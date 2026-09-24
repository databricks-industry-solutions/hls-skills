# rwe-cohortstudy Skill Evaluation

## Overview

Benchmark evaluation for the `rwe-cohortstudy` skill following the
[skill-eval](../../skill-eval/SKILL.md) methodology. Tests whether the skill
helps Genie Code produce correct real-world evidence (RWE) comparative
effectiveness analyses.

## Benchmark Tasks

| task_id | difficulty | task | dataset | discriminator |
|---------|-----------|------|---------|---------------|
| rwe-001 | easy | PS matching + balance diagnostics | rwe_cohort.csv | Correct logit-PS matching + SMD balance table |
| rwe-002 | hard | Full pipeline: PS → stabilized IPW → balance → doubly robust → E-value | rwe_cohort.csv | DR estimator combines PS + outcome model; E-value formula correct |
| rwe-003 | hard | Weighted Cox PH + robust SE + PH test + RMST | rwe_survival.csv | Weighted (not unweighted) Cox; Schoenfeld test; RMST as AUC |
| rwe-004 | edge | Target trial emulation: cloning + censoring + IPW | rwe_tte.csv | Cloning all patients under both strategies; censoring weights |

Tasks 2-4 are discriminators: the naive no-skill approach will likely skip
confounding adjustment (reporting wrong effect direction), use unweighted Cox,
or fail to implement cloning/censoring for target trial emulation.

## Data

Synthetic datasets with built-in confounding by indication:
- Sicker patients are more likely to receive treatment
- Treatment has a true protective effect (OR ~0.65)
- Without PS adjustment, treatment appears harmful

Volume: `/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy/`

Override: `RWE_EVAL_DATA_DIR` env var.

## Scorer Summary

| scorer | level | type | checks |
|--------|-------|------|-------|
| artifact_produced | L1 | deterministic | Primary artifact exists in outputs |
| no_forbidden_content | L1 | deterministic | No forbidden patterns in response |
| methodology_keywords | L1 | deterministic | Response mentions >=2 RWE method terms |
| balance_reported | L1 | deterministic | SMD / balance table / love plot mentioned |
| task_completion | L2 | LLM judge | Method soundness, confounding addressed, correct estimators |
| tool_use_quality | L2 | LLM judge | Process quality: correct step order, correct libraries |

Judge model: `databricks:/databricks-gpt-5-mini` (must differ from generator).
Pass rule: `all_metrics` (task passes iff all scorers pass).

## Ship Gate

- Default gate: `win_rate > 0` AND `zero regressions` at any difficulty
- Regression re-run: `--gate no-regressions` (clean tie passes)
- Any regression at any difficulty blocks the gate

## Run Protocol

### 1. Seed the data volume

```bash
python3 skills/rwe-cohortstudy/eval/generate_data.py
```

### 2. Baseline sessions (skill OFF)

1. Move the skill out of `.assistant/skills/` (or rename the folder)
2. Hard-refresh Genie Code
3. For each task in `evalset.json`: open a **fresh** chat, paste the query
   verbatim, let it finish, save the output
4. Record: notebook link, result table, action log (ordered steps taken)

### 3. Candidate sessions (skill ON)

1. Reinstall the skill under `.assistant/skills/rwe-cohortstudy/`
2. Hard-refresh Genie Code
3. Same tasks, fresh chats, verbatim queries, save outputs identically
4. Do not re-prompt or steer differently than baseline

### 4. Score both arms

```python
import mlflow
from scorers import scorers

mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Users/<you>/skill-eval-rwe-cohortstudy")

# Assemble rows: {"inputs": {...}, "outputs": {...}, "expectations": {...}}
# See skill-eval/references/paired-comparison.md for extraction recipe

baseline_result = mlflow.genai.evaluate(data=rows_baseline, scorers=scorers)
with_skill_result = mlflow.genai.evaluate(data=rows_with_skill, scorers=scorers)

# Extract per-task scores (see paired-comparison.md)
# Save to baseline_scores.json and with_skill_scores.json
```

### 5. Paired comparison

```bash
python3 skills/skill-eval/scripts/compare_runs.py \
    skills/rwe-cohortstudy/eval/baseline_scores.json \
    skills/rwe-cohortstudy/eval/with_skill_scores.json \
    --difficulty skills/rwe-cohortstudy/eval/expectations.json --strict
```

### 6. Error analysis and report

- Read every `tie-fail` or `regression` task in both arms
- Open-code the first failure per trace, group into a failure taxonomy
- See `skill-eval/references/error-analysis.md`
- Write the Evaluation section into `rwe-cohortstudy/SKILL.md`
  using `skill-eval/references/report-template.md`

## Files

```text
eval/
├── README.md            ← this file
├── evalset.json         ← 4 benchmark task definitions (task_id, dataset, query)
├── expectations.json    ← difficulty, expectations, deterministic_checks per task
├── generate_data.py     ← synthetic data generator
└── scorers.py           ← deterministic + LLM judge scorers
```

After running, add:
```text
eval/
├── baseline_scores.json    ← skill-OFF per-task scores
└── with_skill_scores.json  ← skill-ON per-task scores
```

## Reproduce

```bash
# 1. Seed data
python3 skills/rwe-cohortstudy/eval/generate_data.py

# 2. Run sessions (manual, per protocol above)
# 3. Score and compare
python3 skills/skill-eval/scripts/compare_runs.py \
    skills/rwe-cohortstudy/eval/baseline_scores.json \
    skills/rwe-cohortstudy/eval/with_skill_scores.json \
    --difficulty skills/rwe-cohortstudy/eval/expectations.json --strict
```
