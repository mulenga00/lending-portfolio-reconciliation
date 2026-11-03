-- =====================================================================
-- 04_profitability.sql : realised profitability by grade on a MATURED cohort
--
-- Why a matured cohort: loans issued recently have not had time to default, so including them flatters
-- the riskier grades. We therefore use 36-month loans issued Jan-2019 to Mar-2021, which have run their
-- full term (plus a 3-month buffer for cured late payments) by the 30-Jun-2024 snapshot.
-- =====================================================================
DROP TABLE IF EXISTS profitability_grade;
CREATE TABLE profitability_grade AS
SELECT grade,
       COUNT(*)                                                   AS loans,
       SUM(loan_amnt)                                             AS originated,
       SUM(loan_amnt * int_rate) / SUM(loan_amnt)                 AS wavg_rate_pct,
       SUM(CASE WHEN status_asof = 'Charged Off' THEN 1 ELSE 0 END) AS chargeoff_loans,
       SUM(chargeoff_amt)                                         AS chargeoff_principal,
       SUM(interest_collected)                                    AS interest_collected,
       SUM(recoveries)                                            AS recoveries,
       SUM(balance_months)                                        AS balance_months
FROM loan_outcomes
WHERE term_m = 36 AND issue_date <= '2021-03-31'
GROUP BY grade ORDER BY grade;
