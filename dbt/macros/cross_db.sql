{# Small dispatch macros so the same models compile for BigQuery and DuckDB. #}

{% macro safe_divide(numerator, denominator) -%}
    {{ return(adapter.dispatch('safe_divide', 'talent_analytics')(numerator, denominator)) }}
{%- endmacro %}
{% macro bigquery__safe_divide(numerator, denominator) -%}
    safe_divide({{ numerator }}, {{ denominator }})
{%- endmacro %}
{% macro default__safe_divide(numerator, denominator) -%}
    ({{ numerator }}) * 1.0 / nullif({{ denominator }}, 0)
{%- endmacro %}

{% macro median(expr) -%}
    {{ return(adapter.dispatch('median', 'talent_analytics')(expr)) }}
{%- endmacro %}
{% macro bigquery__median(expr) -%}
    approx_quantiles({{ expr }}, 2)[offset(1)]
{%- endmacro %}
{% macro default__median(expr) -%}
    median({{ expr }})
{%- endmacro %}

{% macro hash_key(expr) -%}
    {# Salted so the key can't be reversed by hashing the small space of employee numbers. #}
    {{ dbt.hash("concat('" ~ env_var('EMPLOYEE_KEY_SALT', 'local-dev-salt') ~ "', cast(" ~ expr ~ " as " ~ dbt.type_string() ~ "))") }}
{%- endmacro %}
