#!/usr/bin/env python3
"""Functional tests for the payer-provider-measure-catalog skill.

Unlike the repo-wide SKILL.md linter (tests/test_skill_quality.py), these exercise
the skill's actual code: the catalog validator and the metric-view generator.

  python3 -m pytest skills/semantic-layer/payer-provider-measure-catalog/tests/
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_ROOT / "scripts"
FIXTURE = Path(__file__).resolve().parent / "fixture_mapping.yaml"

pytest.importorskip("yaml", reason="PyYAML required for the catalog scripts")


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=cwd,
                          capture_output=True, text=True)


# ── the catalog is internally correct ────────────────────────────────────────

def test_validator_passes_clean():
    """validate_catalog.py must report 0 errors on the shipped catalog."""
    r = _run([str(SCRIPTS / "validate_catalog.py")], cwd=SKILL_ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 error(s)" in r.stdout


def test_render_produces_catalog_md():
    r = _run([str(SCRIPTS / "render_catalog.py")], cwd=SKILL_ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (SKILL_ROOT / "references" / "catalog.md").exists()


# ── the generator produces the right assets from a mapping ───────────────────

def _generate(tmp: Path):
    r = _run([str(SCRIPTS / "generate_semantic_layer.py"),
              "--mapping", str(FIXTURE), "--out", str(tmp)], cwd=SKILL_ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return (tmp / "01_silver.sql").read_text(), \
           (tmp / "03_metric_views.sql").read_text(), \
           (tmp / "plan.md").read_text()


def test_generator_scope_inference():
    """Only mapped entities produce metric views; unmapped domains are skipped."""
    with tempfile.TemporaryDirectory() as d:
        silver, mv, plan = _generate(Path(d))
        # mapped -> present
        assert "mv_care_delivery__encounter" in mv
        assert "mv_claims__revenue_cycle" in mv
        assert "mv_claims__adjudication" in mv
        # unmapped entity -> skipped
        assert "SKIPPED (entity `member_month` not mapped)" in plan
        assert "SKIPPED (entity `care_gap` not mapped)" in plan
        assert "mv_payer_economics__mlr" not in _mv_created(mv)


def test_generator_measure_skipping():
    """Measures whose canonical fields are missing get skipped, not emitted broken."""
    with tempfile.TemporaryDirectory() as d:
        silver, mv, plan = _generate(Path(d))
        # no allowed_amount in fixture -> net_collection_rate must be skipped
        assert "net_collection_rate" in plan and "net_collection_rate" not in _measure_defs(mv)
        # no index-admission -> readmission_30day_rate skipped, but the raw count survives
        assert "readmission_30day_rate" not in _measure_defs(mv)
        assert "readmission_30day_count" in _measure_defs(mv)


def test_generator_composites_use_measure():
    """Emitted composites must be ratio-of-measures (MEASURE/MEASURE), never bare aggregates."""
    with tempfile.TemporaryDirectory() as d:
        _silver, mv, _plan = _generate(Path(d))
        # denial_rate_count is a composite that survives -> must be ratio-of-measures
        assert "MEASURE(denied_claim_count) / MEASURE(claim_count)" in mv


def test_silver_conforms_enums():
    """Silver view materializes enum maps as CASE producing canonical values."""
    with tempfile.TemporaryDirectory() as d:
        silver, _mv, _plan = _generate(Path(d))
        assert "AS encounter_class" in silver
        assert "'inpatient'" in silver and "'emergency'" in silver


# ── helpers ───────────────────────────────────────────────────────────────

def _mv_created(mv_sql: str) -> str:
    return "\n".join(l for l in mv_sql.splitlines() if l.startswith("CREATE OR REPLACE VIEW"))


def _measure_defs(mv_sql: str) -> str:
    return "\n".join(l for l in mv_sql.splitlines() if l.strip().startswith("- name:"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
