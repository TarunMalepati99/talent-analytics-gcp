# Data dictionary

_Generated 2026-10-28 by `scripts/build_data_dictionary.py` from the dbt manifest and the built warehouse. Edit descriptions in the dbt yml files, not here._

Sensitivity `compensation` / `demographics` = column carries a BigQuery policy tag; masked readers see NULL. Rates in every aggregated mart are suppressed for groups under 10 people.

| Table | Schema | Rows | What it is |
|---|---|---:|---|
| [`dim_employee`](#dim_employee) | people_marts | 1470 | Employee-grain people table. Restricted dataset: analysts with the Fine-Grained Reader role see compensation and demographics; everyone else with access sees them masked. |
| [`fct_attrition_segments`](#fct_attrition_segments) | people_marts | 52 | Attrition by department x job role x tenure band, with small-cell suppression. |
| [`mart_attrition_drivers`](#mart_attrition_drivers) | people_marts | 49 | Attrition rate and lift vs the company rate for each level of each candidate driver. |
| [`mart_attrition_vs_benchmark`](#mart_attrition_vs_benchmark) | people_marts | 0 | Company attrition vs trailing-12-month BLS JOLTS quits and total separations, by industry. |
| [`mart_kpi_scorecard`](#mart_kpi_scorecard) | people_marts | 28 | KPI scorecard, one row per KPI x slice (company and each department). KPI names, definitions, targets and owners come from the kpi_definitions seed; numerators and denominators are defined in the model. Slices under the minimum cell size are suppressed. |
| [`mart_open_roles`](#mart_open_roles) | recruiting_marts | 0 | Open market postings by company board, role family and seniority (fixtures excluded by default). |
| [`mart_replacement_pressure`](#mart_replacement_pressure) | recruiting_marts | 5 | Internal attrition joined to external demand per role family, with a retention priority label. |

0 column(s) are not yet documented.

## dim_employee

Employee-grain people table. Restricted dataset: analysts with the Fine-Grained Reader role see compensation and demographics; everyone else with access sees them masked.

Table-level tests: assert_kpi_scorecard_reconciles

| Column | Type | Description | Sensitivity | Tests |
|---|---|---|---|---|
| `employee_key` | VARCHAR | Salted hash of the HRIS employee number. |  | not_null, unique |
| `department` | VARCHAR | HRIS department (Sales, Research & Development, Human Resources). |  |  |
| `job_role` | VARCHAR | HRIS job title. |  |  |
| `role_family` | VARCHAR | Job role mapped to a market role family (seed job_role_family_map). |  |  |
| `job_level` | BIGINT | Job level 1 (entry) to 5 (executive). |  |  |
| `tenure_band` | VARCHAR | Years at company banded as <1, 1-2, 3-5, 6-10, 10+. |  |  |
| `years_at_company` | BIGINT | Whole years at the company. |  |  |
| `years_since_last_promotion` | BIGINT | Whole years since the employee's last promotion. |  |  |
| `is_promotion_stalled` | BOOLEAN | True when years_since_last_promotion is at least var promotion_stall_years (5). |  |  |
| `works_overtime` | BOOLEAN | True when the HRIS overtime flag is Yes. |  |  |
| `business_travel` | VARCHAR | Non-Travel, Travel_Rarely or Travel_Frequently. |  |  |
| `pay_quartile_in_level` | BIGINT | Pay quartile among peers at the same job level (1 = lowest-paid quarter). |  | accepted_values |
| `monthly_income` | BIGINT | Monthly base pay. | compensation |  |
| `annual_income` | BIGINT | monthly_income x 12. | compensation |  |
| `stock_option_level` | BIGINT | Equity grant level (0-3). | compensation |  |
| `job_satisfaction` | BIGINT | Survey rating, 1 (low) to 4 (very high). |  |  |
| `environment_satisfaction` | BIGINT | Survey rating, 1 (low) to 4 (very high). |  |  |
| `work_life_balance` | BIGINT | Survey rating, 1 (bad) to 4 (best). |  |  |
| `education_level` | VARCHAR | Highest education, coded 1 Below College to 5 Doctor. |  |  |
| `education_field` | VARCHAR | Field of the employee's highest education. |  |  |
| `age_band` | VARCHAR | Age banded as <25, 25-34, 35-44, 45-54, 55+. | demographics |  |
| `gender` | VARCHAR | Gender as recorded in the HRIS. | demographics |  |
| `marital_status` | VARCHAR | Single, Married or Divorced. | demographics |  |
| `is_attrited` | BOOLEAN | True when the HRIS attrition flag is Yes (window undocumented by IBM; treated as 12 months). |  | not_null |

## fct_attrition_segments

Attrition by department x job role x tenure band, with small-cell suppression.

Table-level tests: assert_segments_reconcile_to_headcount, assert_small_cells_are_suppressed

| Column | Type | Description | Sensitivity | Tests |
|---|---|---|---|---|
| `segment_key` | VARCHAR | Hash of department | job role | tenure band. |  | not_null, unique |
| `department` | VARCHAR | HRIS department. |  |  |
| `job_role` | VARCHAR | HRIS job title. |  |  |
| `role_family` | VARCHAR | Market role family for the job role. |  |  |
| `tenure_band` | VARCHAR | Tenure band of the segment. |  |  |
| `headcount` | BIGINT | Employees in the segment. |  |  |
| `is_suppressed` | BOOLEAN | True when headcount is under var min_cell_size (10); rates are then null. |  |  |
| `leavers` | HUGEINT | Leavers in the segment (null when suppressed). |  |  |
| `attrition_rate` | DOUBLE | leavers / headcount (null when suppressed). |  | is_proportion |
| `avg_monthly_income` | DOUBLE | Average monthly pay in the segment (null when suppressed). | compensation |  |

## mart_attrition_drivers

Attrition rate and lift vs the company rate for each level of each candidate driver.

Table-level tests: assert_leavers_le_headcount, unique_combination

| Column | Type | Description | Sensitivity | Tests |
|---|---|---|---|---|
| `factor` | VARCHAR | Candidate driver (overtime, tenure_band, job_level, ...). |  |  |
| `factor_level` | VARCHAR | Level of the driver. |  |  |
| `headcount` | BIGINT | Employees at this level. |  |  |
| `leavers` | HUGEINT | Leavers at this level (null when suppressed). |  |  |
| `attrition_rate` | DOUBLE | leavers / headcount (null when suppressed). |  | is_proportion |
| `company_rate` | DOUBLE | Company-wide attrition rate. |  |  |
| `lift_vs_company` | DOUBLE | attrition_rate / company_rate; 2.0 means twice the company rate. |  |  |

## mart_attrition_vs_benchmark

Company attrition vs trailing-12-month BLS JOLTS quits and total separations, by industry.

| Column | Type | Description | Sensitivity | Tests |
|---|---|---|---|---|
| `industry` | VARCHAR | JOLTS industry. |  |  |
| `benchmark_measure` | VARCHAR | quits_rate or total_separations_rate. |  |  |
| `through_month` | DATE | Latest JOLTS month included. |  |  |
| `months_used` | BIGINT | Should be 12; fewer means BLS hasn't published a full year in the window. |  |  |
| `benchmark_annual_rate` | DOUBLE | Sum of the latest 12 monthly JOLTS rates, as a proportion. |  |  |
| `company_headcount` | BIGINT | Employees in the snapshot. |  |  |
| `company_attrition_rate` | DOUBLE | Company attrition rate (assumes a 12-month window). |  |  |
| `company_vs_benchmark_ratio` | DOUBLE | company_attrition_rate / benchmark_annual_rate. |  |  |

## mart_kpi_scorecard

KPI scorecard, one row per KPI x slice (company and each department). KPI names, definitions, targets and owners come from the kpi_definitions seed; numerators and denominators are defined in the model. Slices under the minimum cell size are suppressed.

Table-level tests: unique_combination

| Column | Type | Description | Sensitivity | Tests |
|---|---|---|---|---|
| `kpi_row_key` | VARCHAR | Hash of kpi_id | slice_type | slice_value. |  | not_null, unique |
| `kpi_id` | VARCHAR | KPI identifier (see seed kpi_definitions). |  | not_null |
| `kpi_name` | VARCHAR | Human-readable KPI name. |  |  |
| `slice_type` | VARCHAR | company or department. |  | accepted_values |
| `slice_value` | VARCHAR | All for the company row, otherwise the department name. |  |  |
| `is_suppressed` | BOOLEAN | True when the denominator is under var min_cell_size (10). |  |  |
| `numerator` | HUGEINT | Count meeting the KPI condition (null when suppressed). |  |  |
| `denominator` | HUGEINT | Population the KPI is measured over. |  |  |
| `kpi_value` | DOUBLE | numerator / denominator (null when suppressed). |  | is_proportion |
| `target` | DOUBLE | Target value from the seed (placeholder until agreed with the owner). |  |  |
| `direction` | VARCHAR | lower_is_better or higher_is_better. |  |  |
| `target_status` | VARCHAR | on target, off target or suppressed. |  | accepted_values |
| `owner` | VARCHAR | Team accountable for the KPI. |  |  |
| `definition` | VARCHAR | Plain-language definition shown in the dashboard tooltip. |  |  |

## mart_open_roles

Open market postings by company board, role family and seniority (fixtures excluded by default).

Table-level tests: unique_combination

| Column | Type | Description | Sensitivity | Tests |
|---|---|---|---|---|
| `company_board` | VARCHAR | Greenhouse or Lever board the postings came from (one per tracked company). |  |  |
| `role_family` | VARCHAR | Role family assigned by the Dataflow title classifier. |  |  |
| `seniority` | VARCHAR | Seniority assigned by the title classifier (intern, entry, mid, senior, lead, ...). |  |  |
| `open_postings` | BIGINT | Number of open postings in the group. |  |  |
| `remote_share` | DOUBLE | Share of the group's postings marked remote. |  | is_proportion |
| `median_days_open` | DOUBLE | Median days since posting, as of the run date. |  |  |
| `as_of` | TIMESTAMP | Latest ingestion timestamp in the group. |  |  |

## mart_replacement_pressure

Internal attrition joined to external demand per role family, with a retention priority label.

| Column | Type | Description | Sensitivity | Tests |
|---|---|---|---|---|
| `role_family` | VARCHAR | Role family shared by HRIS job roles and market postings. |  | not_null, unique |
| `headcount` | BIGINT | Employees in the role family. |  |  |
| `leavers` | HUGEINT | Leavers in the role family (null when suppressed). |  |  |
| `attrition_rate` | DOUBLE | leavers / headcount (null when suppressed). |  |  |
| `company_rate` | DOUBLE | Company-wide attrition rate. |  |  |
| `lift_vs_company` | DOUBLE | attrition_rate / company_rate (null when suppressed). |  |  |
| `market_open_postings` | HUGEINT | Open postings for the role family across tracked boards. |  |  |
| `market_entry_postings` | HUGEINT | Of those, postings at intern or entry seniority. |  |  |
| `market_demand_pct_rank` | DOUBLE | Percent rank of market_open_postings across role families (1 = most in demand). |  |  |
| `priority` | VARCHAR | act now (lift >= 1.25 and demand at or above median), monitor, stable or insufficient data. |  | accepted_values |
