# Evaluation Report — Bulk RNA-seq + Pathway Enrichment Skills

**Setup**: Four GSE164471-derived benchmark tasks were executed by a linear
baseline notebook and a linear skill-guided notebook on `hls-fevm` serverless.
Each notebook ran all four tasks sequentially. MLflow scoring evaluated each
task's notebook source together with its runtime response and artifact manifest.
Scorers: required artifacts, required actions, notebook source validity,
expectation guidelines, and the binary scientific-method judge.

## Results

| task_id | difficulty | baseline | with skills | outcome |
|---------|------------|----------|-------------|---------|
| hls-rnaseq-001 | easy | fail | fail | tie-fail |
| hls-rnaseq-002 | hard | fail | fail | tie-fail |
| hls-rnaseq-003 | edge | fail | pass | **win** |
| hls-rnaseq-004 | hard | fail | pass | **win** |

Win rate: **2/4 (50%)**. Task-level regressions: **0/4**.

The skill-guided notebook passed artifact, required-action, scientific-method,
and notebook-source checks on all four tasks. The baseline passed only notebook
source validity consistently. Task 002 contains one metric-level guideline
regression even though it remains a task-level tie-fail.

## Failure taxonomy

| failure mode | count | arm | status |
|--------------|-------|-----|--------|
| guideline-evidence-omission | 2 tasks | with skills | Open — tasks 001 and 002 did not provide enough explicit evidence for every guideline judge requirement |
| inappropriate-DE-method | 4 tasks | baseline | Eliminated — baseline used Welch tests on log CPM; candidate used PyDESeq2 |
| cutoff-biased-enrichment | 4 tasks | baseline | Eliminated — baseline used pooled thresholded ORA; candidate used full-rank GSEA Prerank |
| missing-required-artifacts | 4 tasks | baseline | Eliminated — candidate produced all required DE, QC, and enrichment artifacts |
| guideline-metric-regression | 1 task | with skills | Review — task 002 flipped `expectations_guidelines` from pass to fail despite gains on the other method and artifact metrics |

## Verdict

**Ship with follow-up.** The default gate passes because the skill-guided arm
has two wins and zero task-level regressions. Before treating the benchmark as
fully clean, review the guideline-judge rationales for tasks 001 and 002 and
either improve the notebook's explicit evidence or narrow the guidelines to
claims observable from notebook source and outputs.

## Limitations

Four tasks provide directional evidence, not statistical significance. All
tasks use one GEO cohort and one Hallmark gene-set library. The comparison uses
explicitly authored baseline and skill-guided notebooks rather than independent
fresh agent generations, so it evaluates these notebook implementations rather
than isolating the causal effect of skill installation. Binary judge metrics
have not been calibrated against human labels.

## Reproduce

- Eval harness: `skills/bulk-rnaseq/eval`
- Data: `/Volumes/hls_amer_catalog/vital_skills/eval`
- Comparison:

```bash
python skills/skill-eval/scripts/compare_runs.py \
  skills/bulk-rnaseq/eval/baseline_scores.json \
  skills/bulk-rnaseq/eval/with_skill_scores.json \
  --difficulty skills/bulk-rnaseq/eval/expectations.json \
  --format text
```
