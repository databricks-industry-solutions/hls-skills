# Geneformer

## Identity and scope

Geneformer is a transformer family for single-cell transcriptomic representations and downstream tasks. Treat model versions, token dictionaries, preprocessing, and fine-tuned heads as separate compatibility dimensions.

Reference sources:

* [Geneformer code](https://github.com/jkobject/geneformer)
* [Geneformer model resources](https://huggingface.co/ctheodoris/Geneformer)

## Inputs and outputs

The adapter must define the expected gene identifiers, vocabulary version, ordering/ranking preprocessing, filtering, and any required metadata. Do not accept an arbitrary expression matrix and silently infer feature order.

Recommended serving boundary:

* small bounded requests: JSON configuration plus a compact encoded feature record or a governed URI
* larger single-cell collections: a Delta/Volume input URI processed by a Job
* outputs: embeddings, predictions, or a governed artifact URI with shape and feature metadata

Include an `input_example` that makes gene vocabulary and feature semantics visible. If the native library expects a dataset object, normalize from a documented table or JSON representation at the boundary.

### Input example (bounded single-cell request)

Field names below are grounded in this file and the transport-encoding table in `integration-contract.md`; every `<...>` is a placeholder that must be resolved from the pinned Geneformer release (do not invent vocabulary IDs, the token limit, or the pooling enum). `config` is a JSON string so the optional controls stay explicit rather than riding an untested `params=` path.

```json
{
  "cell_id": "cell-0001",
  "genes": ["<ensembl-gene-id-1>", "<ensembl-gene-id-2>", "<ensembl-gene-id-3>"],
  "expression": [12.0, 5.0, 3.0],
  "vocab_version": "<vocab-version>",
  "config": "{\"truncation\": true, \"gene_count_limit\": \"<max-input-tokens>\", \"pooling_mode\": \"<pooling-mode>\", \"output\": \"embedding\"}"
}
```

See `SKILL.md` (`## Example`) for the matching Python `input_example`, HTTP request, response shape, and provenance manifest.

## Artifacts and runtime

Pin the code revision, model checkpoint, tokenizer/vocabulary assets, and any fine-tuned head independently. Validate that the checkpoint and vocabulary are compatible before registration. Keep large collections and intermediate matrices outside the model artifact.

## Deployment recommendation

Prefer Jobs for dataset-scale embedding, preprocessing, or fine-tuning. Consider Model Serving for bounded single-cell requests only after measuring initialization, memory, concurrency, and payload limits.

## Wrapper notes

Load the tokenizer/vocabulary and model once. Make preprocessing explicit and testable. Optional controls such as truncation, gene-count limits, pooling mode, or output selection should be explicit inputs unless the exact SDK and serving path has proven `params` support.

## Validation

* verify vocabulary and feature-order compatibility
* compare a small known-input embedding or prediction against the upstream implementation
* test empty cells, unknown genes, duplicate genes, NaN values, and oversized requests
* test CPU/GPU behavior in the target runtime
* validate output dimensions and metadata

## Explore before implementation

* exact Geneformer release and checkpoint family
* whether the use case is embedding, classification, perturbation, or fine-tuning
* preprocessing requirements for the source assay and organism
* acceptable handling of donor or patient-derived data
* whether the model output is suitable for the intended scientific decision
