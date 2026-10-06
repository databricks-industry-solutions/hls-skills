# Evaluation

A skill should make the agent measurably better at its task. Each skill is benchmarked on 3-5 tasks by running Genie Code twice per task, once with the skill and once without, and scoring both runs the same way.

The [skill-eval](skills/skill-eval.md) skill builds the harness for this. Scores are logged to an MLflow experiment, and a paired comparison report is written to the skill's `eval/` folder. The [skill catalog](skills/index.md) shows which skills have a report.

## Run an evaluation

1. Ask Genie Code to use the skill-eval skill to generate an evaluation harness for your skill.
2. Have Genie Code generate a notebook for each task, once with your skill and once without it.
3. Use the skill-eval harness to score both notebooks. This logs the scores to MLflow and writes `eval_report.md`.

## What the `eval/` folder holds

```text
skills/<skill-name>/eval/
├── README.md               # run protocol, scorer summary, ship gate
├── evalset.json            # 3-5 benchmark task definitions (task_id, dataset, query)
├── expectations.json       # difficulty, expectations, deterministic checks per task
├── generate_data.py        # synthetic data generator (seeds the volume)
├── scorers.py              # deterministic + LLM judge definitions
├── score_<skill>.py        # generated scoring notebook: evaluate, compare, report
├── eval_report.md          # after running: paired comparison + failure taxonomy
├── baseline_scores.json    # after running: skill-off per-task scores
└── with_skill_scores.json  # after running: skill-on per-task scores
```

!!! warning "The `eval/` folder holds the answer key"
    `expectations.json` contains the expected results, so `eval/` is excluded from the bundle that is synced to Unity Catalog. Do not copy it into a skill's `references/`.
