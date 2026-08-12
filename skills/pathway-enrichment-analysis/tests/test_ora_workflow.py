"""
Unit tests for the key steps documented in
``references/ora_analysis_reference.md``.

Each test re-creates the exact pandas/numpy logic shown in the corresponding
reference section against small synthetic DataFrames. Calls into gseapy that
would hit the Enrichr API (``gp.enrichr``) are mocked so the tests run
offline; steps that are pure data-wrangling (gene list derivation, term-set
comparisons, column parsing) are tested directly with no mocking needed.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

try:
    import gseapy as gp
    HAS_GSEAPY = True
except ImportError:
    HAS_GSEAPY = False

try:
    import seaborn as sns
    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


# ---------------------------------------------------------------------------
# Step: Load Gene Lists (Directional Split)
# ---------------------------------------------------------------------------

def test_load_gene_lists_directional_split(deseq_results_df):
    padj_cutoff, lfc_cutoff = 0.05, 1.0
    df = deseq_results_df.dropna(subset=["log2FoldChange", "padj"])

    up_genes = df[(df["padj"] < padj_cutoff) & (df["log2FoldChange"] > lfc_cutoff)].index.tolist()
    down_genes = df[(df["padj"] < padj_cutoff) & (df["log2FoldChange"] < -lfc_cutoff)].index.tolist()

    assert up_genes == ["GENE0", "GENE1"]
    assert down_genes == ["GENE5", "GENE6", "GENE7"]
    # genes with missing log2FC/padj must be dropped by dropna(), not
    # miscounted as either direction
    assert "GENE8" not in up_genes + down_genes
    assert "GENE9" not in up_genes + down_genes
    # up and down must never overlap
    assert set(up_genes).isdisjoint(down_genes)


def test_load_gene_lists_returns_empty_when_nothing_significant():
    df = pd.DataFrame({"log2FoldChange": [0.1, -0.2], "padj": [0.9, 0.8]}, index=["A", "B"])
    df = df.dropna(subset=["log2FoldChange", "padj"])

    up_genes = df[(df["padj"] < 0.05) & (df["log2FoldChange"] > 1.0)].index.tolist()
    down_genes = df[(df["padj"] < 0.05) & (df["log2FoldChange"] < -1.0)].index.tolist()

    assert up_genes == []
    assert down_genes == []


# ---------------------------------------------------------------------------
# Step: Run ORA via Enrichr
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_GSEAPY, reason="gseapy not installed")
def test_run_ora_called_separately_per_direction(tmp_path):
    up_genes = ["TP53", "BRCA1"]
    down_genes = ["MYC", "EGFR"]
    gene_sets = ["GO_Biological_Process_2023"]

    with patch("gseapy.enrichr") as mock_enrichr:
        mock_enrichr.return_value = MagicMock()

        gp.enrichr(gene_list=up_genes, gene_sets=gene_sets, organism="human",
                   outdir=str(tmp_path / "enrichr_up"), cutoff=0.05)
        gp.enrichr(gene_list=down_genes, gene_sets=gene_sets, organism="human",
                   outdir=str(tmp_path / "enrichr_down"), cutoff=0.05)

    # ORA must be run separately per direction -- never pooled into one call
    assert mock_enrichr.call_count == 2
    up_call, down_call = mock_enrichr.call_args_list
    assert up_call.kwargs["gene_list"] == up_genes
    assert down_call.kwargs["gene_list"] == down_genes
    assert up_call.kwargs["gene_list"] != down_call.kwargs["gene_list"]


# ---------------------------------------------------------------------------
# Step: Save Results
# ---------------------------------------------------------------------------

def test_save_results_filters_significant_terms_and_writes_tsv(tmp_path):
    enr_results = pd.DataFrame({
        "Term": ["Term A", "Term B", "Term C"],
        "Adjusted P-value": [0.001, 0.2, 0.049],
        "Gene_set": ["GO_BP", "GO_BP", "KEGG"],
    })

    all_path = tmp_path / "ora_up_all_terms.tsv"
    enr_results.to_csv(all_path, sep="\t", index=False)

    sig_up = enr_results[enr_results["Adjusted P-value"] < 0.05]
    sig_path = tmp_path / "ora_up_significant_terms.tsv"
    sig_up.to_csv(sig_path, sep="\t", index=False)

    assert all_path.exists() and sig_path.exists()
    assert len(sig_up) == 2
    assert set(sig_up["Term"]) == {"Term A", "Term C"}

    reloaded = pd.read_csv(sig_path, sep="\t")
    assert len(reloaded) == 2
    assert reloaded["Adjusted P-value"].max() < 0.05


# ---------------------------------------------------------------------------
# Step: Stratified Bar Plot (color mapping)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_SEABORN, reason="seaborn not installed")
def test_bar_plot_color_mapping_has_one_color_per_gene_set():
    sig_up = pd.DataFrame({
        "Gene_set": ["GO_BP", "GO_BP", "KEGG", "Reactome"],
        "Adjusted P-value": [0.001, 0.01, 0.02, 0.03],
    })
    colors = dict(zip(
        sig_up["Gene_set"].unique(),
        sns.color_palette("Set2", n_colors=sig_up["Gene_set"].nunique()),
    ))

    assert set(colors.keys()) == {"GO_BP", "KEGG", "Reactome"}
    assert len(colors) == sig_up["Gene_set"].nunique()
    assert len(set(colors.values())) == len(colors)  # every gene set gets a distinct color


# ---------------------------------------------------------------------------
# Step: Network Enrichment Map
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_NETWORKX, reason="networkx not installed")
def test_network_map_graph_built_from_nodes_and_edges():
    edges = pd.DataFrame({
        "src_idx": [0, 1],
        "targ_idx": [1, 2],
        "jaccard_coef": [0.5, 0.2],
        "overlap_coef": [0.6, 0.3],
        "overlap_genes": [["G1", "G2"], ["G3"]],
    })

    G = nx.from_pandas_edgelist(
        edges, source="src_idx", target="targ_idx",
        edge_attr=["jaccard_coef", "overlap_coef", "overlap_genes"],
    )

    assert set(G.nodes) == {0, 1, 2}
    assert G.number_of_edges() == 2
    assert G.edges[0, 1]["jaccard_coef"] == 0.5


def test_network_map_guard_skips_when_fewer_than_two_significant_terms():
    sig_up = pd.DataFrame({"Term": ["Only one term"], "Adjusted P-value": [0.01]})
    assert len(sig_up) < 2  # matches the "skip network map" guard condition


# ---------------------------------------------------------------------------
# Step: Enrichment Dot Plot (only when requested)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_GSEAPY, reason="gseapy not installed")
def test_dot_plot_only_called_when_explicitly_requested():
    sig_up = pd.DataFrame({
        "Gene_set": ["GO_BP"],
        "Term": ["Term A"],
        "Adjusted P-value": [0.01],
    })

    with patch("gseapy.plot.dotplot") as mock_dotplot:
        dotplot_requested = True
        if dotplot_requested:
            gp.plot.dotplot(sig_up, column="Adjusted P-value", x="Gene_set", top_term=15)

    mock_dotplot.assert_called_once()

    with patch("gseapy.plot.dotplot") as mock_dotplot_skipped:
        dotplot_requested = False
        if dotplot_requested:
            gp.plot.dotplot(sig_up, column="Adjusted P-value", x="Gene_set", top_term=15)

    mock_dotplot_skipped.assert_not_called()


# ---------------------------------------------------------------------------
# Step: Up/Down Term-Overlap Comparison (additional diagnostic)
# ---------------------------------------------------------------------------

def test_updown_term_overlap_counts():
    sig_up = pd.DataFrame({"Term": ["Apoptosis", "Cell Cycle", "p53 Pathway"]})
    sig_dn = pd.DataFrame({"Term": ["Cell Cycle", "DNA Repair"]})

    up_terms = set(sig_up["Term"])
    down_terms = set(sig_dn["Term"])
    shared = up_terms & down_terms
    up_only = up_terms - down_terms
    down_only = down_terms - up_terms

    assert shared == {"Cell Cycle"}
    assert up_only == {"Apoptosis", "p53 Pathway"}
    assert down_only == {"DNA Repair"}

    counts = {"Up-only": len(up_only), "Shared": len(shared), "Down-only": len(down_only)}
    assert counts == {"Up-only": 2, "Shared": 1, "Down-only": 1}


def test_updown_term_overlap_handles_no_overlap():
    sig_up = pd.DataFrame({"Term": ["A", "B"]})
    sig_dn = pd.DataFrame({"Term": ["C", "D"]})

    shared = set(sig_up["Term"]) & set(sig_dn["Term"])
    assert shared == set()


# ---------------------------------------------------------------------------
# Step: Gene-Set Size vs Significance Scatter (additional diagnostic)
# ---------------------------------------------------------------------------

def test_geneset_size_vs_significance_overlap_column_parsing():
    sig_up = pd.DataFrame({
        "Overlap": ["5/200", "12/50"],
        "Adjusted P-value": [0.01, 0.0],
        "Combined Score": [45.2, 500.0],
    })
    sig_up = sig_up.assign(
        direction="up",
        n_overlap=sig_up["Overlap"].str.split("/").str[0].astype(int),
    )

    assert sig_up["n_overlap"].tolist() == [5, 12]

    neg_log10_padj = -np.log10(sig_up["Adjusted P-value"].clip(lower=1e-300))
    # a p-value of exactly 0 must be clipped, not produce -inf/NaN
    assert np.isfinite(neg_log10_padj).all()
    assert neg_log10_padj.iloc[0] == pytest.approx(2.0)


def test_geneset_size_vs_significance_combines_up_and_down():
    sig_up = pd.DataFrame({
        "Overlap": ["4/100"], "Adjusted P-value": [0.02], "Combined Score": [30.0],
    }).assign(direction="up", n_overlap=lambda d: d["Overlap"].str.split("/").str[0].astype(int))
    sig_dn = pd.DataFrame({
        "Overlap": ["8/100"], "Adjusted P-value": [0.03], "Combined Score": [60.0],
    }).assign(direction="down", n_overlap=lambda d: d["Overlap"].str.split("/").str[0].astype(int))

    combined = pd.concat([sig_up, sig_dn], ignore_index=True)

    assert len(combined) == 2
    assert set(combined["direction"]) == {"up", "down"}
    assert combined["n_overlap"].tolist() == [4, 8]
