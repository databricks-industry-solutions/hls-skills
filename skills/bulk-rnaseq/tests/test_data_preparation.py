"""
Tests for SKILL.md > "Step 1: Data Preparation" and the related
"Troubleshooting Common Issues > Data Format Problems" section: loading
orientation, input validation, low-count / missing-metadata filtering, and
index-mismatch resolution.
"""
import numpy as np
import pandas as pd
import pytest


def _filter_data(counts_df, metadata, min_counts=10, condition_col=None):
    """Mirrors the "Data filtering" snippet in Step 1."""
    genes_to_keep = counts_df.columns[counts_df.sum(axis=0) >= min_counts]
    counts_df = counts_df[genes_to_keep]

    if condition_col and condition_col in metadata.columns:
        samples_to_keep = ~metadata[condition_col].isna()
        counts_df = counts_df.loc[samples_to_keep]
        metadata = metadata.loc[samples_to_keep]

    return counts_df, metadata


def test_transpose_converts_genes_by_samples_to_samples_by_genes(raw_counts_genes_by_samples):
    # "From CSV (typical format: genes × samples, needs transpose)"
    transposed = raw_counts_genes_by_samples.T
    assert transposed.shape == (
        raw_counts_genes_by_samples.shape[1],
        raw_counts_genes_by_samples.shape[0],
    )
    assert list(transposed.index) == list(raw_counts_genes_by_samples.columns)
    assert list(transposed.columns) == list(raw_counts_genes_by_samples.index)


def test_input_requirement_counts_must_be_non_negative(raw_counts_genes_by_samples):
    # Step 1 "Input requirements": "non-negative integer read counts"
    assert (raw_counts_genes_by_samples >= 0).all().all()

    invalid_counts = raw_counts_genes_by_samples.copy()
    invalid_counts.iloc[0, 0] = -5
    assert (invalid_counts < 0).any().any()


def test_filter_data_removes_low_count_genes(raw_counts_genes_by_samples, metadata_with_missing):
    counts_df = raw_counts_genes_by_samples.T
    filtered_counts, _ = _filter_data(counts_df, metadata_with_missing, min_counts=10)

    assert "GENE_LOW" not in filtered_counts.columns
    assert filtered_counts.shape[1] == raw_counts_genes_by_samples.shape[0] - 1


def test_filter_data_removes_samples_with_missing_condition(raw_counts_genes_by_samples, metadata_with_missing):
    counts_df = raw_counts_genes_by_samples.T
    filtered_counts, filtered_metadata = _filter_data(
        counts_df, metadata_with_missing, min_counts=0, condition_col="condition"
    )

    assert "S5" not in filtered_metadata.index
    assert "S5" not in filtered_counts.index
    assert filtered_metadata["condition"].isna().sum() == 0
    assert filtered_counts.shape[0] == 5


def test_filter_data_is_noop_when_condition_col_missing(raw_counts_genes_by_samples, metadata_with_missing):
    counts_df = raw_counts_genes_by_samples.T
    filtered_counts, filtered_metadata = _filter_data(
        counts_df, metadata_with_missing, min_counts=0, condition_col="nonexistent_column"
    )
    assert filtered_counts.shape[0] == counts_df.shape[0]
    assert filtered_metadata.shape[0] == metadata_with_missing.shape[0]


def test_index_mismatch_resolved_by_intersection():
    # Troubleshooting > "Index mismatch between counts and metadata":
    # "Take intersection if needed"
    counts_df = pd.DataFrame(
        {"g1": [1, 2, 3], "g2": [4, 5, 6]}, index=["S1", "S2", "S3"]
    )
    metadata = pd.DataFrame({"condition": ["a", "b"]}, index=["S1", "S2"])

    common = counts_df.index.intersection(metadata.index)
    counts_df = counts_df.loc[common]
    metadata = metadata.loc[common]

    assert list(counts_df.index) == ["S1", "S2"]
    assert list(metadata.index) == ["S1", "S2"]
    assert counts_df.shape[0] == 2


@pytest.mark.parametrize(
    "shape, needs_transpose",
    [
        ((6, 1000), False),  # samples x genes -- already correct
        ((1000, 6), True),  # genes x samples -- transpose needed
    ],
)
def test_transpose_detection_heuristic(shape, needs_transpose):
    # Troubleshooting > "All genes have zero counts": transpose when
    # counts_df.shape[1] < counts_df.shape[0]
    counts_df = pd.DataFrame(np.zeros(shape))
    assert (counts_df.shape[1] < counts_df.shape[0]) is needs_transpose
