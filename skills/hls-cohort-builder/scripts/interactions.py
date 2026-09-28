"""Surface-and-choose interaction layer for the cohort builder (Phase 1, Enhancement A).

PURE-PYTHON (no Databricks SDK): this module owns the read-only DECISION SHEET the skill
presents to the analyst, so the interaction logic is unit-testable offline while cohort_run.py
keeps the SQL execution. It assembles the choices the skill must SURFACE (never silently
decide) beyond the existing threshold + combine-mode gates:

  - source_confidence : the minimum model confidence to accept an LLM-ascertained (note /
                        document) diagnosis  -- recall vs precision.
  - source_priority   : when a coded dx and a note/document dx DISAGREE, which source wins.
  - output_delivery   : how to deliver the result -- a materialized Unity Catalog object, a
                        generated re-runnable notebook, or shown in the conversation only.

It also records WHICH decisions were surfaced (feeds the interaction_fidelity scorer) and
generates the notebook artifact for the "notebook" delivery mode. Nothing here touches a
warehouse; cohort_run.py calls these and executes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


# --- Output delivery ----------------------------------------------------------

DELIVERY_MODES = ("uc_table", "notebook", "conversation")
DEFAULT_DELIVERY = "uc_table"

# When a coded dx and a note/document-asserted dx conflict, which source is authoritative.
SOURCE_PRIORITIES = ("code", "note")


def normalize_delivery(value: str | None) -> str:
    """Validate + default the output-delivery choice. None -> the governed UC table (the
    historical default, so existing callers are unchanged)."""
    v = value or DEFAULT_DELIVERY
    if v not in DELIVERY_MODES:
        raise ValueError(f"output_delivery must be one of {DELIVERY_MODES}, got {value!r}")
    return v


# --- Decision-sheet model -----------------------------------------------------

@dataclass
class Decision:
    """One choice the skill surfaces for the user. `required` gates the build; the softer
    decisions (confidence/priority/delivery) have sensible defaults and do NOT block, but are
    still SURFACED so the analyst can override -- and recorded for interaction_fidelity."""
    key: str
    title: str
    options: list = field(default_factory=list)     # [{label, value}]
    required: bool = False
    note: str = ""


def output_delivery_decision() -> Decision:
    return Decision(
        key="output_delivery",
        title="How should the result be delivered?",
        options=[
            {"label": "Materialized Unity Catalog object (governed table/view, shareable)",
             "value": "uc_table"},
            {"label": "A generated, re-runnable notebook (portable, reproducible)",
             "value": "notebook"},
            {"label": "Shown in this conversation only (nothing persisted; fastest)",
             "value": "conversation"},
        ],
        required=False,
        note=f"Defaults to '{DEFAULT_DELIVERY}' if you don't choose.",
    )


def source_confidence_decision() -> Decision:
    return Decision(
        key="source_confidence",
        title="Minimum confidence to accept a note/document-ascertained diagnosis?",
        options=[
            {"label": "Higher recall — accept any span-grounded assertion", "value": 0.0},
            {"label": "Balanced", "value": 0.5},
            {"label": "Higher precision — only high-confidence assertions", "value": 0.8},
        ],
        required=False,
        note="Applies only to LLM-ascertained (note/document) evidence; coded dx is exact.",
    )


def source_priority_decision() -> Decision:
    return Decision(
        key="source_priority",
        title="When a coded diagnosis and a note/document diagnosis DISAGREE, which wins?",
        options=[
            {"label": "Coded diagnosis is authoritative", "value": "code"},
            {"label": "Note/document evidence is authoritative", "value": "note"},
        ],
        required=False,
        note="Only affects conflicting patients; concordant ones are unaffected.",
    )


def cohort_decisions(has_notes: bool) -> list:
    """The NEW (Phase-1) decisions to surface, on top of the existing threshold + combine
    gates that preview_cohort already surfaces. Confidence/priority appear only when an
    LLM-ascertained (notes/document) source is in play; delivery is always offered."""
    decisions = []
    if has_notes:
        decisions.append(source_confidence_decision())
        decisions.append(source_priority_decision())
    decisions.append(output_delivery_decision())
    return decisions


def format_decisions(decisions: list) -> str:
    """Readout block for the NEW decisions, appended to the existing preview."""
    if not decisions:
        return ""
    lines = ["", "**⚙️ Additional choices (surfaced — pick or accept the default):**"]
    for d in decisions:
        req = " *(required)*" if d.required else ""
        lines.append(f"- **{d.title}**{req}")
        for opt in d.options:
            lines.append(f"    - {opt['label']}  → `{d.key}={opt['value']!r}`")
        if d.note:
            lines.append(f"    - _{d.note}_")
    return "\n".join(lines)


def surfaced_keys(has_notes: bool, has_ambiguity: bool) -> set:
    """The COMPLETE set of decision keys the skill surfaced for this task -- the existing
    threshold (if an ambiguous term) + combine (if notes) gates PLUS the Phase-1 additions.
    This is what the interaction_fidelity scorer measures against the gold should-surface set.
    """
    keys = {"output_delivery"}
    if has_ambiguity:
        keys.add("threshold")
    if has_notes:
        keys.update({"combine_mode", "source_confidence", "source_priority"})
    return keys


# --- Notebook artifact (for output_delivery="notebook") -----------------------

def cohort_notebook_source(table: str, definition_json: str, cohort_table: str | None,
                           intent_text: str = "") -> str:
    """Generate a Databricks notebook (source string) that reproduces the confirmed cohort by
    calling the vetted entrypoint with the pinned definition -- portable + re-runnable, and
    honoring the execution model (the notebook CALLS build_confirmed_cohort, it does not
    hand-write cohort SQL). Pure string generation, so it is unit-testable offline.
    """
    d = json.loads(definition_json)
    codes = d.get("condition_codes", [])
    return f'''# Databricks notebook source
# MAGIC %md
# MAGIC # Cohort (reproducible) — {intent_text or "generated by hls-cohort-builder"}
# MAGIC Regenerated from a pinned phenotype definition. Uses the vetted entrypoint
# MAGIC (execution model — no hand-written cohort SQL). Definition is pinned below.

# COMMAND ----------
import sys
sys.path.append("<path-to>/skills/hls-cohort-builder/scripts")  # adjust to your workspace
from cohort_run import build_confirmed_cohort

TABLE = {table!r}
CONDITION_CODES = {codes!r}
NOTES_TABLE = {d.get("note_evidence_table")!r}  # None if this was a coded-only cohort

# COMMAND ----------
# Pinned phenotype definition (reproducible):
DEFINITION = {definition_json!r}
print(DEFINITION)

# COMMAND ----------
print(build_confirmed_cohort(
    TABLE,
    intent_text={intent_text!r},
    condition_codes=CONDITION_CODES,
    threshold_value={d.get("obs_value")!r},
    threshold_op={d.get("obs_op")!r},
    combine_mode={d.get("combine_mode")!r},
    cohort_table={cohort_table!r},
    output_delivery="uc_table",
))
'''
