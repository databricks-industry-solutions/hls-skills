"""v2 multimodal + richer-interaction scorer tests (cohort builder).

Pins the NEW v2 behavior (source_grounding fail-closed on fabricated evidence,
interaction_fidelity, multimodal_trap_specificity, cohort_objective_v2) without touching v1.
Uses the per-skill `cohort` fixture from conftest.py. Pure-Python, offline.
"""

from __future__ import annotations


# ============================ COHORT v2 scorers ==============================

def test_source_grounding_grounded_vs_fabricated(cohort):
    sc, _ = cohort
    quote = "Type 2 diabetes mellitus, poorly controlled"
    gold = sc.CohortGold(
        true_members={"p1"}, all_patients={"p1", "p2"}, reference_codes=set(),
        actual_feasible_n=1,
        documents={"doc1": [f"Clinic note.\n{quote}.\nPlan: follow up."]},
        document_true_members={"p1"})
    # grounded: cited quote is a substring of the source page
    ok = sc.CohortOutput(predicted_members={"p1"}, document_members={"p1"},
                         evidence_anchors={"p1": [{"doc_id": "doc1", "page": 0, "quote": quote}]})
    assert sc.source_grounding(gold, ok)["grounding"] == 1.0
    # fabricated: quote not in the document -> ungrounded (fail-closed)
    fab = sc.CohortOutput(document_members={"p1"},
                          evidence_anchors={"p1": [{"doc_id": "doc1", "page": 0,
                                                    "quote": "stage 4 pancreatic carcinoma"}]})
    r = sc.source_grounding(gold, fab)
    assert r["grounding"] == 0.0 and r["ungrounded"] == ["p1"]
    # claims a document member but gives NO anchor -> ungrounded
    noanchor = sc.CohortOutput(document_members={"p1"}, evidence_anchors={})
    assert sc.source_grounding(gold, noanchor)["grounding"] == 0.0
    # attributed nobody to documents -> nothing to ground -> 1.0
    assert sc.source_grounding(gold, sc.CohortOutput())["grounding"] == 1.0


def test_multimodal_trap_specificity_includes_document_traps(cohort):
    sc, _ = cohort
    gold = sc.CohortGold(
        true_members=set(), all_patients={"n1", "f1", "d1"}, reference_codes=set(),
        actual_feasible_n=0,
        negation_traps={"n1"}, family_history_traps={"f1"}, document_traps={"d1"})
    # leaks the DOCUMENT trap only
    out = sc.CohortOutput(predicted_members={"d1"})
    r = sc.multimodal_trap_specificity(gold, out)
    assert r["n_traps"] == 3 and r["leaked"] == ["d1"]
    assert abs(r["specificity"] - 2 / 3) < 1e-9
    # a clean run leaks nothing
    assert sc.multimodal_trap_specificity(gold, sc.CohortOutput())["specificity"] == 1.0


def test_interaction_fidelity_cohort(cohort):
    sc, _ = cohort
    gold = sc.CohortGold(true_members=set(), all_patients=set(), reference_codes=set(),
                         actual_feasible_n=0,
                         should_surface={"threshold", "combine_mode", "modality_combine",
                                         "output_delivery"})
    full = sc.CohortOutput(surfaced_decisions={"threshold", "combine_mode",
                                               "modality_combine", "output_delivery"})
    assert sc.interaction_fidelity(gold, full)["fidelity"] == 1.0
    half = sc.CohortOutput(surfaced_decisions={"threshold", "combine_mode"})
    assert sc.interaction_fidelity(gold, half)["fidelity"] == 0.5
    none = sc.CohortOutput(surfaced_decisions=set())
    r = sc.interaction_fidelity(gold, none)
    assert r["fidelity"] == 0.0 and set(r["missed"]) == gold.should_surface


def test_cohort_objective_v2_perfect_vs_fabricated(cohort):
    sc, obj = cohort
    quote = "Impression: longstanding type 2 diabetes with suboptimal glycemic control"
    gold = sc.CohortGold(
        true_members={"p1", "p2"}, all_patients={f"p{i}" for i in range(10)},
        reference_codes={("ICD10CM", "E11.9")}, actual_feasible_n=2, should_build=True,
        documents={"doc1": [quote + "."]}, document_true_members={"p1"},
        should_surface={"threshold", "combine_mode", "modality_combine", "output_delivery"})
    perfect = sc.CohortOutput(
        predicted_members={"p1", "p2"}, resolved_codes={("ICD10CM", "E11.9")},
        predicted_n=2, decided_to_build=True, citations=[],
        document_members={"p1"},
        evidence_anchors={"p1": [{"doc_id": "doc1", "page": 0, "quote": quote}]},
        surfaced_decisions={"threshold", "combine_mode", "modality_combine", "output_delivery"})
    assert obj.cohort_objective_v2(gold, perfect).score == 1.0
    # fabricated evidence + hallucinated citation + silent (no surfaced choices) + missed p2
    bad = sc.CohortOutput(
        predicted_members={"p1"}, resolved_codes=set(), predicted_n=8, decided_to_build=True,
        citations=["PMID:notreal"], document_members={"p1"},
        evidence_anchors={"p1": [{"doc_id": "doc1", "page": 0, "quote": "acute MI"}]},
        surfaced_decisions=set())
    assert obj.cohort_objective_v2(gold, bad).score < 0.35


