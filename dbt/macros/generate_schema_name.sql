{# Use the folder's +schema as-is (talent_staging -> "staging") so datasets are
   named the same in every environment: staging, people_marts, recruiting_marts, reference. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}
