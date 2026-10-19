"""Vetted entrypoint for the presentation skill — EXECUTION model.

Genie Code should CALL build_deck() with a validated deck spec, not hand-write 400+ lines
of slide HTML. The baseline failure this prevents: an un-guided agent re-implements the
deck shell every time (brittle navigation, broken PDF export, off-brand styling, and —
worst for HLS — raw numbers typed into slides that do not match the data). This path:
  - renders slides onto the FROZEN deck framework (deck_framework.py) so navigation,
    scaling, and "Save as PDF" always work and every deck looks like one system,
  - uses only the vetted layout vocabulary (layouts.py), HTML-escaping all content,
  - assembles a SINGLE self-contained .html file (optional webfont, otherwise no network),
  - keeps speaker notes in BOTH the per-slide <aside> and a machine-readable JSON block,
  - validates the spec and FAILS LOUD on an unknown layout or empty deck.

Grounding is a SEPARATE, upstream step: pull real figures from the artifact with ground.py,
put those numbers into the spec, THEN build. This module never invents a figure — it only
renders what the spec contains. PHI handling is also upstream and delegated: de-identify the
source with the phi-deidentifier skill (or confirm with the user) before grounding — see
SKILL.md.

Deck spec shape (dict, or a path to a JSON file):
    {
      "title": "Deck title",            # <title> + default used nowhere else
      "footer_left": "Databricks · HLS",# default footer-left for every slide
      "accent": "#ff3621",              # optional brand accent override
      "slides": [ {<slide spec>}, ... ] # see layouts.render_slide / layouts.RENDERERS
    }
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deck_framework import FONT_LINK, FRAMEWORK_CSS, NAV_JS, NAV_MARKUP  # noqa: E402
import layouts  # noqa: E402


def _load_spec(spec):
    if isinstance(spec, str):
        with open(spec, "r", encoding="utf-8") as f:
            return json.load(f)
    if not isinstance(spec, dict):
        raise TypeError("spec must be a dict or a path to a JSON file")
    return spec


def _validate(spec) -> list:
    slides = spec.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("deck spec must have a non-empty 'slides' list")
    for i, s in enumerate(slides):
        if not isinstance(s, dict):
            raise ValueError(f"slide {i + 1} must be an object/dict")
        if s.get("type") not in layouts.RENDERERS:
            raise ValueError(
                f"slide {i + 1}: unknown type {s.get('type')!r}. "
                f"Valid: {', '.join(sorted(layouts.RENDERERS))}"
            )
    return slides


def render_html(spec) -> str:
    """Render a deck spec to a complete self-contained HTML document string (no file I/O)."""
    spec = _load_spec(spec)
    slides = _validate(spec)
    title = spec.get("title", "Presentation")
    footer_left_default = spec.get("footer_left", "")
    accent = spec.get("accent")

    # Per-slide defaults: inherit footer_left, auto page number.
    rendered, notes = [], []
    for i, s in enumerate(slides):
        s = {**s}
        s.setdefault("footer_left", footer_left_default)
        s.setdefault("page", i + 1)
        rendered.append(layouts.render_slide(s, i, len(slides)))
        notes.append(s.get("notes") or "")

    accent_override = (
        f"\n  <style>:root {{ --accent: {_safe_color(accent)}; }}</style>" if accent else ""
    )
    notes_json = json.dumps(notes, ensure_ascii=False, indent=2)

    return (
        "<!doctype html>\n"
        '<html lang="en" data-od-deck-protocol="1"><head>\n'
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{_escape(title)}</title>\n"
        f"{FONT_LINK}\n"
        f"  <style>\n{FRAMEWORK_CSS}\n  </style>\n"
        f"  <style>\n{layouts.COMPONENT_CSS}\n  </style>"
        f"{accent_override}\n"
        "</head>\n<body>\n"
        '  <div class="deck-shell">\n'
        '    <div class="deck-stage" id="deck-stage">\n'
        + "\n".join(rendered)
        + "\n    </div>\n  </div>\n"
        f"{NAV_MARKUP}\n"
        f"  <script>\n{NAV_JS}\n  </script>\n"
        f'<script type="application/json" id="speaker-notes">\n{notes_json}\n</script>\n'
        "</body></html>\n"
    )


def build_deck(spec, out_path: str) -> dict:
    """Render a deck spec and write a self-contained .html file.

    Returns a summary dict: {path, slides, bytes, titles}. Raises on an invalid spec so a
    broken deck is never written silently.
    """
    html_doc = render_html(spec)
    out_path = os.path.abspath(os.path.expanduser(out_path))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    spec = _load_spec(spec)
    titles = [s.get("title") or s.get("statement") or s.get("type") for s in spec["slides"]]
    return {
        "path": out_path,
        "slides": len(spec["slides"]),
        "bytes": len(html_doc.encode("utf-8")),
        "titles": titles,
    }


def _escape(s: str) -> str:
    import html
    return html.escape(str(s))


def _safe_color(c) -> str:
    """Allow only a #hex color as an accent override (prevents CSS/markup injection)."""
    import re
    c = str(c).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{3,8}", c):
        raise ValueError(f"accent must be a #hex color, got {c!r}")
    return c


if __name__ == "__main__":
    # Minimal smoke: build a 2-slide deck to a temp file.
    import tempfile
    demo = {
        "title": "Smoke deck",
        "footer_left": "Databricks · HLS",
        "slides": [
            {"type": "cover", "kicker": "Demo", "title": "Hello [[deck]]",
             "subtitle": "A tiny self-contained deck.", "theme": "dark"},
            {"type": "statement", "eyebrow": "Thesis", "statement": "It **works**."},
        ],
    }
    out = os.path.join(tempfile.gettempdir(), "smoke_deck.html")
    print(build_deck(demo, out))
