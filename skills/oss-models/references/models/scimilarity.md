# Scimilarity

## Identity and scope

Scimilarity is a single-cell representation and similarity-search workflow. The adapter must keep model embedding, reference atlas/index access, query preprocessing, and nearest-neighbor search distinguishable because they may have different scaling and lifecycle requirements.

Reference sources:

* [Scimilarity code](https://github.com/Genentech/scimilarity)
* [Genesis Workbench](https://github.com/databricks-industry-solutions/genesis-workbench)

## Inputs and outputs

Define the gene identifier mapping, feature order, normalization, and filtering required for query cells. Make the reference index or atlas an explicit governed artifact or URI rather than an implicit local download.

A bounded serving request may contain a compact query representation and an index/version identifier. Dataset-scale queries should use a Job and write embeddings, neighbors, labels, and diagnostics to governed tables or files.

### Input example (bounded query-to-similarity request)

Field names are grounded in this file (query representation, index/version identifier, and the explicit `top_k` / distance metric / label-filtering controls from Wrapper notes) and the transport-encoding table in `integration-contract.md`. Placeholders `<...>` (gene IDs, index version) come from the pinned Scimilarity release and index build. `top_k` and `metric` are user-chosen example controls, not upstream-fixed APIs.

```json
{
  "query_id": "query-0001",
  "genes": ["<ensembl-gene-id-1>", "<ensembl-gene-id-2>", "<ensembl-gene-id-3>"],
  "expression": [8.0, 2.0, 1.0],
  "index_version": "<index-version>",
  "top_k": 10,
  "metric": "<distance-metric>",
  "label_filter": null
}
```

Return bounded ranked results (ids, distances, labels) plus index/preprocessing version metadata for serving; return large neighbor graphs or full embeddings through governed URIs.

## Artifacts and runtime

Version the model, preprocessing assets, reference atlas/index, and any search library separately. Record the index build inputs and checksum. Ensure the serving or Job identity can read the index without runtime internet access.

## Deployment recommendation

Use Model Serving for bounded query-to-similarity requests when the index fits the endpoint and update cadence is manageable. Use Jobs when querying large collections, rebuilding indexes, or generating reusable embeddings. A hybrid endpoint-plus-index Job is often preferable.

## Wrapper notes

Load the model and index once where possible. Keep index version and preprocessing version in the request/response metadata. Make top-k, distance metric, label filtering, and output selection explicit inputs unless `params` behavior is proven end to end.

Return bounded ranked results for serving; return large neighbor graphs or full embeddings through governed URIs. Do not hide a reference-atlas download in `predict`.

## Validation

* feature mapping and normalization equivalence with upstream
* known-cell nearest-neighbor regression
* index/model/preprocessing compatibility
* unknown genes, missing features, empty queries, and top-k bounds
* SDK/HTTP equivalence
* index access and startup behavior in the target runtime

## Explore before implementation

* exact Scimilarity release and index format
* whether the reference atlas may contain sensitive or proprietary data
* index update and rollback strategy
* latency and memory under concurrent queries
* whether similarity results are exploratory or used in a regulated workflow
