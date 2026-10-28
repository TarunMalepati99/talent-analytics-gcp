{#
  Post-hook for people marts. On BigQuery, attaches Data Catalog policy tags to every
  column whose yml `config.meta.sensitivity` is set (compensation | demographics), using
  the policy tag names Terraform outputs (vars policy_tag_compensation / policy_tag_demographics).
  BigQuery then enforces column-level security and dynamic masking on those columns.

  On other targets it does nothing, unless var policy_tags_dry_run is true, in which case
  it logs what it would tag (used by `make local` to check the yml wiring offline).
#}
{% macro sensitive_columns(node) %}
  {% set found = {} %}
  {% for name, col in node.columns.items() %}
    {% set meta = col.get('meta') or {} %}
    {% set cfg = col.get('config') or {} %}
    {% set sensitivity = meta.get('sensitivity') or (cfg.get('meta') or {}).get('sensitivity') %}
    {% if sensitivity %}{% do found.update({name: sensitivity}) %}{% endif %}
  {% endfor %}
  {{ return(found) }}
{% endmacro %}

{% macro apply_policy_tags() %}
  {% if execute %}
    {% set sensitive = sensitive_columns(model) %}
    {% if target.type == 'bigquery' and sensitive %}
      {% set tagged = {} %}
      {% for name, sensitivity in sensitive.items() %}
        {% set tag = var('policy_tag_' ~ sensitivity, '') %}
        {% if not tag %}
          {{ exceptions.raise_compiler_error("Column " ~ name ~ " is marked sensitivity=" ~ sensitivity ~ " but var policy_tag_" ~ sensitivity ~ " is empty. Pass it from `terraform output`.") }}
        {% endif %}
        {% do tagged.update({name: {'name': name, 'description': model.columns[name].get('description', ''), 'policy_tags': [tag]}}) %}
      {% endfor %}
      {% do adapter.update_columns(this, tagged) %}
      {% do log("applied policy tags to " ~ tagged | length ~ " column(s) of " ~ this, info=true) %}
    {% elif var('policy_tags_dry_run', false) and sensitive %}
      {% do log("[dry run] would tag " ~ this ~ ": " ~ sensitive, info=true) %}
    {% endif %}
  {% endif %}
  {{ return('') }}
{% endmacro %}
