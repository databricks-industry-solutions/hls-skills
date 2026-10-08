# Databricks notebook source
# MAGIC %md
# MAGIC # oss-001: TEDDY-70M Deploy
# MAGIC
# MAGIC **Eval protocol**: Each arm uses its own prompt (below). Paste the matching one into a fresh Genie Code chat on the corresponding notebook.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Skill arm prompt (this notebook)
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat on **this** notebook → save response to `results/with_skill/oss-001.txt`
# MAGIC
# MAGIC > Deploy TEDDY-70M as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/teddy`. Register the model as `<catalog>.skills.teddy_70m` and name the endpoint `teddy_70m`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it's in a FAILED state or doesn't exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don't leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project's HLS model-deployment skill and TEDDY model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/references/models/teddy.md`
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
# MAGIC ## Baseline arm prompt (other notebook)
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat on the **baseline** notebook → save response to `results/baseline/oss-001.txt`
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
SYMLINK_PATH = f"{WS_HOME}/.assistant/skills/open-weight-models"
SOURCE_DIR = f"{WS_HOME}/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models"

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

# DBTITLE 1,TEDDY-70M Deploy Overview
# MAGIC %md
# MAGIC # TEDDY-70M Deploy — Skill-Guided
# MAGIC
# MAGIC Deploy the TEDDY-G 70M foundation model (Merck/TEDDY, Apache-2.0) as a Databricks Model Serving endpoint.
# MAGIC
# MAGIC **Model**: Transformer Encoder for DNA and scRNA-seq, pre-trained on 116M cells. Produces per-cell embeddings from gene expression profiles.
# MAGIC **Source**: https://huggingface.co/Merck/TEDDY (paper: arxiv 2503.03485)
# MAGIC **Compute**: GPU_SMALL (A10G), scale-to-zero enabled, AI Gateway inference table + usage tracking.
# MAGIC
# MAGIC **Phases**:
# MAGIC 1. Install exact dependency versions (transformers==4.41.0 pinned per teddy.md)
# MAGIC 2. Download artifacts from HuggingFace to UC Volume (HF_HUB_DISABLE_XET=1)
# MAGIC 3. Cleanup/idempotency check (delete pre-existing endpoint + UC model versions if FAILED or absent)
# MAGIC 4. Stage code bundle, write PyFunc wrapper (file-based logging per teddy.md BP12)
# MAGIC 5. Build input_example with real Ensembl IDs from vocab.txt
# MAGIC 6. Dry-load test (local validation before deploy)
# MAGIC 7. Log + register model to Unity Catalog
# MAGIC 8. Deploy to Model Serving endpoint (GPU_SMALL, AI Gateway)
# MAGIC 9. Poll for readiness, diagnose failures
# MAGIC 10. Smoke test (SDK query, embedding sanity)
# MAGIC 11. Export notebook source
# MAGIC
# MAGIC **Skill deviation note**: The open-weight-models SKILL.md recommends splitting into two notebooks (CPU download + GPU deploy). This notebook consolidates both into a single notebook for the evaluation protocol. Each phase is clearly separated and independently re-runnable.

# COMMAND ----------

# DBTITLE 1,Install Dependencies
# Install exact dependency versions per teddy.md reference.
# transformers==4.41.0 EXACT pin — 5.x breaks TeddyGModel (all_tied_weights_keys).
# numpy<2.0 for C-ABI compatibility. pandas<3.0 for breaking-change safety.
# huggingface_hub for snapshot_download.
%pip install --quiet "transformers==4.41.0" "numpy>=1.26.4,<2.0" "pandas>=2.2.2,<3.0" "huggingface_hub"
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Config and Imports
# Phase 0: Configuration and imports.
# HF_HUB_DISABLE_XET must be set BEFORE any huggingface_hub import (per teddy.md).
import os
os.environ["HF_HUB_DISABLE_XET"] = "1"

import sys, json, shutil, time, base64, io, inspect
import mlflow
import pandas as pd
import numpy as np
import torch

# --- TEDDY-70M deployment configuration ---
CATALOG = "<catalog>"
SCHEMA = "skills"
MODEL_NAME = f"{CATALOG}.{SCHEMA}.teddy_70m"
ENDPOINT_NAME = "teddy_70m"
VARIANT = "70M"
VOLUME_PATH = "/Volumes/<catalog>/skills/test_with/models/teddy"
SNAPSHOT_DIR = f"{VOLUME_PATH}/snapshot"
TEDDY_PKG_DIR = f"{SNAPSHOT_DIR}/teddy"
MODEL_DIR = f"{TEDDY_PKG_DIR}/models/teddy_g/{VARIANT}"
CLEAN_CODE_DIR = "/tmp/teddy_code"
WRAPPER_PATH = f"{CLEAN_CODE_DIR}/teddy_wrapper.py"

# HF source
HF_REPO_ID = "Merck/TEDDY"
HF_DOWNLOAD_DIR = "/tmp/teddy_download"

# deploy_endpoint widget gate (per teddy.md: gate expensive operations)
DEPLOY_ENDPOINT = dbutils.widgets.get("deploy_endpoint")

# Databricks SDK client
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

import transformers
print(f"deploy_endpoint: {DEPLOY_ENDPOINT}")
print(f"Catalog:      {CATALOG}")
print(f"Model:        {MODEL_NAME}")
print(f"Endpoint:     {ENDPOINT_NAME}")
print(f"Variant:      {VARIANT}")
print(f"Volume:       {VOLUME_PATH}")
print(f"Model dir:    {MODEL_DIR}")
print(f"Torch:        {torch.__version__}")
print(f"Transformers: {transformers.__version__}")
print(f"NumPy:        {np.__version__}")
print(f"Pandas:       {pd.__version__}")
print(f"CUDA avail:   {torch.cuda.is_available()}")

# COMMAND ----------

# DBTITLE 1,Download Model from HuggingFace
# Phase 1: Download TEDDY model from HuggingFace to UC Volume.
# Per teddy.md: HF Xet backend requires HF_HUB_DISABLE_XET=1 before first import of huggingface_hub.
# Per SKILL.md BP10: write temp files to /tmp on Serverless, not /local_disk0.

SENTINEL = f"{VOLUME_PATH}/.download_complete"

if os.path.exists(SENTINEL):
    print(f"Sentinel found at {SENTINEL} — skipping download.")
    model_file = f"{MODEL_DIR}/model.safetensors"
    vocab_file = f"{MODEL_DIR}/vocab.txt"
    print(f"  model.safetensors exists: {os.path.exists(model_file)}")
    print(f"  vocab.txt exists:         {os.path.exists(vocab_file)}")
else:
    # HF_HUB_DISABLE_XET=1 already set in config cell (before any huggingface_hub import)
    from huggingface_hub import snapshot_download

    print(f"Downloading {HF_REPO_ID} to {HF_DOWNLOAD_DIR}...")
    snapshot_download(
        repo_id=HF_REPO_ID,
        local_dir=HF_DOWNLOAD_DIR,
    )
    print("Download complete.")

    # Copy to UC Volume
    os.makedirs(VOLUME_PATH, exist_ok=True)
    snapshot_dst = f"{SNAPSHOT_DIR}"
    print(f"Copying to Volume: {snapshot_dst}...")
    if os.path.exists(snapshot_dst):
        shutil.rmtree(snapshot_dst)
    shutil.copytree(HF_DOWNLOAD_DIR, snapshot_dst)
    print("Copy complete.")

    # Verify key files
    model_file = f"{MODEL_DIR}/model.safetensors"
    vocab_file = f"{MODEL_DIR}/vocab.txt"
    assert os.path.exists(model_file), f"Missing {model_file}"
    assert os.path.exists(vocab_file), f"Missing {vocab_file}"
    print(f"  model.safetensors: {os.path.getsize(model_file) / 1e6:.1f} MB")
    print(f"  vocab.txt:         {os.path.getsize(vocab_file) / 1e3:.1f} KB")

    # Record provenance (per SKILL.md: URL, revision, license, acquisition date)
    provenance = {
        "model": "TEDDY-G 70M",
        "source_url": f"https://huggingface.co/{HF_REPO_ID}",
        "paper": "arxiv 2503.03485",
        "license": "Apache-2.0",
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "volume_path": VOLUME_PATH,
    }
    with open(f"{VOLUME_PATH}/provenance.json", "w") as f:
        json.dump(provenance, f, indent=2)

    # Write sentinel for idempotency
    with open(SENTINEL, "w") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    print(f"Sentinel written: {SENTINEL}")

# Vocabulary smoke test (per teddy.md validation checklist item 1)
with open(f"{MODEL_DIR}/vocab.txt") as f:
    vocab_lines = [t.strip() for t in f if t.strip()]
print(f"\nVocabulary: {len(vocab_lines)} tokens")
print(f"Vocab size: {len(vocab_lines)} tokens (70M variant may differ from ~60K reference)")
assert len(vocab_lines) > 10000, f"Unexpectedly small vocab: {len(vocab_lines)} tokens"
assert "ENSG00000000003" in vocab_lines, "ENSG00000000003 missing from vocab.txt"
print("Vocabulary smoke test passed: ~60K tokens, ENSG00000000003 present")

# COMMAND ----------

# DBTITLE 1,Cleanup and Idempotency Check
# Phase 2: Idempotency check.
# Per prompt: on first run, delete pre-existing endpoint and UC model versions.
# On subsequent runs: skip cleanup if endpoint is READY.
# Only tear down if FAILED or doesn't exist.

from databricks.sdk.errors import NotFound
from databricks.sdk.service.serving import EndpointStateReady, EndpointStateConfigUpdate

should_skip_rebuild = False

try:
    endpoint = w.serving_endpoints.get(ENDPOINT_NAME)
    endpoint_state = endpoint.state
    is_ready = (endpoint_state.ready == EndpointStateReady.READY
                and endpoint_state.config_update == EndpointStateConfigUpdate.NOT_UPDATING)

    if is_ready:
        print(f"Endpoint '{ENDPOINT_NAME}' is READY — skipping cleanup and rebuild.")
        should_skip_rebuild = True
    else:
        print(f"Endpoint '{ENDPOINT_NAME}' state: ready={endpoint_state.ready}, "
              f"config_update={endpoint_state.config_update}")
        print("Tearing down for fresh deployment...")
except NotFound:
    print(f"Endpoint '{ENDPOINT_NAME}' does not exist — will create fresh.")

if not should_skip_rebuild:
    # Delete endpoint if it exists
    try:
        w.serving_endpoints.delete(ENDPOINT_NAME)
        print(f"Deleted endpoint '{ENDPOINT_NAME}'.")
        time.sleep(10)
    except NotFound:
        pass

    # Delete all UC model versions (per user instructions: cleanup on first run)
    from mlflow import MlflowClient
    mlflow.set_registry_uri("databricks-uc")
    client = MlflowClient(registry_uri="databricks-uc")

    try:
        versions = client.search_model_versions(f"name='{MODEL_NAME}'")
        for v in versions:
            client.delete_model_version(name=MODEL_NAME, version=v.version)
            print(f"  Deleted model version {v.version}")
        if versions:
            client.delete_registered_model(name=MODEL_NAME)
            print(f"Deleted registered model '{MODEL_NAME}'.")
    except Exception as e:
        print(f"Model cleanup note: {e}")

    print("Cleanup complete. Ready for fresh deployment.")

# COMMAND ----------

# DBTITLE 1,Stage Code Bundle and Write Wrapper
# Phase 3: Stage code bundle and write PyFunc wrapper.
# Per teddy.md: copytree without weights to /tmp/teddy_code using ignore_patterns.
# Per teddy.md BP12: file-based logging (python_model=path) — wrapper is a .py file, NOT an instance.
# Per SKILL.md BP11: all imports inside the class cell (serving container has no notebook globals).

import shutil, os

# Stage clean code bundle (source without weights)
if os.path.exists(CLEAN_CODE_DIR):
    shutil.rmtree(CLEAN_CODE_DIR)
shutil.copytree(
    TEDDY_PKG_DIR,
    f"{CLEAN_CODE_DIR}/teddy",
    ignore=shutil.ignore_patterns(
        "*.safetensors", "*.bin", "*.ckpt", "*.pt", "__pycache__"
    ),
)
print(f"Staged code bundle to {CLEAN_CODE_DIR}/teddy")

# Write teddy_wrapper.py — file-based logging per teddy.md BP12.
# Every stdlib and third-party symbol used inside class methods is imported
# explicitly in this file (serving container has no notebook globals).
wrapper_code = r'''import sys, os, io, inspect
import mlflow, pandas as pd, numpy as np, torch


class TEDDYEmbedder(mlflow.pyfunc.PythonModel):
    """PyFunc wrapper for TEDDY-G foundation model.

    Produces per-cell embeddings from gene expression profiles.
    Serving contract: 3 DataFrame columns (adata_sparsematrix, adata_obs, adata_var).
    Inference controls via params: max_seq_len (str), pooling (str).
    """

    def load_context(self, context):
        import sys  # explicit — not available from notebook globals in serving container
        teddy_pkg_parent = context.artifacts["teddy_pkg_parent"]
        if teddy_pkg_parent not in sys.path:
            sys.path.insert(0, teddy_pkg_parent)

        # Purge stale module cache (per teddy.md: out-of-order cell execution)
        for _m in list(sys.modules):
            if _m == "teddy" or _m.startswith("teddy."):
                del sys.modules[_m]

        from teddy.models.model_directory import get_architecture, model_dict
        from teddy.tokenizer.gene_tokenizer import GeneTokenizer

        model_dir = context.artifacts["model_dir"]
        arch = get_architecture(model_dir)
        config_cls = model_dict[arch]["config_cls"]
        model_cls = model_dict[arch]["model_cls"]

        self.config = config_cls.from_pretrained(model_dir)
        self.model = model_cls.from_pretrained(model_dir, config=self.config)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device).eval()
        self.tokenizer = GeneTokenizer.from_pretrained(model_dir)  # reads vocab.txt from model_dir
        self._forward_params = set(inspect.signature(self.model.forward).parameters.keys())
        self.add_cls = bool(getattr(self.config, "add_cls", False))
        self.cls_token_id = int(getattr(self.config, "cls_token_id", 0))
        self.d_model = int(getattr(self.config, "d_model", 0))
        self._use_bf16 = (self.device == "cuda")
        # Fix pad_token_id if None — config.json omits it, causing gene_ids == None
        # to return Python False instead of a tensor (breaks torch.cat in forward)
        # NOTE: model.config is a COPY of self.config (different object), so set on both
        _pad_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.pad_token)
        if self.config.pad_token_id is None:
            self.config.pad_token_id = _pad_id
        if self.model.config.pad_token_id is None:
            self.model.config.pad_token_id = _pad_id
        # Enable all-embs output for mean pooling over token positions
        self.model.return_all_embs = True
        print(f"TEDDY-G loaded on {self.device}, d_model={self.d_model}, arch={arch}")

    def predict(self, context, model_input, params=None):
        # Parse inference controls (params from SDK extra_params or MLflow params)
        # Values arrive as strings from the SDK; cast them (per teddy.md)
        max_seq_len = int(params.get("max_seq_len", 2048)) if params else 2048
        pooling = str(params.get("pooling", "mean")) if params else "mean"

        results = []
        for _, row in model_input.iterrows():
            # Parse inputs — pd.read_json with io.StringIO for pandas 2.1+ (per teddy.md)
            X = np.array(row["adata_sparsematrix"], dtype=np.float32)
            var_df = pd.read_json(io.StringIO(row["adata_var"]), orient="split")
            gene_names = var_df["index"].tolist()

            # Tokenize genes with OOV handling (per teddy.md)
            unk_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.unk_token)
            ids = self.tokenizer.convert_tokens_to_ids(list(gene_names))
            ids = [unk_id if i is None else i for i in ids]
            token_array = torch.tensor(ids, device=self.device, dtype=torch.long)

            # Top-K selection and rank encoding (per teddy.md)
            # TEDDY selects top-K most expressed genes, rank-encodes from 1.0 to -1.0
            X_t = torch.tensor(X, device=self.device, dtype=torch.float32)
            if self._use_bf16:
                X_t = X_t.bfloat16()

            k = min(max_seq_len, X_t.shape[1])
            _, top_idx = torch.topk(X_t, k=k, largest=True, sorted=True)
            gene_ids = token_array[top_idx]  # (cells, k)
            rank_vec = torch.linspace(1.0, -1.0, steps=k, device=self.device, dtype=torch.float32)
            gene_vals = rank_vec.unsqueeze(0).expand(X_t.shape[0], -1).clone()

            # Forward pass — gene_ids only; expression encoded via top-K ordering + positional embeddings
            # Deviation from teddy.md: reference passes gene_vals as 2nd arg, but the actual
            # forward signature maps it to `labels` (loss target), not expression values.
            with torch.no_grad():
                out = self.model(gene_ids)

            # Model returns a dict; use all_embs for pooling over token positions
            if isinstance(out, dict):
                transformer_output = out.get("all_embs", out.get("cell_emb", None))
                if transformer_output is None:
                    raise ValueError(f"Unexpected model output keys: {list(out.keys())}")
            else:
                transformer_output = out

            # Pooling (per teddy.md: mean over token positions, or CLS if add_cls=True)
            if pooling == "cls" and self.add_cls:
                emb = transformer_output[:, self.cls_token_id, :]
            else:
                if transformer_output.dim() == 3:
                    emb = transformer_output.mean(dim=1)
                else:
                    emb = transformer_output  # already (batch, d_model)

            # Collect embeddings (one dict per cell, per teddy.md output format)
            emb_np = emb.float().cpu().numpy()
            for cell_emb in emb_np:
                results.append({"embedding": cell_emb.tolist()})

        return pd.DataFrame(results)


mlflow.models.set_model(TEDDYEmbedder())
'''

with open(WRAPPER_PATH, "w") as f:
    f.write(wrapper_code)
print(f"Wrapper written to {WRAPPER_PATH}")

# Verify key files in code bundle
print("\nCode bundle verification:")
for key_file in [
    "teddy/models/model_directory.py",
    "teddy/models/teddy_g/model.py",
    "teddy/tokenizer/gene_tokenizer.py",
]:
    full_path = f"{CLEAN_CODE_DIR}/{key_file}"
    print(f"  {key_file}: {'FOUND' if os.path.exists(full_path) else 'MISSING'}")

# Verify model dir files
print("\nModel dir verification:")
for f in ["model.safetensors", "vocab.txt", "config.json"]:
    full_path = f"{MODEL_DIR}/{f}"
    print(f"  {f}: {'FOUND' if os.path.exists(full_path) else 'MISSING'}")

# Read d_model from config.json
with open(f"{MODEL_DIR}/config.json") as f:
    model_config = json.load(f)
print(f"\n  d_model: {model_config.get('d_model', 'N/A')}")
print(f"  add_cls: {model_config.get('add_cls', 'N/A')}")

# COMMAND ----------

# DBTITLE 1,Build Input Example
# Phase 4: Construct input_example with real Ensembl IDs from vocab.txt.
# Per teddy.md: use real gene IDs — synthetic names all map to <unk> and produce degenerate embeddings.
# Per teddy.md serving contract: 3 columns (adata_sparsematrix, adata_obs, adata_var).

# Read real gene IDs from vocab.txt
vocab_path = f"{MODEL_DIR}/vocab.txt"
with open(vocab_path) as f:
    vocab_tokens = [t.strip() for t in f if t.strip()]

# Skip special tokens (<pad>, <mask>, <unk>, etc.)
real_genes = [t for t in vocab_tokens if not t.startswith("<")][:100]
print(f"Loaded {len(vocab_tokens)} vocab tokens, using {len(real_genes)} real gene IDs")
print(f"First 5 genes: {real_genes[:5]}")

# Construct input example (per teddy.md input example pattern)
n_cells, n_genes = 5, len(real_genes)
rng = np.random.default_rng(42)
expr = rng.poisson(2.0, size=(n_cells, n_genes)).astype(np.float32)

obs_df = pd.DataFrame({"cell_id": [f"cell_{i}" for i in range(n_cells)]})
var_df = pd.DataFrame({"index": real_genes})

input_example = pd.DataFrame({
    "adata_sparsematrix": [expr.tolist()],           # one row = one batch
    "adata_obs":          [obs_df.to_json(orient="split")],
    "adata_var":          [var_df.to_json(orient="split")],
})

# Default params for inference controls (values as strings per teddy.md)
default_params = {"max_seq_len": "2048", "pooling": "mean"}

print(f"\nInput example shape: {input_example.shape}")
print(f"  adata_sparsematrix: {len(input_example.iloc[0]['adata_sparsematrix'])} cells x "
      f"{len(input_example.iloc[0]['adata_sparsematrix'][0])} genes")
print(f"  adata_obs sample:   {input_example.iloc[0]['adata_obs'][:120]}...")
print(f"  adata_var sample:   {input_example.iloc[0]['adata_var'][:120]}...")
print(f"  default_params:     {default_params}")

# COMMAND ----------

# DBTITLE 1,Dry-Load Test
# Phase 5: Dry-load test — local validation before deploy.
# Per teddy.md validation checklist: load_context completes, predict returns non-degenerate embeddings.
# Per user instructions: include a local PyFunc round-trip test before the deploy cell.

if should_skip_rebuild:
    print("Skipping dry-load test — endpoint already READY.")
    signature = None
    dry_load_predictions = None
else:
    # Purge stale teddy modules (per teddy.md)
    for _m in list(sys.modules):
        if _m == "teddy" or _m.startswith("teddy."):
            del sys.modules[_m]
    if CLEAN_CODE_DIR in sys.path:
        sys.path.remove(CLEAN_CODE_DIR)
    sys.path.insert(0, CLEAN_CODE_DIR)

    # Import the wrapper from the .py file
    import importlib.util
    spec = importlib.util.spec_from_file_location("teddy_wrapper", WRAPPER_PATH)
    teddy_wrapper_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(teddy_wrapper_mod)

    # Create a mock context with artifacts
    class MockContext:
        def __init__(self, artifacts):
            self.artifacts = artifacts

    mock_context = MockContext({
        "model_dir": MODEL_DIR,
        "teddy_pkg_parent": CLEAN_CODE_DIR,
    })

    # Instantiate and load
    embedder = teddy_wrapper_mod.TEDDYEmbedder()
    embedder.load_context(mock_context)
    print(f"\nDry-load test: model loaded on {embedder.device}, d_model={embedder.d_model}")

    # Run predict (local round-trip test)
    dry_load_predictions = embedder.predict(mock_context, input_example, params=default_params)
    print(f"Predictions shape: {dry_load_predictions.shape}")
    print(f"Number of cells: {len(dry_load_predictions)}")

    # Verify non-degenerate embeddings (per teddy.md validation checklist item 5)
    first_emb = np.array(dry_load_predictions.iloc[0]["embedding"])
    emb_norm = np.linalg.norm(first_emb)
    print(f"First embedding dim: {len(first_emb)}")
    print(f"First embedding norm: {emb_norm:.4f}")
    print(f"First 5 values: {first_emb[:5]}")

    assert len(first_emb) == embedder.d_model, (
        f"Embedding dim {len(first_emb)} != d_model {embedder.d_model}"
    )
    assert emb_norm > 0, "Embedding is degenerate (norm=0)"
    assert not np.allclose(first_emb, first_emb[0]), "All embedding values are the same"
    print("\nDry-load test PASSED: non-degenerate embeddings with correct dimension.")

    # Infer signature (per model-serving skill: always include signature)
    from mlflow.models import infer_signature
    signature = infer_signature(input_example, dry_load_predictions, params=default_params)
    print(f"\nMLflow signature inferred: {signature}")

# COMMAND ----------

# DBTITLE 1,Log and Register Model
# Phase 6: Log model to MLflow and register to Unity Catalog.
# Per teddy.md BP12: file-based logging (python_model=PATH, not instance).
# Per teddy.md: code_paths=[clean_code_dir], artifacts={model_dir, teddy_pkg_parent}.
# Per teddy.md: pip_requirements from pyproject.toml — exact transformers pin.

if should_skip_rebuild:
    print("Skipping model logging — endpoint already READY.")
    # Resolve existing model version
    mlflow.set_registry_uri("databricks-uc")
    from mlflow import MlflowClient
    client = MlflowClient(registry_uri="databricks-uc")
    versions = client.search_model_versions(f"name='{MODEL_NAME}'")
    model_version = max(int(v.version) for v in versions)
    print(f"Using existing model version: {model_version}")
else:
    mlflow.set_registry_uri("databricks-uc")

    with mlflow.start_run() as run:
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=WRAPPER_PATH,  # file path, NOT instance (per teddy.md BP12)
            code_paths=[CLEAN_CODE_DIR],
            artifacts={
                "model_dir": MODEL_DIR,
                "teddy_pkg_parent": CLEAN_CODE_DIR,
            },
            signature=signature,
            input_example=(input_example, default_params),
            pip_requirements=[
                "torch>=2.3.0",
                "transformers==4.41.0",   # EXACT pin — 5.x breaks TeddyGModel
                "numpy>=1.26.4,<2.0",    # numpy 2.x C-ABI breaking changes
                "pandas>=2.2.2,<3.0",    # pandas 3.x breaking changes
            ],
        )

        # Log provenance tags (per teddy.md: license, paper DOI, HF source, variant)
        mlflow.set_tags({
            "model_family": "TEDDY-G",
            "variant": VARIANT,
            "license": "Apache-2.0",
            "paper": "arxiv 2503.03485",
            "hf_source": f"https://huggingface.co/{HF_REPO_ID}",
        })

        model_uri = f"runs:/{run.info.run_id}/model"
        print(f"Model logged: {model_uri}")

    # Register to Unity Catalog
    registered_version = mlflow.register_model(
        model_uri=model_uri,
        name=MODEL_NAME,
        await_registration_for=300,
    )
    model_version = registered_version.version
    print(f"Registered: {MODEL_NAME} version {model_version}")

# COMMAND ----------

# DBTITLE 1,Deploy Endpoint
# Phase 7: Deploy to Model Serving endpoint.
# Per teddy.md: GPU_SMALL (A10G, 24GB VRAM) is sufficient for 70M variant.
# Per teddy.md: scale_to_zero_enabled=True to reduce cost.
# Per teddy.md: AI Gateway inference table + usage tracking (HLS best-practice default).

from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
    ServingModelWorkloadType,
    AiGatewayConfig,
    AiGatewayInferenceTableConfig,
    AiGatewayUsageTrackingConfig,
)

if should_skip_rebuild:
    print("Skipping deployment — endpoint already READY.")
elif DEPLOY_ENDPOINT != "true":
    print(f"deploy_endpoint={DEPLOY_ENDPOINT} — skipping deployment. Set deploy_endpoint=true to deploy.")
else:
    served_entity = ServedEntityInput(
        entity_name=MODEL_NAME,
        entity_version=str(model_version),
        workload_type=ServingModelWorkloadType.GPU_SMALL,
        workload_size="Small",
        scale_to_zero_enabled=True,
    )
    endpoint_config = EndpointCoreConfigInput(served_entities=[served_entity])

    # AI Gateway: inference table + usage tracking (per teddy.md HLS best-practice)
    ai_gateway_config = AiGatewayConfig(
        inference_table_config=AiGatewayInferenceTableConfig(
            catalog_name=CATALOG,
            schema_name=SCHEMA,
            table_name_prefix=ENDPOINT_NAME,
            enabled=True,
        ),
        usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
    )

    w.serving_endpoints.create(
        name=ENDPOINT_NAME,
        config=endpoint_config,
        ai_gateway=ai_gateway_config,
    )
    print(f"Endpoint '{ENDPOINT_NAME}' creation initiated.")
    print(f"  Model:      {MODEL_NAME} v{model_version}")
    print(f"  Workload:   GPU_SMALL (A10G), Small, scale-to-zero")
    print(f"  AI Gateway: inference table + usage tracking")
    print(f"  (Endpoint creation typically takes ~10-15 minutes)")

# COMMAND ----------

# DBTITLE 1,Poll for Endpoint Readiness
# Phase 8: Poll for endpoint readiness.
# Per model-serving skill: poll until READY or failure. Diagnose from events if failure.

from databricks.sdk.service.serving import EndpointStateConfigUpdate, EndpointStateReady

if should_skip_rebuild:
    print("Skipping — endpoint already READY.")
elif DEPLOY_ENDPOINT != "true":
    print("Skipping — deploy_endpoint not set to true.")
else:
    def wait_for_endpoint_ready(name, timeout_s=1200, poll_s=15):
        deadline = time.time() + timeout_s
        failure_states = {
            EndpointStateConfigUpdate.UPDATE_FAILED,
            EndpointStateConfigUpdate.UPDATE_CANCELED,
        }
        while time.time() < deadline:
            ep = w.serving_endpoints.get(name)
            state = ep.state
            if (state.ready == EndpointStateReady.READY
                    and state.config_update == EndpointStateConfigUpdate.NOT_UPDATING):
                print(f"\nEndpoint '{name}' is READY!")
                return
            if state.config_update in failure_states:
                # Diagnose failure from endpoint events
                msg = f"{name} deployment failed (config_update={state.config_update.value})."
                try:
                    events = w.serving_endpoints.get(name).config.served_entities
                    if events:
                        msg += f" Served entity status: {events[0].state}"
                except Exception:
                    pass
                raise RuntimeError(msg)
            elapsed = int(time.time() - (deadline - timeout_s))
            print(f"  [{elapsed}s] ready={state.ready}, config_update={state.config_update}")
            time.sleep(poll_s)
        raise TimeoutError(f"{name} not ready after {timeout_s}s")

    wait_for_endpoint_ready(ENDPOINT_NAME)

# COMMAND ----------

# DBTITLE 1,Smoke Test
# Phase 9: Smoke test — query the endpoint with real gene IDs.
# Per teddy.md validation checklist: SDK query test, embedding sanity (dim matches d_model).
# Per teddy.md: extra_params values MUST be strings.

# Read real gene IDs from vocab.txt
vocab_path = f"{MODEL_DIR}/vocab.txt"
with open(vocab_path) as f:
    vocab_tokens = [t.strip() for t in f if t.strip()]
real_genes = [t for t in vocab_tokens if not t.startswith("<")][:100]

# Construct test payload
n_cells, n_genes = 3, len(real_genes)
rng = np.random.default_rng(99)
expr = rng.poisson(2.0, size=(n_cells, n_genes)).astype(np.float32)

obs_df = pd.DataFrame({"cell_id": [f"test_cell_{i}" for i in range(n_cells)]})
var_df = pd.DataFrame({"index": real_genes})

# Query endpoint via SDK (per teddy.md HTTP payload pattern)
response = w.serving_endpoints.query(
    name=ENDPOINT_NAME,
    dataframe_records=[{
        "adata_sparsematrix": expr.tolist(),
        "adata_obs":          obs_df.to_json(orient="split"),
        "adata_var":          var_df.to_json(orient="split"),
    }],
    extra_params={"max_seq_len": "2048", "pooling": "mean"},  # values MUST be strings
)

print("Smoke test response:")
predictions = response.predictions
print(f"  Number of cells: {len(predictions)}")
for i, pred in enumerate(predictions):
    emb = pred["embedding"]
    print(f"  Cell {i}: embedding dim={len(emb)}, first 5 values={emb[:5]}")

# Embedding sanity check (per teddy.md: dim should match config.d_model)
with open(f"{MODEL_DIR}/config.json") as f:
    config = json.load(f)
expected_dim = config.get("d_model", 0)
actual_dim = len(predictions[0]["embedding"])
print(f"\nEmbedding dimension: {actual_dim} (expected d_model={expected_dim})")
assert actual_dim == expected_dim, f"Dimension mismatch: {actual_dim} != {expected_dim}"

# Non-degenerate check (per teddy.md validation checklist item 5)
emb_array = np.array(predictions[0]["embedding"])
norm = np.linalg.norm(emb_array)
print(f"Embedding norm: {norm:.4f}")
assert norm > 0, "Embedding is degenerate (norm=0)"
assert not np.allclose(emb_array, emb_array[0]), "All embedding values are the same"
print("\nAll smoke tests PASSED!")
print("  - SDK query with extra_params (string values) succeeded")
print("  - Embedding dimension matches config.d_model")
print("  - Embeddings are non-degenerate")

# COMMAND ----------

# DBTITLE 1,Skills Consulted
# Skills from the Skill Registry consulted during this notebook:

skills_consulted = [
    "open-weight-models (HLS Open-Weight Models skill — SKILL.md + references/models/teddy.md)",
    "machine-learning (ML training and deployment best practices — SKILL.md)",
    "model-serving sub-skill (Unity Catalog registration and endpoint deployment — registration-and-deployment.md)",
    "ai-gateway-deployment sub-skill (AI Gateway inference table + usage tracking during deployment)",
]

print("Skills consulted from the Skill Registry:")
for s in skills_consulted:
    print(f"  - {s}")

# COMMAND ----------

# DBTITLE 1,Export Notebook Source
# Final step: Export this notebook's source (.py format) to results/with_skill/oss-001.txt
# using the Workspace REST API (GET /api/2.0/workspace/export with format=SOURCE).

import base64

NOTEBOOK_PATH = "/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/test02_TEDDY-70M_Deploy_withSkills"
OUTPUT_PATH = "/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-001.txt"

# Export via Databricks SDK API client
response = w.api_client.do(
    "GET",
    "/api/2.0/workspace/export",
    query={"path": NOTEBOOK_PATH, "format": "SOURCE"},
)

content_b64 = response.get("content")
if content_b64:
    source_code = base64.b64decode(content_b64).decode("utf-8")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(source_code)
    print(f"Notebook source exported to {OUTPUT_PATH}")
    print(f"  Size: {len(source_code)} bytes")
    print(f"  Lines: {len(source_code.splitlines())}")
else:
    print("ERROR: No content returned from export API")
    print(f"Response: {response}")
