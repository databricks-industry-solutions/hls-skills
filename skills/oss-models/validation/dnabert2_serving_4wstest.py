# Databricks notebook source
# MAGIC %md
# MAGIC # Serving validation — DNABERT-2 (genomics) → MLflow PyFunc → Unity Catalog → GPU Model Serving
# MAGIC
# MAGIC **What this is.** A hands-on validation notebook that walks the full path for ONE model:
# MAGIC acquire the weights from Hugging Face → wrap them in an MLflow PyFunc model → register to Unity Catalog →
# MAGIC deploy to a GPU Model Serving endpoint → score one request → tear the endpoint down. It doubles as the
# MAGIC eventual tested worked-example for the `oss-models` skill. DNABERT-2 opens the **DNA / genomics** modality that
# MAGIC is missing from both the skill and Genesis Workbench (roadmap §3 — ranked add #1, Apache-2.0, ungated).
# MAGIC
# MAGIC **The specific unknown this resolves.** Whether a DNA nucleotide sequence string flows cleanly through
# MAGIC DNABERT-2's tokenizer and model to a usable embedding **under a PyFunc on a GPU Serving endpoint** — and what the
# MAGIC exact tokenizer / extra build dependencies and output embedding shape actually are (both unknown until the run;
# MAGIC see the placeholders in Steps 1, 3, and 5). Unlike Geneformer, **there is no TransformerEngine requirement** here.
# MAGIC
# MAGIC **Prerequisites.**
# MAGIC - A GPU-backed runtime for authoring/smoke test (a modest GPU is expected to suffice — see Step 6).
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
# MAGIC **What.** Install `transformers` (plus any tokenizer/build deps the model card names), then declare the run
# MAGIC parameters (catalog / schema / model / endpoint) as notebook widgets so nothing workspace-specific is hardcoded.
# MAGIC
# MAGIC **Why.** DNABERT-2 is a Hugging Face transformer; `transformers` is the core dependency. **The exact extra
# MAGIC dependencies are unverified** — the model card must be checked on the run (DNABERT-2 is commonly reported to ship
# MAGIC custom modeling code, which typically implies `trust_remote_code=True` and may pull tokenizer/attention build
# MAGIC deps). Those are marked placeholder rather than guessed. No TransformerEngine is required.
# MAGIC
# MAGIC **GPU note.** A **modest GPU** is expected to be enough for DNABERT-2 inference (roadmap §3 lists it as a
# MAGIC Serving-shaped model). The exact GPU tier is a placeholder until the run measures memory/latency (see Step 6).

# COMMAND ----------

# MAGIC %pip install transformers
# MAGIC # CONFIRM ON RUN — the model card may require extra deps (e.g. a specific tokenizer package or attention/build
# MAGIC # dep). Add them here ONLY after reading the DNABERT-2 model card; do not guess. Pin exact versions once proven,
# MAGIC # so the same versions feed log_model(pip_requirements=[...]) in Step 4/5.

# COMMAND ----------

# Restart Python so the freshly-installed packages are importable.
dbutils.library.restartPython()

# COMMAND ----------

# Run parameters as widgets — NOTHING workspace/profile/account-specific is hardcoded.
dbutils.widgets.text("catalog",       "<catalog>",                 "Unity Catalog catalog")
dbutils.widgets.text("schema",        "<schema>",                  "Unity Catalog schema")
dbutils.widgets.text("model",         "dnabert2",                  "UC model name")
dbutils.widgets.text("endpoint_name", "dnabert2-serving-test",            "Serving endpoint name")
# RUN-GATE: the side-effecting cells (Steps 5-7) execute ONLY when run_go == "true". Defaults to "false" so the
# notebook is inert on import / Run-All — a human must flip it to run the costed steps.
dbutils.widgets.dropdown("run_go", "false", ["false", "true"], "Run gate (side effects)")

CATALOG       = dbutils.widgets.get("catalog")
SCHEMA        = dbutils.widgets.get("schema")
MODEL         = dbutils.widgets.get("model")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
FULL_NAME     = f"{CATALOG}.{SCHEMA}.{MODEL}"   # <catalog>.<schema>.<model>
RUN_GO        = dbutils.widgets.get("run_go") == "true"   # False → side-effecting Steps 5-7 skip with a message

# Hugging Face source. The roadmap names "DNABERT-2 (Apache-2.0, ungated)" but does NOT state the exact HF repo id,
# so it is a placeholder — confirm the exact id from the model card on the run; do not invent it.
HF_REPO_ID = "<dnabert2-hf-repo-id>"   # CONFIRM ON RUN — exact HF repo id from the DNABERT-2 model card

print(f"Target UC model: {FULL_NAME}")
print(f"Target endpoint: {ENDPOINT_NAME}")
print(f"HF source:       {HF_REPO_ID}")
print(f"RUN_GO:          {RUN_GO}  (side-effecting Steps 5-7 {'WILL' if RUN_GO else 'will NOT'} execute)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Load the model from Hugging Face
# MAGIC
# MAGIC **What.** Pull the DNABERT-2 weights and tokenizer with `transformers`.
# MAGIC
# MAGIC **Why.** DNABERT-2 is a standard HF-hosted transformer, so `AutoModel` / `AutoTokenizer` is the acquisition
# MAGIC path. Whether `trust_remote_code=True` is required depends on the model shipping custom modeling code — set below
# MAGIC as a placeholder to confirm from the model card, not asserted.

# COMMAND ----------

import torch
from transformers import AutoModel, AutoTokenizer

# CONFIRM ON RUN — trust_remote_code flag depends on whether the repo ships custom modeling code (auto_map). Confirm
# from the model card; do not assume. Shown True as the likely case for DNABERT-2's custom architecture.
tokenizer = AutoTokenizer.from_pretrained(HF_REPO_ID, trust_remote_code=True)   # CONFIRM ON RUN
model     = AutoModel.from_pretrained(HF_REPO_ID, trust_remote_code=True)       # CONFIRM ON RUN
model     = model.eval().to("cuda")

print(type(model))
# print(model.config)   # CONFIRM ON RUN — record hidden size / max sequence length for the Step 4 signature.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Smoke inference with a real, model-appropriate input example
# MAGIC
# MAGIC **What.** Tokenize ONE DNA nucleotide sequence string (A/C/G/T) and run a forward pass to capture the real
# MAGIC output shape.
# MAGIC
# MAGIC **Why.** DNABERT-2's input is a raw nucleotide sequence; the model produces a hidden-state / embedding tensor.
# MAGIC The DNA string below is a real, model-appropriate input, but the **tokenizer behavior and output embedding shape
# MAGIC can only be confirmed by the run** — both are placeholders here, never guessed.

# COMMAND ----------

import pandas as pd

# A real DNA nucleotide sequence string (A/C/G/T) — the actual input DNABERT-2 expects.
input_example = pd.DataFrame([{"sequence": "ACGTACGTACGTACGTACGTACGTACGTACGT"}])

# --- Tokenize → forward pass ---------------------------------------------------------------------------------
# tokens = tokenizer(input_example["sequence"].tolist(), return_tensors="pt")   # CONFIRM ON RUN — tokenizer args
# with torch.no_grad():
#     output = model(**{k: v.to("cuda") for k, v in tokens.items()})
# embedding = <pool(output)>   # CONFIRM ON RUN — pooling (e.g. mean over last_hidden_state) per the model card

OUTPUT_SHAPE = "<placeholder: (n_sequences, hidden_dim)>"   # CONFIRM ON RUN — capture real tensor shape here
print("Captured output shape:", OUTPUT_SHAPE)

# Real output example used for the signature in Step 4 — placeholder embedding vector until the run fills it in.
output_example = pd.DataFrame([{"embedding": ["<float>", "..."]}])   # CONFIRM ON RUN — real embedding dim

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Wrap in an MLflow PyFunc with an inferred signature
# MAGIC
# MAGIC **What.** Author a file-based PyFunc (`model.py`) that loads the tokenizer + model once and runs
# MAGIC tokenize → forward → pool, then infer an MLflow signature from the Step 3 input/output example.
# MAGIC
# MAGIC **Why.** The file-based "Models from Code" pattern (`python_model="model.py"` + `mlflow.models.set_model(...)`)
# MAGIC avoids pickling the class and the Python-version unpickle crashes that come with it
# MAGIC (databricks-ml-training `references/custom-pyfunc.md`). The signature pins the request/response contract.

# COMMAND ----------

# Write the PyFunc model file (logged verbatim — no class pickling).
# HF_REPO_ID is INJECTED from the notebook variable above so there is a SINGLE source of truth for the repo id
# (the placeholder propagates until CONFIRMED). NOTE: this is an f-string — keep the body brace-free.
model_py = f'''
import pandas as pd
import torch
import mlflow
from mlflow.pyfunc import PythonModel
from transformers import AutoModel, AutoTokenizer

HF_REPO_ID = "{HF_REPO_ID}"   # injected from the notebook (single source of truth); CONFIRM ON RUN — exact id

class DNABert2Embedder(PythonModel):
    def load_context(self, context):
        # Load tokenizer + weights ONCE at container start.
        self.tokenizer = AutoTokenizer.from_pretrained(HF_REPO_ID, trust_remote_code=True)  # CONFIRM ON RUN
        self.model = AutoModel.from_pretrained(HF_REPO_ID, trust_remote_code=True).eval().to("cuda")  # CONFIRM ON RUN

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        # CONFIRM ON RUN — mirror the exact tokenize → forward → pool path proven in Step 3.
        raise NotImplementedError("CONFIRM ON RUN — wire tokenize/forward/pool from the DNABERT-2 model card")

mlflow.models.set_model(DNABert2Embedder())
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

    with mlflow.start_run(run_name="dnabert2-serving-test"):
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model="model.py",              # file path, not an instance (Models from Code)
            signature=signature,
            input_example=input_example,
            pip_requirements=[                     # CONFIRM ON RUN — pin exact versions proven in Step 1
                "mlflow",
                "transformers",                    # CONFIRM ON RUN — exact version
                "torch",                           # CONFIRM ON RUN — exact torch/CUDA build
                # "<extra-dnabert2-dep>",          # CONFIRM ON RUN — any tokenizer/build dep the model card requires
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
# MAGIC **Why / GPU tier suitability.** DNABERT-2 has no TransformerEngine requirement, so a **modest GPU tier** is
# MAGIC expected to be sufficient — but the **exact tier is a placeholder** until the run measures memory/latency, and
# MAGIC the GPU `workload_type` enum is **not invented here**: discover valid values with
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
                "workload_type":        "<GPU_WORKLOAD_TYPE>",  # CONFIRM ON RUN — a modest GPU tier; discover via `serving-endpoints create -h`
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
# MAGIC **What.** Send exactly ONE request to validate the deployed model, then **delete the endpoint immediately.**
# MAGIC
# MAGIC **Why.** The point of the validation is one live inference end-to-end through Serving. A GPU endpoint keeps billing
# MAGIC while it exists, so teardown is not optional. **Both cells are documented, not executed.**

# COMMAND ----------

if not RUN_GO:
    print("run-gate off; set run_go=true to execute Step 7 scoring. Skipping.")
else:
    # Score one request. Custom PyFunc endpoints take dataframe_records (databricks-model-serving Query section).
    result = deploy.predict(
        endpoint=ENDPOINT_NAME,
        inputs={"dataframe_records": [{"sequence": "ACGTACGTACGTACGTACGTACGTACGTACGT"}]},
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
