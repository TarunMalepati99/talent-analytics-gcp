"""Cloud Composer (Airflow) DAG for the Talent Analytics Platform.

Daily:
    extract (HRIS, ATS postings, BLS JOLTS) -> GCS (dt=YYYY-MM-DD partitions)
    -> load raw tables into BigQuery
    -> Dataflow normalizes + dedups ATS postings
    -> dbt source freshness + dbt build (models and tests, policy tags applied)
Weekly (Mondays):
    retrain BigQuery ML attrition model -> evaluate -> AUC gate
    -> score current employees -> fairness audit -> fairness gate
    -> publish segment-level risk to people marts

Configuration comes from Composer environment variables (set in Terraform):
TALENT_PROJECT, TALENT_BUCKET, TALENT_REGION, TALENT_CODE_DIR, TALENT_PIPELINE_SA,
TALENT_POLICY_TAG_COMPENSATION, TALENT_POLICY_TAG_DEMOGRAPHICS, EMPLOYEE_KEY_SALT.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.providers.apache.beam.operators.beam import BeamRunPythonPipelineOperator
from airflow.providers.google.cloud.operators.bigquery import (
    BigQueryCheckOperator,
    BigQueryInsertJobOperator,
)
from airflow.providers.google.cloud.operators.dataflow import DataflowConfiguration
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator

try:  # Airflow 3 / standard provider
    from airflow.providers.standard.operators.bash import BashOperator
    from airflow.providers.standard.operators.python import ShortCircuitOperator
except ImportError:  # Airflow 2.x
    from airflow.operators.bash import BashOperator
    from airflow.operators.python import ShortCircuitOperator

PROJECT = os.environ.get("TALENT_PROJECT", "your-gcp-project")
BUCKET = os.environ.get("TALENT_BUCKET", "your-talent-lake-bucket")
REGION = os.environ.get("TALENT_REGION", "us-central1")
# Repo is synced to the Composer bucket's data/ folder, mounted at /home/airflow/gcs/data.
CODE_DIR = os.environ.get("TALENT_CODE_DIR", "/home/airflow/gcs/data/talent-analytics-gcp")
MIN_CELL_SIZE = 10
MIN_AUC = 0.70
MIN_ADVERSE_IMPACT_RATIO = 0.80

# In Composer the DAG file sits alone in dags/ while the repo lives in CODE_DIR;
# locally the DAG sits inside the repo.
REPO = Path(CODE_DIR) if Path(CODE_DIR).exists() else Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "config" / "schemas"
SQL_DIR = REPO / "bqml"


def _schema(name: str) -> list[dict]:
    path = SCHEMAS / name
    return json.loads(path.read_text()) if path.exists() else []


def _sql(name: str) -> str:
    return (SQL_DIR / name).read_text()


RAW = "raw/{source}/dt={{{{ ds }}}}/{file}"

default_args = {
    "owner": "people-analytics",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="talent_analytics_daily",
    description="HRIS + ATS + BLS -> BigQuery -> dbt marts; weekly BQML attrition model",
    start_date=datetime(2026, 10, 1),
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    params={"project": PROJECT, "min_cell_size": MIN_CELL_SIZE},
    tags=["people-analytics", "bigquery", "dbt", "dataflow"],
) as dag:

    # ---------- extract -> GCS ----------
    extract = {
        "hris": BashOperator(
            task_id="extract_hris",
            bash_command=f"cd {CODE_DIR} && python -m ingestion.fetch_hris "
                         f"--out gs://{BUCKET}/" + RAW.format(source="hris", file="employees.ndjson"),
        ),
        "postings": BashOperator(
            task_id="extract_postings",
            bash_command=f"cd {CODE_DIR} && python -m ingestion.fetch_postings --config config/boards.yaml "
                         f"--out gs://{BUCKET}/" + RAW.format(source="postings", file="postings_raw.ndjson"),
        ),
        "jolts": BashOperator(
            task_id="extract_jolts",
            bash_command=f"cd {CODE_DIR} && python -m ingestion.fetch_jolts --config config/jolts_series.yaml "
                         f"--out gs://{BUCKET}/" + RAW.format(source="jolts", file="jolts.ndjson"),
        ),
    }

    # ---------- GCS -> BigQuery raw ----------
    def load(task_id, source, file, table, schema, disposition="WRITE_TRUNCATE", **kw):
        return GCSToBigQueryOperator(
            task_id=task_id,
            bucket=BUCKET,
            source_objects=[RAW.format(source=source, file=file)],
            destination_project_dataset_table=f"{PROJECT}.talent_raw.{table}",
            source_format="NEWLINE_DELIMITED_JSON",
            schema_fields=_schema(schema),
            write_disposition=disposition,
            create_disposition="CREATE_IF_NEEDED",
            **kw,
        )

    load_hris = load("load_hris", "hris", "employees.ndjson", "hris_employees", "hris_employees.json")
    load_jolts = load("load_jolts", "jolts", "jolts.ndjson", "bls_jolts", "jolts.json")
    # Raw postings are appended (partitioned by load day) so any day can be replayed.
    load_postings_raw = load(
        "load_postings_raw", "postings", "postings_raw.ndjson", "job_postings_raw", "postings_raw.json",
        disposition="WRITE_APPEND", time_partitioning={"type": "DAY", "field": "ingested_at"},
    )

    # ---------- Dataflow: normalize + dedup postings ----------
    normalize_postings = BeamRunPythonPipelineOperator(
        task_id="dataflow_normalize_postings",
        runner="DataflowRunner",
        py_file=f"{CODE_DIR}/run_normalize_postings.py",
        py_requirements=["apache-beam[gcp]==2.77.0", "pyyaml"],
        py_system_site_packages=False,
        pipeline_options={
            "input": f"gs://{BUCKET}/" + RAW.format(source="postings", file="*.ndjson"),
            "output_table": f"{PROJECT}:talent_raw.job_postings_normalized",
            "dead_letter": f"gs://{BUCKET}/dead_letter/postings/dt={{{{ ds }}}}/rows",
            "temp_location": f"gs://{BUCKET}/tmp/dataflow",
            "setup_file": f"{CODE_DIR}/setup.py",
            "max_num_workers": 2,
            "machine_type": "e2-standard-2",
            "service_account_email": os.environ.get("TALENT_PIPELINE_SA", ""),
        },
        dataflow_config=DataflowConfiguration(
            job_name="normalize-postings-{{ ds_nodash }}",
            project_id=PROJECT,
            location=REGION,
            wait_until_finished=True,
        ),
    )

    # ---------- dbt ----------
    dbt_env = {
        "DBT_TARGET": "bigquery",
        "DBT_PROFILES_DIR": f"{CODE_DIR}/dbt",
        "GCP_PROJECT": PROJECT,
        "EMPLOYEE_KEY_SALT": os.environ.get("EMPLOYEE_KEY_SALT", ""),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    }
    dbt_vars = json.dumps({
        "policy_tag_compensation": os.environ.get("TALENT_POLICY_TAG_COMPENSATION", ""),
        "policy_tag_demographics": os.environ.get("TALENT_POLICY_TAG_DEMOGRAPHICS", ""),
    })
    dbt_freshness = BashOperator(
        task_id="dbt_source_freshness",
        bash_command=f"cd {CODE_DIR}/dbt && dbt source freshness",
        env=dbt_env,
    )
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {CODE_DIR}/dbt && dbt deps --quiet || true; dbt build --vars '{dbt_vars}'",
        env=dbt_env,
    )

    # ---------- weekly BigQuery ML ----------
    def bq(task_id: str, sql_file: str) -> BigQueryInsertJobOperator:
        return BigQueryInsertJobOperator(
            task_id=task_id,
            project_id=PROJECT,
            location="US",
            configuration={"query": {"query": _sql(sql_file), "useLegacySql": False}},
        )

    is_retrain_day = ShortCircuitOperator(
        task_id="is_retrain_day",
        python_callable=lambda logical_date=None, **_: logical_date is not None and logical_date.weekday() == 0,
    )
    train = bq("bqml_train", "01_train_attrition_model.sql")
    evaluate = bq("bqml_evaluate", "02_evaluate_model.sql")
    auc_gate = BigQueryCheckOperator(
        task_id="gate_model_auc",
        sql=f"SELECT roc_auc >= {MIN_AUC} FROM `{PROJECT}.ml.attrition_model_evaluation`",
        use_legacy_sql=False,
        location="US",
    )
    explain = bq("bqml_global_explain", "03_global_explain.sql")
    score = bq("bqml_score_employees", "04_score_employees.sql")
    fairness = bq("bqml_fairness_audit", "05_fairness_audit.sql")
    fairness_gate = BigQueryCheckOperator(
        task_id="gate_fairness_four_fifths",
        sql=f"SELECT COALESCE(LOGICAL_AND(adverse_impact_ratio >= {MIN_ADVERSE_IMPACT_RATIO}), TRUE) "
            f"FROM `{PROJECT}.ml.attrition_fairness_audit`",
        use_legacy_sql=False,
        location="US",
    )
    publish = bq("publish_segment_risk", "06_publish_segment_risk.sql")

    # ---------- dependencies ----------
    extract["hris"] >> load_hris
    extract["jolts"] >> load_jolts
    extract["postings"] >> load_postings_raw >> normalize_postings
    [load_hris, load_jolts, normalize_postings] >> dbt_freshness >> dbt_build
    dbt_build >> is_retrain_day >> train >> evaluate >> auc_gate >> [explain, score]
    score >> fairness >> fairness_gate >> publish
