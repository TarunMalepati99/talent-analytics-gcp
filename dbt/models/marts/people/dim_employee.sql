{{ config(post_hook=["{{ apply_row_access('department') }}"]) }}

-- Employee-grain table for HR analysts with fine-grained access.
-- Compensation and demographic columns carry Data Catalog policy tags on BigQuery
-- (see _people.yml), so masked readers see NULL / masked values for them.
select
    employee_key,
    department,
    job_role,
    role_family,
    job_level,
    tenure_band,
    years_at_company,
    years_since_last_promotion,
    is_promotion_stalled,
    works_overtime,
    business_travel,
    pay_quartile_in_level,
    monthly_income,
    monthly_income * 12            as annual_income,
    stock_option_level,
    job_satisfaction,
    environment_satisfaction,
    work_life_balance,
    education_level,
    education_field,
    age_band,
    gender,
    marital_status,
    is_attrited
from {{ ref('int_employees__enriched') }}
