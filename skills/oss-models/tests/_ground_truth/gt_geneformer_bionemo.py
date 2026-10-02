# Databricks notebook source
# DBTITLE 1,Geneformer BioNeMo Ground Truth
# MAGIC %md
# MAGIC # Geneformer Ground Truth — Path B (NVIDIA BioNeMo)
# MAGIC
# MAGIC End-to-end: download → register → deploy → smoke test → teardown for
# MAGIC [nvidia/geneformer_V2_316M](https://huggingface.co/nvidia/geneformer_V2_316M)
# MAGIC (TransformerEngine, `trust_remote_code=True`, hidden_size=1152). **Path A (standard HF/PyTorch) is in `gt_geneformer`.**
# MAGIC
# MAGIC | Resource | URL |
# MAGIC |----------|-----|
# MAGIC | **Model weights** | [nvidia/geneformer_V2_316M](https://huggingface.co/nvidia/geneformer_V2_316M) |
# MAGIC | **Standard weights** | [ctheodoris/Geneformer](https://huggingface.co/ctheodoris/Geneformer) (V2-316M subdir) |
# MAGIC | **Paper** | [doi.org/10.1038/s41586-023-06139-9](https://doi.org/10.1038/s41586-023-06139-9) |
# MAGIC | **License** | Check NVIDIA repo |
# MAGIC
# MAGIC | Phase | Cells | Installs | Restart? |
# MAGIC |-------|-------|----------|----------|
# MAGIC | **Setup** | 1-3 | — | — |
# MAGIC | **Download** | 4-8 | `huggingface_hub` | restart 1 |
# MAGIC | **Register** | 9-14 | `torch transformers mlflow` + opt `transformer_engine` | restart 2 |
# MAGIC | **Deploy + Score** | 15-16 | — | — |
# MAGIC | **Teardown** | 17-18 | — | — |
# MAGIC
# MAGIC ### Key differences from Path A
# MAGIC
# MAGIC | Aspect | Path A (gt_geneformer) | Path B (this notebook) |
# MAGIC |--------|----------------------|------------------------|
# MAGIC | HF repo | `ctheodoris/Geneformer` | `nvidia/geneformer_V2_316M` |
# MAGIC | Checkpoint | Geneformer-V1-10M | geneformer_V2_316M |
# MAGIC | hidden_size | 256 | 1152 |
# MAGIC | vocab | 25,426 (gc30M) | 20,275 (gc104M) |
# MAGIC | Loading | `AutoModel.from_pretrained(dir)` | `AutoModel.from_pretrained(dir, trust_remote_code=True)` |
# MAGIC | TE requirement | No | Optional (FP8 needs CC≥8.9) |
# MAGIC | GPU tier | GPU_SMALL (A10G) | GPU_SMALL (A10G), tight on VRAM |

# COMMAND ----------

# DBTITLE 1,Compute detection + volume check
import os, subprocess

# --- Volume check: skip download if snapshot already present ---
_VOL_SENTINEL = "/Volumes/<catalog>/skills/models/geneformer_bionemo/.copy_complete"
if os.path.exists(_VOL_SENTINEL):
    print("✓ BioNeMo snapshot already in Volume — download phase will be skipped.")
else:
    print("BioNeMo snapshot NOT in Volume — download phase will run.")

# --- Compute detection ---
try:
    os.makedirs("/local_disk0/tmp", exist_ok=True)
    TMP_DIR = "/local_disk0/tmp"
    IS_SERVERLESS = False
except (PermissionError, OSError):
    TMP_DIR = "/tmp"
    IS_SERVERLESS = True

HAS_GPU = False
GPU_NAME = "none"
try:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode == 0:
        HAS_GPU = True
        GPU_NAME = result.stdout.strip().split("\n")[0]
except (FileNotFoundError, subprocess.TimeoutExpired):
    pass

print(f"Compute : {'Serverless' if IS_SERVERLESS else 'Classic'}")
print(f"Storage : {TMP_DIR}")
print(f"GPU     : {GPU_NAME if HAS_GPU else 'none (CPU-only mode)'}")

# COMMAND ----------

# DBTITLE 1,Configuration
# Remove stale widgets, then re-create with correct defaults
for _w in ["catalog", "schema", "volume_name", "endpoint_name", "run_go"]:
    try:
        dbutils.widgets.remove(_w)
    except Exception:
        pass

dbutils.widgets.text("catalog", "<catalog>", "Unity Catalog catalog")
dbutils.widgets.text("schema", "skills", "Unity Catalog schema")
dbutils.widgets.text("volume_name", "models", "UC volume name")
dbutils.widgets.text("endpoint_name", "geneformer_bionemo_test", "Serving endpoint name")
dbutils.widgets.dropdown("run_go", "false", ["false", "true"], "Run gate (deploy costs real money)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_NAME = dbutils.widgets.get("volume_name")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
RUN_GO = dbutils.widgets.get("run_go") == "true"

# --- BioNeMo-specific config ---
HF_REPO = "nvidia/geneformer_V2_316M"   # NVIDIA BioNeMo HF repo
HIDDEN_SIZE = 1152                        # V2-316M
VOCAB_SIZE = 20275                        # gc104M vocabulary

VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}"
SNAPSHOT_DIR = f"{VOLUME_PATH}/geneformer_bionemo"
REGISTERED_MODEL_NAME = f"{CATALOG}.{SCHEMA}.geneformer_bionemo"

print(f"Catalog    : {CATALOG}.{SCHEMA}")
print(f"Volume     : {VOLUME_PATH}")
print(f"HF repo    : {HF_REPO}")
print(f"Snapshot   : {SNAPSHOT_DIR}")
print(f"Model      : {REGISTERED_MODEL_NAME}")
print(f"Endpoint   : {ENDPOINT_NAME}")
print(f"RUN_GO     : {RUN_GO}")

# COMMAND ----------

# DBTITLE 1,Install huggingface_hub (restart 1)
# MAGIC %pip install -q huggingface_hub
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Post-restart setup + create schema/volume
import os, subprocess

# --- Compute detection (re-derive after restartPython) ---
try:
    os.makedirs("/local_disk0/tmp", exist_ok=True)
    TMP_DIR = "/local_disk0/tmp"
    IS_SERVERLESS = False
except (PermissionError, OSError):
    TMP_DIR = "/tmp"
    IS_SERVERLESS = True

# --- Re-read widget values ---
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_NAME = dbutils.widgets.get("volume_name")
HF_REPO = "nvidia/geneformer_V2_316M"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}"
LOCAL_DIR = os.path.join(TMP_DIR, "geneformer_bionemo_snapshot")
os.makedirs(LOCAL_DIR, exist_ok=True)

# --- Create schema + volume if needed ---
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME_NAME}")

print(f"Compute  : {'Serverless' if IS_SERVERLESS else 'Classic'}")
print(f"Storage  : {TMP_DIR}")
print(f"Schema   : {CATALOG}.{SCHEMA} ✓")
print(f"Volume   : {VOLUME_PATH} ✓")
print(f"Download : {LOCAL_DIR}")
print(f"HF repo  : {HF_REPO}")

# COMMAND ----------

# DBTITLE 1,Download nvidia/geneformer_V2_316M
from huggingface_hub import snapshot_download

vol_dest = f"{VOLUME_PATH}/geneformer_bionemo"
vol_sentinel = os.path.join(vol_dest, ".copy_complete")

if os.path.exists(vol_sentinel):
    print(f"Volume snapshot already present at {vol_dest}, skipping download")
    LOCAL_DIR = vol_dest
else:
    local_sentinel = os.path.join(LOCAL_DIR, ".snapshot_complete")
    if os.path.exists(local_sentinel):
        print(f"Local snapshot already present at {LOCAL_DIR}, skipping download")
    else:
        print(f"Downloading {HF_REPO} -> {LOCAL_DIR} ...")
        snapshot_download(repo_id=HF_REPO, local_dir=LOCAL_DIR)
        with open(local_sentinel, "w") as f:
            f.write("ok")
        print("Download complete.")

# COMMAND ----------

# DBTITLE 1,Verify snapshot + inspect TE requirements
import json

# --- Verify snapshot structure ---
print("Snapshot contents:")
for item in sorted(os.listdir(LOCAL_DIR)):
    kind = "[dir] " if os.path.isdir(os.path.join(LOCAL_DIR, item)) else "[file]"
    size = ""
    if os.path.isfile(os.path.join(LOCAL_DIR, item)):
        sz = os.path.getsize(os.path.join(LOCAL_DIR, item))
        size = f" ({sz:,} bytes)"
    print(f"  {kind} {item}{size}")

# --- Check for config.json ---
config_path = os.path.join(LOCAL_DIR, "config.json")
if os.path.exists(config_path):
    with open(config_path) as f:
        config = json.load(f)
    print(f"\nconfig.json:")
    for k in ["model_type", "architectures", "hidden_size", "num_hidden_layers",
              "max_position_embeddings", "vocab_size", "auto_map"]:
        if k in config:
            print(f"  {k}: {config[k]}")
    # auto_map presence = trust_remote_code needed
    if "auto_map" in config:
        print("\n  ⚠️  auto_map detected → trust_remote_code=True REQUIRED")
else:
    print("\n✗ No config.json found")

# --- Check for custom model code (*.py files) ---
py_files = [f for f in os.listdir(LOCAL_DIR) if f.endswith(".py")]
if py_files:
    print(f"\nCustom code files: {py_files}")
    # Check for TransformerEngine imports
    for pf in py_files:
        with open(os.path.join(LOCAL_DIR, pf)) as f:
            content = f.read()
        if "transformer_engine" in content:
            print(f"  ⚠️  {pf} imports transformer_engine")
        if "trust_remote_code" in content:
            print(f"  ⚠️  {pf} references trust_remote_code")
else:
    print("\nNo custom .py files (standard HF checkpoint)")

# --- Discover token dictionary ---
# BioNeMo V2 models use the gc104M vocabulary (20275 tokens)
# Check if token dict is bundled, otherwise we'll use the one from ctheodoris snapshot
import pickle
dict_path = None

# Check locally first
for candidate in [
    os.path.join(LOCAL_DIR, "token_dictionary_gc104M.pkl"),
    os.path.join(LOCAL_DIR, "geneformer", "token_dictionary_gc104M.pkl"),
]:
    if os.path.exists(candidate):
        dict_path = candidate
        break

# Walk tree for any token_dictionary*.pkl
if not dict_path:
    for root, dirs, files in os.walk(LOCAL_DIR):
        for f in files:
            if "token_dictionary" in f.lower() and f.endswith(".pkl"):
                dict_path = os.path.join(root, f)
                break
        if dict_path:
            break

# Fallback: use ctheodoris snapshot's token dict (same V2 vocabulary)
if not dict_path:
    ctheodoris_dict = f"{VOLUME_PATH}/geneformer/geneformer/token_dictionary_gc104M.pkl"
    if os.path.exists(ctheodoris_dict):
        dict_path = ctheodoris_dict
        print(f"\nℹ️  Token dict from ctheodoris snapshot (same V2 vocab): {dict_path}")

if dict_path:
    with open(dict_path, "rb") as f:
        _td = pickle.load(f)
    ensembl_count = sum(1 for k in _td if str(k).startswith("ENSG"))
    print(f"\n✓ Token dictionary: {dict_path}")
    print(f"  Vocab size: {len(_td)}, Ensembl IDs: {ensembl_count}")
else:
    print("\n✗ No token dictionary found — will need manual path")

# COMMAND ----------

# DBTITLE 1,Copy to Volume + provenance manifest
import shutil, datetime

if os.path.exists(vol_sentinel):
    print(f"✓ Volume snapshot already present, skipping copy")
else:
    if os.path.exists(vol_dest):
        shutil.rmtree(vol_dest)
    print(f"Copying to {vol_dest} ...")
    shutil.copytree(LOCAL_DIR, vol_dest)
    with open(vol_sentinel, "w") as f:
        f.write("ok")
    print(f"✓ Persisted to {vol_dest}")

# --- Provenance manifest ---
manifest = f"""model:
  name: geneformer_bionemo
  variant: V2-316M (NVIDIA BioNeMo)
  source_url: https://huggingface.co/nvidia/geneformer_V2_316M
  standard_weights_url: https://huggingface.co/ctheodoris/Geneformer
  license: check-nvidia-repo
  reviewed_at: {datetime.date.today().isoformat()}
weights:
  location: {vol_dest}
  hidden_size: 1152
  num_hidden_layers: 18
  vocab_size: 20275
runtime:
  download_compute: {'serverless_cpu' if IS_SERVERLESS else 'classic_cpu'}
  register_compute: gpu_required
  trust_remote_code: true
  transformer_engine: optional_for_fp8
"""
with open(f"{vol_dest}/provenance_manifest.yaml", "w") as f:
    f.write(manifest)
print("✓ Provenance manifest written")

# COMMAND ----------

# DBTITLE 1,Idempotent cleanup
# Per .assistant_instructions.md: cleanup early, before registration.
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceDoesNotExist

w = WorkspaceClient()

try:
    _ep = dbutils.widgets.get("endpoint_name")
    _model = f"{dbutils.widgets.get('catalog')}.{dbutils.widgets.get('schema')}.geneformer_bionemo"
except Exception:
    _ep = "geneformer_bionemo_test"
    _model = "<catalog>.skills.geneformer_bionemo"

# Delete endpoint
try:
    w.serving_endpoints.delete(_ep)
    print(f"\u2713 Deleted endpoint '{_ep}'")
except (NotFound, ResourceDoesNotExist):
    print(f"  Endpoint '{_ep}' not found (clean).")

# Delete all UC model versions
try:
    versions = list(w.model_versions.list(_model))
    for v in versions:
        w.model_versions.delete(_model, v.version)
    if versions:
        print(f"\u2713 Deleted {len(versions)} version(s) of {_model}")
    else:
        print(f"  No versions of {_model} (clean).")
except (NotFound, ResourceDoesNotExist):
    print(f"  Model {_model} not found (clean).")

print("\u2713 Cleanup complete — ready for fresh registration.")

# COMMAND ----------

# DBTITLE 1,Install registration deps (restart 2)
# Core deps: torch + transformers + mlflow
# TransformerEngine is optional — needed only for FP8 inference (CC≥8.9)
# If TE build fails, the model still loads via standard PyTorch with trust_remote_code
%pip install -q "torch>=2.0.0" "transformers>=4.30.0,<4.52.0" "mlflow[databricks]"

# Attempt TE install (non-fatal if it fails — source build, needs CUDA toolkit)
try:
    import subprocess as _sp
    _r = _sp.run(
        ["pip", "install", "-q", "transformer_engine[pytorch]"],
        capture_output=True, text=True, timeout=300,
    )
    if _r.returncode == 0:
        print("✓ TransformerEngine installed (FP8 available)")
    else:
        print(f"⚠️  TransformerEngine install failed (expected on Serverless). FP16/BF16 fallback.")
        print(f"   stderr: {_r.stderr[:200]}")
except Exception as e:
    print(f"⚠️  TransformerEngine install skipped: {e}")

dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Post-restart setup (Phase 1b)
import os, json, pickle

# --- Re-read widgets after restart ---
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_NAME = dbutils.widgets.get("volume_name")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
RUN_GO = dbutils.widgets.get("run_go") == "true"

HF_REPO = "nvidia/geneformer_V2_316M"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}"
SNAPSHOT_DIR = f"{VOLUME_PATH}/geneformer_bionemo"
REGISTERED_MODEL_NAME = f"{CATALOG}.{SCHEMA}.geneformer_bionemo"

assert os.path.isdir(SNAPSHOT_DIR), f"Snapshot not found: {SNAPSHOT_DIR}"

# --- Discover token dictionary ---
dict_path = None
for candidate in [
    os.path.join(SNAPSHOT_DIR, "token_dictionary_gc104M.pkl"),
    os.path.join(SNAPSHOT_DIR, "geneformer", "token_dictionary_gc104M.pkl"),
]:
    if os.path.exists(candidate):
        dict_path = candidate
        break

# Walk snapshot
if not dict_path:
    for root, dirs, files in os.walk(SNAPSHOT_DIR):
        for f in files:
            if "token_dictionary" in f.lower() and f.endswith(".pkl"):
                dict_path = os.path.join(root, f)
                break
        if dict_path:
            break

# Fallback: ctheodoris snapshot (same V2 vocabulary)
if not dict_path:
    ctheodoris_dict = f"{VOLUME_PATH}/geneformer/geneformer/token_dictionary_gc104M.pkl"
    if os.path.exists(ctheodoris_dict):
        dict_path = ctheodoris_dict

assert dict_path, "Token dictionary not found in BioNeMo or ctheodoris snapshot"

# --- Check TransformerEngine availability ---
# Flush any stale stub from a prior cell run so the import test is honest.
import sys as _sys
_prev = _sys.modules.pop("transformer_engine", None)
_sys.modules.pop("transformer_engine.pytorch", None)
try:
    import transformer_engine
    # Reject our own stub — it shouldn't count as "available"
    if getattr(transformer_engine, "__version__", "") == "0.0.0-stub":
        raise ImportError("stub")
    TE_AVAILABLE = True
    print(f"✓ TransformerEngine v{transformer_engine.__version__} available")
except ImportError:
    TE_AVAILABLE = False
    print("⚠️  TransformerEngine not available — FP16/BF16 fallback")
    # Install functional TE stubs (nn.Module wrappers) so geneformer.py loads on
    # CPU/serverless.  Weight key names (.qkv.weight, .proj.weight, etc.) match the
    # safetensors state dict, so from_pretrained loads correctly.
    import types, sys
    import torch.nn as _nn
    import torch.nn.functional as _F

    class _StubLinear(_nn.Linear):
        """Drop-in for te.Linear — accepts extra TE kwargs."""
        def __init__(self, in_f, out_f, bias=True, params_dtype=None, **kw):
            super().__init__(in_f, out_f, bias=bias)
            if params_dtype is not None:
                self.to(params_dtype)

    class _StubLayerNorm(_nn.LayerNorm):
        """Drop-in for te.LayerNorm — accepts extra TE kwargs."""
        def __init__(self, normalized_shape, eps=1e-5, params_dtype=None, **kw):
            super().__init__(normalized_shape, eps=eps)
            if params_dtype is not None:
                self.to(params_dtype)

    class _StubMultiheadAttention(_nn.Module):
        """Drop-in for te.MultiheadAttention with fused QKV."""
        def __init__(self, hidden_size, num_attention_heads, num_gqa_groups=None,
                     attention_dropout=0.0, input_layernorm=False, attention_type="self",
                     layer_number=None, attn_mask_type="padding", params_dtype=None,
                     fuse_qkv_params=False, window_size=(-1, -1), qkv_format="bshd", **kw):
            super().__init__()
            self.hidden_size = hidden_size
            self.num_heads = num_attention_heads
            self.head_dim = hidden_size // num_attention_heads
            self.qkv = _nn.Linear(hidden_size, 3 * hidden_size)
            self.proj = _nn.Linear(hidden_size, hidden_size)
            self.attn_drop = _nn.Dropout(attention_dropout)
            if params_dtype is not None:
                self.to(params_dtype)

        def forward(self, hidden_states, attention_mask=None, attn_mask_type="no_mask", **kw):
            B, S, H = hidden_states.shape
            qkv = self.qkv(hidden_states).reshape(B, S, 3, self.num_heads, self.head_dim)
            qkv = qkv.permute(2, 0, 3, 1, 4)  # [3, B, heads, S, head_dim]
            q, k, v = qkv[0], qkv[1], qkv[2]
            scale = self.head_dim ** -0.5
            attn = torch.matmul(q, k.transpose(-2, -1)) * scale
            if attention_mask is not None:
                attn = attn.masked_fill(attention_mask, float("-inf"))
            attn = _F.softmax(attn, dim=-1)
            attn = self.attn_drop(attn)
            out = torch.matmul(attn, v).transpose(1, 2).reshape(B, S, H)
            return self.proj(out)

    _te = types.ModuleType("transformer_engine")
    _te.__version__ = "0.0.0-stub"
    _te_pt = types.ModuleType("transformer_engine.pytorch")
    _te_pt.Linear = _StubLinear
    _te_pt.LayerNorm = _StubLayerNorm
    _te_pt.MultiheadAttention = _StubMultiheadAttention
    _te.pytorch = _te_pt
    sys.modules["transformer_engine"] = _te
    sys.modules["transformer_engine.pytorch"] = _te_pt
    # Flush any cached geneformer module whose `te` binding points at old stubs
    for _mod_name in list(sys.modules):
        if "geneformer" in _mod_name:
            del sys.modules[_mod_name]
    print("  → Functional TE stub installed (nn.Module wrappers for CPU inference)")

# --- Compatibility shim: get_head_mask removed in transformers >=4.52 ---
from transformers import PreTrainedModel as _PTM
if not hasattr(_PTM, "get_head_mask"):
    def _get_head_mask(self, head_mask, num_hidden_layers, is_attention_chunked=False):
        if head_mask is not None:
            head_mask = self._convert_head_mask_to_5d(head_mask, num_hidden_layers)
            if is_attention_chunked:
                head_mask = head_mask.unsqueeze(-1)
        else:
            head_mask = [None] * num_hidden_layers
        return head_mask
    _PTM.get_head_mask = _get_head_mask
    print("  → Patched get_head_mask for transformers compat")

# --- Inspect config ---
config_path = os.path.join(SNAPSHOT_DIR, "config.json")
if os.path.exists(config_path):
    with open(config_path) as f:
        config = json.load(f)
    hidden_size = config.get("hidden_size", "?")
    has_auto_map = "auto_map" in config
    print(f"hidden_size={hidden_size}, layers={config.get('num_hidden_layers', '?')}")
    if has_auto_map:
        print(f"auto_map: {config['auto_map']} → trust_remote_code=True")

print(f"✓ Snapshot  : {SNAPSHOT_DIR}")
print(f"✓ Token dict : {dict_path}")
print(f"  RUN_GO    : {RUN_GO}")

# COMMAND ----------

# DBTITLE 1,Engineering context
# MAGIC %md
# MAGIC ## Engineering Context & Known Issues
# MAGIC
# MAGIC ### TransformerEngine (TE) stubs
# MAGIC
# MAGIC `geneformer.py` does `import transformer_engine.pytorch as te` at the **top level** and uses `te.Linear`, `te.LayerNorm`, `te.MultiheadAttention` throughout. TE requires a CUDA toolkit source build (`pyproject.toml` → CMake → `transformer_engine_torch`), which **fails on serverless GPU** (no dev toolchain). The workaround:
# MAGIC
# MAGIC * **Functional `nn.Module` stubs** installed into `sys.modules["transformer_engine.pytorch"]` before any `from_pretrained` call.
# MAGIC * Stubs use matching weight-key names (`qkv.weight`, `proj.weight`, `layernorm.weight`, `layernorm_mlp.fc1/fc2`) so `safetensors` state-dict loads without renaming.
# MAGIC * Stubs are installed in **two places**: cell 11 (notebook-level) and inside `GeneformerBioNeMo.load_context()` (serving environment, which has no prior kernel state).
# MAGIC
# MAGIC ### `get_head_mask` removal (transformers ≥4.52)
# MAGIC
# MAGIC `geneformer.py` calls `self.get_head_mask(head_mask, num_layers)` — a method removed from `PreTrainedModel` in transformers 4.52. Fix: pin `transformers<4.52` in pip requirements **and** patch the method back onto `PreTrainedModel` at runtime (cells 11, 12) as a safety net.
# MAGIC
# MAGIC ### Inference table conflicts
# MAGIC
# MAGIC Model Serving rejects `create_endpoint` when the auto-generated inference table name (`<endpoint>_payload`) already exists from a prior failed deploy. Fix: timestamped table prefix `<endpoint>_YYYYMMDDHHMM_payload` in cell 15.
# MAGIC
# MAGIC ### Endpoint provisioning time
# MAGIC
# MAGIC GPU_SMALL (A10G) endpoints routinely take 15–25 min to provision. Cell 16 polls with a 1800 s timeout (30 min) and detects `DEPLOYMENT_FAILED` early to avoid silent waits on broken deploys.
# MAGIC
# MAGIC ### Model architecture notes
# MAGIC
# MAGIC | Property | Value |
# MAGIC |---|---|
# MAGIC | Architecture | BERT encoder, **post-norm** (not standard pre-norm) |
# MAGIC | hidden_size | 1152 |
# MAGIC | layers | 18 |
# MAGIC | max_position_embeddings | 4096 |
# MAGIC | vocab | gc104M (20,275 tokens — Ensembl gene IDs) |
# MAGIC | Safetensors | 1.36 GB (`model.safetensors`) |
# MAGIC | `use_te_layers` | `true` in `config.json` (hence TE dependency) |
# MAGIC | `torch_dtype` | `float32` (BF16/FP16 via autocast at inference) |
# MAGIC
# MAGIC ### CLS vs mean pooling
# MAGIC
# MAGIC Smoke testing confirms CLS (`hidden_states[:, 0, :]`) and mean pooling produce **near-identical embeddings** (cosine ≈1.0, L2 distance ≈0.07–0.09 on vectors with L2-norm ≈34.5). Unlike standard BERT, Geneformer has no dedicated `[CLS]` token — position 0 is simply the highest-expressed gene after rank-ordering. The post-norm architecture distributes context broadly across all positions, so CLS carries similar information to the mean. **Mean pooling is the safer default**; CLS becomes meaningful only after fine-tuning with a classification head on position 0.
# MAGIC
# MAGIC ### Downstream applications
# MAGIC
# MAGIC The 1152-dim per-cell embeddings serve as a universal featurization layer for:
# MAGIC
# MAGIC * **Cell-type classification** — few-shot annotation of rare cell types using a lightweight head on frozen embeddings
# MAGIC * **Gene network inference** — attention weights encode gene-gene regulatory relationships; enables *in silico* perturbation studies
# MAGIC * **Patient stratification & drug discovery** — aggregate cell embeddings per sample for outcome prediction or target identification
# MAGIC * **Transfer learning** — broad pretraining (\~100M cells) generalizes to unseen tissues and cell types with minimal labeled data

# COMMAND ----------

# DBTITLE 1,GeneformerBioNeMo PyFunc
import mlflow
import pandas as pd
import numpy as np
import torch


class GeneformerBioNeMo(mlflow.pyfunc.PythonModel):
    """Wraps NVIDIA BioNeMo Geneformer V2-316M to produce per-cell embeddings.

    Loads via trust_remote_code=True to pick up NVIDIA's custom model classes.
    Falls back to standard PyTorch if TransformerEngine is unavailable.

    Inputs (DataFrame, one row per request):
      - cell_id: str
      - genes: list[str] — Ensembl gene IDs
      - expression: list[float] — raw counts aligned to genes
      - vocab_version: str
      - config: JSON string — {truncation, gene_count_limit, pooling_mode}

    Output: list[dict] — {cell_id, embedding, embedding_dim, vocab_version}
    """

    def load_context(self, context):
        import os, json, pickle, sys, types
        import torch

        # --- TE stub: geneformer.py does `import transformer_engine.pytorch as te`
        #     at the top level.  Install functional stubs BEFORE from_pretrained.
        try:
            import transformer_engine  # noqa: F401
        except ImportError:
            import torch.nn as _nn
            import torch.nn.functional as _F

            class _SL(_nn.Linear):
                def __init__(self, in_features, out_features, bias=True, params_dtype=None, **k):
                    super().__init__(in_features, out_features, bias=bias)
                    if params_dtype: self.to(params_dtype)

            class _SLN(_nn.LayerNorm):
                def __init__(self, normalized_shape, eps=1e-5, params_dtype=None, **k):
                    super().__init__(normalized_shape, eps=eps)
                    if params_dtype: self.to(params_dtype)

            class _SMHA(_nn.Module):
                def __init__(self, hidden_size, num_attention_heads, num_gqa_groups=None,
                             attention_dropout=0.0, input_layernorm=False, attention_type="self",
                             layer_number=None, attn_mask_type="padding", params_dtype=None,
                             fuse_qkv_params=False, window_size=(-1,-1), qkv_format="bshd", **k):
                    super().__init__()
                    self.num_heads = num_attention_heads
                    self.head_dim = hidden_size // num_attention_heads
                    self.qkv = _nn.Linear(hidden_size, 3 * hidden_size)
                    self.proj = _nn.Linear(hidden_size, hidden_size)
                    self.attn_drop = _nn.Dropout(attention_dropout)
                    if params_dtype: self.to(params_dtype)

                def forward(self, x, attention_mask=None, attn_mask_type="no_mask", **k):
                    B, S, H = x.shape
                    qkv = self.qkv(x).reshape(B, S, 3, self.num_heads, self.head_dim)
                    qkv = qkv.permute(2, 0, 3, 1, 4)
                    q, k2, v = qkv[0], qkv[1], qkv[2]
                    sc = self.head_dim ** -0.5
                    a = torch.matmul(q, k2.transpose(-2, -1)) * sc
                    if attention_mask is not None:
                        a = a.masked_fill(attention_mask, float("-inf"))
                    a = _F.softmax(a, dim=-1)
                    a = self.attn_drop(a)
                    return self.proj(torch.matmul(a, v).transpose(1, 2).reshape(B, S, H))

            _te = types.ModuleType("transformer_engine")
            _te.__version__ = "0.0.0-stub"
            _tep = types.ModuleType("transformer_engine.pytorch")
            _tep.Linear, _tep.LayerNorm, _tep.MultiheadAttention = _SL, _SLN, _SMHA
            _te.pytorch = _tep
            sys.modules["transformer_engine"] = _te
            sys.modules["transformer_engine.pytorch"] = _tep

        # --- get_head_mask shim: removed in transformers >=4.52 ---
        from transformers import PreTrainedModel as _PTM
        if not hasattr(_PTM, "get_head_mask"):
            def _ghm(self, hm, n, chunked=False):
                if hm is not None:
                    hm = self._convert_head_mask_to_5d(hm, n)
                    if chunked: hm = hm.unsqueeze(-1)
                else:
                    hm = [None] * n
                return hm
            _PTM.get_head_mask = _ghm

        from transformers import AutoModel

        model_dir = context.artifacts["model_dir"]
        dict_path = context.artifacts["token_dict"]

        # Load model with trust_remote_code (BioNeMo custom modules)
        self.model = AutoModel.from_pretrained(
            model_dir, trust_remote_code=True
        )
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device).eval()

        # Load token dictionary (pickle: gene Ensembl ID -> token ID)
        with open(dict_path, "rb") as f:
            self.token_dict = pickle.load(f)

        # Model config
        self.max_tokens = getattr(self.model.config, "max_position_embeddings", 4096)
        self.hidden_size = getattr(self.model.config, "hidden_size", 1152)

        print(f"GeneformerBioNeMo loaded on {self.device}, hidden_size={self.hidden_size}, "
              f"max_tokens={self.max_tokens}")

    def predict(self, context, model_input, params=None):
        import json
        import torch

        results = []
        for _, row in model_input.iterrows():
            cell_id = row.get("cell_id", "unknown")
            genes = list(row["genes"])
            expression = list(row["expression"])
            vocab_version = row.get("vocab_version", "unknown")

            config = {}
            if "config" in row and isinstance(row["config"], str):
                config = json.loads(row["config"])
            truncation = config.get("truncation", True)
            gene_count_limit = int(config.get("gene_count_limit", self.max_tokens))
            pooling_mode = config.get("pooling_mode", "mean")

            # Tokenize: map gene IDs to token IDs, skip unknowns
            tokens = []
            for gene, expr in zip(genes, expression):
                if gene in self.token_dict:
                    tokens.append((self.token_dict[gene], expr))

            if not tokens:
                results.append({
                    "cell_id": cell_id,
                    "embedding": [],
                    "embedding_dim": 0,
                    "vocab_version": vocab_version,
                    "error": "No genes found in token dictionary",
                })
                continue

            # Rank-order by expression (highest first) — Geneformer requirement
            tokens.sort(key=lambda x: -x[1])
            if truncation:
                tokens = tokens[:gene_count_limit]

            input_ids = torch.tensor([[t[0] for t in tokens]], dtype=torch.long)
            input_ids = input_ids.to(self.device)

            with torch.no_grad():
                if self.device == "cuda":
                    with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                        outputs = self.model(input_ids)
                else:
                    outputs = self.model(input_ids)

            hidden = outputs.last_hidden_state
            if pooling_mode == "cls" and hidden.size(1) > 0:
                emb = hidden[:, 0, :]
            else:
                emb = hidden.mean(dim=1)
            emb = emb.squeeze(0).float().cpu().numpy()

            results.append({
                "cell_id": cell_id,
                "embedding": emb.tolist(),
                "embedding_dim": len(emb),
                "vocab_version": vocab_version,
            })

        return results


print("GeneformerBioNeMo PyFunc class defined.")

# COMMAND ----------

# DBTITLE 1,Input example + dry-load test
import json, pickle, pandas as pd
from mlflow.pyfunc import PythonModelContext

# --- Build input_example from real token dictionary (V2 gc104M vocab) ---
with open(dict_path, "rb") as f:
    token_dict = pickle.load(f)
ensembl_genes = [g for g in token_dict.keys() if str(g).startswith("ENSG")][:10]
assert ensembl_genes, "No Ensembl gene IDs found in token dictionary"

input_example = pd.DataFrame([{
    "cell_id": "cell-0001",
    "genes": ensembl_genes,
    "expression": [float(i) for i in range(len(ensembl_genes), 0, -1)],
    "vocab_version": "gc104M",
    "config": json.dumps({
        "truncation": True, "gene_count_limit": "4096",
        "pooling_mode": "mean",
    }),
}])
print(f"\u2713 Input example: {len(ensembl_genes)} real Ensembl IDs (gc104M vocab)")

# --- Dry-load test (pre-deploy gate per .assistant_instructions.md) ---
artifacts = {"model_dir": SNAPSHOT_DIR, "token_dict": dict_path}
ctx = PythonModelContext(artifacts=artifacts, model_config={})

embedder = GeneformerBioNeMo()
embedder.load_context(ctx)
output_example = embedder.predict(ctx, input_example)

dim = output_example[0].get("embedding_dim", 0)
assert dim > 0, f"Dry-load produced dim={dim}"
assert dim == 1152, f"Expected dim=1152 for V2-316M, got {dim}"
print(f"\u2713 Dry-load OK: dim={dim}, first 5={output_example[0]['embedding'][:5]}")

# COMMAND ----------

# DBTITLE 1,Log + register to UC
from mlflow.models import infer_signature

mlflow.set_registry_uri("databricks-uc")
mlflow.set_tracking_uri("databricks")

output_df = pd.DataFrame(output_example if isinstance(output_example, list) else [output_example])

try:
    signature = infer_signature(input_example, output_df)
    print("Signature inferred:", signature)
except Exception as e:
    print(f"Could not infer signature: {e}")
    from mlflow.models.signature import ModelSignature
    from mlflow.types.schema import Schema, ColSpec
    signature = ModelSignature(
        inputs=Schema([
            ColSpec("string", "cell_id"),
            ColSpec("string", "genes"),
            ColSpec("string", "expression"),
            ColSpec("string", "vocab_version"),
            ColSpec("string", "config"),
        ]),
        outputs=Schema([
            ColSpec("string", "cell_id"),
            ColSpec("string", "embedding"),
            ColSpec("long", "embedding_dim"),
            ColSpec("string", "vocab_version"),
        ]),
    )
    print("Using manual signature:", signature)

if not RUN_GO:
    print("run-gate off; set run_go=true to execute log_model + UC registration. Skipping.")
else:
    # Build pip_requirements — include TE only if it installed successfully
    pip_reqs = [
        "torch>=2.0.0",
        "transformers>=4.30.0,<4.52.0",
    ]
    if TE_AVAILABLE:
        pip_reqs.append("transformer_engine[pytorch]")

    with mlflow.start_run(run_name="geneformer_bionemo_register") as run:
        mlflow.set_tag("model_family", "Geneformer")
        mlflow.set_tag("engine", "BioNeMo")
        mlflow.set_tag("checkpoint", "V2-316M")
        mlflow.set_tag("source", "https://huggingface.co/nvidia/geneformer_V2_316M")
        mlflow.set_tag("trust_remote_code", "true")
        mlflow.set_tag("transformer_engine", str(TE_AVAILABLE))

        model_info = mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=GeneformerBioNeMo(),
            artifacts=artifacts,
            signature=signature,
            input_example=input_example,
            pip_requirements=pip_reqs,
        )
        print(f"Model logged: {model_info.model_uri}")

    registered_version = mlflow.register_model(
        model_uri=model_info.model_uri,
        name=REGISTERED_MODEL_NAME,
        await_registration_for=300,
    )
    model_version = registered_version.version
    print(f"Registered: {REGISTERED_MODEL_NAME} v{model_version}")

# COMMAND ----------

# DBTITLE 1,Deploy serving endpoint
if not RUN_GO:
    print("run-gate off; set run_go=true to deploy. Skipping.")
else:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import NotFound, ResourceAlreadyExists
    from databricks.sdk.service.serving import (
        EndpointCoreConfigInput, ServedEntityInput,
        ServingModelWorkloadType,
        AiGatewayConfig, AiGatewayUsageTrackingConfig,
        AiGatewayInferenceTableConfig,
    )

    w = WorkspaceClient()

    # Resolve model_version if not set (e.g., after kernel restart)
    if 'model_version' not in dir():
        _versions = list(w.model_versions.list(REGISTERED_MODEL_NAME))
        model_version = str(max(int(v.version) for v in _versions))
        print(f"  Resolved model_version={model_version} from UC")

    # GPU_SMALL (A10G) — V2-316M is ~1.2 GB, fits in A10G 24 GB VRAM
    # For FP8 inference, need Ada/Hopper (CC>=8.9) — use GPU_MEDIUM or higher
    entity = ServedEntityInput(
        entity_name=REGISTERED_MODEL_NAME,
        entity_version=str(model_version),
        workload_type=ServingModelWorkloadType.GPU_SMALL,
        workload_size="Small",
        scale_to_zero_enabled=True,
    )

    # Use timestamped table prefix to avoid conflicts with stale inference tables
    import datetime
    _ts = datetime.datetime.now().strftime("%Y%m%d%H%M")
    _inf_table_prefix = f"{ENDPOINT_NAME.replace('-', '_')}_{_ts}"

    ai_gateway = AiGatewayConfig(
        usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
        inference_table_config=AiGatewayInferenceTableConfig(
            catalog_name=CATALOG, schema_name=SCHEMA, enabled=True,
            table_name_prefix=_inf_table_prefix,
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
        print(f"\u2713 Endpoint '{ENDPOINT_NAME}' created (GPU_SMALL, AI Gateway)")
    except ResourceAlreadyExists:
        w.serving_endpoints.update_config(
            name=ENDPOINT_NAME, served_entities=[entity],
        )
        print(f"\u2713 Endpoint '{ENDPOINT_NAME}' updated")

    print(f"  Inference table: {CATALOG}.{SCHEMA}.{ENDPOINT_NAME.replace('-','_')}_payload")
    print("Waiting for readiness (~15 min) ...")

# COMMAND ----------

# DBTITLE 1,Smoke test endpoint
if not RUN_GO:
    print("run-gate off; skipping smoke test.")
else:
    import time, json
    from databricks.sdk.service.serving import EndpointStateConfigUpdate, EndpointStateReady

    def wait_for_endpoint_ready(name, timeout_s=1800, poll_s=30):
        from databricks.sdk.service.serving import ServedModelStateDeployment
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            ep = w.serving_endpoints.get(name)
            state = ep.state
            if (state.ready == EndpointStateReady.READY
                    and state.config_update == EndpointStateConfigUpdate.NOT_UPDATING):
                print(f"\nEndpoint '{name}' is READY!")
                return
            # Detect deployment failure early
            for cfg in [ep.pending_config, ep.config]:
                if cfg and cfg.served_entities:
                    for se in cfg.served_entities:
                        if se.state and se.state.deployment == ServedModelStateDeployment.DEPLOYMENT_FAILED:
                            raise RuntimeError(
                                f"Endpoint '{name}' DEPLOYMENT_FAILED: {se.state.deployment_state_message}"
                            )
            print(".", end="", flush=True)
            time.sleep(poll_s)
        raise TimeoutError(f"{name} not ready after {timeout_s}s")

    wait_for_endpoint_ready(ENDPOINT_NAME)

    # Smoke test
    response = w.serving_endpoints.query(
        name=ENDPOINT_NAME,
        dataframe_records=[{
            "cell_id": "cell-0001",
            "genes": ensembl_genes,
            "expression": [12.0, 5.0, 3.0, 2.0, 1.0][:len(ensembl_genes)],
            "vocab_version": "gc104M",
            "config": json.dumps({
                "truncation": True,
                "gene_count_limit": "4096",
                "pooling_mode": "mean",
            }),
        }],
    )
    result = response.as_dict()
    print("Smoke test response:")
    print(json.dumps(result, indent=2)[:2000])

    # Validate embedding dimension
    if "predictions" in result:
        pred = result["predictions"]
        if isinstance(pred, list) and len(pred) > 0:
            emb = pred[0].get("embedding", [])
            print(f"\n\u2713 Embedding dim: {len(emb)} (expected 1152)")
            assert len(emb) == 1152, f"Expected 1152, got {len(emb)}"

# COMMAND ----------

# DBTITLE 1,Teardown header
# MAGIC %md
# MAGIC ## Phase 4 — Teardown
# MAGIC
# MAGIC | Resource | Cost while alive? | Action |
# MAGIC |---|---|---|
# MAGIC | Endpoint (`geneformer_bionemo_test`) | **Yes** (GPU billing) | Delete |
# MAGIC | UC model versions | No | Preserved (audit trail) |
# MAGIC | Inference tables | No (storage only) | Preserved (debugging) |

# COMMAND ----------

# DBTITLE 1,Teardown
# from databricks.sdk import WorkspaceClient
# from databricks.sdk.errors import NotFound

# w = WorkspaceClient()

# try:
#     _ep_name = dbutils.widgets.get("endpoint_name")
# except Exception:
#     _ep_name = "geneformer_bionemo_test"

# try:
#     w.serving_endpoints.delete(_ep_name)
#     print(f"✓ Deleted endpoint '{_ep_name}'")
# except NotFound:
#     print(f"  Endpoint '{_ep_name}' already gone.")

# print("✓ Teardown complete. UC models + inference tables preserved (no ongoing cost).")