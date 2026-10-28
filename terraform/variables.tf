variable "project_id" {
  description = "GCP project to deploy into."
  type        = string
}

variable "region" {
  description = "Region for Composer and Dataflow."
  type        = string
  default     = "us-central1"
}

variable "bq_location" {
  description = "BigQuery location. Data Catalog taxonomies and data policies must use the same location."
  type        = string
  default     = "US"
}

variable "bucket_name" {
  description = "Globally unique name for the data-lake bucket."
  type        = string
}

variable "hr_analysts_members" {
  description = "Principals that may see compensation and demographics in clear text, e.g. [\"group:hr-analytics@yourco.com\"]."
  type        = list(string)
  default     = []
}

variable "people_viewers_members" {
  description = "Principals (e.g. HR business partners) who can query people marts but see sensitive columns masked."
  type        = list(string)
  default     = []
}

variable "recruiting_members" {
  description = "Principals (recruiting team) who can read the recruiting marts."
  type        = list(string)
  default     = []
}

variable "create_composer" {
  description = "Cloud Composer bills continuously, even idle (a few hundred dollars a month for a small environment). Turn on to demo the DAG, then off again."
  type        = bool
  default     = false
}

variable "composer_image_version" {
  description = "Composer image; list current ones with `gcloud composer environments list-image-versions --location REGION`."
  type        = string
  default     = "composer-3-airflow-2"
}

variable "force_destroy" {
  description = "Allow `terraform destroy` to delete non-empty buckets and datasets (portfolio/dev only)."
  type        = bool
  default     = true
}
