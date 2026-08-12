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
- Performing GSEA prerank analysis on a log2-fold-change-ranked gene list without needing a raw expression matrix
- Identifying enriched pathways in scRNA-seq cluster marker genes
- Generating publication-ready enrichment dot plots and GSEA running-score plots

## Choosing a Method: ORA vs GSEA Prerank vs Standard GSEA

**ALWAYS decide which method to use BEFORE running any enrichment analysis.** The choice depends on the input data and the biological question:

| Criterion | ORA (`gp.enrichr`) | GSEA Prerank (`gp.prerank`) | Standard GSEA (`gp.gsea`) |
|-----------|---------------------|------------------------------|----------------------------|
| **Input** | A discrete gene list (e.g., significant DEGs) | A ranked list of ALL tested genes (e.g., log2FC) | A raw expression matrix + phenotype/class labels |
| **When to use** | You have a clear significance threshold and want to test a curated hit list | You want to detect coordinated pathway-level shifts even when individual genes are modest | You want sample-label permutation testing directly on expression data, without a separate DE step |
| **Typical source** | DESeq2 `padj < 0.05 & abs(log2FC) > 1` subset | DESeq2 full `log2FoldChange` column (all genes, sorted descending) | Normalized expression matrix (TPM/CPM) + a two-group phenotype vector |
| **Strength** | Simple, fast, interpretable for focused gene lists | Captures subtle distributed signals; no arbitrary cutoff needed | Most faithful to the original Broad GSEA methodology (permutes sample labels, not genes) |
| **Weakness** | Ignores magnitude; depends on threshold choice; misses genes just below cutoff | Slower (permutation-based); results sensitive to ranking metric | Needs enough samples per group (≥7 recommended) for robust permutation; slowest; couples ranking to the test |
| **Significance metric** | Adjusted P-value < 0.05 | FDR q-val < 0.25 (standard GSEA threshold) | FDR q-val < 0.25 |
| **Directional split** | Run SEPARATELY on up- and down-regulated gene lists | Handles both directions in one run (positive NES = up, negative NES = down) | Handles both directions in one run |
| **Reference doc** | `references/ora_analysis_reference.md` | `references/gsea_prerank_analysis_reference.md` | none — rarely needed, see decision rules below |

**Decision rules:**
1. **Default to GSEA Prerank** when you have full DE results with log2FC values — it is more powerful and avoids arbitrary cutoff bias.
2. **Use ORA** when (a) you only have a gene list without ranks (e.g., cluster markers from scRNA-seq), (b) you want quick hypothesis validation of a specific gene set, or (c) the user explicitly requests ORA/Enrichr.
3. **Almost never use `gp.gsea()` (standard GSEA with expression matrix)** — only reach for it when the user explicitly has a raw expression matrix and phenotype labels AND specifically wants classic sample-permutation GSEA rather than a gene-permutation test on a precomputed ranking. `gp.prerank()` is preferred in virtually every other case because it separates the DE step from the enrichment step and works with output from any DE tool (DESeq2, edgeR, limma, scanpy).
4. **Run both ORA and GSEA Prerank _only_** when the user explicitly asks for both — ORA on the significant subset for discrete pathway hits, plus GSEA Prerank on the full ranked list for subtle coordinated changes.

## Required Visualization Outputs

**ALWAYS produce these visualizations after running enrichment analysis.** Each method also gets its own additional diagnostic plots that make the differences in the table above visible in the output, not just in theory. Full implementations of every plot below live in the reference docs (see [Bundled Resources](#bundled-resources)).

| Method used | MANDATORY outputs | Additional diagnostic outputs (method-specific) | ONLY when requested |
|-------------|-------------------|---------------------------------------------------|---------------------|
| ORA (`gp.enrichr`) | Stratified bar plot + Network enrichment map | Up/down term-overlap comparison (reflects the mandatory directional split) + gene-set-size vs significance scatter (reflects "ignores magnitude" weakness) | Dot plot |
| GSEA Prerank (`gp.prerank`) | Stratified NES bar plot + GSEA enrichment curves (top 3 terms per direction) + Network enrichment map | NES waterfall across all tested gene sets (reflects "handles both directions in one run") + leading-edge gene overlap heatmap (reflects "captures subtle distributed signals") | Dot plot |
| Both ORA + GSEA | All of the above for each | All of the above for each | Dot plot |

**Rules:**
- The **stratified bar plot** and **network enrichment map** are ALWAYS generated — do not skip them unless stated.
- The **dot plot** is generated ONLY when the user explicitly requests it (e.g., "show a dotplot", "make a dot plot").
- The **GSEA enrichment curve** (running score plot) is MANDATORY whenever GSEA is used — show the top 3 enriched gene sets per direction.
- The **method-specific additional diagnostics** should be included whenever running a full analysis, not just a one-off Enrichr/prerank call.
- All bar plots and dot plots must use `gseapy`'s built-in plotting functions (`gp.barplot`, `gseapy.plot.dotplot`) — NOT seaborn or matplotlib bar charts.

## Prerequisites

- **Python packages**: `gseapy`, `pandas`, `matplotlib`, `networkx` (for enrichment map), `seaborn` (for bar plot color grouping and the leading-edge overlap heatmap)
- **Internet access**: `enrich` and `prerank` fetch gene set libraries from the Enrichr API (requires connection); pass a local `.gmt` file path via `gene_sets=` to work offline

```bash
pip install gseapy

# Verify
python -c "import gseapy; print(gseapy.__version__)"
```

## Workflow

1. **Choose a method** using the decision rules above (ORA / GSEA Prerank / Standard GSEA).
2. **Prepare the input.** For ORA, derive up- and down-regulated gene lists from DE results (see `references/ora_analysis_reference.md` → *Load Gene Lists*). For GSEA Prerank, build the full ranked gene list, e.g. `log2FoldChange` sorted descending (see `references/gsea_prerank_analysis_reference.md` → *Load Ranked Gene List*).
3. **Run the analysis.** ORA runs separately per direction against one or more Enrichr databases (`gp.get_library_name(organism="human")` lists all 200+ options). GSEA Prerank runs once on the full list.
4. **Save results** as full and significance-filtered tables (`references/*.md` → *Save Results*).
5. **Generate the mandatory visualizations** (bar plot, network map, and — for GSEA — enrichment curves), then the method-specific additional diagnostics, per the [Required Visualization Outputs](#required-visualization-outputs) table.
6. **Add the dot plot only if the user explicitly asks for one.**
7. **For multiple comparisons** (e.g., several conditions or contrasts), repeat steps 2–6 per comparison and compare the resulting significant-term sets across runs.

See the [Reference Analysis Scripts](#bundled-resources) for the exact, copy-adaptable code for every step.

## Key Parameters

| Parameter | Default | Range/Options | Effect |
|-----------|---------|---------------|--------|
| `gene_sets` (enrichr/prerank) | required | string, list, or path to `.gmt` | Database name(s) from Enrichr; use `gp.get_library_name()` to list, or pass a local `.gmt` path to work offline |
| `organism` (enrichr) | `"human"` | `"human"`, `"mouse"`, `"fly"`, `"fish"`, `"worm"`, `"yeast"` | Species for gene set lookup |
| `cutoff` (enrichr) | `0.05` | 0–1 | Adjusted p-value cutoff for filtering results |
| `rnk` (prerank) | required | pd.Series | Gene → score mapping; sorted descending (log2FC recommended) |
| `permutation_num` (prerank) | `1000` | 100–10000 | Permutations for p-value estimation; 1000 for publication |
| `min_size` / `max_size` (prerank) | `15` / `500` | 5–50 / 100–2000 | Gene set size bounds; filters out too-small or too-generic sets |
| `threads` (prerank) | `4` | 1–64 | CPU threads for permutation |
| `seed` (prerank) | `None` | integer | Random seed for reproducibility |

## Expected Outputs

| Output pattern | Produced by | Description |
|-----------------|-------------|--------------|
| `ora_{up,down}_all_terms.tsv`, `ora_{up,down}_significant_terms.tsv` | ORA reference, *Save Results* | Full and adjusted-p-filtered ORA tables per direction |
| `ora_{up,down}_barplot.png`, `ora_{up,down}_network_map.png` | ORA reference | MANDATORY stratified bar plot + network enrichment map |
| `ora_{up,down}_dotplot.png` | ORA reference | Optional dot plot (only when requested) |
| `ora_updown_term_overlap.png`, `ora_updown_shared_terms.tsv` | ORA reference | Additional: shared vs unique enriched terms between up/down |
| `ora_size_vs_significance.png` | ORA reference | Additional: gene-overlap-count vs -log10(padj) bubble plot |
| `gsea_prerank_all_terms.tsv`, `gsea_prerank_significant_terms.tsv` | GSEA reference, *Save Results* | Full and FDR-filtered prerank tables |
| `gsea_nes_barplot.png`, `gsea_curve_*_NES_*.png`, `gsea_network_map.png` | GSEA reference | MANDATORY NES bar plot + top-3-per-direction enrichment curves + network map |
| `gsea_dotplot.png` | GSEA reference | Optional dot plot (only when requested) |
| `gsea_nes_waterfall.png` | GSEA reference | Additional: NES across all tested gene sets, both directions |
| `gsea_leading_edge_overlap.png` | GSEA reference | Additional: Jaccard overlap heatmap of leading-edge genes across top terms |

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `ConnectionError` in `enrichr`/`prerank` | No internet or Enrichr API down | Check https://maayanlab.cloud/Enrichr/; use local gene sets with `gene_sets="path/to/gmt"` |
| No significant terms returned | Gene list too small or wrong gene ID format | Use ≥10 genes; ensure HGNC symbols (not Ensembl IDs); convert with `pyensembl` |
| Prerank returns all NES ≈ 0 | Ranked list not sorted or too few genes | Verify `rnk` is sorted descending; check `min_size ≤` gene set sizes |
| `KeyError` in gene set | Gene set name misspelled | Use `gp.get_library_name()` to get exact database names |
| Low NES with FDR > 0.25 | Signal is weak or permutation count too low | Increase `permutation_num` to 1000; check raw p-values in `NOM p-val` |
| GSEA plot shows flat line | Gene set has no intersection with ranked list | Check gene naming; confirm gene set species matches data |
| Memory error during prerank | Large expression matrix + high permutations | Reduce `permutation_num`; use `prerank` instead of `gsea` when possible |
| Enrichr results differ from Java GSEA | Different gene set versions | Specify exact database version string from `gp.get_library_name()` |

## Bundled Resources

These are plain, top-to-bottom code snippets organized by step — not reusable helper functions. Load the relevant file on demand, jump to the section for the current step, and adapt that snippet's variable names in place against whatever DESeq2/edgeR results DataFrame (or `dds`/`ds` objects) the user already has in the current Python session.

- `references/ora_analysis_reference.md` — full ORA implementation: directional (up/down) Enrichr runs, mandatory bar/network plots, optional dot plot, plus the up/down term-overlap and gene-set-size-vs-significance diagnostics.
- `references/gsea_prerank_analysis_reference.md` — full GSEA Prerank implementation: single-run prerank, mandatory NES bar/enrichment-curve/network plots, optional dot plot, plus the NES waterfall and leading-edge overlap diagnostics.

## References
- Adapted from [SciAgent gseapy-genie-enrichment skill](https://github.com/jaechang-hits/SciAgent-Skills/blob/0d18706fe1a51239f12b395f046c8aa30fe632b4/skills/genomics-bioinformatics/rnaseq/gseapy-gene-enrichment/SKILL.md) to extend `gseapy` capabilities
- [GSEApy documentation](https://gseapy.readthedocs.io/) — official usage guide and API reference
- [GSEApy GitHub: zqfang/GSEApy](https://github.com/zqfang/GSEApy) — source code and examples
- Fang Z et al. (2023) "GSEApy: a comprehensive package for performing gene set enrichment analysis in Python" — *Bioinformatics* 39(1):btac757. [DOI:10.1093/bioinformatics/btac757](https://doi.org/10.1093/bioinformatics/btac757)
- Subramanian A et al. (2005) "Gene set enrichment analysis: A knowledge-based approach for interpreting genome-wide expression profiles" — *PNAS* 102(43):15545-15550. [DOI:10.1073/pnas.0506580102](https://doi.org/10.1073/pnas.0506580102)
- [Enrichr gene set databases](https://maayanlab.cloud/Enrichr/) — full list of 200+ available gene set libraries
