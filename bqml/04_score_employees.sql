-- Score current employees only (people who already left are history, not risk).
-- Individual scores stay in the restricted ml dataset. HR business partners only get
-- the segment rollup (06_publish_segment_risk.sql), and only after the fairness gate passes.
CREATE OR REPLACE TABLE `{{ params.project }}.ml.attrition_risk_scores` AS
SELECT
  p.employee_key,
  p.department,
  p.job_role,
  p.tenure_band,
  prob.prob                                            AS attrition_probability,
  CASE WHEN prob.prob >= 0.70 THEN 'high'
       WHEN prob.prob >= 0.40 THEN 'medium'
       ELSE 'low' END                                  AS risk_band,
  CURRENT_TIMESTAMP()                                  AS scored_at
FROM ML.PREDICT(
  MODEL `{{ params.project }}.ml.attrition_risk_v1`,
  (
    -- Same feature casts as training, plus pass-through columns for the output.
    SELECT
      employee_key, tenure_band,
      department, job_role, CAST(job_level AS STRING) AS job_level,
      years_at_company, years_since_last_promotion, works_overtime, business_travel,
      CAST(pay_quartile_in_level AS STRING) AS pay_quartile_in_level,
      CAST(stock_option_level AS STRING) AS stock_option_level,
      job_satisfaction, environment_satisfaction, work_life_balance
    FROM `{{ params.project }}.people_marts.dim_employee`
    WHERE NOT is_attrited
  )
) AS p,
UNNEST(p.predicted_is_attrited_probs) AS prob
WHERE prob.label = TRUE;
