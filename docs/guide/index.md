# Vital Skills

Vital Skills is a collection of agent skills for Health & Life Sciences workflows on Databricks. Each skill is a folder with a `SKILL.md` file that follows the [Agent Skills](https://agentskills.io/specification) standard. It teaches Genie Code how to run a domain workflow with the right libraries, tools, and MCP servers.

<div class="grid cards" markdown>

-   :material-rocket-launch: **Getting started**

    ---

    Add the skills to Genie Code, or sync them to Unity Catalog.

    [:octicons-arrow-right-24: Set up](getting-started.md)

-   :material-view-grid: **Skill catalog**

    ---

    Genomics, real-world evidence, PHI de-identification, payer and provider measures, and more.

    [:octicons-arrow-right-24: Browse skills](skills/index.md)

-   :material-scale-balance: **Evaluation**

    ---

    How each skill is benchmarked with and without the skill loaded.

    [:octicons-arrow-right-24: See the method](evaluation.md)

-   :material-source-pull: **Contributing**

    ---

    Report a bug, request a skill, or add your own.

    [:octicons-arrow-right-24: Contribute](contributing.md)

</div>

## How a skill loads

Skills use progressive disclosure, so an agent only reads what the task needs:

1. **Metadata.** The agent reads each skill's `name` and `description` to decide whether it applies.
2. **Instructions.** When a skill matches, the agent loads its full `SKILL.md`.
3. **Resources.** Files in `references/`, `assets/`, and `scripts/` are opened only when the instructions call for them.

## What a skill folder contains

```text
skills/<skill-name>/
├── SKILL.md      # Required: frontmatter + instructions
├── references/   # Optional: loaded on demand
├── assets/       # Optional: templates and fixtures used as-is
├── scripts/      # Optional: runnable helpers
├── tests/        # Optional: unit tests (not published)
└── eval/         # Optional: benchmark evidence (not published)
```
