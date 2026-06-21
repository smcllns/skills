from __future__ import annotations

import contextvars
import json
import os
import ssl
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


USER_AGENT = "social-research/1.0"

# Per-source HTTP request counter. The pipeline tags each adapter's calls with
# the source name (set_current_source); every real HTTP request below records one
# billable call. This is the source of truth for the usage record's vendor call
# counts — measured, not re-derived from code branches, so a Brave 422 retry or a
# Reddit fan-out is counted exactly as it actually happened.
# Assumes SEQUENTIAL execution (the pipeline runs adapters one at a time): the
# source tag is context-local but the counter is a shared Counter, so parallel
# adapters would race on the increment. Make both context-local before adding
# concurrency.
_current_source: contextvars.ContextVar[str | None] = contextvars.ContextVar("social_research_source", default=None)
_request_counts: Counter[str] = Counter()


def set_current_source(source: str | None) -> None:
    _current_source.set(source)


def reset_request_counts() -> None:
    _request_counts.clear()


def get_request_counts() -> dict[str, int]:
    return dict(_request_counts)


def _record_request() -> None:
    source = _current_source.get()
    if source is not None:
        _request_counts[source] += 1


def record_external_request(count: int = 1) -> None:
    """Record billable calls that don't flow through this module's HTTP helpers
    (e.g. a yt-dlp subprocess). Counts against the current source like a real
    request, so such sources still appear in the usage record.
    """
    source = _current_source.get()
    if source is not None and count:
        _request_counts[source] += count


def ensure_ssl_cert_file() -> None:
    if os.environ.get("SSL_CERT_FILE"):
        return
    paths = ssl.get_default_verify_paths()
    if any(cafile and Path(cafile).exists() for cafile in (paths.cafile, paths.openssl_cafile)):
        return
    try:
        import certifi
    except ModuleNotFoundError:
        return
    os.environ["SSL_CERT_FILE"] = certifi.where()


def get_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 20) -> Any:
    ensure_ssl_cert_file()
    _record_request()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_bytes(url: str, *, headers: dict[str, str] | None = None, timeout: int = 30) -> bytes:
    ensure_ssl_cert_file()
    _record_request()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def get_text(url: str, *, headers: dict[str, str] | None = None, timeout: int = 20) -> str:
    ensure_ssl_cert_file()
    _record_request()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None, timeout: int = 20) -> Any:
    ensure_ssl_cert_file()
    _record_request()
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def with_query(url: str, params: dict[str, Any]) -> str:
    return f"{url}?{urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})}"
