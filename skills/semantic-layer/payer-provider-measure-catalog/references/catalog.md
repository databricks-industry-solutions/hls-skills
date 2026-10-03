# HLS Measure Catalog

_Generated from YAML by `scripts/render_catalog.py` — do not edit by hand._

## Domains

| Domain | Lens | Metric views | Measures |
|---|---|---|---|
| access_throughput | provider | mv_access_throughput__appointment | 12 |
| capacity | provider | mv_capacity__slot | 6 |
| care_delivery | provider | mv_care_delivery__encounter | 13 |
| claims | both | mv_claims__revenue_cycle, mv_claims__adjudication | 18 |
| gap_in_care | both | mv_gap_in_care__care_gap | 7 |
| payer_economics | payer | mv_payer_economics__mlr, mv_payer_economics__pmpm | 8 |

**64 measures** across all domains.

## access_throughput  (lens: provider)

### `mv_access_throughput__appointment`  — grain: appointment

| Measure | Type | Expression | Definition |
|---|---|---|---|
| `completed_appointments` | atomic | `COUNT(DISTINCT CASE WHEN appointment_status = 'completed' THEN appointment_id END)` | Appointments that completed. |
| `completed_or_arrived_appointments` | atomic | `COUNT(DISTINCT CASE WHEN appointment_status IN ('completed', 'arrived') THEN appointment_id END)` | Appointments where the patient completed or arrived — the completion numerator. |
| `late_cancel_appointments` | atomic | `COUNT(DISTINCT CASE WHEN appointment_status = 'late_cancel' THEN appointment_id END)` | Appointments cancelled inside the late-cancellation window. |
| `left_without_seen_appointments` | atomic | `COUNT(DISTINCT CASE WHEN appointment_status = 'left_without_seen' THEN appointment_id END)` | Patients who arrived but left without being seen (LWBS). |
| `no_show_appointments` | atomic | `COUNT(DISTINCT CASE WHEN appointment_status = 'no_show' THEN appointment_id END)` | Appointments where the patient did not show. |
| `rescheduled_appointments` | atomic | `COUNT(DISTINCT CASE WHEN appointment_status = 'rescheduled' THEN appointment_id END)` | Appointments that were rescheduled. |
| `same_day_cancel_appointments` | atomic | `COUNT(DISTINCT CASE WHEN appointment_status = 'same_day_cancel' THEN appointment_id END)` | Appointments cancelled the same day. |
| `scheduled_appointments` | atomic | `COUNT(DISTINCT appointment_id)` | Total scheduled appointments across all dispositions — the access-rate denominator. |
| `completion_rate` | composite | `MEASURE(completed_or_arrived_appointments) / MEASURE(scheduled_appointments)` | Share of scheduled appointments the patient completed or arrived for. |
| `late_cancellation_rate` | composite | `MEASURE(late_cancel_appointments) / MEASURE(scheduled_appointments)` | Share of scheduled appointments cancelled late. |
| `no_show_rate` | composite | `MEASURE(no_show_appointments) / MEASURE(scheduled_appointments)` | Share of scheduled appointments that were no-shows. |
| `reschedule_rate` | composite | `MEASURE(rescheduled_appointments) / MEASURE(scheduled_appointments)` | Share of scheduled appointments that were rescheduled. |

**Anti-patterns:**
- `completion_rate` — Averaging a per-day completion percentage. Use ratio-of-measures.

## capacity  (lens: provider)

### `mv_capacity__slot`  — grain: slot

| Measure | Type | Expression | Definition |
|---|---|---|---|
| `made_unavailable_slots` | atomic | `COUNT(DISTINCT CASE WHEN slot_status = 'unavailable' THEN slot_id END)` | Slots blocked / made unavailable (removed from bookable supply). |
| `total_slots` | atomic | `COUNT(DISTINCT slot_id)` | All schedulable slots (total capacity supply). |
| `unused_slots` | atomic | `COUNT(DISTINCT CASE WHEN slot_status = 'open' THEN slot_id END)` | Bookable slots that were never booked (open, unused). |
| `available_slots` | composite | `MEASURE(total_slots) - MEASURE(made_unavailable_slots)` | Bookable supply = total slots minus slots made unavailable. |
| `slot_utilization_rate` | composite | `MEASURE(used_slots) / MEASURE(available_slots)` | Utilization = booked slots / bookable supply. |
| `used_slots` | composite | `MEASURE(available_slots) - MEASURE(unused_slots)` | Booked slots = available supply minus unused (open) slots. |

**Anti-patterns:**
- `available_slots` — Storing available_slots as a physical column and SUM-ing it after a prior filter. Derive it from measures so it recomputes on any slice.
- `slot_utilization_rate` — Dividing used by TOTAL slots (includes blocked capacity) — overstates unused. Denominator is available (bookable) supply.

## care_delivery  (lens: provider)

### `mv_care_delivery__encounter`  — grain: encounter

| Measure | Type | Expression | Definition |
|---|---|---|---|
| `avg_los_days` | atomic | `AVG(los_days)` | Average length of stay (ALOS). Safe as AVG here because a metric view recomputes it from base encounter rows at each query grain. |
| `emergency_count` | atomic | `COUNT(DISTINCT CASE WHEN encounter_class = 'emergency' THEN encounter_id END)` | Distinct emergency department encounters. |
| `encounter_count` | atomic | `COUNT(DISTINCT encounter_id)` | Distinct encounters. The default care-delivery volume denominator. |
| `index_admission_count` | atomic | `COUNT(DISTINCT CASE WHEN is_index_admission THEN encounter_id END)` | Eligible index inpatient admissions — the correct DENOMINATOR for the 30-day readmission rate. |
| `inpatient_count` | atomic | `COUNT(DISTINCT CASE WHEN encounter_class = 'inpatient' THEN encounter_id END)` | Distinct inpatient encounters. |
| `observation_count` | atomic | `COUNT(DISTINCT CASE WHEN encounter_class = 'observation' THEN encounter_id END)` | Distinct observation-status encounters. |
| `readmission_30day_count` | atomic | `COUNT(DISTINCT CASE WHEN is_readmission_30day THEN encounter_id END)` | Admissions that are a 30-day readmission of a prior index admission (numerator). |
| `surgical_encounter_count` | atomic | `COUNT(DISTINCT CASE WHEN is_surgical THEN encounter_id END)` | Distinct encounters involving a surgical procedure. |
| `total_los_days` | atomic | `SUM(los_days)` | Total inpatient length of stay in days (additive). |
| `zero_procedures_count` | atomic | `COUNT(DISTINCT CASE WHEN procedure_count = 0 THEN encounter_id END)` | Encounters with no recorded procedure (a care-appropriateness / documentation signal). |
| `readmission_30day_rate` | composite | `MEASURE(readmission_30day_count) / MEASURE(index_admission_count)` | 30-day readmissions divided by eligible index admissions — the standard readmission rate. |
| `surgical_rate` | composite | `MEASURE(surgical_encounter_count) / MEASURE(encounter_count)` | Share of encounters that are surgical. |
| `zero_procedures_rate` | composite | `MEASURE(zero_procedures_count) / MEASURE(encounter_count)` | Share of encounters with no recorded procedure. |

**Anti-patterns:**
- `avg_los_days` — Precomputing ALOS per group then AVG-ing those averages (average-of-averages). Never store a rate and re-aggregate it — aggregate the base rows.
- `surgical_rate` — AVG of a per-row surgical flag summed then divided outside the metric view — breaks on rollup. Use ratio-of-measures.
- `zero_procedures_rate` — Storing the rate per group and averaging. Use ratio-of-measures so it recomputes at any grain.
- `readmission_30day_rate` — Dividing readmissions by encounter_count (all encounters), or by inpatient_count. The denominator is INDEX admissions, not total volume.

## claims  (lens: both)

### `mv_claims__revenue_cycle`  — grain: claim

| Measure | Type | Expression | Definition |
|---|---|---|---|
| `claim_count` | atomic | `COUNT(DISTINCT claim_id)` | Distinct claims — the per-claim average denominator for this view. |
| `total_allowed_amount` | atomic | `SUM(allowed_amount)` | Total allowed amount (contracted rate) across claims. |
| `total_billed_amount` | atomic | `SUM(billed_amount)` | Total charges billed. |
| `total_paid_amount` | atomic | `SUM(paid_amount)` | Total amount paid by the payer. |
| `total_patient_responsibility` | atomic | `SUM(patient_responsibility)` | Total member cost-share (deductible + coinsurance + copay). |
| `avg_billed_per_claim` | composite | `MEASURE(total_billed_amount) / MEASURE(claim_count)` | Average billed charge per claim. |
| `avg_paid_per_claim` | composite | `MEASURE(total_paid_amount) / MEASURE(claim_count)` | Average paid amount per claim. |
| `net_collection_rate` | composite | `MEASURE(total_paid_amount) / MEASURE(total_allowed_amount)` | Payments collected as a share of the allowed (contracted) amount. |
| `payer_yield_rate` | composite | `MEASURE(total_paid_amount) / MEASURE(total_billed_amount)` | Paid as a share of billed charges (gross yield). |

**Anti-patterns:**
- `net_collection_rate` — Paid / billed — that is gross yield, not net collection. Net collection uses ALLOWED as the denominator.

### `mv_claims__adjudication`  — grain: claim

| Measure | Type | Expression | Definition |
|---|---|---|---|
| `appealed_claim_count` | atomic | `COUNT(DISTINCT CASE WHEN claim_status = 'appealed' THEN claim_id END)` | Claims under appeal. |
| `claim_count` | atomic | `COUNT(DISTINCT claim_id)` | Distinct claims — the count-based denial-rate denominator. |
| `denied_billed_amount` | atomic | `SUM(CASE WHEN claim_status = 'denied' THEN billed_amount ELSE 0 END)` | Billed charges on denied claims. |
| `denied_claim_count` | atomic | `COUNT(DISTINCT CASE WHEN claim_status = 'denied' THEN claim_id END)` | Claims denied. |
| `paid_claim_count` | atomic | `COUNT(DISTINCT CASE WHEN claim_status = 'paid' THEN claim_id END)` | Claims adjudicated as paid. |
| `pending_claim_count` | atomic | `COUNT(DISTINCT CASE WHEN claim_status = 'pending' THEN claim_id END)` | Claims pending adjudication. |
| `total_billed_amount` | atomic | `SUM(billed_amount)` | Total billed charges — the dollar-denial-rate denominator for this view. |
| `denial_rate_count` | composite | `MEASURE(denied_claim_count) / MEASURE(claim_count)` | Share of claims denied (count basis). |
| `denial_rate_dollar` | composite | `MEASURE(denied_billed_amount) / MEASURE(total_billed_amount)` | Share of billed dollars on denied claims (dollar basis). |

**Anti-patterns:**
- `denial_rate_count` — Averaging a per-batch denial percentage. Non-additive — use ratio-of-measures.
- `denial_rate_dollar` — Denied dollars / paid dollars, or reusing the count-based rate. Dollar denial rate divides denied billed by TOTAL billed.

## gap_in_care  (lens: both)

### `mv_gap_in_care__care_gap`  — grain: care_gap

| Measure | Type | Expression | Definition |
|---|---|---|---|
| `closed_gap_count` | atomic | `COUNT(DISTINCT CASE WHEN gap_status = 'closed' THEN care_gap_id END)` | Closed care gaps (measure criteria satisfied). |
| `compliant_count` | atomic | `COUNT(DISTINCT CASE WHEN is_compliant THEN care_gap_id END)` | Members meeting the measure's numerator criteria (screening/control satisfied). |
| `eligible_count` | atomic | `COUNT(DISTINCT CASE WHEN is_eligible THEN care_gap_id END)` | Members in the eligible (denominator) population for the quality measure. |
| `open_gap_count` | atomic | `COUNT(DISTINCT CASE WHEN gap_status = 'open' THEN care_gap_id END)` | Open care gaps (measure criteria not yet met). |
| `gap_closure_rate` | composite | `MEASURE(closed_gap_count) / MEASURE(eligible_count)` | Closed gaps as a share of the eligible population. |
| `open_gap_rate` | composite | `MEASURE(open_gap_count) / MEASURE(eligible_count)` | Open gaps as a share of the eligible population. |
| `screening_compliance_rate` | composite | `MEASURE(compliant_count) / MEASURE(eligible_count)` | Compliant members as a share of the eligible population (HEDIS-style compliance). |

**Anti-patterns:**
- `gap_closure_rate` — closed / (open + closed) drifts as records are excluded; anchor the denominator on the ELIGIBLE population.

## payer_economics  (lens: payer)

### `mv_payer_economics__mlr`  — grain: member_month

| Measure | Type | Expression | Definition |
|---|---|---|---|
| `total_earned_premium` | atomic | `SUM(earned_premium)` | Total earned premium — the MLR denominator. |
| `total_incurred_claims` | atomic | `SUM(incurred_claims)` | Total incurred claims (paid + reserve/IBNR) — the MLR numerator. |
| `medical_loss_ratio` | composite | `MEASURE(total_incurred_claims) / MEASURE(total_earned_premium)` | Medical Loss Ratio — incurred claims as a share of earned premium (ACA MLR concept). |

**Anti-patterns:**
- `medical_loss_ratio` — Paid claims / billed charges, or paid / premium without reserves. MLR uses INCURRED claims (paid + reserve) over EARNED premium; it is non-additive — ratio-of-measures only.

### `mv_payer_economics__pmpm`  — grain: member_month

| Measure | Type | Expression | Definition |
|---|---|---|---|
| `total_allowed_claims` | atomic | `SUM(allowed_claims)` | Total allowed claims attributed to member-months (allowed-basis PMPM numerator). |
| `total_member_months` | atomic | `SUM(member_months)` | Total member-months of exposure — the PMPM / utilization denominator. |
| `total_paid_claims` | atomic | `SUM(paid_claims)` | Total paid claims attributed to member-months — the PMPM numerator. |
| `allowed_pmpm` | composite | `MEASURE(total_allowed_claims) / MEASURE(total_member_months)` | Allowed-basis PMPM — allowed claims per member-month. |
| `pmpm` | composite | `MEASURE(total_paid_claims) / MEASURE(total_member_months)` | Per-Member-Per-Month cost — paid claims divided by member-months of exposure. |

**Anti-patterns:**
- `pmpm` — Dividing by distinct member COUNT instead of member-MONTHS. Exposure is member-months; a member enrolled 6 months contributes 6, not 1.

## Canonical entities

| Entity | Grain | Lens |
|---|---|---|
| `encounter` | One clinical encounter (inpatient stay, outpatient visit, ED visit, or observation). | provider |
| `appointment` | One scheduled appointment (a booking of a slot by a patient). | provider |
| `slot` | One schedulable slot / schedule block (a unit of provider capacity). | provider |
| `claim` | One claim header (one submitted/adjudicated claim). | both |
| `claim_line` | One claim service line (line-level financial detail). | both |
| `enrollment` | One member-month of coverage (member x coverage_month). | payer |
| `member_month` | One member-month with attributed economics (payer medical-economics grain). | payer |
| `care_gap` | One care gap (member x quality measure x period). | both |
| `patient` | One patient (may equal a member seen from the provider side). | both |
| `provider` | One rendering/servicing provider. | both |
| `facility` | One facility / site of care. | provider |
