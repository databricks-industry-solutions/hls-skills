"""Shared fixtures: a Spark session (local in CI, the attached session on Databricks) and the
synthetic 837 files parsed once per test session."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_837  # noqa: E402
import x12_837  # noqa: E402


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession

    active = SparkSession.getActiveSession()
    if active is not None or os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        yield active or SparkSession.builder.getOrCreate()  # Databricks: reuse the attached session
        return
    session = (
        SparkSession.builder.master("local[2]")
        .config("spark.sql.ansi.enabled", "true")  # serverless default; bad input must not raise
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()


@pytest.fixture(scope="session")
def generated():
    return generate_837.build(seed=7, claims_per_file=6)


@pytest.fixture(scope="session")
def parsed(spark, generated):
    files, _ = generated
    raw = spark.createDataFrame([(f"/synthetic/{n}", c) for n, c in files.items()], "file_path string, value string")
    ctx = x12_837.segments(raw)
    checks = x12_837.transaction_checks(raw, ctx)
    out = x12_837.parse_837(ctx, checks)
    return {
        "checks": checks.collect(),
        "claims": {r["patient_control_number"]: r for r in out["claims"].collect()},
        "lines": out["claim_lines"].collect(),
        "dx": out["claim_diagnoses"].collect(),
    }
