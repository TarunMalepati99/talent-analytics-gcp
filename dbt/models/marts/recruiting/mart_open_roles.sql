-- Market demand: open postings by company board, role family and seniority.
-- Test fixtures are excluded unless var include_fixtures is true (local smoke runs).

with postings as (
    select
        *,
        {{ dbt.datediff('cast(posted_at as date)', 'current_date', 'day') }} as days_open
    from {{ ref('stg_jobs__postings') }}
    where {{ 'true' if var('include_fixtures', false) else 'not is_test_fixture' }}
)

select
    company_board,
    role_family,
    seniority,
    count(*)                                                         as open_postings,
    round({{ safe_divide('sum(case when is_remote then 1 else 0 end)', 'count(*)') }}, 3) as remote_share,
    {{ median('days_open') }}                                        as median_days_open,
    max(ingested_at)                                                 as as_of
from postings
group by 1, 2, 3
