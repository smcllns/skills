---
name: social-research
description: Runs a search across social sources like Reddit, Hacker News, GitHub, YouTube, X, web (Brave), Polymarket, TikTok, Instagram, Threads, and Pinterest. Use when asked to research or find the best or popular options for something to enhance web search with what people are saying on that topic across social channels.
---

# Social Research

Use the bundled CLI to collect recent evidence for one topic, normalize the results, and save the raw payloads plus a markdown report.

## Quick Start

Run from the skill directory:

```bash
python3 scripts/social_research.py "topic to research"
```

The CLI prints the saved search directory. Every run writes:

```text
~/.social-research/searches/<timestamp>-<slug>/
  query.json
  raw/<source>.json
  normalized.json
  report.md
```

Keep search directories forever by default. Do not auto-clean old runs.

## Source Selection

Default sources:

- `reddit`
- `hackernews`
- `github`
- `youtube`
- `x`
- `web`
- `polymarket`
- `tiktok`
- `instagram`
- `threads`
- `pinterest`

Limit sources when a narrower run is better:

```bash
python3 scripts/social_research.py "topic" --sources reddit,hackernews,web
```

Use `--lookback-days N`, `--limit N`, or `--output-root /path/to/searches` when needed. Use `--mock` only for local smoke testing.

## Configuration

Credentials should come from the agent runtime's credential manager or environment variables. As a local-only fallback, `~/.social-research/credentials.local.json` is also loaded. Missing credentials make that source report an error in `raw/<source>.json`; they should not block the whole search.

For the API keys, logins, and local runtime setup each source needs, read [CREDENTIALS.md](CREDENTIALS.md).

Credential names:

- GitHub: `GITHUB_TOKEN` or an authenticated `gh` CLI.
- X: `X_BEARER_TOKEN`.
- Web: one of `BRAVE_API_KEY`, `SERPER_API_KEY`, `EXA_API_KEY`, or `PARALLEL_API_KEY`.
- TikTok, Instagram, Threads, Pinterest: `SCRAPECREATORS_API_KEY`.
- YouTube: local `yt-dlp` executable.

Reddit tries public JSON first, then uses `BRAVE_API_KEY` for Brave `site:reddit.com` discovery plus `old.reddit.com` HTML scraping when Reddit blocks JSON. Hacker News and Polymarket use public unauthenticated endpoints.

## Report Expectations

Use `report.md` as the user-facing artifact. It contains:

- query and date window
- source coverage
- top findings with links and engagement signals
- short quoted evidence
- useful source media/images when present
- raw artifact path

Use `normalized.json` when another tool needs structured evidence. Use `raw/*.json` when debugging a source or verifying provenance.

For an optional shareable single-file HTML version of a finished search, see [HTML_REPORT.md](HTML_REPORT.md).

## V1 Boundaries

Do not add these to v1:

- watchlists or SQLite stores
- comparison/competitor mode
- setup wizard
- browser cookie or keychain extraction
- internal LLM planning/reranking
- quality-nudge UI

Future sources to consider after v1 proves useful: Perplexity, Product Hunt, Wirecutter/NYT Article Search, CNET, PCMag, The Verge, Consumer Reports, G2, Capterra, Trustpilot, Amazon reviews, app store reviews, Steam, Chrome Web Store, GitHub Discussions, Discord exports, Bluesky, Mastodon, LinkedIn, Substack, Medium, podcasts/transcripts, and RSS feeds.
