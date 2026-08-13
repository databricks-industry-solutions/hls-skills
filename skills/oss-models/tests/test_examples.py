#!/usr/bin/env python3
"""Offline structural tests for the worked examples in the oss-models skill.

These tests validate the STRUCTURE of the examples added to SKILL.md and the
per-model reference files. They are deliberately offline and deterministic:

  * no network, no weight downloads, no model execution
  * no GPU, no Databricks workspace
  * standard library only, plus optional PyYAML (skipped if absent)

What is checked:
  1. Every fenced ```json block in the skill parses as JSON.
  2. Every fenced ```yaml block parses as YAML (requires PyYAML).
  3. At least one YAML provenance manifest exists and carries the required
     top-level keys from references/integration-contract.md.
  4. The SKILL.md worked example has an HTTP request (dataframe_records with
     genes + expression), a response envelope (predictions), and a Geneformer
     provenance manifest.
  5. Each of the five model reference files contains an input_example JSON block.

Run:
  python3 -m pytest skills/oss-models/tests/ -q
  python3 skills/oss-models/tests/test_examples.py   # no-pytest fallback
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES_DIR = SKILL_DIR / "references"
MODELS_DIR = REFERENCES_DIR / "models"

# Model families that must each ship a concrete input_example.
MODEL_FILES = [
    MODELS_DIR / "geneformer.md",
    MODELS_DIR / "scgpt.md",
    MODELS_DIR / "scimilarity.md",
    MODELS_DIR / "alphafold-openfold.md",
    MODELS_DIR / "boltz.md",
]

# Markdown files whose fenced code blocks we scan.
MD_FILES = sorted({SKILL_MD, *REFERENCES_DIR.rglob("*.md")})

# Required manifest keys, mirrored from references/integration-contract.md.
REQUIRED_MANIFEST_TOP = {"model", "code", "weights", "license", "runtime", "artifacts"}
REQUIRED_MODEL_KEYS = {"name", "upstream_revision", "reviewed_at"}

_FENCE = re.compile(r"```([A-Za-z0-9_+-]+)\n(.*?)```", re.DOTALL)


def fenced_blocks(text: str, lang: str) -> list[str]:
    """Return the bodies of fenced code blocks tagged with `lang`."""
    return [body for tag, body in _FENCE.findall(text) if tag.lower() == lang]


def json_blocks(path: Path) -> list[str]:
    return fenced_blocks(path.read_text(encoding="utf-8"), "json")


def yaml_blocks(path: Path) -> list[str]:
    return fenced_blocks(path.read_text(encoding="utf-8"), "yaml")


# ---------------------------------------------------------------------------
# Optional pytest wiring — the module also runs standalone (see __main__).
# ---------------------------------------------------------------------------
try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore


def _yaml_or_skip():
    try:
        import yaml  # noqa: F401
    except ImportError:  # pragma: no cover
        if pytest is not None:
            pytest.skip("PyYAML not installed")
        raise
    return yaml


def check_json_blocks_parse(path: Path) -> None:
    for i, block in enumerate(json_blocks(path)):
        try:
            json.loads(block)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{path.name}: json block #{i} does not parse: {exc}")


def check_yaml_blocks_parse(path: Path) -> None:
    yaml = _yaml_or_skip()
    for i, block in enumerate(yaml_blocks(path)):
        try:
            yaml.safe_load(block)
        except yaml.YAMLError as exc:  # type: ignore[attr-defined]
            raise AssertionError(f"{path.name}: yaml block #{i} does not parse: {exc}")


def _all_manifests():
    """Parsed YAML blocks across the skill that look like provenance manifests."""
    yaml = _yaml_or_skip()
    manifests = []
    for path in MD_FILES:
        for block in yaml_blocks(path):
            data = yaml.safe_load(block)
            if isinstance(data, dict) and "model" in data and isinstance(data["model"], dict):
                manifests.append((path, data))
    return manifests


def check_manifests_have_required_keys() -> None:
    manifests = _all_manifests()
    assert manifests, "no provenance manifest (yaml block with a `model:` mapping) found"
    for path, data in manifests:
        missing_top = REQUIRED_MANIFEST_TOP - set(data)
        assert not missing_top, f"{path.name}: manifest missing top-level keys {sorted(missing_top)}"
        missing_model = REQUIRED_MODEL_KEYS - set(data["model"])
        assert not missing_model, f"{path.name}: manifest model missing keys {sorted(missing_model)}"
        assert isinstance(data["artifacts"], list), f"{path.name}: manifest `artifacts` must be a list"


def check_skill_worked_example() -> None:
    blocks = [json.loads(b) for b in json_blocks(SKILL_MD)]

    http = [b for b in blocks if isinstance(b, dict) and "dataframe_records" in b]
    assert http, "SKILL.md: no HTTP request block with `dataframe_records`"
    record = http[0]["dataframe_records"][0]
    for field in ("genes", "expression"):
        assert field in record, f"SKILL.md: HTTP record missing `{field}`"
    assert len(record["genes"]) == len(record["expression"]), (
        "SKILL.md: `genes` and `expression` must be the same length"
    )

    responses = [b for b in blocks if isinstance(b, dict) and "predictions" in b]
    assert responses, "SKILL.md: no response block with `predictions`"

    yaml = _yaml_or_skip()
    manifests = [
        yaml.safe_load(b)
        for b in yaml_blocks(SKILL_MD)
        if isinstance(yaml.safe_load(b), dict) and "model" in yaml.safe_load(b)
    ]
    assert manifests, "SKILL.md: no provenance manifest in the worked example"
    assert manifests[0]["model"].get("name") == "geneformer", (
        "SKILL.md: worked-example manifest should be for `geneformer`"
    )


def check_model_has_input_example(path: Path) -> None:
    dict_blocks = [
        b for b in (json.loads(x) for x in json_blocks(path)) if isinstance(b, dict)
    ]
    assert dict_blocks, f"{path.name}: no JSON input_example object found"


if pytest is not None:

    @pytest.mark.parametrize("path", MD_FILES, ids=lambda p: p.name)
    def test_json_blocks_parse(path: Path):
        check_json_blocks_parse(path)

    @pytest.mark.parametrize("path", MD_FILES, ids=lambda p: p.name)
    def test_yaml_blocks_parse(path: Path):
        check_yaml_blocks_parse(path)

    def test_manifests_have_required_keys():
        check_manifests_have_required_keys()

    def test_skill_worked_example():
        check_skill_worked_example()

    @pytest.mark.parametrize("path", MODEL_FILES, ids=lambda p: p.name)
    def test_model_has_input_example(path: Path):
        check_model_has_input_example(path)


def _main() -> int:
    """Standalone runner used when pytest is unavailable."""
    failures: list[str] = []

    def run(label, fn, *args):
        try:
            fn(*args)
            print(f"OK    {label}")
        except AssertionError as exc:
            print(f"FAIL  {label}: {exc}")
            failures.append(label)

    for path in MD_FILES:
        run(f"json parses [{path.name}]", check_json_blocks_parse, path)
    try:
        import yaml  # noqa: F401

        for path in MD_FILES:
            run(f"yaml parses [{path.name}]", check_yaml_blocks_parse, path)
        run("manifests have required keys", check_manifests_have_required_keys)
        run("skill worked example", check_skill_worked_example)
    except ImportError:
        print("SKIP  yaml checks (PyYAML not installed)")
    for path in MODEL_FILES:
        run(f"model has input_example [{path.name}]", check_model_has_input_example, path)

    print()
    if failures:
        print(f"FAILED — {len(failures)} check(s): {failures}")
        return 1
    print("OK — all example-structure checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
