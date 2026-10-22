# Pipeline recipes

All recipes run on serverless. Put `x12_837.py` in the pipeline or job source folder (Lakeflow
pipelines add the root folder to `sys.path`), or `sys.path.append()` a workspace folder that holds it.

## Lakeflow declarative pipeline (Python)

Bronze is an Auto Loader streaming table, one row per file. Silver tables are materialized views:
loop resolution uses window functions over a whole file, which a streaming table cannot do.

```python
import dlt
from pyspark.sql import functions as F
import x12_837

SOURCE = spark.conf.get("x12.source_path")          # e.g. /Volumes/<c>/<s>/<v>/837/

@dlt.table(name="x12_837_raw", comment="Raw 837 files, one row per file")
def x12_837_raw():
    return x12_837.stream_x12(spark, SOURCE).withColumn("ingested_at", F.current_timestamp())

def _parsed():
    raw = spark.read.table("x12_837_raw")
    segs = x12_837.segments(raw)
    checks = x12_837.transaction_checks(raw, segs)
    return checks, x12_837.parse_837(segs, checks)

@dlt.table(name="transaction_checks")
def transaction_checks():
    return _parsed()[0]

@dlt.table(name="claims")
@dlt.expect_or_drop("transaction_ok", "transaction_status = 'ok'")
@dlt.expect("header_matches_lines", "total_charge_amount = line_charge_total")
def claims():
    return _parsed()[1]["claims"]

@dlt.table(name="claims_quarantine")
def claims_quarantine():
    return _parsed()[1]["claims"].filter("transaction_status <> 'ok'")

@dlt.table(name="claim_lines")
def claim_lines():
    return _parsed()[1]["claim_lines"]

@dlt.table(name="claim_diagnoses")
def claim_diagnoses():
    return _parsed()[1]["claim_diagnoses"]
```

Pipeline settings: serverless on, target catalog/schema, configuration `x12.source_path`.
Expectations surface in the pipeline event log, so data-quality counts come for free.

## Scheduled job: Auto Loader + foreachBatch (append)

Use when daily volume makes full materialized-view recomputes expensive. Each micro-batch holds
whole files, so the parser runs per batch and only new files are processed.

```python
import x12_837

TARGET = "<catalog>.<schema>"

def load(batch_df, batch_id):
    segs = x12_837.segments(batch_df)
    checks = x12_837.transaction_checks(batch_df, segs)
    out = x12_837.parse_837(segs, checks)
    checks.write.mode("append").saveAsTable(f"{TARGET}.transaction_checks")
    out["claims"].filter("transaction_status = 'ok'").write.mode("append").saveAsTable(f"{TARGET}.claims")
    out["claims"].filter("transaction_status <> 'ok'").write.mode("append").saveAsTable(f"{TARGET}.claims_quarantine")
    out["claim_lines"].write.mode("append").saveAsTable(f"{TARGET}.claim_lines")
    out["claim_diagnoses"].write.mode("append").saveAsTable(f"{TARGET}.claim_diagnoses")

(x12_837.stream_x12(spark, "/Volumes/<c>/<s>/<v>/837/")
    .writeStream.foreachBatch(load)
    .option("checkpointLocation", "/Volumes/<c>/<s>/<v>/_checkpoints/x12_837")
    .trigger(availableNow=True)
    .start()
    .awaitTermination())
```

Lines and diagnoses from quarantined claims still land; filter them with a semi-join on
`claims.claim_id` downstream, or add the same filter in `load`.

## Re-sent files

`claim_id` is derived from the file path and the claim's position, so the same file loaded twice
produces the same ids: use `MERGE INTO ... ON claim_id` instead of append if senders re-send files.
Replacement and void claims (`claim_frequency_code` 7 / 8) reference the original via
`payer_claim_control_number`; resolve them downstream, not in the parser.
