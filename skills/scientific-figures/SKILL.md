---
name: scientific-figures
description: >
  Guidance for generating publication-quality scientific and biopharma figures
  in Databricks notebooks and apps. Covers static plots (matplotlib/seaborn),
  interactive visualizations (Plotly), 3-D protein structure rendering
  (py3Dmol, Molstar), and domain-specific biopharma chart types (Kaplan-Meier,
  forest plots, waterfall, swimmer, volcano). Load this skill when the user
  asks to create, style, or export any scientific figure, plot, chart, or
  molecular visualization — or when migrating a notebook visualization into a
  Databricks App. Also load proactively for any life sciences research workflow
  — regardless of specific domain — because biological data analysis always
  produces figures as a side-effect even when the user's stated goal is
  "analyze" rather than "visualize".
category: Others
summary: Publication-quality scientific and biopharma figures for notebooks, apps, and reports.
author: Peter Hawkins
version: 0.5
license: Databricks
---

# Scientific Figures Skill

## Overview

This is the hub skill. It defines shared quality standards (size, fonts,
color, layout, export) that apply to every figure, and routes to the right
subskill reference file based on the visualization context. Subskill files
live under `references/` and are loaded on demand — do not load them all up
front.

## When to Use

- User asks to create, style, or export a scientific figure, plot, or chart in a Databricks notebook
- User needs a publication- or report-ready figure (journal PDF/PNG export, correct DPI and font sizes)
- User asks for an interactive visualization (hover, zoom, dashboard embed) or is migrating a notebook plot into a Databricks App
- User asks to render a protein structure, molecular surface, or binding site in 3-D (PDB/mmCIF)
- User asks for a biopharma domain chart: Kaplan-Meier, forest plot, waterfall, swimmer, volcano, dose-response, CONSORT
- Any life sciences analysis workflow that will produce figures as a side effect, even if the user only asked to "analyze"

## Workflow

1. **Route**: match the request to subskill reference file(s) using the decision table below. Always load `references/color.md` alongside any rendering subskill.
2. **Set up**: emit the notebook environment setup snippet (below) before the first figure.
3. **Plan the layout**: apply the pre-render planning rules (legend placement, colorbar placement, panel count and width) before writing plotting code.
4. **Render**: write the figure code in its own cell, separate from expensive compute.
5. **Review visually**: fetch and inspect the rendered image against the design requirements checklist — mandatory for every figure (see "Mandatory visual review").
6. **Export**: save both PDF and PNG with `bbox_inches='tight'`; for LaTeX-embedded figures, check effective font size after scaling.

## Decision: which subskill to load

| Signal in the request | Load subskill |
|---|---|
| **Any figure** (always load, alongside the rendering subskill) | [color.md](references/color.md) |
| Static plot, publication PDF/PNG, journal submission, poster | [matplotlib-seaborn.md](references/matplotlib-seaborn.md) |
| Interactive plot, hover tooltips, zoomable, HTML export, dashboard embed | [plotly-interactive.md](references/plotly-interactive.md) |
| Protein structure, PDB, mmCIF, molecular surface, binding site, 3-D render | [protein-structure-3d.md](references/protein-structure-3d.md) |
| Protein-protein interface, chain contacts, interface residues, distance labels (only when asked; load with the protein subskill) | [protein-interface.md](references/protein-interface.md) |
| KM curve, forest plot, waterfall, swimmer, volcano, CONSORT, dose-response | [biopharma-domains.md](references/biopharma-domains.md) |

If the request spans multiple subskills (e.g. "interactive KM curve"), load
both the domain subskill and the rendering subskill.

## Shared quality standards

Apply these to EVERY figure regardless of library. **These rules override any
conflicting size, font or layout value in a subskill.**

### Resolution and sizing

- **Print / PDF**: 300 DPI minimum, 600 DPI for line art.
- **Screen / notebook**: 150 DPI is sufficient.
- **Databricks Apps**: render at the container size; let the layout engine handle
  responsiveness. The width rule below does not apply to app components.

#### Figure width (hard rule, applies to notebook and paper figures alike)

| Layout | Total figure width | Derivation |
|---|---|---|
| **Single panel** (one plot) | **~3.15 in** | 90% of one journal column (3.5 in) |
| **2+ panels side by side** | **~5.85 in** | 90% of letter text width (8.5 in page minus 1 in margins = 6.5 in) |

- The width covers **everything**: panels, legends, colorbars, panel letters
  and margins. Legends do not get extra width beyond the limit.
- Never exceed 5.85 in for a static figure. If the content does not fit,
  reduce panels per row, move legends below, shorten labels, or split the
  figure. There is no "full-page 10 in" option (10 in is a page *height*).
- **Inherently wide single plots** (KM with at-risk table, forest with
  estimate column, waterfall, swimmer, labelled volcano) start at 3.15 in and
  may widen up to 5.85 in only if the visual review shows they are cramped.
- **Single-panel figures with long labels**: if a single-panel figure has
  category labels (axis ticks, legend entries) long enough that 3.15 in would
  leave less than 50% of the width for the actual plot area, use 5.85 in and
  mark it as `figure*` (full-width) in LaTeX. This is common with biological
  ontology terms, tissue names, and multi-word categories.
- **Exempt:** interactive views (Plotly in notebooks/apps, 3-D viewers) are
  sized to their container; fonts still follow the 8 pt rule. Their static
  exports follow the width rule.
- **Posters, slides, or a specific journal's style guide**: only when the
  user explicitly asks, using the size they specify. No default presets.
- Height follows from the panel aspect rules below, not the other way round.
- At 150 DPI these widths render at ~470 px and ~880 px in the notebook.

### Color

All color rules live in [color.md](references/color.md): the company palette, the
color-by-count order (black → red → navy → orange → teal → grey, max 6 hues),
shade families for related groups, fixed semantic colors, cross-panel
consistency and colormaps. Load it for every figure.

- **Background**: white (`#FFFFFF`) for publications. For notebooks and apps,
  respect the Databricks theme if detectable; otherwise default to white.

### Typography

- **Font family**: `Arial` or `Helvetica` for journals (universal support).
  `Inter` or `Source Sans Pro` for digital/app contexts.
- **Font size (hard rule, at final printed size)**: **8 pt for all text** —
  axis labels, tick labels, legends, colorbar labels, annotations, on-plot
  labels and panel letters.
  - **Titles** (figure and panel): **at least 8 pt**, bold. They may be
    larger, but never smaller.
  - **7.5 pt is the absolute floor.** Nothing goes below it.
  - If text does not fit at 8 pt, change the layout (fewer panels per
    row, legend below, shorter labels, fewer on-plot labels). Do not shrink
    the font.
  - For figures embedded in a LaTeX report, "8 pt" means the *effective*
    size after LaTeX scales the figure to the column width. See "Font size
    compensation" under Export.
  - Posters: scale up proportionally from 8 pt.
- **Bold axis labels and tick labels** by default — they read better at
  typical journal column widths. Drop bold only if a specific journal style
  guide prohibits it (e.g. some Cell Press templates). Title is always bold.
- **No `suptitle` for figures destined for LaTeX.** The LaTeX `\caption{}`
  serves as the figure title. A matplotlib `fig.suptitle()` creates a
  duplicate title that either gets clipped (without `bbox_inches='tight'`) or
  extends the PDF beyond the figsize (with tight), distorting the dimensions
  LaTeX expects. For notebook-only figures, suptitle is fine — keep it at
  `y≤0.98` with adequate `subplots_adjust(top=...)` to prevent overlap with
  panel titles.
- **Long titles must wrap.** If a title exceeds ~40 characters at the target
  figure width, insert a `\n` to wrap to two lines and add `pad=12` to
  prevent collision with the plot area. This applies to `ax.set_title()`,
  colorbar labels, and legend titles.

### Pre-render layout planning

Before writing the plotting code, make these decisions based on the data:

**Legends:** Count the legend entries and estimate the longest label length.
If entries × label length won't fit inside the axes at 8 pt, place the legend
outside — below the figure with `bbox_to_anchor=(0.5, -0.1)`, `loc='upper
center'`, and `ncol≥2`. Never rely on a wrapper library's default legend
placement for figures with >3 categories or labels >20 characters — auto-placed
legends overflow the axes unpredictably.

**Colorbars:** If a colorbar is present, decide placement before rendering.
Vertical colorbars on the right waste margin in narrow figures — use horizontal
at top or bottom for figures ≤3.15 in wide. For multi-panel figures, prefer a
single shared colorbar rather than one per panel.

**Wrapper library overrides:** Many plotting libraries (seaborn, plotly,
domain-specific wrappers) auto-place legends and colorbars outside the axes.
When using any wrapper library:
1. Suppress the auto-legend (the library's equivalent of "no legend") and
   build a manual `fig.legend()` with explicit `bbox_to_anchor` inside the
   figure bounds.
2. If the library adds an auto-colorbar, render first (`make_figure()` or
   equivalent), then find and hide the auto-placed colorbar axis, and add
   your own with controlled positioning via `fig.add_axes()`.
3. The specific suppression mechanism varies by library — check its docs.
   The principle is always the same: take control away from the default and
   place elements explicitly.

### Layout

- Use a fixed `figsize` in inches set by the width rule above. For multi-panel
  figures, **size the panels first, then budget legends, gutters and margins
  in inches**, and place axes explicitly (`fig.add_axes` in inch-derived
  fractions, or `GridSpec` with computed ratios). Never let leftover space
  after legends decide the panel shape — that is what produces stretched plots.
  `tight_layout()` / `constrained_layout=True` are acceptable for quick
  single-panel exploratory plots only.

#### Panel aspect ratio (hard rule)

- **Equal aspect (`ax.set_aspect("equal", adjustable="datalim")` or
  `"box"`) is required whenever x and y share units or the geometry is
  meaningful**: 2-D embeddings (e.g. PCA, t-SNE, UMAP), spatial /
  geographic / image coordinates, x-vs-y of the same quantity (predicted vs
  observed, replicate vs replicate, with a y = x line), correlation matrices
  and heatmaps (square cells), 2-D structure projections and maps.
- **Otherwise choose the box aspect for the data**, not the leftover space:
  ~1:1 to 4:3 for scatter, violin, box and bar panels; wider (up to ~2:1) for
  time series, KM curves and dose-response. Avoid panels taller than wide
  unless the data is inherently vertical (forest plots, ranked lists,
  swimmer plots).
- Plots of the same type in one figure share the same panel size.
- Remove chartjunk: no background grid by default (add light grid only when it
  aids value reading, e.g. bar charts). Remove top and right spines for scatter
  and line plots.
- Legend outside the plot area when >3 items; inside (upper-right or best) for
  ≤3 items.
- Multi-panel: use `subplot_mosaic` or `GridSpec` for complex layouts. Label
  panels A, B, C in the upper-left corner, 8 pt bold.

### Export

#### Default: always save both PDF and PNG

- **Always save both formats** when figures may be used in a report or shared.
  PDF for vector quality in LaTeX; PNG at 300 DPI for previews, slides, and
  web. The `save_figure` helper below defaults to `formats=("pdf", "png")`.
- **PDF** (`.pdf`): preferred for LaTeX `\includegraphics`. Vector text, axes,
  and spines stay crisp at any zoom. Preferred over SVG for LaTeX workflows.
- **PNG** (`.png`): 300 DPI raster. Use for notebook display, slides, and web.
  Never `.jpg` for figures with text or line art.
- **Always save with `bbox_inches='tight'` for both PDF and PNG.** This
  prevents clipping of titles, legends below axes, rotated tick labels, and
  colorbar labels that extend beyond the figsize — the most common source of
  broken figure PDFs. To keep saved dimensions predictable for LaTeX, design
  all content to fit within the figsize (see "Pre-render layout planning"
  below) — then `bbox_inches='tight'` acts as a safety net that captures any
  slight overhang without significantly changing the page size. If a figure's
  tight-cropped dimensions differ substantially from its figsize, that signals
  content is extending outside and the layout needs adjustment. Always print
  the final figure size in the cell output.
- For Plotly: `write_image` (requires kaleido) for static export;
  `write_html` for interactive sharing.

#### Font size compensation for report-embedded figures

When figures are embedded in a LaTeX report via
`\includegraphics[width=0.95\columnwidth]`, LaTeX scales each figure from its
saved width to the column width. Because `bbox_inches='tight'` crops each
figure differently (legends, colorbars, long labels all change the bounding
box), the saved PDF widths vary — and so do the effective font sizes after
scaling.

**Default workflow (tight bbox with compensation):**

1. **Start at 8 pt** for all text (rcParams + every explicit `fontsize=` call).
   Use `sns.set_context("paper", font_scale=0.8)` before `rcParams.update()`
   so seaborn/scanpy internals also use small fonts.
2. **Save with `bbox_inches='tight'`** (the default).
3. **Check the saved PDF width** by reading the MediaBox:
   ```python
   import re
   with open(pdf_path, "rb") as f:
       match = re.search(rb'/MediaBox\s*\[\s*[\d.]+\s+[\d.]+\s+([\d.]+)\s+[\d.]+\s*\]', f.read())
   saved_width_in = float(match.group(1)) / 72
   ```
4. **Calculate the effective font size** after LaTeX scaling:
   ```
   effective_pt = source_pt × (target_width / saved_width)
   ```
   where `target_width` is `0.95 × \columnwidth` (~6.18 in for REVTeX
   preprint).
5. **If effective size is off target**, adjust the source font size:
   ```
   adjusted_pt = round(target_pt × (saved_width / target_width), 1)
   ```
   Clamp: never let the effective size fall below **7.5 pt**.
6. **Re-render** with the adjusted font size and re-save. One iteration is
   usually sufficient — tight-bbox cropping is deterministic for a given
   layout.

**Audit all font sources.** Hardcoded `fontsize=N` calls, rcParams, and
seaborn context all contribute. When changing font sizes, grep for *every*
`fontsize=` in the notebook — not just the ones matching the current value.
Different cells may have been set independently.

**When to use manual layout instead:**

If the user needs pixel-exact font consistency across all figures (e.g. strict
journal style requirements), switch to non-tight saving:
- Remove `bbox_inches='tight'` (set `savefig.bbox` to `"standard"`)
- Use explicit `fig.subplots_adjust(left=..., right=..., ...)` per figure
- All figures save at exactly the `figsize` width → uniform scaling
- This requires more per-figure iteration to avoid clipping, but guarantees
  identical effective font sizes across all figures

#### Rasterization for large scatter plots (hybrid vector+raster PDFs)

Pure vector PDFs of scatter plots with >5,000 points become enormous and slow
to render. Use matplotlib's `rasterized=True` on the scatter artist to produce
**hybrid PDFs**: vector text, axes, spines, and legends with rasterized data
points. This gives crisp text at any zoom while keeping file size manageable.

```python
# Hybrid rasterization: vector chrome, raster data
ax.scatter(x, y, s=1, alpha=0.4, rasterized=True)  # data points rasterized
# Text, axes, legends remain vector — crisp at any zoom
```

When to use `rasterized=True`:
- 2-D embeddings (PCA, t-SNE, UMAP — typically 5K–100K+ points)
- Dense diagnostic scatter plots (e.g. residuals, QC metrics)
- Any scatter with >5,000 points

When NOT to rasterize:
- Bar charts, violin plots, box plots, line plots (already low element count)
- Heatmaps (use `imshow` which is raster by default)
- Dot plots (low element count)

**Wrapper-library caveat:** Some domain plotting libraries (e.g. scanpy,
seaborn) pass `rasterized=` internally. If passing it again raises
`TypeError: got multiple values for keyword argument 'rasterized'`, set
rasterization on the axes instead:
`ax.set_rasterization_zorder(1)` (rasterizes everything below zorder 1;
data points default to zorder 0, text and axes are higher).

### Data ethics in figures

- Follow the workspace PHI rules: never plot individual patient identifiers.
  Aggregate to cohort, arm, or compound level for any figure that may be shared.
- Axis labels must include units. Y-axis should start at zero for bar charts
  unless there is a strong analytical reason not to (document the reason in a
  comment).
- Do not truncate axes to exaggerate effects without explicit annotation.

## Notebook workflow

**Always split expensive compute from plot rendering.** Put data loading,
metric computation, and threshold calculations in their own cell(s). Put the
figure-drawing code in a separate downstream cell that only reads the computed
variables. This lets you iterate on aesthetics (fonts, colors, sizing) without
re-running the expensive pipeline — a round-trip that often takes minutes for
large or compute-heavy datasets.

## Mandatory visual review (every figure, every render)

A figure is not done until the agent has **looked at the rendered image** and
fixed what it sees. Code that runs without error is not evidence that the
figure is correct.

**Hard rule: every figure gets at least one visual review.** No exceptions.
After `runAsset` on any cell that produces a figure, the agent's next action
MUST be `getAssetExecutionResults` (or equivalent) to fetch and inspect the
rendered image. Do not add the next cell, do not proceed to the next analysis
step, until the review is done. This applies to intermediate figures, final
figures, and exploratory plots alike.

**"Cell ran without errors" is not a visual review.** A cell can succeed while
producing overlapping text, clipped legends, or distorted aspect ratios —
matplotlib does not raise exceptions for layout problems. The only way to
catch these is to look at the pixels. If the image cannot be fetched (e.g.
context limits), state that explicitly ("I could not fetch the rendered image
for visual review") rather than silently skipping the check.

**After fixing a figure, re-fetch and re-review.** The fix itself may introduce
new problems (e.g. moving a legend below may collide with x-axis labels).
Every edit-run cycle must end with a fresh visual inspection.

### Review procedure

1. **Render, then view.** After running the plotting cell, fetch the rendered
   image (e.g. `getAssetExecutionResults` for the cell) and inspect it. If the
   run result only returns image metadata, fetch it explicitly.
2. **Confirm it is the new render.** Print the figure size (and any changed
   parameter) in the cell output. If the image looks identical to the
   previous version after a code change, verify the live values in the
   session and re-fetch before drawing conclusions.
3. **Check against the design requirements** (see below).
4. **Fix and repeat** until the requirements pass (up to 3 rounds). Then
   report to the user what was checked and any residual issue that could not
   be fixed, instead of reporting the figure as finished.

Never describe a figure's appearance, or call it complete, without having
viewed the current render.

### Design requirements checklist

These are the pass/fail criteria for every figure. Each item is either met
or not met — there is no "close enough."

| # | Requirement | Pass condition | Common failure |
|---|---|---|---|
| R1 | **Width** | Figure width matches the width rule (3.15 in single-panel, ≤5.85 in multi-panel). Saved file matches designed size. | `tight_layout` or `bbox_inches='tight'` silently changed the width. |
| R2 | **Aspect ratio** | Equal aspect where required (embeddings, spatial, correlation). Otherwise panels are ~1:1 to 4:3. Nothing looks stretched or squashed. | `set_aspect` missing on embedding plots; leftover space dictating panel shape. |
| R3 | **No text overlap** | No overlapping or clipped text, labels, legends, or panel letters. All text fully visible. | Long legend entries or axis labels running into adjacent panels or data. |
| R4 | **No dead space** | No large empty gutters, oversized margins, or wasted whitespace. | `right=0.72` leaving 28% empty when legends are short. |
| R5 | **Font sizes** | 8 pt for all text (7.5 pt floor). Titles ≥8 pt bold. Any hardcoded `fontsize=` below 7.5 is a failure. For report-embedded figures, check effective size after LaTeX scaling. | Legend or tick labels dropped below 7.5 pt "to fit". |
| R6 | **Color** | Palette from color.md only. Count order respected. Max 6 hues. Same category = same color across panels. Neighbors distinguishable. | Default matplotlib colors used instead of company palette. |
| R7 | **Legends** | Complete (every visual encoding explained). Not redundant with on-plot labels. Readable names (no raw column names or opaque IDs). | Legend shows internal identifiers instead of human-readable names. |
| R8 | **Axis labels** | Every axis has a label. Units included where applicable. | Embedding axes unlabeled; count axis missing units. |

### Two-tier review standard

**Standard review (interactive analysis):** Every figure gets at least one
pass through the checklist. Fix any R3 (text overlap) or R5 (font size)
failures immediately — these are never acceptable. For R1, R2, R4, R6–R8,
fix if possible within 1–2 edits; note residual issues to the user if not.

**Report-generation review (PDF/LaTeX export):** Figures destined for a
report or publication must pass **all 8 requirements** before export. The
agent must iterate (up to 3 rounds) until all pass, or explicitly flag which
requirements could not be met and why. A figure that fails any requirement
must not be silently included in a report.

### Acknowledging the review

After reviewing, state what you checked and any issues found — even if
everything passed. Example: "Reviewed: 5.85×4.0 in, equal aspect on embeddings,
no text overlap, 10pt legend (single-panel floor), palette correct." If you
cannot state what you checked, you did not review.

## Notebook environment setup snippet

When generating the first figure in a notebook session, emit this setup cell
before the figure code:

```python
import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns

# -- Scientific figure defaults ------------------------------------------------
_FIGURE_STYLE = {
    # Canvas
    "figure.figsize": (5.85, 4.0),   # multi-panel max width; single panel 3.15 in
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",      # safety net; content should fit in figsize; see Export
    "savefig.pad_inches": 0.05,
    "savefig.transparent": False,
    # Font
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    # 8 pt everywhere; titles >= 8 pt; absolute floor 7.5 pt
    "font.size": 8,
    "axes.titlesize": 8,
    "figure.titlesize": 8,
    "axes.titleweight": "bold",
    "figure.titleweight": "bold",
    "axes.labelsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "legend.title_fontsize": 8,
    # Axes
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": False,
    "axes.linewidth": 0.8,
    # Lines and markers
    "lines.linewidth": 1.5,
    "lines.markersize": 5,
    # Legend
    "legend.frameon": False,
    # Color
    "axes.prop_cycle": mpl.cycler(
        color=["#000000", "#D62728", "#3A6EA5", "#F28C28", "#1BA7A6", "#8C8C8C"]
    ),  # color.md Rule 1 order: black, red, navy, orange, teal, grey
    "image.cmap": "viridis",
}
# seaborn context/style OVERWRITE font sizes: call them first, then our rcParams.
# "paper" context with font_scale=0.8 keeps seaborn/scanpy internals near 8pt.
sns.set_context("paper", font_scale=0.8)
sns.set_style("ticks")
mpl.rcParams.update(_FIGURE_STYLE)

# NOTE: Some domain libraries (e.g. scanpy) override rcParams on import.
# Re-enforce after their imports: mpl.rcParams.update(_FIGURE_STYLE)

print("Scientific figure defaults applied.")
```

## Saving figures from notebooks

When the user wants to save a figure to a UC Volume or workspace path:

```python
import os

def save_figure(fig, name, path, formats=("pdf", "png"), dpi=300):
    """Save a matplotlib figure in one or more formats.

    `path` is a UC Volume or workspace directory the user has chosen — ask
    for it; do not assume a default. Always uses bbox_inches='tight' to
    prevent clipping. Design all content to fit within the figsize so tight
    acts as a safety net, not a layout tool.
    """
    os.makedirs(path, exist_ok=True)
    for fmt in formats:
        out = os.path.join(path, f"{name}.{fmt}")
        fig.savefig(out, format=fmt, dpi=dpi, bbox_inches="tight", pad_inches=0.05)
        print(f"Saved: {out}")
    w, h = fig.get_size_inches()
    print(f"Figure size: {w:.2f} x {h:.2f} in")
```

## App context detection

When the user's figure is destined for a Databricks App rather than a notebook
or PDF, switch guidance:

1. **Simple interactive chart (no complex UI)**: stay in Plotly; use
   `references/plotly-interactive.md`.
2. **Rich app with controls, forms, multi-view**: recommend migrating to a
   React + Plotly.js or React + Deck.gl stack. See the migration section in
   `references/plotly-interactive.md`.
3. **3-D molecular viewer in an app**: use Molstar (not py3Dmol). See
   `references/protein-structure-3d.md`.

## Quick reference: library selection

| Need | Library | Notes |
|---|---|---|
| Static publication figure | matplotlib + seaborn | Best control, universal journal acceptance |
| Quick EDA in notebook | seaborn / pandas `.plot()` | Fastest iteration |
| Interactive exploration | Plotly | Hover, zoom, filter; good notebook support |
| Interactive in Databricks App | Plotly (simple) or React + Plotly.js (complex) | See app migration guide |
| Protein / small molecule 3-D | **Molstar** (default: core CDN in notebooks, React in apps); py3Dmol if the user wants simple Python or asks for it | Try Molstar first; NGL only as a last resort after telling the user. See protein subskill |
| Geospatial / map overlays | Plotly Mapbox or Folium | Not covered in depth here |
| Animated figures | matplotlib FuncAnimation or Plotly frames | Use sparingly; prefer faceting |

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Saved figure width differs from `figsize` | `bbox_inches='tight'` cropped overhanging content | Content is extending outside the figsize — fix layout; treat tight as a safety net, not a layout tool |
| Overlapping or clipped text/legends | Auto-placed legend from a wrapper library, or labels too long for the width | Suppress the auto-legend; place a manual `fig.legend()` below the axes; wrap long titles with `\n` |
| `TypeError: got multiple values for keyword argument 'rasterized'` | Domain library (scanpy, seaborn) passes `rasterized=` internally | Use `ax.set_rasterization_zorder(1)` instead of passing `rasterized=True` |
| Fonts too small in a LaTeX-embedded figure | Tight-cropped PDF widths vary, so LaTeX scaling changes effective font size | Read the MediaBox width, compute effective pt, adjust source font size and re-render (see Export) |
| rcParams reset after import | Some libraries (e.g. scanpy) override rcParams on import | Re-apply `mpl.rcParams.update(_FIGURE_STYLE)` after their imports |
| Plotly static export fails | `write_image` requires kaleido | Install kaleido, or use `write_html` for interactive sharing instead |

## Guardrails

1. **Every figure gets a visual review.** Never call a figure done without fetching and inspecting the rendered image; re-review after every fix (max 3 rounds, then report residual issues).
2. **Never shrink text below 7.5 pt** to make content fit — change the layout instead.
3. **Never exceed the width rule** (3.15 in single-panel, 5.85 in multi-panel) for static figures.
4. **No individual patient identifiers in figures.** Aggregate to cohort, arm, or compound level for anything that may be shared.
5. **Do not truncate axes** to exaggerate effects without explicit annotation; bar charts start at zero unless justified in a comment.
6. Confirm with the user before heavy rendering workloads (e.g. >100k-point 3-D views or batch figure generation).

## References

- [matplotlib documentation](https://matplotlib.org/stable/index.html) — rcParams, layout engines, export
- [seaborn documentation](https://seaborn.pydata.org/) — statistical plotting contexts and styles
- [Plotly Python documentation](https://plotly.com/python/) — interactive figures and static export (kaleido)
- [py3Dmol documentation](https://pypi.org/project/py3Dmol/) — 3-D molecular visualization in notebooks
- [Molstar documentation](https://molstar.org/docs/) — 3-D molecular viewer for apps and notebooks
