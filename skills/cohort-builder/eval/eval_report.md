# Evaluation Report — cohort-builder Skill

**Setup**: Two paths evaluated, both run live in Genie Code on `fevm-testing-playground`
(2026-10-22). Every metric is measured **directly from the materialized cohort tables** against
seeded synthetic ground truth we own (known membership + fixed concept set), via the skill's
`eval/objective.py` (`cohort_objective`):
`0.45·membership_F1 + 0.20·conceptset_F1 + 0.20·feasibility + 0.15·citation − 0.50·hallucination`.

- **Structured path** (coded criteria): build a cohort of **uncontrolled type 2 diabetes** — a
  T2D diagnosis AND most recent HbA1c > 8.0 — from `genie_science_eval.multi_condition_patients`
  (5,000 patients, one row per patient-condition). The discriminator is **concept-set expansion**:
  the full T2D set is `{E11.9, E11.65}`; a naive single-code approach (`E11.9` only) misses the
  248 patients who are E11.65-only.
- **Free-text notes path** (`ai_query`): from `genie_science_eval.clinical_docs_parsed`
  (patient_id, note_text), include patients whose note **asserts their own current T2D**, excluding
  family-history and ruled-out/negated mentions. The discriminator is **negation/subject
  awareness**: all three note archetypes contain the string "diabetes", so a naive
  `LIKE '%diabet%'` leaks every trap.

## Results — structured path (5 fresh Genie sessions)

| run | gold N | predicted N | membership P | R | F1 | E11.65-only captured | conceptset F1 | feasibility | objective |
|-----|--------|-------------|--------------|---|----|----------------------|---------------|-------------|-----------|
| run1 | 952 | 952 | 1.000 | 1.000 | 1.000 | 248/248 | 1.000 | 1.000 | 1.0 |
| run2 | 952 | 952 | 1.000 | 1.000 | 1.000 | 248/248 | 1.000 | 1.000 | 1.0 |
| run3 | 952 | 952 | 1.000 | 1.000 | 1.000 | 248/248 | 1.000 | 1.000 | 1.0 |
| run4 | 952 | 952 | 1.000 | 1.000 | 1.000 | 248/248 | 1.000 | 1.000 | 1.0 |
| run5 | 952 | 952 | 1.000 | 1.000 | 1.000 | 248/248 | 1.000 | 1.000 | 1.0 |
| **aggregate** | 952 | 952 | **1.000** | **1.000** | **1.000** | **248/248** | **1.000** | **1.000** | **1.0** |

- Perfect membership every run. The skill expanded the T2D concept to **both** `E11.9` and
  `E11.65`, capturing all 248 E11.65-only members a single-code query would miss (that naive query
  caps at recall ≈ 0.74, F1 ≈ 0.85).
- Fully reproducible across 5 independent sessions.

## Results — free-text notes path (5 fresh Genie sessions)

Gold: `assert` = 40 (note asserts current T2D → include); traps = `family` 16 + `ruledout` 14 = 30
(must be excluded); 121-patient note population.

| run | predicted N | membership P | R | F1 | trap specificity | traps leaked | objective |
|-----|-------------|--------------|---|----|------------------|--------------|-----------|
| run1 | 41 | 0.976 | 1.000 | 0.988 | 1.000 | 0/30 | 0.9894 |
| run2 | 41 | 0.976 | 1.000 | 0.988 | 1.000 | 0/30 | 0.9894 |
| run3 | 41 | 0.976 | 1.000 | 0.988 | 1.000 | 0/30 | 0.9894 |
| run4 | 41 | 0.976 | 1.000 | 0.988 | 1.000 | 0/30 | 0.9894 |
| run5 | 41 | 0.976 | 1.000 | 0.988 | 1.000 | 0/30 | 0.9894 |
| **aggregate** | 41 | **0.976** | **1.000** | **0.988** | **1.000** | **0/30** | **0.9894** |
| *naive `LIKE` baseline* | 70 | 0.571 | 1.000 | 0.727 | 0.000 | 30/30 | — |

- The skill's `ai_query` path caught all 40 asserted-current-T2D patients and **excluded every one
  of the 30 negation / family-history traps** (trap specificity 1.000). One benign false positive
  (a non-trap note) → precision 0.976.
- The naive keyword baseline recalls everything but **leaks all 30 traps** (precision 0.571,
  specificity 0.000) — the exact failure the free-text path is built to prevent.
- Consistent across all 5 sessions despite the per-note LLM classification.

## Verdict

**ship** — Structured: perfect, reproducible membership with correct ICD-10 concept-set expansion
(objective 1.0). Free-text notes: F1 0.988 with zero trap leakage versus a keyword baseline that
leaks every trap (objective 0.9894). Both paths clear the membership-F1 headline and the
concept-set / negation-awareness discriminators that separate the skill from a no-skill approach.

## Limitations

- Synthetic, seeded data — exact ground truth, but limited archetype variety (one condition family
  for the structured measure threshold; one note trap taxonomy).
- The notes path's single false positive is a non-trap note mis-included; it does not touch the
  negation/family-history traps that matter clinically.
- Citation validity / hallucination terms are inert here (no literature citations requested); they
  are exercised in the literature-augmented phenotype scenarios, not these two tasks.

## Reproduce

- Component scorers / objective: `eval/scorers.py`, `eval/objective.py`
  (smoke test: `python3 eval/objective.py`).
- Structured scorer:
  `DATABRICKS_CONFIG_PROFILE=<p> python3 -I eval/score_cohort_struct.py --base <catalog.schema.multi_condition_patients> --out <catalog.schema.cohort>`
- Free-text notes scorer (also prints the naive-LIKE baseline contrast):
  `DATABRICKS_CONFIG_PROFILE=<p> python3 -I eval/score_cohort_notes.py --out <catalog.schema.cohort>`
- Runs (this report): `genie_science_eval.cohort_struct_skillrun1..5` and
  `genie_science_eval.cohort_notes_skillrun1..5`, `fevm-testing-playground`.
