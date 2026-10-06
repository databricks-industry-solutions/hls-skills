# Contributing
<!-- Do not change this header which generates contribution.md -->
## Add or update a skill

1. Follow authoring guidance on [AGENTS.md](AGENTS.md).
2. Depending on whether it's a pipeline or a guidance skill, start with the appropriate template in `templates/`.
3. Put the skill at `skills/<skill-name>/SKILL.md`.
4. Folder name must match frontmatter `name`. Check format with `test_skill_quality.py`
5. Update the skill table in `README.md`.
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
<!-- Do not change this header which generates evaluation.md -->

A skill should make the agent measurably better at its task. Each skill is benchmarked on 3-5 tasks by running Genie Code twice per task, once with the skill and once without, and scoring both runs the same way.

The [skill-eval](skills/skill-eval/SKILL.md) skill builds the harness for this. Scores are logged to an MLflow experiment, and a paired comparison report `eval_report.md` is written to the skill's `eval/` folder. The [skill catalog](https://databricks-industry-solutions.github.io/hls-skills/guide/skills/) shows which skills have a report.

##### Run an evaluation

1. Ask Genie Code to use the skill-eval skill to generate an evaluation harness for your skill.
2. Have Genie Code generate a notebook for each task, once with your skill and once without it.
3. Use the skill-eval harness to score both notebooks. This logs the scores to MLflow and writes `eval_report.md`.

##### What the `eval/` folder holds

```text
skills/<skill-name>/eval/
├── README.md               # run protocol, scorer summary, ship gate
├── evalset.json            # 3-5 benchmark task definitions (task_id, dataset, query)
├── expectations.json       # difficulty, expectations, deterministic checks per task
├── generate_data.py        # synthetic data generator (seeds the volume)
├── scorers.py              # deterministic + LLM judge definitions
├── score_<skill>.py        # generated scoring notebook: evaluate, compare, report
├── eval_report.md          # after running: paired comparison + failure taxonomy
├── baseline_scores.json    # after running: skill-off per-task scores
└── with_skill_scores.json  # after running: skill-on per-task scores
```

> [!WARNING]
> **The `eval/` folder holds the answer key.** `expectations.json` contains the expected results, so `eval/` is excluded from the bundle that is synced to Unity Catalog. Do not copy it into a skill's `references/`.

## Docs site

Most of the [docs site](https://databricks-industry-solutions.github.io/hls-skills/) is generated from `SKILL.md` files, `README.md`, and this file. Edit those, not the pages in `docs/`.

> [!WARNING]
> Some headings in `README.md` and this file are copied to the site by name. Read [DOCS.md](DOCS.md) before renaming or re-leveling a heading, and for how to preview and publish the site.


### Contributor License Agreement (CLA)
<!-- Do not change this header which is excluded from contribution.md -->

Thanks for contributing to HLS Skills.

By submitting a contribution to this repository, you certify that:

1. **You have the right to submit the contribution.**  
   You created the content yourself, or you have the right to submit it under the project's license.

2. **You grant us a license to use your contribution.**  
   Your contribution will be licensed under the same terms as the rest of this project, and you grant the project maintainers the right to use, modify, and distribute it as part of the project.

3. **You are not submitting confidential or proprietary information.**  
   Your contribution does not include anything you don’t have permission to share publicly.

If you are contributing on behalf of an organization, you confirm that you have the authority to do so. You agree to confirm these terms in your pull request. Any request that does not explicitly accept the terms will be assumed to have accepted.
