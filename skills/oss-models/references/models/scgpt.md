# scGPT model reference

## Identity

* Model family: scGPT (single-cell generative pre-trained transformer)
* Upstream code: https://github.com/bowang-lab/scGPT
* Weights: [Google Drive — Model Zoo](https://drive.google.com/drive/folders/1oWh_-ZRdhtoGQ2Fw24HP41FgLoomVo-y?usp=sharing) (whole-human checkpoint)
* Package: `scgpt==0.2.4` (PyPI)
* Paper: [Cui et al., Nature Methods 2024](https://www.nature.com/articles/s41592-024-02201-0)
* Reviewed date: 2026-09-24
* Code license: check scGPT repo
* Weight terms: check scGPT repo
* Genesis Workbench: https://github.com/databricks-industry-solutions/genesis-workbench (`modules/single_cell/scgpt`)

## What this model does

scGPT is a generative pre-trained transformer for single-cell biology. Given gene expression profiles, it produces gene embeddings for downstream tasks: cell-type annotation, batch correction, perturbation prediction, and generation. The model uses a gene-name vocabulary (`vocab.json`), and its preprocessing pipeline normalizes, selects highly variable genes, and bins expression values.

This reference covers the **whole-human checkpoint** (embedding task) deployed via custom PyFunc. The perturbation model (`03_register_scgpt_perturbation.py`) is a separate deployment.

## Inputs and outputs

### Serving contract

The `TransformerModelWrapper` PyFunc accepts three JSON-encoded columns (same pattern as TEDDY):

| Column | Type | Description |
|--------|------|-------------|
| `adata_sparsematrix` | `list[list[float]]` | Dense expression matrix, shape `(cells, genes)`. |
| `adata_obs` | `str` — JSON orient=`split` | Cell metadata DataFrame. Must include `batch` and optionally `final_annotation`. |
| `adata_var` | `str` — JSON orient=`split` | Gene metadata DataFrame with `gene_name` column. |

Inference controls via `params` (MLflow local) or `extra_params` (SDK):

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `need_preprocess` | bool (as str via SDK) | `True` | Whether to run the scGPT `Preprocessor` |
| `subset_hvg` | int (as str) | `1200` | Number of highly variable genes to select |
| `binning` | int (as str) | `51` | Number of expression bins |
| `filter_gene_by_counts` | int (as str) | `3` | Minimum gene count filter |
| `normalize_total` | float (as str) | `1e4` | Target sum for normalization |

### Output

```json
{
  "predictions": {
    "GENE1": [0.1, 0.2, -0.5, 0.8],
    "GENE2": [-0.3, 0.4, 0.1, -0.7]
  }
}
```

> Embedding vectors are truncated for readability; actual vectors have `hidden_size` floats per gene.

Returns a dict of `{gene_name: embedding_vector}` for genes present in both the vocabulary and the preprocessed input.

### Input example (Python)

```python
import numpy as np, pandas as pd, json

rng = np.random.default_rng(42)
n_cells, n_genes = 10, 100
expr = rng.poisson(2.0, size=(n_cells, n_genes)).astype(float).tolist()

obs = json.dumps({"columns": ["batch", "final_annotation"],
                  "index": [str(i) for i in range(n_cells)],
                  "data": [["batch0", "T cell"]] * n_cells})
var = json.dumps({"columns": ["gene_name"],
                  "index": [f"GENE{i}" for i in range(n_genes)],
                  "data": [[f"GENE{i}"]] * n_genes})

input_example = pd.DataFrame([{
    "adata_sparsematrix": expr,
    "adata_obs": obs,
    "adata_var": var,
}])
```

HTTP request equivalent (JSON):

```json
{
  "dataframe_records": [
    {
      "adata_sparsematrix": [[2.0, 0.0, 5.0], [0.0, 3.0, 1.0]],
      "adata_obs": "{\"columns\": [\"batch\", \"final_annotation\"], \"index\": [\"0\", \"1\"], \"data\": [[\"batch0\", \"T cell\"], [\"batch0\", \"B cell\"]]}",
      "adata_var": "{\"columns\": [\"gene_name\"], \"index\": [\"GENE0\", \"GENE1\", \"GENE2\"], \"data\": [[\"GENE0\"], [\"GENE1\"], [\"GENE2\"]]}"
    }
  ]
}
```

> The example uses a 2-cell, 3-gene matrix. Real inputs should use gene names from the model vocabulary and `orient="split"` JSON encoding for obs/var DataFrames.

### HTTP payload (Databricks SDK)

```python
response = w.serving_endpoints.query(
    name=ENDPOINT_NAME,
    dataframe_records=[{
        "adata_sparsematrix": expr,
        "adata_obs": obs,
        "adata_var": var,
    }],
    extra_params={"need_preprocess": "True", "subset_hvg": "1200", "binning": "51"},
)
```

## Artifacts and runtime

### Checkpoint files (whole-human)

Path: `<VOLUME_PATH>/models/` (from Google Drive download)

| File | Purpose |
|------|---------|
| `best_model.pt` | Model weights (~140 MB) |
| `args.json` | Model config (embsize, nheads, d_hid, nlayers, n_bins, n_hvg, pad_value, mask_value) |
| `vocab.json` | Gene-name vocabulary |

### Download

Weights are on **Google Drive** (not HuggingFace or Zenodo). Use `gdown`:

```python
import gdown

GDRIVE_FOLDER_ID = "1oWh_-ZRdhtoGQ2Fw24HP41FgLoomVo-y"
model_dir = f"{cache_full_path}/models/"
gdown.download_folder(id=GDRIVE_FOLDER_ID, output=f"{model_dir}/")
```

After download, walk the output to find the directory containing `best_model.pt` (gdown may nest subdirectories).

### Sample data

From Figshare (h5ad format):

```python
import wget as wget_lib
wget_lib.download("https://api.figshare.com/v2/file/download/25717328", f"{data_dir}/file.h5ad")
```

### Compute requirements

| Task | Compute |
|------|---------|
| Download (gdown + wget) | CPU (Serverless or classic). Write to `/tmp`. Install `gdown` + `wget`. |
| Register (PyFunc + log_model) | **GPU required** — `flash-attn` needs CUDA at import time. |
| Model Serving endpoint | `GPU_SMALL` (A10G). `flash-attn` requires GPU at import. |

**Critical**: `flash-attn` (a dependency of `scgpt`) **requires GPU at Python import time**, not just at inference. This means:
* The register/deploy notebook must run on GPU compute
* The serving container must have GPU (CPU-only serving will fail at `import scgpt`)

### Adaptive storage

```python
try:
    os.makedirs("/local_disk0/tmp", exist_ok=True)
    TMP_DIR = "/local_disk0/tmp"
except (PermissionError, OSError):
    TMP_DIR = "/tmp"  # Serverless
```

### Dependencies

```python
pip_requirements = [
    "scgpt==0.2.4",
    "flash-attn",
    "torch",
    "scanpy",
    "scipy",
    "numpy",
    "pandas",
    "mlflow==2.22.0",
]
```

Install line: `%pip install -q scgpt==0.2.4 flash-attn scanpy==1.11.2 gdown torch mlflow==2.22.0 scipy numpy pandas`

## Notebook architecture

Use **two separate notebooks**:

1. **Download notebook (CPU)** — `gdown` from Google Drive + `wget` from Figshare. No GPU. Installs `gdown` + `wget` only. Sentinel files for idempotency. Provenance manifest.
2. **Register and deploy notebook (GPU)** — loads model on GPU (flash-attn requires it), wraps in `TransformerModelWrapper` PyFunc, builds input_example from sample data, infers signature, registers to UC, deploys to GPU Model Serving endpoint.

Use `run_go` widget gate for expensive operations.

### GWB lineage

| GWB notebook | This notebook |
|---|---|
| `01_register_scgpt.py` | Phase 1, register (standalone, no GWB wheel) |
| `02_import_model_gwb.py` | **Replaced** by Phase 2 (SDK-only deploy) |
| `03_register_scgpt_perturbation.py` | Not included — add as Phase 1b if needed |

## Wrapper boundary

### `TransformerModelWrapper` PyFunc class

```python
class TransformerModelWrapper(mlflow.pyfunc.PythonModel):
    """scGPT gene embedding model. Adapted from GWB 01_register_scgpt.
    Input: adata_sparsematrix + adata_obs + adata_var (JSON orient=split).
    Output: gene embeddings dict {gene_name: embedding_vector}.
    """
    def __init__(self, special_tokens=["<pad>", "<cls>", "<eoc>"]):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.special_tokens = special_tokens
```

### Artifacts

```python
artifacts = {
    "model_file": model_file,           # best_model.pt
    "model_config_file": model_config_file,  # args.json
    "vocab_file": vocab_file,            # vocab.json
}
```

### `load_context` pattern

```python
def load_context(self, context):
    import json, torch
    from scgpt.tokenizer.gene_tokenizer import GeneVocab
    from scgpt.model import TransformerModel

    self.vocab = GeneVocab.from_file(context.artifacts["vocab_file"])
    for s in self.special_tokens:
        if s not in self.vocab:
            self.vocab.append_token(s)
    self.gene2idx = self.vocab.get_stoi()

    with open(context.artifacts["model_config_file"]) as f:
        cfg = json.load(f)

    self._loaded_model = TransformerModel(
        ntoken=len(self.vocab), d_model=cfg["embsize"],
        nhead=cfg["nheads"], d_hid=cfg["d_hid"],
        nlayers=cfg["nlayers"], vocab=self.vocab,
        pad_value=cfg["pad_value"], n_input_bins=cfg["n_bins"],
    )
    # Partial state_dict load (handles shape mismatches gracefully)
    try:
        self._loaded_model.load_state_dict(
            torch.load(context.artifacts["model_file"], map_location=self.device)
        )
    except Exception:
        model_dict = self._loaded_model.state_dict()
        pretrained = torch.load(context.artifacts["model_file"], map_location=self.device)
        pretrained = {k: v for k, v in pretrained.items()
                      if k in model_dict and v.shape == model_dict[k].shape}
        model_dict.update(pretrained)
        self._loaded_model.load_state_dict(model_dict)

    self._loaded_model.to(self.device).eval()
```

### `preprocess` pattern

Uses `scgpt.preprocess.Preprocessor` to normalize and bin expression data:

```python
def preprocess(self, context, input_dataframe=None, params=None):
    from scgpt.preprocess import Preprocessor
    import scipy.sparse, scanpy

    adata_sparsematrix = scipy.sparse.csr_matrix(input_dataframe['adata_sparsematrix'][0])
    adata_obs = pd.read_json(input_dataframe['adata_obs'][0], orient='split')
    adata_var = pd.read_json(input_dataframe['adata_var'][0], orient='split')
    loaded_data = scanpy.AnnData(adata_sparsematrix, obs=adata_obs, var=adata_var)

    preprocessor = Preprocessor(
        use_key=params.get("use_key", "X"),
        subset_hvg=params.get("subset_hvg", self.n_hvg),
        binning=params.get("binning", self.n_bins),
        # ... additional params
    )
    preprocessor(loaded_data)
    return loaded_data
```

### `predict` pattern

```python
def predict(self, context, model_input=None, params=None):
    if params.get("need_preprocess", True):
        preprocessed = self.preprocess(context, model_input, params)
    else:
        preprocessed = model_input

    gene_embeddings = self._loaded_model.encoder(
        torch.tensor(list(self.gene2idx.values()), dtype=torch.long).to(self.device)
    )
    gene_embeddings = gene_embeddings.detach().cpu().numpy()

    filtered = {
        gene: gene_embeddings[i]
        for i, gene in enumerate(self.gene2idx.keys())
        if gene in preprocessed.var.index.tolist()
    }
    return {k: v.tolist() for k, v in filtered.items()}
```

## Deployment recommendation

**Model Serving** on `GPU_SMALL` (A10G) is appropriate for bounded gene-embedding requests:

* `scale_to_zero_enabled=True` with `ServingModelWorkloadType.GPU_SMALL`.
* Enable AI Gateway inference table + usage tracking.
* `run_go` gate widget to prevent accidental deployment.
* **Prefer Jobs** for large-batch embedding, perturbation prediction, or dataset-scale workflows.

## Registration and observability

Register to Unity Catalog as `<catalog>.<schema>.scgpt`. Log license, paper DOI, Google Drive source URL, and `scgpt==0.2.4` version as MLflow tags. Enable inference table; classify gene expression data before logging.

## Validation checklist

1. **Checkpoint verify**: `best_model.pt`, `args.json`, `vocab.json` all present in Volume.
2. **Import test**: `from scgpt.model import TransformerModel` succeeds on GPU (flash-attn loads).
3. **Dry-load test**: `TransformerModelWrapper.load_context()` completes; prints embsize and vocab size.
4. **Preprocessing test**: `Preprocessor` runs on sample h5ad data; produces binned AnnData.
5. **Forward pass test**: model produces gene embeddings dict with expected genes.
6. **Signature test**: `infer_signature` with `input_example` and `output_example` + `default_params`.
7. **SDK query test**: `w.serving_endpoints.query(extra_params={...})` returns valid embeddings.
8. **Endpoint teardown**: tear down immediately after validation to stop GPU billing.

## Open questions

* Whether `flash-attn` builds cleanly in the Model Serving container (C++ compilation + CUDA).
* Whether Google Drive download via `gdown` is reliable enough for CI/automation (rate limits).
* Optimal `subset_hvg` and `binning` values for production inference.
* Whether the perturbation task (`03_register_scgpt_perturbation.py`) warrants a separate reference.
* Whether `need_preprocess=False` path is useful for pre-processed inputs.
