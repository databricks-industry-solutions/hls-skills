<!-- Template: Pipeline Sub-type — for skills with a linear input→processing→output flow.
     For toolkit-style skills (multiple independent modules), use SKILL_TEMPLATE_TOOLKIT.md.
     For decision guides, use SKILL_TEMPLATE_GUIDE.md. -->
---
name: skill-name-here
description: <Tool/Domain keyword> <what it does>. <Inputs → outputs>. <Disambiguation: for X use Y>
# Description rules (AGENTS.md):
#   - Length ≤ 1024 chars; first 120 chars carry discovery weight
#   - Lead with tool name or domain keyword — NOT stop verbs (Use/A/An/The/Query/Fetch/Run)
#   - Cross-references ("For X use Y") go at the END
#   - No promotional adjectives (powerful/comprehensive/state-of-the-art/...)
version: 1.0.0
author: your name
license: Databricks License
---

# Skill Name Here

## Overview

Brief description of the skill (2-3 sentences). What problem does it solve? What is the expected output?

## When to Use

<!-- 5+ items. Write from the USER'S TASK perspective, not keyword-matching. -->

- Use case 1: description
- Use case 2: description
- Use case 3: description
- Use case 4: description
- Use case 5: description

## Prerequisites

- **MCP / tools**: list required MCP servers or CLIs
- **Inputs**: description of accepted identifiers or data formats
- **Environment**: any special setup needed

## Quick Start

<!-- Optional but recommended. Minimal end-to-end example (10-20 lines or short tool calls). -->

```text
# 1. Resolve input
# 2. Run core query / step
# 3. Format output
```

## Workflow

<!-- Each step SHOULD have its own example block. Target: 5-8 steps. -->

### Step 1: Resolve Input

Description of what this step does.

```text
# Example tool call or code
```

### Step 2: Retrieve / Process

Description of the processing step.

```text
# Example tool call or code
```

### Step 3: Rank / Filter

Description of prioritization or filtering.

```text
# Example tool call or code
```

### Step 4: Enrich

Description of enrichment (literature, clinical precedence, etc.).

```text
# Example tool call or code
```

### Step 5: Generate Output

Description of the deliverable format.

```markdown
| Col1 | Col2 | Col3 |
|------|------|------|
| ...  | ...  | ...  |
```

## Key Parameters

| Parameter | Default | Range / Options | Effect |
|-----------|---------|-----------------|--------|
| `param1` | `value1` | `value1`-`value3` | Controls X behavior |
| `param2` | `10` | `5`-`50` | Adjusts Y granularity |
| `param3` | `"auto"` | `"auto"`, `"manual"` | Selects Z mode |

## Common Recipes

<!-- 2-4 self-contained snippets for ALTERNATIVE APPROACHES or OPTIONAL EXTENSIONS. -->

### Recipe: Alternative Approach A

When to use: brief scenario description.

```text
# Self-contained snippet
```

### Recipe: Alternative Approach B

When to use: brief scenario description.

```text
# Self-contained snippet
```

## Expected Outputs

- Ranked table or structured summary with columns: ...
- Supporting evidence links (PubMed, Open Targets, PubChem, etc.)

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Empty results | Ambiguous input identifier | Resolve ID first; try alternate synonyms |
| Tool / MCP error | Server not configured | Check MCP server is available and authenticated |
| Too many hits | Unfiltered query | Apply score / phase / Lipinski filters |
| Conflicting evidence | Mixed literature signals | Prefer higher clinical precedence; cite both sides |

## Guardrails

1. Avoid retrying more than 3 times
2. Ask to confirm before undertaking a heavy workload

## Bundled Resources

<!-- Optional. Only include if this skill ships sibling directories next to SKILL.md. -->

- `references/<topic>.md` — long-form prose or query templates loaded on demand
- `assets/<file.ext>` — copy-paste templates or static artifacts
- `scripts/<name>.py` — runnable helpers; include docstring header (purpose + usage)

## References

- [Official docs](https://example.com/docs) — primary documentation
- [API / GraphQL reference](https://example.com/api) — query reference
