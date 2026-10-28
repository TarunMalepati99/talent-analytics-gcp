"""Extract BLS JOLTS (Job Openings and Labor Turnover Survey) rates.

These are the external benchmark: national monthly quits, hires and
job-openings rates, overall and for the industries closest to the HRIS data.
Series IDs are configured in config/jolts_series.yaml. A free BLS API key
(BLS_API_KEY env var) raises the request limit and allows 20 years per call;
without it the v2 API still works with lower limits.

Usage:
    python -m ingestion.fetch_jolts --out data/raw/jolts/jolts.ndjson
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from typing import Iterator

import yaml

from ingestion.common import http_post_json, utc_now_iso, write_ndjson

BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def parse_bls_response(payload: dict, ingested_at: str) -> Iterator[dict]:
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API error: {payload.get('message')}")
    for series in payload["Results"]["series"]:
        sid = series["seriesID"]
        for obs in series["data"]:
            period = obs["period"]  # M01..M12; M13 is an annual average we skip
            if not period.startswith("M") or period == "M13":
                continue
            value = obs["value"]
            yield {
                "series_id": sid,
                "year": int(obs["year"]),
                "period": period,
                "value": None if value in ("-", "") else float(value),
                "is_preliminary": any(f.get("code") == "P" for f in obs.get("footnotes", []) if f),
                "ingested_at": ingested_at,
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/jolts_series.yaml")
    parser.add_argument("--out", required=True)
    parser.add_argument("--start-year", type=int, default=date.today().year - 4)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as fh:
        series_ids = [s["id"] for s in yaml.safe_load(fh)["series"]]

    body = {"seriesid": series_ids, "startyear": str(args.start_year), "endyear": str(args.end_year)}
    if os.environ.get("BLS_API_KEY"):
        body["registrationkey"] = os.environ["BLS_API_KEY"]

    rows = list(parse_bls_response(http_post_json(BLS_URL, body), utc_now_iso()))
    n = write_ndjson(rows, args.out)
    print(f"wrote {n} JOLTS observations to {args.out}")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
