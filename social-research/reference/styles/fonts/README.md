# Embedded fonts — subset woff2 (offline, zero network)

Each skin renders in **real OFL faces**, not system fonts. The faces here are
**latin-subset woff2** that get **base64-embedded** into every report's
`<style>` block, so a finished report opens with *zero* network or local font
requests — the offline single-file contract still holds.

## Which faces each skin uses

| Skin | Faces (all SIL Open Font License 1.1) |
| --- | --- |
| **editorial** | Fraunces (display) · Newsreader (serif body) · IBM Plex Mono (labels/data) |
| **dossier** | IBM Plex Sans (grotesk display+body) · IBM Plex Mono (labels/data) |
| **playful** | Fredoka (rounded display) · Outfit (geometric sans body) · Space Mono (labels) |

IBM Plex Mono is shared by editorial + dossier. Fredoka / Outfit / IBM Plex Sans
are **variable** fonts — one file covers the whole 400–700 weight range, so the
`@font-face` declares a weight *range* (e.g. `font-weight:400 700`).

## The recipe (how these were produced)

Google Fonts already serves **per-unicode-range subsets**; we keep only the
`latin` range block and download its woff2. No `fonttools`/`brotli`/`pyftsubset`
needed — just `curl`. [`../../../scripts/fetch_fonts.py`](../../../scripts/fetch_fonts.py)
reproduces **all seven families** bundled here:

```bash
python3 scripts/fetch_fonts.py reference/styles/fonts/
```

It fetches `https://fonts.googleapis.com/css2?family=<Family>:<axis>&display=swap`
with a browser User-Agent (so Google returns woff2, not ttf), parses the
`/* latin */` `@font-face` block(s), and writes files whose names match exactly
what is committed here:

- **Static** families (IBM Plex Mono) → one file per weight,
  `<Family>-<style>-w<weight>.woff2`.
- **Variable** families return a single file covering their weight range. The
  dedicated variable instances are written `<Family>-<style>.woff2` (declare a
  weight *range* in the `@font-face`, e.g. `font-weight:400 700`); the two
  editorial faces keep a representative weight in the name
  (`<Family>-<style>-w<weight>.woff2`) but still declare a range.

This **directory is the source of truth** for what ships; the script reproduces
equivalent latin subsets with identical filenames (exact bytes can differ slightly
when Google re-serves a different variable instance). To add a family, add it to
`SPECS` in `fetch_fonts.py` and re-run. Confirm the licence is **OFL** before
bundling (Google Fonts lists it per family).

## How they get into a report

The worked-example templates (`scripts/templates/<skin>.html`) already carry the
faces base64-embedded in a dedicated `<style>` block — you don't touch it; you
just fill content. The `@font-face` form is:

```css
@font-face{font-family:'IBM Plex Sans';font-style:normal;font-weight:400 700;
  font-display:swap;
  src:url(data:font/woff2;base64,<BASE64-OF-THE-WOFF2>) format('woff2');}
```

If you ever change a skin's faces, regenerate that base64 block from the woff2 in
this directory (`base64 -i <file>.woff2`) and paste it back into the template's
font `<style>` block. The design layer in `reference/styles/<skin>.css` only
*references* the families by name (via `--display` / `--sans` / `--mono` vars);
it carries no `@font-face` itself.
