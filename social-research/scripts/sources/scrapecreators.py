from __future__ import annotations

from core.normalize import normalize_items
from core.models import SearchConfig, SourceResult

from .http import get_json, with_query


class ScrapeCreatorsSearchAdapter:
    source = ""
    endpoint = ""
    query_param = "keyword"
    result_keys: tuple[str, ...] = ("items", "data", "results")

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        token = config.config.get("SCRAPECREATORS_API_KEY")
        if not token:
            return SourceResult(self.source, [], [], "SCRAPECREATORS_API_KEY is not configured")
        url = with_query(self.endpoint, {self.query_param: query})
        data = get_json(url, headers={"Accept": "application/json", "x-api-key": str(token)})
        raw_items = self._items(data)[: config.limit]
        return SourceResult(self.source, data, normalize_items(self.source, raw_items))

    def _items(self, data):
        for key in self.result_keys:
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, list):
                return [self._prepare_item(item) for item in value]
        return []

    def _prepare_item(self, item):
        if isinstance(item, dict) and isinstance(item.get("aweme_info"), dict):
            item = item["aweme_info"]
        if not isinstance(item, dict):
            return item
        prepared = dict(item)
        stats = prepared.get("statistics")
        if isinstance(stats, dict):
            for key in ("digg_count", "comment_count", "play_count", "share_count"):
                if key in stats and key not in prepared:
                    prepared[key] = stats[key]
        if self.source == "instagram":
            code = prepared.get("shortcode") or prepared.get("code")
            if code and not prepared.get("url"):
                prepared["url"] = f"https://www.instagram.com/reel/{code}/"
        return prepared
