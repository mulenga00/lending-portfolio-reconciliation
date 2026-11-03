-- =====================================================================
-- 06_evaluation.sql : score the matching engine against the injected-break answer key
-- (only possible because the data is synthetic; in real life nobody hands you the answer key)
-- =====================================================================
DROP TABLE IF EXISTS eval_detail;
CREATE TABLE eval_detail AS
SELECT k.break_type, k.ledger_txn_id, k.bank_id,
  CASE k.break_type
    WHEN 'DUPLICATE_POSTING'  THEN 'Duplicate posting'
    WHEN 'CASH_NOT_POSTED'    THEN 'Cash received, not posted'
    WHEN 'POSTED_NO_CASH'     THEN 'Posted without bank cash'
    WHEN 'AMOUNT_ERROR'       THEN 'Amount mismatch'
    WHEN 'MISAPPLIED'         THEN 'Misapplied payment'
    WHEN 'UNREVERSED_RETURN'  THEN 'Bank return not reflected in ledger'
    WHEN 'UNREADABLE_REF'     THEN 'Reference unreadable - confirm match'
  END AS expected_type,
  (SELECT r.exception_type FROM recon_results r
    WHERE (k.ledger_txn_id IS NOT NULL AND r.ledger_txn_id = k.ledger_txn_id)
       OR (k.ledger_txn_id IS NULL AND k.bank_id IS NOT NULL AND r.bank_id = k.bank_id)
    ORDER BY r.item_id LIMIT 1) AS detected_as
FROM (SELECT break_type, NULLIF(ledger_txn_id, '') AS ledger_txn_id, NULLIF(bank_id, '') AS bank_id FROM injected_key) k;  -- CSV imports turn blanks into '' not NULL

DROP TABLE IF EXISTS eval_summary;
CREATE TABLE eval_summary AS
SELECT break_type, expected_type, COUNT(*) AS injected,
       SUM(CASE WHEN detected_as IS NOT NULL THEN 1 ELSE 0 END) AS flagged,
       SUM(CASE WHEN detected_as = expected_type THEN 1 ELSE 0 END) AS classified_correctly
FROM eval_detail GROUP BY break_type, expected_type ORDER BY break_type;

-- Break-class exceptions that do NOT trace back to an injected item (candidate false positives)
DROP TABLE IF EXISTS eval_unexplained;
CREATE TABLE eval_unexplained AS
SELECT r.* FROM recon_results r
WHERE r.exception_class = 'Break'
  AND NOT EXISTS (SELECT 1 FROM injected_key k WHERE (NULLIF(k.ledger_txn_id, '') = r.ledger_txn_id)
                                                  OR (NULLIF(k.bank_id, '') = r.bank_id));
