"""``line_chart``: one or more series drawn over shared x values, with end-value labels; with
``changes`` the lines morph to new values between beats (the y axis rescaling when needed), and
the ``trace`` action sweeps a cursor dot along a line.

Axes, ticks and labels are plain ``Text`` (Manim's ``Axes`` number labels need LaTeX).
"""

from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .chart_changes import ChangingChart, keep_opacity, lerp, state_axes, swap_parts
from .math_axes import LiveLabel, Moved
from .pie import window


class Series(SceneParams):
    """One line: ``name``, ``values`` (one per x) and an optional ``color``."""

    name: TranslatableStr
    """Series name (end label / legend)."""
    values: list[float]
    """One value per x."""
    color: ThemeColor | None = None
    """Line color; default: the colour of the video's term the name is (terms:), else the theme.palette color at the series' position."""


@scene("line_chart")
class LineChart(ChangingChart, NarratedScene):
    """``reveal: per_beat`` (default): series *i* is drawn at beat *i* (the axes appear with the
    first one; spread evenly when there are more series than beats). ``all``: every series is
    drawn in the first beat. Each series ends with a ``name value`` label. Each of ``changes``
    is a step of its own: the lines morph to its values and the y axis rescales when they leave
    it or would look flat (``rescale``), or on a word with ``{reveal: change<N>, at: "@word"}``.
    ``{trace: series<N>, to: x}`` sweeps a cursor dot with the line's value along it.

    Action targets: ``title``, ``axes``, ``series<N>`` (1-based), ``series:<name>`` (a line with
    its markers and end label), ``point:<name>@<x>`` (one data point, e.g. ``point:sparse@8``;
    ``x`` as its tick label reads) and ``change<N>`` (the lines; revealing it plays change N).
    """

    outro = 0.5
    target_patterns = ("title", "axes", "series<N>", "series:<name>", "point:<name>@<x>", "change<N>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``axes``, then per series ``series<N>``, ``series:<name>`` and its
        ``point:<name>@<x>``, then ``change<N>`` per change."""
        names = (["title"] if params.title else []) + ["axes"]
        xs = cls.x_texts(params)
        for i, s in enumerate(params.series_list(), start=1):
            names += [f"series{i}", f"series:{s.name}"] + [f"point:{s.name}@{x}" for x in xs]
        return names + [f"change{k}" for k in range(1, len(params.changes) + 1)]

    @classmethod
    def reveal_steps(cls, params: Any) -> list[RevealStep]:
        """One step per series, rising or falling as its values do from first to last
        (``reveal: all``: one step, the first series), then one per change, rising or falling
        as the lines' last values do."""
        series = params.series_list()
        if params.reveal == "all":
            series = series[:1]
        steps = [RevealStep(f"series{i}", value_trend(s.values)) for i, s in enumerate(series, start=1)]
        ends = [sum(values[-1] for values in state) for state in params.states()]
        return steps + [RevealStep(f"change{k}", value_trend(ends[k - 1 : k + 1])) for k in range(1, len(ends))]

    @classmethod
    def trace_problem(cls, params: Any, name: str, options: Any) -> tuple[str, str] | None:
        """``trace`` sweeps a series' cursor to an x inside the chart."""
        if not name.startswith("series"):
            return ("target", f"{name}: trace sweeps a cursor along a line_chart series (series<N> or series:<name>)")
        if options.scale is not None:
            return ("scale", f"{name}: scale is for a function_plot's vector; sweep the cursor with to")
        if not isinstance(options.to, float):
            return ("to", f"{name}: to is where the cursor stops on the x axis, e.g. to: 4")
        if all(isinstance(v, str) for v in params.x):
            if not 1 <= options.to <= len(params.x):
                return ("to", f"{name}: the x values are categories, so to is a position from 1 to {len(params.x)} (to: 2 is {params.x[1]!r}), not {options.to:g}")
            return None
        lo, hi = float(params.x[0]), float(params.x[-1])
        if not lo - 1e-9 <= options.to <= hi + 1e-9:
            return ("to", f"{name}: {options.to:g} is outside the x values [{lo:g}, {hi:g}]")
        return None

    def traced_item(self, target: Target) -> Any:
        """The cursor of the series ``target`` is (made when first traced; ``None``: not a series)."""
        i = self._series_of.get(id(target))
        if i is None:
            return None
        if i not in self._cursors:
            self._cursors[i] = _Cursor(self, i)
        return self._cursors[i]

    @staticmethod
    def x_texts(params: Any) -> list[str]:
        """The x values as their tick labels read."""
        if all(isinstance(v, str) for v in params.x):
            return [str(v) for v in params.x]
        return [format_value(float(v), params.x_format) for v in params.x]

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Chart title (in the header band at the top)."""
        x: list[float] | list[TranslatableStr] = Field(min_length=2)
        """X values: increasing numbers, or category names."""
        series: dict[TranslatableStr, list[float]] | list[Series] = Field(min_length=1)
        """{name: [values]} or a list of {name, values, color}; one value per x."""
        x_label: TranslatableStr = ""
        """X axis label."""
        y_label: TranslatableStr = ""
        """Y axis label."""
        y_min: float | None = None
        """Lower end of the y axis; default: from the data."""
        y_max: float | None = None
        """Upper end of the y axis; default: from the data."""
        value_format: str | None = None
        """Python format for y ticks and end labels; default: automatic."""
        x_format: str = "{:g}"
        """Python format for numeric x tick labels."""
        unit: TranslatableStr = ""
        """Appended to y values."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: series i is drawn at beat i; all: every series in beat 1."""
        changes: list[dict[TextRef, list[float]] | list[float]] = Field(default_factory=list)
        """Values the lines change to, one entry per change: {series name: [values]} (series left out keep theirs) or, with one series, just [values]; change N plays in its own step after the series are drawn, or on a word with {reveal: changeN, at: '@word'}."""
        rescale: bool = True
        """At a change the y axis rescales when the new values leave it or span less than half of it (y_min / y_max stay fixed); false: one y axis covering every change."""
        annotate: bool = True
        """Label the end of each line with its name and value."""
        dots: bool | None = None
        """Markers at the data points; default: when there are at most 12 points."""
        caption: TranslatableStr = ""
        """Note under the chart (e.g. the data source)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption color."""
        title_size: ThemeSize = "heading"
        """Title size (1.3x in a portrait frame)."""
        title_color: ThemeColor = "text"
        """Title color."""
        label_size: ThemeSize = "caption"
        """Size of tick labels, axis labels, end labels and the legend (never below the readable minimum)."""

        @field_validator("value_format", "x_format")
        @classmethod
        def _format(cls, v: str | None) -> str | None:
            return None if v is None else check_format(v)

        @model_validator(mode="after")
        def _consistent(self) -> SceneParams:
            series = self.series_list()
            for s in series:
                if len(s.values) != len(self.x):
                    raise ValueError(f"series {s.name!r} has {len(s.values)} values but x has {len(self.x)}")
            names = [s.name for s in series]
            for k, change in enumerate(self.changes):
                if isinstance(change, list):
                    if len(series) > 1:
                        raise ValueError(f"changes[{k}] is a list of values, but the chart has {len(series)} series: write {{name: [values]}}, e.g. {{{names[0]}: [...]}}")
                    change = {names[0]: change}
                if not change:
                    raise ValueError(f"changes[{k}] is empty: give the new values of at least one series")
                for name, values in change.items():
                    if name not in names:
                        raise ValueError(f"changes[{k}]: {name!r} is not a series (series: {', '.join(names)})")
                    if len(values) != len(self.x):
                        raise ValueError(f"changes[{k}].{name} has {len(values)} values but x has {len(self.x)}")
            numeric = [v for v in self.x if not isinstance(v, str)]
            if numeric and any(b <= a for a, b in zip(numeric, numeric[1:])):
                raise ValueError("numeric x values must be strictly increasing")
            if self.y_min is not None and self.y_max is not None and self.y_max <= self.y_min:
                raise ValueError("y_max must be greater than y_min")
            return self

        def states(self) -> list[list[list[float]]]:
            """Every state's values, per series: the series', then each change's (a series a
            change leaves out keeps its values)."""
            series = self.series_list()
            states = [[list(s.values) for s in series]]
            for change in self.changes:
                given = {series[0].name: change} if isinstance(change, list) else change
                states.append([list(given.get(s.name, before)) for s, before in zip(series, states[-1])])
            return states

        def series_list(self) -> list[Series]:
            """The series as a list of :class:`Series` (a mapping becomes one per key)."""
            if isinstance(self.series, dict):
                return [Series(name=k, values=v) for k, v in self.series.items()]
            return list(self.series)

    @staticmethod
    def _term_color(name: str) -> str | None:
        """The colour of the video's term that is the series' whole name (one colour per
        concept), else ``None``: ``training loss`` and ``test loss`` keep their own colours."""
        text = name.strip()
        spans = term_spans(text, active_terms())
        return spans[0][2].color if len(spans) == 1 and spans[0][:2] == (0, len(text)) else None

    def construct(self) -> None:
        p = self.params
        series = p.series_list()
        states = p.states()
        colors = [self.theme.color(s.color) if s.color else self._term_color(s.name) or self.theme.palette_color(i) for i, s in enumerate(series)]
        fmt = p.value_format or auto_format([v for state in states for values in state for v in values])
        body = self.safe_area
        frame = VGroup()
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            frame.add(title)
            body = body.below(title, gap=0.45)
        if p.caption:
            cap = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            frame.add(cap)
            body = body.above(cap, gap=0.3)
        size = chart_label_size(p.label_size)
        self._colors, self._fmt, self._label_size = colors, fmt, size

        # end-of-line annotations, for every state (measured first: they decide the right
        # margin). When "name value" labels would take more than a third of the width, the
        # names move to a legend and the line ends show only the values.
        self._named = p.annotate
        show_legend = not p.annotate and len(series) > 1
        state_notes = [self._notes_for(state) for state in states]
        if p.annotate and max(n.width for notes in state_notes for n in notes) > body.width * 0.34:
            self._named, show_legend = False, True
            state_notes = [self._notes_for(state) for state in states]
        note_w = max((n.width for notes in state_notes for n in notes), default=0.0)

        x_cats = all(isinstance(v, str) for v in p.x)
        xs = [float(i) for i in range(len(p.x))] if x_cats else [float(v) for v in p.x]
        x_axis = ChartAxis(xs[0], xs[-1], tuple(xs), tuple(self.x_texts(p)), title=p.x_label)
        right = note_w + 0.25 if p.annotate else 0.1

        def y_axis(values: list[float]) -> ChartAxis:
            return value_axis(values, lo=p.y_min, hi=p.y_max, max_ticks=5 if self.is_portrait else 6, fmt=p.value_format, unit=p.unit, title=p.y_label)

        y_axes = state_axes([[v for values in state for v in values] for state in states], y_axis, p.rescale)
        distinct = list({id(a): a for a in y_axes}.values())
        # axes that replace each other share one plot: room for the widest tick labels of all
        tick_width = max(self.text(t, size=size).width for a in distinct for t in a.labels) if len(distinct) > 1 else 0.0

        def layout(top: float = 0.0) -> list[ChartAxes]:
            built = {id(a): chart_axes(body, x_axis, a, size=size, right=right, top=top, tick_width=tick_width) for a in distinct}
            return [built[id(a)] for a in y_axes]

        every_axes = layout()
        if show_legend:
            lines_at = [sample_path([ax.point(xv, yv) for xv, yv in zip(xs, values)]) for ax, state in zip(every_axes, states) for values in state]
            legend, spot = auto_legend([(s.name, c, "line") for s, c in zip(series, colors)], every_axes[0].plot, np.vstack(lines_at), body.width, size=size)
            if spot is None:  # every corner has data: above the plot
                every_axes = layout(top=legend.height + 0.3)
                spot = np.array([body.center[0], body.y1 - legend.height / 2, 0.0])
            frame.add(legend.move_to(spot))
        axes = every_axes[0]
        grid = axes.group
        plot = axes.plot
        self._xs, self._categories, self._plot, self._grid = xs, x_cats, plot, grid
        self._state_axes, self._axes_now = every_axes, axes
        # per state, per series: the frame points, and where the end label stands (its left, its y)
        self._points = [[np.array([ax.point(xv, yv) for xv, yv in zip(xs, values)]) for values in state] for ax, state in zip(every_axes, states)]
        self._spots = []
        for k, notes in enumerate(state_notes):
            self._place_notes(notes, [pts[-1] for pts in self._points[k]], plot.y0, plot.y1)
            self._spots.append([np.array([n.get_left()[0], n.get_center()[1]]) for n in notes])

        show_dots = p.dots if p.dots is not None else len(xs) <= 12
        lines, marks = [], []
        for points, c in zip(self._points[0], colors):
            line = VMobject(stroke_color=c, stroke_width=4).set_points_as_corners(points)
            # without dots, a point target is a dot of its own that appears when acted on
            marks.append([Dot(q, radius=0.05 if show_dots else 0.08, color=c) for q in points])
            lines.append(VGroup(line, VGroup(*marks[-1]) if show_dots else VGroup()))
        notes = state_notes[0]
        self._lines, self._marks, self._notes = lines, marks, notes
        self._now_points = [pts.copy() for pts in self._points[0]]
        self._now_values = [np.array(values, dtype=float) for values in states[0]]
        self._now_spots = [spot.copy() for spot in self._spots[0]] if notes else []
        self._cursors: dict[int, _Cursor] = {}

        def draw(i: int) -> Animation:
            parts = [Create(lines[i][0], rate_func=linear)]
            if len(lines[i][1]):
                parts.append(FadeIn(lines[i][1], lag_ratio=0.2))
            if notes:
                parts.append(FadeIn(notes[i], shift=RIGHT * 0.15))
            return AnimationGroup(*parts, lag_ratio=0.45)

        def intro() -> list[Animation]:
            return ([FadeIn(frame)] if len(frame) and not self.on_screen_parts(frame) else []) + ([FadeIn(grid)] if not self.on_screen_parts(grid) else [])

        chart = self.target("axes", grid, entrance=intro)
        if title is not None:
            self.target("title", title, entrance=intro)
        drawn = []
        self._series_of: dict[int, int] = {}
        for i, s in enumerate(series):
            group = VGroup(lines[i], notes[i]) if notes else lines[i]
            drawn.append(self.target([f"series{i + 1}", f"series:{s.name}"], group, entrance=lambda i=i: self.entrance(chart) + [draw(i)]))
            self._series_of[id(drawn[-1])] = i
            for j, x in enumerate(x_axis.labels):
                dot = marks[i][j]
                appear = (lambda i=i: self.entrance(drawn[i])) if show_dots else (lambda i=i, dot=dot: self.entrance(drawn[i]) + [FadeIn(dot, scale=0.5)])
                self.target(f"point:{s.name}@{x}", dot, entrance=appear)
        self._drawn = drawn
        self.setup_changes(len(p.changes), VGroup(grid, *[d.mobject for d in drawn]))

        def series_steps(indices: list[int]) -> list[Animation]:  # entrance(): never drawn twice
            hidden = [i for i in indices if not self.is_shown(drawn[i])]
            anims = [draw(i) for i in hidden]
            if len(anims) > 1:
                anims = [LaggedStart(*anims, lag_ratio=0.2)]
            return self.entrance(chart) + anims

        if p.reveal == "all":
            steps: list = [lambda: series_steps(list(range(len(series))))]
        else:
            steps = [(lambda i=i: series_steps([i])) for i in range(len(series))]
        self.reveal(steps + self.change_steps(), fraction=0.8, cap=2.5)
        self.finish()

    def _notes_for(self, state: list[list[float]]) -> list[Mobject]:
        """The end labels of every series at a state's values: ``name value``, or (names in a
        legend) the value in the series' colour; none without ``annotate``."""
        if not self.params.annotate:
            return []
        size, fmt = self._label_size, self._fmt
        series = self.params.series_list()
        if self._named:
            return [VGroup(self.text(s.name, size=size, color=c), self._value_text(values[-1], "text")).arrange(RIGHT, buff=0.15) for s, c, values in zip(series, self._colors, state)]
        return [self._value_text(values[-1], c) for c, values in zip(self._colors, state)]

    def _value_text(self, value: float, color: str) -> Text:
        """A bold value label of the end of a line."""
        return self.text(format_value(value, self._fmt, self.params.unit), size=self._label_size, color=color, weight=BOLD)

    def _set_series(self, i: int, points: np.ndarray, values: np.ndarray, spot: np.ndarray | None) -> None:
        """Series ``i`` drawn through ``points`` (frame), its end label saying the last of
        ``values`` with its left end and middle at ``spot``; a cursor on it follows."""
        self._now_points[i], self._now_values[i] = points, values
        self._lines[i][0].set_points_as_corners(points)
        for dot, q in zip(self._marks[i], points):
            dot.move_to(q)
        if self._notes and spot is not None:
            self._now_spots[i] = spot
            note = self._notes[i]
            text = note[1] if self._named else note
            new = self._value_text(float(values[-1]), "text" if self._named else self._colors[i])
            if new.original_text != text.original_text:
                text.become(keep_opacity(new, text))
                text.original_text = new.original_text  # become() keeps the old string (layout dump)
                if self._named:
                    note.arrange(RIGHT, buff=0.15)
            note.shift([spot[0] - note.get_left()[0], spot[1] - note.get_center()[1], 0])
        cursor = self._cursors.get(i)
        if cursor is not None:
            cursor.place(cursor.x)

    def play_change(self, old: int, new: int) -> list[Animation]:
        """Every line morphs to state ``new``'s values, its end label counting and sliding, a
        cursor on it riding along; the y axis rescales first if state ``new`` has another one.
        Series not on screen yet take their new shape at once."""
        values = self.params.states()[new]
        anims: list[Animation] = []
        for i in range(len(self._lines)):
            p0, p1 = self._now_points[i].copy(), self._points[new][i]
            v0, v1 = self._now_values[i].copy(), np.array(values[i], dtype=float)
            s0 = self._now_spots[i].copy() if self._notes else None
            s1 = self._spots[new][i] if self._notes else None
            if not self.is_shown(self._drawn[i]):
                self._set_series(i, p1, v1, s1)
                continue

            def move(m: Mobject, a: float, i: int = i, p0: Any = p0, p1: Any = p1, v0: Any = v0, v1: Any = v1, s0: Any = s0, s1: Any = s1) -> None:
                self._set_series(i, lerp(p0, p1, a), lerp(v0, v1, a), None if s0 is None else lerp(s0, s1, a))

            anims.append(UpdateFromAlphaFunc(self._lines[i][0], move))
            riders = [*self._marks[i], *([self._notes[i]] if self._notes else [])]
            riders += [self._cursors[i].driver] if i in self._cursors else []
            anims += [Moved(m) for m in riders if self.on_screen_parts(m)]
        goal = self._state_axes[new]
        if goal is not self._axes_now:
            anims = self._rescale(self._axes_now, goal, anims)
        return anims

    def _rescale(self, before: ChartAxes, after: ChartAxes, anims: list[Animation]) -> list[Animation]:
        """``anims`` with the y axis changing from ``before`` to ``after`` (one plot): each
        gridline and tick label slides to where its value lies on the new axis while it fades
        (in the first 60 % of the change), the new ones slide in from where theirs lay on the old
        one (in the last 60 %), so the two sets of ticks do not crowd each other."""
        plot = before.plot
        drop = [before.grid, *before.y_labels]
        add = [after.grid, *after.y_labels]
        self._axes_now = after
        if not self.on_screen_parts(self._grid):
            return swap_parts(self, self._grid, drop, add, anims)

        def moved(y: float, start: ChartAxes, goal: ChartAxes) -> float:
            value = start.y.lo + (y - plot.y0) / plot.height * (start.y.hi - start.y.lo)
            return min(max(goal.y_pos(value), plot.y0 - 0.3), plot.y1 + 0.3)

        out = [m.animate(rate_func=window(0.0, 0.6)).shift(UP * (moved(m.get_y(), before, after) - m.get_y())).set_opacity(0) for m in [*before.grid, *before.y_labels]]
        out += [FadeIn(m, shift=UP * (m.get_y() - moved(m.get_y(), after, before)), rate_func=window(0.4, 1.0)) for m in [*after.grid, *after.y_labels]]
        return swap_parts(self, self._grid, drop, add, out + anims)

    @staticmethod
    def _place_notes(notes: list[VGroup], ends: list[np.ndarray], low: float, high: float) -> None:
        """Put each note right of its line end, nudged apart vertically so none overlap."""
        if not notes:
            return
        order = sorted(range(len(notes)), key=lambda i: ends[i][1])
        ys = [ends[i][1] for i in order]
        gap = max(n.height for n in notes) + 0.16
        for k in range(1, len(ys)):
            ys[k] = max(ys[k], ys[k - 1] + gap)
        overflow = ys[-1] - high
        if overflow > 0:
            ys = [y - overflow for y in ys]
        for k in range(len(ys) - 2, -1, -1):
            ys[k] = min(ys[k], ys[k + 1] - gap)
        for k, i in enumerate(order):
            notes[i].move_to([ends[i][0] + 0.2 + notes[i].width / 2, max(ys[k], low), 0])


class _Cursor:
    """A dot on series ``i`` of a line chart with the line's value above it, which the ``trace``
    action sweeps along the line (its ``state`` is its x; on categories, 0 is the first)."""

    def __init__(self, chart: LineChart, i: int) -> None:
        self.chart, self.i = chart, i
        self.dot = Dot(radius=0.1, color=chart._colors[i]).set_stroke(chart.theme.background, width=3).set_z_index(4)
        self.live = LiveLabel(chart, chart._label_size, 4)
        self.driver = VGroup(self.dot, self.live.group)
        self.x = chart._xs[0]
        self.place(self.x)

    @property
    def state(self) -> float:
        """Where it is (what ``trace`` moves)."""
        return self.x

    @property
    def parts(self) -> list[Mobject]:
        """The dot with its label."""
        return [self.driver]

    def goal(self, to: float, scale: float | None) -> float:
        """The x a ``trace`` ``to`` means (on categories, ``to`` counts from 1)."""
        return to - 1 if self.chart._categories else to

    def place(self, x: float) -> None:
        """Put the dot on the line at ``x`` and write the line's value there (between two
        points, the straight line's) above it, or under it at the top of the plot."""
        chart = self.chart
        self.x = float(x)
        points, values = chart._now_points[self.i], chart._now_values[self.i]
        fx = float(np.interp(self.x, chart._xs, points[:, 0]))
        fy = float(np.interp(self.x, chart._xs, points[:, 1]))
        self.dot.move_to([fx, fy, 0])
        self.live.show(format_value(float(np.interp(self.x, chart._xs, values)), chart._fmt, chart.params.unit))
        label = self.live.group
        y = fy + 0.22 + label.height / 2
        if y + label.height / 2 > chart._plot.y1 + 0.1:
            y = fy - 0.22 - label.height / 2
        area = chart.safe_area
        label.move_to([min(max(fx, area.x0 + label.width / 2), area.x1 - label.width / 2), y, 0])
