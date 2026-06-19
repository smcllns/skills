# Report style skins

Three rich **style skins** for the social-research HTML report. Each skin is a
distinct **layout system** — its own structure, spacing, density and decoration,
not just a palette. You **pick one**, start from that skin's **worked-example
template**, fill in your content, and compose from the skin's classes. **You write
no custom CSS and no inline `style=`.** (Full recipe in
[`../../HTML_REPORT.md`](../../HTML_REPORT.md).)

A skin shapes **structure, not just colour**. The three look structurally
different side-by-side — different DOM, not the same page repainted:

| Skin | Layout system | Type | Feel |
| --- | --- | --- | --- |
| **editorial** *(default)* | Paper-grain magazine: masthead + meta-grid, italic section numerals, leader-dot index, a featured hero card then alternating left/right feature cards, criteria tiles, accent callouts. | Fraunces · Newsreader · IBM Plex Mono (serif) | Warm, editorial, stylish |
| **dossier** | Decision-grade briefing: compact document masthead + facts grid, a dense **scorecard matrix** index, horizontal **record cards** (fixed photo + tabular criteria + verdict line), flat hairline rules, square corners, no grain. | IBM Plex Sans · IBM Plex Mono (grotesk) | Trustworthy, dense, corporate |
| **playful** | Imagery-forward colour-block: vivid gradient hero, bright chip-card index, big photo-dominant cards that rotate through saturated accent hues, oversized rank numerals, sticker tags, soft-tint criteria chips. | Fredoka · Outfit · Space Mono (rounded) | Vivid, energetic, creative |

## Pick a taste (skin × mode) by the brief's mood

Each skin ships a **light** and a **dark** palette that are genuinely different
*moods*, not an inverted copy — so the real menu is **six tastes**. The skin sets
the **shape** (table above); the mode you author as default sets the **mood**. The
report loads in that authored mode regardless of the reader's OS (the reader can
still toggle). When nothing clearly fits, use the default, **`editorial · light`**.

| Taste (skin · mode) | Mood | Author it as default for |
| --- | --- | --- |
| **editorial · light** *(default)* | warm cream paper, refined tastemaker | lifestyle, travel, food, culture, stylish; general or mixed briefs read in daylight |
| **editorial · dark** | oxblood & ink, candle-lit and indulgent | dessert, ice-cream, wine, fashion, nightlife — sensory/after-dark topics that read better defaulted dark *even by day* |
| **dossier · light** | bright paper briefing, tabular and trustworthy | B2B / SaaS, factual decision aids, dense daylight comparisons |
| **dossier · dark** | navy terminal, data-forward and focused | engineering / security / infra shortlists, "ops console" topics, late-night decision work |
| **playful · light** | bright pop colour-blocks, high-energy | creative hobbies, kids / family, pop-culture, colourful food, anything cheerful |
| **playful · dark** | neon-on-plum, club energy that glows | gaming, music, nightlife, digital art — vivid topics that want to feel after-hours, defaulted dark by day |

Set the default by the template's `<html data-theme="…">` attribute: `light` or
`dark`.

## What every skin guarantees

- **Real embedded fonts** — OFL faces, latin-subset, **base64-embedded** (zero
  network). See [`fonts/README.md`](fonts/README.md) for the faces + subsetting
  recipe. The offline single-file contract still holds.
- **Light + dark**, both ≥ AA text contrast and first-class moods (not an
  inverted copy), with the accent visible on each background. Mode is set by
  `data-theme` (authored default; **not** `prefers-color-scheme`), flipped by a
  **two-button Light / Dark toggle**, persisted to `localStorage`, with a
  no-flash restore before first paint.
- **The shared validator floor** — every skin satisfies the same required
  ids/classes/sections (`#brief`, `#index`, `#map` just below the index,
  `#top-picks` cards with 3–5 consistent criteria tiles, `#near-misses` cards,
  open Appendices A/B/C, neutral footer). `scripts/validate_html_report.py`
  enforces it for all three.
- **Composition-resilient** — styled by class, fluid/responsive (`max-width` /
  `%` / `clamp()`, no fixed device width), no horizontal scroll at ~375px.

Each `.css` is the **canonical design layer** for its skin (its top comment names
the skin, mood, type and licence). The matching
`scripts/templates/<skin>.html` inlines that css verbatim in `<style id="skin">`,
plus the skin's base64 fonts, as a ready-to-fill worked example.

## How a skin is built

A skin's `.css` reads colours, type, radii and shadows from CSS custom properties
defined in `:root` (light) and in `:root[data-theme="dark"]` (dark), then styles
every element by class. The mode is driven solely by the `data-theme` attribute —
there is no `prefers-color-scheme` fallback, so the authored default always wins
until the reader toggles. No `@font-face`
lives in the `.css` — the faces are embedded in the template's font `<style>`
block (see `fonts/README.md`). Don't blend skins, invent a palette, or hand-roll
CSS in one report; if a real visual need isn't covered, that's a missing class in
the skin — surface it as a skill change.

## Attribution

The faces are Google Fonts families under the **SIL Open Font License 1.1**
(Fraunces, Newsreader, IBM Plex Sans/Mono, Fredoka, Outfit, Space Mono). The
editorial skin's craft system is derived from this skill's own rich exemplar; the
dossier and playful skins are independent re-derivations into the same contract
(one offline file, embedded fonts, fluid/responsive, light + dark).
