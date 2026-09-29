"""A skill's eval/ answer key and tests/ must never be published to Unity Catalog."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sync_skills_git2unity import EXCLUDED_DIRS, discover_skills, is_published, read_bundle  # noqa: E402


def test_eval_and_tests_are_excluded():
    assert {"eval", "tests"} <= EXCLUDED_DIRS


@pytest.mark.parametrize(
    "rel, shipped",
    [
        ("SKILL.md", True),
        ("references/guide.md", True),
        ("scripts/helper.py", True),
        ("eval.md", True),
        ("references/eval/notes.md", True),
        ("scripts/tests/fixture.py", True),
        ("eval/expectations.json", False),
        ("eval/nested/answer.json", False),
        ("tests/test_helper.py", False),
        ("tests/requirements.txt", False),
    ],
)
def test_only_top_level_eval_and_tests_are_dropped(rel, shipped):
    assert is_published(rel) is shipped


def test_repo_skills_ship_no_eval_or_tests_files():
    skills, _ = discover_skills(REPO_ROOT)
    assert skills, "no skills discovered"
    for leaf, skill_dir in skills.items():
        bundle = read_bundle(skill_dir)
        assert "SKILL.md" in bundle, f"{leaf} bundle is missing SKILL.md"
        leaked = [p for p in bundle if Path(p).parts[0] in {"eval", "tests"}]
        assert not leaked, f"{leaf} would publish eval/ or tests/ files: {leaked}"
