#!/usr/bin/env python3
"""Generate synthetic h5ad files for sc-rnaseq skill evaluation.

Creates 5 h5ad variants from pertpy's Stephenson 2021 subsampled dataset:
  1. sample_symbols.h5ad  — gene symbols as var_names, raw counts in .X
  2. sample_ensembl.h5ad  — Ensembl IDs as var_names, symbols in var['feature_name']
  3. sample_processed.h5ad — normalized/log1p in .X, raw counts in .raw
  4. donor1.h5ad           — subset from one donor (for multi-sample task)
  5. donor2.h5ad           — subset from another donor (for multi-sample task)

Run BEFORE either eval arm:
  python3 generate_data.py
  # or in a Databricks notebook cell

Output directory read from SKILL_EVAL_DATA_DIR env var,
falling back to OUT_DIR constant below.
"""

import os
import shutil
import numpy as np

OUT_DIR = os.environ.get(
    "SKILL_EVAL_DATA_DIR",
    "/Volumes/ppareek/rd/eval/sc_rnaseq",
)


def ensure_volume_dir(path: str):
    """Create the output directory on a UC Volume via dbutils."""
    # Try dbutils first (Databricks notebook context)
    try:
        dbutils.fs.mkdirs(path.replace("/Volumes", "/Volumes"))
    except Exception:
        pass
    # Also try os.makedirs for local filesystem
    local_path = path.replace("/Volumes", "")
    try:
        os.makedirs(local_path, exist_ok=True)
    except Exception:
        pass


def generate_synthetic_ensembl_ids(n_genes: int) -> list:
    """Generate synthetic Ensembl-style gene IDs (ENSGXXXXXXXXX)."""
    rng = np.random.default_rng(42)
    ids = []
    used = set()
    for _ in range(n_genes):
        while True:
            eid = f"ENSG{rng.integers(10000000, 99999999)}"
            if eid not in used:
                used.add(eid)
                ids.append(eid)
                break
    return ids


def main():
    import scanpy as sc
    import anndata as ad
    import scipy.sparse as sp

    print(f"Output directory: {OUT_DIR}")
    ensure_volume_dir(OUT_DIR)

    # Load base dataset
    print("Loading Stephenson 2021 subsampled dataset via pertpy...")
    import pertpy as pt
    adata = pt.data.stephenson_2021_subsampled()
    print(f"Base dataset: {adata.shape[0]} cells x {adata.shape[1]} genes")

    # Ensure X is raw counts (integer) for variants that need raw data
    if not sp.issparse(adata.X):
        adata.X = sp.csr_matrix(adata.X)
    
    # Check if data is already normalized (max < 100 suggests log-normalized)
    max_val = adata.X.max()
    if max_val < 100:
        print(f"Warning: max value in .X is {max_val}, data may already be normalized.")
        print("Attempting to recover raw counts by expm1...")
        adata.X = sp.csr_matrix(np.expm1(adata.X.toarray()).astype(np.float32))
    else:
        adata.X = adata.X.astype(np.float32)

    # --- Variant 1: sample_symbols.h5ad ---
    # Clean data with gene symbols as var_names, raw integer counts in .X
    print("\n[1/5] Creating sample_symbols.h5ad...")
    v1 = adata.copy()
    v1.var_names_make_unique()
    # Ensure var_names look like gene symbols (not ENSG)
    if v1.var_names[0].startswith("ENSG"):
        # If already Ensembl, try to get symbols from a column
        for col in ["feature_name", "gene_symbols", "gene_name", "symbol"]:
            if col in v1.var.columns:
                v1.var["ensembl_id"] = v1.var_names.copy()
                v1.var_names = v1.var[col].astype(str).values
                v1.var_names_make_unique()
                break
    v1.write_h5ad(f"{OUT_DIR}/sample_symbols.h5ad")
    print(f"  Saved: {v1.shape}")

    # --- Variant 2: sample_ensembl.h5ad ---
    # Same data but var_names are synthetic Ensembl IDs, symbols in var['feature_name']
    print("\n[2/5] Creating sample_ensembl.h5ad...")
    v2 = adata.copy()
    # Store original gene symbols in feature_name column
    v2.var["feature_name"] = v2.var_names.copy()
    # Replace var_names with synthetic Ensembl IDs
    ensembl_ids = generate_synthetic_ensembl_ids(v2.n_vars)
    v2.var_names = ensembl_ids
    v2.var_names_make_unique()
    v2.write_h5ad(f"{OUT_DIR}/sample_ensembl.h5ad")
    print(f"  Saved: {v2.shape} (var_names are Ensembl IDs)")

    # --- Variant 3: sample_processed.h5ad ---
    # Processed data (normalized, log1p) in .X, raw counts in .raw
    print("\n[3/5] Creating sample_processed.h5ad...")
    v3 = adata.copy()
    v3.var_names_make_unique()
    # Fix var_names if Ensembl
    if v3.var_names[0].startswith("ENSG"):
        for col in ["feature_name", "gene_symbols", "gene_name", "symbol"]:
            if col in v3.var.columns:
                v3.var_names = v3.var[col].astype(str).values
                v3.var_names_make_unique()
                break
    # Store raw counts in .raw, then normalize .X
    v3_raw = v3.copy()
    # Normalize and log1p the .X
    sc.pp.normalize_total(v3, target_sum=1e4)
    sc.pp.log1p(v3)
    # Set .raw to the original counts
    v3.raw = v3_raw
    v3.write_h5ad(f"{OUT_DIR}/sample_processed.h5ad")
    print(f"  Saved: {v3.shape} (.X is normalized/log1p, .raw has counts)")

    # --- Variant 4 & 5: donor1.h5ad, donor2.h5ad ---
    # Two subsets from different donors for multi-sample integration
    print("\n[4/5] Creating donor1.h5ad and donor2.h5ad...")
    # Find a donor/patient column
    donor_col = None
    for col in ["patient_id", "donor_id", "sample", "orig.ident", "donor"]:
        if col in adata.obs.columns:
            donor_col = col
            break
    
    if donor_col is None:
        print(f"  No donor column found in obs. Available: {list(adata.obs.columns)}")
        print("  Splitting by first half / second half instead.")
        mid = adata.n_obs // 2
        donor1 = adata[:mid].copy()
        donor2 = adata[mid:].copy()
        donor1.obs["donor_id"] = "donor1"
        donor2.obs["donor_id"] = "donor2"
    else:
        donors = adata.obs[donor_col].unique()
        if len(donors) >= 2:
            donor1 = adata[adata.obs[donor_col] == donors[0]].copy()
            donor2 = adata[adata.obs[donor_col] == donors[1]].copy()
            # Rename to consistent donor_id
            donor1.obs["donor_id"] = "donor1"
            donor2.obs["donor_id"] = "donor2"
        else:
            mid = adata.n_obs // 2
            donor1 = adata[:mid].copy()
            donor2 = adata[mid:].copy()
            donor1.obs["donor_id"] = "donor1"
            donor2.obs["donor_id"] = "donor2"
    
    # Fix var_names if Ensembl
    for d in [donor1, donor2]:
        if d.var_names[0].startswith("ENSG"):
            for col in ["feature_name", "gene_symbols", "gene_name", "symbol"]:
                if col in d.var.columns:
                    d.var_names = d.var[col].astype(str).values
                    d.var_names_make_unique()
                    break
    
    donor1.write_h5ad(f"{OUT_DIR}/donor1.h5ad")
    donor2.write_h5ad(f"{OUT_DIR}/donor2.h5ad")
    print(f"  donor1: {donor1.shape}, donor2: {donor2.shape}")

    print(f"\nAll 5 h5ad files written to {OUT_DIR}")
    print("Done. You can now run the eval arms.")


if __name__ == "__main__":
    main()