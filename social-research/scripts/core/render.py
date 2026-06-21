from __future__ import annotations

from collections import Counter
from pathlib import Path

from .models import LookbackWindow, SourceItem


def render_markdown(
    *,
    query: str,
    window: LookbackWindow,
    items: list[SourceItem],
    raw_artifact_path: Path,
    errors_by_source: dict[str, str] | None = None,
    window_dropped: dict[str, int] | None = None,
    silent_zero_sources: list[str] | None = None,
) -> str:
    window_line = (
        "Window: all dates (ranked by relevance)"
        if window.start == "0001-01-01"
        else f"Window: {window.start} to {window.end}"
    )
    lines = [
        f"# Social Research: {query}",
        "",
        window_line,
        "",
        "## Source Coverage",
        "",
    ]
    coverage = Counter(item.source for item in items)
    if coverage:
        for source, count in sorted(coverage.items()):
            lines.append(f"- {source}: {count}")
    else:
        lines.append("- no items collected")
    if errors_by_source:
        for source, error in sorted(errors_by_source.items()):
            lines.append(f"- {source}: error: {error}")
    if window_dropped:
        for source, dropped in sorted(window_dropped.items()):
            lines.append(
                f"- {source}: {dropped} collected but dropped as outside the window "
                f"({window.start} to {window.end}) — widen with `--lookback-days` (try `--calibrate`)"
            )

    # Sources that were queried but produced no items at all (no error, no window
    # drop, nothing even before dedupe/ranking) — a silent zero. For high-coverage
    # sources this is usually a defect (over-narrow query / broken connection), not
    # a true absence; the adversarial review must interrogate it, not accept "no
    # data". Computed in the pipeline from pre-rank production so a source whose
    # items were merely deduped or truncated out of the final list is NOT flagged.
    if silent_zero_sources:
        lines.append("")
        lines.append("### Sanity check — sources returned 0 (no error)")
        lines.append(
            "Verify these are genuinely empty, not a broken connection / too-narrow "
            "query. Implausible for high-coverage sources — inspect `raw/<source>.json` "
            "and re-probe with a simpler query before accepting:"
        )
        for source in sorted(silent_zero_sources):
            lines.append(f"- {source}: queried, 0 items, no error")

    lines.extend(["", "## Top Findings", ""])
    if not items:
        lines.append("No evidence items were collected.")
    for index, item in enumerate(items, start=1):
        title = item.title or item.url or item.id
        link = f"[{title}]({item.url})" if item.url else title
        meta = " · ".join(part for part in [item.source, item.published_at or "", _engagement_text(item)] if part)
        lines.append(f"{index}. {link}")
        if meta:
            lines.append(f"   {meta}")
        quote = _quote(item)
        if quote:
            lines.append(f"   > {quote}")
        image = next((media for media in item.media if media.kind == "image" and media.url), None)
        if image:
            alt = image.alt or item.title or "source image"
            lines.append(f"   ![{alt}]({image.url})")
        lines.append("")

    lines.extend(["## Key Patterns", ""])
    for pattern in _patterns(items):
        lines.append(f"- {pattern}")
    lines.extend(["", f"Raw artifacts: `{raw_artifact_path}`", ""])
    return "\n".join(lines)


def _engagement_text(item: SourceItem) -> str:
    if not item.engagement:
        return ""
    return ", ".join(f"{key}={value:g}" for key, value in sorted(item.engagement.items()))


def _quote(item: SourceItem) -> str:
    text = " ".join((item.body or item.title).split())
    if not text:
        return ""
    return text[:280]


def _patterns(items: list[SourceItem]) -> list[str]:
    if not items:
        return ["No source produced evidence for this query/window."]
    counts = Counter(item.source for item in items)
    top_source, top_count = counts.most_common(1)[0]
    patterns = [f"{top_source} contributed the most evidence ({top_count} item{'s' if top_count != 1 else ''})."]
    media_count = sum(1 for item in items if item.media)
    if media_count:
        patterns.append(f"{media_count} item{'s' if media_count != 1 else ''} included media useful for visual inspection.")
    dated_count = sum(1 for item in items if item.published_at)
    patterns.append(f"{dated_count}/{len(items)} items had explicit dates.")
    return patterns
