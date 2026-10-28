# Column-level security + dynamic data masking for HR data.
#
#   policy tag      clear text for                  everyone else with dataset access sees
#   compensation    HR analysts, pipeline SA        NULL               (ALWAYS_NULL)
#   demographics    HR analysts, pipeline SA        "" / 0 defaults    (DEFAULT_MASKING_VALUE)
#
# dbt attaches these tags to columns marked `meta: {sensitivity: ...}` (macros/apply_policy_tags.sql).

resource "google_data_catalog_taxonomy" "hr" {
  region                 = lower(var.bq_location)
  display_name           = "hr_sensitive"
  description            = "Sensitive HR attributes in the talent analytics warehouse."
  activated_policy_types = ["FINE_GRAINED_ACCESS_CONTROL"]

  depends_on = [google_project_service.apis]
}

resource "google_data_catalog_policy_tag" "compensation" {
  taxonomy     = google_data_catalog_taxonomy.hr.id
  display_name = "compensation"
  description  = "Pay, equity and any average of them at small grain."
}

resource "google_data_catalog_policy_tag" "demographics" {
  taxonomy     = google_data_catalog_taxonomy.hr.id
  display_name = "demographics"
  description  = "Protected or personal attributes: age band, gender, marital status."
}

resource "google_bigquery_datapolicy_data_policy" "mask_compensation" {
  location         = lower(var.bq_location)
  data_policy_id   = "mask_compensation"
  policy_tag       = google_data_catalog_policy_tag.compensation.name
  data_policy_type = "DATA_MASKING_POLICY"

  data_masking_policy {
    predefined_expression = "ALWAYS_NULL"
  }
}

resource "google_bigquery_datapolicy_data_policy" "mask_demographics" {
  location         = lower(var.bq_location)
  data_policy_id   = "mask_demographics"
  policy_tag       = google_data_catalog_policy_tag.demographics.name
  data_policy_type = "DATA_MASKING_POLICY"

  data_masking_policy {
    predefined_expression = "DEFAULT_MASKING_VALUE"
  }
}

locals {
  # Built from known strings (not the resource attribute) so for_each keys are known at plan time.
  clear_text_readers = concat(var.hr_analysts_members, ["serviceAccount:${local.pipeline_sa_email}"])
  policy_tags = {
    compensation = google_data_catalog_policy_tag.compensation.name
    demographics = google_data_catalog_policy_tag.demographics.name
  }
  clear_text_grants = {
    for pair in setproduct(keys(local.policy_tags), local.clear_text_readers) :
    "${pair[0]}|${pair[1]}" => { tag = pair[0], member = pair[1] }
  }
  data_policies = {
    compensation = google_bigquery_datapolicy_data_policy.mask_compensation.data_policy_id
    demographics = google_bigquery_datapolicy_data_policy.mask_demographics.data_policy_id
  }
  masked_grants = {
    for pair in setproduct(keys(local.data_policies), var.people_viewers_members) :
    "${pair[0]}|${pair[1]}" => { policy = pair[0], member = pair[1] }
  }
}

resource "google_data_catalog_policy_tag_iam_member" "clear_text" {
  for_each   = local.clear_text_grants
  policy_tag = local.policy_tags[each.value.tag]
  role       = "roles/datacatalog.categoryFineGrainedReader"
  member     = each.value.member

  depends_on = [google_service_account.pipeline]
}

resource "google_bigquery_datapolicy_data_policy_iam_member" "masked" {
  for_each       = local.masked_grants
  project        = var.project_id
  location       = lower(var.bq_location)
  data_policy_id = local.data_policies[each.value.policy]
  role           = "roles/bigquerydatapolicy.maskedReader"
  member         = each.value.member
}
