from __future__ import annotations

from .scrapecreators import ScrapeCreatorsSearchAdapter


class ThreadsAdapter(ScrapeCreatorsSearchAdapter):
    source = "threads"
    endpoint = "https://api.scrapecreators.com/v1/threads/search"
    query_param = "query"
    result_keys = ("threads", "posts", "items", "data", "results")
