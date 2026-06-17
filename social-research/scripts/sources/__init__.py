from __future__ import annotations

from .github import GitHubAdapter
from .hackernews import HackerNewsAdapter
from .instagram import InstagramAdapter
from .pinterest import PinterestAdapter
from .polymarket import PolymarketAdapter
from .reddit import RedditAdapter
from .threads import ThreadsAdapter
from .tiktok import TikTokAdapter
from .web import WebAdapter
from .x import XAdapter
from .youtube import YouTubeAdapter


def default_adapters():
    return {
        "reddit": RedditAdapter(),
        "hackernews": HackerNewsAdapter(),
        "github": GitHubAdapter(),
        "youtube": YouTubeAdapter(),
        "x": XAdapter(),
        "web": WebAdapter(),
        "polymarket": PolymarketAdapter(),
        "tiktok": TikTokAdapter(),
        "instagram": InstagramAdapter(),
        "threads": ThreadsAdapter(),
        "pinterest": PinterestAdapter(),
    }
