# Free-Text Clinical Notes — Diagnosis Ascertainment via Databricks AI Functions

How the skill turns unstructured clinical notes into a **grounded, reproducible** diagnosis
signal, and how that signal combines with coded criteria. The mechanics live in
`scripts/cohort_run.py` (`extract_note_evidence`, `_dx_predicate`); this file documents the
method for review — it is NOT a recipe to re-code by hand.

## Why notes, and why this is not "just run an LLM over notes"

A large share of clinical truth is documented only in narrative text — a diagnosis stated in
an assessment, a severity that never made it to a coded field, a condition the billing codes
missed entirely. Pulling patients from notes naively (a `LIKE '%diabetes%'`) fails two ways at
once, and both are measured in the eval:

1. **Precision collapse from context blindness.** "No evidence of diabetes" and "mother has
   type 2 diabetes" both contain the word — a keyword match wrongly enrolls the negated case
   and the family-history case. These are the classic clinical-NLP failure modes (negation and
   subject/experiencer), and they are exactly the traps the eval seeds.
2. **Recall loss + no reconciliation.** Keyword matching misses paraphrase and abbreviation,
   and says nothing about how note evidence should relate to the coded record.

So the skill does three things a naive approach does not: it reads notes with a
**negation-/subject-aware** extractor, it **span-grounds** every positive (fail-closed against
fabricated evidence), and it **surfaces the code-vs-note combine choice** instead of guessing.

## The extraction — `ai_query` over the notes

Databricks AI Functions (`ai_query`, GA) call a serving endpoint from SQL, row by row, so the
extraction runs where the data lives (no egress of PHI). The default endpoint is a Foundation
Model API pay-per-token model (`databricks-meta-llama-3-3-70b-instruct`); override with
`note_endpoint` (a provisioned-throughput or fine-tuned clinical endpoint for scale/cost).

The pinned prompt (stored in the phenotype definition for reproducibility):

> You are a clinical NLP extractor. Decide whether the note below ASSERTS that THIS patient
> CURRENTLY has {condition}. Answer NO if the mention is negated ("no evidence of", "denies",
> "ruled out", "without"), is family history only ("mother", "father", "sibling", "family
> history"), or is only a screening/risk statement. If YES, reply exactly 'YES:' followed by
> the SHORTEST verbatim quote from the note that documents it. If NO, reply exactly 'NO'.

`{condition}` is the `note_condition` argument (keep it the **diagnosis** — e.g. "type 2
diabetes" — not the whole phenotype; the numeric threshold is applied separately downstream).

## Span-grounding — the notes analogue of code-grounding

Coded criteria are grounded by checking the code is actually present in the data. Note evidence
is grounded the same way, one level up: a positive is kept **only if** the model returned a
verbatim quote AND that quote is actually a substring of the note
(`contains(lower(note_text), lower(evidence_span))`). A hallucinated "YES" with no real
supporting span is dropped. This makes note evidence auditable — every enrolled note-only
patient has a quotable reason — and makes fabrication fail closed, the same guarantee the
citation resolver gives.

The result is materialized to `<notes_table>_note_evidence` (`patient_id`, `verdict`,
`evidence_span`, `asserts_current_dx`) so the cohort is reproducible from the definition, not a
re-run of a stochastic call.

## Combining coded and note-derived diagnoses — a USER choice

Once both signals exist, "who has the diagnosis?" has four defensible answers. The preview
reports the real N for each and the disagreement set, and stops:

| combine_mode | Diagnosis predicate | Use when |
|---|---|---|
| `code_only` | coded dx present | you trust structured coding; notes are noise |
| `note_only` | note asserts current dx | coding is sparse/unreliable; notes are the source of truth |
| `union` | code **OR** note | maximize recall — recover patients the codes missed (RWE, screening) |
| `intersection` | code **AND** note | maximize precision — chart-confirmed cohort (trial screening, adjudication) |

`build_confirmed_cohort` **requires** `combine_mode` once `notes_table` is given — the skill
never picks it, exactly as it never picks a threshold. The measure criterion (e.g. HbA1c > 8.0)
is then applied on top of the chosen diagnosis set.

## Cost & scale notes

- One `ai_query` call per note row. For large corpora, filter first (only notes for a
  candidate population), use a provisioned-throughput endpoint, and/or cache the evidence
  table and re-use it across cohort definitions (it depends only on `note_condition`, not the
  threshold or combine mode).
- The evidence table is safe to drop and rebuild; it carries no state beyond the extraction.
- Keep PHI governance intact: the evidence table inherits UC access controls and should live in
  the same governed schema as the notes; recommend de-identified notes for analyst consumers.

## What is deliberately still out of scope

- **OCR / scanned documents and image/waveform modalities.** `ai_query` reads text; if the
  signal is only in a scan or an image, say so and stop.
- **Mapping note evidence to specific ICD/LOINC codes.** The notes path ascertains the
  *diagnosis* (a patient-level assertion), not a coded concept — it deliberately does not invent
  codes. If a coded concept set is needed, use a terminology MCP on the extracted term.
