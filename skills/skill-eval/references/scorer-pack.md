# Scorer Starter Pack

Referenced from SKILL.md Steps 4-5. Adapt names and checks to the skill under test.

Import rules (MLflow 3, not MLflow 2):

```python
from typing import Literal

import mlflow
from mlflow.genai.scorers import scorer, Correctness, ExpectationsGuidelines, Safety
from mlflow.genai.judges import make_judge
from mlflow.entities import Feedback
```

## Level 1 — Deterministic Scorers

Cheapest signal. Write one per `deterministic_checks` entry in `expectations.json`. Return `bool` or `Feedback`.

```python
@scorer
def artifact_produced(outputs: dict) -> bool:
    """Pass if the session produced its primary artifact."""
    return bool(outputs.get("result_table"))


@scorer
def no_forbidden_content(outputs: dict, expectations: dict) -> Feedback:
    """Pass if no forbidden pattern appears in the response.

    Reads expectations.forbidden_patterns — the row-conversion step in
    benchmark-tasks.md merges deterministic_checks into expectations.
    """
    import re
    response = outputs.get("response", "")
    for pattern in expectations.get("forbidden_patterns", []):
        if re.search(pattern, response, re.IGNORECASE):
            return Feedback(
                name="no_forbidden_content",
                value=False,
                rationale=f"Forbidden pattern found: {pattern}",
            )
    return Feedback(name="no_forbidden_content", value=True)


@scorer
def schema_valid(outputs: dict) -> bool:
    """Pass if the output has the expected shape for downstream use."""
    response = outputs.get("response", "")
    return "padj" in response and "gene" in response.lower()
```

Rules:

- `@scorer` decorator is mandatory; metric name defaults to the function name.
- Return types allowed: `bool`, `int`, `float`, `str`, `Feedback`, or `list[Feedback]`. Multiple Feedbacks in one list need unique `name=` values.
- Simple type hints only (`dict`, `str`) — complex generics break serialization.
- Import non-stdlib helpers **inside** the function if scorers will ever be registered for production monitoring.

## Level 2 — Binary LLM Judges

For subjective criteria. Binary only: `yes`/`no` or `true`/`false`. Judge model must differ from the generator model.

### Correctness (built-in, needs ground truth)

```python
Correctness(model="databricks:/databricks-gpt-5-mini")
# requires expectations.expected_facts or expectations.expected_response per row
```

### Guidelines (built-in, per-row rules)

```python
ExpectationsGuidelines()
# reads expectations.guidelines from each row; no constructor args
```

### Custom judge (make_judge)

```python
task_completion_judge = make_judge(
    name="task_completion",
    instructions="""
You are grading whether an agent session completed a scientific computing task.

Task given to the agent: {{ inputs }}
Session outputs: {{ outputs }}

Grading rules:
- Grade only claims checkable from the text above (method soundness, consistency of reported numbers). Do not demand file contents you cannot access.
- The statistical approach must be reasonable for the task domain.
- Numbers reported must be internally consistent with the described outputs.
- Partial completion counts as failure.

Answer with exactly one word: 'yes' or 'no'.
""",
    feedback_value_type=Literal["yes", "no"],
    model="databricks:/databricks-gpt-5-mini",
)
```

Declare the value type explicitly (`from typing import Literal`) — without `feedback_value_type` the judge output is an untyped string and downstream boolean extraction gets fragile.

Instruction-writing rules (the top failure mode is a vague judge):

1. Role line → grading rules → exact output format.
2. Spell out what counts as failure. "Partial completion counts as failure" does more work than any adjective.
3. Demand a single exact token ('yes'/'no'). No scales, no explanations required in the value.
4. Add 2-3 few-shot examples with critiques once you have labeled failures from error analysis — not before.
5. Template variables: `{{ inputs }}`, `{{ outputs }}`, `{{ expectations }}`, `{{ trace }}`. Trace judges require an explicit `model=`.
6. **Judge only what the provided evidence can support.** Found in dogfooding: a judge instructed to require that "artifacts must exist" but given only narrative outputs (paths + booleans) will either rubber-stamp or blanket-fail — it cannot verify existence. Scope judges to claims checkable from the text (method soundness from action_log, consistency of reported numbers). Artifact existence, schema, and ground-truth thresholds belong to deterministic scorers.

### Process / trajectory judge

Genie Code sessions are not auto-traced, so judge the recorded `action_log` in outputs (see benchmark-tasks.md):

```python
tool_use_judge = make_judge(
    name="tool_use_quality",
    instructions="""
Review the agent's recorded actions in {{ outputs }} (field: action_log) for the task in {{ inputs }}.

Pass only if:
- Tools/steps match the task's requirements,
- Order is sensible (e.g. data loaded before analyzed),
- No redundant or irrelevant calls.

Answer with exactly one word: 'yes' or 'no'.
""",
    feedback_value_type=Literal["yes", "no"],
    model="databricks:/databricks-gpt-5-mini",
)
```

## Assembling the Scorer List

```python
scorers = [
    artifact_produced,          # Level 1
    no_forbidden_content,       # Level 1
    Correctness(model="databricks:/databricks-gpt-5-mini"),      # Level 2, needs expectations
    task_completion_judge,      # Level 2
    tool_use_judge,             # Level 2, process
]

results = mlflow.genai.evaluate(
    data=rows,            # list[dict] with inputs/outputs/expectations
    scorers=scorers,      # no predict_fn — outputs are pre-computed
)
```

Start cheap: if Level 1 already separates baseline from candidate clearly, say so in the report and skip judges for those tasks.
