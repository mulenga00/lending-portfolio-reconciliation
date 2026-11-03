"""
Step 1 - Generate a synthetic consumer-lending portfolio.

Why synthetic: public lending datasets do not ship with a full monthly servicing
history, and a reconciliation exercise needs transaction-level payments. This script
simulates 12,000 unsecured instalment loans (LendingClub-style fields) with monthly
repayment, delinquency roll, charge-off and recovery behaviour by risk grade.

The patterns are plausible, NOT empirical. Do not quote findings as market evidence.

Outputs (data/):
  loans_raw.csv            origination file, deliberately "dirty" (see sql/01_validation.sql)
  monthly_performance.csv  one row per loan per month while the loan is live
  recoveries.csv           post charge-off recoveries
"""
import numpy as np, pandas as pd
from pathlib import Path

SEED = 42
N_LOANS = 12_000
rng = np.random.default_rng(SEED)
OUT = Path(__file__).resolve().parent.parent / "data"

GRADES = list("ABCDEFG")
GRADE_P = [0.18, 0.30, 0.27, 0.14, 0.07, 0.03, 0.01]
BASE_RATE = dict(zip(GRADES, [7.5, 11.0, 14.5, 18.5, 22.5, 26.5, 29.5]))
LIFETIME_PD = dict(zip(GRADES, [0.05, 0.11, 0.19, 0.26, 0.33, 0.40, 0.44]))   # 36-month base
P_60M = dict(zip(GRADES, [0.15, 0.22, 0.28, 0.35, 0.42, 0.50, 0.55]))
P_MISS = dict(zip(GRADES, [0.004, 0.007, 0.011, 0.016, 0.022, 0.028, 0.035]))  # cure-able late payments
P_PREPAY = dict(zip(GRADES, [0.45, 0.42, 0.38, 0.34, 0.30, 0.26, 0.22]))
VINTAGE_PD_MULT = {2019: 1.00, 2020: 0.80, 2021: 0.90, 2022: 1.20, 2023: 1.35}
VINTAGE_RATE_ADJ = {2019: 0.0, 2020: 0.0, 2021: 0.0, 2022: 1.0, 2023: 2.2}

periods = pd.period_range("2019-01", "2024-06", freq="M")
MEND = [p.end_time.normalize() for p in periods]       # month-end dates
LAST_IDX = len(periods) - 1                             # 2024-06 = as-of month
issue_idx_all = np.arange(0, 54)                        # issued 2019-01 .. 2023-06
w = np.array([1.3 if periods[i].year == 2021 else 0.8 if periods[i].year == 2020 else 1.0 for i in issue_idx_all])
w = w / w.sum()

# ---------------------------------------------------------------- loans
issue_idx = rng.choice(issue_idx_all, size=N_LOANS, p=w)
grade = rng.choice(GRADES, size=N_LOANS, p=GRADE_P)
vint = np.array([periods[i].year for i in issue_idx])
term = np.where(rng.random(N_LOANS) < np.array([P_60M[g] for g in grade]), 60, 36)
rate = np.array([BASE_RATE[g] for g in grade]) + rng.normal(0, 0.8, N_LOANS) \
       + np.array([VINTAGE_RATE_ADJ[v] for v in vint])
rate = np.round(rate, 2)
amt = np.clip(np.round(rng.lognormal(9.4, 0.55, N_LOANS) / 25) * 25, 1000, 40000)
r_m = rate / 1200
inst = np.round(amt * r_m / (1 - (1 + r_m) ** (-term)), 2)
pd_life = np.clip(np.array([LIFETIME_PD[g] for g in grade]) * np.where(term == 60, 1.3, 1.0)
                  * np.array([VINTAGE_PD_MULT[v] for v in vint]), 0, 0.8)

loans = pd.DataFrame({
    "loan_id": [f"L{i:07d}" for i in range(1, N_LOANS + 1)],
    "issue_idx": issue_idx, "grade": grade, "term": term, "int_rate": rate,
    "loan_amnt": amt, "installment": inst,
    "purpose": rng.choice(["debt_consolidation", "credit_card", "home_improvement", "other", "major_purchase", "medical"],
                          size=N_LOANS, p=[.46, .22, .09, .12, .06, .05]),
    "home_ownership": rng.choice(["RENT", "MORTGAGE", "OWN"], size=N_LOANS, p=[.42, .48, .10]),
    "annual_inc": np.round(rng.lognormal(11.0, 0.5, N_LOANS), -2),
    "dti": np.round(np.clip(rng.normal(18, 8, N_LOANS), 0, 45), 2),
    "addr_state": rng.choice(["CA", "TX", "NY", "FL", "IL", "PA", "OH", "GA", "NC", "MI"], size=N_LOANS),
    "pmt_due_day": rng.integers(1, 29, N_LOANS),
    "pd_life": pd_life,
})

# ------------------------------------------------------------ monthly simulation
perf_rows, recov_rows = [], []
for row in loans.itertuples(index=False):
    r = row.int_rate / 1200
    bal, accrued, arrears = float(row.loan_amnt), 0.0, 0
    inst_, term_, g = row.installment, row.term, row.grade
    will_default = rng.random() < row.pd_life
    md = int(np.clip(round(rng.gamma(3.5, 4.0) + 5), 6, term_)) if will_default else None
    s = md - 3 if will_default else None                 # first missed payment (charge-off 4 misses later)
    prepay_m = None
    if not will_default and rng.random() < P_PREPAY[g]:
        prepay_m = int(rng.uniform(0.35, 0.9) * term_)
    for t in range(1, term_ + 5):
        idx = row.issue_idx + t
        if idx > LAST_IDX:
            break
        opening = bal
        accrued += bal * r
        owed = bal + accrued
        sched = round(min(inst_, owed), 2)
        # ---- payment decision
        if will_default:
            amount = 0.0 if t >= s else min(inst_, owed)
        elif prepay_m is not None and t == prepay_m:
            amount = owed
        elif arrears > 0:
            cure = rng.random() < 0.70 or arrears >= 2
            amount = min(inst_ * (arrears + 1), owed) if cure else 0.0
        else:
            amount = 0.0 if rng.random() < P_MISS[g] else min(inst_, owed)
        if amount > 0 and 0 < owed - amount <= 1.0:      # absorb sub-$1 residuals into the final payoff (no dust payments)
            amount = owed
        int_paid = min(amount, accrued)
        accrued -= int_paid
        prin_paid = min(amount - int_paid, bal)
        bal -= prin_paid
        arrears = arrears + 1 if amount == 0 else 0
        event, co_amt = "", 0.0
        if will_default and arrears >= 4:
            event, co_amt = "Charged Off", bal
            bal = 0.0
            rec = co_amt * rng.uniform(0.06, 0.18)
            rec_idx = idx + 6
            if rec_idx <= LAST_IDX:
                recov_rows.append((row.loan_id, MEND[rec_idx].date().isoformat(), round(rec, 2)))
        elif bal <= 0.005 and accrued <= 0.005:
            event, bal = "Fully Paid", 0.0
        if event == "Fully Paid":
            bucket = "Paid"
        elif event == "Charged Off":
            bucket = "Charged Off"
        else:
            bucket = {0: "Current", 1: "30", 2: "60", 3: "90"}.get(arrears, "120+")
        perf_rows.append((row.loan_id, t, MEND[idx].date().isoformat(), round(opening, 2), sched, round(amount, 2),
                          round(int_paid, 2), round(prin_paid, 2), round(bal, 2), arrears, bucket, event, round(co_amt, 2)))
        if event:
            break

perf = pd.DataFrame(perf_rows, columns=["loan_id", "period_no", "period_end", "opening_balance", "scheduled_payment",
                                        "paid_amount", "interest_paid", "principal_paid", "closing_balance",
                                        "missed_installments", "dpd_bucket", "event", "chargeoff_amount"])
recov = pd.DataFrame(recov_rows, columns=["loan_id", "recovery_date", "recovery_amount"])

# ------------------------------------------------------------ raw (dirty) origination file
raw = loans.drop(columns=["issue_idx", "pd_life"]).copy()
mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
raw.insert(2, "issue_d", [f"{mon[periods[i].month - 1]}-{periods[i].year}" for i in loans.issue_idx])
raw["term"] = raw["term"].map(lambda x: f" {x} months")
raw["int_rate"] = raw["int_rate"].map(lambda x: f"{x:.2f}%")
n = len(raw)
bad_grade = rng.choice(n, int(n * 0.005), replace=False)
raw.loc[raw.index[bad_grade], "grade"] = raw.iloc[bad_grade]["grade"].str.lower() + " "      # format noise
raw.loc[raw.index[rng.choice(n, int(n * 0.012), replace=False)], "annual_inc"] = np.nan      # missing income
raw.loc[raw.index[rng.choice(n, int(n * 0.004), replace=False)], "dti"] = 999                # impossible DTI
raw = pd.concat([raw, raw.sample(int(n * 0.006), random_state=SEED)]).sample(frac=1, random_state=SEED)  # duplicates

OUT.mkdir(exist_ok=True)
raw.to_csv(OUT / "loans_raw.csv", index=False)
perf.to_csv(OUT / "monthly_performance.csv", index=False)
recov.to_csv(OUT / "recoveries.csv", index=False)
print(f"loans_raw: {len(raw):,} rows | monthly_performance: {len(perf):,} rows | recoveries: {len(recov):,} rows")
