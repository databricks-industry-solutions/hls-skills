"""Unit tests for the presentation builder — pure, offline, sub-second (no warehouse).

Covers the three invariants that make a generated deck trustworthy:
  1. The FROZEN framework is emitted verbatim (nav runtime, protocol marker, print CSS),
     so navigation and "Save as PDF" always work.
  2. The layout renderers are deterministic and SAFE: all content is HTML-escaped, the tiny
     inline markup resolves, bars auto-scale, and an unknown layout fails loud.
  3. The PHI classifier flags direct identifiers and the governance gate blocks sample rows
     from a table that still carries them (ground.py — the pure parts only).
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


# --- PHI classifier + governance gate (pure parts of ground.py) --------------

@pytest.mark.parametrize("col,kind", [
    ("patient_name", "direct"), ("ssn", "direct"), ("mrn", "direct"),
    ("member_id", "direct"), ("email_address", "direct"), ("home_phone", "direct"),
    ("birth_date", "direct"), ("admit_date", "direct"), ("zip_code", "direct"),
    ("birth_year", "quasi"), ("age", "quasi"), ("sex", "quasi"), ("race", "quasi"),
    ("hba1c_value", "safe"), ("condition_code", "safe"), ("surrogate_key", "safe"),
])
def test_classify_column(col, kind):
    assert g.classify_column(col)[0] == kind


def test_scan_phi_buckets():
    res = g.scan_phi(["patient_name", "age", "hba1c_value", "ssn"])
    assert {c for c, _ in res["direct"]} == {"patient_name", "ssn"}
    assert {c for c, _ in res["quasi"]} == {"age"}


class _FakeQ:
    """Stub SQL runner so the governance gate can be tested offline."""
    def __init__(self, columns):
        self._cols = columns
    def __call__(self, stmt):
        if stmt.strip().upper().startswith("DESCRIBE"):
            return [[c, "string", ""] for c in self._cols]
        if "COUNT(*)" in stmt.upper():
            return [[42]]
        return []


def test_assert_shareable_blocks_sample_rows_with_phi():
    q = _FakeQ(["patient_name", "ssn", "hba1c_value"])
    with pytest.raises(g.PhiLeakError):
        g.assert_shareable("c.s.t", allow_sample_rows=True, q=q)


def test_assert_shareable_allows_aggregates_even_with_phi():
    q = _FakeQ(["patient_name", "hba1c_value"])
    prof = g.assert_shareable("c.s.t", allow_sample_rows=False, q=q)
    assert prof["shareable"]["aggregates_ok"] is True
    assert prof["shareable"]["sample_rows_ok"] is False
    assert prof["row_count"] == 42


def test_assert_shareable_clean_table_ok():
    q = _FakeQ(["patient_id", "condition_code", "age_band"])
    prof = g.assert_shareable("c.s.t", allow_sample_rows=True, q=q)
    assert prof["shareable"]["sample_rows_ok"] is True


def test_column_distribution_suppresses_small_cells():
    class DistQ:
        def __call__(self, stmt):
            return [["A", 100], ["B", 30], ["C", 3], ["D", 1]]
    out = g.column_distribution("c.s.t", "region", q=DistQ(), small_cell_k=11)
    labels = [b["label"] for b in out["bars"]]
    assert labels == ["A", "B"] and out["suppressed"] == 2
