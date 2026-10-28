# Applying this pipeline to student retention and success

The project models employee attrition, but every layer maps one-to-one onto the
question a university student-affairs or institutional-research office asks:
*which students are we losing, why, and which programs help?* This note shows the
mapping and what would change.

## Concept map

| This project (HR) | Student success equivalent |
|---|---|
| Employee left (attrition flag) | Student not retained to the next fall / did not persist or graduate |
| Tenure band (< 1 yr, 1–2 yrs, …) | Class standing / term in program (first-year, transfer first term, …) |
| Overtime | Hours worked off campus, credit-load overload |
| Business travel | Commuter vs residential, distance from campus |
| Job level, department, job role | College / school, major, admit type |
| Job / environment satisfaction, work-life balance (1–4 survey items) | Belonging, well-being and engagement survey items (e.g., NSSE-style scales) |
| Promotion stalled | Stalled degree progress (credits earned vs expected) |
| Stock option level | Financial aid / scholarship tier |
| Age band, gender, marital status (audited, never used to score people) | First-generation, Pell eligibility, race/ethnicity, residency — reported in aggregate for equity gaps |
| BLS JOLTS industry benchmark | IPEDS / peer-institution retention and graduation rates |
| Greenhouse / Lever postings APIs | Campus systems via REST/JSON APIs (event check-ins, advising notes, housing, rec-center swipes) |
| Four-fifths fairness gate on risk scores | Equity check before any early-alert flag reaches advisors |
| Small-cell suppression (n < 10) | Same rule, as commonly applied under FERPA to stop students being identified from small groups |

## What carries over unchanged

- **Pipeline shape:** multiple sources → raw → dbt staging → marts → validated extracts → dashboard.
- **KPI scorecard:** `kpi_definitions.csv` becomes first-year retention, credit momentum (15+ credits/term),
  program participation rate, belonging-score share; one row per KPI × unit, with owners and targets.
- **Significance layer:** chi-square + Benjamini–Hochberg and a multivariable logistic regression answer
  "do students in program X persist at a significantly higher rate *after* accounting for admit type,
  first-gen status and credit load?" — the standard program-assessment question.
- **Validation gate:** reconcile every dashboard number to the student-record count, independent R/Python
  check, suppression check — before anything goes to unit directors or leadership.

## What would change

- **Privacy law:** FERPA instead of HR policy; access by unit and role through row-level security.
- **Program effects need a comparison group:** participants self-select, so assessment would add
  propensity-score matching or a regression with selection controls rather than raw participant vs
  non-participant rates.
- **Time dimension:** term-by-term panel data (fall-to-fall cohorts) instead of a single snapshot, so
  retention becomes a true cohort rate.
