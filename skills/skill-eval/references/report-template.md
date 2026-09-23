# Evaluation Report Template

Referenced from SKILL.md Step 7. Paste into the evaluated skill's SKILL.md as its `## Evaluation` section. Keep it short — a reviewer should grasp the evidence in 60 seconds.

---

```markdown
## Evaluation

**Setup**: <n> benchmark tasks, run with and without the skill in Genie Code on
<workspace>, <date>. Scored with MLflow 3 (`mlflow.genai.evaluate`): <scorer list>.
Judge model: <model> (generator: <model>).

**Results**:

| task_id | difficulty | baseline | with skill | outcome |
|---------|-----------|----------|------------|---------|
| task-001 | easy | pass | pass | tie-pass |
| task-002 | hard | fail | pass | **win** |
| task-003 | edge | pass | fail | **regression** |

Win rate: <x>/<n>. Regressions: <y>/<n>.

**Failure taxonomy** (from error analysis of losses):

| failure mode | count | arm | status |
|--------------|-------|-----|--------|
| wrong-identifier-resolution | 2 | baseline | eliminated by skill |
| premature-stop | 1 | with skill | open — fix in Workflow step 3 |

**Verdict**: <ship / fix-and-rerun> — <one sentence why>.

**Limitations**: <n> tasks = directional evidence, not statistical. <other caveats,
e.g. one task used synthetic data, judge not yet validated against human labels>.

**Reproduce**: evalset at <path>; runs in experiment `<experiment path>`;
comparison via `scripts/compare_runs.py`.
```

---

Fill rules:

- The table shows flips, not just rates — one flip is a third of a 3-task eval.
- Every `regression` row must appear in the failure taxonomy with an owner decision (fix now / accept / monitor).
- "Verdict" cites the ship rule from SKILL.md Key Parameters (`ship_threshold`).
- Never delete the Limitations block. Small-sample honesty is what keeps the repo's evals credible.
