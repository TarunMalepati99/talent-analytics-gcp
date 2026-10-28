"""DAG integrity: imports cleanly, has the expected tasks and gates in the right order."""
from pathlib import Path

import pytest

airflow = pytest.importorskip("airflow")
from airflow.models import DagBag  # noqa: E402

DAGS = Path(__file__).resolve().parents[1] / "orchestration" / "dags"


@pytest.fixture(scope="module")
def dag():
    bag = DagBag(dag_folder=str(DAGS), include_examples=False)
    assert not bag.import_errors, bag.import_errors
    return bag.dags["talent_analytics_daily"]


def test_tasks_present(dag):
    expected = {
        "extract_hris", "extract_postings", "extract_jolts", "load_hris", "load_jolts", "load_postings_raw",
        "dataflow_normalize_postings", "dbt_source_freshness", "dbt_build", "is_retrain_day", "bqml_train",
        "bqml_evaluate", "gate_model_auc", "bqml_global_explain", "bqml_score_employees",
        "bqml_fairness_audit", "gate_fairness_four_fifths", "publish_segment_risk",
    }
    assert expected == set(dag.task_ids)


def test_publish_requires_both_gates(dag):
    upstream = dag.get_task("publish_segment_risk").get_flat_relative_ids(upstream=True)
    assert {"gate_model_auc", "gate_fairness_four_fifths", "dbt_build"} <= upstream


def test_dbt_waits_for_dataflow(dag):
    assert "dataflow_normalize_postings" in dag.get_task("dbt_build").get_flat_relative_ids(upstream=True)
