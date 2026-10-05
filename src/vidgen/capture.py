"""Frame capture: stills of a scene at chosen moments, taken while Manim renders it.

A :class:`FrameCapture` is attached to a :class:`~vidgen.scene.NarratedScene` (constructor
argument ``capture=``). It observes the frames the renderer writes (it wraps
``renderer.add_frame``) and never changes them, so frame timing and the beat log are exactly
those of a render without capture.

Moments: ``per_beat`` stills per beat, evenly spaced, the last one on the beat's last frame
(``per_beat=1``: the end of each beat). A silent scene counts as one beat (``beat`` is
``None``) lasting ``duration - outro``. For each moment the capture calls its listeners with
the scene (in the state of that frame) and a :class:`CapturedFrame`; :class:`StillWriter` is
the listener that saves PNGs and the index. Later tools (layout introspection) add listeners.
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from vidgen.fileio import write_bytes_atomic

if TYPE_CHECKING:
    from vidgen.scene import NarratedScene


@dataclass(frozen=True)
class CapturedFrame:
    """One captured moment of a scene.

    ``frame`` is the 0-based index of the frame in the scene's video and ``time`` its
    presentation time (``frame / fps``, seconds from the scene start). ``k`` is the still's
    1-based position within its beat (``n`` = stills per beat; ``k == n`` is the beat's end).
    ``pixels`` is the frame as written to the video (``height x width x 4`` RGBA, uint8).
    """

    scene_id: str
    beat_id: str | None
    k: int
    n: int
    frame: int
    time: float
    pixels: np.ndarray = field(repr=False, compare=False)


#: A capture listener: called with the scene (in the state of the captured frame) and the frame.
CaptureListener = Callable[["NarratedScene", CapturedFrame], None]


def plan_targets(start: int, frames: int, n: int, include_end: bool) -> list[tuple[int, int]]:
    """``(k, frame index)`` of the stills of a segment of ``frames`` frames starting at ``start``.

    Still ``k`` (1..n) is the last frame shown before ``k/n`` of the segment has elapsed, so
    ``k == n`` is the segment's last frame. Without ``include_end`` the last still is left out
    (it is taken when the segment actually ends). When the segment has fewer frames than
    stills, stills on the same frame are merged and the frame keeps the highest ``k``.
    """
    frames = max(frames, 1)
    last = start + frames - 1
    by_frame: dict[int, int] = {}
    for k in range(1, n + 1):
        index = start + max(math.ceil(k * frames / n - 1e-9), 1) - 1
        if include_end or index < last:
            by_frame[index] = k
    return sorted(((k, index) for index, k in by_frame.items()), key=lambda t: t[1])


@dataclass
class _Target:
    beat_id: str | None
    k: int
    frame: int


class FrameCapture:
    """Takes ``per_beat`` stills per beat of one scene and passes them to ``listeners``."""

    def __init__(self, per_beat: int = 1, listeners: Sequence[CaptureListener] = ()) -> None:
        if per_beat < 1:
            raise ValueError("per_beat must be at least 1")
        self.per_beat = per_beat
        self.listeners: list[CaptureListener] = list(listeners)
        self._scene: NarratedScene | None = None
        self._written = 0
        self._last: np.ndarray | None = None
        self._pending: list[_Target] = []
        self._open: dict[str | None, int] = {}

    @property
    def frames_written(self) -> int:
        """How many frames the renderer has written so far."""
        return self._written

    def attach(self, scene: NarratedScene) -> None:
        """Observe the frames ``scene``'s renderer writes (call once, after Manim built it)."""
        renderer = scene.renderer
        original = renderer.add_frame

        def add_frame(frame: Any, num_frames: int = 1) -> None:
            if not getattr(renderer, "skip_animations", False) and num_frames > 0:
                self._observe(frame, num_frames)
            original(frame, num_frames)

        renderer.add_frame = add_frame
        self._scene = scene

    def begin_segment(self, beat_id: str | None, frames: int, *, include_end: bool) -> None:
        """A beat (``None``: a silent scene) starts now and should last ``frames`` frames.

        With ``include_end`` its last still is planned now; otherwise :meth:`end_segment` takes it
        on the frame the beat actually ends with.
        """
        self._open[beat_id] = self._written
        for k, index in plan_targets(self._written, frames, self.per_beat, include_end):
            self._pending.append(_Target(beat_id, k, index))

    def end_segment(self, beat_id: str | None) -> None:
        """The beat ends now: take its last still on the last frame written."""
        start = self._open.pop(beat_id, None)
        if start is None or self._last is None or self._written <= start:
            return
        self._emit(self._last, _Target(beat_id, self.per_beat, self._written - 1))

    def finish(self) -> None:
        """The scene ends: planned stills it never reached are taken from its last frame."""
        pending, self._pending = self._pending, []
        if self._last is None or not pending:
            return
        for target in pending:
            self._emit(self._last, _Target(target.beat_id, target.k, self._written - 1))

    def _observe(self, frame: np.ndarray, num_frames: int) -> None:
        end = self._written + num_frames
        due = [t for t in self._pending if t.frame < end]
        if due:
            self._pending = [t for t in self._pending if t.frame >= end]
            for target in due:
                self._emit(frame, target)
        self._last = frame
        self._written = end

    def _emit(self, pixels: np.ndarray, target: _Target) -> None:
        scene = self._scene
        assert scene is not None, "FrameCapture.attach() was not called"
        from manim import config

        fps = config.frame_rate
        captured = CapturedFrame(
            scene.spec.id, target.beat_id, target.k, self.per_beat, target.frame, target.frame / fps, pixels
        )
        for listener in self.listeners:
            listener(scene, captured)


class StillWriter:
    """Capture listener that saves each still as a PNG in ``folder`` and builds its index.

    File names: ``<beat_id>-<k>.png`` (``<scene_id>-<k>.png`` for a silent scene).
    """

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.entries: list[dict[str, Any]] = []

    def __call__(self, scene: NarratedScene, captured: CapturedFrame) -> None:
        name = f"{captured.beat_id or captured.scene_id}-{captured.k}.png"
        buffer = io.BytesIO()
        Image.fromarray(np.asarray(captured.pixels, dtype=np.uint8)).convert("RGB").save(
            buffer, format="PNG", compress_level=3
        )
        write_bytes_atomic(self.folder / name, buffer.getvalue())
        self.entries.append(
            {
                "beat": captured.beat_id,
                "k": captured.k,
                "n": captured.n,
                "frame": captured.frame,
                "time": round(captured.time, 6),
                "path": name,
            }
        )

    def index(self, scene_id: str, per_beat: int, width: int, height: int, fps: int) -> dict[str, Any]:
        """The scene's ``index.json`` content: stills in frame order (paths relative to it)."""
        frames = sorted(self.entries, key=lambda e: (e["frame"], e["k"]))
        return {"scene": scene_id, "per_beat": per_beat, "width": width, "height": height, "fps": fps, "frames": frames}
