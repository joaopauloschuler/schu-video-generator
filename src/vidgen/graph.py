"""Layered (Sugiyama-style) layout of directed graphs, in pure Python (exported by ``vidgen.api``).

:func:`layered_layout` places the nodes of a directed graph in layers along a main direction
(``LR``: left to right, ``TB``: top to bottom) so that edges point forward, orders each layer to
reduce edge crossings and routes every edge as a polyline that starts and ends on the nodes'
outlines. The phases are the classic ones:

1. **Cycles**: a depth-first search in input order marks back edges; they are laid out reversed
   (and routed back to their real direction), so a cycle reads as one backward edge.
2. **Layers**: longest path from the sources; a source is then pulled up to just before its
   nearest successor. An edge spanning several layers gets an invisible "dummy" node per layer.
3. **Order**: barycenter sweeps down and up the layers (ties keep the current order), the best
   order seen is kept, then adjacent swaps that remove crossings ("transpose").
4. **Coordinates**: layers are spaced by the deepest node in them plus ``layer_gap`` (more
   where an edge label needs room); across a layer, nodes are pulled towards the mean of their
   neighbours while keeping ``node_gap`` apart (an exact weighted isotonic fit per layer).
5. **Routes**: ports spread along the facing sides (sorted by where the edge goes, so edges do
   not cross at a node), clipped to the node's shape (box, ellipse, diamond, stadium);
   ``straight`` polylines through the dummy positions, or ``orthogonal`` runs with a channel per
   edge in each gap.

Everything is deterministic (no randomness, ties broken by input order) and manim-free. Units
are whatever the node sizes are in (Manim units in scenes); the result is centred on the origin
with y pointing up.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from vidgen.errors import VidgenError

Direction = Literal["LR", "TB"]
Routing = Literal["straight", "orthogonal"]
NodeShape = Literal["box", "ellipse", "diamond", "stadium"]
Point = tuple[float, float]

DIRECTIONS: tuple[str, ...] = ("LR", "TB")
ROUTINGS: tuple[str, ...] = ("straight", "orthogonal")
SHAPES: tuple[str, ...] = ("box", "ellipse", "diamond", "stadium")


@dataclass(frozen=True)
class GraphNode:
    """A node to lay out: its id, size (width x height, in the units of the result) and the
    outline edges are clipped to (``box``, ``ellipse``, ``diamond`` or ``stadium`` = a pill)."""

    id: str
    width: float = 0.0
    height: float = 0.0
    shape: NodeShape = "box"


@dataclass(frozen=True)
class GraphEdge:
    """A directed edge ``source -> target``; ``label`` is the size (width, height) of a label to
    reserve room for in the gap the edge leaves its source through (``None``: no label)."""

    source: str
    target: str
    label: tuple[float, float] | None = None


@dataclass(frozen=True)
class NodePlace:
    """Where a node ended up: centre ``(x, y)``, its size, layer (0 first) and index in it."""

    x: float
    y: float
    width: float
    height: float
    layer: int
    order: int


@dataclass(frozen=True)
class EdgeRoute:
    """The route of an input edge from its source's outline to its target's (``points`` has at
    least two points, in the edge's own direction). ``reversed``: the edge closes a cycle and
    runs against the layer direction. ``label_at``: where to centre its label (on the route,
    in the middle of the gap next to the source), or ``None`` without a label."""

    source: str
    target: str
    points: tuple[Point, ...]
    reversed: bool = False
    label_at: Point | None = None


@dataclass(frozen=True)
class GraphLayout:
    """The result of :func:`layered_layout`: node places by id, edge routes in input order,
    the real nodes of each layer in order, the bounding size, the direction, and the number of
    edge crossings between neighbouring layers (counted on the dummy-node graph)."""

    nodes: dict[str, NodePlace]
    edges: list[EdgeRoute]
    layers: list[list[str]]
    width: float
    height: float
    direction: Direction
    crossings: int
    reversed_edges: list[int] = field(default_factory=list)


@dataclass
class _Item:
    """A node of the layered graph: a real node, or a dummy on a long edge."""

    key: int
    node: GraphNode | None
    layer: int = 0
    pos: float = 0.0  # cross coordinate of the centre
    preds: list[int] = field(default_factory=list)
    succs: list[int] = field(default_factory=list)

    def breadth(self, direction: str) -> float:
        if self.node is None:
            return 0.0
        return self.node.height if direction == "LR" else self.node.width

    def depth(self, direction: str) -> float:
        if self.node is None:
            return 0.0
        return self.node.width if direction == "LR" else self.node.height


def layered_layout(
    nodes: Sequence[str | GraphNode],
    edges: Sequence[tuple[str, str] | GraphEdge],
    *,
    direction: Direction = "LR",
    layer_gap: float = 1.0,
    node_gap: float = 0.5,
    routing: Routing = "straight",
    port_spacing: float = 0.2,
    port_spread: float = 0.6,
    label_margin: float = 0.15,
    sweeps: int = 12,
) -> GraphLayout:
    """Lay out a directed graph in layers (see the module docs for the phases).

    ``nodes``: ids or :class:`GraphNode` (with sizes; an id alone is a point). ``edges``:
    ``(source, target)`` pairs or :class:`GraphEdge`. ``direction``: ``LR`` (layers left to
    right) or ``TB`` (top to bottom). ``layer_gap``: free space between neighbouring layers;
    ``node_gap``: between neighbouring nodes of a layer (half of it next to an edge passing
    through). Edges into or out of one side of a node get ports ``port_spacing`` apart, within
    ``port_spread`` of that side. ``routing``: ``straight`` (polylines) or ``orthogonal``.

    Unknown ids, duplicate node ids and self-loops raise :class:`~vidgen.errors.VidgenError`.
    """
    if direction not in DIRECTIONS:
        raise VidgenError(f"unknown direction {direction!r}; use {' or '.join(DIRECTIONS)}")
    if routing not in ROUTINGS:
        raise VidgenError(f"unknown routing {routing!r}; use {' or '.join(ROUTINGS)}")
    graph_nodes = [n if isinstance(n, GraphNode) else GraphNode(str(n)) for n in nodes]
    index: dict[str, int] = {}
    for i, n in enumerate(graph_nodes):
        if n.id in index:
            raise VidgenError(f"node {n.id!r} is listed twice")
        if n.shape not in SHAPES:
            raise VidgenError(f"node {n.id!r}: unknown shape {n.shape!r}; use one of {', '.join(SHAPES)}")
        index[n.id] = i
    graph_edges = [e if isinstance(e, GraphEdge) else GraphEdge(str(e[0]), str(e[1])) for e in edges]
    for e in graph_edges:
        for end in (e.source, e.target):
            if end not in index:
                raise VidgenError(f"edge {e.source} -> {e.target}: unknown node {end!r}")
        if e.source == e.target:
            raise VidgenError(f"edge {e.source} -> {e.target}: a node cannot point to itself")
    n = len(graph_nodes)
    pairs = tuple((index[e.source], index[e.target]) for e in graph_edges)
    flipped, item_layers, chains, order, crossings = _topology(n, pairs, sweeps)
    items = [_Item(key, graph_nodes[key] if key < n else None, lay) for key, lay in enumerate(item_layers)]
    for chain in chains:
        for a, b in zip(chain, chain[1:]):
            items[a].succs.append(b)
            items[b].preds.append(a)
    gaps = _gaps(items, order, chains, graph_edges, flipped, direction, layer_gap, label_margin)
    mains = _mains(items, order, direction, gaps)
    _cross_positions(items, order, direction, node_gap)

    places: dict[str, tuple[float, float]] = {}
    routes_mc: list[tuple[list[tuple[float, float]], tuple[float, float] | None]] = []
    ports = _ports(items, chains, direction, port_spacing, port_spread)
    depths = [max((items[key].depth(direction) for key in row), default=0.0) for row in order]
    for k, chain in enumerate(chains):
        points = _route(items, chain, k, ports, mains, direction)
        anchor = None
        if graph_edges[k].label is not None:
            lay = items[chain[-1]].layer - 1 if k in flipped else items[chain[0]].layer  # gap after layer `lay`
            middle = (mains[lay] + depths[lay] / 2 + mains[lay + 1] - depths[lay + 1] / 2) / 2
            anchor = _label_anchor(points, k in flipped, middle)
        routes_mc.append((points, anchor))
    if routing == "orthogonal":
        routes_mc = _channels(routes_mc, items, chains, mains, depths)

    def to_xy(main: float, cross: float) -> tuple[float, float]:
        return (main, -cross) if direction == "LR" else (cross, -main)

    xs: list[float] = []
    ys: list[float] = []
    for item in items[:n]:
        x, y = to_xy(mains[item.layer], item.pos)
        node = item.node
        assert node is not None
        places[node.id] = (x, y)
        xs += [x - node.width / 2, x + node.width / 2]
        ys += [y - node.height / 2, y + node.height / 2]
    for points, anchor in routes_mc:
        for main, cross in points + ([anchor] if anchor else []):
            x, y = to_xy(main, cross)
            xs.append(x)
            ys.append(y)
    cx = (min(xs) + max(xs)) / 2 if xs else 0.0
    cy = (min(ys) + max(ys)) / 2 if ys else 0.0

    def shifted(main: float, cross: float) -> Point:
        x, y = to_xy(main, cross)
        return (round(x - cx, 9), round(y - cy, 9))

    node_places = {}
    for item in items[:n]:
        node = item.node
        assert node is not None
        x, y = places[node.id]
        node_places[node.id] = NodePlace(round(x - cx, 9), round(y - cy, 9), node.width, node.height, item.layer, order[item.layer].index(item.key))
    routes = []
    for k, (points, anchor) in enumerate(routes_mc):
        path = [shifted(*p) for p in points]
        if k in flipped:
            path.reverse()
        e = graph_edges[k]
        routes.append(EdgeRoute(e.source, e.target, tuple(path), k in flipped, shifted(*anchor) if anchor else None))
    layers = [[items[key].node.id for key in row if items[key].node is not None] for row in order]  # type: ignore[union-attr]
    return GraphLayout(
        node_places, routes, layers,
        round(max(xs) - min(xs), 9) if xs else 0.0, round(max(ys) - min(ys), 9) if ys else 0.0,
        direction, crossings, sorted(flipped),
    )


@lru_cache(maxsize=64)
def _topology(
    n: int, pairs: tuple[tuple[int, int], ...], sweeps: int
) -> tuple[frozenset[int], list[int], list[list[int]], list[list[int]], int]:
    """The size-independent phases (cycles, layers, dummies, order) for ``n`` nodes and the
    edge index pairs: ``(flipped edges, layer per item, chain of item keys per edge, item keys
    per layer in order, crossings)``. Cached: scenes lay out one graph at many
    sizes. Callers must not modify the lists."""
    flipped = _back_edges(n, list(pairs))
    oriented = [(v, u) if k in flipped else (u, v) for k, (u, v) in enumerate(pairs)]
    layer = _layers(n, oriented)
    items = [_Item(i, GraphNode(str(i)), layer[i]) for i in range(n)]
    chains: list[list[int]] = []
    for u, v in oriented:
        chain = [u]
        for lay in range(layer[u] + 1, layer[v]):
            dummy = _Item(len(items), None, lay)
            items.append(dummy)
            chain.append(dummy.key)
        chain.append(v)
        for a, b in zip(chain, chain[1:]):
            items[a].succs.append(b)
            items[b].preds.append(a)
        chains.append(chain)
    order = _order(items, max(layer, default=-1) + 1, sweeps)
    return frozenset(flipped), [it.layer for it in items], chains, order, _total_crossings(items, order)


# ----- phase 1 and 2: cycles and layers ------------------------------------------------------------


def _back_edges(n: int, pairs: list[tuple[int, int]]) -> set[int]:
    """Indices of the edges a depth-first search (nodes and edges in input order) finds closing
    a cycle; reversing them makes the graph acyclic."""
    out: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for k, (u, v) in enumerate(pairs):
        out[u].append((v, k))
    state = [0] * n  # 0 new, 1 on the stack, 2 done
    back: set[int] = set()
    for root in range(n):
        if state[root]:
            continue
        stack: list[tuple[int, int]] = [(root, 0)]
        state[root] = 1
        while stack:
            node, i = stack[-1]
            if i < len(out[node]):
                stack[-1] = (node, i + 1)
                nxt, k = out[node][i]
                if state[nxt] == 1:
                    back.add(k)
                elif state[nxt] == 0:
                    state[nxt] = 1
                    stack.append((nxt, 0))
            else:
                state[node] = 2
                stack.pop()
    return back


def _layers(n: int, edges: list[tuple[int, int]]) -> list[int]:
    """Longest-path layering (every edge points to a later layer), then sources moved up to
    just before their nearest successor."""
    preds: list[list[int]] = [[] for _ in range(n)]
    succs: list[list[int]] = [[] for _ in range(n)]
    for u, v in edges:
        succs[u].append(v)
        preds[v].append(u)
    indegree = [len(p) for p in preds]
    queue = [i for i in range(n) if indegree[i] == 0]
    topo: list[int] = []
    while queue:
        u = queue.pop(0)
        topo.append(u)
        for v in succs[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                queue.append(v)
    layer = [0] * n
    for u in topo:
        for v in succs[u]:
            layer[v] = max(layer[v], layer[u] + 1)
    for u in reversed(topo):
        if not preds[u] and succs[u]:
            layer[u] = min(layer[v] for v in succs[u]) - 1
    return layer


# ----- phase 3: order ------------------------------------------------------------------------------


def _order(items: list[_Item], depth: int, sweeps: int) -> list[list[int]]:
    """Keys of the items of each layer in order, crossings reduced: barycenter sweeps from two
    starts (the input order and its reverse), the better result kept (the first on a tie)."""
    best: tuple[int, list[list[int]]] | None = None
    for reverse in (False, True):
        order = _improve(items, _initial(items, depth, reverse), sweeps)
        count = _total_crossings(items, order)
        if best is None or count < best[0]:
            best = (count, order)
        if count == 0:
            break
    assert best is not None
    return best[1]


def _initial(items: list[_Item], depth: int, reverse: bool) -> list[list[int]]:
    """Layer 0 (and nodes without predecessors) in input order (or reversed), every other
    node after its first predecessor (a breadth-first look)."""
    order: list[list[int]] = [[] for _ in range(depth)]
    for item in reversed(items) if reverse else items:
        if item.layer == 0 or not item.preds:
            order[item.layer].append(item.key)
    placed = {k for row in order for k in row}
    for lay in range(1, depth):
        prev = {k: i for i, k in enumerate(order[lay - 1])}
        rest = [it for it in items if it.layer == lay and it.key not in placed]
        rest.sort(key=lambda it: (min(prev.get(p, len(prev)) for p in it.preds), -it.key if reverse else it.key))
        order[lay] += [it.key for it in rest]
    return order


def _improve(items: list[_Item], order: list[list[int]], sweeps: int) -> list[list[int]]:
    """Barycenter sweeps down and up (ties keep the current order) with transposition; the
    order with the fewest crossings seen."""
    depth = len(order)
    best = [row[:] for row in order]
    best_count = _total_crossings(items, order)
    for sweep in range(sweeps):
        if best_count == 0:
            break
        down = sweep % 2 == 0
        layers = range(1, depth) if down else range(depth - 2, -1, -1)
        for lay in layers:
            fixed = order[lay - 1] if down else order[lay + 1]
            where = {k: i for i, k in enumerate(fixed)}
            current = {k: i for i, k in enumerate(order[lay])}

            def bary(key: int) -> float:
                near = items[key].preds if down else items[key].succs
                spots = [where[k] for k in near if k in where]
                return sum(spots) / len(spots) if spots else float(current[key])

            order[lay].sort(key=lambda k: (bary(k), current[k]))
        _transpose(items, order)
        count = _total_crossings(items, order)
        if count < best_count:
            best, best_count = [row[:] for row in order], count
    _transpose(items, best)
    return best


def _crossings_between(items: list[_Item], upper: list[int], lower: list[int]) -> int:
    """Edge crossings between two neighbouring layers."""
    top = {k: i for i, k in enumerate(upper)}
    bottom = {k: i for i, k in enumerate(lower)}
    pairs = [(top[k], bottom[s]) for k in upper for s in items[k].succs if s in bottom]
    count = 0
    for i in range(len(pairs)):
        a, b = pairs[i]
        for c, d in pairs[i + 1 :]:
            if (a - c) * (b - d) < 0:
                count += 1
    return count


def _total_crossings(items: list[_Item], order: list[list[int]]) -> int:
    return sum(_crossings_between(items, order[i], order[i + 1]) for i in range(len(order) - 1))


def _transpose(items: list[_Item], order: list[list[int]]) -> None:
    """Swap neighbours in a layer while that removes crossings with the layers around it."""

    def local(lay: int) -> int:
        count = 0
        if lay > 0:
            count += _crossings_between(items, order[lay - 1], order[lay])
        if lay + 1 < len(order):
            count += _crossings_between(items, order[lay], order[lay + 1])
        return count

    for _ in range(len(items) + 1):
        improved = False
        for lay, row in enumerate(order):
            for i in range(len(row) - 1):
                before = local(lay)
                row[i], row[i + 1] = row[i + 1], row[i]
                if local(lay) < before:
                    improved = True
                else:
                    row[i], row[i + 1] = row[i + 1], row[i]
        if not improved:
            return


# ----- phase 4: coordinates ------------------------------------------------------------------------


def _gaps(
    items: list[_Item],
    order: list[list[int]],
    chains: list[list[int]],
    edges: list[GraphEdge],
    flipped: frozenset[int],
    direction: str,
    layer_gap: float,
    label_margin: float,
) -> list[float]:
    """Free space after each layer: ``layer_gap``, or more where a label must fit."""
    gaps = [layer_gap] * max(len(order) - 1, 0)
    for k, chain in enumerate(chains):
        label = edges[k].label
        if label is None:
            continue
        extent = label[0] if direction == "LR" else label[1]
        # the label sits in the gap next to the edge's real source
        source_layer = items[chain[-1]].layer if k in flipped else items[chain[0]].layer
        gap = source_layer - 1 if k in flipped else source_layer
        if 0 <= gap < len(gaps):
            gaps[gap] = max(gaps[gap], extent + 2 * label_margin)
    return gaps


def _mains(items: list[_Item], order: list[list[int]], direction: str, gaps: list[float]) -> list[float]:
    """Main-axis coordinate of each layer's centre line."""
    depths = [max((items[k].depth(direction) for k in row), default=0.0) for row in order]
    mains: list[float] = []
    at = 0.0
    for i, d in enumerate(depths):
        if i:
            at += depths[i - 1] / 2 + gaps[i - 1] + d / 2
        mains.append(at)
    return mains


def _separation(a: _Item, b: _Item, direction: str, node_gap: float) -> float:
    gap = node_gap if a.node is not None and b.node is not None else node_gap / 2
    return a.breadth(direction) / 2 + gap + b.breadth(direction) / 2


def _isotonic(targets: list[float], weights: list[float]) -> list[float]:
    """Weighted least squares fit of a non-decreasing sequence (pool adjacent violators)."""
    blocks: list[list[float]] = []  # [value, weight, count]
    for t, w in zip(targets, weights):
        blocks.append([t, w, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, c2 = blocks.pop()
            v1, w1, c1 = blocks.pop()
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, c1 + c2])
    out: list[float] = []
    for value, _, count in blocks:
        out += [value] * int(count)
    return out


def _cross_positions(items: list[_Item], order: list[list[int]], direction: str, node_gap: float, passes: int = 10) -> None:
    """Cross-axis centres: packed, then pulled towards the mean of their neighbours in the layer
    before (down passes) or after (up passes, last, so parents sit centred over their children),
    keeping the separations (long edges pull harder, to run straight)."""
    offsets: list[list[float]] = []
    for row in order:
        offs, at = [], 0.0
        for i, key in enumerate(row):
            if i:
                at += _separation(items[row[i - 1]], items[key], direction, node_gap)
            offs.append(at)
        offsets.append(offs)
        for key, off in zip(row, offs):
            items[key].pos = off - at / 2

    def settle(lay: int, mode: str) -> None:
        row = order[lay]
        wanted, weights = [], []
        for key in row:
            item = items[key]
            near = item.preds if mode == "down" else item.succs
            if near:
                wanted.append(sum(items[k].pos for k in near) / len(near))
                weights.append(len(near) * (2.0 if item.node is None else 1.0))
            else:
                wanted.append(item.pos)
                weights.append(0.05)
        fitted = _isotonic([w - o for w, o in zip(wanted, offsets[lay])], weights)
        for key, y, off in zip(row, fitted, offsets[lay]):
            items[key].pos = y + off

    depth = len(order)
    for p in range(passes):
        mode = "down" if p % 2 == 0 else "up"  # ends with "up": parents centred over children
        layers = range(depth) if mode == "down" else range(depth - 1, -1, -1)
        for lay in layers:
            settle(lay, mode)


# ----- phase 5: routes -----------------------------------------------------------------------------


def _ports(
    items: list[_Item], chains: list[list[int]], direction: str, spacing: float, spread: float
) -> dict[tuple[int, int], float]:
    """Cross offset of each edge's port on a node: ``(edge, 0)`` its start, ``(edge, 1)`` its
    end. Ports on one side are spaced evenly, ordered by the cross position of the edge's
    next point (so edges do not cross at the node)."""
    sides: dict[tuple[int, str], list[tuple[float, int, int]]] = {}
    for k, chain in enumerate(chains):
        sides.setdefault((chain[0], "out"), []).append((items[chain[1]].pos, k, 0))
        sides.setdefault((chain[-1], "in"), []).append((items[chain[-2]].pos, k, 1))
    ports: dict[tuple[int, int], float] = {}
    for (key, _), entries in sides.items():
        entries.sort()
        count = len(entries)
        breadth = items[key].breadth(direction)
        step = min(spacing, spread * breadth / (count - 1)) if count > 1 else 0.0
        for i, (_, k, end) in enumerate(entries):
            ports[(k, end)] = (i - (count - 1) / 2) * step
    return ports


def _boundary(node: GraphNode, direction: str, offset: float) -> float:
    """Distance from a node's centre along the main axis to its outline, at ``offset`` across."""
    depth = (node.width if direction == "LR" else node.height) / 2
    breadth = (node.height if direction == "LR" else node.width) / 2
    if breadth <= 0 or depth <= 0:
        return max(depth, 0.0)
    t = min(abs(offset) / breadth, 1.0)
    if node.shape == "ellipse":
        return depth * (1 - t * t) ** 0.5
    if node.shape == "diamond":
        return depth * (1 - t)
    if node.shape == "stadium":  # rounded ends of radius r; a flat stretch where the side is longer
        r = min(depth, breadth)
        e = max(abs(offset) - max(breadth - r, 0.0), 0.0)
        return depth - r + max(r * r - e * e, 0.0) ** 0.5
    return depth


def _route(
    items: list[_Item], chain: list[int], k: int, ports: dict[tuple[int, int], float], mains: list[float], direction: str
) -> list[tuple[float, float]]:
    """``(main, cross)`` points from the start port on the first node's outline through the
    dummies to the end port (orthogonal routes get their channels in :func:`_channels`)."""
    first, last = items[chain[0]], items[chain[-1]]
    assert first.node is not None and last.node is not None
    start = (mains[first.layer] + _boundary(first.node, direction, ports[(k, 0)]), first.pos + ports[(k, 0)])
    end = (mains[last.layer] - _boundary(last.node, direction, ports[(k, 1)]), last.pos + ports[(k, 1)])
    return [start, *[(mains[items[key].layer], items[key].pos) for key in chain[1:-1]], end]


def _label_anchor(points: list[tuple[float, float]], flipped: bool, middle: float) -> tuple[float, float]:
    """Where an edge's label goes: on its first segment (from the real source), at main
    coordinate ``middle`` (the middle of the gap next to the source)."""
    path = points[::-1] if flipped else points
    return _point_at(path[0], path[1], middle)


def _point_at(a: tuple[float, float], b: tuple[float, float], main: float) -> tuple[float, float]:
    """The point of segment ``a``-``b`` at main coordinate ``main``."""
    span = b[0] - a[0]
    if abs(span) < 1e-9:
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    t = min(max((main - a[0]) / span, 0.0), 1.0)
    return (a[0] + span * t, a[1] + (b[1] - a[1]) * t)


def _channels(
    routes: list[tuple[list[tuple[float, float]], tuple[float, float] | None]],
    items: list[_Item],
    chains: list[list[int]],
    mains: list[float],
    depths: list[float],
) -> list[tuple[list[tuple[float, float]], tuple[float, float] | None]]:
    """Turn straight polylines into orthogonal ones: each step between two layers that changes
    the cross position gets a run across the gap in a channel of its own (edges whose runs
    overlap use different channels, ordered so that they do not cross needlessly)."""
    # per gap, the edges that need a run: (edge, step index, from cross, to cross)
    runs: dict[int, list[tuple[int, int, float, float]]] = {}
    for k, (points, _) in enumerate(routes):
        chain = chains[k]
        for i in range(len(points) - 1):
            a, b = points[i], points[i + 1]
            if abs(a[1] - b[1]) > 1e-6:
                runs.setdefault(items[chain[i]].layer, []).append((k, i, a[1], b[1]))
    channel: dict[tuple[int, int], float] = {}
    for gap, entries in runs.items():
        downs = sorted((e for e in entries if e[3] > e[2]), key=lambda e: (-e[2], e[0]))
        ups = sorted((e for e in entries if e[3] < e[2]), key=lambda e: (e[2], e[0]))
        lanes: list[list[tuple[float, float]]] = []
        lane_of: dict[tuple[int, int], int] = {}
        for k, i, c0, c1 in downs + ups:
            lo, hi = min(c0, c1), max(c0, c1)
            for n, lane in enumerate(lanes):
                if all(hi < a - 1e-6 or lo > b + 1e-6 for a, b in lane):
                    lane.append((lo, hi))
                    lane_of[(k, i)] = n
                    break
            else:
                lanes.append([(lo, hi)])
                lane_of[(k, i)] = len(lanes) - 1
        begin = mains[gap] + depths[gap] / 2
        end = mains[gap + 1] - depths[gap + 1] / 2
        width = end - begin
        count = len(lanes)
        for key, lane in lane_of.items():
            channel[key] = begin + width * (lane + 1) / (count + 1) if count > 1 else (begin + end) / 2
    out = []
    for k, (points, anchor) in enumerate(routes):
        path: list[tuple[float, float]] = [points[0]]
        for i in range(len(points) - 1):
            a, b = points[i], points[i + 1]
            if (k, i) in channel:
                c = channel[(k, i)]
                path += [(c, a[1]), (c, b[1])]
            path.append(b)
        path = _simplify(path)
        if anchor is not None:
            anchor = _first_run_anchor(path, anchor)
        out.append((path, anchor))
    return out


def _first_run_anchor(path: list[tuple[float, float]], anchor: tuple[float, float]) -> tuple[float, float]:
    """The point of an orthogonal path nearest the straight route's label anchor."""
    best, dist = anchor, float("inf")
    for a, b in zip(path, path[1:]):
        p = _nearest(a, b, anchor)
        d = (p[0] - anchor[0]) ** 2 + (p[1] - anchor[1]) ** 2
        if d < dist:
            best, dist = p, d
    return best


def _nearest(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    if length < 1e-12:
        return a
    t = min(max(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length, 0.0), 1.0)
    return (a[0] + dx * t, a[1] + dy * t)


def _simplify(path: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop repeated points and middle points of straight runs."""
    out: list[tuple[float, float]] = []
    for p in path:
        if out and abs(out[-1][0] - p[0]) < 1e-9 and abs(out[-1][1] - p[1]) < 1e-9:
            continue
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            cross = (b[0] - a[0]) * (p[1] - b[1]) - (b[1] - a[1]) * (p[0] - b[0])
            if abs(cross) < 1e-9:
                out[-1] = p
                continue
        out.append(p)
    return out

