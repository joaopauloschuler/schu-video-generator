"""Automatic layout of a signalling pathway in compartment bands (DESIGN.md §95.12). No manim.

The signal runs along the main axis (``LR``: left to right, the bands side by side as columns,
for landscape frames; ``TB``: top to bottom, the bands stacked as rows, for portrait frames):
extracellular space, plasma membrane, cytosol, ER, mitochondrion, nucleus. Each band holds one or
more ranks (layers across the main axis):

1. **Ranks.** A membrane band is one rank: its nodes stand in a row along the membrane, and
   arcs between them run along it (a receptor next to its G protein next to its cyclase).
   Other bands are layered by the longest chain of arcs within the band (feedback arcs and arcs
   closing a loop left out), a node without a predecessor there just before its nearest
   successor. A band's ranks follow the band before.
2. **Dummies.** An arc spanning several ranks gets an invisible point in each rank between, so
   it is routed through that rank where no node is.
3. **Order.** Barycenter sweeps down and up the ranks with transposition (as ``vidgen.graph``),
   the order with fewest crossings kept. In a membrane row, nodes joined along the row move as a
   block (in the order their arcs give), so each such arc joins neighbours.
4. **Coordinates.** Ranks are spaced by their deepest node plus a gap (larger between bands:
   the membranes are drawn there, and room for arc labels is added); across a rank nodes are
   pulled towards their neighbours with a weighted isotonic fit keeping them apart.
5. **Routes.** Every route crosses a rank straight along the main axis (at its port, or at its
   dummy's place) and changes its cross position only in the empty gaps between ranks, so no
   route crosses a node. Arcs between neighbours in a row run straight along it; between
   non-neighbours they bend out into the gap after the row.

Deterministic: the same nodes, sizes and arcs give the same layout (no randomness; ties in input
order). Units are whatever the node sizes are in; the result is centred on the origin, y up."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from vidgen.errors import VidgenError

Direction = Literal["LR", "TB"]
Point = tuple[float, float]


@dataclass(frozen=True)
class LayoutNode:
    """A node to place: id, band index (bands in drawing order), size, whether its band is a
    membrane row, and whether it is an outcome (drawn beside the node it follows)."""

    id: str
    band: int
    width: float
    height: float
    row: bool = False
    outcome: bool = False


@dataclass(frozen=True)
class LayoutEdge:
    """An arc: ``source -> target``; ``feedback`` arcs and arcs closing loops do not set ranks;
    ``label`` (width, height) reserves room in the gap the arc leaves its source through."""

    source: str
    target: str
    feedback: bool = False
    label: tuple[float, float] | None = None


@dataclass(frozen=True)
class Placed:
    """A node's centre, size, rank and place in it."""

    x: float
    y: float
    width: float
    height: float
    rank: int
    order: int

    def box(self, pad: float = 0.0) -> tuple[float, float, float, float]:
        return (self.x - self.width / 2 - pad, self.y - self.height / 2 - pad, self.x + self.width / 2 + pad, self.y + self.height / 2 + pad)


@dataclass(frozen=True)
class Route:
    """An arc's route from its source's outline to its target's (``points`` in the arc's
    direction): straight runs across ranks and along rows; ``curves[i]`` says whether the run
    from ``points[i]`` to ``points[i+1]`` is an S-curve along the main axis (in a gap) rather
    than straight. ``label_at``: where its label goes (in a gap), or ``None``."""

    source: str
    target: str
    points: tuple[Point, ...]
    curves: tuple[bool, ...]
    label_at: Point | None = None
    lateral: bool = False


@dataclass(frozen=True)
class BandBox:
    """A band's rectangle (x0, y0, x1, y1)."""

    index: int
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class PathwayLayout:
    """Node places, arc routes (input order), band boxes, the boundaries between bands (main
    coordinate, as x in LR and y in TB), the size, the direction and the crossings."""

    nodes: dict[str, Placed]
    routes: list[Route]
    bands: list[BandBox]
    width: float
    height: float
    direction: Direction
    crossings: int
    ranks: list[list[str]] = field(default_factory=list)


@dataclass
class _Item:
    key: int
    node: LayoutNode | None
    rank: int
    pos: float = 0.0
    preds: list[int] = field(default_factory=list)
    succs: list[int] = field(default_factory=list)

    def breadth(self, d: str) -> float:
        if self.node is None:
            return 0.0
        return self.node.height if d == "LR" else self.node.width

    def depth(self, d: str) -> float:
        if self.node is None:
            return 0.0
        return self.node.width if d == "LR" else self.node.height


def pathway_layout(
    nodes: Sequence[LayoutNode],
    edges: Sequence[LayoutEdge],
    *,
    direction: Direction = "LR",
    rank_gap: float = 0.8,
    band_gap: float = 1.1,
    node_gap: float = 0.45,
    row_gap: float = 0.7,
    band_pad: float = 0.25,
    label_room: float = 0.0,
    port_spacing: float = 0.16,
    label_margin: float = 0.1,
    sweeps: int = 16,
    outcomes_beside: bool = True,
) -> PathwayLayout:
    """Lay out a pathway (see the module docs). ``rank_gap``: free space between ranks of a
    band; ``band_gap``: between bands; ``node_gap``: between nodes of a rank; ``row_gap``:
    between neighbours of a membrane row joined by an arc (room for its arrow); ``band_pad``:
    a band's margin round its nodes; ``label_room``: room for each band's name (LR: above the
    columns; TB: at the start of each row); ``outcomes_beside``: an outcome stands beside the
    node it follows (in its rank) instead of in a rank of its own."""
    if direction not in ("LR", "TB"):
        raise VidgenError(f"unknown direction {direction!r}; use LR or TB")
    index = {n.id: i for i, n in enumerate(nodes)}
    if len(index) != len(nodes):
        raise VidgenError("pathway layout: a node is listed twice")
    for e in edges:
        if e.source not in index or e.target not in index:
            raise VidgenError(f"pathway layout: arc {e.source} -> {e.target} names an unknown node")
    n = len(nodes)
    bands = sorted({nd.band for nd in nodes})
    row_band = {nd.band: nd.row for nd in nodes}
    # 1. ranks
    ranking = [k for k, e in enumerate(edges) if not e.feedback]
    back = _back_edges(n, [(index[edges[k].source], index[edges[k].target]) for k in ranking])
    downstream = [k for j, k in enumerate(ranking) if j not in back]
    local = [0] * n
    depth_of: dict[int, int] = {}
    satellites = _satellites(nodes, edges, index, downstream, row_band, outcomes_beside)
    for b in bands:
        members = [i for i in range(n) if nodes[i].band == b and i not in satellites]
        if row_band[b]:
            depth_of[b] = 1
            continue
        inner = [(index[edges[k].source], index[edges[k].target]) for k in downstream
                 if nodes[index[edges[k].source]].band == b and nodes[index[edges[k].target]].band == b
                 and index[edges[k].source] not in satellites and index[edges[k].target] not in satellites]
        layers = _longest_path(members, inner)
        for i in members:
            local[i] = layers[i]
        for i, host in satellites.items():
            if nodes[i].band == b:
                local[i] = layers[host]
        depth_of[b] = max((layers[i] for i in members), default=0) + 1
    offset: dict[int, int] = {}
    at = 0
    for b in bands:
        offset[b] = at
        at += depth_of[b]
    rank_count = at
    rank = [offset[nodes[i].band] + local[i] for i in range(n)]
    band_of_rank = [0] * rank_count
    for b in bands:
        for r in range(offset[b], offset[b] + depth_of[b]):
            band_of_rank[r] = b
    is_row_rank = [row_band[band_of_rank[r]] for r in range(rank_count)]
    # 2. items and chains (from the lower rank to the higher)
    items = [_Item(i, nodes[i], rank[i]) for i in range(n)]
    chains: list[list[int]] = []
    lateral: list[int] = []
    for k, e in enumerate(edges):
        a, b2 = index[e.source], index[e.target]
        if rank[a] == rank[b2]:
            chains.append([a, b2])
            lateral.append(k)
            continue
        lo, hi = (a, b2) if rank[a] < rank[b2] else (b2, a)
        chain = [lo]
        for r in range(rank[lo] + 1, rank[hi]):
            dummy = _Item(len(items), None, r)
            items.append(dummy)
            chain.append(dummy.key)
        chain.append(hi)
        for x, y in zip(chain, chain[1:]):
            items[x].succs.append(y)
            items[y].preds.append(x)
        chains.append(chain)
    # row blocks: nodes of a membrane row joined along it, in arc order
    blocks = _row_blocks(items, nodes, edges, index, lateral, is_row_rank, after=direction == "LR")
    # 3. order
    order = _order(items, rank_count, is_row_rank, blocks, sweeps)
    # 4. coordinates
    lateral_pairs = {frozenset((index[edges[k].source], index[edges[k].target])) for k in lateral}
    _cross(items, order, direction, node_gap, row_gap, lateral_pairs, is_row_rank)
    depths = [max((items[k].depth(direction) for k in row), default=0.0) for row in order]
    gaps = []
    for r in range(rank_count - 1):
        between = band_of_rank[r] != band_of_rank[r + 1]
        gaps.append((band_gap + 2 * band_pad) if between else rank_gap)
    for k, e in enumerate(edges):
        if e.label is None or k in lateral:
            continue
        a, b2 = index[e.source], index[e.target]
        r = rank[a] if rank[a] < rank[b2] else rank[a] - 1
        if 0 <= r < len(gaps):
            extent = e.label[0] if direction == "LR" else e.label[1]
            gaps[r] = max(gaps[r], extent + 2 * label_margin + (2 * band_pad if band_of_rank[r] != band_of_rank[r + 1] else 0.0))
    # TB: each band's name at its start (main axis); LR: above the columns (cross axis)
    mains: list[float] = []
    pos = 0.0
    for r in range(rank_count):
        if r:
            pos += depths[r - 1] / 2 + gaps[r - 1] + depths[r] / 2
        if direction == "TB" and label_room > 0 and (r == 0 or band_of_rank[r] != band_of_rank[r - 1]) and not is_row_rank[r]:
            pos += label_room
        mains.append(pos)
    # 5. routes
    ports = _ports(items, chains, edges, index, direction, port_spacing, lateral)
    routes_mc: list[tuple[list[Point], list[bool], Point | None, bool]] = []
    lanes: dict[int, int] = {}
    for k, e in enumerate(edges):
        a, b2 = index[e.source], index[e.target]
        if k in lateral:
            pts, curves = _lateral_route(items, order, a, b2, mains, depths, gaps, direction, lanes)
            routes_mc.append((pts, curves, None, True))
            continue
        chain = chains[k]
        pts, curves = _route(items, chain, k, ports, mains, depths, direction)
        if rank[a] > rank[b2]:
            pts, curves = pts[::-1], curves[::-1]
        label_at = None
        if e.label is not None:
            label_at = _label_point(pts, curves)
        routes_mc.append((pts, curves, label_at, False))

    # bands: main extents from the gaps' middles; cross extent the whole drawing
    def to_xy(main: float, cross: float) -> Point:
        return (main, -cross) if direction == "LR" else (cross, -main)

    cross_lo = min((it.pos - it.breadth(direction) / 2 for it in items), default=0.0)
    cross_hi = max((it.pos + it.breadth(direction) / 2 for it in items), default=0.0)
    for pts, _, lab, _ in routes_mc:
        for _, c in pts + ([lab] if lab else []):
            cross_lo, cross_hi = min(cross_lo, c), max(cross_hi, c)
    cross_lo -= band_pad
    cross_hi += band_pad
    if direction == "LR":
        cross_lo -= label_room
    band_boxes_mc: list[tuple[int, float, float]] = []
    for b in bands:
        first, last = offset[b], offset[b] + depth_of[b] - 1
        start = mains[first] - depths[first] / 2 - (band_pad if not row_band[b] else band_pad * 0.5)
        if direction == "TB" and label_room > 0 and not row_band[b]:
            start -= label_room
        end = mains[last] + depths[last] / 2 + (band_pad if not row_band[b] else band_pad * 0.5)
        band_boxes_mc.append((b, start, end))
    # neighbouring bands meet in the middle of the gap between them
    for i in range(len(band_boxes_mc) - 1):
        b, s, e_ = band_boxes_mc[i]
        b2, s2, e2 = band_boxes_mc[i + 1]
        mid = (e_ + s2) / 2
        if row_band[b]:
            band_boxes_mc[i + 1] = (b2, mid, e2)
        elif row_band[b2]:
            band_boxes_mc[i] = (b, s, mid)
        else:
            band_boxes_mc[i] = (b, s, mid)
            band_boxes_mc[i + 1] = (b2, mid, e2)
    main_lo = min(s for _, s, _ in band_boxes_mc)
    main_hi = max(e for _, _, e in band_boxes_mc)
    xs = [to_xy(main_lo, cross_lo)[0], to_xy(main_hi, cross_hi)[0]]
    ys = [to_xy(main_lo, cross_lo)[1], to_xy(main_hi, cross_hi)[1]]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    def shifted(main: float, cross: float) -> Point:
        x, y = to_xy(main, cross)
        return (round(x - cx, 9), round(y - cy, 9))

    placed = {}
    for it in items[:n]:
        nd = it.node
        assert nd is not None
        x, y = shifted(mains[it.rank], it.pos)
        placed[nd.id] = Placed(x, y, nd.width, nd.height, it.rank, order[it.rank].index(it.key))
    routes = []
    for k, (pts, curves, lab, lat) in enumerate(routes_mc):
        e = edges[k]
        routes.append(Route(e.source, e.target, tuple(shifted(*p) for p in pts), tuple(curves), shifted(*lab) if lab else None, lat))
    boxes = []
    for b, s, e_ in band_boxes_mc:
        (x0, y0), (x1, y1) = shifted(s, cross_lo), shifted(e_, cross_hi)
        boxes.append(BandBox(b, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
    width = round(max(xs) - min(xs), 9)
    height = round(max(ys) - min(ys), 9)
    ranks = [[items[k].node.id for k in row if items[k].node is not None] for row in order]  # type: ignore[union-attr]
    return PathwayLayout(placed, routes, boxes, width, height, direction, _total_crossings(items, order), ranks)


# ----- ranks ------------------------------------------------------------------------------------


def _back_edges(n: int, pairs: list[tuple[int, int]]) -> set[int]:
    """Indices (into ``pairs``) of the arcs a depth-first search in input order finds closing a loop."""
    out: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for k, (u, v) in enumerate(pairs):
        out[u].append((v, k))
    state = [0] * n
    back: set[int] = set()
    for root in range(n):
        if state[root]:
            continue
        stack = [(root, 0)]
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


def _longest_path(members: list[int], edges: list[tuple[int, int]]) -> dict[int, int]:
    """Layer of each member: longest path from the band's sources; a source moved to just
    before its nearest successor."""
    preds: dict[int, list[int]] = {i: [] for i in members}
    succs: dict[int, list[int]] = {i: [] for i in members}
    for u, v in edges:
        succs[u].append(v)
        preds[v].append(u)
    indeg = {i: len(preds[i]) for i in members}
    queue = [i for i in members if indeg[i] == 0]
    topo: list[int] = []
    while queue:
        u = queue.pop(0)
        topo.append(u)
        for v in succs[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    layer = dict.fromkeys(members, 0)
    for u in topo:
        for v in succs[u]:
            layer[v] = max(layer[v], layer[u] + 1)
    for u in reversed(topo):
        if not preds[u] and succs[u]:
            layer[u] = min(layer[v] for v in succs[u]) - 1
    low = min(layer.values(), default=0)
    return {i: layer[i] - low for i in members}


def _satellites(nodes: Sequence[LayoutNode], edges: Sequence[LayoutEdge], index: dict[str, int], downstream: list[int],
                row_band: dict[int, bool], outcomes: bool = True) -> dict[int, int]:
    """Nodes drawn in the rank of the one node they act on or come from, beside it, instead of
    a rank of their own: a modifier nothing upstream activates acting on a node that has other
    inputs (a phosphodiesterase on cAMP, mTORC2 on Akt), and an outcome at the end of a chain
    (a phenotype after its gene). At most one of each per node, in the same band."""
    n = len(nodes)
    ins: dict[int, list[int]] = {i: [] for i in range(n)}
    outs: dict[int, list[int]] = {i: [] for i in range(n)}
    for k in downstream:
        a, b = index[edges[k].source], index[edges[k].target]
        outs[a].append(b)
        ins[b].append(a)
    found: dict[int, int] = {}
    taken: set[tuple[str, int]] = set()
    for i in range(n):
        if row_band[nodes[i].band]:
            continue
        targets, sources = set(outs[i]), set(ins[i])
        if not sources and len(targets) == 1:
            host, side = next(iter(targets)), "before"
            if len(set(ins[host])) < 2:
                continue
        elif outcomes and nodes[i].outcome and not targets and len(sources) == 1:
            host, side = next(iter(sources)), "after"
        else:
            continue
        if nodes[host].band != nodes[i].band or (side, host) in taken:
            continue
        found[i] = host
        taken.add((side, host))
    return {i: h for i, h in found.items() if h not in found}


# ----- order ------------------------------------------------------------------------------------


def _row_blocks(items: list[_Item], nodes: Sequence[LayoutNode], edges: Sequence[LayoutEdge], index: dict[str, int],
                lateral: list[int], is_row_rank: list[bool], after: bool = False) -> dict[int, list[int]]:
    """The blocks of nodes that must stay neighbours in their rank: nodes joined by arcs along
    the rank (a membrane row; a satellite and its node), each block in the order its arcs give
    (a depth-first walk from the first node without a predecessor in the group), keyed by its
    first node; a node of a membrane row alone is a block of one."""
    joined: dict[int, list[int]] = {}
    for k in lateral:
        a, b = index[edges[k].source], index[edges[k].target]
        if edges[k].feedback:
            joined.setdefault(a, [])
            joined.setdefault(b, [])
            continue
        joined.setdefault(a, []).append(b)
        joined.setdefault(b, [])
    blocks: dict[int, list[int]] = {}
    seen: set[int] = set()
    undirected: dict[int, set[int]] = {}
    for a, outs in joined.items():
        for b in outs:
            undirected.setdefault(a, set()).add(b)
            undirected.setdefault(b, set()).add(a)
    for i, it in enumerate(items[: len(nodes)]):
        if (not is_row_rank[it.rank] and i not in joined) or i in seen:
            continue
        group: list[int] = []
        stack = [i]
        while stack:
            x = stack.pop()
            if x in group:
                continue
            group.append(x)
            stack += sorted(undirected.get(x, ()), reverse=True)
        group.sort()
        has_pred = {b for a in group for b in joined.get(a, []) if b in group}
        starts = [g for g in group if g not in has_pred] or group[:1]
        walk: list[int] = []

        def visit(x: int) -> None:
            if x in walk:
                return
            walk.append(x)
            for y in joined.get(x, []):
                if y in group:
                    visit(y)

        for s in starts:
            visit(s)
        for g in group:
            if g not in walk:
                walk.append(g)
        if after and not is_row_rank[it.rank] and len(walk) == 2 and not any(nodes[k].outcome for k in walk):
            walk.reverse()     # a modifier after the node it acts on: below it left to right, clear of its state badges
        seen |= set(walk)
        blocks[walk[0]] = walk
    return blocks


def _order(items: list[_Item], depth: int, is_row: list[bool], blocks: dict[int, list[int]], sweeps: int) -> list[list[int]]:
    best: tuple[int, list[list[int]]] | None = None
    for reverse in (False, True):
        order = _initial(items, depth, is_row, blocks, reverse)
        order = _improve(items, order, is_row, blocks, sweeps)
        count = _total_crossings(items, order)
        if best is None or count < best[0]:
            best = (count, order)
        if count == 0:
            break
    assert best is not None
    return best[1]


def _block_units(row: list[int], blocks: dict[int, list[int]]) -> list[list[int]]:
    """The row's items grouped into its blocks (dummies alone), in the row's order of first members."""
    member: dict[int, int] = {m: first for first, block in blocks.items() for m in block}
    units: list[list[int]] = []
    done: set[int] = set()
    for k in row:
        head = member.get(k)
        if head is None:
            units.append([k])
        elif head not in done:
            done.add(head)
            units.append([m for m in blocks[head] if m in row])
    return units


def _initial(items: list[_Item], depth: int, is_row: list[bool], blocks: dict[int, list[int]], reverse: bool) -> list[list[int]]:
    order: list[list[int]] = [[] for _ in range(depth)]
    seq = list(reversed(items)) if reverse else list(items)
    for it in seq:
        if it.rank == 0 or not it.preds:
            order[it.rank].append(it.key)
    placed = {k for row in order for k in row}
    for r in range(1, depth):
        prev = {k: i for i, k in enumerate(order[r - 1])}
        rest = [it for it in items if it.rank == r and it.key not in placed]
        rest.sort(key=lambda it: (min(prev.get(p, len(prev)) for p in it.preds), -it.key if reverse else it.key))
        order[r] += [it.key for it in rest]
    for r in range(depth):
        order[r] = [k for unit in _block_units(order[r], blocks) for k in unit]
    return order


def _improve(items: list[_Item], order: list[list[int]], is_row: list[bool], blocks: dict[int, list[int]], sweeps: int) -> list[list[int]]:
    depth = len(order)
    # ranks whose blocks must stay together are not transposed node by node
    fixed_ranks = [is_row[r] or any(len(b) > 1 and items[b[0]].rank == r for b in blocks.values()) for r in range(depth)]
    best = [row[:] for row in order]
    best_count = _total_crossings(items, order)
    for sweep in range(sweeps):
        if best_count == 0:
            break
        down = sweep % 2 == 0
        ranks = range(1, depth) if down else range(depth - 2, -1, -1)
        for r in ranks:
            fixed = order[r - 1] if down else order[r + 1]
            where = {k: i for i, k in enumerate(fixed)}
            current = {k: i for i, k in enumerate(order[r])}

            def bary(keys: list[int]) -> float:
                spots = [where[x] for key in keys for x in (items[key].preds if down else items[key].succs) if x in where]
                return sum(spots) / len(spots) if spots else float(sum(current[k] for k in keys)) / len(keys)

            units = _block_units(order[r], blocks)
            units.sort(key=lambda u: (bary(u), current[u[0]]))
            order[r] = [k for u in units for k in u]
        _transpose(items, order, fixed_ranks)
        count = _total_crossings(items, order)
        if count < best_count:
            best, best_count = [row[:] for row in order], count
    _transpose(items, best, fixed_ranks)
    return best


def _crossings_between(items: list[_Item], upper: list[int], lower: list[int]) -> int:
    top = {k: i for i, k in enumerate(upper)}
    bottom = {k: i for i, k in enumerate(lower)}
    pairs = [(top[k], bottom[s]) for k in upper for s in items[k].succs if s in bottom]
    count = 0
    for i in range(len(pairs)):
        a, b = pairs[i]
        for c, d in pairs[i + 1:]:
            if (a - c) * (b - d) < 0:
                count += 1
    return count


def _total_crossings(items: list[_Item], order: list[list[int]]) -> int:
    return sum(_crossings_between(items, order[i], order[i + 1]) for i in range(len(order) - 1))


def _transpose(items: list[_Item], order: list[list[int]], is_row: list[bool]) -> None:
    def local(r: int) -> int:
        c = 0
        if r > 0:
            c += _crossings_between(items, order[r - 1], order[r])
        if r + 1 < len(order):
            c += _crossings_between(items, order[r], order[r + 1])
        return c

    for _ in range(len(items) + 1):
        improved = False
        for r, row in enumerate(order):
            if is_row[r]:
                continue
            for i in range(len(row) - 1):
                before = local(r)
                row[i], row[i + 1] = row[i + 1], row[i]
                if local(r) < before:
                    improved = True
                else:
                    row[i], row[i + 1] = row[i + 1], row[i]
        if not improved:
            return


# ----- coordinates ------------------------------------------------------------------------------


def _isotonic(targets: list[float], weights: list[float]) -> list[float]:
    blocks: list[list[float]] = []
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


def _cross(items: list[_Item], order: list[list[int]], d: str, node_gap: float, row_gap: float,
           lateral: set[frozenset[int]], is_row: list[bool], passes: int = 12) -> None:
    offsets: list[list[float]] = []
    for r, row in enumerate(order):
        offs, at = [], 0.0
        for i, key in enumerate(row):
            if i:
                a, b = items[row[i - 1]], items[key]
                gap = node_gap if a.node is not None and b.node is not None else node_gap / 2
                if frozenset((a.key, b.key)) in lateral:
                    gap = max(gap, row_gap)
                at += a.breadth(d) / 2 + gap + b.breadth(d) / 2
            offs.append(at)
        offsets.append(offs)
        for key, off in zip(row, offs):
            items[key].pos = off - at / 2

    partners: dict[int, list[int]] = {}
    for pair in lateral:
        a, b = sorted(pair)
        partners.setdefault(a, []).append(b)
        partners.setdefault(b, []).append(a)

    def settle(r: int, mode: str) -> None:
        row = order[r]
        where = {k: i for i, k in enumerate(row)}
        wanted, weights = [], []
        for i, key in enumerate(row):
            it = items[key]
            near = it.preds if mode == "down" else it.succs
            beside = [k for k in partners.get(key, []) if k in where]
            if near:
                wanted.append(sum(items[k].pos for k in near) / len(near))
                weights.append(len(near) * (2.0 if it.node is None else 1.0))
            elif beside:   # next to the node it is joined to along the rank (a satellite, a row)
                wanted.append(sum(items[k].pos - offsets[r][where[k]] for k in beside) / len(beside) + offsets[r][i])
                weights.append(1.0)
            else:
                wanted.append(it.pos)
                weights.append(0.05)
        fitted = _isotonic([w - o for w, o in zip(wanted, offsets[r])], weights)
        for key, y, off in zip(row, fitted, offsets[r]):
            items[key].pos = y + off

    depth = len(order)
    for p in range(passes):
        mode = "down" if p % 2 == 0 else "up"
        for r in (range(depth) if mode == "down" else range(depth - 1, -1, -1)):
            settle(r, mode)


# ----- routes -----------------------------------------------------------------------------------


def _ports(items: list[_Item], chains: list[list[int]], edges: Sequence[LayoutEdge], index: dict[str, int], d: str,
           spacing: float, lateral: list[int]) -> dict[tuple[int, int], float]:
    """Cross offset of each arc's port on the node at each end (``(arc, 0)`` the lower-rank end,
    ``(arc, 1)`` the higher): spread along the facing side, sorted by where the arc goes."""
    sides: dict[tuple[int, str], list[tuple[float, int, int]]] = {}
    for k, chain in enumerate(chains):
        if k in lateral:
            continue
        sides.setdefault((chain[0], "out"), []).append((items[chain[1]].pos, k, 0))
        sides.setdefault((chain[-1], "in"), []).append((items[chain[-2]].pos, k, 1))
    ports: dict[tuple[int, int], float] = {}
    for (key, _), entries in sides.items():
        entries.sort()
        count = len(entries)
        breadth = items[key].breadth(d)
        step = min(spacing, 0.7 * breadth / (count - 1)) if count > 1 else 0.0
        for i, (_, k, end) in enumerate(entries):
            ports[(k, end)] = (i - (count - 1) / 2) * step
    return ports


def _route(items: list[_Item], chain: list[int], k: int, ports: dict[tuple[int, int], float], mains: list[float],
           depths: list[float], d: str) -> tuple[list[Point], list[bool]]:
    """``(main, cross)`` points from the lower-rank end to the higher: straight across each
    rank's slab, S-curves in the gaps."""
    first, last = items[chain[0]], items[chain[-1]]
    assert first.node is not None and last.node is not None
    c0 = first.pos + ports[(k, 0)]
    c1 = last.pos + ports[(k, 1)]
    pts: list[Point] = [(mains[first.rank] + first.depth(d) / 2, c0)]
    curves: list[bool] = []

    def add(p: Point, curve: bool) -> None:
        if abs(p[0] - pts[-1][0]) < 1e-9 and abs(p[1] - pts[-1][1]) < 1e-9:
            return
        pts.append(p)
        curves.append(curve)

    add((mains[first.rank] + depths[first.rank] / 2, c0), False)
    for key in chain[1:-1]:
        it = items[key]
        add((mains[it.rank] - depths[it.rank] / 2, it.pos), True)
        add((mains[it.rank] + depths[it.rank] / 2, it.pos), False)
    add((mains[last.rank] - depths[last.rank] / 2, c1), True)
    add((mains[last.rank] - last.depth(d) / 2, c1), False)
    return pts, curves


def _lateral_route(items: list[_Item], order: list[list[int]], a: int, b: int, mains: list[float], depths: list[float],
                   gaps: list[float], d: str, lanes: dict[int, int]) -> tuple[list[Point], list[bool]]:
    """An arc along a membrane row: straight between neighbours; between non-neighbours out
    into the gap after the row (a lane of its own), across, and back."""
    ia, ib = items[a], items[b]
    r = ia.rank
    row = order[r]
    i, j = row.index(a), row.index(b)
    m = mains[r]
    if abs(i - j) == 1:
        sgn = 1.0 if ib.pos > ia.pos else -1.0
        if d == "LR":   # a vertical arc: towards the nodes' left ends, clear of the state badges on their right
            m -= 0.25 * min(ia.depth(d), ib.depth(d))
        return [(m, ia.pos + sgn * ia.breadth(d) / 2), (m, ib.pos - sgn * ib.breadth(d) / 2)], [False]
    lane = lanes.get(r, 0)
    lanes[r] = lane + 1
    gap = gaps[r] if r < len(gaps) else 0.6
    side = 1.0
    out = m + depths[r] / 2 + gap * (0.3 + 0.15 * lane)
    return ([(m + side * ia.depth(d) / 2, ia.pos), (out, ia.pos), (out, ib.pos), (m + side * ib.depth(d) / 2, ib.pos)],
            [False, False, False])


def _label_point(pts: list[Point], curves: list[bool]) -> Point:
    """The middle of the arc's first curved run (a gap), else of its longest run."""
    for (a, b), curve in zip(zip(pts, pts[1:]), curves):
        if curve:
            return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    best = max(zip(pts, pts[1:]), key=lambda ab: abs(ab[1][0] - ab[0][0]) + abs(ab[1][1] - ab[0][1]))
    return ((best[0][0] + best[1][0]) / 2, (best[0][1] + best[1][1]) / 2)


# ----- checks -----------------------------------------------------------------------------------


def s_curve(a: Point, b: Point, t: float, *, main_x: bool) -> Point:
    """The point at ``t`` of the cubic S-curve from ``a`` to ``b`` whose tangents at both ends
    run along the main axis (x when ``main_x``): it never leaves the gap between them."""
    if main_x:
        dm = b[0] - a[0]
        p1, p2 = (a[0] + dm / 2, a[1]), (b[0] - dm / 2, b[1])
    else:
        dm = b[1] - a[1]
        p1, p2 = (a[0], a[1] + dm / 2), (b[0], b[1] - dm / 2)
    u = 1 - t
    x = u ** 3 * a[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * b[0]
    y = u ** 3 * a[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * b[1]
    return (x, y)


def route_hits(layout: PathwayLayout, pad: float = 0.0) -> list[tuple[int, str]]:
    """``(route index, node id)`` for every route that passes through a node other than its
    own two ends (``pad``: grow each node box by this much)."""
    hits = []
    for k, route in enumerate(layout.routes):
        pts = samples(route, layout.direction)
        for node_id, p in layout.nodes.items():
            if node_id in (route.source, route.target):
                continue
            x0, y0, x1, y1 = p.box(pad)
            if any(x0 < x < x1 and y0 < y < y1 for x, y in pts):
                hits.append((k, node_id))
    return hits


def samples(route: Route, direction: str, steps: int = 12) -> list[Point]:
    """Points along a route as drawn, for ``direction`` (the main axis of its S-curves)."""
    out: list[Point] = [route.points[0]]
    for (a, b), curve in zip(zip(route.points, route.points[1:]), route.curves):
        for t in range(1, steps + 1):
            s = t / steps
            out.append(s_curve(a, b, s, main_x=direction == "LR") if curve else (a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s))
    return out


__all__ = ["BandBox", "LayoutEdge", "LayoutNode", "PathwayLayout", "Placed", "Route", "pathway_layout", "route_hits", "s_curve",
           "samples"]
