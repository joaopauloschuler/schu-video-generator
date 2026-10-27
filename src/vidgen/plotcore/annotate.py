"""Placing text on a plot without covering data or other text, deterministically: every piece of
text (a point label, a reference line's name, a fit's parameters, a note) chooses among
candidate boxes the one that covers the fewest data points (markers and samples along lines),
overlaps the fewest boxes placed before it and stays inside the plot; ties go to the candidate
listed first. No randomness: the same inputs give the same places."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .figure import Rect

#: Directions around a point a label tries, in order of preference: above right, above left,
#: below right, below left, above, below, right, left.
DIRECTIONS = ((1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1), (0, -1), (1, 0), (-1, 0))
#: Places in a plot a box tries (``place_in_plot``), in order of preference.
SPOTS = ("top_left", "top_right", "bottom_right", "bottom_left", "top", "bottom", "left", "right")


@dataclass(frozen=True)
class Placement:
    """Where a box went: its ``box``, the index of the candidate chosen, its ``cost`` (0: it
    covers nothing) and ``leader`` (true when it stands off its anchor: draw a line to it)."""

    box: Rect
    index: int
    cost: float
    leader: bool = False


def as_points(points: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    """Frame points as an ``(n, 2)`` array (extra columns and ``nan`` rows dropped)."""
    p = np.asarray(points, dtype=float)
    if p.size == 0:
        return np.zeros((0, 2))
    p = p.reshape(len(p), -1)[:, :2]
    return p[np.isfinite(p).all(axis=1)]


def overlap(a: Rect, b: Rect) -> float:
    """The area two boxes share."""
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return w * h if w > 0 and h > 0 else 0.0


def grow(box: Rect, pad: float) -> Rect:
    """``box`` with ``pad`` added on every side."""
    return Rect(box.x0 - pad, box.y0 - pad, box.x1 + pad, box.y1 + pad)


def covered(box: Rect, points: np.ndarray) -> int:
    """How many of the frame ``points`` (``(n, 2+)``) lie in ``box``."""
    if not len(points):
        return 0
    p = np.asarray(points, dtype=float)
    inside = (p[:, 0] >= box.x0) & (p[:, 0] <= box.x1) & (p[:, 1] >= box.y0) & (p[:, 1] <= box.y1)
    return int(np.count_nonzero(inside))


def box_cost(box: Rect, plot: Rect, points: np.ndarray, taken: Sequence[Rect], pad: float = 0.06) -> float:
    """What a box costs: the part of it outside ``plot`` (heavily), the data points it covers
    (with ``pad`` of air), and its overlap with ``taken`` boxes (text over text is worse than
    text over a few data points: a fixed price per box touched plus its area)."""
    outside = box.width * box.height - overlap(box, plot)
    cost = 1000.0 * max(outside, 0.0)
    cost += 10.0 * covered(grow(box, pad), points)
    for t in taken:
        shared = overlap(grow(box, pad), t)
        if shared > 0:
            cost += 1000.0 + 5000.0 * shared
    return cost


def best_box(candidates: Sequence[Rect], plot: Rect, points: np.ndarray, taken: Sequence[Rect], *, pad: float = 0.06, order_weight: float = 0.01) -> Placement:
    """The cheapest of ``candidates`` (:func:`box_cost`, plus ``order_weight`` per place in the
    list so earlier candidates win ties)."""
    if not candidates:
        raise ValueError("best_box needs candidates")
    pts = as_points(points)
    costs = [box_cost(c, plot, pts, taken, pad) + order_weight * i for i, c in enumerate(candidates)]
    i = int(np.argmin(costs))
    return Placement(candidates[i], i, costs[i] - order_weight * i)


def box_at(cx: float, cy: float, size: tuple[float, float]) -> Rect:
    """A box of ``size`` centred at ``(cx, cy)``."""
    w, h = size
    return Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def place_near(
    anchor: tuple[float, float],
    size: tuple[float, float],
    plot: Rect,
    points: np.ndarray,
    taken: Sequence[Rect],
    *,
    gap: float = 0.12,
    steps: Sequence[float] = (1.0, 2.2, 3.6),
) -> Placement:
    """A label of ``size`` next to the ``anchor`` point: tried in the :data:`DIRECTIONS` at
    ``gap`` × each of ``steps`` from the point (the near ring first); a label off the first
    ring gets a ``leader``. The anchor's own point does not count as covered."""
    w, h = size
    ax, ay = anchor
    candidates = []
    for k, step in enumerate(steps):
        d = gap * step + (0.0 if k == 0 else 0.25 * (k))
        for dx, dy in DIRECTIONS:
            cx = ax + dx * (w / 2 + d) if dx else ax
            cy = ay + dy * (h / 2 + d) if dy else ay
            candidates.append(box_at(cx, cy, size))
    pts = as_points(points)
    if len(pts):
        far = np.hypot(pts[:, 0] - ax, pts[:, 1] - ay) > 1e-6
        pts = pts[far]
    placed = best_box(candidates, plot, pts, taken)
    return Placement(placed.box, placed.index, placed.cost, placed.index >= len(DIRECTIONS))


def place_in_plot(size: tuple[float, float], plot: Rect, points: np.ndarray, taken: Sequence[Rect], *, pad: float = 0.15, spots: Sequence[str] = SPOTS) -> Placement:
    """A box of ``size`` inside ``plot`` (``pad`` from its edges) at the cheapest of ``spots``
    (corners, then edge middles)."""
    w, h = size
    left, right = plot.x0 + pad + w / 2, plot.x1 - pad - w / 2
    bottom, top = plot.y0 + pad + h / 2, plot.y1 - pad - h / 2
    mx, my = plot.center
    where = {
        "top_left": (left, top), "top_right": (right, top), "bottom_right": (right, bottom), "bottom_left": (left, bottom),
        "top": (mx, top), "bottom": (mx, bottom), "left": (left, my), "right": (right, my),
    }
    return best_box([box_at(*where[s], size) for s in spots], plot, points, taken)


def place_on_hline(y: float, size: tuple[float, float], plot: Rect, points: np.ndarray, taken: Sequence[Rect], *, gap: float = 0.08, pad: float = 0.12) -> Placement:
    """The name of a horizontal reference line at frame ``y``: just above or below it, at the
    plot's right end, left end or middle."""
    w, h = size
    xs = (plot.x1 - pad - w / 2, plot.x0 + pad + w / 2, plot.center[0])
    candidates = [box_at(x, y + s * (gap + h / 2), size) for s in (1, -1) for x in xs]
    return best_box(candidates, plot, points, taken)


def place_on_vline(x: float, size: tuple[float, float], plot: Rect, points: np.ndarray, taken: Sequence[Rect], *, gap: float = 0.1, pad: float = 0.12) -> Placement:
    """The name of a vertical reference line at frame ``x``: right or left of it, at the top,
    the bottom or the middle of the plot."""
    w, h = size
    ys = (plot.y1 - pad - h / 2, plot.y0 + pad + h / 2, plot.center[1])
    candidates = [box_at(x + s * (gap + w / 2), y, size) for y in ys for s in (1, -1)]
    return best_box(candidates, plot, points, taken)


def place_in_span(x0: float, x1: float, size: tuple[float, float], plot: Rect, points: np.ndarray, taken: Sequence[Rect], *, vertical: bool = True, pad: float = 0.12) -> Placement:
    """The name of a shaded range (``x0..x1`` across x when ``vertical``, else ``y0..y1`` across
    y): inside it at the top / bottom (left / right), else beside it."""
    w, h = size
    if vertical:
        cx = (x0 + x1) / 2
        candidates = [box_at(cx, plot.y1 - pad - h / 2, size), box_at(cx, plot.y0 + pad + h / 2, size),
                      box_at(x1 + 0.1 + w / 2, plot.y1 - pad - h / 2, size), box_at(x0 - 0.1 - w / 2, plot.y1 - pad - h / 2, size)]
    else:
        cy = (x0 + x1) / 2
        candidates = [box_at(plot.x1 - pad - w / 2, cy, size), box_at(plot.x0 + pad + w / 2, cy, size),
                      box_at(plot.x1 - pad - w / 2, x1 + 0.08 + h / 2, size), box_at(plot.x1 - pad - w / 2, x0 - 0.08 - h / 2, size)]
    return best_box(candidates, plot, points, taken)


__all__ = [
    "DIRECTIONS",
    "SPOTS",
    "Placement",
    "as_points",
    "best_box",
    "box_at",
    "box_cost",
    "covered",
    "grow",
    "overlap",
    "place_in_plot",
    "place_in_span",
    "place_near",
    "place_on_hline",
    "place_on_vline",
]
