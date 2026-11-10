"""
Treasury simulator — scenario engine (single source of truth for the maths).

The Excel workbook (etl/build_simulator_xlsx.py), the Streamlit page
(dashboard/simulator_app.py) and the standalone web page
(etl/build_simulator_html.py) all implement exactly these formulas.
tests in verify_simulator.py reconcile the three.

All money amounts are TRY thousand, one fiscal quarter.

Drivers (a "scenario")
    growth        sales volume growth vs baseline quarter            (fraction)
    usd_shock     % change in USD/TRY over the horizon, + = weaker TRY (fraction)
    eur_shock     % change in EUR/TRY over the horizon                (fraction)
    d_dso         change in days sales outstanding                    (days)
    d_dpo         change in days payables outstanding                 (days)
    inv_build     inventory held above baseline DIO                   (fraction)
    hedge_ratio   share of net FX monetary position sold/bought fwd   (fraction)
    rate_bps      shock to the TRY commercial loan rate               (basis points)

Assumptions (apply to every scenario)
    fx_cogs_share share of COGS that reprices with USD/TRY — an
                  ILLUSTRATIVE ASSUMPTION, not a Mavi disclosure
    horizon_days  hedge horizon used for the CIRP forward (default 90)

Formulas
    days        = period_end - end of month three months earlier (actual days)
    DIO0        = inventory / COGS * days      (same for DSO0 on revenue, DPO0 on COGS)
    revenue_s   = revenue * (1 + growth)
    cogs_s      = COGS * (1 + growth) * (1 + fx_cogs_share * usd_shock)
    inventory_s = cogs_s / days * DIO0 * (1 + inv_build)
    AR_s        = revenue_s / days * (DSO0 + d_dso)
    AP_s        = cogs_s / days * (DPO0 + d_dpo)
    NWC         = inventory + AR - AP          cash impact = -(NWC_s - NWC_0)
    funding     = NWC * loan_rate * days / 365 (same convention as
                  calculate_financing_scenarios.py)
    forward F   = S0 * (1 + i_try*n/365) / (1 + i_fx*n/365)   (CIRP proxy, same
                  as calculate_hedging_backtest.py)
    FX P&L      = (1-h) * N * (S1 - S0) + h * N * (F - S0),  S1 = S0 * (1 + shock)
    P&L impact  = d(gross profit) + FX P&L - d(funding cost)
"""
import sqlite3
from datetime import date, timedelta

DRIVERS = ["growth", "usd_shock", "eur_shock", "d_dso", "d_dpo",
           "inv_build", "hedge_ratio", "rate_bps"]

DEFAULT_ASSUMPTIONS = {"fx_cogs_share": 0.25, "horizon_days": 90}

BASE = dict(growth=0.0, usd_shock=0.0, eur_shock=0.0, d_dso=0.0, d_dpo=0.0,
            inv_build=0.0, hedge_ratio=0.0, rate_bps=0.0)

PRESETS = [
    ("Base", dict(BASE)),
    ("TRY depreciation", dict(BASE, usd_shock=0.20, eur_shock=0.20)),
    ("Payment terms squeeze", dict(BASE, d_dso=15.0, d_dpo=-20.0)),
    ("Inventory build", dict(BASE, inv_build=0.25)),
    ("Combined stress", dict(BASE, usd_shock=0.20, eur_shock=0.20, d_dso=10.0,
                             d_dpo=-15.0, inv_build=0.20, hedge_ratio=0.50,
                             rate_bps=500.0)),
]


def quarter_days(period_end: str) -> int:
    """Actual days in the fiscal quarter ending on period_end (a month end)."""
    d2 = date.fromisoformat(period_end)
    y, m = d2.year, d2.month - 3
    if m <= 0:
        y, m = y - 1, m + 12
    # last day of month m: first day of month m+1 minus one day
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    d1 = date(ny, nm, 1) - timedelta(days=1)
    return (d2 - d1).days


def load_baselines(db_path="db/mavi_treasury.db", company_id=1):
    """One dict per quarter that has financials + FX position + rates loaded."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    fin = conn.execute(
        """SELECT r.period_end, r.fiscal_year, r.fiscal_quarter, r.revenue, r.cogs,
                  r.inventory, r.accounts_receivable, r.accounts_payable,
                  f.commercial_loan_rate_pct, f.factoring_rate_pct
           FROM financial_ratios r
           JOIN financing_scenario_results f
             ON f.company_id = r.company_id AND f.period_end = r.period_end
           WHERE r.company_id = ? ORDER BY r.period_end""", (company_id,)).fetchall()
    out = []
    for r in fin:
        hb = {h["currency_linked"]: h for h in conn.execute(
            """SELECT currency_linked, native_amount_k, spot_at_hedge_start,
                      try_rate_pct, fx_rate_pct
               FROM hedging_backtest_results
               WHERE company_id = ? AND period_end = ?""",
            (company_id, r["period_end"]))}
        if "USD" not in hb or "EUR" not in hb:
            continue
        src = conn.execute(
            """SELECT source_url FROM financial_statements_raw
               WHERE company_id = ? AND period_end = ? LIMIT 1""",
            (company_id, r["period_end"])).fetchone()
        out.append({
            "period_end": r["period_end"],
            "label": f"FY{r['fiscal_year']} Q{r['fiscal_quarter']} ({r['period_end']})",
            "revenue": r["revenue"], "cogs": r["cogs"], "inventory": r["inventory"],
            "ar": r["accounts_receivable"], "ap": r["accounts_payable"],
            "days": quarter_days(r["period_end"]),
            "loan_rate": r["commercial_loan_rate_pct"] / 100.0,
            "factoring_rate": r["factoring_rate_pct"] / 100.0,
            "usd_native": hb["USD"]["native_amount_k"], "eur_native": hb["EUR"]["native_amount_k"],
            "usd_spot": hb["USD"]["spot_at_hedge_start"], "eur_spot": hb["EUR"]["spot_at_hedge_start"],
            "try_rate": hb["USD"]["try_rate_pct"] / 100.0,
            "usd_rate": hb["USD"]["fx_rate_pct"] / 100.0,
            "eur_rate": hb["EUR"]["fx_rate_pct"] / 100.0,
            "source_url": src["source_url"] if src else "",
        })
    asof = conn.execute("SELECT max(rate_date) FROM fx_rates").fetchone()[0]
    conn.close()
    return out, asof


def run(b: dict, s: dict, a: dict = None) -> dict:
    """Evaluate one scenario s against baseline quarter b. Returns all lines."""
    a = {**DEFAULT_ASSUMPTIONS, **(a or {})}
    s = {**BASE, **s}
    days, n = b["days"], a["horizon_days"]

    dio0 = b["inventory"] / b["cogs"] * days
    dso0 = b["ar"] / b["revenue"] * days
    dpo0 = b["ap"] / b["cogs"] * days
    nwc0 = b["inventory"] + b["ar"] - b["ap"]
    gp0 = b["revenue"] - b["cogs"]
    fund0 = nwc0 * b["loan_rate"] * days / 365

    revenue = b["revenue"] * (1 + s["growth"])
    cogs = b["cogs"] * (1 + s["growth"]) * (1 + a["fx_cogs_share"] * s["usd_shock"])
    dio = dio0 * (1 + s["inv_build"])
    dso = dso0 + s["d_dso"]
    dpo = dpo0 + s["d_dpo"]
    inventory = cogs / days * dio
    ar = revenue / days * dso
    ap = cogs / days * dpo
    nwc = inventory + ar - ap
    rate = b["loan_rate"] + s["rate_bps"] / 10000.0
    fund = nwc * rate * days / 365

    fx = {}
    for c in ("usd", "eur"):
        s0 = b[f"{c}_spot"]
        s1 = s0 * (1 + s[f"{c}_shock"])
        fwd = s0 * (1 + b["try_rate"] * n / 365) / (1 + b[f"{c}_rate"] * n / 365)
        nat = b[f"{c}_native"]
        unhedged = nat * (s1 - s0)
        pnl = (1 - s["hedge_ratio"]) * unhedged + s["hedge_ratio"] * nat * (fwd - s0)
        fx[c] = dict(s1=s1, fwd=fwd, unhedged=unhedged, pnl=pnl)

    gp = revenue - cogs
    fx_pnl = fx["usd"]["pnl"] + fx["eur"]["pnl"]
    return {
        "revenue": revenue, "cogs": cogs, "gross_profit": gp,
        "dio": dio, "dso": dso, "dpo": dpo, "ccc": dio + dso - dpo,
        "inventory": inventory, "ar": ar, "ap": ap, "nwc": nwc,
        "d_nwc": nwc - nwc0, "cash_impact": -(nwc - nwc0),
        "loan_rate": rate, "funding_cost": fund, "d_funding_cost": fund - fund0,
        "usd_s1": fx["usd"]["s1"], "eur_s1": fx["eur"]["s1"],
        "usd_fwd": fx["usd"]["fwd"], "eur_fwd": fx["eur"]["fwd"],
        "fx_unhedged": fx["usd"]["unhedged"] + fx["eur"]["unhedged"],
        "usd_pnl": fx["usd"]["pnl"], "eur_pnl": fx["eur"]["pnl"], "fx_pnl": fx_pnl,
        "d_gross_profit": gp - gp0,
        "pnl_impact": (gp - gp0) + fx_pnl - (fund - fund0),
        "base": dict(dio=dio0, dso=dso0, dpo=dpo0, ccc=dio0 + dso0 - dpo0,
                     nwc=nwc0, funding_cost=fund0, gross_profit=gp0),
    }


if __name__ == "__main__":
    baselines, asof = load_baselines()
    b = baselines[-1]
    print(f"Baseline {b['label']}, {b['days']} days, FX data to {asof}")
    for name, sc in PRESETS:
        r = run(b, sc)
        print(f"{name:24s} CCC {r['ccc']:6.1f}  cash {r['cash_impact']:>12,.0f}  "
              f"FX P&L {r['fx_pnl']:>10,.0f}  P&L {r['pnl_impact']:>12,.0f}")
