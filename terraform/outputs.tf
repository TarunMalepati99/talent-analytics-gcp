output "bucket" {
  value = google_storage_bucket.lake.name
}

output "pipeline_service_account" {
  value = google_service_account.pipeline.email
}

output "policy_tag_compensation" {
  description = "Pass to dbt as var policy_tag_compensation."
  value       = google_data_catalog_policy_tag.compensation.name
}

output "policy_tag_demographics" {
  description = "Pass to dbt as var policy_tag_demographics."
  value       = google_data_catalog_policy_tag.demographics.name
}

output "employee_key_salt" {
  value     = random_password.employee_key_salt.result
  sensitive = true
}

output "composer_dag_gcs_prefix" {
  description = "Where to copy the DAG file (empty when Composer is off)."
  value       = var.create_composer ? google_composer_environment.talent[0].config[0].dag_gcs_prefix : ""
}
