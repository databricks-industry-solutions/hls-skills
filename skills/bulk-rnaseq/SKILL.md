---
name: bulk-rnaseq
description: PyDESeq2 differential expression for bulk RNA-seq. Counts + metadata → Wald tests, FDR, optional apeGLM shrinkage, PCA/volcano/MA plots. For pathway enrichment of DE results use pathway-enrichment-analysis.
author: Yen Low
license: Databricks License
---

# PyDESeq2 — Bulk RNA-seq Differential Expression

## Overview

PyDESeq2 is a Python implementation of DESeq2 for differential expression on bulk RNA-seq count data. This skill covers the end-to-end pipeline: load counts and metadata, specify a design formula, fit the model, run Wald tests with FDR correction, optionally shrink LFCs, export results, and produce QC/visualization plots (PCA, volcano, heatmap, MA).

## When to Use

- Analyzing bulk RNA-seq count matrices for differential expression
- Comparing gene expression between conditions (e.g. treated vs control)
- Multi-factor designs that account for batch effects or covariates
- Converting an R DESeq2 workflow to Python / pandas / AnnData
- Integrating DE into a Python analysis pipeline
- For pathway/GO enrichment of DE gene lists, use `pathway-enrichment-analysis` instead

## Prerequisites

- **Packages**: `pydeseq2`, `pandas`, `numpy`, `scipy`, `scikit-learn`, `anndata`
- **Optional (plots)**: `matplotlib`, `seaborn`, `adjustText`
- **Inputs**:
  - Count matrix — non-negative integer read counts (genes × samples in files; **samples × genes** after load)
  - Metadata — samples × experimental factors; sample IDs must match count matrix index
- **Environment**:

```bash
pip install pydeseq2
# or: conda install -c bioconda pydeseq2
```

Python 3.10–3.11 recommended.

## Quick Start

```python
import pandas as pd
import numpy as np
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats

counts_df = pd.read_csv("counts.csv", index_col=0).T  # samples × genes
metadata = pd.read_csv("metadata.csv", index_col=0)

genes_to_keep = counts_df.columns[counts_df.sum(axis=0) >= 10]
counts_df = counts_df[genes_to_keep]

dds = DeseqDataSet(
    counts=counts_df,
    metadata=metadata,
    design="~condition",
    refit_cooks=True,
)
dds.deseq2()

ds = DeseqStats(dds, contrast=["condition", "treated", "control"])
ds.summary()

significant = ds.results_df[ds.results_df.padj < 0.05]
print(f"Found {len(significant)} significant genes")
```

Or via the bundled CLI:

```bash
python scripts/run_deseq2_analysis.py \
  --counts counts.csv \
  --metadata metadata.csv \
  --design "~condition" \
  --contrast condition treated control \
  --output results/ \
  --plots
```

## Workflow

### Step 1: Prepare counts and metadata

Load counts as **samples × genes**. Transpose typical genes × samples CSVs with `.T`. Align sample IDs; drop low-count genes and samples with missing design covariates.

```python
# From CSV (typical format: genes × samples, needs transpose)
counts_df = pd.read_csv("counts.csv", index_col=0).T
metadata = pd.read_csv("metadata.csv", index_col=0)

# From AnnData
# import anndata as ad
# adata = ad.read_h5ad("data.h5ad")
# counts_df = pd.DataFrame(adata.X, index=adata.obs_names, columns=adata.var_names)
# metadata = adata.obs

genes_to_keep = counts_df.columns[counts_df.sum(axis=0) >= 10]
counts_df = counts_df[genes_to_keep]

samples_to_keep = ~metadata.condition.isna()
counts_df = counts_df.loc[samples_to_keep]
metadata = metadata.loc[samples_to_keep]
```

### Step 2: Specify the design formula

**Always use `design="~column_name"` string notation** (Wilkinson formula). Do **not** use legacy `design_factors`. Rename metadata columns that contain spaces or special characters before fitting.

```python
metadata.columns = metadata.columns.str.replace(" ", "_")

design = "~condition"                 # two-group
design = "~batch + condition"         # adjust for batch (put adjustments first)
design = "~age + condition"           # continuous covariate
design = "~group + condition + group:condition"  # interaction
```

**Design formula guidelines:**
- **Always use `design="~column_name"` (string formula notation)** — do NOT use `design_factors` which is a legacy parameter
- **Rename metadata columns that contain spaces or special characters** to use underscores before passing to DeseqDataSet. Example: `metadata.columns = metadata.columns.str.replace(' ', '_')`
- Use Wilkinson formula notation (R-style): `"~condition"`, `"~batch + condition"`
- Put adjustment variables (e.g., batch) before the main variable of interest
- Ensure variables exist as columns in the metadata DataFrame
- Use appropriate data types (categorical for discrete variables)
- The contrast values should still use the original data values (e.g., `'non-viral sepsis patient'`), even if the column was renamed — only the column NAME matters for formula parsing

### Step 3: Fit DESeq2

```python
from pydeseq2.dds import DeseqDataSet

dds = DeseqDataSet(
    counts=counts_df,
    metadata=metadata,
    design="~condition",
    refit_cooks=True,  # Refit after removing outliers
    n_cpus=1           # Parallel processing (adjust as needed)
)
dds.deseq2()
```

`deseq2()` runs size-factor normalization, dispersion estimation/trend/MAP, LFC fitting, Cook's distances, and optional outlier refit.

### Step 4: QC with PCA (before testing)

Generate a PCA on log2(size-factor-normalized counts + 1) using the top ~500 variable genes **after** `dds.deseq2()` and **before** Wald testing. Samples should cluster by condition; if they cluster by batch, revise the design (e.g. `"~batch + condition"`). Full plotting code: `references/workflow_guide.md`.

```python
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

size_factors = dds.obsm["size_factors"]
normalized_counts = counts_df / size_factors[:, None]
log_counts = np.log2(normalized_counts + 1)
top_var_genes = log_counts.var(axis=0).nlargest(500).index
pcs = PCA(n_components=2).fit_transform(
    StandardScaler().fit_transform(log_counts[top_var_genes])
)
# Plot pcs colored by metadata["condition"] — verify clustering
```

### Step 5: Statistical testing

```python
from pydeseq2.ds import DeseqStats

ds = DeseqStats(
    dds,
    contrast=["condition", "treated", "control"],  # Test treated vs control
    alpha=0.05,                # Significance threshold
    cooks_filter=True,         # Filter outliers
    independent_filter=True    # Filter low-power tests
)

ds.summary()
```

**Contrast specification:**
- Format: `[variable, test_level, reference_level]`
- Example: `["condition", "treated", "control"]` tests treated vs control
- If `None`, uses the last coefficient in the design

**Result DataFrame columns:**
- `baseMean`: Mean normalized count across samples
- `log2FoldChange`: Log2 fold change between conditions
- `lfcSE`: Standard error of LFC
- `stat`: Wald test statistic
- `pvalue`: Raw p-value
- `padj`: Adjusted p-value (FDR-corrected via Benjamini-Hochberg)

### Step 5: Optional LFC Shrinkage

Apply shrinkage to reduce noise in fold change estimates:

```python
ds.lfc_shrink()  # Applies apeGLM shrinkage
```

**When to use LFC shrinkage:**
- For visualization (volcano plots, heatmaps)
- For ranking genes by effect size
- When prioritizing genes for follow-up experiments

**Important:** Shrinkage affects only the log2FoldChange values, not the statistical test results (p-values remain unchanged). Use shrunk values for visualization but report unshrunken p-values for significance.

### Step 6: Result Export

Save results and intermediate objects:

```python
import pickle

# Export results as CSV
ds.results_df.to_csv("deseq2_results.csv")

# Save significant genes only
significant = ds.results_df[ds.results_df.padj < 0.05]
significant.to_csv("significant_genes.csv")

# Save DeseqDataSet for later use
with open("dds_result.pkl", "wb") as f:
    pickle.dump(dds.to_picklable_anndata(), f)
```

**Recommended plots every analysis:** PCA (required QC), volcano (required overview). Optional: heatmap of top DEGs, MA plot. Plot recipes and axis rules live in `references/workflow_guide.md`.

**Volcano / MA color rules:** upregulated (log2FC > 1, padj < 0.05) = red; downregulated (log2FC < -1, padj < 0.05) = blue; non-significant = grey. Y-axis for volcano uses `-log10(pvalue)` (raw), not padj. Axis limits use finite `min()`/`max()` × 1.05 — never `quantile()` (clips top hits).

## Key Parameters

| Parameter | Default | Range / options | Effect |
|-----------|---------|-----------------|--------|
| `design` | required | Wilkinson string, e.g. `"~batch + condition"` | Model formula; never `design_factors` |
| `contrast` | last coef | `[variable, test_level, reference_level]` | Which comparison to test |
| `refit_cooks` | `True` | bool | Refit after outlier removal |
| `n_cpus` | `1` | ≥1 | Parallelism for fitting |
| `alpha` | `0.05` | 0–1 | Significance / independent-filter target |
| `cooks_filter` | `True` | bool | Filter Cook's outliers in stats |
| `independent_filter` | `True` | bool | Filter low-power tests |
| `--min-counts` (CLI) | `10` | ≥0 | Gene total-count filter |
| `padj` threshold | `0.05` | 0–1 | Call significant genes |

## Common Recipes

### Recipe: Two-group comparison

When to use: simple treated vs control.

```python
dds = DeseqDataSet(counts=counts_df, metadata=metadata, design="~condition")
dds.deseq2()
ds = DeseqStats(dds, contrast=["condition", "treated", "control"])
ds.summary()
significant = ds.results_df[ds.results_df.padj < 0.05]
```

### Recipe: Multiple treatments vs control

When to use: several levels of `condition` against one reference; reuse one fitted `dds`.

```python
dds = DeseqDataSet(counts=counts_df, metadata=metadata, design="~condition")
dds.deseq2()
all_results = {}
for treatment in ["treatment_A", "treatment_B", "treatment_C"]:
    ds = DeseqStats(dds, contrast=["condition", treatment, "control"])
    ds.summary()
    all_results[treatment] = ds.results_df
```

### Recipe: Batch adjustment

When to use: technical batches confound condition.

```python
dds = DeseqDataSet(counts=counts_df, metadata=metadata, design="~batch + condition")
dds.deseq2()
ds = DeseqStats(dds, contrast=["condition", "treated", "control"])
ds.summary()
```

### Recipe: Continuous covariate

When to use: adjust for age, dose, etc.

```python
metadata["age"] = pd.to_numeric(metadata["age"])
dds = DeseqDataSet(counts=counts_df, metadata=metadata, design="~age + condition")
dds.deseq2()
ds = DeseqStats(dds, contrast=["condition", "treated", "control"])
ds.summary()
```

### Recipe: Rank and split DEGs

When to use: hand-off to enrichment or reporting.

```python
significant = ds.results_df[ds.results_df.padj < 0.05]
sig_large = ds.results_df[(ds.results_df.padj < 0.05) & (ds.results_df.log2FoldChange.abs() > 1)]
up = significant[significant.log2FoldChange > 0]
down = significant[significant.log2FoldChange < 0]
```

## Expected Outputs

- `deseq2_results.csv` — full results (`baseMean`, `log2FoldChange`, `lfcSE`, `stat`, `pvalue`, `padj`)
- `significant_genes.csv` — `padj < 0.05` (optionally also `|log2FoldChange| > 1`)
- `dds_result.pkl` — picklable AnnData for refitting / replotting without re-running DESeq2
- Plots: `pca_plot.png`, `volcano_plot.png`; optional `heatmap_top_degs.png`, `ma_plot.png`
- CLI (`scripts/run_deseq2_analysis.py --output results/`): same artifacts under the output directory

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Index mismatch between counts and metadata | Sample IDs differ | Align on intersection of indexes |
| All genes zero / odd shape | Counts not transposed | Expect samples × genes; `.T` if genes × samples |
| `FormulaSyntaxError: Missing operator` | Spaces in column names | `metadata.columns = metadata.columns.str.replace(' ', '_')`; use `design="~col"` |
| Design matrix not full rank | Confounded factors (e.g. batch=condition) | Drop confounder or model interaction; check `pd.crosstab` |
| No significant genes | Small effects, high variance, low N, batch | Inspect dispersions/size factors; add covariates; review PCA |
| Samples cluster by batch on PCA | Unmodeled technical factor | Use `"~batch + condition"` |
| Volcano top genes clipped | Axis limits via `quantile()` | Use finite min/max × 1.05 |

```python
# Align samples
common = counts_df.index.intersection(metadata.index)
counts_df, metadata = counts_df.loc[common], metadata.loc[common]

# Diagnose confounding
print(pd.crosstab(metadata.condition, metadata.batch))
```

## Bundled Resources

- `references/api_reference.md` — PyDESeq2 classes, methods, attributes
- `references/workflow_guide.md` — extended workflows, viz code, deep troubleshooting
- `scripts/run_deseq2_analysis.py` — CLI for standard DE + optional plots

## References

- Adapted from [PyDESeq2 skill on MCP Market](https://mcpmarket.com/tools/skills/pydeseq2-gene-expression-analysis)
- [PyDESeq2 documentation](https://pydeseq2.readthedocs.io)
- [PyDESeq2 GitHub](https://github.com/owkin/PyDESeq2)
- Muzellec et al. (2023) *Bioinformatics* — [DOI:10.1093/bioinformatics/btad547](https://doi.org/10.1093/bioinformatics/btad547)
- Love et al. (2014) *Genome Biology* — original DESeq2 [DOI:10.1186/s13059-014-0550-8](https://doi.org/10.1186/s13059-014-0550-8)
