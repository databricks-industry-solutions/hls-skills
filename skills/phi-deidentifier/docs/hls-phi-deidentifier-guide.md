# HLS PHI/PII De-Identifier — Skill Guide

*A Genie Science skill for Databricks Genie Code. Operationalizes HIPAA Safe Harbor
de-identification over structured Unity Catalog tables, with enforced k-anonymity and
governance-first output.*

---

## 1. What this skill is, in one paragraph

A data scientist tells Genie *"de-identify this table before I analyze/share it."* The skill
strips the 18 Safe Harbor direct identifiers, **enforces k-anonymity** on the quasi-identifiers
that remain (age, ZIP, sex, length-of-stay, and any others detected), applies the result as a
**dynamic view over the raw table** (so no second copy of PHI is ever created), verifies there
is no residual leak, and returns a plain-language readout of what was removed, generalized,
suppressed, and what is still analyzable. It runs on the **execution model**: Genie calls one
vetted entrypoint and reports its output — it does not hand-write de-identification SQL.

**Why the skill exists (the measured problem):** un-guided Genie de-identifies data that
*looks* clean but leaves ~87% of rows uniquely re-identifiable (k=1), never checks k-anonymity,
and writes a physical copy that leaves the raw PHI fully exposed — all while reporting success.
The skill turns a *plausible* answer into a *defensible* one. Measured objective score:
**0.68 baseline → 0.90 skill.**

---

## 2. How it runs — the execution model

The single entrypoint is `scripts/run_deid.py::run_deid(table)`. Genie is instructed (in
SKILL.md and via a workspace memory instruction) to call it and report its output, never to
reimplement the logic. This matters because de-identification is a compliance task where a
subtle reimplementation error (e.g. forgetting that length-of-stay is a quasi-identifier)
produces a *confident, invisible* failure. The vetted code cannot make that mistake.

```
run_deid("catalog.schema.table")
   → profile every column
   → auto-detect PHI (18 Safe Harbor classes)
   → enforce k-anonymity via utility-weighted generalization
   → build a dynamic VIEW over the raw table (no PHI copy)
   → residual leak scan on the output (defense-in-depth)
   → analyst readout + persisted UC audit record
```

---

## 3. The files, and what each does

### `SKILL.md` — the instruction Genie loads
Frontmatter (`name`, `description`) is the discovery trigger. The body leads with a hard
**"⛔ EXECUTE, DO NOT REIMPLEMENT"** mandate (call `run_deid`, never write your own SQL),
followed by the internal procedure documented *for transparency only*. Also carries the
non-negotiables: this **operationalizes** Safe Harbor but does not **certify** it (the
Privacy Officer does); structured data only; never claim output is "HIPAA compliant."

### `scripts/` — the live code path
| File | Role |
|------|------|
| `run_deid.py` | **The entrypoint.** Orchestrates the whole pipeline; the only thing Genie calls. Derives per-column roles (drop / tokenize / date-year / quasi-identifier / passthrough) from detection, builds the view, runs the residual leak scan, emits the readout, persists the audit record. |
| `detect_phi.py` | Classifies every column into a Safe Harbor class using, in trust order: Unity Catalog PII tags → column-name heuristics → deterministic value validators (SSN/email/phone/IP/ZIP regex + Luhn) → date-shape. Recall-biased: when unsure, flag as PHI. |
| `profile_table.py` | Per-column profile (type, null rate, distinct count, sample values) that seeds detection. |
| `kanon.py` | **The k-anonymity engine.** Generalizes quasi-identifiers along hierarchies with a *utility-weighted greedy search* (sacrifices low-value QIs like geography before high-value clinical ones like age). Includes generic, data-driven ladders (numeric → quartile buckets; categorical → keep/merge-rare/suppress) so it works on **any** table, not just the demo schema. |
| `apply_uc_governance.py` | Builds the schema-driven dynamic view over the raw table (drops direct identifiers, tokenizes IDs, year-reduces dates, applies generalization, filters sub-k rows). Contains the SQL runner `Q` (ambient auth in-workspace, optional profile locally). |
| `deid_report.py` | Renders the analyst-facing readout from the actual run — removed / tokenized / generalized / suppressed / still-analyzable — plus the mandatory Safe Harbor disclaimer. |

### `eval/` — measurement
| File | Role |
|------|------|
| `scorers.py` | Component scorers over a `DeidGold` (ground truth) + `DeidOutput` (what a run produced): `detection_recall`, `residual_leaks`, `utility_retention` (graded), `governance_score`, `f_beta`. Also `mlflow_scorers()` wrapping them as `@scorer` callables. |
| `objective.py` | The single 0–1 score. **Gated + recall-weighted + governance-aware:** any residual leak → 0; else `0.45·F2 + 0.20·utility + 0.15·k_term + 0.20·governance`. Runnable offline; smoke test shows perfect governed = 1.0, ungoverned copy = 0.8, leak = 0.0. |

### `references/` — knowledge the skill relies on
| File | Role |
|------|------|
| `safe_harbor_classes.md` | The 18 Safe Harbor identifier classes mapped to a detected-class + default treatment. |
| `deid_strategies.md` | Redact / tokenize / date-shift / generalize — definitions and when to use each. |
| `restricted_zip3.md` | The ~17 three-digit ZIP prefixes that must be zeroed (with a freshness caveat — re-derive from current Census per engagement). |

---

## 4. The two design guarantees that matter

**Guarantee 1 — k-anonymity is measured over ALL surviving quasi-identifiers, including
derived ones.** The verifier computes actual k on the output view and fails loudly if below
target. This is the exact gap that un-guided Genie misses (it checked only the obvious
demographics, forgetting length-of-stay, and reported a false k=5 over truly-k=1 data).

**Guarantee 2 — passthrough is DENY-by-default.** A column is exposed only if affirmatively
safe (numeric measure). Any unknown non-numeric column is suppressed, never passed through —
plus a residual leak scan re-checks the output for PHI patterns and near-unique free-text.
This was added after live testing on a novel table caught a real leak: a `full_name` column
the name-heuristic didn't recognize was being passed through unredacted.

---

## 4b. Baseline vs. Skill — Scorecard

Measured objective score: **0.68 (baseline, no skill) → 0.90 (skill)**. The gate (any
residual PHI leak → 0) did not fire in either run; the gap comes entirely from the two
dimensions the baseline failed. Component breakdown (each 0–1, then weighted):

| Component | Weight | Baseline (Genie, no skill) | Skill | What drove the difference |
|-----------|--------|----------------------------|-------|---------------------------|
| F2 (recall-weighted detection) | 0.45 | 1.00 | 1.00 | Both strip the obvious direct identifiers — this is table stakes |
| Utility retention | 0.20 | 1.00 | 0.50 | Skill *traded* utility for privacy: age generalized, length-of-stay dropped to reach k. Baseline kept everything raw (no trade) |
| k-anonymity term (k/5, capped) | 0.15 | 0.20 (k=1) | 1.00 (k=6) | Baseline left ~87% of rows uniquely re-identifiable and never checked; skill enforced k≥5 |
| Governance | 0.20 | 0.00 | 1.00 | Baseline wrote a physical copy and left raw PHI exposed; skill used a view over raw, source not exposed |
| **Weighted total** | | **0.68** | **0.90** | |

**Why the skill is 0.90, not 1.0:** it deliberately sacrificed some analytic fidelity
(utility 0.50) to achieve k-anonymity on a small 200-row table. That is the *correct*
privacy/utility trade, and the objective shows it honestly rather than hiding it — a
larger real dataset would generalize less to reach the same k, scoring higher on utility.

**What the tests contributed to these numbers:**
- **k-anonymity (0.20 vs 1.00)** — measured directly on the produced views with
  `SELECT MIN(count) FROM (... GROUP BY quasi_identifiers)`: baseline k=1, skill k=6.
- **Governance (0.00 vs 1.00)** — baseline created a second physical table with raw SSNs
  still readable; skill created a view over raw with the source restricted.
- **The leak gate** — a live run on a *novel* table initially leaked a `full_name` column
  detection didn't recognize. Under the objective that is an automatic **0** (residual
  leak > 0), which is exactly what surfaced the bug and forced the deny-by-default fix.

*Full run log: `results/baseline_findings.md` in the source repo.*

---

## 5. What it produces

- A **dynamic view** (`<table>_deid`) over the raw table — no second PHI copy.
- A **readout**: removed / tokenized / generalized / suppressed / still-analyzable, plus
  verified k and the Safe Harbor disclaimer.
- An **audit record** in `deid_audit_log` — the authoritative artifact a Privacy Officer
  reviews (not Genie's chat prose).

---

## 6. Honest limits

- **Certification is not automated.** The skill operationalizes Safe Harbor; a Privacy
  Officer (or a statistician, for Expert Determination) still certifies.
- **Detection is recall-limited.** Deny-by-default + the leak scan are the backstops, but a
  novel identifier type detection misses relies on those safety nets rather than being named.
- **Generic generalization is cruder than the hand-tuned demo ladders**, and depends on a
  column being detected as a quasi-identifier in the first place.
- **The salt is a demo literal** — production must use a Databricks secret scope (flagged in
  every readout).
- **Structured data only** — free-text notes, PDFs, images are out of scope.
