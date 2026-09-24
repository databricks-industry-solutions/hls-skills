---
name: skill-eval
description: Skill benchmarking for Genie Code agent skills. Benchmark tasks (3-5) -> paired runs with and without the skill -> MLflow 3 genai.evaluate scoring (deterministic scorers + binary LLM judges) -> per-task win/loss/flip comparison -> failure-taxonomy error analysis -> standardized Evaluation report. For authoring a skill itself, use templates/SKILL_TEMPLATE.md; for general MLflow scorer API depth, see the Databricks MLflow 3 GenAI docs.
version: 1.0.0
author: hls-skills contributors
license: Databricks License
---

# Skill Eval

## Overview

Standardized method to prove a Genie Code skill works: run the same benchmark tasks with the skill OFF and ON, score both runs in one MLflow experiment, and compare per-task. The output is a ship/no-ship Evaluation section for the skill's SKILL.md, backed by a failure taxonomy — not vibes. This codifies the repo requirement (AGENTS.md step 5: report performance with and without the skill) into a repeatable pipeline.

## When to Use

- Validating a new skill before opening a PR (repo requires 3-5 benchmark tasks)
- Reviewing someone else's skill PR and needing objective evidence it helps
- Regression-checking an existing skill after an edit to SKILL.md or references/
- Deciding between two variants of a skill (prompt A vs prompt B)
- Building the failure taxonomy that tells you what to fix next in a skill
- Preparing MVP/release sign-off where "the skill helps" must be demonstrated, not asserted

## Prerequisites

- **MCP / tools**: Databricks workspace with Genie Code; `databricks` CLI profile for the target workspace
- **Python**: `pip install "mlflow[databricks]>=3.5.0"` (evaluation only; no Spark needed when using list-of-dicts datasets). 3.5.0 is a conservative floor: `make_judge(feedback_value_type=...)` and `mlflow.search_traces(locations=...)` are both later than 3.1, and I did not pin down the exact release that introduced each. Re-verify against the version you run
- **Inputs**: the skill under test installed in Genie Code (`Workspace/.assistant/skills/<name>/SKILL.md` or user-level `~/.assistant/skills/`)
- **Environment**: an MLflow experiment path you can write to, e.g. `/Users/<you>/skill-eval-<skill-name>`

## File Layout Convention

Evaluation artifacts live **in the evaluated skill's own `eval/` subfolder**, not in `skill-eval/assets/`. This keeps each skill self-contained and co-locates the evidence with the code it validates.

```text
skills/<skill-name>/
├── SKILL.md               ← the skill itself (not modified during eval)
└── eval/
    ├── README.md            ← run protocol, scorer summary, ship gate
    ├── evalset.json         ← 3-5 benchmark task definitions (task_id, dataset, query only)
    ├── expectations.json    ← difficulty, expectations, deterministic_checks per task (keyed by task_id + dataset)
    ├── generate_data.py     ← synthetic data generator (seeds the volume)
    ├── scorers.py           ← deterministic + LLM judge definitions; exports the `scorers` list
    ├── score_<skill>.ipynb  ← (generated) scoring notebook: evaluate + compare + report
    ├── eval_report.md       ← (after running) paired comparison report + failure taxonomy
    ├── baseline_scores.json ← (after running) skill-OFF per-task scores
    └── with_skill_scores.json ← (after running) skill-ON per-task scores
```

**Shared tooling** (comparison script, reference docs) stays in `skill-eval/` and is referenced by relative path.

### Data Volume Convention

Synthetic datasets for benchmark tasks are stored in a Unity Catalog volume, separate from workspace files. The default path is:

```
/Volumes/<catalog>/<schema>/eval/<skill_name>/
```

`generate_data.py` should read the output path from the `SKILL_EVAL_DATA_DIR` environment variable, falling back to an `OUT_DIR` constant. Update the volume paths in `evalset.json` to match. The human evaluator (or the skill author) runs `generate_data.py` before either arm; the agent executing tasks never reads it (Guardrail 8).

## Quick Start

```text
# 1. Write 3-5 benchmark tasks in two files:
#    skills/<skill>/eval/evalset.json       — task_id, dataset, query (the prompt pasted into Genie Code)
#    skills/<skill>/eval/expectations.json  — task_id, dataset, difficulty, expectations, deterministic_checks
#    If tasks need data, write generate_data.py and seed the volume:
#    python3 skills/<skill>/eval/generate_data.py
# 2. Skill OFF: run each task in a fresh Genie Code chat, save outputs
# 3. Skill ON:  same tasks, fresh chats, save outputs
# 4. Generate the scoring notebook (Steps 4-6 in Workflow):
#    - imports scorers from scorers.py (not redefined inline)
#    - loads task queries from evalset.json (not hardcoded)
#    - runs mlflow.genai.evaluate() for both arms
#    - extracts scores via compare_runs.extract_scores()
#    - calls compare_runs.main() for text report
#    See "Steps 4-6: Generate the Scoring Notebook" in Workflow below.
# 5. Error-analyze the losses (references/error-analysis.md), write the report
#    to eval/eval_report.md (references/report-template.md) — do NOT modify the skill's SKILL.md
```

## Workflow

### Step 1: Define Benchmark Tasks

Author 3-5 tasks that represent the skill's core jobs, each with ground truth a grader could check. Vary difficulty: at least one easy, one hard, one adversarial/edge case. Split task definitions across two files in `skills/<skill-name>/eval/`:

- `evalset.json` — one JSON object per task with `task_id`, `dataset`, and `query` (the verbatim prompt pasted into Genie Code).
- `expectations.json` — one JSON object per task with `task_id`, `dataset`, `difficulty` (`easy`/`hard`/`edge`), `expectations` (expected_facts, ground_truth_estimates, guidelines), and `deterministic_checks` (required_artifacts, forbidden_patterns).

Both files share `task_id` and `dataset` as join keys. The `difficulty` field is read directly from `expectations.json` by `compare_runs.py --difficulty`; no separate difficulties file is needed.

If the tasks require data, write a `generate_data.py` in the same `eval/` folder that seeds synthetic datasets into the configured volume (default: `/Volumes/<catalog>/<schema>/eval/<skill_name>/`).

- Full schema + the dimension-tuple method for coverage: `references/benchmark-tasks.md`

```json
// evalset.json
{
  "task_id": "rnaseq-001",
  "dataset": "/Volumes/<catalog>/<schema>/eval/<skill-name>/counts.csv",
  "query": "Run DESeq2 on <volume path> and list top 10 DE genes by padj"
}
```

```json
// expectations.json
{
  "task_id": "rnaseq-001",
  "dataset": "/Volumes/<catalog>/<schema>/eval/<skill-name>/counts.csv",
  "difficulty": "easy",
  "expectations": {
    "expected_facts": ["Table contains padj column", "EGFR in top 10"],
    "guidelines": ["No fabricated gene names"]
  }
}
```

### Step 2: Run Baseline Sessions (Skill OFF)

Remove/disable the skill (move the folder out of `.assistant/skills/`). For each task: open a **fresh** Genie Code chat, paste the query verbatim, let it finish, and save the output (notebook link, result table, or exported artifact). Record any wrong turns — these become baseline traces.

Guardrail: fresh chat per task. Carry-over context contaminates the comparison.

### Step 3: Run Candidate Sessions (Skill ON)

Reinstall the skill, hard-refresh, repeat the identical queries in fresh chats. Save outputs the same way. Do not re-prompt or steer differently than baseline — steering invalidates the pair.

### Steps 4–6: Generate the Scoring Notebook

Steps 4 (deterministic scoring), 5 (LLM judges), and 6 (paired comparison) are executed together in a **single scoring notebook** (`score_<skill>.ipynb`) that lives in the skill's `eval/` folder.

**Key rule**: import, don't redefine. The notebook contains zero function definitions:

| Import from | What |
|-------------|------|
| `scorers.py` | `scorers` (all `@scorer` + `make_judge` objects) |
| `compare_runs.py` | `extract_scores()` (MLflow result → per-task scores) and `main()` (paired comparison, callable with `argv`) |
| `evalset.json` | Task queries (not hardcoded) |
| `expectations.json` | Difficulty labels, expected facts, deterministic checks |

The notebook runs `mlflow.genai.evaluate()` for both arms into the same experiment, extracts per-task boolean scores via `compare_runs.extract_scores()`, saves the score JSONs, then calls `compare_runs.main()` with `--format text` for the paired comparison report.

**`scorers.py` contract**: the skill author writes one export, the `scorers` list. Nothing is appended to it at scoring time — extraction and bool coercion live in the shared `compare_runs.py`, so every skill scores the same way.

- Full cell structure, reference code, and `scorers.py` contract: `references/scoring-notebook.md`
- Ready-to-adapt scorer code: `references/scorer-pack.md`
- Extraction semantics and column naming: `references/paired-comparison.md`

### Step 7: Error Analysis and Report

Read every task that ended `tie-fail` or `regression` in either arm. Open-code the **first** observed failure per trace, then group notes into a named failure taxonomy (axial coding). The taxonomy is the evidence: it shows which failure modes the skill eliminates and which it introduces. Write the report to `eval/eval_report.md` in the evaluated skill's folder — do NOT modify the skill's `SKILL.md`.

- Worksheet + HLS seed taxonomy: `references/error-analysis.md`
- Final report format: `references/report-template.md`

## Key Parameters

| Parameter | Default | Range / Options | Effect |
|-----------|---------|-----------------|--------|
| `n_tasks` | `4` | `3`-`5` (repo rule) | Benchmark coverage vs effort |
| `judge_model` | `databricks:/databricks-gpt-5-mini` | any served judge endpoint | Judge cost/quality; must differ from generator model |
| `score_mode` | `precomputed` | `precomputed`, `predict_fn` | `precomputed` for Genie Code sessions; `predict_fn` only if a code agent can be replayed programmatically |
| `pass_rule` | `all_metrics` | `all_metrics`, `any_metric` | Task-level pass definition used by compare_runs.py |
| `ship_threshold` | `win_rate > 0` and `zero regressions` | team policy | Ship/no-ship gate, checked when given `--difficulty`. Any regression blocks it, at any difficulty, including a task the difficulty map does not label. Use `--gate no-regressions` for a regression re-run where a clean tie is the healthy result |

## Common Recipes

### Recipe: Reference-Free Scoring

When a task has no gold answer (e.g. "summarize this cohort"), score with a rubric judge instead of Correctness.

```python
from mlflow.genai.scorers import Guidelines

Guidelines(
    name="summary_quality",
    guidelines=[
        "The response must state the cohort size",
        "The response must not invent patient counts",
    ],
    model="databricks:/databricks-gpt-5-mini",
)
```

### Recipe: Trajectory (Process) Judge

When the value of the skill is *how* the work is done (right tools, right order), judge the trace. Requires the session to be traced via `mlflow` autolog or manual spans; Genie Code chats are not auto-traced, so capture the session's action log into the outputs instead and judge that.

```python
trajectory_judge = make_judge(
    name="tool_use_quality",
    instructions=(
        "Review the session's recorded actions in {{ outputs }}. "
        "Did the workflow use the appropriate tools/steps for the task in {{ inputs }}, "
        "in a sensible order, without redundant calls? Answer exactly 'yes' or 'no'."
    ),
    feedback_value_type=Literal["yes", "no"],
    model="databricks:/databricks-gpt-5-mini",
)
```

### Recipe: Regression Re-Run

After editing a skill, re-run only the tasks that previously failed plus one easy control. Compare against the previous candidate run (not baseline) to confirm the fix without re-paying full eval cost.

The healthy result here is 0 wins and 0 regressions, which the default gate fails because it requires a win. Pass `--gate no-regressions` so a clean re-run passes and only a new regression fails:

```bash
python3 skills/skill-eval/scripts/compare_runs.py prev_candidate.json new_candidate.json \
    --difficulty expectations.json --gate no-regressions --strict
```

## Expected Outputs

- **Scoring notebook** (`score_<skill>.ipynb`) in `eval/` — imports scorers from `scorers.py`, runs `mlflow.genai.evaluate()` for both arms, extracts scores via `compare_runs.extract_scores()`, calls `compare_runs.main()` with `--format text`, and prints the paired comparison report
- Two MLflow runs in one experiment (`baseline`, `with_skill`), each with per-task scorer results and linked traces
- Score JSONs (`baseline_scores.json`, `with_skill_scores.json`) in `eval/` — consumed by `compare_runs.py`
- Console comparison from `scripts/compare_runs.py`: per-task win/regression/tie-pass/tie-fail, per-metric flips, win-rate, ship-gate verdict
- Failure taxonomy: named failure modes with counts and example task_ids
- Evaluation report (`eval_report.md`) in `eval/` — paired comparison results, failure taxonomy, verdict, limitations, and reproduce instructions. Do NOT modify the evaluated skill's `SKILL.md`.

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `evaluate()` fails on data | Missing nested `inputs` key | Rows must be `{"inputs": {...}, ...}`, not flat dicts |
| Correctness scorer errors | No ground truth in row | Add `expectations.expected_facts` or `expected_response`, or drop Correctness for reference-free tasks |
| Judge call auth/endpoint error | Bad model format | Use `provider:/model`, e.g. `databricks:/databricks-gpt-5-mini` — not `databricks:model` |
| Skill not picked up by Genie Code | Stale chat/cache | New chat + hard refresh after changing skill files; check folder is under `.assistant/skills/` |
| Candidate looks worse on easy tasks | Steering difference between runs | Re-run both arms with identical verbatim queries, fresh chats |
| Judge contradicts deterministic scorers | Judge grading claims it cannot verify from `{{ outputs }}` | Scope judge to narrative-checkable claims; artifact existence/schema belong to deterministic scorers. Deterministic ground truth wins disagreements until the judge is validated (TPR/TNR vs human labels) |
| compare_runs.py reports "unpaired task" | task_id mismatch between runs | task_ids must be identical strings in both score JSONs |
| Baseline and candidate rows mixed in one run | Separate experiments not used correctly | Two `evaluate()` calls, same experiment, distinct run names |

## Guardrails

1. Binary pass/fail judges only. Never report Likert-scale averages as skill evidence.
2. Fresh Genie Code chat per task per arm; verbatim queries; no steering differences.
3. Judge model must differ from the model that generated the outputs.
4. Human reads the losses: never ship a win-rate number without error-analyzing candidate losses first.
5. Confirm with the user before any run > 20 tasks or repeated judge calls (judge cost is real).
6. Do not retry failed judge/scorer calls more than 3 times; inspect the error first.
7. Small samples (3-5 tasks) show direction, not significance — say so in the report.
8. **Information isolation**: When generating a notebook to execute benchmark tasks (Steps 2-3), the agent must read **only `evalset.json`** from the skill's `eval/` folder. It must NOT read `expectations.json`, `generate_data.py`, reference notebooks (`with_skills_*`, `no_skills_*`), or any other file in `eval/` that contains expected answers, ground truth, or evaluation criteria — doing so contaminates the run by leaking the answer key into the generation context. The agent MAY import `scorers.py` when generating the **scoring** notebook (Steps 4-5), since scoring happens after task execution is complete and requires the scorer definitions.

## Evaluation

Dogfooded 2026-09-15 against `skills/bulk-rnaseq` on fe-vm-lakebase-praneeth: 4 tasks, 2 blind agent arms, MLflow 3 scoring, paired comparison. Full report in the bulk-rnaseq SKILL.md Evaluation section. Pipeline mechanics all verified end-to-end: evalset → paired runs → `mlflow.genai.evaluate` → per-task extraction → `compare_runs.py` → report.

Findings that changed this skill:

1. **Judge scope bug (found, fixed in scorer-pack)**: the stock `task_completion` judge demanded artifact *contents* it cannot access and graded narrative verifiability — its flips were pure noise against deterministic ground truth. Judges must only grade what the provided `{{ inputs }}/{{ outputs }}` can actually evidence; artifact existence belongs to deterministic scorers.
2. **Easy tasks don't discriminate**: base model completed all tasks unaided (parity 4/4 tie-pass). Task design rule added: include at least one task where the naive approach fails, or accept that parity is the honest result.
3. **Extraction path**: per-row results are not run artifacts in MLflow 3.x — read scorer values from trace assessments (`mlflow.search_traces`) or the `EvaluationResult` object. paired-comparison.md documents this.
4. **Extraction column names (found on re-validation, MLflow 3.16, 2026-09-23)**: the `eval_results` table and `search_traces` frames name the input column `request`, not `inputs` — the earlier recipe's `r["inputs"]["task_id"]` raised `KeyError: 'inputs'`. Fixed in paired-comparison.md: read `task_id` from `request` (dict or JSON string). The same run re-confirmed the judge-noise finding live — a stock `task_completion` judge marked a crashed baseline `yes` and a clean candidate `no`, while the deterministic scorers cleanly scored the crash 0/3 and the fix 3/3.

## Bundled Resources

### Shared tooling (in `skill-eval/`)

- `references/benchmark-tasks.md` — evalset schema, task design rules, dimension-tuple coverage method
- `references/scorer-pack.md` — deterministic `@scorer` and binary `make_judge` starter code
- `references/paired-comparison.md` — extracting per-task scores from MLflow runs, comparison semantics
- `references/error-analysis.md` — open/axial coding worksheet, HLS failure-mode seeds
- `references/report-template.md` — the Evaluation section template for evaluated skills
- `references/scoring-notebook.md` — scoring notebook generation guide: cell structure, imports, `scorers.py` contract
- `scripts/compare_runs.py` — MLflow score extraction (`extract_scores`) and paired per-task comparison (win/loss/flip, win-rate); stdlib only
- `tests/test_compare_runs.py` — unit tests for the comparison logic

### Per-skill eval artifacts (in each skill's `eval/` folder)

- `assets/dogfood-bulk-rnaseq/` — (legacy location) bulk-rnaseq eval artifacts; predates the `eval/` convention. Its `evalset.json` (`{"tasks": [...]}` with `difficulty`) is accepted directly by `--difficulty`.

## References

- [Hamel Husain — Evals FAQ: error analysis](https://hamel.dev/blog/posts/evals-faq/why-is-error-analysis-so-important-in-llm-evals-and-how-is-it-performed.html) — open/axial coding methodology
- [Hamel Husain — LLM-as-judge](https://hamel.dev/blog/posts/llm-judge/) — binary judges, TPR/TNR validation
- [ai-evals-course/evals-skills](https://github.com/ai-evals-course/evals-skills) — reference skill family for eval workflows
- [MLflow 3 GenAI evaluation](https://mlflow.org/docs/latest/genai/eval-monitor/quickstart/) — `mlflow.genai.evaluate`, scorers
- [Databricks custom judges](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/custom-judge/) — `make_judge`, `{{ trace }}` judges
- [Microsoft agent evaluators](https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-evaluators/agent-evaluators) — system vs process metric split
- [Google ADK evaluation](https://adk.dev/evaluate) — evalset format, trajectory scoring
- [Anthropic — develop tests](https://platform.claude.com/docs/en/docs/test-and-evaluate/develop-tests) — grader ladder, judge != generator
