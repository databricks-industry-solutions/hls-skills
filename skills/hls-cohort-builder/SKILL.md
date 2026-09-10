---
name: hls-cohort-builder
description: >-
  Cohort builder for structured coded clinical data (OMOP/FHIR-flattened conditions,
  labs, meds, procedures) AND free-text clinical notes. Turns a natural-language
  patient-population description — e.g. "type 2 diabetics with uncontrolled HbA1c",
  "how many patients qualify for X", "define a sepsis cohort" — into a defensible,
  reproducible, feasibility-checked cohort. Grounds codes in the data (no hallucinated
  ICD/LOINC), ascertains the diagnosis from notes via ai_query (negation- and
  subject-aware, span-grounded), SURFACES ambiguous clinical thresholds and how to
  combine coded vs note evidence (code_only/note_only/union/intersection) for the user
  to choose, reports feasibility N before building, materializes a verified cohort plus a
  reproducible phenotype definition, and never fabricates literature citations. Run by
  calling the vetted entrypoints in scripts/cohort_run.py — do not hand-write cohort SQL.
  For PHI de-identification of the result use hls-phi-deidentifier.
version: 1.0.0
author: Databricks HLS Field Engineering
license: Databricks License
---

# HLS Clinical Cohort Builder — Literature-Informed, Feasibility-Aware

## Overview

Turns an analyst's natural-language description of a patient population into a
**defensible, reproducible, feasibility-checked cohort** over structured clinical data
**and free-text clinical notes**. It grounds codes in what is actually in the data,
ascertains the diagnosis from note text when a notes source is supplied, surfaces
ambiguous thresholds and the code-vs-note combine choice for the user to decide, checks
feasibility before building, and emits a verified cohort table plus a machine-readable
phenotype definition. The output is a `<table>_cohort` of qualifying `patient_id`s, a
reproducible phenotype definition (codes + comparators + combine mode), and a verification
line confirming membership matches the definition exactly.

It runs on the **execution model**: Genie Code calls the vetted entrypoints in
`scripts/cohort_run.py` and reports their output — it does not hand-write cohort SQL and
does not pick a clinical threshold or a combine mode itself. Those are the user's choices,
surfaced by a read-only preview.

## When to Use

- "Build a cohort of type 2 diabetics with uncontrolled HbA1c on metformin."
- "How many patients would qualify for a heart-failure readmission study?" (feasibility N).
- "Define a sepsis cohort and check it against the literature."
- "Build the diabetes cohort using both the coded records and the clinical notes" (free-text).
- "Is this cohort feasible, or is N too small?" (attrition + minimum-N heuristics).
- "Refine the phenotype — the codes miss patients documented only in notes" (note recovery).

## Prerequisites

- **Compute**: a Databricks SQL warehouse (the entrypoints run SQL via the Databricks SDK;
  ambient auth in-workspace, or a CLI `profile=` locally).
- **Inputs**: a coded clinical table (`catalog.schema.table`, OMOP CDM or FHIR-flattened —
  conditions/labs/meds/procedures) with a `patient_id`. Optionally a free-text notes table
  (`patient_id`, `note_text`) to ascertain the diagnosis from narrative.
- **Model endpoint** (only for the notes path): a serving endpoint `ai_query` can call
  (defaults to a Foundation Model API pay-per-token endpoint,
  `databricks-meta-llama-3-3-70b-instruct`).
- **MCP (optional)**: a terminology MCP (e.g. BioPortal) to expand a concept into a code
  set; a literature MCP (PubMed / Europe PMC / ClinicalTrials.gov) for citation candidates.

## Quick Start

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
print(build_confirmed_cohort("<catalog.schema.table>",
                            intent_text="<same phrasing>",
                            condition_codes=[("ICD10CM","E11.9"), ("ICD10CM","E11.65")],
                            threshold_value=9.0, threshold_op=">="))   # e.g. user chose HEDIS
```

## Workflow

**⛔ EXECUTE, DO NOT REIMPLEMENT.** Call the two named entrypoints and report their output.
Do NOT write your own cohort SQL, and do NOT pick a threshold or combine mode yourself. The
two names make intent unmistakable to a permission reviewer: `preview_cohort_options` is
READ-ONLY (surfaces choices, builds nothing); `build_confirmed_cohort` requires the user's
chosen threshold. The steps below document what the entrypoints do internally — they are
for review, not a recipe to re-code by hand.

### Step 1: Ground the codes

The proposed `(vocabulary, code)` set — from a terminology MCP, clinical-notes parsing, or
the model — is checked against the actual table. Codes not present are excluded and reported,
so a bad source cannot inject a hallucinated code.

```python
preview_cohort_options(table, intent_text, condition_codes=[("ICD10CM","E11.9")],
                       code_source="BioPortal MCP")   # provenance recorded in the readout
```

### Step 2: (Optional) Ascertain the diagnosis from free-text notes

When a `notes_table` is supplied, `ai_query` runs over the notes with a **negation- and
subject-aware** prompt. A note-asserted diagnosis is kept only when the model returns a
verbatim span that is actually in the note (**span-grounding** — the notes analogue of
code-grounding), and the evidence is materialized to `<notes_table>_note_evidence` so the
phenotype is reproducible. See `references/freetext_notes.md`.

```python
preview_cohort_options(table, intent_text, condition_codes=[("ICD10CM","E11.9")],
                       notes_table="<catalog.schema.clinical_notes>",
                       note_col="note_text", note_condition="type 2 diabetes")
```

### Step 3: Surface the choices (threshold + combine), then STOP

For a term with more than one standard definition (e.g. "uncontrolled HbA1c" → >8.0% vs
≥9.0%) the preview returns BOTH options with the real cohort N for each. When notes are
present it also returns `code_only` / `note_only` / `union` / `intersection` sizes plus the
disagreement set (patients notes recovered that codes missed; coded patients with no note
assertion). **Present these to the user and get their choice — never pick for them.**

```text
1. >8.0% (common clinical 'uncontrolled') → cohort N = 84
2. >=9.0% (HEDIS 'poor control')          → cohort N = 68
code_only 84 | note_only 98 | union 118 | intersection 64  (notes recover 34)
```

### Step 4: Build + verify

After the user chooses, `build_confirmed_cohort` materializes the cohort and re-checks that
membership matches the definition exactly (anti-joins for 0 false positives / 0 false
negatives), then emits the reproducible phenotype definition JSON.

```python
build_confirmed_cohort(table, intent_text, condition_codes=[("ICD10CM","E11.9")],
                       notes_table="<...clinical_notes>", note_condition="type 2 diabetes",
                       combine_mode="union", threshold_value=8.0, threshold_op=">")
```

The cohort table carries a light, **non-PHI `ascertainment` column** (`code` | `note` | `both`)
so you can see which source placed each patient. When notes contribute, the build also
materializes a separate **provenance / "delta" table** `<cohort>_provenance`
(`patient_id, ascertainment, in_codes, note_asserts_dx, evidence_span, <measure>`) and prints
its **first 20 rows** — leading with the note-recovered and note-silent-coded cases so you can
audit *why* each patient qualified. Raw note text is **never** copied into the shareable cohort
table; the verbatim span lives only in the provenance table, governed like the notes source
(PHI). See Guardrails.

### Step 5: Literature (separate, verified — never fabricated; optional)

Citations are resolved through `scripts/literature.py`: PMIDs an agent retrieves from a
connected literature MCP are verified against PubMed (kept only if they resolve), with a
direct-PubMed floor that distills the phenotype from the intent and relevance-ranks results.
It fails closed — no verified source, no citation. Pass candidates via `mcp_citations=[...]`;
never state a PMID/NCT id the tool did not return verified. **Set `include_literature=False`
to skip this step entirely** for air-gapped workspaces with no PubMed/MCP egress (avoids the
network round-trip; the step already fails closed either way).

```markdown
| Table | N | Verified | Definition |
|-------|---|----------|------------|
| catalog.schema.cohort | 118 | 0 FP / 0 FN | {codes, comparators, combine_mode} |
```

## Key Parameters

`preview_cohort_options(table, intent_text, condition_codes, code_source="model-proposed", notes_table=None, note_col="note_text", note_id_col="patient_id", note_endpoint=..., note_condition=None, ...)`
`build_confirmed_cohort(table, intent_text, condition_codes, threshold_value, threshold_op=None, cohort_table=None, mcp_citations=None, notes_table=None, note_condition=None, combine_mode=None, ...)`

| Parameter | Default | Range / Options | Effect |
|-----------|---------|-----------------|--------|
| `table` | — (required) | `catalog.schema.table` | Coded clinical records (OMOP/FHIR-flattened). The spine — every patient (incl. note-only) has a row here for the measure column. |
| `intent_text` | — (required) | the user's phrasing | Scanned for ambiguous terms (e.g. "uncontrolled") that trigger the threshold-choice gate. |
| `condition_codes` | — (required) | `[(vocab, code)]` | Proposed concept set from any source; grounded against the data (absent codes excluded). |
| `code_source` | `"model-proposed"` | e.g. `"BioPortal MCP"` | Provenance recorded in the readout. Preview-only. |
| `threshold_value` | — (build) | numeric | The threshold the user chose after preview. Never pick this yourself. |
| `threshold_op` | `None` | `>`, `>=`, `<`, `<=`, `=` | Comparator — part of the user's choice. For an ambiguous term the tool recovers it from the chosen option; it never silently assumes `>`. |
| `notes_table` | `None` | `catalog.schema.table` | Free-text notes source; when set, the diagnosis is also ascertained from note text and the combine choice is surfaced. |
| `note_condition` | `None` (→ `intent_text`) | e.g. `"type 2 diabetes"` | What the note extractor looks for — the diagnosis, not the whole phenotype. |
| `note_endpoint` | `databricks-meta-llama-3-3-70b-instruct` | any serving endpoint | The model `ai_query` calls to read the notes. Override to point at a provisioned-throughput or fine-tuned clinical model. |
| `note_prompt` | `None` (built-in template) | a prompt string | Override the extraction prompt. If it contains `{condition}` it's formatted with the condition, else used verbatim. Must still reply `YES:<verbatim span>` / `NO` for span-grounding. The resolved prompt is pinned in the definition. |
| `note_prefilter` | `None` (scan all notes) | list of keywords, or a raw SQL predicate | **Scale lever.** Restricts which notes get `ai_query`'d — only notes matching the keywords (case-insensitive LIKE-ANY) are scanned. Recall-safe: a note that mentions none of the concept's terms/synonyms cannot assert it, so excluding it loses no true positives (include abbreviations). Cuts LLM calls 10–100× on a large corpus; leave off for small/demo tables. |
| `combine_mode` | `None` | `code_only`/`note_only`/`union`/`intersection` | The user's choice for combining coded + note-derived diagnoses. REQUIRED for build once `notes_table` is given; never guessed. |
| `include_literature` | `True` | `True`/`False` | Set `False` to skip the PubMed/MCP citation step (air-gapped workspaces). |
| `mcp_citations` | `None` | `[PMID, ...]` | Candidate PMIDs retrieved from a literature MCP; verified (kept only if they resolve). |

Feasibility thresholds (engine defaults, not arguments): warn when eligible **N < 100**,
hard-warn when **N < 20**. The preview reports N before anything is built.

### Configuring the notes extractor

The LLM **endpoint** and **prompt** are plain function parameters (`note_endpoint`,
`note_prompt`), with the defaults as clearly-named module constants at the top of
`scripts/cohort_run.py` (`DEFAULT_NOTE_ENDPOINT`, `_NOTE_EXTRACT_PROMPT`). Change them per call
without touching code, or edit the constants to change the default. This is deliberately *not*
a YAML/config-file layer — a Genie Code skill is invoked by function call, so overridable params
plus a documented default are the discoverable, single-source-of-truth pattern.

## Expected Outputs

- A **cohort table** (`<table>_cohort`) of qualifying `patient_id`s + a non-PHI `ascertainment`
  column (`code` | `note` | `both`).
- When notes contribute, a **provenance / "delta" table** (`<cohort>_provenance`) with per-member
  source + the verbatim note span, and a 20-row preview in the readout. (Governed like the notes
  source — the shareable cohort table stays free of raw note text.)
- A **machine-readable phenotype definition** (codes + comparators + combine mode + pinned
  note-extraction prompt/endpoint) stored with it — reproducible and auditable, not just a list.
- A **verification line** confirming membership matches the definition exactly (0 FP / 0 FN).
- **Verified citations**, or an honest "no citation — none fabricated" when none resolve.
- A clean hand-off: Genie Code *builds* the cohort; a Genie *Space* explores it in NL.

## Evaluation

Measured **skill vs no-skill** (Genie Code baseline) against seeded synthetic gold, so scores
are exact. Objective = `0.45·membership_F1 + 0.20·conceptset_F1 + 0.20·feasibility + 0.15·citation − 0.50·hallucination`.

| Task | Metric | No skill (baseline) | Skill |
|------|--------|---------------------|-------|
| Coded cohort | Membership F1 | 0.911 (silent stricter threshold; fabricated citations) | **1.000** |
| Free-text cohort (union) | Membership F1 (live) | 0.620 (silently chose ≥9.0 + intersection; recall 0.449) | **1.000** |
| Free-text cohort | Note-trap specificity | 0.44 (negation/family-history mentions leak in) | **1.00** (0 leaked) |
| Free-text cohort | Composite objective | 0.573 | **1.000** |

Root cause the skill removes: the un-guided baseline **silently makes definitional choices**
(threshold, code/note combine) the analyst never sees. Reproduce with `eval/mlflow_eval.py`
(scenarios `cohort-baseline/skill`, `cohort-freetext-baseline/skill`), which logs each arm to an
MLflow experiment. Unit tests: `tests/` (component scorers incl. `note_trap_specificity`); the
repo's `tests/test_skill_quality.py` validates this SKILL.md. See the eval harness in the source
repo for the full A/B protocol and the live Genie-Code capture.

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Preview returns fewer codes than requested | Some proposed codes aren't in the data (grounding excluded them) | Expected — the readout lists which were dropped. Use a hierarchy-expanded concept set for descendants. |
| It refuses to build and returns a choice prompt | Ambiguous threshold and/or a notes source with no `combine_mode` | The confirm-gate working. Show the options + N to the user, get their choice, call `build_confirmed_cohort`. |
| A harmless preview is blocked by a permission reviewer | Overloaded `run_cohort(...)` where preview vs build differ only by an argument | Call the explicitly-named `preview_cohort_options` (read-only, no threshold arg). |
| No citations attached | No literature MCP connected and/or PubMed unreachable | Correct fail-closed behavior — never fabricate a PMID. You may still name a guideline (ADA/HEDIS) in prose. |
| Note evidence looks too small/large | `note_condition` too broad/narrow, or the endpoint under/over-calls | Set `note_condition` to the diagnosis (not the phenotype); inspect `<notes_table>_note_evidence` (span-grounded verdicts). |
| Cohort N far smaller than expected | A stricter threshold or missing OR-criteria | Re-check the threshold choice and whether criteria should be OR-combined. |

## Guardrails

1. **Execute, do not reimplement** — call the entrypoints; never hand-write cohort SQL. The
   baseline silently substituted a stricter HbA1c threshold and fabricated citations; this
   path prevents both.
2. **Never pick a threshold or combine mode for the user** — surface options with N impact
   and let them choose (both the value AND the operator; both parts of the choice).
3. **Reproducibility over convenience** — always emit the coded phenotype definition, never
   just a patient-id list.
4. **Never fabricate a citation** — state only PMIDs/NCT ids the resolver returned verified;
   naming a guideline (ADA/HEDIS) in prose is fine, asserting an unverified resolvable id is not.
5. **Feasibility gate is not optional** — never hand over a cohort without reporting N and
   per-criterion attrition.
6. **Respect PHI governance** — the cohort inherits UC access controls; if the source is raw
   PHI and the consumer is an analyst, run `hls-phi-deidentifier` on the output or build on a
   de-identified source.
7. **Keep raw notes out of the shareable cohort table** — verbatim note spans (PHI) live only in
   the separate `<cohort>_provenance` table, governed like the notes source; the cohort table
   carries just `patient_id` + the non-PHI `ascertainment` column.

## Bundled Resources

- `scripts/cohort_run.py` — the entrypoints: `preview_cohort_options` (read-only grounding +
  threshold/combine surfacing) and `build_confirmed_cohort` (materialize + verify). Contains
  `extract_note_evidence` (ai_query, negation-/subject-aware, span-grounded).
- `scripts/literature.py` — citation resolver: MCP-verify + direct-PubMed floor, fail-closed.
- `references/ontology_crosswalks.md` — SNOMED/ICD-10/RxNorm/LOINC + OMOP concept-set guidance.
- `references/phenotype_standards.md` — PheKB/eMERGE/OHDSI conventions + minimum-N heuristics.
- `references/mcp_literature_servers.md` — discovering & calling literature/terminology MCP servers.
- `references/freetext_notes.md` — the ai_query note-extraction prompt, negation/subject rules,
  span-grounding, combine modes, and cost notes.
- `tests/scorers.py`, `tests/objective.py`, `tests/test_scorers.py` — the objective function,
  component scorers (membership F1, concept-set F1, feasibility, citation validity, note-trap
  specificity), and their pure-Python unit tests.

## References

- [PheKB](https://phekb.org) — validated electronic phenotype algorithms.
- [OHDSI / ATLAS](https://www.ohdsi.org/software-tools/) — OMOP concept-set + cohort-definition standard.
- [NCQA HEDIS — Comprehensive Diabetes Care (NQF #0059)](https://www.ncqa.org/hedis/) — "poor HbA1c control" ≥ 9.0%.
- [ADA Standards of Care in Diabetes](https://diabetesjournals.org/care) — glycemic targets.
- [Databricks AI Functions — `ai_query`](https://docs.databricks.com/en/large-language-models/ai-functions.html) — LLM inference from SQL.
