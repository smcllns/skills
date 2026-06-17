from __future__ import annotations

from .scrapecreators import ScrapeCreatorsSearchAdapter


class InstagramAdapter(ScrapeCreatorsSearchAdapter):
    source = "instagram"
    endpoint = "https://api.scrapecreators.com/v2/instagram/reels/search"
    query_param = "query"
    result_keys = ("reels", "items", "data", "results")
