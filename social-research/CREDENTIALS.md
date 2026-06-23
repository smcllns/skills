# Social Research Credentials

This file documents what each source needs. Do not store secret values here.

## Setup

- **Requirements:** Python 3.9+ (verified on 3.9.6 and 3.10). No third-party dependencies are required — the CLI runs on the standard library.
- **Install & run:** copy/clone this skill, then run from the skill directory: `python3 scripts/social_research.py "topic to research"`.
- **Output location:** every run writes to `~/.social-research/searches/<timestamp>-<slug>/` (creates `~/.social-research/` in your home directory). Searches are kept forever by default; nothing is auto-cleaned.
- **SSL cert errors (common on a fresh macOS Python):** if a run fails with SSL certificate verification errors, point Python at certifi's bundle with `export SSL_CERT_FILE=$(python3 -m certifi)`, or run the macOS "Install Certificates.command" that ships with python.org Python. `certifi` is an optional soft fallback only; the CLI still has zero required dependencies.

## Runtime Install

- YouTube requires `yt-dlp` on `PATH`.
- Install with Homebrew: `brew install yt-dlp`.
- Do not install with `pip`.

## Credentials

Preferred order:

1. Use the credential manager provided by your agent runtime.
2. Export short-lived environment variables for the command.
3. As a local-only fallback, put secrets in `~/.social-research/credentials.local.json`.

For real user-requested research, preflight credentials for the selected sources before running. Missing credentials are acceptable for `--mock` and local smoke tests; for decision-grade runs, fetch available keys first or explicitly record the blocked source before proceeding.

GitHub also accepts `gh auth token`, so a working authenticated `gh` CLI is enough for that source.

## Sources

| Source | Required setup | Notes |
|---|---|---|
| `reddit` | `BRAVE_API_KEY` for fallback | Tries Reddit public JSON search first. If Reddit blocks or rate-limits JSON (`403` or `429`), falls back to Brave `site:reddit.com` discovery and scrapes matched threads through `old.reddit.com` HTML. Reliable official Reddit coverage still needs a future OAuth/API-backed adapter and a Reddit app credential. |
| `hackernews` | none | Uses Algolia HN search. |
| `github` | `GITHUB_TOKEN` or `gh auth token` | Searches GitHub issues/PRs. |
| `youtube` | `yt-dlp` | No API key. Search quality depends on YouTube allowing local `yt-dlp` search. |
| `x` | `X_BEARER_TOKEN` | Uses X API v2 Full-Archive Search (`search/all`) plus `counts/all` preflight for evergreen research. The token's X developer project must have access to those endpoints. |
| `web` | one of `BRAVE_API_KEY`, `SERPER_API_KEY`, `EXA_API_KEY`, `PARALLEL_API_KEY` | Uses the first configured web-search provider in that order. |
| `polymarket` | none | Uses Polymarket public Gamma API. |
| `tiktok` | `SCRAPECREATORS_API_KEY` | Uses ScrapeCreators. |
| `instagram` | `SCRAPECREATORS_API_KEY` | Uses ScrapeCreators Instagram reels search. |
| `threads` | `SCRAPECREATORS_API_KEY` | Uses ScrapeCreators. A successful call may still return zero posts for narrow local queries. |
| `pinterest` | `SCRAPECREATORS_API_KEY` | Uses ScrapeCreators. |

## Map (HTML report, optional)

| Capability | Required setup | Notes |
|---|---|---|
| Report map | `GEOAPIFY_API_KEY` | Only used by the optional HTML report (`scripts/build_map.py`), not the core search. Geocodes the shortlisted places and renders two static maps (positron + dark-matter) baked into the report as base64. Free tier is **3,000 credits/day** — a report uses ~5–9 geocodes + 2 static maps, comfortably free. Get a key at [geoapify.com](https://www.geoapify.com/) (sign up → create a project → copy its API key). **Without the key the report still builds** — it falls back to the ordered location list + map links. The rendered map **requires attribution**: keep the "© OpenStreetMap contributors · Powered by Geoapify" caption; do not strip it. |

## Local Test Command

```bash
set +x
export BRAVE_API_KEY="<brave-search-api-key>"
export SCRAPECREATORS_API_KEY="<scrapecreators-api-key>"
export X_BEARER_TOKEN="<x-api-bearer-token>"

python3 scripts/social_research.py \
  "best taco trucks in San Mateo California" \
  --lookback-days 365 \
  --limit 25
```

Equivalent local-only fallback in `~/.social-research/credentials.local.json`:

```json
{
  "BRAVE_API_KEY": "<brave-search-api-key>",
  "SCRAPECREATORS_API_KEY": "<scrapecreators-api-key>",
  "X_BEARER_TOKEN": "<x-api-bearer-token>"
}
```
