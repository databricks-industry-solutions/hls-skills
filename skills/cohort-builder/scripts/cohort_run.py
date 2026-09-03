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
        r = self.w.statement_execution.execute_statement(
            warehouse_id=self.wid, catalog=self.catalog, schema=self.schema,
            statement=stmt, wait_timeout="50s")
        if r.status and str(r.status.state) != "StatementState.SUCCEEDED":
            raise RuntimeError(f"{r.status.error} :: {stmt[:200]}")
        return r.result.data_array if r.result else []


def _split_fqn(fqn: str):
    parts = fqn.split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected catalog.schema.table, got: {fqn}")
    return parts


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


def preview_cohort(q: Q, table: str, condition_codes: list, intent_text: str = "") -> CohortPreview:
    """Ground the codes in the data and surface any threshold ambiguity with N impact.

    condition_codes: [(vocab, code)] the caller proposes (from NL intent).
    intent_text: the user's phrasing, scanned for known ambiguous terms.

    Returns a preview to SHOW THE USER. Does not build anything.
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

    # Detect threshold ambiguity from the intent text.
    ambiguity = None
    for term, spec in THRESHOLD_AMBIGUITIES.items():
        if term in intent_text.lower():
            opts = []
            for opt in spec["options"]:
                n = int(q(f"""SELECT COUNT(DISTINCT patient_id) FROM {tbl}
                    WHERE condition_code IN ({code_list})
                      AND hba1c_value {opt['op']} {opt['value']}""")[0][0])
                opts.append({**opt, "cohort_n": n})
            ambiguity = {"term": term, "measure": spec["measure"], "options": opts}
            break

    return CohortPreview(grounded_codes=grounded, missing_codes=missing, ambiguity=ambiguity,
                         base_condition_n=base_n, total_patients=total)


def format_preview(preview: CohortPreview) -> str:
    """Readout for the user to make the threshold choice."""
    lines = ["## Cohort preview — confirm before building", ""]
    lines.append(f"**Codes grounded in the data:** {preview.grounded_codes}")
    if preview.missing_codes:
        lines.append(f"**⚠️ Requested codes NOT found in the data (excluded):** {preview.missing_codes}")
    lines.append(f"**Patients meeting the condition criteria:** {preview.base_condition_n} "
                 f"of {preview.total_patients}")
    lines.append("")
    if preview.ambiguity:
        a = preview.ambiguity
        lines.append(f"**⚠️ Ambiguous criterion — '{a['term']}' ({a['measure']}) has more than one "
                     f"standard definition. CHOOSE ONE (do not let the tool guess):**")
        for i, opt in enumerate(a["options"], 1):
            lines.append(f"  {i}. {opt['label']} → cohort N = **{opt['cohort_n']}**")
        lines.append("")
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


def build_cohort(q: Q, table: str, definition: CohortDefinition,
                 cohort_table: str | None = None) -> CohortResult:
    """Materialize the cohort and VERIFY membership matches the definition exactly."""
    catalog, schema, tbl = _split_fqn(table)
    cohort_table = cohort_table or f"{tbl}_cohort"

    code_list = ", ".join(f"'{code}'" for _, code in definition.condition_codes) or "NULL"
    measure_clause = ""
    if definition.obs_op and definition.obs_value is not None:
        measure_clause = f"AND {definition.obs_measure_col} {definition.obs_op} {definition.obs_value}"

    qualifying = f"""SELECT DISTINCT patient_id
        FROM {tbl}
        WHERE {definition.condition_col} IN ({code_list}) {measure_clause}"""
    q(f"CREATE OR REPLACE TABLE {cohort_table} AS {qualifying}")

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

    return CohortResult(cohort_table=f"{catalog}.{schema}.{cohort_table}", n_patients=n,
                        definition_json=definition.to_json(), verified=verified,
                        verification_note=note)


def format_result(res: CohortResult) -> str:
    return "\n".join([
        "## Cohort built & verified", "",
        f"**Table:** `{res.cohort_table}`",
        f"**Patients:** {res.n_patients}",
        f"**{res.verification_note}**",
        f"**Reproducible definition:** `{res.definition_json}`",
        "",
        "*Literature validation of this phenotype is a SEPARATE step — do not attach a "
        "citation unless it was resolved against a real literature source (see SKILL.md). "
        "Never fabricate a PMID/NCT id.*",
    ])


# --- SINGLE ENTRYPOINT (execution model; mirrors run_deid's one-call shape) ----

def run_cohort(table: str, intent_text: str, condition_codes: list,
               threshold_value: float | None = None, threshold_op: str | None = None,
               cohort_table: str | None = None, mcp_citations: list | None = None,
               profile: str | None = None, warehouse_id: str | None = None) -> str:
    """ONE call. Genie should call this and report its output — nothing else.

    Behavior (the confirm-gate is in the RETURN VALUE, not a separate step Genie must
    remember): if the intent contains an ambiguous clinical threshold and the caller
    did NOT supply threshold_value, this BUILDS NOTHING and returns the choice prompt.
    Genie must show that to the user, get a number, and call again WITH threshold_value.
    If there is no ambiguity (or a threshold is supplied), it builds + verifies.

    Args:
        table: catalog.schema.table of coded clinical records.
        intent_text: the user's exact phrasing (scanned for ambiguous terms).
        condition_codes: [(vocab, code)] proposed from the NL intent (grounded here).
        threshold_value / threshold_op: supply ONLY after the user has chosen.
    """
    catalog, schema, _ = _split_fqn(table)
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)

    preview = preview_cohort(q, table, condition_codes, intent_text=intent_text)

    # Confirm-gate: ambiguous term + no threshold chosen yet -> refuse to build, ask.
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
    definition = CohortDefinition(condition_codes=preview.grounded_codes,
                                  obs_op=op, obs_value=val,
                                  label=intent_text[:80])
    res = build_cohort(q, table, definition, cohort_table=cohort_table)

    warn = ""
    if preview.missing_codes:
        warn = f"\n**⚠️ Excluded codes not present in data: {preview.missing_codes}**"

    # Literature: prefer MCP-retrieved citations (verified), else direct PubMed floor.
    # Fails closed -> never fabricates. mcp_citations is whatever Genie pulled from a
    # connected literature MCP server (list of PMIDs/dicts); None if no server connected.
    lit_block = ""
    try:
        from literature import literature_for_cohort, format_literature
        lit = literature_for_cohort(intent_text, mcp_candidates=mcp_citations)
        lit_block = "\n\n" + format_literature(lit)
        if lit.note:
            lit_block += f"\n*{lit.note}*"
    except Exception:
        lit_block = "\n\n**Literature:** resolver unavailable; no citation attached (none fabricated)."

    return format_result(res) + warn + lit_block


# --- TWO EXPLICITLY-NAMED ENTRYPOINTS (preferred over run_cohort) --------------
# A natural-language permission reviewer that only sees the CALL (not the return value)
# cannot distinguish "preview" from "build" when both are the same function name. These
# two names make intent unmistakable: preview_cohort_options is READ-ONLY (builds nothing,
# takes no threshold), build_confirmed_cohort REQUIRES a chosen threshold. This fixes the
# "Action denied" misfire where a reviewer blocked the (harmless) preview call.

def preview_cohort_options(table: str, intent_text: str, condition_codes: list,
                           code_source: str = "model-proposed",
                           profile: str | None = None, warehouse_id: str | None = None) -> str:
    """READ-ONLY. Grounds codes in the data and returns real cohort-size options for any
    ambiguous threshold. BUILDS NOTHING, creates no tables, takes NO threshold argument.
    Call this FIRST; show its output to the user; get their threshold choice.

    condition_codes: [(vocab, code)] from ANY source. This is the skill's INPUT CONTRACT —
    whether the codes came from a terminology MCP (BioPortal), clinical-notes parsing, or
    the model's own knowledge, they are ALL grounded here against the actual data; codes
    not present in the table are excluded regardless of source. Pass code_source to record
    provenance in the readout (e.g. 'BioPortal MCP', 'clinical-notes MCP', 'model-proposed').
    """
    catalog, schema, _ = _split_fqn(table)
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)
    preview = preview_cohort(q, table, condition_codes, intent_text=intent_text)
    out = f"*Code source: {code_source} (all codes grounded against the data below).*\n\n" + format_preview(preview)
    if not preview.ambiguity:
        out += ("\n\n(No ambiguous threshold detected — call build_confirmed_cohort to "
                "materialize, or supply a measure criterion if one applies.)")
    return out


def build_confirmed_cohort(table: str, intent_text: str, condition_codes: list,
                           threshold_value: float, threshold_op: str | None = None,
                           cohort_table: str | None = None, mcp_citations: list | None = None,
                           profile: str | None = None, warehouse_id: str | None = None) -> str:
    """Materialize + verify a cohort with a threshold the USER has ALREADY chosen.
    threshold_value is REQUIRED — this function is only called after preview_cohort_options
    surfaced the choice and the user picked. threshold_op defaults to None (NOT ">") so that,
    for an ambiguous term, run_cohort recovers the correct operator from the chosen option
    instead of silently forcing ">"; pass it explicitly to override. Delegates to run_cohort."""
    return run_cohort(table, intent_text, condition_codes,
                      threshold_value=threshold_value, threshold_op=threshold_op,
                      cohort_table=cohort_table, mcp_citations=mcp_citations,
                      profile=profile, warehouse_id=warehouse_id)


if __name__ == "__main__":
    prof = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    tbl = sys.argv[1] if len(sys.argv) > 1 else "testing_playground_catalog.deid_live_test.clinical_records"
    print("=== preview_cohort_options (read-only) ===")
    print(preview_cohort_options(tbl, "type 2 diabetes with uncontrolled HbA1c",
                                 [("ICD10CM", "E11.9"), ("ICD10CM", "E11.65")], profile=prof))
