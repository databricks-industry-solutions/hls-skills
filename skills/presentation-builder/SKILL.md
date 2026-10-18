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
  cited to its source) and never types a number by hand. GOVERNS the output: refuses
  row-level PHI in a shareable file (de-identify first) and suppresses small distribution
  cells. Run the vetted entrypoints in scripts/build_deck.py and scripts/ground.py — do not
  hand-write deck HTML. For building the cohort use cohort-builder; to de-identify first use
  phi-deidentifier.
category: Others
summary: Turn a cohort, dataset, model, or analysis into a grounded, PHI-safe, shareable HTML deck.
version: 0.1
author: Zachary Phillips
license: Databricks License
---

# HLS Presentation Builder — Grounded, Governed, Shareable Decks

## Overview

Turns a finished HLS artifact into a **self-contained HTML presentation a stakeholder can
open in any browser and share** — no server, no login, no PowerPoint. The deck renders onto
a frozen design framework (fixed 1920×1080 canvas scaled to fit, keyboard/click navigation,
one-slide-per-page "Save as PDF", Databricks branding), so the author only supplies a
*slide spec* and the figures. The two things that make the output trustworthy are built in:
every number on a data slide is **grounded** in the real artifact (pulled by `ground.py` and
cited to its source table/column), and the file is **governed** (it will not embed row-level
PHI — a shareable deck of a cohort uses aggregates or a de-identified view).

It runs on the **execution model**: Genie Code calls the vetted entrypoints and reports
their output. It does not hand-write the ~400-line deck shell (that is frozen in
`scripts/deck_framework.py`), does not invent a figure (those come from `ground.py`), and
does not decide a table is safe to screenshot (the governance gate does).

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

TABLE = "catalog.schema.my_cohort"

# 1) GOVERN: confirm the table is safe to present (blocks sample PHI; allows aggregates).
prof = ground.assert_shareable(TABLE, allow_sample_rows=False, profile="my-profile")

# 2) GROUND: pull real figures (each returns a `source` string to print on the slide).
head  = ground.cohort_summary(TABLE, profile="my-profile")          # N rows / N subjects
payer = ground.column_distribution(TABLE, "payer", profile="my-profile")  # bar data, small cells suppressed

# 3) ASSEMBLE a spec from those figures (never hand-type a number).
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

# 4) BUILD a single self-contained .html the user can open and share.
print(build_deck.build_deck(spec, "~/Downloads/my_cohort_deck.html"))
```

## Workflow

### Step 1 — Identify the artifact and the story

Confirm what is being presented (cohort / dataset / model / analysis) and the audience
(clinical, data, security, exec). Pick 5–8 slides. Keep one idea per slide.

### Step 2 — Govern before you ground (`ground.assert_shareable`)

Always gate a table-backed deck first.

```python
ground.assert_shareable(TABLE, allow_sample_rows=False)   # aggregates: always OK
# allow_sample_rows=True RAISES PhiLeakError if the table still has direct identifiers.
```

If you need patient-level sample rows in the deck and the table has PHI, **stop and
de-identify first with `phi-deidentifier`**, then build from the governed view. The gate
also reports quasi-identifiers (age, sex, race, ZIP3) for your awareness.

### Step 3 — Ground every figure (`ground.py`)

Pull the numbers from the data; never type them. Each helper returns a `source` string —
put it in the tile `caption` or the slide `notes` so the deck is self-citing.

| Helper | Returns | Use on slide |
|--------|---------|--------------|
| `cohort_summary(table)` | `n_rows`, `n_subjects` | `metrics` tile |
| `numeric_summary(table, col)` | `min/max/avg/median/count` | `metrics` tile |
| `column_distribution(table, col)` | `bars` (small cells < k suppressed) | `bar_chart` |
| `profile_table(table)` | row count, columns, PHI scan | sanity / lineage |

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
to the recipient that it is grounded in `<table>` and carries aggregates only / a governed
view.

## Key Parameters

| Parameter | Where | Meaning |
|-----------|-------|---------|
| `spec["slides"]` | `build_deck` | the slides, each a layout dict (see `references/deck_framework.md`) |
| `spec["accent"]` | `build_deck` | optional `#hex` brand accent override (default `#ff3621`) |
| `theme` | per slide | `"light"` (default) or `"dark"` |
| `allow_sample_rows` | `ground.assert_shareable` | `False` = aggregates only (safe); `True` raises on PHI |
| `small_cell_k` | `ground.column_distribution` | suppress categories under this count (default `11`) |
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
- **No PHI in a shareable file.** `assert_shareable(..., allow_sample_rows=True)` raises on
  a table with direct identifiers; distribution cells under `k` (default 11) are suppressed.
- **No editing the frozen framework.** `deck_framework.py` is the locked shell; styling
  changes go in `layouts.COMPONENT_CSS` or the per-slide spec, never in the framework block.

## Troubleshooting

- **`PhiLeakError` on `assert_shareable`** — the table still has direct identifiers and you
  asked for sample rows. Build from a `phi-deidentifier` view, or present aggregates only
  (`allow_sample_rows=False`).
- **A distribution looks short / a category is missing** — small cells (`< small_cell_k`)
  are suppressed by design; check the returned `suppressed` count, lower `k` only if the
  population and policy allow it.
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
| `scripts/ground.py` | Grounded reads (counts/distributions/summaries) + PHI classifier & governance gate |
| `references/deck_framework.md` | Deck-spec contract + full layout vocabulary reference |
| `references/grounding_recipes.md` | SQL recipes for grounding figures + the PHI/small-cell rules |
| `examples/build_example_deck.py` | Runnable worked example (a cohort readout deck) |
| `tests/` | Offline unit tests (framework emission, renderer safety, PHI gate) |

Design framework adapted from the OpenDesign deck runtime (open-design.ai); HIPAA Safe
Harbor identifiers per 45 CFR §164.514(b)(2).

## Evaluation

Offline unit tests (`tests/test_presentation_builder.py`, no warehouse) assert the three
invariants: the frozen framework is emitted verbatim (navigation + print survive), the
renderers are deterministic and HTML-escape all content (an unknown layout / empty deck /
bad theme fails loud), and the PHI gate blocks sample rows from an identifier-bearing table
while still allowing aggregates. Run `python3 -I -m pytest tests/ -q`.
