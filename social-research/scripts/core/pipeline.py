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

    raw_by_source = {}
    errors_by_source: dict[str, str] = {}
    collected = []
    for source in config.sources:
        adapter = adapters.get(source)
        if adapter is None:
            errors_by_source[source] = "source is not configured"
            raw_by_source[source] = {"source": source, "error": errors_by_source[source], "raw": []}
            continue
        try:
            result = adapter.search(config.query, window, config)
        except Exception as exc:
            errors_by_source[source] = f"{type(exc).__name__}: {exc}"
            raw_by_source[source] = {"source": source, "error": errors_by_source[source], "raw": []}
            continue
        raw_by_source[source] = result.raw_payload()
        if result.error:
            errors_by_source[source] = result.error
        collected.extend(_filter_window(result.items, window))

    ranked = dedupe_and_rank(collected, query=config.query)[: config.limit]
    markdown = render_markdown(
        query=config.query,
        window=window,
        items=ranked,
        raw_artifact_path=run_dir / "raw",
        errors_by_source=errors_by_source,
    )
    storage.write_artifacts(
        run_dir=run_dir,
        query={**config.to_dict(), "window": window.to_dict()},
        raw_by_source=raw_by_source,
        normalized=ranked,
        report=markdown,
    )
    return SearchReport(
        query=config.query,
        window=window,
        run_dir=run_dir,
        items=ranked,
        raw_by_source=raw_by_source,
        errors_by_source=errors_by_source,
        markdown=markdown,
    )


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
