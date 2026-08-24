"""
Step 3 loader: reads data/fx_exposure_template.csv (manually extracted from
the company's own FX risk disclosure — typically Note 25/26 in the KAP/IR
financial statement filing, "Kur riski" / "Finansal araçlardan kaynaklanan
risklerin niteliği ve düzeyi") and upserts into fx_exposure_items.

WHY MANUAL EXTRACTION AGAIN:
Same rationale as load_financials.py — this disclosure exists only inside
the filed PDF, in a company-specific table layout. No API serves it.
Each row keeps its exact source (filing URL) and a notes field documenting
the conversion method (native currency amount + which exchange rate was
used), so the TRY figure is always traceable back to two things: the
company's own disclosed FX-native number, and the specific EVDS/company
rate used to convert it.

Usage:
    python etl/load_fx_exposure.py
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
CSV_PATH = PROJECT_ROOT / "data" / "fx_exposure_template.csv"
COMPANY_ID = 1


def load_fx_exposure():
    conn = sqlite3.connect(DB_PATH)

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    inserted = 0
    for row in rows:
        conn.execute(
            """
            INSERT INTO fx_exposure_items
                (company_id, period_end, item_name, exposure_type, balance_try,
                 currency_linked, direction, notes, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, period_end, item_name)
            DO UPDATE SET
                balance_try=excluded.balance_try,
                notes=excluded.notes,
                source=excluded.source
            """,
            (
                COMPANY_ID,
                row["period_end"],
                row["item_name"],
                row["exposure_type"],
                float(row["balance_try"]),
                row["currency_linked"],
                row["direction"],
                row["notes"],
                row["source"],
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"Loaded/updated {inserted} FX exposure items from {CSV_PATH.name}")


if __name__ == "__main__":
    load_fx_exposure()
