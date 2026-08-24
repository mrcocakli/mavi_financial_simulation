"""
Step 6 — Monthly treasury report generator.
Pulls from financial_ratios, fx_exposure_items, hedging_backtest_results,
options_collar_results, and financing_scenario_results. Produces both a
Markdown and an HTML version: latest quarter as headline, full trend as
appendix.
"""

import sqlite3
from datetime import datetime

DB_PATH = "db/mavi_treasury.db"
COMPANY_ID = 1
COLLAR_K = 0.75  # headline collar width shown in the report


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_ccc_trend(cur):
    cur.execute(
        """
        SELECT period_end, fiscal_year, fiscal_quarter, dio, dso, dpo, ccc
        FROM financial_ratios WHERE company_id=? ORDER BY period_end
        """,
        (COMPANY_ID,),
    )
    return cur.fetchall()


def fetch_fx_exposure_latest(cur, period_end):
    cur.execute(
        """
        SELECT currency_linked, direction, balance_try
        FROM fx_exposure_items
        WHERE company_id=? AND period_end=? AND exposure_type='balance_sheet'
        ORDER BY currency_linked
        """,
        (COMPANY_ID, period_end),
    )
    return cur.fetchall()


def fetch_hedging_summary(cur):
    cur.execute(
        """
        SELECT h.period_end, h.currency_linked, h.status,
               h.unhedged_pnl_try,
               (h.unhedged_pnl_try + h.pnl_forward_vs_unhedged_try) AS forward_pnl_try,
               c.k_factor,
               (h.unhedged_pnl_try + c.pnl_collar_vs_unhedged_try) AS collar_pnl_try
        FROM hedging_backtest_results h
        LEFT JOIN options_collar_results c
            ON h.company_id=c.company_id AND h.period_end=c.period_end
            AND h.currency_linked=c.currency_linked AND h.direction=c.direction
            AND c.k_factor=?
        WHERE h.company_id=?
        ORDER BY h.period_end, h.currency_linked
        """,
        (COLLAR_K, COMPANY_ID),
    )
    return cur.fetchall()


def fetch_financing_trend(cur):
    cur.execute(
        """
        SELECT period_end, baseline_wc_financing_cost_try, factoring_ar_cost_try,
               factoring_vs_baseline_ar_saving_try, lc_ap_cost_try, scf_ap_cost_try,
               lc_scf_comparison_note
        FROM financing_scenario_results WHERE company_id=? ORDER BY period_end
        """,
        (COMPANY_ID,),
    )
    return cur.fetchall()


def fmt_k(val):
    if val is None:
        return "n/a"
    return f"{val:+,.0f}k TRY"


def build_report_data():
    conn = get_conn()
    cur = conn.cursor()

    ccc_trend = fetch_ccc_trend(cur)
    latest_ccc = ccc_trend[-1] if ccc_trend else None
    latest_period = latest_ccc["period_end"] if latest_ccc else None

    fx_latest = fetch_fx_exposure_latest(cur, latest_period) if latest_period else []
    hedging = fetch_hedging_summary(cur)
    financing_trend = fetch_financing_trend(cur)
    latest_financing = financing_trend[-1] if financing_trend else None

    conn.close()
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "latest_period": latest_period,
        "latest_ccc": latest_ccc,
        "ccc_trend": ccc_trend,
        "fx_latest": fx_latest,
        "hedging": hedging,
        "latest_financing": latest_financing,
        "financing_trend": financing_trend,
    }


def render_markdown(d):
    lines = []
    lines.append(f"# Mavi Giyim (BIST: MAVI) — Treasury Report")
    lines.append(f"*Generated {d['generated_at']} | Data through {d['latest_period']}*\n")

    lines.append("## Headline — Latest Quarter\n")
    if d["latest_ccc"]:
        c = d["latest_ccc"]
        lines.append(f"**Period:** {c['period_end']} (FY{c['fiscal_year']} Q{c['fiscal_quarter']})\n")
        lines.append(f"- Cash Conversion Cycle: **{c['ccc']:.1f} days** "
                      f"(DIO {c['dio']:.1f} + DSO {c['dso']:.1f} − DPO {c['dpo']:.1f})\n")

    lines.append("**FX Exposure (balance sheet, latest quarter):**\n")
    for row in d["fx_latest"]:
        lines.append(f"- {row['currency_linked']} ({row['direction']}): {fmt_k(row['balance_try'])}")
    lines.append("")

    lines.append("**Hedging performance, most recent settled quarter (k=0.75 collar):**\n")
    lines.append("| Period | Ccy | Unhedged | Forward | Collar | Status |")
    lines.append("|---|---|---|---|---|---|")
    for row in d["hedging"][-4:]:
        lines.append(f"| {row['period_end']} | {row['currency_linked']} | "
                      f"{fmt_k(row['unhedged_pnl_try'])} | {fmt_k(row['forward_pnl_try'])} | "
                      f"{fmt_k(row['collar_pnl_try'])} | {row['status']} |")
    lines.append("")

    if d["latest_financing"]:
        f = d["latest_financing"]
        lines.append("**Financing costs, latest quarter:**\n")
        lines.append(f"- Baseline working-capital cost: {fmt_k(f['baseline_wc_financing_cost_try'])}")
        lines.append(f"- Factoring vs. baseline (AR): {fmt_k(f['factoring_vs_baseline_ar_saving_try'])} "
                      f"(negative = factoring costs more)")
        lines.append(f"- LC cost: {fmt_k(f['lc_ap_cost_try'])} | SCF cost: {fmt_k(f['scf_ap_cost_try'])} "
                      f"*(not directly comparable — see note)*")
        lines.append("")

    lines.append("---\n## Appendix — Full Trend\n")
    lines.append("### Cash Conversion Cycle\n")
    lines.append("| Period | DIO | DSO | DPO | CCC |")
    lines.append("|---|---|---|---|---|")
    for c in d["ccc_trend"]:
        lines.append(f"| {c['period_end']} | {c['dio']:.1f} | {c['dso']:.1f} | {c['dpo']:.1f} | {c['ccc']:.1f} |")
    lines.append("")

    lines.append("### Hedging — Full History\n")
    lines.append("| Period | Ccy | Unhedged | Forward | Collar | Status |")
    lines.append("|---|---|---|---|---|---|")
    for row in d["hedging"]:
        lines.append(f"| {row['period_end']} | {row['currency_linked']} | "
                      f"{fmt_k(row['unhedged_pnl_try'])} | {fmt_k(row['forward_pnl_try'])} | "
                      f"{fmt_k(row['collar_pnl_try'])} | {row['status']} |")
    lines.append("")

    lines.append("### Financing Costs — Full History\n")
    lines.append("| Period | Baseline WC | Factoring Saving | LC Cost | SCF Cost |")
    lines.append("|---|---|---|---|---|")
    for f in d["financing_trend"]:
        lines.append(f"| {f['period_end']} | {fmt_k(f['baseline_wc_financing_cost_try'])} | "
                      f"{fmt_k(f['factoring_vs_baseline_ar_saving_try'])} | "
                      f"{fmt_k(f['lc_ap_cost_try'])} | {fmt_k(f['scf_ap_cost_try'])} |")

    return "\n".join(lines)


def render_html(d):
    def rows_ccc(trend):
        return "".join(
            f"<tr><td>{c['period_end']}</td><td>{c['dio']:.1f}</td><td>{c['dso']:.1f}</td>"
            f"<td>{c['dpo']:.1f}</td><td>{c['ccc']:.1f}</td></tr>" for c in trend
        )

    def rows_hedging(hedging):
        return "".join(
            f"<tr><td>{r['period_end']}</td><td>{r['currency_linked']}</td>"
            f"<td>{fmt_k(r['unhedged_pnl_try'])}</td><td>{fmt_k(r['forward_pnl_try'])}</td>"
            f"<td>{fmt_k(r['collar_pnl_try'])}</td><td>{r['status']}</td></tr>" for r in hedging
        )

    def rows_financing(trend):
        return "".join(
            f"<tr><td>{f['period_end']}</td><td>{fmt_k(f['baseline_wc_financing_cost_try'])}</td>"
            f"<td>{fmt_k(f['factoring_vs_baseline_ar_saving_try'])}</td>"
            f"<td>{fmt_k(f['lc_ap_cost_try'])}</td><td>{fmt_k(f['scf_ap_cost_try'])}</td></tr>"
            for f in trend
        )

    fx_html = "".join(
        f"<li>{r['currency_linked']} ({r['direction']}): {fmt_k(r['balance_try'])}</li>"
        for r in d["fx_latest"]
    )

    latest_block = ""
    if d["latest_ccc"]:
        c = d["latest_ccc"]
        latest_block = (
            f"<p><b>Period:</b> {c['period_end']} (FY{c['fiscal_year']} Q{c['fiscal_quarter']})</p>"
            f"<p><b>Cash Conversion Cycle:</b> {c['ccc']:.1f} days "
            f"(DIO {c['dio']:.1f} + DSO {c['dso']:.1f} − DPO {c['dpo']:.1f})</p>"
        )

    financing_block = ""
    if d["latest_financing"]:
        f = d["latest_financing"]
        financing_block = (
            f"<p>Baseline working-capital cost: {fmt_k(f['baseline_wc_financing_cost_try'])}</p>"
            f"<p>Factoring vs. baseline (AR): {fmt_k(f['factoring_vs_baseline_ar_saving_try'])} "
            f"(negative = factoring costs more)</p>"
            f"<p>LC cost: {fmt_k(f['lc_ap_cost_try'])} | SCF cost: {fmt_k(f['scf_ap_cost_try'])} "
            f"<i>(not directly comparable — see note)</i></p>"
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Mavi Treasury Report — {d['latest_period']}</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; max-width: 900px; margin: 40px auto; color: #1a1a1a; }}
  h1 {{ font-size: 1.6em; border-bottom: 2px solid #1a1a4a; padding-bottom: 8px; }}
  h2 {{ font-size: 1.2em; color: #1a1a4a; margin-top: 32px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.9em; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: right; }}
  th {{ background: #1a1a4a; color: white; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .meta {{ color: #666; font-size: 0.85em; }}
  .headline {{ background: #f5f5fa; padding: 16px; border-radius: 8px; }}
</style></head>
<body>
<h1>Mavi Giyim (BIST: MAVI) — Treasury Report</h1>
<p class="meta">Generated {d['generated_at']} | Data through {d['latest_period']}</p>

<h2>Headline — Latest Quarter</h2>
<div class="headline">
{latest_block}
<p><b>FX Exposure (balance sheet):</b></p>
<ul>{fx_html}</ul>
{financing_block}
</div>

<h2>Hedging Performance (recent, k=0.75 collar)</h2>
<table><tr><th>Period</th><th>Ccy</th><th>Unhedged</th><th>Forward</th><th>Collar</th><th>Status</th></tr>
{rows_hedging(d['hedging'][-4:])}</table>

<h2>Appendix — Full Trend</h2>
<h3>Cash Conversion Cycle</h3>
<table><tr><th>Period</th><th>DIO</th><th>DSO</th><th>DPO</th><th>CCC</th></tr>
{rows_ccc(d['ccc_trend'])}</table>

<h3>Hedging — Full History</h3>
<table><tr><th>Period</th><th>Ccy</th><th>Unhedged</th><th>Forward</th><th>Collar</th><th>Status</th></tr>
{rows_hedging(d['hedging'])}</table>

<h3>Financing Costs — Full History</h3>
<table><tr><th>Period</th><th>Baseline WC</th><th>Factoring Saving</th><th>LC Cost</th><th>SCF Cost</th></tr>
{rows_financing(d['financing_trend'])}</table>

</body></html>"""


def main():
    d = build_report_data()
    if d["latest_period"] is None:
        print("No data found — check that financial_ratios has rows.")
        return

    md = render_markdown(d)
    html = render_html(d)

    md_path = f"reports/{d['latest_period']}_treasury_report.md"
    html_path = f"reports/{d['latest_period']}_treasury_report.html"

    with open(md_path, "w") as f:
        f.write(md)
    with open(html_path, "w") as f:
        f.write(html)

    print(f"Written: {md_path}")
    print(f"Written: {html_path}")


if __name__ == "__main__":
    main()
