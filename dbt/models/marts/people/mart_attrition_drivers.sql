-- One row per (factor, level): attrition rate and lift vs the company rate.
-- "Lift 2.0" means people in that group leave at twice the overall rate.
-- Protected attributes (age, gender, marital status) are deliberately not listed
-- as drivers; they are only used in the fairness audit of the model.

with e as (
    select * from {{ ref('int_employees__enriched') }}
),

overall as (
    select {{ safe_divide('sum(case when is_attrited then 1 else 0 end)', 'count(*)') }} as company_rate from e
),

long_form as (
    {% set factors = [
        ('overtime',              "case when works_overtime then 'Yes' else 'No' end"),
        ('tenure_band',           'tenure_band'),
        ('job_level',             'cast(job_level as ' ~ dbt.type_string() ~ ')'),
        ('department',            'department'),
        ('job_role',              'job_role'),
        ('business_travel',       'business_travel'),
        ('pay_quartile_in_level', "concat('Q', cast(pay_quartile_in_level as " ~ dbt.type_string() ~ "))"),
        ('promotion_stalled',     "case when is_promotion_stalled then 'Yes' else 'No' end"),
        ('stock_option_level',    'cast(stock_option_level as ' ~ dbt.type_string() ~ ')'),
        ('job_satisfaction',      'cast(job_satisfaction as ' ~ dbt.type_string() ~ ')'),
        ('environment_satisfaction', 'cast(environment_satisfaction as ' ~ dbt.type_string() ~ ')'),
        ('work_life_balance',     'cast(work_life_balance as ' ~ dbt.type_string() ~ ')'),
    ] %}
    {% for name, expr in factors %}
    select
        '{{ name }}'                                         as factor,
        {{ expr }}                                           as factor_level,
        count(*)                                             as headcount,
        sum(case when is_attrited then 1 else 0 end)         as leavers
    from e
    group by 1, 2
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    long_form.factor,
    long_form.factor_level,
    long_form.headcount,
    {{ suppress_small_cells('long_form.leavers', 'long_form.headcount') }}                                   as leavers,
    {{ suppress_small_cells(safe_divide('long_form.leavers', 'long_form.headcount'), 'long_form.headcount') }} as attrition_rate,
    overall.company_rate,
    {{ suppress_small_cells('round(' ~ safe_divide(safe_divide('long_form.leavers', 'long_form.headcount'), 'overall.company_rate') ~ ', 2)', 'long_form.headcount') }} as lift_vs_company
from long_form
cross join overall
