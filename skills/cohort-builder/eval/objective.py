"""Cohort-builder objective function -- rolls scorers into one scalar in [0, 1].

    COHORT_SCORE = 0.45 * membership_F1          # right patients (headline)
                 + 0.20 * conceptset_F1          # right codes, with descendants
                 + 0.20 * feasibility_calibration# predicted N vs actual N
                 + 0.15 * citation_validity      # citations that resolve & support
                 - LAMBDA * hallucination_rate   # invented codes/citations, near-gate

Score clamped to [0, 1]. Runnable today with a CohortGold + CohortOutput.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# Make the sibling scorers module importable no matter the CWD or how this is loaded.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scorers import (  # noqa: E402
    CohortGold, CohortOutput, membership_f1, conceptset_f1,
    feasibility_calibration, build_decision_correct, citation_validity,
)

# Default weights (kept per decision). Positive weights sum to 1.0; LAMBDA is a penalty.
W_MEMBERSHIP = 0.45
W_CONCEPTSET = 0.20
W_FEASIBILITY = 0.20
W_CITATION = 0.15
LAMBDA_HALLUCINATION = 0.50   # heavy: a phenotype "supported" by a fake PMID is worse than none


@dataclass
class CohortObjective:
    score: float
    build_decision_correct: bool
    breakdown: dict


def cohort_objective(gold: CohortGold, out: CohortOutput, resolver=None) -> CohortObjective:
    mem = membership_f1(gold, out)
    cs = conceptset_f1(gold, out)
    feas = feasibility_calibration(gold, out)
    cite = citation_validity(out, resolver=resolver)
    decision_ok = build_decision_correct(gold, out)

    raw = (W_MEMBERSHIP * mem["f1"]
           + W_CONCEPTSET * cs["f1"]
           + W_FEASIBILITY * feas
           + W_CITATION * cite["validity"]
           - LAMBDA_HALLUCINATION * cite["hallucination_rate"])
    score = max(0.0, min(1.0, raw))

    breakdown = {
        "membership_f1": mem["f1"], "membership": mem,
        "conceptset_f1": cs["f1"],
        "feasibility_calibration": feas,
        "citation_validity": cite["validity"],
        "hallucination_rate": cite["hallucination_rate"],
        "build_decision_correct": decision_ok,
    }
    return CohortObjective(score=round(score, 4),
                           build_decision_correct=decision_ok,
                           breakdown=breakdown)


if __name__ == "__main__":
    gold = CohortGold(
        true_members={"p1", "p2", "p3", "p4"},
        all_patients={f"p{i}" for i in range(1, 21)},
        reference_codes={("ICD10CM", "E11.9"), ("ICD10CM", "E11.65"), ("LOINC", "4548-4")},
        actual_feasible_n=4,
        should_build=True,
    )
    good = CohortOutput(
        predicted_members={"p1", "p2", "p3", "p4"},
        resolved_codes={("ICD10CM", "E11.9"), ("ICD10CM", "E11.65"), ("LOINC", "4548-4")},
        predicted_n=4, decided_to_build=True,
        citations=["PMID:29435101", "NCT01234567"],
    )
    hallucinated = CohortOutput(
        predicted_members={"p1", "p2", "p3"},          # missed p4
        resolved_codes={("ICD10CM", "E11.9")},         # incomplete concept set
        predicted_n=12, decided_to_build=True,         # bad feasibility estimate
        citations=["PMID:notreal", "PMID:29435101"],   # one hallucinated
    )
    print("good:        ", cohort_objective(gold, good))
    print("hallucinated:", cohort_objective(gold, hallucinated))
