---
name: "gseapy-gene-enrichment"
description: "GSEA and over-representation analysis (ORA) for RNA-seq and proteomics. Wraps Enrichr for ORA against MSigDB, KEGG, GO, and 200+ databases; runs preranked GSEA on ranked DE gene lists. Outputs enrichment tables and running-score plots. Use after DESeq2 or edgeR for pathway-level interpretation."
license: "MIT"
---

# GSEApy — Gene Set Enrichment Analysis in Python

## Overview

GSEApy provides Python implementations of GSEA and over-representation analysis (ORA) for interpreting gene expression changes at the pathway level. The `enrich` module queries the Enrichr API to test a gene list against 200+ databases (GO, KEGG, MSigDB Hallmarks, Reactome, WikiPathways). The `prerank` and `gsea` modules run the GSEA algorithm on a pre-ranked gene list or expression matrix — computing normalized enrichment scores (NES) and FDR values for each gene set. GSEApy integrates directly with pandas DataFrames from DESeq2 or scanpy differential expression output, making it the standard Python tool for pathway analysis in RNA-seq workflows.

## When to Use

- Interpreting DESeq2 or edgeR differential expression results at pathway/GO-term level
- Running fast ORA (over-representation analysis) against Enrichr's 200+ databases including GO, KEGG, and MSigDB Hallmarks
- Performing GSEA prerank analysis on a log2-fold-change-ranked gene list without an expression matrix
- Identifying enriched pathways in scRNA-seq cluster marker genes
- Generating publication-ready enrichment dot plots and GSEA running-score plots

## Analysis Method Selection: ORA vs GSEA

**ALWAYS decide which method to use BEFORE running any enrichment analysis.** The choice depends on the input data and the biological question:

| Criterion | ORA (`gp.enrichr`) | GSEA Prerank (`gp.prerank`) |
|-----------|-------------------|-----------------------------|
| **Input** | A discrete gene list (e.g., significant DEGs) | A ranked list of ALL tested genes (e.g., log2FC) |
| **When to use** | You have a clear significance threshold and want to test a curated hit list | You want to detect coordinated pathway-level shifts even when individual genes are modest |
| **Typical source** | DESeq2 `padj < 0.05 & abs(log2FC) > 1` subset | DESeq2 full `log2FoldChange` column (all genes, sorted descending) |
| **Strength** | Simple, fast, interpretable for focused gene lists | Captures subtle distributed signals; no arbitrary cutoff needed |
| **Weakness** | Ignores magnitude; depends on threshold choice; misses genes just below cutoff | Slower (permutation-based); results sensitive to ranking metric |
| **Significance metric** | Adjusted P-value < 0.05 | FDR q-val < 0.25 (standard GSEA threshold) |
| **Directional split** | Run SEPARATELY on up- and down-regulated gene lists | Handles both directions in one run (positive NES = up, negative NES = down) |

**Decision rules:**
1. **Default to GSEA Prerank** when you have full DE results with log2FC values — it is more powerful and avoids arbitrary cutoff bias.
2. **Use ORA** when (a) you only have a gene list without ranks (e.g., cluster markers from scRNA-seq), (b) you want quick hypothesis validation of a specific gene set, or (c) the user explicitly requests ORA/Enrichr.
3. **Run BOTH** when the user asks for comprehensive analysis — ORA on the significant subset for discrete pathway hits, plus GSEA Prerank on the full ranked list for subtle coordinated changes.
4. **Never use `gp.gsea()` (standard GSEA with expression matrix)** unless the user explicitly has a raw expression matrix and phenotype labels — `gp.prerank()` is almost always preferred because it separates the DE step from the enrichment step.

## Required Visualization Outputs

**ALWAYS produce these visualizations after running enrichment analysis:**

| Method used | MANDATORY outputs | ONLY when requested |
|-------------|-------------------|---------------------|
| ORA (`gp.enrichr`) | Stratified bar plot (`gp.barplot`) + Network enrichment map | Dot plot (`dotplot`) |
| GSEA Prerank (`gp.prerank`) | Stratified NES bar plot (`gp.barplot` on `res2d`) + GSEA enrichment curves (top 3 terms) + Network enrichment map | Dot plot (`dotplot`) |
| Both ORA + GSEA | All of the above for each | Dot plot |

**Rules:**
- The **stratified bar plot** and **network enrichment map** are ALWAYS generated — do not skip them.
- The **dot plot** is generated ONLY when the user explicitly requests it (e.g., "show a dotplot", "make a dot plot").
- The **GSEA enrichment curve** (running score plot) is MANDATORY whenever GSEA is used — show the top 3 enriched gene sets.
- All bar plots and dot plots must use `gseapy`'s built-in plotting functions (`gp.barplot`, `gseapy.plot.dotplot`) — NOT seaborn or matplotlib bar charts.

## Prerequisites

- **Python packages**: `gseapy`, `pandas`, `matplotlib`, `networkx` (for enrichment map)
- **Internet access**: `enrich` module queries the Enrichr API (requires connection)

```bash
pip install gseapy

# Verify
python -c "import gseapy; print(gseapy.__version__)"
# 1.1.3
```

## Quick Start

```python
import gseapy as gp

# ORA: test a gene list against GO Biological Process
gene_list = ["TP53", "BRCA1", "CDK2", "CCND1", "MYC", "EGFR", "KRAS", "PTEN"]

enr = gp.enrichr(gene_list=gene_list,
                 gene_sets=["GO_Biological_Process_2023"],
                 organism="human",
                 outdir=None)
print(enr.results.head(5)[["Term", "P-value", "Adjusted P-value", "Genes"]])
```

## Workflow

### Step 1: Over-Representation Analysis with Enrichr (ORA)

Test a gene list against pathway databases via the Enrichr API.

```python
import gseapy as gp
import pandas as pd

# Gene list from DESeq2 (significant upregulated genes)
sig_genes = ["TP53", "BRCA1", "CDK2", "CCND1", "MYC", "EGFR",
             "KRAS", "PTEN", "RB1", "AKT1", "PIK3CA", "MDM2"]

# Run ORA against multiple databases
enr = gp.enrichr(
    gene_list=sig_genes,
    gene_sets=[
        "GO_Biological_Process_2023",
        "KEGG_2021_Human",
        "MSigDB_Hallmark_2020",
        "Reactome_2022",
    ],
    organism="human",
    outdir="enrichr_results/",
    cutoff=0.05,
)

# Display top results
results = enr.results
print(f"Enriched terms: {len(results[results['Adjusted P-value'] < 0.05])}")
print(results[results["Adjusted P-value"] < 0.05].sort_values("Adjusted P-value")
      .head(10)[["Gene_set", "Term", "Adjusted P-value", "Combined Score"]])
```

### Step 2: List Available Gene Set Databases

Discover the 200+ databases available through Enrichr.

```python
import gseapy as gp

# List all available gene set libraries
libraries = gp.get_library_name(organism="human")
print(f"Available databases: {len(libraries)}")
print("Selected databases:")
for lib in sorted(libraries):
    if any(kw in lib for kw in ["GO_Bio", "KEGG", "Hallmark", "Reactome"]):
        print(f"  {lib}")

# Mouse databases
mouse_libs = gp.get_library_name(organism="mouse")
print(f"\nMouse databases: {len(mouse_libs)}")
```

### Step 3: GSEA Prerank — Ranked Gene List Analysis

Run GSEA on a log2 fold-change ranked gene list from differential expression.

```python
import gseapy as gp
import pandas as pd
import numpy as np

# Load DESeq2 results (or create example ranked list)
# deseq_results = pd.read_csv("deseq2_results.tsv", sep="\t", index_col=0)
# ranked = deseq_results["log2FoldChange"].dropna().sort_values(ascending=False)

# Example ranked gene list (gene → log2FC)
np.random.seed(42)
gene_names = [f"GENE_{i}" for i in range(1000)]
log2fc = np.random.normal(0, 2, 1000)
ranked = pd.Series(log2fc, index=gene_names).sort_values(ascending=False)

# Run preranked GSEA against MSigDB Hallmarks
pre_res = gp.prerank(
    rnk=ranked,
    gene_sets="MSigDB_Hallmark_2020",
    threads=4,
    min_size=15,
    max_size=500,
    permutation_num=1000,
    outdir="gsea_results/prerank/",
    seed=42,
    verbose=True,
)

# View results
res_df = pre_res.res2d
sig = res_df[res_df["FDR q-val"] < 0.25]
print(f"Significant gene sets (FDR < 0.25): {len(sig)}")
print(sig.sort_values("NES", ascending=False)[["Term", "NES", "NOM p-val", "FDR q-val"]].head(10))
```

### Step 4: GSEA Enrichment Curve / Running Score (MANDATORY when GSEA is used)

**Always produce enrichment curves for the top 3 enriched gene sets** whenever GSEA Prerank is run. This shows how the enrichment score accumulates along the ranked gene list and is the canonical GSEA visualization.

```python
import gseapy as gp
from gseapy.plot import gseaplot
import matplotlib.pyplot as plt

# Plot enrichment curves for top 3 gene sets (MANDATORY)
top_terms = pre_res.res2d.sort_values("NES", ascending=False).head(3)['Term'].tolist()

for term in top_terms:
    print(f"\nGSEA Enrichment Curve: {term}")
    gseaplot(
        rank_metric=pre_res.ranking,
        term=term,
        **pre_res.results[term],
    )
    plt.tight_layout()
    plt.show()
```

### Step 5: Enrichment Dot Plot (ONLY WHEN REQUESTED)

Generate a dot plot showing enrichment significance and gene ratio across top pathways. **Only produce this visualization when the user explicitly asks for a dot plot.** Works with both ORA results (`enr.results`) and GSEA Prerank results (`pre_res.res2d`).

```python
import gseapy as gp
import matplotlib.pyplot as plt
from gseapy.plot import dotplot

# Run ORA and plot results
enr = gp.enrichr(
    gene_list=["TP53", "BRCA1", "CDK2", "CCND1", "MYC", "EGFR",
               "KRAS", "PTEN", "RB1", "AKT1", "PIK3CA", "MDM2",
               "BCL2", "CDKN1A", "E2F1", "CCNE1"],
    gene_sets=["KEGG_2021_Human"],
    organism="human",
    outdir=None,
    cutoff=0.05,
)

# Dot plot: x=gene ratio, size=-log10(p), color=adjusted p-value
ax = dotplot(
    enr.results,
    column="Adjusted P-value",
    x="Gene_set",
    title="KEGG Enrichment",
    cmap="viridis_r",
    size=10,
    top_term=15,
    figsize=(6, 8),
    ofname="enrichment_dotplot.pdf",
)
plt.tight_layout()
plt.savefig("enrichment_dotplot.png", dpi=150, bbox_inches="tight")
print("Saved: enrichment_dotplot.png")
```

### Step 6: Stratified Enrichment Bar Plot (MANDATORY)

Visualize top enriched pathways as a horizontal bar plot, color-coded by gene set database. **This is ALWAYS produced** after running enrichment analysis. Works with both ORA and GSEA results.

#### 6a: Bar plot from ORA results

```python
import gseapy as gp
import seaborn as sns

# From ORA (gp.enrichr) results
enr_df = enr.results  # or enr_up.results, enr_dn.results
enr_df_sig = enr_df[enr_df['Adjusted P-value'] < 0.05].sort_values('Adjusted P-value')

# Color map: one color per Gene_set database
gene_set_colors = dict(zip(
    enr_df_sig['Gene_set'].unique(),
    sns.color_palette('Set2', n_colors=enr_df_sig['Gene_set'].nunique())
))

# Stratified bar plot using gseapy's built-in barplot
gp.barplot(
    df=enr_df_sig,
    column='Adjusted P-value',
    group='Gene_set',
    title='ORA: Top Enriched Pathways (Adjusted P < 0.05)',
    figsize=(10, 8),
    color=gene_set_colors
)
plt.tight_layout()
plt.show()
```

#### 6b: NES bar plot from GSEA Prerank results

```python
import gseapy as gp
import seaborn as sns

# From GSEA Prerank results
gsea_df = pre_res.res2d.copy()
gsea_df['NES'] = gsea_df['NES'].astype(float)
gsea_df['FDR q-val'] = gsea_df['FDR q-val'].astype(float)
gsea_sig = gsea_df[gsea_df['FDR q-val'] < 0.25].sort_values('NES', ascending=False)

# Use gp.barplot on GSEA results (column='FDR q-val' for significance axis)
gp.barplot(
    df=gsea_sig,
    column='FDR q-val',
    group='Name',  # gene set database name in prerank results
    title='GSEA Prerank: Enriched Hallmark Gene Sets (FDR < 0.25)',
    figsize=(10, 8),
)
plt.tight_layout()
plt.show()
```

**Key points:**
- `df`: filtered significant results DataFrame
- `column`: the metric for the x-axis — use `'Adjusted P-value'` for ORA, `'FDR q-val'` for GSEA
- `group`: column to stratify bars by — use `'Gene_set'` for ORA, `'Name'` for GSEA prerank
- `color`: dict mapping each group to a color; use `sns.color_palette('Set2', n)` for distinct colors
- The plot automatically shows `-log10(metric)` on the x-axis and pathway terms on y-axis
- **Always use `gp.barplot()`** — never use seaborn or matplotlib barh() for enrichment results

### Step 7: Network Enrichment Map (MANDATORY)

**Always produce a network enrichment map** after enrichment analysis. Visualizes pathway-pathway relationships as a network where nodes are enriched terms and edges represent shared genes. Works with both ORA and GSEA results. Requires `networkx`.

- `enrichment_map()` returns `(nodes_df, edges_df)`
- **nodes_df:** index=`node_idx`, columns: `Term`, `Hits_ratio`, `p_inv`, `Adjusted P-value`
- **edges_df:** columns: `src_idx`, `targ_idx` (NOT `tgt_idx`), `jaccard_coef`, `overlap_coef`, `overlap_genes`

```python
import networkx as nx
from gseapy.plot import enrichment_map

nodes, edges = enrichment_map(enr_df_sig, column='Adjusted P-value', cutoff=0.05, top_term=30)

G = nx.from_pandas_edgelist(edges, source='src_idx', target='targ_idx',
                            edge_attr=['jaccard_coef', 'overlap_coef', 'overlap_genes'])

fig, ax = plt.subplots(figsize=(14, 12))
pos = nx.spring_layout(G, k=1.5, seed=42)
edge_width = nx.get_edge_attributes(G, 'jaccard_coef').values()

nx.draw_networkx_edges(G, pos, width=edge_width, alpha=0.4, edge_color='grey', ax=ax)
sc = nx.draw_networkx_nodes(G, pos,
    node_size=(nodes['Hits_ratio']*1000).tolist(),
    node_color=nodes['p_inv'].tolist(),
    cmap=plt.cm.RdYlBu_r, alpha=0.85, ax=ax, edgecolors='black', linewidths=0.5)

# Wrap long term labels
term_labels = nodes.Term.to_dict()
wrapped = {k: '\n'.join([v[i:i+28] for i in range(0, len(v), 28)]) for k, v in term_labels.items()}
nx.draw_networkx_labels(G, pos, labels=wrapped, font_size=6, ax=ax)

plt.colorbar(sc, ax=ax, shrink=0.6, label='-log10(Adjusted P-value)')
ax.set_title('Enrichment Map (node size=gene ratio, edge width=Jaccard overlap)')
ax.axis('off')
plt.tight_layout()
plt.show()
```

- Node size: `Hits_ratio` (gene overlap fraction); node color: `p_inv` (-log10 adj p-value)
- Edge width: `jaccard_coef` between connected terms
- Tune `k` in `spring_layout` for spacing, `top_term` for network density

### Step 8: Integrate with DESeq2 / scanpy Output

Use GSEApy directly on differential expression results.

```python
import gseapy as gp
import pandas as pd

# From DESeq2 output loaded into Python
# deseq_df = pd.read_csv("deseq2_results.tsv", sep="\t", index_col=0)
# deseq_df = deseq_df.dropna(subset=["log2FoldChange", "padj"])

# Simulate DESeq2 output
import numpy as np
np.random.seed(0)
n = 500
deseq_df = pd.DataFrame({
    "log2FoldChange": np.random.normal(0, 1.5, n),
    "padj": np.random.uniform(0, 1, n),
}, index=[f"GENE{i}" for i in range(n)])

# Significant up/down gene lists for ORA
up_genes = deseq_df[(deseq_df["padj"] < 0.05) & (deseq_df["log2FoldChange"] > 1)].index.tolist()
dn_genes = deseq_df[(deseq_df["padj"] < 0.05) & (deseq_df["log2FoldChange"] < -1)].index.tolist()
print(f"Upregulated: {len(up_genes)}, Downregulated: {len(dn_genes)}")

# ORA on upregulated genes
if up_genes:
    enr_up = gp.enrichr(gene_list=up_genes,
                         gene_sets=["GO_Biological_Process_2023", "KEGG_2021_Human"],
                         organism="human", outdir=None)
    sig_up = enr_up.results[enr_up.results["Adjusted P-value"] < 0.05]
    print(f"Enriched terms (upregulated): {len(sig_up)}")
    print(sig_up.sort_values("Adjusted P-value").head(5)[["Term", "Adjusted P-value"]])

# Preranked GSEA on full ranked list
ranked = deseq_df["log2FoldChange"].sort_values(ascending=False)
pre = gp.prerank(rnk=ranked, gene_sets="MSigDB_Hallmark_2020",
                 threads=4, permutation_num=500, outdir="gsea_out/", seed=42)
print(pre.res2d[pre.res2d["FDR q-val"] < 0.25].sort_values("NES", ascending=False)
      .head(5)[["Term", "NES", "FDR q-val"]])
```

## Key Parameters

| Parameter | Default | Range/Options | Effect |
|-----------|---------|---------------|--------|
| `gene_sets` (enrichr) | required | string or list | Database name(s) from Enrichr; use `gp.get_library_name()` to list |
| `organism` (enrichr) | `"human"` | `"human"`, `"mouse"`, `"fly"`, `"fish"`, `"worm"`, `"yeast"` | Species for gene set lookup |
| `cutoff` (enrichr) | `0.05` | 0–1 | Adjusted p-value cutoff for filtering results |
| `rnk` (prerank) | required | pd.Series | Gene → score mapping; sorted descending (log2FC recommended) |
| `permutation_num` (prerank) | `1000` | 100–10000 | Permutations for p-value estimation; 1000 for publication |
| `min_size` (prerank) | `15` | 5–50 | Minimum gene set size; filters small/poorly characterized sets |
| `max_size` (prerank) | `500` | 100–2000 | Maximum gene set size; filters very large generic sets |
| `threads` (prerank) | `4` | 1–64 | CPU threads for permutation |
| `seed` (prerank) | `None` | integer | Random seed for reproducibility |
| `weighted_score_type` (prerank) | `1` | 0, 1, 1.5 | GSEA weighting; 1 = standard weighted GSEA |

## Common Recipes

### Recipe 1: Compare Enrichment Between Two Conditions

```python
import gseapy as gp
import pandas as pd

conditions = {
    "treated_vs_ctrl": ["TP53", "BRCA1", "CDK2", "CCND1", "MYC"],
    "treated2_vs_ctrl": ["EGFR", "KRAS", "PTEN", "RB1", "AKT1"],
}

results = {}
for label, genes in conditions.items():
    enr = gp.enrichr(gene_list=genes,
                     gene_sets=["MSigDB_Hallmark_2020"],
                     organism="human",
                     outdir=None)
    sig = enr.results[enr.results["Adjusted P-value"] < 0.05]
    results[label] = set(sig["Term"])
    print(f"{label}: {len(sig)} significant Hallmark terms")

# Overlap
shared = results["treated_vs_ctrl"] & results["treated2_vs_ctrl"]
print(f"Shared terms: {shared}")
```

### Recipe 2: Batch Prerank for Multiple Comparisons

```python
import gseapy as gp
import pandas as pd
from pathlib import Path

# Load multiple DESeq2 result files
comparisons = {
    "treat_vs_ctrl": "deseq_treat_vs_ctrl.tsv",
    "drug_vs_ctrl": "deseq_drug_vs_ctrl.tsv",
}

for name, file in comparisons.items():
    # df = pd.read_csv(file, sep="\t", index_col=0)
    # ranked = df["log2FoldChange"].dropna().sort_values(ascending=False)
    
    # Example: generate synthetic ranked list
    import numpy as np
    ranked = pd.Series(np.random.normal(0, 1, 800),
                       index=[f"G{i}" for i in range(800)]).sort_values(ascending=False)
    
    pre = gp.prerank(
        rnk=ranked,
        gene_sets=["MSigDB_Hallmark_2020", "KEGG_2021_Human"],
        threads=4,
        permutation_num=500,
        outdir=f"gsea_results/{name}/",
        seed=42,
    )
    sig = pre.res2d[pre.res2d["FDR q-val"] < 0.25]
    print(f"{name}: {len(sig)} significant gene sets")
    pre.res2d.to_csv(f"gsea_results/{name}/all_results.tsv", sep="\t")
```

## Expected Outputs

| Output | Format | Description |
|--------|--------|-------------|
| `enr.results` | DataFrame | ORA results: Term, P-value, Adjusted P-value, Combined Score, Genes |
| `pre_res.res2d` | DataFrame | Prerank results: Term, ES, NES, NOM p-val, FDR q-val, Gene % |
| `gsea_results/*.csv` | CSV | Saved enrichment tables per database |
| `gsea_results/*.pdf` | PDF | GSEA running-score plots (one per gene set) |
| `enrichment_dotplot.png` | PNG | Dot plot of top enriched terms |
| `gseaplot output` | PNG/PDF | Running enrichment score + ranked list plot |
| enrichment map | PNG/matplotlib | Network of enriched pathways (nodes=terms, edges=shared genes) |

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `ConnectionError` in `enrichr` | No internet or Enrichr API down | Check https://maayanlab.cloud/Enrichr/; use local gene sets with `gene_sets="path/to/gmt"` |
| No significant terms returned | Gene list too small or wrong gene ID format | Use ≥10 genes; ensure HGNC symbols (not Ensembl IDs); convert with `pyensembl` |
| Prerank returns all NES ≈ 0 | Ranked list not sorted or too few genes | Verify `rnk` is sorted descending; check `min_size ≤` gene set sizes |
| `KeyError` in gene set | Gene set name misspelled | Use `gp.get_library_name()` to get exact database names |
| Low NES with FDR > 0.25 | Signal is weak or permutation count too low | Increase `permutation_num` to 1000; check raw p-values in `NOM p-val` |
| GSEA plot shows flat line | Gene set has no intersection with ranked list | Check gene naming; confirm gene set species matches data |
| Memory error during prerank | Large expression matrix + high permutations | Reduce `permutation_num`; use `prerank` instead of `gsea` when possible |
| Enrichr results differ from Java GSEA | Different gene set versions | Specify exact database version string from `gp.get_library_name()` |

## References
- Adapted from [SciAgent gseapy-genie-enrichment skill](https://github.com/jaechang-hits/SciAgent-Skills/blob/0d18706fe1a51239f12b395f046c8aa30fe632b4/skills/genomics-bioinformatics/rnaseq/gseapy-gene-enrichment/SKILL.md) to extend `gseapy` capabilities
- [GSEApy documentation](https://gseapy.readthedocs.io/) — official usage guide and API reference
- [GSEApy GitHub: zqfang/GSEApy](https://github.com/zqfang/GSEApy) — source code and examples
- Fang Z et al. (2023) "GSEApy: a comprehensive package for performing gene set enrichment analysis in Python" — *Bioinformatics* 39(1):btac757. [DOI:10.1093/bioinformatics/btac757](https://doi.org/10.1093/bioinformatics/btac757)
- Subramanian A et al. (2005) "Gene set enrichment analysis: A knowledge-based approach for interpreting genome-wide expression profiles" — *PNAS* 102(43):15545-15550. [DOI:10.1073/pnas.0506580102](https://doi.org/10.1073/pnas.0506580102)
- [Enrichr gene set databases](https://maayanlab.cloud/Enrichr/) — full list of 200+ available gene set libraries
