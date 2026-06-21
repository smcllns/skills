from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import re
from typing import Protocol

from .dates import lookback_window, utc_now
from .models import SearchConfig, SearchReport, SourceResult
from .rank import dedupe_and_rank
from .render import render_markdown
from .storage import SearchStorage
from .usage import RunUsage, detect_web_provider

from sources import http as http_module


class SourceAdapter(Protocol):
    source: str

    def search(self, query: str, window, config: SearchConfig) -> SourceResult:
        ...


def run_search(
    config: SearchConfig,
    *,
    adapters: dict[str, SourceAdapter],
    now: Callable[[], datetime] = utc_now,
) -> SearchReport:
    _validate_source_names(config.sources)
    window = lookback_window(config.lookback_days, now())
    storage = SearchStorage(config.output_root, now=now)
    run_dir = storage.create_run_dir(config)
    started_at = now().isoformat()

    http_module.reset_request_counts()
    raw_by_source = {}
    errors_by_source: dict[str, str] = {}
    window_dropped: dict[str, int] = {}
    produced_sources: set[str] = set()
    collected = []
    for source in config.sources:
        adapter = adapters.get(source)
        if adapter is None:
            errors_by_source[source] = "source is not configured"
            raw_by_source[source] = {"source": source, "error": errors_by_source[source], "raw": []}
            continue
        http_module.set_current_source(source)
        try:
            result = adapter.search(config.query, window, config)
        except Exception as exc:
            errors_by_source[source] = f"{type(exc).__name__}: {exc}"
            raw_by_source[source] = {"source": source, "error": errors_by_source[source], "raw": []}
            continue
        finally:
            http_module.set_current_source(None)
        raw_by_source[source] = result.raw_payload()
        if result.error:
            errors_by_source[source] = result.error
        in_window = _filter_window(result.items, window)
        dropped = len(result.items) - len(in_window)
        if dropped:
            window_dropped[source] = dropped
        if in_window:
            produced_sources.add(source)
        collected.extend(in_window)

    calls_by_source = http_module.get_request_counts()
    usage = RunUsage(
        run_dir=str(run_dir),
        query=config.query,
        started_at=started_at,
        ended_at=now().isoformat(),
        window=window.to_dict(),
        limit=config.limit,
        web_provider=detect_web_provider(config.config),
        calls_by_source=calls_by_source,
        errors_by_source=errors_by_source,
        harness=_harness_marker(),
    )

    # Silent zeros: queried sources that produced NOTHING (no error, no window
    # drop, no in-window items) — computed pre-rank so a source whose items were
    # merely deduped/truncated out of the final ranked list is not falsely flagged.
    silent_zero_sources = [
        source
        for source in config.sources
        if source not in produced_sources
        and source not in errors_by_source
        and source not in window_dropped
    ]

    ranked = dedupe_and_rank(collected, query=config.query)[: config.limit]
    markdown = render_markdown(
        query=config.query,
        window=window,
        items=ranked,
        raw_artifact_path=run_dir / "raw",
        errors_by_source=errors_by_source,
        window_dropped=window_dropped,
        silent_zero_sources=silent_zero_sources,
    )
    storage.write_artifacts(
        run_dir=run_dir,
        query={**config.to_dict(), "window": window.to_dict()},
        raw_by_source=raw_by_source,
        normalized=ranked,
        report=markdown,
        usage=usage.to_dict(),
    )
    return SearchReport(
        query=config.query,
        window=window,
        run_dir=run_dir,
        items=ranked,
        raw_by_source=raw_by_source,
        errors_by_source=errors_by_source,
        markdown=markdown,
        window_dropped=window_dropped,
    )


def _harness_marker() -> dict[str, str]:
    """Best-effort agent-harness identity for the usage record's boundary.

    Lets the cost reader locate the right transcript/rollout without re-detecting
    it later. Empty when not run under a recognized harness (e.g. unit tests).
    """
    import os

    marker: dict[str, str] = {}
    if claude_session := os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID"):
        marker["harness"] = "claude"
        marker["session_id"] = claude_session
        if transcript := os.environ.get("CLAUDE_TRANSCRIPT_PATH"):
            marker["transcript_path"] = transcript
    elif os.environ.get("CODEX_THREAD_ID"):
        marker["harness"] = "codex"
        marker["session_id"] = os.environ["CODEX_THREAD_ID"]
    return marker


def _validate_source_names(sources: list[str]) -> None:
    for source in sources:
        if not re.fullmatch(r"[a-z0-9-]+", source):
            raise ValueError(f"source names must be lowercase letters, digits, or hyphens: {source!r}")


def _filter_window(items, window):
    return [
        item
        for item in items
        if item.published_at is None or (window.start <= item.published_at <= window.end)
    ]
