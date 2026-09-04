"""Unit tests for the de-identifier component scorers + objective.

These guard the MEASUREMENT code itself — the thing the whole skill's credibility rests on
(a scorer bug would silently shift every downstream number). Pure Python, offline,
sub-second. Fixtures are hand-computed so a refactor that changes the math fails loudly
instead of drifting.
"""

from __future__ import annotations

import pytest


# --- f_beta -------------------------------------------------------------------

def test_f_beta_perfect(deid):
    s, _ = deid
    assert s.f_beta(1.0, 1.0, beta=2.0) == 1.0


def test_f_beta_zero_denominator_guarded(deid):
    s, _ = deid
    # precision=recall=0 -> denom 0 -> must return 0.0, not raise
    assert s.f_beta(0.0, 0.0, beta=2.0) == 0.0


def test_f_beta_recall_weighted_4x(deid):
    s, _ = deid
    # beta=2 weights recall 4x precision: low precision + high recall should beat the
    # symmetric mean of the two. p=0.5, r=1.0 -> F2 = 5*0.5*1 / (4*0.5 + 1) = 2.5/3 = 0.8333
    f2 = s.f_beta(0.5, 1.0, beta=2.0)
    assert f2 == pytest.approx(0.8333, abs=1e-4)
    assert f2 > (0.5 + 1.0) / 2  # recall-favoring


# --- _prf / detection_recall --------------------------------------------------

def test_prf_empty_is_one(deid):
    s, _ = deid
    # no injected PHI and nothing transformed -> vacuously perfect (guards div-by-zero)
    assert s._prf(0, 0, 0) == (1.0, 1.0)


def test_detection_recall_per_cell_and_per_class(deid):
    s, _ = deid
    gold = s.DeidGold(
        injected=[
            s.PhiSpan("r1", "ssn", "ssn", "111"),
            s.PhiSpan("r2", "ssn", "ssn", "222"),
            s.PhiSpan("r1", "email", "email", "a@b.com"),
        ],
        analytic_columns=[],
    )
    # transformed both SSN cells but MISSED the email cell; also over-redacted a non-PHI cell
    out = s.DeidOutput(transformed_cells={("r1", "ssn"), ("r2", "ssn"), ("r9", "age")})
    det = s.detection_recall(gold, out)
    assert det["tp"] == 2 and det["fn"] == 1 and det["fp"] == 1
    assert det["recall"] == pytest.approx(2 / 3)      # 2 of 3 PHI cells caught
    assert det["precision"] == pytest.approx(2 / 3)   # 2 of 3 transformed cells were real PHI
    # per-class: ssn fully caught (2/2), email missed (0/1)
    assert det["per_class_recall"]["ssn"] == 1.0
    assert det["per_class_recall"]["email"] == 0.0


# --- residual_leaks (the gate) ------------------------------------------------

def test_residual_leaks_counts_cells(deid):
    s, _ = deid
    out = s.DeidOutput(residual_phi_cells={("r1", "ssn"), ("r2", "ssn")})
    assert s.residual_leaks(out) == 2


# --- utility_retention: ADDITIVE, not multiplicative --------------------------

def test_utility_partial_column_credit(deid):
    s, _ = deid
    gold = s.DeidGold(injected=[], analytic_columns=["a", "b"])
    # one full column, one dropped, no intervals -> col_keep = (1.0 + 0)/2 = 0.5,
    # interval_keep vacuously 1.0 -> (0.5 + 1.0)/2 = 0.75
    out = s.DeidOutput(surviving_analytic_columns=["a"], analytic_fidelity={"a": "full"})
    assert s.utility_retention(gold, out) == pytest.approx(0.75)


def test_utility_generalized_earns_half(deid):
    s, _ = deid
    gold = s.DeidGold(injected=[], analytic_columns=["a"])
    out = s.DeidOutput(surviving_analytic_columns=["a"], analytic_fidelity={"a": "generalized"})
    # generalized col=0.5, intervals vacuous 1.0 -> (0.5 + 1.0)/2 = 0.75
    assert s.utility_retention(gold, out) == pytest.approx(0.75)


def test_utility_is_additive_not_multiplicative(deid):
    s, _ = deid
    # THE regression this guards: losing intervals must NOT zero the whole utility term
    # (the original multiplicative bug). Full columns + lost intervals should stay > 0.
    gold = s.DeidGold(injected=[], analytic_columns=["a"],
                      intervals=[("p1", "admit", "discharge", 4)])
    out = s.DeidOutput(surviving_analytic_columns=["a"], analytic_fidelity={"a": "full"},
                       preserved_intervals=[])  # interval lost
    u = s.utility_retention(gold, out)
    assert u == pytest.approx(0.5)   # (col 1.0 + interval 0.0)/2 — NOT 0.0
    assert u > 0.0


def test_utility_generalized_interval_half_credit(deid):
    s, _ = deid
    gold = s.DeidGold(injected=[], analytic_columns=[],
                      intervals=[("p1", "admit", "discharge", 4)])
    out = s.DeidOutput(preserved_intervals=[], interval_generalized=True)
    # col vacuous 1.0, interval bucketed -> 0.5 -> (1.0 + 0.5)/2 = 0.75
    assert s.utility_retention(gold, out) == pytest.approx(0.75)


# --- governance_score: the two-boolean term ----------------------------------

@pytest.mark.parametrize("view,exposed,expected", [
    (True, False, 1.0),   # view over raw + source restricted = full credit
    (True, True, 0.5),    # view but raw still exposed
    (False, False, 0.5),  # source restricted but it's a physical copy
    (False, True, 0.0),   # baseline: physical copy + raw PHI exposed
])
def test_governance_score(deid, view, exposed, expected):
    s, _ = deid
    out = s.DeidOutput(is_view_over_raw=view, raw_phi_still_exposed=exposed)
    assert s.governance_score(out) == expected


# --- objective assembly (the smoke test, now ASSERTED) ------------------------

def _gold(s):
    return s.DeidGold(
        injected=[s.PhiSpan("r1", "ssn", "ssn", "1"), s.PhiSpan("r1", "email", "email", "a@b"),
                  s.PhiSpan("r2", "ssn", "ssn", "2")],
        analytic_columns=["age_band", "hba1c"],
        intervals=[("p1", "admit", "discharge", 4)],
    )


def test_objective_perfect_governed_is_one(deid):
    s, o = deid
    perfect = s.DeidOutput(
        transformed_cells={("r1", "ssn"), ("r1", "email"), ("r2", "ssn")},
        residual_phi_cells=set(),
        surviving_analytic_columns=["age_band", "hba1c"],
        analytic_fidelity={"age_band": "full", "hba1c": "full"},
        preserved_intervals=[("p1", "admit", "discharge", 4)],
        k_anonymity=7, is_view_over_raw=True, raw_phi_still_exposed=False)
    res = o.deid_objective(_gold(s), perfect)
    assert res.score == 1.0 and res.leaked is False


def test_objective_ungoverned_copy_docks_governance(deid):
    s, o = deid
    ungoverned = s.DeidOutput(
        transformed_cells={("r1", "ssn"), ("r1", "email"), ("r2", "ssn")},
        residual_phi_cells=set(),
        surviving_analytic_columns=["age_band", "hba1c"],
        analytic_fidelity={"age_band": "full", "hba1c": "full"},
        preserved_intervals=[("p1", "admit", "discharge", 4)],
        k_anonymity=7, is_view_over_raw=False, raw_phi_still_exposed=True)
    res = o.deid_objective(_gold(s), ungoverned)
    assert res.score == pytest.approx(0.8)   # loses the full 0.20 governance term


def test_objective_leak_gate_forces_zero(deid):
    s, o = deid
    leaky = s.DeidOutput(
        transformed_cells={("r1", "ssn"), ("r1", "email")},   # missed r2 ssn
        residual_phi_cells={("r2", "ssn")},                    # ...and it leaked
        surviving_analytic_columns=["age_band", "hba1c"],
        preserved_intervals=[("p1", "admit", "discharge", 4)],
        k_anonymity=7, is_view_over_raw=True, raw_phi_still_exposed=False)
    res = o.deid_objective(_gold(s), leaky)
    assert res.score == 0.0 and res.leaked is True


def test_objective_weights_sum_to_one(deid):
    _, o = deid
    assert o.W_F2 + o.W_UTILITY + o.W_KANON + o.W_GOVERNANCE == pytest.approx(1.0)
