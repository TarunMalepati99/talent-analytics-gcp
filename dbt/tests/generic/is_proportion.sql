{# Passes when every non-null value is between 0 and 1 inclusive. #}
{% test is_proportion(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} < 0 or {{ column_name }} > 1
{% endtest %}
