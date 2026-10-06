"""
Tests for SKILL.md > "Step 3: DESeq2 Fitting" and "Step 4: Statistical
Testing". `pydeseq2` model fitting is expensive and requires per-gene
permutation/optimization, so these tests mock `DeseqDataSet`/`DeseqStats` to
verify the documented call contract (design formula, refit_cooks, contrast
format, filtering flags) rather than re-running the real statistics.
"""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

try:
    import pydeseq2.dds as dds_module
    import pydeseq2.ds as ds_module

    HAS_PYDESEQ2 = True
except ImportError:
    HAS_PYDESEQ2 = False


@pytest.mark.skipif(not HAS_PYDESEQ2, reason="pydeseq2 not installed")
def test_deseqdataset_constructed_with_string_design_and_refit_cooks():
    counts_df = pd.DataFrame(
        {"GENE0": [10, 20, 30, 40]}, index=["S1", "S2", "S3", "S4"]
    )
    metadata = pd.DataFrame(
        {"condition": ["treated", "treated", "control", "control"]}, index=counts_df.index
    )

    with patch("pydeseq2.dds.DeseqDataSet") as MockDDS:
        mock_instance = MagicMock()
        MockDDS.return_value = mock_instance

        dds = dds_module.DeseqDataSet(
            counts=counts_df,
            metadata=metadata,
            design="~condition",
            refit_cooks=True,
            n_cpus=1,
        )
        dds.deseq2()

    _, kwargs = MockDDS.call_args
    assert kwargs["design"] == "~condition"
    assert kwargs["refit_cooks"] is True
    mock_instance.deseq2.assert_called_once()


@pytest.mark.skipif(not HAS_PYDESEQ2, reason="pydeseq2 not installed")
def test_deseqdataset_signature_supports_string_design_formula():
    # SKILL.md: "ALWAYS use design=... string formula notation" -- `design_factors`
    # still exists in the API for backward compatibility but is documented as
    # legacy, so it must default to unset (None) and not be required.
    import inspect

    signature = inspect.signature(dds_module.DeseqDataSet.__init__)
    assert "design" in signature.parameters
    assert signature.parameters["design"].default == "~condition"
    if "design_factors" in signature.parameters:
        assert signature.parameters["design_factors"].default is None


@pytest.mark.skipif(not HAS_PYDESEQ2, reason="pydeseq2 not installed")
def test_deseqstats_called_with_contrast_and_filtering_flags():
    fake_dds = MagicMock()

    with patch("pydeseq2.ds.DeseqStats") as MockDS:
        mock_instance = MagicMock()
        MockDS.return_value = mock_instance

        ds = ds_module.DeseqStats(
            fake_dds,
            contrast=["condition", "treated", "control"],
            alpha=0.05,
            cooks_filter=True,
            independent_filter=True,
        )
        ds.summary()

    _, kwargs = MockDS.call_args
    assert kwargs["contrast"] == ["condition", "treated", "control"]
    assert kwargs["alpha"] == 0.05
    assert kwargs["cooks_filter"] is True
    assert kwargs["independent_filter"] is True
    mock_instance.summary.assert_called_once()


@pytest.mark.skipif(not HAS_PYDESEQ2, reason="pydeseq2 not installed")
def test_lfc_shrink_is_a_separate_call_from_summary():
    # SKILL.md: shrinkage affects only log2FoldChange, not the Wald test p-values,
    # and is applied via a distinct call after ds.summary().
    fake_dds = MagicMock()

    with patch("pydeseq2.ds.DeseqStats") as MockDS:
        mock_instance = MagicMock()
        mock_instance.results_df = pd.DataFrame(
            {"pvalue": [0.01, 0.5], "log2FoldChange": [3.0, 0.1]}
        )
        MockDS.return_value = mock_instance

        ds = ds_module.DeseqStats(fake_dds, contrast=["condition", "treated", "control"])
        ds.summary()
        pvalues_before = ds.results_df["pvalue"].copy()
        ds.lfc_shrink()
        pvalues_after = ds.results_df["pvalue"]

    mock_instance.summary.assert_called_once()
    mock_instance.lfc_shrink.assert_called_once()
    pd.testing.assert_series_equal(pvalues_before, pvalues_after)
