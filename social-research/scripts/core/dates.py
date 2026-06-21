from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import LookbackWindow


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def lookback_window(days: int, now: datetime | None = None) -> LookbackWindow:
    if days < 0:
        # Guard typos like `--lookback-days -30`; 0 is the explicit no-window opt-in.
        raise ValueError("lookback days cannot be negative; use 0 for no window")
    current = now or utc_now()
    end = current.date()
    if days == 0:
        # No window: rank by relevance, keep ALL dated items including any
        # future-dated ones (what --calibrate recommends for evergreen topics
        # whose evidence spans years). Sentinels span the full date range.
        return LookbackWindow(start="0001-01-01", end="9999-12-31")
    start = end - timedelta(days=days)
    return LookbackWindow(start=start.isoformat(), end=end.isoformat())


def date_only(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if text.isdigit() and len(text) == 8:
        try:
            return datetime.strptime(text, "%Y%m%d").date().isoformat()
        except ValueError:
            return None
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        pass
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None
