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

    def test_flags_silent_zero_sources_for_sanity_check(self) -> None:
        report = render_markdown(
            query="private schools bay area",
            window=LookbackWindow(start="2026-05-16", end="2026-06-15"),
            items=[SourceItem(id="r1", source="reddit", title="t", url="https://r.example")],
            raw_artifact_path=Path("/tmp/raw"),
            silent_zero_sources=["youtube"],
        )
        self.assertIn("Sanity check", report)
        self.assertIn("- youtube: queried, 0 items, no error", report)

    def test_no_sanity_section_when_nothing_silent(self) -> None:
        report = render_markdown(
            query="topic",
            window=LookbackWindow(start="2026-05-16", end="2026-06-15"),
            items=[SourceItem(id="r1", source="reddit", title="t", url="https://r.example")],
            raw_artifact_path=Path("/tmp/raw"),
            silent_zero_sources=[],
        )
        self.assertNotIn("Sanity check", report)


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
        self.assertEqual(_reddit_time_bucket(0), "all")
        self.assertEqual(_reddit_time_bucket(730), "all")


class BuildMapTests(unittest.TestCase):
    def setUp(self) -> None:
        import build_map

        self.build_map = build_map

    def test_returns_none_without_api_key(self) -> None:
        place = self.build_map.MapPlace(name="Tillingham", query="Tillingham, Peasmarsh, UK", rank="1")
        self.assertIsNone(self.build_map.build_map([place], api_key=None))

    def test_view_params_use_padded_bbox_for_multiple_points(self) -> None:
        points = [
            {"lon": 0.0, "lat": 50.0},
            {"lon": 1.0, "lat": 51.0},
        ]
        view = self.build_map._view_params(points)
        self.assertEqual(len(view), 1)
        self.assertTrue(view[0].startswith("area=rect:"))
        nums = [float(n) for n in view[0].split("rect:")[1].split(",")]
        self.assertLess(nums[0], 0.0)  # min lon padded outward
        self.assertGreater(nums[2], 1.0)  # max lon padded outward

    def test_view_params_center_for_single_point(self) -> None:
        view = self.build_map._view_params([{"lon": -0.1, "lat": 51.5}])
        self.assertEqual(view, ["center=lonlat:-0.1,51.5", "zoom=11"])

    def test_marker_encodes_color_and_label(self) -> None:
        point = {"lon": -0.1, "lat": 51.5, "rank": "1"}
        marker = self.build_map._marker(point, "#1f63e6")
        self.assertIn("lonlat:-0.1,51.5", marker)
        self.assertIn("color:%231f63e6", marker)
        self.assertIn("text:1", marker)
        self.assertIn("type:material", marker)

    def test_static_map_url_has_required_params(self) -> None:
        url = self.build_map._static_map_url(
            "secret-key", "positron", 760, 480, 2, "png", ["area=rect:0,0,1,1"], ["lonlat:0,0;type:material"]
        )
        self.assertTrue(url.startswith("https://maps.geoapify.com/v1/staticmap?"))
        self.assertIn("style=positron", url)
        self.assertIn("scaleFactor=2", url)
        self.assertIn("marker=lonlat:0,0;type:material", url)
        self.assertIn("apiKey=secret-key", url)

    def test_static_map_url_joins_multiple_markers_into_one_param(self) -> None:
        # Geoapify wants ONE pipe-separated marker param, not repeated params.
        url = self.build_map._static_map_url(
            "k", "positron", 760, 480, 2, "jpeg", ["area=rect:0,0,1,1"],
            ["lonlat:0,0;text:1", "lonlat:1,1;text:2"],
        )
        self.assertEqual(url.count("marker="), 1)
        self.assertIn("marker=lonlat:0,0;text:1|lonlat:1,1;text:2", url)

    def test_build_map_geocodes_and_returns_data_uris(self) -> None:
        bm = self.build_map
        place_top = bm.MapPlace(name="A", query="A, UK", rank="1", kind="top")
        place_near = bm.MapPlace(name="B", query="B, UK", rank="A", kind="near")

        def fake_get_json(url, *, headers=None, timeout=20):
            lat = 51.0 if "A%2C" in url or "A," in url else 52.0
            return {"results": [{"lat": lat, "lon": 0.5, "formatted": "addr"}]}

        captured_urls: list[str] = []

        def fake_get_bytes(url, *, headers=None, timeout=30):
            captured_urls.append(url)
            return b"\x89PNG\r\n\x1a\nfake"

        with (
            patch("build_map.get_json", side_effect=fake_get_json),
            patch("build_map.get_bytes", side_effect=fake_get_bytes),
        ):
            result = bm.build_map([place_top, place_near], api_key="k")

        self.assertIsNotNone(result)
        self.assertTrue(result.light_data_uri.startswith("data:image/jpeg;base64,"))
        self.assertTrue(result.dark_data_uri.startswith("data:image/jpeg;base64,"))
        self.assertEqual(len(result.located), 2)
        self.assertEqual(result.missing, [])
        self.assertIn("OpenStreetMap", result.attribution_text)
        self.assertIn("Geoapify", result.attribution_text)
        self.assertIn("style=positron", captured_urls[0])
        self.assertIn("style=dark-matter", captured_urls[1])

    def test_supplied_coordinates_skip_geocoding(self) -> None:
        bm = self.build_map
        place = bm.MapPlace(name="A", query="A Hotel, AB1 2CD, UK", rank="1", lat=51.5, lon=-0.1)

        def boom(*a, **k):
            raise AssertionError("geocoding API must not be called when coords are supplied")

        with (
            patch("build_map.get_json", side_effect=boom),
            patch("build_map.get_bytes", return_value=b"fake"),
        ):
            result = bm.build_map([place], api_key="k")

        self.assertIsNotNone(result)
        self.assertEqual(len(result.located), 1)
        self.assertEqual(result.located[0]["lat"], 51.5)
        self.assertEqual(result.located[0]["lon"], -0.1)
        self.assertEqual(result.located[0]["source"], "provided")

    def test_no_match_omits_pin_and_records_missing(self) -> None:
        bm = self.build_map
        place = bm.MapPlace(name="Nowhere", query="zzz nowhere", rank="1")

        with patch("build_map.get_json", return_value={"results": []}):
            result = bm.build_map([place], api_key="k")

        # all places failed to geocode -> fallback
        self.assertIsNone(result)

    def test_geocode_cache_round_trips(self) -> None:
        bm = self.build_map
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            calls: list[str] = []

            def fake_get_json(url, *, headers=None, timeout=20):
                calls.append(url)
                return {"results": [{"lat": 51.0, "lon": 0.5, "formatted": "addr"}]}

            with (
                patch("build_map.get_json", side_effect=fake_get_json),
                patch("build_map.get_bytes", return_value=b"img"),
            ):
                place = bm.MapPlace(name="A", query="A, UK", rank="1")
                bm.build_map([place], api_key="k", cache_dir=cache_dir)
                self.assertTrue((cache_dir / "geocode_cache.json").exists())
                # second run should hit the cache, not re-geocode
                bm.build_map([place], api_key="k", cache_dir=cache_dir)

        self.assertEqual(len(calls), 1)


class ValidateHtmlReportTests(unittest.TestCase):
    def setUp(self) -> None:
        import validate_html_report

        self.validate_html_report = validate_html_report

    def test_valid_decision_report_passes(self) -> None:
        html = """
        <html><body>
          <section id="brief">What was asked</section>
          <div class="theme-toggle"><button data-theme="light">Light</button><button data-theme="dark">Dark</button></div>
          <section id="index"><table><tr><td><a href="#pick-1">Pick 1</a></td></tr></table></section>
          <section id="top-picks">
            <article class="card" id="pick-1"><img class="photo" src="data:image/jpeg;base64,aaa"><ul class="checks"><li class="check"><span class="label">Quality signal</span>Great</li><li class="check"><span class="label">Style</span>Smash</li><li class="check"><span class="label">Order</span>Double</li></ul></article>
          </section>
          <section id="near-misses">
            <article class="card near"><img class="photo" src="data:image/jpeg;base64,bbb"><p>Good</p><p>Miss reason</p><a class="button" href="https://example.com">Visit</a></article>
          </section>
          <section id="map"><img class="map-img light" src="data:image/jpeg;base64,ccc"><img class="map-img dark" src="data:image/jpeg;base64,ddd"><p class="map-attrib">© OpenStreetMap contributors · Powered by Geoapify</p></section>
          <details open><summary>Appendix A — searches</summary><p>Verdict: pass. reddit queried → results used.</p></details>
          <details open><summary>Appendix B — next steps</summary></details>
          <details open><summary>Appendix C — debug / issues</summary></details>
        </body></html>
        """

        self.validate_html_report.validate_html(html)

    def test_valid_map_fallback_passes_with_appendix_c_reason(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"><button data-theme="light"></button></div>
          <section id="index"><table><tr><td><a href="#pick-1">Pick 1</a></td></tr></table></section>
          <section id="top-picks"><article class="card" id="pick-1"><img src="data:image/jpeg;base64,a"><span class="check"><span class="label">Quality signal</span>x</span><span class="check"><span class="label">Style</span>x</span><span class="check"><span class="label">Order</span>x</span></article></section>
          <section id="map"><ul class="legend"><li>Top picks</li></ul><p class="map-links"><a href="https://maps.example">Place</a></p></section>
          <details open><summary>Appendix A — searches</summary><p>Verdict: pass. reddit queried → results used.</p></details>
          <details open><summary>Appendix B — next steps</summary></details>
          <details open><summary>Appendix C — debug / issues</summary><p>Fallback used because no Geoapify key was available.</p></details>
        </body></html>
        """

        self.validate_html_report.validate_html(html)

    def test_void_elements_do_not_extend_near_misses_scope(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"><button data-theme="light"></button></div>
          <section id="index"><table><tr><td><a href="#pick-1">Pick 1</a></td></tr></table></section>
          <section id="top-picks"><article class="card" id="pick-1"><img src="data:image/jpeg;base64,a"><span class="check"><span class="label">Quality signal</span>x</span><span class="check"><span class="label">Style</span>x</span><span class="check"><span class="label">Order</span>x</span></article></section>
          <section id="near-misses"><article class="card near"><img src="data:image/jpeg;base64,b"><p>Good</p></article></section>
          <section id="map"><ul class="legend"><li>Top picks</li></ul><p class="map-links"><a href="https://maps.example">Place</a></p></section>
          <details open><summary>Appendix A — searches</summary><p>Verdict: pass. reddit queried → results used.</p></details>
          <details open><summary>Appendix B — next steps</summary></details>
          <details open><summary>Appendix C — debug / issues</summary><p>Fallback used because no Geoapify key was available.</p></details>
        </body></html>
        """

        self.validate_html_report.validate_html(html)

    def test_rejects_hotlinked_images(self) -> None:
        html = '<html><body><section id="brief"></section><div class="theme-toggle"></div><img src="https://example.com/a.jpg"></body></html>'

        with self.assertRaisesRegex(ValueError, "non-data image src"):
            self.validate_html_report.validate_html(html)

    def test_rejects_map_without_geoapify_light_dark_attribution(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"></div>
          <section id="map"><img class="map-img light" src="data:image/jpeg;base64,aaa"></section>
        </body></html>
        """

        with self.assertRaisesRegex(ValueError, "map section"):
            self.validate_html_report.validate_html(html)

    def test_rejects_near_miss_bullet_list_even_when_cards_exist(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"></div>
          <section id="near-misses"><article class="card near"><img src="data:image/jpeg;base64,a"></article><ul><li>Jeffrey's — good but missed</li></ul></section>
        </body></html>
        """

        with self.assertRaisesRegex(ValueError, "near misses"):
            self.validate_html_report.validate_html(html)

    def test_rejects_top_pick_without_matching_criteria_tiles(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"><button data-theme="light"></button></div>
          <section id="index"><table><tr><td><a href="#pick-1">Pick 1</a></td><td><a href="#pick-2">Pick 2</a></td></tr></table></section>
          <section id="top-picks">
            <article class="card" id="pick-1"><img src="data:image/jpeg;base64,a"><span class="check"><span class="label">Quality signal</span>x</span><span class="check"><span class="label">Style</span>x</span><span class="check"><span class="label">Order</span>x</span></article>
            <article class="card" id="pick-2"><img src="data:image/jpeg;base64,b"></article>
          </section>
          <details open><summary>Appendix A — searches</summary><p>Verdict: pass. reddit queried → results used.</p></details><details open><summary>Appendix B — next steps</summary></details>
        </body></html>
        """

        with self.assertRaisesRegex(ValueError, "criteria"):
            self.validate_html_report.validate_html(html)

    def test_rejects_missing_specific_appendix_a_and_review_status(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"><button data-theme="light"></button></div>
          <section id="index"><table><tr><td><a href="#pick-1">Pick 1</a></td></tr></table></section>
          <section id="top-picks"><article class="card" id="pick-1"><img src="data:image/jpeg;base64,a"><span class="check"><span class="label">Quality signal</span>x</span><span class="check"><span class="label">Style</span>x</span><span class="check"><span class="label">Order</span>x</span></article></section>
          <details open><summary>Foo</summary></details><details open><summary>Bar</summary></details>
        </body></html>
        """

        with self.assertRaisesRegex(ValueError, "Appendix A"):
            self.validate_html_report.validate_html(html)

    def test_rejects_missing_index_links(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"><button data-theme="light"></button></div>
          <section id="top-picks"><article class="card" id="pick-1"><img src="data:image/jpeg;base64,a"><span class="check"><span class="label">Quality signal</span>x</span><span class="check"><span class="label">Style</span>x</span><span class="check"><span class="label">Order</span>x</span></article></section>
          <details open><summary>Appendix A — searches</summary><p>Verdict: pass. reddit queried → results used.</p></details><details open><summary>Appendix B — next steps</summary></details>
        </body></html>
        """

        with self.assertRaisesRegex(ValueError, "index"):
            self.validate_html_report.validate_html(html)

    def test_rejects_needs_fixes_without_user_acknowledgement(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"><button data-theme="light"></button></div>
          <section id="index"><table><tr><td><a href="#pick-1">Pick 1</a></td></tr></table></section>
          <section id="top-picks"><article class="card" id="pick-1"><img src="data:image/jpeg;base64,a"><span class="check"><span class="label">Quality signal</span>x</span><span class="check"><span class="label">Style</span>x</span><span class="check"><span class="label">Order</span>x</span></article></section>
          <details open><summary>Appendix A — searches</summary><p>Verdict: needs fixes. reddit queried → results used.</p></details><details open><summary>Appendix B — next steps</summary></details>
        </body></html>
        """

        with self.assertRaisesRegex(ValueError, "review verdict"):
            self.validate_html_report.validate_html(html)

    def test_allows_needs_fixes_with_user_acknowledgement(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"><button data-theme="light"></button></div>
          <section id="index"><table><tr><td><a href="#pick-1">Pick 1</a></td></tr></table></section>
          <section id="top-picks"><article class="card" id="pick-1"><img src="data:image/jpeg;base64,a"><span class="check"><span class="label">Quality signal</span>x</span><span class="check"><span class="label">Style</span>x</span><span class="check"><span class="label">Order</span>x</span></article></section>
          <details open><summary>Appendix A — searches</summary><p>Verdict: needs fixes; user acknowledged limitations. reddit queried → results used.</p></details><details open><summary>Appendix B — next steps</summary></details>
        </body></html>
        """

        self.validate_html_report.validate_html(html)

    def test_clean_credential_preflight_note_does_not_require_appendix_c(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"><button data-theme="light"></button></div>
          <section id="index"><table><tr><td><a href="#pick-1">Pick 1</a></td></tr></table></section>
          <section id="top-picks"><article class="card" id="pick-1"><img src="data:image/jpeg;base64,a"><span class="check"><span class="label">Quality signal</span>x</span><span class="check"><span class="label">Style</span>x</span><span class="check"><span class="label">Order</span>x</span></article></section>
          <p>Credentials preflight passed for Brave and ScrapeCreators.</p>
          <details open><summary>Appendix A — searches</summary><p>Verdict: pass. reddit queried → results used.</p></details><details open><summary>Appendix B — next steps</summary></details>
        </body></html>
        """

        self.validate_html_report.validate_html(html)

    def test_requires_appendix_c_when_debug_terms_appear(self) -> None:
        html = """
        <html><body>
          <section id="brief"></section><div class="theme-toggle"></div>
          <p>First run had no credentials loaded, so X did not contribute.</p>
          <details open><summary>Appendix A — searches</summary></details>
          <details open><summary>Appendix B — next steps</summary></details>
        </body></html>
        """

        with self.assertRaisesRegex(ValueError, "Appendix C"):
            self.validate_html_report.validate_html(html)


class VendorUsageTests(unittest.TestCase):
    def setUp(self) -> None:
        import core.usage as usage_module

        self.usage = usage_module
        http_module.reset_request_counts()

    def tearDown(self) -> None:
        http_module.reset_request_counts()
        http_module.set_current_source(None)

    def test_http_counter_attributes_requests_to_current_source(self) -> None:
        http_module.set_current_source("web")
        http_module._record_request()
        http_module._record_request()
        http_module.set_current_source("reddit")
        http_module._record_request()
        http_module.set_current_source(None)
        http_module._record_request()  # untagged -> not counted
        self.assertEqual(http_module.get_request_counts(), {"web": 2, "reddit": 1})

    def test_prices_web_at_active_provider(self) -> None:
        items = {item.source: item for item in self.usage.price_vendor_calls({"web": 2}, limit=20, web_provider="brave")}
        self.assertAlmostEqual(items["web"].cost_usd, 2 * 0.005)
        self.assertEqual(items["web"].billing, "paid")

    def test_x_is_amortized_per_read(self) -> None:
        items = {item.source: item for item in self.usage.price_vendor_calls({"x": 1}, limit=20, web_provider=None)}
        self.assertAlmostEqual(items["x"].cost_usd, 1 * 20 * 0.005)

    def test_free_and_tos_risky_cost_zero_but_are_flagged(self) -> None:
        items = {item.source: item for item in self.usage.price_vendor_calls({"hackernews": 1, "reddit": 3}, limit=20, web_provider=None)}
        self.assertEqual(items["hackernews"].billing, "free")
        self.assertEqual(items["hackernews"].cost_usd, 0.0)
        self.assertEqual(items["reddit"].billing, "tos_risky")
        self.assertEqual(items["reddit"].cost_usd, 0.0)

    def test_scrapecreators_sources_priced_per_request(self) -> None:
        items = {item.source: item for item in self.usage.price_vendor_calls({"tiktok": 1, "instagram": 1}, limit=20, web_provider=None)}
        self.assertAlmostEqual(items["tiktok"].cost_usd, 0.00188)
        self.assertAlmostEqual(items["instagram"].cost_usd, 0.00188)

    def test_record_external_request_counts_against_current_source(self) -> None:
        http_module.set_current_source("youtube")
        http_module.record_external_request()
        http_module.set_current_source(None)
        http_module.record_external_request()  # untagged -> ignored
        self.assertEqual(http_module.get_request_counts(), {"youtube": 1})

    def test_per_run_vendor_pricing_handles_mixed_limits(self) -> None:
        import cost_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, limit in (("run-a", 10), ("run-b", 30)):
                d = root / name
                d.mkdir()
                (d / "usage.json").write_text(json.dumps({
                    "run_dir": str(d), "started_at": "2026-06-18T12:00:00Z",
                    "limit": limit, "web_provider": "brave",
                    "calls_by_source": {"x": 1},
                }))
            items, runs = cost_report._collect_vendor(root, None)
            self.assertEqual(len(runs), 2)
            x = {item.source: item for item in items}["x"]
            # priced per-run: 1*10*0.005 + 1*30*0.005, NOT 2 calls * last-limit
            self.assertAlmostEqual(x.cost_usd, (1 * 10 + 1 * 30) * 0.005)
            self.assertEqual(x.calls, 2)

    def test_mixed_web_providers_show_blended_rate(self) -> None:
        import cost_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, provider in (("run-a", "brave"), ("run-b", "serper")):
                d = root / name
                d.mkdir()
                (d / "usage.json").write_text(json.dumps({
                    "run_dir": str(d), "started_at": "2026-06-18T12:00:00Z",
                    "limit": 20, "web_provider": provider,
                    "calls_by_source": {"web": 1},
                }))
            items, _ = cost_report._collect_vendor(root, None)
            web = {item.source: item for item in items}["web"]
            # brave $0.005 + serper $0.001 = $0.006 over 2 calls -> blended $0.003
            self.assertAlmostEqual(web.cost_usd, 0.006)
            self.assertEqual(web.calls, 2)
            self.assertAlmostEqual(web.unit_rate, 0.003)
            self.assertIn("blended", web.unit)

    def test_detect_web_provider_precedence(self) -> None:
        self.assertEqual(self.usage.detect_web_provider({"SERPER_API_KEY": "x"}), "serper")
        self.assertEqual(self.usage.detect_web_provider({"BRAVE_API_KEY": "x", "SERPER_API_KEY": "x"}), "brave")
        self.assertIsNone(self.usage.detect_web_provider({}))

    def test_pipeline_emits_usage_record(self) -> None:
        from core.models import SearchConfig
        from core.pipeline import run_search

        class _Adapter:
            source = "demo"

            def search(self, query, window, config):
                return SourceResult(self.source, {"raw": []}, [])

        with tempfile.TemporaryDirectory() as tmp:
            config = SearchConfig(query="hello world", sources=["demo"], output_root=Path(tmp))
            report = run_search(config, adapters={"demo": _Adapter()}, now=lambda: FIXED_NOW)
            usage_path = report.run_dir / "usage.json"
            self.assertTrue(usage_path.exists())
            usage = json.loads(usage_path.read_text())
            self.assertEqual(usage["query"], "hello world")
            self.assertIn("window", usage)
            self.assertIn("calls_by_source", usage)


class CostReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        from core import cost as cost_module

        self.cost = cost_module

    def test_model_slug_mapping(self) -> None:
        self.assertEqual(self.cost.map_model_to_openrouter("claude-opus-4-8"), "anthropic/claude-opus-4.8")
        self.assertEqual(self.cost.map_model_to_openrouter("claude-opus-4-8[1m]"), "anthropic/claude-opus-4.8")
        self.assertEqual(self.cost.map_model_to_openrouter("claude-opus-4-8-fast"), "anthropic/claude-opus-4.8")
        self.assertEqual(self.cost.map_model_to_openrouter("gpt-5.5"), "openai/gpt-5.5")
        self.assertEqual(self.cost.map_model_to_openrouter("gpt-4-1"), "openai/gpt-4.1")

    def test_codex_descendants_handles_parent_cycle(self) -> None:
        index = {
            "a": {"id": "a", "path": None, "parent": "b"},
            "b": {"id": "b", "path": None, "parent": "a"},
        }
        # A<->B cycle must not recurse unbounded.
        result = self.cost._codex_descendants("a", index)
        self.assertEqual([info["id"] for info in result], ["b"])

    def test_claude_adapter_dedups_by_message_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            usage = {"input_tokens": 100, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 50, "output_tokens": 20, "server_tool_use": {"web_search_requests": 1}}
            lines = [
                {"type": "assistant", "requestId": "req1", "timestamp": "2026-06-18T12:00:00Z", "message": {"id": "msgA", "model": "claude-opus-4-8", "usage": usage}},
                {"type": "assistant", "requestId": "req1", "timestamp": "2026-06-18T12:00:00Z", "message": {"id": "msgA", "model": "claude-opus-4-8", "usage": usage}},  # dup content block
                {"type": "assistant", "requestId": "req2", "timestamp": "2026-06-18T12:01:00Z", "message": {"id": "msgB", "model": "claude-opus-4-8", "usage": usage}},
            ]
            transcript.write_text("\n".join(json.dumps(line) for line in lines))
            scopes = self.cost.claude_collect(transcript)
            mt = scopes.main["anthropic/claude-opus-4.8"]
            # two unique responses counted once each
            self.assertEqual(mt.input, 200)
            self.assertEqual(mt.cache_read, 2000)
            self.assertEqual(mt.output, 40)
            self.assertEqual(mt.web_search, 2)

    def test_claude_adapter_includes_subagents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            transcript.write_text(json.dumps({"type": "assistant", "requestId": "r", "timestamp": "2026-06-18T12:00:00Z", "message": {"id": "m", "model": "claude-opus-4-8", "usage": {"input_tokens": 10, "output_tokens": 5}}}))
            sub_dir = transcript.with_suffix("") / "subagents"
            sub_dir.mkdir(parents=True)
            (sub_dir / "agent-a1.jsonl").write_text(json.dumps({"type": "assistant", "requestId": "rs", "timestamp": "2026-06-18T12:00:00Z", "message": {"id": "ms", "model": "claude-opus-4-8", "usage": {"input_tokens": 7, "output_tokens": 3}}}))
            scopes = self.cost.claude_collect(transcript)
            self.assertEqual(scopes.main["anthropic/claude-opus-4.8"].input, 10)
            self.assertEqual(scopes.subagents["anthropic/claude-opus-4.8"].input, 7)

    def test_claude_window_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            lines = [
                {"type": "assistant", "requestId": "r1", "timestamp": "2026-06-18T10:00:00Z", "message": {"id": "m1", "model": "claude-opus-4-8", "usage": {"input_tokens": 100, "output_tokens": 0}}},
                {"type": "assistant", "requestId": "r2", "timestamp": "2026-06-18T13:00:00Z", "message": {"id": "m2", "model": "claude-opus-4-8", "usage": {"input_tokens": 200, "output_tokens": 0}}},
            ]
            transcript.write_text("\n".join(json.dumps(line) for line in lines))
            window = (self.cost._parse_ts("2026-06-18T12:00:00Z"), self.cost._parse_ts("2026-06-18T14:00:00Z"))
            scopes = self.cost.claude_collect(transcript, window)
            self.assertEqual(scopes.main["anthropic/claude-opus-4.8"].input, 200)

    def test_codex_adapter_no_dedup_fresh_input_and_subagent_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "rollout-2026-06-18T07-00-00-parentthread.jsonl"
            child = root / "rollout-2026-06-18T07-05-00-childthread.jsonl"
            parent.write_text("\n".join(json.dumps(line) for line in [
                {"type": "session_meta", "payload": {"id": "parentthread", "thread_source": "user"}},
                {"type": "turn_context", "payload": {"model": "gpt-5.5"}},
                {"type": "event_msg", "timestamp": "2026-06-18T07:01:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 50, "reasoning_output_tokens": 10}}}},
                {"type": "event_msg", "timestamp": "2026-06-18T07:02:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 500, "cached_input_tokens": 100, "output_tokens": 20, "reasoning_output_tokens": 5}}}},
            ]))
            child.write_text("\n".join(json.dumps(line) for line in [
                {"type": "session_meta", "payload": {"id": "childthread", "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parentthread", "depth": 1}}}}},
                {"type": "turn_context", "payload": {"model": "gpt-5.5"}},
                {"type": "event_msg", "timestamp": "2026-06-18T07:06:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 200, "cached_input_tokens": 50, "output_tokens": 8}}}},
            ]))
            scopes = self.cost.codex_collect("parentthread", sessions_root=root)
            mt = scopes.main["openai/gpt-5.5"]
            # fresh input = (1000-400)+(500-100) = 1000 ; cache_read = 500 ; output = 50+10+20+5 = 85
            self.assertEqual(mt.input, 1000)
            self.assertEqual(mt.cache_read, 500)
            self.assertEqual(mt.output, 85)
            self.assertEqual(scopes.subagents["openai/gpt-5.5"].input, 150)
            self.assertEqual(scopes.subagents["openai/gpt-5.5"].cache_read, 50)

    def test_price_tokens_applies_cache_buckets(self) -> None:
        scopes = self.cost.TokenScopes()
        scopes.add_main(self.cost.ModelTokens(model="anthropic/claude-opus-4.8", input=100, cache_read=1000, cache_creation=10, output=20))
        rates = {"rates": {"anthropic/claude-opus-4.8": {"prompt": 5e-6, "input_cache_read": 5e-7, "input_cache_write": 6.25e-6, "completion": 2.5e-5}}}
        items = self.cost.price_tokens(scopes, rates)
        item = items[0]
        self.assertAlmostEqual(item.breakdown["input"], 100 * 5e-6)
        self.assertAlmostEqual(item.breakdown["cache_read"], 1000 * 5e-7)
        self.assertAlmostEqual(item.breakdown["cache_creation"], 10 * 6.25e-6)
        self.assertAlmostEqual(item.breakdown["output"], 20 * 2.5e-5)

    def test_price_tokens_fails_loud_on_unknown_model(self) -> None:
        scopes = self.cost.TokenScopes()
        scopes.add_main(self.cost.ModelTokens(model="anthropic/unknown-9.9", input=1))
        with self.assertRaisesRegex(RuntimeError, "No OpenRouter rate"):
            self.cost.price_tokens(scopes, {"rates": {}})

    def test_render_appendix_d_is_neutral_and_complete(self) -> None:
        summary = {
            "rate_snapshot": {"openrouter_date": "2026-06-18", "openrouter_source": "https://openrouter.ai/api/v1/models", "vendor_date": "2026-06-18"},
            "vendor_items": [{"source": "web", "calls": 1, "billing": "paid", "unit_rate": 0.005, "unit": "per request", "cost_usd": 0.005, "detail": ""}],
            "vendor_total": 0.005,
            "token_items": [{"model": "anthropic/claude-opus-4.8", "scope": "main", "tokens": {"model": "anthropic/claude-opus-4.8", "input": 100, "cache_read": 1000, "cache_creation": 10, "output": 20, "web_search": 0}, "cost_usd": 1.23, "breakdown": {}}],
            "token_total": 1.23,
            "total_usd": 1.235,
        }
        html = self.cost.render_appendix_d(summary)
        self.assertIn("Appendix D", html)
        self.assertIn("OpenRouter", html)
        self.assertIn("snapshot", html)
        self.assertIn("anthropic/claude-opus-4.8", html)
        self.assertIn("Cache read", html)
        # neutral: no session identity leaks
        self.assertNotIn("session", html.lower().replace("the session", ""))


class AppendixDValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        import validate_html_report

        self.validate = validate_html_report.validate_html

    def _base(self, appendix_d: str) -> str:
        return f"""
        <html><body>
          <section id="brief"></section><div class="theme-toggle"><button data-theme="light"></button></div>
          <section id="index"><table><tr><td><a href="#pick-1">Pick 1</a></td></tr></table></section>
          <section id="top-picks"><article class="card" id="pick-1"><img src="data:image/jpeg;base64,a"><span class="check"><span class="label">Quality signal</span>x</span><span class="check"><span class="label">Style</span>x</span><span class="check"><span class="label">Order</span>x</span></article></section>
          <details open><summary>Appendix A — searches</summary><p>Verdict: pass. reddit queried → results used.</p></details>
          <details open><summary>Appendix B — next steps</summary></details>
          {appendix_d}
        </body></html>
        """

    def test_valid_appendix_d_passes(self) -> None:
        d = '<details open><summary>Appendix D — effective cost to produce this report</summary><div class="details-body"><p>OpenRouter snapshot 2026-06-18.</p><table><tr><td>cache read</td><td>$5.61</td></tr></table></div></details>'
        self.validate(self._base(d))

    def test_closed_appendix_d_rejected(self) -> None:
        d = '<details><summary>Appendix D — effective cost</summary><p>OpenRouter snapshot 2026-06-18 $5 cache</p></details>'
        with self.assertRaisesRegex(ValueError, "Appendix D"):
            self.validate(self._base(d))

    def test_appendix_d_without_snapshot_rejected(self) -> None:
        d = '<details open><summary>Appendix D — effective cost</summary><p>Total $5.00 cache read</p></details>'
        with self.assertRaisesRegex(ValueError, "OpenRouter rate snapshot"):
            self.validate(self._base(d))


class DateWindowDefaultTests(unittest.TestCase):
    def test_searchconfig_default_lookback_is_365(self) -> None:
        self.assertEqual(SearchConfig(query="x").lookback_days, 365)


class NoWindowTests(unittest.TestCase):
    def test_lookback_zero_keeps_all_dated_items(self) -> None:
        from datetime import datetime, timezone
        from core.dates import lookback_window
        from core.models import SearchConfig, SourceItem, SourceResult

        class _OldAdapter:
            source = "reddit"

            def search(self, query, window, config):
                return SourceResult(self.source, {"raw": []}, [
                    SourceItem(id="t", source="reddit", title="ancient", url="https://r.example", published_at="2019-01-01"),
                ])

        fixed = datetime(2026, 6, 19, tzinfo=timezone.utc)
        self.assertEqual(lookback_window(0, fixed).start, "0001-01-01")
        with tempfile.TemporaryDirectory() as tmp:
            config = SearchConfig(query="evergreen", sources=["reddit"], lookback_days=0, output_root=Path(tmp))
            report = run_search(config, adapters={"reddit": _OldAdapter()}, now=lambda: fixed)
            self.assertEqual(len(report.items), 1)
            self.assertEqual(report.window_dropped, {})
            self.assertIn("all dates (ranked by relevance)", report.markdown)

    def test_no_window_keeps_future_dated_items(self) -> None:
        from datetime import datetime, timezone
        from core.dates import lookback_window
        from core.pipeline import _filter_window
        from core.models import SourceItem

        window = lookback_window(0, datetime(2026, 6, 19, tzinfo=timezone.utc))
        future = SourceItem(id="f", source="web", title="post-dated", url="https://e.example", published_at="2027-01-01")
        self.assertEqual(len(_filter_window([future], window)), 1)

    def test_negative_lookback_raises(self) -> None:
        from core.dates import lookback_window

        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            lookback_window(-30)


class CalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        import core.calibrate as calibrate_module

        self.calibrate = calibrate_module

    def test_recommend_low_signal_uses_safe_default(self) -> None:
        days, low, _ = self.calibrate.recommend_lookback([10, 20])
        self.assertEqual(days, 365)
        self.assertTrue(low)

    def test_recommend_tight_ages_pick_small_bucket(self) -> None:
        days, low, _ = self.calibrate.recommend_lookback([1, 5, 10, 20, 40])
        self.assertEqual(days, 90)
        self.assertFalse(low)

    def test_recommend_evergreen_spans_years_recommends_no_window(self) -> None:
        days, low, rationale = self.calibrate.recommend_lookback([22, 300, 800, 1480, 2014])
        self.assertIsNone(days)
        self.assertIn("no window", rationale)

    def test_recommend_mid_range_picks_year_bucket(self) -> None:
        days, _, _ = self.calibrate.recommend_lookback([10, 90, 200, 300, 360])
        self.assertEqual(days, 365)

    def test_calibrate_aggregates_probe_dates_and_recommends(self) -> None:
        from datetime import datetime, timezone
        from core.models import SearchConfig

        now = datetime(2026, 6, 19, tzinfo=timezone.utc)
        probes = [
            ("reddit-discovery", 10, ["2026-06-01", "2024-01-01", "2021-06-19", "2020-06-19"]),
            ("web", 5, ["2026-06-10", "2023-06-19"]),
        ]
        with patch.object(self.calibrate, "_probe_dates", return_value=probes):
            result = self.calibrate.calibrate("evergreen topic", SearchConfig(query="evergreen topic"), now=now)
        self.assertEqual(result.dated, 6)
        # probed reflects TOTAL results (10 + 5), not just the dated ones
        self.assertEqual(result.probed, 15)
        # oldest ~6 years -> spans beyond largest bucket -> no window
        self.assertIsNone(result.recommended_lookback_days)
        self.assertEqual(len(result.probes), 2)

    def test_calibrate_requires_a_web_key(self) -> None:
        from core.models import SearchConfig

        with self.assertRaisesRegex(RuntimeError, "calibration needs a web search key"):
            self.calibrate._probe_dates("topic", SearchConfig(query="topic", config={}))


class WindowDropSurfacingTests(unittest.TestCase):
    def test_render_surfaces_window_dropped_sources(self) -> None:
        report = render_markdown(
            query="best sixth forms",
            window=LookbackWindow(start="2026-05-20", end="2026-06-19"),
            items=[],
            raw_artifact_path=Path("/tmp/raw"),
            window_dropped={"reddit": 10},
        )
        self.assertIn("reddit: 10 collected but dropped as outside the window", report)
        self.assertIn("--lookback-days", report)

    def test_pipeline_records_window_drops(self) -> None:
        from datetime import datetime, timezone
        from core.models import SearchConfig, SourceItem, SourceResult

        class _OldAdapter:
            source = "reddit"

            def search(self, query, window, config):
                return SourceResult(
                    self.source,
                    {"raw": []},
                    [SourceItem(id="t1", source="reddit", title="old thread", url="https://r.example", published_at="2021-01-01")],
                )

        fixed = datetime(2026, 6, 19, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            config = SearchConfig(query="best sixth forms", sources=["reddit"], lookback_days=30, output_root=Path(tmp))
            report = run_search(config, adapters={"reddit": _OldAdapter()}, now=lambda: fixed)
            self.assertEqual(report.window_dropped.get("reddit"), 1)
            self.assertEqual(len(report.items), 0)
            self.assertIn("collected but dropped as outside the window", report.markdown)


class SilentZeroPipelineTests(unittest.TestCase):
    def _adapter(self, source, items):
        class _A:
            def __init__(self, s, it):
                self.source = s
                self._it = it

            def search(self, query, window, config):
                from core.models import SourceResult

                return SourceResult(self.source, {"raw": []}, self._it)

        return _A(source, items)

    def test_deduped_or_truncated_source_is_not_flagged_silent_zero(self) -> None:
        from datetime import datetime, timezone
        from core.models import SearchConfig, SourceItem

        # reddit and hackernews return the SAME url -> dedupe collapses to one item;
        # the losing source still produced an in-window item, so it must NOT be a
        # silent zero. polymarket genuinely returns nothing -> it MUST be flagged.
        same_url = "https://example.com/shared"
        adapters = {
            "reddit": self._adapter("reddit", [SourceItem(id="a", source="reddit", title="A", url=same_url, engagement={"score": 100})]),
            "hackernews": self._adapter("hackernews", [SourceItem(id="b", source="hackernews", title="B", url=same_url, engagement={"score": 1})]),
            "polymarket": self._adapter("polymarket", []),
        }
        fixed = datetime(2026, 6, 19, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            config = SearchConfig(query="x", sources=["reddit", "hackernews", "polymarket"], output_root=Path(tmp))
            report = run_search(config, adapters=adapters, now=lambda: fixed)
            # exactly one of the same-url items survives dedupe
            self.assertEqual(len(report.items), 1)
            self.assertNotIn("reddit: queried, 0 items", report.markdown)
            self.assertNotIn("hackernews: queried, 0 items", report.markdown)
            # polymarket produced nothing -> flagged for sanity check
            self.assertIn("- polymarket: queried, 0 items, no error", report.markdown)


if __name__ == "__main__":
    unittest.main()
