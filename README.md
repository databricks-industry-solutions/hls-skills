# <img src="vitalskills.png" alt="Vital Skills" width="40" height="40"> Vital Skills
## Agent skills for Health & Life Sciences workflows. 
Each skill is a `SKILL.md` folder that teaches Genie Code following the [Agent Skills](https://agentskills.io/specification) standard) how to run domain workflows with libraries, tools and MCP servers.


## Setup
#### git clone this repo to Databricks
Git clone this repo onto Databricks. Then open Genie Code and click on Customizations to add the cloned folder. It should point to the `skills` subfolder

#### Optional: Register and sync the skills to [Unity Gateway](https://docs.databricks.com/aws/en/agents/uc-skills/)
Run [`sync_skills_git2unity.py`](sync_skills_git2unity.py) to sync the latest skills from the repo to Unity Catalog. They also show up on Unity Gateway under Skills.

On Databricks, start Serverless or a cluster (>= 15.0 runtime) for compute. Then open the terminal ([how-to-guide](https://docs.databricks.com/aws/en/compute/web-terminal#launch-the-web-terminal)). It should already have the [Databricks CLI](https://docs.databricks.com/aws/en/compute/web-terminal#run-databricks-cli-commands) installed.
```
### To list skills
uv run sync_skills_git2unity.py --dry-run

### To publish/update skills to/on Unity Gateway
uv run sync_skills_git2unity.py --catalog <your_catalog> --schema <your_schema> --warehouse-id <your_sql_wh>
```
You can get the SQL warehouse id from the Databricks left menu bar: SQL Warehouses > select warehouse > Name. It should list the warehouse ID. More details [here](https://www.getorchestra.io/guides/how-to-retrieve-your-databricks-warehouse-id).



## Available Skills

| Skill | Description |
|-------|-------------|
| **sc-rnaseq** | Analyze single-cell RNA-seq data from .h5ad files |
| **bulk-rnaseq** | Analyze for top differentially expressed genes (DEG) from bulk RNA-seq count data |
| **pathway-enrichment-analysis** | Pathway enrichment for RNA-seq. Choose from ORA or GSEA |
| **cohort-builder** | Build a defensible, reproducible, feasibility-checked patient cohort from structured coded data and free-text clinical notes — grounds codes, surfaces threshold + code/note combine choices, never fabricates citations |
| **rwe-cohortstudy** | Perform comparative effectiveness research (aka cohort study design) with appropriate propensity score adjustment, including matching and IPW |
| **phi-deidentifier** | De-identify a structured Unity Catalog table under HIPAA Safe Harbor — enforces k-anonymity on quasi-identifiers and applies a governed view over the raw table (no second PHI copy) |
| **payer-provider-measure-catalog** | Canonical healthcare payer+provider measure catalog (care delivery, access, capacity, claims, gap-in-care, payer economics incl. MLR/PMPM) + generator that maps a customer's sources to Unity Catalog metric views |
| **oss-models** | Package, register, validate, and deploy open-source HLS models (Geneformer, scGPT, Scimilarity, AlphaFold/OpenFold, Boltz) on Databricks |
| **skill-eval** | Benchmark a skill: paired runs with and without it, MLflow `genai.evaluate` scoring, per-task win/loss comparison, failure taxonomy, standardized Evaluation report |

## Repository Layout

```
hls-skills/
├── AGENTS.md                 # Skill authoring guide
├── CLAUDE.md                 # Compatibility shim → AGENTS.md
├── templates/                # Pipeline / toolkit / guide templates
└── skills/
    ├── bulk-rnaseq/
    ├── cohort-builder/
    └── …
```

Each skill:

```
skills/<skill-name>/
├── SKILL.md          # Required
├── references/       # Optional — loaded on demand
├── assets/           # Optional
└── scripts/          # Optional
```

## Creating a Skill
See [CONTRIBUTING.md](CONTRIBUTING.md).

Repo layout and skill templates are inspired by the patterns in [SciAgent-Skills](https://github.com/jaechang-hits/SciAgent-Skills)


## License

Licensed under the Databricks License. See [LICENSE.md](LICENSE.md) and [NOTICE.md](NOTICE.md).
