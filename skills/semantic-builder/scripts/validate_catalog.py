#!/usr/bin/env python3
"""
validate_catalog.py — correctness gate for the HLS measure catalog.

Loads the canonical entity model and every domain measure file, then enforces the
rules that keep the catalog trustworthy across customers:

  ERRORS (exit 1)
    - measure missing a required key
    - unknown measure type
    - metric_view name violates  mv_<domain>__<name>  and matching domain prefix
    - atomic measure's entity is not declared in the canonical model
    - composite measure whose expr contains no MEASURE(...)         (non-additive trap)
    - MEASURE(x) referencing a measure that is not defined anywhere
    - MEASURE(x) in expr not listed in depends_on (or vice-versa)
    - composite referencing a measure that lives in a different metric_view
    - >1 source grain in a metric view (two atomics with different entities)
    - a declared metric_view whose entity is not in the canonical model

  WARNINGS (exit 0)
    - atomic expr references an identifier that is not a known field of its entity
    - measure missing a human definition

Usage:  python3 scripts/validate_catalog.py [--strict]
        --strict  treat warnings as errors (exit 1)
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
CATALOG_REF = ROOT / "references"
CANONICAL = CATALOG_REF / "canonical_model.yaml"
CATALOG_DIR = CATALOG_REF / "measure_catalog"

REQUIRED_KEYS = {"name", "type", "metric_view", "expr", "definition"}
MV_RE = re.compile(r"^mv_([a-z0-9_]+?)__[a-z0-9_]+$")
MEASURE_RE = re.compile(r"MEASURE\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
QUOTED_RE = re.compile(r"'[^']*'")

# SQL keywords / functions that may appear in an atomic expr and are NOT fields.
SQL_STOP = {
    "count", "distinct", "case", "when", "then", "else", "end", "sum", "avg",
    "min", "max", "and", "or", "not", "null", "cast", "as", "coalesce", "is",
    "in", "true", "false", "measure", "nullif", "abs", "round", "date_trunc",
    "datediff", "greatest", "least", "if", "between", "like", "on",
}


def load_yaml(p: Path):
    with open(p) as fh:
        return yaml.safe_load(fh)


def main() -> int:
    strict = "--strict" in sys.argv
    errors: list[str] = []
    warnings: list[str] = []

    if not CANONICAL.exists():
        sys.exit(f"canonical model not found: {CANONICAL}")
    canon = load_yaml(CANONICAL)
    entities = canon.get("entities", {})
    entity_fields = {e: set((d.get("fields") or {}).keys()) for e, d in entities.items()}

    # ── load all measures across domains (names are scoped PER metric view) ───
    measures: dict[tuple[str, str], dict] = {}   # (metric_view, name) -> record (+ _domain,_file)
    by_mv: dict[str, dict[str, dict]] = {}        # metric_view -> {name: record}
    mv_entities: dict[str, set] = {}              # metric_view -> set of entities (atomics)
    mv_declared: dict[str, str] = {}              # metric_view -> declared entity

    files = sorted(CATALOG_DIR.glob("*.yaml"))
    if not files:
        sys.exit(f"no domain files in {CATALOG_DIR}")

    for f in files:
        doc = load_yaml(f) or {}
        domain = doc.get("domain") or f.stem
        for mv in doc.get("metric_views", []) or []:
            mv_declared[mv["name"]] = mv.get("entity", "")
            if mv.get("entity") and mv["entity"] not in entities:
                errors.append(f"[{f.name}] metric_view {mv['name']} declares unknown entity '{mv['entity']}'")
        for m in doc.get("measures", []) or []:
            m = dict(m)
            m["_domain"] = domain
            m["_file"] = f.name
            name = m.get("name", "<unnamed>")
            mv = m.get("metric_view", "<none>")
            if (mv, name) in measures:
                errors.append(f"[{f.name}] duplicate measure '{name}' in metric_view '{mv}'")
            measures[(mv, name)] = m
            by_mv.setdefault(mv, {})[name] = m

    # ── per-measure checks ───────────────────────────────────────────────────
    for (_mv_key, name), m in measures.items():
        f = m["_file"]
        missing = REQUIRED_KEYS - m.keys()
        if missing:
            errors.append(f"[{f}] measure '{name}' missing keys: {sorted(missing)}")
            continue
        if not m.get("definition"):
            warnings.append(f"[{f}] measure '{name}' has empty definition")

        mtype = m["type"]
        if mtype not in ("atomic", "composite"):
            errors.append(f"[{f}] measure '{name}' has unknown type '{mtype}'")
            continue

        # naming convention + domain prefix match
        mv = m["metric_view"]
        mo = MV_RE.match(mv)
        if not mo:
            errors.append(f"[{f}] measure '{name}': metric_view '{mv}' violates mv_<domain>__<name>")
        elif mo.group(1) != m["_domain"]:
            errors.append(f"[{f}] measure '{name}': metric_view domain '{mo.group(1)}' != file domain '{m['_domain']}'")

        expr = m["expr"]

        if mtype == "atomic":
            ent = m.get("entity")
            if not ent:
                errors.append(f"[{f}] atomic '{name}' missing 'entity'")
            elif ent not in entities:
                errors.append(f"[{f}] atomic '{name}' entity '{ent}' not in canonical model")
            else:
                mv_entities.setdefault(mv, set()).add(ent)
                # field reference check (best-effort; warns only)
                bare = QUOTED_RE.sub(" ", expr)
                for tok in IDENT_RE.findall(bare):
                    low = tok.lower()
                    if low in SQL_STOP:
                        continue
                    if tok not in entity_fields.get(ent, set()):
                        warnings.append(
                            f"[{f}] atomic '{name}' references '{tok}' not a field of entity '{ent}'"
                        )
            if "MEASURE(" in expr:
                errors.append(f"[{f}] atomic '{name}' must not use MEASURE(); it aggregates source rows directly")

        else:  # composite
            refs = MEASURE_RE.findall(expr)
            if not refs:
                errors.append(
                    f"[{f}] composite '{name}' has no MEASURE(...) — composites must be ratio-of-measures, "
                    f"never a bare aggregate (non-additive trap)"
                )
            declared = set(m.get("depends_on") or [])
            local = by_mv.get(mv, {})               # measures resolve WITHIN the same metric view
            for r in refs:
                if r not in local:
                    errors.append(
                        f"[{f}] composite '{name}' uses MEASURE({r}) but '{r}' is not a measure in "
                        f"metric_view '{mv}' (a composite can only reference measures in its own view)"
                    )
                if r not in declared:
                    errors.append(f"[{f}] composite '{name}' uses MEASURE({r}) but '{r}' not in depends_on")
            for d in declared:
                if d not in refs:
                    warnings.append(f"[{f}] composite '{name}' lists depends_on '{d}' not used in expr")

    # ── one grain per metric view ────────────────────────────────────────────
    for mv, ents in mv_entities.items():
        if len(ents) > 1:
            errors.append(
                f"metric_view '{mv}' mixes multiple source grains {sorted(ents)} — a metric view binds to "
                f"ONE entity/grain. Pre-conform to a single grain in a gold view instead."
            )
        declared = mv_declared.get(mv)
        if declared and declared not in ents:
            errors.append(
                f"metric_view '{mv}' declares entity '{declared}' but its atomics aggregate {sorted(ents)}"
            )

    # ── report ───────────────────────────────────────────────────────────────
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    n_measures = len(measures)
    n_mvs = len(mv_declared)
    print(f"\nchecked {n_measures} measures across {n_mvs} metric views in {len(files)} domain files")
    print(f"  {len(errors)} error(s), {len(warnings)} warning(s)")

    if errors or (strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
