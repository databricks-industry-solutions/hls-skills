#!/usr/bin/env python3
"""Validate individual SKILL.md quality: frontmatter and template sections.

Simpler fork of SciAgent-Skills tests/test_skill_quality.py — no registry.
Checks frontmatter constraints and required H2 sections against
templates/SKILL_TEMPLATE.md (pipeline) or SKILL_TEMPLATE_GUIDE.md (guide).

Usage:
  python tests/test_skill_quality.py skills/my-skill/SKILL.md
  python tests/test_skill_quality.py skills/my-skill/
  python tests/test_skill_quality.py --all
  pytest tests/test_skill_quality.py
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

# Lowercase kebab-case: a-z, 0-9, hyphens; no leading/trailing hyphen
NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
STOP_VERBS = ("Use ", "A ", "An ", "The ", "Query ", "Fetch ", "Run ")

# Required H2 sections by template sub-type (from templates/)
PIPELINE_REQUIRED = {
    "## Overview",
    "## When to Use",
    "## Workflow",
    "## Troubleshooting",
    "## Guardrails",
    "## References",
}
PIPELINE_RECOMMENDED = {
    "## Prerequisites",
    "## Quick Start",
    "## Key Parameters",
    "## Expected Outputs",
}

GUIDE_REQUIRED = {
    "## Overview",
    "## When to Use",
    "## Key Concepts",
    "## Decision Framework",
    "## Best Practices",
    "## Troubleshooting",
    "## Guardrails",
    "## References",
}
GUIDE_RECOMMENDED = {
    "## Workflow",
    "## Protocol Guidelines",
    "## Related Skills",
}

REQUIRED_BY_TYPE = {
    "pipeline": PIPELINE_REQUIRED,
    "guide": GUIDE_REQUIRED,
}
RECOMMENDED_BY_TYPE = {
    "pipeline": PIPELINE_RECOMMENDED,
    "guide": GUIDE_RECOMMENDED,
}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter. Uses PyYAML when available, else a minimal parser."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip()
    try:
        import yaml

        data = yaml.safe_load(block)
        return data if isinstance(data, dict) else {}
    except ImportError:
        return _parse_frontmatter_simple(block)


def _parse_frontmatter_simple(block: str) -> dict:
    """Minimal key: value parser for common single-line frontmatter."""
    fm: dict = {}
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        value = raw.strip().strip("\"'")
        fm[key.strip()] = value
    return fm


def extract_sections(text: str) -> set[str]:
    """Return the set of H2 section headings in a markdown file."""
    return set(re.findall(r"^## .+", text, re.MULTILINE))


def extract_section_order(text: str) -> list[str]:
    """Return H2 section headings in document order."""
    return re.findall(r"^## .+", text, re.MULTILINE)


def discover_skills(skills_dir: Path = SKILLS_DIR) -> list[Path]:
    """Find all SKILL.md files under skills/."""
    if not skills_dir.is_dir():
        return []
    return sorted(skills_dir.rglob("SKILL.md"))


def resolve_skill_path(path: Path) -> Path:
    """Accept a SKILL.md file or a directory containing one."""
    path = path.expanduser().resolve()
    if path.is_dir():
        candidate = path / "SKILL.md"
        if not candidate.exists():
            raise FileNotFoundError(f"No SKILL.md in directory: {path}")
        return candidate
    if path.name != "SKILL.md":
        raise ValueError(f"Expected a SKILL.md path, got: {path}")
    if not path.exists():
        raise FileNotFoundError(f"SKILL.md not found: {path}")
    return path


# ---------------------------------------------------------------------------
# Type detection
# ---------------------------------------------------------------------------

def detect_skill_type(sections: set[str]) -> str:
    """Infer pipeline / guide from which required set fits best."""
    if "## Key Concepts" in sections and "## Decision Framework" in sections:
        return "guide"
    if "## Workflow" in sections:
        return "pipeline"
    scores = {
        kind: len(required & sections)
        for kind, required in REQUIRED_BY_TYPE.items()
    }
    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    path: Path
    skill_type: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_skill(path: Path, skill_type: str | None = None) -> ValidationResult:
    """Validate one SKILL.md. Returns errors (fail) and warnings (soft)."""
    path = resolve_skill_path(path)
    result = ValidationResult(path=path)
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    sections = extract_sections(text)
    label = path.parent.name

    # --- Frontmatter ---
    if not fm:
        result.errors.append(f"[{label}] Missing or unparseable YAML frontmatter")
        return result

    name = fm.get("name")
    if not name:
        result.errors.append(f"[{label}] Missing frontmatter field: name")
    else:
        name = str(name)
        if len(name) > 64:
            result.errors.append(
                f"[{label}] name is {len(name)} chars, max is 64"
            )
        if not NAME_PATTERN.match(name):
            result.errors.append(
                f"[{label}] name '{name}' must be lowercase kebab-case "
                f"(a-z, 0-9, hyphens; ≤64 chars)"
            )
        if name != path.parent.name:
            result.errors.append(
                f"[{label}] Frontmatter name '{name}' does not match "
                f"parent folder '{path.parent.name}'"
            )

    desc = fm.get("description")
    if not desc:
        result.errors.append(f"[{label}] Missing frontmatter field: description")
    else:
        desc = str(desc)
        if len(desc) > 1024:
            result.errors.append(
                f"[{label}] description is {len(desc)} chars, max is 1024"
            )
        if desc.startswith(STOP_VERBS):
            result.warnings.append(
                f"[{label}] description starts with a stop verb; "
                "lead with a tool/domain keyword instead"
            )

    if "version" not in fm:
        result.errors.append(f"[{label}] Missing frontmatter field: version")

    if "author" not in fm:
        result.errors.append(f"[{label}] Missing frontmatter field: author")

    if "license" not in fm:
        result.errors.append(f"[{label}] Missing frontmatter field: license")

    # --- Sections ---
    inferred = detect_skill_type(sections)
    result.skill_type = skill_type or inferred
    if skill_type and skill_type != inferred:
        result.warnings.append(
            f"[{label}] Forced type '{skill_type}' but content looks like '{inferred}'"
        )

    required = REQUIRED_BY_TYPE[result.skill_type]
    missing = required - sections
    if missing:
        result.errors.append(
            f"[{label}] Missing {result.skill_type} sections: {sorted(missing)}"
        )

    if result.skill_type == "guide":
        order = extract_section_order(text)
        expected_prefix = ["## Overview", "## When to Use"]
        if order[:2] != expected_prefix:
            result.errors.append(
                f"[{label}] Guide sections must start with "
                f"{expected_prefix}; found {order[:2]}"
            )

    recommended = RECOMMENDED_BY_TYPE[result.skill_type]
    soft_missing = recommended - sections
    if soft_missing:
        result.warnings.append(
            f"[{label}] Recommended {result.skill_type} sections missing: "
            f"{sorted(soft_missing)}"
        )

    return result


def validate_paths(
    paths: list[Path],
    skill_type: str | None = None,
) -> list[ValidationResult]:
    return [validate_skill(p, skill_type=skill_type) for p in paths]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _print_result(result: ValidationResult) -> None:
    status = "OK" if result.ok else "FAIL"
    print(f"{status}  {_display_path(result.path)}  [{result.skill_type}]")
    for err in result.errors:
        print(f"  ✗ {err}")
    for warn in result.warnings:
        print(f"  ⚠ {warn}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate SKILL.md frontmatter and template sections."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="SKILL.md file(s) or skill directories",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"Validate every SKILL.md under {SKILLS_DIR}",
    )
    parser.add_argument(
        "--type",
        choices=sorted(REQUIRED_BY_TYPE),
        default=None,
        help="Force template type instead of auto-detect",
    )
    args = parser.parse_args(argv)

    if args.all:
        paths = discover_skills()
        if not paths:
            print(f"No SKILL.md files found under {SKILLS_DIR}", file=sys.stderr)
            return 1
    elif args.paths:
        try:
            paths = [resolve_skill_path(p) for p in args.paths]
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 2

    results = validate_paths(paths, skill_type=args.type)
    for result in results:
        _print_result(result)

    n_fail = sum(1 for r in results if not r.ok)
    n_warn = sum(len(r.warnings) for r in results)
    print()
    if n_fail:
        print(f"FAILED — {n_fail}/{len(results)} skill(s) with errors ({n_warn} warning(s))")
        return 1
    print(f"OK — {len(results)} skill(s) validated ({n_warn} warning(s))")
    return 0


# ---------------------------------------------------------------------------
# Pytest (optional): discovers all skills under skills/
# ---------------------------------------------------------------------------

def _skill_id(path: Path) -> str:
    try:
        return str(path.parent.relative_to(SKILLS_DIR))
    except ValueError:
        return path.parent.name


ALL_SKILLS = discover_skills()

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

if pytest is not None and ALL_SKILLS:

    @pytest.mark.parametrize("skill_path", ALL_SKILLS, ids=_skill_id)
    def test_frontmatter_and_sections(skill_path: Path):
        result = validate_skill(skill_path)
        assert result.ok, "\n".join(result.errors)

    @pytest.mark.parametrize("skill_path", ALL_SKILLS, ids=_skill_id)
    def test_frontmatter_name_length(skill_path: Path):
        fm = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
        name = str(fm.get("name", ""))
        assert name, f"[{skill_path.parent.name}] Missing name"
        assert len(name) <= 64, (
            f"[{skill_path.parent.name}] name is {len(name)} chars, max is 64"
        )

    @pytest.mark.parametrize("skill_path", ALL_SKILLS, ids=_skill_id)
    def test_frontmatter_description_length(skill_path: Path):
        fm = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
        desc = str(fm.get("description", ""))
        assert desc, f"[{skill_path.parent.name}] Missing description"
        assert len(desc) <= 1024, (
            f"[{skill_path.parent.name}] description is {len(desc)} chars, max is 1024"
        )

    @pytest.mark.parametrize("skill_path", ALL_SKILLS, ids=_skill_id)
    def test_frontmatter_version_exists(skill_path: Path):
        fm = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
        assert "version" in fm, (
            f"[{skill_path.parent.name}] Missing 'version' field in frontmatter"
        )

    @pytest.mark.parametrize("skill_path", ALL_SKILLS, ids=_skill_id)
    def test_frontmatter_author_exists(skill_path: Path):
        fm = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
        assert "author" in fm, (
            f"[{skill_path.parent.name}] Missing 'author' field in frontmatter"
        )

    @pytest.mark.parametrize("skill_path", ALL_SKILLS, ids=_skill_id)
    def test_frontmatter_license_exists(skill_path: Path):
        fm = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
        assert "license" in fm, (
            f"[{skill_path.parent.name}] Missing 'license' field in frontmatter"
        )


if __name__ == "__main__":
    sys.exit(main())
