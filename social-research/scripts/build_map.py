#!/usr/bin/env python3
"""Build a beautiful, offline map for the HTML report from a list of places.

Geocodes each place with the Geoapify Geocoding API (cached, fail-loud on
no-match), renders two Geoapify Static Maps (positron for light mode,
dark-matter for dark) with numbered/lettered markers auto-fit to the points'
bounding box, fetches both images, and returns them as base64 data-URIs so the
report stays a single offline file.

Renders only when ``GEOAPIFY_API_KEY`` is configured. With no key — or if every
place fails to geocode, or the static-map render fails — returns ``None`` so the
caller falls back to the plain ordered location list + map links.

Usable as a library (``build_map(...)``) and as a CLI (``--places-file`` /
``--places-json``; ``--out-dir`` writes light.<fmt>, dark.<fmt>, map.json — default fmt jpeg).
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import load_config
from core.usage import merge_run_calls

from sources.http import (
    get_bytes,
    get_json,
    get_request_counts,
    reset_request_counts,
    set_current_source,
    with_query,
)


GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
STATICMAP_URL = "https://maps.geoapify.com/v1/staticmap"

# Required attribution — OpenStreetMap data + Geoapify rendering. Never strip it.
ATTRIBUTION_TEXT = "© OpenStreetMap contributors · Powered by Geoapify"
ATTRIBUTION_HTML = (
    '© <a class="ext" href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    'contributors · Powered by <a class="ext" href="https://www.geoapify.com/">Geoapify</a>'
)

# Marker hues that read clearly on BOTH the positron (light) and dark-matter
# (dark) basemaps. Override per report to match the report palette if wanted.
DEFAULT_TOP_COLOR = "#1f63e6"
DEFAULT_NEAR_COLOR = "#e8772e"


@dataclass(frozen=True)
class MapPlace:
    """One pin request: a display name, the geocoding query, and its label.

    If ``lat``/``lon`` are supplied (e.g. the report author lifted the official
    address or embedded coordinates straight off the result's own website while
    sourcing its photo), they are used directly and geocoding is skipped — this
    is the accurate path and avoids mis-resolving an ambiguous name. Otherwise
    ``query`` is geocoded.
    """

    name: str
    query: str
    rank: str
    kind: str = "top"  # "top" | "near"
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class MapResult:
    light_data_uri: str
    dark_data_uri: str
    attribution_text: str
    attribution_html: str
    located: list[dict[str, Any]] = field(default_factory=list)
    missing: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "located": self.located,
            "missing": self.missing,
            "attribution_text": self.attribution_text,
            "light_bytes": _data_uri_bytes(self.light_data_uri),
            "dark_bytes": _data_uri_bytes(self.dark_data_uri),
        }


def build_map(
    places: list[MapPlace],
    *,
    api_key: str | None = None,
    cache_dir: Path | None = None,
    style_light: str = "positron",
    style_dark: str = "dark-matter",
    width: int = 760,
    height: int = 480,
    scale_factor: int = 2,
    image_format: str = "jpeg",
    top_color: str = DEFAULT_TOP_COLOR,
    near_color: str = DEFAULT_NEAR_COLOR,
) -> MapResult | None:
    """Geocode + render the map, or return None to signal the report fallback."""
    if not api_key:
        print("build_map: GEOAPIFY_API_KEY not set — using location-list fallback", file=sys.stderr)
        return None
    if not places:
        return None

    cache = _GeocodeCache(cache_dir)
    located: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for place in places:
        if place.lat is not None and place.lon is not None:
            # Coordinates supplied from the result's own page — most accurate, no geocoding.
            located.append(
                {
                    "name": place.name,
                    "query": place.query,
                    "rank": place.rank,
                    "kind": place.kind,
                    "lat": place.lat,
                    "lon": place.lon,
                    "formatted": place.query,
                    "confidence": None,
                    "source": "provided",
                }
            )
            continue
        try:
            coords = _geocode(place.query, api_key, cache)
        except urllib.error.URLError as exc:
            print(f"build_map: geocoding failed ({exc}) — using fallback", file=sys.stderr)
            return None
        if coords is None:
            # Fail loud on no-match: keep the result's map link, omit its pin.
            print(f"build_map: no geocode match for {place.name!r} ({place.query!r}) — pin omitted", file=sys.stderr)
            missing.append({"name": place.name, "query": place.query, "rank": place.rank, "kind": place.kind})
            continue
        located.append(
            {
                "name": place.name,
                "query": place.query,
                "rank": place.rank,
                "kind": place.kind,
                "lat": coords["lat"],
                "lon": coords["lon"],
                "formatted": coords.get("formatted", ""),
                "confidence": coords.get("confidence"),
                "source": "geocoded",
            }
        )
    cache.flush()

    if not located:
        print("build_map: no places geocoded — using fallback", file=sys.stderr)
        return None

    markers = [_marker(p, top_color if p["kind"] != "near" else near_color) for p in located]
    view = _view_params(located)
    try:
        light = _fetch_static_map(api_key, style_light, width, height, scale_factor, image_format, view, markers)
        dark = _fetch_static_map(api_key, style_dark, width, height, scale_factor, image_format, view, markers)
    except urllib.error.URLError as exc:
        print(f"build_map: static-map render failed ({exc}) — using fallback", file=sys.stderr)
        return None

    mime = "image/png" if image_format == "png" else "image/jpeg"
    return MapResult(
        light_data_uri=_data_uri(light, mime),
        dark_data_uri=_data_uri(dark, mime),
        attribution_text=ATTRIBUTION_TEXT,
        attribution_html=ATTRIBUTION_HTML,
        located=located,
        missing=missing,
    )


class _GeocodeCache:
    """{query -> {lat, lon, formatted}} persisted in the run dir so re-renders
    don't re-geocode."""

    def __init__(self, cache_dir: Path | None) -> None:
        self.path = (cache_dir / "geocode_cache.json") if cache_dir else None
        self.data: dict[str, dict[str, Any]] = {}
        self._dirty = False
        if self.path and self.path.exists():
            loaded = json.loads(self.path.read_text())
            if isinstance(loaded, dict):
                self.data = loaded

    def get(self, query: str) -> dict[str, Any] | None:
        return self.data.get(query)

    def put(self, query: str, value: dict[str, Any]) -> None:
        self.data[query] = value
        self._dirty = True

    def flush(self) -> None:
        if self.path and self._dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2))
            self._dirty = False


def _geocode(query: str, api_key: str, cache: _GeocodeCache) -> dict[str, Any] | None:
    cached = cache.get(query)
    if cached is not None:
        return cached
    url = with_query(GEOCODE_URL, {"text": query, "format": "json", "limit": 1, "apiKey": api_key})
    data = get_json(url)
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        return None
    top = results[0]
    if top.get("lat") is None or top.get("lon") is None:
        return None
    rank = top.get("rank") or {}
    confidence = rank.get("confidence")
    coords = {
        "lat": top["lat"],
        "lon": top["lon"],
        "formatted": top.get("formatted", ""),
        "confidence": confidence,
    }
    # Don't hide weak matches: a low-confidence hit may pin the wrong place.
    if isinstance(confidence, (int, float)) and confidence < 0.6:
        print(
            f"build_map: low-confidence geocode for {query!r} -> {coords['formatted']!r} "
            f"(confidence {confidence}); verify the pin",
            file=sys.stderr,
        )
    cache.put(query, coords)
    return coords


def _marker(point: dict[str, Any], color: str) -> str:
    color_enc = "%23" + color.lstrip("#")
    fields = [
        f"lonlat:{point['lon']},{point['lat']}",
        "type:material",
        f"color:{color_enc}",
        "size:50",
        f"text:{urllib.parse.quote(str(point['rank']))}",
        "contentcolor:%23ffffff",
        "contentsize:22",
        "whitecircle:no",
    ]
    return ";".join(fields)


def _view_params(points: list[dict[str, Any]]) -> list[str]:
    """Auto-fit to the points' bounding box (padded), or center on a lone point."""
    lons = [p["lon"] for p in points]
    lats = [p["lat"] for p in points]
    if len(points) == 1 or (max(lons) == min(lons) and max(lats) == min(lats)):
        return [f"center=lonlat:{lons[0]},{lats[0]}", "zoom=11"]
    span_lon = max(lons) - min(lons)
    span_lat = max(lats) - min(lats)
    pad_lon = span_lon * 0.18 + 0.01
    pad_lat = span_lat * 0.18 + 0.01
    rect = f"rect:{min(lons) - pad_lon},{min(lats) - pad_lat},{max(lons) + pad_lon},{max(lats) + pad_lat}"
    return [f"area={rect}"]


def _static_map_url(
    api_key: str,
    style: str,
    width: int,
    height: int,
    scale_factor: int,
    image_format: str,
    view: list[str],
    markers: list[str],
) -> str:
    parts = [
        f"style={style}",
        f"width={width}",
        f"height={height}",
        f"scaleFactor={scale_factor}",
        f"format={image_format}",
        *view,
    ]
    # Geoapify wants ALL markers in ONE `marker=` param, pipe-separated (not repeated params).
    if markers:
        parts.append(f"marker={'|'.join(markers)}")
    parts.append(f"apiKey={urllib.parse.quote(api_key)}")
    return STATICMAP_URL + "?" + "&".join(parts)


def _fetch_static_map(
    api_key: str,
    style: str,
    width: int,
    height: int,
    scale_factor: int,
    image_format: str,
    view: list[str],
    markers: list[str],
) -> bytes:
    return get_bytes(_static_map_url(api_key, style, width, height, scale_factor, image_format, view, markers))


def _data_uri(image: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"


def _data_uri_bytes(data_uri: str) -> int:
    head, _, b64 = data_uri.partition(",")
    return len(base64.b64decode(b64)) if b64 else 0


def _places_from_json(raw: Any) -> list[MapPlace]:
    places: list[MapPlace] = []
    for entry in raw:
        places.append(
            MapPlace(
                name=entry["name"],
                query=entry.get("query") or entry.get("address") or entry["name"],
                rank=str(entry["rank"]),
                kind=entry.get("kind", "top"),
                lat=entry.get("lat"),
                lon=entry.get("lon"),
            )
        )
    return places


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build base64 maps for the social-research HTML report.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--places-file", type=Path, help="JSON file: array of {name, query|address, rank, kind}")
    group.add_argument("--places-json", help="Inline JSON array of {name, query|address, rank, kind}")
    parser.add_argument("--cache-dir", type=Path, help="Directory for the geocode cache (usually the run dir)")
    parser.add_argument("--out-dir", type=Path, help="Write light.<fmt>, dark.<fmt> and map.json here (default fmt jpeg)")
    parser.add_argument("--style-light", default="positron")
    parser.add_argument("--style-dark", default="dark-matter")
    parser.add_argument("--width", type=int, default=760)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--format", default="jpeg", choices=["png", "jpeg"])
    parser.add_argument("--top-color", default=DEFAULT_TOP_COLOR)
    parser.add_argument("--near-color", default=DEFAULT_NEAR_COLOR)
    args = parser.parse_args(argv)

    raw = json.loads(args.places_file.read_text()) if args.places_file else json.loads(args.places_json)
    places = _places_from_json(raw)

    config = load_config()
    api_key = config.get("GEOAPIFY_API_KEY")

    # Count Geoapify calls (geocodes + 2 static maps) and fold them into the run's
    # usage record so Appendix D prices the map layer too. build_map runs as its own
    # process after the pipeline has written usage.json, so resetting the shared
    # counter here is safe (it would clobber live pipeline counts if ever called
    # in-process mid-run).
    reset_request_counts()
    set_current_source("geoapify")
    try:
        result = build_map(
            places,
            api_key=api_key,
            cache_dir=args.cache_dir,
            style_light=args.style_light,
            style_dark=args.style_dark,
            width=args.width,
            height=args.height,
            scale_factor=args.scale,
            image_format=args.format,
            top_color=args.top_color,
            near_color=args.near_color,
        )
    finally:
        set_current_source(None)
    geoapify_calls = get_request_counts().get("geoapify", 0)
    if args.cache_dir and geoapify_calls:
        merge_run_calls(args.cache_dir, "geoapify", geoapify_calls)

    if result is None:
        print(json.dumps({"fallback": True}))
        return 0

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        ext = args.format
        (args.out_dir / f"light.{ext}").write_bytes(base64.b64decode(result.light_data_uri.split(",", 1)[1]))
        (args.out_dir / f"dark.{ext}").write_bytes(base64.b64decode(result.dark_data_uri.split(",", 1)[1]))
        (args.out_dir / "map.json").write_text(
            json.dumps(
                {
                    "light_data_uri": result.light_data_uri,
                    "dark_data_uri": result.dark_data_uri,
                    "attribution_text": result.attribution_text,
                    "attribution_html": result.attribution_html,
                    "located": result.located,
                    "missing": result.missing,
                },
                indent=2,
            )
        )

    print(json.dumps({"fallback": False, **result.summary()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
