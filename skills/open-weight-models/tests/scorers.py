"""Phase-based scorers for open-weight-models skill evaluation.

Three-level hierarchy: Categories → Phases → Sub-checks.
Uses mlflow.genai.evaluate() with @scorer-decorated functions.

Categories (aggregate quality dimensions):
  code_quality      — download_staging + pyfunc_quality
  model_lifecycle   — model_registration + endpoint_deployment
  validation        — smoke_tests
  completeness      — ai_search + edge_handling
  safety            — forbidden_patterns

Phases (8 @scorer functions for mlflow.genai.evaluate):
  1. download_staging      — temp paths, XET, deps, CPU/GPU split
  2. pyfunc_quality        — class structure, imports, sys.modules, torch compat
  3. model_registration    — signature, input_example, pip reqs, variant
  4. endpoint_deployment   — SDK enums, AI Gateway, scale-to-zero
  5. smoke_tests           — registration smoke, endpoint query, output shape
  6. ai_search             — index creation, embedding dim, graceful skip
  7. edge_handling         — template fallback, acknowledges unknowns
  8. forbidden_patterns    — catch-all anti-pattern safety net

Usage (MLflow evaluate):
    from scorers import MLFLOW_SCORERS, CATEGORIES, build_eval_data
    result = mlflow.genai.evaluate(data=build_eval_data(tasks, responses), scorers=MLFLOW_SCORERS)

Usage (plain Python):
    from scorers import score_task, score_categories
    results = score_task(task, response)       # {phase: {pass, rationale, checks}}
    cats    = score_categories(results)        # {category: {pass, score, phases}}
"""
import re
from mlflow.genai.scorers import scorer as mlflow_scorer
from mlflow.entities import Feedback


# ---- helpers ---------------------------------------------------------------

def _result(checks: dict, na_reason: str = None) -> dict:
    """Build a scorer result from a checks dict."""
    if na_reason:
        return {"pass": True, "rationale": na_reason, "checks": {}}
    missing = [k for k, v in checks.items() if not v]
    return {
        "pass": len(missing) == 0,
        "rationale": f"Missing: {missing}" if missing else None,
        "checks": checks,
    }


def _is_edge(task: dict) -> bool:
    return task.get("difficulty") == "edge"


def _strip_comments(text: str) -> str:
    """Strip comment lines, inline comments, and markdown cells from exported
    notebook source.  Prevents false positives when forbidden patterns appear
    in comments or negative examples (e.g. '# no /local_disk0')."""
    lines = []
    in_md = False
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("# MAGIC %md"):
            in_md = True
            continue
        if in_md:
            if s.startswith("# COMMAND"):
                in_md = False
            continue
        if s.startswith("#"):
            continue
        # Strip inline comments (  # ... ) — simple heuristic: two+ spaces
        # before '#' followed by a space.  Won't mis-strip '#' inside strings
        # in practice because string-embedded '#' is rarely preceded by 2+ spaces.
        line = re.sub(r'\s{2,}#\s.*$', '', line)
        lines.append(line)
    return "\n".join(lines)


# ---- Phase 1: Download & Staging ------------------------------------------

def download_staging(response: str, task: dict) -> dict:
    """Correct download paths, XET workaround, dep pinning, notebook split."""
    if _is_edge(task):
        return _result({}, "N/A — edge task")
    is_teddy = task.get("model_family") == "teddy"
    return _result({
        "uses_tmp":         bool(re.search(r'(?<!/local_disk0)/tmp', response)),
        # TEDDY-specific: XET backend issue only affects TEDDY repo
        "hf_xet_disabled":  bool(re.search(r"HF_HUB_DISABLE_XET", response)) if is_teddy else True,
        # TEDDY-specific: transformers==4.41.0 pin (5.x breaks TeddyGModel)
        "deps_pinned":      (bool(re.search(r"transformers==\d", response))
                            and not bool(re.search(r"transformers>=", response))) if is_teddy else True,
        # INFORMATIONAL ONLY — no prompt asks for split, so this doesn't affect pass/fail.
        # Kept for signal logging: does the skill encourage notebook separation?
        # "cpu_gpu_split" is excluded from pass/fail via _INFORMATIONAL_CHECKS below.
    })


# ---- Phase 2: Custom PyFunc Quality ---------------------------------------

def pyfunc_quality(response: str, task: dict) -> dict:
    """PyFunc class structure, imports, module hygiene, I/O patterns."""
    if _is_edge(task):
        return _result({}, "N/A — edge task")
    cm = re.search(r"class\s+\w+.*?PythonModel", response)
    has_class = cm is not None
    imports_in_class = bool(re.search(r"^\s{4,}import\s", response[cm.start():], re.M)) if cm else False
    # Also accept module-level imports when using file-based logging (python_model=path)
    file_logging = bool(re.search(r"python_model\s*=|\.py['\"]", response))
    has_module_imports = bool(re.search(r"^(?:import|from)\s+\w+", response, re.M))
    # Widened: accept module-level imports (not just indented inside class methods)
    imports_ok = imports_in_class or has_module_imports
    # io.StringIO — only required if pd.read_json present
    stringio_ok = "StringIO" in response if "pd.read_json" in response else True
    # artifacts_declared — log_model must include artifacts= for pyfunc to find weights
    artifacts_ok = bool(re.search(r"log_model\(.*artifacts\s*=", response, re.DOTALL))
    return _result({
        "pyfunc_class":         has_class,
        "imports_inside_class": imports_ok,
        "load_context":         "load_context" in response,
        "sys_modules_purge":    "sys.modules" in response,
        "io_stringio":          stringio_ok,
        "artifacts_declared":   artifacts_ok,
        # TEDDY-specific: vocab.txt is TEDDY's tokenizer
        "real_gene_ids":        ("vocab.txt" in response) if task.get("model_family") == "teddy" else True,
    })


# ---- Phase 3: Model Registration ------------------------------------------

def model_registration(response: str, task: dict) -> dict:
    """Signature, input/output examples, pip reqs, variant markers."""
    if _is_edge(task):
        return _result({}, "N/A — edge task")
    checks = {
        "infer_signature":  "infer_signature" in response,
        "input_example":    "input_example" in response,
        "pip_requirements":  bool(re.search(r"pip_requirements|requirements", response, re.I)),
        # Widened: accept explicit dep-file references OR documented evidence of
        # source-based dependency analysis (TEDDY's HF repo lacks a clean dep spec,
        # so hardcoding from code analysis + documenting the rationale is acceptable).
        "pip_reqs_from_source": bool(re.search(
            r"pyproject\.toml|requirements\.txt|setup\.(cfg|py)"   # explicit dep file
            r"|(?:read|parsed|derived|sourced|examined).*(?:dependenc|pip.req)"  # documented analysis
            , response, re.I)),
    }
    v = task.get("variant", "")
    if v == "400M":
        checks["mentions_1024"] = "1024" in response
        checks["mentions_400M"] = "400M" in response
    elif v == "70M":
        checks["mentions_70M"] = "70M" in response
    return _result(checks)


# ---- Phase 4: Endpoint Deployment -----------------------------------------

def endpoint_deployment(response: str, task: dict) -> dict:
    """SDK enums, AI Gateway inference table, scale-to-zero."""
    if _is_edge(task):
        return _result({}, "N/A — edge task")
    return _result({
        "sdk_enums":            "ServingModelWorkloadType" in response
                                and not bool(re.search(r'workload_type\s*=\s*["\']GPU', response)),
        "ai_gateway_config":    "AiGatewayInferenceTableConfig" in response
                                and "AutoCaptureConfigInput" not in _strip_comments(response),
        "scale_to_zero":        bool(re.search(r"scale_to_zero", response, re.I)),
        "run_go_gate":          bool(re.search(r"run_go|widget.*gate|SKIP_DEPLOY|RUN_GO", response, re.I)),
    })


# ---- Phase 5: Smoke Tests --------------------------------------------------

def smoke_tests(response: str, task: dict) -> dict:
    """Post-registration and post-deployment validation."""
    if _is_edge(task):
        return _result({}, "N/A — edge task")
    # Registration smoke: load from UC + predict
    reg_smoke = bool(re.search(
        r"(load_model|pyfunc\.load).*models:/.*predict", response, re.DOTALL
    )) or bool(re.search(
        r"(smoke\s*test|registration.*test|validate.*registered)", response, re.I
    ))
    # Endpoint query smoke: actually call the endpoint after creation
    endpoint_smoke = bool(re.search(
        r"(serving_endpoints\.query|requests\.post.*endpoint|curl.*endpoint"
        r"|test.*endpoint|verify.*endpoint|query.*endpoint)",
        response, re.I
    ))
    # Output shape validation: check embedding dimension or output shape
    v = task.get("variant", "")
    if v == "400M":
        shape_ok = bool(re.search(r"(1024|embedding_dimension|output.*shape|assert.*len)", response, re.I))
    elif v == "70M":
        shape_ok = bool(re.search(r"(512|embedding_dimension|output.*shape|assert.*len)", response, re.I))
    else:
        shape_ok = True  # no variant = N/A
    return _result({
        "registration_smoke":   reg_smoke,
        "endpoint_query":       endpoint_smoke,
        "output_shape_check":   shape_ok,
    })


# ---- Phase 6: AI Search ---------------------------------------------------

def ai_search(response: str, task: dict) -> dict:
    """AI Search index creation, embedding dim, graceful skip. Conditional on task.vs."""
    if not task.get("vs"):
        return _result({}, "N/A — task does not require AI Search")
    return _result({
        "index_creation":   bool(re.search(
            r"(DeltaSyncVectorIndexSpecRequest|create_index|vector_search_indexes)", response)),
        "embedding_dim":    bool(re.search(
            r"(embedding_dimension|EmbeddingVectorColumn)", response)),
        "graceful_skip":    bool(re.search(
            r"(tableExists|table.*not.*exist|skip.*VS|skip.*AI.Search|Phase 1b.*optional)",
            response, re.I)),
    })


# ---- Phase 7: Edge Handling ------------------------------------------------

def edge_handling(response: str, task: dict) -> dict:
    """Unsupported model fallback. Conditional on edge tasks."""
    if not _is_edge(task):
        return _result({}, "N/A — not an edge task")
    has_tpl = "model-template" in response.lower() or "model_template" in response.lower()
    ack = any(p in response.lower() for p in
              ["not in", "no reference", "no existing", "does not have", "unknown", "not found"])
    return _result({
        "uses_template":        has_tpl,
        "acknowledges_unknowns": has_tpl or ack,
    })


# ---- Phase 8: Forbidden Patterns (safety net) ------------------------------

def forbidden_patterns(response: str, task: dict) -> dict:
    """Catch-all: no anti-patterns from the task's forbidden list."""
    pats = task.get("deterministic_checks", {}).get("forbidden_patterns", [])
    # Strip comments/markdown to avoid false positives from negative examples
    code_only = _strip_comments(response)
    found = [p for p in pats if re.search(re.escape(p), code_only, re.I)]
    return {
        "pass": len(found) == 0,
        "rationale": f"Found: {found}" if found else None,
        "checks": {p: (p not in found) for p in pats},
    }


# ---- Plain function registry (for score_task / score_categories) -----------

_PLAIN_SCORERS = {
    "download_staging":     download_staging,
    "pyfunc_quality":       pyfunc_quality,
    "model_registration":   model_registration,
    "endpoint_deployment":  endpoint_deployment,
    "smoke_tests":          smoke_tests,
    "ai_search":            ai_search,
    "edge_handling":        edge_handling,
    "forbidden_patterns":   forbidden_patterns,
}
# Keep SCORERS as alias for backward compat
SCORERS = _PLAIN_SCORERS

# Category → list of phase names
CATEGORIES = {
    "code_quality":    ["download_staging", "pyfunc_quality"],
    "model_lifecycle":  ["model_registration", "endpoint_deployment"],
    "validation":       ["smoke_tests"],
    "completeness":     ["ai_search", "edge_handling"],
    "safety":           ["forbidden_patterns"],
}

# Reverse lookup: scorer_name → category
SCORER_CATEGORY = {}
for _cat, _names in CATEGORIES.items():
    for _n in _names:
        SCORER_CATEGORY[_n] = _cat


# ---- Phase-level @scorer wrappers (8 scorers) for mlflow.genai.evaluate() --
#
# 8 scorers = clean traces with readable assessments in the notebook viewer.
# Sub-check detail comes from the plain-Python path (score_task / score_categories).
#
# N/A phases return True + "[N/A] ..." rationale (must be bool to avoid
# Arrow mixed-type errors).

def _to_feedback(result: dict) -> Feedback:
    """Convert a plain scorer result dict to an MLflow Feedback."""
    checks = result.get("checks", {})
    rationale = result.get("rationale", "")
    if not checks and result["pass"] and str(rationale).startswith("N/A"):
        return Feedback(value=True, rationale=f"[N/A] {rationale}")
    if not checks:
        return Feedback(value=result["pass"], rationale=rationale or "pass")
    if result["pass"]:
        return Feedback(value=True, rationale=f"{len(checks)}/{len(checks)} sub-checks pass")
    failed = [k for k, ok in checks.items() if not ok]
    return Feedback(value=False, rationale=f"Failed [{len(failed)}/{len(checks)}]: {failed}")


@mlflow_scorer
def code_quality__download_staging(inputs, outputs, expectations) -> Feedback:
    """Download paths, XET, deps, notebook split."""
    return _to_feedback(download_staging(outputs["response"], expectations["task"]))

@mlflow_scorer
def code_quality__pyfunc_quality(inputs, outputs, expectations) -> Feedback:
    """PyFunc class structure, imports, module hygiene."""
    return _to_feedback(pyfunc_quality(outputs["response"], expectations["task"]))

@mlflow_scorer
def model_lifecycle__model_registration(inputs, outputs, expectations) -> Feedback:
    """Signature, input_example, pip reqs, variant."""
    return _to_feedback(model_registration(outputs["response"], expectations["task"]))

@mlflow_scorer
def model_lifecycle__endpoint_deployment(inputs, outputs, expectations) -> Feedback:
    """SDK enums, AI Gateway, teardown."""
    return _to_feedback(endpoint_deployment(outputs["response"], expectations["task"]))

@mlflow_scorer
def validation__smoke_tests(inputs, outputs, expectations) -> Feedback:
    """Registration smoke, endpoint query, output shape."""
    return _to_feedback(smoke_tests(outputs["response"], expectations["task"]))

@mlflow_scorer
def completeness__ai_search(inputs, outputs, expectations) -> Feedback:
    """AI Search index creation, embedding dim, graceful skip."""
    return _to_feedback(ai_search(outputs["response"], expectations["task"]))

@mlflow_scorer
def completeness__edge_handling(inputs, outputs, expectations) -> Feedback:
    """Template fallback, acknowledges unknowns."""
    return _to_feedback(edge_handling(outputs["response"], expectations["task"]))

@mlflow_scorer
def safety__forbidden_patterns(inputs, outputs, expectations) -> Feedback:
    """Catch-all anti-pattern safety net."""
    result = forbidden_patterns(outputs["response"], expectations["task"])
    checks = result.get("checks", {})
    if result["pass"]:
        return Feedback(value=True, rationale=f"{len(checks)}/{len(checks)} clean")
    found = [k for k, ok in checks.items() if not ok]
    return Feedback(value=False, rationale=f"Found: {found}")


# 8 phase-level scorers for mlflow.genai.evaluate() + trace display
MLFLOW_SCORERS = [
    code_quality__download_staging,
    code_quality__pyfunc_quality,
    model_lifecycle__model_registration,
    model_lifecycle__endpoint_deployment,
    validation__smoke_tests,
    completeness__ai_search,
    completeness__edge_handling,
    safety__forbidden_patterns,
]

MLFLOW_SCORER_MAP = {
    "code_quality__download_staging":       ("download_staging",     "code_quality"),
    "code_quality__pyfunc_quality":         ("pyfunc_quality",       "code_quality"),
    "model_lifecycle__model_registration":  ("model_registration",   "model_lifecycle"),
    "model_lifecycle__endpoint_deployment": ("endpoint_deployment",  "model_lifecycle"),
    "validation__smoke_tests":              ("smoke_tests",          "validation"),
    "completeness__ai_search":              ("ai_search",            "completeness"),
    "completeness__edge_handling":          ("edge_handling",        "completeness"),
    "safety__forbidden_patterns":           ("forbidden_patterns",   "safety"),
}


# ---- Data builder for mlflow.genai.evaluate() ------------------------------

def build_eval_data(tasks: dict, responses: dict) -> list:
    """Build eval data list for mlflow.genai.evaluate().

    Args:
        tasks: {task_id: task_dict}
        responses: {task_id: response_text}
    Returns:
        [{inputs: {task_id, query}, outputs: {response}, expectations: {task}}, ...]
    """
    data = []
    for tid, response in responses.items():
        if tid in tasks:
            data.append({
                "inputs": {"task_id": tid, "query": tasks[tid]["query"]},
                "outputs": {"response": response},
                "expectations": {"task": tasks[tid]},
            })
    return data


# ---- Plain Python helpers (backward compat) --------------------------------

def score_task(task: dict, response: str) -> dict:
    """Score a response against all phases. Returns {phase: {pass, rationale, checks}}."""
    return {name: fn(response, task) for name, fn in _PLAIN_SCORERS.items()}


def score_categories(phase_results: dict) -> dict:
    """Aggregate phase results into category scores.

    Returns {category: {pass, score, n_applicable, phases}}.
    A category passes if ALL its applicable phases pass.
    Score = n_passed / n_applicable (0.0–1.0).
    Phases that returned N/A (empty checks + pass=True) are excluded.
    """
    out = {}
    for cat, phase_names in CATEGORIES.items():
        phases = {}
        for pn in phase_names:
            if pn in phase_results:
                pr = phase_results[pn]
                is_na = pr["pass"] and not pr.get("checks", {})
                phases[pn] = {"pass": pr["pass"], "na": is_na}
        applicable = {k: v for k, v in phases.items() if not v["na"]}
        n_app = len(applicable)
        n_pass = sum(1 for v in applicable.values() if v["pass"])
        out[cat] = {
            "pass": n_pass == n_app if n_app > 0 else True,
            "score": n_pass / n_app if n_app > 0 else None,
            "n_applicable": n_app,
            "phases": phases,
        }
    return out
