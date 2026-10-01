# Databricks notebook source
# DBTITLE 1,scGPT Download Ground Truth
# MAGIC %md
# MAGIC # scGPT — Ground Truth
# MAGIC
# MAGIC > **STATUS: TODO** — Not yet tested end-to-end. Pending gt_geneformer + oss-002/003 completion.
# MAGIC > Weights live on Google Drive (not HF), which adds download complexity (`gdown`).
# MAGIC
# MAGIC Downloads the [scGPT](https://github.com/bowang-lab/scGPT) whole-human checkpoint
# MAGIC from Google Drive + sample data from Figshare to a UC Volume.
# MAGIC
# MAGIC ### Provenance
# MAGIC
# MAGIC [Genesis Workbench scGPT module](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/scgpt)
# MAGIC → [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7) (`oss-models` skill) → this ground truth notebook.
# MAGIC
# MAGIC **Canonical source:** [`modules/single_cell/scgpt`](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/scgpt)
# MAGIC
# MAGIC ### Module notebooks ([source](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/scgpt/notebooks))
# MAGIC
# MAGIC | Notebook | Purpose |
# MAGIC |----------|---------|
# MAGIC | [`01_register_scgpt.py`](https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scgpt/notebooks/01_register_scgpt.py) | Install deps, download weights from Google Drive, register PyFunc to UC |
# MAGIC | [`02_import_model_gwb.py`](https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scgpt/notebooks/02_import_model_gwb.py) | Import into GWB + deploy endpoint |
# MAGIC | [`03_register_scgpt_perturbation.py`](https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scgpt/notebooks/03_register_scgpt_perturbation.py) | Register perturbation model |
# MAGIC | [`04_import_perturbation_gwb.py`](https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scgpt/notebooks/04_import_perturbation_gwb.py) | Import perturbation model + deploy |
# MAGIC | `utils` | Shared utility functions |
# MAGIC
# MAGIC ## Original upstream repos
# MAGIC
# MAGIC | Resource | URL |
# MAGIC |----------|-----|
# MAGIC | **Code** | [github.com/bowang-lab/scGPT](https://github.com/bowang-lab/scGPT) |
# MAGIC | **Weights (whole-human)** | [Google Drive — Model Zoo](https://drive.google.com/drive/folders/1oWh_-ZRdhtoGQ2Fw24HP41FgLoomVo-y?usp=sharing) |
# MAGIC | **Package** | `scgpt==0.2.4` (PyPI) |
# MAGIC | **Paper** | [Cui et al., Nature Methods 2024](https://www.nature.com/articles/s41592-024-02201-0) |
# MAGIC | **License** | Check scGPT repo |
# MAGIC
# MAGIC ## Model details
# MAGIC
# MAGIC | Detail | Value |
# MAGIC |--------|-------|
# MAGIC | Checkpoint | `best_model.pt` + `args.json` + `vocab.json` (whole-human) |
# MAGIC | Tasks | Embedding, annotation, generation, perturbation prediction |
# MAGIC | Tokenization | Gene-name vocabulary (`vocab.json`) — version-specific |
# MAGIC | GPU requirement | GPU_SMALL (A10G) minimum |
# MAGIC | Key gotcha | Weights on Google Drive (not HF/Zenodo) — `gdown` or manual download |
# MAGIC
# MAGIC ## Estimated download times
# MAGIC
# MAGIC | Asset | Size | Est. time |
# MAGIC |-------|------|-----------|
# MAGIC | Whole-human checkpoint (Google Drive) | ~140 MB | ~2–5 min |
# MAGIC | Sample data (Figshare h5ad) | ~50 MB | ~1–2 min |
# MAGIC | **Total** | **~190 MB** | **~3–7 min** |
# MAGIC
# MAGIC ## How to use
# MAGIC
# MAGIC 1. **If model already in Volume** → Cell below verifies and skips
# MAGIC 2. **If not** → Run the download cells below in this notebook

# COMMAND ----------

# DBTITLE 1,Check Volume for model
# --- Verify scGPT model is in Volume (---
# If not present, run the download cells above
# Source: github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/scgpt

dbutils.widgets.text("catalog", "<catalog>", "Unity Catalog catalog")
dbutils.widgets.text("schema", "skills", "Unity Catalog schema")
dbutils.widgets.text("cache_dir", "scgpt_cache_dir", "Cache dir (volume name)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")

import os

volume_path = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"

# scGPT whole-human checkpoint sentinel: best_model.pt
candidates = [
    (volume_path, "best_model.pt"),
    (os.path.join(volume_path, "scGPT_human"), "best_model.pt"),
    (os.path.join(volume_path, "whole_human"), "best_model.pt"),
]

found = False
for path, sentinel in candidates:
    sentinel_path = os.path.join(path, sentinel)
    if os.path.exists(sentinel_path):
        print(f"\u2713 scGPT found at: {path}")
        print(f"  {sentinel} present")
        for f in sorted(os.listdir(path)):
            kind = "[dir]" if os.path.isdir(os.path.join(path, f)) else "[file]"
            print(f"  {kind} {f}")
        found = True
        break

if not found:
    print(f"\u2717 scGPT NOT found in Volume")
    print(f"  Checked: {[p for p, _ in candidates]}")
    print()
    print("Run the download cells above to download:")
    print("  https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scgpt/notebooks/01_register_scgpt.py")
    print(f"  Set widgets: catalog={CATALOG}, schema={SCHEMA}, cache_dir={CACHE_DIR}")
    print()
    print("Or download manually from Google Drive:")
    print("  https://drive.google.com/drive/folders/1oWh_-ZRdhtoGQ2Fw24HP41FgLoomVo-y")
    print("  Files needed: best_model.pt, args.json, vocab.json")

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

# DBTITLE 1,Install gdown + wget
# MAGIC %pip install -q gdown wget
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Post-restart setup
import os, sys

try:
    os.makedirs("/local_disk0/tmp", exist_ok=True)
    TMP_DIR = "/local_disk0/tmp"
    IS_SERVERLESS = False
except (PermissionError, OSError):
    TMP_DIR = "/tmp"
    IS_SERVERLESS = True

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
cache_full_path = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"
print(f"Compute: {'Serverless' if IS_SERVERLESS else 'Classic'}, Volume: {cache_full_path}")

# COMMAND ----------

# DBTITLE 1,Download scGPT model from Google Drive (adapted from GWB)
# Uses gdown to download the whole-human checkpoint from Google Drive.

import gdown

model_dir = f"{cache_full_path}/models/"
os.makedirs(model_dir, exist_ok=True)

# Sentinel: best_model.pt is the main checkpoint file
model_file_check = os.path.join(model_dir, "best_model.pt")
if os.path.exists(model_file_check) and os.path.getsize(model_file_check) > 0:
    print(f"\u2713 Model already at {model_file_check} ({os.path.getsize(model_file_check)} bytes), skipping download")
    # Walk to find the actual dir containing best_model.pt (gdown may nest)
    for root, dirs, files in os.walk(model_dir):
        if "best_model.pt" in files:
            model_dir = root
            break
else:
    # Google Drive folder ID for whole-human (recommended) checkpoint
    GDRIVE_FOLDER_ID = "1oWh_-ZRdhtoGQ2Fw24HP41FgLoomVo-y"
    print(f"Downloading scGPT whole-human checkpoint from Google Drive...")
    print(f"  Folder ID: {GDRIVE_FOLDER_ID}")
    print(f"  Destination: {model_dir}")
    gdown_return = gdown.download_folder(id=GDRIVE_FOLDER_ID, output=f"{model_dir}/")
    model_dir = gdown_return[0].rsplit('/', 1)[0]
    print(f"\u2713 Download complete.")

print(f"Model dir: {model_dir}")
for f in sorted(os.listdir(model_dir)):
    size = os.path.getsize(os.path.join(model_dir, f)) / 1e6
    print(f"  {f}  ({size:.1f} MB)")

# COMMAND ----------

# DBTITLE 1,Download sample data from Figshare (adapted from GWB)
import wget as wget_lib

data_dir = f"{cache_full_path}/data"
os.makedirs(data_dir, exist_ok=True)
file_path = f"{data_dir}/file.h5ad"

if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
    size = os.path.getsize(file_path) / 1e6
    print(f"\u2713 Sample data already at {file_path} ({size:.1f} MB), skipping")
else:
    FIGSHARE_URL = "https://api.figshare.com/v2/file/download/25717328"
    print(f"Downloading sample data from {FIGSHARE_URL}...")
    wget_lib.download(FIGSHARE_URL, str(file_path))
    print(f"\u2713 Downloaded: {file_path}")

# COMMAND ----------

# DBTITLE 1,Verify
# Verify model checkpoint
assert os.path.exists(os.path.join(model_dir, "best_model.pt")), "Missing best_model.pt"
assert os.path.exists(os.path.join(model_dir, "args.json")), "Missing args.json"
assert os.path.exists(os.path.join(model_dir, "vocab.json")), "Missing vocab.json"

print(f"\u2713 scGPT checkpoint verified at: {model_dir}")
print(f"  best_model.pt, args.json, vocab.json all present")

if os.path.exists(file_path):
    size = os.path.getsize(file_path) / 1e6
    print(f"\u2713 Sample data: {file_path} ({size:.1f} MB)")

# COMMAND ----------

# DBTITLE 1,scGPT Register/Deploy Ground Truth
import datetime

manifest = f"""model:
  name: scgpt
  variant: whole-human
  code_url: https://github.com/bowang-lab/scGPT
  weights_url: https://drive.google.com/drive/folders/1oWh_-ZRdhtoGQ2Fw24HP41FgLoomVo-y
  paper: Cui et al., Nature Methods 2024
  package: scgpt==0.2.4
  license: check_repo
  reviewed_at: {datetime.date.today().isoformat()}
adapted_from:
  genesis_workbench: modules/single_cell/scgpt/notebooks/01_register_scgpt.py
  url: https://github.com/databricks-industry-solutions/genesis-workbench/blob/main/modules/single_cell/scgpt/notebooks/01_register_scgpt.py
weights:
  location: {model_dir}
sample_data:
  location: {file_path}
  source_url: https://api.figshare.com/v2/file/download/25717328
runtime:
  download_compute: {'serverless_cpu' if IS_SERVERLESS else 'classic_cpu'}
  register_compute: gpu_required
"""

manifest_path = f"{model_dir}/provenance_manifest.yaml"
with open(manifest_path, "w") as f:
    f.write(manifest)
print("Provenance manifest:", manifest_path)
print(manifest)

%md
# scGPT — Register, Deploy and Score (Standalone)

**Standalone** register + deploy for scGPT (whole-human embedding model),
via [GWB](https://github.com/databricks-industry-solutions/genesis-workbench/tree/main/modules/single_cell/scgpt) + [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7).

| Phase | What | Cells |
|-------|------|-------|
| **1. Register** | Wrap `TransformerModelWrapper` PyFunc, `input_example` + `signature`, register to UC | 3–9 |
| **2. Deploy** | GPU Model Serving endpoint with **inference table** + **AI Gateway** + scale-to-zero | 10–11 |
| **3. Score / Eval** | Endpoint smoke test | 12–13 |
| **4. Teardown** | Delete endpoint. Inference table + UC model preserved | 14–15 |



## Model details

| Field | Value |
|-------|-------|
| Source | [bowang-lab/scGPT](https://github.com/bowang-lab/scGPT) — [Nature Methods 2024](https://www.nature.com/articles/s41592-024-02201-0) |
| Weights | [Google Drive Model Zoo](https://drive.google.com/drive/folders/1oWh_-ZRdhtoGQ2Fw24HP41FgLoomVo-y) (whole-human) |
| Package | `scgpt==0.2.4` (PyPI) |
| GPU tier | `GPU_SMALL` (A10G) — `flash-attn` requires GPU at import |
| Input | `adata_sparsematrix` + `adata_obs` + `adata_var` (JSON orient=split) |
| Params | `need_preprocess`, `subset_hvg` (1200), `binning` (51), etc. |
| Output | Gene embeddings dict (`{gene_name: [float, ...]}`) |
| Key deps | `scgpt==0.2.4`, `torch>=2.0.0`, `flash-attn`, `scanpy` |

## Prerequisite

Model in UC Volume — see the download cells above (this notebook is combined).

# COMMAND ----------

# DBTITLE 1,Configuration
import os, sys

dbutils.widgets.text("catalog", "<catalog>", "Unity Catalog catalog")
dbutils.widgets.text("schema", "skills", "Unity Catalog schema")
dbutils.widgets.text("cache_dir", "scgpt_cache_dir", "Cache dir")
dbutils.widgets.text("endpoint_name", "scgpt-embedder", "Serving endpoint name")
dbutils.widgets.dropdown("run_go", "false", ["false", "true"], "Run gate (deploy costs real money)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
RUN_GO = dbutils.widgets.get("run_go") == "true"

BASE_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"
model_dir = f"{BASE_DIR}/models/"
data_file = f"{BASE_DIR}/data/file.h5ad"

assert os.path.exists(f"{model_dir}/best_model.pt"), (
    f"Checkpoint not found at {model_dir}. Run the download cells above first."
)
print(f"Catalog:  {CATALOG} | Schema: {SCHEMA}")
print(f"Model:    {model_dir}")
print(f"Endpoint: {ENDPOINT_NAME}")
print(f"RUN_GO:   {RUN_GO}")

# COMMAND ----------

# DBTITLE 1,Phase 1 header
# MAGIC %md
# MAGIC ## Phase 1 — Register scGPT to Unity Catalog
# MAGIC
# MAGIC `TransformerModelWrapper` PyFunc — via [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7).
# MAGIC Includes `input_example` + `signature` so the MLflow UI “Test” button works.
# MAGIC
# MAGIC > **GPU required at import** — `flash-attn` needs CUDA to load.

# COMMAND ----------

# DBTITLE 1,Install registration deps
# MAGIC %pip install -q scgpt==0.2.4 flash-attn scanpy==1.11.2 gdown \
# MAGIC     torch mlflow==2.22.0 scipy numpy pandas
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Restore widgets + define PyFunc
import os, sys, json
import numpy as np
import pandas as pd
import scipy.sparse
import torch
import mlflow
import scanpy
from scanpy import AnnData
from scgpt.tasks import GeneEmbedding
from scgpt.tokenizer.gene_tokenizer import GeneVocab
from scgpt.model import TransformerModel
from scgpt.preprocess import Preprocessor
from typing import Dict

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
CACHE_DIR = dbutils.widgets.get("cache_dir")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
RUN_GO = dbutils.widgets.get("run_go") == "true"

BASE_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/{CACHE_DIR}"
model_dir = f"{BASE_DIR}/models/"
data_file = f"{BASE_DIR}/data/file.h5ad"

model_config_file = f"{model_dir}/args.json"
model_file = f"{model_dir}/best_model.pt"
vocab_file = f"{model_dir}/vocab.json"


class TransformerModelWrapper(mlflow.pyfunc.PythonModel):
    """scGPT gene embedding model. Via PR #7.
    Input: adata_sparsematrix + adata_obs + adata_var (JSON orient=split).
    Output: gene embeddings dict {gene_name: embedding_vector}.
    """
    def __init__(self, special_tokens=["<pad>", "<cls>", "<eoc>"]):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.special_tokens = special_tokens

    def load_context(self, context):
        self.model_file = context.artifacts["model_file"]
        self.model_config_file = context.artifacts["model_config_file"]
        self.vocab_file = context.artifacts["vocab_file"]

        self.vocab = GeneVocab.from_file(self.vocab_file)
        for s in self.special_tokens:
            if s not in self.vocab:
                self.vocab.append_token(s)
        self.gene2idx = self.vocab.get_stoi()
        self.ntokens = len(self.vocab)

        with open(self.model_config_file, "r") as f:
            self.model_configs = json.load(f)

        self.embsize = self.model_configs["embsize"]
        self.nhead = self.model_configs["nheads"]
        self.d_hid = self.model_configs["d_hid"]
        self.nlayers = self.model_configs["nlayers"]
        self.n_layers_cls = self.model_configs["n_layers_cls"]
        self.pad_value = self.model_configs["pad_value"]
        self.mask_value = self.model_configs["mask_value"]
        self.n_bins = self.model_configs["n_bins"]
        self.n_hvg = self.model_configs["n_hvg"]

        self._loaded_model = TransformerModel(
            ntoken=self.ntokens, d_model=self.embsize, nhead=self.nhead,
            d_hid=self.d_hid, nlayers=self.nlayers, vocab=self.vocab,
            pad_value=self.pad_value, n_input_bins=self.n_bins,
        )
        try:
            self._loaded_model.load_state_dict(torch.load(self.model_file, map_location=self.device))
        except Exception:
            model_dict = self._loaded_model.state_dict()
            pretrained_dict = torch.load(self.model_file, map_location=self.device)
            pretrained_dict = {k: v for k, v in pretrained_dict.items()
                               if k in model_dict and v.shape == model_dict[k].shape}
            model_dict.update(pretrained_dict)
            self._loaded_model.load_state_dict(model_dict)

        self._loaded_model.to(self.device).eval()
        print(f"scGPT model ready on {self.device} (embsize={self.embsize}, vocab={self.ntokens})")

    def preprocess(self, context, input_dataframe=None, params=None):
        params = params or {}
        adata_sparsematrix = scipy.sparse.csr_matrix(input_dataframe['adata_sparsematrix'][0])
        adata_obs = pd.read_json(input_dataframe['adata_obs'][0], orient='split')
        adata_var = pd.read_json(input_dataframe['adata_var'][0], orient='split')
        loaded_data = scanpy.AnnData(adata_sparsematrix, obs=adata_obs, var=adata_var)
        loaded_data.obs["celltype"] = loaded_data.obs.get("final_annotation", pd.Series("unknown")).astype(str)

        preprocessor = Preprocessor(
            use_key=params.get("use_key", "X"),
            filter_gene_by_counts=params.get("filter_gene_by_counts", 3),
            filter_cell_by_counts=params.get("filter_cell_by_counts", False),
            normalize_total=params.get("normalize_total", 1e4),
            result_normed_key="X_normed",
            log1p=params.get("log1p", False),
            result_log1p_key="X_log1p",
            subset_hvg=params.get("subset_hvg", self.n_hvg),
            hvg_flavor=params.get("hvg_flavor", "cell_ranger"),
            binning=params.get("binning", self.n_bins),
            result_binned_key="X_binned",
        )
        preprocessor(loaded_data, batch_key="batch" if "batch" in loaded_data.obs else None)
        return loaded_data

    def predict(self, context, model_input=None, params=None):
        params = params or {}
        if params.get("need_preprocess", True):
            preprocessed = self.preprocess(context, input_dataframe=model_input, params=params)
        else:
            preprocessed = model_input

        gene_embeddings = self._loaded_model.encoder(torch.tensor(list(self.gene2idx.values()), dtype=torch.long).to(self.device))
        gene_embeddings = gene_embeddings.detach().cpu().numpy()

        filtered = {
            gene: gene_embeddings[i]
            for i, gene in enumerate(self.gene2idx.keys())
            if gene in preprocessed.var.index.tolist()
        }
        return {k: v.tolist() for k, v in filtered.items()}


print("TransformerModelWrapper defined.")

# COMMAND ----------

# DBTITLE 1,Dry-load + build input_example + infer signature
from mlflow.pyfunc import PythonModelContext
from mlflow.models import infer_signature

# Dry-load
artifacts = {"model_file": model_file, "model_config_file": model_config_file, "vocab_file": vocab_file}
ctx = PythonModelContext(artifacts=artifacts, model_config={})

tf_model = TransformerModelWrapper()
tf_model.load_context(ctx)
print(f"\u2713 scGPT loaded: embsize={tf_model.embsize}, vocab={tf_model.ntokens}")

# Build input_example from sample data
adata = scanpy.read(str(data_file), cache=True)
adata_subset = adata[:10, :1500]  # small subset for example

input_example = pd.DataFrame({
    'adata_sparsematrix': [adata_subset.X.toarray().tolist()],
    'adata_obs': [adata_subset.obs.to_json(orient='split')],
    'adata_var': [adata_subset.var.to_json(orient='split')],
})

default_params = {
    "need_preprocess": True, "data_is_raw": False,
    "use_key": "X", "filter_gene_by_counts": 3, "filter_cell_by_counts": False,
    "normalize_total": 1e4, "log1p": False, "subset_hvg": 1200,
    "hvg_flavor": "cell_ranger", "binning": 51,
}

output_example = tf_model.predict(ctx, model_input=input_example, params=default_params)
print(f"\u2713 Dry predict OK: {len(output_example)} gene embeddings returned")

# Infer signature
signature = infer_signature(input_example, output_example, params=default_params)
print(f"\u2713 Signature inferred")

# COMMAND ----------

# DBTITLE 1,Log + register scGPT to UC
from databricks.sdk import WorkspaceClient

def set_mlflow_experiment(tag):
    w = WorkspaceClient()
    base = "Shared/dbx_genesis_workbench_models"
    w.workspace.mkdirs(f"/Workspace/{base}")
    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_tracking_uri("databricks")
    return mlflow.set_experiment(f"/{base}/{tag}")

experiment = set_mlflow_experiment("scgpt_genesis_workbench_modules")
registered_model_name = f"{CATALOG}.{SCHEMA}.scgpt"

with mlflow.start_run(run_name="scgpt_embedder", experiment_id=experiment.experiment_id) as run:
    mlflow.pyfunc.log_model(
        artifact_path="scgpt",
        python_model=tf_model,
        artifacts=artifacts,
        signature=signature,
        input_example=(input_example, default_params),
        pip_requirements=[
            "scgpt==0.2.4", "flash-attn", "torch", "scanpy",
            "scipy", "numpy", "pandas", "mlflow==2.22.0",
        ],
        registered_model_name=registered_model_name,
    )
    print(f"\u2713 Registered {registered_model_name} (run {run.info.run_id})")

# COMMAND ----------

# DBTITLE 1,Phase 2 header
# MAGIC %md
# MAGIC ## Phase 2 — Deploy GPU Model Serving endpoint (SDK-only)
# MAGIC
# MAGIC SDK-only — via [PR #7](https://github.com/databricks-industry-solutions/hls-skills/pull/7). Endpoint created with:
# MAGIC * **Scale-to-zero** enabled
# MAGIC * **Inference table** enabled
# MAGIC * **AI Gateway usage tracking** enabled
# MAGIC
# MAGIC > ⚠️ **GPU endpoints bill while provisioned.** Phase 4 (teardown) cleans up.
# MAGIC > `flash-attn` requires GPU at import — only GPU_SMALL or higher works.

# COMMAND ----------

# DBTITLE 1,Deploy scGPT serving endpoint
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

    uc_model = f"{CATALOG}.{SCHEMA}.scgpt"
    version = max(int(v.version) for v in mc.search_model_versions(f"name='{uc_model}'"))

    entity = ServedEntityInput(
        entity_name=uc_model, entity_version=str(version),
        workload_type=ServingModelWorkloadType.GPU_SMALL, workload_size="Small",
        scale_to_zero_enabled=True,
    )
    # AI Gateway — inference table (UC) + usage tracking
    ai_gateway = AiGatewayConfig(
        usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
        inference_table_config=AiGatewayInferenceTableConfig(
            catalog_name=CATALOG, schema_name=SCHEMA, enabled=True,
            table_name_prefix=ENDPOINT_NAME.replace("-", "_"),
        ),
    )

    try:
        w.serving_endpoints.create(
            name=ENDPOINT_NAME,
            config=EndpointCoreConfigInput(
                name=ENDPOINT_NAME,
                served_entities=[entity],
            ),
            ai_gateway=ai_gateway,
        )
        print(f"\u2713 Endpoint '{ENDPOINT_NAME}' created (GPU_SMALL, v{version})")
    except ResourceAlreadyExists:
        w.serving_endpoints.update_config(
            name=ENDPOINT_NAME, served_entities=[entity],
        )
        print(f"\u2713 Endpoint '{ENDPOINT_NAME}' updated (v{version})")

    print(f"  Inference table: {CATALOG}.{SCHEMA}.{ENDPOINT_NAME.replace('-','_')}_payload")
    print(f"  Scale-to-zero:   enabled")
    print(f"  AI Gateway:      inference table + usage tracking on")

# COMMAND ----------

# DBTITLE 1,Phase 3 header
# MAGIC %md
# MAGIC ## Phase 3 — Score / Eval
# MAGIC
# MAGIC Lightweight endpoint smoke test (no `scgpt`/`flash-attn` deps).

# COMMAND ----------

# DBTITLE 1,Smoke test scGPT endpoint
import requests, json

if not RUN_GO:
    print("run-gate off; set run_go=true to test. Skipping.")
else:
    TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().getOrElse(None)
    HOST = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)

    # Minimal synthetic payload (10 cells x 100 genes)
    import numpy as np
    rng = np.random.default_rng(42)
    fake_expr = rng.poisson(2.0, size=(10, 100)).astype(float).tolist()
    fake_obs = json.dumps({"columns": ["batch", "final_annotation"],
                           "index": [str(i) for i in range(10)],
                           "data": [["batch0", "T cell"]] * 10})
    fake_var = json.dumps({"columns": ["gene_name"],
                           "index": [f"GENE{i}" for i in range(100)],
                           "data": [[f"GENE{i}"]] * 100})

    payload = {
        "dataframe_records": [{
            "adata_sparsematrix": fake_expr,
            "adata_obs": fake_obs,
            "adata_var": fake_var,
        }],
        "params": {"need_preprocess": "True", "subset_hvg": "100", "binning": "51"},
    }

    url = f"{HOST}/serving-endpoints/{ENDPOINT_NAME}/invocations"
    resp = requests.post(
        url, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json=payload, timeout=300,
    )

    if resp.ok:
        result = resp.json()
        preds = result.get("predictions", result)
        if isinstance(preds, dict):
            print(f"\u2713 scGPT endpoint OK: {len(preds)} gene embeddings returned")
            first_key = list(preds.keys())[0]
            print(f"  Sample: {first_key} -> {preds[first_key][:5]}...")
        else:
            print(f"\u2713 Response: {json.dumps(result)[:500]}")
    else:
        print(f"\u2717 Endpoint error {resp.status_code}: {resp.text[:500]}")

# COMMAND ----------

# DBTITLE 1,Phase 4 header
# MAGIC %md
# MAGIC ## Phase 4 — Teardown
# MAGIC
# MAGIC | Resource | Cost while alive? | Action |
# MAGIC |---|---|---|
# MAGIC | Serving endpoint | **Yes** (GPU billing) | `delete` |
# MAGIC | UC model versions | No | Keep |
# MAGIC | Inference table | No (storage) | Keep |

# COMMAND ----------

# DBTITLE 1,Teardown
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

w = WorkspaceClient()

try:
    _ep = dbutils.widgets.get("endpoint_name")
except Exception:
    _ep = "scgpt-embedder"

try:
    w.serving_endpoints.delete(_ep)
    print(f"\u2713 Deleted serving endpoint '{_ep}'")
except NotFound:
    print(f"  Serving endpoint '{_ep}' already gone.")

print("\n\u2713 Teardown complete. Inference table + UC model preserved.")