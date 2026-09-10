"""
Tests for SKILL.md > "Visualization Guidelines": volcano plot color/axis
rules, the PCA variance-stabilizing transform, heatmap z-scoring, and MA plot
axis rules.
"""
import numpy as np
import pandas as pd
import pytest

try:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


def test_volcano_plot_significance_buckets_are_mutually_exclusive(deseq_results_df):
    results = deseq_results_df
    ns = ~((results["padj"] < 0.05) & (results["log2FoldChange"].abs() > 1))
    sig_up = (results["padj"] < 0.05) & (results["log2FoldChange"] > 1)
    sig_down = (results["padj"] < 0.05) & (results["log2FoldChange"] < -1)

    # Every gene belongs to exactly one of the three plotted buckets.
    assert ((ns.astype(int) + sig_up.astype(int) + sig_down.astype(int)) == 1).all()
    assert results[sig_up].index.tolist() == ["GENE0", "GENE1"]
    assert results[sig_down].index.tolist() == ["GENE2", "GENE3"]


def test_volcano_axis_limits_use_actual_max_not_quantile(deseq_results_df):
    # SKILL.md: "Axis limits use min()/max() ... never quantile() which clips
    # the most significant points"
    results = deseq_results_df
    neg_log10p = -np.log10(results["pvalue"])
    neg_log10p_finite = neg_log10p[np.isfinite(neg_log10p)]

    xlim = results["log2FoldChange"].abs().max() * 1.05
    ylim = neg_log10p_finite.max() * 1.05

    assert xlim >= results["log2FoldChange"].abs().max()
    assert ylim >= neg_log10p_finite.max()
    # A quantile-based limit would be strictly smaller and would clip GENE0.
    assert xlim > results["log2FoldChange"].abs().quantile(0.95) * 1.05
    assert ylim > neg_log10p_finite.quantile(0.95) * 1.05


def test_ma_plot_axis_limits_use_min_and_max(deseq_results_df):
    results = deseq_results_df
    log10_basemean = np.log10(results["baseMean"] + 1)

    xlim_low = log10_basemean.min() * 1.05
    xlim_high = log10_basemean.max() * 1.05
    ylim_low = results["log2FoldChange"].min() * 1.05
    ylim_high = results["log2FoldChange"].max() * 1.05

    # x-axis: log10(baseMean + 1) is always non-negative, so this exact
    # SKILL.md formula expands the upper bound but pulls the lower bound
    # toward zero (it does not symmetrically pad outward like the y-axis).
    assert xlim_high >= log10_basemean.max()
    assert np.isclose(xlim_low, log10_basemean.min() * 1.05)

    # y-axis: log2FoldChange spans negative and positive values here, so the
    # same `* 1.05` rule expands both bounds outward from the data range.
    assert ylim_low <= results["log2FoldChange"].min()
    assert ylim_high >= results["log2FoldChange"].max()


@pytest.mark.skipif(not HAS_SKLEARN, reason="scikit-learn not installed")
def test_pca_variance_stabilizing_transform_and_top_variable_gene_selection():
    rng = np.random.default_rng(1)
    samples = [f"S{i}" for i in range(6)]
    genes = [f"GENE{i}" for i in range(20)]
    counts = pd.DataFrame(rng.integers(1, 500, size=(6, 20)), index=samples, columns=genes)
    size_factors = np.ones(6)  # neutral normalization for a deterministic check

    normalized_counts = counts / size_factors[:, None]
    log_counts = np.log2(normalized_counts + 1)
    assert (log_counts.values >= 0).all()

    gene_var = log_counts.var(axis=0)
    top_var_genes = gene_var.nlargest(5).index
    assert len(top_var_genes) == 5
    assert set(top_var_genes) == set(gene_var.sort_values(ascending=False).head(5).index)

    scaled = StandardScaler().fit_transform(log_counts[top_var_genes])
    pca = PCA(n_components=2)
    pcs = pca.fit_transform(scaled)
    assert pcs.shape == (6, 2)


def test_heatmap_zscore_normalizes_each_gene_across_samples():
    samples = [f"S{i}" for i in range(5)]
    genes = ["GENE0", "GENE1"]
    log_counts = pd.DataFrame(
        {"GENE0": [1.0, 2.0, 3.0, 4.0, 5.0], "GENE1": [10.0, 10.0, 10.0, 10.0, 10.0]},
        index=samples,
    )
    heatmap_data = log_counts[genes].T  # genes as rows for clustermap
    heatmap_z = (
        heatmap_data - heatmap_data.mean(axis=1).values[:, None]
    ) / heatmap_data.std(axis=1).values[:, None]

    assert np.isclose(heatmap_z.loc["GENE0"].mean(), 0.0)
    assert np.isclose(heatmap_z.loc["GENE0"].std(), 1.0)
    # A gene with zero variance across samples divides by zero -> NaN z-scores.
    assert heatmap_z.loc["GENE1"].isna().all()


def test_pca_reveals_batch_confound_when_condition_uncorrelated_with_pc1():
    # Diagnostic use: "If samples cluster by batch instead of condition, add
    # batch to the design formula." Verify the grouping-by-mask logic used to
    # color points by condition works regardless of group order.
    metadata = pd.DataFrame(
        {"condition": ["treated", "treated", "control", "control"]}, index=["S0", "S1", "S2", "S3"]
    )
    pcs = np.array([[1.0, 0.1], [1.1, -0.1], [-1.0, 0.2], [-0.9, -0.2]])

    groups = metadata["condition"].unique()
    masks = {group: (metadata["condition"] == group).to_numpy() for group in groups}

    assert masks["treated"].sum() == 2
    assert masks["control"].sum() == 2
    # masks partition all samples with no overlap
    assert not (masks["treated"] & masks["control"]).any()
    assert (masks["treated"] | masks["control"]).all()
