# Application answers built on this project

Only use the GCP answer **after** you have actually run the project on Google
Cloud (`make gcp-infra`, `gcp-ingest`, `gcp-load`, `gcp-normalize`, `gcp-dbt`,
the BQML scripts, and one Composer run). Interviewers ask follow-ups on every
tool you list. Fill the bracketed dates with when you really did it.

---

## "Describe a project: (1) HR/talent data source and your role, (2) stakeholders, (3) decision or outcome"

**(1)** I built a talent analytics platform on GCP over an HRIS employee
dataset (IBM's public HR Attrition data, 1,470 employees and 35 attributes,
standing in for a Workday-style export). I also used live job postings from
public Greenhouse and Lever ATS APIs and BLS JOLTS turnover data. I wrote the
extractors into Cloud Storage and a Dataflow job that normalizes two ATS
schemas and deduplicates postings. I modelled the warehouse in BigQuery with
dbt, with 35 data tests. I protected pay and demographic columns with policy
tags, dynamic masking, row-level security and small-cell suppression.

**(2)** I designed it for three audiences. HR business partners get attrition
by department, role and tenure. Recruiting gets which roles will be hardest to
backfill given market demand. Finance and leadership get company attrition
against the industry benchmark.

**(3)** The analysis isolated overtime in the first two years as the sharpest
attrition signal. That group is 7% of headcount but 22% of leavers, leaving at
51%, which supports a targeted workload and overtime review rather than a
company-wide retention spend. I also trained a BigQuery ML attrition model
(held-out AUC around 0.9) behind a four-fifths-rule fairness gate. The gate
caught an age-band proxy effect, so the pipeline publishes descriptive marts
but withholds individual risk scores until that's fixed.

*(Say it was a portfolio project on public data if asked; it is still a real pipeline.)*

---

## "Where did you gain your GCP experience?"

> Project-based. **Talent Analytics Platform (personal portfolio project), [Oct–Nov 2026]:**
> BigQuery (warehouse, partitioned raw tables, policy tags, data masking, row access policies),
> dbt on BigQuery, Dataflow (Apache Beam pipeline), Cloud Composer (Airflow DAG with
> quality and fairness gates), BigQuery ML (logistic regression, ML.EVALUATE,
> ML.GLOBAL_EXPLAIN), Cloud Storage, IAM and Data Catalog, all provisioned with Terraform.
> [Add any real Indiana University coursework that used GCP, with the course and term.]

---

## Resume bullet (after the GCP run)

- Built a GCP talent-analytics pipeline (GCS, Dataflow/Beam, BigQuery, dbt, Cloud Composer, BigQuery ML, Terraform) joining HRIS, ATS and BLS data. It surfaced an overtime-in-first-two-years segment that is 7% of headcount but 22% of attrition. It enforces column masking, row-level security and a four-fifths fairness gate on model outputs.

---

## Data analyst / assessment roles (e.g. higher-ed student life, institutional research)

**"Tell me about a time you used statistics to show which factors matter."**
I tested 17 workplace and demographic factors against attrition with chi-square
tests, corrected for multiple comparisons with Benjamini–Hochberg, and fitted a
multivariable logistic regression to get adjusted odds ratios. Overtime held up
(odds ratio about 5.8 after controlling for everything else). I also tested the
team's headline claim that overtime hurts new hires *more*: the interaction was
not significant, so I reframed it. New hires lose more people because their
baseline risk is higher, not because overtime affects them differently. I
replicated the whole analysis in R and wrote a cross-check that fails the build
if Python and R disagree.

**"How do you make sure numbers are right before they go out?"**
dbt tests on every mart, reconciliation tests that the KPI scorecard sums back to
the employee table, and a validation gate on the dashboard extracts: no IDs or
pay columns, no group under 10 people exposed, every number re-derived from the
warehouse by a separate query. Results go into a validation report with each
release (`reports/validation_report.md`).

**"How would this apply to student success?"** See `docs/higher_ed_translation.md`:
attrition becomes non-retention, tenure becomes class standing, satisfaction items
become belonging survey items, the JOLTS benchmark becomes IPEDS peers, and the
suppression rule is the same one used for FERPA reporting.

*Only claim Tableau or Power BI after you've built the dashboard from
`dashboard/tableau_powerbi.md` and published it.*
