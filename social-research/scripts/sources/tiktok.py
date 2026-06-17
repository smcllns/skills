from __future__ import annotations

from .scrapecreators import ScrapeCreatorsSearchAdapter


class TikTokAdapter(ScrapeCreatorsSearchAdapter):
    source = "tiktok"
    endpoint = "https://api.scrapecreators.com/v1/tiktok/search/keyword"
    query_param = "query"
    result_keys = ("search_item_list", "videos", "items", "data", "results")
