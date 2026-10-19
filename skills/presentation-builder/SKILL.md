---
name: presentation-builder
description: >-
  Presentation builder that turns a finished HLS artifact — a cohort, de-identified dataset,
  model metrics, measure catalog, or analysis result in Unity Catalog — into a polished,
  shareable, self-contained HTML deck. Triggers on "make a deck/slides", "present this",
  "share this out", "write it up for stakeholders", "turn this cohort/model/analysis into a
  presentation". Renders onto a frozen 1920x1080 framework (keyboard + click navigation,
  Save-as-PDF, Databricks branding) so every deck looks identical. GROUNDS every figure in
  the real artifact via scripts/ground.py (counts, distributions, numeric summaries, each
  cited to its source) and never types a number by hand. Delegates PHI handling to the
  phi-deidentifier skill: de-identify the source first and build from its governed view; if
  phi-deidentifier is not available, asks the user whether to include or exclude PHI. Run the
  vetted entrypoints in scripts/build_deck.py and scripts/ground.py — do not hand-write deck
  HTML. For building the cohort use cohort-builder; to de-identify first use phi-deidentifier.
category: Others
summary: Turn a cohort, dataset, model, or analysis into a grounded, shareable HTML deck (PHI de-id delegated to phi-deidentifier).
version: 0.1
author: Zachary Phillips
license: Databricks License
---

# HLS Presentation Builder — Grounded, Shareable Decks

## Overview

Turns a finished HLS artifact into a **self-contained HTML presentation a stakeholder can
open in any browser and share** — no server, no login, no PowerPoint. The deck renders onto
a frozen design framework (fixed 1920×1080 canvas scaled to fit, keyboard/click navigation,
one-slide-per-page "Save as PDF", Databricks branding), so the author only supplies a
*slide spec* and the figures. What makes the output trustworthy is built in: every number on
a data slide is **grounded** in the real artifact (pulled by `ground.py` and cited to its
source table/column) and never typed by hand.

PHI handling is **delegated**, not re-implemented here: before building a deck from a
patient-level source, de-identify it with the **phi-deidentifier** skill and build from its
governed view. If `phi-deidentifier` is not available in the environment, the builder
**asks the user** whether PHI may be included — see "De-identify before you present" below.

It runs on the **execution model**: Genie Code calls the vetted entrypoints and reports
their output. It does not hand-write the ~400-line deck shell (that is frozen in
`scripts/deck_framework.py`) and does not invent a figure (those come from `ground.py`).

## When to Use

- "Turn this cohort into a deck I can send to the clinical team."
- "Make a shareable presentation of the de-identified claims dataset."
- "Present my model's evaluation metrics as slides for the review."
- "Write up this analysis / measure catalog as an HTML one-pager to share."
- "I need a readout deck for stakeholders — grounded in the real numbers, PHI-safe."
- "Export the cohort summary as slides and let me Save-as-PDF."

For building the cohort itself use **cohort-builder**; to de-identify a table before it
goes into a shareable deck use **phi-deidentifier**.

## Prerequisites

- **Compute: Python-enabled compute (serverless or a cluster) — NOT a SQL-only warehouse.**
  The entrypoints are Python functions; `ground.py` uses the Databricks SDK to execute SQL
  against a warehouse on your behalf (auto-selected, or pass `warehouse_id=`). Auth is
  ambient in-workspace, or a CLI `profile=` locally. **Rendering a deck needs no warehouse at
  all** — only the grounding step queries data.
- **Inputs**: a finished artifact to present — most often a Unity Catalog table/view
  (`catalog.schema.table`): a cohort, a de-identified dataset, a scored table, a measure
  catalog. Model metrics can come from an MLflow run / registered model you pass in as
  figures.
- **No external services** are required to render; an optional Google-Fonts link loads DM
  Sans/DM Mono and degrades gracefully to system fonts offline.

## Quick Start

```python
import sys; sys.path.insert(0, "scripts")
import ground, build_deck

# De-identify FIRST if the source holds PHI: run the phi-deidentifier skill and point TABLE
# at its governed view. If phi-deidentifier isn't available, ask the user whether to include
# or exclude PHI before building (see "De-identify before you present").
TABLE = "catalog.schema.my_cohort_deid"

# 1) GROUND: pull real figures (each returns a `source` string to print on the slide).
head  = ground.cohort_summary(TABLE, profile="my-profile")          # N rows / N subjects
payer = ground.column_distribution(TABLE, "payer", profile="my-profile")  # bar data

# 2) ASSEMBLE a spec from those figures (never hand-type a number).
spec = {
  "title": "My Cohort", "footer_left": "Databricks · HLS",
  "slides": [
    {"type": "cover", "theme": "dark", "title": "My [[cohort]]",
     "subtitle": "Grounded, governed readout."},
    {"type": "metrics", "title": "Headline", "tiles": [
      {"value": f"{head['n_subjects']:,}", "label": "Patients", "caption": head["source"]}]},
    {"type": "bar_chart", "title": "By payer",
     "chart": {"heading": "Patients by payer", "unit": "patients", "bars": payer["bars"]},
     "notes": payer["source"]},
  ],
}

# 3) BUILD a single self-contained .html the user can open and share.
print(build_deck.build_deck(spec, "~/Downloads/my_cohort_deck.html"))
```

## Workflow

### Step 1 — Identify the artifact and the story

Confirm what is being presented (cohort / dataset / model / analysis) and the audience
(clinical, data, security, exec). Pick 5–8 slides. Keep one idea per slide.

### Step 2 — De-identify before you present (delegate to `phi-deidentifier`)

This skill does **not** detect, classify, or redact PHI — that is delegated. Before building
a deck from any patient-/member-level source:

1. **Run the `phi-deidentifier` skill** on the source table. It produces a de-identified,
   k-anonymous, governed Unity Catalog view (Safe Harbor) and a readout of what was removed.
   Point the grounding step (Step 3) at **that view**, not the raw table.

2. **If `phi-deidentifier` is NOT available** in the environment — i.e. it is not installed
   in Genie or whatever LLM/agent is running this skill — **do not guess, and do not quietly
   ship PHI.** Stop and ask the user, e.g.:

   > "The `phi-deidentifier` skill isn't available here, so I can't automatically redact PHI
   > from `<table>` before putting it in a shareable deck. How would you like to proceed?
   > **(a) Include PHI** as-is in the presentation (you confirm the source is already
   > de-identified or that sharing identifiable data is acceptable), or **(b) Exclude PHI** —
   > I'll present grounded aggregates only (counts, distributions, numeric summaries) and
   > leave out patient-level rows."

   Build only after the user chooses. If they choose (b), stick to the `ground.py` aggregate
   helpers and do not place patient-level sample rows on any slide.

A non-PHI source (model metrics, a measure catalog, an already-de-identified view) needs no
de-identification step — go straight to Step 3.

### Step 3 — Ground every figure (`ground.py`)

Pull the numbers from the data; never type them. Each helper returns a `source` string —
put it in the tile `caption` or the slide `notes` so the deck is self-citing.

| Helper | Returns | Use on slide |
|--------|---------|--------------|
| `cohort_summary(table)` | `n_rows`, `n_subjects` | `metrics` tile |
| `numeric_summary(table, col)` | `min/max/avg/median/count` | `metrics` tile |
| `column_distribution(table, col)` | `bars` (top-N value counts) | `bar_chart` |
| `profile_table(table)` | row count, columns | sanity / lineage |

### Step 4 — Assemble the slide spec (vocabulary in `references/deck_framework.md`)

Layout types: `cover`, `statement`, `bullets`, `cards`, `metrics`, `bar_chart`,
`two_column`, `architecture`, `closing`. Per slide: `theme` (`light`/`dark`), `kicker`,
`title`, `subtitle`, `notes` (speaker notes), `footer_left`. Inline markup in any text:
`[[x]]` → accent highlight, `**x**` → bold. All content is HTML-escaped automatically.

### Step 5 — Build and verify (`build_deck.build_deck`)

```python
build_deck.build_deck(spec, "~/Downloads/deck.html")
# -> {path, slides, bytes, titles}
```

Open the file in a browser. Navigate with ← / → / space / click (left half = back) / `R`
to reset / `End`. **Save as PDF**: the browser print dialog emits one slide per page.

### Step 6 — Deliver

Hand over the `.html` (self-contained — email it, drop it in Drive, host it anywhere). Note
to the recipient that it is grounded in `<table>` — and, when the source held PHI, that it
was de-identified upstream with `phi-deidentifier` (or that the user explicitly approved the
PHI it contains).

## Key Parameters

| Parameter | Where | Meaning |
|-----------|-------|---------|
| `spec["slides"]` | `build_deck` | the slides, each a layout dict (see `references/deck_framework.md`) |
| `spec["accent"]` | `build_deck` | optional `#hex` brand accent override (default `#ff3621`) |
| `theme` | per slide | `"light"` (default) or `"dark"` |
| `top` | `ground.column_distribution` | keep the top-N categories by count (default `8`) |
| `profile`, `warehouse_id` | `ground.*` | CLI profile / warehouse for the grounding queries |

## Expected Outputs

- A single self-contained `.html` file at `out_path` (open in any browser, email, host anywhere).
- `build_deck.build_deck(...)` returns `{path, slides, bytes, titles}`.
- `ground.*` helpers return figures plus a `source` string to print as the slide caption.
- Navigation (←/→/space/click/`R`) and browser "Save as PDF" (one slide per page) work out of the box.

## Guardrails

- **No hand-entered figures.** Numbers on `metrics`/`bar_chart` slides must come from
  `ground.py`. If a figure isn't grounded, label it an assumption on a `statement` slide.
- **Sanity-check numeric figures before you print them.** `numeric_summary` returns `min`
  and `max` alongside `avg`/`median` on purpose — eyeball them. Real tables (especially
  synthetic ones) carry impossible outliers (e.g. an HbA1c of 246,952%), which wreck a
  **mean** while leaving the **median** sane. Prefer the median, or filter the measure to a
  plausible range, and never put a mean on a slide without checking its min/max first.
  Grounding reports what's in the data — it does not launder it.
- **De-identify PHI upstream; never ship it silently.** This skill does not redact PHI.
  For a patient-level source, run `phi-deidentifier` first and build from its governed view.
  If `phi-deidentifier` is unavailable, ask the user to include or exclude PHI (Step 2) and
  build only after they choose — do not decide on their behalf.
- **No editing the frozen framework.** `deck_framework.py` is the locked shell; styling
  changes go in `layouts.COMPONENT_CSS` or the per-slide spec, never in the framework block.

## Troubleshooting

- **The source table has PHI and `phi-deidentifier` isn't installed** — don't build yet.
  Ask the user to include or exclude PHI (Step 2); if they exclude it, present grounded
  aggregates only and omit patient-level rows.
- **A distribution looks short / a category is missing** — only the top `top` categories (by
  count, default 8) are returned; raise `top` to show more.
- **`ValueError: unknown type ...` / `theme must be ...`** — the spec has a layout type or
  theme the renderer doesn't support; see the vocabulary in `references/deck_framework.md`.
- **Fonts look like the system default** — the DM Sans/DM Mono webfont link needs network
  access; offline it falls back to system-ui by design (the deck is still self-contained).
- **Navigation / Save-as-PDF misbehaves** — do not hand-edit `deck_framework.py`; regenerate
  the deck through `build_deck` so the frozen shell is emitted verbatim.

## References

| Path | What it is |
|------|-----------|
| `scripts/build_deck.py` | Entrypoint: validate spec → render → write self-contained `.html` |
| `scripts/deck_framework.py` | **Frozen** deck shell (CSS, navigation runtime, print, protocol) |
| `scripts/layouts.py` | Pure slide renderers + the editable component CSS |
| `scripts/ground.py` | Grounded reads (counts/distributions/summaries), each cited to its source |
| `references/deck_framework.md` | Deck-spec contract + full layout vocabulary reference |
| `references/grounding_recipes.md` | SQL recipes for grounding figures + how PHI is delegated |
| `examples/build_example_deck.py` | Runnable worked example (a cohort readout deck) |
| `tests/` | Offline unit tests (framework emission, renderer safety, grounding shape) |

Design framework adapted from the OpenDesign deck runtime (open-design.ai). PHI
de-identification is delegated to the `phi-deidentifier` skill (HIPAA Safe Harbor,
45 CFR §164.514(b)(2)).

## Evaluation

Offline unit tests (`tests/test_presentation_builder.py`, no warehouse) assert the
invariants: the frozen framework is emitted verbatim (navigation + print survive), the
renderers are deterministic and HTML-escape all content (an unknown layout / empty deck /
bad theme fails loud), and the grounding reader shapes figures the way the renderers expect.
Run `python3 -I -m pytest tests/ -q`.
