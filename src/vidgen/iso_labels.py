"""Where an iso diagram's labels go (DESIGN.md §90.8): plain geometry on the picture, no manim,
shared by the ``iso_diagram`` scene (placing) and lint's ``iso_labels`` rule (checking).

Coordinates are ``x`` right, ``y`` up (scene units, or picture units turned up the right way);
a rectangle is ``(left, bottom, right, top)``. What labels keep clear of is drawn convex: a block
on the picture is a convex outline (a box's six corners, a cylinder's two ellipses), so a label is
pushed off it along a straight line (:func:`slide_out`) and what it still covers is measured
exactly (:func:`clip_area`).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

Rect = tuple[float, float, float, float]

#: What a label covers costs: another label's area this many times, a block's area once, and
#: a connector this much per sample point under it (square units of area).
LABEL_WEIGHT = 3.0
BLOCK_WEIGHT = 4.0
LINE_COST = 0.08
#: A block within a label's clearance counts this share of the area it has there (it is not
#: covered, but the label could be read as its).
NEAR_WEIGHT = 0.3
#: A label pushed away from what it names (with a leader line) costs this much per unit of
#: distance, so a slightly crowded place close by can win over a free one far off.
FAR_COST = 1.0


def convex_hull(points: Iterable[Sequence[float]]) -> np.ndarray:
    """The convex hull of ``points`` (N x 2), counter-clockwise, without repeated points."""
    pts = sorted({(round(float(p[0]), 9), round(float(p[1]), 9)) for p in points})
    if len(pts) <= 2:
        return np.array(pts, dtype=float).reshape(-1, 2)

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1], dtype=float)


def rect_of(centre: Sequence[float], size: Sequence[float]) -> Rect:
    """The rectangle of ``size`` (width, height) around ``centre``."""
    return (centre[0] - size[0] / 2, centre[1] - size[1] / 2, centre[0] + size[0] / 2, centre[1] + size[1] / 2)


def overlap_area(a: Rect, b: Rect) -> float:
    """The area two rectangles share."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def rect_union(rects: Iterable[Rect]) -> Rect:
    """The rectangle around ``rects``."""
    found = list(rects)
    return min(r[0] for r in found), min(r[1] for r in found), max(r[2] for r in found), max(r[3] for r in found)


def hull_box(hull: np.ndarray) -> Rect:
    return float(hull[:, 0].min()), float(hull[:, 1].min()), float(hull[:, 0].max()), float(hull[:, 1].max())


def clip_area(rect: Rect, hull: np.ndarray) -> float:
    """The area of the convex polygon ``hull`` inside ``rect`` (Sutherland-Hodgman)."""
    if len(hull) < 3 or overlap_area(rect, hull_box(hull)) <= 0:
        return 0.0
    poly = [tuple(p) for p in hull]
    left, bottom, right, top = rect
    for axis, limit, keep_above in ((0, left, True), (0, right, False), (1, bottom, True), (1, top, False)):
        if not poly:
            return 0.0
        out: list[tuple[float, float]] = []
        for k, cur in enumerate(poly):
            prev = poly[k - 1]
            cur_in = cur[axis] >= limit if keep_above else cur[axis] <= limit
            prev_in = prev[axis] >= limit if keep_above else prev[axis] <= limit
            if cur_in != prev_in:
                t = (limit - prev[axis]) / (cur[axis] - prev[axis])
                out.append((prev[0] + (cur[0] - prev[0]) * t, prev[1] + (cur[1] - prev[1]) * t))
            if cur_in:
                out.append(cur)
        poly = out
    if len(poly) < 3:
        return 0.0
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, [*poly[1:], poly[0]]))) / 2


def _axes(hull: np.ndarray) -> np.ndarray:
    """The axes that can separate a level rectangle from ``hull``: x, y and its edge normals."""
    edges = np.roll(hull, -1, axis=0) - hull
    normals = np.stack([-edges[:, 1], edges[:, 0]], axis=1)
    lengths = np.linalg.norm(normals, axis=1)
    normals = normals[lengths > 1e-12] / lengths[lengths > 1e-12, None]
    return np.vstack([[[1.0, 0.0], [0.0, 1.0]], normals])


def slide_out(size: Sequence[float], start: Sequence[float], direction: Sequence[float], hull: np.ndarray, gap: float = 0.0) -> np.ndarray:
    """The centre nearest ``start`` along ``direction`` (from ``start`` on) at which a rectangle
    of ``size`` keeps ``gap`` off the convex ``hull`` (exact: per separating axis, the first
    moment the two projections part)."""
    s = np.asarray(start, dtype=float)
    d = np.asarray(direction, dtype=float)
    d = d / max(float(np.linalg.norm(d)), 1e-12)
    if len(hull) == 0:
        return s
    axes = _axes(hull) if len(hull) >= 3 else np.array([[1.0, 0.0], [0.0, 1.0]])
    best = math.inf
    w, h = size[0] / 2 + gap, size[1] / 2 + gap
    for a in axes:
        projected = hull @ a
        lo, hi = float(projected.min()), float(projected.max())
        reach = abs(a[0]) * w + abs(a[1]) * h
        c, v = float(s @ a), float(d @ a)
        if c - reach >= hi or c + reach <= lo:
            return s   # apart already
        if v > 1e-12:
            best = min(best, (hi + reach - c) / v)
        elif v < -1e-12:
            best = min(best, (lo - reach - c) / v)
    return s + d * (best if math.isfinite(best) else 0.0)


def ray_exit(hull: np.ndarray, origin: Sequence[float], toward: Sequence[float]) -> np.ndarray:
    """Where the ray from ``origin`` (inside ``hull``) toward ``toward`` leaves the convex ``hull``."""
    o = np.asarray(origin, dtype=float)
    d = np.asarray(toward, dtype=float) - o
    if len(hull) < 3 or float(np.linalg.norm(d)) < 1e-12:
        return o
    best = math.inf
    for a, b in zip(hull, np.roll(hull, -1, axis=0)):
        normal = np.array([b[1] - a[1], -(b[0] - a[0])])   # outward for a counter-clockwise hull
        v = float(d @ normal)
        if v > 1e-12:
            best = min(best, float((a - o) @ normal) / v)
    return o + d * (best if math.isfinite(best) else 0.0)


def rect_exit(rect: Rect, toward: Sequence[float]) -> np.ndarray:
    """Where the ray from ``rect``'s centre toward ``toward`` leaves it."""
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    w, h = (rect[2] - rect[0]) / 2, (rect[3] - rect[1]) / 2
    t = min(w / abs(dx) if abs(dx) > 1e-12 else math.inf, h / abs(dy) if abs(dy) > 1e-12 else math.inf, 1.0)
    return np.array([cx + dx * t, cy + dy * t])


def hull_gap(rect: Rect, hull: np.ndarray) -> float:
    """How far ``rect`` is from the convex ``hull`` (0 when they touch or overlap)."""
    if len(hull) == 0:
        return math.inf
    best = 0.0
    axes = _axes(hull) if len(hull) >= 3 else np.array([[1.0, 0.0], [0.0, 1.0]])
    corners = np.array([[rect[0], rect[1]], [rect[2], rect[1]], [rect[2], rect[3]], [rect[0], rect[3]]])
    for a in axes:   # the largest separation along an axis: exact for the axes, a lower bound otherwise
        p, q = hull @ a, corners @ a
        best = max(best, float(q.min() - p.max()), float(p.min() - q.max()))
    return max(best, 0.0)


def polyline_gap(rect: Rect, points: np.ndarray) -> float:
    """How far ``rect`` is from the polyline ``points`` (sampled densely enough)."""
    if len(points) == 0:
        return math.inf
    dx = np.maximum(np.maximum(rect[0] - points[:, 0], points[:, 0] - rect[2]), 0.0)
    dy = np.maximum(np.maximum(rect[1] - points[:, 1], points[:, 1] - rect[3]), 0.0)
    return float(np.min(np.hypot(dx, dy)))


@dataclass
class Obstacles:
    """What labels keep clear of at one scale: the outlines of blocks and pipes (``hulls`` by
    name; a pipe segment's ``<connector ref>#<k>``), connectors (``lines``: sample points by
    connector ref) and the labels placed so far (``taken``). A label keeps ``clearance`` off the
    outlines too: one that nearly touches another block reads as that block's."""

    hulls: Mapping[str, np.ndarray]
    lines: Mapping[str, np.ndarray] = field(default_factory=dict)
    taken: list[Rect] = field(default_factory=list)
    clearance: float = 0.0

    def cost(self, rect: Rect, skip: Iterable[str] = ()) -> float:
        """What a label at ``rect`` covers (:data:`LABEL_WEIGHT`, :data:`BLOCK_WEIGHT`,
        :data:`LINE_COST`); blocks and connectors named in ``skip`` do not count."""
        skipped = set(skip)
        c = self.clearance
        spaced = (rect[0] - c, rect[1] - c, rect[2] + c, rect[3] + c)   # labels apart, so each reads as its own
        total = LABEL_WEIGHT * sum(overlap_area(spaced, other) for other in self.taken)
        near = (rect[0] - c, rect[1] - c, rect[2] + c, rect[3] + c)
        for name, hull in self.hulls.items():
            if name in skipped or name.split("#")[0] in skipped:
                continue
            covered = clip_area(rect, hull)
            total += BLOCK_WEIGHT * (covered + NEAR_WEIGHT * (clip_area(near, hull) - covered if c > 0 else 0.0))
        for ref, points in self.lines.items():
            if ref in skipped or not len(points):
                continue
            inside = (points[:, 0] >= rect[0]) & (points[:, 0] <= rect[2]) & (points[:, 1] >= rect[1]) & (points[:, 1] <= rect[3])
            total += LINE_COST * int(np.count_nonzero(inside))
        return total

    def clear_of_all(self, size: Sequence[float], start: Sequence[float], direction: Sequence[float], gap: float, rounds: int = 4) -> np.ndarray:
        """The centre along ``direction`` from ``start`` at which a rectangle of ``size`` clears
        every block it met on the way (pushed past each in turn)."""
        centre = np.asarray(start, dtype=float)
        gap = max(gap, self.clearance)
        for _ in range(rounds):
            rect = rect_of(centre, size)
            hits = [hull for hull in self.hulls.values() if clip_area(rect_of(centre, (size[0] + 2 * gap, size[1] + 2 * gap)), hull) > 1e-9]
            hits += [hull_of_rect(r) for r in self.taken if overlap_area(rect, r) > 1e-9]
            if not hits:
                break
            centre = max((slide_out(size, centre, direction, hull, gap) for hull in hits), key=lambda c: float((c - centre) @ np.asarray(direction)))
        return centre


def hull_of_rect(rect: Rect) -> np.ndarray:
    """``rect`` as a convex outline (counter-clockwise)."""
    return np.array([[rect[0], rect[1]], [rect[2], rect[1]], [rect[2], rect[3]], [rect[0], rect[3]]], dtype=float)


def hull_of_point(point: Sequence[float], radius: float = 1e-3) -> np.ndarray:
    """A tiny outline round ``point`` (what a label on a connector points at)."""
    x, y = float(point[0]), float(point[1])
    return hull_of_rect((x - radius, y - radius, x + radius, y + radius))


#: Directions a label beside a block is tried in: up, down, right, left, then the diagonals.
AROUND = ((0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0), (1.0, 1.0), (-1.0, 1.0), (1.0, -1.0), (-1.0, -1.0))


__all__ = [
    "AROUND",
    "BLOCK_WEIGHT",
    "FAR_COST",
    "LABEL_WEIGHT",
    "LINE_COST",
    "NEAR_WEIGHT",
    "Obstacles",
    "Rect",
    "clip_area",
    "convex_hull",
    "hull_box",
    "hull_gap",
    "hull_of_point",
    "hull_of_rect",
    "overlap_area",
    "polyline_gap",
    "ray_exit",
    "rect_exit",
    "rect_of",
    "slide_out",
    "rect_union",
]
