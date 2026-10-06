# Changelog — Vital Skills landing page

All notable changes to the `docs/` landing page (the Vital Skills GitHub Pages
site) are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] — 2026-10-06

Adds a documentation section under `/guide/`, built with MkDocs Material, and
moves deployment to GitHub Actions.

### Added
- `/guide/`: overview, getting started, evaluation, and contributing pages.
- Skill catalog and one page per skill, generated at build time from
  `skills/*/SKILL.md` frontmatter and content (`docs/hooks/skill_pages.py`), with
  an evaluation column linking each skill's `eval/` evidence.
- Databricks logo and Navy/Lava/Oat palette in the guide, matching this page,
  with a light/dark toggle.
- "Docs" link in the landing page top bar.
- `.github/workflows/pages.yml`: `mkdocs build --strict` on PRs, deploy on
  pushes to `dev`.

### Changed
- Go-live: set Settings → Pages → Source to **GitHub Actions** instead of
  flipping the publishing folder to `/docs`. The landing page is copied into the
  build unchanged.

## [0.0.1] — 2026-10-06

Initial landing page — a Databricks-branded static site for the Vital Skills
catalog of Genie Code skills, served from `docs/` on GitHub Pages. Additive
only; no changes to `skills/`.

### Added
- `index.html` — self-contained static landing page:
  - Hero wordmark with a self-drawing signal-line animation (heartbeat, a
    two-tone DNA double helix, and a molecule/waveform motif) plus an overview
    video. Honors `prefers-reduced-motion` with a static final state.
  - Filterable catalog of Genie Code skill cards, each linking to the skill
    folder and its `SKILL.md` on GitHub.
  - Minimal top bar: logo (to the `skills/` folder on GitHub), a GitHub repo
    link, and a sun/moon dark-mode toggle.
  - Footer with a back-to-top logo and a Contribute link.
- `.nojekyll` — serve the static files as-is (no Jekyll processing).
- `vitalskills.mp4` — hero overview video.

### Design
- Databricks brand palette (Lava, Navy, Oat) and DM Sans / DM Mono typography.
- Terminology is "Genie Code skills" throughout.
- WCAG-AA color contrast for text, plus a 3:1 minimum for interactive and
  graphical elements (chip outlines, topic accents). External links open in a
  new tab with an accessibility cue.
- Dark/light theme persists across reloads (stored in `localStorage`), with a
  single source of truth — `data-theme` on `<html>`, applied before first paint
  — driving both the CSS and the toggle script. Falls back to the
  operating-system preference on first visit and follows live OS changes until
  the visitor makes an explicit choice.

### Notes
- Go-live is a maintainer action: in Settings → Pages, flip the publishing
  folder from `/ (root)` to `/docs`. Reversible and non-disruptive. `baseurl`
  is `/hls-skills`.
- JavaScript is required: the skill cards are rendered client-side, and without
  JavaScript the page renders in light mode (the single-source-of-truth theme is
  set by script). This is acceptable because the catalog itself needs JavaScript.
