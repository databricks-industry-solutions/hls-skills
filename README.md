# <img src="docs/guide/assets/vitalskills.png" alt="Vital Skills" width="40" height="40"> Vital Skills
## Agent skills for Health & Life Sciences workflows. 
Each skill is a `SKILL.md` folder that teaches Genie Code following the [Agent Skills](https://agentskills.io/specification) standard) how to run domain workflows with libraries, tools and MCP servers.

Site: [https://databricks-industry-solutions.github.io/hls-skills/](https://databricks-industry-solutions.github.io/hls-skills/)

## Setup
<!-- Do not change this header which generates setup.md -->
#### Git clone this repo to Databricks
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

<!-- skill-catalog:start -->
| Skill | Category | What it does |
|-------|----------|--------------|
| [**bulk-rnaseq**](skills/bulk-rnaseq/SKILL.md) | Bioinformatics | Find top differentially expressed genes from bulk RNA-seq counts. |
| [**open-weight-models**](skills/open-weight-models/SKILL.md) | Bioinformatics | Package, register, validate & deploy open-weight HLS models on Databricks — e.g. TEDDY and Geneformer. |
| [**pathway-enrichment-analysis**](skills/pathway-enrichment-analysis/SKILL.md) | Bioinformatics | Pathway enrichment for RNA-seq (ORA or GSEA). |
| [**sc-rnaseq**](skills/sc-rnaseq/SKILL.md) | Bioinformatics | Analyze single-cell RNA-seq data from .h5ad files. |
| [**cohort-builder**](skills/cohort-builder/SKILL.md) | Clinical RWE | Build a reproducible, feasibility-checked patient cohort from coded + free-text clinical data. |
| [**rwe-cohortstudy**](skills/rwe-cohortstudy/SKILL.md) | Clinical RWE | Comparative effectiveness (cohort study) with propensity adjustment (matching, IPW). |
| [**payer-provider-measure-catalog**](skills/payer-provider-measure-catalog/SKILL.md) | Payer and provider | Canonical payer+provider measure catalog mapped to Unity Catalog metric views. |
| [**phi-deidentifier**](skills/phi-deidentifier/SKILL.md) | Payer and provider | HIPAA Safe-Harbor de-identify a Unity Catalog table (k-anonymity + governed view). |
| [**accelerators**](skills/accelerators/SKILL.md) | Others | Route imaging and biology-model tasks to an HLS accelerator — Pixels or Genesis Workbench — with the exact next step. |
| [**skill-eval**](skills/skill-eval/SKILL.md) | Others | Benchmark a skill: paired runs with/without it, MLflow genai.evaluate scoring, win/loss + failure taxonomy. |
<!-- skill-catalog:end -->

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

## Contributors

- [Yen Low](mailto:yen.low@databricks.com)
- [Zachary Phillips](mailto:zack.phillips@databricks.com)
- [May Merkle-Tan](mailto:may.merkletan@databricks.com)
- [Praneeth Paikray](mailto:praneeth.paikray@databricks.com)
- [Vimal Thomas Joseph](mailto:vimalthomas.joseph@databricks.com)
- [Peter Hawkins](mailto:peter.hawkins@databricks.com)
- [Rohan Parikh](mailto:rohan.parikh@databricks.com)

To add yourself, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Acknowledgements

Thanks to Eli Swanson, Douglas Moore, Parastou Eslami and Khagay Nagdimov for their advice.


