"""README and the landing page skill table come from skills/*/SKILL.md."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "docs" / "hooks"))

from skill_catalog import (  # noqa: E402
    CatalogError,
    js_catalog,
    load_skills,
    main,
    readme_table,
    replace_block,
    sync,
)

def _write_skill(root: Path, name: str, category: str) -> None:
    path = root / name / "SKILL.md"
    path.parent.mkdir()
    path.write_text(
        f"---\nname: {name}\ndescription: {name} skill.\n"
        f"category: {category}\nsummary: {name}.\n---\n",
        encoding="utf-8",
    )


def test_catalog_order_is_category_then_name(tmp_path: Path):
    # Folder order on disk deliberately differs from the expected output order.
    for name, category in [
        ("zeta", "Others"),
        ("alpha", "Clinical"),
        ("mu", "Bioinformatics"),
        ("beta", "Others"),
        ("aa", "Bioinformatics"),
    ]:
        _write_skill(tmp_path, name, category)
    assert [s["name"] for s in load_skills(tmp_path)] == [
        "aa", "mu",  # Bioinformatics
        "alpha",  # Clinical
        "beta", "zeta",  # Others
    ]


def test_repo_skill_names_match_folders():
    """AGENTS.md: folder name must match frontmatter `name`."""
    for skill in load_skills():
        assert skill["name"] == skill["folder"], skill["folder"]


def test_readme_and_landing_page_match_generated_catalog():
    stale = [p.relative_to(REPO_ROOT).as_posix() for p in sync(write=False)]
    assert not stale, (
        f"Skill catalog is stale ({', '.join(stale)}). Run: python docs/hooks/skill_catalog.py"
    )
    skills = load_skills()
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


def test_main_reports_catalog_error_without_traceback(tmp_path, monkeypatch, capsys):
    _write_skill(tmp_path, "demo", "Clinical RWE")
    monkeypatch.setattr(
        "skill_catalog.load_skills", lambda: load_skills(tmp_path)
    )
    assert main(["--check"]) == 1
    assert "Skill catalog error: demo: frontmatter category" in capsys.readouterr().err
