-- =====================================================================
-- 02_portfolio_kpis.sql : one row per loan with its outcome, then grade-level KPIs
-- As-of date of the portfolio snapshot: 2024-06-30
-- =====================================================================
DROP TABLE IF EXISTS loan_outcomes;
CREATE TABLE loan_outcomes AS
WITH agg AS (
  SELECT loan_id,
         COUNT(*)                         AS months_obs,
         SUM(interest_paid)               AS interest_collected,
         SUM(principal_paid)              AS principal_repaid,
         SUM(chargeoff_amount)            AS chargeoff_amt,
         SUM(opening_balance)             AS balance_months,
         MAX(CASE WHEN event = 'Charged Off' THEN period_no END) AS chargeoff_mob
  FROM performance GROUP BY loan_id
), last AS (
  SELECT loan_id, dpd_bucket, closing_balance, event,
         ROW_NUMBER() OVER (PARTITION BY loan_id ORDER BY period_no DESC) AS rn
  FROM performance
), rec AS (
  SELECT loan_id, SUM(recovery_amount) AS recoveries FROM recoveries GROUP BY loan_id
)
SELECT l.*,
       a.months_obs, a.interest_collected, a.principal_repaid, a.chargeoff_amt, a.balance_months, a.chargeoff_mob,
       x.dpd_bucket AS bucket_asof, x.closing_balance AS balance_asof,
       CASE WHEN x.event = 'Fully Paid'   THEN 'Fully Paid'
            WHEN x.event = 'Charged Off'  THEN 'Charged Off'
            WHEN x.dpd_bucket = 'Current' THEN 'Current'
            ELSE 'Late' END AS status_asof,
       COALESCE(r.recoveries, 0) AS recoveries,
       -- months between issue and the 30-Jun-2024 snapshot (used for vintage curves)
       (2024 * 12 + 6) - (CAST(substr(l.issue_date, 1, 4) AS INTEGER) * 12 + CAST(substr(l.issue_date, 6, 2) AS INTEGER)) AS mob_observable
FROM loans l
JOIN agg  a ON a.loan_id = l.loan_id
JOIN last x ON x.loan_id = l.loan_id AND x.rn = 1
LEFT JOIN rec r ON r.loan_id = l.loan_id;

-- Grade-level snapshot (counts and balances only: ratios are computed as formulas in the Excel dashboard)
DROP TABLE IF EXISTS kpi_grade;
CREATE TABLE kpi_grade AS
SELECT grade,
       COUNT(*)                                                    AS loans,
       SUM(loan_amnt)                                              AS originated,
       SUM(loan_amnt * int_rate) / SUM(loan_amnt)                  AS wavg_rate_pct,
       SUM(CASE WHEN status_asof IN ('Current','Late') THEN balance_asof ELSE 0 END) AS outstanding,
       SUM(CASE WHEN bucket_asof IN ('30','60','90','120+') THEN balance_asof ELSE 0 END) AS bal_30plus,
       SUM(CASE WHEN bucket_asof IN ('60','90','120+')      THEN balance_asof ELSE 0 END) AS bal_60plus,
       SUM(CASE WHEN bucket_asof IN ('90','120+')           THEN balance_asof ELSE 0 END) AS bal_90plus,
       SUM(CASE WHEN status_asof = 'Charged Off' THEN 1 ELSE 0 END) AS chargeoff_loans,
       SUM(chargeoff_amt)                                          AS chargeoff_principal,
       SUM(recoveries)                                             AS recoveries
FROM loan_outcomes GROUP BY grade ORDER BY grade;
