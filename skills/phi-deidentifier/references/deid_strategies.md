# De-Identification Strategies

| Strategy | What it does | Reversible? | Use when |
|----------|--------------|-------------|----------|
| **redact** | Replace with null / `***` | No | Direct identifiers with no analytic value (SSN, phone, email, URL, IP) |
| **tokenize** | Salted HMAC pseudonym; key map in a locked schema | Yes (with salt + map) | Identifiers needed for re-linkage/joins (MRN, member id) but not for display |
| **shift_date** | Consistent patient-level offset; intervals preserved | Yes (with salt) | Dates where longitudinal intervals matter |
| **truncate_year** | Keep only the year | No | Dates where day granularity is unneeded downstream |
| **generalize_age** | Ages > 89 → "90+" | No | Age columns |
| **generalize_zip** | First 3 digits; zeroed for restricted prefixes | No | ZIP / postal codes |
| **keep** | Pass through | n/a | Non-PHI and low-risk quasi-identifiers (feeds k-anonymity check) |

Guidance:
- Default to the least-destructive strategy that still satisfies Safe Harbor, so
  analytic value is preserved (this is what makes the de-identified dataset useful).
- Prefer **shift_date** over **truncate_year** whenever any downstream analysis
  cares about intervals, sequences, or time-to-event.
- Only **tokenize** (never keep raw) when re-linkage is a stated requirement, and
  always isolate the key map in a separately-governed schema.
- Salts come from a Databricks secret scope, never a code literal.
