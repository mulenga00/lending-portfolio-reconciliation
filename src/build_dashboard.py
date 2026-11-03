"""
Step 4a - Build excel/Lending_Portfolio_Dashboard.xlsx from the SQL result tables.
SQL output is written as inputs (blue); every ratio and KPI in the workbook is a live Excel formula.
"""
import pandas as pd
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.utils import get_column_letter as L

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / "reports" / "tables"
OUT = ROOT / "excel" / "Lending_Portfolio_Dashboard.xlsx"
OUT.parent.mkdir(exist_ok=True)

kpi = pd.read_csv(T / "kpi_grade.csv")
prof = pd.read_csv(T / "profitability_grade.csv")
vint = pd.read_csv(T / "vintage_curve.csv")
roll = pd.read_csv(T / "roll_rates.csv")
roll_g = pd.read_csv(T / "roll_current_to_30_by_grade.csv")
dq = pd.read_csv(T / "dq_log.csv")

# ---------------------------------------------------------------- styles
NAVY, TEAL, ORANGE, GREY, LIGHT = "1F3864", "2E75B6", "ED7D31", "7F7F7F", "EAF1FB"
F = "Arial"
f_base = Font(name=F, size=10)
f_in = Font(name=F, size=10, color="0000FF")                 # hard-coded inputs from SQL
f_hdr = Font(name=F, size=10, bold=True, color="FFFFFF")
f_bold = Font(name=F, size=10, bold=True)
f_title = Font(name=F, size=18, bold=True, color=NAVY)
f_sub = Font(name=F, size=9, italic=True, color=GREY)
fill_hdr = PatternFill("solid", fgColor=NAVY)
fill_tile = PatternFill("solid", fgColor=LIGHT)
fill_tot = PatternFill("solid", fgColor="D9E2F3")
thin = Side(style="thin", color="BFBFBF")
box = Border(top=thin, bottom=thin, left=thin, right=thin)
USD, PCT, PCT2, INT = '$#,##0;($#,##0);-', '0.0%;(0.0%);-', '0.00%', '#,##0;(#,##0);-'

def header(ws, row, labels, col0=1, height=32):
    for i, t in enumerate(labels):
        c = ws.cell(row=row, column=col0 + i, value=t)
        c.font, c.fill, c.border = f_hdr, fill_hdr, box
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = height

def put(ws, ref, value, fmt=None, font=f_base, fill=None, align=None, border=True):
    c = ws[ref]
    c.value, c.font = value, font
    if fmt: c.number_format = fmt
    if fill: c.fill = fill
    if align: c.alignment = align
    if border: c.border = box
    return c

wb = Workbook()
ws_d = wb.active; ws_d.title = "Dashboard"
ws_g = wb.create_sheet("Grade_Summary")
ws_p = wb.create_sheet("Profitability")
ws_v = wb.create_sheet("Vintage_Curves")
ws_r = wb.create_sheet("Roll_Rates")
ws_q = wb.create_sheet("Data_Quality")
ws_n = wb.create_sheet("Notes")
for w in wb.worksheets:
    w.sheet_view.showGridLines = False

# ================================================================= Grade_Summary
ws = ws_g
ws["A1"].value, ws["A1"].font = "Portfolio snapshot by risk grade (as of 30-Jun-2024)", f_title
ws["A2"].value, ws["A2"].font = "Blue = output of sql/02_portfolio_kpis.sql (inputs). Black = Excel formulas. Synthetic data.", f_sub
cols = ["Grade", "Loans", "Originated ($)", "Wtd avg rate (%)", "Outstanding ($)", "Balance 30+ DPD ($)", "Balance 60+ DPD ($)",
        "Balance 90+ DPD ($)", "Charged-off loans", "Charged-off principal ($)", "Recoveries ($)",
        "30+ DPD % of outstanding", "60+ DPD % of outstanding", "90+ DPD % of outstanding", "Share of originations"]
header(ws, 4, cols, height=45)
r0 = 5
for i, row in enumerate(kpi.itertuples(index=False)):
    r = r0 + i
    vals = [row.grade, row.loans, row.originated, row.wavg_rate_pct, row.outstanding, row.bal_30plus, row.bal_60plus,
            row.bal_90plus, row.chargeoff_loans, row.chargeoff_principal, row.recoveries]
    fmts = [None, INT, USD, '0.00', USD, USD, USD, USD, INT, USD, USD]
    for j, (v, fm) in enumerate(zip(vals, fmts)):
        put(ws, f"{L(j+1)}{r}", v, fm, font=f_bold if j == 0 else f_in)
    put(ws, f"L{r}", f"=IF(E{r}=0,0,F{r}/E{r})", PCT)
    put(ws, f"M{r}", f"=IF(E{r}=0,0,G{r}/E{r})", PCT)
    put(ws, f"N{r}", f"=IF(E{r}=0,0,H{r}/E{r})", PCT)
    put(ws, f"O{r}", f"=C{r}/$C${r0+len(kpi)}", PCT)
rt = r0 + len(kpi)                                   # total row
put(ws, f"A{rt}", "Total", font=f_bold, fill=fill_tot)
for c in "BCEFGHIJK":
    put(ws, f"{c}{rt}", f"=SUM({c}{r0}:{c}{rt-1})", INT if c in "BI" else USD, font=f_bold, fill=fill_tot)
put(ws, f"D{rt}", f"=SUMPRODUCT(C{r0}:C{rt-1},D{r0}:D{rt-1})/C{rt}", '0.00', font=f_bold, fill=fill_tot)
put(ws, f"L{rt}", f"=F{rt}/E{rt}", PCT, font=f_bold, fill=fill_tot)
put(ws, f"M{rt}", f"=G{rt}/E{rt}", PCT, font=f_bold, fill=fill_tot)
put(ws, f"N{rt}", f"=H{rt}/E{rt}", PCT, font=f_bold, fill=fill_tot)
put(ws, f"O{rt}", f"=SUM(O{r0}:O{rt-1})", PCT, font=f_bold, fill=fill_tot)
ws[f"A{rt+2}"].value = ("Note: balances are principal outstanding on live loans at 30-Jun-2024. Delinquency buckets are mutually "
                        "cumulative (30+ includes 60+ and 90+). Charge-off here covers all vintages, so recent vintages are "
                        "understated; use the Profitability tab (matured cohort) for loss rates.")
ws[f"A{rt+2}"].font = f_sub
ws.column_dimensions["A"].width = 10
for c in range(2, 16): ws.column_dimensions[L(c)].width = 15
ws.freeze_panes = "B5"
G_FIRST, G_LAST, G_TOT = r0, rt - 1, rt

# ================================================================= Profitability
ws = ws_p
ws["A1"].value, ws["A1"].font = "Realised profitability by grade: matured cohort", f_title
ws["A2"].value, ws["A2"].font = ("Cohort: 36-month loans issued Jan-2019 to Mar-2021 (fully run their term by 30-Jun-2024, so defaults are "
                                 "observed rather than censored). Blue = SQL output, black = formulas."), f_sub
cols = ["Grade", "Loans", "Originated ($)", "Wtd avg contractual rate", "Charged-off loans", "Charged-off principal ($)",
        "Interest collected ($)", "Recoveries ($)", "Balance-months ($)", "Charge-off rate (% loans)",
        "Net loss rate (% originated)", "Net profit ($)", "Balance-years ($)", "Net annualised return",
        "Yield retained (return / rate)", "Loss drag (pp of rate)"]
header(ws, 4, cols, height=58)
for i, row in enumerate(prof.itertuples(index=False)):
    r = 5 + i
    vals = [row.grade, row.loans, row.originated, row.wavg_rate_pct / 100, row.chargeoff_loans, row.chargeoff_principal,
            row.interest_collected, row.recoveries, row.balance_months]
    fmts = [None, INT, USD, PCT2, INT, USD, USD, USD, USD]
    for j, (v, fm) in enumerate(zip(vals, fmts)):
        put(ws, f"{L(j+1)}{r}", v, fm, font=f_bold if j == 0 else f_in)
    put(ws, f"J{r}", f"=E{r}/B{r}", PCT)
    put(ws, f"K{r}", f"=(F{r}-H{r})/C{r}", PCT)
    put(ws, f"L{r}", f"=G{r}+H{r}-F{r}", USD)
    put(ws, f"M{r}", f"=I{r}/12", USD)
    put(ws, f"N{r}", f"=L{r}/M{r}", PCT)
    put(ws, f"O{r}", f"=N{r}/D{r}", '0%')
    put(ws, f"P{r}", f"=(D{r}-N{r})*100", '0.0')
P_FIRST, P_LAST = 5, 4 + len(prof)
pt = P_LAST + 1
put(ws, f"A{pt}", "Total", font=f_bold, fill=fill_tot)
for c in "BCEFGHIL":
    put(ws, f"{c}{pt}", f"=SUM({c}{P_FIRST}:{c}{P_LAST})", INT if c in "BE" else USD, font=f_bold, fill=fill_tot)
put(ws, f"D{pt}", f"=SUMPRODUCT(C{P_FIRST}:C{P_LAST},D{P_FIRST}:D{P_LAST})/C{pt}", PCT2, font=f_bold, fill=fill_tot)
put(ws, f"J{pt}", f"=E{pt}/B{pt}", PCT, font=f_bold, fill=fill_tot)
put(ws, f"K{pt}", f"=(F{pt}-H{pt})/C{pt}", PCT, font=f_bold, fill=fill_tot)
put(ws, f"M{pt}", f"=I{pt}/12", USD, font=f_bold, fill=fill_tot)
put(ws, f"N{pt}", f"=L{pt}/M{pt}", PCT, font=f_bold, fill=fill_tot)
put(ws, f"O{pt}", f"=N{pt}/D{pt}", '0%', font=f_bold, fill=fill_tot)
put(ws, f"P{pt}", f"=(D{pt}-N{pt})*100", '0.0', font=f_bold, fill=fill_tot)
notes = [
    "Definitions: Net profit = interest collected + recoveries - charged-off principal.  Net annualised return = net profit / (balance-months / 12).",
    "Yield retained = realised return as a share of the contractual rate; Loss drag = contractual rate minus realised return, in percentage points.",
    "Excludes funding cost, servicing cost and taxes, so 'return' is a gross credit-adjusted yield, not profit after costs.",
    "Caution: grades F and G rest on small samples (see Loans column); treat their ratios as directional only.",
]
for k, t in enumerate(notes):
    ws[f"A{pt+2+k}"].value, ws[f"A{pt+2+k}"].font = t, f_sub
ws.column_dimensions["A"].width = 10
for c in range(2, 17): ws.column_dimensions[L(c)].width = 15
ws.freeze_panes = "B5"

# ================================================================= Vintage_Curves
ws = ws_v
ws["A1"].value, ws["A1"].font = "Vintage loss curves: cumulative charge-off by months on book", f_title
ws["A2"].value, ws["A2"].font = ("Rate = cumulative charged-off principal / originated principal of loans that have reached that age. "
                                 "A point is shown only while >=50% of the vintage's principal is observable."), f_sub
years = sorted(vint.vintage.unique())
blocks = [("Exposure ($)", 2), ("Cumulative charge-off ($)", 2 + len(years) + 1), ("Cumulative charge-off rate", 2 + 2 * (len(years) + 1))]
header(ws, 4, ["MOB"], 1)
for title, c0 in blocks:
    ws.cell(row=3, column=c0, value=title).font = f_bold
    header(ws, 4, [str(y) for y in years], c0, height=20)
mobs = list(range(1, 37))
piv_e = vint.pivot(index="mob", columns="vintage", values="exposure")
piv_c = vint.pivot(index="mob", columns="vintage", values="cum_chargeoff")
for i, m in enumerate(mobs):
    r = 5 + i
    put(ws, f"A{r}", m, font=f_bold)
    for j, y in enumerate(years):
        if m in piv_e.index and pd.notna(piv_e.loc[m, y]):
            ce, cc, cr = 2 + j, 2 + len(years) + 1 + j, 2 + 2 * (len(years) + 1) + j
            put(ws, f"{L(ce)}{r}", float(piv_e.loc[m, y]), USD, font=f_in)
            put(ws, f"{L(cc)}{r}", float(piv_c.loc[m, y]), USD, font=f_in)
            put(ws, f"{L(cr)}{r}", f"={L(cc)}{r}/{L(ce)}{r}", PCT)
ws.column_dimensions["A"].width = 8
for c in range(2, 2 + 3 * (len(years) + 1)): ws.column_dimensions[L(c)].width = 14
ws.freeze_panes = "B5"
V_RATE_C0 = 2 + 2 * (len(years) + 1)

# ================================================================= Roll_Rates
ws = ws_r
ws["A1"].value, ws["A1"].font = "Delinquency roll rates (monthly transitions)", f_title
ws["A2"].value, ws["A2"].font = "Where do loans in each bucket at month t-1 end up at month t? Counts are loan-months (blue); percentages are formulas.", f_sub
to_cols = ["Current", "30", "60", "90", "Charged Off", "Paid"]
header(ws, 4, ["From \\ To (days late)"] + to_cols + ["Total"], height=34)
header(ws, 11, ["From \\ To (% of row)"] + to_cols, height=34)
rp = roll.pivot_table(index="from_bucket", columns="to_bucket", values="loans", aggfunc="sum").fillna(0)
for i, fb in enumerate(["Current", "30", "60", "90"]):
    r, r2 = 5 + i, 12 + i
    put(ws, f"A{r}", fb, font=f_bold); put(ws, f"A{r2}", fb, font=f_bold)
    for j, tb in enumerate(to_cols):
        v = float(rp.loc[fb, tb]) if tb in rp.columns else 0.0
        put(ws, f"{L(2+j)}{r}", v, INT, font=f_in)
        put(ws, f"{L(2+j)}{r2}", f"=IF($H{r}=0,0,{L(2+j)}{r}/$H{r})", PCT)
    put(ws, f"H{r}", f"=SUM(B{r}:G{r})", INT, font=f_bold)
ws["A17"].value = ("Reading the matrix: a loan 30 days late rolls to 60 days late about 6 times in 10 and cures about 4 in 10; once 90 days late it is charged off. "
                   "Note: 90 -> Charged Off is 100% by construction of the simulated policy (charge-off after 4 missed instalments).")
ws["A17"].font = f_sub
ws["A19"].value, ws["A19"].font = "Early warning: monthly roll from Current to 30 days late, by grade", f_bold
header(ws, 20, ["Grade", "Current loan-months", "Rolled to 30", "Monthly roll rate"], height=34)
for i, row in enumerate(roll_g.itertuples(index=False)):
    r = 21 + i
    put(ws, f"A{r}", row.grade, font=f_bold)
    put(ws, f"B{r}", row.current_loan_months, INT, font=f_in)
    put(ws, f"C{r}", row.rolled_to_30, INT, font=f_in)
    put(ws, f"D{r}", f"=C{r}/B{r}", PCT2)
RG_FIRST, RG_LAST = 21, 20 + len(roll_g)
ws.column_dimensions["A"].width = 22
for c in range(2, 9): ws.column_dimensions[L(c)].width = 16

# ================================================================= Data_Quality
ws = ws_q
ws["A1"].value, ws["A1"].font = "Data validation log (sql/01_validation.sql)", f_title
ws["A2"].value, ws["A2"].font = "Every issue found in the raw origination file, how many rows it touched and what was done about it.", f_sub
header(ws, 4, ["Check", "Rule", "Rows affected", "Treatment"])
for i, row in enumerate(dq.itertuples(index=False)):
    r = 5 + i
    put(ws, f"A{r}", row.check_name, font=f_bold)
    put(ws, f"B{r}", row.rule, align=Alignment(wrap_text=True, vertical="top"))
    put(ws, f"C{r}", int(row.rows_affected), INT, font=f_in)
    put(ws, f"D{r}", row.treatment, align=Alignment(wrap_text=True, vertical="top"))
    ws.row_dimensions[r].height = 30
ws.column_dimensions["A"].width = 30; ws.column_dimensions["B"].width = 62
ws.column_dimensions["C"].width = 14; ws.column_dimensions["D"].width = 58

# ================================================================= Notes
ws = ws_n
lines = [
    ("About this workbook", f_title),
    ("", f_base),
    ("DATA: fully synthetic. 12,000 simulated unsecured instalment loans issued Jan-2019 to Jun-2023 with monthly repayment history to 30-Jun-2024.", f_base),
    ("The simulator uses LendingClub-style fields (grade A-G, term, rate, instalment) and plausible grade-level default behaviour. It is not real borrower data,", f_base),
    ("so none of the findings are evidence about any real lender or market.", f_base),
    ("", f_base),
    ("METHOD", f_bold),
    ("1. Raw origination file is deliberately dirty; sql/01_validation.sql cleans it and logs each issue (Data_Quality tab).", f_base),
    ("2. sql/02-04 build one row per loan with its outcome, then grade KPIs, vintage curves, roll rates and profitability.", f_base),
    ("3. SQL results are pasted here as inputs (blue). All ratios and KPIs are live formulas, so the workbook recalculates if inputs change.", f_base),
    ("", f_base),
    ("KEY DEFINITIONS", f_bold),
    ("Delinquency buckets: 30 / 60 / 90 = number of missed monthly instalments x 30 days. Charge-off after 4 missed instalments (120+ days).", f_base),
    ("Matured cohort: 36-month loans issued Jan-2019 to Mar-2021. Avoids the bias from recent loans that have not had time to default.", f_base),
    ("Net annualised return: (interest collected + recoveries - charged-off principal) / average balance outstanding. Before funding and operating costs.", f_base),
    ("", f_base),
    ("LIMITATIONS", f_bold),
    ("Single simulated economic cycle with stylised vintage effects; no prepayment-driven interest curtailment beyond what is simulated; no fees or insurance.", f_base),
    ("Grade F and G samples are small; their ratios are directional only.", f_base),
]
for i, (t, f) in enumerate(lines, start=1):
    ws[f"A{i}"].value, ws[f"A{i}"].font = t, f
ws.column_dimensions["A"].width = 150

# ================================================================= Dashboard
ws = ws_d
ws["B1"].value, ws["B1"].font = "Lending Portfolio Dashboard", f_title
ws["B2"].value = "Unsecured instalment lending | 12,000 simulated loans | snapshot 30-Jun-2024 | synthetic data for portfolio demonstration"
ws["B2"].font = f_sub
tiles = [
    ("Loans originated", f"=Grade_Summary!B{G_TOT}", INT, "Jan-2019 to Jun-2023"),
    ("Originated principal", f"=Grade_Summary!C{G_TOT}", '$#,##0.0,,"M"', "all grades"),
    ("Outstanding balance", f"=Grade_Summary!E{G_TOT}", '$#,##0.0,,"M"', "live loans at snapshot"),
    ("30+ days late", f"=Grade_Summary!L{G_TOT}", PCT, "of outstanding balance"),
    ("Charge-off rate", f"=Profitability!J{pt}", PCT, "matured cohort, % of loans"),
    ("Net annualised return", f"=Profitability!N{pt}", PCT, "matured cohort, before costs"),
]
for k, (lab, fml, fmt, sub) in enumerate(tiles):
    c0 = 2 + 2 * k
    for rr in (4, 5, 6):
        ws.merge_cells(start_row=rr, start_column=c0, end_row=rr, end_column=c0 + 1)
        for cc in (c0, c0 + 1):
            ws.cell(row=rr, column=cc).fill = fill_tile
    a = ws.cell(row=4, column=c0, value=lab); a.font = Font(name=F, size=9, bold=True, color=GREY); a.alignment = Alignment(horizontal="center")
    b = ws.cell(row=5, column=c0, value=fml); b.font = Font(name=F, size=18, bold=True, color=NAVY); b.number_format = fmt
    b.alignment = Alignment(horizontal="center", vertical="center")
    s = ws.cell(row=6, column=c0, value=sub); s.font = Font(name=F, size=8, italic=True, color=GREY); s.alignment = Alignment(horizontal="center")
ws.row_dimensions[5].height = 32
for c in range(1, 15): ws.column_dimensions[L(c)].width = 11.5
ws.column_dimensions["A"].width = 2

# ---- findings, computed from the same tables the formulas use
p = prof.copy()
p["co_rate"] = p.chargeoff_loans / p.loans
p["net"] = p.interest_collected + p.recoveries - p.chargeoff_principal
p["nar"] = p.net / (p.balance_months / 12)
p["rate"] = p.wavg_rate_pct / 100
p["ret"] = p.nar / p.rate
pg = p.set_index("grade")
v = vint.assign(r=vint.cum_chargeoff / vint.exposure)
vv = lambda y, m: float(v[(v.vintage == y) & (v.mob == m)].r.iloc[0])
rg = roll_g.assign(r=roll_g.rolled_to_30 / roll_g.current_loan_months).set_index("grade").r
r30 = roll[roll.from_bucket == "30"]; roll_30_60 = r30[r30.to_bucket == "60"].loans.sum() / r30.loans.sum()
low_ret = p[p.grade.isin(list("EFG"))]
findings = [
    f"1. Credit cost climbs steeply with grade: on the matured cohort, {pg.loc['A','co_rate']:.0%} of grade A loans charge off versus {pg.loc['E','co_rate']:.0%} of grade E and {pg.loc['G','co_rate']:.0%} of grade G.",
    f"2. Losses eat the extra yield: grade A keeps {pg.loc['A','ret']:.0%} of its contractual rate as realised return; grade E keeps {pg.loc['E','ret']:.0%} ({pg.loc['E','nar']:.1%} realised vs {pg.loc['E','rate']:.1%} charged). Grades F-G rest on only {int(pg.loc['F','loans'])} and {int(pg.loc['G','loans'])} loans, so treat them as directional.",
    f"3. The 2022 vintage is weaker: cumulative charge-off at 12 months on book is {vv(2022,12):.1%}, against {vv(2019,12):.1%} for 2019 and {vv(2021,12):.1%} for 2021 (about {vv(2022,12)/vv(2021,12)-1:.0%} worse than 2021).",
    f"4. Early warning is clear: the monthly roll from Current to 30 days late is {rg['A']:.1%} in grade A versus {rg['G']:.1%} in grade G, and {roll_30_60:.0%} of loans that reach 30 days late go on to 60.",
    f"Suggested actions: (a) review appetite or pricing for grade E and below, where realised return is under half the contractual rate; (b) tighten limits on 2022+ originations; (c) track the Current-to-30 roll rate monthly by grade as the earliest signal.",
]
ws["B8"].value, ws["B8"].font = "What the data says", Font(name=F, size=12, bold=True, color=NAVY)
for i, t in enumerate(findings):
    r = 9 + i
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=13)
    c = ws.cell(row=r, column=2, value=t)
    c.font = f_bold if t.startswith("Suggested") else f_base
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 30

# ---- charts
def style_axes(ch, ytitle=None, xtitle=None, yfmt=None):
    ch.x_axis.delete = False; ch.y_axis.delete = False
    if ytitle: ch.y_axis.title = ytitle
    if xtitle: ch.x_axis.title = xtitle
    if yfmt: ch.y_axis.number_format = yfmt
    ch.legend.position = "b"
    ch.height, ch.width = 7.6, 14.2

c1 = BarChart(); c1.type = "col"; c1.title = "Charge-off rate by grade (matured cohort)"
c1.add_data(Reference(ws_p, min_col=10, min_row=4, max_row=P_LAST), titles_from_data=True)
c1.set_categories(Reference(ws_p, min_col=1, min_row=P_FIRST, max_row=P_LAST))
c1.series[0].graphicalProperties.solidFill = NAVY
c1.dataLabels = DataLabelList(); c1.dataLabels.showVal = True; c1.dataLabels.showSerName = False; c1.dataLabels.showCatName = False; c1.dataLabels.showLegendKey = False; c1.dataLabels.numFmt = '0%'
style_axes(c1, yfmt="0%"); c1.legend = None
ws.add_chart(c1, "B15")

c2 = BarChart(); c2.type = "col"; c2.title = "Contractual rate vs realised return by grade"
c2.add_data(Reference(ws_p, min_col=4, min_row=4, max_row=P_LAST), titles_from_data=True)
c2.add_data(Reference(ws_p, min_col=14, min_row=4, max_row=P_LAST), titles_from_data=True)
c2.set_categories(Reference(ws_p, min_col=1, min_row=P_FIRST, max_row=P_LAST))
c2.series[0].graphicalProperties.solidFill = "A6A6A6"; c2.series[1].graphicalProperties.solidFill = ORANGE
style_axes(c2, yfmt="0%")
ws.add_chart(c2, "H15")

c3 = LineChart(); c3.title = "Vintage curves: cumulative charge-off by months on book"
for j in range(len(years)):
    c3.add_data(Reference(ws_v, min_col=V_RATE_C0 + j, min_row=4, max_row=4 + 36), titles_from_data=True)
c3.set_categories(Reference(ws_v, min_col=1, min_row=5, max_row=4 + 36))
for s, col in zip(c3.series, [NAVY, TEAL, "70AD47", ORANGE, "C00000"]):
    s.graphicalProperties.line.solidFill = col; s.graphicalProperties.line.width = 22000; s.smooth = False
style_axes(c3, ytitle="% of originated principal", xtitle="Months on book", yfmt="0%")
ws.add_chart(c3, "B31")

c4 = BarChart(); c4.type = "col"; c4.title = "30+ days late, % of outstanding balance (30-Jun-2024)"
c4.add_data(Reference(ws_g, min_col=12, min_row=4, max_row=G_LAST), titles_from_data=True)
c4.set_categories(Reference(ws_g, min_col=1, min_row=G_FIRST, max_row=G_LAST))
c4.series[0].graphicalProperties.solidFill = TEAL
c4.dataLabels = DataLabelList(); c4.dataLabels.showVal = True; c4.dataLabels.showSerName = False; c4.dataLabels.showCatName = False; c4.dataLabels.showLegendKey = False; c4.dataLabels.numFmt = '0.0%'
style_axes(c4, yfmt="0%"); c4.legend = None
ws.add_chart(c4, "H31")

ws.sheet_view.zoomScale = 90
for w in wb.worksheets:                                   # print setup: landscape, one page wide
    w.page_setup.orientation = "landscape"
    w.page_setup.fitToWidth = 1
    w.page_setup.fitToHeight = 0
    w.sheet_properties.pageSetUpPr.fitToPage = True
wb.save(OUT)
print("saved", OUT)
