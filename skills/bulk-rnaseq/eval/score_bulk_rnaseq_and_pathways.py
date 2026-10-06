# Databricks notebook source
# MAGIC %md
# MAGIC # Integrated bulk RNA-seq + pathway enrichment skill evaluation
# MAGIC Scores precomputed baseline and skill-enabled Genie Code outputs, extracts
# MAGIC paired binary metrics, and applies the standard skill-eval ship gate.

# COMMAND ----------

# MAGIC %pip install "mlflow[databricks]>=3.5.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import base64
import sys
from pathlib import Path

import mlflow
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ExportFormat

mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Users/yen.low@databricks.com/skill-eval-rnaseq-pathways")

SKILLS_DIR = Path(
    "/Workspace/Users/yen.low@databricks.com/.assistant/skills/hls-skills/skills"
)
EVAL_DIR = SKILLS_DIR / "bulk-rnaseq" / "eval"
SCRIPTS_DIR = SKILLS_DIR / "skill-eval" / "scripts"
for directory in (EVAL_DIR, SCRIPTS_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from scorers import scorers as all_scorers
from compare_runs import extract_scores, main as compare_main

# COMMAND ----------

with open(EVAL_DIR / "evalset.json", encoding="utf-8") as handle:
    evalset = json.load(handle)
with open(EVAL_DIR / "expectations.json", encoding="utf-8") as handle:
    expectations_list = json.load(handle)

queries = {task["task_id"]: task["query"] for task in evalset}
task_ids = [task["task_id"] for task in evalset]
expectations_by_task = {}
for task in expectations_list:
    merged = dict(task["expectations"])
    merged.update(task.get("deterministic_checks", {}))
    expectations_by_task[task["task_id"]] = merged

# COMMAND ----------

with open(
    "/Volumes/hls_amer_catalog/vital_skills/eval/baseline_outputs.json",
    encoding="utf-8",
) as handle:
    baseline_outputs = json.load(handle)
with open(
    "/Volumes/hls_amer_catalog/vital_skills/eval/with_skill_outputs.json",
    encoding="utf-8",
) as handle:
    with_skill_outputs = json.load(handle)

workspace = WorkspaceClient()
baseline_export = workspace.workspace.export(
    "/Users/yen.low@databricks.com/.assistant/skills/hls-skills/skills/"
    "bulk-rnaseq/eval/run_baseline_arm",
    format=ExportFormat.SOURCE,
)
candidate_export = workspace.workspace.export(
    "/Users/yen.low@databricks.com/.assistant/skills/hls-skills/skills/"
    "bulk-rnaseq/eval/run_with_skills_arm",
    format=ExportFormat.SOURCE,
)
baseline_source = base64.b64decode(baseline_export.content).decode("utf-8")
with_skill_source = base64.b64decode(candidate_export.content).decode("utf-8")
for task_number, task_id in enumerate(task_ids, start=1):
    marker = f"# MAGIC ## Task {task_number}"
    next_marker = f"# MAGIC ## Task {task_number + 1}"
    baseline_section = baseline_source.split(marker, 1)[1]
    candidate_section = with_skill_source.split(marker, 1)[1]
    if next_marker in baseline_section:
        baseline_section = baseline_section.split(next_marker, 1)[0]
    if next_marker in candidate_section:
        candidate_section = candidate_section.split(next_marker, 1)[0]
    baseline_outputs[task_id]["notebook_source"] = baseline_section
    with_skill_outputs[task_id]["notebook_source"] = candidate_section

rows_baseline = [
    {
        "inputs": {"task_id": task_id, "query": queries[task_id]},
        "outputs": baseline_outputs[task_id],
        "expectations": expectations_by_task[task_id],
    }
    for task_id in task_ids
]
rows_with_skill = [
    {
        "inputs": {"task_id": task_id, "query": queries[task_id]},
        "outputs": with_skill_outputs[task_id],
        "expectations": expectations_by_task[task_id],
    }
    for task_id in task_ids
]

# COMMAND ----------

with mlflow.start_run(run_name="baseline"):
    baseline_result = mlflow.genai.evaluate(data=rows_baseline, scorers=all_scorers)

# COMMAND ----------

with mlflow.start_run(run_name="with_skills"):
    candidate_result = mlflow.genai.evaluate(data=rows_with_skill, scorers=all_scorers)

# COMMAND ----------

baseline_scores = extract_scores(baseline_result, rows_baseline)
candidate_scores = extract_scores(candidate_result, rows_with_skill)

with open(EVAL_DIR / "baseline_scores.json", "w", encoding="utf-8") as handle:
    json.dump(baseline_scores, handle, indent=2)
with open(EVAL_DIR / "with_skill_scores.json", "w", encoding="utf-8") as handle:
    json.dump(candidate_scores, handle, indent=2)

# COMMAND ----------

compare_main(
    [
        str(EVAL_DIR / "baseline_scores.json"),
        str(EVAL_DIR / "with_skill_scores.json"),
        "--difficulty",
        str(EVAL_DIR / "expectations.json"),
        "--format",
        "text",
    ]
)