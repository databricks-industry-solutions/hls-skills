import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def raw_counts_genes_by_samples():
    """
    Synthetic count matrix in genes x samples orientation, as typically loaded
    from a CSV before the mandatory `.T` transpose described in
    "Step 1: Data Preparation".

    GENE_LOW has < 10 total reads across samples and should be dropped by the
    low-count gene filter.
    """
    genes = [f"GENE{i}" for i in range(6)] + ["GENE_LOW"]
    samples = [f"S{i}" for i in range(6)]
    rng = np.random.default_rng(0)
    data = rng.integers(20, 200, size=(len(genes) - 1, len(samples)))
    low_row = np.array([[1, 0, 2, 0, 1, 0]])
    counts = np.vstack([data, low_row])
    return pd.DataFrame(counts, index=genes, columns=samples)


@pytest.fixture
def metadata_with_missing():
    """
    Metadata aligned to `raw_counts_genes_by_samples` samples, with one sample
    (S5) missing the condition label -- exercises the "Remove samples with
    missing metadata" filtering step.
    """
    return pd.DataFrame(
        {"condition": ["treated", "treated", "treated", "control", "control", np.nan]},
        index=[f"S{i}" for i in range(6)],
    )


@pytest.fixture
def deseq_results_df():
    """
    Synthetic DESeq2 `ds.results_df`-style table covering the directional and
    edge cases exercised throughout "Result Interpretation" and the
    visualization sections of SKILL.md:

    - GENE0, GENE1: significant & upregulated (padj < 0.05, log2FC > 1)
    - GENE2, GENE3: significant & downregulated (padj < 0.05, log2FC < -1)
    - GENE4, GENE5: not significant (padj >= 0.05 or |log2FC| <= 1)
    - GENE6: padj is NaN (e.g. excluded by independent filtering)
    """
    genes = [f"GENE{i}" for i in range(7)]
    return pd.DataFrame(
        {
            "baseMean": [500.0, 300.0, 800.0, 150.0, 50.0, 900.0, 5.0],
            "log2FoldChange": [3.0, 1.8, -2.5, -4.0, 0.3, -0.5, 2.0],
            "lfcSE": [0.2, 0.3, 0.25, 0.4, 0.2, 0.15, 0.9],
            "stat": [15.0, 6.0, -10.0, -10.0, 1.5, -3.3, 2.2],
            "pvalue": [1e-8, 1e-4, 1e-7, 1e-6, 0.4, 0.001, 0.03],
            "padj": [1e-6, 0.01, 1e-5, 1e-4, 0.6, 0.06, np.nan],
        },
        index=genes,
    )
