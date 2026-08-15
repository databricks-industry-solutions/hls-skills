# Databricks notebook source
# MAGIC %md
# MAGIC # Spike — Geneformer (NVIDIA BioNeMo TransformerEngine checkpoint) → MLflow PyFunc → Unity Catalog → GPU Model Serving
# MAGIC
# MAGIC **What this is.** A hands-on spike (a throwaway proof) that walks the full path for ONE model:
# MAGIC acquire the weights from Hugging Face → wrap them in an MLflow PyFunc model → register to Unity Catalog →
# MAGIC deploy to a GPU Model Serving endpoint → score one request → tear the endpoint down. It doubles as the
# MAGIC eventual tested worked-example for the `oss-models` skill.
# MAGIC
# MAGIC **The specific unknown this resolves.** Whether NVIDIA's TransformerEngine (TE) PyTorch extension — a CUDA
# MAGIC source build, like `flash-attn` — actually **builds and runs inside the Databricks Model Serving container**,
# MAGIC and whether the resulting model serves under a PyFunc. Roadmap §8 grades this **"PLAUSIBLE — needs a
# MAGIC hands-on spike"**: no hard block found (it is not FP8-only, and Docker is recommended-not-required for
# MAGIC inference), but the TE-in-Serving link is unproven. If TE will not build in Serving, the documented fallback
# MAGIC is a **GPU Jobs batch-inference** path instead of Serving.
# MAGIC
# MAGIC **Prerequisites.**
# MAGIC - A GPU-backed runtime for authoring/smoke test — a serverless-GPU notebook or a GPU cluster (see Step 1 for
# MAGIC   the GPU-tier requirements; **T4 is likely insufficient**).
# MAGIC - Unity Catalog write access to the target `<catalog>.<schema>`.
# MAGIC - Permission to create a **GPU** Model Serving endpoint in this workspace.
# MAGIC - A chosen Databricks CLI `--profile` for any CLI step (never auto-selected).
# MAGIC
# MAGIC ---
# MAGIC ### ⚠️ **COSTED-RUN WARNING — DO NOT RUN THIS NOTEBOOK CASUALLY** ⚠️
# MAGIC **This is a DRAFT. Every step below is documented, NOT executed here.** Running it spins up GPU compute and a
# MAGIC GPU Model Serving endpoint, both of which cost real money against a real budget.
# MAGIC - **Run only with an explicit human go-ahead AND a chosen `--profile`.**
# MAGIC - **Assume an idle GPU endpoint keeps billing — do NOT rely on scale-to-zero to save cost here.** (CONFIRM ON RUN:
# MAGIC   the `databricks-model-serving` skill is silent on whether GPU Serving endpoints honor `scale_to_zero_enabled`;
# MAGIC   verify before trusting it. Either way, tear the endpoint down in Step 7.)
# MAGIC - **TEAR DOWN the endpoint in Step 7 the moment the single validation request succeeds.** Do not leave it running.
# MAGIC ---

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Environment, dependencies, and GPU requirements
# MAGIC
# MAGIC **What.** Install the TransformerEngine PyTorch extension and `transformers`, then declare the run parameters
# MAGIC (catalog / schema / model / endpoint) as notebook widgets so nothing workspace-specific is hardcoded.
# MAGIC
# MAGIC **Why.** Geneformer's BioNeMo checkpoint ships as a TE-format model. TE is a **real pip dependency** whose
# MAGIC PyTorch extension is a **source build** (needs a compiler / NVCC) — NVIDIA's "without additional dependencies"
# MAGIC phrasing is overstated (roadmap §8). The pip line and GPU constraints below are quoted from roadmap §8; getting
# MAGIC the GPU tier wrong is the most likely cause of a failed run.
# MAGIC
# MAGIC **GPU requirements (roadmap §8):**
# MAGIC - **NVIDIA GPU required — there is no CPU path.**
# MAGIC - **FP8** needs compute capability **≥ 8.9 (Ada / Hopper)** — **NOT** A100.
# MAGIC - **BF16 / FP16** runs on **Ampere+** (A100 is fine for non-FP8).
# MAGIC - **T4 (Turing, < Ampere) is likely insufficient.**
# MAGIC - **CUDA 12.1+.**
# MAGIC - TE's PyTorch extension is a **source build** (compiler / NVCC present in the runtime).

# COMMAND ----------

# MAGIC %pip install --no-build-isolation 'transformer_engine[pytorch]' transformers
# MAGIC # CONFIRM ON RUN — roadmap §8 verbatim pip line. Pin exact versions once the run proves a working combination,
# MAGIC # so the same versions can be fed to log_model(pip_requirements=[...]) in Step 4.

# COMMAND ----------

# Restart Python so the freshly-installed packages are importable.
dbutils.library.restartPython()

# COMMAND ----------

# Run parameters as widgets — NOTHING workspace/profile/account-specific is hardcoded.
dbutils.widgets.text("catalog",       "<catalog>",                          "Unity Catalog catalog")
dbutils.widgets.text("schema",        "<schema>",                           "Unity Catalog schema")
dbutils.widgets.text("model",         "geneformer_bionemo",                 "UC model name")
dbutils.widgets.text("endpoint_name", "geneformer-bionemo-spike",           "Serving endpoint name")
# RUN-GATE: the side-effecting cells (Steps 5-7) execute ONLY when run_go == "true". Defaults to "false" so the
# notebook is inert on import / Run-All — a human must flip it to run the costed steps.
dbutils.widgets.dropdown("run_go", "false", ["false", "true"], "Run gate (side effects)")

CATALOG       = dbutils.widgets.get("catalog")
SCHEMA        = dbutils.widgets.get("schema")
MODEL         = dbutils.widgets.get("model")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
FULL_NAME     = f"{CATALOG}.{SCHEMA}.{MODEL}"   # <catalog>.<schema>.<model>
RUN_GO        = dbutils.widgets.get("run_go") == "true"   # False → side-effecting Steps 5-7 skip with a message

# Hugging Face source, grounded in roadmap §8. Apache-2.0, commercial-OK.
HF_REPO_ID = "nvidia/geneformer_V2_316M"

print(f"Target UC model: {FULL_NAME}")
print(f"Target endpoint: {ENDPOINT_NAME}")
print(f"HF source:       {HF_REPO_ID}")
print(f"RUN_GO:          {RUN_GO}  (side-effecting Steps 5-7 {'WILL' if RUN_GO else 'will NOT'} execute)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Load the model from Hugging Face
# MAGIC
# MAGIC **What.** Pull the BioNeMo Geneformer TE checkpoint with `AutoModel.from_pretrained`.
# MAGIC
# MAGIC **Why.** Roadmap §8 confirmed the user hypothesis that **no Docker is needed for inference** — the
# MAGIC `nvidia/geneformer_V2_316M` checkpoint loads directly via `AutoModel.from_pretrained` (per the bionemo-recipes
# MAGIC model README). `trust_remote_code=True` is **required** because the checkpoint ships custom modules referenced
# MAGIC through the config's `auto_map` (the model classes live in the repo, not in `transformers`).

# COMMAND ----------

import torch
from transformers import AutoModel  # AutoTokenizer path is model-specific — see the input note in Step 3.

# trust_remote_code=True: the config's auto_map points at custom modeling code shipped in the HF repo.
model = AutoModel.from_pretrained(HF_REPO_ID, trust_remote_code=True)
model = model.eval().to("cuda")   # NVIDIA GPU required — no CPU path (roadmap §8).

# CONFIRM ON RUN — capture the resolved model class, config, and dtype so the served version is pinned.
print(type(model))
# print(model.config)   # CONFIRM ON RUN — record hidden size / max input tokens for the signature in Step 4.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Smoke inference with a real, model-appropriate input example
# MAGIC
# MAGIC **What.** Build ONE bounded single-cell request and run it through the model to capture the real output shape.
# MAGIC
# MAGIC **Why.** Geneformer consumes **tokenized, rank-ordered single-cell gene expression**, not an arbitrary
# MAGIC expression matrix (per the `oss-models` skill's `geneformer.md` input/output contract). The request fields below
# MAGIC are grounded in `geneformer.md`; **the concrete values in each `<...>` slot can only come from the pinned
# MAGIC Geneformer release** (vocabulary version, gene-count / token limit, pooling enum) and MUST NOT be guessed. The
# MAGIC output shape is likewise a **placeholder until the run produces it**.

# COMMAND ----------

import json
import pandas as pd

# Bounded single-cell request. Field names are grounded in geneformer.md; every <...> is a placeholder that MUST be
# resolved from the pinned Geneformer release — do NOT invent Ensembl gene IDs, the token limit, or the pooling enum.
input_example = pd.DataFrame([{
    "cell_id":      "cell-0001",
    "genes":        ["<ensembl-gene-id-1>", "<ensembl-gene-id-2>", "<ensembl-gene-id-3>"],  # CONFIRM ON RUN
    "expression":   [12.0, 5.0, 3.0],
    "vocab_version": "<vocab-version>",                                                      # CONFIRM ON RUN
    "config": json.dumps({
        "truncation":       True,
        "gene_count_limit": "<max-input-tokens>",   # CONFIRM ON RUN — from the pinned release
        "pooling_mode":     "<pooling-mode>",        # CONFIRM ON RUN — pooling enum from the pinned release
        "output":           "embedding",
    }),
}])

# --- Preprocess → tokenize → forward pass ------------------------------------------------------------------
# CONFIRM ON RUN — the exact tokenization/ranking preprocessing (gene → token id via the pinned vocab, rank ordering,
# truncation) comes from the Geneformer release; wire the documented tokenizer here. Placeholder below.
#
# tokenized = <geneformer_tokenizer>(input_example)   # CONFIRM ON RUN
# with torch.no_grad():
#     output = model(**{k: v.to("cuda") for k, v in tokenized.items()})
# embedding = <pool(output)>                           # CONFIRM ON RUN — apply pooling_mode

OUTPUT_SHAPE = "<placeholder: (n_cells, hidden_dim)>"   # CONFIRM ON RUN — capture real tensor shape here
print("Captured output shape:", OUTPUT_SHAPE)

# Real output example used for the signature in Step 4 — placeholder embedding vector until the run fills it in.
output_example = pd.DataFrame([{"cell_id": "cell-0001", "embedding": ["<float>", "..."]}])  # CONFIRM ON RUN

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Wrap in an MLflow PyFunc with an inferred signature
# MAGIC
# MAGIC **What.** Author a file-based PyFunc (`model.py`) that loads the model once and runs the tokenize → forward →
# MAGIC pool path, then infer an MLflow signature from the Step 3 input/output example.
# MAGIC
# MAGIC **Why.** The file-based "Models from Code" pattern (`python_model="model.py"` + `mlflow.models.set_model(...)`)
# MAGIC avoids pickling the class, which is what prevents Python-version unpickle crashes between the training and
# MAGIC serving runtimes (databricks-ml-training `references/custom-pyfunc.md`). The signature makes the request/response
# MAGIC contract explicit at the endpoint boundary.

# COMMAND ----------

# Write the PyFunc model file (logged verbatim — no class pickling).
# HF_REPO_ID is INJECTED from the notebook variable above so there is a SINGLE source of truth for the repo id.
# NOTE: this is an f-string — keep the body brace-free (double any literal { } if you add code that needs them).
model_py = f'''
import json
import pandas as pd
import torch
import mlflow
from mlflow.pyfunc import PythonModel
from transformers import AutoModel

HF_REPO_ID = "{HF_REPO_ID}"   # injected from the notebook (single source of truth); grounded in roadmap §8

class GeneformerEmbedder(PythonModel):
    def load_context(self, context):
        # Load weights + tokenizer ONCE at container start (geneformer.md wrapper note).
        self.model = AutoModel.from_pretrained(HF_REPO_ID, trust_remote_code=True).eval().to("cuda")
        # self.tokenizer = <geneformer_tokenizer_load>   # CONFIRM ON RUN

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        # CONFIRM ON RUN — mirror the exact preprocess → tokenize → forward → pool path proven in Step 3.
        raise NotImplementedError("CONFIRM ON RUN — wire tokenize/forward/pool from the pinned Geneformer release")

mlflow.models.set_model(GeneformerEmbedder())
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
# MAGIC **What.** Log the PyFunc to MLflow with the signature + input example, registering it to UC, then run the
# MAGIC pre-deploy `mlflow.models.predict(...)` env check and promote a `@prod` alias.
# MAGIC
# MAGIC **Why.** `set_registry_uri("databricks-uc")` **before** logging is what sends the model to Unity Catalog rather
# MAGIC than the deprecated workspace registry (databricks-ml-training gotcha). Pinning `pip_requirements` to the exact
# MAGIC versions proven in Step 1 is what stops the endpoint from crashing on an env rebuild. For this TE model,
# MAGIC **`env_pack="databricks_model_serving"`** is roadmap §8's documented mitigation for reproducing a GPU-serving
# MAGIC env from a serverless-GPU notebook.
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

    with mlflow.start_run(run_name="geneformer-bionemo-spike"):
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model="model.py",              # file path, not an instance (Models from Code)
            signature=signature,
            input_example=input_example,
            pip_requirements=[                     # CONFIRM ON RUN — pin the exact versions proven in Step 1
                "mlflow",
                "transformer_engine[pytorch]",     # CONFIRM ON RUN — exact version
                "transformers",                    # CONFIRM ON RUN — exact version
                "torch",                           # CONFIRM ON RUN — exact torch/CUDA build
            ],
            # env_pack="databricks_model_serving", # CONFIRM ON RUN — roadmap §8 mitigation; confirm exact param name/placement
            registered_model_name=FULL_NAME,
        )

    # Pre-deploy validation — rebuilds the env and runs predict() locally BEFORE the endpoint does.
    # NOTE: needs a GPU host and a working predict() (Step 4) — expect this to surface the TE-build question early.
    mlflow.models.predict(model_uri=info.model_uri, input_data=input_example, env_manager="uv")  # CONFIRM ON RUN

    client = MlflowClient(registry_uri="databricks-uc")
    client.set_registered_model_alias(FULL_NAME, "prod", info.registered_model_version)
    print("Registered:", FULL_NAME, "version", info.registered_model_version)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 6 — Deploy to a GPU Model Serving endpoint
# MAGIC
# MAGIC **What.** Create a **GPU** serving endpoint for the registered model version.
# MAGIC
# MAGIC **Why / GPU tier suitability (roadmap §8).** TE is a CUDA extension. GPU tiers that satisfy TE:
# MAGIC **A10G / L40 / H100**. **T4 likely does NOT** (Turing < Ampere). Pick FP8-capable (Ada/Hopper: L40/H100) only
# MAGIC if the checkpoint is actually run in FP8; otherwise A10G (Ampere) is fine for BF16/FP16.
# MAGIC
# MAGIC **The exact GPU `workload_type` enum is NOT invented here.** Discover the valid values at run time with
# MAGIC `databricks serving-endpoints create -h` (databricks-model-serving: "run `create -h` to discover the required
# MAGIC JSON fields for your endpoint type"). **This cell is documented, not executed.**

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
                "workload_type":        "<GPU_WORKLOAD_TYPE>",  # CONFIRM ON RUN — e.g. an A10G/L40/H100 tier; discover via `serving-endpoints create -h`. NOT T4.
                # CONFIRM ON RUN — databricks-model-serving is silent on GPU scale-to-zero support; verify before
                # relying on this to avoid idle GPU billing (see the header warning).
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
# MAGIC **Why.** This is the whole point of the spike — prove one live inference works end-to-end through Serving. A GPU
# MAGIC endpoint keeps billing while it exists, so teardown is not optional. **Both cells are documented, not executed.**

# COMMAND ----------

import json

if not RUN_GO:
    print("run-gate off; set run_go=true to execute Step 7 scoring. Skipping.")
else:
    # Score one request. Custom PyFunc endpoints take dataframe_records (databricks-model-serving Query section).
    result = deploy.predict(
        endpoint=ENDPOINT_NAME,
        inputs={"dataframe_records": [{
            "cell_id":       "cell-0001",
            "genes":         ["<ensembl-gene-id-1>", "<ensembl-gene-id-2>", "<ensembl-gene-id-3>"],  # CONFIRM ON RUN
            "expression":    [12.0, 5.0, 3.0],
            "vocab_version": "<vocab-version>",                                                       # CONFIRM ON RUN
            "config":        json.dumps({"truncation": True, "gene_count_limit": "<max-input-tokens>",
                                         "pooling_mode": "<pooling-mode>", "output": "embedding"}),   # CONFIRM ON RUN
        }]},
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
