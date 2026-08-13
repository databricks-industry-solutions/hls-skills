"""
Tests for SKILL.md > "Step 6: Result Export", "Result Interpretation", and
the "No Significant Genes" diagnostics in Troubleshooting.
"""
import numpy as np
import pandas as pd


def test_significant_gene_filtering_uses_padj(deseq_results_df):
    significant = deseq_results_df[deseq_results_df.padj < 0.05]
    assert set(significant.index) == {"GENE0", "GENE1", "GENE2", "GENE3"}


def test_significant_filter_excludes_nan_padj_gene(deseq_results_df):
    # NaN comparisons are always False, so genes with no padj (e.g. filtered
    # out by independent filtering) are correctly excluded, not silently kept.
    significant = deseq_results_df[deseq_results_df.padj < 0.05]
    assert "GENE6" not in significant.index


def test_significance_and_effect_size_combined_filter(deseq_results_df):
    sig_and_large = deseq_results_df[
        (deseq_results_df.padj < 0.05) & (deseq_results_df.log2FoldChange.abs() > 1)
    ]
    assert set(sig_and_large.index) == {"GENE0", "GENE1", "GENE2", "GENE3"}


def test_up_down_regulated_split(deseq_results_df):
    significant = deseq_results_df[deseq_results_df.padj < 0.05]
    upregulated = significant[significant.log2FoldChange > 0]
    downregulated = significant[significant.log2FoldChange < 0]

    assert set(upregulated.index) == {"GENE0", "GENE1"}
    assert set(downregulated.index) == {"GENE2", "GENE3"}
    assert set(upregulated.index).isdisjoint(downregulated.index)


def test_ranking_by_padj(deseq_results_df):
    top = deseq_results_df.sort_values("padj").head(3)
    assert list(top.index) == ["GENE0", "GENE2", "GENE3"]


def test_ranking_by_absolute_log2fc_uses_shrunk_style_values(deseq_results_df):
    df = deseq_results_df.copy()
    df["abs_lfc"] = df["log2FoldChange"].abs()
    top = df.sort_values("abs_lfc", ascending=False).head(1)
    assert top.index[0] == "GENE3"  # |-4.0| is the largest magnitude


def test_combined_score_ranking_weights_significance_and_effect_size(deseq_results_df):
    df = deseq_results_df.dropna(subset=["padj"]).copy()
    df["score"] = -np.log10(df["padj"]) * df["log2FoldChange"].abs()
    top = df.sort_values("score", ascending=False).head(1)
    assert top.index[0] == "GENE0"  # padj=1e-6, log2FC=3.0 -> highest combined score


def test_top_genes_by_raw_pvalue_diagnostic(deseq_results_df):
    # Troubleshooting > "No Significant Genes" diagnostic
    top = deseq_results_df.nsmallest(3, "pvalue")
    assert list(top.index) == ["GENE0", "GENE2", "GENE3"]


def test_size_factors_close_to_one_diagnostic():
    # Troubleshooting > "No Significant Genes" diagnostic: size factors near 1
    # indicate normalization behaved as expected.
    size_factors = np.array([0.95, 1.02, 0.98, 1.10, 0.90, 1.05])
    assert np.allclose(size_factors, 1.0, atol=0.15)


def test_save_results_writes_full_significant_and_sorted_tables(tmp_path, deseq_results_df):
    output_dir = tmp_path / "results"
    output_dir.mkdir()

    deseq_results_df.to_csv(output_dir / "deseq2_results.csv")
    significant = deseq_results_df[deseq_results_df.padj < 0.05]
    significant.to_csv(output_dir / "significant_genes.csv")
    deseq_results_df.sort_values("padj").to_csv(output_dir / "results_sorted_by_padj.csv")

    assert (output_dir / "deseq2_results.csv").exists()
    assert (output_dir / "significant_genes.csv").exists()
    assert (output_dir / "results_sorted_by_padj.csv").exists()

    reloaded_full = pd.read_csv(output_dir / "deseq2_results.csv", index_col=0)
    reloaded_sig = pd.read_csv(output_dir / "significant_genes.csv", index_col=0)
    assert len(reloaded_full) == len(deseq_results_df)
    assert len(reloaded_sig) == 4
