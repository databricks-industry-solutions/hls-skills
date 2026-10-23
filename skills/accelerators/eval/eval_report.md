# Evaluation Report: accelerators Skill

**Setup**: 4 benchmark tasks run with and without the skill in workspace Genie Code (fevm workspace, 2026-10-05), plus a 10-prompt routing set and the same 4 tasks through the Genie Code CLI (`genie exec`, model gpt-5.6-sol via AI Gateway) as a faster supporting check. Scored with MLflow 3 `mlflow.genai.evaluate`: 3 deterministic scorers (artifact_produced, steers_to_accelerator, no_forbidden_content) and 2 binary LLM judges (precise_next_step, factually_grounded; judge `databricks-gpt-5-mini`). Pass rule: all metrics. No accelerator was installed in the workspace.

## Results: workspace Genie Code (primary)

| task_id | difficulty | baseline | with skill | outcome |
|---------|-----------|----------|------------|---------|
| acc-001 | easy | fail | fail | tie-fail |
| acc-002 | hard | fail | pass | **win** |
| acc-004 | edge | fail | pass | **win** |
| acc-005 | edge | fail | pass | **win** |

Win rate: 3/4. Regressions: 0/4. **Ship gate PASS.**

| task | baseline behavior | with skill |
|------|-------------------|------------|
| acc-001 DICOM to Delta + viewer | Hand-built pydicom pipeline, PNG previews, suggests a Streamlit viewer; never mentions Pixels | Names Pixels and its OHIF viewer and full install, but leads with a pydicom pipeline for the metadata step (see failure modes) |
| acc-002 protein folding + design UI | Builds its own Boltz-2 / RFdiffusion jobs and a Streamlit app (2 jobs created, several manual steps left) | Genesis Workbench: admin, `deploy.sh core` then `large_molecule`, pitfalls |
| acc-004 fine-tune Geneformer | Generic Geneformer fine-tuning guide | Genesis Workbench with Geneformer marked "coming soon", interim path, concrete next step |
| acc-005 Pixels on Azure as non-admin | Finds Pixels by name but says TotalSegmentator (wrong model) and `pip install databricks-pixels` (not on PyPI); no gated features | Token passthrough, Lakebase, Reverse ETL, Azure GPU type, admin vs user split, `make deploy` |

Interference check (with skill only): an unrelated readmission-rate SQL prompt produced no mention of Pixels or Genesis Workbench.

## Results: Genie Code CLI (supporting)

Routing set (10 short prompts, 7 that should route and 3 that should not):

| arm | correct | notes |
|-----|---------|-------|
| without skill | 3/10 | passes only the 3 negatives; never names Pixels or Genesis Workbench |
| with skill | 10/10 | read `SKILL.md` in 9/10 runs; no false triggers on the 3 negatives |

Full tasks: 3/4 wins, 0 regressions (acc-004 tie-fail: the judge did not count "type `@oss-models ...` in Genie Code" as a concrete action).

Economics (CLI, where token counts are reported): routing set 387k tokens with skill vs 242k without (the skill files are read); full tasks 181k vs 212k with 66 s vs 113 s total wall time, because the baseline explores and drafts longer answers.

## Failure taxonomy

| failure mode | count | arm | status |
|--------------|-------|-----|--------|
| unaware-of-accelerator (rebuilds from scratch or generic guide) | 3/4 tasks | baseline | eliminated by skill |
| wrong-accelerator-facts (wrong model, nonexistent PyPI package, missing gated features) | 1/4 | baseline | eliminated by skill |
| no-runnable-next-step | 2/4 (CLI v1) | with skill | fixed: SKILL.md now requires a closing Next step section |
| skill-body-not-read (prompt forbade commands, answered from description only) | 1 run set | with skill | harness artifact; removed from prompts |
| accelerator-library-not-installable-on-serverless | 1/4 (acc-001) | with skill | open; Pixels' pinned requirements failed to install on serverless (env 3 and 5) |
| judge-rejects-skill-handoff (`@oss-models` not counted as an action) | 1/4 (CLI) | with skill | judge limitation; not tuned after the fact |

## Changes made during evaluation

1. Added a required **Next step** section to every answer (fixed two CLI next-step failures).
2. Moved the Geneformer "coming soon" status into the SKILL.md decision tree and labeled `oss-models` as a skill.
3. Corrected the Pixels smallest path after testing: it runs from a repo clone, not a pip package, and its requirements failed to install on serverless. The acc-001 expectation was corrected to match (it previously assumed the library installs anywhere). This is a change to the answer key after a run, made because the key encoded a false fact.

## Limitations

- One run per task per arm; LLM output varies between runs.
- Workspace Genie Code memory persists across chats; it was cleared before the with-skill arm, but both arms shared a schema, and acc-001 with skill hit a table left by the baseline run.
- No accelerator was deployed, so day-2 use (querying an installed Pixels catalog, calling Genesis Workbench endpoints) is not covered.
- Token and time economics are only available from the CLI; workspace Genie Code does not expose them.

## Ship decision

Ship. 3/4 task wins and 0 regressions in workspace Genie Code, 10/10 routing with no false triggers. Follow-ups: report the Pixels serverless install issue to its maintainers, re-run acc-001 once Pixels installs on serverless or ships a wheel, and add day-2 tasks once accelerators are deployed in a shared eval workspace.

## v0.6 update: funke-hl7v2 (2026-10-22)

**Setup**: v0.6 adds funke-hl7v2 routing and 2 tasks (acc-006, acc-007), run in workspace Genie Code (primary) and the Genie Code CLI (supporting).

### Results: workspace Genie Code (primary)

All 11 hls-skills installed as user skills in the with-skill arm; none in the baseline. Fresh notebook and chat per task, memories cleared before each arm, answers saved to a Volume and scored with the scorers below.

| task_id | difficulty | baseline | with skill | outcome |
|---------|-----------|----------|------------|---------|
| acc-006 | easy | fail | pass | **win** |
| acc-007 | edge | fail | pass | **win** |

Win rate: 2/2. Regressions: 0/2. **Ship gate PASS.** Baseline answers wrote their own HL7 parsers and had no Next step; with the skill both used funke, the tested install line and batch split, and ended with a runnable Next step.

Day-2 check (funke already deployed by its bundle, graded by hand): asked for discharged patients (ADT A03) in the catalog. Both arms found `parsed_messages` and returned the correct 2 patients. With the skill, Genie Code also recognized the funke deployment from its pipeline name, did not propose an install, gave the batch split for the NULL batch row and ended with a runnable Next step (`pipelines start-update`). Outcome: tie-pass; the skill does not get in the way once the accelerator is deployed.

### Results: Genie Code CLI (supporting)

All CLI runs use the Genie Code CLI (`genie exec`, model gpt-5.6-sol via AI Gateway, fevm workspace). The with-skill arm installs **all** hls-skills, not only `accelerators`, so every run also checks interference with the other skills. Same scorers and judge as v0.5; the judge is given the exact prompt the agent received (CLI prompts use local paths and ask for the answer only).

### Full tasks (CLI, repeated)

| task_id | difficulty | baseline | with skill, before next-step fix | with skill, after fix |
|---------|-----------|----------|----------------------------------|-----------------------|
| acc-006 | easy | 0/3 | 1/3 (2 runs lacked a runnable Next step) | **3/3** |
| acc-007 | edge | 0/3 | 3/3 | **3/3** |

Ship gate PASS on every run (win rate > 0, 0 regressions).

| task | baseline behavior | with skill |
|------|-------------------|------------|
| acc-006 HL7v2 ADT files to Delta | Hand-written SQL that splits segments on `\r` and `\|`; never mentions funke | funke: `%pip install --no-build-isolation`, `parse_hl7v2_msg`, NULL-parse check, field extraction, Next step |
| acc-007 FHS/BHS batch files | Generic advice (HAPI, Smolder); no funke | funke plus the tested batch split, NULL-parse check and PID-3 note |

### Routing (CLI, all hls-skills installed)

| set | without skills | with skills | notes |
|-----|----------------|-------------|-------|
| v0.5 set + 5 funke/negative prompts (15) | 5/15 | 13/15 | funke 3/3; negatives 5/5 (FHIR clean; length-of-stay metric view went to `payer-provider-measure-catalog`) |
| Held-out HL7 prompts written after the skill (7) | 2/7 | **7/7** | Epic Bridges ADT^A08, ORU OBX labs, VXU registry, MDM OBX-5 notes, bed census; X12 837 and C-CDA negatives clean |
| Near misses, graded by hand (3) | n/a | **3/3** | HL7 to FHIR: parse with funke, says conversion is not covered. MLLP listener: says it runs outside Databricks, funke parses only. De-identify HL7: funke, then hands off to `phi-deidentifier` |

The 2 misses in the first set are interference, not a v0.6 regression. Paired re-runs (3 per prompt, all skills installed) against v0.5:

| prompt | v0.5 | v0.6 |
|--------|------|------|
| R5 cell-type annotation against a reference atlas | 0/3 | 2/3 |
| R7 fine-tune Geneformer | 0/3 | 0/3 |

### Regression on v0.5 tasks (CLI, all hls-skills installed)

| task_id | baseline | with skill | outcome | cause |
|---------|----------|------------|---------|-------|
| acc-001 | fail | pass | **win** | |
| acc-002 | fail | pass | **win** | |
| acc-004 | fail | fail | tie-fail | `open-weight-models` (which has its own Geneformer reference) wins selection in 3 of 4 runs; in the fourth our skill is read and names Genesis Workbench as coming soon, but the answer skips the interim path |
| acc-005 | fail | fail | tie-fail | answer omits the non-admin library path; Pixels follow-up |

No regressions. acc-004 and acc-005 are follow-ups for the Genesis Workbench handoff and Pixels re-review, not funke.

### Change made during evaluation

- **Next step must be literal**: acc-006 answers that ended in a numbered procedure skipped the Next step section or wrote "run the cells above". SKILL.md now requires the Next step to repeat the first command in a code block. acc-006 went from 1/3 to 3/3; acc-007 stayed 3/3.

### Install and pitfalls verified on serverless (funke commit 4312987)

- `%pip install --no-build-isolation git+...` and Git folder + `sys.path` both work in serverless notebooks (environment 4; Git folder also environment 1). Plain `%pip install git+...` failed where the package index did not serve `setuptools` to the isolated build.
- The reference snippet ran unchanged on 88 sample files: 79 parsed, 9 FHS/BHS batch files returned NULL. The batch split turned a 3-message batch file into 3 parsed messages.
- `bundle deploy -t dev` created 10 resources and started nothing; one triggered `HL7 Ingestion` update parsed 6 ADT files. Deploy from Homebrew Python failed (PEP 668) and `warehouse_id` is required.

### Limitations (v0.6)

- Workspace runs: 1 run per task per arm. Both arms used one scratch schema, so the with-skill day-2 answer also saw a table the baseline run had created.
- The eval data sits in a schema named `funke_eval`, which appears in the prompts for both arms. Baseline answers never recommended funke, so the name did not leak the answer.
- The CLI sandbox could not read workspace credentials, so day-2 was only tested in the workspace.
- Tested as a workspace admin; the non-admin bundle path is inferred from the resources it creates.
