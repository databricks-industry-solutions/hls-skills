# Paired Comparison — Extraction and Semantics

Referenced from SKILL.md Step 6. The comparison unit is the **task**, not the metric average.

## Running the Two Arms into One Experiment

```python
import mlflow

mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Users/<you>/skill-eval-<skill-name>")

baseline = mlflow.genai.evaluate(data=rows_baseline, scorers=scorers)
with_skill = mlflow.genai.evaluate(data=rows_with_skill, scorers=scorers)
```

Both calls land as runs in the same experiment. The UI's Compare view gives side-by-side aggregates; the per-task paired analysis below is what the report needs.

## Extracting Per-Task Scores

`compare_runs.py` consumes two JSON files, one per arm:

```json
{
  "rnaseq-001": {"artifact_produced": true, "task_completion": true, "tool_use_quality": false},
  "rnaseq-002": {"artifact_produced": true, "task_completion": false, "tool_use_quality": false}
}
```

**Stable paths (both verified on MLflow 3.x):**

1. **Immediately, in the same process** — the `EvaluationResult` returned by `evaluate()` carries the per-row table. Extract before the process exits:

```python
result = mlflow.genai.evaluate(data=rows, scorers=scorers)
df = result.tables["eval_results"]          # per-row: inputs, outputs, <scorer>/value, <scorer>/rationale
scores = {}
for row, (_, r) in zip(rows, df.iterrows()):
    tid = row["inputs"]["task_id"]
    scores[tid] = {
        col[: -len("/value")]: (str(r[col]).lower() in ("true", "yes", "1"))
        for col in df.columns
        if col.endswith("/value") and r[col] is not None
    }
```

2. **Later, from any process** — scorer outputs are logged as **assessments on the run's traces**, not as run artifacts (there is no `eval_results.json` to download; that path does not exist):

```python
df = mlflow.search_traces(locations=[EXPERIMENT_ID], run_id=RUN_ID)
for _, t in df.iterrows():
    for a in (t.get("assessments") or []):
        name = a["assessment_name"]           # e.g. "task_completion"
        value = a.get("feedback", {}).get("value")
        rationale = a.get("rationale")
```

3. **UI export** — open the run's evaluation view and transcribe per-row values. With 3-5 tasks this is minutes; fine for one-offs.

## Comparison Semantics

Per task, per metric:

| Baseline | Candidate | Meaning |
|----------|-----------|---------|
| pass | pass | tie-pass |
| fail | fail | tie-fail |
| fail | pass | **win** (skill fixed it) |
| pass | fail | **regression** (skill broke it) |

Task-level outcome (default `all_metrics` pass rule): task passes iff all metrics pass.

- **win_rate** = wins / total paired tasks
- **regression_rate** = regressions / total paired tasks
- Ship rule of thumb: win_rate > 0 AND zero regressions on easy tasks (pass `--difficulty` to have the script check this). A regression on a task the difficulty map does not label also blocks the gate, because the script cannot tell whether that task was easy. Anything else needs error analysis before a decision.

With 3-5 tasks, treat the numbers as directional. One flip = 20-33% swing; report the flips themselves, not just rates.

## CLI

```bash
# from the repository root
python3 skills/skill-eval/scripts/compare_runs.py baseline_scores.json with_skill_scores.json
python3 skills/skill-eval/scripts/compare_runs.py baseline.json with_skill.json \
    --pass-rule any_metric --format markdown --difficulty difficulties.json
# CI: --strict exits 1 when the ship gate fails, and also when --difficulty is absent
python3 skills/skill-eval/scripts/compare_runs.py baseline.json with_skill.json \
    --difficulty difficulties.json --strict
```

`difficulties.json` is `{task_id: "easy"|"hard"|"edge"}` lifted from the evalset; it enables the easy-task ship-gate check in the output.
