# accelerators Skill Evaluation

## Overview

Benchmark evaluation for the `accelerators` skill following the [skill-eval](../../skill-eval/SKILL.md) methodology. Tests whether the skill makes Genie Code steer to the right HLS solution accelerator and end with a precise next step, instead of building from scratch or leaving the user at a link. No accelerator needs to be installed.

## Benchmark Tasks

| task_id | difficulty | task | discriminator |
|---------|-----------|------|---------------|
| acc-001 | easy | DICOM metadata to Delta, later browser viewing | Uses Pixels (`Catalog`, `DicomMetaExtractor`, OHIF) instead of a hand-written pydicom loop |
| acc-002 | hard | Protein folding and design with a UI for scientists | Genesis Workbench, admin install, core before large_molecule |
| acc-004 | edge | Fine-tune Geneformer | Genesis Workbench, honest that Geneformer is "coming soon", interim path |
| acc-005 | edge | Full Pixels install on Azure as a non-admin | Gated features, Azure GPU type, admin vs user split |

acc-002, acc-004 and acc-005 are discriminators: without the skill the base model either does not know the accelerator exists, claims support that is not there, or misses cloud and permission details. Task IDs skip acc-003 (an x12-edi-parser task parked until that accelerator is added).

## Data

Synthetic only (`generate_data.py`): 18 CT DICOM files (3 patients x 2 series x 3 instances).

Volume: `/Volumes/hls_amer_catalog/vital_skills/eval/accelerators/` (override with `SKILL_EVAL_DATA_DIR`; replace the path in `evalset.json` queries to match).

## Scorer Summary

| scorer | level | type | checks |
|--------|-------|------|--------|
| artifact_produced | L1 | deterministic | An answer file exists and is non-empty |
| steers_to_accelerator | L1 | deterministic | Every required pattern group in `deterministic_checks.required_patterns` matches |
| no_forbidden_content | L1 | deterministic | No forbidden pattern in the answer |
| precise_next_step | L2 | LLM judge | Answer ends with a concrete command, code or named admin action |
| factually_grounded | L2 | LLM judge | No contradiction of expected facts or guidelines |

Judge model: `databricks:/databricks-gpt-5-mini` (must differ from the Genie Code model). Pass rule: `all_metrics`.

## Ship Gate

Default: `win_rate > 0` and zero regressions at any difficulty.

## Run Protocol

Genie Code keeps memories across chats. Before each arm, start a chat and ask it to delete memories about this eval, and use a fresh notebook per task.


1. **Seed data**: `python3 generate_data.py` (or set `SKILL_EVAL_DATA_DIR`).
2. **Baseline arm**: make sure `accelerators` is not in any registered skill folder. For each task open a fresh Genie Code chat, paste the query from `evalset.json` verbatim and let it finish. Then move `outputs/*.md` to `outputs/baseline/`.
3. **Candidate arm**: register the skill folder without `eval/`, hard-refresh, repeat the same queries in fresh chats. Move `outputs/*.md` to `outputs/with_skill/`.
4. **Score**: run `score_accelerators.py` with the widgets pointing at your skills root, data volume and experiment.
5. **Report**: write `eval_report.md` from the comparison and the failure taxonomy (see `skill-eval/references/report-template.md`).
