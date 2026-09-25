# GPU-Accelerated Analysis (rapids-singlecell)

> Reference file for the `sc-rnaseq` skill.  
> Load via `readSkillFile("skills/sc-rnaseq/references/rapids-singlecell.md")`
> when the user has a single large file (> 500k cells) and accepts GPU compute.

---

For **single large files** where scanpy is too slow (e.g., > 500k cells),
offer `rapids-singlecell` as an alternative.

> **⚠️ `sc.pp.neighbors` has NO GPU equivalent.**  
> This is the #1 mistake in GPU pipelines. You MUST use `sc.pp.neighbors`
> (scanpy), not `rsc`. Using `rsc` for neighbors will fail silently or
> error. See the pipeline example below.

### Supported GPU compute

| Option | Notes |
|---|---|
| **Serverless GPU (A10)** | Works with RAPIDS 25.10. `cupy-cuda12x` is pre-installed in the AI base environment — shorter install. Preferred for single large files. |
| **Classic GPU cluster** (e.g., `g5.4xlarge`) | Full control over instance type and VRAM. Required if Serverless GPU is not available or VRAM > 24 GB needed. |

> **`executeCode` does NOT share the notebook's GPU context on Serverless.**
> All GPU code must run in notebook cells, not via the agent's `executeCode`
> tool. The agent should write cells and let the user run them (or use
> `runAsset`), never attempt GPU work in `executeCode`.

### Agent action — ASK the user:

> "Your file is large. Would you like to use rapids-singlecell for
> GPU-accelerated analysis? This works on Serverless GPU (A10) or a
> classic GPU cluster."

---

## Install

rapids-singlecell requires the RAPIDS CUDA stack. The install differs
between Serverless GPU and classic clusters.

### Serverless GPU (shorter — cupy-cuda12x is pre-installed)

```python
%pip install --extra-index-url=https://pypi.nvidia.com \
  cudf-cu12==25.10.00 dask-cudf-cu12==25.10.00 cuml-cu12==25.10.00 \
  cugraph-cu12==25.10.00 nx-cugraph-cu12==25.10.00 cucim-cu12==25.10.00 \
  pylibraft-cu12==25.10.00 raft-dask-cu12==25.10.00 cuvs-cu12==25.10.00
%pip install rapids-singlecell==0.14.1 scikit-learn==1.5.2 numpy==1.26.4
%restart_python
```

### Classic GPU cluster

```python
%pip install --extra-index-url=https://pypi.nvidia.com \
  cudf-cu12==25.10.00 dask-cudf-cu12==25.10.00 cuml-cu12==25.10.00 \
  cugraph-cu12==25.10.00 nx-cugraph-cu12==25.10.00 cucim-cu12==25.10.00 \
  pylibraft-cu12==25.10.00 raft-dask-cu12==25.10.00 cuvs-cu12==25.10.00
%pip install cupy-cuda12x==13.6.0
%pip install rapids-singlecell==0.14.1 scikit-learn==1.5.2 numpy==1.26.4
%restart_python
```

> **Version note:** Pin RAPIDS packages to the same release train
> (e.g., `25.10.00`). Mixing versions across RAPIDS components causes
> import errors. Check the [RAPIDS release page](https://rapids.ai/)
> for the latest compatible set.

> **⚠️ `%restart_python` wipes ALL session state.** Every variable,
> import, and loaded dataset from prior cells is gone. Structure the
> notebook so that cells after install (MLflow setup, RMM init, data
> load) are **independently re-runnable** — each cell must import what
> it needs. After a restart, re-run cells 2+ in order before continuing.

---

## RMM (RAPIDS Memory Manager) Setup

Initialize the GPU memory allocator **before any GPU work**. This prevents
fragmentation and CUDA OOM on large datasets:

```python
import cupy as cp
import rmm
from rmm.allocators.cupy import rmm_cupy_allocator

rmm.reinitialize(
    managed_memory=False,   # Set True to allow oversubscription (slower)
    pool_allocator=False,   # Default; True pre-allocates a memory pool
    devices=0,              # GPU device ID
)
cp.cuda.set_allocator(rmm_cupy_allocator)
```

> **When to use `managed_memory=True`:** If the dataset is larger than GPU
> VRAM, managed memory lets CUDA spill to host RAM (unified memory). This
> avoids OOM but is significantly slower. Prefer filtering the data down
> first (see filter order below).

---

## Filter Order — GPU-Specific

> **Parameter confirmation applies here too.** Follow the same Round 1 / Round 2
> protocol from the scanpy workflow before running the GPU pipeline. GPU defaults
> differ from scanpy (e.g., `n_top_genes=500`, `resolution=0.2`) — present
> these to the user so they're aware of the differences.

**Critical difference from the scanpy workflow:** filter aggressively on
`pct_counts_mt` and `n_genes_by_counts` **before** calling
`rsc.pp.filter_genes` / `rsc.pp.filter_cells`. This reduces the matrix
size on GPU early and prevents CUDA OOM errors.

> **Notebook cell structure:** Each code block below should be a separate
> notebook cell with its own imports. After `%restart_python`, all prior
> state is lost. Do not rely on imports from earlier cells surviving.

> **Minimize GPU/CPU transfers.** Do all CPU-side profiling and checks
> (Ensembl swap, pre-computed QC, plotting QC violins) BEFORE the single
> `anndata_to_GPU` call. Transfer back to CPU once after UMAP for plotting
> and DE. Two transfers total — not four.

```python
# Cell: Load and prepare data (CPU)
import rapids_singlecell as rsc
import scanpy as sc
import numpy as np

adata = sc.read_h5ad("/Volumes/...")
adata.obs_names_make_unique()
if adata.raw is not None:
    adata = adata.raw.to_adata()

# --- Check gene naming convention BEFORE GPU transfer ---
# Many CELLxGENE / Allen Brain Atlas h5ad files use Ensembl IDs as var_names
# with symbols in var["feature_name"]. flag_gene_family will silently produce
# all-zero QC columns (pct_counts_mt = 0) if var_names are ENSG* IDs.
if adata.var_names[0].startswith("ENSG"):
    symbol_col = None
    for col in ["feature_name", "gene_symbols", "gene_name", "symbol"]:
        if col in adata.var.columns:
            symbol_col = col
            break
    if symbol_col:
        adata.var["ensembl_id"] = adata.var_names.copy()
        adata.var_names = adata.var[symbol_col].astype(str).values
        adata.var_names_make_unique()
        print(f"Swapped var_names from Ensembl IDs to {symbol_col}")
    else:
        print("WARNING: var_names are Ensembl IDs but no symbol column found. "
              "MT/ribo QC will be all zeros. Consider providing a gene mapping.")

# --- Check for pre-computed QC columns ---
# Published h5ad files (CELLxGENE, HCA) often ship with QC already computed.
precomputed_qc = [col for col in adata.obs.columns
                  if col in ["pct_counts_mt", "pct_mt", "n_genes", "total_counts",
                             "n_genes_by_counts", "Fraction mitochrondrial UMIs",
                             "Genes detected", "Number of UMIs"]]
if precomputed_qc:
    print(f"Pre-computed QC columns found: {precomputed_qc}")
    print("Will cross-validate against freshly computed values.")

# Transfer to GPU
rsc.get.anndata_to_GPU(adata)

# --- QC annotation (GPU-accelerated) ---
# Use "MT-" (with hyphen) for human mitochondrial genes; "mt-" for mouse
rsc.pp.flag_gene_family(adata, gene_family_name="mt", gene_family_prefix="MT-")
# Flag BOTH ribosomal subunits: RPS (small) and RPL (large)
rsc.pp.flag_gene_family(adata, gene_family_name="ribo_s", gene_family_prefix="RPS")
rsc.pp.flag_gene_family(adata, gene_family_name="ribo_l", gene_family_prefix="RPL")
adata.var["ribo"] = adata.var["ribo_s"] | adata.var["ribo_l"]
rsc.pp.calculate_qc_metrics(adata, qc_vars=["mt", "ribo"])

# --- Filter aggressively FIRST to prevent CUDA OOM ---
adata = adata[adata.obs["n_genes_by_counts"] < 2500]
adata = adata[adata.obs["pct_counts_mt"] < 5]
rsc.pp.filter_genes(adata, min_cells=3)
rsc.pp.filter_cells(adata, min_genes=200)

# --- Capture post-QC gene/cell counts BEFORE HVG subsetting ---
# n_vars will drop to n_top_genes (500) after filter_highly_variable.
# Capture the real post-QC count here for MLflow logging.
n_cells_post_qc = adata.n_obs
n_genes_post_qc = adata.n_vars
print(f"Post-QC: {n_cells_post_qc:,} cells, {n_genes_post_qc:,} genes")

# --- Normalize → log → HVGs ---
rsc.pp.normalize_total(adata, target_sum=1e4)
rsc.pp.log1p(adata)
rsc.pp.highly_variable_genes(adata, n_top_genes=500, flavor="cell_ranger")
rsc.pp.filter_highly_variable(adata)   # subset to HVGs only

# --- Scale → PCA → neighbors → Leiden → UMAP ---
rsc.pp.scale(adata, max_value=10)
rsc.tl.pca(adata, n_comps=50)
# ⚠️ IMPORTANT: Use sc.pp.neighbors (scanpy), NOT rsc — there is no GPU equivalent.
# Using rsc for neighbors will fail silently or error. This is the #1 mistake.
sc.pp.neighbors(adata)

rsc.tl.leiden(adata, resolution=0.2)    # GPU-accelerated Leiden
rsc.tl.umap(adata)

# --- Transfer to CPU for plotting and DE ---
rsc.get.anndata_to_CPU(adata)
sc.pl.umap(adata, color=["leiden"])

# --- Marker genes (CPU only — no rsc equivalent) ---
sc.tl.rank_genes_groups(adata, groupby="leiden", method="wilcoxon")
```

### Existing annotations & stimulation experiments

**Before running fresh annotation (Gate G4), check `.obs` for existing
cell type columns** (`cell_type`, `celltype`, `cell_ontology_class`).
Many published datasets ship with expert annotations — use them as the
primary source and compare against new clustering rather than re-deriving
from scratch.

**Stimulation / perturbation experiments:** If the dataset has experimental
conditions (stimulated/unstimulated, treated/control, timepoints), the top
DE markers per cluster may reflect the **condition** rather than **cell
identity**. Signs: top markers are interferon-stimulated genes (IFIT3,
OAS1, IFI44L), defensins (DEFA1), or stress response genes across
multiple clusters.

In this case:
1. **Use pre-existing `cell_type` annotations** from `.obs` if available.
2. **Run DE within condition groups** — subset to unstimulated cells first,
   annotate, then map annotations back.
3. **Regress out the stimulation effect** before clustering:
   `sc.pp.regress_out(adata, ["condition"])` (CPU-only, before GPU transfer).
4. Flag to user: "Top markers appear condition-driven, not cell-type-driven.
   Your h5ad has a `cell_type` column — shall I use that instead?"

---

## Which APIs Are GPU vs CPU

Not all operations have GPU-accelerated equivalents. The table below shows
which to call via `rsc` vs `sc`:

| Operation | GPU (`rsc`) | CPU (`sc`) | Notes |
|---|---|---|---|
| `flag_gene_family` | `rsc.pp.flag_gene_family` | manual `.str.startswith()` | rsc convenience function |
| `calculate_qc_metrics` | `rsc.pp.calculate_qc_metrics` | `sc.pp.calculate_qc_metrics` | |
| `filter_cells` / `filter_genes` | `rsc.pp.filter_*` | `sc.pp.filter_*` | |
| `normalize_total` / `log1p` | `rsc.pp.*` | `sc.pp.*` | |
| `highly_variable_genes` | `rsc.pp.highly_variable_genes` | `sc.pp.highly_variable_genes` | Use `flavor="cell_ranger"` on GPU |
| `filter_highly_variable` | `rsc.pp.filter_highly_variable` | manual subsetting | Subsets adata to HVGs |
| `scale` | `rsc.pp.scale` | `sc.pp.scale` | |
| `pca` | `rsc.tl.pca` | `sc.tl.pca` | |
| `neighbors` | — | `sc.pp.neighbors` | **Use scanpy**, not rsc |
| `leiden` | `rsc.tl.leiden` | `sc.tl.leiden` | GPU Leiden via cugraph |
| `umap` | `rsc.tl.umap` | `sc.tl.umap` | |
| `rank_genes_groups` | — | `sc.tl.rank_genes_groups` | **CPU only** — transfer first |
| `diffmap` / `dpt` | — | `sc.tl.diffmap` / `sc.tl.dpt` | **CPU only** — transfer first |
| All plotting | — | `sc.pl.*` | **Always CPU** |

> **Transfer point:** Call `rsc.get.anndata_to_CPU(adata)` after UMAP but
> before marker gene analysis, pseudotime, and plotting. These operations
> have no GPU equivalents and will error on GPU-backed arrays.

---

## GPU-Specific Defaults

| Parameter | scanpy default | rapids-singlecell recommendation | Reason |
|---|---|---|---|
| `n_top_genes` | 2000 | **500** | Fewer HVGs reduces GPU memory; often sufficient |
| `flavor` (HVG) | `seurat` | **`cell_ranger`** | Better suited to GPU workflow |
| `max_value` (scale) | `None` | **10** | Clip outliers before PCA to stabilize GPU numerics |
| `resolution` | 1.0 | **0.2** | Start lower; GPU Leiden is fast to re-run |

---

## Common Pitfalls (GPU-specific)

| Pitfall | Remedy |
|---|---|
| CUDA OOM during pipeline | Filter `pct_counts_mt` and `n_genes_by_counts` BEFORE `filter_cells`/`filter_genes`. Lower `n_top_genes` (500 vs 2000). Try `managed_memory=True` in RMM init as last resort. |
| RAPIDS import errors / version mismatch | All `cu*` packages must be same release train (e.g., `25.10.00`). Install from `pypi.nvidia.com`. |
| `rank_genes_groups` fails on GPU arrays | Must call `rsc.get.anndata_to_CPU(adata)` before DE analysis — no GPU equivalent. |
| rapids-singlecell fails on CPU cluster | Requires NVIDIA GPU + RAPIDS-compatible runtime. |
| `pct_counts_mt` / `pct_counts_ribo` all zeros | var_names are Ensembl IDs (ENSG*), not gene symbols. Swap to the symbol column (`feature_name`, `gene_symbols`) before `flag_gene_family`. See Ensembl check in pipeline example. |
| `sc.pp.neighbors` called via `rsc` or omitted | **No GPU equivalent exists.** Must use `sc.pp.neighbors` (scanpy). This is the most common GPU pipeline error — will fail silently or error. |
| 3-MAD threshold produces [0, 0.1] for pct_mt | Common in brain tissue / nuclear preps where median pct_mt ≈ 0. Fall back to P95 or a biological cutoff (e.g., 5%). Flag to user at Gate G2. |
| `gene_family_prefix="MT"` missing hyphen | Human mito genes are `MT-ND1`, `MT-CO1`, etc. Use `"MT-"` (with hyphen). Mouse uses `"mt-"`. Without hyphen, may match non-mito genes. |
| `NameError` after `%restart_python` | All variables wiped. Re-run cells 2+ in order. Each cell must import what it needs. |
| `n_genes` metric = 500 (HVG count, not post-QC) | Capture `adata.n_vars` BEFORE `filter_highly_variable()`, not after. |
| Top markers are ISGs/defensins across all clusters | Stimulation experiment: markers reflect condition, not cell identity. Use existing `.obs["cell_type"]` or regress out condition. |
| GPU code fails in `executeCode` on Serverless | `executeCode` doesn't share the notebook's GPU context. Write code into notebook cells instead. |
| Redundant GPU/CPU transfers (4 instead of 2) | Do all CPU profiling before the single `anndata_to_GPU`. Transfer to CPU once after UMAP. Two transfers total. |
