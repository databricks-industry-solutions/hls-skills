# funke-hl7v2

## Identity

- Repo: https://github.com/databricks-industry-solutions/funke-hl7v2
- Install doc: README sections "Getting Started" and "Using the funke library directly"; agent and contributor notes in `CLAUDE.md`
- Maintainers: Sean Fischer, Brian Nowak, Chris Mantz (authors in `pyproject.toml`)
- Reviewed: 2026-10-22 against commit 4312987

## Use it for

- Parsing HL7v2 messages (ADT, ORU, ORM, OML, MDM, SIU, VXU, DFT, MFN and others) from files in a Unity Catalog Volume into Delta, without converting to FHIR first
- A native nested Spark type for each message (segment, field, repetition, component, subcomponent) that can be queried from SQL or PySpark
- A streaming Lakeflow pipeline from a landing Volume to `raw_messages` and `parsed_messages`, deployed as an Asset Bundle
- An ADT bed-utilization demo on top: gold tables, metric views, an AI/BI dashboard and a control-room app with a synthetic ADT generator

## Do not use it for

- FHIR resources or bundles: funke parses HL7v2 only
- X12 EDI claims (837, 835, 834): not covered by funke; to build measures from already-parsed claims use `payer-provider-measure-catalog`
- Receiving messages over MLLP or a socket: funke reads files, so an interface engine or other process must land each message as a file in the Volume
- De-identifying the parsed tables: use `phi-deidentifier`
- Computing utilization, length of stay or other measures beyond the bundled ADT demo: use `payer-provider-measure-catalog`

## Deploy signals

- Tables `<catalog>.<schema>.raw_messages` and `<catalog>.<schema>.parsed_messages` (bundle default schema `hl7`)
- Volume `<catalog>.<schema>.landing`
- Pipelines `HL7 Ingestion` and `Bed Utilization (Gold)`
- App `adt-control-room`; gold tables `adt_events`, `current_census` and `bed_utilization`
- With the bundle's default `dev` target, names carry a prefix: schema `dev_<user>_<schema>` and pipelines `[dev <user>] HL7 Ingestion`

## Smallest path

No admin rights and no bundle needed. funke is not on PyPI; install it from GitHub in a notebook, then parse files from a Volume with its UDF. Tested on serverless notebooks (environment version 4) on 2026-10-22:

```python
%pip install --no-build-isolation git+https://github.com/databricks-industry-solutions/funke-hl7v2.git
%restart_python
```

```python
import pyspark.sql.functions as F
from funke.parsing.functions import parse_hl7v2_msg
from funke.parsing.hl7 import HL7v2Schema
from funke.utils import get_value

raw = (spark.read.format("binaryFile").load("/Volumes/<catalog>/<schema>/<volume>/<folder>")
       .withColumn("content", F.regexp_replace(F.decode("content", "UTF-8"), r"^\s+", "")))
parsed = raw.withColumn("hl7", parse_hl7v2_msg(HL7v2Schema())(F.col("content")))
hl7 = F.col("hl7")
parsed.select(
    get_value(hl7, "MSH", 0, 9, 0, 2).alias("trigger_event"),
    get_value(hl7, "PID", 0, 3, 0, 1).alias("patient_id"),
    get_value(hl7, "PID", 0, 5, 0, 1).alias("last_name"),
    get_value(hl7, "PV1", 0, 19, 0, 1).alias("visit_number"),
).write.saveAsTable("<catalog>.<schema>.<table>")
```

- Without pip: clone the repo as a Git folder and `sys.path.insert(0, "/Workspace/<path-to-git-folder>/src")` before the imports (tested on serverless notebooks, environment versions 1 and 4).
- SQL on the parsed column: `hl7.PID[0].fields[5][0][1][1]` is PID-5.1. The segment and field repetition indexes start at 0; field, component and subcomponent numbers start at 1. `get_value(hl7, segment, segment_rep, field, field_rep, component, subcomponent=1)` takes the same positions.
- Field addressing and examples beyond this belong to the README "Example" section; read it for current usage.

## Full install

Prerequisites: Unity Catalog with CREATE SCHEMA on the target catalog, serverless Lakeflow pipelines, a SQL warehouse ID, Databricks Apps (only for the demo app) and Databricks CLI with bundle support. The bundle creates only user-level resources (schema, Volume, pipelines, job, dashboard, app) and uses no admin-only feature; it was tested as a workspace admin, so confirm the user can create apps and schemas.

Commands, from a local clone, inside a Python virtual environment (the bundle builds the funke wheel with `python3 -m pip`):

```bash
databricks bundle deploy -t dev --var catalog=<catalog> --var warehouse_id=<warehouse-id> -p <profile>
# land files in /Volumes/<catalog>/<schema>/landing/ (dev target: dev_<user>_<schema>), then
databricks pipelines start-update <hl7-ingestion-pipeline-id> -p <profile>
```

Deploy takes a few minutes and starts nothing: both pipelines are created idle and the app stopped. In the `dev` target the pipelines are triggered (an update processes the landed files and stops; tested: 6 ADT files to `parsed_messages` in under a minute). The bundle YAML sets `continuous: true`, which applies with `-t prod` (`mode: production`, not tested here). The README alternative is to clone the repo into the workspace and click Deploy in the Asset Bundle editor.

## Pitfalls

- **Batch files parse to NULL**: funke expects one message per input whose first segment is `MSH`. Files wrapped in `FHS`/`BHS` (immunization registry and other batch feeds) fail. Split them first:
  `F.explode(F.split(F.regexp_replace("content", r"\r\n?|\n", "\r"), r"\r(?=MSH\|)"))`, keep rows that start with `MSH|` and drop `BTS`/`FTS` lines. Tested: one 3-message batch file became 3 parsed messages.
- **Failures are silent**: the UDF returns NULL for any message it cannot parse instead of raising. Check `hl7 IS NULL` after every load. A leading blank line also causes NULL; strip leading whitespace first (`regexp_replace(content, r"^\s+", "")`; Spark `ltrim` removes spaces only).
- **`warehouse_id` is required**: `bundle validate` and `deploy` fail with "no value assigned to required variable warehouse_id" until `--var warehouse_id=<id>` is passed.
- **Default catalog `main`**: pass `--var catalog=<catalog>` where the user can create schemas.
- **Deploy fails on Homebrew or system Python**: the wheel build runs `python3 -m pip install` and hits "externally-managed-environment" (PEP 668). Run the deploy from an activated virtual environment.
- **`pip install` fails at "Installing build dependencies"**: when the workspace package index cannot serve `setuptools` (seen with a Databricks PyPI proxy; private mirrors can do the same), install with `--no-build-isolation` or use the Git folder path.
- **Library must reach the Spark workers**: use `%pip` in a notebook or an environment `dependencies` entry (the bundle's pipelines attach the funke wheel this way). Installing into a local path such as `/tmp` with `pip --target` works on the driver only and the UDF fails with `No module named 'funke'`.
- **Dev target names**: the landing Volume is under `dev_<user>_<schema>`, not `<schema>`. The app name `adt-control-room` is not prefixed, so two users deploying into one workspace collide.
- **Continuous pipelines outside dev**: the YAML defines `HL7 Ingestion` and `Bed Utilization (Gold)` as continuous, so outside the `dev` target they run once started and bill until stopped (`databricks pipelines stop <id>`; the demo app can pause them). The `dev` target deploys them as triggered.
- **Patient ID**: use PID-3 (patient identifier list); the README example reads PID-2, a backward-compatibility field that is often empty.
