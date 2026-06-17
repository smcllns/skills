from __future__ import annotations

from .scrapecreators import ScrapeCreatorsSearchAdapter


class PinterestAdapter(ScrapeCreatorsSearchAdapter):
    source = "pinterest"
    endpoint = "https://api.scrapecreators.com/v1/pinterest/search"
    query_param = "query"
    result_keys = ("pins", "items", "data", "results")
