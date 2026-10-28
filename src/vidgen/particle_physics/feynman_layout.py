"""Where the vertices and lines of a Feynman diagram go (Phase Y, Step 238; DESIGN §99.5). No
manim; deterministic.

Coordinates: ``t`` is time (0: the incoming legs' ends, 1: the outgoing legs' ends) and ``y``
the transverse direction (incoming and outgoing ends spread over −1 … 1, spectator quarks above);
the scene maps them onto the screen, time left → right or bottom → top.

1. **Time order of the vertices.** Cutting an internal line that is a bridge splits the
   diagram in two; if one part holds no incoming leg (or the other no outgoing one) the line is
   *timelike* (an s-channel propagator, a W carried off to its decay vertex) and orders its
   vertices; otherwise it is *spacelike* (a t- or u-channel exchange) and its vertices share a
   time. On a loop, a vertex whose outside part holds only incoming legs is early, only outgoing
   legs late; loop lines between early and late vertices are timelike. Vertices joined by
   spacelike lines form a column; the columns are layered by the longest path.
2. **Transverse positions.** The incoming ends are spread on the left edge and the outgoing on the
   right in some order; each vertex sits at the weighted mean of its neighbours (a barycentric
   embedding, solved exactly), vertices sharing a column kept apart.
3. **Order of the ends.** Every order of the incoming and of the outgoing ends is tried (up to
   four per side; more keep the written order and its reverse) and the layout with the fewest
   line crossings wins (a line through a vertex dot counts as one), then the one keeping each
   hadron's quarks together beside its spectators, then the one closest to the written order. A
   u-channel diagram therefore comes out uncrossed, its outgoing legs swapped.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np

from .feynman import IN, OUT, Diagram, DiagramLine

Point = tuple[float, float]
#: Space between spectator quark lines (in y), and the least distance between two vertices of
#: one column.
SPECTATOR_GAP = 0.42
COLUMN_GAP = 1.0
#: Most ends per side whose orders are all tried.
MAX_PERMUTED = 4
#: Sagitta of the arcs of two lines joining the same two vertices (a fraction of their chord).
ARC_BEND = 0.32


@dataclass(frozen=True)
class LineGeometry:
    """A line's ends (``start`` → ``end`` as the diagram gives them) and its bend (0: straight;
    else the arc's sagitta over the chord, positive to the left of start → end)."""

    id: str
    start: Point
    end: Point
    bend: float = 0.0

    def point(self, s: float) -> Point:
        """The point at fraction ``s`` along the line from ``start``."""
        (x0, y0), (x1, y1) = self.start, self.end
        x, y = x0 + (x1 - x0) * s, y0 + (y1 - y0) * s
        if self.bend:
            # a parabola through the ends with the sagitta at the middle (close to an arc)
            h = 4 * self.bend * s * (1 - s)
            x, y = x - (y1 - y0) * h, y + (x1 - x0) * h
        return (x, y)

    def polyline(self, n: int = 12) -> list[Point]:
        if not self.bend:
            return [self.start, self.end]
        return [self.point(k / n) for k in range(n + 1)]


@dataclass(frozen=True)
class DiagramLayout:
    """Positions of a diagram: ``vertices`` (t, y), the lines' geometry, each vertex's column,
    which internal lines are timelike, the hadron groups' brackets ``(index, side, y_low,
    y_high)``, the number of crossings left (0 for every preset) and the bounds ``(t0, y0, t1,
    y1)``."""

    vertices: dict[str, Point]
    lines: dict[str, LineGeometry]
    columns: dict[str, int]
    timelike: dict[str, bool]
    groups: tuple[tuple[int, str, float, float], ...]
    crossings: int
    bounds: tuple[float, float, float, float]

    def times(self, line_id: str) -> tuple[float, float]:
        """The times at which a line begins and ends (earlier first)."""
        g = self.lines[line_id]
        return (min(g.start[0], g.end[0]), max(g.start[0], g.end[0]))


# ----- time order -----------------------------------------------------------------------------------


def _components(vertices: tuple[str, ...], edges: list[tuple[str, str]]) -> list[set[str]]:
    adjacency: dict[str, set[str]] = {v: set() for v in vertices}
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen: set[str] = set()
    parts = []
    for v in vertices:
        if v in seen:
            continue
        part, todo = {v}, [v]
        while todo:
            for n in adjacency[todo.pop()]:
                if n not in part:
                    part.add(n)
                    todo.append(n)
        seen |= part
        parts.append(part)
    return parts


def _legs(d: Diagram, part: set[str]) -> tuple[int, int]:
    """Incoming and outgoing external legs attached to the vertices in ``part``."""
    return (sum(1 for ln in d.initial if ln.end in part), sum(1 for ln in d.final if ln.start in part))


def _orientation(d: Diagram) -> dict[str, int]:
    """For each internal line: +1 (start before end), −1 (end before start), 0 (spacelike)."""
    vertices = d.vertices
    internal = list(d.internal)
    edges = [(ln.start, ln.end) for ln in internal]
    out: dict[str, int] = {}
    bridges: dict[str, tuple[set[str], set[str]]] = {}
    for k, ln in enumerate(internal):
        parts = _components(vertices, edges[:k] + edges[k + 1:])
        if len(parts) == 2:
            a = next(p for p in parts if ln.start in p)
            b = next(p for p in parts if ln.end in p)
            bridges[ln.id] = (a, b)
    for ln in internal:
        if ln.id not in bridges:
            continue
        a, b = bridges[ln.id]
        (ia, oa), (ib, ob) = _legs(d, a), _legs(d, b)
        forward, backward = ib == 0 or oa == 0, ia == 0 or ob == 0
        out[ln.id] = 1 if forward and not backward else (-1 if backward and not forward else 0)
    loop = [ln for ln in internal if ln.id not in bridges]
    if loop:
        tree_edges = [(ln.start, ln.end) for ln in internal if ln.id in bridges]
        parts = _components(vertices, tree_edges)
        cls: dict[str, int] = {}
        for v in {x for ln in loop for x in ln.ends()}:
            part = next(p for p in parts if v in p)
            i, o = _legs(d, part)
            cls[v] = 0 if i and not o else (2 if o and not i else 1)
        for ln in loop:
            a, b = cls[ln.start], cls[ln.end]
            out[ln.id] = (a < b) - (a > b)
    return out


def _columns(d: Diagram, orient: dict[str, int]) -> dict[str, int]:
    vertices = d.vertices
    parent = {v: v for v in vertices}

    def find(v: str) -> str:
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for ln in d.internal:
        if orient[ln.id] == 0:
            ra, rb = find(ln.start), find(ln.end)
            if ra != rb:
                parent[max(ra, rb, key=vertices.index)] = min(ra, rb, key=vertices.index)
    before: dict[str, set[str]] = {find(v): set() for v in vertices}
    for ln in d.internal:
        if orient[ln.id]:
            early, late = (ln.start, ln.end) if orient[ln.id] > 0 else (ln.end, ln.start)
            if find(early) != find(late):
                before[find(late)].add(find(early))
    layer: dict[str, int] = {}

    def depth(g: str, path: tuple[str, ...]) -> int:
        if g in layer:
            return layer[g]
        if g in path:   # contradictory order: give up on it
            return 0
        layer[g] = 1 + max((depth(e, (*path, g)) for e in before[g]), default=-1)
        return layer[g]

    for g in before:
        depth(g, ())
    used = sorted(set(layer.values()))
    return {v: used.index(layer[find(v)]) for v in vertices}


def _column_x(columns: dict[str, int]) -> dict[int, float]:
    count = max(columns.values()) + 1
    if count == 1:
        return {0: 0.5}
    span = {2: 0.38, 3: 0.52, 4: 0.6}.get(count, 0.66)
    return {c: 0.5 - span / 2 + c * span / (count - 1) for c in range(count)}


# ----- transverse positions ---------------------------------------------------------------------------


def _slots(n: int, grouped_top: bool) -> list[float]:
    if n == 1:
        return [1.0 if grouped_top else 0.0]
    return [1.0 - 2.0 * k / (n - 1) for k in range(n)]


def _solve(d: Diagram, ends: dict[str, Point], columns: dict[str, int], xs: dict[int, float]) -> dict[str, Point]:
    """Vertex y as the mean of its neighbours' (external ends fixed), then pushed apart within a
    column."""
    vertices = list(d.vertices)
    index = {v: i for i, v in enumerate(vertices)}
    n = len(vertices)
    a = np.zeros((n, n))
    b = np.zeros(n)
    for ln in d.lines:
        if ln.spectator:
            continue
        if ln.internal:
            i, j = index[ln.start], index[ln.end]
            a[i, i] += 1
            a[j, j] += 1
            a[i, j] -= 1
            a[j, i] -= 1
        else:
            v = ln.end if ln.incoming else ln.start
            a[index[v], index[v]] += 1
            b[index[v]] += ends[ln.id][1]
    y = np.linalg.solve(a, b)
    pos = {v: (xs[columns[v]], float(y[index[v]])) for v in vertices}
    for c in set(columns.values()):
        members = sorted((v for v in vertices if columns[v] == c), key=lambda v: (-pos[v][1], vertices.index(v)))
        if len(members) < 2:
            continue
        ys = [pos[v][1] for v in members]
        for k in range(1, len(ys)):
            ys[k] = min(ys[k], ys[k - 1] - COLUMN_GAP)
        shift = (sum(pos[v][1] for v in members) - sum(ys)) / len(ys)
        for v, yv in zip(members, ys):
            pos[v] = (pos[v][0], yv + shift)
    return pos


def _geometry(d: Diagram, pos: dict[str, Point], ends: dict[str, Point]) -> dict[str, LineGeometry]:
    out: dict[str, LineGeometry] = {}
    pairs: dict[frozenset[str], list[DiagramLine]] = {}
    for ln in d.internal:
        pairs.setdefault(frozenset(ln.ends()), []).append(ln)
    for ln in d.lines:
        if ln.spectator:
            out[ln.id] = LineGeometry(ln.id, (0.0, ends[ln.id][1]), (1.0, ends[ln.id][1]))
        elif ln.incoming:
            out[ln.id] = LineGeometry(ln.id, ends[ln.id], pos[ln.end])
        elif ln.outgoing:
            out[ln.id] = LineGeometry(ln.id, pos[ln.start], ends[ln.id])
        else:
            group = pairs[frozenset(ln.ends())]
            bend = 0.0
            if len(group) > 1:
                k = group.index(ln)
                spread = [ARC_BEND * (1 - 2 * j / (len(group) - 1)) for j in range(len(group))]
                # the same side whichever way the line is written
                first = group[0]
                bend = spread[k] * (1 if (ln.start, ln.end) == (first.start, first.end) else -1)
            out[ln.id] = LineGeometry(ln.id, pos[ln.start], pos[ln.end], bend)
    return out


# ----- crossings ------------------------------------------------------------------------------------

#: Time is stretched by this when measuring distances (the screen is wider than the y range).
_ASPECT = 2.0


def _cross(p: Point, q: Point, r: Point, s: Point) -> bool:
    def orient(a: Point, b: Point, c: Point) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2, d3, d4 = orient(r, s, p), orient(r, s, q), orient(p, q, r), orient(p, q, s)
    return ((d1 > 1e-9 and d2 < -1e-9) or (d1 < -1e-9 and d2 > 1e-9)) and ((d3 > 1e-9 and d4 < -1e-9) or (d3 < -1e-9 and d4 > 1e-9))


def _near(p: Point, a: Point, b: Point, limit: float) -> bool:
    ax, ay, bx, by, px, py = a[0] * _ASPECT, a[1], b[0] * _ASPECT, b[1], p[0] * _ASPECT, p[1]
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    s = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(ax + s * dx - px, ay + s * dy - py) < limit


def count_crossings(d: Diagram, geometry: dict[str, LineGeometry], pos: dict[str, Point]) -> int:
    """Pairs of lines that cross (lines sharing a vertex excepted), plus lines that pass through
    a vertex dot they do not end at."""
    ids = [ln.id for ln in d.lines]
    ends = {ln.id: set(ln.ends()) - {IN, OUT} for ln in d.lines}
    polys = {i: geometry[i].polyline() for i in ids}
    total = 0
    for a_i, b_i in itertools.combinations(ids, 2):
        if ends[a_i] & ends[b_i]:
            continue
        pa, pb = polys[a_i], polys[b_i]
        if any(_cross(pa[k], pa[k + 1], pb[m], pb[m + 1]) for k in range(len(pa) - 1) for m in range(len(pb) - 1)):
            total += 1
    for v, p in pos.items():
        for i in ids:
            if v in ends[i]:
                continue
            poly = polys[i]
            if any(_near(p, poly[k], poly[k + 1], 0.12) for k in range(len(poly) - 1)):
                total += 1
    return total


# ----- the layout -----------------------------------------------------------------------------------


def _orders(legs: list[DiagramLine]) -> list[tuple[DiagramLine, ...]]:
    if len(legs) <= MAX_PERMUTED:
        return list(itertools.permutations(legs))
    return [tuple(legs), tuple(reversed(legs))]


def _inversions(order: tuple[DiagramLine, ...], written: list[DiagramLine]) -> int:
    rank = [written.index(ln) for ln in order]
    return sum(1 for i, j in itertools.combinations(range(len(rank)), 2) if rank[i] > rank[j])


def layout(d: Diagram) -> DiagramLayout:
    """The layout of ``d`` (see the module docstring)."""
    orient = _orientation(d)
    columns = _columns(d, orient)
    xs = _column_x(columns)
    initial, final = list(d.initial), list(d.final)
    spectators = list(d.spectators)
    grouped = {side: {i for g in d.groups if g.side == side for i in g.lines} for side in ("initial", "final")}
    best: tuple[tuple[int, int, int], dict[str, Point], dict[str, Point], dict[str, LineGeometry]] | None = None
    for order_in in _orders(initial):
        for order_out in _orders(final):
            ends: dict[str, Point] = {}
            for order, t, side in ((order_in, 0.0, "initial"), (order_out, 1.0, "final")):
                top = bool(grouped[side]) and order[0].id in grouped[side]
                for ln, y in zip(order, _slots(len(order), top)):
                    ends[ln.id] = (t, y)
            for k, ln in enumerate(spectators, start=1):
                ends[ln.id] = (0.0, 1.0 + SPECTATOR_GAP * k)
            pos = _solve(d, ends, columns, xs)
            geometry = _geometry(d, pos, ends)
            crossings = count_crossings(d, geometry, pos)
            apart = 0
            for order, side in ((order_in, "initial"), (order_out, "final")):
                members = [k for k, ln in enumerate(order) if ln.id in grouped[side]]
                apart += sum(1 for k in range(len(order)) if members and k < max(members) and order[k].id not in grouped[side])
            score = (crossings, apart, _inversions(order_in, initial) + _inversions(order_out, final))
            if best is None or score < best[0]:
                best = (score, pos, ends, geometry)
    assert best is not None
    score, pos, ends, geometry = best
    groups = []
    for k, g in enumerate(d.groups):
        ys = [ends[i][1] for i in g.lines]
        groups.append((k, g.side, min(ys), max(ys)))
    points = [p for geo in geometry.values() for p in geo.polyline()]
    bounds = (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points))
    timelike = {ln.id: orient[ln.id] != 0 for ln in d.internal}
    return DiagramLayout(pos, geometry, columns, timelike, tuple(groups), score[0], bounds)


__all__ = ["ARC_BEND", "DiagramLayout", "LineGeometry", "count_crossings", "layout"]
