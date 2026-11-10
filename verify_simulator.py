"""
Reconciles the Excel simulator against the Python engine.

Reads the cached values of reports/mavi_treasury_simulator.xlsx (so the file
must have been recalculated — opened and saved in Excel, or run through
LibreOffice) and checks every Engine line for every scenario, plus sample
cells of the three sensitivity grids, against etl/simulator_engine.py.

Usage:  python verify_simulator.py
"""
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent / "etl"))
from simulator_engine import BASE, PRESETS, load_baselines, run  # noqa: E402
from build_simulator_xlsx import CUSTOM, OUT_PATH, SCEN_COLS  # noqa: E402

TOL = 0.51  # TRY thousand; Excel and Python both carry full float precision

ENGINE_ROWS = {  # Engine row -> engine.run() key
    16: "revenue", 17: "cogs", 18: "gross_profit", 22: "dio", 23: "dso", 24: "dpo", 25: "ccc",
    28: "inventory", 29: "ar", 30: "ap", 31: "nwc", 32: "d_nwc", 33: "cash_impact",
    36: "loan_rate", 37: "funding_cost", 38: "d_funding_cost", 41: "usd_s1", 42: "eur_s1",
    43: "usd_fwd", 44: "eur_fwd", 47: "usd_pnl", 48: "eur_pnl", 49: "fx_pnl", 50: "fx_unhedged",
    53: "d_gross_profit", 56: "pnl_impact", 57: "cash_impact",
}


def main():
    wb = load_workbook(OUT_PATH, data_only=True)
    eng, sen, inp = wb["Engine"], wb["Sensitivity"], wb["Inputs"]
    if eng["C16"].value is None:
        sys.exit("Workbook has no cached values — open and save it in Excel first.")
    baselines, _ = load_baselines()
    b = next(x for x in baselines if x["label"] == inp["C5"].value)
    scen = [s for _, s in PRESETS] + [CUSTOM]
    checks = fails = 0
    for col, s in zip(SCEN_COLS, scen):
        r = run(b, s)
        for row, key in ENGINE_ROWS.items():
            checks += 1
            x, p = eng[f"{col}{row}"].value, r[key]
            if abs(x - p) > TOL:
                fails += 1
                print(f"MISMATCH Engine!{col}{row} ({key}): Excel {x} vs Python {p}")
    # Sensitivity samples: (cell, scenario, key)
    samples = [
        ("E13", dict(BASE, usd_shock=0.20, eur_shock=0.20, hedge_ratio=0.5), "fx_pnl"),   # grid A: +20%, 50%
        ("G8", dict(BASE, usd_shock=-0.05, eur_shock=-0.05, hedge_ratio=1.0), "fx_pnl"),  # grid A: -5%, 100%
        ("C26", dict(BASE, d_dso=15, d_dpo=-30), "cash_impact"),                          # grid B
        ("H22", dict(BASE, d_dso=-5, d_dpo=20), "cash_impact"),                           # grid B
        ("E35", dict(BASE, inv_build=0.20, usd_shock=0.20), "cash_impact"),               # grid C
        ("G38", dict(BASE, inv_build=0.50, usd_shock=0.40), "cash_impact"),               # grid C
    ]
    for cell, s, key in samples:
        checks += 1
        x, p = sen[cell].value, run(b, s)[key]
        if x is None or abs(x - p) > TOL:
            fails += 1
            print(f"MISMATCH Sensitivity!{cell}: Excel {x} vs Python {p}")
    print(f"Simulator reconciliation: {checks - fails}/{checks} checks passed "
          f"(baseline {b['label']}).")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
