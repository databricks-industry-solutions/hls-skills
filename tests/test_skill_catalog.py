"""README and the landing page skill table come from skills/*/SKILL.md."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "docs" / "hooks"))

from skill_catalog import (  # noqa: E402
    CATEGORY_INDEX,
    CATEGORY_NAMES,
    CatalogError,
    DOCS_CHANGELOG,
    docs_changelog,
    inject_landing_page,
    inject_readme,
    js_catalog,
    load_skills,
    readme_table,
    replace_block,
)

README = REPO_ROOT / "README.md"
LANDING = REPO_ROOT / "docs" / "index.html"


def test_catalog_order_follows_category_then_name():
    """Catalog membership comes from skills/*/SKILL.md — no golden name list.

    A new skill is picked up automatically. Contributors still run
    ``python docs/hooks/skill_catalog.py`` so README.md, docs/index.html, and
    docs/CHANGELOG.md match.
    """
    skills = load_skills()
    folders = {p.parent.name for p in (REPO_ROOT / "skills").glob("*/SKILL.md")}
    assert {s["folder"] for s in skills} == folders
    for skill in skills:
        assert skill["name"] == skill["folder"]
        assert skill["category"] in CATEGORY_NAMES
    expected = sorted(skills, key=lambda s: (CATEGORY_INDEX[s["category"]], s["name"]))
    assert [s["name"] for s in skills] == [s["name"] for s in expected]


def test_readme_and_landing_page_match_generated_catalog():
    skills = load_skills()
    assert README.read_text(encoding="utf-8") == inject_readme(
        README.read_text(encoding="utf-8"), skills
    )
    assert LANDING.read_text(encoding="utf-8") == inject_landing_page(
        LANDING.read_text(encoding="utf-8"), skills
    )
    assert DOCS_CHANGELOG.read_text(encoding="utf-8") == docs_changelog()
    assert "sc-rnaseq" in readme_table(skills)
    assert "Bioinformatics" in js_catalog(skills)


def test_missing_markers_fail():
    with pytest.raises(CatalogError, match="missing markers"):
        replace_block("nope", "<!-- a -->", "<!-- b -->", "x")


def test_invalid_category_fails(tmp_path: Path):
    skill = tmp_path / "demo" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text(
        "---\nname: demo\ndescription: Demo skill.\n"
        "category: Not a category\nsummary: Demo.\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogError, match="category must be one of"):
        load_skills(tmp_path)
