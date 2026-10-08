# Databricks notebook source
# DBTITLE 1,Title
# MAGIC %md
# MAGIC # Open-Weight Models Skill — Test Plan
# MAGIC
# MAGIC End-to-end validation of the `open-weight-models` skill for packaging, registering,
# MAGIC and deploying open-weight HLS models on Databricks.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Why Three Test Layers?
# MAGIC
# MAGIC The skill is a set of instructions that teaches Genie Code how to deploy
# MAGIC HLS models. Testing it requires answering three separate questions:
# MAGIC
# MAGIC | Layer | Question | Assets | When to Run |
# MAGIC |-------|----------|--------|-------------|
# MAGIC | **1 — Structural** | Are the skill files well-formed? (JSON blocks parse, provenance keys present, model references complete) | `01_skill_structure_tests` | Every PR — fast gate, no GPU, no network |
# MAGIC | **2 — Ground Truth** | Do the deployments actually work? (weights download, model registers, endpoint serves, predictions return) | `_dev/_ground_truth/gt_*` notebooks | Before shipping a new model reference — proves the instructions are correct |
# MAGIC | **3 — Skill Eval** | Does the skill improve Genie Code’s output? (baseline vs skill, scored by deterministic rubric) | `03_eval_rubric_and_compare` + `02_eval_prompt_templates` | Before shipping the skill itself — proves it adds value |
# MAGIC
# MAGIC > **Layer 2 status:** GT notebooks are archived in `_dev/_ground_truth/` and score 5-6/8 against the current rubric. They need updating before Layer 2 is operational again.
# MAGIC
# MAGIC **Layer 2 (ground truth) exists because a skill can be structurally valid
# MAGIC but contain wrong instructions.** The only way to know if TEDDY really needs
# MAGIC `transformers==4.41.0` or if Scimilarity really works CPU-only is to run the
# MAGIC deployment. These notebooks are the human-verified reference implementations
# MAGIC that the skill eval scores against.
# MAGIC
# MAGIC **Layer 3 (skill eval) exists because correct reference notebooks don't
# MAGIC guarantee the skill teaches Genie Code well.** The skill text could be
# MAGIC ambiguous, incomplete, or structured in a way Genie Code misinterprets.
# MAGIC Prompting Genie Code with and without the skill, then scoring the output,
# MAGIC is the only way to measure skill quality.

# COMMAND ----------

# DBTITLE 1,Test Plan
# MAGIC %md
# MAGIC ## Skill Location
# MAGIC
# MAGIC The local skill copy lives at `.assistant/skills/open-weight-models/` (this folder).
# MAGIC All test notebooks reference this path.
# MAGIC
# MAGIC ```
# MAGIC <project-folder>/
# MAGIC ├── .assistant/skills/open-weight-models/     ← skill under test
# MAGIC │   ├── SKILL.md                      (rename to SKILL.md.off to disable)
# MAGIC │   ├── references/
# MAGIC │   │   ├── models/                   (7 files: geneformer, scgpt, scimilarity,
# MAGIC │   │   │                              alphafold-openfold, boltz, teddy, index)
# MAGIC │   │   ├── integration-contract.md
# MAGIC │   │   ├── evaluation.md
# MAGIC │   │   ├── maintenance.md
# MAGIC │   │   └── model-template.md
# MAGIC │   └── tests/test_examples.py        (44 offline structural checks)
# MAGIC ├── evalset.json                      ← 9 benchmark tasks (v2.1.0)
# MAGIC ├── scorers.py                        ← 8 phases, 21 sub-checks (family-gated)
# MAGIC ├── compare_runs.py                   ← cross-run comparison logic
# MAGIC ├── results/                          ← exported notebook source (baseline + with_skill)
# MAGIC │   ├── baseline/                     (skill OFF)
# MAGIC │   └── with_skill/                   (skill ON)
# MAGIC ├── 00_oss_models_test_plan           ← this notebook
# MAGIC ├── 01_skill_structure_tests          (Layer 1 — offline gate, runs first)
# MAGIC ├── 02_eval_prompt_templates          (Layer 3 — prompt cards, paste into Genie Code)
# MAGIC ├── 03_eval_rubric_and_compare        (Layer 3 — scoring rubric + ship gate)
# MAGIC ├── oss-001_TEDDY-70M_Deploy_Baseline     (scored pair)
# MAGIC ├── oss-001_TEDDY-70M_Deploy_withSkills   (scored pair)
# MAGIC └── _dev/                             ← archived / stale assets
# MAGIC     ├── 02_skill_eval_runner_ARCHIVED  (superseded by 03_eval_rubric_and_compare)
# MAGIC     └── _ground_truth/                (4 GT notebooks — stale, predate current rubric)
# MAGIC         ├── gt_teddy          (combined download + register/deploy)
# MAGIC         ├── gt_scimilarity    (combined)
# MAGIC         ├── gt_geneformer     (combined)
# MAGIC         └── gt_scgpt          (combined)
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Layer 1 — Structural Gate
# MAGIC
# MAGIC | Notebook | What it checks |
# MAGIC |----------|----------------|
# MAGIC | `01_skill_structure_tests` | 44 offline checks: JSON/YAML block parsing, provenance keys, SKILL.md worked example, per-model input examples, malformed URLs |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Layer 2 — Ground Truth Notebooks
# MAGIC
# MAGIC > **Status:** GT notebooks are archived in `_dev/_ground_truth/` and score 5-6/8 against the current rubric.
# MAGIC > They predate the skill and need updating before Layer 2 is operational. See status callout below.
# MAGIC
# MAGIC These prove the deployment instructions are correct by running them for real.
# MAGIC Each model pair follows SKILL.md Best Practice 8: **CPU download** → **GPU register + deploy**.
# MAGIC
# MAGIC **All `_02_register_deploy` notebooks are now standalone** (no `genesis_workbench`
# MAGIC wheel needed). They are adapted from the GWB source but run independently.
# MAGIC
# MAGIC Every `_02` notebook follows a consistent 4-phase structure:
# MAGIC
# MAGIC | Phase | What | Standard features |
# MAGIC |-------|------|-------------------|
# MAGIC | **1. Register** | PyFunc + `input_example` + `infer_signature` → UC | Signature enables MLflow UI "Test" button |
# MAGIC | **2. Deploy** | SDK-only endpoint creation | **AI Gateway** (inference table + usage tracking) + **scale-to-zero** |
# MAGIC | **3. Score / Eval** | Endpoint smoke test + VS eval scorer (where applicable) | VS eval: self-retrieval, monotonic distances, latency |
# MAGIC | **4. Teardown** | Selective cleanup with `NotFound` handling | Serving endpoints deleted; inference tables + UC models preserved |
# MAGIC
# MAGIC **Model-specific extras:**
# MAGIC * **TEDDY** — VS eval scorer queries `teddy_cell_index`
# MAGIC * **SCimilarity** — VS eval scorer queries `scimilarity_cell_index`; Phase 1b extracts reference to Delta + VS index
# MAGIC * **Geneformer** — Two deployment paths (A: HF/jkobject, B: BioNeMo TE, both no-Docker); eval compares A vs B embeddings (cosine similarity)
# MAGIC * **scGPT** — `TransformerModelWrapper` PyFunc; `flash-attn` requires GPU at import
# MAGIC
# MAGIC **Ground truth notebooks must work on both Serverless and Classic compute.**
# MAGIC They detect the environment at runtime and adapt storage paths, installs,
# MAGIC and GPU checks accordingly. This ensures the skill's instructions are valid
# MAGIC regardless of the user's workspace setup.
# MAGIC
# MAGIC #### Compute detection pattern (used by all `gt_*` notebooks)
# MAGIC
# MAGIC ```python
# MAGIC import os, subprocess
# MAGIC
# MAGIC # Try /local_disk0 first (Classic); fall back to /tmp (Serverless).
# MAGIC try:
# MAGIC     os.makedirs("/local_disk0/tmp", exist_ok=True)
# MAGIC     TMP_DIR = "/local_disk0/tmp"
# MAGIC     IS_SERVERLESS = False
# MAGIC except (PermissionError, OSError):
# MAGIC     TMP_DIR = "/tmp"
# MAGIC     IS_SERVERLESS = True
# MAGIC
# MAGIC HAS_GPU = False
# MAGIC GPU_NAME = "none"
# MAGIC try:
# MAGIC     result = subprocess.run(
# MAGIC         ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
# MAGIC         capture_output=True, text=True, timeout=5,
# MAGIC     )
# MAGIC     if result.returncode == 0:
# MAGIC         HAS_GPU = True
# MAGIC         GPU_NAME = result.stdout.strip().split("\n")[0]
# MAGIC except (FileNotFoundError, subprocess.TimeoutExpired):
# MAGIC     pass
# MAGIC
# MAGIC print(f"Compute : {'Serverless' if IS_SERVERLESS else 'Classic'}")
# MAGIC print(f"Storage : {TMP_DIR}")
# MAGIC print(f"GPU     : {GPU_NAME if HAS_GPU else 'none (CPU-only mode)'}")
# MAGIC ```
# MAGIC
# MAGIC #### Idempotency pattern (all `gt_*` download notebooks)
# MAGIC
# MAGIC Every download notebook is safe to re-run at any point. Three gates,
# MAGIC checked in order:
# MAGIC
# MAGIC ```
# MAGIC Gate 1: Volume sentinel (.copy_complete in Volume dest)
# MAGIC   → model already persisted → skip everything
# MAGIC
# MAGIC Gate 2: Local file check
# MAGIC   → HF snapshot: local sentinel (.snapshot_complete) → skip download
# MAGIC   → Zenodo tarball: gzip -t integrity check → valid? skip : delete + re-download
# MAGIC
# MAGIC Gate 3: Download
# MAGIC   → HF: snapshot_download (handles resume internally)
# MAGIC   → Zenodo: curl -C - (resume partial downloads, 10 retries, 30s backoff)
# MAGIC ```
# MAGIC
# MAGIC After download: verify structure → copy to Volume → write sentinel.
# MAGIC Re-running after a timeout or crash safely resumes from wherever it stopped.
# MAGIC
# MAGIC Download cells print CPU-only mode and continue.
# MAGIC Register/deploy cells raise `RuntimeError` if no GPU
# MAGIC (except Scimilarity, which warns and falls back to `use_gpu=False`).
# MAGIC Geneformer additionally rejects T4 GPUs (needs A10G+ / 24 GB VRAM).
# MAGIC
# MAGIC | Model | GT Notebook | Source Repos | Model Reference | VS path? | Deploy paths |
# MAGIC |-------|-------------|--------------|-----------------|----------|--------------|
# MAGIC | TEDDY-70M | `gt_teddy` | [HuggingFace](https://huggingface.co/Merck/TEDDY) | `teddy.md` | Yes (`teddy_cell_index`) | SDK-only (GPU_SMALL) |
# MAGIC | Scimilarity v1.1 | `gt_scimilarity` | [GitHub](https://github.com/Genentech/scimilarity), [Zenodo](https://zenodo.org/records/10685499) | `scimilarity.md` | Yes (`scimilarity_cell_index`) | GeneOrder (CPU) + GetEmbedding (GPU) |
# MAGIC | Geneformer V2 | `gt_geneformer` | [HuggingFace](https://huggingface.co/ctheodoris/Geneformer) | `geneformer.md` | No | Path A (HF/jkobject) + Path B (BioNeMo TE) |
# MAGIC | scGPT | `gt_scgpt` | [GitHub](https://github.com/bowang-lab/scGPT), [Google Drive](https://drive.google.com/drive/folders/1oWh_-ZRdhtoGQ2Fw24HP41FgLoomVo-y) | `scgpt.md` | No | SDK-only (GPU_SMALL) |
# MAGIC
# MAGIC All notebooks are standalone (adapted from GWB, no `genesis_workbench` wheel).
# MAGIC
# MAGIC These notebooks are **not** the skill eval. They are the answer key.
# MAGIC For the actual eval, open `02_eval_prompt_templates`, copy a prompt card, and let Genie Code generate code on a blank notebook.
# MAGIC
# MAGIC > **Ground truth status (Sep 2026):** GT notebooks are archived in `_dev/_ground_truth/`
# MAGIC > and score 5-6/8 against the current rubric. They predate the skill and lack newer
# MAGIC > best practices (`sys_modules_purge`, `pip_reqs_from_source`, `/tmp` paths).
# MAGIC > They need updating before they can serve as a gold-standard reference.
# MAGIC
# MAGIC The model repo URLs in the prompt let Genie Code inspect the original READMEs/cards:
# MAGIC if a ground truth notebook deploys TEDDY with `transformers==4.41.0` and
# MAGIC Genie Code (with skill) produces `transformers>=4.0`, that's a regression
# MAGIC the skill eval will catch.
# MAGIC
# MAGIC ## Layer 3 — Skill Eval
# MAGIC
# MAGIC | Asset | Purpose |
# MAGIC |-------|---------|
# MAGIC | `evalset.json` | 9 benchmark tasks with model repo URLs (v2.1.0, 5 families) |
# MAGIC | `scorers.py` | 8 phases, 21 sub-checks (TEDDY-specific checks family-gated) |
# MAGIC | `02_eval_prompt_templates` | Prompt cards per task — paste into Genie Code on blank notebooks |
# MAGIC | `03_eval_rubric_and_compare` | Scoring rubric, auto-export, ship gate comparison |
# MAGIC | `results/baseline/` | Exported notebook source with skill OFF |
# MAGIC | `results/with_skill/` | Exported notebook source with skill ON |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## How to Run
# MAGIC
# MAGIC **Layer 1** (every PR, < 1 min):
# MAGIC ```
# MAGIC Run 01_skill_structure_tests on Serverless CPU
# MAGIC ```
# MAGIC
# MAGIC **Layer 2** (before shipping a model reference, ~15 min per model per compute):
# MAGIC ```
# MAGIC Serverless pass:
# MAGIC 1. Run gt_<model> on Serverless CPU (download cells)  → weights land in UC Volume
# MAGIC 2. Run gt_<model> on Serverless GPU (register+deploy)  → endpoint created, smoke-tested, torn down
# MAGIC
# MAGIC Classic pass:
# MAGIC 3. Run gt_<model> on Classic CPU cluster               → verify /local_disk0 path works
# MAGIC 4. Run gt_<model> on Classic ML GPU                     → verify cluster-based deploy
# MAGIC ```
# MAGIC Each gt_* is a combined notebook (download + register/deploy in one).
# MAGIC Models are independent. Run whichever models changed.
# MAGIC Both passes use the same notebook — the compute detection cell adapts automatically.
# MAGIC
# MAGIC **Layer 3** (before shipping the skill, ~30 min per task):
# MAGIC ```
# MAGIC 1. Rename SKILL.md → SKILL.md.off in .assistant/skills/open-weight-models/
# MAGIC 2. Open 02_eval_prompt_templates, find the prompt card for the task
# MAGIC 3. Paste prompt into Genie Code on a blank notebook (fresh chat) → baseline arm
# MAGIC 4. Rename SKILL.md.off → SKILL.md (re-enable skill)
# MAGIC 5. Repeat on another blank notebook (fresh chat) → skill arm
# MAGIC 6. Name notebooks: oss-NNN_<Model>_Deploy_Baseline / _withSkills
# MAGIC 7. Run 03_eval_rubric_and_compare → select pair → auto-exports + scores + ship gate
# MAGIC ```
# MAGIC
# MAGIC **Execution order:** Layer 1 → Layer 2 → Layer 3. Always verify ground truth
# MAGIC before running skill eval — you can’t score Genie Code against an answer key
# MAGIC you haven’t validated.
# MAGIC
# MAGIC **Start cheap:** download cells in each `gt_*` notebook run on Serverless CPU
# MAGIC with no GPU cost. Validate those first, then run register/deploy cells on GPU.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Skill-Eval Benchmarking ([PR #8](https://github.com/databricks-industry-solutions/hls-skills) Pattern)
# MAGIC
# MAGIC **The test IS prompting Genie Code.** The `gt_*` notebooks are ground truth
# MAGIC (proving deployments work); the eval tests whether Genie Code generates
# MAGIC correct code from prompts with vs without the skill.
# MAGIC
# MAGIC ### Eval flow
# MAGIC
# MAGIC | Step | What | How |
# MAGIC |------|------|-----|
# MAGIC | 1 | Send benchmark prompt | Copy from `02_eval_prompt_templates` prompt card, paste in Genie Code on blank notebook |
# MAGIC | 2 | Name + save notebooks | `oss-NNN_<Model>_Deploy_Baseline` / `_withSkills` |
# MAGIC | 3 | Score response | `03_eval_rubric_and_compare` (8 phases, 21 sub-checks per task) |
# MAGIC | 4 | Compare arms | Skill ON vs OFF → ship/no-ship |
# MAGIC
# MAGIC ### Arms
# MAGIC
# MAGIC 1. **Baseline** — rename `SKILL.md` → `SKILL.md.off`, open fresh chat on blank notebook,
# MAGIC    paste prompt, save generated notebook as `oss-NNN_<Model>_Deploy_Baseline`
# MAGIC 2. **Skill** — rename `SKILL.md.off` → `SKILL.md`, fresh chat on another blank notebook,
# MAGIC    paste same prompt, save as `oss-NNN_<Model>_Deploy_withSkills`
# MAGIC 3. **Score** — run `03_eval_rubric_and_compare`: auto-exports notebook source, scores both arms,
# MAGIC    runs ship gate comparison (task_id auto-inferred from pair prefix)
# MAGIC
# MAGIC ### Difficulty levels
# MAGIC
# MAGIC | Level | Definition | Example |
# MAGIC |-------|-----------|----------|
# MAGIC | **easy** | Model is well-documented, widely used, standard HF pattern. Skill adds deployment best practices but Genie Code could likely produce working code without it. | Geneformer — popular HF model, good README |
# MAGIC | **hard** | Model has non-obvious requirements: unusual input formats, specific version pins, custom preprocessing, or niche download sources. Genie Code is unlikely to get it right without the skill. | TEDDY — needs `HF_HUB_DISABLE_XET=1`, AnnData serving contract, `transformers==4.41.0` exact pin |
# MAGIC | **edge** | Model is **not in the skill**. Tests whether Genie Code gracefully acknowledges gaps vs hallucinating instructions. Correct answer: "I don't have specific deployment guidance for this model." | ESM-2 — not covered by any model reference |
# MAGIC | **compute** | Prompt includes a specific compute constraint. Tests whether the skill guides Genie Code to adapt code for the user's environment rather than assuming Serverless GPU. | "I only have Classic CPU" — expect download-only code |
# MAGIC
# MAGIC ### Benchmark tasks (`evalset.json` v2.1.0 — 9 tasks, 5 families)
# MAGIC
# MAGIC | Task ID | Family | Variant | Difficulty | Description |
# MAGIC |---------|--------|---------|-----------|-------------|
# MAGIC | oss-001 | teddy | 70M | hard | Deploy endpoint (core patterns) |
# MAGIC | oss-002 | teddy | 400M | hard | Deploy endpoint + Vector Search index |
# MAGIC | oss-003 | teddy | 70M | compute | Serverless ML compute |
# MAGIC | oss-004 | scimilarity | v1.1 | hard | Deploy from Zenodo + curl |
# MAGIC | oss-005 | geneformer | V1-10M (Path A) | hard | Full Model Serving deploy for single-cell embeddings |
# MAGIC | oss-006 | geneformer | V2-316M BioNeMo (Path B) | hard | Full Model Serving deploy with TransformerEngine-aware loading |
# MAGIC | oss-007 | midnight | — | hard | Pathology tile-embedding deploy |
# MAGIC | oss-008 | generic | ESM-2 | edge | Unsupported model (template fallback) |
# MAGIC | oss-009 | generic | — | compute | CPU-only cluster advisory |
# MAGIC
# MAGIC **Family gating:** scorers.py auto-skips TEDDY-specific checks (e.g. `hf_xet_disabled`,
# MAGIC `deps_pinned`, `real_gene_ids`) for non-TEDDY families. Universal checks (e.g. `uses_tmp`,
# MAGIC `pyfunc_class`, `ai_gateway_config`) apply to all tasks.
# MAGIC
# MAGIC ### Verdict (proposed — refine with team)
# MAGIC
# MAGIC Minimum bar: **1+ wins with 0 regressions = SHIP.** Otherwise iterate.
# MAGIC This is a starting heuristic — adjust thresholds based on real eval runs.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Standard Notebook Structure
# MAGIC
# MAGIC Every `_02_register_deploy` notebook follows a **4-phase pattern** with
# MAGIC consistent components across all models:
# MAGIC
# MAGIC ### Phase 1 — Register
# MAGIC * **PyFunc wrapper** — custom `PythonModel` class with `load_context` + `predict`
# MAGIC * **Dry-load test** — instantiate the model locally, run a forward pass, assert output shape
# MAGIC * **`input_example`** — realistic test input (from real vocab / sample data, not random noise)
# MAGIC * **`infer_signature`** — auto-inferred from input + output examples (enables MLflow UI "Test" button)
# MAGIC * **`log_model`** — registers to Unity Catalog with signature, example, and pinned `pip_requirements`
# MAGIC
# MAGIC ### Phase 1b — Vector Search (TEDDY, SCimilarity only)
# MAGIC * **Reference Delta table** — pre-computed embeddings for reference cell corpus
# MAGIC * **VS endpoint + Delta Sync index** — Standard endpoint, TRIGGERED pipeline type
# MAGIC * **Idempotency** — skips if table + index already at expected row count and dimension
# MAGIC
# MAGIC **How the TEDDY-400M production table was built** (GWB `03_reembed_reference`):
# MAGIC `cellxgene_census.open_soma()` → filter `is_primary_data=True` → batch through
# MAGIC TEDDY-400M → write `(cell_id, embedding, cell_type, tissue, disease)` to Delta.
# MAGIC Result: ~2M rows, dim=1024, 662 cell types, 55 tissues, 108 diseases.
# MAGIC
# MAGIC **Other variants (70M, 160M):** Same pipeline, different checkpoint. Embeddings
# MAGIC are NOT interchangeable — each variant learns its own representation space
# MAGIC (512-d ≠ 768-d ≠ 1024-d). Must re-embed from raw expression data.
# MAGIC For GT testing, a synthetic 200-cell table (Tier 3 fallback) suffices.
# MAGIC
# MAGIC ### Phase 2 — Deploy
# MAGIC * **SDK-only** — no `genesis_workbench` wheel; uses `databricks.sdk.service.serving` directly
# MAGIC * **AI Gateway** (`AiGatewayConfig`) — inference table via `AiGatewayInferenceTableConfig` (logs every request/response to UC Delta table) + `AiGatewayUsageTrackingConfig` (token/request metering). Legacy `AutoCaptureConfigInput` is deprecated.
# MAGIC * **Scale-to-zero** — `scale_to_zero_enabled=True` on all endpoints
# MAGIC * **Run-gated** — behind `run_go` widget (deploy costs real money)
# MAGIC
# MAGIC ### Phase 3 — Score / Eval
# MAGIC * **Endpoint smoke test** — lightweight HTTP request, no ML deps (just `requests`)
# MAGIC * **VS eval scorer** (TEDDY, SCimilarity) — queries VS index with a known embedding,
# MAGIC   validates self-retrieval (top-1), monotonic distance ordering, result count
# MAGIC * **Path A vs B comparison** (Geneformer) — cosine similarity between HF and BioNeMo
# MAGIC   embeddings to confirm both produce valid, non-degenerate vectors
# MAGIC
# MAGIC ### Phase 4 — Teardown
# MAGIC * **Selective cleanup** — serving endpoints deleted (highest cost); VS indexes and
# MAGIC   endpoints commented-out (shared resources); UC models + inference tables preserved
# MAGIC * **Idempotent** — all deletes wrapped in `try/except NotFound`
# MAGIC
# MAGIC ### Download phase (first half of each `gt_*` notebook)
# MAGIC * **Three-gate idempotency** — Volume sentinel → local file check → download
# MAGIC * **Adaptive storage** — `/tmp` (Serverless) or `/local_disk0` (Classic)
# MAGIC * **Resume-capable** — `curl -C -` for Zenodo, `snapshot_download` for HuggingFace
# MAGIC * **CPU-only** — no GPU needed; prints mode and continues
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Compute Compatibility Matrix
# MAGIC
# MAGIC The skill should guide Genie Code to the right compute for the user's
# MAGIC environment — not every workspace has Serverless GPU or ML Runtime.
# MAGIC Ground truth notebooks should be tested on multiple compute types to
# MAGIC verify the skill's instructions work across environments.
# MAGIC
# MAGIC | Compute Type | Download (`gt_*_01`) | Register & Deploy (`gt_*_02`) | Notes |
# MAGIC |-------------|---------------------|-------------------------------|-------|
# MAGIC | **Serverless CPU** | Yes | No (no GPU) | Cheapest for downloads; `/tmp` storage only |
# MAGIC | **Serverless GPU** | Yes | Yes | `/tmp` storage, no `apt-get`, pre-installed CUDA |
# MAGIC | **Serverless ML** | Yes | Yes | ML Runtime + GPU, best for HF models |
# MAGIC | **Classic CPU cluster** | Yes | No (no GPU) | `/local_disk0` available, `apt-get` works |
# MAGIC | **Classic GPU** (T4) | Yes | Small models only | 16 GB VRAM — too small for Geneformer |
# MAGIC | **Classic GPU** (A10G) | Yes | Yes | 24 GB VRAM — minimum for most HLS models |
# MAGIC | **Classic GPU** (L40S) | Yes | Yes | 48 GB VRAM — comfortable for larger models |
# MAGIC | **Classic GPU** (A100) | Yes | Yes | 40/80 GB VRAM — needed for large foundation models |
# MAGIC | **Classic GPU** (H100) | Yes | Yes | 80 GB VRAM — largest models, fastest inference |
# MAGIC | **Classic ML Runtime GPU** | Yes | Yes | Any GPU above + `apt-get`, `/local_disk0`, pre-installed PyTorch/TF |
# MAGIC
# MAGIC ### What the skill should detect / recommend
# MAGIC
# MAGIC * **Storage path:** `/tmp` on Serverless vs `/local_disk0` on Classic
# MAGIC * **Package install:** `%pip` everywhere, but `apt-get` only on Classic
# MAGIC * **GPU availability:** skip register/deploy cells if no GPU attached
# MAGIC * **GPU memory:** T4 (16 GB) vs A10G (24 GB) vs L40S (48 GB) vs A100 (40/80 GB) vs H100 (80 GB) — some models need minimum VRAM
# MAGIC * **ML Runtime:** pre-installed PyTorch/TF vs needing `%pip install torch`
# MAGIC * **TransformerEngine:** only realistic on ML Runtime (complex CUDA build on vanilla GPU)
# MAGIC
# MAGIC ### Testing strategy
# MAGIC
# MAGIC Each `gt_*` notebook must pass on **both** compute families:
# MAGIC
# MAGIC | Run | Compute | What it validates |
# MAGIC |-----|---------|-------------------|
# MAGIC | 1 | Serverless CPU/GPU/ML | `/tmp` paths, no `apt-get`, Serverless env vars |
# MAGIC | 2 | Classic ML Runtime GPU | `/local_disk0` paths, `apt-get` available, cluster-level libs |
# MAGIC
# MAGIC A ground truth notebook that only works on one compute type means the
# MAGIC skill's instructions are incomplete — fix the skill, not just the notebook.
# MAGIC
# MAGIC Edge cases for evalset prompts:
# MAGIC * User says "I only have Classic CPU" → skill should produce download-only code + explain GPU requirement
# MAGIC * User says "I have a T4 cluster" → skill should warn about models that need A10G+
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC * Unity Catalog write access to `<catalog>.<schema>` (set via notebook widgets)
# MAGIC * Permission to create GPU Model Serving endpoints
# MAGIC * For Serverless path: Serverless GPU or ML compute enabled in workspace
# MAGIC * For Classic path: GPU cluster with A10G or better (ML Runtime recommended)
# MAGIC
# MAGIC ## Cost Warning
# MAGIC
# MAGIC GPU endpoints bill continuously while active. Every register/deploy notebook
# MAGIC includes a teardown cell — **run it immediately after the smoke test**.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Adding a New Model
# MAGIC
# MAGIC To add a new HF model (or any external model) to this test suite:
# MAGIC
# MAGIC 1. Create a model reference at `.assistant/skills/open-weight-models/references/models/<model>.md`
# MAGIC  (copy `model-template.md`, fill in identity, inputs/outputs, artifacts, deployment)
# MAGIC 2. Add a row to `.assistant/skills/open-weight-models/references/models/index.md`
# MAGIC 3. Create a combined `gt_<model>` notebook (download + register/deploy in one)
# MAGIC 4. Update the test matrix in this notebook
# MAGIC 5. Run `01_skill_structure_tests` to verify the new reference passes all checks
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Source Feedback — Initial Testing and Review
# MAGIC
# MAGIC All source material lives in
# MAGIC [`databricks-industry-solutions/hls-skills`](https://github.com/databricks-industry-solutions/hls-skills).
# MAGIC This test suite itself lives **outside** the repo at
# MAGIC `/PROJECTS/hls-skills-tests/<project-folder>/` to avoid polluting the skill package.
# MAGIC
# MAGIC Key patterns in the notebooks above were integrated from the following PRs
# MAGIC and review feedback. **PR-specific detail is here for traceability**; the
# MAGIC notebooks themselves just apply the patterns without citing PR numbers inline.
# MAGIC
# MAGIC | Source | What it contributed |
# MAGIC |--------|--------------------|
# MAGIC | [**PR #5**](https://github.com/databricks-industry-solutions/hls-skills/pull/5) (Yen review) | Download/register split, dry-load tests, `infer_signature`, pinned deps, sentinel idempotency, clean code bundles (no weights in artifact), provenance tags |
# MAGIC | [**PR #7**](https://github.com/databricks-industry-solutions/hls-skills/pull/7) | TEDDY module (BP 8-12, TS 8-13), `HF_HUB_DISABLE_XET`, adaptive storage, `io.StringIO` wrapper, real-vocab test payloads, endpoint readiness polling, service log diagnosis |
# MAGIC | **PR #8** (planned) | Eval framework: `evalset.json`, `scorers.py`, `eval_rubric_and_compare` |
# MAGIC | [Yen's TEDDY notebooks](https://github.com/databricks-industry-solutions/hls-skills/tree/main/notebooks/yenl_tests/TEDDY) | trial1 + trial2: real deployment code for TEDDY-70M and Scimilarity |
# MAGIC | Serving-validation notebooks | Geneformer BioNeMo, DNABERT-2, and Midnight proofs-of-concept are kept outside the repo for now. |
# MAGIC | [SKILL.md](https://github.com/databricks-industry-solutions/hls-skills/blob/main/skills/open-weight-models/SKILL.md) | The skill under test (BP 1-12, TS 1-13, 7 model references) |
# MAGIC | [Model references](https://github.com/databricks-industry-solutions/hls-skills/tree/main/skills/open-weight-models/references/models) | Per-model deployment guides (geneformer, scgpt, scimilarity, alphafold-openfold, boltz, teddy) and `index.md` (table-of-contents listing all available model references) |
