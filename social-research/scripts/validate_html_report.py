#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import load_config
from core.gate_ledger import latest_by_gate

# Gates that must each have a passing receipt before a report ships. A draft can
# be shipped with failing content gates only via an explicit draft_approved receipt.
REQUIRED_RELEASE_GATES = (
    "scope_clarified",
    "source_sufficiency",
    "adversarial_review",
    "html_report_path",
    "media_map",
    "cost_capture",
)

DRAFT_ESCAPABLE_GATES = {"source_sufficiency", "adversarial_review", "media_map"}

# Photo-source credentials. If any is present, an SVG/schematic placeholder photo
# is a real defect (the agent could have fetched a verified raster image).
_PHOTO_CRED_ENV = ("SCRAPECREATORS_API_KEY", "BRAVE_API_KEY", "SERPER_API_KEY", "EXA_API_KEY", "PARALLEL_API_KEY")

# Sanctioned map-fallback reasons (HTML_REPORT.md): no key, geocode failure, or
# build_map render failure. "speed" and silence are not sanctioned.
_MAP_NOKEY_RE = re.compile(r"no\s+(?:geoapify\s+)?key|geoapify_api_key\s+not\s+set|without\s+(?:a\s+)?geoapify\s+key", re.I)
_MAP_FAILURE_RE = re.compile(
    r"geocod\w*\s+(?:fail\w*|error|no[- ]?match)|fail\w*\s+to\s+geocode|no\s+geocode\s+match|render\s+fail\w*|"
    r"build_map[^.]{0,120}\"?fallback\"?\s*:\s*true|\"?fallback\"?\s*:\s*true[^.]{0,120}build_map|"
    r"map[^.]{0,120}api\s+(?:error|failure)|api\s+(?:error|failure)[^.]{0,120}map",
    re.I,
)


_VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str]]] = []
        self.ids: set[str] = set()
        self.classes: set[str] = set()
        self.images: list[dict[str, str]] = []
        self.details_open = 0
        self.map_depth = 0
        self.near_depth = 0
        self.near_has_ul = False
        self.near_cards = 0
        self.card_depth = 0
        self.current_card_has_image = False
        self.current_card_is_near = False
        self.current_card_check_count = 0
        self.current_card_labels: list[str] = []
        self.card_image_missing = 0
        self.top_card_ids: list[str] = []
        self.near_card_count = 0
        self.top_card_checks: list[int] = []
        self.top_card_label_sets: list[tuple[str, ...]] = []
        self.label_depth = 0
        self.current_label_text: list[str] = []
        self.map_has_light = False
        self.map_has_dark = False
        self.map_has_links = False
        self.map_has_legend = False
        self.hrefs: set[str] = set()
        self.open_details_summaries: list[str] = []
        self.details_depth = 0
        self.summary_depth = 0
        self.current_summary_text: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: v or "" for k, v in attrs_list}
        is_void = tag in _VOID_ELEMENTS
        if not is_void:
            self.stack.append((tag, attrs))
        depth = len(self.stack)
        if element_id := attrs.get("id"):
            self.ids.add(element_id)
        classes = set(attrs.get("class", "").split())
        self.classes.update(classes)

        if href := attrs.get("href"):
            self.hrefs.add(href)
        if self.map_depth and "map-links" in classes:
            self.map_has_links = True
        if self.map_depth and "legend" in classes:
            self.map_has_legend = True
        if tag == "img":
            self.images.append(attrs)
            if self.card_depth:
                self.current_card_has_image = True
            if self.map_depth and "map-img" in classes and "light" in classes:
                self.map_has_light = True
            if self.map_depth and "map-img" in classes and "dark" in classes:
                self.map_has_dark = True
        if tag == "details" and "open" in attrs:
            self.details_open += 1
            self.details_depth = depth
        if self.details_depth and tag == "summary":
            self.summary_depth = depth
            self.current_summary_text = []
        if attrs.get("id") == "map":
            self.map_depth = depth
        if attrs.get("id") == "near-misses":
            self.near_depth = depth
        if self.near_depth and tag == "ul":
            self.near_has_ul = True
        if tag == "article" and "card" in classes:
            self.card_depth = depth
            self.current_card_has_image = False
            self.current_card_is_near = "near" in classes
            self.current_card_check_count = 0
            self.current_card_labels = []
            if self.current_card_is_near:
                self.near_cards += 1
                self.near_card_count += 1
            else:
                if element_id := attrs.get("id"):
                    self.top_card_ids.append(element_id)
        if self.card_depth and "check" in classes:
            self.current_card_check_count += 1
        if self.card_depth and "label" in classes:
            self.label_depth = depth
            self.current_label_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_ELEMENTS:
            return
        if self.label_depth == len(self.stack):
            label = " ".join(self.current_label_text).strip()
            if label:
                self.current_card_labels.append(label)
            self.label_depth = 0
            self.current_label_text = []
        if self.summary_depth == len(self.stack):
            summary = " ".join(self.current_summary_text).strip()
            if summary:
                self.open_details_summaries.append(summary)
            self.summary_depth = 0
            self.current_summary_text = []
        if self.card_depth == len(self.stack):
            if not self.current_card_has_image:
                self.card_image_missing += 1
            if not self.current_card_is_near:
                self.top_card_checks.append(self.current_card_check_count)
                self.top_card_label_sets.append(tuple(self.current_card_labels))
            self.card_depth = 0
            self.current_card_has_image = False
            self.current_card_is_near = False
            self.current_card_check_count = 0
            self.current_card_labels = []
        if self.map_depth == len(self.stack):
            self.map_depth = 0
        if self.near_depth == len(self.stack):
            self.near_depth = 0
        if self.details_depth == len(self.stack):
            self.details_depth = 0
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1][0] in {"script", "style"}:
            return
        if data.strip():
            self.text_parts.append(data)
            if self.label_depth:
                self.current_label_text.append(data)
            if self.summary_depth:
                self.current_summary_text.append(data)

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


def validate_html(html: str, *, ledger_path: str | Path | None = None) -> None:
    parser = _ReportParser()
    parser.feed(html)
    errors: list[str] = []

    draft_approved = False
    if ledger_path is not None:
        latest = latest_by_gate(ledger_path)
        receipt = latest.get("draft_approved")
        draft_approved = bool(receipt and receipt["status"] == "pass")
        for gate in REQUIRED_RELEASE_GATES:
            gate_receipt = latest.get(gate)
            if gate_receipt is None:
                errors.append(f"release gate '{gate}' not satisfied — missing receipt (gate did not run)")
            elif gate_receipt["status"] == "pass":
                continue
            elif draft_approved and gate in DRAFT_ESCAPABLE_GATES:
                continue
            else:
                reason = gate_receipt.get("reason", "")
                problem = f"status={gate_receipt['status']}: {reason}".rstrip(": ")
                errors.append(f"release gate '{gate}' not satisfied — {problem}")

    if "brief" not in parser.ids:
        errors.append("missing #brief section")
    if "theme-toggle" not in parser.classes or "data-theme" not in html:
        errors.append("missing light/dark theme toggle")

    config = load_config()
    photo_creds_available = any(config.get(key) for key in _PHOTO_CRED_ENV)
    for image in parser.images:
        src = image.get("src", "")
        if not src.startswith("data:image/"):
            errors.append(f"non-data image src: {src[:80]}")
        elif src.startswith("data:image/svg") and photo_creds_available and not draft_approved:
            errors.append("SVG/schematic placeholder image while photo credentials are available — embed a verified raster photo or record draft approval")

    if "index" not in parser.ids:
        errors.append("missing #index table of contents")
    for pick_id in parser.top_card_ids:
        if f"#{pick_id}" not in parser.hrefs:
            errors.append(f"index missing link to #{pick_id}")

    if "map" in parser.ids:
        has_real_map = parser.map_has_light and parser.map_has_dark
        has_fallback_map = parser.map_has_links and parser.map_has_legend and _has_appendix_c(parser.text) and _has_debug_terms(parser.text)
        if not has_real_map and not has_fallback_map:
            errors.append("map section missing real .map-img light/dark images or documented fallback links")
        if has_real_map and ("map-attrib" not in parser.classes or "OpenStreetMap" not in parser.text or "Geoapify" not in parser.text):
            errors.append("map section missing OSM/Geoapify attribution")
        if has_fallback_map and not has_real_map and not draft_approved:
            key_present = bool(config.get("GEOAPIFY_API_KEY"))
            has_failure_reason = bool(_MAP_FAILURE_RE.search(parser.text))
            # With a key present the no-key excuse is a lie; only a real failure justifies the fallback.
            sanctioned = has_failure_reason or (not key_present and bool(_MAP_NOKEY_RE.search(parser.text)))
            if not sanctioned:
                errors.append("map fallback used for a non-sanctioned reason (only no-key / geocode-failure / render-failure qualify; 'speed' does not) — build the real Geoapify map or record draft approval")

    if "near-misses" in parser.ids and parser.near_has_ul:
        errors.append("near misses must be rendered as cards, not a bullet list")
    if "near-misses" in parser.ids and parser.near_card_count == 0:
        errors.append("near misses section has no .card.near cards")

    if parser.card_image_missing:
        errors.append(f"{parser.card_image_missing} result card(s) missing a data image")
    for count in parser.top_card_checks:
        if count < 3 or count > 5:
            errors.append("top-pick cards must include 3–5 criteria tiles each")
            break
    non_empty_label_sets = [labels for labels in parser.top_card_label_sets if labels]
    if non_empty_label_sets and len(set(non_empty_label_sets)) > 1:
        errors.append("top-pick criteria tile labels must match across cards")

    if _has_debug_terms(parser.text) and not _has_appendix_c(parser.text):
        errors.append("debug/process issues require Appendix C")
    summaries = " ".join(parser.open_details_summaries)
    if "Appendix A" not in summaries:
        errors.append("Appendix A must be open <details>")
    if "Appendix B" not in summaries:
        errors.append("Appendix B must be open <details>")
    if re.search(r"Appendix\s+D", parser.text, re.I):
        if "Appendix D" not in summaries:
            errors.append("Appendix D must be an open <details>")
        if not re.search(r"OpenRouter", parser.text, re.I) or not re.search(r"snapshot", parser.text, re.I):
            errors.append("Appendix D must cite a dated OpenRouter rate snapshot")
        if "$" not in parser.text:
            errors.append("Appendix D must show line-itemed dollar costs")
        if not re.search(r"cache", parser.text, re.I):
            errors.append("Appendix D must break out cache token buckets")
    if "Appendix A" in summaries:
        verdict = re.search(r"Verdict:\s*(pass|needs fixes)", parser.text, re.I)
        if not verdict:
            errors.append("Appendix A must include adversarial review verdict")
        elif verdict.group(1).lower() == "needs fixes":
            legacy_ack = re.search(r"user acknowledged|acknowledged limitations", parser.text, re.I)
            if ledger_path is not None and not draft_approved:
                errors.append("review verdict is needs fixes without a draft-approval receipt")
            elif ledger_path is None and not legacy_ack:
                errors.append("review verdict is needs fixes without user-acknowledged limitations")
        if not re.search(r"queried\s*→|blocked/error", parser.text, re.I):
            errors.append("Appendix A must include selected-source status")

    placeholders = [token for token in ("REPLACE_WITH", "<!-- TITLE", "<!-- HEADER", "PLACEHOLDER") if token in html]
    if placeholders:
        errors.append(f"unreplaced template placeholders: {', '.join(placeholders)}")

    if errors:
        raise ValueError("HTML report validation failed:\n- " + "\n- ".join(errors))


def _has_debug_terms(text: str) -> bool:
    return bool(re.search(r"\b(first run|did not contribute|source failure|blocked/error|fallback path|fallback used|geocod(?:e|ing) correction|credential(?:s)? (?:missing|failed|blocked|not configured|not loaded|problem|failure))\b", text, re.I))


def _has_appendix_c(text: str) -> bool:
    return bool(re.search(r"Appendix\s+C", text, re.I))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate mechanical invariants for social-research HTML reports.")
    parser.add_argument("html_file", type=Path)
    parser.add_argument("--ledger", type=Path, help="gate ledger path (default: gate_ledger.jsonl beside the report)")
    parser.add_argument("--skip-gates", action="store_true", help="structural checks only; do not enforce the release-gate ledger")
    args = parser.parse_args(argv)
    ledger_path = None if args.skip_gates else (args.ledger or args.html_file.parent / "gate_ledger.jsonl")
    validate_html(args.html_file.read_text(), ledger_path=ledger_path)
    print("✓ HTML report validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
