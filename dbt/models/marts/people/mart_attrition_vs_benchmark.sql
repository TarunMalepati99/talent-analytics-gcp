-- Company attrition vs the US labour market (BLS JOLTS).
--
-- ASSUMPTION, stated on purpose: the HRIS attrition flag is treated as a trailing
-- 12-month leaver rate. IBM does not document the window for its dataset, so this
-- comparison shows the method; with a real HRIS you'd compute leavers in the last
-- 12 months / average headcount directly from termination dates.
--
-- JOLTS rates are monthly % of employment; the annual figure is the sum of the
-- latest 12 published months, which is how BLS-based annual turnover is usually
-- approximated.

with company as (
    select
        count(*)                                                        as headcount,
        sum(case when is_attrited then 1 else 0 end)                    as leavers,
        {{ safe_divide('sum(case when is_attrited then 1 else 0 end)', 'count(*)') }} as attrition_rate
    from {{ ref('int_employees__enriched') }}
),

jolts as (
    select * from {{ ref('stg_bls__jolts') }}
),

latest_month as (
    select series_id, max(month_start) as latest_month from jolts group by 1
),

trailing_12 as (
    select
        jolts.industry,
        jolts.measure,
        max(jolts.month_start)                                as through_month,
        count(*)                                              as months_used,
        sum(jolts.rate_pct) / 100.0                           as annual_rate
    from jolts
    inner join latest_month on jolts.series_id = latest_month.series_id
    where jolts.month_start > {{ dbt.dateadd('month', -12, 'latest_month.latest_month') }}
    group by 1, 2
)

select
    trailing_12.industry,
    trailing_12.measure                                                   as benchmark_measure,
    trailing_12.through_month,
    trailing_12.months_used,
    round(trailing_12.annual_rate, 4)                                     as benchmark_annual_rate,
    company.headcount                                                     as company_headcount,
    round(company.attrition_rate, 4)                                      as company_attrition_rate,
    round({{ safe_divide('company.attrition_rate', 'trailing_12.annual_rate') }}, 2) as company_vs_benchmark_ratio
from trailing_12
cross join company
where trailing_12.measure in ('quits_rate', 'total_separations_rate')
