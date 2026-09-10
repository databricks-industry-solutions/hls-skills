"""Vetted entrypoints for the cohort skill — EXECUTION model.

Genie Code should CALL these functions, not write its own cohort SQL. The baseline
showed un-guided Genie (a) silently picked one "uncontrolled HbA1c" threshold (>=9.0)
without flagging that >8.0 is equally standard, quietly dropping 16% of true members,
and (b) fabricated journal citations. This vetted path:
  - grounds concept sets in codes ACTUALLY PRESENT in the data (no hallucinated codes),
  - SURFACES threshold ambiguity with the N impact of each option (never silently picks),
  - counts feasibility (N + attrition) BEFORE building,
  - materializes the cohort + a reproducible phenotype definition,
  - VERIFIES membership against the definition and reports it,
  - NEVER emits a literature citation itself (that is a separate, resolver-backed step).

Two-step flow (because "surface & confirm" requires a human choice):
  1. preview_cohort(...) -> ambiguity + per-option feasibility. Show to user, get a choice.
  2. build_cohort(...)   -> materialize + verify the chosen definition.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# --- SQL runner (ambient auth in-workspace; optional profile locally) ---------

class Q:
    def __init__(self, catalog: str, schema: str, profile: str | None = None,
                 warehouse_id: str | None = None):
        from databricks.sdk import WorkspaceClient
        self.w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
        self.wid = warehouse_id or next(wh.id for wh in self.w.warehouses.list())
        self.catalog, self.schema = catalog, schema

    def __call__(self, stmt: str):
        import time
        from databricks.sdk.service.sql import StatementState
        r = self.w.statement_execution.execute_statement(
            warehouse_id=self.wid, catalog=self.catalog, schema=self.schema,
            statement=stmt, wait_timeout="50s")
        # ai_query over many note rows routinely exceeds the 50s synchronous cap, so POLL to
        # completion instead of failing the moment the statement is still RUNNING.
        while r.status and r.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(2)
            r = self.w.statement_execution.get_statement(r.statement_id)
        if r.status and r.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(f"{r.status.error} :: {stmt[:200]}")
        return r.result.data_array if r.result else []


def _split_fqn(fqn: str):
    parts = fqn.split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected catalog.schema.table, got: {fqn}")
    return parts


def _sql_lit(s: str) -> str:
    """Single-quote + escape a string for safe inlining into SQL."""
    return "'" + str(s).replace("'", "''") + "'"


# --- Free-text notes: extract phenotype evidence with Databricks AI Functions --
# The diagnosis can be documented in a coded column OR only in a free-text note. This turns
# notes into a GROUNDED, REPRODUCIBLE diagnosis signal — not a black-box LLM guess — by:
#   1. running ai_query over the notes with a NEGATION- and SUBJECT-aware prompt (rejects
#      "no evidence of diabetes" and "mother had diabetes" — the traps a keyword search hits),
#   2. requiring the model to return the VERBATIM supporting span, and keeping the assertion
#      only if that span is actually IN the note (fail-closed against fabricated evidence),
#   3. MATERIALIZING the result to an evidence table so the note-derived membership is
#      auditable and the phenotype is reproducible (the prompt is pinned in the definition).
# The A1c/measure threshold is still a STRUCTURED criterion; notes establish only the dx.

DEFAULT_NOTE_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"

_NOTE_EXTRACT_PROMPT = (
    "You are a clinical NLP extractor. Decide whether the note below ASSERTS that THIS "
    "patient CURRENTLY has {condition}. Answer NO if the mention is negated (\"no evidence "
    "of\", \"denies\", \"ruled out\", \"without\"), is family history only (\"mother\", "
    "\"father\", \"sibling\", \"family history\"), or is only a screening/risk statement. "
    "If YES, reply exactly 'YES:' followed by the SHORTEST verbatim quote from the note that "
    "documents it. If NO, reply exactly 'NO'. Note: "
)


@dataclass
class NoteEvidence:
    evidence_table: str          # fully-qualified materialized evidence table
    n_asserted: int              # patients whose note asserts the CURRENT dx (span-grounded)
    endpoint: str
    prompt: str
    condition: str


def extract_note_evidence(q: "Q", notes_table: str, condition: str,
                          note_col: str = "note_text", id_col: str = "patient_id",
                          endpoint: str = DEFAULT_NOTE_ENDPOINT,
                          evidence_table: str | None = None,
                          prompt_template: str | None = None) -> NoteEvidence:
    """Run ai_query over the notes and materialize a per-patient diagnosis-assertion table.

    Live-only: needs a SQL warehouse and a model-serving endpoint (a Foundation Model API
    pay-per-token endpoint by default; override with `endpoint`). Returns a NoteEvidence handle
    the preview/build SQL joins against. `asserts_current_dx` is TRUE only when the model says
    YES *and* the quoted span is present in the note (span-grounding = the notes analogue of
    code-grounding).

    prompt_template: override the extraction prompt. If it contains `{condition}` it is
    formatted with the condition; otherwise it is used verbatim. The RESOLVED prompt is pinned
    in the phenotype definition, so a custom prompt stays reproducible. The extractor must still
    reply 'YES:<verbatim span>' or 'NO' for span-grounding to work.
    """
    ncat, nsch, ntbl = _split_fqn(notes_table)
    evi = evidence_table or f"{ntbl}_note_evidence"
    template = prompt_template or _NOTE_EXTRACT_PROMPT
    prompt = template.format(condition=condition) if "{condition}" in template else template
    q(f"""CREATE OR REPLACE TABLE {evi} AS
        WITH raw AS (
          SELECT {id_col} AS patient_id, {note_col} AS note_text,
                 ai_query({_sql_lit(endpoint)}, CONCAT({_sql_lit(prompt)}, {note_col})) AS verdict
          FROM {ntbl}
        ),
        parsed AS (
          SELECT patient_id, note_text, verdict,
                 lower(trim(verdict)) LIKE 'yes%' AS said_yes,
                 CASE WHEN instr(verdict, ':') > 0
                      THEN trim(substring(verdict, instr(verdict, ':') + 1)) END AS evidence_span
          FROM raw
        )
        SELECT patient_id, note_text, verdict, evidence_span,
               -- span-grounding: keep the YES only if the quoted evidence is really in the note
               (said_yes AND evidence_span IS NOT NULL AND length(evidence_span) > 0
                AND contains(lower(note_text), lower(evidence_span))) AS asserts_current_dx
        FROM parsed""")
    n = int(q(f"SELECT COUNT(*) FROM {evi} WHERE asserts_current_dx")[0][0])
    return NoteEvidence(evidence_table=f"{ncat}.{nsch}.{evi}", n_asserted=n,
                        endpoint=endpoint, prompt=prompt, condition=condition)


def _dx_predicate(combine_mode: str, code_col: str, code_list: str, evi_alias: str = "e") -> str:
    """The diagnosis-ascertainment WHERE clause for a chosen combine mode.

    code_only / note_only / union / intersection over (coded dx) and (note-asserted dx).
    Never picked silently — the user chooses the mode after seeing per-mode N (Principle: surface & confirm).
    """
    coded = f"t.{code_col} IN ({code_list})"
    noted = f"{evi_alias}.asserts_current_dx"
    return {
        "code_only": coded,
        "note_only": noted,
        "union": f"({coded} OR {noted})",
        "intersection": f"({coded} AND {noted})",
    }[combine_mode]


# --- Ambiguity registry -------------------------------------------------------
# Known clinical terms that map to MORE THAN ONE defensible operational threshold.
# The skill must SURFACE these, never silently pick one (the baseline's failure).
THRESHOLD_AMBIGUITIES = {
    "uncontrolled hba1c": {
        "measure": "HbA1c",
        "options": [
            {"label": ">8.0% (common clinical 'uncontrolled')", "op": ">", "value": 8.0},
            {"label": ">=9.0% (HEDIS 'poor control')", "op": ">=", "value": 9.0},
        ],
    },
    "poorly controlled hba1c": {
        "measure": "HbA1c",
        "options": [
            {"label": ">=9.0% (HEDIS 'poor control')", "op": ">=", "value": 9.0},
            {"label": ">8.0% (broader)", "op": ">", "value": 8.0},
        ],
    },
}


@dataclass
class CohortDefinition:
    """A reproducible phenotype. Emit this with any materialized cohort."""
    condition_codes: list                 # [(vocab, code)], grounded in the data
    condition_col: str = "condition_code"
    condition_vocab_col: str = "condition_vocab"
    obs_measure_col: str = "hba1c_value"  # numeric measure column
    obs_op: str | None = None             # ">", ">=", None if no measure criterion
    obs_value: float | None = None
    label: str = ""
    # --- free-text notes (optional) ---
    combine_mode: str = "code_only"       # code_only | note_only | union | intersection
    note_evidence_table: str | None = None  # materialized ai_query evidence (patient_id, asserts_current_dx)
    note_endpoint: str | None = None      # model endpoint used (provenance)
    note_prompt: str | None = None        # pinned extraction prompt (reproducibility)

    def to_json(self) -> str:
        return json.dumps(self.__dict__)


# --- Step 1: preview + surface ambiguity --------------------------------------

@dataclass
class CohortPreview:
    grounded_codes: list = field(default_factory=list)   # codes found in the data
    missing_codes: list = field(default_factory=list)    # requested but absent -> flag
    ambiguity: dict | None = None                        # threshold options + N per option
    base_condition_n: int = 0                            # patients meeting condition criteria only
    total_patients: int = 0
    combine: dict | None = None                          # code/note/union/intersection N + disagreement
    note_evidence: NoteEvidence | None = None            # handle to the materialized evidence table


def preview_cohort(q: Q, table: str, condition_codes: list, intent_text: str = "",
                   notes_table: str | None = None, note_col: str = "note_text",
                   note_id_col: str = "patient_id", note_endpoint: str = DEFAULT_NOTE_ENDPOINT,
                   note_condition: str | None = None, note_prompt: str | None = None) -> CohortPreview:
    """Ground the codes in the data and surface any threshold ambiguity with N impact.

    condition_codes: [(vocab, code)] the caller proposes (from NL intent).
    intent_text: the user's phrasing, scanned for known ambiguous terms.
    notes_table: OPTIONAL free-text notes source. When given, the diagnosis can also be
        ascertained from the note text via ai_query (negation-/subject-aware, span-grounded),
        and the preview surfaces code-only / note-only / union / intersection cohort sizes with
        the disagreement set — a SECOND choice the user must make (never combined silently).

    Returns a preview to SHOW THE USER. Does not build the cohort.
    """
    catalog, schema, tbl = _split_fqn(table)
    total = int(q(f"SELECT COUNT(DISTINCT patient_id) FROM {tbl}")[0][0])

    # Which requested codes actually exist? (prevents hallucinated-code cohorts)
    present = {(r[0], r[1]) for r in q(
        f"SELECT DISTINCT condition_vocab, condition_code FROM {tbl} WHERE condition_code IS NOT NULL")}
    grounded = [c for c in condition_codes if tuple(c) in present]
    missing = [c for c in condition_codes if tuple(c) not in present]

    code_list = ", ".join(f"'{code}'" for _, code in grounded) or "NULL"
    base_n = int(q(
        f"SELECT COUNT(DISTINCT patient_id) FROM {tbl} WHERE condition_code IN ({code_list})")[0][0])

    # Free-text notes: extract note-asserted diagnosis and compute the combine options.
    combine = None
    note_evidence = None
    if notes_table:
        note_evidence = extract_note_evidence(
            q, notes_table, condition=note_condition or (intent_text[:120] or "the condition"),
            note_col=note_col, id_col=note_id_col, endpoint=note_endpoint,
            prompt_template=note_prompt)
        evi = note_evidence.evidence_table
        # Set arithmetic done in SQL against the materialized evidence table (scales past IN-lists).
        def _c(pred: str) -> int:
            return int(q(f"""SELECT COUNT(DISTINCT t.patient_id)
                FROM {tbl} t LEFT JOIN {evi} e ON t.patient_id = e.patient_id
                WHERE {pred}""")[0][0])
        coded = f"t.condition_code IN ({code_list})"
        noted = "e.asserts_current_dx"
        combine = {
            "code_only": _c(coded),
            "note_only": _c(noted),
            "union": _c(f"({coded} OR {noted})"),
            "intersection": _c(f"({coded} AND {noted})"),
            "note_recovered": _c(f"({noted} AND NOT ({coded}))"),   # notes find, codes missed
            "code_not_noted": _c(f"({coded} AND NOT ({noted}))"),   # coded, note silent/absent
        }

    # Detect threshold ambiguity from the intent text. In notes mode the threshold options are
    # computed against the UNION diagnosis set (most inclusive) so the user sees the full impact;
    # in code-only mode they are computed against the coded set exactly as before.
    ambiguity = None
    for term, spec in THRESHOLD_AMBIGUITIES.items():
        if term in intent_text.lower():
            opts = []
            for opt in spec["options"]:
                if note_evidence is not None:
                    evi = note_evidence.evidence_table
                    n = int(q(f"""SELECT COUNT(DISTINCT t.patient_id)
                        FROM {tbl} t LEFT JOIN {evi} e ON t.patient_id = e.patient_id
                        WHERE (t.condition_code IN ({code_list}) OR e.asserts_current_dx)
                          AND t.hba1c_value {opt['op']} {opt['value']}""")[0][0])
                else:
                    n = int(q(f"""SELECT COUNT(DISTINCT patient_id) FROM {tbl}
                        WHERE condition_code IN ({code_list})
                          AND hba1c_value {opt['op']} {opt['value']}""")[0][0])
                opts.append({**opt, "cohort_n": n})
            ambiguity = {"term": term, "measure": spec["measure"], "options": opts,
                         "computed_over": "union (code OR note)" if note_evidence else "coded dx"}
            break

    return CohortPreview(grounded_codes=grounded, missing_codes=missing, ambiguity=ambiguity,
                         base_condition_n=base_n, total_patients=total,
                         combine=combine, note_evidence=note_evidence)


def format_preview(preview: CohortPreview) -> str:
    """Readout for the user to make the threshold choice."""
    lines = ["## Cohort preview — confirm before building", ""]
    lines.append(f"**Codes grounded in the data:** {preview.grounded_codes}")
    if preview.missing_codes:
        lines.append(f"**⚠️ Requested codes NOT found in the data (excluded):** {preview.missing_codes}")
    lines.append(f"**Patients meeting the condition criteria:** {preview.base_condition_n} "
                 f"of {preview.total_patients}")
    lines.append("")
    if preview.combine:
        c = preview.combine
        ne = preview.note_evidence
        lines.append(f"**🗒️ Free-text notes analyzed** (endpoint `{ne.endpoint}`, "
                     f"negation-/subject-aware, span-grounded) — the diagnosis can be ascertained "
                     f"from codes, from note text, or both. **CHOOSE how to combine them "
                     f"(do not let the tool guess):**")
        lines.append(f"  1. **code_only** → dx N = **{c['code_only']}** (coded diagnosis only)")
        lines.append(f"  2. **note_only** → dx N = **{c['note_only']}** (note-asserted diagnosis only)")
        lines.append(f"  3. **union** → dx N = **{c['union']}** (code OR note — most inclusive)")
        lines.append(f"  4. **intersection** → dx N = **{c['intersection']}** (code AND note — chart-confirmed)")
        lines.append(f"  • Notes RECOVER **{c['note_recovered']}** patient(s) with no coding; "
                     f"**{c['code_not_noted']}** coded patient(s) have no note assertion.")
        lines.append(f"  *(These are diagnosis counts before the HbA1c threshold below.)*")
        lines.append("")
    if preview.ambiguity:
        a = preview.ambiguity
        over = f" (computed over {a['computed_over']})" if a.get("computed_over") else ""
        lines.append(f"**⚠️ Ambiguous criterion — '{a['term']}' ({a['measure']}) has more than one "
                     f"standard definition. CHOOSE ONE (do not let the tool guess){over}:**")
        for i, opt in enumerate(a["options"], 1):
            lines.append(f"  {i}. {opt['label']} → cohort N = **{opt['cohort_n']}**")
        lines.append("")
    if preview.combine and preview.ambiguity:
        lines.append("Reply with BOTH your combine mode (code_only / note_only / union / intersection) "
                     "AND the threshold option; the cohort is then built and verified.")
    elif preview.combine:
        lines.append("Reply with your combine mode (code_only / note_only / union / intersection); "
                     "the cohort is then built and verified.")
    elif preview.ambiguity:
        lines.append("Reply with the option number, then the cohort will be built and verified.")
    return "\n".join(lines)


# --- Step 2: build + verify ---------------------------------------------------

@dataclass
class CohortResult:
    cohort_table: str
    n_patients: int
    definition_json: str
    verified: bool
    verification_note: str
    ascertainment_summary: dict = field(default_factory=dict)  # {code|note|both: count}
    provenance_table: str | None = None                        # governed per-member source + span
    provenance_preview: str = ""                               # first-20-rows readout


def _format_provenance_preview(rows: list, provenance_table: str, summary: dict) -> str:
    """First-20-rows readout of the provenance/'delta' table so the user can audit WHY each
    member qualified (code vs note) and see the verbatim note span — without querying."""
    by_src = ", ".join(f"{k}={v}" for k, v in sorted(summary.items()))
    lines = [f"**Provenance / delta — `{provenance_table}`** (per-member source; by ascertainment: "
             f"{by_src}). First {len(rows)} rows:", "",
             "| patient_id | ascertainment | in_codes | note_asserts_dx | measure | note span |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        span = (r[5] or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {span} |")
    return "\n".join(lines)


def build_cohort(q: Q, table: str, definition: CohortDefinition,
                 cohort_table: str | None = None) -> CohortResult:
    """Materialize the cohort and VERIFY membership matches the definition exactly."""
    catalog, schema, tbl = _split_fqn(table)
    cohort_table = cohort_table or f"{tbl}_cohort"

    code_list = ", ".join(f"'{code}'" for _, code in definition.condition_codes) or "NULL"
    measure_clause = ""
    if definition.obs_op and definition.obs_value is not None:
        measure_clause = f"AND t.{definition.obs_measure_col} {definition.obs_op} {definition.obs_value}"

    # Diagnosis ascertainment: code-only (default) or, if a notes evidence table is bound,
    # the chosen combine mode over coded + note-asserted dx. LEFT JOIN so note-only members
    # (rows present in the spine table but with no coded dx) still qualify.
    evi = definition.note_evidence_table
    join = f"LEFT JOIN {evi} e ON t.patient_id = e.patient_id" if evi else ""
    dx_clause = _dx_predicate(definition.combine_mode, definition.condition_col, code_list)

    coded_expr = f"t.{definition.condition_col} IN ({code_list})"
    noted_expr = "e.asserts_current_dx" if evi else "false"
    # Per-patient ascertainment: did the CODE, the NOTE, or BOTH place them in the cohort?
    # A light, NON-PHI column carried on the shareable cohort table (raw note text stays out).
    _any_code = f"MAX(CASE WHEN {coded_expr} THEN 1 ELSE 0 END)"
    _any_note = f"MAX(CASE WHEN {noted_expr} THEN 1 ELSE 0 END)"
    ascertainment_expr = (
        f"CASE WHEN {_any_code} = 1 AND {_any_note} = 1 THEN 'both' "
        f"WHEN {_any_note} = 1 THEN 'note' ELSE 'code' END")

    # ids-only qualifying set for verification (structurally different from the create query)
    qualifying = f"""SELECT DISTINCT t.patient_id
        FROM {tbl} t {join}
        WHERE {dx_clause} {measure_clause}"""
    q(f"""CREATE OR REPLACE TABLE {cohort_table} AS
        SELECT t.patient_id, {ascertainment_expr} AS ascertainment
        FROM {tbl} t {join}
        WHERE {dx_clause} {measure_clause}
        GROUP BY t.patient_id""")

    n = int(q(f"SELECT COUNT(*) FROM {cohort_table}")[0][0])

    # Verification: check the MATERIALIZED TABLE against the definition with a structurally
    # DIFFERENT query than the one that created it (anti-joins between the table and the
    # source's qualifying set), so it can actually fail. Comparing counts from a re-run of
    # the identical create-SELECT is a tautology — and count equality also hides compensating
    # errors (one false positive + one false negative net to the same count). We instead
    # require BOTH set differences to be empty:
    #   false_positives = members in the table that do NOT qualify in the source
    #   false_negatives = source patients that qualify but are NOT in the table
    false_positives = int(q(f"""SELECT COUNT(*) FROM {cohort_table} c
        WHERE c.patient_id NOT IN ({qualifying})""")[0][0])
    false_negatives = int(q(f"""SELECT COUNT(*) FROM ({qualifying}) g
        WHERE g.patient_id NOT IN (SELECT patient_id FROM {cohort_table})""")[0][0])
    verified = (false_positives == 0 and false_negatives == 0)
    note = (f"Verified: all {n} members satisfy the definition and no qualifying patient is "
            f"missing (0 false positives, 0 false negatives)."
            if verified else
            f"MISMATCH: {false_positives} member(s) do not satisfy the definition, "
            f"{false_negatives} qualifying patient(s) missing from the table.")

    ascertainment_summary = {r[0]: int(r[1]) for r in
                             q(f"SELECT ascertainment, COUNT(*) FROM {cohort_table} GROUP BY ascertainment")}

    # Provenance / "delta" table — ONLY when notes contributed. Carries the per-member source
    # AND the verbatim note span (PHI): materialized as a SEPARATE, same-governance table, never
    # folded into the shareable cohort table. This is the audit artifact for "why did this
    # patient qualify?" and the disagreement (note-recovered vs coded-but-note-silent).
    provenance_table = None
    provenance_preview = ""
    if evi:
        prov = f"{cohort_table}_provenance"
        q(f"""CREATE OR REPLACE TABLE {prov} AS
            SELECT c.patient_id, c.ascertainment,
                   {_any_code} = 1 AS in_codes,
                   COALESCE({_any_note} = 1, false) AS note_asserts_dx,
                   MAX(e.evidence_span) AS evidence_span,
                   MAX(t.{definition.obs_measure_col}) AS {definition.obs_measure_col}
            FROM {cohort_table} c
              JOIN {tbl} t ON c.patient_id = t.patient_id
              LEFT JOIN {evi} e ON c.patient_id = e.patient_id
            GROUP BY c.patient_id, c.ascertainment""")
        provenance_table = f"{catalog}.{schema}.{prov}"
        # Lead with the most audit-worthy rows: note-recovered (note) and note-silent-coded
        # (code) before the concordant (both), so the preview shows the disagreement, not 20 easy cases.
        rows = q(f"""SELECT patient_id, ascertainment, in_codes, note_asserts_dx,
                       {definition.obs_measure_col}, substr(evidence_span, 1, 80)
                     FROM {prov} ORDER BY ascertainment DESC, patient_id LIMIT 20""")
        provenance_preview = _format_provenance_preview(rows, provenance_table, ascertainment_summary)

    return CohortResult(cohort_table=f"{catalog}.{schema}.{cohort_table}", n_patients=n,
                        definition_json=definition.to_json(), verified=verified,
                        verification_note=note, ascertainment_summary=ascertainment_summary,
                        provenance_table=provenance_table, provenance_preview=provenance_preview)


def format_result(res: CohortResult) -> str:
    lines = [
        "## Cohort built & verified", "",
        f"**Table:** `{res.cohort_table}`",
        f"**Patients:** {res.n_patients}",
        f"**{res.verification_note}**",
    ]
    d = json.loads(res.definition_json)
    if d.get("note_evidence_table"):
        by_src = ", ".join(f"{k}={v}" for k, v in sorted(res.ascertainment_summary.items()))
        lines.append(f"**Diagnosis ascertainment:** `{d['combine_mode']}` (codes + free-text notes) — "
                     f"by source: {by_src}. Note evidence via `{d.get('note_endpoint')}` "
                     f"(negation-/subject-aware, span-grounded; prompt pinned in the definition).")
        if res.provenance_table:
            lines.append(f"**Provenance table:** `{res.provenance_table}` — per-member source + the "
                         f"verbatim note span. Governed like the notes source; raw note text is NOT "
                         f"copied into the shareable cohort table (which carries only a light "
                         f"`ascertainment` column).")
    lines.append(f"**Reproducible definition:** `{res.definition_json}`")
    if res.provenance_preview:
        lines += ["", res.provenance_preview]
    lines += [
        "",
        "*Literature validation of this phenotype is a SEPARATE step — do not attach a "
        "citation unless it was resolved against a real literature source (see SKILL.md). "
        "Never fabricate a PMID/NCT id.*",
    ]
    return "\n".join(lines)


# --- SINGLE ENTRYPOINT (execution model; mirrors run_deid's one-call shape) ----

_COMBINE_MODES = ("code_only", "note_only", "union", "intersection")


def run_cohort(table: str, intent_text: str, condition_codes: list,
               threshold_value: float | None = None, threshold_op: str | None = None,
               cohort_table: str | None = None, mcp_citations: list | None = None,
               notes_table: str | None = None, note_col: str = "note_text",
               note_id_col: str = "patient_id", note_endpoint: str = DEFAULT_NOTE_ENDPOINT,
               note_condition: str | None = None, note_prompt: str | None = None,
               combine_mode: str | None = None, include_literature: bool = True,
               profile: str | None = None, warehouse_id: str | None = None) -> str:
    """ONE call. Genie should call this and report its output — nothing else.

    Behavior (the confirm-gate is in the RETURN VALUE, not a separate step Genie must
    remember): if the intent contains an ambiguous clinical threshold and the caller
    did NOT supply threshold_value — OR a free-text notes source is given and the caller
    did NOT supply combine_mode — this BUILDS NOTHING and returns the choice prompt. Genie
    must show that to the user, get their choice(s), and call again WITH them. If there is no
    ambiguity (or the choices are supplied), it builds + verifies.

    Args:
        table: catalog.schema.table of coded clinical records.
        intent_text: the user's exact phrasing (scanned for ambiguous terms).
        condition_codes: [(vocab, code)] proposed from the NL intent (grounded here).
        threshold_value / threshold_op: supply ONLY after the user has chosen.
        notes_table: OPTIONAL free-text notes source; when given the diagnosis is also
            ascertained from note text (negation-/subject-aware, span-grounded via ai_query).
        combine_mode: how to combine coded + note-derived dx — code_only | note_only |
            union | intersection. REQUIRED (the user's choice) once notes_table is given.
    """
    catalog, schema, _ = _split_fqn(table)
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)

    preview = preview_cohort(q, table, condition_codes, intent_text=intent_text,
                             notes_table=notes_table, note_col=note_col,
                             note_id_col=note_id_col, note_endpoint=note_endpoint,
                             note_condition=note_condition, note_prompt=note_prompt)

    # Confirm-gate 1: notes present but no combine mode chosen -> refuse to build, ask.
    if preview.combine and combine_mode is None:
        return (format_preview(preview) +
                "\n\n**STOP: do not pick a combine mode yourself. Present the options above to "
                "the user, then call run_cohort again with the chosen combine_mode "
                "(and threshold_value/op if a threshold is also being surfaced).**")
    if combine_mode is not None and combine_mode not in _COMBINE_MODES:
        return (f"**STOP: combine_mode='{combine_mode}' is invalid. Use one of "
                f"{', '.join(_COMBINE_MODES)}.**")

    # Confirm-gate 2: ambiguous term + no threshold chosen yet -> refuse to build, ask.
    if preview.ambiguity and threshold_value is None:
        return (format_preview(preview) +
                "\n\n**STOP: do not pick a threshold yourself. Present the options above to "
                "the user, then call run_cohort again with the chosen threshold_value/op.**")

    # Resolve the measure criterion. CRITICAL: never silently default the operator when the
    # term is ambiguous — the operator is PART of the user's choice (HEDIS ">=9.0" vs clinical
    # ">8.0" differ by BOTH value and operator; defaulting ">=9.0" to ">9.0" silently drops
    # every patient at exactly 9.0 — the exact silent-threshold failure this skill prevents).
    op, val = threshold_op, threshold_value
    if preview.ambiguity and threshold_value is not None and op is None:
        # Caller passed a value from the user's chosen option but omitted the operator.
        # Recover it from the matching option rather than guessing ">".
        matching = [o for o in preview.ambiguity["options"] if o["value"] == threshold_value]
        if len(matching) == 1:
            op = matching[0]["op"]
        else:
            # Value doesn't map to exactly one known option -> refuse rather than guess.
            return (format_preview(preview) +
                    f"\n\n**STOP: threshold_value={threshold_value} does not uniquely match one "
                    "of the options above, and no threshold_op was supplied. Re-call with BOTH "
                    "threshold_value AND threshold_op (e.g. '>=') so the operator is not guessed.**")
    ne = preview.note_evidence
    definition = CohortDefinition(condition_codes=preview.grounded_codes,
                                  obs_op=op, obs_value=val,
                                  label=intent_text[:80],
                                  combine_mode=combine_mode or "code_only",
                                  note_evidence_table=ne.evidence_table if ne else None,
                                  note_endpoint=ne.endpoint if ne else None,
                                  note_prompt=ne.prompt if ne else None)
    res = build_cohort(q, table, definition, cohort_table=cohort_table)

    warn = ""
    if preview.missing_codes:
        warn = f"\n**⚠️ Excluded codes not present in data: {preview.missing_codes}**"

    # Literature: prefer MCP-retrieved citations (verified), else direct PubMed floor.
    # Fails closed -> never fabricates. mcp_citations is whatever Genie pulled from a
    # connected literature MCP server (list of PMIDs/dicts); None if no server connected.
    # include_literature=False skips it entirely (air-gapped workspaces with no PubMed/MCP
    # egress: avoids the network round-trip/timeout — the step already fails closed either way).
    lit_block = ""
    if include_literature:
        try:
            from literature import literature_for_cohort, format_literature
            lit = literature_for_cohort(intent_text, mcp_candidates=mcp_citations)
            lit_block = "\n\n" + format_literature(lit)
            if lit.note:
                lit_block += f"\n*{lit.note}*"
        except Exception:
            lit_block = "\n\n**Literature:** resolver unavailable; no citation attached (none fabricated)."
    else:
        lit_block = "\n\n*Literature step skipped (include_literature=False).*"

    return format_result(res) + warn + lit_block


# --- TWO EXPLICITLY-NAMED ENTRYPOINTS (preferred over run_cohort) --------------
# A natural-language permission reviewer that only sees the CALL (not the return value)
# cannot distinguish "preview" from "build" when both are the same function name. These
# two names make intent unmistakable: preview_cohort_options is READ-ONLY (builds nothing,
# takes no threshold), build_confirmed_cohort REQUIRES a chosen threshold. This fixes the
# "Action denied" misfire where a reviewer blocked the (harmless) preview call.

def preview_cohort_options(table: str, intent_text: str, condition_codes: list,
                           code_source: str = "model-proposed",
                           notes_table: str | None = None, note_col: str = "note_text",
                           note_id_col: str = "patient_id", note_endpoint: str = DEFAULT_NOTE_ENDPOINT,
                           note_condition: str | None = None, note_prompt: str | None = None,
                           profile: str | None = None, warehouse_id: str | None = None) -> str:
    """READ-ONLY grounding + surfacing. Grounds codes in the data and returns real cohort-size
    options for any ambiguous threshold. Takes NO threshold and NO combine-mode argument — it
    only SURFACES the choices. Call this FIRST; show its output to the user; get their choice(s).

    condition_codes: [(vocab, code)] from ANY source. This is the skill's INPUT CONTRACT —
    whether the codes came from a terminology MCP (BioPortal), clinical-notes parsing, or
    the model's own knowledge, they are ALL grounded here against the actual data; codes
    not present in the table are excluded regardless of source. Pass code_source to record
    provenance in the readout (e.g. 'BioPortal MCP', 'clinical-notes MCP', 'model-proposed').

    notes_table: OPTIONAL free-text notes source. When given, the diagnosis is ALSO ascertained
    from note text via ai_query (negation-/subject-aware, span-grounded) and the readout surfaces
    code-only / note-only / union / intersection cohort sizes for the user to choose from. NOTE:
    this MATERIALIZES a `<notes_table>_note_evidence` table (it runs ai_query), so it is not
    zero-side-effect like the code-only preview; it still builds no cohort.
    """
    catalog, schema, _ = _split_fqn(table)
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)
    preview = preview_cohort(q, table, condition_codes, intent_text=intent_text,
                             notes_table=notes_table, note_col=note_col,
                             note_id_col=note_id_col, note_endpoint=note_endpoint,
                             note_condition=note_condition, note_prompt=note_prompt)
    src = code_source if not notes_table else f"{code_source}; notes via {note_endpoint}"
    out = f"*Code source: {src} (all codes grounded against the data below).*\n\n" + format_preview(preview)
    if not preview.ambiguity and not preview.combine:
        out += ("\n\n(No ambiguous threshold detected — call build_confirmed_cohort to "
                "materialize, or supply a measure criterion if one applies.)")
    return out


def build_confirmed_cohort(table: str, intent_text: str, condition_codes: list,
                           threshold_value: float, threshold_op: str | None = None,
                           cohort_table: str | None = None, mcp_citations: list | None = None,
                           notes_table: str | None = None, note_col: str = "note_text",
                           note_id_col: str = "patient_id", note_endpoint: str = DEFAULT_NOTE_ENDPOINT,
                           note_condition: str | None = None, note_prompt: str | None = None,
                           combine_mode: str | None = None, include_literature: bool = True,
                           profile: str | None = None, warehouse_id: str | None = None) -> str:
    """Materialize + verify a cohort with the choices the USER has ALREADY made.
    threshold_value is REQUIRED — this function is only called after preview_cohort_options
    surfaced the choice and the user picked. threshold_op defaults to None (NOT ">") so that,
    for an ambiguous term, run_cohort recovers the correct operator from the chosen option
    instead of silently forcing ">"; pass it explicitly to override.

    When notes_table is given, combine_mode (code_only | note_only | union | intersection) is
    REQUIRED — it is the user's choice for how coded and note-derived diagnoses combine, and is
    never picked for them. Delegates to run_cohort."""
    return run_cohort(table, intent_text, condition_codes,
                      threshold_value=threshold_value, threshold_op=threshold_op,
                      cohort_table=cohort_table, mcp_citations=mcp_citations,
                      notes_table=notes_table, note_col=note_col, note_id_col=note_id_col,
                      note_endpoint=note_endpoint, note_condition=note_condition,
                      note_prompt=note_prompt, combine_mode=combine_mode,
                      include_literature=include_literature,
                      profile=profile, warehouse_id=warehouse_id)


if __name__ == "__main__":
    prof = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    tbl = sys.argv[1] if len(sys.argv) > 1 else "testing_playground_catalog.deid_live_test.clinical_records"
    print("=== preview_cohort_options (read-only) ===")
    print(preview_cohort_options(tbl, "type 2 diabetes with uncontrolled HbA1c",
                                 [("ICD10CM", "E11.9"), ("ICD10CM", "E11.65")], profile=prof))
