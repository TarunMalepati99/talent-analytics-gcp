"""Extract the HRIS snapshot.

Stand-in for a Workday/BambooHR employee export: IBM's public HR Analytics
Employee Attrition dataset (1,470 employees, 35 attributes). Note that IBM
describes it as a *fictional* dataset created by its data scientists, so
findings from it demonstrate the method, not facts about a real company.

The CSV is converted to NDJSON with snake_case keys and ingestion metadata so
the raw table schema is stable and explicit (config/schemas/hris_employees.json).

Usage:
    python -m ingestion.fetch_hris --out data/raw/hris/employees.ndjson
    python -m ingestion.fetch_hris --src data/raw/ibm_hr/emp_attrition.csv --out ...
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import urllib.request

from ingestion.common import USER_AGENT, utc_now_iso, write_ndjson

IBM_URL = "https://raw.githubusercontent.com/IBM/employee-attrition-aif360/master/data/emp_attrition.csv"

INT_COLUMNS = {
    "age", "daily_rate", "distance_from_home", "education", "employee_count", "employee_number",
    "environment_satisfaction", "hourly_rate", "job_involvement", "job_level", "job_satisfaction",
    "monthly_income", "monthly_rate", "num_companies_worked", "percent_salary_hike",
    "performance_rating", "relationship_satisfaction", "standard_hours", "stock_option_level",
    "total_working_years", "training_times_last_year", "work_life_balance", "years_at_company",
    "years_in_current_role", "years_since_last_promotion", "years_with_curr_manager",
}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name.strip()).lower()


def parse_csv(text: str, ingested_at: str) -> list[dict]:
    rows = []
    for raw in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        rec = {}
        for key, val in raw.items():
            col = snake(key)
            rec[col] = int(val) if col in INT_COLUMNS and val != "" else val
        rec["_source_system"] = "ibm_hr_attrition_public"
        rec["_ingested_at"] = ingested_at
        rows.append(rec)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=IBM_URL, help="URL or local path of the CSV")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.src.startswith("http"):
        req = urllib.request.Request(args.src, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8-sig")
    else:
        with open(args.src, encoding="utf-8-sig") as fh:
            text = fh.read()

    n = write_ndjson(parse_csv(text, utc_now_iso()), args.out)
    print(f"wrote {n} employee records to {args.out}")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
