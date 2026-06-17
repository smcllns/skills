from __future__ import annotations

import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import SourceItem


TRACKING_PARAMS = {"fbclid", "gclid"}
STOPWORDS = {
    "about",
    "best",
    "from",
    "good",
    "near",
    "that",
    "this",
    "what",
    "when",
    "where",
    "with",
}


def dedupe_and_rank(items: list[SourceItem], query: str | None = None) -> list[SourceItem]:
    best_by_key: dict[str, SourceItem] = {}
    for item in items:
        if query:
            item.relevance = query_relevance(query, item)
        item.score = score_item(item)
        key = dedupe_key(item)
        if key not in best_by_key or item.score > best_by_key[key].score:
            best_by_key[key] = item
    return sorted(best_by_key.values(), key=lambda item: item.score, reverse=True)


def score_item(item: SourceItem) -> float:
    engagement = sum(max(0.0, float(value)) for value in item.engagement.values())
    relevance = max(0.0, min(1.0, float(item.relevance)))
    source_weight = {
        "reddit": 1.15,
        "hackernews": 1.1,
        "github": 1.0,
        "youtube": 1.0,
        "x": 0.95,
        "web": 0.9,
        "polymarket": 0.9,
    }.get(item.source, 0.85)
    text_bonus = min(0.2, len((item.title + " " + item.body).split()) / 250)
    relevance_factor = relevance if relevance > 0 else 0.01
    return round(relevance_factor * (1.0 + math.log1p(engagement) / 3 + text_bonus) * source_weight, 4)


def query_relevance(query: str, item: SourceItem) -> float:
    tokens = _query_tokens(query)
    if not tokens:
        return item.relevance
    text = " ".join([item.title, item.body, item.url, item.author or "", item.container or ""]).lower()
    matched = sum(1 for token in tokens if re.search(rf"\b{re.escape(token)}s?\b", text))
    return round(matched / len(tokens), 4)


def dedupe_key(item: SourceItem) -> str:
    if item.url:
        return _canonical_url(item.url)
    return f"{item.source}:{item.id}".lower()


def _canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query)
            if key not in TRACKING_PARAMS and not key.startswith("utm")
        ]
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def _query_tokens(query: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) < 3 or token in STOPWORDS:
            continue
        if len(token) > 3 and token.endswith("s"):
            token = token[:-1]
        if token not in tokens:
            tokens.append(token)
    return tokens
