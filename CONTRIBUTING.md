# Contributing

Thanks for contributing to HLS Skills.

### Contributor License Agreement (CLA)

By submitting a contribution to this repository, you certify that:

1. **You have the right to submit the contribution.**  
   You created the content yourself, or you have the right to submit it under the project's license.

2. **You grant us a license to use your contribution.**  
   Your contribution will be licensed under the same terms as the rest of this project, and you grant the project maintainers the right to use, modify, and distribute it as part of the project.

3. **You are not submitting confidential or proprietary information.**  
   Your contribution does not include anything you don’t have permission to share publicly.

If you are contributing on behalf of an organization, you confirm that you have the authority to do so. You agree to confirm these terms in your pull request. Any request that does not explicitly accept the terms will be assumed to have accepted.

## Adding or updating a skill

1. Follow [AGENTS.md](AGENTS.md).
2. Start from the matching file in `templates/`.
3. Put the skill at `skills/<skill-name>/SKILL.md`.
4. Folder name must match frontmatter `name`. Check format with `test_skill_quality.py`
5. Update the skill table in `README.md` (Table to be created).
6. Open a PR and request a second-party review.

## Test

Several levels of testing is advised.

#### 1. Repo-level tests: formatting
* ./tests/test_skill_quality.py tests skill's formatting
* ./tests/test_sync_bundle.py tests that unnecessary skill folders are not synced to Unity Catalog/Gateway

Both these tests can be invoked on all skills with 
```
uv run --isolated --with pytest python -m pytest -q tests
```

#### 2.Skill-level unit tests
Store your skill's unit tests here `./skills/<your_skill>/tests`
```
uv run --isolated --with pytest --with-requirements skills/<name>/tests/requirements.txt \
    python -m pytest -q skills/<name>/tests
```

#### Automated CI
Both overall formatting and unit tests can be automated with CI (`.github/workflows/ci.yml`) which runs on every non-draft PR.
- Put a skill's test-only dependencies in `skills/<name>/tests/requirements.txt`, pinned to versions you ran. CI finds every `skills/*/tests/` folder automatically.
- A skill's `eval/` or `tests/` folder is never published by `sync_skills_git2unity.py`; `tests/test_sync_bundle.py` fails if that filter is removed.
- CI also scans the full git history for secrets with gitleaks.

#### 3. Evaluate with and without skill
Call the [skill-eval](skills/skill-eval/SKILL.md) skill to generate an evaluation harness for your skill. It will generate:
```text
skills/<skill-name>/
├── SKILL.md               ← the skill itself (not modified during eval)
└── eval/
    ├── README.md            ← run protocol, scorer summary, ship gate
    ├── evalset.json         ← 3-5 benchmark task definitions (task_id, dataset, query only)
    ├── expectations.json    ← difficulty, expectations, deterministic_checks per task (keyed by task_id + dataset)
    ├── generate_data.py     ← synthetic data generator (seeds the volume)
    ├── scorers.py           ← deterministic + LLM judge definitions; exports the `scorers` list
    ├── score_<skill>.py  ← (generated) scoring notebook: evaluate + compare + report
    ├── eval_report.md       ← (after running) paired comparison report + failure taxonomy
    ├── baseline_scores.json ← (after running) skill-OFF per-task scores
    └── with_skill_scores.json ← (after running) skill-ON per-task scores
```

Call Genie Code to generate a notebook each with and without using your skill. Then use the skill-eval skill to reference the evaluation harness to score both notebooks. The scores will be logged to a MLflow experiment and an eval_report.md will be generated in the `eval` subfolder.
