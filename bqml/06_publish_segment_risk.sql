-- Runs only after the fairness gate passes (see the DAG). Publishes segment-level risk
-- to the people marts; small cells are suppressed like every other people mart.
CREATE OR REPLACE TABLE `{{ params.project }}.people_marts.attrition_risk_by_segment` AS
SELECT
  department,
  job_role,
  tenure_band,
  COUNT(*)                                                                      AS employees_scored,
  IF(COUNT(*) >= {{ params.min_cell_size }}, ROUND(AVG(attrition_probability), 3), NULL) AS avg_risk,
  IF(COUNT(*) >= {{ params.min_cell_size }}, COUNTIF(risk_band = 'high'), NULL)         AS high_risk_employees
FROM `{{ params.project }}.ml.attrition_risk_scores`
GROUP BY 1, 2, 3;
