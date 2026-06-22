"""Date-window calibration probe (preflight).

The CLI's date window is a recency filter. For evergreen / decision topics
("best sixth forms", "best keyboards") the relevant discussion is naturally years
old, so a short window silently discards collected evidence. This module runs a
couple of CHEAP probes against the source that reliably returns dates — Brave
``site:reddit.com`` discovery (verified: ~10/10 results carry ``page_age``) plus a
plain web probe — looks at the age distribution of the top results, and recommends
a ``--lookback-days`` (or "no window: rank by relevance" when evidence spans
years).

Network probing and the recommendation are split so the recommendation logic is
unit-testable without HTTP. Probing requires ``BRAVE_API_KEY`` for the strong
reddit-discovery signal; it falls back to the configured web provider otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .dates import date_only
from .models import SearchConfig

# Lookback buckets we snap a recommendation to. None = no window (rank by relevance).
LOOKBACK_BUCKETS = (30, 90, 180, 365, 730, 1095)
# Below this many dated samples we don't trust the distribution -> safe default.
MIN_SIGNAL = 3
SAFE_DEFAULT_DAYS = 365


@dataclass
class CalibrationResult:
    query: str
    probed: int
    dated: int
    ages_days: list[int] = field(default_factory=list)
    recommended_lookback_days: int | None = SAFE_DEFAULT_DAYS
    low_signal: bool = False
    rationale: str = ""
    probes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def newest_days(self) -> int | None:
        return min(self.ages_days) if self.ages_days else None

    @property
    def oldest_days(self) -> int | None:
        return max(self.ages_days) if self.ages_days else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "probed": self.probed,
            "dated": self.dated,
            "newest_days": self.newest_days,
            "oldest_days": self.oldest_days,
            "p90_days": _percentile(self.ages_days, 90) if self.ages_days else None,
            "recommended_lookback_days": self.recommended_lookback_days,
            "recommended_flag": "--lookback-days 0  (no window: rank by relevance)" if self.recommended_lookback_days is None else f"--lookback-days {self.recommended_lookback_days}",
            "low_signal": self.low_signal,
            "rationale": self.rationale,
            "probes": self.probes,
        }


def recommend_lookback(ages_days: list[int]) -> tuple[int | None, bool, str]:
    """Pick a lookback from observed result ages (days old).

    Returns (recommended_days_or_None, low_signal, rationale). Uses the 90th
    percentile age (not the max) so one ancient outlier doesn't blow up the
    window, then snaps to the smallest bucket that covers it; spans beyond the
    largest bucket recommend no window at all.
    """
    if len(ages_days) < MIN_SIGNAL:
        return (
            SAFE_DEFAULT_DAYS,
            True,
            f"only {len(ages_days)} dated result(s) — too few to calibrate; using safe default {SAFE_DEFAULT_DAYS}d.",
        )
    p90 = _percentile(ages_days, 90)
    if p90 > LOOKBACK_BUCKETS[-1]:
        return (
            None,
            False,
            f"90th-percentile age is {p90}d, beyond the largest bucket ({LOOKBACK_BUCKETS[-1]}d) — recommend no window (rank by relevance).",
        )
    bucket = next(b for b in LOOKBACK_BUCKETS if b >= p90)
    return (
        bucket,
        False,
        f"90% of dated results within {p90}d (newest {min(ages_days)}d, oldest {max(ages_days)}d) — recommend --lookback-days {bucket}.",
    )


def calibrate(
    query: str,
    config: SearchConfig,
    *,
    now: datetime | None = None,
) -> CalibrationResult:
    current = now or datetime.now(timezone.utc)
    ages: list[int] = []
    probes: list[dict[str, Any]] = []
    probed = 0

    for source, total, dates in _probe_dates(query, config):
        probes.append({"source": source, "calls": 1, "results": total, "dated": len(dates)})
        probed += total
        for iso in dates:
            age = _age_days(iso, current)
            if age is not None:
                ages.append(age)

    recommended, low_signal, rationale = recommend_lookback(ages)
    return CalibrationResult(
        query=query,
        probed=probed,
        dated=len(ages),
        ages_days=sorted(ages),
        recommended_lookback_days=recommended,
        low_signal=low_signal,
        rationale=rationale,
        probes=probes,
    )


def _probe_dates(query: str, config: SearchConfig) -> list[tuple[str, int, list[str]]]:
    """Run the cheap date probes, returning (source, total_results, [iso_date,...])
    per probe — total_results lets the diagnostics report how many results carried
    a usable date vs how many were undated.

    Prefers Brave reddit-discovery (strong date signal) + a Brave web probe.
    Falls back to the configured web provider when Brave is absent.
    """
    from sources.http import get_json, post_json, with_query

    cfg = config.config
    results: list[tuple[str, int, list[str]]] = []
    brave = cfg.get("BRAVE_API_KEY")
    if brave:
        headers = {"Accept": "application/json", "X-Subscription-Token": str(brave)}
        for label, q in (("reddit-discovery", f"site:reddit.com {query}"), ("web", query)):
            url = with_query("https://api.search.brave.com/res/v1/web/search", {"q": q, "count": 20})
            data = get_json(url, headers=headers)
            hits = (data.get("web", {}) or {}).get("results", [])
            dates = [d for r in hits if (d := date_only(r.get("page_age")))]
            results.append((label, len(hits), dates))
        return results

    if serper := cfg.get("SERPER_API_KEY"):
        data = post_json("https://google.serper.dev/search", {"q": query, "num": 20}, headers={"X-API-KEY": str(serper)})
        hits = data.get("organic", [])
        dates = [d for item in hits if (d := date_only(item.get("date")))]
        results.append(("serper", len(hits), dates))
        return results

    raise RuntimeError(
        "calibration needs a web search key (BRAVE_API_KEY preferred, SERPER_API_KEY supported) to probe result dates"
    )


def _age_days(iso_date: str, now: datetime) -> int | None:
    try:
        dt = datetime.fromisoformat(iso_date)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max((now - dt).days, 0)


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return ordered[rank]
