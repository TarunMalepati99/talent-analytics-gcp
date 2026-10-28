"""Launcher for the postings normalizer (keeps the repo root on sys.path).

Composer's BeamRunPythonPipelineOperator runs a file, not a module, so it points
here; `--setup_file ./setup.py` ships the `pipelines` package to Dataflow workers.
"""
import logging

from pipelines.normalize_postings import run

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run()
