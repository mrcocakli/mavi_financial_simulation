"""
Step 4 prep — pulls TCMB weighted average deposit interest rates (TRY, USD, EUR),
up to 3-month tenor, monthly stock basis. Used as the CIRP interest rate
differential input for the forward-rate proxy in the hedging backtest.
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
    "TRY": "TP.MT210AGS.TRY.MT02",
    "USD": "TP.MT210AGS.USD.MT02",
    "EUR": "TP.MT210AGS.EUR.MT02",
}

START_DATE = "01-08-2023"
END_DATE = datetime.today().strftime("%d-%m-%Y")


def fetch_series(code):
    df = tcmb.read(code, startdate=START_DATE, enddate=END_DATE, api_key=API_KEY)
    df = df.reset_index()
    df = df.rename(columns={df.columns[0]: "period", df.columns[1]: "rate_pct"})
    df["period"] = df["period"].astype(str)
    df = df[df["period"] >= "2023-08-01"]    
    return df


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for currency, code in SERIES.items():
        print(f"Fetching {currency} ({code})...")
        df = fetch_series(code)

        for _, row in df.iterrows():
            period = row["period"]
            rate = row["rate_pct"]
            if rate is None or str(rate) == "nan":
                continue

            cur.execute(
                """
                INSERT INTO interest_rates_raw
                    (period, currency, tenor, rate_pct, series_code, source_url, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(period, currency, tenor) DO UPDATE SET
                    rate_pct=excluded.rate_pct,
                    retrieved_at=excluded.retrieved_at
                """,
                (period, currency, "3M", float(rate), code,
                 "https://evds2.tcmb.gov.tr/", datetime.now().isoformat()),
            )

        conn.commit()
        print(f"  {len(df)} rows upserted for {currency}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
