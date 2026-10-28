#!/usr/bin/env bash
# Sync the repo into the Composer environment's bucket:
#   code  -> <bucket>/data/talent-analytics-gcp   (mounted at /home/airflow/gcs/data/...)
#   DAG   -> <bucket>/dags/
set -euo pipefail
cd "$(dirname "$0")/.."

PREFIX=$(cd terraform && terraform output -raw composer_dag_gcs_prefix)
if [[ -z "$PREFIX" ]]; then
  echo "Composer is off (create_composer = false). Turn it on in terraform.tfvars and apply first." >&2
  exit 1
fi
ROOT=${PREFIX%/dags}

gcloud storage rsync --recursive --delete-unmatched-destination-objects \
  --exclude='^(\.git|warehouse|data|dbt/target.*|dbt/logs|terraform|\.pytest_cache)(/|$)|.*__pycache__.*' \
  . "$ROOT/data/talent-analytics-gcp"
gcloud storage cp orchestration/dags/talent_analytics_dag.py "$PREFIX/"
echo "Deployed. Open the Airflow UI from the Composer page and trigger talent_analytics_daily."
