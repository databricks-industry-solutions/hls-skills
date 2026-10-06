# Genesis Workbench

## Identity

- Repo: https://github.com/databricks-industry-solutions/genesis-workbench
- Install doc: `Installation.md`; Claude Code skills in `claude_skills/` (install, deploy wizard, troubleshooting, workflows)
- Maintainers: see the repo's contributors page
- Reviewed: 2026-10-05 against commit ca7de8d

## Use it for

A Databricks App plus model endpoints and jobs for life sciences foundation models, deployed per module:

| Module | Models and workflows |
| --- | --- |
| large_molecule | AlphaFold2, ESMFold, Boltz, ESM-2 embeddings, RFdiffusion, ProteinMPNN, protein sequence search |
| small_molecule | GenMol, DiffDock, Chemprop (BBBP, ClinTox, ADMET), KERMT, Proteina-Complexa, NetSolP, PLTNUM, DeepSTABp, MHCflurry |
| single_cell | Scanpy, rapids-singlecell, scGPT (incl. perturbation), SCimilarity (23M-cell reference), TEDDY |
| genomics | NVIDIA Parabricks germline calling, VCF to Delta, Glow GWAS, ClinVar annotation |
| bionemo (optional) | NVIDIA BioNeMo ESM-2 fine-tuning and inference, KERMT fine-tuning; Geneformer tab present but marked "coming soon" |

It also ships a workflow builder in the UI and an MCP server app that exposes deployed endpoints and workflows as tools.

## Do not use it for

- A model it does not ship: package it with the `oss-models` skill
- Notebook-level single-cell QC, clustering and markers without a UI: use `sc-rnaseq`
- Bulk RNA-seq differential expression: use `bulk-rnaseq`

Geneformer: route to Genesis Workbench (bionemo module), and tell the user its Geneformer support is marked "coming soon" in the current release. Until it ships, the `oss-models` skill in hls-skills has a Geneformer packaging reference. Next step for the user: type `@oss-models` in Genie Code and ask it to package Geneformer, which loads `references/models/geneformer.md` from that skill.

## Deploy signals

- Apps `genesis-workbench` (UI) and `mcp-genesis-workbench` (MCP server)
- A `settings` table in the Genesis Workbench schema listing deployed modules
- Model serving endpoints and jobs created per module

## Smallest path

None without an install. If it is already deployed, point the user to the UI app or the endpoints. If the `mcp-genesis-workbench` app is connected as an MCP server, its tools are `list_capabilities`, `endpoint_<name>` (synchronous) and `workflow_<name>` (returns a run id; poll `get_workflow_run_status`).

## Full install

Prerequisites:

- Workspace admin runs the install
- Python 3.11 and the Databricks CLI, with the target workspace as the `DEFAULT` profile
- A Unity Catalog catalog and a schema used only by Genesis Workbench
- A SQL warehouse (2X-Small is enough)
- For bionemo only: build the BioNeMo container from `modules/bionemo/docker/` and push it to a registry

Configuration: create `application.env` in the repo root (`workspace_url`, `core_catalog_name`, `core_schema_name`, `sql_warehouse_id`) and `modules/core/module.env` (`dev_user_prefix`, `app_name`, `secret_scope_name`). Cloud files `aws.env` and `azure.env` hold node and GPU defaults.

Commands, from a local clone:

```bash
./deploy.sh core <aws|azure>
./deploy.sh large_molecule <aws|azure>     # then other modules, one at a time
```

Each module starts background jobs that download and register models; these can take several hours. Wait for one module's jobs to finish before deploying the next.

## Pitfalls

- **Never rerun `./deploy.sh core` on a populated install**: it resets settings. Use `modules/core/update.sh <cloud> --ui-only` for UI changes.
- **Never delete resources in the workspace UI**: deployments are tracked with `.deployed` files and settings tables. Remove with `./destroy.sh <module> <cloud>`; core can only be destroyed after all modules.
- **Cloud support**: the install guide documents aws and azure. A `gcp.env` exists, but GCP is not documented.
- **AWS has no `GPU_LARGE`**: `aws.env` maps the large setting to `MULTIGPU_MEDIUM`.
- **MCP server access**: every MCP call runs as the app service principal with no per-user authorization. Grant `CAN_USE` on the MCP app only to the intended group; do not share it with all users.
- **SCimilarity requests over 16 MB are rejected** by serving; batch the input.
- **Long first deploys**: SCimilarity downloads can take over an hour and AlphaFold database downloads can fail on AWS; see `claude_skills/SKILL_GENESIS_WORKBENCH_TROUBLESHOOTING.md`.
