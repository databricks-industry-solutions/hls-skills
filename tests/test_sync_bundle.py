"""Guard the sync notebook's bundle filter: a skill's eval/ answer key must never ship.

sync_skills_git2unity.py is a Databricks notebook (widgets, spark) and cannot be
imported, so the real EXCLUDED_DIRS and read_bundle are pulled out of its source
with ast and executed in isolation. Renaming or deleting either fails the test.
"""

import ast
from pathlib import Path

SYNC_SCRIPT = Path(__file__).resolve().parent.parent / "sync_skills_git2unity.py"


def _load_read_bundle():
    tree = ast.parse(SYNC_SCRIPT.read_text(encoding="utf-8"))
    wanted = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name == "read_bundle")
        or (isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "EXCLUDED_DIRS" for t in node.targets))
    ]
    assert len(wanted) == 2, "sync_skills_git2unity.py must define EXCLUDED_DIRS and read_bundle at top level"
    ns = {"Path": Path}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), str(SYNC_SCRIPT), "exec"), ns)
    return ns["read_bundle"], ns["EXCLUDED_DIRS"]


def _write(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rel, encoding="utf-8")


def test_eval_dir_is_excluded(tmp_path):
    read_bundle, excluded = _load_read_bundle()
    assert "eval" in excluded
    for rel in [
        "SKILL.md",
        "references/guide.md",
        "scripts/helper.py",
        "eval.md",
        "references/eval/notes.md",
        "eval/expectations.json",
        "eval/nested/answer.json",
    ]:
        _write(tmp_path, rel)

    bundle = read_bundle(tmp_path)

    assert sorted(bundle) == ["SKILL.md", "eval.md", "references/eval/notes.md", "references/guide.md", "scripts/helper.py"]
    assert bundle["SKILL.md"] == b"SKILL.md"


def test_repo_skills_ship_no_eval_files():
    read_bundle, _ = _load_read_bundle()
    skills_dir = SYNC_SCRIPT.parent / "skills"
    for skill in sorted(d for d in skills_dir.iterdir() if (d / "SKILL.md").is_file()):
        leaked = [p for p in read_bundle(skill) if Path(p).parts[0] == "eval"]
        assert not leaked, f"{skill.name} would publish eval files: {leaked}"
