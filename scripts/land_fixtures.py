"""Land the hand-written ATS test fixtures as if fetch_postings.py had produced them.

Used only by `make local` when the live job-board APIs aren't reachable, so the
Dataflow and dbt layers can be exercised end to end offline. Fixture boards are
named `fixture-*` and never appear in real loads.
"""

import json
import sys
from pathlib import Path

from ingestion.common import write_ndjson
from ingestion.fetch_postings import greenhouse_records, lever_records

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
INGESTED_AT = "2026-10-21 00:00:00"


def main(out: str) -> None:
    gh = json.loads((FIX / "greenhouse_fixture.json").read_text())
    lv = json.loads((FIX / "lever_fixture.json").read_text())
    records = list(greenhouse_records("fixture-greenhouse", gh, INGESTED_AT))
    records += list(lever_records("fixture-lever", lv, INGESTED_AT))
    print(f"landed {write_ndjson(records, out)} fixture postings -> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
