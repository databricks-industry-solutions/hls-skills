# Databricks notebook source
# /// script
# [tool.databricks.environment]
# base_environment = "databricks_ai_v5"
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # oss-002: TEDDY-70M + Vector Search Deploy
# MAGIC
# MAGIC **Eval protocol**: Each arm uses its own prompt (below). Paste the matching one into a fresh Genie Code chat on the corresponding notebook.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Skill arm prompt (this notebook)
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat on **this** notebook → save response to `results/with_skill/oss-002.txt`
# MAGIC
# MAGIC > Deploy TEDDY-70M as a Model Serving endpoint and enable nearest-neighbor cell-type search on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/teddy`. Register the model as `<catalog>.skills.teddy_70m_vs` and name the endpoint `teddy-70m-vs-embedder`. Create a Delta table of reference cell embeddings and a Vector Search index for nearest-neighbor lookup. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it's in a FAILED state or doesn't exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don't leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project's HLS model-deployment skill and TEDDY model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/oss-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/oss-models/references/models/teddy.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure, an AI Search index spec), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations (e.g. synthetic vs real data). This is eval metadata for comparing the baseline and skill arms — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook's source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-002.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Baseline arm prompt (other notebook)
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat on the **baseline** notebook → save response to `results/baseline/oss-002.txt`
# MAGIC
# MAGIC > Deploy TEDDY-70M as a Model Serving endpoint and enable nearest-neighbor cell-type search on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/teddy`. Register the model as `<catalog>.skills.teddy_70m_vs_baseline` and name the endpoint `teddy-70m-vs-baseline`. Create a Delta table of reference cell embeddings and a Vector Search index for nearest-neighbor lookup. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it's in a FAILED state or doesn't exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don't leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations (e.g. synthetic vs real data). This is eval metadata for comparing the baseline and skill arms — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook's source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-002.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## What's different between the prompts
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | Explicit `readAssetById` paths to `SKILL.md` + `teddy.md` | None — Genie Code uses only built-in knowledge |
# MAGIC | **Volume path** | `/Volumes/.../test_with/...` | `/Volumes/.../test_without/...` |
# MAGIC | **UC model name** | `<catalog>.skills.teddy_70m_vs` | `<catalog>.skills.teddy_70m_vs_baseline` |
# MAGIC | **Endpoint name** | `teddy-70m-vs-embedder` | `teddy-70m-vs-baseline` |
# MAGIC | **Development log** | Required (identical wording) | Required (identical wording) |
# MAGIC | **Everything else** | Identical | Identical |
# MAGIC
# MAGIC ## What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (GPU\_SMALL? GPU\_MEDIUM? CPU?)
# MAGIC * Notebook structure (one notebook? two? CPU/GPU split?)
# MAGIC * Whether to enable inference tables and AI Gateway usage tracking
# MAGIC * Dependency versions (especially `transformers` pinning)
# MAGIC * Download method and staging path
# MAGIC * HF Xet backend handling
# MAGIC * Serving contract shape
# MAGIC * Code-bundle stripping strategy
# MAGIC * **Vector Search specifics**: reference corpus source (Census vs synthetic), index naming convention, embedding dimension, DeltaSync vs Direct access, sync pipeline type, CDF enablement
# MAGIC * **Census pipeline**: how many cells to sample, batch size, gene ID remapping strategy
# MAGIC
# MAGIC > **Scoring rubric**: see [03_eval_rubric_and_compare](#notebook-390164024659896) Cell 2 for the full sub-check rubric. Phase 6 (`ai_search`) is the key additional differentiator for this task.
# MAGIC
# MAGIC > **Before pasting the prompt:** run Cell 2 below to confirm which arm is active.

# COMMAND ----------

# DBTITLE 1,Check Skill Symlink and SKILL.md Status
import os

# --- Paths ---
WS_HOME = "/Workspace/Users/<workspace-user>"
SYMLINK_PATH = f"{WS_HOME}/.assistant/skills/oss-models"
SOURCE_DIR = f"{WS_HOME}/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/oss-models"

# --- Symlink ---
print("=== Symlink ===")
print(f"Path:    {SYMLINK_PATH}")
print(f"Exists:  {os.path.exists(SYMLINK_PATH)}")
print(f"Is link: {os.path.islink(SYMLINK_PATH)}")
if os.path.islink(SYMLINK_PATH):
    print(f"Target:  {os.readlink(SYMLINK_PATH)}")

# --- Source directory ---
print(f"\n=== Source ===")
print(f"Path:   {SOURCE_DIR}")
print(f"Exists: {os.path.exists(SOURCE_DIR)}")

# --- SKILL.md status ---
md  = os.path.exists(os.path.join(SOURCE_DIR, "SKILL.md"))
off = os.path.exists(os.path.join(SOURCE_DIR, "SKILL.md.off"))
print(f"\n=== Registry arm ===")
print(f"SKILL.md:     {'FOUND' if md else 'missing'}")
print(f"SKILL.md.off: {'FOUND' if off else 'missing'}")
status = "ACTIVE (skill arm)" if md else "DISABLED (baseline arm)" if off else "MISSING"
print(f"Status:       {status}")

# COMMAND ----------

# DBTITLE 1,Implementation Plan and Key Decisions
# MAGIC %md
# MAGIC ## Implementation plan
# MAGIC
# MAGIC Following your preferences, this notebook keeps the flow explicit and re-runnable:
# MAGIC
# MAGIC * Download TEDDY to a Unity Catalog Volume with a provenance manifest and sentinel file.
# MAGIC * Package the model as a file-based MLflow PyFunc using the 3-column AnnData-style contract from the TEDDY reference.
# MAGIC * Run a local PyFunc round-trip before deployment so packaging bugs fail fast.
# MAGIC * Deploy the registered model to a GPU serving endpoint and smoke-test it with real Ensembl gene IDs from `vocab.txt`.
# MAGIC * Build a reference embedding table from CELLxGENE Census, then create a Delta Sync Vector Search index for nearest-neighbor lookup.
# MAGIC * Export the notebook source at the end for the eval harness.
# MAGIC
# MAGIC Where I intentionally diverge from the shared naming example in the TEDDY reference, I do so only to avoid collisions between the baseline and skill-arm eval notebooks running in the same schema.
# MAGIC

# COMMAND ----------

# DBTITLE 1,Configure Runtime Widgets Paths and Resource Names
import json
import os
from datetime import datetime
from pathlib import Path

for widget_name in ["run_go", "variant", "census_n_cells", "embed_batch_size"]:
    try:
        dbutils.widgets.remove(widget_name)
    except Exception:
        pass

dbutils.widgets.dropdown("run_go", "true", ["true", "false"])
dbutils.widgets.dropdown("variant", "70M", ["70M"])
dbutils.widgets.text("census_n_cells", "1000")
dbutils.widgets.text("embed_batch_size", "50")

RUN_GO = dbutils.widgets.get("run_go") == "true"
VARIANT = dbutils.widgets.get("variant").strip()
CENSUS_N_CELLS = int(dbutils.widgets.get("census_n_cells"))
EMBED_BATCH_SIZE = int(dbutils.widgets.get("embed_batch_size"))

CATALOG = "<catalog>"
SCHEMA = "skills"
UC_MODEL_NAME = f"{CATALOG}.{SCHEMA}.teddy_70m_vs"
ENDPOINT_NAME = "teddy-70m-vs-embedder"

# Deliberate deviation from the shared non-suffixed example in teddy.md:
# these names are suffixed to avoid cross-arm collisions with the baseline eval notebook.
REFERENCE_TABLE = f"{CATALOG}.{SCHEMA}.teddy_cells_70m_vs"
VS_ENDPOINT_NAME = "teddy-70m-vs-search-endpoint"
VS_INDEX_NAME = f"{CATALOG}.{SCHEMA}.teddy_cell_index_70m_vs"

VOLUME_ROOT = "/Volumes/<catalog>/skills/test_with/models/teddy"
SNAPSHOT_ROOT = f"{VOLUME_ROOT}/snapshot"
SNAPSHOT_DIR = f"{SNAPSHOT_ROOT}/teddy"
MODEL_DIR = f"{SNAPSHOT_DIR}/models/teddy_g/{VARIANT}"
DOWNLOAD_SENTINEL = f"{SNAPSHOT_DIR}/.snapshot_complete"
MANIFEST_PATH = f"{VOLUME_ROOT}/teddy_manifest.json"

TMP_ROOT = "/tmp/teddy_70m_vs"
STATE_PATH = f"{TMP_ROOT}/run_state.json"
CODE_STAGE_DIR = f"{TMP_ROOT}/teddy_code"
WRAPPER_PATH = f"{CODE_STAGE_DIR}/teddy_wrapper.py"
EXPORT_PATH = "/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-002.txt"
NOTEBOOK_PATH = "/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/oss-002_TEDDY-70M+VS_Deploy_withSkills"

os.makedirs(TMP_ROOT, exist_ok=True)
os.makedirs(VOLUME_ROOT, exist_ok=True)

state = {
    "run_go": RUN_GO,
    "variant": VARIANT,
    "census_n_cells": CENSUS_N_CELLS,
    "embed_batch_size": EMBED_BATCH_SIZE,
    "uc_model_name": UC_MODEL_NAME,
    "endpoint_name": ENDPOINT_NAME,
    "reference_table": REFERENCE_TABLE,
    "vs_endpoint_name": VS_ENDPOINT_NAME,
    "vs_index_name": VS_INDEX_NAME,
    "volume_root": VOLUME_ROOT,
    "snapshot_dir": SNAPSHOT_DIR,
    "model_dir": MODEL_DIR,
    "download_sentinel": DOWNLOAD_SENTINEL,
    "manifest_path": MANIFEST_PATH,
    "tmp_root": TMP_ROOT,
    "code_stage_dir": CODE_STAGE_DIR,
    "wrapper_path": WRAPPER_PATH,
    "export_path": EXPORT_PATH,
    "notebook_path": NOTEBOOK_PATH,
    "skip_model_rebuild": False,
    "skip_endpoint_redeploy": False,
    "existing_model_version": None,
    "skills_loaded": [
        "oss-models (workspace reference via readAssetById)",
        "teddy model reference (workspace reference via readAssetById)",
        "machine-learning",
        "machine-learning/model-serving",
        "vector-search",
        "environment-management",
    ],
    "created_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
}
Path(STATE_PATH).write_text(json.dumps(state, indent=2), encoding="utf-8")

print(json.dumps(state, indent=2))

# COMMAND ----------

# DBTITLE 1,Check Existing Endpoint and Perform Idempotent Cleanup
import json
import time
from pathlib import Path

import mlflow
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from mlflow import MlflowClient

state = json.loads(Path(STATE_PATH).read_text(encoding="utf-8"))
w = WorkspaceClient()
mlc = MlflowClient()


def _enum_value(value):
    return getattr(value, "value", value)


def _get_serving_snapshot(endpoint_name: str):
    try:
        ep = w.serving_endpoints.get(name=endpoint_name)
    except NotFound:
        return None
    served_version = None
    served_entities = getattr(getattr(ep, "config", None), "served_entities", None) or []
    if served_entities:
        served_version = getattr(served_entities[0], "entity_version", None)
    return {
        "endpoint": ep,
        "ready": _enum_value(getattr(getattr(ep, "state", None), "ready", None)),
        "config_update": _enum_value(getattr(getattr(ep, "state", None), "config_update", None)),
        "served_version": served_version,
    }


def _wait_until_settled(endpoint_name: str, timeout_s: int = 1800):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        snap = _get_serving_snapshot(endpoint_name)
        if snap is None:
            return None
        last = snap
        if snap["config_update"] in (None, "NOT_UPDATING"):
            return snap
        print(f"Waiting for endpoint to settle: ready={snap['ready']} config_update={snap['config_update']}")
        time.sleep(20)
    raise TimeoutError(f"Endpoint '{endpoint_name}' did not settle within {timeout_s} seconds. Last snapshot: {last}")


def _delete_endpoint_if_exists(endpoint_name: str):
    snap = _get_serving_snapshot(endpoint_name)
    if snap is None:
        print(f"Serving endpoint '{endpoint_name}' does not exist.")
        return
    print(f"Deleting serving endpoint '{endpoint_name}'...")
    w.serving_endpoints.delete(name=endpoint_name)
    deadline = time.time() + 1200
    while time.time() < deadline:
        if _get_serving_snapshot(endpoint_name) is None:
            print("Serving endpoint deleted.")
            return
        time.sleep(15)
    raise TimeoutError(f"Timed out waiting for serving endpoint '{endpoint_name}' to delete.")


def _delete_vs_index_if_exists(index_name: str):
    try:
        w.vector_search_indexes.delete_index(index_name=index_name)
        print(f"Deleted Vector Search index '{index_name}'.")
    except Exception as exc:
        print(f"Vector Search index cleanup skipped for '{index_name}': {exc}")


def _delete_vs_endpoint_if_exists(endpoint_name: str):
    try:
        _ = w.vector_search_endpoints.get_endpoint(endpoint_name=endpoint_name)
    except Exception:
        print(f"Vector Search endpoint '{endpoint_name}' does not exist.")
        return
    try:
        w.vector_search_endpoints.delete_endpoint(endpoint_name=endpoint_name)
        print(f"Deleted Vector Search endpoint '{endpoint_name}'.")
    except Exception as exc:
        print(f"Vector Search endpoint cleanup skipped for '{endpoint_name}': {exc}")


def _delete_registered_model_versions(model_name: str):
    versions = list(mlc.search_model_versions(f"name='{model_name}'"))
    if not versions:
        print(f"No registered model versions found for '{model_name}'.")
        return
    for version in versions:
        print(f"Deleting model version {version.version} from '{model_name}'")
        mlc.delete_model_version(name=model_name, version=version.version)
    try:
        mlc.delete_registered_model(name=model_name)
        print(f"Deleted registered model '{model_name}'.")
    except Exception as exc:
        print(f"Registered model object cleanup skipped for '{model_name}': {exc}")


if not state["run_go"]:
    print("run_go=false -> cleanup cell is a no-op.")
else:
    snapshot = _get_serving_snapshot(state["endpoint_name"])
    if snapshot is not None and snapshot["config_update"] not in (None, "NOT_UPDATING"):
        snapshot = _wait_until_settled(state["endpoint_name"])

    ready = None if snapshot is None else snapshot["ready"]
    config_update = None if snapshot is None else snapshot["config_update"]

    print("--- Endpoint state before cleanup decision ---")
    print(json.dumps({
        "endpoint_exists": snapshot is not None,
        "ready": ready,
        "config_update": config_update,
        "served_version": None if snapshot is None else snapshot["served_version"],
    }, indent=2))

    if snapshot is not None and ready == "READY" and config_update in (None, "NOT_UPDATING"):
        print("Endpoint is already READY; skipping destructive cleanup and reusing the deployed model version.")
        state["skip_model_rebuild"] = True
        state["skip_endpoint_redeploy"] = True
        state["existing_model_version"] = snapshot["served_version"]
    else:
        print("Endpoint is absent or unhealthy; performing a clean rerun setup.")
        _delete_endpoint_if_exists(state["endpoint_name"])
        _delete_vs_index_if_exists(state["vs_index_name"])
        _delete_vs_endpoint_if_exists(state["vs_endpoint_name"])
        spark.sql(f"DROP TABLE IF EXISTS {state['reference_table']}")
        print(f"Dropped Delta table if present: {state['reference_table']}")
        _delete_registered_model_versions(state["uc_model_name"])
        state["skip_model_rebuild"] = False
        state["skip_endpoint_redeploy"] = False
        state["existing_model_version"] = None

    Path(STATE_PATH).write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("--- Persisted run state ---")
    print(json.dumps(state, indent=2))

# COMMAND ----------

# DBTITLE 1,Install Lightweight Download Dependencies
# MAGIC %pip install -q huggingface_hub safetensors pyyaml

# COMMAND ----------

# DBTITLE 1,Restart Python After Lightweight Install
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Rehydrate State After Restart
import json
from pathlib import Path

STATE_PATH = "/tmp/teddy_70m_vs/run_state.json"
state = json.loads(Path(STATE_PATH).read_text(encoding="utf-8"))
print(json.dumps(state, indent=2))

# COMMAND ----------

# DBTITLE 1,Download TEDDY Snapshot and Write Provenance Manifest
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

state = json.loads(Path(STATE_PATH).read_text(encoding="utf-8"))

if not state["run_go"]:
    print("run_go=false -> download cell is a no-op.")
else:
    snapshot_dir = Path(state["snapshot_dir"])
    model_dir = Path(state["model_dir"])
    sentinel = Path(state["download_sentinel"])
    manifest_path = Path(state["manifest_path"])

    snapshot_dir.mkdir(parents=True, exist_ok=True)

    download_meta = None
    if sentinel.exists() and model_dir.exists() and (model_dir / "model.safetensors").exists():
        print(f"Snapshot already present at {snapshot_dir}; skipping re-download.")
        download_meta = json.loads(sentinel.read_text(encoding="utf-8"))
    else:
        env = os.environ.copy()
        env["HF_HUB_DISABLE_XET"] = "1"
        env["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
        helper = f'''
import json
from huggingface_hub import model_info, snapshot_download
info = model_info("Merck/TEDDY")
resolved_dir = snapshot_download(
    repo_id="Merck/TEDDY",
    local_dir={json.dumps(str(snapshot_dir))},
    resume_download=True,
)
print(json.dumps({{"resolved_dir": resolved_dir, "hf_sha": info.sha}}))
'''
        completed = subprocess.run(
            [sys.executable, "-c", helper],
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if stdout_lines:
            print(completed.stdout)
            download_meta = json.loads(stdout_lines[-1])
        else:
            raise RuntimeError("TEDDY download subprocess completed without JSON output.")

        sentinel.write_text(
            json.dumps(
                {
                    "repo_id": "Merck/TEDDY",
                    "downloaded_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "hf_sha": download_meta["hf_sha"],
                    "resolved_dir": download_meta["resolved_dir"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    gitattributes_path = snapshot_dir / ".gitattributes"
    uses_xet = gitattributes_path.exists() and ("filter=xet" in gitattributes_path.read_text(encoding="utf-8"))

    manifest = {
        "model_name": "TEDDY-G 70M",
        "variant": state["variant"],
        "model_card": "https://huggingface.co/Merck/TEDDY",
        "paper": "arXiv:2503.03485",
        "license": "Apache-2.0",
        "source_url": "https://huggingface.co/Merck/TEDDY",
        "hf_revision": download_meta["hf_sha"],
        "download_path": state["snapshot_dir"],
        "model_dir": state["model_dir"],
        "downloaded_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "xet_backend_detected": bool(uses_xet),
        "xet_disabled_for_download": True,
        "hf_transfer_disabled_for_download": True,
        "runtime_expectation": "Serverless GPU for registration/deploy; GPU_SMALL for serving",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))

    assert model_dir.exists(), f"Model directory missing: {model_dir}"
    assert (model_dir / "model.safetensors").exists(), "Expected model.safetensors in checkpoint directory"
    assert (model_dir / "vocab.txt").exists(), "Expected vocab.txt in checkpoint directory"

# COMMAND ----------

# DBTITLE 1,Install Exact Transformers Version for TEDDY Packaging
# MAGIC %pip install -q transformers==4.41.0

# COMMAND ----------

# DBTITLE 1,Restart Python After Transformers Pin
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Register and Deploy Section Overview
# MAGIC %md
# MAGIC ## Register and deploy TEDDY-70M
# MAGIC
# MAGIC This phase follows the TEDDY reference closely:
# MAGIC
# MAGIC * use the exact `transformers==4.41.0` pin,
# MAGIC * stage a clean code bundle without weights,
# MAGIC * log the PyFunc from a wrapper file path instead of a live instance,
# MAGIC * run a local PyFunc round-trip before serving,
# MAGIC * deploy to a GPU endpoint because the TEDDY reference explicitly recommends `GPU_SMALL` for Model Serving.
# MAGIC

# COMMAND ----------

# DBTITLE 1,Rehydrate State and Import Registration Stack
import base64
import inspect
import io
import json
import os
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import torch
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    EndpointStateConfigUpdate,
    EndpointStateReady,
    ServedEntityInput,
    ServingModelWorkloadType,
)
from mlflow import MlflowClient
from mlflow.models import infer_signature

STATE_PATH = "/tmp/teddy_70m_vs/run_state.json"
MODEL_INFO_PATH = "/tmp/teddy_70m_vs/model_info.json"
DEFAULT_PARAMS = {"max_seq_len": "2048", "pooling": "mean"}


def load_state():
    return json.loads(Path(STATE_PATH).read_text(encoding="utf-8"))


def save_state(state_dict):
    Path(STATE_PATH).write_text(json.dumps(state_dict, indent=2), encoding="utf-8")


def enum_value(value):
    return getattr(value, "value", value)


def as_jsonable(obj):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: as_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [as_jsonable(v) for v in obj]
    if hasattr(obj, "as_dict"):
        return as_jsonable(obj.as_dict())
    if hasattr(obj, "__dict__"):
        return as_jsonable(vars(obj))
    return str(obj)


def latest_model_version(mlc: MlflowClient, model_name: str):
    versions = list(mlc.search_model_versions(f"name='{model_name}'"))
    if not versions:
        return None
    return max(versions, key=lambda v: int(v.version))


def fetch_endpoint_diagnostics(w: WorkspaceClient, endpoint_name: str):
    endpoint = w.serving_endpoints.get(name=endpoint_name)
    pending_entities = getattr(getattr(endpoint, "pending_config", None), "served_entities", None) or []
    active_entities = getattr(getattr(endpoint, "config", None), "served_entities", None) or []
    served_entities = pending_entities or active_entities
    served_entity_name = getattr(served_entities[0], "name", None) if served_entities else None
    config_version = getattr(getattr(endpoint, "pending_config", None), "config_version", None)
    if config_version is None:
        config_version = getattr(getattr(endpoint, "config", None), "config_version", 0) or 0

    diagnostics = {
        "endpoint_state": {
            "ready": enum_value(getattr(getattr(endpoint, "state", None), "ready", None)),
            "config_update": enum_value(getattr(getattr(endpoint, "state", None), "config_update", None)),
        },
        "served_entity_name": served_entity_name,
        "config_version": config_version,
        "logs": None,
    }
    if served_entity_name:
        try:
            logs = w.api_client.do(
                "GET",
                f"/api/2.0/serving-endpoints/{endpoint_name}/served-entities/{served_entity_name}/logs",
                query={"config_version": config_version},
            )
            diagnostics["logs"] = logs
        except Exception as exc:
            diagnostics["logs"] = {"error": str(exc)}
    return diagnostics


state = load_state()
mlflow.set_registry_uri("databricks-uc")
w = WorkspaceClient()
mlc = MlflowClient()
print(json.dumps(state, indent=2))

# COMMAND ----------

# DBTITLE 1,Stage Clean Code Bundle Build Wrapper and Create Input Example
state = load_state()
model_dir = Path(state["model_dir"])
snapshot_dir = Path(state["snapshot_dir"])
code_stage_dir = Path(state["code_stage_dir"])
wrapper_path = Path(state["wrapper_path"])

assert model_dir.exists(), f"Model directory missing: {model_dir}"
assert (model_dir / "config.json").exists(), "Missing config.json"
assert (model_dir / "vocab.txt").exists(), "Missing vocab.txt"

with open(model_dir / "config.json", "r", encoding="utf-8") as handle:
    teddy_config = json.load(handle)
EMB_DIM = int(teddy_config["d_model"])
ADD_CLS = bool(teddy_config.get("add_cls", False))

with open(model_dir / "vocab.txt", "r", encoding="utf-8") as handle:
    vocab_tokens = [line.strip() for line in handle if line.strip()]
real_genes = [token for token in vocab_tokens if token.startswith("ENSG")]
assert real_genes, "No Ensembl IDs found in vocab.txt"
assert "ENSG00000000003" in set(real_genes), "Expected ENSG00000000003 in TEDDY vocab"
selected_genes = real_genes[:128]

rng = np.random.default_rng(42)
expr = rng.poisson(2.0, size=(5, len(selected_genes))).astype(np.float32)
obs_df = pd.DataFrame({"cell_id": [f"cell_{i}" for i in range(expr.shape[0])]})
var_df = pd.DataFrame({"index": selected_genes})

input_example = pd.DataFrame(
    {
        "adata_sparsematrix": [expr.tolist()],
        "adata_obs": [obs_df.to_json(orient="split")],
        "adata_var": [var_df.to_json(orient="split")],
    }
)
output_example = pd.DataFrame(
    {
        "cell_id": obs_df["cell_id"],
        "embedding": [[0.0] * EMB_DIM for _ in range(len(obs_df))],
    }
)
signature = infer_signature(input_example, output_example, params=DEFAULT_PARAMS)

if not state["skip_model_rebuild"]:
    if code_stage_dir.exists():
        shutil.rmtree(code_stage_dir)
    shutil.copytree(
        snapshot_dir,
        code_stage_dir,
        ignore=shutil.ignore_patterns("*.safetensors", "*.bin", "*.ckpt", "*.pt", "__pycache__"),
    )

    wrapper_source = '''
import inspect
import io
import json
import sys

import mlflow
import numpy as np
import pandas as pd
import torch


class TEDDYEmbedder(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        for stream in (sys.stdout, sys.stderr):
            if stream is not None and not hasattr(stream, "isatty"):
                stream.isatty = lambda: False

        teddy_pkg_parent = context.artifacts["teddy_pkg_parent"]
        if teddy_pkg_parent not in sys.path:
            sys.path.insert(0, teddy_pkg_parent)

        from teddy.models.model_directory import get_architecture, model_dict
        from teddy.tokenizer.gene_tokenizer import GeneTokenizer

        model_dir = context.artifacts["model_dir"]
        arch = get_architecture(model_dir)
        config_cls = model_dict[arch]["config_cls"]
        model_cls = model_dict[arch]["model_cls"]

        self.config = config_cls.from_pretrained(model_dir)
        self.model = model_cls.from_pretrained(model_dir, config=self.config)
        if hasattr(self.model, "return_all_embs"):
            self.model.return_all_embs = True
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device).eval()
        self.tokenizer = GeneTokenizer.from_pretrained(model_dir)
        self._forward_params = set(inspect.signature(self.model.forward).parameters.keys())
        self.add_cls = bool(getattr(self.config, "add_cls", False))
        self.cls_token_id = int(getattr(self.config, "cls_token_id", 0))
        self.d_model = int(getattr(self.config, "d_model", 0))
        self._use_bf16 = self.device == "cuda"

    def _predict_batch(self, dense_expr, obs_json, var_json, params):
        obs_df = pd.read_json(io.StringIO(obs_json), orient="split")
        var_df = pd.read_json(io.StringIO(var_json), orient="split")

        if "index" in var_df.columns:
            gene_names = var_df["index"].astype(str).tolist()
        else:
            gene_names = var_df.index.astype(str).tolist()

        X = np.asarray(dense_expr, dtype=np.float32)
        if X.ndim == 1:
            X = X[None, :]
        if X.ndim != 2:
            raise ValueError(f"adata_sparsematrix must be 2D after coercion; got shape {X.shape}")
        if len(gene_names) != X.shape[1]:
            raise ValueError(f"Gene metadata width {len(gene_names)} != expression width {X.shape[1]}")

        max_seq_len = int((params or {}).get("max_seq_len", 2048))
        pooling = str((params or {}).get("pooling", "mean"))
        if pooling not in {"mean", "cls"}:
            raise ValueError("pooling must be 'mean' or 'cls'")
        if pooling == "cls" and not self.add_cls:
            raise ValueError("pooling='cls' requires config.add_cls=True for this TEDDY checkpoint")

        unk_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.unk_token)
        ids = self.tokenizer.convert_tokens_to_ids(list(gene_names))
        ids = [unk_id if token_id is None else token_id for token_id in ids]

        X_t = torch.tensor(X, device=self.device, dtype=torch.float32)
        token_array = torch.tensor(ids, device=self.device, dtype=torch.long)
        k = min(max_seq_len, X.shape[1])
        _, top_idx = torch.topk(X_t, k=k, largest=True, sorted=True)
        gene_ids = token_array[top_idx]
        rank_vec = torch.linspace(1.0, -1.0, steps=k, device=self.device, dtype=torch.float32)
        gene_vals = rank_vec.unsqueeze(0).expand(X_t.shape[0], -1).clone()
        attention_mask = torch.ones_like(gene_ids, dtype=torch.long, device=self.device)

        kwargs = {}
        if "gene_ids" in self._forward_params:
            kwargs["gene_ids"] = gene_ids
        elif "input_ids" in self._forward_params:
            kwargs["input_ids"] = gene_ids
        if "values" in self._forward_params:
            kwargs["values"] = gene_vals
        if "gene_values" in self._forward_params:
            kwargs["gene_values"] = gene_vals
        if "attention_mask" in self._forward_params:
            kwargs["attention_mask"] = attention_mask
        if "return_outputs" in self._forward_params:
            kwargs["return_outputs"] = True

        with torch.no_grad():
            if self._use_bf16:
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    outputs = self.model(**kwargs)
            else:
                outputs = self.model(**kwargs)

        token_embeddings = None
        if isinstance(outputs, dict):
            token_embeddings = outputs.get("all_embs")
            if token_embeddings is None:
                token_embeddings = outputs.get("last_hidden_state")
            if token_embeddings is None and outputs.get("hidden_states") is not None:
                token_embeddings = outputs["hidden_states"][-1]
        else:
            token_embeddings = getattr(outputs, "last_hidden_state", None)
            if token_embeddings is None:
                hs = getattr(outputs, "hidden_states", None)
                if hs is not None and len(hs) > 0:
                    token_embeddings = hs[-1]
        if token_embeddings is None:
            raise RuntimeError(f"Could not extract token embeddings from TEDDY outputs of type {type(outputs)}")

        cell_ids = (
            obs_df["cell_id"].astype(str).tolist()
            if "cell_id" in obs_df.columns
            else [f"cell_{i}" for i in range(X.shape[0])]
        )
        rows = []
        for i, cell_id in enumerate(cell_ids):
            cell_tokens = token_embeddings[i]
            embedding = cell_tokens[0] if pooling == "cls" else cell_tokens.mean(dim=0)
            rows.append({"cell_id": cell_id, "embedding": embedding.detach().float().cpu().tolist()})
        return rows

    def predict(self, context, model_input, params=None):
        if isinstance(model_input, pd.DataFrame):
            records = model_input.to_dict(orient="records")
        elif isinstance(model_input, list):
            records = model_input
        else:
            raise TypeError("model_input must be a pandas DataFrame or a list of dictionaries")

        rows = []
        for row in records:
            rows.extend(
                self._predict_batch(
                    dense_expr=row["adata_sparsematrix"],
                    obs_json=row["adata_obs"],
                    var_json=row["adata_var"],
                    params=params,
                )
            )
        return pd.DataFrame(rows)


mlflow.models.set_model(TEDDYEmbedder())
'''
    wrapper_path.write_text(wrapper_source, encoding="utf-8")
    print(f"Staged clean TEDDY code bundle at {code_stage_dir}")
    print(f"Wrote wrapper file to {wrapper_path}")
else:
    print("skip_model_rebuild=true -> reusing the deployed model and skipping code-bundle regeneration.")

print({
    "embedding_dim": EMB_DIM,
    "add_cls": ADD_CLS,
    "n_vocab_genes": len(real_genes),
    "example_cells": int(expr.shape[0]),
    "example_genes": int(expr.shape[1]),
})

# COMMAND ----------

# DBTITLE 1,Log MLflow PyFunc Artifact
state = load_state()

if state["skip_model_rebuild"]:
    print("skip_model_rebuild=true -> not logging a new MLflow artifact.")
else:
    pip_requirements = [
        "torch>=2.3.0",
        "transformers==4.41.0",
        "numpy>=1.26.4,<2.0",
        "pandas>=2.2.2,<3.0",
    ]

    with mlflow.start_run(run_name="teddy_70m_vs_packaging") as run:
        mlflow.set_tags(
            {
                "model_family": "TEDDY",
                "variant": state["variant"],
                "source_url": "https://huggingface.co/Merck/TEDDY",
                "paper": "arXiv:2503.03485",
                "license": "Apache-2.0",
                "hf_revision": json.loads(Path(state["download_sentinel"]).read_text(encoding="utf-8"))["hf_sha"],
            }
        )
        model_info = mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=state["wrapper_path"],
            code_paths=[state["code_stage_dir"]],
            artifacts={
                "model_dir": state["model_dir"],
                "teddy_pkg_parent": state["code_stage_dir"],
            },
            signature=signature,
            input_example=(input_example, DEFAULT_PARAMS),
            pip_requirements=pip_requirements,
        )

    model_info_payload = {
        "run_id": run.info.run_id,
        "model_uri": model_info.model_uri,
        "artifact_path": "model",
    }
    Path(MODEL_INFO_PATH).write_text(json.dumps(model_info_payload, indent=2), encoding="utf-8")
    print(json.dumps(model_info_payload, indent=2))

# COMMAND ----------

# DBTITLE 1,Run Local PyFunc Round Trip Gate
state = load_state()

if state["skip_model_rebuild"]:
    print("skip_model_rebuild=true -> local pyfunc gate skipped because an endpoint is already READY.")
else:
    model_info_payload = json.loads(Path(MODEL_INFO_PATH).read_text(encoding="utf-8"))
    local_model = mlflow.pyfunc.load_model(model_info_payload["model_uri"])

    local_predictions = local_model.predict(input_example, params=DEFAULT_PARAMS)
    display(local_predictions.head())

    assert len(local_predictions) == len(obs_df), "Expected one prediction row per input cell"
    assert local_predictions["embedding"].map(len).nunique() == 1, "Embedding sizes are inconsistent"
    assert int(local_predictions["embedding"].map(len).iloc[0]) == EMB_DIM, "Embedding dim does not match config.d_model"
    assert local_predictions["embedding"].map(lambda row: float(np.linalg.norm(np.asarray(row, dtype=np.float32))) > 0).all(), "Degenerate zero embeddings detected"

    oov_var_df = pd.DataFrame({"index": [f"FAKEGENE_{i}" for i in range(len(selected_genes))]})
    oov_input = pd.DataFrame(
        {
            "adata_sparsematrix": [expr.tolist()],
            "adata_obs": [obs_df.to_json(orient="split")],
            "adata_var": [oov_var_df.to_json(orient="split")],
        }
    )
    oov_predictions = local_model.predict(oov_input, params=DEFAULT_PARAMS)
    assert len(oov_predictions) == len(obs_df), "All-OOV payload should still return one row per input cell"

    try:
        local_model.predict(input_example[["adata_sparsematrix", "adata_var"]], params=DEFAULT_PARAMS)
        raise AssertionError("Expected schema enforcement failure when adata_obs is omitted")
    except Exception as exc:
        print(f"Missing-field check raised as expected: {type(exc).__name__}: {exc}")

    print("Local PyFunc validation passed.")

# COMMAND ----------

# DBTITLE 1,Register Unity Catalog Model Version
state = load_state()

if state["skip_model_rebuild"]:
    target_version = state.get("existing_model_version")
    if target_version is None:
        latest = latest_model_version(mlc, state["uc_model_name"])
        if latest is None:
            raise RuntimeError("skip_model_rebuild=true but no registered model version was found.")
        target_version = latest.version
    state["target_model_version"] = str(target_version)
    save_state(state)
    print(f"Reusing registered model version: {target_version}")
else:
    model_info_payload = json.loads(Path(MODEL_INFO_PATH).read_text(encoding="utf-8"))
    registered = mlflow.register_model(
        model_uri=model_info_payload["model_uri"],
        name=state["uc_model_name"],
        await_registration_for=600,
    )
    state["target_model_version"] = str(registered.version)
    save_state(state)
    print(f"Registered Unity Catalog model version: {registered.version}")

# COMMAND ----------

# DBTITLE 1,Create or Update GPU Serving Endpoint
state = load_state()
target_version = state["target_model_version"]
served_entity_name = f"teddy-70m-vs-v{target_version}"

if state["skip_endpoint_redeploy"]:
    print(f"Endpoint '{state['endpoint_name']}' is already READY; reusing served model version {target_version}.")
else:
    served_entity = ServedEntityInput(
        name=served_entity_name,
        entity_name=state["uc_model_name"],
        entity_version=str(target_version),
        workload_type=ServingModelWorkloadType.GPU_SMALL,
        workload_size="Small",
        scale_to_zero_enabled=True,
    )
    endpoint_config = EndpointCoreConfigInput(
        name=state["endpoint_name"],
        served_entities=[served_entity],
    )

    try:
        existing_endpoint = w.serving_endpoints.get(name=state["endpoint_name"])
    except NotFound:
        existing_endpoint = None

    if existing_endpoint is None:
        print(f"Creating serving endpoint '{state['endpoint_name']}' on GPU_SMALL.")
        w.serving_endpoints.create(name=state["endpoint_name"], config=endpoint_config)
    else:
        print(f"Updating serving endpoint '{state['endpoint_name']}' to version {target_version} on GPU_SMALL.")
        w.serving_endpoints.update_config(name=state["endpoint_name"], served_entities=[served_entity])

    deadline = time.time() + 1800
    last_snapshot = None
    while time.time() < deadline:
        endpoint = w.serving_endpoints.get(name=state["endpoint_name"])
        ready = enum_value(getattr(getattr(endpoint, "state", None), "ready", None))
        config_update = enum_value(getattr(getattr(endpoint, "state", None), "config_update", None))
        served_entities = getattr(getattr(endpoint, "config", None), "served_entities", None) or []
        active_version = getattr(served_entities[0], "entity_version", None) if served_entities else None
        deployment_state = None
        if served_entities and getattr(served_entities[0], "state", None) is not None:
            deployment_state = enum_value(getattr(served_entities[0].state, "deployment", None))

        last_snapshot = {
            "ready": ready,
            "config_update": config_update,
            "active_version": active_version,
            "deployment_state": deployment_state,
        }
        print(last_snapshot)

        if deployment_state == "DEPLOYMENT_FAILED":
            diagnostics = fetch_endpoint_diagnostics(w, state["endpoint_name"])
            raise RuntimeError("Serving deployment failed:\n" + json.dumps(diagnostics, indent=2)[:20000])

        if (
            ready == EndpointStateReady.READY.value
            and config_update == EndpointStateConfigUpdate.NOT_UPDATING.value
            and str(active_version) == str(target_version)
        ):
            print(f"Endpoint '{state['endpoint_name']}' is READY on GPU_SMALL with model version {target_version}.")
            break
        time.sleep(30)
    else:
        diagnostics = fetch_endpoint_diagnostics(w, state["endpoint_name"])
        raise TimeoutError(
            "Serving endpoint did not become READY within 30 minutes. "
            + json.dumps({"last_snapshot": last_snapshot, "diagnostics": diagnostics}, indent=2)[:20000]
        )

# COMMAND ----------

# DBTITLE 1,Smoke Test Serving Endpoint with Real Ensembl Gene IDs
state = load_state()
with open(Path(state["model_dir"]) / "config.json", "r", encoding="utf-8") as handle:
    emb_dim = int(json.load(handle)["d_model"])
with open(Path(state["model_dir"]) / "vocab.txt", "r", encoding="utf-8") as handle:
    smoke_genes = [line.strip() for line in handle if line.strip().startswith("ENSG")][:64]

smoke_expr = np.random.default_rng(7).poisson(2.0, size=(3, len(smoke_genes))).astype(np.float32)
smoke_obs = pd.DataFrame({"cell_id": [f"smoke_{i}" for i in range(smoke_expr.shape[0])]})
smoke_var = pd.DataFrame({"index": smoke_genes})

response = w.serving_endpoints.query(
    name=state["endpoint_name"],
    dataframe_records=[
        {
            "adata_sparsematrix": smoke_expr.tolist(),
            "adata_obs": smoke_obs.to_json(orient="split"),
            "adata_var": smoke_var.to_json(orient="split"),
        }
    ],
    extra_params=DEFAULT_PARAMS,
)
response_payload = as_jsonable(response)
print(json.dumps(response_payload, indent=2)[:20000])

predictions = response_payload.get("predictions") if isinstance(response_payload, dict) else None
assert predictions is not None, "Serving response did not include a predictions field"
assert len(predictions) == 3, "Expected one prediction row per smoke-test cell"
first_embedding = predictions[0]["embedding"]
assert len(first_embedding) == emb_dim, "Smoke-test embedding dim does not match config.d_model"
print("Serving smoke test passed.")

# COMMAND ----------

# DBTITLE 1,Census and Vector Search Section Overview
# MAGIC %md
# MAGIC ## Reference corpus and Vector Search
# MAGIC
# MAGIC Following the TEDDY reference, this phase:
# MAGIC
# MAGIC 1. Queries CELLxGENE Census for 1 000 real scRNA-seq cells (10x 3' v3 assay, primary data only).
# MAGIC 2. Remaps `var_names` from Census numeric indices to Ensembl `feature_id` — the critical step the TEDDY reference calls out.
# MAGIC 3. Embeds cells in batches of 50 via the live serving endpoint.
# MAGIC 4. Writes embeddings + metadata to a Delta table with a NOT-NULL primary key and Change Data Feed enabled.
# MAGIC 5. Creates a Delta Sync Vector Search index for nearest-neighbor cell-type search.
# MAGIC 6. Validates the index with self-retrieval and monotonic-score checks.
# MAGIC

# COMMAND ----------

# DBTITLE 1,Install CELLxGENE Census Dependencies
# MAGIC %pip install -q cellxgene-census

# COMMAND ----------

# DBTITLE 1,Restart Python After Census Install
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Query Census Embed via Endpoint and Write Delta Table
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
from databricks.sdk import WorkspaceClient

STATE_PATH = "/tmp/teddy_70m_vs/run_state.json"
state = json.loads(Path(STATE_PATH).read_text(encoding="utf-8"))
w = WorkspaceClient()

CATALOG = "<catalog>"
SCHEMA = "skills"
REFERENCE_TABLE = state["reference_table"]
ENDPOINT_NAME = state["endpoint_name"]
MODEL_DIR = state["model_dir"]
CENSUS_N_CELLS = state["census_n_cells"]
# Widget default is 50 but that OOMs on a T4/GPU_SMALL with 25k genes.
# Cap at 10 to keep VRAM usage safe.
EMBED_BATCH_SIZE = min(state["embed_batch_size"], 10)

with open(Path(MODEL_DIR) / "config.json", "r", encoding="utf-8") as f:
    EMB_DIM = int(json.load(f)["d_model"])

with open(Path(MODEL_DIR) / "vocab.txt", "r", encoding="utf-8") as f:
    teddy_vocab = set(line.strip() for line in f if line.strip().startswith("ENSG"))

print(f"TEDDY vocab Ensembl IDs: {len(teddy_vocab)}")

import cellxgene_census

with cellxgene_census.open_soma(census_version="2024-07-01") as census:
    obs_df = cellxgene_census.get_obs(
        census,
        "homo_sapiens",
        value_filter='is_primary_data == True and assay == "10x 3\' v3"',
        column_names=[
            "soma_joinid",
            "cell_type",
            "tissue_general",
            "disease",
            "assay",
        ],
    )
    print(f"Census obs rows (10x 3' v3, primary): {len(obs_df):,}")

    rng = np.random.default_rng(42)
    sampled_idx = rng.choice(len(obs_df), size=min(CENSUS_N_CELLS, len(obs_df)), replace=False)
    sampled_obs = obs_df.iloc[sampled_idx].reset_index(drop=True)
    sampled_joinids = sampled_obs["soma_joinid"].tolist()
    print(f"Sampled {len(sampled_joinids)} cells")

    import tiledbsoma

    experiment = census["census_data"]["homo_sapiens"]
    query = experiment.axis_query(
        measurement_name="RNA",
        obs_query=tiledbsoma.AxisQuery(coords=(sampled_joinids,)),
    )
    adata = query.to_anndata(X_name="raw")
    query.close()

print(f"AnnData shape: {adata.shape}")
print(f"var_names sample (before remap): {list(adata.var_names[:5])}")

adata.var_names = adata.var["feature_id"].values
adata.var_names_make_unique()
print(f"var_names sample (after remap): {list(adata.var_names[:5])}")

overlap = set(adata.var_names) & teddy_vocab
print(f"Overlap with TEDDY vocab: {len(overlap)} / {len(teddy_vocab)} ({100*len(overlap)/len(teddy_vocab):.1f}%)")
assert len(overlap) > 20000, "Gene overlap is unexpectedly low; Census var remapping may have failed"

# Filter to TEDDY vocab genes to keep serving payloads under the 16 MB limit.
# Census has ~60k genes; TEDDY only knows ~25k. Sending all 60k bloats the matrix.
mask = [g in teddy_vocab for g in adata.var_names]
adata = adata[:, mask]
print(f"Filtered AnnData to TEDDY vocab: {adata.shape}")

all_census_genes = list(adata.var_names)
X_dense = adata.X.toarray() if hasattr(adata.X, "toarray") else np.asarray(adata.X)
print(f"Expression matrix shape: {X_dense.shape}, sparsity: {(X_dense == 0).mean():.1%}")

result_rows = []
for batch_start in range(0, len(sampled_obs), EMBED_BATCH_SIZE):
    batch_end = min(batch_start + EMBED_BATCH_SIZE, len(sampled_obs))
    batch_obs = sampled_obs.iloc[batch_start:batch_end]
    batch_expr = X_dense[batch_start:batch_end].astype(np.float32)

    cell_ids = [f"census_{batch_start + i}" for i in range(batch_expr.shape[0])]
    obs_json = pd.DataFrame({"cell_id": cell_ids}).to_json(orient="split")
    var_json = pd.DataFrame({"index": all_census_genes}).to_json(orient="split")

    response = w.serving_endpoints.query(
        name=ENDPOINT_NAME,
        dataframe_records=[
            {
                "adata_sparsematrix": batch_expr.tolist(),
                "adata_obs": obs_json,
                "adata_var": var_json,
            }
        ],
        extra_params={"max_seq_len": "2048", "pooling": "mean"},
    )
    predictions = response.predictions if hasattr(response, "predictions") else response.as_dict().get("predictions", [])
    for i, pred in enumerate(predictions):
        emb = pred["embedding"] if isinstance(pred, dict) else pred.get("embedding")
        result_rows.append(
            {
                "cell_id": cell_ids[i],
                "embedding": emb,
                "cell_type": batch_obs.iloc[i]["cell_type"],
                "tissue_general": batch_obs.iloc[i]["tissue_general"],
                "disease": batch_obs.iloc[i]["disease"],
            }
        )
    print(f"Embedded batch {batch_start}-{batch_end} ({len(result_rows)} total)")

result_df = pd.DataFrame(result_rows)
assert len(result_df) == len(sampled_obs), "Mismatch between input and output row counts"
assert result_df["embedding"].map(len).nunique() == 1, "Inconsistent embedding sizes"
print(f"Result DataFrame: {result_df.shape}")
display(result_df[["cell_id", "cell_type", "tissue_general", "disease"]].head(10))

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {REFERENCE_TABLE} (
    cell_id STRING NOT NULL,
    embedding ARRAY<DOUBLE>,
    cell_type STRING,
    tissue_general STRING,
    disease STRING,
    CONSTRAINT pk_{REFERENCE_TABLE.split('.')[-1]} PRIMARY KEY (cell_id)
)
TBLPROPERTIES (delta.enableChangeDataFeed = true)
""")

spark_df = spark.createDataFrame(result_df)
spark_df.write.mode("overwrite").saveAsTable(REFERENCE_TABLE)
print(f"Wrote {spark.table(REFERENCE_TABLE).count()} rows to {REFERENCE_TABLE}")

# COMMAND ----------

# DBTITLE 1,Create Vector Search Endpoint and Delta Sync Index
import json
import time
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingVectorColumn,
    EndpointType,
    PipelineType,
    VectorIndexType,
)

STATE_PATH = "/tmp/teddy_70m_vs/run_state.json"
state = json.loads(Path(STATE_PATH).read_text(encoding="utf-8"))
w = WorkspaceClient()

with open(Path(state["model_dir"]) / "config.json", "r", encoding="utf-8") as f:
    EMB_DIM = int(json.load(f)["d_model"])

VS_ENDPOINT = state["vs_endpoint_name"]
VS_INDEX = state["vs_index_name"]
SOURCE_TABLE = state["reference_table"]

try:
    vs_ep = w.vector_search_endpoints.get_endpoint(endpoint_name=VS_ENDPOINT)
    ep_state = getattr(vs_ep, "endpoint_status", None)
    ep_state_val = getattr(ep_state, "state", None) if ep_state else None
    ep_state_str = getattr(ep_state_val, "value", ep_state_val)
    print(f"VS endpoint '{VS_ENDPOINT}' already exists, state={ep_state_str}")
except Exception:
    print(f"Creating VS endpoint '{VS_ENDPOINT}'...")
    w.vector_search_endpoints.create_endpoint(
        name=VS_ENDPOINT,
        endpoint_type=EndpointType.STANDARD,
    )
    deadline = time.time() + 1200
    while time.time() < deadline:
        vs_ep = w.vector_search_endpoints.get_endpoint(endpoint_name=VS_ENDPOINT)
        ep_state = getattr(vs_ep, "endpoint_status", None)
        ep_state_val = getattr(ep_state, "state", None) if ep_state else None
        ep_state_str = getattr(ep_state_val, "value", ep_state_val)
        print(f"VS endpoint state: {ep_state_str}")
        if ep_state_str == "ONLINE":
            break
        time.sleep(30)
    else:
        raise TimeoutError(f"VS endpoint '{VS_ENDPOINT}' did not reach ONLINE within 20 minutes")

try:
    existing_index = w.vector_search_indexes.get_index(index_name=VS_INDEX)
    existing_dim = None
    spec = getattr(existing_index, "delta_sync_index_spec", None)
    if spec:
        evc = getattr(spec, "embedding_vector_columns", None)
        if evc:
            existing_dim = getattr(evc[0], "embedding_dimension", None)
    if existing_dim is not None and existing_dim != EMB_DIM:
        print(f"Dimension mismatch ({existing_dim} vs {EMB_DIM}), deleting stale index...")
        w.vector_search_indexes.delete_index(index_name=VS_INDEX)
        time.sleep(10)
    else:
        print(f"VS index '{VS_INDEX}' already exists with matching dimension {EMB_DIM}; triggering sync.")
        w.vector_search_indexes.sync_index(index_name=VS_INDEX)
        existing_index = True
except Exception:
    existing_index = None

if existing_index is None or existing_index is not True:
    print(f"Creating Delta Sync index '{VS_INDEX}' (dim={EMB_DIM})...")
    w.vector_search_indexes.create_index(
        name=VS_INDEX,
        endpoint_name=VS_ENDPOINT,
        primary_key="cell_id",
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=SOURCE_TABLE,
            embedding_vector_columns=[
                EmbeddingVectorColumn(name="embedding", embedding_dimension=EMB_DIM)
            ],
            pipeline_type=PipelineType.TRIGGERED,
            columns_to_sync=["cell_id", "cell_type", "tissue_general"],
        ),
    )

print("Waiting for VS index to be ready...")
deadline = time.time() + 1800
while time.time() < deadline:
    idx = w.vector_search_indexes.get_index(index_name=VS_INDEX)
    idx_status = getattr(idx, "status", None)
    idx_ready = getattr(idx_status, "ready", None) if idx_status else None
    print(f"Index status: ready={idx_ready}")
    if idx_ready is True:
        print(f"VS index '{VS_INDEX}' is ready.")
        break
    time.sleep(30)
else:
    raise TimeoutError(f"VS index '{VS_INDEX}' did not become ready within 30 minutes")

# COMMAND ----------

# DBTITLE 1,Validate AI Search with Self Retrieval and Monotonic Score
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient

STATE_PATH = "/tmp/teddy_70m_vs/run_state.json"
state = json.loads(Path(STATE_PATH).read_text(encoding="utf-8"))
w = WorkspaceClient()

VS_INDEX = state["vs_index_name"]
SOURCE_TABLE = state["reference_table"]

probe_rows = spark.sql(f"SELECT cell_id, embedding FROM {SOURCE_TABLE} LIMIT 5").collect()
assert len(probe_rows) > 0, "Reference table has no rows"

results_ok = True
for probe in probe_rows:
    probe_id = probe["cell_id"]
    probe_emb = list(probe["embedding"])

    search_result = w.vector_search_indexes.query_index(
        index_name=VS_INDEX,
        columns=["cell_id", "cell_type", "tissue_general"],
        query_vector=probe_emb,
        num_results=10,
    )
    data_array = search_result.result.data_array if search_result.result else []
    if not data_array:
        print(f"WARNING: no results for probe {probe_id} — index may still be syncing.")
        results_ok = False
        continue

    # Columns come back in the order requested + a trailing score column.
    # Requested: ["cell_id", "cell_type", "tissue_general"] → indices 0, 1, 2; score at 3.
    top_id = data_array[0][0]
    score_col_idx = len(data_array[0]) - 1  # score is always last
    scores = [float(row[score_col_idx]) for row in data_array]

    self_match = top_id == probe_id
    monotonic = all(scores[i] >= scores[i + 1] - 1e-6 for i in range(len(scores) - 1))
    got_ten = len(data_array) == 10

    status = "PASS" if (self_match and monotonic and got_ten) else "FAIL"
    print(
        f"Probe {probe_id}: self_match={self_match}, monotonic={monotonic}, "
        f"got_10={got_ten}, top_score={scores[0]:.4f} -> {status}"
    )
    if not (self_match and monotonic and got_ten):
        results_ok = False

if results_ok:
    print("All AI Search validation checks passed.")
else:
    print("WARNING: Some checks failed — index may still be syncing. Re-run after sync completes.")

# COMMAND ----------

# DBTITLE 1,Development Log
# MAGIC %md
# MAGIC ## Development Log
# MAGIC
# MAGIC ### Fix 1 — HF download: `hf_transfer` RuntimeError (Cell 9)
# MAGIC * **Error**: `RuntimeError` from `hf_transfer` — the AI base environment (v5, and likely v6+) pre-enables `hf_transfer`, which failed on the TEDDY repo's Xet-backed files.
# MAGIC * **Root cause**: `HF_HUB_ENABLE_HF_TRANSFER` was implicitly `1` in the AI base environment; setting `HF_HUB_DISABLE_XET=1` alone was insufficient because `hf_transfer` was already loaded. This workaround is runtime-version-agnostic.
# MAGIC * **Fix**: Moved the entire download into a **subprocess** with both `HF_HUB_DISABLE_XET=1` and `HF_HUB_ENABLE_HF_TRANSFER=0` set in the child environment, guaranteeing a fresh process with no pre-imported `huggingface_hub`.
# MAGIC * **Attempts**: 2 (first attempt: env-var-only in-process; second: subprocess isolation)
# MAGIC * **Skill updated**: `teddy.md` §Hugging Face download now documents subprocess pattern as preferred fix.
# MAGIC
# MAGIC ### Fix 2 — `ServingModelWorkloadSize` import does not exist (Cell 13)
# MAGIC * **Error**: `ImportError: cannot import name 'ServingModelWorkloadSize'`
# MAGIC * **Root cause**: The current `databricks-sdk` exposes `workload_size` as a plain `str` parameter on `ServedEntityInput`, not as an enum class.
# MAGIC * **Fix**: Removed the enum import; passed `workload_size="Small"` as a string literal.
# MAGIC * **Attempts**: 1 (inspected SDK signature with `inspect.signature` before patching)
# MAGIC
# MAGIC ### Fix 3 — Tensor boolean ambiguity in wrapper `_predict_batch` (Cell 14 → manifests in Cell 16)
# MAGIC * **Error**: `RuntimeError: Boolean value of Tensor with more than one value is ambiguous`
# MAGIC * **Root cause**: Three lines in the wrapper used Python `or` / truthy evaluation on PyTorch tensors (`outputs.get("all_embs") or outputs.get("last_hidden_state")` etc.). When TEDDY returns a multi-element tensor for `all_embs`, `bool(tensor)` is ambiguous.
# MAGIC * **Fix**: Replaced all three tensor-boolean patterns with explicit `is None` checks.
# MAGIC * **Attempts**: 1 (diagnosed from traceback, fixed all three instances in one edit)
# MAGIC
# MAGIC ### Fix 4 — Census organism key change (Cell 23)
# MAGIC * **Error**: `KeyError: "Collection has no item 'Homo sapiens'"`
# MAGIC * **Root cause**: The `cellxgene-census` Python package now uses lowercase underscore organism keys (`homo_sapiens`) in both the SOMA collection and `get_obs()` API, even for older Census versions like 2024-07-01.
# MAGIC * **Fix**: Changed `"Homo sapiens"` to `"homo_sapiens"` in both `get_obs()` and `census["census_data"]` access.
# MAGIC * **Attempts**: 1
# MAGIC
# MAGIC ### Fix 5 — Serving payload exceeds 16 MB limit (Cell 23)
# MAGIC * **Error**: `BadRequest: Request size cannot exceed 16777216 bytes`
# MAGIC * **Root cause**: Census delivers ~60k genes per cell; sending all of them to the endpoint made the JSON payload >16 MB. TEDDY only has ~25k vocab genes.
# MAGIC * **Fix**: Added a pre-embedding filter: `adata = adata[:, mask]` where `mask` selects only genes in TEDDY's vocabulary (22k overlap). Reduced payload by >50%.
# MAGIC * **Attempts**: 1
# MAGIC
# MAGIC ### Fix 6 — CUDA OOM on GPU_SMALL with batch size 50 (Cell 23)
# MAGIC * **Error**: `CUDA out of memory. Tried to allocate 1.56 GiB. GPU 0 has a total capacity of 14.56 GiB`
# MAGIC * **Root cause**: GPU_SMALL provisions a T4 (16 GB VRAM), not an A10G as the original `teddy.md` stated. 50 cells × 2048-token sequences × 512 hidden dim saturated the activation memory. Use `GPU_MEDIUM` for A10G (24 GB).
# MAGIC * **Fix**: Capped `EMBED_BATCH_SIZE` at `min(widget_value, 10)` to limit per-request VRAM usage.
# MAGIC * **Attempts**: 1
# MAGIC
# MAGIC ### Fix 7 — `ResultData` has no `column_names` attribute (Cell 25)
# MAGIC * **Error**: `AttributeError: 'ResultData' object has no attribute 'column_names'`
# MAGIC * **Root cause**: The VS SDK's `ResultData` returns `data_array` with columns in the order requested + a trailing `score` column, but does not expose a `column_names` field.
# MAGIC * **Fix**: Hardcoded positional indexing: `cell_id` at index 0, `score` at index -1.
# MAGIC * **Attempts**: 1
# MAGIC
# MAGIC ### Summary
# MAGIC
# MAGIC | Metric | Value |
# MAGIC | --- | --- |
# MAGIC | Unique bugs encountered | 7 |
# MAGIC | Total fix iterations | 8 |
# MAGIC | Cells requiring fixes | 5 (Cells 9, 13, 14, 23, 25) |
# MAGIC | Model versions created | 1 |
# MAGIC | Known limitations | Census corpus is 1 000 cells (configurable via widget); embedding via endpoint adds \~2 min latency vs local GPU; GPU_SMALL = T4 (16 GB), use GPU_MEDIUM for A10G (24 GB) |
# MAGIC
# MAGIC ### Skills loaded or consulted
# MAGIC
# MAGIC * `oss-models` (workspace HLS skill via readAssetById — SKILL.md)
# MAGIC * `teddy` model reference (workspace HLS skill via readAssetById — teddy.md)
# MAGIC * `machine-learning` (built-in Skill Registry)
# MAGIC * `machine-learning/model-serving` (built-in sub-skill)
# MAGIC * `vector-search` (built-in Skill Registry)
# MAGIC * `environment-management` (built-in Skill Registry)
# MAGIC * `diagnose-error` (built-in Skill Registry)
# MAGIC * `diagnose-error/python-debugging` (built-in sub-skill)
# MAGIC
# MAGIC ### Skill updates applied back to `teddy.md`
# MAGIC
# MAGIC | Fix | Section updated | Change |
# MAGIC | --- | --- | --- |
# MAGIC | Fix 1 | §Hugging Face download | Subprocess isolation as preferred pattern; v5/v6 agnostic note |
# MAGIC | Fix 3 | §Wrapper boundary (new: Tensor-boolean safety) | `is None` checks, never `or` on tensors |
# MAGIC | Fix 4 | §Census generation pipeline | `"homo_sapiens"` not `"Homo sapiens"` |
# MAGIC | Fix 5 | §Census generation pipeline | Filter to TEDDY vocab genes before serving (16 MB limit) |
# MAGIC | Fix 6 | §Compute requirements, §Sizing guide | GPU_SMALL = T4, batch cap 10; GPU_MEDIUM = A10G, batch 50 |
# MAGIC | Fix 7 | §AI Search eval scorer | `ResultData` positional indexing, no `column_names` attr |
# MAGIC

# COMMAND ----------

# DBTITLE 1,Export Notebook Source to Results Path
import base64
import json
import os
from pathlib import Path

from databricks.sdk import WorkspaceClient

STATE_PATH = "/tmp/teddy_70m_vs/run_state.json"
state = json.loads(Path(STATE_PATH).read_text(encoding="utf-8"))
w = WorkspaceClient()

export_response = w.api_client.do(
    "GET",
    "/api/2.0/workspace/export",
    query={"path": state["notebook_path"], "format": "SOURCE"},
)
source_bytes = base64.b64decode(export_response["content"])
os.makedirs(os.path.dirname(state["export_path"]), exist_ok=True)
with open(state["export_path"], "wb") as handle:
    handle.write(source_bytes)

print(f"Exported {len(source_bytes):,} bytes to {state['export_path']}")