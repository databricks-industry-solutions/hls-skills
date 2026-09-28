"""Surface-and-choose interaction layer for the de-identifier (Phase 2, Enhancement A).

PURE-PYTHON (no Databricks SDK): this module owns the read-only DECISION SHEET the de-id
skill presents so the analyst controls the privacy/utility tradeoff BEYOND the single k dial.
run_deid.py calls these and executes; keeping them pure makes the logic unit-testable offline.

Surfaced decisions:
  - per_column_strategy : override the engine's per-column routing (drop / tokenize / date_year /
                          generalize / keep / suppress). This is also the QI-set control:
                          'generalize' makes a column a quasi-identifier, 'keep' takes it out.
  - date_handling       : year-only (default) / interval-preserving-derived / consistent shift.
  - utility_priority    : which quasi-identifiers to PRESERVE (coarsen last) -> feeds the
                          engine's per-QI utility weight (find_minimal_generalization divides
                          benefit by utility, so higher = preserved).
  - output_delivery     : governed UC view (default) / a re-runnable notebook / conversation-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --- Vocabularies -------------------------------------------------------------

DELIVERY_MODES = ("uc_view", "notebook", "conversation")
DEFAULT_DELIVERY = "uc_view"

# The per-column strategies the analyst can force. Maps directly to the DeidPlan role lists.
COLUMN_STRATEGIES = ("drop", "tokenize", "date_year", "generalize", "keep", "suppress")
# role name -> DeidPlan list attribute it populates
_STRATEGY_TO_ROLE = {
    "drop": "dropped_direct", "tokenize": "id_columns", "date_year": "date_year_columns",
    "generalize": "qi_columns", "keep": "passthrough", "suppress": "suppressed_unsafe",
}

DATE_HANDLING = ("year", "interval", "shift")
DEFAULT_DATE_HANDLING = "year"


def normalize_delivery(value: str | None) -> str:
    v = value or DEFAULT_DELIVERY
    if v not in DELIVERY_MODES:
        raise ValueError(f"output_delivery must be one of {DELIVERY_MODES}, got {value!r}")
    return v


def normalize_date_handling(value: str | None) -> str:
    v = value or DEFAULT_DATE_HANDLING
    if v not in DATE_HANDLING:
        raise ValueError(f"date_handling must be one of {DATE_HANDLING}, got {value!r}")
    return v


# --- Per-column strategy overrides (pure, over a role map) --------------------

def initial_role_map(dropped_direct, id_columns, date_year_columns, qi_columns,
                     passthrough, suppressed) -> dict:
    """Column -> current strategy, from a DeidPlan's role lists. The reverse of _STRATEGY_TO_ROLE."""
    m = {}
    for c in dropped_direct: m[c] = "drop"
    for c in id_columns: m[c] = "tokenize"
    for c in date_year_columns: m[c] = "date_year"
    for c in qi_columns: m[c] = "generalize"
    for c in passthrough: m[c] = "keep"
    for c in suppressed: m[c] = "suppress"
    return m


def apply_column_overrides(role_map: dict, overrides: dict | None) -> dict:
    """Return a NEW role map with the analyst's per-column strategy overrides applied.

    Validates: every overridden column must already be known (present in the plan), and every
    strategy must be one of COLUMN_STRATEGIES. Refuses silently-invalid input (a typo'd column
    would otherwise leave PHI unaddressed)."""
    if not overrides:
        return dict(role_map)
    out = dict(role_map)
    for col, strat in overrides.items():
        if col not in role_map:
            raise ValueError(f"override for unknown column {col!r} (not in the plan: {sorted(role_map)})")
        if strat not in COLUMN_STRATEGIES:
            raise ValueError(f"strategy {strat!r} for {col!r} not in {COLUMN_STRATEGIES}")
        out[col] = strat
    return out


def roles_to_lists(role_map: dict) -> dict:
    """Invert a column->strategy map back to strategy->[columns] (the DeidPlan shape)."""
    lists = {role: [] for role in _STRATEGY_TO_ROLE.values()}
    for col, strat in role_map.items():
        lists[_STRATEGY_TO_ROLE[strat]].append(col)
    return {k: sorted(v) for k, v in lists.items()}


# --- Utility priority (pure) --------------------------------------------------

def utility_weights(qi_labels: list, priority: list | None, low: float = 1.0) -> dict:
    """Map each quasi-identifier label to a utility WEIGHT from the analyst's priority order
    (most-valuable-first). Higher weight = preserved (coarsened last) by the engine.

    Ranked labels get strictly-descending weights, ALL strictly above `low`; unlisted labels
    get `low` (coarsened first). Only the relative order matters to the engine. None -> {}
    (engine keeps its built-in per-QI defaults)."""
    if not priority:
        return {}
    n = len(priority)
    weights = {label: float(low + (n - i)) for i, label in enumerate(priority)}  # n+low .. 1+low
    for label in qi_labels:
        weights.setdefault(label, low)
    return weights


# --- Decision sheet -----------------------------------------------------------

@dataclass
class Decision:
    key: str
    title: str
    options: list = field(default_factory=list)
    required: bool = False
    note: str = ""


def deid_decisions(role_map: dict) -> list:
    """The decisions to surface, given the plan's current per-column routing."""
    has_dates = any(s == "date_year" for s in role_map.values())
    has_qis = any(s == "generalize" for s in role_map.values())
    decisions = [Decision(
        key="per_column_strategy",
        title="Override the per-column strategy? (also the quasi-identifier control)",
        options=[{"label": f"`{c}` is currently **{s}**", "value": {c: s}}
                 for c, s in sorted(role_map.items())],
        note=f"Force any column to one of {COLUMN_STRATEGIES}. 'generalize' = treat as a "
             f"quasi-identifier; 'keep' = leave it out of the k-search.")]
    if has_dates:
        decisions.append(Decision(
            key="date_handling",
            title="How should dates be handled?",
            options=[{"label": "Reduce to year (Safe Harbor default)", "value": "year"},
                     {"label": "Interval-preserving derived fields (keep gaps, drop absolute dates)",
                      "value": "interval"},
                     {"label": "Consistent per-patient shift (preserve intervals, hide real dates)",
                      "value": "shift"}]))
    if has_qis:
        decisions.append(Decision(
            key="utility_priority",
            title="Which quasi-identifiers should be PRESERVED (coarsened last)?",
            options=[{"label": "Rank them most-valuable-first (e.g. ['age','length_of_stay','geo'])",
                      "value": "<ordered list of QI labels>"}],
            note="Feeds the engine's utility weighting; unranked QIs are coarsened first."))
    decisions.append(Decision(
        key="output_delivery",
        title="How should the result be delivered?",
        options=[{"label": "Governed Unity Catalog view over raw (default)", "value": "uc_view"},
                 {"label": "A generated, re-runnable notebook", "value": "notebook"},
                 {"label": "Shown in this conversation only (plan + k frontier; nothing persisted)",
                  "value": "conversation"}],
        note=f"Defaults to '{DEFAULT_DELIVERY}'."))
    return decisions


def surfaced_keys(role_map: dict) -> set:
    """The complete set of decision keys surfaced for this table (for interaction_fidelity)."""
    keys = {"per_column_strategy", "output_delivery"}
    if any(s == "date_year" for s in role_map.values()):
        keys.add("date_handling")
    if any(s == "generalize" for s in role_map.values()):
        keys.add("utility_priority")
    return keys


def format_decisions(decisions: list) -> str:
    if not decisions:
        return ""
    lines = ["", "**⚙️ Choices you can override (surfaced — the k dial is not the only lever):**"]
    for d in decisions:
        req = " *(required)*" if d.required else ""
        lines.append(f"- **{d.title}**{req}  → `{d.key}`")
        if d.key == "per_column_strategy":
            for opt in d.options:
                lines.append(f"    - {opt['label']}")
        else:
            for opt in d.options:
                lines.append(f"    - {opt['label']}  → `{opt['value']!r}`")
        if d.note:
            lines.append(f"    - _{d.note}_")
    return "\n".join(lines)


# --- Notebook artifact (output_delivery="notebook") ---------------------------

def deid_notebook_source(raw_fqn: str, k_target: int, view_name: str | None,
                         column_overrides: dict | None = None,
                         date_handling: str | None = None,
                         utility_priority: list | None = None) -> str:
    """Generate a Databricks notebook (source string) reproducing the de-id via the vetted
    entrypoint (execution model — it CALLS apply_deid, no hand-written de-id SQL). Pure."""
    return f'''# Databricks notebook source
# MAGIC %md
# MAGIC # De-identification (reproducible) — {raw_fqn}
# MAGIC Regenerated via the vetted entrypoint with the analyst's surfaced choices pinned below.

# COMMAND ----------
import sys
sys.path.append("<path-to>/skills/hls-phi-deidentifier/scripts")  # adjust to your workspace
from run_deid import apply_deid

# COMMAND ----------
print(apply_deid(
    {raw_fqn!r},
    k_target={k_target!r},
    view_name={view_name!r},
    column_overrides={column_overrides!r},
    date_handling={date_handling!r},
    utility_priority={utility_priority!r},
    output_delivery="uc_view",
))
'''
