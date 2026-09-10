# Workflow — assess → map → generate → justify → expose

The full procedure for standing up the HLS semantic layer for one customer. Read alongside
`mapping_spec.md`, `mv_generation.md`, and `consumption.md`.

## Phase 1 — Assess

1. Confirm auth + target: `databricks current-user me -p <profile>`; agree on target
   `catalog.schema` and `warehouse_id`.
2. Introspect the customer's source(s):
   - `SELECT table_schema, table_name FROM <catalog>.information_schema.tables` to inventory.
   - `SELECT column_name, data_type FROM <catalog>.information_schema.columns WHERE table_name=...`
     for candidate tables.
3. Recognize the source shape and pick adapter(s) from `references/adapters/`:
   - Epic Clarity/Caboodle → `epic_clarity_caboodle.yaml`
   - Landed EDI claims / enrollment → `x12_837_835.yaml`
   - OMOP CDM → `omop_cdm.yaml`
   - Flattened FHIR → `fhir.yaml`
   - Multiple sources (integrated payer+provider) → compose several via `extends:`.
4. Determine which **canonical entities** can be populated. That set determines which metric views
   are in scope (see `mv_generation.md` — unmapped entities drop their MVs).

## Phase 2 — Map

1. Draft `<customer>_mapping.yaml` in the **working directory** (never in the plugin). Start from
   the chosen adapter(s) via `extends:`.
2. Aggressive auto-map: fuzzy-match physical columns to canonical fields; carry adapter defaults;
   fill `target:` (catalog/schema/warehouse_id).
3. Flag every low-confidence binding with a `# REVIEW` comment — unmatched required fields, ambiguous
   columns, code-set enums, incurred-vs-paid, premium source, etc.
4. Present ONLY the flagged items to the user as a short set of questions. Apply their answers.
5. Validate the mapping shape against `mapping_spec.md`.

## Phase 3 — Generate

See `mv_generation.md`. Produce, in `generated/`:
- `01_silver.sql` — one conforming view per mapped entity (physical → canonical field names, joins,
  enum CASE mappings, transforms).
- `02_gold.sql` — enrichments (derived flags like `is_index_admission`) and conformed grains
  (the `member_month` rollup for payer economics).
- `03_metric_views.sql` — one metric view per in-scope `mv_<domain>__<name>`, measures pulled from
  the catalog.

## Phase 4 — Justify

Present the **metric-view plan** for sign-off before any deploy:
- table of `mv_<domain>__<name>` → grain → measures generated → consumers.
- for each asset, one line on why it exists and what it serves.
- explicitly list entities/MVs skipped (and why — unmapped source).
- surface design forks that were auto-decided (e.g. payer economics used the conformed
  `member_month` grain, Option A — offer Option B if the customer prefers query-time composition).

## Phase 5 — Expose

See `consumption.md`. On explicit go-ahead:
1. Run `01`→`02`→`03` against the target schema.
2. Run the catalog validator; smoke-test each metric view with a trivial `MEASURE()` query.
3. Create/point a Genie space (`genie-rooms`) scoped to the metric views.
4. Generate a starter Lakeview dashboard (`databricks-lakeview-dashboard`).
5. Report deployed assets + URLs.

## Guardrails

- Confirm before every outward write (deploy, Genie, dashboard).
- Never invent measures inline — everything comes from the catalog. If a customer needs a measure the
  catalog lacks, add it to the catalog (validate + render), then regenerate.
