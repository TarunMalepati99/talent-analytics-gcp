# Looker Studio dashboard spec

Three pages, one per audience. Every chart reads a dbt mart, never staging, so
small-cell suppression and policy-tag masking apply automatically: an HRBP who
is a *masked reader* sees `NULL` pay columns, and a department-scoped HRBP only
sees their department's rows (row access policies from `macros/apply_row_access.sql`).

Connect with the **BigQuery connector → "Viewer's credentials"** data source
setting, so BigQuery enforces each viewer's own access instead of the owner's.

## Page 1 — HR business partners: "Where are we losing people?"

| Chart | Source | Fields |
|---|---|---|
| Scorecard: company attrition | `people_marts.mart_attrition_drivers` | `company_rate` (any row) |
| Bar: lift by driver level (top 10) | `people_marts.mart_attrition_drivers` | dimension `factor_level`, metric `lift_vs_company`, filter `headcount >= 30`, sort desc |
| Heatmap table: department × tenure band | `people_marts.fct_attrition_segments` | rows `department`, `job_role`; columns `tenure_band`; metric `attrition_rate`; conditional colour; suppressed cells show blank |
| Table: segments ≥ 2× company rate | `people_marts.fct_attrition_segments` | filter `attrition_rate >= 0.32` |
| Controls | — | department, job role |

## Page 2 — Recruiting: "Where will backfills be hardest?"

| Chart | Source | Fields |
|---|---|---|
| Table with priority chips | `recruiting_marts.mart_replacement_pressure` | `role_family`, `attrition_rate`, `lift_vs_company`, `market_open_postings`, `priority` |
| Scatter: attrition lift vs market demand | `recruiting_marts.mart_replacement_pressure` | x `market_demand_pct_rank`, y `lift_vs_company`, bubble `headcount`, colour `priority` |
| Stacked bar: open postings by seniority | `recruiting_marts.mart_open_roles` | dimension `role_family`, breakdown `seniority`, metric `open_postings` |
| Scorecard: median days open | `recruiting_marts.mart_open_roles` | `median_days_open` |

## Page 3 — Finance / leadership: "How do we compare to the market?"

| Chart | Source | Fields |
|---|---|---|
| Bar: company vs JOLTS annual rate by industry | `people_marts.mart_attrition_vs_benchmark` | dimension `industry` + `benchmark_measure`, metrics `company_attrition_rate`, `benchmark_annual_rate` |
| Scorecard: model health | `ml.attrition_model_evaluation` | `roc_auc`, `evaluated_at` (HR analysts only) |
| Table: fairness audit | `ml.attrition_fairness_audit` | `attribute`, `adverse_impact_ratio` (HR analysts only) |
| Note box | — | Benchmark assumes the HRIS attrition flag is a 12-month window |

## Screenshots for the README

After the first BigQuery run, capture one screenshot per page into
`dashboard/screenshots/` and link them from the README. Hiring managers look
at these before they read code.
