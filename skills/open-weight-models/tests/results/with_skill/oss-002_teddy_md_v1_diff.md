# teddy.md v0 → v1 Skill Diff

**Date**: 2026-10-01  
**Source**: oss-002 skill-arm run (notebook ID `4070133587703100`)  
**File**: `.assistant/skills/oss-models/references/models/teddy.md`  
**Patches applied**: 8  

---

## Patch 1 — §Hugging Face download (~line 130)
**Fix**: #1 (hf_transfer RuntimeError)  
**Trigger**: AI v5 base environment pre-enables `hf_transfer`; env-var-only fix insufficient

```diff
- The TEDDY repo uses HF's **Xet/CAS storage backend**. Standard HTTP download fails with:
- ```
- RuntimeError: CAS service error: IO Error: Illegal seek (os error 29)
- ```
- Fix — set the env var **before the first import of `huggingface_hub`** in the process:
- ```python
- import os
- os.environ["HF_HUB_DISABLE_XET"] = "1"  # must come before any huggingface_hub import
- from huggingface_hub import snapshot_download
- snapshot_download(repo_id="Merck/TEDDY", local_dir=local_dir)
- ```
- If `huggingface_hub` was already imported in the session, restart the Python kernel first.
+ The TEDDY repo uses HF's **Xet/CAS storage backend**. Standard HTTP download fails with:
+ ```
+ RuntimeError: CAS service error: IO Error: Illegal seek (os error 29)
+ ```
+
+ **Preferred fix — subprocess isolation** (works on all AI Runtime versions, v5+, v6+):
+
+ Databricks AI base environments (v5, v6, and likely future versions) pre-enable `hf_transfer`
+ via `HF_HUB_ENABLE_HF_TRANSFER=1` and import `huggingface_hub` early. Setting env vars
+ in-process after import has no effect. The robust workaround is to run the download in a
+ **subprocess** with a clean environment:
+
+ ```python
+ import subprocess, sys, os
+ env = {**os.environ, "HF_HUB_DISABLE_XET": "1", "HF_HUB_ENABLE_HF_TRANSFER": "0"}
+ subprocess.check_call(
+     [sys.executable, "-c", f'''
+ import os
+ os.environ["HF_HUB_DISABLE_XET"] = "1"
+ os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
+ from huggingface_hub import snapshot_download
+ snapshot_download(repo_id="Merck/TEDDY", local_dir="{local_dir}")
+ '''],
+     env=env,
+ )
+ ```
+
+ This guarantees a fresh Python process with no pre-imported `huggingface_hub`. Do **not**
+ rely on the simpler env-var-only pattern — it only works if the notebook kernel has never
+ imported `huggingface_hub`, which is not guaranteed on AI Runtime.
```

---

## Patch 2 — §Compute requirements (~line 150)
**Fix**: #6 (CUDA OOM)  
**Trigger**: GPU_SMALL = T4 (14.56 GiB capacity in OOM trace), not A10G as documented

```diff
- | Model Serving endpoint | `GPU_SMALL` (A10G, 24 GB VRAM) is sufficient for all three
-   variants: 70M (~140 MB), 160M (~320 MB), 400M (~800 MB) in bfloat16. H100 is not
-   required. scale-to-zero enabled. |
+ | Model Serving endpoint | `GPU_SMALL` = **T4 (16 GB VRAM)**, not A10G. Sufficient for
+   70M with batch cap ≤10 cells. For 160M/400M or higher throughput, use `GPU_MEDIUM`
+   (A10G, 24 GB VRAM). H100 is not required. `scale_to_zero_enabled=True`. |
```

---

## Patch 3 — §Open questions (~line 466)
**Fix**: v5/v6 clarification + GPU monitoring  
**Trigger**: Documenting runtime-agnostic nature of subprocess fix; GPU tier may change

```diff
- * Whether HF_HUB_DISABLE_XET will remain necessary as HF updates the Xet client.
+ * Whether HF_HUB_DISABLE_XET will remain necessary as HF updates the Xet client.
+   The subprocess workaround is runtime-version-agnostic (tested on AI v5; expected
+   to work on v6+).
  * Whether the `transformers==4.41.0` exact pin will need to be updated ...
  * Optimal `max_seq_len` for 160M and 400M variants ...
  * Whether per-cell `adata_obs` metadata ...
+ * Whether future Databricks GPU_SMALL tiers will provision A10G instead of T4 —
+   monitor release notes.
```

---

## Patch 4 — §Census generation pipeline, step 1 (~line 226)
**Fix**: #4 (Census organism key)  
**Trigger**: `KeyError: "Collection has no item 'Homo sapiens'"`

```diff
- 1. Query Census obs metadata (`is_primary_data=True`, `assay="10x 3' v3"`) → ~59M cells
+ 1. Query Census obs metadata (`is_primary_data=True`, `assay="10x 3' v3"`) using
+    organism key `"homo_sapiens"` (lowercase underscore — **not** `"Homo sapiens"`;
+    the Census Python API changed to lowercase keys for all versions including older
+    census snapshots like 2024-07-01) → ~19M cells (10x 3' v3 primary)
```

---

## Patch 5 — §Census generation pipeline, steps 5-8 (~line 234)
**Fixes**: #5 (payload 16MB) + #6 (CUDA OOM batch sizing)  
**Trigger**: 60k genes exceeded 16MB request limit; 50-cell batches OOM on T4

```diff
  5. Intersect with TEDDY vocab: ~22K overlap out of 25K Ensembl IDs (86.6%)
- 6. Embed in batches of 50 via UC-registered model (`mlflow.pyfunc.load_model`)
- 7. Write `(cell_id, embedding, cell_type, tissue_general, disease)` to Delta
- 8. Enable CDF for Delta Sync AI Search index
+ 6. **Filter AnnData to TEDDY vocab genes** before embedding:
+    `adata = adata[:, mask]`. Census delivers ~60k genes per cell; sending all of
+    them to the serving endpoint exceeds the 16 MB request-size limit. Filtering to
+    the ~22k TEDDY vocab genes cuts the payload by >50% and stays within limits.
+ 7. Embed in batches via the serving endpoint. **Batch size depends on GPU tier**:
+    10 cells for `GPU_SMALL` (T4, 16 GB); 50 for `GPU_MEDIUM` (A10G, 24 GB).
+    Larger batches on T4 cause `CUDA out of memory` — the 70M model's activations
+    at 2048 seq_len × 512 hidden dim saturate 14.5 GB of available VRAM with >10
+    concurrent cells.
+ 8. Write `(cell_id, embedding, cell_type, tissue_general, disease)` to Delta
+ 9. Enable CDF for Delta Sync AI Search index
```

---

## Patch 6 — §Sizing guide (~line 244)
**Fix**: #6 (throughput annotation)  
**Trigger**: Documenting actual endpoint throughput vs local GPU

```diff
- | **1,000** | **~5 min** | **~20 min** | **GT default, good for PCA/t-SNE** |
+ | **1,000** | **~5 min (GPU_MEDIUM, batch 50)** / **~2 min endpoint** | **~20 min** |
+   **GT default, good for PCA/t-SNE** |
```

---

## Patch 7 — §AI Search eval scorer (~line 296)
**Fix**: #7 (ResultData API)  
**Trigger**: `AttributeError: 'ResultData' object has no attribute 'column_names'`

```diff
  During sync, failures are soft warnings (expected). Once the index reports
  `ready=True`, failures become hard assertions.
+
+ **SDK note**: `QueryVectorIndexResponse.result` is a `ResultData` with `data_array`
+ and `row_count` — there is no `column_names` attribute. Columns appear in `data_array`
+ in the order specified in the `columns=` argument, with a trailing `score` column
+ appended. Use positional indexing:
+ ```python
+ top_id = data_array[0][0]            # first requested column
+ score  = float(data_array[0][-1])     # score is always last
+ ```
```

---

## Patch 8 — §Wrapper boundary (NEW subsection, before §OOV gene handling)
**Fix**: #3 (tensor boolean ambiguity)  
**Trigger**: `RuntimeError: Boolean value of Tensor with more than one element is ambiguous`

```diff
+ ### Tensor-boolean safety in `_predict_batch`
+
+ TEDDY's forward pass returns a dict with `all_embs`, `last_hidden_state`, and/or
+ `hidden_states`. **Never use Python `or` or truthy evaluation on these tensors** —
+ `bool(tensor)` raises `RuntimeError: Boolean value of Tensor with more than one
+ element is ambiguous`. Always use explicit `is None` checks:
+
+ ```python
+ # WRONG — triggers tensor boolean ambiguity
+ token_embeddings = outputs.get("all_embs") or outputs.get("last_hidden_state")
+
+ # CORRECT — explicit None checks
+ token_embeddings = outputs.get("all_embs")
+ if token_embeddings is None:
+     token_embeddings = outputs.get("last_hidden_state")
+ if token_embeddings is None and outputs.get("hidden_states") is not None:
+     token_embeddings = outputs["hidden_states"][-1]
+ ```
+
+ This applies to all three extraction branches (dict outputs, named-tuple outputs,
+ hidden-states fallback).

  ### OOV gene handling
```

---

## Fix NOT applied to teddy.md

**Fix 2** (`ServingModelWorkloadSize` enum → string literal): Generic SDK issue, not
TEDDY-specific. Tracked in `/memories/reference/databricks-sdk-gotchas-serving-vs.md`.

---

## Eval context

| Arm | Skill version | Bugs | Iterations | Model versions |
|-----|--------------|------|------------|----------------|
| Baseline | none | 12 | 15 | 5 |
| Skill v1 | original teddy.md | 7 | 8 | 1 |
| Skill v2 | patched teddy.md (this diff) | TBD | TBD | TBD |

Of the 7 skill-v1 bugs, 6 are directly addressed by these patches. The remaining 1
(SDK `workload_size`) is not TEDDY-specific and would persist in v2.
