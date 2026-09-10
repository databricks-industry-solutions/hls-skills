# Clinical Ontology Crosswalks & Concept-Set Guidance

| Domain | Primary vocabulary | Notes |
|--------|-------------------|-------|
| Conditions / diagnoses | **ICD-10-CM**, **SNOMED CT** | ICD-10-CM for billing/EHR problem lists; SNOMED for clinical granularity. Expand via the hierarchy — a parent code implies its descendants. |
| Labs / observations | **LOINC** | Pair the LOINC code with a numeric comparator + unit (e.g. HbA1c 4548-4 > 8.0 %). |
| Medications | **RxNorm** | Resolve to ingredient level, then expand to clinical drugs/products. Consider drug classes (ATC) for "on any statin". |
| Procedures | **CPT-4 / HCPCS**, **ICD-10-PCS** | CPT/HCPCS for outpatient/professional; ICD-10-PCS for inpatient. |

## OMOP / OHDSI (preferred backbone)

If the source is OMOP CDM, use `concept`, `concept_ancestor`, and `concept_relationship`
to build **concept sets** with descendant expansion — this is the OHDSI-standard,
reproducible way to define a phenotype, and it matches ATLAS/PheKB conventions.
`dbignite` (Databricks' FHIR→OMOP accelerator) can produce this layout from FHIR.

## Hierarchy expansion is not optional

String matching ("diabetes" LIKE) is not a cohort definition — it misses coded
records and catches irrelevant text. Always resolve to standard concepts and
include descendants. Model-generated code lists must be **validated against a
vocabulary table** before use; never trust ungrounded codes.

Confidence: high on the vocabulary→domain mapping; the exact concept-set contents
are customer-data-dependent and must be validated per engagement.
