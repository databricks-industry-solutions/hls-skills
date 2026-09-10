"""Literature resolver for cohort phenotypes — fails CLOSED.

The baseline fabricated citations (fake PMID 22319177, a bogus Klompas cite). This
resolver only ever returns citations that RESOLVE against a real source. If it cannot
reach a source, it returns "unverified" and NO citation — it never invents one.

Primary source: PubMed E-utilities (public HTTP API, no MCP required). If a workspace
MCP literature server is available, prefer it, but this direct path means the feature
WORKS without one. Network egress from the runtime is not guaranteed; on any failure the
resolver degrades loudly (unverified), never silently and never with a fabricated id.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class LiteratureResult:
    query: str
    resolved: list = field(default_factory=list)   # [{pmid, title, journal, year}]
    reachable: bool = True                          # False if the source could not be reached
    note: str = ""

    def is_verified(self) -> bool:
        return self.reachable and bool(self.resolved)


def _get(url: str, timeout: int = 15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def search_pubmed(query: str, retmax: int = 3, timeout: int = 15) -> LiteratureResult:
    """Search PubMed and return REAL, resolvable citations only.

    On any network/parse failure -> reachable=False, resolved=[] (fail closed).
    """
    try:
        term = urllib.parse.quote(query)
        # sort=relevance (not the default most-recent) so the top hits are the papers most
        # ABOUT the phenotype, not just the newest paper that mentions it in passing.
        s = _get(f"{EUTILS}/esearch.fcgi?db=pubmed&term={term}&retmax={retmax}"
                 f"&sort=relevance&retmode=json", timeout)
        ids = s.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return LiteratureResult(query=query, resolved=[], reachable=True,
                                    note="Source reachable; no matching publications found.")
        summ = _get(f"{EUTILS}/esummary.fcgi?db=pubmed&id={','.join(ids)}&retmode=json", timeout)
        docs = summ.get("result", {})
        resolved = []
        for pmid in ids:
            d = docs.get(pmid, {})
            if not d:
                continue
            resolved.append({
                "pmid": pmid,
                "title": d.get("title", "").rstrip("."),
                "journal": d.get("fulljournalname") or d.get("source", ""),
                "year": (d.get("pubdate", "") or "")[:4],
            })
        return LiteratureResult(query=query, resolved=resolved, reachable=True)
    except Exception as e:  # network blocked, timeout, parse error -> fail closed
        return LiteratureResult(query=query, resolved=[], reachable=False,
                                note=f"Literature source unreachable ({type(e).__name__}); "
                                     f"NO citation attached. Do not fabricate one.")


# --- Query construction: turn a cohort INTENT into PubMed queries ---------------
# The intent ("type 2 diabetes with uncontrolled HbA1c") is phrased for cohort building,
# not for PubMed. Appending a fixed literal suffix ("... phenotype algorithm electronic
# health record") over-constrains esearch and returns nothing. Instead: distill the
# clinical concept (drop operational qualifiers + numeric thresholds), then try
# progressively broader queries and take the FIRST that resolves to real citations.

_OPERATIONAL_STOPWORDS = {
    "build", "builds", "building", "cohort", "cohorts", "of", "a", "an", "the",
    "patients", "patient", "with", "without", "and", "or", "for", "study", "define",
    "defining", "on", "in", "who", "that", "having", "has", "have", "identify",
    "find", "finds", "how", "many", "would", "qualify", "group", "using", "use",
    # operational qualifiers that hurt PubMed term-mapping (not clinical concepts)
    "uncontrolled", "controlled", "poorly", "poor", "well", "high", "low", "elevated",
    "reduced", "screening", "status", "level", "levels", "value", "values", "recent", "most",
}


def _concept_from_intent(intent_text: str) -> str:
    """Distill a PubMed-searchable clinical concept from a cohort intent.

    Drops operational words ("build", "patients", "uncontrolled") and numeric thresholds
    ("9.0", "8.0%"), keeping disease/measure terms (e.g. "type 2 diabetes hba1c"). Keeps
    digits that are part of a name (the "2" in "type 2 diabetes"). Falls back to the raw
    intent if distillation empties it.
    """
    import re
    t = intent_text.lower()
    t = re.sub(r"\b\d+\.\d+%?\b", " ", t)      # decimal thresholds: 9.0, 8.0%
    t = re.sub(r"\b\d+\s*%\b", " ", t)          # integer percentages: 70%
    t = re.sub(r"[^a-z0-9\s]", " ", t)          # punctuation -> space (keeps digits like "2")
    toks = [w for w in t.split()
            if w.isdigit() or (w not in _OPERATIONAL_STOPWORDS and len(w) > 1)]
    core = " ".join(toks).strip()
    return core or intent_text.strip().lower()


def _pubmed_query_tiers(concept: str) -> list:
    """Ordered PubMed queries: most phenotype-relevant first, broadening to a plain floor.

    The first tier biases toward EHR phenotype/cohort-definition papers (what a cohort
    builder wants to cite); the last is the bare concept so a real disease almost always hits.
    """
    # Concept is REQUIRED (AND) in every tier so results are actually ABOUT it; the
    # phenotype/cohort flavor only re-orders within that, and the last tier is the bare
    # concept as a floor. Combined with sort=relevance this keeps precision high.
    return [
        f'{concept} AND (phenotype OR "cohort identification" OR "computable phenotype")',
        f"{concept} AND cohort",
        concept,
    ]


def search_pubmed_best(intent_text: str, retmax: int = 3, timeout: int = 15) -> LiteratureResult:
    """Distill the cohort intent to a concept and try progressively broader PubMed queries,
    returning the FIRST that resolves to real citations. Fails closed on unreachable.

    This is what makes citations actually show up: the query is derived from the phenotype
    (e.g. "type 2 diabetes hba1c") rather than the literal cohort phrasing.
    """
    concept = _concept_from_intent(intent_text)
    last = None
    for q in _pubmed_query_tiers(concept):
        res = search_pubmed(q, retmax=retmax, timeout=timeout)
        if not res.reachable:
            return res                     # network down -> fail closed immediately
        last = res
        if res.resolved:
            res.note = f"Matched PubMed on: {q!r}"
            return res
    return last or LiteratureResult(query=concept, resolved=[], reachable=True,
                                    note="Source reachable; no matching publications found.")


def format_literature(res: LiteratureResult) -> str:
    """Readout. Verified citations only; otherwise an explicit unverified notice."""
    if res.is_verified():
        lines = ["**Published references (verified against PubMed):**"]
        for c in res.resolved:
            lines.append(f"  - PMID {c['pmid']}: {c['title']} — {c['journal']} ({c['year']})")
        return "\n".join(lines)
    if res.reachable:
        return ("**Literature:** source reachable, but no matching publication found for "
                "this phenotype query. No citation attached (none fabricated).")
    return (f"**Literature:** {res.note} State the clinical rationale in prose if useful, "
            "but attach NO PMID.")


def verify_citations(candidates: list, timeout: int = 15) -> LiteratureResult:
    """Deterministic gate for citations Genie retrieved from a connected MCP server.

    Architecture A: the AGENT (Genie) calls its connected literature MCP server and
    passes the raw results here. This function RESOLVES each candidate against PubMed
    and keeps ONLY those that exist — so an MCP server that returns junk, or a model
    that fabricated around the MCP call, cannot introduce a bad citation. The
    anti-fabrication guarantee lives in THIS code, not in the agent.

    candidates: list of PMIDs (str) or dicts with a 'pmid' key. Anything without a
    resolvable PMID is dropped (a title-only citation cannot be verified -> excluded).

    Returns a LiteratureResult with only verified entries. If the resolver itself
    cannot reach PubMed, reachable=False and NOTHING is asserted (fail closed).
    """
    pmids = []
    for c in candidates or []:
        pmid = c.get("pmid") if isinstance(c, dict) else str(c)
        if pmid and str(pmid).strip().isdigit():
            pmids.append(str(pmid).strip())

    if not pmids:
        return LiteratureResult(query="mcp-verify", resolved=[], reachable=True,
                                note="No resolvable PMIDs among MCP results; nothing verified, "
                                     "nothing fabricated.")
    verified, any_reachable = [], False
    for pmid in pmids:
        meta = resolve_citation(pmid, timeout=timeout)
        if meta is not None:
            any_reachable = True
            verified.append(meta)
    if not verified and not any_reachable:
        return LiteratureResult(query="mcp-verify", resolved=[], reachable=False,
                                note="Could not reach PubMed to verify MCP citations; "
                                     "NONE attached (not fabricated).")
    return LiteratureResult(query="mcp-verify", resolved=verified, reachable=True,
                            note=f"Verified {len(verified)}/{len(pmids)} MCP-supplied citations.")


def literature_for_cohort(intent_text: str, mcp_candidates: list | None = None,
                          timeout: int = 15) -> LiteratureResult:
    """Precedence chain for the cohort skill's literature step.

    1. If Genie supplied MCP-retrieved candidates -> verify them (kept only if resolvable).
    2. Else -> direct PubMed search (the floor that works with no MCP server).
    3. Either way, fails closed: no verified source -> no citation, never fabricated.
    """
    if mcp_candidates:
        res = verify_citations(mcp_candidates, timeout=timeout)
        if res.is_verified():
            res.note = "Source: connected MCP literature server (verified). " + res.note
            return res
        # MCP produced nothing usable -> fall through to the direct floor.
    res = search_pubmed_best(intent_text, timeout=timeout)
    if res.is_verified():
        res.note = "Source: direct PubMed (no MCP citations verified). " + res.note
    return res


def resolve_citation(pmid: str, timeout: int = 15) -> dict | None:
    """Confirm a specific PMID exists and return its metadata, else None.

    Use to CHECK a citation before repeating it (catches the baseline's wrong-PMID case,
    e.g. 22319177 being an unrelated paper). Returns None on any failure -> do not cite.
    """
    try:
        summ = _get(f"{EUTILS}/esummary.fcgi?db=pubmed&id={pmid}&retmode=json", timeout)
        d = summ.get("result", {}).get(pmid, {})
        if not d or d.get("error"):
            return None
        return {"pmid": pmid, "title": d.get("title", "").rstrip("."),
                "journal": d.get("fulljournalname") or d.get("source", ""),
                "year": (d.get("pubdate", "") or "")[:4]}
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    intent = sys.argv[1] if len(sys.argv) > 1 else "type 2 diabetes with uncontrolled HbA1c"
    print(f"intent: {intent!r}  ->  concept: {_concept_from_intent(intent)!r}\n")
    r = literature_for_cohort(intent)
    print(format_literature(r))
    if r.note:
        print(f"[{r.note}]")
    print()
    # Prove the wrong-PMID guard: 22319177 was the baseline's fabricated Kho cite.
    got = resolve_citation("22319177")
    print("PMID 22319177 resolves to:", got["title"][:60] if got else "unresolved")
