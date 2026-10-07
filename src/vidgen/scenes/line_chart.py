"""``line_chart``: one or more series drawn over shared x values, with end-value labels.

Axes, ticks and labels are plain ``Text`` (Manim's ``Axes`` number labels need LaTeX).
"""

from typing import Any, Literal

import numpy as np

from vidgen.api import *


class Series(SceneParams):
    """One line: ``name``, ``values`` (one per x) and an optional ``color``."""

    name: TranslatableStr
    """Series name (end label / legend)."""
    values: list[float]
    """One value per x."""
    color: ThemeColor | None = None
    """Line color; default: the theme.palette color at the series' position."""


@scene("line_chart")
class LineChart(NarratedScene):
    """``reveal: per_beat`` (default): series *i* is drawn at beat *i* (the axes appear with the
    first one; spread evenly when there are more series than beats). ``all``: every series is
    drawn in the first beat. Each series ends with a ``name value`` label.

    Action targets: ``title``, ``axes``, ``series<N>`` (1-based), ``series:<name>`` (a line with
    its markers and end label) and ``point:<name>@<x>`` (one data point, e.g. ``point:sparse@8``;
    ``x`` as its tick label reads).
    """

    outro = 0.5
    target_patterns = ("title", "axes", "series<N>", "series:<name>", "point:<name>@<x>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``axes``, then per series ``series<N>``, ``series:<name>`` and its
        ``point:<name>@<x>``."""
        names = (["title"] if params.title else []) + ["axes"]
        xs = cls.x_texts(params)
        for i, s in enumerate(params.series_list(), start=1):
            names += [f"series{i}", f"series:{s.name}"] + [f"point:{s.name}@{x}" for x in xs]
        return names

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
            for s in self.series_list():
                if len(s.values) != len(self.x):
                    raise ValueError(f"series {s.name!r} has {len(s.values)} values but x has {len(self.x)}")
            numeric = [v for v in self.x if not isinstance(v, str)]
            if numeric and any(b <= a for a, b in zip(numeric, numeric[1:])):
                raise ValueError("numeric x values must be strictly increasing")
            if self.y_min is not None and self.y_max is not None and self.y_max <= self.y_min:
                raise ValueError("y_max must be greater than y_min")
            return self

        def series_list(self) -> list[Series]:
            """The series as a list of :class:`Series` (a mapping becomes one per key)."""
            if isinstance(self.series, dict):
                return [Series(name=k, values=v) for k, v in self.series.items()]
            return list(self.series)

    def construct(self) -> None:
        p = self.params
        series = p.series_list()
        colors = [self.theme.color(s.color) if s.color else self.theme.palette_color(i) for i, s in enumerate(series)]
        fmt = p.value_format or auto_format([v for s in series for v in s.values])
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

        # end-of-line annotations (measured first: they decide the right margin). When
        # "name value" labels would take more than a third of the width, the names move to a
        # legend and the line ends show only the values.
        notes: list[VGroup] = []
        show_legend = not p.annotate and len(series) > 1
        if p.annotate:
            notes = [
                VGroup(self.text(s.name, size=size, color=c), self._value(s, fmt, "text", size)).arrange(RIGHT, buff=0.15)
                for s, c in zip(series, colors)
            ]
            if max(n.width for n in notes) > body.width * 0.34:
                notes = [self._value(s, fmt, c, size) for s, c in zip(series, colors)]
                show_legend = True
        note_w = max((n.width for n in notes), default=0.0)

        values = [v for s in series for v in s.values]
        y_axis = value_axis(values, lo=p.y_min, hi=p.y_max, max_ticks=5 if self.is_portrait else 6, fmt=p.value_format, unit=p.unit, title=p.y_label)
        x_cats = all(isinstance(v, str) for v in p.x)
        xs = [float(i) for i in range(len(p.x))] if x_cats else [float(v) for v in p.x]
        x_axis = ChartAxis(xs[0], xs[-1], tuple(xs), tuple(self.x_texts(p)), title=p.x_label)
        right = note_w + 0.25 if notes else 0.1

        def layout(top: float = 0.0) -> ChartAxes:
            return chart_axes(body, x_axis, y_axis, size=size, right=right, top=top)

        axes = layout()
        if show_legend:
            lines_at = [sample_path([axes.point(xv, yv) for xv, yv in zip(xs, s.values)]) for s in series]
            legend, spot = auto_legend([(s.name, c, "line") for s, c in zip(series, colors)], axes.plot, np.vstack(lines_at), body.width, size=size)
            if spot is None:  # every corner has data: above the plot
                axes = layout(top=legend.height + 0.3)
                spot = np.array([body.center[0], body.y1 - legend.height / 2, 0.0])
            frame.add(legend.move_to(spot))
        pt = axes.point
        grid = axes.group

        show_dots = p.dots if p.dots is not None else len(xs) <= 12
        lines, ends, marks = [], [], []
        for s, c in zip(series, colors):
            points = [pt(xv, yv) for xv, yv in zip(xs, s.values)]
            line = VMobject(stroke_color=c, stroke_width=4).set_points_as_corners(points)
            # without dots, a point target is a dot of its own that appears when acted on
            marks.append([Dot(q, radius=0.05 if show_dots else 0.08, color=c) for q in points])
            lines.append(VGroup(line, VGroup(*marks[-1]) if show_dots else VGroup()))
            ends.append(points[-1])
        self._place_notes(notes, ends, axes.plot.y0, axes.plot.y1)

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
        for i, s in enumerate(series):
            group = VGroup(lines[i], notes[i]) if notes else lines[i]
            drawn.append(self.target([f"series{i + 1}", f"series:{s.name}"], group, entrance=lambda i=i: self.entrance(chart) + [draw(i)]))
            for j, x in enumerate(x_axis.labels):
                dot = marks[i][j]
                appear = (lambda i=i: self.entrance(drawn[i])) if show_dots else (lambda i=i, dot=dot: self.entrance(drawn[i]) + [FadeIn(dot, scale=0.5)])
                self.target(f"point:{s.name}@{x}", dot, entrance=appear)

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
        self.reveal(steps, fraction=0.8, cap=2.5)
        self.finish()

    def _value(self, s: Series, fmt: str, color: str, size: float) -> Text:
        """The bold last-value label of a series."""
        return self.text(format_value(s.values[-1], fmt, self.params.unit), size=size, color=color, weight=BOLD)

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
