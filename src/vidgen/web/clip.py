"""A ``web`` scene's frames as a clip, reused while nothing that draws them changed (DESIGN.md §118.4, §118.10)."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from vidgen.browser.chromium import write_ffv1_clip
from vidgen.fileio import write_text_atomic
from vidgen.web.entry import WebEntry, entry_of, entry_path
from vidgen.web.inputs import page_shape
from vidgen.web.loaded import current_loaded, read_record, record_path
from vidgen.web.page import WebPage, engine_id, layout_digest

log = logging.getLogger("vidgen.web")

#: Version of a clip's inputs (2: the theme, ``data``, beats and the files the page loaded; 3:
#: the video's shape and frames with alpha).
CLIP_VERSION = 3


def scene_data(params: Any) -> dict[str, Any]:
    """The ``data:`` values of a ``web`` scene's params (a model or a mapping), ``{}`` when unset."""
    data = params.get("data") if isinstance(params, Mapping) else getattr(params, "data", None)
    return dict(data or {})


def clip_inputs(root: Path, entry: WebEntry, *, scene_id: str, size: tuple[int, int], fps: int, frames: int,
                theme: Mapping[str, Any] | None = None, data: Mapping[str, Any] | None = None,
                beats: Sequence[Mapping[str, Any]] = (), shape: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What the clip is drawn from (stored in its record): the entry and its file's SHA-256,
    the size (the page's viewport), frame rate and frame count, what the page is given (theme,
    data, beats, the video's shape: aspect, orientation, frame size, region), that the frames
    keep their alpha, and vidgen's page files and Playwright version. The other files the page loads are checked
    from the record (:func:`loaded_changed`)."""
    path = entry_path(root, entry, scene_id)
    return {
        "version": CLIP_VERSION, "engine": engine_id(), "scene": scene_id, "kind": entry.kind, "path": entry.posix,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "width": size[0], "height": size[1], "fps": fps, "frames": frames,
        "theme": dict(theme) if theme is not None else None, "data": dict(data or {}), "beats": [dict(b) for b in beats],
        "shape": dict(shape) if shape is not None else page_shape(size), "alpha": True,
    }


def loaded_changed(root: Path, loaded: Mapping[str, str | None]) -> list[str]:
    """The files of a record's ``loaded`` map that differ now (edited, created or removed)."""
    now = current_loaded(root, loaded)
    return [rel for rel in now if now[rel] != loaded[rel]]


def _clip_key(root: Path, scene_id: str, params: Any, *, size: tuple[int, int], fps: int, frames: int,
              theme: Mapping[str, Any] | None, beats: Sequence[Mapping[str, Any]],
              shape: Mapping[str, Any] | None) -> tuple[WebEntry, dict[str, Any], dict[str, Any], str]:
    """The entry, ``data``, inputs (:func:`clip_inputs`) and key of a scene's clip."""
    entry = entry_of(params)
    data = scene_data(params)
    shape = dict(shape) if shape is not None else page_shape(size)
    inputs = clip_inputs(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames, theme=theme, data=data, beats=beats,
                         shape=shape)
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return entry, data, inputs, key


def layout_record_path(folder: Path, scene_id: str) -> Path:
    """Where the page's layout readings beside a scene's clip are kept: ``<scene_id>.layout.json``."""
    return folder / f"{scene_id}.layout.json"


def _stored_layouts(folder: Path, scene_id: str, key: str) -> dict[int, dict[str, Any]]:
    """The layout readings kept for the clip of ``key`` (frame -> reading), none when the record
    is missing, of another clip or of another reader."""
    record = read_record(layout_record_path(folder, scene_id)) or {}
    if record.get("key") != key or record.get("reader") != layout_digest() or not isinstance(record.get("frames"), dict):
        return {}
    return {int(n): dict(v) for n, v in record["frames"].items()}


def _store_layouts(folder: Path, scene_id: str, key: str, layouts: Mapping[int, Mapping[str, Any]]) -> None:
    frames = {str(n): dict(layouts[n]) for n in sorted(layouts)}
    write_text_atomic(layout_record_path(folder, scene_id),
                      json.dumps({"key": key, "reader": layout_digest(), "frames": frames}, separators=(",", ":")) + "\n")


def make_web_clip(root: Path, folder: Path, scene_id: str, params: Any, *, size: tuple[int, int], fps: int, frames: int,
                  theme: Mapping[str, Any] | None = None, beats: Sequence[Mapping[str, Any]] = (),
                  shape: Mapping[str, Any] | None = None, layout_frames: Iterable[int] = ()) -> Path:
    """``folder/<scene_id>.mkv``: ``frames`` screenshots with alpha (RGBA, FFV1 ``bgra``) of the
    scene's page (``params``: its ``page`` or ``script``, a path in the project folder ``root``,
    and its ``data``) at ``fps`` and ``size`` (the page's viewport),
    drawn now (one Chromium) unless the clip there was drawn from the same inputs
    (:func:`clip_inputs`) and every file the page loaded then is unchanged. ``theme`` and
    ``beats`` are ``ctx.theme`` and ``ctx.beats`` (§118.9), ``shape`` the video's shape
    (:func:`~vidgen.web.inputs.page_shape`; default: a page filling a frame of ``size``, §118.11). Writes ``folder/<scene_id>.json`` =
    ``{"key", "inputs", "loaded"}`` beside it (``loaded``: served path -> SHA-256). When it draws,
    it also reads the page's text at ``layout_frames`` (after their screenshots) into
    ``<scene_id>.layout.json`` (:func:`web_page_layouts` reads them back, §118.12)."""
    entry, data, inputs, key = _clip_key(root, scene_id, params, size=size, fps=fps, frames=frames, theme=theme, beats=beats, shape=shape)
    shape = inputs["shape"]
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
    layout_record_path(folder, scene_id).unlink(missing_ok=True)
    wanted = {n for n in layout_frames if 0 <= n < frames}
    layouts: dict[int, dict[str, Any]] = {}

    def drawn(page: WebPage) -> Iterator[Any]:
        for n in range(frames):
            pixels = page.frame(n)
            if n in wanted:
                layouts[n] = page.layout(n)
            yield pixels

    with WebPage(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames,
                 theme=dict(theme) if theme is not None else None, data=data, beats=[dict(b) for b in beats], shape=shape) as page:
        write_ffv1_clip(clip, fps, size, drawn(page), alpha=True)
        served = dict(sorted(page.loaded.items()))
    write_text_atomic(record, json.dumps({"key": key, "inputs": inputs, "loaded": served}, indent=1) + "\n")
    _store_layouts(folder, scene_id, key, layouts)
    return clip


def web_page_layouts(root: Path, folder: Path, scene_id: str, params: Any, *, size: tuple[int, int], fps: int, frames: int,
                     theme: Mapping[str, Any] | None = None, beats: Sequence[Mapping[str, Any]] = (),
                     shape: Mapping[str, Any] | None = None, at: Iterable[int] = ()) -> dict[int, dict[str, Any]]:
    """The page's text at frames ``at`` (frame -> the reading of ``data/web/layout.js``, page
    pixels), for the clip :func:`make_web_clip` makes from the same arguments: the readings kept
    beside the clip, else read now in one Chromium that steps the page frame by frame (no
    screenshots) to the last frame missing, and kept for next time (§118.12)."""
    entry, data, inputs, key = _clip_key(root, scene_id, params, size=size, fps=fps, frames=frames, theme=theme, beats=beats, shape=shape)
    wanted = sorted({min(max(int(n), 0), frames - 1) for n in at})
    layouts = _stored_layouts(folder, scene_id, key)
    missing = [n for n in wanted if n not in layouts]
    if missing:
        log.info("%s: reading the page's text at %d frame(s), stepping %d frames", scene_id, len(missing), missing[-1] + 1)
        with WebPage(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames,
                     theme=dict(theme) if theme is not None else None, data=data, beats=[dict(b) for b in beats],
                     shape=inputs["shape"]) as page:
            for n in range(missing[-1] + 1):
                page.advance(n)
                if n in missing:
                    layouts[n] = page.layout(n)
        _store_layouts(folder, scene_id, key, layouts)
    return {n: layouts[n] for n in wanted}


def forget_web_clips(folder: Path, scene_ids: Iterable[str]) -> None:
    """Remove the records of these scenes' clips in ``folder``, so their frames are drawn again
    (``vidgen render --force``)."""
    for scene_id in scene_ids:
        record_path(folder, scene_id).unlink(missing_ok=True)


__all__ = ["CLIP_VERSION", "clip_inputs", "forget_web_clips", "layout_record_path", "loaded_changed", "make_web_clip", "scene_data",
           "web_page_layouts"]
