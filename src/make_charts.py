"""Step 5 - PNG charts for the README (reports/charts/)."""
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
T, C = ROOT / "reports" / "tables", ROOT / "reports" / "charts"
C.mkdir(parents=True, exist_ok=True)
NAVY, TEAL, ORANGE, GREY = "#1F3864", "#2E75B6", "#ED7D31", "#A6A6A6"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})

p = pd.read_csv(T / "profitability_grade.csv")
p["co"] = p.chargeoff_loans / p.loans
p["nar"] = (p.interest_collected + p.recoveries - p.chargeoff_principal) / (p.balance_months / 12)
p["rate"] = p.wavg_rate_pct / 100

fig, ax = plt.subplots(1, 2, figsize=(11, 4))
b = ax[0].bar(p.grade, p.co, color=NAVY); ax[0].bar_label(b, labels=[f"{x:.0%}" for x in p.co], padding=2, fontsize=9)
ax[0].set_title("Charge-off rate by grade (matured cohort)", fontweight="bold"); ax[0].yaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
w = 0.38; xs = range(len(p))
ax[1].bar([x - w / 2 for x in xs], p.rate, w, color=GREY, label="Contractual rate")
ax[1].bar([x + w / 2 for x in xs], p.nar, w, color=ORANGE, label="Realised net annualised return")
ax[1].set_xticks(list(xs)); ax[1].set_xticklabels(p.grade); ax[1].legend(frameon=False, fontsize=9)
ax[1].set_title("Losses erode the extra yield of riskier grades", fontweight="bold"); ax[1].yaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
plt.tight_layout(); plt.savefig(C / "grade_risk_return.png", dpi=150); plt.close()

v = pd.read_csv(T / "vintage_curve.csv"); v["r"] = v.cum_chargeoff / v.exposure
fig, ax = plt.subplots(figsize=(7, 4))
for y, col in zip(sorted(v.vintage.unique()), [NAVY, TEAL, "#70AD47", ORANGE, "#C00000"]):
    d = v[v.vintage == y]; ax.plot(d.mob, d.r, label=str(y), color=col, lw=2)
ax.set_title("Vintage curves: cumulative charge-off by months on book", fontweight="bold")
ax.set_xlabel("Months on book"); ax.yaxis.set_major_formatter(lambda x, _: f"{x:.0%}"); ax.legend(frameon=False, title="Vintage")
plt.tight_layout(); plt.savefig(C / "vintage_curves.png", dpi=150); plt.close()

r = pd.read_csv(T / "recon_results.csv")
order = r.groupby(["exception_class", "exception_type"]).size().reset_index(name="n")
order["o"] = order.exception_class.map({"Break": 0, "Review": 1, "Timing": 2}); order = order.sort_values(["o", "n"])
colors = order.exception_class.map({"Break": "#C00000", "Review": ORANGE, "Timing": GREY})
fig, ax = plt.subplots(figsize=(8, 4))
ax.barh(order.exception_type, order.n, color=colors); ax.invert_yaxis()
for i, n in enumerate(order.n): ax.text(n + 2, i, str(n), va="center", fontsize=9)
ax.set_title("Reconciliation exceptions by type (red = break, orange = review, grey = timing)", fontweight="bold", fontsize=10)
plt.tight_layout(); plt.savefig(C / "recon_exceptions.png", dpi=150); plt.close()
print("charts saved")
