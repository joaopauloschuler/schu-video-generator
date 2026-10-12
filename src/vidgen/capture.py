"""Frame capture: stills of a scene at chosen moments, taken while Manim renders it.

A :class:`FrameCapture` is attached to a :class:`~vidgen.scene.NarratedScene` (constructor
argument ``capture=``). It observes the frames the renderer writes (it wraps
``renderer.add_frame``) and never changes them, so frame timing and the beat log are exactly
those of a render without capture.

Moments: ``per_beat`` stills per beat, evenly spaced, the last one on the beat's last frame
(``per_beat=1``: the end of each beat). A silent scene counts as one beat (``beat`` is
``None``) lasting ``duration - outro``. Scene types that name actions in
:attr:`~vidgen.scene.NarratedScene.mid_still_actions` (``stage``: walks, gestures, jumps,
keyframes...) also get a *mid-action* still half-way through each such action
(:meth:`FrameCapture.add_mid_still`, chosen by :func:`mid_action_frame`; ``k`` 0, ``mid`` names
the actions). For each moment the capture calls its listeners with
the scene (in the state of that frame) and a :class:`CapturedFrame`; :class:`StillWriter` is
the listener that saves PNGs and the index; :class:`vidgen.introspect.LayoutRecorder` records
the layout of the same frames.
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
    from vidgen.activity import MotionTrack
    from vidgen.scene import NarratedScene


@dataclass(frozen=True)
class CapturedFrame:
    """One captured moment of a scene.

    ``frame`` is the 0-based index of the frame in the scene's video and ``time`` its
    presentation time (``frame / fps``, seconds from the scene start). ``k`` is the still's
    1-based position within its beat (``n`` = stills per beat; ``k == n`` is the beat's end).
    ``pixels`` is the frame as written to the video (``height x width x 4`` RGBA, uint8).
    A mid-action still has ``k`` 0 and ``mid`` the actions it shows half-way (``walk_to pip``).
    """

    scene_id: str
    beat_id: str | None
    k: int
    n: int
    frame: int
    time: float
    pixels: np.ndarray = field(repr=False, compare=False)
    mid: str | None = None


#: A capture listener: called with the scene (in the state of the captured frame) and the frame.
CaptureListener = Callable[["NarratedScene", CapturedFrame], None]


def still_name(captured: CapturedFrame) -> str:
    """File name of a still: ``<beat_id>-<k>.png`` (``<scene_id>-<k>.png`` for a silent scene);
    a mid-action still ``<beat_id>-m<frame>.png``."""
    if captured.mid is not None:
        return f"{captured.beat_id or captured.scene_id}-m{captured.frame}.png"
    return f"{captured.beat_id or captured.scene_id}-{captured.k}.png"


#: Seconds kept between a mid-action still and any other still of its beat.
MID_STILL_GAP_SECONDS = 0.4
#: Most mid-action stills in one beat (the sheets stay small).
MAX_MID_STILLS = 3


def mid_action_frame(start: int, frames: int, taken: Sequence[int], *, min_gap: int) -> int | None:
    """The still half-way through an action that plays ``frames`` frames from frame ``start``
    (``start + frames // 2``), or ``None`` when the action lasts under two frames or another still
    of the beat (``taken``: frame indexes) is less than ``min_gap`` frames away."""
    if frames < 2:
        return None
    middle = start + frames // 2
    if any(abs(middle - frame) < min_gap for frame in taken):
        return None
    return middle


def mid_action_frames(
    spans: Sequence[tuple[int, int]], taken: Sequence[int], *, min_gap: int, limit: int = MAX_MID_STILLS
) -> list[int]:
    """The mid-action stills of one beat whose actions play ``spans`` (``(start frame, frames)``
    in play order) and whose other stills are ``taken``: :func:`mid_action_frame` of each span in
    turn, each also kept ``min_gap`` from those chosen before it, at most ``limit``. This is what
    :meth:`FrameCapture.add_mid_still` does one action at a time while the scene renders."""
    chosen: list[int] = []
    for start, frames in spans:
        if len(chosen) >= limit:
            break
        frame = mid_action_frame(start, frames, [*taken, *chosen], min_gap=min_gap)
        if frame is not None:
            chosen.append(frame)
    return chosen


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
    mid: str | None = None


class FrameCapture:
    """Takes ``per_beat`` stills per beat of one scene and passes them to ``listeners``.

    ``motion`` (a :class:`vidgen.activity.MotionTrack`) is shown every frame written, for the
    timing lint's change signal.
    """

    def __init__(
        self, per_beat: int = 1, listeners: Sequence[CaptureListener] = (), motion: MotionTrack | None = None
    ) -> None:
        if per_beat < 1:
            raise ValueError("per_beat must be at least 1")
        self.per_beat = per_beat
        self.listeners: list[CaptureListener] = list(listeners)
        self.motion = motion
        self._scene: NarratedScene | None = None
        self._written = 0
        self._last: np.ndarray | None = None
        self._pending: list[_Target] = []
        self._open: dict[str | None, int] = {}
        #: Per beat: the frames of its stills (planned or taken), and how many are mid-action.
        self._beat_frames: dict[str | None, list[int]] = {}
        self._mid_count: dict[str | None, int] = {}

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
        planned = self._beat_frames.setdefault(beat_id, [])
        planned.append(self._written + max(frames, 1) - 1)  # its end
        for k, index in plan_targets(self._written, frames, self.per_beat, include_end):
            self._pending.append(_Target(beat_id, k, index))
            planned.append(index)

    def add_mid_still(self, beat_id: str | None, start: int, frames: int, label: str) -> int | None:
        """An action (``label``, e.g. ``walk_to pip``) of beat ``beat_id`` plays ``frames``
        frames from frame ``start``: plan a still half-way through it (:func:`mid_action_frame`,
        at most :data:`MAX_MID_STILLS` per beat). Returns its frame, or ``None`` if none is planned."""
        if self._mid_count.get(beat_id, 0) >= MAX_MID_STILLS:
            return None
        from manim import config

        planned = self._beat_frames.setdefault(beat_id, [])
        min_gap = max(round(MID_STILL_GAP_SECONDS * config.frame_rate), 1)
        frame = mid_action_frame(start, frames, planned, min_gap=min_gap)
        if frame is None or frame < self._written:
            return None
        planned.append(frame)
        self._mid_count[beat_id] = self._mid_count.get(beat_id, 0) + 1
        self._pending.append(_Target(beat_id, 0, frame, label))
        self._pending.sort(key=lambda t: t.frame)
        return frame

    def end_segment(self, beat_id: str | None) -> None:
        """The beat ends now: take its last still on the last frame written."""
        start = self._open.pop(beat_id, None)
        if start is None or self._last is None or self._written <= start:
            return
        self._emit(self._last, _Target(beat_id, self.per_beat, self._written - 1))

    def finish(self) -> None:
        """The scene ends: planned stills it never reached are taken from its last frame (not a
        mid-action one: its action did not play)."""
        pending, self._pending = [t for t in self._pending if t.mid is None], []
        if self._last is None or not pending:
            return
        for target in pending:
            self._emit(self._last, _Target(target.beat_id, target.k, self._written - 1))

    def _observe(self, frame: np.ndarray, num_frames: int) -> None:
        end = self._written + num_frames
        if self.motion is not None:
            self.motion.observe(frame, self._written, num_frames)
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
            scene.spec.id, target.beat_id, target.k, self.per_beat, target.frame, target.frame / fps, pixels, target.mid
        )
        for listener in self.listeners:
            listener(scene, captured)


class StillWriter:
    """Capture listener that saves each still as a PNG in ``folder`` and builds its index.

    File names: :func:`still_name`.
    """

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.entries: list[dict[str, Any]] = []

    def __call__(self, scene: NarratedScene, captured: CapturedFrame) -> None:
        name = still_name(captured)
        buffer = io.BytesIO()
        Image.fromarray(np.asarray(captured.pixels, dtype=np.uint8)).convert("RGB").save(
            buffer, format="PNG", compress_level=3
        )
        write_bytes_atomic(self.folder / name, buffer.getvalue())
        entry: dict[str, Any] = {
            "beat": captured.beat_id,
            "k": captured.k,
            "n": captured.n,
            "frame": captured.frame,
            "time": round(captured.time, 6),
            "path": name,
        }
        if captured.mid is not None:
            entry["mid"] = captured.mid
        self.entries.append(entry)

    def index(self, scene_id: str, per_beat: int, width: int, height: int, fps: int) -> dict[str, Any]:
        """The scene's ``index.json`` content: stills in frame order (paths relative to it)."""
        frames = sorted(self.entries, key=lambda e: (e["frame"], e["k"]))
        return {"scene": scene_id, "per_beat": per_beat, "width": width, "height": height, "fps": fps, "frames": frames}
