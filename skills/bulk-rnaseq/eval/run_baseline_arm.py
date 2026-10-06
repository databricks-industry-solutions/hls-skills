# Databricks notebook source
# MAGIC %md
# MAGIC # Baseline arm
# MAGIC Four benchmark tasks executed sequentially as independent analyses.

# COMMAND ----------
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import hypergeom, ttest_ind
from sklearn.decomposition import PCA
from statsmodels.stats.multitest import multipletests

root = Path("/Volumes/hls_amer_catalog/vital_skills/eval")
outputs = {}

# COMMAND ----------
# MAGIC %md
# MAGIC ## Task 1

# COMMAND ----------
task_id = "hls-rnaseq-001"
task_dir = root / "task_001"
output_dir = root / "out" / "baseline" / task_id
output_dir.mkdir(parents=True, exist_ok=True)
counts = pd.read_csv(task_dir / "counts.csv", index_col=0).T
metadata = pd.read_csv(task_dir / "metadata.csv", index_col=0)
shared = counts.index.intersection(metadata.index)
counts = counts.loc[shared].apply(pd.to_numeric).astype(int)
metadata = metadata.loc[shared]
counts = counts.loc[:, counts.sum(axis=0) >= 10]
log_cpm = np.log2(counts.div(counts.sum(axis=1), axis=0) * 1_000_000 + 1)
young = metadata.condition == "young"
old = metadata.condition == "old"
stat, pvalue = ttest_ind(log_cpm.loc[old], log_cpm.loc[young], axis=0, equal_var=False)
log2fc = log_cpm.loc[old].mean() - log_cpm.loc[young].mean()
results = pd.DataFrame({"log2FoldChange": log2fc, "pvalue": pvalue}, index=counts.columns)
results["padj"] = multipletests(np.nan_to_num(results.pvalue, nan=1), method="fdr_bh")[1]
results.to_csv(output_dir / "deseq2_results.csv")
significant = results[(results.padj < 0.05) & (results.log2FoldChange.abs() > 1)]
significant.to_csv(output_dir / "significant_genes.csv")
pcs = PCA(n_components=2).fit_transform(log_cpm)
plt.scatter(pcs[:, 0], pcs[:, 1], c=old.astype(int)); plt.savefig(output_dir / "pca_plot.png"); plt.close()
plt.scatter(results.log2FoldChange, -np.log10(results.pvalue.clip(lower=1e-300)), s=4); plt.savefig(output_dir / "volcano_plot.png"); plt.close()
gene_sets = {}
for line in (task_dir / "MSigDB_Hallmark_2020.gmt").read_text().splitlines():
    fields = line.split("\t"); gene_sets[fields[0]] = set(fields[2:])
hits, universe, ora_rows = set(significant.index), set(results.index), []
for term, genes in gene_sets.items():
    overlap = hits & genes
    ora_rows.append({"Term": term, "Overlap": len(overlap), "P-value": hypergeom.sf(len(overlap)-1, len(universe), len(universe & genes), len(hits))})
ora = pd.DataFrame(ora_rows).sort_values("P-value")
ora["Adjusted P-value"] = multipletests(ora["P-value"], method="fdr_bh")[1]
ora.to_csv(output_dir / "ora_pooled_terms.tsv", sep="\t", index=False)
outputs[task_id] = {
    "response": f"Used a Welch t-test on log CPM for young versus old and found {len(significant)} DE genes; ran ORA on the pooled significant list.",
    "action_log": "loaded counts; log CPM; Welch t-test; BH padj; PCA; volcano; pooled up and down genes; ORA",
    "artifacts": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
}

# COMMAND ----------
# MAGIC %md
# MAGIC ## Task 2

# COMMAND ----------
task_id = "hls-rnaseq-002"
task_dir = root / "task_002"
output_dir = root / "out" / "baseline" / task_id
output_dir.mkdir(parents=True, exist_ok=True)
raw = pd.read_csv(task_dir / "counts_with_annotations.csv", index_col=0)
metadata = pd.read_csv(task_dir / "metadata.csv", index_col=0)
sample_columns = raw.columns.intersection(metadata.index)
gene_symbols = raw["HG19en82 Gene Name"]
counts = raw.loc[:, sample_columns].T.apply(pd.to_numeric).astype(int)
metadata = metadata.loc[counts.index]
counts = counts.loc[:, counts.sum(axis=0) >= 10]
log_cpm = np.log2(counts.div(counts.sum(axis=1), axis=0) * 1_000_000 + 1)
young = metadata.condition == "young"
old = metadata.condition == "old"
stat, pvalue = ttest_ind(log_cpm.loc[old], log_cpm.loc[young], axis=0, equal_var=False)
results = pd.DataFrame({"log2FoldChange": log_cpm.loc[old].mean()-log_cpm.loc[young].mean(), "pvalue": pvalue}, index=counts.columns)
results["padj"] = multipletests(np.nan_to_num(results.pvalue, nan=1), method="fdr_bh")[1]
results.to_csv(output_dir / "deseq2_results.csv")
significant = results[(results.padj < 0.05) & (results.log2FoldChange.abs() > 1)]
significant.to_csv(output_dir / "significant_genes.csv")
pcs = PCA(n_components=2).fit_transform(log_cpm)
plt.scatter(pcs[:, 0], pcs[:, 1], c=old.astype(int)); plt.savefig(output_dir / "pca_plot.png"); plt.close()
plt.scatter(results.log2FoldChange, -np.log10(results.pvalue.clip(lower=1e-300)), s=4); plt.savefig(output_dir / "volcano_plot.png"); plt.close()
mapped_hits = set(gene_symbols.reindex(significant.index).dropna())
all_symbols = set(gene_symbols.reindex(results.index).dropna())
gene_sets = {}
for line in (task_dir / "MSigDB_Hallmark_2020.gmt").read_text().splitlines():
    fields = line.split("\t"); gene_sets[fields[0]] = set(fields[2:])
ora_rows = []
for term, genes in gene_sets.items():
    overlap = mapped_hits & genes
    ora_rows.append({"Term": term, "Overlap": len(overlap), "P-value": hypergeom.sf(len(overlap)-1, len(all_symbols), len(all_symbols & genes), len(mapped_hits))})
ora = pd.DataFrame(ora_rows).sort_values("P-value")
ora["Adjusted P-value"] = multipletests(ora["P-value"], method="fdr_bh")[1]
ora.to_csv(output_dir / "ora_pooled_terms.tsv", sep="\t", index=False)
outputs[task_id] = {
    "response": f"Compared young and old by Welch t-test without covariate adjustment; found {len(significant)} DE genes and ran pooled-list ORA after symbol mapping.",
    "action_log": "removed annotation columns; log CPM; Welch t-test; BH padj; PCA; volcano; Ensembl to HGNC; pooled ORA",
    "artifacts": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
}

# COMMAND ----------
# MAGIC %md
# MAGIC ## Task 3

# COMMAND ----------
task_id = "hls-rnaseq-003"
task_dir = root / "task_003"
output_dir = root / "out" / "baseline" / task_id
output_dir.mkdir(parents=True, exist_ok=True)
counts = pd.read_csv(task_dir / "counts_samples_by_genes.csv", index_col=0)
metadata = pd.read_csv(task_dir / "metadata_space_column.csv", index_col=0)
shared = counts.index.intersection(metadata.index)
counts = counts.loc[shared].apply(pd.to_numeric).astype(int)
metadata = metadata.loc[shared]
counts = counts.loc[:, counts.sum(axis=0) >= 10]
log_cpm = np.log2(counts.div(counts.sum(axis=1), axis=0) * 1_000_000 + 1)
young = metadata["age group"] == "young"
old = metadata["age group"] == "old"
stat, pvalue = ttest_ind(log_cpm.loc[old], log_cpm.loc[young], axis=0, equal_var=False)
results = pd.DataFrame({"log2FoldChange": log_cpm.loc[old].mean()-log_cpm.loc[young].mean(), "pvalue": pvalue}, index=counts.columns)
results["padj"] = multipletests(np.nan_to_num(results.pvalue, nan=1), method="fdr_bh")[1]
results.to_csv(output_dir / "deseq2_results.csv")
significant = results[(results.padj < 0.05) & (results.log2FoldChange.abs() > 1)]
significant.to_csv(output_dir / "significant_genes.csv")
pcs = PCA(n_components=2).fit_transform(log_cpm)
plt.scatter(pcs[:, 0], pcs[:, 1], c=old.astype(int)); plt.savefig(output_dir / "pca_plot.png"); plt.close()
plt.scatter(results.log2FoldChange, -np.log10(results.pvalue.clip(lower=1e-300)), s=4); plt.savefig(output_dir / "volcano_plot.png"); plt.close()
gene_sets = {}
for line in (task_dir / "MSigDB_Hallmark_2020.gmt").read_text().splitlines():
    fields = line.split("\t"); gene_sets[fields[0]] = set(fields[2:])
hits, universe, ora_rows = set(significant.index), set(results.index), []
for term, genes in gene_sets.items():
    overlap = hits & genes
    ora_rows.append({"Term": term, "Overlap": len(overlap), "P-value": hypergeom.sf(len(overlap)-1, len(universe), len(universe & genes), len(hits))})
ora = pd.DataFrame(ora_rows).sort_values("P-value")
ora["Adjusted P-value"] = multipletests(ora["P-value"], method="fdr_bh")[1]
ora.to_csv(output_dir / "ora_pooled_terms.tsv", sep="\t", index=False)
outputs[task_id] = {
    "response": f"Recognized samples by genes, compared the age group values with a Welch t-test, and found {len(significant)} DE genes before pooled ORA.",
    "action_log": "samples by genes; age group; log CPM; Welch t-test; PCA; volcano; pooled ORA",
    "artifacts": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
}

# COMMAND ----------
# MAGIC %md
# MAGIC ## Task 4

# COMMAND ----------
task_id = "hls-rnaseq-004"
task_dir = root / "task_004"
output_dir = root / "out" / "baseline" / task_id
output_dir.mkdir(parents=True, exist_ok=True)
counts = pd.read_csv(task_dir / "counts.csv", index_col=0).T
metadata = pd.read_csv(task_dir / "metadata_with_unmatched_sample.csv", index_col=0)
shared = counts.index.intersection(metadata.index)
counts = counts.loc[shared].apply(pd.to_numeric).astype(int)
metadata = metadata.loc[shared]
counts = counts.loc[:, counts.sum(axis=0) >= 10]
log_cpm = np.log2(counts.div(counts.sum(axis=1), axis=0) * 1_000_000 + 1)
young = metadata.condition == "young"
old = metadata.condition == "old"
stat, pvalue = ttest_ind(log_cpm.loc[old], log_cpm.loc[young], axis=0, equal_var=False)
results = pd.DataFrame({"log2FoldChange": log_cpm.loc[old].mean()-log_cpm.loc[young].mean(), "pvalue": pvalue}, index=counts.columns)
results["padj"] = multipletests(np.nan_to_num(results.pvalue, nan=1), method="fdr_bh")[1]
results.to_csv(output_dir / "deseq2_results.csv")
significant = results[(results.padj < 0.05) & (results.log2FoldChange.abs() > 1)]
significant.to_csv(output_dir / "significant_genes.csv")
pcs = PCA(n_components=2).fit_transform(log_cpm)
plt.scatter(pcs[:, 0], pcs[:, 1], c=old.astype(int)); plt.savefig(output_dir / "pca_plot.png"); plt.close()
plt.scatter(results.log2FoldChange, -np.log10(results.pvalue.clip(lower=1e-300)), s=4); plt.savefig(output_dir / "volcano_plot.png"); plt.close()
gene_sets = {}
for line in (task_dir / "MSigDB_Hallmark_2020.gmt").read_text().splitlines():
    fields = line.split("\t"); gene_sets[fields[0]] = set(fields[2:])
hits, universe, ora_rows = set(significant.index), set(results.index), []
for term, genes in gene_sets.items():
    overlap = hits & genes
    ora_rows.append({"Term": term, "Overlap": len(overlap), "P-value": hypergeom.sf(len(overlap)-1, len(universe), len(universe & genes), len(hits))})
ora = pd.DataFrame(ora_rows).sort_values("P-value")
ora["Adjusted P-value"] = multipletests(ora["P-value"], method="fdr_bh")[1]
ora.to_csv(output_dir / "ora_pooled_terms.tsv", sep="\t", index=False)
outputs[task_id] = {
    "response": f"Aligned shared samples and compared young versus old by Welch t-test; found {len(significant)} DE genes and ran pooled ORA.",
    "action_log": "sample intersection; log CPM; Welch t-test; low-count filter; PCA; volcano; pooled ORA",
    "artifacts": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
}

# COMMAND ----------
output_path = root / "baseline_outputs.json"
output_path.write_text(json.dumps(outputs, indent=2), encoding="utf-8")
dbutils.notebook.exit(json.dumps({"arm": "baseline", "tasks": 4, "outputs": str(output_path)}))
