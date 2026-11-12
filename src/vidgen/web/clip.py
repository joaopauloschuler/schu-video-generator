"""A ``web`` scene's frames as a clip, reused while nothing that draws them changed (DESIGN.md §118.4)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from vidgen.browser.chromium import write_ffv1_clip
from vidgen.fileio import write_text_atomic
from vidgen.web.entry import WebEntry, entry_of, entry_path
from vidgen.web.page import WebPage, engine_id

log = logging.getLogger("vidgen.web")


def clip_inputs(root: Path, entry: WebEntry, *, scene_id: str, size: tuple[int, int], fps: int, frames: int) -> dict[str, Any]:
    """What the clip is drawn from (stored in its record): the entry and its file's SHA-256,
    the size, frame rate and frame count, and vidgen's page files and Playwright version."""
    path = entry_path(root, entry, scene_id)
    return {
        "version": 1, "engine": engine_id(), "scene": scene_id, "kind": entry.kind, "path": entry.posix,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "width": size[0], "height": size[1], "fps": fps, "frames": frames,
    }


def _stored_key(record: Path) -> str | None:
    """The cache key in a clip's record, or ``None`` when it is missing or unreadable."""
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("key") if isinstance(data, dict) else None


def make_web_clip(root: Path, folder: Path, scene_id: str, params: Any, *, size: tuple[int, int], fps: int, frames: int) -> Path:
    """``folder/<scene_id>.mkv``: ``frames`` screenshots of the scene's page (``params``: its
    ``page`` or ``script``, a path in the project folder ``root``) at ``fps``, drawn now (one
    Chromium) unless the clip there was drawn from the same inputs (:func:`clip_inputs`).
    Writes ``folder/<scene_id>.json`` = ``{"key", "inputs"}`` beside it."""
    entry = entry_of(params)
    inputs = clip_inputs(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames)
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    clip, record = folder / f"{scene_id}.mkv", folder / f"{scene_id}.json"
    if clip.is_file() and _stored_key(record) == key:
        log.info("%s: reusing the web frames (%s)", scene_id, clip.name)
        return clip
    log.info("%s: drawing %d web frames of %s", scene_id, frames, entry.posix)
    record.unlink(missing_ok=True)
    with WebPage(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames) as page:
        write_ffv1_clip(clip, fps, size, (page.frame(n) for n in range(frames)))
    write_text_atomic(record, json.dumps({"key": key, "inputs": inputs}, indent=1) + "\n")
    return clip


__all__ = ["clip_inputs", "make_web_clip"]
