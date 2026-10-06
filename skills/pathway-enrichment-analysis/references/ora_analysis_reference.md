# ORA (Over-Representation Analysis) — Reference Implementation

This document is the full reference implementation for running Enrichr-based ORA on a
discrete gene list, with the directional split (up vs down) that ORA requires, plus the
recommended visualization suite and the ORA-specific diagnostic plots that make its
up/down split and magnitude-blindness explicit (see `SKILL.md` →
[Required Visualization Outputs](../SKILL.md#required-visualization-outputs)).

**Usage pattern:** these are plain, top-to-bottom code snippets, not reusable helper
functions. Reference the specific snippet needed for the current step and adapt its
variable names in place against whatever gene lists / DataFrames the user already has
(e.g. a DESeq2 `results_df`).

## Table of Contents
1. [Load Gene Lists (Directional Split)](#load-gene-lists-directional-split)
2. [Run ORA via Enrichr](#run-ora-via-enrichr)
3. [Save Results](#save-results)
4. [Bar Plot](#bar-plot)
5. [Network Enrichment Map](#network-enrichment-map)
6. [Enrichment Dot Plot (Additional)](#enrichment-dot-plot-additional)
7. [Up/Down Term-Overlap Comparison (Additional)](#updown-term-overlap-comparison-additional)
8. [Gene-Set Size vs Significance Scatter (Additional)](#gene-set-size-vs-significance-scatter-additional)

---

## Load Gene Lists (Directional Split)

ORA must be run **separately** on up- and down-regulated genes (see the method
comparison table in `SKILL.md`). Derive both lists directly from DE results rather than a
single "significant genes" list, so direction-specific enrichment isn't masked.

```python
import pandas as pd
from pathlib import Path

output_dir = Path("results/ora")
output_dir.mkdir(parents=True, exist_ok=True)

gene_sets = ["GO_Biological_Process_2023", "KEGG_2021_Human", "MSigDB_Hallmark_2020"]
padj_cutoff, lfc_cutoff = 0.05, 1.0

deseq_df = ds.results_df.dropna(subset=["log2FoldChange", "padj"])
up_genes = deseq_df[(deseq_df["padj"] < padj_cutoff) & (deseq_df["log2FoldChange"] > lfc_cutoff)].index.tolist()
down_genes = deseq_df[(deseq_df["padj"] < padj_cutoff) & (deseq_df["log2FoldChange"] < -lfc_cutoff)].index.tolist()

print(f"Upregulated: {len(up_genes)}, Downregulated: {len(down_genes)}")
```

If only a plain gene list is available (e.g., scRNA-seq cluster markers with no ranks),
skip the split and use that single list instead — directional overlap diagnostics simply
won't apply.

## Run ORA via Enrichr

Run separately per direction — do not pool up- and down-regulated genes into one call.

```python
import gseapy as gp

enr_up = gp.enrichr(gene_list=up_genes, gene_sets=gene_sets, organism="human",
                     outdir=str(output_dir / "enrichr_up"), cutoff=0.05)

enr_dn = gp.enrichr(gene_list=down_genes, gene_sets=gene_sets, organism="human",
                     outdir=str(output_dir / "enrichr_down"), cutoff=0.05)
```

## Save Results

```python
sig_up = enr_up.results[enr_up.results["Adjusted P-value"] < 0.05]
enr_up.results.to_csv(output_dir / "ora_up_all_terms.tsv", sep="\t", index=False)
sig_up.to_csv(output_dir / "ora_up_significant_terms.tsv", sep="\t", index=False)
print(f"Upregulated: {len(sig_up)} significant terms")

sig_dn = enr_dn.results[enr_dn.results["Adjusted P-value"] < 0.05]
enr_dn.results.to_csv(output_dir / "ora_down_all_terms.tsv", sep="\t", index=False)
sig_dn.to_csv(output_dir / "ora_down_significant_terms.tsv", sep="\t", index=False)
print(f"Downregulated: {len(sig_dn)} significant terms")
```

## Bar Plot

Always generate this after any ORA run — color-coded by gene set database. Shown for the
upregulated direction; repeat with `sig_dn` / `"down"` for downregulated.

If there are multiple unique Gene_set values, the barplot should be stratified by "Gene_set" displayed in different colors

```python
import matplotlib.pyplot as plt
import seaborn as sns

colors = dict(zip(
    sig_up["Gene_set"].unique(),
    sns.color_palette("Set2", n_colors=sig_up["Gene_set"].nunique()),
))

gp.barplot(
    df=sig_up.sort_values("Adjusted P-value"),
    column="Adjusted P-value",
    group="Gene_set", # if multiple unique Gene_set values, comment out otherwise
    title="ORA (up): Top Enriched Pathways",
    figsize=(10, 8),
    color=colors,
)
plt.tight_layout()
plt.savefig(output_dir / "ora_up_barplot.png", dpi=300, bbox_inches="tight")
plt.show()
```

## Network Enrichment Map

Visualizes pathway-pathway relationships (nodes = enriched terms, edges = shared genes).
Requires `networkx`. Shown for the upregulated direction; repeat with `sig_dn` for
downregulated.

```python
import networkx as nx
from gseapy.plot import enrichment_map

nodes, edges = enrichment_map(sig_up, column="Adjusted P-value", cutoff=0.05, top_term=30)

G = nx.from_pandas_edgelist(
    edges, source="src_idx", target="targ_idx",
    edge_attr=["jaccard_coef", "overlap_coef", "overlap_genes"],
)
fig, ax = plt.subplots(figsize=(14, 12))
pos = nx.spring_layout(G, k=1.5, seed=42)
edge_width = list(nx.get_edge_attributes(G, "jaccard_coef").values())

nx.draw_networkx_edges(G, pos, width=edge_width, alpha=0.4, edge_color="grey", ax=ax)
sc = nx.draw_networkx_nodes(
    G, pos,
    node_size=(nodes["Hits_ratio"] * 1000).tolist(),
    node_color=nodes["p_inv"].tolist(),
    cmap=plt.cm.RdYlBu_r, alpha=0.85, ax=ax, edgecolors="black", linewidths=0.5,
)
term_labels = nodes.Term.to_dict()
wrapped = {k: "\n".join([v[i:i + 28] for i in range(0, len(v), 28)]) for k, v in term_labels.items()}
nx.draw_networkx_labels(G, pos, labels=wrapped, font_size=6, ax=ax)

plt.colorbar(sc, ax=ax, shrink=0.6, label="-log10(Adjusted P-value)")
ax.set_title("ORA (up): Enrichment Map")
ax.axis("off")
plt.tight_layout()
plt.savefig(output_dir / "ora_up_network_map.png", dpi=300, bbox_inches="tight")
plt.show()
```

## Enrichment Dot Plot (ONLY WHEN REQUESTED)

Only produce this when the user explicitly asks for a dot plot.

```python
from gseapy.plot import dotplot

dotplot(
    sig_up,
    column="Adjusted P-value",
    x="Gene_set",
    title="ORA (up): Enrichment Dot Plot",
    cmap="viridis_r",
    size=10,
    top_term=15,
    figsize=(6, 8),
)
plt.tight_layout()
plt.savefig(output_dir / "ora_up_dotplot.png", dpi=300, bbox_inches="tight")
plt.show()
```

## Up/Down Term-Overlap Comparison (Additional)

**ORA-specific diagnostic.** Compares enriched terms between the up- and down-regulated gene lists that ORA must be run on separately. Shows how many enriched pathways are shared vs unique to each direction — a comparison GSEA Prerank doesn't need, since it handles both directions in a single run.

```python
up_terms = set(sig_up["Term"])
down_terms = set(sig_dn["Term"])
shared = up_terms & down_terms
up_only = up_terms - down_terms
down_only = down_terms - up_terms

counts = {"Up-only": len(up_only), "Shared": len(shared), "Down-only": len(down_only)}
print(f"Up/down term overlap: {counts}")

fig, ax = plt.subplots(figsize=(6, 5))
bars = ax.bar(counts.keys(), counts.values(), color=["red", "purple", "blue"], alpha=0.75)
ax.bar_label(bars)
ax.set_ylabel("Number of significant terms")
ax.set_title("ORA: Up vs Down Enriched Term Overlap")
plt.tight_layout()
plt.savefig(output_dir / "ora_updown_term_overlap.png", dpi=300, bbox_inches="tight")
plt.show()

pd.DataFrame(sorted(shared), columns=["Term"]).to_csv(
    output_dir / "ora_updown_shared_terms.tsv", sep="\t", index=False
)
```

## Gene-Set Size vs Significance Scatter (Additional)

**ORA-specific diagnostic.** Plots gene-overlap count vs `-log10(adjusted p-value)` as a
bubble scatter (bubble size = Combined Score). Highlights ORA's core weakness —
significance is driven only by the count of overlapping genes, with no fold-change
magnitude weighting (unlike GSEA's NES).

```python
import numpy as np

sig_up = sig_up.assign(direction="up", n_overlap=sig_up["Overlap"].str.split("/").str[0].astype(int))
sig_dn = sig_dn.assign(direction="down", n_overlap=sig_dn["Overlap"].str.split("/").str[0].astype(int))
combined = pd.concat([sig_up, sig_dn], ignore_index=True)
combined["-log10(padj)"] = -np.log10(combined["Adjusted P-value"].clip(lower=1e-300))

color_map = {"up": "red", "down": "blue"}
fig, ax = plt.subplots(figsize=(9, 7))
for direction, group in combined.groupby("direction"):
    ax.scatter(
        group["n_overlap"], group["-log10(padj)"],
        s=(group["Combined Score"].clip(upper=200) + 10),
        alpha=0.6, edgecolors="black", linewidths=0.3,
        c=color_map[direction], label=direction,
    )
ax.set_xlabel("Number of overlapping genes")
ax.set_ylabel("-log10(Adjusted P-value)")
ax.set_title("ORA: Gene-Set Overlap Size vs Significance\n(bubble size = Combined Score)")
ax.legend(title="Direction")
plt.tight_layout()
plt.savefig(output_dir / "ora_size_vs_significance.png", dpi=300, bbox_inches="tight")
plt.show()
```
