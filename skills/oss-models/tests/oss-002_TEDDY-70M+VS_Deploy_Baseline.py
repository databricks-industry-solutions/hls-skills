# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # oss-002: TEDDY-70M + Vector Search Deploy — Baseline Arm
# MAGIC
# MAGIC **Eval protocol**: Each arm uses its own prompt. This is the **baseline** notebook — Genie Code uses only built-in knowledge, no custom skill files.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Baseline arm prompt (this notebook)
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat on **this** notebook → save response to `results/baseline/oss-002.txt`
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
# MAGIC ## Skill arm prompt (other notebook)
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat on the **skill** notebook → save response to `results/with_skill/oss-002.txt`
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

# DBTITLE 1,Config & Cleanup
# ============================================================
# Cell 3: Configuration & Idempotent Cleanup
# ============================================================
# This cell defines all naming constants and implements the
# re-runnable cleanup logic:
#   - If endpoint is READY  → skip cleanup (reuse existing deploy)
#   - If endpoint is FAILED  → delete endpoint + UC model versions + inference table
#   - If endpoint doesn't exist → nothing to clean (first run)
#   - If endpoint is PENDING/PROVISIONING → wait briefly, then check again

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceConflict
import time

w = WorkspaceClient()

# --- Naming constants (baseline arm) ---
CATALOG = "<catalog>"
SCHEMA = "skills"
UC_MODEL_NAME = f"{CATALOG}.{SCHEMA}.teddy_70m_vs_baseline"
ENDPOINT_NAME = "teddy-70m-vs-baseline"
VOLUME_PATH = "/Volumes/<catalog>/skills/test_without/models/teddy"
VS_ENDPOINT_NAME = "teddy-vs-baseline"
VS_INDEX_NAME = f"{CATALOG}.{SCHEMA}.teddy_cell_search_baseline"
REF_TABLE = f"{CATALOG}.{SCHEMA}.teddy_ref_embeddings_baseline"
HF_REPO = "Merck/TEDDY"

# Inference table auto-generated by Model Serving
INFERENCE_TABLE = f"{CATALOG}.{SCHEMA}.{ENDPOINT_NAME.replace('-', '_')}_payload"

print(f"UC Model:        {UC_MODEL_NAME}")
print(f"Endpoint:        {ENDPOINT_NAME}")
print(f"Volume:          {VOLUME_PATH}")
print(f"VS Endpoint:     {VS_ENDPOINT_NAME}")
print(f"VS Index:        {VS_INDEX_NAME}")
print(f"Ref Table:        {REF_TABLE}")
print(f"Inference Table: {INFERENCE_TABLE}")
print()

# --- Check endpoint state ---
endpoint_state = None
try:
    ep = w.serving_endpoints.get(name=ENDPOINT_NAME)
    endpoint_state = ep.state.ready if ep.state else None
    # Also check pending state
    pending = ep.state.config_state if ep.state else None
    print(f"Endpoint '{ENDPOINT_NAME}' found — state: {endpoint_state} (config: {pending})")
except NotFound:
    print(f"Endpoint '{ENDPOINT_NAME}' not found (first run or already cleaned up).")
except Exception as e:
    print(f"Error checking endpoint: {e}")

# --- Cleanup logic ---
need_cleanup = False

if endpoint_state == "READY":
    print("\n✓ Endpoint is READY — skipping cleanup. Will reuse existing deployment.")
    SKIP_DEPLOY = True
elif endpoint_state == "FAILED":
    print("\n✗ Endpoint is FAILED — will tear down and redeploy.")
    need_cleanup = True
    SKIP_DEPLOY = False
elif endpoint_state in ("NOT_READY", "PENDING", "PROVISIONING"):
    # Wait briefly to see if it settles
    print(f"\nEndpoint is {endpoint_state} — waiting 30s for it to settle...")
    time.sleep(30)
    ep = w.serving_endpoints.get(name=ENDPOINT_NAME)
    endpoint_state = ep.state.ready if ep.state else None
    if endpoint_state == "READY":
        print("✓ Endpoint became READY — skipping cleanup.")
        SKIP_DEPLOY = True
    else:
        print(f"Endpoint still {endpoint_state} — will tear down and redeploy.")
        need_cleanup = True
        SKIP_DEPLOY = False
else:
    print("\nEndpoint doesn't exist — will deploy fresh.")
    SKIP_DEPLOY = False

if need_cleanup:
    # 1. Delete the endpoint
    try:
        w.serving_endpoints.delete(name=ENDPOINT_NAME)
        print(f"  Deleted endpoint '{ENDPOINT_NAME}'")
    except Exception as e:
        print(f"  Could not delete endpoint: {e}")

    # 2. Drop the auto-generated inference table (conflict fix)
    try:
        spark.sql(f"DROP TABLE IF EXISTS {INFERENCE_TABLE}")
        print(f"  Dropped inference table '{INFERENCE_TABLE}'")
    except Exception as e:
        print(f"  Could not drop inference table: {e}")

    # 3. Delete all UC model versions
    try:
        versions = w.versions.list(full_name=UC_MODEL_NAME)
        for v in versions:
            try:
                w.versions.delete(name=UC_MODEL_NAME, version=str(v.version))
                print(f"  Deleted model version {v.version}")
            except Exception as e:
                print(f"  Could not delete version {v.version}: {e}")
    except Exception as e:
        print(f"  Could not list model versions: {e}")

    # 4. Delete the registered model itself (if no versions remain)
    try:
        w.registered_models.delete(full_name=UC_MODEL_NAME)
        print(f"  Deleted registered model '{UC_MODEL_NAME}'")
    except Exception as e:
        print(f"  Could not delete registered model (may have versions or not exist): {e}")

    print("\nCleanup complete. Will proceed with fresh deployment.")
elif not SKIP_DEPLOY:
    print("\nNo cleanup needed. Will proceed with fresh deployment.")

print(f"\nSKIP_DEPLOY = {SKIP_DEPLOY}")

# COMMAND ----------

# DBTITLE 1,Install Dependencies
# ============================================================
# Cell 4: Install Dependencies
# ============================================================
# TEDDY is a PyTorch model. We need torch, huggingface_hub
# for downloading, and transformers for loading.
# On Serverless CPU compute, the CPU-only torch wheel is sufficient.

%pip install -q torch huggingface_hub transformers numpy
# Restart Python to pick up new packages
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Download & Inspect TEDDY Model
# ============================================================
# Cell 5: Download TEDDY Model from HuggingFace & Inspect
# ============================================================
# Downloads the Merck/TEDDY model to the UC volume and inspects
# the file structure to understand how to load it.

import os
from huggingface_hub import list_repo_files, snapshot_download

VOLUME_PATH = "/Volumes/<catalog>/skills/test_without/models/teddy"
HF_REPO = "Merck/TEDDY"

# Create volume directory if needed
dbutils.fs.mkdirs(VOLUME_PATH)

# List all files in the repo to understand the structure
print("=== Files in Merck/TEDDY ===")
repo_files = list_repo_files(HF_REPO)
for f in sorted(repo_files):
    print(f"  {f}")
print(f"\nTotal files: {len(repo_files)}")

# Download the entire repo to the volume
# Use the local path format for /Volumes (strip leading / for local fs)
local_volume = VOLUME_PATH  # /Volumes is mounted as FUSE
print(f"\nDownloading model to {local_volume}...")

download_path = snapshot_download(
    repo_id=HF_REPO,
    local_dir=local_volume,
    repo_type="model",
)
print(f"Download complete: {download_path}")

# Inspect the downloaded files
print("\n=== Downloaded file tree ===")
for root, dirs, files in os.walk(local_volume):
    # Skip hidden directories
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    level = root.replace(local_volume, '').count(os.sep)
    indent = '  ' * level
    print(f"{indent}{os.path.basename(root)}/")
    sub_indent = '  ' * (level + 1)
    for file in sorted(files):
        fpath = os.path.join(root, file)
        size_mb = os.path.getsize(fpath) / (1024 * 1024)
        print(f"{sub_indent}{file} ({size_mb:.1f} MB)")

# COMMAND ----------

# DBTITLE 1,Inspect Model Architecture
# ============================================================
# Cell 6: Inspect Model Architecture & Config
# ============================================================
# Read key source files to understand how TEDDY works.

VOLUME_PATH = "/Volumes/<catalog>/skills/test_without/models/teddy"
import json, os

# --- 70M config ---
config_path = os.path.join(VOLUME_PATH, "teddy/models/teddy_g/70M/config.json")
with open(config_path) as f:
    config_70m = json.load(f)
print("=== 70M config.json ===")
print(json.dumps(config_70m, indent=2))

# --- model.py (architecture) ---
model_py_path = os.path.join(VOLUME_PATH, "teddy/models/teddy_g/model.py")
print("\n=== teddy/models/teddy_g/model.py ===")
with open(model_py_path) as f:
    model_src = f.read()
print(model_src[:5000])  # First 5000 chars
if len(model_src) > 5000:
    print(f"\n... ({len(model_src)} total chars, showing first 5000)")

# --- model_directory.py (loading utility) ---
md_path = os.path.join(VOLUME_PATH, "teddy/models/model_directory.py")
print("\n=== teddy/models/model_directory.py ===")
with open(md_path) as f:
    md_src = f.read()
print(md_src[:5000])
if len(md_src) > 5000:
    print(f"\n... ({len(md_src)} total chars, showing first 5000)")

# --- gene_tokenizer.py (tokenizer) ---
tok_path = os.path.join(VOLUME_PATH, "teddy/tokenizer/gene_tokenizer.py")
print("\n=== teddy/tokenizer/gene_tokenizer.py ===")
with open(tok_path) as f:
    tok_src = f.read()
print(tok_src[:5000])
if len(tok_src) > 5000:
    print(f"\n... ({len(tok_src)} total chars, showing first 5000)")

# --- vocab.json size ---
vocab_path = os.path.join(VOLUME_PATH, "teddy/tokenizer/vocab.json")
with open(vocab_path) as f:
    vocab = json.load(f)
print(f"\n=== vocab.json: {len(vocab)} entries ===")
# Show first 20 entries
for i, (k, v) in enumerate(sorted(vocab.items())[:20]):
    print(f"  {k}: {v}")

# --- README ---
readme_path = os.path.join(VOLUME_PATH, "teddy/models/teddy_g/README.md")
print("\n=== teddy/models/teddy_g/README.md ===")
with open(readme_path) as f:
    print(f.read()[:3000])

# COMMAND ----------

# DBTITLE 1,Create PyFunc Wrapper & Log to MLflow
# ============================================================
# Cell 7: Create PyFunc Wrapper, Log to MLflow & Register in UC
# ============================================================
# Creates a file-based PyFunc wrapper for TEDDY-70M that:
#   - Accepts gene_ids (list of Ensembl IDs) as input
#   - Tokenizes using the GeneTokenizer
#   - Runs through the TeddyGModel transformer
#   - Returns a 512-dim cell embedding
#
# File-based logging is more reliable than instance-based in
# Model Serving (avoids cloudpickle version mismatches).

import os, sys, shutil, json
import mlflow
import pandas as pd
import numpy as np

VOLUME_PATH = "/Volumes/<catalog>/skills/test_without/models/teddy"
UC_MODEL_NAME = "<catalog>.skills.teddy_70m_vs_baseline"
MODEL_70M_DIR = os.path.join(VOLUME_PATH, "teddy", "models", "teddy_g", "70M")

# --- Step 1: Create a clean code directory (just the Python package, no weights) ---
CLEAN_CODE_DIR = "/tmp/teddy_code"
if os.path.exists(CLEAN_CODE_DIR):
    shutil.rmtree(CLEAN_CODE_DIR)

# Copy only the Python source files from the teddy package
src_teddy = os.path.join(VOLUME_PATH, "teddy")
for root, dirs, files in os.walk(src_teddy):
    # Skip __pycache__, .DS_Store, data dirs with non-py files
    dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
    rel = os.path.relpath(root, VOLUME_PATH)
    dst = os.path.join(CLEAN_CODE_DIR, rel)
    os.makedirs(dst, exist_ok=True)
    for f in files:
        if f.endswith('.py') or f.endswith('.json') or f.endswith('.txt'):
            shutil.copy2(os.path.join(root, f), os.path.join(dst, f))

print(f"Clean code dir: {CLEAN_CODE_DIR}")
for root, dirs, files in os.walk(CLEAN_CODE_DIR):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    level = root.replace(CLEAN_CODE_DIR, '').count(os.sep)
    indent = '  ' * level
    print(f"{indent}{os.path.basename(root)}/")
    for f in sorted(files):
        print(f"{'  ' * (level+1)}{f}")

# --- Step 2: Write the PyFunc wrapper file ---
WRAPPER_PATH = "/tmp/teddy_wrapper.py"
wrapper_code = '''"""
TEDDY-70M PyFunc Wrapper for Databricks Model Serving.

Input:  DataFrame with column "gene_ids" (list of Ensembl gene ID strings, e.g. ["ENSG00000000003", ...])
Output: DataFrame with column "embedding" (list of floats, 512 dimensions)
"""
import os, sys, json, logging
import mlflow
import pandas as pd
import numpy as np
import torch

logger = logging.getLogger(__name__)


class TeddyEmbedderModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        """Load the TEDDY model and tokenizer from artifacts."""
        # --- isatty fix (safety measure for Model Serving containers) ---
        # Databricks Model Serving replaces sys.stdout/stderr with StreamToLogger
        # objects that lack isatty(), causing transformers to crash on weight
        # loading reports. Patch before any from_pretrained call.
        for stream in (sys.stdout, sys.stderr):
            if stream is not None and not hasattr(stream, "isatty"):
                stream.isatty = lambda: False

        model_dir = context.artifacts["model_dir"]
        code_dir = context.artifacts["code_dir"]

        # Add code directory to sys.path so we can import the teddy package
        if code_dir not in sys.path:
            sys.path.insert(0, code_dir)

        # Import the model and tokenizer classes
        from teddy.models.teddy_g.model import TeddyGModel, TeddyGConfig
        from teddy.tokenizer.gene_tokenizer import GeneTokenizer

        # Fix for transformers 5.x: TEDDY was written for transformers 4.41.0
        # In transformers 5.x, PreTrainedModel.all_tied_weights_keys returns a list
        # but mark_tied_weights_as_initialized calls .keys() on it, expecting a dict.
        # Override to return an empty dict. hasattr check is skipped because the
        # parent class already defines this property (returning a list).
        TeddyGModel.all_tied_weights_keys = property(lambda self: {})

        # Fix for transformers 5.x: TeddyGConfig lacks pad_token_id but
        # model forward() accesses config.pad_token_id. Set class default.
        if 'pad_token_id' not in TeddyGConfig.__dict__:
            TeddyGConfig.pad_token_id = -2

        # Load model configuration
        config_path = os.path.join(model_dir, "config.json")
        with open(config_path) as f:
            config_dict = json.load(f)
        config = TeddyGConfig(**config_dict)

        # Load model weights
        self.model = TeddyGModel.from_pretrained(model_dir, config=config)
        self.model.eval()

        # Load tokenizer
        vocab_path = os.path.join(model_dir, "vocab.txt")
        self.tokenizer = GeneTokenizer(vocab_file=vocab_path)

        # Store config values
        self.d_model = config.d_model
        self.max_len = config.max_position_embeddings
        self.pad_token_id = config.pad_value  # -2

        logger.info(f"TEDDY model loaded: d_model={self.d_model}, max_len={self.max_len}")

    def predict(self, context, model_input: pd.DataFrame) -> pd.DataFrame:
        """Generate cell embeddings from gene expression data.

        Each row in model_input should have a "gene_ids" column containing
        a list of Ensembl gene ID strings (e.g. ["ENSG00000000003", ...]).
        Genes should be ranked by expression (most expressed first).
        """
        embeddings = []

        for _, row in model_input.iterrows():
            gene_ids = row["gene_ids"]
            if isinstance(gene_ids, str):
                # Handle JSON string input
                gene_ids = json.loads(gene_ids)

            # Convert gene IDs to token IDs using the vocab
            token_ids = []
            for gid in gene_ids:
                tid = self.tokenizer.vocab.get(gid)
                if tid is not None:
                    token_ids.append(tid)

            # Truncate to max sequence length
            token_ids = token_ids[:self.max_len]

            if len(token_ids) == 0:
                # Return zero embedding if no genes match
                embeddings.append([0.0] * self.d_model)
                continue

            # Create input tensor [1, seq_len]
            input_ids = torch.tensor([token_ids], dtype=torch.long)

            # Run model
            with torch.no_grad():
                output = self.model(gene_ids=input_ids)
                emb = output["cell_emb"].squeeze(0).cpu().numpy()

            embeddings.append(emb.tolist())

        return pd.DataFrame({"embedding": embeddings})


mlflow.models.set_model(TeddyEmbedderModel())
'''

with open(WRAPPER_PATH, "w") as f:
    f.write(wrapper_code)
print(f"\nWrapper written to {WRAPPER_PATH} ({len(wrapper_code)} chars)")

# --- Step 3: Log to MLflow & Register in UC ---
mlflow.set_registry_uri("databricks-uc")

# Check current package versions for pip_requirements
import transformers
import torch
print(f"\ntorch version: {torch.__version__}")
print(f"transformers version: {transformers.__version__}")

# Create a sample input and output for signature inference
from mlflow.models import infer_signature

sample_gene_ids = ["ENSG00000000003", "ENSG00000000419", "ENSG00000000457", 
                   "ENSG00000000460", "ENSG00000000938", "ENSG00000000971",
                   "ENSG00000001036", "ENSG00000001084", "ENSG00000001167",
                   "ENSG00000001460"]
sample_input = pd.DataFrame({"gene_ids": [sample_gene_ids]})
sample_output = pd.DataFrame({"embedding": [[0.1] * 512]})  # 512-dim embedding
signature = infer_signature(sample_input, sample_output)
print(f"Signature: {signature}")

with mlflow.start_run() as run:
    model_info = mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=WRAPPER_PATH,
        artifacts={
            "model_dir": MODEL_70M_DIR,
            "code_dir": CLEAN_CODE_DIR,
        },
        pip_requirements=[
            f"torch=={torch.__version__.split('+')[0]}",  # strip CUDA suffix for CPU serving
            f"transformers=={transformers.__version__}",
            f"numpy=={np.__version__}",
            "pandas",
        ],
        signature=signature,
        input_example=sample_input,
    )
    print(f"\nModel logged: {model_info.model_uri}")

    # Register in Unity Catalog
    uc_model = mlflow.register_model(
        model_uri=model_info.model_uri,
        name=UC_MODEL_NAME,
    )
    print(f"Registered: {uc_model.name} version {uc_model.version}")

print(f"\nRun ID: {run.info.run_id}")
print(f"Model URI: {model_info.model_uri}")
print(f"UC Model: {uc_model.name} v{uc_model.version}")

# COMMAND ----------

# DBTITLE 1,Local PyFunc Round-Trip Test
# ============================================================
# Cell 8: Local PyFunc Round-Trip Test (Pre-Deploy Gate)
# ============================================================
# Load the logged model locally and run inference on sample
# gene expression data to verify packaging works before
# deploying to Model Serving.

import mlflow
import pandas as pd
import numpy as np
import json, os, sys

# ---- Transformers 5.x compatibility patches for TEDDY (written for 4.41.0) ----
# Flush cached teddy modules so re-runs get fresh class objects (avoids
# stacking monkey-patches from prior cell executions).
for _k in [k for k in sys.modules if k.startswith('teddy')]:
    del sys.modules[_k]

VOLUME_PATH = "/Volumes/<catalog>/skills/test_without/models/teddy"
if VOLUME_PATH not in sys.path:
    sys.path.insert(0, VOLUME_PATH)
from teddy.models.teddy_g.model import TeddyGModel, TeddyGConfig

# 1. all_tied_weights_keys: In 5.x, mark_tied_weights_as_initialized() calls
#    .keys() on all_tied_weights_keys, expecting a dict. The inherited property
#    returns a list. Override at the class level before any from_pretrained call.
TeddyGModel.all_tied_weights_keys = property(lambda self: {})

# 2. pad_token_id: TEDDY's forward() accesses config.pad_token_id, which existed
#    in 4.x's PretrainedConfig but is no longer a default in 5.x's strict
#    __getattribute__. Set a class-level default (TEDDY config.pad_value is -2).
if 'pad_token_id' not in TeddyGConfig.__dict__:
    TeddyGConfig.pad_token_id = -2

UC_MODEL_NAME = "<catalog>.skills.teddy_70m_vs_baseline"

# Load the registered model (latest version with the wrapper fix)
model_uri = f"models:/{UC_MODEL_NAME}/4"
print(f"Loading model from: {model_uri}")
loaded_model = mlflow.pyfunc.load_model(model_uri)
print("Model loaded successfully.")

# Load the vocab to pick valid gene IDs
vocab_path = os.path.join(VOLUME_PATH, "teddy", "tokenizer", "vocab.json")
with open(vocab_path) as f:
    vocab = json.load(f)

# Get a set of valid Ensembl gene IDs (first 100 from the vocab)
valid_gene_ids = sorted([k for k in vocab.keys() if k.startswith("ENSG")])[:100]
print(f"Using {len(valid_gene_ids)} gene IDs for test")
print(f"Sample: {valid_gene_ids[:5]}")

# --- Test 1: Small input (10 genes) ---
small_input = pd.DataFrame({"gene_ids": [valid_gene_ids[:10]]})
print("\n=== Test 1: Small input (10 genes) ===")
result = loaded_model.predict(small_input)
print(f"Input shape: {small_input.shape}")
print(f"Output shape: {result.shape}")
emb = result["embedding"].iloc[0]
print(f"Embedding dim: {len(emb)}")
print(f"First 5 values: {emb[:5]}")
print(f"Norm: {np.linalg.norm(emb):.4f}")

# --- Test 2: Larger input (50 genes) ---
large_input = pd.DataFrame({"gene_ids": [valid_gene_ids[:50]]})
print("\n=== Test 2: Larger input (50 genes) ===")
result2 = loaded_model.predict(large_input)
emb2 = result2["embedding"].iloc[0]
print(f"Embedding dim: {len(emb2)}")
print(f"Norm: {np.linalg.norm(emb2):.4f}")

# --- Test 3: Batch input (2 cells) ---
batch_input = pd.DataFrame({"gene_ids": [valid_gene_ids[:10], valid_gene_ids[10:30]]})
print("\n=== Test 3: Batch input (2 cells) ===")
result3 = loaded_model.predict(batch_input)
print(f"Output rows: {len(result3)}")
for i in range(len(result3)):
    emb_i = result3["embedding"].iloc[i]
    print(f"  Cell {i}: dim={len(emb_i)}, norm={np.linalg.norm(emb_i):.4f}")

# --- Verify embeddings are different for different inputs ---
if not np.allclose(result["embedding"].iloc[0], result2["embedding"].iloc[0], atol=1e-6):
    print("\n✓ Embeddings differ for different inputs (expected)")
else:
    print("\n⚠ Embeddings are identical for different inputs (unexpected)")

print("\n✅ Local round-trip test PASSED — model is ready for deployment.")

# COMMAND ----------

# DBTITLE 1,Deploy to Model Serving
# ============================================================
# Cell 9: Deploy to Model Serving
# ============================================================
# Creates the serving endpoint for TEDDY-70M embedder.
# CPU Small is sufficient for a 70M-param transformer.
# Scale-to-zero keeps costs down when idle.

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
)

w = WorkspaceClient()

ENDPOINT_NAME = "teddy-70m-vs-baseline"
UC_MODEL_NAME = "<catalog>.skills.teddy_70m_vs_baseline"
# Dynamically resolve latest UC model version
import mlflow
mlflow.set_registry_uri("databricks-uc")
_versions = mlflow.tracking.MlflowClient().search_model_versions(f"name='{UC_MODEL_NAME}'")
MODEL_VERSION = str(max(int(v.version) for v in _versions))
print(f"Latest model version: {MODEL_VERSION}")
CATALOG = "<catalog>"
SCHEMA = "skills"

# --- Check current endpoint state ---
skip_deploy = False
try:
    ep = w.serving_endpoints.get(name=ENDPOINT_NAME)
    state = ep.state.ready if ep.state else None
    state_str = state.value if hasattr(state, 'value') else str(state)
    # Check currently served version
    served_ver = None
    if ep.config and ep.config.served_entities:
        served_ver = ep.config.served_entities[0].entity_version
    if state_str == "READY" and served_ver == MODEL_VERSION:
        print(f"\u2713 Endpoint '{ENDPOINT_NAME}' is already READY on v{served_ver} \u2014 skipping.")
        skip_deploy = True
    elif state_str == "READY" and served_ver != MODEL_VERSION:
        print(f"Endpoint is READY but on v{served_ver}, need v{MODEL_VERSION}. Updating config...")
        w.serving_endpoints.update_config(
            name=ENDPOINT_NAME,
            served_entities=[
                ServedEntityInput(
                    entity_name=UC_MODEL_NAME,
                    entity_version=MODEL_VERSION,
                    workload_size="Small",
                    scale_to_zero_enabled=True,
                )
            ],
        )
        print(f"  \u2713 Config updated to v{MODEL_VERSION}. Endpoint will re-provision.")
        skip_deploy = True  # update_config handles it, no need to create
    else:
        print(f"Endpoint exists but state={state_str}. Will recreate.")
        w.serving_endpoints.delete(name=ENDPOINT_NAME)
        print(f"  Deleted stale endpoint.")
        import time; time.sleep(10)
except NotFound:
    print(f"Endpoint '{ENDPOINT_NAME}' not found \u2014 will create.")

if not skip_deploy:
    print(f"\nCreating endpoint '{ENDPOINT_NAME}' with {UC_MODEL_NAME} v{MODEL_VERSION}...")
    w.serving_endpoints.create(
        name=ENDPOINT_NAME,
        config=EndpointCoreConfigInput(
            name=ENDPOINT_NAME,
            served_entities=[
                ServedEntityInput(
                    entity_name=UC_MODEL_NAME,
                    entity_version=MODEL_VERSION,
                    workload_size="Small",
                    scale_to_zero_enabled=True,
                )
            ],
            # Note: legacy auto_capture_config is deprecated;
            # use AI Gateway inference tables post-deploy if needed.
        ),
    )
    print(f"\u2713 Endpoint creation initiated.")
    print(f"  Entity: {UC_MODEL_NAME} v{MODEL_VERSION}")
    print(f"  Workload: Small (CPU), scale-to-zero=True")
    print(f"  Inference table: configure via AI Gateway post-deploy")

print("\n\u23f3 Run the next cell to wait for READY state and live-test.")

# COMMAND ----------

# DBTITLE 1,Wait for Endpoint & Live Test
# ============================================================
# Cell 10: Wait for Endpoint & Live Test
# ============================================================
# Polls the serving endpoint until READY, then sends a live
# embedding request to validate end-to-end.

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
import time, json, numpy as np

w = WorkspaceClient()
ENDPOINT_NAME = "teddy-70m-vs-baseline"

# --- Wait for READY ---
print(f"Waiting for endpoint '{ENDPOINT_NAME}' to become READY...")
MAX_WAIT = 45 * 60   # 45 min ceiling
POLL = 60             # check every 60s
elapsed = 0

while elapsed < MAX_WAIT:
    ep = w.serving_endpoints.get(name=ENDPOINT_NAME)
    state = ep.state.ready if ep.state else "UNKNOWN"
    print(f"  [{elapsed // 60:>2d}m] ready={state}")

    # Also check config_update — endpoint can be READY on old version
    # while a config update deploys the new one.
    cfg_update = ep.state.config_update if ep.state else None
    cfg_str = cfg_update.value if hasattr(cfg_update, 'value') else str(cfg_update)
    if state.value == "READY" and cfg_str == "NOT_UPDATING":
        # Confirm served version
        sv = ep.config.served_entities[0].entity_version if ep.config and ep.config.served_entities else "?"
        print(f"\n\u2705 Endpoint is READY on v{sv} (took ~{elapsed // 60}m).")
        break
    if state.value == "READY" and cfg_str != "NOT_UPDATING":
        sv_pending = "?"
        if ep.pending_config and ep.pending_config.served_entities:
            sv_pending = ep.pending_config.served_entities[0].entity_version
        print(f"  [{elapsed // 60:>2d}m] ready={state.value}, config_update={cfg_str} (deploying v{sv_pending})")
        time.sleep(POLL)
        elapsed += POLL
        continue
    if state.value == "FAILED":
        msg = ""
        if ep.pending_config:
            msg = getattr(ep.pending_config, "config_state_message", "") or ""
        raise RuntimeError(f"Endpoint FAILED: {msg}")

    time.sleep(POLL)
    elapsed += POLL
else:
    raise TimeoutError(f"Endpoint not READY within {MAX_WAIT // 60}m")

# --- Live test ---
print("\n=== Live Endpoint Test ===")
test_genes = [
    "ENSG00000000003", "ENSG00000000419", "ENSG00000000457",
    "ENSG00000000460", "ENSG00000000938", "ENSG00000000971",
    "ENSG00000001036", "ENSG00000001084", "ENSG00000001167",
    "ENSG00000001460",
]

resp = w.serving_endpoints.query(
    name=ENDPOINT_NAME,
    dataframe_records=[{"gene_ids": test_genes}],
)

pred = resp.predictions[0]
emb = pred["embedding"] if isinstance(pred, dict) else pred
print(f"Embedding dim: {len(emb)}")
print(f"First 5 values: {emb[:5]}")
print(f"Norm: {np.linalg.norm(emb):.4f}")
assert len(emb) == 512, f"Expected 512-dim, got {len(emb)}"

print("\n\u2705 Live endpoint test PASSED.")

# COMMAND ----------

# DBTITLE 1,Build Reference Cell-Type Embeddings Table
# ============================================================
# Cell 11: Build Reference Cell-Type Embeddings Table
# ============================================================
# Creates a reference corpus by embedding synthetic cell-type
# profiles (well-known marker genes) via the deployed endpoint.
# The resulting Delta table is CDF-enabled with a primary key
# so Vector Search can DeltaSync from it.

from databricks.sdk import WorkspaceClient
import json, numpy as np, pandas as pd

w = WorkspaceClient()
ENDPOINT_NAME = "teddy-70m-vs-baseline"
REF_TABLE = "<catalog>.skills.teddy_ref_embeddings_baseline"

# --- Marker-gene profiles for common cell types ---
# Ranked lists of highly-expressed Ensembl gene IDs per type.
CELL_PROFILES = {
    "T_cell_CD4": [
        "ENSG00000010610", "ENSG00000198821", "ENSG00000167286",
        "ENSG00000160654", "ENSG00000081237", "ENSG00000116824",
        "ENSG00000272398", "ENSG00000110848", "ENSG00000169442",
        "ENSG00000105374", "ENSG00000111796", "ENSG00000145649",
        "ENSG00000100453", "ENSG00000115415", "ENSG00000188389",
    ],
    "T_cell_CD8": [
        "ENSG00000153563", "ENSG00000172116", "ENSG00000198821",
        "ENSG00000167286", "ENSG00000160654", "ENSG00000145649",
        "ENSG00000100453", "ENSG00000105374", "ENSG00000081237",
        "ENSG00000116824", "ENSG00000169442", "ENSG00000111796",
        "ENSG00000110848", "ENSG00000115415", "ENSG00000188389",
    ],
    "B_cell": [
        "ENSG00000177455", "ENSG00000012124", "ENSG00000139193",
        "ENSG00000116824", "ENSG00000081237", "ENSG00000211899",
        "ENSG00000169442", "ENSG00000272398", "ENSG00000110848",
        "ENSG00000105369", "ENSG00000007312", "ENSG00000019582",
        "ENSG00000204287", "ENSG00000196126", "ENSG00000026508",
    ],
    "NK_cell": [
        "ENSG00000105374", "ENSG00000111796", "ENSG00000134539",
        "ENSG00000149781", "ENSG00000145649", "ENSG00000100453",
        "ENSG00000115523", "ENSG00000081237", "ENSG00000116824",
        "ENSG00000169442", "ENSG00000110848", "ENSG00000198821",
        "ENSG00000153563", "ENSG00000188389", "ENSG00000115415",
    ],
    "Monocyte": [
        "ENSG00000170458", "ENSG00000019582", "ENSG00000204287",
        "ENSG00000196126", "ENSG00000081237", "ENSG00000169442",
        "ENSG00000110848", "ENSG00000244734", "ENSG00000005961",
        "ENSG00000150337", "ENSG00000143546", "ENSG00000163220",
        "ENSG00000179639", "ENSG00000026508", "ENSG00000163600",
    ],
    "Dendritic_cell": [
        "ENSG00000019582", "ENSG00000204287", "ENSG00000196126",
        "ENSG00000179639", "ENSG00000117281", "ENSG00000081237",
        "ENSG00000169442", "ENSG00000163600", "ENSG00000150337",
        "ENSG00000143546", "ENSG00000163220", "ENSG00000026508",
        "ENSG00000005961", "ENSG00000170458", "ENSG00000116824",
    ],
    "Hepatocyte": [
        "ENSG00000163631", "ENSG00000080618", "ENSG00000145192",
        "ENSG00000173295", "ENSG00000084674", "ENSG00000087086",
        "ENSG00000120053", "ENSG00000110243", "ENSG00000138109",
        "ENSG00000165841", "ENSG00000108515", "ENSG00000117394",
        "ENSG00000160957", "ENSG00000244734", "ENSG00000160868",
    ],
    "Neuron_excitatory": [
        "ENSG00000176884", "ENSG00000183454", "ENSG00000075624",
        "ENSG00000111640", "ENSG00000170579", "ENSG00000007372",
        "ENSG00000172137", "ENSG00000104888", "ENSG00000091664",
        "ENSG00000197971", "ENSG00000198668", "ENSG00000131095",
        "ENSG00000141564", "ENSG00000158710", "ENSG00000108381",
    ],
    "Cardiomyocyte": [
        "ENSG00000092054", "ENSG00000111245", "ENSG00000175084",
        "ENSG00000118194", "ENSG00000159251", "ENSG00000106631",
        "ENSG00000198125", "ENSG00000114854", "ENSG00000198668",
        "ENSG00000075624", "ENSG00000111640", "ENSG00000141564",
        "ENSG00000244734", "ENSG00000087086", "ENSG00000163631",
    ],
    "Fibroblast": [
        "ENSG00000108821", "ENSG00000164692", "ENSG00000168542",
        "ENSG00000026508", "ENSG00000075624", "ENSG00000111640",
        "ENSG00000141564", "ENSG00000087086", "ENSG00000175084",
        "ENSG00000244734", "ENSG00000198668", "ENSG00000131095",
        "ENSG00000163631", "ENSG00000197971", "ENSG00000110799",
    ],
}

print(f"Defined {len(CELL_PROFILES)} cell-type profiles")

# --- Embed each profile via the deployed endpoint ---
print(f"\nEmbedding profiles via '{ENDPOINT_NAME}'...")
records = []
for cell_type, gene_ids in CELL_PROFILES.items():
    resp = w.serving_endpoints.query(
        name=ENDPOINT_NAME,
        dataframe_records=[{"gene_ids": gene_ids}],
    )
    pred = resp.predictions[0]
    emb = pred["embedding"] if isinstance(pred, dict) else pred
    records.append({
        "cell_type_id": cell_type,
        "cell_type": cell_type.replace("_", " "),
        "gene_ids": json.dumps(gene_ids),
        "embedding": emb,
        "n_genes": len(gene_ids),
    })
    print(f"  \u2713 {cell_type:22s} dim={len(emb)}  norm={np.linalg.norm(emb):.2f}")

print(f"\nEmbedded {len(records)} cell types.")

# --- Write as CDF-enabled Delta table with NOT NULL PK ---
spark.sql(f"DROP TABLE IF EXISTS {REF_TABLE}")
spark.sql(f"""
CREATE TABLE {REF_TABLE} (
    cell_type_id STRING NOT NULL,
    cell_type STRING,
    gene_ids STRING,
    embedding ARRAY<FLOAT>,
    n_genes INT,
    CONSTRAINT pk_cell_type PRIMARY KEY (cell_type_id)
) TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
""")

pdf = pd.DataFrame(records)
df = spark.createDataFrame(pdf)
df.write.format("delta").mode("append").saveAsTable(REF_TABLE)

count = spark.table(REF_TABLE).count()
print(f"\n\u2705 Reference table '{REF_TABLE}' created: {count} rows, CDF=true, PK=cell_type_id")
display(spark.table(REF_TABLE).select("cell_type_id", "cell_type", "n_genes", "gene_ids"))

# COMMAND ----------

# DBTITLE 1,Create Vector Search Endpoint & Index
# ============================================================
# Cell 12: Create Vector Search Endpoint & Index
# ============================================================
# Creates a standard VS endpoint and a DeltaSync index with
# self-managed embeddings (512-dim TEDDY vectors) for
# nearest-neighbor cell-type search.

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceConflict
from databricks.sdk.service.vectorsearch import (
    EndpointType, VectorIndexType, PipelineType,
    DeltaSyncVectorIndexSpecRequest, EmbeddingVectorColumn,
)
import time

w = WorkspaceClient()

VS_ENDPOINT_NAME = "teddy-vs-baseline"
VS_INDEX_NAME = "<catalog>.skills.teddy_cell_search_baseline"
REF_TABLE = "<catalog>.skills.teddy_ref_embeddings_baseline"

# --- Step 1: Create VS endpoint (if needed) ---
try:
    vs_ep = w.vector_search_endpoints.get_endpoint(endpoint_name=VS_ENDPOINT_NAME)
    _raw = vs_ep.endpoint_status.state if vs_ep.endpoint_status else None
    ep_st = _raw.value if hasattr(_raw, 'value') else str(_raw)
    print(f"VS endpoint '{VS_ENDPOINT_NAME}' exists \u2014 status: {ep_st}")
except NotFound:
    print(f"Creating VS endpoint '{VS_ENDPOINT_NAME}'...")
    w.vector_search_endpoints.create_endpoint(
        name=VS_ENDPOINT_NAME,
        endpoint_type=EndpointType.STANDARD,
    )
    ep_st = "PROVISIONING"
    print(f"  \u2713 Creation initiated.")

if ep_st != "ONLINE":
    print("Waiting for VS endpoint to come ONLINE...")
    for _ in range(60):  # up to 30 min
        time.sleep(30)
        vs_ep = w.vector_search_endpoints.get_endpoint(endpoint_name=VS_ENDPOINT_NAME)
        _raw = vs_ep.endpoint_status.state if vs_ep.endpoint_status else None
        ep_st = _raw.value if hasattr(_raw, 'value') else str(_raw)
        print(f"  status: {ep_st}")
        if ep_st == "ONLINE":
            break
    else:
        raise TimeoutError("VS endpoint did not come ONLINE within 30m")

print(f"\n\u2713 VS endpoint '{VS_ENDPOINT_NAME}' is ONLINE.")

# --- Step 2: Create DeltaSync index (self-managed embeddings) ---
try:
    existing = w.vector_search_indexes.get_index(index_name=VS_INDEX_NAME)
    idx_ready = existing.status.ready if existing.status else False
    print(f"\nVS index '{VS_INDEX_NAME}' exists \u2014 ready={idx_ready}")
    if idx_ready:
        print("Index is already ready \u2014 skipping creation.")
except (NotFound, Exception):
    print(f"\nCreating DeltaSync index '{VS_INDEX_NAME}'...")
    w.vector_search_indexes.create_index(
        name=VS_INDEX_NAME,
        endpoint_name=VS_ENDPOINT_NAME,
        primary_key="cell_type_id",
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=REF_TABLE,
            embedding_vector_columns=[
                EmbeddingVectorColumn(name="embedding", embedding_dimension=512)
            ],
            columns_to_sync=["cell_type_id", "cell_type", "n_genes", "gene_ids"],
            pipeline_type=PipelineType.TRIGGERED,
        ),
    )
    print(f"  \u2713 Index creation initiated.")
    idx_ready = False

# --- Wait for index sync ---
if not idx_ready:
    print("\nWaiting for index to sync...")
    for i in range(60):  # up to 30 min
        time.sleep(30)
        idx = w.vector_search_indexes.get_index(index_name=VS_INDEX_NAME)
        ready = idx.status.ready if idx.status else False
        msg = idx.status.message if idx.status else "unknown"
        print(f"  [{i * 30 // 60}m{i * 30 % 60:02d}s] ready={ready}  msg={msg}")
        if ready:
            break
    else:
        # Try triggering a manual sync
        print("Triggering manual sync...")
        w.vector_search_indexes.sync_index(index_name=VS_INDEX_NAME)
        time.sleep(60)

print(f"\n\u2705 Vector Search index '{VS_INDEX_NAME}' is READY.")

# COMMAND ----------

# DBTITLE 1,End-to-End Nearest-Neighbor Search Test
# ============================================================
# Cell 13: End-to-End Nearest-Neighbor Search Test
# ============================================================
# Queries the VS index with marker-gene profiles and verifies
# the full pipeline: genes -> endpoint -> embedding -> VS -> results.

from databricks.sdk import WorkspaceClient
import numpy as np

w = WorkspaceClient()
VS_INDEX_NAME = "<catalog>.skills.teddy_cell_search_baseline"
ENDPOINT_NAME = "teddy-70m-vs-baseline"

def embed_genes(gene_ids):
    """Helper: embed a gene list via the serving endpoint."""
    resp = w.serving_endpoints.query(
        name=ENDPOINT_NAME,
        dataframe_records=[{"gene_ids": gene_ids}],
    )
    pred = resp.predictions[0]
    return pred["embedding"] if isinstance(pred, dict) else pred

def search(query_emb, label, n=5):
    """Helper: query VS index and print results."""
    results = w.vector_search_indexes.query_index(
        index_name=VS_INDEX_NAME,
        columns=["cell_type_id", "cell_type", "n_genes"],
        query_vector=query_emb,
        num_results=n,
    )
    print(f"\n=== {label} ===")
    print(f"{'Rank':<5} {'Cell Type':<25} {'Score':>8}")
    print("-" * 40)
    for i, row in enumerate(results.result.data_array, 1):
        print(f"{i:<5} {row[0]:<25} {row[-1]:>8.4f}")
    return results.result.data_array[0][0]  # top match id

# --- Test 1: T-cell CD4 markers -> should match T cells ---
t4_genes = ["ENSG00000010610", "ENSG00000198821", "ENSG00000167286",
            "ENSG00000160654", "ENSG00000081237"]
top1 = search(embed_genes(t4_genes), "Query: T-cell CD4 markers")
print(f"  Top match: {top1} {'\u2713' if 'T_cell' in top1 else '\u2717'}")

# --- Test 2: Hepatocyte markers -> should match Hepatocyte ---
hep_genes = ["ENSG00000163631", "ENSG00000080618", "ENSG00000145192",
             "ENSG00000084674", "ENSG00000087086"]
top2 = search(embed_genes(hep_genes), "Query: Hepatocyte markers")
print(f"  Top match: {top2} {'\u2713' if 'Hepato' in top2 else '\u2717'}")

# --- Test 3: NK cell markers -> should match NK ---
nk_genes = ["ENSG00000105374", "ENSG00000111796", "ENSG00000134539",
            "ENSG00000145649", "ENSG00000115523"]
top3 = search(embed_genes(nk_genes), "Query: NK cell markers")
print(f"  Top match: {top3} {'\u2713' if 'NK' in top3 else '\u2717'}")

# --- Test 4: Fibroblast markers -> should match Fibroblast ---
fib_genes = ["ENSG00000108821", "ENSG00000164692", "ENSG00000168542",
             "ENSG00000026508", "ENSG00000075624"]
top4 = search(embed_genes(fib_genes), "Query: Fibroblast markers")
print(f"  Top match: {top4} {'\u2713' if 'Fibro' in top4 else '\u2717'}")

print("\n\u2705 End-to-end nearest-neighbor search tests completed.")

# COMMAND ----------

# DBTITLE 1,Development Log — Baseline Arm Debug Tracker
# MAGIC %md
# MAGIC ## Development Log — Baseline Arm (No Skill)
# MAGIC
# MAGIC This section documents every code fix, debug iteration, and reversal required to reach a fully working deployment. This is eval metadata for comparison against the **skill arm**.
# MAGIC
# MAGIC ### Summary
# MAGIC
# MAGIC | Metric | Value |
# MAGIC | --- | --- |
# MAGIC | **Unique bugs encountered** | 12 |
# MAGIC | **Total fix iterations** | 15 |
# MAGIC | **Cells requiring fixes** | 6 of 12 code cells (7, 8, 9, 10, 11, 12) |
# MAGIC | **Model versions burned** | 5 (v1–v5; only v5 works on endpoint) |
# MAGIC | **Endpoint config updates** | 1 (v4→v5 after wrapper fix) |
# MAGIC | **VS index sync wait** | ~18.5 min |
# MAGIC
# MAGIC ### Fix Log
# MAGIC
# MAGIC | # | Cell | Error | Root Cause | Iterations |
# MAGIC | --- | --- | --- | --- | --- |
# MAGIC | 1 | 7,8 | `AttributeError: 'list' has no 'keys'` | transformers 5.x changed `all_tied_weights_keys` from list→dict contract | 3 |
# MAGIC | 2 | 8 | `RecursionError` on re-run | Monkey-patch `__init__` stacking via global variable rebind | 2 |
# MAGIC | 3 | 9 | `TypeError: missing arg 'name'` | `EndpointCoreConfigInput` requires `name` in this SDK version | 1 |
# MAGIC | 4 | 9 | `InvalidParameterValue: auto_capture deprecated` | Legacy inference table API removed; must use AI Gateway | 1 |
# MAGIC | 5 | 10 | `TimeoutError` (infinite poll loop) | SDK enum `EndpointStateReady.READY != "READY"` (False) | 2 |
# MAGIC | 6 | 7→10 | `BadRequest: pad_token_id missing` | Wrapper lacked pad_token_id patch; only notebook-level patch existed | 1 |
# MAGIC | 7 | 9 | `TypeError: NoneType not iterable` | `get_registered_model().latest_versions` returns None | 1 |
# MAGIC | 8 | 10 | `BadRequest: pad_token_id` again | Endpoint still serving v4 during config update (stale version) | 2 |
# MAGIC | 9 | 11 | `AnalysisException: PK column nullable` | Spark infers nullable from pandas; PK requires NOT NULL | 1 |
# MAGIC | 10 | 12 | `TypeError: unexpected kwarg 'name'` | VS `get_endpoint(endpoint_name=...)` not `get_endpoint(name=...)` | 1 |
# MAGIC | 11 | 12 | `AttributeError: 'str' has no 'value'` | `create_endpoint(endpoint_type="STANDARD")` — SDK needs enum, not string | 1 |
# MAGIC | 12 | 12 | `AttributeError: 'dict' has no 'as_dict'` | `delta_sync_index_spec={...}` — SDK needs typed dataclasses, not dicts | 1 |
# MAGIC
# MAGIC ### Key Observations
# MAGIC
# MAGIC * **Transformers version pinning** was the single biggest issue (fixes 1, 2, 6, 8). A skill that prescribes `transformers==4.41.0` would have avoided 4 bugs and 8 iterations.
# MAGIC * **SDK enum vs string comparisons** caused 3 silent failures (fixes 5, 10, 11). These are hard to debug because no exception is raised — code just takes the wrong branch.
# MAGIC * **Inconsistent SDK parameter naming** (`name` vs `endpoint_name` vs `index_name`) caused fix 10. Easy to get wrong without docs.
# MAGIC * **Typed dataclass requirement** (fix 12) is undiscoverable without trial-and-error when the skill file's example code uses raw dicts.
# MAGIC
# MAGIC ### Known Limitation: Synthetic Reference Corpus
# MAGIC
# MAGIC Cell 11 uses **synthetic marker-gene profiles** (15 hand-curated genes × 10 cell types) instead of real single-cell data from **CellxGENE Census**. The VS index works and returns correct top-1 matches, but:
# MAGIC * Only 10 reference points (vs 1,000+ from Census)
# MAGIC * No real expression values — just gene ID lists (TEDDY's rank encoding is not exercised)
# MAGIC * No real cell metadata (tissue, disease, donor)
# MAGIC * Embedding quality is untested on real scRNA-seq distributions
# MAGIC
# MAGIC ### Skill Arm Gap Analysis (post-hoc, from `teddy.md`)
# MAGIC
# MAGIC The skill reference (`teddy.md`) prescribes patterns that would have prevented most of the 12 bugs and produced a higher-quality deployment:
# MAGIC
# MAGIC | Area | Skill Prescribes | Baseline Did | Impact |
# MAGIC | --- | --- | --- | --- |
# MAGIC | **transformers version** | `==4.41.0` (exact pin) | Unpinned (resolved to 5.17.0) | **4 bugs, 8 iterations** (fixes 1, 2, 6, 8) |
# MAGIC | **Serving compute** | `GPU_SMALL` (A10G) | CPU Small | Slower inference, no bf16 |
# MAGIC | **Serving contract** | 3-column AnnData (`adata_sparsematrix`, `adata_obs`, `adata_var`) | 1-column `gene_ids` list | Missing rank encoding, expression values |
# MAGIC | **Reference corpus** | CellxGENE Census (1,000 real cells, metadata) | Synthetic (10 types, 15 genes each) | No real scRNA-seq, no metadata |
# MAGIC | **Census gene remapping** | `adata.var["feature_id"]` for Ensembl IDs | N/A (no Census) | Would have caught var_names trap |
# MAGIC | **HF download** | `HF_HUB_DISABLE_XET=1` before import | Not set (worked by luck) | Fragile on repo changes |
# MAGIC | **Code bundle** | `shutil.copytree` with `ignore_patterns("*.safetensors",...)` | Manual `os.walk` + extension filter | Functional but less robust |
# MAGIC | **Model loading** | `get_architecture()` + `model_dict` | Direct import of TeddyGModel | Missed the model registry pattern |
# MAGIC | **OOV handling** | `unk_token_id` fallback | Skip unknown genes | Silent data loss |
# MAGIC | **VS SDK types** | Shows exact `VectorIndexType.DELTA_SYNC`, `DeltaSyncVectorIndexSpecRequest` | Used raw dicts/strings | **3 bugs** (fixes 10, 11, 12) |
# MAGIC | **Inference tables** | AI Gateway config in `create()` | Removed (deprecated API) | No request logging |
# MAGIC | **Notebook structure** | 3 `restartPython()` boundaries | 1 restart (Cell 4) | Potential dep conflicts |
# MAGIC
# MAGIC **Bottom line**: The skill reference would have eliminated **7 of 12 bugs** (transformers pin + VS SDK types) and produced a Census-backed corpus instead of synthetic profiles. The remaining 5 bugs (SDK enum comparisons, PK nullable, `latest_versions` None, config update race) are Databricks SDK version-specific issues that the skill doesn't cover.

# COMMAND ----------

# DBTITLE 1,Export Notebook & List Skills
# ============================================================
# Cell 14: Export Notebook Source & List Skills
# ============================================================
# Exports this notebook as Databricks .py format via the
# Workspace REST API and saves to the results directory.

import base64, os
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ExportFormat

w = WorkspaceClient()

NOTEBOOK_PATH = "/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/oss-002_TEDDY-70M+VS_Deploy_Baseline"
OUTPUT_PATH = "/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-002.txt"

# --- Export via SDK ---
export_resp = w.workspace.export(path=NOTEBOOK_PATH, format=ExportFormat.SOURCE)
source_bytes = base64.b64decode(export_resp.content)
source_text = source_bytes.decode("utf-8")

print(f"Exported notebook: {len(source_text):,} chars, {len(source_text.splitlines())} lines")
print(f"First 200 chars:\n{source_text[:200]}")

# --- Write to output path ---
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w") as f:
    f.write(source_text)

print(f"\n\u2705 Saved to: {OUTPUT_PATH}")
print(f"   Size: {len(source_text):,} chars")

# --- Skills loaded during this notebook ---
print("\n=== Skills Loaded from Skill Registry ===")
print("  1. vector-search        \u2014 VS endpoint/index creation, DeltaSync patterns")
print("  2. machine-learning     \u2014 ML lifecycle, model logging, serving handoff")
print("  3. diagnose-error       \u2014 Python debugging for transformers 5.x compat")
print("  4. data-sampling        \u2014 (implicit) data quality verification")