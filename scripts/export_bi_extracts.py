"""Export dashboard-ready extracts for Tableau (Public or Desktop) and Power BI.

Only aggregated, suppressed tables leave the warehouse: no employee-grain rows,
no compensation columns, and every rate for a group under the minimum cell size
is blank. scripts/validate_extracts.py checks all of that, plus reconciliation
to the warehouse, before the files are used.

    python scripts/export_bi_extracts.py --db warehouse/talent.duckdb --out dashboard/extracts
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

MIN_CELL = 10
CAVEAT = ("HRIS data is IBM's public HR Analytics Employee Attrition dataset, which IBM describes as fictional; "
          "figures demonstrate the method, not a real company.")


def overtime_by_tenure(con) -> pd.DataFrame:
    df = con.sql("""
        select tenure_band,
               case when works_overtime then 'Overtime' else 'No overtime' end as overtime_group,
               count(*) as headcount,
               sum(is_attrited::int) as leavers
        from people_marts.dim_employee
        group by 1, 2 order by 1, 2""").df()
    small = df["headcount"] < MIN_CELL
    df["is_suppressed"] = small
    df["attrition_rate"] = (df["leavers"] / df["headcount"]).where(~small)
    df["leavers"] = df["leavers"].astype("Int64").where(~small)
    return df


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="warehouse/talent.duckdb")
    ap.add_argument("--stats-dir", default="reports/stats")
    ap.add_argument("--out", default="dashboard/extracts")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stats = Path(args.stats_dir)
    con = duckdb.connect(args.db, read_only=True)

    extracts: dict[str, pd.DataFrame] = {
        "kpi_scorecard": con.sql("""
            select kpi_id, kpi_name, slice_type, slice_value, is_suppressed, numerator, denominator,
                   kpi_value, target, direction, target_status, owner, definition
            from people_marts.mart_kpi_scorecard order by kpi_id, slice_type, slice_value""").df(),
        # Compensation (avg_monthly_income) is dropped: extracts may be published to Tableau Public.
        "attrition_segments": con.sql("""
            select department, job_role, role_family, tenure_band, headcount, is_suppressed, leavers, attrition_rate
            from people_marts.fct_attrition_segments order by department, job_role, tenure_band""").df(),
        "overtime_by_tenure": overtime_by_tenure(con),
        "attrition_by_factor": pd.read_csv(stats / "attrition_rates_ci.csv"),
        "significance_tests": pd.read_csv(stats / "chi_square_tests.csv"),
        "adjusted_odds_ratios": pd.read_csv(stats / "logit_odds_ratios.csv"),
    }
    con.close()

    files = {}
    for name, df in extracts.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        files[path.name] = {"rows": int(len(df)), "columns": list(df.columns),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "min_cell_size": MIN_CELL, "data_caveat": CAVEAT, "files": files}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(files)} extracts to {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
