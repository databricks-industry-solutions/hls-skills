"""Document/image de-identification (Phase 4) — parse -> detect -> redact -> governed derivative.

File de-id yields a DERIVED ASSET (a redacted text derivative), not a UC view over a table, so it
gets its own vetted entrypoints (kept distinct from run_deid for a clean permission review):
  - preview_document_deid_options : READ-ONLY. Parse the docs, detect PHI, surface the plan + the
                                    surface-and-choose sheet. Builds nothing.
  - apply_document_deid           : parse (ai_parse_document) -> redact PHI in the extracted text ->
                                    write a governed redacted derivative + a SEPARATELY-GOVERNED,
                                    reversible surrogate->raw crosswalk -> residual-leak scan.

Reversible provenance (locked decision): every redacted record carries a NON-PHI surrogate key
(random uuid, NOT derived from PHI) and a crosswalk (surrogate -> raw doc) lives in a separate
locked schema, so there is always a governed path back — Safe Harbor 164.514(c)-compatible.

The PHI patterns are defined ONCE here (pure) and reused by both the Python detector (unit-tested)
and the SQL redaction, so detection and redaction can never drift apart. NOTE: the name rule is
demo-simplified (it targets a 'Name:' field); production name detection needs NER / ai_extract.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apply_uc_governance import Q                                      # noqa: E402
from deid_interactions import normalize_delivery, format_decisions, Decision  # noqa: E402


# (class, python_regex, sql_regex, replacement). VALUE patterns first, then the field rule.
PHI_SPECS = [
    ("ssn",   r"\b\d{3}-\d{2}-\d{4}\b",                      r"[0-9]{3}-[0-9]{2}-[0-9]{4}",                 "[SSN]"),
    ("mrn",   r"\bMRN\d{4,}\b",                              r"MRN[0-9]{4,}",                               "[MRN]"),
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", "[EMAIL]"),
    ("phone", r"\(\d{3}\)\s*\d{3}-\d{4}",                    r"\\([0-9]{3}\\) ?[0-9]{3}-[0-9]{4}",          "[PHONE]"),
    ("name",  r"(?im)^Name:\s*.+$",                          r"(?m)^Name:.*$",                              "Name: [NAME]"),
]
# Residual scan checks only VALUE classes (a redacted 'Name: [NAME]' line is not a leak).
_RESIDUAL_CLASSES = ("ssn", "mrn", "email", "phone")


# --- Pure helpers (unit-tested; no SDK) ---------------------------------------

def detect_phi_spans(text: str) -> list:
    """Return [(phi_class, matched_value)] for every PHI match in `text` (recall-biased)."""
    import re
    found = []
    for klass, py, _sql, _rep in PHI_SPECS:
        for m in re.finditer(py, text or ""):
            found.append((klass, m.group(0)))
    return found


def redact_text(text: str) -> tuple[str, dict]:
    """Mask every detected PHI span. Returns (redacted_text, {class: count}). Deterministic."""
    import re
    counts = {}
    out = text or ""
    for klass, py, _sql, rep in PHI_SPECS:
        out, n = re.subn(py, rep, out)
        if n:
            counts[klass] = counts.get(klass, 0) + n
    return out, counts


def residual_phi(text: str) -> list:
    """Re-scan a REDACTED string for surviving PHI VALUE patterns. Any hit is a hard failure."""
    import re
    hits = []
    for klass, py, _sql, _rep in PHI_SPECS:
        if klass in _RESIDUAL_CLASSES and re.search(py, text or ""):
            hits.append(klass)
    return hits


def redaction_sql(col: str) -> str:
    """Build the nested regexp_replace SQL that redacts `col`, using the SAME patterns as the
    Python redactor so SQL and Python never drift. Applied server-side over the parsed text."""
    expr = col
    for _klass, _py, sql, rep in PHI_SPECS:
        expr = f"regexp_replace({expr}, '{sql}', '{rep}')"
    return expr


def _document_decisions() -> list:
    """Surface-and-choose sheet for document de-id (mirrors the structured one, doc-flavored)."""
    return [
        Decision(key="redaction_strategy", title="How should detected PHI be handled?",
                 options=[{"label": "Mask (irreversible)", "value": "mask"},
                          {"label": "Tokenize (re-linkable via the locked crosswalk)", "value": "tokenize"}],
                 note="Direct identifiers are masked in the derivative; reversibility is via the crosswalk."),
        Decision(key="reversible_linkage", title="Keep a governed path back to the original?",
                 options=[{"label": "Yes — locked surrogate->raw crosswalk (default)", "value": True},
                          {"label": "No — one-way, no crosswalk", "value": False}],
                 note="Locked crosswalk is Safe Harbor 164.514(c)-compatible (surrogate not PHI-derived)."),
        Decision(key="output_delivery", title="How should the result be delivered?",
                 options=[{"label": "Governed derivative table (default)", "value": "uc_view"},
                          {"label": "A generated notebook", "value": "notebook"},
                          {"label": "Conversation-only (plan; nothing persisted)", "value": "conversation"}]),
    ]


# --- Live entrypoints ---------------------------------------------------------

def _parse_staged(q: Q, docs_glob: str, staged: str, id_regex: str):
    """Parse docs -> staged (surrogate_key, doc_id, raw_file_path, text). One uuid per doc, minted
    ONCE here so the derivative and the crosswalk share the same non-PHI surrogate."""
    q(f"""CREATE OR REPLACE TABLE {staged} AS
        SELECT uuid() AS surrogate_key,
               regexp_extract(path, '{id_regex}', 1) AS doc_id,
               path AS raw_file_path,
               array_join(transform(
                 CAST(ai_parse_document(content):document.elements AS ARRAY<STRUCT<content STRING>>),
                 e -> e.content), '\\n') AS text
        FROM read_files('{docs_glob}', format => 'binaryFile')
        WHERE regexp_extract(path, '{id_regex}', 1) <> ''""")


def preview_document_deid_options(docs_glob: str, catalog: str, schema: str,
                                  id_regex: str = r"([^/]+)\\.[^.]+$",
                                  profile: str | None = None, warehouse_id: str | None = None) -> str:
    """READ-ONLY: parse the documents, detect PHI, and surface the per-class counts + the
    surface-and-choose sheet. Materializes a staged parse table but writes no derivative."""
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)
    staged = "clinical_deid_docs_staged"
    _parse_staged(q, docs_glob, staged, id_regex)
    n = int(q(f"SELECT COUNT(*) FROM {staged}")[0][0])
    counts = {}
    for klass, _py, sql, _rep in PHI_SPECS:
        c = int(q(f"SELECT COUNT(*) FROM {staged} WHERE text RLIKE '{sql}'")[0][0])
        counts[klass] = c
    lines = ["## Document de-identification preview (read-only)", "",
             f"Parsed **{n}** document(s). PHI detected (docs containing each class):"]
    for klass, c in counts.items():
        lines.append(f"  - **{klass}**: {c}")
    lines.append(format_decisions(_document_decisions()))
    lines += ["", "Then call `apply_document_deid(docs_glob, catalog, schema, ...)` with your choices."]
    return "\n".join(lines)


def apply_document_deid(docs_glob: str, catalog: str, schema: str,
                        derivative_table: str = "clinical_deid_docs_deid",
                        reid_schema: str | None = None, keep_crosswalk: bool = True,
                        output_delivery: str | None = None, confirmed: bool = False,
                        id_regex: str = r"([^/]+)\\.[^.]+$",
                        profile: str | None = None, warehouse_id: str | None = None) -> str:
    """Parse -> redact -> governed derivative + reversible locked crosswalk -> residual scan.

    Produces:
      - <derivative_table>            : (surrogate_key, redacted_text) — consumer-readable, NO raw link.
      - <reid_schema>.<...>_crosswalk : (surrogate_key, raw_doc_id, raw_file_path) — SEPARATELY governed,
                                        the only path back to the original (lock it to a re-id role).
    Returns the analyst readout incl. the residual-leak verdict (hard FAIL on any surviving PHI value).

    CONFIRM-GATE (mirrors cohort's run_cohort): the surface-and-choose choices — redaction_strategy,
    reversible_linkage, output_delivery — are the USER'S to make. Unless `confirmed=True`, this BUILDS
    NOTHING and returns the read-only preview + the decision sheet + a STOP, so Genie must show the
    options, get the user's choice, and call again with confirmed=True. Surfacing already happens via
    the preview step under SKILL.md guidance; this gate HARDENS it so it can never be skipped even if
    a caller invokes apply directly.
    """
    if not confirmed:
        return (preview_document_deid_options(docs_glob, catalog, schema, id_regex=id_regex,
                                              profile=profile, warehouse_id=warehouse_id)
                + "\n\n**STOP: do not pick the redaction strategy, reversibility, or delivery "
                  "yourself. Present the options above to the user, then call apply_document_deid "
                  "again with their choices AND `confirmed=True`.**")
    delivery = normalize_delivery(output_delivery)
    reid_schema = reid_schema or f"{schema}_reid_locked"
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)
    staged = "clinical_deid_docs_staged"
    _parse_staged(q, docs_glob, staged, id_regex)
    n = int(q(f"SELECT COUNT(*) FROM {staged}")[0][0])

    if delivery == "conversation":
        counts = {k: int(q(f"SELECT COUNT(*) FROM {staged} WHERE text RLIKE '{sql}'")[0][0])
                  for k, _py, sql, _rep in PHI_SPECS}
        return (f"### Document de-id (conversation-only — nothing persisted)\n"
                f"Parsed {n} document(s); PHI detected per class: {counts}. "
                f"No derivative or crosswalk written (output_delivery=conversation).")

    # Redacted derivative (surrogate + redacted text ONLY — no raw doc_id/path in the shareable copy).
    q(f"""CREATE OR REPLACE TABLE {derivative_table} AS
        SELECT surrogate_key, {redaction_sql('text')} AS redacted_text FROM {staged}""")

    # Reversible, separately-governed crosswalk (the only path back to the raw document).
    crosswalk_ref = "(no crosswalk — one-way de-id)"
    if keep_crosswalk:
        q(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{reid_schema}")
        xwalk = f"{catalog}.{reid_schema}.{derivative_table}_crosswalk"
        q(f"""CREATE OR REPLACE TABLE {xwalk} AS
            SELECT surrogate_key, doc_id AS raw_doc_id, raw_file_path FROM {staged}""")
        crosswalk_ref = f"{xwalk} (LOCK to a re-identification role — do NOT grant to the analyst role)"

    # Residual-leak scan on the OUTPUT derivative: any surviving PHI VALUE pattern is a hard FAIL.
    residual_sql = " OR ".join(f"redacted_text RLIKE '{sql}'"
                               for k, _py, sql, _rep in PHI_SPECS if k in _RESIDUAL_CLASSES)
    leaks = int(q(f"SELECT COUNT(*) FROM {derivative_table} WHERE {residual_sql}")[0][0])
    passed = leaks == 0

    lines = ["### Document de-identification — complete", "",
             f"**Parsed + redacted:** {n} document(s) → `{catalog}.{schema}.{derivative_table}` "
             f"(surrogate_key + redacted_text; no raw identifiers).",
             f"**Reversible crosswalk:** {crosswalk_ref}",
             f"**Residual-leak scan:** {'PASS — 0 surviving PHI values.' if passed else f'FAIL — {leaks} doc(s) still contain a PHI value. DO NOT SHARE.'}",
             "", "*Processed against Safe Harbor, pending Privacy Officer review — never 'de-identified/HIPAA compliant'.*"]
    return "\n".join(lines)
