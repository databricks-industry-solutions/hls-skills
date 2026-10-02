# HLS adapter integration contract

Use this file with the official Databricks ML training, Model Serving, Python SDK, and MLflow evaluation skills. It defines the HLS-specific contract without duplicating their general tutorials.

## Adapter responsibilities

A model adapter must:

* accept only declared inputs
* convert transport representations into the model's native types
* load heavyweight state once during initialization
* avoid network access during prediction
* return a stable JSON-compatible result or governed artifact references
* expose enough metadata to reproduce the run
* fail with actionable errors for invalid inputs and missing artifacts

A typical custom PyFunc boundary is conceptually:

```python
class HLSModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        self.manifest = load_manifest(context.artifacts["manifest"])
        self.model = load_model_from_local_artifacts(context.artifacts)

    def predict(self, context, model_input, params=None):
        request = normalize_request(model_input)
        validate_request(request, self.manifest)
        result = self.model.predict(request)
        return serialize_result(result)
```

The exact model API, input types, and serialization must come from the model reference and upstream source. Do not copy this pseudocode as a complete implementation.

## Request-shape rules

Use explicit fields for meaningful controls such as sequence length, number of samples, temperature, recycling count, seed, ranking method, or output format. If a control changes scientific behavior, it should be visible in the signature or in a versioned request object.

Use `params` only after testing all of the following on the exact path:

* local `mlflow.pyfunc` invocation
* MLflow serving input validation
* Databricks Model Serving HTTP request
* the selected Databricks SDK or client

If any path drops or reshapes optional parameters, move them into the declared model input, usually as a scalar column or a JSON configuration field. Document the compatibility decision in the model reference.

## Common transport encodings

| Native value | Recommended boundary | Required validation |
| --- | --- | --- |
| Short sequence | string field | alphabet, length, and missing-value checks |
| FASTA | string or governed URI | header, sequence count, size, and format checks |
| AnnData or sparse matrix | split/orient JSON, tabular fields, or governed URI | feature order, dimensions, sparsity, and schema checks |
| Nested constraints | JSON string | schema, allowed keys, and numeric bounds |
| Protein/ligand structure | text, base64, or governed URI | format, size, and sanitization checks |
| Large result | governed output URI plus metadata | identity, retention, and access checks |

Generate an `input_example` for every selected transport shape. Include at least one Python dictionary, one SDK-friendly payload, and one HTTP-compatible payload where they differ.

## Provenance manifest

Store a machine-readable manifest next to the model or in a linked governed location. At minimum include:

```yaml
model:
  name: <canonical-name>
  upstream_revision: <immutable-commit-or-release>
  reviewed_at: <YYYY-MM-DD>
code:
  source_url: <url>
  revision: <commit-or-tag>
weights:
  source_url: <hf-git-zenodo-or-approved-mirror-url>
  revision_or_record: <immutable-reference>
  sha256: <checksum>
license:
  code: <license-or-unknown>
  weights: <license-or-unknown>
  databases: <terms-or-not-applicable>
runtime:
  python: <version>
  accelerator: <cpu-gpu-or-specific-family>
  network_required_at_runtime: false
artifacts:
  - name: <artifact>
    location: <governed-volume-or-model-artifact>
    sha256: <checksum>
```

Never mark unknown license, checksum, or source revision as verified. Route unresolved items to human review.

## Jobs and serving boundary

A serving adapter should be small and bounded. Put database construction, MSA search, docking loops, diffusion trajectories, large-batch preprocessing, and artifact-heavy postprocessing in Jobs unless the target platform explicitly supports the required workload.

For a hybrid design, document:

* the serving request and response contract
* the Job input/output contract
* the shared artifact or URI handoff
* retry and idempotency behavior
* identity and permission boundaries
* how inference metadata is linked across stages

## AI Gateway and inference tables

Use gateway policies and inference tables only when supported by the endpoint and workspace configuration. Apply data minimization before enabling request/response capture. For HLS data, review whether sequences, structures, donor identifiers, patient-derived features, compounds, or generated outputs are sensitive or proprietary.

Prefer logging metadata, hashes, request IDs, governed URIs, and validation outcomes over raw scientific payloads when the raw payload is not needed for debugging or audit. Document retention and access controls in the deployment plan.
