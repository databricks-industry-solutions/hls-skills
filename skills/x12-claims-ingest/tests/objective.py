"""x12-claims-ingest objective function: rolls the scorers into one scalar in [0, 1].

Gated design, like phi-deidentifier's leak gate:
    - ANY claim from a truncated / invalid transaction loaded into the main claims table without a
      flag -> score 0. Silently loading partial claims is the failure that hurts a payer most: the
      numbers look complete and are wrong.
    - A run that loads no valid claims -> score 0 (no credit for terms that do not apply).

v1 (ingest_objective, PINNED as a regression baseline: do not change these weights; add a v2):
    - Otherwise: 0.30 * claim_set_F1         # the right claims, no extras
               + 0.30 * field_accuracy       # member, payer, billing NPI, billed amount, principal dx,
                                             # patient DOB / gender (COB and patient-loop traps)
               + 0.15 * line_accuracy        # procedure / revenue code, charge, units, service date
               + 0.15 * validation_reporting # truncated and non-X12 files identified
               + 0.10 * ran_where_asked      # requested job / pipeline actually completed

v2 (ingest_objective_v2, pre-registered 2026-10-19 before any v2 eval run): identical to v1 on tasks
without planted quality defects. On quality tasks it adds the detection F1 of (claim, rule) flags:
                 0.25 * claim_set_F1 + 0.25 * field_accuracy + 0.10 * line_accuracy
               + 0.10 * validation_reporting + 0.05 * ran_where_asked + 0.25 * quality_detection_F1
Same gates as v1.

Runnable today: give it an IngestGold + IngestOutput and it returns a number + breakdown.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# Make the sibling scorers module importable no matter the CWD or how this is loaded.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ingest_scorers import (  # noqa: E402
    IngestGold, IngestOutput, claim_set_f1, field_accuracy, line_accuracy, quality_detection, ran_where_asked,
    silent_bad_loads, validation_reporting,
)

# --- v1 weights (PINNED). Sum to 1.0 ---
W_CLAIMS = 0.30
W_FIELDS = 0.30
W_LINES = 0.15
W_VALIDATION = 0.15
W_RUN = 0.10

# --- v2 weights for quality tasks (PINNED). Sum to 1.0 ---
W2_CLAIMS, W2_FIELDS, W2_LINES, W2_VALIDATION, W2_RUN, W2_QUALITY = 0.25, 0.25, 0.10, 0.10, 0.05, 0.25


@dataclass
class IngestObjective:
    score: float
    gated: bool
    breakdown: dict
    gate_reason: str | None = None


def ingest_objective(gold: IngestGold, out: IngestOutput) -> IngestObjective:
    bad = silent_bad_loads(gold, out)
    cs = claim_set_f1(gold, out)
    fa = field_accuracy(gold, out)
    la = line_accuracy(gold, out)
    vr = validation_reporting(gold, out)
    rw = ran_where_asked(gold, out)
    breakdown = {
        "silent_bad_loads": bad,
        "claim_precision": cs["precision"], "claim_recall": cs["recall"], "claim_f1": cs["f1"],
        "field_accuracy": fa["accuracy"], "per_field_accuracy": fa["per_field"],
        "line_accuracy": la, "validation_reporting": vr, "ran_where_asked": rw,
    }
    if bad > 0:
        return IngestObjective(score=0.0, gated=True, breakdown=breakdown, gate_reason="silent_bad_load")
    if cs["recall"] == 0:
        return IngestObjective(score=0.0, gated=True, breakdown=breakdown, gate_reason="nothing_loaded")
    score = W_CLAIMS * cs["f1"] + W_FIELDS * fa["accuracy"] + W_LINES * la + W_VALIDATION * vr + W_RUN * rw
    return IngestObjective(score=round(score, 4), gated=False, breakdown=breakdown)


def ingest_objective_v2(gold: IngestGold, out: IngestOutput) -> IngestObjective:
    v1 = ingest_objective(gold, out)
    q = quality_detection(gold, out)
    breakdown = {**v1.breakdown, "quality_precision": q["precision"], "quality_recall": q["recall"],
                 "quality_f1": q["f1"], "quality_applicable": q["applicable"]}
    if v1.gated or not q["applicable"]:
        return IngestObjective(score=v1.score, gated=v1.gated, breakdown=breakdown, gate_reason=v1.gate_reason)
    b = v1.breakdown
    score = (W2_CLAIMS * b["claim_f1"] + W2_FIELDS * b["field_accuracy"] + W2_LINES * b["line_accuracy"]
             + W2_VALIDATION * b["validation_reporting"] + W2_RUN * b["ran_where_asked"] + W2_QUALITY * q["f1"])
    return IngestObjective(score=round(score, 4), gated=False, breakdown=breakdown)


if __name__ == "__main__":
    # Smoke test: one claim with one line, one truncated claim, one bad file.
    gold = IngestGold(
        claims={"PCN1": {"member_id": "M1", "payer_id": "PAY01", "billing_provider_npi": "1111111111",
                         "total_charge_amount": "100.00", "principal_diagnosis_code": "E119",
                         "patient_birth_date": "1980-01-01", "patient_gender": "F"}},
        lines={"PCN1": {1: {"procedure_code": "99213", "revenue_code": None, "line_charge_amount": "100.00",
                            "service_units": "1.00", "service_date": "2026-09-01"}}},
        bad_files={"truncated.x12"}, invalid_pcns={"PCN9"},
    )
    perfect = IngestOutput(claims={"PCN1": dict(gold.claims["PCN1"])}, lines={"PCN1": dict(gold.lines["PCN1"])},
                           reported_bad_files={"truncated.x12"})
    unreported = IngestOutput(claims=perfect.claims, lines=perfect.lines)
    silent = IngestOutput(claims={**perfect.claims, "PCN9": {}}, lines=perfect.lines,
                          reported_bad_files={"truncated.x12"})
    print("perfect:          ", ingest_objective(gold, perfect).score, "(expect 1.0)")
    print("bad file missed:  ", ingest_objective(gold, unreported).score, "(expect 0.85)")
    print("silent bad load:  ", ingest_objective(gold, silent).score, "(expect 0.0, gated)")
