"""
Step 3 output: for each currency the company is exposed to, computes the TRY
P&L swing from a 1% move in that currency against TRY — the headline number
this step is meant to produce.

Method: TRY-equivalent net position (already stored in fx_exposure_items,
converted at the period-end rate when it was loaded) x 1%. This is linear
because these are monetary positions (cash, receivables, payables, debt) —
their TRY value moves close to proportionally with the FX rate. It's the
same method companies use for their own 10%-shock disclosures in Note 25/26
of KAP filings (just scaled to 1% instead of 10%), which is why we can
directly cross-check our number against the company's own disclosure.

Usage:
    python etl/calculate_fx_sensitivity.py
"""
import sqlite3
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "db/mavi_treasury.db")
COMPANY_ID = 1


def calculate_sensitivity():
    conn = sqlite3.connect(DB_PATH)

    periods = [r[0] for r in conn.execute(
        "SELECT DISTINCT period_end FROM fx_exposure_items WHERE company_id = ? ORDER BY period_end DESC",
        (COMPANY_ID,)
    ).fetchall()]

    if not periods:
        print("No fx_exposure_items rows found. Run load_fx_exposure.py first.")
        return

    latest_period = periods[0]
    print(f"FX sensitivity as of {latest_period}\n")

    rows = conn.execute(
        """
        SELECT currency_linked, SUM(balance_try) as net_try
        FROM fx_exposure_items
        WHERE company_id = ? AND period_end = ?
        GROUP BY currency_linked
        """,
        (COMPANY_ID, latest_period),
    ).fetchall()

    total_abs_1pct = 0
    print(f"{'Currency':<10}{'Net TRY position':>20}{'1% move = TRY swing':>24}")
    for currency, net_try in rows:
        sensitivity_1pct = net_try * 0.01
        total_abs_1pct += abs(sensitivity_1pct)
        print(f"{currency:<10}{net_try:>20,.0f}{sensitivity_1pct:>24,.0f}")

    print(f"\nCombined magnitude (sum of absolute 1% moves): {total_abs_1pct:,.0f} thousand TRY")
    print("\n(Cross-check: company's own Note 25 discloses a 10% USD move as "
          "±82,378 thousand TRY and a 10% EUR move as ∓5,292 thousand TRY — "
          "divide by 10 to compare against the 1% figures above.)")

    conn.close()


if __name__ == "__main__":
    calculate_sensitivity()
