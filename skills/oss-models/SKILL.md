---
name: oss-models
description: Package, register, validate, and deploy open-source health and life-sciences models on Databricks. Use for Geneformer, scGPT, Scimilarity, TEDDY, AlphaFold/OpenFold, Boltz, or similar models whose code, checkpoints, databases, tokenizers, or scientific inputs come from Hugging Face, Git, Zenodo, or other external sources. Use this skill when a request involves custom PyFunc wrappers, Unity Catalog registration, Model Serving, Jobs, GPU/runtime selection, complex biological inputs, provenance, or AI Gateway inference tables.
category: Bioinformatics
summary: Package, register, validate & deploy open-source HLS models on Databricks — e.g. TEDDY and Geneformer.
catalog_order: 40
version: 0.0.1
author: hengrumay
license: Databricks License
---

# HLS OSS Models

## Overview

This guide is a Health & Life Sciences (HLS) extension layer for packaging, registering, validating, and deploying open-source scientific models on Databricks. It does not reproduce generic MLflow or custom PyFunc mechanics — it supplies the model-family decisions that generic guidance cannot know: scientific preprocessing, checkpoint and database requirements, GPU and runtime constraints, serving-versus-Jobs suitability, provenance, and biological sanity checks. When the request needs standard logging, signatures, dependency packaging, Unity Catalog registration, Model Serving, or MLflow evaluation, use the existing Databricks ML training and Model Serving skills as the implementation foundation and layer this guide on top.

These six model families (single-cell; protein/biomolecular structure) are an initial, representative set. The skill is designed to extend — see `references/models/index.md` and `references/model-template.md` to add a family. Coverage grows as demand and validated models arrive.

## When to Use

- The request names an HLS model (Geneformer, scGPT, Scimilarity, TEDDY, AlphaFold/OpenFold, Boltz, or similar) whose code or weights come from an external source.
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
8. **Split the download notebook from the register-and-deploy notebook.** The model download requires only CPU and a stable write path; the dry-load test, MLflow logging, and registration require GPU. Separating them keeps each notebook independently re-entrant and avoids wasting GPU time on downloads. The download notebook writes to a UC Volume; the register/deploy notebook reads from it.
9. **Read `pip_requirements` from the model's own dependency spec, not from PyFunc class imports.** PyFunc imports show only the wrapper's direct dependencies; they miss the full import chain of any bundled package. Read `pyproject.toml`, `requirements.txt`, or `setup.cfg` from the source repository, then pin exact or bounded versions for packages known to have breaking APIs across releases (especially `transformers`, `numpy`, `pandas`, `anndata`). An unbounded `>=X.Y` resolved to a newer incompatible major version is a common cause of "A library raised an error during model load" failures in the serving container.
10. **On Serverless compute, write temporary files to `/tmp`, not `/local_disk0`.** `/local_disk0` is not available on Serverless CPU or GPU compute. `/tmp` is always writable on both Serverless and classic compute.
11. **Import every stdlib and third-party symbol used inside a PyFunc class explicitly in that class cell.** The serving container deserialises the class in a fresh Python process that has no knowledge of what the notebook imported. Even `sys`, `os`, `io`, and other stdlib modules must be imported inside the class cell — not only at the top of the notebook — or they will raise `NameError` in the serving container while the same code passes a local dry-load test (because notebook-session globals are shared within the kernel).
12. **Use file-based model logging (`python_model=<path>`) when the model code is shipped via `code_paths`, not pip-installed.** Passing a live instance (`python_model=wrapper`) triggers cloudpickle serialisation, which captures `import <package>` references. If the package is not pip-installable (only available via `code_paths`), the serving container will fail at unpickle time with `ModuleNotFoundError` because `cloudpickle.load()` runs **before** `code_paths` are placed on `sys.path`. The fix: write the PyFunc class to a standalone `.py` file, add `mlflow.models.set_model(MyWrapper())` at module level, and pass `python_model=<path_to_wrapper.py>` to `log_model`. This makes MLflow import the file directly after `code_paths` are on `sys.path`, bypassing cloudpickle entirely. This applies to all HLS models whose source code is bundled (TEDDY, Geneformer custom tokenizers, scGPT, etc.).
13. **Use SDK enum classes for endpoint configuration, not string literals.** When setting `workload_type`, use `ServingModelWorkloadType.GPU_SMALL` (from `databricks.sdk.service.serving`), not the string `"GPU_SMALL"`. String literals bypass SDK validation and can silently produce invalid configs. The same principle applies to other typed fields: `EndpointStateReady`, `EndpointStateConfigUpdate`, `ServedModelStateDeployment`, etc.
14. **Construct test payloads from the declared signature, not from "typical" template code.** Before running a smoke test against a deployed endpoint, read the model's MLflow signature and ensure every required field is present with the correct type. A missing required column (e.g. `adata_obs`) produces a schema-enforcement `BadRequest` that is distinct from the model logic itself. Use real input values from the model's vocabulary or reference data — synthetic values that map to the OOV token produce degenerate outputs that cannot validate the tokenisation path.

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
8. **Hugging Face Xet storage backend causes IO errors during download.** Some HF repos use HF's Xet/CAS storage backend, which performs parallel seeks and fails with `RuntimeError: CAS service error: IO Error: Illegal seek (os error 29)` in environments that do not support it (including Serverless).
   - *How to avoid*: Set `os.environ["HF_HUB_DISABLE_XET"] = "1"` **before** the first `import huggingface_hub` in the process. If `huggingface_hub` was already imported in the session, restart the Python kernel first so the env var takes effect before the library initialises. Check the repo's `.gitattributes` for `filter=xet` to detect Xet-backed files before downloading.
9. **Unpinned `transformers>=X.Y` resolves to 5.x and breaks 4.x models.** Transformers 5.x restructured `PreTrainedModel._move_missing_keys_from_meta_to_device` to call `self.all_tied_weights_keys.keys()` where 4.x used `_tied_weights_keys` (a list). An unbounded `pip_requirements` entry resolves to the latest release in the serving container, silently introducing the incompatibility. This surfaces as `AttributeError: 'Model' object has no attribute 'all_tied_weights_keys'` in the service logs — not the build logs.
   - *How to avoid*: Always pin `transformers` to the version from the model's own `pyproject.toml`. Validate by reading that file from the source repo, not by inspecting PyFunc class imports.
9b. **`get_head_mask` removed in transformers ≥4.52.** `geneformer.py` (BioNeMo) calls `self.get_head_mask()`, removed from `PreTrainedModel` in 4.52. Surfaces as `AttributeError: 'BertModel' object has no attribute 'get_head_mask'` — same root cause as #9 (unpinned transformers) but a different breaking change within the 4.x series.
    - *How to avoid*: Pin `transformers>=4.30.0,<4.52.0` in `pip_requirements` **and** add a runtime shim that patches the method back onto `PreTrainedModel` inside `load_context` as a safety net.
10. **Deployment failure diagnosis requires service logs, not build logs.** Build logs only show Docker/pip installation steps. The Python traceback from a model-load failure appears in the *service logs*.
    - *How to find service logs*: `GET /api/2.0/serving-endpoints/{name}/served-entities/{entity-name}/logs?config_version={n}` where `n` is `endpoint.pending_config.config_version` for a failed update (the default `config_version=0` targets the currently active config, not the failed pending one). Databricks CLI: `databricks api get "/api/2.0/serving-endpoints/{name}/served-entities/{entity-name}/logs?config_version={n}"`.
11. **Stale `sys.modules` cache causes `ModuleNotFoundError` after out-of-order cell execution.** When cells run out of order across multiple kernel executions, a partial import of a bundled package can persist in `sys.modules`. Subsequent runs resolve submodule lookups against the stale cached object rather than the freshly staged code bundle.
    - *How to avoid*: Purge `package.*` entries from `sys.modules` in **two places**: (a) at cell level before any `from <package> import ...` statement in the notebook, and (b) at the top of `load_context` inside the PyFunc wrapper. The cell-level purge catches notebook re-execution issues; the `load_context` purge makes the dry-load test cell safe (it imports the package in the same kernel as the class cell). The serving container starts clean, so the `load_context` purge is a no-op there — but it costs nothing and prevents a class of hard-to-debug failures. Also re-insert the bundle path at position 0 in `sys.path` after purging.
12. **`pd.read_json` treats a literal JSON string as a file path in newer pandas.** Pandas 2.1+ deprecated passing a raw JSON string directly and may raise `FileNotFoundError` treating the content as a path.
    - *How to avoid*: Always wrap with `io.StringIO`: `pd.read_json(io.StringIO(json_string), orient="split")`. Import `io` explicitly inside the PyFunc class cell.
13. **`serving_endpoints.query()` uses `extra_params`, not `params`.** The Databricks Python SDK's `serving_endpoints.query()` signature uses `extra_params: Optional[Dict[str, str]]`, not `params`. Values must be strings.
    - *How to avoid*: Pass `extra_params={"max_seq_len": "2048", "pooling": "mean"}` (string values). The PyFunc `predict` method should cast on receipt: `int(params.get("max_seq_len", 2048))`, `str(params.get("pooling", "mean"))`.
14. **Use a `run_go` widget gate for expensive operations.** Endpoint creation, model deployment, and VS index creation cost real money. A widget gate (`dbutils.widgets.dropdown("run_go", "false", ["false", "true"])`) prevents accidental execution in shared notebooks.
    - *How to implement*: Read `RUN_GO = dbutils.widgets.get("run_go") == "true"` early; wrap all side-effect cells with `if not RUN_GO: print("run-gate off"); ...`.
15. **Use sentinel files for idempotent re-runs.** Downloads and copies to UC Volumes should be idempotent — check for a sentinel file (e.g. `.copy_complete`, `.snapshot_complete`) before repeating expensive operations.
    - *How to implement*: Write a sentinel after successful completion; check for it at the start of the cell.
16. **Use adaptive storage paths.** `/local_disk0` is unavailable on Serverless compute. Detect the environment at runtime and fall back to `/tmp`.
    - *How to implement*: `try: os.makedirs("/local_disk0/tmp", exist_ok=True); TMP_DIR = "/local_disk0/tmp" except (PermissionError, OSError): TMP_DIR = "/tmp"`.
17. **Write a provenance manifest alongside the model.** Record model name, source URL, code URL, license, download date, compute type, and runtime requirements in a YAML manifest stored next to the model weights in the UC Volume.
18. **`flash-attn` requires GPU at import time.** Models that depend on `flash-attn` (e.g. scGPT) cannot be imported on CPU-only compute. Both the registration notebook and the serving container must have GPU access.
    - *How to avoid*: Use GPU compute for registration notebooks; specify `GPU_SMALL` for serving endpoints.
19. **`cloudpickle.load()` fails with `ModuleNotFoundError` for non-pip code bundles.** When `python_model=<instance>` is used with `code_paths`, cloudpickle serialises the wrapper and captures `import <package>` references. At load time in the serving container, `cloudpickle.load()` runs **before** MLflow places `code_paths` on `sys.path`, so any import of a bundled (non-pip) package raises `ModuleNotFoundError`. The error appears in service logs as `[mlflow_parse] ModuleNotFoundError: No module named '<package>'` with `category: user_dep_missing`. A local dry-load test will NOT catch this because the notebook kernel already has the package on `sys.path`.
    - *How to avoid*: Use file-based logging: write the PyFunc class to a standalone `.py` file, add `mlflow.models.set_model(MyWrapper())` at module level, and pass `python_model=<path_to_file>` to `log_model`. See Best Practices §12.
20. **Google Drive downloads via `gdown` may be unreliable.** `gdown` depends on Google Drive sharing permissions and rate limits. Verify downloads by checking file size and presence of sentinel files.
    - *How to avoid*: Use sentinel files; implement file-size checks after download; consider mirroring to a UC Volume for CI reliability.
21. **C++/CUDA library required at import time but cannot build on Serverless.** Some models depend on libraries that require a full CUDA toolkit for source compilation (e.g. NVIDIA TransformerEngine for BioNeMo Geneformer). These fail with a CMake/wheel build error on Serverless GPU (no dev toolchain) and in Model Serving containers.
    - *How to avoid*: Inspect the library's usage in the model code. If it provides standard PyTorch modules (Linear, LayerNorm, MultiheadAttention), write **functional `nn.Module` stubs** that match the constructor signature and weight-key names from the safetensors state dict, then inject them into `sys.modules` before `from_pretrained`. Install stubs in **both** the notebook setup cell and inside `load_context` (the serving container has no prior kernel state). Mark stubs with `__version__ = "0.0.0-stub"` so they can be distinguished from the real library. See `references/models/geneformer.md` for a complete worked example.
22. **`sys.stdout.isatty()` crash in Model Serving containers.** The serving container replaces `sys.stdout` with `StreamToLogger`, which lacks `isatty()`. Libraries like `transformers` call `sys.stdout.isatty()` during model loading and crash with `AttributeError`.
    - *How to avoid*: In `load_context`, before any model loading: `for stream in (sys.stdout, sys.stderr): if stream is not None and not hasattr(stream, "isatty"): stream.isatty = lambda: False`.
23. **Inference table name conflict blocks endpoint creation.** Model Serving auto-generates an inference table named `<endpoint>_payload`. If that table already exists from a prior failed deploy (even if the endpoint was deleted), `create_endpoint` fails with a conflict error.
    - *How to avoid*: Use a timestamped inference table prefix in `AiGatewayInferenceTableConfig`. **Always** use `AiGatewayConfig` (not the deprecated `AutoCaptureConfigInput`) when creating endpoints:
    ```python
    from databricks.sdk.service.serving import (
        AiGatewayConfig, AiGatewayInferenceTableConfig, AiGatewayUsageTrackingConfig,
    )
    ai_gateway = AiGatewayConfig(
        inference_table_config=AiGatewayInferenceTableConfig(
            catalog_name=CATALOG, schema_name=SCHEMA,
            table_name_prefix=f"{endpoint_name}_{datetime.now():%Y%m%d%H%M}",
            enabled=True,
        ),
        usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
    )
    w.serving_endpoints.create(name=endpoint_name, config=endpoint_config, ai_gateway=ai_gateway)
    ```
24. **Endpoint provisioning timeout with no early failure detection.** GPU endpoints (A10G) routinely take 15–25 min to provision. A naïve polling loop with a fixed timeout wastes time waiting on already-failed deployments.
    - *How to avoid*: Poll with a 1800 s timeout (30 min) and check `ServedModelStateDeployment.DEPLOYMENT_FAILED` on each iteration. Raise immediately with the deployment state message instead of waiting for the full timeout.
25. **Model forward output keys differ from documentation or expected conventions.** Custom HLS models may return pre-pooled embeddings under non-standard dict keys (e.g. `cell_emb` instead of `all_embs` or `last_hidden_state`). The wrapper’s embedding extraction silently returns `None`, which surfaces later as `unsupported operand type(s) for *: 'NoneType' and 'Tensor'` in the pooling step.
    - *How to avoid*: **Always run a runtime diagnostic** before writing the extraction logic: call `model(**fwd_kwargs)` once and print `type(outputs)`, `outputs.keys()` (for dicts), and shape/dim of each value. Check the model reference (`references/models/<model>.md`) for the verified output key. If the output is already 2D (pre-pooled), skip external pooling with a `dim() == 2` guard. Also verify which parameters `forward()` actually accepts via `inspect.signature(model.forward).parameters.keys()` — unused kwargs are silently filtered but worth documenting.
    - *Discovered*: oss-002 v2 (2026-10-01). TEDDY 70M returns `{"cell_emb": tensor(cells, d_model)}`. See `references/models/teddy.md` §Forward output key.

## Workflow

1. **Identify the model and execution boundary.** Record upstream source, revisions, weight source, licenses, input/output modalities, dependencies, and the required inference mode (see Key Concepts).
2. **Inspect the model reference.** Load the matching file under `references/models/`. If there is none, use `references/model-template.md` and create a proposed adapter plan before writing code. Do not invent model APIs, tensor shapes, tokenizer names, database paths, or license terms.
3. **Choose Jobs versus Model Serving.** Apply the Decision Framework above; a hybrid is often best.
4. **Define the serving contract before the wrapper.** Build the `input_example`, signature, and documented SDK + HTTP examples (see Best Practices §1).
5. **Package for reproducibility.** Pin and manifest all provenance-controlled inputs. Read `pip_requirements` from the model's own dependency specification (`pyproject.toml`, `requirements.txt`, or `setup.cfg`) rather than inferring them from PyFunc class imports — the PyFunc imports miss the bundled package's full import chain (see Best Practices §9). Test an offline startup path (see Best Practices §2–3).
6. **Implement and register.** Use the standard custom PyFunc pattern, add only the HLS adapter behavior, and register to Unity Catalog with a versioning/promotion strategy (see Best Practices §4–5).
7. **Validate scientifically and operationally.** Run at minimum: import/dependency smoke test; offline artifact and checksum test; wrapper initialization test; signature and `input_example` test; Python SDK and HTTP payload tests; a small known-input regression test; malformed-input and resource-limit tests; a serving or Job deployment test in the target runtime; and output sanity checks for the model family.

## Model-family references

Load only the relevant reference:

- `references/models/geneformer.md`
- `references/models/scgpt.md`
- `references/models/scimilarity.md`
- `references/models/alphafold-openfold.md`
- `references/models/boltz.md`
- `references/models/teddy.md`

Add new families by copying `references/model-template.md`, adding one row to `references/models/index.md`, and documenting tests before changing this core file.

## AI Gateway and inference tables

Inference tables are a **best-practice default** for HLS model endpoints — enable them proactively during endpoint creation, not only when the user explicitly asks. Scientific models handle sensitive biological data (gene expression profiles, protein sequences, patient-derived cell metadata) where observability, audit trails, and payload governance are essential. Include the `ai_gateway` configuration with `inference_table_config.enabled=True` and `usage_tracking_config.enabled=True` in the `serving_endpoints.create()` call. For the implementation pattern (SDK classes, existing-gateway preservation, payload verification), load `machine-learning/ai-gateway-deployment.md` from the official model-serving sub-skill. For existing endpoints that lack an inference table, attach one via `serving_endpoints.put_ai_gateway()`.

The generic `databricks-model-serving` skill says "do not add AI Gateway features automatically" — that conservative default is appropriate for ordinary sklearn/XGBoost deployments but **does not apply to HLS models** covered by this skill. When there is a tension between the generic skill and this domain-specific guidance, this skill takes precedence for models in scope.

Before enabling inference tables, apply the data-minimization rules in Best Practices §6: classify sequence, structure, patient, donor, and compound data in the payload; minimize or redact sensitive fields; log a hash, metadata record, or governed URI instead of raw inputs; define retention, access, and masking rules; and confirm the inference-table catalog is backed by external storage (default-storage catalogs are not supported). Document the data-governance review alongside the endpoint configuration.

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

## Guardrails

1. Pin every provenance-controlled input — code, weights, tokenizer, scientific database, and configuration — to an immutable commit SHA or content-addressed release with a recorded checksum; never trust a git tag, `latest` URL, or mutable branch, since tags can be re-pointed.
2. Download weights, tokenizers, and reference databases at build time into a governed Volume or model artifact location; never fetch them at request time, and test an offline / network-restricted startup path.
3. Never log raw sensitive payloads — patient, donor, sequence, structure, or compound data — to inference tables; classify and minimize/redact first, and log a hash, metadata record, or governed URI instead of the raw input.
4. Honor and record both the model AND the dataset/weights licenses in the manifest before packaging or distributing; treat an unknown license as blocking, not as a default-permit.
5. Validate the exact serving serializer against the deployed endpoint before depending on an SDK `params=` path, arrays, or nested lists; prefer explicit fields/columns for controls.
6. When a model name is ambiguous, stop and ask for the exact upstream project (repository, package, model card) rather than guessing tensor shapes, tokenizer names, database paths, or APIs.
7. Never treat a green technical deployment as scientific or clinical validity; report technical validation separately and defer scientific, clinical, and regulatory sign-off to the appropriate review.

## References

- [Databricks custom PyFunc reference](https://github.com/databricks/devhub/blob/main/.databricks/aitools/skills/databricks-ml-training/references/custom-pyfunc.md)
- [Databricks Agent Skills documentation](https://docs.databricks.com/aws/en/agent-skills)
- [Genesis Workbench solution accelerator](https://github.com/databricks-industry-solutions/genesis-workbench)
- [MLflow custom Python model documentation](https://mlflow.org/docs/latest/ml/model/python_model/)
