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
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apply_uc_governance import Q, build_deid_view          # noqa: E402
from profile_table import profile_table                     # noqa: E402
from detect_phi import detect_phi                            # noqa: E402
from deid_report import build_readout                        # noqa: E402
from kanon import (DEFAULT_QIS, build_qis, find_minimal_generalization,  # noqa: E402
                   generalization_summary)


# Column-role vocabulary (shared by the planner). Direct identifiers with no analytic value
# are DROPPED (redaction); id-like columns are TOKENIZED (pseudonym, linkage kept); dates are
# reduced to YEAR; quasi-identifiers are GENERALIZED (reduction) by the k-anon engine; numeric
# measures pass through; unknown non-numeric columns are SUPPRESSED (deny-by-default).
DIRECT_DROP = {"name", "ssn", "email", "phone", "fax", "url", "ip_address",
               "certificate_license", "vehicle_id", "biometric", "photo"}
ID_CLASSES = {"other_unique_id", "mrn", "health_plan_number", "account_number", "device_id"}
NUMERIC_HINTS = ("int", "double", "float", "decimal", "long", "short", "byte")


def _split_fqn(fqn: str):
    parts = fqn.split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected catalog.schema.table, got: {fqn}")
    return parts[0], parts[1], parts[2]


@dataclass
class DeidPlan:
    """The per-column de-identification plan for a table (independent of k_target).

    Separates redaction (dropped/tokenized direct identifiers) from reduction (generalized
    quasi-identifiers) so both the preview and the apply step share ONE routing decision.
    """
    qis: list = field(default_factory=list)                 # QuasiIdentifier objects (generalized)
    id_columns: list = field(default_factory=list)          # tokenized
    date_year_columns: list = field(default_factory=list)   # reduced to YEAR
    passthrough: list = field(default_factory=list)         # numeric measures kept as-is
    suppressed_unsafe: list = field(default_factory=list)   # unknown non-numeric -> denied
    dropped_direct: list = field(default_factory=list)      # direct identifiers -> redacted
    phi_cols: list = field(default_factory=list)            # [(column, detected_class)]
    profiles: list = field(default_factory=list)
    classifications: list = field(default_factory=list)


def _plan_columns(q: Q, table: str) -> DeidPlan:
    """Profile + detect PHI, then route every column to its Safe Harbor strategy.

    Schema-driven so it works on ANY table, not just the demo schema. This is the single
    source of truth for column roles; run_deid and preview_deid_options both call it.
    """
    profiles = profile_table(q, table)
    classifications = detect_phi(profiles)
    phi_cols = [(c.column, c.detected_class) for c in classifications if c.detected_class != "not_phi"]
    cls_by_col = {c.column: c.detected_class for c in classifications}

    qis = build_qis(profiles, classifications, q=q, table=table)
    qi_cols = {qi.column for qi in qis} | {"admit_date", "discharge_date"}   # __los__ consumes dates

    id_columns = [c for c, k in cls_by_col.items() if k in ID_CLASSES]
    date_year_columns = [c for c, k in cls_by_col.items()
                         if k == "date_element" and c not in qi_cols]
    handled = set(id_columns) | set(date_year_columns) | qi_cols
    dropped_direct = {c for c, k in cls_by_col.items() if k in DIRECT_DROP}

    passthrough, suppressed_unsafe = [], []
    for p in profiles:
        if p.column in handled or p.column in dropped_direct:
            continue
        dtype = (p.data_type or "").lower()
        if any(t in dtype for t in NUMERIC_HINTS):
            passthrough.append(p.column)          # affirmatively safe -> expose
        else:
            suppressed_unsafe.append(p.column)    # unknown non-numeric -> DENY (do not leak)

    return DeidPlan(qis=qis, id_columns=id_columns, date_year_columns=date_year_columns,
                    passthrough=passthrough, suppressed_unsafe=suppressed_unsafe,
                    dropped_direct=sorted(dropped_direct), phi_cols=phi_cols,
                    profiles=profiles, classifications=classifications)


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

    # 1-2: profile + detect + route columns (shared planner; surfaced for transparency)
    plan = _plan_columns(q, table)
    phi_cols = plan.phi_cols
    cls_by_col = {c.column: c.detected_class for c in plan.classifications}
    qis, id_columns = plan.qis, plan.id_columns
    date_year_columns, passthrough = plan.date_year_columns, plan.passthrough
    suppressed_unsafe = plan.suppressed_unsafe

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


# --- SURFACE-AND-CHOOSE (privacy/utility tradeoff is the USER'S call) -----------
# Mirrors the cohort builder's preview_cohort_options -> build_confirmed_cohort. The de-id
# tradeoff dial is k_target: higher k = stronger re-identification resistance, but more
# generalization/suppression = less analytic utility. preview_deid_options SURFACES the
# frontier (read-only); apply_deid commits the k the user picked. run_deid stays as the
# one-call path for callers that just want the k=5 default.

def preview_deid_options(raw_fqn: str, k_candidates=(2, 5, 10, 20),
                         profile: str | None = None, warehouse_id: str | None = None) -> str:
    """READ-ONLY. Surface the privacy/utility tradeoff so the USER picks the point.

    Shows (a) the per-column plan — what is redacted vs tokenized vs date→year vs generalized
    vs kept vs suppressed — and (b) a k frontier: for each candidate k, what the k-anonymity
    engine would generalize/suppress and the utility cost. BUILDS NOTHING (the generalization
    search is count-only). Call this FIRST; show it to the user; get their k; call apply_deid.
    """
    catalog, schema, table = _split_fqn(raw_fqn)
    q = Q(catalog, schema, profile=profile, warehouse_id=warehouse_id)
    plan = _plan_columns(q, table)
    total = int(q(f"SELECT COUNT(*) FROM {table}")[0][0]) or 1

    lines = ["## De-identification preview — choose the privacy/utility point", ""]
    detected = "\n".join(f"  - {c} → {klass}" for c, klass in plan.phi_cols) or "  (none)"
    lines += ["**PHI detected (auto):**", detected, ""]
    lines += ["**Per-column plan (Safe Harbor strategy — redaction vs reduction):**",
              f"  - **Redacted / removed** (direct identifiers): {', '.join(plan.dropped_direct) or '—'}",
              f"  - **Tokenized** (pseudonym, linkage kept): {', '.join(plan.id_columns) or '—'}",
              f"  - **Date → year**: {', '.join(plan.date_year_columns) or '—'}",
              f"  - **Generalized / reduced** (quasi-identifiers, k-anon): "
              f"{', '.join(qi.label for qi in plan.qis) or '—'}",
              f"  - **Kept as-is** (numeric measures): {', '.join(plan.passthrough) or '—'}",
              f"  - **Suppressed** (unknown non-numeric, deny-by-default): "
              f"{', '.join(plan.suppressed_unsafe) or '—'}",
              ""]

    lines += ["**Privacy ↔ utility frontier — CHOOSE a k (higher k = stronger anonymization, but "
              "more generalization/suppression = less utility). Do not pick for the user:**", "",
              "| k_target | k achieved | rows suppressed | QIs kept full | QIs coarsened | QIs value-suppressed | detail |",
              "|---|---|---|---|---|---|---|"]
    for k in k_candidates:
        gen = find_minimal_generalization(q, table, qis=plan.qis, k_target=int(k))
        summ = generalization_summary(plan.qis, gen)
        full = [s["quasi_identifier"] for s in summ if s["level"] == 0]
        coarsened = [f"{s['quasi_identifier']}(L{s['level']}/{s['of']})"
                     for s in summ if 0 < s["level"] < s["of"]]
        dropped = [s["quasi_identifier"] for s in summ if s["of"] and s["level"] == s["of"]]
        supp = gen.suppressed_rows
        detail = "; ".join(coarsened + [f"{d} (value-suppressed)" for d in dropped]) or "none"
        lines.append(f"| {k} | {gen.k_achieved} | {supp} ({100 * supp / total:.1f}%) | "
                     f"{len(full)} | {len(coarsened)} | {len(dropped)} | {detail} |")
    lines += ["", "Reply with the k you want, then call `apply_deid(<table>, k_target=<k>)`. "
              "The per-column redaction/tokenize/generalize plan above is applied at that k."]
    return "\n".join(lines)


def apply_deid(raw_fqn: str, k_target: int, view_name: str | None = None,
               profile: str | None = None, warehouse_id: str | None = None) -> str:
    """Apply de-identification at the k the USER chose after preview_deid_options.

    k_target is REQUIRED — it is the user's privacy/utility choice, surfaced by the preview and
    never picked for them. Delegates to the vetted run_deid pipeline (which builds the governed
    view, verifies actual k over ALL surviving quasi-identifiers, and scans for residual leaks)."""
    return run_deid(raw_fqn, view_name=view_name, k_target=k_target,
                    profile=profile, warehouse_id=warehouse_id)


if __name__ == "__main__":
    fqn = sys.argv[1] if len(sys.argv) > 1 else "main.clinical.patients_raw"
    prof = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    print("=== preview_deid_options (read-only frontier) ===")
    print(preview_deid_options(fqn, profile=prof))
