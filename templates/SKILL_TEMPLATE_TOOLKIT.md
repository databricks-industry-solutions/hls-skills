<!-- Template: Toolkit Sub-type — for skills that are collections of independent modules.
     For linear pipelines, use SKILL_TEMPLATE.md.
     For database/API wrappers, use this template and organize Core API by query type. -->
---
name: "toolkit-name-here"
# Description rules (AGENTS.md):
#   - Length ≤ 1024 chars; first 120 chars carry discovery weight
#   - Lead with tool name or domain keyword — NOT stop verbs
#   - Cross-references ("For X use Y") go at the END
description: "<Tool/Domain keyword> <what it does>. <Module coverage>. <Disambiguation: for X use Y>."
license: "Databricks License"
---

# Toolkit Name Here

## Overview

Brief description of the toolkit (2-3 sentences). What domain does it cover? What kinds of tasks does it enable?

## When to Use

<!-- 5+ items from the USER'S TASK perspective.
     Include 1-2 alternative tool comparison bullets. -->

- Use case 1: description
- Use case 2: description
- Use case 3: description
- Use case 4: description
- Use case 5: description
- Use `alternative-skill` instead when [condition]
- For [different task], use `other-skill`; this toolkit is for [specific scope]

## Prerequisites

- **MCP / tools**: list required MCP servers or packages
- **Inputs**: common identifier or data formats
- **Rate limits**: note any API throttling if relevant

## Quick Start

```text
# Minimal common use-case
```

## Core API

<!-- Organize by functional module or query type (4-8 subsections). -->

### Module 1: Lookup / Resolve

```text
# Resolve names to IDs
```

### Module 2: Search

```text
# Search entities
```

### Module 3: Fetch Details

```text
# Retrieve full records
```

### Module 4: Filter / Transform

```text
# Filter or transform results
```

## Key Concepts

### Concept 1: Identifier Model

Brief explanation of IDs / entity types the agent must understand.

### Concept 2: Score / Ranking Semantics

Brief explanation of any scores or precedence fields.

## Common Workflows

### Workflow 1: Standard Lookup Pipeline

**Goal**: Describe what this workflow achieves end-to-end.

```text
# Step 1: resolve
# Step 2: search
# Step 3: enrich
# Step 4: format
```

### Workflow 2: Batch Processing

**Goal**: Process multiple inputs.

```text
# Loop over inputs and aggregate results
```

## Key Parameters

| Parameter | Module | Default | Range / Options | Effect |
|-----------|--------|---------|-----------------|--------|
| `param1` | Search | `"default"` | options | Controls search mode |
| `param2` | Filter | `0.5` | `0.0`-`1.0` | Score threshold |
| `param3` | All | `10` | `1`-`50` | Result limit |

## Best Practices

1. **Always resolve IDs first**: Avoid ambiguous string matches downstream
2. **Prefer primary sources**: Cite Open Targets / PubChem / PubMed links in outputs
3. **Don't over-fetch**: Cap result sets before enrichment steps

## Common Recipes

### Recipe: Quick Summary

When to use: Fast overview without full enrichment.

```text
# Short snippet
```

### Recipe: Export Table

When to use: Produce a markdown or CSV-ready table.

```text
# Short snippet
```

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Ambiguous match | Multiple entities share a name | Disambiguate by entity type / organism |
| Empty search | Wrong vocabulary | Try synonyms or alternate IDs |
| Truncated results | Limit too low | Raise limit or paginate |
| Stale fields | Schema drift | Prefer documented fields; check references/ |

## Related Skills

- **related-skill-1** — how this connects (e.g., upstream / downstream)
- **related-skill-2** — alternative for a related use-case

## Bundled Resources

- `references/<topic>.md` — API cheatsheets / query templates
- `scripts/<name>.py` — reusable helpers

## References

- [Tool documentation](https://example.com/docs)
- [API reference](https://example.com/api)
