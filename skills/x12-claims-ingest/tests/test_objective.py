"""Objective-function tests: the math, the gate, and that the skill's own parser scores 1.0."""

from __future__ import annotations

import copy

import pytest

from ingest_scorers import (
    CLAIM_FIELDS, IngestOutput, field_accuracy, gold_from_key, output_from_records, silent_bad_loads,
)
from objective import W_FIELDS, W_VALIDATION, ingest_objective


def _perfect_rows(key):
    """Contract-shaped rows that reproduce the answer key exactly."""
    claims, lines = [], []
    for c in key["claims"]:
        claims.append({"patient_control_number": c["patient_control_number"], **{f: c.get(f) for f in CLAIM_FIELDS}})
        for ln in c["lines"]:
            lines.append({"patient_control_number": c["patient_control_number"], "line_number": ln["line_number"],
                          "procedure_code": ln["procedure_code"], "revenue_code": ln["revenue_code"],
                          "line_charge_amount": ln["charge"], "service_units": ln["units"],
                          "service_date": ln["service_date"]})
    checks = [{"file_name": t["file"], "status": t["transaction_status"]} for t in key["transactions"]]
    return claims, lines, checks


def test_perfect_output_scores_one(generated):
    _, key = generated
    gold = gold_from_key(key)
    obj = ingest_objective(gold, output_from_records(*_perfect_rows(key)))
    assert obj.score == 1.0 and not obj.gated


def test_silent_partial_load_is_gated_to_zero(generated):
    _, key = generated
    gold = gold_from_key(key)
    claims, lines, checks = _perfect_rows(key)
    claims.append({"patient_control_number": key["truncated_claims"][0], "member_id": "X"})
    obj = ingest_objective(gold, output_from_records(claims, lines, checks))
    assert obj.gated and obj.score == 0.0


def test_flagged_partial_load_is_not_gated(generated):
    _, key = generated
    gold = gold_from_key(key)
    claims, lines, checks = _perfect_rows(key)
    for c in claims:
        c["status"] = "ok"
    claims.append({"patient_control_number": key["truncated_claims"][0], "status": "missing_SE"})
    out = output_from_records(claims, lines, checks)
    assert silent_bad_loads(gold, out) == 0
    assert ingest_objective(gold, out).score == 1.0


def test_cob_payer_leak_costs_field_accuracy(generated):
    """Naive parser: the 2330B other-payer NM1*PR overwrites the primary payer on COB claims."""
    _, key = generated
    gold = gold_from_key(key)
    leaked = copy.deepcopy(key)
    cob = [c for c in leaked["claims"] if c["has_cob"]]
    for c in cob:
        c["payer_id"] = "OTHER99"
    out = output_from_records(*_perfect_rows(leaked))
    fa = field_accuracy(gold, out)
    expected_payer_acc = 1 - len(cob) / len(key["claims"])
    assert fa["per_field"]["payer_id"] == pytest.approx(expected_payer_acc)
    expected = 1.0 - W_FIELDS * (1 - expected_payer_acc) / len(CLAIM_FIELDS)
    assert ingest_objective(gold, out).score == pytest.approx(expected, abs=1e-4)


def test_patient_carry_over_costs_field_accuracy(generated):
    """Naive parser: the 2000C patient DOB carries into the next subscriber's claim."""
    _, key = generated
    gold = gold_from_key(key)
    carried = copy.deepcopy(key)
    claims = carried["claims"]
    hit = 0
    for prev, cur in zip(claims, claims[1:]):
        if not prev["patient_is_subscriber"] and cur["patient_is_subscriber"] and prev["file"] == cur["file"]:
            cur["patient_birth_date"] = prev["patient_birth_date"]
            hit += 1
    assert hit, "fixture must contain a patient loop followed by a subscriber-only claim"
    out = output_from_records(*_perfect_rows(carried))
    assert field_accuracy(gold, out)["per_field"]["patient_birth_date"] < 1.0
    assert ingest_objective(gold, out).score < 1.0


def test_unreported_bad_files_cost_validation_weight(generated):
    _, key = generated
    gold = gold_from_key(key)
    claims, lines, _ = _perfect_rows(key)
    obj = ingest_objective(gold, output_from_records(claims, lines, []))
    assert obj.score == pytest.approx(1.0 - W_VALIDATION)


def test_requested_run_that_did_not_complete(generated):
    _, key = generated
    gold = gold_from_key(key, requires_run=True)
    assert ingest_objective(gold, output_from_records(*_perfect_rows(key), ran_where_asked=False)).score == pytest.approx(0.9)
    assert ingest_objective(gold, output_from_records(*_perfect_rows(key), ran_where_asked=True)).score == 1.0


def test_empty_output_is_gated_to_zero(generated):
    _, key = generated
    obj = ingest_objective(gold_from_key(key), IngestOutput())
    assert obj.gated and obj.gate_reason == "nothing_loaded" and obj.score == 0.0


def test_missing_lines_score_zero_even_where_key_is_blank(generated):
    """837P lines have no revenue code; a run with no lines must not get credit for that blank."""
    from ingest_scorers import line_accuracy

    _, key = generated
    claims, _, checks = _perfect_rows(key)
    assert line_accuracy(gold_from_key(key), output_from_records(claims, [], checks)) == 0.0


def test_objective_survives_json_round_trip(generated):
    """The scoring notebook rebuilds outputs from JSON; the score must not change."""
    import json

    from ingest_scorers import to_jsonable

    _, key = generated
    gold = gold_from_key(key)
    out = output_from_records(*_perfect_rows(key))
    d = json.loads(json.dumps(to_jsonable(out)))
    rebuilt = IngestOutput(claims=d["claims"], flagged_pcns=set(d["flagged_pcns"]),
                           reported_bad_files=set(d["reported_bad_files"]), ran_where_asked=d["ran_where_asked"],
                           lines={p: {int(k): v for k, v in ls.items()} for p, ls in d["lines"].items()})
    assert ingest_objective(gold, rebuilt).score == 1.0


def test_skill_parser_scores_one(parsed, generated):
    """End to end: the skill's own parser output, mapped to the contract, reproduces the key."""
    _, key = generated
    claims = [dict(r.asDict(), status=r["transaction_status"]) for r in parsed["claims"].values()]
    pcn_by_id = {r["claim_id"]: r["patient_control_number"] for r in parsed["claims"].values()}
    lines = [dict(r.asDict(), patient_control_number=pcn_by_id[r["claim_id"]], service_date=r["service_from_date"])
             for r in parsed["lines"]]
    checks = [{"file_name": r["file_path"], "status": r["transaction_status"]} for r in parsed["checks"]]
    obj = ingest_objective(gold_from_key(key), output_from_records(claims, lines, checks))
    assert obj.score == 1.0, obj.breakdown


def test_mlflow_scorers_are_binary(generated):
    pytest.importorskip("mlflow")
    from ingest_scorers import mlflow_scorers, to_jsonable

    _, key = generated
    gold = to_jsonable(gold_from_key(key))
    out = to_jsonable(output_from_records(*_perfect_rows(key)))
    for s in mlflow_scorers():
        value = s(outputs={"ingest_output": out}, expectations={"ingest_gold": gold})
        assert value is True, s.name
