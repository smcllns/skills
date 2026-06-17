from __future__ import annotations

from datetime import datetime, timezone

from core.normalize import normalize_items
from core.models import SearchConfig, SourceResult

from .http import get_json, with_query


class HackerNewsAdapter:
    source = "hackernews"

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        start_ts = _date_to_unix(window.start)
        end_ts = _date_to_unix(window.end) + 86400
        url = with_query(
            "https://hn.algolia.com/api/v1/search",
            {"query": query, "tags": "story", "numericFilters": f"created_at_i>{start_ts},created_at_i<{end_ts}", "hitsPerPage": config.limit},
        )
        data = get_json(url)
        raws = []
        for hit in data.get("hits", []):
            object_id = hit.get("objectID")
            raws.append(
                {
                    "id": object_id,
                    "title": hit.get("title") or hit.get("story_title"),
                    "url": hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}",
                    "author": hit.get("author"),
                    "created_at": hit.get("created_at"),
                    "points": hit.get("points"),
                    "num_comments": hit.get("num_comments"),
                }
            )
        return SourceResult(self.source, data, normalize_items(self.source, raws))


def _date_to_unix(date_value: str) -> int:
    return int(datetime.fromisoformat(date_value).replace(tzinfo=timezone.utc).timestamp())
