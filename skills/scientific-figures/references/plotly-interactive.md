# Plotly — Interactive Figures & App Migration

Subskill of `scientific-figures`. Load when the user needs interactive
visualization (hover, zoom, filter) in notebooks or Databricks Apps.

**Sizing rules (hub rules apply; these are the Plotly specifics):**
- **Interactive views** (notebook, App) are exempt from the inch width rule;
  size them to the container / notebook width.
- **Fonts are 8 pt in every case.** Plotly sizes are CSS px at 96 px/in, so
  8 pt = **11 px** (`PT8 = 11`). Titles at least 11 px. Never below 10 px
  (10 pt), and 14 px only for single-panel static exports.
- **Static exports** (`write_image`) follow the hub width rule: 3.15 in
  (302 px) single panel, 5.85 in (562 px) for 2+ panels, with
  `scale=300/96` for 300 DPI. View the exported image before reporting it
  (hub visual review).
- Equal aspect for embeddings / spatial / same-unit axes:
  `fig.update_yaxes(scaleanchor="x", scaleratio=1)`.

## When to use Plotly

| Context | Use Plotly? | Notes |
|---|---|---|
| Notebook EDA — quick look at data | Yes | `px` one-liners are fastest |
| Notebook — interactive drill-down | Yes | Hover data, click events |
| Journal figure submission | No | Journals want PDF/PNG → use matplotlib |
| Databricks App — simple charts | Yes | Plotly renders directly via Dash or Gradio |
| Databricks App — complex multi-view UI | Start Plotly, migrate to React | See migration section |
| Dashboard widget | No | Dashboards have their own charting |

## Plotly Express quick patterns

### Setup

```python
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

# Set default template for clean scientific look
pio.templates.default = "plotly_white"

# Colors come from color.md (PALETTE, CATEGORICAL, family_shades); never Plotly defaults.
# CATEGORICAL = black, red 500, navy 500, orange 500, teal 500, grey 500 (max 6 hues)
CATEGORICAL = ["#000000", "#D62728", "#3A6EA5", "#F28C28", "#1BA7A6", "#8C8C8C"]
```

### Common chart types

```python
# Scatter with hover
fig = px.scatter(
    df, x="biomarker_value", y="response_score",
    color="treatment_arm", hover_data=["subject_id", "compound_id"],
    color_discrete_sequence=CATEGORICAL,   # or color_discrete_map=ARM_COLORS (color.md Rule 3)
    title="Biomarker vs Response",
)
PT8 = 11    # 8 pt in Plotly px (96 px/in)
fig.update_layout(
    font_family="Arial",
    font_size=PT11,
    title_font_size=PT11,
    width=800, height=500,   # interactive view: container-sized, exempt from width rule
)
fig.show()

# Faceted line chart (time series by arm)
fig = px.line(
    df, x="visit_day", y="measurement",
    color="treatment_arm", facet_col="compound_id",
    facet_col_wrap=3,
    color_discrete_sequence=CATEGORICAL,
)
fig.update_yaxes(matches=None)  # independent y-axes per facet
fig.show()
```

### Layout polish

```python
def polish_plotly(fig, width=800, height=500, font_px=15):
    """Apply scientific figure standards to a Plotly figure.

    font_px=11 is 8 pt (hub rule). width/height are for interactive views;
    for static export use export_static() below.
    """
    fig.update_layout(
        font=dict(family="Arial", size=font_px),
        title_font_size=font_px,
        width=width,
        height=height,
        margin=dict(l=60, r=30, t=50, b=50),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font_size=font_px,
        ),
        plot_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridwidth=0.5, gridcolor="#E5E5E5",
                     showline=True, linewidth=0.8, linecolor="black")
    fig.update_yaxes(showgrid=True, gridwidth=0.5, gridcolor="#E5E5E5",
                     showline=True, linewidth=0.8, linecolor="black")
    return fig
```

## Static export from Plotly

When the user needs a PNG/PDF from a Plotly figure (e.g., for a manuscript
appendix alongside interactive version):

```python
# Requires: pip install kaleido
PX_PER_IN = 96

def export_static(fig, name, width_in=5.85, height_in=4.0):
    """Static export at the hub width rule (3.15 in single panel, 5.85 in 2+ panels)."""
    w, h = round(width_in * PX_PER_IN), round(height_in * PX_PER_IN)
    for ext in ("pdf", "png"):
        fig.write_image(f"{name}.{ext}", width=w, height=h, scale=300 / PX_PER_IN)
    print(f"Exported {name}: {width_in:.2f} x {height_in:.2f} in ({w} x {h} px @ 300 DPI)")

export_static(fig, "figure", width_in=5.85, height_in=4.0)
fig.write_html("figure.html", include_plotlyjs="cdn")  # interactive: exempt from width rule
```

## Notebook rendering notes

- Plotly figures render natively in Databricks notebooks.
- For large datasets (>50k points), use `px.scatter` with
  `render_mode="webgl"` to avoid sluggish SVG rendering.
- If the notebook uses `displayHTML`, wrap the Plotly HTML:
  ```python
  displayHTML(fig.to_html(include_plotlyjs="cdn"))
  ```

## Databricks App: when to stay with Plotly

Stay with Python + Plotly (via Dash, Gradio, or Streamlit) when:

- The app is a **single-page data explorer** with <10 interactive controls.
- The development team is **Python-only** (no frontend engineers).
- Time to ship is **<2 weeks**.
- The visualization is primarily **charts and tables**, not custom UI components.

### Dash pattern for Databricks Apps

```python
# app.py for a Databricks App
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
from databricks.sdk import WorkspaceClient

app = dash.Dash(__name__)
w = WorkspaceClient()

# Load data from Unity Catalog
df = spark.table("<catalog>.<schema>.gold_ae_summary").toPandas()

app.layout = html.Div([
    html.H1("Adverse Event Dashboard"),
    dcc.Dropdown(
        id="compound-filter",
        options=[{"label": c, "value": c} for c in df["compound_id"].unique()],
        multi=True,
        placeholder="Select compounds...",
    ),
    dcc.Graph(id="ae-chart"),
])

@app.callback(
    Output("ae-chart", "figure"),
    Input("compound-filter", "value"),
)
def update_chart(compounds):
    filtered = df if not compounds else df[df["compound_id"].isin(compounds)]
    fig = px.bar(filtered, x="soc_term", y="event_count",
                 color="ae_grade", barmode="stack")
    return polish_plotly(fig)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
```

## When to migrate to React

Migrate from Python Plotly to React + Plotly.js (or React + Deck.gl / Nivo)
when:

- The app needs **complex UI**: multi-tab layouts, drag-and-drop, modals,
  custom forms, or rich state management.
- The app needs **real-time updates** (WebSockets, streaming data).
- **Performance matters**: React virtual DOM handles large component trees
  better than Dash callback chains.
- The team has **frontend engineers** who prefer TypeScript/JSX.
- You need to embed a **Molstar viewer** alongside 2-D charts (Molstar is a
  React component).

### Migration path

1. **Keep the Plotly figure specs**: the `go.Figure` JSON schema is the same in
   Python and `plotly.js`. Export figure JSON with `fig.to_json()` and pass it
   to the `<Plot>` React component.
2. **Replace Dash callbacks with React state**: each `@callback` becomes a
   `useState` + `useEffect` or a query hook.
3. **Backend**: keep the Databricks SQL connector or SDK for data fetching.
   Expose it via FastAPI or the Databricks Apps backend.

### Minimal React + Plotly.js skeleton

```tsx
// src/components/AEChart.tsx
import Plot from "react-plotly.js";
import type { Data, Layout } from "plotly.js";

interface Props {
  data: Data[];
  title: string;
}

export function AEChart({ data, title }: Props) {
  const layout: Partial<Layout> = {
    title: { text: title, font: { family: "Inter", size: 16 } },
    font: { family: "Inter", size: 12 },
    plot_bgcolor: "white",
    xaxis: { showgrid: true, gridcolor: "#E5E5E5" },
    yaxis: { showgrid: true, gridcolor: "#E5E5E5" },
    margin: { l: 60, r: 30, t: 50, b: 50 },
  };

  return (
    <Plot
      data={data}
      layout={layout}
      useResizeHandler
      style={{ width: "100%", height: "100%" }}
    />
  );
}
```

### App structure for Databricks Apps (React)

```
my-app/
├── app.yaml              # Databricks App manifest
├── backend/
│   ├── main.py           # FastAPI serving data from UC
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── AEChart.tsx
│   │   │   └── MolViewer.tsx   # if using Molstar
│   │   └── hooks/
│   │       └── useData.ts
│   └── vite.config.ts
└── README.md
```

## Decision framework summary

```
User wants interactive figure
│
├── In a notebook? ──────────────> Plotly Express (px)
│
├── In a Databricks App?
│   ├── Simple UI, Python team? ─> Dash + Plotly
│   ├── Complex UI or 3D mol? ──> React + Plotly.js (± Molstar)
│   └── Needs maps / geo? ──────> React + Deck.gl or Plotly Mapbox
│
└── Needs static export too? ───> Plotly → kaleido → PDF/PNG
```
