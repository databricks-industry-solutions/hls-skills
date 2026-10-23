# Generation — mapping + catalog → SQL

How Phase 3 turns the mapping file and the measure catalog into deployable SQL. Three layers.

## 01_silver.sql — conform each mapped entity

For each mapped entity, emit one view named `<entity>` in the target schema that renames/derives
physical columns to canonical field names.

- Apply `joins` (to-one only) and reference joined columns as `<table>.<col>`.
- Materialize `enums` as `CASE` expressions producing the canonical value:
  ```sql
  CASE WHEN ENC_TYPE_C IN ('101','102') THEN 'inpatient'
       WHEN ENC_TYPE_C = '5' THEN 'emergency' ... ELSE 'other' END AS encounter_class
  ```
- Apply `transform` macros (e.g. `span_to_monthly` cross-joins a month spine to expand coverage spans).

Guard: if a referenced physical column doesn't exist in the source, fail with a clear message — do
not silently emit `NULL`.

## 02_gold.sql — enrichments + conformed grains

- **Derived attributes** the catalog needs that aren't raw columns: `is_index_admission`,
  `is_readmission_30day` (window over a patient's inpatient encounters within 30 days),
  `procedure_count`, `is_surgical`.
- **Conformed `member_month`** for payer economics (Option A): roll `claim` to `member_id x
  service_month` (SUM of incurred/paid/allowed), then join `enrollment` on
  `member_id, coverage_month = service_month`. Emit as a single view at member-month grain so the
  metric view never fans across two facts.

## 03_metric_views.sql — one metric view per in-scope MV

For each `mv_<domain>__<name>` whose entity is mapped:

- `source`: the silver/gold view for its entity.
- Emit each catalog measure for that metric view verbatim from `expr` (atomics as aggregates,
  composites as `MEASURE()/MEASURE()`).
- Add dimensions from the entity's `role: dimension` fields + joined dims (provider, facility,
  calendar) as to-one joins.

Example (abridged):
```sql
CREATE OR REPLACE VIEW <schema>.mv_care_delivery__encounter (... METRIC VIEW ...) AS
$$
version: 0.1
source: <schema>.encounter
dimensions:
  - name: encounter_date
    expr: encounter_date
  - name: encounter_class
    expr: encounter_class
measures:
  - name: encounter_count
    expr: COUNT(DISTINCT encounter_id)
  - name: avg_los_days
    expr: AVG(los_days)
  - name: readmission_30day_rate
    expr: MEASURE(readmission_30day_count) / MEASURE(index_admission_count)
$$;
```

## Scope inference

- Generate a metric view **only if** its declared entity (and any entity its measures aggregate) is
  present in the mapping. Otherwise skip it and record the skip in the Justify report.
- If `scope.domains` is set in the mapping, intersect with the inferred set.

## Correctness

- Run `scripts/validate_catalog.py` before generating — the catalog must be clean.
- After generating, smoke-test each metric view: `SELECT MEASURE(<a_measure>) FROM <mv>`.
- Never hand-edit a composite into a bare aggregate during generation; measures are copied from the
  catalog unchanged.
