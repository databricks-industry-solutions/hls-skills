# HIPAA Safe Harbor — 18 Identifier Classes & Default Treatment

Authority: 45 CFR §164.514(b)(2). To de-identify under Safe Harbor, ALL 18 of the
following must be removed or generalized for the individual and their relatives,
employers, and household members. Confidence: high on the class list; treatments
below are defaults — the covered entity's Privacy Officer sets the final policy.

| # | Class | `detected_class` | Default treatment |
|---|-------|------------------|-------------------|
| 1 | Names | `name` | redact / tokenize |
| 2 | Geographic subdivisions < state (street, city, county, precinct, ZIP) | `geo_sub_state` | ZIP → first 3 digits, zeroed if the 3-digit area has ≤ 20,000 people; drop finer geo |
| 3 | All date elements finer than year (birth, admission, discharge, death) directly related to an individual; all ages > 89 | `date_element` / `age_over_89` | consistent patient-level date-shift or truncate to year; ages > 89 → "90+" |
| 4 | Telephone numbers | `phone` | redact |
| 5 | Fax numbers | `fax` | redact |
| 6 | Email addresses | `email` | redact |
| 7 | Social Security numbers | `ssn` | redact |
| 8 | Medical record numbers | `mrn` | redact / tokenize |
| 9 | Health plan beneficiary numbers | `health_plan_number` | redact / tokenize |
| 10 | Account numbers | `account_number` | redact / tokenize |
| 11 | Certificate / license numbers | `certificate_license` | redact |
| 12 | Vehicle identifiers & serial numbers (incl. plates) | `vehicle_id` | redact |
| 13 | Device identifiers & serial numbers | `device_id` | redact / tokenize |
| 14 | Web URLs | `url` | redact |
| 15 | IP addresses | `ip_address` | redact |
| 16 | Biometric identifiers (finger/voice prints) | `biometric` | redact (out of MVP scope) |
| 17 | Full-face photographs & comparable images | `photo` | redact (out of MVP scope) |
| 18 | Any other unique identifying number, characteristic, or code | `other_unique_id` | review individually; redact/tokenize |

Plus the residual clause: even after removing all 18, the covered entity must have
no actual knowledge that the remaining information could re-identify an individual.
This is why the k-anonymity check on quasi-identifiers matters.
