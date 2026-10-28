-- Evaluation on the held-out 20% (the is_eval = TRUE rows). Results are written to a
-- table so the dashboard can show model health and the DAG can gate on AUC.
CREATE OR REPLACE TABLE `{{ params.project }}.ml.attrition_model_evaluation` AS
SELECT
  CURRENT_TIMESTAMP() AS evaluated_at,
  'attrition_risk_v1' AS model_name,
  *
FROM ML.EVALUATE(MODEL `{{ params.project }}.ml.attrition_risk_v1`);
