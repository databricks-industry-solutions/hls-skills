# FAQ

## What is a skill?

A folder with a `SKILL.md` file that teaches Genie Code how to run a Health & Life Sciences workflow: which libraries, tools and MCP servers to use, and in what order. Skills follow the [Agent Skills](https://agentskills.io/specification) standard.

## How do I start using the skills?

Clone this repository into your Databricks workspace, open Genie Code, and add the cloned `skills` folder under Customizations. See [Setup](setup.md).

## Can I use the skills with agents other than Genie Code?

Yes. Any agent that supports the Agent Skills standard can load the same folders. For example, copy a skill folder into `.claude/skills/` to use it with Claude Code.

## How do I share skills across my workspace?

Run `sync_skills_git2unity.py` to register the skills in Unity Catalog. They then show up on [Unity Gateway](https://docs.databricks.com/aws/en/agents/uc-skills/) under Skills. See [Setup](setup.md).

## Why are a skill's `tests/` and `eval/` folders missing after syncing?

They are kept in Git for contributors and are never published by the sync script.

## How do I know a skill helps?

Each skill is benchmarked with and without the skill on the same tasks. See [Evaluation](evaluation.md).

## How do I report a bug, request a skill, or add my own?

[Open an issue](https://github.com/databricks-industry-solutions/hls-skills/issues/new/choose) to report a bug or request a skill. To add or update one, see [Contributing](contributing.md).

## Why does a page under `docs/guide/` look empty on GitHub?

Pages such as Setup, Contributing and Evaluation are copied from `README.md` and `CONTRIBUTING.md` when the site is built. Their source file holds only an include line, which GitHub hides. Edit the root file instead; see [DOCS.md](https://github.com/databricks-industry-solutions/hls-skills/blob/dev/DOCS.md).
