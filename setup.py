"""Packages the pipeline code so Dataflow workers can import it (--setup_file ./setup.py)."""
import setuptools

setuptools.setup(
    name="talent-analytics-pipelines",
    version="1.0.0",
    packages=["pipelines", "ingestion"],
    install_requires=["pyyaml>=6"],
)
