#!/usr/bin/env python3
"""
Synthetic data generator for rwe-cohortstudy skill evaluation.

Creates three datasets with built-in confounding by indication:
  1. rwe_cohort.csv   — cross-sectional, binary mortality outcome (tasks rwe-001, rwe-002)
  2. rwe_survival.csv  — time-to-event for weighted Cox + RMST (task rwe-003)
  3. rwe_tte.csv       — target trial emulation structure (task rwe-004)

Confounding design:
  - Sicker patients (older, higher Charlson, prior MI, worse HbA1c, lower eGFR,
    smoker) are MORE likely to receive treatment.
  - These same factors increase mortality / event risk.
  - True treatment effect is PROTECTIVE (OR ~0.7 for mortality).
  - Without PS adjustment, treatment appears HARMFUL (confounding by indication).
  - After PS adjustment, the protective effect is recovered.

This makes tasks good discriminators: a naive approach that skips confounding
adjustment will report the wrong direction of effect.

Usage:
    python3 generate_data.py

Output volume (override via SKILL_EVAL_DATA_DIR, or legacy RWE_EVAL_DATA_DIR):
    /Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy/
"""

import os
import numpy as np
import pandas as pd

# ── Configuration ──────────────────────────────────────────────────────────

N_COHORT = 2000       # cross-sectional cohort size
N_SURVIVAL = 2000     # survival cohort size
N_TTE = 1500          # target trial emulation cohort size
RANDOM_STATE = 42

OUT_DIR = os.environ.get("SKILL_EVAL_DATA_DIR") or os.environ.get(
    "RWE_EVAL_DATA_DIR",
    "/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy",
)

COVARIATES = [
    "age", "female", "charlson_score", "prior_mi", "diabetes_duration",
    "hba1c", "egfr", "bmi", "smoker", "statin_use", "ace_inhibitor",
]

CATEGORICAL = ["female", "prior_mi", "smoker", "statin_use", "ace_inhibitor"]

# ── True effect sizes (ground truth for evaluation) ───────────────────────
# These are the causal parameters baked into the data-generating process.
# A correctly specified analysis should recover values close to these.
# The `estimate_deviation` scorer in scorers.py compares agent outputs
# against these values (default 25% relative tolerance).
#
# NOTE: These are *conditional* parameters from the logistic / exponential
# models.  Marginal estimates (PSM, DR, IPW-weighted Cox) will differ
# slightly due to non-collapsibility of the OR/HR, but the tolerance
# is wide enough that any correct confounding-adjusted analysis passes
# while an unadjusted analysis (crude OR ~1.5–2.0) clearly fails.

TRUE_EFFECTS = {
    "odds_ratio":     0.65,   # conditional OR — mortality logistic model
    "hazard_ratio":   0.70,   # conditional HR — exponential survival model
}

# Treatment intercepts control confounding strength / treatment prevalence.
# Cohort tasks use the default (-3.5 → ~10% treated).
# TTE needs higher prevalence to avoid positivity violations.
TREATMENT_INTERCEPTS = {
    "cohort":  -3.5,   # ~10% treated  (rwe-001, rwe-002, rwe-003)
    "tte":     -1.0,   # ~45% treated  (rwe-004)
}

# ── Data generation ───────────────────────────────────────────────────────

def _generate_base_covariates(n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Generate baseline covariates with realistic distributions and correlations."""
    df = pd.DataFrame()

    # Age: 40-85, slightly right-skewed
    df["age"] = rng.normal(62, 11, n).clip(40, 85).round(0).astype(int)

    # Female: 45% prevalence
    df["female"] = rng.binomial(1, 0.45, n)

    # Charlson comorbidity score: 0-6, correlated with age
    charlson_base = (df["age"] - 40) / 15  # higher in older patients
    df["charlson_score"] = rng.poisson(np.clip(charlson_base, 0, 5)).astype(int)

    # Prior MI: 15% prevalence, higher in older / higher Charlson
    p_mi = 0.05 + 0.02 * (df["age"] - 40) / 10 + 0.03 * df["charlson_score"]
    df["prior_mi"] = rng.binomial(1, np.clip(p_mi, 0, 0.5))

    # Diabetes duration: 1-25 years, correlated with age
    df["diabetes_duration"] = rng.normal(
        8 + (df["age"] - 50) * 0.3, 4, n
    ).clip(1, 25).round(0).astype(int)

    # HbA1c: 5.5-11%, higher in longer diabetes duration
    df["hba1c"] = rng.normal(
        7.0 + 0.05 * df["diabetes_duration"], 1.2, n
    ).clip(5.5, 11).round(1)

    # eGFR: 20-120, lower in older patients and higher Charlson
    df["egfr"] = rng.normal(
        85 - 0.5 * (df["age"] - 50) - 3 * df["charlson_score"], 15, n
    ).clip(20, 120).round(0).astype(int)

    # BMI: 18-45
    df["bmi"] = rng.normal(29, 5, n).clip(18, 45).round(1)

    # Smoker: 20% prevalence, slightly higher in younger patients
    p_smoke = 0.25 - 0.003 * (df["age"] - 40)
    df["smoker"] = rng.binomial(1, np.clip(p_smoke, 0.05, 0.35))

    # Statin use: 40% prevalence, higher in older / prior MI
    p_statin = 0.25 + 0.01 * (df["age"] - 40) + 0.15 * df["prior_mi"]
    df["statin_use"] = rng.binomial(1, np.clip(p_statin, 0, 0.8))

    # ACE inhibitor: 35% prevalence, higher in lower eGFR / higher Charlson
    p_ace = 0.20 + 0.01 * df["charlson_score"] + 0.001 * (90 - df["egfr"])
    df["ace_inhibitor"] = rng.binomial(1, np.clip(p_ace, 0, 0.7))

    return df


def _treatment_probability(df: pd.DataFrame, intercept: float = -3.5) -> np.ndarray:
    """
    Probability of receiving treatment, driven by confounders.
    Sicker patients (older, higher Charlson, prior MI, worse HbA1c, lower eGFR,
    smoker) are more likely to receive treatment — classic confounding by indication.

    intercept: controls base treatment rate.
      -3.5 → ~10% treated (default, for cohort tasks).
      -1.0 → ~35-40% treated (for TTE, avoids positivity violations).
    """
    logit_p = (
        intercept
        + 0.04 * (df["age"] - 60)
        + 0.30 * df["charlson_score"]
        + 0.50 * df["prior_mi"]
        + 0.03 * (df["diabetes_duration"] - 8)
        + 0.20 * (df["hba1c"] - 7.0)
        - 0.015 * (df["egfr"] - 80)
        + 0.25 * df["smoker"]
        - 0.10 * df["statin_use"]
        - 0.08 * df["ace_inhibitor"]
    )
    return 1 / (1 + np.exp(-logit_p))


def _mortality_probability(
    df: pd.DataFrame, treatment: np.ndarray
) -> np.ndarray:
    """
    Probability of mortality. Treatment has a TRUE protective effect (OR < 1).
    Confounders increase risk, creating confounding by indication.
    Uses TRUE_EFFECTS["odds_ratio"] as the conditional treatment OR.
    """
    logit_p = (
        -4.0
        + 0.05 * (df["age"] - 60)
        + 0.35 * df["charlson_score"]
        + 0.60 * df["prior_mi"]
        + 0.04 * (df["diabetes_duration"] - 8)
        + 0.25 * (df["hba1c"] - 7.0)
        - 0.02 * (df["egfr"] - 80)
        + 0.30 * df["smoker"]
        + np.log(TRUE_EFFECTS["odds_ratio"]) * treatment
    )
    return 1 / (1 + np.exp(-logit_p))


def generate_cross_sectional(n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Generate cross-sectional cohort with binary mortality outcome."""
    df = _generate_base_covariates(n, rng)
    ps = _treatment_probability(df)
    df["treatment"] = rng.binomial(1, ps)

    mort_p = _mortality_probability(df, df["treatment"].values)
    df["mortality"] = rng.binomial(1, mort_p)

    # Sanity check: unadjusted effect should be harmful (confounding by indication)
    crude_or = (
        df[df["treatment"] == 1]["mortality"].mean()
        / (1 - df[df["treatment"] == 1]["mortality"].mean())
    ) / (
        df[df["treatment"] == 0]["mortality"].mean()
        / (1 - df[df["treatment"] == 0]["mortality"].mean())
    )
    print(f"  Crude OR (unadjusted): {crude_or:.3f}  (expect > 1 due to confounding)")
    print(f"  Treatment rate: {df['treatment'].mean():.3f}")
    print(f"  Mortality rate: {df['mortality'].mean():.3f}")
    print(f"  N treated: {df['treatment'].sum()}  N control: {(1-df['treatment']).sum()}")
    return df


def generate_survival(n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Generate cohort with time-to-event outcomes for survival analysis."""
    df = _generate_base_covariates(n, rng)
    ps = _treatment_probability(df)
    df["treatment"] = rng.binomial(1, ps)

    # Baseline hazard driven by covariates (same structure as mortality)
    # Scale: exp(-5)/100 ≈ 0.00067 daily hazard → mean ~1500 days → ~30% events in 730d
    logit_h = (
        -5.0
        + 0.04 * (df["age"] - 60)
        + 0.30 * df["charlson_score"]
        + 0.50 * df["prior_mi"]
        + 0.03 * (df["diabetes_duration"] - 8)
        + 0.20 * (df["hba1c"] - 7.0)
        - 0.015 * (df["egfr"] - 80)
        + 0.25 * df["smoker"]
    )
    # Treatment reduces hazard — uses TRUE_EFFECTS["hazard_ratio"]
    log_h_treatment = np.log(TRUE_EFFECTS["hazard_ratio"]) * df["treatment"]
    hazard = np.exp(logit_h + log_h_treatment) / 100  # daily hazard

    # Exponential time-to-event
    time_to_event = rng.exponential(1 / hazard).astype(int)
    time_to_event = np.clip(time_to_event, 1, 730)  # 1-730 days follow-up

    # Censoring: 30% administrative censoring at 730 days
    censor_time = rng.integers(365, 731, n)
    event = (time_to_event <= censor_time).astype(int)
    time_to_event = np.where(event == 1, time_to_event, censor_time)

    df["time_to_event"] = time_to_event
    df["event"] = event

    # Sanity check (lifelines optional — skip if not installed)
    try:
        from lifelines.statistics import logrank_test

        t, c = df[df["treatment"] == 1], df[df["treatment"] == 0]
        lr = logrank_test(
            t["time_to_event"], c["time_to_event"],
            event_observed_A=t["event"], event_observed_B=c["event"],
        )
        print(f"  Unweighted logrank p: {lr.p_value:.6f}  (expect non-significant or harmful due to confounding)")
    except ImportError:
        print("  (lifelines not installed — skipping logrank sanity check)")
    print(f"  Event rate: {df['event'].mean():.3f}")
    print(f"  Median time-to-event: {df['time_to_event'].median():.0f} days")
    return df


def generate_target_trial(n: int, rng: np.random.Generator) -> pd.DataFrame:
    """
    Generate observational data structured for target trial emulation.
    Each patient has an index date and may or may not initiate treatment
    within the 30-day grace period. Outcome is binary mortality within 2 years.
    """
    df = _generate_base_covariates(n, rng)

    # Index date: random dates in a 2-year window
    start = pd.Timestamp("2022-01-01")
    df["patient_id"] = range(1, n + 1)
    df["index_date"] = start + pd.to_timedelta(rng.integers(0, 730, n), unit="D")

    # Treatment initiation: use TTE intercept for adequate positivity.
    ps = _treatment_probability(df, intercept=TREATMENT_INTERCEPTS["tte"])
    df["treatment_initiated"] = rng.binomial(1, ps)

    # Treatment date: within 30-day grace period if initiated
    grace_days = rng.integers(0, 31, n)
    df["treatment_date"] = df["index_date"] + pd.to_timedelta(
        np.where(df["treatment_initiated"] == 1, grace_days, np.nan), unit="D"
    )

    # Follow-up: 730 days from index
    df["followup_days"] = 730

    # Outcome: same mortality model (treatment protective)
    mort_p = _mortality_probability(df, df["treatment_initiated"].values)
    df["mortality"] = rng.binomial(1, mort_p)

    # Time to event or censoring
    event_time = rng.integers(30, 731, n)
    df["event_time"] = np.where(df["mortality"] == 1, event_time, 730)
    df["event"] = df["mortality"]

    # Outcome date (for patients with events)
    df["outcome_date"] = df["index_date"] + pd.to_timedelta(
        np.where(df["mortality"] == 1, df["event_time"], np.nan), unit="D"
    )

    print(f"  N patients: {n}")
    print(f"  Treatment initiated: {df['treatment_initiated'].sum()} ({df['treatment_initiated'].mean():.3f})")
    print(f"  Mortality: {df['mortality'].sum()} ({df['mortality'].mean():.3f})")
    return df


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    rng = np.random.default_rng(RANDOM_STATE)

    print("=" * 70)
    print("Generating rwe-cohortstudy evaluation datasets")
    print(f"Output directory: {OUT_DIR}")
    print("=" * 70)

    # Generate datasets
    print("\n[1/3] Cross-sectional cohort (rwe_cohort.csv)...")
    cohort = generate_cross_sectional(N_COHORT, rng)

    print("\n[2/3] Survival cohort (rwe_survival.csv)...")
    survival = generate_survival(N_SURVIVAL, rng)

    print("\n[3/3] Target trial emulation (rwe_tte.csv)...")
    tte = generate_target_trial(N_TTE, rng)

    # Write to volume
    os.makedirs(OUT_DIR, exist_ok=True)

    cohort_path = os.path.join(OUT_DIR, "rwe_cohort.csv")
    survival_path = os.path.join(OUT_DIR, "rwe_survival.csv")
    tte_path = os.path.join(OUT_DIR, "rwe_tte.csv")

    cohort.to_csv(cohort_path, index=False)
    print(f"\nWrote {cohort_path} ({len(cohort)} rows)")

    survival.to_csv(survival_path, index=False)
    print(f"Wrote {survival_path} ({len(survival)} rows)")

    tte.to_csv(tte_path, index=False)
    print(f"Wrote {tte_path} ({len(tte)} rows)")

    # Summary
    print("\n" + "=" * 70)
    print("Done. Datasets for 4 benchmark tasks:")
    print(f"  rwe-001 (easy): {cohort_path} — PS matching + balance")
    print(f"  rwe-002 (hard): {cohort_path} — doubly robust + E-value")
    print(f"  rwe-003 (hard): {survival_path} — weighted Cox + RMST")
    print(f"  rwe-004 (edge): {tte_path} — target trial emulation")
    print("=" * 70)


if __name__ == "__main__":
    main()
