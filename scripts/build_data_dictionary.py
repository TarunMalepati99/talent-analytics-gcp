"""Generate docs/data_dictionary.md from the dbt manifest and the built warehouse.

Descriptions, sensitivity tags and tests come from the dbt yml (via
dbt/target/manifest.json); column types and row counts come from the warehouse
itself. Regenerated every run, so the dictionary can't drift from the models.

    python scripts/build_data_dictionary.py --db warehouse/talent.duckdb
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb

MART_SCHEMAS = ("people_marts", "recruiting_marts")


def column_tests(manifest: dict) -> dict:
    """(model name, column) -> list of test names attached in yml."""
    tests = defaultdict(list)
    for node in manifest["nodes"].values():
        if node["resource_type"] != "test":
            continue
        meta = node.get("test_metadata") or {}
        col = node.get("column_name")
        for dep in node.get("depends_on", {}).get("nodes", []):
            model = dep.split(".")[-1]
            tests[(model, col)].append(meta.get("name", node["name"]))
            break
    return tests


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="warehouse/talent.duckdb")
    ap.add_argument("--manifest", default="dbt/target/manifest.json")
    ap.add_argument("--out", default="docs/data_dictionary.md")
    args = ap.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text())
    tests = column_tests(manifest)
    con = duckdb.connect(args.db, read_only=True)

    models = sorted(
        (n for n in manifest["nodes"].values()
         if n["resource_type"] == "model" and n["schema"].endswith(MART_SCHEMAS)),
        key=lambda n: (n["schema"], n["name"]),
    )

    L = [
        "# Data dictionary",
        "",
        f"_Generated {date.today().isoformat()} by `scripts/build_data_dictionary.py` from the dbt manifest and the built "
        "warehouse. Edit descriptions in the dbt yml files, not here._",
        "",
        "Sensitivity `compensation` / `demographics` = column carries a BigQuery policy tag; masked readers see NULL. "
        "Rates in every aggregated mart are suppressed for groups under 10 people.",
        "",
        "| Table | Schema | Rows | What it is |",
        "|---|---|---:|---|",
    ]
    undocumented = 0
    sections = []
    for node in models:
        schema, name = node["schema"], node["name"]
        try:
            rows = con.sql(f"select count(*) from {schema}.{name}").fetchall()[0][0]
            types = dict(con.sql(
                f"select column_name, data_type from information_schema.columns "
                f"where table_schema = '{schema}' and table_name = '{name}' order by ordinal_position").fetchall())
        except duckdb.Error:
            rows, types = None, {}
        L.append(f"| [`{name}`](#{name}) | {schema} | {rows if rows is not None else 'n/a'} | {node.get('description', '').strip()} |")

        model_tests = sorted({t for (m, c), ts in tests.items() if m == name and c is None for t in ts})
        S = [f"## {name}", "", node.get("description", "").strip(), ""]
        if model_tests:
            S += [f"Table-level tests: {', '.join(model_tests)}", ""]
        S += ["| Column | Type | Description | Sensitivity | Tests |", "|---|---|---|---|---|"]
        documented = node.get("columns", {})
        for col, dtype in types.items():
            info = documented.get(col, {})
            desc = (info.get("description") or "").strip()
            if not desc:
                undocumented += 1
            sens = ((info.get("config") or {}).get("meta") or {}).get("sensitivity") or (info.get("meta") or {}).get("sensitivity") or ""
            ctests = ", ".join(sorted(set(tests.get((name, col), []))))
            S.append(f"| `{col}` | {dtype} | {desc or '_not yet documented_'} | {sens} | {ctests} |")
        sections += S + [""]

    L += ["", f"{undocumented} column(s) are not yet documented.", ""] + sections
    Path(args.out).write_text("\n".join(L))
    print(f"wrote {args.out} ({len(models)} tables, {undocumented} undocumented columns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
