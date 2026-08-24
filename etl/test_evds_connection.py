"""
Step 1 sanity check. Run this after init_db.py.

What it does:
1. Calls EVDS (via the tcmb package) for USD/TRY and EUR/TRY buying rates,
   last 14 days.
2. Prints the result to screen so you can eyeball it against
   evds3.tcmb.gov.tr or a currency site.
3. Does NOT write to the database yet — that's load_fx_rates.py.
   This script's only job is to prove the API tap works end to end.

Usage:
    python etl/test_evds_connection.py
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evds_client import get_evds_series

SERIES = {
    "TP.DK.USD.A.YTL": "USD/TRY (buying)",
    "TP.DK.EUR.A.YTL": "EUR/TRY (buying)",
}


def main():
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=14)  # small window, weekends/holidays included
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")

    print(f"Requesting EVDS series {list(SERIES.keys())}")
    print(f"Date range: {start_date} to {end_date}\n")

    try:
        df = get_evds_series(list(SERIES.keys()), start_date, end_date)
    except Exception as e:
        print("FAILED — connection or auth problem.")
        print(f"Error: {e}")
        if "list index out of range" in str(e):
            print("\n(This specific message is a known rough edge in the "
                  "'tcmb' package: it tries to parse an HTML error page and "
                  "chokes when the server returns something else instead — "
                  "usually still means an auth or connectivity failure.)")
        print("\nCheck, in order:")
        print("  1. Is EVDS_API_KEY in your .env file set to the exact key "
              "from evds3.tcmb.gov.tr -> Profilim -> API Key?")
        print("  2. Keys can take a few minutes to activate after first "
              "being generated — try again shortly if you just created it.")
        print("  3. Confirm you have internet access to tcmb.gov.tr right "
              "now (some corporate/school networks block it).")
        sys.exit(1)

    if df.empty:
        print("Request succeeded but returned no rows. "
              "Check the date range (weekends/holidays have no rate published).")
        sys.exit(1)

    # rename the underscore-joined columns back to readable labels
    col_map = {code.replace(".", "_"): label for code, label in SERIES.items()}
    df = df.rename(columns=col_map)

    print(df.tail(10).to_string())
    print("\nConnection test PASSED. EVDS tap is live.")


if __name__ == "__main__":
    main()
