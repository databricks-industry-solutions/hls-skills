"""Cohort-builder scorers -- runnable, pure-Python, deterministic.

Ground truth comes from SEEDED synthetic data: each synthetic patient is generated
with known cohort membership and the reference concept set is fixed, so membership
and concept-set accuracy are exact. Citation validity is checked against a resolver
(stubbed for offline runs; real runs hit the literature MCP server).
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --- Data contracts -----------------------------------------------------------

@dataclass
class CohortGold:
    true_members: set                       # {patient_id} that SHOULD be in the cohort
    all_patients: set                       # full population (for N / feasibility)
    reference_codes: set                    # the correct concept set {(vocab, code)}
    actual_feasible_n: int                  # true eligible N (== len(true_members))
    should_build: bool = True               # was this cohort feasible enough to build?
    # --- free-text (clinical-notes) ground truth (optional; populated for notes runs) ---
    # For a notes-inclusive cohort, membership is a CHOICE of how to combine coded criteria
    # with note-derived evidence. Each combine mode has its own exact gold set so the A/B can
    # score whichever definition the user confirmed.
    code_true_members: set = field(default_factory=set)      # coded dx AND uncontrolled A1c
    note_true_members: set = field(default_factory=set)      # note asserts CURRENT dx AND uncontrolled A1c
    union_true_members: set = field(default_factory=set)     # code OR note (headline notes gold)
    intersection_true_members: set = field(default_factory=set)  # code AND note
    negation_traps: set = field(default_factory=set)         # note NEGATES the dx ("no evidence of…")
    family_history_traps: set = field(default_factory=set)   # dx belongs to a relative, not the patient
    naive_keyword_members: set = field(default_factory=set)  # what a dumb LIKE '%diabet%' + A1c filter returns
    # --- multimodal / document ground truth (optional; populated for PDF/image runs) ---
    document_true_members: set = field(default_factory=set)  # dx asserted in a parsed PDF/image AND uncontrolled A1c
    document_traps: set = field(default_factory=set)         # doc distractors ("ruled out", "resolved", family hx)
    documents: dict = field(default_factory=dict)            # doc_id -> [page_text,...] (source for span-grounding)
    document_evidence: dict = field(default_factory=dict)    # patient_id -> [{doc_id,page,bbox,quote}] TRUE anchors
    should_surface: set = field(default_factory=set)         # decision keys the skill SHOULD surface (interaction_fidelity)


@dataclass
class CohortOutput:
    predicted_members: set = field(default_factory=set)
    resolved_codes: set = field(default_factory=set)         # {(vocab, code)} the run used
    predicted_n: int = 0                                     # N the feasibility step predicted
    decided_to_build: bool = True
    citations: list = field(default_factory=list)            # ["PMID:12345", "NCT01234567", ...]
    # --- multimodal / document (optional; default empty = coded/notes behavior unchanged) ---
    document_members: set = field(default_factory=set)       # members the run attributed to document evidence
    evidence_anchors: dict = field(default_factory=dict)     # patient_id -> [{doc_id,page,bbox,quote}] CLAIMED anchors
    surfaced_decisions: set = field(default_factory=set)     # decision keys the run surfaced to the user


# --- Component scorers --------------------------------------------------------

def _f1(pred: set, truth: set) -> dict:
    tp = len(pred & truth)
    fp = len(pred - truth)
    fn = len(truth - pred)
    p = tp / (tp + fp) if (tp + fp) else 1.0
    r = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"precision": p, "recall": r, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def membership_f1(gold: CohortGold, out: CohortOutput) -> dict:
    """Did the run select the right patients? Headline metric."""
    return _f1(out.predicted_members, gold.true_members)


def conceptset_f1(gold: CohortGold, out: CohortOutput) -> dict:
    """Did ontology normalization resolve the right codes (with descendants)?"""
    return _f1(out.resolved_codes, gold.reference_codes)


def feasibility_calibration(gold: CohortGold, out: CohortOutput) -> float:
    """1 - relative error between predicted and actual N (clamped to [0,1])."""
    if gold.actual_feasible_n == 0:
        return 1.0 if out.predicted_n == 0 else 0.0
    rel_err = abs(out.predicted_n - gold.actual_feasible_n) / gold.actual_feasible_n
    return max(0.0, 1.0 - rel_err)


def build_decision_correct(gold: CohortGold, out: CohortOutput) -> bool:
    """Did the feasibility gate make the right proceed/stop call?"""
    return out.decided_to_build == gold.should_build


def citation_validity(out: CohortOutput, resolver=None) -> dict:
    """Fraction of citations that RESOLVE to a real record.

    resolver(citation) -> bool. Offline default treats well-formed PMID/NCT ids as
    resolvable so the pipeline runs; real runs pass an MCP-backed resolver that also
    checks the citation actually supports the claim. Hallucination = 1 - validity.
    """
    if not out.citations:
        return {"validity": 1.0, "hallucination_rate": 0.0, "n": 0}

    def _default(c: str) -> bool:
        c = c.strip().upper()
        return (c.startswith("PMID:") and c[5:].isdigit()) or \
               (c.startswith("NCT") and c[3:].isdigit() and len(c) == 11)

    r = resolver or _default
    valid = sum(1 for c in out.citations if r(c))
    n = len(out.citations)
    return {"validity": valid / n, "hallucination_rate": 1 - valid / n, "n": n}


def note_trap_specificity(gold: CohortGold, out: CohortOutput) -> dict:
    """Free-text-specific: of the note distractors that must NOT count (negated mentions and
    family-history mentions), how many did the run correctly EXCLUDE?

    This is the axis where a naive keyword/LIKE baseline fails and negation-/subject-aware
    extraction wins: "no evidence of diabetes" and "mother had type 2 diabetes" both contain
    the string 'diabetes' but assert nothing about the CURRENT patient. specificity = correctly
    excluded traps / all traps; 1.0 means every distractor was kept out.
    """
    traps = gold.negation_traps | gold.family_history_traps
    if not traps:
        return {"specificity": 1.0, "trap_leak_rate": 0.0, "n_traps": 0, "leaked": []}
    leaked = sorted(traps & out.predicted_members)
    excluded = len(traps) - len(leaked)
    return {"specificity": excluded / len(traps),
            "trap_leak_rate": len(leaked) / len(traps),
            "n_traps": len(traps), "leaked": leaked}


def multimodal_trap_specificity(gold: CohortGold, out: CohortOutput) -> dict:
    """Generalizes note_trap_specificity across ALL unstructured sources: notes AND parsed
    documents. Adds document distractors (`document_traps`) -- "diabetes ruled out",
    "history of gestational diabetes, resolved", "father has type 2 diabetes" -- to the note
    negation/family-history traps. specificity = correctly-excluded traps / all traps.

    When there are no document traps this equals note_trap_specificity, so nothing regresses.
    """
    traps = gold.negation_traps | gold.family_history_traps | gold.document_traps
    if not traps:
        return {"specificity": 1.0, "trap_leak_rate": 0.0, "n_traps": 0, "leaked": []}
    leaked = sorted(traps & out.predicted_members)
    excluded = len(traps) - len(leaked)
    return {"specificity": excluded / len(traps),
            "trap_leak_rate": len(leaked) / len(traps),
            "n_traps": len(traps), "leaked": leaked}


def _quote_grounded(quote: str, pages: list, page: int = None) -> bool:
    """A claimed evidence quote is GROUNDED iff it is a non-empty substring of the source
    document text (the cited page if given, else any page). Case-insensitive. This is the
    document analogue of note span-grounding: a model cannot cite evidence that isn't there.
    """
    q = (quote or "").strip().lower()
    if not q or not pages:
        return False
    if page is not None and 0 <= page < len(pages):
        return q in (pages[page] or "").lower()
    return any(q in (p or "").lower() for p in pages)


def source_grounding(gold: CohortGold, out: CohortOutput) -> dict:
    """Of the members the run attributed to DOCUMENT evidence, what fraction cite an anchor
    whose verbatim quote actually appears in the source document? (Multimodal fail-closed.)

    Fails a member when: it claims a document source but provides no anchor, or the cited
    quote is not a substring of the cited page (a fabricated/hallucinated citation). If the
    run attributed nobody to documents, there is nothing to ground -> 1.0 (recall is scored
    separately by membership_f1).
    """
    doc_members = sorted(out.document_members)
    if not doc_members:
        return {"grounding": 1.0, "n_doc_members": 0, "grounded": 0, "ungrounded": []}
    grounded, ungrounded = 0, []
    for pid in doc_members:
        anchors = out.evidence_anchors.get(pid) or []
        ok = False
        for a in anchors:
            pages = gold.documents.get(a.get("doc_id"), [])
            if _quote_grounded(a.get("quote", ""), pages, a.get("page")):
                ok = True
                break
        if ok:
            grounded += 1
        else:
            ungrounded.append(pid)
    return {"grounding": grounded / len(doc_members),
            "n_doc_members": len(doc_members), "grounded": grounded, "ungrounded": ungrounded}


def interaction_fidelity(gold: CohortGold, out: CohortOutput) -> dict:
    """Did the run SURFACE the decisions it should (threshold, code/note/document combine,
    modality weighting, output delivery) instead of silently deciding? surfaced / should.

    This is the core value prop: the un-guided baseline silently makes definitional choices
    the analyst never sees. Empty should_surface -> 1.0 (nothing to surface).
    """
    should = set(gold.should_surface)
    if not should:
        return {"fidelity": 1.0, "surfaced": len(out.surfaced_decisions), "expected": 0, "missed": []}
    surfaced = set(out.surfaced_decisions) & should
    missed = sorted(should - surfaced)
    return {"fidelity": len(surfaced) / len(should),
            "surfaced": len(surfaced), "expected": len(should), "missed": missed}


# --- Trace adapter ------------------------------------------------------------

def outputs_to_gold_and_output(expectations: dict, outputs: dict) -> tuple:
    """Rehydrate CohortGold (from an eval row's expectations) and CohortOutput (from
    the skill's returned artifact) into the dataclasses the scorers consume."""
    gold = CohortGold(
        true_members=set(expectations["true_members"]),
        all_patients=set(expectations.get("all_patients", [])),
        reference_codes={tuple(c) for c in expectations.get("reference_codes", [])},
        actual_feasible_n=expectations["actual_feasible_n"],
        should_build=expectations.get("should_build", True),
        code_true_members=set(expectations.get("code_true_members", [])),
        note_true_members=set(expectations.get("note_true_members", [])),
        union_true_members=set(expectations.get("union_true_members", [])),
        intersection_true_members=set(expectations.get("intersection_true_members", [])),
        negation_traps=set(expectations.get("negation_traps", [])),
        family_history_traps=set(expectations.get("family_history_traps", [])),
        naive_keyword_members=set(expectations.get("naive_keyword_members", [])),
        document_true_members=set(expectations.get("document_true_members", [])),
        document_traps=set(expectations.get("document_traps", [])),
        documents=expectations.get("documents", {}),
        document_evidence=expectations.get("document_evidence", {}),
        should_surface=set(expectations.get("should_surface", [])),
    )
    out = CohortOutput(
        predicted_members=set(outputs.get("predicted_members", [])),
        resolved_codes={tuple(c) for c in outputs.get("resolved_codes", [])},
        predicted_n=outputs.get("predicted_n", 0),
        decided_to_build=outputs.get("decided_to_build", True),
        citations=outputs.get("citations", []),
        document_members=set(outputs.get("document_members", [])),
        evidence_anchors=outputs.get("evidence_anchors", {}),
        surfaced_decisions=set(outputs.get("surfaced_decisions", [])),
    )
    return gold, out


# --- MLflow scorer wrappers (for A/B / production monitoring; optional import) --

def mlflow_scorers(resolver=None):
    """Return mlflow.genai @scorer callables wrapping the components above.

    Imported lazily so the pure-Python scorers work without mlflow installed. Pass a
    `resolver` (MCP-backed) in real runs so citation checks hit the literature server;
    the offline default only validates id FORMAT.
    """
    from mlflow.genai.scorers import scorer
    from mlflow.entities import Feedback

    @scorer
    def cohort_membership_f1(expectations: dict, outputs: dict) -> float:
        gold, out = outputs_to_gold_and_output(expectations, outputs)
        return membership_f1(gold, out)["f1"]

    @scorer
    def cohort_feasibility_calibration(expectations: dict, outputs: dict) -> float:
        gold, out = outputs_to_gold_and_output(expectations, outputs)
        return feasibility_calibration(gold, out)

    @scorer
    def cohort_no_hallucinated_citations(outputs: dict) -> Feedback:
        out = CohortOutput(citations=outputs.get("citations", []))
        c = citation_validity(out, resolver=resolver)
        bad = round(c["hallucination_rate"] * c["n"])
        return Feedback(value="pass" if bad == 0 else "fail",
                        rationale=f"{bad}/{c['n']} citation(s) did not resolve")

    @scorer
    def cohort_build_decision(expectations: dict, outputs: dict) -> Feedback:
        gold, out = outputs_to_gold_and_output(expectations, outputs)
        ok = build_decision_correct(gold, out)
        return Feedback(value="pass" if ok else "fail",
                        rationale=f"decided_to_build={out.decided_to_build}, should_build={gold.should_build}")

    @scorer
    def cohort_note_trap_specificity(expectations: dict, outputs: dict) -> Feedback:
        """Free-text runs only: did negated / family-history note mentions stay OUT?"""
        gold, out = outputs_to_gold_and_output(expectations, outputs)
        r = note_trap_specificity(gold, out)
        return Feedback(value="pass" if r["trap_leak_rate"] == 0 else "fail",
                        rationale=f"{len(r['leaked'])}/{r['n_traps']} note distractor(s) leaked in: {r['leaked']}")

    return [cohort_membership_f1, cohort_feasibility_calibration,
            cohort_no_hallucinated_citations, cohort_build_decision,
            cohort_note_trap_specificity]
