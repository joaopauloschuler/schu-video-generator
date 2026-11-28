"""The clip a ``web`` or ``3d`` scene's drawn frames are kept in until the scene plays them:
lossless FFV1 by default, or with ``render.intermediate: compact`` a small
H.264 picture (4:4:4, CRF :data:`COMPACT_CRF`) and, for frames with alpha, a lossless FFV1
alpha stream beside it in the same Matroska file (stream title :data:`ALPHA_TITLE`, read back
by :class:`vidgen.clips.ClipReader`).

:func:`write_frames_clip` writes one (:class:`FramesClipWriter`: in a thread beside the
drawing); :func:`clip_serves` tells whether a kept clip stored one way serves a render that asks
for another.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from types import TracebackType
from typing import Any, Literal

import numpy as np

from vidgen.errors import VidgenError

#: How a scene's drawn frames are kept (``render.intermediate``).
Intermediate = Literal["lossless", "compact"]
INTERMEDIATES: tuple[str, ...] = ("lossless", "compact")
#: The compact picture: libx264 at this CRF and preset, in 4:4:4 (no chroma subsampling, so
#: coloured edges stay sharp; the final encode subsamples once). Measured on Escapement's
#: frames: 4.6 times smaller than FFV1, 39-41 dB PSNR, SSIM 0.96-0.97 against the
#: lossless frames, and the final H.264 made from it within 0.25 dB of the one made from them.
COMPACT_CRF = "12"
COMPACT_PRESET = "veryfast"
#: Title of the lossless alpha stream of a compact clip with alpha.
ALPHA_TITLE = "alpha"


def clip_serves(stored: str | None, wanted: str) -> bool:
    """Whether a kept clip stored as ``stored`` (``None``: written before compact clips existed, lossless)
    serves a render asking for ``wanted``: a lossless clip serves both, a compact one only
    ``compact`` (asking for ``lossless`` draws the frames again)."""
    return (stored or "lossless") == "lossless" or wanted == "compact"


def write_frames_clip(path: Path, fps: int, size: tuple[int, int], frames: Iterable[np.ndarray], *, alpha: bool = False,
                      intermediate: str = "lossless") -> None:
    """Write ``frames`` (RGB arrays, H x W x 3, ``size`` = (W, H); with ``alpha`` RGBA, H x W x 4,
    straight alpha) in order to ``path`` (Matroska): ``lossless``, one FFV1 stream (``bgra`` with
    alpha, else ``bgr0``); ``compact``, an H.264 4:4:4 picture and, with ``alpha``, a lossless
    FFV1 ``gray`` alpha stream. Written to a ``.partial`` file first, so a failure (also one
    raised while ``frames`` is iterated) leaves none."""
    import av

    if intermediate not in INTERMEDIATES:
        raise VidgenError(f"unknown intermediate '{intermediate}' (one of {', '.join(INTERMEDIATES)})")
    width, height = size
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    given = "rgba" if alpha else "rgb24"
    try:
        with av.open(str(partial), mode="w", format="matroska") as container:
            if intermediate == "lossless":
                picture = container.add_stream("ffv1", rate=fps)
                stored = "bgra" if alpha else "bgr0"
            else:
                picture = container.add_stream("libx264", rate=fps, options={"crf": COMPACT_CRF, "preset": COMPACT_PRESET})
                stored = "yuv444p"
            picture.width, picture.height, picture.pix_fmt = width, height, stored
            mask = None
            if intermediate == "compact" and alpha:
                mask = container.add_stream("ffv1", rate=fps)
                mask.width, mask.height, mask.pix_fmt = width, height, "gray"
                mask.metadata["title"] = ALPHA_TITLE
            for n, pixels in enumerate(frames):
                frame = av.VideoFrame.from_ndarray(pixels, format=given).reformat(format=stored)
                frame.pts = n
                container.mux(picture.encode(frame))
                if mask is not None:
                    plane = av.VideoFrame.from_ndarray(np.ascontiguousarray(pixels[..., 3]), format="gray")
                    plane.pts = n
                    container.mux(mask.encode(plane))
            container.mux(picture.encode())
            if mask is not None:
                container.mux(mask.encode())
        try:
            os.replace(partial, path)
        except PermissionError:   # Windows: the old clip is open in another program (a player)
            raise VidgenError(f"cannot replace {path}: close the program that has it open and render again") from None
    finally:
        partial.unlink(missing_ok=True)


#: Progress while a clip's frames are drawn; the render worker prints it as
#: ``progress: ...`` lines, which ``vidgen render`` shows under the scene's name.
progress_log = logging.getLogger("vidgen.progress")
#: Seconds between two progress lines (at most one line in this time; the last frame always has one).
PROGRESS_SECONDS = 10.0


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
    frames after the first (the first compiles a WebGL page's shaders). ``what``: the words
    before the count (``3d frames`` for a ``3d`` scene, whose page draws and reads its canvas in
    one call: its summary has no split, Step 351)."""

    def __init__(self, total: int, *, ready_seconds: float = 0.0, clock: Callable[[], float] = time.monotonic,
                 what: str = "web frames") -> None:
        self.total, self._clock, self.what = total, clock, what
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
            return f"{self.what} {self.done}/{self.total}"
        return (f"{self.what} {self.done}/{self.total}, {seconds_text(rate)} s a frame, "
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
        head = (f"{self.what} {self.done}/{self.total} drawn in {duration_text(self._clock() - self._started)} "
                f"(the page ready in {self.ready_seconds:.1f} s before), {seconds_text((self._clock() - self._started) / count)} s a frame")
        if self.what != "web frames":
            return head
        return (f"{head} (the page's frame(t, ctx) {seconds_text(self.hook_seconds / count)} s, "
                f"drawing and the screenshot {seconds_text(self.draw_seconds / count)} s)")

    def finish(self) -> None:
        """Log :meth:`summary`."""
        progress_log.info("%s", self.summary())


class _Stopped(Exception):
    """The drawing failed: the clip being written is given up."""


_END, _STOP = object(), object()


class FramesClipWriter:
    """``with FramesClipWriter(path, fps, size, prepare, alpha=..., intermediate=...) as clip:
    clip.put(item)``: :func:`write_frames_clip` in a thread of its own, so a frame is decoded
    (``prepare(item)`` -> its pixels, e.g. a PNG decoded) and encoded while the next one is drawn.
    The frames are written in the order put; at most :attr:`DEPTH` wait. An
    error of the writer is raised by the next :meth:`put` or on leaving the block; an error inside
    the block stops the writer and leaves no clip (nor a ``.partial`` file)."""

    DEPTH = 2

    def __init__(self, path: Path, fps: int, size: tuple[int, int], prepare: Callable[[Any], np.ndarray], *, alpha: bool = False,
                 intermediate: str = "lossless") -> None:
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=self.DEPTH)
        self._prepare = prepare
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._write, args=(path, fps, size, alpha, intermediate), name="vidgen-frames-clip",
                                        daemon=True)

    def _frames(self) -> Iterator[np.ndarray]:
        while (item := self._queue.get()) is not _END:
            if item is _STOP:
                raise _Stopped
            yield self._prepare(item)

    def _write(self, path: Path, fps: int, size: tuple[int, int], alpha: bool, intermediate: str) -> None:
        try:
            write_frames_clip(path, fps, size, self._frames(), alpha=alpha, intermediate=intermediate)
        except _Stopped:
            pass
        except BaseException as exc:  # noqa: BLE001 - handed to the drawing thread
            self._error = exc

    def __enter__(self) -> FramesClipWriter:
        self._thread.start()
        return self

    def put(self, item: Any) -> None:
        """Hand the next frame to the writer (waits while :attr:`DEPTH` frames wait)."""
        self._send(item)

    def _send(self, item: Any) -> None:
        while True:
            if self._error is not None:
                raise self._error
            if not self._thread.is_alive():
                raise VidgenError("the frames clip writer stopped")
            try:
                self._queue.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        if exc is None:
            self._send(_END)
            self._thread.join()
            if self._error is not None:
                raise self._error
            return
        if self._thread.is_alive() and self._error is None:
            try:
                self._send(_STOP)
            except BaseException:  # noqa: BLE001 - the error inside the block is the one to raise
                pass
        self._thread.join()


__all__ = ["ALPHA_TITLE", "COMPACT_CRF", "COMPACT_PRESET", "INTERMEDIATES", "PROGRESS_SECONDS", "FrameProgress", "FramesClipWriter", "Intermediate",
           "clip_serves", "duration_text", "seconds_text", "write_frames_clip"]
