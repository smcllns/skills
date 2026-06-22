from __future__ import annotations

import os
import subprocess

from core.normalize import normalize_items
from core.models import SearchConfig, SourceResult

from .http import get_json, with_query


class GitHubAdapter:
    source = "github"

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        token = _github_token(config.config)
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        url = with_query("https://api.github.com/search/issues", {"q": _issue_search_query(query, window), "sort": "reactions", "order": "desc", "per_page": config.limit})
        data = get_json(url, headers=headers)
        raws = []
        for item in data.get("items", []):
            reactions = item.get("reactions") or {}
            repo_url = item.get("repository_url") or ""
            raws.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "body": item.get("body"),
                    "url": item.get("html_url"),
                    "author": (item.get("user") or {}).get("login"),
                    "repository_url": repo_url.replace("https://api.github.com/repos/", ""),
                    "created_at": item.get("created_at"),
                    "comments": item.get("comments"),
                    "likes": reactions.get("+1", 0),
                }
            )
        return SourceResult(self.source, data, normalize_items(self.source, raws))


def _issue_search_query(query: str, window) -> str:
    if window.is_all_dates():
        return query
    return f"{query} created:>{window.start}"


def _github_token(config: dict) -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or config.get("GITHUB_TOKEN")
    if token:
        return str(token)
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
