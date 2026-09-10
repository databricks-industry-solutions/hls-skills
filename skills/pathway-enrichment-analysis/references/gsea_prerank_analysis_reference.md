# GSEA Prerank — Reference Implementation

This document is the full reference implementation for running preranked GSEA (`gp.prerank`)
on a full ranked gene list, plus the recommended visualization suite and the
GSEA-specific diagnostic plots that make its single-run, magnitude-aware nature explicit
(see `SKILL.md` → [Required Visualization Outputs](../SKILL.md#required-visualization-outputs)).

**Usage pattern:** these are plain, top-to-bottom code snippets, not reusable helper
functions. Reference the specific snippet needed for the current step and adapt its
variable names in place against the ranked Series the user already has (e.g.
`ds.results_df["log2FoldChange"]`).

## Table of Contents
1. [Load Ranked Gene List](#load-ranked-gene-list)
2. [Run GSEA Prerank](#run-gsea-prerank)
3. [Save Results](#save-results)
4. [NES Bar Plot](#nes-bar-plot)
5. [Enrichment Curves](#enrichment-curves)
6. [Network Enrichment Map](#network-enrichment-map)
7. [Enrichment Dot Plot (Additional)](#enrichment-dot-plot-additional)
8. [NES Waterfall (Additional)](#nes-waterfall-additional)
9. [Leading-Edge Gene Overlap Heatmap (Additional)](#leading-edge-gene-overlap-heatmap-additional)

---

## Load Ranked Gene List

GSEA Prerank runs on the **full** ranked gene list (e.g., all genes ranked by log2FC), not
just a significant subset — this is what lets it capture both directions in one run.

```python
from pathlib import Path

output_dir = Path("results/gsea")
output_dir.mkdir(parents=True, exist_ok=True)

ranked = ds.results_df["log2FoldChange"].dropna().sort_values(ascending=False)
ranked = ranked[~ranked.index.duplicated(keep="first")]
print(f"Loaded {len(ranked)} ranked genes (range: {ranked.max():.2f} to {ranked.min():.2f})")
```

If loading from a `.rnk` file instead:
`ranked = pd.read_csv(path, sep=None, engine="python", header=None, index_col=0).iloc[:, 0]`.

## Run GSEA Prerank

```python
import gseapy as gp

pre_res = gp.prerank(
    rnk=ranked,
    gene_sets="MSigDB_Hallmark_2020",
    threads=4,
    min_size=15,
    max_size=500,
    permutation_num=1000,
    outdir=str(output_dir / "prerank"),
    seed=42,
    verbose=True,
)
```

## Save Results

```python
fdr_cutoff = 0.25

res_df = pre_res.res2d.copy()
res_df["NES"] = res_df["NES"].astype(float)
res_df["FDR q-val"] = res_df["FDR q-val"].astype(float)
res_df.to_csv(output_dir / "gsea_prerank_all_terms.tsv", sep="\t", index=False)

sig_df = res_df[res_df["FDR q-val"] < fdr_cutoff].sort_values("NES", ascending=False)
sig_df.to_csv(output_dir / "gsea_prerank_significant_terms.tsv", sep="\t", index=False)
print(f"{len(sig_df)} significant terms (FDR < {fdr_cutoff})")
```

`res2d` columns: `Name`, `Term`, `ES`, `NES`, `NOM p-val`, `FDR q-val`, `FWER p-val`,
`Tag %`, `Gene %`, `Lead_genes` (semicolon-separated leading-edge genes).

## NES Bar Plot

Always generate this after any GSEA Prerank run.

```python
import matplotlib.pyplot as plt

gp.barplot(
    df=sig_df,
    column="FDR q-val",
    title=f"GSEA Prerank: Enriched Gene Sets (FDR < {fdr_cutoff})",
    figsize=(10, 8),
)
plt.tight_layout()
plt.savefig(output_dir / "gsea_nes_barplot.png", dpi=300, bbox_inches="tight")
plt.show()
```

## Enrichment Curves

Running-score curves for the top positive- and negative-NES terms. Always show the top 3
per direction whenever GSEA is used.

```python
from gseapy.plot import gseaplot

top_pos = sig_df.sort_values("NES", ascending=False).head(3)["Term"].tolist()
top_neg = sig_df.sort_values("NES", ascending=True).head(3)["Term"].tolist()

for direction, terms in [("positive_NES", top_pos), ("negative_NES", top_neg)]:
    for term in terms:
        gseaplot(rank_metric=pre_res.ranking, term=term, **pre_res.results[term])
        plt.tight_layout()
        safe_term = "".join(c if c.isalnum() else "_" for c in term)[:60]
        plt.savefig(output_dir / f"gsea_curve_{direction}_{safe_term}.png", dpi=300, bbox_inches="tight")
        plt.show()
```

## Network Enrichment Map

Reuses the same `enrichment_map` utility as ORA — pass `FDR q-val` renamed to
`Adjusted P-value` since GSEA results are already FDR-filtered upstream (cutoff=1.0
avoids double-filtering).

```python
import networkx as nx
from gseapy.plot import enrichment_map

map_df = sig_df.rename(columns={"FDR q-val": "Adjusted P-value"})
nodes, edges = enrichment_map(map_df, column="Adjusted P-value", cutoff=1.0, top_term=30)

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

plt.colorbar(sc, ax=ax, shrink=0.6, label="-log10(FDR q-val)")
ax.set_title("GSEA Prerank: Enrichment Map")
ax.axis("off")
plt.tight_layout()
plt.savefig(output_dir / "gsea_network_map.png", dpi=300, bbox_inches="tight")
plt.show()
```

*Guard before plotting:* skip if `len(sig_df) < 2` (network map needs ≥2 terms) or if
`edges` comes back empty (no shared-gene overlap between the top terms).

## Enrichment Dot Plot (Additional)

```python
from gseapy.plot import dotplot

dotplot(
    sig_df,
    column="FDR q-val",
    x="Name",
    title="GSEA Prerank: Enrichment Dot Plot",
    cmap="viridis_r",
    size=10,
    top_term=15,
    figsize=(6, 8),
)
plt.tight_layout()
plt.savefig(output_dir / "gsea_dotplot.png", dpi=300, bbox_inches="tight")
plt.show()
```

## NES Waterfall (Additional)

**GSEA-specific diagnostic.** Plots NES across ALL tested gene sets, sorted, colored by
direction and significance. Highlights that GSEA Prerank captures both up- and
down-regulated pathway signal in a single run — unlike ORA, which requires two separate
runs.

```python
ordered = res_df.sort_values("NES", ascending=False).reset_index(drop=True)
sig_mask = ordered["FDR q-val"] < fdr_cutoff
colors = [
    ("red" if nes > 0 else "blue") if sig else "lightgrey"
    for nes, sig in zip(ordered["NES"], sig_mask)
]

fig, ax = plt.subplots(figsize=(10, max(6, len(ordered) * 0.06)))
ax.bar(range(len(ordered)), ordered["NES"], color=colors, width=1.0)
ax.axhline(0, color="black", linewidth=0.8)
ax.set_xlabel(f"Gene sets ranked by NES (n={len(ordered)})")
ax.set_ylabel("Normalized Enrichment Score (NES)")
ax.set_title(f"GSEA Prerank: NES Waterfall — Both Directions in One Run\n(colored: FDR < {fdr_cutoff})")
ax.set_xticks([])
plt.tight_layout()
plt.savefig(output_dir / "gsea_nes_waterfall.png", dpi=300, bbox_inches="tight")
plt.show()
```

## Leading-Edge Gene Overlap Heatmap (Additional)

**GSEA-specific diagnostic.** Jaccard-similarity heatmap of leading-edge genes shared
between the top enriched terms (from the `Lead_genes` column). Highlights GSEA's ability
to detect coordinated, distributed signal driven by overlapping leading-edge gene sets
rather than a fixed significance cutoff on individual genes.

```python
import numpy as np
import seaborn as sns

top = sig_df.sort_values("FDR q-val").head(15)
leading_edges = {
    row["Term"]: set(str(row["Lead_genes"]).split(";"))
    for _, row in top.iterrows()
}
terms = list(leading_edges.keys())
n = len(terms)

jaccard = np.zeros((n, n))
for i, t1 in enumerate(terms):
    for j, t2 in enumerate(terms):
        a, b = leading_edges[t1], leading_edges[t2]
        jaccard[i, j] = len(a & b) / len(a | b) if (a | b) else 0.0

short_labels = [t if len(t) <= 40 else t[:37] + "..." for t in terms]
fig, ax = plt.subplots(figsize=(max(8, n * 0.5), max(6, n * 0.5)))
sns.heatmap(
    jaccard, xticklabels=short_labels, yticklabels=short_labels,
    cmap="viridis", vmin=0, vmax=1, square=True,
    cbar_kws={"label": "Jaccard similarity (leading-edge genes)"}, ax=ax,
)
ax.set_title("GSEA Prerank: Leading-Edge Gene Overlap")
plt.xticks(rotation=90, fontsize=7)
plt.yticks(rotation=0, fontsize=7)
plt.tight_layout()
plt.savefig(output_dir / "gsea_leading_edge_overlap.png", dpi=300, bbox_inches="tight")
plt.show()
```

*Guard before plotting:* skip if `"Lead_genes"` is missing (e.g. `ssgsea` results don't
have it) or fewer than 2 terms remain after filtering.
