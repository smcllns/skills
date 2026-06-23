# Query strategy

Briefs are not API queries. A decision brief can be long and multi-axis; search APIs work best with short, targeted phrases.

## Rules

- Start broad enough to discover candidates, then run targeted follow-ups for the axes that matter.
- Prefer short entity/topic phrases over prose.
- Cap follow-up searches; do not multiply every source by every phrase without a reason.
- Treat source-specific syntax as source-specific. Do not assume one query string is optimal everywhere.

## X search

X uses a query language, not plain web prose.

- Use Full-Archive Search for evergreen research; Recent Search is only last-7-days and does not satisfy decision-grade lookbacks.
- Avoid bare `and`; whitespace already means AND and X may reject bare `and` as ambiguous syntax.
- Quote exact entities when ambiguity matters: `"Example Pack" zipper`, not `Example zipper` (which can match unrelated examples).
- Do not pass long natural-language briefs directly. Decompose them into X-native candidates: quoted event/place names, short intent terms, and explicit location OR groups.
- Use `counts/all` as a cheap preflight for volume/cost and access errors before `search/all`.
- Treat an explicit `total_tweet_count: 0` as zero even if the counts response includes a pagination token; do not burn `search/all` calls on zero-count queries.
- Persist X diagnostics: query sent, count total, search skipped/attempted, and any API error.
- If Full-Archive Search fails, mark X blocked with the API error. Do not silently fall back to Recent Search for an evergreen report.

## Example: local event brief

Brief: `top things to do for a holiday weekend in a metro area`

Better X search intents:

- `"Holiday Name" ("Metro Area" OR "Primary City" OR "Known Nickname") (event OR festival OR brunch OR tickets OR free)`
- `"Named Festival"`
- `"Named Venue" "Holiday Name"`

## Example: product brief

Brief: `best durable commuter backpack with laptop protection and repairable zippers`

Better search intents:

- `durable commuter backpack laptop protection`
- `repairable backpack zippers`
- `"Example Pack" zipper failure`
- `"Example Pack" laptop compartment`
- `"Example Pack" warranty repair`

## Source-specific patterns

### Local food/place recommendations

For local recommendation briefs, source fit matters more than exhaustive source coverage.

- High-value: `web`, `reddit`, `tiktok`, `instagram`.
- Often useful: `x` for current chatter/contests/news.
- Secondary discovery: `youtube`, `pinterest`.
- Usually one quick probe max: `threads`.
- Usually out-of-scope: `hackernews`, `github`, `polymarket`, unless the user explicitly wants tech/code/market signal.

### X search for local recommendations

Use short X-native terms with explicit location groups. Do not pass the whole decision brief.

Better intents:

- `<dish or category> ("City" OR abbreviation)`
- `best <dish or category> ("City" OR abbreviation)`
- `"Named Place" <dish or category>`

Cap X re-probes because rate limits are real. If `counts/all` returns zero for a long/prose query, treat that as query-shape evidence and immediately try a concise source-native query.

### Instagram search

Instagram search works best with caption/hashtag-like phrases.

Better intents:

- `<city> best <item> bakery`
- `<city abbreviation> best pastry bakery`
- `<named place> pastry`

Expect small result sets. Inspect for malformed/off-brief reels before treating Instagram as sufficient.

### TikTok search

TikTok can handle direct local food briefs better than many sources, but short follow-ups improve coverage.

Better intents:

- `best <item> <city>`
- `best <category> <city>`
- `<city> <category> review`

Treat TikTok as high-value for current local food/place recommendations when it returns dated creator posts with engagement.

### YouTube search

Use human video-search phrases. Long decision prose can return zero even when useful videos exist.

Better intents:

- `best <item> <city>`
- `best <category> <city> <qualifier>`
- `<city> food tour <category>`

If long prose returns zero, re-probe once with a short query before declaring YouTube thin.

### Pinterest search

Use Pinterest for visual/listicle discovery and corroboration, not freshness or authoritative ranking.

Better intents:

- `<city> <item> bakery`
- `best <city> <category>`
- `<city> <category> guide`

Undated pins are normal; cite them as discovery evidence only.

### Threads search

Run one short source-native probe when the topic seems conversational. If the API succeeds with zero posts, mark Threads as queried-zero and stop.

Better intents:

- `best <item> <city>`
- `<city> <category>`

### Hacker News, GitHub, and Polymarket source fit

- Hacker News: use for tech/startup/developer discourse; local consumer recommendations are usually low-yield.
- GitHub: use for code, tools, repos, issues, and curated developer lists; local consumer recommendations are usually low-yield.
- Polymarket: use for forecastable outcomes where market odds matter; local restaurant/retail quality recommendations are usually out-of-scope.
