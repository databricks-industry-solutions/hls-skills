# Grounding recipes & governance rules

A deck is only trustworthy if every number came from the data and no PHI leaks into a file
that gets emailed around. `scripts/ground.py` enforces both. This is the reference for what
each helper does, the SQL behind it, and the governance rules.

## The rule: ground, then present

1. **Gate** the table (`assert_shareable`).
2. **Ground** the figures (`cohort_summary`, `numeric_summary`, `column_distribution`).
3. Drop the returned values into the spec and the returned `source` string into the slide
   `caption`/`notes`.
4. Never type a figure into prose by hand. If a number can't be grounded, it's an
   assumption — label it as one on a `statement` slide, don't put it on a `metrics` tile.

All reads auth like `hls-cohort-builder`: ambient in-workspace, or pass `profile=` locally;
`warehouse_id=` is auto-selected if omitted. All helpers accept `q=` to inject a runner
(used by the offline tests).

## Helpers → SQL

### `profile_table(table)`
`DESCRIBE {table}` for the column schema + `SELECT COUNT(*)`, plus a `scan_phi()` of the
column names. Returns `{table, row_count, columns:[{name,type}], phi:{direct, quasi}}`.

### `cohort_summary(table, id_col="patient_id")`
```sql
SELECT COUNT(*), COUNT(DISTINCT patient_id) FROM {table}   -- id_col used only if present
```
Returns `{n_rows, n_subjects, source}`. → a `metrics` tile.

### `numeric_summary(table, column)`
```sql
SELECT COUNT(c), MIN(c), MAX(c), AVG(c), percentile_approx(c, 0.5) FROM {table}
```
Returns `{count, min, max, avg, median, source}`. → a `metrics` tile (pick the stat you want).

### `column_distribution(table, column, top=8, small_cell_k=11)`
```sql
SELECT CAST(column AS STRING) v, COUNT(*) n FROM {table} GROUP BY 1 ORDER BY n DESC
```
Returns `{bars:[{label, value}], suppressed, source}` shaped for a `bar_chart`.
**Cells with `n < small_cell_k` are dropped** and counted in `suppressed`.

## Governance rules

### Direct identifiers → no sample rows
`assert_shareable(table, allow_sample_rows=False)` is always safe (aggregates only).
With `allow_sample_rows=True`, it raises `PhiLeakError` if the table has any **direct
identifier** column. HIPAA Safe Harbor §164.514(b)(2) names, matched on column name:
names, SSN, MRN, member/subscriber/beneficiary IDs, account/policy/claim numbers, email,
phone/fax, address/street/city/ZIP, dates of birth, fine-grained service dates
(admit/discharge/death/visit), device/serial IDs, URLs, IPs, biometrics, license/VIN/passport.

**This is a name-based guardrail, not a de-identifier.** It catches the common leaks; it does
not inspect values or enforce k-anonymity. For an actual de-identified, k-anonymous,
governed view, run `phi-deidentifier` and build the deck from its output.

### Quasi-identifiers → flagged, not blocked
Age, sex/gender, race/ethnicity, year-of-birth, ZIP3 are reported under
`shareable.quasi_identifiers` for your awareness. In combination they can re-identify;
suppress small cells and avoid cross-tabs with tiny counts.

### Small cells → suppressed
Distributions drop any category with fewer than `small_cell_k` (default 11) rows. 11 is the
common small-cell threshold for public health reporting; raise it for small or sensitive
populations.

## Grounding a model (no table helper needed)

Model metrics usually come from MLflow, not a table — pull them yourself and pass as figures:

```python
import mlflow
r = mlflow.get_run("<run_id>")           # or search_runs / the UC registered model
tiles = [
  {"value": f"{r.data.metrics['f1']:.3f}", "label": "F1",
   "caption": f"Source: MLflow run {r.info.run_id[:8]}"},
  {"value": f"{r.data.metrics['auc']:.3f}", "label": "AUROC",
   "caption": f"Source: MLflow run {r.info.run_id[:8]}"},
]
```

The discipline is identical: the `caption` cites where the number came from.
