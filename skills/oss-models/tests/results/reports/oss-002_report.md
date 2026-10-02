# oss-002 — Eval Report

**Generated**: 2026-10-01T17:19:47.219234+00:00
**Evalset**: v3.0.0
**Pair**: oss-002_TEDDY-70M+VS_Deploy_v2
**Task**: oss-002 | family: teddy | variant: 70M | difficulty: hard | vs: True
**Baseline NB**: oss-002_TEDDY-70M+VS_Deploy_Baseline
**Skill NB**: oss-002_TEDDY-70M+VS_Deploy_withSkills_v2

## Phase Summary

| Phase | Baseline | Skill | Delta |
| --- | --- | --- | --- |
| download_staging | PASS | PASS | same |
| pyfunc_quality | PASS | PASS | same |
| model_registration | FAIL | PASS | skill wins |
| endpoint_deployment | FAIL | PASS | skill wins |
| smoke_tests | FAIL | PASS | skill wins |
| ai_search | PASS | PASS | same |
| edge_handling | PASS | PASS | same |
| forbidden_patterns | PASS | PASS | same |

## Category Summary

| Category | Baseline | Skill |
| --- | --- | --- |
| code_quality | 100% | 100% |
| model_lifecycle | 0% | 100% |
| validation | 0% | 100% |
| completeness | 100% | 100% |
| safety | 100% | 100% |

## Sub-check Breakdown

| Phase | Sub-check | Baseline | Skill | Delta |
| --- | --- | --- | --- | --- |
| download_staging | uses_tmp | pass | pass | same |
| download_staging | hf_xet_disabled | pass | pass | same |
| download_staging | deps_pinned | pass | pass | same |
| pyfunc_quality | pyfunc_class | pass | pass | same |
| pyfunc_quality | imports_inside_class | pass | pass | same |
| pyfunc_quality | load_context | pass | pass | same |
| pyfunc_quality | sys_modules_purge | pass | pass | same |
| pyfunc_quality | io_stringio | pass | pass | same |
| pyfunc_quality | artifacts_declared | pass | pass | same |
| pyfunc_quality | real_gene_ids | pass | pass | same |
| model_registration | infer_signature | pass | pass | same |
| model_registration | input_example | pass | pass | same |
| model_registration | pip_requirements | pass | pass | same |
| model_registration | pip_reqs_from_source | FAIL | pass | << skill wins |
| model_registration | mentions_70M | pass | pass | same |
| endpoint_deployment | sdk_enums | FAIL | pass | << skill wins |
| endpoint_deployment | ai_gateway_config | FAIL | pass | << skill wins |
| endpoint_deployment | scale_to_zero | pass | pass | same |
| endpoint_deployment | run_go_gate | pass | pass | same |
| smoke_tests | registration_smoke | FAIL | pass | << skill wins |
| smoke_tests | endpoint_query | pass | pass | same |
| smoke_tests | output_shape_check | pass | pass | same |
| ai_search | index_creation | pass | pass | same |
| ai_search | embedding_dim | pass | pass | same |
| ai_search | graceful_skip | pass | pass | same |
| forbidden_patterns | /local_disk0 | pass | pass | same |
| forbidden_patterns | transformers>= | pass | pass | same |
| forbidden_patterns | ENSG00000FAKE | pass | pass | same |
| forbidden_patterns | AutoCaptureConfigInput | pass | pass | same |
| forbidden_patterns | workload_type="GPU | pass | pass | same |

## Ship Gate

```
Paired tasks: 2 | wins: 2 | regressions: 0 | tie-pass: 0 | tie-fail: 0
win_rate: 1.00 | regression_rate: 0.00
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
oss-002 [hard]: baseline=FAIL candidate=PASS -> win
    endpoint_deployment/ai_gateway_config: win
    endpoint_deployment/sdk_enums: win
    model_registration/pip_reqs_from_source: win
    smoke_tests/registration_smoke: win
```

## Development Log Comparison

| Metric | Baseline | Skill | Delta |
| --- | --- | --- | --- |
| Unique bugs | 12 | 7 | -5 |
| Fix iterations | 15 | 7 | -8 |
| Cells needing fixes | 6 | 5 | -1 |
| Model versions | 5 | 3 | -2 |
| Fix entries | 12 | 7 | -5 |

### Baseline Fixes

| # | Cell | Iterations | Error |
| --- | --- | --- | --- |
| 1 | 7,8 | 3 | `AttributeError: 'list' has no 'keys'` |
| 2 | 8 | 2 | `RecursionError` on re-run |
| 3 | 9 | 1 | `TypeError: missing arg 'name'` |
| 4 | 9 | 1 | `InvalidParameterValue: auto_capture deprecated` |
| 5 | 10 | 2 | `TimeoutError` (infinite poll loop) |
| 6 | 7→10 | 1 | `BadRequest: pad_token_id missing` |
| 7 | 9 | 1 | `TypeError: NoneType not iterable` |
| 8 | 10 | 2 | `BadRequest: pad_token_id` again |
| 9 | 11 | 1 | `AnalysisException: PK column nullable` |
| 10 | 12 | 1 | `TypeError: unexpected kwarg 'name'` |
| 11 | 12 | 1 | `AttributeError: 'str' has no 'value'` |
| 12 | 12 | 1 | `AttributeError: 'dict' has no 'as_dict'` |

### Skill Fixes

| # | Cell | Iterations | Error |
| --- | --- | --- | --- |
| 1 | Cell 5 (Cleanup) | 1 | `ModelVersionsAPI.delete() got an unexpected keyword argumen |
| 2 | Cell 4 (Config) | 1 | `AssertionError: Missing model.safetensors` at lowercase `70 |
| 3 | Cell 11 (Log Model) | 1 | `OSError: source code not available` |
| 4 | Cell 11 (Log Model) | 1 | `unsupported operand type(s) for *: 'NoneType' and 'Tensor'` |
| 5 | Cell 12 (Dry-load) | 1 | `AssertionError: Expected 1 row, got 5` |
| 6 | Cell 13 (Deploy) | 1 | `NameError: name 'SKIP_DEPLOY' is not defined` |
| 7 | Cell 13 (Deploy) | 1 | Cell execution timed out after 900s |

## Delta Summary

* Skill wins: 4
  * model_registration/pip_reqs_from_source
  * endpoint_deployment/sdk_enums
  * endpoint_deployment/ai_gateway_config
  * smoke_tests/registration_smoke
* Baseline wins: 0
* Both fail: 0
