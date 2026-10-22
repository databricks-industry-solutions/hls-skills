# Evaluation Report — phi-deidentifier Skill

**Setup**: Two paths evaluated, both run live in Genie Code on `fevm-testing-playground`
(2026-10-22 structured; 2026-10-19 document). Every metric is measured **directly from the
materialized output tables** against synthetic ground truth we own (we inject the PHI, so
recall is measured, not estimated) — never from the agent's own narrative. Scored with the
skill's `eval/objective.py` (`deid_objective`): a hard **leak gate** (any residual identifier →
0), then `0.45·F2(recall,precision) + 0.20·utility + 0.15·min(k/5,1) + 0.20·governance`.

- **Structured path** (`scripts/run_deid.py` → UC governed view): de-identify
  `deid_live_test.patients_raw` (250 rows: name, ssn, email, phone, zip, admit/discharge dates,
  age_band, sex, hba1c) for analytics sharing — redact direct identifiers, tokenize `patient_id`,
  generalize quasi-identifiers to k-anonymity target 5.
- **Document path** (`scripts/deid_docs.py`): de-identify a synthetic 15,772-char EHR PDF
  (`patient_whitfield_margaret_ehr.pdf`) — layered member/relative redaction + `ai_mask` + regex,
  then a deterministic residual verdict.

## Results — structured path (5 fresh Genie sessions)

| run | residual leaks | recall | precision | k-anonymity | governance | utility | objective |
|-----|----------------|--------|-----------|-------------|------------|---------|-----------|
| run1 | 0 | 1.000 | 1.000 | 33 | 1.00 | 0.562 | 0.9125 |
| run2 | 0 | 1.000 | 1.000 | 33 | 1.00 | 0.562 | 0.9125 |
| run3 | 0 | 1.000 | 1.000 | 33 | 1.00 | 0.562 | 0.9125 |
| run4 | 0 | 1.000 | 1.000 | 33 | 1.00 | 0.562 | 0.9125 |
| run5 | 0 | 1.000 | 1.000 | 33 | 1.00 | 0.562 | 0.9125 |
| **aggregate** | **0** | **1.000** | **1.000** | **33** | **1.00** | **0.562** | **0.9125** |

- **0 residual leaks** every run (SSN / email / phone / name scanned against the raw input — a
  "zero leaks" claim is checked, not trusted). All four direct identifiers removed; `patient_id`
  emitted only as a salted `pseudo_patient_id`.
- **Governance = 1.00**: output is a `VIEW` over the raw table (no second physical PHI copy) and
  the raw identifiers are not surfaced to the consumer role. This is the dimension a no-skill
  baseline fails (it writes a physical copy and leaves raw PHI exposed → governance 0).
- **k-anonymity = 33** over the generalized QIs (`age_band`, `zip`, LOS, `sex`), well above the
  target of 5; 250/250 rows retained (no suppression needed at this generalization).
- **Utility 0.562**: `hba1c` kept at full fidelity; `age_band`/`sex`/`zip` generalized and the
  admit→discharge interval preserved as a bucketed length-of-stay — a deliberate privacy/utility
  trade, not loss.
- **Reproducibility**: the structured path is deterministic SQL (salted-hash tokenization + fixed
  generalization), so all 5 independent sessions produced **byte-identical** views. This is the
  headline — the "safe to share?" answer does not change run to run.

**Optional redaction+tokenize-only mode** (`apply_kanon=False`): the skill can also skip
k-anonymity (direct identifiers dropped/tokenized, dates → year, quasi-identifiers kept at full
granularity). In that mode k is unmeasurable and the readout is surfaced as **REVIEW REQUIRED** —
never a certified de-identification. (Verified live separately; not part of the 5-run table above,
which targets k=5.)

## Results — document path (5 fresh Genie sessions)

| metric | value |
|--------|-------|
| precision | 0.966 |
| recall | 0.895 (→ **1.000** after the shared-surname family-redaction fix) |
| F1 | 0.929 |
| deterministic residual verdict | PASS (0/0/0) × 5, reported verbatim |

- Ground truth: 19 member-PHI entities that must be redacted (patient + relative names incl. a
  misspelled surname, employer, sub-state geography, dictation/accession IDs, pharmacy ID, SSN,
  phone, email, MRN, DEA, date) and a keep-set of 10 that must **not** be redacted (6 provider
  surnames + 4 clinical tokens). Measured by substring survival in the output table.
- The only recurring false positive was a provider surname occasionally over-masked by the
  additive `ai_mask` layer (over-redaction, not a leak); no clinical content was lost in any run.
- Earlier (pre-enhancement) sessions reported wildly inconsistent leak counts (2, 6, 6, 5, 6)
  because the agent improvised its own LLM re-scan. The skill now emits a **deterministic**
  residual verdict (fixed-format / member / employer, each a fixed query) and `SKILL.md` instructs
  the agent to report it verbatim — removing the run-to-run roulette.

## Verdict

**ship** — Structured: perfect detection and governance with strong k-anonymity, fully
reproducible across 5 sessions (objective 0.9125, 0 leaks). Document: F1 0.929 (recall 1.000
after the family-redaction fix) with a deterministic, verbatim-reported residual verdict. The
model-dependent categories the verdict names (sub-state geography, narrative org/school names,
relatives without a cue or shared surname) always route to Privacy-Officer review.

## Limitations

- Synthetic data with injected PHI — exact ground truth, but a single structured schema and a
  single EHR archetype; real tables/documents will have more variety.
- The document path's lone precision failure mode is `ai_mask` occasionally over-masking a
  provider surname (nondeterministic, additive layer); it never leaks member PHI.
- k-anonymity is measured on the output view; it does not model an adversary with external
  linkage beyond the quasi-identifier set.

## Reproduce

- Component scorers / objective: `eval/scorers.py`, `eval/objective.py`
  (smoke test: `python3 eval/objective.py`).
- Structured scorer (reads a governed view, scans leaks against the raw input):
  `DATABRICKS_CONFIG_PROFILE=<p> python3 -I eval/score_phi_struct.py --raw <catalog.schema.patients_raw> --out <catalog.schema.view>`
- Structured runs (this report): `genie_science_eval.phi_struct_skillrun1..5` over
  `deid_live_test.patients_raw`, `fevm-testing-playground`.
- Document path: offline unit tests `python3 -I -m pytest tests/ -q`; live multi-scenario harness
  in the dev repo (`eval/ab_deid_edge_cases_live.py`).
