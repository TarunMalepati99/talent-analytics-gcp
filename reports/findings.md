# Findings — Talent Analytics Platform

_Generated 2026-10-28 by `scripts/build_findings.py`._

> **Data caveat.** The HRIS layer uses IBM's public HR Analytics Employee Attrition dataset, which IBM describes as fictional. These findings demonstrate the pipeline and method; they are not facts about a real company.

## 1. Baseline

- 1,470 employees, 237 leavers → **company attrition 16.1%**.

## 2. Strongest single drivers (lift vs company rate, groups ≥ 30 people)

| Factor | Level | Headcount | Attrition | Lift |
|---|---|---:|---:|---:|
| job_role | Sales Representative | 83 | 39.8% | 2.47× |
| tenure_band | 0: <1 yr | 44 | 36.4% | 2.26× |
| work_life_balance | 1 | 80 | 31.2% | 1.94× |
| overtime | Yes | 416 | 30.5% | 1.89× |
| tenure_band | 1: 1-2 yrs | 298 | 28.9% | 1.79× |
| job_level | 1 | 543 | 26.3% | 1.63× |
| environment_satisfaction | 1 | 284 | 25.4% | 1.57× |
| business_travel | Travel_Frequently | 277 | 24.9% | 1.55× |

## 3. The decision-grade finding: overtime × early tenure

| Tenure band | Overtime: n | Overtime: attrition | No overtime: n | No overtime: attrition |
|---|---:|---:|---:|---:|
| 0: <1 yr | 14 | 71.4% | 30 | 20.0% |
| 1: 1-2 yrs | 90 | 47.8% | 208 | 20.7% |
| 2: 3-5 yrs | 127 | 28.3% | 307 | 7.8% |
| 3: 6-10 yrs | 120 | 25.8% | 328 | 7.3% |
| 4: 10+ yrs | 65 | 10.8% | 181 | 7.2% |

Employees with **≤ 2 years' tenure who work overtime** are 104 people (7.1% of headcount) but 53 leavers (**22.4% of all attrition**), leaving at 51.0%. Overtime matters at every tenure band, and the percentage-point gap is widest for new hires — the recommendation is an overtime cap / workload review for employees in their first two years, owned by HRBPs with the people managers of the segments below.

**Is the effect really stronger for new hires?** On the absolute scale, yes: overtime adds 30.4 percentage points (95% CI 19.5–41.3) for ≤ 2 years' tenure vs 16.2 (95% CI 11.2–21.3) for longer tenure. On the odds scale, no: adjusted overtime odds ratios are 7.2 vs 5.2, and the interaction term is not significant (likelihood-ratio χ² = 0.78, p = 0.38). Overtime multiplies risk by a similar factor at every tenure; new hires lose more people from it because their baseline risk is higher. That still makes them the place to act first, but the claim is about volume, not a special effect.

## 4. Segments leaving at ≥ 2× the company rate (department × role × tenure)

| Department | Role | Tenure | Headcount | Attrition |
|---|---|---|---:|---:|
| Research & Development | Laboratory Technician | 0: <1 yr | 11 | 63.6% |
| Human Resources | Human Resources | 1: 1-2 yrs | 13 | 46.2% |
| Sales | Sales Representative | 2: 3-5 yrs | 24 | 45.8% |
| Sales | Sales Representative | 1: 1-2 yrs | 41 | 41.5% |
| Research & Development | Laboratory Technician | 1: 1-2 yrs | 77 | 36.4% |

19 small segments (86 employees) are suppressed (fewer than 10 people) to prevent re-identification.

## 5. Which differences are statistically significant?

Chi-square tests on 17 factors, Benjamini–Hochberg adjusted: **13 are significant** at α = 0.05. Not significant: pay_quartile_in_level, education_level, gender, is_promotion_stalled.

| Factor | Group | χ² (df) | Adjusted p | Cramér's V |
|---|---|---:|---:|---:|
| Works overtime | workplace | 89.0 (1) | 6.6e-20 | 0.25 (small) |
| Job role | workplace | 86.2 (8) | 2.3e-14 | 0.24 (small) |
| Job level | workplace | 72.5 (4) | 3.8e-14 | 0.22 (small) |
| Tenure band | workplace | 67.3 (4) | 3.6e-13 | 0.21 (small) |
| Age band | demographic | 64.9 (4) | 9.3e-13 | 0.21 (small) |
| Stock option level | workplace | 60.6 (3) | 1.2e-12 | 0.20 (small) |
| Marital status | demographic | 46.2 (2) | 2.3e-10 | 0.18 (small) |
| Business travel | workplace | 24.2 (2) | 1.2e-05 | 0.13 (small) |

Multivariable logistic regression (27 terms, McFadden pseudo-R² 0.29); strongest adjusted odds ratios, 95% CI:

| Term | Odds ratio | 95% CI | p |
|---|---:|---|---:|
| works_overtime | 5.75 | 4.04–8.18 | 2.6e-22 |
| job_level=1 | 3.64 | 2.28–5.81 | 6.4e-08 |
| age_band=<25 | 2.91 | 1.52–5.59 | 1.3e-03 |
| department=Sales | 2.83 | 1.91–4.18 | 1.9e-07 |
| stock_option_level=0 | 2.64 | 1.51–4.62 | 7.0e-04 |
| tenure_band=0: <1 yr | 2.46 | 1.05–5.74 | 3.8e-02 |
| is_promotion_stalled | 2.44 | 1.37–4.34 | 2.4e-03 |
| tenure_band=1: 1-2 yrs | 2.41 | 1.55–3.74 | 9.6e-05 |

Promotion stall shows why adjustment matters: on its own it isn't linked to attrition (adjusted p = 0.38), but holding tenure and level constant it raises the odds of leaving 2.4× — stalled employees tend to be long-tenured, which hides the effect.

Demographics are in the regression as controls only; the scoring model excludes them. Events per parameter: 8.8 (guideline ≈ 10), so small levels have wide intervals.

**Replication:** an independent base-R implementation was cross-checked against Python: **pass** on 178 values.

## 6. Attrition-risk model (local mirror of the BigQuery ML model)

- Logistic regression, class-balanced, protected attributes excluded from features; 1196 train / 274 held-out employees.
- Held-out **ROC AUC 0.895**, recall 0.841 and precision 0.416 at a 0.5 threshold.
- 100 of 1233 current employees score ≥ 0.7 (high risk).
- **Fairness gate (four-fifths rule on high-risk flags):**
  - gender: adverse-impact ratio 0.803 → pass
  - age_band: adverse-impact ratio 0.402 → **FAIL**

The gate fails: age_band '<25' is flagged 16.9% of the time vs 6.8% for '45-54'. Protected attributes are not features, so this comes through proxies such as tenure and job level. In the Composer DAG this check blocks `publish_segment_risk`, so HRBPs would get the descriptive marts above but not model scores until the proxy issue is addressed (e.g. dropping or constraining proxy features, or per-group thresholds reviewed with legal).

_Numbers from BigQuery ML itself will differ somewhat (different split hash and optimizer)._

## 7. External benchmark (BLS JOLTS)

Not loaded in this run. `make ingest` pulls live JOLTS data from the BLS API.

## 8. Replacement pressure (internal attrition × market demand)

Only offline test fixtures are loaded, so this section is left out. `make ingest` pulls live postings from the Greenhouse/Lever boards in `config/boards.yaml`.
