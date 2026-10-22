"""The LOCKED deck framework — the self-contained HTML shell every deck is built on.

This is the "DO NOT EDIT" layer, adapted faithfully from the OpenDesign deck runtime
(the Genie Design reference deck). It provides a fixed 1920x1080 canvas scaled to fit the
viewport, keyboard/click/postMessage navigation, "Save as PDF" one-slide-per-page export,
and the OD Deck Protocol v1 state events. Slide *content* and per-deck *styling* live
elsewhere (layouts.py + the deck spec); nothing here changes between decks.

Keeping this frozen is what makes every generated presentation behave identically and
survive iframe focus quirks — the renderer only ever concatenates these constants around
rendered slide bodies. Do not hand-edit the CSS/JS strings below.
"""

from __future__ import annotations

# --- Design tokens -----------------------------------------------------------
# Databricks brand palette. Overridable per deck ONLY via --accent (see build_deck);
# everything else is fixed so decks read as one system.
BRAND_ACCENT = "#ff3621"

# --- Framework CSS (first <style> block; frozen) -----------------------------
# Raw string: preserves the `\3c style>` CSS escape used so the comment can mention a
# <style> tag without the browser parsing it.
FRAMEWORK_CSS = r"""    /* ===========================================================
       Deck framework — DO NOT EDIT the rules in this \3c style> block.
       Edit only inside the second \3c style> block below (per-deck
       styles) and inside <section class="slide"> bodies.

       Contract this framework provides:
         - 1920×1080 fixed canvas, scaled to fit the viewport
         - Only .slide.active is visible at a time
         - Programmatic prev/next + counter elements kept outside the scaled
           stage but hidden by default so the host can render the UI chrome
         - OD Deck Protocol v1 absolute navigation + state events
         - Keyboard (← → space PgUp PgDn Home End R), half-slide click, and stored
           position survive iframe focus quirks
         - "Save as PDF" produces a multi-page vertical PDF, one slide
           per page, by toggling every slide visible under @media print
       =========================================================== */
    :root {
      --bg: #ffffff;
      --fg: #1b3139;
      --muted: #1b5162;
      --accent: #ff3621;
      --surface: #f9f7f4;
      --shell: #1b3139;
      --border: #dce0e2;
      --success: #00a972;
      --font-display: "DM Sans", system-ui, -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      --font-body: "DM Sans", system-ui, -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      --font-mono: "DM Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: var(--shell);
      color: var(--fg);
      font: 18px/1.5 -apple-system, system-ui, sans-serif;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    .deck-shell { position: fixed; inset: 0; overflow: hidden; }
    .deck-stage {
      width: 1920px; height: 1080px; background: var(--bg); position: relative;
      transform-origin: top left; box-shadow: 0 30px 80px rgba(0, 0, 0, 0.35);
    }
    .slide { position: absolute; inset: 0; overflow: hidden; }
    .slide:not(.active) { display: none !important; }
    :where(.slide.active) { display: flex; flex-direction: column; }
    .deck-counter {
      position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%); display: none;
      align-items: center; gap: 4px; background: rgba(10, 14, 26, 0.92);
      backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); padding: 6px;
      border-radius: 999px; border: 1px solid rgba(255, 255, 255, 0.08); color: #fff;
      font: 12px/1 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 0.18em; z-index: 1000;
    }
    .deck-counter button {
      width: 36px; height: 36px; background: transparent; color: #fff; border: 0;
      border-radius: 50%; font-size: 18px; line-height: 1; cursor: pointer; display: grid;
      place-items: center; transition: background 0.15s;
    }
    .deck-counter button:hover { background: rgba(255, 255, 255, 0.12); }
    .deck-counter button[disabled] { opacity: 0.3; cursor: default; }
    .deck-counter .deck-count { padding: 0 14px; letter-spacing: 0.22em; }
    .deck-counter .deck-count .total { color: rgba(255, 255, 255, 0.5); }
    .deck-hint {
      position: fixed; bottom: 26px; right: 28px; color: rgba(255, 255, 255, 0.4);
      font: 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: 0.2em;
      text-transform: uppercase; z-index: 999; pointer-events: none; display: none;
    }
    @media print {
      @page { size: 1920px 1080px; margin: 0; }
      html, body { width: 1920px !important; height: auto !important; overflow: visible !important; background: #fff !important; }
      .deck-shell { position: static !important; display: block !important; inset: auto !important; }
      .deck-stage { width: 1920px !important; height: auto !important; transform: none !important; box-shadow: none !important; position: static !important; }
      .slide { display: flex !important; position: relative !important; inset: auto !important; width: 1920px !important; height: 1080px !important; page-break-after: always; break-after: page; }
      .slide:last-child { page-break-after: auto; break-after: auto; }
      .deck-counter, .deck-hint { display: none !important; }
    }"""

# --- Navigation chrome markup (frozen) ---------------------------------------
NAV_MARKUP = """  <nav class="deck-counter" role="navigation" aria-label="Deck navigation">
    <button type="button" id="deck-prev" aria-label="Previous slide">‹</button>
    <span class="deck-count"><span id="deck-cur">01</span> <span class="total">/ <span id="deck-total">01</span></span></span>
    <button type="button" id="deck-next" aria-label="Next slide">›</button>
  </nav>
  <div class="deck-hint">← / → · space · R reset</div>"""

# --- Navigation runtime (frozen; OD Deck Protocol v1) ------------------------
NAV_JS = r"""    (function () {
      var stage = document.getElementById('deck-stage');
      var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
      var prev = document.getElementById('deck-prev');
      var next = document.getElementById('deck-next');
      var cur = document.getElementById('deck-cur');
      var total = document.getElementById('deck-total');
      var STORE = 'deck:idx:' + (location.pathname || '/');
      var idx = 0;
      function fit() {
        var sw = window.innerWidth; var sh = window.innerHeight; var pad = 32;
        var s = Math.min((sw - pad) / 1920, (sh - pad) / 1080);
        if (!isFinite(s) || s <= 0) s = 1;
        var tx = (sw - 1920 * s) / 2; var ty = (sh - 1080 * s) / 2;
        stage.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + s + ')';
      }
      function pad2(n) { return (n < 10 ? '0' : '') + n; }
      function paint() {
        slides.forEach(function (el, i) { el.classList.toggle('active', i === idx); });
        if (cur) cur.textContent = pad2(idx + 1); if (total) total.textContent = pad2(slides.length);
        if (prev) prev.toggleAttribute('disabled', idx <= 0); if (next) next.toggleAttribute('disabled', idx >= slides.length - 1);
        postDeckState();
      }
      function go(i) { idx = Math.max(0, Math.min(slides.length - 1, i)); paint(); try { localStorage.setItem(STORE, String(idx)); } catch (_) {} }
      var OD_DECK_PROTOCOL_VERSION = 1;
      function postDeckState() { try { window.parent.postMessage({ type: 'od:slide-state', protocolVersion: OD_DECK_PROTOCOL_VERSION, active: idx, count: slides.length }, '*'); } catch (_) {} }
      function announceDeckProtocol() { try { window.parent.postMessage({ type: 'od:deck-ready', protocolVersion: OD_DECK_PROTOCOL_VERSION, capabilities: ["absolute-navigation","state-events"] }, '*'); } catch (_) {} }
      window.addEventListener('message', function (event) {
        var data = event && event.data; if (!data || data.type !== 'od:slide') return;
        if (data.protocolVersion != null && data.protocolVersion !== OD_DECK_PROTOCOL_VERSION) return;
        var target = idx;
        if (data.action === 'go') { if (typeof data.index !== 'number' || !isFinite(data.index)) return; target = Math.floor(data.index); }
        else if (data.action === 'next') target = idx + 1; else if (data.action === 'prev') target = idx - 1;
        else if (data.action === 'first') target = 0; else if (data.action === 'last') target = slides.length - 1; else return;
        go(target);
      });
      function onKey(e) {
        if (e.__odDeckKeyHandled) return; var t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
        if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
        if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') { e.__odDeckKeyHandled = true; e.preventDefault(); go(idx + 1); }
        else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.__odDeckKeyHandled = true; e.preventDefault(); go(idx - 1); }
        else if (e.key === 'Home' || String(e.key).toLowerCase() === 'r') { e.__odDeckKeyHandled = true; e.preventDefault(); go(0); }
        else if (e.key === 'End') { e.__odDeckKeyHandled = true; e.preventDefault(); go(slides.length - 1); }
      }
      window.addEventListener('keydown', onKey, true); document.addEventListener('keydown', onKey, true);
      if (prev) prev.addEventListener('click', function () { go(idx - 1); }); if (next) next.addEventListener('click', function () { go(idx + 1); });
      document.addEventListener('click', function (e) {
        if (e.defaultPrevented) return; if (e.button !== undefined && e.button !== 0) return; if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
        var t = e.target;
        while (t && t !== document.body && t !== document.documentElement) {
          var tag = String(t.tagName || '').toUpperCase();
          if (tag === 'A' || tag === 'BUTTON' || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t.isContentEditable || t.getAttribute('role') === 'button' || t.getAttribute('role') === 'link') return;
          t = t.parentElement;
        }
        focusDeck(); if (e.clientX < window.innerWidth / 2) go(idx - 1); else go(idx + 1);
      }, true);
      document.body.setAttribute('tabindex', '-1'); document.body.style.outline = 'none';
      function focusDeck() { try { window.focus(); document.body.focus({ preventScroll: true }); } catch (_) {} }
      document.addEventListener('mousedown', focusDeck); window.addEventListener('load', focusDeck);
      try { var saved = parseInt(localStorage.getItem(STORE) || '0', 10); if (!isNaN(saved) && saved >= 0 && saved < slides.length) idx = saved; } catch (_) {}
      window.addEventListener('resize', fit); announceDeckProtocol(); fit(); paint(); focusDeck();
    })();"""

# Optional webfont (DM Sans / DM Mono). Progressive: if the viewer is offline the
# framework CSS falls back to system-ui, so the deck still renders.
FONT_LINK = (
    '  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '  <link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&'
    'family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet">'
)
