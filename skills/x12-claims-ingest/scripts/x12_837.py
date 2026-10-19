"""Parse X12 837P / 837I claim files into Delta-ready DataFrames with built-in Spark functions only.

Serverless and Lakeflow (SDP) compatible: no UDFs, no RDDs, no SparkContext, no external packages,
and ANSI-safe (every index and cast uses get / try_cast, so bad input becomes NULL, not an error).

Flow:
    raw   = read_x12(spark, "/Volumes/<c>/<s>/<v>/837/")      # file_path, value
    segs  = segments(raw)                                       # one row per segment + loop context
    out   = parse_837(segs)                                     # claims, claim_lines, claim_diagnoses
    chk   = transaction_checks(raw, segs)                       # SE count / control number / not-X12

Loop context is resolved with running "last position" windows per file, so a segment knows which
transaction, HL (billing provider / subscriber / patient), claim (CLM) and line (LX) it belongs to.
"""

from __future__ import annotations

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

ENVELOPE_SEGMENTS = ["ISA", "IEA", "GS", "GE"]
PRINCIPAL_DX_QUALIFIERS = ["ABK", "BK"]
DX_QUALIFIERS = ["ABK", "BK", "ABF", "BF", "ABJ", "BJ", "APR", "PR", "ABN", "BN"]


# ── element helpers ──────────────────────────────────────────────────────────

def _q(col_name: str) -> str:
    """SQL for a regex that matches the 1-char separator held in `col_name` literally."""
    return f"concat('\\\\Q', {col_name}, '\\\\E')"


def _e(n: int) -> str:
    """SQL for X12 element n of the current segment (1-based, as in CLM01), NULL when absent or empty."""
    return f"nullif(get(elements, {n}), '')"


def _el(n: int) -> Column:
    return F.expr(_e(n))


def _comp(n: int, k: int) -> Column:
    """Component k (0-based) of composite element n, e.g. SV101-2 is _comp(1, 1)."""
    return F.expr(f"nullif(get(split(get(elements, {n}), {_q('component_sep')}), {k}), '')")


def _is(seg_id: str, qualifier: str | None = None, qual_el: int = 1) -> Column:
    cond = F.col("seg_id") == seg_id
    if qualifier is not None:
        cond = cond & (_el(qual_el) == qualifier)
    return cond


def _pick(cond: Column, value: Column) -> Column:
    """Aggregate: the value from the (single) segment matching cond."""
    return F.first(F.when(cond, value), ignorenulls=True)


def _try_cast(sql: str, type_: str) -> Column:
    return F.expr(f"try_cast({sql} AS {type_})")


def _date(sql: str) -> Column:
    """CCYYMMDD (or the first half of CCYYMMDD-CCYYMMDD) -> DATE, NULL when malformed."""
    return F.expr(f"to_date(try_to_timestamp(substring({sql}, 1, 8), 'yyyyMMdd'))")


def _claim_id() -> Column:
    return F.sha2(F.concat_ws("|", F.col("file_path"), F.col("clm_pos").cast("string")), 256)


# ── read ─────────────────────────────────────────────────────────────────────

def read_x12(spark, path: str) -> DataFrame:
    """Batch read: one row per file (wholetext), with the source path for lineage."""
    return (
        spark.read.format("text").option("wholetext", True).load(path)
        .select(F.col("_metadata.file_path").alias("file_path"), "value")
    )


def stream_x12(spark, path: str, schema_location: str | None = None) -> DataFrame:
    """Auto Loader read for jobs and Lakeflow pipelines: one row per newly arrived file."""
    reader = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "text")
        .option("wholetext", True)
    )
    if schema_location:
        reader = reader.option("cloudFiles.schemaLocation", schema_location)
    return reader.load(path).select(F.col("_metadata.file_path").alias("file_path"), "value")


# ── segments + loop context ──────────────────────────────────────────────────

def _with_x12_flags(raw: DataFrame) -> DataFrame:
    """Locate the ISA header and read the delimiters it declares (fixed-width ISA = 106 chars)."""
    return (
        # batch reads report dbfs:/Volumes/..., Auto Loader /Volumes/...; normalize so claim_id is stable
        raw.withColumn("file_path", F.regexp_replace("file_path", "^dbfs:", ""))
        .withColumn("_x12", F.expr("substring(value, greatest(instr(value, 'ISA'), 1))"))
        .withColumn(
            "is_x12",
            (F.instr("value", "ISA") > 0) & (F.length("_x12") >= 106)
            & (F.substring("_x12", 104, 1) == F.substring("_x12", 4, 1)),  # ISA15/16 boundary check
        )
    )


def segments(raw: DataFrame) -> DataFrame:
    """Explode files into segments and attach loop context columns. Non-X12 files are dropped here
    (transaction_checks reports them)."""
    segs = (
        _with_x12_flags(raw).filter("is_x12")
        .withColumn("element_sep", F.substring("_x12", 4, 1))
        .withColumn("component_sep", F.substring("_x12", 105, 1))
        .withColumn("segment_term", F.substring("_x12", 106, 1))
        .select(
            "file_path", "element_sep", "component_sep",
            F.posexplode(F.expr(f"split(_x12, {_q('segment_term')})")).alias("seg_pos", "seg_raw"),
        )
        .withColumn("seg", F.regexp_replace("seg_raw", r"^\s+|\s+$", ""))
        .filter(F.col("seg") != "")
        .withColumn("elements", F.expr(f"split(seg, {_q('element_sep')})"))
        .withColumn("seg_id", F.col("elements")[0])
        .drop("seg_raw", "element_sep")
    )

    w = (Window.partitionBy("file_path").orderBy("seg_pos")
         .rowsBetween(Window.unboundedPreceding, Window.currentRow))

    def last_pos(cond: Column) -> Column:
        return F.coalesce(F.last(F.when(cond, F.col("seg_pos")), ignorenulls=True).over(w), F.lit(-1))

    def carry(cond: Column, value: Column) -> Column:
        return F.last(F.when(cond, value), ignorenulls=True).over(w)

    ctx = segs.select(
        "*",
        last_pos(_is("ST")).alias("st_pos"),
        last_pos(_is("HL")).alias("hl_pos"),
        last_pos(_is("HL", "20", 3)).alias("bp_hl_pos"),
        last_pos(_is("HL", "22", 3)).alias("sub_hl_pos"),
        last_pos(_is("HL", "23", 3)).alias("pat_hl_pos"),
        last_pos(_is("CLM")).alias("clm_pos"),
        last_pos(_is("LX")).alias("lx_pos"),
        last_pos(_is("SBR")).alias("sbr_pos"),
        carry(_is("NM1"), _el(1)).alias("nm1_qualifier"),
        carry(_is("ISA"), F.trim(_el(13))).alias("isa_control_number"),
        carry(_is("GS"), _el(8)).alias("implementation_version"),
        carry(_is("ST"), _el(1)).alias("transaction_set"),
        carry(_is("ST"), _el(2)).alias("st_control_number"),
    )

    in_claim = (F.col("clm_pos") > F.col("hl_pos")) & (F.col("clm_pos") > F.col("st_pos"))
    in_line = in_claim & (F.col("lx_pos") > F.col("clm_pos"))
    # 2320/2330 other-subscriber loops start with SBR after CLM and before the first LX
    in_cob = in_claim & ~in_line & (F.col("sbr_pos") > F.col("clm_pos"))
    return (
        ctx.withColumn("in_claim", in_claim)
        .withColumn("in_line", in_line)
        .withColumn("in_cob", in_cob)
        .withColumn("pat_hl_pos", F.when(F.col("pat_hl_pos") > F.col("sub_hl_pos"), F.col("pat_hl_pos")))
    )


# ── parse ────────────────────────────────────────────────────────────────────

def _billing_providers(ctx: DataFrame) -> DataFrame:
    bp = ctx.filter((F.col("hl_pos") == F.col("bp_hl_pos")) & ~F.col("in_claim"))
    in_85 = F.col("nm1_qualifier") == "85"
    return bp.groupBy("file_path", "bp_hl_pos").agg(
        _pick(_is("NM1", "85"), _el(9)).alias("billing_provider_npi"),
        _pick(_is("NM1", "85"), _el(3)).alias("billing_provider_name"),
        _pick(_is("REF", "EI") & in_85, _el(2)).alias("billing_provider_tin"),
        _pick(_is("PRV", "BI"), _el(3)).alias("billing_provider_taxonomy"),
        _pick(_is("N4") & in_85, _el(2)).alias("billing_provider_state"),
        _pick(_is("N4") & in_85, _el(3)).alias("billing_provider_zip"),
    )


def _subscribers(ctx: DataFrame) -> DataFrame:
    sub = ctx.filter((F.col("hl_pos") == F.col("sub_hl_pos")) & ~F.col("in_claim"))
    in_il = F.col("nm1_qualifier") == "IL"
    return sub.groupBy("file_path", "sub_hl_pos").agg(
        _pick(_is("SBR"), _el(1)).alias("payer_responsibility_code"),
        _pick(_is("SBR"), _el(2)).alias("subscriber_relationship_code"),
        _pick(_is("SBR"), _el(3)).alias("group_number"),
        _pick(_is("SBR"), _el(9)).alias("claim_filing_indicator"),
        _pick(_is("NM1", "IL"), _el(9)).alias("member_id"),
        _pick(_is("NM1", "IL"), _el(3)).alias("subscriber_last_name"),
        _pick(_is("NM1", "IL"), _el(4)).alias("subscriber_first_name"),
        _pick(_is("DMG") & in_il, _date(_e(2))).alias("subscriber_birth_date"),
        _pick(_is("DMG") & in_il, _el(3)).alias("subscriber_gender"),
        _pick(_is("N4") & in_il, _el(2)).alias("subscriber_state"),
        _pick(_is("N4") & in_il, _el(3)).alias("subscriber_zip"),
        _pick(_is("NM1", "PR"), _el(9)).alias("payer_id"),
        _pick(_is("NM1", "PR"), _el(3)).alias("payer_name"),
    )


def _patients(ctx: DataFrame) -> DataFrame:
    pat = ctx.filter((F.col("hl_pos") == F.col("pat_hl_pos")) & ~F.col("in_claim"))
    in_qc = F.col("nm1_qualifier") == "QC"
    return pat.groupBy("file_path", "pat_hl_pos").agg(
        _pick(_is("PAT"), _el(1)).alias("patient_relationship_code"),
        _pick(_is("NM1", "QC"), _el(3)).alias("patient_last_name"),
        _pick(_is("NM1", "QC"), _el(4)).alias("patient_first_name"),
        _pick(_is("DMG") & in_qc, _date(_e(2))).alias("patient_birth_date_2000c"),
        _pick(_is("DMG") & in_qc, _el(3)).alias("patient_gender_2000c"),
    )


def _hi_codes(ctx: DataFrame) -> DataFrame:
    """Every HI composite at claim level: one row per (claim, qualifier, code)."""
    hi = ctx.filter(_is("HI") & F.col("in_claim") & ~F.col("in_line") & ~F.col("in_cob"))
    return (
        hi.select("file_path", "clm_pos", "seg_pos", "component_sep",
                  F.posexplode(F.expr("slice(elements, 2, size(elements) - 1)")).alias("el_idx", "composite"))
        .withColumn("_parts", F.expr(f"split(composite, {_q('component_sep')})"))
        .select(
            "file_path", "clm_pos", "seg_pos", "el_idx",
            F.expr("nullif(get(_parts, 0), '')").alias("qualifier"),
            F.expr("nullif(get(_parts, 1), '')").alias("code"),
        )
        .filter(F.col("code").isNotNull())
    )


def parse_837(ctx: DataFrame, checks: DataFrame | None = None) -> dict[str, DataFrame]:
    """Build claims (one row per CLM), claim_lines (one row per LX) and claim_diagnoses.

    `ctx` is the output of segments(). Pass `checks` (transaction_checks output) to stamp each claim
    with its transaction_status so callers can quarantine claims from malformed transactions.
    """
    claim_level = ctx.filter(F.col("in_claim") & ~F.col("in_line") & ~F.col("in_cob"))
    claims = claim_level.groupBy("file_path", "clm_pos").agg(
        F.first("st_pos").alias("st_pos"),
        F.first("bp_hl_pos").alias("bp_hl_pos"),
        F.first("sub_hl_pos").alias("sub_hl_pos"),
        F.first("pat_hl_pos", ignorenulls=True).alias("pat_hl_pos"),
        F.first("isa_control_number").alias("isa_control_number"),
        F.first("st_control_number").alias("st_control_number"),
        F.first("implementation_version").alias("implementation_version"),
        _pick(_is("CLM"), _el(1)).alias("patient_control_number"),
        _pick(_is("CLM"), _try_cast(_e(2), "DECIMAL(18,2)")).alias("total_charge_amount"),
        _pick(_is("CLM"), _comp(5, 0)).alias("facility_code"),
        _pick(_is("CLM"), _comp(5, 2)).alias("claim_frequency_code"),
        _pick(_is("CL1"), _el(1)).alias("admission_type_code"),
        _pick(_is("CL1"), _el(2)).alias("admission_source_code"),
        _pick(_is("CL1"), _el(3)).alias("patient_status_code"),
        _pick(_is("DTP", "434"), _el(3)).alias("_statement_period"),
        _pick(_is("DTP", "435"), _date(_e(3))).alias("admission_date"),
        _pick(_is("REF", "G1"), _el(2)).alias("prior_authorization_number"),
        _pick(_is("REF", "9F"), _el(2)).alias("referral_number"),
        _pick(_is("REF", "F8"), _el(2)).alias("payer_claim_control_number"),
        _pick(_is("REF", "D9"), _el(2)).alias("clearinghouse_trace_number"),
        _pick(_is("NM1", "82") & (_el(8) == "XX"), _el(9)).alias("rendering_provider_npi"),
        _pick(_is("NM1", "71") & (_el(8) == "XX"), _el(9)).alias("attending_provider_npi"),
        _pick(_is("NM1", "DN") & (_el(8) == "XX"), _el(9)).alias("referring_provider_npi"),
        _pick(_is("NM1", "77") & (_el(8) == "XX"), _el(9)).alias("service_facility_npi"),
    )

    # lines
    line_level = ctx.filter(F.col("in_line"))
    sv1, sv2 = _is("SV1"), _is("SV2")
    lines = (
        line_level
        .withColumn("_proc", F.when(sv1, F.expr("get(elements, 1)")).when(sv2, F.expr("get(elements, 2)")))
        .withColumn("_proc_parts", F.expr(f"split(_proc, {_q('component_sep')})"))
        .groupBy("file_path", "clm_pos", "lx_pos").agg(
            _pick(_is("LX"), _try_cast(_e(1), "INT")).alias("line_number"),
            _pick(sv1 | sv2, F.expr("nullif(get(_proc_parts, 0), '')")).alias("procedure_qualifier"),
            _pick(sv1 | sv2, F.expr("nullif(get(_proc_parts, 1), '')")).alias("procedure_code"),
            _pick(sv1 | sv2, F.expr("filter(slice(_proc_parts, 3, 4), x -> x != '')")).alias("procedure_modifiers"),
            _pick(sv2, _el(1)).alias("revenue_code"),
            _pick(sv1, _try_cast(_e(2), "DECIMAL(18,2)")).alias("_sv1_charge"),
            _pick(sv2, _try_cast(_e(3), "DECIMAL(18,2)")).alias("_sv2_charge"),
            _pick(sv1, _el(3)).alias("_sv1_unit_basis"),
            _pick(sv2, _el(4)).alias("_sv2_unit_basis"),
            _pick(sv1, _try_cast(_e(4), "DECIMAL(15,3)")).alias("_sv1_units"),
            _pick(sv2, _try_cast(_e(5), "DECIMAL(15,3)")).alias("_sv2_units"),
            _pick(sv1, _el(5)).alias("line_place_of_service"),
            _pick(sv1, F.expr(f"transform(split(get(elements, 7), {_q('component_sep')}), x -> try_cast(x AS INT))"))
            .alias("diagnosis_pointers"),
            _pick(_is("DTP", "472"), _el(3)).alias("_service_period"),
            _pick(_is("REF", "6R"), _el(2)).alias("line_item_control_number"),
            _pick(_is("NM1", "82") & (_el(8) == "XX"), _el(9)).alias("line_rendering_provider_npi"),
            _pick(_is("LIN") & (_el(2) == "N4"), _el(3)).alias("ndc_code"),
        )
        .select(
            _claim_id().alias("claim_id"),
            "line_number", "procedure_qualifier", "procedure_code", "procedure_modifiers", "revenue_code",
            F.coalesce("_sv1_charge", "_sv2_charge").alias("line_charge_amount"),
            F.coalesce("_sv1_unit_basis", "_sv2_unit_basis").alias("unit_basis_code"),
            F.coalesce("_sv1_units", "_sv2_units").alias("service_units"),
            "line_place_of_service", "diagnosis_pointers",
            _date("_service_period").alias("service_from_date"),
            _date("element_at(split(_service_period, '-'), -1)").alias("service_to_date"),
            "line_item_control_number", "line_rendering_provider_npi", "ndc_code",
            "file_path", F.col("lx_pos").alias("_lx_pos"),
        )
    )

    # diagnoses
    hi = _hi_codes(ctx)
    seq_w = Window.partitionBy("file_path", "clm_pos").orderBy("seg_pos", "el_idx")
    diagnoses = (
        hi.filter(F.col("qualifier").isin(DX_QUALIFIERS))
        .withColumn("diagnosis_sequence", F.row_number().over(seq_w))
        .select(
            _claim_id().alias("claim_id"), "diagnosis_sequence",
            F.col("qualifier").alias("diagnosis_qualifier"),
            F.col("code").alias("diagnosis_code"),
            F.col("qualifier").isin(PRINCIPAL_DX_QUALIFIERS).alias("is_principal"),
        )
    )
    dx_summary = (
        hi.groupBy("file_path", "clm_pos").agg(
            _pick(F.col("qualifier").isin(PRINCIPAL_DX_QUALIFIERS), F.col("code")).alias("principal_diagnosis_code"),
            _pick(F.col("qualifier").isin("ABJ", "BJ"), F.col("code")).alias("admitting_diagnosis_code"),
            _pick(F.col("qualifier") == "DR", F.col("code")).alias("drg_code"),
            F.array_sort(F.collect_list(F.when(
                F.col("qualifier").isin("ABK", "BK", "ABF", "BF"),
                F.struct("seg_pos", "el_idx", "code"),
            ))).alias("_dx"),
        )
        .withColumn("diagnosis_codes", F.transform("_dx", lambda s: s["code"]))
        .drop("_dx")
    )

    line_dates = lines.groupBy("claim_id").agg(
        F.min("service_from_date").alias("_line_from"),
        F.max("service_to_date").alias("_line_to"),
        F.count(F.lit(1)).alias("line_count"),
        F.sum("line_charge_amount").alias("line_charge_total"),
    )

    claim_type = (
        F.when(F.col("implementation_version").contains("X222"), "professional")
        .when(F.col("implementation_version").contains("X223"), "institutional")
        .when(F.col("implementation_version").contains("X224"), "dental")
        .otherwise("unknown")
    )
    out = (
        claims.withColumn("claim_id", _claim_id())
        .join(_billing_providers(ctx), ["file_path", "bp_hl_pos"], "left")
        .join(_subscribers(ctx), ["file_path", "sub_hl_pos"], "left")
        .join(_patients(ctx), ["file_path", "pat_hl_pos"], "left")
        .join(dx_summary, ["file_path", "clm_pos"], "left")
        .join(line_dates, ["claim_id"], "left")
        .withColumn("claim_type", claim_type)
        .withColumn("place_of_service_code", F.when(F.col("claim_type") == "professional", F.col("facility_code")))
        .withColumn(
            "type_of_bill",
            F.when(F.col("claim_type") == "institutional", F.concat("facility_code", "claim_frequency_code")),
        )
        .withColumn("statement_from_date", _date("_statement_period"))
        .withColumn("statement_to_date", _date("element_at(split(_statement_period, '-'), -1)"))
        .withColumn("service_from_date", F.coalesce("statement_from_date", "_line_from"))
        .withColumn("service_to_date", F.coalesce("statement_to_date", "_line_to"))
        .withColumn("patient_is_subscriber", F.col("pat_hl_pos").isNull())
        .withColumn("patient_birth_date", F.coalesce("patient_birth_date_2000c", "subscriber_birth_date"))
        .withColumn("patient_gender", F.coalesce("patient_gender_2000c", "subscriber_gender"))
    )
    if checks is not None:
        out = out.join(
            checks.select("file_path", F.col("_st_pos").alias("st_pos"), "transaction_status"),
            ["file_path", "st_pos"], "left",
        )
    else:
        out = out.withColumn("transaction_status", F.lit(None).cast("string"))

    claims_out = out.select(
        "claim_id", "claim_type", "patient_control_number", "claim_frequency_code",
        "place_of_service_code", "type_of_bill", "total_charge_amount", "line_count", "line_charge_total",
        "service_from_date", "service_to_date", "statement_from_date", "statement_to_date", "admission_date",
        "admission_type_code", "admission_source_code", "patient_status_code",
        "member_id", "subscriber_last_name", "subscriber_first_name", "subscriber_birth_date",
        "subscriber_gender", "subscriber_state", "subscriber_zip", "subscriber_relationship_code",
        "group_number", "claim_filing_indicator", "payer_responsibility_code", "payer_id", "payer_name",
        "patient_is_subscriber", "patient_relationship_code", "patient_last_name", "patient_first_name",
        "patient_birth_date", "patient_gender",
        "billing_provider_npi", "billing_provider_name", "billing_provider_tin", "billing_provider_taxonomy",
        "billing_provider_state", "billing_provider_zip", "rendering_provider_npi", "attending_provider_npi",
        "referring_provider_npi", "service_facility_npi",
        "principal_diagnosis_code", "admitting_diagnosis_code", "diagnosis_codes", "drg_code",
        "prior_authorization_number", "referral_number", "payer_claim_control_number",
        "clearinghouse_trace_number",
        "isa_control_number", "st_control_number", "implementation_version", "transaction_status",
        F.col("file_path").alias("source_file"),
    )
    lines_out = lines.withColumnRenamed("file_path", "source_file").drop("_lx_pos")
    return {"claims": claims_out, "claim_lines": lines_out, "claim_diagnoses": diagnoses}


# ── validation ───────────────────────────────────────────────────────────────

def transaction_checks(raw: DataFrame, ctx: DataFrame) -> DataFrame:
    """One row per ST/SE transaction (plus one per non-X12 file) with a transaction_status:
    ok | missing_SE | segment_count_mismatch | control_number_mismatch | not_837 | not_x12."""
    body = ctx.filter((F.col("st_pos") >= 0) & ~F.col("seg_id").isin(ENVELOPE_SEGMENTS))
    tx = body.groupBy("file_path", "st_pos").agg(
        F.first("transaction_set").alias("transaction_set"),
        F.first("st_control_number").alias("st_control_number"),
        F.first("implementation_version").alias("implementation_version"),
        _pick(_is("SE"), _try_cast(_e(1), "INT")).alias("se_segment_count"),
        _pick(_is("SE"), _el(2)).alias("se_control_number"),
        # ST..SE inclusive (GS/GE/ISA/IEA between transactions are excluded above)
        F.count(F.lit(1)).alias("segment_count"),
        F.count(F.when(_is("CLM"), 1)).alias("claim_count"),
    )
    status = (
        F.when(F.col("se_segment_count").isNull(), "missing_SE")
        .when(F.col("transaction_set") != "837", "not_837")
        .when(F.col("se_segment_count") != F.col("segment_count"), "segment_count_mismatch")
        .when(F.col("se_control_number") != F.col("st_control_number"), "control_number_mismatch")
        .otherwise("ok")
    )
    tx = tx.withColumn("transaction_status", status).withColumnRenamed("st_pos", "_st_pos")

    bad_files = (
        _with_x12_flags(raw).filter(~F.col("is_x12"))
        .select(
            "file_path", F.lit(None).cast("bigint").alias("_st_pos"),
            F.lit(None).cast("string").alias("transaction_set"),
            F.lit(None).cast("string").alias("st_control_number"),
            F.lit(None).cast("string").alias("implementation_version"),
            F.lit(None).cast("int").alias("se_segment_count"),
            F.lit(None).cast("string").alias("se_control_number"),
            F.lit(0).cast("bigint").alias("segment_count"),
            F.lit(0).cast("bigint").alias("claim_count"),
            F.lit("not_x12").alias("transaction_status"),
        )
    )
    return tx.unionByName(bad_files)
