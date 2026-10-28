"""Shared helpers for the ingestion jobs.

Every extractor writes newline-delimited JSON (NDJSON) so the files can be
loaded straight into BigQuery with `bq load --source_format=NEWLINE_DELIMITED_JSON`
or picked up by the Dataflow normalizer. Outputs go to a local path or to
`gs://` (when google-cloud-storage is installed and credentials are present).
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterable

USER_AGENT = "talent-analytics-gcp/1.0 (portfolio project; contact via GitHub)"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def http_get_json(url: str, retries: int = 3, backoff: float = 2.0) -> Any:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as err:  # noqa: BLE001 - retry any transport error
            last_err = err
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_err}")


def http_post_json(url: str, payload: dict, retries: int = 3, backoff: float = 2.0) -> Any:
    body = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as err:  # noqa: BLE001
            last_err = err
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"POST {url} failed after {retries} attempts: {last_err}")


def write_ndjson(records: Iterable[dict], destination: str) -> int:
    """Write records as NDJSON to a local file or a gs:// URI. Returns row count."""
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records]
    data = ("\n".join(lines) + "\n") if lines else ""

    if destination.startswith("gs://"):
        from google.cloud import storage  # imported lazily so local runs need no GCP libs

        bucket_name, _, blob_path = destination[len("gs://"):].partition("/")
        storage.Client().bucket(bucket_name).blob(blob_path).upload_from_string(
            data, content_type="application/x-ndjson"
        )
    else:
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        with open(destination, "w", encoding="utf-8") as fh:
            fh.write(data)
    return len(lines)
