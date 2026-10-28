-- Monthly JOLTS rates (%), labelled with industry and measure from the series seed.
with source as (
    select * from {{ source('talent_raw', 'bls_jolts') }}
),

series as (
    select * from {{ ref('jolts_series') }}
)

select
    source.series_id,
    series.industry,
    series.measure,
    cast(concat(cast(source.year as {{ dbt.type_string() }}), '-', substr(source.period, 2, 2), '-01') as date) as month_start,
    source.value                                  as rate_pct,
    source.is_preliminary
from source
inner join series on source.series_id = series.series_id
where source.value is not null
