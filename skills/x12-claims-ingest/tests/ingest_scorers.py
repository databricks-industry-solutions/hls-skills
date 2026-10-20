"""x12-claims-ingest scorers: runnable, pure-Python, deterministic.

Every scorer compares an `IngestGold` (the answer key written by scripts/generate_837.py, so labels
are exact) with an `IngestOutput` (the tables a run actually wrote, read back by column name). The
components feed the objective in objective.py and are wrapped as binary mlflow.genai @scorer
functions by `mlflow_scorers()` for the with/without-skill comparison.

Output contract (the benchmark prompts name these columns, so both arms are graded the same way):
    claims:      patient_control_number, member_id, payer_id, billing_provider_npi, total_charge_amount,
                 principal_diagnosis_code, patient_birth_date, patient_gender
    claim_lines: patient_control_number, line_number, procedure_code, revenue_code, line_charge_amount,
                 service_units, service_date
    file_checks: file_name, status   ('ok' or any other value naming the problem)
Task-specific extras (declared per task in expectations.json, deterministic_checks):
    claims: x12_version                     claim_lines: rendering_provider_npi, line_diagnosis_codes
    claim_quality: patient_control_number, rule_id   (quality tasks only)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CLAIM_FIELDS = ["member_id", "payer_id", "billing_provider_npi", "total_charge_amount",
                "principal_diagnosis_code", "patient_birth_date", "patient_gender"]
LINE_FIELDS = ["procedure_code", "revenue_code", "line_charge_amount", "service_units", "service_date"]
AMOUNT_FIELDS = {"total_charge_amount", "line_charge_amount", "service_units"}
DATE_FIELDS = {"patient_birth_date", "service_date"}
QUALITY_RULE_IDS = {"NPI_INVALID", "BILLING_ADDRESS_PO_BOX", "ZIP_INCOMPLETE", "ICD10_FORMAT", "PROCEDURE_CODE_FORMAT",
                    "REVENUE_CODE_FORMAT", "POS_INVALID", "DATE_INVALID", "DX_POINTER_INVALID", "TOTAL_MISMATCH",
                    "DUPLICATE_CLAIM"}


# --- normalization --------------------------------------------------------------

def _norm(name: str, value):
    """Compare values the way a reviewer would: amounts numerically, dates as ISO, codes as trimmed text."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    if name == "x12_version":
        import re
        m = re.search(r"(4010|5010)", str(value))
        return m.group(1) if m else str(value).strip()
    if name == "line_diagnosis_codes":
        import re
        items = value if isinstance(value, (list, tuple)) else re.split(r"[,;|\s]+", re.sub(r"[\[\]'\"]", "", str(value)))
        items = [str(i).strip().upper() for i in items if i is not None and str(i).strip()]
        return ",".join(items) or None
    if name in AMOUNT_FIELDS:
        try:
            return str(Decimal(str(value)).quantize(Decimal("0.01")))  # text, so JSON round trips are lossless
        except (InvalidOperation, ValueError):
            return str(value).strip()
    if name in DATE_FIELDS:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        for candidate, fmt in ((text[:8], "%Y%m%d"), (text[:10], "%Y-%m-%d"), (text[:10], "%m/%d/%Y")):
            try:
                return datetime.strptime(candidate, fmt).date().isoformat()
            except ValueError:
                pass
        return text
    return str(value).strip().upper()


def _file_name(path) -> str:
    return str(path).rstrip("/").rsplit("/", 1)[-1]


# --- data contracts ---------------------------------------------------------------

@dataclass
class IngestGold:
    claims: dict                      # pcn -> {field: normalized value}
    lines: dict                       # pcn -> {line_number: {field: normalized value}}
    bad_files: set                    # file names whose transactions are not all ok
    invalid_pcns: set                 # claims inside truncated / invalid transactions
    requires_run: bool = False        # task asks for a job/pipeline that must actually run
    quality: set = field(default_factory=set)   # {(pcn, rule_id)} planted defects; empty = not a quality task


@dataclass
class IngestOutput:
    claims: dict = field(default_factory=dict)        # pcn -> {field: normalized value}, main claims table
    lines: dict = field(default_factory=dict)         # pcn -> {line_number: {field: normalized value}}
    flagged_pcns: set = field(default_factory=set)    # rows in the main table marked not-ok (status column)
    reported_bad_files: set = field(default_factory=set)
    ran_where_asked: bool | None = None               # None = not part of the task
    quality_flags: set = field(default_factory=set)   # {(pcn, rule_id)} from claim_quality, known rule ids only


def gold_from_key(key: dict, requires_run: bool = False, claim_extras: tuple = (), line_extras: tuple = (),
                  quality: bool = False) -> IngestGold:
    """Answer key -> IngestGold. Extras and quality are opt-in per task, so tasks 1-4 score as before."""
    line_src = {"rendering_provider_npi": "rendering_npi", "line_diagnosis_codes": "diagnosis_codes"}
    claims, lines, qual = {}, {}, set()
    for c in key["claims"]:
        pcn = _norm("pcn", c["patient_control_number"])
        claims[pcn] = {f: _norm(f, c.get(f)) for f in (*CLAIM_FIELDS, *claim_extras)}
        lines[pcn] = {}
        for ln in c["lines"]:
            gl = {
                "procedure_code": _norm("procedure_code", ln["procedure_code"]),
                "revenue_code": _norm("revenue_code", ln["revenue_code"]),
                "line_charge_amount": _norm("line_charge_amount", ln["charge"]),
                "service_units": _norm("service_units", ln["units"]),
                "service_date": _norm("service_date", ln["service_date"]),
            }
            for f in line_extras:
                gl[f] = _norm(f, ln.get(line_src.get(f, f)))
            lines[pcn][int(ln["line_number"])] = gl
        if quality:
            qual |= {(pcn, r) for r in c.get("defects", []) if r in QUALITY_RULE_IDS}
    bad = {t["file"] for t in key["transactions"] if t["transaction_status"] != "ok"}
    invalid = {_norm("pcn", p) for p in key.get("truncated_claims", [])}
    return IngestGold(claims, lines, bad, invalid, requires_run, qual)


def output_from_records(claim_rows: list[dict], line_rows: list[dict], check_rows: list[dict] | None = None,
                        ran_where_asked: bool | None = None, quality_rows: list[dict] | None = None,
                        claim_extras: tuple = (), line_extras: tuple = ()) -> IngestOutput:
    """Build an IngestOutput from table rows (dicts keyed by the contract's column names, any case).

    A claims row with a status-like column (status / transaction_status / is_valid) that is not ok counts
    as flagged, i.e. the run marked it instead of silently loading it as good.
    """
    out = IngestOutput(ran_where_asked=ran_where_asked)
    for raw in claim_rows:
        r = {str(k).lower(): v for k, v in raw.items()}
        pcn = _norm("pcn", r.get("patient_control_number"))
        if pcn is None:
            continue
        out.claims[pcn] = {f: _norm(f, r.get(f)) for f in (*CLAIM_FIELDS, *claim_extras)}
        status = r.get("status", r.get("transaction_status"))
        valid = r.get("is_valid")
        if (status is not None and str(status).strip().lower() not in ("ok", "valid", "pass", "passed")) or valid is False:
            out.flagged_pcns.add(pcn)
    for raw in line_rows:
        r = {str(k).lower(): v for k, v in raw.items()}
        pcn = _norm("pcn", r.get("patient_control_number"))
        try:
            ln = int(Decimal(str(r.get("line_number"))))
        except (InvalidOperation, ValueError, TypeError):
            continue
        out.lines.setdefault(pcn, {})[ln] = {f: _norm(f, r.get(f)) for f in (*LINE_FIELDS, *line_extras)}
    for raw in check_rows or []:
        r = {str(k).lower(): v for k, v in raw.items()}
        name = r.get("file_name") or r.get("file_path") or r.get("source_file")
        status = str(r.get("status", r.get("transaction_status", ""))).strip().lower()
        if name and status not in ("ok", "valid", "pass", "passed"):
            out.reported_bad_files.add(_file_name(name))
    for raw in quality_rows or []:
        r = {str(k).lower(): v for k, v in raw.items()}
        rule = str(r.get("rule_id") or "").strip().upper()
        pcn = _norm("pcn", r.get("patient_control_number"))
        if pcn and rule in QUALITY_RULE_IDS:  # OTHER / unknown ids are ignored, not penalized
            out.quality_flags.add((pcn, rule))
    return out


# --- component scorers --------------------------------------------------------------

def silent_bad_loads(gold: IngestGold, out: IngestOutput) -> int:
    """Claims from invalid transactions sitting in the main claims table with no flag. The gate."""
    return len({p for p in gold.invalid_pcns if p in out.claims and p not in out.flagged_pcns})


def claim_set_f1(gold: IngestGold, out: IngestOutput) -> dict:
    loaded = {p for p in out.claims if p not in out.flagged_pcns}
    tp = len(loaded & set(gold.claims))
    precision = tp / len(loaded) if loaded else 0.0
    recall = tp / len(gold.claims) if gold.claims else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def field_accuracy(gold: IngestGold, out: IngestOutput) -> dict:
    """Share of (matched claim, field) values that equal the key; also per-field accuracy."""
    matched = [p for p in gold.claims if p in out.claims]
    if not matched:
        return {"accuracy": 0.0, "per_field": {f: 0.0 for f in CLAIM_FIELDS}}
    fields = list(gold.claims[matched[0]])
    per_field = {f: sum(out.claims[p].get(f) == gold.claims[p][f] for p in matched) / len(matched)
                 for f in fields}
    return {"accuracy": sum(per_field.values()) / len(per_field), "per_field": per_field}


def line_accuracy(gold: IngestGold, out: IngestOutput) -> float:
    """Share of key line fields reproduced, over every line of every key claim (missing lines count wrong)."""
    total = correct = 0
    for pcn, glines in gold.lines.items():
        olines = out.lines.get(pcn, {})
        for n, gl in glines.items():
            total += len(gl)
            if n in olines:  # a missing line scores 0, even where the key value is blank
                correct += sum(olines[n].get(f) == gl[f] for f in gl)
    return correct / total if total else 1.0


def validation_reporting(gold: IngestGold, out: IngestOutput) -> float:
    """Recall of the bad files the run identified (1.0 when the task has none)."""
    if not gold.bad_files:
        return 1.0
    return len(gold.bad_files & out.reported_bad_files) / len(gold.bad_files)


def quality_detection(gold: IngestGold, out: IngestOutput) -> dict:
    """Precision / recall / F1 of (claim, rule) flags against the planted defects (quality tasks only)."""
    if not gold.quality:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "applicable": False}
    tp = len(gold.quality & out.quality_flags)
    precision = tp / len(out.quality_flags) if out.quality_flags else 0.0
    recall = tp / len(gold.quality)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "applicable": True}


def ran_where_asked(gold: IngestGold, out: IngestOutput) -> float:
    if not gold.requires_run:
        return 1.0
    return 1.0 if out.ran_where_asked else 0.0


# --- mlflow wrappers -----------------------------------------------------------------

PASS = 0.99  # synthetic labels are exact, so "correct" means essentially all of it
QUALITY_PASS = 0.95  # pre-registered 2026-10-19 for x12-006


def mlflow_scorers():
    """Binary mlflow.genai @scorer callables over rows shaped
    outputs={"ingest_output": IngestOutput.__dict__-like dict}, expectations={"ingest_gold": dict}.

    mlflow is imported lazily so the pure-Python scorers work without it.
    """
    from mlflow.genai.scorers import scorer

    def _gold(expectations: dict) -> IngestGold:
        g = dict(expectations["ingest_gold"])
        g["bad_files"], g["invalid_pcns"] = set(g["bad_files"]), set(g["invalid_pcns"])
        g["quality"] = {tuple(x) for x in g.get("quality", [])}
        g["lines"] = {p: {int(k): v for k, v in ls.items()} for p, ls in g["lines"].items()}
        return IngestGold(**g)

    def _out(outputs: dict) -> IngestOutput:
        o = dict(outputs["ingest_output"])
        o["flagged_pcns"], o["reported_bad_files"] = set(o["flagged_pcns"]), set(o["reported_bad_files"])
        o["quality_flags"] = {tuple(x) for x in o.get("quality_flags", [])}
        o["lines"] = {p: {int(k): v for k, v in ls.items()} for p, ls in o["lines"].items()}
        return IngestOutput(**o)

    @scorer
    def no_silent_bad_load(outputs: dict, expectations: dict) -> bool:
        return silent_bad_loads(_gold(expectations), _out(outputs)) == 0

    @scorer
    def claims_complete(outputs: dict, expectations: dict) -> bool:
        return claim_set_f1(_gold(expectations), _out(outputs))["f1"] >= PASS

    @scorer
    def claim_fields_correct(outputs: dict, expectations: dict) -> bool:
        return field_accuracy(_gold(expectations), _out(outputs))["accuracy"] >= PASS

    @scorer
    def lines_correct(outputs: dict, expectations: dict) -> bool:
        return line_accuracy(_gold(expectations), _out(outputs)) >= PASS

    @scorer
    def bad_files_reported(outputs: dict, expectations: dict) -> bool:
        return validation_reporting(_gold(expectations), _out(outputs)) >= PASS

    @scorer
    def ran_as_asked(outputs: dict, expectations: dict) -> bool:
        return ran_where_asked(_gold(expectations), _out(outputs)) == 1.0

    @scorer
    def quality_issues_found(outputs: dict, expectations: dict) -> bool:
        return quality_detection(_gold(expectations), _out(outputs))["f1"] >= QUALITY_PASS

    return [no_silent_bad_load, claims_complete, claim_fields_correct, lines_correct,
            bad_files_reported, ran_as_asked, quality_issues_found]


def to_jsonable(obj) -> dict:
    """IngestGold / IngestOutput -> JSON-safe dict (sets become sorted lists, Decimals strings)."""
    def conv(v):
        if isinstance(v, set):
            return sorted(conv(x) for x in v)
        if isinstance(v, tuple):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {str(k): conv(x) for k, x in v.items()}
        if isinstance(v, Decimal):
            return str(v)
        return v
    return {k: conv(v) for k, v in obj.__dict__.items()}
