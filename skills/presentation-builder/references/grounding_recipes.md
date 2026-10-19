# Grounding recipes

A deck is only trustworthy if every number came from the data. `scripts/ground.py` is how
you pull them. This is the reference for what each helper does and the SQL behind it.

PHI is handled **upstream**, not here: de-identify the source with the `phi-deidentifier`
skill (or confirm with the user that PHI may be included) *before* grounding — see
SKILL.md, "De-identify before you present." `ground.py` presents whatever table it is given.

## The rule: ground, then present

1. **De-identify first** if the source holds patient-level PHI (delegate to
   `phi-deidentifier`; if it's unavailable, ask the user), then ground the governed view.
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
`DESCRIBE {table}` for the column schema + `SELECT COUNT(*)`.
Returns `{table, row_count, columns:[{name,type}]}`.

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

### `column_distribution(table, column, top=8)`
```sql
SELECT CAST(column AS STRING) v, COUNT(*) n FROM {table} GROUP BY 1 ORDER BY n DESC LIMIT top
```
Returns `{bars:[{label, value}], source}` shaped for a `bar_chart`.

## PHI is handled upstream (delegated to phi-deidentifier)

The presentation builder does not detect, classify, or suppress PHI. If the source table
holds patient-level data:

1. Run the **`phi-deidentifier`** skill to produce a de-identified, k-anonymous, governed
   view, then point `ground.py` at that view.
2. If `phi-deidentifier` is **not available** in the environment (not installed in Genie or
   whatever agent is running), **ask the user** whether they want PHI included in the
   presentation or excluded — do not decide silently. See SKILL.md for the exact prompt.

For the identifier taxonomy, k-anonymity enforcement, and the Safe Harbor disclaimer, see
the `phi-deidentifier` skill — that is the single source of truth for de-identification.

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
