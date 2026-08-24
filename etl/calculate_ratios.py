"""
Step 2 calculation: turns financial_statements_raw into financial_ratios.

Formulas (standard working-capital ratios, quarterly — not annualized):
    DIO = inventory / COGS_standalone_quarter * days_in_quarter
    DSO = accounts_receivable / revenue_standalone_quarter * days_in_quarter
    DPO = accounts_payable / COGS_standalone_quarter * days_in_quarter
    CCC = DIO + DSO - DPO

Notes on choices (state these explicitly if asked in an interview):
- Uses quarter-end balance sheet figures (inventory, AR, AP) as the numerator,
  not average of beginning/ending balance. Average-balance is more "correct"
  textbook practice; quarter-end is simpler and consistent across periods,
  and the difference is a footnote-able caveat, not a broken model. You can
  switch to averages later once you have 2+ consecutive quarters loaded.
- Revenue/COGS must be standalone-quarter, not cumulative YTD, because KAP
  reports income statement items cumulatively. Q1 cumulative = Q1 standalone.
  Q2 standalone = Q2 cumulative - Q1 cumulative. Q3 standalone = Q3 cum - Q2 cum.
  Q4 standalone = FY cum - Q3 cum.
- days_in_quarter uses actual calendar days between the prior quarter-end and
  this quarter-end (not a flat 91.25), for accuracy.

Usage:
    python etl/calculate_ratios.py
"""
import sqlite3
from pathlib import Path
from datetime import datetime, date
import os
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "db/mavi_treasury.db")
COMPANY_ID = 1


def get_raw_pivot(conn, company_id):
    """Returns {(fiscal_year, fiscal_quarter): {line_item_en: value_try, 'period_end': str}}"""
    rows = conn.execute(
        """
        SELECT fiscal_year, fiscal_quarter, period_end, line_item_en, value_try
        FROM financial_statements_raw
        WHERE company_id = ?
        ORDER BY fiscal_year, fiscal_quarter
        """,
        (company_id,),
    ).fetchall()

    pivot = {}
    for fy, fq, period_end, item, val in rows:
        key = (fy, fq)
        pivot.setdefault(key, {"period_end": period_end})
        pivot[key][item] = val
    return pivot


def get_standalone_revenue_cogs(pivot, fy, fq):
    """
    Mavi discloses standalone 3-month figures directly for Q1-Q3 (no subtraction
    needed). The annual report (fq=4) only gives a full-year cumulative total,
    so standalone Q4 = full-year total minus the 9-month cumulative figure
    (loaded separately as revenue_cumulative_9mo / cogs_cumulative_9mo on the
    Q3 row).
    """
    row = pivot.get((fy, fq), {})
    if fq in (1, 2, 3):
        return row.get("revenue"), row.get("cogs")
    elif fq == 4:
        revenue_fy = row.get("revenue")
        cogs_fy = row.get("cogs")
        prev_row = pivot.get((fy, 3), {})
        revenue_9mo = prev_row.get("revenue_cumulative_9mo")
        cogs_9mo = prev_row.get("cogs_cumulative_9mo")
        revenue_sa = revenue_fy - revenue_9mo if None not in (revenue_fy, revenue_9mo) else None
        cogs_sa = cogs_fy - cogs_9mo if None not in (cogs_fy, cogs_9mo) else None
        return revenue_sa, cogs_sa
    return None, None


def days_between(prev_period_end, period_end):
    if prev_period_end is None:
        return 91  # fallback for the first quarter you load, no prior period to diff against
    d1 = date.fromisoformat(prev_period_end)
    d2 = date.fromisoformat(period_end)
    return (d2 - d1).days


def calculate_ratios():
    conn = sqlite3.connect(DB_PATH)
    pivot = get_raw_pivot(conn, COMPANY_ID)
    now = datetime.now().isoformat()

    sorted_keys = sorted(pivot.keys())
    computed = 0

    for i, (fy, fq) in enumerate(sorted_keys):
        row = pivot[(fy, fq)]
        period_end = row["period_end"]
        inventory = row.get("inventory")
        ar = row.get("accounts_receivable")
        ap = row.get("accounts_payable")
        revenue_sa, cogs_sa = get_standalone_revenue_cogs(pivot, fy, fq)

        if None in (inventory, ar, ap, revenue_sa, cogs_sa) or cogs_sa == 0 or revenue_sa == 0:
            print(f"Skipping {fy}-Q{fq}: missing inputs (need inventory, AR, AP, "
                  f"and standalone revenue/COGS — the latter needs this quarter "
                  f"AND the prior quarter loaded).")
            continue

        prev_period_end = pivot[sorted_keys[i - 1]]["period_end"] if i > 0 and sorted_keys[i-1][0] == fy else None
        days = days_between(prev_period_end, period_end)

        dio = inventory / cogs_sa * days
        dso = ar / revenue_sa * days
        dpo = ap / cogs_sa * days
        ccc = dio + dso - dpo

        conn.execute(
            """
            INSERT INTO financial_ratios
                (company_id, period_end, fiscal_year, fiscal_quarter,
                 revenue, cogs, inventory, accounts_receivable, accounts_payable,
                 dio, dso, dpo, ccc, calculated_at, calc_method_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, period_end) DO UPDATE SET
                revenue=excluded.revenue, cogs=excluded.cogs, inventory=excluded.inventory,
                accounts_receivable=excluded.accounts_receivable, accounts_payable=excluded.accounts_payable,
                dio=excluded.dio, dso=excluded.dso, dpo=excluded.dpo, ccc=excluded.ccc,
                calculated_at=excluded.calculated_at, calc_method_notes=excluded.calc_method_notes
            """,
            (
                COMPANY_ID, period_end, fy, fq,
                revenue_sa, cogs_sa, inventory, ar, ap,
                round(dio, 1), round(dso, 1), round(dpo, 1), round(ccc, 1),
                now, f"standalone quarter, {days} days, quarter-end balances (not averaged)",
            ),
        )
        computed += 1
        print(f"{fy}-Q{fq}: DIO={dio:.1f}  DSO={dso:.1f}  DPO={dpo:.1f}  CCC={ccc:.1f} days")

    conn.commit()
    conn.close()
    print(f"\nComputed ratios for {computed} quarter(s).")


if __name__ == "__main__":
    calculate_ratios()
