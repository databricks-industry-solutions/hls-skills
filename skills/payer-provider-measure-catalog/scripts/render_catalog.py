#!/usr/bin/env python3
"""
render_catalog.py — render the human-readable catalog.md from the YAML source of truth.

Reads canonical_model.yaml + measure_catalog/*.yaml and writes references/catalog.md.
Run after any catalog edit (and in CI) so the Markdown view never drifts from the YAML.

Usage:  python3 scripts/render_catalog.py
"""
from __future__ import annotations
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "references"
CANONICAL = REF / "canonical_model.yaml"
CATALOG_DIR = REF / "measure_catalog"
OUT = REF / "catalog.md"


def load(p: Path):
    with open(p) as fh:
        return yaml.safe_load(fh)


def main() -> int:
    canon = load(CANONICAL)
    files = sorted(CATALOG_DIR.glob("*.yaml"))

    lines: list[str] = []
    lines.append("# HLS Measure Catalog")
    lines.append("")
    lines.append("_Generated from YAML by `scripts/render_catalog.py` — do not edit by hand._")
    lines.append("")

    # summary
    total = 0
    lines.append("## Domains")
    lines.append("")
    lines.append("| Domain | Lens | Metric views | Measures |")
    lines.append("|---|---|---|---|")
    docs = [(f, load(f) or {}) for f in files]
    for f, doc in docs:
        ms = doc.get("measures", []) or []
        total += len(ms)
        mvs = ", ".join(mv["name"] for mv in doc.get("metric_views", []) or [])
        lines.append(f"| {doc.get('domain', f.stem)} | {doc.get('lens','')} | {mvs} | {len(ms)} |")
    lines.append(f"\n**{total} measures** across all domains.\n")

    # per domain
    for f, doc in docs:
        lines.append(f"## {doc.get('domain', f.stem)}  (lens: {doc.get('lens','')})")
        lines.append("")
        by_mv: dict[str, list] = {}
        for m in doc.get("measures", []) or []:
            by_mv.setdefault(m["metric_view"], []).append(m)
        for mv, ms in by_mv.items():
            grain = next((v.get("grain") for v in doc.get("metric_views", []) if v["name"] == mv), "")
            lines.append(f"### `{mv}`  — grain: {grain}")
            lines.append("")
            lines.append("| Measure | Type | Expression | Definition |")
            lines.append("|---|---|---|---|")
            for m in sorted(ms, key=lambda x: (x["type"] != "atomic", x["name"])):
                expr = m["expr"].replace("|", "\\|")
                defn = (m.get("definition", "") or "").replace("|", "\\|")
                lines.append(f"| `{m['name']}` | {m['type']} | `{expr}` | {defn} |")
            lines.append("")
            # anti-patterns callouts
            aps = [m for m in ms if m.get("anti_pattern")]
            if aps:
                lines.append("**Anti-patterns:**")
                for m in aps:
                    lines.append(f"- `{m['name']}` — {m['anti_pattern']}")
                lines.append("")

    # canonical entities appendix
    lines.append("## Canonical entities")
    lines.append("")
    lines.append("| Entity | Grain | Lens |")
    lines.append("|---|---|---|")
    for e, d in (canon.get("entities") or {}).items():
        grain = (d.get("grain", "") or "").split("\n")[0]
        lines.append(f"| `{e}` | {grain} | {d.get('lens','')} |")
    lines.append("")

    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT}  ({total} measures, {len(files)} domains)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
