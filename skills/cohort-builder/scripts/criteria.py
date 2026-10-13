"""Generalized clinical criteria: measure thresholds + demographic/attribute filters.

PURE-PYTHON (no Databricks SDK) so the generalization logic is unit-testable offline,
exactly like interactions.py. cohort_run.py grounds columns against the live table and
executes SQL; this module owns the data-driven DECISIONS:

  - CLINICAL_THRESHOLDS : the registry of ambiguous "out-of-range" terms (uncontrolled
                          HbA1c, uncontrolled BP, high LDL, obesity, CKD/eGFR, ...) ->
                          the measure, the candidate column names, and the >1 defensible
                          cutoff OPTIONS the skill must SURFACE (never silently pick).
  - detect_threshold_term / looks_like_threshold : find a registered term, OR notice an
                          UNREGISTERED out-of-range phrase so the skill can FAIL LOUD
                          (ask for the column + cutoff) instead of dropping the criterion.
  - ground_measure_column : pick the real measure column present in the table (explicit
                          override > first registry candidate present), or None -> fail loud.
  - compile_demographics : turn age_min/age_max + sex + generic filters into grounded,
                          alias-safe SQL predicate Filters, reporting any that cannot ground.

This is what makes the skill work across conditions, clinical values, ages, genders, and
arbitrary structured attributes -- not just the seeded diabetes/HbA1c phenotype.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# --- SQL helpers (pure) -------------------------------------------------------

NUMERIC_OPS = (">", ">=", "<", "<=", "=", "!=", "<>")
SET_OPS = ("in", "not in")


def sql_lit(value) -> str:
    """Single-quote + escape a scalar for safe inlining; numbers pass through bare."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


# --- Clinical threshold registry ----------------------------------------------
# Each ambiguous term maps to a measure that has MORE THAN ONE defensible operational
# cutoff. The skill SURFACES the options with real N impact; it never silently picks one
# (the baseline's documented failure). `measure_candidates` are the column names we try, in
# order, to GROUND the measure against the actual table schema -- so the same term works
# whether the column is `hba1c_value`, `a1c`, `systolic_bp`, `sbp`, etc.

@dataclass
class ThresholdSpec:
    term: str
    measure_label: str
    measure_candidates: list          # column names tried in order against the table schema
    options: list                     # [{label, op, value}] -- the choices to surface


CLINICAL_THRESHOLDS = [
    ThresholdSpec(
        "uncontrolled hba1c", "HbA1c",
        ["hba1c_value", "hba1c", "a1c", "hemoglobin_a1c", "hgba1c"],
        [{"label": ">8.0% (common clinical 'uncontrolled')", "op": ">", "value": 8.0},
         {"label": ">=9.0% (HEDIS 'poor control')", "op": ">=", "value": 9.0}],
    ),
    ThresholdSpec(
        "poorly controlled hba1c", "HbA1c",
        ["hba1c_value", "hba1c", "a1c", "hemoglobin_a1c", "hgba1c"],
        [{"label": ">=9.0% (HEDIS 'poor control')", "op": ">=", "value": 9.0},
         {"label": ">8.0% (broader)", "op": ">", "value": 8.0}],
    ),
    ThresholdSpec(
        "uncontrolled hypertension", "Systolic BP (mmHg)",
        ["systolic_bp", "sbp", "systolic", "bp_systolic", "systolic_blood_pressure"],
        [{"label": ">=140 (JNC7 / traditional stage 2)", "op": ">=", "value": 140.0},
         {"label": ">=130 (2017 ACC/AHA stage 1)", "op": ">=", "value": 130.0}],
    ),
    ThresholdSpec(
        "uncontrolled blood pressure", "Systolic BP (mmHg)",
        ["systolic_bp", "sbp", "systolic", "bp_systolic", "systolic_blood_pressure"],
        [{"label": ">=140 (JNC7 / traditional stage 2)", "op": ">=", "value": 140.0},
         {"label": ">=130 (2017 ACC/AHA stage 1)", "op": ">=", "value": 130.0}],
    ),
    ThresholdSpec(
        "high ldl", "LDL cholesterol (mg/dL)",
        ["ldl", "ldl_c", "ldl_cholesterol", "ldl_value"],
        [{"label": ">=190 (severe hypercholesterolemia)", "op": ">=", "value": 190.0},
         {"label": ">=160 (high)", "op": ">=", "value": 160.0},
         {"label": ">=100 (above optimal; ASCVD target)", "op": ">=", "value": 100.0}],
    ),
    ThresholdSpec(
        "obesity", "BMI (kg/m^2)",
        ["bmi", "body_mass_index", "bmi_value"],
        [{"label": ">=30 (obese, WHO class I+)", "op": ">=", "value": 30.0},
         {"label": ">=40 (severe/class III)", "op": ">=", "value": 40.0}],
    ),
    ThresholdSpec(
        "overweight", "BMI (kg/m^2)",
        ["bmi", "body_mass_index", "bmi_value"],
        [{"label": ">=25 (overweight+, WHO)", "op": ">=", "value": 25.0},
         {"label": ">=30 (obese only)", "op": ">=", "value": 30.0}],
    ),
    ThresholdSpec(
        "reduced egfr", "eGFR (mL/min/1.73m^2)",
        ["egfr", "egfr_value", "gfr", "estimated_gfr"],
        [{"label": "<60 (CKD stage 3+, KDIGO)", "op": "<", "value": 60.0},
         {"label": "<45 (CKD stage 3b+)", "op": "<", "value": 45.0},
         {"label": "<30 (CKD stage 4+)", "op": "<", "value": 30.0}],
    ),
    ThresholdSpec(
        "chronic kidney disease", "eGFR (mL/min/1.73m^2)",
        ["egfr", "egfr_value", "gfr", "estimated_gfr"],
        [{"label": "<60 (CKD stage 3+, KDIGO)", "op": "<", "value": 60.0},
         {"label": "<45 (CKD stage 3b+)", "op": "<", "value": 45.0},
         {"label": "<30 (CKD stage 4+)", "op": "<", "value": 30.0}],
    ),
]

_THRESHOLD_BY_TERM = {s.term: s for s in CLINICAL_THRESHOLDS}

# Phrases that signal an out-of-range criterion. If one appears but no registry term matches
# (or the measure column can't be grounded), the skill must ASK rather than drop the criterion.
_OUT_OF_RANGE_HINTS = (
    "uncontrolled", "poorly controlled", "poor control", "out of control", "out-of-range",
    "out of range", "elevated", "high ", "low ", "abnormal", "above goal", "above target",
    "below goal", "not at goal", "not at target",
)


def detect_threshold_term(intent_text: str) -> ThresholdSpec | None:
    """Return the registered ThresholdSpec whose term appears in the intent, else None.
    Longest term first so 'poorly controlled hba1c' wins over a bare substring."""
    text = (intent_text or "").lower()
    for spec in sorted(CLINICAL_THRESHOLDS, key=lambda s: -len(s.term)):
        if spec.term in text:
            return spec
    return None


def looks_like_threshold(intent_text: str) -> bool:
    """True if the intent contains an out-of-range phrase (so a measure cutoff is implied),
    whether or not it maps to a registered term. Drives FAIL-LOUD for unregistered measures."""
    text = (intent_text or "").lower()
    return any(h in text for h in _OUT_OF_RANGE_HINTS)


def ground_measure_column(available_cols, spec: ThresholdSpec | None = None,
                          explicit: str | None = None) -> str | None:
    """Resolve the real measure column present in the table.

    Precedence: an explicit caller-supplied column (if present) > the first registry
    candidate present. Returns None if nothing grounds -> the caller must fail loud.
    """
    cols = {c.lower() for c in available_cols}
    if explicit and explicit.lower() in cols:
        return explicit
    if explicit:                       # caller named a column that isn't in the table
        return None
    if spec:
        for cand in spec.measure_candidates:
            if cand.lower() in cols:
                return cand
    return None


# --- Demographic / attribute filters ------------------------------------------
# A grounded, alias-safe predicate. col_template carries a `{a}` placeholder where the table
# alias prefix goes (so the same Filter works in an aliased JOIN query and a bare one), and
# base_columns are the raw columns it references (for schema grounding).

AGE_COLUMN_CANDIDATES = ["age", "age_years", "patient_age", "current_age"]
BIRTHDATE_COLUMN_CANDIDATES = ["birth_date", "date_of_birth", "dob", "birthdate", "birth_dt"]
SEX_COLUMN_CANDIDATES = ["sex", "gender", "administrative_gender", "sex_at_birth"]


@dataclass
class Filter:
    col_template: str                 # e.g. "{a}age" or a derived expr with {a} before cols
    op: str                           # a NUMERIC_OP, or 'in'/'not in'
    value: object                     # scalar, or list/tuple for set ops
    label: str = ""                   # human-readable, for the readout
    base_columns: list = field(default_factory=list)   # raw cols referenced (for grounding)

    def to_dict(self) -> dict:
        return {"col_template": self.col_template, "op": self.op,
                "value": list(self.value) if isinstance(self.value, (list, tuple)) else self.value,
                "label": self.label, "base_columns": list(self.base_columns)}

    @staticmethod
    def from_dict(d: dict) -> "Filter":
        return Filter(d["col_template"], d["op"], d["value"], d.get("label", ""),
                      list(d.get("base_columns", [])))


def _validate_op(op: str) -> str:
    o = (op or "=").strip().lower() if op and op.strip().lower() in SET_OPS else (op or "=").strip()
    if o in SET_OPS or o in NUMERIC_OPS:
        return o
    raise ValueError(f"Unsupported operator {op!r}; use one of {NUMERIC_OPS + SET_OPS}")


def filter_sql(f: Filter, alias: str = "") -> str:
    """Render one Filter to a SQL predicate. `alias` ('' or e.g. 't') prefixes column refs."""
    prefix = f"{alias}." if alias else ""
    col = f.col_template.replace("{a}", prefix)
    op = _validate_op(f.op)
    if op in SET_OPS:
        vals = f.value if isinstance(f.value, (list, tuple)) else [f.value]
        rendered = ", ".join(sql_lit(v) for v in vals)
        return f"{col} {op.upper()} ({rendered})"
    return f"{col} {op} {sql_lit(f.value)}"


def filters_predicate(filters, alias: str = "") -> str:
    """AND all filters into one predicate (empty string if none)."""
    parts = [filter_sql(f, alias) for f in (filters or [])]
    return " AND ".join(f"({p})" for p in parts)


def _resolve_present(candidates, available_cols) -> str | None:
    cols = {c.lower(): c for c in available_cols}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]        # return the actual-cased column
    return None


def _age_expr(available_cols) -> tuple[str, list, str] | None:
    """Resolve an age EXPRESSION from the schema. An explicit age column is used directly;
    otherwise age is DERIVED from a birth-date column via datediff. Returns
    (col_template, base_columns, source_note) or None if neither is available."""
    age_col = _resolve_present(AGE_COLUMN_CANDIDATES, available_cols)
    if age_col:
        return "{a}" + age_col, [age_col], f"age column `{age_col}`"
    dob = _resolve_present(BIRTHDATE_COLUMN_CANDIDATES, available_cols)
    if dob:
        expr = "floor(datediff(current_date(), try_cast({a}" + dob + " AS date)) / 365.25)"
        return expr, [dob], f"age derived from `{dob}`"
    return None


def compile_demographics(available_cols, age_min=None, age_max=None, sex=None,
                         filters=None) -> tuple[list, list]:
    """Build grounded Filters from the ergonomic inputs + generic predicates.

    Inputs:
      age_min / age_max : numeric bounds -> >= / <= on a grounded age expr (or derived from DOB).
      sex               : a scalar or list -> = / IN on a grounded sex/gender column.
      filters           : list of dicts {column, op, value, label?} for ANY structured attribute
                          ("other variables") -- grounded against the schema.

    Returns (grounded_filters, unresolved) where `unresolved` is a list of human-readable
    descriptions of criteria that could NOT be grounded (so the caller can fail loud).
    """
    grounded, unresolved = [], []
    cols = {c.lower(): c for c in available_cols}

    if age_min is not None or age_max is not None:
        resolved = _age_expr(available_cols)
        if resolved is None:
            unresolved.append("age criterion (no age or birth-date column found in the table)")
        else:
            tmpl, base, src = resolved
            if age_min is not None:
                grounded.append(Filter(tmpl, ">=", float(age_min),
                                       f"age >= {age_min} ({src})", list(base)))
            if age_max is not None:
                grounded.append(Filter(tmpl, "<=", float(age_max),
                                       f"age <= {age_max} ({src})", list(base)))

    if sex is not None:
        sex_col = _resolve_present(SEX_COLUMN_CANDIDATES, available_cols)
        if sex_col is None:
            unresolved.append("sex/gender criterion (no sex/gender column found in the table)")
        elif isinstance(sex, (list, tuple)):
            grounded.append(Filter("{a}" + sex_col, "in", list(sex),
                                   f"{sex_col} in {list(sex)}", [sex_col]))
        else:
            grounded.append(Filter("{a}" + sex_col, "=", sex,
                                   f"{sex_col} = {sex}", [sex_col]))

    for spec in (filters or []):
        col = spec.get("column")
        if not col:
            continue
        if col.lower() not in cols:
            unresolved.append(f"filter on `{col}` (column not found in the table)")
            continue
        real = cols[col.lower()]
        op = spec.get("op", "=")
        val = spec.get("value")
        label = spec.get("label") or f"{real} {op} {val}"
        grounded.append(Filter("{a}" + real, op, val, label, [real]))

    return grounded, unresolved
