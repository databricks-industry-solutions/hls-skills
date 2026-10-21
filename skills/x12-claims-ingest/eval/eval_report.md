# Evaluation Report: x12-claims-ingest Skill

**Setup**: 6 benchmark tasks (1 easy, 3 hard, 2 edge) on synthetic X12 837 files with exact answer keys,
run with and without the skill in Genie Code CLI (`genie exec`, model `databricks-gpt-5-6-sol`) on
fe-vm-hls-amer, 2026-10-19 to 2026-10-20. 3 replicates per (task, arm), 36 runs. Each run started in a fresh
folder with an isolated Genie home (no personal skills, memories or AGENTS.md); the skill arm got the
published bundle only (no `eval/`, `tests/`). Scored from the tables each run wrote, with MLflow 3
(`mlflow.genai.evaluate`): `no_silent_bad_load`, `claims_complete`, `claim_fields_correct`, `lines_correct`,
`bad_files_reported`, `ran_as_asked`, `quality_issues_found` (deterministic) and `data_quality_disclosure`
(LLM judge, `databricks:/databricks-gpt-5-mini`). Composite objective `ingest_objective_v2`
(`tests/objective.py`). Tasks x12-005 / x12-006, objective v2 and the quality scorer were committed before
any arm ran on them.

## Results

Per-replicate outcome under the pre-registered rule (all metrics pass, judge included):

| task_id | difficulty | r11 | r12 | r13 | baseline pass | with skill pass |
|---------|------------|-----|-----|-----|---------------|-----------------|
| x12-001 load clean 837P | easy | regression (judge) | tie-pass | win (judge) | 2/3 | 2/3 |
| x12-002 837P + 837I, delimiters, COB + patient loops | hard | tie-pass | tie-pass | tie-pass | 3/3 | 3/3 |
| x12-003 truncated + non-X12 file | edge | tie-fail | tie-pass | **win** | 1/3 | **2/3** |
| x12-004 serverless Lakeflow pipeline | hard | tie-pass | regression (judge) | tie-pass | 3/3 | 2/3 |
| x12-005 4010 + 5010, corrections and voids, line context | hard | tie-pass | win (judge) | tie-pass | 2/3 | 3/3 |
| x12-006 18 planted data-quality defects | edge | tie-pass | regression (judge) | tie-fail (judge) | 2/3 | 1/3 |

Majority over 3 replicates (`baseline_scores.json` / `with_skill_scores.json`, a metric passes if it passed
in at least 2 runs): win rate 1/6, regressions 1/6 (x12-006, from judge false negatives).
**Ship gate FAIL** under the pre-registered rule.

Deterministic metrics only (judge excluded; post hoc, see failure mode 3):

| task_id | baseline pass | with skill pass | majority outcome |
|---------|---------------|-----------------|------------------|
| x12-001 | 3/3 | 3/3 | tie-pass |
| x12-002 | 3/3 | 3/3 | tie-pass |
| x12-003 | 1/3 | 2/3 | **win** |
| x12-004 | 3/3 | 3/3 | tie-pass |
| x12-005 | 3/3 | 3/3 | tie-pass |
| x12-006 | 3/3 | 3/3 | tie-pass |

Win rate 1/6, regressions 0/6 (gate would pass). Objective v2 mean per replicate: baseline 0.833 / 1.000 /
0.833, with skill 0.833 / 1.000 / 1.000.

Supporting evidence (not part of the gate), from the 36 transcripts and run records:

| | baseline | with skill |
|---|---|---|
| parsing approach | 15/18 runs read files into driver-side Python and built DataFrames with `createDataFrame`; 3/18 (the pipeline task) used a Python UDF | 18/18 used the skill's distributed PySpark parser |
| hand-written code per run (median) | ~400 lines | ~140 lines (0 when it called the module only) |
| output tokens (median) | 15.1K | 10.6K (about 30% fewer) |
| wall time (median) | 305 s | 397 s (slower: more reading, serverless job submission) |

Round 1 (2026-10-19, earlier skill version, x12-001..004 only, 1 replicate, judge v2): 4/4 tie-pass;
median output tokens 14.9K vs 8.0K, wall time 280 s vs 224 s. Scores in `scores/r1/`.

## Failure taxonomy (from error analysis of every non-pass)

| failure mode | count | arm | status |
|--------------|-------|-----|--------|
| 1. Silent partial load: claims from the truncated file loaded as valid (r13 also dropped 2 valid claims) | 2/3 x12-003 runs | baseline | eliminated by skill (0/3) |
| 2. Over-quarantine: skill followed SKILL.md "quarantine errors", found NPI check-digit and 5-digit ZIP errors on every claim and loaded 0 claims | 1/3 x12-003 runs (r11); related judge fail x12-001 r11 | with skill | open: fix now (see below) |
| 3. Judge false negatives: rationale confirms the response matches the tables, then fails it (counts files, "names files as ok", treats claim-level findings as file problems) | 3 runs | baseline | open: judge not validated; deterministic view reported |
| 3. (same) | 3 runs | with skill | open (as above) |
| 4. Run lost to model-endpoint token expiry (`403 Invalid Token`) mid-run | 3 runs | baseline | infrastructure; discarded and rerun under the same rule for both arms |

Notes:

- **Failure mode 2 is a data and guidance defect, not a parser defect.** Data for x12-001..004 was generated
  before the generator produced Luhn-valid NPIs and 9-digit billing ZIPs, so its "clean" claims really do
  fail the CMS rules the skill now checks. Fix: regenerate x12-001..004 data, and change SKILL.md Step 6 to
  flag by default and quarantine only when the user asks.
- **Mapping and quality knowledge did not separate the arms.** On x12-005 and x12-006 the baseline produced
  correct tables 3/3; its own code implemented the NPI Luhn/80840 check, the 9-digit ZIP and PO Box rules
  and replacement/void handling unaided. The skill matched it (3/3) without a regression.
- **No leakage found.** Transcripts were scanned for reads of answer keys, other arms' tables or the skill
  bundle in the baseline arm; none.

## Verdict

**fix-and-rerun**: the pre-registered gate (`win_rate > 0` and zero regressions, all metrics) fails because
of judge false negatives; on deterministic metrics the skill wins x12-003 (no silent partial loads) with no
regressions, uses about 30% fewer tokens, and is the only arm whose code scales (distributed parser in 18/18
runs vs driver-side Python or UDFs in 18/18 baseline runs). Before the next round: fix failure mode 2,
replace or validate the judge, and add a pre-registered high-volume task so scalability is scored as
correctness.

## Limitations

6 tasks x 3 replicates = directional evidence, not statistical. All data is synthetic (generator in
`scripts/generate_837.py`); x12-001..004 data predates the generator's NPI/ZIP fix. One generator model
(`databricks-gpt-5-6-sol`) and one judge model; the judge was rewritten once during round 1 (v1 failed every
run on harmless exit codes) and is not validated against human labels. Wall time includes serverless
start-up and is noisy. Three baseline runs were rerun after infrastructure failures. The deterministic-only
view is a post hoc reading; the pre-registered rule is the all-metrics one.

## Reproduce

Evalset `eval/evalset.json` + `eval/expectations.json`; data via `eval/generate_data.py`; arms via
`eval/run_genie_arms.py --first-rep 11 --reps 3`; scoring via `eval/score_x12_claims_ingest.py` (one run per
replicate, widgets `runs_dir`, `baseline_prefix`, `with_skill_prefix`); runs `baseline_r11..r13` and
`with_skill_r11..r13` in MLflow experiment `/Users/raven.mukherjee@databricks.com/skill-eval-x12-claims-ingest`;
comparison via `skills/skill-eval/scripts/compare_runs.py` on `scores/r1X/` (per replicate) or
`baseline_scores.json` / `with_skill_scores.json` (majority).
