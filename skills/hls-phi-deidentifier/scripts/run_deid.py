"""Single entrypoint for the de-identification skill — EXECUTION model.

Genie Code should CALL this function and report its return value. It must NOT
write its own de-identification SQL: the live test showed that reimplementation is
lossy (Genie omitted length-of-stay from its k-anonymity check and shipped a view
that claimed k=5 while 50%+ of rows were uniquely identifiable). This vetted path
treats every quasi-identifier — including derived ones like length-of-stay — as
in-scope, so the false-assurance failure cannot happen.

Usage inside Genie Code / a notebook (ambient auth):
    import sys; sys.path.append('<skill>/scripts')
    from run_deid import run_deid
    print(run_deid("main.clinical.patients_raw"))
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apply_uc_governance import Q, build_deid_view          # noqa: E402
from profile_table import profile_table                     # noqa: E402
from detect_phi import detect_phi                            # noqa: E402
from deid_report import build_readout                        # noqa: E402
from kanon import DEFAULT_QIS, build_qis                     # noqa: E402


def _split_fqn(fqn: str):
    parts = fqn.split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected catalog.schema.table, got: {fqn}")
    return parts[0], parts[1], parts[2]


def _persist_audit(q: Q, table_fqn: str, view_fqn: str, k_actual: int | None,
                   passed: bool, readout: str) -> str:
    """Write the verified readout to a UC audit table; return its FQN + row marker.

    Makes the tool's output the durable source of truth, independent of chat prose.
    Best-effort: if the write fails, the readout is still returned (never blocks de-id).
    """
    audit_tbl = "deid_audit_log"
    try:
        q(f"""CREATE TABLE IF NOT EXISTS {audit_tbl} (
            ts TIMESTAMP, source_table STRING, output_view STRING,
            k_actual INT, passed BOOLEAN, readout STRING)""")
        safe = readout.replace("'", "''")
        k_sql = "NULL" if k_actual is None else str(k_actual)   # None -> SQL NULL (unmeasured)
        q(f"""INSERT INTO {audit_tbl} VALUES (current_timestamp(), '{table_fqn}',
            '{view_fqn}', {k_sql}, {str(passed).lower()}, '{safe}')""")
        return f"{q.catalog}.{q.schema}.{audit_tbl} (latest row for {view_fqn})"
    except Exception as e:
        return f"(audit persist skipped: {type(e).__name__})"


def _residual_leak_scan(q: Q, view: str) -> list:
    """Re-scan the OUTPUT view for PHI that slipped past detection. Returns leaking columns.

    Belt-and-suspenders to deny-by-default: checks each string column for SSN/email/phone
    patterns and flags near-unique free-text columns (a name column detection missed).
    Pseudo-id/token columns are exempt (they are hashes by construction).
    """
    cols = [(r[0], (r[1] or "").lower()) for r in q(f"DESCRIBE {view}")
            if r and r[0] and not r[0].startswith("#")]
    total = int(q(f"SELECT COUNT(*) FROM {view}")[0][0]) or 1
    leaks = []
    for name, dtype in cols:
        if name.startswith("pseudo_") or "generalized" in name or name.endswith("_year"):
            continue
        if "string" not in dtype and "char" not in dtype:
            continue
        # PHI regex hit in any value?
        hit = q(f"""SELECT COUNT(*) FROM {view} WHERE
            `{name}` RLIKE '[0-9]{{3}}-[0-9]{{2}}-[0-9]{{4}}' OR `{name}` RLIKE '@'
            OR `{name}` RLIKE '\\\\([0-9]{{3}}\\\\)'""")
        if int(hit[0][0]) > 0:
            leaks.append(name)
            continue
        # near-unique free text (looks like a name/free identifier detection missed)
        distinct = int(q(f"SELECT COUNT(DISTINCT `{name}`) FROM {view}")[0][0])
        if distinct / total > 0.8:
            leaks.append(name)
    return leaks


def _measure_actual_k(q: Q, view: str, generalization) -> tuple[int | None, int]:
    """Measure k on the view over ALL surviving quasi-identifier columns.

    Critically: this includes derived QIs (e.g. length_of_stay) that a naive check
    forgets. Returns (k_min, unique_row_count).

    If there are NO generalized quasi-identifier columns to measure over, k is
    UNMEASURED — returns (None, 0), NOT a large sentinel. A caller must treat None as
    "cannot certify re-identification resistance" (fail-closed / review-required), never
    as an automatic pass: with no QIs measured, silently reporting a huge k would be a
    false assurance for exactly the tables where a missed QI is the risk.
    """
    cols = [r[0] for r in q(f"DESCRIBE {view}") if r and r[0] and not r[0].startswith("#")]
    # Surviving QI columns are those emitted with a *_generalized suffix, plus any
    # kept quasi-identifier passthroughs. Exclude the pseudo-id, dates, and the lab value.
    qi_cols = [c for c in cols if c.endswith("_generalized")]
    if not qi_cols:
        return None, 0
    grp = ", ".join(qi_cols)
    r = q(f"""SELECT MIN(cnt), SUM(CASE WHEN cnt=1 THEN 1 ELSE 0 END)
              FROM (SELECT {grp}, COUNT(*) cnt FROM {view} GROUP BY {grp})""")
    return int(r[0][0]), int(r[0][1] or 0)


def run_deid(raw_fqn: str, view_name: str | None = None, k_target: int = 5,
             profile: str | None = None, warehouse_id: str | None = None) -> str:
    """Run the full vetted de-identification pipeline and return the DS readout.

    Steps (all vetted; do not reimplement in ad-hoc SQL):
      1. Profile the table.
      2. Auto-detect PHI columns (surfaced for transparency).
      3. Build a k-anonymity-enforcing VIEW over raw (no PHI copy), treating derived
         columns (length-of-stay) as quasi-identifiers.
      4. Measure ACTUAL k over all surviving QIs and fail loudly if below target.
      5. Return the analyst-facing readout.
    """
    catalog, schema, table = _split_fqn(raw_fqn)
    view_name = view_name or f"{table}_deid"
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)

    # 1-2: profile + detect (surfaced so the user sees what was classified)
    profiles = profile_table(q, table)
    classifications = detect_phi(profiles)
    phi_cols = [(c.column, c.detected_class) for c in classifications if c.detected_class != "not_phi"]

    # Derive the schema-specific column roles from detection (so this works on ANY table,
    # not just the demo schema). Direct identifiers -> dropped; ids -> tokenized; dates ->
    # year; quasi-identifiers -> generalized via build_qis; everything else -> passthrough.
    DIRECT_DROP = {"name", "ssn", "email", "phone", "fax", "url", "ip_address",
                   "certificate_license", "vehicle_id", "biometric", "photo"}
    ID_CLASSES = {"other_unique_id", "mrn", "health_plan_number", "account_number", "device_id"}
    cls_by_col = {c.column: c.detected_class for c in classifications}

    qis = build_qis(profiles, classifications, q=q, table=table)
    qi_cols = {qi.column for qi in qis} | {"admit_date", "discharge_date"}  # __los__ consumes dates

    id_columns = [c for c, k in cls_by_col.items() if k in ID_CLASSES]
    date_year_columns = [c for c, k in cls_by_col.items()
                         if k == "date_element" and c not in qi_cols]

    # DENY-BY-DEFAULT passthrough: a column is exposed as-is ONLY if it is affirmatively
    # safe -- numeric measures (labs, scores). Anything else that detection did not route
    # to id/date/QI is SUPPRESSED, not passed through. This prevents leaks like a free-text
    # 'full_name' the name-heuristic missed: unknown string columns are never exposed raw.
    prof_by_col = {p.column: p for p in profiles}
    NUMERIC_HINTS = ("int", "double", "float", "decimal", "long", "short", "byte")
    handled = set(id_columns) | set(date_year_columns) | qi_cols
    dropped_direct = {c for c, k in cls_by_col.items() if k in DIRECT_DROP}
    passthrough, suppressed_unsafe = [], []
    for p in profiles:
        if p.column in handled or p.column in dropped_direct:
            continue
        dtype = (p.data_type or "").lower()
        is_numeric = any(t in dtype for t in NUMERIC_HINTS)
        if is_numeric:
            passthrough.append(p.column)          # affirmatively safe -> expose
        else:
            suppressed_unsafe.append(p.column)    # unknown non-numeric -> DENY (do not leak)

    # 3: build the governed view (schema-driven)
    gov = build_deid_view(q, table, view_name, k_target=k_target, qis=qis,
                          id_columns=id_columns, passthrough_columns=passthrough,
                          date_year_columns=date_year_columns)

    # 4: verify ACTUAL k over all surviving quasi-identifiers (the gate the live test needed)
    k_actual, unique_rows = _measure_actual_k(q, view_name, gov.generalization)
    kept = int(q(f"SELECT COUNT(*) FROM {view_name}")[0][0])
    total = int(q(f"SELECT COUNT(*) FROM {table}")[0][0])

    # 4b: RESIDUAL LEAK SCAN (defense-in-depth). Deny-by-default already suppresses unknown
    # columns, but this catches anything that slipped through: re-scan the OUTPUT view's
    # columns for PHI. Any hit is a leak -> hard FAIL regardless of k.
    leaked_cols = _residual_leak_scan(q, view_name)

    # 5: readout, with an explicit verification verdict
    dropped_cols = [c for c, k in cls_by_col.items() if k in DIRECT_DROP]
    readout = build_readout(gov, k_actual=k_actual, rows_kept=kept, rows_total=total,
                            removed_columns=dropped_cols + [f"exact dates ({', '.join(date_year_columns)}→year)"]
                            if date_year_columns else dropped_cols,
                            tokenized_columns=id_columns,
                            suppressed_columns=suppressed_unsafe,
                            passthrough_columns=passthrough)
    detected = "\n".join(f"  - {c} -> {klass}" for c, klass in phi_cols)
    leak_fail = " LEAK DETECTED in output: " + ", ".join(leaked_cols) + " — DO NOT SHARE." if leaked_cols else ""
    # k_actual is None when there were NO quasi-identifiers to measure -> we CANNOT certify
    # re-identification resistance. That is REVIEW-REQUIRED, never an automatic pass.
    k_measured = k_actual is not None
    passed = k_measured and k_actual >= k_target and not leaked_cols
    if not k_measured:
        verdict = (f"REVIEW REQUIRED: no quasi-identifier columns were generalized, so k-anonymity "
                   f"could not be measured — re-identification resistance is UNVERIFIED (target "
                   f"{k_target}). Do NOT treat as de-identified without a Privacy Officer review "
                   f"of the surviving columns.{leak_fail}")
    else:
        verdict = (f"VERIFIED: actual k={k_actual} over ALL surviving quasi-identifiers "
                   f"(target {k_target}). {'PASS.' if passed else 'FAIL — DO NOT SHARE.'}{leak_fail}")
        if unique_rows:
            verdict += f" {unique_rows} uniquely-identifiable rows remain."

    full = f"### PHI detected (auto)\n{detected}\n\n{readout}\n\n---\n**{verdict}**"

    # Persist the AUTHORITATIVE readout to UC so a reviewer reads the tool's own output,
    # not Genie's chat paraphrase (which can editorialize beyond what the tool did).
    audit_ref = _persist_audit(q, table_fqn=raw_fqn, view_fqn=gov.view_fqn,
                               k_actual=k_actual, passed=passed, readout=full)
    return full + f"\n\n*Authoritative record: {audit_ref} — cite THIS, not chat text.*"


if __name__ == "__main__":
    fqn = sys.argv[1] if len(sys.argv) > 1 else "main.clinical.patients_raw"
    prof = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    print(run_deid(fqn, profile=prof))
