-- The decision table: for each role family, how fast do we lose people and how
-- hard is the market competing for the same profile?
--
--   internal side: headcount, leavers, attrition rate, lift vs company
--   market side:   open postings across tracked company boards (and entry-level share)
--
-- priority = 'act now' when a family loses people well above the company rate AND
-- market demand for it is at or above the median family: replacements will be slow
-- and expensive, so retention spend there has the best payoff.

with people as (
    select
        role_family,
        count(*)                                             as headcount,
        sum(case when is_attrited then 1 else 0 end)         as leavers
    from {{ ref('int_employees__enriched') }}
    group by 1
),

company as (
    select {{ safe_divide('sum(leavers)', 'sum(headcount)') }} as company_rate from people
),

market as (
    select
        role_family,
        sum(open_postings)                                                     as market_open_postings,
        sum(case when seniority in ('intern', 'entry') then open_postings else 0 end) as market_entry_postings
    from {{ ref('mart_open_roles') }}
    group by 1
),

joined as (
    select
        people.role_family,
        people.headcount,
        people.leavers,
        {{ safe_divide('people.leavers', 'people.headcount') }}               as attrition_rate,
        company.company_rate,
        coalesce(market.market_open_postings, 0)                              as market_open_postings,
        coalesce(market.market_entry_postings, 0)                             as market_entry_postings
    from people
    cross join company
    left join market on people.role_family = market.role_family
),

ranked as (
    select
        *,
        {{ safe_divide('attrition_rate', 'company_rate') }}                    as lift_vs_company,
        percent_rank() over (order by market_open_postings)                   as market_demand_pct_rank
    from joined
)

select
    role_family,
    headcount,
    {{ suppress_small_cells('leavers') }}                                      as leavers,
    {{ suppress_small_cells('round(attrition_rate, 4)') }}                     as attrition_rate,
    round(company_rate, 4)                                                    as company_rate,
    {{ suppress_small_cells('round(lift_vs_company, 2)') }}                    as lift_vs_company,
    market_open_postings,
    market_entry_postings,
    round(market_demand_pct_rank, 2)                                          as market_demand_pct_rank,
    case
        when headcount < {{ var('min_cell_size') }}                  then 'insufficient data'
        when lift_vs_company >= 1.25 and market_demand_pct_rank >= 0.5 then 'act now'
        when lift_vs_company >= 1.25                                  then 'monitor: high attrition'
        when market_demand_pct_rank >= 0.5                           then 'monitor: hot market'
        else 'stable'
    end                                                                       as priority
from ranked
