"""Consistency checks for the accelerators skill references.

The skill is instructions only, so the tests guard the parts an agent relies on:
every index row has a reference file and vice versa, every reference has the
template's sections, every reference is routed from SKILL.md, and internal
file pointers resolve.

Run: uv run --isolated --with pytest python -m pytest -q skills/accelerators/tests
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
REFS = SKILL_DIR / "references"
ACCEL_DIR = REFS / "accelerators"
SKILL_MD = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
INDEX_MD = (ACCEL_DIR / "index.md").read_text(encoding="utf-8")


def h2_sections(text: str) -> list[str]:
    return re.findall(r"^## (.+)$", text, re.MULTILINE)


TEMPLATE_SECTIONS = h2_sections((REFS / "accelerator-template.md").read_text(encoding="utf-8"))
REFERENCE_FILES = sorted(p for p in ACCEL_DIR.glob("*.md") if p.name != "index.md")
INDEX_LINKS = re.findall(r"\]\(([a-z0-9-]+\.md)\)", INDEX_MD)


def test_template_has_sections():
    assert TEMPLATE_SECTIONS, "accelerator-template.md has no H2 sections"


def test_index_and_files_match():
    assert sorted(INDEX_LINKS) == sorted(p.name for p in REFERENCE_FILES)


@pytest.mark.parametrize("ref", REFERENCE_FILES, ids=lambda p: p.stem)
def test_reference_has_template_sections(ref: Path):
    sections = h2_sections(ref.read_text(encoding="utf-8"))
    missing = [s for s in TEMPLATE_SECTIONS if s not in sections]
    assert not missing, f"{ref.name} missing sections: {missing}"


@pytest.mark.parametrize("ref", REFERENCE_FILES, ids=lambda p: p.stem)
def test_reference_identity_fields(ref: Path):
    text = ref.read_text(encoding="utf-8")
    assert re.search(r"Repo: https://github\.com/databricks-industry-solutions/" + re.escape(ref.stem), text)
    assert re.search(r"Reviewed: \d{4}-\d{2}-\d{2} against commit [0-9a-f]{7,40}", text)


@pytest.mark.parametrize("ref", REFERENCE_FILES, ids=lambda p: p.stem)
def test_reference_is_routed_from_skill(ref: Path):
    assert f"references/accelerators/{ref.name}" in SKILL_MD


def test_skill_file_pointers_resolve():
    for rel in set(re.findall(r"`(references/[^`]+\.md)`", SKILL_MD)):
        if "<" in rel:
            continue
        assert (SKILL_DIR / rel).is_file(), f"SKILL.md points to missing {rel}"


def test_no_placeholders_left_in_references():
    for ref in REFERENCE_FILES:
        text = ref.read_text(encoding="utf-8")
        assert not re.search(r"^- (Repo|Install doc|Maintainers|Reviewed):\s*$", text, re.MULTILINE), ref.name
