# Color: Palette and Assignment Rules

Subskill of `scientific-figures`. **Load for every figure**, together with the
rendering subskill. These rules override any color value hardcoded in other
subskills or recipes.

## Company palette

> **Placeholder palette** (illustrative, not an official brand standard).
> Replace the hex values here when the official brand palette is available;
> every rule below refers to palette names, not hex codes.

### Brand families (dark to light)

| Family | 900 | 700 | 500 (core) | 300 |
|---|---|---|---|---|
| Navy | `#0B1F3A` | `#1F3F6E` | `#3A6EA5` | `#8FB3DA` |
| Red | `#7F1414` | `#A81E1F` | `#D62728` | `#F2A49C` |
| Orange | `#8A4300` | `#C25E00` | `#F28C28` | `#FBC98E` |
| Teal | `#00474B` | `#00737A` | `#1BA7A6` | `#93D9D6` |

Red 500 is matplotlib's default red (`tab:red`, `#D62728`).

### Neutrals and lights

| Name | Hex | Use |
|---|---|---|
| Black | `#000000` | First data color, axes, text |
| Grey 700 | `#4D4D4D` | Secondary text, reference / threshold lines |
| Grey 500 | `#8C8C8C` | Control / "other" category |
| Grey 300 | `#C8C8C8` | Not significant, de-emphasised data |
| Navy 50 | `#E8EEF6` | Light fills, shaded bands, box fills |
| Orange 50 | `#FEF3E6` | Highlight fills |
| Light grey | `#F2F4F7` | Panel / table backgrounds |

```python
PALETTE = {
    "black": "#000000",
    "navy_900": "#0B1F3A", "navy_700": "#1F3F6E", "navy_500": "#3A6EA5", "navy_300": "#8FB3DA",
    "red_900": "#7F1414", "red_700": "#A81E1F", "red_500": "#D62728", "red_300": "#F2A49C",
    "orange_900": "#8A4300", "orange_700": "#C25E00", "orange_500": "#F28C28", "orange_300": "#FBC98E",
    "teal_900": "#00474B", "teal_700": "#00737A", "teal_500": "#1BA7A6", "teal_300": "#93D9D6",
    "grey_700": "#4D4D4D", "grey_500": "#8C8C8C", "grey_300": "#C8C8C8",
    "navy_50": "#E8EEF6", "orange_50": "#FEF3E6", "light_grey": "#F2F4F7",
}
FAMILIES = {
    "navy":   [PALETTE[f"navy_{s}"] for s in (900, 700, 500, 300)],
    "red":    [PALETTE[f"red_{s}"] for s in (900, 700, 500, 300)],
    "orange": [PALETTE[f"orange_{s}"] for s in (900, 700, 500, 300)],
    "teal":   [PALETTE[f"teal_{s}"] for s in (900, 700, 500, 300)],
}
```

No hex values outside this palette, unless the user supplies them.

## Rule 1: colors by number of categories

| Categories | Colors (in order) |
|---|---|
| 1 | Black. Lines and markers black; filled shapes (bars, violins, boxes) black outline with white or clear interior |
| 2 | Black, Red 500 |
| 3 | Black, Red 500, Navy 500 |
| 4 | + Orange 500 |
| 5 | + Teal 500 |
| 6 | + Grey 500 |
| > 6 | Do not add hues. Use faceting, on-plot labels, or Rule 2 shades |

```python
CATEGORICAL = [PALETTE[k] for k in
               ("black", "red_500", "navy_500", "orange_500", "teal_500", "grey_500")]

def categorical_colors(categories):
    """Assign the ordered ladder; fail loud past 6 instead of inventing hues."""
    cats = list(categories)
    if len(cats) > len(CATEGORICAL):
        raise ValueError(f"{len(cats)} categories > {len(CATEGORICAL)}: "
                         "facet, label on-plot, or group into shade families (Rule 2)")
    return dict(zip(cats, CATEGORICAL))
```

- The order matters: the most important / reference category gets black,
  the main comparison gets red.
- Navy 900 / 700 are too close to black to sit next to it as data colors; use
  them for text, outlines and structure, or inside a navy shade family
  without black present.

## Rule 2: related groups get shades of one family

When categories are obviously related (dose levels, subtypes of one cell
lineage, time points, replicates of one condition), give the group one family
and vary the shade, instead of spending separate hues.

- **Ordered groups** (dose, time, grade): light to dark in order
  (300 → 500 → 700 → 900), lowest = lightest.
- **Unordered subgroups** (subtypes, clusters within a lineage): the largest
  member gets the 500 core shade, others take 700 / 300 / 900.
- One family per group; never mix families within a related group.
- Different groups in the same plot use different families, following the
  Rule 1 order (navy, red, orange, teal).
- **Warm families** (red, orange): avoid putting Orange 900 / Red 900 next to
  each other; dark oranges read as brown. Prefer 700 / 500 / 300.
- More than 4 members in a group: label on-plot or facet rather than
  interpolating extra shades.

```python
def family_shades(members, family, ordered=True):
    """Map related members to one family. ordered=True: light -> dark."""
    members = list(members)
    if len(members) > 4:
        raise ValueError(f"{len(members)} members > 4 shades: facet or label on-plot")
    shades = FAMILIES[family]                       # 900, 700, 500, 300
    if ordered:
        picks = {1: [2], 2: [3, 1], 3: [3, 2, 1], 4: [3, 2, 1, 0]}[len(members)]
    else:
        picks = {1: [2], 2: [2, 3], 3: [2, 3, 1], 4: [2, 3, 1, 0]}[len(members)]
    return {m: shades[i] for m, i in zip(members, picks)}
```

## Rule 3: fixed semantic colors

| Element | Color |
|---|---|
| Axes, text, zero line | Black (zero line 0.5 lw) |
| Reference / threshold lines | Grey 700, dashed |
| Not significant / background points | Grey 300 |
| Two arms: control vs treatment | Black, Red 500 (Rule 1) |
| Multi-arm: control / placebo | Grey 500; dose arms as a navy family, light to dark (Rule 2) |
| Up / down regulated (volcano) | Red 500 / Navy 500, NS Grey 300 |
| Response (waterfall, spider) | PR Teal 500, SD Grey 500, PD Red 500 |
| Fit line over data points | Data black, fit Red 500 |
| Confidence bands / shaded regions | Same color as the line, alpha 0.15-0.2 |
| Diagram boxes (CONSORT etc.) | Navy 50 fill, Navy 500 edge, black text |

## Rule 4: consistency

- A category has the **same color in every panel and every figure** of a
  notebook / report. Define the mapping dict once and reuse it.
- Clusters derived from a labelled category (e.g. algorithm-assigned clusters
  vs expert-annotated groups) inherit the category's family so panels can be
  compared.
- Categories that are adjacent in the plot or compared directly must not
  share a near-identical color.

## Continuous data

- **Sequential**: `viridis` or `cividis` by default. Single-hue brand ramp
  for one quantity: `light_grey` → Navy 300 → Navy 500 → Navy 900.
- **Diverging** (centered on 0 or a reference): Navy 500 → white → Red 500,
  centered with `TwoSlopeNorm`.
- Never `jet`, `rainbow`, `tab10`, `tab20`, or default Plotly sequences.

```python
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

BRAND_SEQ = LinearSegmentedColormap.from_list(
    "brand_seq", [PALETTE["light_grey"], PALETTE["navy_300"], PALETTE["navy_500"], PALETTE["navy_900"]])
BRAND_DIV = LinearSegmentedColormap.from_list(
    "brand_div", [PALETTE["navy_500"], "#FFFFFF", PALETTE["red_500"]])
# usage: ax.imshow(z, cmap=BRAND_DIV, norm=TwoSlopeNorm(vcenter=0))
```

## Accessibility

- Red 500 with black is a widely used pairing and reads well in practice.
  Where black and red lines overlap heavily, varying line style or marker
  (solid vs dashed, filled vs open) is a useful extra but not required.
- **Red and Orange together**: they rely on luminance difference (Orange 500
  is lighter). When both are lines or small markers, also vary line style or
  marker shape.
- Check that the figure still reads in grayscale for any 4+ color plot.

## Plotly

Use the same names: `color_discrete_sequence=CATEGORICAL` or
`color_discrete_map=<mapping dict>`; continuous scales from `BRAND_SEQ` /
`BRAND_DIV` stops. Never rely on Plotly's default color sequence.

## Visual review additions

During the hub's mandatory visual review, also check:
- Rule 1 order followed; no more than 6 distinct hues.
- Related groups use one family (Rule 2); no browns from dark oranges.
- Same category, same color across panels (Rule 4).
- No off-palette colors.
