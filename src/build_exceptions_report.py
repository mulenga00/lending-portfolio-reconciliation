"""
Step 4b - Build reports/Reconciliation_Exceptions_Report.xlsx from the SQL reconciliation output.
Sheets: Summary (formulas over the register), Exceptions (working tracker), Rules, Engine_Validation.
"""
import sqlite3, pandas as pd
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / "reports" / "tables"
OUT = ROOT / "reports" / "Reconciliation_Exceptions_Report.xlsx"
con = sqlite3.connect(ROOT / "data" / "lending.db")
res = pd.read_sql("SELECT * FROM recon_results", con)
rules = pd.read_csv(T / "recon_rule_summary.csv")
tot = pd.read_csv(T / "recon_totals.csv").set_index("metric").value
ev = pd.read_csv(T / "eval_summary.csv")
unexplained_n = len(pd.read_csv(T / "eval_unexplained.csv"))
params = pd.read_sql("SELECT * FROM recon_params", con).iloc[0]

NAVY, GREY, LIGHT = "1F3864", "7F7F7F", "EAF1FB"
F = "Arial"
f_base, f_in = Font(name=F, size=10), Font(name=F, size=10, color="0000FF")
f_bold, f_hdr = Font(name=F, size=10, bold=True), Font(name=F, size=10, bold=True, color="FFFFFF")
f_title, f_sub = Font(name=F, size=18, bold=True, color=NAVY), Font(name=F, size=9, italic=True, color=GREY)
f_sec = Font(name=F, size=12, bold=True, color=NAVY)
fill_hdr, fill_tot = PatternFill("solid", fgColor=NAVY), PatternFill("solid", fgColor="D9E2F3")
thin = Side(style="thin", color="BFBFBF"); box = Border(top=thin, bottom=thin, left=thin, right=thin)
USD2, USD0, INT, PCT = '$#,##0.00;($#,##0.00);-', '$#,##0;($#,##0);-', '#,##0;(#,##0);-', '0.0%'

def put(ws, ref, v, fmt=None, font=f_base, fill=None, align=None):
    c = ws[ref]; c.value, c.font, c.border = v, font, box
    if fmt: c.number_format = fmt
    if fill: c.fill = fill
    if align: c.alignment = align
    return c
def header(ws, row, labels, col0=1, height=30):
    for i, t in enumerate(labels):
        c = ws.cell(row=row, column=col0 + i, value=t)
        c.font, c.fill, c.border = f_hdr, fill_hdr, box
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = height

# ---------------------------------------------------------------- prepare register
d = res.copy()
d["ledger"] = d.ledger_cents / 100
d["bank"] = d.bank_cents / 100
d["variance"] = d.variance_cents / 100
d.loc[d.side != "MATCHED PAIR", "variance"] = None
d["amount_issue"] = d.apply(lambda r: abs(r.variance) if r.exception_type == "Amount mismatch"
                            else abs(r.ledger) if pd.notna(r.ledger) else abs(r.bank), axis=1)
d["class_ord"] = d.exception_class.map({"Break": 0, "Review": 1, "Timing": 2})
d["prio_ord"] = d.priority.map({"High": 0, "Medium": 1, "Low": 2})
d = d.sort_values(["class_ord", "prio_ord", "amount_issue"], ascending=[True, True, False]).reset_index(drop=True)
d["status"] = d.exception_class.map({"Break": "Open", "Review": "Open", "Timing": "Monitor"})
d["side_lbl"] = d.side.map({"MATCHED PAIR": "Matched pair", "LEDGER ONLY": "Ledger only", "BANK ONLY": "Bank only"})

wb = Workbook()
ws_s = wb.active; ws_s.title = "Summary"
ws_e = wb.create_sheet("Exceptions")
ws_r = wb.create_sheet("Rules")
ws_v = wb.create_sheet("Engine_Validation")
for w in wb.worksheets: w.sheet_view.showGridLines = False

# ================================================================= Exceptions
ws = ws_e
ws["A1"].value, ws["A1"].font = "Exceptions register: Q2-2024 cash reconciliation", f_title
ws["A2"].value, ws["A2"].font = ("One row per item that needs attention or explanation. Class: Break = needs correction; Review = matched with low confidence, "
                                 "confirm; Timing = expected to clear. Status column is a dropdown for tracking."), f_sub
cols = ["Item ID", "Class", "Exception type", "Side", "Loan ID", "Ledger txn", "Bank ref", "Date", "Ledger ($)", "Bank ($)",
        "Variance ($) ledger - bank", "Amount at issue ($)", "Age (days)", "Priority", "Owner", "Root cause", "Recommended action", "Status"]
header(ws, 4, cols, height=40)
E0 = 5
for i, r in enumerate(d.itertuples(index=False)):
    row = E0 + i
    vals = [r.item_id, r.exception_class, r.exception_type, r.side_lbl, r.loan_id if pd.notna(r.loan_id) else None,
            r.ledger_txn_id if pd.notna(r.ledger_txn_id) else None, r.bank_id if pd.notna(r.bank_id) else None, r.item_date,
            r.ledger if pd.notna(r.ledger) else None, r.bank if pd.notna(r.bank) else None,
            r.variance if pd.notna(r.variance) else None, r.amount_issue, int(r.age_days), r.priority, r.owner,
            r.root_cause, r.recommended_action, r.status]
    for j, v in enumerate(vals, start=1):
        c = ws.cell(row=row, column=j, value=v); c.font = f_base
        if j in (9, 10, 11, 12): c.number_format = USD2
    pc = ws.cell(row=row, column=14)
    pc.fill = PatternFill("solid", fgColor={"High": "F8CBAD", "Medium": "FFE699", "Low": "C6E0B4"}[r.priority])
E1 = E0 + len(d) - 1
dv = DataValidation(type="list", formula1='"Open,In progress,Resolved,No action,Monitor"', allow_blank=False)
ws.add_data_validation(dv); dv.add(f"R{E0}:R{E1}")
ws.auto_filter.ref = f"A4:R{E1}"
ws.freeze_panes = "D5"
for col, w in zip("ABCDEFGHIJKLMNOPQR", [8, 9, 34, 13, 11, 13, 13, 11, 12, 12, 14, 14, 9, 10, 17, 70, 70, 12]):
    ws.column_dimensions[col].width = w

def rng(col): return f"Exceptions!${col}${E0}:${col}${E1}"
TYPE, CLASS, LEDG, BANK, VAR, AMT, AGE, PRIO, OWN = rng("C"), rng("B"), rng("I"), rng("J"), rng("K"), rng("L"), rng("M"), rng("N"), rng("O")

# ================================================================= Summary
ws = ws_s
ws["A1"].value, ws["A1"].font = "Cash Reconciliation Report", f_title
ws["A2"].value = (f"Loan servicing ledger vs bank statement | {params.period_start} to {params.period_end} | "
                  "synthetic data | blue = input from SQL, black = formula")
ws["A2"].font = f_sub

# ---- 1. bridge
ws["A4"].value, ws["A4"].font = "1. Ledger-to-bank bridge: is the difference fully explained?", f_sec
header(ws, 5, ["Line", "Amount ($)", "How it is derived"], height=22)
r2 = rules.set_index("rule")
ledger_total, bank_total = tot["ledger_value_cents"] / 100, tot["bank_value_cents"] / 100
bridge = [
    ("Ledger collections total", ledger_total, "Input: sum of servicing ledger", f_in),
    ("Bank cash total", bank_total, "Input: sum of bank statement lines (returns are negative)", f_in),
    ("Difference to explain (ledger - bank)", "=B6-B7", "Formula", f_bold),
    ("Card processing fees withheld (matched card payments)", r2.loc["R2_CARD_FEE", "variance_cents"] / 100, "Input: rule R2 variance; bank settles net of 1.5% + $0.20", f_in),
    ("Amount mismatches (variance on matched pairs)", f'=SUMIFS({VAR},{TYPE},"Amount mismatch")', "Formula over Exceptions", f_base),
    ("Misapplied payments (variance on matched pairs)", f'=SUMIFS({VAR},{TYPE},"Misapplied payment")', "Formula over Exceptions", f_base),
    ("Low-confidence matches (card fees on unreferenced payments)", f'=SUMIFS({VAR},{TYPE},"Reference unreadable - confirm match")', "Formula over Exceptions", f_base),
    ("Ledger only: duplicate postings", f'=SUMIFS({LEDG},{TYPE},"Duplicate posting")', "Ledger value with no bank cash", f_base),
    ("Ledger only: posted without bank cash", f'=SUMIFS({LEDG},{TYPE},"Posted without bank cash")', "Ledger value with no bank cash", f_base),
    ("Ledger only: timing, in transit at cut-off", f'=SUMIFS({LEDG},{TYPE},"Timing - in transit at cut-off")', "Posted last days of June; cash lands in July", f_base),
    ("Bank only: cash received, not posted", f'=-SUMIFS({BANK},{TYPE},"Cash received, not posted")', "Bank cash with no ledger entry (sign reversed)", f_base),
    ("Bank only: unapplied cash, reference unreadable", f'=-SUMIFS({BANK},{TYPE},"Unapplied cash - reference unreadable")', "Sign reversed", f_base),
    ("Bank only: timing, prior-period posting", f'=-SUMIFS({BANK},{TYPE},"Timing - prior-period posting")', "Ledger posted in March; cash lands in April", f_base),
    ("Bank only: returns not in ledger", f'=-SUMIFS({BANK},{TYPE},"Bank return not reflected in ledger")', "Negative bank lines, sign reversed", f_base),
]
for i, (lab, val, how, fnt) in enumerate(bridge):
    r = 6 + i
    put(ws, f"A{r}", lab, font=f_bold if i in (0, 1, 2) else f_base)
    put(ws, f"B{r}", val, USD2, font=fnt)
    put(ws, f"C{r}", how, font=f_sub)
rb = 6 + len(bridge)
put(ws, f"A{rb}", "Total explained", font=f_bold, fill=fill_tot); put(ws, f"B{rb}", f"=SUM(B9:B{rb-1})", USD2, font=f_bold, fill=fill_tot); put(ws, f"C{rb}", "Sum of the lines above", font=f_sub, fill=fill_tot)
put(ws, f"A{rb+1}", "Unexplained difference", font=f_bold, fill=fill_tot); put(ws, f"B{rb+1}", f"=ROUND(B8-B{rb},2)", USD2, font=f_bold, fill=fill_tot)
put(ws, f"C{rb+1}", "Must be zero: every dollar of difference is traced to an item", font=f_sub, fill=fill_tot)

# ---- 2. match results
s = rb + 4
ws[f"A{s-1}"].value, ws[f"A{s-1}"].font = "2. Match results by rule", f_sec
header(ws, s, ["Rule", "Pairs matched", "Ledger ($)", "Bank ($)", "% of ledger items"], height=24)
desc = {"R1_EXACT": "R1 Exact (ACH)", "R2_CARD_FEE": "R2 Card, net of fee", "R3_AMOUNT_VARIANCE": "R3 Amount variance (exception)",
        "R4_MISAPPLIED": "R4 Misapplied (exception)", "R5_FUZZY_AMT_DATE": "R5 Fuzzy, low confidence (review)"}
for i, row in enumerate(rules.itertuples(index=False)):
    r = s + 1 + i
    put(ws, f"A{r}", desc[row.rule], font=f_bold)
    put(ws, f"B{r}", int(row.pairs), INT, font=f_in)
    put(ws, f"C{r}", row.ledger_cents / 100, USD0, font=f_in)
    put(ws, f"D{r}", row.bank_cents / 100, USD0, font=f_in)
    put(ws, f"E{r}", f"=B{r}/$B${s+len(rules)+2}", PCT)
rr = s + 1 + len(rules)
put(ws, f"A{rr}", "Ledger items not matched", font=f_bold)
put(ws, f"B{rr}", f"=B{rr+1}-SUM(B{s+1}:B{rr-1})", INT); put(ws, f"E{rr}", f"=B{rr}/$B${rr+1}", PCT)
put(ws, f"A{rr+1}", "Total ledger items", font=f_bold, fill=fill_tot)
put(ws, f"B{rr+1}", int(tot["ledger_items"]), INT, font=Font(name=F, size=10, bold=True, color="0000FF"), fill=fill_tot)
put(ws, f"E{rr+1}", f"=SUM(E{s+1}:E{rr})", PCT, font=f_bold, fill=fill_tot)
put(ws, f"A{rr+2}", "Clean auto-match rate (R1 + R2)", font=f_bold)
put(ws, f"B{rr+2}", f"=(B{s+1}+B{s+2})/B{rr+1}", PCT, font=f_bold)

# ---- 3. by exception type
s3 = rr + 6
ws[f"A{s3-1}"].value, ws[f"A{s3-1}"].font = "3. Exceptions by type", f_sec
header(ws, s3, ["Exception type", "Class", "Items", "Amount at issue ($)", "Avg age (days)", "High priority"], height=24)
types = d.groupby(["exception_class", "exception_type"]).size().reset_index().assign(o=lambda x: x.exception_class.map({"Break": 0, "Review": 1, "Timing": 2})) \
         .sort_values(["o", "exception_type"])
for i, row in enumerate(types.itertuples(index=False)):
    r = s3 + 1 + i
    put(ws, f"A{r}", row.exception_type, font=f_bold); put(ws, f"B{r}", row.exception_class)
    put(ws, f"C{r}", f'=COUNTIFS({TYPE},A{r})', INT)
    put(ws, f"D{r}", f'=SUMIFS({AMT},{TYPE},A{r})', USD0)
    put(ws, f"E{r}", f'=AVERAGEIFS({AGE},{TYPE},A{r})', '0')
    put(ws, f"F{r}", f'=COUNTIFS({TYPE},A{r},{PRIO},"High")', INT)
r3 = s3 + 1 + len(types)
put(ws, f"A{r3}", "Total", font=f_bold, fill=fill_tot); put(ws, f"B{r3}", "", fill=fill_tot)
put(ws, f"C{r3}", f"=SUM(C{s3+1}:C{r3-1})", INT, font=f_bold, fill=fill_tot)
put(ws, f"D{r3}", f"=SUM(D{s3+1}:D{r3-1})", USD0, font=f_bold, fill=fill_tot)
put(ws, f"E{r3}", "", fill=fill_tot)
put(ws, f"F{r3}", f"=SUM(F{s3+1}:F{r3-1})", INT, font=f_bold, fill=fill_tot)

# ---- 4. ageing and ownership
s4 = r3 + 4
ws[f"A{s4-1}"].value, ws[f"A{s4-1}"].font = "4. Open breaks: ageing and ownership", f_sec
header(ws, s4, ["Age bucket (days since item date)", "Break items", "Amount at issue ($)"], height=24)
for i, (lab, lo, hi) in enumerate([("0 - 30", 0, 30), ("31 - 60", 31, 60), ("61 - 91", 61, 91)]):
    r = s4 + 1 + i
    put(ws, f"A{r}", lab, font=f_bold)
    put(ws, f"B{r}", f'=COUNTIFS({CLASS},"Break",{AGE},">={lo}",{AGE},"<={hi}")', INT)
    put(ws, f"C{r}", f'=SUMIFS({AMT},{CLASS},"Break",{AGE},">={lo}",{AGE},"<={hi}")', USD0)
header(ws, s4 + 6, ["Owner", "Open breaks + reviews", "of which High priority"], height=24)
owners = sorted(d[d.exception_class != "Timing"].owner.unique())
for i, o in enumerate(owners):
    r = s4 + 7 + i
    put(ws, f"A{r}", o, font=f_bold)
    put(ws, f"B{r}", f'=COUNTIFS({OWN},A{r},{CLASS},"<>Timing")', INT)
    put(ws, f"C{r}", f'=COUNTIFS({OWN},A{r},{CLASS},"<>Timing",{PRIO},"High")', INT)
ws.column_dimensions["A"].width = 56
for c in "BCDEF": ws.column_dimensions[c].width = 20
ws.column_dimensions["C"].width = 22

# ================================================================= Rules
ws = ws_r
ws["A1"].value, ws["A1"].font = "Matching rules and parameters", f_title
ws["A2"].value, ws["A2"].font = "Rules run in order; each only sees items the earlier rules left unmatched. Pairing is one-to-one (nearest date wins).", f_sub
header(ws, 4, ["Rule", "Logic", "Outcome"], height=22)
rule_rows = [
    ("R1 Exact", "Same loan reference (parsed from bank narrative), identical amount, bank date 0-5 days after ledger date. ACH payments.", "Matched"),
    ("R2 Card net of fee", "Same loan reference, bank amount = ledger x (1 - 1.5%) - $0.20 within 2 cents, same date window. Card payments.", "Matched; fee variance recorded"),
    ("R3 Amount variance", "Same loan reference and date window but amounts differ by up to 90% of the ledger amount.", "Exception: Amount mismatch"),
    ("R4 Misapplied", "Bank reference and ledger loan differ; identical amount and date window; both sides still unmatched.", "Exception: Misapplied payment"),
    ("R5 Fuzzy", "Bank narrative has no usable loan reference; accepted only if the amount + date candidate is unique in both directions.", "Review: confirm match"),
    ("Residual: ledger only", "Duplicate if same loan, amount and date already matched; Timing if posted within 5 days of period end; otherwise Posted without cash.", "Classified by cause"),
    ("Residual: bank only", "Return if negative or narrative says RETURN; Timing if value date within 5 days of period start; otherwise unapplied / not posted.", "Classified by cause"),
]
for i, (a, b, c) in enumerate(rule_rows):
    r = 5 + i
    put(ws, f"A{r}", a, font=f_bold, align=Alignment(vertical="top")); put(ws, f"B{r}", b, align=Alignment(wrap_text=True, vertical="top"))
    put(ws, f"C{r}", c, align=Alignment(wrap_text=True, vertical="top")); ws.row_dimensions[r].height = 42
ws["A14"].value, ws["A14"].font = "Parameters (sql/05_reconciliation.sql, table recon_params)", f_sec
header(ws, 15, ["Parameter", "Value", "Meaning"], height=22)
for i, (a, b, c) in enumerate([
    ("period_start / period_end", f"{params.period_start} / {params.period_end}", "Reconciliation window"),
    ("fee_pct / fee_flat_cents", f"{params.fee_pct:.1%} / {int(params.fee_flat_cents)}", "Card settlement fee schedule"),
    ("date_window_days", int(params.date_window_days), "Max days bank value date may trail ledger posting date"),
    ("fee_tol_cents", int(params.fee_tol_cents), "Rounding tolerance on fee-adjusted amount"),
    ("amount_var_pct", f"{params.amount_var_pct:.0%}", "Max amount variance for rule R3"),
    ("cutoff_days", int(params.cutoff_days), "Days at period edges treated as timing")]):
    r = 16 + i
    put(ws, f"A{r}", a, font=f_bold); put(ws, f"B{r}", b, font=f_in); put(ws, f"C{r}", c)
ws.column_dimensions["A"].width = 30; ws.column_dimensions["B"].width = 100; ws.column_dimensions["C"].width = 58

# ================================================================= Engine validation
ws = ws_v
ws["A1"].value, ws["A1"].font = "Engine validation against the injected-break answer key", f_title
ws["A2"].value, ws["A2"].font = ("Possible only because the data is synthetic: every break was injected on purpose and recorded in data/injected_breaks_key.csv. "
                                 "Real reconciliations have no answer key."), f_sub
header(ws, 4, ["Injected break type", "Expected exception type", "Injected", "Flagged", "Classified correctly", "Flag rate", "Correct-label rate"], height=34)
for i, row in enumerate(ev.itertuples(index=False)):
    r = 5 + i
    put(ws, f"A{r}", row.break_type, font=f_bold); put(ws, f"B{r}", row.expected_type)
    put(ws, f"C{r}", int(row.injected), INT, font=f_in); put(ws, f"D{r}", int(row.flagged), INT, font=f_in)
    put(ws, f"E{r}", int(row.classified_correctly), INT, font=f_in)
    put(ws, f"F{r}", f"=D{r}/C{r}", PCT); put(ws, f"G{r}", f"=E{r}/C{r}", PCT)
rv = 5 + len(ev)
put(ws, f"A{rv}", "Total", font=f_bold, fill=fill_tot); put(ws, f"B{rv}", "", fill=fill_tot)
for c in "CDE": put(ws, f"{c}{rv}", f"=SUM({c}5:{c}{rv-1})", INT, font=f_bold, fill=fill_tot)
put(ws, f"F{rv}", f"=D{rv}/C{rv}", PCT, font=f_bold, fill=fill_tot); put(ws, f"G{rv}", f"=E{rv}/C{rv}", PCT, font=f_bold, fill=fill_tot)
put(ws, f"A{rv+2}", "Break-class exceptions NOT traceable to an injected item", font=f_bold)
put(ws, f"C{rv+2}", unexplained_n, INT, font=f_in)
notes = [
    "Known limitation: a transposed-digit amount error can be so large (e.g. $100.00 keyed as $10.00) that it falls outside rule R3's 90% tolerance.",
    "Such an item is still flagged, but as two separate unmatched items (Posted without bank cash + Cash received, not posted) instead of one Amount mismatch.",
    "Injection was kept away from the first and last week of the quarter so cut-off timing is not confused with true breaks.",
]
for i, t in enumerate(notes): ws[f"A{rv+4+i}"].value, ws[f"A{rv+4+i}"].font = t, f_sub
ws.column_dimensions["A"].width = 30; ws.column_dimensions["B"].width = 38
for c in "CDEFG": ws.column_dimensions[c].width = 16

for w in wb.worksheets:
    w.page_setup.orientation = "landscape"; w.page_setup.fitToWidth = 1; w.page_setup.fitToHeight = 0
    w.sheet_properties.pageSetUpPr.fitToPage = True
wb.save(OUT)
print("saved", OUT, "| register rows:", len(d))
