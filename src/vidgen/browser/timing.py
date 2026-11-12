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


__all__ = ["clip_plan"]
