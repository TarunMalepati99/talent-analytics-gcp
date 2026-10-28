from pathlib import Path

import pytest

from ingestion.fetch_hris import parse_csv, snake
from ingestion.fetch_jolts import parse_bls_response

ROOT = Path(__file__).resolve().parents[1]
IBM = ROOT / "data" / "raw" / "hris" / "employees.ndjson"


@pytest.mark.parametrize("src,dst", [
    ("EmployeeNumber", "employee_number"), ("OverTime", "over_time"),
    ("YearsWithCurrManager", "years_with_curr_manager"), ("Over18", "over18"),
])
def test_snake(src, dst):
    assert snake(src) == dst


def test_parse_csv_strips_bom_and_types_ints():
    text = "\ufeffAge,Attrition,EmployeeNumber,OverTime\n41,Yes,1,Yes\n"
    [row] = parse_csv(text, "2026-10-21 00:00:00")
    assert row["age"] == 41 and row["employee_number"] == 1 and row["over_time"] == "Yes"


@pytest.mark.skipif(not IBM.exists(), reason="run `make data` first")
def test_landed_hris_types_and_count():
    import json
    rows = [json.loads(l) for l in IBM.read_text().splitlines() if l.strip()]
    assert len(rows) == 1470
    assert isinstance(rows[0]["monthly_income"], int)
    assert rows[0]["attrition"] in {"Yes", "No"}
    assert len({r["employee_number"] for r in rows}) == 1470


def test_parse_bls_skips_annual_average_and_flags_preliminary():
    payload = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {"series": [{"seriesID": "JTS000000000000000QUR", "data": [
            {"year": "2026", "period": "M08", "value": "2.0", "footnotes": [{"code": "P", "text": "preliminary"}]},
            {"year": "2026", "period": "M07", "value": "1.9", "footnotes": [{}]},
            {"year": "2025", "period": "M13", "value": "2.0", "footnotes": []},
        ]}]},
    }
    rows = list(parse_bls_response(payload, "2026-10-21 00:00:00"))
    assert [r["period"] for r in rows] == ["M08", "M07"]
    assert rows[0]["is_preliminary"] is True and rows[1]["is_preliminary"] is False


def test_parse_bls_raises_on_api_error():
    with pytest.raises(RuntimeError):
        list(parse_bls_response({"status": "REQUEST_NOT_PROCESSED", "message": ["limit"]}, "x"))
