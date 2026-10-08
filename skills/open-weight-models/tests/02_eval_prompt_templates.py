# Databricks notebook source
# DBTITLE 1,Prompt Templates and Guide
# MAGIC %md
# MAGIC # Eval Prompt Templates
# MAGIC
# MAGIC Canonical prompt library for the HLS skills eval. Each cell below is one task
# MAGIC (oss-001 through oss-009) with both **baseline** and **skill** arm prompts.
# MAGIC
# MAGIC ## How to run a task
# MAGIC
# MAGIC 1. Create a **dedicated pair** of notebooks: `oss-NNN_<Model>_Baseline` + `oss-NNN_<Model>_withSkills`
# MAGIC 2. Copy the matching prompt from this notebook into Cell 1 of each
# MAGIC 3. Toggle the skill: `mv SKILL.md SKILL.md.off` (baseline) or `mv SKILL.md.off SKILL.md` (skill)
# MAGIC 4. Open a **fresh** Genie Code chat on the target notebook and paste the prompt
# MAGIC 5. Score with `03_eval_rubric_and_compare`
# MAGIC
# MAGIC ## Baseline protocol (skill OFF)
# MAGIC
# MAGIC Rename the file — **not the folder**:
# MAGIC ```
# MAGIC mv .assistant/skills/open-weight-models/SKILL.md .assistant/skills/open-weight-models/SKILL.md.off
# MAGIC ```
# MAGIC Re-enable: `mv .assistant/skills/open-weight-models/SKILL.md.off .assistant/skills/open-weight-models/SKILL.md`
# MAGIC
# MAGIC > **Why not rename the folder?** The assistant discovers skills via `.assistant/skills/*/SKILL.md`.
# MAGIC > A renamed folder like `_open-weight-models-off/` still contains `SKILL.md`, so the glob still matches.
# MAGIC
# MAGIC > **Built-in skills remain active.** Platform skills (`machine-learning`, `databricks-model-serving`,
# MAGIC > `environment-management`, etc.) cannot be toggled. The baseline comparison measures the
# MAGIC > incremental value of the custom HLS skill on top of built-in Databricks knowledge.
# MAGIC
# MAGIC ## Prompt template checklist
# MAGIC
# MAGIC When promoting a **placeholder** task (oss-003+) to a full eval prompt, ensure both arms include:
# MAGIC
# MAGIC | Section | Required | Notes |
# MAGIC |---------|----------|-------|
# MAGIC | Task description | ✅ | Model name, HF URL, license, what to deploy |
# MAGIC | Catalog / schema / volume paths | ✅ | BL: `test_without/`, SK: `test_with/` |
# MAGIC | UC model + endpoint names | ✅ | BL: `*_baseline`, SK: clean name |
# MAGIC | Idempotency instruction | ✅ | Skip if READY, tear down if FAILED |
# MAGIC | Skill `readAssetById` paths | SK only | `SKILL.md` + model-specific `references/models/<model>.md` |
# MAGIC | "Treat skill as authoritative" | SK only | Prevents Genie Code from substituting its own patterns |
# MAGIC | `gt_` contamination guard | ✅ | "Do NOT read any file starting with `gt_`" |
# MAGIC | Skills consulted list | ✅ | "List every skill from the Skill Registry you loaded" |
# MAGIC | Development log | ✅ | Markdown cell titled "Development Log" — bugs, iterations, versions |
# MAGIC | **Runtime capture** | ✅ | Code cell titled "Runtime and Environment Info" — see below |
# MAGIC | Export step | ✅ | Workspace REST API export to `results/{arm}/oss-NNN.txt` |
# MAGIC
# MAGIC ### Runtime capture paragraph (copy verbatim into both arms)
# MAGIC
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC
# MAGIC See also: `README_environments.md` for known runtime snapshots and detection logic.
# MAGIC
# MAGIC ### Naming conventions
# MAGIC
# MAGIC | Item | Baseline arm | Skill arm |
# MAGIC |------|-------------|----------|
# MAGIC | Volume | `/Volumes/.../test_without/models/<model>` | `/Volumes/.../test_with/models/<model>` |
# MAGIC | UC model | `<catalog>.skills.<model>_baseline` | `<catalog>.skills.<model>` |
# MAGIC | Endpoint | `<model>-baseline` | `<model>` |
# MAGIC | Export | `results/baseline/oss-NNN.txt` | `results/with_skill/oss-NNN.txt` |

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
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
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
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/references/models/teddy.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
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
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
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
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/references/models/teddy.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure, an AI Search index spec), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations (e.g. synthetic vs real data). This is eval metadata for comparing the baseline and skill arms — do not skip it.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
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

# DBTITLE 1,oss-003: TEDDY 400M +VS (hard) — READY
# MAGIC %md
# MAGIC # oss-003: TEDDY-400M + Vector Search (GWB)
# MAGIC
# MAGIC **Status**: 🟡 **Ready** — full prompts, not yet run in dedicated test notebooks.
# MAGIC
# MAGIC **Key difference from oss-002**: Uses 400M variant (`embedding_dimension=1024`) and hints at an existing production table (`genesis_workbench.teddy_cells`). Tests GWB fallback behavior.
# MAGIC
# MAGIC **Prerequisite**: Ensure `references/models/teddy.md` covers the 400M variant (it should — same HF repo).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Baseline arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` renamed to `SKILL.md.off` → save to `results/baseline/oss-003.txt`
# MAGIC
# MAGIC > Deploy TEDDY-400M as a Model Serving endpoint and enable nearest-neighbor cell-type search on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use the 400M variant (d\_model=1024). There may already be a production reference table (`genesis_workbench.teddy_cells`) in the workspace — use it if available, otherwise build a reference corpus. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/teddy_400m`. Register the model as `<catalog>.skills.teddy_400m_vs_baseline` and name the endpoint `teddy-400m-vs-baseline`. Create a Delta table of reference cell embeddings and a Vector Search index for nearest-neighbor lookup. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations (e.g. synthetic vs real data). This is eval metadata for comparing the baseline and skill arms — do not skip it.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-003.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Skill arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` active → save to `results/with_skill/oss-003.txt`
# MAGIC
# MAGIC > Deploy TEDDY-400M as a Model Serving endpoint and enable nearest-neighbor cell-type search on Databricks. The model is at https://huggingface.co/Merck/TEDDY (Apache-2.0, paper: arxiv 2503.03485). Use the 400M variant (d\_model=1024). There may already be a production reference table (`genesis_workbench.teddy_cells`) in the workspace — use it if available, otherwise build a reference corpus. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/teddy_400m`. Register the model as `<catalog>.skills.teddy_400m_vs` and name the endpoint `teddy-400m-vs`. Create a Delta table of reference cell embeddings and a Vector Search index for nearest-neighbor lookup. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project’s HLS model-deployment skill and TEDDY model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/references/models/teddy.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure, an AI Search index spec), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations (e.g. synthetic vs real data). This is eval metadata for comparing the baseline and skill arms — do not skip it.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-003.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Arm differences
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | Explicit `readAssetById` to `SKILL.md` + `teddy.md` | None |
# MAGIC | **Volume path** | `test_with/models/teddy_400m` | `test_without/models/teddy_400m` |
# MAGIC | **UC model** | `teddy_400m_vs` | `teddy_400m_vs_baseline` |
# MAGIC | **Endpoint** | `teddy-400m-vs` | `teddy-400m-vs-baseline` |
# MAGIC
# MAGIC ### What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (GPU\_SMALL? GPU\_MEDIUM?)
# MAGIC * Whether to use the GWB production table or build from Census
# MAGIC * Whether to enable inference tables and AI Gateway usage tracking
# MAGIC * Dependency versions (especially `transformers` pinning)
# MAGIC * Download method and HF Xet backend handling
# MAGIC * Vector Search specifics: DeltaSync vs Direct access, sync pipeline type

# COMMAND ----------

# DBTITLE 1,oss-004: scimilarity (hard) — READY
# MAGIC %md
# MAGIC # oss-004: Scimilarity v1.1 Deploy
# MAGIC
# MAGIC **Status**: 🟡 **Ready** — full prompts, not yet run in dedicated test notebooks.
# MAGIC
# MAGIC **Prerequisite**: Create `references/models/scimilarity.md` if not already present.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Baseline arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` renamed to `SKILL.md.off` → save to `results/baseline/oss-004.txt`
# MAGIC
# MAGIC > Deploy Scimilarity v1.1 as a Model Serving endpoint on Databricks. The model repo is https://github.com/Genentech/scimilarity and pre-trained weights are at https://zenodo.org/records/10685499. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/scimilarity`. Register the model as `<catalog>.skills.scimilarity_v11_baseline` and name the endpoint `scimilarity-v11-baseline`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-004.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Skill arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` active → save to `results/with_skill/oss-004.txt`
# MAGIC
# MAGIC > Deploy Scimilarity v1.1 as a Model Serving endpoint on Databricks. The model repo is https://github.com/Genentech/scimilarity and pre-trained weights are at https://zenodo.org/records/10685499. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/scimilarity`. Register the model as `<catalog>.skills.scimilarity_v11` and name the endpoint `scimilarity-v11`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project’s HLS model-deployment skill and Scimilarity model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/references/models/scimilarity.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-004.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Arm differences
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | Explicit `readAssetById` to `SKILL.md` + `scimilarity.md` | None |
# MAGIC | **Volume path** | `test_with/models/scimilarity` | `test_without/models/scimilarity` |
# MAGIC | **UC model** | `scimilarity_v11` | `scimilarity_v11_baseline` |
# MAGIC | **Endpoint** | `scimilarity-v11` | `scimilarity-v11-baseline` |
# MAGIC
# MAGIC ### What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (GPU\_SMALL? CPU?)
# MAGIC * How to download Zenodo weights (wget? requests? SDK?)
# MAGIC * Dependency management (scimilarity pip install vs manual)
# MAGIC * Serving contract shape
# MAGIC * Code-bundle stripping strategy

# COMMAND ----------

# DBTITLE 1,oss-005: geneformer V1 deploy (hard) — READY
# MAGIC %md
# MAGIC # oss-005: Geneformer V1 Deploy (Path A)
# MAGIC
# MAGIC **Status**: 🟡 **Ready** — full prompts, not yet run in dedicated test notebooks.
# MAGIC
# MAGIC **Key test**: Deploy Path A (ctheodoris/Geneformer, V1-10M variant, `embedding_dimension=256`, pickle token dicts). Must handle HF repo restructure — `geneformer-12L-30M` no longer exists.
# MAGIC
# MAGIC **Prerequisite**: Create `references/models/geneformer.md` if not already present.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Baseline arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` renamed to `SKILL.md.off` → save to `results/baseline/oss-005.txt`
# MAGIC
# MAGIC > Deploy Geneformer (V1-10M variant) as a Model Serving endpoint on Databricks for single-cell embedding. The model is at https://huggingface.co/ctheodoris/Geneformer. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/geneformer_v1`. Register the model as `<catalog>.skills.geneformer_v1_10m_baseline` and name the endpoint `geneformer-v1-10m-baseline`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Enable `scale_to_zero_enabled=True` on the served entity to avoid idle GPU charges. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-005.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Skill arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` active → save to `results/with_skill/oss-005.txt`
# MAGIC
# MAGIC > Deploy Geneformer (V1-10M variant) as a Model Serving endpoint on Databricks for single-cell embedding. The model is at https://huggingface.co/ctheodoris/Geneformer. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/geneformer_v1`. Register the model as `<catalog>.skills.geneformer_v1_10m` and name the endpoint `geneformer-v1-10m`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Enable `scale_to_zero_enabled=True` on the served entity to avoid idle GPU charges. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project’s HLS model-deployment skill and Geneformer model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/references/models/geneformer.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-005.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Arm differences
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | Explicit `readAssetById` to `SKILL.md` + `geneformer.md` | None |
# MAGIC | **Volume path** | `test_with/models/geneformer_v1` | `test_without/models/geneformer_v1` |
# MAGIC | **UC model** | `geneformer_v1_10m` | `geneformer_v1_10m_baseline` |
# MAGIC | **Endpoint** | `geneformer-v1-10m` | `geneformer-v1-10m-baseline` |
# MAGIC
# MAGIC ### What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (GPU\_SMALL? GPU\_MEDIUM?)
# MAGIC * How to handle HF repo restructure (subfolder selection)
# MAGIC * Pickle token dict loading strategy
# MAGIC * Dependency versions
# MAGIC * Serving contract shape (gene IDs in, embeddings out)

# COMMAND ----------

# DBTITLE 1,oss-006: geneformer BioNeMo (hard) — READY
# MAGIC %md
# MAGIC # oss-006: Geneformer V2 (NVIDIA BioNeMo) Deploy (Path B)
# MAGIC
# MAGIC **Status**: 🟡 **Ready** — full prompts, not yet run in dedicated test notebooks.
# MAGIC
# MAGIC **Key test**: Deploy Path B — NVIDIA BioNeMo checkpoint (`nvidia/geneformer_V2_316M`). Requires `trust_remote_code=True`, `transformer_engine[pytorch]` dep, Ampere+ GPU. Must NOT require Docker/BioNeMo container.
# MAGIC
# MAGIC **Prerequisite**: Ensure `references/models/geneformer.md` covers Path B / BioNeMo variant.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Baseline arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` renamed to `SKILL.md.off` → save to `results/baseline/oss-006.txt`
# MAGIC
# MAGIC > Deploy Geneformer using the NVIDIA BioNeMo checkpoint (nvidia/geneformer\_V2\_316M) as a Model Serving endpoint on Databricks. Use the TransformerEngine-aware checkpoint directly via AutoModel — no Docker or BioNeMo container needed. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/geneformer_v2`. Register the model as `<catalog>.skills.geneformer_v2_316m_baseline` and name the endpoint `geneformer-v2-316m-baseline`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Enable `scale_to_zero_enabled=True` on the served entity to avoid idle GPU charges. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-006.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Skill arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` active → save to `results/with_skill/oss-006.txt`
# MAGIC
# MAGIC > Deploy Geneformer using the NVIDIA BioNeMo checkpoint (nvidia/geneformer\_V2\_316M) as a Model Serving endpoint on Databricks. Use the TransformerEngine-aware checkpoint directly via AutoModel — no Docker or BioNeMo container needed. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/geneformer_v2`. Register the model as `<catalog>.skills.geneformer_v2_316m` and name the endpoint `geneformer-v2-316m`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Enable `scale_to_zero_enabled=True` on the served entity to avoid idle GPU charges. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project’s HLS model-deployment skill and Geneformer model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/references/models/geneformer.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-006.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Arm differences
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | Explicit `readAssetById` to `SKILL.md` + `geneformer.md` | None |
# MAGIC | **Volume path** | `test_with/models/geneformer_v2` | `test_without/models/geneformer_v2` |
# MAGIC | **UC model** | `geneformer_v2_316m` | `geneformer_v2_316m_baseline` |
# MAGIC | **Endpoint** | `geneformer-v2-316m` | `geneformer-v2-316m-baseline` |
# MAGIC
# MAGIC ### What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (GPU\_SMALL? GPU\_MEDIUM? — needs Ampere+)
# MAGIC * `trust_remote_code` handling
# MAGIC * `transformer_engine[pytorch]` dependency pinning
# MAGIC * Serving contract shape
# MAGIC * Whether to use BioNeMo’s native tokenizer or re-implement

# COMMAND ----------

# DBTITLE 1,oss-007: midnight (hard) — READY
# MAGIC %md
# MAGIC # oss-007: Midnight Pathology Model Deploy
# MAGIC
# MAGIC **Status**: 🟡 **Ready** — full prompts, not yet run in dedicated test notebooks.
# MAGIC
# MAGIC **Key test**: Image-based model (histopathology tiles → embeddings). Different modality from scRNA-seq models.
# MAGIC
# MAGIC **Prerequisite**: Create `references/models/midnight.md` if not already present.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Baseline arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` renamed to `SKILL.md.off` → save to `results/baseline/oss-007.txt`
# MAGIC
# MAGIC > Deploy kaiko-ai/midnight (pathology tile-embedding model, MIT license) as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/kaiko-ai/midnight (code: https://github.com/kaiko-ai/midnight). It takes histopathology image tiles as input and produces embedding vectors. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/midnight`. Register the model as `<catalog>.skills.midnight_baseline` and name the endpoint `midnight-baseline`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-007.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Skill arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` active → save to `results/with_skill/oss-007.txt`
# MAGIC
# MAGIC > Deploy kaiko-ai/midnight (pathology tile-embedding model, MIT license) as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/kaiko-ai/midnight (code: https://github.com/kaiko-ai/midnight). It takes histopathology image tiles as input and produces embedding vectors. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/midnight`. Register the model as `<catalog>.skills.midnight` and name the endpoint `midnight`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project’s HLS model-deployment skill and Midnight model reference using `readAssetById` (type `file`) at these workspace paths:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/references/models/midnight.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-007.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Arm differences
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | Explicit `readAssetById` to `SKILL.md` + `midnight.md` | None |
# MAGIC | **Volume path** | `test_with/models/midnight` | `test_without/models/midnight` |
# MAGIC | **UC model** | `midnight` | `midnight_baseline` |
# MAGIC | **Endpoint** | `midnight` | `midnight-baseline` |
# MAGIC
# MAGIC ### What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (GPU\_SMALL? GPU\_MEDIUM?)
# MAGIC * Image preprocessing pipeline (tile size, normalization)
# MAGIC * Serving contract shape (base64 image in, embedding out?)
# MAGIC * Dependency management (torchvision, timm, etc.)

# COMMAND ----------

# DBTITLE 1,oss-008: ESM-2 (edge) — READY
# MAGIC %md
# MAGIC # oss-008: ESM-2 Protein Model Deploy (Edge: Unknown Model)
# MAGIC
# MAGIC **Status**: 🟡 **Ready** — full prompts, not yet run in dedicated test notebooks.
# MAGIC
# MAGIC **Key test**: Edge case — model not in any skill reference. Tests whether the generic SKILL.md patterns (sys.modules purge, code-bundle stripping, GPU\_SMALL, etc.) still help when there’s no model-specific reference.
# MAGIC
# MAGIC **Note**: No `references/models/esm2.md` needed — that’s the point of this edge case.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Baseline arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` renamed to `SKILL.md.off` → save to `results/baseline/oss-008.txt`
# MAGIC
# MAGIC > Deploy the ESM-2 protein language model (facebook/esm2\_t6\_8M\_UR50D) as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/facebook/esm2_t6_8M_UR50D. It takes amino acid sequences as input and produces per-residue embeddings. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_without/models/esm2`. Register the model as `<catalog>.skills.esm2_t6_8m_baseline` and name the endpoint `esm2-t6-8m-baseline`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-008.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Skill arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` active → save to `results/with_skill/oss-008.txt`
# MAGIC
# MAGIC > Deploy the ESM-2 protein language model (facebook/esm2\_t6\_8M\_UR50D) as a Model Serving endpoint on Databricks. The model is at https://huggingface.co/facebook/esm2_t6_8M_UR50D. It takes amino acid sequences as input and produces per-residue embeddings. Use catalog `<catalog>`, schema `skills`. Store downloaded artifacts under `/Volumes/<catalog>/skills/test_with/models/esm2`. Register the model as `<catalog>.skills.esm2_t6_8m` and name the endpoint `esm2-t6-8m`. Make the notebook fully re-runnable: on first run, delete any pre-existing endpoint and UC model versions; on subsequent runs, skip cleanup if the endpoint is already in READY state (only tear down if it’s in a FAILED state or doesn’t exist). If a deployment fails, diagnose the error from endpoint events/logs, fix the root cause, and retry — don’t leave the notebook in a broken state. Write the code and explain your decisions.
# MAGIC >
# MAGIC > **Before writing any code**, read the project’s HLS model-deployment skill using `readAssetById` (type `file`) at this workspace path:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern (e.g., a particular MLflow logging method, a dependency version, a wrapper structure), use that exact pattern — do not substitute your own approach even if it seems simpler or more familiar. Before writing each code cell, re-check the relevant skill section to ensure your implementation matches. If you deviate from a skill recommendation, state why explicitly in a code comment.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, model versions created, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-008.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Arm differences
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | `SKILL.md` only (no model-specific ref) | None |
# MAGIC | **Volume path** | `test_with/models/esm2` | `test_without/models/esm2` |
# MAGIC | **UC model** | `esm2_t6_8m` | `esm2_t6_8m_baseline` |
# MAGIC | **Endpoint** | `esm2-t6-8m` | `esm2-t6-8m-baseline` |
# MAGIC
# MAGIC ### What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Compute type (CPU may suffice for 8M params)
# MAGIC * Whether to use HF pipeline or custom pyfunc
# MAGIC * Tokenizer handling (ESM has its own)
# MAGIC * Serving contract shape (sequence in, embedding out)

# COMMAND ----------

# DBTITLE 1,oss-009: CPU-only advisory (edge) — READY
# MAGIC %md
# MAGIC # oss-009: CPU-Only Deployment Advisory (Edge)
# MAGIC
# MAGIC **Status**: 🟡 **Ready** — full prompts, not yet run in dedicated test notebooks.
# MAGIC
# MAGIC **Key test**: Advisory edge case — no deployment, just guidance. Tests whether the skill helps the agent give better compute/architecture advice when GPU isn’t available. Lighter prompt — no volume/model/endpoint naming needed, but still needs dev-log, runtime capture, and export.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Baseline arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` renamed to `SKILL.md.off` → save to `results/baseline/oss-009.txt`
# MAGIC
# MAGIC > I want to deploy a single-cell embedding model (like TEDDY or Geneformer) on Databricks but I only have a Classic CPU cluster (no GPU). What are my options? Consider: which models can run on CPU, what are the performance tradeoffs, can Model Serving use CPU workload types, and are there quantization or distillation alternatives? Write your analysis as code cells with markdown explanations — include concrete code examples where possible (e.g., deploying a small model on CPU, benchmarking inference time). Use catalog `<catalog>`, schema `skills`.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/baseline/oss-009.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Skill arm prompt
# MAGIC
# MAGIC Paste into a **fresh** Genie Code chat with `SKILL.md` active → save to `results/with_skill/oss-009.txt`
# MAGIC
# MAGIC > I want to deploy a single-cell embedding model (like TEDDY or Geneformer) on Databricks but I only have a Classic CPU cluster (no GPU). What are my options? Consider: which models can run on CPU, what are the performance tradeoffs, can Model Serving use CPU workload types, and are there quantization or distillation alternatives? Write your analysis as code cells with markdown explanations — include concrete code examples where possible (e.g., deploying a small model on CPU, benchmarking inference time). Use catalog `<catalog>`, schema `skills`.
# MAGIC >
# MAGIC > **Before writing any code**, read the project’s HLS model-deployment skill using `readAssetById` (type `file`) at this workspace path:
# MAGIC > - `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/.assistant/skills/open-weight-models/SKILL.md`
# MAGIC >
# MAGIC > **Treat these skill references as authoritative.** When a skill specifies a concrete implementation pattern or compute guidance, use that — do not substitute your own approach.
# MAGIC >
# MAGIC > **Important**: Do NOT read, search, or reference any notebook or file whose name starts with `gt_` in this project — those are ground-truth references and reading them would contaminate the evaluation.
# MAGIC >
# MAGIC > At the end, list every skill from the Skill Registry that you loaded or consulted while developing this notebook.
# MAGIC >
# MAGIC > **Development log (required)**: Before the export step, add a markdown cell titled "Development Log" that documents every code fix, debug iteration, and reversal you made during development. For each fix, record: (1) the cell number, (2) the error message, (3) the root cause, and (4) how many attempts it took to resolve. Include a summary table with: total unique bugs encountered, total fix iterations, number of cells requiring fixes, and any known limitations.
# MAGIC >
# MAGIC > **Runtime capture (required)**: Before the export step, add a code cell titled "Runtime and Environment Info" that prints: Python version, platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type (serverless vs classic — check if DBR version starts with `client.` or pyspark contains `databricks.connect`), environment (check `DATABRICKS_AI_ENV` + `DATABRICKS_ENV_VERSION` env vars for AI Runtime version), key package versions (databricks-sdk, mlflow, transformers, torch, numpy, pandas, pyspark), and GPU info (device name, VRAM) if available. This is eval metadata for reproducibility — do not skip it.
# MAGIC >
# MAGIC > **Final step**: Export this notebook’s source (Databricks `.py` format) to `/Workspace/Users/<workspace-user>/PROJECTS/hls-skills-tests/<project-folder>/results/with_skill/oss-009.txt` using the Workspace REST API (`GET /api/2.0/workspace/export` with `format=SOURCE`, then base64-decode and write to the output path).
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ### Arm differences
# MAGIC
# MAGIC | | Skill arm | Baseline arm |
# MAGIC |---|---|---|
# MAGIC | **Skill reference** | `SKILL.md` only (no model-specific ref) | None |
# MAGIC | **Volume/model/endpoint** | N/A (advisory, not deploy) | N/A |
# MAGIC
# MAGIC ### What the prompt does NOT prescribe (skill should decide)
# MAGIC
# MAGIC * Which models to recommend for CPU
# MAGIC * Whether to actually deploy or just advise
# MAGIC * Quantization/ONNX strategies
# MAGIC * Benchmark methodology
