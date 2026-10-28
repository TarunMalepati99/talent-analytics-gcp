-- Adverse-impact check on model outputs (the "four-fifths rule" used in US
-- employment-selection guidance): for each protected attribute, the group flagged
-- high-risk least often divided by the group flagged most often. A ratio < 0.8
-- means the model treats groups very differently and needs review before anyone
-- acts on its scores. Groups under min_cell_size are ignored.
CREATE OR REPLACE TABLE `{{ params.project }}.ml.attrition_fairness_audit` AS
WITH scored AS (
  SELECT s.risk_band, d.gender, d.age_band
  FROM `{{ params.project }}.ml.attrition_risk_scores` s
  JOIN `{{ params.project }}.people_marts.dim_employee` d USING (employee_key)
),
by_group AS (
  SELECT 'gender' AS attribute, gender AS grp, COUNT(*) AS n, AVG(IF(risk_band = 'high', 1, 0)) AS flag_rate FROM scored GROUP BY 1, 2
  UNION ALL
  SELECT 'age_band', age_band, COUNT(*), AVG(IF(risk_band = 'high', 1, 0)) FROM scored GROUP BY 1, 2
)
SELECT
  attribute,
  ROUND(SAFE_DIVIDE(MIN(flag_rate), MAX(flag_rate)), 3) AS adverse_impact_ratio,
  ARRAY_AGG(STRUCT(grp, n, ROUND(flag_rate, 3) AS flag_rate)) AS groups,
  CURRENT_TIMESTAMP() AS audited_at
FROM by_group
WHERE n >= {{ params.min_cell_size }}
GROUP BY attribute;
