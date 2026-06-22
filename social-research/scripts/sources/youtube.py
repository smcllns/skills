from __future__ import annotations

import json
import shutil
import subprocess

from core.normalize import normalize_items
from core.models import SearchConfig, SourceResult

from .http import record_external_request


class YouTubeAdapter:
    source = "youtube"

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        if not shutil.which("yt-dlp"):
            return SourceResult(self.source, [], [], "yt-dlp is not installed")
        cmd = ["yt-dlp", "--dump-json", "--flat-playlist", f"ytsearch{config.limit}:{query}"]
        # yt-dlp is a subprocess (not sources.http), so record the scrape call
        # explicitly — otherwise YouTube would vanish from the usage record despite
        # being a flagged ToS-risky path.
        record_external_request()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return SourceResult(self.source, {"stderr": result.stderr}, [], result.stderr.strip() or "yt-dlp failed")
        raw_items = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        raws = [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "description": item.get("description"),
                "url": item.get("webpage_url") or item.get("url"),
                "channel": item.get("channel") or item.get("uploader"),
                "published_at": item.get("upload_date"),
                "view_count": item.get("view_count"),
                "like_count": item.get("like_count"),
                "thumbnail": item.get("thumbnail"),
            }
            for item in raw_items
        ]
        return SourceResult(self.source, raw_items, normalize_items(self.source, raws))
