locals {
  apis = [
    "bigquery.googleapis.com",
    "bigquerydatapolicy.googleapis.com",
    "datacatalog.googleapis.com",
    "storage.googleapis.com",
    "dataflow.googleapis.com",
    "composer.googleapis.com",
    "iam.googleapis.com",
  ]

  datasets = {
    talent_raw       = "Landing tables loaded from GCS: HRIS snapshot, raw + normalized ATS postings, BLS JOLTS."
    staging          = "dbt staging and intermediate views."
    reference        = "dbt seeds: role-family mapping and JOLTS series metadata."
    people_marts     = "People analytics marts. Sensitive columns carry policy tags (masked for non-analysts)."
    recruiting_marts = "Recruiting / market-demand marts."
    ml               = "BigQuery ML attrition model, evaluation, individual risk scores and fairness audit. Analysts only."
  }

  labels = {
    app         = "talent-analytics"
    data_domain = "people"
    managed_by  = "terraform"
  }
}

data "google_project" "this" {}

locals {
  pipeline_sa_email = "talent-pipeline@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

# ---------- data lake ----------
resource "google_storage_bucket" "lake" {
  name                        = var.bucket_name
  location                    = var.bq_location
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy
  labels                      = local.labels

  versioning {
    enabled = true
  }

  # Dataflow scratch space is disposable.
  lifecycle_rule {
    condition {
      age            = 7
      matches_prefix = ["tmp/"]
    }
    action {
      type = "Delete"
    }
  }

  # Keep raw landings ~13 months for replay and audit, then delete.
  lifecycle_rule {
    condition {
      age            = 400
      matches_prefix = ["raw/"]
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

# ---------- BigQuery datasets ----------
resource "google_bigquery_dataset" "ds" {
  for_each                   = local.datasets
  dataset_id                 = each.key
  description                = each.value
  location                   = var.bq_location
  delete_contents_on_destroy = var.force_destroy
  labels                     = local.labels

  depends_on = [google_project_service.apis]
}

# ---------- pipeline identity ----------
resource "google_service_account" "pipeline" {
  account_id   = "talent-pipeline"
  display_name = "Talent analytics pipeline (Composer workers, Dataflow, dbt, BQML)"
}

resource "google_project_iam_member" "pipeline_project_roles" {
  for_each = toset([
    "roles/bigquery.jobUser",
    "roles/dataflow.worker",
    "roles/dataflow.developer",
    "roles/composer.worker",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_storage_bucket_iam_member" "pipeline_lake" {
  bucket = google_storage_bucket.lake.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "pipeline_editor" {
  for_each   = local.datasets
  dataset_id = google_bigquery_dataset.ds[each.key].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

# Dataflow jobs launched from Composer run as the pipeline SA.
resource "google_service_account_iam_member" "pipeline_act_as_self" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.pipeline.email}"
}

# ---------- consumer access (least privilege by dataset) ----------
locals {
  dataset_readers = merge(
    { for m in var.hr_analysts_members : "people_marts|${m}" => { ds = "people_marts", member = m } },
    { for m in var.people_viewers_members : "people_marts|${m}" => { ds = "people_marts", member = m } },
    { for m in var.hr_analysts_members : "ml|${m}" => { ds = "ml", member = m } },
    { for m in var.hr_analysts_members : "recruiting_marts|${m}" => { ds = "recruiting_marts", member = m } },
    { for m in var.recruiting_members : "recruiting_marts|${m}" => { ds = "recruiting_marts", member = m } },
  )
}

resource "google_bigquery_dataset_iam_member" "readers" {
  for_each   = local.dataset_readers
  dataset_id = google_bigquery_dataset.ds[each.value.ds].dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = each.value.member
}

resource "google_project_iam_member" "readers_job_user" {
  for_each = toset(concat(var.hr_analysts_members, var.people_viewers_members, var.recruiting_members))
  project  = var.project_id
  role     = "roles/bigquery.jobUser"
  member   = each.value
}

# Salt for hashing employee numbers in dbt (stg_hris__employees). Passed to Composer as
# an env var for simplicity; in production use Composer's Secret Manager backend.
resource "random_password" "employee_key_salt" {
  length  = 32
  special = false
}
