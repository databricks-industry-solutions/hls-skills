# Phenotype Standards & Feasibility Heuristics

## Reproducible-phenotype conventions
- **PheKB** (phekb.org) — library of validated electronic phenotype algorithms;
  a natural literature-review target and a comparison baseline for user criteria.
- **eMERGE Network** — validated phenotype algorithms with reported PPV.
- **OHDSI / ATLAS** — concept-set + cohort-definition standard on OMOP; the most
  portable format. Emit definitions in a shape that maps to OHDSI cohort JSON where
  possible.

## Cohort quality principles
- A phenotype is defined by **concept sets + temporal/logical rules**, not a
  patient-id list. Always persist the definition.
- Report an estimate of **PPV / sensitivity** against a reference definition when
  one exists (e.g. a PheKB algorithm for the same condition).
- Prefer definitions that already have **published validation** — cite the PMID.

## Feasibility thresholds (defaults, tune per study)
| N eligible | Signal | Action |
|------------|--------|--------|
| ≥ 100 | usable for most retrospective analyses | proceed |
| 20–99 | underpowered for many endpoints | warn; report per-criterion attrition |
| < 20 | generally not analyzable | hard-warn; recommend relaxing criteria |

Minimum viable N is study-dependent (a rare-disease RWE study may accept far fewer;
a trial-screening feasibility check may need thousands). Use the study intent the
user gave to set thresholds, and always show the attrition waterfall so the user
sees which single criterion is driving N down.
