{#
  Row-level security for department-scoped HR business partners (BigQuery only).

  `dbt build` recreates tables, which drops row access policies, so they are
  re-applied as a post-hook every run. Configure with the var:

    hrbp_department_access:
      "Sales": ["group:hrbp-sales@yourco.com"]
      "Research & Development": ["group:hrbp-rnd@yourco.com"]
    hr_all_departments: ["group:hr-analytics@yourco.com"]

  Once any row access policy exists on a table, principals not covered by one see
  zero rows, so the all-departments policy for central HR analytics is required.
#}
{% macro apply_row_access(column='department') %}
  {% if execute and target.type == 'bigquery' %}
    {% set by_dept = var('hrbp_department_access', {}) %}
    {% set all_access = var('hr_all_departments', []) %}
    {% if by_dept or all_access %}
      {% set stmts = [] %}
      {% for dept, members in by_dept.items() %}
        {% set policy = 'dept_' ~ (dept | lower | replace(' ', '_') | replace('&', 'and')) %}
        {% do stmts.append(
          "create or replace row access policy " ~ policy ~ " on " ~ this
          ~ " grant to (" ~ ("'" ~ (members | join("', '")) ~ "'") ~ ")"
          ~ " filter using (" ~ column ~ " = '" ~ dept ~ "')"
        ) %}
      {% endfor %}
      {% if all_access %}
        {% do stmts.append(
          "create or replace row access policy all_departments on " ~ this
          ~ " grant to (" ~ ("'" ~ (all_access | join("', '")) ~ "'") ~ ") filter using (true)"
        ) %}
      {% endif %}
      {{ return(stmts | join(';\n')) }}
    {% endif %}
  {% endif %}
  {{ return('') }}
{% endmacro %}
