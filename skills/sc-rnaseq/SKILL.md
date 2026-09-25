---
name: sc-rnaseq
description: >
  Guidance for analyzing single-cell RNA-seq data from h5ad files stored on
  Unity Catalog Volumes. Load this skill when the user mentions h5ad, AnnData,
  scanpy, single-cell, scRNA-seq, rapids-singlecell, cspray, 10x Genomics,
  cell-type annotation, batch correction, harmony, UMAP, leiden clustering,
  MLflow experiment tracking for single-cell, marker genes, pseudotime,
  or asks to build tables/dashboards from single-cell experiments.
---

# Single-Cell Analysis on Databricks

## Scope

This skill is a **router**. It contains decision logic, compute rules, and
mandatory gates. Detailed tool-specific workflows live in reference files
loaded on demand (see "Reference Files" below).

Covers: reading `.h5ad` (AnnData) files from UC Volumes, exploratory
analysis with **scanpy**, large-scale tabular extraction with **cspray**,
GPU-accelerated workflows with **rapids-singlecell**, and **MLflow
experiment tracking** for reproducible single-cell pipelines.

---

## Reference Files — Load After Routing

After the decision flowchart determines the tool path, load the matching
reference file(s) with `readSkillFile`. Do NOT load all files up front.

| File | Load when… | Path |
|---|---|---|
| **scanpy-workflow.md** | Interactive exploration, single or multi-sample, QC, clustering, harmony, cell type annotation | `references/scanpy-workflow.md` |
| **rapids-singlecell.md** | Single large file (> 500k cells) + user accepts GPU cluster | `references/rapids-singlecell.md` |
| **cspray-tables.md** | Building Delta tables, dashboards, SQL-queryable data, or Delta write after analysis | `references/cspray-tables.md` |
| **mlflow-tracking.md** | Gate G5 = yes (default ON). Load alongside whichever tool file is active. | `references/mlflow-tracking.md` |

---

## Mandatory Decision Gates

**The agent MUST stop and wait for user input at these points.** Do not
generate code past a gate until the user has responded. Even if the user
said "write code for this" or "analyze this" — these gates still apply.
Generating a complete end-to-end notebook without pausing is a skill
violation.

| # | Gate | When | What to present | Reference |
|---|---|---|---|---|
| G1 | **Batch key selection** | Multi-sample, after profiling | Per-sample metadata overlap table + recommended key(s) | `references/scanpy-workflow.md` |
| G2 | **QC thresholds** | After computing QC metrics | Data-driven thresholds (MAD/percentile) vs defaults, per-sample QC summary | `references/scanpy-workflow.md` |
| G3 | **Uniform vs per-sample QC** | Multi-sample, if QC profiles differ | Per-sample QC distribution table + recommendation | `references/scanpy-workflow.md` |
| G4 | **Cell type annotation** | After marker gene analysis | LLM-suggested cell types with confidence, requiring expert review | `references/scanpy-workflow.md` |
| G5 | **MLflow tracking** | Start of analysis (after install cell) | Set up notebook-scoped experiment + parent run. Default ON — only skip if user explicitly declines. | `references/mlflow-tracking.md` |

**Critical rule: If you computed QC distributions, you MUST use them to
set thresholds.** Never compute per-sample P95/MAD values and then ignore
them in favor of static defaults (e.g., computing P95 pct_mt = 5.5% and
then filtering at 20% is a skill violation).

**Markdown on decision cells:** Every code cell that implements a gate
decision (QC thresholds, batch key, cell type annotations, MLflow setup)
MUST have a preceding markdown cell documenting the rationale — what data
drove the choice, what the user confirmed, and any adjustments. A notebook
with only a title markdown cell and 10+ code cells is a skill violation.

**Single source of truth for parameters:** When the user confirms
thresholds at Gate G2, store them in a Python dict variable (e.g.,
`qc_params`, `analysis_params`) and reference that variable in BOTH the
pipeline code AND `mlflow.log_params()`. Never hardcode a separate dict
for logging — the logged params and executed params must be the same
object. See `references/mlflow-tracking.md` "Parameter Variables" for the pattern.

**Log each gate, not just the final state:** Every time the agent passes
through a gate (G2: user confirms thresholds, G1: user picks batch key,
G4: user confirms cell types), open a nested MLflow child run and log
the decision. Do not defer all logging to a single run at the end of the
notebook — that loses the iteration history. See `references/mlflow-tracking.md` "Agent-Iteration
Tracking" for the run hierarchy.

**Biologically incompatible samples:** If profiling reveals the files are
from fundamentally different tissues, organisms, or assay types, **flag
this to the user before proceeding.** Harmony cannot meaningfully correct
across unrelated biology — it will merge unrelated cell populations. The
agent should say:
> "These samples appear to be from different tissues/studies (e.g., lung
> T cells vs skin fibroblasts). Batch correction may merge unrelated
> cell types. Are you sure you want to integrate, or would separate
> per-sample analysis be more appropriate?"

---

## 1. Input Data Conventions

* h5ad files live on UC Volumes.  
  Typical path: `/Volumes/<catalog>/<schema>/<volume>/<experiment>/<sample>.h5ad`
* Always confirm the path(s) with the user before reading. Use
  `dbutils.fs.ls()` or `readAssetById` (assetType `directory`) to verify.
* If a user gives a local or DBFS path, remind them to stage the file on a
  UC Volume first.

---

## 2. Scoping Questions — Ask Before Diving In

Unless the user's goal is already obvious, **ask these questions up front**
before choosing a tool path. Getting scope wrong wastes significant time
(wrong compute, wrong library, wrong output format).

1. **"What is the end goal — interactive exploration, or building queryable
   tables / dashboards?"**
   * Exploration → scanpy or rapids-singlecell (see reference files).
   * Tables / dashboards → almost always cspray (`references/cspray-tables.md`). Much faster and scales.
     Even after a scanpy/rapids run, use cspray for the Delta write.
2. **"How many h5ad files, and roughly how large?"**
   * Drives compute selection (§3) and whether cspray is needed.
   * Heterogeneous obs columns across files? cspray handles this (`references/cspray-tables.md`).
3. **"Do you need to reprocess from raw counts, or just extract the existing
   metadata (obs, var, embeddings)?"**
   * Just extract existing obs → cspray (or backed-mode read for a single file).
   * Reprocess → scanpy / rapids-singlecell pipeline.
4. **"Single sample or multi-sample? If multi-sample, do you need batch
   correction?"**
   * Multi-sample + batch correction → `references/scanpy-workflow.md` (multi-sample section).
5. **"I’ll track parameters and iterations with MLflow — any reason
   not to?"**
   * MLflow tracking is **on by default**. Only skip if the user
     explicitly declines. Do not silently omit it.

> **Rule of thumb:** If the user says "save to a table" or "build a
> dashboard" and isn't running QC/clustering, route to cspray immediately.
> Don't load the data into scanpy just to extract `.obs` — cspray does it
> at Spark scale without loading the full matrix into memory.

> **Parameter confirmation:** When the workflow involves QC / clustering /
> analysis, always present proposed parameters to the user for approval
> before running. See `references/scanpy-workflow.md` "Parameter Confirmation Protocol" for the full
> two-round pattern.

---

## 3. Compute Selection — Decision Tree

The primary constraint is **RAM**. h5ad files decompress into AnnData objects
that can be 3–10x larger in memory than on disk.

| Scenario | Recommended Compute | Notes |
|---|---|---|
| Single file or few files, **total < 1 GB on disk** | Serverless (default) | Works out of the box. |
| Single file or few files, **1–5 GB on disk** | Serverless — **select the largest memory option** available in the notebook compute picker | Prevents OOM kernel restarts. |
| Single file **> 5 GB** or aggregate **> 5 GB** | Classic all-purpose cluster with **high-memory instance** (e.g., `r5.4xlarge` / 128 GB+) | Set autotermination ≤ 30 min per workspace convention. |
| Single very large file + GPU desired | **Serverless GPU (A10)** preferred, or classic GPU cluster (`g5.4xlarge`) | See `references/rapids-singlecell.md`. `cupy-cuda12x` pre-installed on Serverless GPU. `executeCode` does NOT share GPU context — use notebook cells. |
| **cspray** (any file count) | Serverless works, **but** call `sdata.set_intermediary_persistance(persist=False)` after `from_h5ads()` | cspray uses `CLEAR CACHE`/`PERSIST TABLE` internally — blocked on Spark Connect. See `references/cspray-tables.md`. |

### Diagnosing OOM

If the notebook kernel dies silently ("Notebook state was lost", command
cancelled with no traceback), the most likely cause is the AnnData object
exhausting RAM.

**Agent action:** Ask the user for the file size(s). Recommend:
1. Increase serverless memory tier to the maximum available option, OR
2. Switch to a classic cluster with more RAM.

Do NOT retry on the same compute — it will fail the same way.

---

## 4. Tool-Specific Workflows (in reference files)

Detailed scanpy, rapids-singlecell, and cspray workflows are in the
reference files listed above. After routing, load the relevant file(s).

---

## 5. Decision Flowchart — Which Tool Path?

```
User provides h5ad path(s)
       │
       ├─ ASK SCOPING QUESTIONS (§2) if goal is unclear
       │
       ├─ Goal is interactive exploration / QC / clustering?
       │    │
       │    ├─ Single sample or few small files (< 1 GB) → load references/scanpy-workflow.md
       │    ├─ Multiple samples → load references/scanpy-workflow.md (multi-sample section)
       │    │    └─ ASK: batch key? harmony preferred?
       │    └─ Single very large file (> 500k cells) → load references/rapids-singlecell.md
       │         └─ ASK: GPU cluster OK?
       │
       └─ Goal is building tables / dashboards / SQL-queryable data?
            │
            ├─ Any number of files → load references/cspray-tables.md — preferred default
            ├─ Only need obs from a single file → backed-mode read (references/cspray-tables.md)
            └─ After scanpy/rapids analysis → still use cspray for Delta write (references/cspray-tables.md)
```

---


## 6. Common Pitfalls

Tool-specific pitfalls are in each reference file. Cross-cutting issues:

| Pitfall | Remedy |
|---|---|
| Kernel dies silently reading h5ad | Almost always OOM. Check file size, increase RAM (§3). |
| `scanpy` import error on serverless | Run `%pip install scanpy[leiden]` + restart. |
| cspray `CLEAR CACHE` error on serverless | Call `sdata.set_intermediary_persistance(persist=False)` after `from_h5ads()`. See `references/cspray-tables.md`. |
| cspray `FileNotFoundError` on `dbfs:` paths | Strip prefix: `path.replace("dbfs:", "")` before passing to `SprayData.from_h5ads()`. |
| cspray not found | Install from GitHub: `%pip install git+https://github.com/databricks-solutions/cspray.git@main` — not on PyPI. |
| UMAP looks like a blob | Upstream QC issue — revisit filtering thresholds. |
| Full `sc.read_h5ad()` just to inspect metadata | Use `ad.read_h5ad(path, backed="r")` instead — loads obs/var without the expression matrix. |
| `adata.raw` ignored, re-clustering processed data | Check `adata.raw is not None`; use `.raw.to_adata()` for reprocessing. |
| Gene names are Ensembl IDs, not symbols | Join against a BioMart/Ensembl reference CSV or use a var column. |
| `rank_genes_groups` errors after subsetting | Ensure `.copy()` after subsetting; stale views break DE tests. |
| Profiled QC but used static defaults anyway | If you computed per-sample P95/MAD, those values MUST feed into the threshold proposal (Gate G2). |
| Integrated biologically incompatible samples | Flag before Harmony (Gate G1). Harmony cannot correct across unrelated biology. |
| No cell type annotation after marker analysis | Gate G4 is mandatory — always suggest cell types after rank_genes_groups. |
| Notebook has no markdown explaining decisions | Every decision cell needs a preceding markdown cell with rationale. |
| No MLflow tracking set up | Gate G5 — default ON. Set up right after install. See `references/mlflow-tracking.md`. |
| `promote_suggested` `UNRESOLVED_COLUMN` on dotted obs names | h5ad files with obs columns like `orig.ident` (Seurat-origin) crash promotion. Scan batch to identify bad files, report to user, offer to re-run without them. See `references/cspray-tables.md` §"Handling Promotion Failures". |

---

## 7. Checklist Before Running

1. **Ask scoping questions (§2)** unless goal is already clear.
2. Confirm h5ad path(s) exist on a UC Volume.
3. Estimate total file size → pick compute (§3).
4. Route to the correct reference file(s) using the decision flowchart (§5).
5. If multiple samples → profile per-sample QC, ask batch key (Gate G1).
6. **Compute data-driven QC thresholds** and present for confirmation (Gate G2).
7. If single large file → offer rapids-singlecell (ask user about GPU).
8. If goal is tables/dashboards → recommend cspray.
9. Install packages in the first cell, restart Python.
10. **Start MLflow parent run** (`references/mlflow-tracking.md`) — log iterations as nested runs.
11. After clustering, **suggest cell type annotations** (Gate G4) with LLM —
    present as suggestions requiring expert review.
12. After analysis, persist results to Delta via cspray (`references/cspray-tables.md`).
13. **Include markdown narration** — decisions and justification only.
14. Log final run to MLflow: confirmed params, cell type annotations JSON,
    h5ad path (artifact only if user opts in).
