# Databricks notebook source
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # Scoring Notebook — rwe-cohortstudy Skill Evaluation
# MAGIC
# MAGIC This notebook scores two paired arms (baseline / with-skill) for the `rwe-cohortstudy` skill using `mlflow.genai.evaluate`.
# MAGIC
# MAGIC **Scorers** are imported from `scorers.py` (zero redefinitions inline).
# MAGIC
# MAGIC **Comparison** is delegated to `compare_runs.py` from the shared `skill-eval/scripts/` folder.
# MAGIC
# MAGIC | Cell | Purpose |
# MAGIC |------|---------|
# MAGIC | 1 | Install deps + restart |
# MAGIC | 2 | MLflow experiment + import scorers |
# MAGIC | 3 | Load expectations |
# MAGIC | 4 | Build eval rows — baseline (no skills) |
# MAGIC | 5 | Build eval rows — candidate (with skills) |
# MAGIC | 6 | Evaluate baseline |
# MAGIC | 7 | Evaluate candidate |
# MAGIC | 8 | Extract scores + save JSONs |
# MAGIC | 9 | Paired comparison + markdown report |

# COMMAND ----------

# DBTITLE 1,Install deps
# MAGIC %pip install "mlflow[databricks]>=3.5.0" openai --quiet

# COMMAND ----------

# DBTITLE 1,Restart Python
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,MLflow experiment + import scorers
import sys, mlflow

mlflow.set_tracking_uri("databricks")

EXPERIMENT_PATH = "/Users/yen.low@databricks.com/skill-eval-rwe-cohortstudy"
mlflow.set_experiment(EXPERIMENT_PATH)

EVAL_DIR = "/Workspace/Users/yen.low@databricks.com/.assistant/skills/hls-skills/skills/rwe-cohortstudy/eval"
if EVAL_DIR not in sys.path:
    sys.path.insert(0, EVAL_DIR)

from scorers import scorers as all_scorers
print(f"Loaded {len(all_scorers)} scorers: {[s.name if hasattr(s, 'name') else s.__name__ for s in all_scorers]}")

# COMMAND ----------

# DBTITLE 1,Load expectations
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

print("Loaded expectations for tasks:", list(expectations_by_task.keys()))

# COMMAND ----------

# DBTITLE 1,Build eval rows: baseline (no skills)
with open(f"{EVAL_DIR}/evalset.json") as f:
    evalset = json.load(f)
task_queries = {e["task_id"]: e["query"] for e in evalset}
task_ids = [e["task_id"] for e in evalset]

# ── Outputs captured from no_skills_rwe_cohortstudy notebook execution ──
no_skills_outputs = {
    "rwe-001": {
        "response": (
            "Crude OR = 1.5777 (Harmful, p=0.074). "
            "8/11 covariates imbalanced (SMD > 0.1). "
            "Imbalanced variables: age, charlson_score, prior_mi, diabetes_duration, hba1c, egfr, bmi, smoker. "
            "Confounder adjustment is needed. "
            "No propensity score matching performed. No love plot generated."
        ),
        "action_log": (
            "Loaded rwe_cohort.csv (2000 patients) -> "
            "Crude mortality comparison (chi-square test, OR=1.5777) -> "
            "Baseline covariate standardized mean difference (SMD) balance table"
        ),
        "result_table": True,
    },
    "rwe-002": {
        "response": (
            "Propensity score model (logistic regression, AUC=0.7831). "
            "PS matching: caliper=0.217, 187/187 treated matched, matched sample n=374. "
            "Matched OR = 0.4697. "
            "Inverse probability weights computed. "
            "IPW-weighted treated mortality=0.0717, control=0.0961. "
            "Risk difference=-0.0245. IPW odds ratio = 0.7259. "
            "Adjusted logistic regression OR = 0.4045 [0.2346, 0.6972], p=0.001. "
            "Treatment is PROTECTIVE after adjustment. "
            "No stabilized weights. No doubly robust estimation. No E-value computed. "
            "No confidence interval for DR estimate."
        ),
        "action_log": (
            "Loaded rwe_cohort.csv -> "
            "Propensity score estimation (logistic regression, AUC=0.7831) -> "
            "Nearest-neighbor matching (caliper=0.217) -> "
            "Inverse probability weights (not stabilized) -> "
            "IPW-weighted outcome comparison -> "
            "Adjusted logistic regression"
        ),
        "result_table": True,
    },
    "rwe-003": {
        "response": (
            "KM survival curves plotted. Log-rank test p=0.002630. "
            "Unadjusted Cox hazard ratio = 1.6484 [1.1863, 2.2907], p=0.0029. "
            "Adjusted Cox model (covariate-adjusted, NOT IPW-weighted): "
            "treatment HR = 0.6550 [0.4666, 0.9194], p=0.014. "
            "Treatment is PROTECTIVE after covariate adjustment. "
            "Proportional hazards assumption NOT tested (no Schoenfeld residuals). "
            "RMST NOT computed. No IPW applied."
        ),
        "action_log": (
            "Loaded rwe_survival.csv -> "
            "Kaplan-Meier curves -> "
            "Log-rank test -> "
            "Unadjusted Cox PH model -> "
            "Covariate-adjusted Cox PH model (no IPW weighting)"
        ),
        "result_table": True,
    },
    "rwe-004": {
        "response": (
            "Intention-to-treat analysis performed. "
            "Compared mortality between treatment initiation (n=724) and no initiation (n=776). "
            "No cloning applied. No censoring for strategy deviation. "
            "No per-protocol design. No censoring weights computed."
        ),
        "action_log": (
            "Loaded rwe_tte.csv -> "
            "Data exploration (1500 rows, detected columns) -> "
            "Intention-to-treat mortality comparison (no cloning, no censoring)"
        ),
        "result_table": True,
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
for r in rows_baseline:
    print(f"  {r['inputs']['task_id']}: {r['outputs']['response'][:80]}...")

# COMMAND ----------

# DBTITLE 1,Build eval rows: candidate (with skills)
# ── Outputs captured from with_skills_rwe_cohortstudy notebook execution ──
with_skills_outputs = {
    "rwe-001": {
        "response": (
            "Crude OR = 1.5778 (Harmful, p=0.074). "
            "8/11 covariates imbalanced (SMD > 0.1). "
            "Propensity scores estimated via logistic regression. "
            "Confounder assessment via standardized mean differences (SMD). "
            "Love plot generated showing covariate balance before/after. "
            "Balance table produced. Confounder adjustment confirmed necessary."
        ),
        "action_log": (
            "Loaded rwe_cohort.csv -> "
            "Crude mortality comparison -> "
            "Propensity score estimation (logistic regression) -> "
            "Standardized mean difference (SMD) computation -> "
            "Balance table -> "
            "Love plot"
        ),
        "result_table": True,
    },
    "rwe-002": {
        "response": (
            "Full causal pipeline executed. "
            "Propensity scores estimated via logistic regression. Common support verified. "
            "Stabilized inverse probability weights computed (ATE, trimmed at 1%). "
            "Balance diagnostics: love plot and weighted baseline characteristics table. "
            "IPW-weighted risk ratio = 0.8249, odds ratio = 0.8099. "
            "G-computation ATE = -0.0479 [95% CI -0.0698, -0.0273]. "
            "Doubly robust ATE = -0.0328 [95% CI -0.0704, 0.0047]. "
            "E-value = 1.719. Tipping point analysis performed. "
            "Bootstrap confidence intervals computed. "
            "Treatment reduces mortality risk."
        ),
        "action_log": (
            "Loaded rwe_cohort.csv -> "
            "Propensity score estimation (logistic regression) -> "
            "Common support check -> "
            "Stabilized IPW (ATE weights, trimmed) -> "
            "Balance table (love plot, weighted SMDs) -> "
            "IPW-weighted effect estimation (RR, OR) -> "
            "G-computation (outcome regression standardization) -> "
            "Doubly robust estimation (bootstrap CI, n_boot=300) -> "
            "E-value sensitivity analysis -> "
            "Tipping point analysis"
        ),
        "result_table": True,
    },
    "rwe-003": {
        "response": (
            "Propensity scores estimated, stabilized IPW computed. "
            "Weighted Kaplan-Meier curves plotted. "
            "Weighted log-rank test p = 0.000236. "
            "Weighted Cox proportional hazards model with robust (sandwich) standard errors: "
            "hazard ratio = 0.6421 [0.4526, 0.9109], p=0.013. "
            "Proportional hazards assumption tested via Schoenfeld residuals "
            "(treatment p=0.110, PH assumption not violated). "
            "Restricted mean survival time (RMST) difference = 6.6 days (tau=687 days). "
            "Treatment improves survival."
        ),
        "action_log": (
            "Loaded rwe_survival.csv -> "
            "Propensity score estimation (logistic regression) -> "
            "Stabilized IPW computation (ATE weights) -> "
            "Balance assessment (love plot, balance table) -> "
            "Weighted Kaplan-Meier curves (weighted logrank) -> "
            "Weighted Cox PH model (robust SE, IPW applied) -> "
            "Schoenfeld residuals test (proportional hazards assumption) -> "
            "Restricted mean survival time (RMST) difference computation"
        ),
        "result_table": True,
    },
    "rwe-004": {
        "response": (
            "Target trial emulation using cloning-censoring-weighting framework. "
            "Two strategies: A (initiate treatment) vs B (no initiation). Grace period: 30 days. "
            "Cloning applied: 3000 observations from 1500 patients (1500 per strategy). "
            "Censoring applied for strategy deviation (776 censored in A, 724 in B). "
            "Inverse probability weights for censoring computed. "
            "Per-protocol effect on uncensored subset (n=1500). "
            "IPW-censor-weighted risk ratio = 1.7697. "
            "Censoring-weighted logistic regression: strategy effect = -0.0251 "
            "[95% CI -0.0489, -0.0013], p=0.039. "
            "E-value = 2.937. "
            "Conclusion: initiating treatment reduces mortality per per-protocol analysis."
        ),
        "action_log": (
            "Loaded rwe_tte.csv -> "
            "Target trial specification (PICO, grace period 30 days) -> "
            "Cloning (1500 -> 3000 observations, 2 strategies) -> "
            "Censoring for strategy deviation -> "
            "IPW-censor weight estimation -> "
            "Per-protocol effect estimation (censoring-weighted logistic regression) -> "
            "E-value sensitivity analysis"
        ),
        "result_table": True,
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
for r in rows_with_skill:
    print(f"  {r['inputs']['task_id']}: {r['outputs']['response'][:80]}...")

# COMMAND ----------

# DBTITLE 1,Evaluate baseline (no skills)
with mlflow.start_run(run_name="baseline_no_skills"):
    baseline_result = mlflow.genai.evaluate(
        data=rows_baseline,
        scorers=all_scorers,
    )
print("Baseline evaluation complete.")
print("Tables:", list(baseline_result.tables.keys()))

# COMMAND ----------

# DBTITLE 1,Evaluate candidate (with skills)
with mlflow.start_run(run_name="with_skill"):
    candidate_result = mlflow.genai.evaluate(
        data=rows_with_skill,
        scorers=all_scorers,
    )
print("Candidate evaluation complete.")
print("Tables:", list(candidate_result.tables.keys()))

# COMMAND ----------

# DBTITLE 1,Extract scores + save JSONs
import importlib
import scorers as _sm
importlib.reload(_sm)
extract_scores = _sm.extract_scores
SCORER_NAMES = _sm.SCORER_NAMES
print("Active SCORER_NAMES:", sorted(SCORER_NAMES))

baseline_scores  = extract_scores(baseline_result,  rows_baseline)
candidate_scores = extract_scores(candidate_result, rows_with_skill)

baseline_path  = f"{EVAL_DIR}/baseline_scores.json"
candidate_path = f"{EVAL_DIR}/with_skill_scores.json"

with open(baseline_path, "w") as f:
    json.dump(baseline_scores, f, indent=2)
with open(candidate_path, "w") as f:
    json.dump(candidate_scores, f, indent=2)

print("Saved:", baseline_path)
print("Saved:", candidate_path)
print("\n=== Baseline scores ===")
print(json.dumps(baseline_scores, indent=2))
print("\n=== Candidate scores ===")
print(json.dumps(candidate_scores, indent=2))

# COMMAND ----------

# DBTITLE 1,Paired comparison
COMPARE_RUNS_DIR = "/Workspace/Users/yen.low@databricks.com/.assistant/skills/hls-skills/skills/skill-eval/scripts"
if COMPARE_RUNS_DIR not in sys.path:
    sys.path.insert(0, COMPARE_RUNS_DIR)
from compare_runs import main as compare_main

compare_main([
    baseline_path,
    candidate_path,
    "--difficulty", f"{EVAL_DIR}/expectations.json",
    "--format", "text",
])