#!/usr/bin/env python3
"""Profile a source schema and draft a mapping when the SA has none.

Genie Code runs this in Phase 1 when no `<customer>_mapping.yaml` exists. It inventories a
schema, samples candidate code/status columns, matches physical tables+columns to the canonical
model by name synonyms, and writes a best-effort mapping draft. Every low-confidence binding and
every unmatched required field carries a `# REVIEW:` comment for the SA to confirm.

Modes
-----
live      Query <catalog>.information_schema.columns via databricks-sdk Statement Execution and
          sample distinct values of candidate enum columns.
              profile_source.py --catalog c --schema s --warehouse-id <id> [--profile <cli-profile>]
offline   Read a JSON dump of columns instead of a live workspace (testing / air-gapped).
              profile_source.py --catalog c --schema s --schema-json cols.json
          cols.json = [{"table_name": "...", "column_name": "...", "data_type": "...",
                        "sample_values": ["...", ...]}, ...]  (sample_values optional)

Outputs (to --out, default cwd)
    <schema>_profile.json        inventory + samples
    <schema>_mapping.draft.yaml  the mapping draft (feed to generate_semantic_layer.py after review)

See references/profiling.md for the heuristics.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "references"

# ── entity table-name synonyms (see profiling.md) ────────────────────────────
ENTITY_SYNS = {
    "encounter":    ["encounter", "visit", "enc", "admission", "ipstay", "inpatient"],
    "appointment":  ["appointment", "appt", "booking"],
    "slot":         ["slot", "scheduleblock", "block", "availability", "capacity"],
    "claim":        ["claimheader", "claim", "clm", "claims"],
    "claim_line":   ["claimline", "clmline", "serviceline", "claimdetail"],
    "enrollment":   ["enrollment", "coverage", "membercoverage", "elig", "membership"],
    "member_month": ["membermonth", "medecon", "medicaleconomics", "pmpm", "econ"],
    "care_gap":     ["caregap", "gap", "hedis", "qualitygap", "measuregap"],
    "member":       ["member", "mbr"],
    "patient":      ["patient", "pat"],
    "provider":     ["provider", "prov", "npi"],
    "facility":     ["facility", "fac", "site"],
}

# ── field column-name synonyms (normalized: lowercase, alnum only) ────────────
FIELD_SYNS = {
    "patient_id":            ["patientid", "patid", "mrn"],
    "member_id":             ["memberid", "mbrid", "subscrid", "subscriberid"],
    "encounter_id":          ["encounterid", "encid", "visitid"],
    "appointment_id":        ["appointmentid", "apptid"],
    "slot_id":               ["slotid", "blockid"],
    "claim_id":              ["claimid", "clmid"],
    "claim_line_id":         ["claimlineid", "clmlineid", "servicelineid"],
    "care_gap_id":           ["caregapid", "gapid"],
    "provider_id":           ["providerid", "provid", "billprovnpi", "npi"],
    "facility_id":           ["facilityid", "facid"],
    "payer_id":              ["payerid"],
    "plan_id":               ["planid"],
    "encounter_date":        ["encounterdate", "admitdate", "admitdt", "servicedate", "visitdate", "visitdt"],
    "appointment_date":      ["appointmentdate", "apptdate", "apptdt"],
    "slot_date":             ["slotdate", "slotdt", "blockdate"],
    "service_month":         ["servicemonth", "svcdt", "servicedate", "svcfromdt", "servicefromdate"],
    "coverage_month":        ["coveragemonth", "covmonth", "eligmonth"],
    "period_month":          ["periodmonth", "perioddt", "measureperiod"],
    "los_days":              ["losdays", "los", "lengthofstay", "lengthofstaydays"],
    "procedure_count":       ["procedurecount", "proccnt", "numprocedures"],
    "billed_amount":         ["billedamount", "billed", "charge", "chrg", "totalcharge", "clmtotalchrgamt"],
    "allowed_amount":        ["allowedamount", "allowed", "clmallowedamt"],
    "paid_amount":           ["paidamount", "paid", "clmpaidamt"],
    "patient_responsibility": ["patientresponsibility", "patresp", "clmpatrespamt", "memberliability"],
    "incurred_amount":       ["incurredamount", "incurred"],
    "member_months":         ["membermonths", "mm"],
    "earned_premium":        ["earnedpremium", "premium", "prempmpm", "premamt"],
    "incurred_claims":       ["incurredclaims", "incurredamt"],
    "paid_claims":           ["paidclaims"],
    "allowed_claims":        ["allowedclaims"],
    "measure_id":            ["measureid", "hedismeasure", "hedisid"],
    "birth_date":            ["birthdate", "dob"],
    "specialty":             ["specialty"],
    "department":            ["department", "dept"],
    "region":                ["region"],
    "revenue_code":          ["revenuecode", "revcode", "revcd"],
    "procedure_code":        ["procedurecode", "hcpcs", "cptcode", "cpt"],
    "service_units":         ["serviceunits", "units", "svcunitcnt"],
    # enum / code columns
    "encounter_class":       ["encounterclass", "enctype", "encclass", "encountertype", "patientclass", "patclass"],
    "claim_status":          ["claimstatus", "adjstatus", "adjstatuscd", "clpstatus", "clp02statuscd", "claimstatuscd", "statuscd", "status"],
    "appointment_status":    ["appointmentstatus", "apptstatus", "apptstatuscd", "disposition", "visitstatus", "status"],
    "slot_status":           ["slotstatus", "blockstatus", "slotstate", "blockstate", "status"],
    "gap_status":            ["gapstatus", "gapstate", "status"],
}

DATE_FIELDS = {"service_month", "coverage_month", "period_month"}  # need date_trunc to month


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def load_yaml(p: Path) -> dict:
    import yaml
    return yaml.safe_load(p.read_text()) or {}


# ── column acquisition ───────────────────────────────────────────────────────
def columns_offline(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text())


def columns_live(catalog: str, schema: str, warehouse_id: str, profile: str | None) -> list[dict]:
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()

    def run(sql: str) -> list[list]:
        r = w.statement_execution.execute_statement(warehouse_id=warehouse_id, statement=sql, wait_timeout="50s")
        return [list(row) for row in (r.result.data_array or [])] if r.result else []

    cols = [{"table_name": t, "column_name": c, "data_type": d} for t, c, d in run(
        f"SELECT table_name, column_name, data_type FROM {catalog}.information_schema.columns "
        f"WHERE table_schema = '{schema}' ORDER BY table_name, ordinal_position")]
    # sample string columns that look like codes/statuses
    for col in cols:
        name, dt = norm(col["column_name"]), (col["data_type"] or "").lower()
        if "string" in dt and any(k in name for k in ("status", "state", "class", "type", "code", "cd", "disposition")):
            vals = run(f"SELECT `{col['column_name']}` FROM {catalog}.{schema}.`{col['table_name']}` "
                       f"WHERE `{col['column_name']}` IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 25")
            col["sample_values"] = [v[0] for v in vals]
    return cols


# ── matching ───────────────────────────────────────────────────────────────
def match_entity(table: str) -> str | None:
    n = norm(table)
    best, best_len = None, 0
    for ent, syns in ENTITY_SYNS.items():
        for s in syns:
            if s in n and len(s) > best_len:
                best, best_len = ent, len(s)
    return best


def match_field(field: str, table_cols: list[dict]) -> str | None:
    """Return the physical column name matching canonical `field`, or None."""
    syns = set(FIELD_SYNS.get(field, [])) | {norm(field)}
    # exact-ish first
    for c in table_cols:
        if norm(c["column_name"]) in syns:
            return c["column_name"]
    # contains fallback
    for c in table_cols:
        cn = norm(c["column_name"])
        if any(s in cn or cn in s for s in syns):
            return c["column_name"]
    return None


def draft_mapping(catalog: str, schema: str, cols: list[dict], canon: dict, warehouse_id: str | None) -> str:
    entities = canon.get("entities", {})
    by_table: dict[str, list[dict]] = {}
    for c in cols:
        by_table.setdefault(c["table_name"], []).append(c)

    # best table per canonical entity
    ent_table: dict[str, str] = {}
    for table in by_table:
        ent = match_entity(table)
        if ent and ent not in ent_table:  # first match wins; REVIEW covers ambiguity
            ent_table[ent] = table

    L = ['name: {}_draft'.format(norm(schema) or "source"),
         'description: "AUTO-PROFILED DRAFT — confirm every # REVIEW before generating"',
         '',
         'target:',
         f'  catalog:      {catalog}',
         f'  schema:       {schema}       # REVIEW: output schema is usually a curated schema, not the source',
         f'  warehouse_id: {warehouse_id or "REVIEW_set_warehouse_id"}   # REVIEW',
         '',
         'entities:']

    matched_entities = 0
    for ent, spec in entities.items():
        table = ent_table.get(ent)
        if not table:
            continue
        matched_entities += 1
        tcols = by_table[table]
        fields = spec.get("fields", {})
        L += ['', f'  {ent}:', f'    source: {catalog}.{schema}.{table}']
        # grain
        gk = spec.get("grain_keys", [])
        gk_phys = [match_field(k, tcols) or f"REVIEW_{k}" for k in gk]
        L.append(f'    grain_keys: [{", ".join(gk_phys)}]   # REVIEW: confirm grain')
        # fields (non-enum, role != enum-only)
        enum_fields = {f for f, fd in fields.items() if isinstance(fd, dict) and fd.get("enum")}
        L.append('    fields:')
        for f, fd in fields.items():
            if f in enum_fields:
                continue
            phys = match_field(f, tcols)
            required = isinstance(fd, dict) and fd.get("required")
            if phys and f in DATE_FIELDS:
                L.append(f"      {f}: \"date_trunc('month', {phys})\"")
            elif phys:
                L.append(f'      {f}: {phys}')
            elif required:
                L.append(f'      {f}:   # REVIEW: unmapped (REQUIRED — entity blocked until set)')
            else:
                L.append(f'      {f}:   # REVIEW: unmapped (optional — drops dependent measures)')
        # enums
        if enum_fields:
            L.append('    enums:')
            for f in enum_fields:
                phys = match_field(f, tcols)
                col_obj = next((c for c in tcols if c["column_name"] == phys), None)
                samples = (col_obj or {}).get("sample_values") if col_obj else None
                allowed = fields[f].get("enum", [])
                L.append(f'      {f}:')
                L.append(f'        source_column: {phys or "REVIEW_column"}   # REVIEW: confirm')
                if samples:
                    L.append('        map:   # REVIEW: map each sampled value -> canonical')
                    for v in samples:
                        L.append(f'          "{v}":   # REVIEW  (canonical one of: {", ".join(allowed)})')
                else:
                    L.append(f'        map: {{}}   # REVIEW: sample values and map -> one of: {", ".join(allowed)}')
                L.append('        default: other')

    L += ['', f'# profiled {len(by_table)} tables -> matched {matched_entities} canonical entities.',
          '# Unmatched canonical entities were omitted (their metric views will not generate).']
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Profile a source schema and draft a mapping.")
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--warehouse-id")
    ap.add_argument("--profile", help="Databricks CLI profile for live mode")
    ap.add_argument("--schema-json", help="offline: JSON dump of columns instead of a live query")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    if args.schema_json:
        cols = columns_offline(Path(args.schema_json))
    else:
        if not args.warehouse_id:
            ap.error("live mode needs --warehouse-id (or pass --schema-json for offline)")
        cols = columns_live(args.catalog, args.schema, args.warehouse_id, args.profile)

    canon = load_yaml(REF / "canonical_model.yaml")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.schema}_profile.json").write_text(json.dumps(cols, indent=2))
    draft = draft_mapping(args.catalog, args.schema, cols, canon, args.warehouse_id)
    draft_path = out / f"{args.schema}_mapping.draft.yaml"
    draft_path.write_text(draft)

    n_review = draft.count("# REVIEW")
    print(f"profiled {len({c['table_name'] for c in cols})} tables, {len(cols)} columns")
    print(f"wrote {draft_path}  ({n_review} # REVIEW flags to confirm)")
    print("next: confirm the # REVIEW items, then run generate_semantic_layer.py --mapping " + str(draft_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
