# HLS Skills

Agent skills for Health & Life Sciences / drug-discovery workflows. Each skill is a `SKILL.md` folder that teaches coding agents (Claude Code, Cursor, and others following the [Agent Skills](https://agentskills.io/specification) standard) how to run domain workflows with MCP tools such as Open Targets, PubChem, and PubMed.

Repo layout and skill templates follow the patterns in [SciAgent-Skills](https://github.com/jaechang-hits/SciAgent-Skills) (templates + categories only — skills here are HLS-specific).

## Installation

```bash
# Install all skills into .claude/skills
curl -sSL https://raw.githubusercontent.com/databricks-industry-solutions/hls-skills/main/install_skills.sh | bash

# Specific skills
curl -sSL https://raw.githubusercontent.com/databricks-industry-solutions/hls-skills/main/install_skills.sh | bash -s -- adme-assessment hit-identification

# Cursor
curl -sSL https://raw.githubusercontent.com/databricks-industry-solutions/hls-skills/main/install_skills.sh | bash -s -- --cursor

# Claude + Cursor
curl -sSL https://raw.githubusercontent.com/databricks-industry-solutions/hls-skills/main/install_skills.sh | bash -s -- --both
```

From a local checkout:

```bash
./install_skills.sh --local
./install_skills.sh --local --cursor
./install_skills.sh --list
```

## Available Skills

| Skill | Category | Description |
|-------|----------|-------------|
| **druggable-targets** | target-discovery | Prioritize druggable targets for a disease (Open Targets + PubMed) |
| **hit-identification** | hit-to-lead | Find small-molecule hits for a gene/protein (Open Targets + PubChem) |
| **adme-assessment** | compound-assessment | ADME / drug-likeness via PubChem |
| **safety-assessment** | compound-assessment | Safety / toxicity via PubChem + PubMed |

## Repository Layout

```
hls-skills/
├── AGENTS.md                 # Skill authoring guide
├── CLAUDE.md                 # Compatibility shim → AGENTS.md
├── install_skills.sh
├── templates/                # Pipeline / toolkit / guide templates
├── integration-templates/    # Consumer snippets for Codex / Cursor / Windsurf
├── .claude-plugin/           # Claude Code plugin manifest
└── skills/
    ├── target-discovery/
    ├── hit-to-lead/
    └── compound-assessment/
```

Each skill:

```
skills/<category>/<skill-name>/
├── SKILL.md          # Required
├── references/       # Optional — loaded on demand
├── assets/           # Optional
└── scripts/          # Optional
```

## Creating a Skill

1. Read [AGENTS.md](AGENTS.md)
2. Copy the right template from `templates/`
3. Place it at `skills/<category>/<skill-name>/SKILL.md`
4. Ensure frontmatter `name` matches the folder name

| Template | Use when |
|----------|----------|
| `SKILL_TEMPLATE.md` | Linear pipeline |
| `SKILL_TEMPLATE_TOOLKIT.md` | Toolkit or database/MCP API surface |
| `SKILL_TEMPLATE_GUIDE.md` | Decision guide |

## License

Licensed under the Databricks License. See [LICENSE.md](LICENSE.md) and [NOTICE.md](NOTICE.md).
