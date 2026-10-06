# Scimilarity model reference

## Identity

* Model family: Scimilarity (single-cell representation + kNN cell-type annotation)
* Upstream code: https://github.com/Genentech/scimilarity
* Genesis Workbench: https://github.com/databricks-industry-solutions/genesis-workbench (`modules/single_cell/scimilarity`)
* Zenodo weights: https://zenodo.org/records/10685499/files/model_v1.1.tar.gz?download=1
* HuggingFace expanded: https://huggingface.co/sail-mskcc/scimilarity_expanded_model
* Paper: https://doi.org/10.1038/s41467-023-44275-w
* Reviewed date: 2026-09-24
* Code license: BSD-3-Clause (Zenodo v1.1), Apache-2.0 (HF expanded)
* Weight terms: CC-BY-4.0 (Zenodo), Apache-2.0 (HF expanded — verify before distribution)
* Current version: v1.1 (Zenodo) / expanded (SAIL-MSKCC)

## What this model does

Scimilarity is a single-cell RNA-seq encoder trained on a large reference atlas. Given a set of gene expression values, it produces a cell embedding and performs kNN cell-type annotation against its built-in reference. The model uses HGNC gene symbols (not Ensembl IDs), aligns query genes to its internal gene ordering, log-normalizes counts (TP10K + log1p), and produces embeddings via a neural encoder. The kNN layer returns predicted cell types, neighbor distances, and confidence statistics.

This reference covers **online inference** (bounded per-cell queries to a Model Serving endpoint); for large-batch annotation of full AnnData objects use a Job with `scanpy`.

## Available model sources

| | Zenodo v1.1 (Genentech) | HF expanded (SAIL @ MSKCC) |
|---|---|---|
| Source | [Zenodo 10685499](https://zenodo.org/records/10685499) | [sail-mskcc/scimilarity_expanded_model](https://huggingface.co/sail-mskcc/scimilarity_expanded_model) |
| Training cells | 7.9 M | **39.5 M** (5×) |
| Search index cells | 23.4 M | **45.5 M** (2×) |
| Distribution | Single tarball | Individual files (HF LFS) |
| Core model size | ~250 MB (in 1.3 GB tarball) | **~1.0 GB** |
| kNN indexes | Included in tarball | **~159 GB** (optional) |
| Download method | `curl` with retry + resume | `huggingface_hub.snapshot_download` |
| License | CC-BY-4.0 (check repo) | Apache-2.0 |
| API compatibility | `scimilarity` v0.4+ | Same — just change `model_path` |

**Both models use the same `scimilarity` API.** `CellEmbedding(model_path=...)` / `CellAnnotation(model_path=...)` works unchanged. For embedding-only (no cell search), both need <1 GB of core files.

Use the `model_source` widget to select `zenodo` or `huggingface` at runtime.

## Inputs and outputs

### Serving contract

The PyFunc wrapper accepts two JSON-string columns per row:

| Column | Type | Description |
|--------|------|-------------|
| `genes` | `str` — JSON array | HGNC gene symbols (e.g. `["MALAT1", "TMSB4X", "B2M"]`). Must match the model's gene vocabulary. |
| `expression` | `str` — JSON array | Raw counts aligned to `genes`. Same length as genes array. |

Note: gene names are **HGNC symbols** (e.g. `MALAT1`, `B2M`), NOT Ensembl IDs. The model's `gene_order` attribute contains the canonical gene list.

### Output

| Column | Type | Description |
|--------|------|-------------|
| `predicted_celltype` | `str` | kNN-predicted cell type label |
| `embedding` | `str` — JSON array of floats | Cell embedding vector |
| `nn_dist_mean` | `float` | Mean kNN distance (confidence proxy) |

### Input example

```json
{
  "genes": "[\"MALAT1\", \"TMSB4X\", \"B2M\", \"RPL13\", \"RPL41\"]",
  "expression": "[12.0, 8.0, 5.0, 3.0, 2.0]"
}
```

```python
import json
import pandas as pd

# Use real HGNC gene symbols from the PBMC dataset
input_example = pd.DataFrame([{
    "genes": json.dumps(["MALAT1", "TMSB4X", "B2M", "RPL13", "RPL41"]),
    "expression": json.dumps([12.0, 8.0, 5.0, 3.0, 2.0]),
}])
```

**Critical**: use real HGNC symbols known to the model (e.g. from the PBMC 3k dataset). The model's `ca.gene_order` contains the full gene vocabulary.

### HTTP payload (Databricks SDK)

```python
import json
response = w.serving_endpoints.query(
    name=ENDPOINT_NAME,
    dataframe_records=[{
        "genes": json.dumps(["MALAT1", "TMSB4X", "B2M", "RPL13", "RPL41"]),
        "expression": json.dumps([12.0, 8.0, 5.0, 3.0, 2.0]),
    }],
)
```

Note: Scimilarity serving does not use `extra_params` — no tunable inference controls.

## Artifacts and runtime

### Model directory (`model_dir`)

Path: `<VOLUME_PATH>/scimilarity/`

Downloaded from Zenodo as a `.tar.gz` that extracts to `model_v1.1/`.

| File | Purpose |
|------|---------|
| `config.json` | Model architecture config |
| `*.ckpt` or `*.pt` | Model weights (encoder + kNN index) |
| `gene_order.tsv` / embedded | Canonical gene list for alignment |
| `annotation_*.pkl` | kNN index and reference labels |

### Download (Zenodo v1.1)

The Zenodo model is a single tarball. Use `curl` with retry + resume (Zenodo can be slow, ~30–60 min):

```python
def curl_download(url, destination, max_attempts=10, backoff_s=30):
    """Download via curl with retry + resume."""
    for attempt in range(1, max_attempts + 1):
        rc = subprocess.run(
            ["curl", "-fSL", "-C", "-", "--connect-timeout", "60",
             "--max-time", "3600", "--progress-bar", "-o", destination, url]
        ).returncode
        if rc == 0:
            return
        time.sleep(backoff_s)
    raise RuntimeError(f"Download failed after {max_attempts} attempts")

curl_download(ZENODO_URL, tarball)
subprocess.run(["tar", "--no-same-owner", "-xzf", tarball, "-C", MODEL_DIR], check=True)
```

### Download (HuggingFace expanded)

```python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="sail-mskcc/scimilarity_expanded_model",
    local_dir=dest,
    allow_patterns=["*.ckpt", "*.tsv", "*.json", "*.csv",
                    "annotation/labelled_kNN.bin",
                    "annotation/reference_labels.tsv"],  # core only, skip kNN indexes
    resume_download=True,
)
```

Set `allow_patterns=None` to download everything including kNN indexes (~159 GB).

### Parallel download

Model + sample data can be downloaded in parallel using `ThreadPoolExecutor`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

model_fn = setup_zenodo if MODEL_SOURCE == "zenodo" else setup_huggingface
with ThreadPoolExecutor(max_workers=2) as executor:
    futures = {
        executor.submit(model_fn): "model",
        executor.submit(setup_sample_data): "sample_data",
    }
    for future in as_completed(futures):
        future.result()  # raises on failure
```

### Compute requirements

| Task | Compute |
|------|---------|
| Download from Zenodo | CPU (Serverless or classic). Download to `/tmp`, extract, copy to Volume. |
| Register and deploy | CPU — **no GPU required**. Scimilarity runs on CPU. |
| Model Serving endpoint | `Small` workload size, CPU. No GPU tier needed. `scale_to_zero_enabled=True`. |

### Dependencies

Registration deps (exact pins from GT notebook for reproducibility):

```
%pip install -q scimilarity==0.4.0 scanpy==1.11.2 numcodecs==0.13.1 \
    numpy==1.26.4 pandas==1.5.3 mlflow==2.22.0 cloudpickle==2.0.0 \
    typing_extensions==4.15.0 tbb==2021.13.0 setuptools<82
```

For serving `pip_requirements`:

```python
pip_requirements = [
    "scimilarity==0.4.0",
    "torch>=2.0.0",
    "pytorch-lightning>=2.0.0",
    "scanpy==1.11.2",
    "numpy==1.26.4",
    "pandas==1.5.3",
    "mlflow==2.22.0",
    "cloudpickle==2.0.0",
]
```

Note: `scimilarity` uses `hnswlib` + `tiledb-vector-search` (NOT faiss) for kNN.

## Notebook architecture

Use **two separate notebooks**:

1. **Download notebook (CPU)** — `curl` from Zenodo OR `snapshot_download` from HF. Widget selects source. Parallel download (model + sample data via `ThreadPoolExecutor`). No GPU, no `scimilarity` import needed. Provenance manifest.
2. **Register and deploy notebook (CPU)** — installs `scimilarity`, loads model from Volume, registers **three separate PyFunc models** to UC, optionally creates VS index, deploys CPU Model Serving endpoints.

Separating these avoids re-downloading on failed registration attempts. Use `run_go` widget gate for expensive operations.

### Three PyFunc models (from GWB module)

| Model | GWB Source | Purpose | CPU/GPU |
|-------|-----------|---------|--------|
| **GeneOrder** | `02_register_GeneOrder.py` | Static gene-order lookup (~28K genes) | CPU |
| **GetEmbedding** | `03_register_GetEmbedding.py` | Neural net cell embeddings (128-d) | CPU |
| **SearchNearest** | `04_register_SearchNearest.py` | kNN cell search (standalone ref) | CPU |

**Note**: `04_register_SearchNearest.py` is **DEPRECATED** in the GWB DAG. Use Phase 1b (AI Search) instead for production.

### Phase 1b — AI Search alternative (optional)

Replaces SearchNearest for production. Creates:
1. `scimilarity_cells` Delta table (extracted from model reference labels)
2. Databricks AI Search index (`scimilarity_cell_index`) with Delta Sync

Source table resolution uses a 2-tier fallback:
1. GWB production table (`genesis_workbench.scimilarity_cells`) if GWB deployed
2. Extract from model artifacts (`skills.scimilarity_cells`) via GWB 06b pattern

SCimilarity always produces **128-d** embeddings (fixed by architecture, not configurable).

```python
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    VectorIndexType,
    PipelineType,
)

w.vector_search_indexes.create_index(
    name=VS_INDEX,
    endpoint_name=VS_ENDPOINT,
    primary_key="cell_id",
    index_type=VectorIndexType.DELTA_SYNC,
    delta_sync_vector_index_spec=DeltaSyncVectorIndexSpecRequest(
        source_table=source_table,
        embedding_vector_columns=[{"name": "embedding", "dimension": 128}],
        pipeline_type=PipelineType.TRIGGERED,
    ),
)
```

## Wrapper boundary

### Key imports and classes (from `scimilarity` package)

```python
from scimilarity.cell_annotation import CellAnnotation
from scimilarity.utils import align_dataset, lognorm_counts
```

### `load_context` pattern

```python
def load_context(self, context):
    from scimilarity.cell_annotation import CellAnnotation
    model_dir = context.artifacts["model_dir"]
    self.ca = CellAnnotation(model_path=model_dir, use_gpu=False)
```

### `predict` pattern

```python
def predict(self, context, model_input, params=None):
    import json, numpy as np, pandas as pd, anndata as ad
    from scipy.sparse import csr_matrix
    from scimilarity.utils import align_dataset, lognorm_counts

    genes_list = [json.loads(g) if isinstance(g, str) else list(g)
                  for g in model_input["genes"]]
    expr_list  = [json.loads(e) if isinstance(e, str) else list(e)
                  for e in model_input["expression"]]

    n_cells = len(expr_list)
    gene_names = genes_list[0]  # batch shares the same gene set

    X = np.zeros((n_cells, len(gene_names)), dtype=np.float32)
    for i, expr in enumerate(expr_list):
        X[i, :len(expr)] = expr

    adata = ad.AnnData(X=csr_matrix(X), var=pd.DataFrame(index=gene_names))
    adata = align_dataset(adata, self.ca.gene_order)
    adata = lognorm_counts(adata)

    embeddings = self.ca.get_embeddings(adata.X)
    preds, nn_idxs, nn_dists, nn_stats = self.ca.get_predictions_knn(
        embeddings, weighting=True
    )

    results = []
    for i in range(n_cells):
        results.append({
            "predicted_celltype": str(preds.values[i]),
            "embedding": json.dumps(embeddings[i].tolist()),
            "nn_dist_mean": float(np.mean(nn_dists[i] if nn_dists.ndim > 1 else nn_dists)),
        })
    return pd.DataFrame(results)
```

### Preprocessing pipeline (from upstream repo)

Scimilarity requires two preprocessing steps before inference:
1. **Gene alignment** — `align_dataset(adata, ca.gene_order)` reorders and pads query genes to match the model's internal gene ordering
2. **Log-normalization** — `lognorm_counts(adata)` applies TP10K + log1p normalization matching the model's training

Both functions are from `scimilarity.utils`. Do NOT skip these or substitute custom normalization.

## Deployment recommendation

**Model Serving** on CPU is appropriate for bounded per-cell annotation requests:

* `workload_size="Small"` with `scale_to_zero_enabled=True`.
* No GPU needed — Scimilarity runs entirely on CPU.
* For full AnnData batch annotation (thousands+ cells), prefer a Job that uses `scanpy` directly.

## Registration and observability

Register to Unity Catalog as `<catalog>.<schema>.scimilarity`. Log BSD-3 license, Zenodo URL, paper DOI, and version as MLflow tags.

## Validation checklist

1. **Gene vocabulary test**: `ca.gene_order` contains known HGNC symbols (e.g. `MALAT1` is present).
2. **Import test**: `from scimilarity.cell_annotation import CellAnnotation` succeeds in serving container.
3. **Dry-load test**: `CellAnnotation(model_path=..., use_gpu=False)` loads without error.
4. **PBMC test**: PBMC 3k cells produce reasonable cell types (T cells, B cells, monocytes).
5. **Single-cell payload test**: one cell with 5 known genes returns `predicted_celltype`, `embedding`, `nn_dist_mean`.
6. **Unknown-gene test**: genes not in `gene_order` are handled gracefully (alignment drops them).
7. **Empty expression test**: all-zero expression returns an embedding without raising.
8. **SDK query test**: `w.serving_endpoints.query(dataframe_records=[...])` succeeds.
9. **Embedding sanity**: embedding vector has consistent dimension (128-d) across cells.
10. **VS self-retrieval test** (Phase 1b): query VS index with a known embedding; verify top-1 result is the query cell itself.
11. **VS monotonic distances** (Phase 1b): verify kNN distances are monotonically non-increasing.
12. **HF expanded model test**: if using HF source, verify `gene_order.tsv` sentinel present and API compatibility with Zenodo model.

## Open questions

* Whether `hnswlib` builds cleanly in the Model Serving container (C++ compilation required).
* Optimal batch size for concurrent kNN queries.
* Whether the reference atlas in the model tarball contains any proprietary or sensitive cell data.
* Index update strategy when Genentech releases a new Scimilarity version.
* Whether HF expanded model (~39.5M cells) produces significantly different embeddings from Zenodo v1.1 (7.9M cells) for the same input.
* Whether kNN indexes (~159 GB) are needed for embedding-only use cases.
