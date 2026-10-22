"""Grounding for deck content — pull REAL figures from a Unity Catalog artifact.

Why this exists: a deck is only trustworthy if every number on it came from the data. This
module is the bridge between an upstream HLS artifact (a cohort table from cohort-builder,
a de-identified view from phi-deidentifier, a model's metrics, a measure catalog, any UC
table) and the deck spec. The agent calls these helpers, drops the returned figures into
`metrics`/`bar_chart` slides, and cites the source — it never types a number by hand.

The one guarantee: GROUNDED — counts, distributions, and numeric summaries come from live
SQL over the artifact, each returned with the exact `source` string to print as the slide
caption.

PHI handling is NOT done here. This module presents whatever table it is given as-is. De-
identification is delegated to the `phi-deidentifier` skill: run it first and build the deck
from its governed, k-anonymous view. If `phi-deidentifier` is not available in the
environment, ASK the user whether PHI may be included before building (see SKILL.md,
"De-identify before you present").

The SQL runner mirrors hls-cohort-builder's Q: ambient auth in-workspace, optional
`profile=` locally, polls to completion.
"""

from __future__ import annotations


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
    """Row count + column schema for a UC table/view.

    Returns {table, row_count, columns:[{name,type}]}.
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
    }


def column_distribution(table, column, profile=None, warehouse_id=None, q=None, top=8):
    """GROUNDED value counts for a categorical column, shaped as bar_chart `bars`.
    Returns {bars, source}.
    """
    _check_fqn(table)
    q = q or Q(profile=profile, warehouse_id=warehouse_id)
    rows = q(
        f"SELECT CAST({column} AS STRING) AS v, COUNT(*) AS n FROM {table} "
        f"GROUP BY 1 ORDER BY n DESC LIMIT {int(top)}"
    )
    bars = [{"label": "(null)" if r[0] is None else r[0], "value": int(r[1])} for r in rows]
    return {
        "bars": bars,
        "source": f"Source: {table} · GROUP BY {column}",
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


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else round(f, 2)
    except (TypeError, ValueError):
        return v
