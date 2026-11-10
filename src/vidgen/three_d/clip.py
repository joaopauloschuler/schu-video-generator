"""The 3D frames of a scene render as a clip, reused while nothing that draws them changed
(DESIGN.md §114.5)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from vidgen.fileio import write_text_atomic
from vidgen.three_d.browser import engine_id, write_clip
from vidgen.three_d.description import description_key

log = logging.getLogger("vidgen.three_d")


def _stored_key(record: Path) -> str | None:
    """The cache key in a clip's record, or ``None`` when it is missing or unreadable."""
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("key") if isinstance(data, dict) else None


def make_3d_clip(folder: Path, name: str, description: dict[str, Any]) -> Path:
    """``folder/<name>.mkv``: the frames of ``description``, drawn now (one Chromium) unless the
    clip there was drawn from the same description by the same page, three.js and Playwright.
    Writes ``folder/<name>.json`` = ``{"key", "description"}`` beside it."""
    clip, record = folder / f"{name}.mkv", folder / f"{name}.json"
    key = description_key(description, engine_id())
    if clip.is_file() and _stored_key(record) == key:
        log.info("%s: reusing the 3D frames (%s)", name, clip.name)
        return clip
    log.info("%s: drawing %d 3D frames", name, description["frames"])
    record.unlink(missing_ok=True)
    write_clip(description, clip)
    write_text_atomic(record, json.dumps({"key": key, "description": description}, indent=1) + "\n")
    return clip


__all__ = ["make_3d_clip"]
