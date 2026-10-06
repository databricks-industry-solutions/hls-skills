# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # RWE Cohort Study Analysis (With rwe-cohortstudy Skill)
# MAGIC
# MAGIC This notebook executes the four benchmark tasks from `evalset.json` using the `rwe-cohortstudy` skill methodology:
# MAGIC
# MAGIC 1. **rwe-001** — Compare mortality between treated and untreated groups; determine if confounder adjustment is needed
# MAGIC 2. **rwe-002** — Estimate the causal effect of treatment on mortality
# MAGIC 3. **rwe-003** — Compare time-to-event outcomes between treatment groups
# MAGIC 4. **rwe-004** — Estimate the causal effect of initiating treatment using a target trial emulation design
# MAGIC
# MAGIC The workflow follows the standard RWE pipeline: study design → cohort assembly → propensity score estimation → confounding adjustment → balance diagnostics → treatment effect estimation → sensitivity analysis.

# COMMAND ----------

# DBTITLE 1,Package Installation & Imports
# MAGIC %pip install scikit-learn statsmodels lifelines matplotlib seaborn --quiet
# MAGIC
# MAGIC import pandas as pd
# MAGIC import numpy as np
# MAGIC from sklearn.linear_model import LogisticRegression
# MAGIC from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
# MAGIC from sklearn.preprocessing import StandardScaler
# MAGIC from sklearn.model_selection import cross_val_predict
# MAGIC from sklearn.metrics import roc_auc_score, brier_score_loss
# MAGIC import statsmodels.api as sm
# MAGIC import statsmodels.formula.api as smf
# MAGIC from lifelines import KaplanMeierFitter, CoxPHFitter
# MAGIC from lifelines.statistics import logrank_test, proportional_hazard_test
# MAGIC import matplotlib.pyplot as plt
# MAGIC import seaborn as sns
# MAGIC import warnings
# MAGIC warnings.filterwarnings('ignore')
# MAGIC
# MAGIC print("All packages loaded.")

# COMMAND ----------

# DBTITLE 1,Shared Utility Functions
# ============================================================
# Propensity Score Estimation
# ============================================================
def estimate_propensity_scores(df, covariates, treatment_col='treatment',
                                method='logistic', cv_folds=5, random_state=42):
    """Estimate propensity scores via logistic regression or ML methods."""
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

# ============================================================
# Common Support Check
# ============================================================
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

# ============================================================
# Nearest-Neighbor Matching
# ============================================================
def nearest_neighbor_match(df, treatment_col='treatment', ps_col='propensity_score',
                            ratio=1, caliper=None, replace=False, random_state=42):
    """Nearest-neighbor matching on logit(PS)."""
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

# ============================================================
# Inverse Probability Weighting
# ============================================================
def compute_ipw(df, treatment_col='treatment', ps_col='propensity_score',
                weight_type='ate', trim_percent=None):
    """Compute inverse probability weights (ATE, ATT, ATU, or overlap)."""
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

def compute_stabilized_weights(df, treatment_col='treatment', ps_col='propensity_score'):
    """Stabilized IPW reduces weight variance by multiplying by marginal P(treatment)."""
    df = df.copy()
    ps, z = df[ps_col].values, df[treatment_col].values
    p = z.mean()
    df['ipw_stabilized'] = np.where(z == 1, p/ps, (1-p)/(1-ps))
    print(f"Stabilized weights: mean={df['ipw_stabilized'].mean():.3f}, SD={df['ipw_stabilized'].std():.3f}")
    return df

# ============================================================
# Balance Diagnostics
# ============================================================
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

def love_plot(data, covariates, treatment_col='treatment', weight_col=None,
              categorical_cols=None, title='Covariate Balance'):
    """Love plot: SMD before vs after adjustment."""
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

print("Utility functions defined.")

# COMMAND ----------

# DBTITLE 1,Treatment Effect & Sensitivity Functions
# ============================================================
# Treatment Effect Estimation
# ============================================================
def estimate_ate_continuous(data, outcome_col, treatment_col='treatment', weight_col='ipw'):
    """Weighted mean difference for continuous outcomes."""
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

def estimate_ate_binary(data, outcome_col, treatment_col='treatment', weight_col='ipw'):
    """Risk difference, RR, OR for binary outcomes with IPW."""
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

def doubly_robust(data, outcome_col, treatment_col='treatment', covariates=None,
                  ps_col='propensity_score', outcome_type='continuous', n_boot=500):
    """Doubly robust estimation: consistent if EITHER the PS model OR the outcome model is correct."""
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

# ============================================================
# Sensitivity Analysis
# ============================================================
def evalue(rr, ci_lower=None, ci_upper=None):
    """E-value: minimum strength of association an unmeasured confounder needs with BOTH treatment and outcome to explain away the observed effect."""
    pt = rr if rr >= 1 else 1/rr
    e = pt + np.sqrt(pt * (pt - 1))
    print(f"E-value (point): {e:.3f}")
    if ci_lower is not None and ci_upper is not None:
        ci_b = ci_lower if rr >= 1 else 1/ci_upper
        e_ci = ci_b + np.sqrt(ci_b*(ci_b-1)) if ci_b >= 1 else 1.0
        print(f"E-value (CI bound): {e_ci:.3f}")
        return {'evalue_point': e, 'evalue_ci': e_ci}
    return {'evalue_point': e}

def tipping_point(data, outcome_col, treatment_col='treatment', weight_col='ipw',
                  strength_range=(1.0, 5.0), prevalence_range=(0.05, 0.5), n_grid=20):
    """Vary strength (RR) and prevalence of a hypothetical unmeasured confounder to find where the treatment effect crosses null."""
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

print("Treatment effect and sensitivity functions defined.")

# COMMAND ----------

# DBTITLE 1,Survival & Target Trial Emulation Functions
# ============================================================
# Survival Analysis Functions
# ============================================================
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
        w = s[weight_col].values if weight_col and weight_col in s.columns else None
        kmf = KaplanMeierFitter()
        kmf.fit(s[time_col], event_observed=s[event_col], weights=w, label=labels[i])
        kmf.plot_survival_function(ax=ax, ci_show=True, color=colors[i])
        med = kmf.median_survival_time_
        print(f"{labels[i]}: median = {med:.1f}d" if not np.isinf(med) else f"{labels[i]}: median not reached")
    t_data, c_data = data[data[treatment_col]==1], data[data[treatment_col]==0]
    lr = logrank_test(t_data[time_col], c_data[time_col], event_observed_A=t_data[event_col],
                     event_observed_B=c_data[event_col],
                     weight_A=t_data[weight_col] if weight_col and weight_col in t_data.columns else None,
                     weight_B=c_data[weight_col] if weight_col and weight_col in c_data.columns else None)
    print(f"\nWeighted logrank: p = {lr.p_value:.6f}")
    ax.set_xlabel('Days'); ax.set_ylabel('Survival'); ax.set_title('Weighted KM Curves')
    ax.set_xlim(0, max_time); ax.legend(); plt.tight_layout(); plt.show()
    return lr.p_value

def weighted_cox_model(data, time_col='time_to_event', event_col='event',
                      treatment_col='treatment', weight_col='ipw',
                      covariates=None, robust_se=True):
    """Weighted Cox PH with robust sandwich SEs."""
    if covariates is None:
        covariates = []
    cols_needed = [time_col, event_col, treatment_col, weight_col] + covariates
    cox = data[cols_needed].copy()
    cox = cox.rename(columns={time_col: 'duration', event_col: 'event',
                              weight_col: 'weights', treatment_col: 'treatment'})
    cph = CoxPHFitter(penalizer=0.01)
    formula = 'treatment' + (' + ' + ' + '.join(covariates) if covariates else '')
    cph.fit(cox, duration_col='duration', event_col='event',
           weights_col='weights', robust=robust_se, formula=formula)
    hr = np.exp(cph.params_['treatment'])
    ci = np.exp(cph.confidence_intervals_.loc['treatment'])
    # Handle different lifelines column naming across versions
    summary_cols = cph.summary.columns.tolist()
    p_col = 'p' if 'p' in summary_cols else 'p-value'
    hr_col = 'HR' if 'HR' in summary_cols else 'exp(coef)'
    p = cph.summary.loc['treatment', p_col]
    print(f"Treatment HR: {hr:.4f} [{ci.iloc[0]:.4f}, {ci.iloc[1]:.4f}], p={p:.6f}")
    display_cols = [c for c in ['coef', 'se(coef)', hr_col, p_col] if c in summary_cols]
    print(cph.summary[display_cols])
    ph = proportional_hazard_test(cph, cox, time_transform='rank')
    print(f"\nSchoenfeld PH test:\n{ph.summary[['test_statistic', 'p']]}")
    return cph

def rmst_difference(data, time_col='time_to_event', event_col='event',
                   treatment_col='treatment', weight_col='ipw', tau=None):
    """RMST: area under survival curve up to tau. Valid even if PH assumption fails."""
    if tau is None:
        tau = data[time_col].max()
    rmst = {}
    fig, ax = plt.subplots(figsize=(10, 7))
    for grp, label, color in [(0, 'Control', '#1f77b4'), (1, 'Treated', '#d62728')]:
        s = data[data[treatment_col] == grp]
        w = s[weight_col].values if weight_col and weight_col in s.columns else None
        kmf = KaplanMeierFitter()
        kmf.fit(s[time_col], event_observed=s[event_col], weights=w, label=label)
        surv = kmf.survival_function_at_times(np.arange(0, int(tau)+1)).values
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

# ============================================================
# Target Trial Emulation
# ============================================================
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
    censor_covs = [c for c in df.columns if c not in [id_col, treatment_col, outcome_col, 'strategy']
                   and df[c].dtype in ['int64', 'float64', 'int32', 'float32', 'bool']]
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

print("Survival and target trial emulation functions defined.")

# COMMAND ----------

# DBTITLE 1,Task rwe-001: Compare Mortality & Assess Confounders
# MAGIC %md
# MAGIC ---
# MAGIC ## Task rwe-001: Compare mortality and assess confounder adjustment
# MAGIC
# MAGIC **Query**: *Using the observational data at `/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy/rwe_cohort.csv`, compare the mortality between treated and untreated groups. Determine if you need confounder adjustment.*
# MAGIC
# MAGIC **Approach**: Load the cohort data, inspect the schema, compute crude mortality by treatment group, then assess baseline covariate imbalance using standardized mean differences (SMD). If any SMD > 0.1, confounder adjustment is needed.

# COMMAND ----------

# DBTITLE 1,rwe-001: Load Data & Explore Schema
# --- Load the cohort dataset ---
cohort_path = "/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy/rwe_cohort.csv"
df_cohort = pd.read_csv(cohort_path)
print(f"Dataset shape: {df_cohort.shape}")
print(f"\nColumns and dtypes:")
print(df_cohort.dtypes)
print(f"\nFirst 5 rows:")
df_cohort.head()

# --- Auto-detect treatment and outcome columns ---
treatment_candidates = [c for c in df_cohort.columns if c.lower() in ['treatment', 'treated', 'group', 'exposure', 'drug', 'therapy']]
outcome_candidates = [c for c in df_cohort.columns if any(k in c.lower() for k in ['mortality', 'death', 'died', 'event', 'outcome', 'dead'])]

treatment_col = treatment_candidates[0] if treatment_candidates else 'treatment'
outcome_col = outcome_candidates[0] if outcome_candidates else 'mortality'
print(f"\nDetected treatment column: '{treatment_col}'")
print(f"Detected outcome column: '{outcome_col}'")
print(f"Treatment distribution: {df_cohort[treatment_col].value_counts().to_dict()}")
print(f"Outcome distribution: {df_cohort[outcome_col].value_counts().to_dict()}")

# COMMAND ----------

# DBTITLE 1,rwe-001: Crude Mortality Comparison
# --- Crude mortality comparison ---
treated = df_cohort[df_cohort[treatment_col] == 1]
control = df_cohort[df_cohort[treatment_col] == 0]

mortality_treated = treated[outcome_col].mean()
mortality_control = control[outcome_col].mean()
crude_rd = mortality_treated - mortality_control
crude_rr = mortality_treated / mortality_control if mortality_control > 0 else np.inf

print("=" * 60)
print("CRUDE MORTALITY COMPARISON (Unadjusted)")
print("=" * 60)
print(f"Treated (n={len(treated)}): mortality = {mortality_treated:.4f} ({mortality_treated*100:.1f}%)")
print(f"Control (n={len(control)}): mortality = {mortality_control:.4f} ({mortality_control*100:.1f}%)")
print(f"Risk difference: {crude_rd:.4f} ({crude_rd*100:.1f} percentage points)")
print(f"Risk ratio: {crude_rr:.4f}")

# Unadjusted logistic regression for p-value
import statsmodels.formula.api as smf
crude_model = smf.logit(f"{outcome_col} ~ {treatment_col}", data=df_cohort).fit(disp=0)
or_crude = np.exp(crude_model.params[treatment_col])
or_ci = np.exp(crude_model.conf_int().loc[treatment_col])
p_crude = crude_model.pvalues[treatment_col]
print(f"Odds ratio (crude): {or_crude:.4f} [{or_ci[0]:.4f}, {or_ci[1]:.4f}], p={p_crude:.6f}")

# COMMAND ----------

# DBTITLE 1,rwe-001: Confounder Assessment via SMDs
# --- Confounder assessment via SMDs ---
# Identify covariates (all columns except treatment, outcome, and ID-like columns)
exclude_cols = {treatment_col, outcome_col}
id_like = [c for c in df_cohort.columns if c.lower() in ['id', 'subject_id', 'patient_id', 'subject', 'patient', 'index_date']]
exclude_cols.update(id_like)
covariates_001 = [c for c in df_cohort.columns if c not in exclude_cols and df_cohort[c].dtype in ['int64', 'float64', 'int32', 'float32', 'bool']]

# Identify categorical (binary) covariates
categorical_covs = [c for c in covariates_001 if df_cohort[c].nunique() <= 2]
print(f"Covariates assessed: {covariates_001}")
print(f"Categorical (binary): {categorical_covs}")

# Compute SMDs for each covariate
print("\n" + "=" * 60)
print("CONFOUNDER ASSESSMENT: Standardized Mean Differences")
print("=" * 60)

smd_results = []
for cov in covariates_001:
    fn = compute_smd_categorical if cov in categorical_covs else compute_smd
    smd_val = abs(fn(df_cohort, cov, treatment_col))
    smd_results.append({'Covariate': cov, 'SMD': smd_val, 'Imbalanced': smd_val > 0.1})

smd_df = pd.DataFrame(smd_results).sort_values('SMD', ascending=False)
print(f"\n{'Covariate':<25} {'SMD':>10} {'Status':>12}")
print('-' * 50)
for _, r in smd_df.iterrows():
    status = 'IMBALANCED' if r['Imbalanced'] else 'balanced'
    print(f"{r['Covariate']:<25} {r['SMD']:>10.4f} {status:>12}")

n_imbalanced = smd_df['Imbalanced'].sum()
print(f"\nImbalanced covariates (SMD > 0.1): {n_imbalanced}/{len(smd_df)}")

if n_imbalanced > 0:
    print("\n>>> CONFOUNDER ADJUSTMENT IS NEEDED.")
    print(f">>> {n_imbalanced} covariate(s) show material imbalance (SMD > 0.1) between treatment groups.")
    print(">>> Crude comparison is biased; propensity score adjustment required.")
else:
    print("\n>>> No material imbalance detected. Crude comparison may be adequate.")
    print(">>> However, adjustment is still recommended as a sensitivity check.")

# Visualize SMDs
fig, ax = plt.subplots(figsize=(10, max(6, len(covariates_001)*0.4)))
y_pos = np.arange(len(smd_df))
ax.barh(y_pos, smd_df['SMD'].values, color=['#d62728' if x else '#1f77b4' for x in smd_df['Imbalanced']])
ax.axvline(0.1, color='black', ls='--', lw=1, label='SMD=0.1 threshold')
ax.set_yticks(y_pos); ax.set_yticklabels(smd_df['Covariate'].values)
ax.set_xlabel('Absolute SMD'); ax.set_title('Baseline Covariate Imbalance (Unadjusted)')
ax.legend(); plt.tight_layout(); plt.show()

# COMMAND ----------

# DBTITLE 1,Task rwe-002: Causal Effect Estimation
# MAGIC %md
# MAGIC ---
# MAGIC ## Task rwe-002: Estimate causal effect of treatment on mortality
# MAGIC
# MAGIC **Query**: *Using the cohort data at `/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy/rwe_cohort.csv`, estimate the causal effect of treatment on mortality.*
# MAGIC
# MAGIC **Approach**: Estimate propensity scores via logistic regression, compute inverse probability weights (ATE), verify covariate balance after weighting, then estimate the causal effect using doubly robust estimation. Perform E-value sensitivity analysis for unmeasured confounding.

# COMMAND ----------

# DBTITLE 1,rwe-002: PS Estimation & IPW
# --- Step 1: Propensity Score Estimation ---
print("=" * 60)
print("STEP 1: PROPENSITY SCORE ESTIMATION")
print("=" * 60)
df_ps = estimate_propensity_scores(df_cohort, covariates_001, treatment_col=treatment_col, method='logistic')

# --- Step 2: Common Support Check ---
print("\n" + "=" * 60)
print("STEP 2: COMMON SUPPORT CHECK")
print("=" * 60)
check_common_support(df_ps, treatment_col=treatment_col)

# --- Step 3: Compute IPW (ATE weights) ---
print("\n" + "=" * 60)
print("STEP 3: INVERSE PROBABILITY WEIGHTING (ATE)")
print("=" * 60)
df_weighted = compute_ipw(df_ps, treatment_col=treatment_col, weight_type='ate', trim_percent=1)
df_weighted = compute_stabilized_weights(df_weighted, treatment_col=treatment_col)

# COMMAND ----------

# DBTITLE 1,rwe-002: Balance Diagnostics
# --- Step 4: Balance Diagnostics ---
print("=" * 60)
print("STEP 4: BALANCE DIAGNOSTICS AFTER IPW")
print("=" * 60)
bal = balance_table(df_weighted, covariates_001, treatment_col=treatment_col,
                    weight_col='ipw', categorical_cols=categorical_covs)

# Love plot
love_plot(df_weighted, covariates_001, treatment_col=treatment_col,
          weight_col='ipw', categorical_cols=categorical_covs,
          title='Covariate Balance: Unadjusted vs IPW-Adjusted')

# Baseline table (weighted)
print("\nBaseline Characteristics Table (IPW-Weighted):")
bt = baseline_table(df_weighted, covariates_001, treatment_col=treatment_col,
                     categorical_cols=categorical_covs, weight_col='ipw')
print(bt.to_string(index=False))

# COMMAND ----------

# DBTITLE 1,rwe-002: Effect Estimation & Sensitivity
# --- Step 5: Treatment Effect Estimation ---
print("=" * 60)
print("STEP 5: TREATMENT EFFECT ESTIMATION")
print("=" * 60)

# 5a: IPW-weighted risk difference, RR, OR
print("\n--- 5a: IPW-Weighted Effect (Binary Outcome) ---")
effect_ipw = estimate_ate_binary(df_weighted, outcome_col, treatment_col=treatment_col, weight_col='ipw')

# 5b: G-computation (outcome regression standardization)
print("\n--- 5b: G-Computation ---")
effect_gcomp = g_computation(df_cohort, outcome_col, treatment_col=treatment_col,
                             covariates=covariates_001, outcome_type='binary', n_boot=300)

# 5c: Doubly Robust Estimation
print("\n--- 5c: Doubly Robust Estimation ---")
effect_dr = doubly_robust(df_ps, outcome_col, treatment_col=treatment_col,
                          covariates=covariates_001, ps_col='propensity_score',
                          outcome_type='binary', n_boot=300)

# --- Step 6: Sensitivity Analysis ---
print("\n" + "=" * 60)
print("STEP 6: SENSITIVITY ANALYSIS (Unmeasured Confounding)")
print("=" * 60)
print("\n--- E-Value ---")
rr = effect_ipw['rr']
evalue(rr=rr, ci_lower=None, ci_upper=None)

print("\n--- Tipping Point Analysis ---")
tip = tipping_point(df_weighted, outcome_col, treatment_col=treatment_col,
                    weight_col='ipw', n_grid=15)

print("\n" + "=" * 60)
print("SUMMARY: CAUSAL EFFECT OF TREATMENT ON MORTALITY")
print("=" * 60)
print(f"Crude RD:          {crude_rd:.4f} (from rwe-001)")
print(f"IPW-weighted RD:   {effect_ipw['rd']:.4f}")
print(f"IPW-weighted RR:   {effect_ipw['rr']:.4f}")
print(f"IPW-weighted OR:   {effect_ipw['or']:.4f}")
print(f"Doubly Robust ATE: {effect_dr['ate']:.4f} [{effect_dr['ci'][0]:.4f}, {effect_dr['ci'][1]:.4f}]")
print(f"\nConclusion: Treatment {'reduces' if effect_ipw['rd'] < 0 else 'increases'} mortality.")
print(f"The E-value indicates the minimum confounder strength needed to explain away the finding.")

# COMMAND ----------

# DBTITLE 1,Task rwe-003: Time-to-Event Comparison
# MAGIC %md
# MAGIC ---
# MAGIC ## Task rwe-003: Compare time-to-event outcomes between treatment groups
# MAGIC
# MAGIC **Query**: *Using the observational data at `/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy/rwe_survival.csv`, compare time-to-event outcomes between treatment groups.*
# MAGIC
# MAGIC **Approach**: Load the survival dataset, identify time and event columns, estimate propensity scores and compute IPW for confounding adjustment, then compare groups using weighted Kaplan-Meier curves with logrank test, weighted Cox proportional hazards model, and restricted mean survival time (RMST).

# COMMAND ----------

# DBTITLE 1,rwe-003: Load Survival Data & Explore
# --- Load the survival dataset ---
survival_path = "/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy/rwe_survival.csv"
df_surv = pd.read_csv(survival_path)
print(f"Dataset shape: {df_surv.shape}")
print(f"\nColumns and dtypes:")
print(df_surv.dtypes)
print(f"\nFirst 5 rows:")
print(df_surv.head())

# --- Auto-detect columns ---
treatment_col_s = [c for c in df_surv.columns if c.lower() in ['treatment', 'treated', 'group', 'exposure', 'drug', 'therapy']]
# Exact column name matches take priority over partial keyword matches
exact_time_names = ['time_to_event', 'tte', 'survival_time', 'follow_up_time', 'followup_time', 'time']
exact_event_names = ['event', 'death', 'died', 'mortality', 'status', 'outcome']
time_candidates = [c for c in df_surv.columns if c.lower() in exact_time_names]
if not time_candidates:
    time_candidates = [c for c in df_surv.columns if any(k in c.lower() for k in ['time', 'follow', 'duration', 'days', 'survival', 'tte', 'period'])]
event_candidates = [c for c in df_surv.columns if c.lower() in exact_event_names]
if not event_candidates:
    event_candidates = [c for c in df_surv.columns if any(k in c.lower() for k in ['event', 'death', 'died', 'mortality', 'outcome', 'dead', 'status', 'failure'])]

treatment_col_s = treatment_col_s[0] if treatment_col_s else 'treatment'
time_col_s = time_candidates[0] if time_candidates else 'time_to_event'
event_col_s = event_candidates[0] if event_candidates else 'event'

print(f"\nDetected treatment column: '{treatment_col_s}'")
print(f"Detected time column: '{time_col_s}'")
print(f"Detected event column: '{event_col_s}'")
print(f"\nTreatment distribution: {df_surv[treatment_col_s].value_counts().to_dict()}")
print(f"Event distribution: {df_surv[event_col_s].value_counts().to_dict()}")
print(f"Time range: [{df_surv[time_col_s].min():.1f}, {df_surv[time_col_s].max():.1f}]")

# COMMAND ----------

# DBTITLE 1,rwe-003: PS Estimation & IPW for Survival Data
# --- Identify covariates for PS adjustment ---
exclude_s = {treatment_col_s, time_col_s, event_col_s}
id_like_s = [c for c in df_surv.columns if c.lower() in ['id', 'subject_id', 'patient_id', 'subject', 'patient']]
exclude_s.update(id_like_s)
covariates_s = [c for c in df_surv.columns if c not in exclude_s and df_surv[c].dtype in ['int64', 'float64', 'int32', 'float32', 'bool']]
cat_covs_s = [c for c in covariates_s if df_surv[c].nunique() <= 2]
print(f"Covariates for adjustment: {covariates_s}")
print(f"Categorical (binary): {cat_covs_s}")

# --- Propensity score estimation and IPW ---
if len(covariates_s) > 0:
    df_surv_ps = estimate_propensity_scores(df_surv, covariates_s, treatment_col=treatment_col_s, method='logistic')
    df_surv_w = compute_ipw(df_surv_ps, treatment_col=treatment_col_s, weight_type='ate', trim_percent=1)
    df_surv_w = compute_stabilized_weights(df_surv_w, treatment_col=treatment_col_s)
    
    # Balance check
    balance_table(df_surv_w, covariates_s, treatment_col=treatment_col_s,
                  weight_col='ipw', categorical_cols=cat_covs_s)
    love_plot(df_surv_w, covariates_s, treatment_col=treatment_col_s,
              weight_col='ipw', categorical_cols=cat_covs_s,
              title='Survival Data: Covariate Balance (IPW)')
else:
    print("No covariates available for adjustment; using unweighted analysis.")
    df_surv_w = df_surv.copy()
    df_surv_w['ipw'] = 1.0
    df_surv_w['ipw_stabilized'] = 1.0

# COMMAND ----------

# DBTITLE 1,rwe-003: KM Curves, Cox PH, RMST
# --- Weighted Kaplan-Meier Curves with Logrank Test ---
print("=" * 60)
print("WEIGHTED KAPLAN-MEIER CURVES & LOGRANK TEST")
print("=" * 60)
p_logrank = weighted_km_curves(df_surv_w, time_col=time_col_s, event_col=event_col_s,
                               treatment_col=treatment_col_s, weight_col='ipw_stabilized')

# Also show unweighted KM for comparison
print("\n--- Unweighted KM for Comparison ---")
p_logrank_unadj = weighted_km_curves(df_surv_w, time_col=time_col_s, event_col=event_col_s,
                                     treatment_col=treatment_col_s, weight_col=None)

# --- Weighted Cox Proportional Hazards Model ---
print("\n" + "=" * 60)
print("WEIGHTED COX PROPORTIONAL HAZARDS MODEL")
print("=" * 60)
cox_covs = [c for c in covariates_s if c not in [time_col_s, event_col_s]][:5]  # top 5 covariates
cph = weighted_cox_model(df_surv_w, time_col=time_col_s, event_col=event_col_s,
                          treatment_col=treatment_col_s, weight_col='ipw_stabilized',
                          covariates=cox_covs)

# --- Restricted Mean Survival Time (RMST) ---
print("\n" + "=" * 60)
print("RESTRICTED MEAN SURVIVAL TIME (RMST)")
print("=" * 60)
tau = df_surv_w[time_col_s].quantile(0.9)  # use 90th percentile as truncation
tau = int(tau)
rmst_result = rmst_difference(df_surv_w, time_col=time_col_s, event_col=event_col_s,
                                treatment_col=treatment_col_s, weight_col='ipw_stabilized', tau=tau)

print("\n" + "=" * 60)
print("SUMMARY: TIME-TO-EVENT COMPARISON")
print("=" * 60)
print(f"Logrank p (weighted):   {p_logrank:.6f}")
print(f"Logrank p (unweighted): {p_logrank_unadj:.6f}")
print(f"RMST difference:        {rmst_result['rmst_diff']:.1f} days")
hr_val = np.exp(cph.params_['treatment'])
print(f"Hazard ratio (weighted): {hr_val:.4f}")
print(f"\nConclusion: Treatment {'improves' if hr_val < 1 else 'worsens'} survival (HR={hr_val:.4f}).")

# COMMAND ----------

# DBTITLE 1,Task rwe-004: Target Trial Emulation
# MAGIC %md
# MAGIC ---
# MAGIC ## Task rwe-004: Target Trial Emulation
# MAGIC
# MAGIC **Query**: *Using the observational data at `/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy/rwe_tte.csv`, estimate the causal effect of initiating treatment on the outcome using a target trial emulation design.*
# MAGIC
# MAGIC **Approach**: Define the target trial specification (PICO), assemble the cohort, apply the cloning-censoring-weighting framework to emulate two treatment strategies (initiate vs. do not initiate), estimate censoring weights via IPW, and compare outcomes between the two strategies.

# COMMAND ----------

# DBTITLE 1,rwe-004: Load TTE Data & Explore
# --- Load the TTE dataset ---
tte_path = "/Volumes/hls_amer_catalog/vital_skills/eval/rwe-cohortstudy/rwe_tte.csv"
df_tte = pd.read_csv(tte_path)
print(f"Dataset shape: {df_tte.shape}")
print(f"\nColumns and dtypes:")
print(df_tte.dtypes)
print(f"\nFirst 5 rows:")
print(df_tte.head())

# --- Auto-detect columns ---
# Treatment: exact names first, then partial match for columns containing 'treatment' or 'initiated'
treatment_col_t = [c for c in df_tte.columns if c.lower() in ['treatment', 'treated', 'treatment_initiated', 'group', 'exposure', 'drug', 'therapy']]
if not treatment_col_t:
    treatment_col_t = [c for c in df_tte.columns if any(k in c.lower() for k in ['treatment', 'treated', 'initiated'])]
# Outcome: exact names first, then partial match
exact_outcome_names = ['mortality', 'outcome', 'death', 'died']
outcome_col_t = [c for c in df_tte.columns if c.lower() in exact_outcome_names]
if not outcome_col_t:
    outcome_col_t = [c for c in df_tte.columns if any(k in c.lower() for k in ['outcome', 'event', 'death', 'mortality', 'died', 'dead', 'failure'])]
# ID column
id_col_t = [c for c in df_tte.columns if c.lower() in ['id', 'subject_id', 'patient_id', 'subject', 'patient']]
# Time: exact names first, then partial match
exact_time_names_t = ['event_time', 'followup_days', 'follow_up_days', 'time_to_event', 'tte', 'survival_time', 'time']
time_col_t = [c for c in df_tte.columns if c.lower() in exact_time_names_t]
if not time_col_t:
    time_col_t = [c for c in df_tte.columns if any(k in c.lower() for k in ['time', 'follow', 'days', 'survival', 'tte', 'period'])]

treatment_col_t = treatment_col_t[0] if treatment_col_t else 'treatment'
outcome_col_t = outcome_col_t[0] if outcome_col_t else 'outcome'
id_col_t = id_col_t[0] if id_col_t else None
time_col_t = time_col_t[0] if time_col_t else None

print(f"\nDetected treatment column: '{treatment_col_t}'")
print(f"Detected outcome column: '{outcome_col_t}'")
print(f"Detected ID column: '{id_col_t}'")
print(f"Detected time column: '{time_col_t}'")
print(f"\nTreatment distribution: {df_tte[treatment_col_t].value_counts().to_dict()}")
print(f"Outcome distribution: {df_tte[outcome_col_t].value_counts().to_dict()}")

# COMMAND ----------

# DBTITLE 1,rwe-004: Target Trial Specification
# --- Define the Target Trial Specification ---
print("=" * 60)
print("TARGET TRIAL SPECIFICATION")
print("=" * 60)
study_design = {
    'question': 'Does initiating treatment reduce the outcome compared to no initiation?',
    'population': 'All eligible patients in the observational cohort',
    'intervention': 'Initiate treatment (strategy A)',
    'comparator': 'Do not initiate treatment (strategy B)',
    'outcome': f'{outcome_col_t} (binary)',
    'follow_up': 'From treatment initiation (time zero) through end of observation',
    'assignment': 'Cloning: each patient is cloned into both strategies',
    'exclusions': 'Patients with missing treatment or outcome data',
    'grace_period': '30 days for treatment initiation',
}
for k, v in study_design.items():
    print(f'  {k}: {v}')

# --- Clean data for TTE ---
df_tte_clean = df_tte.dropna(subset=[treatment_col_t, outcome_col_t]).copy()
if id_col_t is None:
    df_tte_clean['_id'] = range(len(df_tte_clean))
    id_col_t = '_id'
else:
    df_tte_clean[id_col_t] = df_tte_clean[id_col_t].fillna(
        pd.Series(range(len(df_tte_clean)), index=df_tte_clean.index)
    )

# Determine follow-up time if available
time_col_tte = time_col_t if time_col_t and time_col_t in df_tte_clean.columns else None
if time_col_tte is None:
    df_tte_clean['followup'] = 730  # default max follow-up if no time column
tau_tte = int(df_tte_clean[time_col_tte].max()) if time_col_tte else 730

print(f"\nCohort size: {len(df_tte_clean)}")
print(f"Treated: {(df_tte_clean[treatment_col_t]==1).sum()} | Control: {(df_tte_clean[treatment_col_t]==0).sum()}")

# COMMAND ----------

# DBTITLE 1,rwe-004: Cloning, Censoring, Weighting & Effect Estimation
# --- Apply Target Trial Emulation: Cloning, Censoring, Weighting ---
print("=" * 60)
print("TARGET TRIAL EMULATION: CLONING, CENSORING, WEIGHTING")
print("=" * 60)

pooled_tte = target_trial_emulation(
    df_tte_clean,
    id_col=id_col_t,
    treatment_col=treatment_col_t,
    outcome_col=outcome_col_t,
    grace_period=30,
    max_followup=tau_tte
)

# --- Estimate treatment effect on uncensored clones ---
uncensored = pooled_tte[~pooled_tte['censored']].copy()
print(f"\nUncensored clones for analysis: {len(uncensored)}")
print(f"  Strategy A (initiate): {(uncensored['strategy']==1).sum()}")
print(f"  Strategy B (no initiate): {(uncensored['strategy']==0).sum()}")

# --- Effect estimation: IPW-weighted outcome comparison ---
if 'ipw_censor' in uncensored.columns and uncensored['ipw_censor'].sum() > 0:
    uncensored['ipw_censor'] = uncensored['ipw_censor'].clip(0.01, 100)
    
    # Weighted outcome rates by strategy
    strat_a = uncensored[uncensored['strategy'] == 1]
    strat_b = uncensored[uncensored['strategy'] == 0]
    
    rate_a = np.average(strat_a[outcome_col_t], weights=strat_a['ipw_censor'].values) if len(strat_a) > 0 else np.nan
    rate_b = np.average(strat_b[outcome_col_t], weights=strat_b['ipw_censor'].values) if len(strat_b) > 0 else np.nan
    
    rd_tte = rate_a - rate_b
    rr_tte = rate_a / rate_b if rate_b > 0 else np.inf
    
    print(f"\n--- IPW-Censor-Weighted Effect Estimates ---")
    print(f"Strategy A (initiate) outcome rate: {rate_a:.4f} ({rate_a*100:.1f}%)")
    print(f"Strategy B (no initiate) outcome rate: {rate_b:.4f} ({rate_b*100:.1f}%)")
    print(f"Risk difference: {rd_tte:.4f} ({rd_tte*100:.1f} pp)")
    print(f"Risk ratio: {rr_tte:.4f}")
else:
    # Unweighted comparison if censoring weights not available
    rate_a = uncensored[uncensored['strategy']==1][outcome_col_t].mean()
    rate_b = uncensored[uncensored['strategy']==0][outcome_col_t].mean()
    rd_tte = rate_a - rate_b
    rr_tte = rate_a / rate_b if rate_b > 0 else np.inf
    print(f"\nUnweighted outcome rate A: {rate_a:.4f}")
    print(f"Unweighted outcome rate B: {rate_b:.4f}")
    print(f"Risk difference: {rd_tte:.4f}")
    print(f"Risk ratio: {rr_tte:.4f}")

# --- Logistic regression on uncensored clones with censoring weights ---
print("\n--- Logistic Regression (Censoring-Weighted) ---")
try:
    # Use strategy as the treatment variable
    uncensored['strategy_var'] = uncensored['strategy'].astype(float)
    # Fit weighted logistic regression
    formula_tte = f"{outcome_col_t} ~ strategy_var"
    
    # Add covariates if available
    cov_cols_tte = [c for c in uncensored.columns 
                    if c not in [id_col_t, treatment_col_t, outcome_col_t, 'strategy', 'clone_id', 
                               'censored', 'followup', 'event', 'ipw_censor', 'strategy_var']
                    and uncensored[c].dtype in ['int64', 'float64', 'int32', 'float32', 'bool']]
    if len(cov_cols_tte) > 0:
        formula_tte = f"{outcome_col_t} ~ strategy_var + " + " + ".join(cov_cols_tte[:10])
    
    if 'ipw_censor' in uncensored.columns:
        wls_model = smf.wls(formula_tte, data=uncensored, 
                           weights=uncensored['ipw_censor'].clip(0.01, 100)).fit(disp=0)
    else:
        wls_model = smf.ols(formula_tte, data=uncensored).fit(disp=0)
    
    est = wls_model.params['strategy_var']
    se = wls_model.bse['strategy_var']
    ci_lo = est - 1.96 * se
    ci_hi = est + 1.96 * se
    p_val = wls_model.pvalues['strategy_var']
    print(f"Strategy effect (RD): {est:.4f} [{ci_lo:.4f}, {ci_hi:.4f}], p={p_val:.6f}")
except Exception as e:
    print(f"Logistic regression could not be fit: {e}")
    print(f"Falling back to crude comparison: RD={rd_tte:.4f}")

# --- Sensitivity Analysis: E-Value ---
print("\n--- E-Value Sensitivity Analysis ---")
evalue(rr=rr_tte, ci_lower=None, ci_upper=None)

# --- Summary ---
print("\n" + "=" * 60)
print("SUMMARY: TARGET TRIAL EMULATION")
print("=" * 60)
print(f"Design: Cloning + censoring + IPW for censoring")
print(f"Strategies: A (initiate treatment) vs B (no initiation)")
print(f"Outcome rate A: {rate_a:.4f} | Outcome rate B: {rate_b:.4f}")
print(f"Risk difference: {rd_tte:.4f}")
print(f"Risk ratio: {rr_tte:.4f}")
print(f"\nConclusion: Initiating treatment {'reduces' if rd_tte < 0 else 'increases'} the outcome")
print(f"in the target trial emulation framework.")
print(f"The E-value quantifies robustness to unmeasured confounding.")

# COMMAND ----------

