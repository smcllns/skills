from __future__ import annotations

from typing import Any

from .dates import date_only
from .models import MediaItem, SourceItem


def normalize_item(source: str, raw: dict[str, Any], index: int) -> SourceItem:
    source = source.lower()
    media = _media(raw)
    engagement = _engagement(raw)
    return SourceItem(
        id=str(_first(raw, "id", "objectID", "video_id", "pin_id", "aweme_id", "pk") or f"{source}-{index + 1}"),
        source=source,
        title=str(_first(raw, "title", "name", "question", "caption", "description", "text", "desc") or f"{source} item {index + 1}").strip(),
        url=str(_first(raw, "url", "html_url", "link", "share_url", "permalink") or "").strip(),
        body=str(_first(raw, "body", "selftext", "caption", "description", "text", "desc", "snippet") or "").strip(),
        author=_optional_str(_first(raw, "author", "user", "channel", "channel_title", "author_name", "handle")),
        container=_optional_str(_first(raw, "subreddit", "repo", "repository_url", "board", "source_domain")),
        published_at=date_only(_first(raw, "published_at", "created_at", "date", "created_utc", "created_at_i", "taken_at", "create_time")),
        engagement=engagement,
        relevance=_relevance(raw),
        media=media,
        raw=dict(raw),
    )


def normalize_items(source: str, raws: list[dict[str, Any]]) -> list[SourceItem]:
    return [normalize_item(source, raw, index) for index, raw in enumerate(raws) if isinstance(raw, dict)]


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("username") or value.get("login") or value.get("name") or value.get("full_name")
    text = str(value).strip()
    return text or None


def _engagement(raw: dict[str, Any]) -> dict[str, int | float]:
    if isinstance(raw.get("engagement"), dict):
        return {str(key): _number(value) for key, value in raw["engagement"].items() if _number(value) is not None}
    keys = (
        "score",
        "points",
        "num_comments",
        "comment_count",
        "comments",
        "like_count",
        "digg_count",
        "likes",
        "view_count",
        "play_count",
        "views",
        "save_count",
        "saves",
        "share_count",
        "volume",
        "liquidity",
        "reposts",
        "shares",
    )
    out: dict[str, int | float] = {}
    aliases = {
        "view_count": "views",
        "play_count": "views",
        "like_count": "likes",
        "digg_count": "likes",
        "comment_count": "comments",
        "num_comments": "comments",
        "save_count": "saves",
        "share_count": "shares",
    }
    for key in keys:
        number = _number(raw.get(key))
        if number is not None:
            out[aliases.get(key, key)] = number
    return out


def _media(raw: dict[str, Any]) -> list[MediaItem]:
    values: list[Any] = []
    for key in ("thumbnail", "thumbnail_url", "image", "image_url", "cover", "cover_url", "display_url"):
        if raw.get(key):
            values.append(raw[key])
    if isinstance(raw.get("media"), list):
        values.extend(raw["media"])
    items: list[MediaItem] = []
    for value in values:
        if isinstance(value, str):
            items.append(MediaItem(url=value, kind="image", alt=str(raw.get("title") or raw.get("description") or "")))
        elif isinstance(value, dict):
            url = value.get("url") or value.get("src")
            if url:
                items.append(
                    MediaItem(
                        url=str(url),
                        kind=str(value.get("kind") or value.get("type") or "image"),
                        alt=str(value.get("alt") or raw.get("title") or ""),
                    )
                )
    return items


def _number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        text = str(value).replace(",", "").strip()
        return float(text) if "." in text else int(text)
    except ValueError:
        return None


def _relevance(raw: dict[str, Any]) -> float:
    value = _first(raw, "relevance", "score_hint")
    return float(value) if value is not None else 0.5
