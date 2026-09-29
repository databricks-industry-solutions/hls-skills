"""Scorers for sc-rnaseq skill evaluation.

Deterministic scorers check the action_log and response for skill-specific
behaviours: MLflow setup, data-driven QC, inline plots, Ensembl handling,
.raw fallback, per-sample profiling, batch key selection, harmony, and
absence of forbidden patterns (static defaults).

LLM judges evaluate task completion and tool-use quality.

Export: `scorers` list — consumed by the scoring notebook.
"""

import re
from typing import Literal

from mlflow.genai.scorers import scorer, Correctness, ExpectationsGuidelines
from mlflow.genai.judges import make_judge
from mlflow.entities import Feedback


# ---------------------------------------------------------------------------
# Level 1 — Deterministic scorers
# ---------------------------------------------------------------------------

@scorer
def artifact_produced(outputs: dict) -> bool:
    """Pass if the session produced its primary artifact (notebook ran)."""
    return bool(outputs.get("result_table"))


@scorer
def mlflow_setup(outputs: dict) -> bool:
    """Pass if MLflow tracking was set up (skill Gate G5, default ON)."""
    log = (outputs.get("action_log", "") + " " + outputs.get("response", "")).lower()
    return any(kw in log for kw in ["mlflow", "start_run", "log_params", "set_experiment"])


@scorer
def data_driven_qc(outputs: dict) -> bool:
    """Pass if QC thresholds were data-driven (MAD/percentile), not static.

    The skill's Gate G2 requires computing MAD or percentile-based thresholds
    from the actual QC distributions and presenting them to the user.
    """
    log = (outputs.get("action_log", "") + " " + outputs.get("response", "")).lower()
    data_driven_kws = [
        "mad", "median absolute deviation", "percentile", "p95", "p5",
        "quantile", "data-driven", "data_driven", "iqr",
    ]
    return any(kw in log for kw in data_driven_kws)


@scorer
def no_forbidden_content(outputs: dict, expectations: dict) -> Feedback:
    """Pass if no forbidden pattern appears in the response/action_log.

    Checks expectations.forbidden_patterns — typically static textbook
    defaults like 'pct_counts_mt < 20' that indicate the skill's data-driven
    threshold gate was bypassed.
    """
    text = outputs.get("response", "") + " " + outputs.get("action_log", "")
    for pattern in expectations.get("forbidden_patterns", []):
        if re.search(pattern, text, re.IGNORECASE):
            return Feedback(
                name="no_forbidden_content",
                value=False,
                rationale=f"Forbidden pattern found: {pattern}",
            )
    return Feedback(name="no_forbidden_content", value=True)


@scorer
def inline_plots(outputs: dict) -> bool:
    """Pass if %matplotlib inline was added after restart.

    The skill requires this in the first code cell after restartPython()
    to ensure scanpy plots render in Databricks notebooks.
    """
    log = (outputs.get("action_log", "") + " " + outputs.get("response", "")).lower()
    return "matplotlib inline" in log or "%matplotlib" in log


@scorer
def markdown_narration(outputs: dict) -> bool:
    """Pass if markdown cells explaining decisions were included.

    The skill requires every decision cell (QC thresholds, batch key, cell
    types, MLflow setup) to have a preceding markdown cell with rationale.
    """
    log = (outputs.get("action_log", "") + " " + outputs.get("response", "")).lower()
    narration_kws = [
        "markdown", "rationale", "decision", "justification",
        "threshold", "confirmed", "proposed", "gate",
    ]
    return sum(1 for kw in narration_kws if kw in log) >= 2


@scorer
def required_artifacts_present(outputs: dict, expectations: dict) -> Feedback:
    """Pass if all required_artifacts are mentioned in action_log or response.

    Task-specific artifacts (e.g. 'ensembl_swap', 'raw_to_adata',
    'harmony_integration') are declared in expectations.required_artifacts.
    This scorer checks each artifact name appears as a substring in the
    combined output text.
    """
    text = (outputs.get("action_log", "") + " " + outputs.get("response", "")).lower()
    missing = []
    for artifact in expectations.get("required_artifacts", []):
        # Flexible matching: artifact name or close variant in text
        artifact_lower = artifact.lower()
        # Map artifact names to expected keywords
        keyword_map = {
            "umap_plot": ["umap"],
            "leiden_clusters": ["leiden"],
            "mlflow_run": ["mlflow"],
            "ensembl_swap": ["ensembl", "ensg", "swap", "var_names", "feature_name"],
            "nonzero_pct_mt": ["pct_counts_mt", "mitochondrial", "mt-"],
            "rmm_setup": ["rmm", "rapids memory manager", "rmm_cupy_allocator", "rmm.reinitialize"],
            "gpu_transfer": ["anndata_to_gpu", "anndata_to_GPU", "rsc.get", "gpu transfer", "to_gpu"],
            "per_sample_qc": ["per_sample", "per sample", "backed", "profile"],
            "batch_key_selection": ["batch_key", "batch key", "donor", "batch"],
            "harmony_integration": ["harmony", "batch correction", "integrate"],
        }
        kws = keyword_map.get(artifact_lower, [artifact_lower])
        if not any(kw in text for kw in kws):
            missing.append(artifact)
    if missing:
        return Feedback(
            name="required_artifacts_present",
            value=False,
            rationale=f"Missing artifacts: {', '.join(missing)}",
        )
    return Feedback(name="required_artifacts_present", value=True)


# ---------------------------------------------------------------------------
# Level 2 — LLM judges (binary: yes/no)
# ---------------------------------------------------------------------------

task_completion_judge = make_judge(
    name="task_completion",
    instructions="""
You are grading whether an AI agent session completed a single-cell RNA-seq
analysis task on Databricks.

Task given to the agent: {{ inputs }}
Session outputs: {{ outputs }}

Grading rules:
- The notebook must have loaded data, run QC, normalized, clustered, and produced a UMAP.
- The statistical approach must be reasonable for scRNA-seq (scanpy pipeline: QC -> normalize -> HVG -> PCA -> neighbors -> UMAP -> Leiden).
- If the task involved Ensembl IDs, the agent must have detected and swapped them before QC.
- If the task involved .raw, the agent must have used raw counts for reprocessing.
- If the task involved multi-sample data, per-sample QC and batch correction must have been performed.
- Partial completion (e.g., notebook crashed before UMAP) counts as failure.
- Numbers reported must be internally consistent with the described outputs.

Answer with exactly one word: 'yes' or 'no'.
""",
    feedback_value_type=Literal["yes", "no"],
    model="databricks:/databricks-gpt-5-mini",
)


tool_use_judge = make_judge(
    name="tool_use_quality",
    instructions="""
Review the agent's recorded actions in {{ outputs }} (field: action_log) for the task in {{ inputs }}.

Pass only if:
- Tools/steps match the task's requirements (scanpy pipeline steps in correct order),
- Data is loaded before analysis, QC before normalization, normalization before HVG/PCA,
- No redundant or irrelevant calls,
- MLflow tracking was set up early (after install),
- Inline plotting was enabled (%matplotlib inline),
- For multi-sample tasks: per-sample profiling before concatenation, batch key selected before integration.

Answer with exactly one word: 'yes' or 'no'.
""",
    feedback_value_type=Literal["yes", "no"],
    model="databricks:/databricks-gpt-5-mini",
)


# ---------------------------------------------------------------------------
# Scorer list — consumed by the scoring notebook
# ---------------------------------------------------------------------------

scorers = [
    artifact_produced,            # Level 1
    mlflow_setup,                 # Level 1
    data_driven_qc,               # Level 1
    no_forbidden_content,         # Level 1
    inline_plots,                 # Level 1
    markdown_narration,           # Level 1
    required_artifacts_present,   # Level 1
    Correctness(model="databricks:/databricks-gpt-5-mini"),  # Level 2, needs expectations
    task_completion_judge,        # Level 2
    tool_use_judge,               # Level 2
]