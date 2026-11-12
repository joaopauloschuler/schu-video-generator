"""A ``web`` scene's frames as a clip, reused while nothing that draws them changed (DESIGN.md §118.4, §118.10)."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from vidgen.browser.chromium import write_ffv1_clip
from vidgen.fileio import write_text_atomic
from vidgen.web.entry import WebEntry, entry_of, entry_path
from vidgen.web.loaded import current_loaded, read_record, record_path
from vidgen.web.page import WebPage, engine_id

log = logging.getLogger("vidgen.web")

#: Version of a clip's inputs (2: the theme, ``data``, beats and the files the page loaded).
CLIP_VERSION = 2


def scene_data(params: Any) -> dict[str, Any]:
    """The ``data:`` values of a ``web`` scene's params (a model or a mapping), ``{}`` when unset."""
    data = params.get("data") if isinstance(params, Mapping) else getattr(params, "data", None)
    return dict(data or {})


def clip_inputs(root: Path, entry: WebEntry, *, scene_id: str, size: tuple[int, int], fps: int, frames: int,
                theme: Mapping[str, Any] | None = None, data: Mapping[str, Any] | None = None,
                beats: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """What the clip is drawn from (stored in its record): the entry and its file's SHA-256,
    the size, frame rate and frame count, what the page is given (theme, data, beats) and
    vidgen's page files and Playwright version. The other files the page loads are checked
    from the record (:func:`loaded_changed`)."""
    path = entry_path(root, entry, scene_id)
    return {
        "version": CLIP_VERSION, "engine": engine_id(), "scene": scene_id, "kind": entry.kind, "path": entry.posix,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "width": size[0], "height": size[1], "fps": fps, "frames": frames,
        "theme": dict(theme) if theme is not None else None, "data": dict(data or {}), "beats": [dict(b) for b in beats],
    }


def loaded_changed(root: Path, loaded: Mapping[str, str | None]) -> list[str]:
    """The files of a record's ``loaded`` map that differ now (edited, created or removed)."""
    now = current_loaded(root, loaded)
    return [rel for rel in now if now[rel] != loaded[rel]]


def make_web_clip(root: Path, folder: Path, scene_id: str, params: Any, *, size: tuple[int, int], fps: int, frames: int,
                  theme: Mapping[str, Any] | None = None, beats: Sequence[Mapping[str, Any]] = ()) -> Path:
    """``folder/<scene_id>.mkv``: ``frames`` screenshots of the scene's page (``params``: its
    ``page`` or ``script``, a path in the project folder ``root``, and its ``data``) at ``fps``,
    drawn now (one Chromium) unless the clip there was drawn from the same inputs
    (:func:`clip_inputs`) and every file the page loaded then is unchanged. ``theme`` and
    ``beats`` are ``ctx.theme`` and ``ctx.beats`` (§118.9). Writes ``folder/<scene_id>.json`` =
    ``{"key", "inputs", "loaded"}`` beside it (``loaded``: served path -> SHA-256)."""
    entry = entry_of(params)
    data = scene_data(params)
    inputs = clip_inputs(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames, theme=theme, data=data, beats=beats)
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    clip, record = folder / f"{scene_id}.mkv", record_path(folder, scene_id)
    stored = read_record(record) or {}
    loaded = stored.get("loaded") if isinstance(stored.get("loaded"), dict) else {}
    if clip.is_file() and stored.get("key") == key:
        changed = loaded_changed(root, loaded)
        if not changed:
            log.info("%s: reusing the web frames (%s)", scene_id, clip.name)
            return clip
        log.info("%s: %s changed since the web frames were drawn", scene_id, ", ".join(changed))
    log.info("%s: drawing %d web frames of %s", scene_id, frames, entry.posix)
    record.unlink(missing_ok=True)
    with WebPage(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames,
                 theme=dict(theme) if theme is not None else None, data=data, beats=[dict(b) for b in beats]) as page:
        write_ffv1_clip(clip, fps, size, (page.frame(n) for n in range(frames)))
        served = dict(sorted(page.loaded.items()))
    write_text_atomic(record, json.dumps({"key": key, "inputs": inputs, "loaded": served}, indent=1) + "\n")
    return clip


def forget_web_clips(folder: Path, scene_ids: Iterable[str]) -> None:
    """Remove the records of these scenes' clips in ``folder``, so their frames are drawn again
    (``vidgen render --force``)."""
    for scene_id in scene_ids:
        record_path(folder, scene_id).unlink(missing_ok=True)


__all__ = ["CLIP_VERSION", "clip_inputs", "forget_web_clips", "loaded_changed", "make_web_clip", "scene_data"]
