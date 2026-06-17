from __future__ import annotations

from core.normalize import normalize_items
from core.models import SearchConfig, SourceResult

from .http import get_json, with_query


class XAdapter:
    source = "x"

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        token = config.config.get("X_BEARER_TOKEN")
        if not token:
            return SourceResult(self.source, [], [], "X_BEARER_TOKEN is not configured")
        url = with_query(
            "https://api.twitter.com/2/tweets/search/recent",
            {
                "query": query,
                "max_results": min(max(config.limit, 10), 100),
                "tweet.fields": "created_at,public_metrics,author_id",
            },
        )
        data = get_json(url, headers={"Authorization": f"Bearer {token}"})
        raws = []
        for item in data.get("data", []):
            metrics = item.get("public_metrics") or {}
            tweet_id = item.get("id")
            raws.append(
                {
                    "id": tweet_id,
                    "title": item.get("text"),
                    "text": item.get("text"),
                    "url": f"https://x.com/i/web/status/{tweet_id}",
                    "created_at": item.get("created_at"),
                    "likes": metrics.get("like_count"),
                    "reposts": metrics.get("retweet_count"),
                    "comments": metrics.get("reply_count"),
                }
            )
        return SourceResult(self.source, data, normalize_items(self.source, raws))
