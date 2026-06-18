from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CREDENTIALS_PATH = Path.home() / ".social-research" / "credentials.local.json"


def load_config(path: Path = CREDENTIALS_PATH) -> dict[str, Any]:
    merged = _read_json_object(path)

    for key, value in os.environ.items():
        if key.startswith(("SOCIAL_RESEARCH_", "SCRAPECREATORS_", "BRAVE_", "SERPER_", "EXA_", "PARALLEL_", "GITHUB_", "X_", "GEOAPIFY_")):
            merged[key] = value
    return merged


def _read_json_object(path: Path) -> dict[str, Any]:
    if path.exists():
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a JSON object")
        return dict(data)
    return {}
