from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


USER_AGENT = "social-research/1.0"


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
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_bytes(url: str, *, headers: dict[str, str] | None = None, timeout: int = 30) -> bytes:
    ensure_ssl_cert_file()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def get_text(url: str, *, headers: dict[str, str] | None = None, timeout: int = 20) -> str:
    ensure_ssl_cert_file()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None, timeout: int = 20) -> Any:
    ensure_ssl_cert_file()
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
