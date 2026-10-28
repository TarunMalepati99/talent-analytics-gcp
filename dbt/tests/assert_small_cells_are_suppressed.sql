-- Privacy guardrail: no segment below the minimum cell size may expose leavers or rates.
select segment_key
from {{ ref('fct_attrition_segments') }}
where headcount < {{ var('min_cell_size') }}
  and (leavers is not null or attrition_rate is not null or avg_monthly_income is not null)
