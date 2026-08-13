"""Shared fixtures for pathway-enrichment-analysis skill tests."""

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def deseq_results_df():
    """
    Synthetic DESeq2-style results DataFrame covering all directional cases
    used by the "Load Gene Lists" / "Load Ranked Gene List" reference steps:

    - GENE0, GENE1: upregulated (padj < 0.05, log2FC > 1)
    - GENE5, GENE6, GENE7: downregulated (padj < 0.05, log2FC < -1)
    - GENE2, GENE3, GENE4: below the significance / effect-size thresholds
    - GENE8, GENE9: missing log2FoldChange / padj, to test dropna handling
    """
    log2fc = [3.0, 2.5, 1.5, 0.2, -0.1, -1.5, -2.0, -3.5, np.nan, 0.5]
    padj = [0.001, 0.01, 0.2, 0.5, 0.9, 0.03, 0.001, 0.0001, 0.01, np.nan]
    index = [f"GENE{i}" for i in range(len(log2fc))]
    return pd.DataFrame({"log2FoldChange": log2fc, "padj": padj}, index=index)
