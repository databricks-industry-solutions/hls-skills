# Profiling — drafting a mapping when the SA has none

The per-customer **source-mapping file** is the only customer-specific input the generator needs.
When the SA has not written one, Genie Code **profiles the source** to draft it, then confirms the
flagged items. This is Phase 1–2 of the workflow made concrete.

Two ways to profile, same output (a draft `<schema>_mapping.draft.yaml` full of `# REVIEW` flags):

1. **Script** — `scripts/profile_source.py` (automated; live over a warehouse, or offline from a JSON dump).
2. **Agent-driven** — Genie Code runs the SQL below itself and applies the heuristics by hand.
   Use this when the script can't reach the workspace.

> A draft is a set of **guesses to confirm**, never a finished mapping. Every low-confidence binding
> and every unmatched required field carries a `# REVIEW:` comment. Present only the flagged items.

## Step 1 — inventory the schema

```sql
SELECT table_name, column_name, data_type
FROM <catalog>.information_schema.columns
WHERE table_schema = '<schema>'
ORDER BY table_name, ordinal_position;
```

## Step 2 — sample candidate code / status columns

For every string column whose name looks like a status/class/type/code (or that the entity match
below wants as an `enum` field), sample its distinct values so they can be mapped to canonical enums:

```sql
SELECT <col> AS value, COUNT(*) AS n
FROM <catalog>.<schema>.<table>
GROUP BY <col> ORDER BY n DESC LIMIT 25;
```

## Step 3 — match physical → canonical

Match by **normalized name** (lowercase, strip non-alphanumerics) against the synonyms below; ties
break on data-type compatibility. Only the canonical vocabulary in `canonical_model.yaml` is a valid
target — never invent a field.

**Entities (table-name synonyms):**

| Canonical entity | Physical table name contains |
|---|---|
| `encounter` | encounter, visit, enc, admission, ip_stay, inpatient |
| `appointment` | appointment, appt, booking |
| `slot` | slot, schedule_block, block, availability, capacity |
| `claim` | claim, clm, claim_header, claims |
| `claim_line` | claim_line, clm_line, service_line, claim_detail |
| `enrollment` | enrollment, coverage, member_coverage, elig, membership |
| `member_month` | member_month, membermonth, med_econ, medical_economics, pmpm |
| `care_gap` | care_gap, gap, hedis, quality_gap, measure_gap |
| `member` / `patient` | member, mbr / patient, pat |
| `provider` / `facility` | provider, prov, npi / facility, fac, site |

**Fields (column-name synonyms — high-value):** `*_id` keys match `<entity>_id`;
`patient_id`←pat_id/mrn; `member_id`←mbr_id/subscr_id/subscriber_id;
`encounter_date`←admit_dt/service_dt/visit_dt; `los_days`←los/length_of_stay;
`claim_status`←status/adj_status/clp_status; `service_month`←svc_dt/service_date (→ `date_trunc('month', …)`);
`billed_amount`←billed/charge/chrg; `allowed_amount`←allowed; `paid_amount`←paid;
`appointment_status`←appt_status/disposition; `slot_status`←block_status/slot_state;
`member_months`←mm/1; `earned_premium`←premium/prem_pmpm; `gap_status`←gap_state.

## Step 4 — emit the draft

- Map every field you matched; set `grain_keys` from the primary key column (`# REVIEW: confirm grain`).
- Any **required** canonical field with no match → emit `<field>:  # REVIEW: unmapped` (blocks that entity).
- Any canonical **enum** field → emit an `enums:` block with the sampled values under
  `map: {}  # REVIEW: map sampled values -> canonical enum`.
- `target.schema` defaults to the source schema but flag it — output usually lands in a curated schema.
- Entities with no matching table are simply omitted (their metric views drop out — that's expected).

The draft is then handed to Phase 2: confirm the `# REVIEW` items, then run the generator.
