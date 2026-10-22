# cohort-builder Skill Evaluation

## Overview

Benchmark evaluation for the `cohort-builder` skill following the
[skill-eval](../../skill-eval/SKILL.md) methodology. Tests whether the skill helps Genie Code
select the **right patients** — with the right codes and correct handling of free-text evidence —
across coded (structured) criteria and clinical-notes (`ai_query`) criteria.

## Benchmark Tasks

| task_id | path | difficulty | task | dataset | discriminator |
|---------|------|-----------|------|---------|---------------|
| cohort-struct-01 | structured | core | Uncontrolled T2D: T2D dx + HbA1c > 8.0, full concept set | `multi_condition_patients` (5,000) | Expand T2D to `{E11.9, E11.65}` — a single-code query misses 248 E11.65-only patients |
| cohort-notes-01 | free-text (`ai_query`) | hard | Include patients whose note asserts their own current T2D; exclude family-history and ruled-out mentions | `clinical_docs_parsed` (121) | Negation/subject awareness — a naive `LIKE '%diabet%'` leaks all 30 traps |

Both are discriminators against a no-skill baseline: the naive structured query under-captures by
using one code; the naive keyword query over-captures by leaking negated and family-history
mentions.

## Data

Seeded synthetic data with known membership:
- **Structured**: `testing_playground_catalog.genie_science_eval.multi_condition_patients` — 5,000
  patients across several conditions/measures; gold "uncontrolled T2D" = 952 patients
  (E11.9-only 704, E11.65-only 248 after dedup).
- **Free-text**: `clinical_docs_parsed` note text with labeled archetypes in `clinical_docs_gold`
  — `assert` 40 (true current T2D), `family` 16 + `ruledout` 14 = 30 traps.

## Scoring

`eval/objective.py` (`cohort_objective`):
`0.45·membership_F1 + 0.20·conceptset_F1 + 0.20·feasibility + 0.15·citation − 0.50·hallucination`.
Components in `eval/scorers.py` (incl. `note_trap_specificity` for the free-text path). Structured
runs scored with `eval/score_cohort_struct.py`; notes runs with `eval/score_cohort_notes.py`
(which also prints the naive-`LIKE` baseline for contrast).

## Results

See [eval_report.md](eval_report.md). Headline: structured membership F1 **1.000** (all 248
E11.65-only members captured), objective 1.0; free-text F1 **0.988** with trap specificity 1.000
(0/30 traps leaked) versus a naive baseline at F1 0.727 that leaks all 30 traps.
