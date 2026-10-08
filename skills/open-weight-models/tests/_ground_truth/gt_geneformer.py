# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# DBTITLE 1,Geneformer Ground Truth
# MAGIC %md
# MAGIC # Geneformer Ground Truth — Path A (HF/jkobject)
# MAGIC
# MAGIC End-to-end: download → register → deploy → smoke test → teardown for
# MAGIC [Geneformer](https://huggingface.co/ctheodoris/Geneformer) `Geneformer-V1-10M`
# MAGIC (standard PyTorch, hidden_size=256). **Path B (BioNeMo NVIDIA engine) is in a separate notebook.**
# MAGIC
# MAGIC | Resource | URL |
# MAGIC |----------|-----|
# MAGIC | **Model weights** | [ctheodoris/Geneformer](https://huggingface.co/ctheodoris/Geneformer) |
# MAGIC | **Code (jkobject fork)** | [github.com/jkobject/geneformer](https://github.com/jkobject/geneformer) |
# MAGIC | **Paper** | [doi.org/10.1038/s41586-023-06139-9](https://doi.org/10.1038/s41586-023-06139-9) |
# MAGIC | **License** | Check Geneformer repo |
# MAGIC
# MAGIC | Phase | Cells | Installs | Restart? |
# MAGIC |-------|-------|----------|----------|
# MAGIC | **Setup** | 1-3 | — | — |
# MAGIC | **Download** | 4-8 | `huggingface_hub` | restart 1 |
# MAGIC | **Register** | 9-14 | `torch transformers mlflow` | restart 2 |
# MAGIC | **Deploy + Score** | 15-16 | — | — |
# MAGIC | **Teardown** | 17-18 | — | — |

# COMMAND ----------

# DBTITLE 1,Compute detection
import os, subprocess

# --- Volume check: skip download if snapshot already present ---
_VOL_SENTINEL = "/Volumes/<catalog>/skills/models/geneformer/.copy_complete"
if os.path.exists(_VOL_SENTINEL):
    print("✓ Geneformer snapshot already in Volume — download phase will be skipped.")
else:
    print("Geneformer snapshot NOT in Volume — download phase will run.")

# --- Compute detection (works on Serverless and Classic) ---
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
# Widgets survive restartPython()
# Remove stale widgets, then re-create with correct defaults
for _w in ["catalog", "schema", "volume_name", "model_name", "endpoint_name", "run_go"]:
    try:
        dbutils.widgets.remove(_w)
    except Exception:
        pass

dbutils.widgets.text("catalog", "<catalog>", "Unity Catalog catalog")
dbutils.widgets.text("schema", "skills", "Unity Catalog schema")
dbutils.widgets.text("volume_name", "models", "UC volume name")
dbutils.widgets.text("model_name", "Geneformer-V1-10M", "Model checkpoint name")
dbutils.widgets.text("endpoint_name", "geneformer_test", "Serving endpoint name")
dbutils.widgets.dropdown("run_go", "false", ["false", "true"], "Run gate (deploy costs real money)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_NAME = dbutils.widgets.get("volume_name")
MODEL_NAME = dbutils.widgets.get("model_name")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
RUN_GO = dbutils.widgets.get("run_go") == "true"

VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}"
SNAPSHOT_DIR = f"{VOLUME_PATH}/geneformer"
CHECKPOINT_DIR = f"{SNAPSHOT_DIR}/{MODEL_NAME}"
REGISTERED_MODEL_NAME = f"{CATALOG}.{SCHEMA}.geneformer"
HF_REPO = "ctheodoris/Geneformer"

print(f"Catalog    : {CATALOG}.{SCHEMA}")
print(f"Volume     : {VOLUME_PATH}")
print(f"Checkpoint : {MODEL_NAME}")
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
MODEL_NAME = dbutils.widgets.get("model_name")
HF_REPO = "ctheodoris/Geneformer"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}"
LOCAL_DIR = os.path.join(TMP_DIR, "geneformer_snapshot")
os.makedirs(LOCAL_DIR, exist_ok=True)

# --- Create schema + volume if needed ---
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME_NAME}")

print(f"Compute  : {'Serverless' if IS_SERVERLESS else 'Classic'}")
print(f"Storage  : {TMP_DIR}")
print(f"Schema   : {CATALOG}.{SCHEMA} ✓")
print(f"Volume   : {VOLUME_PATH} ✓")
print(f"Download : {LOCAL_DIR}")
print(f"Model    : {MODEL_NAME}")

# COMMAND ----------

# DBTITLE 1,Download Geneformer snapshot
from huggingface_hub import snapshot_download

vol_dest = f"{VOLUME_PATH}/geneformer"
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

# DBTITLE 1,Verify snapshot + discover token dictionary
# --- Verify snapshot structure ---
print("Snapshot contents:")
for item in sorted(os.listdir(LOCAL_DIR)):
    kind = "[dir] " if os.path.isdir(os.path.join(LOCAL_DIR, item)) else "[file]"
    print(f"  {kind} {item}")

# Verify checkpoint dir
checkpoint_dir = os.path.join(LOCAL_DIR, MODEL_NAME)
assert os.path.isdir(checkpoint_dir), (
    f"Checkpoint dir not found: {checkpoint_dir}. "
    f"Available: {[d for d in os.listdir(LOCAL_DIR) if os.path.isdir(os.path.join(LOCAL_DIR, d))]}"
)
print(f"\n✓ Checkpoint: {checkpoint_dir}")
for f in sorted(os.listdir(checkpoint_dir)):
    print(f"  {f}")

# --- Discover token dictionary (pickle format, inside geneformer/ package) ---
import pickle
dict_path = None
# V1 models use gene_dictionaries_30m/, V2 use top-level gc104M
for candidate in [
    os.path.join(LOCAL_DIR, "geneformer", "gene_dictionaries_30m", "token_dictionary_gc30M.pkl"),
    os.path.join(LOCAL_DIR, "geneformer", "token_dictionary_gc104M.pkl"),
]:
    if os.path.exists(candidate):
        dict_path = candidate
        break
else:
    # Walk tree for any token_dictionary*.pkl
    for root, dirs, files in os.walk(LOCAL_DIR):
        for f in files:
            if "token_dictionary" in f.lower() and f.endswith(".pkl"):
                dict_path = os.path.join(root, f)
                break
        if dict_path:
            break

if dict_path:
    with open(dict_path, "rb") as f:
        _td = pickle.load(f)
    ensembl_count = sum(1 for k in _td if str(k).startswith("ENSG"))
    print(f"\n✓ Token dictionary: {dict_path}")
    print(f"  Vocab size: {len(_td)}, Ensembl IDs: {ensembl_count}")
else:
    print("\n✗ No token dictionary found — manual inspection needed")

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
  name: geneformer
  checkpoint: {MODEL_NAME}
  source_url: https://huggingface.co/ctheodoris/Geneformer
  code_url: https://github.com/jkobject/geneformer
  license: check-repo
  reviewed_at: {datetime.date.today().isoformat()}
weights:
  location: {vol_dest}/{MODEL_NAME}
runtime:
  download_compute: {'serverless_cpu' if IS_SERVERLESS else 'classic_cpu'}
  register_compute: gpu_required
"""
with open(f"{vol_dest}/provenance_manifest.yaml", "w") as f:
    f.write(manifest)
print("✓ Provenance manifest written")

# COMMAND ----------

# DBTITLE 1,Idempotent cleanup
# Per .assistant_instructions.md: cleanup early, before registration.
# Deletes existing endpoint + all UC model versions for a clean run.
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, ResourceDoesNotExist

w = WorkspaceClient()

# Re-read widgets (may run before or after restart)
try:
    _ep = dbutils.widgets.get("endpoint_name")
    _model = f"{dbutils.widgets.get('catalog')}.{dbutils.widgets.get('schema')}.geneformer"
except Exception:
    _ep = "geneformer_test"
    _model = "<catalog>.skills.geneformer"

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
# MAGIC %pip install -q "torch>=2.0.0" "transformers>=4.30.0" "mlflow[databricks]"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Post-restart setup (Phase 1b)
import os, json

# --- Re-read widgets after restart ---
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_NAME = dbutils.widgets.get("volume_name")
MODEL_NAME = dbutils.widgets.get("model_name")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
RUN_GO = dbutils.widgets.get("run_go") == "true"

VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}"
SNAPSHOT_DIR = f"{VOLUME_PATH}/geneformer"
CHECKPOINT_DIR = f"{SNAPSHOT_DIR}/{MODEL_NAME}"
REGISTERED_MODEL_NAME = f"{CATALOG}.{SCHEMA}.geneformer"

assert os.path.isdir(CHECKPOINT_DIR), f"Checkpoint not found: {CHECKPOINT_DIR}"

# --- Discover token dictionary (pickle, inside geneformer/ package) ---
import pickle
dict_path = None
for candidate in [
    os.path.join(SNAPSHOT_DIR, "geneformer", "gene_dictionaries_30m", "token_dictionary_gc30M.pkl"),
    os.path.join(SNAPSHOT_DIR, "geneformer", "token_dictionary_gc104M.pkl"),
]:
    if os.path.exists(candidate):
        dict_path = candidate
        break
else:
    for root, dirs, files in os.walk(SNAPSHOT_DIR):
        for f in files:
            if "token_dictionary" in f.lower() and f.endswith(".pkl"):
                dict_path = os.path.join(root, f)
                break
        if dict_path:
            break

assert dict_path, "Token dictionary not found in snapshot"

# --- Inspect config.json ---
config_path = os.path.join(CHECKPOINT_DIR, "config.json")
if os.path.exists(config_path):
    with open(config_path) as f:
        config = json.load(f)
    hidden_size = config.get("hidden_size", "?")
    print(f"hidden_size={hidden_size}, layers={config.get('num_hidden_layers', '?')}")

print(f"✓ Checkpoint : {CHECKPOINT_DIR}")
print(f"✓ Token dict : {dict_path}")
print(f"  RUN_GO    : {RUN_GO}")

# COMMAND ----------

# DBTITLE 1,GeneformerEmbedder wrapper file
import os

# --- Write wrapper to file (file-based logging, no cloudpickle) ---
# Following gt_teddy pattern: python_model=path avoids cloudpickle
# version mismatches between notebook and serving container.

WRAPPER_PATH = "/tmp/geneformer_wrapper.py"

wrapper_code = '''
import mlflow
import pickle


class GeneformerEmbedder(mlflow.pyfunc.PythonModel):
    """Wraps Geneformer to produce per-cell embeddings.

    Inputs (DataFrame, one row per request):
      - cell_id: str
      - genes: list[str] -- Ensembl gene IDs (must be in token dictionary)
      - expression: list[float] -- raw counts aligned to genes
      - vocab_version: str
      - config: JSON string -- {truncation, gene_count_limit, pooling_mode}

    Output: list[dict] -- {cell_id, embedding, embedding_dim, vocab_version}
    """

    def load_context(self, context):
        import os, sys, pickle
        import torch
        from transformers import AutoModel

        # Fix for Model Serving: container replaces sys.stdout with
        # StreamToLogger which lacks isatty(). Transformers' loading
        # report calls sys.stdout.isatty() and crashes without this.
        for stream in (sys.stdout, sys.stderr):
            if stream is not None and not hasattr(stream, "isatty"):
                stream.isatty = lambda: False

        checkpoint_dir = context.artifacts["checkpoint_dir"]
        dict_path = context.artifacts["token_dict"]

        self.model = AutoModel.from_pretrained(checkpoint_dir)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device).eval()

        with open(dict_path, "rb") as f:
            self.token_dict = pickle.load(f)

        self.max_tokens = getattr(self.model.config, "max_position_embeddings", 2048)
        self.hidden_size = getattr(self.model.config, "hidden_size", 256)
        print(f"Geneformer loaded on {self.device}, hidden_size={self.hidden_size}, "
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

            tokens = []
            for gene, expr in zip(genes, expression):
                if gene in self.token_dict:
                    tokens.append((self.token_dict[gene], expr))

            if not tokens:
                results.append({
                    "cell_id": cell_id, "embedding": [],
                    "embedding_dim": 0, "vocab_version": vocab_version,
                    "error": "No genes found in token dictionary",
                })
                continue

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
'''

with open(WRAPPER_PATH, "w") as f:
    f.write(wrapper_code)

# Import from file for dry-load test
import importlib.util
spec = importlib.util.spec_from_file_location("geneformer_wrapper", WRAPPER_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
GeneformerEmbedder = mod.GeneformerEmbedder

print(f"\u2713 Wrapper written to {WRAPPER_PATH}")
print(f"\u2713 GeneformerEmbedder imported from file")

# COMMAND ----------

# DBTITLE 1,Input example + dry-load test
import json, pickle, pandas as pd
from mlflow.pyfunc import PythonModelContext

# --- Build input_example from real token dictionary (pickle format) ---
with open(dict_path, "rb") as f:
    token_dict = pickle.load(f)
ensembl_genes = [g for g in token_dict.keys() if g.startswith("ENSG")][:10]
assert ensembl_genes, "No Ensembl gene IDs found in token dictionary"

input_example = pd.DataFrame([{
    "cell_id": "cell-0001",
    "genes": ensembl_genes,
    "expression": [float(i) for i in range(len(ensembl_genes), 0, -1)],
    "vocab_version": "v1",
    "config": json.dumps({
        "truncation": True, "gene_count_limit": "2048",
        "pooling_mode": "mean", "output": "embedding",
    }),
}])
print(f"\u2713 Input example: {len(ensembl_genes)} real Ensembl IDs")

# --- Dry-load test (pre-deploy gate per .assistant_instructions.md) ---
artifacts = {"checkpoint_dir": CHECKPOINT_DIR, "token_dict": dict_path}
ctx = PythonModelContext(artifacts=artifacts, model_config={})

embedder = GeneformerEmbedder()
embedder.load_context(ctx)
output_example = embedder.predict(ctx, input_example)

dim = output_example[0].get("embedding_dim", 0)
assert dim > 0, f"Dry-load produced dim={dim}"
print(f"\u2713 Dry-load OK: dim={dim}, first 5={output_example[0]['embedding'][:5]}")

# COMMAND ----------

# DBTITLE 1,Log + register to UC
import mlflow
import pandas as pd
from mlflow.models import infer_signature

mlflow.set_registry_uri("databricks-uc")
mlflow.set_tracking_uri("databricks")

# Build output for signature
output_df = pd.DataFrame(output_example if isinstance(output_example, list) else [output_example])

try:
    signature = infer_signature(input_example, output_df)
    print("Signature inferred:", signature)
except Exception as e:
    print(f"Could not infer signature (likely placeholder data): {e}")
    # Build manual signature as fallback
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

# Patch wrapper for MLflow 3.x code-based logging (requires set_model())
with open(WRAPPER_PATH, "r") as f:
    _code = f.read()
if "set_model" not in _code:
    _code += "\n\nmlflow.models.set_model(GeneformerEmbedder())\n"
    with open(WRAPPER_PATH, "w") as f:
        f.write(_code)
    print("\u2713 Patched wrapper with set_model() for MLflow 3.x")

if not RUN_GO:
    print("run-gate off; set run_go=true to execute log_model + UC registration. Skipping.")
else:
    with mlflow.start_run(run_name="geneformer_register") as run:
        mlflow.set_tag("model_family", "Geneformer")
        mlflow.set_tag("checkpoint", MODEL_NAME)
        mlflow.set_tag("source", "https://huggingface.co/ctheodoris/Geneformer")
        mlflow.set_tag("code", "https://github.com/jkobject/geneformer")

        model_info = mlflow.pyfunc.log_model(
            artifact_path="model",  # name= changes python_model semantics in 3.x
            python_model=WRAPPER_PATH,       # file-based, no cloudpickle
            artifacts=artifacts,
            signature=signature,
            input_example=input_example,
            pip_requirements=[
                "torch", "transformers", "numpy",
            ],
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

    entity = ServedEntityInput(
        entity_name=REGISTERED_MODEL_NAME,
        entity_version=str(model_version),
        workload_type=ServingModelWorkloadType.GPU_SMALL,
        workload_size="Small",
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
        print(f"\u2713 Endpoint '{ENDPOINT_NAME}' created (GPU_SMALL, AI Gateway inference table + usage tracking)")
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
    import time
    from databricks.sdk.service.serving import EndpointStateConfigUpdate, EndpointStateReady

    def wait_for_endpoint_ready(name, timeout_s=1200, poll_s=20):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            state = w.serving_endpoints.get(name).state
            if (state.ready == EndpointStateReady.READY
                    and state.config_update == EndpointStateConfigUpdate.NOT_UPDATING):
                print(f"\nEndpoint '{name}' is READY!")
                return
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
            "vocab_version": "v1",
            "config": json.dumps({
                "truncation": True,
                "gene_count_limit": "2048",
                "pooling_mode": "mean",
                "output": "embedding",
            }),
        }],
    )
    print("Smoke test response:")
    print(json.dumps(response.as_dict(), indent=2)[:2000])

# COMMAND ----------

# DBTITLE 1,Teardown header
# MAGIC %md
# MAGIC ## Phase 4 — Teardown
# MAGIC
# MAGIC | Resource | Cost while alive? | Action |
# MAGIC |---|---|---|
# MAGIC | Endpoint (`geneformer_test`) | **Yes** (GPU billing) | Delete |
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
#     _ep_name = "geneformer_test"

# try:
#     w.serving_endpoints.delete(_ep_name)
#     print(f"✓ Deleted endpoint '{_ep_name}'")
# except NotFound:
#     print(f"  Endpoint '{_ep_name}' already gone.")

# print("✓ Teardown complete. UC models + inference tables preserved (no ongoing cost).")