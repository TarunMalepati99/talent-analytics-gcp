"""Apache Beam pipeline: normalize raw ATS postings into one BigQuery table.

Runs locally with the DirectRunner (used by `make local`) and on Google Cloud
Dataflow with `--runner DataflowRunner` (used by the Composer DAG).

    # local
    python -m pipelines.normalize_postings \
        --input 'data/raw/postings/*.ndjson' --output data/staged/postings_normalized

    # Dataflow
    python -m pipelines.normalize_postings \
        --runner DataflowRunner --project $PROJECT --region us-central1 \
        --temp_location gs://$BUCKET/tmp --setup_file ./setup.py \
        --input 'gs://$BUCKET/raw/postings/dt=*/*.ndjson' \
        --output_table $PROJECT:talent_raw.job_postings_normalized \
        --dead_letter gs://$BUCKET/dead_letter/postings

Steps: read NDJSON -> parse -> normalize per source (bad rows to dead letter)
-> key by posting_key -> keep latest ingest per posting -> write.
"""

from __future__ import annotations

import argparse
import json
import logging

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions

from pipelines.postings_transforms import latest, normalize_record

BQ_SCHEMA = {
    "fields": [
        {"name": "posting_key", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source", "type": "STRING", "mode": "REQUIRED"},
        {"name": "board", "type": "STRING", "mode": "REQUIRED"},
        {"name": "source_job_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "title", "type": "STRING", "mode": "REQUIRED"},
        {"name": "department", "type": "STRING", "mode": "NULLABLE"},
        {"name": "team", "type": "STRING", "mode": "NULLABLE"},
        {"name": "location", "type": "STRING", "mode": "NULLABLE"},
        {"name": "workplace_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "is_remote", "type": "BOOL", "mode": "NULLABLE"},
        {"name": "role_family", "type": "STRING", "mode": "REQUIRED"},
        {"name": "seniority", "type": "STRING", "mode": "REQUIRED"},
        {"name": "posted_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "updated_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "url", "type": "STRING", "mode": "NULLABLE"},
        {"name": "ingested_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ]
}

DEAD_LETTER = "dead_letter"


class NormalizeDoFn(beam.DoFn):
    def process(self, line: str):
        try:
            yield normalize_record(json.loads(line))
        except Exception as err:  # noqa: BLE001 - every bad row goes to the dead letter
            yield beam.pvalue.TaggedOutput(DEAD_LETTER, json.dumps({"error": str(err), "line": line[:2000]}))


def build(pipeline: beam.Pipeline, input_glob: str, output: str | None,
          output_table: str | None, dead_letter: str | None) -> None:
    results = (
        pipeline
        | "ReadRaw" >> beam.io.ReadFromText(input_glob)
        | "DropBlank" >> beam.Filter(lambda l: l.strip())
        | "Normalize" >> beam.ParDo(NormalizeDoFn()).with_outputs(DEAD_LETTER, main="ok")
    )

    deduped = (
        results.ok
        | "KeyByPosting" >> beam.Map(lambda r: (r["posting_key"], r))
        | "GroupByPosting" >> beam.GroupByKey()
        | "KeepLatest" >> beam.Map(lambda kv: latest(list(kv[1])))
    )

    if output_table:
        deduped | "WriteBQ" >> beam.io.WriteToBigQuery(
            output_table,
            schema=BQ_SCHEMA,
            write_disposition=beam.io.BigQueryDisposition.WRITE_TRUNCATE,
            create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED,
        )
    if output:
        (deduped
         | "ToJson" >> beam.Map(lambda r: json.dumps(r, sort_keys=True))
         | "WriteLocal" >> beam.io.WriteToText(output, file_name_suffix=".ndjson", shard_name_template=""))
    if dead_letter:
        results[DEAD_LETTER] | "WriteDeadLetter" >> beam.io.WriteToText(
            dead_letter, file_name_suffix=".ndjson", shard_name_template="")


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="NDJSON glob (local or gs://)")
    parser.add_argument("--output", help="local/GCS prefix for NDJSON output")
    parser.add_argument("--output_table", help="BigQuery table PROJECT:DATASET.TABLE")
    parser.add_argument("--dead_letter", help="prefix for rows that failed to normalize")
    known, beam_args = parser.parse_known_args(argv)
    if not (known.output or known.output_table):
        parser.error("give --output and/or --output_table")

    options = PipelineOptions(beam_args)
    options.view_as(SetupOptions).save_main_session = False
    with beam.Pipeline(options=options) as p:
        build(p, known.input, known.output, known.output_table, known.dead_letter)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run()
