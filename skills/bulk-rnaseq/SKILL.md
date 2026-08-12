---
name: bulk-rnaseq
description: Differential gene expression analysis (Python DESeq2). Identify DE genes from bulk RNA-seq counts, Wald tests, FDR correction, PCA clustering, volcano, MA plots, for RNA-seq analysis.
author: Yen Low
license: Databricks License
---
# PyDESeq2

## Overview

PyDESeq2 is a Python implementation of DESeq2 for differential expression analysis with bulk RNA-seq data. Design and execute complete workflows from data loading through result interpretation, including single-factor and multi-factor designs, Wald tests with multiple testing correction, optional apeGLM shrinkage, and integration with pandas and AnnData.

## When to Use This Skill

This skill should be used when:
- Analyzing bulk RNA-seq count data for differential expression
- Comparing gene expression between experimental conditions (e.g., treated vs control)
- Performing multi-factor designs accounting for batch effects or covariates
- Converting R-based DESeq2 workflows to Python
- Integrating differential expression analysis into Python-based pipelines
- Users mention "DESeq2", "differential expression", "RNA-seq analysis", or "PyDESeq2"

## Quick Start Workflow

For users who want to perform a standard differential expression analysis:

```python
import pandas as pd
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats

# 1. Load data
counts_df = pd.read_csv("counts.csv", index_col=0).T  # Transpose to samples × genes
metadata = pd.read_csv("metadata.csv", index_col=0)

# 2. Filter low-count genes
genes_to_keep = counts_df.columns[counts_df.sum(axis=0) >= 10]
counts_df = counts_df[genes_to_keep]

# 3. Initialize and fit DESeq2
dds = DeseqDataSet(
    counts=counts_df,
    metadata=metadata,
    design="~condition",
    refit_cooks=True
)
dds.deseq2()

# 4. PCA plot (MANDATORY QC step — always include)
#    See Visualization Guidelines > PCA Plot for full code
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
size_factors = dds.obsm["size_factors"]
normalized_counts = counts_df[genes_to_keep] / size_factors[:, None]
log_counts = np.log2(normalized_counts + 1)
gene_var = log_counts.var(axis=0)
top_var_genes = gene_var.nlargest(500).index
scaled = StandardScaler().fit_transform(log_counts[top_var_genes])
pca = PCA(n_components=2)
pcs = pca.fit_transform(scaled)
# Plot PCs colored by condition — verify samples cluster by group

# 5. Perform statistical testing
ds = DeseqStats(dds, contrast=["condition", "treated", "control"])
ds.summary()

# 6. Access results
results = ds.results_df
significant = results[results.padj < 0.05]
print(f"Found {len(significant)} significant genes")
```

## Core Workflow Steps

### Step 1: Data Preparation

**Input requirements:**
- **Count matrix:** Samples × genes DataFrame with non-negative integer read counts
- **Metadata:** Samples × variables DataFrame with experimental factors

**Common data loading patterns:**

```python
# From CSV (typical format: genes × samples, needs transpose)
counts_df = pd.read_csv("counts.csv", index_col=0).T
metadata = pd.read_csv("metadata.csv", index_col=0)

# From TSV
counts_df = pd.read_csv("counts.tsv", sep="\t", index_col=0).T

# From AnnData
import anndata as ad
adata = ad.read_h5ad("data.h5ad")
counts_df = pd.DataFrame(adata.X, index=adata.obs_names, columns=adata.var_names)
metadata = adata.obs
```

**Data filtering:**

```python
# Remove low-count genes
genes_to_keep = counts_df.columns[counts_df.sum(axis=0) >= 10]
counts_df = counts_df[genes_to_keep]

# Remove samples with missing metadata
samples_to_keep = ~metadata.condition.isna()
counts_df = counts_df.loc[samples_to_keep]
metadata = metadata.loc[samples_to_keep]
```

### Step 2: Design Specification

The design formula specifies how gene expression is modeled.

**CRITICAL: Always use `design="~column_name"` string notation** (Wilkinson formula), not `design_factors`. The formula parser (formulaic) cannot handle column names with spaces or special characters.

**Single-factor designs:**
```python
design = "~condition"  # Simple two-group comparison
```

**Multi-factor designs:**
```python
design = "~batch + condition"  # Control for batch effects
design = "~age + condition"     # Include continuous covariate
design = "~group + condition + group:condition"  # Interaction effects
```

**Design formula guidelines:**
- **Always use `design="~column_name"` (string formula notation)** — do NOT use `design_factors` which is a legacy parameter
- **Rename metadata columns that contain spaces or special characters** to use underscores before passing to DeseqDataSet. Example: `metadata.columns = metadata.columns.str.replace(' ', '_')`
- Use Wilkinson formula notation (R-style): `"~condition"`, `"~batch + condition"`
- Put adjustment variables (e.g., batch) before the main variable of interest
- Ensure variables exist as columns in the metadata DataFrame
- Use appropriate data types (categorical for discrete variables)
- The contrast values should still use the original data values (e.g., `'non-viral sepsis patient'`), even if the column was renamed — only the column NAME matters for formula parsing

### Step 3: DESeq2 Fitting

Initialize the DeseqDataSet and run the complete pipeline:

```python
from pydeseq2.dds import DeseqDataSet

dds = DeseqDataSet(
    counts=counts_df,
    metadata=metadata,
    design="~condition",
    refit_cooks=True,  # Refit after removing outliers
    n_cpus=1           # Parallel processing (adjust as needed)
)

# Run the complete DESeq2 pipeline
dds.deseq2()
```

**What `deseq2()` does:**
1. Computes size factors (normalization)
2. Fits genewise dispersions
3. Fits dispersion trend curve
4. Computes dispersion priors
5. Fits MAP dispersions (shrinkage)
6. Fits log fold changes
7. Calculates Cook's distances (outlier detection)
8. Refits if outliers detected (optional)

### Step 4: Statistical Testing

Perform Wald tests to identify differentially expressed genes:

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

## Common Analysis Patterns

### Two-Group Comparison

Standard case-control comparison:

```python
dds = DeseqDataSet(counts=counts_df, metadata=metadata, design="~condition")
dds.deseq2()

ds = DeseqStats(dds, contrast=["condition", "treated", "control"])
ds.summary()

results = ds.results_df
significant = results[results.padj < 0.05]
```

### Multiple Comparisons

Testing multiple treatment groups against control:

```python
dds = DeseqDataSet(counts=counts_df, metadata=metadata, design="~condition")
dds.deseq2()

treatments = ["treatment_A", "treatment_B", "treatment_C"]
all_results = {}

for treatment in treatments:
    ds = DeseqStats(dds, contrast=["condition", treatment, "control"])
    ds.summary()
    all_results[treatment] = ds.results_df

    sig_count = len(ds.results_df[ds.results_df.padj < 0.05])
    print(f"{treatment}: {sig_count} significant genes")
```

### Accounting for Batch Effects

Control for technical variation:

```python
# Include batch in design
dds = DeseqDataSet(counts=counts_df, metadata=metadata, design="~batch + condition")
dds.deseq2()

# Test condition while controlling for batch
ds = DeseqStats(dds, contrast=["condition", "treated", "control"])
ds.summary()
```

### Continuous Covariates

Include continuous variables like age or dosage:

```python
# Ensure continuous variable is numeric
metadata["age"] = pd.to_numeric(metadata["age"])

dds = DeseqDataSet(counts=counts_df, metadata=metadata, design="~age + condition")
dds.deseq2()

ds = DeseqStats(dds, contrast=["condition", "treated", "control"])
ds.summary()
```

## Using the Analysis Script

This skill includes a complete command-line script for standard analyses:

```bash
# Basic usage
python scripts/run_deseq2_analysis.py \
  --counts counts.csv \
  --metadata metadata.csv \
  --design "~condition" \
  --contrast condition treated control \
  --output results/

# With additional options
python scripts/run_deseq2_analysis.py \
  --counts counts.csv \
  --metadata metadata.csv \
  --design "~batch + condition" \
  --contrast condition treated control \
  --output results/ \
  --min-counts 10 \
  --alpha 0.05 \
  --n-cpus 4 \
  --plots
```

**Script features:**
- Automatic data loading and validation
- Gene and sample filtering
- Complete DESeq2 pipeline execution
- Statistical testing with customizable parameters
- Result export (CSV, pickle)
- Optional visualization (volcano and MA plots)

Refer users to `scripts/run_deseq2_analysis.py` when they need a standalone analysis tool or want to batch process multiple datasets.

## Result Interpretation

### Identifying Significant Genes

```python
# Filter by adjusted p-value
significant = ds.results_df[ds.results_df.padj < 0.05]

# Filter by both significance and effect size
sig_and_large = ds.results_df[
    (ds.results_df.padj < 0.05) &
    (abs(ds.results_df.log2FoldChange) > 1)
]

# Separate up- and down-regulated
upregulated = significant[significant.log2FoldChange > 0]
downregulated = significant[significant.log2FoldChange < 0]

print(f"Upregulated: {len(upregulated)}")
print(f"Downregulated: {len(downregulated)}")
```

### Ranking and Sorting

```python
# Sort by adjusted p-value
top_by_padj = ds.results_df.sort_values("padj").head(20)

# Sort by absolute fold change (use shrunk values)
ds.lfc_shrink()
ds.results_df["abs_lfc"] = abs(ds.results_df.log2FoldChange)
top_by_lfc = ds.results_df.sort_values("abs_lfc", ascending=False).head(20)

# Sort by a combined metric
ds.results_df["score"] = -np.log10(ds.results_df.padj) * abs(ds.results_df.log2FoldChange)
top_combined = ds.results_df.sort_values("score", ascending=False).head(20)
```

### Quality Metrics

```python
# Check normalization (size factors should be close to 1)
print("Size factors:", dds.obsm["size_factors"])

# Examine dispersion estimates
import matplotlib.pyplot as plt
plt.hist(dds.varm["dispersions"], bins=50)
plt.xlabel("Dispersion")
plt.ylabel("Frequency")
plt.title("Dispersion Distribution")
plt.show()

# Check p-value distribution (should be mostly flat with peak near 0)
plt.hist(ds.results_df.pvalue.dropna(), bins=50)
plt.xlabel("P-value")
plt.ylabel("Frequency")
plt.title("P-value Distribution")
plt.show()
```

## Visualization Guidelines

**REQUIRED visualizations for every DESeq2 analysis (always produce ALL of these):**
1. **PCA plot** — sample clustering to verify condition separation and detect outliers/batch effects
2. **Volcano plot** — significance vs effect size overview
3. **Heatmap** (optional but recommended) — expression patterns of top DEGs
4. **MA plot** (optional) — fold change vs mean expression diagnostic

The PCA plot must be generated immediately after fitting the DESeq2 model (after `dds.deseq2()`) and BEFORE statistical testing, as it serves as a critical quality-control step. If samples do not cluster by experimental condition, the downstream DE results may be unreliable and the design formula may need revision (e.g., adding a batch covariate).

### Volcano Plot

Visualize significance vs effect size. **Upregulated genes are red, downregulated genes are blue.** Axes are tightened to the actual data max (not quantiles) to avoid unnecessary whitespace.

```python
import matplotlib.pyplot as plt
import numpy as np
from adjustText import adjust_text

results = ds.results_df.copy()

fig, ax = plt.subplots(figsize=(10, 8))

# Non-significant (grey)
ns = results[~((results['padj'] < 0.05) & (results['log2FoldChange'].abs() > 1))]
ax.scatter(ns['log2FoldChange'], -np.log10(ns['pvalue']),
           alpha=0.3, s=5, c='grey', label='Not significant')

# Upregulated (red)
sig_up = results[(results['padj'] < 0.05) & (results['log2FoldChange'] > 1)]
ax.scatter(sig_up['log2FoldChange'], -np.log10(sig_up['pvalue']),
           alpha=0.6, s=15, c='red', label=f'Upregulated ({len(sig_up)})')

# Downregulated (blue)
sig_down = results[(results['padj'] < 0.05) & (results['log2FoldChange'] < -1)]
ax.scatter(sig_down['log2FoldChange'], -np.log10(sig_down['pvalue']),
           alpha=0.6, s=15, c='blue', label=f'Downregulated ({len(sig_down)})')

# Label top genes
texts = []
for idx, row in results.sort_values('padj').head(15).iterrows():
    texts.append(ax.text(row['log2FoldChange'], -np.log10(row['pvalue']), idx, fontsize=7))
adjust_text(texts, arrowprops=dict(arrowstyle='-', color='black', lw=0.5))

# Threshold lines
ax.axhline(-np.log10(0.05), color='black', linestyle='--', alpha=0.4, lw=0.8)
ax.axvline(1, color='black', linestyle='--', alpha=0.4, lw=0.8)
ax.axvline(-1, color='black', linestyle='--', alpha=0.4, lw=0.8)

# Tighten axes to actual data max (NOT quantiles — quantiles clip the most significant genes)
neg_log10p = -np.log10(results['pvalue'])
neg_log10p_finite = neg_log10p[np.isfinite(neg_log10p)]
xlim = results['log2FoldChange'].abs().max() * 1.05
ylim = neg_log10p_finite.max() * 1.05
ax.set_xlim(-xlim, xlim)
ax.set_ylim(-0.5, ylim)

ax.set_xlabel('log2 Fold Change')
ax.set_ylabel('-log10(p-value)')
ax.set_title('Volcano Plot')
ax.legend(loc='upper right')
plt.tight_layout()
plt.savefig("volcano_plot.png", dpi=300)
plt.show()
```

**Key rules for volcano plots:**
- Upregulated genes (log2FC > 1, padj < 0.05): **red**
- Downregulated genes (log2FC < -1, padj < 0.05): **blue**
- Non-significant: grey
- Y-axis uses `-log10(pvalue)` (raw p-value), NOT padj
- Axis limits use `min() * 1.05` or `max() * 1.05` of finite values — never use `quantile()` which clips the most significant points
- Include threshold dashed lines at log2FC = ±1 and -log10(0.05)

### PCA Plot (MANDATORY)

**Always include a PCA plot in every DESeq2 analysis.** This is a critical QC step that must be generated after model fitting (`dds.deseq2()`) and before interpreting DE results. It reveals whether samples cluster by experimental condition, detects outliers, and exposes confounding batch effects that would invalidate downstream results. Run PCA on variance-stabilized (log-transformed) counts.

```python
import matplotlib.pyplot as plt
import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# Variance-stabilizing transform: log2(normalized_counts + 1)
# Use size-factor-normalized counts from the fitted dds object
size_factors = dds.obsm["size_factors"]
normalized_counts = counts_filtered / size_factors[:, None]
log_counts = np.log2(normalized_counts + 1)

# PCA on top 500 most variable genes
gene_var = log_counts.var(axis=0)
top_var_genes = gene_var.nlargest(500).index
log_counts_top = log_counts[top_var_genes]

# Fit PCA
scaler = StandardScaler()
scaled = scaler.fit_transform(log_counts_top)
pca = PCA(n_components=2)
pcs = pca.fit_transform(scaled)

# Plot
fig, ax = plt.subplots(figsize=(8, 6))
groups = metadata_aligned[condition_col].unique()
colors = ['red', 'blue', 'green', 'orange', 'purple'][:len(groups)]

for group, color in zip(groups, colors):
    mask = metadata_aligned[condition_col] == group
    ax.scatter(pcs[mask, 0], pcs[mask, 1],
              c=color, s=80, alpha=0.8, edgecolors='black', linewidths=0.5,
              label=group)
    # Label each sample
    for i, name in enumerate(metadata_aligned.index[mask]):
        ax.annotate(name, (pcs[mask, 0][i], pcs[mask, 1][i]),
                    fontsize=7, ha='left', va='bottom')

ax.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]*100:.1f}% variance)')
ax.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]*100:.1f}% variance)')
ax.set_title('PCA — Sample Clustering')
ax.legend()
plt.tight_layout()
plt.savefig("pca_plot.png", dpi=300)
plt.show()
```

**Diagnostic use:**
- Samples should cluster by experimental condition (not by batch)
- Outlier samples far from their group may need removal or investigation
- If samples cluster by batch instead of condition, add batch to the design formula (`"~batch + condition"`)

### Heatmap

Show expression patterns of top DEGs across samples. Use z-scored log-normalized counts.

```python
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

# Select top DEGs (by padj)
top_n = 50
top_genes = ds.results_df.sort_values('padj').head(top_n).index.tolist()

# Log-normalized counts for heatmap
size_factors = dds.obsm["size_factors"]
normalized_counts = counts_filtered / size_factors[:, None]
log_counts = np.log2(normalized_counts + 1)

# Subset to top genes and z-score across samples (rows = genes)
heatmap_data = log_counts[top_genes].T  # genes × samples → need genes as rows
# Z-score each gene across samples
heatmap_z = (heatmap_data - heatmap_data.mean(axis=1).values[:, None]) / heatmap_data.std(axis=1).values[:, None]

# Create annotation colors for conditions
condition_colors = metadata_aligned[condition_col].map(
    dict(zip(metadata_aligned[condition_col].unique(), ['red', 'blue', 'green', 'orange'][:metadata_aligned[condition_col].nunique()]))
)

# Plot clustered heatmap
g = sns.clustermap(
    heatmap_z,
    cmap='RdBu_r',
    center=0,
    vmin=-2, vmax=2,
    col_colors=condition_colors,
    figsize=(10, 12),
    dendrogram_ratio=(0.1, 0.15),
    xticklabels=True,
    yticklabels=True,
    linewidths=0,
    cbar_kws={'label': 'Z-score'}
)
g.ax_heatmap.set_yticklabels(g.ax_heatmap.get_yticklabels(), fontsize=6)
g.ax_heatmap.set_xticklabels(g.ax_heatmap.get_xticklabels(), fontsize=8)
g.fig.suptitle(f'Top {top_n} DEGs — Clustered Heatmap', y=1.01)
plt.savefig("heatmap_top_degs.png", dpi=300, bbox_inches='tight')
plt.show()
```

**Diagnostic use:**
- Confirm that top DEGs show clear separation between conditions
- Identify genes with outlier expression in individual samples
- Hierarchical clustering of samples (columns) should recapitulate the experimental groups
- If samples don't cluster by condition, re-examine the experimental design or check for confounders

### MA Plot

Show fold change vs mean expression to diagnose expression-dependent bias. Uses the same red/blue color scheme as the volcano plot.

```python
import matplotlib.pyplot as plt
import numpy as np

results = ds.results_df.copy()

fig, ax = plt.subplots(figsize=(10, 6))

# Non-significant (grey)
ns = results[~((results['padj'] < 0.05) & (results['log2FoldChange'].abs() > 1))]
ax.scatter(np.log10(ns['baseMean'] + 1), ns['log2FoldChange'],
           alpha=0.3, s=5, c='grey', label='Not significant')

# Upregulated (red)
sig_up = results[(results['padj'] < 0.05) & (results['log2FoldChange'] > 1)]
ax.scatter(np.log10(sig_up['baseMean'] + 1), sig_up['log2FoldChange'],
           alpha=0.6, s=15, c='red', label=f'Upregulated ({len(sig_up)})')

# Downregulated (blue)
sig_down = results[(results['padj'] < 0.05) & (results['log2FoldChange'] < -1)]
ax.scatter(np.log10(sig_down['baseMean'] + 1), sig_down['log2FoldChange'],
           alpha=0.6, s=15, c='blue', label=f'Downregulated ({len(sig_down)})')

ax.axhline(0, color='black', linestyle='--', alpha=0.4, lw=0.8)
ax.axhline(1, color='black', linestyle=':', alpha=0.3, lw=0.6)
ax.axhline(-1, color='black', linestyle=':', alpha=0.3, lw=0.6)

# Tighten axes: use small FIXED padding, not multiplicative (% padding over-expands large ranges)
log10_basemean = np.log10(results['baseMean'] + 1)
ax.set_xlim(log10_basemean.min() * 1.05, log10_basemean.max() * 1.05)
ax.set_ylim(results['log2FoldChange'].min() * 1.05, results['log2FoldChange'].max() * 1.05)

ax.set_xlabel('log10(Base Mean + 1)')
ax.set_ylabel('log2 Fold Change')
ax.set_title('MA Plot')
ax.legend(loc='upper left')
plt.tight_layout()
plt.savefig("ma_plot.png", dpi=300)
plt.show()
```

**Key rules for MA plots:**
- X-axis: `log10(baseMean + 1)` — use `.min()` and `.max()` for limits
- Y-axis: `log2FoldChange` — use `.min()` and `.max()` for limits
- Never use `quantile()` for axis limits — use actual `min()`/`max()` to show all data points

**Diagnostic use:**
- The point cloud should be centered around log2FC = 0 (no systematic bias)
- If the cloud is shifted up or down, normalization may have failed
- Highly significant genes at low expression (left side) may be unreliable — check with `independent_filter=True`
- "Funnel" shape (wider spread at low expression) is expected due to higher variance at low counts

## Troubleshooting Common Issues

### Data Format Problems

**Issue:** "Index mismatch between counts and metadata"

**Solution:** Ensure sample names match exactly
```python
print("Counts samples:", counts_df.index.tolist())
print("Metadata samples:", metadata.index.tolist())

# Take intersection if needed
common = counts_df.index.intersection(metadata.index)
counts_df = counts_df.loc[common]
metadata = metadata.loc[common]
```

**Issue:** "All genes have zero counts"

**Solution:** Check if data needs transposition
```python
print(f"Counts shape: {counts_df.shape}")
# If genes > samples, transpose is needed
if counts_df.shape[1] < counts_df.shape[0]:
    counts_df = counts_df.T
```

### Design Matrix Issues

**Issue:** `FormulaSyntaxError: Missing operator between X and Y`

**Cause:** Column name has spaces (e.g., `"subject status"`). The formulaic parser treats spaces as missing operators.

**Solution:** Rename metadata columns to replace spaces with underscores BEFORE creating DeseqDataSet:
```python
# Fix column names with spaces
metadata.columns = metadata.columns.str.replace(' ', '_')
condition_col = 'subject_status'  # use the renamed column

# Use design= string notation, NOT design_factors
dds = DeseqDataSet(
    counts=counts_df,
    metadata=metadata,
    design=f"~{condition_col}",  # formula notation
    refit_cooks=True
)
```

**Issue:** "Design matrix is not full rank"

**Cause:** Confounded variables (e.g., all treated samples in one batch)

**Solution:** Remove confounded variable or add interaction term
```python
# Check confounding
print(pd.crosstab(metadata.condition, metadata.batch))

# Either simplify design or add interaction
design = "~condition"  # Remove batch
# OR
design = "~condition + batch + condition:batch"  # Model interaction
```

### No Significant Genes

**Diagnostics:**
```python
# Check dispersion distribution
plt.hist(dds.varm["dispersions"], bins=50)
plt.show()

# Check size factors
print(dds.obsm["size_factors"])

# Look at top genes by raw p-value
print(ds.results_df.nsmallest(20, "pvalue"))
```

**Possible causes:**
- Small effect sizes
- High biological variability
- Insufficient sample size
- Technical issues (batch effects, outliers)

## Reference Documentation

For comprehensive details beyond this workflow-oriented guide:

- **API Reference** (`references/api_reference.md`): Complete documentation of PyDESeq2 classes, methods, and data structures. Use when needing detailed parameter information or understanding object attributes.

- **Workflow Guide** (`references/workflow_guide.md`): In-depth guide covering complete analysis workflows, data loading patterns, multi-factor designs, troubleshooting, and best practices. Use when handling complex experimental designs or encountering issues.

Load these references into context when users need:
- Detailed API documentation: `Read references/api_reference.md`
- Comprehensive workflow examples: `Read references/workflow_guide.md`
- Troubleshooting guidance: `Read references/workflow_guide.md` (see Troubleshooting section)

## Key Reminders

1. **Data orientation matters:** Count matrices typically load as genes × samples but need to be samples × genes. Always transpose with `.T` if needed.

2. **Sample filtering:** Remove samples with missing metadata before analysis to avoid errors.

3. **Gene filtering:** Filter low-count genes (e.g., < 10 total reads) to improve power and reduce computational time.

4. **Design formula order:** Put adjustment variables before the variable of interest (e.g., `"~batch + condition"` not `"~condition + batch"`).

5. **ALWAYS use `design="~col"` string notation** — never `design_factors`. Rename columns with spaces to underscores first (`metadata.columns = metadata.columns.str.replace(' ', '_')`).

5. **LFC shrinkage timing:** Apply shrinkage after statistical testing and only for visualization/ranking purposes. P-values remain based on unshrunken estimates.

6. **Result interpretation:** Use `padj < 0.05` for significance, not raw p-values. The Benjamini-Hochberg procedure controls false discovery rate.

7. **Contrast specification:** The format is `[variable, test_level, reference_level]` where test_level is compared against reference_level.

8. **Save intermediate objects:** Use pickle to save DeseqDataSet objects for later use or additional analyses without re-running the expensive fitting step.

## Installation and Requirements

PyDESeq2 can be installed via pip or conda:

```bash
# Via pip
pip install pydeseq2

# Via conda
conda install -c bioconda pydeseq2
```

**System requirements:**
- Python 3.10-3.11
- pandas 1.4.3+
- numpy 1.23.0+
- scipy 1.11.0+
- scikit-learn 1.1.1+
- anndata 0.8.0+

**Optional for visualization:**
- matplotlib
- seaborn

## Additional Resources
- Adapted [**PyDESeq2** skill](https://mcpmarket.com/tools/skills/pydeseq2-gene-expression-analysis) 1.0.0 from MCP Market to Databricks
- **Official Documentation:** https://pydeseq2.readthedocs.io
- **GitHub Repository:** https://github.com/owkin/PyDESeq2
- **Publication:** Muzellec et al. (2023) Bioinformatics, DOI: 10.1093/bioinformatics/btad547
- **Original DESeq2 (R):** Love et al. (2014) Genome Biology, DOI: 10.1186/s13059-014-0550-8
