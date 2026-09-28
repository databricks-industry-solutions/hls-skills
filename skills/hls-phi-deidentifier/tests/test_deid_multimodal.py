"""v2 multimodal + richer-interaction scorer tests (de-identifier).

Pins the NEW v2 behavior (region-aware detection_recall + residual_leaks, 3-part
governance_score_v2, interaction_fidelity, modality_coverage, deid_objective_v2 incl. the
modality-aware leak gate) without touching v1. Uses the per-skill `deid` fixture. Offline.
"""

from __future__ import annotations


# ============================ DE-ID v2 scorers ===============================

def _region_keys(gold, sc):
    return {(r.doc_id, r.page, tuple(r.bbox)) for r in gold.phi_regions}


def test_detection_recall_region_aware(deid):
    sc, _ = deid
    gold = sc.DeidGold(injected=[], analytic_columns=[], phi_regions=[
        sc.PhiRegion("doc1", 0, (1, 2, 3, 4), "name", "Alex Rivera"),
        sc.PhiRegion("doc1", 0, (5, 6, 7, 8), "ssn", "123-45-6789")])
    # redact only one of the two regions -> recall 0.5, no over-redaction
    out = sc.DeidOutput(redacted_regions={("doc1", 0, (1, 2, 3, 4))})
    det = sc.detection_recall(gold, out)
    assert det["recall"] == 0.5 and det["precision"] == 1.0
    # redact both -> recall 1.0
    full = sc.DeidOutput(redacted_regions=_region_keys(gold, sc))
    assert sc.detection_recall(gold, full)["recall"] == 1.0


def test_residual_leaks_counts_cells_and_regions(deid):
    sc, _ = deid
    out = sc.DeidOutput(residual_phi_cells={("r1", "ssn")},
                        residual_phi_regions={("doc1", 0, (1, 2, 3, 4))})
    assert sc.residual_leaks(out) == 2
    # empty regions -> identical to v1 (cells only): the pinned path is unaffected
    assert sc.residual_leaks(sc.DeidOutput(residual_phi_cells={("r1", "ssn")})) == 1


def test_governance_score_v2_three_parts(deid):
    sc, _ = deid

    def gov(view, raw_exposed, sur, cross):
        return sc.governance_score_v2(sc.DeidOutput(
            is_view_over_raw=view, raw_phi_still_exposed=raw_exposed,
            surrogate_key_present=sur, crosswalk_locked=cross))

    assert gov(True, False, True, True) == 1.0                 # all three parts
    assert abs(gov(True, False, False, False) - 2 / 3) < 1e-9  # view + raw-not-exposed
    assert gov(False, True, False, False) == 0.0               # nothing
    # crosswalk part needs BOTH surrogate AND locked
    assert abs(gov(True, False, True, False) - 2 / 3) < 1e-9


def test_modality_coverage(deid):
    sc, _ = deid
    gold = sc.DeidGold(injected=[], analytic_columns=[], modalities_present={"pdf", "image"})
    out = sc.DeidOutput(modalities_handled={"pdf"})
    r = sc.modality_coverage(gold, out)
    assert r["coverage"] == 0.5 and r["skipped"] == ["image"]
    full = sc.DeidOutput(modalities_handled={"pdf", "image"})
    assert sc.modality_coverage(gold, full)["coverage"] == 1.0
    # no modalities declared (legacy structured) -> full credit
    assert sc.modality_coverage(sc.DeidGold(injected=[], analytic_columns=[]),
                                sc.DeidOutput())["coverage"] == 1.0


def test_deid_objective_v2_gate_and_terms(deid):
    sc, obj = deid
    gold = sc.DeidGold(
        injected=[], analytic_columns=[], modalities_present={"pdf", "image"},
        phi_regions=[sc.PhiRegion("doc1", 0, (1, 2, 3, 4), "name", "X"),
                     sc.PhiRegion("doc2", 0, (5, 6, 7, 8), "ssn", "Y")],
        should_surface={"redaction_strategy", "pixel_aggressiveness", "output_delivery"})
    allregions = _region_keys(gold, sc)

    def out(**kw):
        base = dict(redacted_regions=allregions, residual_phi_regions=set(),
                    k_anonymity=5, is_view_over_raw=True, raw_phi_still_exposed=False,
                    surrogate_key_present=True, crosswalk_locked=True,
                    modalities_handled={"pdf", "image"},
                    surfaced_decisions={"redaction_strategy", "pixel_aggressiveness",
                                        "output_delivery"})
        base.update(kw)
        return sc.DeidOutput(**base)

    # perfect multimodal run -> 1.0
    assert obj.deid_objective_v2(gold, out()).score == 1.0
    # a residual region (burned-in pixel PHI left in) trips the gate -> 0.0
    r = obj.deid_objective_v2(gold, out(residual_phi_regions={("doc1", 0, (1, 2, 3, 4))}))
    assert r.score == 0.0 and r.leaked is True
    # missing reversible crosswalk -> governance 2/3 -> 1.0 - 0.20*(1/3)
    assert abs(obj.deid_objective_v2(gold, out(crosswalk_locked=False)).score
               - (1.0 - obj.W2_GOVERNANCE * (1 / 3))) < 1e-3
    # silently skipped the image modality -> coverage 0.5 -> docks 0.10*0.5
    assert abs(obj.deid_objective_v2(gold, out(modalities_handled={"pdf"})).score
               - (1.0 - obj.W2_MODALITY * 0.5)) < 1e-3


def test_v1_deid_objective_unchanged_by_v2_additions(deid):
    """Guard: the pinned v1 objective still returns its documented numbers with the new
    (default-empty) multimodal fields present on the dataclasses."""
    sc, obj = deid
    gold = sc.DeidGold(
        injected=[sc.PhiSpan("r1", "ssn", "ssn", "123-45-6789")],
        analytic_columns=["age_band"], intervals=[])
    perfect = sc.DeidOutput(
        transformed_cells={("r1", "ssn")}, residual_phi_cells=set(),
        surviving_analytic_columns=["age_band"], analytic_fidelity={"age_band": "full"},
        k_anonymity=7, is_view_over_raw=True, raw_phi_still_exposed=False)
    assert obj.deid_objective(gold, perfect).score == 1.0
