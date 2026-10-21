"""``iso_diagram``: a diagram of blocks in the isometric view (DESIGN.md §90.6): boxes, slabs,
cylinders and databases, flat tiles, stacks of layers and group plates on a grid, joined by
connectors along the grid, with flat labels that stay readable."""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .diagram import _ID, _unknown, edge_ref, parse_edges

log = logging.getLogger("vidgen.scenes")

BlockShape = Literal["box", "slab", "cylinder", "database", "tile"]
EdgeStyle = Literal["solid", "dashed", "pipe"]
Cells = tuple[float, float]


def _check_id(value: str) -> str:
    value = value.strip()
    if not _ID.match(value):
        raise ValueError(f"id {value!r}: use letters, digits, spaces, '_', '.' and '-' (no '->' or ':')")
    return value


def _check_cells(value: Cells | None, what: str, low: float) -> Cells | None:
    if value is not None and not all(low <= v <= 40 for v in value):
        raise ValueError(f"{what} {list(value)}: each number must be {low:g} to 40 cells")
    return value


class _Named(SceneParams):
    """A string shorthand is the id and the label."""

    also_accepts = (str,)
    text_shorthand = {str: ("field", "id")}
    text_defaults = {"label": "id"}

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"id": data} if isinstance(data, str) else data

    @field_validator("id", check_fields=False)
    @classmethod
    def _id(cls, value: str) -> str:
        return _check_id(value)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A plain string is also one (JSON Schema ``anyOf`` string | object)."""
        return {"anyOf": [{"type": "string", "minLength": 1}, handler(core_schema)]}


class IsoLayer(_Named):
    """A layer of a stack: ``{id, label?, shape?, height?, color?}`` (a plain string is its id and label)."""

    id: str
    """Name used by edges and targets (letters, digits, spaces, _ . -)."""
    label: TranslatableStr = ""
    """Text beside the layer (default: the id)."""
    shape: BlockShape = "slab"
    """slab (default), box, tile, cylinder or database; it covers the stack's footprint."""
    height: float | None = Field(default=None, gt=0, le=8)
    """Height in cells (default by shape: a slab 0.3)."""
    color: ThemeColor | None = None
    """Its colour (default: the stack's color, else the scene's block_color, or a term's colour)."""

    def text(self) -> str:
        return self.label or self.id


class IsoBlock(_Named):
    """A block on the grid: ``{id, label?, shape?, at?, size?, height?, color?}``, or a stack of
    ``layers`` (bottom up) with ``gap?`` and ``label_side?`` (a plain string is a block's id and
    label)."""

    id: str
    """Name used by edges, groups and targets (letters, digits, spaces, _ . -)."""
    label: TranslatableStr = ""
    """Text shown with the block (default: the id): on its top when it fits, else beside it; a stack's caption under it."""
    shape: BlockShape | None = None
    """box (default: 1x1, 0.8 high), slab (2x2, 0.3), cylinder (1x1, 0.9), database (a cylinder with bands) or tile (a flat 2x2 platform, 0.12); not on a stack."""
    layers: list[IsoLayer] | None = Field(default=None, min_length=1, max_length=12)
    """Makes it a stack: its layers FROM THE BOTTOM UP, each an id string or {id, label?, shape?, height?, color?} (a slab by default)."""
    at: Cells | None = None
    """[column, row] of its back cell on the grid: columns run to the lower right, rows to the lower left (give every block an 'at', or none)."""
    size: Cells | None = None
    """[columns, rows] of cells it covers (default by shape, a stack [2, 2]; a cylinder's is square)."""
    height: float | None = Field(default=None, gt=0, le=8)
    """Height in cells (default by shape; not on a stack: give its layers heights)."""
    gap: float | None = Field(default=None, ge=0, le=2)
    """A stack's space between layers (default 0.12 cells)."""
    label_side: Literal["auto", "left", "right"] | None = None
    """Where a stack's layer labels go: auto (default: the side away from the diagram's middle), left or right."""
    color: ThemeColor | None = None
    """Its colour (a stack's: its layers'; default: the scene's block_color, or a term's colour when its label is a term)."""

    @field_validator("at")
    @classmethod
    def _at(cls, value: Cells | None) -> Cells | None:
        return _check_cells(value, "at", 0)

    @field_validator("size")
    @classmethod
    def _size(cls, value: Cells | None) -> Cells | None:
        return _check_cells(value, "size", 0.5)

    @model_validator(mode="after")
    def _kind(self) -> "IsoBlock":
        if self.layers is not None:
            wrong = [name for name in ("shape", "height") if getattr(self, name) is not None]
            if wrong:
                raise ValueError(f"block {self.id!r} has layers, so it is a stack: give {' and '.join(wrong)} to its layers instead")
        else:
            wrong = [name for name in ("gap", "label_side") if getattr(self, name) is not None]
            if wrong:
                raise ValueError(f"block {self.id!r}: {' and '.join(wrong)} are for a stack (a block with 'layers'); add its layers or leave them out")
        return self

    @property
    def is_stack(self) -> bool:
        return self.layers is not None

    def text(self) -> str:
        """What the block shows: its label, else its id (a stack: as its caption)."""
        return self.label or self.id


class IsoGroup(SceneParams):
    """A group: ``{id, blocks, label?, color?}``, a plate under the blocks and stacks it lists."""

    id: str
    """Name used by targets (group:<id>)."""
    blocks: list[str] = Field(min_length=1)
    """Ids of the blocks and stacks on the plate (whole stacks, not their layers)."""
    label: TranslatableStr = ""
    """Optional caption by the plate."""
    color: ThemeColor | None = None
    """Plate tint (default: dim)."""

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _check_id(value)


class IsoEdge(SceneParams):
    """A connector: ``{from, to, label?, style?, color?}``, or the shorthand ``"a -> b: label"`` (``-->`` dashed)."""

    also_accepts = (str,)
    text_shorthand = {str: ("after", ":")}

    source: str = Field(alias="from")
    """Block or stack id the connector starts at."""
    to: str
    """Block or stack id it points to."""
    label: TranslatableStr = ""
    """Optional text on the connector."""
    style: EdgeStyle | None = None
    """solid (a flat arrow), dashed or pipe (a raised channel, no arrowhead); default: the scene's edge_style ('-->' is dashed)."""
    color: ThemeColor | None = None
    """Colour (default: the scene's edge_color)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if isinstance(data, str):
            edges = parse_edges(data)
            if len(edges) > 1:
                raise ValueError(f"{data!r} is a chain of {len(edges)} edges; list it under the scene's edges")
            return _scene_style(edges[0])
        return data

    @field_validator("source", "to")
    @classmethod
    def _ends(cls, value: str) -> str:
        return value.strip()

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """The shorthand string is also an edge (JSON Schema ``anyOf`` string | object)."""
        return {"anyOf": [{"type": "string", "pattern": "->"}, handler(core_schema)]}

    def ref(self) -> str:
        return edge_ref(self.source, self.to)


def _scene_style(edge: dict[str, Any]) -> dict[str, Any]:
    """A shorthand edge: ``->`` takes the scene's edge_style, ``-->`` is dashed."""
    if edge.get("style") == "solid":
        edge = {k: v for k, v in edge.items() if k != "style"}
    return edge


@dataclass
class _Label:
    """A label to place: whose (``kind``: block, layer, stack, group or edge; ``owner``: its id or
    connector ref) and its text."""

    kind: str
    owner: str
    text: Mobject


@dataclass
class _Placement:
    """Where the labels go at one scale: centres (picture origin at 0, 0), which sit on their
    block's top, leader lines, and the bounds of everything."""

    centres: dict[int, np.ndarray] = field(default_factory=dict)
    on_top: set[int] = field(default_factory=set)
    leaders: list[tuple[int, np.ndarray, np.ndarray]] = field(default_factory=list)
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class _Plan:
    scale: float
    labels: list[_Label]
    placement: _Placement
    fits: bool


@scene("iso_diagram")
class IsoDiagram(NarratedScene):
    """A diagram of blocks in the isometric view: boxes, slabs, cylinders and databases, flat
    tiles, stacks of layers (a layered architecture, a network's layers) and group plates on a
    grid, joined by connectors along the grid (flat arrows, dashed, or pipes). Labels stay flat
    and readable: on a block's top when they fit, else beside it on a plate; a stack's layers are
    labelled at its side. The diagram is fitted to the frame (16:9 and 9:16) and shown in the
    first beat.

    Action targets: ``heading``, ``block<N>`` (1-based: every block and layer in the order
    written, a stack's layers bottom up in its place), ``block:<id>``, ``stack:<id>``,
    ``group:<id>`` and ``edge:<from>-><to>``.
    """

    outro = 0.5
    target_patterns = ("heading", "block<N>", "block:<id>", "stack:<id>", "group:<id>", "edge:<from>-><to>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``heading`` (if any), ``block<N>`` and ``block:<id>`` per block and layer,
        ``stack:<id>``, ``group:<id>``, ``edge:<from>-><to>``."""
        names = ["heading"] if params.heading else []
        for i, (block_id, *_rest) in enumerate(params.all_blocks(), start=1):
            names += [f"block{i}", f"block:{block_id}"]
        names += [f"stack:{s.id}" for s in params.stacks()] + [f"group:{g.id}" for g in params.groups]
        return names + [f"edge:{e.ref()}" for e in params.edges]

    class Params(SceneParams):
        blocks: list[IsoBlock] = Field(min_length=1, max_length=30)
        """The blocks, in order: an id string, {id, label?, shape?, at?, size?, height?, color?}, or a stack {id, layers (bottom up), label?, at?, size?, gap?, label_side?, color?} (up to ~12 read well)."""
        groups: list[IsoGroup] = Field(default_factory=list, max_length=8)
        """Plates under blocks that belong together: {id, blocks, label?, color?}."""
        edges: list[IsoEdge] = Field(default_factory=list, max_length=40)
        """Connectors along the grid: 'a -> b', 'a -> b: label', 'a --> b' (dashed), chains 'a -> b -> c', or {from, to, label?, style?, color?}."""
        heading: TranslatableStr = ""
        """Optional heading above the diagram."""
        arrange: Literal["auto", "row", "column", "grid", "zigzag"] = "auto"
        """How blocks without 'at' are placed, in the order written: row (along the columns, to the lower right), column (along the rows, to the lower left), grid, zigzag (right, down-left, right...: two columns down a tall frame) or auto (row; zigzag in 9:16)."""
        columns: int | None = Field(default=None, ge=1, le=12)
        """Columns of the grid arrangement (default: about the square root of the count)."""
        spacing: float | None = Field(default=None, ge=0, le=6)
        """Empty cells between arranged blocks (default: 1; 2 in a zigzag, so labels fit above and below)."""
        floor: Literal["grid", "plain", "none"] = "grid"
        """The floor under the diagram: with grid lines, plain, or none."""
        block_color: Literal["palette"] | ThemeColor = "palette"
        """Colour of blocks without their own: 'palette' (one theme palette colour each) or one colour."""
        edge_style: EdgeStyle = "solid"
        """Connectors without their own style: solid (flat arrow), dashed or pipe."""
        edge_color: ThemeColor = "dim"
        """Connector colour."""
        label_color: ThemeColor = "text"
        """Label colour (a label on a block's top takes the ink that reads best on it)."""
        edge_label_color: ThemeColor = "dim"
        """Connector label colour."""
        heading_color: ThemeColor = "text"
        """Heading colour."""
        size: ThemeSize = "body"
        """Label size (reduced, not below the readable minimum, when space is short)."""
        edge_label_size: ThemeSize = "caption"
        """Connector label size (never below the readable minimum)."""
        heading_size: ThemeSize = "heading"
        """Heading size."""

        @field_validator("edges", mode="before")
        @classmethod
        def _chains(cls, value: Any) -> Any:
            if not isinstance(value, list):
                return value
            out: list[Any] = []
            for item in value:
                out += [_scene_style(e) for e in parse_edges(item)] if isinstance(item, str) else [item]
            return out

        @model_validator(mode="after")
        def _references(self) -> SceneParams:
            seen: dict[str, str] = {}
            for kind, name in [("stack" if b.is_stack else "block", b.id) for b in self.blocks] \
                    + [("layer", layer.id) for s in self.stacks() for layer in s.layers or ()]:
                if name in seen:
                    raise ValueError(f"the id {name!r} is used twice (a {seen[name]} and a {kind}); blocks, stacks and layers need different ids")
                seen[name] = kind
            groups: set[str] = set()
            items = [b.id for b in self.blocks]
            for group in self.groups:
                if group.id in groups:
                    raise ValueError(f"groups: the id {group.id!r} is used twice")
                groups.add(group.id)
                for member in group.blocks:
                    if seen.get(member) == "layer":
                        raise ValueError(f"group '{group.id}': {member!r} is a layer of a stack; list the stack instead")
                    if member not in items:
                        raise ValueError(f"group '{group.id}': {_unknown('block', member, items)}")
            refs: set[str] = set()
            for i, edge in enumerate(self.edges):
                for end in (edge.source, edge.to):
                    if end not in seen:
                        raise ValueError(f"edges[{i}] ({edge.source} -> {edge.to}): {_unknown('block', end, list(seen))}")
                if edge.source == edge.to:
                    raise ValueError(f"edges[{i}]: {edge.source!r} points to itself")
                if edge.ref() in refs:
                    raise ValueError(f"edges[{i}]: {edge.source} -> {edge.to} is listed twice")
                refs.add(edge.ref())
            for portrait in (False, True):   # raises ValueError on overlapping blocks, a block on another group's plate...
                self.layout(portrait)
            return self

        def stacks(self) -> list[IsoBlock]:
            """The blocks that are stacks (have ``layers``)."""
            return [b for b in self.blocks if b.is_stack]

        def all_blocks(self) -> list[tuple[str, str, str | None, str | None]]:
            """``(id, label, colour, stack)`` of every block and layer in the order written (a
            stack's layers bottom up in its place; a layer's colour defaults to its stack's)."""
            out: list[tuple[str, str, str | None, str | None]] = []
            for b in self.blocks:
                if b.layers is None:
                    out.append((b.id, b.text(), b.color, None))
                else:
                    out += [(layer.id, layer.text(), layer.color or b.color, b.id) for layer in b.layers]
            return out

        def layout(self, portrait: bool = False) -> IsoDiagramLayout:
            """The diagram laid out on the grid (:func:`layout_iso_diagram`); ``portrait``: for a
            tall frame (``arrange: auto`` is a zigzag there)."""
            items = [ItemSpec(b.id, b.at, block=BlockSpec(b.id, b.shape or "box", b.size, b.height)) if b.layers is None else
                     ItemSpec(b.id, b.at, layers=tuple(BlockSpec(layer.id, layer.shape, None, layer.height) for layer in b.layers),
                              size=b.size, **({"gap": b.gap} if b.gap is not None else {}))
                     for b in self.blocks]
            groups = [GroupSpec(g.id, tuple(g.blocks)) for g in self.groups]
            edges = [EdgeSpec(e.source, e.to, e.style or self.edge_style) for e in self.edges]
            how = ("zigzag" if portrait else "row") if self.arrange == "auto" else self.arrange
            spacing = self.spacing if self.spacing is not None else (2.0 if how == "zigzag" else 1.0)
            return layout_iso_diagram(items, groups, edges, how=how, columns=self.columns, spacing=spacing)

    #: Largest tile width (Manim units), so a small diagram does not fill the frame.
    max_tile = 2.4
    #: Smallest tile width before the labels are made smaller, per point of label size / 32.
    min_tile = 1.0
    #: Labels stay this much above the readable size (as ``diagram``).
    floor_margin = 1.05
    #: Label wrap widths (Manim units at size 32): blocks, a stack's layers, connectors.
    wrap = 3.0
    layer_wrap = 3.6
    edge_wrap = 2.6
    #: Space between a label and what it names, and a stack's layer labels' leader lines.
    gap = 0.14
    lead = 0.35
    #: A label plate's padding, corner and opacity.
    label_pad = (0.16, 0.08)
    plate_opacity = 0.88
    #: Outline width of the blocks.
    stroke = 1.6
    #: Placing labels: a connector is sampled every ``line_step`` tile units, and a label over
    #: one sample costs as much as this much area (square Manim units) of overlap.
    line_step = 0.1
    line_cost = 0.08

    # ----- layout ----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        body = self.safe_area
        heading = None
        if p.heading:
            header = self.region("header")
            heading = fit_text(p.heading, header.width, header.height, size=self.theme.size(p.heading_size),
                               color=p.heading_color, weight=BOLD, role="heading")
            place(heading, header, fit="none", align="center")
            body = body.below(heading, gap=0.4)
        self.diagram_layout = layout = p.layout(self.is_portrait)
        self._colors = self._block_colors()
        self._shapes = self._world_shapes(layout)
        self._bounds = self._shapes.bounds()
        plan = self._fit(body)
        if not plan.fits:
            log.warning("scene '%s': the iso diagram does not fit this frame at the readable label size; "
                        "use fewer blocks, shorter labels or split it", self.spec.id)
        elif plan.scale < self.min_tile * readable_size() / 32:
            log.warning("scene '%s': the iso diagram's blocks are drawn small (its labels take the room); "
                        "use fewer blocks or stacks, shorter labels, or split it", self.spec.id)
        parts = self._draw(plan, body)
        self._steps(heading, parts)

    def _block_colors(self) -> dict[str, str]:
        """Each block's colour: its own, else a term's its label says, else the scene's."""
        p = self.params
        terms = active_terms()
        out: dict[str, str] = {}
        for k, (block_id, label, color, _stack) in enumerate(p.all_blocks()):
            term = find_term(label, terms) if terms and color is None else None
            if color is not None:
                out[block_id] = self.theme.color(color)
            elif term is not None:
                out[block_id] = term.color
            elif p.block_color == "palette":
                out[block_id] = self.theme.palette_color(k)
            else:
                out[block_id] = self.theme.color(p.block_color)
        return out

    def _world_shapes(self, layout: IsoDiagramLayout) -> DiagramShapes:
        """The shapes of everything (:func:`diagram_shapes`) in the scene's colours."""
        p = self.params
        edge_colors = [self.theme.color(e.color or p.edge_color) for e in p.edges]
        group_colors = {g.id: self.theme.color(g.color or "dim") for g in p.groups}
        return diagram_shapes(layout, self._colors, edge_colors, group_colors, floor=p.floor,
                              background=self.theme.background, text=self.theme.color("text"))

    def _make_labels(self, size: float, edge_size: float) -> list[_Label]:
        """Every label's text at ``size`` (blocks, layers, stacks, groups) and ``edge_size``."""
        p = self.params
        u, ue = size / 32, edge_size / 32
        labels: list[_Label] = []
        for block_id, label, _color, stack in p.all_blocks():
            width = (self.layer_wrap if stack else self.wrap) * u
            labels.append(_Label("layer" if stack else "block", block_id,
                                 fit_text(label, width, size=size, color=p.label_color, weight=BOLD, balance=True)))
        for s in p.stacks():
            labels.append(_Label("stack", s.id, fit_text(s.text(), self.wrap * 1.3 * u, size=size, color=p.label_color, balance=True)))
        for g in p.groups:
            if g.label:
                labels.append(_Label("group", g.id, fit_text(g.label, self.wrap * 1.3 * u, size=size, color=p.label_color, balance=True)))
        for e in p.edges:
            if e.label:
                labels.append(_Label("edge", e.ref(), fit_text(e.label, self.edge_wrap * ue, size=edge_size, color=p.edge_label_color, balance=True)))
        return labels

    def _fit(self, body: Region) -> _Plan:
        """The largest diagram whose labels, at the largest size from the requested one down to
        the readable minimum, fit ``body`` with the tile at least :attr:`min_tile` wide."""
        p = self.params
        size, edge_size = float(self.theme.size(p.size)), float(self.theme.size(p.edge_label_size))
        floor = readable_size() * self.floor_margin
        lowest = min(1.0, floor / size, floor / edge_size)
        factors, f = [1.0], 1.0
        while f > lowest + 1e-9:
            f = max(lowest, f * 0.9)
            factors.append(f)
        best: _Plan | None = None
        for factor in factors:
            sizes = (max(min(size, floor), size * factor), max(min(edge_size, floor), edge_size * factor))
            labels = self._make_labels(*sizes)
            plan = self._largest(body, labels)
            if plan.fits and plan.scale >= self.min_tile * sizes[0] / 32:
                return plan
            if best is None or (plan.fits, plan.scale) > (best.fits, best.scale):
                best = plan
        assert best is not None
        return best

    def _largest(self, body: Region, labels: list[_Label]) -> _Plan:
        """The largest scale (tile width, Manim units) up to :attr:`max_tile` at which the
        diagram and ``labels`` fit ``body`` (bisection; not fitting even small: the smallest)."""
        cap = min(self.max_tile, body.width / 1.2, body.height / 1.2)

        def fits(scale: float) -> tuple[bool, _Placement]:
            placement = self._place(scale, labels)
            x0, y0, x1, y1 = placement.bounds
            return x1 - x0 <= body.width + 1e-6 and y1 - y0 <= body.height + 1e-6, placement

        ok, placement = fits(cap)
        if ok:
            return _Plan(cap, labels, placement, True)
        low, high = 0.15, cap
        ok, placement = fits(low)
        if not ok:
            return _Plan(low, labels, placement, False)
        for _ in range(18):
            middle = (low + high) / 2
            ok, found = fits(middle)
            if ok:
                low, placement = middle, found
            else:
                high = middle
        return _Plan(low, labels, placement, True)

    def _place(self, scale: float, labels: list[_Label]) -> _Placement:
        """The labels placed at ``scale`` (picture origin at 0, 0; y up), in turn: a stack's
        layers at its side (its ``label_side``; ``auto``: away from the diagram's middle unless the
        other side is clearer), spread so they do not touch, with leader lines; then each block's
        on its top when it fits there, else above, below, right or left of it, whichever first
        overlaps no label or block placed so far; stack and group captions below (else above,
        right, left); connector labels on the connector's middle (else just above or below)."""
        layout = self.diagram_layout
        out = _Placement()

        def at(point: tuple[float, float]) -> np.ndarray:
            return np.array([point[0] * scale, -point[1] * scale])

        def frame(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
            left, top, right, bottom = box
            return left * scale, -bottom * scale, right * scale, -top * scale

        blocks = {name: frame(b.box.picture_bounds()) for name, b in layout.blocks.items()}
        taken: list[tuple[float, float, float, float]] = []

        def size(k: int, plate: bool = True) -> tuple[float, float]:
            text = labels[k].text
            return (text.width + 2 * self.label_pad[0], text.height + 2 * self.label_pad[1]) if plate else (text.width, text.height)

        def rect(centre: np.ndarray, wh: tuple[float, float]) -> tuple[float, float, float, float]:
            return centre[0] - wh[0] / 2, centre[1] - wh[1] / 2, centre[0] + wh[0] / 2, centre[1] + wh[1] / 2

        def inside(r: tuple[float, float, float, float], points: np.ndarray) -> int:
            return int(np.count_nonzero((points[:, 0] >= r[0]) & (points[:, 0] <= r[2]) & (points[:, 1] >= r[1]) & (points[:, 1] <= r[3])))

        def overlap(r: tuple[float, float, float, float], skip: set[str]) -> float:
            """What a label at ``r`` covers: other labels (area), blocks (the share of each
            block's faces, as its picture's area) and connectors (:attr:`line_cost` a sample)."""
            total = sum(_area(r, other) for other in taken)
            total += sum(weight * inside(r, points) for name, (points, weight) in faces.items() if name not in skip)
            return total + sum(self.line_cost * inside(r, points) for ref, points in lines.items() if ref not in skip)

        faces = {}
        for name, block in layout.blocks.items():
            points = np.array([at(iso_point(*p)) for p in _face_points(block.box)])
            left, bottom, right, top = blocks[name]
            faces[name] = (points, (right - left) * (top - bottom) * 0.7 / len(points))
        lines = {edge.ref(): np.array([at(iso_point(*point)) for point in edge.samples(self.line_step)]) for edge in layout.edges}

        def choose(k: int, options: list[tuple[np.ndarray, bool]], skip: set[str]) -> None:
            best: tuple[float, int] | None = None
            for n, (centre, plate) in enumerate(options):
                cost = overlap(rect(centre, size(k, plate)), skip)
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, n)
                if cost <= 1e-9:
                    break
            assert best is not None
            centre, plate = options[best[1]]
            out.centres[k] = centre
            if not plate:
                out.on_top.add(k)
            taken.append(rect(centre, size(k, plate)))

        by_owner = {(lab.kind, lab.owner): k for k, lab in enumerate(labels)}
        middle = _middle(blocks)
        sides = {s.id: s.label_side or "auto" for s in self.params.stacks()}
        for stack_id, stack in layout.stacks.items():
            left, _, right, _ = _union([blocks[n] for n in stack.layers])
            outward = "left" if (left + right) / 2 < middle - 1e-6 else "right"
            options = [sides[stack_id]] if sides[stack_id] != "auto" else [outward, "right" if outward == "left" else "left"]
            columns = [self._layer_column(stack, side, by_owner, at, blocks, size) for side in options]
            mine = set(stack.layers)
            column = min(columns, key=lambda c: sum(overlap(rect(centre, size(k)), mine) for k, centre, _, _ in c))
            for k, centre, start, end in column:   # the outward side unless the other one is clearer
                out.centres[k] = centre
                out.leaders.append((k, start, end))
                taken.append(rect(centre, size(k)))
        for name, block in layout.blocks.items():
            k = by_owner.get(("block", name))
            if k is None:
                continue
            left, bottom, right, top = blocks[name]
            w, h = size(k)
            room_w, room_h = (v * scale for v in top_room(block))
            tw, th = size(k, False)
            options: list[tuple[np.ndarray, bool]] = []
            if tw / (2 * room_w) + th / (2 * room_h) <= 0.92:
                options.append((at(top_point(block)), False))
            cx = (left + right) / 2
            options += [(np.array([cx, top + self.gap + h / 2]), True), (np.array([cx, bottom - self.gap - h / 2]), True),
                        (np.array([right + self.gap + w / 2, (top + bottom) / 2]), True), (np.array([left - self.gap - w / 2, (top + bottom) / 2]), True)]
            choose(k, options, {name})
        for kind, boxes in (("stack", {s: _union([blocks[n] for n in st.layers]) for s, st in layout.stacks.items()}),
                            ("group", {g: frame(box.picture_bounds()) for g, box in layout.plates.items()})):
            for name, (left, bottom, right, top) in boxes.items():
                k = by_owner.get((kind, name))
                if k is None:
                    continue
                w, h = size(k)
                cx, cy = (left + right) / 2, (top + bottom) / 2
                members = set(layout.stacks[name].layers) if kind == "stack" else {
                    n for n, b in layout.blocks.items() if b.group == name}
                choose(k, [(np.array([cx, bottom - self.gap - h / 2]), True), (np.array([cx, top + self.gap + h / 2]), True),
                           (np.array([right + self.gap + w / 2, cy]), True), (np.array([left - self.gap - w / 2, cy]), True)], members)
        for edge in layout.edges:
            k = by_owner.get(("edge", edge.ref()))
            if k is None:
                continue
            a, b = edge.longest()
            centre = at(iso_point(*edge.midpoint()))
            way = at(iso_point(*b)) - at(iso_point(*a))
            normal = np.array([-way[1], way[0]]) / max(float(np.linalg.norm(way)), 1e-9)
            if normal[1] < 0:
                normal = -normal
            w, h = size(k)
            off = abs(normal[0]) * w / 2 + abs(normal[1]) * h / 2 + self.gap / 2 + 0.06 * scale
            ends = {edge.source, edge.target, edge.ref()}
            choose(k, [(centre + normal * off, True), (centre - normal * off, True), (centre, True)], ends)
        bounds = frame(self._bounds)
        everything = [bounds, *[rect(out.centres[k], size(k, k not in out.on_top)) for k in out.centres]]
        out.bounds = _union(everything)
        return out

    def _layer_column(self, stack: Any, side: str, by_owner: dict[tuple[str, str], int], at: Any,
                      blocks: dict[str, tuple[float, float, float, float]], size: Any) -> list[tuple[int, np.ndarray, np.ndarray, np.ndarray]]:
        """A stack's layer labels in a column at its ``side`` (``left`` or ``right``), spread
        apart: per layer its label's index, centre, and its leader line's ends (from the layer's
        side face to the label)."""
        left, _bottom, right, _top = _union([blocks[n] for n in stack.layers])
        rows = []
        for name in stack.layers:
            rows.append((by_owner[("layer", name)], at(side_point(self.diagram_layout.blocks[name], side))))
        ys = _spread([a[1] for _, a in rows], [size(k)[1] for k, _ in rows], 0.06)
        column = []
        for (k, anchor), y in zip(rows, ys):
            w = size(k)[0]
            x = right + self.lead + w / 2 if side == "right" else left - self.lead - w / 2
            column.append((k, np.array([x, y]), anchor, np.array([x - w / 2 if side == "right" else x + w / 2, y])))
        return column

    # ----- drawing ---------------------------------------------------------------------------

    def _draw(self, plan: _Plan, body: Region) -> dict[str, Any]:
        """Every mobject, placed in the body: the floor, plates, connectors, blocks (in the
        view's draw order) and labels, and the groups the targets are made of."""
        p = self.params
        layout = self.diagram_layout
        x0, y0, x1, y1 = plan.placement.bounds
        shift = body.center[:2] - np.array([(x0 + x1) / 2, (y0 + y1) / 2])
        to_scene = picture_to_scene(plan.scale, shift)
        s = self._shapes
        floor = shapes_mobject(s.floor, to_scene, ink=None, stroke=self.stroke)
        floor.set_z_index(0)
        plates = {}
        for gid, shapes in s.plates.items():
            plates[gid] = shapes_mobject(shapes, to_scene, ink=outline_ink(shapes[-1].fill), stroke=self.stroke)
            plates[gid].set_z_index(1)
        edges: dict[int, VGroup] = {k: VGroup() for k in range(len(layout.edges))}
        for k, shapes in s.arrows.items():
            edges[k].add(shapes_mobject(shapes, to_scene, ink=None).set_z_index(2))
        blocks: dict[str, VGroup] = {}
        for rank, (kind, key) in enumerate(layout.order()):
            if kind == "block":
                blocks[key] = shapes_mobject(s.blocks[key], to_scene, ink=outline_ink(self._colors[key]), stroke=self.stroke)
                blocks[key].set_z_index(10 + rank)
            else:
                k, shapes = s.pipes[key]
                piece = shapes_mobject(shapes, to_scene, ink=outline_ink(shapes[-1].fill), stroke=self.stroke)
                edges[k].add(piece.set_z_index(10 + rank))
        texts: dict[tuple[str, str], VGroup] = {}
        on_fill: dict[str, tuple[Mobject, Mobject]] = {}
        background = self.theme.background
        dark, light = self.theme.background, self.theme.color("text")
        for k, label in enumerate(plan.labels):
            centre = plan.placement.centres[k] + shift
            text = label.text.move_to(np.array([centre[0], centre[1], 0.0]))
            group = VGroup()
            if k in plan.placement.on_top:
                text.set_color(readable_ink(self._colors[label.owner], dark, light))
                on_fill[label.owner] = (text, blocks[label.owner][-1])
            else:
                plate = RoundedRectangle(width=text.width + 2 * self.label_pad[0], height=text.height + 2 * self.label_pad[1],
                                         corner_radius=min(0.12, (text.height + 2 * self.label_pad[1]) / 2))
                plate.set_fill(background, opacity=self.plate_opacity).set_stroke(width=0).move_to(text.get_center())
                group.add(plate.set_z_index(900))
            group.add(text.set_z_index(902))
            texts[(label.kind, label.owner)] = group
        for k, start, end in plan.placement.leaders:
            label = plan.labels[k]
            line = Line(np.array([*(start + shift), 0.0]), np.array([*(end + shift), 0.0]))
            line.set_stroke(self.theme.color("dim"), width=2.0).set_z_index(899)
            dot = Dot(np.array([*(start + shift), 0.0]), radius=0.035, color=self.theme.color("dim")).set_z_index(899)
            texts[(label.kind, label.owner)].add_to_back(line, dot)
        everything = VGroup(floor, *plates.values(), *edges.values(), *blocks.values(), *texts.values())
        if not plan.fits:   # at the readable size and still too big: the whole diagram smaller
            shrink_to_fit(everything, body.width, body.height).move_to(body.center)
        return {"floor": floor, "plates": plates, "edges": edges, "blocks": blocks, "texts": texts, "on_fill": on_fill}

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, heading: Mobject | None, parts: dict[str, Any]) -> None:
        """Targets, and the scene's one step: the whole diagram comes in (floor and plates, the
        blocks back to front, then the connectors)."""
        p = self.params
        layout = self.diagram_layout
        texts = parts["texts"]
        top = self.target("heading", heading, entrance=lambda: [FadeIn(heading, shift=DOWN * 0.15)]) if heading is not None else None
        block_targets: dict[str, Target] = {}
        for i, (block_id, *_rest) in enumerate(p.all_blocks(), start=1):
            mob = VGroup(parts["blocks"][block_id], *([texts[(k, block_id)] for k in ("block", "layer") if (k, block_id) in texts]))
            fill = [parts["on_fill"][block_id]] if block_id in parts["on_fill"] else []
            block_targets[block_id] = self.target([f"block{i}", f"block:{block_id}"], mob, outline=parts["blocks"][block_id],
                                                  on_fill=fill, entrance=lambda mob=mob: [FadeIn(mob, shift=DOWN * 0.12)])
        for stack in p.stacks():
            caption = [texts[("stack", stack.id)]] if ("stack", stack.id) in texts else []
            self.target(f"stack:{stack.id}", VGroup(*[block_targets[layer.id].mobject for layer in stack.layers], *caption))
        for group in p.groups:
            members = [block_targets[m].mobject for m in group.blocks if m in block_targets]
            members += [block_targets[layer.id].mobject for s in p.stacks() if s.id in group.blocks for layer in s.layers or ()]
            caption = [texts[("group", group.id)]] if ("group", group.id) in texts else []
            self.target(f"group:{group.id}", VGroup(parts["plates"][group.id], *caption, *members))
        edge_targets = []
        for k, edge in enumerate(p.edges):
            mob = VGroup(parts["edges"][k], *([texts[("edge", edge.ref())]] if ("edge", edge.ref()) in texts else []))
            edge_targets.append(self.target(f"edge:{edge.ref()}", mob))
        order = [key for kind, key in layout.order() if kind == "block"]
        captions = [texts[key] for key in texts if key[0] in ("stack", "group")]

        def build() -> list[Animation]:
            ground = [m for m in [parts["floor"], *parts["plates"].values(), *captions] if not self.on_screen_parts(m)]
            anims: list[Animation] = [FadeIn(VGroup(*ground))] if ground else []
            arrivals = [a for name in order for a in self.entrance(block_targets[name])]
            if arrivals:
                anims.append(LaggedStart(*arrivals, lag_ratio=0.12))
            links = [a for t in edge_targets for a in self.entrance(t)]
            if links:
                anims.append(LaggedStart(*links, lag_ratio=0.1))
            if top is not None:
                anims = self.entrance(top) + anims
            return [Succession(*anims)] if len(anims) > 1 else anims

        self.reveal([build], fraction=0.8, cap=2.0)
        self.finish()


def _area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """The area two rectangles (left, bottom, right, top) share."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _union(rects: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)


def _face_points(box: Any, count: int = 5) -> list[tuple[float, float, float]]:
    """Points spread over the three faces of ``box`` the view shows (top, ``y1`` and ``x1``
    sides), ``count`` by ``count`` on each."""
    steps = [k / (count - 1) for k in range(count)]
    xs = [box.x0 + (box.x1 - box.x0) * s for s in steps]
    ys = [box.y0 + (box.y1 - box.y0) * s for s in steps]
    zs = [box.z0 + (box.z1 - box.z0) * s for s in steps]
    return ([(x, y, box.z1) for x in xs for y in ys] + [(x, box.y1, z) for x in xs for z in zs]
            + [(box.x1, y, z) for y in ys for z in zs])


def _middle(blocks: dict[str, tuple[float, float, float, float]]) -> float:
    left, _, right, _ = _union(list(blocks.values()))
    return (left + right) / 2


def _spread(ys: list[float], heights: list[float], gap: float) -> list[float]:
    """Label centres near ``ys`` (one column, any order) that keep ``gap`` between labels of
    ``heights``, keeping their order from the top and the column's middle."""
    order = sorted(range(len(ys)), key=lambda k: -ys[k])
    placed: dict[int, float] = {}
    previous: int | None = None
    for k in order:
        y = ys[k]
        if previous is not None:
            y = min(y, placed[previous] - (heights[previous] + heights[k]) / 2 - gap)
        placed[k] = y
        previous = k
    drift = (sum(ys) - sum(placed.values())) / len(ys)
    return [placed[k] + drift for k in range(len(ys))]
