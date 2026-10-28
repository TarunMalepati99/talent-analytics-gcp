# Design decisions

Short records of the choices an interviewer is most likely to ask about.

### 1. Land raw, normalize later
ATS payloads are stored untouched (`talent_raw.job_postings_raw`, partitioned by
ingest day). Normalization lives in Dataflow, so a parsing fix can be replayed
over history without re-calling the APIs, and the raw table is the audit trail.

### 2. Why Dataflow for postings but not for the HRIS file
The HRIS export is one well-typed CSV: a BigQuery load job is cheaper and simpler.
Postings come from two vendors with different shapes, timestamp formats (ISO with
offsets vs epoch milliseconds) and duplicates across daily loads; that's a
per-record transform + dedup, which is what Beam is for. Bad records go to a
dead-letter output instead of failing the job.

### 3. One dbt project, two targets
`dbt build --target local` (DuckDB) and `--target bigquery` run the same models.
The few dialect differences (safe divide, median, hashing) sit behind
`adapter.dispatch` macros in `macros/cross_db.sql`. This keeps CI free and fast
while BigQuery stays the production engine.

### 4. Privacy is enforced by the warehouse, not by convention
- **Pseudonymization:** the HRIS employee number never leaves staging; marts use
  a salted hash (`hash_key` macro, salt from Terraform).
- **Column-level security + dynamic masking:** compensation and demographic
  columns get Data Catalog policy tags (dbt post-hook). HR analysts see clear
  text; HRBPs see `NULL`/default values; nobody needs a separate "safe" copy.
- **Row-level security:** department-scoped HRBPs only see their department
  (`apply_row_access` post-hook, re-applied every run because rebuilds drop policies).
- **Small-cell suppression:** any segment under 10 people has its rates nulled,
  enforced by a dbt test so a refactor can't silently leak it.

### 5. Protected attributes are audited, not modelled
Age, gender and marital status are excluded from model features and used only
to audit outputs with the four-fifths rule. The DAG blocks publishing risk
scores when the audit fails. In this dataset it does fail on age band through
proxies (tenure, job level), which is exactly the case the gate exists for.

### 6. Deterministic train/eval split
BigQuery ML's `RANDOM` split changes every retrain, making week-over-week AUC
comparisons noisy. The split uses `FARM_FINGERPRINT(employee_key) % 5 = 0`, so
the same people are held out every time.

### 7. Benchmark assumption is written down, not hidden
IBM doesn't state the window behind its attrition flag. The benchmark mart
treats it as 12 months and says so in the SQL, the docs and the dashboard note.
With a real HRIS the mart would compute leavers ÷ average headcount from
termination dates instead.

### 8. Composer is optional in Terraform
Composer bills continuously, even when idle (typically a few hundred dollars a
month for a small environment; check the current Composer pricing page). `create_composer = false` by default: the same steps run from the
Makefile, and Composer is switched on only to demonstrate scheduled runs.
