---
name: accelerators
description: HLS solution accelerator steerage for Databricks. Routes a task to an existing databricks-industry-solutions accelerator and gives the precise next step - Pixels (DICOM medical imaging, OHIF viewer, DICOMweb, MONAI segmentation) and Genesis Workbench (protein folding and design, docking, ADMET, single-cell foundation models, variant calling, NVIDIA BioNeMo). Consult before building an imaging pipeline or biology model stack from scratch. For notebook single-cell analysis use sc-rnaseq; for de-identifying tables use phi-deidentifier.
category: Others
summary: Route imaging and biology-model tasks to an HLS accelerator — Pixels or Genesis Workbench — with the exact next step.
version: 0.5
author: Rohan Parikh
license: Databricks License
---

# HLS Accelerators

## Overview

Databricks publishes Health and Life Sciences solution accelerators under [databricks-industry-solutions](https://github.com/databricks-industry-solutions). Many requests ("index my DICOM files", "fold these proteins", "dock this ligand") are already solved by one of them. This skill routes the request to the right accelerator and ends with a precise next step: the exact library call, install command or admin action the user needs, plus the pitfalls that are not obvious from the README.

The skill is instructions only. It does not install or run accelerators itself. Per-accelerator facts live in `references/accelerators/`; the index is `references/accelerators/index.md`. Others can add accelerators by copying `references/accelerator-template.md`.

## When to Use

- A user wants to ingest, catalog or query DICOM images (CT, MR, X-ray) on Databricks, view them in a browser or auto-segment CT scans
- A user wants protein structure prediction (AlphaFold2, ESMFold, Boltz) or protein design (RFdiffusion, ProteinMPNN) at scale
- A user wants small-molecule generation, docking or ADMET/toxicity prediction
- A user wants cell-type annotation against a reference atlas (SCimilarity), scGPT perturbation or a single-cell foundation model behind a UI
- A user needs germline variant calling (NVIDIA Parabricks), GWAS, ClinVar annotation or NVIDIA BioNeMo fine-tuning
- A user is about to hand-write a pipeline, parser or serving wrapper that an accelerator already provides

## Key Concepts

### Steer, do not rebuild
The base model does not know these accelerators exist and will write pydicom loops or custom folding endpoints from scratch. Recommending the accelerator first saves days and avoids known failure modes.

### Precise next step
Every answer ends with a short **Next step** section: one concrete action the user can take now (a command or snippet to run) and, if something is blocking them, the exact admin action and who does it. A link or "see the docs" is not a next step.

### The repo is the source of truth
Accelerators change weekly. Use the facts in `references/accelerators/<name>.md` for routing and pitfalls, then read the accelerator's own README and install docs for current steps. If the repo is cloned as a Git folder in the workspace, read the files there; otherwise give the user the repo URL and the exact file to open.

### Library path vs full install
Some accelerators can be used as a Python library from a notebook (Pixels cataloging from a repo clone; check the serverless caveat in its reference). Others are a full install of apps, jobs and GPU endpoints that needs workspace admin rights (Genesis Workbench, Pixels viewer and segmentation). Recommend the smallest path that answers the request.

### Accelerators are not supported products
They are provided as-is without SLAs. Problems go to the repo's GitHub Issues, not Databricks support.

## Decision Framework

```
What is the user trying to do?
├── Medical imaging (DICOM)
│   ├── Index files, query metadata in SQL → Pixels, library path
│   ├── Browser viewer, DICOMweb endpoint, CT auto-segmentation → Pixels, full install
│   └── De-identify DICOM tags → Pixels DicomMetaAnonymizerExtractor
│       (structured tables instead → phi-deidentifier)
└── Life sciences models
    ├── Proteins: fold, design, embed → Genesis Workbench large_molecule
    ├── Small molecules: generate, dock, ADMET → Genesis Workbench small_molecule
    ├── Single-cell foundation models (SCimilarity, scGPT, TEDDY) → Genesis Workbench single_cell
    │   (notebook QC, clustering, markers → sc-rnaseq)
    ├── Geneformer → Genesis Workbench bionemo; support is marked "coming soon",
    │   so say so and offer the `open-weight-models` skill as the interim path
    ├── Variant calling, GWAS, ClinVar → Genesis Workbench genomics
    └── Model not shipped by Genesis Workbench → `open-weight-models` skill
```

| Task | Accelerator | Smallest path | Reference |
|------|-------------|---------------|-----------|
| Catalog DICOM files into a Delta table | Pixels | `Catalog` + `DicomMetaExtractor` | `references/accelerators/pixels.md` |
| OHIF viewer, DICOMweb, Vista3D segmentation | Pixels | Full install (admin) | `references/accelerators/pixels.md` |
| Protein structure prediction or design | Genesis Workbench | Full install: core + large_molecule (admin) | `references/accelerators/genesis-workbench.md` |
| Docking, molecule generation, ADMET | Genesis Workbench | Full install: core + small_molecule (admin) | `references/accelerators/genesis-workbench.md` |
| Single-cell foundation models | Genesis Workbench | Full install: core + single_cell (admin) | `references/accelerators/genesis-workbench.md` |
| Variant calling, GWAS, ClinVar | Genesis Workbench | Full install: core + genomics (admin) | `references/accelerators/genesis-workbench.md` |

## Best Practices

1. **Route before writing code**: Match the request to the Decision Framework, then read only that accelerator's reference.
2. **Check whether it is already deployed**: Before proposing an install, ask the user or check the workspace for the signals listed in the reference (app, endpoint or table names). If it is deployed, point the user at it.
3. **Prefer the smallest path**: Use the library path when it answers the request. Do not propose a full install to get DICOM metadata into a table.
4. **Name the blocker precisely**: When an install needs admin rights or gated features, list exactly which ones and who enables them.
5. **Cite the repo and the file**: Give the repo URL and the specific README or install doc section so the user can follow current steps.

## Troubleshooting

1. **The accelerator does not cover the request**: Recommending it anyway sends the user down a dead end.
   - *How to avoid*: Check the capability list in the reference; if nothing matches, say so and name the related skill.
2. **Install fails on a gated feature**: Pixels needs Apps user token passthrough, Lakebase and Reverse ETL; Genesis Workbench needs workspace admin.
   - *How to avoid*: List prerequisites from the reference before giving install commands.
3. **Cloud-specific settings break the install**: For example `GPU_MEDIUM` serving does not exist on Azure.
   - *How to avoid*: Ask which cloud the workspace runs on and apply the cloud notes in the reference.
4. **Code fails on serverless**: Some accelerator notebooks and helpers assume classic compute (RDDs, `/local_disk0`, init scripts).
   - *How to avoid*: Ask which compute the user has and prefer the patterns the reference marks as serverless-safe.
5. **Resources deleted by hand break later deploys**: Genesis Workbench tracks deployments with `.deployed` files and settings tables.
   - *How to avoid*: Remove modules only with `./destroy.sh <module> <cloud>`.

## Workflow

1. **Step 1: Classify the request**
   - Map it to a row in the Decision Framework
   - Decision point: no match → say no covered accelerator fits and suggest the related skill
2. **Step 2: Read the reference**
   - Open `references/accelerators/<name>.md` for capabilities, deploy signals, paths and pitfalls
3. **Step 3: Check the current state**
   - Ask or check whether the accelerator is already deployed and which cloud the workspace uses
4. **Step 4: Answer and close with a Next step section**
   - Library path: the install line and the minimal working snippet
   - Full install: prerequisites, commands in order, expected duration and the admin actions needed
   - Point to the repo's README or install doc for anything beyond the reference
   - Finish with `Next step`: the first command or snippet to run now, then any admin action with the role that performs it

## Protocol Guidelines

1. **One reference per accelerator**: Copy `references/accelerator-template.md` to `references/accelerators/<name>.md` and add a row to `references/accelerators/index.md`.
2. **Stable facts only**: References hold capabilities, deploy signals, prerequisites and the riskiest pitfalls. Step-by-step install text stays in the accelerator's repo.
3. **Record what was reviewed**: Each reference lists the date and upstream commit it was checked against.
4. **Update this file only for routing**: Add a Decision Framework branch and table row when a new accelerator is added.

## Evaluation

Evaluated with `skill-eval` on 2026-10-05 (full report: `eval/eval_report.md`).

| Run | Baseline | With skill | Outcome |
|-----|----------|------------|---------|
| Workspace Genie Code, 4 tasks | 0/4 pass | 3/4 pass | 3 wins, 0 regressions, ship gate pass |
| Genie Code CLI routing, 10 prompts | 3/10 | 10/10 | no false triggers on 3 unrelated prompts |

Without the skill, Genie Code rebuilt a DICOM pipeline and a protein folding stack from scratch and gave wrong Pixels facts. The remaining tie (DICOM to Delta) reflects that Pixels' library did not install on serverless in testing; the skill now says so.

## Guardrails

1. Do not install or deploy accelerators on the user's behalf; give the commands and let the user or their admin run them.
2. Do not claim an accelerator supports a model, format or cloud unless its reference or repo documents it.
3. Treat accelerator outputs (segmentations, structure predictions, variant calls) as research results, not clinical or regulatory validation.
4. Never suggest deleting accelerator resources in the workspace UI; use the accelerator's destroy or uninstall script.
5. Avoid retrying more than 3 times; if an install step keeps failing, collect the task name and logs and point the user to the repo's GitHub Issues.

## References

- [databricks-industry-solutions](https://github.com/databricks-industry-solutions) - all published solution accelerators
- [Pixels](https://github.com/databricks-industry-solutions/pixels) - DICOM ingestion, OHIF viewer, DICOMweb, MONAI segmentation
- [Genesis Workbench](https://github.com/databricks-industry-solutions/genesis-workbench) - life sciences foundation models, workflows and MCP server

## Related Skills

- `open-weight-models` - package and serve an open-weight HLS model that Genesis Workbench does not ship
- `sc-rnaseq` - notebook-level single-cell analysis with scanpy and rapids-singlecell
- `phi-deidentifier` - de-identify structured Unity Catalog tables (Pixels covers DICOM tags)
