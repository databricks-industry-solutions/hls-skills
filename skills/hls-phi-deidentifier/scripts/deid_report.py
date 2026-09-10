"""Data-scientist-facing de-identification readout.

Answers the three questions a DS actually has after saying "de-id this before I
analyze it":
  1. What did you hide? (so I know it's safe to share)
  2. Is it ACTUALLY safe, or just name-stripped? (k-anonymity -- the thing I can't eyeball)
  3. What can I still analyze in this table? (which columns kept fidelity, which lost it)

This is NOT a compliance-signature artifact -- it is a trust-and-usability readout
for the analyst. It still ends with the Safe Harbor caveat, because the analyst
should know a human must certify before external release.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_uc_governance import DIRECT_IDENTIFIERS, ANALYTIC_PASS_THROUGH, GovernanceResult  # noqa: E402

SAFE_HARBOR_CAVEAT = (
    "This table was processed against HIPAA Safe Harbor by an automated skill. "
    "It is safe for internal analysis and lower-trust sharing, but a Privacy Officer "
    "must certify it before external release. Re-identification risk is bounded by "
    "the k-anonymity level below, not eliminated."
)


def _fidelity(level: int, max_level: int) -> str:
    if level == 0:
        return "full"
    if level >= max_level:
        return "dropped"
    return "generalized"


def build_readout(gov: GovernanceResult, k_actual: int | None = None,
                  rows_kept: int | None = None, rows_total: int | None = None,
                  removed_columns=None, tokenized_columns=None,
                  suppressed_columns=None, passthrough_columns=None) -> str:
    """Return a markdown readout for the analyst from the governance result.

    Column lists come from the ACTUAL run (schema-driven), not hardcoded demo names.
    Falls back to the demo direct-identifier list only if nothing is supplied.
    """
    # Prefer the independently-MEASURED k. Only fall back to the engine's self-reported
    # k_achieved when the caller passed nothing at all (k_actual omitted). A caller that
    # explicitly measured "unmeasurable" passes k_actual=None AND signals it via
    # k_measured=False in the verdict; here we detect the no-QI case the same way the
    # measurer does — gov.generalization empty — and render it as UNMEASURED, never a number.
    k_unmeasured = (k_actual is None and not gov.generalization)
    k = None if k_unmeasured else (k_actual if k_actual is not None else gov.k_achieved)

    removed = ", ".join(removed_columns) if removed_columns is not None else ", ".join(DIRECT_IDENTIFIERS)

    generalized_lines, dropped = [], []
    analyzable = list(passthrough_columns) if passthrough_columns is not None else list(ANALYTIC_PASS_THROUGH)
    for item in gov.generalization:
        fid = _fidelity(item["level"], item["of"])
        label = item["quasi_identifier"]
        if fid == "full":
            analyzable.append(label)
        elif fid == "generalized":
            generalized_lines.append(f"  - {label}: coarsened (level {item['level']}/{item['of']}) — "
                                     f"usable at reduced granularity")
            analyzable.append(f"{label} (coarse)")
        else:  # dropped
            dropped.append(label)

    if k is None:
        safety_line = (f"**Re-identification safety:** k-anonymity **NOT MEASURED** — no "
                       f"quasi-identifier columns were generalized (target {gov.k_target}). "
                       f"Re-identification resistance is UNVERIFIED; Privacy Officer review required.")
        meaning_line = ("  Meaning: nothing was generalized to measure k over, so this readout "
                        "makes NO claim about re-identifiability of the surviving columns.")
    else:
        safe_verdict = ("SAFE to share internally" if k >= gov.k_target
                        else f"NOT yet at target (k={k} < {gov.k_target}) — do not share")
        safety_line = (f"**Re-identification safety:** k-anonymity = **{k}** (target "
                       f"{gov.k_target}). {safe_verdict}.")
        meaning_line = (f"  Meaning: every combination of the surviving quasi-identifiers is "
                        f"shared by at least {k} patients, so no row points to one person.")

    parts = [
        "## De-identification readout",
        "",
        f"**Output:** `{gov.view_fqn}` (a view over the raw table — no second copy of PHI was created)",
        "",
        safety_line,
        meaning_line,
    ]
    if rows_kept is not None and rows_total is not None:
        supp = rows_total - rows_kept
        parts.append(f"  Rows: {rows_kept}/{rows_total} kept" +
                     (f", {supp} suppressed to reach k." if supp else ", none suppressed."))
    parts += ["", f"**Removed entirely (direct identifiers):** {removed}."]
    if tokenized_columns:
        parts.append(f"**Tokenized (pseudonymized for linkage):** {', '.join(tokenized_columns)}.")
    if suppressed_columns:
        parts.append(f"**Suppressed (unknown/unsafe columns, denied by default — NOT leaked):** "
                     f"{', '.join(suppressed_columns)}.")
    parts.append("")
    if generalized_lines:
        parts.append("**Generalized for privacy (you traded detail for safety):**")
        parts += generalized_lines
        parts.append("")
    if dropped:
        parts.append(f"**Dropped for privacy — do NOT build analysis needing these:** {', '.join(dropped)}.")
        parts.append("")
    parts += [
        f"**You CAN still analyze:** {', '.join(analyzable)}.",
        "",
        f"**Salt source:** {gov.salt_source}",
        "",
        "---",
        f"*{SAFE_HARBOR_CAVEAT}*",
    ]
    return "\n".join(parts)
