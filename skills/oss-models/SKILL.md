---
name: oss-models
description: Package, register, validate, and deploy open-source health and life-sciences models on Databricks. Use for Geneformer, scGPT, Scimilarity, AlphaFold/OpenFold, Boltz, or similar models whose code, checkpoints, databases, tokenizers, or scientific inputs come from Hugging Face, Git, Zenodo, or other external sources. Use this skill when a request involves custom PyFunc wrappers, Unity Catalog registration, Model Serving, Jobs, GPU/runtime selection, complex biological inputs, provenance, or AI Gateway inference tables.
author: hengrumay
license: Databricks License
---

# HLS OSS Models

## Overview

This guide is a Health & Life Sciences (HLS) extension layer for packaging, registering, validating, and deploying open-source scientific models on Databricks. It does not reproduce generic MLflow or custom PyFunc mechanics — it supplies the model-family decisions that generic guidance cannot know: scientific preprocessing, checkpoint and database requirements, GPU and runtime constraints, serving-versus-Jobs suitability, provenance, and biological sanity checks. When the request needs standard logging, signatures, dependency packaging, Unity Catalog registration, Model Serving, or MLflow evaluation, use the existing Databricks ML training and Model Serving skills as the implementation foundation and layer this guide on top.

## When to Use

- The request names an HLS model (Geneformer, scGPT, Scimilarity, AlphaFold/OpenFold, Boltz, or similar) whose code or weights come from an external source.
- The task involves biological sequences or structures, single-cell data, molecular design, or other complex scientific inputs that need a deliberate serving contract.
- Model code, checkpoints, tokenizers, or reference databases must be pinned and packaged for offline, reproducible startup.
- You must decide between Model Serving, Jobs, an interactive app, or a multi-step workflow for a scientific model.
- The request touches provenance, licensing, or offline reproducibility controls for external model weights and datasets.
- The user asks for AI Gateway policies, usage tracking, or inference tables over an HLS endpoint that may log sensitive payloads.

For generic custom PyFunc, sklearn, or ordinary PyTorch packaging with no scientific inputs, use the standard Databricks ML training skill instead.

## Key Concepts

### Extension layer, not a replacement
Reusable Databricks mechanics (PyFunc, signatures, UC registration, serving) live in the generic skills. This guide adds only the HLS-specific adapter behavior. Do not assume Genie Code has a formal skill-inheritance mechanism; if the generic skill is unavailable, restate only the minimum implementation checklist from `references/integration-contract.md` rather than copying the generic tutorial.

### Execution boundary
Before writing code, record the exact upstream repository/package/model card, the model and code revision (immutable commit — prefer a commit SHA, since git tags can be re-pointed), the checkpoint or weight source and revision, the model and dataset licenses, expected input modalities and output objects, preprocessing/postprocessing and reference-data dependencies, and whether the user needs online inference, batch scoring, an interactive app, or a multi-step workflow. If the model name is ambiguous, stop and ask for the exact upstream project, or select the closest reference while clearly marking assumptions.

### Provenance-controlled inputs
Treat code, weights, tokenizers, scientific databases, and configuration as separate provenance-controlled inputs — each pinned to an immutable revision with URL, checksum, license, and acquisition date recorded in a manifest. A mutable branch, `latest` URL, or unpinned model card is non-reproducible until pinned.

### Serving-contract shapes for scientific inputs
Complex inputs (AnnData, sparse matrices, FASTA, YAML, structures) need a deliberate contract: scalar/tabular fields for small bounded values; JSON strings for nested records or configuration; base64 or URI references for files and structures; arrays or nested lists only after testing the exact serving serializer; a Volume or object-storage URI for large inputs with authorization and lifecycle rules.

### Technical vs scientific validation
Technical validation (imports, signatures, deployment) is distinct from scientific, clinical, and regulatory validation. A successful deployment never implies clinical validity.

## Decision Framework

Route the model first, then choose the execution mode.

```
Is there scientific preprocessing, a custom checkpoint layout, or complex biological input?
├── No  → use the standard Databricks ML training skill (generic PyFunc/PyTorch packaging)
└── Yes → use this guide together with the ML training skill
    │
    └── How is inference shaped?
        ├── Bounded, deterministic, self-contained, stable request schema → consider Model Serving
        ├── CPU-heavy prep / MSA / very large DBs / multi-stage / large artifact outputs → Jobs / workflow
        └── Both (bounded scoring + heavy preparation or design loops) → hybrid: endpoint + Job
```

Choose **Model Serving** only when *all* hold; choose **Jobs / orchestration** when *any* of the Jobs-side conditions hold:

| Scenario | Recommended | Rationale |
|----------|-------------|-----------|
| Bounded JSON/file-URI contract, artifacts fit endpoint, no runtime internet, acceptable latency/size, safe outputs | Model Serving | Low-latency online inference with a stable, packaged contract |
| CPU-heavy preprocessing or MSA generation before GPU inference | Jobs | Separates heavy prep from latency-sensitive scoring |
| Very large reference databases or multiple containers/processes | Jobs | Exceeds endpoint resource and packaging limits |
| Multi-stage, iterative, asynchronous, or long-running inference | Jobs | Not representable as a single bounded request |
| Large structures, trajectories, files, or artifact collections as output | Jobs | Outputs too large or numerous for an HTTP response |
| Reproducibility/auditability outweigh low latency | Jobs | Deterministic, logged, re-runnable execution |
| Bounded scoring plus preparation, enrichment, or design loops | Hybrid | Endpoint for scoring, Job for preparation/artifact generation |

For endpoint observability, usage tracking, or request logging, use supported AI Gateway features subject to data-governance review (see Best Practices and `references/maintenance.md`).

## Best Practices

1. **Define the serving contract before the wrapper.** Create an `input_example` and a signature that represent the actual request. Prefer explicit columns/fields for meaningful optional controls over an untested SDK `params=` path. Document request/response examples for both Python SDK and HTTP invocation, and validate them with the generic MLflow serving-input tools plus a real endpoint or local runner.
2. **Package for reproducibility.** Pin source revisions and dependency versions; prefer build-time downloads into a governed Volume or model artifact location; record URL, revision, checksum, license, and acquisition date in a manifest; never download weights at request time; never embed credentials in artifacts or notebooks; test an offline / network-restricted startup path.
3. **Make cache and database paths explicit.** Ensure cache paths are writable by the serving or Job identity. Keep large reference databases outside the model artifact when appropriate, but version and validate their mounted location.
4. **Keep the wrapper boundary thin.** Load heavyweight objects once during initialization; keep `predict` deterministic with respect to declared inputs; normalize scientific input types at the boundary; return stable serializable outputs or persisted artifact references; expose provenance without leaking secrets.
5. **Register with a promotion strategy.** Register to Unity Catalog with an explicit versioning/promotion strategy, and store the source/weight manifest alongside the model version or in a linked governed location.
6. **Minimize sensitive data in observability.** Before enabling inference tables, classify sequence, structure, patient, donor, and compound data; minimize or redact payloads; define retention, access, and masking rules; prefer a hash, metadata record, or governed URI over raw inputs; confirm failures/retries do not create misleading duplicate records. Inference tables are governance mechanisms, not a substitute for model validation or authorization design.
7. **Separate technical from scientific validation.** For regulated, clinical, or decision-support use cases, keep technical validation distinct from scientific, clinical, regulatory, and human-review requirements.

## Example

A concrete end-to-end example that makes Best Practices §1 real for a **bounded single-cell Geneformer request** on Model Serving. Every *field name* is grounded in `references/models/geneformer.md` (gene identifiers, vocabulary version, truncation, gene-count limit, pooling mode, output selection) and `references/integration-contract.md` (transport-encoding table, manifest keys). Every *upstream-specific value* is a clearly-marked placeholder `<...>` that MUST be resolved from the pinned Geneformer release — the no-invention rule applies: these are not real vocabulary IDs, revisions, checksums, or tensor shapes.

Transport choice: the encoding table routes an AnnData / sparse-matrix row to tabular fields plus a JSON configuration string, so a single cell becomes a compact feature record (`genes` + `expression`) and a `config` JSON string for the optional controls.

### (a) Python `input_example`

```python
input_example = {
    "cell_id": "cell-0001",
    # Gene IDs MUST be present in the pinned vocabulary <vocab-version>.
    # Placeholders — resolve real Ensembl IDs from the pinned Geneformer release.
    "genes": ["<ensembl-gene-id-1>", "<ensembl-gene-id-2>", "<ensembl-gene-id-3>"],
    "expression": [12.0, 5.0, 3.0],  # counts aligned position-for-position to `genes`
    "vocab_version": "<vocab-version>",
    # Optional controls as explicit fields (Best Practices §1), NOT an untested params= path.
    # Supported values (e.g. the pooling mode enum, the max token/gene-count limit) must be
    # read from the pinned reference — do not assume them here.
    "config": "{\"truncation\": true, \"gene_count_limit\": \"<max-input-tokens>\", \"pooling_mode\": \"<pooling-mode>\", \"output\": \"embedding\"}",
}
```

### (b) Equivalent HTTP request JSON

MLflow scoring-server `dataframe_records` format. Confirm the exact accepted format (`dataframe_split` / `dataframe_records` / `inputs`) against the deployed endpoint signature and MLflow version before depending on it — see `databricks-model-serving`.

```json
{
  "dataframe_records": [
    {
      "cell_id": "cell-0001",
      "genes": ["<ensembl-gene-id-1>", "<ensembl-gene-id-2>", "<ensembl-gene-id-3>"],
      "expression": [12.0, 5.0, 3.0],
      "vocab_version": "<vocab-version>",
      "config": "{\"truncation\": true, \"gene_count_limit\": \"<max-input-tokens>\", \"pooling_mode\": \"<pooling-mode>\", \"output\": \"embedding\"}"
    }
  ]
}
```

### (c) Expected response shape

MLflow scoring-server response envelope. The embedding vector values and dimension are placeholders because the true shape is fixed by the pinned checkpoint — do not assert a dimension.

```json
{
  "predictions": [
    {
      "cell_id": "cell-0001",
      "embedding": ["<float>", "<float>", "..."],
      "embedding_dim": "<embedding-dim>",
      "vocab_version": "<vocab-version>",
      "model_revision": "<immutable-commit>"
    }
  ]
}
```

### (d) Provenance manifest snippet

Stored next to the model version (keys per `references/integration-contract.md`). The two `source_url` values are the reference sources listed in `geneformer.md`; every other `<...>` must be resolved and never marked verified until confirmed upstream.

```yaml
model:
  name: geneformer
  upstream_revision: <immutable-commit>
  reviewed_at: <YYYY-MM-DD>
code:
  source_url: https://github.com/jkobject/geneformer
  revision: <commit-or-tag>
weights:
  source_url: https://huggingface.co/ctheodoris/Geneformer
  revision_or_record: <immutable-commit>
  sha256: <sha256>
license:
  code: <license-or-unknown>
  weights: <license-or-unknown>
  databases: not-applicable
runtime:
  python: "<python-version>"
  accelerator: <cpu-gpu-or-specific-family>
  network_required_at_runtime: false
artifacts:
  - name: vocabulary
    location: <governed-volume-or-model-artifact>
    sha256: <sha256>
  - name: checkpoint
    location: <governed-volume-or-model-artifact>
    sha256: <sha256>
```

## Troubleshooting

1. **Downloading weights at request time.** Slow, non-reproducible, and often fails in network-restricted serving.
   - *How to avoid*: Download at build time into a governed Volume or artifact location; test an offline startup path.
2. **Unpinned or `latest` revisions.** A mutable branch or model card silently changes behavior.
   - *How to avoid*: Pin an immutable commit SHA or content-addressed release/DOI (git tags can move) and record it in the manifest with a checksum.
3. **Relying on an untested `params=` path.** The SDK `params=` route may not round-trip for a given custom PyFunc and deployment route.
   - *How to avoid*: Use explicit fields/columns for controls, and validate the exact serving serializer before depending on arrays or nested lists.
4. **Logging raw sensitive payloads.** Inference tables can capture patient, donor, sequence, or compound data.
   - *How to avoid*: Classify and minimize/redact first; log hashes, metadata, or governed URIs instead of raw inputs.
5. **Assuming skill inheritance.** Genie Code has no formal mechanism to inherit the generic skill's steps.
   - *How to avoid*: When the generic skill is absent, restate only the minimum checklist from `references/integration-contract.md`.
6. **Implying clinical validity from a green deployment.** A successful technical deployment says nothing about scientific or clinical validity.
   - *How to avoid*: Report technical validation separately and defer scientific/clinical/regulatory sign-off to the appropriate review.
7. **Inventing model APIs.** Guessing tensor shapes, tokenizer names, database paths, or license terms produces broken wrappers.
   - *How to avoid*: Load the matching `references/models/<model>.md`; if none exists, use `references/model-template.md` and propose an adapter plan before writing code.

## Workflow

1. **Identify the model and execution boundary.** Record upstream source, revisions, weight source, licenses, input/output modalities, dependencies, and the required inference mode (see Key Concepts).
2. **Inspect the model reference.** Load the matching file under `references/models/`. If there is none, use `references/model-template.md` and create a proposed adapter plan before writing code. Do not invent model APIs, tensor shapes, tokenizer names, database paths, or license terms.
3. **Choose Jobs versus Model Serving.** Apply the Decision Framework above; a hybrid is often best.
4. **Define the serving contract before the wrapper.** Build the `input_example`, signature, and documented SDK + HTTP examples (see Best Practices §1).
5. **Package for reproducibility.** Pin and manifest all provenance-controlled inputs; test an offline startup path (see Best Practices §2–3).
6. **Implement and register.** Use the standard custom PyFunc pattern, add only the HLS adapter behavior, and register to Unity Catalog with a versioning/promotion strategy (see Best Practices §4–5).
7. **Validate scientifically and operationally.** Run at minimum: import/dependency smoke test; offline artifact and checksum test; wrapper initialization test; signature and `input_example` test; Python SDK and HTTP payload tests; a small known-input regression test; malformed-input and resource-limit tests; a serving or Job deployment test in the target runtime; and output sanity checks for the model family.

## Model-family references

Load only the relevant reference:

- `references/models/geneformer.md`
- `references/models/scgpt.md`
- `references/models/scimilarity.md`
- `references/models/alphafold-openfold.md`
- `references/models/boltz.md`

Add new families by copying `references/model-template.md`, adding one row to `references/models/index.md`, and documenting tests before changing this core file.

## AI Gateway and inference tables

When the user asks for gateway policies, usage tracking, or inference tables, first determine whether the selected endpoint and workspace support the requested feature, then enable only the supported configuration through the standard Databricks serving workflow. Apply the data-minimization rules in Best Practices §6 before logging any request or response.

## Maintenance and updates

See `references/maintenance.md` for update triggers, official-skill synchronization, versioning, CI checks, model-family onboarding, ownership, and review cadence. Keep model-specific facts in the reference file; keep reusable Databricks mechanics in the official generic skills. Update the model reference and changelog when upstream behavior changes; update this core file only when the shared routing or contract changes.

## Protocol Guidelines

Every new model reference should include:

1. Upstream and weight sources.
2. Immutable revision and license fields.
3. Input/output contract with examples.
4. Artifact and cache layout.
5. Dependency and accelerator requirements.
6. Serving-versus-Jobs recommendation.
7. Wrapper boundary and serialization rules.
8. Registration and deployment path.
9. Smoke, regression, and negative tests.
10. Open questions requiring deeper exploration.
11. Date reviewed and upstream version.

## Related Skills

- `databricks-ml-training` — generic custom PyFunc, signatures, dependency packaging, and Unity Catalog registration this guide builds on.
- `databricks-model-serving` — endpoint lifecycle, routing, and AI Gateway configuration for the serving path.
- `databricks-mlflow-evaluation` — evaluation mechanics for validating model outputs.

## References

- [Databricks custom PyFunc reference](https://github.com/databricks/devhub/blob/main/.databricks/aitools/skills/databricks-ml-training/references/custom-pyfunc.md)
- [Databricks Agent Skills documentation](https://docs.databricks.com/aws/en/agent-skills)
- [Genesis Workbench solution accelerator](https://github.com/databricks-industry-solutions/genesis-workbench)
- [MLflow custom Python model documentation](https://mlflow.org/docs/latest/ml/model/python_model/)
