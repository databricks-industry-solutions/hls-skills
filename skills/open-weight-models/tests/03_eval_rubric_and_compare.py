# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# DBTITLE 1,Notebook Eval Comparison
# MAGIC %md
# MAGIC # Notebook Eval Comparison
# MAGIC
# MAGIC Compares **baseline** (skill OFF) vs **skill** (skill ON) notebook arms for the open-weight-models eval.
# MAGIC
# MAGIC Auto-discovers notebook pairs in the project directory by matching a **prefix** (model family)
# MAGIC against two **suffixes** (`Baseline` vs a skill-arm suffix). Scores each arm with `scorers.py`,
# MAGIC runs `compare_runs.py` for the ship-gate verdict, and produces a fixable sub-check breakdown
# MAGIC showing which gaps are already covered in the skill files vs truly missing.

# COMMAND ----------

# DBTITLE 1,Scoring Rubric
# MAGIC %md
# MAGIC ## Scoring Rubric
# MAGIC
# MAGIC Automated via `scorers.py` (8 phases, 21 sub-checks). Checks marked **\[T\]** are **TEDDY-only** — they auto-pass for other model families. All other checks are universal.
# MAGIC
# MAGIC > **Family gating**: `scorers.py` uses `task.model_family` to skip TEDDY-specific checks for scimilarity, geneformer, midnight, etc.
# MAGIC
# MAGIC ### Phase 1 — Download & Staging (`download_staging`)
# MAGIC
# MAGIC | Sub-check | What it tests | Skill source | Baseline likely? |
# MAGIC |---|---|---|---|
# MAGIC | `uses_tmp` | Writes to `/tmp`, not `/local_disk0` (Serverless compat) | SKILL.md §10, teddy.md §Compute | Maybe |
# MAGIC | `hf_xet_disabled` **\[T\]** | Sets `HF_HUB_DISABLE_XET=1` before importing `huggingface_hub` | SKILL.md §8, teddy.md §HF download | **No** — obscure HF backend issue |
# MAGIC | `deps_pinned` **\[T\]** | Pins `transformers==4.41.0` exactly (not `>=`) | SKILL.md §9, teddy.md §Dependencies | **No** — baseline uses `>=` or latest |
# MAGIC | ~~`cpu_gpu_split`~~ | ~~Separates download (CPU) from register/deploy (GPU) notebooks~~ | REMOVED §8, teddy.md §Notebook arch | **No** — baseline uses one notebook |
# MAGIC
# MAGIC ### Phase 2 — PyFunc Quality (`pyfunc_quality`)
# MAGIC
# MAGIC | Sub-check | What it tests | Skill source | Baseline likely? |
# MAGIC |---|---|---|---|
# MAGIC | `pyfunc_class` | Defines a `PythonModel` subclass | SKILL.md §4, teddy.md §Wrapper | Yes |
# MAGIC | `imports_inside_class` | All imports inside the class cell (serving container has no notebook globals) | SKILL.md §11, teddy.md §Imports | **No** — common mistake |
# MAGIC | `load_context` | Implements `load_context` for model loading | teddy.md §load\_context pattern | Yes |
# MAGIC | `sys_modules_purge` | Purges `teddy.*` from `sys.modules` before load | SKILL.md §11, teddy.md §Stale module cache | **No** — not intuitive |
# MAGIC | `io_stringio` | Wraps `pd.read_json` with `io.StringIO` (pandas 2.1+ compat) | SKILL.md §12, teddy.md §predict | **No** — pandas API change |
# MAGIC | `artifacts_declared` | `log_model()` includes `artifacts=` so pyfunc can find weights | Built-in ML skill | Maybe — often omitted |
# MAGIC | `real_gene_ids` **\[T\]** | Uses real Ensembl IDs from `vocab.txt`, not synthetic names | teddy.md §Input example, §Validation | **No** — baseline invents gene names |
# MAGIC
# MAGIC ### Phase 3 — Model Registration (`model_registration`)
# MAGIC
# MAGIC | Sub-check | What it tests | Skill source | Baseline likely? |
# MAGIC |---|---|---|---|
# MAGIC | `infer_signature` | Uses `mlflow.models.infer_signature` | Built-in ML skill | Yes |
# MAGIC | `input_example` | Provides `input_example` when logging | Built-in ML skill | Yes |
# MAGIC | `pip_requirements` | Specifies `pip_requirements` | teddy.md §Dependencies | Partial — may miss exact pins |
# MAGIC | `pip_reqs_from_source` | References `pyproject.toml`/`requirements.txt` for dep sourcing | SKILL.md §Dependencies | **No** — baseline guesses from imports |
# MAGIC | `mentions_70M` | References the 70M variant explicitly | teddy.md §Identity | Yes |
# MAGIC
# MAGIC ### Phase 4 — Endpoint Deployment (`endpoint_deployment`)
# MAGIC
# MAGIC | Sub-check | What it tests | Skill source | Baseline likely? |
# MAGIC |---|---|---|---|
# MAGIC | `sdk_enums` | Uses `ServingModelWorkloadType` enum, not string `"GPU_SMALL"` | Built-in model-serving skill | Maybe |
# MAGIC | `ai_gateway_config` | Uses `AiGatewayInferenceTableConfig` (not deprecated `AutoCaptureConfigInput`) | SKILL.md §AI Gateway, teddy.md §Registration | **No** — baseline uses old API or skips |
# MAGIC | `scale_to_zero` | Enables scale-to-zero | teddy.md §Deployment recommendation | Yes |
# MAGIC | `run_go_gate` | Widget gate (`SKIP_DEPLOY`/`RUN_GO`) for expensive operations | SKILL.md §Workflow | **No** — baseline runs unconditionally |
# MAGIC
# MAGIC ### Phase 5 — Smoke Tests (`smoke_tests`)
# MAGIC
# MAGIC | Sub-check | What it tests | Skill source | Baseline likely? |
# MAGIC |---|---|---|---|
# MAGIC | `registration_smoke` | Post-registration load + predict test | teddy.md §Validation checklist | Maybe |
# MAGIC | `endpoint_query` | Post-deployment endpoint query test | teddy.md §SDK query test | Maybe |
# MAGIC | `output_shape_check` | Validates embedding dim = 512 for 70M | teddy.md §Output, §Validation | **No** — must read `config.json` |
# MAGIC
# MAGIC ### Phase 6 — AI Search (`ai_search`)
# MAGIC
# MAGIC > **Conditional**: only scored when `task.vs == true` (oss-002, oss-003). Auto-passes as N/A for all other tasks.
# MAGIC
# MAGIC | Sub-check | What it tests | Skill source | Baseline likely? |
# MAGIC |---|---|---|---|
# MAGIC | `index_creation` | Creates a Delta Sync AI Search index (`DeltaSyncVectorIndexSpecRequest`, `create_index`, or `vector_search_indexes`) | teddy.md §AI Search index creation | **No** — baseline may skip VS entirely |
# MAGIC | `embedding_dim` | Specifies `embedding_dimension` or `EmbeddingVectorColumn` in index spec (512 for 70M, 1024 for 400M) | teddy.md §AI Search index creation, §Variant-aware naming | **No** — must know variant→dim mapping |
# MAGIC | `graceful_skip` | Handles missing source table gracefully (`tableExists`, skip logic) instead of crashing | teddy.md §Census generation, evalset guidelines | Maybe — depends on defensive coding |
# MAGIC
# MAGIC ### Phase 7 — Edge Handling (`edge_handling`)
# MAGIC
# MAGIC > **Conditional**: only scored when `task.difficulty == "edge"` (oss-008). Auto-passes as N/A for all other tasks.
# MAGIC
# MAGIC | Sub-check | What it tests | Skill source | Baseline likely? |
# MAGIC |---|---|---|---|
# MAGIC | `uses_template` | References `model-template.md` for an unknown model family | SKILL.md §Extension layer, model-template.md | **No** — baseline has no template awareness |
# MAGIC | `acknowledges_unknowns` | Explicitly states the model is not in the reference set ("not found", "no reference", etc.) | SKILL.md §Execution boundary | Maybe — may still attempt blind deploy |
# MAGIC
# MAGIC ### Phase 8 — Forbidden Patterns (`forbidden_patterns`)
# MAGIC
# MAGIC | Pattern | Why forbidden | Skill source |
# MAGIC |---|---|---|
# MAGIC | `/local_disk0` | Not available on Serverless | SKILL.md §10 |
# MAGIC | `transformers>=` | Resolves to 5.x, breaks `TeddyGModel` | SKILL.md §9, teddy.md §Dependencies |
# MAGIC | `ENSG00000FAKE` | Invented gene IDs produce degenerate embeddings | teddy.md §Input example |
# MAGIC | `AutoCaptureConfigInput` | Deprecated; use `AiGatewayInferenceTableConfig` | SKILL.md §AI Gateway |
# MAGIC | `workload_type="GPU` | String literal; must use SDK enum | Built-in model-serving skill |
# MAGIC
# MAGIC ### Development Log (eval metadata)
# MAGIC
# MAGIC Both prompts require a **"Development Log"** markdown cell before the export step. This cell documents every fix, debug iteration, and reversal that occurred during development — providing a quantitative comparison of effort between arms.
# MAGIC
# MAGIC **Where the logs live:**
# MAGIC
# MAGIC | Notebook | Cell | Title |
# MAGIC |---|---|---|
# MAGIC | `oss-002_TEDDY-70M+VS_Deploy_Baseline` | Cell 14 (second-to-last) | Development Log — Baseline Arm (No Skill) |
# MAGIC | `oss-002_TEDDY-70M+VS_Deploy_withSkills` | TBD (agent will create it) | Development Log |
# MAGIC
# MAGIC **What to compare:**
# MAGIC
# MAGIC | Metric | Baseline (observed) | Skill (expected) |
# MAGIC |---|---|---|
# MAGIC | Unique bugs | 12 | Fewer (skill eliminates ~7) |
# MAGIC | Fix iterations | 15 | Fewer |
# MAGIC | Cells needing fixes | 6 of 12 | Fewer |
# MAGIC | Model versions burned | 5 (v1–v5) | Fewer |
# MAGIC | Known limitations | Synthetic corpus (10 types, no Census) | Census-backed corpus (1K+ real cells) |
# MAGIC
# MAGIC > The dev log is **not scored automatically** by `scorers.py` — it's qualitative eval metadata for the human reviewer. The prompt wording is identical across both arms so any difference in the log is purely a function of how many issues each arm actually hit.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Expected diff signals — TEDDY (oss-001 through oss-003)
# MAGIC
# MAGIC Strongest → weakest:
# MAGIC
# MAGIC 1. **`transformers==4.41.0` exact pin** — 5.x breakage **\[T\]**
# MAGIC 2. **`HF_HUB_DISABLE_XET=1`** — obscure Xet/CAS backend error **\[T\]**
# MAGIC 3. **`AiGatewayInferenceTableConfig`** — HLS best-practice default
# MAGIC 4. **Code-bundle stripping** — strip `.safetensors` from `code_paths` **\[T\]**
# MAGIC 5. **`io.StringIO` wrapping** — pandas 2.1+ deprecation (conditional on `pd.read_json`)
# MAGIC 6. **Real gene IDs from `vocab.txt`** — not synthetic **\[T\]**
# MAGIC 7. **`sys.modules` purge** — stale-cache pitfall (universal)
# MAGIC 8. **CPU/GPU notebook split** — separate concerns (universal)
# MAGIC
# MAGIC ### Expected diff signals — AI Search / Vector Search (oss-002, oss-003 only)
# MAGIC
# MAGIC 1. **`DeltaSyncVectorIndexSpecRequest` with `TRIGGERED` pipeline** — correct index spec
# MAGIC 2. **`embedding_dimension=512` (70M) / `1024` (400M)** — variant-aware dim
# MAGIC 3. **Census-based reference corpus** (`cellxgene-census`, real cells) vs synthetic stubs
# MAGIC 4. **Gene ID remapping** (`adata.var["feature_id"]`) — Census default var\_names are numeric indices
# MAGIC 5. **CDF enablement** (`delta.enableChangeDataFeed`) on source table — required for Delta Sync
# MAGIC 6. **Graceful skip** — table-existence check before index creation
# MAGIC 7. **Self-retrieval eval scorer** — validates index with known embeddings
# MAGIC
# MAGIC ### Expected diff signals — Geneformer (oss-005, oss-006)
# MAGIC
# MAGIC 1. **Token dictionaries are pickle, not JSON** — `token_dictionary_gc30M.pkl` must be loaded with `pickle.load`, not parsed as text
# MAGIC 2. **TransformerEngine (TE) stubs** (Path B / BioNeMo only) — `geneformer.py` imports `transformer_engine.pytorch`; needs stub module in `load_context` since TE requires CUDA source build
# MAGIC 3. **`isatty()` crash in Model Serving** (Path A) — serving container's `StreamToLogger` lacks `isatty()`; must patch `sys.stdout` in `load_context`
# MAGIC 4. **`transformers<4.52.0` pin** — `get_head_mask` removed in 4.52; both paths break without the upper bound
# MAGIC 5. **`trust_remote_code=True`** (Path B) — NVIDIA checkpoint has custom model code in `geneformer.py`
# MAGIC 6. **Real Ensembl gene IDs from token dictionary** — not synthetic; tokenizer maps gene IDs → token IDs
# MAGIC 7. **Path A vs Path B architecture awareness** — model family has two distinct deployment paths with different wrappers, deps, and artifacts
# MAGIC 8. **Inference table name conflicts** — timestamp prefix to avoid collisions across model versions
# MAGIC
# MAGIC ### Expected diff signals — Scimilarity (oss-004)
# MAGIC
# MAGIC 1. **Zenodo download with retry/resume** — primary model source is a single tarball from Zenodo, not HF; needs `curl` with exponential backoff (30–60 min download)
# MAGIC 2. **`scimilarity` package via `code_paths`** — not pip-installable; must bundle from source repo, triggering file-based `python_model` logging
# MAGIC 3. **CPU-only deployment** — no GPU needed (unlike teddy/geneformer); `workload_type` should NOT request GPU
# MAGIC 4. **Cell gene alignment** (`align_dataset`) — preprocessing pipeline from `scimilarity.utils` must reorder gene columns to match model vocabulary
# MAGIC 5. **Three PyFunc models** (from GWB module) — embedder, annotator, and query interface have different wrappers
# MAGIC 6. **Parallel download optimization** — model + sample data can be downloaded concurrently with `ThreadPoolExecutor`
# MAGIC 7. **No `transformers` dependency** — scimilarity uses PyTorch + custom modules, not HuggingFace; no version-pinning pitfall
# MAGIC
# MAGIC ### Expected diff signals — Midnight (oss-007)
# MAGIC
# MAGIC > **TBD** — No model reference exists yet. Midnight is a pathology foundation model; diff signals will be added when the reference file is authored.
# MAGIC
# MAGIC ### Expected diff signals — Generic / Edge (oss-008, oss-009)
# MAGIC
# MAGIC > Edge tasks test template fallback and uncertainty acknowledgment, not model-specific knowledge. Diff signals are captured in the `edge_handling` phase checks (`uses_template`, `acknowledges_unknowns`).
# MAGIC
# MAGIC ### Universal checks (apply to all model families)
# MAGIC
# MAGIC | Check | Phase | Why universal |
# MAGIC |---|---|---|
# MAGIC | `uses_tmp` | download_staging | Serverless compat — all models |
# MAGIC | `pyfunc_class` | pyfunc_quality | Any custom model needs PythonModel |
# MAGIC | `load_context` | pyfunc_quality | Standard pyfunc weight loading |
# MAGIC | `artifacts_declared` | pyfunc_quality | log_model needs artifacts= |
# MAGIC | `sys_modules_purge` | pyfunc_quality | Custom module cache issue |
# MAGIC | `infer_signature` | model_registration | MLflow best practice |
# MAGIC | `input_example` | model_registration | MLflow best practice |
# MAGIC | `pip_reqs_from_source` | model_registration | Dep sourcing from project files |
# MAGIC | `sdk_enums` | endpoint_deployment | Avoid string literals for workload type |
# MAGIC | `ai_gateway_config` | endpoint_deployment | Use current API, not deprecated |
# MAGIC | `scale_to_zero` | endpoint_deployment | Cost safety |
# MAGIC | `run_go_gate` | endpoint_deployment | Widget gate for expensive ops |
# MAGIC | `registration_smoke` | smoke_tests | Pre-deploy validation |
# MAGIC | `endpoint_query` | smoke_tests | Post-deploy validation |
# MAGIC | ~~`cpu_gpu_split`~~ | ~~download_staging~~ | Removed — no prompt asks for split |
# MAGIC
# MAGIC ### Conditional checks (task-gated)
# MAGIC
# MAGIC | Check | Phase | Condition | Why conditional |
# MAGIC |---|---|---|---|
# MAGIC | `index_creation` | ai_search | `task.vs == true` | Only VS tasks need an index |
# MAGIC | `embedding_dim` | ai_search | `task.vs == true` | Dimension only matters with an index |
# MAGIC | `graceful_skip` | ai_search | `task.vs == true` | Table-existence guard for VS source table |
# MAGIC | `uses_template` | edge_handling | `task.difficulty == "edge"` | Only unknown-model tasks test template fallback |
# MAGIC | `acknowledges_unknowns` | edge_handling | `task.difficulty == "edge"` | Only edge tasks test explicit uncertainty |

# COMMAND ----------

# DBTITLE 1,Skills inventory
# --- Discover custom skills (toggleable) ---
import os, glob

NB_DIR = os.path.dirname(os.path.abspath(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
))
BASE = f"/Workspace{NB_DIR}"

skill_base = os.path.join(BASE, ".assistant", "skills")
custom_skills = []
for skill_dir in sorted(glob.glob(os.path.join(skill_base, "*"))):
    name = os.path.basename(skill_dir)
    if name.startswith("."):
        continue
    skill_md = os.path.join(skill_dir, "SKILL.md")
    skill_md_off = os.path.join(skill_dir, "SKILL.md.off")
    if os.path.exists(skill_md):
        custom_skills.append((name, "ACTIVE", skill_md))
    elif os.path.exists(skill_md_off):
        custom_skills.append((name, "DISABLED", skill_md_off))
    else:
        custom_skills.append((name, "NO SKILL.md", skill_dir))

print("=" * 70)
print("  SKILLS INVENTORY")
print("=" * 70)

print(f"\n--- Custom skills (toggleable via SKILL.md rename) ---")
print(f"  Location: {skill_base}/*/SKILL.md")
for name, status, path in custom_skills:
    icon = "\u2713" if status == "ACTIVE" else "\u2717" if status == "DISABLED" else "?"
    print(f"  {icon} {name:<30} {status}")
if not custom_skills:
    print("  (none found)")

print(f"\n--- Built-in skills (always active, NOT toggleable) ---")
print("  These are loaded by the assistant from the platform Skill Registry.")
print("  The baseline arm still has access to all of these.")
builtin_relevant = {
    "ML / Model Serving": [
        "machine-learning", "databricks-model-serving", "databricks-mlflow-evaluation",
        "mlflow", "feature-tables", "feature-views",
    ],
    "Compute / Environment": [
        "environment-management", "spark-connect", "air-migration",
        "databricks-execution-compute",
    ],
    "Data / SQL": [
        "data-sampling", "writing-sql", "databricks-dbsql",
        "system-tables", "vector-search",
    ],
    "Infrastructure": [
        "databricks-cli-public", "databricks-jobs", "databricks-bundles",
        "databricks-apps-python", "git",
    ],
    "Code Quality": [
        "diagnose-error", "fix-lints", "writing-unit-tests",
        "spark-api", "python-dev",
    ],
}
for category, skills in builtin_relevant.items():
    print(f"\n  {category}:")
    for s in skills:
        print(f"    \u2022 {s}")

print(f"\n--- Toggle helper ---")
print(f"  To disable a custom skill: rename SKILL.md \u2192 SKILL.md.off")
print(f"  To re-enable:              rename SKILL.md.off \u2192 SKILL.md")
print(f"  \u26a0 Renaming the FOLDER (e.g. _open-weight-models-off/) is unreliable \u2014")
print(f"    the assistant's */SKILL.md glob still matches.")
print(f"  \u26a0 Built-in skills cannot be disabled. Baseline comparisons")
print(f"    measure custom skill value ON TOP of built-in knowledge.")

# COMMAND ----------

# DBTITLE 1,Config + discover notebook pairs
import os, sys, json, base64, re
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ExportFormat, ObjectType

# --- Project paths ---
NB_DIR = os.path.dirname(os.path.abspath(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
))
BASE = f"/Workspace{NB_DIR}"
if BASE not in sys.path:
    sys.path.insert(0, BASE)

EVALSET_PATH = os.path.join(BASE, "evalset.json")
RESULTS_DIR = os.path.join(BASE, "results")
SKILL_DIR = os.path.join(BASE, ".assistant", "skills", "open-weight-models")

w = WorkspaceClient()

# --- Load evalset for model families + task mapping ---
with open(EVALSET_PATH) as f:
    evalset = json.load(f)

families = sorted(set(t["model_family"] for t in evalset["tasks"]))
task_by_family = {}
for t in evalset["tasks"]:
    task_by_family.setdefault(t["model_family"], []).append(t)

# --- Discover notebook pairs by prefix/suffix ---
# List all notebooks in the project directory
project_objects = w.workspace.list(NB_DIR)
nb_names = [obj.path.split("/")[-1] for obj in project_objects if obj.object_type == ObjectType.NOTEBOOK]

# Configurable suffixes — adjust if your naming convention differs
BASELINE_SUFFIX = "_Baseline"
SKILL_SUFFIXES = ["_withSkills", "_WithSkill", "_Skill"]  # try in order

def find_pairs(nb_names, baseline_suffix, skill_suffixes):
    """Match notebook pairs by shared prefix + different suffix.
    Also discovers versioned skill arms (_v2, _v3, ...) as separate pairs
    sharing the same baseline."""
    pairs = []
    baselines = [n for n in nb_names if n.endswith(baseline_suffix)]
    for bl in baselines:
        prefix = bl[: -len(baseline_suffix)].rstrip(" -_")
        for suf in skill_suffixes:
            # v1: exact match (no version suffix)
            v1_candidates = [n for n in nb_names
                             if n != bl and n.startswith(prefix) and n.endswith(suf)
                             and not re.search(r'_v\d+$', n)]  # exclude versioned
            if v1_candidates:
                pairs.append({
                    "prefix": prefix,
                    "baseline": bl,
                    "skill": v1_candidates[0],
                    "suffix_matched": suf,
                    "version": 1,
                })
            # vN: versioned variants (e.g., _withSkills_v2, _withSkills_v3)
            version_pat = re.compile(
                rf'^{re.escape(prefix)}.*{re.escape(suf)}_v(\d+)$'
            )
            for nb in nb_names:
                m = version_pat.match(nb)
                if m:
                    ver = int(m.group(1))
                    pairs.append({
                        "prefix": f"{prefix}_v{ver}",
                        "baseline": bl,
                        "skill": nb,
                        "suffix_matched": f"{suf}_v{ver}",
                        "version": ver,
                    })
            if v1_candidates:  # found at least v1 for this suffix, skip others
                break
    # Sort: base prefix first, then version
    pairs.sort(key=lambda p: (p['prefix'], p.get('version', 1)))
    return pairs

pairs = find_pairs(nb_names, BASELINE_SUFFIX, SKILL_SUFFIXES)

print(f"Project dir: {NB_DIR}")
print(f"Evalset:     v{evalset['version']}, {len(evalset['tasks'])} tasks, families: {families}")
print(f"Notebooks:   {len(nb_names)} found")
print(f"\nDiscovered {len(pairs)} pair(s):")
for i, p in enumerate(pairs):
    print(f"  [{i}] prefix='{p['prefix']}'")
    print(f"      baseline: {p['baseline']}")
    print(f"      skill:    {p['skill']}")

# --- Widgets ---
pair_labels = [p["prefix"] for p in pairs]
if pair_labels:
    dbutils.widgets.dropdown("pair", pair_labels[0], pair_labels, "Notebook pair")
dbutils.widgets.dropdown("task_id", evalset["tasks"][0]["task_id"],
                         [t["task_id"] for t in evalset["tasks"]], "Task ID")
print("\nWidgets created. Select pair + task_id above, then run remaining cells.")

# COMMAND ----------

# DBTITLE 1,Export selected pair
# Read widget selection
selected_prefix = dbutils.widgets.get("pair")

pair = next((p for p in pairs if p["prefix"] == selected_prefix), None)
if pair is None and len(pairs) == 1:
    pair = pairs[0]
    print(f"\u26a0 Widget value '{selected_prefix}' stale — auto-selected '{pair['prefix']}'")
elif pair is None:
    raise ValueError(
        f"No pair found for prefix '{selected_prefix}'. "
        f"Available: {[p['prefix'] for p in pairs]}. Re-run Cell 4 first."
    )

# Auto-infer task_id from pair prefix (e.g. "oss-001_TEDDY-70M_Deploy" -> "oss-001")
task_ids = [t["task_id"] for t in evalset["tasks"]]
TASK_ID = None
for tid in task_ids:
    if pair["prefix"].startswith(tid):
        TASK_ID = tid
        break
if TASK_ID is None:
    # Fallback to widget
    TASK_ID = dbutils.widgets.get("task_id")
    print(f"\u26a0 Could not infer task_id from prefix '{pair['prefix']}' — using widget value '{TASK_ID}'")
else:
    print(f"\u2713 Auto-inferred task_id='{TASK_ID}' from pair prefix")

print(f"Pair:    {pair['prefix']}")
print(f"Task:    {TASK_ID}")

def export_notebook(name):
    """Export notebook as SOURCE text via SDK."""
    path = f"{NB_DIR}/{name}"
    resp = w.workspace.export(path=path, format=ExportFormat.SOURCE)
    return base64.b64decode(resp.content).decode("utf-8")

baseline_text = export_notebook(pair["baseline"])
skill_text = export_notebook(pair["skill"])

# Save to results dirs
for arm, text in [("baseline", baseline_text), ("with_skill", skill_text)]:
    out_path = os.path.join(RESULTS_DIR, arm, f"{TASK_ID}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(text)

print(f"\nExported:")
print(f"  baseline   ({pair['baseline']}): {len(baseline_text):,} chars")
print(f"  with_skill ({pair['skill']}):    {len(skill_text):,} chars")
print(f"  Saved to results/{{arm}}/{TASK_ID}.txt")

# COMMAND ----------

# DBTITLE 1,Score both arms
import importlib, scorers
importlib.reload(scorers)  # pick up any edits to scorers.py
from scorers import score_task, score_categories, SCORERS, CATEGORIES

# Look up task definition from evalset
task = next(t for t in evalset["tasks"] if t["task_id"] == TASK_ID)
print(f"Task: {task['task_id']} | family: {task['model_family']} | "
      f"variant: {task.get('variant', '-')} | difficulty: {task['difficulty']}")
if task.get("vs"):
    print(f"  +AI Search (index required)")

# Score both arms
baseline_results = score_task(task, baseline_text)
skill_results = score_task(task, skill_text)

# Phase-level summary
print(f"\n{'Phase':<25} {'Baseline':>10} {'Skill':>10}")
print("-" * 47)
for phase in baseline_results:
    bl = "PASS" if baseline_results[phase]["pass"] else "FAIL"
    sk = "PASS" if skill_results[phase]["pass"] else "FAIL"
    marker = "" if bl == sk else (" << skill wins" if sk == "PASS" else " << baseline wins")
    print(f"  {phase:<23} {bl:>10} {sk:>10}{marker}")

bl_pass = sum(1 for r in baseline_results.values() if r["pass"])
sk_pass = sum(1 for r in skill_results.values() if r["pass"])
total = len(baseline_results)
print(f"\nPhases passed: baseline {bl_pass}/{total}, skill {sk_pass}/{total}")

# Category-level summary (from eval runner rubric)
baseline_cats = score_categories(baseline_results)
skill_cats = score_categories(skill_results)

print(f"\n{'Category':<20} {'Baseline':>10} {'Skill':>10}")
print("-" * 42)
for cat in CATEGORIES:
    bl_c = baseline_cats.get(cat, {})
    sk_c = skill_cats.get(cat, {})
    bl_s = f"{bl_c['score']:.0%}" if bl_c.get("score") is not None else "N/A"
    sk_s = f"{sk_c['score']:.0%}" if sk_c.get("score") is not None else "N/A"
    bl_icon = "PASS" if bl_c.get("pass") else "FAIL"
    sk_icon = "PASS" if sk_c.get("pass") else "FAIL"
    print(f"  {cat:<18} {bl_icon} {bl_s:>5} {sk_icon} {sk_s:>5}")

# Build sub-check level metrics for compare_runs (matches eval runner rubric)
def scores_to_metrics(phases):
    """Flatten phase/sub-check scores to {metric_key: bool} for compare_runs."""
    metrics = {}
    for phase_name, phase_data in phases.items():
        checks = phase_data.get("checks", {})
        if checks:
            for check_name, check_val in checks.items():
                metrics[f"{phase_name}/{check_name}"] = bool(check_val)
        else:
            metrics[phase_name] = bool(phase_data["pass"])
    return metrics

# --- Accumulate scores across tasks (read → merge → write) ---
def _load_scores(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

bl_path = os.path.join(RESULTS_DIR, "baseline_scores.json")
sk_path = os.path.join(RESULTS_DIR, "skill_scores.json")

baseline_scores = _load_scores(bl_path)
skill_scores = _load_scores(sk_path)

baseline_scores[TASK_ID] = scores_to_metrics(baseline_results)
skill_scores[TASK_ID] = scores_to_metrics(skill_results)

for path, scores in [(bl_path, baseline_scores), (sk_path, skill_scores)]:
    with open(path, "w") as f:
        json.dump(scores, f, indent=2)

print(f"Scores saved — {len(baseline_scores)} task(s) in baseline, {len(skill_scores)} in skill")

# COMMAND ----------

# DBTITLE 1,Run comparison (ship gate)
from compare_runs import compare, format_text, format_markdown

difficulty = {t["task_id"]: t["difficulty"] for t in evalset["tasks"]}
comp = compare(baseline_scores, skill_scores, difficulty=difficulty)

print(format_text(comp))
print()
print(format_markdown(comp))

# COMMAND ----------

# DBTITLE 1,Detailed sub-check breakdown
# Collect all sub-checks across both arms, grouped by phase
print(f"{'Phase':<25} {'Sub-check':<25} {'Baseline':>10} {'Skill':>10} {'Delta':>15}")
print("=" * 87)

all_deltas = []  # collect for fixable analysis

for phase in baseline_results:
    bl_r = baseline_results[phase]
    sk_r = skill_results[phase]
    bl_checks = bl_r.get("checks") or {}
    sk_checks = sk_r.get("checks") or {}

    # Phase header
    bl_phase = "PASS" if bl_r["pass"] else "FAIL"
    sk_phase = "PASS" if sk_r["pass"] else "FAIL"
    print(f"\n  {phase:<23} {'':25} {bl_phase:>10} {sk_phase:>10}")

    if not bl_checks and not sk_checks:
        rationale = bl_r.get("rationale", "")
        if rationale:
            print(f"  {'':25} {'('+rationale+')':25}")
        continue

    all_keys = list(dict.fromkeys(list(bl_checks) + list(sk_checks)))
    for key in all_keys:
        bl_val = bl_checks.get(key)
        sk_val = sk_checks.get(key)
        bl_str = "pass" if bl_val else "FAIL"
        sk_str = "pass" if sk_val else "FAIL"

        if bl_val == sk_val:
            delta = "same" if bl_val else "both fail"
        elif sk_val and not bl_val:
            delta = "<< skill wins"
        else:
            delta = "<< baseline wins"

        print(f"  {'':25} {key:<25} {bl_str:>10} {sk_str:>10} {delta:>15}")

        all_deltas.append({
            "phase": phase,
            "check": key,
            "baseline": bl_val,
            "skill": sk_val,
            "delta": delta,
        })

# COMMAND ----------

# DBTITLE 1,Development log comparison
# --- Development log extraction & comparison ---
# Parses the "Development Log" markdown cell from each arm's exported text.
# Extracts summary metrics + per-fix entries for side-by-side comparison.
# Gracefully skips if either arm lacks a dev log.

def _extract_dev_log_cell(text):
    """Extract the actual dev log cell (not the prompt cell) from exported .py text.
    Requires 'Development Log' as a heading or DBTITLE — not just mentioned in body text."""
    cells = re.split(r'# COMMAND ----------', text)
    for cell in cells:
        # Skip the prompt cell
        if re.search(r'Paste into a.*fresh.*Genie Code', cell, re.I):
            continue
        # Require "Development Log" as a heading (# / ## / ###) or DBTITLE
        is_heading = bool(re.search(
            r'(?:DBTITLE.*Development Log|^#+\s*Development Log|# MAGIC #+\s*Development Log)',
            cell, re.I | re.M
        ))
        if not is_heading:
            continue
        lines = []
        for line in cell.strip().split('\n'):
            clean = re.sub(r'^# MAGIC\s?', '', line)
            clean = re.sub(r'^# DBTITLE.*', '', clean)
            lines.append(clean)
        return '\n'.join(lines).strip()
    return None

def _parse_dev_log_metrics(log_text):
    """Extract key metrics from the summary table in a dev log cell."""
    metrics = {}
    # Unique bugs
    m = re.search(r'[Uu]nique bugs.*?\|\s*(\d+)', log_text)
    if m: metrics['unique_bugs'] = int(m.group(1))
    # Total fix iterations
    m = re.search(r'[Ff]ix iterations.*?\|\s*(\d+)', log_text)
    if m: metrics['fix_iterations'] = int(m.group(1))
    # Cells requiring fixes
    m = re.search(r'[Cc]ells.*?fix.*?\|\s*(\d+)', log_text)
    if m: metrics['cells_fixed'] = int(m.group(1))
    # Model versions (burned/created)
    m = re.search(r'[Mm]odel versions.*?\|\s*(\d+)', log_text)
    if m: metrics['model_versions'] = int(m.group(1))
    # Count individual fix entries ("### Fix N" or table rows "| N |")
    fix_headings = re.findall(r'### Fix \d+', log_text)
    fix_table_rows = re.findall(r'\| \d+ \|', log_text)
    metrics['fix_entries_found'] = max(len(fix_headings), len(fix_table_rows))
    # Known limitations (extract raw text)
    m = re.search(r'[Kk]nown [Ll]imitation.*?\|\s*(.+?)\s*\|', log_text)
    if m: metrics['known_limitations'] = m.group(1).strip()
    return metrics

def _extract_fix_list(log_text):
    """Extract per-fix summaries as a list of dicts."""
    fixes = []
    # Format A: table rows  | # | Cell | Error | Root Cause | Iterations |
    table_rows = re.findall(
        r'\| (\d+) \| ([^|]+)\| ([^|]+)\| ([^|]+)\| (\d+) \|', log_text)
    if table_rows:
        for num, cell, error, cause, iters in table_rows:
            fixes.append({
                'fix_num': int(num), 'cell': cell.strip(),
                'error': error.strip()[:80], 'root_cause': cause.strip()[:80],
                'iterations': int(iters),
            })
        return fixes
    # Format B: ### Fix N — <title> (Cell X)
    blocks = re.split(r'### Fix (\d+)', log_text)
    for i in range(1, len(blocks), 2):
        num = int(blocks[i])
        body = blocks[i+1] if i+1 < len(blocks) else ''
        cell_m = re.search(r'\(Cell[s]? ([\d, ]+)\)', body)
        error_m = re.search(r'\*\*Error\*\*:?\s*(.+?)(?:\n|$)', body)
        cause_m = re.search(r'\*\*Root cause\*\*:?\s*(.+?)(?:\n|$)', body)
        attempts_m = re.search(r'\*\*Attempts\*\*:?\s*(\d+)', body)
        fixes.append({
            'fix_num': num,
            'cell': cell_m.group(1).strip() if cell_m else '?',
            'error': (error_m.group(1).strip()[:80] if error_m else '?'),
            'root_cause': (cause_m.group(1).strip()[:80] if cause_m else '?'),
            'iterations': int(attempts_m.group(1)) if attempts_m else 1,
        })
    return fixes

# --- Extract from both arms ---
bl_log = _extract_dev_log_cell(baseline_text)
sk_log = _extract_dev_log_cell(skill_text)

if not bl_log and not sk_log:
    print("\u26a0 Neither arm has a Development Log cell — skipping comparison.")
    dev_log_comparison = None
else:
    bl_metrics = _parse_dev_log_metrics(bl_log) if bl_log else {}
    sk_metrics = _parse_dev_log_metrics(sk_log) if sk_log else {}
    bl_fixes = _extract_fix_list(bl_log) if bl_log else []
    sk_fixes = _extract_fix_list(sk_log) if sk_log else []

    # Override fix_entries_found with actual parsed count (regex heuristic overcounts)
    bl_metrics['fix_entries_found'] = len(bl_fixes)
    sk_metrics['fix_entries_found'] = len(sk_fixes)

    # --- Side-by-side summary ---
    print("=" * 80)
    print("  DEVELOPMENT LOG COMPARISON")
    print("=" * 80)
    metric_labels = [
        ('unique_bugs',    'Unique bugs'),
        ('fix_iterations', 'Fix iterations'),
        ('cells_fixed',    'Cells needing fixes'),
        ('model_versions', 'Model versions burned'),
        ('fix_entries_found', 'Fix entries parsed'),
    ]
    print(f"\n  {'Metric':<25} {'Baseline':>10} {'Skill':>10} {'Delta':>12}")
    print("  " + "-" * 59)
    for key, label in metric_labels:
        bl_val = bl_metrics.get(key)
        sk_val = sk_metrics.get(key)
        bl_s = str(bl_val) if bl_val is not None else 'N/A'
        sk_s = str(sk_val) if sk_val is not None else 'N/A'
        if bl_val is not None and sk_val is not None:
            diff = sk_val - bl_val
            delta = f"{diff:+d}" if diff != 0 else "same"
            if diff < 0:
                delta += " \u2713"  # skill is better
        else:
            delta = ''
        print(f"  {label:<25} {bl_s:>10} {sk_s:>10} {delta:>12}")

    # Known limitations
    bl_lim = bl_metrics.get('known_limitations', '')
    sk_lim = sk_metrics.get('known_limitations', '')
    if bl_lim or sk_lim:
        print(f"\n  Known limitations:")
        if bl_lim: print(f"    BL: {bl_lim[:100]}")
        if sk_lim: print(f"    SK: {sk_lim[:100]}")

    # --- Per-fix comparison ---
    if bl_fixes or sk_fixes:
        print(f"\n  {'--- Baseline fixes ---':^80}")
        print(f"  {'#':<4} {'Cell':<10} {'Iters':>5}  Error")
        for f in bl_fixes:
            print(f"  {f['fix_num']:<4} {f['cell']:<10} {f['iterations']:>5}  {f['error']}")
        print(f"\n  {'--- Skill arm fixes ---':^80}")
        print(f"  {'#':<4} {'Cell':<10} {'Iters':>5}  Error")
        for f in sk_fixes:
            print(f"  {f['fix_num']:<4} {f['cell']:<10} {f['iterations']:>5}  {f['error']}")

    # Store for downstream cells
    dev_log_comparison = {
        'baseline': {'metrics': bl_metrics, 'fixes': bl_fixes, 'found': bl_log is not None},
        'skill':    {'metrics': sk_metrics, 'fixes': sk_fixes, 'found': sk_log is not None},
    }
    print(f"\n\u2713 dev_log_comparison stored for persist cell")

# COMMAND ----------

# DBTITLE 1,Fixable analysis
# --- Which failing sub-checks are already covered in the skill? ---
# Auto-resolve model reference file based on task family
model_family = task.get("model_family", "unknown")
model_ref_name = f"{model_family}.md"
model_ref_path = os.path.join(SKILL_DIR, "references", "models", model_ref_name)
skill_md_path = os.path.join(SKILL_DIR, "SKILL.md")

skill_texts = {}
for label, path in [("SKILL.md", skill_md_path), (model_ref_name, model_ref_path)]:
    # Try active path first, then .off (disabled) — analysis should reflect
    # what the skill CONTAINS, not whether it's currently active.
    for try_path in [path, path + ".off"]:
        try:
            with open(try_path) as f:
                skill_texts[label] = f.read()
            break
        except FileNotFoundError:
            continue
    else:
        skill_texts[label] = ""
print(f"Model reference: {model_ref_name} ({'found' if skill_texts[model_ref_name] else 'NOT FOUND'})")

# Patterns to detect coverage per sub-check
coverage_patterns = {
    # Phase 1: download_staging
    # --- Universal patterns (check SKILL.md + model ref) ---
    "uses_tmp":             [(model_ref_name, r"/tmp"), ("SKILL.md", r"/tmp|local_disk0")],
    "sys_modules_purge":    [(model_ref_name, r"sys\.modules"), ("SKILL.md", r"sys\.modules")],
    "imports_inside_class": [(model_ref_name, r"imports inside"), ("SKILL.md", r"import.*inside.*class")],
    "io_stringio":          [(model_ref_name, r"StringIO"), ("SKILL.md", r"StringIO")],
    "artifacts_declared":   [(model_ref_name, r"artifacts\s*="), ("SKILL.md", r"artifacts")],
    "pip_reqs_from_source": [(model_ref_name, r"pyproject\.toml|requirements\.txt"), ("SKILL.md", r"pyproject\.toml")],
    "ai_gateway_config":    [(model_ref_name, r"AiGateway"), ("SKILL.md", r"AI Gateway|AiGateway")],
    "run_go_gate":          [(model_ref_name, r"RUN_GO|widget.*gate"), ("SKILL.md", r"RUN_GO|widget.*gate")],
    "registration_smoke":   [(model_ref_name, r"smoke.test"), ("SKILL.md", r"smoke.test")],
    # --- Family-specific patterns (check model ref + SKILL.md) ---
    "hf_xet_disabled":      [(model_ref_name, r"HF_HUB_DISABLE_XET|XET"), ("SKILL.md", r"HF_HUB_DISABLE_XET|XET")],
    "deps_pinned":          [(model_ref_name, r"transformers==\d|pin.*(?:transform|version)"), ("SKILL.md", r"pin.*(?:transform|version)")],
    "cpu_gpu_split":        [(model_ref_name, r"two separate notebooks|split.*download"), ("SKILL.md", r"split.*download.*notebook")],
    "real_gene_ids":        [(model_ref_name, r"vocab\.txt|Ensembl|gene.dict|token.dict"), ("SKILL.md", r"vocab|tokenizer")],
    # --- Phase 6: ai_search (conditional on task.vs) ---
    "index_creation":       [(model_ref_name, r"DeltaSyncVectorIndexSpecRequest|create_index|vector_search_indexes"), ("SKILL.md", r"AI Search|vector.search")],
    "embedding_dim":        [(model_ref_name, r"embedding_dimension|EmbeddingVectorColumn"), ("SKILL.md", r"embedding.dim")],
    "graceful_skip":        [(model_ref_name, r"tableExists|table.*not.*exist|skip.*VS|graceful"), ("SKILL.md", r"graceful|skip")],
    # --- Phase 7: edge_handling ---
    "uses_template":        [("SKILL.md", r"model-template"), (model_ref_name, r"model-template")],
    "acknowledges_unknowns":[("SKILL.md", r"execution.boundary|ambiguous|stop and ask"), (model_ref_name, r"ambiguous")],
}

# Build fixable analysis table — fully dynamic (no hardcoded notes)
failing = [d for d in all_deltas if not d["baseline"] or not d["skill"]]

print(f"{'Sub-check':<25} {'BL':>4} {'SK':>4} {'In skill?':<20} {'Category':<22} Note")
print("=" * 115)

# Dynamic category buckets
skill_wins = []          # in skill + BL fail + SK pass
skill_wins_builtin = []  # NOT in skill + BL fail + SK pass (built-in or luck)
regressions = []         # BL pass + SK fail (true regression, regardless of coverage)
both_fail_covered = []   # BL fail + SK fail + in skill (skill didn't help)
both_fail_gap = []       # BL fail + SK fail + NOT in skill

for d in failing:
    check = d["check"]
    bl_pass = d["baseline"]
    sk_pass = d["skill"]
    bl = "pass" if bl_pass else "FAIL"
    sk = "pass" if sk_pass else "FAIL"

    # Check coverage in skill files
    found_in = []
    for label, pattern in coverage_patterns.get(check, []):
        if re.search(pattern, skill_texts.get(label, ""), re.I):
            found_in.append(label)

    coverage = ", ".join(found_in) if found_in else "NOT FOUND"
    in_skill = bool(found_in)

    # Classify dynamically based on actual BL/SK values
    if bl_pass and not sk_pass:
        category = "REGRESSION"
        note = f"BL passes, SK regressed{' (skill covers it!)' if in_skill else ''}"
        regressions.append(d)
    elif not bl_pass and sk_pass and in_skill:
        category = "skill win"
        note = "In skill + skill arm passes"
        skill_wins.append(d)
    elif not bl_pass and sk_pass and not in_skill:
        category = "win (built-in)"
        note = "Not in custom skill — built-in or emergent"
        skill_wins_builtin.append(d)
    elif not bl_pass and not sk_pass and in_skill:
        category = "both fail (covered)"
        note = "In skill but neither arm passes — skill not effective"
        both_fail_covered.append(d)
    elif not bl_pass and not sk_pass and not in_skill:
        category = "both fail (gap)"
        note = "Not in skill, neither arm passes"
        both_fail_gap.append(d)
    else:
        category = "???"
        note = f"Unexpected: BL={bl} SK={sk} in_skill={in_skill}"

    print(f"  {check:<23} {bl:>4} {sk:>4} {coverage:<20} {category:<22} {note}")

print(f"\n--- Summary (dynamic, per-task) ---")
print(f"  Skill wins (in skill, BL fail, SK pass):     {len(skill_wins)}")
for d in skill_wins:
    print(f"    \u2713 {d['phase']}/{d['check']}")
print(f"  Wins via built-in (not in custom skill):     {len(skill_wins_builtin)}")
for d in skill_wins_builtin:
    print(f"    \u2713 {d['phase']}/{d['check']}")
print(f"  Regressions (BL pass, SK fail):              {len(regressions)}")
for d in regressions:
    print(f"    \u2717 {d['phase']}/{d['check']}")
print(f"  Both fail, skill covers it:                  {len(both_fail_covered)}")
for d in both_fail_covered:
    print(f"    \u26a0 {d['phase']}/{d['check']}")
print(f"  Both fail, content gap:                      {len(both_fail_gap)}")
for d in both_fail_gap:
    print(f"    \u26a0 {d['phase']}/{d['check']}")
print(f"  Total failing sub-checks (either arm):        {len(failing)}")

# COMMAND ----------

# DBTITLE 1,Scorer refinement analysis
# --- Scorer refinement analysis ---
# Cross-reference each sub-check against actual eval results to identify
# checks that are misaligned, too strict, or missing.

import importlib
importlib.reload(__import__("scorers"))  # pick up any edits
from scorers import SCORERS

# Read scorers.py source for pattern inspection
with open(os.path.join(BASE, "scorers.py")) as f:
    scorer_source = f.read()

# --- Refinement registry ---
# Each entry: (verdict, issue, recommendation)
# Verdicts:
#   keep       = check is fine, no changes needed
#   widened    = scorer regex was broadened (less strict matching)
#   skill-fix  = skill content was updated to address a failure (scorer unchanged)
#   content-gap = check passes/fails based on built-in knowledge, not custom skill
#   soften     = check is too strict, needs relaxation
#   remove     = check should be removed
refinements = {
    # Phase 1: download_staging
    "uses_tmp":         ("keep",    None, None),
    "hf_xet_disabled":  ("keep",    None, None),
    "deps_pinned":      ("keep",    None, None),
    "cpu_gpu_split":    ("keep", None, None),  # softened in scorers.py

    # Phase 2: pyfunc_quality
    "pyfunc_class":         ("keep", None, None),
    "imports_inside_class": ("keep", None, None),  # widened in scorers.py
    "load_context":     ("keep", None, None),
    "sys_modules_purge":("skill-fix",
        "v1: Regression (BL pass, SK fail). v2: both pass — skill fix confirmed",
        "Skill: dual-site purge guidance in §11 + model refs (cell level + load_context with code blocks)"),
    "io_stringio":      ("keep", None, None),
    "artifacts_declared": ("keep", None, None),
    "real_gene_ids":    ("keep", None, None),

    # Phase 3: model_registration
    "infer_signature":  ("keep", None, None),
    "input_example":    ("keep", None, None),
    "pip_requirements": ("keep", None, None),
    "pip_reqs_from_source": ("widened",
        "v1: both-fail. v2: skill win — scorer widening + skill content confirmed",
        "Scorer: regex widened to accept setup.py + dep-analysis patterns (e.g. 'read/parsed ... dependencies')"),

    # Phase 4: endpoint_deployment
    "sdk_enums":            ("skill-fix",
        "v1+v2: SK pass via built-in model-serving skill (reinforced by custom skill §13)",
        "Skill: SDK enum guidance in §13 + model refs (ServingModelWorkloadType.GPU_SMALL snippet)"),
    "ai_gateway_config":    ("skill-fix",
        "v1: both-fail (agent skipped gateway entirely). v2: skill win — agent adopted full AiGatewayConfig. "
        "Also fixed scorer false positive (AutoCaptureConfigInput in comments)",
        "Skill: concrete AiGatewayConfig code block in §23 + model refs. "
        "Scorer: _strip_comments() before AutoCaptureConfigInput check"),
    "scale_to_zero":        ("keep", None, None),
    "run_go_gate":          ("keep", None, None),

    # Phase 5: smoke_tests
    "registration_smoke":   ("keep", None, None),
    "endpoint_query":       ("keep", None, None),
    "output_shape_check":   ("keep", None, None),

    # Phase 8: forbidden_patterns — all keep
}

# --- Proposed new checks ---
new_checks = []

# --- Build live status lookup from current eval results ---
# Maps sub-check name -> (bl_pass, sk_pass) for the CURRENT pair
live_status = {}
for d in all_deltas:
    live_status[d["check"]] = (d["baseline"], d["skill"])

# --- Print refinement table with live cross-reference ---
print(f"{'Sub-check':<25} {'Verdict':<12} {'Live status':<18} Issue")
print("=" * 110)

counts = {}
confirmed_count = 0
not_effective_count = 0
for check, (verdict, issue, rec) in sorted(refinements.items(), key=lambda x: x[1][0]):
    counts[verdict] = counts.get(verdict, 0) + 1
    if verdict == "keep":
        continue  # don't clutter output with passing checks

    # Cross-reference against current eval results
    if check in live_status:
        bl_ok, sk_ok = live_status[check]
        if verdict in ("skill-fix", "widened"):
            if sk_ok and not bl_ok:
                status = "\u2705 confirmed"
                confirmed_count += 1
            elif sk_ok and bl_ok:
                status = "\u2705 both pass"
                confirmed_count += 1
            elif not sk_ok and not bl_ok:
                status = "\u274c not effective"
                not_effective_count += 1
            else:
                status = "\u26a0 regressed"
                not_effective_count += 1
        else:
            sk_s = "pass" if sk_ok else "FAIL"
            bl_s = "pass" if bl_ok else "FAIL"
            status = f"BL={bl_s} SK={sk_s}"
    else:
        status = "(not in task)"

    print(f"  {check:<23} {verdict:<12} {status:<18} {issue}")
    if rec:
        print(f"  {'':23} {'':12} {'':18} \u2192 {rec}")
    print()

print(f"\n--- Existing checks: {len(refinements)} ---")
verdict_icons = {
    "keep": "\u2713", "soften": "\u26a0", "widen": "\u26a0", "widened": "\u26a0",
    "conditional": "\u26a0", "remove": "\u2717",
    "skill-fix": "\U0001f527", "content-gap": "\u2139",
}
for v in ["keep", "widened", "skill-fix", "content-gap", "soften", "widen", "conditional", "remove"]:
    if counts.get(v):
        icon = verdict_icons.get(v, "?")
        print(f"  {icon} {v}: {counts[v]}")
if confirmed_count or not_effective_count:
    print(f"\n  Live validation: {confirmed_count} confirmed, {not_effective_count} not yet effective")

# --- v1 vs v2 comparison (from manifest) ---
manifest_path = os.path.join(RESULTS_DIR, "manifest.json")
try:
    with open(manifest_path) as f:
        _manifest = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    _manifest = {"runs": []}

# Find all runs for the current task_id
task_runs = [r for r in _manifest["runs"] if r["task_id"] == TASK_ID]
if len(task_runs) > 1:
    print(f"\n{'='*110}")
    print(f"  PAIR COMPARISON — {TASK_ID} ({len(task_runs)} runs)")
    print(f"{'='*110}")
    print(f"  {'Pair':<40} {'SK Phases':>10} {'SK Wins':>8} {'BL Wins':>8} {'Regr':>6} "
          f"{'Bugs':>8} {'Iters':>8} {'Versions':>9}")
    print(f"  {'-'*100}")
    for r in task_runs:
        prefix = r.get("pair_prefix", "?")
        phases = r.get("phases", {})
        sk_pass = sum(1 for p in phases.values() if p.get("skill"))
        total_p = len(phases)
        sc = r.get("sub_check_summary", {})
        sw = sc.get("skill_wins", 0)
        bw = sc.get("baseline_wins", 0)
        # Regressions = baseline_wins in this context (BL pass, SK fail)
        dl = r.get("dev_log", {})
        sk_dl = dl.get("skill") or {}
        bugs = sk_dl.get("unique_bugs", "-")
        iters = sk_dl.get("fix_iterations", "-")
        versions = sk_dl.get("model_versions", "-")
        # Trim prefix for display
        short = prefix.replace(f"{TASK_ID}_", "")
        print(f"  {short:<40} {sk_pass:>5}/{total_p}    {sw:>5}    {bw:>5}  {bw:>5} "
              f"{str(bugs):>8} {str(iters):>8} {str(versions):>9}")

# --- Proposed new checks ---
print(f"\n--- Proposed new checks: {len(new_checks)} ---")
for phase, name, description, pattern in new_checks:
    bl_match = bool(re.search(pattern, baseline_text, re.I | re.M))
    sk_match = bool(re.search(pattern, skill_text, re.I | re.M))
    bl_str = "pass" if bl_match else "FAIL"
    sk_str = "pass" if sk_match else "FAIL"
    delta = ""
    if sk_match and not bl_match:
        delta = " << skill wins"
    elif bl_match and not sk_match:
        delta = " << baseline wins"
    print(f"  + {phase}/{name}")
    print(f"    {description}")
    print(f"    BL={bl_str}  SK={sk_str}{delta}")
    print()

# COMMAND ----------

# DBTITLE 1,Save run to manifest, per-task report, and cross-task summary
# --- Persist: manifest.json + per-task report + cross-task summary ---
from datetime import datetime, timezone
from compare_runs import format_text as _fmt_text

MANIFEST_PATH = os.path.join(RESULTS_DIR, "manifest.json")
REPORTS_DIR = os.path.join(RESULTS_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

def _load_manifest():
    try:
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"runs": []}

timestamp = datetime.now(timezone.utc).isoformat()

# ---- 1. Per-task markdown report (survives re-runs) ----------------------
lines = []
lines.append(f"# {TASK_ID} — Eval Report")
lines.append(f"")
lines.append(f"**Generated**: {timestamp}")
lines.append(f"**Evalset**: v{evalset['version']}")
lines.append(f"**Pair**: {pair['prefix']}")
lines.append(f"**Task**: {task['task_id']} | family: {task['model_family']} | "
             f"variant: {task.get('variant', '-')} | difficulty: {task['difficulty']} | "
             f"vs: {task.get('vs', False)}")
lines.append(f"**Baseline NB**: {pair['baseline']}")
lines.append(f"**Skill NB**: {pair['skill']}")
lines.append(f"")

# Phase summary
lines.append(f"## Phase Summary")
lines.append(f"")
lines.append(f"| Phase | Baseline | Skill | Delta |")
lines.append(f"| --- | --- | --- | --- |")
for phase in baseline_results:
    bl = "PASS" if baseline_results[phase]["pass"] else "FAIL"
    sk = "PASS" if skill_results[phase]["pass"] else "FAIL"
    delta = "same" if bl == sk else ("skill wins" if sk == "PASS" else "baseline wins")
    lines.append(f"| {phase} | {bl} | {sk} | {delta} |")
lines.append(f"")

# Category summary
lines.append(f"## Category Summary")
lines.append(f"")
lines.append(f"| Category | Baseline | Skill |")
lines.append(f"| --- | --- | --- |")
for cat in CATEGORIES:
    bl_c = baseline_cats.get(cat, {})
    sk_c = skill_cats.get(cat, {})
    bl_s = f"{bl_c['score']:.0%}" if bl_c.get("score") is not None else "N/A"
    sk_s = f"{sk_c['score']:.0%}" if sk_c.get("score") is not None else "N/A"
    lines.append(f"| {cat} | {bl_s} | {sk_s} |")
lines.append(f"")

# Sub-check breakdown
lines.append(f"## Sub-check Breakdown")
lines.append(f"")
lines.append(f"| Phase | Sub-check | Baseline | Skill | Delta |")
lines.append(f"| --- | --- | --- | --- | --- |")
for d in all_deltas:
    bl = "pass" if d["baseline"] else "FAIL"
    sk = "pass" if d["skill"] else "FAIL"
    lines.append(f"| {d['phase']} | {d['check']} | {bl} | {sk} | {d['delta']} |")
lines.append(f"")

# Ship gate
lines.append(f"## Ship Gate")
lines.append(f"")
if "comp" in dir():
    lines.append(f"```")
    lines.append(_fmt_text(comp))
    lines.append(f"```")
else:
    lines.append(f"Ship gate not run (no comp object).")
lines.append(f"")

# Dev log section (if available)
if dev_log_comparison is not None:
    lines.append(f"## Development Log Comparison")
    lines.append(f"")
    lines.append(f"| Metric | Baseline | Skill | Delta |")
    lines.append(f"| --- | --- | --- | --- |")
    _bl_m = dev_log_comparison['baseline']['metrics']
    _sk_m = dev_log_comparison['skill']['metrics']
    for key, label in [('unique_bugs', 'Unique bugs'), ('fix_iterations', 'Fix iterations'),
                       ('cells_fixed', 'Cells needing fixes'), ('model_versions', 'Model versions'),
                       ('fix_entries_found', 'Fix entries')]:
        bv = _bl_m.get(key, '-')
        sv = _sk_m.get(key, '-')
        if isinstance(bv, int) and isinstance(sv, int):
            d = sv - bv
            delta = f"{d:+d}" if d != 0 else "same"
        else:
            delta = ""
        lines.append(f"| {label} | {bv} | {sv} | {delta} |")
    lines.append(f"")
    # Per-fix tables
    for arm_label, arm_key in [('Baseline', 'baseline'), ('Skill', 'skill')]:
        fixes = dev_log_comparison[arm_key]['fixes']
        if fixes:
            lines.append(f"### {arm_label} Fixes")
            lines.append(f"")
            lines.append(f"| # | Cell | Iterations | Error |")
            lines.append(f"| --- | --- | --- | --- |")
            for fx in fixes:
                lines.append(f"| {fx['fix_num']} | {fx['cell']} | {fx['iterations']} | {fx['error'][:60]} |")
            lines.append(f"")
else:
    lines.append(f"## Development Log Comparison")
    lines.append(f"")
    lines.append(f"No development log found in either arm.")
    lines.append(f"")

# Skill wins summary
skill_wins_list = [d for d in all_deltas if d["skill"] and not d["baseline"]]
baseline_wins_list = [d for d in all_deltas if d["baseline"] and not d["skill"]]
both_fail_list = [d for d in all_deltas if not d["baseline"] and not d["skill"]]

lines.append(f"## Delta Summary")
lines.append(f"")
lines.append(f"* Skill wins: {len(skill_wins_list)}")
for d in skill_wins_list:
    lines.append(f"  * {d['phase']}/{d['check']}")
lines.append(f"* Baseline wins: {len(baseline_wins_list)}")
for d in baseline_wins_list:
    lines.append(f"  * {d['phase']}/{d['check']}")
lines.append(f"* Both fail: {len(both_fail_list)}")
for d in both_fail_list:
    lines.append(f"  * {d['phase']}/{d['check']}")
lines.append(f"")

report_path = os.path.join(REPORTS_DIR, f"{TASK_ID}_report.md")
with open(report_path, "w") as f:
    f.write("\n".join(lines))
print(f"\u2713 Report saved to {report_path}")

# ---- 2. Manifest record ---------------------------------------------------
run_record = {
    "timestamp":        timestamp,
    "evalset_version":  evalset["version"],
    "task_id":          TASK_ID,
    "pair_prefix":      pair["prefix"],
    "baseline_notebook": pair["baseline"],
    "skill_notebook":   pair["skill"],
    "report_path":      f"results/reports/{TASK_ID}_report.md",
    "task_meta": {
        "model_family":  task.get("model_family"),
        "variant":       task.get("variant"),
        "difficulty":    task.get("difficulty"),
        "vs":            task.get("vs", False),
    },
    "phases": {
        phase: {
            "baseline": baseline_results[phase]["pass"],
            "skill":    skill_results[phase]["pass"],
        }
        for phase in baseline_results
    },
    "categories": {
        cat: {
            "baseline": baseline_cats[cat]["pass"],
            "skill":    skill_cats[cat]["pass"],
            "baseline_score": baseline_cats[cat].get("score"),
            "skill_score":    skill_cats[cat].get("score"),
        }
        for cat in CATEGORIES
    },
    "sub_check_summary": {
        "total_checks":     len(all_deltas),
        "skill_wins":       len(skill_wins_list),
        "baseline_wins":    len(baseline_wins_list),
        "both_pass":        sum(1 for d in all_deltas if d["baseline"] and d["skill"]),
        "both_fail":        len(both_fail_list),
    },
    "ship_gate": {
        "verdict":          "PASS" if comp.ship_gate_passed else "FAIL",
        "win_rate":         comp.win_rate,
        "regression_rate":  comp.regression_rate,
    } if "comp" in dir() else {"verdict": "NOT_RUN"},
    "dev_log": {
        "baseline": dev_log_comparison['baseline']['metrics'] if dev_log_comparison else None,
        "skill":    dev_log_comparison['skill']['metrics'] if dev_log_comparison else None,
        "found":    dev_log_comparison is not None,
    },
}

manifest = _load_manifest()
manifest["runs"] = [
    r for r in manifest["runs"]
    if not (r["task_id"] == TASK_ID and r["pair_prefix"] == pair["prefix"])
]
manifest["runs"].append(run_record)
# Sort by task_id, then version (v1 before v2) using pair_prefix
import re as _re
def _sort_key(r):
    prefix = r.get("pair_prefix", "")
    # Extract version number from _v2, _v3 etc; default to 1 for v1 pairs
    vm = _re.search(r'_v(\d+)$', prefix)
    ver = int(vm.group(1)) if vm else 1
    return (r["task_id"], ver, r["timestamp"])
manifest["runs"].sort(key=_sort_key)

with open(MANIFEST_PATH, "w") as f:
    json.dump(manifest, f, indent=2)

print(f"\u2713 Manifest saved to {MANIFEST_PATH}")
print(f"  Task: {TASK_ID} | Pair: {pair['prefix']} | {timestamp}")

# ---- 3. Cross-task summary table ------------------------------------------
print(f"\n{'='*100}")
print(f"  CROSS-TASK SUMMARY  ({len(manifest['runs'])} run(s) in manifest)")
print(f"{'='*100}")
print(f"{'Task':<12} {'Pair':<22} {'SK Phases':>10} "
      f"{'SK Wins':>8} {'BL Wins':>8} {'Gate':>6}  {'Bugs BL→SK':>12} {'Iters BL→SK':>13}")
print("-" * 110)

for r in manifest["runs"]:
    tm = r.get("task_meta", {})
    phases = r.get("phases", {})
    bl_pass = sum(1 for p in phases.values() if p.get("baseline"))
    sk_pass = sum(1 for p in phases.values() if p.get("skill"))
    total_p = len(phases)
    sc = r.get("sub_check_summary", {})
    sw = sc.get("skill_wins", 0)
    bw = sc.get("baseline_wins", 0)
    gate = r.get("ship_gate", {}).get("verdict", "?")
    # Short pair label: strip task_id prefix for readability
    pair_prefix = r.get("pair_prefix", "?")
    short_pair = pair_prefix.replace(f"{r['task_id']}_", "", 1)
    if len(short_pair) > 20:
        short_pair = short_pair[:18] + ".."
    # Dev log metrics
    dl = r.get("dev_log", {})
    if dl.get("found") and dl.get("baseline") and dl.get("skill"):
        bl_bugs = dl["baseline"].get("unique_bugs", "?")
        sk_bugs = dl["skill"].get("unique_bugs", "?")
        bl_iters = dl["baseline"].get("fix_iterations", "?")
        sk_iters = dl["skill"].get("fix_iterations", "?")
        bugs_str = f"{bl_bugs}→{sk_bugs}"
        iters_str = f"{bl_iters}→{sk_iters}"
    else:
        bugs_str = "-"
        iters_str = "-"
    print(
        f"  {r['task_id']:<10} {short_pair:<22}"
        f"    {sk_pass}/{total_p}     {sw:>4}     {bw:>4}"
        f"   {gate}  {bugs_str:>12} {iters_str:>13}"
    )

print(f"\nArtifacts:")
print(f"  manifest:  {MANIFEST_PATH}")
print(f"  reports:   {REPORTS_DIR}/")
print(f"  scores:    baseline_scores.json ({len(baseline_scores)} tasks), skill_scores.json ({len(skill_scores)} tasks)")
print(f"  sources:   results/baseline/{TASK_ID}.txt, results/with_skill/{TASK_ID}.txt")
print(f"\n  \u26a0 Note: scores files are keyed by task_id — v2 runs overwrite v1 scores.")
print(f"    The ship gate comparison uses the LATEST pair for each task_id.")
print(f"    Manifest preserves all runs (keyed by pair_prefix).")
