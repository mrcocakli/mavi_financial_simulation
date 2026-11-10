"""
Sanity check for the whole pipeline so far (Steps 1-3).
Not part of the regular monthly refresh — run this whenever you want to
confirm the database is in the state you think it's in.

Usage:
    python verify_data.py
"""
import sqlite3
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "db/mavi_treasury.db")

checks_passed = 0
checks_failed = 0

def check(label, condition, detail=""):
    global checks_passed, checks_failed
    status = "PASS" if condition else "FAIL"
    if condition:
        checks_passed += 1
    else:
        checks_failed += 1
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))

conn = sqlite3.connect(DB_PATH)

print("=" * 70)
print("1. DATABASE STRUCTURE")
print("=" * 70)
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]
expected_tables = {
    "companies", "financial_ratios", "financial_statements_raw",
    "financing_comparison", "financing_structures", "fx_exposure_items",
    "fx_rates", "hedge_scenarios", "monthly_reports"
}
check("All expected tables exist", expected_tables.issubset(set(tables)),
      f"found {len(tables)} tables")

print()
print("=" * 70)
print("2. STEP 2 — FINANCIAL BASELINE")
print("=" * 70)
raw_periods = conn.execute(
    "SELECT DISTINCT period_end FROM financial_statements_raw ORDER BY period_end"
).fetchall()
raw_periods = [r[0] for r in raw_periods]
print(f"Periods in financial_statements_raw: {raw_periods}")
check("No stray/leftover periods (only real, sourced quarters)",
      "2025-06-30" not in raw_periods,
      "if this fails, run: DELETE FROM financial_statements_raw WHERE period_end='2025-06-30';")
check("At least 2 periods loaded", len(raw_periods) >= 2)

ratio_rows = conn.execute(
    "SELECT period_end, dio, dso, dpo, ccc FROM financial_ratios ORDER BY period_end"
).fetchall()
print(f"Computed ratios: {ratio_rows}")
check("At least 1 quarter of ratios computed", len(ratio_rows) >= 1)

print()
print("=" * 70)
print("3. STEP 1/3 — FX RATES (EVDS)")
print("=" * 70)
fx_count = conn.execute("SELECT COUNT(*) FROM fx_rates").fetchone()[0]
fx_min_max = conn.execute("SELECT MIN(rate_date), MAX(rate_date) FROM fx_rates").fetchone()
print(f"fx_rates row count: {fx_count}, date range: {fx_min_max}")
check("fx_rates is populated (not empty)", fx_count > 0)
check("fx_rates covers at least ~2 years", fx_count > 500,
      "expect ~730/year x 2 currencies x 2 rate types minus weekends/holidays")

pairs = conn.execute("SELECT DISTINCT currency_pair FROM fx_rates").fetchall()
pairs = {r[0] for r in pairs}
check("Both USDTRY and EURTRY present", {"USDTRY", "EURTRY"}.issubset(pairs))

print()
print("=" * 70)
print("4. STEP 3 — FX EXPOSURE")
print("=" * 70)
exp_periods = conn.execute(
    "SELECT DISTINCT period_end FROM fx_exposure_items ORDER BY period_end"
).fetchall()
exp_periods = [r[0] for r in exp_periods]
print(f"Periods in fx_exposure_items: {exp_periods}")
check("at least 4 quarters of FX exposure loaded", len(exp_periods) >= 4,
      f"found {len(exp_periods)}")

exp_rows = conn.execute(
    "SELECT period_end, currency_linked, direction, balance_try FROM fx_exposure_items ORDER BY period_end, currency_linked"
).fetchall()
for row in exp_rows:
    print(f"  {row}")
check("two exposure rows (USD + EUR) per quarter", len(exp_rows) == 2 * len(exp_periods),
      f"found {len(exp_rows)}")

print()
print("Checking each exposure period has a nearby fx_rate for backtest use...")
for pe in exp_periods:
    nearest = conn.execute(
        "SELECT rate_date FROM fx_rates WHERE rate_date <= ? ORDER BY rate_date DESC LIMIT 1",
        (pe,)
    ).fetchone()
    ok = nearest is not None
    check(f"  fx_rates has data at/before {pe}", ok,
          f"nearest: {nearest[0] if nearest else 'NONE FOUND'}")

conn.close()

print()
print("=" * 70)
print(f"RESULT: {checks_passed} passed, {checks_failed} failed")
print("=" * 70)
if checks_failed == 0:
    print("Everything checks out. Safe to move on to Step 4.")
else:
    print("Fix the FAIL items above before building the hedging backtest on top of this.")
