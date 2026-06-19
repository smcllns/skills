from __future__ import annotations

import html
import http.client
import re
import urllib.error
from urllib.parse import urlsplit, urlunsplit

from core.normalize import normalize_items
from core.models import SearchConfig, SourceResult

from .http import get_json, get_text, with_query


OLD_REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}


class RedditAdapter:
    source = "reddit"

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        url = with_query("https://www.reddit.com/search.json", {"q": query, "sort": "relevance", "t": _reddit_time_bucket(config.lookback_days), "limit": config.limit, "raw_json": 1})
        try:
            data = get_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code not in (403, 429):
                raise
            return self._brave_old_reddit_fallback(query, config, str(exc))
        raws = _json_posts(data)
        return SourceResult(self.source, data, normalize_items(self.source, raws))

    def _brave_old_reddit_fallback(self, query: str, config: SearchConfig, json_error: str) -> SourceResult:
        token = config.config.get("BRAVE_API_KEY")
        if not token:
            return SourceResult(self.source, {"mode": "json_blocked", "json_error": json_error}, [], "Reddit JSON is blocked and BRAVE_API_KEY is not configured")

        search_url = with_query("https://api.search.brave.com/res/v1/web/search", {"q": f"site:reddit.com {query}", "count": min(config.limit, 20)})
        discovery = get_json(search_url, headers={"Accept": "application/json", "X-Subscription-Token": str(token)})
        threads = []
        seen_urls: set[str] = set()
        for result in (discovery.get("web", {}) or {}).get("results", []):
            reddit_url = _reddit_thread_url(result.get("url") or "")
            if not reddit_url or reddit_url in seen_urls:
                continue
            seen_urls.add(reddit_url)
            old_url = _old_reddit_url(reddit_url)
            try:
                page = get_text(old_url, headers=OLD_REDDIT_HEADERS)
            except (urllib.error.URLError, TimeoutError, UnicodeError, OSError, http.client.HTTPException):
                continue
            parsed = _parse_old_reddit_thread(page, reddit_url, old_url, result)
            if parsed:
                threads.append(parsed)
            if len(threads) >= config.limit:
                break

        raw = {"mode": "brave_old_reddit_fallback", "json_error": json_error, "discovery": discovery, "threads": threads}
        if not threads:
            return SourceResult(self.source, raw, [], "Reddit JSON is blocked and old Reddit fallback found no parseable threads")
        return SourceResult(self.source, raw, normalize_items(self.source, threads))


def _reddit_time_bucket(days: int) -> str:
    if days <= 0:
        return "all"  # no window: widest Reddit bucket, don't re-narrow to a week
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    if days <= 366:
        return "year"
    return "all"  # multi-year windows exceed Reddit's "year" bucket


def _json_posts(data):
    raws = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data") or {}
        permalink = post.get("permalink") or ""
        raws.append(
            {
                "id": post.get("id"),
                "title": post.get("title"),
                "selftext": post.get("selftext"),
                "url": f"https://www.reddit.com{permalink}" if permalink else post.get("url"),
                "author": post.get("author"),
                "subreddit": post.get("subreddit"),
                "created_utc": post.get("created_utc"),
                "score": post.get("score"),
                "num_comments": post.get("num_comments"),
            }
        )
    return raws


def _reddit_thread_url(url: str) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.netloc.endswith("reddit.com") or "/comments/" not in parts.path:
        return None
    path_parts = [part for part in parts.path.split("/") if part]
    if len(path_parts) < 4 or path_parts[0].lower() != "r" or path_parts[2].lower() != "comments":
        return None
    thread_parts = path_parts[:5] if len(path_parts) >= 5 else path_parts[:4]
    return urlunsplit(("https", "www.reddit.com", f"/{'/'.join(thread_parts)}/", "", ""))


def _old_reddit_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(("https", "old.reddit.com", parts.path, "", ""))


def _parse_old_reddit_thread(page: str, reddit_url: str, scraped_url: str, discovery: dict) -> dict | None:
    title = _first_title(page)
    if not title:
        return None
    comments = _comments(page)
    discovery_description = _clean_html(str(discovery.get("description") or ""))
    body_parts = [discovery_description, _post_body(page), *[comment["body"] for comment in comments[:5]]]
    return {
        "id": _match(page, r'data-fullname="t3_([^"]+)"') or reddit_url,
        "title": title,
        "body": "\n\n".join(part for part in body_parts if part),
        "url": reddit_url,
        "author": _match(page, r'<a[^>]*class="author[^"]*"[^>]*>(.*?)</a>'),
        "subreddit": _subreddit(reddit_url, page),
        "created_at": _match(page, r'<time[^>]+datetime="([^"]+)"'),
        "score": _number(_match(page, r'data-score="([^"]+)"')),
        "num_comments": _number(_match(page, r'data-comments-count="([^"]+)"')) or len(comments),
        "comments": comments,
        "scraped_url": scraped_url,
        "discovery": {
            "title": _clean_html(str(discovery.get("title") or "")),
            "url": discovery.get("url"),
            "description": discovery_description,
        },
    }


def _first_title(page: str) -> str:
    match = re.search(r'<a[^>]+class="[^"]*\btitle\b[^"]*"[^>]*>(.*?)</a>', page, re.S)
    if match:
        return _clean_html(match.group(1))
    return _clean_html(_match(page, r"<title>(.*?)</title>") or "")


def _post_body(page: str) -> str:
    match = re.search(r'<div class="thing"[\s\S]*?<div class="usertext-body[^"]*"[^>]*>\s*<div class="md">(.*?)</div>', page)
    return _clean_html(match.group(1)) if match else ""


def _comments(page: str) -> list[dict]:
    comments = []
    pattern = r'<div[^>]+class="[^"]*\bcomment\b[^"]*"[^>]+data-fullname="(?P<id>t1_[^"]+)"[^>]*>(?P<body>.*?)(?=<div[^>]+class="[^"]*\bcomment\b[^"]*"[^>]+data-fullname="t1_|</body>)'
    for match in re.finditer(pattern, page, re.S):
        block = match.group("body")
        body_match = re.search(r'<div class="usertext-body[^"]*"[^>]*>\s*<div class="md">(.*?)</div>', block, re.S)
        body = _clean_html(body_match.group(1)) if body_match else ""
        if not body:
            continue
        comments.append(
            {
                "id": match.group("id"),
                "author": _match(block, r'<a[^>]*class="author[^"]*"[^>]*>(.*?)</a>'),
                "body": body,
                "score": _number(_match(block, r'<span class="score unvoted" title="([^"]*)"')),
                "created_at": _match(block, r'<time[^>]+datetime="([^"]+)"'),
                "url": _match(block, r'<a[^>]+href="([^"]+)"[^>]+class="bylink"'),
            }
        )
    return comments


def _subreddit(url: str, page: str) -> str | None:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    if len(parts) >= 2 and parts[0].lower() == "r":
        return parts[1]
    return _match(page, r"/r/([^/]+)/")


def _match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.S)
    return _clean_html(match.group(1)) if match else None


def _clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _number(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except ValueError:
        return None
