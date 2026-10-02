# Databricks notebook source
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # OSS-Models Skill — Structural Tests (Offline Gate)
# MAGIC
# MAGIC Runs 44 offline checks against `.assistant/skills/oss-models/`.
# MAGIC No network, no GPU, no model weights needed.
# MAGIC
# MAGIC **Checks:** JSON/YAML block parsing, provenance manifest keys,
# MAGIC SKILL.md worked example, per-model input example headings (6 models
# MAGIC incl. TEDDY), malformed URL detection.

# COMMAND ----------

# DBTITLE 1,Install PyYAML
# MAGIC %pip install -q pyyaml
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Run structural tests
import subprocess, sys, os

# Resolve skill path relative to this notebook
NB_DIR = os.path.dirname(os.path.abspath(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()))
SKILL_DIR = os.path.join("/Workspace", NB_DIR.lstrip("/"), ".assistant", "skills", "oss-models")
TEST_FILE = os.path.join(SKILL_DIR, "tests", "test_examples.py")

assert os.path.exists(TEST_FILE), f"Test file not found: {TEST_FILE}"
print(f"Skill dir: {SKILL_DIR}")
print(f"Test file: {TEST_FILE}")

os.chdir(SKILL_DIR)
result = subprocess.run(
    [sys.executable, TEST_FILE],
    capture_output=True, text=True, timeout=60
)

print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:1000])

print(f"\nExit code: {result.returncode}")
assert result.returncode == 0, f"{result.stdout.count('FAIL')} test(s) FAILED"

# COMMAND ----------

# DBTITLE 1,Run via pytest (optional)
import os, subprocess, sys

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# Run via subprocess (like cell 3) with --assert=plain to avoid
# assertion-rewrite __pycache__ on the FUSE mount.  Working dir is
# already the skill dir from cell 3's os.chdir().
try:
    import pytest  # noqa: just checks availability
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", TEST_FILE, "-q",
         "-p", "no:cacheprovider", "--assert=plain"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:500])
    print(f"pytest exit code: {result.returncode}")
except ImportError:
    print("pytest not installed — standalone runner above is sufficient.")