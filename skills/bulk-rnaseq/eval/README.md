# Integrated RNA-seq Skill Evaluation

This harness evaluates `bulk-rnaseq` together with
`pathway-enrichment-analysis` on four tasks derived from GEO GSE164471.

## Protocol

1. Generate data with `generate_data.py` and upload it to
   `/Volumes/hls_amer_catalog/vital_skills/eval`.
2. Run every query from `evalset.json` in a fresh Genie Code chat with both
   skills disabled. Replace `<ARM>` with `baseline` and capture each final
   response, action log, and artifact filenames in `baseline_outputs.json`.
3. Enable both skills without either skill's `eval/` folder. Hard refresh, run
   the same queries verbatim in fresh chats, replace `<ARM>` with `with_skills`,
   and capture `with_skill_outputs.json`.
4. Run `score_bulk_rnaseq_and_pathways.py` in Databricks. It records both arms
   in one MLflow experiment and invokes the shared `compare_runs.py` gate.
5. Read every tie-fail or regression, create a failure taxonomy, and write
   `eval_report.md` without modifying either skill.

## Information isolation

The task-running agent may read only `evalset.json`. It must not read
`expectations.json`, `generate_data.py`, scorer code, prior outputs, or reports.
The installed candidate skills must exclude `eval/` so the answer key is never
available to either arm.

## Data generation

```bash
SKILL_EVAL_DATA_DIR=/tmp/hls-rnaseq-eval python3 eval/generate_data.py
databricks fs cp -r /tmp/hls-rnaseq-eval \
  dbfs:/Volumes/hls_amer_catalog/vital_skills/eval \
  --overwrite --profile hls-fevm
```

The generator downloads the public GSE164471 annotated raw counts and the
public `MSigDB_Hallmark_2020` Enrichr GMT. It writes clean, annotated,
samples-by-genes, and sample-mismatch variants. No expected answers or planted
effects are placed in the task directories.

## Gate

Ship only with at least one task-level win and zero regressions. Four tasks are
directional evidence, not statistical significance.
