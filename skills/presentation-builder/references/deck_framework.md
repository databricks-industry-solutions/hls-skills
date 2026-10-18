# Deck-spec contract & layout vocabulary

The deck is a single JSON-serializable **spec**. `build_deck.build_deck(spec, out_path)`
validates it, renders each slide onto the frozen framework, and writes one self-contained
`.html`. `build_deck.render_html(spec)` returns the HTML string without writing a file.

## Deck spec

```jsonc
{
  "title": "Deck title",              // browser tab <title>
  "footer_left": "Databricks · HLS",  // default footer-left text for every slide
  "accent": "#ff3621",                // OPTIONAL #hex accent override (brand = #ff3621)
  "slides": [ /* one object per slide, see below */ ]
}
```

Only `slides` is required; it must be non-empty. An invalid spec raises — a broken deck is
never written.

## Fields on every slide

| Field | Meaning |
|-------|---------|
| `type` | one of the layout types below (required) |
| `theme` | `"light"` (default) or `"dark"` |
| `label` | screen label `"NN Title"` (auto-generated if omitted) |
| `kicker` | small uppercase eyebrow above the title (accent color) |
| `title` | slide title |
| `subtitle` | supporting line under the title |
| `notes` | speaker notes (hidden `<aside>` + machine-readable JSON block) |
| `footer_left` | overrides the deck default for this slide |
| `page` | footer page number (auto = slide index) |
| `no_footer` | `true` to hide the footer on this slide |
| `id` | `data-od-id` anchor (auto = `slide-NN`) |

### Inline markup (any text field)

- `[[x]]` → `x` in the accent color (the brand red highlight)
- `**x**` → **bold**
- Everything is HTML-escaped **before** markup is applied, so user content can't break the deck.

## Layout types

### `cover` — title slide (hero, vertically centered)
`kicker`, `title`, `subtitle`, `meta` (list of short strings, e.g. version/date), `disclaimer`
(uppercase mono line over an accent rule), `logo` (image URL/data-URI) + `logo_alt`.

### `statement` — one big centered thesis (hero)
`eyebrow`, `statement` (the big line), optional `steps` (list of strings or `{label, text}`).

### `closing` — same shape as `statement`
Use for next-steps / CTA. `eyebrow`, `statement`, `steps`.

### `bullets` — title + numbered points
`points`: list of `{heading, body}` (or plain strings). Numbered 01, 02, …

### `cards` — 2–4 cards
`cards`: list of `{label, heading, body, featured?}`. One `featured: true` card is inverted
(dark). Grid auto-sizes to the count (clamped 2–4).

### `metrics` — KPI tiles (GROUNDED figures)
`tiles`: list of `{value, label, caption}`. `value` is a pre-formatted string
(`"2,214"`, `"8.6"`, `"94.1%"`). Put the `ground.py` `source` string in `caption`.

### `bar_chart` — horizontal bars (GROUNDED figures)
`chart`: `{heading, unit, bars, max?}`. `bars`: list of `{label, value, display?}`. Bars
auto-scale to `max` (or the largest value); the **first** bar is accent-colored. `display`
overrides the printed value label.

### `two_column` — copy + panel
`left`: list of paragraphs (markup allowed). `right`: one of
`{"points": [...]}`, `{"steps": [...]}`, or `{"image": "url", "alt": "..."}`.

### `architecture` — stacked flow nodes
`nodes`: list of `{label, heading, body}`, rendered top-to-bottom with ↓ connectors.

## Navigation & export (provided by the frozen framework)

- **On-screen nav bar**: a prev · `NN / NN` counter · next pill is pinned bottom-center, with
  a keyboard hint bottom-right. These are shown by default (the editable layer re-enables the
  framework chrome, which is hidden only for host-embedded use) so a standalone shared deck is
  obviously a slide deck and navigable without instructions.
- Keys: `← / →`, `space` / `PgDn` next, `PgUp` prev, `Home` / `R` reset, `End` last.
- Click: left half = previous, right half = next (links/buttons are exempt).
- Position is remembered via `localStorage`; the deck fits any viewport (scaled 1920×1080).
- **Save as PDF**: open the browser print dialog → one slide per page, 1920×1080 landscape.
- Embeddable: posts `od:deck-ready` / `od:slide-state` and accepts `od:slide` messages
  (OD Deck Protocol v1) so a host page can drive it.

## What is frozen vs editable

- **Frozen** (`deck_framework.py`): the first `<style>` block, the nav markup, the nav JS,
  the print CSS, the `:root` tokens. Never hand-edit; it's what makes every deck consistent.
- **Editable**: `layouts.COMPONENT_CSS` (the second `<style>` block — component styling) and
  the per-slide spec content. A per-deck accent is set via `spec["accent"]` only.
