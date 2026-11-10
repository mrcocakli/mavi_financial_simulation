"""
Treasury simulator — Excel workbook builder.

Reads the baseline quarters from the SQLite database and writes
reports/mavi_treasury_simulator.xlsx. Every number on the Engine, Sensitivity
and Dashboard tabs is a live Excel formula that traces back to the Inputs and
Data tabs; nothing downstream of Data is hardcoded by Python.

Colour convention (standard financial-model practice):
    blue text   = hardcoded input (sourced figure or scenario lever)
    black text  = formula on the same sheet
    green text  = link to another sheet
    yellow fill = cell you are meant to change

Usage:
    python etl/build_simulator_xlsx.py
Then open the file in Excel and save once (or run a LibreOffice recalc) so the
cached formula values populate.
"""
import sys
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulator_engine import DEFAULT_ASSUMPTIONS, DRIVERS, PRESETS, load_baselines  # noqa: E402

DB_PATH = "db/mavi_treasury.db"
OUT_PATH = "reports/mavi_treasury_simulator.xlsx"

F = "Arial"
BLUE = Font(name=F, size=10, color="0000FF")
BLACK = Font(name=F, size=10)
GREEN = Font(name=F, size=10, color="008000")
BOLD = Font(name=F, size=10, bold=True)
TITLE = Font(name=F, size=14, bold=True)
NOTE = Font(name=F, size=9, italic=True, color="666666")
HEAD = Font(name=F, size=10, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="1A1A4A")
SECTION_FILL = PatternFill("solid", fgColor="E8EAF2")
YELLOW = PatternFill("solid", fgColor="FFFF00")
THIN = Side(style="thin", color="BBBBBB")
TOP = Border(top=THIN)

TRY = '#,##0;(#,##0);"-"'
PCT = '0.0%;(0.0%);"-"'
DAYS = '0.0;(0.0);"-"'
RATE4 = "0.0000"
INT = '#,##0;(#,##0);"-"'

SCEN_COLS = ["C", "D", "E", "F", "G", "H"]          # five presets + Custom
SCEN_NAMES = [n for n, _ in PRESETS] + ["Custom"]
CUSTOM = dict(growth=0.05, usd_shock=0.10, eur_shock=0.10, d_dso=5.0, d_dpo=-5.0,
              inv_build=0.10, hedge_ratio=0.75, rate_bps=250.0)


def put(ws, ref, value, font=BLACK, fmt=None, fill=None, bold=False, align=None):
    c = ws[ref]
    c.value = value
    c.font = Font(name=F, size=font.size, color=font.color, italic=font.italic,
                  bold=True) if bold else font
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if align:
        c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
    return c


def header(ws, row, labels, start_col=2):
    for i, lab in enumerate(labels):
        c = ws.cell(row=row, column=start_col + i, value=lab)
        c.font, c.fill = HEAD, HEAD_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def section(ws, row, text, last_col="I"):
    for col in range(2, ws[f"{last_col}1"].column + 1):
        ws.cell(row=row, column=col).fill = SECTION_FILL
    put(ws, f"B{row}", text, BOLD, fill=SECTION_FILL)


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


# --------------------------------------------------------------------------
def build_data(wb, baselines, asof):
    ws = wb.create_sheet("Data")
    put(ws, "B1", "Data — sourced baseline inputs (one row per quarter)", TITLE)
    put(ws, "B2", f"Loaded from db/mavi_treasury.db on {datetime.now():%Y-%m-%d}. "
                  f"EVDS FX series run to {asof}. Amounts in TRY thousand unless stated. "
                  "Blue = hardcoded figure from the source named in column Q.", NOTE)
    cols = ["Period end", "Quarter label", "Revenue (standalone qtr)", "COGS (standalone qtr)",
            "Inventory", "Trade receivables", "Trade payables", "TRY commercial loan rate",
            "Factoring rate", "Net USD position (USD k)", "Net EUR position (EUR k)",
            "USD/TRY spot at qtr end", "EUR/TRY spot at qtr end", "TRY 3M deposit rate",
            "USD 3M deposit rate", "EUR 3M deposit rate", "Filing (KAP / Mavi IR)"]
    header(ws, 4, cols, start_col=1)
    ws.row_dimensions[4].height = 42
    for i, b in enumerate(baselines):
        r = 5 + i
        vals = [date.fromisoformat(b["period_end"]), b["label"], b["revenue"], b["cogs"],
                b["inventory"], b["ar"], b["ap"], b["loan_rate"], b["factoring_rate"],
                b["usd_native"], b["eur_native"], b["usd_spot"], b["eur_spot"],
                b["try_rate"], b["usd_rate"], b["eur_rate"], b["source_url"]]
        fmts = ["yyyy-mm-dd", None, TRY, TRY, TRY, TRY, TRY, "0.00%", "0.00%", INT, INT,
                RATE4, RATE4, "0.00%", "0.00%", "0.00%", None]
        for j, (v, f) in enumerate(zip(vals, fmts)):
            c = ws.cell(row=r, column=1 + j, value=v)
            c.font = BLUE
            if f:
                c.number_format = f
    last = 4 + len(baselines)
    n = last + 2
    notes = [
        "Sources and method",
        "Revenue, COGS, inventory, receivables, payables: Mavi consolidated financial statements filed on KAP "
        "(link in column Q). Q4 revenue/COGS are full-year less nine-month cumulative, per etl/calculate_ratios.py.",
        "Loan and factoring rates: TCMB EVDS series TP.BKR.TRY.1 and TP.FKF.TRY.1, month of quarter end "
        "(etl/calculate_financing_scenarios.py).",
        "Net FX positions: Mavi FX-sensitivity note, native currency, converted at EVDS selling rate on the "
        "quarter-end date (etl/calculate_hedging_backtest.py).",
        "Deposit rates: TCMB EVDS TP.MT210AGS.{TRY,USD,EUR}.MT02 (3-month deposit rates) — used only as the "
        "covered-interest-parity proxy for a forward rate. No free TRY forward quotes exist; this is a disclosed proxy.",
    ]
    for k, t in enumerate(notes):
        put(ws, f"A{n + k}", t, BOLD if k == 0 else NOTE)
    widths(ws, {"A": 12, "B": 26, **{get_column_letter(c): 15 for c in range(3, 17)}, "Q": 60})
    ws.freeze_panes = "C5"
    return last


def build_inputs(wb, last):
    ws = wb.create_sheet("Inputs")
    rng = lambda col: f"Data!${col}$5:${col}${last}"
    put(ws, "B1", "Inputs — baseline quarter, assumptions and scenario levers", TITLE)
    put(ws, "B2", "Change yellow cells only. Everything else on this tab is a link to Data.", NOTE)

    section(ws, 4, "1. Baseline quarter")
    put(ws, "B5", "Baseline quarter (pick from list)", BOLD)
    put(ws, "C5", f"=INDEX({rng('B')},ROWS({rng('B')}))", GREEN, fill=YELLOW)
    put(ws, "D5", "Defaults to the latest quarter in Data. Overwrite with the dropdown to rebase.", NOTE)
    dv = DataValidation(type="list", formula1=f"={rng('B')}", allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("C5")

    look = lambda col: f"=INDEX({rng(col)},MATCH($C$5,{rng('B')},0))"
    base_rows = [
        (7, "Period end", look("A"), "yyyy-mm-dd", GREEN, "Data"),
        (8, "Days in quarter", "=C7-EOMONTH(C7,-3)", "0", BLACK, "Actual calendar days: period end less the month end three months earlier"),
        (9, "Revenue", look("C"), TRY, GREEN, "TRY thousand, standalone quarter"),
        (10, "COGS", look("D"), TRY, GREEN, "TRY thousand, standalone quarter"),
        (11, "Inventory", look("E"), TRY, GREEN, "TRY thousand, quarter end"),
        (12, "Trade receivables", look("F"), TRY, GREEN, "TRY thousand, quarter end"),
        (13, "Trade payables", look("G"), TRY, GREEN, "TRY thousand, quarter end"),
        (14, "TRY commercial loan rate", look("H"), "0.00%", GREEN, "EVDS TP.BKR.TRY.1, annual"),
        (15, "Net USD monetary position", look("J"), INT, GREEN, "USD thousand; positive = long USD"),
        (16, "Net EUR monetary position", look("K"), INT, GREEN, "EUR thousand; negative = short EUR"),
        (17, "USD/TRY spot (S0)", look("L"), RATE4, GREEN, "EVDS selling rate at quarter end"),
        (18, "EUR/TRY spot (S0)", look("M"), RATE4, GREEN, "EVDS selling rate at quarter end"),
        (19, "TRY 3M deposit rate", look("N"), "0.00%", GREEN, "CIRP input"),
        (20, "USD 3M deposit rate", look("O"), "0.00%", GREEN, "CIRP input"),
        (21, "EUR 3M deposit rate", look("P"), "0.00%", GREEN, "CIRP input"),
    ]
    for r, lab, f, fmt, font, note in base_rows:
        put(ws, f"B{r}", lab)
        put(ws, f"C{r}", f, font, fmt)
        put(ws, f"D{r}", note, NOTE)

    section(ws, 23, "2. Model assumptions (apply to every scenario)")
    put(ws, "B24", "FX-linked share of COGS")
    put(ws, "C24", DEFAULT_ASSUMPTIONS["fx_cogs_share"], BLUE, "0.0%", YELLOW)
    put(ws, "D24", "ILLUSTRATIVE ASSUMPTION — Mavi does not disclose this. Share of COGS that reprices "
                   "one-for-one with USD/TRY. Set to 0% to switch the cost channel off.", NOTE)
    put(ws, "B25", "Hedge horizon (days)")
    put(ws, "C25", DEFAULT_ASSUMPTIONS["horizon_days"], BLUE, "0", YELLOW)
    put(ws, "D25", "Tenor of the forward and the period over which the FX shock plays out. "
                   "90 days matches the quarterly backtest.", NOTE)
    put(ws, "B26", "Day-count basis")
    put(ws, "C26", 365, BLUE, "0")
    put(ws, "D26", "Actual/365, same as etl/calculate_hedging_backtest.py and calculate_financing_scenarios.py.", NOTE)

    section(ws, 28, "3. Scenario levers")
    header(ws, 29, ["Lever"] + SCEN_NAMES + ["How to read it"])
    lever_meta = [
        ("Sales volume growth", "0.0%", "vs baseline quarter; scales revenue and COGS"),
        ("USD/TRY shock", "0.0%", "+ = TRY weakens. Moves USD position P&L and FX-linked COGS"),
        ("EUR/TRY shock", "0.0%", "+ = TRY weakens. Moves EUR position P&L"),
        ("Change in DSO (days)", "0", "+ = customers pay later (cash out)"),
        ("Change in DPO (days)", "0", "- = suppliers paid sooner (cash out)"),
        ("Inventory build", "0.0%", "extra days of stock held, as % of baseline DIO"),
        ("Hedge ratio (forward)", "0%", "share of each net FX position locked at the CIRP forward"),
        ("Loan rate shock (bps)", "0", "added to the TRY commercial loan rate"),
    ]
    scen_vals = [s for _, s in PRESETS] + [CUSTOM]
    for i, (drv, (lab, fmt, note)) in enumerate(zip(DRIVERS, lever_meta)):
        r = 30 + i
        put(ws, f"B{r}", lab)
        for col, sv, name in zip(SCEN_COLS, scen_vals, SCEN_NAMES):
            fill = YELLOW if name == "Custom" else None
            put(ws, f"{col}{r}", sv[drv], BLUE, fmt, fill)
        put(ws, f"I{r}", note, NOTE)
    put(ws, "B39", "Base column must stay at zero — the Dashboard measures every scenario against it. "
                   "Preset columns can be edited; the Custom column is yours.", NOTE)
    widths(ws, {"A": 2, "B": 30, "C": 24, "D": 17, "E": 17, "F": 17, "G": 17, "H": 17, "I": 58})
    ws.freeze_panes = "C4"


def build_engine(wb):
    ws = wb.create_sheet("Engine")
    put(ws, "B1", "Engine — one column per scenario, identical formulas across columns", TITLE)
    put(ws, "B2", "TRY thousand, one quarter. Green = link to Inputs. No hardcoded numbers on this tab.", NOTE)
    header(ws, 4, ["Line"] + [f"=Inputs!{c}29" for c in SCEN_COLS] + ["Formula in words"])

    I = "Inputs!"
    DAYS_, DC = f"{I}$C$8", f"{I}$C$26"
    REV, COGS, INV, AR, AP = (f"{I}$C${r}" for r in (9, 10, 11, 12, 13))
    LOAN, NUSD, NEUR, SUSD, SEUR, ITRY, IUSD, IEUR = (f"{I}$C${r}" for r in range(14, 22))
    PHI, N = f"{I}$C$24", f"{I}$C$25"
    NWC0 = f"({INV}+{AR}-{AP})"

    rows = {}

    def line(r, key, label, formula, fmt, note="", font=BLACK, bold=False):
        rows[key] = r
        put(ws, f"B{r}", label, BOLD if bold else BLACK)
        for c in SCEN_COLS:
            cell = put(ws, f"{c}{r}", formula.replace("{c}", c), font, fmt, bold=bold)
            if bold:
                cell.border = TOP
        put(ws, f"I{r}", note, NOTE)

    section(ws, 5, "Levers (linked from Inputs)")
    lever_fmt = ["0.0%", "0.0%", "0.0%", "0", "0", "0.0%", "0%", "0"]
    lever_lab = ["Sales volume growth", "USD/TRY shock", "EUR/TRY shock", "Change in DSO (days)",
                 "Change in DPO (days)", "Inventory build", "Hedge ratio", "Loan rate shock (bps)"]
    for i, (k, lab, fmt) in enumerate(zip(DRIVERS, lever_lab, lever_fmt)):
        line(6 + i, k, lab, f"=Inputs!{{c}}{30 + i}", fmt, font=GREEN)
    g, su, se, dds, ddp, ib, h, bps = (f"{{c}}{6 + i}" for i in range(8))

    section(ws, 15, "Quarter P&L")
    line(16, "revenue", "Revenue", f"={REV}*(1+{g})", TRY, "Baseline revenue x (1 + growth)", GREEN)
    line(17, "cogs", "COGS", f"={COGS}*(1+{g})*(1+{PHI}*{su})", TRY,
         "Baseline COGS x (1 + growth) x (1 + FX-linked share x USD/TRY shock)", GREEN)
    line(18, "gp", "Gross profit", "={c}16-{c}17", TRY, "Revenue - COGS", bold=True)
    line(19, "gm", "Gross margin", "=IF({c}16=0,0,{c}18/{c}16)", "0.0%", "Gross profit / revenue")

    section(ws, 21, "Cash conversion cycle (days)")
    line(22, "dio", "DIO", f"={INV}/{COGS}*{DAYS_}*(1+{ib})", DAYS, "Baseline DIO x (1 + inventory build)", GREEN)
    line(23, "dso", "DSO", f"={AR}/{REV}*{DAYS_}+{dds}", DAYS, "Baseline DSO + change in DSO", GREEN)
    line(24, "dpo", "DPO", f"={AP}/{COGS}*{DAYS_}+{ddp}", DAYS, "Baseline DPO + change in DPO", GREEN)
    line(25, "ccc", "Cash conversion cycle", "={c}22+{c}23-{c}24", DAYS, "DIO + DSO - DPO", bold=True)

    section(ws, 27, "Trade working capital")
    line(28, "inv", "Inventory", f"={{c}}17/{DAYS_}*{{c}}22", TRY, "Scenario COGS per day x DIO", GREEN)
    line(29, "ar", "Trade receivables", f"={{c}}16/{DAYS_}*{{c}}23", TRY, "Scenario revenue per day x DSO", GREEN)
    line(30, "ap", "Trade payables", f"={{c}}17/{DAYS_}*{{c}}24", TRY, "Scenario COGS per day x DPO", GREEN)
    line(31, "nwc", "Net trade working capital", "={c}28+{c}29-{c}30", TRY, "Inventory + receivables - payables", bold=True)
    line(32, "dnwc", "Change vs baseline quarter", f"={{c}}31-{NWC0}", TRY, "Scenario NWC - reported NWC", GREEN)
    line(33, "cash", "Cash impact", "=-{c}32", TRY, "Minus the change in NWC: negative = cash absorbed", bold=True)

    section(ws, 35, "Cost of funding working capital")
    line(36, "rate", "TRY loan rate", f"={LOAN}+{bps}/10000", "0.00%", "Baseline loan rate + shock", GREEN)
    line(37, "fund", "Funding cost for the quarter", f"={{c}}31*{{c}}36*{DAYS_}/{DC}", TRY,
         "NWC x loan rate x days / 365", GREEN)
    line(38, "dfund", "Change vs baseline quarter", f"={{c}}37-{NWC0}*{LOAN}*{DAYS_}/{DC}", TRY,
         "Scenario funding cost - baseline funding cost", GREEN)

    section(ws, 40, "FX on net monetary position")
    line(41, "usd_s1", "USD/TRY at horizon (S1)", f"={SUSD}*(1+{su})", RATE4, "S0 x (1 + shock)", GREEN)
    line(42, "eur_s1", "EUR/TRY at horizon (S1)", f"={SEUR}*(1+{se})", RATE4, "S0 x (1 + shock)", GREEN)
    line(43, "usd_f", "USD/TRY forward (F)", f"={SUSD}*(1+{ITRY}*{N}/{DC})/(1+{IUSD}*{N}/{DC})", RATE4,
         "Covered interest parity: S0 x (1 + i_TRY x n/365) / (1 + i_USD x n/365)", GREEN)
    line(44, "eur_f", "EUR/TRY forward (F)", f"={SEUR}*(1+{ITRY}*{N}/{DC})/(1+{IEUR}*{N}/{DC})", RATE4,
         "Same, with the EUR deposit rate", GREEN)
    line(45, "usd_un", "USD position P&L if unhedged", f"={NUSD}*({{c}}41-{SUSD})", TRY, "Position x (S1 - S0)", GREEN)
    line(46, "eur_un", "EUR position P&L if unhedged", f"={NEUR}*({{c}}42-{SEUR})", TRY, "Position x (S1 - S0)", GREEN)
    line(47, "usd_pnl", "USD position P&L at hedge ratio", f"=(1-{h})*{{c}}45+{h}*{NUSD}*({{c}}43-{SUSD})", TRY,
         "(1 - h) x unhedged + h x position x (F - S0)", GREEN)
    line(48, "eur_pnl", "EUR position P&L at hedge ratio", f"=(1-{h})*{{c}}46+{h}*{NEUR}*({{c}}44-{SEUR})", TRY,
         "(1 - h) x unhedged + h x position x (F - S0)", GREEN)
    line(49, "fx_pnl", "FX P&L, total", "={c}47+{c}48", TRY, "USD + EUR", bold=True)
    line(50, "fx_un", "Memo: FX P&L if fully unhedged", "={c}45+{c}46", TRY, "For comparison with the row above")

    section(ws, 52, "Scenario summary")
    line(53, "dgp", "Change in gross profit", f"={{c}}18-({REV}-{COGS})", TRY, "Scenario - baseline gross profit", GREEN)
    line(54, "s_fx", "FX P&L", "={c}49", TRY, "From the FX block")
    line(55, "s_fund", "Extra funding cost", "=-{c}38", TRY, "Minus the change in funding cost")
    line(56, "pnl", "Quarter P&L impact", "={c}53+{c}54+{c}55", TRY, "Sum of the three lines above", bold=True)
    line(57, "s_cash", "Cash impact", "={c}33", TRY, "From the working-capital block", bold=True)

    widths(ws, {"A": 2, "B": 34, **{c: 17 for c in SCEN_COLS}, "I": 66})
    ws.freeze_panes = "C5"
    return rows


def build_sensitivity(wb, R):
    ws = wb.create_sheet("Sensitivity")
    put(ws, "B1", "Sensitivity grids — every cell is a formula on Inputs / Engine", TITLE)
    put(ws, "B2", "TRY thousand. Blue axis values can be overwritten. Each grid moves two levers and holds "
                  "the rest at baseline.", NOTE)
    I = "Inputs!"
    D, REV, COGS, INV, AR, AP = (f"{I}$C${r}" for r in (8, 9, 10, 11, 12, 13))
    NUSD, NEUR, SUSD, SEUR = (f"{I}$C${r}" for r in (15, 16, 17, 18))
    PHI = f"{I}$C$24"
    FUSD, FEUR = f"Engine!$C${R['usd_f']}", f"Engine!$C${R['eur_f']}"

    def grid(top, title, row_lab, col_lab, row_vals, col_vals, rfmt, cfmt, formula, note):
        section(ws, top, title, last_col="I")
        put(ws, f"B{top + 1}", note, NOTE)
        put(ws, f"B{top + 2}", f"{row_lab}  \\  {col_lab}", BOLD, align="center")
        ws[f"B{top + 2}"].fill = HEAD_FILL
        ws[f"B{top + 2}"].font = HEAD
        for j, v in enumerate(col_vals):
            c = put(ws, f"{get_column_letter(3 + j)}{top + 2}", v, BLUE, cfmt, align="center")
            c.fill = SECTION_FILL
        for i, v in enumerate(row_vals):
            r = top + 3 + i
            c = put(ws, f"B{r}", v, BLUE, rfmt, align="center")
            c.fill = SECTION_FILL
            for j in range(len(col_vals)):
                col = get_column_letter(3 + j)
                f = formula.replace("{row}", f"$B{r}").replace("{col}", f"{col}${top + 2}")
                put(ws, f"{col}{r}", f, GREEN, TRY)
        return top + 3 + len(row_vals) + 1

    nxt = grid(4, "A. FX P&L on the net monetary position", "USD/TRY and EUR/TRY shock", "Hedge ratio",
               [-0.10, -0.05, 0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40], [0, 0.25, 0.5, 0.75, 1.0],
               "0%", "0%",
               f"=(1-{{col}})*({NUSD}*{SUSD}+{NEUR}*{SEUR})*{{row}}"
               f"+{{col}}*({NUSD}*({FUSD}-{SUSD})+{NEUR}*({FEUR}-{SEUR}))",
               "Same shock applied to both currencies. At 100% hedged the result is the forward carry and no "
               "longer depends on the shock.")
    nxt = grid(nxt, "B. Cash impact of payment terms", "Change in DSO (days)", "Change in DPO (days)",
               [-10, -5, 0, 5, 10, 15, 20, 30], [-30, -20, -10, 0, 10, 20],
               "0", "0",
               f"=-({REV}/{D}*{{row}}-{COGS}/{D}*{{col}})",
               "Minus (revenue per day x change in DSO - COGS per day x change in DPO). Negative = cash absorbed.")
    grid(nxt, "C. Cash impact of an inventory build under a USD/TRY shock", "Inventory build",
         "USD/TRY shock",
         [0, 0.10, 0.20, 0.30, 0.40, 0.50], [0, 0.10, 0.20, 0.30, 0.40],
         "0%", "0%",
         f"=-(({COGS}*(1+{PHI}*{{col}})/{D})*(({INV}/{COGS}*{D})*(1+{{row}})-{AP}/{COGS}*{D})+{AR}"
         f"-({INV}+{AR}-{AP}))",
         "Scenario COGS per day x (DIO x (1 + build) - DPO) + receivables, less reported NWC. "
         "Uses the FX-linked COGS share on Inputs.")
    widths(ws, {"A": 2, "B": 44, **{get_column_letter(c): 15 for c in range(3, 10)}})


def build_dashboard(wb, R):
    ws = wb.create_sheet("Dashboard", 0)
    put(ws, "B1", "Mavi Giyim — Treasury Simulator", TITLE)
    put(ws, "B2", "Scenario analysis on reported working capital and FX position. "
                  "Simulation on public data; not a forecast and not company guidance.", NOTE)
    put(ws, "B4", "Scenario to display", BOLD)
    put(ws, "C4", "Combined stress", BLUE, fill=YELLOW)
    dv = DataValidation(type="list", formula1="=Inputs!$C$29:$H$29", allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("C4")
    put(ws, "D4", "=MATCH(C4,Inputs!$C$29:$H$29,0)", GREEN, "0")
    put(ws, "E4", "<- column index of the chosen scenario (helper)", NOTE)
    put(ws, "B5", "Baseline quarter", BOLD)
    put(ws, "C5", "=Inputs!C5", GREEN)
    put(ws, "D5", "Change it on the Inputs tab", NOTE)

    header(ws, 7, ["Metric", "Baseline", "Scenario", "Change", "Unit"])
    pick = lambda key: f"=INDEX(Engine!$C${R[key]}:$H${R[key]},$D$4)"
    base = lambda key: f"=Engine!$C${R[key]}"
    kpis = [
        ("Cash conversion cycle", "ccc", DAYS, "days"),
        ("DIO", "dio", DAYS, "days"),
        ("DSO", "dso", DAYS, "days"),
        ("DPO", "dpo", DAYS, "days"),
        ("Net trade working capital", "nwc", TRY, "TRY k"),
        ("Funding cost for the quarter", "fund", TRY, "TRY k"),
        ("Gross profit", "gp", TRY, "TRY k"),
        ("FX P&L on monetary position", "fx_pnl", TRY, "TRY k"),
    ]
    for i, (lab, key, fmt, unit) in enumerate(kpis):
        r = 8 + i
        put(ws, f"B{r}", lab)
        put(ws, f"C{r}", base(key), GREEN, fmt)
        put(ws, f"D{r}", pick(key), GREEN, fmt)
        put(ws, f"E{r}", f"=D{r}-C{r}", BLACK, fmt)
        put(ws, f"F{r}", unit, NOTE)
    put(ws, "B17", "Cash impact (minus change in NWC)", BOLD)
    put(ws, "D17", pick("cash"), GREEN, TRY, bold=True)
    put(ws, "F17", "TRY k", NOTE)
    put(ws, "B18", "Quarter P&L impact", BOLD)
    put(ws, "D18", pick("pnl"), GREEN, TRY, bold=True)
    put(ws, "F18", "TRY k  = change in gross profit + FX P&L - extra funding cost", NOTE)

    header(ws, 21, ["All scenarios"] + SCEN_NAMES)
    comp = [("Cash conversion cycle (days)", "ccc", DAYS), ("Cash impact (TRY k)", "cash", TRY),
            ("FX P&L (TRY k)", "fx_pnl", TRY), ("Quarter P&L impact (TRY k)", "pnl", TRY)]
    for i, (lab, key, fmt) in enumerate(comp):
        r = 22 + i
        put(ws, f"B{r}", lab)
        for c in SCEN_COLS:
            put(ws, f"{c}{r}", f"=Engine!{c}{R[key]}", GREEN, fmt)

    ch = BarChart()
    ch.type, ch.style = "col", 10
    ch.title = "Cash impact and quarter P&L impact by scenario (TRY thousand)"
    ch.add_data(Reference(ws, min_col=2, max_col=8, min_row=23), from_rows=True, titles_from_data=True)
    ch.add_data(Reference(ws, min_col=2, max_col=8, min_row=25), from_rows=True, titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=3, max_col=8, min_row=21))
    ch.height, ch.width = 8.5, 24
    ws.add_chart(ch, "B28")
    widths(ws, {"A": 2, "B": 36, "C": 24, "D": 20, "E": 18, "F": 18, "G": 18, "H": 18})


def build_about(wb, asof):
    ws = wb.create_sheet("About")
    put(ws, "B1", "About this model", TITLE)
    lines = [
        ("What it is", "A scenario simulator for Mavi Giyim's (BIST: MAVI) trade working capital and FX "
                       "position: FX shocks, payment-term changes, an inventory build, a forward hedge ratio "
                       "and a loan-rate shock, measured against a reported quarter."),
        ("How to use", "1) Dashboard: pick a scenario in C4.  2) Inputs: change the yellow Custom column, the "
                       "baseline quarter or the two assumptions.  3) Engine: read any number back to its "
                       "formula; column I states each formula in words."),
        ("Colours", "Blue text = hardcoded input.  Black = formula on the same tab.  Green = link to another "
                    "tab.  Yellow fill = cells meant to be changed."),
        ("Units", "TRY thousand, one fiscal quarter, unless a column says otherwise."),
        ("Data", f"Financials from Mavi's KAP filings; rates and FX from TCMB EVDS (FX series to {asof}). "
                 "Row-level sources are on the Data tab."),
        ("Limit 1", "FX-linked share of COGS is an illustrative assumption. Mavi does not disclose it."),
        ("Limit 2", "Forward rates are a covered-interest-parity proxy from EVDS deposit rates, not dealer quotes."),
        ("Limit 3", "Inventory and payables reprice fully and immediately with COGS; in practice FIFO layers "
                    "and contract terms delay this."),
        ("Limit 4", "Working-capital balances are quarter-end points, not averages; Mavi's business is seasonal."),
        ("Limit 5", "The FX block covers the disclosed net monetary position only, not forecast purchases or sales."),
        ("Built by", "etl/build_simulator_xlsx.py — regenerated by the pipeline whenever the database changes."),
    ]
    for i, (k, v) in enumerate(lines):
        put(ws, f"B{3 + i}", k, BOLD)
        c = put(ws, f"C{3 + i}", v, BLACK)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[3 + i].height = 30
    widths(ws, {"A": 2, "B": 14, "C": 120})


def main():
    baselines, asof = load_baselines(DB_PATH)
    if not baselines:
        sys.exit("No quarter has financials + FX position + rates loaded; run the pipeline first.")
    wb = Workbook()
    wb.remove(wb.active)
    last = build_data(wb, baselines, asof)
    build_inputs(wb, last)
    rows = build_engine(wb)
    build_sensitivity(wb, rows)
    build_dashboard(wb, rows)
    build_about(wb, asof)
    wb._sheets = [wb[n] for n in ("Dashboard", "Inputs", "Engine", "Sensitivity", "Data", "About")]
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
    Path(OUT_PATH).parent.mkdir(exist_ok=True)
    wb.save(OUT_PATH)
    print(f"Wrote {OUT_PATH}: {len(baselines)} baseline quarter(s), latest {baselines[-1]['label']}.")


if __name__ == "__main__":
    main()
