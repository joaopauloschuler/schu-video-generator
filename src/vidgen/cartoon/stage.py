"""Stage geometry: marks, the ground line and depth (DESIGN.md §69.6). No manim.

A stage places things (characters and props) by a *mark* (a named x position) or
an x position, on a ground line, at a *depth*: 0 stands on the ground line at full size, 1 at the
back of the stage, higher up and smaller. Things further back are drawn first.

Positions are fractions of the stage: x from 0 (left edge) to 1 (right edge) of the stage (as
wide as the frame, or ``width`` frames for a camera to pan across), the ground line's height from
the bottom edge as a fraction of the frame height. Sizes are fractions of the frame's shorter
side, so a character is as tall in 9:16 as in 16:9.

*Layers* (Step 74) are pictures or shapes drawn behind the ground (``background``, ``middle``) or
in front of the characters (``foreground``) that move by their *parallax factor* when the camera
moves: the stage and its characters move by 1, a far layer less, a near one more.
"""

from __future__ import annotations

import difflib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

#: The built-in marks: name -> x (0 = left edge, 1 = right edge).
MARKS: dict[str, float] = {"far_left": 0.1, "left": 0.25, "centre": 0.5, "right": 0.75, "far_right": 0.9}
#: Scale of a thing at depth 1 (the back of the stage); depth 0 is full size.
FAR_SCALE = 0.55
#: Height (fraction of the frame height) above the ground line where a thing at depth 1 stands.
FAR_RISE = 0.12
#: Where a layer is drawn: behind the ground band (``background``, then ``middle``) or in front of
#: the characters (``foreground``).
LAYER_PLACES: tuple[str, ...] = ("background", "middle", "foreground")
#: A layer's parallax factor when it gives none: how far it moves on screen for a camera move
#: that moves the stage (and its characters) by one unit.
DEFAULT_FACTORS: dict[str, float] = {"background": 0.3, "middle": 0.6, "foreground": 1.4}
#: Largest camera zoom a layer is sized for (the ``zoom`` action allows up to 8).
MAX_ZOOM = 8.0


@dataclass(frozen=True)
class StageItem:
    """One thing to place: its name, kind (``character`` or ``prop``), mark or x, depth, own
    scale and ``lift`` (how far above the ground line it hangs, a fraction of the frame height)."""

    name: str
    kind: str
    at: str | float
    depth: float = 0.0
    scale: float = 1.0
    lift: float = 0.0


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


def numbered_names(entries: Sequence[tuple[str | None, str]]) -> list[str]:
    """Each ``(own name, default name)`` entry's name: its own, else its default numbered from the
    second use of that default on (``tree``, ``tree_2``): the names of a stage's props and layers."""
    names: list[str] = []
    count: dict[str, int] = {}
    for own, default in entries:
        if own is not None:
            names.append(own)
            continue
        count[default] = count.get(default, 0) + 1
        names.append(default + (f"_{count[default]}" if count[default] > 1 else ""))
    return names


def prop_default_name(prop: str | None, svg: str | None) -> str:
    """A prop's default name: the built-in prop's name (``tree``), or the SVG's file name made an
    identifier (``old_well``)."""
    if prop is not None:
        return prop
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", PurePosixPath(svg or "").stem).strip("_")
    return stem or "prop"


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


def ground_top(ground: float, items: Sequence[StageItem] = ()) -> float:
    """The top of the ground area (a fraction of the frame height above the bottom edge): the
    ground line, or higher, the line where the deepest item standing on the ground (``lift`` 0)
    stands, so everything at a depth stands on the drawn ground, not above it (§69.6). Items
    with a ``lift`` hang in the air and do not count."""
    depths = [item.depth for item in items if item.lift == 0]
    return ground + FAR_RISE * max(depths, default=0.0)


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
    stage_width: float | None = None,
) -> list[StagePlacement]:
    """Where each item goes, in draw order (back to front). ``size`` is the height of a thing of
    scale 1 at depth 0, as a fraction of the frame's shorter side; x positions are fractions of
    ``stage_width`` (Manim units, default the frame's width), centred on the frame's centre."""
    short_side = min(frame_width, frame_height)
    width = frame_width if stage_width is None else stage_width
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
                feet=feet_point(x, item.depth, ground + item.lift, width, frame_height),
                height=size * short_side * item.scale * depth_scale(item.depth),
            )
        )
    return placements


def facing_towards_centre(x_fraction: float) -> str:
    """``right`` for a thing on the left half of the stage (or in the middle), else ``left``: so
    two characters on either side face each other."""
    return "right" if x_fraction <= 0.5 else "left"


def layer_transform(factor: float, camera_center: Sequence[float], zoom: float) -> tuple[float, tuple[float, float]]:
    """``(scale, (dx, dy))``: how to move a layer drawn for the camera's home view (centre at the
    origin, zoom 1) so that, seen through a camera at ``camera_center`` (x, y) with ``zoom``
    (frame width / view width), it appears moved by ``factor`` times the camera's move and
    magnified by ``zoom ** factor``. Scale about the origin first, then shift. Factor 1 (the
    stage): no change; factor 0: fixed on screen.

    A point ``b`` of the layer is shown at ``zoom ** factor * (b - factor * camera_center)`` from
    the frame's centre, so it sits in the scene at ``k * b + camera_center * (1 - factor * k)``
    with ``k = zoom ** (factor - 1)``."""
    k = zoom ** (factor - 1.0)
    keep = 1.0 - factor * k
    return k, (camera_center[0] * keep, camera_center[1] * keep)


def layer_half_extent(
    factor: float, *, stage_width: float, frame_width: float, frame_height: float, max_zoom: float = MAX_ZOOM
) -> tuple[float, float]:
    """Half the width and height (Manim units, about the origin) a layer must cover so that no
    camera view inside the stage (``stage_width`` x ``frame_height``, zoom 1 to ``max_zoom``)
    shows past its edges. A layer seen at zoom ``z`` from a centre ``c`` shows ``|b| <= half
    view / z ** factor + factor * |c|``; the largest over ``z`` is found on a fine grid."""
    best_x = best_y = 0.0
    steps = 64
    for i in range(steps + 1):
        z = 1.0 + (max_zoom - 1.0) * i / steps
        reach_x = max(stage_width - frame_width / z, 0.0) / 2  # the farthest a view's centre gets
        reach_y = max(frame_height - frame_height / z, 0.0) / 2
        best_x = max(best_x, frame_width / 2 / z**factor + factor * reach_x)
        best_y = max(best_y, frame_height / 2 / z**factor + factor * reach_y)
    return (math.ceil(best_x * 1000) / 1000, math.ceil(best_y * 1000) / 1000)


__all__ = [
    "DEFAULT_FACTORS",
    "FAR_RISE",
    "FAR_SCALE",
    "LAYER_PLACES",
    "MARKS",
    "MAX_ZOOM",
    "StagePlacement",
    "StageItem",
    "depth_scale",
    "draw_order",
    "facing_towards_centre",
    "feet_point",
    "ground_top",
    "known_marks",
    "layer_half_extent",
    "layer_transform",
    "mark_x",
    "stage_layout",
    "unknown_mark_message",
]
