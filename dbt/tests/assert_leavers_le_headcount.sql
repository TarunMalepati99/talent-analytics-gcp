select factor, factor_level
from {{ ref('mart_attrition_drivers') }}
where leavers > headcount
