"""README and the landing page skill table come from skills/*/SKILL.md."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "docs" / "hooks"))

from skill_catalog import (  # noqa: E402
    CATEGORY_NAMES,
    CatalogError,
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
    skills = load_skills()
    names = [s["name"] for s in skills]
    assert names == [
        "bulk-rnaseq",
        "open-weight-models",
        "pathway-enrichment-analysis",
        "sc-rnaseq",
        "cohort-builder",
        "rwe-cohortstudy",
        "payer-provider-measure-catalog",
        "phi-deidentifier",
        "accelerators",
        "skill-eval",
    ]
    assert {s["category"] for s in skills} <= set(CATEGORY_NAMES)


def test_readme_and_landing_page_match_generated_catalog():
    skills = load_skills()
    assert README.read_text(encoding="utf-8") == inject_readme(
        README.read_text(encoding="utf-8"), skills
    )
    assert LANDING.read_text(encoding="utf-8") == inject_landing_page(
        LANDING.read_text(encoding="utf-8"), skills
    )
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
