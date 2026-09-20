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
import math

TRUTHY = ("true", "yes", "1")
FALSY = ("false", "no", "0")


def to_bool(task_id, metric, value):
    """Never coerce an unknown value to False — a failed scorer is not a task failure."""
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise ValueError(f"{task_id}/{metric}: scorer produced no value")
    text = str(value).strip().lower()
    if text in TRUTHY:
        return True
    if text in FALSY:
        return False
    raise ValueError(f"{task_id}/{metric}: non-boolean score {value!r}; make the scorer binary")


result = mlflow.genai.evaluate(data=rows, scorers=scorers)
df = result.tables["eval_results"]          # per-row: inputs, outputs, <scorer>/value, <scorer>/rationale
scores = {}
for _, r in df.iterrows():
    # Join on the task_id carried in the row itself. evaluate() scores rows
    # concurrently and does not promise to return them in input order, so
    # zipping this table against `rows` can attach one task's scores to another.
    tid = r["inputs"]["task_id"]
    scores[tid] = {
        col[: -len("/value")]: to_bool(tid, col, r[col])
        for col in df.columns
        if col.endswith("/value")
    }
missing = {row["inputs"]["task_id"] for row in rows} - set(scores)
assert not missing, f"no scores returned for {sorted(missing)}"
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
- Ship rule: win_rate > 0 AND zero regressions, at any difficulty (pass `--difficulty` to enable the gate). A hard or edge regression blocks the gate just like an easy one, because a regression on the adversarial task is the result the eval exists to surface.
- For a regression re-run against a previous candidate, where 0 wins and 0 regressions is the healthy result, use `--gate no-regressions`. The default rule requires a win and would fail an unchanged, healthy skill.

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
