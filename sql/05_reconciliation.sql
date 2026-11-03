-- =====================================================================
-- 05_reconciliation.sql : Q2-2024 cash reconciliation, servicing ledger vs bank statement
--
-- Method: a rule waterfall. Each rule only sees items the previous rules did not match, and pairing is
-- one-to-one (nearest date wins), so a duplicated ledger posting cannot "steal" the same bank line twice.
--   R1 exact           same loan ref, identical amount, bank date 0-5 days after ledger date (ACH)
--   R2 card fee        same loan ref, bank amount = ledger amount net of the card fee schedule
--   R3 amount variance same loan ref and date window but amounts differ (<=90%)      -> EXCEPTION
--   R4 misapplied      bank ref and ledger loan differ, amount and date agree          -> EXCEPTION
--   R5 fuzzy           bank reference unreadable; unique amount + date candidate        -> REVIEW
-- Everything still unmatched is classified by cause (duplicate, timing, missing cash, ...).
-- Tables expected: ledger (txn_id, loan_id, posting_date, amount, method), bank (bank_id, value_date, amount, narrative)
-- =====================================================================
DROP TABLE IF EXISTS recon_params;
CREATE TABLE recon_params (period_start TEXT, period_end TEXT, fee_pct REAL, fee_flat_cents INTEGER,
                           date_window_days INTEGER, fee_tol_cents INTEGER, amount_var_pct REAL, cutoff_days INTEGER);
INSERT INTO recon_params VALUES ('2024-04-01', '2024-06-30', 0.015, 20, 5, 2, 0.90, 5);

-- ---- staging: amounts in integer cents, loan reference parsed out of the free-text bank narrative
DROP TABLE IF EXISTS ledger_stg;
CREATE TABLE ledger_stg AS
SELECT txn_id, loan_id, posting_date, CAST(ROUND(amount * 100) AS INTEGER) AS amount_cents, method FROM ledger;
CREATE INDEX ix_ls_loan ON ledger_stg(loan_id);

DROP TABLE IF EXISTS bank_stg;
CREATE TABLE bank_stg AS
SELECT bank_id, value_date, CAST(ROUND(amount * 100) AS INTEGER) AS amount_cents, narrative,
       CASE WHEN instr(narrative, 'REF:') > 0
             AND substr(narrative, instr(narrative, 'REF:') + 4, 8) GLOB 'L[0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
            THEN substr(narrative, instr(narrative, 'REF:') + 4, 8) END AS ref_loan_id,
       CASE WHEN amount < 0 OR narrative LIKE '%RETURN%' THEN 1 ELSE 0 END AS is_return
FROM bank;
CREATE INDEX ix_bs_ref ON bank_stg(ref_loan_id);

DROP TABLE IF EXISTS matches;
CREATE TABLE matches (ledger_txn_id TEXT, bank_id TEXT, rule TEXT, confidence TEXT, variance_cents INTEGER);
CREATE INDEX ix_m_l ON matches(ledger_txn_id);
CREATE INDEX ix_m_b ON matches(bank_id);

-- ---------------------------------------------------------------------
-- R1 exact
-- ---------------------------------------------------------------------
CREATE TEMP TABLE cand AS
SELECT l.txn_id, b.bank_id, julianday(b.value_date) - julianday(l.posting_date) AS dd, l.amount_cents - b.amount_cents AS var
FROM ledger_stg l
JOIN bank_stg b ON b.ref_loan_id = l.loan_id AND b.amount_cents = l.amount_cents AND b.is_return = 0
CROSS JOIN recon_params p
WHERE l.method = 'ACH'
  AND julianday(b.value_date) - julianday(l.posting_date) BETWEEN 0 AND p.date_window_days;
INSERT INTO matches
SELECT txn_id, bank_id, 'R1_EXACT', 'High', var FROM (
  SELECT c.*, ROW_NUMBER() OVER (PARTITION BY bank_id ORDER BY dd, txn_id) AS rb
  FROM (SELECT cand.*, ROW_NUMBER() OVER (PARTITION BY txn_id ORDER BY dd, bank_id) AS rl FROM cand) c WHERE rl = 1
) WHERE rb = 1;
DROP TABLE cand;

-- ---------------------------------------------------------------------
-- R2 card payments settle net of fee: expected bank amount = ledger * (1 - fee%) - flat fee
-- ---------------------------------------------------------------------
CREATE TEMP TABLE cand AS
SELECT l.txn_id, b.bank_id, julianday(b.value_date) - julianday(l.posting_date) AS dd, l.amount_cents - b.amount_cents AS var
FROM ledger_stg l
JOIN bank_stg b ON b.ref_loan_id = l.loan_id AND b.is_return = 0
CROSS JOIN recon_params p
WHERE l.method = 'CARD'
  AND l.txn_id NOT IN (SELECT ledger_txn_id FROM matches)
  AND ABS(b.amount_cents - CAST(ROUND(l.amount_cents * (1 - p.fee_pct) - p.fee_flat_cents) AS INTEGER)) <= p.fee_tol_cents
  AND julianday(b.value_date) - julianday(l.posting_date) BETWEEN 0 AND p.date_window_days;
INSERT INTO matches
SELECT txn_id, bank_id, 'R2_CARD_FEE', 'High', var FROM (
  SELECT c.*, ROW_NUMBER() OVER (PARTITION BY bank_id ORDER BY dd, txn_id) AS rb
  FROM (SELECT cand.*, ROW_NUMBER() OVER (PARTITION BY txn_id ORDER BY dd, bank_id) AS rl FROM cand) c WHERE rl = 1
) WHERE rb = 1;
DROP TABLE cand;

-- ---------------------------------------------------------------------
-- R3 same loan and date window, amounts disagree (within tolerance)  -> amount mismatch exception
-- ---------------------------------------------------------------------
CREATE TEMP TABLE cand AS
SELECT l.txn_id, b.bank_id, julianday(b.value_date) - julianday(l.posting_date) AS dd, l.amount_cents - b.amount_cents AS var
FROM ledger_stg l
JOIN bank_stg b ON b.ref_loan_id = l.loan_id AND b.is_return = 0
CROSS JOIN recon_params p
WHERE l.txn_id NOT IN (SELECT ledger_txn_id FROM matches)
  AND b.bank_id NOT IN (SELECT bank_id FROM matches)
  AND ABS(l.amount_cents - b.amount_cents) <= p.amount_var_pct * l.amount_cents
  AND julianday(b.value_date) - julianday(l.posting_date) BETWEEN 0 AND p.date_window_days;
INSERT INTO matches
SELECT txn_id, bank_id, 'R3_AMOUNT_VARIANCE', 'Exception', var FROM (
  SELECT c.*, ROW_NUMBER() OVER (PARTITION BY bank_id ORDER BY dd, txn_id) AS rb
  FROM (SELECT cand.*, ROW_NUMBER() OVER (PARTITION BY txn_id ORDER BY dd, bank_id) AS rl FROM cand) c WHERE rl = 1
) WHERE rb = 1;
DROP TABLE cand;

-- ---------------------------------------------------------------------
-- R4 misapplied: bank reference names loan X, ledger posted the same cash to loan Y
-- ---------------------------------------------------------------------
CREATE TEMP TABLE cand AS
SELECT l.txn_id, b.bank_id, julianday(b.value_date) - julianday(l.posting_date) AS dd, 0 AS var
FROM ledger_stg l
JOIN bank_stg b ON b.amount_cents = l.amount_cents AND b.ref_loan_id IS NOT NULL AND b.ref_loan_id <> l.loan_id AND b.is_return = 0
CROSS JOIN recon_params p
WHERE l.method = 'ACH'
  AND l.txn_id NOT IN (SELECT ledger_txn_id FROM matches)
  AND b.bank_id NOT IN (SELECT bank_id FROM matches)
  AND julianday(b.value_date) - julianday(l.posting_date) BETWEEN 0 AND p.date_window_days;
INSERT INTO matches
SELECT txn_id, bank_id, 'R4_MISAPPLIED', 'Exception', var FROM (
  SELECT c.*, ROW_NUMBER() OVER (PARTITION BY bank_id ORDER BY dd, txn_id) AS rb
  FROM (SELECT cand.*, ROW_NUMBER() OVER (PARTITION BY txn_id ORDER BY dd, bank_id) AS rl FROM cand) c WHERE rl = 1
) WHERE rb = 1;
DROP TABLE cand;

-- ---------------------------------------------------------------------
-- R5 fuzzy: bank narrative has no usable loan reference. Accept only if the amount+date candidate is unique both ways.
-- ---------------------------------------------------------------------
CREATE TEMP TABLE cand AS
SELECT l.txn_id, b.bank_id, julianday(b.value_date) - julianday(l.posting_date) AS dd, l.amount_cents - b.amount_cents AS var
FROM ledger_stg l
JOIN bank_stg b ON b.ref_loan_id IS NULL AND b.is_return = 0
CROSS JOIN recon_params p
WHERE l.txn_id NOT IN (SELECT ledger_txn_id FROM matches)
  AND b.bank_id NOT IN (SELECT bank_id FROM matches)
  AND julianday(b.value_date) - julianday(l.posting_date) BETWEEN 0 AND p.date_window_days
  AND ( (l.method = 'ACH'  AND b.amount_cents = l.amount_cents)
     OR (l.method = 'CARD' AND ABS(b.amount_cents - CAST(ROUND(l.amount_cents * (1 - p.fee_pct) - p.fee_flat_cents) AS INTEGER)) <= p.fee_tol_cents) );
INSERT INTO matches
SELECT txn_id, bank_id, 'R5_FUZZY_AMT_DATE', 'Low', var FROM (
  SELECT c.*, COUNT(*) OVER (PARTITION BY bank_id) AS cb, COUNT(*) OVER (PARTITION BY txn_id) AS cl FROM cand c
) WHERE cb = 1 AND cl = 1;
DROP TABLE cand;

-- =====================================================================
-- Exceptions register
-- =====================================================================
DROP TABLE IF EXISTS recon_results;
CREATE TABLE recon_results (
  item_id INTEGER PRIMARY KEY AUTOINCREMENT, side TEXT, ledger_txn_id TEXT, bank_id TEXT, loan_id TEXT, item_date TEXT,
  ledger_cents INTEGER, bank_cents INTEGER, variance_cents INTEGER, exception_type TEXT, exception_class TEXT,
  root_cause TEXT, recommended_action TEXT, owner TEXT, priority TEXT, age_days INTEGER);

-- (a) matched pairs that still need attention
INSERT INTO recon_results (side, ledger_txn_id, bank_id, loan_id, item_date, ledger_cents, bank_cents, variance_cents,
                           exception_type, exception_class, root_cause, recommended_action, owner, priority, age_days)
SELECT 'MATCHED PAIR', l.txn_id, b.bank_id, l.loan_id, l.posting_date, l.amount_cents, b.amount_cents, m.variance_cents,
  CASE m.rule WHEN 'R3_AMOUNT_VARIANCE' THEN 'Amount mismatch'
              WHEN 'R4_MISAPPLIED'      THEN 'Misapplied payment'
              ELSE 'Reference unreadable - confirm match' END,
  CASE m.rule WHEN 'R5_FUZZY_AMT_DATE' THEN 'Review' ELSE 'Break' END,
  CASE m.rule WHEN 'R3_AMOUNT_VARIANCE' THEN 'Ledger amount differs from cash received (likely keying or transposition error)'
              WHEN 'R4_MISAPPLIED'      THEN 'Bank reference ' || b.ref_loan_id || ' but ledger posted to ' || l.loan_id
              ELSE 'Bank narrative has no usable loan reference; paired on amount and date only' END,
  CASE m.rule WHEN 'R3_AMOUNT_VARIANCE' THEN 'Check remittance advice, correct the ledger amount and post the difference'
              WHEN 'R4_MISAPPLIED'      THEN 'Reverse and repost to ' || b.ref_loan_id || '; check late fees on both accounts'
              ELSE 'Confirm payer from remittance and record the reference mapping' END,
  CASE m.rule WHEN 'R3_AMOUNT_VARIANCE' THEN 'Loan Servicing' ELSE 'Cash Applications' END,
  CASE m.rule WHEN 'R4_MISAPPLIED' THEN 'High'
              WHEN 'R3_AMOUNT_VARIANCE' THEN CASE WHEN ABS(m.variance_cents) >= 500 THEN 'High' ELSE 'Medium' END
              ELSE 'Low' END,
  CAST(julianday(p.period_end) - julianday(l.posting_date) AS INTEGER)
FROM matches m
JOIN ledger_stg l ON l.txn_id = m.ledger_txn_id
JOIN bank_stg   b ON b.bank_id = m.bank_id
CROSS JOIN recon_params p
WHERE m.rule IN ('R3_AMOUNT_VARIANCE', 'R4_MISAPPLIED', 'R5_FUZZY_AMT_DATE');

-- (b) ledger items with no bank counterpart
CREATE TEMP TABLE ledger_open AS
SELECT l.*,
  (SELECT COUNT(*) FROM matches mm JOIN ledger_stg l2 ON l2.txn_id = mm.ledger_txn_id
    WHERE l2.loan_id = l.loan_id AND l2.amount_cents = l.amount_cents
      AND l2.posting_date = l.posting_date AND l2.txn_id <> l.txn_id) AS dup_n,
  CASE WHEN julianday(p.period_end) - julianday(l.posting_date) < p.cutoff_days THEN 1 ELSE 0 END AS at_cutoff,
  CAST(julianday(p.period_end) - julianday(l.posting_date) AS INTEGER) AS age_days
FROM ledger_stg l CROSS JOIN recon_params p
WHERE l.txn_id NOT IN (SELECT ledger_txn_id FROM matches);

INSERT INTO recon_results (side, ledger_txn_id, loan_id, item_date, ledger_cents, exception_type, exception_class,
                           root_cause, recommended_action, owner, priority, age_days)
SELECT 'LEDGER ONLY', txn_id, loan_id, posting_date, amount_cents,
  CASE WHEN dup_n > 0 THEN 'Duplicate posting' WHEN at_cutoff = 1 THEN 'Timing - in transit at cut-off' ELSE 'Posted without bank cash' END,
  CASE WHEN dup_n = 0 AND at_cutoff = 1 THEN 'Timing' ELSE 'Break' END,
  CASE WHEN dup_n > 0 THEN 'Same loan, amount and date already posted and matched to bank cash'
       WHEN at_cutoff = 1 THEN 'Posted in the last days of the period; bank value date falls after period end'
       ELSE 'Ledger shows a payment but no cash reached the bank (failed settlement or posting error)' END,
  CASE WHEN dup_n > 0 THEN 'Reverse the duplicate entry and restore the loan balance'
       WHEN at_cutoff = 1 THEN 'Re-check against next period statement; no action unless still open'
       ELSE 'Trace payment with the processor; reverse posting if cash was not received' END,
  CASE WHEN dup_n > 0 THEN 'Loan Servicing' ELSE 'Treasury' END,
  CASE WHEN dup_n > 0 THEN 'Medium' WHEN at_cutoff = 1 THEN 'Low' ELSE 'High' END,
  age_days
FROM ledger_open;
DROP TABLE ledger_open;

-- (c) bank items with no ledger counterpart
INSERT INTO recon_results (side, bank_id, loan_id, item_date, bank_cents, exception_type, exception_class,
                           root_cause, recommended_action, owner, priority, age_days)
SELECT 'BANK ONLY', b.bank_id, b.ref_loan_id, b.value_date, b.amount_cents,
  CASE WHEN b.is_return = 1 THEN 'Bank return not reflected in ledger'
       WHEN julianday(b.value_date) - julianday(p.period_start) < p.cutoff_days THEN 'Timing - prior-period posting'
       WHEN b.ref_loan_id IS NULL THEN 'Unapplied cash - reference unreadable'
       ELSE 'Cash received, not posted' END,
  CASE WHEN b.is_return = 0 AND julianday(b.value_date) - julianday(p.period_start) < p.cutoff_days THEN 'Timing' ELSE 'Break' END,
  CASE WHEN b.is_return = 1 THEN 'Payment returned by the bank (e.g. NSF) but the ledger still shows the loan as paid'
       WHEN julianday(b.value_date) - julianday(p.period_start) < p.cutoff_days THEN 'Ledger posted in the prior period (March); bank value date falls in this period'
       WHEN b.ref_loan_id IS NULL THEN 'Cash received with no readable loan reference and no unique ledger candidate'
       ELSE 'Cash reached the bank but no ledger posting exists' END,
  CASE WHEN b.is_return = 1 THEN 'Reverse the payment, reinstate arrears and trigger a collections contact'
       WHEN julianday(b.value_date) - julianday(p.period_start) < p.cutoff_days THEN 'Confirm against prior-period reconciliation; no action expected'
       WHEN b.ref_loan_id IS NULL THEN 'Identify the payer from the processor file and apply the cash'
       ELSE 'Post to the loan account and check whether a late fee was charged in error' END,
  CASE WHEN b.is_return = 1 THEN 'Collections'
       WHEN julianday(b.value_date) - julianday(p.period_start) < p.cutoff_days THEN 'Treasury'
       ELSE 'Cash Applications' END,
  CASE WHEN b.is_return = 1 THEN 'High'
       WHEN julianday(b.value_date) - julianday(p.period_start) < p.cutoff_days THEN 'Low'
       WHEN b.ref_loan_id IS NULL THEN 'Medium' ELSE 'High' END,
  CAST(julianday(p.period_end) - julianday(b.value_date) AS INTEGER)
FROM bank_stg b CROSS JOIN recon_params p
WHERE b.bank_id NOT IN (SELECT bank_id FROM matches);

-- =====================================================================
-- Summary tables used by the Excel exceptions report
-- =====================================================================
DROP TABLE IF EXISTS recon_rule_summary;
CREATE TABLE recon_rule_summary AS
SELECT m.rule, COUNT(*) AS pairs, SUM(l.amount_cents) AS ledger_cents, SUM(b.amount_cents) AS bank_cents,
       SUM(m.variance_cents) AS variance_cents
FROM matches m JOIN ledger_stg l ON l.txn_id = m.ledger_txn_id JOIN bank_stg b ON b.bank_id = m.bank_id
GROUP BY m.rule ORDER BY m.rule;

DROP TABLE IF EXISTS recon_totals;
CREATE TABLE recon_totals AS
SELECT 'ledger_items' AS metric, COUNT(*) AS value FROM ledger_stg
UNION ALL SELECT 'ledger_value_cents', SUM(amount_cents) FROM ledger_stg
UNION ALL SELECT 'bank_items', COUNT(*) FROM bank_stg
UNION ALL SELECT 'bank_value_cents', SUM(amount_cents) FROM bank_stg;
