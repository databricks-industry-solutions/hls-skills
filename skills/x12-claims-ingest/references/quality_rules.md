# Quality rules (`quality_checks()`) and mapping rules

Deterministic checks run by `scripts/x12_837.py`. Each rule cites a public source. "Verified" means the
primary source was read for this skill; "sourced" means a credible public reference (X12 interpretation,
state or payer companion guide) that payers commonly apply. Payer-specific edits vary: treat warnings as
configurable, errors as quarantine candidates.

## Quality rules

| rule_id | severity | rule | source |
|---|---|---|---|
| NPI_INVALID | error | 10 digits; check digit = Luhn mod 10 over the first 9 digits computed as if prefixed by 80840 (add 24). Checked on billing, rendering, attending, referring, service facility and line rendering NPIs | verified: [CMS NPI check digit](https://www.cms.gov/Regulations-and-Guidance/Administrative-Simplification/NationalProvIdentStand/Downloads/NPIcheckdigit.pdf) |
| BILLING_ID_NOT_NPI | error | 5010 billing provider primary ID is the NPI (NM108 = XX) | verified: [CMS, How to avoid common 5010 claims rejections](https://www.cms.gov/files/document/howtoavoidcommonversion5010claimsrejectionspdf) |
| BILLING_ADDRESS_PO_BOX | error | 2010AA billing provider address must be a physical address, for 837P and 837I; a PO Box may only be the pay-to address | verified: same CMS document |
| ZIP_INCOMPLETE | error | 9-digit ZIP for the billing provider and the service facility | verified: same CMS document |
| ICD10_FORMAT | error | ICD-10-CM codes are 3-7 characters (letter, digit, then letters/digits) and are sent without the decimal point | sourced: [CMS ICD-10](https://www.cms.gov/medicare/coding-billing/icd-10-codes) |
| PROCEDURE_CODE_FORMAT | error | HC qualifier: CPT `00000`, Category II `0000F`, Category III `0000T`, HCPCS Level II `A0000` | sourced: [AMA CPT](https://www.ama-assn.org/practice-management/cpt), [CMS HCPCS](https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system) |
| REVENUE_CODE_FORMAT | error | revenue codes are 4 digits with the leading zero kept (`0450`, not `450`) | sourced: [CMS Blue Button revenue center code](https://bluebutton.cms.gov/fhir/CodeSystem/CLM-REV-CNTR-CD/) |
| POS_INVALID | error | place of service is a 2-digit CMS code; unassigned: 28-30, 35-40, 43-48, 59, 63-64, 67-70, 73-80, 82-98 | verified: [CMS POS code set](https://www.cms.gov/medicare/coding-billing/place-of-service-codes/code-sets) |
| DATE_INVALID | error | no future service dates; birth date not after service; statement from <= to; 837I line dates inside the statement period | sourced: payer companion guides |
| DX_POINTER_INVALID | error | SV107 pointers are 1-based positions in the claim's diagnosis list; at most 4 per line | sourced: [X12 RFI 2776](https://x12.org/resources/requests-for-interpretation/rfi-2776-use-diagnosis-pointers-837-pacdr) |
| TOTAL_MISMATCH | error | CLM02 equals the sum of line charges (SV102 / SV203); voids excluded | sourced: payer front-end edits |
| DUPLICATE_CLAIM | warning | a later original claim with the same member, patient, billing NPI, service date, charge and procedures; replacements and voids are not duplicates | sourced: payer duplicate edits (criteria vary, adjust the signature) |
| GENDER_CODE_INVALID | warning | DMG03 is M, F or U | sourced: [X12 RFI 2311](https://x12.org/resources/requests-for-interpretation/rfi-2311-nonbinary-gender-claims) |
| FILING_INDICATOR_INVALID | warning | SBR09 is an X12 claim filing indicator code | sourced: X12 code list |
| ISA_NOT_FIXED_WIDTH | warning | the ISA is 106 characters including the terminator; trimmed padding is non-compliant but still parsed | verified: ISA layout (positions 4 / 105 / 106) |

## Mapping rules

| rule | implementation | source |
|---|---|---|
| Version | GS08: `004010X098A1` / `004010X096A1` (4010A1 P / I), `005010X222A1` / `005010X223A2` (5010 P / I); 4010 uses ICD-9 qualifiers BK/BF, 5010 ICD-10 ABK/ABF. Column `x12_version` | sourced: CMS 5010 materials |
| Claim versions | CLM05-3 1 original, 7 replacement, 8 void; 7 and 8 carry REF*F8 (payer claim control number of the original). `resolve_claim_versions()` keeps the latest version by GS date and drops voids | sourced: [X12 RFI 1538](https://x12.org/resources/requests-for-interpretation/rfi-1538-5010837i2300clm05-3-and-ref) |
| Performing provider | line 2420A > claim 2310B rendering > 2310A attending (837I) > 2010AA billing: `effective_rendering_npi` | verified (837P): [SC DHHS 837P companion guide](https://scdhhs.gov/sites/dhhs/files/managedcare/837%20Professional%20Companion%20Guide_Final%209-12-22.pdf), "if neither the line level (2420A) nor claim level (2310B) NPIs are entered, the system defaults to the billing/pay-to provider NPI"; 837I attending step is this skill's convention |
| Line diagnoses | SV107 pointers resolved to codes: `line_diagnosis_codes` (NULL for an out-of-range pointer) | sourced: X12 RFI 2776 |
| Place of service | line SV105 overrides claim CLM05-1 (837P): `effective_place_of_service` | sourced: [X12 RFI 2269](https://x12.org/resources/requests-for-interpretation/rfi-2269-837p-multiple-place-service) |
| Patient vs subscriber | 2000C only when the patient differs from the subscriber; member key comes from 2010BA | sourced: CAQH CORE claim content rule |
