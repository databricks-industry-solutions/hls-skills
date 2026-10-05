# Eval Runtime Environments

This documents the compute environments used for the HLS skills eval runs.
Each test notebook is driven by a fresh Genie Code session — it doesn't share
state with previous runs or with the eval harness.

## Compute types used

| Phase | Compute | Environment | Notes |
|-------|---------|-------------|-------|
| Model download + register + deploy | Serverless GPU (GPU_1xA10) | AI Runtime v5 | TEDDY needs GPU for `log_model` dry-load and serving |
| Census + Vector Search | Same session (serverless GPU) | AI Runtime v5 | Census API is CPU but runs in same notebook |
| Eval harness (03_eval) | Serverless CPU | Standard Python env | No GPU needed — scores exported .txt files |

## Known serverless GPU environment (AI Runtime v5, as of Oct 2026)

```
Python:          3.12.3
Platform:        Linux (Amazon Linux 2023, glibc 2.39)
DBR version:     client.5.12
Compute type:    serverless
Environment:     AI Runtime v5

Key packages:
  databricks-sdk         0.67.0
  mlflow                 3.16.1
  transformers           4.41.0  (pinned by %pip)
  torch                  2.9.0+cu129
  numpy                  2.2.6
  pandas                 2.3.3
  scipy                  1.15.3
  cellxgene-census       1.18.0  (installed by %pip)
  tiledbsoma             2.3.0   (pulled by census)
  pyspark                4.1.0+databricks.connect.18.1.9

GPU:
  NVIDIA A10G, 22.1 GB VRAM
  CUDA 12.9
```

## Known serverless CPU environment (eval harness)

```
Python:          3.12.3
Platform:        Linux (Amazon Linux 2023, glibc 2.39)
DBR version:     client.6.2
Compute type:    serverless
Environment:     unknown (no AI Runtime on CPU serverless)

Key packages:
  databricks-sdk         0.122.0
  mlflow                 not installed
  numpy                  2.3.4
  pandas                 2.3.3
  pyspark                4.3.0.dev0+databricks.connect.19.1
```

## Detection logic

Serverless vs classic:
- `DATABRICKS_RUNTIME_VERSION` starts with `client.` → serverless
- `pyspark` version contains `databricks.connect` → serverless
- `IS_SERVERLESS=true` env var (not always set on serverless GPU)

AI Runtime version:
- `DATABRICKS_AI_ENV=true` + `DATABRICKS_ENV_VERSION=N` → AI Runtime vN
- `AIR_RUNTIME_VERSION` → AI Runtime (fallback)

## Classic GPU (not currently used)

If a task needs classic compute (e.g., custom init scripts, specific DBR),
attach an A10G single-node cluster with DBR ML 15.x+. The runtime cell
will show `Compute type: classic` and `Environment: unknown`.

## Prompt addition for runtime capture

All task prompts (both baseline and skill arms) should include this
paragraph before the export instruction:

> **Runtime capture (required)**: Before the export step, add a code cell
> titled "Runtime and Environment Info" that prints: Python version,
> platform, DBR version (`DATABRICKS_RUNTIME_VERSION`), compute type
> (serverless vs classic), environment (AI Runtime version if applicable),
> key package versions (databricks-sdk, mlflow, transformers, torch, numpy,
> pandas, pyspark), and GPU info (device name, VRAM) if available.
> This is eval metadata for reproducibility — do not skip it.

This ensures the runtime is captured by the same Genie Code session that
produced the notebook results, on whatever compute was attached at the time.
