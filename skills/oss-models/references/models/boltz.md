# Boltz

## Identity and scope

Boltz-family workflows support biomolecular structure or interaction prediction with structured inputs that may include proteins, nucleic acids, ligands, templates, MSAs, constraints, and sampling settings. Confirm the exact Boltz release, task mode, and input schema before implementation.

Reference sources:

* [Boltz code](https://github.com/jwohlwend/boltz)
* [Genesis Workbench](https://github.com/databricks-industry-solutions/genesis-workbench)

## Inputs and outputs

The native workflow may use YAML or another structured configuration. Preserve that schema explicitly at the boundary or define a validated JSON equivalent. Document entity identifiers, sequences, ligand representation, constraints, templates/MSAs, seeds, sampling controls, and output selection.

For Model Serving, use a bounded JSON string or governed input URI and return compact scores plus governed structure-result URIs. For Jobs, retain the full configuration, intermediate files, structures, confidence metrics, and provenance manifest.

### Input example (bounded JSON equivalent of the native config)

The concept names below (entity identifiers, sequences, ligand representation, constraints, templates/MSAs, seed, sampling controls, output selection) are grounded in this file; the transport-encoding table in `integration-contract.md` routes the native YAML to a validated JSON string, so `config` carries the schema equivalent as a JSON string rather than mapping arbitrary DataFrame columns to a file. The exact key spellings and allowed entity types must match the pinned Boltz release — do not invent the schema, sequences, ligand SMILES, weights revision, or database versions. `seed` and `num_samples` are user-chosen example controls.

```json
{
  "job_id": "boltz-0001",
  "config": "{\"entities\": [{\"id\": \"A\", \"type\": \"<entity-type>\", \"sequence\": \"<amino-acid-sequence>\"}, {\"id\": \"L\", \"type\": \"<entity-type>\", \"ligand\": \"<ligand-smiles>\"}], \"constraints\": [], \"templates\": [], \"msa\": \"<precomputed-or-none>\"}",
  "seed": 0,
  "num_samples": 1,
  "output": "scores_and_uri"
}
```

Validate allowed keys, numeric bounds, entity references, and file/URI access before invoking inference. Return compact scores plus a governed structure-result URI for serving; retain the full bundle in a Job.

## Artifacts and runtime

Pin code, model weights, tokenizers or parsers, chemical/structure dependencies, and any MSA or template assets. Validate the license and redistribution terms for each source. Keep large databases and generated outputs in governed locations with explicit cache paths.

## Deployment recommendation

Prefer Jobs or hybrid orchestration for complex structures, multiple entities, sampling, MSA/template generation, and large output bundles. Use serving for a bounded, preprocessed request only after measuring startup, GPU memory, request limits, and response behavior.

## Wrapper notes

If the upstream CLI expects a YAML file, do not silently map arbitrary DataFrame columns to a file. Either accept a validated configuration string or create a documented typed request-to-YAML conversion layer. Validate allowed keys, numeric bounds, entity references, and file/URI access before invoking inference.

Make sampling count, seed, diffusion or recycling controls, and output format explicit inputs when they affect reproducibility. Use `params` only after end-to-end SDK and endpoint testing.

## Validation

* schema and entity-reference validation
* known complex regression with structural and confidence sanity checks
* invalid residues, malformed ligands, missing entities, and unsupported constraints
* deterministic seed behavior where promised
* GPU memory and timeout tests
* output bundle and manifest integrity
* Job retry, idempotency, and governed URI access

## Explore before implementation

* exact Boltz release and supported input schema
* whether the task is prediction, design, or interaction scoring
* ligand and database licensing
* required MSA/template assets and refresh policy
* whether result payloads contain proprietary or sensitive structures
