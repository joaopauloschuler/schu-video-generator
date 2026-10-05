"""Shared fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml


def minimal_config(**overrides: Any) -> dict[str, Any]:
    """A small valid raw config mapping."""
    data: dict[str, Any] = {
        "title": "Test video",
        "scenes": [
            {"id": "intro", "type": "title", "beats": [{"text": "Hello there."}, {"text": "Second beat."}]},
            {"id": "main", "type": "bullets", "beats": [{"id": "custom", "text": "One two three four."}]},
        ],
    }
    data.update(overrides)
    return data


@pytest.fixture
def make_project(tmp_path: Path) -> Callable[..., Path]:
    """Write a project folder with the given raw config; returns its directory."""

    def make(data: dict[str, Any] | None = None, name: str = "video.yaml", folder: str = "proj") -> Path:
        root = tmp_path / folder
        root.mkdir(parents=True, exist_ok=True)
        data = minimal_config() if data is None else data
        text = json.dumps(data) if name.endswith(".json") else yaml.safe_dump(data, sort_keys=False)
        (root / name).write_text(text, encoding="utf-8")
        return root

    return make
