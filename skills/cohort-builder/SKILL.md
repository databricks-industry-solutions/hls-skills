---
name: hls-cohort-builder
description: >-
  Build a defensible, reproducible patient cohort from structured coded clinical data
  (OMOP/FHIR-flattened conditions, labs, meds, procedures). Use when the user describes
  a patient population — e.g. "build a cohort of type 2 diabetics with uncontrolled
  HbA1c", "how many patients qualify for X", "define a sepsis cohort". Grounds the
  definition in codes ACTUALLY present in the data (no hallucinated ICD/LOINC codes),
  SURFACES ambiguous clinical thresholds for the user to choose (never silently picks),
  reports feasibility (N) before building, materializes a verified cohort table with a
  reproducible phenotype definition, and never fabricates literature citations. Run by
  calling the vetted entrypoints in scripts/cohort_run.py — do not hand-write cohort SQL.
  Structured/coded data only (not free-text notes).
---

# HLS Clinical Cohort Builder — Literature-Informed, Feasibility-Aware

<!--
Genie Code skill. Install to /Users/<you>@databricks.com/.assistant/skills/hls-cohort-builder/
(personal) or /Workspace/.assistant/skills/... (shared). Part of the "Genie Science"
HLS skill family. MVP scope: STRUCTURED clinical data, NOT free-text notes.
-->

## What this skill does

Turns an analyst's natural-language description of a patient population into a
**defensible, reproducible, feasibility-checked cohort** over structured clinical
data — grounding codes in the data, surfacing ambiguous thresholds, checking
feasibility before building, and emitting a verified cohort + reproducible definition.

## ⛔ HOW TO RUN THIS SKILL — EXECUTE, DO NOT REIMPLEMENT

**Call the ONE vetted entrypoint `run_cohort` and report its output. Do NOT write your
own cohort SQL, and do NOT pick a clinical threshold yourself.**

Use the TWO explicitly-named functions — they make each step's intent unmistakable:

```python
import sys
sys.path.append('<this-skill-dir>/scripts')   # the scripts/ folder next to this SKILL.md
from cohort_run import preview_cohort_options, build_confirmed_cohort

# STEP 1 — READ-ONLY preview. Grounds codes in the data and returns real cohort-size
# options for the ambiguous threshold. Builds NOTHING. Show its output to the user.
print(preview_cohort_options("<catalog.schema.table>",
                             intent_text="<the user's exact phrasing>",
                             condition_codes=[("ICD10CM","E11.9"), ("ICD10CM","E11.65")]))

# STEP 2 — ONLY after the user picks a threshold. Materializes + verifies the cohort.
# Pass BOTH the value AND the operator from the option the user chose. If you omit
# threshold_op for an ambiguous term, the tool recovers it from the matching option;
# it will NOT silently assume ">". (HEDIS "poor control" is >=9.0, NOT >9.0.)
print(build_confirmed_cohort("<catalog.schema.table>",
                            intent_text="<same phrasing>",
                            condition_codes=[("ICD10CM","E11.9"), ("ICD10CM","E11.65")],
                            threshold_value=9.0, threshold_op=">="))   # e.g. user chose HEDIS
```

`preview_cohort_options` is read-only and safe to call immediately — it takes no
threshold and creates no tables, so it IS the "surface the options first" step. Call it,
present its real numbers to the user, then call `build_confirmed_cohort` with their choice —
**the value AND the operator together** (they are both part of the choice). Report the
tool's actual numbers — never substitute your own threshold table.

### Getting the condition codes — use a terminology MCP if one is connected

`condition_codes` is an INPUT CONTRACT: a list of `(vocabulary, code)` pairs. Where they
come from does NOT matter to the skill — they are always grounded against the actual data
(codes not present are excluded), so the source cannot introduce a bad code.

**Prefer a connected terminology MCP** (e.g. BioPortal — Biomedical Ontology & Terminology)
to expand the user's clinical concept into a real, hierarchy-aware code set, rather than
guessing codes yourself:

- Different MCP servers take different INPUTS — a terminology server wants a *term*
  ("type 2 diabetes"); a notes/NLP server wants a *string of clinical text*; another may
  want structured params. **Read the connected server's tool schema and adapt to it** — do
  not assume a fixed signature. Your goal is only to obtain `(vocabulary, code)` pairs.
- Pass what you get to `preview_cohort_options(..., condition_codes=[...],
  code_source="<server name>")`. Set `code_source` so the readout records provenance.
- If NO terminology MCP is connected, propose codes from your own knowledge and pass
  `code_source="model-proposed"`. Grounding still catches anything not in the data.

Never state a code as authoritative that the tool's output did not confirm as grounded.

**Why this is mandatory (not a suggestion) — the baseline failures this prevents:**
1. **Silent threshold substitution.** Un-guided Genie picked "HbA1c ≥ 9.0" for
   "uncontrolled" without flagging that ">8.0" is equally standard, quietly dropping
   16% of true members. `preview_cohort` surfaces BOTH options with the N impact of
   each and forces the user to choose. Never pick for them.
2. **Hallucinated codes.** `preview_cohort` reports which requested codes are NOT in
   the data and excludes them — it will not build a cohort on a code that does not exist.
3. **Fabricated citations.** The entrypoints NEVER attach a literature citation. If you
   cite a published phenotype, it must be resolved against a real literature source (an
   MCP literature server) — see the literature section. NEVER invent a PMID or NCT id;
   the baseline fabricated both.

The sections below document the method for transparency/review — they are NOT a recipe
to re-code by hand.

## Scope (MVP)

- **In scope:** structured, coded clinical tables — conditions/diagnoses
  (ICD-10-CM, SNOMED CT), observations/labs (LOINC + values), medications
  (RxNorm), procedures (CPT/HCPCS), demographics. OMOP CDM or FHIR-flattened
  layouts are ideal.
- **Out of scope (this version):** free-text note parsing, NER, and OCR. If the
  user's signal lives only in unstructured notes, say so plainly and stop — the
  concept-extraction-from-text capability is a future skill.

## When to use (trigger conditions)

Invoke when the user describes a patient population and wants it built, counted,
validated, or refined. Example prompts:
- "Build a cohort of type 2 diabetics with uncontrolled HbA1c on metformin."
- "How many patients would qualify for a heart-failure readmission study?"
- "Define a sepsis cohort and check it against the literature."
- "Is this cohort feasible, or is N too small?"

## Inputs the skill needs (ask if missing)

1. **Population intent** — the clinical description (the user's prompt usually
   has it; restate your interpretation back for confirmation).
2. **Source tables** — the coded clinical tables and their schema/CDM. If OMOP,
   note the CDM version; if FHIR-flattened, note the resource tables.
3. **Study intent** (optional but improves feasibility) — what the cohort is for
   (retrospective analysis, trial screening, RWE), which shapes minimum-N and
   which criteria matter.

## Literature layer — MCP retrieval + deterministic verification (Architecture A)

Citations are handled by a division of labor that makes fabrication impossible:

1. **You (the agent) RETRIEVE.** If a literature MCP server is connected to this
   workspace (e.g. a PubMed / Europe PMC / ClinicalTrials.gov server the admin
   approved and the user connected), call it to find candidate publications for the
   phenotype. Collect the **PMIDs** it returns. Do NOT connect servers yourself and
   do NOT assume one exists — check what is connected.

2. **The entrypoint VERIFIES.** Pass those PMIDs to `run_cohort(..., mcp_citations=[...])`.
   The vetted code resolves EVERY PMID against PubMed and keeps only those that exist.
   Anything unresolvable is dropped. This is why you must never write a citation into
   your prose yourself — route it through `mcp_citations` so it is verified.

3. **Automatic fallback.** If you pass no `mcp_citations` (no server connected), the
   entrypoint runs a direct PubMed search itself as a floor. Either path fails CLOSED:
   if nothing verifies, NO citation is attached — never a fabricated one.

**Hard rule:** never state a PMID/NCT id in your own message that did not come back
verified in the entrypoint's output. The baseline fabricated PMID 22319177 (an
unrelated cancer paper) and a bogus Klompas citation — that must never recur.

## What the entrypoints do internally (for transparency — NOT a recipe to re-code)

`preview_cohort_options` and `build_confirmed_cohort` (in `scripts/cohort_run.py`) perform
these steps. This section documents them for review; do not reimplement them by hand.

1. **Ground the codes.** The proposed `(vocabulary, code)` set — from a terminology MCP,
   clinical-notes parsing, or the model — is checked against the actual table. Codes not
   present are excluded and reported. Prefer hierarchy-expanded concept sets (see
   `references/ontology_crosswalks.md`); grounding catches anything spurious regardless of source.

2. **Surface threshold ambiguity.** For a term with more than one standard operational
   definition (e.g. "uncontrolled HbA1c" → >8.0% vs ≥9.0%), `preview_cohort_options`
   returns BOTH options with the real cohort N for each and stops. Never pick for the user.

3. **Literature (separate, verified).** Citations are resolved via `scripts/literature.py`
   (agent-retrieved MCP candidates verified against PubMed, or a direct-PubMed floor) and
   fail closed — no verified source, no citation. Never fabricate a PMID/NCT id. Naming a
   real guideline in prose is fine; asserting an unverified resolvable ID is not.

4. **Feasibility before building.** The preview reports eligible N so the user sees size
   before materializing (default warn < 100, hard-warn < 20). Do not build an infeasible
   cohort silently.

5. **Materialize + verify.** `build_confirmed_cohort` writes the cohort table and a
   machine-readable phenotype definition (codes + comparators), then re-checks that
   membership matches the definition exactly. Hand off to a **Genie Space** for NL
   exploration (Genie Code builds; Genie Space explores).

## Guardrails

- Reproducibility over convenience: always emit the coded phenotype definition,
  never just a patient-id list.
- Never expand or alter the user's criteria from literature without citing the
  source and getting confirmation.
- Feasibility gate is not optional — never hand over a cohort without reporting
  N and per-criterion attrition.
- Respect PHI governance: the cohort table inherits UC access controls; if the
  source is raw PHI and the consumer is an analyst, recommend running the
  `hls-phi-deidentifier` skill on the output or building on an already
  de-identified source.
- If the literature MCP servers are unavailable, degrade loudly, not silently.

## Key parameters (`preview_cohort_options` / `build_confirmed_cohort`)

`preview_cohort_options(table, intent_text, condition_codes, code_source="model-proposed", ...)`
`build_confirmed_cohort(table, intent_text, condition_codes, threshold_value, threshold_op=None, cohort_table=None, mcp_citations=None, ...)`

| Parameter | Default | Range / values | What it controls |
|---|---|---|---|
| `table` | — (required) | `catalog.schema.table` | Coded clinical records (OMOP/FHIR-flattened). |
| `intent_text` | — (required) | the user's exact phrasing | Scanned for ambiguous clinical terms (e.g. "uncontrolled") that trigger the threshold-choice gate. |
| `condition_codes` | — (required) | `[(vocab, code)]` | Proposed concept set from any source; **grounded against the data** (codes not present are excluded), so a bad source can't inject a bad code. |
| `code_source` | `"model-proposed"` | e.g. `"BioPortal MCP"`, `"clinical-notes MCP"` | Provenance recorded in the readout. Preview-only. |
| `threshold_value` | — (required for build) | numeric | The clinical threshold the **user chose** after preview. Never pick this yourself. |
| `threshold_op` | `None` | `>`, `>=`, `<`, `<=`, `=` | Comparator — **part of the user's choice**, not a default. For an ambiguous term the tool recovers it from the chosen option if omitted; it never silently assumes `>`. |
| `cohort_table` | auto | `catalog.schema.table` | Where the materialized cohort lands. |
| `mcp_citations` | `None` | `[PMID, ...]` | Candidate PMIDs Genie retrieved from a connected literature MCP; verified (kept only if they resolve) — never asserted unverified. |

Feasibility thresholds (engine defaults, not arguments): warn when eligible **N < 100**,
hard-warn when **N < 20**. The preview reports N before anything is built.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Preview returns a smaller code set than requested | Some proposed codes aren't present in the data (grounding excluded them) | Expected and correct — the readout lists which codes were dropped. Use a hierarchy-expanded concept set if you're missing descendants. |
| It refuses to build and returns a choice prompt | The intent has an ambiguous threshold (e.g. "uncontrolled") and no `threshold_value` was passed | This is the confirm-gate working. Show the options + N impact to the user, get a number, call `build_confirmed_cohort`. |
| A harmless preview call is blocked by a permission reviewer | Using an overloaded `run_cohort(...)` where preview vs build differ only by an argument | Call the explicitly-named `preview_cohort_options` (read-only, no threshold arg) — the reviewer can't infer intent from arguments (Principle 6). |
| No citations attached | No literature MCP connected and/or PubMed unreachable | Correct fail-closed behavior — degrade loudly, never fabricate a PMID. You may still name a guideline (ADA/HEDIS) in prose. |
| Cohort N far smaller than expected | A stricter threshold or missing OR-criteria | Re-check the threshold choice and whether criteria should be OR-combined; the baseline's silent >9.0 pick dropped 16% of members this way. |
| The skill didn't load on a naive prompt | Discovery competition — a built-in `data-sampling` skill matched harder (Principle 4b) | Name it explicitly ("use the hls-cohort-builder skill") or rely on the workspace memory instruction; contested-domain skills are invocable, not ambient. |

## Files

- `scripts/cohort_run.py` — **the entrypoints**: `preview_cohort_options` (read-only) and
  `build_confirmed_cohort` (materialize + verify). This is what the skill runs.
- `scripts/literature.py` — citation resolver: MCP-verify + direct-PubMed floor, fail-closed.
- `references/ontology_crosswalks.md` — SNOMED/ICD-10/RxNorm/LOINC notes + OMOP concept-set guidance.
- `references/phenotype_standards.md` — PheKB/eMERGE/OHDSI conventions and minimum-N heuristics.
- `references/mcp_literature_servers.md` — how to discover & call literature/terminology MCP servers.
