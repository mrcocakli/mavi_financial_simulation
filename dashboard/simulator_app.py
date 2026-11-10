"""
Treasury simulator — Streamlit page.

Run from the project root:
    streamlit run dashboard/simulator_app.py

To add it to an existing multi-page Streamlit app, copy this file into that
app's pages/ folder; it only depends on etl/simulator_engine.py and the DB.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "etl"))
from simulator_engine import BASE, DEFAULT_ASSUMPTIONS, PRESETS, load_baselines, run  # noqa: E402

st.set_page_config(page_title="Mavi Treasury Simulator", layout="wide")

baselines, asof = load_baselines(str(ROOT / "db" / "mavi_treasury.db"))
if not baselines:
    st.error("No complete baseline quarter in the database. Run `python etl/run_pipeline.py` first.")
    st.stop()

# (key, label, min, max, step, scale to engine units, help)
LEVERS = [
    ("usd_shock", "USD/TRY shock (%)", -10, 50, 1, 100, "+ means a weaker lira"),
    ("eur_shock", "EUR/TRY shock (%)", -10, 50, 1, 100, None),
    ("hedge_ratio", "Hedge ratio, forward (%)", 0, 100, 5, 100, "Share of each net FX position locked at the CIRP forward"),
    ("d_dso", "Change in DSO (days)", -15, 30, 1, 1, "+ means customers pay later"),
    ("d_dpo", "Change in DPO (days)", -30, 30, 1, 1, "- means suppliers are paid sooner"),
    ("inv_build", "Inventory build (%)", -20, 50, 1, 100, "Extra stock days vs baseline DIO"),
    ("growth", "Sales volume growth (%)", -20, 30, 1, 100, None),
    ("rate_bps", "Loan rate shock (bps)", -1000, 1000, 50, 1, None),
]


def apply_preset():
    preset = dict(PRESETS)[st.session_state["preset"]]
    for key, _, _, _, _, scale, _ in LEVERS:
        st.session_state[key] = int(round(preset[key] * scale))


for key, *_ in LEVERS:
    st.session_state.setdefault(key, 0)

st.title("Mavi Treasury Simulator")
st.caption(f"Scenario analysis on Mavi Giyim's reported working capital and FX position. "
           f"Market data to {asof}. Simulation on public data; not a forecast.")

with st.sidebar:
    labels = [b["label"] for b in baselines]
    b = baselines[labels.index(st.selectbox("Baseline quarter", labels, index=len(labels) - 1))]
    st.selectbox("Preset scenario", [n for n, _ in PRESETS], key="preset", on_change=apply_preset)
    st.subheader("Levers")
    for key, label, lo, hi, step, _, hlp in LEVERS:
        st.slider(label, lo, hi, step=step, key=key, help=hlp)
    st.subheader("Model assumptions")
    fx_share = st.slider("FX-linked share of COGS (%)", 0, 60, int(DEFAULT_ASSUMPTIONS["fx_cogs_share"] * 100), 5,
                         help="Illustrative assumption. Mavi does not disclose this.")
    horizon = st.slider("Hedge horizon (days)", 30, 180, DEFAULT_ASSUMPTIONS["horizon_days"], 30)

s = {key: st.session_state[key] / scale for key, _, _, _, _, scale, _ in LEVERS}
a = {"fx_cogs_share": fx_share / 100, "horizon_days": horizon}
r = run(b, s, a)


def try_m(v):
    return f"{v / 1e3:,.0f}"


k1, k2, k3, k4 = st.columns(4)
k1.metric("Cash impact (TRY m)", try_m(r["cash_impact"]), help="Minus the change in net trade working capital")
k2.metric("Quarter P&L impact (TRY m)", try_m(r["pnl_impact"]), help="Change in gross profit + FX P&L - extra funding cost")
k3.metric("Cash conversion cycle (days)", f"{r['ccc']:.1f}", f"{r['ccc'] - r['base']['ccc']:+.1f} vs baseline", delta_color="inverse")
k4.metric("FX P&L (TRY m)", try_m(r["fx_pnl"]), f"unhedged {try_m(r['fx_unhedged'])}", delta_color="off")

c1, c2 = st.columns(2)
with c1:
    st.subheader("Trade working capital (TRY m)")
    wc = pd.DataFrame({
        "Baseline": [b["inventory"], b["ar"], b["ap"], r["base"]["nwc"]],
        "Scenario": [r["inventory"], r["ar"], r["ap"], r["nwc"]],
    }, index=["Inventory", "Receivables", "Payables", "Net working capital"]) / 1e3
    st.bar_chart(wc, stack=False)
with c2:
    st.subheader("Quarter P&L impact by driver (TRY m)")
    pl = pd.DataFrame({"TRY m": [r["d_gross_profit"], r["fx_pnl"], -r["d_funding_cost"], r["pnl_impact"]]},
                      index=["1 Gross profit", "2 FX on net position", "3 Funding cost", "4 Total"]) / 1e3
    st.bar_chart(pl)

st.subheader("FX P&L on the net monetary position, by size of lira move (TRY m)")
shocks = list(range(-10, 51, 2))
fx = pd.DataFrame({
    name: [run(b, {**s, "usd_shock": p / 100, "eur_shock": p / 100, "hedge_ratio": h}, a)["fx_pnl"] / 1e3 for p in shocks]
    for name, h in [("Unhedged", 0.0), (f"Chosen ({s['hedge_ratio']:.0%})", s["hedge_ratio"]), ("Fully hedged", 1.0)]
}, index=pd.Index(shocks, name="Lira move (%)"))
st.line_chart(fx)

st.subheader("The numbers (TRY thousand, one quarter)")
base = run(b, BASE, a)
lines = [("DIO (days)", "dio"), ("DSO (days)", "dso"), ("DPO (days)", "dpo"), ("Cash conversion cycle (days)", "ccc"),
         ("Revenue", "revenue"), ("COGS", "cogs"), ("Gross profit", "gross_profit"), ("Inventory", "inventory"),
         ("Trade receivables", "ar"), ("Trade payables", "ap"), ("Net trade working capital", "nwc"),
         ("Funding cost for the quarter", "funding_cost"), ("FX P&L on monetary position", "fx_pnl")]
tbl = pd.DataFrame([(lab, base[k], r[k], r[k] - base[k]) for lab, k in lines],
                   columns=["Line", "Baseline", "Scenario", "Change"]).set_index("Line")
st.dataframe(tbl.style.format("{:,.1f}"))

with st.expander("Method and limits"):
    st.markdown(
        "- Working capital is rebuilt from days (DIO, DSO, DPO) on scenario revenue and COGS; cash impact is "
        "minus the change in inventory + receivables - payables.\n"
        "- The hedged share of each net FX position is locked at a covered-interest-parity forward from TCMB "
        "deposit rates. This is a proxy; free TRY forward quotes do not exist.\n"
        "- Funding cost = net trade working capital x TRY commercial loan rate x days / 365.\n"
        "- The FX-linked share of COGS is an illustrative assumption, not a Mavi disclosure.\n"
        "- Balances are quarter-end points, not averages. Inventory and payables reprice immediately.\n"
        "- Formulas are identical to the Excel model (`reports/mavi_treasury_simulator.xlsx`) and are "
        "reconciled by `verify_simulator.py`.")
