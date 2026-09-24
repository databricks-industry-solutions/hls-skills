#!/usr/bin/env python3
"""
Scorers for rwe-cohortstudy skill evaluation.

Level 1 (deterministic @scorer): artifact_produced, no_forbidden_content,
    methodology_keywords, balance_reported, sensitivity_analysis_reported,
    estimate_deviation.
Level 2 (binary LLM judges): task_completion, tool_use_quality.

Import rules (MLflow 3, not MLflow 2):
    pip install "mlflow[databricks]>=3.5.0"
"""

import json
import re
from typing import Literal

import mlflow
import openai
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback

# ── Level 1: Deterministic Scorers ─────────────────────────────────────────


@scorer
def artifact_produced(outputs: dict) -> bool:
    """Pass if the session produced its primary artifact (result table or output)."""
    return bool(outputs.get("result_table") or outputs.get("response"))


@scorer
def no_forbidden_content(outputs: dict, expectations: dict) -> Feedback:
    """Pass if no forbidden pattern appears in the response."""
    response = str(outputs.get("response", ""))
    for pattern in expectations.get("forbidden_patterns", []):
        if re.search(pattern, response, re.IGNORECASE):
            return Feedback(
                name="no_forbidden_content",
                value=False,
                rationale=f"Forbidden pattern found: {pattern}",
            )
    return Feedback(name="no_forbidden_content", value=True)


@scorer
def methodology_keywords(outputs: dict, expectations: dict) -> bool:
    """
    Pass if the response mentions the key methodological terms expected
    for the task (from expected_facts). Checks for domain-specific keywords
    that indicate the correct RWE method was used.
    """
    response = str(outputs.get("response", "")).lower()
    action_log = str(outputs.get("action_log", "")).lower()
    combined = response + " " + action_log

    # Must mention at least 2 key method terms from expectations
    key_terms = [
        "propensity score",
        "logistic regression",
        "matching",
        "caliper",
        "inverse probability",
        "weight",
        "standardized mean difference",
        "smd",
        "balance",
        "doubly robust",
        "e-value",
        "cox",
        "hazard ratio",
        "proportional hazards",
        "schoenfeld",
        "restricted mean survival time",
        "rmst",
        "target trial",
        "cloning",
        "censoring",
        "per-protocol",
        "bootstrap",
        "confidence interval",
    ]
    found = sum(1 for term in key_terms if term in combined)
    return found >= 2


@scorer
def balance_reported(outputs: dict) -> bool:
    """
    Pass if the response or action log mentions balance diagnostics
    (SMD values, balance table, or love plot).
    """
    combined = str(outputs.get("response", "")) + " " + str(outputs.get("action_log", ""))
    combined_lower = combined.lower()
    return any(
        term in combined_lower
        for term in ["smd", "standardized mean difference", "balance table", "love plot", "balanced"]
    )


@scorer
def sensitivity_analysis_reported(outputs: dict) -> Feedback:
    """
    Pass if the response or action log mentions any form of sensitivity analysis
    for unmeasured confounding or robustness of causal estimates.

    Covers: E-value, quantitative bias analysis, tipping point analysis,
    Rosenbaum bounds, negative control outcomes/exposures, varying caliper/
    matching parameters, subgroup sensitivity checks, and general
    "sensitivity analysis" phrasing.
    """
    combined = str(outputs.get("response", "")) + " " + str(outputs.get("action_log", ""))
    combined_lower = combined.lower()

    sensitivity_terms = [
        "e-value",
        "e value",
        "sensitivity analysis",
        "sensitivity to unmeasured confounding",
        "quantitative bias analysis",
        "tipping point",
        "rosenbaum bound",
        "negative control outcome",
        "negative control exposure",
        "robustness check",
        "sensitivity check",
        "varying caliper",
        "trimming weight",
        "truncating weight",
        "alternative specification",
        "unmeasured confounder",
    ]
    matched = [t for t in sensitivity_terms if t in combined_lower]
    if matched:
        return Feedback(
            name="sensitivity_analysis_reported",
            value=True,
            rationale=f"Sensitivity terms found: {', '.join(matched)}",
        )
    return Feedback(
        name="sensitivity_analysis_reported",
        value=False,
        rationale="No sensitivity analysis terms found in output.",
    )


@scorer
def estimate_deviation(outputs: dict, expectations: dict) -> Feedback:
    """
    Pass if reported effect estimates (HR, OR, RR, RMST, ATE, E-value)
    are within a relative tolerance of the ground-truth values.

    Expects expectations["ground_truth_estimates"] as a dict, e.g.:
        {"hazard_ratio": 0.72, "odds_ratio": 0.65, "rmst_difference": 15.3}
    """
    ground_truth = expectations.get("ground_truth_estimates", {})
    if not ground_truth:
        return Feedback(
            name="estimate_deviation",
            value=True,
            rationale="No ground-truth estimates provided; skipped.",
        )

    combined = str(outputs.get("response", "")) + " " + str(outputs.get("action_log", ""))

    TOLERANCE = 0.25  # 25% relative tolerance (accommodates OR/HR non-collapsibility)

    # Maps canonical name -> regex patterns that capture the numeric value
    ESTIMATE_PATTERNS: dict[str, list[str]] = {
        "hazard_ratio": [
            r"hazard\s+ratio[:\s=~]*([\d]+\.?[\d]*)",
            r"\bHR[:\s=~]*([\d]+\.?[\d]*)",
        ],
        "odds_ratio": [
            r"odds\s+ratio[:\s=~]*([\d]+\.?[\d]*)",
            r"\bOR[:\s=~]*([\d]+\.?[\d]*)",
        ],
        "risk_ratio": [
            r"risk\s+ratio[:\s=~]*([\d]+\.?[\d]*)",
            r"\bRR[:\s=~]*([\d]+\.?[\d]*)",
            r"relative\s+risk[:\s=~]*([\d]+\.?[\d]*)",
        ],
        "rmst_difference": [
            r"RMST\s+difference[:\s=~]*(-?[\d]+\.?[\d]*)",
            r"restricted\s+mean\s+survival\s+time\s+difference[:\s=~]*(-?[\d]+\.?[\d]*)",
        ],
        "ate": [
            r"\bATE[:\s=~]*(-?[\d]+\.?[\d]*)",
            r"average\s+treatment\s+effect[:\s=~]*(-?[\d]+\.?[\d]*)",
        ],
        "e_value": [
            r"E-value[:\s=~]*([\d]+\.?[\d]*)",
            r"\be[\s-]?value[:\s=~]*([\d]+\.?[\d]*)",
        ],
    }

    deviations: list[str] = []
    matched = 0

    for name, expected_val in ground_truth.items():
        patterns = ESTIMATE_PATTERNS.get(name, [])
        if not patterns:
            # Fallback: search for "name = value" generically
            safe_name = re.escape(name.replace("_", " "))
            patterns = [rf"{safe_name}[:\s=~]*(-?[\d]+\.?[\d]*)"]

        found_value = None
        for pat in patterns:
            m = re.search(pat, combined, re.IGNORECASE)
            if m:
                found_value = float(m.group(1))
                break

        if found_value is None:
            deviations.append(f"{name}: not found in output (expected {expected_val})")
            continue

        matched += 1
        rel_dev = (
            abs(found_value)
            if expected_val == 0
            else abs(found_value - expected_val) / abs(expected_val)
        )
        if rel_dev > TOLERANCE:
            deviations.append(
                f"{name}: reported {found_value}, expected {expected_val} "
                f"(deviation {rel_dev:.1%})"
            )

    if deviations:
        return Feedback(
            name="estimate_deviation",
            value=False,
            rationale="; ".join(deviations),
        )
    if matched == 0:
        return Feedback(
            name="estimate_deviation",
            value=False,
            rationale=f"None of the {len(ground_truth)} ground-truth estimates found in output.",
        )
    return Feedback(
        name="estimate_deviation",
        value=True,
        rationale=f"All {matched} reported estimates within {TOLERANCE:.0%} of ground truth.",
    )


# ── Level 2: Binary LLM Judges ─────────────────────────────────────────────
#
# NOTE: databricks-gpt-5-mini does not support response_schema or
# temperature!=1.  We call the endpoint directly via the OpenAI SDK
# instead of using mlflow.genai.judges.make_judge.
#
# max_tokens must be >= 500 because gpt-5-mini is a reasoning model
# that consumes tokens for internal chain-of-thought before emitting
# the visible answer.

JUDGE_MODEL = "databricks-gpt-5-mini"
JUDGE_MAX_TOKENS = 1000


def _get_judge_client():
    """Lazy-init OpenAI client pointing at the Databricks serving proxy."""
    creds = mlflow.utils.databricks_utils.get_databricks_host_creds()
    return openai.OpenAI(
        base_url=f"{creds.host}/serving-endpoints",
        api_key=creds.token,
    )


def _call_judge(system_prompt: str, inputs: dict, outputs: dict) -> bool:
    """Send a yes/no grading prompt and return True iff the answer starts with 'yes'."""
    client = _get_judge_client()
    user_msg = (
        f"Task:\n{json.dumps(inputs, default=str)}\n\n"
        f"Outputs:\n{json.dumps(outputs, default=str)}"
    )
    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=JUDGE_MAX_TOKENS,
    )
    answer = resp.choices[0].message.content.strip().lower()
    return answer.startswith("yes")


TASK_COMPLETION_PROMPT = """\
You are grading whether an agent session completed a real-world evidence (RWE)
comparative effectiveness research task correctly.

Grading rules:
- Grade only claims checkable from the text (method soundness,
  internal consistency of reported numbers, correct use of RWE terminology).
- The statistical approach must be reasonable for comparative effectiveness
  research (e.g., propensity score adjustment for confounding, appropriate
  weighting scheme, correct estimator for the outcome type).
- Numbers reported must be internally consistent with the described outputs.
- The session must have addressed confounding by indication (treatment
  assignment correlated with patient severity). An unadjusted comparison
  that ignores confounding is a failure.
- Partial completion counts as failure.
- For tasks requiring E-values: the E-value formula must be
  E = RR + sqrt(RR * (RR - 1)) for RR >= 1.
- For tasks requiring doubly robust estimation: both a propensity score
  model AND an outcome model must be used.
- For survival tasks: the Cox model must be weighted (IPW applied), not
  unweighted, and the proportional hazards assumption must be tested.
- For target trial emulation: cloning (all patients under both strategies),
  censoring for deviation, and censoring weights are all required.

Answer with exactly one word: 'yes' or 'no'.
"""

TOOL_USE_PROMPT = """\
Review the agent's recorded actions (field: action_log in Outputs) for the
RWE task.

Pass only if:
- Tools/steps match the task's requirements (e.g., data loaded before
  analysis, propensity scores estimated before matching/weighting,
  balance assessed after adjustment, effect estimated after balance
  confirmed).
- Order is sensible (e.g., load data -> estimate PS -> adjust -> check
  balance -> estimate effect -> sensitivity analysis).
- No redundant or irrelevant calls.
- The correct Python libraries are used (sklearn for PS, statsmodels for
  regression, lifelines for survival).
- For survival analysis: weighted Cox model fitted, not just KM curves.
- For target trial emulation: cloning and censoring steps present, not
  just a simple treatment comparison.

Answer with exactly one word: 'yes' or 'no'.
"""


@scorer
def task_completion_judge(inputs: dict, outputs: dict) -> Feedback:
    """LLM judge: did the session produce a methodologically sound RWE analysis?

    Judge errors propagate: MLflow records them as a missing value, which
    extract_scores rejects, instead of a silent task failure.
    """
    return Feedback(name="task_completion", value=_call_judge(TASK_COMPLETION_PROMPT, inputs, outputs))


@scorer
def tool_use_judge(inputs: dict, outputs: dict) -> Feedback:
    """LLM judge: were the right tools/steps used in the right order?"""
    return Feedback(name="tool_use_quality", value=_call_judge(TOOL_USE_PROMPT, inputs, outputs))


# ── Scorer Assembly ────────────────────────────────────────────────────────

scorers = [
    artifact_produced,          # Level 1
    no_forbidden_content,       # Level 1
    methodology_keywords,      # Level 1
    balance_reported,           # Level 1
    estimate_deviation,         # Level 1
    sensitivity_analysis_reported,  # Level 1
    task_completion_judge,      # Level 2
    tool_use_judge,             # Level 2, process
]


if __name__ == "__main__":
    # Quick smoke test on a dummy row
    row = {
        "inputs": {"query": "test", "task_id": "rwe-001"},
        "outputs": {
            "response": "Propensity score matching with logistic regression, caliper 0.2, SMD balanced",
            "action_log": "Loaded CSV -> Estimated PS via logistic regression -> Nearest-neighbor matching -> Balance table",
        },
        "expectations": {
            "expected_facts": ["PS estimated", "balance table"],
            "forbidden_patterns": ["fabricated.*data"],
        },
    }

    import json

    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment("/Users/yen.low@databricks.com/skill-eval-rwe-cohortstudy")

    result = mlflow.genai.evaluate(data=[row], scorers=scorers)
    df = result.tables["eval_results"]
    print(json.dumps(df.to_dict(orient="records"), indent=2, default=str))
