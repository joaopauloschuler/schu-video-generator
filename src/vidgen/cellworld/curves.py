"""Exact outlines of the cell world's shapes as cubic Bézier pieces in µm (DESIGN.md §95.6):
what the renderer draws and what the boolean operations of :mod:`.regions` combine. A piece is
four points ``(p0, p1, p2, p3)``; a closed outline is a list of pieces end to end. No manim."""

from __future__ import annotations

import math
from collections.abc import Sequence

from .geometry import ArcBand, Capsule, Ellipse, Point, Polyline, RoundedBox

Cubic = tuple[Point, Point, Point, Point]
#: Arc pieces are at most this many radians, so a 100 µm outline stays within 0.1 nm of its
#: true curve at any zoom.
ARC_STEP = math.pi / 8


def arc_step(r: float) -> float:
    """The longest arc piece (radians) for radius ``r`` µm: a quarter circle for small things
    (within 0.01 nm of a true circle up to 50 nm), shorter for large ones."""
    return math.pi / 2 if r < 0.05 else math.pi / 4 if r < 1.0 else ARC_STEP


def arc(cx: float, cy: float, r: float, a0: float, a1: float, step: float | None = None) -> list[Cubic]:
    """A circular arc from angle ``a0`` to ``a1`` (either way round), in pieces of at most
    ``step`` radians (default: :func:`arc_step` of ``r``)."""
    pieces = max(1, math.ceil(abs(a1 - a0) / (step or arc_step(abs(r))) - 1e-9))
    step = (a1 - a0) / pieces
    k = 4 / 3 * math.tan(step / 4) * r
    out = []
    for i in range(pieces):
        a, b = a0 + i * step, a0 + (i + 1) * step
        p0 = (cx + r * math.cos(a), cy + r * math.sin(a))
        p3 = (cx + r * math.cos(b), cy + r * math.sin(b))
        p1 = (p0[0] - k * math.sin(a), p0[1] + k * math.cos(a))
        p2 = (p3[0] + k * math.sin(b), p3[1] - k * math.cos(b))
        out.append((p0, p1, p2, p3))
    return out


def line(p: Point, q: Point) -> Cubic:
    """A straight piece."""
    return (p, (p[0] + (q[0] - p[0]) / 3, p[1] + (q[1] - p[1]) / 3), (p[0] + 2 * (q[0] - p[0]) / 3, p[1] + 2 * (q[1] - p[1]) / 3), q)


def transform(curves: Sequence[Cubic], angle: float = 0.0, dx: float = 0.0, dy: float = 0.0, sx: float = 1.0, sy: float = 1.0) -> list[Cubic]:
    """Scale (``sx``, ``sy``), turn by ``angle`` and move by ``(dx, dy)``."""
    c, s = math.cos(angle), math.sin(angle)

    def f(p: Point) -> Point:
        x, y = p[0] * sx, p[1] * sy
        return (x * c - y * s + dx, x * s + y * c + dy)

    return [(f(a), f(b), f(e), f(d)) for a, b, e, d in curves]  # type: ignore[misc]


def polygon(points: Sequence[Point]) -> list[Cubic]:
    """A closed outline of straight pieces through ``points``."""
    return [line(p, q) for p, q in zip(points, [*points[1:], points[0]])]


def smooth(points: Sequence[Point], closed: bool = False, tension: float = 1.0) -> list[Cubic]:
    """A smooth curve through ``points`` (Catmull–Rom as Bézier pieces); ``closed`` joins the
    last point to the first."""
    pts = list(points)
    n = len(pts)
    if n < 2:
        return []
    out = []
    count = n if closed else n - 1
    for i in range(count):
        p0 = pts[(i - 1) % n] if closed or i > 0 else pts[i]
        p1, p2 = pts[i], pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed or i + 2 < n else p2
        t = tension / 6
        c1 = (p1[0] + (p2[0] - p0[0]) * t, p1[1] + (p2[1] - p0[1]) * t)
        c2 = (p2[0] - (p3[0] - p1[0]) * t, p2[1] - (p3[1] - p1[1]) * t)
        out.append((p1, c1, c2, p2))
    return out


def shape_curves(shape: object, grow: float = 0.0) -> list[Cubic]:
    """One closed outline of ``shape`` (µm) grown outwards by ``grow`` µm (negative: inwards);
    a :class:`~.regions.Region` gives all its outlines; a :class:`Polyline` its line (open)."""
    if isinstance(shape, Ellipse):
        step = arc_step(max(shape.a, shape.b) + grow)
        return transform(arc(0.0, 0.0, 1.0, 0.0, 2 * math.pi, step), shape.angle, shape.cx, shape.cy, shape.a + grow, shape.b + grow)
    if isinstance(shape, Capsule):
        h, r = shape.half, shape.radius + grow
        local = [line((-h, -r), (h, -r)), *arc(h, 0.0, r, -math.pi / 2, math.pi / 2), line((h, r), (-h, r)),
                 *arc(-h, 0.0, r, math.pi / 2, 3 * math.pi / 2)]
        return transform(local, shape.angle, shape.cx, shape.cy)
    if isinstance(shape, ArcBand):
        half = shape.thickness / 2 + grow
        (sx, sy), (ex, ey) = shape.ends()
        return [*arc(shape.cx, shape.cy, shape.radius + half, shape.start, shape.end),
                *arc(ex, ey, half, shape.end, shape.end + math.pi),
                *arc(shape.cx, shape.cy, shape.radius - half, shape.end, shape.start),
                *arc(sx, sy, half, shape.start + math.pi, shape.start + 2 * math.pi)]
    if isinstance(shape, RoundedBox):
        hx, hy, r = shape._corner()
        r += grow
        if r < 0:
            hx, hy, r = hx + r, hy + r, 0.0
        local: list[Cubic] = []
        corners = [((hx, hy), 0.0), ((-hx, hy), math.pi / 2), ((-hx, -hy), math.pi), ((hx, -hy), 1.5 * math.pi)]
        for k, ((ox, oy), a0) in enumerate(corners):
            if r > 0:
                local += arc(ox, oy, r, a0, a0 + math.pi / 2)
            end = (ox + r * math.cos(a0 + math.pi / 2), oy + r * math.sin(a0 + math.pi / 2))
            (nx, ny), b0 = corners[(k + 1) % 4]
            start = (nx + r * math.cos(b0), ny + r * math.sin(b0))
            if math.dist(end, start) > 1e-12:
                local.append(line(end, start))
        return transform(local, shape.angle, shape.cx, shape.cy)
    if isinstance(shape, Polyline):
        return [line(p, q) for p, q in zip(shape.points, shape.points[1:])]
    contours = getattr(shape, "contours", None)
    if contours is not None:
        return [c for contour in contours() for c in contour]
    raise TypeError(f"no outline for {type(shape).__name__}")


def flatten(curves: Sequence[Cubic], steps: int = 8) -> list[Point]:
    """Points along ``curves`` (``steps`` per piece, the last point included)."""
    out: list[Point] = []
    for p0, p1, p2, p3 in curves:
        for k in range(steps):
            t = k / steps
            u = 1 - t
            out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                        u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    if curves:
        out.append(curves[-1][3])
    return out
