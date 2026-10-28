# Reporting specification — Attrition & Retention Dashboard

The contract between the people who use the dashboard and the pipeline that feeds
it: what questions it answers, where each number comes from, how it is defined,
who can see it, and how it is tested before release.

## 1. Requirements

Gathered as stakeholder questions; each maps to a page and a source table.

| # | Stakeholder | Question | Decision it supports | Page | Source |
|---|---|---|---|---|---|
| Q1 | HR leadership | Are we hitting our retention KPIs, company-wide and by department? | Where to focus retention budget this quarter | 1. KPI scorecard | `mart_kpi_scorecard` |
| Q2 | HR business partners | Which groups leave at a rate that is *statistically* above the company? | Which managers to engage first | 2. Drivers | `attrition_by_factor` (stats layer) |
| Q3 | HR business partners | Which factors still matter once the others are held constant? | Whether to act on overtime, travel, level or engagement | 2. Drivers | `adjusted_odds_ratios` |
| Q4 | People managers | Is overtime driving early-tenure exits, and by how much? | Overtime cap / workload review for new hires | 3. Overtime × tenure | `overtime_by_tenure`, `significance_summary.json` |
| Q5 | HR business partners | Which department × role × tenure segments are highest risk? | Targeted stay interviews | 4. Segments | `fct_attrition_segments` |
| Q6 | Finance | Is our attrition high for our industry? | Benchmark for planning | 5. Benchmark | `mart_attrition_vs_benchmark` (live JOLTS) |

Out of scope: individual risk scores (withheld until the model passes the fairness gate, see `docs/decisions.md` §5).

## 2. Data sources and lineage

| Source | Access | Refresh | Lands in | Notes |
|---|---|---|---|---|
| HRIS employee snapshot (IBM sample, fictional) | CSV over HTTPS | daily (DAG) | `talent_raw.hris_employees` | 1,470 employees, 35 attributes |
| BLS JOLTS | REST API, JSON | daily check; BLS publishes monthly | `talent_raw.bls_jolts` | quits and total separations by industry |
| Greenhouse / Lever job boards | REST API, JSON | daily | `talent_raw.job_postings_raw` → Dataflow | two schemas normalized and deduplicated |

`raw → staging (dbt views) → marts (dbt tables) → stats layer (Python, replicated in R) → extracts → dashboard`.
Lineage per column: `dbt docs generate && dbt docs serve`. Column definitions: `docs/data_dictionary.md`.

## 3. Metric definitions

KPIs are defined once in `dbt/seeds/kpi_definitions.csv` (name, definition, numerator,
denominator, direction, target, owner) and computed in `mart_kpi_scorecard`. Targets are
placeholders until each owner agrees them.

| Measure | Definition | Notes |
|---|---|---|
| Attrition rate | leavers ÷ headcount in the snapshot | IBM does not document the window; treated as 12 months |
| Lift | group attrition ÷ company attrition | 2.0 = twice the company rate |
| 95% CI on a rate | Wilson score interval | better than the normal approximation for small groups and rates near 0 |
| "Above company" flag | the group's CI lower bound is above the company rate | avoids flagging noise in small groups |
| Significance across levels | chi-square test of independence, Benjamini–Hochberg adjusted across all factors | effect size = Cramér's V |
| Adjusted odds ratio | multivariable logistic regression, Wald 95% CI | demographics included as controls for inference only |

## 4. Validation and test plan

Nothing is disseminated until every check passes. Run order: `make dbt` → `make stats` → `make bi`.

| ID | Layer | Test | Expected result | Automated in |
|---|---|---|---|---|
| D1 | dbt | Keys unique and not null; accepted values; relationships (KPI ids to seed) | 0 failing rows | `_people.yml`, `_recruiting.yml`, `_seeds.yml` |
| D2 | dbt | Every rate is a proportion in [0, 1] | 0 failing rows | `is_proportion` generic test |
| D3 | dbt | Segment and KPI totals reconcile to `dim_employee`; leavers ≤ headcount | 0 failing rows | `assert_segments_reconcile_to_headcount`, `assert_kpi_scorecard_reconciles`, `assert_leavers_le_headcount` |
| D4 | dbt | Segments under 10 people expose no rates or pay | 0 failing rows | `assert_small_cells_are_suppressed` |
| S1 | stats | Python and an independent R implementation agree (chi-square, BH-adjusted p, odds ratios, CIs, LRT) | relative diff < 1e-4, p-value diff < 1e-6 | `scripts/cross_check_stats.py` |
| P1 | extracts | Files unchanged since export | SHA-256 matches manifest | `scripts/validate_extracts.py` |
| P2 | extracts | No employee identifiers or pay columns | none present | same |
| P3 | extracts | Groups under 10 expose no counts or rates | none exposed | same |
| Q1 | extracts | Rates and p-values in [0, 1]; each CI contains its estimate | all true | same |
| R1 | extracts | Company KPIs equal an independent count from `dim_employee` | exact match | same |
| R2 | extracts | Every breakdown sums back to company headcount | exact match | same |
| R3 | extracts | Stats-layer rates equal the dbt driver mart (two separate computations) | diff < 1e-9 | same |
| M1 | manual | Dashboard spot-check: 3 KPI tiles and 3 bars match `reports/validation_report.md` sources | match | release checklist below |

Results: `reports/validation_report.md` (regenerated each run).

### Release checklist (manual, per dashboard version)
- [ ] `make local` green (dbt tests, R/Python cross-check, extract validation)
- [ ] Data caveat visible on every page
- [ ] M1 spot-check done and noted in the version log
- [ ] Tooltips show definitions from `kpi_definitions.csv`
- [ ] Viewer-credential / row-access check with a department-scoped test user (BigQuery target)

## 5. Access and privacy

- Employee-grain data stays in the warehouse; extracts are aggregates only.
- Pay and demographic columns carry BigQuery policy tags; pay never leaves the warehouse in extracts.
- Any group under 10 people is suppressed in every mart and extract (enforced by tests D4 and P3).
- Demographic results are reported only in aggregate, for equity monitoring, never to score individuals.

## 6. Known limitations

- The HRIS data is IBM's fictional sample; findings show the method, not facts about a company.
- One snapshot, no termination dates: rates are cross-sectional, not true 12-month turnover.
- The regression has about 8.8 events per parameter, slightly under the common 10-per-parameter guideline; estimates for small levels (job level 4–5, HR department) have wide intervals.
- Associations, not causes: an odds ratio for overtime does not prove overtime causes exits.
