# Geneformer model reference

## Identity

* Model family: Geneformer (single-cell transcriptomic transformer encoder)
* Upstream code: https://github.com/jkobject/geneformer (jkobject fork — primary)
* Original HuggingFace: https://huggingface.co/ctheodoris/Geneformer (Path A checkpoint)
* NVIDIA BioNeMo checkpoint: https://huggingface.co/nvidia/geneformer_V2_316M (Path B checkpoint)
* Paper: https://doi.org/10.1038/s41586-023-06139-9
* Reviewed date: 2026-09-30
* Code license: Apache-2.0
* Weight terms: check Geneformer repo (verify on model card before distribution)

## What this model does

Geneformer is a transformer encoder foundation model for single-cell RNA-seq. Given gene expression profiles, it produces per-cell embedding vectors for downstream tasks: cell-type annotation, batch correction, perturbation prediction, and cross-dataset transfer. The model tokenizes cells by rank-ordering expressed genes and mapping to a learned vocabulary.

This reference covers **two validated deployment paths**:

| Path | Checkpoint | hidden_size | Vocab | Layers | Status |
|------|-----------|-------------|-------|--------|--------|
| **A. HF/ctheodoris** | `ctheodoris/Geneformer` → `Geneformer-V1-10M` | 256 | gc30M (25,426 tokens) | 6 | **Validated** |
| **B. NVIDIA BioNeMo** | `nvidia/geneformer_V2_316M` | 1152 | gc104M (20,275 tokens) | 18 | **Validated** |

Both paths are validated end-to-end on Databricks (serverless GPU, Model Serving GPU_SMALL A10G).

### Downstream applications

The per-cell embeddings serve as a universal featurization layer for:

* **Cell-type classification** — few-shot annotation of rare cell types using a lightweight head on frozen embeddings
* **Gene network inference** — attention weights encode gene-gene regulatory relationships; enables *in silico* perturbation studies
* **Patient stratification & drug discovery** — aggregate cell embeddings per sample for outcome prediction or target identification
* **Transfer learning** — broad pretraining (~100M cells) generalizes to unseen tissues and cell types with minimal labeled data

## Architecture comparison

| Property | Path A (V1-10M) | Path B (V2-316M) |
|----------|-----------------|-------------------|
| HF repo | `ctheodoris/Geneformer` | `nvidia/geneformer_V2_316M` |
| Checkpoint subdir | `Geneformer-V1-10M/` | (root — no subdir) |
| Parameters | ~10M | ~316M |
| hidden_size | 256 | 1152 |
| num_hidden_layers | 6 | 18 |
| max_position_embeddings | 2048 | 4096 |
| vocab | gc30M (25,426 tokens) | gc104M (20,275 tokens) |
| Token dict format | pickle (`.pkl`) | pickle (`.pkl`) |
| Token dict path | `geneformer/gene_dictionaries_30m/token_dictionary_gc30M.pkl` | shared: `geneformer/geneformer/token_dictionary_gc104M.pkl` |
| Safetensors size | ~40 MB | 1.36 GB |
| Architecture | Standard BERT encoder | BERT encoder, **post-norm** (not standard pre-norm) |
| `trust_remote_code` | No | **Yes** (custom `geneformer.py` with TE layers) |
| TransformerEngine | Not needed | Required by `config.json` (`use_te_layers: true`) — handled via stubs |
| `torch_dtype` | float32 | float32 (BF16 via autocast at inference) |
| UC model name | `<catalog>.<schema>.geneformer` | `<catalog>.<schema>.geneformer_bionemo` |
| Endpoint name | `geneformer_test` | `geneformer_bionemo_test` |
| GT notebook | `gt_geneformer` | `gt_geneformer_bionemo` |

### CLS vs mean pooling (Path B finding)

Smoke testing on Path B confirms CLS (`hidden_states[:, 0, :]`) and mean pooling produce **near-identical embeddings** (cosine ≈1.0, L2 distance ≈0.07–0.09 on vectors with L2-norm ≈34.5). Unlike standard BERT, Geneformer has no dedicated `[CLS]` token — position 0 is simply the highest-expressed gene after rank-ordering. The post-norm architecture distributes context broadly across all positions. **Mean pooling is the safer default**; CLS becomes meaningful only after fine-tuning with a classification head on position 0.

## Inputs and outputs

### Serving contract (both paths)

Both PyFunc wrappers accept per-cell inputs:

| Column | Type | Description |
|--------|------|-------------|
| `cell_id` | `str` | Cell identifier |
| `genes` | `list[str]` | Ensembl gene IDs (must be present in the token dictionary) |
| `expression` | `list[float]` | Raw counts aligned position-for-position to `genes` |
| `vocab_version` | `str` | Vocabulary version tag (`"v1"` for Path A, `"gc104M"` for Path B) |
| `config` | `str` (JSON) | `{"truncation": true, "gene_count_limit": "2048", "pooling_mode": "mean"}` |

### Input example (use real gene IDs from token dictionary)

```json
{
  "cell_id": "cell-0001",
  "genes": ["<ENSG-id-from-token-dict>", "<ENSG-id-from-token-dict>"],
  "expression": [2.0, 1.0],
  "vocab_version": "gc104M",
  "config": "{\"truncation\": true, \"gene_count_limit\": \"4096\", \"pooling_mode\": \"mean\"}"
}
```

```python
import pickle

# Token dictionaries are pickle, not JSON
with open(dict_path, "rb") as f:
    token_dict = pickle.load(f)
ensembl_genes = [g for g in token_dict.keys() if str(g).startswith("ENSG")][:10]

input_example = pd.DataFrame([{
    "cell_id": "cell-0001",
    "genes": ensembl_genes,
    "expression": [float(i) for i in range(len(ensembl_genes), 0, -1)],
    "vocab_version": "gc104M",  # or "v1" for Path A
    "config": json.dumps({"truncation": True, "gene_count_limit": "4096", "pooling_mode": "mean"}),
}])
```

**Critical**: always use real Ensembl IDs from the token dictionary. Synthetic gene names produce degenerate embeddings.

### Output

```json
{
  "cell_id": "cell-0001",
  "embedding": [0.37, -1.56, 0.08],
  "embedding_dim": 1152,
  "vocab_version": "gc104M"
}
```

Embedding dimension equals the model's `hidden_size` (256 for Path A, 1152 for Path B).

## Artifacts and runtime

### HF repo structure (`ctheodoris/Geneformer` — Path A)

| Path | Purpose |
|------|---------|
| `Geneformer-V1-10M/` | 10M-param checkpoint (6 layers) — **validated** |
| `geneformer/gene_dictionaries_30m/token_dictionary_gc30M.pkl` | gc30M token dictionary (pickle) |

### HF repo structure (`nvidia/geneformer_V2_316M` — Path B)

| Path | Purpose |
|------|---------|
| `config.json` | Model config (`use_te_layers: true`, `auto_map` for custom classes) |
| `geneformer.py` | Custom model code (requires `trust_remote_code=True`) |
| `model.safetensors` | 1.36 GB weights |
| Token dict: shared from ctheodoris snapshot | `geneformer/geneformer/token_dictionary_gc104M.pkl` |

The token dictionary file name varies by release — discover it at runtime:

```python
import os, pickle

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
```

### Download

Use `huggingface_hub.snapshot_download` to local temp, then copy to UC Volume:

```python
from huggingface_hub import snapshot_download
snapshot_download(repo_id=HF_REPO, local_dir=LOCAL_DIR)
```

Use sentinel files (`.snapshot_complete`, `.copy_complete`) for idempotent re-runs.

### Compute requirements

| Task | Compute |
|------|---------|
| Download from HF | CPU (Serverless or classic). Adaptive storage (`/local_disk0/tmp` or `/tmp`). |
| Dry-load, log model, register | **GPU required**. Serverless GPU (1×A10G) validated. |
| Model Serving endpoint | `GPU_SMALL` (A10G). Both paths validated. |

Path A (10M params) fits easily on A10G. Path B (316M params, 1.36 GB safetensors) also fits on A10G with headroom.

### Dependencies (Path A)

```python
pip_requirements = ["torch", "transformers", "numpy"]
```

### Dependencies (Path B)

```python
pip_requirements = ["torch>=2.0.0", "transformers>=4.30.0,<4.52.0"]
```

**Note**: Path B does NOT require `transformer_engine` as a pip dependency. TE is handled via functional `nn.Module` stubs — see "TransformerEngine stubs" below.

**Pin `transformers<4.52`**: `geneformer.py` calls `self.get_head_mask()`, which was removed from `PreTrainedModel` in transformers 4.52.

## Known issues and workarounds

### TransformerEngine (TE) stubs (Path B only)

`geneformer.py` does `import transformer_engine.pytorch as te` at the **top level** and uses `te.Linear`, `te.LayerNorm`, `te.MultiheadAttention` throughout. TE requires a CUDA toolkit source build (`pyproject.toml` → CMake → `transformer_engine_torch`), which **fails on serverless GPU** (no dev toolchain) and in Model Serving containers.

Workaround: **functional `nn.Module` stubs** installed into `sys.modules["transformer_engine.pytorch"]` before any `from_pretrained` call.

* Stubs implement `_StubLinear(nn.Linear)`, `_StubLayerNorm(nn.LayerNorm)`, `_StubMultiheadAttention(nn.Module)` with fused QKV.
* Weight-key names match the safetensors state dict (`qkv.weight`, `proj.weight`, `layernorm.weight`, `layernorm_mlp.fc1/fc2`) so `from_pretrained` loads without renaming.
* Stubs are installed in **two places**: the notebook setup cell (for dry-load) and inside `GeneformerBioNeMo.load_context()` (for the serving container, which has no prior kernel state).
* Mark stubs with `__version__ = "0.0.0-stub"` so they can be distinguished from real TE.

### `get_head_mask` removal (transformers ≥4.52)

`geneformer.py` calls `self.get_head_mask(head_mask, num_layers)` — a method removed from `PreTrainedModel` in transformers 4.52. Fix: pin `transformers<4.52` in pip requirements **and** patch the method back onto `PreTrainedModel` at runtime as a safety net:

```python
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
```

### `isatty()` crash in Model Serving (Path A)

The serving container replaces `sys.stdout` with `StreamToLogger`, which lacks `isatty()`. Transformers' loading report calls `sys.stdout.isatty()` and crashes. Fix in `load_context`:

```python
import sys
for stream in (sys.stdout, sys.stderr):
    if stream is not None and not hasattr(stream, "isatty"):
        stream.isatty = lambda: False
```

### Inference table name conflicts

Model Serving rejects `create_endpoint` when the auto-generated inference table name (`<endpoint>_payload`) already exists from a prior failed deploy. Fix: timestamped table prefix `<endpoint>_YYYYMMDDHHMM_payload`.

### Endpoint provisioning time

GPU_SMALL (A10G) endpoints routinely take 15–25 min to provision. Poll with a **1800 s timeout** (30 min) and detect `DEPLOYMENT_FAILED` early:

```python
from databricks.sdk.service.serving import ServedModelStateDeployment
# Inside poll loop:
for cfg in [ep.pending_config, ep.config]:
    if cfg and cfg.served_entities:
        for se in cfg.served_entities:
            if se.state and se.state.deployment == ServedModelStateDeployment.DEPLOYMENT_FAILED:
                raise RuntimeError(f"DEPLOYMENT_FAILED: {se.state.deployment_state_message}")
```

## Notebook architecture

Each path has its own **self-contained GT notebook** (download → register → deploy → smoke test → teardown):

| Notebook | Path | Phases |
|----------|------|--------|
| `gt_geneformer` | A (HF/ctheodoris) | Setup → Download (restart 1) → Register (restart 2) → Deploy → Smoke test → Teardown |
| `gt_geneformer_bionemo` | B (NVIDIA BioNeMo) | Setup → Download (restart 1) → Register (restart 2) → Deploy → Smoke test → Teardown |

Both notebooks use:
* Widget-based configuration (`catalog`, `schema`, `volume_name`, `endpoint_name`, `run_go`)
* `run_go` gate for expensive operations (deploy, endpoint creation)
* Idempotent cleanup cell before registration (delete existing endpoint + model versions)
* Sentinel files for download idempotency
* Dry-load test before `log_model` (pre-deploy gate)

Path A uses **file-based logging** (`python_model=WRAPPER_PATH`) following the gt_teddy pattern to avoid cloudpickle version mismatches. Path B uses **class-based logging** (cloudpickle) since the TE stubs must be self-contained inside `load_context`.

## Wrapper boundary

### Path A: `GeneformerEmbedder`

```python
class GeneformerEmbedder(mlflow.pyfunc.PythonModel):
    """Wraps ctheodoris Geneformer V1-10M for per-cell embeddings.
    Standard HF loading — no trust_remote_code needed."""
```

Artifacts: `{"checkpoint_dir": CHECKPOINT_DIR, "token_dict": dict_path}`

### Path B: `GeneformerBioNeMo`

```python
class GeneformerBioNeMo(mlflow.pyfunc.PythonModel):
    """Wraps NVIDIA BioNeMo Geneformer V2-316M for per-cell embeddings.
    Requires trust_remote_code=True. Installs TE stubs in load_context."""
```

Artifacts: `{"model_dir": SNAPSHOT_DIR, "token_dict": dict_path}`

### `load_context` key differences

| Aspect | Path A | Path B |
|--------|--------|--------|
| `trust_remote_code` | Not needed | **Required** |
| TE stubs | Not needed | Installed inside `load_context` |
| `get_head_mask` shim | Not needed | Patched inside `load_context` |
| `isatty()` fix | **Required** | Not needed (not observed) |
| Token dict format | pickle | pickle |

## Deployment recommendation

* `GPU_SMALL` (A10G) with `scale_to_zero_enabled=True`.
* Use `ServingModelWorkloadType.GPU_SMALL` SDK enum (not string literal).
* Enable AI Gateway inference table + usage tracking.
* `run_go` gate widget to prevent accidental deployment.
* **Prefer Jobs** for dataset-scale embedding, preprocessing, or fine-tuning.
* Path A is simpler (no stubs). Path B produces richer embeddings (1152-dim vs 256-dim).

## Registration and observability

| Path | UC model name | Inference table |
|------|--------------|------------------|
| A | `<catalog>.<schema>.geneformer` | `<endpoint>_payload` |
| B | `<catalog>.<schema>.geneformer_bionemo` | `<endpoint>_YYYYMMDDHHMM_payload` (timestamped) |

Log license, HF source URL, paper DOI, and checkpoint name as MLflow tags.

## Validation checklist

1. **Token dictionary discovery**: find correct `.pkl` file in snapshot (gc30M for Path A, gc104M for Path B).
2. **Real Ensembl IDs**: `input_example` uses real gene IDs from the token dictionary, not synthetic.
3. **Dry-load test**: PyFunc `load_context()` completes on GPU without errors.
4. **Forward pass test**: model produces embedding with expected dimension (256 for Path A, 1152 for Path B).
5. **Signature test**: `infer_signature` with `input_example` and `output_example`.
6. **SDK query test**: `w.serving_endpoints.query()` returns valid embeddings from deployed endpoint.
7. **Endpoint teardown**: tear down immediately after validation to stop GPU billing.
8. **(Path B only) TE stub validation**: TE stubs load correctly in both notebook and serving container.
9. **(Path B only) `get_head_mask` shim**: verify transformers version pin + runtime patch.

## Resolved questions

* **TE in Model Serving container**: TE does NOT build in serving containers. Functional `nn.Module` stubs are the validated workaround — no TE source build needed.
* **GPU tier for 316M**: A10G (`GPU_SMALL`) handles the 1.36 GB model comfortably.
* **BF16 vs FP32**: `torch.autocast(dtype=torch.bfloat16)` works correctly on A10G for both paths. Weights stored as float32, autocast at inference.
* **Embedding dimensions**: 256 for V1-10M (Path A), 1152 for V2-316M (Path B) — confirmed via `config.json` and smoke tests.
* **CLS vs mean pooling**: Near-identical for both paths (no dedicated CLS token). Mean pooling is the default.

## Open questions

* Whether the `geneformer-6L-30M` or `geneformer-12L-30M` checkpoints from ctheodoris offer meaningful improvements over V1-10M for specific downstream tasks.
* Latency and throughput benchmarks at scale (batch queries, concurrent requests).
* Fine-tuning workflow for cell-type classification heads on frozen embeddings.
