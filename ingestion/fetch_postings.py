"""Extract open job postings from public Greenhouse and Lever job-board APIs.

These are the same public endpoints that power companies' careers pages, so no
credentials are needed. Records are landed *raw* (the full JSON payload as a
string) with ingestion metadata; normalization into one schema happens in the
Dataflow job (dataflow/normalize_postings.py). Keeping the raw payload means a
parsing bug can be fixed and replayed without re-calling the APIs.

Usage:
    python -m ingestion.fetch_postings --config config/boards.yaml \
        --out data/raw/postings/postings_raw.ndjson
    python -m ingestion.fetch_postings --out gs://BUCKET/raw/postings/dt=2026-10-21/postings_raw.ndjson
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterator

import yaml

from ingestion.common import http_get_json, utc_now_iso, write_ndjson

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
LEVER_URL = "https://api.lever.co/v0/postings/{board}?mode=json"


def greenhouse_records(board: str, payload: dict, ingested_at: str) -> Iterator[dict]:
    for job in payload.get("jobs", []):
        yield {
            "source": "greenhouse",
            "board": board,
            "source_job_id": str(job.get("id")),
            "payload": json.dumps(job, ensure_ascii=False),
            "ingested_at": ingested_at,
        }


def lever_records(board: str, payload: list, ingested_at: str) -> Iterator[dict]:
    for job in payload or []:
        yield {
            "source": "lever",
            "board": board,
            "source_job_id": str(job.get("id")),
            "payload": json.dumps(job, ensure_ascii=False),
            "ingested_at": ingested_at,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/boards.yaml")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    ingested_at = utc_now_iso()
    records: list[dict] = []
    failures: list[str] = []

    for board in cfg.get("greenhouse", []):
        try:
            records.extend(greenhouse_records(board, http_get_json(GREENHOUSE_URL.format(board=board)), ingested_at))
        except RuntimeError as err:
            failures.append(f"greenhouse/{board}: {err}")

    for board in cfg.get("lever", []):
        try:
            records.extend(lever_records(board, http_get_json(LEVER_URL.format(board=board)), ingested_at))
        except RuntimeError as err:
            failures.append(f"lever/{board}: {err}")

    n = write_ndjson(records, args.out)
    print(f"wrote {n} raw postings to {args.out}")
    for f in failures:
        print(f"WARN {f}", file=sys.stderr)
    # Fail the task only if every board failed; partial loads are still useful.
    return 1 if failures and not records else 0


if __name__ == "__main__":
    sys.exit(main())
