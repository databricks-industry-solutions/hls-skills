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
        s = _get(f"{EUTILS}/esearch.fcgi?db=pubmed&term={term}&retmax={retmax}&retmode=json", timeout)
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
    res = search_pubmed(f"{intent_text} phenotype algorithm electronic health record",
                        timeout=timeout)
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
    r = search_pubmed("type 2 diabetes uncontrolled HbA1c electronic phenotype algorithm")
    print(format_literature(r))
    print()
    # Prove the wrong-PMID guard: 22319177 was the baseline's fabricated Kho cite.
    got = resolve_citation("22319177")
    print("PMID 22319177 resolves to:", got["title"][:60] if got else "unresolved")
