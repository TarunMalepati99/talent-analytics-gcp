with source as (
    select * from {{ source('talent_raw', 'job_postings_normalized') }}
)

select
    posting_key,
    source                                   as ats_source,
    board                                    as company_board,
    source_job_id,
    title,
    department,
    team,
    location,
    workplace_type,
    coalesce(is_remote, false)               as is_remote,
    role_family,
    seniority,
    cast(posted_at as timestamp)             as posted_at,
    cast(updated_at as timestamp)            as updated_at,
    url,
    cast(ingested_at as timestamp)           as ingested_at,
    starts_with(board, 'fixture-')           as is_test_fixture
from source
