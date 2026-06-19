"""Model-agnostic LLM-token cost reader (cost layer 2) + harness adapters.

Reads the agent harness's own transcript/rollout, sums the *real* token usage by
model and bucket, prices it at current OpenRouter rates (the effective-cost lens),
and combines it with the data-vendor layer (``core.usage``) into one line-itemed
total for Appendix D.

Harness adapters (thin, per the issue's verified mechanics):
  - Claude Code: main transcript + ``<session>/subagents/agent-*.jsonl``. One API
    response = N JSONL lines (one per content block) all repeating the same
    response-level usage -> DEDUP by (message.id, requestId), count usage once.
    Buckets are additive/exclusive: input_tokens (fresh), cache_creation, cache_read.
  - Codex: rollout + ``parent_thread_id`` subagent chain. token_count per turn,
    NO dedup. ``input_tokens`` is INCLUSIVE of ``cached_input_tokens`` (verified:
    total_tokens == input + output), so fresh prompt = input - cached.

Cache pricing is kept (it is the dominant term): cache reads are ~10% of fresh
input, and dominate the input side on a warm session.
"""
from __future__ import annotations

import glob
import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sources.http import get_json

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# OpenRouter pricing keys we map buckets onto.
PRICE_PROMPT = "prompt"
PRICE_CACHE_READ = "input_cache_read"
PRICE_CACHE_WRITE = "input_cache_write"
PRICE_COMPLETION = "completion"
PRICE_WEB_SEARCH = "web_search"


# ---------------------------------------------------------------------------
# Token aggregation model (harness-agnostic)
# ---------------------------------------------------------------------------
@dataclass
class ModelTokens:
    model: str  # OpenRouter slug
    input: int = 0  # fresh, uncached prompt tokens
    cache_read: int = 0
    cache_creation: int = 0
    output: int = 0  # completion (+ reasoning, for Codex)
    web_search: int = 0  # server-side web search requests (count)

    def add(self, other: "ModelTokens") -> None:
        self.input += other.input
        self.cache_read += other.cache_read
        self.cache_creation += other.cache_creation
        self.output += other.output
        self.web_search += other.web_search

    def to_dict(self) -> dict[str, int | str]:
        return {
            "model": self.model,
            "input": self.input,
            "cache_read": self.cache_read,
            "cache_creation": self.cache_creation,
            "output": self.output,
            "web_search": self.web_search,
        }


@dataclass
class TokenScopes:
    """Tokens split by scope so Appendix D can show subagents separately."""

    main: dict[str, ModelTokens] = field(default_factory=dict)
    subagents: dict[str, ModelTokens] = field(default_factory=dict)

    def _bucket(self, scope: dict[str, ModelTokens], model: str) -> ModelTokens:
        return scope.setdefault(model, ModelTokens(model=model))

    def add_main(self, mt: ModelTokens) -> None:
        self._bucket(self.main, mt.model).add(mt)

    def add_subagent(self, mt: ModelTokens) -> None:
        self._bucket(self.subagents, mt.model).add(mt)


# ---------------------------------------------------------------------------
# Model slug mapping: internal harness id -> OpenRouter slug
# ---------------------------------------------------------------------------
def map_model_to_openrouter(model: str) -> str:
    """Map an internal model id to its OpenRouter slug.

    Rules (per the issue): dashes between version numbers -> dots, add the
    provider prefix, strip the ``[1m]`` long-context and ``-fast`` variants
    (they share the base model's OpenRouter rate).
    """
    name = model.strip()
    name = re.sub(r"\[1m\]$", "", name)
    name = re.sub(r"-fast$", "", name)
    # Numeric version dashes -> dots (claude-opus-4-8 -> claude-opus-4.8;
    # gpt-4-1 -> gpt-4.1). gpt-5.5 already uses a dot and is unaffected.
    name = re.sub(r"(?<=\d)-(?=\d)", ".", name)
    if name.startswith("claude"):
        return f"anthropic/{name}"
    if name.startswith("gpt"):
        return f"openai/{name}"
    if "/" in name:
        return name
    return name


# ---------------------------------------------------------------------------
# OpenRouter rate fetch + snapshot
# ---------------------------------------------------------------------------
def fetch_openrouter_rates(*, now: datetime | None = None) -> dict[str, Any]:
    """Fetch live OpenRouter model rates; return a dated snapshot.

    Fails loud if the fetch fails — we never fabricate a rate.
    """
    data = get_json(OPENROUTER_MODELS_URL, headers={"Accept": "application/json"}, timeout=30)
    models = data.get("data") if isinstance(data, dict) else None
    if not models:
        raise RuntimeError("OpenRouter returned no models — cannot price tokens")
    rates: dict[str, dict[str, float]] = {}
    for entry in models:
        slug = entry.get("id")
        pricing = entry.get("pricing") or {}
        if slug and pricing:
            rates[slug] = {k: float(v) for k, v in pricing.items() if _is_number(v)}
    stamp = (now or datetime.now(timezone.utc)).date().isoformat()
    return {"date": stamp, "source": OPENROUTER_MODELS_URL, "rates": rates}


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Token pricing
# ---------------------------------------------------------------------------
@dataclass
class TokenLineItem:
    model: str
    scope: str  # "main" | "subagents"
    tokens: ModelTokens
    cost_usd: float
    breakdown: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "scope": self.scope,
            "tokens": self.tokens.to_dict(),
            "cost_usd": round(self.cost_usd, 6),
            "breakdown": {k: round(v, 6) for k, v in self.breakdown.items()},
        }


def price_tokens(scopes: TokenScopes, rates: dict[str, Any]) -> list[TokenLineItem]:
    items: list[TokenLineItem] = []
    for scope_name, scope in (("main", scopes.main), ("subagents", scopes.subagents)):
        for model in sorted(scope):
            items.append(_price_model(scope_name, scope[model], rates["rates"]))
    return items


def _price_model(scope_name: str, mt: ModelTokens, rates: dict[str, dict[str, float]]) -> TokenLineItem:
    pricing = rates.get(mt.model)
    if pricing is None:
        raise RuntimeError(
            f"No OpenRouter rate for model {mt.model!r} (scope {scope_name}); "
            "refusing to price at $0. Fix the slug mapping or the snapshot."
        )
    breakdown = {
        "input": mt.input * pricing.get(PRICE_PROMPT, 0.0),
        "cache_read": mt.cache_read * pricing.get(PRICE_CACHE_READ, 0.0),
        # OpenAI bills cache writes at the input rate (no cache-write key); fall
        # back to the prompt rate so Codex cache-creation, if ever present, prices.
        "cache_creation": mt.cache_creation * pricing.get(PRICE_CACHE_WRITE, pricing.get(PRICE_PROMPT, 0.0)),
        "output": mt.output * pricing.get(PRICE_COMPLETION, 0.0),
        "web_search": mt.web_search * pricing.get(PRICE_WEB_SEARCH, 0.0),
    }
    return TokenLineItem(mt.model, scope_name, mt, sum(breakdown.values()), breakdown)


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------
def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _in_window(ts: datetime | None, window: tuple[datetime, datetime] | None) -> bool:
    # No window -> include everything. No timestamp -> include (belongs to the
    # measured session; dropping it would understate real usage).
    if window is None or ts is None:
        return True
    start, end = window
    return start <= ts <= end


# ---------------------------------------------------------------------------
# Claude Code adapter
# ---------------------------------------------------------------------------
def claude_collect(transcript_path: str | Path, window: tuple[datetime, datetime] | None = None) -> TokenScopes:
    scopes = TokenScopes()
    transcript = Path(transcript_path)
    if transcript.exists():
        for model, mt in _claude_file_tokens(transcript, window).items():
            scopes.add_main(mt)
    subagent_dir = transcript.with_suffix("") / "subagents"
    for agent_file in sorted(subagent_dir.glob("agent-*.jsonl")):
        for model, mt in _claude_file_tokens(agent_file, window).items():
            scopes.add_subagent(mt)
    return scopes


def _claude_file_tokens(path: Path, window: tuple[datetime, datetime] | None) -> dict[str, ModelTokens]:
    by_model: dict[str, ModelTokens] = {}
    seen: set[tuple[str, str]] = set()
    for line in path.read_text().splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "assistant":
            continue
        message = obj.get("message") or {}
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            continue
        # Dedup: one API response = N content-block lines repeating the same usage.
        # Check the window first so an out-of-window line never "consumes" the key.
        key = (str(message.get("id")), str(obj.get("requestId")))
        if key in seen:
            continue
        if not _in_window(_parse_ts(obj.get("timestamp")), window):
            continue
        seen.add(key)
        slug = map_model_to_openrouter(message.get("model") or "unknown")
        mt = by_model.setdefault(slug, ModelTokens(model=slug))
        mt.input += int(usage.get("input_tokens") or 0)
        mt.cache_read += int(usage.get("cache_read_input_tokens") or 0)
        mt.cache_creation += int(usage.get("cache_creation_input_tokens") or 0)
        mt.output += int(usage.get("output_tokens") or 0)
        server = usage.get("server_tool_use") or {}
        if isinstance(server, dict):
            mt.web_search += int(server.get("web_search_requests") or 0)
    return by_model


# ---------------------------------------------------------------------------
# Codex adapter
# ---------------------------------------------------------------------------
def codex_collect(
    thread_id: str,
    window: tuple[datetime, datetime] | None = None,
    *,
    sessions_root: Path | None = None,
) -> TokenScopes:
    sessions_root = sessions_root or (Path.home() / ".codex" / "sessions")
    index = _codex_index(sessions_root)
    scopes = TokenScopes()
    root = index.get(thread_id)
    if root is None:
        return scopes
    for model, mt in _codex_file_tokens(root["path"], window).items():
        scopes.add_main(mt)
    for child in _codex_descendants(thread_id, index):
        for model, mt in _codex_file_tokens(child["path"], window).items():
            scopes.add_subagent(mt)
    return scopes


def _codex_index(sessions_root: Path) -> dict[str, dict[str, Any]]:
    """Map thread_id -> {id, path, parent} for every rollout under sessions_root."""
    index: dict[str, dict[str, Any]] = {}
    for path in glob.glob(str(sessions_root / "**" / "rollout-*.jsonl"), recursive=True):
        meta = _codex_session_meta(Path(path))
        if not meta:
            continue
        thread_id = meta.get("id")
        if not thread_id:
            continue
        parent = None
        source = meta.get("source")
        if isinstance(source, dict):
            spawn = (source.get("subagent") or {}).get("thread_spawn") or {}
            parent = spawn.get("parent_thread_id")
        parent = parent or meta.get("parent_thread_id")
        index[thread_id] = {"id": thread_id, "path": Path(path), "parent": parent}
    return index


def _codex_session_meta(path: Path) -> dict[str, Any] | None:
    for line in path.read_text().splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "session_meta":
            payload = obj.get("payload")
            return payload if isinstance(payload, dict) else obj
    return None


def _codex_descendants(
    thread_id: str,
    index: dict[str, dict[str, Any]],
    _seen: set[str] | None = None,
) -> list[dict[str, Any]]:
    # _seen guards against cycles in on-disk parent_thread_id metadata (A->B->A
    # would otherwise recurse unbounded). Recurses the chain for depth > 1.
    seen = _seen if _seen is not None else {thread_id}
    result: list[dict[str, Any]] = []
    for tid, info in index.items():
        if info.get("parent") == thread_id and tid not in seen:
            seen.add(tid)
            result.append(info)
            result.extend(_codex_descendants(tid, index, seen))
    return result


def _codex_file_tokens(path: Path, window: tuple[datetime, datetime] | None) -> dict[str, ModelTokens]:
    by_model: dict[str, ModelTokens] = {}
    current_model = "unknown"
    for line in path.read_text().splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("type")
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else None
        if kind == "turn_context" and payload and payload.get("model"):
            current_model = payload["model"]
        elif kind == "session_meta" and payload and payload.get("model"):
            current_model = payload["model"]
        token_info = None
        if kind == "token_count" and isinstance(obj.get("info"), dict):
            token_info = obj["info"]
        elif kind == "event_msg" and payload and payload.get("type") == "token_count" and isinstance(payload.get("info"), dict):
            token_info = payload["info"]
        if token_info is None:
            continue
        if not _in_window(_parse_ts(obj.get("timestamp") or (payload or {}).get("timestamp")), window):
            continue
        # Sum per-turn deltas (last_token_usage); NO dedup for Codex.
        last = token_info.get("last_token_usage") or {}
        slug = map_model_to_openrouter(current_model)
        mt = by_model.setdefault(slug, ModelTokens(model=slug))
        cached = int(last.get("cached_input_tokens") or 0)
        total_input = int(last.get("input_tokens") or 0)
        # input_tokens is INCLUSIVE of cached -> fresh prompt = input - cached.
        mt.input += max(total_input - cached, 0)
        mt.cache_read += cached
        mt.output += int(last.get("output_tokens") or 0) + int(last.get("reasoning_output_tokens") or 0)
    return by_model


# ---------------------------------------------------------------------------
# Appendix D rendering (neutral: models + $ only, no session/user identity)
# ---------------------------------------------------------------------------
def _usd(value: float) -> str:
    if value and abs(value) < 0.01:
        return f"${value:.4f}"
    return f"${value:,.2f}"


def _int(value: int) -> str:
    return f"{value:,}"


def render_appendix_d(cost: dict[str, Any]) -> str:
    """Render the Appendix D ``<details open>`` block from a cost summary.

    Neutral by contract: emits MODEL names, token buckets and dollars only — never
    the session id, transcript path, cwd or user. Matches the A/B/C polish (real
    tables, td.num right-aligned counts, one-line intro).
    """
    vendor_items = cost["vendor_items"]
    token_items = cost["token_items"]
    snapshot = cost["rate_snapshot"]
    vendor_total = cost["vendor_total"]
    token_total = cost["token_total"]
    total = cost["total_usd"]

    vendor_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['source'])}</td>"
        f"<td class=\"num\">{_int(item['calls'])}</td>"
        f"<td>{html.escape(_billing_label(item['billing']))}</td>"
        f"<td class=\"num\">{html.escape(_rate_label(item))}</td>"
        f"<td class=\"num\">{_usd(item['cost_usd'])}</td>"
        "</tr>"
        for item in vendor_items
    ) or "<tr><td>No data-vendor calls recorded</td><td class=\"num\">0</td><td>—</td><td class=\"num\">—</td><td class=\"num\">$0.00</td></tr>"

    token_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['tokens']['model'])}<br><span class=\"meta\">{html.escape(_scope_label(item['scope']))}</span></td>"
        f"<td class=\"num\">{_int(item['tokens']['input'])}</td>"
        f"<td class=\"num\">{_int(item['tokens']['cache_read'])}</td>"
        f"<td class=\"num\">{_int(item['tokens']['cache_creation'])}</td>"
        f"<td class=\"num\">{_int(item['tokens']['output'])}</td>"
        f"<td class=\"num\">{_usd(item['cost_usd'])}</td>"
        "</tr>"
        for item in token_items
    ) or "<tr><td>No LLM tokens recorded</td><td class=\"num\">0</td><td class=\"num\">0</td><td class=\"num\">0</td><td class=\"num\">0</td><td class=\"num\">$0.00</td></tr>"

    web_searches = sum(item["tokens"]["web_search"] for item in token_items)
    web_note = f" {web_searches} server web-search request(s) priced separately." if web_searches else ""

    return f"""<details open>
  <summary>Appendix D — effective cost to produce this report</summary>
  <div class="details-body">
    <p>Fully-loaded marginal cost of producing this report at standard <em>paid</em>
      rates (the price-floor lens: vendor calls billed at paid tier even within a
      free allowance; LLM tokens priced via OpenRouter, cache buckets priced
      separately). Subagent tokens are included.{web_note}</p>
    <h3>Data-vendor API calls</h3>
    <table>
      <thead><tr><th scope="col">Source</th><th scope="col">Calls</th><th scope="col">Billing</th><th scope="col">Unit rate</th><th scope="col">Cost</th></tr></thead>
      <tbody>
        {vendor_rows}
        <tr><td><strong>Vendor subtotal</strong></td><td class="num"></td><td></td><td class="num"></td><td class="num"><strong>{_usd(vendor_total)}</strong></td></tr>
      </tbody>
    </table>
    <h3>LLM tokens by model &amp; bucket</h3>
    <table>
      <thead><tr><th scope="col">Model / scope</th><th scope="col">Input</th><th scope="col">Cache read</th><th scope="col">Cache write</th><th scope="col">Output</th><th scope="col">Cost</th></tr></thead>
      <tbody>
        {token_rows}
        <tr><td><strong>LLM subtotal</strong></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"><strong>{_usd(token_total)}</strong></td></tr>
      </tbody>
    </table>
    <p class="note"><strong>Total effective cost / report: {_usd(total)}</strong>
      ({_usd(vendor_total)} data-vendor + {_usd(token_total)} LLM tokens).</p>
    <p class="meta">Rates: OpenRouter token rates snapshot {html.escape(str(snapshot.get('openrouter_date', 'n/a')))}
      (<a class="ext" href="{html.escape(str(snapshot.get('openrouter_source', OPENROUTER_MODELS_URL)))}">openrouter.ai/api/v1/models</a>);
      paid vendor rates snapshot {html.escape(str(snapshot.get('vendor_date', 'n/a')))}.
      Anthropic's 1h-vs-5m cache-write asymmetry is collapsed to OpenRouter's single
      input_cache_write rate (acceptable approximation).</p>
  </div>
</details>"""


def _billing_label(billing: str) -> str:
    return {
        "paid": "paid",
        "free": "free (no paid tier)",
        "tos_risky": "⚠ ToS-risky at scale",
        "unpriced": "unpriced",
    }.get(billing, billing)


def _scope_label(scope: str) -> str:
    return "subagents" if scope == "subagents" else "main agent"


def _rate_label(item: dict[str, Any]) -> str:
    if item["billing"] == "paid":
        return f"{_usd(item['unit_rate'])} {item['unit']}"
    return "—"
