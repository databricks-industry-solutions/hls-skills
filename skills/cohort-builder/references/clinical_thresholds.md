# Clinical measure-threshold registry

The cohort builder's signature behavior is to **surface** an ambiguous "out-of-range" criterion
with the real N impact of each defensible cutoff — never to silently pick one. The registry that
powers this lives in `scripts/criteria.py` as `CLINICAL_THRESHOLDS` and is condition-agnostic: it
generalizes past the original diabetes/HbA1c case to any clinical value.

## How a threshold is resolved

1. **Term detection** — `detect_threshold_term(intent_text)` matches the user's phrasing against
   the registry (longest term first, so "poorly controlled hba1c" beats a bare substring).
2. **Measure-column grounding** — `ground_measure_column(...)` finds the real column in the table.
   An explicit `measure_col=` wins; otherwise the first registry *candidate* column present is used
   (so the same term works whether the column is `hba1c_value`, `a1c`, `systolic_bp`, `sbp`, …).
3. **Surface options** — each registered term carries ≥ 2 standard cutoffs `{label, op, value}`;
   the preview computes the cohort N for each and presents them.
4. **Fail loud** — if an out-of-range phrase is detected but no term matches *or* no measure column
   grounds, the skill asks for `measure_col` + `threshold_value` + `threshold_op` rather than
   dropping the criterion. The surfaced cutoffs are **suggestions** — the user may supply any value.

## Registered measures (as of this version)

| Term(s) | Measure | Candidate columns | Standard cutoffs surfaced |
|---------|---------|-------------------|---------------------------|
| uncontrolled / poorly controlled hba1c | HbA1c | `hba1c_value`, `hba1c`, `a1c`, `hemoglobin_a1c`, `hgba1c` | `>8.0` (clinical), `>=9.0` (HEDIS poor control) |
| uncontrolled hypertension / blood pressure | Systolic BP (mmHg) | `systolic_bp`, `sbp`, `systolic`, `bp_systolic`, `systolic_blood_pressure` | `>=140` (JNC7), `>=130` (2017 ACC/AHA) |
| high ldl | LDL (mg/dL) | `ldl`, `ldl_c`, `ldl_cholesterol`, `ldl_value` | `>=190`, `>=160`, `>=100` (ASCVD target) |
| obesity / overweight | BMI (kg/m²) | `bmi`, `body_mass_index`, `bmi_value` | `>=30` / `>=25` (WHO), `>=40` (class III) |
| reduced egfr / chronic kidney disease | eGFR (mL/min/1.73m²) | `egfr`, `egfr_value`, `gfr`, `estimated_gfr` | `<60` (CKD 3+), `<45` (3b+), `<30` (4+) |

## Extending the registry

Add a `ThresholdSpec` to `CLINICAL_THRESHOLDS` in `criteria.py`:

```python
ThresholdSpec(
    "elevated troponin", "Troponin (ng/mL)",
    ["troponin", "troponin_t", "troponin_value"],
    [{"label": ">=0.04 (99th percentile URL)", "op": ">=", "value": 0.04}],
)
```

Guidance:
- List **candidate columns** most-specific first; grounding takes the first present in the table.
- Give **≥ 2 cutoffs** when more than one standard definition exists (that is the whole point of
  surfacing). A single-cutoff entry is fine when there is only one defensible threshold.
- Cutoffs are **suggestions**; the user can always override with `threshold_value`/`threshold_op`,
  or target an unregistered measure entirely via `measure_col`.
- For a measure with two components (e.g. BP systolic *and* diastolic), register the primary measure
  here and express the second component as a generic `filters=[{column, op, value}]` entry.

## Demographic & attribute criteria

Ages, genders, and arbitrary structured attributes are not thresholds — they are grounded filters,
compiled by `compile_demographics(...)`:
- `age_min` / `age_max` → applied to a grounded `age` column, or **derived** from a birth-date
  column (`age`, `age_years`, `patient_age` | `birth_date`, `date_of_birth`, `dob`, …).
- `sex` → `=` on a scalar or `IN` on a list, against `sex`/`gender`/`administrative_gender`.
- `filters=[{column, op, value}]` → any column present in the table ("other variables").

Each is grounded against the schema, reported with per-criterion attrition N in the preview, and
pinned into the reproducible phenotype definition. A criterion whose column is absent is surfaced
as unresolved (fail loud), never silently dropped.
