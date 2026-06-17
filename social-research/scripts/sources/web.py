from __future__ import annotations

import urllib.error

from core.normalize import normalize_items
from core.models import SearchConfig, SourceResult

from .http import get_json, post_json, with_query


class WebAdapter:
    source = "web"

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        if config.config.get("BRAVE_API_KEY"):
            return self._brave(query, window, config)
        if config.config.get("SERPER_API_KEY"):
            return self._serper(query, window, config)
        if config.config.get("EXA_API_KEY"):
            return self._exa(query, window, config)
        if config.config.get("PARALLEL_API_KEY"):
            return self._parallel(query, window, config)
        return SourceResult(self.source, [], [], "configure BRAVE_API_KEY, SERPER_API_KEY, EXA_API_KEY, or PARALLEL_API_KEY")

    def _brave(self, query: str, window, config: SearchConfig) -> SourceResult:
        headers = {"Accept": "application/json", "X-Subscription-Token": str(config.config["BRAVE_API_KEY"])}
        count = min(config.limit, 20)
        url = with_query("https://api.search.brave.com/res/v1/web/search", {"q": query, "count": count, "freshness": f"{window.start}to{window.end}"})
        try:
            data = get_json(url, headers=headers)
        except urllib.error.HTTPError as exc:
            if exc.code != 422:
                raise
            url = with_query("https://api.search.brave.com/res/v1/web/search", {"q": query, "count": count})
            data = get_json(url, headers=headers)
        raws = [
            {
                "id": result.get("url"),
                "title": result.get("title"),
                "snippet": result.get("description"),
                "url": result.get("url"),
                "published_at": result.get("page_age"),
            }
            for result in data.get("web", {}).get("results", [])
        ]
        return SourceResult(self.source, data, normalize_items(self.source, raws))

    def _serper(self, query: str, window, config: SearchConfig) -> SourceResult:
        data = post_json("https://google.serper.dev/search", {"q": query, "num": config.limit}, headers={"X-API-KEY": str(config.config["SERPER_API_KEY"])})
        raws = [{"id": item.get("link"), "title": item.get("title"), "snippet": item.get("snippet"), "url": item.get("link"), "published_at": item.get("date")} for item in data.get("organic", [])]
        return SourceResult(self.source, data, normalize_items(self.source, raws))

    def _exa(self, query: str, window, config: SearchConfig) -> SourceResult:
        data = post_json(
            "https://api.exa.ai/search",
            {"query": query, "numResults": config.limit, "startPublishedDate": f"{window.start}T00:00:00Z", "endPublishedDate": f"{window.end}T23:59:59Z"},
            headers={"x-api-key": str(config.config["EXA_API_KEY"])},
        )
        raws = [{"id": item.get("url"), "title": item.get("title"), "body": item.get("text"), "url": item.get("url"), "published_at": item.get("publishedDate")} for item in data.get("results", [])]
        return SourceResult(self.source, data, normalize_items(self.source, raws))

    def _parallel(self, query: str, window, config: SearchConfig) -> SourceResult:
        data = post_json(
            "https://api.parallel.ai/v1/search",
            {"search_queries": [query], "advanced_settings": {"max_results": config.limit}},
            headers={"Authorization": f"Bearer {config.config['PARALLEL_API_KEY']}"},
        )
        raws = [
            {
                "id": item.get("url"),
                "title": item.get("title"),
                "snippet": ((item.get("excerpts") or [""])[0] or ""),
                "url": item.get("url"),
                "published_at": item.get("publish_date"),
            }
            for item in data.get("results", [])
            if isinstance(item, dict)
        ]
        return SourceResult(self.source, data, normalize_items(self.source, raws))
