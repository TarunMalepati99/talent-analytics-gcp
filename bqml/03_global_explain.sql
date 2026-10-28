-- Which features move predicted attrition risk most (class-level attributions).
CREATE OR REPLACE TABLE `{{ params.project }}.ml.attrition_feature_importance` AS
SELECT CURRENT_TIMESTAMP() AS explained_at, *
FROM ML.GLOBAL_EXPLAIN(MODEL `{{ params.project }}.ml.attrition_risk_v1`, STRUCT(TRUE AS class_level_explain));
