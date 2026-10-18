"""Grounding + governance for deck content — pull REAL figures from a Unity Catalog
artifact, and refuse to leak PHI into a shareable file.

Why this exists: a deck is only trustworthy if every number on it came from the data. This
module is the bridge between an upstream HLS artifact (a cohort table from cohort-builder,
a de-identified view from phi-deidentifier, a model's metrics, a measure catalog, any UC
table) and the deck spec. The agent calls these helpers, drops the returned figures into
`metrics`/`bar_chart` slides, and cites the source — it never types a number by hand.

Two guarantees:
  1. GROUNDED — counts, distributions, and numeric summaries come from live SQL over the
     artifact, each returned with the exact `source` string to print as the slide caption.
  2. GOVERNED — a shareable deck must not embed row-level PHI. `scan_phi()` flags
     direct-identifier columns (pure, testable), `assert_shareable()` BLOCKS sample rows
     from a table that still carries them (pointing you at phi-deidentifier), and
     distributions SUPPRESS small cells (default k<11) so a bar can't re-identify anyone.

The SQL runner mirrors hls-cohort-builder's Q: ambient auth in-workspace, optional
`profile=` locally, polls to completion.
"""

from __future__ import annotations

import re

# --- direct-identifier column classifier (PURE — no SDK, fully testable) -----
# HIPAA Safe Harbor §164.514(b)(2) direct & quasi identifiers, matched on COLUMN NAME.
# This is a name-based screen (catches the common cases); it is a guardrail, not a
# substitute for running phi-deidentifier, which inspects values and enforces k-anonymity.
_IDENTIFIER_PATTERNS = [
    ("name", r"(^|_)(first|last|full|patient|member|given|family|sur|maiden)?_?name($|_)"),
    ("ssn", r"ssn|social_?security"),
    ("mrn", r"\bmrn\b|medical_?record"),
    ("member_id", r"member_?(id|number|no)|subscriber_?(id|number)|beneficiary_?id"),
    ("account", r"account_?(id|number|no)|policy_?(id|number|no)|claim_?(id|number)"),
    ("email", r"e?_?mail"),
    ("phone", r"phone|fax|mobile|telephone"),
    ("address", r"address|street|^addr|city|zip|postal"),
    ("date_of_birth", r"birth_?date|date_?of_?birth|\bdob\b"),
    ("fine_date", r"admit_?date|discharge_?date|death_?date|service_?date|visit_?date|encounter_?date"),
    ("device_id", r"device_?(id|serial)|serial_?number"),
    ("url", r"\burl\b|website"),
    ("ip", r"ip_?address|\bip\b"),
    ("biometric", r"fingerprint|biometric|face_?id"),
    ("other_unique", r"license|certificate|vehicle|vin|passport"),
]

# A trailing "_year" or an age *band* column is generally safe; whole age in years is a
# quasi-identifier only in combination, so we flag it softly (quasi), not as a hard block.
_QUASI_PATTERNS = [
    ("birth_year", r"birth_?year|year_?of_?birth"),
    ("age", r"(^|_)age($|_)"),
    ("sex", r"(^|_)(sex|gender)($|_)"),
    ("race", r"(^|_)(race|ethnicity)($|_)"),
    ("zip3", r"zip3|zip_?3"),
]

DEFAULT_SMALL_CELL_K = 11  # suppress distribution cells with fewer rows than this


def classify_column(name: str):
    """Return ('direct', identifier_type) / ('quasi', type) / ('safe', None) for a column name."""
    low = re.sub(r"[^a-z0-9_]", "", str(name).lower())
    for kind, pat in _IDENTIFIER_PATTERNS:
        if re.search(pat, low):
            # "birth_year"/"age_band" style columns are generalized → not a direct id
            if kind in ("date_of_birth", "fine_date") and ("year" in low or "band" in low):
                return ("quasi", kind)
            return ("direct", kind)
    for kind, pat in _QUASI_PATTERNS:
        if re.search(pat, low):
            return ("quasi", kind)
    return ("safe", None)


def scan_phi(columns):
    """Classify a list of column names. Returns {direct:[(col,type)], quasi:[(col,type)]}.
    Pure — call it on the output of profile_table()['columns'] or any column list."""
    direct, quasi = [], []
    for c in columns:
        kind, t = classify_column(c)
        if kind == "direct":
            direct.append((c, t))
        elif kind == "quasi":
            quasi.append((c, t))
    return {"direct": direct, "quasi": quasi}


# --- SQL runner (SDK; mirrors hls-cohort-builder Q) --------------------------

class Q:
    def __init__(self, catalog=None, schema=None, profile=None, warehouse_id=None):
        from databricks.sdk import WorkspaceClient
        self.w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
        self.wid = warehouse_id or next(wh.id for wh in self.w.warehouses.list())
        self.catalog, self.schema = catalog, schema

    def __call__(self, stmt):
        import time
        from databricks.sdk.service.sql import StatementState
        r = self.w.statement_execution.execute_statement(
            warehouse_id=self.wid, catalog=self.catalog, schema=self.schema,
            statement=stmt, wait_timeout="50s")
        while r.status and r.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(2)
            r = self.w.statement_execution.get_statement(r.statement_id)
        if r.status and r.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(f"{r.status.error} :: {stmt[:200]}")
        return r.result.data_array if r.result else []


def _check_fqn(table: str):
    if len(str(table).split(".")) != 3:
        raise ValueError(f"Expected a fully-qualified catalog.schema.table, got: {table!r}")


# --- grounded reads ----------------------------------------------------------

def profile_table(table, profile=None, warehouse_id=None, q=None):
    """Row count + column schema for a UC table/view, plus a PHI scan of the columns.

    Returns {table, row_count, columns:[{name,type}], phi:{direct,quasi}}.
    """
    _check_fqn(table)
    q = q or Q(profile=profile, warehouse_id=warehouse_id)
    cols = []
    for r in q(f"DESCRIBE {table}"):
        name = (r[0] or "").strip()
        if not name or name.startswith("#"):
            break
        cols.append({"name": name, "type": (r[1] or "").strip() if len(r) > 1 else ""})
    n = q(f"SELECT COUNT(*) FROM {table}")
    row_count = int(n[0][0]) if n and n[0] else 0
    return {
        "table": table,
        "row_count": row_count,
        "columns": cols,
        "phi": scan_phi([c["name"] for c in cols]),
    }


def column_distribution(table, column, profile=None, warehouse_id=None, q=None,
                        top=8, small_cell_k=DEFAULT_SMALL_CELL_K):
    """GROUNDED, small-cell-suppressed value counts for a categorical column, shaped as
    bar_chart `bars`. Cells with count < small_cell_k are dropped (re-identification guard)
    and reported in `suppressed`. Returns {bars, source, suppressed}.
    """
    _check_fqn(table)
    q = q or Q(profile=profile, warehouse_id=warehouse_id)
    rows = q(
        f"SELECT CAST({column} AS STRING) AS v, COUNT(*) AS n FROM {table} "
        f"GROUP BY 1 ORDER BY n DESC LIMIT {int(top) + 50}"
    )
    bars, suppressed = [], 0
    for v, n in ((r[0], int(r[1])) for r in rows):
        if n < small_cell_k:
            suppressed += 1
            continue
        bars.append({"label": "(null)" if v is None else v, "value": n})
        if len(bars) >= top:
            break
    return {
        "bars": bars,
        "suppressed": suppressed,
        "source": f"Source: {table} · GROUP BY {column} (cells < {small_cell_k} suppressed)",
    }


def numeric_summary(table, column, profile=None, warehouse_id=None, q=None):
    """GROUNDED min / max / avg / median / count for a numeric column.
    Returns {count, min, max, avg, median, source}."""
    _check_fqn(table)
    q = q or Q(profile=profile, warehouse_id=warehouse_id)
    r = q(
        f"SELECT COUNT({column}), MIN({column}), MAX({column}), AVG({column}), "
        f"percentile_approx({column}, 0.5) FROM {table}"
    )[0]
    return {
        "count": int(r[0]) if r[0] is not None else 0,
        "min": _num(r[1]), "max": _num(r[2]), "avg": _num(r[3]), "median": _num(r[4]),
        "source": f"Source: {table}.{column}",
    }


def cohort_summary(table, profile=None, warehouse_id=None, q=None, id_col="patient_id"):
    """GROUNDED headline for a cohort/dataset table: N rows and N distinct subjects.
    Returns {n_rows, n_subjects, source}. Use for a `metrics` tile."""
    _check_fqn(table)
    q = q or Q(profile=profile, warehouse_id=warehouse_id)
    cols = {c["name"].lower() for c in profile_table(table, q=q)["columns"]}
    sel = f"COUNT(*), COUNT(DISTINCT {id_col})" if id_col.lower() in cols else "COUNT(*), COUNT(*)"
    r = q(f"SELECT {sel} FROM {table}")[0]
    return {
        "n_rows": int(r[0]), "n_subjects": int(r[1]),
        "source": f"Source: {table}",
    }


# --- governance gate ---------------------------------------------------------

def assert_shareable(table, allow_sample_rows=False, profile=None, warehouse_id=None, q=None):
    """Governance gate for a deck sourced from `table`.

    - Aggregates (counts, distributions, numeric summaries) are allowed from any table.
    - Row-level SAMPLE data is BLOCKED when the table still carries direct identifiers:
      a shareable file must not embed PHI. The fix is to de-identify first (phi-deidentifier)
      and build the deck from the governed view.

    Returns the profile dict (with a 'shareable' verdict) when it passes; raises PhiLeakError
    when `allow_sample_rows=True` on a table that has direct identifiers.
    """
    prof = profile_table(table, profile=profile, warehouse_id=warehouse_id, q=q)
    direct = prof["phi"]["direct"]
    prof["shareable"] = {
        "aggregates_ok": True,
        "sample_rows_ok": not direct,
        "direct_identifiers": direct,
        "quasi_identifiers": prof["phi"]["quasi"],
    }
    if allow_sample_rows and direct:
        cols = ", ".join(f"{c} ({t})" for c, t in direct)
        raise PhiLeakError(
            f"{table} still carries direct identifiers [{cols}]; sample rows cannot go into a "
            f"shareable deck. De-identify it first with phi-deidentifier and build from the "
            f"governed view, or present grounded AGGREGATES only (counts/distributions)."
        )
    return prof


class PhiLeakError(RuntimeError):
    """Raised when sample PHI rows would be embedded in a shareable deck."""


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else round(f, 2)
    except (TypeError, ValueError):
        return v
