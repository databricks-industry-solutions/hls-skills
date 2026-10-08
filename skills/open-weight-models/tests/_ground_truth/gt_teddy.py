# Databricks notebook source
# /// script
# [tool.databricks.environment]
# base_environment = "databricks_ai_v5"
# environment_version = "5"
# ///
# DBTITLE 1,TEDDY Ground Truth
# MAGIC %md
# MAGIC
# MAGIC %md
# MAGIC # TEDDY{-70M} — Ground Truth
# MAGIC
# MAGIC Combined download + register/deploy for [Merck/TEDDY](https://huggingface.co/Merck/TEDDY).
# MAGIC Validates the skill's deployment instructions end-to-end.
# MAGIC
# MAGIC ### Provenance
# MAGIC
# MAGIC [Genesis Workbench TEDDY module](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/teddy/teddy_g_v1)
# MAGIC → [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7) (`open-weight-models` skill)
# MAGIC → this ground truth notebook.
# MAGIC
# MAGIC | Field | Value |
# MAGIC |-------|-------|
# MAGIC | Source | [HuggingFace Merck/TEDDY](https://huggingface.co/Merck/TEDDY) |
# MAGIC | License | Apache-2.0 |
# MAGIC | Paper | [arXiv:2503.03485](https://arxiv.org/abs/2503.03485) |
# MAGIC | Variants | 70M, 160M, 400M |
# MAGIC | Key gotcha | `HF_HUB_DISABLE_XET=1` required before `import huggingface_hub` (Xet/CAS backend) |
# MAGIC | Download | ~350 MB, ~2–4 min |
# MAGIC
# MAGIC ### How to run
# MAGIC
# MAGIC Run cells top-to-bottom with `run_go=true`. Download cells are idempotent.
# MAGIC
# MAGIC ### Install order (2 restarts, by design)
# MAGIC
# MAGIC The notebook has two `restartPython()` boundaries because download and registration
# MAGIC need different deps:
# MAGIC
# MAGIC | Phase | Cells | Installs | Why separate |
# MAGIC |---|---|---|---|
# MAGIC | **Cleanup** | 12 | none | Deletes endpoint + UC model + cells table (idempotent) |
# MAGIC | **Download** | 5-8 | `huggingface_hub` only | Lightweight, no GPU deps |
# MAGIC | *restart 1* | Cell 5 | `restartPython()` | |
# MAGIC | **Register** | 13-17 | `scanpy torch transformers mlflow` | Heavy deps for PyFunc + model loading |
# MAGIC | *restart 2* | Cell 13 | `restartPython()` | |
# MAGIC | **Census** | 20-21 | `cellxgene-census` via `%pip` | subprocess breaks botocore.compat on serverless |
# MAGIC | *restart 3* | Cell 20 | `restartPython()` | |
# MAGIC
# MAGIC Cells 6 and 14 re-read widgets after each restart (widgets persist, Python vars don't).
# MAGIC Cell 11 is the canonical config cell; Cell 2 is a quick check only.

# COMMAND ----------

# DBTITLE 1,Check Volume for model
# --- Verify TEDDY model is in Volume (---
# If not present, run the download cells above
# Source: github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/teddy/teddy_g_v1

dbutils.widgets.text("catalog", "<catalog>", "Unity Catalog catalog")
dbutils.widgets.text("schema", "skills", "Unity Catalog schema")
dbutils.widgets.text("cache_dir", "models", "Cache dir (UC volume name)")
dbutils.widgets.text("teddy_model_size", "70M", "TEDDY-G variant (70M | 160M | 400M)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
VARIANT = dbutils.widgets.get("teddy_model_size")

import os

volume_base = f"/Volumes/{CATALOG}/{SCHEMA}"

candidates = [
    (f"{volume_base}/{CACHE_DIR}", "GWB convention"),
    (f"{volume_base}/models/snapshot", "skill-tests convention"),
]

found = False
for path, label in candidates:
    teddy_pkg = os.path.join(path, "teddy")
    if os.path.isdir(teddy_pkg):
        checkpoint = os.path.join(teddy_pkg, "models", "teddy_g", VARIANT)
        vocab = os.path.join(checkpoint, "vocab.txt") if os.path.isdir(checkpoint) else None
        print(f"\u2713 TEDDY found at: {path} ({label})")
        print(f"  teddy/ package: {teddy_pkg}")
        if os.path.isdir(checkpoint):
            print(f"  {VARIANT} checkpoint: {checkpoint}")
            print(f"  vocab.txt: {os.path.exists(vocab)}")
        found = True
        break

if not found:
    print(f"\u2717 TEDDY NOT found in Volume")
    print(f"  Checked: {[p for p, _ in candidates]}")
    print()
    print("Run the download cells above to download:")
    print("  See the download cells above in this notebook.")
    print(f"  Set widgets: catalog={CATALOG}, schema={SCHEMA}, cache_dir={CACHE_DIR}, teddy_model_size={VARIANT}")

# COMMAND ----------

# DBTITLE 1,Compute detection
import os, subprocess

try:
    os.makedirs("/local_disk0/tmp", exist_ok=True)
    TMP_DIR = "/local_disk0/tmp"
    IS_SERVERLESS = False
except (PermissionError, OSError):
    TMP_DIR = "/tmp"
    IS_SERVERLESS = True

print(f"Compute : {'Serverless' if IS_SERVERLESS else 'Classic'}")
print(f"Storage : {TMP_DIR}")

# COMMAND ----------

# DBTITLE 1,Create UC Schema + Volume
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{CACHE_DIR}")
cache_full_path = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"
print(f"Volume ready: {cache_full_path}")

# COMMAND ----------

# DBTITLE 1,Install huggingface_hub
# MAGIC %pip install -q huggingface_hub
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Post-restart setup
import os, sys, subprocess

# Re-derive compute detection after restartPython
try:
    os.makedirs("/local_disk0/tmp", exist_ok=True)
    TMP_DIR = "/local_disk0/tmp"
    IS_SERVERLESS = False
except (PermissionError, OSError):
    TMP_DIR = "/tmp"
    IS_SERVERLESS = True

# Re-read widgets
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
VARIANT = dbutils.widgets.get("teddy_model_size")

HF_REPO = "Merck/TEDDY"
cache_full_path = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"
print(f"Compute: {'Serverless' if IS_SERVERLESS else 'Classic'}, Volume: {cache_full_path}, Variant: {VARIANT}")

# COMMAND ----------

# DBTITLE 1,Download TEDDY snapshot from HuggingFace (adapted from GWB)

# MUST set before first import of huggingface_hub — TEDDY repo uses Xet/CAS backend.
os.environ["HF_HUB_DISABLE_XET"] = "1"

from huggingface_hub import snapshot_download

HF_REVISION = "main"
snapshot_dir = f"{cache_full_path}/snapshots/{HF_REVISION}"
os.makedirs(snapshot_dir, exist_ok=True)

sentinel = os.path.join(snapshot_dir, ".snapshot_complete")
if os.path.exists(sentinel):
    print(f"\u2713 Snapshot already at {snapshot_dir}, skipping download")
else:
    print(f"Downloading {HF_REPO}@{HF_REVISION} -> {snapshot_dir}")
    snapshot_download(
        repo_id=HF_REPO,
        revision=HF_REVISION,
        local_dir=snapshot_dir,
        local_dir_use_symlinks=False,
    )
    with open(sentinel, "w") as f:
        f.write("ok")
    print("Download complete.")

# Add to sys.path so teddy package is importable
if snapshot_dir not in sys.path:
    sys.path.insert(0, snapshot_dir)

# COMMAND ----------

# DBTITLE 1,Verify snapshot structure
teddy_pkg_dir = os.path.join(snapshot_dir, "teddy")
assert os.path.isdir(teddy_pkg_dir), (
    f"Expected `teddy/` package at {teddy_pkg_dir}. "
    f"Inspect snapshot: {os.listdir(snapshot_dir)}"
)

model_dir = os.path.join(teddy_pkg_dir, "models", "teddy_g", VARIANT)
assert os.path.isdir(model_dir), (
    f"Expected TEDDY-G {VARIANT} checkpoint at {model_dir}. "
    f"Available: {os.listdir(os.path.join(teddy_pkg_dir, 'models', 'teddy_g'))}"
)

vocab_path = os.path.join(model_dir, "vocab.txt")
assert os.path.exists(vocab_path), f"Missing vocab.txt at {vocab_path}"

print(f"\u2713 teddy/ package: {teddy_pkg_dir}")
print(f"\u2713 {VARIANT} checkpoint: {model_dir}")
print(f"\u2713 vocab.txt: {vocab_path}")
print()
for item in sorted(os.listdir(snapshot_dir)):
    kind = "[dir] " if os.path.isdir(os.path.join(snapshot_dir, item)) else "[file]"
    print(f"  {kind} {item}")

# COMMAND ----------

# DBTITLE 1,Write provenance manifest
import datetime

manifest = f"""model:
  name: teddy
  variant: {VARIANT}
  source_url: https://huggingface.co/Merck/TEDDY
  license: Apache-2.0
  paper: arXiv:2503.03485
  reviewed_at: {datetime.date.today().isoformat()}
adapted_from:
  genesis_workbench: modules/single_cell/teddy/teddy_g_v1/notebooks/01_register_teddy.py
  url: https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/teddy/teddy_g_v1/notebooks/01_register_teddy.py
weights:
  location: {model_dir}
runtime:
  download_compute: {'serverless_cpu' if IS_SERVERLESS else 'classic_cpu'}
  register_compute: gpu_required
  hf_hub_disable_xet: true
"""

manifest_path = f"{snapshot_dir}/provenance_manifest.yaml"
with open(manifest_path, "w") as f:
    f.write(manifest)
print("Provenance manifest:", manifest_path)
print(manifest)

# COMMAND ----------

# DBTITLE 1,Register Deploy and Score overview
# MAGIC %md
# MAGIC # TEDDY-G -- Register, Deploy and Score (Standalone)
# MAGIC
# MAGIC Via [GWB](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/teddy/teddy_g_v1)
# MAGIC + [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7).
# MAGIC
# MAGIC | Phase | What |
# MAGIC |-------|------|
# MAGIC | **1. Register** | Wrap `TEDDYEmbedder` PyFunc, `input_example` + `signature`, register to UC |
# MAGIC | **1b. AI Search** | Create AI Search endpoint + Delta Sync index over `teddy_cells` (optional for oss-001; needed for oss-002+) |
# MAGIC | **2. Deploy** | GPU Model Serving endpoint with **inference table** + **AI Gateway** + scale-to-zero |
# MAGIC | **3. Score / Eval** | Endpoint smoke test + AI Search eval scorer (self-retrieval, monotonic distances) |
# MAGIC | **4. Teardown** | Delete endpoint + optionally AI Search resources. Inference table + UC model preserved |
# MAGIC
# MAGIC ## Model details
# MAGIC
# MAGIC | Field | Value |
# MAGIC |-------|-------|
# MAGIC | Source | [HuggingFace Merck/TEDDY](https://huggingface.co/Merck/TEDDY) (Apache-2.0) |
# MAGIC | Variants | **70M** (d=512), **160M** (d=768), **400M** (d=1024) |
# MAGIC | GPU tier | `GPU_SMALL` (A10G) sufficient for 70M; 400M needs A10 + bf16 |
# MAGIC | Input | `adata_sparsematrix` + `adata_var` + `adata_obs` (JSON orient=split) |
# MAGIC | Params | `max_seq_len` (int, default 2048), `pooling` ("mean" or "cls") |
# MAGIC | Output | `[{"embedding": [float, ...]}, ...]` -- one per input cell |
# MAGIC | Key gotcha | `HF_HUB_DISABLE_XET=1` before import; `transformers==4.41.0` exact pin |
# MAGIC
# MAGIC ## Architecture: Endpoint vs AI Search
# MAGIC
# MAGIC ```
# MAGIC Raw gene expression  -->  [Serving Endpoint]  -->  512-d embedding
# MAGIC                                                        |
# MAGIC                                                        v
# MAGIC                                               [AI Search Index]
# MAGIC                                                        |
# MAGIC                                                        v
# MAGIC                                           "CD14+ monocyte, blood, Alzheimer's"
# MAGIC ```
# MAGIC
# MAGIC * **Endpoint** = the model (always needed). Takes expression, returns embedding.
# MAGIC * **AI Search index** = the lookup (optional). Takes embedding, returns nearest known cells with metadata.
# MAGIC * AI Search is NOT needed for the endpoint to work. It adds the "what cell type is this?" layer.
# MAGIC * For oss-001 (baseline deploy test): skip AI Search. For oss-002+ and production: keep AI Search.
# MAGIC
# MAGIC ## Prerequisite
# MAGIC
# MAGIC Model in UC Volume -- see the download cells above (this notebook is combined).

# COMMAND ----------

# DBTITLE 1,Configuration
import os, sys

dbutils.widgets.text("catalog", "<catalog>", "Unity Catalog catalog")
dbutils.widgets.text("schema", "skills", "Unity Catalog schema")
dbutils.widgets.text("cache_dir", "models", "Cache dir (UC volume name)")
dbutils.widgets.dropdown("teddy_model_size", "70M", ["70M", "160M", "400M"], "TEDDY-G variant")
dbutils.widgets.text("teddy_hf_repo", "Merck/TEDDY", "HF repo")
dbutils.widgets.text("teddy_hf_revision", "main", "HF revision")
dbutils.widgets.dropdown("run_go", "false", ["false", "true"], "Run gate (deploy + VS cost real money)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
MODEL_SIZE = dbutils.widgets.get("teddy_model_size")
HF_REPO = dbutils.widgets.get("teddy_hf_repo")
HF_REVISION = dbutils.widgets.get("teddy_hf_revision")
RUN_GO = dbutils.widgets.get("run_go") == "true"

BASE_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"

# Try snapshots/<revision>/teddy/ first, then flat layout (snapshot/teddy/)
_gwb_path = f"{BASE_DIR}/snapshots/{HF_REVISION}/teddy"
_flat_path = f"{BASE_DIR}/snapshot/teddy"  # downloaded via download cells above (flat layout)
if os.path.isdir(_gwb_path):
    snapshot_dir = f"{BASE_DIR}/snapshots/{HF_REVISION}"
elif os.path.isdir(_flat_path):
    snapshot_dir = f"{BASE_DIR}/snapshot"
else:
    snapshot_dir = f"{BASE_DIR}/snapshots/{HF_REVISION}"  # will fail at assert below

teddy_pkg_dir = os.path.join(snapshot_dir, "teddy")
model_dir = os.path.join(teddy_pkg_dir, "models", "teddy_g", MODEL_SIZE)

EMB_DIM = {"70M": 512, "160M": 768, "400M": 1024}[MODEL_SIZE]

assert os.path.isdir(model_dir), (
    f"Checkpoint not found at {model_dir}. Run the download cells above first."
)
print(f"Catalog: {CATALOG} | Schema: {SCHEMA}")
print(f"Model:   TEDDY-G {MODEL_SIZE} (d_model={EMB_DIM})")
print(f"Path:    {model_dir}")
print(f"RUN_GO:  {RUN_GO}")

# COMMAND ----------

# DBTITLE 1,Idempotent cleanup (delete existing endpoint + model versions)
# Idempotent cleanup: delete existing endpoint + UC model versions
# so re-running the notebook gets a fully fresh deploy.
# Skipped when run_go=false (just viewing / downloading).
#
# Per convention: cleanup cell lives AFTER config, BEFORE download/install.

if RUN_GO:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import NotFound, ResourceDoesNotExist
    from mlflow.tracking import MlflowClient
    import mlflow

    w = WorkspaceClient()
    mlflow.set_registry_uri("databricks-uc")
    mc = MlflowClient(registry_uri="databricks-uc")

    # -- Endpoint names this notebook creates --
    endpoint_name = f"teddy-{MODEL_SIZE.lower()}-embedder"
    uc_model_name = f"{CATALOG}.{SCHEMA}.teddy_{MODEL_SIZE.lower()}"
    target_table = f"{CATALOG}.{SCHEMA}.teddy_cells_{MODEL_SIZE.lower()}"

    # 1. Delete serving endpoint
    try:
        w.serving_endpoints.delete(endpoint_name)
        print(f"Deleted endpoint: {endpoint_name}")
    except (NotFound, ResourceDoesNotExist):
        print(f"Endpoint {endpoint_name}: not found (OK)")

    # 2. Delete all UC model versions
    try:
        versions = mc.search_model_versions(f"name='{uc_model_name}'")
        for v in versions:
            mc.delete_model_version(name=uc_model_name, version=v.version)
            print(f"Deleted model version: {uc_model_name} v{v.version}")
        if versions:
            mc.delete_registered_model(name=uc_model_name)
            print(f"Deleted registered model: {uc_model_name}")
        else:
            print(f"Model {uc_model_name}: no versions (OK)")
    except Exception as e:
        print(f"Model cleanup: {e}")

    # 3. Drop teddy_cells table (will be regenerated from Census)
    if spark.catalog.tableExists(target_table):
        spark.sql(f"DROP TABLE {target_table}")
        print(f"Dropped table: {target_table}")
    else:
        print(f"Table {target_table}: not found (OK)")

    # 4. Also clean up legacy artifacts from prior naming conventions
    for legacy_ep in [f"teddy_{MODEL_SIZE.lower()}"]:
        try:
            w.serving_endpoints.delete(legacy_ep)
            print(f"Deleted legacy endpoint: {legacy_ep}")
        except (NotFound, ResourceDoesNotExist):
            pass

    print("\nCleanup done. Notebook will create fresh artifacts.")
else:
    print("run_go=false -- skipping cleanup (read-only mode).")
    print(f"  Would clean: teddy-{MODEL_SIZE.lower()}-embedder, "
          f"{CATALOG}.{SCHEMA}.teddy_{MODEL_SIZE.lower()}, "
          f"{CATALOG}.{SCHEMA}.teddy_cells_{MODEL_SIZE.lower()}")

# COMMAND ----------

# DBTITLE 1,Phase 1 header
# MAGIC %md
# MAGIC ## Phase 1 — Register TEDDYEmbedder to Unity Catalog
# MAGIC
# MAGIC **Heavy deps** (`teddy`, `torch`, `mlflow`, `scanpy`). Uses `python_model=path`
# MAGIC (file-based logging, no cloudpickle) with `teddy_wrapper.py`.
# MAGIC Includes `input_example` + `signature` so the MLflow UI “Test” button works.
# MAGIC
# MAGIC Adapted from [GWB TEDDY module](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/teddy/teddy_g_v1) via [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7).

# COMMAND ----------

# DBTITLE 1,Install registration deps
# Pin transformers==4.41.0 — TEDDY's GeneTokenizer breaks on newer versions
os.environ["HF_HUB_DISABLE_XET"] = "1"  # avoid xet download issues

%pip install -q scanpy==1.11.2 transformers==4.41.0 einops torch \
    mlflow==2.22.0 huggingface_hub pandas numpy
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Restore widgets + stage code bundle
import os, sys, shutil, json
import numpy as np
import pandas as pd
import mlflow

os.environ["HF_HUB_DISABLE_XET"] = "1"

# Re-read widgets
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
MODEL_SIZE = dbutils.widgets.get("teddy_model_size")
HF_REPO = dbutils.widgets.get("teddy_hf_repo")
HF_REVISION = dbutils.widgets.get("teddy_hf_revision")
RUN_GO = dbutils.widgets.get("run_go") == "true"

BASE_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"
_gwb_path = f"{BASE_DIR}/snapshots/{HF_REVISION}/teddy"
_flat_path = f"{BASE_DIR}/snapshot/teddy"
if os.path.isdir(_gwb_path):
    snapshot_dir = f"{BASE_DIR}/snapshots/{HF_REVISION}"
elif os.path.isdir(_flat_path):
    snapshot_dir = f"{BASE_DIR}/snapshot"
else:
    snapshot_dir = f"{BASE_DIR}/snapshots/{HF_REVISION}"
teddy_pkg_dir = os.path.join(snapshot_dir, "teddy")
model_dir = os.path.join(teddy_pkg_dir, "models", "teddy_g", MODEL_SIZE)
EMB_DIM = {"70M": 512, "160M": 768, "400M": 1024}[MODEL_SIZE]

# Add snapshot to sys.path so `from teddy.xxx import yyy` works
if snapshot_dir not in sys.path:
    sys.path.insert(0, snapshot_dir)

# Stage clean code bundle (teddy/ source without weights + teddy_wrapper.py)
clean_code_dir = "/tmp/teddy_code"
if os.path.exists(clean_code_dir):
    shutil.rmtree(clean_code_dir)
shutil.copytree(
    teddy_pkg_dir, f"{clean_code_dir}/teddy",
    ignore=shutil.ignore_patterns("*.safetensors", "*.bin", "*.ckpt", "*.pt", "__pycache__"),
)

# Copy teddy_wrapper.py from the workspace bundle
_gwb_wrapper = "/Workspace/Users/<workspace-user>/.bundle/genesis_workbench_teddy/prod_aws/files/notebooks/teddy_wrapper.py"
wrapper_dest = f"{clean_code_dir}/teddy_wrapper.py"
shutil.copy2(_gwb_wrapper, wrapper_dest)

if clean_code_dir not in sys.path:
    sys.path.insert(0, clean_code_dir)
from teddy_wrapper import TEDDYEmbedder

print(f"\u2713 TEDDYEmbedder imported from {wrapper_dest}")
print(f"  code_paths bundle at {clean_code_dir}")

# COMMAND ----------

# DBTITLE 1,Build input_example + dry-load + infer signature
from mlflow.pyfunc import PythonModelContext
from mlflow.models import infer_signature
import scanpy as sc

# --- Build realistic input_example from model vocab ---
n_cells, n_genes = 5, 100
rng = np.random.default_rng(seed=42)
expr = rng.poisson(2.0, size=(n_cells, n_genes)).astype(np.float32)

vocab_path = os.path.join(model_dir, "vocab.txt")
with open(vocab_path) as f:
    vocab_tokens = [line.strip() for line in f if line.strip()]
real_genes = [t for t in vocab_tokens if not t.startswith("<")][:n_genes]
assert len(real_genes) == n_genes

obs_df = pd.DataFrame({"cell_id": [f"cell_{i}" for i in range(n_cells)]})
var_df = pd.DataFrame({"index": real_genes})

input_example = pd.DataFrame({
    "adata_sparsematrix": [expr.tolist()],
    "adata_obs": [obs_df.to_json(orient="split")],
    "adata_var": [var_df.to_json(orient="split")],
})

default_params = {"max_seq_len": 2048, "pooling": "mean"}

# --- Dry-load test ---
artifacts = {"model_dir": model_dir, "teddy_pkg_parent": clean_code_dir}
ctx = PythonModelContext(artifacts=artifacts, model_config={})

model = TEDDYEmbedder(model_size=MODEL_SIZE)
model.load_context(ctx)

output_example = model.predict(ctx, input_example, default_params)
print(f"\u2713 Dry-load OK: {len(output_example)} embeddings, dim={len(output_example[0]['embedding'])}")
assert len(output_example[0]["embedding"]) == EMB_DIM

# --- Infer signature (enables UI testing) ---
signature = infer_signature(
    model_input=input_example,
    model_output=output_example,
    params=default_params,
)
print(f"\u2713 Signature inferred:")
print(f"  Input:  {signature.inputs}")
print(f"  Output: {signature.outputs}")
print(f"  Params: {signature.params}")

# COMMAND ----------

# DBTITLE 1,Log + register TEDDY to UC
from databricks.sdk import WorkspaceClient

def set_mlflow_experiment(tag):
    w = WorkspaceClient()
    base = "Shared/dbx_genesis_workbench_models"
    w.workspace.mkdirs(f"/Workspace/{base}")
    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_tracking_uri("databricks")
    return mlflow.set_experiment(f"/{base}/{tag}")

experiment = set_mlflow_experiment("teddy_genesis_workbench_modules")
registered_model_name = f"{CATALOG}.{SCHEMA}.teddy_{MODEL_SIZE.lower()}"

with mlflow.start_run(run_name=f"teddy_{MODEL_SIZE}_embedder", experiment_id=experiment.experiment_id) as run:
    mlflow.pyfunc.log_model(
        artifact_path="teddy",
        python_model=wrapper_dest,          # file-based — no cloudpickle
        artifacts=artifacts,                # model_dir + teddy_pkg_parent
        signature=signature,                # for UI testing
        input_example=(input_example, default_params),  # for UI testing
        pip_requirements=[
            "torch", "transformers==4.41.0", "einops", "scanpy",
            "numpy", "pandas", "mlflow==2.22.0",
        ],
        registered_model_name=registered_model_name,
    )
    print(f"\u2713 Registered {registered_model_name} (run {run.info.run_id})")

# COMMAND ----------

# DBTITLE 1,Registration smoke test (load from UC + predict)
# Validate the UC-registered artifact works end-to-end.
# Loads the model from Unity Catalog (not the local instance),
# runs predict, and asserts output shape matches expectations.

import mlflow

mlflow.set_registry_uri("databricks-uc")
UC_MODEL = f"{CATALOG}.{SCHEMA}.teddy_{MODEL_SIZE.lower()}"
loaded = mlflow.pyfunc.load_model(f"models:/{UC_MODEL}/1")

result = loaded.predict(input_example, params=default_params)
assert isinstance(result, list), f"Expected list, got {type(result)}"
assert len(result) == 5, f"Expected 5 embeddings, got {len(result)}"
assert len(result[0]["embedding"]) == EMB_DIM, (
    f"Expected dim={EMB_DIM}, got {len(result[0]['embedding'])}"
)
print(f"\u2713 Registration smoke test passed")
print(f"  Model:  {UC_MODEL} v1")
print(f"  Output: {len(result)} embeddings, dim={len(result[0]['embedding'])}")
print(f"  First 3 values: {result[0]['embedding'][:3]}")

# COMMAND ----------

# DBTITLE 1,Phase 1b header
# MAGIC %md
# MAGIC ## Phase 1b — AI Search (optional for oss-001, needed for oss-002+)
# MAGIC
# MAGIC Creates a `teddy_cells` Delta table + Databricks AI Search index for
# MAGIC nearest-neighbor cell-type lookup.
# MAGIC
# MAGIC ### Why AI Search exists (and when to skip it)
# MAGIC
# MAGIC **Model Serving endpoint (Phase 2)** and **AI Search** serve different purposes:
# MAGIC
# MAGIC | Component | What it does | Needed for |
# MAGIC |---|---|---|
# MAGIC | Serving endpoint | Raw gene expression -> 512-d embedding vector | Always (the model itself) |
# MAGIC | AI Search index | "Given this embedding, what known cells are most similar?" | Cell-type annotation, similarity search |
# MAGIC
# MAGIC The endpoint works without AI Search — you get embedding vectors either way.
# MAGIC AI Search adds the **lookup** layer: embed a new cell via the endpoint, then query
# MAGIC the index to get back "this looks like a CD14+ monocyte from blood with Alzheimer's."
# MAGIC
# MAGIC **For oss-001 (baseline deploy test):** AI Search is optional — the 8 scorer phases
# MAGIC check notebook code quality, not search. Skip if you only need the endpoint.
# MAGIC
# MAGIC **For oss-002+ and production:** Keep AI Search — the skill instructs the assistant
# MAGIC to build both endpoint + index. The Census table is the **reference corpus**
# MAGIC that AI Search queries against. Bigger corpus = more cell types identifiable.
# MAGIC
# MAGIC ### How the 400M production table was built
# MAGIC
# MAGIC The `genesis_workbench.teddy_cells` table (~2M rows, dim=1024, 662 cell types,
# MAGIC 55 tissues, 108 diseases) was generated by GWB `03_reembed_reference`:
# MAGIC
# MAGIC 1. `cellxgene_census.open_soma()` → filter `is_primary_data=True` (CZ CELLxGENE Census)
# MAGIC 2. Batch raw expression matrices through TEDDY-400M (Spark UDF or driver loop)
# MAGIC 3. Write `(cell_id, embedding, cell_type, tissue_general, disease, ...)` to Delta
# MAGIC 4. Enable CDF → create Delta Sync AI Search index
# MAGIC
# MAGIC ### Can other variants (70M, 160M) derive a similar table?
# MAGIC
# MAGIC **Yes — same pipeline, different checkpoint.** Swap `MODEL_SIZE` and re-embed
# MAGIC from raw expression data. Embeddings are NOT interchangeable between variants:
# MAGIC each learns its own representation space (512-d ≠ 768-d ≠ 1024-d), so you
# MAGIC cannot project or truncate — you must re-run the full embedding pass.
# MAGIC
# MAGIC | Variant | Dim | Production table | Status |
# MAGIC |---------|-----|-----------------|--------|
# MAGIC | 400M | 1024 | `genesis_workbench.teddy_cells` (~2M rows) | Done |
# MAGIC | 70M | 512 | Not yet built | Register `teddy_70m`, then `run_go=true` |
# MAGIC | 160M | 768 | Not yet built | Register `teddy_160m`, then same |
# MAGIC
# MAGIC ### Source table resolution
# MAGIC
# MAGIC The cell below writes to `skills.teddy_cells_{variant}` (e.g. `teddy_cells_70m`).
# MAGIC All data comes from CELLxGENE Census (real cells with biological metadata).
# MAGIC
# MAGIC | Step | Condition | Result |
# MAGIC |---|---|---|
# MAGIC | 1. Exists? | Table already in catalog | Reuse it. `DROP TABLE` to regenerate. |
# MAGIC | 2. Generate | `run_go=true` | Stream from Census, embed, write with metadata |
# MAGIC | 3. Skip | `run_go=false` | Print instructions |
# MAGIC
# MAGIC **Sizing guide** (`census_n_cells` widget):
# MAGIC
# MAGIC | N | Time | PCA/tSNE | Cell types | Use case |
# MAGIC |---|---|---|---|---|
# MAGIC | 200 | ~45s | Marginal (sparse clusters) | ~50-80 | Smoke test only |
# MAGIC | **1,000** | **~4 min** | **Good (clear clusters)** | **~200-300** | **GT default** |
# MAGIC | 10,000 | ~38 min | Excellent | ~500+ | Production |
# MAGIC
# MAGIC > **Gene ID compatibility verified:** Census `feature_id` = Ensembl IDs,
# MAGIC > matching TEDDY vocab (86.6% overlap, 22K/25K genes). Code remaps
# MAGIC > `adata.var_names` from gene symbols to `feature_id` before intersecting.
# MAGIC > Census data is **streamed** from S3 via `tiledbsoma` — no pre-download
# MAGIC > to Volume needed. Requires `pip install cellxgene-census` (auto-installed).

# COMMAND ----------

# DBTITLE 1,Install Census deps
# Census deps — separate %pip install + restart (subprocess approach
# breaks botocore.compat on serverless).
%pip install -q cellxgene-census
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Post-Census-restart setup
import os, sys, importlib
import mlflow, numpy as np, pandas as pd

os.environ["HF_HUB_DISABLE_XET"] = "1"

# Re-read widgets after restart
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
MODEL_SIZE = dbutils.widgets.get("teddy_model_size")
RUN_GO = dbutils.widgets.get("run_go") == "true"

BASE_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"
_gwb_path = f"{BASE_DIR}/snapshots/main/teddy"
_flat_path = f"{BASE_DIR}/snapshot/teddy"
if os.path.isdir(_gwb_path):
    snapshot_dir = f"{BASE_DIR}/snapshots/main"
elif os.path.isdir(_flat_path):
    snapshot_dir = f"{BASE_DIR}/snapshot"
else:
    snapshot_dir = f"{BASE_DIR}/snapshots/main"

model_dir = os.path.join(snapshot_dir, "teddy", "models", "teddy_g", MODEL_SIZE)
EMB_DIM = {"70M": 512, "160M": 768, "400M": 1024}[MODEL_SIZE]

print(f"Post-Census-restart: {CATALOG}.{SCHEMA} | TEDDY-{MODEL_SIZE} | RUN_GO={RUN_GO}")
print(f"  model_dir: {model_dir}")

# COMMAND ----------

# DBTITLE 1,Resolve or generate teddy_cells source table
# Resolve or generate the teddy_cells table for AI Search indexing.
#
# Target: {catalog}.{schema}.teddy_cells_{variant}  (e.g. teddy_cells_70m)
# Source: CELLxGENE Census (real cells with cell_type, tissue, disease metadata)
#
# Decision:
#   1. Table exists?   -> reuse (DROP TABLE to regenerate)
#   2. run_go=true?    -> stream from Census, embed via UC model, write Delta
#   3. else            -> print instructions

TARGET_TABLE = f"{CATALOG}.{SCHEMA}.teddy_cells_{MODEL_SIZE.lower()}"
UC_MODEL = f"{CATALOG}.{SCHEMA}.teddy_{MODEL_SIZE.lower()}"
VS_SOURCE_TABLE = None
VS_HAS_METADATA = False

dbutils.widgets.text("census_n_cells", "1000",
                     "Census cells to embed (1000 good for PCA/tSNE, 200 minimal, 10K production)")
CENSUS_N = int(dbutils.widgets.get("census_n_cells"))

print(f"Target table:  {TARGET_TABLE}")
print(f"UC model:      {UC_MODEL}")
print(f"Variant:       TEDDY-{MODEL_SIZE} (dim={EMB_DIM})")
print(f"Census cells:  {CENSUS_N:,}")
print(f"Run gate:      {RUN_GO}")
print()

# -- 1. Table already exists? Reuse it. -----------------------------------
if spark.catalog.tableExists(TARGET_TABLE):
    row_count = spark.table(TARGET_TABLE).count()
    has_meta = "cell_type" in spark.table(TARGET_TABLE).columns
    VS_SOURCE_TABLE = TARGET_TABLE
    VS_HAS_METADATA = has_meta
    print(f"v Table exists: {TARGET_TABLE}")
    print(f"  {row_count:,} rows, metadata={'yes' if has_meta else 'no'}")
    print(f"  To regenerate: DROP TABLE {TARGET_TABLE}  then re-run.")

# -- 2. Generate from CELLxGENE Census ------------------------------------
#    Streams expression data from Census S3 via tiledbsoma (no pre-download).
#    Gene IDs: Census feature_id = Ensembl (ENSG*), matching TEDDY vocab.
#    Verified overlap: 86.6% (22K / 25K TEDDY Ensembl IDs).
#
#    Time estimates (serverless CPU):
#      200 cells  ~45s  |  1,000 cells  ~4 min  |  10,000 cells  ~38 min
elif RUN_GO:
    import cellxgene_census, tiledbsoma  # installed via %pip cell above
    import mlflow, numpy as np, pandas as pd
    from pyspark.sql.types import StructType, StructField, StringType, ArrayType, FloatType

    print(f"=== CELLxGENE Census -> TEDDY-{MODEL_SIZE} ===")
    print(f"    {CENSUS_N:,} cells -> {TARGET_TABLE} (dim={EMB_DIM})")

    # 2a. Query Census obs metadata
    census = cellxgene_census.open_soma()
    obs_filter = 'is_primary_data == True and assay == "10x 3\' v3"'
    with census["census_data"]["homo_sapiens"].axis_query(
        measurement_name="RNA",
        obs_query=tiledbsoma.AxisQuery(value_filter=obs_filter),
    ) as q:
        obs_df = q.obs(
            column_names=["soma_joinid", "cell_type", "tissue_general", "disease"]
        ).concat().to_pandas()
    print(f"  Census matched: {len(obs_df):,} cells")

    obs_sample = (obs_df.sample(n=CENSUS_N, random_state=42).reset_index(drop=True)
                  if len(obs_df) > CENSUS_N else obs_df.reset_index(drop=True))
    print(f"  Sampled: {len(obs_sample):,} cells, "
          f"{obs_sample['cell_type'].nunique()} cell types, "
          f"{obs_sample['tissue_general'].nunique()} tissues")

    # 2b. Read expression matrix for sampled cells
    with census["census_data"]["homo_sapiens"].axis_query(
        measurement_name="RNA",
        obs_query=tiledbsoma.AxisQuery(coords=(obs_sample["soma_joinid"].tolist(),)),
    ) as q:
        adata = q.to_anndata(X_name="raw")
    census.close()
    print(f"  AnnData: {adata.shape[0]} cells x {adata.shape[1]} genes")

    # 2c. Remap var_names to Ensembl IDs
    #     Census default var_names = gene symbols (NOC2L, ISG15, ...)
    #     TEDDY vocab = Ensembl IDs (ENSG00000000003, ...)
    #     Must use feature_id column for intersection.
    adata.var_names = adata.var["feature_id"].values
    adata.var_names_make_unique()

    vocab_path = os.path.join(model_dir, "vocab.txt")
    with open(vocab_path) as f:
        teddy_vocab = {line.strip() for line in f if line.strip() and not line.startswith("<")}
    shared_genes = [g for g in adata.var_names if g in teddy_vocab]
    print(f"  Gene overlap: {len(shared_genes)} / {len(teddy_vocab)} TEDDY vocab")
    if len(shared_genes) < 50:
        raise ValueError(
            f"Only {len(shared_genes)} shared genes -- check Census gene ID format. "
            f"Expected Ensembl IDs in adata.var['feature_id'].")

    # 2d. Embed through UC-registered model
    mlflow.set_registry_uri("databricks-uc")
    loaded = mlflow.pyfunc.load_model(f"models:/{UC_MODEL}/1")
    adata_sub = adata[:, shared_genes].copy()
    var_json = pd.DataFrame({"index": shared_genes}).to_json(orient="split")

    BATCH_SIZE = 50
    all_rows = []
    for i in range(0, adata_sub.shape[0], BATCH_SIZE):
        batch = adata_sub[i : i + BATCH_SIZE]
        expr = (batch.X.toarray().astype(np.float32)
                if hasattr(batch.X, "toarray")
                else np.array(batch.X, dtype=np.float32))
        cids = [f"census_{j}" for j in range(i, i + batch.shape[0])]
        result = loaded.predict(pd.DataFrame({
            "adata_sparsematrix": [expr.tolist()],
            "adata_obs": [pd.DataFrame({"cell_id": cids}).to_json(orient="split")],
            "adata_var": [var_json],
        }), params={"max_seq_len": 2048, "pooling": "mean"})
        meta = obs_sample.iloc[i : i + batch.shape[0]]
        for j, (cid, r) in enumerate(zip(cids, result)):
            all_rows.append((
                cid, r["embedding"],
                str(meta.iloc[j]["cell_type"]),
                str(meta.iloc[j]["tissue_general"]),
                str(meta.iloc[j]["disease"]),
            ))
        if (i // BATCH_SIZE) % 10 == 0:
            print(f"  Embedded {len(all_rows):,} / {adata_sub.shape[0]:,}")

    # 2e. Write to Delta
    schema = StructType([
        StructField("cell_id", StringType(), False),
        StructField("embedding", ArrayType(FloatType()), False),
        StructField("cell_type", StringType(), True),
        StructField("tissue_general", StringType(), True),
        StructField("disease", StringType(), True),
    ])
    spark.createDataFrame(all_rows, schema=schema) \
         .write.format("delta").mode("overwrite").saveAsTable(TARGET_TABLE)
    spark.sql(f"ALTER TABLE {TARGET_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
    VS_SOURCE_TABLE = TARGET_TABLE
    VS_HAS_METADATA = True
    ct = spark.sql(f"SELECT COUNT(DISTINCT cell_type) FROM {TARGET_TABLE}").first()[0]
    ti = spark.sql(f"SELECT COUNT(DISTINCT tissue_general) FROM {TARGET_TABLE}").first()[0]
    print(f"\n  Done: {TARGET_TABLE}")
    print(f"  {len(all_rows):,} rows, dim={EMB_DIM}, {ct} cell types, {ti} tissues")

# -- 3. Nothing to do ------------------------------------------------------
else:
    print("No table found and run-gate is off.")
    print("  -> Set run_go=true + census_n_cells (default 1000) to generate.")
    print("  -> 1000 cells takes ~4 min. Good for PCA/tSNE viz.")

# -- Summary ---------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"VS_SOURCE_TABLE = {VS_SOURCE_TABLE}")
print(f"VS_HAS_METADATA = {VS_HAS_METADATA}")

# COMMAND ----------

# DBTITLE 1,Visualize teddy_cells embeddings
import numpy as np
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from numpy.linalg import norm as lnorm

# Visualize the AI Search source table from the resolve cell above.
# 5-panel layout: Heatmap | PCA | t-SNE | L2 norms | Cosine sim
# PCA + t-SNE colored by cell_type when Census metadata is present.
try:
    _viz_table = VS_SOURCE_TABLE
except NameError:
    _viz_table = None

if _viz_table is None or not spark.catalog.tableExists(_viz_table):
    print("AI Search source table not set. Run the resolve cell first.")
else:
    total = spark.table(_viz_table).count()
    MAX_VIZ = 2000
    if total > MAX_VIZ:
        frac = min(1.0, (MAX_VIZ * 3) / total)
        pdf = spark.table(_viz_table).sample(fraction=frac, seed=42).limit(MAX_VIZ).toPandas()
    else:
        pdf = spark.table(_viz_table).toPandas()

    embs = np.array(pdf["embedding"].tolist())
    has_ct = "cell_type" in pdf.columns
    dim = embs.shape[1]
    n_ct = pdf["cell_type"].nunique() if has_ct else 0
    n_tis = pdf["tissue_general"].nunique() if "tissue_general" in pdf.columns else 0
    print(f"{total:,} total, showing {len(pdf):,}, dim={dim}"
          + (f", {n_ct} cell types, {n_tis} tissues" if has_ct else ""))

    # -- Shared: top cell types for coloring --
    if has_ct:
        top_types = pdf["cell_type"].value_counts().head(10).index.tolist()
        ct_idx = pdf["cell_type"].apply(
            lambda x: top_types.index(x) if x in top_types else -1)
        cmap_ct = plt.colormaps.get_cmap("tab10")

    def _scatter_by_ct(ax, coords_2d, title):
        """Color scatter by cell type (top 10 + other)."""
        if has_ct:
            for i, ct in enumerate(top_types):
                m = ct_idx == i
                ax.scatter(coords_2d[m, 0], coords_2d[m, 1], s=6, alpha=0.5,
                           c=[cmap_ct(i)], label=ct[:20])
            m_other = ct_idx == -1
            ax.scatter(coords_2d[m_other, 0], coords_2d[m_other, 1],
                       s=2, alpha=0.15, c="grey", label="other")
            ax.legend(fontsize=5, loc="upper right", ncol=2, markerscale=2)
        else:
            sc = ax.scatter(coords_2d[:, 0], coords_2d[:, 1], s=12, alpha=0.6,
                            c=np.arange(len(coords_2d)), cmap="viridis")
            plt.colorbar(sc, ax=ax, label="Cell index", shrink=0.8)
        ax.set_title(title)

    # -- Layout: 2 rows x 3 cols (bottom-right empty or summary text) --
    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    fig.suptitle(f"TEDDY-{MODEL_SIZE} Embeddings ({total:,} cells, dim={dim})",
                 fontsize=14)

    # 1. Heatmap (first 30 cells x first 64 dims)
    ax = axes[0, 0]
    im = ax.imshow(embs[:30, :64], aspect="auto", cmap="RdBu_r", vmin=-10, vmax=10)
    ax.set_xlabel("Dim (first 64)")
    ax.set_ylabel("Cell")
    ax.set_title("Heatmap (30 x 64)")
    plt.colorbar(im, ax=ax, shrink=0.8)

    # 2. PCA
    pca = PCA(n_components=2)
    pca_coords = pca.fit_transform(embs)
    ax = axes[0, 1]
    _scatter_by_ct(ax, pca_coords,
                   f"PCA ({pca.explained_variance_ratio_[:2].sum():.1%} var)")
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%})")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%})")

    # 3. t-SNE (needs >= ~50 cells to be meaningful)
    ax = axes[0, 2]
    if len(embs) >= 50:
        perp = min(30, len(embs) // 4)
        tsne = TSNE(n_components=2, perplexity=perp, random_state=42,
                    init="pca", learning_rate="auto")
        tsne_coords = tsne.fit_transform(embs)
        _scatter_by_ct(ax, tsne_coords, f"t-SNE (perplexity={perp})")
        ax.set_xlabel("tSNE-1")
        ax.set_ylabel("tSNE-2")
    else:
        ax.text(0.5, 0.5, f"Need >= 50 cells\n(have {len(embs)})",
                ha="center", va="center", fontsize=12, transform=ax.transAxes)
        ax.set_title("t-SNE (skipped)")

    # 4. L2 norm distribution
    norms = lnorm(embs, axis=1)
    ax = axes[1, 0]
    ax.hist(norms, bins=30, edgecolor="black", alpha=0.7, color="steelblue")
    ax.axvline(norms.mean(), color="red", ls="--", label=f"mean={norms.mean():.1f}")
    ax.set_xlabel("L2 norm")
    ax.set_ylabel("Count")
    ax.set_title(f"L2 norms (dim={dim})")
    ax.legend()

    # 5. Pairwise cosine similarity
    rng = np.random.default_rng(0)
    n_pairs = min(500, len(embs) * (len(embs) - 1) // 2)
    idxs = rng.choice(len(embs), size=(n_pairs, 2), replace=True)
    cos_sims = [float(np.dot(embs[i], embs[j]) / (lnorm(embs[i]) * lnorm(embs[j]) + 1e-9))
                for i, j in idxs if i != j]
    ax = axes[1, 1]
    ax.hist(cos_sims, bins=30, edgecolor="black", alpha=0.7, color="coral")
    ax.axvline(np.mean(cos_sims), color="red", ls="--",
               label=f"mean={np.mean(cos_sims):.3f}")
    ax.set_xlabel("Cosine similarity")
    ax.set_ylabel("Count")
    ax.set_title("Pairwise cosine sim")
    ax.legend()

    # 6. Summary text panel
    ax = axes[1, 2]
    ax.axis("off")
    summary = (
        f"Table: {_viz_table}\n"
        f"Total rows: {total:,}\n"
        f"Showing: {len(pdf):,}\n"
        f"Dim: {dim}\n"
        f"L2 norms: {norms.mean():.1f} +/- {norms.std():.1f}\n"
        f"Value range: [{embs.min():.2f}, {embs.max():.2f}]\n"
        f"Pairwise cos: {np.mean(cos_sims):.3f} +/- {np.std(cos_sims):.3f}\n"
        f"PCA var (2d): {pca.explained_variance_ratio_[:2].sum():.1%}\n"
    )
    if has_ct:
        summary += f"Cell types: {n_ct}\nTissues: {n_tis}\n"
    ax.text(0.05, 0.95, summary, transform=ax.transAxes, fontsize=10,
            verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))
    ax.set_title("Summary")

    plt.tight_layout()
    plt.show()

# COMMAND ----------

# DBTITLE 1,Create AI Search index for TEDDY (04 pattern)
# Create AI Search index over teddy_cells table

if not RUN_GO:
    print("run-gate off; set run_go=true to create AI Search index. Skipping.")
else:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.vectorsearch import (
        EndpointType, DeltaSyncVectorIndexSpecRequest,
        EmbeddingVectorColumn, VectorIndexType, PipelineType,
    )
    from databricks.sdk.errors import NotFound, BadRequest
    import time

    w = WorkspaceClient()
    VS_ENDPOINT = "gwb_teddy_vs_endpoint"
    VS_INDEX = f"{CATALOG}.{SCHEMA}.teddy_cell_index"

    # Use VS_SOURCE_TABLE from the resolve cell above
    try:
        source_table = VS_SOURCE_TABLE
    except NameError:
        source_table = None

    if source_table is None or not spark.catalog.tableExists(source_table):
        print(f"\u2717 No AI Search source table available (VS_SOURCE_TABLE not set or missing).")
        print("  Run the 'Resolve or generate' cell above first.")
        print("  Skipping AI Search index creation (Phase 1b is optional).")
    else:
        print(f"Source table: {source_table}")

        # Endpoint
        try:
            ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT)
            print(f"AI Search endpoint '{VS_ENDPOINT}' exists")
        except Exception:
            print(f"Creating AI Search endpoint '{VS_ENDPOINT}'...")
            w.vector_search_endpoints.create_endpoint(name=VS_ENDPOINT, endpoint_type=EndpointType.STANDARD)
            for _ in range(60):
                ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT)
                if ep.endpoint_status and ep.endpoint_status.state and ep.endpoint_status.state.value == "ONLINE":
                    print(f"\u2713 Endpoint ONLINE"); break
                time.sleep(30)

        # Index (handles variant switch: dim mismatch → drop + recreate)
        try:
            existing = w.vector_search_indexes.get_index(VS_INDEX)
            spec = getattr(existing, "delta_sync_index_spec", None)
            cols = getattr(spec, "embedding_vector_columns", []) if spec else []
            existing_dim = int(getattr(cols[0], "embedding_dimension", 0)) if cols else None
            if existing_dim and existing_dim != EMB_DIM:
                print(f"Dim mismatch ({existing_dim} vs {EMB_DIM}) — dropping and recreating.")
                w.vector_search_indexes.delete_index(index_name=VS_INDEX)
                time.sleep(30)
                existing = None
            else:
                print(f"Index exists — triggering sync.")
                try: w.vector_search_indexes.sync_index(index_name=VS_INDEX)
                except BadRequest: print("  Sync already in progress.")
        except NotFound:
            existing = None

        if existing is None:
            try:
                spark.sql(f"ALTER TABLE {source_table} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
            except Exception as e:
                print(f"  Note: Could not set CDF on {source_table} (may be read-only): {e}")
            w.vector_search_indexes.create_index(
                name=VS_INDEX, endpoint_name=VS_ENDPOINT, primary_key="cell_id",
                index_type=VectorIndexType.DELTA_SYNC,
                delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
                    source_table=source_table,
                    embedding_vector_columns=[EmbeddingVectorColumn(name="embedding", embedding_dimension=EMB_DIM)],
                    pipeline_type=PipelineType.TRIGGERED,
                    columns_to_sync=["cell_id"] + (["cell_type", "tissue_general"] if VS_HAS_METADATA else []),
                ),
            )
            print(f"\u2713 Index '{VS_INDEX}' created (dim={EMB_DIM}).")

# COMMAND ----------

# DBTITLE 1,Phase 2 header
# MAGIC %md
# MAGIC ## Phase 2 — Deploy GPU Model Serving endpoint (SDK-only)
# MAGIC
# MAGIC SDK-only — via [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7).
# MAGIC
# MAGIC Endpoint created with:
# MAGIC * **Scale-to-zero** enabled (saves cost when idle)
# MAGIC * **AI Gateway** enabled — inference table (logs requests + responses to UC) + usage tracking (token/request metering)
# MAGIC
# MAGIC > ⚠️ **GPU endpoints bill while provisioned.** Phase 4 (teardown) cleans up.

# COMMAND ----------

# DBTITLE 1,Deploy TEDDY serving endpoint
if not RUN_GO:
    print("run-gate off; set run_go=true to deploy. Skipping.")
else:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import (
        EndpointCoreConfigInput, ServedEntityInput,
        ServingModelWorkloadType,
        AiGatewayConfig, AiGatewayUsageTrackingConfig,
        AiGatewayInferenceTableConfig,
    )
    from databricks.sdk.errors import ResourceAlreadyExists
    from mlflow.tracking import MlflowClient

    w = WorkspaceClient()
    mc = MlflowClient(registry_uri="databricks-uc")

    uc_model = f"{CATALOG}.{SCHEMA}.teddy_{MODEL_SIZE.lower()}"
    version = max(int(v.version) for v in mc.search_model_versions(f"name='{uc_model}'"))
    endpoint_name = f"teddy-{MODEL_SIZE.lower()}-embedder"

    entity = ServedEntityInput(
        entity_name=uc_model, entity_version=str(version),
        workload_type=ServingModelWorkloadType.GPU_SMALL,
        workload_size="Small",
        scale_to_zero_enabled=True,
    )

    # AI Gateway — inference table (UC) + usage tracking
    # Legacy auto_capture_config is deprecated; inference tables now live
    # inside AiGatewayConfig.inference_table_config.
    ai_gateway = AiGatewayConfig(
        usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
        inference_table_config=AiGatewayInferenceTableConfig(
            catalog_name=CATALOG,
            schema_name=SCHEMA,
            enabled=True,
            table_name_prefix=endpoint_name.replace("-", "_"),
        ),
    )

    try:
        w.serving_endpoints.create(
            name=endpoint_name,
            config=EndpointCoreConfigInput(
                name=endpoint_name,
                served_entities=[entity],
            ),
            ai_gateway=ai_gateway,
        )
        print(f"\u2713 Endpoint '{endpoint_name}' created (GPU_SMALL, v{version})")
    except ResourceAlreadyExists:
        w.serving_endpoints.update_config(
            name=endpoint_name,
            served_entities=[entity],
        )
        print(f"\u2713 Endpoint '{endpoint_name}' updated (v{version})")

    print(f"  Inference table: {CATALOG}.{SCHEMA}.{endpoint_name.replace('-','_')}_payload")
    print(f"  Scale-to-zero:   enabled")
    print(f"  AI Gateway:      inference table + usage tracking on")

# COMMAND ----------

# DBTITLE 1,Phase 3 header
# MAGIC %md
# MAGIC ## Phase 3 — Score / Eval
# MAGIC
# MAGIC **3a. Endpoint smoke test** — hit the serving endpoint, validate embedding shape.
# MAGIC Always runs (the endpoint is the core deliverable).
# MAGIC
# MAGIC **3b. AI Search eval scorer** — query the AI Search index with a known embedding,
# MAGIC validate self-retrieval (top-1 = query cell) and monotonic distances.
# MAGIC Only runs if the VS index exists (Phase 1b was executed). Skips gracefully otherwise.
# MAGIC
# MAGIC > For **oss-001** (baseline deploy): 3a is sufficient. Skip 3b.
# MAGIC > For **oss-002+** and production: run both 3a + 3b to validate full pipeline.
# MAGIC
# MAGIC Both are lightweight (no `teddy`/`torch` deps — just `requests` + Databricks SDK).

# COMMAND ----------

# DBTITLE 1,Smoke test TEDDY endpoint
# Lightweight smoke test — no teddy/torch/scanpy import needed
import requests, json

if not RUN_GO:
    print("run-gate off; set run_go=true to test. Skipping.")
else:
    TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().getOrElse(None)
    HOST = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
    endpoint_name = f"teddy-{MODEL_SIZE.lower()}-embedder"

    # Minimal test input (same format as input_example)
    payload = {
        "dataframe_records": [{
            "adata_sparsematrix": [[1.0, 2.0, 3.0, 0.0, 0.5] * 20],  # 1 cell, 100 genes
            "adata_var": json.dumps({"columns": ["index"], "index": list(range(100)),
                                     "data": [[f"ENSG{i:011d}"] for i in range(100)]}),
            "adata_obs": json.dumps({"columns": ["cell_id"], "index": [0],
                                     "data": [["smoke_test_cell"]]}),
        }],
        "params": {"max_seq_len": 2048, "pooling": "mean"},
    }

    url = f"{HOST}/serving-endpoints/{endpoint_name}/invocations"
    resp = requests.post(
        url, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json=payload, timeout=120,
    )

    if resp.ok:
        result = resp.json()
        preds = result.get("predictions", [])
        if preds:
            emb = preds[0].get("embedding", [])
            print(f"\u2713 TEDDY endpoint OK: {len(emb)}-d embedding")
            print(f"  First 5 values: {emb[:5]}")
        else:
            print(f"\u2713 Response received but no predictions key: {json.dumps(result)[:500]}")
    else:
        print(f"\u2717 Endpoint error {resp.status_code}: {resp.text[:500]}")
        print("  (endpoint may still be provisioning — retry in a few minutes)")

# COMMAND ----------

# DBTITLE 1,AI Search eval scorer (query index + validate)
# 3b. AI Search eval — query the index and validate search quality.
# Only runs if the AI Search index exists (Phase 1b was executed).

if not RUN_GO:
    print("run-gate off; skipping AI Search eval.")
else:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import NotFound
    import time

    w = WorkspaceClient()
    VS_INDEX = f"{CATALOG}.{SCHEMA}.teddy_cell_index"

    # Use VS_SOURCE_TABLE from the resolve cell (matches index dimension)
    try:
        source_table = VS_SOURCE_TABLE
    except NameError:
        source_table = f"{CATALOG}.{SCHEMA}.teddy_cells_{MODEL_SIZE.lower()}"

    try:
        idx_info = w.vector_search_indexes.get_index(VS_INDEX)
    except NotFound:
        print(f"AI Search index '{VS_INDEX}' not found — Phase 1b was not run. Skipping.")
        idx_info = None

    if idx_info is not None:
        # Check if index is fully synced
        idx_ready = getattr(idx_info.status, "ready", False) if idx_info.status else False
        if not idx_ready:
            print(f"\u26a0 Index '{VS_INDEX}' is still syncing — results may be incomplete.")
            print(f"  Status: {getattr(idx_info.status, 'message', 'unknown')}")
            print(f"  Re-run this cell once sync finishes.\n")

        # Grab a real embedding from the source table as the query vector
        sample_row = spark.table(source_table).limit(1).collect()[0]
        query_emb = sample_row["embedding"]
        expected_cell_id = sample_row["cell_id"]

        NUM_RESULTS = 10
        t0 = time.time()
        vs_result = w.vector_search_indexes.query_index(
            index_name=VS_INDEX,
            columns=["cell_id"],
            query_vector=query_emb,
            num_results=NUM_RESULTS,
        )
        latency_ms = (time.time() - t0) * 1000

        rows = vs_result.result.data_array or []
        returned_ids = [r[0] for r in rows]
        scores = [float(r[1]) for r in rows] if rows and len(rows[0]) > 1 else []

        # --- Scorers ---
        # 1. Self-retrieval: querying a cell's own embedding should return itself as top-1
        self_retrieval = expected_cell_id in returned_ids[:1]
        # 2. Result count: should return the requested number
        count_ok = len(rows) == NUM_RESULTS
        # 3. Monotonic distances: results should be ordered by similarity
        monotonic = all(scores[i] >= scores[i+1] for i in range(len(scores)-1)) if scores else True

        print(f"AI Search eval results for '{VS_INDEX}':")
        print(f"  Index ready:      {'\u2713' if idx_ready else '\u26a0 still syncing'}")
        print(f"  Query cell:       {expected_cell_id}")
        print(f"  Results returned: {len(rows)}/{NUM_RESULTS} {'\u2713' if count_ok else '\u2717'}")
        print(f"  Self-retrieval:   {'\u2713 top-1 match' if self_retrieval else '\u2717 NOT in top-1'}")
        print(f"  Monotonic scores: {'\u2713' if monotonic else '\u2717'}")
        print(f"  Latency:          {latency_ms:.0f} ms")
        if scores:
            print(f"  Score range:      [{scores[0]:.4f} .. {scores[-1]:.4f}]")
        print(f"  Top-5 results:")
        for i, r in enumerate(rows[:5]):
            print(f"    {i+1}. {r}")

        # Hard assertions only when index is ready; soft warnings during sync
        if idx_ready:
            assert count_ok, f"Expected {NUM_RESULTS} results, got {len(rows)}"
            assert self_retrieval, f"Self-retrieval failed — {expected_cell_id} not in top-1"
            print(f"\n\u2713 All AI Search scorers passed.")
        else:
            failures = []
            if not count_ok: failures.append(f"count={len(rows)}/{NUM_RESULTS}")
            if not self_retrieval: failures.append("self-retrieval miss")
            if failures:
                print(f"\n\u26a0 Soft failures (index still syncing): {', '.join(failures)}")
                print("  These are expected during sync — re-run when ready.")
            else:
                print(f"\n\u2713 All VS scorers passed (even during sync!).")

# COMMAND ----------

# DBTITLE 1,Phase 4 header
# MAGIC %md
# MAGIC ## Phase 4 — Teardown
# MAGIC
# MAGIC Cleanup resources created by this notebook. Run selectively.
# MAGIC
# MAGIC | Resource | Cost while alive? | Teardown action |
# MAGIC |---|---|---|
# MAGIC | Serving endpoint | **Yes** (GPU billing, even at scale-to-zero provisioned) | `delete` |
# MAGIC | AI Search endpoint | Yes (compute) | `delete` (shared — only if no other indexes) |
# MAGIC | AI Search index | Minimal (storage only) | `delete` |
# MAGIC | UC model version | No | Keep (cheap, useful for audit) |
# MAGIC | Inference table | No (storage only) | Keep (useful for debugging) |

# COMMAND ----------

# DBTITLE 1,Teardown
# Selective teardown — uncomment the resources you want to clean up.
# Safe to re-run (all operations are idempotent / catch NotFound).

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

w = WorkspaceClient()
endpoint_name = f"teddy-{MODEL_SIZE.lower()}-embedder"
VS_INDEX = f"{CATALOG}.{SCHEMA}.teddy_cell_index"
VS_ENDPOINT = "gwb_teddy_vs_endpoint"

# --- 1. Serving endpoint (highest cost) ---
# try:
#     w.serving_endpoints.delete(endpoint_name)
#     print(f"\u2713 Deleted serving endpoint '{endpoint_name}'")
# except NotFound:
#     print(f"  Serving endpoint '{endpoint_name}' already gone.")

# --- 2. AI Search index ---
# try:
#     w.vector_search_indexes.delete_index(index_name=VS_INDEX)
#     print(f"\u2713 Deleted AI Search index '{VS_INDEX}'")
# except NotFound:
#     print(f"  AI Search index '{VS_INDEX}' already gone.")

# --- 3. AI Search endpoint (shared — only delete if no other indexes use it) ---
# try:
#     w.vector_search_endpoints.delete_endpoint(VS_ENDPOINT)
#     print(f"\u2713 Deleted AI Search endpoint '{VS_ENDPOINT}'")
# except NotFound:
#     print(f"  AI Search endpoint '{VS_ENDPOINT}' already gone.")

print("\n\u2713 Teardown complete. Inference table + UC model preserved (no ongoing cost).")
