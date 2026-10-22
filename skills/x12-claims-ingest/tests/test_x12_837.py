"""Parser tests against the synthetic answer key (scripts/generate_837.py)."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "x12_837.py"


def _d(s):
    return datetime.strptime(s, "%Y%m%d").date() if s else None


def _ok_claims(parsed):
    return {k: v for k, v in parsed["claims"].items() if v["transaction_status"] == "ok"}


def test_every_complete_claim_is_parsed_once(parsed, generated):
    _, key = generated
    assert set(_ok_claims(parsed)) == {c["patient_control_number"] for c in key["claims"]}
    ids = [r["claim_id"] for r in parsed["claims"].values()]
    assert len(ids) == len(set(ids))


def test_truncated_and_non_x12_files_are_flagged(parsed, generated):
    _, key = generated
    got = {(r["file_path"].rsplit("/", 1)[-1], r["st_control_number"]): r["transaction_status"] for r in parsed["checks"]}
    want = {(t["file"], t["st_control_number"]): t["transaction_status"] for t in key["transactions"]}
    assert got == want
    for pcn, row in parsed["claims"].items():
        if pcn in key["truncated_claims"]:
            assert row["transaction_status"] == "missing_SE"


def test_header_amounts_and_line_totals(parsed, generated):
    _, key = generated
    claims = _ok_claims(parsed)
    for c in key["claims"]:
        row = claims[c["patient_control_number"]]
        assert row["total_charge_amount"] == Decimal(str(c["total_charge_amount"])).quantize(Decimal("0.01"))
        assert row["line_count"] == c["line_count"]
        assert row["line_charge_total"] == row["total_charge_amount"]
        assert row["claim_type"] == c["claim_type"]


def test_member_payer_and_provider_come_from_the_primary_loops(parsed, generated):
    _, key = generated
    claims = _ok_claims(parsed)
    for c in key["claims"]:
        row = claims[c["patient_control_number"]]
        assert row["member_id"] == c["member_id"]
        assert row["payer_id"] == c["payer_id"]  # not the 2330B other payer
        assert row["billing_provider_npi"] == c["billing_provider_npi"]
        assert row["billing_provider_tin"] == c["billing_provider_tin"]
        assert row["claim_filing_indicator"] == c["claim_filing_indicator"]
        npi = row["rendering_provider_npi"] if c["claim_type"] == "professional" else row["attending_provider_npi"]
        assert npi == c["rendering_or_attending_npi"]  # not blanked by the 2330D NM1*82
        assert row["prior_authorization_number"] == c["prior_authorization_number"]


def test_cob_loop_does_not_leak(parsed, generated):
    _, key = generated
    claims = _ok_claims(parsed)
    cob = [c for c in key["claims"] if c["has_cob"]]
    assert cob, "fixture must contain COB claims"
    for c in cob:
        row = claims[c["patient_control_number"]]
        assert row["payer_claim_control_number"] is None  # REF*F8 lives in 2330B
        assert row["member_id"] != "OTHERMEMBER1"


def test_patient_loop_does_not_carry_into_the_next_subscriber(parsed, generated):
    _, key = generated
    claims = _ok_claims(parsed)
    assert any(not c["patient_is_subscriber"] for c in key["claims"])
    for c in key["claims"]:
        row = claims[c["patient_control_number"]]
        assert row["patient_is_subscriber"] == c["patient_is_subscriber"]
        assert row["patient_birth_date"] == _d(c["patient_birth_date"])
        assert row["patient_gender"] == c["patient_gender"]
        assert row["subscriber_birth_date"] == _d(c["subscriber_birth_date"])


def test_diagnoses_in_order_with_principal_first(parsed, generated):
    _, key = generated
    claims = _ok_claims(parsed)
    by_claim = defaultdict(list)
    for r in parsed["dx"]:
        by_claim[r["claim_id"]].append(r)
    for c in key["claims"]:
        row = claims[c["patient_control_number"]]
        assert row["principal_diagnosis_code"] == c["principal_diagnosis_code"]
        assert row["diagnosis_codes"] == c["diagnosis_codes"]
        dx = sorted(by_claim[row["claim_id"]], key=lambda r: r["diagnosis_sequence"])
        assert [r["diagnosis_code"] for r in dx] == c["diagnosis_codes"]
        assert [r["is_principal"] for r in dx] == [True] + [False] * (len(dx) - 1)


def test_institutional_fields(parsed, generated):
    _, key = generated
    claims = _ok_claims(parsed)
    inst = [c for c in key["claims"] if c["claim_type"] == "institutional"]
    assert inst
    for c in inst:
        row = claims[c["patient_control_number"]]
        assert row["type_of_bill"] == c["type_of_bill"]
        assert row["drg_code"] == c["drg_code"]
        assert row["statement_from_date"] == _d(c["statement_from_date"])
        assert row["statement_to_date"] == _d(c["statement_to_date"])
        assert row["service_from_date"] == row["statement_from_date"]
        assert row["place_of_service_code"] is None


def test_lines(parsed, generated):
    _, key = generated
    claims = _ok_claims(parsed)
    lines = defaultdict(dict)
    for r in parsed["lines"]:
        lines[r["claim_id"]][r["line_number"]] = r
    for c in key["claims"]:
        row = claims[c["patient_control_number"]]
        got = lines[row["claim_id"]]
        assert set(got) == {ln["line_number"] for ln in c["lines"]}
        for ln in c["lines"]:
            g = got[ln["line_number"]]
            assert g["procedure_code"] == ln["procedure_code"]
            assert g["revenue_code"] == ln["revenue_code"]
            assert (g["procedure_modifiers"] or []) == ln["modifiers"]
            assert g["line_charge_amount"] == Decimal(str(ln["charge"])).quantize(Decimal("0.01"))
            assert g["service_units"] == Decimal(ln["units"])
            assert g["service_from_date"] == _d(ln["service_date"])
            assert g["diagnosis_pointers"] == ln["diagnosis_pointers"]
        if c["claim_type"] == "professional":
            assert row["place_of_service_code"] == "11"
            assert row["service_from_date"] == min(_d(ln["service_date"]) for ln in c["lines"])


def test_bad_values_become_null_not_errors(spark, generated):
    """ANSI mode: a non-numeric charge or bad date must yield NULL, not fail the job."""
    import x12_837

    files, _ = generated
    broken = files["prof_basic.x12"].replace("CLM*PCN000001*190*", "CLM*PCN000001*ABC*", 1)
    broken = broken.replace("DTP*472*D8*2026", "DTP*472*D8*XX26", 1)
    raw = spark.createDataFrame([("/synthetic/broken.x12", broken)], "file_path string, value string")
    claims = x12_837.parse_837(x12_837.segments(raw))["claims"].collect()
    row = next(r for r in claims if r["patient_control_number"] == "PCN000001")
    assert row["total_charge_amount"] is None


def test_claim_id_ignores_dbfs_prefix(spark, generated):
    """Batch reads report dbfs:/Volumes/..., Auto Loader /Volumes/...: the same file must get the same ids."""
    import x12_837

    files, _ = generated
    content = files["prof_basic.x12"]
    ids = []
    for path in ["dbfs:/Volumes/c/s/v/837/prof_basic.x12", "/Volumes/c/s/v/837/prof_basic.x12"]:
        raw = spark.createDataFrame([(path, content)], "file_path string, value string")
        ids.append(sorted(r["claim_id"] for r in x12_837.parse_837(x12_837.segments(raw))["claims"].collect()))
    assert ids[0] == ids[1]


def test_module_is_serverless_safe():
    """No UDFs, RDDs, SparkContext or Arrow/pandas mapping: these fail or are unsupported on serverless."""
    src = SCRIPT.read_text()
    for pattern in [r"\budf\b", r"pandas_udf", r"\.rdd\b", r"sparkContext", r"mapInArrow", r"mapInPandas",
                    r"\.cache\(", r"\.persist\(", r"^import (?!__future__)(?!pyspark)", r"^from (?!__future__)(?!pyspark)"]:
        assert not re.search(pattern, src, re.M), pattern
