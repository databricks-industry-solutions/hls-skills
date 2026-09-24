# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,RWE Comparative Effectiveness — No Skills Baseline
# MAGIC %md
# MAGIC # RWE Comparative Effectiveness Study — Baseline (No Skills)
# MAGIC
# MAGIC This notebook implements the 4 benchmark tasks from `evalset.json` using general statistical knowledge, without specialized RWE skill guidance.
# MAGIC
# MAGIC 1. **rwe-001** (easy): Compare mortality between treated/untreated; determine if confounder adjustment is needed
# MAGIC 2. **rwe-002** (hard): Estimate the causal effect of treatment on mortality
# MAGIC 3. **rwe-003** (hard): Compare time-to-event outcomes between treatment groups
# MAGIC 4. **rwe-004** (edge): Target trial emulation for treatment initiation effect

# COMMAND ----------

# DBTITLE 1,Install Dependencies
# MAGIC %pip install scikit-learn statsmodels lifelines matplotlib seaborn --quiet

# COMMAND ----------

# DBTITLE 1,Imports and Configuration
import pandas as pd
import numpy as np
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics import roc_auc_score
import statsmodels.api as sm
import statsmodels.formula.api as smf
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.statistics import logrank_test
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = '/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy'

# COMMAND ----------

# DBTITLE 1,Task rwe-001
# MAGIC %md
# MAGIC ---
# MAGIC ## Task rwe-001: Compare Mortality Between Treated and Untreated Groups
# MAGIC
# MAGIC **Query**: Using the observational data at `rwe_cohort.csv`, compare the mortality between treated and untreated groups. Determine if you need confounder adjustment.

# COMMAND ----------

# DBTITLE 1,rwe-001: Crude Comparison & Confounding Assessment
# ── Task rwe-001: Compare mortality & assess need for confounding adjustment ──

df = pd.read_csv(f"{DATA_DIR}/rwe_cohort.csv")
print(f"Dataset: {df.shape[0]} patients, {df.shape[1]} columns")
print(f"Columns: {df.columns.tolist()}")
display(df.head())

# Separate groups
treated = df[df['treatment'] == 1]
control = df[df['treatment'] == 0]
print(f"\nTreated: n={len(treated)} ({len(treated)/len(df):.1%})")
print(f"Control: n={len(control)} ({len(control)/len(df):.1%})")

# ── Crude mortality comparison ──
mort_t = treated['mortality'].mean()
mort_c = control['mortality'].mean()

contingency = pd.crosstab(df['treatment'], df['mortality'])
chi2, p_val, dof, expected = stats.chi2_contingency(contingency)

# Crude OR
a, b = contingency.loc[1, 1], contingency.loc[1, 0]
c, d = contingency.loc[0, 1], contingency.loc[0, 0]
crude_or = (a * d) / (b * c)
se_log_or = np.sqrt(1/a + 1/b + 1/c + 1/d)
ci_lo = np.exp(np.log(crude_or) - 1.96 * se_log_or)
ci_hi = np.exp(np.log(crude_or) + 1.96 * se_log_or)

print(f"\n--- Crude (Unadjusted) Mortality Comparison ---")
print(f"  Treated mortality:  {mort_t:.4f} ({int(a)}/{len(treated)})")
print(f"  Control mortality:  {mort_c:.4f} ({int(c)}/{len(control)})")
print(f"  Crude odds ratio:   {crude_or:.4f} [95% CI: {ci_lo:.4f}, {ci_hi:.4f}]")
print(f"  Chi-square p-value: {p_val:.6f}")
print(f"  Direction: {'Treatment appears HARMFUL (OR > 1)' if crude_or > 1 else 'Treatment appears PROTECTIVE (OR < 1)'}")

# ── Baseline covariate comparison ──
exclude_cols = ['treatment', 'mortality', 'time_to_event', 'event', 'patient_id']
covariates = [c for c in df.columns if c not in exclude_cols]

print(f"\n--- Baseline Covariate Balance ---")
print(f"{'Covariate':<25} {'Treated':>10} {'Control':>10} {'SMD':>8} {'p-value':>10}")
print('-' * 65)

imbalanced_covs = []
for col in covariates:
    t_mean = treated[col].mean()
    c_mean = control[col].mean()
    pooled_sd = np.sqrt((treated[col].var() + control[col].var()) / 2)
    smd = abs(t_mean - c_mean) / pooled_sd if pooled_sd > 0 else 0
    _, p = stats.ttest_ind(treated[col].dropna(), control[col].dropna())
    flag = " ***" if smd > 0.1 else ""
    print(f"  {col:<23} {t_mean:>10.3f} {c_mean:>10.3f} {smd:>8.4f} {p:>10.4f}{flag}")
    if smd > 0.1:
        imbalanced_covs.append(col)

print(f"\nImbalanced covariates (SMD > 0.1): {len(imbalanced_covs)}/{len(covariates)}")
if imbalanced_covs:
    print(f"  Imbalanced: {', '.join(imbalanced_covs)}")
    print(f"\n>>> CONFOUNDER ADJUSTMENT IS NEEDED.")
    print(f">>> The crude OR ({crude_or:.4f}) is likely biased due to baseline imbalances.")
else:
    print(f"\n>>> No significant confounding detected.")

# COMMAND ----------

# DBTITLE 1,Task rwe-002
# MAGIC %md
# MAGIC ---
# MAGIC ## Task rwe-002: Estimate Causal Effect of Treatment on Mortality
# MAGIC
# MAGIC **Query**: Using the cohort data at `rwe_cohort.csv`, estimate the causal effect of treatment on mortality.

# COMMAND ----------

# DBTITLE 1,rwe-002: Causal Effect Estimation
# ── Task rwe-002: Estimate causal effect of treatment on mortality ────────────

df = pd.read_csv(f"{DATA_DIR}/rwe_cohort.csv")
exclude_cols = ['treatment', 'mortality', 'time_to_event', 'event', 'patient_id']
covariates = [c for c in df.columns if c not in exclude_cols]
print(f"Covariates for PS model: {covariates}")

# ── Step 1: Propensity Score Estimation ──
X = df[covariates].fillna(df[covariates].median())
y = df['treatment'].values
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

ps_model = LogisticRegression(max_iter=2000, C=1.0, solver='lbfgs')
ps_model.fit(X_scaled, y)
df['ps'] = ps_model.predict_proba(X_scaled)[:, 1]
df['ps'] = df['ps'].clip(0.01, 0.99)

print(f"PS model AUC: {roc_auc_score(y, df['ps']):.4f}")
print(f"PS range: [{df['ps'].min():.4f}, {df['ps'].max():.4f}]")

# PS overlap plot
fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(df[df['treatment']==0]['ps'], bins=50, alpha=0.6, label='Control', color='#1f77b4', density=True)
ax.hist(df[df['treatment']==1]['ps'], bins=50, alpha=0.6, label='Treated', color='#d62728', density=True)
ax.set_xlabel('Propensity Score')
ax.set_ylabel('Density')
ax.set_title('Propensity Score Distribution by Treatment Group')
ax.legend()
plt.tight_layout()
plt.show()

# ── Step 2: PS Matching (1:1 nearest neighbor on logit-PS) ──
treated_idx = df[df['treatment']==1].index
control_idx = df[df['treatment']==0].index

df['logit_ps'] = np.log(df['ps'] / (1 - df['ps']))
caliper = 0.2 * df['logit_ps'].std()

nn = NearestNeighbors(n_neighbors=1, metric='euclidean')
nn.fit(df.loc[control_idx, ['logit_ps']])
distances, indices = nn.kneighbors(df.loc[treated_idx, ['logit_ps']])

within_caliper = distances.flatten() <= caliper
matched_treated = df.loc[treated_idx[within_caliper]]
matched_control = df.loc[control_idx[indices[within_caliper].flatten()]]
matched_df = pd.concat([matched_treated, matched_control])

print(f"\nPS Matching: {within_caliper.sum()}/{len(treated_idx)} treated matched (caliper={caliper:.3f})")
print(f"Matched sample: {len(matched_df)} patients")

# Matched OR
mt = matched_treated['mortality'].mean()
mc = matched_control['mortality'].mean()
if 0 < mt < 1 and 0 < mc < 1:
    matched_or = (mt/(1-mt)) / (mc/(1-mc))
    print(f"\n--- PS-Matched Results ---")
    print(f"  Treated mortality: {mt:.4f}")
    print(f"  Control mortality: {mc:.4f}")
    print(f"  Matched OR: {matched_or:.4f}")
else:
    matched_or = np.nan
    print(f"Cannot compute matched OR (boundary proportions)")

# ── Step 3: IPW Estimation (ATE weights) ──
df['ipw'] = np.where(df['treatment']==1, 1/df['ps'], 1/(1-df['ps']))
# Trim extreme weights at 1st/99th percentile
p1, p99 = np.percentile(df['ipw'], [1, 99])
df['ipw'] = df['ipw'].clip(p1, p99)

wt = df[df['treatment']==1]
wc = df[df['treatment']==0]
ipw_mort_t = np.average(wt['mortality'], weights=wt['ipw'])
ipw_mort_c = np.average(wc['mortality'], weights=wc['ipw'])
ipw_rd = ipw_mort_t - ipw_mort_c
if 0 < ipw_mort_t < 1 and 0 < ipw_mort_c < 1:
    ipw_or = (ipw_mort_t/(1-ipw_mort_t)) / (ipw_mort_c/(1-ipw_mort_c))
else:
    ipw_or = np.nan

print(f"\n--- IPW Results ---")
print(f"  Treated mortality (weighted): {ipw_mort_t:.4f}")
print(f"  Control mortality (weighted): {ipw_mort_c:.4f}")
print(f"  Risk Difference: {ipw_rd:.4f}")
print(f"  IPW Odds Ratio: {ipw_or:.4f}")

# ── Step 4: Adjusted Logistic Regression ──
formula = "mortality ~ treatment + " + " + ".join(covariates)
adj_model = smf.logit(formula, data=df).fit(disp=0)
adj_or = np.exp(adj_model.params['treatment'])
adj_ci = np.exp(adj_model.conf_int().loc['treatment'])
adj_p = adj_model.pvalues['treatment']

print(f"\n--- Adjusted Logistic Regression ---")
print(f"  Adjusted OR: {adj_or:.4f} [95% CI: {adj_ci.iloc[0]:.4f}, {adj_ci.iloc[1]:.4f}]")
print(f"  p-value: {adj_p:.6f}")

# ── Summary ──
crude_mort_t = df[df['treatment']==1]['mortality'].mean()
crude_mort_c = df[df['treatment']==0]['mortality'].mean()
crude_or = (crude_mort_t/(1-crude_mort_t)) / (crude_mort_c/(1-crude_mort_c))

print(f"\n{'='*60}")
print(f"SUMMARY OF CAUSAL EFFECT ESTIMATES")
print(f"{'='*60}")
print(f"{'Method':<30} {'OR':>8} {'Direction':>15}")
print('-'*55)
for name, val in [('Crude (unadjusted)', crude_or), ('PS-Matched', matched_or), ('IPW', ipw_or), ('Adjusted Regression', adj_or)]:
    direction = 'Protective' if val < 1 else 'Harmful' if val > 1 else 'Null'
    print(f"  {name:<28} {val:>8.4f} {direction:>15}")
print(f"\nConclusion: After adjusting for confounders, treatment appears {'PROTECTIVE' if adj_or < 1 else 'HARMFUL'}.")

# COMMAND ----------

# DBTITLE 1,Task rwe-003
# MAGIC %md
# MAGIC ---
# MAGIC ## Task rwe-003: Compare Time-to-Event Outcomes Between Treatment Groups
# MAGIC
# MAGIC **Query**: Using the observational data at `rwe_survival.csv`, compare time-to-event outcomes between treatment groups.

# COMMAND ----------

# DBTITLE 1,rwe-003: Time-to-Event Analysis
# ── Task rwe-003: Compare time-to-event outcomes ─────────────────────────────

df_surv = pd.read_csv(f"{DATA_DIR}/rwe_survival.csv")
print(f"Survival data: {df_surv.shape[0]} patients, {df_surv.shape[1]} columns")
print(f"Columns: {df_surv.columns.tolist()}")
display(df_surv.head())

# Auto-detect key columns
time_col = next((c for c in df_surv.columns if 'time' in c.lower()), None)
event_col = next((c for c in df_surv.columns if c.lower() in ['event', 'status', 'censored']), None)
treatment_col = 'treatment'
exclude = [time_col, event_col, treatment_col, 'patient_id']
covariates = [c for c in df_surv.columns if c not in exclude and c is not None]

print(f"\nTime: {time_col}, Event: {event_col}, Treatment: {treatment_col}")
print(f"Event rate: {df_surv[event_col].mean():.3f}")
print(f"Covariates: {covariates}")

# ── Kaplan-Meier Curves ──
fig, ax = plt.subplots(figsize=(10, 7))
for grp, label, color in [(0, 'Control', '#1f77b4'), (1, 'Treated', '#d62728')]:
    subset = df_surv[df_surv[treatment_col] == grp]
    kmf = KaplanMeierFitter()
    kmf.fit(subset[time_col], event_observed=subset[event_col], label=label)
    kmf.plot_survival_function(ax=ax, ci_show=True, color=color)
    med = kmf.median_survival_time_
    if np.isinf(med):
        print(f"{label}: median survival not reached")
    else:
        print(f"{label}: median survival = {med:.1f}")

ax.set_xlabel('Time (days)')
ax.set_ylabel('Survival Probability')
ax.set_title('Kaplan-Meier Survival Curves by Treatment Group')
ax.legend()
plt.tight_layout()
plt.show()

# ── Log-Rank Test ──
t_grp = df_surv[df_surv[treatment_col] == 1]
c_grp = df_surv[df_surv[treatment_col] == 0]
lr = logrank_test(t_grp[time_col], c_grp[time_col],
                  event_observed_A=t_grp[event_col],
                  event_observed_B=c_grp[event_col])
print(f"\nLog-rank test: statistic={lr.test_statistic:.4f}, p={lr.p_value:.6f}")

# ── Unadjusted Cox PH Model ──
print(f"\n--- Unadjusted Cox PH Model ---")
cox_unadj = CoxPHFitter()
cox_unadj_df = df_surv[[time_col, event_col, treatment_col]].dropna()
cox_unadj.fit(cox_unadj_df, duration_col=time_col, event_col=event_col)
hr_unadj = np.exp(cox_unadj.params_[treatment_col])
ci_unadj = np.exp(cox_unadj.confidence_intervals_.loc[treatment_col])
p_unadj = cox_unadj.summary.loc[treatment_col, 'p']
print(f"  Unadjusted HR: {hr_unadj:.4f} [{ci_unadj.iloc[0]:.4f}, {ci_unadj.iloc[1]:.4f}], p={p_unadj:.6f}")

# ── Adjusted Cox PH Model ──
print(f"\n--- Adjusted Cox PH Model ---")
cox_adj_df = df_surv[[time_col, event_col, treatment_col] + covariates].dropna()
cph = CoxPHFitter(penalizer=0.01)
cph.fit(cox_adj_df, duration_col=time_col, event_col=event_col)
cph.print_summary(columns=['coef', 'exp(coef)', 'se(coef)', 'p'])

hr_adj = np.exp(cph.params_[treatment_col])
ci_adj = np.exp(cph.confidence_intervals_.loc[treatment_col])
p_adj = cph.summary.loc[treatment_col, 'p']
print(f"\nTreatment HR (adjusted): {hr_adj:.4f} [{ci_adj.iloc[0]:.4f}, {ci_adj.iloc[1]:.4f}], p={p_adj:.6f}")
print(f"Interpretation: Treatment is {'PROTECTIVE' if hr_adj < 1 else 'HARMFUL'} after covariate adjustment.")

# ── Summary ──
print(f"\n{'='*60}")
print(f"TIME-TO-EVENT SUMMARY")
print(f"{'='*60}")
print(f"Log-rank test p-value: {lr.p_value:.6f}")
print(f"Unadjusted HR: {hr_unadj:.4f} [{ci_unadj.iloc[0]:.4f}, {ci_unadj.iloc[1]:.4f}]")
print(f"Adjusted HR:   {hr_adj:.4f} [{ci_adj.iloc[0]:.4f}, {ci_adj.iloc[1]:.4f}]")
print(f"\nNote: Unadjusted analysis may be confounded. The adjusted Cox model")
print(f"controls for observed covariates but does not use PS weighting.")

# COMMAND ----------

# DBTITLE 1,Task rwe-004
# MAGIC %md
# MAGIC ---
# MAGIC ## Task rwe-004: Target Trial Emulation
# MAGIC
# MAGIC **Query**: Using the observational data at `rwe_tte.csv`, estimate the causal effect of initiating treatment on the outcome using a target trial emulation design.

# COMMAND ----------

# DBTITLE 1,rwe-004: Target Trial Emulation
# ── Task rwe-004: Target Trial Emulation ──────────────────────────────────────

df_tte = pd.read_csv(f"{DATA_DIR}/rwe_tte.csv")
print(f"Target trial data: {df_tte.shape[0]} patients, {df_tte.shape[1]} columns")
print(f"Columns: {df_tte.columns.tolist()}")
display(df_tte.head())

# Explore data structure
for col in df_tte.columns:
    if df_tte[col].dtype == 'object':
        print(f"\n{col} (string): {dict(df_tte[col].value_counts().head(5))}")
    elif df_tte[col].nunique() <= 10:
        print(f"\n{col} (categorical): {dict(df_tte[col].value_counts())}")
    else:
        print(f"\n{col} (continuous): min={df_tte[col].min():.2f}, max={df_tte[col].max():.2f}, mean={df_tte[col].mean():.2f}")

# ── Identify key columns ──
time_col = next((c for c in df_tte.columns if 'time' in c.lower() and 'treat' not in c.lower()), 
                next((c for c in df_tte.columns if 'follow' in c.lower() or 'duration' in c.lower()), None))
event_col = next((c for c in df_tte.columns if c.lower() in ['event', 'outcome', 'status', 'death']), None)
treat_col = next((c for c in df_tte.columns if 'treat' in c.lower()), None)

# Look for treatment initiation time if present
treat_time_col = next((c for c in df_tte.columns if 'treat' in c.lower() and 'time' in c.lower()), None)

print(f"\nDetected columns:")
print(f"  Time: {time_col}")
print(f"  Event: {event_col}")
print(f"  Treatment: {treat_col}")
print(f"  Treatment time: {treat_time_col}")

# Exclude outcome, time, treatment, ID, and date columns from covariates
exclude = [c for c in [time_col, event_col, treat_col, treat_time_col, 'patient_id',
           'mortality', 'followup_days', 'index_date', 'treatment_date', 'outcome_date'] if c is not None]
covariates = [c for c in df_tte.columns if c not in exclude and df_tte[c].dtype != 'object']
print(f"  Covariates: {covariates}")

# COMMAND ----------

# DBTITLE 1,rwe-004: Target Trial Emulation Analysis
# ── Target Trial Emulation: Intention-to-Treat Analysis ──────────────────────
# Target trial emulation framework:
#   1. Eligibility: all patients at time zero (baseline)
#   2. Treatment strategies: initiate treatment vs. no treatment
#   3. Assignment: observational (address via PS weighting)
#   4. Follow-up: from time zero to outcome or censoring
#   5. Outcome: event of interest

# ── Step 1: Define treatment strategies at baseline ──
# If treatment_time is available, classify initiation vs non-initiation
if treat_time_col is not None:
    # Patients who initiated treatment early (within a grace period) vs. never/late initiators
    grace_period = df_tte[treat_time_col].quantile(0.25) if df_tte[treat_time_col].max() > 0 else 0
    df_tte['initiated'] = ((df_tte[treat_col] == 1) & 
                           (df_tte[treat_time_col] <= max(grace_period, 1))).astype(int)
    print(f"Grace period for treatment initiation: {grace_period:.1f}")
    print(f"Initiated: {df_tte['initiated'].sum()}, Not initiated: {(1-df_tte['initiated']).sum()}")
    strategy_col = 'initiated'
else:
    # Without treatment timing, use treatment assignment as the strategy
    strategy_col = treat_col
    print(f"No treatment timing column found — using {treat_col} as strategy indicator")

# ── Step 2: Propensity score for treatment initiation ──
X = df_tte[covariates].fillna(df_tte[covariates].median())
y = df_tte[strategy_col].values

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

ps_model = LogisticRegression(max_iter=2000, C=1.0, solver='lbfgs')
ps_model.fit(X_scaled, y)
df_tte['ps'] = ps_model.predict_proba(X_scaled)[:, 1].clip(0.01, 0.99)
print(f"\nPS model AUC: {roc_auc_score(y, df_tte['ps']):.4f}")

# ── Step 3: IPW weights ──
df_tte['ipw'] = np.where(df_tte[strategy_col]==1, 1/df_tte['ps'], 1/(1-df_tte['ps']))
# Stabilize weights
p_treat = df_tte[strategy_col].mean()
df_tte['ipw_stab'] = np.where(df_tte[strategy_col]==1, p_treat/df_tte['ps'], (1-p_treat)/(1-df_tte['ps']))
# Trim
for w_col in ['ipw', 'ipw_stab']:
    lo, hi = np.percentile(df_tte[w_col], [1, 99])
    df_tte[w_col] = df_tte[w_col].clip(lo, hi)
print(f"Stabilized weight mean: {df_tte['ipw_stab'].mean():.3f}, SD: {df_tte['ipw_stab'].std():.3f}")

# ── Step 4: Weighted outcome analysis ──
if time_col and event_col:
    # Weighted KM curves
    fig, ax = plt.subplots(figsize=(10, 7))
    for grp, label, color in [(0, 'No initiation', '#1f77b4'), (1, 'Treatment initiation', '#d62728')]:
        subset = df_tte[df_tte[strategy_col] == grp]
        kmf = KaplanMeierFitter()
        kmf.fit(subset[time_col], event_observed=subset[event_col],
                weights=subset['ipw_stab'], label=label)
        kmf.plot_survival_function(ax=ax, ci_show=True, color=color)
        med = kmf.median_survival_time_
        print(f"{label}: median = {med:.1f}" if not np.isinf(med) else f"{label}: median not reached")

    ax.set_xlabel('Time (days)')
    ax.set_ylabel('Survival Probability')
    ax.set_title('Target Trial Emulation: IPW-Weighted Kaplan-Meier Curves')
    ax.legend()
    plt.tight_layout()
    plt.show()

    # Weighted log-rank test
    t_grp = df_tte[df_tte[strategy_col]==1]
    c_grp = df_tte[df_tte[strategy_col]==0]
    lr = logrank_test(t_grp[time_col], c_grp[time_col],
                      event_observed_A=t_grp[event_col], event_observed_B=c_grp[event_col],
                      weight_A=t_grp['ipw_stab'], weight_B=c_grp['ipw_stab'])
    print(f"\nWeighted log-rank: p={lr.p_value:.6f}")

    # Weighted Cox model
    cox_df = df_tte[[time_col, event_col, strategy_col, 'ipw_stab']].copy()
    cox_df = cox_df.rename(columns={time_col: 'T', event_col: 'E', strategy_col: 'treatment', 'ipw_stab': 'w'})
    cph = CoxPHFitter(penalizer=0.01)
    cph.fit(cox_df, duration_col='T', event_col='E', weights_col='w',
            robust=True, formula='treatment')
    hr = np.exp(cph.params_['treatment'])
    ci = np.exp(cph.confidence_intervals_.loc['treatment'])
    p_val = cph.summary.loc['treatment', 'p']

    print(f"\n--- IPW-Weighted Cox Model (Target Trial Emulation) ---")
    print(f"  Treatment initiation HR: {hr:.4f} [{ci.iloc[0]:.4f}, {ci.iloc[1]:.4f}], p={p_val:.6f}")
    print(f"  Interpretation: Treatment initiation is {'PROTECTIVE' if hr < 1 else 'HARMFUL'}")

    # Also run adjusted (unweighted) Cox for comparison
    cox_adj_df = df_tte[[time_col, event_col, strategy_col] + covariates].dropna()
    cph_adj = CoxPHFitter(penalizer=0.01)
    cph_adj.fit(cox_adj_df, duration_col=time_col, event_col=event_col)
    hr_adj = np.exp(cph_adj.params_[strategy_col])
    ci_adj = np.exp(cph_adj.confidence_intervals_.loc[strategy_col])
    
    print(f"\n--- Comparison ---")
    print(f"  IPW-weighted HR: {hr:.4f} [{ci.iloc[0]:.4f}, {ci.iloc[1]:.4f}]")
    print(f"  Covariate-adjusted HR: {hr_adj:.4f} [{ci_adj.iloc[0]:.4f}, {ci_adj.iloc[1]:.4f}]")
else:
    # Binary outcome analysis with IPW
    print("\nNo time-to-event columns detected. Using binary outcome analysis.")
    outcome_col = event_col or next((c for c in df_tte.columns if 'outcome' in c.lower() or 'mort' in c.lower()), None)
    if outcome_col:
        wt = df_tte[df_tte[strategy_col]==1]
        wc = df_tte[df_tte[strategy_col]==0]
        p1 = np.average(wt[outcome_col], weights=wt['ipw_stab'])
        p0 = np.average(wc[outcome_col], weights=wc['ipw_stab'])
        rd = p1 - p0
        rr = p1/p0 if p0 > 0 else np.inf
        print(f"  IPW risk in initiators: {p1:.4f}")
        print(f"  IPW risk in non-initiators: {p0:.4f}")
        print(f"  Risk difference: {rd:.4f}")
        print(f"  Risk ratio: {rr:.4f}")

print(f"\n{'='*60}")
print(f"TARGET TRIAL EMULATION SUMMARY")
print(f"{'='*60}")
print(f"Design: Emulated randomized trial using observational data")
print(f"Strategy: Treatment initiation vs. no treatment")
print(f"Confounding adjustment: Inverse probability weighting (stabilized)")
print(f"Note: This analysis assumes no unmeasured confounding and")
print(f"      correct model specification for the propensity score.")