# Output tables

Produced by `parse_837()` and `transaction_checks()` in `scripts/x12_837.py`. `claim_id` is
`sha2(source_file || '|' || claim position)`, stable when the same file is reprocessed, by batch
or Auto Loader (a leading `dbfs:` on the path is stripped first).

## claims (one row per CLM)

| Column | Source | Notes |
|---|---|---|
| claim_id | derived | join key to lines and diagnoses |
| claim_type | GS08 | professional / institutional / dental / unknown (5010 X222/X223/X224, 4010A1 X098/X096/X097) |
| x12_version | GS08 | `5010` or `4010` |
| patient_control_number | CLM01 | provider's claim number |
| claim_frequency_code | CLM05-3 | 1 original, 7 replacement, 8 void |
| place_of_service_code | CLM05-1 | 837P only |
| type_of_bill | CLM05-1 + CLM05-3 | 837I only, e.g. `111`, `131` |
| total_charge_amount | CLM02 | DECIMAL(18,2) |
| line_count, line_charge_total | lines | reconciliation against total_charge_amount |
| service_from_date, service_to_date | DTP*434 else min/max DTP*472 | |
| statement_from_date, statement_to_date, admission_date | DTP*434, DTP*435 | 837I |
| admission_type_code, admission_source_code, patient_status_code | CL1 | 837I |
| member_id, subscriber_* | 2010BA NM1*IL, DMG, N4 | |
| group_number, claim_filing_indicator, payer_responsibility_code, subscriber_relationship_code | SBR (2000B) | filing indicator: MC Medicaid, MA/MB Medicare A/B, 16 Medicare Advantage HMO, CI commercial, HM HMO |
| payer_id, payer_name | 2010BB NM1*PR | primary payer only |
| patient_is_subscriber | absence of 2000C | |
| patient_* | 2010CA, else subscriber | birth date and gender fall back to subscriber |
| billing_provider_npi, _id_qualifier, _name, _tin, _taxonomy, _address, _state, _zip | 2000A/2010AA | address = N3 lines; qualifier should be XX in 5010 |
| rendering_provider_npi, attending_provider_npi, referring_provider_npi, service_facility_npi, service_facility_zip | 2310 loops | claim level only |
| principal_diagnosis_code, admitting_diagnosis_code, diagnosis_codes, drg_code | HI | diagnosis_codes = principal + other in order |
| prior_authorization_number, referral_number, payer_claim_control_number, clearinghouse_trace_number | REF G1 / 9F / F8 / D9 | |
| isa_control_number, st_control_number, implementation_version, functional_group_datetime, source_file | envelope | lineage; GS date/time orders claim versions |
| transaction_status | transaction_checks | keep `ok` in the main table |

## claim_lines (one row per LX)

claim_id, line_number, procedure_qualifier, procedure_code, procedure_modifiers (array),
revenue_code (837I), line_charge_amount, unit_basis_code, service_units, line_place_of_service,
diagnosis_pointers (array of int, 837P), service_from_date, service_to_date,
line_item_control_number, line_rendering_provider_npi, ndc_code, source_file, plus mapped context:
`effective_rendering_npi` (2420A > 2310B > 2310A > 2010AA), `effective_place_of_service` (SV105 > CLM05-1),
`line_diagnosis_codes` (SV107 pointers resolved; NULL entries mark out-of-range pointers).

## claims, current view (`resolve_claim_versions`)

Same columns as `claims` plus `version_count`; one row per claim (latest version by GS date), voids removed.

## claim_quality (`quality_checks`)

claim_id, patient_control_number, line_number, rule_id, severity (error | warning), field, value, message,
source_file. Rules and sources: `quality_rules.md`.

## claim_diagnoses (one row per HI diagnosis)

claim_id, diagnosis_sequence, diagnosis_qualifier, diagnosis_code, is_principal.

## transaction_checks (one row per ST/SE, plus one per non-X12 file)

file_path, transaction_set, st_control_number, implementation_version, isa_fixed_width, se_segment_count,
se_control_number, segment_count, claim_count, transaction_status
(`ok`, `missing_SE`, `segment_count_mismatch`, `control_number_mismatch`, `not_837`, `not_x12`).

## Mapping to payer-provider-measure-catalog (`adapters/x12_837_835.yaml`)

The adapter expects landed header/line tables. Override its `source` and field bindings with:

| Canonical field | This skill |
|---|---|
| claim.claim_id | claims.claim_id |
| claim.member_id | claims.member_id |
| claim.service_month | `date_trunc('month', claims.service_from_date)` |
| claim.billed_amount | claims.total_charge_amount |
| claim.payer_id | claims.payer_id |
| claim.provider_id | claims.billing_provider_npi |
| claim_line.claim_line_id | `concat(claim_id, '-', line_number)` |
| claim_line.line_billed_amount | claim_lines.line_charge_amount |
| claim_line.procedure_code / revenue_code / service_units | claim_lines.* |

Allowed and paid amounts and claim status come from the 835 remittance, which this skill does not
parse; leave those adapter fields unmapped and the generator skips the dependent measures.
