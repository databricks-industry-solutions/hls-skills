"""Unit tests for the cohort-builder component scorers + objective.

Guards the measurement code: membership (per-patient), concept set (per-code), feasibility
calibration, citation validity, and the hallucination penalty that makes a fake-PMID cohort
score WORSE than a cohort with no citation at all. Pure Python, offline, sub-second.
"""

from __future__ import annotations

import pytest


# --- _f1 ----------------------------------------------------------------------

def test_f1_empty_sets_vacuously_perfect(cohort):
    s, _ = cohort
    r = s._f1(set(), set())
    assert r["f1"] == 1.0 and r["precision"] == 1.0 and r["recall"] == 1.0


def test_f1_partial(cohort):
    s, _ = cohort
    # pred {1,2,3}, truth {2,3,4}: tp=2, fp=1, fn=1 -> p=r=2/3 -> f1=2/3
    r = s._f1({"1", "2", "3"}, {"2", "3", "4"})
    assert r["tp"] == 2 and r["fp"] == 1 and r["fn"] == 1
    assert r["f1"] == pytest.approx(2 / 3)


# --- membership_f1 (per-patient, the headline) --------------------------------

def test_membership_baseline_recall_miss(cohort):
    s, _ = cohort
    # reproduce the baseline shape: perfect precision, missed members (silent threshold)
    truth = {f"p{i}" for i in range(86)}
    pred = {f"p{i}" for i in range(72)}   # missed 14
    gold = s.CohortGold(true_members=truth, all_patients=truth, reference_codes=set(),
                        actual_feasible_n=86)
    out = s.CohortOutput(predicted_members=pred)
    mem = s.membership_f1(gold, out)
    assert mem["precision"] == 1.0
    assert mem["recall"] == pytest.approx(72 / 86, abs=1e-4)   # ~0.837


# --- conceptset_f1 (per-code) -------------------------------------------------

def test_conceptset_incomplete(cohort):
    s, _ = cohort
    gold = s.CohortGold(true_members=set(), all_patients=set(),
                        reference_codes={("ICD10CM", "E11.9"), ("ICD10CM", "E11.65"), ("LOINC", "4548-4")},
                        actual_feasible_n=0)
    out = s.CohortOutput(resolved_codes={("ICD10CM", "E11.9")})   # only 1 of 3
    cs = s.conceptset_f1(gold, out)
    assert cs["recall"] == pytest.approx(1 / 3)
    assert cs["precision"] == 1.0   # the one it used is correct


# --- feasibility_calibration --------------------------------------------------

def test_feasibility_exact(cohort):
    s, _ = cohort
    gold = s.CohortGold(set(), set(), set(), actual_feasible_n=86)
    assert s.feasibility_calibration(gold, s.CohortOutput(predicted_n=86)) == 1.0


def test_feasibility_relative_error_clamped(cohort):
    s, _ = cohort
    gold = s.CohortGold(set(), set(), set(), actual_feasible_n=86)
    # predicted 43 -> rel err 0.5 -> calibration 0.5
    assert s.feasibility_calibration(gold, s.CohortOutput(predicted_n=43)) == pytest.approx(0.5)
    # wildly off -> clamped at 0, never negative
    assert s.feasibility_calibration(gold, s.CohortOutput(predicted_n=1000)) == 0.0


def test_feasibility_zero_actual_edge(cohort):
    s, _ = cohort
    gold = s.CohortGold(set(), set(), set(), actual_feasible_n=0)
    assert s.feasibility_calibration(gold, s.CohortOutput(predicted_n=0)) == 1.0
    assert s.feasibility_calibration(gold, s.CohortOutput(predicted_n=5)) == 0.0


# --- citation_validity / hallucination ----------------------------------------

def test_citation_none_is_valid(cohort):
    s, _ = cohort
    c = s.citation_validity(s.CohortOutput(citations=[]))
    assert c["validity"] == 1.0 and c["hallucination_rate"] == 0.0 and c["n"] == 0


def test_citation_format_default_resolver(cohort):
    s, _ = cohort
    # default offline resolver validates FORMAT only: one well-formed PMID, one junk
    c = s.citation_validity(s.CohortOutput(citations=["PMID:123", "garbage"]))
    assert c["validity"] == 0.5 and c["hallucination_rate"] == 0.5 and c["n"] == 2


def test_citation_custom_resolver(cohort):
    s, _ = cohort
    # a resolver that rejects everything -> full hallucination
    c = s.citation_validity(s.CohortOutput(citations=["PMID:123"]), resolver=lambda x: False)
    assert c["validity"] == 0.0 and c["hallucination_rate"] == 1.0


# --- build_decision_correct ---------------------------------------------------

@pytest.mark.parametrize("decided,should,ok", [
    (True, True, True), (False, False, True), (True, False, False), (False, True, False)])
def test_build_decision(cohort, decided, should, ok):
    s, _ = cohort
    gold = s.CohortGold(set(), set(), set(), actual_feasible_n=0, should_build=should)
    out = s.CohortOutput(decided_to_build=decided)
    assert s.build_decision_correct(gold, out) is ok


# --- objective assembly (smoke test, now ASSERTED) ----------------------------

def _gold(s):
    return s.CohortGold(
        true_members={"p1", "p2", "p3", "p4"}, all_patients={f"p{i}" for i in range(1, 21)},
        reference_codes={("ICD10CM", "E11.9"), ("ICD10CM", "E11.65"), ("LOINC", "4548-4")},
        actual_feasible_n=4, should_build=True)


def test_objective_clean_run_is_one(cohort):
    s, o = cohort
    good = s.CohortOutput(
        predicted_members={"p1", "p2", "p3", "p4"},
        resolved_codes={("ICD10CM", "E11.9"), ("ICD10CM", "E11.65"), ("LOINC", "4548-4")},
        predicted_n=4, decided_to_build=True, citations=["PMID:29435101", "NCT01234567"])
    res = o.cohort_objective(_gold(s), good)
    assert res.score == 1.0 and res.build_decision_correct is True


def test_objective_hallucination_craters_score(cohort):
    s, o = cohort
    bad = s.CohortOutput(
        predicted_members={"p1", "p2", "p3"},        # missed p4
        resolved_codes={("ICD10CM", "E11.9")},       # incomplete concept set
        predicted_n=12, decided_to_build=True,       # bad feasibility estimate
        citations=["PMID:notreal", "PMID:29435101"]) # one hallucinated (format-invalid)
    res = o.cohort_objective(_gold(s), bad)
    # documented smoke value ~0.31 — pin it so a scorer change trips
    assert res.score == pytest.approx(0.3107, abs=1e-3)


def test_objective_fake_citation_worse_than_none(cohort):
    s, o = cohort
    # SAME cohort quality, differing only in citations: a fabricated PMID must score
    # STRICTLY LOWER than attaching no citation (the LAMBDA hallucination penalty).
    base = dict(predicted_members={"p1", "p2", "p3", "p4"},
                resolved_codes={("ICD10CM", "E11.9"), ("ICD10CM", "E11.65"), ("LOINC", "4548-4")},
                predicted_n=4, decided_to_build=True)
    none = o.cohort_objective(_gold(s), s.CohortOutput(citations=[], **base)).score
    fake = o.cohort_objective(_gold(s), s.CohortOutput(citations=["PMID:notreal"], **base)).score
    assert fake < none


def test_objective_positive_weights_sum_to_one(cohort):
    _, o = cohort
    assert o.W_MEMBERSHIP + o.W_CONCEPTSET + o.W_FEASIBILITY + o.W_CITATION == pytest.approx(1.0)


# --- free-text notes: trap specificity + generator gold -----------------------

def _notes_gold(s):
    """Gold with negation/family-history traps for the free-text specificity scorer."""
    return s.CohortGold(
        true_members={"p1", "p2"}, all_patients={f"p{i}" for i in range(1, 11)},
        reference_codes={("ICD10CM", "E11.9")}, actual_feasible_n=2, should_build=True,
        negation_traps={"p7", "p8"}, family_history_traps={"p9"})


def test_note_trap_specificity_all_excluded(cohort):
    s, _ = cohort
    out = s.CohortOutput(predicted_members={"p1", "p2"})   # no trap leaked in
    r = s.note_trap_specificity(_notes_gold(s), out)
    assert r["specificity"] == 1.0 and r["trap_leak_rate"] == 0.0 and r["n_traps"] == 3


def test_note_trap_specificity_penalizes_leaks(cohort):
    s, _ = cohort
    out = s.CohortOutput(predicted_members={"p1", "p2", "p8", "p9"})  # negation + family-hx leaked
    r = s.note_trap_specificity(_notes_gold(s), out)
    assert r["n_traps"] == 3 and set(r["leaked"]) == {"p8", "p9"}
    assert r["specificity"] == pytest.approx(1 / 3) and r["trap_leak_rate"] == pytest.approx(2 / 3)


def test_note_trap_specificity_no_traps_is_vacuously_perfect(cohort):
    s, _ = cohort
    g = s.CohortGold(true_members=set(), all_patients=set(), reference_codes=set(),
                     actual_feasible_n=0)
    r = s.note_trap_specificity(g, s.CohortOutput(predicted_members={"p1"}))
    assert r["specificity"] == 1.0 and r["n_traps"] == 0
