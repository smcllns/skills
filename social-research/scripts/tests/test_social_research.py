from __future__ import annotations

import http.client
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
import urllib.error
import urllib.parse
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from core.models import (  # noqa: E402
    LookbackWindow,
    MediaItem,
    SearchConfig,
    SourceItem,
    SourceResult,
)
import core.config as config_module  # noqa: E402
from core.config import load_config  # noqa: E402
from core.normalize import normalize_item  # noqa: E402
from core.pipeline import run_search  # noqa: E402
from core.rank import dedupe_and_rank  # noqa: E402
from core.render import render_markdown  # noqa: E402
from core.storage import SearchStorage, slugify  # noqa: E402
import sources.http as http_module  # noqa: E402
from sources.instagram import InstagramAdapter  # noqa: E402
from sources.pinterest import PinterestAdapter  # noqa: E402
from sources.reddit import RedditAdapter  # noqa: E402
from sources.threads import ThreadsAdapter  # noqa: E402
from sources.tiktok import TikTokAdapter  # noqa: E402
from sources.web import WebAdapter  # noqa: E402


FIXED_NOW = datetime(2026, 6, 15, 14, 32, tzinfo=timezone.utc)


class ConfigTests(unittest.TestCase):
    def test_loads_credentials_local_and_env_overrides_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            credentials_path = root / "credentials.local.json"
            credentials_path.write_text(json.dumps({"BRAVE_API_KEY": "from-credentials", "SCRAPECREATORS_API_KEY": "from-credentials"}))

            with patch.dict(os.environ, {"BRAVE_API_KEY": "from-env"}, clear=False):
                config = load_config(credentials_path)

        self.assertEqual(config["BRAVE_API_KEY"], "from-env")
        self.assertEqual(config["SCRAPECREATORS_API_KEY"], "from-credentials")

    def test_does_not_load_generic_config_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings_dir = root / ".social-research"
            settings_dir.mkdir()
            (settings_dir / "config.json").write_text(json.dumps({"BRAVE_API_KEY": "from-config", "SOCIAL_RESEARCH_LABEL": "from-config"}))

            with patch("pathlib.Path.home", return_value=root):
                reloaded_config = importlib.reload(config_module)
                try:
                    with patch.dict(os.environ, {}, clear=True):
                        config = reloaded_config.load_config()
                finally:
                    importlib.reload(config_module)

        self.assertNotIn("BRAVE_API_KEY", config)
        self.assertNotIn("SOCIAL_RESEARCH_LABEL", config)


class SearchStorageTests(unittest.TestCase):
    def test_creates_expected_directory_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = SearchConfig(query="Claude Code skills?", sources=["reddit"], output_root=root)
            item = SourceItem(
                id="r1",
                source="reddit",
                title="Claude Code skills are getting useful",
                url="https://reddit.example/thread",
                body="People are comparing skill workflows.",
                published_at="2026-06-12",
                engagement={"score": 42},
            )
            storage = SearchStorage(root=root, now=lambda: FIXED_NOW)

            run_dir = storage.create_run_dir(config)
            storage.write_artifacts(
                run_dir=run_dir,
                query=config.to_dict(),
                raw_by_source={"reddit": {"items": [{"id": "r1"}]}},
                normalized=[item],
                report="# Report\n",
            )

            self.assertEqual(run_dir.name, "2026-06-15-1432-claude-code-skills")
            self.assertEqual(json.loads((run_dir / "query.json").read_text())["query"], config.query)
            self.assertEqual(json.loads((run_dir / "raw" / "reddit.json").read_text())["items"][0]["id"], "r1")
            self.assertEqual(json.loads((run_dir / "normalized.json").read_text())["items"][0]["title"], item.title)
            self.assertEqual((run_dir / "report.md").read_text(), "# Report\n")

    def test_slugify_keeps_meaningful_words(self) -> None:
        self.assertEqual(slugify("  What's good in AI/audio?  "), "whats-good-in-ai-audio")


class NormalizationTests(unittest.TestCase):
    def test_normalizes_media_and_engagement_from_representative_payload(self) -> None:
        raw = {
            "id": "yt1",
            "title": "Hands-on review",
            "description": "A detailed demo.",
            "url": "https://youtu.be/demo",
            "channel": "Example Channel",
            "published_at": "2026-06-10T12:00:00Z",
            "view_count": 1200,
            "like_count": 90,
            "thumbnail": "https://img.example/thumb.jpg",
        }

        item = normalize_item("youtube", raw, 0)

        self.assertEqual(item.id, "yt1")
        self.assertEqual(item.source, "youtube")
        self.assertEqual(item.author, "Example Channel")
        self.assertEqual(item.published_at, "2026-06-10")
        self.assertEqual(item.engagement["views"], 1200)
        self.assertEqual(item.media[0].url, "https://img.example/thumb.jpg")
        self.assertEqual(item.media[0].kind, "image")

    def test_preserves_zero_relevance_and_polymarket_engagement(self) -> None:
        item = normalize_item(
            "polymarket",
            {"id": "pm1", "title": "Market", "url": "https://polymarket.example", "relevance": 0, "volume": 120, "liquidity": 80},
            0,
        )

        self.assertEqual(item.relevance, 0)
        self.assertEqual(item.engagement["volume"], 120)
        self.assertEqual(item.engagement["liquidity"], 80)

    def test_instagram_caption_shortcode_and_display_image_are_normalized(self) -> None:
        with patch(
            "sources.scrapecreators.get_json",
            return_value={
                "reels": [
                    {
                        "id": "ig1",
                        "shortcode": "ABC123",
                        "caption": "Leo's Tacos Truck in San Mateo",
                        "taken_at": "2026-04-10T20:28:35.000Z",
                        "like_count": 247,
                        "comment_count": 13,
                        "display_url": "https://img.example/ig.jpg",
                    }
                ]
            },
        ):
            result = InstagramAdapter().search(
                "tacos",
                LookbackWindow(start="2026-01-01", end="2026-12-31"),
                SearchConfig(query="tacos", config={"SCRAPECREATORS_API_KEY": "token"}),
            )

        item = result.items[0]
        self.assertEqual(item.title, "Leo's Tacos Truck in San Mateo")
        self.assertEqual(item.body, "Leo's Tacos Truck in San Mateo")
        self.assertEqual(item.url, "https://www.instagram.com/reel/ABC123/")
        self.assertEqual(item.published_at, "2026-04-10")
        self.assertEqual(item.engagement["likes"], 247)
        self.assertEqual(item.engagement["comments"], 13)
        self.assertEqual(item.media[0].url, "https://img.example/ig.jpg")

    def test_tiktok_search_item_list_aweme_info_is_normalized(self) -> None:
        with patch(
            "sources.scrapecreators.get_json",
            return_value={
                "search_item_list": [
                    {
                        "aweme_info": {
                            "aweme_id": "tt1",
                            "desc": "Leo's Taco Truck in San Mateo CA",
                            "create_time": 1764315908,
                            "share_url": "https://www.tiktok.com/@foodie/video/tt1",
                            "statistics": {"digg_count": 1526, "comment_count": 43, "play_count": 10000, "share_count": 12},
                        }
                    }
                ]
            },
        ):
            result = TikTokAdapter().search(
                "tacos",
                LookbackWindow(start="2026-01-01", end="2026-12-31"),
                SearchConfig(query="tacos", config={"SCRAPECREATORS_API_KEY": "token"}),
            )

        item = result.items[0]
        self.assertEqual(item.id, "tt1")
        self.assertEqual(item.title, "Leo's Taco Truck in San Mateo CA")
        self.assertEqual(item.url, "https://www.tiktok.com/@foodie/video/tt1")
        self.assertEqual(item.engagement["likes"], 1526)
        self.assertEqual(item.engagement["comments"], 43)
        self.assertEqual(item.engagement["views"], 10000)
        self.assertEqual(item.engagement["shares"], 12)


class HttpTests(unittest.TestCase):
    def test_get_json_uses_certifi_when_python_default_cafile_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_cafile = str(Path(tmp) / "missing-cert.pem")
            fake_certifi_path = str(Path(tmp) / "certifi.pem")
            Path(fake_certifi_path).write_text("fake cert bundle")
            default_paths = types.SimpleNamespace(cafile=None, openssl_cafile=missing_cafile)
            fake_certifi = types.SimpleNamespace(where=lambda: fake_certifi_path)

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return b'{"ok": true}'

            def fake_urlopen(request, *, timeout):
                self.assertEqual(os.environ.get("SSL_CERT_FILE"), fake_certifi_path)
                return FakeResponse()

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.dict(sys.modules, {"certifi": fake_certifi}),
                patch("ssl.get_default_verify_paths", return_value=default_paths),
                patch("sources.http.urllib.request.urlopen", side_effect=fake_urlopen),
            ):
                self.assertEqual(http_module.get_json("https://example.test"), {"ok": True})


class WebAdapterTests(unittest.TestCase):
    def test_brave_retries_without_freshness_when_date_range_is_rejected(self) -> None:
        calls: list[str] = []

        observed_headers = []

        def fake_get_json(url, *, headers=None):
            calls.append(url)
            observed_headers.append(headers)
            if len(calls) == 1:
                exc = urllib.error.HTTPError(url, 422, "Unprocessable Entity", None, BytesIO())
                exc.close()
                raise exc
            return {
                "web": {
                    "results": [
                        {
                            "url": "https://example.com/tacos",
                            "title": "Best taco trucks in San Mateo",
                            "description": "Leo's Tacos and Taqueria El Chacho",
                        }
                    ]
                }
            }

        with patch("sources.web.get_json", side_effect=fake_get_json):
            result = WebAdapter().search(
                "best taco trucks",
                LookbackWindow(start="2025-06-16", end="2026-06-16"),
                SearchConfig(query="best taco trucks", limit=25, config={"BRAVE_API_KEY": "token"}),
            )

        self.assertEqual(result.items[0].title, "Best taco trucks in San Mateo")
        self.assertIn("freshness=", calls[0])
        self.assertNotIn("freshness=", calls[1])
        self.assertIn("count=20", calls[0])
        self.assertEqual(observed_headers[0]["Accept"], "application/json")


class ScrapeCreatorsAdapterTests(unittest.TestCase):
    def test_threads_uses_query_param(self) -> None:
        calls: list[str] = []

        def fake_get_json(url, *, headers=None):
            calls.append(url)
            return {"posts": []}

        with patch("sources.scrapecreators.get_json", side_effect=fake_get_json):
            ThreadsAdapter().search(
                "taco trucks",
                LookbackWindow(start="2026-01-01", end="2026-12-31"),
                SearchConfig(query="taco trucks", config={"SCRAPECREATORS_API_KEY": "token"}),
            )

        self.assertIn("query=taco+trucks", calls[0])
        self.assertNotIn("keyword=", calls[0])

    def test_pinterest_uses_query_param(self) -> None:
        calls: list[str] = []

        def fake_get_json(url, *, headers=None):
            calls.append(url)
            return {"pins": []}

        with patch("sources.scrapecreators.get_json", side_effect=fake_get_json):
            PinterestAdapter().search(
                "taco trucks",
                LookbackWindow(start="2026-01-01", end="2026-12-31"),
                SearchConfig(query="taco trucks", config={"SCRAPECREATORS_API_KEY": "token"}),
            )

        self.assertIn("query=taco+trucks", calls[0])
        self.assertNotIn("keyword=", calls[0])


class RankTests(unittest.TestCase):
    def test_dedupes_by_url_and_prefers_more_engaged_item(self) -> None:
        low = SourceItem(
            id="a",
            source="web",
            title="Same story",
            url="https://example.com/story?utm=1",
            body="short",
            engagement={"likes": 2},
            relevance=0.3,
        )
        high = SourceItem(
            id="b",
            source="reddit",
            title="Same story with discussion",
            url="https://example.com/story",
            body="long discussion",
            engagement={"score": 100, "comments": 20},
            relevance=0.5,
        )
        other = SourceItem(
            id="c",
            source="hackernews",
            title="Different story",
            url="https://news.ycombinator.com/item?id=123",
            body="interesting",
            engagement={"points": 10},
            relevance=0.3,
        )

        ranked = dedupe_and_rank([low, high, other])

        self.assertEqual([item.id for item in ranked], ["b", "c"])
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_query_relevance_beats_unrelated_engagement(self) -> None:
        unrelated = SourceItem(
            id="pm1",
            source="polymarket",
            title="Anime Awards winner",
            url="https://polymarket.example/anime-awards",
            body="A high volume market unrelated to restaurants.",
            engagement={"volume": 50000},
        )
        relevant = SourceItem(
            id="web1",
            source="web",
            title="Leo's taco truck",
            url="https://example.com/leos-taco-truck",
            body="Local diners recommend this truck.",
        )

        ranked = dedupe_and_rank([unrelated, relevant], query="best taco trucks in San Mateo California")

        self.assertEqual([item.id for item in ranked], ["web1", "pm1"])
        self.assertEqual(unrelated.relevance, 0)
        self.assertEqual(relevant.relevance, 0.4)
        self.assertGreater(relevant.relevance, unrelated.relevance)

    def test_query_relevance_matches_whole_words_and_simple_plurals(self) -> None:
        item = SourceItem(
            id="food1",
            source="web",
            title="Sandwich shop near Santa Clara with taco trucks",
            url="https://example.com/food",
            body="Local list.",
        )

        dedupe_and_rank([item], query="best taco trucks in San Mateo California")

        self.assertEqual(item.relevance, 0.4)


class RenderTests(unittest.TestCase):
    def test_markdown_includes_coverage_links_quotes_and_useful_images(self) -> None:
        report = render_markdown(
            query="Claude Code skills",
            window=LookbackWindow(start="2026-05-16", end="2026-06-15"),
            items=[
                SourceItem(
                    id="ig1",
                    source="instagram",
                    title="Agent workflow clip",
                    url="https://instagram.example/reel",
                    body="A creator says skills made agents feel practical.",
                    author="creator",
                    published_at="2026-06-14",
                    engagement={"likes": 15},
                    media=[MediaItem(url="https://img.example/reel.jpg", kind="image", alt="Reel thumbnail")],
                    score=0.75,
                )
            ],
            raw_artifact_path=Path("/tmp/search/raw"),
        )

        self.assertIn("# Social Research: Claude Code skills", report)
        self.assertIn("- instagram: 1", report)
        self.assertIn("[Agent workflow clip](https://instagram.example/reel)", report)
        self.assertIn("![Reel thumbnail](https://img.example/reel.jpg)", report)
        self.assertIn("> A creator says skills made agents feel practical.", report)
        self.assertIn("Raw artifacts: `/tmp/search/raw`", report)


class PipelineSmokeTests(unittest.TestCase):
    def test_mock_source_run_writes_full_search_directory(self) -> None:
        class MockAdapter:
            source = "mock"

            def search(self, query: str, window: LookbackWindow, config: SearchConfig) -> SourceResult:
                return SourceResult(
                    source="mock",
                    raw={"items": [{"id": "m1", "title": query}]},
                    items=[
                        SourceItem(
                            id="m1",
                            source="mock",
                            title=f"{query} field note",
                            url="https://example.com/m1",
                            body="A mock source produced evidence.",
                            published_at=window.end,
                            engagement={"score": 5},
                        )
                    ],
                )

        with tempfile.TemporaryDirectory() as tmp:
            config = SearchConfig(
                query="Claude Code skills",
                sources=["mock"],
                output_root=Path(tmp),
            )

            report = run_search(config, adapters={"mock": MockAdapter()}, now=lambda: FIXED_NOW)

            self.assertEqual(report.run_dir.name, "2026-06-15-1432-claude-code-skills")
            self.assertTrue((report.run_dir / "query.json").exists())
            self.assertTrue((report.run_dir / "raw" / "mock.json").exists())
            self.assertTrue((report.run_dir / "normalized.json").exists())
            self.assertTrue((report.run_dir / "report.md").exists())
            self.assertEqual(report.items[0].source, "mock")

    def test_filters_dated_items_outside_window_and_keeps_undated_items(self) -> None:
        class OldAdapter:
            source = "old"

            def search(self, query: str, window: LookbackWindow, config: SearchConfig) -> SourceResult:
                return SourceResult(
                    source="old",
                    raw={"items": []},
                    items=[
                        SourceItem(id="old", source="old", title="old", url="https://example.com/old", published_at="2001-01-01"),
                        SourceItem(id="current", source="old", title="current", url="https://example.com/current", published_at=window.end),
                        SourceItem(id="undated", source="old", title="undated", url="https://example.com/undated"),
                    ],
                )

        with tempfile.TemporaryDirectory() as tmp:
            report = run_search(
                SearchConfig(query="window", sources=["old"], lookback_days=7, output_root=Path(tmp)),
                adapters={"old": OldAdapter()},
                now=lambda: FIXED_NOW,
            )

            self.assertEqual({item.id for item in report.items}, {"current", "undated"})

    def test_rejects_source_names_that_cannot_be_raw_artifact_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run_search(
                    SearchConfig(query="bad source", sources=["../oops"], output_root=Path(tmp)),
                    adapters={},
                    now=lambda: FIXED_NOW,
                )


class RedditAdapterTests(unittest.TestCase):
    def test_falls_back_to_brave_and_scrapes_old_reddit_when_json_is_blocked(self) -> None:
        calls: list[str] = []
        text_headers: list[dict | None] = []
        thread_html = """
        <html>
          <head><title>Best burritos/tacos in the Peninsula? : bayarea</title></head>
          <body>
            <div class="thing" data-fullname="t3_abc123" data-score="28" data-comments-count="55">
              <p class="title"><a class="title" href="/r/bayarea/comments/abc123/best_burritostacos/">Best burritos/tacos in the Peninsula?</a></p>
              <p class="tagline">submitted <time datetime="2026-03-29T20:06:51+00:00"></time> by <a class="author">poster</a></p>
              <a href="/r/bayarea/">self.bayarea</a>
              <div class="usertext-body"><div class="md"><p>What are your favorite tacos?</p></div></div>
            </div>
            <div class="comment" data-fullname="t1_c1">
              <div class="entry unvoted">
                <p class="tagline"><a class="author">local1</a><span class="score unvoted" title="35">35 points</span><time datetime="2026-03-30T00:03:56+00:00"></time></p>
                <form><div class="usertext-body"><div class="md"><p>Leo's taco truck in San Mateo on ECR near 92.</p></div></div></form>
                <a href="https://old.reddit.com/r/bayarea/comments/abc123/best_burritostacos/c1/" class="bylink">permalink</a>
              </div>
            </div>
            <div class="comment" data-fullname="t1_c2">
              <div class="entry unvoted">
                <p class="tagline"><a class="author">local2</a><span class="score unvoted" title="16">16 points</span></p>
                <form><div class="usertext-body"><div class="md"><p>Taqueria El Chacho in the Foster City Target plaza is mad good.</p></div></div></form>
                <a href="https://old.reddit.com/r/bayarea/comments/abc123/best_burritostacos/c2/" class="bylink">permalink</a>
              </div>
            </div>
          </body>
        </html>
        """

        def fake_get_json(url, *, headers=None):
            calls.append(url)
            if "reddit.com/search.json" in url:
                exc = urllib.error.HTTPError(url, 403, "Blocked", None, BytesIO())
                exc.close()
                raise exc
            return {
                "web": {
                    "results": [
                        {
                            "url": "https://www.reddit.com/r/bayarea/comments/abc123/best_burritostacos/c1/?utm_source=share",
                            "title": "r/bayarea on Reddit: Best burritos/tacos in the Peninsula?",
                            "description": "<strong>Leo&#x27;s taco truck</strong> in San Mateo on ECR near 92.",
                        },
                        {
                            "url": "https://www.reddit.com/r/bayarea/comments/abc123/best_burritostacos/c2/",
                            "title": "Duplicate comment permalink",
                            "description": "Another Brave hit for the same Reddit thread.",
                        },
                    ]
                }
            }

        def fake_get_text(url, *, headers=None):
            calls.append(url)
            text_headers.append(headers)
            return thread_html

        with patch("sources.reddit.get_json", side_effect=fake_get_json), patch("sources.reddit.get_text", side_effect=fake_get_text):
            result = RedditAdapter().search(
                "best taco trucks in San Mateo California",
                LookbackWindow(start="2025-06-16", end="2026-06-16"),
                SearchConfig(query="best taco trucks in San Mateo California", limit=10, config={"BRAVE_API_KEY": "token"}),
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.raw["mode"], "brave_old_reddit_fallback")
        self.assertIn("site:reddit.com", urllib.parse.unquote_plus(calls[1]))
        self.assertIn("https://old.reddit.com/r/bayarea/comments/abc123/best_burritostacos/", calls[2])
        self.assertEqual(len([call for call in calls if call.startswith("https://old.reddit.com/")]), 1)
        self.assertIn("Mozilla/5.0", text_headers[0]["User-Agent"])
        self.assertEqual(result.raw["threads"][0]["discovery"]["description"], "Leo's taco truck in San Mateo on ECR near 92.")
        self.assertEqual(result.raw["threads"][0]["comments"][0]["body"], "Leo's taco truck in San Mateo on ECR near 92.")
        self.assertEqual(result.items[0].title, "Best burritos/tacos in the Peninsula?")
        self.assertTrue(result.items[0].body.startswith("Leo's taco truck in San Mateo on ECR near 92."))
        self.assertIn("Taqueria El Chacho", result.items[0].body)
        self.assertEqual(result.items[0].engagement["comments"], 55)

    def test_reddit_fallback_reports_missing_brave_key_after_json_block(self) -> None:
        def blocked_json(url, *, headers=None):
            exc = urllib.error.HTTPError(url, 403, "Blocked", None, BytesIO())
            exc.close()
            raise exc

        with patch("sources.reddit.get_json", side_effect=blocked_json):
            result = RedditAdapter().search(
                "taco trucks",
                LookbackWindow(start="2025-06-16", end="2026-06-16"),
                SearchConfig(query="taco trucks", config={}),
            )

        self.assertEqual(result.error, "Reddit JSON is blocked and BRAVE_API_KEY is not configured")

    def test_reddit_fallback_handles_json_rate_limit(self) -> None:
        thread_html = """
        <html>
          <body>
            <div class="thing" data-fullname="t3_rate" data-score="8" data-comments-count="1">
              <a class="title">Rate limited taco thread</a>
            </div>
            <div class="comment" data-fullname="t1_c1">
              <div class="usertext-body"><div class="md"><p>Leo's taco truck still wins.</p></div></div>
            </div>
          </body>
        </html>
        """

        def fake_get_json(url, *, headers=None):
            if "reddit.com/search.json" in url:
                exc = urllib.error.HTTPError(url, 429, "Too Many Requests", None, BytesIO())
                exc.close()
                raise exc
            return {"web": {"results": [{"url": "https://www.reddit.com/r/bayarea/comments/rate123/rate_limited_thread/"}]}}

        with patch("sources.reddit.get_json", side_effect=fake_get_json), patch("sources.reddit.get_text", return_value=thread_html):
            result = RedditAdapter().search(
                "taco trucks",
                LookbackWindow(start="2025-06-16", end="2026-06-16"),
                SearchConfig(query="taco trucks", limit=10, config={"BRAVE_API_KEY": "token"}),
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.raw["mode"], "brave_old_reddit_fallback")
        self.assertEqual(result.items[0].title, "Rate limited taco thread")

    def test_reddit_fallback_skips_one_malformed_thread_page(self) -> None:
        calls: list[str] = []
        thread_html = """
        <html>
          <body>
            <div class="thing" data-fullname="t3_ok" data-score="12" data-comments-count="1">
              <a class="title">Good taco truck thread</a>
              <time datetime="2026-04-01T00:00:00+00:00"></time>
            </div>
            <div class="comment" data-fullname="t1_c1">
              <div class="usertext-body"><div class="md"><p>Leo's taco truck is worth trying.</p></div></div>
            </div>
          </body>
        </html>
        """

        def fake_get_json(url, *, headers=None):
            if "reddit.com/search.json" in url:
                exc = urllib.error.HTTPError(url, 403, "Blocked", None, BytesIO())
                exc.close()
                raise exc
            return {
                "web": {
                    "results": [
                        {"url": "https://www.reddit.com/r/bayarea/comments/bad123/bad_thread/"},
                        {"url": "https://www.reddit.com/r/bayarea/comments/dropped123/dropped_thread/"},
                        {"url": "https://www.reddit.com/r/bayarea/comments/ok123/good_thread/"},
                    ]
                }
            }

        def fake_get_text(url, *, headers=None):
            calls.append(url)
            if "bad123" in url:
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
            if "dropped123" in url:
                raise http.client.IncompleteRead(b"partial")
            return thread_html

        with patch("sources.reddit.get_json", side_effect=fake_get_json), patch("sources.reddit.get_text", side_effect=fake_get_text):
            result = RedditAdapter().search(
                "taco trucks",
                LookbackWindow(start="2025-06-16", end="2026-06-16"),
                SearchConfig(query="taco trucks", limit=10, config={"BRAVE_API_KEY": "token"}),
            )

        self.assertIsNone(result.error)
        self.assertEqual(
            calls,
            [
                "https://old.reddit.com/r/bayarea/comments/bad123/bad_thread/",
                "https://old.reddit.com/r/bayarea/comments/dropped123/dropped_thread/",
                "https://old.reddit.com/r/bayarea/comments/ok123/good_thread/",
            ],
        )
        self.assertEqual(result.items[0].title, "Good taco truck thread")

    def test_maps_lookback_days_to_reddit_time_bucket(self) -> None:
        from sources.reddit import _reddit_time_bucket

        self.assertEqual(_reddit_time_bucket(7), "week")
        self.assertEqual(_reddit_time_bucket(30), "month")
        self.assertEqual(_reddit_time_bucket(90), "year")


if __name__ == "__main__":
    unittest.main()
