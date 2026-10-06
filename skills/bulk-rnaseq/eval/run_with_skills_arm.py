# Databricks notebook source
# MAGIC %md
# MAGIC # Skill-guided arm
# MAGIC Four benchmark tasks executed sequentially as independent analyses.

# COMMAND ----------
import json
from pathlib import Path

import gseapy as gp
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

root = Path("/Volumes/hls_amer_catalog/vital_skills/eval")
outputs = {}

# COMMAND ----------
# MAGIC %md
# MAGIC ## Task 1

# COMMAND ----------
task_id = "hls-rnaseq-001"
task_dir = root / "task_001"
output_dir = root / "out" / "with_skills" / task_id
output_dir.mkdir(parents=True, exist_ok=True)
counts = pd.read_csv(task_dir / "counts.csv", index_col=0).T
metadata = pd.read_csv(task_dir / "metadata.csv", index_col=0)
shared = counts.index.intersection(metadata.index)
counts = counts.loc[shared].apply(pd.to_numeric, errors="raise").astype(int)
metadata = metadata.loc[shared]
counts = counts.loc[:, counts.sum(axis=0) >= 10]
dds = DeseqDataSet(counts=counts, metadata=metadata, design="~condition", refit_cooks=True, n_cpus=4)
dds.deseq2()
stats = DeseqStats(dds, contrast=["condition", "old", "young"], alpha=0.05, cooks_filter=True, independent_filter=True, n_cpus=4)
stats.summary()
results = stats.results_df.copy()
results.to_csv(output_dir / "deseq2_results.csv")
significant = results[results.padj < 0.05]
significant.to_csv(output_dir / "significant_genes.csv")
normalized = pd.DataFrame(dds.layers["normed_counts"], index=dds.obs_names, columns=dds.var_names)
log_counts = np.log2(normalized + 1)
top = log_counts.var().nlargest(min(500, log_counts.shape[1])).index
pcs = PCA(n_components=2).fit_transform(StandardScaler().fit_transform(log_counts[top]))
plt.scatter(pcs[:, 0], pcs[:, 1], c=(metadata.condition == "old").astype(int)); plt.savefig(output_dir / "pca_plot.png"); plt.close()
plt.scatter(results.log2FoldChange, -np.log10(results.pvalue.fillna(1).clip(lower=1e-300)), s=4); plt.savefig(output_dir / "volcano_plot.png"); plt.close()
plt.scatter(np.log10(results.baseMean.clip(lower=1)), results.log2FoldChange, s=4); plt.savefig(output_dir / "ma_plot.png"); plt.close()
ranked = results.log2FoldChange.dropna().sort_values(ascending=False)
enrichment = gp.prerank(rnk=ranked, gene_sets=str(task_dir / "MSigDB_Hallmark_2020.gmt"), min_size=15, max_size=500, permutation_num=1000, seed=42, threads=4, outdir=None, no_plot=True)
gsea = enrichment.res2d.copy()
gsea.to_csv(output_dir / "gsea_prerank_all_terms.tsv", sep="\t", index=False)
gsea[gsea["FDR q-val"] < 0.25].to_csv(output_dir / "gsea_prerank_significant_terms.tsv", sep="\t", index=False)
plot_data = gsea.reindex(gsea.NES.abs().sort_values(ascending=False).index).head(20)
plt.barh(plot_data.Term, plot_data.NES); plt.gca().invert_yaxis(); plt.savefig(output_dir / "gsea_nes_barplot.png", bbox_inches="tight"); plt.close()
graph = nx.Graph(); graph.add_nodes_from(plot_data.Term.astype(str)); nx.draw_networkx(graph, with_labels=False, node_size=100); plt.savefig(output_dir / "gsea_network_map.png"); plt.close()
outputs[task_id] = {
    "response": f"Completed PyDESeq2 with design ~condition and old-versus-young contrast on {counts.shape[0]} samples and {counts.shape[1]} genes; found {len(significant)} genes at padj < 0.05. Ran GSEA Prerank on all tested genes and reported pathways at FDR q-value < 0.25.",
    "action_log": "validated raw integer counts; low-count filter; PyDESeq2; ~condition; old; young; fit before PCA; normed_counts; raw pvalue volcano; GSEA Prerank; all tested genes; 1000 permutations; seed 42; FDR",
    "artifacts": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
}

# COMMAND ----------
# MAGIC %md
# MAGIC ## Task 2

# COMMAND ----------
task_id = "hls-rnaseq-002"
task_dir = root / "task_002"
output_dir = root / "out" / "with_skills" / task_id
output_dir.mkdir(parents=True, exist_ok=True)
raw = pd.read_csv(task_dir / "counts_with_annotations.csv", index_col=0)
metadata = pd.read_csv(task_dir / "metadata.csv", index_col=0)
gene_map = raw["HG19en82 Gene Name"].copy()
sample_columns = raw.columns.intersection(metadata.index)
counts = raw.loc[:, sample_columns].T.apply(pd.to_numeric, errors="raise").astype(int)
metadata = metadata.loc[counts.index]
counts = counts.loc[:, counts.sum(axis=0) >= 10]
dds = DeseqDataSet(counts=counts, metadata=metadata, design="~sex + condition", refit_cooks=True, n_cpus=4)
dds.deseq2()
stats = DeseqStats(dds, contrast=["condition", "old", "young"], alpha=0.05, cooks_filter=True, independent_filter=True, n_cpus=4)
stats.summary()
results = stats.results_df.copy()
results.to_csv(output_dir / "deseq2_results.csv")
significant = results[results.padj < 0.05]
significant.to_csv(output_dir / "significant_genes.csv")
normalized = pd.DataFrame(dds.layers["normed_counts"], index=dds.obs_names, columns=dds.var_names)
log_counts = np.log2(normalized + 1); top = log_counts.var().nlargest(min(500, log_counts.shape[1])).index
pcs = PCA(n_components=2).fit_transform(StandardScaler().fit_transform(log_counts[top]))
plt.scatter(pcs[:, 0], pcs[:, 1], c=(metadata.condition == "old").astype(int)); plt.savefig(output_dir / "pca_plot.png"); plt.close()
plt.scatter(results.log2FoldChange, -np.log10(results.pvalue.fillna(1).clip(lower=1e-300)), s=4); plt.savefig(output_dir / "volcano_plot.png"); plt.close()
plt.scatter(np.log10(results.baseMean.clip(lower=1)), results.log2FoldChange, s=4); plt.savefig(output_dir / "ma_plot.png"); plt.close()
rank_frame = pd.DataFrame({"score": results.log2FoldChange, "symbol": gene_map.reindex(results.index)}).dropna()
rank_frame["magnitude"] = rank_frame.score.abs()
ranked = rank_frame.sort_values("magnitude", ascending=False).drop_duplicates("symbol").set_index("symbol").score.sort_values(ascending=False)
enrichment = gp.prerank(rnk=ranked, gene_sets=str(task_dir / "MSigDB_Hallmark_2020.gmt"), min_size=15, max_size=500, permutation_num=1000, seed=42, threads=4, outdir=None, no_plot=True)
gsea = enrichment.res2d.copy(); gsea.to_csv(output_dir / "gsea_prerank_all_terms.tsv", sep="\t", index=False)
gsea[gsea["FDR q-val"] < 0.25].to_csv(output_dir / "gsea_prerank_significant_terms.tsv", sep="\t", index=False)
plot_data = gsea.reindex(gsea.NES.abs().sort_values(ascending=False).index).head(20)
plt.barh(plot_data.Term, plot_data.NES); plt.gca().invert_yaxis(); plt.savefig(output_dir / "gsea_nes_barplot.png", bbox_inches="tight"); plt.close()
graph = nx.Graph(); graph.add_nodes_from(plot_data.Term.astype(str)); nx.draw_networkx(graph, with_labels=False, node_size=100); plt.savefig(output_dir / "gsea_network_map.png"); plt.close()
outputs[task_id] = {
    "response": f"Excluded annotation columns, fitted PyDESeq2 design ~sex + condition, and tested old versus young; found {len(significant)} genes at padj < 0.05. Mapped Ensembl IDs to HGNC symbols and ran GSEA Prerank with 1000 permutations and seed 42.",
    "action_log": "excluded annotation columns; raw integer counts; low-count filter; PyDESeq2; ~sex + condition; normed_counts PCA; Ensembl to HGNC; prerank; 1000; seed; FDR",
    "artifacts": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
}

# COMMAND ----------
# MAGIC %md
# MAGIC ## Task 3

# COMMAND ----------
task_id = "hls-rnaseq-003"
task_dir = root / "task_003"
output_dir = root / "out" / "with_skills" / task_id
output_dir.mkdir(parents=True, exist_ok=True)
counts = pd.read_csv(task_dir / "counts_samples_by_genes.csv", index_col=0)
metadata = pd.read_csv(task_dir / "metadata_space_column.csv", index_col=0).rename(columns={"age group": "age_group"})
shared = counts.index.intersection(metadata.index)
counts = counts.loc[shared].apply(pd.to_numeric, errors="raise").astype(int)
metadata = metadata.loc[shared]
counts = counts.loc[:, counts.sum(axis=0) >= 10]
dds = DeseqDataSet(counts=counts, metadata=metadata, design="~age_group", refit_cooks=True, n_cpus=4)
dds.deseq2()
stats = DeseqStats(dds, contrast=["age_group", "old", "young"], alpha=0.05, cooks_filter=True, independent_filter=True, n_cpus=4)
stats.summary()
results = stats.results_df.copy(); results.to_csv(output_dir / "deseq2_results.csv")
significant = results[results.padj < 0.05]; significant.to_csv(output_dir / "significant_genes.csv")
normalized = pd.DataFrame(dds.layers["normed_counts"], index=dds.obs_names, columns=dds.var_names)
log_counts = np.log2(normalized + 1); top = log_counts.var().nlargest(min(500, log_counts.shape[1])).index
pcs = PCA(n_components=2).fit_transform(StandardScaler().fit_transform(log_counts[top]))
plt.scatter(pcs[:, 0], pcs[:, 1], c=(metadata.age_group == "old").astype(int)); plt.savefig(output_dir / "pca_plot.png"); plt.close()
plt.scatter(results.log2FoldChange, -np.log10(results.pvalue.fillna(1).clip(lower=1e-300)), s=4); plt.savefig(output_dir / "volcano_plot.png"); plt.close()
plt.scatter(np.log10(results.baseMean.clip(lower=1)), results.log2FoldChange, s=4); plt.savefig(output_dir / "ma_plot.png"); plt.close()
ranked = results.log2FoldChange.dropna().sort_values(ascending=False)
enrichment = gp.prerank(rnk=ranked, gene_sets=str(task_dir / "MSigDB_Hallmark_2020.gmt"), min_size=15, max_size=500, permutation_num=1000, seed=42, threads=4, outdir=None, no_plot=True)
gsea = enrichment.res2d.copy(); gsea.to_csv(output_dir / "gsea_prerank_all_terms.tsv", sep="\t", index=False)
gsea[gsea["FDR q-val"] < 0.25].to_csv(output_dir / "gsea_prerank_significant_terms.tsv", sep="\t", index=False)
plot_data = gsea.reindex(gsea.NES.abs().sort_values(ascending=False).index).head(20)
plt.barh(plot_data.Term, plot_data.NES); plt.gca().invert_yaxis(); plt.savefig(output_dir / "gsea_nes_barplot.png", bbox_inches="tight"); plt.close()
graph = nx.Graph(); graph.add_nodes_from(plot_data.Term.astype(str)); nx.draw_networkx(graph, with_labels=False, node_size=100); plt.savefig(output_dir / "gsea_network_map.png"); plt.close()
outputs[task_id] = {
    "response": f"Recognized samples by genes, renamed age group to age_group, fitted design ~age_group, and retained young and old contrast values. Found {len(significant)} genes at padj < 0.05 and ran GSEA Prerank.",
    "action_log": "samples by genes; no transpose; age_group; ~age_group; young; old; PyDESeq2; normed_counts; prerank; 1000 permutations; seed 42; FDR",
    "artifacts": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
}

# COMMAND ----------
# MAGIC %md
# MAGIC ## Task 4

# COMMAND ----------
task_id = "hls-rnaseq-004"
task_dir = root / "task_004"
output_dir = root / "out" / "with_skills" / task_id
output_dir.mkdir(parents=True, exist_ok=True)
counts = pd.read_csv(task_dir / "counts.csv", index_col=0).T
metadata = pd.read_csv(task_dir / "metadata_with_unmatched_sample.csv", index_col=0)
shared = counts.index.intersection(metadata.index)
unmatched = sorted(set(metadata.index) - set(shared))
counts = counts.loc[shared].apply(pd.to_numeric, errors="raise").astype(int)
metadata = metadata.loc[shared]
counts = counts.loc[:, counts.sum(axis=0) >= 10]
dds = DeseqDataSet(counts=counts, metadata=metadata, design="~sex + condition", refit_cooks=True, n_cpus=4)
dds.deseq2()
stats = DeseqStats(dds, contrast=["condition", "old", "young"], alpha=0.05, cooks_filter=True, independent_filter=True, n_cpus=4)
stats.summary()
results = stats.results_df.copy(); results.to_csv(output_dir / "deseq2_results.csv")
significant = results[results.padj < 0.05]; significant.to_csv(output_dir / "significant_genes.csv")
normalized = pd.DataFrame(dds.layers["normed_counts"], index=dds.obs_names, columns=dds.var_names)
log_counts = np.log2(normalized + 1); top = log_counts.var().nlargest(min(500, log_counts.shape[1])).index
pcs = PCA(n_components=2).fit_transform(StandardScaler().fit_transform(log_counts[top]))
plt.scatter(pcs[:, 0], pcs[:, 1], c=(metadata.condition == "old").astype(int)); plt.savefig(output_dir / "pca_plot.png"); plt.close()
plt.scatter(results.log2FoldChange, -np.log10(results.pvalue.fillna(1).clip(lower=1e-300)), s=4); plt.savefig(output_dir / "volcano_plot.png"); plt.close()
plt.scatter(np.log10(results.baseMean.clip(lower=1)), results.log2FoldChange, s=4); plt.savefig(output_dir / "ma_plot.png"); plt.close()
ranked = results.log2FoldChange.dropna().sort_values(ascending=False)
enrichment = gp.prerank(rnk=ranked, gene_sets=str(task_dir / "MSigDB_Hallmark_2020.gmt"), min_size=15, max_size=500, permutation_num=1000, seed=42, threads=4, outdir=None, no_plot=True)
gsea = enrichment.res2d.copy(); gsea.to_csv(output_dir / "gsea_prerank_all_terms.tsv", sep="\t", index=False)
gsea[gsea["FDR q-val"] < 0.25].to_csv(output_dir / "gsea_prerank_significant_terms.tsv", sep="\t", index=False)
plot_data = gsea.reindex(gsea.NES.abs().sort_values(ascending=False).index).head(20)
plt.barh(plot_data.Term, plot_data.NES); plt.gca().invert_yaxis(); plt.savefig(output_dir / "gsea_nes_barplot.png", bbox_inches="tight"); plt.close()
graph = nx.Graph(); graph.add_nodes_from(plot_data.Term.astype(str)); nx.draw_networkx(graph, with_labels=False, node_size=100); plt.savefig(output_dir / "gsea_network_map.png"); plt.close()
outputs[task_id] = {
    "response": f"Aligned the counts and metadata intersection, excluded unmatched metadata sample {unmatched}, fitted PyDESeq2 design ~sex + condition, and ran GSEA Prerank at FDR q-value < 0.25.",
    "action_log": "sample intersection; unmatched metadata sample; low-count filter; PyDESeq2; ~sex + condition; normed_counts PCA; prerank; FDR",
    "artifacts": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
}

# COMMAND ----------
output_path = root / "with_skill_outputs.json"
output_path.write_text(json.dumps(outputs, indent=2), encoding="utf-8")
dbutils.notebook.exit(json.dumps({"arm": "with_skills", "tasks": 4, "outputs": str(output_path)}))
