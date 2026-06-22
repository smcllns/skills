from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import urllib.error
from typing import Any

from core.normalize import normalize_items
from core.models import SearchConfig, SourceResult

from .http import get_json, with_query


ARCHIVE_START = "2006-03-21T00:00:00Z"
TWEET_FIELDS = "created_at,public_metrics,author_id,entities,referenced_tweets,conversation_id,lang"
EXPANSIONS = "author_id,referenced_tweets.id,attachments.media_keys"
USER_FIELDS = "username,name,verified"
MEDIA_FIELDS = "url,preview_image_url,type,width,height"
BAY_AREA_LOCATION_QUERY = '("Bay Area" OR "San Francisco" OR SF OR Oakland OR Berkeley OR "San Jose")'
DEFAULT_FILTER_QUERY = "-is:retweet"
HOLIDAY_PATTERNS = (
    (r"\bfather(?:'|’)?s\s+day\b", "Father's Day"),
    (r"\bmother(?:'|’)?s\s+day\b", "Mother's Day"),
    (r"\bmemorial\s+day\b", "Memorial Day"),
    (r"\blabor\s+day\b", "Labor Day"),
    (r"\bnew\s+year(?:'|’)?s\s+eve\b", "New Year's Eve"),
    (r"\bthanksgiving\b", "Thanksgiving"),
    (r"\bchristmas\b", "Christmas"),
)
KNOWN_LOCATIONS = {
    "austin": "Austin",
    "berkeley": "Berkeley",
    "boston": "Boston",
    "chicago": "Chicago",
    "denver": "Denver",
    "los angeles": '"Los Angeles"',
    "new york": '"New York"',
    "oakland": "Oakland",
    "portland": "Portland",
    "san diego": '"San Diego"',
    "san francisco": '("San Francisco" OR SF)',
    "san jose": '"San Jose"',
    "seattle": "Seattle",
}
STOPWORDS = {
    "activity",
    "activities",
    "area",
    "best",
    "brunch",
    "dad",
    "dads",
    "do",
    "event",
    "events",
    "families",
    "family",
    "for",
    "in",
    "kid",
    "kids",
    "near",
    "the",
    "thing",
    "things",
    "to",
    "top",
    "weekend",
    "with",
}


class XAdapter:
    source = "x"

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        token = config.config.get("X_BEARER_TOKEN")
        if not token:
            return SourceResult(self.source, [], [], "X_BEARER_TOKEN is not configured")

        headers = {"Authorization": f"Bearer {token}"}
        diagnostics: list[dict[str, Any]] = []
        tweets: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        candidates = _query_candidates(query)
        if not candidates:
            return SourceResult(self.source, {"queries": []}, [], "X query is empty")
        for x_query in candidates:
            diagnostic: dict[str, Any] = {"query": x_query}
            diagnostics.append(diagnostic)
            try:
                counts = _counts_all(x_query, window, headers)
            except urllib.error.HTTPError as exc:
                return _blocked(exc, "counts", raw={"queries": diagnostics}, diagnostic=diagnostic)

            diagnostic["counts"] = counts
            diagnostic["total"] = _total_count(counts)
            if diagnostic["total"] == 0:
                diagnostic["search_skipped"] = "zero_count"
                continue

            try:
                data = _search_all(x_query, window, config.limit - len(tweets), headers)
            except urllib.error.HTTPError as exc:
                return _blocked(exc, "search", raw={"queries": diagnostics}, diagnostic=diagnostic)

            diagnostic["search"] = data
            response_items = data.get("data", [])
            for item in response_items:
                tweet_id = item.get("id")
                if tweet_id in seen_ids:
                    continue
                if tweet_id:
                    seen_ids.add(tweet_id)
                tweets.append(item)
            if response_items or len(tweets) >= config.limit:
                break

        raw = {"queries": diagnostics}
        if diagnostics:
            raw["query"] = diagnostics[0]["query"]
            raw["counts"] = diagnostics[0]["counts"]
        if tweets:
            raw["search"] = {"data": tweets}
        raws = [_raw_tweet(item) for item in tweets]
        return SourceResult(self.source, raw, normalize_items(self.source, raws)[: config.limit])


def _counts_all(query: str, window, headers: dict[str, str]) -> dict[str, Any]:
    return get_json(
        with_query(
            "https://api.twitter.com/2/tweets/counts/all",
            {
                "query": query,
                "granularity": "day",
                **_time_params(window),
            },
        ),
        headers=headers,
    )


def _search_all(query: str, window, limit: int, headers: dict[str, str]) -> dict[str, Any]:
    remaining = max(limit, 1)
    data: dict[str, Any] = {"data": [], "includes": {}, "meta": {}}
    next_token: str | None = None
    while remaining > 0:
        response = get_json(
            with_query(
                "https://api.twitter.com/2/tweets/search/all",
                {
                    "query": query,
                    "max_results": min(max(remaining, 10), 500),
                    "tweet.fields": TWEET_FIELDS,
                    "expansions": EXPANSIONS,
                    "user.fields": USER_FIELDS,
                    "media.fields": MEDIA_FIELDS,
                    "next_token": next_token,
                    **_time_params(window),
                },
            ),
            headers=headers,
        )
        data["data"].extend(response.get("data", []))
        _merge_includes(data["includes"], response.get("includes", {}))
        data["meta"] = response.get("meta", {})
        remaining = limit - len(data["data"])
        next_token = data["meta"].get("next_token")
        if not next_token:
            break
    return data


def _raw_tweet(item: dict[str, Any]) -> dict[str, Any]:
    metrics = item.get("public_metrics") or {}
    tweet_id = item.get("id")
    raw = {
        "id": tweet_id,
        "title": item.get("text"),
        "text": item.get("text"),
        "url": f"https://x.com/i/web/status/{tweet_id}",
        "created_at": item.get("created_at"),
        "likes": metrics.get("like_count"),
        "reposts": metrics.get("retweet_count"),
        "comments": metrics.get("reply_count"),
        "raw": item,
    }
    urls = ((item.get("entities") or {}).get("urls") or []) if isinstance(item.get("entities"), dict) else []
    expanded = [url.get("expanded_url") for url in urls if isinstance(url, dict) and url.get("expanded_url")]
    if expanded:
        raw["expanded_urls"] = expanded
    return raw


def _time_params(window) -> dict[str, str]:
    return {"start_time": _start_time(window.start), "end_time": _end_time(window.end)}


def _start_time(value: str) -> str:
    if value.startswith("0001-"):
        return ARCHIVE_START
    return f"{value}T00:00:00Z" if len(value) == 10 else value


def _end_time(value: str) -> str:
    latest_allowed = _utc_now() - timedelta(seconds=15)
    if value.startswith("9999-"):
        return _iso_z(latest_allowed)
    if len(value) == 10:
        end = datetime.fromisoformat(value).replace(tzinfo=timezone.utc) + timedelta(days=1)
        return _iso_z(min(end, latest_allowed))
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat(timespec="seconds").replace("+00:00", "Z")


def _query_candidates(query: str) -> list[str]:
    sanitized = _sanitize_query(query)
    candidates: list[str] = []
    holiday = _holiday_phrase(query)
    location = _location_query(query)
    event_phrases = _event_phrases(query)

    if event_phrases and holiday:
        candidates.append(f'"{event_phrases[0]}" {holiday}')
    elif event_phrases and _phrase_covers_query(event_phrases[0], sanitized):
        candidates.append(f'"{event_phrases[0]}"')
    if holiday and location:
        candidates.append(" ".join(part for part in (holiday, location, _intent_query(query)) if part))
    if _should_try_sanitized(sanitized):
        candidates.append(sanitized)

    deduped: list[str] = []
    for candidate in candidates or [sanitized]:
        candidate = _with_default_filters(candidate)
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped[:3]


def _sanitize_query(query: str) -> str:
    # X search treats bare "and" as ambiguous operator syntax. Whitespace is AND.
    return re.sub(r"\s+", " ", re.sub(r"(?i)\band\b", " ", query)).strip()


def _with_default_filters(query: str) -> str:
    if not query:
        return query
    return f"{query} {DEFAULT_FILTER_QUERY}"


def _holiday_phrase(query: str) -> str | None:
    for pattern, phrase in HOLIDAY_PATTERNS:
        if re.search(pattern, query, flags=re.IGNORECASE):
            return f'"{phrase}"'
    return None


def _location_query(query: str) -> str | None:
    lower = query.lower()
    if "bay area" in lower:
        return BAY_AREA_LOCATION_QUERY
    if re.search(r"\bsf\b", lower):
        return '("San Francisco" OR SF)'
    for needle, x_query in KNOWN_LOCATIONS.items():
        if needle in lower:
            return x_query
    fallback = _fallback_location_phrase(query)
    if fallback:
        return fallback
    return None


def _fallback_location_phrase(query: str) -> str | None:
    text = query
    for pattern, _phrase in HOLIDAY_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    for token in re.findall(r"[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+", text):
        if token.lower() not in STOPWORDS and token.lower() not in {"june", "jun"}:
            return token
    return None


def _intent_query(query: str) -> str | None:
    terms = {_normalize_term(term) for term in re.findall(r"[A-Za-z0-9À-ÖØ-öø-ÿ'’.-]+", query)}
    if terms & {"activity", "activities", "brunch", "event", "events", "festival", "tickets"}:
        return "(event OR events OR festival OR brunch OR tickets OR free)"
    return None


def _event_phrases(query: str) -> list[str]:
    text = query
    for pattern, _phrase in HOLIDAY_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\bbay\s+area\b", " ", text)
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*|&|\d+", text)
    phrases: list[str] = []
    current: list[str] = []
    for token in tokens:
        if _is_title_token(token):
            current.append(token)
            continue
        if token == "&" and current:
            current.append(token)
            continue
        _append_phrase(phrases, current)
        current = []
    _append_phrase(phrases, current)
    return phrases


def _is_title_token(token: str) -> bool:
    if token.lower() in {"june", "jun"}:
        return False
    return token == "SF" or (token.isupper() and len(token) > 1) or token[:1].isupper()


def _append_phrase(phrases: list[str], tokens: list[str]) -> None:
    cleaned = [token for token in tokens if token != "&"]
    if len(cleaned) < 2:
        return
    phrase = " ".join(cleaned)
    if phrase.lower() not in {"bay area", "san francisco", "san jose"} and phrase not in phrases:
        phrases.append(phrase)


def _phrase_covers_query(phrase: str, query: str) -> bool:
    phrase_terms = {_normalize_term(term) for term in re.findall(r"[A-Za-z0-9À-ÖØ-öø-ÿ'’.-]+", phrase)}
    query_terms = [_normalize_term(term) for term in _content_terms(query)]
    return bool(query_terms) and all(term in phrase_terms for term in query_terms)


def _should_try_sanitized(query: str) -> bool:
    return len(_content_terms(query)) <= 6


def _content_terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[A-Za-z0-9À-ÖØ-öø-ÿ'’.-]+", query) if _normalize_term(term) not in STOPWORDS]


def _normalize_term(term: str) -> str:
    return term.lower().replace("’", "'")


def _total_count(counts: dict[str, Any]) -> int | None:
    meta = counts.get("meta") if isinstance(counts, dict) else None
    if isinstance(meta, dict) and meta.get("total_tweet_count") is not None:
        return int(meta["total_tweet_count"])
    if isinstance(meta, dict) and meta.get("next_token"):
        return None
    data = counts.get("data") if isinstance(counts, dict) else None
    if isinstance(data, list):
        return sum(int(bucket.get("tweet_count") or 0) for bucket in data if isinstance(bucket, dict))
    return None


def _merge_includes(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if isinstance(value, list):
            target.setdefault(key, []).extend(value)
        else:
            target[key] = value


def _blocked(
    exc: urllib.error.HTTPError,
    step: str,
    *,
    raw: dict[str, Any],
    diagnostic: dict[str, Any] | None = None,
) -> SourceResult:
    body = exc.read().decode("utf-8", "replace")[:1000]
    reason = f"X Full-Archive Search failed during {step}: HTTP {exc.code} {exc.reason}: {body}".strip()
    if diagnostic is not None:
        diagnostic["error"] = reason
    return SourceResult("x", raw, [], reason)
