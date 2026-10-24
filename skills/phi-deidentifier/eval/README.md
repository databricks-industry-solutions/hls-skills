# phi-deidentifier Skill Evaluation

## Overview

Benchmark evaluation for the `phi-deidentifier` skill following the
[skill-eval](../../skill-eval/SKILL.md) methodology. Tests whether the skill helps Genie Code
produce a **safe, governed, analytically-useful** de-identification — across structured tables
and unstructured clinical documents — instead of a name-stripped copy that still leaks or
destroys utility.

## Benchmark Tasks

| task_id | path | difficulty | task | dataset | discriminator |
|---------|------|-----------|------|---------|---------------|
| phi-struct-01 | structured | core | De-identify a patient table for analytics sharing (redact direct IDs, tokenize id, k-anon target 5) | `deid_live_test.patients_raw` (250) | Governed VIEW (not a physical copy) + 0 leaks + measured k ≥ target, with utility retained |
| phi-doc-01 | document | hard | De-identify an EHR PDF; redact member + relatives, keep providers + clinical content | `patient_whitfield_margaret_ehr.pdf` | Member/relative names + sub-state geo + IDs redacted; provider names and clinical tokens kept; deterministic residual verdict |

Both are discriminators against a no-skill baseline: the naive approach writes a **physical copy**
and leaves raw PHI exposed (governance 0), skips k-anonymity, and on documents either over-redacts
clinical content or improvises an unreliable self-reported leak count.

## Data

Synthetic, with injected PHI so ground truth is exact:
- **Structured**: `testing_playground_catalog.deid_live_test.patients_raw` — 250 patients with
  name, SSN, email, phone, zip, admit/discharge dates, age_band, sex, hba1c.
- **Document**: a synthetic 15,772-char EHR (face sheet + clinical notes + imaging/discharge) with
  19 known member-PHI entities and a 10-item keep-set (providers + clinical tokens).

## Scoring

`eval/objective.py` (`deid_objective`): hard leak gate, then
`0.45·F2(recall,precision) + 0.20·utility + 0.15·min(k/5,1) + 0.20·governance`. Components in
`eval/scorers.py`. Structured runs are scored from the governed view with
`eval/score_phi_struct.py`; the leak scan runs against the actual raw input, so a "zero leaks"
claim is verified, not trusted.

## Results

See [eval_report.md](eval_report.md). Headline: structured path 0 leaks / recall 1.000 / k=33 /
governance 1.00 / objective **0.9125**, byte-identical across 5 sessions; document path F1 **0.929**
(recall 1.000 after the shared-surname fix) with a deterministic residual verdict.
