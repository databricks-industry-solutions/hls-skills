"""De-identifier objective function -- rolls scorers into one scalar in [0, 1].

Gated, recall-weighted design (asymmetric on purpose):
    - ANY residual PHI leak -> score 0. A single leaked identifier fails the run
      outright, no matter how good everything else is.

v1 (deid_objective, PINNED as a regression baseline -- do not change its weights):
    - Otherwise: 0.45 * F2(recall, precision)      # recall weighted 4x precision
               + 0.20 * utility_retention          # analytic value preserved (graded)
               + 0.15 * min(k_anonymity / k_target, 1)
               + 0.20 * governance                 # view-over-raw + raw-not-exposed

v2 (deid_objective_v2, multimodal + richer interaction):
    - Leak gate expands to ANY modality (structured cell OR parsed-doc/pixel region).
    - Otherwise: 0.35 * F2  + 0.15 * utility + 0.10 * k_term
               + 0.20 * governance_v2 (3-part: view + raw-not-exposed + reversible locked crosswalk)
               + 0.10 * interaction_fidelity + 0.10 * modality_coverage

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
    governance_score, governance_score_v2, interaction_fidelity, modality_coverage, f_beta,
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

# --- v2 weights (multimodal + richer interaction). Non-gate weights sum to 1.0 ---
# F2 and utility make room for two new terms; governance stays 0.20 but is now the 3-part
# governance_score_v2 (adds the reversible locked crosswalk). interaction_fidelity rewards
# surfacing the strategy choices; modality_coverage penalizes silently skipping a modality.
W2_F2 = 0.35
W2_UTILITY = 0.15
W2_KANON = 0.10
W2_GOVERNANCE = 0.20
W2_INTERACTION = 0.10
W2_MODALITY = 0.10


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


def deid_objective_v2(gold: DeidGold, out: DeidOutput) -> DeidObjective:
    """v2 objective: modality-aware leak gate + 3-part governance + interaction_fidelity +
    modality_coverage. v1 (deid_objective) is untouched so its pinned numbers hold.

    The leak gate (residual_leaks) now counts structured residual cells AND unstructured
    residual regions (burned-in pixel text / unredacted parsed-doc spans): any -> 0.
    """
    leaks = residual_leaks(out)             # region-aware
    det = detection_recall(gold, out)       # region-aware
    f2 = f_beta(det["precision"], det["recall"], beta=BETA)
    util = utility_retention(gold, out)
    kterm = min(out.k_anonymity / K_TARGET, 1.0) if K_TARGET else 1.0
    gov = governance_score_v2(out)
    interact = interaction_fidelity(gold, out)
    modcov = modality_coverage(gold, out)

    breakdown = {
        "residual_leaks": leaks,
        "precision": det["precision"], "recall": det["recall"],
        "per_class_recall": det["per_class_recall"],
        "f2": f2, "utility_retention": util,
        "k_anonymity": out.k_anonymity, "k_term": kterm,
        "governance_v2": gov,
        "interaction_fidelity": interact["fidelity"], "interaction_detail": interact,
        "modality_coverage": modcov["coverage"], "modality_detail": modcov,
    }

    if leaks > 0:
        return DeidObjective(score=0.0, leaked=True, breakdown=breakdown)

    score = (W2_F2 * f2 + W2_UTILITY * util + W2_KANON * kterm + W2_GOVERNANCE * gov
             + W2_INTERACTION * interact["fidelity"] + W2_MODALITY * modcov["coverage"])
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
