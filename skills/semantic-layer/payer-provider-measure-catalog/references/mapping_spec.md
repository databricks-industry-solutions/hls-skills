# Source-mapping file spec

The per-customer mapping file is the **only** customer-specific input. It lives in the SA's working
directory (e.g. `<customer>_mapping.yaml`), NOT in the plugin. It binds physical sources to the
canonical model; the measure catalog never changes.

## Top-level keys

```yaml
name: <customer_slug>
description: <one line>

extends:                      # optional: inherit adapter defaults (list = compose sources)
  - adapters/epic_clarity_caboodle.yaml
  - adapters/x12_837_835.yaml

target:                       # where generated assets land
  catalog:      <catalog>
  schema:       <schema>
  warehouse_id: <id>

scope:                        # OPTIONAL. Default = generate every MV whose entities are all mapped.
  domains: [care_delivery, claims, payer_economics]

entities:                     # the mappings — see below
  <entity>: { ... }
```

## Per-entity keys

```yaml
encounter:
  source: <catalog>.<schema>.<table>       # primary / grain-defining table
  grain_keys: [<physical key col(s)>]      # must resolve to the entity's canonical grain
  joins:                                    # OPTIONAL multi-table entity — MUST be to-one
    - table: <table>
      on:    "<join predicate>"
      type:  left
  fields:                                   # canonical_field: <physical column | SQL expr>
    <canonical_field>: <expr>
  enums:                                    # OPTIONAL physical value -> canonical value
    <canonical_field>:
      source_column: <physical col>
      map: { "<phys>": <canonical_value>, ... }
      default: other
  transform:                                # OPTIONAL named macro (e.g. span expansion)
    macro: span_to_monthly
    args: { ... }
```

## Rules

- **Only map what exists.** Omit entities the customer can't populate; their metric views drop out.
- **Field expressions** may be any Spark SQL scalar expression (rename, `datediff`, `case`,
  arithmetic, `coalesce`). The generator validates that referenced physical columns exist.
- **Joins must be to-one.** A join that fans out the grain is rejected (it would double-count measures).
- **Enums keep the boundary clean:** the customer maps physical codes → canonical enum values; the
  catalog owns the logical filter (e.g. `encounter_class = 'inpatient'`).
- **Transforms are named, shipped macros** — not free-form SQL. `span_to_monthly` expands coverage
  spans into member-months. Add new macros to the plugin, not the mapping.
- **`member_month`** is a derived/conformed entity: its mapping references `derived_from` (a claims
  rollup + enrollment join) rather than a single source table. See `x12_837_835.yaml`.

## Auto-draft conventions

When drafted during Assess:
- Every binding the tool is unsure about gets a trailing `# REVIEW: <question>`.
- Required canonical fields with no match are emitted as `<field>:  # REVIEW: unmapped`.
- Enum maps are pre-filled from the adapter but always flagged for code-set confirmation.
