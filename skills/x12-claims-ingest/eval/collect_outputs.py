"""Read back what an arm produced for one task, as the objective's IngestOutput (JSON-safe dict).

Reads <schema>.<prefix>claims / claim_lines / file_checks by the column names the prompt required.
A missing table or column is not an error: it simply scores as missing. For tasks that require a
pipeline run, checks that a pipeline with the requested name exists and its latest update COMPLETED.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from ingest_scorers import output_from_records, to_jsonable  # noqa: E402


def _rows(spark, table: str) -> list[dict]:
    if not spark.catalog.tableExists(table):
        return []
    return [r.asDict() for r in spark.table(table).collect()]


def pipeline_completed(name: str) -> bool:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    for p in w.pipelines.list_pipelines(filter=f"name LIKE '{name}'"):
        info = w.pipelines.get(p.pipeline_id)
        updates = w.pipelines.list_updates(p.pipeline_id, max_results=1).updates or []
        if info.spec and info.spec.serverless and updates and str(updates[0].state).endswith("COMPLETED"):
            return True
    return False


def collect(spark, schema: str, prefix: str, requires_run: bool = False, pipeline_name: str | None = None,
            claim_extras: tuple = (), line_extras: tuple = (), quality: bool = False) -> dict:
    claims = _rows(spark, f"{schema}.{prefix}claims")
    lines = _rows(spark, f"{schema}.{prefix}claim_lines")
    checks = _rows(spark, f"{schema}.{prefix}file_checks")
    flags = _rows(spark, f"{schema}.{prefix}claim_quality") if quality else []
    ran = pipeline_completed(pipeline_name) if requires_run and pipeline_name else None
    if requires_run and ran is None:
        ran = False
    return to_jsonable(output_from_records(claims, lines, checks, ran_where_asked=ran, quality_rows=flags,
                                           claim_extras=claim_extras, line_extras=line_extras))
