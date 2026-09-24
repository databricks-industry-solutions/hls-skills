# TEDDY model reference

## Identity

* Model family: TEDDY (Transformer Encoder for DNA and scRNA-seq)
* Upstream code and weights URL: https://huggingface.co/Merck/TEDDY
* Model card: https://huggingface.co/Merck/TEDDY
* Paper: arXiv:2503.03485
* Reviewed date: 2026-09-05
* Upstream revision: pinned via `snapshot_download` — record the commit SHA from `.gitattributes` after download
* Code license: Apache-2.0
* Weight terms: Apache-2.0 (verify on model card before distribution)
* Variants: 70M, 160M, 400M (parameter count)

## What this model does

TEDDY-G is a transformer encoder foundation model pre-trained on 116 million single-cell RNA-seq (scRNA-seq) cells. It produces per-cell embedding vectors from gene expression profiles. The model selects the top-K most expressed genes per cell, rank-encodes their expression values as linearly spaced floats from 1.0 (highest) to −1.0 (lowest), and passes the sequence through a transformer encoder. The resulting embeddings are used for cell-type annotation, batch correction, perturbation prediction, and cross-dataset transfer. This reference covers **online inference** (bounded per-cell queries to a Model Serving endpoint); for large-batch embedding of AnnData objects use a Job.

## Inputs and outputs

### Serving contract

The model does not accept a raw AnnData object. Transport as three DataFrame columns per row; all three are **required** by the MLflow signature and must be present in every request payload, even if `adata_obs` is not used by the model internals.

| Column | Type | Description |
|--------|------|-------------|
| `adata_sparsematrix` | `list[list[float]]` | Dense expression matrix, shape `(cells, genes)`. One sublist per cell; values are raw or normalised counts. |
| `adata_obs` | `str` — JSON orient=`split` | Cell metadata DataFrame. Required by the signature; not consumed by `predict`. Include at minimum a `cell_id` column. |
| `adata_var` | `str` — JSON orient=`split` | Gene metadata DataFrame. Must have an `index` column containing Ensembl gene IDs (`ENSGXXXXXXXXXXX`) that match `vocab.txt`. |

Inference controls are passed as `extra_params` (Databricks Python SDK) or the `params` field (MLflow local):

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `max_seq_len` | int (pass as `str` via SDK) | 2048 | Top-K genes selected per cell. |
| `pooling` | str | `"mean"` | `"mean"` pools over all token positions; `"cls"` uses the CLS token (only valid when `config.add_cls=True`). |

### Output

```text
{"predictions": [{"embedding": [<float>, ...]}, ...]}
```

One dict per input cell. Embedding dimension equals `config.d_model` (read from `config.json` in the checkpoint directory).

### Python `input_example` (use real vocab gene IDs)

```python
import pandas as pd
import numpy as np

# Read real Ensembl IDs from vocab.txt — do NOT invent gene names
vocab_path = f"{model_dir}/vocab.txt"
with open(vocab_path) as f:
    vocab_tokens = [t.strip() for t in f if t.strip()]
real_genes = [t for t in vocab_tokens if not t.startswith("<")][:100]  # skip special tokens

n_cells, n_genes = 5, len(real_genes)
expr = np.random.default_rng(42).poisson(2.0, size=(n_cells, n_genes)).astype(np.float32)

obs_df = pd.DataFrame({"cell_id": [f"cell_{i}" for i in range(n_cells)]})
var_df = pd.DataFrame({"index": real_genes})

input_example = pd.DataFrame({
    "adata_sparsematrix": [expr.tolist()],           # one row = one batch
    "adata_obs":          [obs_df.to_json(orient="split")],
    "adata_var":          [var_df.to_json(orient="split")],
})
```

**Critical**: always use real Ensembl IDs from `vocab.txt` when constructing test payloads. Synthetic gene names will all map to the `<unk>` token and produce degenerate embeddings that cannot validate the tokenisation path.

### HTTP payload (Databricks SDK)

```python
response = w.serving_endpoints.query(
    name=ENDPOINT_NAME,
    dataframe_records=[{
        "adata_sparsematrix": expr.tolist(),
        "adata_obs":          obs_df.to_json(orient="split"),
        "adata_var":          var_df.to_json(orient="split"),
    }],
    extra_params={"max_seq_len": "2048", "pooling": "mean"},  # values MUST be strings
)
```

Note: the SDK's `serving_endpoints.query()` uses `extra_params: Dict[str, str]`, **not** `params`. Values must be strings; the PyFunc wrapper should cast them: `int(params.get("max_seq_len", 2048))`, `str(params.get("pooling", "mean"))`.

## Artifacts and runtime

### Checkpoint directory (`model_dir`)

Path: `<VOLUME_PATH>/snapshot/teddy/models/teddy_g/<VARIANT>/`

| File | Size (70M) | Purpose |
|------|------------|----------|
| `model.safetensors` | ~285 MB | Model weights |
| `vocab.txt` | ~756 KB | ~60 K Ensembl gene IDs (one per line); used by `GeneTokenizer.from_pretrained()` |
| `config.json` | — | Architecture config (`d_model`, `add_cls`, `cls_token_id`, …) |
| `tokenizer_config.json` | — | Tokenizer init config |
| `added_tokens.json` | — | Special tokens (`<pad>`, `<mask>`, `<unk>`) |
| `special_tokens_map.json` | — | Maps special-token roles |

### Code bundle (`teddy_pkg_parent`)

Stage a copy of `<VOLUME_PATH>/snapshot/teddy/` **without weights** to `/tmp/teddy_code` using `shutil.copytree` with `ignore=shutil.ignore_patterns("*.safetensors", "*.bin", "*.ckpt", "*.pt")`. This produces `~30 MB` of Python source. Pass `clean_code_dir = "/tmp/teddy_code"` as the `teddy_pkg_parent` artifact so `load_context` can insert it into `sys.path`.

### Key source files (read before writing `load_context`)

| File | Exports used in wrapper |
|------|------------------------|
| `teddy/models/model_directory.py` | `get_architecture(model_dir)`, `model_dict` |
| `teddy/models/teddy_g/model.py` | `TeddyGConfig`, `TeddyGModel` (via `model_dict`) |
| `teddy/tokenizer/gene_tokenizer.py` | `GeneTokenizer` — `from_pretrained(model_dir)` reads `vocab.txt` from the CHECKPOINT dir, not `teddy/tokenizer/` |

### Hugging Face download

The TEDDY repo uses HF's **Xet/CAS storage backend**. Standard HTTP download fails with:
```
RuntimeError: CAS service error: IO Error: Illegal seek (os error 29)
```
Fix — set the env var **before the first import of `huggingface_hub`** in the process:
```python
import os
os.environ["HF_HUB_DISABLE_XET"] = "1"  # must come before any huggingface_hub import
from huggingface_hub import snapshot_download
snapshot_download(repo_id="Merck/TEDDY", local_dir=local_dir)
```
If `huggingface_hub` was already imported in the session, restart the Python kernel first.

### Compute requirements

| Task | Compute |
|------|---------|
| Download from HF | CPU (Serverless or classic). Write to `/tmp`, not `/local_disk0`. |
| Dry-load test, log model, register | GPU (Serverless GPU or GPU classic). |
| Model Serving endpoint | `GPU_SMALL` (A10G, 24 GB VRAM) is sufficient for all three variants: 70M (~140 MB), 160M (~320 MB), 400M (~800 MB) in bfloat16. H100 is not required. scale-to-zero enabled. |

### Dependencies (from `pyproject.toml`)

```python
pip_requirements = [
    "torch>=2.3.0",
    "transformers==4.41.0",   # EXACT — 5.x breaks TeddyGModel (all_tied_weights_keys)
    "numpy>=1.26.4,<2.0",    # numpy 2.x has C-ABI breaking changes
    "pandas>=2.2.2,<3.0",    # pandas 3.x has breaking changes
    # anndata — NOT in the serving path; do not include
]
```

`transformers` must be pinned exactly to `4.41.0`. In transformers 5.x, `PreTrainedModel._move_missing_keys_from_meta_to_device` calls `self.all_tied_weights_keys.keys()` on a dict; `TeddyGModel` only implements `_tied_weights_keys` (a list from 4.x). An unpinned `>=4.40` resolves to 5.x in the serving container and fails with `AttributeError: 'TeddyGModel' object has no attribute 'all_tied_weights_keys'`.

## Notebook architecture

Use **two separate notebooks**:

1. **Download notebook (CPU)** — installs `huggingface_hub`, sets `HF_HUB_DISABLE_XET=1` before importing it, calls `snapshot_download`, copies the snapshot to a UC Volume. Does not require GPU.
2. **Register and deploy notebook (GPU)** — reads the snapshot from the Volume, stages a stripped code bundle to `/tmp/teddy_code`, runs the dry-load test on GPU, logs and registers the model to Unity Catalog, deploys to a Model Serving endpoint.

Separating these avoids wasting GPU time on downloads and makes each notebook independently re-entrant.

## Wrapper boundary

### Imports inside the PyFunc class cell

Every symbol used inside class methods must be imported **in the same cell** as the class definition. The serving container deserialises the class in a fresh Python process with no notebook globals. At minimum:

```python
import sys, os, io, inspect
import mlflow, pandas as pd, numpy as np, torch
```

Do **not** rely on `sys`, `os`, or `io` being available from a notebook-level `import os, sys` — they will not exist in the serving container.

### `load_context` pattern

```python
def load_context(self, context):
    import sys  # explicit — not available from notebook globals in serving container
    teddy_pkg_parent = context.artifacts["teddy_pkg_parent"]
    if teddy_pkg_parent not in sys.path:
        sys.path.insert(0, teddy_pkg_parent)

    from teddy.models.model_directory import get_architecture, model_dict
    from teddy.tokenizer.gene_tokenizer import GeneTokenizer

    model_dir = context.artifacts["model_dir"]
    arch = get_architecture(model_dir)
    config_cls = model_dict[arch]["config_cls"]
    model_cls  = model_dict[arch]["model_cls"]

    self.config    = config_cls.from_pretrained(model_dir)
    self.model     = model_cls.from_pretrained(model_dir, config=self.config)
    self.device    = "cuda" if torch.cuda.is_available() else "cpu"
    self.model.to(self.device).eval()
    self.tokenizer = GeneTokenizer.from_pretrained(model_dir)  # reads vocab.txt from model_dir
    self._forward_params = set(inspect.signature(self.model.forward).parameters.keys())
    self.add_cls     = bool(getattr(self.config, "add_cls", False))
    self.cls_token_id = int(getattr(self.config, "cls_token_id", 0))
    self.d_model     = int(getattr(self.config, "d_model", 0))
    self._use_bf16   = (self.device == "cuda")
```

### OOV gene handling

Genes absent from `vocab.txt` return `None` from `convert_tokens_to_ids`. Fall back to `unk_token_id`:

```python
unk_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.unk_token)
ids = self.tokenizer.convert_tokens_to_ids(list(gene_names))
ids = [unk_id if i is None else i for i in ids]
```

### Top-K selection and rank encoding

TEDDY does not consume raw expression counts; it selects the top-K most expressed genes and rank-encodes their positions:

```python
k = min(max_seq_len, X.shape[1])
_, top_idx = torch.topk(X_t, k=k, largest=True, sorted=True)
gene_ids   = token_array[top_idx]                             # (cells, k)
rank_vec   = torch.linspace(1.0, -1.0, steps=k)              # 1.0 = highest expression
gene_vals  = rank_vec.unsqueeze(0).expand(cells, -1).clone()
```

### `predict` — `pd.read_json` on newer pandas

Pandas 2.1+ deprecates passing a literal JSON string directly; always wrap:
```python
var_df = pd.read_json(io.StringIO(row["adata_var"]), orient="split")
```

### Stale module cache (out-of-order cell execution)

In a long-lived kernel, a prior partial import of the `teddy` package can persist in `sys.modules` and cause `ModuleNotFoundError` for submodules on re-run. Purge before calling `load_context`:

```python
for _m in list(sys.modules):
    if _m == "teddy" or _m.startswith("teddy."):
        del sys.modules[_m]
if clean_code_dir in sys.path:
    sys.path.remove(clean_code_dir)
sys.path.insert(0, clean_code_dir)
```

## Deployment recommendation

**Model Serving** is appropriate for the 70M variant and bounded per-cell queries:

* Checkpoint fits on `GPU_SMALL` with headroom; `scale_to_zero_enabled=True` reduces cost.
* Larger variants (160M, 400M) may require `GPU_MEDIUM`; verify with a local dry-load.
* For full-AnnData batch embedding (thousands to millions of cells), prefer a Job that reads the Volume snapshot directly and writes embeddings back to Unity Catalog.

## Registration and observability

Register to Unity Catalog as `<catalog>.<schema>.teddy_<variant>` (e.g. `main.scratch.teddy_70m`). Log Apache-2.0 license, paper DOI, HF source URL, and variant as MLflow tags. If inference tables are enabled, `adata_sparsematrix` and `adata_var` contain gene expression profiles — classify before logging; prefer logging only `cell_id`, embedding dimension, and variant tag.

## Validation checklist

1. **Vocabulary smoke test**: load `vocab.txt`, verify ~60 K lines, check that `ENSG00000000003` is present.
2. **Import test**: in the serving container environment, `from teddy.models.model_directory import get_architecture, model_dict` and `from teddy.tokenizer.gene_tokenizer import GeneTokenizer` succeed.
3. **Dry-load test**: `load_context` completes, prints `TEDDY-G 70M loaded on cuda, d_model=…`.
4. **Signature test**: `infer_signature` on `input_example` produces schema with all three columns (`adata_sparsematrix`, `adata_obs`, `adata_var`) as required fields.
5. **Real-gene payload test**: test payload uses Ensembl IDs from `vocab.txt`; embeddings are non-degenerate (not all the same value, norm > 0).
6. **All-OOV payload test**: all gene names set to random strings → all map to `<unk>` → model still returns an embedding without raising an exception.
7. **Missing-field test**: omit `adata_obs` from the request → endpoint returns a schema-validation error (confirming the signature enforces all three fields).
8. **SDK query test**: `w.serving_endpoints.query(extra_params={"max_seq_len": "2048", "pooling": "mean"})` succeeds (values as strings, not ints).
9. **Embedding sanity**: for 70M, embedding dimension should match `config.d_model` (read from `config.json`).

## Open questions

* Whether HF_HUB_DISABLE_XET will remain necessary as HF updates the Xet client.
* Whether the `transformers==4.41.0` exact pin will need to be updated for future TEDDY releases.
* Optimal `max_seq_len` for 160M and 400M variants (may differ from 70M default of 2048).
* Whether per-cell `adata_obs` metadata (batch label, donor ID) should be echoed back in the response to aid downstream correlation.
