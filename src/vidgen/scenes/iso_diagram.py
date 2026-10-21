"""``iso_diagram``: a diagram of blocks in the isometric view (DESIGN.md §90.6, §90.8-90.10):
boxes, slabs, cylinders and databases, flat tiles, stacks of layers and group plates on a grid,
joined by connectors along the grid, with flat labels that stay readable, and the actions that
build, raise, explode, recolour and relabel it, flow along its connectors and focus on its parts
(``scenes/iso_actions.py``)."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .chart_changes import keep_opacity
from .iso_motion import FillFade, FlowDots, GrowBlock, LiftMove, Reshape, SwapAtEnd, Veil
from .diagram import _ID, _unknown, edge_ref, parse_edges

log = logging.getLogger("vidgen.scenes")

BlockShape = Literal["box", "slab", "cylinder", "database", "tile"]
EdgeStyle = Literal["solid", "dashed", "pipe"]
EntranceStyle = Literal["drop", "grow", "fade"]
Cells = tuple[float, float]
LabelKey = tuple[str, str]
Box = tuple[float, float, float, float]

#: With ``at`` in a tall frame, a slanted grid (:func:`slant`) is used when it draws the
#: diagram at least this much larger; the body's width over its height there.
SLANT_GAIN = 1.15
PORTRAIT_BODY = 0.62
#: Fitting the diagram: scales tried from the largest down, each this share of the one before,
#: until one fits; then this many bisection steps between it and the next larger one.
SCAN_STEP = 0.9
BISECT_STEPS = 8
#: In a tall frame, another layout of an ``at`` grid (``IsoDiagram.Params.layouts``) is drawn
#: instead of the preferred one when it is fitted at least this much larger.
LAYOUT_GAIN = 1.05


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
    """Text shown with the block (default: the id): on its top when it fits, else beside it; a stack's caption under it (a stack of one layer has one label: its layer's, else this)."""
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
    label_side: Literal["auto", "left", "right", "below"] | None = None
    """Where a stack's layer labels go: auto (default: in 16:9 at the side away from the diagram's middle, in 9:16 below the stack), left, right (with leader lines) or below (a list under the stack, each with a swatch of its layer's colour)."""
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
    """Optional caption by the plate's front edge."""
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
    """Optional text along the connector."""
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
    connector ref), its text, the room it keeps (``extent``: the largest of the texts it shows,
    with a ``relabel`` action's) and how to write another text in its style."""

    kind: str
    owner: str
    text: Mobject
    extent: tuple[float, float]
    make: Callable[[str], Mobject]

    @property
    def key(self) -> LabelKey:
        return (self.kind, self.owner)


@dataclass
class _Placement:
    """Where the labels go at one scale (picture origin at 0, 0; y up): centres, which sit on
    their block's top, leader lines, swatches (a stack's labels listed under it) and the bounds of
    everything."""

    centres: dict[int, np.ndarray] = field(default_factory=dict)
    on_top: set[int] = field(default_factory=set)
    leaders: list[tuple[int, np.ndarray, np.ndarray]] = field(default_factory=list)
    swatches: dict[int, tuple[np.ndarray, tuple[float, float]]] = field(default_factory=dict)
    bounds: Box = (0.0, 0.0, 0.0, 0.0)


@dataclass
class _Plan:
    scale: float
    labels: list[_Label]
    placement: _Placement
    fits: bool


@dataclass
class _Solid:
    """A drawn piece the actions recolour with its shading kept: its mobject and its shapes in
    a colour (``paint`` turns each of its colours into the one wanted)."""

    mobject: Mobject
    build: Callable[[Callable[[str], str]], Mobject]


@scene("iso_diagram")
class IsoDiagram(NarratedScene):
    """A diagram of blocks in the isometric view: boxes, slabs, cylinders and databases, flat
    tiles, stacks of layers (a layered architecture, a network's layers) and group plates on a
    grid, joined by connectors along the grid (flat arrows, dashed, or pipes). Labels stay flat
    and readable: on a block's top when they fit, else right by it; a stack's layers are
    labelled at its side (or listed under it in 9:16); connector labels lie along the connector,
    a group's caption by its plate's front edge. The diagram is fitted to the frame (16:9 and
    9:16) and built in the first beat (``build: each``: one block or stack per step), except what
    a ``reveal`` or ``build`` action brings.

    Actions: ``build`` (grow up from the floor, drop in, fade), ``raise`` / ``lower``, ``explode``
    / ``collapse`` (a stack's layers apart and back), ``flow`` (dots or packets along connectors),
    ``focus`` (the camera on a part), ``relabel`` (swap a label or value), and ``dim``,
    ``highlight`` (blocks keep their shading), ``zoom``, ``callout``... Action targets:
    ``heading``, ``diagram``, ``block<N>`` (1-based: every block and layer in the order written, a
    stack's layers bottom up in its place), ``block:<id>``, ``stack:<id>``, ``group:<id>`` and
    ``edge:<from>-><to>``.
    """

    outro = 0.5
    target_patterns = ("heading", "diagram", "block<N>", "block:<id>", "stack:<id>", "group:<id>", "edge:<from>-><to>")
    #: The ``iso_diagram`` actions (``scenes/iso_actions.py``) act on this scene type only.
    iso_diagram_actions = True
    mid_still_actions = frozenset({"build", "raise", "lower", "explode", "collapse", "flow", "relabel"})

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``heading`` (if any), ``diagram``, ``block<N>`` and ``block:<id>`` per block and
        layer, ``stack:<id>``, ``group:<id>``, ``edge:<from>-><to>``."""
        names = (["heading"] if params.heading else []) + ["diagram"]
        for i, (block_id, *_rest) in enumerate(params.all_blocks(), start=1):
            names += [f"block{i}", f"block:{block_id}"]
        names += [f"stack:{s.id}" for s in params.stacks()] + [f"group:{g.id}" for g in params.groups]
        return names + [f"edge:{e.ref()}" for e in params.edges]

    @staticmethod
    def target_kind(name: str) -> str:
        """What a target name of the scene stands for: ``heading``, ``diagram``, ``block``,
        ``stack``, ``group`` or ``edge``."""
        if name in ("heading", "diagram"):
            return name
        if name.startswith("block"):
            return "block"
        return name.split(":", 1)[0]

    @classmethod
    def has_label(cls, params: Any, name: str) -> bool:
        """Whether target ``name`` shows a label (``relabel``): every block and layer does; a
        stack its caption unless it repeats a layer's label (a stack of one: its layer's); a
        group or connector when given one."""
        kind = cls.target_kind(name)
        if kind == "block":
            return True
        rest = name.split(":", 1)[-1]
        if kind == "stack":
            stack = next(s for s in params.stacks() if s.id == rest)
            layers = stack.layers or []
            return len(layers) == 1 or stack.text() not in {layer.text() for layer in layers}
        if kind == "group":
            return bool(next(g for g in params.groups if g.id == rest).label)
        if kind == "edge":
            return bool(next(e for e in params.edges if e.ref() == rest).label)
        return False

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
        portrait_grid: Literal["auto", "keep"] = "auto"
        """Blocks placed with 'at' in a tall frame (9:16): auto draws the grid as written or slanted (all or half the way) so its longer direction runs down the frame, whichever is drawn larger (neighbours keep their sides; connectors are routed again); keep draws it as written."""
        floor: Literal["grid", "plain", "none"] = "grid"
        """The floor under the diagram: with grid lines, plain, or none."""
        build: Literal["together", "each"] = "together"
        """How the scene builds the diagram: together (all in the first beat) or each (one block or stack per step, spread over the beats, with the connectors whose ends are there); blocks a reveal or build action names wait for it."""
        entrance: EntranceStyle = "drop"
        """How blocks come in: drop (in from above), grow (up from the floor; a stack layer by layer) or fade."""
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
            stack's layers bottom up in its place; a layer's colour defaults to its stack's; the
            one layer of a stack of one is labelled with its own label, else the stack's)."""
            out: list[tuple[str, str, str | None, str | None]] = []
            for b in self.blocks:
                if b.layers is None:
                    out.append((b.id, b.text(), b.color, None))
                elif len(b.layers) == 1:
                    layer = b.layers[0]
                    out.append((layer.id, layer.label or b.label or layer.id, layer.color or b.color, b.id))
                else:
                    out += [(layer.id, layer.text(), layer.color or b.color, b.id) for layer in b.layers]
            return out

        def layout(self, portrait: bool = False) -> IsoDiagramLayout:
            """The diagram laid out on the grid (:func:`layout_iso_diagram`); ``portrait``: for a
            tall frame (``arrange: auto`` is a zigzag there; with ``at``, the grid may be slanted
            down the frame, ``portrait_grid``)."""
            items = self._items()
            groups = [GroupSpec(g.id, tuple(g.blocks)) for g in self.groups]
            edges = [EdgeSpec(e.source, e.to, e.style or self.edge_style) for e in self.edges]
            how = ("zigzag" if portrait else "row") if self.arrange == "auto" else self.arrange
            spacing = self.spacing if self.spacing is not None else (2.0 if how == "zigzag" else 1.0)
            written = layout_iso_diagram(items, groups, edges, how=how, columns=self.columns, spacing=spacing)
            if not portrait or self.portrait_grid == "keep" or any(item.at is None for item in items) or len(items) < 2:
                return written

            def score(layout: IsoDiagramLayout) -> float:
                w, h = picture_size(layout)
                return min(PORTRAIT_BODY / max(w, 1e-6), 1.0 / max(h, 1e-6))

            best, best_score = written, score(written) * SLANT_GAIN
            for slanted in self._slanted(items, groups, edges, how, spacing, (1.0,)):
                if score(slanted) > best_score:
                    best, best_score = slanted, score(slanted)
            return best

        def layouts(self, portrait: bool = False) -> list[IsoDiagramLayout]:
            """The layouts the scene may draw, the preferred first: :meth:`layout`, and in a tall
            frame with ``at`` and ``portrait_grid: auto`` also the grid as written and slanted
            all or half the way along either axis (the scene draws the one fitted largest)."""
            first = self.layout(portrait)
            items = self._items()
            if not portrait or self.portrait_grid == "keep" or any(item.at is None for item in items) or len(items) < 2:
                return [first]
            groups = [GroupSpec(g.id, tuple(g.blocks)) for g in self.groups]
            edges = [EdgeSpec(e.source, e.to, e.style or self.edge_style) for e in self.edges]
            spacing = self.spacing if self.spacing is not None else 1.0
            how = "row" if self.arrange == "auto" else self.arrange
            written = layout_iso_diagram(items, groups, edges, how=how, columns=self.columns, spacing=spacing)
            return [first, written, *self._slanted(items, groups, edges, how, spacing, (1.0, 0.5))]

        def _items(self) -> list[ItemSpec]:
            return [ItemSpec(b.id, b.at, block=BlockSpec(b.id, b.shape or "box", b.size, b.height)) if b.layers is None else
                    ItemSpec(b.id, b.at, layers=tuple(BlockSpec(layer.id, layer.shape, None, layer.height) for layer in b.layers),
                             size=b.size, **({"gap": b.gap} if b.gap is not None else {}))
                    for b in self.blocks]

        def _slanted(self, items: list[ItemSpec], groups: list[GroupSpec], edges: list[EdgeSpec], how: str, spacing: float,
                     shares: Sequence[float]) -> list[IsoDiagramLayout]:
            """The grid slanted along x and along y, each by the ``shares`` (where the blocks do not then overlap)."""
            out = []
            for share in shares:
                for along in ("x", "y"):
                    try:
                        out.append(layout_iso_diagram(slant(items, along, share), groups, edges, how=how, columns=self.columns, spacing=spacing))
                    except ValueError:
                        continue
            return out

    #: Largest tile width (Manim units), so a small diagram does not fill the frame; in 9:16 this
    #: much more (a phone shows the frame small, and a tall frame has room above and below).
    max_tile = 2.4
    portrait_tile = 1.35
    #: Smallest tile width before the labels are made smaller, per point of label size / 32.
    min_tile = 1.0
    #: Labels stay this much above the readable size (as ``diagram``).
    floor_margin = 1.05
    #: Label wrap widths (Manim units at size 32): blocks, a stack's layers, connectors.
    wrap = 3.0
    layer_wrap = 3.6
    edge_wrap = 2.6
    #: Space between a label and what it names, a stack's layer labels' leader lines, and the gap
    #: from which a label beside a block gets a leader line to it.
    gap = 0.14
    lead = 0.35
    leader_from = 0.35
    #: A label plate's padding, corner and opacity.
    label_pad = (0.16, 0.08)
    plate_opacity = 0.88
    #: Outline width of the blocks.
    stroke = 1.6
    #: Connectors are sampled every ``line_step`` tile units (labels keep off them).
    line_step = 0.1
    #: A stack's layer list under it (9:16): a swatch's width per text height, the gap after it.
    swatch = 1.5
    swatch_gap = 0.14
    #: Entrances: how far (cells) a block drops in from, and a stack's layers' lag.
    drop = 0.8
    #: A raised block's shadow on its ground: its opacity at full lift (``shadow_lift`` cells).
    shadow_opacity = 0.35
    shadow_lift = 0.6
    #: Flow: a dot's radius and a packet's size (cells), the dots' spacing (share of the way).
    dot_radius = 0.09
    packet = 0.22
    flow_spacing = 0.16

    # ----- layout ----------------------------------------------------------------------------

    def construct(self) -> None:
        heading, body, plan = self.plan_diagram()
        parts = self._draw(plan, body)
        self._steps(heading, parts)

    def plan_diagram(self) -> tuple[Mobject | None, Region, _Plan]:
        """The heading, the body left for the diagram, and the diagram laid out and fitted to it
        with its labels placed (nothing drawn yet)."""
        p = self.params
        body = self.safe_area
        heading = None
        if p.heading:
            header = self.region("header")
            heading = fit_text(p.heading, header.width, header.height, size=self.theme.size(p.heading_size),
                               color=p.heading_color, weight=BOLD, role="heading")
            place(heading, header, fit="none", align="center")
            body = body.below(heading, gap=0.4)
        self._colors = self._block_colors()
        layouts = p.layouts(self.is_portrait)
        if len(layouts) > 1:   # in 9:16 the grid as written or slanted: the one drawn largest at the label size asked for
            sizes = (float(self.theme.size(p.size)), float(self.theme.size(p.edge_label_size)))
            best: tuple[_Plan, IsoDiagramLayout] | None = None
            seen: set[tuple[Any, ...]] = set()
            for layout in layouts:
                key = tuple(sorted(layout.items.items()))
                if key in seen:
                    continue
                seen.add(key)
                self._take(layout)
                plan = self._largest(body, self._make_labels(*sizes), bisect=2)
                if best is None or (plan.fits, plan.scale) > (best[0].fits, best[0].scale * LAYOUT_GAIN):
                    best = (plan, layout)
            assert best is not None
            layouts = [best[1]]
        self._take(layouts[0])
        plan = self._fit(body)
        if not plan.fits:
            log.warning("scene '%s': the iso diagram does not fit this frame at the readable label size; "
                        "use fewer blocks, shorter labels or split it", self.spec.id)
        elif plan.scale < self.min_tile * readable_size() / 32:
            log.warning("scene '%s': the iso diagram's blocks are drawn small (its labels take the room); "
                        "use fewer blocks or stacks, shorter labels, or split it", self.spec.id)
        return heading, body, plan

    def _take(self, layout: IsoDiagramLayout) -> None:
        """``layout`` taken as the scene's: its shapes and the geometry its labels keep clear of."""
        self.diagram_layout = layout
        self._shapes = self._world_shapes(layout)
        self._geometry(layout)

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
        self._edge_colors = [self.theme.color(e.color or p.edge_color) for e in p.edges]
        self._group_colors = {g.id: self.theme.color(g.color or "dim") for g in p.groups}
        return diagram_shapes(layout, self._colors, self._edge_colors, self._group_colors, floor=p.floor,
                              background=self.theme.background, text=self.theme.color("text"))

    def _geometry(self, layout: IsoDiagramLayout) -> None:
        """What the labels keep clear of, on the picture turned up the right way (tile widths,
        ``y`` up): each block's outline, each stack's and plate's, the connectors' samples; the
        lifts the scene's actions will give the blocks, and the bounds of everything with them."""
        up = np.array([1.0, -1.0])
        self._hulls = {name: convex_hull(np.array(block_outline(b)) * up) for name, b in layout.blocks.items()}
        self._lift_max = self._planned_lifts()
        # what other labels keep clear of: a block where it stands and where actions raise it to
        self._swept = {name: convex_hull(np.vstack([hull, np.array(block_outline(layout.blocks[name], self._lift_max[name])) * up]))
                       if self._lift_max[name] > 1e-9 else hull for name, hull in self._hulls.items()}
        self._stack_hulls = {sid: convex_hull(np.vstack([self._swept[n] for n in s.layers])) for sid, s in layout.stacks.items()}
        self._plate_hulls = {gid: convex_hull(np.array(box_outline(box)) * up) for gid, box in layout.plates.items()}
        self._lines = {edge.ref(): np.array([iso_point(*q) for q in edge.samples(self.line_step)]) * up for edge in layout.edges}
        # the connectors as they tilt up to the blocks actions raise (a raised block's label rides
        # up with it and must keep off them there too)
        self._raised_lines: dict[str, np.ndarray] = {}
        for edge in layout.edges:
            low, high = self._lift_max[self._end_blocks(edge.source)[0]], self._lift_max[self._end_blocks(edge.target)[0]]
            if max(low, high) > 1e-9:
                samples = edge.samples(self.line_step)
                last = max(len(samples) - 1, 1)
                self._raised_lines[edge.ref()] = np.array([iso_point(x, y, z + low + (high - low) * j / last)
                                                           for j, (x, y, z) in enumerate(samples)]) * up
        boxes = iter(layout.pipe_boxes())
        self._pipe_hulls = {f"{edge.ref()}#{j}": convex_hull(np.array(box_outline(next(boxes))) * up)
                            for edge in layout.edges if edge.style == "pipe" for j in range(len(edge.points) - 1)}
        left, top, right, bottom = self._shapes.bounds()
        rects = [(left, -bottom, right, -top)]
        for name, lift in self._lift_max.items():
            if lift > 1e-9:
                rects.append(hull_box(convex_hull(np.array(block_outline(layout.blocks[name], lift)) * up)))
        self._bounds = rect_union(rects)

    def _planned_lifts(self) -> dict[str, float]:
        """The most each block may be raised by the scene's ``raise`` and ``explode`` actions
        (cells), so the diagram is fitted with room for them."""
        layout = self.diagram_layout
        names = type(self).target_names(self.params)
        own = {name: 0.0 for name in layout.blocks}
        gaps = {sid: s.gap for sid, s in layout.stacks.items()}
        plates = self._plate_lift_max = {gid: 0.0 for gid in layout.plates}
        for kind in ("raise", "explode"):
            for use in self.action_uses(kind):
                for pattern in use.config.targets():
                    for name in [n for n in names if fnmatchcase(n, pattern)]:
                        blocks = self._blocks_named(name)
                        if kind == "raise":
                            for b in self._bottoms(blocks):
                                own[b] += use.options.by
                            if self.target_kind(name) == "group":
                                plates[name[len("group:"):]] += use.options.by
                        else:
                            for sid in {layout.blocks[b].stack for b in blocks} - {None}:
                                gaps[sid] = max(gaps[sid], use.options.gap)
        return self._lifts_of(own, gaps)

    def _lifts_of(self, own: dict[str, float], gaps: dict[str, float]) -> dict[str, float]:
        """Each block's lift (cells): its own raise and those of the layers under it, and its
        stack's gap beyond the stack's own."""
        layout = self.diagram_layout
        out: dict[str, float] = {}
        for name, block in layout.blocks.items():
            if block.stack is None:
                out[name] = own[name]
                continue
            stack = layout.stacks[block.stack]
            out[name] = sum(own[layer] for layer in stack.layers[: block.level + 1]) + block.level * (gaps[block.stack] - stack.gap)
        return out

    def _bottoms(self, blocks: Sequence[str]) -> list[str]:
        """What raising ``blocks`` raises: each block, but of a stack the lowest of them (the
        layers above go with it)."""
        layout = self.diagram_layout
        out: list[str] = []
        lowest: dict[str, str] = {}
        for name in blocks:
            stack = layout.blocks[name].stack
            if stack is None:
                out.append(name)
            elif stack not in lowest or layout.blocks[name].level < layout.blocks[lowest[stack]].level:
                lowest[stack] = name
        return out + list(lowest.values())

    def _blocks_named(self, name: str) -> list[str]:
        """The blocks (and layers) target ``name`` covers."""
        p = self.params
        kind = self.target_kind(name)
        everything = [b for b, *_ in p.all_blocks()]
        if kind == "block":
            if name.startswith("block:"):
                return [name[len("block:"):]]
            return [everything[int(name[len("block"):]) - 1]]
        if kind == "stack":
            return list(self.diagram_layout.stacks[name[len("stack:"):]].layers)
        if kind == "group":
            group = next(g for g in p.groups if g.id == name[len("group:"):])
            return [b for b in everything if self._item_of(b) in group.blocks]
        if kind == "diagram":
            return everything
        return []

    def _item_of(self, block: str) -> str:
        return self.diagram_layout.blocks[block].stack or block

    # ----- labels ----------------------------------------------------------------------------

    def _label_keys(self) -> dict[str, LabelKey]:
        """The label each target name shows (for ``relabel``): a block's or layer's, a stack's
        caption (of a stack of one: its layer's label), a group's caption, a connector's."""
        p = self.params
        out: dict[str, LabelKey] = {}
        for i, (block_id, _label, _color, stack) in enumerate(p.all_blocks(), start=1):
            kind = "layer" if stack is not None and len(self.diagram_layout.stacks[stack].layers) > 1 else "block"
            out[f"block{i}"] = out[f"block:{block_id}"] = (kind, block_id)
        for s in p.stacks():
            out[f"stack:{s.id}"] = ("block", s.layers[0].id) if len(s.layers or ()) == 1 else ("stack", s.id)
        out.update({f"group:{g.id}": ("group", g.id) for g in p.groups})
        out.update({f"edge:{e.ref()}": ("edge", e.ref()) for e in p.edges})
        return out

    def _relabels(self) -> dict[LabelKey, list[str]]:
        """The texts ``relabel`` actions will give each label (so it keeps room for them)."""
        keys = self._label_keys()
        out: dict[LabelKey, list[str]] = {}
        for use in self.action_uses("relabel"):
            for pattern in use.config.targets():
                for name, key in keys.items():
                    if fnmatchcase(name, pattern):
                        out.setdefault(key, []).append(str(use.options.text))
        return out

    def _make_labels(self, size: float, edge_size: float) -> list[_Label]:
        """Every label's text at ``size`` (blocks, layers, stacks, groups) and ``edge_size``."""
        p = self.params
        u, ue = size / 32, edge_size / 32
        later = self._relabels()
        labels: list[_Label] = []

        def add(kind: str, owner: str, text: str, width: float, at: float, color: str, weight: str = NORMAL) -> None:
            def make(words: str) -> Mobject:
                return fit_text(words, width, size=at, color=color, weight=weight, balance=True)

            made = make(text)
            extent = (made.width, made.height)
            for other in later.get((kind, owner), []):
                alt = make(other)
                extent = (max(extent[0], alt.width), max(extent[1], alt.height))
            labels.append(_Label(kind, owner, made, extent, make))

        captions = {s.id: s.text() for s in p.stacks() if len(s.layers or ()) > 1}
        for block_id, label, _color, stack in p.all_blocks():
            if stack is not None and stack in captions:
                add("layer", block_id, label, self.layer_wrap * u, size, p.label_color, BOLD)
            else:
                add("block", block_id, label, self.wrap * u, size, p.label_color, BOLD)
        for s in p.stacks():
            if s.id in captions and captions[s.id] not in {layer.text() for layer in s.layers or ()}:   # never a label twice
                add("stack", s.id, captions[s.id], self.wrap * 1.3 * u, size, p.label_color)
        for g in p.groups:
            if g.label:
                add("group", g.id, g.label, self.wrap * 1.3 * u, size, p.label_color)
        for e in p.edges:
            if e.label:
                add("edge", e.ref(), e.label, self.edge_wrap * ue, edge_size, p.edge_label_color)
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

    def _largest(self, body: Region, labels: list[_Label], bisect: int = BISECT_STEPS) -> _Plan:
        """The largest scale (tile width, Manim units) up to :attr:`max_tile` at which the
        diagram and ``labels`` fit ``body`` (a scan down, then ``bisect`` steps; not fitting
        even small: the smallest)."""
        cap = min(self.max_tile * (self.portrait_tile if self.is_portrait else 1.0), body.width / 1.2, body.height / 1.2)
        x0, y0, x1, y1 = self._bounds   # no larger than the drawing alone fits (its labels only add to it)
        cap = min(cap, body.width / max(x1 - x0, 1e-6), body.height / max(y1 - y0, 1e-6))

        def inside(placement: _Placement) -> bool:
            x0, y0, x1, y1 = placement.bounds
            return x1 - x0 <= body.width + 1e-6 and y1 - y0 <= body.height + 1e-6

        def fits(scale: float) -> tuple[bool, _Placement]:
            # labels above and below their blocks first; else beside them (a wide body has room
            # at the sides when the labels above and below take its height, a tall one the other way)
            placement = self._place(scale, labels)
            if inside(placement):
                return True, placement
            x0, y0, x1, y1 = placement.bounds
            if y1 - y0 <= body.height + 1e-6 or x1 - x0 > body.width * 0.98:   # labels beside the blocks help the height only
                return False, placement
            sideways = self._place(scale, labels, sideways=True)
            return (True, sideways) if inside(sideways) else (False, placement)

        ok, placement = fits(cap)
        if ok:
            return _Plan(cap, labels, placement, True)
        # Whether it fits is not monotonic in the scale (a label pushed clear at one scale can lie
        # by its block at a larger one), so scan down for the largest that fits, then bisect.
        low, high = 0.15, cap
        scale = cap * SCAN_STEP
        while scale > low:
            ok, found = fits(scale)
            if ok:
                low, placement = scale, found
                break
            high, scale = scale, scale * SCAN_STEP
        else:
            ok, placement = fits(low)
            if not ok:
                return _Plan(low, labels, placement, False)
        for _ in range(bisect):
            middle = (low + high) / 2
            ok, found = fits(middle)
            if ok:
                low, placement = middle, found
            else:
                high = middle
        return _Plan(low, labels, placement, True)

    def _place(self, scale: float, labels: list[_Label], sideways: bool = False) -> _Placement:
        """The labels placed at ``scale`` (picture origin at 0, 0; y up), in turn: a stack's
        layers in a column at its side with leader lines, or listed under it with swatches
        (``label_side``; ``auto``: away from the diagram's middle in 16:9, under it in 9:16, unless
        another place covers less); each block's on its top when it fits there, else right by its
        outline (above, below, beside: ``sideways`` tries beside first; above and below also
        lined up with either side of the block), else pushed clear with a leader line; connector
        labels along the connector, beside it; stack and group captions by the stack's foot and
        the plate's front edges. Each takes the first place that covers no label, block or
        connector, else the one that covers least."""
        layout = self.diagram_layout
        out = _Placement()
        hulls = {n: h * scale for n, h in {**self._swept, **self._pipe_hulls}.items()}
        obstacles = Obstacles(hulls, {ref: pts * scale for ref, pts in self._lines.items()}, clearance=2 * self.gap)
        by_owner = {lab.key: k for k, lab in enumerate(labels)}
        Owner = np.ndarray | Callable[[np.ndarray], np.ndarray] | None

        def size(k: int, plate: bool = True) -> tuple[float, float]:
            w, h = labels[k].extent
            return (w + 2 * self.label_pad[0], h + 2 * self.label_pad[1]) if plate else (w, h)

        def commit(k: int, centre: np.ndarray, plate: bool = True, owner: Owner = None) -> None:
            out.centres[k] = np.asarray(centre, dtype=float)
            if not plate:
                out.on_top.add(k)
            rect = rect_of(centre, size(k, plate))
            obstacles.taken.append(rect)
            hull = owner(out.centres[k]) if callable(owner) else owner
            if hull is not None and hull_gap(rect, hull) > self.leader_from:
                middle = np.array([(hull[:, 0].min() + hull[:, 0].max()) / 2, (hull[:, 1].min() + hull[:, 1].max()) / 2])
                start = ray_exit(hull, middle, centre)
                out.leaders.append((k, start, rect_exit(rect, start)))

        def raised(k: int, plate: bool, rect: Box) -> float:
            """What label ``k`` at ``rect`` covers of the tilted connectors when its block is raised
            as high as the scene's actions take it (it rides up with the block; a label on the top
            may lie anywhere on its block)."""
            label = labels[k]
            lift = self._lift_max.get(label.owner, 0.0) if label.kind == "block" else 0.0
            if lift <= 1e-9 or not plate or not self._raised_lines:
                return 0.0
            dy = lift * ISO_RISE * scale
            up_rect = (rect[0], rect[1] + dy, rect[2], rect[3] + dy)
            count = 0
            for points in self._raised_lines.values():
                pts = points * scale
                count += int(np.count_nonzero((pts[:, 0] >= up_rect[0]) & (pts[:, 0] <= up_rect[2]) & (pts[:, 1] >= up_rect[1]) & (pts[:, 1] <= up_rect[3])))
            return LINE_COST * count

        def choose(k: int, near: list[tuple[np.ndarray, bool]], far: Callable[[], list[np.ndarray]], skip: set[str], owner: Owner) -> None:
            best: tuple[float, np.ndarray, bool] | None = None
            for centre, plate in near:
                rect = rect_of(centre, size(k, plate))
                cost = obstacles.cost(rect, skip) + raised(k, plate, rect)
                if cost <= 1e-9:
                    commit(k, centre, plate, owner)
                    return
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, centre, plate)
            for centre in far():   # pushed clear: dearer the further off it goes
                rect = rect_of(centre, size(k))
                hull = owner(centre) if callable(owner) else owner
                off = max(hull_gap(rect, hull) - self.leader_from, 0.0) if hull is not None else 0.0
                cost = obstacles.cost(rect, skip) + raised(k, True, rect) + FAR_COST * off
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, centre, True)
            assert best is not None
            commit(k, best[1], best[2], owner)

        def around(k: int, hull: np.ndarray, directions: Sequence[Sequence[float]]) -> tuple[list[tuple[np.ndarray, bool]], Callable[[], list[np.ndarray]]]:
            middle = np.array([(hull[:, 0].min() + hull[:, 0].max()) / 2, (hull[:, 1].min() + hull[:, 1].max()) / 2])
            near = [(slide_out(size(k), middle, d, hull, self.gap), True) for d in directions]
            return near, lambda: [obstacles.clear_of_all(size(k), c, d, self.gap) for (c, _), d in zip(near, directions)]

        def aligned(k: int, hull: np.ndarray) -> list[tuple[np.ndarray, bool]]:
            """Above and below a block narrower than the label, lined up with its left or right
            edge instead of its middle (clear of a neighbour on the other side)."""
            left, _bottom, right, _top = hull_box(hull)
            room = (size(k)[0] - (right - left)) / 2
            if room <= 1e-6:
                return []
            middle = np.array([(left + right) / 2, (hull[:, 1].min() + hull[:, 1].max()) / 2])
            return [(slide_out(size(k), middle + np.array([side * room, 0.0]), (0.0, up), hull, self.gap), True)
                    for up in (1.0, -1.0) for side in (-1.0, 1.0)]

        # a stack's layers: a column at its side, or a list under it
        placed_captions: set[str] = set()
        for sid, stack in layout.stacks.items():
            if len(stack.layers) < 2:
                continue
            columns = [self._layer_column(stack, side, by_owner, scale, size) for side in self._label_sides(sid)]
            mine = set(stack.layers)
            best = min(enumerate(columns), key=lambda c: (round(sum(obstacles.cost(rect, mine) for rect in c[1][1]), 6), c[0]))[1]
            for k, centre, leader, swatch in best[0]:
                out.centres[k] = centre
                if leader is not None:
                    out.leaders.append((k, *leader))
                if swatch is not None:
                    out.swatches[k] = swatch
            obstacles.taken.extend(best[1])
            if best[2]:
                placed_captions.add(sid)
        # a group's caption: by its plate's front edges, else round it, else outside the diagram
        whole = rect_union([hull_box(h) for h in hulls.values()])
        for gid in layout.plates:
            k = by_owner.get(("group", gid))
            if k is None:
                continue
            hull = self._plate_hulls[gid] * scale
            box = layout.plates[gid]
            fronts = [np.array(iso_point(*q)) * np.array([scale, -scale]) for q in
                      (((box.x0 + box.x1) / 2, box.y1, 0.0), (box.x1, (box.y0 + box.y1) / 2, 0.0), (box.x1, box.y1, 0.0))]
            middle = np.array([(hull[:, 0].min() + hull[:, 0].max()) / 2, (hull[:, 1].min() + hull[:, 1].max()) / 2])
            directions = [f - middle for f in fronts] + [np.array([-1.0, 0.0]), np.array([1.0, 0.0]), np.array([0.0, 1.0])]
            near, far_near = around(k, hull, directions)
            h = size(k)[1]

            def far(far_near: Callable[[], list[np.ndarray]] = far_near, middle: np.ndarray = middle, h: float = h) -> list[np.ndarray]:
                outside = [np.array([middle[0], whole[1] - self.gap - h / 2]), np.array([middle[0], whole[3] + self.gap + h / 2])]
                return far_near() + outside

            choose(k, near, far, set(), hull)
        # each block's label: on its top, else right by it, else pushed clear (with a leader)
        for name, block in layout.blocks.items():
            k = by_owner.get(("block", name))
            if k is None:
                continue
            hull = self._hulls[name] * scale   # its label rides with it when it is raised
            room_w, room_h = (v * scale for v in top_room(block))
            tw, th = size(k, False)
            near: list[tuple[np.ndarray, bool]] = []
            if tw / (2 * room_w) + th / (2 * room_h) <= 0.92:
                u, v = top_point(block)
                near.append((np.array([u * scale, -v * scale]), False))
            beside, far_off = around(k, hull, SIDEWAYS if sideways else AROUND)
            choose(k, near + beside + aligned(k, hull), far_off, {name}, hull)
        # a stack's caption: under its foot, else round it
        for sid, stack in layout.stacks.items():
            k = by_owner.get(("stack", sid))
            if k is None or sid in placed_captions:
                continue
            hull = self._stack_hulls[sid] * scale
            near, far = around(k, hull, ((0.0, -1.0), (-1.0, -1.0), (1.0, -1.0), (0.0, 1.0), (-1.0, 0.0), (1.0, 0.0)))
            choose(k, near, far, set(stack.layers), hull)   # clear of its layers also where actions raise them (the hull swept)
        # connector labels: beside the connector, along its longest straight run first
        for edge in layout.edges:
            k = by_owner.get(("edge", edge.ref()))
            if k is None:
                continue
            w, h = size(k)
            options: list[tuple[np.ndarray, bool]] = []
            normals: list[np.ndarray] = []
            segments = sorted(zip(edge.points, edge.points[1:]), key=lambda ab: -float(np.hypot(ab[1][0] - ab[0][0], ab[1][1] - ab[0][1])))
            for a, b in segments:
                pa, pb = (np.array(iso_point(*q)) * np.array([scale, -scale]) for q in (a, b))
                way = pb - pa
                normal = np.array([-way[1], way[0]]) / max(float(np.linalg.norm(way)), 1e-9)
                if normal[1] < 0:
                    normal = -normal
                off = abs(normal[0]) * w / 2 + abs(normal[1]) * h / 2 + self.gap / 2 + 0.06 * scale
                for share in (0.5, 0.3, 0.7):
                    point = pa + way * share
                    options += [(point + normal * off, True), (point - normal * off, True)]
                    normals += [normal, -normal]
            a, b = segments[0]
            options.append(((np.array(iso_point(*a)) + np.array(iso_point(*b))) / 2 * np.array([scale, -scale]), True))
            line = obstacles.lines[edge.ref()]

            def anchor(centre: np.ndarray, line: np.ndarray = line) -> np.ndarray:
                point = line[int(np.argmin(np.hypot(line[:, 0] - centre[0], line[:, 1] - centre[1])))]
                return hull_of_point(point)

            def pushed(options: list[tuple[np.ndarray, bool]] = options, normals: list[np.ndarray] = normals, k: int = k) -> list[np.ndarray]:
                return [obstacles.clear_of_all(size(k), c, d, self.gap) for (c, _), d in zip(options[:4], normals[:4])]

            choose(k, options, pushed, {edge.ref()}, anchor)
        out.bounds = self._placement_bounds(scale, labels, out, size)
        return out

    def _placement_bounds(self, scale: float, labels: list[_Label], out: _Placement, size: Callable[..., tuple[float, float]]) -> Box:
        """Everything placed: the drawing (with the room its raised blocks take), the labels
        (also where they ride when their block is raised), swatches and leader lines."""
        x0, y0, x1, y1 = self._bounds
        rects: list[Box] = [(x0 * scale, y0 * scale, x1 * scale, y1 * scale)]
        for k, centre in out.centres.items():
            rect = rect_of(centre, size(k, k not in out.on_top))
            rects.append(rect)
            lift = self._lift_max.get(labels[k].owner, 0.0) if labels[k].kind in ("block", "layer") and k not in out.swatches else 0.0
            lift = self._plate_lift_max.get(labels[k].owner, 0.0) if labels[k].kind == "group" else lift
            if lift > 1e-9:
                dy = lift * ISO_RISE * scale
                rects.append((rect[0], rect[1] + dy, rect[2], rect[3] + dy))
        rects += [rect_of(c, wh) for c, wh in out.swatches.values()]
        rects += [(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])) for _, a, b in out.leaders]
        return rect_union(rects)

    def _label_sides(self, stack_id: str) -> list[str]:
        """Where a stack's layer labels may go, preferred first: its ``label_side``, or for
        ``auto`` in 9:16 the list below it then the sides, in 16:9 the side away from the
        diagram's middle, the other side, then below."""
        side = next(s.label_side for s in self.params.stacks() if s.id == stack_id) or "auto"
        if side != "auto":
            return [side]
        hull = self._stack_hulls[stack_id]
        everything = rect_union([hull_box(h) for h in self._hulls.values()])
        outward = "left" if (hull[:, 0].min() + hull[:, 0].max()) / 2 < (everything[0] + everything[2]) / 2 - 1e-6 else "right"
        other = "right" if outward == "left" else "left"
        return ["below", outward, other] if self.is_portrait else [outward, other, "below"]

    def _layer_column(self, stack: Any, side: str, by_owner: dict[LabelKey, int], scale: float,
                      size: Callable[..., tuple[float, float]]) -> tuple[list[tuple[int, np.ndarray, tuple[np.ndarray, np.ndarray] | None, Any]], list[Box], bool]:
        """A stack's layer labels at its ``side``: in a column at its ``left`` or ``right``,
        spread apart, each with a leader line from its layer's side face; or ``below``: its
        caption under its foot and the layers listed under that, top layer first, each after a
        swatch of its colour. Returns the labels (index, centre, leader, swatch), the rectangles
        they take, and whether the caption was placed."""
        hull = self._stack_hulls[stack.id] * scale
        left, bottom, right, _top = hull_box(hull)
        rows: list[tuple[int, np.ndarray, tuple[np.ndarray, np.ndarray] | None, Any]] = []
        rects: list[Box] = []
        if side == "below":
            y = bottom - self.gap
            caption = by_owner.get(("stack", stack.id))
            if caption is not None:
                w, h = size(caption)
                centre = slide_out((w, h), ((left + right) / 2, (bottom + _top) / 2), (0.0, -1.0), hull, self.gap)
                rows.append((caption, centre, None, None))
                rects.append(rect_of(centre, (w, h)))
                y = centre[1] - h / 2 - 0.04
            entries = []
            for name in reversed(stack.layers):
                k = by_owner[("layer", name)]
                w, h = size(k)
                sw = self.swatch * size(k, False)[1]
                entries.append((k, w, h, sw))
            width = max(sw + self.swatch_gap + w for _, w, _, sw in entries)
            x0 = (left + right) / 2 - width / 2
            for k, w, h, sw in entries:
                cy = y - h / 2
                swatch = (np.array([x0 + sw / 2, cy]), (sw, sw / 2))
                centre = np.array([x0 + sw + self.swatch_gap + w / 2, cy])
                rows.append((k, centre, None, swatch))
                rects += [rect_of(centre, (w, h)), rect_of(*swatch)]
                y = cy - h / 2 - 0.02
            return rows, rects, caption is not None
        anchors = []
        for name in stack.layers:
            u, v = side_point(self.diagram_layout.blocks[name], side)
            anchors.append((by_owner[("layer", name)], np.array([u * scale, -v * scale])))
        ys = _spread([a[1] for _, a in anchors], [size(k)[1] for k, _ in anchors], 0.06)
        for (k, anchor), y in zip(anchors, ys):
            w, h = size(k)
            x = right + self.lead + w / 2 if side == "right" else left - self.lead - w / 2
            centre = np.array([x, y])
            rows.append((k, centre, (anchor, np.array([x - w / 2 if side == "right" else x + w / 2, y])), None))
            rects.append(rect_of(centre, (w, h)))
        return rows, rects, False

    # ----- drawing ---------------------------------------------------------------------------

    def _draw(self, plan: _Plan, body: Region) -> dict[str, Any]:
        """Every mobject, placed in the body: the floor, plates, connectors, blocks (in the
        view's draw order) and labels, and the groups the targets are made of."""
        layout = self.diagram_layout
        x0, y0, x1, y1 = plan.placement.bounds
        shift = body.center[:2] - np.array([(x0 + x1) / 2, (y0 + y1) / 2])
        to_scene = picture_to_scene(plan.scale, shift)
        s = self._shapes
        solids: dict[int, _Solid] = {}

        def drawn(build: Callable[[Callable[[str], str]], tuple[list[Any], str | None]]) -> Mobject:
            """A piece drawn from ``build(paint)`` (its shapes and outline ink with each colour
            turned by ``paint``), kept so actions can recolour it with its shading."""

            def made(paint: Callable[[str], str]) -> Mobject:
                shapes, ink = build(paint)
                return shapes_mobject(shapes, to_scene, ink=ink, stroke=self.stroke)

            mob = made(lambda color: color)
            solids[id(mob)] = _Solid(mob, made)
            return mob

        p = self.params
        # built a part at a time: the floor comes in with what stands on it (pieces added to this group)
        self._floor_cells = FloorCells(layout) if p.floor != "none" and (p.build == "each" or self._left_to_actions()) else None
        self._floor_shown: set[tuple[int, int]] = set()
        floor = VGroup() if self._floor_cells is not None else shapes_mobject(s.floor, to_scene, ink=None, stroke=self.stroke)
        floor.set_z_index(0)
        plates: dict[str, Mobject] = {}
        for gid, shapes in s.plates.items():
            box, fill = layout.plates[gid], shapes[-1].fill
            plates[gid] = drawn(lambda paint, box=box, fill=fill: (plate_shapes(box, paint(fill)), outline_ink(paint(fill))))
            plates[gid].set_z_index(1)
        edges: dict[int, VGroup] = {k: VGroup() for k in range(len(layout.edges))}
        self._arrows: dict[int, Mobject] = {}
        self._edge_lift = {k: (0.0, 0.0) for k in range(len(layout.edges))}   # how far up each connector's ends reach (raised blocks)
        for k in s.arrows:
            edge, color = layout.edges[k], self._edge_colors[k]
            arrow = drawn(lambda paint, edge=edge, color=color: (arrow_shapes(edge, paint(color)), None))
            edges[k].add(arrow.set_z_index(2))
            self._arrows[k] = arrow
        blocks: dict[str, Mobject] = {}
        self._pipe_depths: dict[int, list[float]] = {k: [] for k in range(len(layout.edges))}
        pipe_boxes = layout.pipe_boxes()
        #: each pipe's segments (by connector index): the piece drawn and its box on the ground
        self._pipe_pieces: dict[int, list[tuple[Mobject, Box3]]] = {}
        pieces: dict[int, Mobject] = {}
        ranks: dict[int, int] = {}
        for rank, (kind, key) in enumerate(layout.order()):
            if kind == "block":
                block, color = layout.blocks[key], self._colors[key]
                blocks[key] = drawn(lambda paint, block=block, color=color: (block_shapes(block, paint(color)), outline_ink(paint(color))))
                blocks[key].set_z_index(10 + rank)
            else:
                k = s.pipes[key][0]
                box, color = pipe_boxes[key], self._edge_colors[k]
                piece = drawn(lambda paint, box=box, color=color: (box_faces(box, paint(color)), outline_ink(paint(color))))
                edges[k].add(piece.set_z_index(10 + rank))
                ranks[key] = rank
                pieces[key] = piece
        for key in range(len(s.pipes)):   # pipe segments in path order, with the depth each is drawn at
            self._pipe_depths[s.pipes[key][0]].append(10 + ranks[key] + 0.5)
            self._pipe_pieces.setdefault(s.pipes[key][0], []).append((pieces[key], pipe_boxes[key]))
        texts: dict[LabelKey, VGroup] = {}
        self._label_text: dict[LabelKey, Mobject] = {}
        self._label_plate: dict[LabelKey, Mobject | None] = {}
        self._label_on_top: set[LabelKey] = set()
        self._label_moves: dict[LabelKey, bool] = {}
        self._label_leader: set[LabelKey] = set()
        self._labels = {lab.key: lab for lab in plan.labels}
        on_fill: dict[str, tuple[Mobject, Mobject]] = {}
        dark, light = self.theme.background, self.theme.color("text")
        place_ = plan.placement
        for k, label in enumerate(plan.labels):
            centre = place_.centres[k] + shift
            text = label.text.move_to(np.array([centre[0], centre[1], 0.0]))
            group = VGroup()
            plate = None
            if k in place_.on_top:
                drawn_block = blocks[label.owner]   # its top: a box's last face, a cylinder's top ellipse
                top_face = drawn_block[0][-1] if layout.blocks[label.owner].shape in ("cylinder", "database") else drawn_block[-1]
                text.set_color(readable_ink(rgb_to_hex(top_face.fill_rgbas[0, :3]), dark, light))
                on_fill[label.owner] = (text, top_face)
                self._label_on_top.add(label.key)
            else:
                plate = self._plate_for(text)
                group.add(plate.set_z_index(900))
            group.add(text.set_z_index(902))
            if k in place_.swatches:
                (sc, (sw, sh)) = place_.swatches[k]
                group.add(self._swatch(sc + shift, sw, sh, self._colors[label.owner]))
            texts[label.key] = group
            self._label_text[label.key] = text
            self._label_plate[label.key] = plate
            self._label_moves[label.key] = label.kind in ("block", "layer") and k not in place_.swatches
        for k, start, end in place_.leaders:
            label = plan.labels[k]
            line = Line(np.array([*(start + shift), 0.0]), np.array([*(end + shift), 0.0]))
            line.set_stroke(self.theme.color("dim"), width=2.0).set_z_index(899)
            dot = Dot(np.array([*(start + shift), 0.0]), radius=0.035, color=self.theme.color("dim")).set_z_index(899)
            texts[label.key].add_to_back(line, dot)
            self._label_leader.add(label.key)
        everything = VGroup(floor, *plates.values(), *edges.values(), *blocks.values(), *texts.values())
        self._unit = plan.scale
        if not plan.fits:   # at the readable size and still too big: the whole diagram smaller
            before, width = everything.get_center().copy(), everything.width
            shrink_to_fit(everything, body.width, body.height).move_to(body.center)
            factor, after = everything.width / max(width, 1e-9), everything.get_center().copy()
            inner = to_scene
            self._unit = plan.scale * factor

            def to_scene(u: float, v: float, inner: Any = inner) -> np.ndarray:
                return after + (inner(u, v) - before) * factor
        self._to_scene = to_scene
        self._solids = solids
        return {"floor": floor, "plates": plates, "edges": edges, "blocks": blocks, "texts": texts, "on_fill": on_fill}

    def _plate_for(self, text: Mobject) -> Mobject:
        """The plate behind a label beside what it names."""
        h = text.height + 2 * self.label_pad[1]
        plate = RoundedRectangle(width=text.width + 2 * self.label_pad[0], height=h, corner_radius=min(0.12, h / 2))
        return plate.set_fill(self.theme.background, opacity=self.plate_opacity).set_stroke(width=0).move_to(text.get_center())

    def _swatch(self, centre: np.ndarray, width: float, height: float, color: str) -> Mobject:
        """A small flat diamond in a layer's colour (the layer list under a stack)."""
        x, y = float(centre[0]), float(centre[1])
        diamond = Polygon([x - width / 2, y, 0], [x, y + height / 2, 0], [x + width / 2, y, 0], [x, y - height / 2, 0])
        return diamond.set_fill(color, opacity=1.0).set_stroke(outline_ink(color), width=self.stroke).set_z_index(901)

    # ----- targets and steps -------------------------------------------------------------------

    def _recolor(self, mobs: Sequence[Mobject], keys: Sequence[LabelKey] = ()) -> Callable[[Callable[[str], str]], dict[int, tuple[np.ndarray, np.ndarray]]] | None:
        """``Target.recolor`` for the solid pieces among ``mobs`` (blocks, plates, connectors);
        the plates behind the labels ``keys`` keep their colour (a highlighted label is its text
        in the colour on its plate, not a block of colour)."""
        pieces = [self._solids[id(m)] for m in mobs if id(m) in self._solids]
        if not pieces:
            return None
        plates = [m for key in keys if self._label_plate.get(key) is not None for m in self._label_plate[key].get_family() if isinstance(m, VMobject)]

        def recolor(paint: Callable[[str], str]) -> dict[int, tuple[np.ndarray, np.ndarray]]:
            out: dict[int, tuple[np.ndarray, np.ndarray]] = {id(m): (m.fill_rgbas[0, :3].copy(), m.stroke_rgbas[0, :3].copy()) for m in plates
                                                             if len(m.fill_rgbas) and len(m.stroke_rgbas)}
            for piece in pieces:
                for live, made in zip(piece.mobject.get_family(), piece.build(paint).get_family()):
                    if isinstance(live, VMobject) and isinstance(made, VMobject) and len(made.fill_rgbas) and len(made.stroke_rgbas):
                        out[id(live)] = (made.fill_rgbas[0, :3].copy(), made.stroke_rgbas[0, :3].copy())
            return out

        return recolor

    def _steps(self, heading: Mobject | None, parts: dict[str, Any]) -> None:
        """Targets, and the scene's own steps: the diagram in the first beat, or one item per
        step (``build: each``), leaving to the actions what a ``reveal`` or ``build`` names."""
        p = self.params
        layout = self.diagram_layout
        self._parts = parts
        self._heading = heading
        self._veiled: dict[Any, list[tuple[VMobject, np.ndarray, np.ndarray]]] = {}   # labels a focus faded out, with their colours
        texts = parts["texts"]
        self._style = p.entrance
        self._in: set[Any] = set()   # ("block", id), ("plate", gid), ("caption", key), ("edge", k), "floor"
        self._own = {name: 0.0 for name in layout.blocks}
        self._plate_lift = {gid: 0.0 for gid in layout.plates}
        self._gaps = {sid: s.gap for sid, s in layout.stacks.items()}
        self._lifted = {name: 0.0 for name in layout.blocks}
        self._plate_lifted = {gid: 0.0 for gid in layout.plates}
        self._shadows: dict[str, Mobject] = {}
        self._composite: dict[int, list[str]] = {}
        top = self.target("heading", heading, entrance=lambda: [FadeIn(heading, shift=DOWN * 0.15)]) if heading is not None else None
        self._block_targets: dict[str, Target] = {}
        for i, (block_id, *_rest) in enumerate(p.all_blocks(), start=1):
            mob = VGroup(parts["blocks"][block_id], *self._block_labels(block_id))
            fill = [parts["on_fill"][block_id]] if block_id in parts["on_fill"] else []
            self._block_targets[block_id] = self.target([f"block{i}", f"block:{block_id}"], mob, outline=parts["blocks"][block_id], on_fill=fill,
                                                        entrance=lambda b=block_id: self._arrivals([b]),
                                                        recolor=self._recolor([parts["blocks"][block_id]], self._keys_of([block_id])))
        for stack in p.stacks():
            caption = [texts[("stack", stack.id)]] if ("stack", stack.id) in texts else []
            layers = [layer.id for layer in stack.layers or ()]
            target = self.target(f"stack:{stack.id}", VGroup(*[self._block_targets[n].mobject for n in layers], *caption),
                                 entrance=lambda layers=layers, sid=stack.id: self._arrivals(layers, captions=[sid]),
                                 recolor=self._recolor([parts["blocks"][n] for n in layers], [*self._keys_of(layers), ("stack", stack.id)]),
                                 on_fill=[pair for n in layers for pair in self._block_targets[n].on_fill])
            self._composite[id(target)] = layers
        for group in p.groups:
            members = self._blocks_named(f"group:{group.id}")
            caption = [texts[("group", group.id)]] if ("group", group.id) in texts else []
            target = self.target(f"group:{group.id}", VGroup(parts["plates"][group.id], *caption, *[self._block_targets[n].mobject for n in members]),
                                 entrance=lambda members=members, gid=group.id: self._arrivals(members, plates=[gid]),
                                 recolor=self._recolor([parts["plates"][group.id], *[parts["blocks"][n] for n in members]],
                                                       [*self._keys_of(members), ("group", group.id)]),
                                 on_fill=[pair for n in members for pair in self._block_targets[n].on_fill])
            self._composite[id(target)] = members
        self._edge_targets: list[Target] = []
        for k, edge in enumerate(p.edges):
            mob = VGroup(parts["edges"][k], *([texts[("edge", edge.ref())]] if ("edge", edge.ref()) in texts else []))
            self._edge_targets.append(self.target(f"edge:{edge.ref()}", mob, entrance=lambda k=k: self._edge_arrivals([k], force=True),
                                                  recolor=self._recolor(list(parts["edges"][k]), [("edge", edge.ref())])))
        everything = [b for b, *_ in p.all_blocks()]
        whole = VGroup(parts["floor"], *parts["plates"].values(), *parts["edges"].values(), *[t.mobject for t in self._block_targets.values()],
                       *[texts[key] for key in texts if key[0] in ("stack", "group")])
        diagram = self.target("diagram", whole, entrance=lambda: self._arrivals(everything, plates=list(layout.plates), floor=True, edges_too=True),
                              recolor=self._recolor([*parts["plates"].values(), *[m for g in parts["edges"].values() for m in g], *parts["blocks"].values()],
                                                    list(texts)),
                              on_fill=list(parts["on_fill"].values()))
        self._composite[id(diagram)] = everything
        self._waiting = self._left_to_actions()
        order = [key for kind, key in layout.order() if kind == "block"]
        free = [b for b in order if ("block", b) not in self._waiting]
        steps: list[Callable[[], list[Animation]]]
        if p.build == "together":
            steps = [lambda: (self.entrance(top) if top is not None else []) + self._arrivals(free, floor=True, edges_too=True)]
        else:
            items = [[b for b in self._blocks_named(f"block:{blk.id}" if not blk.is_stack else f"stack:{blk.id}") if b in free] for blk in p.blocks]
            items = [item for item in items if item]
            first = items[0] if items else []
            steps = [lambda: (self.entrance(top) if top is not None else []) + self._arrivals(first, floor=True, edges_too=True)]
            steps += [lambda item=item: self._arrivals(item, edges_too=True) for item in items[1:]]
        self.reveal(steps, fraction=0.8, cap=2.0)
        self.finish()

    @staticmethod
    def _keys_of(blocks: Sequence[str]) -> list[LabelKey]:
        """The label keys a block or layer may have."""
        return [(kind, b) for b in blocks for kind in ("block", "layer")]

    def _block_labels(self, block_id: str) -> list[Mobject]:
        texts = self._parts["texts"]
        return [texts[(k, block_id)] for k in ("block", "layer") if (k, block_id) in texts]

    def _left_to_actions(self) -> set[Any]:
        """What the scene's own steps leave to ``reveal`` and ``build`` actions: the blocks (and
        layers) they name, directly or as part of a stack, group or the diagram; the plates and
        captions of the stacks and groups they name; the connectors they name. A connector to a
        block that waits comes in with it."""
        names = type(self).target_names(self.params)
        patterns = [pattern for kind in ("reveal", "build") for use in self.action_uses(kind) for pattern in use.config.targets()]
        named = [n for n in names if any(fnmatchcase(n, pattern) for pattern in patterns)]
        out: set[Any] = set()
        for name in named:
            kind = self.target_kind(name)
            out |= {("block", b) for b in self._blocks_named(name)}
            if kind == "stack":
                out.add(("caption", ("stack", name[len("stack:"):])))
            elif kind == "group":
                gid = name[len("group:"):]
                out |= {("plate", gid), ("caption", ("group", gid))}
            elif kind == "edge":
                out.add(("edge", next(k for k, e in enumerate(self.params.edges) if f"edge:{e.ref()}" == name)))
        return out

    def is_shown(self, target: Target | str) -> bool:
        """A stack, group or the diagram is shown once all its blocks are."""
        found = self.find_targets(target) if isinstance(target, str) else [target]
        composite = getattr(self, "_composite", {})
        if found and all(id(t) in composite for t in found):
            return any(all(("block", b) in self._in for b in composite[id(t)]) for t in found)
        return super().is_shown(target)

    def _arrivals(self, blocks: Sequence[str], *, plates: Sequence[str] = (), captions: Sequence[str] = (), floor: bool = False,
                  edges_too: bool = True, style: str | None = None) -> list[Animation]:
        """Bring ``blocks`` in (back to front, in ``style``: the scene's ``entrance`` unless
        given), with what comes with them: the floor, their plates and the captions of their
        groups and stacks unless an action waits to show those (``plates`` and ``captions``: shown
        whatever waits), and the connectors whose ends are then all shown."""
        parts = self._parts
        layout = self.diagram_layout
        style = style or self._style
        ground: list[Mobject] = []
        if floor and "floor" not in self._in:
            self._in.add("floor")
            if self._floor_cells is None:
                ground.append(parts["floor"])
        coming = [b for b in [key for kind, key in layout.order() if kind == "block"] if b in blocks and ("block", b) not in self._in]
        for b in coming:
            self._in.add(("block", b))
        if self._floor_cells is not None and coming:   # the floor under what is there now
            piece = self._floor_piece({self._item_of(b) for b in layout.blocks if ("block", b) in self._in})
            if piece is not None:
                ground.append(piece)
        wanted_plates = list(plates) + [layout.blocks[b].group for b in coming if layout.blocks[b].group and ("plate", layout.blocks[b].group) not in self._waiting]
        for gid in dict.fromkeys(wanted_plates):
            if gid and ("plate", gid) not in self._in:
                self._in.add(("plate", gid))
                ground.append(parts["plates"][gid])
                key = ("group", gid)
                if key in parts["texts"] and (gid in plates or ("caption", key) not in self._waiting):
                    self._in.add(("caption", key))
                    ground.append(parts["texts"][key])
        stacks = list(captions) + [layout.blocks[b].stack for b in coming if layout.blocks[b].stack]
        for sid in dict.fromkeys(stacks):
            key = ("stack", sid)
            if key in parts["texts"] and ("caption", key) not in self._in and (sid in captions or ("caption", key) not in self._waiting):
                self._in.add(("caption", key))
                ground.append(parts["texts"][key])
        anims: list[Animation] = [FadeIn(VGroup(*ground))] if ground else []
        arrivals = [self._enter(b, style) for b in coming]
        if arrivals:
            anims.append(LaggedStart(*arrivals, lag_ratio=0.9 if style == "grow" else 0.12))   # grown: each on the one below
        if edges_too:
            ready = [k for k in range(len(layout.edges)) if ("edge", k) not in self._in and ("edge", k) not in self._waiting]
            links = self._edge_arrivals(ready, force=False)
            if links:
                anims.append(LaggedStart(*links, lag_ratio=0.1))
        return [Succession(*anims)] if len(anims) > 1 else anims

    def _floor_piece(self, items: set[str]) -> Mobject | None:
        """The floor not shown yet under ``items`` (the floor of a diagram built a part at a
        time), added to the floor's group; ``None`` when there is none."""
        cells = self._floor_cells
        assert cells is not None
        new = cells.under(items) - self._floor_shown
        if not new:
            return None
        shapes = cells.shapes(sorted(new), self._floor_shown, floor=self.params.floor, background=self.theme.background, text=self.theme.color("text"))
        self._floor_shown |= new
        piece = shapes_mobject(shapes, self._to_scene, ink=None, stroke=self.stroke).set_z_index(0)
        self._parts["floor"].add(piece)
        return piece

    def _edge_arrivals(self, ks: Sequence[int], force: bool) -> list[Animation]:
        """The connectors ``ks`` whose ends are both shown fade in (``force``: whatever their ends)."""
        anims = []
        for k in ks:
            edge = self.diagram_layout.edges[k]
            ends = [self._end_blocks(edge.source), self._end_blocks(edge.target)]
            if ("edge", k) in self._in or not (force or all(any(("block", b) in self._in for b in end) for end in ends)):
                continue
            self._in.add(("edge", k))
            anims.append(FadeIn(self._edge_targets[k].mobject))
        return anims

    def _end_blocks(self, name: str) -> list[str]:
        layout = self.diagram_layout
        return list(layout.stacks[name].layers) if name in layout.stacks else [name]

    def _enter(self, block: str, style: str) -> Animation:
        """One block (with its labels) coming in: dropping in from above, growing up from its
        ground, or fading in."""
        target = self._block_targets[block]
        mob = target.mobject
        if style == "fade":
            return FadeIn(mob)
        rise = UP * self.drop * ISO_RISE * self._unit
        if style == "drop":
            return FadeIn(mob, shift=-rise)
        placed = self.diagram_layout.blocks[block]
        box = placed.box
        height = box.z1 - box.z0
        drawn = self._parts["blocks"][block]
        color = self._colors[block]
        lift = self._lifted[block]

        def build(t: float) -> Mobject:
            grown = PlacedBlock(placed.id, placed.shape, Box3(box.x0, box.y0, box.z0, box.x1, box.y1, box.z0 + height * t))
            shapes = block_shapes(grown, color, lift=lift)
            return shapes_mobject(shapes, self._to_scene, ink=outline_ink(color), stroke=self.stroke)

        riders = [self._label_text[key] for key in self._label_on_top if key[1] == block]
        labels = [group for group in self._block_labels(block)]
        return GrowBlock(mob, drawn, build, UP * height * ISO_RISE * self._unit, riders, labels, run_time=1.0)

    # ----- actions (scenes/iso_actions.py) -----------------------------------------------------

    def iso_blocks_of(self, targets: Sequence[Target]) -> list[str]:
        """The blocks and layers ``targets`` cover, in order."""
        out: list[str] = []
        for t in targets:
            for name in t.names:
                if self.target_kind(name) in ("block", "stack", "group", "diagram"):
                    out += [b for b in self._blocks_named(name) if b not in out]
                    break
        return out

    def iso_build(self, targets: Sequence[Target], style: str) -> list[Animation]:
        """Bring the hidden ``targets`` in, their blocks in ``style``."""
        anims: list[Animation] = []
        for t in targets:
            kind = self.target_kind(t.name)
            if kind == "edge":
                anims += self._edge_arrivals([self._edge_targets.index(t)], force=True)
            elif kind == "heading":
                anims += self.entrance(t)
            else:
                blocks = self.iso_blocks_of([t])
                plates = [t.name[len("group:"):]] if kind == "group" else list(self.diagram_layout.plates) if kind == "diagram" else []
                captions = [t.name[len("stack:"):]] if kind == "stack" else []
                anims += self._arrivals(blocks, plates=plates, captions=captions, floor=kind == "diagram", style=style)
        return anims

    def iso_raise(self, targets: Sequence[Target], by: float | None, *, down: bool = False) -> list[Animation]:
        """Raise (``down``: lower; ``by`` ``None``: back to the ground) the targets' blocks;
        raising a layer raises the layers above it; a group's plate rises with its members."""
        blocks = self.iso_blocks_of(targets)
        groups = {t.name[len("group:"):] for t in targets if self.target_kind(t.name) == "group"}
        for b in self._bottoms(blocks):
            self._own[b] = 0.0 if by is None else max(0.0, self._own[b] + (-by if down else by))
        for gid in groups:
            self._plate_lift[gid] = 0.0 if by is None else max(0.0, self._plate_lift[gid] + (-by if down else by))
        return self._settle()

    def iso_restore(self, targets: Sequence[Target], own: dict[str, float], plates: dict[str, float]) -> list[Animation]:
        """The targets' lifts back to ``own`` and ``plates`` (from :meth:`iso_lift_state`; an
        action's ``until``)."""
        for b in self._bottoms(self.iso_blocks_of(targets)):
            self._own[b] = own[b]
        for t in targets:
            if self.target_kind(t.name) == "group":
                gid = t.name[len("group:"):]
                self._plate_lift[gid] = plates[gid]
        return self._settle()

    def iso_lift_state(self) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        """The raises of the blocks and plates and the stacks' gaps now."""
        return dict(self._own), dict(self._plate_lift), dict(self._gaps)

    def iso_explode(self, targets: Sequence[Target], gap: float | None, gaps: dict[str, float] | None = None) -> list[Animation]:
        """Set the gap between the layers of the targets' stacks: ``gap``, else from ``gaps``
        (by stack), else their own."""
        layout = self.diagram_layout
        for sid in {layout.blocks[b].stack for b in self.iso_blocks_of(targets)} - {None}:
            self._gaps[sid] = gap if gap is not None else (gaps or {}).get(sid, layout.stacks[sid].gap)
        return self._settle()

    def _settle(self) -> list[Animation]:
        """Move every block, plate and label that rides with them to the lifts now wanted, with
        a shadow under a raised block or plate."""
        layout = self.diagram_layout
        lifts = self._lifts_of(self._own, self._gaps)
        rise = UP * ISO_RISE * self._unit
        anims: list[Animation] = []
        shown = {id(m) for m in self.get_mobject_family_members()}

        def move(mob: Mobject, dz: float) -> None:
            if abs(dz) < 1e-9:
                return
            if any(id(m) in shown for m in mob.get_family()):
                anims.append(LiftMove(mob, rise * dz))
            else:
                mob.shift(rise * dz)

        for name, block in layout.blocks.items():
            dz = lifts[name] - self._lifted[name]
            move(self._parts["blocks"][name], dz)
            for key in [("block", name), ("layer", name)]:
                if key in self._parts["texts"] and self._label_moves[key]:
                    move(self._parts["texts"][key], dz)
            self._lifted[name] = lifts[name]
            if block.level == 0:
                anims += self._shadow(name, lifts[name], block.box, ("block", name) in self._in, block.shape)
        for gid, box in layout.plates.items():
            dz = self._plate_lift[gid] - self._plate_lifted[gid]
            move(self._parts["plates"][gid], dz)
            self._parts["plates"][gid].set_z_index(9 if self._plate_lift[gid] > 1e-9 else 1)   # raised: over the arrows on the floor under it
            if ("group", gid) in self._parts["texts"]:   # its caption by its front edge goes with it
                move(self._parts["texts"][("group", gid)], dz)
            self._plate_lifted[gid] = self._plate_lift[gid]
            anims += self._shadow(gid, self._plate_lift[gid], box, ("plate", gid) in self._in, "box")
        for k, edge in enumerate(layout.edges):   # a connector (flat arrow or pipe) tilts up to its raised ends
            wanted = (lifts[self._end_blocks(edge.source)[0]], lifts[self._end_blocks(edge.target)[0]])
            before = self._edge_lift[k]
            if np.allclose(wanted, before, atol=1e-9):
                continue
            self._edge_lift[k] = wanted
            color = self._edge_colors[k]
            pieces: list[tuple[Mobject, Callable[[list[float]], Mobject]]] = []
            if k in self._arrows:
                pieces.append((self._arrows[k], lambda ends, edge=edge, color=color:
                               shapes_mobject(ramped(arrow_shapes(edge, color), edge, *ends), self._to_scene, ink=None, stroke=self.stroke)))
            for piece, box in self._pipe_pieces.get(k, []):   # each segment's box sheared along the slope
                pieces.append((piece, lambda ends, edge=edge, color=color, box=box:
                               shapes_mobject(ramped(box_faces(box, color), edge, *ends), self._to_scene, ink=outline_ink(color), stroke=self.stroke)))
            for piece, make in pieces:
                def build(t: float, make: Callable[[list[float]], Mobject] = make, before: tuple[float, float] = before,
                          wanted: tuple[float, float] = wanted) -> Mobject:
                    return make([a + (b - a) * t for a, b in zip(before, wanted)])

                if any(id(m) in shown for m in piece.get_family()):
                    anims.append(Reshape(piece, build))
                else:
                    for m, made in zip(piece.get_family(), build(1.0).get_family()):
                        m.points = made.points.copy()
        return anims

    def _shadow(self, name: str, lift: float, box: Box3, visible: bool, shape: str) -> list[Animation]:
        """The shadow under block or plate ``name`` raised ``lift`` cells: darker as it rises."""
        to = self.shadow_opacity * min(1.0, lift / self.shadow_lift) if visible else 0.0
        shadow = self._shadows.get(name)
        if shadow is None:
            if to <= 0:
                return []
            if shape in ("cylinder", "database"):
                r = min(box.x1 - box.x0, box.y1 - box.y0) / 2
                cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
                ground = [(cx + r * np.cos(a), cy + r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 32, endpoint=False)]
            else:
                ground = [(box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)]
            shadow = Polygon(*[self._to_scene(*iso_point(x, y, box.z0)) for x, y in ground])
            floor_color = mix_colors(self.theme.color("text"), self.theme.background, 0.05)
            shadow.set_fill(mix_colors("#000000", floor_color, 0.6), opacity=0.0).set_stroke(width=0).set_z_index(1.5)
            self._shadows[name] = shadow
            self.add(shadow)
        if abs(float(shadow.get_fill_opacity()) - to) < 1e-6:
            return []
        return [FillFade(shadow, to)]

    def iso_flow(self, targets: Sequence[Target], *, count: int, style: str, color: str, back: bool, chain: bool) -> list[Animation]:
        """Dots or packets moving along the targets' connectors (one after another with
        ``chain``)."""
        layout = self.diagram_layout
        flows: list[Animation] = []
        for t in targets:
            if self.target_kind(t.name) != "edge":
                continue
            k = self._edge_targets.index(t)
            edge = layout.edges[k]
            points = list(reversed(edge.points)) if back else list(edge.points)
            pipe = edge.style == "pipe"
            up = (PIPE_HEIGHT if pipe else 0.0) + (self.packet / 2 if style == "packets" else self.dot_radius * 0.6)
            total = sum(float(np.linalg.norm(np.subtract(b, a))) for a, b in zip(points, points[1:]))
            lengths = np.cumsum([0.0] + [float(np.linalg.norm(np.subtract(b, a))) for a, b in zip(points, points[1:])])
            depths = list(reversed(self._pipe_depths[k])) if back else self._pipe_depths[k]
            rise = tuple(reversed(self._edge_lift[k])) if back else self._edge_lift[k]   # up to raised ends

            def at(s: float, points: list[Any] = points, lengths: np.ndarray = lengths, total: float = total, up: float = up,
                   rise: tuple[float, float] = rise) -> np.ndarray:
                d = s * total
                j = int(min(np.searchsorted(lengths, d, side="right") - 1, len(points) - 2))
                share = (d - lengths[j]) / max(lengths[j + 1] - lengths[j], 1e-9)
                a, b = np.array(points[j]), np.array(points[j + 1])
                x, y, z = a + (b - a) * share
                return self._to_scene(*iso_point(x, y, z + up + rise[0] + (rise[1] - rise[0]) * s))

            def depth(s: float, lengths: np.ndarray = lengths, total: float = total, depths: list[float] = depths) -> float:
                if not depths:
                    return 2.5
                j = int(min(np.searchsorted(lengths, s * total, side="right") - 1, len(depths) - 1))
                return depths[max(j, 0)]

            dots = VGroup(*[self._flow_dot(style, color) for _ in range(count)])
            flows.append(FlowDots(dots, at, depth, self.flow_spacing))
        if chain and len(flows) > 1:
            return [Succession(*flows)]
        return flows

    def _flow_dot(self, style: str, color: str) -> Mobject:
        """A dot (a small disc) or a packet (a small cube in the view) in ``color``."""
        if style == "packets":
            half = self.packet / 2
            return shapes_mobject(box_faces(Box3(-half, -half, -half, half, half, half), color), picture_to_scene(self._unit, (0.0, 0.0)),
                                  ink=outline_ink(color), stroke=self.stroke)
        dot = Circle(radius=max(self.dot_radius * self._unit, 0.05))
        return dot.set_fill(color, opacity=1.0).set_stroke(outline_ink(color), width=self.stroke)

    def iso_relabel(self, target: Target, text: str) -> tuple[list[Animation], str | None]:
        """The label ``target`` shows (:meth:`_label_keys`) turned into ``text``; also returns
        the text it showed (``None`` when the target has no label)."""
        key = self._label_keys().get(target.name)
        if key is None or key not in self._label_text:
            return [], None
        old = self._label_text[key]
        before = _words(old)
        new = self._labels[key].make(text)
        new.move_to(old.get_center()).set_z_index(902)
        old_inks = {rgb_to_hex(m.fill_rgbas[0, :3]) for m in old.family_members_with_points() if isinstance(m, VMobject)}
        new_inks = {rgb_to_hex(m.fill_rgbas[0, :3]) for m in new.family_members_with_points() if isinstance(m, VMobject)}
        if old_inks and (key in self._label_on_top or (len(old_inks) == 1 and old_inks != new_inks)):   # its block's ink, or a highlight's colour
            new.set_color(next(iter(old_inks)))
        veiled = key in self._veiled   # faded out by a focus: the new text comes back with it
        if veiled:
            gone = {id(m) for m in old.get_family()}
            self._veiled[key] = [look for look in self._veiled[key] if id(look[0]) not in gone] + \
                [(m, m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in new.get_family() if isinstance(m, VMobject)]
        keep_opacity(new, old)
        group = self._parts["texts"][key]
        plate = self._label_plate[key]
        new_plate = None
        if plate is not None:
            new_plate = self._plate_for(new).set_z_index(plate.z_index)
            if veiled:
                new_plate.set_fill(opacity=0.0)
        self._label_text[key] = new
        for t in self.targets:
            if any(pair[0] is old for pair in t.on_fill):
                t.on_fill = tuple((new, shape) if words is old else (words, shape) for words, shape in t.on_fill)
        if not self.on_screen_parts(old):   # not shown yet: changed at once
            group.remove(old)
            group.add(new)
            if plate is not None:
                plate.become(new_plate)
            return [], before
        anims: list[Animation] = [Transform(old, new.copy())]   # the old text morphs; the new one takes its place when it ends
        if plate is not None:
            anims.append(Transform(plate, new_plate))
        return [*anims, SwapAtEnd(group, old, new)], before

    def iso_focus_view(self, targets: Sequence[Target], padding: float, scale: float | None) -> tuple[float, np.ndarray]:
        """The camera view (width, centre) that shows ``targets`` with ``padding`` around them
        (``scale``: that magnification), placed in the safe area (clear of the margins and of
        reserved overlays such as captions); the whole frame for ``diagram`` or when they fill it."""
        fw, fh = self.frame_width, self.frame_height
        if any(t.name == "diagram" for t in targets):
            return fw, np.zeros(3)
        parts = [m for t in targets for m in (self.on_screen_parts(t) or [t.mobject])]
        group = Group(*parts)
        area = self.safe_area
        pad = 2 * padding * min(area.width, area.height)   # a share of the shorter side, both ways (9:16: not most of its width)
        factor = scale if scale is not None else min(3.0, (area.width - pad) / max(group.width, 1e-6), (area.height - pad) / max(group.height, 1e-6))
        if factor <= 1.02:
            return fw, np.zeros(3)
        width, height = fw / factor, fh / factor
        wanted = group.get_center()[:2] - np.asarray(area.center[:2], dtype=float) / factor   # its middle on the area's
        center = view_center_within(self.camera_bounds(), wanted, width, height)
        return width, np.array([*center, 0.0])

    def iso_veil(self, width: float, centre: np.ndarray) -> list[Animation]:
        """The labels (and the heading) that a view ``width`` wide at ``centre`` would cut at its
        edge, or leave out, fade out; those faded so that the view shows whole fade back in.
        Blocks may be cut by the view's edge, a label never is (``focus``)."""
        height = width * self.frame_height / self.frame_width
        margin = 0.01 * width
        x0, x1 = centre[0] - width / 2 + margin, centre[0] + width / 2 - margin
        y0, y1 = centre[1] - height / 2 + margin, centre[1] + height / 2 - margin
        texts = dict(self._parts["texts"])
        if self._heading is not None:
            texts[("heading", "")] = self._heading
        anims: list[Animation] = []
        for key, group in texts.items():
            if not self.on_screen_parts(group):
                continue
            whole = x0 <= group.get_left()[0] and group.get_right()[0] <= x1 and y0 <= group.get_bottom()[1] and group.get_top()[1] <= y1
            if not whole and key not in self._veiled:
                looks = [(m, m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in group.get_family() if isinstance(m, VMobject)]
                self._veiled[key] = looks
                anims.append(Veil(group, looks, hide=True))
            elif whole and key in self._veiled:
                anims.append(Veil(group, self._veiled.pop(key), hide=False))
        return anims

    # ----- lint (DESIGN.md §90.10) -----------------------------------------------------------

    def layout_keys(self, beat_id: str | None) -> dict[str, Any]:
        """What the layout dump adds to a still: ``iso_diagram`` with the labels shown (text,
        whose, box in pixels, on a block's top, with a leader line) and the outlines of the
        blocks and plates and the paths of the connectors on screen, for lint ``iso_labels``."""
        if not hasattr(self, "_label_text"):
            return {}
        shown = {id(m) for m in self.get_mobject_family_members()}
        cam = self.camera

        def px(mob: Mobject, points: np.ndarray) -> np.ndarray:
            return np.asarray(cam.points_to_subpixel_coords(mob, np.asarray(points, dtype=float)), dtype=float)

        def visible(mob: Mobject) -> bool:
            members = [m for m in mob.family_members_with_points() if isinstance(m, VMobject)]
            return bool(members) and any(id(m) in shown for m in members) and max(float(np.max(m.fill_rgbas[:, 3])) for m in members) > 0.3

        def outline(mob: Mobject) -> list[list[float]]:
            points = np.vstack([m.points for m in mob.family_members_with_points()])
            return [[round(float(x), 1), round(float(y), 1)] for x, y in convex_hull(px(mob, points))]

        labels = []
        for key, text in self._label_text.items():
            if not visible(text):
                continue
            plate = self._label_plate.get(key)
            box_mob = plate if plate is not None else text
            xy = px(box_mob, box_mob.get_all_points())
            labels.append({"kind": key[0], "owner": key[1], "text": _words(text),
                           "box": [round(float(v), 1) for v in (*xy.min(axis=0), *xy.max(axis=0))],
                           "on_top": key in self._label_on_top, "leader": key in self._label_leader or key[0] == "layer"})
        blocks = [{"id": name, "outline": outline(mob)} for name, mob in self._parts["blocks"].items() if visible(mob)]
        plates = [{"id": gid, "outline": outline(mob)} for gid, mob in self._parts["plates"].items() if visible(mob)]
        stacks = [{"id": sid, "layers": list(s.layers)} for sid, s in self.diagram_layout.stacks.items()]
        edges = []
        for k, edge in enumerate(self.diagram_layout.edges):
            mob = self._parts["edges"][k]
            if not visible(mob):
                continue
            samples = edge.samples(0.25)
            low, high = self._edge_lift[k]   # tilted up to raised ends, as drawn
            points = np.array([self._to_scene(*iso_point(x, y, z + low + (high - low) * s / max(len(samples) - 1, 1)))
                               for s, (x, y, z) in enumerate(samples)])
            edges.append({"ref": edge.ref(), "source": edge.source, "target": edge.target,
                          "points": [[round(float(x), 1), round(float(y), 1)] for x, y in px(mob, points)]})
        frame = getattr(cam, "frame", None)
        zoom = self.frame_width / float(frame.width) if frame is not None and float(frame.width) > 1e-9 else 1.0   # a focus magnifies
        return {"iso_diagram": {"labels": labels, "blocks": blocks, "plates": plates, "stacks": stacks, "edges": edges, "zoom": round(zoom, 4)}}


def _words(text: Mobject) -> str:
    """The characters a label shows."""
    inner = getattr(text, "lines_text", text)
    return str(getattr(inner, "original_text", ""))


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
