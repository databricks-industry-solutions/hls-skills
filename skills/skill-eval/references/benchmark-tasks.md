# Benchmark Tasks — Evalset Schema and Task Design

Referenced from SKILL.md Step 1.

## Task Design Rules

1. **3-5 tasks** per repo requirement (AGENTS.md testing section). Fewer is unprovable, more is unpaid.
2. **Difficulty spread**: at least 1 easy (core happy path), 1 hard (multi-step, real data size), 1 edge/adversarial (ambiguous input, missing data, or a task near the skill's boundary). **Include at least one task where the naive no-skill approach actually fails** — dogfooding showed strong base models pass easy/medium tasks unaided (parity), so without a discriminator task the only honest verdict is tie.
3. **Ground truth must be checkable** by a grader who was not in the session: exact values where possible (gene counts, table names, padj thresholds), guidelines where not.
4. **Real inputs**: point at real data in the workspace (volumes, UC tables). Synthetic tasks need expert review before results are trusted.
5. **Verbatim queries**: the `query` string is what gets pasted into Genie Code, character-for-character, in both arms.

## Evalset Schema

One JSON object per task. This same object later becomes an MLflow eval row by adding `outputs`.

```json
{
  "task_id": "<skill>-<NNN>",
  "query": "<exact prompt pasted into Genie Code>",
  "difficulty": "easy | hard | edge",
  "expectations": {
    "expected_facts": ["<checkable fact 1>", "<checkable fact 2>"],
    "expected_response": "<optional gold answer, for Correctness scorer>",
    "guidelines": ["<must rule>", "<must-not rule>"]
  },
  "deterministic_checks": {
    "required_artifacts": ["result_table", "notebook"],
    "forbidden_patterns": ["<regex that must NOT appear, e.g. fabricated identifier>"]
  }
}
```

Field notes:

- `task_id` — stable string, identical across baseline and candidate runs. The comparison joins on it.
- `expected_facts` — feeds the MLflow `Correctness` scorer. Facts, not prose: "Output table has a padj column", not "a good analysis".
- `guidelines` — feeds `ExpectationsGuidelines`. Use for must/must-not rules.
- `deterministic_checks` — consumed by your `@scorer` functions (Level 1), not by MLflow built-ins.

## Dimension-Tuple Coverage Method

To pick tasks that cover the skill's surface without guessing, define 2-3 variation axes and pick tuples:

| Axis | Example values (bulk-rnaseq skill) |
|------|------------------------------------|
| Data modality | bulk RNA-seq, single-cell, proteomics |
| Task type | QC, differential expression, enrichment |
| Input state | clean counts, messy headers, missing metadata |

Hand-write ~6 tuples, keep the 3-5 that matter most, render each into a natural task. A tuple that no real user would hit is a wasted task.

## Converting to MLflow Rows

After both session arms are done, each task becomes two rows (one per arm). `deterministic_checks` merge into `expectations` so scorers read one place:

```python
row = {
    "inputs": {"query": task["query"], "task_id": task["task_id"]},
    "outputs": {
        "response": "<summary of what the session produced>",
        "result_table": "<UC table or artifact path, if any>",
        "action_log": "<ordered list of tools/steps the session took>",
    },
    "expectations": {
        **task["expectations"],
        **task.get("deterministic_checks", {}),
    },
}
```

`outputs` is pre-computed, so `mlflow.genai.evaluate()` needs **no `predict_fn`**. `action_log` is the stand-in for a trajectory — Genie Code sessions are not auto-traced into MLflow, so record the session's steps manually into outputs for the process judge to review.
