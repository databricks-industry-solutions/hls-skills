"""MLflow scorers for the integrated bulk RNA-seq and enrichment benchmark."""

from __future__ import annotations

import re
from typing import Literal

from mlflow.entities import Feedback
from mlflow.genai.judges import make_judge
from mlflow.genai.scorers import ExpectationsGuidelines, scorer


@scorer
def required_artifacts_present(outputs: dict, expectations: dict) -> Feedback:
    actual = {str(name) for name in outputs.get("artifacts", [])}
    required = {str(name) for name in expectations.get("required_artifacts", [])}
    missing = sorted(required - actual)
    return Feedback(
        name="required_artifacts_present",
        value=not missing,
        rationale="All required artifacts present" if not missing else f"Missing: {missing}",
    )


@scorer
def required_actions_present(outputs: dict, expectations: dict) -> Feedback:
    evidence = " ".join(
        [
            str(outputs.get("response", "")),
            str(outputs.get("action_log", "")),
            str(outputs.get("notebook_source", "")),
        ]
    ).lower()
    required = [str(token) for token in expectations.get("required_action_tokens", [])]
    missing = [token for token in required if token.lower() not in evidence]
    return Feedback(
        name="required_actions_present",
        value=not missing,
        rationale="All required actions evidenced" if not missing else f"Missing: {missing}",
    )


@scorer
def no_forbidden_patterns(outputs: dict, expectations: dict) -> Feedback:
    evidence = " ".join(
        [
            str(outputs.get("response", "")),
            str(outputs.get("action_log", "")),
            str(outputs.get("notebook_source", "")),
        ]
    )


scientific_method_judge = make_judge(
    name="scientific_method",
    instructions="""
You are grading the scientific method described in an RNA-seq agent session.

Task: {{ inputs }}
Session evidence, including the executed task-specific notebook source: {{ outputs }}
Expected scientific facts and guidelines: {{ expectations }}

Pass only if the evidence describes a coherent count-based differential-expression
workflow and a suitable downstream pathway-enrichment method. Fail if it substitutes
a generic test for count modeling, mishandles orientation or covariates, uses
incompatible gene identifiers, chooses ORA when a complete ranked table is available
without justification, or confuses DE FDR with GSEA FDR. Grade only claims visible in
the provided evidence; artifact existence is scored separately.

Answer exactly 'yes' or 'no'.
""",
    feedback_value_type=Literal["yes", "no"],
    model="databricks:/databricks-gpt-5-mini",
)


scorers = [
    required_artifacts_present,
    required_actions_present,
    no_forbidden_patterns,
    notebook_source_valid,
    ExpectationsGuidelines(),
    scientific_method_judge,
]
