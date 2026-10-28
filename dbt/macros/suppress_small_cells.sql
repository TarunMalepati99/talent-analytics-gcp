{# Returns `expr` only when the cell has at least var('min_cell_size') employees, else null. #}
{% macro suppress_small_cells(expr, headcount_expr='headcount') -%}
    case when {{ headcount_expr }} >= {{ var('min_cell_size') }} then {{ expr }} end
{%- endmacro %}
