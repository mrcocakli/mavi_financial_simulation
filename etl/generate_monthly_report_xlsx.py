"""
Step 6 — Monthly treasury report, Excel version.
Same data sources as generate_monthly_report.py (financial_ratios,
fx_exposure_items, hedging_backtest_results, options_collar_results,
financing_scenario_results). Produces a formatted, multi-tab workbook.
"""

import sqlite3
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

DB_PATH = "db/mavi_treasury.db"
COMPANY_ID = 1
COLLAR_K = 0.75

HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=10)
HEADER_FILL = PatternFill("solid", fgColor="1A1A4A")
BODY_FONT = Font(name="Arial", size=10)
TITLE_FONT = Font(name="Arial", bold=True, size=14)
NOTE_FONT = Font(name="Arial", italic=True, size=9, color="666666")
TRY_FMT = "#,##0;(#,##0);-"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def style_header_row(ws, row, ncols):
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")


def autosize(ws):
    for col_cells in ws.columns:
        length = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
        ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max(length + 2, 10), 40)


def build_headline_sheet(wb, cur):
    ws = wb.active
    ws.title = "Headline"

    cur.execute(
        """SELECT period_end, fiscal_year, fiscal_quarter, dio, dso, dpo, ccc
           FROM financial_ratios WHERE company_id=? ORDER BY period_end DESC LIMIT 1""",
        (COMPANY_ID,),
    )
    latest = cur.fetchone()

    ws["A1"] = "Mavi Giyim (BIST: MAVI) — Treasury Report"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Data through {latest['period_end']}"
    ws["A2"].font = NOTE_FONT

    if latest:
        ws["A4"] = "Period"
        ws["B4"] = latest["period_end"]
        ws["A5"] = "Fiscal Year / Quarter"
        ws["B5"] = f"FY{latest['fiscal_year']} Q{latest['fiscal_quarter']}"
        ws["A6"] = "DIO (days)"
        ws["B6"] = latest["dio"]
        ws["A7"] = "DSO (days)"
        ws["B7"] = latest["dso"]
        ws["A8"] = "DPO (days)"
        ws["B8"] = latest["dpo"]
        ws["A9"] = "Cash Conversion Cycle (days)"
        ws["B9"] = "=B6+B7-B8"  # real formula, not the stored ccc value
        for r in range(4, 10):
            ws.cell(row=r, column=1).font = Font(name="Arial", bold=True, size=10)
            ws.cell(row=r, column=2).font = BODY_FONT

    cur.execute(
        """SELECT currency_linked, direction, balance_try FROM fx_exposure_items
           WHERE company_id=? AND period_end=? AND exposure_type='balance_sheet'
           ORDER BY currency_linked""",
        (COMPANY_ID, latest["period_end"]),
    )
    fx_rows = cur.fetchall()

    ws["A11"] = "FX Exposure (balance sheet, latest quarter)"
    ws["A11"].font = Font(name="Arial", bold=True, size=11)
    ws["A12"] = "Currency"
    ws["B12"] = "Direction"
    ws["C12"] = "Balance (k TRY)"
    style_header_row(ws, 12, 3)
    r = 13
    for row in fx_rows:
        ws.cell(row=r, column=1, value=row["currency_linked"]).font = BODY_FONT
        ws.cell(row=r, column=2, value=row["direction"]).font = BODY_FONT
        c = ws.cell(row=r, column=3, value=row["balance_try"])
        c.font = BODY_FONT
        c.number_format = TRY_FMT
        r += 1
    r += 1

    cur.execute(
        """SELECT baseline_wc_financing_cost_try, factoring_vs_baseline_ar_saving_try,
                  lc_ap_cost_try, scf_ap_cost_try
           FROM financing_scenario_results WHERE company_id=? ORDER BY period_end DESC LIMIT 1""",
        (COMPANY_ID,),
    )
    fin = cur.fetchone()
    if fin:
        ws.cell(row=r, column=1, value="Financing Costs (latest quarter, k TRY)").font = Font(
            name="Arial", bold=True, size=11
        )
        r += 1
        labels = [
            ("Baseline working-capital cost", fin["baseline_wc_financing_cost_try"]),
            ("Factoring vs. baseline (AR) — negative means factoring costs more",
             fin["factoring_vs_baseline_ar_saving_try"]),
            ("LC cost", fin["lc_ap_cost_try"]),
            ("SCF cost (not directly comparable to LC — see Financing tab note)",
             fin["scf_ap_cost_try"]),
        ]
        for label, val in labels:
            ws.cell(row=r, column=1, value=label).font = BODY_FONT
            c = ws.cell(row=r, column=2, value=val)
            c.font = BODY_FONT
            c.number_format = TRY_FMT
            r += 1

    ws.column_dimensions["A"].width = 45
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 20


def build_ccc_sheet(wb, cur):
    ws = wb.create_sheet("CCC Trend")
    headers = ["Period", "Fiscal Year", "Fiscal Quarter", "DIO", "DSO", "DPO", "CCC"]
    for i, h in enumerate(headers, start=1):
        ws.cell(row=1, column=i, value=h)
    style_header_row(ws, 1, len(headers))

    cur.execute(
        """SELECT period_end, fiscal_year, fiscal_quarter, dio, dso, dpo
           FROM financial_ratios WHERE company_id=? ORDER BY period_end""",
        (COMPANY_ID,),
    )
    rows = cur.fetchall()
    for r, row in enumerate(rows, start=2):
        ws.cell(row=r, column=1, value=row["period_end"]).font = BODY_FONT
        ws.cell(row=r, column=2, value=row["fiscal_year"]).font = BODY_FONT
        ws.cell(row=r, column=3, value=row["fiscal_quarter"]).font = BODY_FONT
        ws.cell(row=r, column=4, value=row["dio"]).font = BODY_FONT
        ws.cell(row=r, column=5, value=row["dso"]).font = BODY_FONT
        ws.cell(row=r, column=6, value=row["dpo"]).font = BODY_FONT
        f = ws.cell(row=r, column=7, value=f"=D{r}+E{r}-F{r}")  # CCC computed live
        f.font = BODY_FONT

    ws.cell(row=1, column=8, value="Source: financial_ratios table, derived from KAP quarterly filings")
    ws.cell(row=1, column=8).font = NOTE_FONT
    autosize(ws)


def build_hedging_sheet(wb, cur):
    ws = wb.create_sheet("Hedging Backtest")
    headers = ["Period", "Currency", "Unhedged P&L (k TRY)", "Forward P&L (k TRY)",
               f"Collar P&L, k={COLLAR_K} (k TRY)", "Status"]
    for i, h in enumerate(headers, start=1):
        ws.cell(row=1, column=i, value=h)
    style_header_row(ws, 1, len(headers))

    cur.execute(
        """
        SELECT h.period_end, h.currency_linked, h.status, h.unhedged_pnl_try,
               h.pnl_forward_vs_unhedged_try, c.pnl_collar_vs_unhedged_try
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
    rows = cur.fetchall()

    for r, row in enumerate(rows, start=2):
        ws.cell(row=r, column=1, value=row["period_end"]).font = BODY_FONT
        ws.cell(row=r, column=2, value=row["currency_linked"]).font = BODY_FONT

        unhedged_col = 3
        uh_cell = ws.cell(row=r, column=unhedged_col, value=row["unhedged_pnl_try"])
        uh_cell.font = BODY_FONT
        uh_cell.number_format = TRY_FMT

        if row["pnl_forward_vs_unhedged_try"] is not None:
            fwd_cell = ws.cell(row=r, column=4, value=f"=C{r}+{row['pnl_forward_vs_unhedged_try']}")
        else:
            fwd_cell = ws.cell(row=r, column=4, value=None)
        fwd_cell.font = BODY_FONT
        fwd_cell.number_format = TRY_FMT

        if row["pnl_collar_vs_unhedged_try"] is not None:
            col_cell = ws.cell(row=r, column=5, value=f"=C{r}+{row['pnl_collar_vs_unhedged_try']}")
        else:
            col_cell = ws.cell(row=r, column=5, value=None)
        col_cell.font = BODY_FONT
        col_cell.number_format = TRY_FMT

        ws.cell(row=r, column=6, value=row["status"]).font = BODY_FONT

    note_row = len(rows) + 3
    ws.cell(row=note_row, column=1,
            value="Forward/Collar shown as Unhedged + delta (delta stored in DB, "
                  "recombined here as a live formula). Source: hedging_backtest_results, "
                  "options_collar_results.")
    ws.cell(row=note_row, column=1).font = NOTE_FONT
    autosize(ws)


def build_financing_sheet(wb, cur):
    ws = wb.create_sheet("Financing Costs")
    headers = ["Period", "Baseline WC Cost (k TRY)", "Factoring AR Cost (k TRY)",
               "Factoring vs Baseline Saving (k TRY)", "LC Cost (k TRY)", "SCF Cost (k TRY)"]
    for i, h in enumerate(headers, start=1):
        ws.cell(row=1, column=i, value=h)
    style_header_row(ws, 1, len(headers))

    cur.execute(
        """SELECT period_end, baseline_wc_financing_cost_try, factoring_ar_cost_try,
                  factoring_vs_baseline_ar_saving_try, lc_ap_cost_try, scf_ap_cost_try
           FROM financing_scenario_results WHERE company_id=? ORDER BY period_end""",
        (COMPANY_ID,),
    )
    rows = cur.fetchall()

    for r, row in enumerate(rows, start=2):
        ws.cell(row=r, column=1, value=row["period_end"]).font = BODY_FONT
        b = ws.cell(row=r, column=2, value=row["baseline_wc_financing_cost_try"])
        f = ws.cell(row=r, column=3, value=row["factoring_ar_cost_try"])
        s = ws.cell(row=r, column=4, value=row["factoring_vs_baseline_ar_saving_try"])  # pulled directly, not re-derived
        lc = ws.cell(row=r, column=5, value=row["lc_ap_cost_try"])
        scf = ws.cell(row=r, column=6, value=row["scf_ap_cost_try"])
        for c in (b, f, s, lc, scf):
            c.font = BODY_FONT
            c.number_format = TRY_FMT

    note_row = len(rows) + 3
    ws.cell(row=note_row, column=1,
            value="LC and SCF costs are NOT directly comparable: LC is a flat guarantee/service "
                  "fee on the AP balance; SCF assumes the full AP balance is actively financed at "
                  "the commercial loan rate. They serve different purposes (risk mitigation vs. "
                  "liquidity access). Source: financing_scenario_results, financing_rates_raw "
                  "(TCMB EVDS TP.BKR.TRY.1, TP.FKF.TRY.1; LC rate is a documented market-benchmark "
                  "assumption, ~6% annualized, not a live series).")
    ws.cell(row=note_row, column=1).font = NOTE_FONT
    ws.cell(row=note_row, column=1).alignment = Alignment(wrap_text=True)
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=6)
    ws.row_dimensions[note_row].height = 45
    autosize(ws)


def main():
    conn = get_conn()
    cur = conn.cursor()

    wb = Workbook()
    build_headline_sheet(wb, cur)
    build_ccc_sheet(wb, cur)
    build_hedging_sheet(wb, cur)
    build_financing_sheet(wb, cur)

    cur.execute(
        "SELECT MAX(period_end) FROM financial_ratios WHERE company_id=?", (COMPANY_ID,)
    )
    latest_period = cur.fetchone()[0]
    conn.close()

    out_path = f"reports/{latest_period}_treasury_report.xlsx"
    wb.save(out_path)
    print(f"Written: {out_path}")
    print("NOTE: open in Excel and let it recalculate once (Excel does this "
          "automatically on open) — formula cells will show blank/0 until then "
          "if previewed with a non-Excel tool.")


if __name__ == "__main__":
    main()
