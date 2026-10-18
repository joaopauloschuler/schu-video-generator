"""Geometry on a ``function_plot``'s plane (DESIGN §87.7): ``points``, ``vectors`` (sums drawn
tip to tail) and ``marks`` (segments, braces, angle arcs, dimension lines), all in data
coordinates. :class:`PlaneFigure` (no manim) resolves the references between them and moves
them for the ``trace`` action; :class:`PlaneGeometry` draws them on :class:`MathAxes` and keeps
every item, label and mark in step when a point or vector moves."""

import re
from collections.abc import Callable, Sequence
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .math_axes import LiveLabel, MathAxes, fill_label, label_problem, place_label

#: A position: a point's or a vector's name (a vector: its tip), ``point<N>``, ``vector<N>``, or ``[x, y]``.
Ref = str | tuple[float, float]
#: The kinds of mark, each a key holding its positions.
MARK_KINDS = ("segment", "brace", "angle", "dimension")
#: How many positions each kind of mark takes (``segment``: at least 2).
MARK_SIZES = {"brace": 2, "angle": 3, "dimension": 2}
#: The fields each kind of label may use.
POINT_FIELDS = ("x", "y", "name")
VECTOR_FIELDS = ("x", "y", "length", "name")
MARK_FIELDS = {"segment": ("length",), "brace": ("length",), "dimension": ("length",), "angle": ("angle",)}
#: Default mark colours.
MARK_COLORS = {"segment": "text", "brace": "text", "angle": "accent", "dimension": "dim"}
#: Radius of a point; stroke width of a vector, a segment; opacity of a sum's tip-to-tail copies.
POINT_RADIUS, VECTOR_WIDTH, SEGMENT_WIDTH, GHOST_OPACITY = 0.09, 6.0, 4.0, 0.45
_NUMBERED = re.compile(r"^(point|vector)(\d+)$")
_NAME = re.compile(r"^[^\s\[\](){},:]+$")


def name_problem(name: str) -> str | None:
    """Why ``name`` cannot name a point or a vector (``None`` when it can)."""
    if not _NAME.match(name):
        return f"name {name!r}: write it without spaces, brackets, commas or ':' (A, B, P1, v, a')"
    if _NUMBERED.match(name):
        return f"name {name!r} looks like a numbered target; choose another (A, P, v)"
    return None


class PlotPoint(SceneParams):
    """A point: ``{at, name, label, color, decimals}``; ``[x, y]`` alone is its position."""

    also_accepts = (list,)

    at: tuple[float, float]
    """[x, y]: where it is; the trace action moves it."""
    name: str | None = None
    """Its name (A, B, P): marks and vectors may refer to it, and it is its label by default."""
    label: TranslatableStr | None = None
    """Its label: {x}, {y} and {name} are filled in as it moves ('P({x}, {y})'); default: its name; '' for none."""
    color: ThemeColor | None = None
    """Dot colour; default: the colour of the first term its label says, else text."""
    decimals: int = Field(1, ge=0, le=4)
    """Decimal places of the numbers in its label."""

    @model_validator(mode="before")
    @classmethod
    def _from_list(cls, data: Any) -> Any:
        return {"at": data} if isinstance(data, (list, tuple)) else data

    @model_validator(mode="after")
    def _check(self) -> "PlotPoint":
        problem = (name_problem(self.name) if self.name else None) or (label_problem(self.label, POINT_FIELDS) if self.label else None)
        if problem:
            raise ValueError(problem)
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """``[x, y]`` alone is also a point (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, handler(core_schema)]}


class PlotVector(SceneParams):
    """A vector (an arrow): ``{from, to | components | sum, name, label, color, decimals}``; ``[x, y]`` alone goes from the origin to there."""

    also_accepts = (list,)

    start: Ref | None = Field(None, alias="from")
    """Its tail: [x, y], a point's name or another vector (its tip); default: the origin."""
    to: Ref | None = None
    """Its tip: [x, y] (trace moves it) or a point's name (it follows the point)."""
    components: tuple[float, float] | None = None
    """[dx, dy] from its tail, instead of to (trace scales or turns it)."""
    sum: list[str] | None = None
    """[a, b, ...]: earlier vectors (names or vector<N>) added tip to tail; this arrow is their resultant, drawn from the first one's tail."""
    name: str | None = None
    """Its name (a, v): sums, marks and labels may use it; its label by default."""
    label: TranslatableStr | None = None
    """Its label: {x} and {y} (its components), {length} and {name} are filled in as it changes; default: its name; '' for none."""
    color: ThemeColor | None = None
    """Arrow colour; default: the colour of the first term its label says, else the theme palette in order (after the functions)."""
    decimals: int = Field(1, ge=0, le=4)
    """Decimal places of the numbers in its label."""

    @model_validator(mode="before")
    @classmethod
    def _from_list(cls, data: Any) -> Any:
        return {"to": data} if isinstance(data, (list, tuple)) else data

    @model_validator(mode="after")
    def _check(self) -> "PlotVector":
        given = [k for k in ("to", "components", "sum") if getattr(self, k) is not None]
        if len(given) != 1:
            raise ValueError(f"a vector needs exactly one of to, components or sum (got {', '.join(given) or 'none'})")
        if self.sum is not None and len(self.sum) < 2:
            raise ValueError("sum: list at least two vectors ([a, b])")
        if self.sum is not None and self.start is not None:
            raise ValueError("a sum starts at its first vector's tail: leave out from")
        problem = (name_problem(self.name) if self.name else None) or (label_problem(self.label, VECTOR_FIELDS) if self.label else None)
        if problem:
            raise ValueError(problem)
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """``[x, y]`` alone is also a vector from the origin (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, handler(core_schema)]}


class PlotMark(SceneParams):
    """A mark: one of ``{segment: [A, B, ...]}``, ``{brace: [A, B]}``, ``{angle: [A, V, B]}``
    (at V), ``{dimension: [A, B]}``, with ``label``, ``side``, ``color``, ``closed``, ``dashed``,
    ``decimals``. A position is a point's name, a vector's (its tip) or ``[x, y]``."""

    segment: list[Ref] | None = None
    """[A, B, ...]: straight lines through these positions (closed: back to the first: a polygon)."""
    brace: list[Ref] | None = None
    """[A, B]: a curly brace beside the segment A-B, its label beyond it."""
    angle: list[Ref] | None = None
    """[A, V, B]: the angle at V between V-A and V-B (the smaller one): an arc, a square at 90°."""
    dimension: list[Ref] | None = None
    """[A, B]: a dimension line beside A-B with end bars, its label beside it."""
    label: TranslatableStr | None = None
    """Its label: {length} (segment, brace, dimension: in axis units) or {angle} (degrees, '{angle}°') are filled in as things move; default: '{length}' on a dimension, none on the others."""
    side: Literal["auto", "above", "below", "left", "right"] = "auto"
    """Brace and dimension: which side of the segment; auto: away from the middle of the figure."""
    color: ThemeColor | None = None
    """Its colour; default: the colour of the first term its label says, else text (accent for an angle, dim for a dimension)."""
    closed: bool = False
    """Segment: join the last position back to the first."""
    dashed: bool = False
    """Segment: draw it dashed."""
    decimals: int | None = Field(None, ge=0, le=4)
    """Decimal places of the numbers in its label (default 1; 0 for an angle)."""

    @model_validator(mode="after")
    def _check(self) -> "PlotMark":
        given = [k for k in MARK_KINDS if getattr(self, k) is not None]
        if len(given) != 1:
            raise ValueError(f"a mark is exactly one of segment, brace, angle or dimension (got {', '.join(given) or 'none'})")
        kind = given[0]
        refs = getattr(self, kind)
        if kind == "segment" and len(refs) < 2:
            raise ValueError("segment: list at least two positions ([A, B])")
        if kind in MARK_SIZES and len(refs) != MARK_SIZES[kind]:
            example = "[A, V, B] (the vertex in the middle)" if kind == "angle" else "[A, B]"
            raise ValueError(f"{kind}: list exactly {MARK_SIZES[kind]} positions, {example}")
        if (self.closed or self.dashed) and kind != "segment":
            raise ValueError(f"closed and dashed are for a segment, not a {kind}")
        if self.side != "auto" and kind not in ("brace", "dimension"):
            raise ValueError(f"side is for a brace or a dimension, not a {kind}")
        problem = label_problem(self.label, MARK_FIELDS[kind]) if self.label else None
        if problem:
            raise ValueError(problem)
        return self

    @property
    def kind(self) -> str:
        """``segment``, ``brace``, ``angle`` or ``dimension``."""
        return next(k for k in MARK_KINDS if getattr(self, k) is not None)

    @property
    def refs(self) -> list[Ref]:
        """The positions it is drawn through."""
        return getattr(self, self.kind)

    @property
    def template(self) -> str:
        """Its label template ('' for none)."""
        if self.label is not None:
            return self.label
        return "{length}" if self.kind == "dimension" else ""

    @property
    def places(self) -> int:
        """Decimal places of its label's numbers."""
        return self.decimals if self.decimals is not None else (0 if self.kind == "angle" else 1)


# ----- the figure (no manim) ---------------------------------------------------------------------


def mark_numbers(marks: Sequence[PlotMark]) -> list[str]:
    """Each mark's target name: its kind numbered within its kind (``brace1``, ``angle1``, ``brace2``)."""
    seen: dict[str, int] = {}
    names = []
    for mark in marks:
        seen[mark.kind] = seen.get(mark.kind, 0) + 1
        names.append(f"{mark.kind}{seen[mark.kind]}")
    return names


class PlaneFigure:
    """The positions of a plane's points and vectors (data units), resolved from their params:
    a point is where it is; a vector's tail and tip come from positions, its components or (a
    sum) the vectors it adds. :meth:`move` changes a point or a vector, and everything that refers
    to it follows. ``ValueError`` names the item and the reference it cannot resolve."""

    def __init__(self, points: Sequence[PlotPoint], vectors: Sequence[PlotVector]) -> None:
        self.point_specs, self.vector_specs = list(points), list(vectors)
        self.point_names = {p.name: k for k, p in enumerate(points) if p.name}
        self.vector_names = {v.name: k for k, v in enumerate(vectors) if v.name}
        if len(self.point_names) < sum(1 for p in points if p.name):
            raise ValueError(f"points: two points are called {_first_twice([p.name for p in points if p.name])!r}")
        if len(self.vector_names) < sum(1 for v in vectors if v.name):
            raise ValueError(f"vectors: two vectors are called {_first_twice([v.name for v in vectors if v.name])!r}")
        both = sorted(set(self.point_names) & set(self.vector_names))
        if both:
            raise ValueError(f"{both[0]!r} names a point and a vector; give them different names")
        self.points = [np.array(p.at, dtype=float) for p in points]
        self.summands: list[list[int]] = []
        self.states: list[np.ndarray | None] = []
        for k, spec in enumerate(vectors):
            where = f"vectors[{k}]"
            self.summands.append([self.vector_index(ref, where, before=k) for ref in spec.sum] if spec.sum else [])
            for ref in (spec.start, spec.to):
                if ref is not None:
                    self.at(ref, where, vectors_before=k)
            if spec.components is not None:
                self.states.append(np.array(spec.components, dtype=float))
            elif isinstance(spec.to, tuple):
                self.states.append(np.array(spec.to, dtype=float))
            else:
                self.states.append(None)  # follows a position, or a sum

    def vector_index(self, ref: str, where: str, before: int | None = None) -> int:
        """The index of the vector ``ref`` names (its name or ``vector<N>``), one before ``before``."""
        numbered = _NUMBERED.match(ref)
        k = int(numbered.group(2)) - 1 if numbered and numbered.group(1) == "vector" else self.vector_names.get(ref, -1)
        limit = len(self.vector_specs) if before is None else before
        if not 0 <= k < limit:
            names = [f"vector{i + 1}" + (f" ({self.vector_specs[i].name})" if self.vector_specs[i].name else "") for i in range(limit)]
            known = f"the vectors before it are {', '.join(names)}" if before is not None else f"the vectors are {', '.join(names) or 'none'}"
            raise ValueError(f"{where}: no vector {ref!r}; {known}")
        return k

    def at(self, ref: Ref, where: str, vectors_before: int | None = None) -> np.ndarray:
        """The data position ``ref`` names now: ``[x, y]``, a point, or a vector's tip."""
        if not isinstance(ref, str):
            return np.array(ref, dtype=float)
        numbered = _NUMBERED.match(ref)
        if numbered and numbered.group(1) == "point":
            k = int(numbered.group(2)) - 1
            if not 0 <= k < len(self.points):
                raise ValueError(f"{where}: no {ref}; there are {len(self.points)} points")
            return self.points[k].copy()
        if ref in self.point_names:
            return self.points[self.point_names[ref]].copy()
        if (numbered and numbered.group(1) == "vector") or ref in self.vector_names:
            return self.ends(self.vector_index(ref, where, vectors_before), where)[1]
        known = [*self.point_names, *(n for n in self.vector_names)]
        hint = f"; the names are {', '.join(known)}" if known else "; name a point ({at: [1, 2], name: A}) or write [x, y]"
        raise ValueError(f"{where}: no point or vector {ref!r}{hint}")

    def ends(self, k: int, where: str = "") -> tuple[np.ndarray, np.ndarray]:
        """Vector ``k``'s tail and tip now."""
        spec = self.vector_specs[k]
        where = where or f"vectors[{k}]"
        if self.summands[k]:
            tail = self.ends(self.summands[k][0], where)[0]
            return tail, tail + sum((self.components(i) for i in self.summands[k]), np.zeros(2))
        tail = self.at(spec.start, where, k) if spec.start is not None else np.zeros(2)
        if spec.components is not None:
            return tail, tail + self.states[k]
        if isinstance(spec.to, tuple):
            return tail, self.states[k].copy()
        return tail, self.at(spec.to, where, k)

    def components(self, k: int) -> np.ndarray:
        """Vector ``k``'s tip minus its tail."""
        tail, tip = self.ends(k)
        return tip - tail

    def chain(self, k: int) -> list[tuple[np.ndarray, np.ndarray]]:
        """A sum's vectors laid tip to tail from the first one's tail: ``(tail, tip)`` of each."""
        out = []
        start = self.ends(self.summands[k][0])[0]
        for i in self.summands[k]:
            step = self.components(i)
            out.append((start, start + step))
            start = start + step
        return out

    def trace_problem(self, kind: str, k: int) -> str | None:
        """Why the ``trace`` action cannot move point / vector ``k`` (``None`` when it can)."""
        if kind == "point":
            return None
        spec = self.vector_specs[k]
        if spec.sum:
            return f"vector{k + 1} is a sum: it follows its vectors; trace one of them"
        if isinstance(spec.to, str):
            return f"vector{k + 1} ends at {spec.to}: it follows it; trace {spec.to} instead"
        return None

    def state(self, kind: str, k: int) -> np.ndarray:
        """What ``trace`` moves: a point's position, a vector's tip (or its components)."""
        return (self.points[k] if kind == "point" else self.states[k]).copy()

    def goal(self, kind: str, k: int, to: tuple[float, float] | None, scale: float | None) -> np.ndarray:
        """The state a ``trace`` with ``to`` (a position) or ``scale`` ends in."""
        if kind == "point":
            return np.array(to, dtype=float)
        tail, tip = self.ends(k)
        new_tip = np.array(to, dtype=float) if to is not None else tail + (tip - tail) * float(scale)
        return new_tip - tail if self.vector_specs[k].components is not None else new_tip

    def move(self, kind: str, k: int, state: np.ndarray) -> None:
        """Set a point's position or a vector's state."""
        if kind == "point":
            self.points[k] = np.asarray(state, dtype=float).copy()
        else:
            self.states[k] = np.asarray(state, dtype=float).copy()

    def coordinates(self, marks: Sequence[PlotMark] = ()) -> np.ndarray:
        """Every position the figure draws (``(n, 2)``), for the default ranges."""
        out = [*self.points]
        for k in range(len(self.vector_specs)):
            out += list(self.ends(k))
            if self.summands[k]:
                out += [tip for _, tip in self.chain(k)]
        for j, mark in enumerate(marks):
            out += [self.at(ref, f"marks[{j}]") for ref in mark.refs]
        return np.array(out, dtype=float).reshape(-1, 2)

    def mark_value(self, mark: PlotMark, where: str = "") -> float:
        """What a mark's label shows: the length along its positions, or the angle in degrees."""
        spots = [self.at(ref, where) for ref in mark.refs]
        if mark.kind == "angle":
            a, v, b = spots
            first = np.arctan2(*(a - v)[::-1])
            second = np.arctan2(*(b - v)[::-1])
            return float(abs(np.degrees((second - first + np.pi) % (2 * np.pi) - np.pi)))
        if mark.closed:
            spots.append(spots[0])
        return float(sum(np.linalg.norm(b - a) for a, b in zip(spots, spots[1:])))


def _first_twice(names: list[str]) -> str:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            return name
        seen.add(name)
    return names[0]


def check_figure(points: Sequence[PlotPoint], vectors: Sequence[PlotVector], marks: Sequence[PlotMark]) -> PlaneFigure:
    """The figure, with every reference of the marks resolved (``ValueError`` on the first bad one)."""
    figure = PlaneFigure(points, vectors)
    for j, mark in enumerate(marks):
        spots = [figure.at(ref, f"marks[{j}].{mark.kind}") for ref in mark.refs]
        if mark.kind == "angle":
            a, v, b = spots
            if np.linalg.norm(a - v) < 1e-9 or np.linalg.norm(b - v) < 1e-9:
                raise ValueError(f"marks[{j}].angle: a ray has no length (a position is the vertex)")
        elif any(np.linalg.norm(b - a) < 1e-9 for a, b in zip(spots, spots[1:])):
            raise ValueError(f"marks[{j}].{mark.kind}: two positions in a row are the same point")
    for k in range(len(vectors)):
        if np.linalg.norm(figure.components(k)) < 1e-9 and not figure.summands[k]:
            raise ValueError(f"vectors[{k}]: its tail and tip are the same point")
    return figure


def geometry_range(values: np.ndarray, with_zero: bool) -> tuple[float, float]:
    """An axis range holding ``values`` (and 0 when ``with_zero``) with room around them, on
    whole numbers once the span is over 2."""
    lo, hi = float(values.min()), float(values.max())
    if with_zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    pad = max(0.5, 0.12 * (hi - lo))
    lo, hi = lo - pad, hi + pad
    step = 1.0 if hi - lo > 3 else 0.5
    return float(np.floor(lo / step) * step), float(np.ceil(hi / step) * step)


# ----- drawing (manim) ---------------------------------------------------------------------------


def _renew(old: Mobject, new: Mobject, placed: bool, z: int) -> None:
    """``old.become(new)``, keeping a dimmed or faded look once it was placed (the opacities of
    ``new`` scaled by how far ``old``'s first part is below its own)."""
    if placed:
        before = [m for m in old.family_members_with_points()]
        after = [m for m in new.family_members_with_points()]
        if before and after:
            def opacity(m: Mobject) -> float:
                return float(m.get_stroke_opacity() if m.get_stroke_width() > 0 else m.get_fill_opacity())

            base = opacity(after[0])
            ratio = opacity(before[0]) / base if base > 1e-6 else 1.0
            if abs(ratio - 1) > 1e-6:
                for m in after:
                    m.set_stroke(opacity=m.get_stroke_opacity() * ratio)
                    m.set_fill(opacity=m.get_fill_opacity() * ratio)
    old.become(new)
    old.set_z_index(z)


def _arrow(tail: np.ndarray, tip: np.ndarray, color: str, opacity: float = 1.0) -> Arrow:
    if np.linalg.norm(tip - tail) < 1e-3:  # a vector scaled through 0
        tip = tail + np.array([1e-3, 0.0, 0.0])
    arrow = Arrow(tail, tip, buff=0, color=color, stroke_width=VECTOR_WIDTH, tip_length=0.24, max_tip_length_to_length_ratio=0.35,
                  max_stroke_width_to_length_ratio=12)
    arrow.set_opacity(opacity)
    return arrow


def point_label_spot(point: np.ndarray, away: np.ndarray, w: float, h: float, plot: Region, obstacles: list[tuple[float, float, float, float]],
                     avoid: np.ndarray, first: int | None = None) -> tuple[np.ndarray, int]:
    """Where a ``w`` x ``h`` label of a point goes: one of 8 directions around it, the first (from
    ``first``, else the one nearest ``away``) inside ``plot`` and clear of ``obstacles`` and the
    ``avoid`` frame points; returns the centre and the direction's index."""
    angles = np.radians(np.arange(8) * 45.0)
    dirs = np.column_stack([np.cos(angles), np.sin(angles)])
    start = first if first is not None else int(np.argmax(dirs @ (away[:2] / (np.linalg.norm(away[:2]) or 1.0)))) if np.linalg.norm(away[:2]) > 1e-9 else 1
    order = sorted(range(8), key=lambda i: (min((i - start) % 8, (start - i) % 8), (i - start) % 8))
    pad = 0.04
    fallback = None
    for i in order:
        d = dirs[i]
        reach = POINT_RADIUS + 0.1 + 0.5 * (abs(d[0]) * w + abs(d[1]) * h)
        c = point[:2] + d * reach
        box = (c[0] - w / 2 - pad, c[1] - h / 2 - pad, c[0] + w / 2 + pad, c[1] + h / 2 + pad)
        if box[0] < plot.x0 - 0.2 or box[2] > plot.x1 + 0.2 or box[1] < plot.y0 - 0.2 or box[3] > plot.y1 + 0.2:
            continue
        fallback = fallback or (np.array([c[0], c[1], 0.0]), i)
        if any(box[0] < o[2] and o[0] < box[2] and box[1] < o[3] and o[1] < box[3] for o in obstacles):
            continue
        if len(avoid) and bool(((avoid[:, 0] > box[0]) & (avoid[:, 0] < box[2]) & (avoid[:, 1] > box[1]) & (avoid[:, 1] < box[3])).any()):
            continue
        return np.array([c[0], c[1], 0.0]), i
    if fallback is not None:
        return fallback
    d = dirs[start]
    return np.array([point[0] + d[0] * 0.4, point[1] + d[1] * 0.4, 0.0]), start


def _box(m: Mobject) -> tuple[float, float, float, float]:
    return MathAxes.label_box(m)


def _sampled(points: Sequence[np.ndarray], step: float = 0.1) -> np.ndarray:
    """Frame points every ``step`` along the polyline through ``points``."""
    out = []
    for a, b in zip(points, points[1:]):
        n = max(2, int(np.linalg.norm(b[:2] - a[:2]) / step) + 1)
        out.append(np.linspace(a, b, n))
    return np.vstack(out) if out else np.zeros((0, 3))


class _Item:
    """One drawn point, vector or mark: ``group`` (what its target holds), ``label`` (a
    :class:`LiveLabel` or ``None``), ``needs`` (the targets to bring first), ``entrance()``, and
    its drawn parts (``dot``; ``arrow`` and a sum's ``ghosts``; a mark's ``shape`` and ``spec``);
    :meth:`PlaneGeometry.layout` redraws it."""

    def __init__(self, names: list[str], group: VGroup, label: LiveLabel | None, needs: list[str]) -> None:
        self.names, self.group, self.label, self.needs = names, group, label, needs
        self.entrance: Callable[[], Animation] = lambda: FadeIn(group)
        self.template, self.color = "", ""
        self.dot: Mobject | None = None
        self.spot: int | None = None  # the direction index of a point's label, kept while it moves
        self.arrow: Mobject | None = None
        self.ghosts = VGroup()
        self.shape: Mobject | None = None
        self.spec: Any = None


class TracedFigureItem:
    """A point or vector of the figure seen by the ``trace`` action (:class:`Traced`)."""

    def __init__(self, geometry: "PlaneGeometry", kind: str, k: int) -> None:
        self.geometry, self.kind, self.k = geometry, kind, k
        item = geometry.points[k] if kind == "point" else geometry.vectors[k]
        self.driver: Mobject = item.group[0]

    @property
    def state(self) -> np.ndarray:
        return self.geometry.figure.state(self.kind, self.k)

    @property
    def parts(self) -> list[Mobject]:
        return self.geometry.parts

    def place(self, state: Any) -> None:
        self.geometry.figure.move(self.kind, self.k, state)
        self.geometry.layout()

    def goal(self, to: Any, scale: float | None) -> np.ndarray:
        """Where a ``trace`` with ``to`` / ``scale`` takes it."""
        return self.geometry.figure.goal(self.kind, self.k, to, scale)


class PlaneGeometry:
    """The points, vectors and marks of a ``function_plot`` drawn on ``axes``; :meth:`layout`
    places them all (and their labels, clear of ``obstacles`` and the ``avoid`` frame points) from
    the figure's current positions."""

    def __init__(
        self, scene: NarratedScene, axes: MathAxes, params: Any, size: float, obstacles: list[tuple[float, float, float, float]],
        avoid: np.ndarray, palette_from: int,
    ) -> None:
        self.scene, self.axes, self.size = scene, axes, size
        self.static_obstacles, self.static_avoid = list(obstacles), avoid
        self.point_specs, self.vector_specs, self.mark_specs = params.points, params.vectors, params.marks
        self.figure = check_figure(params.points, params.vectors, params.marks)
        theme = scene.theme
        self.points: list[_Item] = []
        for k, spec in enumerate(self.point_specs):
            template = spec.label if spec.label is not None else (spec.name or "")
            color = self._color(spec.color, template, "text")
            dot = Dot(radius=POINT_RADIUS, color=color).set_z_index(3)
            label = LiveLabel(scene, size, 4) if template else None
            names = [f"point{k + 1}"] + ([f"point:{spec.name}"] if spec.name else [])
            item = _Item(names, VGroup(dot, *([label.group] if label else [])), label, [])
            item.entrance = lambda dot=dot, label=label: LaggedStart(FadeIn(dot, scale=0.4), *([FadeIn(label.group)] if label else []), lag_ratio=0.4)
            item.template, item.color, item.dot = template, color, dot
            self.points.append(item)
        self.vectors: list[_Item] = []
        for k, spec in enumerate(self.vector_specs):
            template = spec.label if spec.label is not None else (spec.name or "")
            color = self._color(spec.color, template, None) or theme.palette_color(palette_from + k)
            arrow = _arrow(np.zeros(3), RIGHT, color).set_z_index(2)
            ghosts = VGroup(*[_arrow(np.zeros(3), RIGHT, self._vector_color(i, palette_from), GHOST_OPACITY) for i in self.figure.summands[k][1:]])
            label = LiveLabel(scene, size, 4) if template else None
            names = [f"vector{k + 1}"] + ([f"vector:{spec.name}"] if spec.name else [])
            needs = [self.vectors[i].names[0] for i in self.figure.summands[k]] + self._needs([r for r in (spec.start, spec.to) if r is not None])
            item = _Item(names, VGroup(arrow, ghosts, *([label.group] if label else [])), label, needs)
            item.template, item.color, item.arrow, item.ghosts = template, color, arrow, ghosts
            self.vectors.append(item)
        for k, item in enumerate(self.vectors):
            summands = [self.vectors[i] for i in self.figure.summands[k][1:]]
            item.entrance = self._vector_entrance(item, summands)
        self.marks: list[_Item] = []
        for j, (spec, name) in enumerate(zip(self.mark_specs, mark_numbers(self.mark_specs))):
            color = self._color(spec.color, spec.template, MARK_COLORS[spec.kind])
            shape = VMobject().set_z_index(1)
            label = LiveLabel(scene, size, 4) if spec.template else None
            item = _Item([name], VGroup(shape, *([label.group] if label else [])), label, self._needs(spec.refs))
            item.spec, item.color, item.shape = spec, color, shape
            draw = GrowFromCenter if spec.kind == "brace" else Create
            item.entrance = lambda shape=shape, label=label, draw=draw: LaggedStart(draw(shape), *([FadeIn(label.group)] if label else []), lag_ratio=0.5)
            self.marks.append(item)
        self.placed = False
        self.layout()
        self.placed = True

    def _vector_color(self, i: int, palette_from: int) -> str:
        spec = self.vector_specs[i]
        template = spec.label if spec.label is not None else (spec.name or "")
        return self._color(spec.color, template, None) or self.scene.theme.palette_color(palette_from + i)

    def _color(self, own: str | None, label: str, default: str | None) -> str | None:
        """An item's own colour, else the colour of the first term its label says, else ``default``."""
        if own:
            return self.scene.theme.color(own)
        term = find_term(label, active_terms()) if label else None
        if term is not None:
            return term.color
        return self.scene.theme.color(default) if default else None

    def _needs(self, refs: Sequence[Ref]) -> list[str]:
        """The targets a set of positions names (points and vectors), to bring in first."""
        out: list[str] = []
        for ref in refs:
            if not isinstance(ref, str):
                continue
            numbered = _NUMBERED.match(ref)
            if numbered:
                out.append(ref)
            elif ref in self.figure.point_names:
                out.append(f"point{self.figure.point_names[ref] + 1}")
            elif ref in self.figure.vector_names:
                out.append(f"vector{self.figure.vector_names[ref] + 1}")
        return out

    def _vector_entrance(self, item: _Item, summands: list[_Item]) -> Callable[[], Animation]:
        def entrance() -> Animation:
            parts: list[Animation] = []
            if summands:  # copies of the vectors slide tip to tail, then the resultant grows
                parts.append(AnimationGroup(*[TransformFromCopy(s.arrow, g) for s, g in zip(summands, item.ghosts)]))
            parts.append(GrowArrow(item.arrow))
            if item.label is not None:
                parts.append(FadeIn(item.label.group))
            return Succession(*parts) if summands else LaggedStart(*parts, lag_ratio=0.5)

        return entrance

    @property
    def items(self) -> list[_Item]:
        """Points, vectors and marks, in that order."""
        return [*self.points, *self.vectors, *self.marks]

    @property
    def parts(self) -> list[Mobject]:
        """Everything that may change when the figure moves."""
        return [m for item in self.items for m in item.group]

    def traced(self, kind: str, k: int) -> TracedFigureItem:
        """Point or vector ``k`` as the ``trace`` action moves it."""
        return TracedFigureItem(self, kind, k)

    def layout(self) -> None:
        """Draw every item where the figure has it now and place the labels."""
        axes, figure = self.axes, self.figure
        to_frame = lambda xy: axes.point(float(xy[0]), float(xy[1]))  # noqa: E731
        frame_spots = [to_frame(p) for p in figure.points]
        lines: list[np.ndarray] = []
        arrows = []
        for k, item in enumerate(self.vectors):
            tail, tip = (to_frame(e) for e in figure.ends(k))
            _renew(item.arrow, _arrow(tail, tip, item.color).set_z_index(2), self.placed, 2)
            for ghost, (a, b), i in zip(item.ghosts, figure.chain(k)[1:] if figure.summands[k] else [], figure.summands[k][1:]):
                _renew(ghost, _arrow(to_frame(a), to_frame(b), self.vectors[i].color, GHOST_OPACITY), self.placed, 2)
            arrows.append((tail, tip))
            lines.append(_sampled([tail, tip]))
            frame_spots += [tail, tip]
        middle = np.mean(frame_spots, axis=0) if frame_spots else np.array([axes.plot.center[0], axes.plot.center[1], 0.0])
        obstacles = list(self.static_obstacles)
        for item in self.marks:
            spec = item.spec
            spots = [to_frame(figure.at(ref, "")) for ref in spec.refs]
            if item.label is not None:
                item.label.show(fill_label(spec.template, {"length": figure.mark_value(spec), "angle": figure.mark_value(spec)}, spec.places))
            label = item.label.group if item.label is not None else None
            shape = self._mark_shape(spec, spots, item.color, label, middle)
            _renew(item.shape, shape, self.placed, 1)
            if label is not None:
                label.set_z_index(4)
                obstacles.append(_box(label))
            lines.append(item.shape.get_all_points())
        avoid = np.vstack([self.static_avoid, *lines]) if lines else self.static_avoid
        for k, item in enumerate(self.points):
            point = frame_spots[k]
            item.dot.move_to(point)
            if item.label is None:
                continue
            x, y = figure.points[k]
            item.label.show(fill_label(item.template, {"x": float(x), "y": float(y), "name": self.point_specs[k].name or ""}, self.point_specs[k].decimals))
            spot, item.spot = point_label_spot(point, point - middle, item.label.group.width, item.label.group.height, axes.plot, obstacles, avoid, item.spot)
            item.label.group.move_to(spot)
            obstacles.append(_box(item.label.group))
        for k, item in enumerate(self.vectors):
            if item.label is None:
                continue
            tail, tip = arrows[k]
            dx, dy = figure.components(k)
            item.label.show(fill_label(item.template, {"x": float(dx), "y": float(dy), "length": float(np.hypot(dx, dy)), "name": self.vector_specs[k].name or ""},
                                       self.vector_specs[k].decimals))
            obstacles.append(place_label(item.label.group, _sampled([tail, tip], 0.05), axes.plot, obstacles, avoid))

    def _mark_shape(self, spec: PlotMark, spots: list[np.ndarray], color: str, label: Mobject | None, middle: np.ndarray) -> VMobject:
        """A mark's shape (its label moved into place)."""
        if spec.kind == "segment":
            through = [*spots, spots[0]] if spec.closed else spots
            line = VMobject(stroke_color=color, stroke_width=SEGMENT_WIDTH).set_points_as_corners(through)
            shape = DashedVMobject(line, num_dashes=max(6, int(line.get_arc_length() / 0.22))) if spec.dashed else line
            if label is not None:
                place_label(label, _sampled(through, 0.05), self.axes.plot, [], np.zeros((0, 3)))
            return shape
        if spec.kind == "angle":
            return angle_mark(spots[1], spots[0], spots[2], label=label, color=color).shape
        normal = _side_normal(spots[0], spots[1], spec.side, middle)
        build = brace_mark if spec.kind == "brace" else dimension_mark
        return build(spots[0], spots[1], label=label, normal=normal, color=color).shape


def _side_normal(a: np.ndarray, b: np.ndarray, side: str, middle: np.ndarray) -> np.ndarray:
    """The normal of the segment a-b on ``side`` (``auto``: away from ``middle``)."""
    normal = segment_normal(a, b, middle)
    want = {"above": UP, "below": DOWN, "left": LEFT, "right": RIGHT}.get(side)
    if want is not None:
        along = float(np.dot(normal[:2], want[:2]))
        if abs(along) > 1e-6 and along < 0:
            normal = -normal
    return normal
