"""What happens over time in a rendered scene: the input of ``vidgen lint``'s timing rules.

Written by the worker next to the stills and the layout dump (``<render_dir>/activity/<scene>.json``,
DESIGN.md §17) whenever stills are captured:

- **beats**: each narrated beat's start, narration end (``start + d``), whether ``d`` came from
  its MP3 or the word-count estimate, and ``busy``: how long the beat's own code (its
  animations and waits) took before the scene waited for ``d + pad``;
- **plays**: every ``self.play``/``self.wait`` with scene times, beat and animation names
  (:class:`vidgen.scene.PlayRecord`);
- **motion**: a cheap per-frame change signal from :class:`MotionTrack`, which sees every frame
  the renderer writes (via :class:`vidgen.capture.FrameCapture`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from vidgen.scene import NarratedScene

#: Version of the activity file format.
ACTIVITY_VERSION = 1

#: At most this many sample points on the frame's shorter side (a 480p frame is sampled every
#: 3rd pixel, 1080p every 6th: 45 000-58 000 points per 16:9 frame, ~1.3 ms to compare).
MOTION_SAMPLES = 180

#: A sample point counts as changed when a colour channel moved by more than this (0-255).
MOTION_LEVEL = 6


class MotionTrack:
    """Per-frame change signal: the fraction of sample points that changed since the previous
    frame. Frames are sampled on a regular grid (no averaging: anti-aliased edges of moving
    objects change the samples they cross, a static frame changes none). A frozen ``wait`` is
    one frame written N times: only its first copy can differ from the frame before."""

    def __init__(self, samples: int = MOTION_SAMPLES, level: int = MOTION_LEVEL) -> None:
        self.samples = samples
        self.level = level
        self.step: int | None = None
        self.grid: tuple[int, int] | None = None
        self.changes: list[tuple[int, float]] = []
        self.frames = 0
        self._previous: np.ndarray | None = None

    def observe(self, frame: np.ndarray, index: int, count: int) -> None:
        """The renderer writes ``frame`` as frames ``index .. index + count - 1``."""
        if count <= 0:
            return
        if self.step is None:
            self.step = max(1, -(-min(frame.shape[0], frame.shape[1]) // self.samples))
        sampled = np.asarray(frame[:: self.step, :: self.step, :3], dtype=np.int16)
        if self.grid is None:
            self.grid = (int(sampled.shape[1]), int(sampled.shape[0]))
        if self._previous is None or self._previous.shape != sampled.shape:
            changed = 1.0
        else:
            moved = (np.abs(sampled - self._previous) > self.level).any(axis=2)
            changed = float(np.count_nonzero(moved)) / moved.size
        if changed > 0:
            self.changes.append((index, round(changed, 5) or 1e-5))
        self._previous = sampled
        self.frames = index + count

    def to_json(self) -> dict[str, Any]:
        """``{step, grid, level, changes: [[frame, fraction], ...]}`` (frames that changed only)."""
        return {
            "step": self.step,
            "grid": list(self.grid) if self.grid else None,
            "level": self.level,
            "changes": [[frame, fraction] for frame, fraction in self.changes],
        }


def activity_document(scene: NarratedScene, motion: MotionTrack, fps: int) -> dict[str, Any]:
    """The scene's activity file content (see the module docstring and DESIGN.md §17)."""
    sources = {}
    for beat in scene.beats:
        sources[beat.id] = "audio" if scene.beat_audio(beat) is not None else "estimate"
    beats = [
        {
            "id": entry.beat_id,
            "start": round(entry.start, 6),
            "end": round(entry.end, 6),
            "busy": round(scene.beat_busy.get(entry.beat_id, 0.0), 6),
            "source": sources.get(entry.beat_id, "estimate"),
            "text": entry.text,
        }
        for entry in scene.beat_log
    ]
    plays = [
        {
            "start": round(p.start, 6),
            "end": round(p.end, 6),
            "beat": p.beat,
            "animations": list(p.animations),
            "wait": p.wait,
            "requested": p.requested,
        }
        for p in scene.play_log
    ]
    return {
        "version": ACTIVITY_VERSION,
        "scene": scene.spec.id,
        "type": scene.spec.type,
        "fps": fps,
        "frames": motion.frames,
        "duration": round(float(scene.renderer.time), 6),
        "pad": scene.pad,
        "silent": {"duration": scene.spec.duration, "busy": round(scene.silent_busy, 6)}
        if scene.spec.silent and scene.silent_busy is not None
        else None,
        "beats": beats,
        "plays": plays,
        "motion": motion.to_json(),
        # the last frames a crossfade into the next scene covers (DESIGN.md §49): they blend away
        "overlap_out": scene.transition_out.overlap if scene.transition_out is not None else 0,
    }
