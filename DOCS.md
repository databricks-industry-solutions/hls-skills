# Docs site

The [GitHub Pages site](https://databricks-industry-solutions.github.io/hls-skills/) is `docs/index.html` (the landing page) plus an MkDocs guide under `/guide/`. Most of the guide is not written in `docs/`. It is generated at build time from files elsewhere in this repository, so **edit the source file, not the page.**

## Where each page comes from

| Page | Source | Edit |
|------|--------|------|
| Landing page | `docs/index.html`; skill rows from each `skills/*/SKILL.md` (`category`, `summary`) | Layout and copy on the page; skill rows via frontmatter + `python docs/hooks/skill_catalog.py` |
| Skill catalog and one page per skill | Each `skills/*/SKILL.md` (frontmatter and body) | The skill's `SKILL.md` |
| README skill table | Same `category` / `summary` frontmatter | The skill's `SKILL.md`, then `python docs/hooks/skill_catalog.py` |
| Setup | The `## Setup` section of [README.md](README.md) | `README.md` |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md), without the CLA section; section 3 of Test becomes a link to Evaluation | `CONTRIBUTING.md` |
| Evaluation | The `#### 3. Evaluate with and without skill` section of [CONTRIBUTING.md](CONTRIBUTING.md) | `CONTRIBUTING.md` |
| FAQ | `docs/guide/faq.md` | The page itself |
| Links | `docs/guide/links.md` | The page itself |
| Changelog | `docs/CHANGELOG.md` | The page itself |

A page under `docs/guide/` that holds only a title and a line like `<!-- include: README.md#Setup -->` is a copy. Editing that page changes nothing you can see.

## Headings are load-bearing

> [!WARNING]
> **Do not rename, delete, or re-level a heading that a page copies from.** The copy finds its text by the heading's words, so a renamed heading breaks it.

These headings are copied today:

- `## Setup` in `README.md`
- `#### 3. Evaluate with and without skill` in `CONTRIBUTING.md`
- `### Contributor License Agreement (CLA)` in `CONTRIBUTING.md` (left out of the Contributing page)

To list every copy, run `rg "<!-- include:" docs/`.

If you must change one of these headings, change the matching `<!-- include: ... -->` line in `docs/guide/` in the same pull request. Rules that follow from how sections are found:

- **Wording.** Headings match without case, backticks, or link URLs, but every word must match.
- **Level.** A section runs until the next heading of the same or a higher level. A subsection must be deeper than its parent: under `#### 3. Evaluate ...`, use `#####`. A `##` there would end the section and drop everything after it.
- **Uniqueness.** Two headings with the same text in one file make the copy ambiguous.

The strict build fails if a file or heading is missing or ambiguous, and names the page and the heading. It catches a broken copy, but not a section that silently got shorter because a heading level changed. Preview the page.

## Write Markdown that works on GitHub and on the site

Copied text is shown in two places, so it has to render in both.

- **Links.** Relative links, such as `[AGENTS.md](AGENTS.md)`, point at GitHub on the site. To link a site page, use its full URL, such as `https://databricks-industry-solutions.github.io/hls-skills/guide/skills/`.
- **Notes and warnings.** Use GitHub alerts (`> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]`, `> [!CAUTION]`). The site turns them into boxed notes. MkDocs-only syntax such as `!!! note` shows as raw text on GitHub.
- **Comments.** `<!-- ... -->` is hidden in both places but stays in the published page source. Do not start one with `include:` in a page under `docs/`; that marks a copy.

## The include line

`docs/hooks/repo_sections.py` expands these lines when the site builds:

| Line | Copies |
|------|--------|
| `<!-- include: README.md#Setup -->` | The text under `Setup`, without the heading |
| `<!-- include: CONTRIBUTING.md -->` | The whole file, without its leading `# Title` |
| `... omit="Heading"` | Leaves out that heading and its text. Repeat for more |
| `... replace="Heading=Markdown"` | Keeps the heading, swaps its text for the Markdown. Links in it are relative to the page |
| `... level=3` | Shifts headings so the copy's top level is `###` (default `##`) |

## Preview, check, publish

- **Preview:** `uv run --isolated --with-requirements docs/requirements.txt mkdocs serve`. Edits to `docs/`, `README.md`, and `CONTRIBUTING.md` reload on save. After editing `docs/hooks/`, restart the server; it caches hook code.
- **Check:** `uv run --isolated --with pytest python -m pytest -q tests` includes `tests/test_docs_sections.py`, which expands every include line.
- **CI:** `.github/workflows/pages.yml` runs `mkdocs build --strict` on PRs that touch `docs/`, `skills/`, root Markdown files, or `mkdocs.yml`. It does not deploy: the organization's IP allow list blocks Pages deployments from GitHub-hosted runners.
- **Publish** (maintainers, after docs or skill changes merge): from an up-to-date `dev` checkout on an allowed network, run

  ```
  uv run --isolated --with-requirements docs/requirements.txt \
      mkdocs gh-deploy --strict --no-history -m "Deploy docs from dev @ $(git rev-parse --short HEAD)"
  ```

  This pushes the built site to the `gh-pages` branch, which Pages serves.
