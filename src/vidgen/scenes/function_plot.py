"""``function_plot``: maths axes with functions f(x), dots that travel along a curve with a live
value label (and a tangent following them), and shaded areas under a curve between bounds.

The expressions are parsed by :func:`~vidgen.mathexpr.parse_expression` (a whitelisted parser,
never ``eval``). The axes (:func:`math_axes`, :class:`MathAxes`) are maths style: they cross at the origin when it is in
view, with arrow tips, ticks and plain ``Text`` labels (no LaTeX). The ``trace`` beat action
moves a dot (or an area's right end) to a new x (DESIGN §87.6).
"""

from collections.abc import Callable
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .line_chart import LineChart
from .math_axes import ChainedTargets, LiveLabel, MathAxes, clip_segment, fill_label, label_plate, label_problem, math_axes, place_label
from .plane_geometry import PlaneFigure, PlaneGeometry, PlotMark, PlotPoint, PlotVector, check_figure, geometry_range, mark_numbers

#: Names given to functions written without one, in order.
DEFAULT_NAMES = ("f", "g", "h", "p", "q", "r", "s", "u", "v", "w")
#: Curve samples per Manim unit of plot width (at least :data:`MIN_SAMPLES`).
SAMPLES_PER_UNIT, MIN_SAMPLES = 90, 240
#: Stroke width of a curve; radius of a dot; fill opacity of an area by default.
CURVE_WIDTH, DOT_RADIUS, AREA_OPACITY = 5.0, 0.1, 0.3
#: A tangent's length as a share of the plot's width, at most :data:`TANGENT_MAX` units.
TANGENT_SHARE, TANGENT_MAX = 0.4, 4.5
#: The fields a dot's and an area's ``label`` may use.
DOT_FIELDS = ("x", "y", "slope", "name")
AREA_FIELDS = ("area", "from", "to", "name")


# ----- params --------------------------------------------------------------------------------


class PlotFunction(SceneParams):
    """A function: ``{expr, name, label, color, domain, dashed}``; a string alone is its
    expression (``x^2``, ``f(x) = x^2``)."""

    also_accepts = (str,)

    expr: str
    """f(x) written as maths: x^2 - 1, 2x + 1, sin(x), exp(-x^2/2), sqrt(x), abs(x); or 'f(x) = x^2' (the name in front)."""
    name: str | None = None
    """Its name (in labels and for on / under / trace); default: the name in expr, else f, g, h... in order."""
    label: TranslatableStr | None = None
    """The label by the curve; default: 'f(x) = x²' from the name and expr; '' for none."""
    color: ThemeColor | None = None
    """Curve colour; default: the colour of the video's term the name or label is (terms:), else the theme palette in order."""
    domain: tuple[float, float] | None = None
    """[from, to]: draw it only there (default: the whole x range)."""
    dashed: bool = False
    """Draw the curve dashed (e.g. an approximation)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"expr": data} if isinstance(data, str) else data

    @model_validator(mode="after")
    def _split(self) -> "PlotFunction":
        named, body = split_definition(self.expr)
        if named is not None and self.name is not None and named != self.name:
            raise ValueError(f"expr names the function {named!r} but name is {self.name!r}")
        self.expr = body
        if named is not None:
            self.name = named
        if self.domain is not None and self.domain[1] <= self.domain[0]:
            raise ValueError(f"domain {list(self.domain)}: the second end must be greater than the first")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """An expression alone is also a function (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}


class PlotDot(SceneParams):
    """A dot on a function's curve: ``{on, x, label, tangent, guides, color, decimals}``."""

    on: str | None = None
    """The function it sits on (its name); default: the first."""
    x: float
    """Where it starts; the trace action moves it."""
    label: TranslatableStr | None = None
    """Its live value label: {x}, {y}, {slope} and {name} are filled in as it moves ({y:.3f}: a format); default '{name}({x}) = {y}'; '' for none."""
    tangent: bool = False
    """Draw the tangent line at the dot; it turns as the dot moves."""
    guides: bool = False
    """Dashed lines from the dot to both axes."""
    color: ThemeColor = "highlight"
    """Dot colour."""
    tangent_color: ThemeColor = "accent"
    """Tangent colour."""
    decimals: int = Field(1, ge=0, le=4)
    """Decimal places of the numbers in its label."""

    @field_validator("label")
    @classmethod
    def _label(cls, v: str | None) -> str | None:
        problem = None if v is None else label_problem(v, DOT_FIELDS)
        if problem:
            raise ValueError(problem)
        return v


class PlotArea(SceneParams):
    """A shaded area: ``{under, over, between, label, color, opacity, decimals}``."""

    under: str | None = None
    """The function above the area (its name); default: the first."""
    over: str | None = None
    """The function below the area; default: the x axis (y = 0)."""
    between: tuple[float, float]
    """[from, to] on the x axis; the trace action moves its right end."""
    label: TranslatableStr = ""
    """Text in the area: {area} (its signed size, the integral), {from}, {to} and {name} are filled in; e.g. 'A = {area}'."""
    color: ThemeColor | None = None
    """Fill colour; default: the colour of the function above it."""
    opacity: float = Field(AREA_OPACITY, gt=0.0, le=1.0)
    """Fill opacity."""
    decimals: int = Field(2, ge=0, le=4)
    """Decimal places of the numbers in its label."""

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        problem = label_problem(v, AREA_FIELDS) if v else None
        if problem:
            raise ValueError(problem)
        return v

    @model_validator(mode="after")
    def _bounds(self) -> "PlotArea":
        if self.between[1] <= self.between[0]:
            raise ValueError(f"between {list(self.between)}: the second end must be greater than the first")
        return self


def _outside(x: float, y: float, x_range: tuple[float, float], y_range: tuple[float, float]) -> str | None:
    """Why ``(x, y)`` is not on the plot (``None`` when it is)."""
    if x_range[0] - 1e-9 <= x <= x_range[1] + 1e-9 and y_range[0] - 1e-9 <= y <= y_range[1] + 1e-9:
        return None
    return f"({x:g}, {y:g}) is outside the plot (x {x_range[0]:g} to {x_range[1]:g}, y {y_range[0]:g} to {y_range[1]:g}); widen x_range / y_range"


def auto_y_range(values: np.ndarray) -> tuple[float, float]:
    """A y range for sampled function ``values`` (``nan`` ignored): their span without a few
    extreme values when those would squash the rest (an asymptote), reaching 0 when it is near,
    with a margin."""
    finite = values[np.isfinite(values)]
    if not finite.size:
        raise ValueError("no function has a value in the x range")
    lo, hi = float(finite.min()), float(finite.max())
    q_lo, q_hi = (float(v) for v in np.percentile(finite, [3, 97]))
    if hi - lo > 4 * max(q_hi - q_lo, 1e-9):
        lo, hi = q_lo, q_hi
    span = max(hi - lo, 1e-6)
    if lo > 0 and lo < 0.6 * span:
        lo = 0.0
    if hi < 0 and -hi < 0.6 * span:
        hi = 0.0
    span = max(hi - lo, 1e-6)
    if hi - lo < 1e-9:
        lo, hi = lo - 1.0, hi + 1.0
    return lo - 0.06 * span, hi + 0.06 * span


@scene("function_plot")
class FunctionPlot(NarratedScene):
    """Maths axes with functions f(x) written as expressions (parsed safely, never run as code),
    dots on the curves with a live value label (and a tangent and guide lines), and shaded areas
    under a curve. ``reveal: per_beat`` (default): the axes with function 1 at beat 1, then
    each further function, dot and area at the next beat (spread evenly when there are more than
    beats); ``all``: everything in beat 1. A ``reveal`` action shows an item on a word instead
    (the item's own beat then holds), and ``trace`` moves a dot along its curve (its label, tangent and guides follow) or an area's
    right end.

    Action targets: ``title``, ``axes``, ``function<N>`` / ``function:<name>`` (a curve and its
    label), ``dot<N>`` (a dot, its label and guides), ``tangent<N>`` (dot N's tangent) and
    ``area<N>``.
    """

    outro = 0.5
    target_patterns = (
        "title", "axes", "function<N>", "function:<name>", "dot<N>", "tangent<N>", "area<N>", "point<N>", "point:<name>", "vector<N>",
        "vector:<name>", "segment<N>", "brace<N>", "angle<N>", "dimension<N>",
    )

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        functions: list[PlotFunction] = []
        """The functions: 'x^2', 'f(x) = sin(x)' or {expr, name, label, color, domain, dashed}; a later one may use an earlier one (g(x) = f(x) + 1)."""
        x_range: tuple[float, float] | None = None
        """[from, to]: the x axis; needed with functions; default (geometry only): around the points, vectors and marks."""
        y_range: tuple[float, float] | None = None
        """[from, to]: the y axis; default: from the functions' values (and the points, vectors and marks)."""
        dots: list[PlotDot] = []
        """Dots on the curves: {on, x, label, tangent, guides}; moved by the trace action."""
        areas: list[PlotArea] = []
        """Shaded areas: {under, over, between, label}."""
        points: list[PlotPoint] = []
        """Points on the plane: [x, y] or {at, name, label, color}; moved by the trace action."""
        vectors: list[PlotVector] = []
        """Arrows: [x, y] (from the origin) or {from, to | components | sum, name, label, color}; sum: [a, b] adds earlier vectors tip to tail; trace moves or scales them."""
        marks: list[PlotMark] = []
        """{segment: [A, B, ...]}, {brace: [A, B]}, {angle: [A, V, B]}, {dimension: [A, B]}, with label; a position is a point's or a vector's name or [x, y]."""
        axes: bool = True
        """false: no axes, ticks or grid (pure geometry; positions keep their place)."""
        x_label: TranslatableStr = "x"
        """Name at the end of the x axis ('' for none)."""
        y_label: TranslatableStr = "y"
        """Name at the top of the y axis ('' for none)."""
        grid: bool = True
        """Faint lines at the ticks."""
        aspect: Literal["auto", "equal"] | None = None
        """auto: the plot fills the space; equal: one unit is as long on both axes (true angles and slopes); default: equal with vectors or angle marks or without functions, else auto."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: function 1 with the axes at beat 1, then one function, dot, area, point, vector or mark per beat; all: everything in beat 1."""
        title_size: ThemeSize = "heading"
        """Title size (1.3x in a portrait frame)."""
        title_color: ThemeColor = "text"
        """Title colour."""
        label_size: ThemeSize = "caption"
        """Size of the tick, axis, curve, dot, area, point, vector and mark labels (never below the readable minimum)."""

        @model_validator(mode="after")
        def _check(self) -> "FunctionPlot.Params":
            if not (self.functions or self.points or self.vectors or self.marks):
                raise ValueError("give at least one of functions, points, vectors or marks")
            if self.functions and self.x_range is None:
                raise ValueError("x_range: give the x axis's [from, to] (needed with functions)")
            if not self.functions and (self.dots or self.areas):
                raise ValueError(f"{'dots' if self.dots else 'areas'} sit on a function: add functions")
            for name, (lo, hi) in (("x_range", self.x_range or (0.0, 1.0)), ("y_range", self.y_range or (0.0, 1.0))):
                if hi <= lo:
                    raise ValueError(f"{name} [{lo:g}, {hi:g}]: the second end must be greater than the first")
            figure = check_figure(self.points, self.vectors, self.marks)
            for k, (name, expr) in enumerate(self.expressions().items()):
                x_range = self.x_range or (0.0, 1.0)
                lo, hi = self.functions[k].domain or x_range
                if not np.isfinite(expr(np.linspace(max(lo, x_range[0]), min(hi, x_range[1]), 401))).any():
                    raise ValueError(f"functions[{k}] {name}(x) = {expr.text} has no value on the x range {list(x_range)}")
            x_range, y_range = self.plot_ranges(figure)
            for x, y in figure.coordinates(self.marks):
                problem = _outside(x, y, x_range, y_range)
                if problem:
                    raise ValueError(f"points, vectors and marks: {problem}")
            for k, dot in enumerate(self.dots):
                where = f"dots[{k}]"
                fn = self.function_of(dot.on, where)
                self.check_x(fn, dot.x, f"{where}.x")
            for k, area in enumerate(self.areas):
                where = f"areas[{k}]"
                bounding = [self.function_of(area.under, where)] + ([self.function_of(area.over, where)] if area.over is not None else [])
                for name in bounding:
                    for end in area.between:
                        self.check_x(name, end, f"{where}.between")
            return self

        def figure(self) -> PlaneFigure:
            """The points and vectors, resolved."""
            return check_figure(self.points, self.vectors, self.marks)

        def plot_ranges(self, figure: PlaneFigure | None = None) -> tuple[tuple[float, float], tuple[float, float]]:
            """The x and y ranges: the given ones, else from the functions' values and the
            figure's positions."""
            figure = figure or self.figure()
            spots = figure.coordinates(self.marks)
            x_range = self.x_range or geometry_range(spots[:, 0], self.axes)
            if self.y_range is not None:
                return x_range, self.y_range
            if not self.functions:
                return x_range, geometry_range(spots[:, 1], self.axes)
            values = np.concatenate([e(np.linspace(*x_range, 801)) for e in self.expressions().values()])
            lo, hi = auto_y_range(values)
            if len(spots):
                lo, hi = min(lo, float(spots[:, 1].min()) - 0.3), max(hi, float(spots[:, 1].max()) + 0.3)
            return x_range, (lo, hi)

        def shape(self) -> str:
            """The aspect: the given one, else ``equal`` with vectors or angle marks or without functions."""
            if self.aspect is not None:
                return self.aspect
            return "equal" if self.vectors or any(m.kind == "angle" for m in self.marks) or not self.functions else "auto"

        def function_names(self) -> list[str]:
            """Every function's name: its own, else the next free one of :data:`DEFAULT_NAMES`."""
            taken = {f.name for f in self.functions if f.name}
            free = iter(n for n in DEFAULT_NAMES if n not in taken)
            names = []
            for k, spec in enumerate(self.functions):
                name = spec.name or next(free, f"f{k + 1}")
                if name in names:
                    raise ValueError(f"functions[{k}]: two functions are called {name!r}")
                if name in MATH_NAMES:
                    raise ValueError(f"functions[{k}]: {name!r} is the variable, a constant or a built-in function; choose another name")
                names.append(name)
            return names

        def expressions(self) -> dict[str, MathExpression]:
            """The parsed functions by name, in order (each may call those before it)."""
            out: dict[str, MathExpression] = {}
            for k, (name, spec) in enumerate(zip(self.function_names(), self.functions)):
                try:
                    out[name] = parse_expression(spec.expr, dict(out))
                except ValueError as exc:
                    later = [n for n in self.function_names()[k:] if n in spec.expr]
                    hint = f" (a function may use only those before it, not {later[0]})" if later and "unknown name" in str(exc) else ""
                    raise ValueError(f"functions[{k}]: {exc}{hint}") from None
            return out

        def function_of(self, name: str | None, where: str) -> str:
            """The name of the function ``name`` refers to (``None``: the first)."""
            names = self.function_names()
            if name is None:
                return names[0]
            if name not in names:
                raise ValueError(f"{where}: no function {name!r}; the functions are {', '.join(names)}")
            return name

        def x_problem(self, name: str, x: float) -> str | None:
            """Why a point at ``x`` on function ``name`` cannot be shown (``None`` when it can)."""
            lo, hi = self.plot_ranges()[0]
            spec = self.functions[self.function_names().index(name)]
            if spec.domain is not None:
                lo, hi = max(lo, spec.domain[0]), min(hi, spec.domain[1])
            if not lo - 1e-9 <= x <= hi + 1e-9:
                return f"x = {x:g} is outside {name}'s drawn range [{lo:g}, {hi:g}]"
            if not np.isfinite(self.expressions()[name].at(x)):
                return f"{name} has no value at x = {x:g}"
            return None

        def check_x(self, name: str, x: float, where: str) -> None:
            problem = self.x_problem(name, x)
            if problem:
                raise ValueError(f"{where}: {problem}")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``axes`` (if shown), ``function<N>`` and ``function:<name>``,
        ``dot<N>`` (and ``tangent<N>`` for a dot with a tangent), ``area<N>``, ``point<N>`` and
        ``point:<name>``, ``vector<N>`` and ``vector:<name>``, then each mark's kind numbered
        (``segment1``, ``brace1``, ``angle1``, ``dimension1``)."""
        names = (["title"] if params.title else []) + (["axes"] if params.axes else [])
        for k, name in enumerate(params.function_names(), start=1):
            names += [f"function{k}", f"function:{name}"]
        for k, dot in enumerate(params.dots, start=1):
            names += [f"dot{k}"] + ([f"tangent{k}"] if dot.tangent else [])
        names += [f"area{k}" for k in range(1, len(params.areas) + 1)]
        for kind, items in (("point", params.points), ("vector", params.vectors)):
            for k, item in enumerate(items, start=1):
                names += [f"{kind}{k}"] + ([f"{kind}:{item.name}"] if item.name else [])
        return names + mark_numbers(params.marks)

    @classmethod
    def item_names(cls, params: Any) -> list[str]:
        """The main name of each item the scene reveals one by one, in order."""
        return ([f"function{k}" for k in range(1, len(params.functions) + 1)] + [f"dot{k}" for k in range(1, len(params.dots) + 1)]
                + [f"area{k}" for k in range(1, len(params.areas) + 1)] + [f"point{k}" for k in range(1, len(params.points) + 1)]
                + [f"vector{k}" for k in range(1, len(params.vectors) + 1)] + mark_numbers(params.marks))

    @classmethod
    def reveal_steps(cls, params: Any) -> list[RevealStep]:
        """One step per function (rising or falling over the x range), dot, area, point, vector and mark."""
        expressions = params.expressions()
        xs = np.linspace(*params.plot_ranges()[0], 9)
        trends = {}
        for k, expr in enumerate(expressions.values(), start=1):
            trends[f"function{k}"] = value_trend([float(v) for v in expr(xs) if np.isfinite(v)])
        steps = [RevealStep(name, trends.get(name)) for name in cls.item_names(params)]
        return steps[:1] if params.reveal == "all" else steps

    # ----- building -----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        expressions = p.expressions()
        names = list(expressions)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            body = body.below(title, gap=0.45)
        size = chart_label_size(p.label_size)
        x_range, y_range = p.plot_ranges()
        axes = math_axes(
            body, x_range, y_range, label=lambda s: self.text(s, size=size, color="dim"), aspect=p.shape(),
            grid=p.grid, x_title=self.text(p.x_label, size=size, color="dim") if p.x_label and p.axes else None,
            y_title=self.text(p.y_label, size=size, color="dim") if p.y_label and p.axes else None, visible=p.axes,
        )
        self.axes = axes
        colors = [self._function_color(k, name) for k, name in enumerate(names)]
        color_of = dict(zip(names, colors))
        curves = [self._curve(axes, expressions[n], spec, c) for n, spec, c in zip(names, p.functions, colors)]
        labels = self._curve_labels(axes, names, expressions, curves, colors, size)
        obstacles = [MathAxes.label_box(m) for m in [*axes.labels, *(x for x in labels if x is not None)]]
        areas = [
            _Area(self, axes, spec, expressions[p.function_of(spec.under, "")], None if spec.over is None else expressions[spec.over],
                  p.function_of(spec.under, ""), self._area_color(spec, color_of[p.function_of(spec.under, "")]), size, obstacles)
            for spec in p.areas
        ]
        dots = [_Dot(self, axes, spec, expressions[p.function_of(spec.on, "")], p.function_of(spec.on, ""), size, obstacles) for spec in p.dots]
        curve_points = [c.get_all_points() for c in curves if len(c)]
        avoid = np.vstack([*curve_points, axes.line_points()] if p.axes else [*curve_points, np.zeros((0, 3))])
        geometry = PlaneGeometry(self, axes, p, size, obstacles, avoid, len(names))
        self.geometry = geometry
        for dot in dots:  # dot labels keep clear of the figure's labels too, wherever they move
            dot.more_obstacles = geometry.label_boxes
            dot.place(dot.x)

        chain = ChainedTargets(self)
        revealed, add = chain.revealed, chain.add
        base: list[Target] = []
        if title is not None:
            base.append(add("title", title, lambda: [FadeIn(title)], []))
        if p.axes:
            base.append(add("axes", axes.group, lambda: [FadeIn(axes.group)], list(base)))
        function_targets = []
        for k, name in enumerate(names):
            group = VGroup(curves[k], labels[k]) if labels[k] is not None else VGroup(curves[k])

            def draw(k: int = k) -> list[Animation]:
                parts: list[Animation] = [Create(curves[k], rate_func=linear)]
                if labels[k] is not None:
                    parts.append(FadeIn(labels[k]))
                return [AnimationGroup(*parts, lag_ratio=0.6)]

            function_targets.append(add([f"function{k + 1}", f"function:{name}"], group, draw, list(base)))
        dot_targets = []
        for k, dot in enumerate(dots):
            owner = function_targets[names.index(dot.name)]
            with_tangent = dot.tangent is not None and f"tangent{k + 1}" not in revealed
            dot_targets.append(add(f"dot{k + 1}", dot.group, lambda dot=dot, with_tangent=with_tangent: [dot.entrance(with_tangent)], [*base, owner]))
            if dot.tangent is not None:
                add(f"tangent{k + 1}", dot.tangent, lambda dot=dot: [Create(dot.tangent)], [*base, owner, dot_targets[-1]])
        area_targets = []
        for k, area in enumerate(areas):
            owner = function_targets[names.index(area.name)]
            area_targets.append(add(f"area{k + 1}", area.group, lambda area=area: [area.entrance()], [*base, owner]))
        by_name: dict[str, Target] = {}
        for item in geometry.items:
            before = [*base, *(by_name[n] for n in item.needs)]
            by_name[item.names[0]] = add(item.names, item.group, lambda item=item: [item.entrance()], before)
        self.dots, self.areas = dots, areas
        self._traced: list[tuple[Target, Any]] = [
            *zip(dot_targets, dots), *zip(area_targets, areas),
            *((by_name[f"point{k + 1}"], geometry.traced("point", k)) for k in range(len(geometry.points))),
            *((by_name[f"vector{k + 1}"], geometry.traced("vector", k)) for k in range(len(geometry.vectors))),
        ]

        chain.reveal(base, [*function_targets, *dot_targets, *area_targets, *(by_name[item.names[0]] for item in geometry.items)], p.reveal == "all")
        self.finish()

    @classmethod
    def trace_problem(cls, params: Any, name: str, options: Any) -> tuple[str, str] | None:
        """``(option, message)`` when the ``trace`` action cannot move target ``name`` as asked."""
        to, scale = options.to, options.scale
        kind, _, own = name.partition(":")
        if own and kind in ("point", "vector"):
            number = next(k for k, item in enumerate(params.points if kind == "point" else params.vectors) if item.name == own)
        else:
            kind = name.rstrip("0123456789")
            number = int(name[len(kind):]) - 1 if name[len(kind):] else -1
        if kind not in ("dot", "area", "point", "vector") or number < 0:
            return ("target", f"{name}: trace moves a dot<N>, an area<N>, a point<N> or a vector<N>")
        if scale is not None and kind != "vector":
            return ("scale", f"{name}: scale is for a vector; move a {kind} with to")
        if kind in ("dot", "area"):
            if not isinstance(to, float):
                return ("to", f"{name}: to is an x (a number) for a {kind}, e.g. to: 2")
            if kind == "dot":
                problem = params.x_problem(params.function_of(params.dots[number].on, ""), to)
            else:
                area = params.areas[number]
                problem = params.x_problem(params.function_of(area.under, ""), to)
                if problem is None and area.over is not None:
                    problem = params.x_problem(area.over, to)
            return ("to", f"{name}: {problem}") if problem else None
        if to is not None and not isinstance(to, tuple):
            return ("to", f"{name}: to is a position [x, y] for a {kind}, e.g. to: [2, 1]")
        figure = params.figure()
        problem = figure.trace_problem(kind, number)
        if problem:
            return ("target", problem)
        goal = figure.goal(kind, number, to, scale)
        spot = goal if kind == "point" or params.vectors[number].components is None else figure.ends(number)[0] + goal
        problem = _outside(float(spot[0]), float(spot[1]), *params.plot_ranges(figure))
        return ("scale" if scale is not None else "to", f"{name}: {problem}") if problem else None

    def traced_item(self, target: Target) -> Any:
        """What the ``trace`` action moves for ``target`` (``None``: nothing)."""
        return next((item for own, item in self._traced if own is target), None)

    def _function_color(self, k: int, name: str) -> str:
        spec = self.params.functions[k]
        if spec.color:
            return self.theme.color(spec.color)
        return LineChart._term_color(name) or (LineChart._term_color(spec.label) if spec.label else None) or self.theme.palette_color(k)

    def _area_color(self, spec: PlotArea, under: str) -> str:
        """An area's own colour, else the colour of the first term its label says, else its curve's."""
        if spec.color:
            return self.theme.color(spec.color)
        term = find_term(spec.label, active_terms()) if spec.label else None
        return term.color if term is not None else under

    def _curve(self, axes: "MathAxes", expr: MathExpression, spec: PlotFunction, color: str) -> VGroup:
        lo, hi = axes.x_range
        if spec.domain is not None:
            lo, hi = max(lo, spec.domain[0]), min(hi, spec.domain[1])
        count = max(MIN_SAMPLES, int(axes.plot.width * SAMPLES_PER_UNIT * (hi - lo) / (axes.x_range[1] - axes.x_range[0])))
        pieces = VGroup()
        for run in curve_runs(expr, lo, hi, axes.y_range, count):
            points = [axes.point(x, y) for x, y in run]
            line = VMobject(stroke_color=color, stroke_width=CURVE_WIDTH).set_points_as_corners(points)
            pieces.add(DashedVMobject(line, num_dashes=max(8, int(line.get_arc_length() / 0.22))) if spec.dashed else line)
        return pieces

    def _curve_labels(self, axes: "MathAxes", names: list[str], expressions: dict[str, MathExpression], curves: list[VGroup], colors: list[str], size: float) -> list[Mobject | None]:
        """Each function's label, by its curve where it covers no curve, other label or tick label."""
        obstacles = [axes.label_box(m) for m in axes.labels]
        curve_points = np.vstack([c.get_all_points() if len(c) else np.zeros((0, 3)) for c in curves] + [axes.line_points()])
        out: list[Mobject | None] = []
        for k, name in enumerate(names):
            spec = self.params.functions[k]
            text = spec.label if spec.label is not None else f"{name}(x) = {pretty_expression(expressions[name].text)}"
            if not text or not len(curves[k]):
                out.append(None)
                continue
            words = self.text(text, size=size, color=colors[k])
            if words.width > axes.plot.width * 0.6:
                words.scale_to_fit_width(axes.plot.width * 0.6)
            label = VGroup(label_plate(words), words).set_z_index(1)  # readable on an area or the grid
            box = place_label(label, curves[k].get_all_points(), axes.plot, obstacles, curve_points)
            obstacles.append(box)
            out.append(label)
        return out


def curve_runs(expr: MathExpression, lo: float, hi: float, y_range: tuple[float, float], count: int) -> list[np.ndarray]:
    """The visible pieces of ``expr`` over ``lo..hi`` as ``(n, 2)`` arrays of data points:
    split where it is undefined, leaves the y range (ending on its edge) or jumps across it
    (an asymptote)."""
    xs = np.linspace(lo, hi, count)
    ys = expr(xs)
    y0, y1 = y_range
    span = y1 - y0
    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    def edge(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
        """Where the segment a -> b (a inside) crosses the y range's edge."""
        bound = y1 if b[1] > y1 else y0
        t = (bound - a[1]) / (b[1] - a[1])
        return (a[0] + t * (b[0] - a[0]), bound)

    previous: tuple[float, float] | None = None
    for x, y in zip(xs, ys):
        point = (float(x), float(y))
        finite = bool(np.isfinite(y))
        inside = finite and y0 - 1e-9 <= y <= y1 + 1e-9
        jump = previous is not None and finite and abs(point[1] - previous[1]) > 1.5 * span
        if jump and current:
            runs.append(current)
            current = []
        if inside:
            if not current and previous is not None and not jump and np.isfinite(previous[1]) and not (y0 <= previous[1] <= y1):
                current.append(edge(point, previous))
            current.append(point)
        elif current:
            if finite and not jump:
                current.append(edge(current[-1], point))
            runs.append(current)
            current = []
        previous = point if finite else None
    if current:
        runs.append(current)
    return [np.array(r) for r in runs if len(r) >= 2]


def dot_label_spot(point: np.ndarray, direction: np.ndarray, w: float, h: float, plot: Region, obstacles: list[tuple[float, float, float, float]]) -> np.ndarray:
    """Where a ``w`` x ``h`` label of a dot at ``point`` goes: beside it on the side above the
    curve (``direction``: the curve's direction there), else another corner, inside ``plot`` and
    clear of ``obstacles`` when it can be."""
    side = -1.0 if direction[1] > 0 else 1.0  # up-left of a rising curve is above it
    dx, dy = DOT_RADIUS + 0.08 + w / 2, DOT_RADIUS + 0.1 + h / 2
    spots = [(side, 1), (-side, 1), (-side, -1), (side, -1)]
    fallback = None
    for sx, sy in spots:
        cx, cy = point[0] + sx * dx, point[1] + sy * dy
        box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if box[0] < plot.x0 or box[2] > plot.x1 or box[1] < plot.y0 or box[3] > plot.y1:
            continue
        if not any(box[0] < o[2] and o[0] < box[2] and box[1] < o[3] and o[1] < box[3] for o in obstacles):
            return np.array([cx, cy, 0.0])
        fallback = fallback if fallback is not None else np.array([cx, cy, 0.0])
    if fallback is not None:
        return fallback
    cx = min(max(point[0] + side * dx, plot.x0 + w / 2), plot.x1 - w / 2)
    cy = min(max(point[1] + dy, plot.y0 + h / 2), plot.y1 - h / 2)
    return np.array([cx, cy, 0.0])


def area_label_spot(
    edges: np.ndarray, w: float, h: float, plot: Region, obstacles: list[tuple[float, float, float, float]]
) -> np.ndarray:
    """Where a ``w`` x ``h`` label of an area goes: ``edges`` are its ``(x, bottom, top)`` frame
    coordinates along x. The first spot (from the middle outwards, low first) where the label
    lies inside the area and clear of ``obstacles``; else the first clear one, else the middle
    (kept in ``plot``). An area too small for it has it just above."""
    pad = 0.05
    n = len(edges)
    spots = [
        np.array([edges[i, 0], edges[i, 1] + share * (edges[i, 2] - edges[i, 1]), 0.0])
        for i in (min(n - 1, int(f * (n - 1))) for f in (0.5, 0.6, 0.4, 0.7, 0.3, 0.8, 0.2))
        for share in (0.35, 0.5, 0.2, 0.65)
    ]

    def clear(box: tuple[float, float, float, float]) -> bool:
        inside = box[0] >= plot.x0 and box[2] <= plot.x1 and box[1] >= plot.y0 and box[3] <= plot.y1
        return inside and not any(box[0] < o[2] and o[0] < box[2] and box[1] < o[3] and o[1] < box[3] for o in obstacles)

    def within(box: tuple[float, float, float, float]) -> bool:
        under = edges[(edges[:, 0] >= box[0] - pad) & (edges[:, 0] <= box[2] + pad)]
        return box[0] >= edges[0, 0] and box[2] <= edges[-1, 0] and bool(len(under)) and bool((under[:, 1] <= box[1] - pad).all() and (under[:, 2] >= box[3] + pad).all())

    boxes = [(spot, (spot[0] - w / 2, spot[1] - h / 2, spot[0] + w / 2, spot[1] + h / 2)) for spot in spots]
    for spot, box in boxes:
        if within(box) and clear(box):
            return spot
    # too small to hold it: just above the area's top, from its middle outwards
    above = [np.array([edges[i, 0], max(edges[i, 2], edges[i, 1]) + h / 2 + 0.12, 0.0]) for i in (min(n - 1, int(f * (n - 1))) for f in (0.5, 0.75, 0.25, 1.0, 0.0))]
    for spot, box in [*((q, (q[0] - w / 2, q[1] - h / 2, q[0] + w / 2, q[1] + h / 2)) for q in above), *boxes]:
        if clear(box):
            return spot
    first = spots[0]
    return np.array([min(max(first[0], plot.x0 + w / 2), plot.x1 - w / 2), min(max(first[1], plot.y0 + h / 2), plot.y1 - h / 2), 0.0])


# ----- dots and areas that move -----------------------------------------------------------------


class _Dot:
    """A dot on a curve with its live value label, guides and tangent; :meth:`place` moves them."""

    def __init__(
        self, scene: FunctionPlot, axes: MathAxes, spec: PlotDot, expr: MathExpression, name: str, size: float, obstacles: list[tuple[float, float, float, float]]
    ) -> None:
        self.scene, self.axes, self.spec, self.expr, self.name, self.size = scene, axes, spec, expr, name, size
        self.obstacles = obstacles
        self.more_obstacles: Callable[[], list[tuple[float, float, float, float]]] = list
        theme = scene.theme
        self.dot = Dot(radius=DOT_RADIUS, color=theme.color(spec.color)).set_z_index(3)
        self.template = spec.label if spec.label is not None else "{name}({x}) = {y}"
        self.live = LiveLabel(scene, size, 3)
        self.label = self.live.group
        self.guides = VGroup(DashedLine(ORIGIN, RIGHT), DashedLine(ORIGIN, RIGHT)) if spec.guides else None
        self.tangent = Line(ORIGIN, RIGHT, color=theme.color(spec.tangent_color), stroke_width=4).set_z_index(1) if spec.tangent else None
        self.group = VGroup(*([self.guides] if self.guides is not None else []), self.dot, *([self.label] if self.template else []))
        self.x = spec.x
        self.driver = self.dot
        self.placed = False
        self.place(spec.x)
        self.placed = True

    @property
    def state(self) -> float:
        """Its x (what ``trace`` moves)."""
        return self.x

    @property
    def parts(self) -> list[Mobject]:
        """Everything that moves with the dot."""
        return [m for m in (self.dot, self.label if self.template else None, self.guides, self.tangent) if m is not None]

    def entrance(self, with_tangent: bool) -> Animation:
        """The dot pops in, then its label, guides and (``with_tangent``) tangent."""
        parts: list[Animation] = [FadeIn(self.dot, scale=0.4)]
        if self.guides is not None:
            parts.append(Create(self.guides))
        if self.template:
            parts.append(FadeIn(self.label, shift=UP * 0.1))
        if with_tangent and self.tangent is not None:
            parts.append(Create(self.tangent))
        return LaggedStart(*parts, lag_ratio=0.3)

    def place(self, x: float) -> None:
        """Move the dot to ``x`` on its curve; the label, guides and tangent follow."""
        y = self.expr.at(x)
        if not np.isfinite(y):
            return
        self.x = x
        axes = self.axes
        point = axes.point(x, y)
        self.dot.move_to(point)
        slope = self.expr.slope(x, 1e-5 * (axes.x_range[1] - axes.x_range[0]))
        ux, uy = axes.units
        direction = np.array([ux, (slope if np.isfinite(slope) else 0.0) * uy, 0.0])
        direction /= np.linalg.norm(direction)
        if self.tangent is not None:
            half = min(TANGENT_MAX, TANGENT_SHARE * axes.plot.width) / 2
            self.tangent.put_start_and_end_on(*clip_segment(point - direction * half, point + direction * half, axes.plot))
        if self.guides is not None:
            dim = self.scene.theme.color("dim")
            ox, oy = axes.origin
            to_x = DashedLine(point, axes.point(x, oy), color=dim, stroke_width=2, dash_length=0.08)
            to_y = DashedLine(point, axes.point(ox, y), color=dim, stroke_width=2, dash_length=0.08)
            for old, new in zip(self.guides, (to_x, to_y)):
                if self.placed:  # keep a dimmed look
                    new.set_stroke(opacity=old.get_stroke_opacity())
                old.become(new)
        if self.template:
            self._label(fill_label(self.template, {"x": float(x), "y": float(y), "slope": float(slope), "name": self.name}, self.spec.decimals), point, direction)

    @property
    def shown_text(self) -> str | None:
        """The label's text now."""
        return self.live.content

    def _label(self, content: str, point: np.ndarray, direction: np.ndarray) -> None:
        self.live.show(content)
        obstacles = self.obstacles + self.more_obstacles()
        self.label.move_to(dot_label_spot(point, direction, self.label.width, self.label.height, self.axes.plot, obstacles))


class _Area:
    """A shaded area under a curve (over another or the x axis) with its value label;
    :meth:`place` moves its right end."""

    def __init__(
        self, scene: FunctionPlot, axes: MathAxes, spec: PlotArea, top: MathExpression, bottom: MathExpression | None, name: str, color: str, size: float,
        obstacles: list[tuple[float, float, float, float]],
    ) -> None:
        self.scene, self.axes, self.spec, self.top, self.bottom, self.name, self.size = scene, axes, spec, top, bottom, name, size
        self.color, self.obstacles = color, obstacles
        self.shape = VMobject().set_z_index(-1)
        self.live = LiveLabel(scene, size, 2)
        self.label = self.live.group
        self.group = VGroup(self.shape, *([self.label] if spec.label else []))
        self.start, self.end = spec.between
        self.driver = self.shape
        self.placed = False
        self.place(self.end)
        self.placed = True

    @property
    def state(self) -> float:
        """Its right end (what ``trace`` moves)."""
        return self.end

    @property
    def shown_text(self) -> str | None:
        """The label's text now."""
        return self.live.content

    @property
    def parts(self) -> list[Mobject]:
        """Everything that changes with the area."""
        return [self.shape, *([self.label] if self.spec.label else [])]

    def entrance(self) -> Animation:
        """The area fades in from the axis, then its label."""
        parts: list[Animation] = [FadeIn(self.shape)]
        if self.spec.label:
            parts.append(FadeIn(self.label))
        return LaggedStart(*parts, lag_ratio=0.5)

    def place(self, end: float) -> None:
        """Move the right end to ``end``: the shape and the label's value follow."""
        self.end = end
        axes = self.axes
        y0, y1 = axes.y_range
        lo, hi = (self.start, end) if end >= self.start else (end, self.start)
        xs = np.linspace(lo, hi, max(2, int(axes.plot.width * SAMPLES_PER_UNIT * (hi - lo) / (axes.x_range[1] - axes.x_range[0])) + 2))
        top = self.top(xs)
        bottom = self.bottom(xs) if self.bottom is not None else np.zeros_like(xs)
        ok = np.isfinite(top) & np.isfinite(bottom)
        xs, top, bottom = xs[ok], np.clip(top[ok], y0, y1), np.clip(bottom[ok], y0, y1)
        if len(xs) >= 2:
            points = [axes.point(x, y) for x, y in zip(xs, top)] + [axes.point(x, y) for x, y in zip(xs[::-1], bottom[::-1])]
            opacity = self.shape.get_fill_opacity() if self.placed else self.spec.opacity
            shape = Polygon(*points, stroke_width=0, fill_color=self.color, fill_opacity=opacity)
            self.shape.become(shape)
            self.shape.set_z_index(-1)
        if not self.spec.label:
            return
        heights = self.top(xs) - (self.bottom(xs) if self.bottom is not None else 0.0)
        size = float(np.sum((heights[1:] + heights[:-1]) / 2 * np.diff(xs))) if len(xs) >= 2 else 0.0
        size = size if end >= self.start else -size
        content = fill_label(self.spec.label, {"area": size, "from": float(self.start), "to": float(end), "name": self.name}, self.spec.decimals)
        self.live.show(content)
        if len(xs) >= 2:
            edges = np.column_stack([[axes.x_pos(float(x)) for x in xs], [axes.y_pos(float(y)) for y in bottom], [axes.y_pos(float(y)) for y in top]])
            self.label.move_to(area_label_spot(edges, self.label.width, self.label.height, axes.plot, self.obstacles))
