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

Redaction is LAYERED (each layer owns what it is actually good at):
  1. MEMBER / RELATIVE name layer — the patient/member is the data subject, so the member's
     name is extracted from the face-sheet field (Patient/Member Name) and every occurrence of
     its tokens (incl. the shared family surname) is redacted throughout; relatives' names are
     redacted after a relationship cue ("husband Robert" -> "husband [NAME]"). PROVIDER names
     are kept on purpose (not the member's identifiers; keeps the record clinically useful).
  2. MODEL layer — `ai_mask` masks the no-fixed-format identifiers regex cannot catch (street
     addresses, geographic detail, written-out dates, and format-less IDs). It is called
     PER LINE (parse the doc, explode to lines, mask each, regroup) because ai_mask recall
     collapses on a long whole-document string — chunking keeps every input short. Note the
     'person name' label is deliberately NOT used, so providers are not masked here either.
  3. REGEX layer (PHI_SPECS) — deterministic, defined ONCE and shared by the Python detector
     (unit-tested) and the SQL redactor so they never drift. This is the ONLY layer the
     residual-leak gate can prove: SSN (incl. masked ***-**-#### and "ending in ####"),
     phone/fax, email, MRN (incl. dash format), DEA (incl. dash), labeled account/policy/NPI
     IDs, URL, IP, dates.

The model and member layers are ADDITIVE recall — a model can miss, and a member name the
field-extractor doesn't find is not redacted — so Privacy-Officer review remains required;
never claim "de-identified / HIPAA compliant" on this output alone. Relatives' bare first
names can remain (only the shared surname is removed via the member tokens).
"""

from __future__ import annotations

import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apply_uc_governance import Q                                      # noqa: E402
from deid_interactions import normalize_delivery, format_decisions, Decision  # noqa: E402


# --- Deterministic regex layer -----------------------------------------------
# (class, python_regex, sql_regex, replacement). IDs before dates so a dash-format MRN like
# MRN-2024-00847291 is consumed as an MRN, not split as a date. SQL regexes double their
# backslashes so the SQL string literal yields single ones. There is NO name rule here — names
# are handled by the member-name layer (patient only; providers kept), not by regex.
PHI_SPECS = [
    ("ssn",         r"\b\d{3}-\d{2}-\d{4}\b",                 r"[0-9]{3}-[0-9]{2}-[0-9]{4}",                 "[SSN]"),
    ("ssn_masked",  r"\*{3}-?\*{2}-?\d{4}",                   r"\\*{3}-?\\*{2}-?[0-9]{4}",                   "[SSN]"),
    ("ssn_partial", r"(?i)ending in \d{4}\b",                 r"(?i)ending in [0-9]{4}",                     "[SSN]"),
    ("mrn",         r"(?i)\bMRN[-:#]? ?\d[0-9A-Za-z-]{3,}",   r"(?i)MRN[-:#]? ?[0-9][0-9A-Za-z-]{3,}",       "[MRN]"),
    ("dea",         r"(?i)\bDEA[ :#]*[A-Za-z]{2}[- ]?\d{7}",  r"(?i)DEA[ :#]*[A-Za-z]{2}[- ]?[0-9]{7}",      "[DEA]"),
    # value token must contain a DIGIT so real IDs match ("ACCT-CVH-9938471", "Group number 445566")
    # but plain prose after the keyword does not ("account balance", "group of patients"). The
    # filler group (?:...no|number|run|...)* absorbs multi-word labels ("EMS run number 44821",
    # "radiology accession number RAD-..."); the optional (?:</td><td>) lets a label and its value
    # sit in adjacent HTML table cells ("Accession Number:</td><td>RAD-2026-VT-091244829").
    ("labeled_id",  r"(?i)\b(acct|account|policy|group|grp|member|subscriber|beneficiary|medicare|medicaid|accession|specimen|rx|prescription|ems|dict|dictation|npi|dea)(?:[\s#:.-]+(?:no\.?|number|num|id|#|run|order|record))*[\s#:.-]*(?:</td>\s*<td>\s*)?([A-Za-z0-9][A-Za-z0-9-]*\d[A-Za-z0-9-]*)",
                    r"(?i)(acct|account|policy|group|grp|member|subscriber|beneficiary|medicare|medicaid|accession|specimen|rx|prescription|ems|dict|dictation|npi|dea)([\\s#:.-]+(no\\.?|number|num|id|#|run|order|record))*[\\s#:.-]*(</td>\\s*<td>\\s*)?([A-Za-z0-9][A-Za-z0-9-]*[0-9][A-Za-z0-9-]*)", "[ID]"),
    ("phone",       r"\(\d{3}\)\s*\d{3}-\d{4}",               r"\\([0-9]{3}\\) ?[0-9]{3}-[0-9]{4}",          "[PHONE]"),
    ("phone_dash",  r"\b\d{3}-\d{3}-\d{4}\b",                 r"[0-9]{3}-[0-9]{3}-[0-9]{4}",                 "[PHONE]"),
    ("phone_dot",   r"\b\d{3}\.\d{3}\.\d{4}\b",               r"[0-9]{3}\\.[0-9]{3}\\.[0-9]{4}",             "[PHONE]"),
    ("email",       r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", "[EMAIL]"),
    ("url",         r"https?://\S+",                          r"https?://\\S+",                              "[URL]"),
    ("ip",          r"\b\d{1,3}(\.\d{1,3}){3}\b",             r"[0-9]{1,3}(\\.[0-9]{1,3}){3}",               "[IP]"),
    ("date",        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",           r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}",           "[DATE]"),
    ("date_iso",    r"\b\d{4}-\d{2}-\d{2}\b",                 r"[0-9]{4}-[0-9]{2}-[0-9]{2}",                 "[DATE]"),
]
# All regex classes are deterministic VALUE/ID patterns, so all are residual-checkable.
_RESIDUAL_CLASSES = tuple(k for (k, _p, _s, _r) in PHI_SPECS)

# Model layer: ai_mask handles the no-fixed-format identifiers — addresses, geographic detail,
# written-out dates, and format-less IDs. 'person name' is intentionally OMITTED so PROVIDER
# names are not masked (the member name is handled separately). <= 20 labels (ai_mask's cap).
AI_MASK_LABELS = [
    "street address", "city", "county", "zip code",
    "date of birth", "date", "age over 89", "fax number",
    "medical record number", "health plan beneficiary number", "insurance policy number",
    "account number", "medicare beneficiary identifier", "national provider identifier",
    "dea number", "license number", "device serial number",
    "employer or workplace name", "school or university name", "organization name",
]

# Member-name field extraction, defined ONCE as a Python regex; the SQL form is DERIVED from it
# (backslashes doubled, single quotes escaped) so the two can never drift. Two alternatives:
#   (a) "Patient/Member Name:" (plain or table cell) — the common face-sheet field, and
#   (b) a bare "Patient:/Member:" ONLY in a table cell ("Patient:</td><td>Whittfield, ...") — this
#       catches a SECOND patient field elsewhere in the record whose surname may be MISSPELLED, so
#       ALL matches are collected and their tokens unioned (so "Whitfield" AND "Whittfield" redact).
# The bare form requires the </td><td> table cell so prose ("Patient reports...") never triggers.
# Terminator stops at </td>, a comma (handles "Last, First"), or newline.
_MEMBER_PATTERN = (r"(?is)(?:(?:Patient|Member|Insured|Subscriber)\s*Name\s*:?\s*(?:</td>\s*<td>\s*)?"
                   r"|(?:Patient|Member)\s*:?\s*</td>\s*<td>\s*)"
                   r"([A-Z][A-Za-z.' -]{1,60}?)\s*(?:</td>|,|\n|$)")
_MEMBER_PY_RE = re.compile(_MEMBER_PATTERN)
MEMBER_NAME_RE = _MEMBER_PATTERN.replace("\\", "\\\\").replace("'", "''")   # SQL-literal form

# Employer/workplace is Safe-Harbor identifier class 15. Extract the face-sheet "Employer:" field
# value and redact that exact phrase everywhere (deterministic); the model layer additionally
# masks narrative employer/school mentions. Stops before a trailing "(Retired ...)" note.
_EMPLOYER_PATTERN = (r"(?i)\bEmployer\s*(?::\s*(?:</td>\s*<td>\s*)?|</td>\s*<td>\s*)"
                     r"(?-i:([A-Z][A-Za-z0-9 .,'&-]{2,60}?))\s*(?:</td>|\n|\(|$)")
_EMPLOYER_PY_RE = re.compile(_EMPLOYER_PATTERN)
EMPLOYER_RE = _EMPLOYER_PATTERN.replace("\\", "\\\\").replace("'", "''")

# Relatives of the member are Safe-Harbor identifiers too. Redact the NAME that follows a
# relationship cue while KEEPING the cue word (so "husband Robert" -> "husband [NAME]", and the
# clinical meaning survives). Group 1 = cue, group 2 = separator, group 3 = name (dropped). Defined
# once; the SQL form is derived. Capitalized name only, so lowercase prose ("father of three",
# "mother was admitted") is not touched.
_RELATIVE_PATTERN = (
    r"(?i)\b(husband|wife|spouse|son|daughter|child|children|mother|father|brother|sister|"
    r"sibling|grandson|granddaughter|grandchild|parent|guardian|partner|fiance|fiancee|"
    r"emergency contact|next of kin)\b([:\s]+(?:is |was |named )?)"
    r"((?-i:[A-Z][a-z]+(?:[-\s][A-Z][a-z]+){0,2}))")   # (?-i:) = capitalized name only
_RELATIVE_PY_RE = re.compile(_RELATIVE_PATTERN)
_RELATIVE_SQL = _RELATIVE_PATTERN.replace("\\", "\\\\").replace("'", "''")


# --- Pure helpers (unit-tested; no SDK) ---------------------------------------

def detect_phi_spans(text: str) -> list:
    """Return [(phi_class, matched_value)] for every regex PHI match (recall-biased)."""
    found = []
    for klass, py, _sql, _rep in PHI_SPECS:
        for m in re.finditer(py, text or ""):
            found.append((klass, m.group(0)))
    return found


def redact_text(text: str) -> tuple[str, dict]:
    """Apply the REGEX layer only (deterministic). Returns (redacted_text, {class: count}).
    Names/addresses are handled by the member + model layers (SQL-side), not here."""
    counts = {}
    out = text or ""
    for klass, py, _sql, rep in PHI_SPECS:
        out, n = re.subn(py, rep, out)
        if n:
            counts[klass] = counts.get(klass, 0) + n
    return out, counts


def residual_phi(text: str) -> list:
    """Re-scan a REDACTED string for surviving regex PHI patterns. Any hit is a hard failure."""
    hits = []
    for klass, py, _sql, _rep in PHI_SPECS:
        if klass in _RESIDUAL_CLASSES and re.search(py, text or ""):
            hits.append(klass)
    return hits


def extract_member_name(text: str) -> str:
    """Extract member/patient name(s) from ALL patient-name fields, space-joined (pure mirror of
    the SQL regexp_extract_all path). Collecting all matches unions tokens across fields, so a
    misspelled surname in a second field is redacted too. Returns '' if none found."""
    return " ".join(m.strip() for m in _MEMBER_PY_RE.findall(text or "") if m.strip())


def extract_employer(text: str) -> str:
    """Extract the employer/workplace phrase from the face-sheet 'Employer:' field. '' if none."""
    m = _EMPLOYER_PY_RE.search(text or "")
    return m.group(1).strip() if m else ""


def member_name_tokens(member: str) -> list:
    """Name tokens (len > 1) of the member, for redaction. Splits on non-letters so a
    hyphenated/compound name yields each part; the surname token removes the whole family."""
    return [t for t in re.split(r"[^A-Za-z]+", member or "") if len(t) > 1]


def redact_member(text: str, member: str) -> str:
    """Redact every occurrence of the member's name tokens (pure mirror of the SQL layer)."""
    toks = member_name_tokens(member)
    if not toks:
        return text or ""
    pat = r"(?i)\b(" + "|".join(re.escape(t) for t in toks) + r")\b"
    return re.sub(pat, "[NAME]", text or "")


def redact_relatives(text: str) -> str:
    """Redact the name following a relationship cue, keeping the cue (pure mirror of SQL)."""
    return _RELATIVE_PY_RE.sub(r"\1\2[NAME]", text or "")


def redact_family(text: str, member: str) -> str:
    """Redact relatives who share the member's surname: 1-2 capitalized names immediately before a
    member surname token ("Robert James Whitfield", "Thomas Whitfield") -> [NAME]. Keyed on the
    member's own surname, so providers (referred to as 'Dr. <Surname>') are not affected. Pure
    mirror of the SQL layer. Case-sensitive leading names so lowercase prose is untouched."""
    anchors = [t for t in member_name_tokens(member) if len(t) >= 5]
    if not anchors:
        return text or ""
    pat = r"(?:[A-Z][A-Za-z'-]+ ){1,2}(?:" + "|".join(re.escape(t) for t in anchors) + r")"
    return re.sub(pat, "[NAME]", text or "")


def redact_employer(text: str, employer: str) -> str:
    """Redact the exact employer phrase everywhere (case-insensitive, literal — pure mirror)."""
    if not employer:
        return text or ""
    return re.sub(re.escape(employer), "[EMPLOYER]", text or "", flags=re.I)


# --- SQL builders -------------------------------------------------------------

def _ai_mask_labels_array() -> str:
    return "array(" + ", ".join("'" + lbl.replace("'", "''") + "'" for lbl in AI_MASK_LABELS) + ")"


def redaction_sql(col: str) -> str:
    """Nested regexp_replace for the deterministic regex layer, using the SAME patterns as the
    Python redactor so SQL and Python never drift. `col` may be any SQL expression (e.g. the
    member-redaction expression), so the regex layer wraps it."""
    expr = col
    for _klass, _py, sql, rep in PHI_SPECS:
        expr = f"regexp_replace({expr}, '{sql}', '{rep}')"
    return expr


def _relative_redaction_sql(text_expr: str) -> str:
    """Redact names after a relationship cue, keeping the cue ($1$2 are the cue + separator)."""
    return f"regexp_replace({text_expr}, '{_RELATIVE_SQL}', '$1$2[NAME]')"


def _family_redaction_sql(text_expr: str, member_expr: str) -> str:
    """Redact 1-2 capitalized names before a member surname token (shared-surname relatives).
    Anchors are member tokens of length >= 5; case-sensitive leading names (no (?i))."""
    toks5 = (f"array_join(filter(split(regexp_replace({member_expr}, '[^A-Za-z ]', ' '), ' '), "
             f"x -> length(x) >= 5), '|')")
    pat = f"concat('(?:[A-Z][A-Za-z''-]+ ){{1,2}}(', {toks5}, ')')"
    return (f"CASE WHEN {toks5} <> '' THEN regexp_replace({text_expr}, {pat}, '[NAME]') "
            f"ELSE {text_expr} END")


def _employer_redaction_sql(text_expr: str, employer_expr: str) -> str:
    """Redact the extracted employer phrase everywhere (case-insensitive). The phrase is a COLUMN
    value (not a SQL literal), used directly as the pattern; these phrases are alphanumeric so no
    metachar escaping is needed. Passes through unchanged when no employer was found."""
    return (f"CASE WHEN {employer_expr} <> '' "
            f"THEN regexp_replace({text_expr}, concat('(?i)', {employer_expr}), '[EMPLOYER]') "
            f"ELSE {text_expr} END")


def _member_redaction_sql(text_expr: str, member_expr: str) -> str:
    """Redact the member's name tokens in `text_expr`. Tokens are derived in-SQL from the
    extracted member name (letters only, len > 1). Guarded: if no usable token, pass through
    unchanged (never build an empty alternation that would match everywhere)."""
    toks = (f"array_join(filter(split(regexp_replace({member_expr}, '[^A-Za-z ]', ' '), ' '), "
            f"x -> length(x) > 1), '|')")
    pat = f"concat('(?i)\\\\b(', {toks}, ')\\\\b')"
    return (f"CASE WHEN {member_expr} <> '' AND {toks} <> '' "
            f"THEN regexp_replace({text_expr}, {pat}, '[NAME]') ELSE {text_expr} END")


def _chunked_mask_cte(staged: str, model_masking: bool) -> str:
    """A `WITH reg AS (...)` CTE producing (surrogate_key, member, masked). When model_masking,
    the doc is exploded to lines, ai_mask runs PER LINE (short inputs -> high recall), and the
    lines are regrouped in order; otherwise `masked` is just the raw text."""
    if not model_masking:
        return f"WITH reg AS (SELECT surrogate_key, member, employer, text AS masked FROM {staged})"
    return (
        f"WITH ex AS (SELECT surrogate_key, member, employer, pos, "
        f"ai_mask(line, {_ai_mask_labels_array()}) AS m "
        f"FROM (SELECT surrogate_key, member, employer, posexplode(split(text, '\\n')) AS (pos, line) "
        f"FROM {staged})), "
        f"reg AS (SELECT surrogate_key, max(member) AS member, max(employer) AS employer, "
        f"array_join(transform(array_sort(collect_list(struct(pos, m))), s -> s.m), '\\n') AS masked "
        f"FROM ex GROUP BY surrogate_key)"
    )


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
    """Parse docs -> staged (surrogate_key, doc_id, raw_file_path, text, member). One uuid per
    doc, minted ONCE here so the derivative and the crosswalk share the same non-PHI surrogate.
    The member name is extracted from the face-sheet field for the member-name redaction layer."""
    q(f"""CREATE OR REPLACE TABLE {staged} AS
        SELECT *,
               trim(array_join(regexp_extract_all(text, '{MEMBER_NAME_RE}', 1), ' ')) AS member,
               trim(regexp_extract(text, '{EMPLOYER_RE}', 1)) AS employer
        FROM (
          SELECT uuid() AS surrogate_key,
                 regexp_extract(path, '{id_regex}', 1) AS doc_id,
                 path AS raw_file_path,
                 array_join(transform(
                   CAST(ai_parse_document(content):document.elements AS ARRAY<STRUCT<content STRING>>),
                   e -> e.content), '\\n') AS text
          FROM read_files('{docs_glob}', format => 'binaryFile')
          WHERE regexp_extract(path, '{id_regex}', 1) <> '')""")


def preview_document_deid_options(docs_glob: str, catalog: str, schema: str,
                                  id_regex: str = r"([^/]+)\\.[^.]+$",
                                  profile: str | None = None, warehouse_id: str | None = None) -> str:
    """READ-ONLY: parse the documents, detect PHI, and surface the per-class counts + the
    surface-and-choose sheet. Materializes a staged parse table but writes no derivative."""
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)
    # Unique staged table per call so concurrent sessions never collide on a shared name.
    staged = f"deid_preview_staged_{uuid.uuid4().hex[:8]}"
    _parse_staged(q, docs_glob, staged, id_regex)
    n = int(q(f"SELECT COUNT(*) FROM {staged}")[0][0])
    detected = int(q(f"SELECT COUNT(*) FROM {staged} WHERE member <> ''")[0][0])
    counts = {}
    for klass, _py, sql, _rep in PHI_SPECS:
        counts[klass] = int(q(f"SELECT COUNT(*) FROM {staged} WHERE text RLIKE '{sql}'")[0][0])
    q(f"DROP TABLE IF EXISTS {staged}")
    lines = ["## Document de-identification preview (read-only)", "",
             f"Parsed **{n}** document(s). Deterministic (regex) PHI — docs containing each class:"]
    for klass, c in counts.items():
        lines.append(f"  - **{klass}**: {c}")
    lines += ["",
              f"**Member name** auto-detected from the face sheet in **{detected}/{n}** doc(s) → the "
              "member's name tokens (incl. the family surname) are redacted everywhere; **provider "
              "names are intentionally kept**. If a doc's member is not detected, its name is NOT "
              "redacted — specify it or check the face-sheet field.",
              "**Model layer (`ai_mask`, per line)** additionally masks street **addresses**, "
              "geographic detail, written-out **dates**, and format-less IDs — additive recall, not "
              "shown in the counts and not residual-provable, so Privacy-Officer review remains required."]
    lines.append(format_decisions(_document_decisions()))
    lines += ["", "Then call `apply_document_deid(docs_glob, catalog, schema, ...)` with your choices."]
    return "\n".join(lines)


def apply_document_deid(docs_glob: str, catalog: str, schema: str,
                        derivative_table: str = "clinical_deid_docs_deid",
                        reid_schema: str | None = None, keep_crosswalk: bool = True,
                        output_delivery: str | None = None, confirmed: bool = False,
                        model_masking: bool = True,
                        id_regex: str = r"([^/]+)\\.[^.]+$",
                        profile: str | None = None, warehouse_id: str | None = None) -> str:
    """Parse -> layered redact -> governed derivative + reversible locked crosswalk -> residual scan.

    Produces:
      - <derivative_table>            : (surrogate_key, redacted_text) — consumer-readable, NO raw link.
      - <reid_schema>.<...>_crosswalk : (surrogate_key, raw_doc_id, raw_file_path) — SEPARATELY governed,
                                        the only path back to the original (lock it to a re-id role).
    Returns the analyst readout incl. the residual-leak verdict (hard FAIL on any surviving regex PHI).

    CONFIRM-GATE (mirrors cohort's run_cohort): the surface-and-choose choices — redaction_strategy,
    reversible_linkage, output_delivery — are the USER'S to make. Unless `confirmed=True`, this BUILDS
    NOTHING and returns the read-only preview + the decision sheet + a STOP. `model_masking=False` runs
    deterministic-only (regex + member name, no ai_mask)."""
    if not confirmed:
        return (preview_document_deid_options(docs_glob, catalog, schema, id_regex=id_regex,
                                              profile=profile, warehouse_id=warehouse_id)
                + "\n\n**STOP: do not pick the redaction strategy, reversibility, or delivery "
                  "yourself. Present the options above to the user, then call apply_document_deid "
                  "again with their choices AND `confirmed=True`.**")
    delivery = normalize_delivery(output_delivery)
    reid_schema = reid_schema or f"{schema}_reid_locked"
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)
    # Staged table is namespaced to this run's derivative so concurrent sessions don't collide.
    staged = f"{derivative_table}_staged"
    _parse_staged(q, docs_glob, staged, id_regex)
    n = int(q(f"SELECT COUNT(*) FROM {staged}")[0][0])
    undetected = int(q(f"SELECT COUNT(*) FROM {staged} WHERE member = ''")[0][0])

    if delivery == "conversation":
        counts = {k: int(q(f"SELECT COUNT(*) FROM {staged} WHERE text RLIKE '{sql}'")[0][0])
                  for k, _py, sql, _rep in PHI_SPECS}
        q(f"DROP TABLE IF EXISTS {staged}")
        return (f"### Document de-id (conversation-only — nothing persisted)\n"
                f"Parsed {n} document(s); regex PHI per class: {counts}. Member name detected in "
                f"{n - undetected}/{n}. No derivative or crosswalk written (output_delivery=conversation).")

    # Redacted derivative: chunked ai_mask (model layer) -> member-name redaction -> regex layer.
    cte = _chunked_mask_cte(staged, model_masking)
    # layers over the (chunk-)masked text: employer -> relatives(cue) -> family(shared surname)
    # -> member tokens -> regex. family runs BEFORE member tokens (it anchors on the surname).
    redacted_expr = redaction_sql(_member_redaction_sql(_family_redaction_sql(
        _relative_redaction_sql(_employer_redaction_sql("masked", "employer")), "member"), "member"))
    q(f"""CREATE OR REPLACE TABLE {derivative_table} AS
        {cte}
        SELECT surrogate_key, {redacted_expr} AS redacted_text FROM reg""")

    # Reversible, separately-governed crosswalk (the only path back to the raw document).
    crosswalk_ref = "(no crosswalk — one-way de-id)"
    if keep_crosswalk:
        q(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{reid_schema}")
        xwalk = f"{catalog}.{reid_schema}.{derivative_table}_crosswalk"
        q(f"""CREATE OR REPLACE TABLE {xwalk} AS
            SELECT surrogate_key, doc_id AS raw_doc_id, raw_file_path FROM {staged}""")
        crosswalk_ref = f"{xwalk} (LOCK to a re-identification role — do NOT grant to the analyst role)"

    # --- DETERMINISTIC residual verdict (reproducible; replaces ad-hoc per-session LLM re-scans).
    # Three programmatic checks over the OUTPUT derivative, each run exactly the same way every time.
    residual_sql = " OR ".join(f"redacted_text RLIKE '{sql}'"
                               for k, _py, sql, _rep in PHI_SPECS if k in _RESIDUAL_CLASSES)
    regex_leaks = int(q(f"SELECT COUNT(*) FROM {derivative_table} WHERE {residual_sql}")[0][0])
    _tok = "array_join(filter(split(regexp_replace(s.member,'[^A-Za-z ]',' '),' '), x -> length(x) > 1), '|')"
    member_leaks = int(q(
        f"SELECT COUNT(*) FROM {derivative_table} d JOIN {staged} s ON d.surrogate_key = s.surrogate_key "
        f"WHERE s.member <> '' AND {_tok} <> '' AND d.redacted_text RLIKE concat('(?i)\\\\b(', {_tok}, ')\\\\b')"
    )[0][0])
    employer_leaks = int(q(
        f"SELECT COUNT(*) FROM {derivative_table} d JOIN {staged} s ON d.surrogate_key = s.surrogate_key "
        f"WHERE s.employer <> '' AND d.redacted_text RLIKE concat('(?i)', s.employer)"
    )[0][0])
    det_fail = regex_leaks + member_leaks + employer_leaks
    verdict = "PASS" if det_fail == 0 else f"FAIL — {det_fail} residual item(s). DO NOT SHARE."
    q(f"DROP TABLE IF EXISTS {staged}")   # staged carried raw text; drop once checks are done

    name_note = ("" if undetected == 0 else
                 f" ⚠️ Member name NOT auto-detected in {undetected}/{n} doc(s) — supply it or check the field.")
    lines = ["### Document de-identification — complete", "",
             f"**Parsed + redacted:** {n} document(s) → `{catalog}.{schema}.{derivative_table}` "
             f"(surrogate_key + redacted_text; no raw identifiers).",
             f"**Reversible crosswalk:** {crosswalk_ref}",
             "",
             "**Deterministic residual verdict** (reproducible — report THIS, do not improvise a "
             "separate re-scan):",
             f"  - Fixed-format PHI (SSN/phone/email/MRN/DEA/IDs/URL/IP/dates): **{regex_leaks}** surviving",
             f"  - Member/patient name tokens (incl. misspelled-surname field + family surname): **{member_leaks}** surviving",
             f"  - Employer phrase: **{employer_leaks}** surviving",
             f"  - **Verdict: {verdict}**{name_note}",
             "",
             "**Kept by design** (not member PHI): provider names, facility name/URL, clinical content.",
             "**Model-dependent — NOT deterministically provable, so these ALWAYS require Privacy-Officer "
             "review before sharing:** sub-state geography (towns/counties), narrative employer/school "
             "names, relatives' bare first names, and any identifier the model layer missed.",
             "",
             "*Processed against Safe Harbor, pending Privacy Officer review — never "
             "'de-identified / HIPAA compliant'.*"]
    return "\n".join(lines)
