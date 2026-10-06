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
