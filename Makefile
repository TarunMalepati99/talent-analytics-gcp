# Talent Analytics Platform — common tasks.
#   make local     full offline run: HRIS + test-fixture postings -> Beam -> DuckDB -> dbt -> model -> findings
#   make ingest    pull LIVE postings (Greenhouse/Lever) and BLS JOLTS to data/raw, then rebuild locally
#   make stats     significance tests + regression (Python), independent R replication, cross-check
#   make bi        Tableau/Power BI extracts + validation gate (fails on any privacy or reconciliation error)
#   make test      unit tests (ingestion parsers, Beam transforms, DAG integrity, stats, extract checks)
#   make gcp-*     see README "Run it on Google Cloud"

PY      ?= python3
export PYTHONPATH := $(CURDIR)
DB      := warehouse/talent.duckdb
DBT     := cd dbt && DBT_PROFILES_DIR=. dbt

.PHONY: local ingest data fixtures normalize load dbt model stats findings bi brief docs test clean \
        gcp-infra gcp-ingest gcp-load gcp-normalize gcp-dbt gcp-deploy-dags

local: data fixtures normalize load dbt model stats findings bi brief docs

data:
	$(PY) -m ingestion.fetch_hris --out data/raw/hris/employees.ndjson

fixtures:
	$(PY) scripts/land_fixtures.py data/raw/postings/postings_fixture.ndjson

ingest: data
	rm -f data/raw/postings/postings_fixture.ndjson
	$(PY) -m ingestion.fetch_postings --out data/raw/postings/postings_raw.ndjson
	$(PY) -m ingestion.fetch_jolts --out data/raw/jolts/jolts.ndjson
	$(MAKE) normalize load dbt model stats findings bi brief docs

normalize:
	$(PY) -m pipelines.normalize_postings --input 'data/raw/postings/*.ndjson' \
		--output data/staged/postings_normalized --dead_letter data/staged/dead_letter_postings

load:
	$(PY) scripts/load_local_duckdb.py --db $(DB)

dbt:
	$(DBT) seed --quiet
	$(DBT) build --vars '{policy_tags_dry_run: true}'

model:
	$(PY) bqml/local_mirror.py --db $(DB) --out reports/model_local_mirror.json > /dev/null

stats:
	$(PY) analysis/attrition_significance.py --db $(DB)
	@if command -v Rscript >/dev/null 2>&1; then \
		Rscript analysis/r/attrition_significance.R warehouse/analysis_base.csv analysis/model_spec.csv reports/stats; \
	else echo "Rscript not found: skipping the R replication (the cross-check will report not_run)"; fi
	$(PY) scripts/cross_check_stats.py --stats-dir reports/stats
	$(PY) analysis/plot_odds_ratios.py

findings:
	$(PY) scripts/build_findings.py --db $(DB)

bi:
	$(PY) scripts/export_bi_extracts.py --db $(DB) --out dashboard/extracts
	$(PY) scripts/validate_extracts.py --db $(DB) --extracts dashboard/extracts

brief:
	$(PY) scripts/build_brief.py --db $(DB)

docs:
	$(PY) scripts/build_data_dictionary.py --db $(DB)

test:
	$(PY) -m pytest -q

clean:
	rm -rf warehouse data/staged dbt/target dbt/logs

# ---------------- Google Cloud ----------------
# Needs: gcloud auth application-default login; GCP_PROJECT and BUCKET set; terraform applied.
GCP_PROJECT ?= $(shell gcloud config get-value project 2>/dev/null)
BUCKET      ?= $(GCP_PROJECT)-talent-lake
REGION      ?= us-central1
DT          := $(shell date -u +%F)

gcp-infra:
	cd terraform && terraform init && terraform apply

gcp-ingest:
	$(PY) -m ingestion.fetch_hris     --out gs://$(BUCKET)/raw/hris/dt=$(DT)/employees.ndjson
	$(PY) -m ingestion.fetch_postings --out gs://$(BUCKET)/raw/postings/dt=$(DT)/postings_raw.ndjson
	$(PY) -m ingestion.fetch_jolts    --out gs://$(BUCKET)/raw/jolts/dt=$(DT)/jolts.ndjson

gcp-load:
	bq load --replace --source_format=NEWLINE_DELIMITED_JSON talent_raw.hris_employees gs://$(BUCKET)/raw/hris/dt=$(DT)/*.ndjson config/schemas/hris_employees.json
	bq load --replace --source_format=NEWLINE_DELIMITED_JSON talent_raw.bls_jolts gs://$(BUCKET)/raw/jolts/dt=$(DT)/*.ndjson config/schemas/jolts.json
	bq load --source_format=NEWLINE_DELIMITED_JSON --time_partitioning_field=ingested_at talent_raw.job_postings_raw gs://$(BUCKET)/raw/postings/dt=$(DT)/*.ndjson config/schemas/postings_raw.json

gcp-normalize:
	$(PY) run_normalize_postings.py --runner DataflowRunner --project $(GCP_PROJECT) --region $(REGION) \
		--temp_location gs://$(BUCKET)/tmp/dataflow --setup_file ./setup.py \
		--service_account_email talent-pipeline@$(GCP_PROJECT).iam.gserviceaccount.com \
		--input 'gs://$(BUCKET)/raw/postings/dt=*/*.ndjson' \
		--output_table $(GCP_PROJECT):talent_raw.job_postings_normalized \
		--dead_letter gs://$(BUCKET)/dead_letter/postings/dt=$(DT)/rows

gcp-dbt:
	cd dbt && DBT_TARGET=bigquery GCP_PROJECT=$(GCP_PROJECT) DBT_PROFILES_DIR=. \
		EMPLOYEE_KEY_SALT="$$(cd ../terraform && terraform output -raw employee_key_salt)" \
		dbt build --vars "{policy_tag_compensation: '$$(cd ../terraform && terraform output -raw policy_tag_compensation)', policy_tag_demographics: '$$(cd ../terraform && terraform output -raw policy_tag_demographics)'}"

gcp-deploy-dags:
	scripts/deploy_composer.sh
