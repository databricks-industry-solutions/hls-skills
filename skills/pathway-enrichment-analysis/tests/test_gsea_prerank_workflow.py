"""
Unit tests for the key steps documented in
``references/gsea_prerank_analysis_reference.md``.

Each test re-creates the exact pandas/numpy logic shown in the corresponding
reference section against small synthetic DataFrames/Series. The call into
gseapy that would hit the permutation engine (``gp.prerank``) is mocked so
the tests run offline; steps that are pure data-wrangling (ranking, term
selection, coloring, Jaccard similarity) are tested directly with no
mocking needed.
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


# ---------------------------------------------------------------------------
# Step: Load Ranked Gene List
# ---------------------------------------------------------------------------

def test_load_ranked_list_from_deseq_results(deseq_results_df):
    ranked = deseq_results_df["log2FoldChange"].dropna().sort_values(ascending=False)
    ranked = ranked[~ranked.index.duplicated(keep="first")]

    # sorted descending
    assert ranked.is_monotonic_decreasing
    # the NaN log2FC gene (GENE8) must be dropped, not ranked
    assert "GENE8" not in ranked.index
    # GSEA Prerank uses the FULL ranked list, not just the significant subset
    assert len(ranked) == 9
    assert ranked.index[0] == "GENE0"  # highest log2FC


def test_load_ranked_list_deduplicates_keeping_first_occurrence():
    df = pd.DataFrame(
        {"log2FoldChange": [1.0, np.nan, -2.0, 3.0, 3.0]},
        index=["A", "B", "C", "D", "D"],
    )
    ranked = df["log2FoldChange"].dropna().sort_values(ascending=False)
    ranked = ranked[~ranked.index.duplicated(keep="first")]

    assert list(ranked.index) == ["D", "A", "C"]
    assert ranked.tolist() == [3.0, 1.0, -2.0]
    assert "B" not in ranked.index


def test_load_ranked_list_from_rnk_file(tmp_path):
    rnk_path = tmp_path / "ranked_genes.rnk"
    rnk_path.write_text("GENE1\t2.5\nGENE2\t-1.0\nGENE3\t0.5\n")

    ranked = pd.read_csv(rnk_path, sep=None, engine="python", header=None, index_col=0).iloc[:, 0]

    assert ranked.loc["GENE1"] == 2.5
    assert ranked.loc["GENE2"] == -1.0
    assert len(ranked) == 3


# ---------------------------------------------------------------------------
# Step: Run GSEA Prerank
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_GSEAPY, reason="gseapy not installed")
def test_run_prerank_called_once_on_full_ranked_list(tmp_path):
    ranked = pd.Series([2.0, 1.0, -1.0, -2.0], index=["A", "B", "C", "D"])

    with patch("gseapy.prerank") as mock_prerank:
        mock_prerank.return_value = MagicMock()
        gp.prerank(
            rnk=ranked, gene_sets="MSigDB_Hallmark_2020", threads=4,
            min_size=15, max_size=500, permutation_num=1000,
            outdir=str(tmp_path / "prerank"), seed=42, verbose=True,
        )

    # GSEA Prerank handles both directions in a SINGLE run
    assert mock_prerank.call_count == 1
    call = mock_prerank.call_args
    assert call.kwargs["rnk"].equals(ranked)
    assert call.kwargs["permutation_num"] == 1000
    assert call.kwargs["seed"] == 42


# ---------------------------------------------------------------------------
# Step: Save Results
# ---------------------------------------------------------------------------

def test_save_results_filters_by_fdr_and_sorts_by_nes_descending():
    res_df = pd.DataFrame({
        "Name": ["a"] * 4,
        "Term": ["T1", "T2", "T3", "T4"],
        "NES": ["1.5", "-2.1", "0.5", "3.0"],
        "FDR q-val": ["0.01", "0.5", "0.3", "0.001"],
    })
    res_df["NES"] = res_df["NES"].astype(float)
    res_df["FDR q-val"] = res_df["FDR q-val"].astype(float)

    fdr_cutoff = 0.25
    sig_df = res_df[res_df["FDR q-val"] < fdr_cutoff].sort_values("NES", ascending=False)

    assert list(sig_df["Term"]) == ["T4", "T1"]
    assert sig_df["NES"].is_monotonic_decreasing
    assert (sig_df["FDR q-val"] < fdr_cutoff).all()


# ---------------------------------------------------------------------------
# Step: Enrichment Curves (top positive/negative NES term selection)
# ---------------------------------------------------------------------------

def test_top_positive_and_negative_nes_terms_selected():
    sig_df = pd.DataFrame({
        "Term": ["T1", "T2", "T3", "T4", "T5"],
        "NES": [2.5, 1.8, -1.2, -3.0, 0.5],
    })
    top_pos = sig_df.sort_values("NES", ascending=False).head(3)["Term"].tolist()
    top_neg = sig_df.sort_values("NES", ascending=True).head(3)["Term"].tolist()

    assert top_pos == ["T1", "T2", "T5"]
    assert top_neg == ["T4", "T3", "T5"]
    # both directions are pulled from opposite ends of the same ranking
    assert top_pos[0] != top_neg[0]


def test_top_terms_selection_handles_fewer_than_requested_count():
    sig_df = pd.DataFrame({"Term": ["Only positive"], "NES": [1.0]})
    top_pos = sig_df.sort_values("NES", ascending=False).head(3)["Term"].tolist()
    assert top_pos == ["Only positive"]


# ---------------------------------------------------------------------------
# Step: Network Enrichment Map (column rename before reuse)
# ---------------------------------------------------------------------------

def test_network_map_renames_fdr_column_for_reuse():
    sig_df = pd.DataFrame({"Term": ["T1", "T2"], "FDR q-val": [0.01, 0.2]})
    map_df = sig_df.rename(columns={"FDR q-val": "Adjusted P-value"})

    assert "Adjusted P-value" in map_df.columns
    assert "FDR q-val" not in map_df.columns
    assert map_df["Adjusted P-value"].tolist() == [0.01, 0.2]


def test_network_map_guard_skips_when_fewer_than_two_significant_terms():
    sig_df = pd.DataFrame({"Term": ["Only one term"], "FDR q-val": [0.01]})
    assert len(sig_df) < 2  # matches the "skip network map" guard condition


# ---------------------------------------------------------------------------
# Step: NES Waterfall (additional diagnostic) — coloring logic
# ---------------------------------------------------------------------------

def test_nes_waterfall_color_assignment_reflects_direction_and_significance():
    res_df = pd.DataFrame({
        "NES": [2.5, 1.0, -0.5, -2.0],
        "FDR q-val": [0.01, 0.3, 0.4, 0.02],
    })
    fdr_cutoff = 0.25
    ordered = res_df.sort_values("NES", ascending=False).reset_index(drop=True)
    sig_mask = ordered["FDR q-val"] < fdr_cutoff
    colors = [
        ("red" if nes > 0 else "blue") if sig else "lightgrey"
        for nes, sig in zip(ordered["NES"], sig_mask)
    ]

    # significant positive NES -> red, significant negative NES -> blue,
    # non-significant (regardless of sign) -> lightgrey
    assert colors == ["red", "lightgrey", "lightgrey", "blue"]


def test_nes_waterfall_preserves_both_directions_in_one_ordering():
    res_df = pd.DataFrame({
        "NES": [-1.0, 3.0, 0.2, -2.5],
        "FDR q-val": [0.01, 0.01, 0.9, 0.01],
    })
    ordered = res_df.sort_values("NES", ascending=False).reset_index(drop=True)

    # GSEA Prerank surfaces both up (positive) and down (negative) NES
    # gene sets from a single ordered table -- ORA would need two separate runs
    assert ordered["NES"].max() > 0
    assert ordered["NES"].min() < 0
    assert ordered["NES"].is_monotonic_decreasing


# ---------------------------------------------------------------------------
# Step: Leading-Edge Gene Overlap Heatmap (additional diagnostic)
# ---------------------------------------------------------------------------

def test_leading_edge_jaccard_similarity_matrix():
    sig_df = pd.DataFrame({
        "Term": ["T1", "T2", "T3"],
        "FDR q-val": [0.01, 0.02, 0.03],
        "Lead_genes": ["A;B;C;D", "C;D;E;F", "G;H"],
    })
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

    t1_idx, t2_idx, t3_idx = terms.index("T1"), terms.index("T2"), terms.index("T3")
    # T1={A,B,C,D} vs T2={C,D,E,F}: intersection {C,D}, union has 6 genes -> 2/6
    assert jaccard[t1_idx, t2_idx] == pytest.approx(2 / 6)
    # T1 and T3={G,H} share no genes
    assert jaccard[t1_idx, t3_idx] == 0.0
    # a term is always fully similar to itself
    assert np.allclose(np.diag(jaccard), 1.0)
    # similarity is symmetric
    assert np.allclose(jaccard, jaccard.T)


def test_leading_edge_guard_skips_when_column_missing():
    sig_df = pd.DataFrame({"Term": ["T1", "T2"], "FDR q-val": [0.01, 0.02]})
    assert "Lead_genes" not in sig_df.columns  # matches the "skip heatmap" guard condition
