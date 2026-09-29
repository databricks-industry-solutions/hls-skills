## Summary

<!-- What changed and why, in 1-3 bullets. -->

## Test plan

<!-- Commands run and what they showed. For a skill: test_skill_quality.py output, skill tests, and any Genie Code runs. -->

## Type of change

- [ ] New skill
- [ ] Skill update
- [ ] skill-eval / evaluation evidence
- [ ] Repo tooling / CI
- [ ] Docs

## Skill checklist

<!-- Delete this section if the PR does not add or change a skill. -->

- [ ] `python tests/test_skill_quality.py skills/<name>/SKILL.md` passes
- [ ] Folder name matches frontmatter `name`; `author`, `version`, `license` set
- [ ] Unit tests in `skills/<name>/tests/` (test-only deps in `tests/requirements.txt`)
- [ ] Benchmark evidence in `skills/<name>/eval/` (see `skills/skill-eval`), or a note on why not yet
- [ ] `README.md` skill table updated

## Contribution terms

- [ ] I accept the contribution terms in [CONTRIBUTING.md](https://github.com/databricks-industry-solutions/hls-skills/blob/main/CONTRIBUTING.md) (right to submit, license grant, no confidential information).
