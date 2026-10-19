# x12-claims-ingest Skill Evaluation

Benchmark for `x12-claims-ingest` following the [skill-eval](../../skill-eval/SKILL.md) method: the
same 4 tasks run in Genie Code with the skill OFF and ON, scored in one MLflow experiment, compared
per task with `skill-eval/scripts/compare_runs.py`, plus a composite objective (`../tests/objective.py`).

## Benchmark tasks

| task_id | difficulty | task | discriminator |
|---|---|---|---|
| x12-001 | easy | Load clean 837P files (14 claims) | control: a base model may pass |
| x12-002 | hard | 837P + 837I, three delimiter styles, multi-transaction file, patient and COB loops (27 claims), billed by payer | hard-coded delimiters, other-payer leak into payer_id, patient DOB carried across subscribers |
| x12-003 | edge | Truncated transfer + a non-X12 file named `.x12` among good files (13 valid claims) | partial claims loaded as valid; bad files not reported |
| x12-004 | hard | Serverless Lakeflow pipeline, run once (14 claims) | UDF / RDD / non-PySpark parsers, windows inside streaming tables |

Prompts (`evalset.json`) name the output tables and columns, so both arms are graded on the same
contract. `<PREFIX>` is the only per-arm substitution (`b_<task>_` baseline, `s_<task>_` with skill).

## Data

`generate_data.py` writes each task's files to `$SKILL_EVAL_DATA_DIR/<task_id>/` (default
`/Volumes/hls_amer_catalog/x12_claims_ingest_test/eval/x12-claims-ingest/`) and the answer keys to
`$SKILL_EVAL_GRADER_DIR` (default `/Volumes/hls_amer_catalog/x12_claims_ingest_test/grader/x12-claims-ingest/`),
a separate Volume the arms are never pointed at. Counts are pinned; generation fails if they drift.
All identifiers are synthetic.

## Scoring

| scorer | level | checks |
|---|---|---|
| no_silent_bad_load | L1 | no claim from a truncated/invalid transaction sits unflagged in the claims table (objective gate) |
| claims_complete | L1 | claim-set F1 >= 0.99 against the key |
| claim_fields_correct | L1 | member, payer, billing NPI, billed amount, principal dx, patient DOB/gender >= 0.99 |
| lines_correct | L1 | procedure/revenue code, charge, units, service date >= 0.99 |
| bad_files_reported | L1 | every bad file appears in file_checks with a non-ok status |
| ran_as_asked | L1 | x12-004: a serverless pipeline with the requested name completed |
| data_quality_disclosure | L2 judge | response states the load count and names skipped files honestly |

Composite objective, logged per task as `ingest_score_<task>` and `ingest_score_mean` on each run:
gate (silent bad load -> 0), else `0.30 claim F1 + 0.30 field accuracy + 0.15 line accuracy +
0.15 validation reporting + 0.10 ran where asked`. Weights are pinned (v1).

Judge model `databricks:/databricks-gpt-5-mini` (must differ from Genie Code's model). Pass rule
`all_metrics`. Ship gate: win rate > 0 and zero regressions.

## Run protocol

1. Seed data: run `generate_data.py` on Databricks (writes to the Volumes above).
2. Baseline arm (skill OFF): a fresh Genie Code session per task that has never read this skill.
   No `x12-claims-ingest` under `.assistant/skills/` (or the CLI's skills folder), personal skills and
   memories off. Paste each `evalset.json` query verbatim with `<PREFIX>` = `b_<task>_`. Save the final
   response and the ordered steps to `_runs/baseline/<task_id>.json` (`{"response", "action_log"}`).
3. With-skill arm: install the skill WITHOUT `eval/` and `tests/`, fresh session per task, same queries
   with `<PREFIX>` = `s_<task>_`; save to `_runs/with_skill/<task_id>.json`.
4. Score: run `score_x12_claims_ingest.py` (experiment `/Users/<you>/skill-eval-x12-claims-ingest`).
5. Error-analyze every tie-fail and regression, then write `eval_report.md`
   (`skill-eval/references/report-template.md`).

Repeat each (task, arm) 3 times if time allows: agent runs are not deterministic.
