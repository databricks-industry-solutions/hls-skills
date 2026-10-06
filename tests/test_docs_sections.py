"""Docs pages copy sections of repository files; every include must resolve."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "docs" / "hooks"))

from repo_links import REPO, absolute_links  # noqa: E402
from repo_sections import (  # noqa: E402
    MARKER,
    SectionError,
    alerts_to_admonitions,
    expand_includes,
    extract_section,
    omit_section,
    replace_section,
    shift_headings,
    without_title,
)

SOURCE = """# Title

## Setup
#### Clone
Clone it.

```
### not a heading
```

#### Sync with [Gateway](https://example.com)
Run [the script](sync.py).

## Next
Elsewhere.
"""


def test_section_stops_at_next_heading_of_same_level():
    body = extract_section(SOURCE, "Setup")
    assert body.startswith("#### Clone")
    assert "### not a heading" in body
    assert "Run [the script](sync.py)." in body
    assert "Elsewhere" not in body


def test_heading_match_ignores_case_and_link_urls():
    assert extract_section(SOURCE, "sync with gateway") == "Run [the script](sync.py)."


@pytest.mark.parametrize(
    "text, heading, error",
    [
        (SOURCE, "Missing", "no heading"),
        ("## A\nx\n## A\ny\n", "A", "appears 2 times"),
        ("## A\n\n## B\nx\n", "A", "is empty"),
    ],
)
def test_bad_sections_fail(text, heading, error):
    with pytest.raises(SectionError, match=error):
        extract_section(text, heading)


def test_omit_drops_heading_and_its_subsections_only():
    out = omit_section(SOURCE, "Setup")
    assert "## Setup" not in out and "Clone it." not in out and "not a heading" not in out
    assert "# Title" in out and "## Next" in out


def test_replace_keeps_heading_and_swaps_body():
    out = replace_section(SOURCE, "Setup", "See [Setup](setup.md).")
    assert "## Setup\n\nSee [Setup](setup.md).\n\n## Next" in out
    assert "Clone it." not in out


def test_replace_needs_markdown():
    with pytest.raises(SectionError, match="needs '=Markdown'"):
        expand_includes('<!-- include: README.md replace="Setup" -->\n')


def test_omit_unknown_heading_fails():
    with pytest.raises(SectionError, match="no heading"):
        omit_section(SOURCE, "Missing")


def test_whole_file_drops_only_leading_title():
    assert without_title("\n# Title\nIntro\n## A\nx") == "\nIntro\n## A\nx"
    assert without_title("## A\nx") == "## A\nx"


def test_marker_options_parse():
    m = MARKER.match('<!-- include: CONTRIBUTING.md omit="A (B)" omit="C" level=3 -->')
    assert m["path"] == "CONTRIBUTING.md" and m["heading"] is None
    assert 'omit="A (B)"' in m["options"] and "level=3" in m["options"]
    m = MARKER.match("<!-- include: README.md#Setup level=3 -->")
    assert m["heading"] == "Setup"


def test_github_alerts_become_admonitions():
    md = "Intro\n\n> [!WARNING]\n> **Careful.** Line one.\n>\n> Line two.\nAfter\n"
    assert alerts_to_admonitions(md) == (
        "Intro\n\n!!! warning\n    **Careful.** Line one.\n\n    Line two.\n\nAfter"
    )


def test_alerts_in_fenced_code_and_plain_quotes_stay():
    md = "```\n> [!NOTE]\n```\n> just a quote"
    assert alerts_to_admonitions(md) == md


def test_headings_shift_but_fenced_code_does_not():
    shifted = shift_headings(extract_section(SOURCE, "Setup"), 2)
    assert shifted.startswith("## Clone")
    assert "## Sync with [Gateway](https://example.com)" in shifted
    assert "### not a heading" in shifted


def test_relative_links_and_images_point_at_github():
    md = "[s](sync.py) [a](#x) [e](https://e.com) ![i](./img.png)\n```\n[c](code.py)\n```\n"
    out = absolute_links(md, "skills/foo")
    assert f"[s]({REPO}/blob/main/skills/foo/sync.py)" in out
    assert f"![i]({REPO}/raw/main/skills/foo/img.png)" in out
    assert "[a](#x)" in out and "[e](https://e.com)" in out
    assert "[c](code.py)" in out


@pytest.mark.parametrize("path", ["../outside.md", "missing.md"])
def test_bad_paths_fail(path):
    with pytest.raises(SectionError):
        expand_includes(f"<!-- include: {path}#Setup -->\n")


def test_marker_inside_fenced_code_is_left_alone():
    md = "```\n<!-- include: missing.md#Setup -->\n```\n"
    assert expand_includes(md) == (md, set())


def test_readme_setup_expands_with_absolute_links():
    out, used = expand_includes("<!-- include: README.md#Setup -->\n")
    assert used == {REPO_ROOT / "README.md"}
    assert f"]({REPO}/blob/main/sync_skills_git2unity.py)" in out
    assert "<!-- include:" not in out


@pytest.mark.parametrize(
    "page", sorted(REPO_ROOT.glob("docs/**/*.md")), ids=lambda p: p.name
)
def test_every_docs_include_resolves(page):
    expand_includes(page.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["setup.md", "contributing.md", "evaluation.md"])
def test_guide_page_is_copied_from_repo_file(name):
    page = REPO_ROOT / "docs" / "guide" / name
    assert any(MARKER.match(line) for line in page.read_text(encoding="utf-8").splitlines())


def test_evaluation_page_has_whole_section():
    page = REPO_ROOT / "docs" / "guide" / "evaluation.md"
    out, _ = expand_includes(page.read_text(encoding="utf-8"))
    assert "## Run an evaluation" in out and "## What the `eval/` folder holds" in out
    assert "!!! warning" in out and "## Docs site" not in out


def test_contributing_page_has_no_cla():
    page = REPO_ROOT / "docs" / "guide" / "contributing.md"
    out, used = expand_includes(page.read_text(encoding="utf-8"))
    assert used == {REPO_ROOT / "CONTRIBUTING.md"}
    assert "Contributor License Agreement" not in out
    assert "you certify that" not in out
    assert "## Docs site" in out
    assert "#### 3. Evaluate with and without skill\n\nSee [Evaluation](evaluation.md)." in out
    assert "Run an evaluation" not in out and "holds the answer key" not in out
    assert out.count("\n# ") == 0 and out.startswith("# Contributing")
