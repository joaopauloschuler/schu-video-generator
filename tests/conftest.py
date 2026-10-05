"""Shared fixtures."""

from __future__ import annotations

import json
import sys
import textwrap
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml


def minimal_config(**overrides: Any) -> dict[str, Any]:
    """A small valid raw config mapping."""
    data: dict[str, Any] = {
        "title": "Test video",
        "scenes": [
            {
                "id": "intro",
                "type": "text_card",
                "params": {"text": "Hello"},
                "beats": [{"text": "Hello there."}, {"text": "Second beat."}],
            },
            {"id": "main", "type": "text_card", "params": {"text": "Main"}, "beats": [{"id": "custom", "text": "One two three four."}]},
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


@pytest.fixture(autouse=True)
def _isolate_vidgen_state() -> Iterator[None]:
    """Each test starts with no extension scene types/hooks and no active project."""
    from vidgen import extensions, hooks, registry, runtime

    runtime.clear_context()
    with registry.isolated(), hooks.isolated():
        yield
    runtime.clear_context()
    for name in [n for n in sys.modules if n.startswith(extensions.PACKAGE_PREFIX)]:
        del sys.modules[name]


def write_files(root: Path, files: dict[str, str]) -> None:
    """Write ``{relative path: source}`` under ``root`` (sources are dedented)."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
