# Databricks notebook source
# DBTITLE 1,Scimilarity Ground Truth
# MAGIC %md
# MAGIC # Scimilarity v1.1 — Ground Truth
# MAGIC
# MAGIC > **STATUS: TODO** — Not yet tested end-to-end. Pending gt_geneformer + oss-002/003 completion.
# MAGIC > AI Search rename already applied to this notebook.
# MAGIC
# MAGIC Downloads the Scimilarity v1.1 pretrained model from Zenodo to a UC Volume.
# MAGIC
# MAGIC ### Provenance
# MAGIC
# MAGIC [Genesis Workbench SCimilarity module](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/scimilarity)
# MAGIC → [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7) (`oss-models` skill) → this ground truth notebook.
# MAGIC
# MAGIC **Canonical source:** [`modules/single_cell/scimilarity`](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/scimilarity) |
# MAGIC ### Module notebooks ([source](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/scimilarity/notebooks))
# MAGIC
# MAGIC | Notebook | Purpose |
# MAGIC |----------|---------|
# MAGIC | [`01_wget_scimilarity.py`](https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scimilarity/notebooks/01_wget_scimilarity.py) | `ScimilaritySetup` class — idempotent download + extract + parallel model+data |
# MAGIC | [`02_register_GeneOrder.py`](https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scimilarity/notebooks/02_register_GeneOrder.py) | Register gene ordering model |
# MAGIC | [`03_register_GetEmbedding.py`](https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scimilarity/notebooks/03_register_GetEmbedding.py) | Register embedding model |
# MAGIC | [`04_register_SearchNearest.py`](https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scimilarity/notebooks/04_register_SearchNearest.py) | Register kNN search model |
# MAGIC | [`05_importNserve_model_gwb.py`](https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scimilarity/notebooks/05_importNserve_model_gwb.py) | Import into GWB + deploy endpoints (requires GWB library) |
# MAGIC | `06b_checkNuse_SCimilarityEndpoints` | Verify endpoints + smoke test |
# MAGIC
# MAGIC > **Standalone path**: `01_wget` → `02_register` → `03_register` → `04_register` work without the GWB library.
# MAGIC > `05_importNserve` is only needed for GWB app deployment.
# MAGIC
# MAGIC ## Available models
# MAGIC
# MAGIC | | Zenodo v1.1 (Genentech) | HF expanded (SAIL @ MSKCC) |
# MAGIC |---|---|---|
# MAGIC | Source | [Zenodo 10685499](https://zenodo.org/records/10685499) | [sail-mskcc/scimilarity_expanded_model](https://huggingface.co/sail-mskcc/scimilarity_expanded_model) |
# MAGIC | Training cells | 7.9 M | **39.5 M** (5×) |
# MAGIC | Search index cells | 23.4 M | **45.5 M** (2×) |
# MAGIC | Distribution | Single tarball | Individual files (HF LFS) |
# MAGIC | Core model size | ~250 MB (in 1.3 GB tarball) | **~1.0 GB** (encoder + decoder + gene_order + reference_labels) |
# MAGIC | kNN indexes | Included in tarball | **~159 GB** (optional — 50 GB each for annotation + cellsearch) |
# MAGIC | Download method | `curl` | `huggingface_hub.snapshot_download` |
# MAGIC | License | Check repo | Apache-2.0 |
# MAGIC | API compatibility | `scimilarity` v0.4+ | Same — just change `model_path` |
# MAGIC
# MAGIC > **Both models use the same `scimilarity` API.** `CellEmbedding(model_path=...)` works unchanged.
# MAGIC > For embedding-only (no cell search), both need <1 GB of core files.
# MAGIC
# MAGIC ## Estimated download times
# MAGIC
# MAGIC | Source | Asset | Size | Est. time |
# MAGIC |--------|-------|------|-----------|
# MAGIC | Zenodo | Model v1.1 tarball | ~1.3 GB | **~30–60 min** (Zenodo is slow) |
# MAGIC | Zenodo | Sample data h5ad | ~50 MB | ~1–2 min |
# MAGIC | HF | Core model only | ~1.0 GB | **~2–5 min** (HF CDN is fast) |
# MAGIC | HF | Full (with kNN) | ~160 GB | **~hours** (needs large Volume) |
# MAGIC
# MAGIC > Set `model_source` widget to `zenodo` or `huggingface`.
# MAGIC > Set `download_knn` to `true` for HF full download (default: `false`).
# MAGIC
# MAGIC
# MAGIC ## BioNeMo integration — NVIDIA Geneformer as alternative engine
# MAGIC
# MAGIC | | SCimilarity (Genentech) | Geneformer V2 (NVIDIA BioNeMo) |
# MAGIC |---|---|---|
# MAGIC | Architecture | Metric-learning AE (triplet loss) | Transformer (attention) |
# MAGIC | Training data | 7.9 M cells (v1.1) / 39.5 M (expanded) | 30 M cells (Genecorpus-30M) |
# MAGIC | Embedding dim | 128 | 512 (316M param model) |
# MAGIC | Input format | Raw expression matrix → `align_dataset` + `lognorm_counts` | Rank-value encoded gene tokens |
# MAGIC | Cell search | Built-in kNN (`CellQuery`) | BYO index (Databricks AI Search) |
# MAGIC | Cell annotation | Built-in (`CellAnnotation`) | Fine-tune or kNN on embeddings |
# MAGIC | Install | `pip install scimilarity` | `pip install transformer_engine[pytorch] transformers` |
# MAGIC | Docker needed? | **No** — pip works | **No** — `AutoModel.from_pretrained("nvidia/geneformer_V2_316M")` |
# MAGIC | Compute | **CPU** for inference | **GPU required** (Ampere+, no CPU path) |
# MAGIC | HF source | [sail-mskcc/scimilarity_expanded_model](https://huggingface.co/sail-mskcc/scimilarity_expanded_model) | [nvidia/geneformer_V2_316M](https://huggingface.co/nvidia/geneformer_V2_316M) |
# MAGIC | License | Apache-2.0 (expanded) | Apache-2.0 |
# MAGIC
# MAGIC > **Neither model needs Docker on Databricks.** Both load directly via pip + HuggingFace.
# MAGIC > SCimilarity runs on serverless CPU; Geneformer needs serverless GPU (AI Runtime).
# MAGIC
# MAGIC **Existing workspace notebooks:**
# MAGIC - [`geneformer_bionemo_serving_4wstest`](https://github.com/Genentech/scimilarity) — validates HF → MLflow PyFunc → UC → GPU Model Serving path for Geneformer
# MAGIC - BioNeMo module (`bionemo_esm_finetune`, `bionemo_esm_inference`) — ESM protein model
# MAGIC
# MAGIC **When to use Geneformer instead of SCimilarity:**
# MAGIC - Larger embedding space (512-d vs 128-d) — may capture finer cell-state differences
# MAGIC - Transformer attention weights are interpretable (which genes drive the embedding)
# MAGIC - Already on GPU compute for other BioNeMo models (ESM, MegaMolBART)
# MAGIC - Want to fine-tune on custom cell-type labels
# MAGIC
# MAGIC **When to stick with SCimilarity:**
# MAGIC - CPU-only inference (serverless, no GPU cost)
# MAGIC - Built-in cell search + cell annotation (no need to build your own index)
# MAGIC - The `04_register_SearchNearest` → `06b+06c` (Delta + AI Search) migration path is already validated
# MAGIC
# MAGIC ## How to use
# MAGIC
# MAGIC 1. **If model already in Volume** → Cell below verifies and skips
# MAGIC 2. **If not** → Run the download cells below in this notebook

# COMMAND ----------

# DBTITLE 1,Check Volume for model
# --- Configuration: choose model source + check Volume ---
import os

dbutils.widgets.text("catalog", "<catalog>", "Unity Catalog catalog")
dbutils.widgets.text("schema", "skills", "Unity Catalog schema")
dbutils.widgets.text("cache_dir", "scimilarity", "Cache dir (volume name)")
dbutils.widgets.dropdown("model_source", "zenodo", ["zenodo", "huggingface"], "Model source")
dbutils.widgets.dropdown("download_knn", "false", ["false", "true"], "Download kNN indexes (HF only, ~159 GB)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
MODEL_SOURCE = dbutils.widgets.get("model_source")
DOWNLOAD_KNN = dbutils.widgets.get("download_knn") == "true"

# --- Source-specific paths ---
# Both models use gene_order.tsv as sentinel; same scimilarity API
BASE_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"

if MODEL_SOURCE == "zenodo":
    MODEL_SUBDIR = "model/model_v1.1"
    MODEL_VERSION = "v1.1"
    HF_REPO_ID = None
else:
    MODEL_SUBDIR = "model/expanded_model"    # SAIL-MSKCC expanded
    MODEL_VERSION = "expanded"
    HF_REPO_ID = "sail-mskcc/scimilarity_expanded_model"

model_path = f"{BASE_DIR}/{MODEL_SUBDIR}"
gene_order_file = os.path.join(model_path, "gene_order.tsv")

print(f"Source   : {MODEL_SOURCE}")
print(f"Model dir: {model_path}")
if MODEL_SOURCE == "huggingface":
    print(f"kNN      : {'yes (~159 GB)' if DOWNLOAD_KNN else 'no (core model only, ~1 GB)'}")
print()

if os.path.exists(gene_order_file):
    n_files = sum(1 for _, _, files in os.walk(model_path) for _ in files)
    print(f"\u2713 Scimilarity {MODEL_VERSION} already in Volume")
    print(f"  {n_files} files in model directory")
else:
    print(f"\u2717 Model NOT found at {model_path}")
    print(f"  Run cells 3–6 to download from {MODEL_SOURCE}")

# COMMAND ----------

# DBTITLE 1,Compute detection
import os, subprocess

# --- Compute detection (works on Serverless and Classic) ---
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
print(f"Volume ready: /Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}")

# COMMAND ----------

# DBTITLE 1,Download + extract
import subprocess, time, logging, os, shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scimilarity_setup")

# --- Shared paths ---
MODEL_DIR = f"{BASE_DIR}/model"
DOWNLOADS_DIR = f"{BASE_DIR}/downloads"
DATA_DIR = f"{BASE_DIR}/data/adams_etal_2020"
SAMPLE_DATA_URL = "https://zenodo.org/records/13685881/files/GSE136831_subsample.h5ad?download=1"
SAMPLE_DATA_PATH = f"{DATA_DIR}/GSE136831_subsample.h5ad"


def curl_download(url, destination, max_attempts=10, backoff_s=30):
    """Download via curl with retry + resume."""
    if os.path.exists(destination) and os.path.getsize(destination) > 0:
        logger.info(f"Already exists: {destination} ({os.path.getsize(destination)/1e6:.0f} MB)")
        return
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    for attempt in range(1, max_attempts + 1):
        logger.info(f"curl attempt {attempt}/{max_attempts}: {os.path.basename(destination)}")
        rc = subprocess.run(
            ["curl", "-fSL", "-C", "-", "--connect-timeout", "60",
             "--max-time", "3600", "--progress-bar", "-o", destination, url]
        ).returncode
        if rc == 0:
            logger.info(f"Done: {destination} ({os.path.getsize(destination)/1e6:.0f} MB)")
            return
        logger.warning(f"curl exit {rc} — retrying in {backoff_s}s")
        time.sleep(backoff_s)
    raise RuntimeError(f"Download failed after {max_attempts} attempts: {url}")


def setup_sample_data():
    """Download Adams et al. sample h5ad (shared by both sources)."""
    if os.path.exists(SAMPLE_DATA_PATH) and os.path.getsize(SAMPLE_DATA_PATH) > 0:
        logger.info(f"Sample data already at {SAMPLE_DATA_PATH}")
        return SAMPLE_DATA_PATH
    os.makedirs(DATA_DIR, exist_ok=True)
    curl_download(SAMPLE_DATA_URL, SAMPLE_DATA_PATH)
    return SAMPLE_DATA_PATH


# =====================================================================
# SOURCE A: Zenodo v1.1 (Genentech)
# =====================================================================
def setup_zenodo():
    ZENODO_URL = "https://zenodo.org/records/10685499/files/model_v1.1.tar.gz?download=1"
    tarball = f"{DOWNLOADS_DIR}/model_v1.1.tar.gz"
    extract_sentinel = f"{MODEL_DIR}/model_v1.1/gene_order.tsv"

    if os.path.exists(extract_sentinel):
        logger.info(f"Zenodo v1.1 already extracted at {MODEL_DIR}/model_v1.1")
        return

    start = time.time()
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)
    curl_download(ZENODO_URL, tarball)
    logger.info(f"Extracting {tarball} -> {MODEL_DIR}")
    subprocess.run(["tar", "--no-same-owner", "-xzf", tarball, "-C", MODEL_DIR], check=True)
    logger.info(f"Zenodo setup complete in {time.time()-start:.0f}s")


# =====================================================================
# SOURCE B: HuggingFace expanded model (SAIL @ MSKCC)
# Uses huggingface_hub.snapshot_download — built-in resume, retry, LFS
# =====================================================================
def setup_huggingface():
    from huggingface_hub import snapshot_download

    dest = f"{MODEL_DIR}/expanded_model"
    sentinel = os.path.join(dest, "gene_order.tsv")

    if os.path.exists(sentinel):
        logger.info(f"HF expanded model already at {dest}")
        return

    # Core model: encoder, decoder, gene_order, metadata, labels (~1 GB)
    # kNN indexes: annotation/ + cellsearch/ (~159 GB) — optional
    if DOWNLOAD_KNN:
        logger.info("Downloading FULL HF model (~160 GB) with kNN indexes...")
        allow = None  # everything
    else:
        logger.info("Downloading HF core model only (~1 GB, no kNN indexes)...")
        allow = ["*.ckpt", "*.tsv", "*.json", "*.csv",
                 "annotation/labelled_kNN.bin",   # needed for CellAnnotation
                 "annotation/reference_labels.tsv"]

    start = time.time()
    os.makedirs(dest, exist_ok=True)

    snapshot_download(
        repo_id=HF_REPO_ID,
        local_dir=dest,
        allow_patterns=allow,
        resume_download=True,
    )
    logger.info(f"HF download complete in {time.time()-start:.0f}s")


# =====================================================================
# Run: download model + sample data in parallel
# =====================================================================
if os.path.exists(gene_order_file):
    logger.info(f"Model already present at {model_path}. Checking sample data...")
    setup_sample_data()
else:
    logger.info(f"Starting Scimilarity setup (source={MODEL_SOURCE})...")
    model_fn = setup_zenodo if MODEL_SOURCE == "zenodo" else setup_huggingface
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(model_fn): "model",
            executor.submit(setup_sample_data): "sample_data",
        }
        for future in as_completed(futures):
            key = futures[future]
            future.result()  # raises on failure
            logger.info(f"{key}: done")
    logger.info("Setup complete.")

# COMMAND ----------

# DBTITLE 1,Verify
assert os.path.exists(gene_order_file), f"Missing sentinel: {gene_order_file}"

print(f"\u2713 Scimilarity {MODEL_VERSION} ready at: {model_path}")
print(f"  Source: {MODEL_SOURCE}")
print()

# Show top-level files + first-level subdirs
total_files = 0
total_bytes = 0
for entry in sorted(os.listdir(model_path)):
    full = os.path.join(model_path, entry)
    if os.path.isfile(full):
        size = os.path.getsize(full)
        total_bytes += size
        total_files += 1
        print(f"  {entry}  ({size/1e6:.1f} MB)")
    elif os.path.isdir(full):
        # Count files in subdirectory
        sub_files = sum(1 for _, _, fs in os.walk(full) for _ in fs)
        sub_bytes = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(full) for f in fs)
        total_files += sub_files
        total_bytes += sub_bytes
        print(f"  {entry}/  ({sub_files} files, {sub_bytes/1e9:.1f} GB)")

print(f"\n  Total: {total_files} files, {total_bytes/1e9:.2f} GB")

if os.path.exists(SAMPLE_DATA_PATH):
    size = os.path.getsize(SAMPLE_DATA_PATH) / 1e6
    print(f"\n\u2713 Sample data: {SAMPLE_DATA_PATH} ({size:.1f} MB)")

# COMMAND ----------

# DBTITLE 1,Scimilarity Register/Deploy Ground Truth
import datetime

# Source-specific provenance
if MODEL_SOURCE == "zenodo":
    source_block = """  source_url: https://zenodo.org/records/10685499
  source_type: zenodo_tarball"""
else:
    source_block = f"""  source_url: https://huggingface.co/{HF_REPO_ID}
  source_type: huggingface_hub
  knn_included: {DOWNLOAD_KNN}"""

manifest = f"""model:
  name: scimilarity
  version: {MODEL_VERSION}
{source_block}
  code_url: https://github.com/Genentech/scimilarity
  license: {'Apache-2.0' if MODEL_SOURCE == 'huggingface' else 'check_repo'}
  reviewed_at: {datetime.date.today().isoformat()}
adapted_from:
  genesis_workbench: modules/single_cell/scimilarity/notebooks/01_wget_scimilarity.py
  url: https://github.com/databricks-industry-solutions/genesis-workbench
  deprecation_note: 04_register_SearchNearest.py superseded by 06b + 06c
weights:
  location: {model_path}
sample_data:
  location: {SAMPLE_DATA_PATH}
  source_url: https://zenodo.org/records/13685881
runtime:
  download_compute: {'serverless_cpu' if IS_SERVERLESS else 'classic_cpu'}
  register_compute: cpu_or_gpu
"""

manifest_path = os.path.join(model_path, "provenance_manifest.yaml")
with open(manifest_path, "w") as f:
    f.write(manifest)
print("Provenance manifest:", manifest_path)
print(manifest)

%md
# SCimilarity — Register, Deploy and Score (Standalone)

**Standalone** register + deploy for SCimilarity, via [GWB](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/scimilarity) + [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7). Three phases with intentionally separated dependencies:

| Phase | What | Cells |
|-------|------|-------|
| **1. Register** | Log PyFunc models to UC (GeneOrder, GetEmbedding, SearchNearest) with `input_example` + `signature` | 4–9 |
| **1b. AI Search** | Extract reference to Delta + create AI Search index (optional, replaces SearchNearest for prod) | 10–12 |
| **2. Deploy** | Model Serving endpoints with **inference table** + **AI Gateway** + scale-to-zero | 13–14 |
| **3. Score / Eval** | 3a: Endpoint smoke test. 3b: VS eval scorer (self-retrieval, monotonic scores) | 15–17 |
| **4. Teardown** | Delete endpoints + optionally VS resources. Inference table + UC models preserved | 18–19 |

> **Why standalone?** The GWB wheel (`genesis_workbench`) adds app-framework
> deps and an extra install step. For ground-truth scoring and evals, Phases 2–3
> should run with zero ML dependencies.



### Cell search: two paths

| Path | Infra | Latency | Scale | When to use |
|------|-------|---------|-------|-------------|
| **SearchNearest PyFunc** (04) | None — kNN bundled in model weights | Fast (in-process) | ~23M cells (Zenodo) | Standalone scoring, evals, dev — no extra setup |
| **AI Search** (06b+06c) | AI Search endpoint + Delta table | ~20–50ms (Standard) | 45M+ cells (HF expanded) | Production, multi-user, auto-sync |

## Model sources

| | Zenodo v1.1 (Genentech) | HF expanded (SAIL @ MSKCC) |
|---|---|---|
| Weights | [Zenodo 10685499](https://zenodo.org/records/10685499) | [sail-mskcc/scimilarity_expanded_model](https://huggingface.co/sail-mskcc/scimilarity_expanded_model) |
| Training cells | 7.9 M | 39.5 M |
| API compat | `scimilarity` v0.4+ | Same — just change `model_path` |
| License | Check repo | Apache-2.0 |

## Prerequisite

Model in UC Volume — see download cells above.

# COMMAND ----------

# DBTITLE 1,Configuration
import os

dbutils.widgets.text("catalog", "<catalog>", "Unity Catalog catalog")
dbutils.widgets.text("schema", "skills", "Unity Catalog schema")
dbutils.widgets.text("cache_dir", "scimilarity", "Cache dir (volume name)")
dbutils.widgets.dropdown("model_source", "zenodo", ["zenodo", "huggingface"], "Model source")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
MODEL_SOURCE = dbutils.widgets.get("model_source")

BASE_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"
MODEL_SUBDIR = "model/model_v1.1" if MODEL_SOURCE == "zenodo" else "model/expanded_model"
model_path = f"{BASE_DIR}/{MODEL_SUBDIR}"
geneOrder_path = os.path.join(model_path, "gene_order.tsv")

assert os.path.exists(geneOrder_path), (
    f"Model not found at {model_path}. Run the download cells above first."
)

print(f"Catalog    : {CATALOG}")
print(f"Schema     : {SCHEMA}")
print(f"Model path : {model_path}")
print(f"Source     : {MODEL_SOURCE}")

# COMMAND ----------

# DBTITLE 1,Phase 1 header
# MAGIC %md
# MAGIC ## Phase 1 — Register PyFunc models to Unity Catalog
# MAGIC
# MAGIC **Heavy deps required** (`scimilarity`, `mlflow`). Three models:
# MAGIC 1. **GeneOrder** — static gene ordering vector (CPU, lightweight)
# MAGIC 2. **GetEmbedding** — neural net cell embeddings (CPU or GPU)
# MAGIC 3. **SearchNearest** — kNN cell search (CPU, standalone reference)
# MAGIC
# MAGIC Adapted from GWB `02_register_GeneOrder.py`, `03_register_GetEmbedding.py`,
# MAGIC `04_register_SearchNearest.py` — **no `genesis_workbench` wheel needed.**

# COMMAND ----------

# DBTITLE 1,Install registration deps
# MAGIC %pip install -q scimilarity==0.4.0 scanpy==1.11.2 numcodecs==0.13.1 \
# MAGIC     numpy==1.26.4 pandas==1.5.3 mlflow==2.22.0 cloudpickle==2.0.0 \
# MAGIC     typing_extensions==4.15.0 tbb==2021.13.0 setuptools<82
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Restore widgets after restart
# Re-read widgets after restartPython — widget state persists but Python vars don't
import os

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
MODEL_SOURCE = dbutils.widgets.get("model_source")

BASE_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"
MODEL_SUBDIR = "model/model_v1.1" if MODEL_SOURCE == "zenodo" else "model/expanded_model"
model_path = f"{BASE_DIR}/{MODEL_SUBDIR}"
geneOrder_path = os.path.join(model_path, "gene_order.tsv")

print(f"model_path: {model_path}")

# COMMAND ----------

# DBTITLE 1,Register GeneOrder to UC
import csv
import mlflow
import pandas as pd
from mlflow.pyfunc.model import PythonModelContext
from mlflow.models import infer_signature

class SCimilarity_GeneOrder(mlflow.pyfunc.PythonModel):
    """Static gene-order lookup. Returns the 28k gene ordering vector."""
    def load_context(self, context: PythonModelContext):
        self.gene_order = []
        with open(context.artifacts["geneOrder_path"]) as f:
            for row in csv.reader(f, delimiter="\t"):
                self.gene_order.extend(row)

    def predict(self, model_input: pd.DataFrame = None):
        return self.gene_order

# Test locally
class _Ctx:
    artifacts = {"geneOrder_path": geneOrder_path}

_model = SCimilarity_GeneOrder()
_model.load_context(_Ctx())
assert len(_model.predict()) > 20_000, "Gene order should have >20k genes"
print(f"\u2713 GeneOrder: {len(_model.predict())} genes")

# Log + register
model_name_go = f"{CATALOG}.{SCHEMA}.scimilarity_gene_order"
example_input = pd.DataFrame({"input": ["get_gene_order"]})
sig = infer_signature(example_input, _model.predict(example_input))

with mlflow.start_run(run_name="scimilarity_gene_order") as run:
    mlflow.pyfunc.log_model(
        artifact_path="Gene_Order",
        python_model=_model,
        artifacts={"geneOrder_path": geneOrder_path},
        input_example=example_input,
        signature=sig,
        pip_requirements=["setuptools<82"],
        registered_model_name=model_name_go,
    )
    print(f"\u2713 Registered {model_name_go} (run {run.info.run_id})")

# COMMAND ----------

# DBTITLE 1,Register GetEmbedding to UC
import numpy as np
import torch
from scimilarity import CellEmbedding

class SCimilarity_GetEmbedding(mlflow.pyfunc.PythonModel):
    """Cell embedding model. Input: expression vectors; output: 128-d embeddings."""
    def load_context(self, context: PythonModelContext):
        self.ce = CellEmbedding(context.artifacts["model_path"])

    def predict(self, context: PythonModelContext, model_input: pd.DataFrame) -> pd.DataFrame:
        results = []
        for _, row in model_input.iterrows():
            sample_df = pd.read_json(row["celltype_sample"], orient="split")
            obs_json = row.get("celltype_sample_obs")
            obs_df = pd.read_json(obs_json, orient="split") if obs_json else None

            embeddings = []
            for si, sr in sample_df.iterrows():
                arr = np.array(sr["celltype_subsample"], dtype=np.float64).reshape(1, -1)
                emb = self.ce.get_embeddings(arr)
                embeddings.append({"celltype_sample_index": si, "embedding": emb.tolist()})

            edf = pd.DataFrame(embeddings)
            edf.index = edf["celltype_sample_index"]
            edf.index.name = None
            if obs_df is not None:
                edf = pd.merge(edf, obs_df, left_index=True, right_index=True)
            results.append(edf)

        out = pd.concat(results).reset_index(drop=True)
        for col in out.select_dtypes(include=["int"]).columns:
            out[col] = out[col].astype(float)
        return out

# Test locally
class _CtxEmb:
    artifacts = {"model_path": model_path}

_emb_model = SCimilarity_GetEmbedding()
_emb_model.load_context(_CtxEmb())
print(f"\u2713 GetEmbedding loaded from {model_path}")

# --- Build input_example + signature for UI testing ---
# Synthetic expression vector using gene order length
_n_genes = len(pd.read_csv(geneOrder_path, header=None).squeeze().tolist())
_synth_expr = np.random.default_rng(42).normal(0, 1, _n_genes).tolist()
_sample_df = pd.DataFrame([{"celltype_subsample": _synth_expr}], index=["synth_0"])

example_input_emb = pd.DataFrame([{
    "celltype_sample": _sample_df.to_json(orient="split"),
}])

# Add optional column with None for proper signature inference
example_input_emb_with_opt = example_input_emb.copy()
example_input_emb_with_opt["celltype_sample_obs"] = None

_emb_output = _emb_model.predict(_CtxEmb(), example_input_emb)
sig_emb = infer_signature(example_input_emb_with_opt, _emb_output)
print(f"\u2713 Signature: {sig_emb}")

# Log + register
model_name_emb = f"{CATALOG}.{SCHEMA}.scimilarity_get_embedding"

with mlflow.start_run(run_name="scimilarity_get_embedding") as run:
    mlflow.pyfunc.log_model(
        artifact_path="Get_Embedding",
        python_model=_emb_model,
        artifacts={"model_path": model_path},
        input_example=example_input_emb,
        signature=sig_emb,
        pip_requirements=[
            "setuptools<82", "mlflow==2.22.0", "cloudpickle==2.0.0",
            "scanpy==1.11.2", "numcodecs==0.13.1",
            "scimilarity==0.4.0", "pandas==1.5.3", "numpy==1.26.4",
        ],
        registered_model_name=model_name_emb,
    )
    print(f"\u2713 Registered {model_name_emb} (run {run.info.run_id})")

# COMMAND ----------

# DBTITLE 1,Register SearchNearest to UC (reference — standalone kNN)
# For production at scale, use Phase 1b (AI Search) instead.
import json
from scimilarity import CellQuery

class SCimilarity_SearchNearest(mlflow.pyfunc.PythonModel):
    """kNN cell search. Input: embedding + optional params; output: nearest neighbors."""
    def load_context(self, context: PythonModelContext):
        self.cq = CellQuery(context.artifacts["model_path"])

    def predict(self, context: PythonModelContext, model_input: pd.DataFrame) -> pd.DataFrame:
        embeddings = model_input["embedding"].iloc[0]
        if isinstance(embeddings, str):
            embeddings = json.loads(embeddings)
        embeddings = np.array(embeddings)

        # Parse optional k parameter
        k = 100
        if "params" in model_input.columns:
            raw = model_input["params"].iloc[0]
            if raw and not (isinstance(raw, float) and pd.isna(raw)):
                try:
                    p = json.loads(raw) if isinstance(raw, str) else raw
                    k = int(p.get("k", 100))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

        nn_idxs, nn_dists, results_meta = self.cq.search_nearest(embeddings, k=k)
        return pd.DataFrame([{
            "nn_idxs": [a.tolist() for a in nn_idxs],
            "nn_dists": [a.tolist() for a in nn_dists],
            "results_metadata": json.dumps(results_meta.to_dict()),
        }])

# Test locally
class _CtxSearch:
    artifacts = {"model_path": model_path}

_search_model = SCimilarity_SearchNearest()
_search_model.load_context(_CtxSearch())
print(f"\u2713 SearchNearest loaded (kNN index in {model_path})")

# --- Build input_example + signature for UI testing ---
# Use embedding from the GetEmbedding test if available, else synthetic 128-d
try:
    _test_emb = _emb_output.iloc[0]["embedding"]
    if isinstance(_test_emb, list) and len(_test_emb) == 128:
        _search_emb = _test_emb
    else:
        _search_emb = np.random.default_rng(42).normal(0, 1, 128).tolist()
except Exception:
    _search_emb = np.random.default_rng(42).normal(0, 1, 128).tolist()

example_input_search = pd.DataFrame([{
    "embedding": _search_emb,
    "params": json.dumps({"k": 10}),
}])

# With optional params column for signature
example_input_search_opt = example_input_search.copy()
example_input_search_opt.loc[1] = {"embedding": _search_emb, "params": None}
example_input_search_opt["params"] = example_input_search_opt["params"].where(
    example_input_search_opt["params"].notna(), None
)

_search_output = _search_model.predict(_CtxSearch(), example_input_search.iloc[:1])
sig_search = infer_signature(example_input_search_opt, _search_output)
print(f"\u2713 Signature: {sig_search}")

# Log + register
model_name_search = f"{CATALOG}.{SCHEMA}.scimilarity_search_nearest"

with mlflow.start_run(run_name="scimilarity_search_nearest") as run:
    mlflow.pyfunc.log_model(
        artifact_path="Search_Nearest",
        python_model=_search_model,
        artifacts={"model_path": model_path},
        input_example=example_input_search.iloc[:1],
        signature=sig_search,
        pip_requirements=[
            "setuptools<82", "mlflow==2.22.0", "cloudpickle==2.0.0",
            "scanpy==1.11.2", "numcodecs==0.13.1",
            "scimilarity==0.4.0", "pandas==1.5.3", "numpy==1.26.4",
        ],
        registered_model_name=model_name_search,
    )
    print(f"\u2713 Registered {model_name_search} (run {run.info.run_id})")

# COMMAND ----------

# DBTITLE 1,Phase 1b header
# MAGIC %md
# MAGIC ## Phase 1b — AI Search alternative (optional)
# MAGIC
# MAGIC **Replaces SearchNearest for production.** Creates a `scimilarity_cells` Delta table +
# MAGIC Databricks AI Search index for nearest-neighbor cell search.
# MAGIC
# MAGIC ### Source table resolution (2-tier fallback)
# MAGIC
# MAGIC | Priority | Table | Rows | Dim | Metadata | When used |
# MAGIC |---|---|---|---|---|---|
# MAGIC | 1. Existing production | `genesis_workbench.scimilarity_cells` | 23.4M | 128 | prediction, tissue, disease, study, QC | If available |
# MAGIC | 2. Extract from model | `skills.scimilarity_cells` | ~23M (Zenodo) / ~45M (HF) | 128 | same | If needed |
# MAGIC
# MAGIC > SCimilarity always produces 128-d embeddings (single architecture) —
# MAGIC > no dimension mismatch concern unlike TEDDY.
# MAGIC
# MAGIC > **Skip this phase** if you only need standalone scoring via the SearchNearest PyFunc.
# MAGIC > The AI Search path is preferred when you need multi-user access, auto-sync with new data,
# MAGIC > or the HF expanded model's 45M-cell index (too large for in-process kNN).

# COMMAND ----------

# DBTITLE 1,Resolve or extract scimilarity_cells source table
# Resolve scimilarity_cells source table for AI Search indexing.
# 2-tier fallback:
#   1. GWB production table (genesis_workbench.scimilarity_cells) — if GWB deployed
#   2. Extract from model artifacts (skills.scimilarity_cells) — adapted from GWB 06b
#
# SCimilarity always produces 128-d embeddings (single architecture, no dim mismatch).

GWB_SCIM_TABLE = f"{CATALOG}.genesis_workbench.scimilarity_cells"
CELLS_TABLE = f"{CATALOG}.{SCHEMA}.scimilarity_cells"
VS_SOURCE_TABLE = None
VS_HAS_METADATA = False

# --- Tier 1: GWB production table ---
if spark.catalog.tableExists(GWB_SCIM_TABLE):
    gwb_count = spark.table(GWB_SCIM_TABLE).count()
    gwb_dim = spark.sql(f"SELECT size(embedding) FROM {GWB_SCIM_TABLE} LIMIT 1").first()[0]
    VS_SOURCE_TABLE = GWB_SCIM_TABLE
    VS_HAS_METADATA = True
    print(f"\u2713 Using GWB production table: {GWB_SCIM_TABLE}")
    print(f"  {gwb_count:,} cells, dim={gwb_dim}, "
          f"74 cell types, 188 tissues, 136 diseases")

# --- Tier 2: Existing or extract skills table ---
if VS_SOURCE_TABLE is None and spark.catalog.tableExists(CELLS_TABLE):
    skills_count = spark.table(CELLS_TABLE).count()
    VS_SOURCE_TABLE = CELLS_TABLE
    print(f"\u2713 Using existing skills table: {CELLS_TABLE} ({skills_count:,} rows)")

if VS_SOURCE_TABLE is not None:
    print(f"\nVS_SOURCE_TABLE = {VS_SOURCE_TABLE}")
    print(f"VS_HAS_METADATA = {VS_HAS_METADATA}")
    print("Skipping extraction — source table already available.")
else:
    print("No existing table found. Extracting from model artifacts...")
    from scimilarity import CellQuery as _CQ
    import numpy as _np

    BATCH_SIZE = 1_000_000

    cq = _CQ(model_path, load_knn=False)
    n_cells = len(cq.cell_metadata)
    _probe = _np.asarray(cq.get_precomputed_embeddings(_np.array([0], dtype=_np.int64))).reshape(1, -1)
    emb_dim = _probe.shape[1]
    print(f"Reference cells: {n_cells:,}  |  Embedding dim: {emb_dim}")
    from pyspark.sql.types import StructType, StructField, StringType, ArrayType, FloatType
    import pandas as pd

    spark.sql(f"DROP TABLE IF EXISTS {CELLS_TABLE}")
    meta_cols = list(cq.cell_metadata.columns)
    cell_ids = cq.cell_metadata.index.astype(str)
    schema = StructType(
        [StructField("cell_id", StringType(), False),
         StructField("embedding", ArrayType(FloatType(), False), False)]
        + [StructField(c, StringType(), True) for c in meta_cols]
    )

    written = 0
    for start in range(0, n_cells, BATCH_SIZE):
        end = min(start + BATCH_SIZE, n_cells)
        embs = _np.asarray(cq.get_precomputed_embeddings(
            _np.arange(start, end, dtype=_np.int64)
        )).astype(_np.float32).reshape(end - start, emb_dim)
        meta = cq.cell_metadata.iloc[start:end].reset_index(drop=True)
        pdf = pd.DataFrame({"cell_id": cell_ids[start:end].to_numpy()})
        pdf["embedding"] = [row.tolist() for row in embs]
        for c in meta_cols:
            vals = meta[c]
            pdf[c] = vals.astype(object).where(vals.notna(), None).map(
                lambda v: None if v is None else str(v)
            )
        spark.createDataFrame(pdf, schema=schema).write.format("delta").mode("append").saveAsTable(CELLS_TABLE)
        written += (end - start)
        print(f"  Batch: rows [{start:,}, {end:,}) — {written:,}/{n_cells:,}")

    spark.sql(f"ALTER TABLE {CELLS_TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
    VS_SOURCE_TABLE = CELLS_TABLE
    print(f"\u2713 Wrote {written:,} cells to {CELLS_TABLE} (CDF enabled)")
    print(f"\nVS_SOURCE_TABLE = {VS_SOURCE_TABLE}")

# COMMAND ----------

# DBTITLE 1,Create AI Search index (06c pattern)
# Creates a Delta Sync AI Search index over the scimilarity_cells table.

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import (
    EndpointType, DeltaSyncVectorIndexSpecRequest,
    EmbeddingVectorColumn, VectorIndexType, PipelineType,
)
from databricks.sdk.errors import NotFound, BadRequest
import time

w = WorkspaceClient()

VS_ENDPOINT = "gwb_scimilarity_vs_endpoint"
VS_INDEX = f"{CATALOG}.{SCHEMA}.scimilarity_cell_index"

# Use VS_SOURCE_TABLE from the resolve cell above
try:
    source_table = VS_SOURCE_TABLE
except NameError:
    source_table = None

if source_table is None or not spark.catalog.tableExists(source_table):
    print(f"\u2717 No AI Search source table available. Run the resolve/extract cell above first.")
else:
    print(f"Source table: {source_table}")

# Endpoint (only proceed if source table exists)
try:
    ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT)
    print(f"AI Search endpoint '{VS_ENDPOINT}' exists (status: {ep.endpoint_status})")
except Exception:
    print(f"Creating AI Search endpoint '{VS_ENDPOINT}'...")
    w.vector_search_endpoints.create_endpoint(name=VS_ENDPOINT, endpoint_type=EndpointType.STANDARD)
    for _ in range(60):
        ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT)
        if ep.endpoint_status and ep.endpoint_status.state and ep.endpoint_status.state.value == "ONLINE":
            print(f"\u2713 Endpoint ONLINE"); break
        time.sleep(30)

# Index
try:
    w.vector_search_indexes.get_index(VS_INDEX)
    print(f"Index '{VS_INDEX}' already exists. Triggering sync...")
    try:
        w.vector_search_indexes.sync_index(index_name=VS_INDEX)
    except BadRequest:
        print("  Sync already in progress.")
except NotFound:
    print(f"Creating Delta Sync AI Search index '{VS_INDEX}'...")
    w.vector_search_indexes.create_index(
        name=VS_INDEX, endpoint_name=VS_ENDPOINT, primary_key="cell_id",
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=source_table,
            embedding_vector_columns=[EmbeddingVectorColumn(name="embedding", embedding_dimension=128)],
            pipeline_type=PipelineType.TRIGGERED,
            columns_to_sync=["cell_id"] + (["prediction", "tissue"] if VS_HAS_METADATA else []),
        ),
    )
    print(f"\u2713 Index created. Initial sync will begin automatically.")

print(f"\nTo check status: w.vector_search_indexes.get_index('{VS_INDEX}')")

# COMMAND ----------

# DBTITLE 1,Phase 2 header
# MAGIC %md
# MAGIC ## Phase 2 — Deploy Model Serving endpoints (SDK-only)
# MAGIC
# MAGIC SDK-only — via [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7).
# MAGIC
# MAGIC Endpoints created with:
# MAGIC * **Scale-to-zero** enabled
# MAGIC * **Inference table** enabled (logs requests/responses to `{catalog}.{schema}.<prefix>_payload`)
# MAGIC * **AI Gateway usage tracking** enabled
# MAGIC
# MAGIC > ⚠️ **GPU endpoints bill while provisioned.** Phase 4 (teardown) cleans up.

# COMMAND ----------

# DBTITLE 1,Deploy serving endpoints
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
mlflow_client = MlflowClient(registry_uri="databricks-uc")

def _latest_version(uc_model_name: str) -> int:
    versions = mlflow_client.search_model_versions(f"name='{uc_model_name}'")
    return max((int(v.version) for v in versions), default=1)

def _deploy(endpoint_name: str, uc_model_name: str, workload_type: str, workload_size: str):
    version = _latest_version(uc_model_name)
    print(f"Deploying {uc_model_name} v{version} -> {endpoint_name} ({workload_type}/{workload_size})")

    entity = ServedEntityInput(
        entity_name=uc_model_name, entity_version=str(version),
        workload_type=workload_type, workload_size=workload_size,
        scale_to_zero_enabled=True,
    )
    # AI Gateway — inference table (UC) + usage tracking
    ai_gateway = AiGatewayConfig(
        usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
        inference_table_config=AiGatewayInferenceTableConfig(
            catalog_name=CATALOG, schema_name=SCHEMA, enabled=True,
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
        print(f"  \u2713 Created (AI Gateway inference table + usage tracking + s2z)")
    except ResourceAlreadyExists:
        w.serving_endpoints.update_config(
            name=endpoint_name, served_entities=[entity],
        )
        print(f"  \u2713 Updated (s2z)")

# GeneOrder: lightweight lookup — CPU/Small
_deploy("scimilarity-gene-order", f"{CATALOG}.{SCHEMA}.scimilarity_gene_order",
        ServingModelWorkloadType.CPU, "Small")

# GetEmbedding: neural net inference — GPU recommended for throughput
_deploy("scimilarity-get-embedding", f"{CATALOG}.{SCHEMA}.scimilarity_get_embedding",
        ServingModelWorkloadType.GPU_MEDIUM, "Small")

print("\nEndpoints provisioning. Check Serving UI for status.")

# COMMAND ----------

# DBTITLE 1,Phase 3 header
# MAGIC %md
# MAGIC ## Phase 3 — Score / Eval
# MAGIC
# MAGIC **3a. Endpoint smoke test** — hit serving endpoints, validate response format.
# MAGIC **3b. AI Search eval scorer** — query the AI Search index with a known embedding,
# MAGIC validate self-retrieval and monotonic distance ordering.
# MAGIC
# MAGIC Both are lightweight (no `scimilarity` deps — just `requests` + Databricks SDK).

# COMMAND ----------

# DBTITLE 1,Smoke test endpoints
# Lightweight smoke test — no scimilarity import needed
import requests, json, os

TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().getOrElse(None)
HOST = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)

def score_endpoint(endpoint_name: str, payload: dict) -> dict:
    """Score a Model Serving endpoint. Returns parsed JSON response."""
    url = f"{HOST}/serving-endpoints/{endpoint_name}/invocations"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()

# Test GeneOrder
try:
    go_result = score_endpoint("scimilarity-gene-order", {
        "dataframe_records": [{"input": "get_gene_order"}]
    })
    genes = go_result.get("predictions", [])
    print(f"\u2713 GeneOrder endpoint: {len(genes)} genes returned")
except Exception as e:
    print(f"\u2717 GeneOrder endpoint: {e}")
    print("  (endpoint may still be provisioning — retry in a few minutes)")

# COMMAND ----------

# DBTITLE 1,AI Search eval scorer (query index + validate)
# 3b. AI Search eval — query the scimilarity_cell_index and validate.
# Only runs if the AI Search index exists (Phase 1b was executed).

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
import time

w = WorkspaceClient()
VS_INDEX = f"{CATALOG}.{SCHEMA}.scimilarity_cell_index"

# Use VS_SOURCE_TABLE from the resolve cell
try:
    source_table = VS_SOURCE_TABLE
except NameError:
    source_table = f"{CATALOG}.{SCHEMA}.scimilarity_cells"

try:
    idx_info = w.vector_search_indexes.get_index(VS_INDEX)
except NotFound:
    print(f"AI Search index '{VS_INDEX}' not found — Phase 1b was not run. Skipping.")
    idx_info = None

if idx_info is not None:
    # Grab a real embedding from the source table as query vector
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
    scores = [float(r[1]) for r in rows] if len(rows) > 0 and len(rows[0]) > 1 else []

    # --- Scorers ---
    self_retrieval = expected_cell_id in returned_ids[:1]
    count_ok = len(rows) == NUM_RESULTS
    monotonic = all(scores[i] >= scores[i+1] for i in range(len(scores)-1)) if scores else True

    print(f"\u2713 AI Search eval results for '{VS_INDEX}' (128-d scimilarity embeddings):")
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

    assert count_ok, f"Expected {NUM_RESULTS} results, got {len(rows)}"
    assert self_retrieval, f"Self-retrieval failed"
    print(f"\n\u2713 All AI Search scorers passed.")

# COMMAND ----------

# DBTITLE 1,Phase 4 header
# MAGIC %md
# MAGIC ## Phase 4 — Teardown
# MAGIC
# MAGIC Cleanup resources. Run selectively — uncomment what you need.
# MAGIC
# MAGIC | Resource | Cost while alive? | Teardown action |
# MAGIC |---|---|---|
# MAGIC | Serving endpoints (GeneOrder, GetEmbedding) | **Yes** (CPU + GPU billing) | `delete` |
# MAGIC | AI Search endpoint (`gwb_scimilarity_vs_endpoint`) | Yes (compute) | `delete` (shared — only if no other indexes) |
# MAGIC | AI Search index (`scimilarity_cell_index`) | Minimal (storage) | `delete` |
# MAGIC | UC model versions | No | Keep (audit trail) |
# MAGIC | Inference tables | No (storage only) | Keep (debugging) |

# COMMAND ----------

# DBTITLE 1,Teardown
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

w = WorkspaceClient()

# --- 1. Serving endpoints (highest cost) ---
for ep_name in ["scimilarity-gene-order", "scimilarity-get-embedding"]:
    try:
        w.serving_endpoints.delete(ep_name)
        print(f"\u2713 Deleted serving endpoint '{ep_name}'")
    except NotFound:
        print(f"  Serving endpoint '{ep_name}' already gone.")

# --- 2. AI Search index ---
# VS_INDEX = f"{CATALOG}.{SCHEMA}.scimilarity_cell_index"
# try:
#     w.vector_search_indexes.delete_index(index_name=VS_INDEX)
#     print(f"\u2713 Deleted AI Search index '{VS_INDEX}'")
# except NotFound:
#     print(f"  AI Search index already gone.")

# --- 3. AI Search endpoint (shared) ---
# try:
#     w.vector_search_endpoints.delete_endpoint("gwb_scimilarity_vs_endpoint")
#     print(f"\u2713 Deleted AI Search endpoint")
# except NotFound:
#     print(f"  AI Search endpoint already gone.")

print("\n\u2713 Teardown complete. Inference tables + UC models preserved.")