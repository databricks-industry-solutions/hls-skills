# Matplotlib & Seaborn — Publication-Quality Static Figures

Subskill of `scientific-figures`. Load when the user needs a static figure for
a journal, poster, report, or PDF export.

## When to use matplotlib/seaborn vs. other libraries

- **Use matplotlib/seaborn** when the output is a static image (PDF, PNG, SVG)
  for a manuscript, poster, regulatory submission, or slide deck.
- **Switch to Plotly** if the user needs hover, zoom, or interactive filtering.
- **Switch to domain subskill** if the chart type is biopharma-specific (KM,
  forest, etc.) — but come back here for rendering settings.

## RC params: the full publication preset

The hub SKILL.md has the default `_FIGURE_STYLE` dict. **The hub's width,
font-size, aspect and visual-review rules override anything in this file.**
Presets here only set the figure width; fonts stay at the hub's 8 pt.

### Width presets

```python
# Single panel: 90% of a 3.5 in journal column
SINGLE_PANEL = {"figure.figsize": (3.15, 2.6)}

# 2+ panels across: 90% of letter text width (6.5 in)
MULTI_PANEL = {"figure.figsize": (5.85, 4.0)}

# Line art (no raster content): raise export resolution
LINE_ART = {"savefig.dpi": 600}
```

- Single-panel figures may drop non-title text to 7.5 pt only if 8 pt does
  not fit (hub rule). Set this per figure, not in a preset.
- Inherently wide single plots (waterfall, swimmer, KM with at-risk table,
  labelled volcano) start at 3.15 in and may widen up to 5.85 in **only if
  visual review shows the 3.15 in version is cramped**.
- No journal-specific presets (e.g. 7 pt Nature style) and no poster preset.
  Posters, slides or a specific journal's style guide are used only when the
  user explicitly asks, with the size they specify.

### Applying a preset

```python
import matplotlib as mpl

def apply_style(preset: dict):
    """Merge a preset on top of the base scientific defaults."""
    mpl.rcParams.update(_FIGURE_STYLE)  # base from SKILL.md
    mpl.rcParams.update(preset)
```

## Layout recipes

### Inch-budgeted layout (default for every figure)

Size the panels first (aspect per the hub rules), then budget labels,
gutters, legends and margins in inches, and check the total against the width
rule. Place axes explicitly. Automatic layout engines (`tight_layout`,
`constrained_layout`) decide panel shape from leftover space and are the main
cause of stretched panels; use them only for quick single-panel exploratory
plots.

```python
W = 5.85                          # width rule: multi-panel (single panel: 3.15)
PANEL_W, PANEL_H = 2.1, 2.1       # aspect chosen for the data, not leftover space
LEFT, GAP, RIGHT = 0.65, 0.60, 0.40   # y-label + ticks, gutter, right margin
BOTTOM, TOP = 0.55, 0.45              # x-label + ticks, title
N_COLS = 2

total = LEFT + N_COLS * PANEL_W + (N_COLS - 1) * GAP + RIGHT
assert total <= W + 1e-6, f"Layout needs {total:.2f} in > {W} in; re-budget"
H = BOTTOM + PANEL_H + TOP

fig = plt.figure(figsize=(W, H))
axes = [fig.add_axes([(LEFT + i * (PANEL_W + GAP)) / W, BOTTOM / H,
                      PANEL_W / W, PANEL_H / H]) for i in range(N_COLS)]
# ... plot ...
fig.savefig("out.pdf", bbox_inches=None)   # keep the designed size
print(f"Figure size: {W:.2f} x {H:.2f} in")
```

If a legend sits beside a panel, its width comes out of the same budget. If the
budget does not close at 8 pt, change the layout (legend below, fewer panels
per row), never the font size.

### Multi-panel with subplot_mosaic

```python
fig, axes = plt.subplot_mosaic(
    [["A", "B"],
     ["C", "C"]],
    figsize=(5.85, 4.6),
    gridspec_kw={"left": 0.11, "right": 0.97, "bottom": 0.10, "top": 0.93,
                 "wspace": 0.35, "hspace": 0.45},
)
for label, ax in axes.items():
    ax.set_title(label, loc="left", fontweight="bold", fontsize=11)
```

### Panel labels (A, B, C)

```python
def label_panels(axes, fontsize=11, x=-0.05, y=1.05):
    """Add A, B, C labels to a list or dict of axes."""
    if isinstance(axes, dict):
        items = list(axes.items())
    else:
        items = [(chr(65 + i), ax) for i, ax in enumerate(axes.flat)]
    for label, ax in items:
        ax.text(x, y, label, transform=ax.transAxes,
                fontsize=fontsize, fontweight="bold", va="top")
```

## Color palette recipes

All colors come from [color.md](color.md): `PALETTE`, `CATEGORICAL`
(black, red, navy, orange, teal, grey; max 6), `family_shades()` for related
groups, and `BRAND_SEQ` / `BRAND_DIV` colormaps. Do not define other palettes
here.

### Treatment-arm palette (color.md Rule 3)

```python
# Two arms: control black, treatment red (Rule 1).
ARM_COLORS_2 = {"control": PALETTE["black"], "treatment": PALETTE["red_500"]}

# Multi-arm: placebo grey, dose arms one navy family light -> dark, comparator red.
ARM_COLORS = {
    "placebo":    PALETTE["grey_500"],
    **family_shades(["low_dose", "mid_dose", "high_dose"], "navy", ordered=True),
    "comparator": PALETTE["red_500"],
}
```

### Continuous colormaps

```python
import matplotlib.cm as cm

cmap_seq = cm.viridis     # sequential default (or BRAND_SEQ for a single-hue ramp)
cmap_div = BRAND_DIV      # diverging navy -> white -> red, use TwoSlopeNorm(vcenter=0)
cmap_cyc = cm.twilight    # cyclic (e.g., phase data)
```

## Seaborn integration

### Context and style

```python
import seaborn as sns

# set_context / set_style OVERWRITE font sizes and other rcParams.
# Call them FIRST, then apply _FIGURE_STYLE so the hub's 8 pt rule wins.
# Never use "paper" (shrinks fonts) or "talk"/"poster" unless the user asks.
sns.set_context("notebook")
sns.set_style("ticks")         # cleanest for publications
mpl.rcParams.update(_FIGURE_STYLE)
sns.despine()                  # remove top + right spines
```

### When to use seaborn vs. raw matplotlib

| Use seaborn for | Use matplotlib for |
|---|---|
| Statistical summaries (violin, box, swarm) | Full control over every element |
| Faceted grids (`FacetGrid`, `catplot`) | Custom insets, broken axes |
| Quick heatmaps (`heatmap`, `clustermap`) | Specialized biopharma chart types |
| Regression overlays (`lmplot`, `regplot`) | Annotations, arrows, custom legends |

### Heatmap with proper formatting

```python
def styled_heatmap(data, ax=None, cmap="viridis", fmt=".2f",
                   cbar_label="", **kwargs):
    """Publication-ready heatmap with sane annotation defaults."""
    ax = ax or plt.gca()
    sns.heatmap(
        data, ax=ax, cmap=cmap, annot=True, fmt=fmt,
        linewidths=0.5, linecolor="white",
        cbar_kws={"label": cbar_label, "shrink": 0.8},
        **kwargs,
    )
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
    return ax
```

## Common pitfalls

1. **Clipped or stretched layouts**: budget space in inches (see layout
   recipe) and confirm by viewing the render (hub visual review). Do not rely
   on `tight_layout` / `constrained_layout` or `bbox_inches="tight"` to fix
   layout problems; they change panel shape or saved size.
2. **DPI mismatch**: `fig.dpi` controls display; `savefig.dpi` controls export.
   Set both explicitly.
3. **Font not embedded in PDF**: use `mpl.rcParams["pdf.fonttype"] = 42` to
   embed TrueType fonts (required by most journals).
4. **Legend overlapping data**: use `bbox_to_anchor=(1.02, 1)` with
   `loc="upper left"` to push legend outside.
5. **White edges in PNG**: set `savefig.facecolor = "white"` explicitly;
   `transparent=True` can cause issues with some viewers.

```python
# PDF font embedding (add to setup cell)
mpl.rcParams["pdf.fonttype"] = 42   # TrueType
mpl.rcParams["ps.fonttype"] = 42
```

## Violin plots on skewed / high-N data

Violin plots on data with extreme outliers (clinical lab values, sensor
readings, financial distributions, high-throughput assay QC) often produce
needle-thin tails that make the bulk of the distribution unreadable. Apply
these rules:

1. **Clip the display data** at the 99th (or 95th) percentile before passing to
   `violinplot`. Compute statistics (median, Q1/Q3) on the **full** unclipped
   data so they remain accurate.
2. **Subsample jitter** to ~3% of points (floor of ~200). Full scatter above
   ~5K cells becomes an opaque blob that hides the violin shape.
3. **Violin fill alpha 0.6.** Lower (0.35) washes out; higher (0.8) hides the
   jitter behind the fill.
4. **Structural lines at 1.5 lw.** Median as a solid line; Q1/Q3 as thinner
   dashed lines (0.8 lw) so they don't compete.
5. **Fixed `figsize` from the width rule** (3.15 in single panel, 5.85 in
   multi-panel) with the inch-budgeted layout. `constrained_layout` tends
   to stretch violin panels horizontally.
6. **Don't annotate clipping on the plot.** Mention it in the figure caption
   instead — on-plot annotations collide with legends.

```python
import numpy as np

_CLIP_PCTILE = 99
_JITTER_FRAC = 0.03
_RNG = np.random.default_rng(42)

raw = df[metric].dropna().values
clip_hi = np.percentile(raw, _CLIP_PCTILE)
data = raw[raw <= clip_hi]          # display data
med = np.median(raw)                # stats from full data
q1, q3 = np.percentile(raw, [25, 75])

parts = ax.violinplot(data, positions=[0], showmedians=False,
                      showextrema=False)
for pc in parts["bodies"]:
    pc.set_facecolor(color)
    pc.set_alpha(0.6)
    pc.set_edgecolor(color)
    pc.set_linewidth(1.5)

# Subsampled jitter strip
n_show = max(int(len(data) * _JITTER_FRAC), 200)
idx_sub = _RNG.choice(len(data), size=n_show, replace=False)
jitter = _RNG.normal(0, 0.04, size=n_show)
ax.scatter(jitter, data[idx_sub], s=0.3, alpha=0.3,
           color=PALETTE["grey_700"], rasterized=True, zorder=2)

# Median + quartiles
ax.hlines(med, -0.18, 0.18, colors="black", linewidths=1.5, zorder=3)
for q in (q1, q3):
    ax.hlines(q, -0.10, 0.10, colors="black", linewidths=0.8,
              linestyles="--", zorder=3)
```

## Grouped violin recipe (multiple conditions per panel)

When comparing two or more conditions (e.g. samples, treatment arms) across
several metrics, place them **side-by-side within each panel** rather than in
separate figures. This lets the reader compare directly.

Key parameters:
- Offset each condition’s violin to a different x-position (e.g. -0.35, +0.35).
- Use the same `violin_width` for all to keep shapes comparable.
- Shared horizontal reference lines (e.g. QC thresholds) span the full panel.
- Panel labels (A, B, C) in the upper-left corner, 8 pt bold.
- A shared colour legend at the bottom of the figure, with enough bottom margin
  (`bbox_to_anchor` y ≈ 0.01) to clear x-tick labels.

```python
from matplotlib.patches import Patch

_FS = 8             # hub rule: 8 pt for all text, titles >= 8 pt
_LW = 1.5           # uniform structural line width

conditions = categorical_colors(["Sample A", "Sample B"])   # color.md: black, red
positions  = {"Sample A": -0.35, "Sample B": 0.35}
metrics    = [("n_genes", "Genes detected"), ("total_counts", "Total UMI counts")]

fig, axes = plt.subplots(1, len(metrics), figsize=(5.85, 3.4))   # multi-panel width rule
fig.subplots_adjust(left=0.13, right=0.97, bottom=0.22, top=0.86, wspace=0.50)
fig.suptitle("QC Distributions", fontsize=_FS, fontweight="bold", y=0.97)

for panel_idx, (ax, (col, label)) in enumerate(zip(axes, metrics)):
    ax.text(-0.18, 1.06, chr(65 + panel_idx), transform=ax.transAxes,
            fontsize=_FS, fontweight="bold", va="top")  # A, B, C

    for cond_name, color in conditions.items():
        pos = positions[cond_name]
        # ... violin + jitter per condition (see recipe above) ...

    ax.set_ylabel(label, fontsize=_FS, fontweight="bold")
    ax.set_xticks(list(positions.values()))
    ax.set_xticklabels(list(conditions.keys()), fontsize=_FS,
                       fontweight="bold")
    ax.tick_params(axis="y", labelsize=_FS)
    sns.despine(ax=ax)

# Shared colour legend
handles = [Patch(facecolor=c, edgecolor=c, label=n, alpha=0.6)
           for n, c in conditions.items()]
fig.legend(handles=handles, loc="lower center", ncol=len(conditions),
           fontsize=_FS, frameon=False, bbox_to_anchor=(0.5, 0.01))
```

## Statistical annotation

For adding significance brackets (p-values) to bar/box plots:

```python
from scipy import stats

def add_significance(ax, x1, x2, y, p_value, height=0.02):
    """Add a significance bracket between two x positions."""
    stars = "ns" if p_value > 0.05 else "*" if p_value > 0.01 else "**" if p_value > 0.001 else "***"
    ax.plot([x1, x1, x2, x2], [y, y + height, y + height, y],
            lw=0.8, color="black")
    ax.text((x1 + x2) / 2, y + height, stars,
            ha="center", va="bottom", fontsize=11)
```

## Accessibility check

Before finalizing any figure, verify:

- [ ] Colorblind-safe palette (use `colorspacious` or
  [Coblis simulator](https://www.color-blindness.com/coblis-color-blindness-simulator/))
- [ ] Sufficient contrast: line colors distinct from background
- [ ] Redundant encoding: don't rely on color alone — add markers, line styles,
  or hatching for key distinctions
- [ ] Font sizes and width follow the hub rules, confirmed on the rendered
  image (hub "Mandatory visual review")
