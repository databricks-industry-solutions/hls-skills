---
name: payer-provider-measure-catalog
description: Healthcare payer + provider measure catalog and semantic-layer generator. Canonical, source-agnostic definitions across six domains (care delivery, access/throughput, capacity, claims revenue-cycle + adjudication, gap-in-care, payer medical economics incl. MLR/PMPM), plus a workflow that maps a customer's Databricks sources to the canonical model and generates Unity Catalog metric views for Genie, dashboards, and agents. Answers "what is the correct/additive definition of measure X" and "build/generate the metric views for <customer>". Inputs → a per-customer source-mapping file; outputs → conforming views + metric views. For PHI/HIPAA scanning use a compliance skill; this skill defines and builds measures, it does not classify data.
version: 0.1.0
author: Vimal Thomas Joseph
license: Databricks License
---

# Payer/Provider Measure Catalog

## Overview

A governed, source-agnostic healthcare semantic layer for **both payer and provider**. It has two
parts over one canonical model: (1) a **measure catalog** — the correct, domain-grouped definitions of
64 healthcare measures that never change per customer; and (2) a **build workflow** — assess a
customer's Databricks sources, map them to the canonical model, and generate Unity Catalog metric
views consumable by Genie, AI/BI dashboards, Power BI, and agents. The only per-customer input is a
source-mapping file; the catalog is fixed.

## When to Use

- Look up the correct definition of a healthcare measure (ALOS, excess days, readmission rate, denial
  rate, net collection rate, slot utilization, MLR, PMPM) and whether it is additive.
- Decide how a non-additive rate must be modeled in a metric view (ratio-of-measures, not average-of-averages).
- Stand up a semantic layer for a provider system, a payer, or an integrated payer+provider customer.
- Map Epic Clarity/Caboodle, X12 837/835/834 claims, OMOP CDM, or FHIR sources to governed metric views.
- Generate `care_delivery`, `claims`, or `payer_economics` metric views for a specific customer schema.
- Give a Genie space or an agent a governed measure layer instead of raw tables.

## Prerequisites

- **MCP / tools**: Databricks CLI authenticated to the target workspace
  (`databricks current-user me -p <profile>`); Python 3.9+ with PyYAML for the scripts.
- **Inputs**: read access to the customer's source catalog/schema; a target `catalog.schema` and SQL
  `warehouse_id` for the generated layer.
- **Environment**: a working directory for the engagement — all customer-specific artifacts
  (the mapping file, generated SQL) live there, never inside this skill.

## Quick Start

```text
# 1. Copy the closest adapter as a starting mapping, edit sources for the customer:
#    references/adapters/{epic_clarity_caboodle,x12_837_835,omop_cdm,fhir}.yaml
# 2. Generate the layer from the mapping:
python3 scripts/generate_semantic_layer.py --mapping <customer>_mapping.yaml --out generated
# 3. Review generated/plan.md, then deploy generated/01_silver.sql and 03_metric_views.sql
#    to the target schema, and smoke-test:  SELECT MEASURE(<measure>) FROM <mv>
```

## Workflow

### Step 1: Assess

Introspect the customer's source catalog/schema (`information_schema` / workspace files). Identify
which canonical entities can be populated — that set decides which metric views are in scope. Pick the
closest adapter(s) from `references/adapters/`.

```text
SELECT table_name, column_name FROM <catalog>.information_schema.columns WHERE table_schema = '<src>';
```

### Step 2: Map

Draft `<customer>_mapping.yaml` in the working dir (start from an adapter via `extends:`). Auto-map
physical columns to canonical fields; flag low-confidence bindings with `# REVIEW` and confirm them
with the user. See `references/mapping_spec.md`.

```yaml
entities:
  encounter:
    source: <catalog>.<schema>.<table>
    fields: { encounter_id: ENC_CSN_ID, los_days: "datediff(disch, admit)" }
    enums:  { encounter_class: { source_column: ENC_TYPE_C, map: {"101": inpatient}, default: other } }
```

### Step 3: Generate

Run the generator. It infers scope (skips metric views whose entity is unmapped) and skips any measure
whose canonical fields are missing — nothing broken is emitted. See `references/mv_generation.md`.

```text
python3 scripts/generate_semantic_layer.py --mapping <customer>_mapping.yaml --out generated
# -> generated/01_silver.sql, generated/03_metric_views.sql, generated/plan.md
```

### Step 4: Justify

Present `plan.md` — the grain-grouped metric-view plan — for sign-off: which views/measures were
built, which were skipped and why, and any auto-decided design fork (e.g. payer economics on the
conformed `member_month` grain).

### Step 5: Deploy & Expose

On explicit go-ahead, run `01_silver.sql` then `03_metric_views.sql` against the target schema,
validate, and smoke-test each metric view. Then hand off to Genie and a starter Lakeview dashboard.
See `references/consumption.md`.

```text
SELECT MEASURE(avg_los_days), MEASURE(readmission_30day_count)
FROM <catalog>.<schema>.mv_care_delivery__encounter;
```

## Key Parameters

| Parameter | Default | Options | Effect |
|-----------|---------|---------|--------|
| `--mapping` | (required) | path | The per-customer source-mapping file |
| `--out` | `generated` | path | Output dir for the generated SQL + plan |
| `--skill` / `--plugin` | skill root | path | Where the catalog references live (rarely overridden) |
| mapping `scope.domains` | all mappable | domain list | Restrict which domains generate |

## Expected Outputs

- `generated/01_silver.sql` — one conforming view per mapped entity (physical → canonical names, enum
  CASE, joins, filters).
- `generated/03_metric_views.sql` — one `mv_<domain>__<name>` per in-scope metric view, atomics as
  aggregates and composites as `MEASURE()/MEASURE()`.
- `generated/plan.md` — the justify report (built vs skipped, with reasons).

## Troubleshooting

- **`UNRESOLVED_COLUMN` on deploy** — the mapping references a physical column that does not exist.
  Fix the mapping's `fields`/`enums`, regenerate; the catalog and generator do not change.
- **`DATATYPE_MISMATCH` on a flag** — a source flag is INT where a boolean is expected. Wrap it:
  `CAST(<col> AS BOOLEAN)` (robust to both int and boolean).
- **A metric view is missing** — its entity was not mapped; check `plan.md` for the skip reason.
- **A measure is missing** — a canonical field it needs is unmapped (e.g. no `allowed_amount` →
  `net_collection_rate` is skipped). Map the field or accept the reduced coverage.
- **A rate looks wrong on rollup** — it must be a composite (`MEASURE(a)/MEASURE(b)`), never a stored
  or averaged rate. Run the validator.

## Guardrails

- **Only what's mapped gets generated** — unmapped entities silently drop their metric views.
- **Nothing customer-specific enters this skill** — mappings, generated SQL, and secrets stay in the
  working directory.
- **Validate before deploy** — `python3 scripts/validate_catalog.py` must report 0 errors; never
  deploy a measure that fails it.
- **Confirm before outward writes** — deploying views/metric views and creating Genie spaces or
  dashboards are outward actions; show the plan and get explicit approval.
- **Never invent measures inline** — if a customer needs one the catalog lacks, add it to the catalog
  (validate + render), then regenerate. Composites must be ratio-of-measures.
- **Run after any catalog edit**: `validate_catalog.py` (correctness gate) then `render_catalog.py`
  (regenerate `references/catalog.md`).

## References

- `references/canonical_model.yaml` — the entity contract (grains + required fields).
- `references/measure_catalog/*.yaml` — the 64 measure definitions across 6 domains (source of truth).
- `references/catalog.md` — human-readable rendering of all measures (generated).
- `references/adapters/*.yaml` — starter source mappings: Epic Clarity/Caboodle, X12 837/835/834,
  OMOP CDM, FHIR.
- `references/workflow.md` · `mapping_spec.md` · `mv_generation.md` · `consumption.md` — the workflow.
- `scripts/validate_catalog.py` · `render_catalog.py` · `generate_semantic_layer.py` — the tooling.
- `tests/` — functional tests that run the validator and generator.
