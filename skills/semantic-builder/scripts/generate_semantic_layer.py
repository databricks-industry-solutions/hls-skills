#!/usr/bin/env python3
"""
generate_semantic_layer.py — mapping + measure catalog -> deployable SQL.

Reads the canonical model + measure catalog (from the plugin) and a per-customer
source-mapping file, then emits:
    <out>/01_silver.sql        one conforming view per mapped entity
    <out>/03_metric_views.sql  one metric view per in-scope mv_<domain>__<name>
    <out>/plan.md              the justify report (what was built, what was skipped, why)

Scope is inferred: a metric view is generated only if its entity is mapped, and a
measure is emitted only if every canonical field / dependency it needs is available.
Everything else is skipped and recorded in plan.md.

Usage:
  python3 scripts/generate_semantic_layer.py --mapping <mapping.yaml> [--out <dir>] [--plugin <root>]
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
QUOTED_RE = re.compile(r"'[^']*'")
MEASURE_RE = re.compile(r"MEASURE\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")


def load(p: Path):
    with open(p) as fh:
        return yaml.safe_load(fh)


def mask_quotes(expr: str):
    """Replace 'literals' with placeholders so identifiers inside them aren't touched."""
    lits: list[str] = []

    def repl(m):
        lits.append(m.group(0))
        return f"\x00{len(lits)-1}\x00"

    return QUOTED_RE.sub(repl, expr), lits


def unmask(expr: str, lits: list[str]):
    for i, lit in enumerate(lits):
        expr = expr.replace(f"\x00{i}\x00", lit)
    return expr


def prefix_source(expr: str, fields: set[str]) -> str:
    """Prefix canonical field references with `source.` (Databricks metric-view style)."""
    masked, lits = mask_quotes(expr)
    for f in sorted(fields, key=len, reverse=True):
        masked = re.sub(rf"\b{re.escape(f)}\b", f"source.{f}", masked)
    return unmask(masked, lits)


def referenced_fields(expr: str, entity_fields: set[str]) -> set[str]:
    masked, _ = mask_quotes(expr)
    toks = set(IDENT_RE.findall(masked))
    return toks & entity_fields


def build_silver(entity: str, emap: dict, target: str) -> str:
    """One conforming view: physical -> canonical field names, joins, enum CASE, filter."""
    src = emap["source"]
    select_lines: list[str] = []
    for canon, expr in (emap.get("fields") or {}).items():
        select_lines.append(f"  {expr} AS {canon}")
    for canon, spec in (emap.get("enums") or {}).items():
        col = spec["source_column"]
        whens = "\n".join(
            f"       WHEN {col} = '{k}' THEN '{v}'" for k, v in (spec.get("map") or {}).items()
        )
        default = spec.get("default", "other")
        select_lines.append(f"  CASE\n{whens}\n       ELSE '{default}' END AS {canon}")
    body = ",\n".join(select_lines)
    sql = f"CREATE OR REPLACE VIEW {target}.{entity} AS\nSELECT\n{body}\nFROM {src}"
    for j in emap.get("joins") or []:
        sql += f"\n{j.get('type','left').upper()} JOIN {j['table']} ON {j['on']}"
    if emap.get("filter"):
        sql += f"\nWHERE {emap['filter']}"
    return sql + ";"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--out", default="generated")
    ap.add_argument("--plugin", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args()

    plugin = Path(args.plugin)
    ref = plugin / "references"
    canon = load(ref / "canonical_model.yaml")
    entities = canon.get("entities", {})
    entity_all_fields = {e: set((d.get("fields") or {}).keys()) for e, d in entities.items()}
    entity_dims = {
        e: [f for f, fd in (d.get("fields") or {}).items() if fd.get("role") in ("dimension", "date")]
        for e, d in entities.items()
    }

    # catalog: metric_view -> {entity, grain, measures[]}
    mvs: dict[str, dict] = {}
    for f in sorted((ref / "measure_catalog").glob("*.yaml")):
        doc = load(f) or {}
        for mv in doc.get("metric_views", []) or []:
            mvs.setdefault(mv["name"], {"entity": mv.get("entity"), "grain": mv.get("grain"),
                                        "domain": doc.get("domain"), "measures": []})
        for m in doc.get("measures", []) or []:
            mvs.setdefault(m["metric_view"], {"measures": []})["measures"].append(m)

    mapping = load(Path(args.mapping))
    target_cfg = mapping.get("target", {})
    target = f"{target_cfg['catalog']}.{target_cfg['schema']}"
    mapped = mapping.get("entities", {})

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ── 01 silver ────────────────────────────────────────────────────────────
    silver_parts = [f"-- 01_silver.sql — conforming views in {target}",
                    f"USE CATALOG {target_cfg['catalog']};", f"USE SCHEMA {target_cfg['schema']};", ""]
    avail: dict[str, set] = {}
    for entity, emap in mapped.items():
        if entity not in entities:
            print(f"WARN mapping entity '{entity}' not in canonical model — skipped")
            continue
        avail[entity] = set((emap.get("fields") or {}).keys()) | set((emap.get("enums") or {}).keys())
        silver_parts.append(build_silver(entity, emap, target))
        silver_parts.append("")
    (out / "01_silver.sql").write_text("\n".join(silver_parts))

    # ── 03 metric views (scope inference + measure skipping) ──────────────────
    mv_parts = [f"-- 03_metric_views.sql — metric views in {target}",
                f"USE CATALOG {target_cfg['catalog']};", f"USE SCHEMA {target_cfg['schema']};", ""]
    plan: list[str] = ["# Generation plan", "",
                       f"Target: `{target}`  ·  warehouse: `{target_cfg.get('warehouse_id','?')}`", ""]

    built_mvs = 0
    for mv_name, mv in sorted(mvs.items()):
        entity = mv.get("entity")
        if entity not in avail:
            plan.append(f"- ⏭️  **{mv_name}** — SKIPPED (entity `{entity}` not mapped)")
            continue
        efields = entity_all_fields.get(entity, set())
        have = avail[entity]
        survived: set[str] = set()
        emitted: list[dict] = []
        skipped_measures: list[str] = []

        # atomics first
        for m in mv["measures"]:
            if m["type"] != "atomic":
                continue
            need = referenced_fields(m["expr"], efields)
            missing = need - have
            if missing:
                skipped_measures.append(f"{m['name']} (missing {sorted(missing)})")
                continue
            survived.add(m["name"])
            emitted.append(m)

        # composites: iterate to resolve dependency chains
        comps = [m for m in mv["measures"] if m["type"] == "composite"]
        changed = True
        while changed:
            changed = False
            for m in comps:
                if m["name"] in survived or m["name"] in [s.split()[0] for s in skipped_measures]:
                    continue
                deps = set(m.get("depends_on") or [])
                if deps <= survived:
                    survived.add(m["name"]); emitted.append(m); changed = True
        for m in comps:
            if m["name"] not in survived:
                deps = set(m.get("depends_on") or [])
                skipped_measures.append(f"{m['name']} (needs {sorted(deps - survived)})")

        if not emitted:
            plan.append(f"- ⏭️  **{mv_name}** — SKIPPED (no measures survived; missing fields)")
            continue

        # emit metric view YAML
        dims = [d for d in entity_dims.get(entity, []) if d in have]
        lines = [f"CREATE OR REPLACE VIEW {target}.{mv_name}", "  WITH METRICS LANGUAGE YAML AS", "$$",
                 "version: 0.1", f"source: {target}.{entity}", "", "dimensions:"]
        for d in dims:
            lines.append(f"  - name: {d}")
            lines.append(f"    expr: source.{d}")
        lines.append("")
        lines.append("measures:")
        for m in emitted:
            if m["type"] == "atomic":
                expr = prefix_source(m["expr"], efields)
            else:
                expr = m["expr"]  # MEASURE(...) references stay as-is
            lines.append(f"  - name: {m['name']}")
            lines.append(f"    expr: {expr}")
        lines.append("$$;")
        mv_parts.append("\n".join(lines)); mv_parts.append("")
        built_mvs += 1

        plan.append(f"- ✅ **{mv_name}** (`{entity}`) — {len(emitted)} measures"
                    + (f"; skipped: {skipped_measures}" if skipped_measures else ""))

    (out / "03_metric_views.sql").write_text("\n".join(mv_parts))
    plan.append("")
    plan.append(f"**{built_mvs} metric views built**, sourcing from {len(avail)} conformed entities.")
    (out / "plan.md").write_text("\n".join(plan))

    print(f"wrote {out}/01_silver.sql, {out}/03_metric_views.sql, {out}/plan.md")
    print(f"  entities conformed: {sorted(avail)}")
    print(f"  metric views built: {built_mvs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
