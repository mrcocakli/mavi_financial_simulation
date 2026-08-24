"""
Step 2 loader: reads data/financials_template.csv (which you fill in by hand
from KAP filings) and upserts rows into financial_statements_raw.

WHY MANUAL EXTRACTION, NOT SCRAPING:
KAP does not offer a clean free API for structured financial statement data.
Filings are PDF/XBRL documents per disclosure. Scraping XBRL is possible but
fragile and easy to get subtly wrong (wrong period, wrong consolidation
level). For a project whose whole value proposition is being *traceable and
correct*, manually reading each KAP filing and typing ~10-15 line items per
quarter into the CSV is the right tradeoff — it's maybe 15 minutes per
quarter, and every value carries the exact KAP filing URL as its source.

IMPORTANT — KAP interim income statement figures are CUMULATIVE:
Mavi's KAP income statement for Q2 reports revenue/COGS as Jan 1 - Jun 30
(cumulative), not April-June standalone. To get a standalone quarter figure
for ratio calculations, you must subtract the prior cumulative period:
    standalone_Q2 = cumulative_Jan-Jun - cumulative_Jan-Mar
This script stores whatever you put in the CSV as-is (traceability). Do the
cumulative -> standalone conversion explicitly in calculate_ratios.py, not
silently here, so it's visible and checkable.

Usage:
    python etl/load_financials.py
"""
import sqlite3
import csv
from pathlib import Path
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "db/mavi_treasury.db")
CSV_PATH = PROJECT_ROOT / "data" / "financials_template.csv"
COMPANY_ID = 1  # MAVI, from companies table


def load_financials():
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat()

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    inserted = 0
    for row in rows:
        if float(row["value_try"]) == 0:
            # skip placeholder rows you haven't filled in yet
            continue
        conn.execute(
            """
            INSERT INTO financial_statements_raw
                (company_id, period_end, fiscal_year, fiscal_quarter,
                 statement_type, line_item_en, line_item_tr, value_try,
                 unit, source_url, filed_date, retrieved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, period_end, statement_type, line_item_en)
            DO UPDATE SET
                value_try = excluded.value_try,
                source_url = excluded.source_url,
                filed_date = excluded.filed_date,
                retrieved_at = excluded.retrieved_at
            """,
            (
                COMPANY_ID,
                row["period_end"],
                int(row["fiscal_year"]),
                int(row["fiscal_quarter"]),
                row["statement_type"],
                row["line_item_en"],
                row["line_item_tr"],
                float(row["value_try"]),
                row["unit"],
                row["source_url"],
                row["filed_date"],
                now,
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"Loaded/updated {inserted} line items from {CSV_PATH.name}")


if __name__ == "__main__":
    load_financials()
