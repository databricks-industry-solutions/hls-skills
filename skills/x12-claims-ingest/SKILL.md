---
name: x12-claims-ingest
description: >-
  X12 837P/837I EDI claims ingestion and data quality on Databricks. Parses raw 837 professional and
  institutional files (5010 and 4010A1) from a Unity Catalog Volume into Delta tables (claims, claim
  lines, diagnoses) with built-in Spark functions only, so it runs on serverless, in Lakeflow
  declarative pipelines (SDP) and with Auto Loader. Encodes the mapping rules: HL loop hierarchy,
  COB loops kept out of primary fields, replacement/void resolution (CLM05-3, REF*F8), performing-
  provider precedence, diagnosis-pointer resolution, line vs claim place of service. Runs sourced
  quality checks (NPI check digit, 5010 billing address and ZIP rules, code-set formats, date logic,
  totals, duplicates) and quarantines truncated or non-X12 files. Inputs: a Volume path of
  .x12/.edi/.txt files. Outputs: claims, claim_lines, claim_diagnoses, claim_quality,
  transaction_checks. For measure definitions and metric views on the landed tables use payer-
  provider-measure-catalog; for de-identification use phi-deidentifier.
category: Payer and provider
summary: Parse X12 837P/837I claim files into Delta claims, lines and quality-check tables on serverless or Lakeflow.
version: 0.1.0
author: Raven Mukherjee
license: Databricks License
---

# X12 837 Claims Ingest

## Overview

Turns raw X12 837 claim files (professional 005010X222A1 / 004010X098A1 and institutional
005010X223A2 / 004010X096A1) into analysis-ready Delta tables, applies the claim mapping rules payers
get wrong (claim versions, performing provider, diagnosis pointers) and runs sourced quality checks. The parser in `scripts/x12_837.py` uses only built-in Spark SQL
functions and window functions: no UDFs, no RDDs, no external packages. That keeps it portable to
serverless compute, Lakeflow declarative pipelines, and Databricks SQL-adjacent jobs. Output is one row
per claim, one row per service line, one row per diagnosis, and one validation row per transaction.

## When to Use

- A payer or clearinghouse lands 837 files in cloud storage or a UC Volume and needs them as tables.
- Building a claims bronze/silver layer from EDI instead of a vendor extract.
- Loading 837s on serverless or in an SDP pipeline where third-party JVM or Python parsers are not an option.
- Checking a batch of 837 files for truncation, SE segment-count mismatches, or files that are not X12.
- Getting claim, line and diagnosis tables that `payer-provider-measure-catalog` can map to metric views.
- Answering "how many claims, what billed amount, which providers" from a folder of raw EDI.
- Applying corrected and voided claims (frequency 7 / 8) so totals are not double counted.
- Finding claims that fail front-end edits (bad NPI check digit, PO Box billing address, 5-digit ZIP,
  invalid codes, pointer or total errors, duplicates) before they reach adjudication or reporting.

## Prerequisites

- **Compute**: serverless (notebook, job, or Lakeflow pipeline) or any cluster on DBR 14.3+.
  ANSI mode on or off both work.
- **Inputs**: a Volume (or external location) path holding 837 files, one interchange or more per file.
- **Permissions**: `READ VOLUME` on the source; `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE` on the target.
- **Code**: copy `scripts/x12_837.py` beside the notebook or pipeline source (or into a workspace
  folder on `sys.path`). It imports only `pyspark`.

## Quick Start

```python
import sys; sys.path.append("<folder containing x12_837.py>")
import x12_837

raw    = x12_837.read_x12(spark, "/Volumes/<catalog>/<schema>/<volume>/837/")
segs   = x12_837.segments(raw)
checks = x12_837.transaction_checks(raw, segs)
out    = x12_837.parse_837(segs, checks)

display(checks)                                  # anything not 'ok' needs a look first
for name, df in out.items():                     # claims, claim_lines, claim_diagnoses
    df.write.mode("overwrite").saveAsTable(f"<catalog>.<schema>.{name}")
```

No files yet? `python3 scripts/generate_837.py --out /Volumes/<c>/<s>/<v>/837` writes synthetic
837P/837I files (fake IDs) that exercise every trap listed under Troubleshooting.

## Workflow

### Step 1: Inspect the source

Confirm the files are 837s and see which variants are present before parsing. The ISA header is
fixed width, so the delimiters are at known positions.

```sql
SELECT _metadata.file_path,
       substring(value, 4, 1)   AS element_sep,
       substring(value, 105, 1) AS component_sep,
       substring(value, 106, 1) AS segment_term,
       regexp_extract(value, '00(5010X22[234]|4010X09[678])A[0-9]', 0) AS version
FROM read_files('/Volumes/<c>/<s>/<v>/837/', format => 'text', wholeText => true)
LIMIT 20;
```

`X222` / `X098` = professional, `X223` / `X096` = institutional (5010 / 4010A1), `X224` / `X097` =
dental (header fields parse; dental lines are out of scope). 4010 files carry ICD-9 (BK/BF) diagnoses;
`x12_version` keeps them apart. Files that are 835 or 834 show up as `not_837` in Step 3. Some senders
trim the ISA padding: delimiters are read from the ISA itself, and `isa_fixed_width` flags it.

### Step 2: Split into segments with loop context

`segments(raw)` reads each file's own delimiters from its ISA, splits segments and elements, and
attaches context columns: `st_pos`, `hl_pos`, `bp_hl_pos`, `sub_hl_pos`, `pat_hl_pos`, `clm_pos`,
`lx_pos`, plus `in_claim`, `in_line`, `in_cob`. These come from running "last position" windows per
file, which is how the HL hierarchy is resolved without a stateful parser.

```python
segs = x12_837.segments(raw)
segs.groupBy("seg_id").count().orderBy("count", ascending=False).show()
```

Persist `segs` as a bronze table when the volume is large or when you will rerun silver logic.

### Step 3: Validate transactions

`transaction_checks(raw, segs)` returns one row per ST/SE transaction and one per non-X12 file, with
`transaction_status` in `ok`, `missing_SE`, `segment_count_mismatch`, `control_number_mismatch`,
`not_837`, `not_x12`. Report counts by status to the user before loading.

```python
checks.groupBy("transaction_status").count().show()
```

### Step 4: Parse claims, lines, diagnoses

`parse_837(segs, checks)` returns a dict of three DataFrames. Every claim row carries
`transaction_status`; keep `ok` claims in the main table and route the rest to a quarantine table.
Column definitions are in `references/output_tables.md`.

```python
claims = out["claims"]
good, bad = claims.filter("transaction_status = 'ok'"), claims.filter("transaction_status <> 'ok'")
```

Lines carry the claim context that needs mapping rules: `effective_rendering_npi` (line 2420A, else
claim 2310B rendering, else 837I attending, else billing), `effective_place_of_service` (line SV105
over CLM05-1) and `line_diagnosis_codes` (SV107 pointers resolved to the claim's ordered ICD codes).

### Step 5: Resolve corrected and voided claims

Frequency 7 replaces and 8 voids an earlier claim (both with REF*F8). Loading every version double
counts. `resolve_claim_versions(claims)` keeps the latest version per claim and drops voids; pass
`link_keys` if you link versions by an ICN map instead of billing NPI + member + patient control number.

```python
current = x12_837.resolve_claim_versions(out["claims"])   # one row per claim, version_count shows history
```

### Step 6: Run quality checks

`quality_checks(claims, claim_lines, claim_diagnoses, checks)` returns one row per (claim, line, rule)
failure with `severity` error or warning. Rules and sources: `references/quality_rules.md`. Quarantine
errors or route them to a work queue; report counts by rule to the user.

```python
q = x12_837.quality_checks(current, out["claim_lines"], out["claim_diagnoses"], checks)
q.groupBy("rule_id", "severity").count().orderBy("rule_id").show()
```

### Step 7: Reconcile

Check internal consistency before handing the tables on. Billed amount on the header must equal the
sum of line charges; every claim needs a member, payer and billing NPI.

```sql
SELECT count(*) AS claims,
       sum(total_charge_amount) AS billed,
       count_if(total_charge_amount <> line_charge_total) AS header_line_mismatch,
       count_if(member_id IS NULL OR payer_id IS NULL OR billing_provider_npi IS NULL) AS missing_keys
FROM <catalog>.<schema>.claims;
```

### Step 8: Write and hand off

Write `claims` (current view), `claim_lines`, `claim_diagnoses`, `claim_quality` and
`transaction_checks` to the target schema, keyed by `claim_id`. For incremental loads use a recipe below. To build measures, point
`payer-provider-measure-catalog` at these tables (field mapping in `references/output_tables.md`).

## Key Parameters

| Parameter | Default | Options | Effect |
|-----------|---------|---------|--------|
| `path` (read_x12 / stream_x12) | (required) | Volume or cloud path | Folder or glob of 837 files |
| `checks` (parse_837) | `None` | transaction_checks output | Stamps `transaction_status` on each claim |
| `schema_location` (stream_x12) | `None` | path | Auto Loader checkpoint for schema tracking (jobs) |
| quarantine filter | `transaction_status = 'ok'` | any status list | Which claims reach the main table |
| `link_keys` (resolve_claim_versions) | billing NPI, member, PCN | column names | How versions of one claim are linked |
| `as_of` (quality_checks) | today | `YYYY-MM-DD` | Reference date for future-date checks |

## Common Recipes

### Recipe: Lakeflow declarative pipeline (SDP)

When to use: continuous or scheduled ingest with lineage, on serverless pipelines. Bronze is a
streaming table (Auto Loader); silver tables are materialized views because the loop windows need a
complete file. Full code in `references/pipeline_recipes.md`.

```python
import dlt, x12_837

@dlt.table(name="x12_837_raw")
def raw():
    return x12_837.stream_x12(spark, spark.conf.get("source_path"))

@dlt.table(name="claims")
def claims():
    raw = spark.read.table("x12_837_raw"); segs = x12_837.segments(raw)
    return x12_837.parse_837(segs, x12_837.transaction_checks(raw, segs))["claims"]
```

### Recipe: Incremental job with Auto Loader + foreachBatch

When to use: high daily volume where recomputing materialized views is too costly. Each micro-batch
is a static DataFrame, so the windowed parser runs per batch and appends.

```python
def load(batch_df, _):
    segs = x12_837.segments(batch_df); chk = x12_837.transaction_checks(batch_df, segs)
    for name, df in x12_837.parse_837(segs, chk).items():
        df.write.mode("append").saveAsTable(f"<c>.<s>.{name}")
    chk.write.mode("append").saveAsTable("<c>.<s>.transaction_checks")

(x12_837.stream_x12(spark, "/Volumes/<c>/<s>/<v>/837/").writeStream
   .foreachBatch(load).option("checkpointLocation", "/Volumes/<c>/<s>/<v>/_chk/837")
   .trigger(availableNow=True).start())
```

## Expected Outputs

- `claims`: one row per CLM. Claim type, patient control number, billed amount, dates (statement or
  line-derived), member and patient demographics, payer, billing/rendering/attending NPIs, TIN,
  principal + ordered diagnosis codes, DRG, type of bill or place of service, prior auth, lineage
  (`source_file`, ISA/ST control numbers), `transaction_status`.
- `claim_lines`: one row per LX. Procedure code + modifiers, revenue code, charge, units, service
  dates, diagnosis pointers and `line_diagnosis_codes`, `effective_rendering_npi`,
  `effective_place_of_service`, line control number, NDC.
- `claim_quality`: one row per rule failure (claim, line, rule_id, severity, field, value, message).
- `claim_diagnoses`: one row per HI diagnosis code with sequence and `is_principal`.
- `transaction_checks`: one row per transaction or non-X12 file with segment counts and status.

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Zero claims, file listed as `not_x12` | Leading junk, wrong file type, or a short/corrupt ISA | Open the file; the ISA must be 106 chars with matching separators at positions 4 and 104 |
| Claims marked `missing_SE` | Truncated transfer | Re-request the file; do not load those claims as final |
| `segment_count_mismatch` | SE01 disagrees with the segments received | Usually a partial or hand-edited file; quarantine and re-request |
| Patient name/DOB repeats across claims | Hand-written parser carrying 2000C values forward | Use the HL-scoped joins in `parse_837`; a patient loop only applies under its own subscriber HL |
| Payer ID or claim number from the wrong payer | 2320/2330 COB loops (second SBR, NM1*PR, REF*F8) read as primary | Exclude `in_cob` segments from claim-level fields, as `parse_837` does |
| Header billed amount differs from line total | Parsed SV1 charge from the wrong element, or lines dropped | SV1-02 is charge (837P), SV2-03 is charge (837I); check `line_count` |
| `[CAST_INVALID_INPUT]` / `ARRAY_INDEX_OUT_OF_BOUNDS` errors in custom SQL | ANSI mode on serverless | Use `try_cast` and `get(array, i)` as the module does |
| UDF / RDD / `sparkContext` errors on serverless | Code outside this module | Keep transforms in DataFrame or SQL functions |
| Billed totals too high after a correction batch | Replacements (CLM05-3 = 7) loaded next to the originals | Run `resolve_claim_versions`; voids (8) drop the claim |
| Payer rejects NPIs that "look valid" | 10 digits is not enough: the check digit must pass (Luhn with 80840) | `NPI_INVALID` in `quality_checks`; see `npi_is_valid` |
| 4010 claims show `claim_type = unknown` or no diagnoses | Version not recognized, or ICD-9 qualifiers ignored | Use this module: X098/X096 and BK/BF are handled; filter on `x12_version` |

## Guardrails

- **837 files are PHI.** Write only to schemas with appropriate access controls; never print member
  names, DOBs or IDs in summaries. Use `phi-deidentifier` before sharing outputs.
- **Validate before load.** Always run `transaction_checks` and report non-`ok` counts; never mix
  quarantined claims into the main table silently.
- **Do not invent fields.** If a requested field is not in `references/output_tables.md`, find the
  segment in `references/837_loops.md` and extend the module; do not guess positions.
- **Confirm before outward writes.** Creating tables, pipelines or jobs is an outward action; show the
  target schema and table names and get approval.
- **Serverless-safe code only.** No UDFs, RDDs, `sparkContext`, `cache()`, or non-PySpark imports in
  the parse path.
- **Do not invent quality rules.** Use the sourced rules in `references/quality_rules.md`; payer-specific
  edits (duplicate signature, gender extensions) are configurable and must be confirmed with the user.
- **Retry at most 3 times** on the same error; then stop and report what was tried.

## Bundled Resources

- `scripts/x12_837.py`: the parser (`read_x12`, `stream_x12`, `segments`, `transaction_checks`,
  `parse_837`, `resolve_claim_versions`, `quality_checks`, `npi_is_valid`).
- `scripts/generate_837.py`: synthetic 837P/837I generator with an answer key (stdlib only).
- `references/837_loops.md`: loop and segment cheat sheet, element positions used, parsing traps.
- `references/output_tables.md`: column dictionary and mapping to the measure-catalog x12 adapter.
- `references/pipeline_recipes.md`: full Lakeflow pipeline and Auto Loader job code.
- `references/quality_rules.md`: quality and mapping rules with public sources.

## References

- [X12 transaction sets](https://x12.org/products/transaction-sets): 837 is maintained by X12; the
  implementation guides (TR3) are licensed and are not reproduced here.
- [CMS Place of Service code set](https://www.cms.gov/medicare/coding-billing/place-of-service-codes/code-sets)
- [CMS NPI check digit](https://www.cms.gov/Regulations-and-Guidance/Administrative-Simplification/NationalProvIdentStand/Downloads/NPIcheckdigit.pdf)
  and [How to avoid common 5010 claims rejections](https://www.cms.gov/files/document/howtoavoidcommonversion5010claimsrejectionspdf)
- [NUCC provider taxonomy](https://taxonomy.nucc.org/)
- [Auto Loader](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/)
- [Lakeflow declarative pipelines](https://docs.databricks.com/aws/en/dlt/)
- [Serverless compute limitations](https://docs.databricks.com/aws/en/compute/serverless/limitations)
- [`try_cast`](https://docs.databricks.com/aws/en/sql/language-manual/functions/try_cast) and
  [ANSI compliance](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-ansi-compliance)
