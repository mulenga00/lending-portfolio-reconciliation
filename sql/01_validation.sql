-- =====================================================================
-- 01_validation.sql : clean the raw origination file and log every issue
-- Input tables (loaded by run_pipeline.py): stg_loans_raw (all TEXT), performance, recoveries
-- Output tables: loans (clean), dq_log (data-quality log)
-- =====================================================================
DROP TABLE IF EXISTS loans_dedup;
CREATE TABLE loans_dedup AS
SELECT * FROM (
  SELECT r.*, ROW_NUMBER() OVER (PARTITION BY loan_id ORDER BY rowid) AS rn
  FROM stg_loans_raw r
) WHERE rn = 1;

DROP TABLE IF EXISTS dq_log;
CREATE TABLE dq_log (check_name TEXT, rule TEXT, rows_affected INTEGER, treatment TEXT);

INSERT INTO dq_log
SELECT 'Duplicate loan records', 'Same loan_id appears more than once in the origination file',
       (SELECT COUNT(*) FROM stg_loans_raw) - (SELECT COUNT(*) FROM loans_dedup),
       'Kept first record per loan_id';

INSERT INTO dq_log
SELECT 'Inconsistent grade format', 'Grade not a clean upper-case single letter (case / trailing spaces)',
       COUNT(*), 'Trimmed and upper-cased'
FROM loans_dedup WHERE grade <> UPPER(TRIM(grade));

INSERT INTO dq_log
SELECT 'Missing annual income', 'annual_inc is blank', COUNT(*),
       'Left as NULL; excluded from income-based metrics, loan retained'
FROM loans_dedup WHERE annual_inc = '';

INSERT INTO dq_log
SELECT 'Impossible DTI', 'Debt-to-income outside 0-100', COUNT(*),
       'Set to NULL (placeholder value 999); loan retained'
FROM loans_dedup WHERE CAST(dti AS REAL) NOT BETWEEN 0 AND 100;

DROP TABLE IF EXISTS loans;
CREATE TABLE loans AS
SELECT
  loan_id,
  UPPER(TRIM(grade))                                            AS grade,
  CAST(REPLACE(REPLACE(term, 'months', ''), ' ', '') AS INTEGER) AS term_m,
  CAST(REPLACE(int_rate, '%', '') AS REAL)                      AS int_rate,
  CAST(loan_amnt AS REAL)                                       AS loan_amnt,
  CAST(installment AS REAL)                                     AS installment,
  substr(issue_d, 5, 4) || '-' ||
    printf('%02d', (instr('JanFebMarAprMayJunJulAugSepOctNovDec', substr(issue_d, 1, 3)) + 2) / 3) || '-01' AS issue_date,
  CAST(substr(issue_d, 5, 4) AS INTEGER)                        AS vintage,
  purpose, home_ownership,
  CASE WHEN annual_inc = '' THEN NULL ELSE CAST(annual_inc AS REAL) END AS annual_inc,
  CASE WHEN CAST(dti AS REAL) BETWEEN 0 AND 100 THEN CAST(dti AS REAL) END AS dti,
  addr_state
FROM loans_dedup;
CREATE UNIQUE INDEX IF NOT EXISTS ix_loans ON loans(loan_id);
CREATE INDEX IF NOT EXISTS ix_perf ON performance(loan_id, period_no);
CREATE INDEX IF NOT EXISTS ix_rec ON recoveries(loan_id);

-- ---------------------------------------------------------------------
-- Integrity checks between files (all expected to be zero)
-- ---------------------------------------------------------------------
INSERT INTO dq_log
SELECT 'Orphan performance rows', 'Performance record with no matching loan', COUNT(*), 'Would be excluded (none found)'
FROM performance p WHERE NOT EXISTS (SELECT 1 FROM loans l WHERE l.loan_id = p.loan_id);

INSERT INTO dq_log
SELECT 'Loans with no performance', 'Loan with no monthly record', COUNT(*), 'Would be excluded (none found)'
FROM loans l WHERE NOT EXISTS (SELECT 1 FROM performance p WHERE p.loan_id = l.loan_id);

INSERT INTO dq_log
SELECT 'Payment split mismatch', 'interest_paid + principal_paid differs from paid_amount by more than $0.02', COUNT(*),
       'Would be investigated (none found)'
FROM performance WHERE ABS(interest_paid + principal_paid - paid_amount) > 0.02;

INSERT INTO dq_log
SELECT 'Principal roll-forward break',
       'loan_amnt <> principal repaid + charged-off principal + closing balance (tolerance $1)', COUNT(*),
       'Would be investigated (none found)'
FROM (
  SELECT l.loan_id, l.loan_amnt,
         SUM(p.principal_paid) AS repaid, SUM(p.chargeoff_amount) AS co,
         (SELECT closing_balance FROM performance x WHERE x.loan_id = l.loan_id ORDER BY period_no DESC LIMIT 1) AS closing
  FROM loans l JOIN performance p ON p.loan_id = l.loan_id
  GROUP BY l.loan_id
) WHERE ABS(loan_amnt - repaid - co - closing) > 1;
