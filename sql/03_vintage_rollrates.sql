-- =====================================================================
-- 03_vintage_rollrates.sql : vintage loss curves and delinquency roll rates
-- =====================================================================
DROP TABLE IF EXISTS mob_grid;
CREATE TABLE mob_grid AS
WITH RECURSIVE g(m) AS (SELECT 1 UNION ALL SELECT m + 1 FROM g WHERE m < 60) SELECT m FROM g;

-- Cumulative charge-off (% of originated principal) by months-on-book, per origination year.
-- Only loans that have actually reached month m are counted (right-censoring control), and a point is shown
-- only while at least 50% of the vintage's originated principal is observable at that age.
DROP TABLE IF EXISTS vintage_curve;
CREATE TABLE vintage_curve AS
WITH tot AS (SELECT vintage, SUM(loan_amnt) AS vintage_total FROM loan_outcomes GROUP BY vintage),
curve AS (
  SELECT o.vintage, g.m AS mob,
         SUM(o.loan_amnt) AS exposure,
         SUM(CASE WHEN o.chargeoff_mob IS NOT NULL AND o.chargeoff_mob <= g.m THEN o.chargeoff_amt ELSE 0 END) AS cum_chargeoff
  FROM loan_outcomes o JOIN mob_grid g ON g.m <= o.mob_observable
  GROUP BY o.vintage, g.m
)
SELECT c.vintage, c.mob, c.exposure, c.cum_chargeoff
FROM curve c JOIN tot t ON t.vintage = c.vintage
WHERE c.exposure >= 0.5 * t.vintage_total AND c.mob <= 36
ORDER BY c.vintage, c.mob;

-- Roll-rate matrix: where do loans in bucket X at month t-1 end up at month t?
DROP TABLE IF EXISTS roll_rates;
CREATE TABLE roll_rates AS
WITH t AS (
  SELECT loan_id, period_no, dpd_bucket AS to_bucket,
         LAG(dpd_bucket)     OVER (PARTITION BY loan_id ORDER BY period_no) AS from_bucket,
         LAG(closing_balance) OVER (PARTITION BY loan_id ORDER BY period_no) AS from_balance
  FROM performance
)
SELECT from_bucket, to_bucket, COUNT(*) AS loans, ROUND(SUM(from_balance), 2) AS balance
FROM t
WHERE from_bucket IN ('Current','30','60','90')
GROUP BY from_bucket, to_bucket;

-- Early-warning view: share of loans that roll Current -> 30 days late in a month, by grade
DROP TABLE IF EXISTS roll_current_to_30_by_grade;
CREATE TABLE roll_current_to_30_by_grade AS
WITH t AS (
  SELECT p.loan_id, p.dpd_bucket AS to_bucket,
         LAG(p.dpd_bucket) OVER (PARTITION BY p.loan_id ORDER BY p.period_no) AS from_bucket
  FROM performance p
)
SELECT l.grade,
       SUM(CASE WHEN t.from_bucket = 'Current' THEN 1 ELSE 0 END) AS current_loan_months,
       SUM(CASE WHEN t.from_bucket = 'Current' AND t.to_bucket = '30' THEN 1 ELSE 0 END) AS rolled_to_30
FROM t JOIN loans l ON l.loan_id = t.loan_id
GROUP BY l.grade ORDER BY l.grade;
