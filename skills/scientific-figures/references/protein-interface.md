# Protein-Protein Interface Visualization (on request only)

Subskill of `scientific-figures`, extending [protein-structure-3d.md](protein-structure-3d.md).
**Load only when the user asks** to show, compute, highlight or annotate an
interface / contacts / binding patch between chains. This is NOT part of the
default structure render. Build on the verified core-Molstar notebook pattern
in `protein-structure-3d.md` (panel options, HETATM removal, chain palette).

Verified on PDB 4Z18 (PD-L1 homodimer) in a Databricks notebook with
`molstar@4.5.0` from jsDelivr via `displayHTML()`.

## Workflow

1. **Compute the interface in Python (Biopython)**, not in the viewer. You
   get an inspectable residue table you can check against the literature,
   save, and pass to Molstar as plain residue lists.
2. **Sanity-check** against published residues and the biological assembly.
3. **Display in core Molstar** with each chain's interface as its own
   component, optionally with distance lines and residue labels.

## 1. Interface residues (Biopython)

```python
%pip install biopython -q   # with dbutils.library.restartPython() in the install cell
```

```python
import io, requests, pandas as pd
from Bio.PDB import PDBParser, NeighborSearch

CUTOFF = 4.5   # Å, heavy atom to heavy atom (user default for this task)
pdb_text = requests.get("https://files.rcsb.org/download/4Z18.pdb").text
model = PDBParser(QUIET=True).get_structure("4Z18", io.StringIO(pdb_text))[0]

# Polymer heavy atoms only: hetflag ' ' drops HETATM + water; drop hydrogens
atoms = [a for a in model.get_atoms()
         if a.get_parent().id[0] == " " and a.element != "H"]

records = []
for a1, a2 in NeighborSearch(atoms).search_all(CUTOFF, level="A"):
    r1, r2 = a1.get_parent(), a2.get_parent()
    c1, c2 = r1.get_parent().id, r2.get_parent().id
    if c1 == c2:
        continue                                # inter-chain contacts only
    for r, c, pr, pc in [(r1, c1, r2, c2), (r2, c2, r1, c1)]:
        records.append({"chain": c, "resi": r.id[1], "resn": r.get_resname(),
                        "partner": f"{pc}:{pr.get_resname()}{pr.id[1]}",
                        "dist": float(a1 - a2)})

interface = (pd.DataFrame(records).groupby(["chain", "resi", "resn"])
             .agg(min_dist_A=("dist", "min"), atom_pairs=("dist", "size"),
                  partners=("partner", lambda s: ", ".join(sorted(set(s)))))
             .reset_index())
INTERFACE = {c: sorted(g["resi"]) for c, g in interface.groupby("chain")}
```

**Optional patches + closest contact:** keep atom-level pairs (atom names
and midpoint coords), single-linkage cluster the contact midpoints (10 Å link
distance worked for 4Z18: 2 patches), take the minimum-distance pair per
patch. Convert everything to plain Python types (`int()`, `float()`) before
`json.dumps`; numpy int64 is not JSON serializable.

## 2. Sanity checks (always report these)

- Compare with any literature residues and say how many are recovered
  (4Z18 at 4.5 Å: only 2 of 4 published residues, E39 and Q91, both chain A).
- **Asymmetric-unit contacts may be crystal packing, not the biological
  interface.** If the two chains contribute non-equivalent residues (chain A
  139-146 vs chain B 135-142, as in 4Z18), flag that it may not be a
  symmetric biological dimer and suggest checking the RCSB biological
  assembly or PDBePISA.
- A fixed distance cutoff includes packing contacts; prefer curated residues
  or PISA buried-surface analysis when the user needs "the" interface.

## 3. Display in core Molstar

Start from the verified notebook pattern in `protein-structure-3d.md`
(same `Viewer.create` panel options, HETATM removal, chain-id palette,
surface alpha 0.40). Then add the pieces below. Every JS brace inside the
Python f-string must be doubled (`{{ }}`); the snippets below are shown as
plain JS.

### Residue-set components (verified)

Pass residues as a PyMOL-syntax script. One component per chain lets each
chain have its own highlight color.

```python
def pymol_selection(interface):   # {'A': [24, 25]} -> '(chain A and resi 24+25)'
    return " or ".join(f"(chain {c} and resi {'+'.join(map(str, r))})"
                       for c, r in interface.items() if r)
```

```javascript
plugin.builders.structure.tryCreateComponent(st.cell, {
  type: { name: 'script', params: { language: 'pymol', expression: sel } },
  nullIfEmpty: true, label: 'Interface chain A (4.5 Å)'
}, 'interface-A').then(function(iface) {
  return rep.addRepresentation(iface, {           // rep = plugin.builders.structure.representation
    type: 'ball-and-stick',                       // or 'molecular-surface' + typeParams:{alpha:0.85}
    color: 'uniform', colorParams: { value: 0x0B1F3A } });   // int color
});
```

- Components show up by label in the wrench panel, so users can toggle them.
- **Color option the user liked for per-chain highlights:** chain body in the
  family's 300 shade, that chain's interface in its 900 shade (e.g. Navy
  300 `#8FB3DA` / Navy 900 `#0B1F3A`, Red 300 `#F2A49C` / Red 900
  `#7F1414`). Single shared highlight (Orange 500 `#F28C28`) is the simpler
  alternative, but it is close to Red and weak on a red chain.
- Do not overlay a second cartoon on the interface residues to recolor them
  (coincident geometry z-fights). Use sticks or a surface patch instead.

### Distance lines + residue labels

`plugin.managers.structure.measurement.addDistance(a, b, opts)` and
`addLabel(a, opts)` need `StructureElement.Loci` on the **parent**
structure. `repr.getAllLoci()` does NOT return usable loci (error:
`e.elements is not iterable`). Build the loci yourself:

```javascript
function atomLoci(sel, color, key) {        // sel e.g. 'chain A and resi 91 and name OE1'
  var comp;
  return plugin.builders.structure.tryCreateComponent(st.cell, {
    type: { name: 'script', params: { language: 'pymol', expression: sel } },
    nullIfEmpty: true, label: key }, key).then(function(c) {
    if (!c) throw new Error('empty selection: ' + sel);
    comp = c;
    return rep.addRepresentation(c, { type: 'ball-and-stick',
      color: 'uniform', colorParams: { value: color } });
  }).then(function() {
    var atomIdx = comp.cell.obj.data.units[0].elements[0];   // model atom index
    var parent = st.cell.obj.data;
    for (var u = 0; u < parent.units.length; u++) {
      var local = Array.prototype.indexOf.call(parent.units[u].elements, atomIdx);
      if (local >= 0) return { kind: 'element-loci', structure: parent,
        elements: [{ unit: parent.units[u], indices: Int32Array.of(local) }] };
    }
    throw new Error('atom not found in parent: ' + sel);
  });
}
// then: meas.addDistance(L1, L2, distOpts); meas.addLabel(L1, labelOpts('Q91 (A)'));
```

- Labels: anchor residue labels on the CA atom
  (`chain X and resi N and name CA`). Label the closest-contact residues plus
  a few others (e.g. top 3 per chain by atom contacts + published residues);
  skip residues already labelled at a distance line. Expect overlap in dense
  patches; keep the count small.
- **Unconfirmed:** size/text options. Current code passes
  `{customText, labelParams:{customText, textSize:1.5}, visualParams:{textSize:1.5}}`
  to `addLabel` and
  `{lineParams:{linesSize:0.2}, labelParams:{textSize:1.5}, visualParams:{textSize:1.5, linesSize:0.2}}`
  to `addDistance`. Not yet verified that these enlarge the text/lines or
  that custom label text replaces Molstar's default; check with the user
  before relying on it.

### Sequencing

Run Molstar builder/measurement calls **one after another** (chain promises
with `array.reduce(function(p, x){ return p.then(...) }, Promise.resolve())`),
not in parallel. Keep the on-page diagnostic log (one ✓/✗ per step) while
developing and ask the user to read it back; the agent cannot see
`displayHTML()` output.

## Avoid

- **MolViewSpec** (`viewer.loadMvsData(json, 'mvsj')`) rendered a blank
  viewer in `molstar@4.5.0` CDN inside `displayHTML()` (cause unknown). Use
  the component/script approach above.
- Computing contacts in JS inside the viewer: harder to inspect, validate
  or reuse than the Biopython table.
