# AlphaFold and OpenFold

## Identity and scope

AlphaFold-family workflows commonly combine sequence parsing, feature generation or MSA search, large databases, neural inference, relaxation, and structure postprocessing. AlphaFold, AlphaFold3, and OpenFold are not interchangeable adapters; confirm the exact implementation and license before packaging.

Reference sources:

* [AlphaFold](https://github.com/google-deepmind/alphafold)
* [OpenFold](https://github.com/aqlaboratory/openfold)
* [Genesis Workbench](https://github.com/databricks-industry-solutions/genesis-workbench)

## Inputs and outputs

For a bounded request, define sequence or structure inputs, chain metadata, optional templates/MSA settings, random seed, recycle or sampling controls, and output selection. Prefer a sequence string or governed FASTA/JSON URI over an unconstrained nested object.

Outputs are often structures, confidence metrics, rankings, and intermediate files. For serving, return metadata plus governed output URIs when the result is too large for a response. For Jobs, write a durable result bundle with manifest, structure files, scores, and runtime metadata.

### Input example (bounded, preprocessed inference request)

Field names are grounded in this file (sequence/chain inputs, template/MSA settings, random seed, recycle controls, output selection) and the transport-encoding table in `integration-contract.md` (FASTA → string or governed URI). The sequence is a placeholder — do not invent a real sequence, weights revision, or database version; `msa_mode` and `templates` values must match the pinned variant. `seed`, `recycles`, and `num_models` are user-chosen example controls. This shape assumes MSA/features are already prepared (heavy MSA search belongs in a Job).

```json
{
  "job_id": "fold-0001",
  "sequences": [{"chain_id": "A", "sequence": "<amino-acid-sequence>"}],
  "msa_uri": "<governed-msa-or-features-uri-or-null>",
  "msa_mode": "<precomputed-or-none>",
  "templates": false,
  "seed": 0,
  "recycles": 3,
  "num_models": 1,
  "output": "metadata_and_uri"
}
```

Return confidence metrics and a governed structure-result URI for serving; write the full structure bundle in a Job.

## Artifacts and runtime

Treat model parameters, MSA/template databases, chemical or structural libraries, code revision, and accelerator runtime as separate versioned inputs. Large databases usually belong in governed Volumes or another approved mounted location, not inside the MLflow model artifact.

Do not download databases or weights during a request. Validate mount paths, permissions, checksums, disk space, and database versions before registration or deployment.

## Deployment recommendation

Prefer Jobs or a hybrid workflow. CPU-heavy MSA and feature generation, multi-stage inference, relaxation, and artifact-heavy output are strong signals for Jobs. A serving endpoint may be appropriate only for a bounded, preprocessed, self-contained inference path with tested GPU startup and latency.

## Wrapper notes

Keep the PyFunc wrapper thin: validate request, resolve governed local artifacts, invoke a tested inference entry point, and publish results. Do not put an unbounded search, database build, or multi-minute orchestration loop inside `predict` without explicit platform validation.

Optional controls such as MSA mode, templates, recycles, seed, and output detail should be explicit inputs or a versioned JSON request. Test the actual SDK and endpoint behavior rather than assuming `params` is preserved.

## Validation

* sequence and chain parsing
* database and feature-generation smoke test
* known protein regression with confidence/output sanity checks
* malformed FASTA, unsupported residues, oversized sequences, and timeout behavior
* CPU/GPU and disk-space checks
* output-file integrity and manifest validation
* end-to-end Job retry and idempotency test

## Explore before implementation

* exact AlphaFold/OpenFold variant and task scope
* licensing and permitted use of code, weights, and databases
* whether the user needs monomer, multimer, complex, or design workflows
* database refresh and reproducibility policy
* whether results require scientific or clinical review
