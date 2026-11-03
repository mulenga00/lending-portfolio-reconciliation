"""
Step 3 - Load the CSVs into SQLite, run the SQL files in order, export result tables.
Usage: python src/run_pipeline.py
"""
import sqlite3, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, SQL, TABLES = ROOT / "data", ROOT / "sql", ROOT / "reports" / "tables"
DB = ROOT / "data" / "lending.db"
TABLES.mkdir(parents=True, exist_ok=True)

if DB.exists():
    DB.unlink()
con = sqlite3.connect(DB)

# create the typed, empty input tables first (00_create_tables.sql drops and recreates them), then load the CSVs into them
con.executescript((SQL / "00_create_tables.sql").read_text())
print("ran 00_create_tables.sql")

# raw loan file stays all-text on purpose: cleaning is done (and logged) in SQL
pd.read_csv(DATA / "loans_raw.csv", dtype=str, keep_default_na=False).to_sql("stg_loans_raw", con, index=False, if_exists="append")
pd.read_csv(DATA / "monthly_performance.csv", keep_default_na=False).replace({"event": {"": ""}}).to_sql("performance", con, index=False, if_exists="append")
pd.read_csv(DATA / "recoveries.csv").to_sql("recoveries", con, index=False, if_exists="append")
pd.read_csv(DATA / "servicing_ledger.csv").to_sql("ledger", con, index=False, if_exists="append")
pd.read_csv(DATA / "bank_statement.csv").to_sql("bank", con, index=False, if_exists="append")
pd.read_csv(DATA / "injected_breaks_key.csv").to_sql("injected_key", con, index=False, if_exists="append")

for f in sorted(SQL.glob("0*.sql")):
    if f.name.startswith("00"):
        continue  # already run above, before loading the data
    con.executescript(f.read_text())
    print(f"ran {f.name}")
con.commit()

for t in ["dq_log", "kpi_grade", "profitability_grade", "vintage_curve", "roll_rates", "roll_current_to_30_by_grade",
          "recon_results", "recon_rule_summary", "recon_totals", "eval_summary", "eval_unexplained"]:
    pd.read_sql(f"SELECT * FROM {t}", con).to_csv(TABLES / f"{t}.csv", index=False)
print("exported tables ->", TABLES)
con.close()
