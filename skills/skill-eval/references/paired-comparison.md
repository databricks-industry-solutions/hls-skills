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

**Stable paths (both verified against MLflow 3.16 on Databricks):**

The per-row table names the columns `request` / `response` (the dict you passed as `inputs` / `outputs`), **not** `inputs` / `outputs`, and each scorer adds `<name>/value` and `<name>/rationale`. So read `task_id` out of `request`, and note `request` may come back as a dict or a JSON string.

1. **Immediately, in the same process** — the `EvaluationResult` returned by `evaluate()` carries the per-row table. Extract before the process exits:

```python
import math

TRUTHY = ("true", "yes", "1")
FALSY = ("false", "no", "0")


# Same coercion rules as compare_runs.py `_to_bool` (bool / yes-no / 1-0 / true-false),
# applied here at extraction time so the JSON you write is already clean. Keep the two
# in sync: an unknown value raises in both places rather than silently becoming False.
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


import json


def task_id_of(request):
    """`request` is the inputs dict you passed (sometimes a JSON string)."""
    req = json.loads(request) if isinstance(request, str) else request
    return req["task_id"]


result = mlflow.genai.evaluate(data=rows, scorers=scorers)
df = result.tables["eval_results"]          # per-row: trace_id, request, response, <scorer>/value, <scorer>/rationale, assessments
scores = {}
for _, r in df.iterrows():
    # Join on the task_id carried in the row itself. evaluate() scores rows
    # concurrently and does not promise to return them in input order, so
    # zipping this table against `rows` can attach one task's scores to another.
    tid = task_id_of(r["request"])
    scores[tid] = {
        col[: -len("/value")]: to_bool(tid, col, r[col])
        for col in df.columns
        if col.endswith("/value")
    }
missing = {row["inputs"]["task_id"] for row in rows} - set(scores)
assert not missing, f"no scores returned for {sorted(missing)}"
```

2. **Later, from any process** — scorer outputs are logged as **assessments on the run's traces**, not as run artifacts (there is no `eval_results.json` to download; that path does not exist). This is the path that survives the process exiting, and the one dogfooding actually used:

```python
# run_id filters to the arm; each assessment is one scorer's result on one trace
df = mlflow.search_traces(run_id=RUN_ID)   # add locations=[EXPERIMENT_ID] to scope the search
scores = {}
for _, t in df.iterrows():
    tid = task_id_of(t["request"])
    metrics = {}
    for a in (t.get("assessments") or []):
        name = a["assessment_name"]                    # e.g. "task_completion"
        value = a.get("feedback", {}).get("value")     # "yes"/"no"/"true"/"false"
        if name and value is not None:
            metrics[name] = to_bool(tid, name, value)
    scores[tid] = metrics
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

`difficulties.json` is `{task_id: "easy"|"hard"|"edge"}` lifted from the evalset; it enables the ship-gate check in the output (a regression at any difficulty blocks it).

`--strict` also fails on any incomplete comparison: a task **unpaired** (in one file only), **uncomparable** (in both but sharing no metric name), or **partially mismatched** (a metric present in only one arm — the odd metric, possibly the one that regressed, drops out of the verdict). A candidate that crashed on, dropped, or renamed a metric of a would-be regression must not clear the gate on the surviving signal. Fix the dropped/renamed metric, or pass `--allow-incomplete` to ship on the paired subset deliberately. Without `--strict`, the verdict still prints but carries a `comparison incomplete` caveat next to it.

Difficulty labels enable the gate and label regressions in the output, but do not change the arithmetic — every regression blocks, at any level (there is no easy/hard weighting). `--difficulty` is required under `--strict` to enforce the coverage discipline of having assigned levels, not because the value feeds the pass/fail decision.

For a skill whose value is convention consistency rather than raw task success, the honest result is parity (all tie-pass), which the default gate fails for having no win. Ship such a skill on `--gate no-regressions` instead — a clean tie passes and only a new regression fails.
