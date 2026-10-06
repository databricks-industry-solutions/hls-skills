"""Adaptive k-anonymity generalization engine -- the de-id skill's centerpiece.

The baseline failure this fixes: Genie strips direct identifiers but leaves quasi-
identifiers (age, ZIP3, sex, length-of-stay) at full granularity, so ~87% of rows
are unique (k=1) and it never checks. This engine generalizes quasi-identifiers
along defined hierarchies until every equivalence class has >= k members,
suppressing the residual rows that cannot reach k.

Pure-Python + SQL-expression emitting: it computes the minimal generalization level
per quasi-identifier, then hands apply_uc_governance.py the SQL to realize it in a
Unity Catalog view. Deterministic; no model calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --- Generalization hierarchies -----------------------------------------------
# Each quasi-identifier has ordered levels 0..N; level 0 = finest, higher = coarser.
# A level is a SQL expression template applied to the raw column.

@dataclass
class QuasiIdentifier:
    column: str
    levels: list          # SQL expr templates, finest -> coarsest; "{c}" = raw column ref
    label: str = ""
    utility: float = 1.0  # higher = more analytically valuable => coarsen LAST

    def expr(self, level: int) -> str:
        level = max(0, min(level, len(self.levels) - 1))
        return self.levels[level].replace("{c}", self.column)

    @property
    def max_level(self) -> int:
        return len(self.levels) - 1


# Default hierarchies for the demo schema. Coarser levels trade utility for k.
DEFAULT_QIS = [
    QuasiIdentifier(
        column="age_band",
        levels=[
            "{c}",                                                        # L0: decade band (raw)
            "CASE WHEN {c}='90+' OR {c} IN ('70s','80s') THEN '65+' "
            "WHEN {c} IN ('0s','10s') THEN '0-17' ELSE '18-64' END",      # L1: 3 life-stage bands
            "'all-ages'",                                                 # L2: suppress
        ],
        label="age",
        utility=3.0,          # clinically valuable -> preserve
    ),
    QuasiIdentifier(
        column="zip",
        levels=[
            "LEFT({c},3)",        # L0: ZIP3 (Safe Harbor max)
            "LEFT({c},1)",        # L1: ZIP1 (region)
            "'***'",              # L2: suppress
        ],
        label="geo",
        utility=1.0,          # least valuable clinically -> coarsen first
    ),
    QuasiIdentifier(
        column="__los__",        # derived: DATEDIFF(discharge, admit); special-cased below
        levels=[
            "{c}",                                                        # L0: exact days
            "CASE WHEN {c}<=3 THEN '1-3d' WHEN {c}<=7 THEN '4-7d' ELSE '8-14d' END",  # L1: buckets
            "'any-LOS'",                                                  # L2: suppress
        ],
        label="length_of_stay",
        utility=2.5,          # longitudinal value -> preserve where possible
    ),
    QuasiIdentifier(
        column="sex",
        levels=["{c}", "'*'"],   # L0: raw, L1: suppress
        label="sex",
        utility=2.0,
    ),
]

LOS_EXPR = "DATEDIFF(discharge_date, admit_date)"   # substituted for __los__ column ref


def _resolve_expr(qi: QuasiIdentifier, level: int) -> str:
    e = qi.expr(level)
    return e.replace("__los__", f"({LOS_EXPR})")


# --- Generic, data-driven hierarchies for ANY column -------------------------
# Custom ladders above win when a column is known. For an unknown quasi-identifier,
# build a fallback ladder from the column's TYPE so the engine is never "stuck":
#   numeric     -> exact -> quartile buckets -> halves -> suppress
#   categorical -> keep -> merge rare values into 'other' -> suppress
# This is what makes the skill work on tables beyond the demo schema.

def _numeric_quartile_levels(column: str, q1, q2, q3) -> list:
    """Bucket a numeric column at its own quartiles, then halves, then suppress."""
    c = "{c}"
    quartile = (f"CASE WHEN {c} <= {q1} THEN 'Q1' WHEN {c} <= {q2} THEN 'Q2' "
                f"WHEN {c} <= {q3} THEN 'Q3' ELSE 'Q4' END")
    half = f"CASE WHEN {c} <= {q2} THEN 'low' ELSE 'high' END"
    return [c, quartile, half, "'*'"]


def make_generic_qi(profile, utility: float = 1.5, q=None, table: str | None = None):
    """Build a fallback QuasiIdentifier from a column profile (see profile_table).

    Numeric columns are bucketed at their observed quartiles (data-driven, not
    hardcoded thresholds). Categorical columns keep -> merge-rare-into-other (needs
    q+table to find frequent values) -> suppress. Returns None for columns that make
    no sense to generalize (single value / all null).
    """
    col = profile.column
    dtype = (profile.data_type or "").lower()
    if profile.distinct_count is not None and profile.distinct_count <= 1:
        return None

    is_numeric = any(t in dtype for t in ("int", "double", "float", "decimal", "long", "short", "byte"))
    if is_numeric:
        vals = []
        for v in profile.sample_values:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        if len(vals) >= 4:
            vals.sort()
            n = len(vals)
            q1, q2, q3 = vals[n // 4], vals[n // 2], vals[(3 * n) // 4]
            levels = _numeric_quartile_levels(col, q1, q2, q3)
        else:
            levels = ["{c}", "'*'"]     # too few samples to bucket -> keep or suppress
        return QuasiIdentifier(column=col, levels=levels, label=col, utility=utility)

    # categorical: keep -> merge rare into 'other' (top-N frequent kept) -> suppress.
    # The middle rung needs the actual frequent values; if a SQL runner + table are
    # provided we compute them, otherwise fall back to keep -> suppress.
    if q is not None and table is not None:
        top = [r[0] for r in q(
            f"SELECT `{col}` FROM {table} WHERE `{col}` IS NOT NULL "
            f"GROUP BY `{col}` ORDER BY COUNT(*) DESC LIMIT 5") if r and r[0] is not None]
        if top:
            keep_list = ", ".join("'" + str(v).replace("'", "''") + "'" for v in top)
            merge = f"CASE WHEN {{c}} IN ({keep_list}) THEN {{c}} ELSE 'other' END"
            levels = ["{c}", merge, "'*'"]
            return QuasiIdentifier(column=col, levels=levels, label=col, utility=utility)
    levels = ["{c}", "'other'"]
    return QuasiIdentifier(column=col, levels=levels, label=col, utility=utility)


def build_qis(profiles, phi_classifications, custom_qis=None, q=None, table: str | None = None) -> list:
    """Assemble the quasi-identifier set for a table.

    Uses custom_qis (or DEFAULT_QIS) for known columns, and generates generic
    data-driven QIs for any OTHER column flagged as a quasi-identifier by detection
    but lacking a custom ladder. This is the "works on any table" path.

    phi_classifications: list from detect_phi; columns classed as quasi-identifier
    types (geo_sub_state, age_over_89, or 'not_phi' demographics kept for analysis)
    are candidates. Direct identifiers are handled elsewhere (dropped/tokenized).
    """
    # A custom QI only applies if its column actually exists in THIS table. The demo
    # DEFAULT_QIS reference age_band/zip/sex and a derived LOS (needs admit+discharge);
    # skip any whose columns are absent, so the engine works on arbitrary tables.
    present_cols = {p.column for p in profiles}

    def _custom_applies(qi) -> bool:
        if qi.column == "__los__":
            return {"admit_date", "discharge_date"} <= present_cols
        return qi.column in present_cols

    custom = {qi.column: qi for qi in (custom_qis or DEFAULT_QIS) if _custom_applies(qi)}
    known_cols = set(custom)
    result = list(custom.values())

    # Columns detection thinks are quasi-identifiers but we have no custom ladder for.
    # NOTE: date_element is intentionally EXCLUDED -- raw dates are handled by year-
    # reduction (or LOS derivation) upstream, not turned into generic string QIs. Adding
    # them here double-counts temporal info and forces over-generalization (k collapses
    # everything into one class). Geo and age are the generic quasi-identifiers.
    QI_CLASSES = {"geo_sub_state", "age_over_89"}
    prof_by_col = {p.column: p for p in profiles}
    for c in phi_classifications:
        if c.column in known_cols:
            continue
        # treat detected geo/age/date quasi-identifiers, plus low-cardinality demographics
        prof = prof_by_col.get(c.column)
        looks_demographic = (prof and prof.distinct_count is not None
                             and 1 < prof.distinct_count <= 15)
        if c.detected_class in QI_CLASSES or (c.detected_class == "not_phi" and looks_demographic):
            qi = make_generic_qi(prof, q=q, table=table) if prof else None
            if qi:
                result.append(qi)
    return result


@dataclass
class GeneralizationResult:
    levels: dict = field(default_factory=dict)   # column -> chosen level
    k_achieved: int = 0
    suppressed_rows: int = 0
    group_by_exprs: list = field(default_factory=list)
    select_exprs: list = field(default_factory=list)


def _count_kmin_and_suppressed(q, table: str, exprs: list, k_target: int) -> tuple[int, int]:
    """Return (min group size, rows in groups smaller than k) for a generalization."""
    grp = ", ".join(exprs)
    rows = q(f"""SELECT MIN(cnt), SUM(CASE WHEN cnt < {k_target} THEN cnt ELSE 0 END), SUM(cnt)
                 FROM (SELECT {grp}, COUNT(*) cnt FROM {table} GROUP BY {grp})""")
    kmin = int(rows[0][0]) if rows and rows[0][0] is not None else 0
    below = int(rows[0][1]) if rows and rows[0][1] is not None else 0
    return kmin, below


def find_minimal_generalization(q, table: str, qis=None, k_target: int = 5,
                                max_suppression_frac: float = 0.10) -> GeneralizationResult:
    """Greedily coarsen quasi-identifiers until k_target is met with acceptable suppression.

    Strategy: start all-finest. While k < target, coarsen the QI whose coarsening most
    reduces the number of sub-k rows (greedy). Stop when k_target met, or when further
    coarsening would exceed max_suppression_frac and we fall back to suppressing the
    residual sub-k rows via a WHERE filter in the view.

    `q` is a callable running SQL and returning rows (see apply_uc_governance._Q).
    """
    qis = qis or DEFAULT_QIS
    levels = {qi.column: 0 for qi in qis}

    def exprs_for(levels):
        return [_resolve_expr(qi, levels[qi.column]) for qi in qis]

    total = int(q(f"SELECT COUNT(*) FROM {table}")[0][0])

    for _ in range(sum(qi.max_level for qi in qis) + 1):
        exprs = exprs_for(levels)
        kmin, below = _count_kmin_and_suppressed(q, table, exprs, k_target)
        if kmin >= k_target:
            return GeneralizationResult(levels=dict(levels), k_achieved=kmin, suppressed_rows=0,
                                        group_by_exprs=exprs, select_exprs=exprs)
        # Try coarsening each QI one level. Pick the move with the best benefit/cost:
        # benefit = reduction in sub-k rows; cost = utility weight of the QI coarsened.
        # This preserves high-utility clinical variables (age, LOS) and sacrifices
        # low-utility ones (geo) first -- fixing the naive "minimize sub-k rows" flaw
        # that nuked age and LOS while keeping ZIP.
        best = None
        for qi in qis:
            if levels[qi.column] >= qi.max_level:
                continue
            trial = dict(levels); trial[qi.column] += 1
            _, tbelow = _count_kmin_and_suppressed(q, table, exprs_for(trial), k_target)
            benefit = below - tbelow                       # rows pulled out of sub-k
            score = benefit / qi.utility                   # per unit of utility sacrificed
            if best is None or score > best[1]:
                best = (qi.column, score, trial)
        if best is None:
            break                          # fully coarsened; suppress residual below
        levels = best[2]

    # Fully generalized but still k<target for some groups -> suppress residual rows.
    exprs = exprs_for(levels)
    kmin, below = _count_kmin_and_suppressed(q, table, exprs, k_target)
    if below / total <= max_suppression_frac:
        return GeneralizationResult(levels=dict(levels), k_achieved=k_target, suppressed_rows=below,
                                    group_by_exprs=exprs, select_exprs=exprs)
    # Even suppression is too costly -> return honest partial result; caller must warn.
    return GeneralizationResult(levels=dict(levels), k_achieved=kmin, suppressed_rows=below,
                                group_by_exprs=exprs, select_exprs=exprs)


def generalization_summary(qis, result: GeneralizationResult) -> list[dict]:
    """Human-readable per-QI level chosen, for the audit report."""
    qis = qis or DEFAULT_QIS
    out = []
    for qi in qis:
        lvl = result.levels.get(qi.column, 0)
        out.append({"quasi_identifier": qi.label, "column": qi.column,
                    "level": lvl, "of": qi.max_level, "expr": _resolve_expr(qi, lvl)})
    return out
