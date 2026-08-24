"""
Step 7 — Full pipeline orchestrator. Runs every ETL/calculation script in the
correct dependency order, stops on first failure, and reports what ran.

Before running this for a new month:
  1. Check KAP / Mavi IR for a new quarterly filing.
  2. If one exists, manually add rows to data/financials_template.csv and
     data/fx_exposure_template.csv (see README for the exact column format).
  3. Then run this script.

If no new filing exists yet, running this is still safe and useful — it
refreshes FX rates, interest rates, and financing rates (fully automatic,
no manual step needed), so your report stays current even between filings.
"""

import subprocess
import sys
from datetime import datetime

STEPS = [
    ("FX rates (EVDS)", "etl/load_fx_rates.py"),
    ("Interest rates (EVDS)", "etl/load_interest_rates.py"),
    ("Financing rates (EVDS + LC assumption)", "etl/load_financing_rates.py"),
    ("Financials (from CSV — update manually first)", "etl/load_financials.py"),
    ("Cash conversion cycle ratios", "etl/calculate_ratios.py"),
    ("FX exposure (from CSV — update manually first)", "etl/load_fx_exposure.py"),
    ("FX sensitivity", "etl/calculate_fx_sensitivity.py"),
    ("Hedging backtest (forward)", "etl/calculate_hedging_backtest.py"),
    ("Options collar backtest", "etl/calculate_options_collar.py"),
    ("Financing scenario comparison", "etl/calculate_financing_scenarios.py"),
    ("Monthly report (Markdown + HTML)", "etl/generate_monthly_report.py"),
    ("Monthly report (Excel)", "etl/generate_monthly_report_xlsx.py"),
    ("Data verification", "verify_data.py"),
]


def run_step(label, script):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"  ({script})")
    print(f"{'='*70}")
    result = subprocess.run([sys.executable, script])
    return result.returncode == 0


def main():
    print(f"Mavi Treasury Pipeline — started {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("\nReminder: if a new quarterly filing has come out, make sure you've")
    print("added it to data/financials_template.csv and data/fx_exposure_template.csv")
    print("BEFORE this run, or you'll just be refreshing rates on old financials.\n")
    print("After this run finishes: open the generated .xlsx in Excel and save it")
    print("once (Cmd+S) before treating it as final — formulas won't show real")
    print("values until Excel recalculates and you save.\n")

    results = []
    for label, script in STEPS:
        ok = run_step(label, script)
        results.append((label, ok))
        if not ok:
            print(f"\n!!! FAILED: {label} ({script})")
            print("Stopping pipeline here — fix this step, then rerun.")
            break

    print(f"\n{'='*70}")
    print("PIPELINE SUMMARY")
    print(f"{'='*70}")
    for label, ok in results:
        status = "OK" if ok else "FAILED"
        print(f"  [{status:6}] {label}")

    all_ok = all(ok for _, ok in results) and len(results) == len(STEPS)
    print(f"\n{'Completed successfully.' if all_ok else 'Pipeline stopped early — see failure above.'}")


if __name__ == "__main__":
    main()
