# oss-001 — Eval Report

**Generated**: 2026-10-01T07:36:08.621020+00:00
**Evalset**: v3.0.0
**Pair**: oss-001_TEDDY-70M_Deploy
**Task**: oss-001 | family: teddy | variant: 70M | difficulty: hard | vs: False
**Baseline NB**: oss-001_TEDDY-70M_Deploy_Baseline
**Skill NB**: oss-001_TEDDY-70M_Deploy_withSkills

## Phase Summary

| Phase | Baseline | Skill | Delta |
| --- | --- | --- | --- |
| download_staging | FAIL | PASS | skill wins |
| pyfunc_quality | FAIL | PASS | skill wins |
| model_registration | FAIL | PASS | skill wins |
| endpoint_deployment | FAIL | PASS | skill wins |
| smoke_tests | FAIL | PASS | skill wins |
| ai_search | PASS | PASS | same |
| edge_handling | PASS | PASS | same |
| forbidden_patterns | PASS | PASS | same |

## Category Summary

| Category | Baseline | Skill |
| --- | --- | --- |
| code_quality | 0% | 100% |
| model_lifecycle | 0% | 100% |
| validation | 0% | 100% |
| completeness | N/A | N/A |
| safety | 100% | 100% |

## Sub-check Breakdown

| Phase | Sub-check | Baseline | Skill | Delta |
| --- | --- | --- | --- | --- |
| download_staging | uses_tmp | FAIL | pass | << skill wins |
| download_staging | hf_xet_disabled | FAIL | pass | << skill wins |
| download_staging | deps_pinned | FAIL | pass | << skill wins |
| pyfunc_quality | pyfunc_class | pass | pass | same |
| pyfunc_quality | imports_inside_class | pass | pass | same |
| pyfunc_quality | load_context | pass | pass | same |
| pyfunc_quality | sys_modules_purge | FAIL | pass | << skill wins |
| pyfunc_quality | io_stringio | pass | pass | same |
| pyfunc_quality | artifacts_declared | FAIL | pass | << skill wins |
| pyfunc_quality | real_gene_ids | pass | pass | same |
| model_registration | infer_signature | pass | pass | same |
| model_registration | input_example | pass | pass | same |
| model_registration | pip_requirements | pass | pass | same |
| model_registration | pip_reqs_from_source | FAIL | pass | << skill wins |
| model_registration | mentions_70M | pass | pass | same |
| endpoint_deployment | sdk_enums | pass | pass | same |
| endpoint_deployment | ai_gateway_config | FAIL | pass | << skill wins |
| endpoint_deployment | scale_to_zero | pass | pass | same |
| endpoint_deployment | run_go_gate | pass | pass | same |
| smoke_tests | registration_smoke | FAIL | pass | << skill wins |
| smoke_tests | endpoint_query | pass | pass | same |
| smoke_tests | output_shape_check | pass | pass | same |
| forbidden_patterns | /local_disk0 | pass | pass | same |
| forbidden_patterns | transformers>= | pass | pass | same |
| forbidden_patterns | ENSG00000FAKE | pass | pass | same |
| forbidden_patterns | AutoCaptureConfigInput | pass | pass | same |
| forbidden_patterns | workload_type="GPU | pass | pass | same |

## Ship Gate

```
Paired tasks: 2 | wins: 1 | regressions: 0 | tie-pass: 0 | tie-fail: 1
win_rate: 0.50 | regression_rate: 0.00
SHIP GATE PASS

oss-001 [hard]: baseline=FAIL candidate=PASS -> win
    download_staging/deps_pinned: win
    download_staging/hf_xet_disabled: win
    download_staging/uses_tmp: win
    endpoint_deployment/ai_gateway_config: win
    model_registration/pip_reqs_from_source: win
    pyfunc_quality/artifacts_declared: win
    pyfunc_quality/sys_modules_purge: win
    smoke_tests/registration_smoke: win
oss-002 [hard]: baseline=FAIL candidate=FAIL -> tie-fail
    endpoint_deployment/sdk_enums: win
    pyfunc_quality/sys_modules_purge: regression
    smoke_tests/registration_smoke: win
```

## Development Log Comparison

No development log found in either arm.

## Delta Summary

* Skill wins: 8
  * download_staging/uses_tmp
  * download_staging/hf_xet_disabled
  * download_staging/deps_pinned
  * pyfunc_quality/sys_modules_purge
  * pyfunc_quality/artifacts_declared
  * model_registration/pip_reqs_from_source
  * endpoint_deployment/ai_gateway_config
  * smoke_tests/registration_smoke
* Baseline wins: 0
* Both fail: 0
