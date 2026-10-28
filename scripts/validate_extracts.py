"""Validate dashboard extracts before they are published.

Runs the test plan in docs/reporting_spec.md section 4: privacy checks (no
employee-grain rows, no pay columns, small cells suppressed), range checks, and
reconciliation of every published number back to the warehouse by an
independent query. Writes reports/validation_report.md and exits non-zero if
any check fails, so the Makefile and CI stop before a bad extract goes out.

    python scripts/validate_extracts.py --db warehouse/talent.duckdb --extracts dashboard/extracts
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

MIN_CELL = 10
FORBIDDEN_COLUMNS = {"employee_key", "employee_number", "monthly_income", "annual_income", "avg_monthly_income"}
SIZE_COLUMNS = ("headcount", "denominator")
VALUE_COLUMNS = ("leavers", "numerator", "attrition_rate", "kpi_value", "ci_low", "ci_high", "lift_vs_company")
RATE_COLUMNS = ("attrition_rate", "kpi_value", "p_value", "p_adj_bh")
RATE_CI_COLUMNS = ("ci_low", "ci_high")  # proportions only where the file holds rates (odds-ratio CIs are not)

# mart_attrition_drivers uses display labels; the stats layer uses model column names.
DRIVER_MAP = {
    "overtime": ("works_overtime", {"Yes": "1", "No": "0"}),
    "promotion_stalled": ("is_promotion_stalled", {"Yes": "1", "No": "0"}),
    "pay_quartile_in_level": ("pay_quartile_in_level", None),
}


class Check:
    def __init__(self, cid: str, name: str):
        self.cid, self.name, self.failures = cid, name, []

    def fail(self, msg: str):
        self.failures.append(msg)

    @property
    def passed(self) -> bool:
        return not self.failures


# ------------------------------------------------------------ privacy and range checks (pure, unit-tested)

def check_forbidden_columns(extracts: dict[str, pd.DataFrame], c: Check) -> Check:
    for name, df in extracts.items():
        bad = FORBIDDEN_COLUMNS & set(df.columns)
        if bad:
            c.fail(f"{name}: forbidden column(s) {sorted(bad)}")
    return c


def check_small_cells(extracts: dict[str, pd.DataFrame], c: Check, min_cell: int = MIN_CELL) -> Check:
    for name, df in extracts.items():
        size_col = next((s for s in SIZE_COLUMNS if s in df.columns), None)
        if size_col is None:
            continue
        small = df[df[size_col] < min_cell]
        for col in (v for v in VALUE_COLUMNS if v in df.columns):
            leaked = small[col].notna().sum()
            if leaked:
                c.fail(f"{name}: {leaked} row(s) with {size_col} < {min_cell} expose {col}")
    return c


def check_ranges(extracts: dict[str, pd.DataFrame], c: Check) -> Check:
    for name, df in extracts.items():
        cols = list(RATE_COLUMNS) + (list(RATE_CI_COLUMNS) if "attrition_rate" in df.columns else [])
        for col in (r for r in cols if r in df.columns):
            s = df[col].dropna()
            if ((s < 0) | (s > 1)).any():
                c.fail(f"{name}.{col}: values outside [0, 1]")
        if {"ci_low", "ci_high", "attrition_rate"} <= set(df.columns):
            d = df.dropna(subset=["ci_low", "ci_high", "attrition_rate"])
            bad = ((d["ci_low"] > d["attrition_rate"] + 1e-12) | (d["ci_high"] < d["attrition_rate"] - 1e-12)).sum()
            if bad:
                c.fail(f"{name}: {bad} confidence interval(s) do not contain the rate")
        if {"ci_low", "ci_high", "odds_ratio"} <= set(df.columns):
            bad = ((df["ci_low"] > df["odds_ratio"]) | (df["ci_high"] < df["odds_ratio"])).sum()
            if bad:
                c.fail(f"{name}: {bad} odds-ratio interval(s) do not contain the estimate")
    return c


# ------------------------------------------------------------ reconciliation to the warehouse

def reconcile(extracts: dict[str, pd.DataFrame], con) -> list[Check]:
    headcount, leavers = con.sql(
        "select count(*), sum(is_attrited::int) from people_marts.dim_employee").fetchall()[0]
    checks = []

    c = Check("R1", "Company KPI matches an independent count from dim_employee")
    k = extracts["kpi_scorecard"]
    row = k[(k.kpi_id == "ATTR_RATE") & (k.slice_type == "company")].iloc[0]
    if (int(row.numerator), int(row.denominator)) != (leavers, headcount):
        c.fail(f"ATTR_RATE {row.numerator}/{row.denominator} vs warehouse {leavers}/{headcount}")
    early = con.sql("select count(*), sum(is_attrited::int) from people_marts.dim_employee "
                    "where years_at_company <= 2").fetchall()[0]
    row = k[(k.kpi_id == "EARLY_ATTR") & (k.slice_type == "company")].iloc[0]
    if (int(row.numerator), int(row.denominator)) != (early[1], early[0]):
        c.fail(f"EARLY_ATTR {row.numerator}/{row.denominator} vs warehouse {early[1]}/{early[0]}")
    checks.append(c)

    c = Check("R2", "Every breakdown sums back to company headcount")
    by_factor = extracts["attrition_by_factor"].groupby("factor")["headcount"].sum()
    for f, n in by_factor.items():
        if n != headcount:
            c.fail(f"attrition_by_factor.{f} sums to {n}, not {headcount}")
    for name in ("attrition_segments", "overtime_by_tenure"):
        n = extracts[name]["headcount"].sum()
        if n != headcount:
            c.fail(f"{name} sums to {n}, not {headcount}")
    for kpi, grp in k[k.slice_type == "department"].groupby("kpi_id"):
        company = k[(k.kpi_id == kpi) & (k.slice_type == "company")]["denominator"].iloc[0]
        if grp["denominator"].sum() != company:
            c.fail(f"{kpi}: department denominators sum to {grp['denominator'].sum()}, company is {company}")
    checks.append(c)

    c = Check("R3", "Stats-layer rates equal the dbt driver mart (two independent computations)")
    mart = con.sql("select factor, factor_level, headcount, attrition_rate from people_marts.mart_attrition_drivers").df()
    stats = extracts["attrition_by_factor"].copy()
    stats["factor_level"] = stats["factor_level"].astype(str)
    compared = 0
    for _, m in mart.iterrows():
        factor, level = m["factor"], str(m["factor_level"])
        if factor in DRIVER_MAP:
            factor, mapping = DRIVER_MAP[factor]
            level = mapping[level] if mapping else level.lstrip("Q")
        s = stats[(stats.factor == factor) & (stats.factor_level == level)]
        if s.empty:
            continue
        compared += 1
        s = s.iloc[0]
        if int(s.headcount) != int(m.headcount):
            c.fail(f"{factor}={level}: headcount {s.headcount} vs mart {m.headcount}")
        if pd.isna(m.attrition_rate) != pd.isna(s.attrition_rate) or (
                pd.notna(m.attrition_rate) and abs(m.attrition_rate - s.attrition_rate) > 1e-9):
            c.fail(f"{factor}={level}: rate {s.attrition_rate} vs mart {m.attrition_rate}")
    if compared < 40:
        c.fail(f"only {compared} factor levels matched between stats and mart; mapping may be broken")
    c.name += f" — {compared} levels compared"
    checks.append(c)
    return checks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="warehouse/talent.duckdb")
    ap.add_argument("--extracts", default="dashboard/extracts")
    ap.add_argument("--stats-dir", default="reports/stats")
    ap.add_argument("--out", default="reports/validation_report.md")
    args = ap.parse_args(argv)

    ex_dir = Path(args.extracts)
    manifest = json.loads((ex_dir / "manifest.json").read_text())
    extracts = {Path(f).stem: pd.read_csv(ex_dir / f) for f in manifest["files"]}

    checks = []
    c = Check("P1", "Files match the export manifest (no edits after export)")
    for f, meta in manifest["files"].items():
        if hashlib.sha256((ex_dir / f).read_bytes()).hexdigest() != meta["sha256"]:
            c.fail(f"{f}: checksum differs from manifest")
    checks.append(c)
    checks.append(check_forbidden_columns(extracts, Check("P2", "No employee identifiers or pay columns in any extract")))
    checks.append(check_small_cells(extracts, Check("P3", f"Groups under {MIN_CELL} people expose no counts or rates")))
    checks.append(check_ranges(extracts, Check("Q1", "Rates and p-values in [0, 1]; every interval contains its estimate")))

    con = duckdb.connect(args.db, read_only=True)
    checks += reconcile(extracts, con)
    con.close()

    c = Check("S1", "Python and R statistics agree (scripts/cross_check_stats.py)")
    cc_path = Path(args.stats_dir) / "cross_check.json"
    cc = json.loads(cc_path.read_text()) if cc_path.exists() else {"status": "not_run"}
    if cc["status"] != "pass":
        c.fail(f"cross-check status: {cc['status']}")
    else:
        c.name += f" — {cc['values_compared']} values"
    checks.append(c)

    passed = sum(ch.passed for ch in checks)
    L = ["# Extract validation report", "",
         f"_Generated {date.today().isoformat()} by `scripts/validate_extracts.py`. Test plan: `docs/reporting_spec.md` §4._", "",
         f"**{passed} of {len(checks)} checks passed.**", "",
         "| ID | Check | Result |", "|---|---|---|"]
    for ch in checks:
        L.append(f"| {ch.cid} | {ch.name} | {'pass' if ch.passed else 'FAIL'} |")
    fails = [ch for ch in checks if not ch.passed]
    if fails:
        L += ["", "## Failures", ""] + [f"- {ch.cid}: {m}" for ch in fails for m in ch.failures]
    Path(args.out).write_text("\n".join(L) + "\n")
    print(f"extract validation: {passed}/{len(checks)} checks passed -> {args.out}")
    for ch in fails:
        for m in ch.failures:
            print(f"  FAIL {ch.cid}: {m}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
