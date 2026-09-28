# Databricks notebook source
# --- Cell 1: Overview (markdown) ---
# # Scoring Notebook — sc-rnaseq Skill Evaluation
#
# Evaluates the sc-rnaseq skill against 4 benchmark tasks (scrna-001 through scrna-004).
# Two arms: baseline (skill OFF) and candidate (skill ON).
# Scorers imported from scorers.py; comparison from compare_runs.py.
# Judge model: databricks:/databricks-gpt-5-mini

# Databricks notebook source
# --- Cell 2: Install dependencies ---
%pip install "mlflow[databricks]>=3.5.0" --quiet

# Databricks notebook source
# --- Cell 3: Restart Python ---
dbutils.library.restartPython()

# Databricks notebook source
# --- Cell 4: MLflow experiment + imports ---
import sys, json, mlflow

mlflow.set_tracking_uri("databricks")
EXPERIMENT_PATH = "/Users/yen.low@databricks.com/skill-eval-sc-rnaseq"
mlflow.set_experiment(EXPERIMENT_PATH)

SKILLS_ROOT = "/Workspace/Users/yen.low@databricks.com/.assistant/skills/hls-skills/skills"
EVAL_DIR = f"{SKILLS_ROOT}/sc-rnaseq/eval"
SCRIPTS_DIR = f"{SKILLS_ROOT}/skill-eval/scripts"
# Fall back: skill-eval may be under user skills
SKILL_EVAL_SCRIPTS = "/Workspace/Users/yen.low@databricks.com/.assistant/skills/skill-eval/scripts"

for d in (EVAL_DIR, SCRIPTS_DIR, SKILL_EVAL_SCRIPTS):
    if d not in sys.path:
        sys.path.insert(0, d)

from scorers import scorers as all_scorers
from compare_runs import extract_scores, main as compare_main

print(f"Loaded {len(all_scorers)} scorers")
print(f"Experiment: {EXPERIMENT_PATH}")

# Databricks notebook source
# --- Cell 5: Load expectations ---
with open(f"{EVAL_DIR}/expectations.json") as f:
    expectations_list = json.load(f)

# Merge deterministic_checks into expectations (scorer-pack convention)
expectations_by_task = {}
for e in expectations_list:
    merged = dict(e["expectations"])
    for k, v in e.get("deterministic_checks", {}).items():
        merged[k] = v
    expectations_by_task[e["task_id"]] = merged

print(f"Loaded expectations for {len(expectations_by_task)} tasks")

# Databricks notebook source
# --- Cell 6: Load task queries and build baseline rows ---
with open(f"{EVAL_DIR}/evalset.json") as f:
    evalset = json.load(f)
task_queries = {e["task_id"]: e["query"] for e in evalset}
task_ids = [e["task_id"] for e in evalset]

# === BASELINE OUTPUTS (skill OFF) — fill after running baseline sessions ===
# Each entry: {"response": "<summary>", "action_log": "<steps>", "result_table": bool}
no_skills_outputs = {
    "scrna-001": {
        "response": "",
        "action_log": "",
        "result_table": False,
    },
    "scrna-002": {
        "response": "",
        "action_log": "",
        "result_table": False,
    },
    "scrna-003": {
        "response": "",
        "action_log": "",
        "result_table": False,
    },
    "scrna-004": {
        "response": "",
        "action_log": "",
        "result_table": False,
    },
}

rows_baseline = [
    {
        "inputs": {"task_id": tid, "query": task_queries[tid]},
        "outputs": no_skills_outputs[tid],
        "expectations": expectations_by_task[tid],
    }
    for tid in task_ids
]

print(f"Built {len(rows_baseline)} baseline rows")

# Databricks notebook source
# --- Cell 7: Build candidate rows (skill ON) ---
# === CANDIDATE OUTPUTS (skill ON) — fill after running candidate sessions ===
with_skills_outputs = {
    "scrna-001": {
        "response": "",
        "action_log": "",
        "result_table": False,
    },
    "scrna-002": {
        "response": "",
        "action_log": "",
        "result_table": False,
    },
    "scrna-003": {
        "response": "",
        "action_log": "",
        "result_table": False,
    },
    "scrna-004": {
        "response": "",
        "action_log": "",
        "result_table": False,
    },
}

rows_with_skill = [
    {
        "inputs": {"task_id": tid, "query": task_queries[tid]},
        "outputs": with_skills_outputs[tid],
        "expectations": expectations_by_task[tid],
    }
    for tid in task_ids
]

print(f"Built {len(rows_with_skill)} candidate rows")

# Databricks notebook source
# --- Cell 8: Evaluate baseline ---
print("Running baseline evaluation...")
baseline_result = mlflow.genai.evaluate(
    data=rows_baseline,
    scorers=all_scorers,
)
print(f"Baseline evaluation complete. Run ID: {baseline_result.run_id}")

# Databricks notebook source
# --- Cell 9: Evaluate candidate ---
print("Running candidate evaluation...")
candidate_result = mlflow.genai.evaluate(
    data=rows_with_skill,
    scorers=all_scorers,
)
print(f"Candidate evaluation complete. Run ID: {candidate_result.run_id}")

# Databricks notebook source
# --- Cell 10: Extract scores + save ---
baseline_scores = extract_scores(baseline_result, rows_baseline)
candidate_scores = extract_scores(candidate_result, rows_with_skill)

with open(f"{EVAL_DIR}/baseline_scores.json", "w") as f:
    json.dump(baseline_scores, f, indent=2)
with open(f"{EVAL_DIR}/with_skill_scores.json", "w") as f:
    json.dump(candidate_scores, f, indent=2)

print("Baseline scores:", json.dumps(baseline_scores, indent=2))
print("\nCandidate scores:", json.dumps(candidate_scores, indent=2))

# Databricks notebook source
# --- Cell 11: Paired comparison ---
print("=" * 60)
print("PAIRED COMPARISON REPORT")
print("=" * 60)
compare_main([
    f"{EVAL_DIR}/baseline_scores.json",
    f"{EVAL_DIR}/with_skill_scores.json",
    "--difficulty", f"{EVAL_DIR}/expectations.json",
    "--format", "text",
])