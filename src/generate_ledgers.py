"""
Step 2 - Build two independent transaction files for the Q2-2024 reconciliation.

  servicing_ledger.csv   what the loan servicing system says was collected
  bank_statement.csv     what the bank / card processor says arrived

Both are derived from the same underlying borrower payments (monthly_performance.csv),
then realistic differences are layered on. Every deliberately injected break is written to
injected_breaks_key.csv so the SQL matching engine can be scored against a known answer.

Realistic frictions applied to ALL payments (these are not "breaks", the engine must absorb them):
  * ledger posts on the next business day if the borrower pays at a weekend
  * bank value date lags posting by 1-2 business days (ACH, card)
  * card payments settle NET of a processing fee (1.5% + $0.20)
  * period cut-off: payments straddling 1 Apr / 30 Jun appear on one side only

Injected breaks:
  DUPLICATE_POSTING, CASH_NOT_POSTED, POSTED_NO_CASH, AMOUNT_ERROR, MISAPPLIED,
  UNREVERSED_RETURN, and UNREADABLE_REF (a matching difficulty rather than a true break).
"""
import numpy as np, pandas as pd
from pathlib import Path

SEED = 7
rng = np.random.default_rng(SEED)
DATA = Path(__file__).resolve().parent.parent / "data"
P_START, P_END = pd.Timestamp("2024-04-01"), pd.Timestamp("2024-06-30")
FEE_PCT, FEE_FLAT = 0.015, 0.20

perf = pd.read_csv(DATA / "monthly_performance.csv", parse_dates=["period_end"])
loans = pd.read_csv(DATA / "loans_raw.csv").drop_duplicates("loan_id")[["loan_id", "pmt_due_day"]]

# ---- real payment events for Mar-Jun 2024
tx = perf[(perf.period_end >= "2024-03-31") & (perf.paid_amount > 0)][["loan_id", "period_end", "paid_amount"]].merge(loans, on="loan_id")
method = pd.Series(rng.choice(["ACH", "CARD"], size=loans.shape[0], p=[0.70, 0.30]), index=loans.loan_id)
tx["method"] = tx.loan_id.map(method)

lag = rng.choice([0, 1, 2, 3], size=len(tx), p=[0.60, 0.20, 0.10, 0.10])
days_in_month = tx.period_end.dt.days_in_month
pay_day = np.minimum(tx.pmt_due_day.values + lag, days_in_month.values)
tx["pay_date"] = pd.to_datetime(dict(year=tx.period_end.dt.year, month=tx.period_end.dt.month, day=pay_day))
tx["posting_date"] = pd.to_datetime(np.busday_offset(tx.pay_date.values.astype("datetime64[D]"), 0, roll="forward"))
settle_lag = np.where(tx.method == "CARD", rng.choice([1, 2], size=len(tx), p=[.5, .5]),
                      rng.choice([1, 2], size=len(tx), p=[.65, .35]))
tx["value_date"] = pd.to_datetime(np.busday_offset(tx.posting_date.values.astype("datetime64[D]"), settle_lag, roll="forward"))
tx["amount_cents"] = np.round(tx.paid_amount * 100).astype(int)
tx["bank_cents"] = np.where(tx.method == "CARD",
                            np.round(tx.amount_cents * (1 - FEE_PCT) - FEE_FLAT * 100).astype(int), tx.amount_cents)
tx = tx.sort_values(["posting_date", "loan_id"]).reset_index(drop=True)
tx["txn_id"] = [f"SL-{i:07d}" for i in range(1, len(tx) + 1)]
tx["bank_id"] = [f"BK-{i:08d}" for i in range(10_000_001, 10_000_001 + len(tx))]
tx["ledger_loan"] = tx.loan_id
tx["ledger_cents"] = tx.amount_cents
tx["narr_ref"] = tx.loan_id

# ---- pick injection targets away from period edges so cut-off timing stays unambiguous
eligible = np.array(tx[(tx.posting_date >= "2024-04-08") & (tx.posting_date <= "2024-06-18")].index)
rng.shuffle(eligible)
n = len(eligible)
def take(frac, pool=None):
    global eligible
    pool = eligible if pool is None else pool
    k = max(5, int(round(len(tx) * frac)))
    picked = pool[:k]
    eligible = np.array(np.setdiff1d(eligible, picked))
    rng.shuffle(eligible)
    return picked
ach_pool = lambda: eligible[(tx.loc[eligible, "method"] == "ACH").to_numpy()]

key, extra_ledger, extra_bank = [], [], []

dup = take(0.0035)
for i in dup:
    r = tx.loc[i]
    extra_ledger.append(dict(loan_id=r.loan_id, posting_date=r.posting_date, amount_cents=r.amount_cents, method=r.method, src=i))
    key.append(("DUPLICATE_POSTING", None, None, r.loan_id, r.amount_cents, i))

no_post = take(0.0040)                       # bank has cash, ledger never posted it
tx["drop_ledger"] = False; tx.loc[no_post, "drop_ledger"] = True
for i in no_post:
    key.append(("CASH_NOT_POSTED", None, tx.loc[i, "bank_id"], tx.loc[i, "loan_id"], tx.loc[i, "bank_cents"], i))

no_cash = take(0.0035)                       # ledger posted, bank never received
tx["drop_bank"] = False; tx.loc[no_cash, "drop_bank"] = True
for i in no_cash:
    key.append(("POSTED_NO_CASH", tx.loc[i, "txn_id"], None, tx.loc[i, "loan_id"], tx.loc[i, "amount_cents"], i))

def transpose(c):
    s = str(c)
    for j in rng.permutation(len(s) - 2):     # leave the cents digits alone
        if s[j] != s[j + 1]:
            return int(s[:j] + s[j + 1] + s[j] + s[j + 2:])
    return c + 1000
amt_err = take(0.0025)
for i in amt_err:
    old = tx.loc[i, "amount_cents"]
    new = transpose(old)
    tx.loc[i, "ledger_cents"] = new
    key.append(("AMOUNT_ERROR", tx.loc[i, "txn_id"], tx.loc[i, "bank_id"], tx.loc[i, "loan_id"], new - old, i))

mis = take(0.0015, ach_pool())
all_ids = loans.loan_id.to_numpy()
for i in mis:
    wrong = rng.choice(all_ids)
    while wrong == tx.loc[i, "loan_id"]:
        wrong = rng.choice(all_ids)
    tx.loc[i, "ledger_loan"] = wrong
    key.append(("MISAPPLIED", tx.loc[i, "txn_id"], tx.loc[i, "bank_id"], tx.loc[i, "loan_id"], tx.loc[i, "amount_cents"], i))

ret = take(0.0025, ach_pool())
for i in ret:
    r = tx.loc[i]
    vd = r.value_date + pd.Timedelta(days=int(rng.integers(3, 7)))
    extra_bank.append(dict(value_date=vd, amount_cents=-int(r.bank_cents), loan_id=r.loan_id, kind="RETURN"))
    key.append(("UNREVERSED_RETURN", None, "RETURN", r.loan_id, -int(r.bank_cents), i))

garb = take(0.0050)
tx["garble"] = ""
tx.loc[garb, "garble"] = rng.choice(["none", "short"], size=len(garb))
for i in garb:
    key.append(("UNREADABLE_REF", tx.loc[i, "txn_id"], tx.loc[i, "bank_id"], tx.loc[i, "loan_id"], tx.loc[i, "bank_cents"], i))
tx["garble"] = tx["garble"].fillna("")

# ---- assemble ledger
led = tx[~tx.drop_ledger][["txn_id", "ledger_loan", "posting_date", "ledger_cents", "method"]].rename(
    columns={"ledger_loan": "loan_id", "ledger_cents": "amount_cents"})
if extra_ledger:
    d = pd.DataFrame(extra_ledger)
    d["txn_id"] = [f"SL-{i:07d}" for i in range(len(tx) + 1, len(tx) + 1 + len(d))]
    for j, i in enumerate(d.src):
        key[[k for k, e in enumerate(key) if e[0] == "DUPLICATE_POSTING" and e[5] == i][0]] = \
            ("DUPLICATE_POSTING", d.txn_id.iloc[j], None, d.loan_id.iloc[j], d.amount_cents.iloc[j], i)
    led = pd.concat([led, d[led.columns]])
led = led[(led.posting_date >= P_START) & (led.posting_date <= P_END)].sort_values(["posting_date", "txn_id"])
led["posting_date"] = led.posting_date.dt.strftime("%Y-%m-%d")
led["amount"] = (led.amount_cents / 100).round(2)
led[["txn_id", "loan_id", "posting_date", "amount", "method"]].to_csv(DATA / "servicing_ledger.csv", index=False)

# ---- assemble bank
def narrative(r):
    ref = r.loan_id
    if r.garble == "none":
        return "ACH CR UNIDENTIFIED CUST PMT" if r.method == "ACH" else "CARD SETTLE UNIDENTIFIED NET OF FEES"
    if r.garble == "short":
        ref = ref[:6]
    return f"ACH CR REF:{ref} CUST PMT" if r.method == "ACH" else f"CARD SETTLE REF:{ref} NET OF FEES"
b = tx[~tx.drop_bank].copy()
b["narrative"] = b.apply(narrative, axis=1)
bank = b[["bank_id", "value_date", "bank_cents", "narrative"]].rename(columns={"bank_cents": "amount_cents"})
if extra_bank:
    e = pd.DataFrame(extra_bank)
    e["bank_id"] = [f"BK-{i:08d}" for i in range(20_000_001, 20_000_001 + len(e))]
    e["narrative"] = "ACH RETURN R01 NSF REF:" + e.loan_id
    for j, bid in enumerate(e.bank_id):
        idx = [k for k, x in enumerate(key) if x[0] == "UNREVERSED_RETURN" and x[3] == e.loan_id.iloc[j] and x[2] == "RETURN"][0]
        key[idx] = ("UNREVERSED_RETURN", None, bid, key[idx][3], key[idx][4], key[idx][5])
    bank = pd.concat([bank, e[bank.columns]])
bank = bank[(bank.value_date >= P_START) & (bank.value_date <= P_END)].sort_values(["value_date", "bank_id"])
bank["value_date"] = bank.value_date.dt.strftime("%Y-%m-%d")
bank["amount"] = (bank.amount_cents / 100).round(2)
bank[["bank_id", "value_date", "amount", "narrative"]].to_csv(DATA / "bank_statement.csv", index=False)

pd.DataFrame(key, columns=["break_type", "ledger_txn_id", "bank_id", "loan_id", "amount_cents", "_src"]).drop(columns="_src") \
  .to_csv(DATA / "injected_breaks_key.csv", index=False)
print(f"ledger rows: {len(led):,} | bank rows: {len(bank):,} | injected: {pd.Series([k[0] for k in key]).value_counts().to_dict()}")
