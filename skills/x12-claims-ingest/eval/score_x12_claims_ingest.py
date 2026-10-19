# Databricks notebook source
# MAGIC %md
# MAGIC # Score x12-claims-ingest: Genie Code with vs without the skill
# MAGIC
# MAGIC Scorers come from `eval/scorers.py` (deterministic table checks + one binary judge); the composite
# MAGIC objective from `tests/objective.py` (pinned v1 weights) is logged per task as run metrics.
# MAGIC Extraction and the paired comparison come from `skills/skill-eval/scripts/compare_runs.py`.
# MAGIC Arms write tables with a per-arm prefix (`<PREFIX>` in evalset.json) and a `<task_id>.json` with
# MAGIC `response` and `action_log` under `RUNS_DIR/<arm>/`.

# COMMAND ----------

# MAGIC %pip install "mlflow[databricks]>=3.5.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import sys

import mlflow

mlflow.set_tracking_uri("databricks")
dbutils.widgets.text("experiment", "/Users/raven.mukherjee@databricks.com/skill-eval-x12-claims-ingest")
dbutils.widgets.text("baseline_prefix", "b_{task}_")
dbutils.widgets.text("with_skill_prefix", "s_{task}_")
dbutils.widgets.text("tasks", "")  # comma-separated task ids; empty = all in evalset.json
dbutils.widgets.text("run_suffix", "")
dbutils.widgets.text("runs_dir", "/Volumes/hls_amer_catalog/x12_claims_ingest_test/eval/x12-claims-ingest/_runs")
EXPERIMENT_PATH = dbutils.widgets.get("experiment")
mlflow.set_experiment(EXPERIMENT_PATH)
SKILLS_ROOT = "/Workspace/Users/raven.mukherjee@databricks.com/hls-skills-dev/hls-skills/skills"  # not .assistant/skills
EVAL_DIR = f"{SKILLS_ROOT}/x12-claims-ingest/eval"
TESTS_DIR = f"{SKILLS_ROOT}/x12-claims-ingest/tests"
SCRIPTS_DIR = f"{SKILLS_ROOT}/skill-eval/scripts"
for d in (EVAL_DIR, TESTS_DIR, SCRIPTS_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)
from collect_outputs import collect
from compare_runs import extract_scores, main as compare_main
from ingest_scorers import IngestGold, IngestOutput, gold_from_key, to_jsonable
from objective import ingest_objective
from scorers import scorers as all_scorers

SCHEMA = "hls_amer_catalog.x12_claims_ingest_test"
RUNS_DIR = dbutils.widgets.get("runs_dir")
# table prefix per arm; {task} = task_id with '-' -> '_'
ARMS = {"baseline": dbutils.widgets.get("baseline_prefix"), "with_skill": dbutils.widgets.get("with_skill_prefix")}

# COMMAND ----------

with open(f"{EVAL_DIR}/expectations.json") as f:
    expectations_list = json.load(f)
with open(f"{EVAL_DIR}/evalset.json") as f:
    evalset = json.load(f)
task_queries = {e["task_id"]: e["query"] for e in evalset}
_only = [t.strip() for t in dbutils.widgets.get("tasks").split(",") if t.strip()]
task_ids = [e["task_id"] for e in evalset if not _only or e["task_id"] in _only]
expectations_list = [e for e in expectations_list if e["task_id"] in task_ids]

expectations_by_task, golds = {}, {}
for e in expectations_list:
    checks = e.get("deterministic_checks", {})
    with open(checks["gold_key"]) as f:
        gold = gold_from_key(json.load(f), requires_run=checks.get("requires_run", False))
    golds[e["task_id"]] = gold
    expectations_by_task[e["task_id"]] = {**e["expectations"], **checks, "ingest_gold": to_jsonable(gold)}

# COMMAND ----------

def arm_rows(arm: str):
    rows, objectives = [], {}
    for tid in task_ids:
        prefix = ARMS[arm].format(task=tid.replace("-", "_"))
        checks = expectations_by_task[tid]
        pipeline = checks.get("pipeline_name", "").replace("<PREFIX>", prefix) or None
        ingest_output = collect(spark, SCHEMA, prefix, checks.get("requires_run", False), pipeline)
        try:
            with open(f"{RUNS_DIR}/{arm}/{tid}.json") as f:
                session = json.load(f)
        except FileNotFoundError:
            session = {"response": "", "action_log": ""}
        rows.append({
            "inputs": {"task_id": tid, "query": task_queries[tid].replace("<PREFIX>", prefix)},
            "outputs": {"response": session.get("response", ""), "action_log": session.get("action_log", ""),
                        "ingest_output": ingest_output},
            "expectations": expectations_by_task[tid],
        })
        out = IngestOutput(**{**ingest_output,
                              "flagged_pcns": set(ingest_output["flagged_pcns"]),
                              "reported_bad_files": set(ingest_output["reported_bad_files"]),
                              "lines": {p: {int(k): v for k, v in ls.items()} for p, ls in ingest_output["lines"].items()}})
        objectives[tid] = ingest_objective(golds[tid], out)
    return rows, objectives

rows_baseline, obj_baseline = arm_rows("baseline")
rows_with_skill, obj_with_skill = arm_rows("with_skill")

# COMMAND ----------

with mlflow.start_run(run_name="baseline" + dbutils.widgets.get("run_suffix")):
    baseline_result = mlflow.genai.evaluate(data=rows_baseline, scorers=all_scorers)
with mlflow.start_run(run_name="with_skill" + dbutils.widgets.get("run_suffix")):
    candidate_result = mlflow.genai.evaluate(data=rows_with_skill, scorers=all_scorers)

for result, objs in ((baseline_result, obj_baseline), (candidate_result, obj_with_skill)):
    with mlflow.start_run(run_id=result.run_id):
        mlflow.log_metrics({f"ingest_score_{t.replace('-', '_')}": o.score for t, o in objs.items()})
        mlflow.log_metric("ingest_score_mean", sum(o.score for o in objs.values()) / len(objs))
        mlflow.log_dict({t: {"score": o.score, "gated": o.gated, **o.breakdown} for t, o in objs.items()},
                        "ingest_objective.json")

# COMMAND ----------

scorer_names = {s.name for s in all_scorers}
baseline_scores = extract_scores(baseline_result, rows_baseline, scorer_names=scorer_names)
candidate_scores = extract_scores(candidate_result, rows_with_skill, scorer_names=scorer_names)
with open(f"{EVAL_DIR}/baseline_scores.json", "w") as f:
    json.dump(baseline_scores, f, indent=2)
with open(f"{EVAL_DIR}/with_skill_scores.json", "w") as f:
    json.dump(candidate_scores, f, indent=2)
print({t: (obj_baseline[t].score, obj_with_skill[t].score) for t in task_ids})

# COMMAND ----------

compare_main([
    f"{EVAL_DIR}/baseline_scores.json",
    f"{EVAL_DIR}/with_skill_scores.json",
    "--difficulty", f"{EVAL_DIR}/expectations.json",
    "--format", "text",
])
