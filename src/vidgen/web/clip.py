"""A ``web`` scene's frames as a clip, reused while nothing that draws them changed (DESIGN.md §118.4, §118.10)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from vidgen.browser.frames_clip import FramesClipWriter, clip_serves
from vidgen.fileio import write_text_atomic
from vidgen.web.entry import WebEntry, entry_of, entry_path
from vidgen.web.inputs import design_width_of, page_shape
from vidgen.web.loaded import current_loaded, read_record, record_path
from vidgen.web.music import helper_digest, payload_digest
from vidgen.web.page import WebPage, engine_id, layout_digest

log = logging.getLogger("vidgen.web")
#: Progress while a clip's frames are drawn (DESIGN.md §120.10); the render worker prints it as
#: ``progress: ...`` lines, which ``vidgen render`` shows under the scene's name.
progress_log = logging.getLogger("vidgen.progress")
#: Seconds between two progress lines (at most one line in this time; the last frame always has one).
PROGRESS_SECONDS = 10.0

#: Version of a clip's inputs (2: the theme, ``data``, beats and the files the page loaded; 3:
#: the video's shape and frames with alpha).
CLIP_VERSION = 3


def seconds_text(seconds: float) -> str:
    """``"1.21"`` or, under a tenth, ``"0.034"``: seconds a frame for a progress line."""
    return f"{seconds:.2f}" if seconds >= 0.1 else f"{seconds:.3f}"


def duration_text(seconds: float) -> str:
    """``"45 s"``, ``"3 min 05 s"``, ``"1 h 07 min"``: a time span for a progress line."""
    whole = max(0, round(seconds))
    if whole < 60:
        return f"{whole} s"
    if whole < 3600:
        return f"{whole // 60} min {whole % 60:02d} s"
    return f"{whole // 3600} h {whole // 60 % 60:02d} min"


class FrameProgress:
    """Progress lines for ``total`` frames being drawn: ``web frames 30/90, 1.21 s a frame, about
    1 min 13 s left`` at most every :data:`PROGRESS_SECONDS`, then a summary that splits a frame's
    time into the page's ``frame(t, ctx)`` hook and the drawing with the screenshot (and says how
    long the page took to become ready, ``ready_seconds``). The rate and what is left are from the
    frames after the first (the first compiles a WebGL page's shaders)."""

    def __init__(self, total: int, *, ready_seconds: float = 0.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.total, self._clock = total, clock
        self.ready_seconds = ready_seconds
        self.done = 0
        self._started = self._last_line = clock()
        self._after_first = clock()
        self.hook_seconds = self.draw_seconds = 0.0

    def seconds_per_frame(self) -> float | None:
        """Mean seconds a frame since the first frame (``None`` before the second)."""
        if self.done < 2:
            return None
        return (self._clock() - self._after_first) / (self.done - 1)

    def line(self) -> str:
        """The progress line for now."""
        rate = self.seconds_per_frame()
        if rate is None:
            return f"web frames {self.done}/{self.total}"
        return (f"web frames {self.done}/{self.total}, {seconds_text(rate)} s a frame, "
                f"about {duration_text(rate * (self.total - self.done))} left")

    def drawn(self, hook_seconds: float, draw_seconds: float) -> None:
        """One more frame drawn: ``hook_seconds`` in the page's hooks, ``draw_seconds`` drawing it and taking the screenshot."""
        self.done += 1
        self.hook_seconds += hook_seconds
        self.draw_seconds += draw_seconds
        now = self._clock()
        if self.done == 1:
            self._after_first = now
        if self.done < self.total and now - self._last_line >= PROGRESS_SECONDS:
            self._last_line = now
            progress_log.info("%s", self.line())

    def summary(self) -> str:
        """The line after the last frame."""
        count = max(1, self.done)
        return (f"web frames {self.done}/{self.total} drawn in {duration_text(self._clock() - self._started)} "
                f"(the page ready in {self.ready_seconds:.1f} s before), "
                f"{seconds_text((self._clock() - self._started) / count)} s a frame (the page's frame(t, ctx) "
                f"{seconds_text(self.hook_seconds / count)} s, drawing and the screenshot {seconds_text(self.draw_seconds / count)} s)")

    def finish(self) -> None:
        """Log :meth:`summary`."""
        progress_log.info("%s", self.summary())


def scene_data(params: Any) -> dict[str, Any]:
    """The ``data:`` values of a ``web`` scene's params (a model or a mapping), ``{}`` when unset."""
    data = params.get("data") if isinstance(params, Mapping) else getattr(params, "data", None)
    return dict(data or {})


def clip_inputs(root: Path, entry: WebEntry, *, scene_id: str, size: tuple[int, int], fps: int, frames: int,
                theme: Mapping[str, Any] | None = None, data: Mapping[str, Any] | None = None,
                beats: Sequence[Mapping[str, Any]] = (), shape: Mapping[str, Any] | None = None,
                design_width: int | None = None, music: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What the clip is drawn from (stored in its record): the entry and its file's SHA-256,
    the size (the frames' pixels; the page's window too unless ``design_width`` gives its width
    in CSS pixels, §118.17: then ``design_width`` is among the inputs, and left out otherwise so
    that the keys of clips without it stay as they were), frame rate and frame count, what the page is given (theme,
    data, beats, the video's shape: aspect, orientation, frame size, region), that the frames
    keep their alpha, and vidgen's page files and Playwright version. The other files the page loads are checked
    from the record (:func:`loaded_changed`). ``music`` (§120.8, ``ctx.music``): with it the
    inputs name its SHA-256 and the music helper's; without it they leave ``music`` out, so the
    keys of clips without music data stay as they were."""
    path = entry_path(root, entry, scene_id)
    return {
        **({} if design_width is None else {"design_width": design_width}),
        **({} if music is None else {"music": {"data": payload_digest(music), "helper": helper_digest()}}),
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
              shape: Mapping[str, Any] | None, music: Mapping[str, Any] | None = None) -> tuple[WebEntry, dict[str, Any], dict[str, Any], str]:
    """The entry, ``data``, inputs (:func:`clip_inputs`) and key of a scene's clip."""
    entry = entry_of(params)
    data = scene_data(params)
    shape = dict(shape) if shape is not None else page_shape(size)
    inputs = clip_inputs(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames, theme=theme, data=data, beats=beats,
                         shape=shape, design_width=design_width_of(params), music=music)
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
                  shape: Mapping[str, Any] | None = None, layout_frames: Iterable[int] = (),
                  music: Mapping[str, Any] | None = None, intermediate: str = "lossless") -> Path:
    """``folder/<scene_id>.mkv``: ``frames`` screenshots with alpha (RGBA, FFV1 ``bgra``) of the
    scene's page (``params``: its ``page`` or ``script``, a path in the project folder ``root``,
    its ``data`` and its ``design_width``) at ``fps`` and ``size`` (the frames' pixels: the page's
    window, or with ``design_width`` a window that wide in CSS pixels drawn at ``size``, §118.17),
    drawn now (one Chromium) unless the clip there was drawn from the same inputs
    (:func:`clip_inputs`) and every file the page loaded then is unchanged. ``theme`` and
    ``beats`` are ``ctx.theme`` and ``ctx.beats`` (§118.9), ``shape`` the video's shape
    (:func:`~vidgen.web.inputs.page_shape`; default: a page filling a frame of ``size``, §118.11). Writes ``folder/<scene_id>.json`` =
    ``{"key", "inputs", "loaded"}`` beside it (``loaded``: served path -> SHA-256). When it draws,
    it also reads the page's text at ``layout_frames`` (after their screenshots) into
    ``<scene_id>.layout.json`` (:func:`web_page_layouts` reads them back, §118.12). ``music``:
    the scene's music data, ``ctx.music`` (§120.8). ``intermediate``: how the frames are kept
    (§120.9; ``compact``: H.264 4:4:4 with a lossless alpha stream, the record then says
    ``"intermediate": "compact"``); it is not in the key: a lossless clip is reused for either,
    a compact one only while ``compact`` is asked for. While it draws, :class:`FrameProgress`
    logs progress lines on ``vidgen.progress`` (§120.10)."""
    entry, data, inputs, key = _clip_key(root, scene_id, params, size=size, fps=fps, frames=frames, theme=theme, beats=beats, shape=shape,
                                         music=music)
    shape = inputs["shape"]
    clip, record = folder / f"{scene_id}.mkv", record_path(folder, scene_id)
    stored = read_record(record) or {}
    loaded = stored.get("loaded") if isinstance(stored.get("loaded"), dict) else {}
    if clip.is_file() and stored.get("key") == key and clip_serves(stored.get("intermediate"), intermediate):
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

    opened = time.monotonic()
    with WebPage(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames,
                 theme=dict(theme) if theme is not None else None, data=data, beats=[dict(b) for b in beats], shape=shape,
                 design_width=inputs.get("design_width"), music=dict(music) if music is not None else None) as page:
        progress = FrameProgress(frames, ready_seconds=time.monotonic() - opened)
        with FramesClipWriter(clip, fps, size, page.pixels, alpha=True, intermediate=intermediate) as writer:
            for n in range(frames):
                started = time.monotonic()
                page.advance(n)
                hooked = time.monotonic()
                png = page.screenshot(n)
                shot = time.monotonic()
                writer.put(png)   # decoded and encoded while the next frame is drawn (DESIGN.md §120.10)
                if n in wanted:
                    layouts[n] = page.layout(n)
                progress.drawn(hooked - started, shot - hooked)
        served = dict(sorted(page.loaded.items()))
    progress.finish()
    kept = {} if intermediate == "lossless" else {"intermediate": intermediate}
    write_text_atomic(record, json.dumps({"key": key, "inputs": inputs, "loaded": served, **kept}, indent=1) + "\n")
    _store_layouts(folder, scene_id, key, layouts)
    return clip


def web_page_layouts(root: Path, folder: Path, scene_id: str, params: Any, *, size: tuple[int, int], fps: int, frames: int,
                     theme: Mapping[str, Any] | None = None, beats: Sequence[Mapping[str, Any]] = (),
                     shape: Mapping[str, Any] | None = None, at: Iterable[int] = (),
                     music: Mapping[str, Any] | None = None) -> dict[int, dict[str, Any]]:
    """The page's text at frames ``at`` (frame -> the reading of ``data/web/layout.js``, page
    pixels), for the clip :func:`make_web_clip` makes from the same arguments: the readings kept
    beside the clip, else read now in one Chromium that steps the page frame by frame (no
    screenshots) to the last frame missing, and kept for next time (§118.12)."""
    entry, data, inputs, key = _clip_key(root, scene_id, params, size=size, fps=fps, frames=frames, theme=theme, beats=beats, shape=shape,
                                         music=music)
    wanted = sorted({min(max(int(n), 0), frames - 1) for n in at})
    layouts = _stored_layouts(folder, scene_id, key)
    missing = [n for n in wanted if n not in layouts]
    if missing:
        log.info("%s: reading the page's text at %d frame(s), stepping %d frames", scene_id, len(missing), missing[-1] + 1)
        with WebPage(root, entry, scene_id=scene_id, size=size, fps=fps, frames=frames,
                     theme=dict(theme) if theme is not None else None, data=data, beats=[dict(b) for b in beats],
                     shape=inputs["shape"], design_width=inputs.get("design_width"),
                     music=dict(music) if music is not None else None) as page:
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


__all__ = ["CLIP_VERSION", "PROGRESS_SECONDS", "FrameProgress", "clip_inputs", "duration_text", "seconds_text", "forget_web_clips",
           "layout_record_path", "loaded_changed", "make_web_clip", "scene_data", "web_page_layouts"]
