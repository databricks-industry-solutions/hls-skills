# Contributing

## Report a bug or request a skill

[Open an issue](https://github.com/databricks-industry-solutions/hls-skills/issues/new/choose) and pick a form:

- **Bug report.** A skill gives wrong guidance, its code fails, or repo tooling breaks.
- **Skill request.** Propose a new skill or a major change. Open one before starting the work so others can weigh in.

!!! danger "This repository is public"
    Do not include PHI, patient-level rows, credentials, or confidential customer details in issues or pull requests. Report security issues as described in [SECURITY.md](https://github.com/databricks-industry-solutions/hls-skills/blob/dev/SECURITY.md).

## Add or update a skill

1. Read the [authoring guide](https://github.com/databricks-industry-solutions/hls-skills/blob/dev/AGENTS.md) and start from the matching file in [`templates/`](https://github.com/databricks-industry-solutions/hls-skills/tree/dev/templates).
2. Put the skill at `skills/<skill-name>/SKILL.md`. The folder name must match the frontmatter `name`.
3. Add unit tests in `skills/<skill-name>/tests/` and benchmark it as described in [Evaluation](evaluation.md).
4. Update the skill table in `README.md`. This site's [skill catalog](skills/index.md) updates itself from the frontmatter.
5. Open a pull request against `dev` and ask for a review.

## Run the checks locally

```bash
# Format check for every skill, plus the sync bundle filter
uv run --isolated --with pytest python -m pytest -q tests

# One skill's unit tests
uv run --isolated --with pytest --with-requirements skills/<name>/tests/requirements.txt \
    python -m pytest -q skills/<name>/tests
```

CI runs the same checks on every pull request and also scans the full Git history for secrets.

## Preview this site

```bash
uv run --isolated --with-requirements docs/requirements.txt mkdocs serve
```

The skill pages are generated from each `SKILL.md`, so edit the skill, not the site. Full details are in [CONTRIBUTING.md](https://github.com/databricks-industry-solutions/hls-skills/blob/dev/CONTRIBUTING.md).

## Publish this site

The site is published by a maintainer, not by CI, because the GitHub organization's IP allow list blocks Pages deployments from GitHub-hosted runners. After docs or skill changes merge, run this from an up-to-date `dev` checkout on an allowed network:

```bash
uv run --isolated --with-requirements docs/requirements.txt \
    mkdocs gh-deploy --strict --no-history -m "Deploy docs from dev @ $(git rev-parse --short HEAD)"
```

This builds the site and pushes it to the `gh-pages` branch, which GitHub Pages serves.
