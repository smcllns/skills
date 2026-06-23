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

Before a real (non-`--mock`) run, choose sources deliberately from the brief. If a source is in scope, it must end the run in one of three states: **queried with relevant results**, **queried with zero relevant results**, or **blocked with a concrete reason**. Do not handwave a failed source with “other sources were enough” — you cannot know that source would not contribute unless you hit it.

Briefs are not API queries. For decision-grade work, deconstruct a broad brief into a small capped set of targeted searches (see [reference/query-strategy.md](reference/query-strategy.md)); do not feed one long prose string to every source and accept the first thin result.

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

For decision-grade work, treat that list as a catalog, not a mandate. Source fit matters:

- Local food/place recommendations: usually `web`, `reddit`, `tiktok`, `instagram`; add `x` for current chatter/contests/news; use `youtube`/`pinterest` as secondary discovery; run `threads` at most once when relevant; skip `hackernews`, `github`, and `polymarket` unless the brief explicitly needs tech, code, or prediction-market evidence.
- Forecasts, elections, sports, finance/crypto, policy, and entertainment outcomes: include `polymarket` when market odds are decision-relevant.
- Developer/code ecosystem questions: include `github` and `hackernews`.

Limit sources when a narrower run is better:

```bash
python3 scripts/social_research.py "topic" --sources reddit,hackernews,web
```

Use `--lookback-days N`, `--limit N`, or `--output-root /path/to/searches` when needed. Use `--mock` only for local smoke testing.

## Date window — calibrate it, don't guess

The date window is a recency filter; it keeps undated items but drops dated ones
(Reddit/X/YouTube) that fall outside it. The default is `--lookback-days 365`, but
the right window is topic-dependent: evergreen / decision topics ("best sixth
forms", "best keyboards") need a wide window or **none** (rank by relevance),
while fresh-news topics want a narrow one. A too-short window silently discards
collected evidence.

Calibrate before a real run with a couple of cheap probes (~$0.01):

```bash
python3 scripts/social_research.py "topic" --calibrate
```

It probes the sources that actually carry dates (Brave `site:reddit.com`
discovery + web), reports the age spread, and recommends a `--lookback-days`
(or "no window: rank by relevance" when evidence spans years). Pass that value to
the real run. If a run still drops items, the report's Source Coverage flags it
("N collected but dropped as outside the window") — widen and re-run.

## Configuration

Credentials should come from the agent runtime's credential manager or environment variables. As a local-only fallback, `~/.social-research/credentials.local.json` is also loaded. Missing credentials make that source report an error in `raw/<source>.json`; they should not block local smoke tests.

For any real user-requested run, preflight credentials before collecting data: list the selected sources, verify the credential each one needs, and fetch available secrets from the runtime credential manager / 1Password before running. Only proceed with a selected source missing if you explicitly note the omission up front and the remaining sources are sufficient for the task. Never run a broad requested search with all high-value sources unauthenticated and present “no items collected” as a normal result.

For the API keys, logins, and local runtime setup each source needs, read [CREDENTIALS.md](CREDENTIALS.md).

Credential names:

- GitHub: `GITHUB_TOKEN` or an authenticated `gh` CLI.
- X: `X_BEARER_TOKEN`.
- Web: one of `BRAVE_API_KEY`, `SERPER_API_KEY`, `EXA_API_KEY`, or `PARALLEL_API_KEY`.
- TikTok, Instagram, Threads, Pinterest: `SCRAPECREATORS_API_KEY`.
- YouTube: local `yt-dlp` executable.
- Optional HTML-report map: `GEOAPIFY_API_KEY` (used only by `scripts/build_map.py`, not the core search; the report falls back to a location list + links without it). See [HTML_REPORT.md](HTML_REPORT.md).

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

## Decision-grade Recommendation Workflow

Use this workflow when the user will choose between a shortlist, asks for “top/best” recommendations, or wants a shareable/HTML report. Quick lookups and raw evidence dumps can stop at `report.md`.

Each step writes a receipt to the per-report **gate ledger**; the final validator refuses to ship a report whose gates didn't run or didn't pass (see [Release gate ledger](#release-gate-ledger-fail-closed) below). Create the report workspace before preflight:

```bash
RUN=$(mktemp -d "$HOME/.social-research/searches/report-XXXXXX")
LEDGER="$RUN/gate_ledger.jsonl"
```

Individual search CLI runs still create their own evidence dirs; cite those paths in the report workspace rather than treating a search run dir as the final report dir.

1. Resolve scope, then preflight. Clarify any **high-impact ambiguity** (gender, region, audience) with the user *before* spending on research — don't assume. Preflight credentials and selected sources, **and calibrate the date window** (`--calibrate`, see above). In-scope sources must be queried, return zero relevant results, or be marked blocked with a concrete reason. For an HTML report, open a cost boundary now (`python3 scripts/cost_report.py begin`).
   - Write `scope_clarified` once ambiguity is resolved (or a documented assumption is recorded): `python3 scripts/core/gate_ledger.py "$LEDGER" scope_clarified pass --reason "<resolved/assumed>"`.
   - `python3 scripts/cost_report.py preflight --ledger "$LEDGER"` → confirms token capture and writes `cost_capture` (records "unavailable", never `$0`, when there's no token session).
2. Run one broad search (with the calibrated `--lookback-days`) plus targeted follow-up searches where the first pass exposes gaps (regions, candidate names, subtypes, or missing sources).
3. Synthesize a ranked `report.md` source of truth from the evidence. Do not mirror source order or raw engagement counts. Confirm **source sufficiency**: a high-coverage source (YouTube/Reddit/web/X) that came back implausibly thin is a defect until re-probed (see plausibility check below). Write `source_sufficiency pass` once coverage holds, or `fail` to halt/force a draft.
4. Enrich each pick with fields the HTML/report needs: official page, current status/availability when relevant, address/coords if location matters, one visually verified good photo, order/action detail, ranking rationale, caveat, and near-miss reason where relevant.
5. Run an adversarial research review before HTML generation. A fresh subagent reviewer is mandatory for decision-grade work; if none is available, do an adversarial self-review and record that as a major Appendix C issue. Write `adversarial_review pass`, or `fail` when the verdict is `needs fixes`.
6. If the verdict is `needs fixes`, fix collection/ranking/synthesis, or explicitly ask the user to accept a draft. If they accept, write `draft_approved pass` — that, and only that, lets the validator ship a known-limited report. Do not silently continue to HTML.
7. Generate HTML **via [HTML_REPORT.md](HTML_REPORT.md)** (never the generic `markdown-to-html` skill); it prettifies reviewed data, never invents fields. Write `html_report_path pass --evidence "$RUN/report.html"`. Build the real map + verified photos per HTML_REPORT, then write `media_map pass` when the real assets are present or the fallback reason is sanctioned; write `fail` only for unsanctioned/missing media ("speed" does not qualify).
8. Close the cost boundary (`python3 scripts/cost_report.py finish <id> --appendix /tmp/appendix_d.html`) and paste its body into Appendix D. Run the final release gate: `python3 scripts/validate_html_report.py "$RUN/report.html" --ledger "$LEDGER"` — it fails closed if any required receipt is missing or not `pass`. Then run the mechanical HTML QA in [HTML_REPORT.md](HTML_REPORT.md), including `agent-browser` on the uploaded URL when sharing.

Adversarial review template:

```md
## Adversarial research review

Verdict: pass | needs fixes

Findings:
1. ...

Data-source plausibility (per source: is the volume believable?):
- <source>: <count> — plausible? | SUSPECT: <why> → <re-probe/fix>

Required fixes before HTML:
- ...
```

The reviewer attacks research quality, not visual design: brief fit, source completeness, credential/config blockers, stale/closed/availability errors, missed obvious candidates, hype bias, ranking evidence, near-miss explanations, caveats, **data-source plausibility (see below)**, and whether `report.md` contains every field the HTML needs. Append the verdict block to `report.md` so the source of truth carries its own review state.

### Data-source plausibility — mandatory common-sense check

A **surprisingly light signal** from a source is **not** automatically a fact
about the world. This covers three cases, not just empty results:

1. **Zero** — the source returned nothing.
2. **Near-zero** — a handful where you'd expect plenty.
3. **Larger but still surprisingly light** — e.g. 40 results for a topic that
   obviously has thousands; a big-looking number can still be far below reality.

Any of these is just as likely a **defect** as a true absence: a broken/blocked
connection, an over-narrow or over-verbose query, a date window silently dropping
items, misreporting, or simply the **agent being lazy/rushing** (accepting the
first thin pass instead of looking properly). The reviewer must sanity-check each
source's volume against real-world expectations and treat the implausible as
suspect, not settled.

> Example: a YouTube search for "popular mechanical keyboards" returning ~4
> results is not credible — there are obviously thousands of such videos. That is
> a signal the query was too specific, the source/connection failed, a filter
> dropped everything, or you simply didn't look properly — **not** that the topic
> lacks coverage.

When a high-coverage source (YouTube, Reddit, web, X) returns a surprisingly light
signal — zero, near-zero, or just far below what the topic obviously supports —
the verdict is **needs fixes** until you have:

1. **Inspected the raw payload** (`raw/<source>.json`) — did the source actually
   return little, or did normalization/the window drop it? (Source Coverage flags
   window drops; a queried source absent from coverage with no error is a red
   flag.)
2. **Re-probed with a simpler, human-style query** — search the way a person would
   ("mechanical keyboards"), not a 10-word decision sentence.
3. **Checked the date window** (`--calibrate`; widen or use `--lookback-days 0`).

Do not accept "this source had little data" until those are ruled out. The bar is
"did we get the immediately-available data if we just looked properly?"

## Release gate ledger (fail-closed)

The decision-grade gates above are enforced, not trusted. Each writes one line to the per-report ledger `$RUN/gate_ledger.jsonl`; the final `validate_html_report.py --ledger` blocks the report unless every required gate has a `pass` receipt. **A missing receipt counts as a gate that didn't run → blocked.** The required gates (single source of truth: `REQUIRED_RELEASE_GATES` in `scripts/validate_html_report.py`):

| Gate | Written at | Producer |
| --- | --- | --- |
| `scope_clarified` | step 1, ambiguity resolved | `gate_ledger.py "$LEDGER" scope_clarified pass` |
| `cost_capture` | step 1 preflight | `cost_report.py preflight --ledger "$LEDGER"` |
| `source_sufficiency` | step 3, coverage confirmed | `gate_ledger.py "$LEDGER" source_sufficiency pass` |
| `adversarial_review` | step 5 | `gate_ledger.py "$LEDGER" adversarial_review pass` |
| `html_report_path` | step 7, HTML built | `gate_ledger.py "$LEDGER" html_report_path pass --evidence "$RUN/report.html"` |
| `media_map` | step 7, map+photos done | `gate_ledger.py "$LEDGER" media_map pass` |

Write `fail` (with a `--reason`) instead of `pass` when a gate genuinely fails — it blocks the same as a missing receipt, but records why. The one escape hatch is `draft_approved pass`, written only when the user explicitly accepts a known-limited draft; it lets the validator ship past a `needs fixes` review, a non-sanctioned map fallback, or placeholder photos. Status is `pass | fail | skip`; receipts are append-only, latest wins (a re-run can flip `fail` → `pass`).

## V1 Boundaries

Do not add these to v1:

- watchlists or SQLite stores
- comparison/competitor mode
- setup wizard
- browser cookie or keychain extraction
- internal LLM planning/reranking
- quality-nudge UI

Future sources to consider after v1 proves useful: Perplexity, Product Hunt, Wirecutter/NYT Article Search, CNET, PCMag, The Verge, Consumer Reports, G2, Capterra, Trustpilot, Amazon reviews, app store reviews, Steam, Chrome Web Store, GitHub Discussions, Discord exports, Bluesky, Mastodon, LinkedIn, Substack, Medium, podcasts/transcripts, and RSS feeds.
