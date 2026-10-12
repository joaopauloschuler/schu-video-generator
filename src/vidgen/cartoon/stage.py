"""Stage geometry: marks, the ground line and depth (DESIGN.md §69.6). No manim.

A stage places things (characters now, props from Step 75) by a *mark* (a named x position) or
an x position, on a ground line, at a *depth*: 0 stands on the ground line at full size, 1 at the
back of the stage, higher up and smaller. Things further back are drawn first.

Positions are fractions of the frame: x from 0 (left edge) to 1 (right edge), the ground line's
height from the bottom edge as a fraction of the frame height. Sizes are fractions of the frame's
shorter side, so a character is as tall in 9:16 as in 16:9.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: The built-in marks: name -> x (0 = left edge, 1 = right edge).
MARKS: dict[str, float] = {"far_left": 0.1, "left": 0.25, "centre": 0.5, "right": 0.75, "far_right": 0.9}
#: Scale of a thing at depth 1 (the back of the stage); depth 0 is full size.
FAR_SCALE = 0.55
#: Height (fraction of the frame height) above the ground line where a thing at depth 1 stands.
FAR_RISE = 0.12


@dataclass(frozen=True)
class StageItem:
    """One thing to place: its name, kind (``character``), mark or x, depth and own scale."""

    name: str
    kind: str
    at: str | float
    depth: float = 0.0
    scale: float = 1.0


@dataclass(frozen=True)
class StagePlacement:
    """Where a :class:`StageItem` goes, in Manim units: ``feet`` (x, y) on screen and ``height``
    (its full size times its depth scale). ``index`` is its position in the input list."""

    name: str
    kind: str
    index: int
    x_fraction: float
    depth: float
    feet: tuple[float, float]
    height: float


def known_marks(marks: Mapping[str, float] | None = None) -> dict[str, float]:
    """The built-in :data:`MARKS` with a stage's own ``marks`` (same name: its own wins)."""
    return {**MARKS, **(marks or {})}


def unknown_mark_message(name: str, known: Sequence[str]) -> str:
    """``unknown mark 'centr'; did you mean 'centre'? marks: far_left, left, ...``."""
    close = difflib.get_close_matches(name, list(known), n=1, cutoff=0.6)
    hint = f"; did you mean '{close[0]}'?" if close else ""
    return f"unknown mark '{name}'{hint} marks: {', '.join(known)} (or an x position from 0 to 1)"


def mark_x(at: str | float, marks: Mapping[str, float] | None = None) -> float:
    """The x (0..1) of a mark name or of an x position; ``ValueError`` for an unknown mark or an x
    outside 0..1."""
    if isinstance(at, str):
        table = known_marks(marks)
        if at not in table:
            raise ValueError(unknown_mark_message(at, list(table)))
        return float(table[at])
    if not 0.0 <= at <= 1.0:
        raise ValueError(f"x position {at} is outside the frame (use 0 = left edge to 1 = right edge)")
    return float(at)


def depth_scale(depth: float) -> float:
    """How much smaller a thing at ``depth`` (0..1) is drawn: 1 at the front, :data:`FAR_SCALE` at
    the back, linear between."""
    return 1.0 - (1.0 - FAR_SCALE) * depth


def feet_point(x_fraction: float, depth: float, ground: float, frame_width: float, frame_height: float) -> tuple[float, float]:
    """The feet of a thing at ``x_fraction`` and ``depth`` on a ground line ``ground`` (a fraction
    of the frame height above the bottom edge), in Manim units (origin in the frame's centre)."""
    x = (x_fraction - 0.5) * frame_width
    y = (ground + FAR_RISE * depth - 0.5) * frame_height
    return (x, y)


def draw_order(depths: Sequence[float]) -> list[int]:
    """Indices of ``depths`` from the back to the front: deeper first, ties in list order."""
    return sorted(range(len(depths)), key=lambda i: (-depths[i], i))


def stage_layout(
    items: Sequence[StageItem],
    *,
    marks: Mapping[str, float] | None = None,
    ground: float,
    size: float,
    frame_width: float,
    frame_height: float,
) -> list[StagePlacement]:
    """Where each item goes, in draw order (back to front). ``size`` is the height of a thing of
    scale 1 at depth 0, as a fraction of the frame's shorter side."""
    short_side = min(frame_width, frame_height)
    placements = []
    for i in draw_order([item.depth for item in items]):
        item = items[i]
        x = mark_x(item.at, marks)
        placements.append(
            StagePlacement(
                name=item.name,
                kind=item.kind,
                index=i,
                x_fraction=x,
                depth=item.depth,
                feet=feet_point(x, item.depth, ground, frame_width, frame_height),
                height=size * short_side * item.scale * depth_scale(item.depth),
            )
        )
    return placements


def facing_towards_centre(x_fraction: float) -> str:
    """``right`` for a thing on the left half of the stage (or in the middle), else ``left``: so
    two characters on either side face each other."""
    return "right" if x_fraction <= 0.5 else "left"


__all__ = [
    "FAR_RISE",
    "FAR_SCALE",
    "MARKS",
    "StagePlacement",
    "StageItem",
    "depth_scale",
    "draw_order",
    "facing_towards_centre",
    "feet_point",
    "known_marks",
    "mark_x",
    "stage_layout",
    "unknown_mark_message",
]
