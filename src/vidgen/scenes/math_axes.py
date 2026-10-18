"""Shared parts of the maths scenes (``function_plot``, ``number_line``; DESIGN §87.6, §87.7):
maths axes (:func:`math_axes`) and their tick labels, labels with live values, label placement
clear of curves and other labels, and the animations the ``trace`` action plays."""

import string
from collections.abc import Callable, Sequence
from fnmatch import fnmatchcase
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from vidgen.api import *

#: Opacity of the plate behind a live label (the theme background colour).
PLATE_OPACITY = 0.8
#: Opacity of the grid lines.
GRID_OPACITY = 0.2
#: Space kept free beyond the arrow tips (units) and the length of a tick mark either side.
TIP_ROOM, TICK = 0.3, 0.07
#: In an ``auto`` aspect, the plot is at most this many times as tall as it is wide (9:16).
MAX_TALL = 1.5


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


def ticks_within(lo: float, hi: float, count: int) -> list[float]:
    return [t for t in axis_ticks(lo, hi, count) if lo - 1e-9 <= t <= hi + 1e-9]


def thinned_labels(positions: list[float], extents: list[float], gap: float, keep: float | None) -> list[int]:
    """Indices of evenly spaced labels to keep (every k-th, aligned on the one at ``keep``)."""
    n = len(positions)
    anchor = positions.index(keep) if keep in positions else 0
    for k in range(1, n + 1):
        kept = [i for i in range(n) if (i - anchor) % k == 0]
        if all(abs(positions[b] - positions[a]) >= (extents[a] + extents[b]) / 2 + gap for a, b in zip(kept, kept[1:])):
            return kept
    return [anchor]


def tick_label(value: float, label: Callable[[str], Mobject]) -> Mobject:
    """A tick's number made by ``label``, negative ones with a typographic minus."""
    return label(tick_texts([value])[0].replace("-", "−"))


def _shaped(region: Region, x_range: tuple[float, float], y_range: tuple[float, float], aspect: str) -> Region:
    """The plot in ``region``, centred: ``equal`` gives both axes one unit; ``auto`` fills it, at
    most :data:`MAX_TALL` times as tall as wide."""
    if aspect == "equal":
        unit = min(region.width / (x_range[1] - x_range[0]), region.height / (y_range[1] - y_range[0]))
        w, h = unit * (x_range[1] - x_range[0]), unit * (y_range[1] - y_range[0])
    else:
        w, h = region.width, min(region.height, region.width * MAX_TALL)
    cx, cy = region.center[0], region.center[1]
    return Region(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


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
    visible: bool = True,
) -> MathAxes:
    """Maths axes in ``area``: crossing at the origin when it is in view (else along the bottom /
    left edge), arrow tips at the positive ends, round ticks with labels made by ``label``
    (a single ``0`` at the origin), faint grid lines, the axis titles by the tips; ``aspect``
    ``equal`` gives both axes the same unit. ``visible=False``: only the mapping (the plot fills
    ``area`` but for :data:`TIP_ROOM` on each side; nothing is drawn)."""
    if not visible:
        inner = Region(area.x0 + TIP_ROOM, area.y0 + TIP_ROOM, area.x1 - TIP_ROOM, area.y1 - TIP_ROOM)
        return MathAxes(_shaped(inner, x_range, y_range, aspect), x_range, y_range, (min(max(0.0, x_range[0]), x_range[1]), min(max(0.0, y_range[0]), y_range[1])))
    dim = resolve_color(color)
    portrait = area.height > area.width
    x_ticks = ticks_within(*x_range, 5 if portrait else 8)
    y_ticks = ticks_within(*y_range, 8 if portrait else 6)
    ox = min(max(0.0, x_range[0]), x_range[1])
    oy = min(max(0.0, y_range[0]), y_range[1])
    both_inside = x_range[0] < 0 < x_range[1] and y_range[0] < 0 < y_range[1]
    x_texts = {t: tick_label(t, label) for t in x_ticks if not (both_inside and t == 0) and not (t == ox and oy != 0 and y_range[0] < 0 < y_range[1])}
    y_texts = {t: tick_label(t, label) for t in y_ticks if not (t == oy and x_range[0] < 0 < x_range[1])}
    gap = 0.14
    tick_w = max((m.width for m in y_texts.values()), default=0.0)
    tick_h = max((m.height for m in x_texts.values()), default=0.0)
    half_x = max((m.width for m in x_texts.values()), default=0.0) / 2  # an end tick's label is centred on the end

    def layout(left: float, bottom: float) -> Region:
        return _shaped(Region(area.x0 + max(left, half_x), area.y0 + bottom, area.x1 - max(TIP_ROOM, half_x), area.y1 - TIP_ROOM), x_range, y_range, aspect)

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
    keep_x = thinned_labels([axes.x_pos(t) for t in xs], [x_texts[t].width for t in xs], 0.3, axes.x_pos(0.0) if 0.0 in xs else None)
    ys = sorted(y_texts)
    keep_y = thinned_labels([axes.y_pos(t) for t in ys], [y_texts[t].height for t in ys], 0.25, None)
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


def label_plate(text: Mobject) -> Mobject:
    """A plate in the background colour behind ``text`` (so grid lines and curves do not cross it)."""
    return RoundedRectangle(
        width=text.width + 0.2, height=text.height + 0.14, corner_radius=0.06, stroke_width=0,
        fill_color=current_theme().background, fill_opacity=PLATE_OPACITY,
    ).move_to(text)


class LiveLabel:
    """Text on a plate (``group``) whose text changes as its item moves; :meth:`show` rebuilds it
    only when the text changes, keeping a dimmed opacity."""

    def __init__(self, scene: NarratedScene, size: float, z: int) -> None:
        self.scene, self.size, self.z = scene, size, z
        self.text = scene.text(" ", size=size)
        self.plate = label_plate(self.text)
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
        plate = label_plate(self.text)
        plate.set_fill(opacity=PLATE_OPACITY * opacity)
        self.plate.become(plate)
        self.group.set_z_index(self.z)  # become() brought parts at z 0, under the plate
        self.content = content


class Traced(Protocol):
    """Something the ``trace`` action moves: its ``state`` (a number, or an ``[x, y]`` array) goes
    to another by :meth:`place`; ``driver`` is the mobject the animation runs on, ``parts``
    everything that may change with it."""

    driver: Mobject

    @property
    def state(self) -> Any: ...

    @property
    def parts(self) -> list[Mobject]: ...

    def place(self, state: Any) -> None: ...


class TraceMove(Animation):
    """Moves a traced item from the state ``start`` to ``end`` (numbers or arrays)."""

    def __init__(self, item: Traced, start: Any, end: Any, **kwargs: Any) -> None:
        super().__init__(item.driver, **kwargs)
        self.item, self.start, self.end = item, start, end

    def interpolate_mobject(self, alpha: float) -> None:
        self.item.place(self.start + (self.end - self.start) * self.rate_func(alpha))


class Moved(Animation):
    """Marks a part another animation moves, so Manim redraws it on every frame."""

    def interpolate_mobject(self, alpha: float) -> None:
        pass




class ChainedTargets:
    """A maths scene's targets, each with its own entrance and the targets it needs on screen
    first (title, axes, its function...): an entrance brings that chain, each part once, so a
    ``reveal`` action on an item draws what it stands on too. ``revealed``: the target names a
    ``reveal`` action shows (the scene leaves them to it)."""

    def __init__(self, scene: NarratedScene) -> None:
        self.scene = scene
        self.own: dict[int, Callable[[], list[Animation]]] = {}
        self.needs: dict[int, list[Target]] = {}
        names = type(scene).target_names(scene.params)
        self.revealed = {name for action in scene.action_uses("reveal") for pattern in action.config.targets() for name in names if fnmatchcase(name, pattern)}

    def bring(self, chain: Sequence[Target]) -> list[Animation]:
        """The entrances of the targets in ``chain`` not on screen yet, in order."""
        return [a for t in dict.fromkeys(chain) if not self.scene.is_shown(t) for a in self.own[id(t)]()]

    def add(self, names: str | list[str], mobject: Mobject, own: Callable[[], list[Animation]], before: list[Target]) -> Target:
        """Register a target with its own entrance ``own`` and the targets ``before`` it needs."""
        target = self.scene.target(names, mobject, entrance=lambda: self.bring([*self.needs[id(target)], target]))
        self.own[id(target)], self.needs[id(target)] = own, before
        return target

    def reveal(self, base: list[Target], items: list[Target], at_once: bool) -> None:
        """The scene's steps: ``base`` with the first item, then one item per beat (``at_once``:
        all in the first beat). An item a ``reveal`` action shows keeps its slot, empty, so the
        others keep their beats."""
        slots = [[] if self.revealed.intersection(t.names) else [t] for t in items]

        def step(targets: list[Target]) -> Callable[[], list[Animation]]:
            return lambda: self.bring([*base, *(d for t in targets for d in [*self.needs[id(t)], t])])

        steps = [step([t for own in slots for t in own])] if at_once else [step(own) for own in slots]
        self.scene.reveal(steps or [step([])], fraction=0.8, cap=2.0)


@action("trace")
class Trace(Action):
    """Moves what a maths scene draws: on a function_plot a dot (dot<N>) along its curve to
    x = `to` (its value label, guides and tangent following), an area's right end (area<N>) to
    `to`, a point (point<N>) to [x, y] = `to`, a vector's tip (vector<N>) to `to` or the vector
    scaled by `scale`; on a number_line a point to `to`; on a line_chart a cursor dot along a
    series (series<N>) to x = `to` (on categories, the position from 1), with the line's value.
    Everything drawn from them follows.
    `until: <beat>` moves it back."""

    class Options(ActionOptions):
        to: float | tuple[float, float] | None = None
        """Where it ends: an x for a dot, an area or a number line's point; [x, y] for a point or a vector's tip."""
        scale: float | None = None
        """A vector only, instead of to: multiply it by this (2: twice as long, -1: turned round); its tail stays."""

        @model_validator(mode="after")
        def _one(self) -> "Trace.Options":
            if (self.to is None) == (self.scale is None):
                raise ValueError("trace needs to (where it ends) or, for a vector, scale (e.g. {trace: vector1, scale: 2})")
            if self.scale is not None and self.scale == 0:
                raise ValueError("scale 0 would leave no vector; use a number such as 0.5 or -1")
            return self

    run_time = 2.0
    reversible = True

    def __init__(self, options: ActionOptions, config: Any) -> None:
        super().__init__(options, config)
        self.saved: list[tuple[Traced, Any]] = []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """The scene's own checks (``trace_problem``) of each target it moves."""
        trace_problem = getattr(scene_cls, "trace_problem", None)
        if trace_problem is None:
            return [("target", "trace moves the dots, areas, points and vectors of a function_plot, the points of a number_line or a cursor along a line_chart series")]
        names = scene_cls.target_names(params)
        matched = [n for pattern in self.config.targets() for n in names if fnmatchcase(n, pattern)]
        problems: list[tuple[str, str]] = []
        for name in dict.fromkeys(matched):
            found = trace_problem(params, name, self.options)
            if found:
                problems.append(found)
        return problems

    def _moves(self, scene: NarratedScene, item: Traced, end: Any) -> list[Animation]:
        moving = TraceMove(item, item.state, end, rate_func=smooth)
        shown = [m for m in item.parts if scene.on_screen_parts(m) and m is not moving.mobject]
        return [moving, *[Moved(m) for m in shown]]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Each item moves to ``to`` (or a vector is scaled)."""
        anims: list[Animation] = []
        for target in targets:
            item = scene.traced_item(target)
            if item is None:
                continue
            self.saved.append((item, item.state))
            goal = item.goal(self.options.to, self.options.scale) if hasattr(item, "goal") else self.options.to
            anims += self._moves(scene, item, goal)
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to where they were."""
        saved, self.saved = self.saved, []
        return [a for item, state in saved for a in self._moves(scene, item, state)]
