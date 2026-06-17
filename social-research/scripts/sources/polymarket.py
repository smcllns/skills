from __future__ import annotations

from core.normalize import normalize_items
from core.models import SearchConfig, SourceResult

from .http import get_json, with_query


class PolymarketAdapter:
    source = "polymarket"

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        url = with_query("https://gamma-api.polymarket.com/public-search", {"q": query})
        data = get_json(url)
        results = data.get("events") or data.get("markets") or data.get("results") or []
        raws = [
            {
                "id": item.get("id") or item.get("slug"),
                "title": item.get("title") or item.get("question"),
                "body": item.get("description"),
                "url": item.get("url") or (f"https://polymarket.com/event/{item.get('slug')}" if item.get("slug") else ""),
                "published_at": item.get("createdAt") or item.get("startDate"),
                "volume": item.get("volume"),
                "liquidity": item.get("liquidity"),
            }
            for item in results[: config.limit]
            if isinstance(item, dict)
        ]
        return SourceResult(self.source, data, normalize_items(self.source, raws))
