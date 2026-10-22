# Protein & Molecular Structure 3-D Visualization

Subskill of `scientific-figures`. Load when the user needs to render protein
structures, small molecules, binding sites, or any 3-D molecular visualization.

**Sizing rules:** interactive viewers (py3Dmol, Molstar) are exempt from the
hub's inch width rule; size them to the notebook / app container. **Static
snapshots for papers follow the hub rules**: 3.15 in single panel, 5.85 in for
2+ panels, 8 pt for any labels or annotations added in matplotlib, and a
visual review of the final image before reporting it.

**Colors:** highlights, selections and annotations use [color.md](color.md)
(e.g. highlight Red 500, context Navy 500, backbone Grey 300). When the user
specifies colors by name (e.g. "blue for RBD, red for antibody"), use the
closest brand-palette family and convert to int for Molstar with
`int("8FB3DA", 16)`. If the user gives an explicit hex code, use it directly.
Established chemistry conventions are allowed exceptions: element (CPK)
coloring such as `greenCarbon`, and B-factor / charge gradients in
blue-white-red (`rwb`). No rainbow (`roygb`) gradients.

## Library selection

| Context | Library | Why |
|---|---|---|
| Databricks notebook (default) | **Molstar core (CDN)** | `molstar@4.5.0` via `displayHTML()`; verified: HETATM removal, chain coloring, semi-transparent surfaces, collapsible tools panel |
| Databricks notebook, quick Python view | **py3Dmol** | Pure Python, renders inline, zero JS build |
| Databricks notebook, last resort | **NGL Viewer** | Only when a specific feature is verified to fail in core Molstar; tell the user before switching |
| Databricks App (simple embed) | **py3Dmol via iframe** | Wrap `view.write_html()` in an iframe if app is Dash/Gradio |
| Databricks App (rich interaction) | **Molstar** | React component, full feature set, production-grade |
| Static figure for paper | **Molstar UI screenshot**, **py3Dmol → PNG**, or **PyMOL** (only if user asks) | See "Static image capture" and "Automated figure pipelines" below |

### Decision rule

- **Default: Molstar, always try it first.** In a Databricks App (React),
  use the full Molstar plugin. In a notebook, use the **core `molstar`
  package** from jsDelivr via `displayHTML()` (see "Molstar in notebooks"
  below). It supports programmatic styling: HETATM removal, chain coloring,
  semi-transparent surfaces. Do NOT use the `@rcsb/rcsb-molstar` wrapper for
  anything beyond a plain render; its customization calls silently fail.
- **Python-native: py3Dmol.** Use when the user wants a simple Python API,
  quick single-style renders, or specifically asks for py3Dmol.
- **Last resort: NGL Viewer.** Only after a specific feature has been tried
  in core Molstar and verified not to work. Never silently switch libraries
  when the user asked for (or the default is) Molstar; say what failed and
  ask before falling back.
- **App (Python-only)**: if the app is Dash/Gradio and the 3-D view is
  secondary, embed py3Dmol HTML via iframe.

### Structural analysis + visualization pipeline

For notebooks that analyze protein structures (parsing, contacts, interfaces,
mutations), follow this tool hierarchy:

1. **BioPython / numpy — analysis backbone.** Use for all structural logic:
   PDB/mmCIF parsing, contact computation, SASA, interface geometry, sequence
   alignment, camera-angle calculation. Pure Python, pip-installable, works
   on serverless. Unless the analysis is trivial (e.g. just loading a PDB to
   view), BioPython should do the heavy lifting.
2. **Molstar — interactive viewing.** Default for all 3-D renders in
   notebooks. Use for exploration, debugging, and final presentation. Not
   part of automated pipelines — treat as `if DEBUG:` cells.
3. **matplotlib / seaborn — 2-D figures.** Contact maps, lollipop plots,
   heatmaps, any 2-D panel. Fully reproducible, saves to PDF/PNG.
4. **PyMOL — only if the user explicitly asks.** Do not proactively suggest
   or generate PyMOL code. If the user asks, note that:
   - `pymol-open-source` installs via conda, not pip (use conda in `%sh`
     cells on classic clusters, or init scripts for jobs)
   - PyMOL has a full Python API (`pymol.cmd`) for headless scripting:
     load structure, set camera (`set_view`), color, add surfaces, ray-trace
     to PNG — all without a GUI
   - **Recommend local testing first** — develop and debug PyMOL scripts
     locally, then build into a Databricks pipeline/job if automated
     figure generation is truly needed
   - No PyMOL code examples in this skill — the PyMOL API is well
     documented externally and changes frequently enough that stale
     examples cause more harm than help

### Static image capture

For getting images out of notebook 3-D renders:

- **Molstar UI**: click the camera icon in the viewport toolbar (or via
  the wrench → screenshot). Image downloads to the browser. Simplest
  option for one-off figures.
- **py3Dmol `pngURI()`**: returns a base64 PNG to Python. Quality is lower
  than Molstar and can be inconsistent, but it's fully programmatic.
- **PyMOL headless**: only if the user needs a reproducible, automated
  pipeline that generates figures without human interaction.

Note: there is no reliable way to programmatically capture a Molstar render
back to Python from a `displayHTML()` iframe — the iframe is sandboxed with
no `postMessage` bridge to the notebook kernel.

## py3Dmol in Databricks notebooks

### Installation

```python
%pip install py3Dmol
```

### Basic PDB rendering

```python
import py3Dmol

def show_structure(pdb_id: str, style: str = "cartoon",
                   color_scheme: str = "chain",
                   width: int = 800, height: int = 500):
    """Render a PDB structure inline in a Databricks notebook."""
    view = py3Dmol.view(query=f"pdb:{pdb_id}", width=width, height=height)

    # IMPORTANT: use "colorscheme", not "color", for named schemes
    # ("color" sets a single literal color; "colorscheme" maps data → colors)
    style_spec = {style: {"colorscheme": color_scheme}}
    view.setStyle(style_spec)
    view.setBackgroundColor("white")
    view.zoomTo()
    return view.show()

# Example: Trastuzumab Fab bound to HER2
show_structure("1N8Z")
```

### Color schemes

```python
# By chain (default — good for complexes)
# CRITICAL: use "colorscheme", NOT "color". "color" treats the string as a
# literal color name, which silently falls back to black.
view.setStyle({"cartoon": {"colorscheme": "chain"}})

# By secondary structure
view.setStyle({"cartoon": {"colorscheme": "ss"}})

# By residue property (hydrophobicity)
view.setStyle({"cartoon": {"colorscheme": "Jmol"}})

# By B-factor (temperature factor)
view.setStyle({"cartoon": {"color": "b", "colorscheme": {
    "prop": "b", "gradient": "rwb", "min": 10, "max": 80   # low B blue -> high B red
}}})

# Custom: highlight specific residues
view.setStyle({"resi": ["100-120"], "chain": "A"},
              {"stick": {"color": "#D62728"}})    # color.md Red 500
view.setStyle({"resi": ["100-120"], "chain": "A"},
              {"cartoon": {"color": "#D62728"}})
```

### Molecular surfaces

**Limitation:** py3Dmol's `addSurface` on a residue selection renders the
**solvent-exposed face** of those residues, not the buried interface between
chains. For protein-protein interface visualization where you need surfaces
at the contact zone, use Molstar (preferred) or NGL as a last resort.

```python
# Solvent-accessible surface, transparent
view.addSurface(py3Dmol.SAS, {
    "opacity": 0.7,
    "color": "white",
}, {"chain": "A"})

# Electrostatic-style (color by charge property)
view.addSurface(py3Dmol.VDW, {
    "opacity": 0.8,
    "colorscheme": {"prop": "partialCharge", "gradient": "rwb"},
})
```

### Binding site focus

**`within` selector caveat:** the `within` distance selector matches **all
atoms** including HETATM records (waters, ions, ligands) and hydrogens if
present. To restrict to protein-protein contacts, add `"hetflag": False` to
**both** the selecting and target selections:

```python
# Protein-only interface (exclude HETATM on both sides)
view.setStyle(
    {"chain": "A", "hetflag": False,
     "within": {"distance": 5.0, "sel": {"chain": "B", "hetflag": False}}},
    {"cartoon": {"color": "#F28C28"}},
)
```

Also note: a simple distance cutoff (e.g. 5 Å) captures crystal packing
contacts in addition to the biological interface. For curated interface
residues, prefer **literature-reported residues** or **PDBePISA**
buried-surface-area (BSA > 0 Å²) analysis. Standard cutoffs:
- **4.5 Å heavy-atom**: PDBePISA / most interface studies
- **5.0 Å heavy-atom**: common but generous (second-shell contacts)
- **8–10 Å Cα–Cα**: coarser proxy for network-based analyses

```python
def show_binding_site(pdb_id, ligand_resn, radius=5.0,
                      width=800, height=500):
    """Render a binding site: ligand as sticks, nearby residues as lines."""
    view = py3Dmol.view(query=f"pdb:{pdb_id}", width=width, height=height)

    # Protein backbone
    view.setStyle({"cartoon": {"color": "#C8C8C8", "opacity": 0.5}})   # Grey 300

    # Ligand
    view.setStyle({"resn": ligand_resn},
                  {"stick": {"colorscheme": "greenCarbon", "radius": 0.2}})

    # Nearby residues
    view.setStyle(
        {"within": {"distance": radius, "sel": {"resn": ligand_resn}},
         "not": {"resn": ligand_resn}},
        {"line": {"color": "#3A6EA5"}},   # Navy 500
    )

    view.zoomTo({"resn": ligand_resn})
    view.setBackgroundColor("white")
    return view.show()

# Example: drug binding pocket
show_binding_site("1N8Z", "HER")
```

### Loading from file (UC Volume or workspace)

```python
import py3Dmol

# Read PDB from a UC Volume
with open("/Volumes/<catalog>/<schema>/<volume>/structures/my_protein.pdb") as f:
    pdb_data = f.read()

view = py3Dmol.view(width=800, height=500)
view.addModel(pdb_data, "pdb")
view.setStyle({"cartoon": {"colorscheme": "chain"}})
view.setBackgroundColor("white")
view.zoomTo()
view.show()

# mmCIF format (increasingly common from PDB)
with open("/Volumes/<catalog>/<schema>/<volume>/structures/my_protein.cif") as f:
    cif_data = f.read()

view = py3Dmol.view(width=800, height=500)
view.addModel(cif_data, "cif")
view.setStyle({"cartoon": {"colorscheme": "chain"}})
view.zoomTo()
view.show()
```

### AlphaFold confidence coloring (pLDDT)

```python
def show_alphafold(uniprot_id, width=800, height=500):
    """Fetch and render an AlphaFold model colored by pLDDT confidence."""
    import requests
    url = f"https://alphafold.ebi.ac.uk/files/AF-{uniprot_id}-F1-model_v4.pdb"
    pdb = requests.get(url).text

    view = py3Dmol.view(width=width, height=height)
    view.addModel(pdb, "pdb")
    # pLDDT is stored in the B-factor column
    view.setStyle({"cartoon": {"color": "b", "colorscheme": {
        "prop": "b",
        "gradient": "roygb",
        "min": 50,   # low confidence
        "max": 100,  # high confidence
    }}})
    view.setBackgroundColor("white")
    view.zoomTo()
    return view.show()

# Example: Human EGFR
show_alphafold("P00533")
```

### Exporting a static image from py3Dmol

py3Dmol renders in WebGL; there is no direct `savefig`. Use the PNG callback:

```python
# In a notebook cell:
view = py3Dmol.view(query="pdb:1N8Z", width=1600, height=1000)  # 2x for hi-res
view.setStyle({"cartoon": {"colorscheme": "chain"}})
view.setBackgroundColor("white")
view.zoomTo()

# Render to PNG via JavaScript callback
view.png()  # returns base64 PNG; save with:

import base64
png_data = view.pngURI()  # data:image/png;base64,...
if png_data:
    img_bytes = base64.b64decode(png_data.split(",")[1])
    with open("/Volumes/<catalog>/<schema>/<volume>/figures/structure.png", "wb") as f:
        f.write(img_bytes)
```

Note: `pngURI()` can be inconsistent in headless or sandboxed environments.
If the capture is blank or missing, see "Static image capture" above for
alternatives.

## NGL Viewer in Databricks notebooks (last resort)

Use NGL only when a specific feature has been tried in core Molstar and
verified not to work (e.g. per-residue custom hex colors, if confirmed
unsupported). Tell the user what failed in Molstar before switching. NGL
loads reliably from `unpkg.com` in Databricks `displayHTML()` iframes and
offers selection-based color schemes and layered representations.

### Why NGL over py3Dmol for complex scenes

- **First-match color schemes**: `addSelectionScheme` applies rules in
  priority order, so interface residues can override chain colors cleanly.
- **Multiple layered representations**: cartoon + transparent surface +
  opaque interface surface in one scene, each with its own selection.
- **`sele: 'polymer'`** excludes all HETATM (waters, ions) from any
  representation -- no manual filtering needed.
- **`displayHTML()` compatible**: loads from CDN via dynamic `<script>` tag.

### Installation

No pip install needed. NGL loads from CDN inside `displayHTML()`.

### Complete example: pastel cartoon + transparent surface + interface

```python
COLOR_A  = "#93C5E8"   # soft sky blue
COLOR_B  = "#E8A3B3"   # soft rose
COLOR_IF = "#E8B84D"   # warm amber

html = f"""
<div id="viewport" style="width:800px; height:600px;"></div>
<script>
(function() {{
  var s = document.createElement('script');
  s.src = 'https://unpkg.com/ngl@2.3.1/dist/ngl.js';
  s.onload = function() {{
    var stage = new NGL.Stage('viewport', {{
      backgroundColor: 'white', quality: 'high'
    }});
    // First-match color scheme: interface first, then per-chain
    var schemeId = NGL.ColormakerRegistry.addSelectionScheme([
      ['{COLOR_IF}', '39 or 45 or 47 or 91'],  // interface
      ['{COLOR_A}',  ':A'],                      // chain A
      ['{COLOR_B}',  ':B'],                      // chain B
      ['#D0D0D0',    '*'],                       // fallback
    ], 'custom_scheme');
    stage.loadFile('rcsb://4Z18').then(function(comp) {{
      comp.addRepresentation('cartoon', {{
        color: schemeId, sele: 'polymer', smoothSheet: true,
      }});
      comp.addRepresentation('surface', {{
        color: schemeId, opacity: 0.22,
        surfaceType: 'sas', sele: 'polymer',
      }});
      comp.addRepresentation('surface', {{
        color: schemeId, opacity: 0.55,
        surfaceType: 'sas',
        sele: '(39 or 45 or 47 or 91) and polymer',
      }});
      comp.autoView();
    }});
  }};
  document.head.appendChild(s);
}})();
</script>
"""
displayHTML(html)
```

### Key NGL API patterns

```javascript
// Selection syntax
':A'                         // chain A
'39 or 45 or 47'             // residue numbers
'polymer'                    // protein/nucleic only (no HETATM)
'hetero and not water'       // ligands only
'(39 or 45) and :A'          // residues on specific chain

// Representations
comp.addRepresentation('cartoon',    {color: schemeId, sele: 'polymer'});
comp.addRepresentation('surface',    {color: schemeId, opacity: 0.3, surfaceType: 'sas', sele: 'polymer'});
comp.addRepresentation('ball+stick', {sele: 'hetero and not water'});
comp.addRepresentation('spacefill',  {sele: 'ion', scale: 0.5});
```

## Molstar (preferred viewer)

Molstar is the modern, production-grade molecular viewer used by RCSB PDB and
PDBe. It is the **default recommendation** for 3-D molecular visualization,
in both notebooks (core `molstar` CDN build) and Apps (React).

### Molstar in notebooks via `displayHTML()` (core package — use this)

Verified working pattern (PDB 4Z18, PD-L1 homodimer): HETATM removed, chains
colored, semi-transparent surface over cartoon, full-width viewport on load,
wrench button that opens only the structure tools panel.

**Required panel state on load** (this is the target UX, keep it exactly):
- Viewport fills the whole frame; no panels open at start.
- The **wrench** button is visible in the viewport toolbar but **not active**.
- Clicking the wrench opens the structure tools panel and the **sequence
  strip** (polymer sequence bar at the top of the expanded layout), but NOT
  the left "Home" panel (Home stays collapsed to a thin tab strip).
- Clicking the wrench again hides the panel and the viewport resizes back.

```python
import base64, requests

pdb_id = "4Z18"
pdb_text = requests.get(f"https://files.rcsb.org/download/{pdb_id}.pdb").text
pdb_b64 = base64.b64encode(pdb_text.encode()).decode()

html = f"""
<div id="molstar-app" style="width:800px; height:600px; position:relative;"></div>
<script>
(function() {{
  var link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'https://cdn.jsdelivr.net/npm/molstar@4.5.0/build/viewer/molstar.css';
  document.head.appendChild(link);

  var s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/molstar@4.5.0/build/viewer/molstar.js';
  s.onload = function() {{
    molstar.Viewer.create('molstar-app', {{
      // --- Panel state: full viewport; wrench opens ONLY the tools panel ---
      layoutIsExpanded: false,
      layoutShowControls: false,   // panels hidden at start (full viewport)
      collapseRightPanel: false,   // MUST be false, else wrench appears to do nothing
      layoutShowLeftPanel: true,   // keep Home/state tree reachable...
      collapseLeftPanel: true,     // ...but collapsed, so wrench doesn't co-open Home
      layoutShowRemoteState: false,
      layoutShowSequence: true,   // sequence strip visible when wrench is clicked
      layoutShowLog: false,
      viewportShowControls: true,  // REQUIRED: renders the wrench button
      viewportShowSettings: true,  // sliders icon (render settings)
      viewportShowExpand: true,
      viewportShowSelectionMode: false,
      viewportShowAnimation: false,
      viewportShowTrajectoryControls: false,
    }}).then(function(viewer) {{
      var plugin = viewer.plugin;
      // White background (viewer.setBackground does NOT exist)
      plugin.canvas3d.setProps({{ renderer: {{ backgroundColor: {{r:1,g:1,b:1}} }} }});

      viewer.loadStructureFromData(atob('{pdb_b64}'), 'pdb', false).then(function() {{
        var hier = plugin.managers.structure.hierarchy;
        var st = hier.current.structures[0];
        // Component keys: structure-component-static-polymer / -water / -ion / -ligand

        // 1. Remove HETATM: pass COMPONENT REFS (passing comp.cell throws)
        var nonPolymer = st.components.filter(function(c) {{
          return (c.key || '').indexOf('polymer') === -1;
        }});
        if (nonPolymer.length) hier.remove(nonPolymer);
        st = hier.current.structures[0];   // re-read after removal

        // 2. Color by chain: pass COMPONENT REFS (comp.representations throws)
        plugin.managers.structure.component.updateRepresentationsTheme(
          st.components, {{ color: 'chain-id' }}
        );

        // 3. Semi-transparent surface over the cartoon (polymer only)
        st.components.forEach(function(c) {{
          if ((c.key || '').indexOf('polymer') !== -1) {{
            plugin.builders.structure.representation.addRepresentation(
              c.cell,
              {{ type: 'molecular-surface', typeParams: {{ alpha: 0.40 }}, color: 'chain-id' }}
            );
          }}
        }});
      }});
    }});
  }};
  document.head.appendChild(s);
}})();
</script>
"""
displayHTML(html)
```

**Core Molstar API notes (verified in notebooks):**

| Task | Works | Fails / gotcha |
|---|---|---|
| Background | `plugin.canvas3d.setProps({renderer:{backgroundColor:...}})` | `viewer.setBackground()` is not a function |
| Find components | `plugin.managers.structure.hierarchy.current.structures[0].components` | — |
| Remove HETATM | `hierarchy.remove(componentRefs)` | `hierarchy.remove([comp.cell])` → "reading 'transform'" error |
| Chain coloring | `updateRepresentationsTheme(components, {color:'chain-id'})` | passing `comp.representations` → "not iterable" |
| Transparent surface | `addRepresentation(comp.cell, {type:'molecular-surface', typeParams:{alpha:0.40}})` | alpha 0.25 looked too faint; 0.40 is a good default. **Add surface to ALL components FIRST, then call `updateRepresentationsTheme` once on ALL components** — coloring before adding surface, or in two passes, gives mismatched cartoon/surface colors |
| Cartoon transparency | **not working** | `transparency` theme params and state-builder `alpha` updates have no visible effect, even at extreme values |
| Panel visibility | set at `Viewer.create()` time only | `layout.setProps(...)` / `regionState` after creation silently do nothing; CSS `display:none` on panels leaves the viewport squashed to a thin slice |
| Custom hex per chain | `updateRepresentationsTheme(components, {color:'chain-id', colorParams:{palette:{name:'colors', params:{list:{kind:'set', colors:[0x3A6EA5, 0xD62728]}}}}})`; pass the same `colorParams` to `addRepresentation` so surface matches | colors must be ints (`int(hex.lstrip('#'), 16)` in Python), not `'#RRGGBB'` strings; palette order follows chain order (A, B, ...) |

### Chain-id palette mapping (critical)

Molstar's `chain-id` color theme maps the palette to chains **by sorted
chain label of the chains present in the structure**, not by absolute
alphabetical position. The first chain present (alphabetically) gets
`palette[0]`, the second gets `palette[1]`, etc. If a chain is absent from
the loaded structure, its slot is skipped — there is no gap.

```python
# 3 chains (A, B, C): palette[0]=A, palette[1]=B, palette[2]=C
colors_3 = [int("8FB3DA",16), int("F2A49C",16), int("93D9D6",16)]

# 2 chains (A, B only): palette[0]=A, palette[1]=B
colors_ab = [int("8FB3DA",16), int("F2A49C",16)]

# 2 chains (A, C only — B absent): palette[0]=A, palette[1]=C
# Chain C gets index 1, NOT index 2 — do not pad for absent chains
colors_ac = [int("8FB3DA",16), int("93D9D6",16)]
```

**Common mistake:** when loading a 2-chain PDB (e.g. chains A+C), chain C
gets `palette[1]` (the second slot), NOT `palette[2]`. Do not pad the
palette with placeholder colors for absent chains.

**Panel option pitfalls:**
- `layoutShowControls: false` + `viewportShowControls: false` → no wrench at
  all; controls are unreachable.
- `layoutShowControls: true` + `collapseRightPanel: true` → panel starts
  collapsed but the wrench appears to do nothing (toggles hidden/collapsed).
- `collapseLeftPanel: false` → wrench also opens Home every time.
- `layoutShowSequence: true` only shows the sequence strip **inside the
  expanded layout** (wrench click), not on the compact default viewport.
  There is no reliable way to show the sequence strip on load without also
  showing the Home panel; the sequence lives in the "top" layout region
  which requires `layoutIsExpanded: true` + `collapseLeftPanel: false`.

**Debugging `displayHTML()` output:** the agent cannot see rendered iframe
output or JS console errors. While developing, add an on-page log div
(`<div id="mol-status">` + a `log()` helper writing ✓/✗ per step, each step
in its own `try/catch`) and ask the user to report what it shows. Remove the
log div from the final version.

**f-string escaping:** the HTML is a Python f-string, so every JavaScript
brace must be doubled (`{{ }}`). A single brace in a patched JS snippet
causes a Python `SyntaxError` before anything renders.

### Filtering PDB to specific chains

When the user wants only a subset of chains (e.g. one antibody + one antigen
from a multi-chain complex), filter the PDB text in Python before base64
encoding. This avoids extra components in Molstar and keeps the render clean.

```python
# Keep only chains A and B (ATOM records only, waters excluded)
pdb_2chain = "\n".join(
    l for l in pdb_text.splitlines()
    if (not l.startswith("ATOM") and not l.startswith("HETATM"))
    or (l.startswith("ATOM") and l[21] in "AB")
)
pdb_2chain_b64 = base64.b64encode(pdb_2chain.encode()).decode()
```

This keeps all header/remark records and ATOM lines for the selected chains.
HETATM records (waters, ligands) are excluded.

### Multiple viewers on one page (side-by-side comparison)

Load `molstar.js` once, then create multiple viewers in the `onload`
callback. Each viewer gets its own div, plugin, and data. Use a factory
function to avoid duplicating setup code.

```python
html = f"""
<div style="display:flex; gap:10px;">
  <div id="v1" style="width:420px; height:480px;"></div>
  <div id="v2" style="width:420px; height:480px;"></div>
</div>
<script>
(function() {{
  /* load molstar.css + molstar.js once, then: */
  s.onload = function() {{
    function setupViewer(divId, pdbB64, chainColors) {{
      molstar.Viewer.create(divId, {{
        layoutShowLeftPanel: false, /* ... other panel options ... */
      }}).then(function(viewer) {{
        var plugin = viewer.plugin;
        /* ... loadStructureFromData, HETATM removal, coloring ... */
      }});
    }}
    setupViewer('v1', '{pdb1_b64}', [Navy_300, Red_300]);
    setupViewer('v2', '{pdb2_b64}', [Navy_300, Teal_300]);
  }};
}})();
</script>
"""
displayHTML(html)
```

### RCSB Molstar wrapper (plain render only)

The `@rcsb/rcsb-molstar` wrapper ([genesis-workbench](https://github.com/databricks-industry-solutions/genesis-workbench)
pattern) is fine for an unstyled render, but its post-load customization
calls silently fail. Prefer the core package above.

```python
import base64, requests

pdb_id = "4Z18"
pdb_url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
pdb_text = requests.get(pdb_url).text
pdb_b64 = base64.b64encode(pdb_text.encode()).decode()

html = f"""
<div id="molstar-viewer" style="width:800px; height:600px; position:relative;"></div>
<script>
(function() {{
  var link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'https://cdn.jsdelivr.net/npm/@rcsb/rcsb-molstar@3.1.1/build/dist/viewer/rcsb-molstar.css';
  document.head.appendChild(link);

  var script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/npm/@rcsb/rcsb-molstar@3.1.1/build/dist/viewer/rcsb-molstar.js';
  script.onload = function() {{
    var viewer = new rcsbMolstar.Viewer('molstar-viewer', {{
      showImportControls: false,
      showSessionControls: false,
    }});
    viewer.loadStructureFromData(atob('{pdb_b64}'), 'pdb', false);
  }};
  document.head.appendChild(script);
}})();
</script>
"""
displayHTML(html)
```

**CDN notes:**
- **Core Molstar** (`cdn.jsdelivr.net/npm/molstar@4.5.0/build/viewer/`):
  loads and supports programmatic styling. **Use this.**
- **RCSB Molstar wrapper** (`cdn.jsdelivr.net/@rcsb/rcsb-molstar`): loads
  and renders with `rcsbMolstar.Viewer`, but post-load customization
  silently fails.
- **PDBe Molstar** (`ebi.ac.uk` CDN): fails to load in Databricks
  `displayHTML()` iframes (`PDBeMolstarPlugin is not defined`).

### When to choose Molstar over py3Dmol

- Need to display **large complexes** (>100k atoms, cryo-EM maps)
- Need **volumetric data** (electron density, cryo-EM)
- Need **multiple coordinated views** (structure + sequence + density)
- Building a **React app** (Molstar is natively a React plugin)
- Need **session state** (save/restore view, share URLs)

### React integration

```bash
npm install molstar
```

```tsx
// src/components/MolViewer.tsx
import { useEffect, useRef } from "react";
import { createPluginUI } from "molstar/lib/mol-plugin-ui";
import { DefaultPluginUISpec } from "molstar/lib/mol-plugin-ui/spec";
import "molstar/lib/mol-plugin-ui/skin/light.scss";

interface Props {
  pdbId: string;
  width?: string;
  height?: string;
}

export function MolViewer({ pdbId, width = "100%", height = "600px" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pluginRef = useRef<Awaited<ReturnType<typeof createPluginUI>> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const init = async () => {
      const plugin = await createPluginUI({
        target: containerRef.current!,
        spec: {
          ...DefaultPluginUISpec(),
          layout: {
            initial: {
              isExpanded: false,
              showControls: true,
            },
          },
        },
      });
      pluginRef.current = plugin;

      // Load structure from RCSB
      const data = await plugin.builders.data.download(
        { url: `https://files.rcsb.org/download/${pdbId}.cif` },
        { state: { isGhost: true } },
      );
      const trajectory = await plugin.builders.structure.parseTrajectory(data, "mmcif");
      await plugin.builders.structure.hierarchy.applyPreset(trajectory, "default");
    };

    init();

    return () => {
      pluginRef.current?.dispose();
    };
  }, [pdbId]);

  return <div ref={containerRef} style={{ width, height }} />;
}
```

### Loading from UC Volume (via FastAPI backend)

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.responses import Response

app = FastAPI()

@app.get("/api/structure/{filename}")
async def get_structure(filename: str):
    """Serve a PDB/CIF file from the UC Volume."""
    path = f"/Volumes/<catalog>/<schema>/<volume>/structures/{filename}"
    with open(path, "rb") as f:
        content = f.read()
    content_type = "chemical/x-cif" if filename.endswith(".cif") else "chemical/x-pdb"
    return Response(content=content, media_type=content_type)
```

## Protein-protein interfaces (only if asked)

If the user asks to compute, highlight or annotate an interface between
chains (contact residues, per-chain highlight colors, distance lines,
residue labels), load [protein-interface.md](protein-interface.md). Do not
add interface highlighting to a structure render unprompted.

## Multi-model comparison

For comparing structures side by side (e.g., docked poses, mutants):

```python
import py3Dmol

def compare_structures(pdb_data_list, labels=None,
                       width=400, height=400):
    """Render multiple structures in a grid for comparison."""
    n = len(pdb_data_list)
    cols = min(n, 3)
    rows = (n + cols - 1) // cols

    view = py3Dmol.view(
        width=width * cols, height=height * rows,
        viewergrid=(rows, cols),
    )

    for i, pdb in enumerate(pdb_data_list):
        r, c = divmod(i, cols)
        view.addModel(pdb, "pdb", viewer=(r, c))
        view.setStyle({"cartoon": {"colorscheme": "chain"}}, viewer=(r, c))
        view.setBackgroundColor("white", viewer=(r, c))
        view.zoomTo(viewer=(r, c))
        if labels:
            view.addLabel(labels[i], {
                "position": {"x": 0, "y": 0, "z": 0},
                "backgroundColor": "white",
                "fontColor": "black",
                "fontSize": 14,
            }, viewer=(r, c))

    return view.show()
```

## Common pitfalls

1. **py3Dmol `color` vs `colorscheme`**: `{"color": "chain"}` treats
   `"chain"` as a **literal color name** (falls back to black silently).
   Use `{"colorscheme": "chain"}` for data-mapped color schemes (chain,
   ss, Jmol, etc.). `"color"` is only for a single hex/named color like
   `"#D62728"`. This is the #1 py3Dmol gotcha.
2. **py3Dmol surface at buried interfaces**: `addSurface` on a residue
   selection renders the solvent-exposed face, not the buried protein-
   protein contact zone. Use Molstar (or NGL as a last resort).
3. **py3Dmol `within` includes HETATM**: the `within` distance selector
   matches all atoms -- waters, ions, hydrogens. Add `"hetflag": False`
   on both the selecting and target selections for protein-only contacts.
4. **py3Dmol not rendering in notebook**: ensure you call `.show()` as the
   last expression in the cell. Assigning to a variable and printing later
   may not trigger the JavaScript.
5. **Large PDB files slow**: for structures >500k atoms, use Molstar or
   simplify the representation (e.g., surface only, no stick/ball).
6. **mmCIF vs PDB format**: modern PDB entries may only have mmCIF. Use
   `"cif"` as the format argument in `addModel()`.
7. **Background color**: always set to white for figures; the default dark
   background doesn't work in papers or light-themed apps.
8. **Coordinate systems**: PDB coordinates are in Angstroms. If overlaying
   data from different sources, verify alignment first.
9. **Wrong Molstar package**: the `@rcsb/rcsb-molstar` wrapper silently
   ignores customization and PDBe Molstar does not load at all. Use the core
   `molstar` package (`molstar@4.5.0/build/viewer/`), which supports
   HETATM removal, chain coloring and surfaces.
10. **Interface identification**: a simple distance cutoff (5 A) captures
    crystal packing contacts beyond the biological interface. Prefer
    literature-curated residues or PDBePISA BSA analysis.
11. **Silently switching libraries**: do not fall back from Molstar to NGL
    (or py3Dmol) without trying Molstar first and telling the user what
    failed. The user's preference is Molstar.
12. **Molstar panels changed after creation**: layout must be set in
    `Viewer.create()` options. Target state: `layoutShowControls: false`,
    `viewportShowControls: true`, `collapseRightPanel: false`,
    `collapseLeftPanel: true` (wrench present, not open, opens tools only).
13. **Molstar cartoon transparency**: no working method found from the CDN
    build. Don't promise it; use surface alpha for see-through effects.
14. **Unescaped braces in f-string HTML**: double every JS brace (`{{ }}`).
15. **Molstar surface + cartoon color mismatch**: add the surface to ALL
    polymer components first, then call `updateRepresentationsTheme` once on
    ALL components. If you color before adding the surface, or color in two
    passes, cartoon and surface get different color mappings and appear
    "mixed."
