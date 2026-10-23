# FAQ

## What is a skill?
A folder with a `SKILL.md` file that teaches Genie Code how to run a Health & Life Sciences workflow, specifying which libraries, tools and MCP servers to use, and in what order. Skills follow the [Agent Skills](https://agentskills.io/specification){target="_blank" rel="noopener"} standard.


## How do I start using the skills?
Clone this repository into your Databricks workspace, open Genie Code, and add the cloned `skills` folder under Customizations. See [Setup](setup.md){target="_blank" rel="noopener"}.


## How do I know a skill helps?
Each skill is benchmarked with and without the skill on the same tasks. See [Evaluation](evaluation.md){target="_blank" rel="noopener"}.


## Can I use the skills with agents other than Genie Code?
Yes. Any agent that supports the Agent Skills standard can load the same folders. For example, copy a skill folder into `.claude/skills/` to use it with Claude Code.


## Is there a Genie Code CLI?
Yes, you can use the skills with [Genie Code CLI](https://docs.databricks.com/aws/en/genie-code/genie-code-cli){target="_blank" rel="noopener"}.


## Will the skills overload my agent and slow it down?
No. Skills use [progressive disclosure](https://agentskills.io/home#how-do-agent-skills-work){target="_blank" rel="noopener"}, so an agent only reads what the task needs:

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


## How do I share skills?
#### Option 1 
Make the folder path accessible and share the path with other users.

#### Option 2
Run [`sync_skills_git2unity.py`](https://github.com/databricks-industry-solutions/vital-skills/blob/main/sync_skills_git2unity.py){target="_blank" rel="noopener"} to register the skills in Unity Catalog. They then show up on [Unity Gateway](https://docs.databricks.com/aws/en/agents/uc-skills/){target="_blank" rel="noopener"} under Skills for other users to discover and use, provided you grant them appropriate permissions. See [Setup](setup.md){target="_blank" rel="noopener"}.


## Why are a skill's `tests/` and `eval/` folders missing after syncing?
They are kept in Git for contributors and are never published by the [`sync_skills_git2unity.py` script](https://github.com/databricks-industry-solutions/vital-skills/blob/main/sync_skills_git2unity.py){target="_blank" rel="noopener"}.


## How do I report a bug, request a skill, or add my own?
[Open an issue](https://github.com/databricks-industry-solutions/vital-skills/issues/new/choose){target="_blank" rel="noopener"} to report a bug or request a skill. To add or update one, see [Contributing](contributing.md){target="_blank" rel="noopener"}.


## Why does a page under `docs/guide/` look empty on GitHub?
Pages such as Setup, Contributing and Evaluation are copied from `README.md` and `CONTRIBUTING.md` when the site is built. Their source file holds only an include line, which GitHub hides. Edit the root file instead; see [DOCS.md](https://github.com/databricks-industry-solutions/vital-skills/blob/main/DOCS.md){target="_blank" rel="noopener"}.



