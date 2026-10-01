# Databricks notebook source
# MAGIC %md
# MAGIC # oss-001: TEDDY-70M Deploy — Baseline Arm
# MAGIC
# MAGIC **Eval protocol**: Each arm uses its own prompt. This is the **baseline** notebook — Genie Code uses only built-in knowledge, no custom skill files.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Baseline arm prompt (this notebook)
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat on **this** notebook → save response to `results/baseline/oss-001.txt`
# MAGIC
# MAGIC > Deploy TEDDY-70M as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/teddy`. Register the model as `<catalog>.skills.teddy_70m_baseline` and name the endpoint `teddy_70m_baseline`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it's in a FAILED state or doesn't exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don't leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Final step**: Export this notebook's source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-001.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Skill arm prompt (other notebook)
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat on the **skill** notebook → save response to `results/with_skill/oss-001.txt`
# MAGIC
# MAGIC > Deploy TEDDY-70M as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/teddy`. Register the model as `<catalog>.skills.teddy_70m` and name the endpoint `teddy_70m`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it's in a FAILED state or doesn't exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don't leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project's HLS model-deployment skill and TEDDY model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/oss-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/oss-models/references/models/teddy.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Final step**: Export this notebook's source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-001.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## What's different between the prompts
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | Explicit `readAssetById` paths to `SKILL.md` + `teddy.md` | None — Genie Code uses only built-in knowledge |
# MAGIC | **Volume path** | `/Volumes/.../test_with/...` | `/Volumes/.../test_without/...` |
# MAGIC | **UC model name** | `<catalog>.skills.teddy_70m` | `<catalog>.skills.teddy_70m_baseline` |
# MAGIC | **Endpoint name** | `teddy_70m` | `teddy_70m_baseline` |
# MAGIC | **Everything else** | Identical | Identical |
# MAGIC
# MAGIC ## What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (GPU\_SMALL? GPU\_MEDIUM? CPU?)
# MAGIC * Notebook structure (one notebook? two? CPU/GPU split?)
# MAGIC * Whether to enable inference tables and AI Gateway usage tracking
# MAGIC * Whether to set up Vector Search
# MAGIC * Dependency versions (especially `transformers` pinning)
# MAGIC * Download method and staging path
# MAGIC * HF Xet backend handling
# MAGIC * Serving contract shape
# MAGIC * Code-bundle stripping strategy
# MAGIC
# MAGIC > **Scoring rubric**: see [04_eval_rubric_and_compare](#notebook-390164024659896) Cell 2 for the full sub-check rubric.
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

# DBTITLE 1,Install Dependencies
# MAGIC %pip install huggingface_hub safetensors --quiet

# COMMAND ----------

# DBTITLE 1,Restart Python after pip install
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Reinitialize imports config and define endpoint diagnos ...
# Re-establish config after kernel restart
import base64
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
import transformers
from mlflow import MlflowClient
from mlflow.models import infer_signature
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    EndpointStateConfigUpdate,
    EndpointStateReady,
    ServedEntityInput,
    ServingModelWorkloadType,
)

# Config (duplicated because restartPython clears state)
CATALOG = "<catalog>"
SCHEMA = "skills"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/test_without/models/teddy"
REGISTERED_MODEL_NAME = f"{CATALOG}.{SCHEMA}.teddy_70m_baseline"
ENDPOINT_NAME = "teddy_70m_baseline"
SERVED_ENTITY_NAME = "teddy70mbaseline"
HF_REPO_ID = "Merck/TEDDY"
MODEL_SUBDIR = "teddy/models/teddy_g/70M"
REPO_BUNDLE_DIR = os.path.join(VOLUME_PATH, "bundle")
MODEL_DIR = os.path.join(REPO_BUNDLE_DIR, MODEL_SUBDIR)
SERVING_TIMEOUT_MIN = 45
PRIMARY_WORKLOAD = "CPU"
PRIMARY_WORKLOAD_SIZE = "Small"
FALLBACK_WORKLOAD = "GPU_SMALL"
FALLBACK_WORKLOAD_SIZE = "Small"
LOCAL_TEST_INPUT = {
    "gene_ids": [101, 205, 999, 1200, 2048, 43811],
    "mean_pool": True,
}
NOTEBOOK_PATH = "/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/test02_TEDDY-70M_Deploy_Baseline"
EXPORT_PATH = "/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-001.txt"

w = WorkspaceClient()
mlflow.set_registry_uri("databricks-uc")


def as_jsonable(obj):
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    if isinstance(obj, dict):
        return obj
    return str(obj)


def fetch_endpoint_diagnostics(client, endpoint_name, served_entity_name):
    diagnostics = {}
    try:
        diagnostics["endpoint"] = as_jsonable(client.serving_endpoints.get(endpoint_name))
    except Exception as exc:
        diagnostics["endpoint_error"] = str(exc)

    try:
        diagnostics["build_logs"] = as_jsonable(
            client.serving_endpoints.build_logs(endpoint_name, served_entity_name)
        )
    except Exception as exc:
        diagnostics["build_logs_error"] = str(exc)

    try:
        diagnostics["server_logs"] = as_jsonable(
            client.serving_endpoints.logs(endpoint_name, served_entity_name)
        )
    except Exception as exc:
        diagnostics["server_logs_error"] = str(exc)

    return diagnostics


print("Imports and config ready.")
print(f"MLflow version:      {mlflow.__version__}")
print(f"Transformers version:{transformers.__version__}")
print(f"Torch version:       {torch.__version__}")
print(f"Workspace host:      {w.config.host}")

# COMMAND ----------

# DBTITLE 1,Idempotency — check endpoint state and clean up if needed
# Idempotency logic:
# - If endpoint is READY + NOT_UPDATING -> skip cleanup and reuse it.
# - If endpoint is still UPDATING -> wait until it settles, then re-check.
# - If endpoint is FAILED / canceled / not present -> clean up and do a fresh deployment.

def get_endpoint_detail(client, name):
    try:
        return client.serving_endpoints.get(name)
    except (NotFound, ResourceDoesNotExist):
        return None


def delete_endpoint_if_exists(client, name, wait_timeout_min=20):
    endpoint = get_endpoint_detail(client, name)
    if endpoint is None:
        print(f"  Endpoint '{name}' does not exist (nothing to delete)")
        return

    client.serving_endpoints.delete(name)
    deadline = time.time() + (wait_timeout_min * 60)
    while time.time() < deadline:
        if get_endpoint_detail(client, name) is None:
            print(f"  Deleted endpoint '{name}'")
            return
        time.sleep(10)
    raise TimeoutError(f"Timed out waiting for endpoint '{name}' deletion")


def delete_all_model_versions(model_name):
    registry_client = MlflowClient(registry_uri="databricks-uc")
    try:
        versions = list(registry_client.search_model_versions(f"name='{model_name}'"))
        if not versions:
            print(f"  No model versions found for '{model_name}'")
        for version in versions:
            registry_client.delete_model_version(name=model_name, version=version.version)
            print(f"  Deleted model version {version.version}")
        try:
            registry_client.delete_registered_model(name=model_name)
            print(f"  Deleted registered model '{model_name}'")
        except Exception as exc:
            if "not found" in str(exc).lower() or "RESOURCE_DOES_NOT_EXIST" in str(exc):
                print(f"  Registered model '{model_name}' does not exist (nothing to delete)")
            else:
                raise
    except Exception as exc:
        if "not found" in str(exc).lower() or "RESOURCE_DOES_NOT_EXIST" in str(exc):
            print(f"  Registered model '{model_name}' does not exist (nothing to delete)")
        else:
            raise


endpoint = get_endpoint_detail(w, ENDPOINT_NAME)
if endpoint is not None and endpoint.state.config_update == EndpointStateConfigUpdate.IN_PROGRESS:
    print(f"Endpoint '{ENDPOINT_NAME}' is still updating. Waiting for it to settle before deciding...")
    w.serving_endpoints.wait_get_serving_endpoint_not_updating(
        ENDPOINT_NAME,
        timeout=timedelta(minutes=SERVING_TIMEOUT_MIN),
    )
    endpoint = get_endpoint_detail(w, ENDPOINT_NAME)

if (
    endpoint is not None
    and endpoint.state.ready == EndpointStateReady.READY
    and endpoint.state.config_update == EndpointStateConfigUpdate.NOT_UPDATING
):
    SKIP_DEPLOY = True
    print(f"Endpoint '{ENDPOINT_NAME}' is already READY. Skipping cleanup and redeploy.")
else:
    SKIP_DEPLOY = False
    print("\n--- Cleanup ---")
    if endpoint is None:
        print(f"Endpoint '{ENDPOINT_NAME}' does not exist. Cleaning up any leftover model versions...")
    else:
        print(
            f"Endpoint '{ENDPOINT_NAME}' is in state "
            f"{endpoint.state.ready.value}/{endpoint.state.config_update.value}. "
            "Cleaning it up before a fresh deployment..."
        )
        delete_endpoint_if_exists(w, ENDPOINT_NAME)

    delete_all_model_versions(REGISTERED_MODEL_NAME)
    print("\nCleanup complete. Proceeding with fresh deployment.")

# COMMAND ----------

# DBTITLE 1,Download and stage TEDDY files
from huggingface_hub import hf_hub_download

REQUIRED_REPO_FILES = [
    "teddy/__init__.py",
    "teddy/models/__init__.py",
    "teddy/models/classification_heads.py",
    "teddy/models/teddy_g/__init__.py",
    "teddy/models/teddy_g/model.py",
    "teddy/models/teddy_g/70M/added_tokens.json",
    "teddy/models/teddy_g/70M/config.json",
    "teddy/models/teddy_g/70M/model.safetensors",
    "teddy/models/teddy_g/70M/special_tokens_map.json",
    "teddy/models/teddy_g/70M/tokenizer_config.json",
    "teddy/models/teddy_g/70M/vocab.txt",
]

if SKIP_DEPLOY:
    print("Skipping TEDDY artifact staging because the endpoint is already READY.")
else:
    os.makedirs(REPO_BUNDLE_DIR, exist_ok=True)
    copied_files = []
    for relative_path in REQUIRED_REPO_FILES:
        source_path = hf_hub_download(repo_id=HF_REPO_ID, filename=relative_path)
        target_path = os.path.join(REPO_BUNDLE_DIR, relative_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copyfile(source_path, target_path)
        copied_files.append(target_path)

    print(f"Staged {len(copied_files)} files under {REPO_BUNDLE_DIR}")
    for staged_path in copied_files:
        print("  ", os.path.relpath(staged_path, REPO_BUNDLE_DIR))

    with open(os.path.join(MODEL_DIR, "added_tokens.json"), "r", encoding="utf-8") as handle:
        PAD_TOKEN_ID = json.load(handle)["<pad>"]

    print(f"Resolved pad token id: {PAD_TOKEN_ID}")

# COMMAND ----------

# DBTITLE 1,Define TEDDY pyfunc wrapper
class TeddyEmbeddingPyFunc(mlflow.pyfunc.PythonModel):
    MODEL_SUBDIR = "teddy/models/teddy_g/70M"

    def load_context(self, context):
        repo_root = context.artifacts["repo_root"]
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)

        from teddy.models.teddy_g.model import TeddyGConfig, TeddyGModel

        model_dir = os.path.join(repo_root, self.MODEL_SUBDIR)
        with open(os.path.join(model_dir, "added_tokens.json"), "r", encoding="utf-8") as handle:
            self.pad_token_id = json.load(handle)["<pad>"]

        config = TeddyGConfig.from_pretrained(model_dir)
        config.pad_token_id = self.pad_token_id
        self.model = TeddyGModel.from_pretrained(model_dir, config=config)
        self.model.return_all_embs = True
        self.model.eval()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)

    @staticmethod
    def _coerce_gene_ids(value):
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, (list, tuple)) or len(value) == 0:
            raise ValueError("Each row must provide a non-empty 'gene_ids' list.")
        return [int(token_id) for token_id in value]

    def predict(self, context, model_input):
        if isinstance(model_input, pd.DataFrame):
            records = model_input.to_dict(orient="records")
        elif isinstance(model_input, list):
            records = model_input
        else:
            raise TypeError("model_input must be a pandas DataFrame or a list of dictionaries")

        sequences = [self._coerce_gene_ids(row["gene_ids"]) for row in records]
        pool_flags = [bool(row.get("mean_pool", True)) for row in records]
        max_len = min(max(len(sequence) for sequence in sequences), int(self.model.config.max_position_embeddings))

        input_ids = torch.full(
            (len(sequences), max_len),
            self.pad_token_id,
            dtype=torch.long,
            device=self.device,
        )
        attention_mask = torch.zeros(
            (len(sequences), max_len),
            dtype=torch.long,
            device=self.device,
        )

        for row_idx, sequence in enumerate(sequences):
            clipped = sequence[:max_len]
            input_ids[row_idx, : len(clipped)] = torch.tensor(clipped, dtype=torch.long, device=self.device)
            attention_mask[row_idx, : len(clipped)] = 1

        with torch.no_grad():
            outputs = self.model(
                gene_ids=input_ids,
                attention_mask=attention_mask,
                return_outputs=True,
            )

        all_embeddings = outputs["all_embs"]
        rows = []
        for row_idx, sequence in enumerate(sequences):
            seq_len = min(len(sequence), max_len)
            valid_embeddings = all_embeddings[row_idx, :seq_len, :]
            if pool_flags[row_idx]:
                embedding = valid_embeddings.mean(dim=0)
            else:
                embedding = valid_embeddings[0]
            rows.append(
                {
                    "cell_embedding": embedding.detach().cpu().tolist(),
                    "seq_len": int(seq_len),
                    "embedding_dim": int(embedding.shape[0]),
                    "pooled": bool(pool_flags[row_idx]),
                }
            )
        return pd.DataFrame(rows)


def local_bundle_predict(model_input: pd.DataFrame) -> pd.DataFrame:
    if REPO_BUNDLE_DIR not in sys.path:
        sys.path.insert(0, REPO_BUNDLE_DIR)

    from teddy.models.teddy_g.model import TeddyGConfig, TeddyGModel

    with open(os.path.join(MODEL_DIR, "added_tokens.json"), "r", encoding="utf-8") as handle:
        pad_token_id = json.load(handle)["<pad>"]

    config = TeddyGConfig.from_pretrained(MODEL_DIR)
    config.pad_token_id = pad_token_id
    model = TeddyGModel.from_pretrained(MODEL_DIR, config=config)
    model.return_all_embs = True
    model.eval()

    sequences = [TeddyEmbeddingPyFunc._coerce_gene_ids(value) for value in model_input["gene_ids"]]
    pool_flags = [bool(value) for value in model_input.get("mean_pool", True)]
    max_len = min(max(len(sequence) for sequence in sequences), int(model.config.max_position_embeddings))

    input_ids = torch.full((len(sequences), max_len), pad_token_id, dtype=torch.long)
    attention_mask = torch.zeros((len(sequences), max_len), dtype=torch.long)

    for row_idx, sequence in enumerate(sequences):
        clipped = sequence[:max_len]
        input_ids[row_idx, : len(clipped)] = torch.tensor(clipped, dtype=torch.long)
        attention_mask[row_idx, : len(clipped)] = 1

    with torch.no_grad():
        outputs = model(gene_ids=input_ids, attention_mask=attention_mask, return_outputs=True)

    all_embeddings = outputs["all_embs"]
    rows = []
    for row_idx, sequence in enumerate(sequences):
        seq_len = min(len(sequence), max_len)
        valid_embeddings = all_embeddings[row_idx, :seq_len, :]
        if pool_flags[row_idx]:
            embedding = valid_embeddings.mean(dim=0)
        else:
            embedding = valid_embeddings[0]
        rows.append(
            {
                "cell_embedding": embedding.detach().cpu().tolist(),
                "seq_len": int(seq_len),
                "embedding_dim": int(embedding.shape[0]),
                "pooled": bool(pool_flags[row_idx]),
            }
        )

    return pd.DataFrame(rows)


print("Defined the local inference helper and the serving pyfunc wrapper.")

# COMMAND ----------

# DBTITLE 1,Log the MLflow model artifact
if SKIP_DEPLOY:
    print("Skipping MLflow packaging because the endpoint is already READY.")
else:
    input_example = pd.DataFrame(
        [
            LOCAL_TEST_INPUT,
            {"gene_ids": [7, 14, 21, 28], "mean_pool": False},
        ]
    )
    output_example = local_bundle_predict(input_example)
    signature = infer_signature(input_example, output_example)
    display(output_example)

    pip_requirements = [
        f"torch=={torch.__version__.split('+')[0]}",
        f"transformers=={transformers.__version__}",
        f"pandas=={pd.__version__}",
        f"numpy=={np.__version__}",
        "safetensors",
    ]

    with mlflow.start_run(run_name="teddy_70m_baseline_packaging"):
        mlflow.log_params(
            {
                "hf_repo_id": HF_REPO_ID,
                "registered_model_name": REGISTERED_MODEL_NAME,
                "endpoint_name": ENDPOINT_NAME,
                "primary_workload": PRIMARY_WORKLOAD,
                "fallback_workload": FALLBACK_WORKLOAD,
            }
        )
        log_kwargs = dict(
            python_model=TeddyEmbeddingPyFunc(),
            artifacts={"repo_root": REPO_BUNDLE_DIR},
            signature=signature,
            input_example=input_example,
            pip_requirements=pip_requirements,
        )
        try:
            model_info = mlflow.pyfunc.log_model(name="model", **log_kwargs)
        except TypeError:
            model_info = mlflow.pyfunc.log_model(artifact_path="model", **log_kwargs)

    print(f"Logged model artifact: {model_info.model_uri}")

# COMMAND ----------

# DBTITLE 1,Run local pyfunc round-trip gate
if SKIP_DEPLOY:
    print("Skipping the local pyfunc round-trip because the endpoint is already READY.")
else:
    local_model = mlflow.pyfunc.load_model(model_info.model_uri)
    local_predictions = local_model.predict(pd.DataFrame([LOCAL_TEST_INPUT]))
    display(local_predictions)

    assert int(local_predictions.iloc[0]["embedding_dim"]) == 512, "Unexpected embedding width"
    assert int(local_predictions.iloc[0]["seq_len"]) == len(LOCAL_TEST_INPUT["gene_ids"]), "Sequence length mismatch"
    print("Local pyfunc round-trip passed.")

# COMMAND ----------

# DBTITLE 1,Register the model in Unity Catalog
if SKIP_DEPLOY:
    existing_endpoint = w.serving_endpoints.get(ENDPOINT_NAME)
    MODEL_VERSION = existing_endpoint.config.served_entities[0].entity_version
    print(f"Reusing existing served model version: {MODEL_VERSION}")
else:
    registered_version = mlflow.register_model(
        model_uri=model_info.model_uri,
        name=REGISTERED_MODEL_NAME,
        await_registration_for=300,
    )
    MODEL_VERSION = registered_version.version
    print(f"Registered Unity Catalog model version: {MODEL_VERSION}")

# COMMAND ----------

# DBTITLE 1,Create or update the serving endpoint
if SKIP_DEPLOY:
    print(f"Endpoint '{ENDPOINT_NAME}' is already READY. Deployment cell is a no-op.")
else:
    deployment_attempts = [
        {
            "workload_type": ServingModelWorkloadType.CPU,
            "workload_size": PRIMARY_WORKLOAD_SIZE,
            "label": f"{PRIMARY_WORKLOAD}/{PRIMARY_WORKLOAD_SIZE}",
            "reason": "TEDDY-G 70M is demonstrated on CPU in the upstream tutorial, so CPU is the lowest-cost first attempt.",
        },
        {
            "workload_type": ServingModelWorkloadType.GPU_SMALL,
            "workload_size": FALLBACK_WORKLOAD_SIZE,
            "label": f"{FALLBACK_WORKLOAD}/{FALLBACK_WORKLOAD_SIZE}",
            "reason": "Fallback if the CPU deployment fails during model build or startup.",
        },
    ]

    SELECTED_WORKLOAD = None
    last_exception = None

    for attempt_number, attempt in enumerate(deployment_attempts, start=1):
        served_entity = ServedEntityInput(
            name=SERVED_ENTITY_NAME,
            entity_name=REGISTERED_MODEL_NAME,
            entity_version=str(MODEL_VERSION),
            workload_type=attempt["workload_type"],
            workload_size=attempt["workload_size"],
            scale_to_zero_enabled=False,
        )
        endpoint_config = EndpointCoreConfigInput(served_entities=[served_entity])
        print(f"Attempt {attempt_number}: deploying with {attempt['label']}")
        print(f"Reason: {attempt['reason']}")

        try:
            existing_endpoint = get_endpoint_detail(w, ENDPOINT_NAME)
            if existing_endpoint is None:
                w.serving_endpoints.create(name=ENDPOINT_NAME, config=endpoint_config)
            else:
                w.serving_endpoints.update_config(
                    name=ENDPOINT_NAME,
                    served_entities=[served_entity],
                )

            w.serving_endpoints.wait_get_serving_endpoint_not_updating(
                ENDPOINT_NAME,
                timeout=timedelta(minutes=SERVING_TIMEOUT_MIN),
            )
            endpoint = w.serving_endpoints.get(ENDPOINT_NAME)
            print(
                f"Endpoint settled in state "
                f"{endpoint.state.ready.value}/{endpoint.state.config_update.value}"
            )

            if (
                endpoint.state.ready == EndpointStateReady.READY
                and endpoint.state.config_update == EndpointStateConfigUpdate.NOT_UPDATING
            ):
                SELECTED_WORKLOAD = attempt["label"]
                break

            diagnostics = fetch_endpoint_diagnostics(w, ENDPOINT_NAME, SERVED_ENTITY_NAME)
            raise RuntimeError(
                "Endpoint did not reach READY. Diagnostics:\n"
                + json.dumps(diagnostics, indent=2)[:20000]
            )
        except Exception as exc:
            last_exception = exc
            print(f"Attempt {attempt_number} failed: {exc}")
            diagnostics = fetch_endpoint_diagnostics(w, ENDPOINT_NAME, SERVED_ENTITY_NAME)
            print(json.dumps(diagnostics, indent=2)[:20000])
            if attempt_number < len(deployment_attempts):
                print("Cleaning up failed endpoint state before retrying...")
                delete_endpoint_if_exists(w, ENDPOINT_NAME)
            else:
                raise

    if SELECTED_WORKLOAD is None:
        raise RuntimeError(f"Deployment did not succeed after retries: {last_exception}")

    print(f"Endpoint '{ENDPOINT_NAME}' is READY using workload {SELECTED_WORKLOAD}")

# COMMAND ----------

# DBTITLE 1,Smoke-test the serving endpoint
endpoint_test_records = [LOCAL_TEST_INPUT]
endpoint_response = w.serving_endpoints.query(
    ENDPOINT_NAME,
    dataframe_records=endpoint_test_records,
)
endpoint_response_dict = as_jsonable(endpoint_response)
print(json.dumps(endpoint_response_dict, indent=2)[:20000])

# COMMAND ----------

# DBTITLE 1,Export notebook source to results path
export_response = w.api_client.do(
    "GET",
    "/api/2.0/workspace/export",
    query={"path": NOTEBOOK_PATH, "format": "SOURCE"},
)
source_bytes = base64.b64decode(export_response["content"])
os.makedirs(os.path.dirname(EXPORT_PATH), exist_ok=True)
with open(EXPORT_PATH, "wb") as handle:
    handle.write(source_bytes)

print(f"Exported {len(source_bytes):,} bytes to {EXPORT_PATH}")

# COMMAND ----------

# DBTITLE 1,Decisions and loaded skills
# MAGIC %md
# MAGIC ## Decisions and loaded skills
# MAGIC
# MAGIC * The notebook stages a minimal TEDDY bundle into the Unity Catalog volume instead of cloning the entire repository, so the logged artifact contains only the files needed at inference time.
# MAGIC * The model is packaged as a custom MLflow pyfunc because TEDDY-70M is a custom embedding architecture rather than a stock text-generation pipeline.
# MAGIC * The deployment tries `CPU` first because the TEDDY tutorial explicitly demonstrates the 70M checkpoint on CPU, then retries with `GPU_SMALL` if serving build or startup fails.
# MAGIC * A local pyfunc round-trip runs before endpoint creation so packaging errors fail fast instead of surfacing after a long serving build.
# MAGIC * Skill Registry items loaded or consulted while developing this notebook:
# MAGIC   * `machine-learning`
# MAGIC   * `environment-management`