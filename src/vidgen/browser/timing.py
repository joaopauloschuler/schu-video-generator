"""How many frames a scene drawn in Chromium needs, and its beats on the scene's clock
(``3d`` §114.1, ``web`` §118.1)."""

from __future__ import annotations

import math
from typing import Any

from vidgen.three_d.description import BeatSpan


def clip_plan(scene: Any, spare_frames: int) -> tuple[list[BeatSpan], int]:
    """The beats of ``scene`` (a ``NarratedScene``) on its clock and how many frames to draw:
    as long as the scene plays (its beats, or a silent scene's duration), then its outro, then
    ``spare_frames`` (the last one holds if the scene runs longer)."""
    from manim import config

    fps = int(config.frame_rate)
    spans: list[BeatSpan] = []
    frames = 0
    if scene.beats:
        for beat in scene.beats:
            window = scene.beat_window(beat)
            start = frames / fps
            spans.append(BeatSpan(beat.id, start, start + window.heard))
            frames += round(window.window * fps)
    else:
        frames = round(max((scene.spec.duration or 0.0) - scene.outro, 1 / fps) * fps)
    return spans, frames + math.ceil(scene.outro * fps) + spare_frames


def planned_still_frames(scene: Any) -> list[int]:
    """The frames a ``NarratedScene``'s capture will take stills of (its ``per_beat``; 1 without a
    capture), as :class:`~vidgen.capture.FrameCapture` plans them: each beat's evenly spaced
    stills and its last frame (``round(window * fps)`` frames per beat, as :func:`clip_plan`
    counts them), or a silent scene's stills. Mid-action stills are not predicted."""
    from manim import config

    from vidgen.capture import plan_targets

    fps = int(config.frame_rate)
    capture = getattr(scene, "capture", None)
    per_beat = int(capture.per_beat) if capture is not None else 1
    out: set[int] = set()
    if scene.beats:
        start = 0
        for beat in scene.beats:
            count = round(scene.beat_window(beat).window * fps)
            out.update(index for _, index in plan_targets(start, count, per_beat, include_end=False))
            out.add(start + max(count, 1) - 1)
            start += count
    else:
        length = max((scene.spec.duration or 0.0) - scene.outro, 1 / fps)
        out.update(index for _, index in plan_targets(0, round(length * fps), per_beat, include_end=True))
    return sorted(out)


__all__ = ["clip_plan", "planned_still_frames"]
