"""Unit tests for the presentation builder — pure, offline, sub-second (no warehouse).

Covers the invariants that make a generated deck trustworthy:
  1. The FROZEN framework is emitted verbatim (nav runtime, protocol marker, print CSS),
     so navigation and "Save as PDF" always work.
  2. The layout renderers are deterministic and SAFE: all content is HTML-escaped, the tiny
     inline markup resolves, bars auto-scale, and an unknown layout fails loud.
  3. The grounding reader shapes figures as the renderers expect (ground.py — the pure part).

PHI handling is NOT the presentation builder's job (it is delegated to phi-deidentifier), so
there is nothing PHI-related to test here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import build_deck as bd  # noqa: E402
import deck_framework as fw  # noqa: E402
import ground as g  # noqa: E402
import layouts as L  # noqa: E402


# --- framework is emitted verbatim -------------------------------------------

def _mini():
    return {
        "title": "T", "footer_left": "F",
        "slides": [
            {"type": "cover", "title": "Hello", "theme": "dark"},
            {"type": "statement", "statement": "Thesis."},
        ],
    }


def test_doc_is_self_contained_and_well_formed():
    html = bd.render_html(_mini())
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert 'data-od-deck-protocol="1"' in html
    # frozen framework strings present verbatim
    assert fw.NAV_JS.strip() in html
    assert fw.NAV_MARKUP.strip() in html
    assert "od:deck-ready" in html and "OD_DECK_PROTOCOL_VERSION = 1" in html
    assert "@media print" in html  # Save-as-PDF path
    assert ".deck-stage" in html and "1920px" in html


def test_navigation_chrome_is_visible():
    # Standalone decks must surface the prev/counter/next pill + keyboard hint (the frozen
    # framework hides them for host-embedded use; the editable layer re-shows them).
    html = bd.render_html(_mini())
    assert ".deck-counter { display: flex; }" in html
    assert ".deck-hint { display: block; }" in html
    assert 'id="deck-prev"' in html and 'id="deck-next"' in html


def test_one_section_per_slide():
    html = bd.render_html(_mini())
    # data-screen-label only appears on real slides (not in the framework comment).
    assert html.count("data-screen-label=") == 2


def test_speaker_notes_in_aside_and_json():
    spec = _mini()
    spec["slides"][0]["notes"] = "Say this out loud."
    html = bd.render_html(spec)
    assert '<aside class="speaker-notes">Say this out loud.</aside>' in html
    notes_json = html.split('id="speaker-notes">', 1)[1].split("</script>", 1)[0]
    assert json.loads(notes_json) == ["Say this out loud.", ""]


# --- renderers are safe + deterministic --------------------------------------

def test_content_is_html_escaped():
    html = bd.render_html({"slides": [
        {"type": "statement", "statement": "<script>alert(1)</script> & \"x\""}]})
    assert "<script>alert(1)" not in html.split('id="speaker-notes"')[0]
    assert "&lt;script&gt;alert(1)" in html


def test_inline_markup():
    assert L._inline("a [[b]] c") == 'a <span class="hl">b</span> c'
    assert L._inline("a **b** c") == "a <strong>b</strong> c"
    assert L._inline("<x>") == "&lt;x&gt;"


def test_bar_chart_autoscales_first_bar_accent():
    html = bd.render_html({"slides": [{"type": "bar_chart", "title": "t", "chart": {
        "heading": "h", "bars": [{"label": "a", "value": 200}, {"label": "b", "value": 50}]}}]})
    assert "width:100.0%" in html   # max value -> full width
    assert "width:25.0%" in html    # 50/200
    assert "200" in html and "50" in html


def test_cards_grid_class_clamped():
    html = bd.render_html({"slides": [{"type": "cards", "title": "t", "cards": [
        {"heading": "a"}, {"heading": "b"}, {"heading": "c", "featured": True}]}]})
    assert 'class="cards n3"' in html
    assert "card featured" in html


def test_unknown_layout_fails_loud():
    with pytest.raises(ValueError):
        bd.render_html({"slides": [{"type": "pie_of_pie"}]})


def test_empty_deck_fails_loud():
    with pytest.raises(ValueError):
        bd.render_html({"slides": []})


def test_bad_theme_fails_loud():
    with pytest.raises(ValueError):
        bd.render_html({"slides": [{"type": "statement", "statement": "x", "theme": "neon"}]})


def test_accent_override_rejects_injection():
    with pytest.raises(ValueError):
        bd.render_html({"accent": "red; } body{display:none", "slides": [
            {"type": "statement", "statement": "x"}]})
    ok = bd.render_html({"accent": "#00a972", "slides": [{"type": "statement", "statement": "x"}]})
    assert "--accent: #00a972" in ok


def test_build_deck_writes_file(tmp_path):
    out = tmp_path / "deck.html"
    summ = bd.build_deck(_mini(), str(out))
    assert out.exists() and summ["slides"] == 2 and summ["bytes"] > 1000


# --- grounding reader shapes figures for the renderers (pure part of ground.py) ---

def test_column_distribution_shapes_bars():
    class DistQ:
        def __call__(self, stmt):
            return [["A", 100], ["B", 30], ["C", 3], ["D", 1]]
    out = g.column_distribution("c.s.t", "region", q=DistQ())
    assert [b["label"] for b in out["bars"]] == ["A", "B", "C", "D"]
    assert [b["value"] for b in out["bars"]] == [100, 30, 3, 1]
    assert out["source"].startswith("Source: c.s.t")


def test_column_distribution_labels_null():
    class DistQ:
        def __call__(self, stmt):
            return [[None, 5]]
    out = g.column_distribution("c.s.t", "region", q=DistQ())
    assert out["bars"] == [{"label": "(null)", "value": 5}]
