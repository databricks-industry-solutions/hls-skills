# Databricks notebook source
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # Scoring Notebook: accelerators Skill Evaluation
# MAGIC
# MAGIC Scores two paired arms (baseline / with-skill) with `mlflow.genai.evaluate`. Scorers come from `scorers.py`;
# MAGIC score extraction and comparison come from `skill-eval/scripts/compare_runs.py`.
# MAGIC
# MAGIC Arm outputs are the markdown answers Genie Code saved to the outputs volume, moved into
# MAGIC `outputs/baseline/` and `outputs/with_skill/` after each arm.

# COMMAND ----------

# DBTITLE 1,Install deps
# MAGIC %pip install "mlflow[databricks]>=3.5.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Config
dbutils.widgets.text("skills_root", "/Workspace/Users/<you>/hls-skills/skills")
dbutils.widgets.text("data_dir", "/Volumes/hls_amer_catalog/vital_skills/eval/accelerators")
dbutils.widgets.text("experiment", "/Users/<you>/skill-eval-accelerators")

SKILLS_ROOT = dbutils.widgets.get("skills_root")
DATA_DIR = dbutils.widgets.get("data_dir")
EXPERIMENT_PATH = dbutils.widgets.get("experiment")
EVAL_DIR = f"{SKILLS_ROOT}/accelerators/eval"
SCRIPTS_DIR = f"{SKILLS_ROOT}/skill-eval/scripts"

# COMMAND ----------

# DBTITLE 1,MLflow experiment + imports
import json
import sys

import mlflow

mlflow.set_tracking_uri("databricks")
mlflow.set_experiment(EXPERIMENT_PATH)
for d in (EVAL_DIR, SCRIPTS_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

from compare_runs import extract_scores, main as compare_main
from scorers import scorers as all_scorers

print(f"Loaded {len(all_scorers)} scorers")

# COMMAND ----------

# DBTITLE 1,Load tasks + expectations
with open(f"{EVAL_DIR}/evalset.json") as f:
    evalset = json.load(f)
with open(f"{EVAL_DIR}/expectations.json") as f:
    expectations_list = json.load(f)

expectations_by_task = {}
for e in expectations_list:
    merged = dict(e["expectations"])
    merged.update(e.get("deterministic_checks", {}))
    expectations_by_task[e["task_id"]] = merged

task_ids = [e["task_id"] for e in evalset]
queries = {e["task_id"]: e["query"] for e in evalset}

# COMMAND ----------

# DBTITLE 1,Build rows per arm
def read_answer(arm: str, task_id: str) -> str:
    try:
        with open(f"{DATA_DIR}/outputs/{arm}/{task_id}.md") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def build_rows(arm: str) -> list[dict]:
    return [
        {
            "inputs": {"task_id": tid, "query": queries[tid]},
            "outputs": {"response": read_answer(arm, tid)},
            "expectations": expectations_by_task[tid],
        }
        for tid in task_ids
    ]


rows_baseline = build_rows("baseline")
rows_candidate = build_rows("with_skill")
for arm, rows in (("baseline", rows_baseline), ("with_skill", rows_candidate)):
    missing = [r["inputs"]["task_id"] for r in rows if not r["outputs"]["response"]]
    print(f"{arm}: {len(rows) - len(missing)}/{len(rows)} answers found; missing {missing}")

# COMMAND ----------

# DBTITLE 1,Evaluate both arms
with mlflow.start_run(run_name="baseline"):
    result_baseline = mlflow.genai.evaluate(data=rows_baseline, scorers=all_scorers)
with mlflow.start_run(run_name="with_skill"):
    result_candidate = mlflow.genai.evaluate(data=rows_candidate, scorers=all_scorers)

# COMMAND ----------

# DBTITLE 1,Extract scores + save JSONs
scorer_names = {"artifact_produced", "steers_to_accelerator", "no_forbidden_content", "precise_next_step", "factually_grounded"}
baseline_scores = extract_scores(result_baseline, rows_baseline, scorer_names)
candidate_scores = extract_scores(result_candidate, rows_candidate, scorer_names)

with open(f"{DATA_DIR}/baseline_scores.json", "w") as f:
    json.dump(baseline_scores, f, indent=2)
with open(f"{DATA_DIR}/with_skill_scores.json", "w") as f:
    json.dump(candidate_scores, f, indent=2)

# COMMAND ----------

# DBTITLE 1,Paired comparison
compare_main([
    f"{DATA_DIR}/baseline_scores.json",
    f"{DATA_DIR}/with_skill_scores.json",
    "--difficulty", f"{EVAL_DIR}/expectations.json",
    "--format", "markdown",
])
