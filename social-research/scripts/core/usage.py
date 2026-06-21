"""Per-run usage record + data-vendor billing catalog (cost layer 1).

The pipeline measures actual HTTP requests per source (see ``sources.http``'s
request counter) and writes a ``usage.json`` into each run directory. The cost
reader (``core.cost`` / ``cost_report.py``) reads those records to price the
data-vendor layer at standard *paid* tier — the "effective cost" lens — even
where a free allowance exists.

Two cost layers feed Appendix D:
  1. Data-vendor API calls  → priced here (real dollars per HTTP request).
  2. LLM tokens             → priced in ``core.cost`` via OpenRouter.

Vendor rates are pulled from each vendor's public pricing page and SNAPSHOTTED
with a date for reproducibility; pricing pages have no API, so the snapshot is a
hand-maintained constant. Re-confirm and bump ``VENDOR_RATES_SNAPSHOT["date"]``
when rates change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data-vendor billing catalog
# ---------------------------------------------------------------------------
# Snapshot of standard *paid-tier* rates, per HTTP request unless noted.
# Confirmed against each vendor's pricing page on the date below.
VENDOR_RATES_SNAPSHOT: dict[str, Any] = {
    "date": "2026-06-18",
    "currency": "USD",
    "note": (
        "Entry paid-tier rates, per HTTP request unless noted. Effective-cost "
        "lens: priced at paid tier even within a free allowance. X is billed "
        "per post read (pay-per-use); we amortize as calls x lookback limit."
    ),
    "web_provider_rates": {
        # The `web` source uses the first configured provider in this precedence;
        # priced at that provider's per-request rate.
        "brave": {"rate": 0.005, "tier": "Brave Search $5 / 1k requests", "url": "https://brave.com/search/api/"},
        "serper": {"rate": 0.001, "tier": "Serper Starter $50 / 50k credits", "url": "https://serper.dev/"},
        "exa": {"rate": 0.007, "tier": "Exa Search $7 / 1k requests", "url": "https://exa.ai/pricing"},
        "parallel": {"rate": 0.005, "tier": "Parallel Search base $0.005 / request (10 results)", "url": "https://parallel.ai/pricing"},
    },
    "scrapecreators": {"rate": 0.00188, "tier": "ScrapeCreators Freelance $47 / 25k credits", "url": "https://scrapecreators.com/"},
    "x_per_read": {"rate": 0.005, "tier": "X API pay-per-use $0.005 / post read (Feb 2026)", "url": "https://docs.x.com/x-api"},
    "geoapify": {"rate": 0.0002, "tier": "Geoapify entry $59 / 10k credits per day (~$0.0002 / credit)", "url": "https://www.geoapify.com/pricing/"},
}

# Sources billed via the ScrapeCreators API (1 credit per request each).
SCRAPECREATORS_SOURCES = frozenset({"tiktok", "instagram", "threads", "pinterest"})

# Free APIs with no paid tier -> $0, but still real calls worth recording.
FREE_SOURCES = frozenset({"github", "hackernews", "polymarket", "mock"})

# Scraping paths that are ToS-risky at service scale. $0 monetary, but the
# effective-cost view must FLAG them, not bury them as free.
TOS_RISKY_SOURCES = frozenset({"reddit", "youtube"})

# Credential precedence the WebAdapter uses to pick a provider (must mirror
# sources/web.py). Recorded into the usage record so the cost reader can price
# the `web` source at the actually-used provider's rate.
WEB_PROVIDER_PRECEDENCE = (
    ("BRAVE_API_KEY", "brave"),
    ("SERPER_API_KEY", "serper"),
    ("EXA_API_KEY", "exa"),
    ("PARALLEL_API_KEY", "parallel"),
)


def detect_web_provider(config: dict[str, Any]) -> str | None:
    for key, provider in WEB_PROVIDER_PRECEDENCE:
        if config.get(key):
            return provider
    return None


@dataclass(frozen=True)
class VendorLineItem:
    source: str
    calls: int
    billing: str  # "paid" | "free" | "tos_risky" | "unpriced"
    unit_rate: float
    unit: str
    cost_usd: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "calls": self.calls,
            "billing": self.billing,
            "unit_rate": self.unit_rate,
            "unit": self.unit,
            "cost_usd": round(self.cost_usd, 6),
            "detail": self.detail,
        }


@dataclass
class RunUsage:
    """Usage for one CLI invocation (one run directory)."""

    run_dir: str
    query: str
    started_at: str
    ended_at: str
    window: dict[str, str]
    limit: int
    web_provider: str | None
    calls_by_source: dict[str, int] = field(default_factory=dict)
    errors_by_source: dict[str, str] = field(default_factory=dict)
    harness: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_dir": self.run_dir,
            "query": self.query,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "window": self.window,
            "limit": self.limit,
            "web_provider": self.web_provider,
            "calls_by_source": dict(self.calls_by_source),
            "errors_by_source": dict(self.errors_by_source),
            "harness": dict(self.harness),
        }


def price_vendor_calls(
    calls_by_source: dict[str, int],
    *,
    limit: int,
    web_provider: str | None,
) -> list[VendorLineItem]:
    """Price each source's measured HTTP calls at standard paid tier."""
    items: list[VendorLineItem] = []
    for source in sorted(calls_by_source):
        calls = calls_by_source[source]
        items.append(_price_source(source, calls, limit=limit, web_provider=web_provider))
    return items


def _price_source(source: str, calls: int, *, limit: int, web_provider: str | None) -> VendorLineItem:
    if source == "web":
        provider = web_provider or "brave"
        entry = VENDOR_RATES_SNAPSHOT["web_provider_rates"].get(provider, VENDOR_RATES_SNAPSHOT["web_provider_rates"]["brave"])
        rate = entry["rate"]
        return VendorLineItem(source, calls, "paid", rate, "per request", calls * rate, f"{provider}: {entry['tier']}")
    if source in SCRAPECREATORS_SOURCES:
        rate = VENDOR_RATES_SNAPSHOT["scrapecreators"]["rate"]
        return VendorLineItem(source, calls, "paid", rate, "per request", calls * rate, VENDOR_RATES_SNAPSHOT["scrapecreators"]["tier"])
    if source == "x":
        rate = VENDOR_RATES_SNAPSHOT["x_per_read"]["rate"]
        reads = calls * max(limit, 1)
        return VendorLineItem(
            source, calls, "paid", rate, "per post read",
            reads * rate,
            f"{VENDOR_RATES_SNAPSHOT['x_per_read']['tier']}; "
            f"{calls} call(s) × {max(limit, 1)} reads/call = {reads:,} reads × ${rate} = ${reads * rate:,.2f}",
        )
    if source == "geoapify":
        rate = VENDOR_RATES_SNAPSHOT["geoapify"]["rate"]
        return VendorLineItem(source, calls, "paid", rate, "per credit", calls * rate, VENDOR_RATES_SNAPSHOT["geoapify"]["tier"])
    if source in FREE_SOURCES:
        return VendorLineItem(source, calls, "free", 0.0, "per request", 0.0, "no paid tier")
    if source in TOS_RISKY_SOURCES:
        return VendorLineItem(
            source, calls, "tos_risky", 0.0, "per request", 0.0,
            "scraping path — $0 monetary but ToS-risky at service scale; flagged, not billed",
        )
    return VendorLineItem(source, calls, "unpriced", 0.0, "per request", 0.0, "source not in billing catalog")


def merge_run_calls(run_dir: Path, source: str, count: int) -> None:
    """Add `count` calls for `source` into an existing run's usage.json.

    Used by side processes (e.g. build_map.py's Geoapify calls) that run after
    the main pipeline has already written the run's usage record.
    """
    import json

    path = Path(run_dir) / "usage.json"
    if not path.exists():
        return
    data = json.loads(path.read_text())
    calls = data.setdefault("calls_by_source", {})
    calls[source] = calls.get(source, 0) + count
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
