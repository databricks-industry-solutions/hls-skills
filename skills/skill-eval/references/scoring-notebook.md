# Scoring Notebook — Generation Guide

Referenced from SKILL.md Steps 4–6. The scoring notebook is the deliverable that ties evaluation, extraction, and comparison into a single runnable artifact.

## Principle

**Import, don't redefine.** The notebook contains zero function definitions. Scorers come from `scorers.py`, score extraction from `scorers.extract_scores()`, and paired comparison from `compare_runs.main()`.

## Shared modules the notebook imports

| Module | What it provides | Location |
|--------|-----------------|----------|
| `scorers.py` | `scorers` list (all `@scorer` + `make_judge` objects), `SCORER_NAMES`, `extract_scores()` | `skills/<skill>/eval/scorers.py` |
| `compare_runs.py` | `main()` (CLI entry point callable with `argv`), `_to_bool()`, `compare()`, `format_text()`, `format_markdown()` | `skills/skill-eval/scripts/compare_runs.py` |

## Notebook cell structure

| # | Cell | What it does |
|---|------|--------------|
| 1 | Overview (markdown) | Describes the skill being evaluated, scorer source, workflow |
| 2 | Install dependencies | `%pip install "mlflow[databricks]>=3.5.0" --quiet` |
| 3 | Restart Python | `dbutils.library.restartPython()` |
| 4 | MLflow experiment + import scorers | `mlflow.set_experiment(...)`, `sys.path.insert(0, EVAL_DIR)`, `from scorers import scorers as all_scorers` |
| 5 | Load expectations | Parse `expectations.json`, merge `deterministic_checks` into `expectations` |
| 6 | Build eval rows: baseline | Load `task_queries` from `evalset.json`, define `no_skills_outputs` dict, assemble `rows_baseline` |
| 7 | Build eval rows: candidate | Define `with_skills_outputs` dict, assemble `rows_with_skill` |
| 8 | Evaluate baseline | `mlflow.genai.evaluate(data=rows_baseline, scorers=all_scorers)` |
| 9 | Evaluate candidate | `mlflow.genai.evaluate(data=rows_with_skill, scorers=all_scorers)` |
| 10 | Extract scores + save | `from scorers import extract_scores` → save `baseline_scores.json`, `with_skill_scores.json` |
| 11 | Paired comparison | `from compare_runs import main as compare_main` → call once with `--format text` (prints directly to stdout) |

## Cell-by-cell reference code

### Cell 4 — MLflow experiment + import scorers

Scorers come from `scorers.py`, not redefined inline:

```python
import sys, mlflow
mlflow.set_tracking_uri("databricks")
EXPERIMENT_PATH = "/Users/<you>/skill-eval-<skill-name>"
mlflow.set_experiment(EXPERIMENT_PATH)
EVAL_DIR = "/Workspace/Users/<you>/.assistant/skills/<repo>/skills/<skill>/eval"
if EVAL_DIR not in sys.path:
    sys.path.insert(0, EVAL_DIR)
from scorers import scorers as all_scorers
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

Extraction uses `scorers.extract_scores()`, not inline code:

```python
from scorers import extract_scores

baseline_scores = extract_scores(baseline_result, rows_baseline)
candidate_scores = extract_scores(candidate_result, rows_with_skill)

# Save to JSON — these are the inputs to compare_runs.py
with open(f"{EVAL_DIR}/baseline_scores.json", "w") as f:
    json.dump(baseline_scores, f, indent=2)
with open(f"{EVAL_DIR}/with_skill_scores.json", "w") as f:
    json.dump(candidate_scores, f, indent=2)
```

### Cell 11 — Paired comparison via `compare_runs.main()`

Comparison uses `compare_runs.main()` programmatically, not inline reimplementation. Call once with `--format text` — the output prints directly to stdout and is sufficient for the eval report:

```python
COMPARE_RUNS_DIR = "/Workspace/Users/<you>/.assistant/skills/<repo>/skills/skill-eval/scripts"
if COMPARE_RUNS_DIR not in sys.path:
    sys.path.insert(0, COMPARE_RUNS_DIR)
from compare_runs import main as compare_main

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

`scorers.py` is authored in two phases:

### Phase 1 — Skill author writes (before any eval run)

- `scorers` — list of all `@scorer` functions and `make_judge` objects

This is the only export required when the file is first created. See `references/scorer-pack.md` for starter code.

### Phase 2 — Agent appends during scoring notebook generation

When generating the scoring notebook, the agent adds the following to `scorers.py` if not already present:

- `SCORER_NAMES` — set of scorer name strings, derived from the `scorers` list (stays in sync automatically)
- `extract_scores(result, rows, scorer_names=None)` — parses `EvaluationResult.tables["eval_results"]` into `{task_id: {metric: bool}}`; delegates bool coercion to `compare_runs._to_bool()`

These are generated on the fly because they depend on the MLflow column naming convention (`<scorer>/value`) and `compare_runs._to_bool()`, which the skill author shouldn't need to know about. The agent adapts the extraction logic to the actual scorer names present in `scorers.py`.

`compare_runs._to_bool()` handles `None`, `NaN`, `bool`, and string (`"yes"/"no"/"true"/"false"/"1"/"0"`) coercion centrally. Do not reimplement this logic anywhere else.

### Final state after both phases

```python
# Phase 1 (skill author)
scorers = [artifact_produced, no_forbidden_content, ..., task_completion_judge, tool_use_judge]

# Phase 2 (agent-generated)
SCORER_NAMES = {s.name if hasattr(s, 'name') else s.__name__ for s in scorers}

from compare_runs import _to_bool

def extract_scores(result, rows, scorer_names=None):
    names = scorer_names or SCORER_NAMES
    df = result.tables["eval_results"]
    value_cols = [c for c in df.columns if c.endswith("/value") and c[:-len("/value")] in names]
    scores = {}
    for _, r in df.iterrows():
        req = json.loads(r["request"]) if isinstance(r["request"], str) else r["request"]
        tid = req["task_id"]
        scores[tid] = {col[:-len("/value")]: _to_bool(r[col], context=f"{tid}/{col}") for col in value_cols}
    missing = {row["inputs"]["task_id"] for row in rows} - set(scores)
    if missing:
        raise ValueError(f"No scores returned for tasks: {sorted(missing)}")
    return scores
```

## Reference implementation

See `skills/rwe-cohortstudy/eval/score_rwe_cohortstudy` for a working example. The evaluation report is written to `eval/eval_report.md` (see `references/report-template.md`) — not into the skill's `SKILL.md`.
