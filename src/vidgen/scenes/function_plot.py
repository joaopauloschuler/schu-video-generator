"""``function_plot``: maths axes with functions f(x), dots that travel along a curve with a live
value label (and a tangent following them), and shaded areas under a curve between bounds.

The expressions are parsed by :func:`~vidgen.mathexpr.parse_expression` (a whitelisted parser,
never ``eval``). The axes (:func:`math_axes`, :class:`MathAxes`) are maths style: they cross at the origin when it is in
view, with arrow tips, ticks and plain ``Text`` labels (no LaTeX). The ``trace`` beat action
moves a dot (or an area's right end) to a new x (DESIGN §87.6).
"""

import string
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .line_chart import LineChart

#: Names given to functions written without one, in order.
DEFAULT_NAMES = ("f", "g", "h", "p", "q", "r", "s", "u", "v", "w")
#: Curve samples per Manim unit of plot width (at least :data:`MIN_SAMPLES`).
SAMPLES_PER_UNIT, MIN_SAMPLES = 90, 240
#: Stroke width of a curve; radius of a dot; fill opacity of an area by default.
CURVE_WIDTH, DOT_RADIUS, AREA_OPACITY = 5.0, 0.1, 0.3
#: A tangent's length as a share of the plot's width, at most :data:`TANGENT_MAX` units.
TANGENT_SHARE, TANGENT_MAX = 0.4, 4.5
#: Opacity of the plate behind a dot's value label (the theme background colour).
PLATE_OPACITY = 0.8
#: Opacity of the grid lines.
GRID_OPACITY = 0.2
#: Space kept free beyond the arrow tips (units) and the length of a tick mark either side.
TIP_ROOM, TICK = 0.3, 0.07
#: In an ``auto`` aspect, the plot is at most this many times as tall as it is wide (9:16).
MAX_TALL = 1.5
#: The fields a dot's and an area's ``label`` may use.
DOT_FIELDS = ("x", "y", "slope", "name")
AREA_FIELDS = ("area", "from", "to", "name")


# ----- labels with live values (no manim) ------------------------------------------------------


def _number(value: float, decimals: int, spec: str = "") -> str:
    """``value`` as a label shows it: with ``spec`` (``.3f``) or ``decimals`` places, never
    ``-0``, a typographic minus."""
    text = format(value, spec) if spec else f"{value:.{decimals}f}"
    if text.startswith("-") and float(text) == 0:
        text = text[1:]
    return text.replace("-", "−")


def fill_label(template: str, values: dict[str, float | str], decimals: int) -> str:
    """``template`` with its ``{field}`` / ``{field:.2f}`` replaced from ``values`` (numbers with
    :func:`_number`)."""
    out = []
    for literal, name, spec, _ in string.Formatter().parse(template):
        out.append(literal)
        if name is None:
            continue
        value = values[name]
        out.append(_number(value, decimals, spec or "") if isinstance(value, float) else format(value, spec or ""))
    return "".join(out)


def label_problem(template: str, fields: Sequence[str]) -> str | None:
    """Why ``template`` is not a label with ``fields`` (``None`` when it is)."""
    try:
        names = [name for _, name, _, _ in string.Formatter().parse(template) if name is not None]
    except ValueError as exc:
        return f"label {template!r}: {exc} (write {{ and }} as {{{{ and }}}})"
    bad = [n for n in names if n not in fields]
    if bad:
        return f"label {template!r}: unknown field {{{bad[0]}}}; it may use {', '.join('{' + f + '}' for f in fields)}"
    try:
        fill_label(template, {f: (1.0 if f != "name" else "f") for f in fields}, 1)
    except ValueError as exc:
        return f"label {template!r}: {exc}"
    return None


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
    target_patterns = ("title", "axes", "function<N>", "function:<name>", "dot<N>", "tangent<N>", "area<N>")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        functions: list[PlotFunction] = Field(min_length=1)
        """The functions: 'x^2', 'f(x) = sin(x)' or {expr, name, label, color, domain, dashed}; a later one may use an earlier one (g(x) = f(x) + 1)."""
        x_range: tuple[float, float]
        """[from, to]: the x axis."""
        y_range: tuple[float, float] | None = None
        """[from, to]: the y axis; default: from the functions' values."""
        dots: list[PlotDot] = []
        """Dots on the curves: {on, x, label, tangent, guides}; moved by the trace action."""
        areas: list[PlotArea] = []
        """Shaded areas: {under, over, between, label}."""
        x_label: TranslatableStr = "x"
        """Name at the end of the x axis ('' for none)."""
        y_label: TranslatableStr = "y"
        """Name at the top of the y axis ('' for none)."""
        grid: bool = True
        """Faint lines at the ticks."""
        aspect: Literal["auto", "equal"] = "auto"
        """auto: the plot fills the space; equal: one unit is as long on both axes (true angles and slopes)."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: function 1 with the axes at beat 1, then one function, dot or area per beat; all: everything in beat 1."""
        title_size: ThemeSize = "heading"
        """Title size (1.3x in a portrait frame)."""
        title_color: ThemeColor = "text"
        """Title colour."""
        label_size: ThemeSize = "caption"
        """Size of the tick, axis, curve, dot and area labels (never below the readable minimum)."""

        @model_validator(mode="after")
        def _check(self) -> "FunctionPlot.Params":
            for name, (lo, hi) in (("x_range", self.x_range), ("y_range", self.y_range or (0.0, 1.0))):
                if hi <= lo:
                    raise ValueError(f"{name} [{lo:g}, {hi:g}]: the second end must be greater than the first")
            expressions = self.expressions()
            xs = np.linspace(*self.x_range, 401)
            for k, (name, expr) in enumerate(expressions.items()):
                spec = self.functions[k]
                lo, hi = spec.domain or self.x_range
                if not np.isfinite(expr(np.linspace(max(lo, self.x_range[0]), min(hi, self.x_range[1]), 401))).any():
                    raise ValueError(f"functions[{k}] {name}(x) = {expr.text} has no value on the x range {list(self.x_range)}")
            if self.y_range is None:
                auto_y_range(np.concatenate([e(xs) for e in expressions.values()]))
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
            lo, hi = self.x_range
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
        """``title`` (if any), ``axes``, ``function<N>`` and ``function:<name>``, ``dot<N>`` (and
        ``tangent<N>`` for a dot with a tangent), ``area<N>``."""
        names = (["title"] if params.title else []) + ["axes"]
        for k, name in enumerate(params.function_names(), start=1):
            names += [f"function{k}", f"function:{name}"]
        for k, dot in enumerate(params.dots, start=1):
            names += [f"dot{k}"] + ([f"tangent{k}"] if dot.tangent else [])
        return names + [f"area{k}" for k in range(1, len(params.areas) + 1)]

    @classmethod
    def reveal_steps(cls, params: Any) -> list[RevealStep]:
        """One step per function (rising or falling over the x range), dot and area."""
        expressions = params.expressions()
        xs = np.linspace(*params.x_range, 9)
        steps = []
        for k, expr in enumerate(expressions.values(), start=1):
            values = [float(v) for v in expr(xs) if np.isfinite(v)]
            steps.append(RevealStep(f"function{k}", value_trend(values)))
        steps += [RevealStep(f"dot{k}") for k in range(1, len(params.dots) + 1)]
        steps += [RevealStep(f"area{k}") for k in range(1, len(params.areas) + 1)]
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
        sample_x = np.linspace(*p.x_range, 801)
        y_range = p.y_range or auto_y_range(np.concatenate([expressions[n](sample_x) for n in names]))
        axes = math_axes(
            body, p.x_range, y_range, label=lambda s: self.text(s, size=size, color="dim"), aspect=p.aspect,
            grid=p.grid, x_title=self.text(p.x_label, size=size, color="dim") if p.x_label else None,
            y_title=self.text(p.y_label, size=size, color="dim") if p.y_label else None,
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

        revealed = self._revealed_by_actions()
        # each target's own entrance, and the targets it needs on screen first (in order)
        bare: dict[int, Callable[[], list[Animation]]] = {}
        needs: dict[int, list[Target]] = {}

        def bring(chain: Sequence[Target]) -> list[Animation]:
            return [a for t in dict.fromkeys(chain) if not self.is_shown(t) for a in bare[id(t)]()]

        def add(names: str | list[str], mobject: Mobject, own: Callable[[], list[Animation]], before: list[Target]) -> Target:
            target = self.target(names, mobject, entrance=lambda: bring([*needs[id(target)], target]))
            bare[id(target)], needs[id(target)] = own, before
            return target

        base: list[Target] = []
        if title is not None:
            base.append(add("title", title, lambda: [FadeIn(title)], []))
        axes_target = add("axes", axes.group, lambda: [FadeIn(axes.group)], list(base))
        base.append(axes_target)
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
        self.dots, self.areas = dots, areas
        self._dot_targets, self._area_targets = dot_targets, area_targets

        # an item a reveal action shows keeps its slot, empty: the others keep their beats
        items = [[] if revealed.intersection(t.names) else [t] for t in [*function_targets, *dot_targets, *area_targets]]

        def step(targets: list[Target]) -> Callable[[], list[Animation]]:
            return lambda: bring([*base, *(d for t in targets for d in [*needs[id(t)], t])])

        steps = [step([t for own in items for t in own])] if p.reveal == "all" else [step(own) for own in items]
        self.reveal(steps, fraction=0.8, cap=2.0)
        self.finish()

    def _revealed_by_actions(self) -> set[str]:
        """Target names a ``reveal`` action shows: the scene leaves them to it."""
        names = type(self).target_names(self.params)
        return {name for action in self.action_uses("reveal") for pattern in action.config.targets() for name in names if fnmatchcase(name, pattern)}

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
            label = VGroup(_plate(words), words).set_z_index(1)  # readable on an area or the grid
            box = place_label(label, curves[k].get_all_points(), axes.plot, obstacles, curve_points)
            obstacles.append(box)
            out.append(label)
        return out


# ----- axes (no scene) --------------------------------------------------------------------------


@dataclass
class MathAxes:
    """Maths axes laid out by :func:`math_axes`: ``plot`` (the region the ranges map to),
    ``x_range`` / ``y_range``, where the axes cross (``origin``, data units), ``group`` (grid,
    axis lines with tips, ticks, labels), ``labels`` (the tick and axis labels)."""

    plot: Region
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    origin: tuple[float, float]
    group: VGroup = field(default_factory=VGroup)
    labels: list[Mobject] = field(default_factory=list)

    def x_pos(self, x: float) -> float:
        """Frame x of a data x."""
        lo, hi = self.x_range
        return self.plot.x0 + (x - lo) / (hi - lo) * self.plot.width

    def y_pos(self, y: float) -> float:
        """Frame y of a data y."""
        lo, hi = self.y_range
        return self.plot.y0 + (y - lo) / (hi - lo) * self.plot.height

    def point(self, x: float, y: float) -> np.ndarray:
        """The frame point of a data point."""
        return np.array([self.x_pos(x), self.y_pos(y), 0.0])

    @property
    def units(self) -> tuple[float, float]:
        """Frame units per data unit along x and y."""
        return self.plot.width / (self.x_range[1] - self.x_range[0]), self.plot.height / (self.y_range[1] - self.y_range[0])

    def line_points(self, step: float = 0.1) -> np.ndarray:
        """Frame points along both axis lines, ``step`` apart (for labels to keep off them)."""
        ax, ay = self.x_pos(self.origin[0]), self.y_pos(self.origin[1])
        xs = np.arange(self.plot.x0, self.plot.x1 + step, step)
        ys = np.arange(self.plot.y0, self.plot.y1 + step, step)
        return np.vstack([np.column_stack([xs, np.full_like(xs, ay), np.zeros_like(xs)]), np.column_stack([np.full_like(ys, ax), ys, np.zeros_like(ys)])])

    @staticmethod
    def label_box(m: Mobject) -> tuple[float, float, float, float]:
        """``(x0, y0, x1, y1)`` of a mobject."""
        return (m.get_left()[0], m.get_bottom()[1], m.get_right()[0], m.get_top()[1])


def _ticks(lo: float, hi: float, count: int) -> list[float]:
    return [t for t in axis_ticks(lo, hi, count) if lo - 1e-9 <= t <= hi + 1e-9]


def _every(positions: list[float], extents: list[float], gap: float, keep: float | None) -> list[int]:
    """Indices of evenly spaced labels to keep (every k-th, aligned on the one at ``keep``)."""
    n = len(positions)
    anchor = positions.index(keep) if keep in positions else 0
    for k in range(1, n + 1):
        kept = [i for i in range(n) if (i - anchor) % k == 0]
        if all(abs(positions[b] - positions[a]) >= (extents[a] + extents[b]) / 2 + gap for a, b in zip(kept, kept[1:])):
            return kept
    return [anchor]


def math_axes(
    area: Region,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    *,
    label: Callable[[str], Mobject],
    aspect: str = "auto",
    grid: bool = True,
    x_title: Mobject | None = None,
    y_title: Mobject | None = None,
    color: Any = "dim",
) -> MathAxes:
    """Maths axes in ``area``: crossing at the origin when it is in view (else along the bottom /
    left edge), arrow tips at the positive ends, round ticks with labels made by ``label``
    (a single ``0`` at the origin), faint grid lines, the axis titles by the tips; ``aspect``
    ``equal`` gives both axes the same unit."""
    dim = resolve_color(color)
    portrait = area.height > area.width
    x_ticks = _ticks(*x_range, 5 if portrait else 8)
    y_ticks = _ticks(*y_range, 8 if portrait else 6)
    ox = min(max(0.0, x_range[0]), x_range[1])
    oy = min(max(0.0, y_range[0]), y_range[1])
    both_inside = x_range[0] < 0 < x_range[1] and y_range[0] < 0 < y_range[1]
    x_texts = {t: label(tick_texts([t])[0].replace("-", "−")) for t in x_ticks if not (both_inside and t == 0) and not (t == ox and oy != 0 and y_range[0] < 0 < y_range[1])}
    y_texts = {t: label(tick_texts([t])[0].replace("-", "−")) for t in y_ticks if not (t == oy and x_range[0] < 0 < x_range[1])}
    gap = 0.14
    tick_w = max((m.width for m in y_texts.values()), default=0.0)
    tick_h = max((m.height for m in x_texts.values()), default=0.0)
    half_x = max((m.width for m in x_texts.values()), default=0.0) / 2  # an end tick's label is centred on the end

    def layout(left: float, bottom: float) -> Region:
        region = Region(area.x0 + max(left, half_x), area.y0 + bottom, area.x1 - max(TIP_ROOM, half_x), area.y1 - TIP_ROOM)
        if aspect == "equal":
            unit = min(region.width / (x_range[1] - x_range[0]), region.height / (y_range[1] - y_range[0]))
            w, h = unit * (x_range[1] - x_range[0]), unit * (y_range[1] - y_range[0])
        else:
            w, h = region.width, min(region.height, region.width * MAX_TALL)
        cx, cy = region.center[0], region.center[1]
        return Region(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    left = bottom = 0.0
    plot = layout(left, bottom)
    for _ in range(3):  # room for the labels beside an axis near (or on) an edge
        axes = MathAxes(plot, x_range, y_range, (ox, oy))
        need_left = max(0.0, tick_w + 2 * gap - (axes.x_pos(ox) - plot.x0))
        need_bottom = max(0.0, tick_h + 2 * gap - (axes.y_pos(oy) - plot.y0))
        if need_left < 1e-3 and need_bottom < 1e-3:
            break
        left, bottom = left + need_left, bottom + need_bottom
        plot = layout(left, bottom)
    axes = MathAxes(plot, x_range, y_range, (ox, oy))
    ax, ay = axes.x_pos(ox), axes.y_pos(oy)

    lines = VGroup()
    if grid:
        for t in x_ticks:
            if abs(t - ox) > 1e-9:
                lines.add(Line([axes.x_pos(t), plot.y0, 0], [axes.x_pos(t), plot.y1, 0], stroke_width=1, color=dim, stroke_opacity=GRID_OPACITY))
        for t in y_ticks:
            if abs(t - oy) > 1e-9:
                lines.add(Line([plot.x0, axes.y_pos(t), 0], [plot.x1, axes.y_pos(t), 0], stroke_width=1, color=dim, stroke_opacity=GRID_OPACITY))
    lines.set_z_index(-2)
    tip = dict(tip_length=0.18, tip_width=0.16)
    x_axis = Line([plot.x0, ay, 0], [plot.x1 + TIP_ROOM * 0.7, ay, 0], color=dim, stroke_width=2.5)
    y_axis = Line([ax, plot.y0, 0], [ax, plot.y1 + TIP_ROOM * 0.7, 0], color=dim, stroke_width=2.5)
    x_axis.add_tip(**tip)
    y_axis.add_tip(**tip)
    marks = VGroup(
        *[Line([axes.x_pos(t), ay - TICK, 0], [axes.x_pos(t), ay + TICK, 0], color=dim, stroke_width=2) for t in x_ticks if abs(t - ox) > 1e-9 or ay == plot.y0],
        *[Line([ax - TICK, axes.y_pos(t), 0], [ax + TICK, axes.y_pos(t), 0], color=dim, stroke_width=2) for t in y_ticks if abs(t - oy) > 1e-9 or ax == plot.x0],
    )
    xs = sorted(x_texts)
    keep_x = _every([axes.x_pos(t) for t in xs], [x_texts[t].width for t in xs], 0.3, axes.x_pos(0.0) if 0.0 in xs else None)
    ys = sorted(y_texts)
    keep_y = _every([axes.y_pos(t) for t in ys], [y_texts[t].height for t in ys], 0.25, None)
    labels: list[Mobject] = []
    for i in keep_x:
        t = xs[i]
        labels.append(x_texts[t].move_to([axes.x_pos(t), ay - TICK - gap - x_texts[t].height / 2, 0]))
    for i in keep_y:
        t = ys[i]
        labels.append(y_texts[t].move_to([ax - TICK - gap - y_texts[t].width / 2, axes.y_pos(t), 0]))
    if both_inside:
        zero = label("0")
        labels.append(zero.move_to([ax - gap - zero.width / 2, ay - gap - zero.height / 2, 0]))
    if x_title is not None:
        below = ay > plot.y1 - 1e-6
        x_title.move_to([plot.x1 + TIP_ROOM * 0.7 - x_title.width / 2, ay + (-1 if below else 1) * (gap + x_title.height / 2 + TICK), 0])
        labels.append(x_title)
    if y_title is not None:
        on_left = ax > plot.x1 - 1e-6
        y_title.move_to([ax + (-1 if on_left else 1) * (gap + TICK + y_title.width / 2), plot.y1 + TIP_ROOM * 0.7 - y_title.height / 2, 0])
        labels.append(y_title)
    axes.labels = labels
    for m in labels:  # numbers stay readable where a curve crosses them
        m.set_z_index(1)
    axes.group = VGroup(lines, x_axis, y_axis, marks, *labels)
    return axes


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


def place_label(
    label: Mobject, curve: np.ndarray, plot: Region, obstacles: list[tuple[float, float, float, float]], avoid: np.ndarray
) -> tuple[float, float, float, float]:
    """Move ``label`` beside a point of ``curve`` (frame points), above it or below, the first
    place inside ``plot`` that covers no ``obstacles`` box and no ``avoid`` point; returns its box."""
    w, h = label.width, label.height
    pad = 0.06

    def free(cx: float, cy: float) -> bool:
        box = (cx - w / 2 - pad, cy - h / 2 - pad, cx + w / 2 + pad, cy + h / 2 + pad)
        if box[0] < plot.x0 or box[2] > plot.x1 or box[1] < plot.y0 or box[3] > plot.y1:
            return False
        if any(box[0] < o[2] and o[0] < box[2] and box[1] < o[3] and o[1] < box[3] for o in obstacles):
            return False
        inside = (avoid[:, 0] > box[0]) & (avoid[:, 0] < box[2]) & (avoid[:, 1] > box[1]) & (avoid[:, 1] < box[3])
        return not bool(inside.any())

    def put(cx: float, cy: float) -> tuple[float, float, float, float]:
        label.move_to([cx, cy, 0])
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    n = len(curve)
    shares = [0.88, 0.72, 0.56, 0.4, 0.97, 0.24, 0.1, *np.linspace(0.05, 0.95, 19)]
    for share in shares:
        i = min(n - 1, max(1, int(share * (n - 1))))
        a, b = curve[i - 1], curve[min(n - 1, i + 1)]
        tangent = b[:2] - a[:2]
        normal = np.array([-tangent[1], tangent[0]])
        normal = normal / (np.linalg.norm(normal) or 1.0)
        if normal[1] < 0:
            normal = -normal
        for side in (1, -1):
            d = normal * side
            reach = 0.16 + 0.5 * (abs(d[0]) * w + abs(d[1]) * h)
            cx, cy = curve[i][0] + d[0] * reach, curve[i][1] + d[1] * reach
            if free(cx, cy):
                return put(cx, cy)
    # anywhere free in the plot, nearest to the curve's right part
    near = curve[min(n - 1, int(0.88 * (n - 1)))]
    grid_x = np.arange(plot.x0 + w / 2 + pad, plot.x1 - w / 2 - pad, 0.12)
    grid_y = np.arange(plot.y0 + h / 2 + pad, plot.y1 - h / 2 - pad, 0.12)
    spots = sorted(((x, y) for x in grid_x for y in grid_y), key=lambda q: (q[0] - near[0]) ** 2 + (q[1] - near[1]) ** 2)
    for cx, cy in spots:
        if free(cx, cy):
            return put(cx, cy)
    end = curve[-1]
    return put(min(max(end[0] - w / 2, plot.x0 + w / 2), plot.x1 - w / 2), min(max(end[1] + h, plot.y0 + h / 2), plot.y1 - h / 2))


def clip_segment(a: np.ndarray, b: np.ndarray, region: Region) -> tuple[np.ndarray, np.ndarray]:
    """The part of the segment ``a`` -> ``b`` inside ``region`` (Liang-Barsky); a point when none is."""
    lo, hi = 0.0, 1.0
    d = b - a
    for p, q in ((-d[0], a[0] - region.x0), (d[0], region.x1 - a[0]), (-d[1], a[1] - region.y0), (d[1], region.y1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return a, a
            continue
        t = q / p
        if p < 0:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
    if lo > hi:
        return a, a
    return a + d * lo, a + d * hi


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


def _plate(text: Mobject) -> Mobject:
    """A plate in the background colour behind ``text`` (so grid lines and curves do not cross it)."""
    return RoundedRectangle(
        width=text.width + 0.2, height=text.height + 0.14, corner_radius=0.06, stroke_width=0,
        fill_color=current_theme().background, fill_opacity=PLATE_OPACITY,
    ).move_to(text)


class _LiveLabel:
    """Text on a plate (``group``) whose text changes as its item moves; :meth:`show` rebuilds it
    only when the text changes, keeping a dimmed opacity."""

    def __init__(self, scene: FunctionPlot, size: float, z: int) -> None:
        self.scene, self.size, self.z = scene, size, z
        self.text = scene.text(" ", size=size)
        self.plate = _plate(self.text)
        self.group = VGroup(self.plate, self.text).set_z_index(z)
        self.content: str | None = None

    def show(self, content: str) -> None:
        """Write ``content``."""
        if content == self.content:
            return
        opacity = self.text.get_fill_opacity() if self.content is not None else 1.0
        text = self.scene.text(content, size=self.size)
        text.set_fill(opacity=opacity)
        self.text.become(text)
        self.text.original_text = text.original_text  # what the layout dump reads
        plate = _plate(self.text)
        plate.set_fill(opacity=PLATE_OPACITY * opacity)
        self.plate.become(plate)
        self.group.set_z_index(self.z)  # become() brought parts at z 0, under the plate
        self.content = content


class _Dot:
    """A dot on a curve with its live value label, guides and tangent; :meth:`place` moves them."""

    def __init__(
        self, scene: FunctionPlot, axes: MathAxes, spec: PlotDot, expr: MathExpression, name: str, size: float, obstacles: list[tuple[float, float, float, float]]
    ) -> None:
        self.scene, self.axes, self.spec, self.expr, self.name, self.size = scene, axes, spec, expr, name, size
        self.obstacles = obstacles
        theme = scene.theme
        self.dot = Dot(radius=DOT_RADIUS, color=theme.color(spec.color)).set_z_index(3)
        self.template = spec.label if spec.label is not None else "{name}({x}) = {y}"
        self.live = _LiveLabel(scene, size, 3)
        self.label = self.live.group
        self.guides = VGroup(DashedLine(ORIGIN, RIGHT), DashedLine(ORIGIN, RIGHT)) if spec.guides else None
        self.tangent = Line(ORIGIN, RIGHT, color=theme.color(spec.tangent_color), stroke_width=4).set_z_index(1) if spec.tangent else None
        self.group = VGroup(*([self.guides] if self.guides is not None else []), self.dot, *([self.label] if self.template else []))
        self.x = spec.x
        self.placed = False
        self.place(spec.x)
        self.placed = True

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
        self.label.move_to(dot_label_spot(point, direction, self.label.width, self.label.height, self.axes.plot, self.obstacles))


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
        self.live = _LiveLabel(scene, size, 2)
        self.label = self.live.group
        self.group = VGroup(self.shape, *([self.label] if spec.label else []))
        self.start, self.end = spec.between
        self.placed = False
        self.place(self.end)
        self.placed = True

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


class _Trace(Animation):
    """Moves a dot or an area's right end from ``start`` to ``end`` (data x)."""

    def __init__(self, item: _Dot | _Area, start: float, end: float, **kwargs: Any) -> None:
        mobject = item.dot if isinstance(item, _Dot) else item.shape
        super().__init__(mobject, **kwargs)
        self.item, self.start, self.end = item, start, end

    def interpolate_mobject(self, alpha: float) -> None:
        self.item.place(self.start + (self.end - self.start) * self.rate_func(alpha))


class _Moved(Animation):
    """Marks a part another animation moves, so Manim redraws it on every frame."""

    def interpolate_mobject(self, alpha: float) -> None:
        pass


@action("trace")
class Trace(Action):
    """On a function_plot: a dot (dot<N>) travels along its curve to x = `to`, its value label,
    guides and tangent following; an area (area<N>) grows or shrinks to end at x = `to`, its
    value following. `until: <beat>` moves it back."""

    class Options(ActionOptions):
        to: float
        """The x it ends at (data units of the x axis)."""

    run_time = 2.0
    reversible = True

    def __init__(self, options: ActionOptions, config: Any) -> None:
        super().__init__(options, config)
        self.saved: list[tuple[_Dot | _Area, float]] = []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """A function_plot's dots and areas only; ``to`` where the dot's function has a value."""
        if not issubclass(scene_cls, FunctionPlot):
            return [("target", "trace moves the dots and areas of a function_plot")]
        names = scene_cls.target_names(params)
        matched = [n for pattern in self.config.targets() for n in names if fnmatchcase(n, pattern)]
        problems: list[tuple[str, str]] = []
        for name in dict.fromkeys(matched):
            if name.startswith("dot"):
                dot = params.dots[int(name[3:]) - 1]
                problem = params.x_problem(params.function_of(dot.on, ""), self.options.to)
            elif name.startswith("area"):
                area = params.areas[int(name[4:]) - 1]
                problem = params.x_problem(params.function_of(area.under, ""), self.options.to)
                if problem is None and area.over is not None:
                    problem = params.x_problem(area.over, self.options.to)
            else:
                problem = "trace moves a dot<N> or an area<N>"
            if problem:
                problems.append(("to", f"{name}: {problem}"))
        return problems

    def _items(self, scene: NarratedScene, targets: list[Target]) -> list[_Dot | _Area]:
        items: list[_Dot | _Area] = []
        for target in targets:
            for k, own in enumerate(scene._dot_targets):
                if own is target:
                    items.append(scene.dots[k])
            for k, own in enumerate(scene._area_targets):
                if own is target:
                    items.append(scene.areas[k])
        return items

    def _moves(self, scene: NarratedScene, item: _Dot | _Area, end: float) -> list[Animation]:
        start = item.x if isinstance(item, _Dot) else item.end
        moving = _Trace(item, start, end, rate_func=smooth)
        shown = [m for m in item.parts if scene.on_screen_parts(m) and m is not moving.mobject]
        return [moving, *[_Moved(m) for m in shown]]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Each dot / area moves to ``to``."""
        anims: list[Animation] = []
        for item in self._items(scene, targets):
            self.saved.append((item, item.x if isinstance(item, _Dot) else item.end))
            anims += self._moves(scene, item, self.options.to)
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to where they were."""
        saved, self.saved = self.saved, []
        return [a for item, x in saved for a in self._moves(scene, item, x)]
