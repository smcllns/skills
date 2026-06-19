from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import SearchConfig, SourceItem


class SearchStorage:
    def __init__(self, root: Path, now: Callable[[], datetime]) -> None:
        self.root = Path(root)
        self.now = now

    def create_run_dir(self, config: SearchConfig) -> Path:
        timestamp = self.now().strftime("%Y-%m-%d-%H%M")
        base = self.root / f"{timestamp}-{slugify(config.query)}"
        run_dir = base
        suffix = 2
        while run_dir.exists():
            run_dir = Path(f"{base}-{suffix}")
            suffix += 1
        (run_dir / "raw").mkdir(parents=True)
        return run_dir

    def write_artifacts(
        self,
        *,
        run_dir: Path,
        query: dict[str, Any],
        raw_by_source: dict[str, Any],
        normalized: list[SourceItem],
        report: str,
        usage: dict[str, Any] | None = None,
    ) -> None:
        _write_json(run_dir / "query.json", query)
        raw_dir = run_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        for source, payload in raw_by_source.items():
            _write_json(raw_dir / f"{source}.json", payload)
        _write_json(run_dir / "normalized.json", {"items": [item.to_dict() for item in normalized]})
        (run_dir / "report.md").write_text(report)
        if usage is not None:
            _write_json(run_dir / "usage.json", usage)


def slugify(value: str) -> str:
    value = value.replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80].strip("-") or "search"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
