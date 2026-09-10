# Evaluation and stress testing

Use this reference to compare the HLS extension with no skills and with the generic Databricks ML skills.

## Configurations

* A: generic Databricks skills plus the HLS skill
* B: skills disabled
* C: generic skills enabled but the HLS skill disabled

The desired result for HLS cases is A passes while B and C fail or omit important model-specific decisions. If C passes, the HLS skill may be redundant for that case.

## Scenario groups

Test at least:

* custom PyFunc packaging for a Hugging Face checkpoint
* Git or Zenodo code/weight provenance
* model signature and `input_example`
* optional controls through SDK and HTTP
* AnnData, sparse matrix, FASTA, YAML, and structure inputs
* UC registration and versioned manifests
* Model Serving versus Jobs selection
* GPU/database/cache requirements
* AI Gateway and inference-table data minimization
* each model reference and an unknown-model fallback
* negative cases that should route to generic ML guidance

## Scoring dimensions

Score each run for:

* trigger precision
* correct reuse of generic guidance
* model-specific correctness
* explicit assumptions and open questions
* serving/Jobs decision quality
* signature and payload completeness
* provenance and license handling
* safety and data-governance awareness
* reproducibility and validation coverage

Run each prompt multiple times. Keep prompts, configuration, agent version, skill revision, and results in a version-controlled evaluation set. Update the relevant model reference when a test exposes a model-specific gap; update the core skill only when the shared routing or contract changes.
