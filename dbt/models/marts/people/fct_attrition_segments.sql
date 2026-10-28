{{ config(post_hook=["{{ apply_row_access('department') }}"]) }}

-- Attrition by department x job role x tenure band: the table HR business partners
-- filter in the dashboard. Small cells are suppressed (see var min_cell_size).

with employees as (
    select * from {{ ref('int_employees__enriched') }}
),

segments as (
    select
        department,
        job_role,
        role_family,
        tenure_band,
        count(*)                                                as headcount,
        sum(case when is_attrited then 1 else 0 end)            as leavers,
        avg(monthly_income)                                     as avg_monthly_income
    from employees
    group by 1, 2, 3, 4
)

select
    {{ dbt.hash("concat(department, '|', job_role, '|', tenure_band)") }} as segment_key,
    department,
    job_role,
    role_family,
    tenure_band,
    headcount,
    headcount < {{ var('min_cell_size') }}                                  as is_suppressed,
    {{ suppress_small_cells('leavers') }}                                    as leavers,
    {{ suppress_small_cells(safe_divide('leavers', 'headcount')) }}          as attrition_rate,
    {{ suppress_small_cells('round(avg_monthly_income, 0)') }}               as avg_monthly_income
from segments
