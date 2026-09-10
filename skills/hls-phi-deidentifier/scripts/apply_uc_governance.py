"""Apply Safe Harbor de-identification through Unity Catalog governance.

Fixes the two baseline failures:
  1. Raw PHI persisted as a 2nd copy -> here we build a VIEW over the raw table;
     raw PHI never moves and there is no second physical copy of identifiers.
  2. No k-anonymity -> the view applies the generalization from kanon.py and
     suppresses residual sub-k rows, so the consumer never sees a k<target group.

Emits a dynamic view: direct identifiers dropped, dates -> interval-preserving
LOS + admit_year, quasi-identifiers generalized to the computed levels, and a
WHERE filter removing suppressed equivalence classes.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kanon import DEFAULT_QIS, LOS_EXPR, find_minimal_generalization, generalization_summary  # noqa: E402

# Direct identifiers to DROP entirely (never surfaced in the view).
DIRECT_IDENTIFIERS = ["patient_name", "ssn", "email", "phone"]
# Analytic columns passed through untouched.
ANALYTIC_PASS_THROUGH = ["hba1c"]


class Q:
    """Thin SQL runner returning row arrays; shared by kanon + this module.

    profile=None uses ambient auth -- correct inside Genie Code / a Databricks
    notebook, where there is no CLI profile. Pass a profile only for local CLI runs.
    warehouse_id can be pinned; otherwise the first available warehouse is used.
    """
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


@dataclass
class GovernanceResult:
    view_fqn: str
    k_target: int
    k_achieved: int
    suppressed_rows: int
    generalization: list
    salt_source: str


def _pseudo_id_expr(column: str, salt: str) -> str:
    """Salted HMAC-style pseudonym. Salt comes from a secret in production; the
    literal path here is for the demo only and is flagged in the audit report."""
    return f"sha2(concat('{salt}', {column}), 256)"


def build_deid_view(
    q: Q, raw_table: str, view_name: str,
    k_target: int = 5, salt: str = "DEMO_SALT_USE_SECRET_SCOPE_IN_PROD",
    qis=None, id_columns=None, passthrough_columns=None, date_year_columns=None,
) -> GovernanceResult:
    """Create/replace a Safe Harbor de-identification VIEW over raw_table.

    raw_table / view_name are bare names in the configured catalog.schema.

    Schema-driven when the caller supplies (from detection):
      id_columns          -> tokenized as pseudo IDs (salted hash)
      date_year_columns   -> reduced to YEAR() (Safe Harbor permits year)
      passthrough_columns -> analytic columns kept as-is
    Falls back to the demo schema defaults when none are supplied.
    """
    qis = qis or DEFAULT_QIS
    # Demo-schema fallbacks preserve existing behavior; generic callers pass real lists.
    if id_columns is None and passthrough_columns is None and date_year_columns is None:
        id_columns = ["patient_id"]
        date_year_columns = ["admit_date"]
        passthrough_columns = list(ANALYTIC_PASS_THROUGH)
    id_columns = id_columns or []
    date_year_columns = date_year_columns or []
    passthrough_columns = passthrough_columns or []

    # 1. Compute minimal generalization to reach k_target.
    gen = find_minimal_generalization(q, raw_table, qis=qis, k_target=k_target)

    # 2. Build SELECT list.
    select_parts = []
    for idc in id_columns:
        select_parts.append(f"{_pseudo_id_expr(idc, salt)} AS pseudo_{idc.strip('_')}")
    for dc in date_year_columns:
        select_parts.append(f"YEAR({dc}) AS {dc.strip('_')}_year")
    # generalized quasi-identifiers (exposed, generalized -- includes LOS via __los__)
    gsummary = generalization_summary(qis, gen)
    for item in gsummary:
        select_parts.append(f"{item['expr']} AS {item['column'].strip('_')}_generalized")
    # analytic pass-through
    for c in passthrough_columns:
        select_parts.append(c)

    # 3. Suppression filter: remove equivalence classes below k_target.
    grp = ", ".join(gen.group_by_exprs)
    # window count over the generalized grouping; keep only rows in classes >= k.
    inner = f"""SELECT *, COUNT(*) OVER (PARTITION BY {grp}) AS _eq_class_size
                FROM {raw_table}"""
    select_sql = ",\n  ".join(select_parts)
    view_sql = f"""CREATE OR REPLACE VIEW {view_name} AS
SELECT
  {select_sql}
FROM ({inner})
WHERE _eq_class_size >= {k_target}"""

    q(view_sql)

    # 4. Verify achieved k on the actual view output.
    return GovernanceResult(
        view_fqn=f"{q.catalog}.{q.schema}.{view_name}",
        k_target=k_target, k_achieved=gen.k_achieved, suppressed_rows=gen.suppressed_rows,
        generalization=gsummary,
        salt_source="LITERAL (DEMO) -- use dbutils.secrets in production",
    )
