---
name: hls-phi-deidentifier
description: >-
  De-identify PHI/PII in a structured Unity Catalog table under HIPAA Safe Harbor before
  analysis or sharing. Triggers when the user asks to de-identify, redact, anonymize, mask,
  scrub, or "make safe / shareable" a table of patient, member, claims, or clinical records —
  especially before analysis, export, or handing data to a collaborator. Goes beyond stripping
  direct identifiers (names, SSN, MRN, email, phone, dates): it ENFORCES k-anonymity on
  quasi-identifiers (age, ZIP, sex, length-of-stay) so the result is not silently
  re-identifiable, applies the result as a Unity Catalog view over the raw table (no second
  copy of PHI), and returns a readout of what was removed, generalized, and still analyzable.
  Structured/tabular data only. Run by calling the vetted entrypoint scripts/run_deid.py — do
  not hand-write de-identification SQL. For building patient cohorts use hls-cohort-builder.
version: 1.0.0
author: Databricks HLS Field Engineering
license: Databricks License
---

# HLS PHI/PII De-Identifier (Safe Harbor) — Structured Data

## Overview

Operationalizes the **HIPAA Safe Harbor** method (45 CFR §164.514(b)(2)) over **structured**
Unity Catalog tables: it detects the 18 Safe Harbor identifier classes at the column and value
level, applies a defensible per-class de-identification strategy, **enforces k-anonymity on the
surviving quasi-identifiers**, and applies the result as a **dynamic Unity Catalog view over the
raw table** so raw PHI never moves. The output is a governed view plus an analyst-facing readout
of what was removed, tokenized, generalized, suppressed, and still analyzable — with the mandatory
Safe Harbor disclaimer. It **operationalizes** Safe Harbor; it does **not** certify
de-identification — that is the covered entity's Privacy Officer's determination.

Runs on the **execution model**: Genie Code calls `scripts/run_deid.py` and reports its output —
it does not hand-write de-identification SQL. This matters because hand-written de-id reliably
forgets that *derived* columns are quasi-identifiers (e.g. emitting `length_of_stay_days` but
excluding it from the k-check → a view reporting "k=5" while half its rows are uniquely
re-identifiable). The entrypoint treats every quasi-identifier as in-scope and verifies actual k.

## When to Use

- "De-identify the `hls.raw.patients` table for the analytics team."
- "Apply Safe Harbor to our claims table and show me what got masked."
- "Prep `encounters` so a data scientist can use it without seeing PHI."
- "Anonymize this member table before we share it with a vendor."
- "Is this table safe to export? Make it re-identification-resistant, not just name-stripped."
- "Mask PHI but keep length-of-stay so we can still do longitudinal analysis."

## Prerequisites

- **Compute**: a Databricks SQL warehouse (ambient auth in-workspace, or a CLI `profile=` locally).
- **Inputs**: a fully-qualified structured table (`catalog.schema.table`) with typed columns.
- **Consumer role**: the group/role that should read the de-identified view (governance is role-driven).
- **Environment (optional)**: a Databricks secret scope for the tokenization salt (never a literal);
  a separately-governed schema if a re-identification key map is required.
- **Scope**: structured/tabular data only — free-text notes, scanned PDFs, and images are out of scope.

## Quick Start

```python
import sys
sys.path.append('<this-skill-dir>/scripts')   # the scripts/ folder next to this SKILL.md
from run_deid import run_deid
print(run_deid("<catalog.schema.table>"))       # e.g. the table the user named
```

That single call runs the whole pipeline (profile → PHI detection → k-anonymity generalization →
view-over-raw → verification → readout) and returns the report to show the user. Report its
output; do not paraphrase or recompute it.

## Workflow

**⛔ EXECUTE, DO NOT REIMPLEMENT.** Call `run_deid` and report its output; never write your own
de-identification SQL. The steps below document what the entrypoint does internally — for review,
not a recipe to re-code by hand.

### Step 1: Profile the target

`scripts/profile_table.py` captures per column: name, type, sample distinct values, null rate,
cardinality. This drives detection and is the first section of the audit report.

### Step 2: Detect & classify PHI

`scripts/detect_phi.py` assigns each column to a Safe Harbor class (or "not PHI"), in order of
trust: Unity Catalog PII tags → value validators (SSN/NPI-Luhn/card-Luhn/email/phone/IP/URL/date)
→ name heuristics → `ai_classify` as a tie-breaker only. Detection is recall-dominated (when
unsure, flag as PHI). **Surface the classification table to the user before transforming anything.**

```text
column, detected_class, method, confidence, proposed_strategy   # confirm with the user
```

### Step 3: Choose per-class strategy

Defaults (overridable) from `references/deid_strategies.md`: direct identifiers → redact or
tokenize (salted HMAC) if re-linkage is needed; dates → reduced to year with intervals preserved
via derived fields; ages → pass through if ≤ 89 else "90+"; ZIP → first 3 digits, zeroed for the
restricted prefixes (`references/restricted_zip3.md`).

### Step 4: Enforce k-anonymity (the step baseline Genie skips)

`scripts/kanon.py` generalizes quasi-identifiers to a k-anonymity target (default k=5) with a
**utility-weighted greedy search** — sacrificing low-value QIs (geo) before high-value clinical
ones (age, LOS). Direct-identifier stripping is table stakes; without this step stripped data is
still re-identifiable (measured baseline: k=1, ~87% of rows unique). Reports the privacy/utility
trade explicitly.

### Step 5: Apply through Unity Catalog governance (no second PHI copy)

`scripts/apply_uc_governance.py` builds a **dynamic view over the raw table** that drops direct
identifiers, converts dates to interval-preserving derived fields, applies the step-4
generalization, and filters suppressed sub-k rows. Consumer access is gated with
`is_account_group_member`; the raw source must not be readable by the consumer role. Any key map
lands in a separately-governed, locked schema.

### Step 6: Verify (residual-risk scan) & emit the readout

The entrypoint measures **actual k over ALL surviving quasi-identifiers** (including derived ones)
and runs a **residual leak scan** — any PHI pattern or near-unique free-text column is a hard FAIL
regardless of k. It emits the readout, persists it to a UC audit table, and appends the mandatory
Safe Harbor disclaimer naming the Privacy Officer as the certifying authority.

## Key Parameters

`run_deid(raw_fqn, view_name=None, k_target=5, profile=None, warehouse_id=None)`

| Parameter | Default | Range / Options | Effect |
|-----------|---------|-----------------|--------|
| `raw_fqn` | — (required) | `catalog.schema.table` | The raw table to de-identify. Read-only source; never overwritten. |
| `view_name` | `<table>_deid` | any valid view name | Name of the governed view created over the raw table. |
| `k_target` | `5` | integer ≥ 2 (2–10 typical) | k-anonymity target. Higher k = stronger re-id resistance, more generalization / utility loss. Raise for small populations at higher risk. |
| `profile` | `None` (ambient auth) | a Databricks CLI profile | Local runs only; in-workspace uses ambient auth. |
| `warehouse_id` | `None` (first available) | a SQL warehouse id | Pin the warehouse if the default pick is wrong. |

Internals (engine-set, not arguments): generalization ladders are data-driven per column (numeric
→ quartile buckets → halves → suppress; categorical → keep → merge-rare-into-'other' → suppress);
row suppression is capped (`max_suppression_frac`, default 0.10); passthrough is deny-by-default
(only numeric measures pass; unknown non-numeric columns are suppressed, never leaked).

## Expected Outputs

- A **governed dynamic view** over the raw table (no second PHI copy) readable by the consumer role.
- An **analyst readout**: removed / tokenized / generalized / suppressed / still-analyzable, with
  the k achieved and rows suppressed.
- A **UC audit-table** record of the verified readout, plus the **mandatory Safe Harbor disclaimer**.
- A residual-leak-scan result (hard FAIL on any surviving PHI pattern).

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| View over-generalizes to a huge k (utility destroyed) | A raw date/high-cardinality column routed through the generic-QI path | Confirm dates are year-reduced / interval-derived, not treated as raw QIs. |
| Readout says `PASS` but you suspect re-identifiability | A quasi-identifier (esp. a derived one like LOS) was excluded from the k-check | Cannot happen via `run_deid` (it checks all surviving QIs). If you see it, someone hand-wrote SQL — re-run through the entrypoint. |
| A free-text / name column survived unredacted | Detection is recall-limited and missed it | The residual leak scan should hard-FAIL it; add the column to detection and re-run. Never pass through unknown non-numeric columns. |
| `k_target` unreachable without dropping many rows | Population too small for the chosen k | Lower `k_target`, or accept the (capped) suppression the engine reports — don't silently ship sub-k rows. |
| Consumer can still read raw PHI | The raw source isn't restricted for the consumer role | Governance is a *view*; also ensure the consumer role cannot read the raw table (back-door exposure). |
| "HIPAA compliant" appears in output | — | Never claim it. Say "processed against Safe Harbor, pending Privacy Officer review." |

## Guardrails

1. **Execute, do not reimplement** — call `run_deid`; never hand-write de-id SQL (the LOS k-check
   failure cannot happen via the entrypoint).
2. **Never certify** — the output is "processed against Safe Harbor, pending Privacy Officer
   review," never "de-identified / HIPAA compliant."
3. **Never transform an unconfirmed column** — surface the classification table (step 2) first.
4. **Never write a re-identification key map into an analyst-accessible schema.**
5. **Never echo raw PHI into chat** beyond the minimum to confirm a classification, and mask it.
6. **When detection confidence is low across many columns, stop and ask** — false negatives leak PHI.

## Bundled Resources

- `scripts/run_deid.py` — the entrypoint: profile → detect → k-anon generalization → view-over-raw
  → residual leak scan → readout + UC audit log.
- `scripts/kanon.py` — utility-weighted k-anonymity generalization engine (generic, any-table).
- `scripts/apply_uc_governance.py` — builds the schema-driven dynamic view over the raw table.
- `scripts/detect_phi.py` — PHI classifier (UC tags → validators → name heuristics → ai_classify).
- `scripts/profile_table.py` — column profiler.
- `scripts/deid_report.py` — analyst-facing readout builder.
- `references/safe_harbor_classes.md` — the 18 classes + default treatment.
- `references/deid_strategies.md` — strategy definitions and when to use each.
- `references/restricted_zip3.md` — ZIP3 prefixes that must be zeroed.
- `tests/scorers.py`, `tests/objective.py`, `tests/test_scorers.py` — the objective function,
  component scorers (detection recall/F2, residual-leak gate, utility retention, k-anonymity,
  governance), and their pure-Python unit tests.

## References

- [45 CFR §164.514(b) — Safe Harbor](https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-E/section-164.514) — the de-identification standard.
- [HHS Guidance on De-identification](https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/de-identification/index.html) — Safe Harbor & Expert Determination.
- [Databricks Unity Catalog — dynamic views & row/column masks](https://docs.databricks.com/en/data-governance/unity-catalog/index.html) — governance enforcement.
- [Databricks AI Functions — `ai_classify`](https://docs.databricks.com/en/large-language-models/ai-functions.html) — tie-breaker classification from SQL.
