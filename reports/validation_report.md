# Extract validation report

_Generated 2026-10-28 by `scripts/validate_extracts.py`. Test plan: `docs/reporting_spec.md` §4._

**8 of 8 checks passed.**

| ID | Check | Result |
|---|---|---|
| P1 | Files match the export manifest (no edits after export) | pass |
| P2 | No employee identifiers or pay columns in any extract | pass |
| P3 | Groups under 10 people expose no counts or rates | pass |
| Q1 | Rates and p-values in [0, 1]; every interval contains its estimate | pass |
| R1 | Company KPI matches an independent count from dim_employee | pass |
| R2 | Every breakdown sums back to company headcount | pass |
| R3 | Stats-layer rates equal the dbt driver mart (two independent computations) — 49 levels compared | pass |
| S1 | Python and R statistics agree (scripts/cross_check_stats.py) — 178 values | pass |
