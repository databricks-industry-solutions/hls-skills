"""Slide layout vocabulary — pure, SDK-free HTML renderers + the per-deck component CSS.

This is the "edit here" layer the framework comment refers to. Each layout is a small,
deterministic function from a slide spec (a dict) to an HTML `<section class="slide">`.
Keeping these pure makes the renderer fully testable offline (no warehouse, no network)
and guarantees two decks built from the same spec are byte-identical.

Supported layout types (slide["type"]):
    cover         title slide: kicker, title, subtitle, meta list, disclaimer, logo
    statement     one big centered statement (section divider / thesis)
    bullets       title + lead + numbered points (heading + body each)
    cards         title + 2-4 cards (label, heading, body); one may be featured
    metrics       title + KPI tiles (value, label, caption) — for GROUNDED figures
    bar_chart     title + horizontal bar chart (label, value) — for GROUNDED figures
    two_column    title + left copy / right panel (points or an image)
    architecture  title + vertically stacked nodes (label, heading, body)
    closing       closing statement + next-step list

Every slide may carry: label (screen label "NN Title"), theme ("light"|"dark"),
footer_left, page (footer page number), notes (speaker notes), id (data-od-id).

Inline markup inside any text field: `[[x]]` -> accent highlight, `**x**` -> bold.
All text is HTML-escaped BEFORE markup is applied, so user content cannot break the deck.
"""

from __future__ import annotations

import html
import re

# --- Component CSS (second <style> block; this is the editable layer) --------
COMPONENT_CSS = """    .slide { padding: 64px 120px 48px; font-family: var(--font-body); background: var(--surface); color: var(--fg); }
    .slide.dark { background: var(--fg); color: var(--bg); }
    .slide.light { background: var(--surface); color: var(--fg); }
    .slide.hero { justify-content: center; }
    .kicker { margin-bottom: 20px; font-family: var(--font-mono); font-size: 17px; line-height: 1.3; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); }
    .display { font-family: var(--font-display); font-size: 104px; font-weight: 500; line-height: 1.02; letter-spacing: -0.03em; }
    .title { max-width: none; font-family: var(--font-display); font-size: 58px; font-weight: 500; line-height: 1.08; letter-spacing: -0.02em; }
    .subtitle { max-width: 60ch; margin-top: 18px; color: var(--muted); font-size: 28px; line-height: 1.4; }
    .dark .subtitle { color: var(--bg); }
    .hl { color: var(--accent); }
    .slide-head { flex: 0 0 auto; }
    .slide-head .subtitle { width: 100%; max-width: none; }
    .slide-body { flex: 1; min-height: 0; display: flex; align-items: center; padding-bottom: 92px; }
    .slide-body.top { align-items: flex-start; padding-top: 40px; }
    .footer { position: absolute; left: 120px; right: 120px; bottom: 48px; padding-top: 18px; border-top: 1px solid var(--border); display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 16px; letter-spacing: 0.02em; color: var(--muted); }
    .dark .footer { color: var(--bg); border-color: rgba(255,255,255,0.18); }

    /* cover */
    .cover { width: 100%; max-width: 1560px; margin-inline: auto; display: grid; grid-template-columns: 1fr 280px; align-items: center; gap: 100px; }
    .cover.no-logo { grid-template-columns: 1fr; }
    .cover .display { font-size: 132px; }
    .cover .subtitle { max-width: 34ch; font-size: 36px; color: var(--muted); }
    .dark .cover .subtitle { color: var(--bg); }
    .cover-meta { margin-top: 34px; display: flex; flex-wrap: wrap; gap: 10px 28px; font-family: var(--font-mono); font-size: 18px; letter-spacing: 0.02em; color: var(--muted); }
    .dark .cover-meta { color: var(--bg); }
    .cover-disclaimer { max-width: 60ch; margin-top: 34px; padding-top: 18px; border-top: 1px solid var(--accent); font-family: var(--font-mono); font-size: 16px; line-height: 1.5; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); }
    .dark .cover-disclaimer { color: var(--bg); }
    .cover-logo { width: 280px; height: 280px; object-fit: contain; border-radius: 16px; }

    /* statement / closing */
    .statement { width: 100%; max-width: 1400px; margin-inline: auto; }
    .statement .eyebrow { font-family: var(--font-mono); font-size: 18px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); margin-bottom: 26px; }
    .statement .big { font-family: var(--font-display); font-size: 76px; font-weight: 500; line-height: 1.12; letter-spacing: -0.02em; max-width: 26ch; }
    .steps { margin-top: 44px; display: grid; gap: 16px; max-width: 1100px; }
    .step { display: grid; grid-template-columns: 48px 1fr; gap: 20px; align-items: baseline; padding-top: 18px; border-top: 1px solid var(--border); }
    .dark .step { border-color: rgba(255,255,255,0.18); }
    .step .n { font-family: var(--font-mono); color: var(--accent); font-size: 18px; }
    .step .t { font-size: 24px; line-height: 1.4; }
    .step .t strong { font-weight: 600; }

    /* bullets */
    .points { width: 100%; max-width: 1560px; margin-inline: auto; display: grid; gap: 18px; }
    .point { display: grid; grid-template-columns: 56px 1fr; gap: 24px; align-items: start; padding-top: 22px; border-top: 1px solid var(--border); }
    .dark .point { border-color: rgba(255,255,255,0.18); }
    .point .n { font-family: var(--font-mono); color: var(--accent); font-size: 19px; padding-top: 6px; }
    .point h3 { font-size: 30px; line-height: 1.2; font-weight: 500; }
    .point p { margin-top: 8px; font-size: 22px; line-height: 1.45; color: var(--muted); }
    .dark .point p { color: var(--bg); }

    /* cards */
    .cards { width: 100%; max-width: 1560px; margin-inline: auto; display: grid; gap: 28px; }
    .cards.n2 { grid-template-columns: repeat(2, 1fr); }
    .cards.n3 { grid-template-columns: repeat(3, 1fr); }
    .cards.n4 { grid-template-columns: repeat(4, 1fr); }
    .card { min-height: 380px; padding: 34px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); color: var(--fg); display: flex; flex-direction: column; }
    .card.featured { background: var(--fg); color: var(--bg); border-color: var(--fg); }
    .card .label { font-family: var(--font-mono); font-size: 16px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
    .card.featured .label { color: var(--accent); }
    .card h3 { margin-top: auto; padding-top: 48px; font-size: 34px; line-height: 1.15; font-weight: 500; letter-spacing: -0.01em; }
    .card p { margin-top: 18px; font-size: 21px; line-height: 1.45; color: var(--muted); }
    .card.featured p { color: var(--bg); }

    /* metrics / KPI tiles */
    .tiles { width: 100%; max-width: 1560px; margin-inline: auto; display: grid; gap: 28px; }
    .tiles.n2 { grid-template-columns: repeat(2, 1fr); }
    .tiles.n3 { grid-template-columns: repeat(3, 1fr); }
    .tiles.n4 { grid-template-columns: repeat(4, 1fr); }
    .tile { padding: 34px 34px 30px; border-top: 2px solid var(--accent); background: var(--bg); color: var(--fg); }
    .tile .value { font-family: var(--font-display); font-size: 84px; font-weight: 500; line-height: 1; letter-spacing: -0.03em; }
    .tile .label { margin-top: 16px; font-size: 24px; line-height: 1.25; font-weight: 500; }
    .tile .caption { margin-top: 12px; font-family: var(--font-mono); font-size: 15px; line-height: 1.4; color: var(--muted); }

    /* bar chart */
    .chart { width: 100%; max-width: 1560px; margin-inline: auto; padding: 34px 36px 32px; border-top: 2px solid var(--accent); background: var(--bg); color: var(--fg); }
    .chart-head { display: flex; align-items: baseline; justify-content: space-between; gap: 24px; margin-bottom: 30px; }
    .chart-head h3 { font-size: 32px; line-height: 1.2; font-weight: 500; }
    .chart-head span { font-family: var(--font-mono); font-size: 15px; color: var(--muted); }
    .bars { display: grid; gap: 22px; }
    .bar-row { display: grid; grid-template-columns: 320px 1fr 120px; gap: 20px; align-items: center; }
    .bar-label { font-size: 20px; line-height: 1.25; }
    .bar-track { height: 36px; background: var(--surface); border: 1px solid var(--border); }
    .bar-fill { height: 100%; background: var(--fg); }
    .bar-row:first-child .bar-fill { background: var(--accent); }
    .bar-value { font-family: var(--font-mono); font-size: 20px; text-align: right; }

    /* two column */
    .two-col { width: 100%; max-width: 1560px; margin-inline: auto; display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 72px; align-items: center; }
    .col-copy p { font-size: 24px; line-height: 1.5; color: var(--muted); }
    .dark .col-copy p { color: var(--bg); }
    .col-copy p + p { margin-top: 20px; }
    .col-copy strong { color: var(--fg); font-weight: 600; }
    .dark .col-copy strong { color: var(--bg); }
    .col-panel { padding: 40px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); color: var(--fg); }
    .col-panel .points, .col-panel .steps { margin: 0; max-width: none; }
    .col-panel img, .col-img { width: 100%; height: 100%; object-fit: contain; display: block; border-radius: 8px; }

    /* architecture */
    .arch { width: 100%; max-width: 1400px; margin-inline: auto; display: grid; gap: 18px; }
    .arch-node { padding: 28px 34px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); color: var(--fg); display: grid; grid-template-columns: 0.8fr 1fr 1.6fr; align-items: center; gap: 32px; }
    .arch-node .label { font-family: var(--font-mono); font-size: 16px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
    .arch-node h3 { font-size: 32px; line-height: 1.15; font-weight: 500; }
    .arch-node p { font-size: 20px; line-height: 1.45; color: var(--muted); }
    .arch-arrow { text-align: center; font-size: 28px; color: var(--accent); margin: -6px 0; }

    .speaker-notes { display: none; }
    [data-od-id]:focus-visible { outline: 4px solid var(--success); outline-offset: 6px; }

    /* Standalone decks are shared WITHOUT a host app's chrome, so surface the built-in
       navigation the frozen framework ships (and wires to prev/next): a prev · counter ·
       next pill (bottom center) plus a keyboard hint (bottom right). Overriding here in the
       editable layer leaves the frozen framework block untouched. */
    .deck-counter { display: flex; }
    .deck-hint { display: block; }
    @media print { .deck-counter, .deck-hint { display: none !important; } }"""

# --- inline markup -----------------------------------------------------------

def _inline(text) -> str:
    """HTML-escape text, then apply the tiny inline markup: [[x]] -> accent, **x** -> bold."""
    s = html.escape("" if text is None else str(text))
    s = re.sub(r"\[\[(.+?)\]\]", r'<span class="hl">\1</span>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return s


def _attr(text) -> str:
    """Escape text for use inside an HTML attribute value."""
    return html.escape("" if text is None else str(text), quote=True)


def _footer(slide) -> str:
    left = slide.get("footer_left", "")
    page = slide.get("page")
    page_s = ("%02d" % page) if isinstance(page, int) else _inline(page or "")
    return f'<div class="footer"><span>{_inline(left)}</span><span>{page_s}</span></div>'


def _head(slide) -> str:
    """Kicker + title + subtitle header block, shared by content layouts."""
    parts = ['<header class="slide-head">']
    if slide.get("kicker"):
        parts.append(f'<div class="kicker">{_inline(slide["kicker"])}</div>')
    if slide.get("title"):
        parts.append(f'<h2 class="title">{_inline(slide["title"])}</h2>')
    if slide.get("subtitle"):
        parts.append(f'<p class="subtitle">{_inline(slide["subtitle"])}</p>')
    parts.append("</header>")
    return "".join(parts)


def _grid_class(base: str, n: int) -> str:
    return f"{base} n{max(2, min(4, n))}"


# --- layout renderers --------------------------------------------------------

def _cover(slide) -> str:
    logo = slide.get("logo")
    body = ['<div class="cover%s">' % ("" if logo else " no-logo")]
    body.append('<div class="cover-main">')
    if slide.get("kicker"):
        body.append(f'<div class="kicker">{_inline(slide["kicker"])}</div>')
    body.append(f'<h1 class="display">{_inline(slide.get("title", ""))}</h1>')
    if slide.get("subtitle"):
        body.append(f'<p class="subtitle">{_inline(slide["subtitle"])}</p>')
    meta = slide.get("meta") or []
    if meta:
        body.append('<div class="cover-meta">' + "".join(f"<span>{_inline(m)}</span>" for m in meta) + "</div>")
    if slide.get("disclaimer"):
        body.append(f'<p class="cover-disclaimer">{_inline(slide["disclaimer"])}</p>')
    body.append("</div>")
    if logo:
        body.append(f'<img class="cover-logo" src="{_attr(logo)}" alt="{_attr(slide.get("logo_alt", "Logo"))}">')
    body.append("</div>")
    return "".join(body)


def _statement(slide) -> str:
    body = ['<div class="statement">']
    if slide.get("eyebrow"):
        body.append(f'<div class="eyebrow">{_inline(slide["eyebrow"])}</div>')
    body.append(f'<p class="big">{_inline(slide.get("statement", slide.get("title", "")))}</p>')
    body += _steps_block(slide.get("steps"))
    body.append("</div>")
    return "".join(body)


def _steps_block(steps) -> list:
    if not steps:
        return []
    out = ['<div class="steps">']
    for i, s in enumerate(steps, 1):
        if isinstance(s, dict):
            label = s.get("label") or ("%02d" % i)
            text = s.get("text", "")
        else:
            label, text = "%02d" % i, s
        out.append(f'<div class="step"><span class="n">{_inline(label)}</span><span class="t">{_inline(text)}</span></div>')
    out.append("</div>")
    return out


def _bullets(slide) -> str:
    pts = slide.get("points") or []
    out = [_head(slide), '<div class="slide-body top"><div class="points">']
    for i, p in enumerate(pts, 1):
        if isinstance(p, dict):
            heading, bodytext = p.get("heading", ""), p.get("body", "")
        else:
            heading, bodytext = p, ""
        out.append('<div class="point">')
        out.append(f'<span class="n">{"%02d" % i}</span>')
        out.append("<div>")
        if heading:
            out.append(f"<h3>{_inline(heading)}</h3>")
        if bodytext:
            out.append(f"<p>{_inline(bodytext)}</p>")
        out.append("</div></div>")
    out.append("</div></div>")
    return "".join(out)


def _cards(slide) -> str:
    cards = slide.get("cards") or []
    out = [_head(slide), '<div class="slide-body">', f'<div class="{_grid_class("cards", len(cards))}">']
    for c in cards:
        cls = "card featured" if c.get("featured") else "card"
        out.append(f'<article class="{cls}">')
        if c.get("label"):
            out.append(f'<div class="label">{_inline(c["label"])}</div>')
        out.append(f'<h3>{_inline(c.get("heading", ""))}</h3>')
        if c.get("body"):
            out.append(f'<p>{_inline(c["body"])}</p>')
        out.append("</article>")
    out.append("</div></div>")
    return "".join(out)


def _metrics(slide) -> str:
    tiles = slide.get("tiles") or []
    out = [_head(slide), '<div class="slide-body">', f'<div class="{_grid_class("tiles", len(tiles))}">']
    for t in tiles:
        out.append('<div class="tile">')
        out.append(f'<div class="value">{_inline(t.get("value", ""))}</div>')
        out.append(f'<div class="label">{_inline(t.get("label", ""))}</div>')
        if t.get("caption"):
            out.append(f'<div class="caption">{_inline(t["caption"])}</div>')
        out.append("</div>")
    out.append("</div></div>")
    return "".join(out)


def _bar_chart(slide) -> str:
    chart = slide.get("chart") or {}
    bars = chart.get("bars") or []
    values = [float(b.get("value", 0) or 0) for b in bars]
    scale = chart.get("max") or (max(values) if values else 1) or 1
    out = [_head(slide), '<div class="slide-body"><div class="chart">']
    out.append('<div class="chart-head">')
    out.append(f'<h3>{_inline(chart.get("heading", ""))}</h3>')
    if chart.get("unit"):
        out.append(f'<span>{_inline(chart["unit"])}</span>')
    out.append('</div><div class="bars">')
    for b in bars:
        v = float(b.get("value", 0) or 0)
        pct = max(0.0, min(100.0, (v / scale) * 100.0)) if scale else 0.0
        display = b.get("display") if b.get("display") is not None else _fmt_num(v)
        out.append('<div class="bar-row">')
        out.append(f'<div class="bar-label">{_inline(b.get("label", ""))}</div>')
        out.append(f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>')
        out.append(f'<div class="bar-value">{_inline(display)}</div>')
        out.append("</div>")
    out.append("</div></div></div>")
    return "".join(out)


def _two_column(slide) -> str:
    out = [_head(slide), '<div class="slide-body"><div class="two-col">']
    out.append('<div class="col-copy">')
    for para in slide.get("left") or []:
        out.append(f"<p>{_inline(para)}</p>")
    out.append("</div>")
    right = slide.get("right") or {}
    out.append('<div class="col-panel">')
    if right.get("image"):
        out.append(f'<img class="col-img" src="{_attr(right["image"])}" alt="{_attr(right.get("alt", ""))}">')
    elif right.get("steps"):
        out += _steps_block(right["steps"])
    elif right.get("points"):
        out.append('<div class="points">')
        for i, p in enumerate(right["points"], 1):
            heading = p.get("heading", "") if isinstance(p, dict) else p
            bodytext = p.get("body", "") if isinstance(p, dict) else ""
            out.append(f'<div class="point"><span class="n">{"%02d" % i}</span><div><h3>{_inline(heading)}</h3>')
            if bodytext:
                out.append(f"<p>{_inline(bodytext)}</p>")
            out.append("</div></div>")
        out.append("</div>")
    out.append("</div></div></div>")
    return "".join(out)


def _architecture(slide) -> str:
    nodes = slide.get("nodes") or []
    out = [_head(slide), '<div class="slide-body"><div class="arch">']
    for i, n in enumerate(nodes):
        if i:
            out.append('<div class="arch-arrow">↓</div>')
        out.append('<article class="arch-node">')
        out.append(f'<div class="label">{_inline(n.get("label", ""))}</div>')
        out.append(f'<h3>{_inline(n.get("heading", ""))}</h3>')
        out.append(f'<p>{_inline(n.get("body", ""))}</p>')
        out.append("</article>")
    out.append("</div></div>")
    return "".join(out)


def _closing(slide) -> str:
    # closing is a statement with next-steps; reuse the statement machinery.
    return _statement(slide)


def _fmt_num(v: float) -> str:
    """Compact human number: ints without decimals, else one decimal, thousands grouped."""
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.1f}"


RENDERERS = {
    "cover": _cover,
    "statement": _statement,
    "bullets": _bullets,
    "cards": _cards,
    "metrics": _metrics,
    "bar_chart": _bar_chart,
    "two_column": _two_column,
    "architecture": _architecture,
    "closing": _closing,
}

# Layouts that center content vertically (hero); others top-align via their own body class.
_HERO_TYPES = {"cover", "statement", "closing"}


def render_slide(slide, index: int, total: int) -> str:
    """Render one slide spec to a complete <section class="slide"> string."""
    stype = slide.get("type")
    if stype not in RENDERERS:
        raise ValueError(
            f"Unknown slide type {stype!r} (slide {index + 1}). "
            f"Valid types: {', '.join(sorted(RENDERERS))}."
        )
    theme = slide.get("theme", "light")
    if theme not in ("light", "dark"):
        raise ValueError(f"slide {index + 1}: theme must be 'light' or 'dark', got {theme!r}")
    classes = ["slide", theme]
    if stype in _HERO_TYPES:
        classes.append("hero")
    label = slide.get("label") or f"{index + 1:02d} {stype.title()}"
    od_id = slide.get("id") or f"slide-{index + 1:02d}"

    inner = RENDERERS[stype](slide)
    footer = "" if slide.get("no_footer") else _footer({**slide, "page": slide.get("page", index + 1)})
    notes = slide.get("notes")
    notes_html = f'<aside class="speaker-notes">{_inline(notes)}</aside>' if notes else ""

    return (
        f'      <section class="{" ".join(classes)}" '
        f'data-screen-label="{_attr(label)}" data-od-id="{_attr(od_id)}">\n'
        f"        {inner}\n"
        f"        {footer}\n"
        f"        {notes_html}\n"
        f"      </section>"
    )
