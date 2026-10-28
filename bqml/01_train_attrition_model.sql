-- Attrition-risk model (BigQuery ML logistic regression).
-- Rendered by Airflow: {{ params.project }} comes from the DAG.
--
-- Design choices:
--  * Protected attributes (age, gender, marital status) are NOT features. They are
--    used only in 05_fairness_audit.sql to check the model's outputs.
--  * Deterministic 80/20 split on a hash of employee_key, so re-training on the same
--    data evaluates on the same people (RANDOM splits drift run to run).
--  * auto_class_weights balances the ~16% positive class.
--  * The training service account needs Fine-Grained Reader on the compensation
--    policy tag (granted in Terraform) because pay quartile/stock level are features.
CREATE OR REPLACE MODEL `{{ params.project }}.ml.attrition_risk_v1`
OPTIONS (
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['is_attrited'],
  auto_class_weights = TRUE,
  data_split_method = 'CUSTOM',
  data_split_col = 'is_eval',
  enable_global_explain = TRUE,
  l2_reg = 1.0
) AS
SELECT
  department,
  job_role,
  CAST(job_level AS STRING)            AS job_level,
  years_at_company,
  years_since_last_promotion,
  works_overtime,
  business_travel,
  CAST(pay_quartile_in_level AS STRING) AS pay_quartile_in_level,
  CAST(stock_option_level AS STRING)   AS stock_option_level,
  job_satisfaction,
  environment_satisfaction,
  work_life_balance,
  is_attrited,
  MOD(ABS(FARM_FINGERPRINT(employee_key)), 5) = 0 AS is_eval
FROM `{{ params.project }}.people_marts.dim_employee`;
