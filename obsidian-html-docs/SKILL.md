---
name: obsidian-html-docs
description: "Use when creating .html docs intended to render inline in Obsidian with the HTML Docs plugin (github.com/smcllns/obsidian-plugin-html-docs)."
---

# Obsidian HTML Docs authoring guide

The [HTML Docs plugin](https://community.obsidian.md/account/plugins/html-docs) for Obsidian renders each `.html` file in a sandboxed iframe via Blob URL. No `allow-same-origin`, no vault path resolution, no storage. Author within that envelope.

## Linking and embedding

Wikilinks need the explicit `.html` extension; embeds take an optional `|WxH` (standard Obsidian embed-sizing syntax — also supports `|width` for proportional scaling, see [Obsidian docs](https://help.obsidian.md/Linking+notes+and+files/Embed+files)):

```markdown
[[my-doc.html]]            <- link
![[doc.html|600x400]]      <- embed
```

Default embed height ≈ 600px; tab views fill the pane.

## What works in the HTML page

**Works:**

- HTML / CSS (grid, `light-dark()`, animations, SVG)
- JavaScript (ES2020+, fetch with CORS, `requestAnimationFrame`, Canvas 2D)
- Forms
- `window.parent.postMessage(msg, '*')`
- Anchor links and the History API
- HTTPS resources (images, fonts, stylesheets)
- `data:` URLs and inline SVG

**Blocked:**

- `localStorage` / `sessionStorage` / `IndexedDB` / `document.cookie` — use URL hash or `postMessage` for state
- Reading `window.parent.*` — cross-origin (`postMessage` still works)
- Top-level navigation — links inside the page can't redirect Obsidian itself; use `target="_blank"` to open externally
- Clipboard API — programmatic `navigator.clipboard.*` is blocked, but users can still select text and copy with ⌘C
- Service workers, geolocation, notifications
- Vault-relative URLs (see Assets)

## Assets

| Source | Works? |
|---|---|
| `attachments/foo.png` or any vault-relative path | **No** — fails silently |
| Inline `<svg>` | Yes |
| `data:` URL | Yes |
| HTTPS URL (image, font, stylesheet) | Yes — CORS permitting |
| Obsidian theme / CSS | Yes — via injected theme tokens (see below) |

Inline SVG or `data:` URL for small graphics. Host photos externally (R2/CDN). Never reference the vault.

## Theme tokens

Before loading the Blob, the plugin injects a `<style>` snapshot of Obsidian's current theme. Open docs re-render on theme change.

Default to these for vault-native docs, with `light-dark()` fallbacks so the file still works when opened outside Obsidian:

```css
:root {
  color-scheme: light dark;
  --bg:   var(--obsidian-bg,   light-dark(#ffffff, #0e1014));
  --text: var(--obsidian-text, light-dark(#16161a, #e7e9ec));
}
```

For a specific aesthetic (brand palette, brutalist, retro), design freely — Obsidian context is a hint, not a constraint. Full token list in the appendix.

## Appendix: injected theme tokens

| Token | Purpose |
|---|---|
| `--obsidian-color-scheme` | `light` or `dark` (also sets `color-scheme:` on `:root`) |
| `--obsidian-bg`, `--obsidian-bg-2` | Background surfaces |
| `--obsidian-text`, `--obsidian-text-muted` | Text colors |
| `--obsidian-accent` | Accent |
| `--obsidian-border` | Borders |
| `--obsidian-font`, `--obsidian-font-mono` | Font stacks |
