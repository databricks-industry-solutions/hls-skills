# Error Analysis Worksheet

Referenced from SKILL.md Step 7. Method: Hamel Husain's open coding → axial coding. The failure taxonomy is the deliverable — win-rates only point at where to look.

## Open Coding (per trace)

Read every task that ended `tie-fail` or `regression` in either arm. For each, fill one row. Annotate the **first** observed failure — downstream errors cascade from it and are noise.

| task_id | arm | first failure observed (free text) | where in session (early/mid/late) | severity (blocks task / degrades) |
|---------|-----|------------------------------------|-----------------------------------|-----------------------------------|
| | | | | |

Rules:

- One "benevolent dictator" (domain expert) writes the notes. Do not outsource annotation — the notes feed the fix loop.
- Free text, concrete: "resolved BRCA1 to wrong Ensembl ID" not "bad gene handling".
- ≥ 5-10 traces before grouping (across both arms is fine at this scale).

## Axial Coding (grouping)

Group the free-text notes into named failure modes. Count occurrences. This is the taxonomy.

| failure mode | definition | count | example task_ids | arm(s) affected |
|--------------|-----------|-------|------------------|-----------------|
| | | | | |

## HLS Seed Taxonomy

Start grouping against these; add modes as observed:

| failure mode | signature |
|--------------|-----------|
| wrong-identifier-resolution | gene/protein/cohort ID mapped to wrong entity (BRCA1 → wrong Ensembl) |
| fabricated-reference | cited paper, database ID, or URL does not exist |
| fabricated-numbers | numeric results not traceable to actual output |
| skipped-analysis-step | required step (e.g. normalization, QC) silently omitted |
| wrong-database-or-version | right query, wrong source or stale version |
| phi-leakage | patient-identifying values surfaced in output |
| scale-blindness | approach works on toy data, infeasible at real data size |
| premature-stop | session ended with task partially done, presented as complete |
| context-loss | later steps contradict earlier results in same session |

## Feeding Back

1. Taxonomy rows where `arm = with_skill` → fix targets for the skill (description, workflow steps, guardrails).
2. Rows where the skill **eliminated** a baseline failure mode → the evidence section of the report.
3. Persistent modes you will iterate on → promote to a dedicated deterministic scorer or judge in `scorer-pack.md` terms. Modes seen once → fix directly, no eval infrastructure.

## Cadence

- Per skill change: re-read losses only (Recipe: Regression Re-Run).
- Per release: full worksheet across all skills in the release.
