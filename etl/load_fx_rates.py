"""
Step 3 loader: pulls daily USD/TRY and EUR/TRY (buying + selling) from EVDS
(via the tcmb package) and writes them into fx_rates. Chunks requests by
calendar year as a safety margin — TCMB's web service has historically
limited how much data a single request returns, and yearly chunks stay
comfortably under that regardless of frequency.

Usage:
    python etl/load_fx_rates.py --start 2023-01-01 --end 2025-12-31
    (defaults to last 3 years if no args given)
"""
import argparse
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, date
import os
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evds_client import get_evds_series

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "db/mavi_treasury.db")

SERIES_MAP = {
    "TP.DK.USD.A.YTL": ("USDTRY", "buying"),
    "TP.DK.USD.S.YTL": ("USDTRY", "selling"),
    "TP.DK.EUR.A.YTL": ("EURTRY", "buying"),
    "TP.DK.EUR.S.YTL": ("EURTRY", "selling"),
}


def year_chunks(start: date, end: date):
    chunks = []
    cur = start
    while cur <= end:
        chunk_end = min(date(cur.year, 12, 31), end)
        chunks.append((cur, chunk_end))
        cur = date(cur.year + 1, 1, 1)
    return chunks


def load_fx_rates(start_date: str, end_date: str):
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat()
    total_rows = 0

    for chunk_start, chunk_end in year_chunks(start, end):
        s_str = chunk_start.isoformat()
        e_str = chunk_end.isoformat()
        print(f"Pulling {s_str} to {e_str} ...")

        df = get_evds_series(list(SERIES_MAP.keys()), s_str, e_str)

        for rate_date_ts, row in df.iterrows():
            rate_date = rate_date_ts.strftime("%Y-%m-%d")

            for series_code, (pair, rate_type) in SERIES_MAP.items():
                col = series_code.replace(".", "_")
                if col not in row or pd.isna(row[col]):
                    continue  # holiday/weekend, no rate published
                val = row[col]
                conn.execute(
                    """
                    INSERT INTO fx_rates
                        (rate_date, currency_pair, rate_type, rate, source, series_code, retrieved_at)
                    VALUES (?, ?, ?, ?, 'TCMB EVDS', ?, ?)
                    ON CONFLICT(rate_date, currency_pair, rate_type)
                    DO UPDATE SET rate=excluded.rate, retrieved_at=excluded.retrieved_at
                    """,
                    (rate_date, pair, rate_type, float(val), series_code, now),
                )
                total_rows += 1

        conn.commit()

    conn.close()
    print(f"\nDone. Upserted {total_rows} fx_rates rows covering {start_date} to {end_date}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None, help="YYYY-MM-DD, defaults to 3 years ago")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, defaults to today")
    args = parser.parse_args()

    end_default = date.today()
    start_default = date(end_default.year - 3, end_default.month, end_default.day)

    start_date = args.start or start_default.isoformat()
    end_date = args.end or end_default.isoformat()

    load_fx_rates(start_date, end_date)
