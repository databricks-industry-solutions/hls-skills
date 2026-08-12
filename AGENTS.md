# HLS Skills — Authoring Guide

Canonical guide for authoring Health & Life Sciences agent skills in this repository.
`CLAUDE.md` is only a compatibility import shim; update this file when authoring rules change.

Layout inspired by [SciAgent-Skills](https://github.com/jaechang-hits/SciAgent-Skills) templates and categories — without a central registry.

## Directory Layout

```
├── AGENTS.md
├── templates/
│   ├── SKILL_TEMPLATE.md           ← Pipeline
│   ├── SKILL_TEMPLATE_TOOLKIT.md   ← Toolkit / database-style
│   └── SKILL_TEMPLATE_PROSE.md     ← Guide
├── integration-templates/          ← AGENTS / Cursor / Windsurf consumer snippets
└── skills/
    ├── target-discovery/
    ├── hit-to-lead/
    └── compound-assessment/
```

Each skill lives at:

```
skills/{category}/{skill-name}/SKILL.md
```

Optional siblings next to `SKILL.md`: `references/`, `assets/`, `scripts/`.

---

## Workflow: Topic → Skill

### Step 1. Determine which skill template to use

| Criteria | → Pipeline / Toolkit / Database | → Guide |
|----------|----------------------------------|---------|
| Primary content | Tool calls, MCP workflows, code | Concepts, decision frameworks |
| User action | "Run this analysis" | "Decide how to approach this" |

| Sub-type | When | Template |
|----------|------|----------|
| **Pipeline** | Linear input→process→output | `templates/SKILL_TEMPLATE.md` |
| **Toolkit** | Multiple independent modules | `templates/SKILL_TEMPLATE_TOOLKIT.md` |
| **Database** | API / MCP query wrapper | `templates/SKILL_TEMPLATE_TOOLKIT.md` (organize by query type) |
| **Guide** | Prose decision framework | `templates/SKILL_TEMPLATE_PROSE.md` |


### Step 2. Author the skill

1. Copy the matching template into `skills/{skill-name}/SKILL.md`
2. Folder name must match frontmatter `name` (lowercase, hyphens, ≤64 chars)
3. Prefer `{tool-or-domain}-{purpose}` naming (e.g. `druggable-targets`, `adme-assessment`)
4. Keep `SKILL.md` concise; put long queries / API cheatsheets in `references/`

### Step 3. Description Rules

The `description` field is the discovery hook agents use before loading the full file.

- ≤ 1024 characters; put tool/domain keywords in the **first 120 characters**
- Lead with keywords, not stop verbs (`Use`, `A`, `An`, `The`, `Query`, `Fetch`, `Run`)
- Put disambiguation (`For X use Y`) at the **end**
- No promotional adjectives (`powerful`, `comprehensive`, `state-of-the-art`)

### Step 4. Bundled Resources

| Directory | Use for |
|-----------|---------|
| `references/` | On-demand markdown: GraphQL, API fields, decision tables |
| `assets/` | Static templates / fixtures used as-is |
| `scripts/` | Runnable helpers (>~80 lines or repeated boilerplate) |

### Step 5. Testing and evaluation (TBD)
1. Unit tests for code snippets in a `tests` subfolder within your skill
2. Ensure your skill reliably loads in Genie Code
3. Design 3-5 benchmarking tasks
4. Report Genie Code performance on those tasks with and without your skill
5. Peer testing can be done during the pull request.

---

## Quality Checklist

- [ ] Frontmatter has `name`, `description` (and `license` when known)
- [ ] `name` matches parent folder
- [ ] Correct template / sub-type
- [ ] "When to Use" written from the user's task perspective
- [ ] Required sections present for the chosen template
- [ ] References cite sources with URLs
- [ ] No verbatim copy-paste from proprietary docs

---

## Progressive Disclosure

1. **Metadata** — `name` + `description` for discovery
2. **Instructions** — full `SKILL.md` when activated
3. **Resources** — `references/`, `assets/`, `scripts/` only as needed
