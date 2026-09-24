---
name: rwe-cohortstudy
description: >
  Conduct real-world evidence (RWE) comparative effectiveness studies in Python.
  Covers propensity score matching, inverse probability weighting, overlap weighting,
  doubly robust estimation, balance diagnostics (SMD, love plots), treatment effect
  estimation, survival analysis, sensitivity analysis (E-values, tipping points),
  external control arm integration, marginal structural models for time-varying confounding,
  and target trial emulation. Read this skill when the user asks to compare treatment groups
  in observational data, run propensity score analysis, build external control arms, emulate
  a target trial, perform causal inference from EHR/claims data, or conduct comparative
  cohort studies with confounding adjustment.
author: Yen Low
version: 0.1
license: Databricks License
---

# Real-World Evidence Analysis in Python

## Overview

This skill provides a complete toolkit for comparative effectiveness research (CER) and
real-world evidence studies using Python. It maps the standard R-based RWE workflow
(MatchIt, WeightIt, cobalt, survival, survey, tableone, EValue, tipr) to Python equivalents
using scikit-learn, statsmodels, lifelines, and custom implementations.

## When to Use

Load this skill when the user wants to:
- Compare two or more treatment groups in observational (non-randomized) data
- Apply propensity score matching, weighting, or stratification
- Build an external control arm from real-world data
- Emulate a target trial from EHR or claims data
- Assess sensitivity of observational findings to unmeasured confounding
- Handle time-varying confounding with marginal structural models
- Produce balance diagnostics (standardized mean differences, love plots)
- Estimate treatment effects with proper confidence intervals

## Python Package Stack

```python
%pip install scikit-learn statsmodels lifelines matplotlib seaborn --quiet

import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_predict
from sklearn.calibration import calibration_curve
from sklearn.metrics import roc_auc_score, brier_score_loss
import statsmodels.api as sm
import statsmodels.formula.api as smf
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.statistics import logrank_test, proportional_hazard_test
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')
```

### Package Mapping: R to Python

| R Package | Python Equivalent | Notes |
|---|---|---|
| MatchIt | sklearn + custom nearest-neighbor | Logistic regression for PS, sklearn.neighbors for matching |
| WeightIt | sklearn + manual weight computation | IPW, stabilized, overlap weights computed directly |
| cobalt | Custom SMD functions + matplotlib | Love plots and balance tables from scratch |
| tableone | Custom groupby + SMD | Baseline characteristics table with tests |
| survey | statsmodels.stats.weightstats | Weighted mean, proportion, quantile estimation |
| survival | lifelines | KM curves, Cox PH, logrank tests |
| EValue | Custom E-value function | See sensitivity analysis section |
| tipr | Custom tipping point function | See sensitivity analysis section |
| twang | sklearn GBM + custom weight extraction | GBM-based PS with balance optimization |
| optmatch | scipy.optimize.linear_sum_assignment | Optimal matching via Hungarian algorithm |

## Workflow

1. Define the study question (PICO: population, intervention, comparator, outcome)
2. Cohort assembly (inclusion/exclusion criteria, treatment assignment, follow-up)
3. Covariate assessment (baseline confounders measured pre-treatment)
4. Propensity score estimation (probability of treatment given covariates)
5. Confounding adjustment (matching, weighting, stratification, or doubly robust)
6. Balance diagnostics (verify covariate balance after adjustment, SMD < 0.1)
7. Treatment effect estimation (outcome model on adjusted sample/weights)
8. Sensitivity analysis (E-values, tipping point analysis)
9. Reporting (baseline table, balance table, effect estimates with CIs, survival curves)

## Guardrails

1. Adjust only for baseline confounders measured before treatment; never put post-treatment variables in the propensity score model.
2. Check common support before estimating effects; report how many patients fall outside it and trim (Section 4.3) rather than extrapolate.
3. Do not report an effect until balance is verified: every covariate needs SMD < 0.1 after adjustment.
4. Never present an unadjusted comparison as a causal effect; confounding by indication is the default in observational data.
5. Report every effect estimate with a 95% CI; use robust (sandwich) standard errors for weighted models.
6. Pair every causal estimate with a sensitivity analysis for unmeasured confounding (E-value or tipping point).
7. For time-to-event outcomes, test proportional hazards (Schoenfeld) before reporting a Cox HR.

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| Few treated patients matched | Caliper too tight or poor overlap | Check common support; caliper 0.1-0.2 SD of logit(PS) is typical (Section 3) |
| Extreme IPW weights | PS near 0 or 1 | Stabilize weights, trim at percentiles, or use overlap weights (Section 4) |
| SMD > 0.1 after adjustment | PS model misspecified | Add interactions or nonlinear terms, or use a GBM PS model; re-check balance |
| Schoenfeld test rejects PH | Hazards not proportional | Report RMST difference, which does not assume PH (Section 7.3) |
| Weighted Cox CIs too narrow | Naive SEs ignore weighting | Fit with `robust=True` in lifelines |
| PS logistic model does not converge | Unscaled or collinear covariates | Standardize covariates, raise `max_iter`, or add L1/L2 regularization |

---

## 1. Study Design and Target Trial Emulation

### Defining the Target Trial

Before writing any code, articulate the trial you are emulating:

```python
study_design = {
    'question': 'Does drug A reduce mortality compared to drug B in adults with T2DM?',
    'population': 'Adults >=18y with T2DM, no prior exposure to either drug',
    'intervention': 'Initiation of Drug A',
    'comparator': 'Initiation of Drug B',
    'outcome': 'All-cause mortality within 2 years',
    'follow_up': '2 years from treatment initiation (time zero)',
    'assignment': 'New user (initiator) design',
    'eligibility_window': 'Index date = first prescription; covariates from 365d pre-index',
    'exclusions': ['Prior cancer', 'Pregnancy', '< 365d enrollment pre-index', 'Age < 18'],
}
for k, v in study_design.items():
    print(f'{k}: {v}')
```

### Key Design Principles

- Time zero: treatment assignment and follow-up start. All covariates must be measured BEFORE time zero.
- New-user design: exclude prior exposure to either treatment (avoids prevalent-user bias).
- Active comparator: use an active treatment as comparator when possible (minimizes confounding by indication).
- Grace period: allow a window (e.g., 30 days) between eligibility and treatment initiation.
- Intention-to-treat: patients stay in assigned group regardless of discontinuation.

### Cohort Assembly

```python
def assemble_cohort(df, index_date_col='index_date', treatment_col='treatment',
                    min_enrollment_days=365, min_age=18, max_followup_days=730):
    """Assemble a new-user cohort with eligibility criteria."""
    cohort = df.copy()
    cohort = cohort[cohort['prior_exposure_drugA'] == False]
    cohort = cohort[cohort['prior_exposure_drugB'] == False]
    cohort = cohort[cohort['days_enrolled_pre_index'] >= min_enrollment_days]
    cohort = cohort[cohort['age_at_index'] >= min_age]
    for excl_col in ['prior_cancer', 'pregnancy_at_index']:
        if excl_col in cohort.columns:
            cohort = cohort[~cohort[excl_col]]
    cohort['followup_days'] = (
        cohort['disenrollment_date'] - cohort[index_date_col]
    ).dt.days.clip(upper=max_followup_days).clip(lower=0)
    cohort['event'] = cohort['event_date'].notna().astype(int)
    cohort['time_to_event'] = np.where(
        cohort['event'] == 1,
        (cohort['event_date'] - cohort[index_date_col]).dt.days,
        cohort['followup_days']
    )
    print(f"Cohort: {len(cohort)} | Treated: {(cohort[treatment_col]==1).sum()} | Control: {(cohort[treatment_col]==0).sum()}")
    return cohort.reset_index(drop=True)
```

---

## 2. Propensity Score Estimation

The propensity score is `e(X) = P(treatment=1 | X)`, estimated via logistic regression or ML methods.

```python
def estimate_propensity_scores(df, covariates, treatment_col='treatment',
                                method='logistic', cv_folds=5, random_state=42):
    """
    method: 'logistic' (standard), 'lasso' (L1 variable selection),
           'rf' (random forest, cross-fitted), 'gbm' (gradient boosting, cross-fitted)
    """
    X = df[covariates].copy().fillna(df[covariates].median())
    y = df[treatment_col].values
    scaler = StandardScaler()
    X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=covariates, index=df.index)

    if method == 'logistic':
        model = LogisticRegression(penalty='l2', C=1.0, solver='lbfgs', max_iter=2000)
        model.fit(X_scaled, y)
        ps = model.predict_proba(X_scaled)[:, 1]
        print(f"Logistic PS AUC: {roc_auc_score(y, ps):.4f}")
    elif method == 'lasso':
        model = LogisticRegression(penalty='l1', C=0.1, solver='saga', max_iter=5000)
        model.fit(X_scaled, y)
        ps = model.predict_proba(X_scaled)[:, 1]
        n_sel = (model.coef_[0] != 0).sum()
        print(f"Lasso PS AUC: {roc_auc_score(y, ps):.4f} ({n_sel}/{len(covariates)} covariates)")
    elif method == 'rf':
        model = RandomForestClassifier(n_estimators=500, max_depth=6, min_samples_leaf=20)
        ps = cross_val_predict(model, X_scaled, y, cv=cv_folds, method='predict_proba')[:, 1]
        model.fit(X_scaled, y)
        print(f"RF PS AUC (CV): {roc_auc_score(y, ps):.4f}")
    elif method == 'gbm':
        model = GradientBoostingClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8)
        ps = cross_val_predict(model, X_scaled, y, cv=cv_folds, method='predict_proba')[:, 1]
        model.fit(X_scaled, y)
        print(f"GBM PS AUC (CV): {roc_auc_score(y, ps):.4f}")

    df = df.copy()
    df['propensity_score'] = ps.clip(0.01, 0.99)
    print(f"Brier score: {brier_score_loss(y, ps):.4f} (0.25=random)")
    for grp in [0, 1]:
        s = df[df[treatment_col] == grp]
        label = 'Treated' if grp == 1 else 'Control'
        print(f"  PS {label}: mean={s['propensity_score'].mean():.3f}")
    return df

covariates = ['age', 'female', 'charlson_score', 'prior_mi', 'diabetes_duration',
               'hba1c', 'egfr', 'bmi', 'smoker', 'statin_use', 'ace_inhibitor']
df = estimate_propensity_scores(df, covariates, method='logistic')
```

### Common Support Check

```python
def check_common_support(df, treatment_col='treatment', ps_col='propensity_score'):
    """Visualize PS distribution overlap between groups."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for grp, color, label in [(0, '#1f77b4', 'Control'), (1, '#d62728', 'Treated')]:
        s = df[df[treatment_col] == grp]
        axes[0].hist(s[ps_col], bins=30, alpha=0.6, color=color, label=label, density=True)
    axes[0].set_xlabel('PS'); axes[0].set_title('PS Distribution'); axes[0].legend()

    treated = df[df[treatment_col] == 1][ps_col]
    control = df[df[treatment_col] == 0][ps_col]
    axes[1].hist(control, bins=30, alpha=0.7, color='#1f77b4', label='Control', orientation='horizontal')
    axes[1].hist(treated, bins=30, alpha=0.7, color='#d62728', label='Treated',
                 orientation='horizontal', weights=np.ones_like(treated) * -1)
    axes[1].set_title('Mirror Histogram'); axes[1].legend()
    plt.tight_layout(); plt.show()

    lo = max(treated.min(), control.min()); hi = min(treated.max(), control.max())
    n_out = ((df[ps_col] < lo) | (df[ps_col] > hi)).sum()
    print(f"Common support: [{lo:.3f}, {hi:.3f}] | Outside: {n_out} ({n_out/len(df)*100:.1f}%)")
```

---

## 3. Propensity Score Matching

### 3.1 Nearest-Neighbor Matching (1:1, with or without replacement)

```python
from sklearn.neighbors import NearestNeighbors

def nearest_neighbor_match(df, treatment_col='treatment', ps_col='propensity_score',
                            ratio=1, caliper=None, replace=False, random_state=42):
    """
    Nearest-neighbor matching on logit(PS).
    ratio: controls per treated. caliper: max distance in SD of logit(PS) units (0.1-0.2 typical).
    """
    np.random.seed(random_state)
    treated = df[df[treatment_col] == 1].copy().reset_index(drop=True)
    control = df[df[treatment_col] == 0].copy().reset_index(drop=True)
    treated['ps_logit'] = np.log(treated[ps_col] / (1 - treated[ps_col]))
    control['ps_logit'] = np.log(control[ps_col] / (1 - control[ps_col]))
    caliper_val = caliper * np.std(treated['ps_logit'].values) if caliper else np.inf

    available = list(range(len(control)))
    matched_pairs = []
    for t_idx in range(len(treated)):
        if not available:
            break
        t_ps = treated.loc[t_idx, 'ps_logit']
        c_vals = control.loc[available, 'ps_logit'].values
        dists = np.abs(c_vals - t_ps)
        n_match = min(ratio, len(available))
        nearest = np.argsort(dists)[:n_match]
        for pos in nearest:
            if dists[pos] <= caliper_val:
                matched_pairs.append((treated.index[t_idx], control.index[available[pos]]))
                if not replace:
                    available.pop(pos)

    idx = [p[0] for p in matched_pairs] + [p[1] for p in matched_pairs]
    matched_data = df.loc[idx].copy()
    print(f"Matched: {len(matched_pairs)} pairs")
    return matched_data

matched_df = nearest_neighbor_match(df, ratio=1, caliper=0.2, replace=False)
```

### 3.2 Optimal Matching (Hungarian Algorithm)

```python
from scipy.optimize import linear_sum_assignment

def optimal_match(df, treatment_col='treatment', ps_col='propensity_score', caliper=None):
    """Optimal matching minimizes total within-pair distance."""
    treated = df[df[treatment_col] == 1].copy().reset_index(drop=True)
    control = df[df[treatment_col] == 0].copy().reset_index(drop=True)
    treated['ps_logit'] = np.log(treated[ps_col] / (1 - treated[ps_col]))
    control['ps_logit'] = np.log(control[ps_col] / (1 - control[ps_col]))
    dist = np.abs(treated['ps_logit'].values[:, None] - control['ps_logit'].values[None, :])
    if caliper:
        dist[dist > caliper * np.std(treated['ps_logit'].values)] = 1e6
    row_ind, col_ind = linear_sum_assignment(dist)
    if caliper:
        valid = dist[row_ind, col_ind] < 1e6
        row_ind, col_ind = row_ind[valid], col_ind[valid]
    matched = pd.concat([treated.iloc[row_ind], control.iloc[col_ind]]).reset_index(drop=True)
    print(f"Optimal matched: {len(row_ind)} pairs")
    return matched
```

### 3.3 Variable-Ratio Matching

```python
def variable_ratio_match(df, treatment_col='treatment', ps_col='propensity_score',
                         max_ratio=5, caliper=0.2, random_state=42):
    """Match more controls where controls are abundant in PS space."""
    np.random.seed(random_state)
    treated = df[df[treatment_col] == 1].copy().reset_index(drop=True)
    control = df[df[treatment_col] == 0].copy().reset_index(drop=True)
    treated['ps_logit'] = np.log(treated[ps_col] / (1 - treated[ps_col]))
    control['ps_logit'] = np.log(control[ps_col] / (1 - control[ps_col]))
    caliper_val = caliper * np.std(treated['ps_logit'].values)
    treated = treated.sort_values('propensity_score', ascending=False).reset_index(drop=True)
    available = set(range(len(control)))
    matched_idx = []
    for t_idx in range(len(treated)):
        t_ps = treated.loc[t_idx, 'ps_logit']
        avail_list = sorted(available)
        c_vals = control.loc[avail_list, 'ps_logit'].values
        dists = np.abs(c_vals - t_ps)
        within = np.where(dists <= caliper_val)[0]
        if len(within) == 0:
            continue
        n_match = min(max_ratio, len(within))
        nearest = within[np.argsort(dists[within])[:n_match]]
        for pos in nearest:
            c_idx = avail_list[pos]
            matched_idx.append(treated.index[t_idx])
            matched_idx.append(control.index[c_idx])
            available.discard(c_idx)
    matched_data = df.loc[matched_idx].copy()
    print(f"Variable-ratio matched: {len(matched_idx)//2} pairs")
    return matched_data
```

---

## 4. Inverse Probability Weighting

### 4.1 Standard IPW (ATE, ATT, ATU, Overlap)

```python
def compute_ipw(df, treatment_col='treatment', ps_col='propensity_score',
                weight_type='ate', trim_percent=None):
    """
    weight_type: 'ate' (1/PS, 1/(1-PS)), 'att' (1, PS/(1-PS)),
                 'atu' ((1-PS)/PS, 1), 'overlap' ((1-PS), PS)
    """
    df = df.copy()
    ps, z = df[ps_col].values, df[treatment_col].values
    if weight_type == 'ate':
        df['ipw'] = np.where(z == 1, 1/ps, 1/(1-ps))
    elif weight_type == 'att':
        df['ipw'] = np.where(z == 1, 1.0, ps/(1-ps))
    elif weight_type == 'atu':
        df['ipw'] = np.where(z == 1, (1-ps)/ps, 1.0)
    elif weight_type == 'overlap':
        df['ipw'] = np.where(z == 1, 1-ps, ps)
    if trim_percent is not None:
        lo = np.percentile(df['ipw'], trim_percent)
        hi = np.percentile(df['ipw'], 100 - trim_percent)
        df = df[(df['ipw'] >= lo) & (df['ipw'] <= hi)]
    ess = lambda w: (w.sum()**2) / (w**2).sum()
    print(f"Weight: {weight_type} | range [{df['ipw'].min():.2f}, {df['ipw'].max():.2f}]")
    print(f"  Effective N: T={ess(df.loc[df[treatment_col]==1,'ipw']):.0f}, C={ess(df.loc[df[treatment_col]==0,'ipw']):.0f}")
    return df

df_weighted = compute_ipw(df, weight_type='ate', trim_percent=1)
```

### 4.2 Stabilized Weights

```python
def compute_stabilized_weights(df, treatment_col='treatment', ps_col='propensity_score'):
    """Stabilized IPW reduces weight variance by multiplying by marginal P(treatment)."""
    df = df.copy()
    ps, z = df[ps_col].values, df[treatment_col].values
    p = z.mean()
    df['ipw_stabilized'] = np.where(z == 1, p/ps, (1-p)/(1-ps))
    print(f"Stabilized weights: mean={df['ipw_stabilized'].mean():.3f}, SD={df['ipw_stabilized'].std():.3f}")
    return df
```

### 4.3 Trimming Rules

```python
def trim_weights(df, ps_col='propensity_score', method='crump', lower=5, upper=95):
    """crump: keep PS in [0.1, 0.9]. percentile: trim at lower/upper percentiles."""
    if method == 'crump':
        mask = (df[ps_col] >= 0.1) & (df[ps_col] <= 0.9)
    elif method == 'percentile':
        lo, hi = np.percentile(df[ps_col], [lower, upper])
        mask = (df[ps_col] >= lo) & (df[ps_col] <= hi)
    return df[mask].copy()
```

---

## 5. Balance Diagnostics

### 5.1 Standardized Mean Difference (SMD)

```python
def compute_smd(data, covariate, treatment_col='treatment', weight_col=None):
    """SMD for continuous covariate. SMD > 0.1 indicates imbalance (Austin 2009)."""
    t, c = data[data[treatment_col]==1], data[data[treatment_col]==0]
    if weight_col:
        wt, wc = t[weight_col].values, c[weight_col].values
        mt, mc = np.average(t[covariate], weights=wt), np.average(c[covariate], weights=wc)
        vt = np.average((t[covariate]-mt)**2, weights=wt)
        vc = np.average((c[covariate]-mc)**2, weights=wc)
    else:
        mt, mc = t[covariate].mean(), c[covariate].mean()
        vt, vc = t[covariate].var(), c[covariate].var()
    sd = np.sqrt((vt + vc) / 2)
    return (mt - mc) / sd if sd > 0 else 0.0

def compute_smd_categorical(data, covariate, treatment_col='treatment', weight_col=None):
    """SMD for binary/categorical variables based on proportions."""
    t, c = data[data[treatment_col]==1], data[data[treatment_col]==0]
    if weight_col:
        pt = np.average(t[covariate], weights=t[weight_col])
        pc = np.average(c[covariate], weights=c[weight_col])
    else:
        pt, pc = t[covariate].mean(), c[covariate].mean()
    pv = (pt*(1-pt) + pc*(1-pc)) / 2
    return (pt - pc) / np.sqrt(pv) if pv > 0 else 0.0
```

### 5.2 Balance Table (TableOne Equivalent)

```python
def balance_table(data, covariates, treatment_col='treatment',
                  weight_col=None, categorical_cols=None):
    """Covariate balance table with SMDs before/after adjustment."""
    categorical_cols = categorical_cols or []
    results = []
    for cov in covariates:
        fn = compute_smd_categorical if cov in categorical_cols else compute_smd
        smd_unadj = abs(fn(data, cov, treatment_col, weight_col=None))
        smd_adj = abs(fn(data, cov, treatment_col, weight_col=weight_col)) if weight_col else None
        results.append({'Covariate': cov, 'SMD_unadjusted': smd_unadj,
                        'SMD_adjusted': smd_adj, 'Balanced': (smd_adj < 0.1 if smd_adj is not None else smd_unadj < 0.1)})
    bal = pd.DataFrame(results)
    print(f"\n{'Covariate':<25} {'SMD(unadj)':>12} {'SMD(adj)':>12} {'OK':>5}")
    print('-'*60)
    for _, r in bal.iterrows():
        adj = f"{r['SMD_adjusted']:.4f}" if r['SMD_adjusted'] is not None else 'N/A'
        print(f"{r['Covariate']:<25} {r['SMD_unadjusted']:>12.4f} {adj:>12} {'Y' if r['Balanced'] else 'N':>5}")
    print(f"Balanced: {bal['Balanced'].sum()}/{len(bal)}")
    return bal

# For matched data
balance_table(matched_df, covariates, categorical_cols=['female', 'smoker', 'statin_use'])
# For weighted data
balance_table(df_weighted, covariates, weight_col='ipw', categorical_cols=['female', 'smoker', 'statin_use'])
```

### 5.3 Love Plot

```python
def love_plot(data, covariates, treatment_col='treatment', weight_col=None,
              categorical_cols=None, title='Covariate Balance'):
    """Love plot: SMD before vs after adjustment (cobalt::love.plot equivalent)."""
    categorical_cols = categorical_cols or []
    smds_before, smds_after = [], []
    for cov in covariates:
        fn = compute_smd_categorical if cov in categorical_cols else compute_smd
        smds_before.append(abs(fn(data, cov, treatment_col, weight_col=None)))
        if weight_col:
            smds_after.append(abs(fn(data, cov, treatment_col, weight_col=weight_col)))
    fig, ax = plt.subplots(figsize=(10, max(6, len(covariates)*0.4)))
    y = np.arange(len(covariates))
    ax.scatter(smds_before, y, c='#d62728', s=60, label='Unadjusted', zorder=3)
    if weight_col:
        ax.scatter(smds_after, y, c='#1f77b4', s=60, label='Adjusted', zorder=3)
        ax.hlines(y, smds_before, smds_after, colors='grey', lw=0.8, alpha=0.5)
    ax.axvline(0.1, color='black', ls='--', lw=1, alpha=0.5, label='SMD=0.1')
    ax.set_yticks(y); ax.set_yticklabels(covariates)
    ax.set_xlabel('Absolute SMD'); ax.set_title(title); ax.legend()
    plt.tight_layout(); plt.show()
```

---

## 6. Treatment Effect Estimation

### 6.1 Continuous Outcome (Weighted Mean Difference)

```python
def estimate_ate_continuous(data, outcome_col, treatment_col='treatment', weight_col='ipw'):
    t, c = data[data[treatment_col]==1], data[data[treatment_col]==0]
    wt, wc = t[weight_col].values, c[weight_col].values
    mt, mc = np.average(t[outcome_col], weights=wt), np.average(c[outcome_col], weights=wc)
    ate = mt - mc
    vt = np.average((t[outcome_col]-mt)**2, weights=wt)
    vc = np.average((c[outcome_col]-mc)**2, weights=wc)
    ess_t = (wt.sum()**2)/(wt**2).sum()
    ess_c = (wc.sum()**2)/(wc**2).sum()
    se = np.sqrt(vt/ess_t + vc/ess_c)
    z = 1.96
    print(f"ATE (continuous): {ate:.3f} [{ate-z*se:.3f}, {ate+z*se:.3f}]")
    return {'ate': ate, 'se': se, 'ci': (ate-z*se, ate+z*se)}
```

### 6.2 Binary Outcome (Risk Difference, RR, OR)

```python
def estimate_ate_binary(data, outcome_col, treatment_col='treatment', weight_col='ipw'):
    t, c = data[data[treatment_col]==1], data[data[treatment_col]==0]
    pt = np.average(t[outcome_col], weights=t[weight_col].values)
    pc = np.average(c[outcome_col], weights=c[weight_col].values)
    rd, rr = pt - pc, pt/pc if pc > 0 else np.inf
    or_val = (pt/(1-pt))/(pc/(1-pc)) if (0<pt<1 and 0<pc<1) else np.inf
    ess_t = (t[weight_col].sum()**2)/(t[weight_col]**2).sum()
    ess_c = (c[weight_col].sum()**2)/(c[weight_col]**2).sum()
    se_rd = np.sqrt(pt*(1-pt)/ess_t + pc*(1-pc)/ess_c)
    z = 1.96
    print(f"Risk diff: {rd:.4f} [{rd-z*se_rd:.4f}, {rd+z*se_rd:.4f}]")
    print(f"Risk ratio: {rr:.4f} | Odds ratio: {or_val:.4f}")
    print(f"NNT: {1/rd:.1f}" if rd != 0 else "NNT: undefined")
    return {'rd': rd, 'rr': rr, 'or': or_val}
```

### 6.3 G-computation (Outcome Regression Standardization)

```python
def g_computation(data, outcome_col, treatment_col='treatment', covariates=None,
                  outcome_type='continuous', n_boot=500):
    """Fit outcome model, predict under treatment=1 and treatment=0, take mean diff."""
    if covariates is None:
        covariates = [c for c in data.columns if c not in [outcome_col, treatment_col]]
    formula = f"{outcome_col} ~ {treatment_col} + " + " + ".join(covariates)
    fit_fn = smf.ols if outcome_type == 'continuous' else smf.logit
    model = fit_fn(formula, data=data).fit(disp=0)
    ate = model.predict(data.assign(**{treatment_col: 1})).mean() - model.predict(data.assign(**{treatment_col: 0})).mean()
    boots = []
    for _ in range(n_boot):
        bd = data.sample(n=len(data), replace=True)
        try:
            bm = fit_fn(formula, data=bd).fit(disp=0)
            boots.append(bm.predict(bd.assign(**{treatment_col: 1})).mean() - bm.predict(bd.assign(**{treatment_col: 0})).mean())
        except:
            continue
    ci = (np.percentile(boots, 2.5), np.percentile(boots, 97.5))
    print(f"G-computation ATE: {ate:.4f} [{ci[0]:.4f}, {ci[1]:.4f}]")
    return {'ate': ate, 'ci': ci}
```

### 6.4 Doubly Robust Estimation

```python
def doubly_robust(data, outcome_col, treatment_col='treatment', covariates=None,
                  ps_col='propensity_score', outcome_type='continuous', n_boot=500):
    """
    Doubly robust: consistent if EITHER the PS model OR the outcome model is correct.
    DR = mean[ (Z*Y - (Z-e)*m1)/e - ((1-Z)*Y + (Z-e)*m0)/(1-e) ]
    """
    if covariates is None:
        covariates = [c for c in data.columns if c not in [outcome_col, treatment_col, ps_col]]
    z, y, e = data[treatment_col].values, data[outcome_col].values, data[ps_col].values
    formula = f"{outcome_col} ~ " + " + ".join(covariates)
    fit_fn = smf.ols if outcome_type == 'continuous' else smf.logit
    m1 = fit_fn(formula, data=data[data[treatment_col]==1]).fit(disp=0).predict(data)
    m0 = fit_fn(formula, data=data[data[treatment_col]==0]).fit(disp=0).predict(data)
    dr = (((z*y - (z-e)*m1)/e) - ((1-z)*y + (z-e)*m0)/(1-e)).mean()
    boots = []
    for _ in range(n_boot):
        bd = data.sample(n=len(data), replace=True)
        try:
            mt = fit_fn(formula, data=bd[bd[treatment_col]==1]).fit(disp=0).predict(bd)
            mc = fit_fn(formula, data=bd[bd[treatment_col]==0]).fit(disp=0).predict(bd)
            zb, yb, eb = bd[treatment_col].values, bd[outcome_col].values, bd[ps_col].values
            boots.append((((zb*yb-(zb-eb)*mt)/eb) - ((1-zb)*yb+(zb-eb)*mc)/(1-eb)).mean())
        except:
            continue
    se = np.std(boots, ddof=1)
    print(f"Doubly Robust ATE: {dr:.4f} [{dr-1.96*se:.4f}, {dr+1.96*se:.4f}]")
    return {'ate': dr, 'se': se, 'ci': (dr-1.96*se, dr+1.96*se)}
```

---

## 7. Survival Analysis

### 7.1 Weighted Kaplan-Meier Curves

```python
def weighted_km_curves(data, time_col='time_to_event', event_col='event',
                       treatment_col='treatment', weight_col='ipw',
                       labels=None, max_time=None):
    """Weighted KM survival curves with logrank test."""
    labels = labels or ['Control', 'Treated']
    if max_time is None:
        max_time = data[time_col].max()
    fig, ax = plt.subplots(figsize=(10, 7))
    colors = ['#1f77b4', '#d62728']
    for i, grp in enumerate([0, 1]):
        s = data[data[treatment_col] == grp]
        w = s[weight_col].values if weight_col else None
        kmf = KaplanMeierFitter()
        kmf.fit(s[time_col], event_observed=s[event_col], weights=w, label=labels[i])
        kmf.plot_survival_function(ax=ax, ci_show=True, color=colors[i])
        med = kmf.median_survival_time_
        print(f"{labels[i]}: median = {med:.1f}d" if not np.isinf(med) else f"{labels[i]}: median not reached")
    t, c = data[data[treatment_col]==1], data[data[treatment_col]==0]
    lr = logrank_test(t[time_col], c[time_col], event_observed_A=t[event_col],
                     event_observed_B=c[event_col],
                     weight_A=t[weight_col] if weight_col else None,
                     weight_B=c[weight_col] if weight_col else None)
    print(f"\nWeighted logrank: p = {lr.p_value:.6f}")
    ax.set_xlabel('Days'); ax.set_ylabel('Survival'); ax.set_title('Weighted KM Curves')
    ax.set_xlim(0, max_time); ax.legend(); plt.tight_layout(); plt.show()
    return lr.p_value

weighted_km_curves(df_weighted, weight_col='ipw')
```

### 7.2 Weighted Cox Proportional Hazards

```python
def weighted_cox_model(data, time_col='time_to_event', event_col='event',
                      treatment_col='treatment', weight_col='ipw',
                      covariates=None, robust_se=True):
    """Weighted Cox PH with robust sandwich SEs."""
    if covariates is None:
        covariates = []
    cox = data[[time_col, event_col, treatment_col, weight_col] + covariates].copy()
    cox = cox.rename(columns={time_col: 'duration', event_col: 'event',
                              weight_col: 'weights', treatment_col: 'treatment'})
    cph = CoxPHFitter(penalizer=0.01)
    formula = 'treatment' + (' + ' + ' + '.join(covariates) if covariates else '')
    cph.fit(cox, duration_col='duration', event_col='event',
           weights_col='weights', robust=robust_se, formula=formula)
    hr = np.exp(cph.params_['treatment'])
    ci = np.exp(cph.confidence_intervals_.loc['treatment'])
    p = cph.summary.loc['treatment', 'p']
    print(f"Treatment HR: {hr:.4f} [{ci.iloc[0]:.4f}, {ci.iloc[1]:.4f}], p={p:.6f}")
    print(cph.summary[['coef', 'se(coef)', 'HR', 'p']])
    ph = proportional_hazard_test(cph, cox, time_transform='rank')
    print(f"\nSchoenfeld PH test:\n{ph.summary[['test_statistic', 'p']]}")
    return cph

cph = weighted_cox_model(df_weighted, weight_col='ipw_stabilized', covariates=['age', 'charlson_score'])
```

### 7.3 Restricted Mean Survival Time (RMST)

```python
def rmst_difference(data, time_col='time_to_event', event_col='event',
                   treatment_col='treatment', weight_col='ipw', tau=None):
    """
    RMST: area under survival curve up to tau. Valid even if PH assumption fails.
    """
    if tau is None:
        tau = data[time_col].max()
    rmst = {}
    fig, ax = plt.subplots(figsize=(10, 7))
    for grp, label, color in [(0, 'Control', '#1f77b4'), (1, 'Treated', '#d62728')]:
        s = data[data[treatment_col] == grp]
        w = s[weight_col].values if weight_col else None
        kmf = KaplanMeierFitter()
        kmf.fit(s[time_col], event_observed=s[event_col], weights=w, label=label)
        surv = kmf.survival_function_at_times(np.arange(0, tau+1)).values
        rmst[grp] = np.trapz(surv, dx=1)
        kmf.plot_survival_function(ax=ax, ci_show=False, color=color)
        tv = kmf.survival_function_.index.values
        sv = kmf.survival_function_.iloc[:, 0].values
        ax.fill_between(tv, sv, alpha=0.2, color=color)
        print(f"{label}: RMST({tau}) = {rmst[grp]:.1f} days")
    ax.axvline(tau, color='black', ls='--', alpha=0.5, label=f'tau={tau}')
    ax.set_xlabel('Days'); ax.set_title(f'RMST (tau={tau})'); ax.legend()
    plt.tight_layout(); plt.show()
    print(f"RMST difference: {rmst[1]-rmst[0]:.1f} days")
    print(f"RMST ratio: {rmst[1]/rmst[0]:.4f}")
    return {'rmst_diff': rmst[1]-rmst[0]}
```

---

## 8. Sensitivity Analysis

### 8.1 E-values

```python
def evalue(rr, ci_lower=None, ci_upper=None):
    """
    E-value (VanderWeele & Ding 2017): minimum strength of association an unmeasured
    confounder needs with BOTH treatment and outcome to explain away the observed effect.
    Formula: E = RR + sqrt(RR * (RR - 1)) where RR >= 1.
    """
    pt = rr if rr >= 1 else 1/rr
    e = pt + np.sqrt(pt * (pt - 1))
    print(f"E-value (point): {e:.3f}")
    if ci_lower is not None and ci_upper is not None:
        ci_b = ci_lower if rr >= 1 else 1/ci_upper
        e_ci = ci_b + np.sqrt(ci_b*(ci_b-1)) if ci_b >= 1 else 1.0
        print(f"E-value (CI bound): {e_ci:.3f}")
        return {'evalue_point': e, 'evalue_ci': e_ci}
    return {'evalue_point': e}

# E-value of ~2.2 means unmeasured confounder needs RR >= 2.2 with both treatment and outcome
evalue(rr=0.72, ci_lower=0.55, ci_upper=0.94)
```

### 8.2 Tipping Point Analysis

```python
def tipping_point(data, outcome_col, treatment_col='treatment', weight_col='ipw',
                  strength_range=(1.0, 5.0), prevalence_range=(0.05, 0.5), n_grid=20):
    """
    Vary strength (RR) and prevalence of a hypothetical unmeasured confounder
    to find where the treatment effect crosses null.
    """
    t, c = data[data[treatment_col]==1], data[data[treatment_col]==0]
    observed_rd = np.average(t[outcome_col], weights=t[weight_col].values) - np.average(c[outcome_col], weights=c[weight_col].values)
    strengths = np.linspace(*strength_range, n_grid)
    prevalences = np.linspace(*prevalence_range, n_grid)
    results = []
    for s in strengths:
        for p in prevalences:
            adj_rd = observed_rd - p * (s - 1)
            results.append({'strength': s, 'prevalence': p, 'adjusted_rd': adj_rd, 'null': abs(adj_rd) < 0.001})
    tip = pd.DataFrame(results)
    pivot = tip.pivot(index='prevalence', columns='strength', values='adjusted_rd')
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(pivot, cmap='RdBu_r', center=0, ax=ax, cbar_kws={'label': 'Adjusted RD'})
    ax.set_xlabel('Confounder-Outcome RR'); ax.set_ylabel('Confounder Prevalence')
    ax.set_title('Tipping Point Analysis'); plt.tight_layout(); plt.show()
    crossing = tip[tip['null']].sort_values('strength')
    if len(crossing) > 0:
        print(f"Effect crosses null at RR={crossing.iloc[0]['strength']:.2f}, prevalence={crossing.iloc[0]['prevalence']:.2f}")
    return tip
```

---

## 9. External Control Arms

### Integrating RWD as External Controls for Single-Arm Trials

```python
def build_external_control_arm(rwd_df, trial_df, covariates,
                               treatment_col='treatment',
                               weight_method='overlap', trim=0.1):
    """
    Build an external control arm from real-world data to augment a single-arm trial.
    1. Pool trial patients (treated) and RWD patients (potential controls)
    2. Estimate PS for being in the trial vs RWD
    3. Apply weighting (overlap preferred) and trim poorly overlapping observations
    4. Assess balance and return weighted external control arm
    """
    trial_df = trial_df.copy(); trial_df[treatment_col] = 1; trial_df['source'] = 'trial'
    rwd_df = rwd_df.copy(); rwd_df[treatment_col] = 0; rwd_df['source'] = 'rwd'
    pooled = pd.concat([trial_df, rwd_df], ignore_index=True)
    pooled = estimate_propensity_scores(pooled, covariates, treatment_col, method='logistic')
    pooled = trim_weights(pooled, method='crump')
    pooled = compute_ipw(pooled, treatment_col=treatment_col, weight_type=weight_method)
    cat_cols = [c for c in covariates if pooled[c].nunique() <= 2]
    balance_table(pooled, covariates, treatment_col=treatment_col, weight_col='ipw', categorical_cols=cat_cols)
    ext_ctrl = pooled[pooled['source'] == 'rwd'].copy()
    trial_arm = pooled[pooled['source'] == 'trial'].copy()
    print(f"\nExternal control: {len(ext_ctrl)} | Trial: {len(trial_arm)} | Method: {weight_method}")
    return pooled, ext_ctrl, trial_arm
```

---

## 10. Marginal Structural Models (Time-Varying Confounding)

When confounders are affected by prior treatment (e.g., CD4 count in HIV), standard
regression is biased. MSMs with time-varying IPW solve this.

```python
def estimate_msm_ipw(long_df, id_col, time_col, treatment_col, outcome_col,
                      covariates_static, covariates_time_varying, max_time=None):
    """
    Estimate a marginal structural model using time-varying stabilized IPW.
    Requires long-format data (one row per patient-time period) with treatment_lag column.
    """
    if max_time is None:
        max_time = long_df[time_col].max()
    df = long_df.copy().sort_values([id_col, time_col]).reset_index(drop=True)
    num_w = pd.Series(1.0, index=df.index)
    den_w = pd.Series(1.0, index=df.index)

    for t in range(1, max_time + 1):
        period = df[df[time_col] == t]
        if len(period) == 0:
            continue
        y = period[treatment_col].values
        # Numerator: treatment ~ prior treatment + static covariates
        X_num = period[[treatment_col + '_lag'] + covariates_static].fillna(0)
        # Denominator: treatment ~ prior treatment + ALL covariates
        X_den = period[[treatment_col + '_lag'] + covariates_static + covariates_time_varying].fillna(0)
        if 0 < y.sum() < len(y):
            m_num = LogisticRegression(max_iter=1000).fit(X_num, y)
            m_den = LogisticRegression(max_iter=1000).fit(X_den, y)
            ps_num = m_num.predict_proba(X_num)[:, 1]
            ps_den = m_den.predict_proba(X_den)[:, 1]
        else:
            ps_num = ps_den = np.full(len(period), 0.5)
        idx = period.index
        num_w.loc[idx] = np.where(y == 1, ps_num, 1 - ps_num)
        den_w.loc[idx] = np.where(y == 1, ps_den, 1 - ps_den)

    df['sw'] = df.groupby(id_col).apply(
        lambda g: np.cumprod(g['sw_numerator'].values / g['sw_denominator'].values)
        if 'sw_numerator' in g else np.cumprod(num_w.loc[g.index].values / den_w.loc[g.index].values)
    ).explode().values
    df['sw'] = df['sw'].clip(0, 10)

    # Fit weighted outcome model on final observation per patient
    final = df.groupby(id_col).last().reset_index()
    final['cum_treatment'] = df.groupby(id_col)[treatment_col].mean().values
    model = smf.wls(f"{outcome_col} ~ cum_treatment + " + " + ".join(covariates_static),
                   data=final, weights=final['sw']).fit()
    ate = model.params['cum_treatment']
    ci = model.conf_int().loc['cum_treatment']
    print(f"MSM causal effect: {ate:.4f} [{ci[0]:.4f}, {ci[1]:.4f}]")
    return model
```

---

## 11. Target Trial Emulation (Cloning, Censoring, Weighting)

```python
def target_trial_emulation(df, id_col, treatment_col, outcome_col,
                           grace_period=30, max_followup=730):
    """
    Emulate a target trial with two strategies:
    - Strategy A: Initiate treatment within grace period and continue
    - Strategy B: Do not initiate treatment within grace period
    Uses cloning, censoring, and IPW to estimate per-protocol effects.
    """
    clone_treated = df.copy(); clone_treated['strategy'] = 1
    clone_control = df.copy(); clone_control['strategy'] = 0
    pooled = pd.concat([clone_treated, clone_control], ignore_index=True)
    pooled['clone_id'] = pooled.index

    # Censoring: deviate from assigned strategy
    treated_within_grace = pooled[treatment_col] == 1
    pooled['censored'] = False
    pooled.loc[(pooled['strategy'] == 1) & (~treated_within_grace), 'censored'] = True
    pooled.loc[(pooled['strategy'] == 0) & treated_within_grace, 'censored'] = True

    # Follow-up and outcome
    pooled['followup'] = max_followup
    pooled.loc[pooled['censored'], 'followup'] = grace_period
    pooled['event'] = pooled[outcome_col]
    pooled.loc[pooled['censored'], 'event'] = 0

    # IPW for censoring
    censor_covs = [c for c in df.columns if c not in [id_col, treatment_col, outcome_col, 'strategy']]
    y_unc = (~pooled['censored']).astype(int)
    X_c = pooled[censor_covs].fillna(0)
    if 0 < y_unc.sum() < len(y_unc):
        cm = LogisticRegression(max_iter=1000).fit(X_c, y_unc)
        p_unc = cm.predict_proba(X_c)[:, 1].clip(0.01, 0.99)
        pooled['ipw_censor'] = np.where(pooled['censored'], 0, 1/p_unc)
    else:
        pooled['ipw_censor'] = 1.0

    uncensored = pooled[~pooled['censored']].copy()
    print(f"Cloned: {len(pooled)} (from {len(df)})")
    print(f"  Strategy A: {(pooled['strategy']==1).sum()} ({pooled[pooled['strategy']==1]['censored'].sum()} censored)")
    print(f"  Strategy B: {(pooled['strategy']==0).sum()} ({pooled[pooled['strategy']==0]['censored'].sum()} censored)")
    print(f"  Uncensored for analysis: {len(uncensored)}")
    return pooled
```

---

## 12. Propensity Score Stratification

```python
def ps_stratification(df, covariates, treatment_col='treatment',
                      ps_col='propensity_score', outcome_col=None,
                      n_strata=5, outcome_type='continuous'):
    """
    PS stratification (quintiles): estimate effect within strata and pool.
    """
    df = df.copy()
    df['ps_stratum'] = pd.qcut(df[ps_col], n_strata, labels=False)
    for s in range(n_strata):
        sd = df[df['ps_stratum'] == s]
        print(f"Stratum {s+1} (n={len(sd)}, PS [{sd[ps_col].min():.3f}, {sd[ps_col].max():.3f}]):")
        for cov in covariates[:5]:
            smd = compute_smd(sd, cov, treatment_col)
            print(f"  {cov}: SMD={abs(smd):.4f} {'OK' if abs(smd)<0.1 else 'IMBALANCED'}")
    if outcome_col:
        effects = []
        for s in range(n_strata):
            sd = df[df['ps_stratum'] == s]
            t, c = sd[sd[treatment_col]==1], sd[sd[treatment_col]==0]
            if outcome_type == 'continuous':
                eff = t[outcome_col].mean() - c[outcome_col].mean()
            else:
                eff = t[outcome_col].mean() - c[outcome_col].mean()
            w = len(sd) / len(df)
            effects.append((s, eff, w))
        pooled = sum(e * w for _, e, w in effects)
        print(f"\nPooled effect (stratified): {pooled:.4f}")
        for s, e, w in effects:
            print(f"  Stratum {s+1}: effect={e:.4f}, weight={w:.3f}")
        return pooled
```

---

## 13. Reporting and Best Practices

### Baseline Characteristics Table

```python
def baseline_table(data, covariates, treatment_col='treatment',
                   categorical_cols=None, weight_col=None):
    """Produce Table 1: baseline characteristics by treatment group."""
    categorical_cols = categorical_cols or []
    rows = []
    for cov in covariates:
        t, c = data[data[treatment_col]==1], data[data[treatment_col]==0]
        if weight_col:
            wt, wc = t[weight_col].values, c[weight_col].values
            if cov in categorical_cols:
                mt = f"{np.average(t[cov], weights=wt)*100:.1f}%"
                mc = f"{np.average(c[cov], weights=wc)*100:.1f}%"
            else:
                mt = f"{np.average(t[cov], weights=wt):.2f} +/- {np.sqrt(np.average((t[cov]-np.average(t[cov], weights=wt))**2, weights=wt)):.2f}"
                mc = f"{np.average(c[cov], weights=wc):.2f} +/- {np.sqrt(np.average((c[cov]-np.average(c[cov], weights=wc))**2, weights=wc)):.2f}"
        else:
            if cov in categorical_cols:
                mt = f"{t[cov].mean()*100:.1f}%"
                mc = f"{c[cov].mean()*100:.1f}%"
            else:
                mt = f"{t[cov].mean():.2f} +/- {t[cov].std():.2f}"
                mc = f"{c[cov].mean():.2f} +/- {c[cov].std():.2f}"
        fn = compute_smd_categorical if cov in categorical_cols else compute_smd
        smd = abs(fn(data, cov, treatment_col, weight_col))
        rows.append({'Variable': cov, 'Treated': mt, 'Control': mc, 'SMD': f"{smd:.3f}"})
    return pd.DataFrame(rows)
```

### Reporting Checklist

1. State the target trial specification (PICO, eligibility, treatment strategies, outcomes, follow-up)
2. Report sample sizes at each stage (exclusions, matched/weighted N, effective sample size)
3. Present baseline characteristics table (Table 1) before and after adjustment
4. Report balance diagnostics: SMD for each covariate, love plot, proportion balanced
5. Report treatment effect with 95% CI for: risk difference, RR, OR (binary) or mean difference (continuous)
6. For time-to-event: HR from Cox model, KM curves, RMST difference, logrank p-value
7. Report E-value and tipping point analysis for unmeasured confounding
8. Specify PS model (method, covariates, AUC, calibration)
9. Report sensitivity analyses (weight truncation, alternative estimators, alternative covariate sets)
10. Discuss common support and potential for residual confounding

## References

- Austin PC. Balance diagnostics for comparing the distribution of baseline covariates between treatment groups in propensity-score matched samples. Stat Med. 2009. https://doi.org/10.1002/sim.3697
- VanderWeele TJ, Ding P. Sensitivity analysis in observational research: introducing the E-value. Ann Intern Med. 2017. https://doi.org/10.7326/M16-2607
- Hernan MA, Robins JM. Using big data to emulate a target trial when a randomized trial is not available. Am J Epidemiol. 2016. https://doi.org/10.1093/aje/kwv254
- Robins JM, Hernan MA, Brumback B. Marginal structural models and causal inference in epidemiology. Epidemiology. 2000. https://doi.org/10.1097/00001648-200009000-00011
- Crump RK et al. Dealing with limited overlap in estimation of average treatment effects. Biometrika. 2009. https://doi.org/10.1093/biomet/asn055
- Li F, Morgan KL, Zaslavsky AM. Balancing covariates via propensity score weighting. JASA. 2018. https://doi.org/10.1080/01621459.2016.1260466
- Stuart EA. Matching methods for causal inference: a review and a look forward. Stat Sci. 2010. https://doi.org/10.1214/09-STS313
