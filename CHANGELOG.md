# Changelog

All notable changes to Vital Skills are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] — Unreleased

First public release: Health & Life Sciences **Genie Code** skills, a generated
catalog, and a docs site. Clone the repo into Databricks, point Genie Code at
`skills/`, optionally sync to Unity Gateway.

### Added

**Skills** (Agent Skills `SKILL.md` bundles: references, scripts, tests, eval)

- Bioinformatics: `bulk-rnaseq`, `open-weight-models`, `pathway-enrichment-analysis`, `sc-rnaseq`
- Clinical: `cohort-builder`, `phi-deidentifier`, `rwe-cohortstudy`, `semantic-builder`
- Others: `accelerators`, `presentation-builder`, `scientific-figures`, `skill-eval`

**Catalog and site**

- README and landing-page tables generated from each skill’s `category` and `summary` (`docs/hooks/skill_catalog.py`)
- GitHub Pages landing page plus MkDocs Material guide under `/guide/` (one page per skill)
- Categories: Bioinformatics, Clinical, Others
- Dark/light theme (persists in `localStorage`; follows the OS until the visitor chooses)

**Authoring and CI**

- Pipeline and guide templates; `AGENTS.md` authoring rules
- `sync_skills_git2unity.py` to register skills on Unity Gateway
- `skill-eval` paired with/without-skill benchmarking (MLflow); BiomniBench-DA harness
- PR checks: skill quality, per-skill tests, catalog `--check`, docs `--strict` build, gitleaks

### Changed

Names that existed before this tag, now canonical in 1.0:

- `oss-models` → `open-weight-models`
- `payer-provider-measure-catalog` → `semantic-builder`
- `Clinical RWE` and `Payer and provider` → one **Clinical** category

`sync_skills_git2unity.py` never deletes skills. If you synced before 1.0, drop the
old `oss-models` and `payer-provider-measure-catalog` skills from your Unity Catalog
schema by hand.

### Notes

- Site publish is `mkdocs gh-deploy` to `gh-pages` (GitHub-hosted runners cannot deploy Pages on this org). PRs still run `mkdocs build --strict`.
- The landing-page catalog needs JavaScript.
- Compliance (HIPAA and similar) remains the user’s obligation; see the README disclaimer.
