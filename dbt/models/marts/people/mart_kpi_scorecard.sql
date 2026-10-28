-- KPI scorecard: one row per KPI x slice (the company, then each department).
--
-- Each KPI's numerator and denominator are defined once here, in SQL, and its
-- name, plain-language definition, direction and target live in the
-- kpi_definitions seed, so the dashboard, the data dictionary and this model
-- read from one source. Targets in the seed are placeholders until agreed with
-- the KPI owner. Slices under the minimum cell size are suppressed.

{% set kpis = [
    ('ATTR_RATE',      'is_attrited',                                         'true'),
    ('EARLY_ATTR',     'is_attrited and years_at_company <= 2',               'years_at_company <= 2'),
    ('FIRST_YEAR_RET', 'not is_attrited and years_at_company < 1',            'years_at_company < 1'),
    ('NEWHIRE_OT',     'works_overtime and years_at_company <= 2',            'years_at_company <= 2'),
    ('PROMO_STALL',    'is_promotion_stalled',                                'true'),
    ('LOW_WLB',        'work_life_balance = 1',                               'true'),
    ('LOW_ENV_SAT',    'environment_satisfaction = 1',                        'true'),
] %}

with e as (
    select *, 'All' as company_slice from {{ ref('int_employees__enriched') }}
),

counts as (
    {% for slice_type, slice_col in [('company', 'company_slice'), ('department', 'department')] %}
    {% set outer_loop = loop %}
    {% for kpi_id, num, den in kpis %}
    select
        '{{ kpi_id }}'                                             as kpi_id,
        '{{ slice_type }}'                                         as slice_type,
        {{ slice_col }}                                            as slice_value,
        sum(case when {{ num }} then 1 else 0 end)                 as numerator,
        sum(case when {{ den }} then 1 else 0 end)                 as denominator
    from e
    group by 1, 2, 3
    {% if not (loop.last and outer_loop.last) %}union all{% endif %}
    {% endfor %}
    {% endfor %}
),

defs as (
    select * from {{ ref('kpi_definitions') }}
)

select
    {{ dbt.hash("concat(counts.kpi_id, '|', counts.slice_type, '|', counts.slice_value)") }} as kpi_row_key,
    counts.kpi_id,
    defs.kpi_name,
    counts.slice_type,
    counts.slice_value,
    counts.denominator < {{ var('min_cell_size') }}                                     as is_suppressed,
    {{ suppress_small_cells('counts.numerator', 'counts.denominator') }}                as numerator,
    counts.denominator,
    {{ suppress_small_cells(safe_divide('counts.numerator', 'counts.denominator'), 'counts.denominator') }} as kpi_value,
    defs.target,
    defs.direction,
    case
        when counts.denominator < {{ var('min_cell_size') }} then 'suppressed'
        when defs.direction = 'lower_is_better'
             and {{ safe_divide('counts.numerator', 'counts.denominator') }} <= defs.target then 'on target'
        when defs.direction = 'higher_is_better'
             and {{ safe_divide('counts.numerator', 'counts.denominator') }} >= defs.target then 'on target'
        else 'off target'
    end                                                                                 as target_status,
    defs.owner,
    defs.definition
from counts
inner join defs on counts.kpi_id = defs.kpi_id
