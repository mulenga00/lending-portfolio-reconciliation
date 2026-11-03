"""Run the whole project end to end:  python run_all.py   (about a minute)."""
import subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parent
for step in ["generate_portfolio", "generate_ledgers", "run_pipeline", "build_dashboard", "build_exceptions_report", "make_charts"]:
    print(f"\n=== {step} ===")
    subprocess.run([sys.executable, str(root / "src" / f"{step}.py")], check=True)
print("\nDone. Open excel/Lending_Portfolio_Dashboard.xlsx and reports/Reconciliation_Exceptions_Report.xlsx")
