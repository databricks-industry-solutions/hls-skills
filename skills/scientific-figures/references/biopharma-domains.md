# Biopharma Domain Figures

Subskill of `scientific-figures`. Load when the user needs a domain-specific
clinical/biopharma chart type. These recipes produce publication-quality
figures using matplotlib/seaborn; for interactive versions, combine with the
Plotly subskill.

## Chart type index

| Chart | Use case | Section |
|---|---|---|
| Kaplan-Meier (KM) | Time-to-event survival analysis | [KM Curves](#kaplan-meier-curves) |
| Forest plot | Meta-analysis, subgroup hazard/odds ratios | [Forest Plots](#forest-plots) |
| Waterfall plot | Best tumor response per subject | [Waterfall Plots](#waterfall-plots) |
| Swimmer plot | Individual subject treatment duration + events | [Swimmer Plots](#swimmer-plots) |
| Volcano plot | Differential expression / biomarker significance | [Volcano Plots](#volcano-plots) |
| Dose-response | EC50/IC50 curves | [Dose-Response](#dose-response-curves) |
| CONSORT flow | Patient disposition / enrollment | [CONSORT Diagrams](#consort-flow-diagrams) |
| Spider plot | Tumor burden over time per subject | [Spider Plots](#spider-plots) |

## Shared conventions

- Import the setup cell from the hub SKILL.md before any domain figure.
- **The hub's width, font-size, aspect and visual-review rules override the
  recipes below.** Every chart here is a single plot: default width **3.15 in**.
  Inherently wide charts (KM with at-risk table, forest with estimate column,
  waterfall, swimmer, labelled volcano) may widen up to **5.85 in** only when
  the visual review shows 3.15 in is cramped.
- All text 8 pt (rcParams from the hub); do not hardcode smaller sizes. If
  labels crowd, label fewer items rather than shrink the font.
- Margins are fixed in inches with `set_margins_in` (below), not
  `tight_layout`, so the saved figure keeps its designed size.

```python
def set_margins_in(fig, left=0.6, right=0.15, bottom=0.55, top=0.35):
    """Fixed margins in inches (replaces tight_layout; keeps designed size)."""
    w, h = fig.get_size_inches()
    fig.subplots_adjust(left=left / w, right=1 - right / w,
                        bottom=bottom / h, top=1 - top / h)
```

- **Colors follow [color.md](color.md).** Define `PALETTE`,
  `categorical_colors` and `family_shades` from color.md before these
  recipes. Use `ARM_COLORS` / `ARM_COLORS_2` from `matplotlib-seaborn.md` for
  treatment arms. Semantic colors (response categories, up/down, thresholds)
  follow color.md Rule 3.
- PHI rule: never plot individual patient names or identifiers. Use
  `subject_id` (pseudonymized) or aggregate.
- Always include number-at-risk tables below KM curves.
- Label axes with units. Include the statistical test and p-value in the
  figure or caption.

## Kaplan-Meier curves

```python
import numpy as np
import matplotlib.pyplot as plt
from lifelines import KaplanMeierFitter
from lifelines.statistics import logrank_test

def plot_km(df, time_col, event_col, group_col,
            arm_colors=None, ax=None, ci_alpha=0.15,
            xlabel="Time (months)", ylabel="Survival probability",
            title="Kaplan-Meier Estimate",
            show_at_risk=True, at_risk_ticks=None):
    """
    Publication-quality KM plot with number-at-risk table.

    Parameters
    ----------
    df : DataFrame with columns for time, event (1=event), and group.
    arm_colors : dict mapping group values to hex colors.
    show_at_risk : if True, add number-at-risk table below the plot.
    at_risk_ticks : list of time points for the at-risk table.
    """
    own_fig = ax is None
    if own_fig:
        fig, ax = plt.subplots(figsize=(3.15, 3.6))   # single-plot width rule
    else:
        fig = ax.figure

    groups = sorted(df[group_col].unique())
    if arm_colors is None:
        arm_colors = categorical_colors(groups)   # color.md Rule 1; raises past 6

    kmfs = {}
    for group in groups:
        mask = df[group_col] == group
        kmf = KaplanMeierFitter()
        kmf.fit(
            df.loc[mask, time_col],
            event_observed=df.loc[mask, event_col],
            label=str(group),
        )
        kmf.plot_survival_function(
            ax=ax, color=arm_colors[group],
            ci_alpha=ci_alpha, linewidth=1.5,
        )
        kmfs[group] = kmf

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="lower left", frameon=False)

    # Number-at-risk table
    if show_at_risk:
        if at_risk_ticks is None:
            at_risk_ticks = np.linspace(0, df[time_col].max(), 6).astype(int)
        _add_at_risk_table(ax, kmfs, at_risk_ticks, arm_colors)

    # Log-rank test (pairwise for 2 groups)
    if len(groups) == 2:
        g1, g2 = groups
        result = logrank_test(
            df.loc[df[group_col] == g1, time_col],
            df.loc[df[group_col] == g2, time_col],
            event_observed_A=df.loc[df[group_col] == g1, event_col],
            event_observed_B=df.loc[df[group_col] == g2, event_col],
        )
        ax.text(0.95, 0.95, f"Log-rank p = {result.p_value:.4f}",
                transform=ax.transAxes, ha="right", va="top", fontsize=11)

    if own_fig:
        n_rows = len(groups) if show_at_risk else 0
        set_margins_in(fig, left=0.75, right=0.15,
                       bottom=0.55 + (0.2 + 0.18 * n_rows if n_rows else 0), top=0.35)
    return fig, ax


def _add_at_risk_table(ax, kmfs, ticks, arm_colors):
    """Add number-at-risk table below a KM plot."""
    fig = ax.figure
    y_offset = -0.25
    for i, (group, kmf) in enumerate(kmfs.items()):
        counts = []
        for t in ticks:
            n = int((kmf.event_table.index <= t).sum())
            at_risk = kmf.event_table.loc[
                kmf.event_table.index <= t, "at_risk"
            ]
            counts.append(int(at_risk.iloc[-1]) if len(at_risk) > 0 else 0)
        for j, (t, c) in enumerate(zip(ticks, counts)):
            ax.text(
                t, y_offset - i * 0.07, str(c),
                transform=ax.get_xaxis_transform(),
                ha="center", va="top", fontsize=11,
                color=arm_colors[group],
            )
        ax.text(
            -0.02, y_offset - i * 0.07, str(group),
            transform=ax.get_xaxis_transform(),
            ha="right", va="top", fontsize=11, fontweight="bold",
            color=arm_colors[group],
        )
```

## Forest plots

```python
def plot_forest(labels, estimates, ci_lower, ci_upper,
                null_value=1.0, xlabel="Hazard Ratio (95% CI)",
                title="Subgroup Analysis", figsize=(None, None)):
    """
    Forest plot for hazard ratios or odds ratios.

    Parameters
    ----------
    labels : list of subgroup names.
    estimates : list of point estimates (HR or OR).
    ci_lower, ci_upper : lists of CI bounds.
    null_value : reference line (1.0 for ratio, 0.0 for difference).
    """
    n = len(labels)
    # Inch budget: subgroup labels | plot area | estimate [CI] column
    LEFT_IN, AXIS_MIN_IN, RIGHT_IN = 1.2, 1.5, 1.7
    w = figsize[0] or min(max(3.15, LEFT_IN + AXIS_MIN_IN + RIGHT_IN), 5.85)
    h = figsize[1] or max(2.6, n * 0.3 + 0.9)
    figsize = (w, h)

    fig, ax = plt.subplots(figsize=figsize)
    y_pos = range(n)

    # CI lines
    for i in range(n):
        ax.plot([ci_lower[i], ci_upper[i]], [i, i],
                color=PALETTE["black"], linewidth=1.5, solid_capstyle="butt")

    # Point estimates
    ax.scatter(estimates, y_pos, color=PALETTE["black"], s=50, zorder=5)

    # Null reference line
    ax.axvline(null_value, color=PALETTE["grey_700"], linestyle="--", linewidth=0.8)

    # Labels and annotations
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.invert_yaxis()

    # Add text annotations: estimate [CI]
    for i in range(n):
        txt = f"{estimates[i]:.2f} [{ci_lower[i]:.2f}, {ci_upper[i]:.2f}]"
        ax.text(ax.get_xlim()[1] * 1.02, i, txt,
                va="center", fontsize=11, family="monospace")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    set_margins_in(fig, left=LEFT_IN, right=RIGHT_IN, bottom=0.55, top=0.35)
    return fig, ax
```

## Waterfall plots

```python
def plot_waterfall(subject_ids, pct_changes, threshold_pr=-30,
                   threshold_pd=20, title="Best Overall Response",
                   figsize=(3.15, 2.6)):
    """
    Waterfall plot of best percentage change in tumor size (RECIST).

    Bars colored: green (PR, <= -30%), red (PD, >= +20%), gray (SD).
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Sort by response magnitude
    order = np.argsort(pct_changes)[::-1]
    pct_sorted = np.array(pct_changes)[order]
    ids_sorted = np.array(subject_ids)[order]

    colors = []
    for p in pct_sorted:
        if p <= threshold_pr:
            colors.append(PALETTE["teal_500"])   # partial response
        elif p >= threshold_pd:
            colors.append(PALETTE["red_500"])    # progressive disease
        else:
            colors.append(PALETTE["grey_500"])   # stable disease

    ax.bar(range(len(pct_sorted)), pct_sorted, color=colors, width=0.8,
           edgecolor="none")

    # RECIST thresholds
    ax.axhline(threshold_pr, color=PALETTE["grey_700"], linestyle="--",
               linewidth=0.8, alpha=0.7)
    ax.axhline(threshold_pd, color=PALETTE["grey_700"], linestyle=":",
               linewidth=0.8, alpha=0.7)
    ax.axhline(0, color="black", linewidth=0.5)

    ax.set_ylabel("Best change from baseline (%)")
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_xlabel(f"Subjects (n={len(pct_sorted)})")

    # Legend
    from matplotlib.patches import Patch
    legend_items = [
        Patch(facecolor=PALETTE["teal_500"], label=f"PR (≤{threshold_pr}%)"),
        Patch(facecolor=PALETTE["grey_500"], label="SD"),
        Patch(facecolor=PALETTE["red_500"], label=f"PD (≥+{threshold_pd}%)"),
    ]
    ax.legend(handles=legend_items, loc="upper right", frameon=False)
    set_margins_in(fig, left=0.65, right=0.15, bottom=0.4, top=0.35)
    return fig, ax
```

## Swimmer plots

```python
def plot_swimmer(df, subject_col, duration_col, event_col=None,
                 response_col=None, arm_col=None,
                 arm_colors=None, title="Swimmer Plot",
                 xlabel="Time on treatment (months)",
                 figsize=(3.15, None)):
    """
    Swimmer plot: horizontal bars per subject showing treatment duration.

    Parameters
    ----------
    df : one row per subject.
    event_col : column with event markers (e.g., 'PD', 'death').
    response_col : column with best response category for bar color.
    """
    df_sorted = df.sort_values(duration_col, ascending=True).reset_index(drop=True)
    n = len(df_sorted)
    if figsize[1] is None:
        figsize = (figsize[0], max(2.6, n * 0.25 + 0.85))   # >= 0.25 in per row at 8 pt

    fig, ax = plt.subplots(figsize=figsize)

    for i, row in df_sorted.iterrows():
        if response_col and arm_colors:
            ax.barh(i, row[duration_col], height=0.6,
                    color=arm_colors[row[response_col]], edgecolor="none")
        else:   # single category: black outline, white interior (color.md Rule 1)
            ax.barh(i, row[duration_col], height=0.6,
                    facecolor="white", edgecolor=PALETTE["black"], linewidth=0.8)

        # Event marker
        if event_col and pd.notna(row.get(event_col)):
            ax.plot(row[duration_col], i, "k>", markersize=6)

    ax.set_yticks(range(n))
    ax.set_yticklabels(df_sorted[subject_col])
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.invert_yaxis()
    set_margins_in(fig, left=0.9, right=0.15, bottom=0.5, top=0.35)
    return fig, ax
```

## Volcano plots

```python
def plot_volcano(df, log2fc_col, pval_col,
                 gene_col=None, fc_thresh=1.0, pval_thresh=0.05,
                 n_label=10, title="Differential Expression",
                 figsize=(3.15, 3.0)):
    """
    Volcano plot: -log10(p) vs log2(fold change).

    Parameters
    ----------
    fc_thresh : absolute log2FC threshold for significance coloring.
    pval_thresh : p-value threshold.
    n_label : number of top genes to label.
    """
    fig, ax = plt.subplots(figsize=figsize)

    neg_log_p = -np.log10(df[pval_col].clip(lower=1e-300))
    log2fc = df[log2fc_col]

    # Color categories
    sig_up = (log2fc >= fc_thresh) & (df[pval_col] <= pval_thresh)
    sig_down = (log2fc <= -fc_thresh) & (df[pval_col] <= pval_thresh)
    ns = ~(sig_up | sig_down)

    ax.scatter(log2fc[ns], neg_log_p[ns], c=PALETTE["grey_300"], s=8, alpha=0.5,
              label="NS", rasterized=True)
    ax.scatter(log2fc[sig_up], neg_log_p[sig_up], c=PALETTE["red_500"], s=12,
              alpha=0.7, label="Up")
    ax.scatter(log2fc[sig_down], neg_log_p[sig_down], c=PALETTE["navy_500"], s=12,
              alpha=0.7, label="Down")

    # Threshold lines
    ax.axhline(-np.log10(pval_thresh), color=PALETTE["grey_700"], linestyle="--",
               linewidth=0.5)
    ax.axvline(fc_thresh, color=PALETTE["grey_700"], linestyle="--", linewidth=0.5)
    ax.axvline(-fc_thresh, color=PALETTE["grey_700"], linestyle="--", linewidth=0.5)

    # Label top hits
    if gene_col:
        sig = df[sig_up | sig_down].copy()
        sig["_nlp"] = neg_log_p[sig.index]
        top = sig.nlargest(n_label, "_nlp")
        for _, row in top.iterrows():
            ax.annotate(
                row[gene_col],
                (row[log2fc_col], -np.log10(row[pval_col])),
                fontsize=11, ha="center",
                xytext=(0, 5), textcoords="offset points",
            )

    ax.set_xlabel("log$_2$(Fold Change)")
    ax.set_ylabel("-log$_{10}$(p-value)")
    ax.set_title(title)
    ax.legend(loc="upper right", frameon=False)
    set_margins_in(fig, left=0.6, right=0.15, bottom=0.55, top=0.35)
    return fig, ax
```

## Dose-response curves

```python
from scipy.optimize import curve_fit

def four_param_logistic(x, bottom, top, ec50, hill):
    """4-parameter logistic (Hill equation)."""
    return bottom + (top - bottom) / (1 + (ec50 / x) ** hill)


def plot_dose_response(concentrations, responses, compound_name="",
                       xlabel="Concentration (nM)",
                       ylabel="% Response",
                       figsize=(3.15, 2.8)):
    """
    Dose-response curve with 4PL fit and EC50 annotation.
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Raw data
    ax.scatter(concentrations, responses, color=PALETTE["black"], s=30,
              zorder=5, label="Data")

    # Fit
    try:
        popt, _ = curve_fit(
            four_param_logistic, concentrations, responses,
            p0=[min(responses), max(responses),
                np.median(concentrations), 1.0],
            maxfev=10000,
        )
        x_fit = np.geomspace(min(concentrations), max(concentrations), 200)
        y_fit = four_param_logistic(x_fit, *popt)
        ax.plot(x_fit, y_fit, color=PALETTE["red_500"], linewidth=1.5, label="4PL fit")

        ec50 = popt[2]
        ax.axvline(ec50, color=PALETTE["grey_700"], linestyle=":", linewidth=0.8)
        ax.text(ec50 * 1.2, max(responses) * 0.5,
                f"EC50 = {ec50:.1f} nM", fontsize=11)
    except RuntimeError:
        ax.text(0.5, 0.5, "Fit did not converge",
                transform=ax.transAxes, ha="center", color=PALETTE["red_500"])

    ax.set_xscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(f"Dose-Response: {compound_name}" if compound_name else "Dose-Response")
    ax.legend(frameon=False)
    set_margins_in(fig, left=0.6, right=0.15, bottom=0.55, top=0.35)
    return fig, ax
```

## Spider plots

```python
def plot_spider(df, time_col, pct_change_col, subject_col,
                group_col=None, arm_colors=None,
                threshold_pr=-30, threshold_pd=20,
                title="Tumor Burden Over Time",
                xlabel="Time (weeks)",
                ylabel="Change from baseline (%)",
                figsize=(3.15, 2.3)):
    """
    Spider plot: one line per subject showing tumor burden change over time.
    """
    fig, ax = plt.subplots(figsize=figsize)

    subjects = df[subject_col].unique()
    for subj in subjects:
        subj_data = df[df[subject_col] == subj].sort_values(time_col)
        color = PALETTE["black"]          # single category (color.md Rule 1)
        if group_col and arm_colors:
            grp = subj_data[group_col].iloc[0]
            color = arm_colors[grp]
        ax.plot(subj_data[time_col], subj_data[pct_change_col],
                color=color, alpha=0.5, linewidth=0.8)

    # RECIST thresholds
    ax.axhline(threshold_pr, color=PALETTE["grey_700"], linestyle="--",
               linewidth=0.8, alpha=0.7, label=f"PR ({threshold_pr}%)")
    ax.axhline(threshold_pd, color=PALETTE["grey_700"], linestyle=":",
               linewidth=0.8, alpha=0.7, label=f"PD (+{threshold_pd}%)")
    ax.axhline(0, color="black", linewidth=0.5)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="upper right", frameon=False)
    set_margins_in(fig, left=0.6, right=0.15, bottom=0.55, top=0.35)
    return fig, ax
```

## CONSORT flow diagrams

CONSORT diagrams are best built with matplotlib patches and annotations.
For complex flows, consider the `schemdraw` library.

```python
def plot_consort_simple(stages: dict, title="CONSORT Flow Diagram",
                        figsize=(3.15, None)):
    """
    Simple CONSORT flow with vertical boxes.

    Parameters
    ----------
    stages : ordered dict of {"label": count}, e.g.
        {"Screened": 500, "Enrolled": 350, "Randomized": 300,
         "Arm A": 150, "Arm B": 150, "Completed": 240}
    """
    from matplotlib.patches import FancyBboxPatch

    if figsize[1] is None:
        figsize = (figsize[0], len(stages) * 0.9 + 0.6)
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(stages) * 2 + 1)
    ax.axis("off")
    ax.set_title(title, fontsize=11, fontweight="bold")

    y = len(stages) * 2
    for label, count in stages.items():
        box = FancyBboxPatch(
            (2.5, y - 0.6), 5, 1.2,
            boxstyle="round,pad=0.2",
            facecolor=PALETTE["navy_50"], edgecolor=PALETTE["navy_500"], linewidth=1.2,
        )
        ax.add_patch(box)
        ax.text(5, y, f"{label}\nn = {count}",
                ha="center", va="center", fontsize=11)
        if y < len(stages) * 2:
            ax.annotate(
                "", xy=(5, y + 0.6), xytext=(5, y + 1.4),
                arrowprops=dict(arrowstyle="->", color=PALETTE["navy_500"], lw=1.2),
            )
        y -= 2

    set_margins_in(fig, left=0.1, right=0.1, bottom=0.1, top=0.35)
    return fig, ax
```

## Dependencies

Install as needed:

```python
%pip install lifelines  # KM curves, survival analysis
%pip install scipy      # dose-response fitting, stats
# matplotlib and seaborn are pre-installed on Databricks
```

## Combining domain figures with Plotly

For interactive versions of these domain charts (e.g., hoverable KM curves),
the general pattern is:

1. Compute the same data (KM estimates, forest CIs, etc.) in Python.
2. Build the figure with `plotly.graph_objects` instead of matplotlib.
3. Apply the `polish_plotly()` function from `plotly-interactive.md`.

Lifelines KM estimates can be extracted as DataFrames via
`kmf.survival_function_` and `kmf.confidence_interval_` for direct use in
Plotly traces.
