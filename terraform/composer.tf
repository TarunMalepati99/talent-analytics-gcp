# Optional: Cloud Composer 3 environment that runs orchestration/dags/talent_analytics_dag.py.
# Off by default because it bills continuously; see README "Cost control".

resource "google_project_iam_member" "composer_service_agent" {
  count   = var.create_composer ? 1 : 0
  project = var.project_id
  role    = "roles/composer.ServiceAgentV2Ext"
  member  = "serviceAccount:service-${data.google_project.this.number}@cloudcomposer-accounts.iam.gserviceaccount.com"
}

resource "google_composer_environment" "talent" {
  count  = var.create_composer ? 1 : 0
  name   = "talent-analytics"
  region = var.region
  labels = local.labels

  config {
    environment_size = "ENVIRONMENT_SIZE_SMALL"

    software_config {
      image_version = var.composer_image_version
      pypi_packages = {
        "dbt-bigquery"                         = ">=1.9,<2"
        "apache-airflow-providers-apache-beam" = ""
        "pyyaml"                               = ""
      }
      env_variables = {
        TALENT_PROJECT                 = var.project_id
        TALENT_BUCKET                  = google_storage_bucket.lake.name
        TALENT_REGION                  = var.region
        TALENT_PIPELINE_SA             = google_service_account.pipeline.email
        TALENT_CODE_DIR                = "/home/airflow/gcs/data/talent-analytics-gcp"
        TALENT_POLICY_TAG_COMPENSATION = google_data_catalog_policy_tag.compensation.name
        TALENT_POLICY_TAG_DEMOGRAPHICS = google_data_catalog_policy_tag.demographics.name
        EMPLOYEE_KEY_SALT              = random_password.employee_key_salt.result
      }
    }

    workloads_config {
      scheduler {
        cpu        = 0.5
        memory_gb  = 2
        storage_gb = 1
        count      = 1
      }
      web_server {
        cpu        = 0.5
        memory_gb  = 2
        storage_gb = 1
      }
      worker {
        cpu        = 1
        memory_gb  = 4
        storage_gb = 2
        min_count  = 1
        max_count  = 2
      }
    }

    node_config {
      service_account = google_service_account.pipeline.email
    }
  }

  depends_on = [
    google_project_iam_member.composer_service_agent,
    google_project_iam_member.pipeline_project_roles,
  ]
}
