#!/usr/bin/env python3
"""Effective per-report cost reader for social-research (Appendix D).

Two cost layers, one line-itemed total:
  1. Data-vendor API calls — measured per run (``usage.json``), priced at paid tier.
  2. LLM tokens — read from the agent harness's own transcript/rollout, priced via
     live OpenRouter rates (cache buckets separately), subagents included.

Boundary mechanism (explicit start/end markers — the robust option):
  begin   record a boundary: harness + session id(s) + start timestamp.
  finish  close it: window = [start, now]; aggregate every CLI run + agent turn in
          that window under the one boundary; emit cost.json + the Appendix D HTML.

Rollup rule: a report may span several CLI invocations and many agent turns. They
roll up by TIME-WINDOW UNION under one boundary — every run whose usage.json
started within [begin, finish] and every transcript/rollout turn timestamped in the
same window. Simplest correct rollup; documented for review.

Usage:
  cost_report.py begin  [--label L] [--output-root R]
  cost_report.py finish [<id> | --latest] [--out cost.json] [--appendix appendix_d.html]
  cost_report.py report --since ISO [--until ISO] [--harness claude|codex]
                        [--session ID] [--transcript PATH] [--output-root R]
                        [--out cost.json] [--appendix appendix_d.html]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import cost as cost_mod
from core.usage import VENDOR_RATES_SNAPSHOT, VendorLineItem, price_vendor_calls

BOUNDARY_DIR = Path.home() / ".social-research" / "cost-boundaries"
DEFAULT_OUTPUT_ROOT = Path.home() / ".social-research" / "searches"


# ---------------------------------------------------------------------------
# Harness detection
# ---------------------------------------------------------------------------
def detect_harness() -> dict[str, Any]:
    if session := (os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID")):
        return {
            "harness": "claude",
            "session_id": session,
            "transcript_path": os.environ.get("CLAUDE_TRANSCRIPT_PATH", ""),
        }
    if thread := os.environ.get("CODEX_THREAD_ID"):
        return {"harness": "codex", "session_id": thread, "transcript_path": ""}
    return {"harness": "", "session_id": "", "transcript_path": ""}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# begin / finish boundary store
# ---------------------------------------------------------------------------
def cmd_begin(args: argparse.Namespace) -> int:
    harness = detect_harness()
    start = _now()
    boundary_id = f"boundary-{start.strftime('%Y%m%d-%H%M%S')}"
    boundary = {
        "id": boundary_id,
        "label": args.label or "",
        "started_at": start.isoformat(),
        "output_root": str(args.output_root or DEFAULT_OUTPUT_ROOT),
        **harness,
    }
    BOUNDARY_DIR.mkdir(parents=True, exist_ok=True)
    (BOUNDARY_DIR / f"{boundary_id}.json").write_text(json.dumps(boundary, indent=2) + "\n")
    if not harness["harness"]:
        print("warning: no Claude/Codex session detected in env; token costs will be empty at finish", file=sys.stderr)
    print(boundary_id)
    return 0


def _load_boundary(identifier: str | None, latest: bool) -> dict[str, Any]:
    if latest or identifier is None:
        files = sorted(BOUNDARY_DIR.glob("boundary-*.json"))
        if not files:
            raise SystemExit("no boundaries found; run `cost_report.py begin` first")
        return json.loads(files[-1].read_text())
    path = BOUNDARY_DIR / (identifier if identifier.endswith(".json") else f"{identifier}.json")
    if not path.exists():
        raise SystemExit(f"boundary not found: {path}")
    return json.loads(path.read_text())


def cmd_finish(args: argparse.Namespace) -> int:
    boundary = _load_boundary(args.id, args.latest)
    summary = build_cost(
        harness=boundary.get("harness", ""),
        session_id=boundary.get("session_id", ""),
        transcript_path=boundary.get("transcript_path", ""),
        since=boundary["started_at"],
        until=_now().isoformat(),
        output_root=Path(boundary.get("output_root") or DEFAULT_OUTPUT_ROOT),
        boundary_id=boundary["id"],
    )
    _emit(summary, args.out, args.appendix)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    harness = args.harness or detect_harness()["harness"]
    session = args.session or detect_harness()["session_id"]
    transcript = args.transcript or detect_harness()["transcript_path"]
    summary = build_cost(
        harness=harness,
        session_id=session,
        transcript_path=transcript,
        since=args.since,
        until=args.until or _now().isoformat(),
        output_root=args.output_root or DEFAULT_OUTPUT_ROOT,
        boundary_id=None,
    )
    _emit(summary, args.out, args.appendix)
    return 0


# ---------------------------------------------------------------------------
# Core assembly
# ---------------------------------------------------------------------------
def build_cost(
    *,
    harness: str,
    session_id: str,
    transcript_path: str,
    since: str,
    until: str,
    output_root: Path,
    boundary_id: str | None,
) -> dict[str, Any]:
    start = cost_mod._parse_ts(since)
    end = cost_mod._parse_ts(until)
    window = (start, end) if start and end else None

    # --- Layer 2: LLM tokens via the harness adapter ---
    scopes = cost_mod.TokenScopes()
    if harness == "claude" and transcript_path:
        scopes = cost_mod.claude_collect(transcript_path, window)
    elif harness == "codex" and session_id:
        scopes = cost_mod.codex_collect(session_id, window)

    rates = cost_mod.fetch_openrouter_rates()
    token_items = cost_mod.price_tokens(scopes, rates)
    token_total = sum(item.cost_usd for item in token_items)

    # --- Layer 1: data-vendor calls from run usage records in window ---
    vendor_items, runs = _collect_vendor(output_root, window)
    vendor_total = sum(item.cost_usd for item in vendor_items)

    return {
        "boundary_id": boundary_id,
        "harness": harness,
        "session_id": session_id,
        "window": {"start": since, "end": until},
        "runs": runs,
        "rate_snapshot": {
            "openrouter_date": rates["date"],
            "openrouter_source": rates["source"],
            "vendor_date": VENDOR_RATES_SNAPSHOT["date"],
            "vendor_note": VENDOR_RATES_SNAPSHOT["note"],
        },
        "vendor_items": [item.to_dict() for item in vendor_items],
        "vendor_total": round(vendor_total, 6),
        "token_items": [item.to_dict() for item in token_items],
        "token_total": round(token_total, 6),
        "total_usd": round(vendor_total + token_total, 6),
    }


def _collect_vendor(output_root: Path, window: tuple[datetime, datetime] | None) -> tuple[list, list[str]]:
    """Price each run with ITS OWN limit/web_provider, then aggregate by source.

    Pricing per-run (rather than merging call counts first) keeps X amortization
    and web-provider selection correct even when one report spans runs with
    different --limit values or different web providers.
    """
    runs: list[str] = []
    per_source: dict[str, list[VendorLineItem]] = {}
    for usage_file in sorted(Path(output_root).glob("*/usage.json")):
        try:
            usage = json.loads(usage_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        started = cost_mod._parse_ts(usage.get("started_at"))
        if not cost_mod._in_window(started, window):
            continue
        runs.append(usage.get("run_dir", str(usage_file.parent)))
        items = price_vendor_calls(
            dict(usage.get("calls_by_source") or {}),
            limit=usage.get("limit", 20),
            web_provider=usage.get("web_provider"),
        )
        for item in items:
            per_source.setdefault(item.source, []).append(item)
    return [_aggregate_source(per_source[source]) for source in sorted(per_source)], runs


def _aggregate_source(parts: list[VendorLineItem]) -> VendorLineItem:
    """Sum a source's per-run line items. When the per-run unit rate varies across
    runs (e.g. a `web` row priced under Brave in one run and Serper in another),
    show the blended effective rate + a "blended" marker so the displayed rate
    matches the summed cost instead of silently keeping the first run's label.
    """
    base = parts[0]
    if len(parts) == 1:
        return base
    calls = sum(part.calls for part in parts)
    cost = sum(part.cost_usd for part in parts)
    if len({part.unit_rate for part in parts}) == 1:
        return replace(base, calls=calls, cost_usd=cost)
    blended_rate = cost / calls if calls else 0.0
    return replace(
        base,
        calls=calls,
        cost_usd=cost,
        unit_rate=blended_rate,
        unit=f"{base.unit} (blended)",
        detail="blended rate across runs with differing tiers/providers",
    )


def _emit(summary: dict[str, Any], out: Path | None, appendix: Path | None) -> None:
    appendix_html = cost_mod.render_appendix_d(summary)
    if out:
        out.write_text(json.dumps(summary, indent=2) + "\n")
    if appendix:
        appendix.write_text(appendix_html + "\n")
    print(json.dumps({
        "vendor_total": summary["vendor_total"],
        "token_total": summary["token_total"],
        "total_usd": summary["total_usd"],
        "runs": len(summary["runs"]),
        "models": [item["tokens"]["model"] for item in summary["token_items"]],
        "cost_json": str(out) if out else None,
        "appendix_html": str(appendix) if appendix else None,
    }, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    begin = sub.add_parser("begin", help="record a cost boundary at report start")
    begin.add_argument("--label", default="")
    begin.add_argument("--output-root", type=Path)
    begin.set_defaults(func=cmd_begin)

    finish = sub.add_parser("finish", help="close a boundary and emit Appendix D")
    finish.add_argument("id", nargs="?")
    finish.add_argument("--latest", action="store_true")
    finish.add_argument("--out", type=Path)
    finish.add_argument("--appendix", type=Path)
    finish.set_defaults(func=cmd_finish)

    report = sub.add_parser("report", help="one-shot cost report for an explicit window")
    report.add_argument("--since", required=True)
    report.add_argument("--until")
    report.add_argument("--harness", choices=["claude", "codex"])
    report.add_argument("--session")
    report.add_argument("--transcript")
    report.add_argument("--output-root", type=Path)
    report.add_argument("--out", type=Path)
    report.add_argument("--appendix", type=Path)
    report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
