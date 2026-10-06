# Large-Scale Tabular Extraction (cspray)

> Reference file for the `sc-rnaseq` skill.  
> Load via `readSkillFile("skills/sc-rnaseq/references/cspray-tables.md")`
> when the goal is building Delta tables, dashboards, or SQL-queryable data
> from h5ad files, or for the Delta write step after scanpy/rapids analysis.

---

When the goal is to **build Delta tables** from h5ad files for downstream SQL
queries, dashboards, or Genie Spaces, prefer **cspray** over loading
everything into memory with scanpy. This applies even for a single file when
the user only needs obs metadata or the post-analysis write to Delta.

## When to recommend cspray

* **Any number of files** when the goal is a Delta table — not just "many".
* The user wants to query cell metadata, cluster assignments, or gene
  expression as a SQL table.
* Building gold-layer tables for BI consumption.
* After a scanpy / rapids-singlecell analysis, for the Delta write step.
* The user only needs existing obs metadata without reprocessing.

> **Default recommendation:** Unless the user explicitly needs to run QC /
> clustering / DE first, route to cspray. Don't load the full count matrix
> into scanpy just to call `adata.obs.to_parquet()` — cspray reads obs at
> Spark scale without ever materializing the expression matrix.

---

## Install

cspray is installed from GitHub (not PyPI). Use the `main` branch for
stable releases:

```python
%pip install git+https://github.com/databricks-solutions/cspray.git@main
%restart_python
```

> **Branch selection:** Use `@main` for production workloads. Use `@develop`
> for the latest features. Pin to a specific commit hash for reproducibility
> in tracked MLflow runs (e.g.,
> `git+https://github.com/databricks-solutions/cspray.git@3b5ae0a`).

> **MLflow autolog:** cspray runs PCA and k-means internally. Disable
> MLflow autologging to prevent it from capturing these internal steps
> as spurious experiments:
> ```python
> import mlflow
> mlflow.autolog(disable=True)
> ```

---

## Serverless Compute Compatibility

cspray internally calls `CLEAR CACHE` and `PERSIST TABLE`, both of which
are **blocked on serverless compute** (Spark Connect). Call
`set_intermediary_persistance(persist=False)` **immediately after**
`SprayData.from_h5ads()` and **before** any other operation:

```python
sdata = SprayData.from_h5ads(spark, ...)
sdata.set_intermediary_persistance(persist=False)  # REQUIRED on serverless
```

This must come before:
* `sdata.to_tables_and_reset()`
* `cs.md.promote_suggested()` (also triggers PERSIST internally)
* Any `cs.pp.*` preprocessing call

> **On classic compute** this is optional — default caching improves
> performance. Only disable on serverless.

---

## Path Prefix Stripping

`dbutils.fs.ls()` and Spark's `binaryFile` format return paths prefixed
with `dbfs:`. **h5py (used by cspray) requires POSIX paths** (`/Volumes/...`).
Always strip before passing to `SprayData.from_h5ads()`:

```python
raw_paths = [f.path for f in dbutils.fs.ls("/Volumes/<catalog>/<schema>/<volume>/")]
clean_paths = [p.replace("dbfs:", "") for p in raw_paths]
sdata = SprayData.from_h5ads(spark, path=clean_paths, ...)
```

> Passing `dbfs:`-prefixed paths causes `FileNotFoundError` inside h5py.

---

## Two Ingestion Pathways

cspray supports two distinct pathways. **The agent must clarify which one
the user needs** — the tables produced, the columns available, and the
dashboard patterns differ significantly. The pathway depends on the user’s
actual ask and may need clarification — don’t assume.

> **Ask the user:** "Do you need to reprocess from raw counts (QC, normalize,
> cluster), or just extract the existing metadata and expression values as-is?"
> If unclear, Pathway A is the safer default — it preserves the h5ad as-is.

| | Pathway A — Metadata-only | Pathway B — Raw processing |
|---|---|---|
| **When** | Pre-processed h5ad (CELLxGENE, published). **Most common.** | Raw-count h5ad needing QC/normalize/cluster. |
| **`from_raw`** | `False` | `True` |
| **`cs.pp.*`** | Skip entirely | Full pipeline |
| **Tables** | obs, X, var, sam (bronze + promoted) | obs, X, var, sam (bronze→silver) + `gold_clu_cell` |
| **PCA / clusters** | Only if already in the h5ad | Computed by cspray |
| **QC in sam** | Sparse (only if pre-computed) | Full MT pass rates |

---

## SprayData API — Ingestion Pattern

> **`len(sdata)` is not supported.** Count input paths before `from_h5ads()`.

### Pathway A — Metadata-only ingest (most common)

```python
from cspray.data import SprayData
import cspray as cs

# Ensembl reference optional — only for Ensembl ID → symbol resolution.
ensembl_reference_df = None
try:
    ensembl_reference_df = spark.createDataFrame(cs.utils.get_gene_table())
except Exception:
    pass  # cspray uses whatever identifiers are in the h5ad

sdata = SprayData.from_h5ads(
    spark,
    path="/Volumes/<catalog>/<schema>/<volume>/h5ad_files/",
    force_partitioning=500,
    chunk_size=int(6_000_000),
    from_raw=False,               # Pathway A: use processed .X, NOT .raw
    broadcast_genes=True,
    ensembl_reference_df=ensembl_reference_df,
    obs_metadata_columns="all",
    var_metadata_columns="all",
)

sdata.set_intermediary_persistance(persist=False)  # required on serverless

# Write bronze tables (obs, X, var, sam)
sdata.to_tables_and_reset(spark, table_base="<catalog>.<schema>", join_char=".bronze_")

# Promote shared obs fields to typed columns
cs.md.promote_suggested(sdata, which="both", promote_sam=True)
sdata.to_tables_and_reset(
    spark, table_base="<catalog>.<schema>", join_char=".bronze_",
    subset=["obs", "var", "sam"],
)
# Done. No cs.pp.* pipeline. No silver layer needed.
```

### Pathway B — Raw processing (QC → normalize → PCA → cluster)

```python
from cspray.data import SprayData
import cspray as cs

ensembl_reference_df = None
try:
    ensembl_reference_df = spark.createDataFrame(cs.utils.get_gene_table())
except Exception:
    pass

sdata = SprayData.from_h5ads(
    spark,
    path="/Volumes/<catalog>/<schema>/<volume>/raw_h5ad/",
    force_partitioning=500,
    chunk_size=int(6_000_000),
    from_raw=True,                # Pathway B: use adata.raw
    broadcast_genes=True,
    ensembl_reference_df=ensembl_reference_df,
    obs_metadata_columns="all",
    var_metadata_columns="all",
)

sdata.set_intermediary_persistance(persist=False)  # required on serverless

# Bronze tables first
sdata.to_tables_and_reset(spark, table_base="<catalog>.<schema>", join_char=".bronze_")
cs.md.promote_suggested(sdata, which="both", promote_sam=True)
sdata.to_tables_and_reset(
    spark, table_base="<catalog>.<schema>", join_char=".bronze_",
    subset=["obs", "var", "sam"],
)

# --- cspray preprocessing pipeline (Pathway B only) ---
cs.pp.calculate_qc_metrics(sdata)
cs.pp.filter_cells(sdata)
cs.pp.filter_genes(sdata)
cs.pp.apply_samplewise_mt_statistic(sdata)
cs.pp.filter_cells_on_mt(sdata)
cs.pp.normalize(sdata)
cs.pp.log1p_counts(sdata)
sdata.to_tables_and_reset(spark, table_base="<catalog>.<schema>", join_char=".silver_")
```

> **Uniform thresholds only:** cspray's `cs.pp.filter_*` applies the same
> thresholds across all files. For heterogeneous QC profiles, filter in
> scanpy per-sample first, write back to h5ad, then ingest via Pathway A.


---

## Output Table Architecture

cspray produces **separate tables per AnnData layer**, not one monolithic
table. This is a critical detail for downstream queries and dashboards.

| Table | Grain | Key Columns | Purpose |
|---|---|---|---|
| `*_obs` | One row per cell | `fp_int`, `cell_idx`, `cell_barcode` | Cell metadata, QC metrics, cluster assignments, embeddings |
| `*_X` | One row per (cell × gene) | `fp_int`, `cell_idx`, `gene_name` | Expression matrix in long/tall format |
| `*_var` | One row per gene per sample | `fp_int`, `gene_name` | Gene-level metadata |
| `*_sam` | One row per sample | `fp_int` | Sample-level QC summary |
| `*_clu_cell` (gold) | One row per cluster per sample | `fp_int`, `cluster_id` | Cluster summary: n_cells, marker genes, modal cell type. **Pathway B only.** |

**Key identifiers:**
* `fp_int` (int) — hash of `file_path`, uniquely identifies a sample.
* `cell_idx` (bigint) — cell index within a sample. Combined with `fp_int`,
  uniquely identifies a cell across the entire dataset.
* `gene_name` (string) — gene identifier in the X table.

**Join keys:**
* obs ↔ X: `fp_int, cell_idx`
* obs ↔ sam: `fp_int`
* obs ↔ clu_cell: `fp_int, cluster_id`

---

## obs Table Schema

The obs table uses a **hybrid VARIANT + promoted columns** approach:

* `obs_data` (VARIANT) — catch-all for all obs fields from the source h5ad.
  Query with `variant_get(obs_data, '$.field_name', 'STRING')`.
* **Promoted columns** — commonly shared fields extracted as top-level typed
  columns for fast filtering: `cell_type`, `disease`, `tissue`, `sex`,
  `development_stage`, `assay`, `suspension_type`, plus ontology term IDs.
* **QC metrics:** `total_count`, `n_genes_by_counts`, `pct_mt`.
* **Embeddings (Pathway B only):** `pca_features_array` (array\<double\>).
  Access PCA components with `pca_features_array[0] AS pc1,
  pca_features_array[1] AS pc2`. Not present in Pathway A unless the h5ad
  already contained embeddings that were promoted.
* **Multi-resolution clustering (Pathway B only):** `cluster_k_2` through
  `cluster_k_5`, `cluster_id` — cspray runs k-means at multiple k values.
  Not present in Pathway A.

> **Metadata promotion:** `cs.md.promote_suggested()` analyzes which obs
> fields are shared across files and promotes them to typed columns. This is
> the recommended approach for heterogeneous collections — common fields
> become fast-filterable columns, file-specific extras stay in `obs_data`
> VARIANT.

---

## Handling Promotion Failures — Dot-in-Column-Name Bug

**Known issue (cspray ≤ 1.1.0):** `cs.md.promote_suggested()` crashes with
`UNRESOLVED_COLUMN.WITH_SUGGESTION` when any h5ad file in the batch has an
obs column whose name contains a literal dot (e.g., `orig.ident`, common in
Seurat-origin datasets from CZI CELLxGENE). Spark interprets the unescaped
dot as struct field access (`` `orig`.`ident` ``) instead of a single column
name (`` `orig.ident` ``). The error is batch-wide — all files fail, not
just the problematic one.

**Agent action — diagnose, report, and retry without the bad files:**

When `promote_suggested` raises `UNRESOLVED_COLUMN` referencing a dotted
name, the agent MUST:

1. **Identify the problematic column name** from the error message (the
   unresolved column, e.g., `` `orig`.`ident` `` means `orig.ident`).
2. **Scan the batch to find which file(s) contain the column:**
   ```python
   import anndata as ad

   problem_col = "orig.ident"  # extracted from error message
   bad_files = []
   for p in selected_paths:
       adata = ad.read_h5ad(p, backed="r")
       if problem_col in adata.obs.columns:
           bad_files.append(p)
       adata.file.close()

   print(f"Files with '{problem_col}' column ({len(bad_files)}):")
   for f in bad_files:
       print(f"  {f}")
   ```
3. **Report to the user** with a clear explanation:
   > "Metadata promotion failed because file(s) {bad_files} contain an obs
   > column named `{problem_col}`. The dot in the column name is a known
   > cspray bug — Spark interprets it as struct access. The bronze tables
   > (X, obs, var, sam) are already written and intact. Options:
   > (a) Re-run ingestion excluding the problematic file(s), then promote.
   > (b) Keep all files but skip promotion — query via `variant_get(obs_data,
   > '$.field', 'STRING')` instead of top-level columns."
4. **If the user chooses to re-run**, remove the bad files from the path
   list and re-ingest:
   ```python
   clean_paths = [p for p in selected_paths if p not in bad_files]
   sdata = SprayData.from_h5ads(spark, path=clean_paths, ...)
   sdata.set_intermediary_persistance(persist=False)
   sdata.to_tables_and_reset(spark, table_base=TABLE_BASE, join_char=JOIN_CHAR)
   cs.md.promote_suggested(sdata, which="both", promote_sam=True)
   sdata.to_tables_and_reset(
       spark, table_base=TABLE_BASE, join_char=JOIN_CHAR,
       subset=["obs", "var", "sam"],
   )
   ```
5. **Always wrap `promote_suggested` in try/except** as a defensive pattern,
   even when no dotted columns are expected — heterogeneous h5ad collections
   are unpredictable:
   ```python
   try:
       cs.md.promote_suggested(sdata, which="both", promote_sam=True)
       sdata.to_tables_and_reset(..., subset=["obs", "var", "sam"])
   except Exception as e:
       if "UNRESOLVED_COLUMN" in str(e):
           # Extract dotted column name, scan files, report to user
           ...
       else:
           raise
   ```

> **Upstream fix pending:** The root cause is that cspray does not
> backtick-escape column names containing dots when constructing Spark
> DataFrame/SQL references during promotion. Until this is fixed upstream,
> the scan-and-exclude pattern above is the recommended workaround.

---

## X Table Schema & Optimization

The expression matrix is stored in **long/tall format** (one row per cell ×
gene pair). For a dataset with 100k cells and 20k genes, this can be
billions of rows. Optimization is critical.

**Columns:**
* `fp_int`, `cell_idx`, `file_path` — cell identity
* `gene_name`, `gene_idx` — gene identity
* `expression` (float) — raw counts
* `norm_counts` (double) — normalized counts
* `log1p_norm_counts` (double) — log-normalized counts
* `is_mt` (boolean) — mitochondrial gene flag
* `total_counts`, `pct_mt` — per-gene QC
* `bin_cell_counts`, `bin_gene_counts` — binned count statistics

**CLUSTER BY (Liquid Clustering):**

The X table should use `CLUSTER BY` for query performance. The optimal
column order depends on the dominant query pattern:

```sql
-- Gene-centric queries (most common in dashboards):
-- "Show expression of gene X across all cells"
ALTER TABLE <catalog>.<schema>.silver_x CLUSTER BY (gene_name, fp_int);

-- Sample-centric queries:
-- "Show all genes for cells in sample Y"
ALTER TABLE <catalog>.<schema>.silver_x CLUSTER BY (fp_int, gene_name);
```

> **Agent action:** Ask the user about their dominant query pattern before
> setting CLUSTER BY order. Gene-first is better for dashboards and
> cross-sample gene queries (e.g., "show CXCL13 expression across all
> diseases"). Sample-first is better for per-sample analysis pipelines.
> Default recommendation: **gene_name first** for dashboard/BI use cases.

### CLUSTER BY recommendations per table

| Table | CLUSTER BY | Rationale |
|---|---|---|
| `*_x` | `(gene_name, fp_int)` | Gene-centric dashboard queries filter on `gene_name` first. |
| `*_obs` | `(disease, tissue)` or `(cell_type, disease)` | Depends on dashboard filter pattern. Use `(disease, tissue)` for explorer-style; `(cell_type, disease)` for cell-type drilldowns. |
| `*_sam` | Skip | Small table (one row per sample). No clustering benefit. |
| `*_var` | Skip | Small table. |
| `gold_clu_cell` | Skip | Small table (Pathway B only). |

---

## sam Table Schema

One row per sample with pre-computed QC summaries:
* `n_cells`, `total_counts`, `mean_genes_per_cell`
* MT pass rates at multiple thresholds: `pct_cells_passing_mt_2.0_pct`,
  `pct_cells_passing_mt_5.0_pct`, `pct_cells_passing_mt_8.0_pct`,
  `pct_cells_passing_mt_10.0_pct`

These pre-computed rates let dashboards show QC distributions without
scanning the full obs table.

---

## Gold Tables & Dashboard Strategy

Gold table needs differ by pathway. Do not create gold tables that
don’t apply to the pathway the user followed.

### Pathway A (metadata-only) — no gold tables needed

All dashboard queries run directly against **bronze** (promoted) tables:
`bronze_obs`, `bronze_x`, `bronze_sam`. There is no PCA, no clustering,
no `clu_cell`. The dashboard scope is: cell metadata exploration, gene
expression queries, sample overview. This covers the majority of use cases
(CELLxGENE / published h5ad files).

### Pathway B (raw processing) — one gold table

* **gold_clu_cell**: Cluster-level summary with `n_cells`, `marker_genes`
  (array\<string\>), modal `cell_type`, and `cell_type_count`. One row per
  cluster per sample. Produced by cspray after the `cs.pp.*` pipeline.

PCA scatter plots and cell-type drilldowns query `silver_obs` directly
(which has `pca_features_array`, `cluster_id`). For very large datasets,
use `TABLESAMPLE` or a dashboard-side row limit instead of a dedicated
subsampled gold table:

```sql
SELECT pca_features_array[0] AS pc1, pca_features_array[1] AS pc2,
       cell_type, disease, cluster_id
FROM <catalog>.<schema>.silver_obs TABLESAMPLE (5 PERCENT);
```

> **Decommissioned:** A subsampled `gold_obs` table (proportional stratified
> sampling to \~2,000 cells/cluster) was previously used for PCA scatter
> performance. This is no longer recommended — use `TABLESAMPLE` on
> `silver_obs` instead.

---

## Example Dashboard Query Patterns

### Pathway A (metadata-only) — queries hit bronze tables

The X table uses `expression` (raw counts from processed .X) and may
not have `log1p_norm_counts` or `norm_counts` (those come from `cs.pp.*`).
For Pathway A, use `expression` directly or compute log-normalization
in the query.

```sql
-- Gene expression across diseases (Pathway A: bronze tables)
WITH filtered_x AS (
  SELECT fp_int, cell_idx, gene_name, expression
  FROM <catalog>.<schema>.bronze_x
  WHERE gene_name = :gene_name   -- benefits from gene_name-first clustering
)
SELECT fx.*, o.disease, o.tissue, o.cell_type
FROM filtered_x fx
  JOIN <catalog>.<schema>.bronze_obs o
    ON fx.fp_int = o.fp_int AND fx.cell_idx = o.cell_idx;

-- Cell metadata overview (Pathway A: all promoted columns)
SELECT cell_type, disease, tissue, sex, COUNT(*) AS n_cells
FROM <catalog>.<schema>.bronze_obs
GROUP BY ALL;

-- Sample summary (Pathway A: sam may be sparse — only pre-computed fields)
SELECT fp_int, file_path, n_cells
FROM <catalog>.<schema>.bronze_sam;
```

### Pathway B (raw processing) — queries hit silver/gold tables

```sql
-- Gene expression across diseases (Pathway B: silver tables with normalized counts)
WITH filtered_x AS (
  SELECT fp_int, cell_idx, gene_name, log1p_norm_counts
  FROM <catalog>.<schema>.silver_x
  WHERE gene_name = :gene_name
)
SELECT fx.*, o.disease, o.tissue, o.cell_type, o.cluster_id
FROM filtered_x fx
  JOIN <catalog>.<schema>.silver_obs o
    ON fx.fp_int = o.fp_int AND fx.cell_idx = o.cell_idx;

-- PCA scatter (Pathway B: silver_obs has pca_features_array)
SELECT pca_features_array[0] AS pc1, pca_features_array[1] AS pc2,
       cell_type, disease, cluster_id
FROM <catalog>.<schema>.silver_obs
TABLESAMPLE (5 PERCENT);  -- or use dashboard row limit

-- Cluster summary (Pathway B only: gold_clu_cell)
SELECT cluster_id, n_cells, cell_type, marker_genes
FROM <catalog>.<schema>.gold_clu_cell;

-- Sample QC overview (Pathway B: silver_sam has full MT pass rates)
SELECT fp_int, n_cells, mean_genes_per_cell,
  `pct_cells_passing_mt_5.0_pct` * 100 AS pct_pass_mt_5
FROM <catalog>.<schema>.silver_sam;
```

### Shared pattern: gene expression queries

The X→obs join pattern is the same for both pathways — only the table
prefix (`bronze_` vs `silver_`) and available expression columns differ.
Both benefit from `CLUSTER BY (gene_name, fp_int)` on the X table.

---

## Backed-Mode Reads

Backed mode (`backed="r"`) opens an h5ad lazily — obs, var, uns, and obsm
keys are loaded but the expression matrix is not. Use it for:

* **Profiling / inspection** before full load — see the scanpy workflow
  "Profiling with Backed Reads" for the full pattern and code.
* **Extracting obs metadata** from a single file without processing.
* **Multi-file metadata inspection** to discover batch keys.

```python
import anndata as ad

adata = ad.read_h5ad("/Volumes/.../sample.h5ad", backed="r")
obs_df = adata.obs.copy()  # pandas DataFrame, no expression matrix in memory
adata.file.close()         # always close the file handle
```

> **Limitations:** Backed mode only gives you what's already stored in the
> file. You cannot run QC, normalize, cluster, or compute new fields. For
> multi-file Delta table extraction, cspray is still the right tool because
> it handles schema heterogeneity and parallelizes I/O.

> **Note:** Verify cspray API and import patterns against the latest docs on
> GitHub before generating code. The package is under active development and
> the API surface may change.

cspray leverages Spark distributed I/O, so it scales horizontally and avoids
single-node RAM bottlenecks.

---

## Writing Results to Delta (Post-Analysis)

### Preferred path: cspray (Pathway A after scanpy/rapids analysis)

For most tabular persistence — even after a scanpy / rapids-singlecell
analysis — **write through cspray** rather than manually converting
`adata.obs` to a Spark DataFrame. cspray handles schema heterogeneity,
parallel I/O, and VARIANT columns. Save the processed h5ad back to a UC
Volume, then point cspray at it:

```python
# After analysis, write processed h5ad to Volume
adata.write_h5ad("/Volumes/<catalog>/<schema>/<volume>/processed/sample_A.h5ad")

# Then use cspray SprayData API for the full table set (obs, X, var, sam)
from cspray.data import SprayData
import cspray as cs

sdata = SprayData.from_h5ads(spark, path="/Volumes/.../processed/")
sdata.set_intermediary_persistance(persist=False)  # required on serverless
cs.md.promote_suggested(sdata, which="both", promote_sam=True)
sdata.to_tables_and_reset(
    spark, table_base="<catalog>.<schema>", join_char=".silver_"
)
```

### Fallback: manual obs extraction

Use the manual approach **only** when persisting a small, single-sample
result that includes computed fields not yet written back to h5ad (e.g.,
cluster assignments still only in memory):

```python
import pyspark.sql.functions as F

obs_df = spark.createDataFrame(adata.obs.reset_index())
obs_df = obs_df.withColumn("_loaded_ts", F.current_timestamp())

obs_df.write.format("delta").mode("overwrite").saveAsTable(
    "<catalog>.<schema>.gold_single_cell_clusters"
)
```

> **Caution:** This approach breaks when combining files with different obs
> schemas. If you have heterogeneous sources, use cspray.

### Governance rules

* Include `COMMENT` and `TBLPROPERTIES` (`quality`, `owner`, `domain`).
* Gold tables for dashboards should use `CLUSTER BY` if > 1 GB.
* For the X table specifically, set `CLUSTER BY (gene_name, fp_int)` for
  gene-centric dashboard queries. See X Table Schema above for details.
* Pathway B: prefer normalized counts (`log1p_norm_counts`) in dashboards.
  Pathway A: `expression` from processed .X is acceptable (it’s already
  the author’s chosen representation).

> **Reading expression and embeddings:** Expression lives in the X table —
> `expression` (raw counts from the processed `.X`) when ingesting
> pre-processed data, plus `norm_counts` / `log1p_norm_counts` when cspray
> runs QC/normalization from raw. PCA coordinates and cluster assignments
> live in obs, present only if the h5ad already carried them (promoted) or
> cspray generated them (raw-processing pathway). **UMAP is not a cspray
> output.** Use existing UMAP coordinates only if the h5ad already has them;
> for scatter plots otherwise, prefer PCA — computing UMAP over data at this
> scale is expensive and needs separate consideration. See the X Table
> Schema and obs Table Schema above for columns.
