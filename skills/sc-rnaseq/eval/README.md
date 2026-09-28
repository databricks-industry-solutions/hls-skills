# Evaluation — sc-rnaseq Skill

## Overview

Evaluates the `sc-rnaseq` skill (single-cell RNA-seq analysis on Databricks)
against 4 benchmark tasks covering: single-sample QC + clustering, Ensembl ID
handling, `.raw` fallback for reprocessing, and multi-sample integration with
batch correction.

**Skill under test**: `/Users/yen.low@databricks.com/.assistant/skills/hls-skills/skills/sc-rnaseq/SKILL.md`

## Benchmark Tasks

| task_id | difficulty | Description | Key skill behaviour tested |
|---------|-----------|-------------|---------------------------|
| scrna-001 | easy | Single-sample scanpy QC + UMAP + Leiden | MLflow tracking (G5), data-driven QC (G2), inline plots, markdown narration |
| scrna-002 | hard | Ensembl ID gene name handling (scanpy) | Detect ENSG var_names, swap to symbols before QC (prevents all-zero pct_mt) |
| scrna-003 | hard | rapids-singlecell GPU pipeline | RMM setup, anndata_to_GPU, sc.pp.neighbors from scanpy (not rsc), rsc.tl.leiden/umap |
| scrna-004 | hard | Multi-sample integration | Per-sample QC profiling (G1/G3), batch key selection (G1), harmony integration |

## Scorer Summary

### Level 1 — Deterministic (@scorer)

| Scorer | What it checks |
|--------|----------------|
| `artifact_produced` | Session produced output (notebook ran to completion) |
| `mlflow_setup` | MLflow tracking was set up (Gate G5, default ON) |
| `data_driven_qc` | QC thresholds were MAD/percentile-based, not static defaults (Gate G2) |
| `no_forbidden_content` | No forbidden patterns (e.g., `pct_counts_mt < 20`) in output |
| `inline_plots` | `%matplotlib inline` added after restartPython() |
| `markdown_narration` | Markdown cells explaining decisions were included |
| `required_artifacts_present` | All task-specific required artifacts mentioned in output |

### Level 2 — LLM Judges (make_judge, binary yes/no)

| Judge | What it evaluates |
|-------|--------------------|
| `Correctness` | Built-in scorer: checks expected_facts against response |
| `task_completion` | Did the session complete the task correctly? |
| `tool_use_quality` | Were the right tools/steps used in the right order? |

**Judge model**: `databricks:/databricks-gpt-5-mini` (must differ from generator)

## Ship Gate

- **Pass rule**: `all_metrics` — task passes iff all metrics pass
- **Ship threshold**: `win_rate > 0` AND zero regressions
- **Difficulty**: checked via `--difficulty expectations.json`
- Any regression at any difficulty blocks the gate

## Run Protocol

### Prerequisites

1. `mlflow[databricks] >= 3.5.0` installed
2. UC Volume for data: `/Volumes/hls_amer_catalog/vital_skills/eval/sc_rnaseq/` (or set `SKILL_EVAL_DATA_DIR`)
3. The sc-rnaseq skill installed in `.assistant/skills/`

### Step 1: Generate Data

Run `generate_data.py` in a Databricks notebook cell (needs pertpy + scanpy):

```python
import sys
sys.path.insert(0, "/Workspace/Users/yen.low@databricks.com/.assistant/skills/hls-skills/skills/sc-rnaseq/eval")
exec(open("/Workspace/Users/yen.low@databricks.com/.assistant/skills/hls-skills/skills/sc-rnaseq/eval/generate_data.py").read())
```

This creates 5 h5ad files in the volume:
- `sample_symbols.h5ad` — gene symbols, raw counts
- `sample_ensembl.h5ad` — Ensembl IDs as var_names, symbols in `var['feature_name']`
- `sample_processed.h5ad` — normalized in `.X`, raw counts in `.raw` (legacy, unused by current tasks)
- `donor1.h5ad` / `donor2.h5ad` — multi-sample subsets

### Step 2: Run Baseline Sessions (Skill OFF)

1. Move/disable the sc-rnaseq skill (rename or move the folder out of `.assistant/skills/`)
2. For each task: open a **fresh** Genie Code chat, paste the query from `evalset.json` verbatim
3. Let the session complete (respond to any agent questions naturally — do NOT steer)
4. Save outputs: capture the notebook link and record the `response`, `action_log`, and `result_table` for each task
5. Fill in `no_skills_outputs` in the scoring notebook

### Step 3: Run Candidate Sessions (Skill ON)

1. Reinstall the sc-rnaseq skill (copy `SKILL.md` + `references/` only — NOT the `eval/` folder)
2. Hard-refresh, repeat identical queries in fresh chats
3. Save outputs the same way
4. Fill in `with_skills_outputs` in the scoring notebook

### Step 4: Score

Run the scoring notebook `score_sc_rnaseq.py`:
1. Fill in `no_skills_outputs` and `with_skills_outputs` dicts (Cells 6-7)
2. Run all cells in order
3. Check the paired comparison report (Cell 11 output)
4. Score JSONs saved to `baseline_scores.json` and `with_skill_scores.json`

### Step 5: Error Analysis + Report

1. Read every task that ended `tie-fail` or `regression`
2. Open-code the first observed failure per trace
3. Group into a failure taxonomy
4. Write `eval_report.md` using `references/report-template.md`

## Guardrails

- Fresh Genie Code chat per task per arm; verbatim queries; no steering differences
- Judge model must differ from generator model
- Do NOT read `expectations.json` or `generate_data.py` when running task sessions (answer key isolation)
- Keep `eval/` out of the installed skill tree in both arms
- Small sample (4 tasks) = directional evidence, not statistical

## File Layout

```
sc-rnaseq/eval/
├── README.md              ← this file
├── evalset.json            ← 4 task definitions (task_id, dataset, query)
├── expectations.json       ← difficulty, expected_facts, deterministic_checks
├── generate_data.py        ← creates h5ad variants on UC Volume
├── scorers.py              ← deterministic + LLM judge scorers; exports `scorers` list
├── score_sc_rnaseq.py      ← scoring notebook: evaluate + compare + report
├── baseline_scores.json    ← (after running) skill-OFF per-task scores
├── with_skill_scores.json  ← (after running) skill-ON per-task scores
└── eval_report.md         ← (after running) paired comparison report + failure taxonomy
```

## Reproduce

```bash
# After data generation and both arms:
python3 skills/skill-eval/scripts/compare_runs.py \
    baseline_scores.json with_skill_scores.json \
    --difficulty expectations.json --strict
```