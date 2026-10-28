-- Validation before dissemination: the scorecard must reconcile to the employee table.
-- 1. Company-level attrition numerator/denominator equal leavers/headcount in dim_employee.
-- 2. For every KPI, department denominators sum to the company denominator.
-- 3. No numerator exceeds its denominator.

with dim as (
    select count(*) as headcount, sum(case when is_attrited then 1 else 0 end) as leavers
    from {{ ref('dim_employee') }}
),

company as (
    select kpi_id, numerator, denominator
    from {{ ref('mart_kpi_scorecard') }}
    where slice_type = 'company'
),

dept_totals as (
    select kpi_id, sum(denominator) as dept_denominator
    from {{ ref('mart_kpi_scorecard') }}
    where slice_type = 'department'
    group by 1
)

select 'company attrition does not match dim_employee' as failure, company.kpi_id
from company cross join dim
where company.kpi_id = 'ATTR_RATE'
  and (company.numerator <> dim.leavers or company.denominator <> dim.headcount)

union all

select 'department denominators do not sum to company' as failure, company.kpi_id
from company
inner join dept_totals on company.kpi_id = dept_totals.kpi_id
where company.denominator <> dept_totals.dept_denominator

union all

select 'numerator exceeds denominator' as failure, kpi_id
from {{ ref('mart_kpi_scorecard') }}
where numerator > denominator
