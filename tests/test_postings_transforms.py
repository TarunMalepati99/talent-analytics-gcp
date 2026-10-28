import json
from pathlib import Path

import apache_beam as beam
import pytest
from apache_beam.testing.test_pipeline import TestPipeline
from apache_beam.testing.util import assert_that, equal_to

from pipelines.normalize_postings import DEAD_LETTER, NormalizeDoFn
from pipelines.postings_transforms import (
    ROLE_FAMILY_RULES, SENIORITY_RULES, classify, latest, normalize_record, posting_key,
)
from ingestion.fetch_postings import greenhouse_records, lever_records

FIX = Path(__file__).parent / "fixtures"


def gh_raw():
    payload = json.loads((FIX / "greenhouse_fixture.json").read_text())
    return list(greenhouse_records("fixture-co", payload, "2026-10-21 00:00:00"))


def lever_raw():
    payload = json.loads((FIX / "lever_fixture.json").read_text())
    return list(lever_records("fixture-lever", payload, "2026-10-21 00:00:00"))


@pytest.mark.parametrize("title,expected", [
    ("Senior Data Engineer, People Analytics", "people_hr"),
    ("Machine Learning Engineer", "data_ml"),
    ("Software Engineer, Backend", "engineering"),
    ("Account Executive, Enterprise", "sales"),
    ("Laboratory Technician II", "research"),
    ("Product Manager, Payments", "product_design"),
    ("Aircraft Maintenance Planner", "other"),  # 'ai' must not match inside 'Aircraft'
    ("General Manager", "management"),
])
def test_role_family(title, expected):
    assert classify(title, ROLE_FAMILY_RULES, "other") == expected


@pytest.mark.parametrize("title,expected", [
    ("Software Engineering Intern", "intern"),
    ("Data Scientist, New Grad", "entry"),
    ("Senior Data Engineer", "senior"),
    ("Staff Engineer", "staff_plus"),
    ("Director of Recruiting", "manager"),
    ("VP, People", "executive"),
    ("Data Analyst", "mid"),
])
def test_seniority(title, expected):
    assert classify(title, SENIORITY_RULES, "mid") == expected


def test_greenhouse_normalization_converts_timezones_and_departments():
    rec = normalize_record(gh_raw()[0])
    assert rec["source"] == "greenhouse"
    assert rec["posted_at"] == "2026-09-20 14:00:00"  # -04:00 -> UTC
    assert rec["department"] == "People" and rec["team"] == "People Analytics"
    assert rec["is_remote"] is True
    assert rec["posting_key"] == posting_key("greenhouse", "fixture-co", "1001")


def test_greenhouse_falls_back_to_updated_at_when_unpublished():
    rec = normalize_record(gh_raw()[2])
    assert rec["posted_at"] == rec["updated_at"] == "2026-10-18 08:00:00"


def test_lever_normalization_epoch_ms_and_workplace():
    rec = normalize_record(lever_raw()[1])
    assert rec["source"] == "lever"
    assert rec["workplace_type"] == "remote" and rec["is_remote"] is True
    assert rec["posted_at"] == "2025-10-09 10:00:00"
    assert rec["role_family"] == "sales"


def test_empty_title_is_rejected():
    with pytest.raises(ValueError):
        normalize_record(gh_raw()[4])


def test_latest_keeps_most_recent_ingest():
    a = {"ingested_at": "2026-10-20 00:00:00", "updated_at": "x", "v": 1}
    b = {"ingested_at": "2026-10-21 00:00:00", "updated_at": "x", "v": 2}
    assert latest([a, b])["v"] == 2


def test_beam_pipeline_routes_bad_rows_to_dead_letter():
    lines = [json.dumps(r) for r in gh_raw() + lever_raw()] + ["{not json"]
    with TestPipeline() as p:
        out = p | beam.Create(lines) | beam.ParDo(NormalizeDoFn()).with_outputs(DEAD_LETTER, main="ok")
        assert_that(out.ok | "titles" >> beam.Map(lambda r: r["source_job_id"]),
                    equal_to(["1001", "1002", "1003", "1004", "a1b2c3", "d4e5f6", "g7h8i9"]), label="ok")
        assert_that(out[DEAD_LETTER] | beam.combiners.Count.Globally(), equal_to([2]), label="dead")
