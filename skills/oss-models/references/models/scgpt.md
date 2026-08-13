# scGPT

## Identity and scope

scGPT is a single-cell foundation-model family with model-version-specific tokenization, vocabulary, preprocessing, and downstream-task behavior. Treat checkpoint, vocabulary, task head, and data schema as a single compatibility contract.

Reference sources:

* [scGPT code](https://github.com/bowang-lab/scGPT)
* [scGPT model resources](https://huggingface.co/ PangboHu/scGPT)
* [Genesis Workbench](https://github.com/databricks-industry-solutions/genesis-workbench)

## Inputs and outputs

Document gene identifiers, vocabulary, expression representation, batch or tissue metadata, masking or perturbation configuration, and expected output type. A custom PyFunc should not accept a generic nested object without declaring how it is serialized.

For serving, prefer an explicit JSON request or a table-like representation that can be converted into the native data structure. For complex nested or sparse inputs, a split/orient JSON string or governed URI is often easier to validate than implicit nested DataFrame coercion.

Include examples for:

* one bounded cell or small batch
* a task configuration with optional controls as explicit fields
* the corresponding HTTP payload

### Input example (one bounded cell + task config)

Field names are grounded in this file (gene identifiers, expression representation, batch metadata, masking/perturbation configuration, output type) and the transport-encoding table in `integration-contract.md` (sparse row → tabular fields plus a JSON config string). Every `<...>` is a placeholder resolved from the pinned scGPT checkpoint and vocabulary — do not invent vocabulary IDs, the checkpoint task modes, or the mask token.

```json
{
  "cell_id": "cell-0001",
  "genes": ["<gene-symbol-or-id-1>", "<gene-symbol-or-id-2>", "<gene-symbol-or-id-3>"],
  "expression": [4, 1, 0],
  "vocab_version": "<vocab-version>",
  "batch_metadata": {"batch_id": "<batch-id>", "tissue": "<tissue-or-not-applicable>"},
  "task_config": "{\"task\": \"<embedding-or-annotation-or-perturbation>\", \"mask\": false, \"output\": \"embedding\"}"
}
```

For a nested or sparse input, prefer a split/orient JSON string or a governed URI over implicit nested-DataFrame coercion.

## Artifacts and runtime

Pin the model checkpoint, vocabulary, tokenizer/configuration, code revision, and any downstream head. Cache assets in a governed Volume or model artifact location and validate checksums during build or startup.

## Deployment recommendation

Use Jobs for large embedding, perturbation, or dataset workflows. Serving can fit bounded inference if model initialization and request serialization are stable. If the wrapper returns large matrices or annotations, return a governed URI and metadata rather than an oversized response.

## Wrapper notes

Load the model and tokenizer in `load_context`. Normalize transport inputs into the exact native structure and preserve feature order. Make options such as task, masking, perturbation configuration, sampling, or output selection explicit in the request contract when they change results.

The Genesis Workbench implementation is a useful pattern to inspect for custom PyFunc registration, Volume-backed checkpoints, complex input serialization, and serving examples, but verify all APIs against the selected upstream revision.

## Validation

* vocabulary and checkpoint compatibility
* feature-order and batch-metadata checks
* known-input regression for each supported task
* malformed JSON, unknown genes, empty cells, and oversized batches
* local PyFunc, SDK, and HTTP payload equivalence
* target-runtime GPU and startup test

## Explore before implementation

* exact upstream checkpoint and task mode
* whether the intended workflow is embedding, annotation, generation, or perturbation
* native support for the desired input object and serialization
* model license and permitted use
* whether inference tables can safely store any request or response fields
