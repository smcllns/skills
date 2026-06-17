#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from core.config import load_config
from core.models import SearchConfig, SourceItem, SourceResult
from core.pipeline import run_search
from sources import default_adapters


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a saved social research search.")
    parser.add_argument("query", help="Search query/topic")
    parser.add_argument("--sources", help="Comma-separated source list")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output-root", type=Path, default=Path.home() / ".social-research" / "searches")
    parser.add_argument("--mock", action="store_true", help="Use a local mock source for smoke testing")
    args = parser.parse_args()

    config_values = load_config()
    sources = [part.strip().lower() for part in args.sources.split(",") if part.strip()] if args.sources else None
    adapters = default_adapters()
    if args.mock:
        sources = ["mock"]
        adapters = {"mock": MockAdapter()}
    config = SearchConfig(
        query=args.query,
        sources=sources or list(adapters.keys()),
        lookback_days=args.lookback_days,
        limit=args.limit,
        output_root=args.output_root,
        config=config_values,
    )
    report = run_search(config, adapters=adapters)
    print(report.run_dir)
    return 0


class MockAdapter:
    source = "mock"

    def search(self, query, window, config: SearchConfig) -> SourceResult:
        return SourceResult(
            source=self.source,
            raw={"items": [{"id": "mock-1", "query": query}]},
            items=[
                SourceItem(
                    id="mock-1",
                    source=self.source,
                    title=f"{query} mock evidence",
                    url="https://example.com/social-research/mock",
                    body="Mock evidence for validating the saved-search pipeline.",
                    published_at=window.end,
                    engagement={"score": 1},
                )
            ],
        )


if __name__ == "__main__":
    raise SystemExit(main())
