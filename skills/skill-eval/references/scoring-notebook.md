# Scoring Notebook — Generation Guide

Referenced from SKILL.md Steps 4–6. The scoring notebook is the deliverable that ties evaluation, extraction, and comparison into a single runnable artifact.

## Principle

**Import, don't redefine.** The notebook contains zero function definitions. Scorers come from `scorers.py`, score extraction from `compare_runs.extract_scores()`, and paired comparison from `compare_runs.main()`.

## Shared modules the notebook imports

| Module | What it provides | Location |
|--------|-----------------|----------|
| `scorers.py` | `scorers` list (all `@scorer` + `make_judge` objects) | `skills/<skill>/eval/scorers.py` |
| `compare_runs.py` | `extract_scores()` (MLflow result → `{task_id: {metric: bool}}`), `main()` (CLI entry point callable with `argv`) | `skills/skill-eval/scripts/compare_runs.py` |

## Notebook cell structure

| # | Cell | What it does |
|---|------|--------------|
| 1 | Overview (markdown) | Describes the skill being evaluated, scorer source, workflow |
| 2 | Install dependencies | `%pip install "mlflow[databricks]>=3.5.0" --quiet` |
| 3 | Restart Python | `dbutils.library.restartPython()` |
| 4 | MLflow experiment + imports | `mlflow.set_experiment(...)`, put `EVAL_DIR` and `SCRIPTS_DIR` on `sys.path`, import `scorers` and `compare_runs` |
| 5 | Load expectations | Parse `expectations.json`, merge `deterministic_checks` into `expectations` |
| 6 | Build eval rows: baseline | Load `task_queries` from `evalset.json`, define `no_skills_outputs` dict, assemble `rows_baseline` |
| 7 | Build eval rows: candidate | Define `with_skills_outputs` dict, assemble `rows_with_skill` |
| 8 | Evaluate baseline | `mlflow.genai.evaluate(data=rows_baseline, scorers=all_scorers)` |
| 9 | Evaluate candidate | `mlflow.genai.evaluate(data=rows_with_skill, scorers=all_scorers)` |
| 10 | Extract scores + save | `extract_scores(result, rows, all_scorers)` → save `baseline_scores.json`, `with_skill_scores.json` |
| 11 | Paired comparison | `compare_main([...])` → call once with `--format text` (prints directly to stdout) |

## Cell-by-cell reference code

### Cell 4 — MLflow experiment + imports

Scorers come from `scorers.py`, extraction and comparison from `compare_runs.py`. Both directories go on `sys.path` here, before any import:

```python
import sys, mlflow
mlflow.set_tracking_uri("databricks")
EXPERIMENT_PATH = "/Users/<you>/skill-eval-<skill-name>"
mlflow.set_experiment(EXPERIMENT_PATH)
SKILLS_ROOT = "/Workspace/Users/<you>/.assistant/skills/<repo>/skills"
EVAL_DIR = f"{SKILLS_ROOT}/<skill>/eval"
SCRIPTS_DIR = f"{SKILLS_ROOT}/skill-eval/scripts"
for d in (EVAL_DIR, SCRIPTS_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)
from scorers import scorers as all_scorers
from compare_runs import extract_scores, main as compare_main
```

### Cell 5 — Load expectations

```python
import json

with open(f"{EVAL_DIR}/expectations.json") as f:
    expectations_list = json.load(f)

# Merge deterministic_checks into expectations (scorer-pack convention)
expectations_by_task = {}
for e in expectations_list:
    merged = dict(e["expectations"])
    for k, v in e.get("deterministic_checks", {}).items():
        merged[k] = v
    expectations_by_task[e["task_id"]] = merged
```

### Cell 6 — Build eval rows (baseline)

Task queries loaded from `evalset.json`, not hardcoded:

```python
with open(f"{EVAL_DIR}/evalset.json") as f:
    evalset = json.load(f)
task_queries = {e["task_id"]: e["query"] for e in evalset}
task_ids = [e["task_id"] for e in evalset]

# Outputs captured from the no-skills notebook execution
no_skills_outputs = {
    "<task-001>": {
        "response": "<summary of what the notebook produced>",
        "action_log": "<comma-separated list of methods/steps>",
        "result_table": True,
    },
    # ... one entry per task
}

rows_baseline = [
    {
        "inputs": {"task_id": tid, "query": task_queries[tid]},
        "outputs": no_skills_outputs[tid],
        "expectations": expectations_by_task[tid],
    }
    for tid in task_ids
]
```

### Cell 10 — Extract scores + save

Extraction uses `compare_runs.extract_scores()`, not inline code. It raises on a missing task or a `None`/`NaN`/non-binary score rather than recording a silent fail:

```python
baseline_scores = extract_scores(baseline_result, rows_baseline, all_scorers)
candidate_scores = extract_scores(candidate_result, rows_with_skill, all_scorers)

# Save to JSON — these are the inputs to compare_runs.py
with open(f"{EVAL_DIR}/baseline_scores.json", "w") as f:
    json.dump(baseline_scores, f, indent=2)
with open(f"{EVAL_DIR}/with_skill_scores.json", "w") as f:
    json.dump(candidate_scores, f, indent=2)
```

### Cell 11 — Paired comparison via `compare_runs.main()`

Comparison uses `compare_runs.main()` programmatically, not inline reimplementation. Call once with `--format text` — the output prints directly to stdout and is sufficient for the eval report:

```python
compare_main([
    f"{EVAL_DIR}/baseline_scores.json",
    f"{EVAL_DIR}/with_skill_scores.json",
    "--difficulty", f"{EVAL_DIR}/expectations.json",
    "--format", "text",
])
```

## Outputs dict shape

For each task in each arm, capture three fields from the executed notebook:

```python
{
    "response": "<summary of what the notebook produced: estimates, conclusions, key numbers>",
    "action_log": "<comma-separated list of methods/steps the notebook executed>",
    "result_table": True  # or False if the notebook crashed
}
```

These are assembled into eval rows as `{"inputs": {"task_id": ..., "query": ...}, "outputs": {...}, "expectations": {...}}`.

## `scorers.py` contract

The skill author writes one export, `scorers` — a list of all `@scorer` functions and `make_judge` objects. See `references/scorer-pack.md` for starter code.

```python
scorers = [artifact_produced, no_forbidden_content, ..., task_completion_judge, tool_use_judge]
```

Nothing is appended to `scorers.py` when the scoring notebook is generated. Extraction (the `request` column, `<scorer>/value` columns, strict bool coercion of `None`/`NaN`/`yes`/`no`/`true`/`false`/`1`/`0`) lives once in `compare_runs.extract_scores()`; do not reimplement it in `scorers.py` or the notebook.

The evaluation report is written to `eval/eval_report.md` (see `references/report-template.md`) — not into the skill's `SKILL.md`.
