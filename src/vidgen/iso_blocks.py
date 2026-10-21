"""The geometry of an iso block diagram (DESIGN.md §90.6), the ``iso_diagram`` scene's model:
blocks, stacks of layers, group plates and connectors placed on a grid in the world of
:mod:`vidgen.world.iso_view`, and the shapes of :mod:`vidgen.cartoon.iso_drawing` they are
drawn with. Plain math, no manim: ``vidgen validate`` lays a diagram out to check it.

The grid: ``at: [column, row]`` is the back corner of an item's cells; columns run along the
world's ``x`` (to the viewer's lower right), rows along ``y`` (to the lower left), heights up.
An item fills its cells less :data:`CELL_INSET` on each side, so neighbours stay apart.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from vidgen.cartoon.iso_drawing import Line, Poly, Shape, Upright, box_shapes, shade, shape_bounds
from vidgen.cartoon.level_drawing import mix
from vidgen.world.iso_view import ISO_RISE, Box3, Point3, draw_order, iso_point

#: Block shapes and their default height (tile units) and footprint (cells).
SHAPES = ("box", "slab", "cylinder", "database", "tile")
ROUND = ("cylinder", "database")
SHAPE_HEIGHT = {"box": 0.8, "slab": 0.3, "cylinder": 0.9, "database": 0.9, "tile": 0.12}
SHAPE_SIZE = {"box": (1.0, 1.0), "slab": (2.0, 2.0), "cylinder": (1.0, 1.0), "database": (1.0, 1.0), "tile": (2.0, 2.0)}
#: How far an item stays inside its cells on each side (tile units).
CELL_INSET = 0.1
#: A stack's default footprint (cells) and the gap between its layers.
STACK_SIZE = (2.0, 2.0)
STACK_GAP = 0.12
#: Arranged in a row or column, a stack keeps this many more empty cells to its neighbours.
STACK_ROOM = 1.5
#: A group's plate: how far it reaches past its members and how thick it is.
PLATE_PAD = 0.3
PLATE_HEIGHT = 0.08
#: The floor reaches this far past everything, and is one rectangle when the union of what it
#: is under covers at least this share of the rectangle around it.
FLOOR_PAD = 0.45
FLOOR_FILL = 0.6
#: Connectors: a flat arrow's width and head, a pipe's width and height, dashes, and how far
#: a connector stays off the blocks it joins (tile units).
ARROW_WIDTH = 0.1
HEAD_LENGTH = 0.3
HEAD_WIDTH = 0.3
PIPE_WIDTH = 0.24
PIPE_HEIGHT = 0.16
DASH = 0.22
DASH_GAP = 0.14
CLEARANCE = 0.06
#: Two blocks whose sides share at least this much (tile units) are joined by a straight connector.
MIN_SHARED = 0.2
#: The shortest end segment of a connector left in view (tile units).
MIN_RUN = 0.45
#: How far apart the two connectors between the same blocks run (one each way), and how far
#: in front of the blocks in its way a connector goes round them.
TWIN_OFFSET = 0.16
DETOUR = 0.5
#: Connector styles.
EDGE_STYLES = ("solid", "dashed", "pipe")
#: How items are placed when none gives ``at`` (``zigzag``: two columns down the picture, for
#: a tall frame).
ARRANGEMENTS = ("row", "column", "grid", "zigzag")
#: Colours on the background: the floor and its lines (towards the text colour), a group's
#: plate (towards the group's colour); a block's outline, darker than the block.
FLOOR_TINT = 0.05
FLOOR_LINE_TINT = 0.14
PLATE_TINT = 0.32
OUTLINE_SHADE = 0.55


@dataclass(frozen=True)
class Rect:
    """A rectangle on the floor (tile units): ``x0 .. x1`` by ``y0 .. y1``."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def grown(self, by: float) -> Rect:
        return Rect(self.x0 - by, self.y0 - by, self.x1 + by, self.y1 + by)

    def overlaps(self, other: Rect) -> bool:
        """Whether the two share an area (touching edges do not count)."""
        return min(self.x1, other.x1) - max(self.x0, other.x0) > 1e-6 and min(self.y1, other.y1) - max(self.y0, other.y0) > 1e-6

    def union(self, other: Rect) -> Rect:
        return Rect(min(self.x0, other.x0), min(self.y0, other.y0), max(self.x1, other.x1), max(self.y1, other.y1))


@dataclass(frozen=True)
class BlockSpec:
    """A block as written: its ``shape`` (:data:`SHAPES`), footprint ``size`` (cells) and
    ``height`` (tile units); ``None`` takes the shape's default (in a stack: the stack's footprint)."""

    id: str
    shape: str = "box"
    size: tuple[float, float] | None = None
    height: float | None = None


@dataclass(frozen=True)
class ItemSpec:
    """Something standing on the grid: one ``block``, or a stack of ``layers`` (bottom first)
    with a footprint ``size`` and ``gap`` between layers; ``at``: its back cell (column, row),
    ``None`` to be arranged."""

    id: str
    at: tuple[float, float] | None = None
    block: BlockSpec | None = None
    layers: tuple[BlockSpec, ...] = ()
    size: tuple[float, float] | None = None
    gap: float = STACK_GAP

    @property
    def is_stack(self) -> bool:
        return self.block is None

    def cells(self) -> tuple[float, float]:
        """The footprint in cells (columns, rows)."""
        if self.block is not None:
            return block_size(self.block)
        return self.size or STACK_SIZE


@dataclass(frozen=True)
class GroupSpec:
    """A group: a plate under its ``members`` (ids of items: blocks or stacks)."""

    id: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class EdgeSpec:
    """A connector from block (or stack) ``source`` to ``target``; ``style`` of :data:`EDGE_STYLES`."""

    source: str
    target: str
    style: str = "solid"


@dataclass(frozen=True)
class PlacedBlock:
    """A block in the world: its ``box`` (a cylinder's is the square around it), the stack it is
    a layer of (``level`` from 0 at the bottom) and the group plate it stands on."""

    id: str
    shape: str
    box: Box3
    stack: str | None = None
    level: int = 0
    group: str | None = None

    def rect(self) -> Rect:
        return Rect(self.box.x0, self.box.y0, self.box.x1, self.box.y1)


@dataclass(frozen=True)
class PlacedStack:
    """A stack in the world: its footprint ``rect``, the height it stands on and its layers
    (block ids, bottom first)."""

    id: str
    rect: Rect
    z0: float
    layers: tuple[str, ...]
    gap: float
    group: str | None = None


@dataclass(frozen=True)
class PlacedEdge:
    """A connector: its path on the floor (world points at one height, from the source's side to
    the target's) and ``style``."""

    source: str
    target: str
    style: str
    points: tuple[Point3, ...]

    def ref(self) -> str:
        return f"{self.source}->{self.target}"

    def length(self) -> float:
        return sum(_distance(a, b) for a, b in zip(self.points, self.points[1:]))

    def samples(self, step: float) -> list[Point3]:
        """Points along the path about ``step`` apart, both ends included."""
        total = self.length()
        count = max(1, math.ceil(total / step))
        return [cut_path(self.points, 0.0, total * k / count)[-1] if k else self.points[0] for k in range(count + 1)]

    def longest(self) -> tuple[Point3, Point3]:
        """The ends of the path's longest segment (the first of equal ones)."""
        return max(zip(self.points, self.points[1:]), key=lambda pair: _distance(*pair))

    def midpoint(self) -> Point3:
        """The middle of the path's longest segment (where its label goes)."""
        a, b = self.longest()
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


@dataclass
class IsoDiagramLayout:
    """A laid-out diagram: blocks (stack layers too) by id, stacks, group plates, connectors, the
    floor under everything (the union of these rectangles: each item, plate and connector
    segment and :data:`FLOOR_PAD` around it) and each item's footprint."""

    blocks: dict[str, PlacedBlock]
    stacks: dict[str, PlacedStack]
    plates: dict[str, Box3]
    edges: list[PlacedEdge]
    floor: tuple[Rect, ...]
    items: dict[str, Rect] = field(default_factory=dict)

    def end_rect(self, name: str) -> Rect:
        """The footprint a connector to block or stack ``name`` reaches (a layer's: its stack's)."""
        if name in self.stacks:
            return self.stacks[name].rect
        block = self.blocks[name]
        return self.stacks[block.stack].rect if block.stack else block.rect()

    def ground(self, name: str) -> float:
        """The height block or stack ``name`` stands on (a plate's top, or the floor)."""
        group = self.stacks[name].group if name in self.stacks else self.blocks[name].group
        return PLATE_HEIGHT if group else 0.0

    def order(self) -> list[tuple[str, int]]:
        """What stands on the floor, back to front (:func:`draw_order`): ``("block", id)`` and
        ``("pipe", k)`` for each segment ``k`` of :meth:`pipe_boxes` (connectors and plates lie
        under them and are drawn first)."""
        pieces: list[tuple[str, object]] = [("block", name) for name in self.blocks]
        boxes = [b.box for b in self.blocks.values()]
        for k, box in enumerate(self.pipe_boxes()):
            pieces.append(("pipe", k))
            boxes.append(box)
        return [pieces[i] for i in draw_order(boxes)]  # type: ignore[misc]

    def pipe_boxes(self) -> list[Box3]:
        """Every pipe segment's box, connectors in order."""
        return [box for edge in self.edges if edge.style == "pipe" for box in pipe_segments(edge)]


@dataclass
class DiagramShapes:
    """The shapes a laid-out diagram is drawn with, by part: the floor, each group's plate, each
    flat connector's arrow (by connector index), each block, and each pipe segment (in
    :meth:`IsoDiagramLayout.order`'s numbering, with its connector's index)."""

    floor: list[Shape]
    plates: dict[str, list[Shape]]
    arrows: dict[int, list[Shape]]
    blocks: dict[str, list[Shape]]
    pipes: list[tuple[int, list[Shape]]]

    def all(self) -> list[Shape]:
        return [*self.floor, *[s for v in self.plates.values() for s in v], *[s for v in self.arrows.values() for s in v],
                *[s for v in self.blocks.values() for s in v], *[s for _, v in self.pipes for s in v]]

    def bounds(self) -> tuple[float, float, float, float]:
        """``(left, top, right, bottom)`` (tile widths) of everything on the picture."""
        found = [shape_bounds(s) for s in self.all()]
        return min(b[0] for b in found), min(b[1] for b in found), max(b[2] for b in found), max(b[3] for b in found)


def block_size(block: BlockSpec) -> tuple[float, float]:
    """A block's footprint in cells (a cylinder's is square)."""
    w, d = block.size or SHAPE_SIZE[block.shape]
    if block.shape in ROUND and block.size is not None:
        w = d = min(w, d)
    return w, d


def block_height(block: BlockSpec) -> float:
    return block.height if block.height is not None else SHAPE_HEIGHT[block.shape]


def arrange(items: Sequence[ItemSpec], how: str = "row", columns: int | None = None, spacing: float = 1.0) -> list[tuple[float, float]]:
    """``at`` for each item placed by ``how`` (:data:`ARRANGEMENTS`) in order with ``spacing``
    cells between them (next to a stack in a row or column :data:`STACK_ROOM` more), each
    centred across its row or column (in a ``zigzag``: in its cell of the largest item's size)."""
    sizes = [item.cells() for item in items]
    if how == "zigzag":   # right, then down-left, right...: two columns down the picture
        step_x = max(w for w, _ in sizes) + spacing
        step_y = max(d for _, d in sizes) + spacing
        return [((k + 1) // 2 * step_x + (step_x - spacing - w) / 2, k // 2 * step_y + (step_y - spacing - d) / 2)
                for k, (w, d) in enumerate(sizes)]
    # in a row or column a stack keeps STACK_ROOM more cells to each neighbour, for its layers' labels
    gaps = [spacing + (STACK_ROOM if a.is_stack or b.is_stack else 0.0) for a, b in zip(items, items[1:])] + [0.0]
    if how == "row":
        depth = max(d for _, d in sizes)
        at, x = [], 0.0
        for (w, d), gap in zip(sizes, gaps):
            at.append((x, (depth - d) / 2))
            x += w + gap
        return at
    if how == "column":
        width = max(w for w, _ in sizes)
        at, y = [], 0.0
        for (w, d), gap in zip(sizes, gaps):
            at.append(((width - w) / 2, y))
            y += d + gap
        return at
    cols = columns or max(1, math.ceil(math.sqrt(len(items))))
    widths = [max(sizes[k][0] for k in range(c, len(items), cols)) for c in range(min(cols, len(items)))]
    rows = math.ceil(len(items) / cols)
    depths = [max(sizes[k][1] for k in range(r * cols, min((r + 1) * cols, len(items)))) for r in range(rows)]
    at = []
    for k, (w, d) in enumerate(sizes):
        r, c = divmod(k, cols)
        x = sum(widths[:c]) + c * spacing + (widths[c] - w) / 2
        y = sum(depths[:r]) + r * spacing + (depths[r] - d) / 2
        at.append((x, y))
    return at


def layout_iso_diagram(items: Sequence[ItemSpec], groups: Sequence[GroupSpec] = (), edges: Sequence[EdgeSpec] = (), *,
                       how: str = "row", columns: int | None = None, spacing: float = 1.0) -> IsoDiagramLayout:
    """Place ``items`` (at their ``at``, or all arranged by ``how`` when none gives one), lift
    the members of ``groups`` onto plates and route ``edges`` along the grid. Raises
    ``ValueError`` naming the problem: items given ``at`` and not, overlapping items, a block
    standing on a group's plate without being a member, unknown or repeated names."""
    placed_at = [item.at for item in items]
    if any(a is None for a in placed_at):
        if any(a is not None for a in placed_at):
            missing = [item.id for item in items if item.at is None]
            raise ValueError(f"some blocks and stacks have 'at' and some do not (without one: {', '.join(missing[:4])}); "
                             "give every one an 'at: [column, row]', or none and let 'arrange' place them")
        placed_at = arrange(items, how, columns, spacing)  # type: ignore[assignment]
    member_of: dict[str, str] = {}
    known_items = {item.id for item in items}
    for group in groups:
        for member in group.members:
            if member not in known_items:
                raise ValueError(f"group '{group.id}': '{member}' is not a block or stack of the diagram"
                                 " (a group holds whole blocks and stacks, not a stack's layers)")
            if member in member_of:
                raise ValueError(f"'{member}' is in two groups ('{member_of[member]}' and '{group.id}'); a block stands on one plate")
            member_of[member] = group.id
    cells: dict[str, Rect] = {}
    for item, (x, y) in zip(items, placed_at):  # type: ignore[misc]
        w, d = item.cells()
        cells[item.id] = Rect(x, y, x + w, y + d)
    names = list(cells)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if cells[a].overlaps(cells[b]):
                raise ValueError(f"'{a}' and '{b}' overlap on the grid; move one with 'at: [column, row]' "
                                 "(a block fills its cells from 'at' by its 'size'), or put one on the other with a stack")
    blocks: dict[str, PlacedBlock] = {}
    stacks: dict[str, PlacedStack] = {}
    rects: dict[str, Rect] = {}
    for item in items:
        rect = cells[item.id].grown(-CELL_INSET)
        rects[item.id] = rect
        group = member_of.get(item.id)
        z = PLATE_HEIGHT if group else 0.0
        if item.block is not None:
            blocks[item.id] = PlacedBlock(item.id, item.block.shape, Box3(rect.x0, rect.y0, z, rect.x1, rect.y1, z + block_height(item.block)), group=group)
            continue
        for level, layer in enumerate(item.layers):
            box = layer_box(rect, layer, z)
            blocks[layer.id] = PlacedBlock(layer.id, layer.shape, box, item.id, level, group)
            z = box.z1 + item.gap
        stacks[item.id] = PlacedStack(item.id, rect, PLATE_HEIGHT if group else 0.0, tuple(layer.id for layer in item.layers), item.gap, group)
    plates: dict[str, Box3] = {}
    for group in groups:
        if not group.members:
            continue
        area = rects[group.members[0]]
        for member in group.members[1:]:
            area = area.union(rects[member])
        area = area.grown(PLATE_PAD)
        for other, rect in rects.items():
            if member_of.get(other) != group.id and rect.overlaps(area):
                raise ValueError(f"'{other}' stands where group '{group.id}''s plate lies (the plate covers its members and a little more); "
                                 f"add '{other}' to the group's blocks or move it away")
        for name, plate in plates.items():
            if Rect(plate.x0, plate.y0, plate.x1, plate.y1).overlaps(area):
                raise ValueError(f"the plates of groups '{name}' and '{group.id}' overlap; move their blocks apart (groups do not nest)")
        plates[group.id] = Box3(area.x0, area.y0, 0.0, area.x1, area.y1, PLATE_HEIGHT)
    layout = IsoDiagramLayout(blocks, stacks, plates, [], (), rects)
    layout.edges = route_edges(layout, edges)
    under = [*rects.values(), *[Rect(p.x0, p.y0, p.x1, p.y1) for p in plates.values()]]
    for edge in layout.edges:
        for a, b in zip(edge.points, edge.points[1:]):
            under.append(Rect(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
    layout.floor = _floor(tuple(r.grown(FLOOR_PAD) for r in under))
    return layout


def slant(items: Sequence[ItemSpec], along: str) -> list[ItemSpec]:
    """``items`` (all with ``at``) on a slanted grid: each moves along the other axis by how far
    its middle lies along ``along`` (``x`` or ``y``), so that axis runs straight down the
    picture (the view's ``x = y`` diagonal). A row along ``x`` becomes a column down a tall frame;
    neighbours keep their order and sides."""
    middles = [(item.at[0] + item.cells()[0] / 2) if along == "x" else (item.at[1] + item.cells()[1] / 2) for item in items]  # type: ignore[index]
    low = min(middles)
    out = []
    for item, middle in zip(items, middles):
        x, y = item.at  # type: ignore[misc]
        out.append(replace(item, at=(x, y + middle - low) if along == "x" else (x + middle - low, y)))
    return out


def picture_size(layout: IsoDiagramLayout) -> tuple[float, float]:
    """Width and height (tile widths) of ``layout``'s blocks and floor on the picture."""
    points = [p for b in layout.blocks.values() for p in block_outline(b)]
    points += [iso_point(x, y) for r in layout.floor for x in (r.x0, r.x1) for y in (r.y0, r.y1)]
    us, vs = [p[0] for p in points], [p[1] for p in points]
    return max(us) - min(us), max(vs) - min(vs)


def _floor(rects: tuple[Rect, ...]) -> tuple[Rect, ...]:
    """The floor's rectangles: the rectangle around ``rects`` when their union covers at least
    :data:`FLOOR_FILL` of it (a ragged edge would look like a mistake), else ``rects`` (a
    zigzag's floor follows its steps)."""
    box = rects[0]
    for rect in rects[1:]:
        box = box.union(rect)
    cover = _Cover(rects)
    area = sum((cover.xs[i + 1] - cover.xs[i]) * (cover.ys[j + 1] - cover.ys[j])
               for i in range(len(cover.xs) - 1) for j in range(len(cover.ys) - 1) if cover.inside[i][j])
    return (box,) if area >= FLOOR_FILL * (box.x1 - box.x0) * (box.y1 - box.y0) else rects


def layer_box(rect: Rect, layer: BlockSpec, z: float) -> Box3:
    """A stack layer's box on the stack's footprint ``rect`` from height ``z`` (a cylinder layer:
    the largest square inside it, centred)."""
    x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
    if layer.shape in ROUND:
        side = min(x1 - x0, y1 - y0)
        x0, y0 = rect.cx - side / 2, rect.cy - side / 2
        x1, y1 = x0 + side, y0 + side
    return Box3(x0, y0, z, x1, y1, z + block_height(layer))


def route_edges(layout: IsoDiagramLayout, edges: Sequence[EdgeSpec]) -> list[PlacedEdge]:
    """Each connector's path along the grid (:func:`route`), one height for the whole path (the
    higher of the grounds its ends stand on); two connectors between the same ends (one each
    way) run side by side."""
    pairs = {(e.source, e.target) for e in edges}
    out: list[PlacedEdge] = []
    for edge in edges:
        a, b = layout.end_rect(edge.source), layout.end_rect(edge.target)
        if a == b:
            raise ValueError(f"connector {edge.source} -> {edge.target}: both are in one stack; its layers touch, so nothing is drawn between them")
        twin = (edge.target, edge.source) in pairs
        ends = {_item_of(layout, edge.source), _item_of(layout, edge.target)}
        obstacles = [r for name, r in layout.items.items() if name not in ends]
        heights = (_item_height(layout, edge.source), _item_height(layout, edge.target))
        round_ends = (_is_round(layout, edge.source), _is_round(layout, edge.target))
        path = route(a, b, obstacles, twin=twin, heights=heights, round_ends=round_ends)
        z = max(layout.ground(edge.source), layout.ground(edge.target)) + 0.01
        out.append(PlacedEdge(edge.source, edge.target, edge.style, tuple((x, y, z) for x, y in path)))
    return out


def _item_height(layout: IsoDiagramLayout, name: str) -> float:
    """How high the item block or stack ``name`` belongs to stands above its ground."""
    item = _item_of(layout, name)
    if item in layout.stacks:
        stack = layout.stacks[item]
        return layout.blocks[stack.layers[-1]].box.z1 - stack.z0
    box = layout.blocks[item].box
    return box.z1 - box.z0


def _is_round(layout: IsoDiagramLayout, name: str) -> bool:
    """Whether the item block or stack ``name`` belongs to is round (cylinders all the way up)."""
    item = _item_of(layout, name)
    layers = layout.stacks[item].layers if item in layout.stacks else (item,)
    return all(layout.blocks[layer].shape in ROUND for layer in layers)


def _item_of(layout: IsoDiagramLayout, name: str) -> str:
    """The item (block or stack) block or stack ``name`` belongs to."""
    if name in layout.stacks:
        return name
    return layout.blocks[name].stack or name


def route(a: Rect, b: Rect, obstacles: Sequence[Rect] = (), *, twin: bool = False,
          heights: tuple[float, float] = (0.0, 0.0), round_ends: tuple[bool, bool] = (False, False)) -> list[tuple[float, float]]:
    """A path along the grid from ``a``'s side to ``b``'s: straight when their sides face each
    other over at least :data:`MIN_SHARED` (round the front of the ``obstacles`` in its way, at
    :data:`DETOUR` past them, when that crosses fewer), else one turn, whichever of the two
    crosses fewer (ties: along ``x`` first). ``twin``: one of two connectors between the same
    rectangles, shifted aside (each to its own right). Its ends stay :data:`CLEARANCE` off the
    sides (off a cylinder's round side with ``round_ends``), and off a side the view cannot see
    (the back ones, at ``x0`` and ``y0``) as far as the block (``heights``: of ``a`` and ``b``)
    hides the floor there (:func:`hidden_run`), so the arrow's tip shows where it meets the
    block's outline."""
    shift = TWIN_OFFSET / 2 if twin else 0.0
    low, high = max(a.y0, b.y0), min(a.y1, b.y1)
    if high - low >= MIN_SHARED and (b.x0 >= a.x1 or a.x0 >= b.x1):
        forward = b.x0 >= a.x1
        y = (low + high) / 2 + (shift if forward else -shift)
        path = [(a.x1, y), (b.x0, y)] if forward else [(a.x0, y), (b.x1, y)]
        lane = max(r.y1 for r in [a, b, *_crossed(path, obstacles)]) + DETOUR + shift
        path = min([path, [(a.cx, a.y1), (a.cx, lane), (b.cx, lane), (b.cx, b.y1)]], key=lambda p: _crossings(p, obstacles))
    else:
        low, high = max(a.x0, b.x0), min(a.x1, b.x1)
        if high - low >= MIN_SHARED and (b.y0 >= a.y1 or a.y0 >= b.y1):
            forward = b.y0 >= a.y1
            x = (low + high) / 2 + (-shift if forward else shift)
            path = [(x, a.y1), (x, b.y0)] if forward else [(x, a.y0), (x, b.y1)]
            lane = max(r.x1 for r in [a, b, *_crossed(path, obstacles)]) + DETOUR + shift
            path = min([path, [(a.x1, a.cy), (lane, a.cy), (lane, b.cy), (b.x1, b.cy)]], key=lambda p: _crossings(p, obstacles))
        else:
            sx = 1.0 if b.cx > a.cx else -1.0
            sy = 1.0 if b.cy > a.cy else -1.0
            x_first = [(a.x1 if sx > 0 else a.x0, a.cy), (b.cx, a.cy), (b.cx, b.y0 if sy > 0 else b.y1)]
            y_first = [(a.cx, a.y1 if sy > 0 else a.y0), (a.cx, b.cy), (b.x0 if sx > 0 else b.x1, b.cy)]
            options = [x_first, y_first]
            if twin:  # the other way round runs the other turn, so the two stay apart
                options = [y_first, x_first] if sx * sy > 0 else options
            path = min(options, key=lambda p: _crossings(p, obstacles))
    if round_ends[0]:
        path[0] = _on_circle(path[0], path[1], a)
    if round_ends[1]:
        path[-1] = _on_circle(path[-1], path[-2], b)
    return _trimmed(path, (a, b), heights, round_ends)


def _on_circle(end: tuple[float, float], toward: tuple[float, float], rect: Rect) -> tuple[float, float]:
    """``end`` (on a side of ``rect``) moved along the path onto the circle inside ``rect``."""
    r = min(rect.x1 - rect.x0, rect.y1 - rect.y0) / 2
    if abs(toward[0] - end[0]) >= abs(toward[1] - end[1]):   # the path leaves along x
        reach = math.sqrt(max(r * r - (end[1] - rect.cy) ** 2, 0.0))
        return (rect.cx + math.copysign(reach, toward[0] - end[0]), end[1])
    reach = math.sqrt(max(r * r - (end[0] - rect.cx) ** 2, 0.0))
    return (end[0], rect.cy + math.copysign(reach, toward[1] - end[1]))


def hidden_run(rect: Rect, height: float, direction: tuple[float, float], at: tuple[float, float], round_end: bool = False) -> float:
    """How far along the floor from the back side of a block on ``rect``, ``height`` high, a
    connector there (at point ``at`` of that side, running away from it the way ``direction``
    points) is hidden behind the block: the back sides are at ``x0`` (left on the picture) and
    ``y0`` (right); nothing hides a connector at a front side. ``round_end``: the block is the
    cylinder inside ``rect`` and ``at`` is on its side."""
    rise = 2 * height * ISO_RISE   # the floor behind a block shows above its top's back edges past this
    if direction[0] < -0.5:   # away from the x0 side
        across = at[1] - rect.cy
        size = rect.y1 - rect.cy
    elif direction[1] < -0.5:   # away from the y0 side
        across = at[0] - rect.cx
        size = rect.x1 - rect.cx
    else:
        return 0.0
    if round_end:   # the outline is the circle's widest point on the picture, r·√2 off the middle
        hidden = size * math.sqrt(2) - across - math.sqrt(max(size * size - across * across, 0.0))
    else:
        hidden = size - across
    return max(0.0, min(hidden, rise))


def _trimmed(path: list[tuple[float, float]], ends: tuple[Rect, Rect], heights: tuple[float, float],
             round_ends: tuple[bool, bool]) -> list[tuple[float, float]]:
    """``path`` with its ends moved off ``ends`` (:func:`route`), each end segment keeping at
    least :data:`MIN_RUN` (the hidden part shortened first)."""
    out = list(path)
    first = _unit((*path[0], 0.0), (*path[1], 0.0))
    last = _unit((*path[-2], 0.0), (*path[-1], 0.0))
    start = hidden_run(ends[0], heights[0], first, path[0], round_ends[0])
    end = hidden_run(ends[1], heights[1], (-last[0], -last[1]), path[-1], round_ends[1])
    if len(path) == 2:
        room = math.dist(path[0], path[1]) - 2 * CLEARANCE - MIN_RUN
        if start + end > room:
            share = max(room, 0.0) / (start + end)
            start, end = start * share, end * share
    else:
        start = min(start, max(math.dist(path[0], path[1]) - CLEARANCE - MIN_RUN, 0.0))
        end = min(end, max(math.dist(path[-2], path[-1]) - CLEARANCE - MIN_RUN, 0.0))
    out[0] = (path[0][0] + first[0] * (CLEARANCE + start), path[0][1] + first[1] * (CLEARANCE + start))
    out[-1] = (path[-1][0] - last[0] * (CLEARANCE + end), path[-1][1] - last[1] * (CLEARANCE + end))
    return out


def _crossed(path: Sequence[tuple[float, float]], obstacles: Sequence[Rect]) -> list[Rect]:
    """The ``obstacles`` the axis-aligned ``path`` runs through."""
    found = []
    for rect in obstacles:
        for (x0, y0), (x1, y1) in zip(path, path[1:]):
            if Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)).grown(0.01).overlaps(rect):
                found.append(rect)
                break
    return found


def _crossings(path: Sequence[tuple[float, float]], obstacles: Sequence[Rect]) -> int:
    """How many of ``obstacles`` the axis-aligned ``path`` runs through."""
    return len(_crossed(path, obstacles))


def _distance(a: Point3, b: Point3) -> float:
    return math.dist(a, b)


def _unit(a: Point3, b: Point3) -> tuple[float, float]:
    length = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    return (b[0] - a[0]) / length, (b[1] - a[1]) / length


def cut_path(points: Sequence[Point3], start: float, end: float) -> list[Point3]:
    """The part of the polyline ``points`` from arc length ``start`` to ``end``."""
    out: list[Point3] = []
    walked = 0.0
    for a, b in zip(points, points[1:]):
        length = _distance(a, b)
        lo, hi = max(start - walked, 0.0), min(end - walked, length)
        if hi > lo and length > 0:
            p = tuple(a[i] + (b[i] - a[i]) * lo / length for i in range(3))
            q = tuple(a[i] + (b[i] - a[i]) * hi / length for i in range(3))
            if not out:
                out.append(p)  # type: ignore[arg-type]
            out.append(q)  # type: ignore[arg-type]
        walked += length
    return out


def ribbon(points: Sequence[Point3], width: float, fill: str) -> list[Shape]:
    """A flat band ``width`` wide along ``points`` (a rectangle per segment, reaching half the
    width past an inner corner so the corner is filled)."""
    shapes: list[Shape] = []
    last = len(points) - 2
    for k, (a, b) in enumerate(zip(points, points[1:])):
        dx, dy = _unit(a, b)
        back = width / 2 if k > 0 else 0.0
        ahead = width / 2 if k < last else 0.0
        p = (a[0] - dx * back, a[1] - dy * back)
        q = (b[0] + dx * ahead, b[1] + dy * ahead)
        nx, ny = -dy * width / 2, dx * width / 2
        z = a[2]
        shapes.append(Poly(((p[0] + nx, p[1] + ny, z), (q[0] + nx, q[1] + ny, z), (q[0] - nx, q[1] - ny, z), (p[0] - nx, p[1] - ny, z)), fill, False))
    return shapes


def arrow_shapes(edge: PlacedEdge, fill: str) -> list[Shape]:
    """A flat arrow along the connector (dashed: in dashes), its head at the target."""
    points = list(edge.points)
    total = edge.length()
    head = min(HEAD_LENGTH, total * 0.6)
    body_end = total - head * 0.9
    shapes: list[Shape] = []
    if edge.style == "dashed":
        at = 0.0
        while at < body_end - 1e-6:
            piece = cut_path(points, at, min(at + DASH, body_end))
            if len(piece) >= 2:
                shapes += ribbon(piece, ARROW_WIDTH, fill)
            at += DASH + DASH_GAP
    elif body_end > 0:
        shapes += ribbon(cut_path(points, 0.0, body_end), ARROW_WIDTH, fill)
    tip, before = points[-1], cut_path(points, total - head, total)[0]
    dx, dy = _unit(before, tip)
    nx, ny = -dy * HEAD_WIDTH / 2, dx * HEAD_WIDTH / 2
    z = tip[2]
    shapes.append(Poly(((tip[0], tip[1], z), (before[0] + nx, before[1] + ny, z), (before[0] - nx, before[1] - ny, z)), fill, False))
    return shapes


def pipe_segments(edge: PlacedEdge) -> list[Box3]:
    """The boxes of a pipe along the connector, one per segment (each reaching half the pipe's
    width past an inner corner)."""
    boxes: list[Box3] = []
    points = edge.points
    last = len(points) - 2
    half = PIPE_WIDTH / 2
    for k, (a, b) in enumerate(zip(points, points[1:])):
        dx, dy = _unit(a, b)
        back, ahead = (half if k > 0 else 0.0), (half if k < last else 0.0)
        p = (a[0] - dx * back, a[1] - dy * back)
        q = (b[0] + dx * ahead, b[1] + dy * ahead)
        x0, x1 = sorted((p[0], q[0]))
        y0, y1 = sorted((p[1], q[1]))
        if abs(dx) >= abs(dy):   # along x: the pipe's width across y
            y0, y1 = (y0 + y1) / 2 - half, (y0 + y1) / 2 + half
        else:
            x0, x1 = (x0 + x1) / 2 - half, (x0 + x1) / 2 + half
        boxes.append(Box3(x0, y0, a[2], x1, y1, a[2] + PIPE_HEIGHT))
    return boxes


def box_faces(box: Box3, fill: str, *, lift: float = 0.0) -> list[Shape]:
    """A box's visible faces (:func:`box_shapes`), raised ``lift`` tile units."""
    return box_shapes(box.x0, box.y0, box.z0 + lift, box.x1, box.y1, box.z1 + lift, fill)


def block_shapes(block: PlacedBlock, fill: str, *, lift: float = 0.0) -> list[Shape]:
    """The shapes of ``block`` in colour ``fill``, raised ``lift`` tile units: a box's faces,
    or an upright cylinder (a ``database`` with two bands round it)."""
    box = block.box
    if block.shape not in ROUND:
        return box_faces(box, fill, lift=lift)
    cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    radius = min(box.x1 - box.x0, box.y1 - box.y0) / 2
    z0, z1 = box.z0 + lift, box.z1 + lift
    shapes: list[Shape] = [Upright(cx, cy, z0, z1, radius, fill)]
    if block.shape == "database":
        for share in (1 / 3, 2 / 3):
            shapes.append(Line(front_arc(cx, cy, z0 + (z1 - z0) * share, radius), shade(fill, 0.35), 1.0))
    return shapes


def front_arc(cx: float, cy: float, z: float, radius: float, samples: int = 24) -> tuple[Point3, ...]:
    """The half of a level circle facing the viewer (from its left to its right on the picture)."""
    # on the picture the circle's left end is at angle 135° (x - y smallest), its front at 45°
    return tuple((cx + radius * math.cos(math.radians(a)), cy + radius * math.sin(math.radians(a)), z)
                 for a in (135 - 180 * k / samples for k in range(samples + 1)))


def plate_shapes(plate: Box3, fill: str) -> list[Shape]:
    """A group's plate."""
    return box_faces(plate, fill)


def floor_shapes(floor: Sequence[Rect], fill: str, line: str) -> list[Shape]:
    """The floor: the union of the rectangles ``floor`` (flat polygons, one per outline) with the
    grid's lines over it (every whole cell)."""
    cover = _Cover(floor)
    shapes: list[Shape] = [Poly(tuple((x, y, 0.0) for x, y in loop), fill, False) for loop in cover.outlines()]
    shapes += [Line(((a[0], a[1], 0.0), (b[0], b[1], 0.0)), line, 0.6) for a, b in cover.grid_lines()]
    return shapes


class _Cover:
    """The union of rectangles on the floor, on the grid of their own edges (each cell of that
    grid inside one rectangle or outside all)."""

    def __init__(self, rects: Sequence[Rect]) -> None:
        self.xs = sorted({v for r in rects for v in (r.x0, r.x1)})
        self.ys = sorted({v for r in rects for v in (r.y0, r.y1)})
        self.inside = [[any(r.x0 <= (self.xs[i] + self.xs[i + 1]) / 2 <= r.x1 and r.y0 <= (self.ys[j] + self.ys[j + 1]) / 2 <= r.y1 for r in rects)
                        for j in range(len(self.ys) - 1)] for i in range(len(self.xs) - 1)]

    def covered(self, i: int, j: int) -> bool:
        return 0 <= i < len(self.inside) and 0 <= j < len(self.inside[0]) and self.inside[i][j]

    def outlines(self) -> list[list[tuple[float, float]]]:
        """The outer outlines (counter-clockwise in ``x``, ``y``), corners only; holes are left filled."""
        xs, ys = self.xs, self.ys
        edges: dict[tuple[float, float], list[tuple[float, float]]] = {}
        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                if not self.inside[i][j]:
                    continue
                corners = [(xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])]
                for k, (di, dj) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0))):
                    if not self.covered(i + di, j + dj):
                        edges.setdefault(corners[k], []).append(corners[(k + 1) % 4])
        loops: list[list[tuple[float, float]]] = []
        while edges:
            start = next(iter(edges))
            loop, point = [start], start
            while True:
                ahead = edges[point].pop()
                if not edges[point]:
                    del edges[point]
                if ahead == start:
                    break
                loop.append(ahead)
                point = ahead
            loop = _corners_only(loop)
            if _signed_area(loop) > 0:
                loops.append(loop)
        return loops

    def grid_lines(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """The whole-cell lines over the union, as segments (along ``x``, then along ``y``)."""
        out: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for y in range(math.ceil(self.ys[0] + 0.05), math.floor(self.ys[-1] - 0.05) + 1):
            rows = [j for j in range(len(self.ys) - 1) if self.ys[j] - 1e-9 <= y <= self.ys[j + 1] + 1e-9]
            out += [((a, y), (b, y)) for a, b in _runs(self.xs, [any(self.covered(i, j) for j in rows) for i in range(len(self.xs) - 1)])]
        for x in range(math.ceil(self.xs[0] + 0.05), math.floor(self.xs[-1] - 0.05) + 1):
            cols = [i for i in range(len(self.xs) - 1) if self.xs[i] - 1e-9 <= x <= self.xs[i + 1] + 1e-9]
            out += [((x, a), (x, b)) for a, b in _runs(self.ys, [any(self.covered(i, j) for i in cols) for j in range(len(self.ys) - 1)])]
        return out


def _runs(edges: Sequence[float], marks: Sequence[bool]) -> list[tuple[float, float]]:
    """The spans of consecutive marked cells (cell ``k`` from ``edges[k]`` to ``edges[k + 1]``)."""
    out: list[tuple[float, float]] = []
    start: float | None = None
    for k, mark in enumerate(marks):
        if mark and start is None:
            start = edges[k]
        if not mark and start is not None:
            out.append((start, edges[k]))
            start = None
    if start is not None:
        out.append((start, edges[len(marks)]))
    return out


def _corners_only(loop: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """``loop`` without the points that lie on a straight run."""
    out = []
    for k, p in enumerate(loop):
        a, b = loop[k - 1], loop[(k + 1) % len(loop)]
        if abs((p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0])) > 1e-9:
            out.append(p)
    return out


def _signed_area(loop: Sequence[tuple[float, float]]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(loop, [*loop[1:], loop[0]])) / 2


def top_point(block: PlacedBlock, lift: float = 0.0) -> tuple[float, float]:
    """The middle of ``block``'s top on the picture (tile widths)."""
    box = block.box
    return iso_point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2, box.z1 + lift)


def top_room(block: PlacedBlock) -> tuple[float, float]:
    """Width and height (tile widths) of the largest level rectangle inside ``block``'s top on
    the picture, at the shape's own proportions: half its diamond each way."""
    box = block.box
    w, d = box.x1 - box.x0, box.y1 - box.y0
    if block.shape in ROUND:
        w = d = min(w, d) * 0.9
    side = min(w, d)
    return side / 2 + abs(w - d) / 4, side / 4 + abs(w - d) / 8


def side_point(block: PlacedBlock, side: str, lift: float = 0.0) -> tuple[float, float]:
    """The middle of ``block``'s side face on the picture: ``right`` (the face at ``x1``) or
    ``left`` (at ``y1``)."""
    box = block.box
    z = (box.z0 + box.z1) / 2 + lift
    if side == "right":
        return iso_point(box.x1, (box.y0 + box.y1) / 2, z)
    return iso_point((box.x0 + box.x1) / 2, box.y1, z)


def box_outline(box: Box3, lift: float = 0.0) -> list[tuple[float, float]]:
    """The corners of ``box`` raised ``lift`` on the picture (tile widths, ``v`` down): their
    convex hull is the box's outline as seen."""
    return [iso_point(x, y, z + lift) for x, y, z in box.corners()]


def block_outline(block: PlacedBlock, lift: float = 0.0, samples: int = 24) -> list[tuple[float, float]]:
    """Points whose convex hull is ``block``'s outline on the picture (raised ``lift``): a
    box's corners, a cylinder's top and bottom ellipses."""
    box = block.box
    if block.shape not in ROUND:
        return box_outline(box, lift)
    cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    r = min(box.x1 - box.x0, box.y1 - box.y0) / 2
    return [iso_point(cx + r * math.cos(2 * math.pi * k / samples), cy + r * math.sin(2 * math.pi * k / samples), z + lift)
            for z in (box.z0, box.z1) for k in range(samples)]


def readable_ink(fill: str, dark: str, light: str) -> str:
    """``dark`` or ``light``, whichever reads better on ``fill`` (WCAG contrast)."""
    from vidgen.lint.color import contrast_ratio, hex_rgb   # here: the lint package registers its rules on import

    on = hex_rgb(fill)
    return dark if contrast_ratio(hex_rgb(dark), on) >= contrast_ratio(hex_rgb(light), on) else light


def outline_ink(fill: str) -> str:
    """The outline of a block, plate or pipe of colour ``fill``: a darker shade of it (on any
    background, unlike the cartoon's one ink)."""
    return shade(fill, OUTLINE_SHADE)


def diagram_shapes(layout: IsoDiagramLayout, block_colors: Mapping[str, str], edge_colors: Sequence[str], group_colors: Mapping[str, str],
                   *, floor: str, background: str, text: str) -> DiagramShapes:
    """The shapes of ``layout``: blocks in ``block_colors`` (by id), connectors in
    ``edge_colors`` (by index), plates tinted by ``group_colors`` on ``background``, and the
    ``floor`` (``grid``, ``plain`` or ``none``) a touch of ``text`` on it."""
    ground = []
    if floor != "none":
        ground = floor_shapes(layout.floor, mix(background, text, FLOOR_TINT), mix(background, text, FLOOR_LINE_TINT))
        if floor == "plain":
            ground = [s for s in ground if isinstance(s, Poly)]
    plates = {name: plate_shapes(box, mix(background, group_colors[name], PLATE_TINT)) for name, box in layout.plates.items()}
    arrows: dict[int, list[Shape]] = {}
    pipes: list[tuple[int, list[Shape]]] = []
    for k, edge in enumerate(layout.edges):
        if edge.style == "pipe":
            pipes += [(k, box_faces(box, edge_colors[k])) for box in pipe_segments(edge)]
        else:
            arrows[k] = arrow_shapes(edge, edge_colors[k])
    blocks = {name: block_shapes(block, block_colors[name]) for name, block in layout.blocks.items()}
    return DiagramShapes(ground, plates, arrows, blocks, pipes)


__all__ = [
    "ARRANGEMENTS",
    "EDGE_STYLES",
    "SHAPES",
    "BlockSpec",
    "DiagramShapes",
    "EdgeSpec",
    "GroupSpec",
    "IsoDiagramLayout",
    "ItemSpec",
    "PlacedBlock",
    "PlacedEdge",
    "PlacedStack",
    "Rect",
    "arrange",
    "arrow_shapes",
    "block_outline",
    "block_shapes",
    "box_outline",
    "diagram_shapes",
    "floor_shapes",
    "layout_iso_diagram",
    "outline_ink",
    "picture_size",
    "slant",
    "pipe_segments",
    "plate_shapes",
    "readable_ink",
    "route",
    "side_point",
    "top_point",
    "top_room",
]
