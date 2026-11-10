"""
Step 5 prep — pulls TCMB commercial loan rate and financing-company (factoring
proxy) loan rate. LC commission is not a published time series; it's a
documented market-benchmark assumption (~6% annualized) sourced separately.
"""

import os
from datetime import datetime
import sqlite3
import tcmb
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "db/mavi_treasury.db"
API_KEY = os.getenv("EVDS_API_KEY")

SERIES = {
    "commercial_loan": "TP.BKR.TRY.1",
    "factoring": "TP.FKF.TRY.1",
}

START_DATE = "01-08-2023"
END_DATE = datetime.today().strftime("%d-%m-%Y")

LC_COMMISSION_RATE = 6.0
LC_SOURCE = "https://www.akreditif.biz.tr/akreditif-acilis-masraf-ve-komisyonlari.html"
LC_NOTES = ("Market benchmark, not company-specific: import LC amount/tenor "
            "amendment commission commonly cited at 6% annualized in Turkish "
            "trade-finance advisory examples. Applied flat across all periods "
            "as a documented assumption, not a time series.")


def fetch_series(code):
    df = tcmb.read(code, startdate=START_DATE, enddate=END_DATE, api_key=API_KEY)
    df = df.reset_index()
    df = df.rename(columns={df.columns[0]: "period", df.columns[1]: "rate_pct"})
    df["period"] = df["period"].astype(str)
    df = df[df["period"] >= "2023-08-01"]
    return df


def upsert_lc_assumption(conn):
    """LC commission: fixed assumption, one row per quarter that has financials.

    Periods come from financial_statements_raw, so a newly loaded quarter gets
    its row automatically (this list used to be hardcoded, which silently
    dropped new quarters from the financing comparison).
    """
    cur = conn.cursor()
    periods = [r[0] for r in cur.execute(
        "SELECT DISTINCT substr(period_end, 1, 7) FROM financial_statements_raw ORDER BY 1")]
    for period in periods:
        cur.execute(
            """
            INSERT INTO financing_rates_raw
                (period, rate_type, rate_pct, series_code, source_url, notes, retrieved_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(period, rate_type) DO UPDATE SET
                rate_pct=excluded.rate_pct, notes=excluded.notes, retrieved_at=excluded.retrieved_at
            """,
            (period, "lc_commission", LC_COMMISSION_RATE, None, LC_SOURCE, LC_NOTES,
             datetime.now().isoformat()),
        )
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for rate_type, code in SERIES.items():
        print(f"Fetching {rate_type} ({code})...")
        df = fetch_series(code)
        for _, row in df.iterrows():
            period, rate = row["period"], row["rate_pct"]
            if rate is None or str(rate) == "nan":
                continue
            cur.execute(
                """
                INSERT INTO financing_rates_raw
                    (period, rate_type, rate_pct, series_code, source_url, retrieved_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(period, rate_type) DO UPDATE SET
                    rate_pct=excluded.rate_pct, retrieved_at=excluded.retrieved_at
                """,
                (period, rate_type, float(rate), code,
                 "https://evds2.tcmb.gov.tr/", datetime.now().isoformat()),
            )
        conn.commit()
        print(f"  {len(df)} rows upserted for {rate_type}")

    upsert_lc_assumption(conn)
    conn.commit()
    conn.close()
    print("LC commission assumption rows added.")
    print("Done.")


if __name__ == "__main__":
    main()
