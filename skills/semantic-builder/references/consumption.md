# Consumption — expose the semantic layer

Phase 5. Once metric views are deployed and validated, wire the consumption surfaces. Reuse existing
skills rather than reinventing them.

## Genie

Use the `genie-rooms` skill (or `databricks genie` CLI / REST) to create or point a Genie space at
the deployed metric views.

- Scope the space to the `mv_<domain>__*` views (not raw silver/gold) so questions resolve through
  governed measures.
- Seed instructions with the domain framing and the atomic-vs-composite note so Genie never sums a
  rate. Feed a few example questions per domain (e.g. "MLR by plan last quarter", "no-show rate by
  department", "30-day readmission rate trend").
- The catalog's `definition` fields make good measure descriptions for the space.

## AI/BI (Lakeview) dashboard

Use `databricks-lakeview-dashboard` to generate a starter dashboard per domain in scope:

- One page per metric view; KPI tiles for the headline composites (ALOS, no-show rate, utilization,
  denial rate, MLR, PMPM) and trend charts over the entity's date dimension.
- Datasets query the metric views via `MEASURE()`, never the base tables.

## Other consumers (no extra work)

Because the layer is governed metric views over gold/silver, these come for free:
- **Power BI** — point at the gold views (DirectQuery or Import); measures are already defined.
- **Feature Store / ML** — the conformed silver/gold entities are feature-ready.
- **Delta Sharing** — share the schema; consumers inherit the same semantics.

## Reporting

Report back: deployed catalog.schema, the list of `mv_<domain>__<name>` created, the Genie space URL,
and the dashboard URL. Note any domains skipped for lack of source, so the customer knows the coverage
boundary.
