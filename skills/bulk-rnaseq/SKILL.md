---
name: bulk-rnaseq
description: PyDESeq2 differential expression for bulk RNA-seq. Counts + metadata → Wald tests, FDR, optional apeGLM shrinkage, PCA/volcano/MA plots. For pathway enrichment of DE results use pathway-enrichment-analysis.
author: Yen Low
version: 0.2
license: Databricks
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
pip install "pydeseq2>=0.5"
# or: conda install -c bioconda pydeseq2
```

Snippets here are verified against pydeseq2 0.5.4. The storage location of size factors and normalized counts changed between releases, so the workflow reads `dds.layers["normed_counts"]`, which is stable across 0.4 and 0.5.

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

normalized_counts = pd.DataFrame(
    dds.layers["normed_counts"], index=dds.obs_names, columns=dds.var_names
)
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

## Evaluation
All 35 unit [tests](./tests) passed (`pytest skills/bulk-rnaseq/tests`).

### Standardized paired eval (skill-eval pipeline, 2026-09-15)

**Setup**: 4 benchmark tasks (easy/hard/hard/edge) on synthetic bulk RNA-seq data with 60 planted DE genes (ground truth known), run with and without the skill on a serverless job. Scored with MLflow 3 `mlflow.genai.evaluate`: 9 deterministic scorers (artifact/schema/planted-truth thresholds) + 1 binary judge (`task_completion`, gpt-5-mini).

**Results** (deterministic scorers; artifact booleans were verified by the executing agent against the produced files, not independently re-inspected):

| task_id | difficulty | baseline | with skill | outcome |
|---------|-----------|----------|------------|---------|
| se-001 | easy | pass | pass | tie-pass |
| se-002 | hard (batch) | pass | pass | tie-pass |
| se-003 | hard (full workflow; no planted threshold set) | pass | pass | tie-pass |
| se-004 | edge (column name with a space) | pass | pass | tie-pass |

`planted_check` is a threshold test, so the committed score files record only whether each run cleared the planted-gene bar, not how many genes it recovered.

Final-output parity: 4/4 tie-pass. Both arms completed every task with pydeseq2 and used the correct designs (`~batch + condition` for se-002).

**First-attempt reliability** (read off the run transcripts, not derivable from the committed score files): baseline 4/4 first-attempt success, with skill 2/4 — the with-skill arm hit `KeyError: 'size_factors'` on se-002/se-003 because the Step 4 PCA snippet read `dds.obsm["size_factors"]`, which current pydeseq2 does not populate (size factors live in `dds.obs`, normalized counts in `dds.layers["normed_counts"]`). **Fixed in v0.2**: Step 4 now reads `dds.layers["normed_counts"]` directly, and the same stale reference was corrected in `references/workflow_guide.md` and `references/api_reference.md`. The reliability numbers above are pre-fix and have not been re-measured.

**Failure taxonomy**:

| failure mode | count | arm | status |
|--------------|-------|-----|--------|
| stale-skill-snippet (size_factors location) | 2 tasks | with skill | fixed in v0.2 |
| judge-unverifiable-evidence | 6/8 rows | both | judge design issue, not a skill issue — the judge demanded file contents it cannot access |

**Verdict**: tie on final outputs, which fails the default ship gate (it requires at least one win). The base model already handles this domain well; the skill's value on these tasks is convention consistency (plots, exports, design formulas), not task success. Judge scores were **excluded pending human-label validation** — rationale inspection showed the judge grading narrative verifiability rather than completion (a judge-spec error, since corrected in skill-eval's scorer pack), so its TPR/TNR is unknown.

**Limitations**: 4 tasks, one dataset family (synthetic negative-binomial counts) — directional only. A discriminating eval needs harder tasks: messier real data, multi-factor designs, larger scale, or tasks where naive DESeq2 usage fails.

**Reproduce**: evalset, difficulty map, and both score files are at `skills/skill-eval/assets/dogfood-bulk-rnaseq/`. Comparison:

```bash
python3 skills/skill-eval/scripts/compare_runs.py \
  skills/skill-eval/assets/dogfood-bulk-rnaseq/baseline_scores.json \
  skills/skill-eval/assets/dogfood-bulk-rnaseq/with_skill_scores.json \
  --difficulty skills/skill-eval/assets/dogfood-bulk-rnaseq/difficulties.json
```

The persisted score files still include the unvalidated judge metric (`task_completion`), so that command prints `1 win | 1 regression | 2 tie-fail` and `SHIP GATE FAIL (regressions: se-004 (edge))`. Both the win and the regression come from the judge alone.

Drop `task_completion` from both files and the same command prints `0 wins | 0 regressions | 4 tie-pass` and `SHIP GATE FAIL (no wins)`. That is the honest reading of this eval. On the deterministic scorers the skill neither helped nor hurt the final output, and a tie does not clear a gate that requires a win.

### Manual comparison vs publication

#### Comparison of code generated without and with skill
Data and results sourced from [Campbell et al., J Clin Invest. 2022;132(23):e153014](https://pmc.ncbi.nlm.nih.gov/articles/PMC9711880) identifying DEG in patients with non-viral sepsis (vs healthy)
| Dimension | Without Skills | With skills | [Paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9711880/) |
|-----------|----------------|-------------|-------|
| Packages  | GEOparse gseapy scipy statsmodels | pydeseq2 gseapy GEOparse adjustText networkx | R: DESeq |
| DEG method | Welch t-test | PyDESeq2 | R's DESeq2 |
| Genes tested | 13732 (counts>10, samples>3) | 17,085 (counts>10) | 17,101 (counts>5) |
| Significant DEGs | 38 (FDR<0.05, abs log2FC>1) | 1,210 (padj<0.05, abs log2FC>1) | 1208 (FDR<0.05) |
| QC | None | PCA | PCA |
| Top DEGs | 0 paper-reported DEGs among sig. DEGs | 4/6 paper-reported DEGs among top 10 DEGs | IFITM3, IFITM2, IFITM1, HPSE, LGALS3BP, SELENBP1 |
| Pathway analysis | ORA (KEGG, GO, Reactome) | GSEA Prerank (MSigDB Hallmark, KEGG) — statistically stronger; no arbitrary cutoff | Lab validation, not enrichment analysis |
| Visualizations | Volcano plot only | PCA, volcano (with adjustText), NES barplot, network enrichment map, GSEA enrichment curves (top 3) | PCA, volcano, heatmap, IGV |

Takeaways: 
* With skills, the significant DEGs (1210) largely agree with those in the paper (1208). Slight differences may arise from the DESeq2 implementation in Python in the former and in R in the latter. Also they were tested on slightly different genes due to the former using default count thresholds (<10) while the latter used count<5.
* With skills, GSEA prerank captures the complement/coagulation and ribosome/translational angles more precisely, but misses the platelet-specific terms that the no-skills ORA finds.
* The irony: the no-skills notebook's underpowered DEG method (only 38 genes) actually produces a more focused gene list for ORA, which happens to enrich for platelet-specific biology — exactly what the paper is about. Analysis with skills finds 1,210 DEGs (matching the paper's count), but the broader gene list dilutes the platelet signal in GSEA.
* Because the paper's suggested pathways are expert-inferred and then validated in the lab, the discovery process differs considerably from typical computational pathway enrichment methods (ORA or GSEA) and thus, it can be difficult to definitively compare either enrichment method to the paper's results.


## Guardrails

1. Verify counts orientation (samples × genes after load) before fitting — transpose genes × samples files.
2. Use `design="~col"` string notation only; rename metadata columns containing spaces before fitting.
3. Report unshrunken p-values for significance; use shrunk LFCs only for visualization and ranking.
4. Do not retry a failing fit more than 3 times — read the error (see Troubleshooting) first.
5. Confirm with the user before running on matrices larger than ~50k genes × 100 samples.

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
