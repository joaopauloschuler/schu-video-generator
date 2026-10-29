"""Drawing primitives of the character generator (DESIGN.md §69.1, §69.47): styled shapes from
points, pieces marked to trail in the wind or as hair beyond the head, and the outline maths
the clothes need (a shape's outline as a polygon, a polygon cut to a box, its width at a
height, dots that fit inside it). Character units throughout (``y`` up)."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from manim import Polygon, VMobject

from vidgen.cartoon.character import OUTER_HAIR_ATTRIBUTE, TRAIL_ATTRIBUTE

#: How far each trailing piece turns in the wind, as a share of
#: :data:`~vidgen.cartoon.wind.TRAIL_DEGREES` (DESIGN.md §69.32): the scarf's end, long hair, a
#: bun, pointy and floppy ears, the hat; since Step 113 a ponytail, braids, a cap and a
#: necklace's pendant; since Step 114 an animal's tail (a bird's fan of feathers less) and its
#: long ears; since Step 124 a robot's antenna, a cape, a wizard hat and a party hat (a crown does
#: not). Round ears and the other hair styles do not trail.
TRAIL_WEIGHTS: dict[str, float] = {
    "scarf": 1.2, "long": 0.7, "bun": 0.4, "pointy": 0.35, "floppy": 1.0, "hat": 0.35,
    "ponytail": 0.9, "braids": 0.6, "cap": 0.25, "pendant": 0.5, "medal": 0.3,
    "tail": 0.8, "feathers": 0.4, "long_ears": 0.3,
    "antenna": 0.35, "cape": 0.9, "wizard_hat": 0.4, "party_hat": 0.2,
}

Point = tuple[float, float]


def outlined(mob: VMobject, fill: str, outline: str, width: float) -> VMobject:
    """``mob`` filled with ``fill`` and outlined ``width`` wide in ``outline``."""
    return mob.set_fill(fill, opacity=1).set_stroke(outline, width=width)


def filled(mob: VMobject, fill: str) -> VMobject:
    """``mob`` filled with ``fill``, no outline."""
    return mob.set_fill(fill, opacity=1).set_stroke(width=0)


def point_at(cx: float, cy: float, radius: float, degrees: float) -> Point:
    """The point ``radius`` from (cx, cy) at ``degrees`` counterclockwise from the right."""
    angle = math.radians(degrees)
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def arc_points(cx: float, cy: float, radii: Sequence[float], start_deg: float, end_deg: float) -> list[Point]:
    """Points from ``start_deg`` to ``end_deg`` around (cx, cy), one per radius (alternating
    radii give a zigzag)."""
    last = len(radii) - 1
    return [point_at(cx, cy, radius, start_deg + (end_deg - start_deg) * k / last) for k, radius in enumerate(radii)]


def polygon(points: Sequence[Sequence[float]]) -> Polygon:
    """A closed polygon through ``points`` (x, y)."""
    return Polygon(*(np.array([p[0], p[1], 0.0]) for p in points))


def tapered_band(
    points: Sequence[Point], start_width: float, end_width: float, tip_points: int = 7, *, profile: Callable[[float], float] | None = None,
) -> list[Point]:
    """The outline of a band along the path ``points``, ``start_width`` wide at the first point
    narrowing evenly to ``end_width`` at the last, with a round tip there (a tail, a feather).
    ``profile``: the width at each share (0..1) of the length instead (a bushy tail); the tip
    stays ``end_width`` wide."""
    if len(points) < 2:
        raise ValueError("a band needs two points or more")
    lengths = [0.0]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.hypot(x1 - x0, y1 - y0))
    total = lengths[-1] or 1e-9
    left, right = [], []
    for k, (x, y) in enumerate(points):
        x0, y0 = points[max(k - 1, 0)]
        x1, y1 = points[min(k + 1, len(points) - 1)]
        length = math.hypot(x1 - x0, y1 - y0) or 1e-9
        nx, ny = -(y1 - y0) / length, (x1 - x0) / length
        width = start_width + (end_width - start_width) * lengths[k] / total if profile is None else profile(lengths[k] / total)
        half = width / 2
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))
    (xa, ya), (xb, yb) = points[-2], points[-1]
    heading = math.degrees(math.atan2(yb - ya, xb - xa))
    tip = [point_at(xb, yb, end_width / 2, heading + 90 - 180 * k / (tip_points + 1)) for k in range(1, tip_points + 1)]
    return [*left, *tip, *reversed(right)]


def trailing(mob: VMobject, pivot: Sequence[float], piece: str) -> VMobject:
    """Mark ``mob`` as a piece that trails in the wind, turning about ``pivot`` by the weight of
    ``piece`` in :data:`TRAIL_WEIGHTS` (the :class:`~vidgen.cartoon.character.Character` reads
    the mark; DESIGN.md §69.32)."""
    for member in mob.get_family():
        setattr(member, TRAIL_ATTRIBUTE, (float(pivot[0]), float(pivot[1]), TRAIL_WEIGHTS[piece]))
    return mob


def outer_hair(mob: VMobject) -> VMobject:
    """Mark ``mob`` (drawn in the ``head`` part) as hair beyond the head (:data:`OUTER_HAIR_ATTRIBUTE`)."""
    for member in mob.get_family():
        setattr(member, OUTER_HAIR_ATTRIBUTE, True)
    return mob


# ----- outline maths (no drawing) -------------------------------------------------------------------


def outline_polygon(mob: VMobject, per_curve: int = 6) -> list[Point]:
    """The outline of ``mob`` (one closed path of cubic Bézier curves) as a polygon of
    ``per_curve`` points per curve."""
    curves = np.asarray(mob.points, dtype=float).reshape(-1, 4, 3)
    ts = np.linspace(0.0, 1.0, per_curve, endpoint=False)
    points: list[Point] = []
    for p0, p1, p2, p3 in curves:
        for t in ts:
            u = 1.0 - t
            x, y, _ = u**3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t**3 * p3
            points.append((float(x), float(y)))
    return points


def _clip_half_plane(points: Sequence[Point], axis: int, limit: float, keep_below: bool) -> list[Point]:
    """Sutherland-Hodgman: the part of the polygon ``points`` with coordinate ``axis`` at most
    (``keep_below``) or at least ``limit``."""
    def inside(p: Point) -> bool:
        return p[axis] <= limit if keep_below else p[axis] >= limit

    out: list[Point] = []
    for k, current in enumerate(points):
        previous = points[k - 1]
        if inside(current) != inside(previous):
            share = (limit - previous[axis]) / (current[axis] - previous[axis])
            out.append((previous[0] + share * (current[0] - previous[0]), previous[1] + share * (current[1] - previous[1])))
        if inside(current):
            out.append(current)
    return out


def clip_to_box(points: Sequence[Point], left: float = -math.inf, bottom: float = -math.inf,
                right: float = math.inf, top: float = math.inf) -> list[Point]:
    """The part of the polygon ``points`` inside the box (empty when nothing is)."""
    out = list(points)
    for axis, limit, keep_below in ((0, left, False), (0, right, True), (1, bottom, False), (1, top, True)):
        if math.isfinite(limit) and out:
            out = _clip_half_plane(out, axis, limit, keep_below)
    return out if len(out) >= 3 else []


def span_at(points: Sequence[Point], y: float) -> tuple[float, float] | None:
    """The leftmost and rightmost x where the polygon ``points`` crosses the height ``y``
    (``None``: it does not reach that height)."""
    xs = []
    for k, (x1, y1) in enumerate(points):
        x0, y0 = points[k - 1]
        if (y0 - y) * (y1 - y) <= 0 and y0 != y1:
            xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
    return (min(xs), max(xs)) if xs else None


def _inside(points: Sequence[Point], x: float, y: float) -> bool:
    crossings = 0
    for k, (x1, y1) in enumerate(points):
        x0, y0 = points[k - 1]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) / (y1 - y0) * (x1 - x0):
            crossings += 1
    return crossings % 2 == 1


def _edge_distance(points: Sequence[Point], x: float, y: float) -> float:
    best = math.inf
    for k, (x1, y1) in enumerate(points):
        x0, y0 = points[k - 1]
        dx, dy = x1 - x0, y1 - y0
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else min(max(((x - x0) * dx + (y - y0) * dy) / length2, 0.0), 1.0)
        best = min(best, math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)))
    return best


def dot_centres(points: Sequence[Point], spacing: float, radius: float, margin: float) -> list[Point]:
    """Centres of dots ``radius`` big on a grid ``spacing`` apart (every other row shifted half a
    step, a row through the polygon's middle) that lie inside the polygon ``points`` at least
    ``margin`` from its edge."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    rows = int((max(ys) - min(ys)) / spacing) + 2
    columns = int((max(xs) - min(xs)) / spacing) + 2
    found = []
    for row in range(-rows, rows + 1):
        y = cy + row * spacing
        shift = spacing / 2 if row % 2 else 0.0
        for column in range(-columns, columns + 1):
            x = cx + column * spacing + shift
            if _inside(points, x, y) and _edge_distance(points, x, y) >= radius + margin:
                found.append((x, y))
    return found


__all__ = [
    "TRAIL_WEIGHTS",
    "arc_points",
    "clip_to_box",
    "dot_centres",
    "filled",
    "outer_hair",
    "outline_polygon",
    "outlined",
    "point_at",
    "polygon",
    "span_at",
    "tapered_band",
    "trailing",
]
