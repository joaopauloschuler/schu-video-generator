"""The isometric view (DESIGN.md §89.3): world points to the picture and the draw order of boxes.
Plain math, no manim and no drawing, so a stage and a later presentation diagram can share it.

The world is in tile units (``x`` to the viewer's lower right, ``y`` to the lower left, ``z``
up). The picture is in *tile widths* (a cell's diamond is 1 wide and 1/2 high): ``u`` to the
right, ``v`` down. One tile unit up is :data:`ISO_RISE` tile widths on the picture: a true
isometric view tilted so that a cell's diamond is twice as wide as it is high (the 2:1 view of
pixel-art games), with no perspective: things keep their size wherever they stand.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Sequence
from dataclasses import dataclass

#: How far one tile unit up rises on the picture, in tile widths: the view looks down at 30°,
#: from halfway between the ``x`` and the ``y`` axis, scaled so a cell's diamond is 1 wide.
ISO_RISE = math.sqrt(1.5) / 2
#: Boxes closer than this (tile units) count as touching, not overlapping.
_TOUCH = 1e-6
#: Boxes whose pictures come this close (tile widths) are ordered too: a drawing may reach a
#: little past its box (a tree's crown, an outline).
PICTURE_SLACK = 0.35

Point3 = tuple[float, float, float]


def iso_point(x: float, y: float, z: float = 0.0) -> tuple[float, float]:
    """A world point on the picture: ``(u, v)`` in tile widths, ``v`` down."""
    return ((x - y) / 2, (x + y) / 4 - z * ISO_RISE)


def iso_depth(x: float, y: float, z: float = 0.0) -> float:
    """How near the viewer a world point is (larger: nearer); for ordering points, not boxes."""
    return x + y + z * 0.01


@dataclass(frozen=True)
class Box3:
    """An upright box in the world, ``x0 .. x1`` by ``y0 .. y1`` by ``z0 .. z1`` (tile units):
    what a block, a wall, an object or a character stands in, for the draw order."""

    x0: float
    y0: float
    z0: float
    x1: float
    y1: float
    z1: float

    def corners(self) -> list[Point3]:
        return [(x, y, z) for x in (self.x0, self.x1) for y in (self.y0, self.y1) for z in (self.z0, self.z1)]

    def picture_bounds(self) -> tuple[float, float, float, float]:
        """``(left, top, right, bottom)`` of the box on the picture (tile widths, ``v`` down)."""
        points = [iso_point(*corner) for corner in self.corners()]
        us, vs = [p[0] for p in points], [p[1] for p in points]
        return min(us), min(vs), max(us), max(vs)


def in_front(a: Box3, b: Box3) -> bool | None:
    """Whether ``a`` is drawn after ``b`` (it hides ``b`` where they overlap on the picture):
    ``True`` or ``False``; ``None`` when their pictures are apart (by :data:`PICTURE_SLACK`), or
    side by side (apart along ``x`` one way and along ``y`` the other). Boxes apart along an axis
    are ordered by it (a plane between them has the viewer on the nearer one's side: larger ``x``,
    larger ``y`` or higher ``z``); overlapping boxes (which the rules never make) by their middles."""
    la, ta, ra, ba = a.picture_bounds()
    lb, tb, rb, bb = b.picture_bounds()
    if ra + PICTURE_SLACK <= lb or rb + PICTURE_SLACK <= la or ba + PICTURE_SLACK <= tb or bb + PICTURE_SLACK <= ta:
        return None
    apart = [_apart(a.x0, a.x1, b.x0, b.x1), _apart(a.y0, a.y1, b.y0, b.y1), _apart(a.z0, a.z1, b.z0, b.z1)]
    if apart[0] is not None and apart[1] is not None and apart[0] != apart[1]:
        return None   # side by side on the picture (one to the right, the other to the left): no order
    for found in apart:
        if found is not None:
            return found
    middle_a = iso_depth((a.x0 + a.x1) / 2, (a.y0 + a.y1) / 2, (a.z0 + a.z1) / 2)
    return middle_a > iso_depth((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, (b.z0 + b.z1) / 2)


def _apart(a0: float, a1: float, b0: float, b1: float) -> bool | None:
    """Along one axis: ``True`` when ``a`` lies beyond ``b`` (nearer the viewer), ``False`` when
    before it, ``None`` when they overlap."""
    if a0 >= b1 - _TOUCH:
        return True
    if b0 >= a1 - _TOUCH:
        return False
    return None


def draw_order(boxes: Sequence[Box3]) -> list[int]:
    """The indices of ``boxes`` back to front: each box after every box it hides
    (:func:`in_front`). Deterministic: among boxes free to go next, the one furthest back (by its
    back corner), then the lower, then the first given."""
    count = len(boxes)
    after: list[list[int]] = [[] for _ in range(count)]
    waiting = [0] * count
    for i in range(count):
        for j in range(i + 1, count):
            order = in_front(boxes[i], boxes[j])
            if order is None:
                continue
            back, front = (j, i) if order else (i, j)
            after[back].append(front)
            waiting[front] += 1

    def key(k: int) -> tuple[float, float, int]:
        box = boxes[k]
        return (box.x0 + box.y0, box.z0, k)

    ready = [key(k) for k in range(count) if waiting[k] == 0]
    heapq.heapify(ready)
    done: list[int] = []
    placed = [False] * count
    while len(done) < count:
        if not ready:   # a cycle (overlapping boxes): the furthest back of the rest goes next
            ready = [min(key(k) for k in range(count) if not placed[k])]
        k = heapq.heappop(ready)[-1]
        if placed[k]:
            continue
        placed[k] = True
        done.append(k)
        for front in after[k]:
            waiting[front] -= 1
            if waiting[front] == 0 and not placed[front]:
                heapq.heappush(ready, key(front))
    return done


__all__ = ["ISO_RISE", "PICTURE_SLACK", "Box3", "Point3", "draw_order", "in_front", "iso_depth", "iso_point"]
