# Maintaining the HLS OSS model skill

This guide keeps the HLS extension current without copying generic Databricks ML guidance into every model reference.

## 1. Treat the skill as a small maintained product

Maintain three layers separately:

* `SKILL.md`: stable routing, shared decision rules, and the adapter contract.
* `references/integration-contract.md`: HLS-specific serving, provenance, and validation rules shared by model families.
* `references/models/<model>.md`: model-specific facts, examples, caveats, and tests.

When a change applies to ordinary MLflow or Model Serving generally, update or link to the official Databricks skill instead of duplicating it here. When a change applies to one model family, update only that model reference.

## 2. Update triggers

Open a maintenance change when any of these occur:

* Databricks changes MLflow, Model Serving, Python SDK, Unity Catalog, AI Gateway, inference-table, Jobs, or runtime behavior.
* The official `databricks-ml-training` or Model Serving skill changes its custom PyFunc contract.
* An upstream model releases a new checkpoint, tokenizer, API, license, runtime requirement, or input format.
* A Hugging Face, Git, Zenodo, or mirror URL becomes mutable, unavailable, rate-limited, or changes its terms.
* A GPU, CUDA, Python, dependency, security, or supply-chain issue affects a supported model.
* A stress test exposes a missing decision, incorrect payload, weak trigger, or unnecessary duplication.
* Genesis Workbench or another validated accelerator introduces a reusable deployment pattern.

Do not update merely because a model has a new paper or release. First determine whether the change affects packaging, inputs, execution mode, scientific correctness, security, or reproducibility.

## 3. Add a model family

Copy `references/model-template.md` to `references/models/<canonical-name>.md`, then add one registry row to `references/models/index.md`.

Before merging, populate:

* canonical name, aliases, and upstream URLs
* code revision, weight revision or record, checksums, and licenses
* tokenizer, vocabulary, database, and cache requirements
* native input/output types and transport encodings
* `input_example`, signature, SDK payload, and HTTP payload
* optional-parameter strategy and tested client paths
* wrapper initialization and prediction boundary
* GPU, memory, runtime, and filesystem requirements
* Jobs, Serving, or hybrid recommendation
* registration and deployment path
* known failure modes and open questions
* smoke, regression, negative, and resource-limit tests
* `reviewed_at`, upstream version, and skill version

If upstream behavior is not verified, label it `unverified` and add an exploration item. Never fill gaps with plausible API names or undocumented tensor shapes.

## 4. Keep facts separate from recommendations

Every model reference should distinguish:

* `Verified facts`: observed in upstream source, model card, release asset, or a validated Databricks run.
* `Databricks recommendation`: the proposed packaging, serving, or Jobs design.
* `Open exploration`: behavior that requires a targeted experiment or owner review.

This prevents an implementation preference from being mistaken for upstream model behavior.

## 5. Choose an update strategy for official Databricks guidance

Use one of these approaches:

* Link-through: preferred. Keep the official generic skill as the source of truth and link to its current reference.
* Compatibility summary: keep only the small checklist needed when the generic skill is unavailable, and record the source URL and review date.
* Snapshot: use only when reproducibility requires a frozen copy. Record the source commit, snapshot date, and an explicit review owner.

Do not silently fork `custom-pyfunc.md`. If its guidance changes, compare the source revision, identify the HLS impact, update the integration contract only where needed, and add a regression test.

## 6. Use versioning and a changelog

Version the HLS skill independently from upstream models and Databricks runtimes.

* Major: trigger semantics, adapter contract, or deployment decision rules change.
* Minor: a new model family, source type, deployment pattern, or test group is added.
* Patch: factual correction, link repair, example fix, or wording clarification.

Each release entry should include:

* skill version and date
* changed files
* affected model families
* upstream and Databricks versions reviewed
* behavior or trigger changes
* new or changed tests
* migration notes, if any
* reviewer and unresolved risks

Example metadata:

```yaml
skill_version: 0.3.0
reviewed_at: 2026-08-12
generic_skill_source:
  name: databricks-ml-training
  source_url: https://github.com/databricks/devhub/blob/main/.databricks/aitools/skills/databricks-ml-training/references/custom-pyfunc.md
  source_revision: <commit-or-release>
models:
  - name: scgpt
    upstream_revision: <commit-or-release>
    status: verified
```

## 7. Automate cheap checks

Run these checks on every change:

* frontmatter parses and `name`/`description` remain valid
* every referenced file exists
* every model registry entry points to one reference file
* every reference contains required headings
* links resolve or are explicitly marked pending review
* code fences and YAML examples parse
* no credentials, tokens, or unpinned `latest` weight URLs are present
* source/weight manifests contain revision, checksum, and license fields
* model references do not duplicate the generic PyFunc tutorial

Run model-specific tests only when that model reference or a shared contract changes. Run the full trigger and A/B/C evaluation suite for changes to `SKILL.md`, routing language, or shared integration rules.

## 8. Maintain a small evaluation corpus

Store versioned prompts and expected criteria rather than only a pass/fail transcript. Include:

* explicit HLS model requests
* natural-language requests with no model name
* generic PyFunc requests that must route away
* Hugging Face, Git, Zenodo, and governed-mirror cases
* SDK versus HTTP optional-parameter cases
* complex scientific inputs
* Serving, Jobs, and hybrid deployment cases
* unknown-model and incomplete-provenance cases
* AI Gateway/inference-table governance cases

For each prompt, record the Genie Code version, enabled skills, skill version, loaded skill files, tool calls, answer, and evaluator score. Compare:

* A: generic Databricks skills plus HLS skill
* B: skills disabled
* C: generic skills enabled but HLS skill disabled

A new HLS reference should improve its target cases without increasing false triggering on generic ML requests.

## 9. Recommended update workflow

1. Open an issue with the trigger, source, affected model(s), and expected behavior.
2. Pin and inspect the upstream code, weights, release notes, and license terms.
3. Classify the change as core, shared contract, or model-specific.
4. Update the smallest applicable file.
5. Add or revise payload examples and provenance metadata.
6. Add a regression test before changing expected behavior.
7. Run static checks, model tests, and the relevant A/B/C evaluation slice.
8. Review security, licensing, data governance, and clinical-use boundaries.
9. Update the changelog and review metadata.
10. Publish the new skill revision and start a fresh Genie Code chat for validation.

## 10. Ownership and review cadence

Assign ownership at two levels:

* Platform owner: generic Databricks integration, runtime, SDK, Serving, Jobs, UC, and AI Gateway behavior.
* Model owner: upstream API, weights, scientific inputs/outputs, licensing, and model-specific tests.

Use event-driven updates for security, breaking upstream releases, and platform changes. Otherwise, review each model reference at least quarterly and review the generic-skill compatibility summary whenever the linked Databricks skill changes.

## Sources

* [Databricks Agent Skills documentation](https://docs.databricks.com/aws/en/agent-skills)
* [Databricks custom PyFunc reference](https://github.com/databricks/devhub/blob/main/.databricks/aitools/skills/databricks-ml-training/references/custom-pyfunc.md)
* [MLflow custom Python model documentation](https://mlflow.org/docs/latest/ml/model/python_model/)
* [Genesis Workbench solution accelerator](https://github.com/databricks-industry-solutions/genesis-workbench)
