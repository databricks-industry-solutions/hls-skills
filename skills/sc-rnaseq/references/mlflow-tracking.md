# MLflow Experiment Tracking for Single-Cell Analysis

> Reference file for the `sc-rnaseq` skill.  
> Load via `readSkillFile("skills/sc-rnaseq/references/mlflow-tracking.md")`
> when Gate G5 = yes (default ON). Load alongside whichever tool file
> (scanpy, rapids, cspray) is being used.

---

## Gate G5 — Default ON

**MLflow tracking is on by default for every analysis.** The agent must
set up the experiment and parent run right after the install cell, before
any data loading. Only skip if the user explicitly says "no tracking" or
"skip MLflow."

Single-cell workflows benefit from MLflow tracking because preprocessing
parameters (filter thresholds, resolution, n_pcs) materially change results.
Tracking lets users compare runs, reproduce analyses, and share artifacts.

---

## Setup (include in every notebook, immediately after install cell)

```python
import mlflow

mlflow.set_registry_uri("databricks-uc")
# Runs log to the notebook-scoped experiment by default (the experiment tied
# to this notebook) — no set_experiment() call needed. Only set one explicitly
# when the user asks to log elsewhere, e.g.:
#   mlflow.set_experiment("/Users/<user_email>/scrna_<experiment_name>")
```

> **Guard against re-run errors:** `mlflow.start_run()` errors if a run
> is already active (common when re-running notebook cells during iterative
> development). Always guard with:
> ```python
> if mlflow.active_run():
>     mlflow.end_run()
> parent_run = mlflow.start_run(run_name="...")
> ```
> Apply this pattern to every `start_run()` call that is NOT inside a
> `with` block (the `with` form auto-closes and is safe to re-run).

> **Experiment location:** default to the notebook-scoped experiment. Only
> set an explicit path when the user wants a shared or specific location — a
> path they choose, e.g. a `/Shared/...` path for team-shared experiments.

---

## Parameter Variables — Single Source of Truth

**Anti-pattern:** Building a separate hardcoded dict for `mlflow.log_params()`
at the end of the notebook. This decouples logged params from executed
params — if the user adjusted a threshold mid-analysis, the logging dict
may not reflect the actual value used.

**Correct pattern:** Define parameter dicts as variables when the user
confirms them (Gate G2), then use the same variables in the pipeline code
and in `mlflow.log_params()`:

```python
# Gate G2: user confirmed these thresholds
qc_params = {
    "pct_counts_mt": 7,        # data-driven: P95=5.5%, MAD=7.1%
    "min_genes": 350,           # data-driven: MAD lower=342
    "max_genes": 3500,          # data-driven: MAD upper=3480
    "min_cells": 3,             # standard
}

analysis_params = {
    "n_top_genes": 2000,
    "n_pcs": 30,
    "cluster_resolution": 1.0,
    "target_sum": 10000,
    "batch_key": "donor_id",    # from Gate G1
    "integration_method": "harmony",
}
```

Then in the QC cell:
```python
adata = adata[adata.obs.pct_counts_mt < qc_params["pct_counts_mt"], :]
adata = adata[adata.obs.n_genes_by_counts < qc_params["max_genes"], :]
sc.pp.filter_cells(adata, min_genes=qc_params["min_genes"])
```

And in the MLflow logging:
```python
mlflow.log_params(qc_params)         # guaranteed same values
mlflow.log_params(analysis_params)
```

> **Rule:** The dict that `mlflow.log_params()` receives MUST be the same
> object used in the pipeline code. If the user adjusts a param, update
> the dict variable, not a separate logging dict.

---

## What to Log

| Category | Examples |
|---|---|
| **Parameters** | `qc_params` dict + `analysis_params` dict (see above) |
| **Metrics** | `n_cells_raw`, `n_cells_filtered`, `n_genes`, `n_clusters`, `n_hvg`, `filter_retention_pct`, `gene_mapping_rate`, `total_time_sec` |
| **Artifacts** | QC scatter plots, UMAP PNGs, marker gene CSVs, processed `.h5ad`, flat `.parquet` |
| **Tags** | `dataset`, `species`, `pipeline` (e.g., `scanpy_standard`), `created_by`, `param_source` |

---

## Full Example

```python
import mlflow
import scanpy as sc
import tempfile, time

tmpdir = tempfile.TemporaryDirectory()
sc.settings.figdir = tmpdir.name        # scanpy saves plots here

t0 = time.time()

# ---- Run the scanpy pipeline ----
# ... QC, filtering, normalize, HVG, PCA, neighbors, UMAP, leiden ...

# ---- Collect metrics ----
metrics = {
    "n_cells": adata.n_obs,
    "n_genes": adata.n_vars,
    "n_clusters": int(adata.obs["leiden"].nunique()),
    "n_hvg": int(adata.var["highly_variable"].sum()),
    "total_time_sec": time.time() - t0,
}

# Use the SAME param dicts from the pipeline (see "Parameter Variables")
# qc_params and analysis_params were defined when user confirmed Gate G2

mlflow.set_registry_uri("databricks-uc")
# notebook-scoped experiment by default — set_experiment() only if directed

with mlflow.start_run(run_name="sample_A_scanpy"):
    mlflow.log_params(qc_params)          # same object used in QC cell
    mlflow.log_params(analysis_params)    # same object used in analysis
    mlflow.log_metrics(metrics)

    # Save plots — scanpy `save=` param writes to figdir
    sc.pl.umap(adata, color="leiden", save="umap_leiden.png")
    sc.pl.rank_genes_groups(adata, n_genes=20, save="markers.png")

    # Save processed h5ad
    adata.write_h5ad(tmpdir.name + "/processed.h5ad")

    # Save flat obs + marker expression as parquet
    adata.obs.to_parquet(tmpdir.name + "/cell_metadata.parquet")

    # Log everything in tmpdir as artifacts
    mlflow.log_artifacts(tmpdir.name)

    mlflow.set_tags({
        "dataset": "sample_A",
        "species": "hsapiens",
        "pipeline": "scanpy_standard",
    })
```

---

## Key Patterns

* **One run per sample or parameter sweep.** For parameter sweeps, use nested
  runs: `mlflow.start_run(nested=True)`.
* **Save plots via scanpy's `save=` kwarg** (writes to `sc.settings.figdir`)
  then batch-log with `mlflow.log_artifacts(figdir)`. Alternatively use
  `return_fig=True` + `fig.savefig()`.
* **h5ad artifact storage:** Default to **not** logging the processed h5ad
  as an MLflow artifact (it can be GBs). The code + logged params are
  sufficient for reproducibility. If the user opts in (`store_h5ad=True`)
  or this is the final accepted run, log it. Always write to a UC Volume
  and log the path as a param regardless.
* **Flat parquet** alongside h5ad makes cell metadata queryable without
  loading the full AnnData. Include cluster, UMAP coords, and top-marker
  expression columns.
* **Subsampling for large datasets:** When logging a flat expression matrix,
  subsample proportionally per cluster (e.g., 10k cells max) to keep artifact
  sizes manageable. Use stratified sampling to preserve cluster proportions.

---

## Agent-Iteration Tracking

When the agent is driving an iterative analysis (profiling → QC → clustering
→ interpreting → re-running with adjusted params), **track each gate
passage as an MLflow child run** so the full decision history is preserved.

**Anti-pattern:** Logging a single run at the end of the notebook with a
hardcoded params dict. This loses all iteration history (which thresholds
were proposed vs accepted, which cell types were corrected, how many
clustering rounds were tried) and decouples logged params from executed
params.

**Correct pattern:** Open a nested child run each time the agent passes
through a gate. The child run logs the param dict variables (same objects
used in the code), metrics from that iteration, and any plots:

| Gate | What the child run logs |
|---|---|
| G2 (QC thresholds confirmed) | `qc_params` dict, `param_source` tag ("data_driven"/"user_adjusted"), n_cells_pre, n_cells_post |
| G1 (batch key confirmed) | `analysis_params` dict (includes `batch_key`), `param_source` tag |
| After clustering | n_clusters, UMAP plot, resolution used |
| G4 (cell types confirmed) | Cell type annotations JSON artifact, n_cell_types_annotated |
| Final | All confirmed params, all plots, h5ad path (artifact optional) |

### Experiment scoping

Scope the experiment to the **notebook** to keep iteration history
self-contained. The agent should only look up runs within the current
analysis — never use MLflow history from a different notebook or session
to drive decisions in this one.

```python
import mlflow

# Derive experiment from the notebook path (auto-scopes to this analysis)
notebook_path = dbutils.notebook.entry_point.getDbutils() \
    .notebook().getContext().notebookPath().get()
mlflow.set_registry_uri("databricks-uc")
experiment = mlflow.set_experiment(notebook_path + "_experiment")
```

### Run hierarchy

| Level | What it tracks | When created |
|---|---|---|
| **Parent run** | Overall analysis: dataset path, file count, tissue, species, profiling metadata | Once, at the start of analysis |
| **Child run: iteration N** | QC params used, n_cells filtered, n_clusters, UMAP plot, marker genes | Each QC→cluster→interpret cycle |
| **Child run: final** | Confirmed params, final cell types, processed h5ad (optional), all plots | When user accepts results |

```python
# Start parent run at beginning of analysis
# Guard: end any active run from a prior cell execution
if mlflow.active_run():
    mlflow.end_run()
parent_run = mlflow.start_run(run_name="analysis_pbmc_lung")
mlflow.set_tags({
    "origin": "agent",
    "dataset": "/Volumes/.../sample_A.h5ad",
    "tissue": "lung",
    "species": "hsapiens",
})

# --- Gate G2: user confirmed QC thresholds ---
# qc_params dict was defined when user confirmed (see "Parameter Variables")
with mlflow.start_run(run_name="gate_g2_qc", nested=True):
    mlflow.log_params(qc_params)          # SAME dict used in pipeline
    mlflow.set_tag("param_source", "data_driven")  # or "user_adjusted"
    mlflow.log_metrics({"n_cells_pre_qc": 67333, "n_cells_post_qc": 64200})
    mlflow.log_artifacts(tmpdir.name)     # QC violin plots

# --- Gate G1: user confirmed batch key ---
with mlflow.start_run(run_name="gate_g1_batch", nested=True):
    mlflow.log_params(analysis_params)    # SAME dict with batch_key, n_pcs, etc.
    mlflow.set_tag("param_source", "user_confirmed")

# --- Post-clustering (may iterate if user adjusts resolution) ---
with mlflow.start_run(run_name="iter_1_clustering", nested=True):
    mlflow.log_params({"cluster_resolution": analysis_params["cluster_resolution"]})
    mlflow.log_metrics({"n_clusters": 15})
    mlflow.log_artifacts(tmpdir.name)     # UMAP plot

# --- User adjusts resolution → update the variable, re-run, log again ---
analysis_params["cluster_resolution"] = 0.5  # user requested change
with mlflow.start_run(run_name="iter_2_resolution_adjusted", nested=True):
    mlflow.log_params({"cluster_resolution": analysis_params["cluster_resolution"]})
    mlflow.set_tag("param_source", "user_adjusted")
    mlflow.log_metrics({"n_clusters": 8})
    mlflow.log_artifacts(tmpdir.name)

# --- Gate G4: user confirmed cell types ---
with mlflow.start_run(run_name="gate_g4_cell_types", nested=True):
    mlflow.log_params({"store_h5ad": False})
    mlflow.log_metrics({"n_clusters": 8, "n_cell_types_annotated": 8})

    # Log cell type annotations as structured artifact
    import json
    annotations = [
        {"cluster": "0", "markers": "CD3D,CD3E,IL7R",
         "llm_suggestion": "T cells (naive)", "confidence": "high",
         "user_decision": "accepted", "final_label": "T cells (naive)"},
        {"cluster": "4", "markers": "COL1A1,DCN,LUM",
         "llm_suggestion": "Fibroblasts", "confidence": "medium",
         "user_decision": "corrected", "final_label": "Myofibroblasts"},
    ]
    with open(tmpdir.name + "/cell_type_annotations.json", "w") as f:
        json.dump(annotations, f, indent=2)
    mlflow.log_artifacts(tmpdir.name)

    mlflow.set_tag("status", "complete")

mlflow.end_run()  # close parent
```

### What to track per iteration

| Category | Fields |
|---|---|
| **Parameters** | All QC/analysis params + `param_source` ("data_driven", "user_provided", "user_adjusted", "default") |
| **Metrics** | `n_cells_pre_qc`, `n_cells_post_qc`, `n_clusters`, `filter_retention_pct` |
| **Artifacts** | QC scatter plots, UMAP PNGs, marker gene CSVs |
| **Cell type annotations** (final run) | JSON with: cluster, markers, llm_suggestion, confidence, user_decision, final_label |

### h5ad artifact storage

Processed h5ad files can be large (GBs). Default behavior:
* **Intermediate iterations:** Do not store h5ad as MLflow artifact.
  Results are reproducible from the code + logged params.
* **Final run:** Store h5ad only if `store_h5ad=True` (user opt-in).
  Alternative: always write to a UC Volume and log the **path** as a param.

### Reading iteration history

The agent can look up prior iterations within the current analysis to
avoid repeating work:

```python
# Find child runs of the current parent
runs = mlflow.search_runs(
    experiment_ids=[experiment.experiment_id],
    filter_string=f"tags.mlflow.parentRunId = '{parent_run.info.run_id}'",
    order_by=["start_time DESC"],
)
# Use to check: what params were already tried, what metrics resulted
```

> **Scope rule:** Only read runs that are children of the current parent
> run. Never use runs from a different parent or a different notebook's
> experiment to drive analysis decisions.

---

## Notebook Markdown Narration

Every code cell that makes a **decision** (choosing thresholds, selecting
a batch key, accepting/rejecting cell types, re-running with adjusted
params) MUST have a preceding markdown cell explaining the rationale.
This is not optional — the notebook is the audit trail.

Keep markdown concise — 2–4 sentences, not paragraphs. A reviewer should
understand the analysis decisions without reading the code.

**What to narrate (with markdown cell before the code cell):**
* **QC thresholds:** "P95 of pct_mt is 5.5%, MAD upper bound is 7.1%.
  Filtering at pct_mt < 7%. User confirmed."
* **Batch key selection:** "Profiling shows `donor_id` has no overlap
  between files — using as batch key for Harmony. User confirmed."
* **Cell type annotations:** "⚠️ LLM-suggested annotations based on top
  markers. Expert review required. User corrected clusters 4 and 5."
* **Parameter adjustments:** "Lowering resolution from 1.0 to 0.5 per
  user request — previous run had 25 clusters, too granular."
* **Integration warnings:** "These samples are from different tissues.
  User confirmed integration is intentional."

**Do NOT narrate** routine operations ("Now we normalize", "This cell
runs PCA"). Focus on **decisions and their justification**.

**Anti-pattern:** A notebook with only a title markdown cell and 10 code
cells. Every notebook should have markdown explaining at minimum: the QC
threshold rationale, the batch key choice, and the cell type annotations.
