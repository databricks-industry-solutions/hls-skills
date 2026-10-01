# HLS OSS-Models Skill Screening Tests

Paired A/B evaluation of the `oss-models` custom skill for deploying open-source
health & life-sciences models on Databricks.

## What This Tests

Does the custom `oss-models` skill (SKILL.md + model references) produce **better
notebook code** than Genie Code's built-in knowledge alone? Each task is run
twice — once with the skill active ("skill arm"), once without ("baseline arm")
— and scored on 8 phases / 25+ sub-checks.

## Directory Layout

```
<project-folder>/
├── README.md                              # This file
├── evalset.json                           # Task catalog (v3.0.0, 9 tasks)
├── scorers.py                             # 8-phase scorer (21 sub-checks)
├── compare_runs.py                        # Paired comparison + ship gate
├── 00_oss_models_test_plan                # High-level test plan
├── 01_skill_structure_tests               # Skill file validation
├── 03_eval_rubric_and_compare             # <<< Main eval notebook
│
├── oss-001_TEDDY-70M_Deploy_Baseline      # Notebook pair: oss-001
├── oss-001_TEDDY-70M_Deploy_withSkills
├── oss-002_TEDDY-70M+VS_Deploy_Baseline   # Notebook pair: oss-002
├── oss-002_TEDDY-70M+VS_Deploy_withSkills
│
├── .assistant/skills/oss-models/          # The custom skill under test
│   ├── SKILL.md  (or .off when disabled)  #   Toggle: rename to disable
│   └── references/models/                 #   Model-specific references
│       ├── teddy.md
│       ├── geneformer.md
│       ├── scimilarity.md
│       └── ...
│
└── results/                               # All persisted outputs
    ├── manifest.json                      #   Run index (accumulates)
    ├── baseline_scores.json               #   {task_id: {metric: bool}}
    ├── skill_scores.json
    ├── baseline/                           #   Exported notebook sources
    │   ├── oss-001.txt
    │   └── oss-002.txt
    ├── with_skill/
    │   ├── oss-001.txt
    │   └── oss-002.txt
    └── reports/                            #   Per-task markdown reports
        ├── oss-001_report.md
        └── oss-002_report.md
```

## Workflow

### 1. Prepare the notebook pair

Each task needs two notebooks: `{prefix}_Baseline` and `{prefix}_withSkills`.
Cell 1 has the prompt for both arms. Cell 2 checks whether the skill is
active or disabled.

### 2. Run the baseline arm

1. Rename `SKILL.md` → `SKILL.md.off`
2. Open the **Baseline** notebook in a **fresh** Genie Code chat
3. Paste the baseline prompt from Cell 1
4. Let Genie Code write the full notebook
5. The prompt's final step exports the source automatically

### 3. Run the skill arm

1. Rename `SKILL.md.off` → `SKILL.md`
2. Open the **withSkills** notebook in a **fresh** Genie Code chat
3. Paste the skill prompt from Cell 1
4. Let Genie Code write the full notebook
5. The prompt's final step exports the source automatically

### 4. Score and compare

Open `03_eval_rubric_and_compare` and run all cells:

| Cell | What it does |
|---|---|
| 3 | Skills inventory (shows active/disabled state) |
| 4 | Discover notebook pairs + create widgets |
| 5 | Export both arms as `.py` source text |
| 6 | Score both arms (8 phases) + save accumulated scores |
| 7 | Ship gate comparison (win/regression/tie) |
| 8 | Detailed sub-check breakdown table |
| 9 | Fixable analysis (which failures are covered in skill?) |
| 10 | Scorer refinement analysis |
| 11 | **Save** per-task report + manifest + cross-task summary |

### 5. Review persisted artifacts

- **`results/reports/{task_id}_report.md`** — full detail for that task
  (survives when you re-run with a different task)
- **`results/manifest.json`** — structured index of all runs with
  phase/category scores and ship-gate verdict
- **Score JSONs** — accumulate across tasks; input to `compare_runs.py`
  for cross-task ship gate

## What Gets Saved (and Why Nothing Is Lost)

| Artifact | Path | Lifecycle |
|---|---|---|
| Notebook source | `results/{arm}/{task_id}.txt` | Per-task, overwritten only by same task |
| Score JSONs | `results/*_scores.json` | Accumulate across tasks (read→merge→write) |
| Per-task report | `results/reports/{task_id}_report.md` | One per task, replaced on re-run of same task |
| Manifest | `results/manifest.json` | Append-only (dedup by task_id + pair_prefix) |

Running oss-002 does **not** overwrite oss-001's scores, report, or source.
Re-running oss-001 replaces its own entry with updated scores.

## Scoring Architecture

```
evalset.json (9 tasks)
    │
    ▼
scorers.py (8 phases, 21+ sub-checks)
    │
    ├── Phase 1: download_staging      (uses_tmp, hf_xet, deps_pinned)
    ├── Phase 2: pyfunc_quality        (class, imports, sys.modules, io.StringIO)
    ├── Phase 3: model_registration    (signature, input_example, pip_reqs)
    ├── Phase 4: endpoint_deployment   (SDK enums, AI Gateway, scale_to_zero)
    ├── Phase 5: smoke_tests           (registration, endpoint, output shape)
    ├── Phase 6: ai_search             [vs=true only] (index, dim, graceful_skip)
    ├── Phase 7: edge_handling         [edge only] (template, unknowns)
    └── Phase 8: forbidden_patterns    (anti-pattern safety net)
    │
    ▼
compare_runs.py
    │
    ├── Per-task: win / regression / tie-pass / tie-fail
    ├── Aggregate: win_rate, regression_rate
    └── Ship gate: PASS if >=1 win AND 0 regressions
```

## Task Matrix (evalset v3.0.0)

| Task | Family | Variant | VS | Difficulty | Key test |
|---|---|---|---|---|---|
| oss-001 | teddy | 70M | no | hard | Deploy only (baseline) |
| oss-002 | teddy | 70M | yes | hard | Deploy + AI Search (Census corpus) |
| oss-003 | teddy | 400M | yes | hard | Deploy + AI Search (GWB fallback) |
| oss-004 | scimilarity | - | no | hard | Deploy (Zenodo weights) |
| oss-005 | geneformer | - | no | hard | Deploy Path A (HF, V1-10M) |
| oss-006 | geneformer | - | no | hard | Deploy Path B (NVIDIA BioNeMo) |
| oss-007 | midnight | - | no | hard | Deploy (pathology tile-embedding) |
| oss-008 | generic | - | no | edge | Unknown model → model-template.md |
| oss-009 | generic | - | no | compute | CPU-only, no GPU |

## Adding a New Task

1. Add the task to `evalset.json` with `task_id`, `model_family`, `query`,
   `expectations`, `deterministic_checks`
2. If the model family is new, add a reference file to
   `.assistant/skills/oss-models/references/models/`
3. If needed, add family-specific sub-checks to `scorers.py`
   (gate on `task.model_family`)
4. Create the notebook pair:
   `{task_id}_{name}_Baseline` + `{task_id}_{name}_withSkills`
5. Run cells 3-4 in the eval notebook to discover the new pair

## Key Design Decisions

- **Skill toggle = file rename, not folder rename.** Renaming `SKILL.md` →
  `SKILL.md.off` is reliable; renaming the folder is not (the assistant's
  glob may still match).
- **Built-in skills are always active.** The baseline arm still has access
  to `machine-learning`, `databricks-model-serving`, `vector-search`, etc.
  The eval measures the *marginal* value of the custom skill.
- **Scores accumulate.** Running oss-002 does not overwrite oss-001 scores.
  The manifest deduplicates by `(task_id, pair_prefix)` — re-running the
  same task replaces the old entry.
- **Per-task reports survive.** Each task gets its own markdown report with
  the full sub-check breakdown, so switching tasks in the notebook doesn't
  lose detail.
- **Prompts are NOT identical across arms.** The skill arm prompt explicitly
  instructs Genie Code to read `SKILL.md` + `teddy.md`. The baseline prompt
  has no such instruction. This is intentional: the eval measures whether
  the skill *content* teaches Genie Code things it wouldn't otherwise know.
