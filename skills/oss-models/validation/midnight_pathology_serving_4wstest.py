# Databricks notebook source
# MAGIC %md
# MAGIC # Serving validation — kaiko-ai/midnight (pathology tile-embedding encoder) → MLflow PyFunc → Unity Catalog → GPU Model Serving
# MAGIC
# MAGIC **What this is.** A hands-on validation notebook that walks the full path for ONE model:
# MAGIC acquire the weights from Hugging Face → wrap them in an MLflow PyFunc model → register to Unity Catalog →
# MAGIC deploy to a GPU Model Serving endpoint → score one request → tear the endpoint down. It doubles as the
# MAGIC eventual tested worked-example for the `oss-models` skill.
# MAGIC
# MAGIC **This is the FIRST imaging-modality entry, and its I/O contract differs from the sequence/structure models.**
# MAGIC `kaiko-ai/midnight` (MIT, ungated — roadmap §5, cleanest pathology add) is a **pathology tile-embedding
# MAGIC encoder**: it maps a **histopathology image tile → a fixed-length embedding vector**. It is **NOT a
# MAGIC vision-language model (VLM)** — there is no text input and no text output. Because the input is an image, this
# MAGIC notebook adds an explicit **image-preprocessing sub-step** (Step 3a) that the sequence/structure validation notebooks do not
# MAGIC have. This is exactly the point (roadmap §1a) where the shared `oss-models` scaffolding first bends for imaging.
# MAGIC
# MAGIC **The specific unknown this resolves.** Whether a preprocessed histopathology tile flows cleanly through Midnight
# MAGIC to an embedding vector **under a PyFunc on a GPU Serving endpoint**, and what the exact expected patch size /
# MAGIC normalization and output embedding dimension actually are (all unknown until the run — see placeholders in
# MAGIC Steps 3a, 3, 5).
# MAGIC
# MAGIC **Prerequisites.**
# MAGIC - A GPU-backed runtime for authoring/smoke test.
# MAGIC - Unity Catalog write access to the target `<catalog>.<schema>`.
# MAGIC - Permission to create a GPU Model Serving endpoint in this workspace.
# MAGIC - A chosen Databricks CLI `--profile` for any CLI step (never auto-selected).
# MAGIC
# MAGIC ---
# MAGIC ### ⚠️ **COSTED-RUN WARNING — DO NOT RUN THIS NOTEBOOK CASUALLY** ⚠️
# MAGIC **This is a DRAFT. Every step below is documented, NOT executed here.** Running it spins up GPU compute and a
# MAGIC GPU Model Serving endpoint, both of which cost real money against a real budget.
# MAGIC - **Run only with an explicit human go-ahead AND a chosen `--profile`.**
# MAGIC - **A GPU Serving endpoint keeps billing while it exists.**
# MAGIC - **TEAR DOWN the endpoint in Step 7 the moment the single validation request succeeds.** Do not leave it running.
# MAGIC ---

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Environment, dependencies, and GPU requirements
# MAGIC
# MAGIC **What.** Install the deps needed to load the encoder and preprocess an image tile, then declare the run
# MAGIC parameters (catalog / schema / model / endpoint) as notebook widgets so nothing workspace-specific is hardcoded.
# MAGIC
# MAGIC **Why.** Midnight is an HF-hosted vision encoder; loading it needs `transformers`, and image preprocessing needs
# MAGIC an imaging stack (`Pillow` for tiles, `torchvision` for resize/normalize transforms are the usual choices).
# MAGIC **Whether Midnight additionally needs `timm` or a custom loader is unverified** — confirm from the model card on
# MAGIC the run; those extras are placeholders, not guesses.
# MAGIC
# MAGIC **GPU note.** A vision encoder of this class runs on a modest-to-mid GPU tier; the **exact tier is a placeholder**
# MAGIC until the run measures memory/latency (see Step 6). No TransformerEngine requirement.

# COMMAND ----------

# MAGIC %pip install transformers pillow torchvision
# MAGIC # CONFIRM ON RUN — the model card may require extra deps (e.g. timm, or a custom loader). Add them here ONLY
# MAGIC # after reading the kaiko-ai/midnight model card; do not guess. Pin exact versions once proven, so the same
# MAGIC # versions feed log_model(pip_requirements=[...]) in Step 4/5.

# COMMAND ----------

# Restart Python so the freshly-installed packages are importable.
dbutils.library.restartPython()

# COMMAND ----------

# Run parameters as widgets — NOTHING workspace/profile/account-specific is hardcoded.
dbutils.widgets.text("catalog",       "<catalog>",                     "Unity Catalog catalog")
dbutils.widgets.text("schema",        "<schema>",                      "Unity Catalog schema")
dbutils.widgets.text("model",         "midnight_pathology",            "UC model name")
dbutils.widgets.text("endpoint_name", "midnight-pathology-serving-test",      "Serving endpoint name")
# RUN-GATE: the side-effecting cells (Steps 5-7) execute ONLY when run_go == "true". Defaults to "false" so the
# notebook is inert on import / Run-All — a human must flip it to run the costed steps.
dbutils.widgets.dropdown("run_go", "false", ["false", "true"], "Run gate (side effects)")

CATALOG       = dbutils.widgets.get("catalog")
SCHEMA        = dbutils.widgets.get("schema")
MODEL         = dbutils.widgets.get("model")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
FULL_NAME     = f"{CATALOG}.{SCHEMA}.{MODEL}"   # <catalog>.<schema>.<model>
RUN_GO        = dbutils.widgets.get("run_go") == "true"   # False → side-effecting Steps 5-7 skip with a message

# Hugging Face source, grounded in roadmap §5. MIT, ungated — no HF gate to accept.
HF_REPO_ID = "kaiko-ai/midnight"

print(f"Target UC model: {FULL_NAME}")
print(f"Target endpoint: {ENDPOINT_NAME}")
print(f"HF source:       {HF_REPO_ID}")
print(f"RUN_GO:          {RUN_GO}  (side-effecting Steps 5-7 {'WILL' if RUN_GO else 'will NOT'} execute)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Load the model from Hugging Face
# MAGIC
# MAGIC **What.** Pull the Midnight encoder weights with `transformers`.
# MAGIC
# MAGIC **Why.** Midnight is an ungated MIT model, so acquisition is a plain `from_pretrained` with no HF token / gate
# MAGIC acceptance. Whether the correct loader is `AutoModel` vs a `timm`/custom loader, and whether
# MAGIC `trust_remote_code=True` is required, is unverified — confirm from the model card, do not assume.

# COMMAND ----------

import torch
from transformers import AutoModel   # CONFIRM ON RUN — confirm the correct loader (AutoModel vs timm/custom) from the model card

# CONFIRM ON RUN — trust_remote_code flag depends on whether the repo ships custom modeling code. Confirm from the card.
model = AutoModel.from_pretrained(HF_REPO_ID, trust_remote_code=True)   # CONFIRM ON RUN
model = model.eval().to("cuda")

print(type(model))
# print(model.config)   # CONFIRM ON RUN — record embedding dim + expected input resolution for Steps 3a/3/4.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3a — Image preprocessing sub-step (imaging-only — not in the sequence/structure validation notebooks)
# MAGIC
# MAGIC **What.** Take a histopathology image tile and resize + normalize it to the exact patch size / normalization
# MAGIC statistics the encoder expects, producing the input tensor for the forward pass.
# MAGIC
# MAGIC **Why.** Unlike a DNA string or a tokenized cell, an image tile must be shaped to the encoder's fixed input
# MAGIC resolution and normalized with the model's expected mean/std before it will produce a meaningful embedding.
# MAGIC **The exact patch size and normalization constants are unverified** — they come from the Midnight model card
# MAGIC (often ImageNet-style mean/std for ViT encoders, but do NOT assume) and are placeholders here.

# COMMAND ----------

# from PIL import Image                # uncomment together with the preprocess block below (used by Image.open)
# from torchvision import transforms   # CONFIRM ON RUN — confirm the preprocessing pipeline from the model card

PATCH_SIZE = "<patch-size-hw>"      # CONFIRM ON RUN — e.g. (224, 224); read from the Midnight model card
NORM_MEAN  = "<normalization-mean>" # CONFIRM ON RUN — per-channel mean; read from the model card
NORM_STD   = "<normalization-std>"  # CONFIRM ON RUN — per-channel std;  read from the model card

# preprocess = transforms.Compose([
#     transforms.Resize(PATCH_SIZE),          # CONFIRM ON RUN
#     transforms.ToTensor(),
#     transforms.Normalize(NORM_MEAN, NORM_STD),  # CONFIRM ON RUN
# ])
#
# tile = Image.open("<path-or-uri-to-a-histopathology-tile>").convert("RGB")  # CONFIRM ON RUN — a real tile
# pixel_values = preprocess(tile).unsqueeze(0).to("cuda")   # shape (1, 3, H, W)

print("Preprocessing constants (patch size / mean / std) are placeholders — CONFIRM ON RUN from the model card.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Smoke inference with a real, model-appropriate input example
# MAGIC
# MAGIC **What.** Run the preprocessed tile through the encoder and capture the real output embedding shape.
# MAGIC
# MAGIC **Why.** Midnight's output is a **single embedding vector per tile** (tile → vector), a different contract than
# MAGIC the sequence/structure models. The embedding **dimension is unknown until the run** and is a placeholder here.
# MAGIC The `input_example` for MLflow is a small image tile / tensor representation, not text.

# COMMAND ----------

import pandas as pd

# input_example for MLflow: a small image tile represented so the signature is explicit. The exact transport encoding
# (base64 tile bytes vs a governed image URI vs a raw pixel tensor) is a boundary decision to confirm on the run.
input_example = pd.DataFrame([{"tile": "<base64-encoded-histopathology-tile-or-uri>"}])  # CONFIRM ON RUN

# --- Forward pass -------------------------------------------------------------------------------------------
# with torch.no_grad():
#     output = model(pixel_values)          # from Step 3a; CONFIRM ON RUN — exact forward call
# embedding = <extract_embedding(output)>   # CONFIRM ON RUN — pooled CLS / feature vector per the model card

OUTPUT_SHAPE = "<placeholder: (n_tiles, embedding_dim)>"   # CONFIRM ON RUN — capture real embedding dim here
print("Captured output shape:", OUTPUT_SHAPE)

# Real output example used for the signature in Step 4 — placeholder embedding vector until the run fills it in.
output_example = pd.DataFrame([{"embedding": ["<float>", "..."]}])   # CONFIRM ON RUN — real embedding dim

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Wrap in an MLflow PyFunc with an inferred signature
# MAGIC
# MAGIC **What.** Author a file-based PyFunc (`model.py`) that loads the encoder once and runs
# MAGIC decode-tile → preprocess → forward → extract-embedding, then infer an MLflow signature from the Step 3
# MAGIC input/output example.
# MAGIC
# MAGIC **Why.** The file-based "Models from Code" pattern (`python_model="model.py"` + `mlflow.models.set_model(...)`)
# MAGIC avoids pickling the class and the Python-version unpickle crashes that come with it
# MAGIC (databricks-ml-training `references/custom-pyfunc.md`). The signature pins the image-in / embedding-out contract,
# MAGIC and the preprocessing from Step 3a must live INSIDE the PyFunc so the endpoint applies it identically.

# COMMAND ----------

# Write the PyFunc model file (logged verbatim — no class pickling).
# HF_REPO_ID is INJECTED from the notebook variable above so there is a SINGLE source of truth for the repo id.
# NOTE: this is an f-string — keep the body brace-free.
model_py = f'''
import pandas as pd
import torch
import mlflow
from mlflow.pyfunc import PythonModel
from transformers import AutoModel

HF_REPO_ID = "{HF_REPO_ID}"   # injected from the notebook (single source of truth); grounded in roadmap §5 (MIT, ungated)

class MidnightTileEncoder(PythonModel):
    def load_context(self, context):
        # Load weights ONCE at container start.
        self.model = AutoModel.from_pretrained(HF_REPO_ID, trust_remote_code=True).eval().to("cuda")  # CONFIRM ON RUN
        # self.preprocess = <torchvision transform from Step 3a>   # CONFIRM ON RUN — patch size + normalization

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        # CONFIRM ON RUN — mirror decode-tile → preprocess (Step 3a) → forward → extract-embedding (Step 3).
        raise NotImplementedError("CONFIRM ON RUN — wire decode/preprocess/forward/extract from the Midnight model card")

mlflow.models.set_model(MidnightTileEncoder())
'''
with open("model.py", "w") as f:
    f.write(model_py)

# COMMAND ----------

from mlflow.models import infer_signature

signature = infer_signature(input_example, output_example)   # from Step 3 examples
print(signature)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 5 — Log and register to Unity Catalog under `<catalog>.<schema>.<model>`
# MAGIC
# MAGIC **What.** Log the PyFunc to MLflow with the signature + input example, register it to UC, run the pre-deploy
# MAGIC `mlflow.models.predict(...)` env check, and promote a `@prod` alias.
# MAGIC
# MAGIC **Why.** `set_registry_uri("databricks-uc")` **before** logging is what sends the model to Unity Catalog rather
# MAGIC than the deprecated workspace registry (databricks-ml-training gotcha). Pinning `pip_requirements` to the exact
# MAGIC versions proven in Step 1 stops the endpoint crashing on an env rebuild.
# MAGIC
# MAGIC **This cell is documented, not executed** (it registers a UC object). Run only with explicit go.

# COMMAND ----------

import mlflow
from mlflow.tracking import MlflowClient

if not RUN_GO:
    print("run-gate off; set run_go=true to execute Step 5 (MLflow log_model + UC registration). Skipping.")
else:
    mlflow.set_registry_uri("databricks-uc")   # MUST precede log_model — else lands in workspace registry.
    mlflow.set_experiment(f"/Users/<you>/{MODEL}")   # CONFIRM ON RUN — parent folder must already exist.

    with mlflow.start_run(run_name="midnight-pathology-serving-test"):
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model="model.py",              # file path, not an instance (Models from Code)
            signature=signature,
            input_example=input_example,
            pip_requirements=[                     # CONFIRM ON RUN — pin exact versions proven in Step 1
                "mlflow",
                "transformers",                    # CONFIRM ON RUN — exact version
                "torch",                           # CONFIRM ON RUN — exact torch/CUDA build
                "pillow",                          # CONFIRM ON RUN — exact version
                "torchvision",                     # CONFIRM ON RUN — exact version
                # "<extra-midnight-dep>",          # CONFIRM ON RUN — e.g. timm, if the model card requires it
            ],
            registered_model_name=FULL_NAME,
        )

    # Pre-deploy validation — rebuilds the env and runs predict() locally BEFORE the endpoint does.
    mlflow.models.predict(model_uri=info.model_uri, input_data=input_example, env_manager="uv")  # CONFIRM ON RUN

    client = MlflowClient(registry_uri="databricks-uc")
    client.set_registered_model_alias(FULL_NAME, "prod", info.registered_model_version)
    print("Registered:", FULL_NAME, "version", info.registered_model_version)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 6 — Deploy to a GPU Model Serving endpoint
# MAGIC
# MAGIC **What.** Create a GPU serving endpoint for the registered model version.
# MAGIC
# MAGIC **Why / GPU tier suitability.** Midnight is a vision encoder with no TransformerEngine requirement, so a
# MAGIC **modest-to-mid GPU tier** is expected to be sufficient — but the **exact tier is a placeholder** until the run
# MAGIC measures memory/latency, and the GPU `workload_type` enum is **not invented here**: discover valid values with
# MAGIC `databricks serving-endpoints create -h` (databricks-model-serving). **This cell is documented, not executed.**

# COMMAND ----------

from mlflow.deployments import get_deploy_client
import time

def wait_until_ready(deploy_client, name, timeout_s=1800, interval_s=30):
    # Readiness per databricks-model-serving: fully ready when state.ready == "READY" AND
    # state.config_update == "NOT_UPDATING" (both field names + string values are grounded in that skill).
    # Querying before then returns 404/503. CONFIRM ON RUN — the MLflow deployments client accessor (get_endpoint)
    # and its response shape; the skill documents the poll via the CLI:
    #   databricks serving-endpoints get <name> --profile <profile>
    #     | jq '{ready: .state.ready, config_update: .state.config_update}'
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ep = deploy_client.get_endpoint(endpoint=name)   # CONFIRM ON RUN — accessor + response shape
        state = (ep.get("state") or {}) if isinstance(ep, dict) else {}
        ready, cfg = state.get("ready"), state.get("config_update")
        print(f"  endpoint state: ready={ready} config_update={cfg}")
        if ready == "READY" and cfg == "NOT_UPDATING":
            return True
        time.sleep(interval_s)
    raise TimeoutError(f"Endpoint {name} not READY within {timeout_s}s")

deploy = get_deploy_client("databricks")

if not RUN_GO:
    print("run-gate off; set run_go=true to execute Step 6 (create GPU serving endpoint). Skipping.")
else:
    version = info.registered_model_version   # from Step 5

    deploy.create_endpoint(
        name=ENDPOINT_NAME,
        config={
            "served_entities": [{
                "entity_name":          FULL_NAME,
                "entity_version":       version,
                "workload_size":        "Small",
                "workload_type":        "<GPU_WORKLOAD_TYPE>",  # CONFIRM ON RUN — a modest/mid GPU tier; discover via `serving-endpoints create -h`
                # CONFIRM ON RUN — databricks-model-serving is silent on GPU scale-to-zero support; verify before
                # relying on this to avoid idle GPU billing.
                "scale_to_zero_enabled": True,
            }],
            "traffic_config": {"routes": [
                {"served_model_name": f"{MODEL}-{version}", "traffic_percentage": 100}
            ]},
        },
    )
    # Poll BOTH state.ready == READY AND state.config_update == NOT_UPDATING before querying (databricks-model-serving).
    wait_until_ready(deploy, ENDPOINT_NAME)
    print(f"Endpoint {ENDPOINT_NAME} is READY.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 7 — Score one request, then TEAR DOWN the endpoint
# MAGIC
# MAGIC **What.** Send exactly ONE tile request to validate the deployed encoder, then **delete the endpoint immediately.**
# MAGIC
# MAGIC **Why.** The point of the validation is one live tile→embedding inference end-to-end through Serving. A GPU endpoint
# MAGIC keeps billing while it exists, so teardown is not optional. **Both cells are documented, not executed.**

# COMMAND ----------

if not RUN_GO:
    print("run-gate off; set run_go=true to execute Step 7 scoring. Skipping.")
else:
    # Score one request. Custom PyFunc endpoints take dataframe_records (databricks-model-serving Query section).
    result = deploy.predict(
        endpoint=ENDPOINT_NAME,
        inputs={"dataframe_records": [{"tile": "<base64-encoded-histopathology-tile-or-uri>"}]},  # CONFIRM ON RUN
    )
    print(result)   # CONFIRM ON RUN — capture the real embedding shape returned by the endpoint

# COMMAND ----------

# TEAR DOWN — delete the GPU endpoint the moment the request above succeeds. Do not leave it running.
if not RUN_GO:
    print("run-gate off; nothing was deployed, so nothing to tear down.")
else:
    deploy.delete_endpoint(endpoint=ENDPOINT_NAME)
    # CLI equivalent: databricks serving-endpoints delete <endpoint_name> --profile <profile>
    print(f"Deleted endpoint: {ENDPOINT_NAME}")
