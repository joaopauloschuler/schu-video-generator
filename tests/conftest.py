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

#: OpenRouter's answer seen live on 2026-10-09 for an account requiring Zero Data Retention
#: (`recraft/recraft-v4.1-flash`, `black-forest-labs/flux.2-klein-4b`; Step 63).
LIVE_ZDR_404 = (
    '{"error":{"message":"0 endpoints out of 1 requested are available matching your guardrail restrictions and data policy. '
    'We removed them for the following reasons ...ZDR violation (account settings): 1 endpoint excluded; configurable at '
    'https://openrouter.ai/settings/privacy","code":404,"metadata":{"input_endpoint_count":1,"ineligibility_reasons":'
    '[{"reason":"zdr-violation-by-account","endpoint_count":1,"configure_url":"https://openrouter.ai/settings/privacy"}]}}}'
)


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


def write_clip(path: Path, seconds: float = 4.0, size: str = "64x36", fps: int = 5, audio: bool = True) -> Path:
    """Write a small lossless H.264 test clip with ffmpeg: frame ``n`` is a flat grey (RGB
    ``11.64 (n + 1)``, so a decoded pixel tells which frame shows), with a 440 Hz tone when
    ``audio``."""
    import shutil
    import subprocess

    path.parent.mkdir(parents=True, exist_ok=True)
    video = f"color=c=black:s={size}:r={fps}:d={seconds},format=yuv420p,geq=lum='26+10*N':cb=128:cr=128"
    inputs = ["-f", "lavfi", "-i", video] + (["-f", "lavfi", "-i", f"sine=f=440:d={seconds}"] if audio else [])
    codecs = ["-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if audio else [])
    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error", *inputs, *codecs, str(path)], check=True, capture_output=True)
    return path


def clip_frame_index(grey: float) -> int:
    """The frame number of a :func:`write_clip` clip from a decoded pixel's grey value (0-255)."""
    return round(grey * 219 / 2550) - 1
