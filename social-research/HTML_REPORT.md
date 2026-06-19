# HTML Report (rich skins)

An optional, shareable HTML version of a finished search. It is **derived from
`report.md`** — `report.md` stays the raw artifact; the HTML is a curated,
designed view of the same findings. Read this only when producing an HTML report.

**The model in one line:** the skill ships **three rich skins** (editorial /
dossier / playful), and each has a genuinely different **light** and **dark**
mood — so there are **six "tastes"** (skin × mode) to choose from. Pick the one
taste that fits the brief, start from that skin's **worked-example template**, set
its **authored default mode** (light or dark) to match the taste, fill in your
content, compose from the skin's classes — **write no custom CSS**. A skin is a
whole **layout system** (structure + spacing + density + decoration), not a
palette, so the choice shapes the report's *shape*; the mode you author as default
sets its *mood*.

## When to produce it

- The user asks for a shareable / pretty / sendable version of the findings, or
- the shortlist is decision-grade (a handful of picks the user will choose between)
  and a single self-contained file is more useful than markdown.

Skip it for quick lookups or raw evidence dumps — `report.md` is enough. For
decision-grade reports, do not generate HTML until the adversarial research
review verdict in `report.md` is `pass` or the user has acknowledged known
limitations (see `SKILL.md`).

## Output contract (locked)

- **One self-contained `.html` file.** It must open with **zero network or local
  dependencies** — no hotlinked images, no `./..._files/` paths, no CDN fonts.
- **Images are base64 data-URIs**, inlined directly in `<img src="data:...">`.
- **Real fonts, base64-embedded** — each skin ships genuine OFL faces as
  **latin-subset woff2, base64-embedded** in a `<style>` block, so the report
  still opens with **zero network requests**. You don't load or pick fonts: the
  worked-example template already carries the skin's faces. (Faces + subsetting
  recipe: [`reference/styles/fonts/README.md`](reference/styles/fonts/README.md).)
- **Light *and* dark mode**, defaulting to the **mode you author** for the taste
  you picked — not the OS preference (see below).

## Step 1 — pick a taste (skin × mode), don't design from scratch

Don't invent a visual identity. The skill bundles **three** rich skins in
[`reference/styles/`](reference/styles/). Each skin is a **distinct layout
system** — its own structure, density, type and decoration — and each ships a
**light** and a **dark** palette that are genuinely different *moods*, not an
inverted copy. So the real menu is **six tastes** (skin × mode). Picking a taste
sets both the report's **shape** (the skin) and its **mood** (the default mode).
This is what keeps reports consistent and high-craft regardless of who runs them.

**Skim** [`reference/styles/README.md`](reference/styles/README.md) and pick the
**one** taste whose mood fits the brief. Default to **`editorial · light`** when
nothing clearly fits.

The **shape** comes from the skin:

| Skin | Shape |
| --- | --- |
| **editorial** *(default)* | serif paper-grain magazine — masthead + meta-grid, section numerals, leader-dot index, featured hero then alternating left/right feature cards |
| **dossier** | grotesk decision briefing — facts grid, a dense scorecard-matrix index, horizontal tabular record cards, flat hairline rules, square corners |
| **playful** | rounded bright colour-block — vivid gradient hero, chip-card index, big photo-dominant cards rotating through saturated hues, oversized rank numerals |

The **mood** comes from which mode you author as the default — these six are the
tastes to choose between:

| Taste (skin · mode) | Mood | Author it as default for |
| --- | --- | --- |
| **editorial · light** *(default)* | warm cream paper, refined tastemaker | lifestyle, travel, food, culture, stylish; general or mixed briefs read in daylight |
| **editorial · dark** | oxblood & ink, candle-lit and indulgent | dessert, ice-cream, wine, fashion, nightlife — sensory/after-dark topics that read better defaulted dark *even by day* |
| **dossier · light** | bright paper briefing, tabular and trustworthy | B2B / SaaS, factual decision aids, dense daylight comparisons |
| **dossier · dark** | navy terminal, data-forward and focused | engineering / security / infra shortlists, "ops console" topics, late-night decision work |
| **playful · light** | bright pop colour-blocks, high-energy | creative hobbies, kids / family, pop-culture, colourful food, anything cheerful |
| **playful · dark** | neon-on-plum, club energy that glows | gaming, music, nightlife, digital art — vivid topics that want to feel after-hours, defaulted dark by day |

To set the default mode, the template's `<html>` tag carries
`data-theme="light"`; change it to `data-theme="dark"` for a dark taste. The
report then **loads in that mode regardless of the reader's OS**; the in-page
toggle still lets the reader flip to the sibling mode (and that choice persists).

**Don't blend skins, don't invent a palette, don't write custom CSS** (no extra
`<style>` rules, no inline `style=`). If you hit a genuine visual need the classes
don't cover, that's a missing class in the skin — surface it as a skill change,
don't hand-roll CSS in one report.

## Step 2 — start from the skin's worked-example template

Each skin ships its **own worked-example template** at
`scripts/templates/<skin>.html` (`editorial.html` / `dossier.html` /
`playful.html`). **Copy the one for the skin you picked** and edit it. It is a
complete, openable, offline file that already carries: the skin's structure (the
template *is* the skin's layout), the skin's css inlined in `<style id="skin">`,
the skin's fonts base64-embedded, `<meta charset>` + viewport, fluid responsive
CSS (`max-width` / `%` / `clamp()` — never a fixed device width), semantic
headings, `alt`/`aria`, focus styles, the theme toggle + no-flash restore, and
every required section filled with worked-example content (placeholder photos you
replace with real base64).

Set the **authored default mode** for your taste first: leave `<html
data-theme="light">` as-is for a light taste, or change it to
`data-theme="dark"` for a dark taste. Then shape the template's structure and
content **within the skin's classes**: rewrite every word, vary the card count,
add / remove / reorder sections, drop the map or near-misses. It carries the usual sections — header,
`#brief`, `#index`, `#map` (conditional, directly after the index), `#top-picks`,
`#near-misses`, Appendices A/B/C, footer. Compose **only from the skin's classes**
— don't add `<style>` rules or inline `style=`, and don't touch the embedded font
`<style>` block.

Because each skin is a different layout system, **don't try to port one skin's
markup into another** — start from the right template and the structure comes for
free.

### Title — the tab carries the question, the `<h1>` carries the skin's voice

- **`<title>` (browser tab)** is the **canonical research question** — plain,
  searchable, no skin name or suffix. This is the one string that identifies the
  report.
- **`<h1>`** may be a **stylised display headline** in the skin's voice
  (editorial and playful lean into a magazine headline; dossier states the
  question plainly) — but it must be *about the same topic* as the `<title>`,
  never a competing or contradictory claim.
- **`.subtitle` / `.sub`** is the **optimization framing** — what you optimized
  for — **not** a reworded restatement of the title. A paraphrased title in
  `.sub` is the double-title bug; don't do it.

So `<title>` and `<h1>` need not be byte-identical, but they must not read as two
different reports. Never leave a skin-name suffix (e.g. `· editorial`) in the
`<title>` — that's a worked-example artifact, not part of a real report.

### Content model

- **Header:** title (the research question), one-line framing, **criteria pills**
  = the query's stated requirements, and the **theme toggle**.
- **Brief:** the user's exact query, verbatim (see below).
- **Index:** a terse table-of-contents of the results (see below).
- **Top picks:** ranked cards, each with one landscape photo, a one-line
  why-pick, **consistent criteria tiles**, an honest caveat, and action links.
  Give each card `id="pick-N"` so the index can link to it. For decision-grade
  recommendations, tiles must carry decision evidence, not generic blurbs:
  quality/fit signal, style/type, why it ranks here, order/action, and caveat as
  appropriate to the brief.
- **Near misses:** lighter cards — photo, why-it's-good, miss-reason, one link.
  Do not reduce near misses to a bullet list when the report is a shortlist.

### Brief — show the query verbatim

Just under the header, the `#brief` section quotes the **user's exact research
query**. Paste it **verbatim — never paraphrase, summarise, or tidy it up**;
its job is to record precisely what was asked so the reader can judge the results
against it. One `<p>` per paragraph of the original. It is styled as a quoted
callout ("what was asked"), visually distinct from the results.

### Index — a table of CONTENTS, not a summary

The `#index` section is a terse, scannable preview that lets the reader sense the
richer cards below — **one row per top pick**, name linking to that card's
anchor. It is **not** a replacement for the cards: include only the **3–5
decision variables that actually decide this topic**, then a one-phrase
*Standout*.

Pick the columns from what the brief optimises for:

- **Hotels:** Region · Drive from London · Food (veg/vegan) · Dogs → *Standout*.
- **Restaurants / burgers:** Location · Style · Quality signal · Order → *Standout*.
- **Keyboards:** Layout · Switches · Price → *Standout*.
- **Software/SaaS:** Price · Platform · Best-for → *Standout*.

Keep cells to a few words; the detail lives in the card. The table scrolls
horizontally on narrow screens, so resist adding a sixth column.

### Light + dark mode — authored default, not OS

The skin you inlined carries both palettes: **light tokens in `:root`** and a
**dark token set** in `:root[data-theme="dark"]`. The mode is chosen entirely by
the `data-theme` attribute — **not** `prefers-color-scheme`. Load precedence is:

1. **The reader's saved choice** — if they have ever clicked the toggle, their
   `localStorage` preference wins (an inline `<head>` script applies it before
   first paint, so there's no flash).
2. **Otherwise the authored default** — the mode you set on `<html data-theme>`.
   This is how a "dark taste" report opens dark in broad daylight.

The header carries a **two-button Light / Dark toggle** (no "System" — the OS
never decides the mode). Clicking flips to the **same skin's sibling mode** and
persists to `localStorage`. You don't design or recompute any of this — every skin
ships a genuine, first-class dark palette already (deep-but-not-black surfaces, an
accent that keeps contrast on dark), AA-checked in both modes.

**Still check both modes render** on your actual content: text contrast ≥ AA,
photos legible, accent visible on each background. If something reads wrong,
you picked the data/photo poorly or edited the skin — re-inline the skin
unchanged rather than tweaking tokens.

### Criteria tiles — keep labels consistent

Derive 3–5 tile labels from the **query's stated requirements** and use the
**same labels on every card** (e.g. for "dog-friendly, veg/vegan, couple, hard
to find" → `Food` / `Dog` / `Couple fit` / `Discovery`; for quality-first
burgers → `Quality signal` / `Style` / `Why it ranks here` / `Order`). Do
**not** let labels drift card-to-card ("Why here" on one, "Social/discovery" on
the next) — that was a real v1 defect.

### Base64 images — discipline + size budget

- **One** curated landscape image per item, with meaningful `alt`.
- **Visually verify every chosen photo before shipping**: correct venue/item,
  not a logo, not a generic storefront unless the brief actually calls for the
  exterior, and not an image-search mismatch. If you cannot verify a photo,
  choose another or record the exception in Appendix C.
- **Resize and compress before inlining** so the file stays sane. Example (macOS):
  ```bash
  sips -s format jpeg -s formatOptions 75 -Z 1100 in.jpg --out out.jpg
  base64 -i out.jpg            # paste into src="data:image/jpeg;base64,...."
  ```
  Target **~1000–1200px wide, JPEG q≈70–80**. Budget the whole file to a few MB,
  not the ~5 MB an un-optimized single-file dump produces. Convert AVIF/WebP
  sources to JPEG so every browser renders them.
- No hotlinks, no local paths — ever.

### Clickable-link convention — one treatment everywhere

Readers must be able to tell at a glance what is clickable. Use **one** treatment
for "this links to an external thing" and apply it everywhere; make static pills
look clearly different so nobody clicks a label expecting a link.

| Element | Looks like | Markup |
| --- | --- | --- |
| **External link** (visit site, source, map link) | accent colour, hover underline, **trailing ↗** | `<a class="ext" …>` or `<a class="button" …>` |
| **Internal jump** (index → card) | accent colour, hover underline, **no ↗** | plain `<a href="#pick-N">` |
| **Static label** (criteria pill, criteria-tile label) | muted, **squared + dashed** border, default cursor, **no underline, no ↗** | `.criteria li`, `.check .label`, or `.tag` |

The `↗` is reserved for links that **leave the page**. Every action button and
every external inline link carries it; internal anchors and static labels never
do. The **one exception** is the map's OSM/Geoapify **attribution credits** —
boilerplate credit links that stay plain (no `↗`), like attribution everywhere on
the web. Do not style the hero/brief requirement pills or the criteria tiles as
accent pills — that was the v1 confusion (some pills were links, some weren't).

### Map — conditional

Render the `MAP` section **only if items have locations/addresses**; delete the
whole `<section id="map">` otherwise (a keyboards report has no map).

**Real map (required when a key is available — needs `GEOAPIFY_API_KEY`).** If
items have locations, you MUST attempt the real map first: check for
`GEOAPIFY_API_KEY` and run `scripts/build_map.py`. Bake in two Geoapify static
maps (one per theme) as base64, so the report stays a single offline file:

1. Build the place list from the located items — one entry per pick:
   `{name, query, rank, kind}` where `query` is the geocoding string, `rank` is
   the marker label (`1`..`N` for top picks, `A`..`D` for near misses), `kind` is
   `top` or `near`.
   - **Get the address from the result's own page — don't geocode a bare name.**
     When you fetch each result's official site for its photo, lift its **official
     postal address (with postcode)** from the same page and use that as `query`.
     Ambiguous names ("The Harper") mis-resolve to the wrong town; a full
     address+postcode geocodes accurately.
   - **Even better, pass coordinates directly.** If the page exposes lat/lng
     (schema.org `LocalBusiness`/`geo` JSON-LD, or a Google-Maps embed), add
     `lat`/`lon` to the entry. `build_map.py` then **skips geocoding entirely** for
     that pin — zero geocoding error. Only fall back to name-only `query` when the
     page gives neither.
2. Run the helper (writes `light.<fmt>`/`dark.<fmt>` for inspection + `map.json`; default `fmt` is `jpeg`):
   ```bash
   python3 scripts/build_map.py --places-file places.json \
     --cache-dir ~/.social-research/searches/<run-dir> --out-dir /tmp/map
   ```
   It geocodes each place (Geoapify, cached in the run dir, **fails loud** on a
   no-match — that place keeps its map link but gets no pin), then renders
   **positron** (light) + **dark-matter** (dark) static maps at `scaleFactor=2`
   with numbered/lettered markers auto-fit to the bounding box.
3. Paste `map.json`'s `light_data_uri` and `dark_data_uri` into the two
   `<img class="map-img light/dark">` `src`s, and its `attribution_html` into the
   `.map-attrib` caption. CSS swaps the image with the active theme. Keep the
   **legend** (top picks 1–N vs near misses A–D) and the `.map-links` list.

**Attribution is required** — render the OSM + Geoapify caption; never strip it.

**Fallback (only when justified).** Use the fallback only when one of these is
true and recorded in Appendix C: no key is available, `build_map.py` prints
`{"fallback": true}`, or specific places fail to geocode after address/postcode
refinement. Delete the `.map-card` block and keep only the **legend** + the
ordered **`.map-links`** list of exact map links. Never fabricate coordinates or
hand-draw a schematic/SVG map — that is not a documented fallback.

## Derive from `report.md` — add fields there first

The HTML must not invent data. If a card needs a field `report.md` doesn't carry
(why-pick line, criteria evidence, caveat, region/distance), **add it to
`report.md` first**, then derive the HTML from it. `report.md` remains the source
of truth.

## Appendices

Appendices default **open** (`<details open>`) — they're part of the report, not
hidden by default. Hold them to the same polish as the main body: the search
itemisation is a real table (right-align counts with `td.num`, a one-line intro
above it), and next steps use the `.next-steps` arrow list, not a bare `<ul>`.

- **Appendix A — searches:** a table of the runs and source counts (from the run
  directories under `~/.social-research/searches/`), with a note on how each run
  was used. Include selected-source status: `queried → results used`, `queried →
  zero relevant results`, or `blocked/error with concrete reason`. Include the
  adversarial research review verdict (`pass`, or user-acknowledged limitations).
- **Appendix B — next steps:** concrete actions to verify or improve the
  shortlist.
- **Appendix C — debug / issues:** required when any technical or process issue
  occurred: credential problems, source failures, fallback paths, map/geocoding
  corrections, QA fixes, or adversarial self-review because a subagent was not
  available. Keep these out of the main recommendation body unless they change
  the recommendation itself.
- **Appendix D — effective cost:** the fully-loaded marginal cost to produce
  this report at standard *paid* rates (the price-floor lens). **Generated, not
  hand-written** — see *Appendix D — effective cost* below.

## Appendix D — effective cost (generated)

Appendix D prices two cost layers and emits a line-itemed total:

1. **Data-vendor API calls** — every HTTP request the CLI made, measured per run
   and priced at standard paid tier (even within a free allowance). Free APIs
   (GitHub, HN, Polymarket) show $0; scraping paths (Reddit fallback, yt-dlp) are
   flagged ToS-risky at service scale, not silently buried as $0.
2. **LLM tokens** — the agent's own real token usage (main agent **and**
   subagents), read from the harness transcript and priced via current
   **OpenRouter** rates, with cache-read / cache-write buckets priced separately
   (cache pricing is the dominant term — do not drop it).

Do **not** hand-write this appendix. Wrap the report with a cost boundary:

```bash
# at report start — records the boundary (harness + session + start time):
BID=$(python3 scripts/cost_report.py begin)

# ... run searches, do the research, build the report ...

# at report end — closes the boundary, writes cost.json + the Appendix D body:
python3 scripts/cost_report.py finish "$BID" \
  --out ~/.social-research/searches/<run-dir>/cost.json \
  --appendix /tmp/appendix_d.html
```

Paste the generated `/tmp/appendix_d.html` body into the Appendix D `<details>`
slot. It is **neutral by contract** — model names and dollars only, never the
session id, file paths, or user identity. The rendered block carries its own
dated OpenRouter + paid-vendor rate snapshot for reproducibility.

> **Boundary mechanism (design default).** The boundary uses explicit
> start/end markers (robust). A report spanning several CLI invocations and many
> agent turns rolls up by **time-window union** under one boundary: every run and
> every agent turn between `begin` and `finish` is summed. If you cannot run
> `begin` first, `cost_report.py report --since <ISO> [--harness …] [--session …]`
> produces the same output for an explicit window.

## Footer — neutral

No agent names, no personal hosts/usernames, no machine paths. The skill is
public. A neutral provenance line (skill name, month/year, photo source) only.

## The validator floor (shared by all three skins)

Whatever skin you pick, `scripts/validate_html_report.py` enforces the same
**mechanical floor** — run it before shipping and it must pass:

- `#brief` (verbatim query), `#index` (links to each `#pick-N`), `#map` directly
  after the index when locations exist, `#top-picks`, `#near-misses`.
- Top-pick cards: each an `<article class="card pick" id="pick-N">` with one
  `data:` image and **3–5 criteria tiles** (`.check` with `.label`/`.val`) whose
  labels are **identical across all cards**.
- Near misses render as `.card.near` cards, never a bullet list.
- Map (when present): `.map-img.light` + `.map-img.dark` (only one shown per
  theme) + `.map-attrib` with OSM + Geoapify; or the documented fallback links.
- Appendices A/B (and C when issues occurred) are **open** `<details>`; Appendix A
  carries the review verdict + selected-source status.
- Every `<img>` is a `data:image/...` URI; no unreplaced placeholders.

The skins differ in *shape*; they do not differ in this floor.

## Before you ship — check

- **One skin, no custom CSS.** You started from one `scripts/templates/<skin>.html`,
  its `reference/styles/<skin>.css` is inlined in `<style id="skin">`, you added
  **no** other `<style>` rules (the font `<style>` block is untouched) and **no**
  inline `style=`; everything is built from the skin's classes.
- Opens offline: no network/local requests (all images **and fonts** are embedded;
  images are `data:` URIs, fonts are base64 `data:font/woff2`).
- **Fonts actually render** — the skin's faces apply (not a system fallback);
  check in the browser.
- Every top-pick and near-miss card has one curated `data:image/...` photo that
  was visually verified as the correct venue/item. If an item genuinely has no
  usable verified photo, log the exception in Appendix C.
- Top-pick cards have 3–5 consistent criteria tiles with the same labels across
  the report.
- Near misses, if present, render as cards with photo, why-it's-good,
  miss-reason, and one link — not a bullet list.
- Fluid at ~375px, ~768px, ~1280px — no horizontal scroll, no fixed device width.
- UTF-8 glyphs (`—`, `≤`, `·`, `↗`) render correctly.
- **Title**: `<title>` is the canonical research question (no skin-name suffix);
  `<h1>` is the same topic in the skin's voice; `.sub` is the optimization
  framing, not a reworded restatement of the title.
- **Brief** shows the query verbatim near the top.
- **Index** table present; each name jumps to its `#pick-N` card.
- **Map (when present) sits directly after the index** — order is header → brief →
  index → map → top picks → near misses → appendices.
- **Light and dark** both legible: the report loads in the **authored default
  mode** you set on `<html data-theme>`, the two-button toggle flips to the
  sibling mode, and the choice persists across reloads.
- **Links consistent**: external = accent + ↗; static pills = muted/squared, no ↗.
- **Appendices A/B open** and polished; Appendix C open when issues occurred.
- **Appendix D** present and open when a cost record was produced: generated by
  `cost_report.py`, showing vendor calls & $, LLM tokens by model/bucket & $
  (incl. subagents + cache breakdown), a total effective $/report, and a dated
  rate snapshot. Neutral (model names + $ only). Delete only if no cost record.
- Source completeness is explicit in Appendix A; no selected source is handwaved
  as “enough” if it failed before a real query.
- Research review verdict is `pass`, or known limitations were acknowledged by
  the user, and the verdict is recorded in Appendix A.
- Map shows with a legend **iff** items have locations. With a key, `map.json`
  exists, `light_data_uri` + `dark_data_uri` are inlined into `.map-img.light` /
  `.map-img.dark`, only one theme map is visible at a time, and OSM + Geoapify
  attribution renders. Fallback states its reason in Appendix C.
- Final QA uses `agent-browser` on the uploaded URL if installed. Bypass only if
  `agent-browser` is missing/fails, and record that reason in Appendix C.
  Required QA evidence: viewport/device, uploaded URL, `scrollWidth <=
  clientWidth`, and screenshots of the top plus map/appendix area.
- Run `python3 scripts/validate_html_report.py <file>`; it must pass.
- Footer is neutral; no personal info anywhere.
