---
name: pathway-enrichment-analysis
description: Pathway enrichment method selection for RNA-seq and proteomics. Choose among ORA (Enrichr), GSEA Prerank, and standard GSEA; covers inputs, significance thresholds, required plots, and GSEApy implementation. Consult after differential expression when interpreting gene lists at pathway/GO level. For DESeq2 DE workflows use bulk-rnaseq.
author: Yen Low
license: MIT
---

# Pathway Enrichment Analysis

## Overview

Pathway enrichment interprets differential expression (or other ranked/hit gene lists) at the pathway and GO-term level rather than gene by gene. This guide covers when to use over-representation analysis (ORA), GSEA Prerank, or standard GSEA; how to prepare inputs; which outputs and plots to produce; and how to run the analyses with GSEApy against Enrichr libraries (GO, KEGG, MSigDB, Reactome, and 200+ others). Use it after DESeq2, edgeR, limma, or scanpy DE — not as a substitute for the DE step itself.

## When to Use

- Interpreting DESeq2 or edgeR differential expression results at pathway/GO-term level
- Choosing among ORA, GSEA Prerank, and standard GSEA given the available inputs
- Running Enrichr ORA against GO, KEGG, MSigDB Hallmarks, and other libraries
- Performing GSEA prerank on a log2-fold-change-ranked gene list without a raw expression matrix
- Identifying enriched pathways in scRNA-seq cluster marker genes
- Producing enrichment tables plus required bar plots, network maps, and GSEA running-score plots
- For upstream DESeq2 differential expression, use `bulk-rnaseq` instead

## Key Concepts

### Over-representation analysis (ORA)

ORA tests whether a **discrete gene list** (e.g. significant DEGs) is enriched for genes in curated sets. In GSEApy this is `gp.enrichr`, which queries Enrichr. It is simple and fast, but ignores magnitude of change and depends on an arbitrary significance cutoff. Run **separately** on up- and down-regulated lists. Typical threshold: adjusted P-value < 0.05. Full recipe: `references/ora_analysis_reference.md`.

### GSEA Prerank

GSEA Prerank runs the GSEA algorithm on a **ranked list of all tested genes** (e.g. log2 fold-change sorted descending) without needing a raw expression matrix. In GSEApy this is `gp.prerank`. It detects coordinated pathway shifts even when individual genes are modest, handles both directions in one run (positive NES = up, negative NES = down), and avoids cutoff bias. Typical threshold: FDR q-val < 0.25. Full recipe: `references/gsea_prerank_analysis_reference.md`.

### Standard GSEA

Standard GSEA (`gp.gsea`) permutes **sample/phenotype labels** on an expression matrix. It is closest to the original Broad methodology but needs enough samples per group (≥7 recommended), is slowest, and couples ranking to the test. Prefer `gp.prerank()` in virtually every other case — it separates DE from enrichment and works with output from any DE tool.

### Gene set libraries and identifiers

Enrichr provides 200+ libraries (`gp.get_library_name(organism="human")`). Pass a local `.gmt` via `gene_sets=` for offline use. Gene IDs must match the library (typically HGNC symbols, not Ensembl IDs).

## Decision Framework

**ALWAYS decide which method to use BEFORE running any enrichment analysis.**

```
Question: What input do you have?
├── Discrete gene list only (no ranks)
│   └── → ORA (`gp.enrichr`)
├── Full DE results with a ranking metric (e.g. log2FC)
│   ├── Default → GSEA Prerank (`gp.prerank`)
│   └── User explicitly wants ORA / Enrichr → ORA on significant subset
├── Raw expression matrix + phenotype labels
│   └── User explicitly wants sample-permutation GSEA
│       └── → Standard GSEA (`gp.gsea`); otherwise still prefer Prerank on a DE ranking
└── User asks for both ORA and GSEA
    └── → ORA on significant genes + Prerank on full ranked list
```

| Scenario | Recommended approach | Rationale |
|----------|---------------------|-----------|
| Full DE table with log2FC for all genes | GSEA Prerank | More powerful; no arbitrary cutoff |
| Only a gene list (e.g. scRNA-seq cluster markers) | ORA | No ranks available |
| Quick hypothesis check on a curated hit list | ORA | Fast and interpretable |
| Expression matrix + labels; user wants classic Broad GSEA | Standard GSEA | Sample-label permutation |
| User asks for both methods | ORA + Prerank | Discrete hits + subtle coordinated signals |
| Default when unsure and ranks exist | GSEA Prerank | Preferred over `gp.gsea()` in almost all cases |

| Criterion | ORA (`gp.enrichr`) | GSEA Prerank (`gp.prerank`) | Standard GSEA (`gp.gsea`) |
|-----------|---------------------|------------------------------|----------------------------|
| **Input** | Discrete gene list | Ranked list of ALL tested genes | Expression matrix + phenotype |
| **Typical source** | `padj < 0.05 & abs(log2FC) > 1` | Full `log2FoldChange` column | TPM/CPM + two-group labels |
| **Strength** | Simple, fast, focused | Subtle distributed signals; no cutoff | Faithful to Broad GSEA |
| **Weakness** | Threshold-dependent; ignores magnitude | Slower; sensitive to ranking metric | Needs ≥7 samples/group; slowest |
| **Significance** | Adjusted P < 0.05 | FDR q < 0.25 | FDR q < 0.25 |
| **Direction** | Separate up/down runs | One run (sign of NES) | One run (sign of NES) |

## Best Practices

1. **Choose the method first**: Apply the decision framework before calling Enrichr or prerank — do not default to ORA solely because it is familiar.
2. **Prefer GSEA Prerank when ranks exist**: Use the full DE ranking (e.g. log2FC) rather than thresholding away signal.
3. **Split ORA by direction**: Always run up- and down-regulated gene lists separately; never pool them.
4. **Use HGNC symbols and exact library names**: Confirm species and ID type; list libraries with `gp.get_library_name()` rather than guessing strings.
5. **Ship required plots every run**: Always produce the bar plot and network enrichment map; for GSEA also produce enrichment curves for the top 3 terms per direction. Use `gp.barplot` / `gseapy.plot.dotplot` — not ad-hoc seaborn/matplotlib bar charts.
6. **Dot plots only on request**: Generate a dot plot only when the user explicitly asks for one.
7. **Set seeds and publication-grade permutations**: For prerank, use `permutation_num=1000` and a fixed `seed` when reporting results.
8. **Compare across contrasts deliberately**: For multiple conditions, repeat the full workflow per contrast and compare significant-term sets afterward.

## Troubleshooting

1. **Running ORA on a thresholded list when full ranks were available**
   - *How to avoid*: Default to GSEA Prerank whenever log2FC (or another ranking metric) exists for all tested genes.
2. **Pooling up- and down-regulated genes in one ORA call**
   - *How to avoid*: Always run separate Enrichr analyses per direction.
3. **Using Ensembl IDs against symbol-based Enrichr libraries**
   - *How to avoid*: Convert to HGNC (or matching) symbols before enrichment; verify overlap size is non-trivial.
4. **Skipping the network map or using custom bar charts**
   - *How to avoid*: Follow the required visualization table; call GSEApy plotting helpers.
5. **Calling `gp.gsea()` by default on an expression matrix**
   - *How to avoid*: Prefer DE → ranked list → `gp.prerank()` unless the user explicitly wants sample-permutation GSEA.
6. **Unsorted or tiny ranked lists yielding flat NES ≈ 0**
   - *How to avoid*: Sort `rnk` descending; keep gene-set size within `min_size`/`max_size`; ensure ≥10 genes for ORA.
7. **Offline or API failures treated as empty biology**
   - *How to avoid*: Check Enrichr availability; fall back to a local `.gmt` via `gene_sets=`.

## Workflow

1. **Step 1: Planning**
   - Apply the decision framework (ORA / GSEA Prerank / standard GSEA / both).
   - Confirm organism, gene ID type, and target Enrichr libraries (or local `.gmt`).
2. **Step 2: Prepare input**
   - ORA: derive up- and down-regulated gene lists (`references/ora_analysis_reference.md` → *Load Gene Lists*).
   - Prerank: build full ranked Series, e.g. log2FC sorted descending (`references/gsea_prerank_analysis_reference.md` → *Load Ranked Gene List*).
3. **Step 3: Run analysis**
   - ORA: `gp.enrichr` per direction against one or more databases.
   - Prerank: single `gp.prerank` on the full list.
4. **Step 4: Save results**
   - Write full and significance-filtered tables (`references/*.md` → *Save Results*).
5. **Step 5: Visualize**
   - Required plots + method-specific diagnostics (see Protocol Guidelines).
   - Dot plot only if explicitly requested.
6. **Step 6: Multi-contrast (optional)**
   - Repeat steps 2–5 per comparison; compare significant-term sets across runs.

Load the matching reference file on demand and adapt variable names to the user's existing DESeq2/edgeR/scanpy objects — snippets are step-oriented recipes, not a packaged library.

## Protocol Guidelines

1. **Required visualizations (always)**
   - ORA: bar plot + network enrichment map; plus up/down term-overlap comparison and gene-set-size vs significance scatter for full analyses.
   - GSEA Prerank: NES bar plot + enrichment curves (top 3 terms per direction) + network map; plus NES waterfall and leading-edge overlap heatmap for full analyses.
   - Both methods requested: produce the full set for each.
2. **Optional visualizations**: Dot plot only when the user asks (e.g. "show a dotplot").
3. **Key parameters**

   | Parameter | Default | Range / options | Effect |
   |-----------|---------|-----------------|--------|
   | `gene_sets` | required | string, list, or `.gmt` path | Enrichr library name(s) or local GMT |
   | `organism` (enrichr) | `"human"` | human, mouse, fly, fish, worm, yeast | Species for lookup |
   | `cutoff` (enrichr) | `0.05` | 0–1 | Adjusted p-value filter |
   | `rnk` (prerank) | required | `pd.Series` | Gene → score; sort descending |
   | `permutation_num` (prerank) | `1000` | 100–10000 | Permutations for p-values |
   | `min_size` / `max_size` (prerank) | `15` / `500` | 5–50 / 100–2000 | Gene-set size bounds |
   | `threads` (prerank) | `4` | 1–64 | CPU threads |
   | `seed` (prerank) | `None` | integer | Reproducibility |

4. **Expected output patterns**

   | Output pattern | Method | Description |
   |----------------|--------|-------------|
   | `ora_{up,down}_all_terms.tsv`, `ora_{up,down}_significant_terms.tsv` | ORA | Full and filtered tables |
   | `ora_{up,down}_barplot.png`, `ora_{up,down}_network_map.png` | ORA | Required plots |
   | `ora_{up,down}_dotplot.png` | ORA | Optional (request only) |
   | `ora_updown_term_overlap.png`, `ora_size_vs_significance.png` | ORA | Additional diagnostics |
   | `gsea_prerank_all_terms.tsv`, `gsea_prerank_significant_terms.tsv` | Prerank | Full and FDR-filtered tables |
   | `gsea_nes_barplot.png`, `gsea_curve_*_NES_*.png`, `gsea_network_map.png` | Prerank | Required plots |
   | `gsea_dotplot.png`, `gsea_nes_waterfall.png`, `gsea_leading_edge_overlap.png` | Prerank | Optional / additional |

5. **Environment**
   - Packages: `gseapy`, `pandas`, `matplotlib`, `networkx`, `seaborn`.
   - Install: `pip install gseapy`. Internet required unless a local `.gmt` is supplied.

## Related Skills

- `bulk-rnaseq` — upstream differential expression (DESeq2); produce the ranked lists and DEG tables this guide consumes.

## Companion Assets

- `references/ora_analysis_reference.md` — ORA implementation: directional Enrichr runs, bar/network plots, optional dot plot, up/down overlap and size-vs-significance diagnostics.
- `references/gsea_prerank_analysis_reference.md` — GSEA Prerank implementation: single-run prerank, NES bar/curves/network, optional dot plot, NES waterfall and leading-edge overlap diagnostics.

## References

- Adapted from [SciAgent gseapy-gene-enrichment skill](https://github.com/jaechang-hits/SciAgent-Skills/blob/0d18706fe1a51239f12b395f046c8aa30fe632b4/skills/genomics-bioinformatics/rnaseq/gseapy-gene-enrichment/SKILL.md)
- [GSEApy documentation](https://gseapy.readthedocs.io/) — usage guide and API reference
- [GSEApy GitHub: zqfang/GSEApy](https://github.com/zqfang/GSEApy) — source and examples
- Fang Z et al. (2023) "GSEApy: a comprehensive package for performing gene set enrichment analysis in Python" — *Bioinformatics* 39(1):btac757. [DOI:10.1093/bioinformatics/btac757](https://doi.org/10.1093/bioinformatics/btac757)
- Subramanian A et al. (2005) "Gene set enrichment analysis: A knowledge-based approach for interpreting genome-wide expression profiles" — *PNAS* 102(43):15545-15550. [DOI:10.1073/pnas.0506580102](https://doi.org/10.1073/pnas.0506580102)
- [Enrichr gene set databases](https://maayanlab.cloud/Enrichr/) — 200+ gene set libraries
