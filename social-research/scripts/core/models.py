from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any


ALL_DATES_START = "0001-01-01"
ALL_DATES_END = "9999-12-31"


DEFAULT_SOURCES = [
    "reddit",
    "hackernews",
    "github",
    "youtube",
    "x",
    "web",
    "polymarket",
    "tiktok",
    "instagram",
    "threads",
    "pinterest",
]


def _clean(value: Any) -> Any:
    if is_dataclass(value):
        return _clean(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if item is not None}
    return value


@dataclass(frozen=True)
class LookbackWindow:
    start: str
    end: str

    def is_all_dates(self) -> bool:
        return self.start == ALL_DATES_START and self.end == ALL_DATES_END

    def to_dict(self) -> dict[str, str]:
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True)
class MediaItem:
    url: str
    kind: str = "image"
    alt: str = ""
    width: int | None = None
    height: int | None = None


@dataclass
class SourceItem:
    id: str
    source: str
    title: str
    url: str
    body: str = ""
    author: str | None = None
    container: str | None = None
    published_at: str | None = None
    engagement: dict[str, int | float] = field(default_factory=dict)
    relevance: float = 0.5
    media: list[MediaItem] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return _clean(self)


@dataclass(frozen=True)
class SourceResult:
    source: str
    raw: Any
    items: list[SourceItem]
    error: str | None = None

    def raw_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"source": self.source, "raw": self.raw}
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class SearchConfig:
    query: str
    sources: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))
    lookback_days: int = 365
    limit: int = 20
    output_root: Path = field(default_factory=lambda: Path.home() / ".social-research" / "searches")
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "sources": list(self.sources),
            "lookback_days": self.lookback_days,
            "limit": self.limit,
            "output_root": str(self.output_root),
        }


@dataclass(frozen=True)
class SearchReport:
    query: str
    window: LookbackWindow
    run_dir: Path
    items: list[SourceItem]
    raw_by_source: dict[str, Any]
    errors_by_source: dict[str, str]
    markdown: str
    # source -> count of items collected but dropped because their date fell
    # outside the window. Surfaces silent over-filtering (the 30-day-default bug).
    window_dropped: dict[str, int] = field(default_factory=dict)

    def normalized_payload(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "window": self.window.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "errors_by_source": dict(self.errors_by_source),
            "window_dropped": dict(self.window_dropped),
        }
