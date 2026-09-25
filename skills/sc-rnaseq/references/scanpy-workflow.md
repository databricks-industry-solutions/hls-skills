# Scanpy Workflow — Single-Sample & Multi-Sample Integration

> Reference file for the `sc-rnaseq` skill.  
> Load via `readSkillFile("skills/sc-rnaseq/references/scanpy-workflow.md")`
> when the decision flowchart routes to interactive exploration (single or
> multi-sample).

---

## Single-Sample Workflow (scanpy)

Use scanpy for interactive, single-sample (or small multi-sample) exploratory
analysis.

### Install

```python
%pip install scanpy[leiden] anndata
dbutils.library.restartPython()
```

> **Version pinning:** For reproducible pipelines (especially MLflow-tracked
> runs), pin exact versions, e.g.:
> `%pip install numpy==1.26.4 scanpy==1.11.4 anndata==0.12.10`.
> The Genesis Workbench also installs `scikit-network` for Louvain clustering
> without an igraph dependency — consider this if Leiden install is
> problematic.

### Parameter Confirmation Protocol (Gate G2)

**This is a mandatory gate.** Never silently pick QC thresholds or analysis
parameters and run. Always present proposed values to the user for
confirmation **and wait for their response** before executing the pipeline.
This applies to both scanpy and rapids-singlecell workflows.

#### Round 1 — Propose data-driven values, get consent

After computing QC metrics, calculate data-driven thresholds (see
"Data-Driven QC Thresholds" below) and present them — **not** static
textbook defaults. The table must show the data evidence:

> "Based on the QC distributions in your data, I propose these thresholds.
> Do they look reasonable, or would you like to adjust?"
>
> | Parameter | Proposed | Evidence | Textbook default |
> |---|---|---|---|
> | `pct_counts_mt` | < 7% | P95 = 5.5%, MAD upper = 7.1% | 20% |
> | `min_genes` | 350 | MAD lower = 342, P5 = 380 | 200 |
> | `n_genes_by_counts` | < 3,500 | MAD upper = 3,480, P95 = 2,535 | 2,500 |
> | `target_sum` | 10,000 | Standard | 10,000 |
> | `n_top_genes` | 2,000 | Standard | 2,000 |
> | `n_pcs` | 30 | Standard | 30 |
> | `cluster_resolution` | 1.0 | Starting point | 1.0 |

**Stop here and wait for the user to confirm or modify before proceeding.**
Do not generate the next code cell until the user responds.

> **Anti-pattern to avoid:** Computing per-sample QC (P95 pct_mt = 5.5%)
> then using pct_mt < 20 in the filter. If you profiled the data, the
> profile MUST inform the thresholds. Using static defaults after profiling
> means the profiling was wasted.

#### Round 2 — Flag adjustments after initial results

After the first analysis completes, review the results (QC plots, cluster
counts, UMAP structure) and suggest parameter changes **if warranted**:

> "The UMAP shows one dominant cluster with several small satellites. A lower
> resolution (e.g., 0.5) might give cleaner groupings. Want me to re-run
> with that?"

**Guardrails on iteration:**
* Suggest at most **one round of adjustments** per parameter. If the user
  accepted the initial value once and the result looks reasonable, don't
  keep proposing tweaks — it becomes laborious.
* Batch related suggestions into a single message (e.g., "lower resolution
  to 0.5 and raise pct_mt to 25") rather than asking one-by-one.
* If the user says "looks fine" or "let's move on", stop iterating
  immediately. Don't second-guess their judgment.
* For parameters with clear data-driven signals (e.g., QC scatter plots
  showing an obvious elbow), flag the evidence briefly. For subjective
  parameters (resolution, n_pcs), defer to the user's domain expertise.

#### When to skip confirmation

* The user provided explicit parameters in their request ("use resolution
  0.3 and filter at 5% mito") — just use them.
* Re-running with the same parameters after a code fix or compute change.
* The user said "use defaults" or "just run it".

---

### QC Strategy: Uniform vs Per-Sample Thresholds

When working with **multiple samples**, QC thresholds (pct_mt, min_genes,
n_genes_by_counts) can be applied either uniformly across all samples or
tuned per sample. The choice matters — different tissues, assays, or
sequencing depths can have very different QC distributions.

#### How to decide

Before committing to thresholds, **profile QC metrics per sample** using
backed reads or a quick QC-only pass. Present a per-sample summary to the
user:

```python
import anndata as ad
import pandas as pd

files = {"sample_A": "/Volumes/.../A.h5ad", "sample_B": "/Volumes/.../B.h5ad"}
qc_summary = []
for name, path in files.items():
    adata = ad.read_h5ad(path, backed="r")
    obs = adata.obs
    qc_summary.append({
        "sample": name,
        "n_cells": len(obs),
        "median_pct_mt": obs["pct_counts_mt"].median() if "pct_counts_mt" in obs else None,
        "median_n_genes": obs["n_genes_by_counts"].median() if "n_genes_by_counts" in obs else None,
        "p95_pct_mt": obs["pct_counts_mt"].quantile(0.95) if "pct_counts_mt" in obs else None,
    })
    adata.file.close()
pd.DataFrame(qc_summary)
```

Then present the findings:

> "QC distributions vary across your samples:
>
> | Sample | Cells | Median % MT | P95 % MT | Median genes |
> |---|---|---|---|---|
> | sample_A | 12,000 | 2.1% | 8.3% | 1,800 |
> | sample_B | 45,000 | 5.4% | 22.1% | 950 |
>
> Sample B has much higher mitochondrial content. Options:
> 1. **Uniform threshold** (e.g., pct_mt < 20) — simpler, keeps more cells
>    from sample B but may include lower-quality cells.
> 2. **Per-sample thresholds** — e.g., 10% for A, 25% for B — adapts to
>    each sample's quality profile.
>
> Which approach do you prefer?"

#### Tool-specific constraints

| Tool | Uniform | Per-sample | Notes |
|---|---|---|---|
| **cspray** | Yes | **No** (current limitation) | `cs.pp.filter_*` applies the same thresholds to all files in the SprayData object. |
| **scanpy** | Yes | Yes | Filter each AnnData individually before `ad.concat()`. |
| **rapids-singlecell** | Yes | Yes | Same as scanpy — filter before concat. |

> **When to skip this decision:** Single-sample workflows, or the user has
> already specified thresholds. Don't add a per-sample profiling step for
> one file.

### Profiling with Backed Reads

When the agent needs to **explore metadata it doesn't already know** —
batch keys, obs columns, whether `.raw` exists, gene name format — use
backed-mode reads instead of loading the full expression matrix. This
applies to a **small number of files** (up to \~10–20); for hundreds of
files, use cspray which reads metadata at Spark scale.

```python
import anndata as ad

def profile_h5ad(path):
    """Inspect an h5ad file without loading the expression matrix."""
    adata = ad.read_h5ad(path, backed="r")
    print(f"Shape: {adata.shape[0]:,} cells x {adata.shape[1]:,} genes")
    print(f".raw present: {adata.raw is not None}")
    print(f"Layers: {list(adata.layers.keys())}")
    print(f"obsm keys: {list(adata.obsm.keys())}")
    print(f"obs columns ({len(adata.obs.columns)}):")
    for col in adata.obs.columns:
        n_unique = adata.obs[col].nunique()
        examples = adata.obs[col].dropna().unique()[:5].tolist()
        print(f"  {col}: {n_unique} unique — {examples}")
    adata.file.close()
    return adata.obs.copy()  # return obs as pandas DataFrame
```

> **When to use backed reads:**
> * The agent needs to discover obs columns, batch keys, or file structure
>   that the user hasn't already provided.
> * A small number of files (not hundreds — cspray is better there).
> * You need to confirm `.raw` presence, gene name format, or layer names.
>
> **When to skip:** The user already provided parameters and column names,
> or said "just run it." Don't add a profiling step that serves no purpose.
>
> **Key rule:** If you DO need to inspect metadata, never use
> `sc.read_h5ad()` for that — it loads the full expression matrix. Use
> `ad.read_h5ad(path, backed="r")` which loads only obs/var/uns/obsm.
> Always close the file handle after: `adata.file.close()`.

When profiling **multiple files** (small batches), loop with backed reads:

```python
import anndata as ad

files = {
    "sample_A": "/Volumes/.../sample_A.h5ad",
    "sample_B": "/Volumes/.../sample_B.h5ad",
}

for name, path in files.items():
    adata = ad.read_h5ad(path, backed="r")
    print(f"\n{'='*60}")
    print(f"Sample: {name} — {adata.shape[0]:,} cells x {adata.shape[1]:,} genes")
    print(f"  .raw present: {adata.raw is not None}")
    for col in ['donor_id', 'batch', 'sample', 'cell_type', 'disease',
                'tissue', 'assay', 'sex']:
        if col in adata.obs.columns:
            vals = adata.obs[col].unique()
            print(f"  {col}: {vals[:5].tolist()}"
                  f"{'...' if len(vals) > 5 else ''}  ({len(vals)} unique)")
    adata.file.close()
```

### Read h5ad from Volume (Full Load)

When ready to process (either after profiling or when the user has already
provided sufficient context), do the full read:

```python
import scanpy as sc

adata = sc.read_h5ad("/Volumes/<catalog>/<schema>/<volume>/<file>.h5ad")
adata.obs_names_make_unique()

# If the file has a .raw layer with unprocessed counts, use it
if adata.raw is not None:
    adata = adata.raw.to_adata()
```

> **Raw data fallback:** Many published h5ad files store processed data in
> `.X` and raw counts in `.raw`. Always check `adata.raw`; if it exists and
> the user wants to reprocess from scratch, convert with `.raw.to_adata()`.

### Gene Name Handling

Gene identifiers in `.var` vary across datasets (Ensembl IDs, symbols, mixed).
If the user's file uses Ensembl IDs and they need gene symbols:

```python
# Option 1: gene names already in a var column
adata.var_names = adata.var["<gene_name_column>"].astype(str).values
adata.var_names_make_unique()

# Option 2: join against an Ensembl reference (e.g., BioMart export)
import pandas as pd
ref = pd.read_csv("/Volumes/<catalog>/<schema>/<volume>/ensembl_genes.csv")
adata.var = adata.var.reset_index().merge(
    ref, left_on="index", right_on="ensembl_gene_id", how="left"
)
adata.var["gene_name"] = adata.var["external_gene_name"].fillna(adata.var["ensembl_gene_id"])
adata.var = adata.var.set_index("gene_name", drop=False)
adata.var_names_make_unique()
```

### Typical QC → Clustering Pipeline

> **Check gene naming first:** Many CELLxGENE / Allen Brain Atlas h5ad
> files use Ensembl IDs as `var_names` with symbols in
> `var["feature_name"]`. If `var_names` start with `ENSG`, the QC
> annotations below will silently produce all-zero columns (`pct_counts_mt
> = 0`). Swap to gene symbols first — see "Gene Name Handling" above.

```python
# --- Verify var_names are gene symbols, not Ensembl IDs ---
# If var_names are ENSG*, swap to symbol column before QC annotation.
# Without this, MT-/RPS/RPL prefix matching produces all zeros.
if adata.var_names[0].startswith("ENSG"):
    for col in ["feature_name", "gene_symbols", "gene_name", "symbol"]:
        if col in adata.var.columns:
            adata.var["ensembl_id"] = adata.var_names.copy()
            adata.var_names = adata.var[col].astype(str).values
            adata.var_names_make_unique()
            print(f"Swapped var_names from Ensembl IDs to {col}")
            break
    else:
        print("WARNING: var_names are Ensembl IDs but no symbol column found.")

# Annotate gene classes for QC
adata.var["mt"]   = adata.var_names.str.upper().str.startswith("MT-")     # mitochondrial
adata.var["ribo"] = adata.var_names.str.upper().str.startswith(("RPS", "RPL"))  # ribosomal
adata.var["hb"]   = adata.var_names.str.upper().str.contains(r"^HB[^(P)]")     # hemoglobin

sc.pp.calculate_qc_metrics(
    adata, qc_vars=["mt", "ribo", "hb"], inplace=True, log1p=True
)

# Filter cells & genes
sc.pp.filter_cells(adata, min_genes=200)
sc.pp.filter_genes(adata, min_cells=3)
adata = adata[adata.obs.n_genes_by_counts < 2500, :]  # doublet proxy
adata = adata[adata.obs.pct_counts_mt < 20, :].copy()  # dead/dying cells

# Normalize → log → HVGs
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata, n_top_genes=2000)

# PCA → neighbors → UMAP → Leiden
sc.tl.pca(adata, n_comps=50)
sc.pp.neighbors(adata, n_pcs=30)
sc.tl.umap(adata)
sc.tl.leiden(adata, resolution=1.0)

sc.pl.umap(adata, color=["leiden"])
```

> **QC notes:**
> * Ribosomal (`ribo`) and hemoglobin (`hb`) fractions help identify low-quality
>   cells beyond mitochondrial fraction alone.
> * The `n_genes_by_counts < 2500` upper bound is a simple doublet proxy.
>   For rigorous doublet removal, consider **scrublet** or **DoubletFinder**.
> * Use `.str.upper()` for case-insensitive matching — gene-name casing varies
>   across species and references.

Adapt parameters to the dataset. The above is a starting template, not a
fixed recipe.

### Data-Driven QC Thresholds

Rather than proposing textbook defaults (pct_mt < 20, n_genes < 2500), the
agent should **compute data-driven thresholds** after the initial QC metrics
pass and present them to the user. This replicates how a scientist inspects
violin/scatter plots before choosing cutoffs.

```python
import numpy as np

def mad_outlier_bound(series, n_mads=3):
    """Compute median ± n_mads * MAD for outlier detection."""
    med = series.median()
    mad = np.median(np.abs(series - med))
    return med - n_mads * mad, med + n_mads * mad

# After sc.pp.calculate_qc_metrics(adata, ...)
mt_low, mt_high = mad_outlier_bound(adata.obs["pct_counts_mt"])
genes_low, genes_high = mad_outlier_bound(adata.obs["n_genes_by_counts"])
counts_low, counts_high = mad_outlier_bound(adata.obs["total_counts"])

# Also compute percentiles for context
mt_p95 = adata.obs["pct_counts_mt"].quantile(0.95)
genes_p5 = adata.obs["n_genes_by_counts"].quantile(0.05)
genes_p95 = adata.obs["n_genes_by_counts"].quantile(0.95)
```

Then present the data-informed proposal (not the static defaults):

> "Based on the QC distributions in your data:
>
> | Parameter | Data-driven value | How derived | Default |
> |---|---|---|---|
> | `pct_counts_mt` | < 8.5% | P95 = 8.3%, MAD upper = 9.1% | 20% |
> | `n_genes_by_counts` upper | < 4,200 | MAD upper = 4,180 | 2,500 |
> | `n_genes_by_counts` lower | > 350 | MAD lower = 342, P5 = 380 | 200 |
> | `min_genes` | 350 | From lower bound above | 200 |
>
> The data suggests tighter thresholds than the textbook defaults.
> Want me to use these, or adjust?"

**When this applies:**
* Multi-sample datasets where QC distributions vary across samples.
* Any dataset where the agent hasn't been given explicit thresholds.
* The QC metrics must already be computed (requires the full load, not
  backed mode — unless pre-computed QC columns exist in the h5ad).

**When to skip:** The user already provided explicit thresholds, or said
"use defaults."

### Marker Gene Analysis

After clustering, identify differentially expressed genes per cluster:

```python
# Wilcoxon rank-sum test per cluster
sc.tl.rank_genes_groups(adata, groupby="leiden", method="wilcoxon")
sc.pl.rank_genes_groups(adata, n_genes=20, sharey=False, save="marker_genes.png")

# Extract top N markers per cluster to a DataFrame
import pandas as pd
n_markers = 10
marker_df = pd.DataFrame(adata.uns["rank_genes_groups"]["names"]).head(n_markers)
marker_df.to_csv("/tmp/top_markers_per_cluster.csv", index=False)
```

### LLM-Assisted Cell Type Annotation (Gate G4)

**This is a mandatory gate.** After marker gene analysis, the agent MUST
interpret top markers per cluster and suggest preliminary cell type labels.
Do not end the analysis without presenting cell type suggestions. This is
a fast first pass that leverages the LLM's knowledge of canonical marker–
cell type associations.

If the data already has a `cell_type` column from the original file, the
agent should **compare the new clustering against the existing annotations**
and flag discrepancies (e.g., "Cluster 5 is mostly 'keratinocyte' per the
original annotation but split across two new clusters").

**⚠️ These are approximate suggestions — they MUST be expert-reviewed.**

#### How it works

1. Extract the top markers per cluster (already done in Marker Gene Analysis).
2. If `tissue` is in `.obs`, note the tissue context — expected cell
   populations differ by tissue. If not, ask the user.
3. The agent examines the markers and presents a suggestion table:

> **⚠️ LLM-suggested cell type annotations — requires expert verification**
>
> Tissue context: lung
>
> | Cluster | Top markers | Suggested type | Confidence | Basis |
> |---|---|---|---|---|
> | 0 | CD3D, CD3E, IL7R, TCF7 | T cells (naive) | High | Canonical T cell markers |
> | 1 | CD14, LYZ, S100A8, S100A9 | Monocytes (classical) | High | Canonical myeloid |
> | 2 | MS4A1, CD79A, CD79B | B cells | High | Canonical B cell markers |
> | 3 | NKG7, GNLY, KLRD1 | NK cells | Medium | Could also be cytotoxic T |
> | 4 | COL1A1, DCN, LUM | Fibroblasts | Medium | Tissue-context dependent |
> | 5 | EPCAM, KRT18, MUC1 | Epithelial | Medium | Broad epithelial |
>
> Please review and correct. Want me to assign these to
> `adata.obs['cell_type_suggested']`?

4. After user confirms/corrects, write both the LLM suggestion and the
   user's final decision to `.obs`:

```python
# Build annotation map from user-confirmed labels
annotation_map = {
    "0": "T cells (naive)",
    "1": "Monocytes (classical)",
    "2": "B cells",
    "3": "NK cells",           # user confirmed
    "4": "Myofibroblasts",     # user corrected from "Fibroblasts"
    "5": "Alveolar epithelial", # user refined from "Epithelial"
}

# Store both the LLM suggestion and the user-confirmed label
adata.obs["cell_type_llm"] = adata.obs["leiden"].map(annotation_map)
adata.obs["cell_type_source"] = "llm_suggested"  # default
# After user corrections:
# adata.obs.loc[adata.obs["leiden"].isin(["4", "5"]), "cell_type_source"] = "user_corrected"
```

#### Guardrails

* **Always present as suggestions.** Never auto-assign without user
  confirmation. The table header must include the warning.
* **Confidence signal:** High = well-known canonical markers with no
  ambiguity. Medium = plausible but could be another type. Low = markers
  are ambiguous or the agent isn't confident.
* **Tissue context matters.** The same markers mean different things in
  lung vs brain vs blood. Ask for tissue if not in `.obs`.
* **Track provenance.** Store `cell_type_source` ("llm_suggested" vs
  "user_corrected" vs "user_provided") so downstream consumers know the
  annotation origin. Log this to MLflow as a structured artifact.
* **For rigorous annotation,** suggest dedicated tools (CellTypist,
  scimilarity, Azimuth) as a follow-up — the LLM call is a fast first
  pass, not a replacement for reference-based methods.

#### Notebook markdown

When generating notebook cells for this step, **always include a markdown
cell** above the annotation code:

```markdown
## Cell Type Annotation (LLM-Suggested — Expert Review Required)

The following cell type labels were suggested by the assistant based on
top marker genes per cluster. **These are approximate and must be verified
by a domain expert.** Corrections were applied for clusters 4 and 5 per
user review.
```

### Extracting Embeddings to `.obs`

For downstream Delta tables or flat-file exports, copy PCA / UMAP coordinates
into `.obs` so they travel with cell metadata:

```python
for i in range(min(4, adata.obsm["X_pca"].shape[1])):
    adata.obs[f"PCA_{i}"] = adata.obsm["X_pca"][:, i]
for i in range(2):
    adata.obs[f"UMAP_{i}"] = adata.obsm["X_umap"][:, i]
```

### Diffusion Pseudotime (Optional)

If the user's experiment has a trajectory (e.g., differentiation):

```python
import numpy as np
# Set root cell (e.g., first cell in cluster 0)
adata.uns["iroot"] = int(np.flatnonzero(adata.obs["leiden"] == "0")[0])
sc.tl.diffmap(adata)
sc.tl.dpt(adata)
sc.pl.umap(adata, color=["dpt_pseudotime"])
```

> Only compute pseudotime when biologically meaningful. Ask the user if their
> experiment has an expected trajectory before adding this step.

---

## Multi-Sample Integration (scanpy + harmony / scVI)

When the user provides **multiple h5ad files** (or a single concatenated object
with multiple samples), integration requires batch-correction.

### Agent action — Profile first, THEN ask (Gate G1)

**This is a mandatory gate.** Do not ask the user to name a batch key blind,
and do not proceed past this point without user confirmation. Instead,
inspect the files with backed reads ("Profiling with Backed Reads" above) and
present what you find:

1. **Profile all files in backed mode** to discover obs columns and their
   unique values. Look for columns likely to represent batch structure:
   `donor_id`, `sample`, `batch`, `library_id`, `site`, `dataset`,
   `study`, `platform`, `assay`.
2. **Present a summary to the user** with a recommendation:
   > "I inspected both files. They share these metadata columns that could
   > serve as batch keys:
   >
   > | Column | File A unique | File B unique | Overlap? |
   > |---|---|---|---|
   > | `donor_id` | 5 donors | 8 donors | No overlap — good batch key |
   > | `assay` | 10x 3' v2 | Seq-Well | Different — could confound |
   > | `tissue` | lung | lung | Same — not useful as batch key |
   >
   > I'd recommend batch-correcting on `donor_id`. Sound good, or would
   > you prefer a different key?"
3. **Ask for integration method preference:**
   Default recommendation: **Harmony** — fast, lightweight, well-supported.
   Alternatives: scVI (deeper correction), scanorama, bbknn.

> **If the user hasn't already named a batch key**, profile first — don't
> load multiple large h5ad files fully just to inspect obs columns. Backed
> reads cost almost nothing. If the user already said "batch on donor_id",
> skip straight to the full load.

> **Biologically incompatible samples:** If profiling reveals the files are
> from different tissues, organisms, or fundamentally different assays,
> **stop and flag this before proceeding.** Harmony cannot meaningfully
> correct across unrelated biology. Present the evidence:
> > "These files appear to be from different tissues (lung vs skin) with
> > different cell type populations. Integration may merge unrelated cell
> > types. Would you prefer separate per-sample analysis instead?"
>
> **Wait for the user's response.** Do not proceed with integration if the
> biology doesn't support it.

### Harmony integration

```python
%pip install scanpy[leiden] harmonypy anndata
%restart_python
```

**Use `harmonypy` directly** — do NOT use the scanpy wrapper
`sce.pp.harmony_integrate()`. The wrapper is broken on anndata ≥ 0.13
(shape mismatch when assigning the corrected embedding) and does not
reliably support multi-key batch correction.

```python
import scanpy as sc
import harmonypy as hm
import anndata as ad

# Concatenate multiple AnnData objects
# (assumes adatas is a list of AnnData, each with .obs["sample_id"])
adata = ad.concat(adatas, join="outer", label="sample_id")

# Standard preprocessing (see above) …
# PCA must be computed before Harmony:
sc.tl.pca(adata, n_comps=50)

# --- Harmony via direct API ---
ho = hm.run_harmony(
    adata.obsm["X_pca"],          # (n_cells, n_pcs) PCA matrix
    adata.obs,                     # metadata DataFrame
    vars_use=["sample_id"],        # batch key(s) — list works for multi-key
)

# harmonypy 2.x: Z_corr is already (n_cells, n_pcs) — do NOT transpose
adata.obsm["X_pca_harmony"] = ho.Z_corr

# Use the corrected embedding for neighbors/UMAP
sc.pp.neighbors(adata, use_rep="X_pca_harmony", n_pcs=30)
sc.tl.umap(adata)
sc.tl.leiden(adata, resolution=1.0)
```

#### Multi-key batch correction

To correct on multiple batch variables simultaneously (e.g., sample AND
assay), pass a list to `vars_use`:

```python
ho = hm.run_harmony(
    adata.obsm["X_pca"],
    adata.obs,
    vars_use=["sample_id", "assay"],  # corrects both sources of variation
)
adata.obsm["X_pca_harmony"] = ho.Z_corr
```

#### Version notes

> * **harmonypy 2.x** (current): `ho.Z_corr` is `(n_cells, n_pcs)`.
>   Assign directly to `obsm` — do NOT transpose.
> * **harmonypy 1.x** (legacy): `ho.Z_corr` was `(n_pcs, n_cells)`.
>   Requires `.T` before assigning. Check with
>   `ho.Z_corr.shape[0] == adata.n_obs` — if False, transpose.
> * **`sce.pp.harmony_integrate()`**: Broken on anndata ≥ 0.13. The
>   wrapper transposes the result assuming the 1.x convention, producing a
>   shape mismatch with harmonypy 2.x. Avoid entirely.
