# Databricks notebook source
# DBTITLE 1,Eval scratch
# MAGIC %md
# MAGIC # Eval Scratch — Blank Notebook for Prompt Testing
# MAGIC
# MAGIC This notebook is intentionally blank. Open Genie Code, paste a prompt
# MAGIC from `evalset.json`, and let it generate code here.
# MAGIC
# MAGIC The `.assistant/skills/oss-models/` skill is in scope for this folder.
# MAGIC
# MAGIC ## Baseline protocol (skill OFF)
# MAGIC
# MAGIC To run a **baseline** test, rename the SKILL.md file — **not the folder**:
# MAGIC ```
# MAGIC mv .assistant/skills/oss-models/SKILL.md .assistant/skills/oss-models/SKILL.md.off
# MAGIC ```
# MAGIC Then start a **fresh chat** on a blank notebook and paste the prompt.
# MAGIC
# MAGIC To re-enable: `mv .assistant/skills/oss-models/SKILL.md.off .assistant/skills/oss-models/SKILL.md`
# MAGIC
# MAGIC > **Why not rename the folder?** The assistant discovers skills via `.assistant/skills/*/SKILL.md`.
# MAGIC > A renamed folder like `_oss-models-off/` still contains `SKILL.md`, so the glob still matches.
# MAGIC > Renaming the file itself is the only reliable disable method.
# MAGIC
# MAGIC > **Built-in skills remain active.** Platform skills (`machine-learning`, `databricks-model-serving`,
# MAGIC > `environment-management`, etc.) cannot be toggled. The baseline comparison measures the
# MAGIC > incremental value of the custom HLS skill on top of built-in Databricks knowledge.

# COMMAND ----------

# DBTITLE 1,oss-001: TEDDY 70M (hard) — TESTED
# MAGIC %md
# MAGIC # oss-001: TEDDY-70M Deploy
# MAGIC
# MAGIC **Status**: ✅ Tested — [Baseline NB](#notebook-390164024659897) | [Skill NB](#notebook-390164024659899)
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Baseline arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` renamed to `SKILL.md.off` → save to `results/baseline/oss-001.txt`
# MAGIC
# MAGIC > Deploy TEDDY-70M as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/teddy`. Register the model as `<catalog>.skills.teddy_70m_baseline` and name the endpoint `teddy_70m_baseline`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it's in a FAILED state or doesn't exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don't leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Final step**: Export this notebook's source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-001.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Skill arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` active → save to `results/with_skill/oss-001.txt`
# MAGIC
# MAGIC > Deploy TEDDY-70M as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/teddy`. Register the model as `<catalog>.skills.teddy_70m` and name the endpoint `teddy_70m`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it's in a FAILED state or doesn't exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don't leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project's HLS model-deployment skill and TEDDY model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/oss-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/oss-models/references/models/teddy.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Final step**: Export this notebook's source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-001.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Arm differences
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | Explicit `readAssetById` to `SKILL.md` + `teddy.md` | None |
# MAGIC | **Volume path** | `test_with/models/teddy` | `test_without/models/teddy` |
# MAGIC | **UC model** | `teddy_70m` | `teddy_70m_baseline` |
# MAGIC | **Endpoint** | `teddy_70m` | `teddy_70m_baseline` |
# MAGIC
# MAGIC ### What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (GPU\_SMALL? GPU\_MEDIUM? CPU?)
# MAGIC * Notebook structure (one notebook? two? CPU/GPU split?)
# MAGIC * Whether to enable inference tables and AI Gateway usage tracking
# MAGIC * Whether to set up Vector Search
# MAGIC * Dependency versions (especially `transformers` pinning)
# MAGIC * Download method and staging path
# MAGIC * HF Xet backend handling
# MAGIC * Serving contract shape
# MAGIC * Code-bundle stripping strategy

# COMMAND ----------

# DBTITLE 1,oss-002: TEDDY 70M +VS (hard) — TESTED
# MAGIC %md
# MAGIC # oss-002: TEDDY-70M + Vector Search
# MAGIC
# MAGIC **Status**: ✅ Tested — [Baseline NB](#notebook-4070133587703101) | [Skill NB](#notebook-4070133587703100) | [Skill v2 NB](#notebook-2452914719238703)
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Baseline arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` renamed to `SKILL.md.off` → save to `results/baseline/oss-002.txt`
# MAGIC
# MAGIC > Deploy TEDDY-70M as a Model Serving endpoint and enable nearest-neighbor cell-type search on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/teddy`. Register the model as `<catalog>.skills.teddy_70m_vs_baseline` and name the endpoint `teddy-70m-vs-baseline`. Create a Delta table of reference cell embeddings and a Vector Search index for nearest-neighbor lookup. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it's in a FAILED state or doesn't exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don't leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations (e.g. synthetic vs real data). This is eval metadata for comparing the baseline and skill arms — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook's source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-002.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Skill arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` active → save to `results/with_skill/oss-002.txt`
# MAGIC
# MAGIC > Deploy TEDDY-70M as a Model Serving endpoint and enable nearest-neighbor cell-type search on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/teddy`. Register the model as `<catalog>.skills.teddy_70m_vs` and name the endpoint `teddy-70m-vs-embedder`. Create a Delta table of reference cell embeddings and a Vector Search index for nearest-neighbor lookup. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it's in a FAILED state or doesn't exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don't leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project's HLS model-deployment skill and TEDDY model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/oss-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/oss-models/references/models/teddy.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure, an AI Search index spec), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations (e.g. synthetic vs real data). This is eval metadata for comparing the baseline and skill arms — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook's source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-002.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Arm differences
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | Explicit `readAssetById` to `SKILL.md` + `teddy.md` | None |
# MAGIC | **Volume path** | `test_with/models/teddy` | `test_without/models/teddy` |
# MAGIC | **UC model** | `teddy_70m_vs` | `teddy_70m_vs_baseline` |
# MAGIC | **Endpoint** | `teddy-70m-vs-embedder` | `teddy-70m-vs-baseline` |
# MAGIC | **Dev log** | Required (identical) | Required (identical) |
# MAGIC
# MAGIC ### What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (GPU\_SMALL? GPU\_MEDIUM? CPU?)
# MAGIC * Notebook structure (one notebook? two? CPU/GPU split?)
# MAGIC * Whether to enable inference tables and AI Gateway usage tracking
# MAGIC * Dependency versions (especially `transformers` pinning)
# MAGIC * Download method and staging path
# MAGIC * HF Xet backend handling
# MAGIC * Serving contract shape
# MAGIC * Code-bundle stripping strategy
# MAGIC * **Vector Search specifics**: reference corpus source (Census vs synthetic), index naming, embedding dimension, DeltaSync vs Direct access, sync pipeline type, CDF enablement
# MAGIC * **Census pipeline**: how many cells to sample, batch size, gene ID remapping strategy

# COMMAND ----------

# DBTITLE 1,oss-003: TEDDY 400M +VS (hard) — PLACEHOLDER
# MAGIC %md
# MAGIC # oss-003: TEDDY-400M + Vector Search (GWB)
# MAGIC
# MAGIC **Status**: ⚠️ **Placeholder** — initial prompt, not yet battle-tested in dedicated test notebooks. Needs volume isolation, resource naming, idempotency, gt\_ guard, dev-log, and export steps before running.
# MAGIC
# MAGIC **Eval protocol**: Paste the prompt below into Genie Code chat on this notebook.
# MAGIC
# MAGIC **Skill arm**: `.assistant/skills/oss-models/` active (default) → save response to `results/with_skill/oss-003.txt`
# MAGIC
# MAGIC **Baseline arm**: rename `SKILL.md` → `SKILL.md.off` in `.assistant/skills/oss-models/`, fresh chat → save to `results/baseline/oss-003.txt`
# MAGIC
# MAGIC **Key difference from oss-002**: Uses 400M variant (`embedding_dimension=1024`) and hints at an existing production table (`genesis_workbench.teddy_cells`).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Prompt**:
# MAGIC
# MAGIC > Deploy TEDDY-400M as a Model Serving endpoint and enable nearest-neighbor cell-type search on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). There may already be a production reference table (genesis_workbench.teddy_cells) in the workspace — use it if available. Use catalog `<catalog>`, schema `skills`. Write the code.

# COMMAND ----------

# DBTITLE 1,oss-004: scimilarity (hard) — PLACEHOLDER
# MAGIC %md
# MAGIC # oss-004: Scimilarity v1.1 Deploy
# MAGIC
# MAGIC **Status**: ⚠️ **Placeholder** — initial prompt, not yet battle-tested in dedicated test notebooks. Needs volume isolation, resource naming, idempotency, gt\_ guard, dev-log, and export steps before running.
# MAGIC
# MAGIC **Eval protocol**: Paste the prompt below into Genie Code chat on this notebook.
# MAGIC
# MAGIC **Skill arm**: `.assistant/skills/oss-models/` active (default) → save response to `results/with_skill/oss-004.txt`
# MAGIC
# MAGIC **Baseline arm**: rename `SKILL.md` → `SKILL.md.off` in `.assistant/skills/oss-models/`, fresh chat → save to `results/baseline/oss-004.txt`
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Prompt**:
# MAGIC
# MAGIC > Deploy Scimilarity v1.1 as a Model Serving endpoint on Databricks. The model repo is https://github.com/Genentech/scimilarity and pre-trained weights are at https://zenodo.org/records/10685499. Use catalog `<catalog>`, schema `skills`. Write the code.

# COMMAND ----------

# DBTITLE 1,oss-005: geneformer V1 deploy (hard) — PLACEHOLDER
# MAGIC %md
# MAGIC # oss-005: Geneformer V1 Deploy
# MAGIC
# MAGIC **Status**: ⚠️ **Placeholder** — initial prompt, not yet battle-tested in dedicated test notebooks. Needs volume isolation, resource naming, idempotency, gt\_ guard, dev-log, and export steps before running.
# MAGIC
# MAGIC **Eval protocol**: Paste the prompt below into Genie Code chat on this notebook.
# MAGIC
# MAGIC **Skill arm**: `.assistant/skills/oss-models/` active (default) → save response to `results/with_skill/oss-005.txt`
# MAGIC
# MAGIC **Baseline arm**: rename `SKILL.md` → `SKILL.md.off` in `.assistant/skills/oss-models/`, fresh chat → save to `results/baseline/oss-005.txt`
# MAGIC
# MAGIC **Key test**: Full end-to-end deploy of Geneformer Path A (ctheodoris/Geneformer, V1-10M variant, `embedding_dimension=256`, pickle token dicts). Must handle HF repo restructure — `geneformer-12L-30M` no longer exists.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Prompt**:
# MAGIC
# MAGIC > Deploy Geneformer (Geneformer-V1-10M) as a Model Serving endpoint on Databricks for single-cell embedding. The model is at https://huggingface.co/ctheodoris/Geneformer. Use catalog `<catalog>`, schema `skills`. Write the code and explain your decisions.

# COMMAND ----------

# DBTITLE 1,oss-006: geneformer BioNeMo (hard) — PLACEHOLDER
# MAGIC %md
# MAGIC # oss-006: Geneformer V2 (NVIDIA BioNeMo) Deploy
# MAGIC
# MAGIC **Status**: ⚠️ **Placeholder** — initial prompt, not yet battle-tested in dedicated test notebooks. Needs volume isolation, resource naming, idempotency, gt\_ guard, dev-log, and export steps before running.
# MAGIC
# MAGIC **Eval protocol**: Paste the prompt below into Genie Code chat on this notebook.
# MAGIC
# MAGIC **Skill arm**: `.assistant/skills/oss-models/` active (default) → save response to `results/with_skill/oss-006.txt`
# MAGIC
# MAGIC **Baseline arm**: rename `SKILL.md` → `SKILL.md.off` in `.assistant/skills/oss-models/`, fresh chat → save to `results/baseline/oss-006.txt`
# MAGIC
# MAGIC **Key test**: Deploy Path B — NVIDIA BioNeMo checkpoint (`nvidia/geneformer_V2_316M`). Requires `trust_remote_code=True`, `transformer_engine[pytorch]` dep, Ampere+ GPU. Must NOT require Docker/BioNeMo container.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Prompt**:
# MAGIC
# MAGIC > Deploy Geneformer using the NVIDIA BioNeMo checkpoint (nvidia/geneformer_V2_316M) as a Model Serving endpoint on Databricks. Use the TransformerEngine-aware checkpoint directly via AutoModel — no Docker or BioNeMo container needed. Use catalog `<catalog>`, schema `skills`. Write the code.

# COMMAND ----------

# DBTITLE 1,oss-007: midnight (hard) — PLACEHOLDER
# MAGIC %md
# MAGIC # oss-007: Midnight Pathology Model Deploy
# MAGIC
# MAGIC **Status**: ⚠️ **Placeholder** — initial prompt, not yet battle-tested in dedicated test notebooks. Needs volume isolation, resource naming, idempotency, gt\_ guard, dev-log, and export steps before running.
# MAGIC
# MAGIC **Eval protocol**: Paste the prompt below into Genie Code chat on this notebook.
# MAGIC
# MAGIC **Skill arm**: `.assistant/skills/oss-models/` active (default) → save response to `results/with_skill/oss-007.txt`
# MAGIC
# MAGIC **Baseline arm**: rename `SKILL.md` → `SKILL.md.off` in `.assistant/skills/oss-models/`, fresh chat → save to `results/baseline/oss-007.txt`
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Prompt**:
# MAGIC
# MAGIC > Deploy kaiko-ai/midnight (pathology tile-embedding model, MIT license) as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/kaiko-ai/midnight (code: https://github.com/kaiko-ai/midnight). It takes histopathology image tiles as input and produces embedding vectors. Use catalog `<catalog>`, schema `skills`. Write the code.

# COMMAND ----------

# DBTITLE 1,oss-008: ESM-2 (edge) — PLACEHOLDER
# MAGIC %md
# MAGIC # oss-008: ESM-2 Protein Model Deploy
# MAGIC
# MAGIC **Status**: ⚠️ **Placeholder** — initial prompt, not yet battle-tested in dedicated test notebooks. Needs volume isolation, resource naming, idempotency, gt\_ guard, dev-log, and export steps before running.
# MAGIC
# MAGIC **Eval protocol**: Paste the prompt below into Genie Code chat on this notebook.
# MAGIC
# MAGIC **Skill arm**: `.assistant/skills/oss-models/` active (default) → save response to `results/with_skill/oss-008.txt`
# MAGIC
# MAGIC **Baseline arm**: rename `SKILL.md` → `SKILL.md.off` in `.assistant/skills/oss-models/`, fresh chat → save to `results/baseline/oss-008.txt`
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Prompt**:
# MAGIC
# MAGIC > I have a HuggingFace protein language model at https://huggingface.co/facebook/esm2_t6_8M_UR50D that I want to deploy on Databricks Model Serving. Use catalog `<catalog>`, schema `skills`. Write the code.

# COMMAND ----------

# DBTITLE 1,oss-009: CPU-only advisory (compute) — PLACEHOLDER
# MAGIC %md
# MAGIC # oss-009: CPU-Only Deployment Advisory
# MAGIC
# MAGIC **Status**: ⚠️ **Placeholder** — initial prompt, not yet battle-tested in dedicated test notebooks. Needs volume isolation, resource naming, idempotency, gt\_ guard, dev-log, and export steps before running.
# MAGIC
# MAGIC **Eval protocol**: Paste the prompt below into Genie Code chat on this notebook.
# MAGIC
# MAGIC **Skill arm**: `.assistant/skills/oss-models/` active (default) → save response to `results/with_skill/oss-009.txt`
# MAGIC
# MAGIC **Baseline arm**: rename `SKILL.md` → `SKILL.md.off` in `.assistant/skills/oss-models/`, fresh chat → save to `results/baseline/oss-009.txt`
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Prompt**:
# MAGIC
# MAGIC > I want to deploy a single-cell embedding model on Databricks but I only have a Classic CPU cluster (no GPU). What are my options?