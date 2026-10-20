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
    """Locate the ISA header and read the delimiters it declares.

    The element separator is the character after "ISA". Splitting the ISA on it (at most 17 parts) leaves
    ISA16 as the first character of the last part: that is the component separator, and the next character
    is the segment terminator. This works for spec-compliant fixed-width ISAs (106 chars, terminator at 106)
    and for senders that trim the padding; `isa_fixed_width` records which one a file is.
    """
    sep = "substring(_x12, 4, 1)"
    return (
        # batch reads report dbfs:/Volumes/..., Auto Loader /Volumes/...; normalize so claim_id is stable
        raw.withColumn("file_path", F.regexp_replace("file_path", "^dbfs:", ""))
        .withColumn("_x12", F.expr("substring(value, greatest(instr(value, 'ISA'), 1))"))
        .withColumn("_isa_parts", F.expr(f"split(_x12, {_q(sep)}, 17)"))
        .withColumn("element_sep", F.expr(sep))
        .withColumn("component_sep", F.expr("substring(get(_isa_parts, 16), 1, 1)"))
        .withColumn("segment_term", F.expr("substring(get(_isa_parts, 16), 2, 1)"))
        .withColumn(
            "is_x12",
            (F.instr("value", "ISA") > 0) & F.col("_x12").startswith("ISA")
            & (F.size("_isa_parts") == 17) & ~F.col("element_sep").rlike("[A-Za-z0-9 ]")
            & (F.col("component_sep") != "") & (F.col("segment_term") != ""),
        )
        .withColumn(
            "isa_fixed_width",
            (F.substring("_x12", 104, 1) == F.col("element_sep"))
            & (F.substring("_x12", 105, 1) == F.col("component_sep"))
            & (F.substring("_x12", 106, 1) == F.col("segment_term")),
        )
    )


def segments(raw: DataFrame) -> DataFrame:
    """Explode files into segments and attach loop context columns. Non-X12 files are dropped here
    (transaction_checks reports them)."""
    segs = (
        _with_x12_flags(raw).filter("is_x12")
        .select(
            "file_path", "element_sep", "component_sep", "isa_fixed_width",
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
        carry(_is("GS"), F.concat_ws("", _el(4), F.lpad(F.coalesce(_el(5), F.lit("0000")), 4, "0")))
        .alias("functional_group_datetime"),
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
        _pick(_is("NM1", "85"), _el(8)).alias("billing_provider_id_qualifier"),
        _pick(_is("N3") & in_85, F.concat_ws(" ", _el(1), _el(2))).alias("billing_provider_address"),
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
        F.first("functional_group_datetime").alias("functional_group_datetime"),
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
        _pick(_is("N4") & (F.col("nm1_qualifier") == "77"), _el(3)).alias("service_facility_zip"),
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

    iv = F.col("implementation_version")
    claim_type = (  # 5010: X222 / X223 / X224; 4010A1: X098 / X096 / X097
        F.when(iv.contains("X222") | iv.contains("X098"), "professional")
        .when(iv.contains("X223") | iv.contains("X096"), "institutional")
        .when(iv.contains("X224") | iv.contains("X097"), "dental")
        .otherwise("unknown")
    )
    x12_version = F.when(iv.startswith("004010"), "4010").when(iv.startswith("005010"), "5010")
    out = (
        claims.withColumn("claim_id", _claim_id())
        .join(_billing_providers(ctx), ["file_path", "bp_hl_pos"], "left")
        .join(_subscribers(ctx), ["file_path", "sub_hl_pos"], "left")
        .join(_patients(ctx), ["file_path", "pat_hl_pos"], "left")
        .join(dx_summary, ["file_path", "clm_pos"], "left")
        .join(line_dates, ["claim_id"], "left")
        .withColumn("claim_type", claim_type)
        .withColumn("x12_version", x12_version)
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
        "claim_id", "claim_type", "x12_version", "patient_control_number", "claim_frequency_code",
        "place_of_service_code", "type_of_bill", "total_charge_amount", "line_count", "line_charge_total",
        "service_from_date", "service_to_date", "statement_from_date", "statement_to_date", "admission_date",
        "admission_type_code", "admission_source_code", "patient_status_code",
        "member_id", "subscriber_last_name", "subscriber_first_name", "subscriber_birth_date",
        "subscriber_gender", "subscriber_state", "subscriber_zip", "subscriber_relationship_code",
        "group_number", "claim_filing_indicator", "payer_responsibility_code", "payer_id", "payer_name",
        "patient_is_subscriber", "patient_relationship_code", "patient_last_name", "patient_first_name",
        "patient_birth_date", "patient_gender",
        "billing_provider_npi", "billing_provider_id_qualifier", "billing_provider_name", "billing_provider_tin",
        "billing_provider_taxonomy", "billing_provider_address", "billing_provider_state", "billing_provider_zip",
        "rendering_provider_npi", "attending_provider_npi", "referring_provider_npi", "service_facility_npi",
        "service_facility_zip",
        "principal_diagnosis_code", "admitting_diagnosis_code", "diagnosis_codes", "drg_code",
        "prior_authorization_number", "referral_number", "payer_claim_control_number",
        "clearinghouse_trace_number",
        "isa_control_number", "st_control_number", "implementation_version", "functional_group_datetime",
        "transaction_status", F.col("file_path").alias("source_file"),
    )
    # Line-level mapping rules that need claim context:
    #  - performing provider: line 2420A > claim 2310B rendering > 2310A attending (837I) > 2010AA billing
    #  - place of service: line SV105 overrides claim CLM05-1 (837P)
    #  - diagnoses: SV107 pointers are 1-based positions in the claim's ordered HI list; out of range -> NULL
    ctx_cols = out.select("claim_id", "rendering_provider_npi", "attending_provider_npi", "billing_provider_npi",
                          "place_of_service_code", "diagnosis_codes")
    lines_out = (
        lines.join(ctx_cols, "claim_id", "left")
        .withColumn("effective_rendering_npi", F.coalesce("line_rendering_provider_npi", "rendering_provider_npi",
                                                          "attending_provider_npi", "billing_provider_npi"))
        .withColumn("effective_place_of_service", F.coalesce("line_place_of_service", "place_of_service_code"))
        .withColumn("line_diagnosis_codes",
                    F.expr("transform(diagnosis_pointers, p -> get(diagnosis_codes, p - 1))"))
        .drop("rendering_provider_npi", "attending_provider_npi", "billing_provider_npi", "place_of_service_code",
              "diagnosis_codes", "_lx_pos")
        .withColumnRenamed("file_path", "source_file")
    )
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
        F.first("isa_fixed_width").alias("isa_fixed_width"),
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
            F.lit(None).cast("boolean").alias("isa_fixed_width"),
            F.lit(None).cast("int").alias("se_segment_count"),
            F.lit(None).cast("string").alias("se_control_number"),
            F.lit(0).cast("bigint").alias("segment_count"),
            F.lit(0).cast("bigint").alias("claim_count"),
            F.lit("not_x12").alias("transaction_status"),
        )
    )
    return tx.unionByName(bad_files)


# ── claim versions (replacements / voids) ────────────────────────────────────

def resolve_claim_versions(claims: DataFrame,
                           link_keys: tuple[str, ...] = ("billing_provider_npi", "member_id",
                                                         "patient_control_number")) -> DataFrame:
    """Current view of each claim: the latest version per claim, with voided claims removed.

    CLM05-3 frequency: 1 original, 7 replacement, 8 void. Replacements and voids carry REF*F8 (the payer's
    claim control number of the original). A payer that keeps an ICN -> claim map can pass link_keys that
    use it; the default links versions by billing NPI + member + patient control number, the usual fallback
    when the 837 alone is all you have. Versions are ordered by the GS date/time of the file that carried
    them. Only claims from valid transactions are considered.
    """
    keys = list(link_keys)
    base = claims.filter(F.col("transaction_status").isNull() | (F.col("transaction_status") == "ok"))
    w = Window.partitionBy(*keys).orderBy(F.col("functional_group_datetime").desc_nulls_last(),
                                          F.col("source_file").desc(), F.col("claim_id").desc())
    return (
        base.withColumn("_rank", F.row_number().over(w))
        .withColumn("version_count", F.count(F.lit(1)).over(Window.partitionBy(*keys)))
        .filter((F.col("_rank") == 1) & (F.coalesce(F.col("claim_frequency_code"), F.lit("1")) != "8"))
        .drop("_rank")
    )


# ── data-quality checks ──────────────────────────────────────────────────────

# rule_id -> (severity, check). Sources are in references/quality_rules.md.
QUALITY_RULES = {
    "NPI_INVALID": ("error", "NPI is not 10 digits with a valid Luhn check digit (prefix 80840)"),
    "BILLING_ID_NOT_NPI": ("error", "5010 billing provider primary ID qualifier is not XX (NPI)"),
    "BILLING_ADDRESS_PO_BOX": ("error", "5010 billing provider address is a PO Box / lock box"),
    "ZIP_INCOMPLETE": ("error", "5010 billing provider / service facility ZIP is not 9 digits"),
    "ICD10_FORMAT": ("error", "ICD-10 code is not 3-7 characters (letter, digit, then alphanumerics, no decimal)"),
    "PROCEDURE_CODE_FORMAT": ("error", "HCPCS/CPT code is not 00000, 0000F, 0000T or A0000"),
    "REVENUE_CODE_FORMAT": ("error", "revenue code is not 4 digits (leading zero kept)"),
    "POS_INVALID": ("error", "place of service is not a valid CMS code (or is unassigned)"),
    "DATE_INVALID": ("error", "future date, birth after service, or service outside the statement period"),
    "DX_POINTER_INVALID": ("error", "diagnosis pointer is not 1..N of the claim's diagnoses, or more than 4"),
    "TOTAL_MISMATCH": ("error", "claim total charge differs from the sum of line charges"),
    "DUPLICATE_CLAIM": ("warning", "later submission duplicating an earlier claim (member, provider, date, "
                                   "procedures, charge)"),
    "GENDER_CODE_INVALID": ("warning", "DMG03 gender is not M, F or U"),
    "FILING_INDICATOR_INVALID": ("warning", "SBR09 claim filing indicator is not an X12 code"),
    "ISA_NOT_FIXED_WIDTH": ("warning", "ISA header is not the fixed-width 106 characters the standard requires"),
}
_POS_UNASSIGNED = ([28, 29, 30] + list(range(35, 41)) + list(range(43, 49)) + [59, 63, 64] + list(range(67, 71))
                   + list(range(73, 81)) + list(range(82, 99)))
_FILING_CODES = ["11", "12", "13", "14", "15", "16", "17", "AM", "BL", "CH", "CI", "DS", "FI", "HM", "LM", "MA",
                 "MB", "MC", "OF", "TV", "VA", "WC", "ZZ"]


def npi_is_valid(col: str) -> Column:
    """CMS NPI check digit: Luhn mod 10 over the first 9 digits, computed as if prefixed by 80840 (+24)."""
    d = f"try_cast(substr({col}, i, 1) AS INT)"
    return F.expr(
        f"{col} RLIKE '^[0-9]{{10}}$' AND "
        f"(10 - aggregate(sequence(1, 9), 24, (acc, i) -> acc + CASE WHEN (9 - i) % 2 = 0 "
        f"THEN {d} * 2 - CASE WHEN {d} * 2 > 9 THEN 9 ELSE 0 END ELSE {d} END) % 10) % 10 "
        f"= try_cast(substr({col}, 10, 1) AS INT)"
    )


def _pos_is_valid(col: str) -> Column:
    return F.col(col).rlike("^[0-9]{2}$") & F.expr(f"try_cast({col} AS INT) BETWEEN 1 AND 99") \
        & ~F.expr(f"try_cast({col} AS INT)").isin(_POS_UNASSIGNED)


def quality_checks(claims: DataFrame, claim_lines: DataFrame, claim_diagnoses: DataFrame,
                   checks: DataFrame | None = None, as_of: str | None = None) -> DataFrame:
    """One row per (claim, line, rule) that fails a deterministic data-quality rule (QUALITY_RULES).

    Columns: claim_id, patient_control_number, line_number, rule_id, severity, field, value, message,
    source_file. File-level rules (ISA_NOT_FIXED_WIDTH) have a NULL claim_id. Run on claims from valid
    transactions; `as_of` (YYYY-MM-DD, default today) is the reference date for future-date checks.
    """
    today = F.lit(as_of).cast("date") if as_of else F.current_date()
    c = claims.filter(F.col("transaction_status").isNull() | (F.col("transaction_status") == "ok"))
    pcn = c.select("claim_id", "patient_control_number", "source_file")

    def flag(df, cond, rule, field, value, line=None):
        sev, msg = QUALITY_RULES[rule]
        return df.filter(cond).select(
            "claim_id", F.lit(None).cast("int").alias("line_number") if line is None else F.col(line),
            F.lit(rule).alias("rule_id"), F.lit(sev).alias("severity"), F.lit(field).alias("field"),
            F.col(value).cast("string").alias("value"), F.lit(msg).alias("message"))

    parts = []
    for col in ("billing_provider_npi", "rendering_provider_npi", "attending_provider_npi",
                "referring_provider_npi", "service_facility_npi"):
        parts.append(flag(c, F.col(col).isNotNull() & ~F.coalesce(npi_is_valid(col), F.lit(False)),
                          "NPI_INVALID", col, col))
    parts.append(flag(c, F.coalesce(F.col("billing_provider_id_qualifier"), F.lit("")) != "XX",
                      "BILLING_ID_NOT_NPI", "billing_provider_id_qualifier", "billing_provider_id_qualifier"))
    parts.append(flag(c, F.col("billing_provider_address").rlike(
        r"(?i)\b(P\.?\s*O\.?\s*BOX|POST\s+OFFICE\s+BOX|LOCK\s*BOX)\b"),
        "BILLING_ADDRESS_PO_BOX", "billing_provider_address", "billing_provider_address"))
    for col in ("billing_provider_zip", "service_facility_zip"):
        cond = ~F.coalesce(F.col(col), F.lit("")).rlike("^[0-9]{9}$")
        if col == "service_facility_zip":
            cond = F.col(col).isNotNull() & cond
        parts.append(flag(c, cond, "ZIP_INCOMPLETE", col, col))
    parts.append(flag(c, F.col("place_of_service_code").isNotNull() & ~_pos_is_valid("place_of_service_code"),
                      "POS_INVALID", "place_of_service_code", "place_of_service_code"))
    parts.append(flag(c, (F.col("service_from_date") > today) | (F.col("service_to_date") > today)
                      | (F.col("patient_birth_date") > F.col("service_from_date"))
                      | (F.col("statement_from_date") > F.col("statement_to_date")),
                      "DATE_INVALID", "service_from_date", "service_from_date"))
    parts.append(flag(c, (F.coalesce(F.col("claim_frequency_code"), F.lit("1")) != "8")
                      & ~F.col("total_charge_amount").eqNullSafe(F.col("line_charge_total")),
                      "TOTAL_MISMATCH", "total_charge_amount", "total_charge_amount"))
    parts.append(flag(c, F.col("patient_gender").isNotNull() & ~F.col("patient_gender").isin("M", "F", "U"),
                      "GENDER_CODE_INVALID", "patient_gender", "patient_gender"))
    parts.append(flag(c, F.col("claim_filing_indicator").isNotNull()
                      & ~F.col("claim_filing_indicator").isin(_FILING_CODES),
                      "FILING_INDICATOR_INVALID", "claim_filing_indicator", "claim_filing_indicator"))

    # duplicates: same member + patient + billing NPI + service date + charge + procedures, original claims only
    procs = claim_lines.groupBy("claim_id").agg(
        F.concat_ws(",", F.array_sort(F.collect_list(F.coalesce("procedure_code", "revenue_code")))).alias("_procs"))
    sig = ["member_id", "patient_birth_date", "patient_first_name", "billing_provider_npi", "service_from_date",
           "total_charge_amount", "_procs"]
    dup_w = Window.partitionBy(*sig).orderBy("functional_group_datetime", "source_file", "patient_control_number")
    dups = (c.filter(~F.coalesce(F.col("claim_frequency_code"), F.lit("1")).isin("7", "8"))
            .join(procs, "claim_id", "left").withColumn("_n", F.row_number().over(dup_w)))
    parts.append(flag(dups, F.col("_n") > 1, "DUPLICATE_CLAIM", "patient_control_number", "patient_control_number"))

    # line-level rules
    ln = claim_lines.join(c.select("claim_id", "claim_type", "statement_from_date", "statement_to_date"), "claim_id")
    parts.append(flag(ln, (F.col("procedure_qualifier") == "HC")
                      & ~F.coalesce(F.col("procedure_code"), F.lit("")).rlike("^([0-9]{5}|[0-9]{4}[FT]|[A-V][0-9]{4})$"),
                      "PROCEDURE_CODE_FORMAT", "procedure_code", "procedure_code", line="line_number"))
    parts.append(flag(ln, F.col("revenue_code").isNotNull() & ~F.col("revenue_code").rlike("^[0-9]{4}$"),
                      "REVENUE_CODE_FORMAT", "revenue_code", "revenue_code", line="line_number"))
    parts.append(flag(ln, F.col("line_place_of_service").isNotNull() & ~_pos_is_valid("line_place_of_service"),
                      "POS_INVALID", "line_place_of_service", "line_place_of_service", line="line_number"))
    parts.append(flag(ln, F.col("diagnosis_pointers").isNotNull()
                      & ((F.size("diagnosis_pointers") > 4) | F.expr("exists(line_diagnosis_codes, x -> x IS NULL)")),
                      "DX_POINTER_INVALID", "diagnosis_pointers", "diagnosis_pointers", line="line_number"))
    parts.append(flag(ln, (F.col("service_from_date") > today) | (F.col("service_to_date") > today)
                      | ((F.col("claim_type") == "institutional")
                         & ((F.col("service_from_date") < F.col("statement_from_date"))
                            | (F.col("service_to_date") > F.col("statement_to_date")))),
                      "DATE_INVALID", "line_service_date", "service_from_date", line="line_number"))
    parts.append(flag(ln, F.col("line_rendering_provider_npi").isNotNull()
                      & ~F.coalesce(npi_is_valid("line_rendering_provider_npi"), F.lit(False)),
                      "NPI_INVALID", "line_rendering_provider_npi", "line_rendering_provider_npi", line="line_number"))

    # diagnosis format (ICD-10 qualifiers only; ICD-9 BK/BF in 4010 data is not held to ICD-10 shape)
    dx = claim_diagnoses.filter(F.col("diagnosis_qualifier").isin("ABK", "ABF", "ABJ", "APR", "ABN"))
    parts.append(flag(dx, ~F.col("diagnosis_code").rlike("^[A-Z][0-9][0-9A-Z]{1,5}$"),
                      "ICD10_FORMAT", "diagnosis_code", "diagnosis_code"))

    out = parts[0]
    for p in parts[1:]:
        out = out.unionByName(p)
    out = out.join(pcn, "claim_id", "inner")

    if checks is not None:
        sev, msg = QUALITY_RULES["ISA_NOT_FIXED_WIDTH"]
        isa = (checks.filter(F.col("isa_fixed_width") == F.lit(False))
               .select(F.lit(None).cast("string").alias("claim_id"), F.lit(None).cast("int").alias("line_number"),
                       F.lit("ISA_NOT_FIXED_WIDTH").alias("rule_id"), F.lit(sev).alias("severity"),
                       F.lit("ISA").alias("field"), F.lit(None).cast("string").alias("value"), F.lit(msg).alias("message"),
                       F.lit(None).cast("string").alias("patient_control_number"), F.col("file_path").alias("source_file"))
               .dropDuplicates(["source_file"]))
        out = out.unionByName(isa)
    return out.select("claim_id", "patient_control_number", "line_number", "rule_id", "severity", "field", "value",
                      "message", "source_file")
