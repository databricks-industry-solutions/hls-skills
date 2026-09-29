"""De-identification scorers -- runnable, pure-Python, deterministic.

All scorers operate on a `DeidGold` (ground truth from synthetic generation) and a
`DeidOutput` (what a run produced). Because we INJECT the PHI when generating data,
every label is exact -- recall is measured, not estimated.

These functions are the components of the objective in objective.py, and are wrapped
as mlflow.genai @scorer functions in this module's `mlflow_scorers()` for A/B use.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --- Data contracts -----------------------------------------------------------

@dataclass(frozen=True)
class PhiSpan:
    """One injected identifier. row_id+column+class uniquely locate it."""
    row_id: str
    column: str
    phi_class: str          # a Safe Harbor detected_class (see references/safe_harbor_classes.md)
    raw_value: str


@dataclass(frozen=True)
class PhiRegion:
    """One injected identifier in an UNSTRUCTURED artifact (parsed PDF / image).

    The multimodal analogue of PhiSpan: instead of (row_id, column) it is located by
    (doc_id, page, bbox). bbox is a 4-tuple (x0, y0, x1, y1) so the region is hashable and
    comparable. Populated by the document/image gold generators; used by the region-aware
    detection + residual-leak scorers so a de-id run over parsed docs is measured exactly.
    """
    doc_id: str
    page: int
    bbox: tuple                 # (x0, y0, x1, y1)
    phi_class: str
    raw_value: str


@dataclass
class DeidGold:
    injected: list[PhiSpan]                 # every PHI value we planted (structured cells)
    analytic_columns: list[str]             # non-PHI columns that SHOULD survive
    intervals: list[tuple] = field(default_factory=list)
    # each interval: (patient_id, col_a, col_b, days) -- the true gap between two of a
    # patient's dates, used to check that date-shifting preserved intervals.
    # --- multimodal ground truth (optional; populated for PDF/image runs) ---
    phi_regions: list = field(default_factory=list)          # [PhiRegion] planted in parsed docs/images
    modalities_present: set = field(default_factory=set)     # {"structured","pdf","image"} the task actually contains
    documents: dict = field(default_factory=dict)            # doc_id -> {page:int -> page_text} (for residual grounding)
    should_surface: set = field(default_factory=set)         # decision keys the skill SHOULD surface (interaction_fidelity)


@dataclass
class DeidOutput:
    """What a de-id run produced, read back from the consumer-role view."""
    # cells the run actually transformed (row_id, column) -> still-PHI? (residual check)
    transformed_cells: set = field(default_factory=set)          # {(row_id, column)}
    residual_phi_cells: set = field(default_factory=set)         # {(row_id, column)} still containing PHI in OUTPUT
    surviving_analytic_columns: list = field(default_factory=list)
    preserved_intervals: list = field(default_factory=list)      # (patient_id, col_a, col_b, days) observed in output
    k_anonymity: int = 0
    # How each analytic column survived: "full" (unchanged), "generalized" (present but
    # coarsened for k-anon -> partial credit), or absent (dropped -> no credit). Lets the
    # objective represent a deliberate privacy/utility trade instead of zeroing utility.
    analytic_fidelity: dict = field(default_factory=dict)        # column -> "full"|"generalized"
    # Governance posture -- the dimension the baseline exposed as missing.
    is_view_over_raw: bool = False        # output is a VIEW over the raw table (no 2nd PHI copy)
    raw_phi_still_exposed: bool = True    # does the source table still expose direct identifiers to consumers?
    interval_generalized: bool = False    # interval kept in coarsened form (bucketed LOS) rather than exact
    # --- multimodal + v2 governance/interaction (optional; default empty = v1 behavior) ---
    redacted_regions: set = field(default_factory=set)       # {(doc_id, page, bbox)} the run masked/inpainted
    residual_phi_regions: set = field(default_factory=set)   # {(doc_id, page, bbox)} PHI still visible in OUTPUT
    modalities_handled: set = field(default_factory=set)     # {"structured","pdf","image"} the run actually processed
    surfaced_decisions: set = field(default_factory=set)     # decision keys the run surfaced to the user
    surrogate_key_present: bool = False   # every output row/artifact carries a NON-PHI surrogate key
    crosswalk_locked: bool = False        # reversible surrogate->raw crosswalk exists in a separately-governed locked schema


# --- Component scorers --------------------------------------------------------

def _prf(tp: int, fp: int, fn: int) -> tuple[float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return precision, recall


def detection_recall(gold: DeidGold, out: DeidOutput) -> dict:
    """Per-class + overall precision/recall of PHI detection.

    TP = injected cell that was transformed. FN = injected cell left untouched (LEAK RISK).
    FP = a cell transformed that was not injected PHI (over-redaction; hurts utility only).

    Region-aware: injected PHI in parsed docs/images (gold.phi_regions, located by
    (doc_id, page, bbox)) is scored alongside structured cells against out.redacted_regions.
    When there are no regions (a purely structured run) this reduces EXACTLY to the v1
    per-cell computation, so the pinned v1 numbers are unchanged.
    """
    injected_cells = {(s.row_id, s.column): s.phi_class for s in gold.injected}
    injected_regions = {(r.doc_id, r.page, tuple(r.bbox)): r.phi_class for r in gold.phi_regions}
    tp = fn = fp = 0
    per_class: dict = {}
    for cell, klass in injected_cells.items():
        hit = cell in out.transformed_cells
        c = per_class.setdefault(klass, {"tp": 0, "fn": 0})
        if hit:
            tp += 1; c["tp"] += 1
        else:
            fn += 1; c["fn"] += 1
    for region, klass in injected_regions.items():
        hit = region in out.redacted_regions
        c = per_class.setdefault(klass, {"tp": 0, "fn": 0})
        if hit:
            tp += 1; c["tp"] += 1
        else:
            fn += 1; c["fn"] += 1
    for cell in out.transformed_cells:
        if cell not in injected_cells:
            fp += 1
    for region in out.redacted_regions:
        if region not in injected_regions:
            fp += 1
    precision, recall = _prf(tp, fp, fn)
    per_class_recall = {
        k: (v["tp"] / (v["tp"] + v["fn"]) if (v["tp"] + v["fn"]) else 1.0)
        for k, v in per_class.items()
    }
    return {"precision": precision, "recall": recall,
            "per_class_recall": per_class_recall, "tp": tp, "fp": fp, "fn": fn}


def residual_leaks(out: DeidOutput) -> int:
    """PHI still present in the OUTPUT (any modality). Any value > 0 is a hard failure.

    Sums structured residual cells AND unstructured residual regions (burned-in pixel text
    or unredacted parsed-doc spans). Empty regions -> identical to v1, so the pinned v1
    leak-gate behavior is preserved.
    """
    return len(out.residual_phi_cells) + len(out.residual_phi_regions)


# Credit per analytic column by how faithfully it survived.
_FIDELITY_CREDIT = {"full": 1.0, "generalized": 0.5}   # dropped/absent -> 0.0


def utility_retention(gold: DeidGold, out: DeidOutput) -> float:
    """Graded analytic value preserved, additively (NOT multiplicatively) combining
    column survival and interval preservation, so trading ONE dimension for privacy
    does not zero the whole score.

    Each analytic column earns credit by fidelity: full=1.0, generalized=0.5, dropped=0.0.
    Intervals earn credit exact=1.0, generalized(bucketed)=0.5, lost=0.0. The two are
    averaged. This lets the objective represent a deliberate privacy/utility trade --
    the entire point of k-anonymity -- instead of punishing correct generalization.
    """
    if gold.analytic_columns:
        credit = 0.0
        for c in gold.analytic_columns:
            if c in out.surviving_analytic_columns:
                credit += _FIDELITY_CREDIT.get(out.analytic_fidelity.get(c, "full"), 1.0)
        col_keep = credit / len(gold.analytic_columns)
    else:
        col_keep = 1.0

    if gold.intervals:
        observed = {(p, a, b): d for (p, a, b, d) in out.preserved_intervals}
        exact = sum(1 for (p, a, b, d) in gold.intervals if observed.get((p, a, b)) == d)
        interval_keep = exact / len(gold.intervals)
        if interval_keep == 0.0 and out.interval_generalized:
            interval_keep = 0.5           # bucketed LOS still supports coarse longitudinal analysis
    else:
        interval_keep = 1.0

    return (col_keep + interval_keep) / 2.0


def governance_score(out: DeidOutput) -> float:
    """Governance posture -- the dimension the baseline exposed as missing.

    Rewards enforcing de-id through a VIEW over the raw table (no second physical copy
    of PHI) AND ensuring the raw source no longer exposes direct identifiers to
    consumers. Baseline Genie wrote a physical copy and left raw PHI fully exposed -> 0.
    """
    score = 0.0
    if out.is_view_over_raw:
        score += 0.5          # no second PHI copy; de-id is a governed view
    if not out.raw_phi_still_exposed:
        score += 0.5          # source is masked/restricted for consumers
    return score


def governance_score_v2(out: DeidOutput) -> float:
    """v2 governance -- a THREE-part check (each worth 1/3), adding the locked, reversible
    re-identification crosswalk required by the plan (Safe Harbor 164.514(c)-compatible).

    1. view-over-raw       : de-id enforced as a view, no second physical PHI copy.
    2. raw-not-exposed     : the source no longer exposes direct identifiers to consumers.
    3. reversible crosswalk: every output carries a NON-PHI surrogate key AND a
                             surrogate->raw crosswalk lives in a separately-governed LOCKED
                             schema -- preserving a governed path back to the original
                             regardless of tokenization or k-anonymity.
    Kept separate from v1 governance_score (0.5/0.5) so the pinned v1 objective is unchanged.
    """
    parts = [out.is_view_over_raw,
             (not out.raw_phi_still_exposed),
             (out.surrogate_key_present and out.crosswalk_locked)]
    return sum(1 for p in parts if p) / 3.0


def interaction_fidelity(gold: DeidGold, out: DeidOutput) -> dict:
    """Did the skill SURFACE the decisions it should (per-column strategy, date handling, QI
    set, utility priority, pixel aggressiveness, output delivery) instead of silently deciding?

    surfaced / should-surface. This is the core value prop of the surface-and-choose design:
    a run that silently picks defaults scores low even if the de-id itself is competent.
    No decisions were expected (empty should_surface) -> 1.0 (nothing to surface).
    """
    should = set(gold.should_surface)
    if not should:
        return {"fidelity": 1.0, "surfaced": len(out.surfaced_decisions), "expected": 0, "missed": []}
    surfaced = set(out.surfaced_decisions) & should
    missed = sorted(should - surfaced)
    return {"fidelity": len(surfaced) / len(should),
            "surfaced": len(surfaced), "expected": len(should), "missed": missed}


def modality_coverage(gold: DeidGold, out: DeidOutput) -> dict:
    """Did the run handle EVERY modality present, or silently skip one (e.g., leave the images
    untouched while de-identifying the table)? handled / present.

    A skipped modality is dangerous: its PHI survives unaddressed. This is scored separately
    from the leak gate because a run can 'skip' a modality without a residual-scan hit if it
    simply never looked at it. present is empty (single-modality legacy) -> 1.0.
    """
    present = set(gold.modalities_present)
    if not present:
        return {"coverage": 1.0, "handled": sorted(out.modalities_handled), "present": [], "skipped": []}
    handled = set(out.modalities_handled) & present
    skipped = sorted(present - handled)
    return {"coverage": len(handled) / len(present),
            "handled": sorted(handled), "present": sorted(present), "skipped": skipped}


def f_beta(precision: float, recall: float, beta: float = 2.0) -> float:
    """F-beta; beta=2 weights recall 4x precision -- the de-id default."""
    b2 = beta * beta
    denom = (b2 * precision) + recall
    return (1 + b2) * precision * recall / denom if denom else 0.0


# --- Trace adapter ------------------------------------------------------------

def outputs_to_gold_and_output(expectations: dict, outputs: dict) -> tuple[DeidGold, DeidOutput]:
    """Rehydrate DeidGold (from an eval row's expectations) and DeidOutput (from the
    skill's returned artifact) into the dataclasses the component scorers consume.

    `expectations` is the gold half of an MLflow eval dataset row (produced by
    synthetic_gold.generate_deid_dataset and serialized). `outputs` is whatever the
    de-id skill returns for a task -- adapt the keys here to the real return shape.
    """
    def _region(x):
        # normalize [doc_id, page, [x0,y0,x1,y1]] (JSON) -> (doc_id, page, (x0,y0,x1,y1))
        return (x[0], x[1], tuple(x[2]))

    gold = DeidGold(
        injected=[PhiSpan(**s) for s in expectations["injected"]],
        analytic_columns=expectations.get("analytic_columns", []),
        intervals=[tuple(t) for t in expectations.get("intervals", [])],
        phi_regions=[PhiRegion(doc_id=r["doc_id"], page=r["page"], bbox=tuple(r["bbox"]),
                               phi_class=r["phi_class"], raw_value=r["raw_value"])
                     for r in expectations.get("phi_regions", [])],
        modalities_present=set(expectations.get("modalities_present", [])),
        documents=expectations.get("documents", {}),
        should_surface=set(expectations.get("should_surface", [])),
    )
    out = DeidOutput(
        transformed_cells={tuple(c) for c in outputs.get("transformed_cells", [])},
        residual_phi_cells={tuple(c) for c in outputs.get("residual_phi_cells", [])},
        surviving_analytic_columns=outputs.get("surviving_analytic_columns", []),
        preserved_intervals=[tuple(t) for t in outputs.get("preserved_intervals", [])],
        k_anonymity=outputs.get("k_anonymity", 0),
        redacted_regions={_region(x) for x in outputs.get("redacted_regions", [])},
        residual_phi_regions={_region(x) for x in outputs.get("residual_phi_regions", [])},
        modalities_handled=set(outputs.get("modalities_handled", [])),
        surfaced_decisions=set(outputs.get("surfaced_decisions", [])),
        surrogate_key_present=outputs.get("surrogate_key_present", False),
        crosswalk_locked=outputs.get("crosswalk_locked", False),
    )
    return gold, out


# --- MLflow scorer wrappers (for A/B / production monitoring; optional import) --

def mlflow_scorers():
    """Return mlflow.genai @scorer callables wrapping the components above.

    Imported lazily so the pure-Python scorers work without mlflow installed. Each
    scorer reads `expectations` (gold) + `outputs` (skill result) from the eval row.
    Feedback values: numeric metrics for recall/utility; a pass/fail for the leak
    gate (the single dimension a security reviewer cares about most).
    """
    from mlflow.genai.scorers import scorer
    from mlflow.entities import Feedback

    @scorer
    def deid_recall(expectations: dict, outputs: dict) -> float:
        gold, out = outputs_to_gold_and_output(expectations, outputs)
        return detection_recall(gold, out)["recall"]

    @scorer
    def deid_no_residual_leak(outputs: dict) -> Feedback:
        # The headline safety gate: any residual PHI in the output fails.
        out = DeidOutput(residual_phi_cells={tuple(c) for c in outputs.get("residual_phi_cells", [])})
        n = residual_leaks(out)
        return Feedback(value="pass" if n == 0 else "fail",
                        rationale=f"{n} residual PHI cell(s) detected in de-identified output")

    @scorer
    def deid_utility(expectations: dict, outputs: dict) -> float:
        gold, out = outputs_to_gold_and_output(expectations, outputs)
        return utility_retention(gold, out)

    return [deid_recall, deid_no_residual_leak, deid_utility]
