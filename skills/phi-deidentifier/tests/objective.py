"""De-identifier objective function -- rolls scorers into one scalar in [0, 1].

Gated, recall-weighted design (asymmetric on purpose):
    - ANY residual PHI leak -> score 0. A single leaked identifier fails the run
      outright, no matter how good everything else is.
    - Otherwise: 0.60 * F2(recall, precision)      # recall weighted 4x precision
               + 0.25 * utility_retention          # analytic value preserved
               + 0.15 * min(k_anonymity / k_target, 1)

Runnable today: give it a DeidGold + DeidOutput and it returns a number + breakdown.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# Make the sibling scorers module importable no matter the CWD or how this is loaded.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scorers import (  # noqa: E402
    DeidGold, DeidOutput, detection_recall, residual_leaks, utility_retention,
    governance_score, f_beta,
)

# Weights re-set after the baseline exposed two objective flaws:
#  - utility was multiplicative (interval loss zeroed everything) -> now graded/additive
#  - governance (view-over-raw + raw-not-exposed) had ZERO weight while being THE gap
#    baseline Genie showed (physical copy + exposed raw PHI). Now a first-class term.
# Sum of non-gate weights = 1.0.
W_F2 = 0.45          # detection quality (recall-weighted); direct-ID stripping is table stakes
W_UTILITY = 0.20     # graded analytic value retained
W_KANON = 0.15       # re-identification resistance
W_GOVERNANCE = 0.20  # enforced via governed view, raw PHI not left exposed
K_TARGET = 5
BETA = 2.0


@dataclass
class DeidObjective:
    score: float
    leaked: bool
    breakdown: dict


def deid_objective(gold: DeidGold, out: DeidOutput) -> DeidObjective:
    leaks = residual_leaks(out)
    det = detection_recall(gold, out)
    f2 = f_beta(det["precision"], det["recall"], beta=BETA)
    util = utility_retention(gold, out)
    kterm = min(out.k_anonymity / K_TARGET, 1.0) if K_TARGET else 1.0
    gov = governance_score(out)

    breakdown = {
        "residual_leaks": leaks,
        "precision": det["precision"], "recall": det["recall"],
        "per_class_recall": det["per_class_recall"],
        "f2": f2, "utility_retention": util,
        "k_anonymity": out.k_anonymity, "k_term": kterm,
        "governance": gov,
    }

    if leaks > 0:
        return DeidObjective(score=0.0, leaked=True, breakdown=breakdown)

    score = W_F2 * f2 + W_UTILITY * util + W_KANON * kterm + W_GOVERNANCE * gov
    return DeidObjective(score=round(score, 4), leaked=False, breakdown=breakdown)


if __name__ == "__main__":
    # Smoke test with a tiny hand-built gold/output so the math is verifiable.
    from scorers import PhiSpan
    gold = DeidGold(
        injected=[
            PhiSpan("r1", "ssn", "ssn", "123-45-6789"),
            PhiSpan("r1", "email", "email", "a@b.com"),
            PhiSpan("r2", "ssn", "ssn", "987-65-4321"),
        ],
        analytic_columns=["age_band", "hba1c"],
        intervals=[("p1", "admit", "discharge", 4)],
    )
    # A genuinely perfect run: all PHI handled, no leak, full analytic fidelity,
    # k>=target, AND governed (view over raw + raw not exposed) -> expect score 1.0.
    perfect = DeidOutput(
        transformed_cells={("r1", "ssn"), ("r1", "email"), ("r2", "ssn")},
        residual_phi_cells=set(),
        surviving_analytic_columns=["age_band", "hba1c"],
        analytic_fidelity={"age_band": "full", "hba1c": "full"},
        preserved_intervals=[("p1", "admit", "discharge", 4)],
        k_anonymity=7,
        is_view_over_raw=True, raw_phi_still_exposed=False,
    )
    # Same quality, but written as a physical COPY with raw PHI left exposed (baseline
    # behavior) -> governance term = 0, so it scores lower despite identical de-id quality.
    ungoverned = DeidOutput(
        transformed_cells={("r1", "ssn"), ("r1", "email"), ("r2", "ssn")},
        residual_phi_cells=set(),
        surviving_analytic_columns=["age_band", "hba1c"],
        analytic_fidelity={"age_band": "full", "hba1c": "full"},
        preserved_intervals=[("p1", "admit", "discharge", 4)],
        k_anonymity=7,
        is_view_over_raw=False, raw_phi_still_exposed=True,
    )
    leaky = DeidOutput(
        transformed_cells={("r1", "ssn"), ("r1", "email")},   # missed r2 ssn
        residual_phi_cells={("r2", "ssn")},                    # ...and it shows in output
        surviving_analytic_columns=["age_band", "hba1c"],
        preserved_intervals=[("p1", "admit", "discharge", 4)],
        k_anonymity=7,
        is_view_over_raw=True, raw_phi_still_exposed=False,
    )
    print("perfect (governed):  ", deid_objective(gold, perfect).score, "(expect 1.0)")
    print("ungoverned (copy):   ", deid_objective(gold, ungoverned).score, "(expect 0.8 — governance gap)")
    print("leaky (gate):        ", deid_objective(gold, leaky).score, "(expect 0.0 — leak gate)")
