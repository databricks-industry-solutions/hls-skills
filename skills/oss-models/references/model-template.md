# HLS model reference template

Copy this file to `references/models/<model-family>.md` for a new model. Replace every placeholder and remove sections that do not apply.

## Identity

* Model family:
* Upstream code URL:
* Model card or documentation URL:
* Weight/checkpoint URL:
* Reviewed date:
* Upstream revision:
* Code license:
* Weight and database terms:

## What this model does

State the supported task in one paragraph. Distinguish research capability from clinical or regulatory validation.

## Inputs and outputs

Document the native inputs, the recommended Databricks transport representation, an `input_example`, the signature shape, and the output serialization. Include feature order and preprocessing requirements.

## Artifacts and runtime

List:

* code packages and pinned versions
* checkpoints and tokenizers
* reference databases
* cache directories
* CPU, memory, GPU, and storage expectations
* whether multiple processes or containers are required
* whether runtime internet access is prohibited or unnecessary

## Wrapper boundary

Describe `load_context`, request normalization, prediction, postprocessing, and failure behavior. State whether optional controls are explicit model inputs or tested `params`.

## Deployment recommendation

Choose Model Serving, Jobs, or hybrid. Explain the decision using latency, resource, request-size, database, and output-size constraints.

## Registration and observability

Describe the Unity Catalog model artifact and versioning approach. If AI Gateway inference tables or usage tracking are appropriate, specify what is safe to log and what must be redacted or represented by a governed URI.

## Validation

Include:

* import and offline-startup checks
* known-input regression case
* signature and payload tests
* malformed-input tests
* resource-limit tests
* target-runtime deployment test
* model-specific scientific sanity checks

## Open questions

List uncertainties that require upstream or platform exploration before implementation.
