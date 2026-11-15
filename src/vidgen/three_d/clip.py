"""The 3D frames of a scene render as a clip, reused while nothing that draws them changed
(DESIGN.md §114.5)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from vidgen.browser.frames_clip import clip_serves
from vidgen.fileio import write_text_atomic
from vidgen.three_d.browser import engine_id, write_clip
from vidgen.three_d.description import description_key

log = logging.getLogger("vidgen.three_d")


def _stored(record: Path) -> dict[str, Any]:
    """A clip's record, ``{}`` when it is missing or unreadable."""
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def make_3d_clip(folder: Path, name: str, description: dict[str, Any], intermediate: str = "lossless") -> Path:
    """``folder/<name>.mkv``: the frames of ``description``, drawn now (one Chromium) unless the
    clip there was drawn from the same description by the same page, three.js and Playwright
    and is stored as ``intermediate`` asks (DESIGN.md §120.9: a lossless clip serves either, a
    compact one only ``compact``). Writes ``folder/<name>.json`` = ``{"key", "description"}``
    (+ ``"intermediate": "compact"``) beside it."""
    clip, record = folder / f"{name}.mkv", folder / f"{name}.json"
    key = description_key(description, engine_id())
    stored = _stored(record)
    if clip.is_file() and stored.get("key") == key and clip_serves(stored.get("intermediate"), intermediate):
        log.info("%s: reusing the 3D frames (%s)", name, clip.name)
        return clip
    log.info("%s: drawing %d 3D frames", name, description["frames"])
    record.unlink(missing_ok=True)
    write_clip(description, clip, intermediate)
    kept = {} if intermediate == "lossless" else {"intermediate": intermediate}
    write_text_atomic(record, json.dumps({"key": key, "description": description, **kept}, indent=1) + "\n")
    return clip


__all__ = ["make_3d_clip"]
