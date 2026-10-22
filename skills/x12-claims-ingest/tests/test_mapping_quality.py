"""Mapping rules (version, claim versions, line context) and quality checks, against generated answer keys."""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import generate_837  # noqa: E402
import generate_data  # noqa: E402  (the benchmark specs, so the skill is checked on the exact eval data)
import x12_837  # noqa: E402
from ingest_scorers import QUALITY_RULE_IDS, gold_from_key, output_from_records  # noqa: E402
from objective import ingest_objective_v2  # noqa: E402

AS_OF = "2026-10-19"


def _parse(spark, files):
    raw = spark.createDataFrame([(f"/synthetic/{n}", c) for n, c in files.items()], "file_path string, value string")
    segs = x12_837.segments(raw)
    checks = x12_837.transaction_checks(raw, segs)
    return checks, x12_837.parse_837(segs, checks)


@pytest.fixture(scope="module")
def mapping(spark):
    seed, spec = generate_data.TASKS["x12-005"]
    files, key = generate_837.build(seed=seed, spec=spec)
    checks, out = _parse(spark, files)
    current = x12_837.resolve_claim_versions(out["claims"])
    return {"key": key, "checks": checks.collect(), "current": current.collect(), "lines": out["claim_lines"].collect()}


@pytest.fixture(scope="module")
def quality(spark):
    seed, spec = generate_data.TASKS["x12-006"]
    files, key = generate_837.build(seed=seed, spec=spec)
    checks, out = _parse(spark, files)
    q = x12_837.quality_checks(out["claims"], out["claim_lines"], out["claim_diagnoses"], checks, as_of=AS_OF)
    return {"key": key, "checks": checks.collect(), "claims": out["claims"].collect(),
            "lines": out["claim_lines"].collect(), "quality": q.collect()}


def _d(s):
    return datetime.strptime(s, "%Y%m%d").date() if s else None


def test_npi_check_digit_sql(spark):
    rows = spark.createDataFrame([("1234567893",), ("1245002005",), ("1245002000",), ("123456789",), (None,)], "n string")
    got = [r[0] for r in rows.select(x12_837.npi_is_valid("n")).collect()]
    assert got[:4] == [True, True, False, False] and not got[4]


def test_4010_files_map_as_professional_with_icd9(mapping):
    key = {c["patient_control_number"]: c for c in mapping["key"]["claims"]}
    got = {r["patient_control_number"]: r for r in mapping["current"]}
    old = [p for p, c in key.items() if c["x12_version"] == "4010"]
    assert old
    for p in old:
        assert got[p]["x12_version"] == "4010" and got[p]["claim_type"] == "professional"
        assert got[p]["principal_diagnosis_code"] == key[p]["principal_diagnosis_code"]


def test_replacements_and_voids_resolve_to_current_view(mapping):
    key = {c["patient_control_number"]: c for c in mapping["key"]["claims"]}
    got = {r["patient_control_number"]: r for r in mapping["current"]}
    assert set(got) == set(key)  # voided claims gone, each claim once
    for p, c in key.items():
        assert got[p]["total_charge_amount"] == Decimal(str(c["total_charge_amount"])).quantize(Decimal("0.01"))
        assert got[p]["claim_frequency_code"] == c["frequency"]


def test_line_rendering_precedence_and_pointer_resolution(mapping):
    key = {c["patient_control_number"]: c for c in mapping["key"]["claims"]}
    current_ids = {r["claim_id"]: r["patient_control_number"] for r in mapping["current"]}
    lines = defaultdict(dict)
    for r in mapping["lines"]:
        if r["claim_id"] in current_ids:
            lines[current_ids[r["claim_id"]]][r["line_number"]] = r
    assert any(ln["line_rendering_npi"] for c in key.values() for ln in c["lines"])
    for p, c in key.items():
        for ln in c["lines"]:
            g = lines[p][ln["line_number"]]
            assert g["effective_rendering_npi"] == ln["rendering_npi"]
            assert g["line_diagnosis_codes"] == ln["diagnosis_codes"]


def test_quality_checks_find_exactly_the_planted_defects(quality):
    gold = {(c["patient_control_number"], r) for c in quality["key"]["claims"] for r in c["defects"]}
    got = {(r["patient_control_number"], r["rule_id"]) for r in quality["quality"] if r["rule_id"] in QUALITY_RULE_IDS}
    assert got == gold
    clean = {c["patient_control_number"] for c in quality["key"]["claims"] if not c["defects"]}
    assert not [r for r in quality["quality"] if r["patient_control_number"] in clean]


def test_trimmed_isa_is_parsed_and_flagged(spark):
    spec = [{"name": "trimmed.x12", "kind": "P", "style": {}, "tx": [(4, True)], "ctrl": 901, "trimmed_isa": True}]
    files, key = generate_837.build(seed=9, spec=spec)
    assert len(files["trimmed.x12"].split("~", 1)[0]) < 105
    checks, out = _parse(spark, files)
    rows = checks.collect()
    assert [r["transaction_status"] for r in rows] == ["ok"] and rows[0]["isa_fixed_width"] is False
    assert {r["patient_control_number"] for r in out["claims"].collect()} == {c["patient_control_number"] for c in key["claims"]}
    q = x12_837.quality_checks(out["claims"], out["claim_lines"], out["claim_diagnoses"], checks, as_of=AS_OF).collect()
    assert [r["rule_id"] for r in q] == ["ISA_NOT_FIXED_WIDTH"]


def _contract_rows(claims, lines, checks_rows, quality_rows=None):
    pcn = {r["claim_id"]: r["patient_control_number"] for r in claims}
    cl = [r.asDict() for r in claims]
    ln = [dict(r.asDict(), patient_control_number=pcn[r["claim_id"]], service_date=r["service_from_date"],
               rendering_provider_npi=r["effective_rendering_npi"]) for r in lines if r["claim_id"] in pcn]
    ch = [{"file_name": r["file_path"], "status": r["transaction_status"]} for r in checks_rows]
    q = [r.asDict() for r in quality_rows or []]
    return cl, ln, ch, q


def test_skill_scores_one_on_mapping_task(mapping):
    extras_c, extras_l = ("x12_version",), ("rendering_provider_npi", "line_diagnosis_codes")
    gold = gold_from_key(mapping["key"], claim_extras=extras_c, line_extras=extras_l)
    cl, ln, ch, _ = _contract_rows(mapping["current"], mapping["lines"], mapping["checks"])
    obj = ingest_objective_v2(gold, output_from_records(cl, ln, ch, claim_extras=extras_c, line_extras=extras_l))
    assert obj.score == 1.0, obj.breakdown


def test_skill_scores_one_on_quality_task(quality):
    gold = gold_from_key(quality["key"], quality=True)
    cl, ln, ch, q = _contract_rows(quality["claims"], quality["lines"], quality["checks"], quality["quality"])
    obj = ingest_objective_v2(gold, output_from_records(cl, ln, ch, quality_rows=q))
    assert obj.score == 1.0, obj.breakdown
