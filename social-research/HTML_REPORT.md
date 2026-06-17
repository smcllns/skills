# HTML Report (v2 polish)

An optional, shareable HTML version of a finished search. It is **derived from
`report.md`** — `report.md` stays the raw artifact; the HTML is a curated,
designed view of the same findings. Read this only when producing an HTML report.

## When to produce it

- The user asks for a shareable / pretty / sendable version of the findings, or
- the shortlist is decision-grade (a handful of picks the user will choose between)
  and a single self-contained file is more useful than markdown.

Skip it for quick lookups or raw evidence dumps — `report.md` is enough.

## Output contract (locked)

- **One self-contained `.html` file.** It must open with **zero network or local
  dependencies** — no hotlinked images, no `./..._files/` paths, no CDN fonts.
- **Images are base64 data-URIs**, inlined directly in `<img src="data:...">`.
- **System fonts only** — because there are no network deps, you cannot load web
  fonts. Personality comes from type *treatment* (scale, weight, case, color),
  not exotic faces.
- **Light *and* dark mode**, defaulting to the OS preference (see below).

## Step 1 — design the visuals (do a real design pass)

Before touching the template, design a fresh visual identity for *this* report's
subject — this is the fix for "the report looks templated." If a design skill is
available, use it: Anthropic's official **`frontend-design`** plugin
(`frontend-design:frontend-design`, from the `claude-plugins-official`
marketplace) is purpose-built for this and recommended. It is optional and not
bundled with this skill — if it isn't installed, apply the same principles
yourself using the guidance below. Either way, produce and then apply:

- a 4–6 colour named-hex **palette** — **and a genuine dark variant of it** (see
  *Light + dark mode* below), not a mechanical inversion,
- a deliberate **display + body + utility** type pairing (system stacks),
- a **type scale** and **spacing rhythm**,
- **one topic-specific aesthetic risk** you can justify from the subject matter.

Ground every choice in the subject's own world (a hotels report and a keyboards
report must not look alike). Avoid the three AI defaults (cream+serif+terracotta;
near-black+acid-green; broadsheet hairlines).

> The template at `scripts/templates/report_template.html` is a **structural
> skeleton**, not a skin. Its neutral default styling MUST be overridden — shipping
> it unchanged reintroduces the templated look. Override the `:root` design tokens
> (and marker/map styling) with the direction from your design pass.

## Step 2 — fill the template

`scripts/templates/report_template.html` has commented slots: `HEADER`,
`TOP_PICKS`, `NEAR_MISSES`, `MAP` (conditional), `APPENDIX_A`, `APPENDIX_B`,
`FOOTER`, plus one worked example card. It already bakes in `<meta charset>` +
viewport, fluid responsive CSS (`max-width` / `%` / `clamp()` — never a fixed
device width), semantic headings, `alt`/`aria`, and focus styles.

### Content model

- **Header:** title (the research question), one-line framing, **criteria pills**
  = the query's stated requirements, and the **theme toggle**.
- **Brief:** the user's exact query, verbatim (see below).
- **Index:** a terse table-of-contents of the results (see below).
- **Top picks:** ranked cards, each with one landscape photo, a one-line
  why-pick, **consistent criteria tiles**, an honest caveat, and action links.
  Give each card `id="pick-N"` so the index can link to it.
- **Near misses:** lighter cards — photo, why-it's-good, miss-reason, one link.

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
- **Keyboards:** Layout · Switches · Price → *Standout*.
- **Software/SaaS:** Price · Platform · Best-for → *Standout*.

Keep cells to a few words; the detail lives in the card. The table scrolls
horizontally on narrow screens, so resist adding a sixth column.

### Light + dark mode

The template ships **light tokens in `:root`** and a **dark token set** applied
two ways: `@media (prefers-color-scheme: dark)` (unless the reader forced light)
and `:root[data-theme="dark"]`. A **light / system / dark** segmented toggle in
the header overrides the OS default and **persists to `localStorage`**; an inline
`<head>` script restores the choice before first paint (no flash).

Design a **real dark palette** in your design pass — recompute every token
(deep-but-not-black surfaces, raised cards, an accent that keeps contrast on
dark), don't just invert the light one. The header is tokenised (`--header-bg`,
`--header-ink`, `--header-sub`, `--header-line`) so it reads correctly in both
modes; `--btn-ink` is the text colour on a filled accent button. **Check both
modes**: text contrast ≥ AA, photos still legible, accent visible on each
background.

### Criteria tiles — keep labels consistent

Derive the tile labels from the **query's stated requirements** and use the
**same labels on every card** (e.g. for "dog-friendly, veg/vegan, couple, hard
to find" → `Food` / `Dog` / `Couple fit` / `Discovery`). Do **not** let labels
drift card-to-card ("Why here" on one, "Social/discovery" on the next) — that
was a real v1 defect.

### Base64 images — discipline + size budget

- **One** curated landscape image per item, with meaningful `alt`.
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
do. Do not style the hero/brief requirement pills or the criteria tiles as accent
pills — that was the v1 confusion (some pills were links, some weren't).

### Map — conditional

Render the `MAP` section **only if items have locations/addresses**; delete the
whole `<section id="map">` otherwise (a keyboards report has no map). When shown:
a basic schematic with a **legend** (top picks vs near misses) and a fallback
list of exact map links. Keep it schematic — don't fabricate precise
coordinates. (A richer map is a separate roadmap item.)

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
  was used.
- **Appendix B — next steps:** concrete actions to verify or improve the
  shortlist.

## Footer — neutral

No agent names, no personal hosts/usernames, no machine paths. The skill is
public. A neutral provenance line (skill name, month/year, photo source) only.

## Before you ship — check

- Opens offline: no network/local requests (all images are `data:` URIs).
- Fluid at ~375px, ~768px, ~1280px — no horizontal scroll, no fixed device width.
- UTF-8 glyphs (`—`, `≤`, `·`, `↗`) render correctly.
- **Brief** shows the query verbatim near the top.
- **Index** table present; each name jumps to its `#pick-N` card.
- **Light and dark** both legible (toggle works, persists, system default works).
- **Links consistent**: external = accent + ↗; static pills = muted/squared, no ↗.
- **Appendices open** and polished.
- Map shows with a legend **iff** items have locations.
- Footer is neutral; no personal info anywhere.
