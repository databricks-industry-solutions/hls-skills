#!/usr/bin/env python3
"""
Scorers for the accelerators skill evaluation.

Level 1 (deterministic @scorer): artifact_produced, steers_to_accelerator, no_forbidden_content.
Level 2 (binary LLM judges): precise_next_step, factually_grounded.

Outputs are the markdown answers Genie Code saved per task (outputs["response"]).

Import rules (MLflow 3, not MLflow 2):
    pip install "mlflow[databricks]>=3.5.0"
"""

import re
from typing import Literal

from mlflow.entities import Feedback
from mlflow.genai.judges import make_judge
from mlflow.genai.scorers import scorer

JUDGE_MODEL = "databricks:/databricks-gpt-5-mini"

# ── Level 1: Deterministic Scorers ─────────────────────────────────────────


@scorer
def artifact_produced(outputs: dict) -> bool:
    """Pass if Genie Code saved a non-empty answer for the task."""
    return bool(str(outputs.get("response", "")).strip())


@scorer
def steers_to_accelerator(outputs: dict, expectations: dict) -> Feedback:
    """Pass if every required pattern group matches at least once.

    expectations.required_patterns is a list of groups; each group is a list of
    regex alternatives (case-insensitive). All groups must match.
    """
    response = str(outputs.get("response", ""))
    for group in expectations.get("required_patterns", []):
        if not any(re.search(p, response, re.IGNORECASE) for p in group):
            return Feedback(name="steers_to_accelerator", value=False, rationale=f"No match for any of {group}")
    return Feedback(name="steers_to_accelerator", value=True)


@scorer
def no_forbidden_content(outputs: dict, expectations: dict) -> Feedback:
    """Pass if no forbidden pattern appears in the response."""
    response = str(outputs.get("response", ""))
    for pattern in expectations.get("forbidden_patterns", []):
        if re.search(pattern, response, re.IGNORECASE):
            return Feedback(name="no_forbidden_content", value=False, rationale=f"Forbidden pattern found: {pattern}")
    return Feedback(name="no_forbidden_content", value=True)


# ── Level 2: Binary LLM Judges ─────────────────────────────────────────────

precise_next_step = make_judge(
    name="precise_next_step",
    instructions="""
You are grading whether an assistant's answer leaves the user with a precise next step.

User request: {{ inputs }}
Assistant answer: {{ outputs }}

Grading rules:
- Pass only if the answer ends with at least one concrete action the user can take now:
  a command or code they can run, or a specific action a named role (for example a
  workspace admin) must take.
- A list of links or "see the documentation" with no concrete action is a failure.
- Grade only what is in the answer text. Do not assume files or code that are not shown.

Answer with exactly one word: 'yes' or 'no'.
""",
    feedback_value_type=Literal["yes", "no"],
    model=JUDGE_MODEL,
)

factually_grounded = make_judge(
    name="factually_grounded",
    instructions="""
You are grading whether an assistant's answer about Databricks solution accelerators is
consistent with known facts.

User request: {{ inputs }}
Assistant answer: {{ outputs }}
Known facts and guidelines: {{ expectations }}

Grading rules:
- Fail if the answer contradicts any known fact (for example claims a feature exists
  that the facts say is not available, or gives a setting the facts say does not work).
- Fail if the answer breaks any guideline.
- Missing facts are acceptable unless a guideline requires them.

Answer with exactly one word: 'yes' or 'no'.
""",
    feedback_value_type=Literal["yes", "no"],
    model=JUDGE_MODEL,
)

scorers = [artifact_produced, steers_to_accelerator, no_forbidden_content, precise_next_step, factually_grounded]
