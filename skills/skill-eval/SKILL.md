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
- **Python**: `pip install "mlflow[databricks]>=3.1.0"` (evaluation only; no Spark needed when using list-of-dicts datasets). API usage here follows the MLflow 3.1+ GenAI interfaces (`mlflow.genai.evaluate`, `@scorer`, `make_judge`) — pin and re-verify if running on a different major version
- **Inputs**: the skill under test installed in Genie Code (`Workspace/.assistant/skills/<name>/SKILL.md` or user-level `~/.assistant/skills/`)
- **Environment**: an MLflow experiment path you can write to, e.g. `/Users/<you>/skill-eval-<skill-name>`

## Quick Start

```text
# 1. Write 3-5 benchmark tasks with ground truth (references/benchmark-tasks.md)
# 2. Skill OFF: run each task in a fresh Genie Code chat, save outputs
# 3. Skill ON:  same tasks, fresh chats, save outputs
# 4. Score both runs (references/scorer-pack.md):
mlflow.genai.evaluate(data=rows_baseline, scorers=scorers)    # run "baseline"
mlflow.genai.evaluate(data=rows_with_skill, scorers=scorers)  # run "with_skill"
# 5. Compare paired runs (from the repository root):
python3 skills/skill-eval/scripts/compare_runs.py baseline_scores.json with_skill_scores.json
# 6. Error-analyze the losses (references/error-analysis.md), write the report
#    (references/report-template.md) into the skill's Evaluation section
```

## Workflow

### Step 1: Define Benchmark Tasks

Author 3-5 tasks that represent the skill's core jobs, each with ground truth a grader could check. Vary difficulty: at least one easy, one hard, one adversarial/edge case. Store as an evalset (one JSON object per task: `task_id`, `query`, `expectations`).

- Full schema + the dimension-tuple method for coverage: `references/benchmark-tasks.md`

```json
{
  "task_id": "rnaseq-001",
  "query": "Run DESeq2 on <volume path> and list top 10 DE genes by padj",
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

### Step 4: Score Deterministically (Level 1)

Assemble rows as `{"inputs": {...}, "outputs": {...}, "expectations": {...}}` with pre-collected outputs (no `predict_fn` needed — outputs already exist). Apply cheap deterministic checks first with `@scorer` functions: artifact produced? schema valid? forbidden content absent?

- Ready-to-adapt scorer code: `references/scorer-pack.md`

```python
from mlflow.genai.scorers import scorer

@scorer
def artifact_produced(outputs: dict) -> bool:
    return bool(outputs.get("result_table"))
```

### Step 5: Score with Binary Judges (Level 2)

Add LLM judges for subjective criteria. Binary pass/fail only — never Likert scales. Use a judge model **different from the generator** (default: `databricks:/databricks-gpt-5-mini`). For process quality ("did it call the right tools in a sensible order?"), use a `make_judge` with `{{ trace }}`.

- Judge instructions pattern (critique-first, few-shot): `references/scorer-pack.md`

```python
from typing import Literal

from mlflow.genai.judges import make_judge

task_judge = make_judge(
    name="task_completion",
    instructions=(
        "Given the task {{ inputs }} and the session outputs {{ outputs }}, "
        "grade only claims checkable from that text (method soundness, "
        "internal consistency of reported numbers); artifact existence is "
        "covered by deterministic scorers, not you. "
        "Answer exactly 'yes' or 'no'."
    ),
    feedback_value_type=Literal["yes", "no"],
    model="databricks:/databricks-gpt-5-mini",
)
```

### Step 6: Paired Comparison

Run both datasets through `mlflow.genai.evaluate()` into the **same experiment**, then compare per task. A paired comparison reports flips (baseline-pass → candidate-fail = regression; baseline-fail → candidate-pass = win), not just two averages.

```bash
# from the repository root; --difficulty enables the ship gate, --strict exits 1 on gate fail (CI)
# --strict also exits 1 if --difficulty is missing, since the gate cannot be evaluated without it
python3 skills/skill-eval/scripts/compare_runs.py baseline_scores.json with_skill_scores.json \
    --difficulty difficulties.json [--strict]
# -> per-task win/regression/tie-pass/tie-fail, per-metric flips, win-rate, SHIP GATE PASS/FAIL verdict
```

- Extraction recipe (search_runs -> per-task score JSON): `references/paired-comparison.md`

### Step 7: Error Analysis and Report

Read every task that ended `tie-fail` or `regression` in either arm. Open-code the **first** observed failure per trace, then group notes into a named failure taxonomy (axial coding). The taxonomy is the evidence: it shows which failure modes the skill eliminates and which it introduces.

- Worksheet + HLS seed taxonomy: `references/error-analysis.md`
- Final report format (goes into the skill's `## Evaluation` section): `references/report-template.md`

## Key Parameters

| Parameter | Default | Range / Options | Effect |
|-----------|---------|-----------------|--------|
| `n_tasks` | `4` | `3`-`5` (repo rule) | Benchmark coverage vs effort |
| `judge_model` | `databricks:/databricks-gpt-5-mini` | any served judge endpoint | Judge cost/quality; must differ from generator model |
| `score_mode` | `precomputed` | `precomputed`, `predict_fn` | `precomputed` for Genie Code sessions; `predict_fn` only if a code agent can be replayed programmatically |
| `pass_rule` | `all_metrics` | `all_metrics`, `any_metric` | Task-level pass definition used by compare_runs.py |
| `ship_threshold` | `win_rate > 0` and `no regressions on easy or unlabeled tasks` | team policy | Ship/no-ship gate. The script checks it when given `--difficulty`. A regression on a task missing from the difficulty map also blocks the gate, so a partial map cannot hide one |

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

## Expected Outputs

- Two MLflow runs in one experiment (`baseline`, `with_skill`), each with per-task scorer results and linked traces
- Console/markdown comparison from `scripts/compare_runs.py`: per-task win/regression/tie-pass/tie-fail, per-metric flips, win-rate, ship-gate verdict
- Failure taxonomy: named failure modes with counts and example task_ids
- Completed `## Evaluation` section in the evaluated skill's SKILL.md (from `references/report-template.md`)

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

## Evaluation

Dogfooded 2026-09-15 against `skills/bulk-rnaseq` on fe-vm-lakebase-praneeth: 4 tasks, 2 blind agent arms, MLflow 3 scoring, paired comparison. Full report in the bulk-rnaseq SKILL.md Evaluation section. Pipeline mechanics all verified end-to-end: evalset → paired runs → `mlflow.genai.evaluate` → per-task extraction → `compare_runs.py` → report.

Findings that changed this skill:

1. **Judge scope bug (found, fixed in scorer-pack)**: the stock `task_completion` judge demanded artifact *contents* it cannot access and graded narrative verifiability — its flips were pure noise against deterministic ground truth. Judges must only grade what the provided `{{ inputs }}/{{ outputs }}` can actually evidence; artifact existence belongs to deterministic scorers.
2. **Easy tasks don't discriminate**: base model completed all tasks unaided (parity 4/4 tie-pass). Task design rule added: include at least one task where the naive approach fails, or accept that parity is the honest result.
3. **Extraction path**: per-row results are not run artifacts in MLflow 3.x — read scorer values from trace assessments (`mlflow.search_traces`) or the `EvaluationResult` object. paired-comparison.md documents this.

## Bundled Resources

- `references/benchmark-tasks.md` — evalset schema, task design rules, dimension-tuple coverage method
- `references/scorer-pack.md` — deterministic `@scorer` and binary `make_judge` starter code
- `references/paired-comparison.md` — extracting per-task scores from MLflow runs, comparison semantics
- `references/error-analysis.md` — open/axial coding worksheet, HLS failure-mode seeds
- `references/report-template.md` — the Evaluation section template for evaluated skills
- `scripts/compare_runs.py` — paired per-task comparison (win/loss/flip, win-rate); stdlib only
- `tests/test_compare_runs.py` — unit tests for the comparison logic

## References

- [Hamel Husain — Evals FAQ: error analysis](https://hamel.dev/blog/posts/evals-faq/why-is-error-analysis-so-important-in-llm-evals-and-how-is-it-performed.html) — open/axial coding methodology
- [Hamel Husain — LLM-as-judge](https://hamel.dev/blog/posts/llm-judge/) — binary judges, TPR/TNR validation
- [ai-evals-course/evals-skills](https://github.com/ai-evals-course/evals-skills) — reference skill family for eval workflows
- [MLflow 3 GenAI evaluation](https://mlflow.org/docs/latest/genai/eval-monitor/quickstart/) — `mlflow.genai.evaluate`, scorers
- [Databricks custom judges](https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/custom-judge/) — `make_judge`, `{{ trace }}` judges
- [Microsoft agent evaluators](https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-evaluators/agent-evaluators) — system vs process metric split
- [Google ADK evaluation](https://adk.dev/evaluate) — evalset format, trajectory scoring
- [Anthropic — develop tests](https://platform.claude.com/docs/en/docs/test-and-evaluate/develop-tests) — grader ladder, judge != generator
