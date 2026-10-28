# Tableau / Power BI build guide

The Looker Studio spec (`looker_studio.md`) reads BigQuery directly. This guide
builds the same story in **Tableau Public** (free) or **Power BI Desktop** from the
validated CSV extracts in `dashboard/extracts/`, so it can be published and linked
from a resume without a GCP account.

Regenerate and validate the extracts first:

```bash
make local          # or: make stats bi
cat reports/validation_report.md   # must say every check passed
```

| Extract | Grain | Use |
|---|---|---|
| `kpi_scorecard.csv` | KPI × slice (company, department) | Page 1 tiles and table |
| `attrition_by_factor.csv` | factor × level, with Wilson 95% CI | Page 2 bars with error bars |
| `adjusted_odds_ratios.csv` | model term | Page 2 forest plot |
| `significance_tests.csv` | factor | Page 2 "is it significant?" table |
| `overtime_by_tenure.csv` | tenure band × overtime group | Page 3 |
| `attrition_segments.csv` | department × role × tenure | Page 4 heatmap |

Every extract is aggregated, contains no pay columns, and blanks any group under 10 people.
Put this caveat in a text box on every page: *"IBM sample HR data (fictional). Demonstrates method, not a real company."*

## Page 1 — KPI scorecard (stakeholder Q1)

- **Tiles:** filter `slice_type = company`; one tile per `kpi_name` showing `kpi_value` as %, with `target` underneath.
- **Status:** show `target_status` as a text label plus an icon (✓ / !), not colour alone.
- **Table:** rows `kpi_name`, columns `slice_value` (departments), value `kpi_value`. Suppressed cells show "<10".
- **Tooltip:** `definition`, `numerator`/`denominator`, `owner`.
- Tableau calculated field: `IF [is_suppressed] THEN "<10" ELSE STR(ROUND([kpi_value]*100,1)) + "%" END`.

## Page 2 — What drives attrition? (Q2, Q3)

- **Bar chart with error bars:** `attrition_by_factor`, filter `factor` with a single-select parameter
  (default `works_overtime`). Bars = `attrition_rate`; error bars from `ci_low` to `ci_high`
  (Tableau: dual-axis Gantt bar sized `ci_high - ci_low` starting at `ci_low`, synchronized axes;
  Power BI: error bars on the bar visual, upper/lower = `ci_high`/`ci_low`).
  Reference line at `company_rate`. Use `level_label` for the axis.
- **Colour:** `vs_company` (above / within / below) — label it in the legend.
- **Forest plot:** `adjusted_odds_ratios`, rows `term`, point `odds_ratio`, whisker `ci_low`–`ci_high`,
  **log x-axis**, reference line at 1. Filled marks where `significant` is true.
  `reports/figures/adjusted_odds_ratios.png` is the reference rendering.
- **Significance table:** `significance_tests` sorted by `cramers_v`: label, `p_adj_bh`, `cramers_v`, `effect_size`.

## Page 3 — Overtime × tenure (Q4)

- Side-by-side bars: x `tenure_band`, colour `overtime_group`, y `attrition_rate`.
- Text box with the numbers from `reports/stats/significance_summary.json` → `overtime_x_early_tenure`:
  the percentage-point gap for ≤ 2 years vs > 2 years, and the interaction test result.
  Say plainly: overtime multiplies the odds of leaving at every tenure; the interaction isn't
  significant, so new hires stand out because their baseline risk is higher.

## Page 4 — Segments (Q5)

- Highlight table: rows `department`, `job_role`; columns `tenure_band`; colour `attrition_rate`
  (one sequential hue, light → dark). Suppressed cells blank with a "<10" label.

## Publishing

- Tableau Public: *File → Save to Tableau Public*. Add the link to the README and resume.
- Power BI: publishing to web requires a work account; otherwise export the `.pbix` and PDF screenshots.
- Save one screenshot per page to `dashboard/screenshots/` and link them from the README.
