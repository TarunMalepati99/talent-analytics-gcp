-- One row per employee. Renames, types and drops columns that are constant in the
-- source (employee_count, standard_hours, over18) so downstream models stay lean.
-- employee_number is replaced by a salted hash: marts never carry the raw HRIS ID.

with source as (
    select * from {{ source('talent_raw', 'hris_employees') }}
)

select
    {{ hash_key('employee_number') }}            as employee_key,
    department,
    job_role,
    job_level,
    education,
    education_field,
    business_travel,
    over_time = 'Yes'                            as works_overtime,
    attrition = 'Yes'                            as is_attrited,

    -- tenure & history
    years_at_company,
    years_in_current_role,
    years_since_last_promotion,
    years_with_curr_manager,
    total_working_years,
    num_companies_worked,
    training_times_last_year,

    -- compensation (policy-tagged in marts)
    monthly_income,
    percent_salary_hike,
    stock_option_level,

    -- survey & performance (1 = low ... 4 = high)
    environment_satisfaction,
    job_satisfaction,
    relationship_satisfaction,
    job_involvement,
    work_life_balance,
    performance_rating,

    -- demographics (policy-tagged; excluded from the attrition model's features)
    age,
    gender,
    marital_status,
    distance_from_home,

    _source_system                               as source_system,
    _ingested_at                                 as ingested_at
from source
