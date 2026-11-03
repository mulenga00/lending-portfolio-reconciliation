-- =====================================================================
-- 00_create_tables.sql : create the empty input tables (run this FIRST, then import the CSVs)
-- Column types matter: SQLite would otherwise import every column as text and sort numbers wrongly.
-- Import each CSV from data/ into the table of the same purpose (header row = skip 1 row):
--   loans_raw.csv            -> stg_loans_raw
--   monthly_performance.csv  -> performance
--   recoveries.csv           -> recoveries
--   servicing_ledger.csv     -> ledger
--   bank_statement.csv       -> bank
--   injected_breaks_key.csv  -> injected_key
-- =====================================================================
DROP TABLE IF EXISTS stg_loans_raw;
CREATE TABLE stg_loans_raw (            -- all TEXT on purpose: cleaning happens in 01_validation.sql
  loan_id TEXT, grade TEXT, issue_d TEXT, term TEXT, int_rate TEXT, loan_amnt TEXT, installment TEXT, purpose TEXT,
  home_ownership TEXT, annual_inc TEXT, dti TEXT, addr_state TEXT, pmt_due_day TEXT);

DROP TABLE IF EXISTS performance;
CREATE TABLE performance (
  loan_id TEXT, period_no INTEGER, period_end TEXT, opening_balance REAL, scheduled_payment REAL, paid_amount REAL,
  interest_paid REAL, principal_paid REAL, closing_balance REAL, missed_installments INTEGER, dpd_bucket TEXT,
  event TEXT, chargeoff_amount REAL);

DROP TABLE IF EXISTS recoveries;
CREATE TABLE recoveries (loan_id TEXT, recovery_date TEXT, recovery_amount REAL);

DROP TABLE IF EXISTS ledger;
CREATE TABLE ledger (txn_id TEXT, loan_id TEXT, posting_date TEXT, amount REAL, method TEXT);

DROP TABLE IF EXISTS bank;
CREATE TABLE bank (bank_id TEXT, value_date TEXT, amount REAL, narrative TEXT);

DROP TABLE IF EXISTS injected_key;
CREATE TABLE injected_key (break_type TEXT, ledger_txn_id TEXT, bank_id TEXT, loan_id TEXT, amount_cents INTEGER);
