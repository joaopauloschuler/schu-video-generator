"""``diagram`` (alias ``flowchart``): a directed graph laid out in layers, revealed step by step."""

import difflib
import logging
import re
from collections.abc import Callable
from typing import Any, Literal, NamedTuple

import numpy as np

from vidgen.api import *

from .actions import dim_to

log = logging.getLogger("vidgen.scenes")

Shape = Literal["box", "round", "pill", "circle", "diamond", "cylinder"]

#: Node ids: letters, digits, spaces, ``_``, ``.`` and ``-`` (no ``->`` or ``:``, which the edge
#: shorthand uses), not starting or ending with a space or ``-``.
_ID = re.compile(r"^\w(?:[\w .\-]*[\w.])?$")
#: The arrows of the edge shorthand: ``->`` solid, ``-->`` dashed.
_ARROW = re.compile(r"\s*(-->|->)\s*")
#: Outline used for routing edges to each node shape.
_OUTLINE = {"box": "box", "round": "box", "cylinder": "box", "pill": "stadium", "circle": "ellipse", "diamond": "diamond"}


def edge_ref(source: str, target: str) -> str:
    """The name of an edge in ``steps``, ``highlight`` and targets: ``from->to``."""
    return f"{source}->{target}"


def parse_edges(text: str) -> list[dict[str, Any]]:
    """The edges a shorthand string means: ``"a -> b"``, ``"a -> b: label"``, ``"a --> b"``
    (dashed) or a chain ``"a -> b -> c"`` (one edge per arrow; a label needs a single arrow)."""
    parts = _ARROW.split(text.strip())
    if len(parts) < 3:
        raise ValueError(f"{text!r} is not an edge; write 'from -> to', 'from -> to: label' or 'from --> to' (dashed)")
    ids, arrows = parts[0::2], parts[1::2]
    label = ""
    if ":" in ids[-1]:
        ids[-1], label = (s.strip() for s in ids[-1].split(":", 1))
        if len(arrows) > 1:
            raise ValueError(f"{text!r}: a label needs a single edge ('from -> to: label'), not a chain")
    out = []
    for a, b, arrow in zip(ids, ids[1:], arrows):
        if not a or not b:
            raise ValueError(f"{text!r}: an arrow needs a node id on both sides")
        edge: dict[str, Any] = {"from": a, "to": b, "style": "dashed" if arrow == "-->" else "solid"}
        if label:
            edge["label"] = label
        out.append(edge)
    return out


class DiagramNode(SceneParams):
    """A node: ``{id, label?, shape?, icon?, color?}`` (a plain string is its id and label)."""

    also_accepts = (str,)

    id: str
    """Name used by edges, steps and targets (letters, digits, spaces, _ . -)."""
    label: str = ""
    """Text in the node (default: the id; wrapped to fit)."""
    shape: Shape | None = None
    """box, round, pill, circle, diamond or cylinder (default: the scene's shape)."""
    icon: IconName | None = None
    """Optional icon with the label: above it in left-to-right layouts, circles and diamonds, else beside it."""
    color: ThemeColor | None = None
    """Outline, tint and icon colour (default: the scene's node_color)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"id": data} if isinstance(data, str) else data

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        value = value.strip()
        if not _ID.match(value):
            raise ValueError(f"node id {value!r}: use letters, digits, spaces, '_', '.' and '-' (no '->' or ':')")
        return value

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A plain string is also a node (JSON Schema ``anyOf`` string | object)."""
        return {"anyOf": [{"type": "string", "minLength": 1}, handler(core_schema)]}

    def text(self) -> str:
        """The label as shown."""
        return self.label or self.id


class DiagramEdge(SceneParams):
    """An edge: ``{from, to, label?, style?, color?}``, or the shorthand ``"a -> b: label"``."""

    also_accepts = (str,)

    source: str = Field(alias="from")
    """Node id the edge starts at."""
    to: str
    """Node id the arrow points to."""
    label: str = ""
    """Optional text on the edge, near its start."""
    style: Literal["solid", "dashed"] = "solid"
    """solid or dashed line."""
    color: ThemeColor | None = None
    """Line colour (default: the scene's edge_color)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if isinstance(data, str):
            edges = parse_edges(data)
            if len(edges) > 1:
                raise ValueError(f"{data!r} is a chain of {len(edges)} edges; list it under the scene's edges")
            return edges[0]
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
        """``from->to``."""
        return edge_ref(self.source, self.to)


StepRefs = list[str] | str


@scene("diagram")
class Diagram(NarratedScene):
    """A flowchart or any directed graph, laid out automatically in layers (left to right in
    16:9 and square frames, top to bottom in 9:16), revealed step by step: by default one node
    per step in layout order, each after the edges that lead to it grow in from their source
    (``reveal: layers`` one layer per step, ``all`` everything at once, or explicit ``steps``).
    Steps are spread over the beats; a ``highlight`` path adds a last step. Registered also as
    ``flowchart``.

    Action targets: ``heading``, ``node<N>`` (1-based, in the order listed), ``node:<id>`` and
    ``edge:<from>-><to>``.
    """

    outro = 0.5
    target_patterns = ("heading", "node<N>", "node:<id>", "edge:<from>-><to>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``heading`` (if any), ``node<N>`` and ``node:<id>`` per node, ``edge:<from>-><to>``
        per edge."""
        names = ["heading"] if params.heading else []
        for i, node in enumerate(params.nodes, start=1):
            names += [f"node{i}", f"node:{node.id}"]
        return names + [f"edge:{e.ref()}" for e in params.edges]

    class Params(SceneParams):
        nodes: list[DiagramNode] = Field(min_length=1, max_length=30)
        """The nodes: an id string, or {id, label?, shape?, icon?, color?} (1-30; up to ~12 read well)."""
        edges: list[DiagramEdge] = Field(default_factory=list, max_length=60)
        """The edges: 'a -> b', 'a -> b: label', 'a --> b' (dashed), chains 'a -> b -> c', or {from, to, label?, style?, color?}."""
        heading: str = ""
        """Optional heading above the diagram."""
        direction: Literal["auto", "LR", "TB"] = "auto"
        """LR: layers left to right; TB: top to bottom; auto: LR in landscape and square frames, TB in portrait (the other one if it keeps text much larger)."""
        routing: Literal["curved", "straight", "orthogonal"] = "curved"
        """Edge lines: curved (smooth S-curves), straight (polylines) or orthogonal (right angles)."""
        reveal: Literal["nodes", "layers", "all"] = "nodes"
        """nodes: one node per step in layout order (edges into it first); layers: one layer per step; all: everything in one step."""
        steps: list[StepRefs] | None = None
        """Explicit steps instead of reveal: per step a node id or edge 'a->b', or a list of them; edges between shown nodes come along; anything not listed comes in one more step."""
        highlight: list[str] = Field(default_factory=list)
        """A path or set to emphasise in a last step: node ids (with the edges between consecutive ones) and edges 'a->b'; the rest dims."""
        shape: Shape = "round"
        """Default node shape: box, round, pill, circle, diamond or cylinder."""
        node_color: ThemeColor = "primary"
        """Default node outline, tint and icon colour."""
        label_color: ThemeColor = "text"
        """Node label colour."""
        edge_color: ThemeColor = "dim"
        """Default edge colour."""
        edge_label_color: ThemeColor = "dim"
        """Edge label colour."""
        heading_color: ThemeColor = "text"
        """Heading colour."""
        highlight_color: ThemeColor = "highlight"
        """Outline and line colour of the highlighted nodes and edges."""
        size: ThemeSize = "body"
        """Node label size (up to 1.3x larger in a small diagram; reduced, not below the readable minimum, when space is short)."""
        edge_label_size: ThemeSize = "caption"
        """Edge label size (reduced with the node labels)."""
        heading_size: ThemeSize = "heading"
        """Heading size."""

        @field_validator("edges", mode="before")
        @classmethod
        def _chains(cls, value: Any) -> Any:
            if not isinstance(value, list):
                return value
            out: list[Any] = []
            for item in value:
                out += parse_edges(item) if isinstance(item, str) else [item]
            return out

        @model_validator(mode="after")
        def _references(self) -> SceneParams:
            ids = [n.id for n in self.nodes]
            seen: set[str] = set()
            for i, node_id in enumerate(ids):
                if node_id in seen:
                    raise ValueError(f"nodes[{i}]: id {node_id!r} is used twice")
                seen.add(node_id)
            refs: set[str] = set()
            for i, edge in enumerate(self.edges):
                for end in (edge.source, edge.to):
                    if end not in seen:
                        raise ValueError(f"edges[{i}] ({edge.source} -> {edge.to}): {_unknown('node', end, ids)}")
                if edge.source == edge.to:
                    raise ValueError(f"edges[{i}]: {edge.source!r} points to itself (loops are not supported)")
                if edge.ref() in refs:
                    raise ValueError(f"edges[{i}]: {edge.source} -> {edge.to} is listed twice")
                refs.add(edge.ref())
            listed: set[str] = set()
            for k, step in enumerate(self.step_refs() or []):
                for ref in step:
                    self.resolve(ref, f"steps[{k}]")
                    key = _normal(ref)
                    if key in listed:
                        raise ValueError(f"steps[{k}]: {ref!r} is already in an earlier step")
                    listed.add(key)
            for ref in self.highlight:
                self.resolve(ref, "highlight")
            return self

        def step_refs(self) -> list[list[str]] | None:
            """``steps`` with single refs as one-element lists."""
            if self.steps is None:
                return None
            return [[s] if isinstance(s, str) else list(s) for s in self.steps]

        def resolve(self, ref: str, where: str) -> tuple[str, str | tuple[str, str]]:
            """``("node", id)`` or ``("edge", (from, to))`` for a node id or ``a->b`` ref."""
            text = _normal(ref)
            if "->" in text:
                source, _, target = text.partition("->")
                known = [e.ref() for e in self.edges]
                if text not in known:
                    raise ValueError(f"{where}: {_unknown('edge', text, known)}")
                return "edge", (source, target)
            ids = [n.id for n in self.nodes]
            if text not in ids:
                raise ValueError(f"{where}: {_unknown('node', text, ids)}")
            return "node", text

    #: In a vertical frame the heading grows by this factor (as in ``bullets``).
    portrait_growth = 1.3
    #: Text grows up to this factor over the requested sizes when the diagram has room.
    growth = 1.3
    #: Label wrap widths tried (Manim units at the body size of 32 points; scaled with the size).
    wraps = (3.2, 2.3, 1.7, 4.4)
    #: A non-default direction (``auto``) must keep text this much larger to be chosen.
    direction_bias = 1.1
    #: Opacity of a node's tint (its fill in the node colour; more would cost a highlighted
    #: label contrast on light themes) and of the dimmed rest (as ``icon_grid``: a dimmed ``dim``
    #: edge label stays above lint's 2:1).
    fill_opacity = 0.1
    dimmed_opacity = 0.55
    #: Factors for the gaps between layers tried, widest first, when the diagram fits with room
    #: to spare (1.4x these between the nodes of a layer).
    spreads = (1.8, 1.5, 1.25, 1.0)
    #: Labels stay this much above the readable size (lint measures short lowercase words a
    #: little smaller than their font size says).
    floor_margin = 1.05
    #: Line widths (Manim stroke widths).
    node_stroke = 3.0
    edge_stroke = 3.0

    # ----- layout ----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        body = self.safe_area
        heading = None
        if p.heading:
            header = self.region("header")
            size = float(self.theme.size(p.heading_size)) * (self.portrait_growth if self.is_portrait else 1.0)
            heading = fit_text(p.heading, header.width, header.height, size=size, color=p.heading_color, weight=BOLD, role="heading")
            place(heading, header, fit="none", align="center")
            body = body.below(heading, gap=0.4)
        plan = self._spread(self._choose(body), body)
        if not plan.fits:
            log.warning(
                "scene '%s': the diagram's %d nodes do not fit this frame at the readable size; "
                "split it into smaller diagrams (or shorten labels)", self.spec.id, len(p.nodes),
            )
        drawing = self._draw(plan)
        pills = [e.pill for e in drawing.edges if e.pill is not None]
        everything = VGroup(*drawing.nodes.values(), *[e.group for e in drawing.edges], *pills)
        if not plan.fits:  # at the readable size and still too big: scale the whole diagram down
            everything.scale(min(plan.shrink, 1.0), about_point=ORIGIN)
        everything.shift(body.center)
        self.graph_layout = plan.layout
        self._steps(heading, drawing, plan)

    def _direction_options(self) -> list[str]:
        """Directions to try, the preferred first."""
        p = self.params
        if p.direction != "auto":
            return [p.direction]
        return ["TB", "LR"] if self.is_portrait else ["LR", "TB"]

    def _choose(self, body: Region) -> "_Plan":
        """The plan with the largest text: per direction and wrap width, the largest size
        factor (from :attr:`growth` down to the readable minimum) at which the laid-out diagram
        fits ``body``. Text grown beyond the requested size never decides the layout."""
        options = self._direction_options()
        best: tuple[Any, ...] | None = None
        chosen = None
        for rank, direction in enumerate(options):
            bias = 1.0 if rank == 0 else 1 / self.direction_bias
            for wrap in self.wraps:
                plan = self._fit(body, direction, wrap)
                if plan.fits:
                    key: tuple[Any, ...] = (1, round(min(plan.factor, 1.0) * bias, 3), round(plan.factor * bias, 3))
                else:  # nothing fits: the one that needs the least extra shrinking
                    key = (0, round(plan.shrink * bias, 3), 0.0)
                if best is None or key > best:
                    best, chosen = key, plan
        assert chosen is not None
        return chosen

    def _fit(self, body: Region, direction: str, wrap: float) -> "_Plan":
        """The largest factor whose layout fits ``body`` (sizes floored at the readable size)."""
        p = self.params
        size = float(self.theme.size(p.size))
        edge_size = float(self.theme.size(p.edge_label_size))
        floor = readable_size() * self.floor_margin
        lowest = min(1.0, floor / size, floor / edge_size)  # every size at its floor
        factors = [self.growth, 1.15, 1.0]
        f = 1.0
        while f > lowest + 1e-9:
            f = max(lowest, f * 0.9)
            factors.append(f)
        plan = None
        for factor in factors:
            sizes = (max(min(size, floor), size * factor), max(min(edge_size, floor), edge_size * factor))
            plan = self._plan(direction, wrap, sizes, factor)
            plan = plan._replace(shrink=min(body.width / max(plan.layout.width, 1e-6), body.height / max(plan.layout.height, 1e-6)))
            if plan.shrink >= 1.0 - 1e-6:
                return plan._replace(fits=True)
        assert plan is not None
        return plan

    def _spread(self, plan: "_Plan", body: Region) -> "_Plan":
        """The plan with wider gaps (up to :attr:`spreads`) where the body has room to spare, so
        a diagram bound by one side of the frame does not huddle in the middle of the other."""
        if not plan.fits:
            return plan

        def fits(spread: tuple[float, float]) -> "_Plan | None":
            wider = self._plan(plan.direction, plan.wrap, (plan.size, plan.edge_size), plan.factor, spread)
            ok = wider.layout.width <= body.width + 1e-6 and wider.layout.height <= body.height + 1e-6
            return wider._replace(fits=True, shrink=1.0) if ok else None

        layers = next((f for f in self.spreads if fits((f, 1.0))), 1.0)
        for nodes in (f * 1.4 for f in self.spreads):
            wider = fits((layers, nodes))
            if wider is not None:
                return wider
        return plan

    def _plan(
        self, direction: str, wrap: float, sizes: tuple[float, float], factor: float, spread: tuple[float, float] = (1.0, 1.0)
    ) -> "_Plan":
        """Node and edge label sizes measured at ``sizes`` (label, edge label) and the layout."""
        p = self.params
        size, edge_size = sizes
        u = size / 32
        boxes = {}
        for node in p.nodes:
            boxes[node.id] = self._node_box(node, wrap * u, size, direction)
        labels: dict[int, tuple[float, float]] = {}
        ue = edge_size / 32
        for k, edge in enumerate(p.edges):
            if edge.label:
                m = measure_text(edge.label, 2.6 * ue * 0.97, size=edge_size, balance=True)
                labels[k] = (m.width + 0.2 * ue, m.height + 0.12 * ue)
        layout = layered_layout(
            [GraphNode(n.id, boxes[n.id][0], boxes[n.id][1], _OUTLINE[self._shape(n)]) for n in p.nodes],
            [GraphEdge(e.source, e.to, labels.get(k)) for k, e in enumerate(p.edges)],
            direction=direction,  # type: ignore[arg-type]
            layer_gap=(0.95 if direction == "LR" else 0.85) * u * spread[0],
            node_gap=0.5 * u * spread[1],
            routing="orthogonal" if p.routing == "orthogonal" else "straight",
            port_spacing=0.22 * u,
            label_margin=0.22 * u,
        )
        return _Plan(layout, direction, wrap, size, edge_size, factor, False, 0.0)

    def _shape(self, node: DiagramNode) -> str:
        return node.shape or self.params.shape

    def _content_size(self, node: DiagramNode, width: float, size: float, direction: str) -> tuple[float, float, bool]:
        """Width and height of a node's label (+ icon), and whether the icon stands above it:
        in circles and diamonds, and in left-to-right layouts (where width is scarce)."""
        m = measure_text(node.text(), width * 0.97, size=size, balance=True)
        w, h = m.width, m.height
        above = direction == "LR" or self._shape(node) in ("circle", "diamond")
        if node.icon:
            ih = self._icon_height(size)
            if above:
                w, h = max(w, ih), h + ih + 0.12 * size / 32
            else:
                w, h = w + ih + 0.15 * size / 32, max(h, ih)
        return w, h, above

    @staticmethod
    def _icon_height(size: float) -> float:
        return 0.0208 * size * 0.9

    def _node_box(self, node: DiagramNode, width: float, size: float, direction: str) -> tuple[float, float]:
        """The node's outer size for a label wrapped to ``width`` at ``size``."""
        w, h, _ = self._content_size(node, width, size, direction)
        return self._outer(self._shape(node), w, h, size / 32)

    @staticmethod
    def _outer(shape: str, w: float, h: float, u: float) -> tuple[float, float]:
        """Outer size of a shape around content ``w`` x ``h`` (``u``: size / 32)."""
        px, py = 0.32 * u, 0.2 * u
        if shape == "circle":
            d = float(np.hypot(w, h)) + 0.2 * u
            return d, d
        if shape == "diamond":
            x, y = w / 2 + 0.1 * u, h / 2 + 0.1 * u
            a = x + 1.5 * y
            return 2 * a, 2 * a / 1.5
        if shape == "pill":
            height = h + 2 * py
            return max(w + 2 * px + height * 0.35, height * 1.4), height
        width = max(w + 2 * px, 1.3 * u)
        if shape == "cylinder":
            return width, h + 2 * py + 2 * Diagram._rim(width, u)
        return width, h + 2 * py

    @staticmethod
    def _rim(width: float, u: float) -> float:
        """Vertical radius of a cylinder's ellipses."""
        return min(0.12 * width, 0.18 * u)

    # ----- drawing ---------------------------------------------------------------------------

    def _draw(self, plan: "_Plan") -> "_Drawing":
        p = self.params
        nodes = {node.id: self._node(node, plan) for node in p.nodes}
        edges = [self._edge(k, edge, plan) for k, edge in enumerate(p.edges)]
        return _Drawing(nodes, edges)

    def _node(self, node: DiagramNode, plan: "_Plan") -> VGroup:
        """``VGroup(shape, icon?, label)`` at the node's place."""
        p = self.params
        u = plan.size / 32
        place_ = plan.layout.nodes[node.id]
        color = self.theme.color(node.color or p.node_color)
        shape_name = self._shape(node)
        label = fit_text(node.text(), plan.wrap * u, size=plan.size, color=p.label_color, balance=True)
        w, h, above = self._content_size(node, plan.wrap * u, plan.size, plan.direction)
        parts: list[Mobject] = []
        mark = icon(node.icon, color=node.color or p.node_color, height=self._icon_height(plan.size), theme=self.theme) if node.icon else None
        if mark is not None:
            if above:
                mark.next_to(label, UP, buff=0.12 * u)
            else:
                mark.next_to(label, LEFT, buff=0.15 * u)
                mark.match_y(label[0] if len(label) == 1 else label)
            content = VGroup(mark, label)
        else:
            content = VGroup(label)
        width, height = self._outer(shape_name, max(w, content.width), max(h, content.height), u)
        width, height = max(width, place_.width), max(height, place_.height)
        shape = self._shape_mobject(shape_name, width, height, u)
        shape.set_fill(color, opacity=self.fill_opacity).set_stroke(color, width=self.node_stroke)
        if shape_name == "cylinder":
            shape[1].set_fill(opacity=0)
            content.move_to(np.array([0.0, -self._rim(width, u) / 2, 0.0]))
        else:
            content.move_to(ORIGIN)
        parts = [shape, *([mark] if mark is not None else []), label]
        group = VGroup(*parts).shift(np.array([place_.x, place_.y, 0.0]))
        for part in parts:
            part.set_z_index(1)
        return group

    def _shape_mobject(self, shape: str, w: float, h: float, u: float) -> VMobject:
        """The outline of a node, centred on the origin."""
        if shape == "box":
            return RoundedRectangle(width=w, height=h, corner_radius=min(0.06 * u, h / 4))
        if shape == "round":
            return RoundedRectangle(width=w, height=h, corner_radius=min(0.22 * u, h / 2.5))
        if shape == "pill":
            return RoundedRectangle(width=w, height=h, corner_radius=h / 2 - 1e-4)
        if shape == "circle":
            return Circle(radius=w / 2)
        if shape == "diamond":
            return Polygon(np.array([0, h / 2, 0]), np.array([w / 2, 0, 0]), np.array([0, -h / 2, 0]), np.array([-w / 2, 0, 0]))
        ry = self._rim(w, u)
        top = Arc(radius=1, start_angle=0, angle=PI).stretch(w / 2, 0, about_point=ORIGIN).stretch(ry, 1, about_point=ORIGIN).shift(UP * (h / 2 - ry))
        bottom = Arc(radius=1, start_angle=PI, angle=PI).stretch(w / 2, 0, about_point=ORIGIN).stretch(ry, 1, about_point=ORIGIN).shift(DOWN * (h / 2 - ry))
        body = VMobject()
        body.set_points(top.points)
        body.add_line_to(np.array([-w / 2, -h / 2 + ry, 0.0]))
        body.append_points(bottom.points)
        body.add_line_to(np.array([w / 2, h / 2 - ry, 0.0]))
        rim = Arc(radius=1, start_angle=PI, angle=PI).stretch(w / 2, 0, about_point=ORIGIN).stretch(ry, 1, about_point=ORIGIN).shift(UP * (h / 2 - ry))
        return VGroup(body, rim)

    def _edge(self, k: int, edge: DiagramEdge, plan: "_Plan") -> "_EdgeParts":
        """Line, arrowhead and label of an edge (its route from the layout)."""
        p = self.params
        u = plan.size / 32
        route = plan.layout.edges[k]
        color = self.theme.color(edge.color or p.edge_color)
        points = [np.array([x, y, 0.0]) for x, y in route.points]
        tip_length = float(np.clip(0.2 * u, 0.13, 0.26))
        main = RIGHT if plan.direction == "LR" else DOWN
        path, end, tangent = self._path(points, main, tip_length)
        path.set_stroke(color, width=self.edge_stroke).set_fill(opacity=0)
        line: VMobject = path
        if edge.style == "dashed":
            length = sum(float(np.linalg.norm(b - a)) for a, b in zip(points, points[1:]))
            line = DashedVMobject(path, num_dashes=max(3, int(length / (0.2 * u))), dashed_ratio=0.55)
            line.set_stroke(color, width=self.edge_stroke)
        side = np.array([-tangent[1], tangent[0], 0.0])
        tip = Polygon(end, end - tangent * tip_length + side * tip_length * 0.5, end - tangent * tip_length - side * tip_length * 0.5)
        tip.set_fill(color, opacity=1).set_stroke(color, width=1)
        parts: list[Mobject] = [line, tip]
        pill = None
        if edge.label and route.label_at is not None:
            ue = plan.edge_size / 32
            text = fit_text(edge.label, 2.6 * ue, size=plan.edge_size, color=p.edge_label_color, balance=True)
            at = np.array([route.label_at[0], route.label_at[1], 0.0])
            text.move_to(at).set_z_index(3)
            pill = RoundedRectangle(width=text.width + 0.2 * ue, height=text.height + 0.12 * ue, corner_radius=min(0.12 * ue, (text.height + 0.12 * ue) / 2))
            pill.set_fill(self.theme.background, opacity=1).set_stroke(width=0).move_to(at).set_z_index(2)
            parts.append(text)
        return _EdgeParts(VGroup(*parts), line, tip, pill)

    def _path(self, points: list[np.ndarray], main: np.ndarray, tip: float) -> tuple[VMobject, np.ndarray, np.ndarray]:
        """The edge's line through ``points``, ending ``tip`` short of the last point (under the
        arrowhead); also that last point and the direction there (unit)."""
        end = points[-1]
        path = VMobject()
        if self.params.routing == "curved":
            dm = float(np.dot(points[-1] - points[-2], main))
            tangent = main * (1.0 if dm >= 0 else -1.0) if abs(dm) > 1e-6 else _unit(points[-1] - points[-2])
            stops = points[:-1] + [end - tangent * tip * 0.9]
            path.start_new_path(stops[0])
            for a, b in zip(stops, stops[1:]):
                d = float(np.dot(b - a, main))
                if abs(d) < 1e-6:
                    path.add_line_to(b)
                else:
                    path.add_cubic_bezier_curve_to(a + main * d / 2, b - main * d / 2, b)
            return path, end, tangent
        tangent = _unit(points[-1] - points[-2])
        path.set_points_as_corners([*points[:-1], end - tangent * tip * 0.9])
        return path, end, tangent

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, heading: Mobject | None, d: "_Drawing", plan: "_Plan") -> None:
        p = self.params
        self._drawing = d
        top = self.target("heading", heading, entrance=lambda: [FadeIn(heading, shift=DOWN * 0.15)]) if heading is not None else None
        self._nodes: dict[str, Target] = {}
        for i, node in enumerate(p.nodes, start=1):
            mob = d.nodes[node.id]
            self._nodes[node.id] = self.target([f"node{i}", f"node:{node.id}"], mob, outline=mob[0], entrance=lambda mob=mob: [FadeIn(mob, scale=0.85)])
        self._edges: dict[str, Target] = {}
        for k, edge in enumerate(p.edges):
            self._edges[edge.ref()] = self.target(f"edge:{edge.ref()}", d.edges[k].group, entrance=lambda k=k: self._edge_entrance(k))
        groups = self._step_groups(plan.layout)
        steps: list[Any] = []
        for i, (node_ids, edge_refs) in enumerate(groups):
            later = {ref for _, refs in groups[i + 1 :] for ref in refs}

            def build(node_ids: list[str] = node_ids, edge_refs: list[str] = edge_refs, later: set[str] = later, first: bool = i == 0) -> list[Animation]:
                anims = self._reveal(node_ids, edge_refs, later)
                if first and top is not None:
                    anims = self.entrance(top) + anims
                return [Succession(*anims)] if len(anims) > 1 else anims

            steps.append(build)
        if p.highlight:
            steps.append(self._focus())
        self.reveal(steps, fraction=0.75, cap=1.6)
        self.finish()

    def _step_groups(self, layout: GraphLayout) -> list[tuple[list[str], list[str]]]:
        """``(node ids, edge refs)`` per step: explicit ``steps`` (nodes no step names in one
        more step), else per ``reveal`` in layout order (layer by layer, top to bottom / left
        to right within a layer)."""
        p = self.params
        ordered = sorted(p.nodes, key=lambda n: (layout.nodes[n.id].layer, layout.nodes[n.id].order))
        explicit = p.step_refs()
        if explicit is not None:
            groups: list[tuple[list[str], list[str]]] = []
            named: set[str] = set()
            for refs in explicit:
                ids, edges = [], []
                for ref in refs:
                    kind, value = p.resolve(ref, "steps")
                    if kind == "node":
                        ids.append(value)  # type: ignore[arg-type]
                        named.add(value)  # type: ignore[arg-type]
                    else:
                        edges.append(edge_ref(*value))  # type: ignore[misc]
                        named.add(edge_ref(*value))  # type: ignore[misc]
                groups.append((ids, edges))
            rest = [n.id for n in ordered if n.id not in named]
            return groups + ([(rest, [])] if rest else [])   # edges not named come with their ends
        if p.reveal == "all":
            return [([n.id for n in ordered], [])]
        if p.reveal == "layers":
            return [(row, []) for row in layout.layers if row]
        return [([n.id], []) for n in ordered]

    def _reveal(self, node_ids: list[str], edge_refs: list[str], later: set[str]) -> list[Animation]:
        """One step, in waves: the nodes no edge of the step leads to appear, then the edges
        whose source is on screen grow from it, then the nodes they reach appear, and so on.
        Edges between nodes on screen come along unless a ``later`` step names them; an edge
        named in the step brings its ends. Nothing on screen is revealed again."""
        p = self.params
        appeared = {n.id for n in p.nodes if self.is_shown(self._nodes[n.id])}
        nodes = [n for n in dict.fromkeys(node_ids) if n not in appeared]
        visible = appeared | set(nodes)
        edges = [e for e in p.edges if not self.is_shown(self._edges[e.ref()])
                 and (e.ref() in edge_refs or (e.ref() not in later and e.source in visible and e.to in visible))]
        for e in edges:
            nodes += [end for end in (e.source, e.to) if end not in appeared and end not in nodes]
        chain: list[Animation] = []

        def wave(anims: list[Animation]) -> None:
            if anims:
                chain.append(LaggedStart(*anims, lag_ratio=0.15) if len(anims) > 1 else anims[0])

        while nodes or edges:
            waiting = {e.to for e in edges}
            ready = [n for n in nodes if n not in waiting]
            growing = [e for e in edges if e.source in appeared]
            if not ready and not growing:   # a cycle within the step: start at its first node
                ready = nodes[:1]
            wave([a for n in ready for a in self.entrance(self._nodes[n])])
            appeared |= set(ready)
            nodes = [n for n in nodes if n not in ready]
            growing = [e for e in edges if e.source in appeared]
            wave([self._grow(p.edges.index(e)) for e in growing])
            edges = [e for e in edges if e not in growing]
        return chain

    def _edge_entrance(self, k: int) -> list[Animation]:
        """An edge's entrance as a target (the ``reveal`` action): its ends not on screen yet
        appear, then it grows."""
        edge = self.params.edges[k]
        ends = [a for end in dict.fromkeys((edge.source, edge.to)) for a in self.entrance(self._nodes[end])]
        return [Succession(LaggedStart(*ends, lag_ratio=0.15), self._grow(k))] if ends else [self._grow(k)]

    def _grow(self, k: int) -> Animation:
        """An edge grows from its source to its target, then its arrowhead and label appear."""
        parts = self._drawing.edges[k]
        line = Create(parts.line, lag_ratio=1.0 if isinstance(parts.line, DashedVMobject) else 0.0, rate_func=linear)
        rest: list[Animation] = [FadeIn(parts.tip, scale=0.5)]
        if parts.pill is not None:
            rest += [FadeIn(parts.pill), FadeIn(parts.group[2])]
        return Succession(line, AnimationGroup(*rest))

    def _focus(self) -> Callable[[], list[Animation]]:
        """The highlight step: the chosen nodes and edges turn ``highlight_color`` (outlines,
        tint, icons, lines; labels keep their colour), everything else dims."""
        p = self.params
        color = self.theme.color(p.highlight_color)
        nodes: set[str] = set()
        edges: set[str] = set()
        refs = [p.resolve(r, "highlight") for r in p.highlight]
        known = {e.ref() for e in p.edges}
        previous: str | None = None
        for kind, value in refs:
            if kind == "edge":
                edges.add(edge_ref(*value))  # type: ignore[misc]
                previous = None
                continue
            nodes.add(value)  # type: ignore[arg-type]
            if previous is not None:
                for ref in (edge_ref(previous, value), edge_ref(value, previous)):  # type: ignore[arg-type]
                    if ref in known:
                        edges.add(ref)
            previous = value  # type: ignore[assignment]

        def build() -> list[Animation]:
            d = self._drawing
            anims: list[Animation] = []
            for node_id, target in self._nodes.items():
                if node_id in nodes:
                    if self.on_screen_parts(target):
                        mob = d.nodes[node_id]
                        goal = mob[0].copy().set_stroke(color, width=self.node_stroke * 1.5)
                        for member in goal.family_members_with_points():
                            if member.get_fill_opacity() > 0:  # not a cylinder's rim
                                member.set_fill(color, opacity=self.fill_opacity * 1.6)
                        anims.append(Transform(mob[0], goal))
                        if len(mob) == 3:
                            anims.append(mob[1].animate.set_color(color))
                else:
                    anims += [dim_to(target, part, self.dimmed_opacity) for part in self.on_screen_parts(target)]
            for k, edge in enumerate(p.edges):
                target = self._edges[edge.ref()]
                if edge.ref() in edges:
                    if self.on_screen_parts(target):
                        parts = d.edges[k]
                        anims += [parts.line.animate.set_stroke(color, width=self.edge_stroke * 1.6), parts.tip.animate.set_fill(color).set_stroke(color)]
                else:
                    anims += [dim_to(target, part, self.dimmed_opacity) for part in self.on_screen_parts(target)]
            return anims

        return build


#: Also available as ``flowchart`` (same params and targets).
scene("flowchart")(Diagram)


def _normal(ref: str) -> str:
    """A ref with the spaces around ``->`` removed."""
    return "->".join(part.strip() for part in ref.strip().split("->"))


def _unknown(kind: str, name: str, known: list[str]) -> str:
    """``unknown node 'x'; did you mean 'y'? (nodes: ...)``."""
    message = f"unknown {kind} {name!r}"
    close = difflib.get_close_matches(name, known, n=3, cutoff=0.5)
    if close:
        message += f"; did you mean {' or '.join(repr(c) for c in close)}?"
    shown = known[:12] + (["..."] if len(known) > 12 else [])
    return message + f" ({kind}s: {', '.join(shown) or 'none'})"


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else RIGHT


class _Plan(NamedTuple):
    """A planned diagram: the layout and the sizes it was made at."""

    layout: GraphLayout
    direction: str
    wrap: float
    size: float
    edge_size: float
    factor: float
    fits: bool
    shrink: float


class _EdgeParts(NamedTuple):
    """An edge's mobjects: ``group`` = VGroup(line, tip, label?) (the target); the label's
    backdrop ``pill`` (background colour, hiding lines under the label) is apart, so that
    highlights do not paint it."""

    group: VGroup
    line: VMobject
    tip: VMobject
    pill: VMobject | None


class _Drawing(NamedTuple):
    nodes: dict[str, VGroup]
    edges: list[_EdgeParts]
