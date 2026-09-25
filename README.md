# HLS Skills

Agent skills for Health & Life Sciences  workflows. Each skill is a `SKILL.md` folder that teaches Genie Code following the [Agent Skills](https://agentskills.io/specification) standard) how to run domain workflows with libraries, tools and MCP servers.


## Available Skills

| Skill | Description |
|-------|-------------|
| **bulk-rnaseq** | Analyze for top differentially expressed genes (DEG) from bulk RNA-seq count data |
| **pathway-enrichment-analysis** | Pathway enrichment for RNA-seq. Choose from ORA or GSEA |
| **cohort-builder** | Build a defensible, reproducible, feasibility-checked patient cohort from structured coded data and free-text clinical notes — grounds codes, surfaces threshold + code/note combine choices, never fabricates citations |
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
1. Follow [AGENTS.md](AGENTS.md).
2. Start from the matching file in `templates/`.
3. Put the skill at `skills/<skill-name>/SKILL.md`.
4. Folder name must match frontmatter `name`. 
5. Update the skill table in `README.md` (Table to be created).
6. Open a PR and request a second-party review.

| Template | Use when |
|----------|----------|
| `SKILL_TEMPLATE.md` | Linear pipeline |
| `SKILL_TEMPLATE_GUIDE.md` | Decision guide |

Repo layout and skill templates are inspired by the patterns in [SciAgent-Skills](https://github.com/jaechang-hits/SciAgent-Skills)


## License

Licensed under the Databricks License. See [LICENSE.md](LICENSE.md) and [NOTICE.md](NOTICE.md).
