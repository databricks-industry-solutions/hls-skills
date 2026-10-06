# Pixels

## Identity

- Repo: https://github.com/databricks-industry-solutions/pixels
- Install doc: `docs/INSTALL.md`; agent and contributor notes in `CLAUDE.md`
- Maintainers: see the repo's contributors page
- Reviewed: 2026-10-05 against commit 347c349

## Use it for

- Cataloging DICOM files (`.dcm` and zip archives) from a Unity Catalog Volume into a Delta table (`object_catalog`) and querying the metadata with SQL
- Incremental ingestion with Auto Loader, optionally with managed file events
- De-identifying DICOM metadata with format-preserving encryption (`DicomMetaAnonymizerExtractor`)
- A browser DICOM viewer (OHIF) and a DICOMweb QIDO/WADO/STOW gateway as Databricks Apps
- CT auto-segmentation with MONAI Label and Vista3D on a GPU serving endpoint
- A Genie space and AI/BI dashboard over DICOM metadata

## Do not use it for

- De-identifying structured tables of patient records: use `phi-deidentifier`
- Training a new imaging model from scratch: Pixels serves Vista3D; for other models use `oss-models`
- Sending studies back to a PACS: not supported (open feature request, issue #198)

## Deploy signals

- Table `<catalog>.<schema>.object_catalog` (default schema `pixels`)
- Apps `pixels-dicomweb` (viewer) and `pixels-dicomweb-gateway`
- Serving endpoint `pixels-monai-uc`
- Job `pixels_install` in the bundle deployment

## Smallest path

Pixels has no PyPI package (issue #210). Its notebooks run from a clone of the repo: clone it as a Git folder, install `requirements.txt`, add `src/` to `sys.path`, then:

```python
import sys
sys.path.insert(0, "/Workspace/<path-to-pixels-git-folder>/src")
from dbx.pixels import Catalog
from dbx.pixels.dicom import DicomMetaExtractor

catalog = Catalog(spark, table="<catalog>.<schema>.object_catalog", volume="<catalog>.<schema>.<volume>")
catalog_df = catalog.catalog("/Volumes/<catalog>/<schema>/<volume>/dicom/")
meta_df = DicomMetaExtractor(catalog, permissive=True, remove_un_tags=True).transform(catalog_df)
catalog.save(meta_df)
```

Serverless caveat: in a test on 2026-10-05, installing Pixels' pinned `requirements.txt` failed on serverless (environment versions 3 and 5, via `%pip`, `pip install git+...` and job environment dependencies) with dependency conflicts. Tell the user to try it on their compute first. If it fails, the reliable route is the full install below, which runs its own install job; for metadata only in the meantime, `pydicom` can read the tags, but it does not give the viewer, DICOMweb or segmentation.

- Zip archives: `catalog.catalog(path, extractZip=True)`
- Incremental: `catalog.catalog(path, streaming=True, streamCheckpointBasePath=<path>)`

## Full install

Prerequisites (workspace admin or account team):

- Unity Catalog, serverless compute and a serverless SQL warehouse
- Databricks Apps plus Apps user token passthrough (org-level flag)
- Lakebase and Reverse ETL (gated previews)
- GPU Model Serving, Vector Search, AI/BI Genie and Foundation Model APIs (`databricks-bge-large-en`)
- Databricks CLI v0.230 or later (the new CLI; the legacy `pip install databricks-cli` cannot run bundles)

Commands, from a local clone:

```bash
make deploy CATALOG=<catalog> SCHEMA=pixels TARGET=prod PROFILE=<profile>
databricks bundle run pixels_install -t prod -p <profile> --var catalog=<catalog>
```

The install job has 15 serverless tasks and takes 30 to 45 minutes; the GPU endpoint alone can take 15 to 30 minutes to provision. `validate_install` checks every surface at the end.

## Pitfalls

- **`databricks bundle deploy` alone fails**: the dashboard template must be rendered first. Use `make deploy`, or `make build && make render-dashboard` before `bundle deploy`.
- **Default catalog `main` is not writable**: pass `--var catalog=<catalog>`.
- **Azure GPU type**: `GPU_MEDIUM` does not exist on Azure. Leave `serving_workload_type` empty (auto picks `GPU_LARGE`, then `GPU_SMALL`) or set it explicitly.
- **Warehouse lookup fails at validate**: the bundle looks for "Serverless Starter Warehouse"; pass `--var sql_warehouse=<id>` otherwise.
- **Apps fail with "user token passthrough feature is not enabled"**: the org-level flag is off; the account team enables it.
- **Library install on serverless**: pinned requirements can conflict with the serverless runtime (see Smallest path); do not promise the library path works until it has run once.
- **Stale artifacts after edits**: run `make clean && make build` before redeploying.
- **Large zips run out of memory**: very large whole-slide pathology zips can OOM ingest (issue #226), and serverless UDF memory limits can be hit (issue #149). Split archives or use larger compute.
- **Viewer spins forever**: a StudyInstanceUID that is not in the catalog (issue #137) or null StudyInstanceUIDs (issue #135).
