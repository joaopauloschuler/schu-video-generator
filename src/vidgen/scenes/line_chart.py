"""``line_chart``: one or more series drawn over shared x values, with end-value labels.

Axes, ticks and labels are plain ``Text`` (Manim's ``Axes`` number labels need LaTeX).
"""

from typing import Literal

import numpy as np

from vidgen.api import *


class Series(SceneParams):
    """One line: ``name``, ``values`` (one per x) and an optional ``color``."""

    name: str
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
    """

    outro = 0.5

    class Params(SceneParams):
        title: str = ""
        """Chart title."""
        x: list[float] | list[str] = Field(min_length=2)
        """X values: increasing numbers, or category names."""
        series: dict[str, list[float]] | list[Series] = Field(min_length=1)
        """{name: [values]} or a list of {name, values, color}; one value per x."""
        x_label: str = ""
        """X axis label."""
        y_label: str = ""
        """Y axis label."""
        y_min: float | None = None
        """Lower end of the y axis; default: from the data."""
        y_max: float | None = None
        """Upper end of the y axis; default: from the data."""
        value_format: str | None = None
        """Python format for y ticks and end labels; default: automatic."""
        x_format: str = "{:g}"
        """Python format for numeric x tick labels."""
        unit: str = ""
        """Appended to y values."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: series i is drawn at beat i; all: every series in beat 1."""
        annotate: bool = True
        """Label the end of each line with its name and value."""
        dots: bool | None = None
        """Markers at the data points; default: when there are at most 12 points."""
        caption: str = ""
        """Note under the chart (e.g. the data source)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption color."""

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
        top = self.frame_height / 2 - self.margin_y
        bottom = -self.frame_height / 2 + self.margin_y
        left, right = -self.safe_width / 2, self.safe_width / 2
        dim = self.theme.color("dim")

        frame = VGroup()
        if p.title:
            title = fit_text(p.title, self.safe_width, self.safe_height * 0.18, size="heading", weight=BOLD, font=self.theme.font_for("heading"))
            frame.add(title.move_to([0, top - title.height / 2, 0]))
            top = title.get_bottom()[1] - 0.4
        if p.caption:
            cap = fit_text(p.caption, self.safe_width, self.safe_height * 0.15, size=p.caption_size, color=p.caption_color)
            frame.add(cap.move_to([0, bottom + cap.height / 2, 0]))
            bottom = cap.get_top()[1] + 0.25
        if p.y_label:
            ylab = fit_text(p.y_label, self.safe_width * 0.6, size="small", color="dim", align="left")
            frame.add(ylab.move_to([left + ylab.width / 2, top - ylab.height / 2, 0]))
            top = ylab.get_bottom()[1] - 0.25
        if p.x_label:
            xlab = fit_text(p.x_label, self.safe_width * 0.8, size="small", color="dim")
            frame.add(xlab.move_to([0, bottom + xlab.height / 2, 0]))
            bottom = xlab.get_top()[1] + 0.15

        values = [v for s in series for v in s.values]
        y_lo = p.y_min if p.y_min is not None else min(values)
        y_hi = p.y_max if p.y_max is not None else max(values)
        ticks = nice_ticks(y_lo, y_hi, 5 if self.is_portrait else 6)
        if p.y_min is not None:
            ticks = [t for t in ticks if t >= p.y_min] or ticks
        if p.y_max is not None:
            ticks = [t for t in ticks if t <= p.y_max] or ticks
        y0 = min(ticks[0], y_lo)
        y1 = max(ticks[-1], y_hi)
        tick_labels = [self.text(format_value(t, fmt, p.unit), size="small", color="dim") for t in ticks]
        tick_w = max(t.width for t in tick_labels)

        # end-of-line annotations (measured first: they decide the right margin). When
        # "name value" labels would take more than a third of the width, the names move to a
        # legend above the plot and the line ends show only the values.
        notes: list[VGroup] = []
        show_legend = not p.annotate and len(series) > 1
        if p.annotate:
            notes = [
                VGroup(self.text(s.name, size="caption", color=c), self._value(s, fmt, "text")).arrange(RIGHT, buff=0.15)
                for s, c in zip(series, colors)
            ]
            if max(n.width for n in notes) > self.safe_width * 0.34:
                notes = [self._value(s, fmt, c) for s, c in zip(series, colors)]
                show_legend = True
        if show_legend:
            legend = self._legend(series, colors)
            legend.move_to([0, top - legend.height / 2, 0])
            frame.add(legend)
            top = legend.get_bottom()[1] - 0.3
        note_w = max((n.width for n in notes), default=0.0)

        x_cats = all(isinstance(v, str) for v in p.x)
        xs = list(range(len(p.x))) if x_cats else [float(v) for v in p.x]
        x_texts = [str(v) if x_cats else format_value(float(v), p.x_format) for v in p.x]
        probe = [self.text(t, size="small", color="dim") for t in x_texts]
        xlab_h = max(m.height for m in probe)

        plot_l = left + tick_w + 0.25
        plot_r = right - (note_w + 0.25 if notes else 0.1)
        plot_b = bottom + xlab_h + 0.2
        plot_t = top

        def pt(xv: float, yv: float) -> np.ndarray:
            fx = (xv - xs[0]) / ((xs[-1] - xs[0]) or 1.0)
            fy = (yv - y0) / ((y1 - y0) or 1.0)
            return np.array([plot_l + fx * (plot_r - plot_l), plot_b + fy * (plot_t - plot_b), 0.0])

        axes = VGroup(Line(pt(xs[0], y0), pt(xs[-1], y0), color=dim, stroke_width=2))
        for t, lab in zip(ticks, tick_labels):
            axes.add(lab.move_to(pt(xs[0], t) + LEFT * (0.18 + lab.width / 2)))
            if t != y0:
                axes.add(DashedLine(pt(xs[0], t), pt(xs[-1], t), color=dim, stroke_width=1, stroke_opacity=0.4, dash_length=0.08))
        max_labels = 4 if self.is_portrait else 7
        step = max(1, int(np.ceil(len(xs) / max_labels)))
        shown = list(range(0, len(xs), step))
        if len(xs) - 1 - shown[-1] >= max(2, 0.75 * step):
            shown.append(len(xs) - 1)
        for i in shown:
            axes.add(probe[i].move_to(pt(xs[i], y0) + DOWN * (0.18 + probe[i].height / 2)))

        show_dots = p.dots if p.dots is not None else len(xs) <= 12
        lines, ends = [], []
        for s, c in zip(series, colors):
            points = [pt(xv, yv) for xv, yv in zip(xs, s.values)]
            line = VMobject(stroke_color=c, stroke_width=4).set_points_as_corners(points)
            extra = VGroup(*[Dot(q, radius=0.05, color=c) for q in points]) if show_dots else VGroup()
            lines.append(VGroup(line, extra))
            ends.append(points[-1])
        self._place_notes(notes, ends, plot_b, plot_t)

        def draw(i: int) -> Animation:
            parts = [Create(lines[i][0], rate_func=linear)]
            if len(lines[i][1]):
                parts.append(FadeIn(lines[i][1], lag_ratio=0.2))
            if notes:
                parts.append(FadeIn(notes[i], shift=RIGHT * 0.15))
            return AnimationGroup(*parts, lag_ratio=0.45)

        intro = [FadeIn(frame), FadeIn(axes)] if len(frame) else [FadeIn(axes)]
        if p.reveal == "all":
            steps: list = [lambda: intro + [LaggedStart(*[draw(i) for i in range(len(series))], lag_ratio=0.2)]]
        else:
            steps = [lambda: intro + [draw(0)]] + [(lambda i=i: draw(i)) for i in range(1, len(series))]
        self.reveal(steps, fraction=0.8, cap=2.5)
        self.finish()

    def _value(self, s: Series, fmt: str, color: str) -> Text:
        """The bold last-value label of a series."""
        return self.text(format_value(s.values[-1], fmt, self.params.unit), size="caption", color=color, weight=BOLD)

    def _legend(self, series: list[Series], colors: list[str]) -> VGroup:
        """Color swatch + name per series, wrapped into rows that fit the safe width."""
        items = [
            VGroup(Line(ORIGIN, RIGHT * 0.35, color=c, stroke_width=4), self.text(s.name, size="caption", color="text")).arrange(RIGHT, buff=0.12)
            for s, c in zip(series, colors)
        ]
        rows, row, width = VGroup(), VGroup(), 0.0
        for item in items:
            if len(row) and width + 0.5 + item.width > self.safe_width:
                rows.add(row.arrange(RIGHT, buff=0.5))
                row, width = VGroup(), 0.0
            row.add(item)
            width += item.width + (0.5 if len(row) > 1 else 0)
        if len(row):
            rows.add(row.arrange(RIGHT, buff=0.5))
        return shrink_to_fit(rows.arrange(DOWN, buff=0.15), self.safe_width)

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
