"""Load landed NDJSON into a local DuckDB file that mirrors the BigQuery `talent_raw` dataset.

This is the local equivalent of the GCSToBigQueryOperator tasks in the Composer
DAG: same table names, same column types (from config/schemas/*.json), so the
dbt project runs unchanged against either target.

    python scripts/load_local_duckdb.py --db warehouse/talent.duckdb
"""

import argparse
import glob
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
BQ_TO_DUCK = {"STRING": "VARCHAR", "INT64": "BIGINT", "FLOAT64": "DOUBLE", "BOOL": "BOOLEAN", "TIMESTAMP": "TIMESTAMP"}

TABLES = {
    # table name: (schema file, landing glob)
    "hris_employees": ("hris_employees.json", "data/raw/hris/*.ndjson"),
    "bls_jolts": ("jolts.json", "data/raw/jolts/*.ndjson"),
    "job_postings_normalized": (None, "data/staged/postings_normalized*.ndjson"),
}

POSTINGS_COLUMNS = {
    "posting_key": "VARCHAR", "source": "VARCHAR", "board": "VARCHAR", "source_job_id": "VARCHAR",
    "title": "VARCHAR", "department": "VARCHAR", "team": "VARCHAR", "location": "VARCHAR",
    "workplace_type": "VARCHAR", "is_remote": "BOOLEAN", "role_family": "VARCHAR", "seniority": "VARCHAR",
    "posted_at": "TIMESTAMP", "updated_at": "TIMESTAMP", "url": "VARCHAR", "ingested_at": "TIMESTAMP",
}


def columns_for(schema_file):
    if schema_file is None:
        return POSTINGS_COLUMNS
    fields = json.loads((ROOT / "config" / "schemas" / schema_file).read_text())
    return {f["name"]: BQ_TO_DUCK[f["type"]] for f in fields}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/talent.duckdb")
    ap.add_argument("--schema", default="talent_raw")
    args = ap.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(args.db)
    con.execute(f"create schema if not exists {args.schema}")

    for table, (schema_file, pattern) in TABLES.items():
        cols = columns_for(schema_file)
        col_ddl = ", ".join(f'"{c}" {t}' for c, t in cols.items())
        con.execute(f"create or replace table {args.schema}.{table} ({col_ddl})")
        files = sorted(glob.glob(str(ROOT / pattern)))
        if files:
            struct = "{" + ", ".join(f"'{c}': '{t}'" for c, t in cols.items()) + "}"
            con.execute(
                f"insert into {args.schema}.{table} select * from read_json(?, format='newline_delimited', columns={struct})",
                [files],
            )
        n = con.execute(f"select count(*) from {args.schema}.{table}").fetchone()[0]
        print(f"{args.schema}.{table}: {n} rows" + ("" if files else "  (no landed files; table created empty)"))
    con.close()


if __name__ == "__main__":
    main()
