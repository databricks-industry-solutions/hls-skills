"""Skill table for README.md and docs/index.html, from skills/*/SKILL.md.

Each skill's frontmatter holds `category` and `summary`. This module formats
those into the README Markdown table and the landing-page TOPICS/SKILLS
arrays. Markers in those files are the only parts that are rewritten.

  python docs/hooks/skill_catalog.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOOKS_DIR.parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
README = REPO_ROOT / "README.md"
LANDING = REPO_ROOT / "docs" / "index.html"

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

# Display order of landing-page filter chips and README groups.
CATEGORIES = [
    ("Bioinformatics", "var(--t-bio)"),
    ("Clinical RWE", "var(--t-rwe)"),
    ("Payer and provider", "var(--t-pp)"),
    ("Others", "var(--t-oth)"),
]
CATEGORY_NAMES = tuple(name for name, _ in CATEGORIES)
CATEGORY_INDEX = {name: i for i, name in enumerate(CATEGORY_NAMES)}

README_START = "<!-- skill-catalog:start -->"
README_END = "<!-- skill-catalog:end -->"
JS_START = "/* skill-catalog:start */"
JS_END = "/* skill-catalog:end */"


class CatalogError(ValueError):
    """A skill's catalog fields are missing or a marker block is absent."""


def _parse_frontmatter(text: str) -> dict:
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    try:
        import yaml

        data = yaml.safe_load(match.group(1))
        return data if isinstance(data, dict) else {}
    except ImportError:
        fm = {}
        for line in match.group(1).splitlines():
            if not line.strip() or line.strip().startswith("#") or ":" not in line:
                continue
            key, _, raw = line.partition(":")
            fm[key.strip()] = raw.strip().strip("\"'")
        return fm
    except Exception as exc:
        raise CatalogError(f"unparseable YAML frontmatter: {exc}") from exc


def _summary(meta: dict) -> str:
    explicit = " ".join(str(meta.get("summary") or "").split())
    if explicit:
        return explicit
    description = " ".join(str(meta.get("description") or "").split())
    first = description.split(". ")[0].rstrip(".")
    return first


def load_skills(skills_dir: Path = SKILLS_DIR) -> list[dict]:
    """One dict per skills/*/SKILL.md, ordered for the public tables."""
    skills = []
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER.match(text)
        try:
            meta = _parse_frontmatter(text)
        except CatalogError as exc:
            raise CatalogError(f"{path.parent.name}: {exc}") from exc
        folder = path.parent
        eval_dir = folder / "eval"
        category = str(meta.get("category") or "").strip()
        if category not in CATEGORY_INDEX:
            allowed = ", ".join(CATEGORY_NAMES)
            raise CatalogError(
                f"{folder.name}: frontmatter category must be one of: {allowed}"
            )
        summary = _summary(meta)
        if not summary:
            raise CatalogError(
                f"{folder.name}: set frontmatter summary (one-line table blurb)"
            )
        order = meta.get("catalog_order", 1000)
        try:
            order = int(order)
        except (TypeError, ValueError) as exc:
            raise CatalogError(
                f"{folder.name}: catalog_order must be an integer"
            ) from exc
        body = text[match.end() :] if match else text
        skills.append(
            {
                "folder": folder.name,
                "name": str(meta.get("name") or folder.name),
                "description": " ".join(str(meta.get("description") or "").split()),
                "summary": summary,
                "category": category,
                "catalog_order": order,
                "version": str(meta.get("version") or ""),
                "author": str(meta.get("author") or ""),
                "license": str(meta.get("license") or ""),
                "body": body,
                "has_report": (eval_dir / "eval_report.md").is_file(),
                "has_eval": eval_dir.is_dir() and any(eval_dir.iterdir()),
            }
        )
    skills.sort(
        key=lambda s: (CATEGORY_INDEX[s["category"]], s["catalog_order"], s["name"])
    )
    return skills


def readme_table(skills: list[dict] | None = None) -> str:
    skills = skills if skills is not None else load_skills()
    rows = [
        "| Skill | Category | What it does |",
        "|-------|----------|--------------|",
    ]
    for skill in skills:
        summary = skill["summary"].replace("|", "\\|")
        rows.append(
            f"| [**{skill['name']}**](skills/{skill['folder']}/SKILL.md) "
            f"| {skill['category']} | {summary} |"
        )
    return "\n".join(rows)


def js_catalog(skills: list[dict] | None = None) -> str:
    skills = skills if skills is not None else load_skills()
    topics = ",\n".join(
        f"    {{ name: {json.dumps(name, ensure_ascii=False)}, color: {json.dumps(color, ensure_ascii=False)} }}"
        for name, color in CATEGORIES
    )
    items = ",\n".join(
        "    { "
        f"name: {json.dumps(s['name'], ensure_ascii=False)}, "
        f"topic: {json.dumps(s['category'], ensure_ascii=False)},\n"
        f"      outcome: {json.dumps(s['summary'], ensure_ascii=False)} }}"
        for s in skills
    )
    return (
        f"  const TOPICS = [\n{topics}\n  ];\n\n"
        f"  const SKILLS = [\n{items}\n  ];"
    )


def replace_block(text: str, start: str, end: str, inner: str) -> str:
    i = text.find(start)
    j = text.find(end)
    if i < 0 or j < 0 or j < i:
        raise CatalogError(f"missing markers {start!r} ... {end!r}")
    indent = j
    while indent > 0 and text[indent - 1] in " \t":
        indent -= 1
    return f"{text[:i]}{start}\n{inner.rstrip()}\n{text[indent:]}"


def inject_readme(text: str, skills: list[dict] | None = None) -> str:
    return replace_block(text, README_START, README_END, readme_table(skills))


def inject_landing_page(text: str, skills: list[dict] | None = None) -> str:
    return replace_block(text, JS_START, JS_END, js_catalog(skills))


def sync(write: bool = True) -> tuple[Path, ...]:
    skills = load_skills()
    readme = inject_readme(README.read_text(encoding="utf-8"), skills)
    landing = inject_landing_page(LANDING.read_text(encoding="utf-8"), skills)
    if write:
        README.write_text(readme, encoding="utf-8")
        LANDING.write_text(landing, encoding="utf-8")
    return README, LANDING


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if README.md or docs/index.html are out of date",
    )
    args = parser.parse_args(argv)
    skills = load_skills()
    readme_ok = README.read_text(encoding="utf-8") == inject_readme(
        README.read_text(encoding="utf-8"), skills
    )
    landing_ok = LANDING.read_text(encoding="utf-8") == inject_landing_page(
        LANDING.read_text(encoding="utf-8"), skills
    )
    if args.check:
        if readme_ok and landing_ok:
            return 0
        stale = [
            path
            for path, ok in ((README, readme_ok), (LANDING, landing_ok))
            if not ok
        ]
        print(
            "Skill catalog is stale. Run:\n"
            "  python docs/hooks/skill_catalog.py\n"
            "Out of date: " + ", ".join(p.as_posix() for p in stale),
            file=sys.stderr,
        )
        return 1
    sync(write=True)
    print(f"Updated {README.relative_to(REPO_ROOT)} and {LANDING.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
