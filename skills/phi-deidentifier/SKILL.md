---
name: hls-phi-deidentifier
description: >-
  De-identify PHI/PII in a structured Unity Catalog table under HIPAA Safe Harbor
  before analysis or sharing. Use whenever the user asks to de-identify, redact,
  anonymize, mask, scrub, or "make safe / shareable" a table of patient, member,
  claims, or clinical records — especially before analysis, export, or handing data
  to a collaborator. Goes beyond stripping direct identifiers (names, SSN, MRN,
  email, phone, dates): it ENFORCES k-anonymity on quasi-identifiers (age, ZIP,
  sex, length-of-stay) so the result is not silently re-identifiable, applies the
  result as a Unity Catalog view over the raw table (no second copy of PHI), and
  returns a readout of what was removed, what was generalized, and which columns
  are still analyzable. Structured/tabular data only. Run by calling the vetted
  entrypoint scripts/run_deid.py — do not hand-write de-identification SQL.
---

# HLS PHI/PII De-Identifier (Safe Harbor) — Structured Data

<!--
Genie Code skill. Install to /Users/<you>@databricks.com/.assistant/skills/hls-phi-deidentifier/
(personal) or /Workspace/.assistant/skills/... (shared). Part of the "Genie Science"
HLS skill family. MVP scope: STRUCTURED data only.
-->

## What this skill does

Operationalizes the **HIPAA Safe Harbor** method (45 CFR §164.514(b)(2)) over
**structured** Unity Catalog tables: it detects the 18 Safe Harbor identifier
classes at the column and value level, applies a defensible per-class
de-identification strategy, enforces it through Unity Catalog governance
(a dynamic view over the raw table so raw PHI never moves), and emits an
analyst-facing readout.

## ⛔ HOW TO RUN THIS SKILL — EXECUTE, DO NOT REIMPLEMENT

**Call the vetted entrypoint. Do NOT write your own de-identification SQL.**

```python
import sys
sys.path.append('<this-skill-dir>/scripts')   # the scripts/ folder next to this SKILL.md
from run_deid import run_deid
print(run_deid("<catalog.schema.table>"))       # e.g. the table the user named
```

That single call runs the whole pipeline (profile → PHI detection → k-anonymity
generalization → view-over-raw → verification → readout) and returns the report to
show the user. Report its output; do not paraphrase or recompute it.

**Why this is mandatory (not a suggestion):** k-anonymity is the entire point of
this skill, and it is easy to get subtly, invisibly wrong. Hand-written de-id SQL
reliably forgets that *derived* columns are quasi-identifiers — e.g. emitting
`length_of_stay_days` but excluding it from the k-anonymity check, producing a view
that reports "k=5" while half its rows are uniquely re-identifiable. The entrypoint
treats every quasi-identifier (including derived ones) as in-scope and **verifies
actual k over all surviving columns**, so that false-assurance failure cannot happen.
If you reimplement in ad-hoc SQL, you will reproduce that failure. Call `run_deid`.

The sections below document what the entrypoint does internally, for transparency
and review — they are NOT a recipe for you to re-code by hand.

## CRITICAL — what this skill is and is NOT

- This skill **operationalizes** Safe Harbor. It does **not** and cannot
  *certify* a dataset as de-identified. Under HIPAA, that determination is made
  by the covered entity's Privacy Officer (Safe Harbor) or a qualified
  statistician (Expert Determination). **Every report this skill emits must
  carry that disclaimer.** Do not tell the user their data is "HIPAA
  compliant" or "de-identified" — say it has been "processed against the Safe
  Harbor rule set, pending Privacy Officer review."
- MVP scope is **structured data only** (typed columns, coded values). Free-text
  notes, scanned PDFs, and images are **out of scope** for this version. If the
  user points at a `/Volumes/**` path of documents or an obvious free-text
  column, tell them plainly it is out of scope for the MVP and stop — do not
  attempt partial NER.

## When to use (trigger conditions)

Invoke when the user asks to de-identify, redact, scrub, mask, or anonymize
PHI/PII in a Unity Catalog table, or asks to prepare a dataset for analysts /
research / sharing under Safe Harbor. Example prompts:
- "De-identify the `hls.raw.patients` table for the analytics team."
- "Apply Safe Harbor to our claims table and show me what got masked."
- "Prep `encounters` so a data scientist can use it without seeing PHI."

## Inputs the skill needs (ask if missing)

1. **Target** — fully-qualified table (`catalog.schema.table`) or list of tables.
2. **Consumer role** — the group/role that should see the de-identified view
   (e.g. `analysts`). Governance is role-driven.
3. **Strategy overrides** (optional) — any column where the user wants a
   specific treatment (e.g. "keep age as a band," "tokenize MRN, don't drop it").
4. **Re-identification need** (optional) — whether a locked key map is required
   for later re-linkage. If yes, it lands in a separately-governed schema.

## The 18 Safe Harbor identifier classes (reference)

See `references/safe_harbor_classes.md` for the authoritative list and the
default treatment per class. The 18 classes, in brief: names; geographic
subdivisions smaller than state (incl. ZIP — keep only first 3 digits, and zero
them if the 3-digit area has ≤ 20,000 people); **all date elements finer than
year** (and any age > 89 → "90+"); phone; fax; email; SSN; MRN; health-plan
beneficiary number; account number; certificate/license number; vehicle
identifiers; device identifiers; URLs; IP addresses; biometric identifiers;
full-face photos; and **any other unique identifying number/characteristic/code**.

## Procedure

### 1. Profile the target
Run `scripts/profile_table.py`. For each column, capture: name, type, a sample
of distinct values, null rate, and cardinality. This drives detection and is the
first section of the audit report.

### 2. Detect & classify PHI columns
Run `scripts/detect_phi.py`. Assign each column to a Safe Harbor class (or
"not PHI") using, in order of trust:
- **Unity Catalog tags / PII classifiers** already on the column — trust these first.
- **Name heuristics** — `ssn`, `mrn`, `dob`, `zip`, `phone`, `email`, etc.
- **Value validators** — deterministic regex + checksums: SSN format, NPI
  (Luhn with 80840 prefix), Luhn for card/account numbers, email/phone/IP/URL
  regex, date parsing. Validators are authoritative over name heuristics.
- **`ai_classify`** as a *tie-breaker only* for ambiguous columns, never as the
  sole basis for a decision. Log every AI-assisted call to MLflow.

Output a **classification table**: `column, detected_class, method, confidence,
proposed_strategy`. **Surface this to the user for confirmation before
transforming anything.** Detection is recall-dominated — when uncertain, flag
as PHI rather than passing it through.

### 3. Choose per-class strategy
Defaults (overridable) from `references/deid_strategies.md`:
- **Direct identifiers** (name, SSN, MRN, phone, email, account #, device ID,
  URL, IP, license, vehicle) → **redact** (null/`***`) or **tokenize** (salted
  HMAC) if re-linkage is needed.
- **Dates** → reduced to **year** (Safe Harbor permits year), with intervals
  preserved via derived fields (e.g. length-of-stay) so longitudinal analysis
  survives. (Consistent patient-level date-shift is an alternative where day
  granularity is needed; the entrypoint uses year-reduction + interval derivation.)
- **Ages** → pass through if ≤ 89, else bucket to "90+".
- **ZIP / geo** → first 3 digits, zeroed for the ~17 restricted prefixes
  (list in `references/restricted_zip3.md`).
- **Quasi-identifiers** (sex, race, admit year, 3-digit ZIP) → keep, but they
  feed the residual-risk check in step 5.

### 4. Enforce k-anonymity (the step baseline Genie skips)
Run `scripts/kanon.py`. Direct-identifier stripping is table stakes — baseline
Genie already does it. The differentiated, mandatory step is quasi-identifier
generalization to a k-anonymity target (default k=5): without it, stripped data
is still re-identifiable (measured baseline: k=1, ~87% of rows unique).
- The engine coarsens quasi-identifiers (age, geo/ZIP, length-of-stay, sex) along
  defined hierarchies, using a **utility-weighted greedy search** so it sacrifices
  low-value QIs (geo) before high-value clinical ones (age, LOS).
- It reaches k_target with minimal generalization, suppressing residual sub-k rows
  only if generalization alone cannot get there (and only within a suppression cap).
- **Report the privacy/utility trade explicitly**: which QIs were generalized to
  what level, k achieved, rows suppressed. Never silently destroy analytic value.

### 5. Apply through Unity Catalog governance (do NOT write a second PHI copy)
This is the demo's spine. Run `scripts/apply_uc_governance.py`:
- Create a **dynamic VIEW over the raw table** that drops direct identifiers,
  converts dates to interval-preserving derived fields, applies the step-4
  generalization, and filters out suppressed sub-k equivalence classes. Raw PHI
  is **never copied** — baseline Genie's physical copy left the raw SSNs fully
  exposed; a view does not.
- Gate consumer access with `is_account_group_member` and ensure the raw source
  is not readable by the consumer role (so PHI is not exposed via the back door).
- If tokenizing with re-linkage, write the key map to a **separately-governed,
  locked schema** — never co-located with the analyst-readable view.
- Salt comes from a Databricks secret scope, never a literal (the demo literal is
  flagged as such in the audit report).
Always show the user the raw-role vs. consumer-role result side by side.

### 6. Verify (residual-risk scan) & emit the readout
The entrypoint measures **actual k-anonymity over ALL surviving quasi-identifiers**
(including derived ones like length-of-stay) and runs a **residual leak scan** on the
output view — any PHI pattern or near-unique free-text column is a hard FAIL regardless
of k. It then emits the analyst readout (what was removed / tokenized / generalized /
suppressed / still-analyzable), persists the verified readout to a UC audit table, and
appends the **mandatory Safe Harbor disclaimer** naming the Privacy Officer as the
certifying authority. Passthrough is **deny-by-default**: only affirmatively-safe
(numeric) columns pass through; unknown non-numeric columns are suppressed, never leaked.

## Guardrails

- Never transform a column the user hasn't seen classified (step 2 confirmation).
- Never claim the output "is de-identified / HIPAA compliant." Use "processed
  against Safe Harbor, pending Privacy Officer review."
- Never write a re-identification key map into an analyst-accessible schema.
- Never echo raw PHI values into chat beyond the minimum needed to confirm a
  classification, and mask them when you do.
- If detection confidence is low across many columns, stop and ask rather than
  guessing — false negatives leak PHI.

## Key parameters (`run_deid`)

`run_deid(raw_fqn, view_name=None, k_target=5, profile=None, warehouse_id=None)`

| Parameter | Default | Range / values | What it controls |
|---|---|---|---|
| `raw_fqn` | — (required) | `catalog.schema.table` | The raw table to de-identify. Read-only source; never overwritten. |
| `view_name` | `<table>_deid` | any valid view name | Name of the governed view created over the raw table. |
| `k_target` | `5` | integer ≥ 2 (2–10 typical) | k-anonymity target. Higher k = stronger re-id resistance, more generalization / utility loss. 5 is the common Safe-Harbor-adjacent default; raise for small populations at higher risk. |
| `profile` | `None` (ambient auth) | a Databricks CLI profile | Local runs only; in-workspace uses ambient auth. |
| `warehouse_id` | `None` (first available) | a SQL warehouse id | Pin the warehouse if the default pick is wrong. |

Internals worth knowing (set by the engine, not arguments): generalization ladders are
data-driven per column (numeric → quartile buckets → halves → suppress; categorical → keep
→ merge-rare-into-'other' → suppress); row suppression is capped (`max_suppression_frac`,
default 0.10) so the engine prefers generalization over dropping rows; passthrough is
deny-by-default (only numeric measures pass; unknown non-numeric columns are suppressed).

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Output view over-generalizes to a huge k (all utility destroyed) | A raw date/high-cardinality column was routed through the generic-QI path and collapsed k | Confirm dates are year-reduced / interval-derived, not treated as raw QIs; report it — this was the Principle 7 double-counting bug. |
| Readout says `PASS` but you suspect re-identifiability | A quasi-identifier (esp. a *derived* one like length-of-stay) was excluded from the k-check | This cannot happen via `run_deid` (it checks all surviving QIs). If you see it, someone hand-wrote SQL — re-run through the entrypoint. |
| A free-text / name column survived unredacted | Detection is recall-limited and missed it | The residual leak scan should hard-FAIL this; if it slipped through, add the column to detection and re-run. Never pass through unknown non-numeric columns. |
| `k_target` unreachable without dropping many rows | Population too small for the chosen k | Lower `k_target`, or accept the (capped) suppression the engine reports — don't silently ship sub-k rows. |
| Consumer can still read raw PHI | The raw source table isn't restricted for the consumer role | Governance is a *view*; you must also ensure the consumer role cannot read the raw table (back-door exposure). |
| "HIPAA compliant" appears in output | — | Never claim it. The report must say "processed against Safe Harbor, pending Privacy Officer review." |

## Files

- `scripts/run_deid.py` — **the entrypoint**: profile → detect → k-anon generalization →
  view-over-raw → residual leak scan → readout + UC audit log. This is what the skill runs.
- `scripts/kanon.py` — utility-weighted k-anonymity generalization engine (generic, any-table).
- `scripts/apply_uc_governance.py` — builds the schema-driven dynamic view over the raw table.
- `scripts/detect_phi.py` — PHI classifier (UC tags → name heuristics → value validators).
- `scripts/profile_table.py` — column profiler.
- `scripts/deid_report.py` — analyst-facing readout builder.
- `references/safe_harbor_classes.md` — the 18 classes + default treatment.
- `references/deid_strategies.md` — strategy definitions and when to use each.
- `references/restricted_zip3.md` — ZIP3 prefixes that must be zeroed.
