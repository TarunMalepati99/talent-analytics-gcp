-- Adds the segment labels every people mart groups by, so band boundaries are
-- defined once.

with employees as (
    select * from {{ ref('stg_hris__employees') }}
),

role_map as (
    select job_role, role_family from {{ ref('job_role_family_map') }}
)

select
    employees.*,
    coalesce(role_map.role_family, 'other')                       as role_family,

    case
        when years_at_company < 1  then '0: <1 yr'
        when years_at_company <= 2 then '1: 1-2 yrs'
        when years_at_company <= 5 then '2: 3-5 yrs'
        when years_at_company <= 10 then '3: 6-10 yrs'
        else '4: 10+ yrs'
    end                                                           as tenure_band,

    case
        when age < 25 then '<25'
        when age < 35 then '25-34'
        when age < 45 then '35-44'
        when age < 55 then '45-54'
        else '55+'
    end                                                           as age_band,

    -- IBM codes education 1-5; labels follow the dataset's documentation.
    case education
        when 1 then '1: Below College'
        when 2 then '2: College'
        when 3 then '3: Bachelor'
        when 4 then '4: Master'
        when 5 then '5: Doctor'
    end                                                           as education_level,

    -- Pay relative to peers at the same job level (1 = lowest-paid quarter).
    ntile(4) over (partition by job_level order by monthly_income) as pay_quartile_in_level,

    years_since_last_promotion >= {{ var('promotion_stall_years') }} as is_promotion_stalled
from employees
left join role_map on employees.job_role = role_map.job_role
