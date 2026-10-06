"""``scatter``: points of one or more series on two numeric axes, with an optional trend line."""

from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .actions import dim_to

#: Point marker radius (Manim units) by the number of points drawn: (up to n points, radius).
_RADII = ((20, 0.11), (60, 0.085), (150, 0.065))


class ScatterPoint(SceneParams):
    """One point: ``[x, y]``, ``[x, y, label]`` or ``{x, y, label?, group?}``."""

    also_accepts = (list,)

    x: float
    """Horizontal value."""
    y: float
    """Vertical value."""
    label: str = ""
    """Name written beside the point (see show_labels); also names its target point:<series>@<label>."""
    group: str | int | None = None
    """Reveal group (reveal: groups): points of one group appear together, groups in order of first use."""

    @model_validator(mode="before")
    @classmethod
    def _from_list(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)):
            if len(data) not in (2, 3):
                raise ValueError(f"a point is [x, y] or [x, y, label], got {len(data)} values")
            return dict(zip(("x", "y", "label"), data))
        return data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """``[x, y]`` / ``[x, y, label]`` are points too (JSON Schema ``anyOf`` array | object)."""
        pair = {"type": "array", "prefixItems": [{"type": "number"}, {"type": "number"}, {"type": "string"}], "minItems": 2, "maxItems": 3}
        return {"anyOf": [pair, handler(core_schema)]}


class ScatterSeries(SceneParams):
    """One series: ``{name, points, color?, marker?}``."""

    name: str = Field(min_length=1)
    """Series name (legend, targets series:<name>)."""
    points: list[ScatterPoint] = Field(min_length=1)
    """The points: [x, y], [x, y, label] or {x, y, label, group}."""
    color: ThemeColor | None = None
    """Marker color; default: the theme.palette color at the series' position."""
    marker: Literal["auto", "circle", "square", "triangle", "diamond"] = "auto"
    """Marker shape; auto: circle, square, triangle, diamond by series position (tells series apart without colour)."""


@scene("scatter")
class Scatter(NarratedScene):
    """``reveal: series`` (default): series *i* appears at beat *i* (the axes with the first),
    its points popping in from left to right; ``groups``: the points of each ``group`` appear
    together, one group per beat; ``all``: every point in beat 1. A ``trend`` line adds a step
    (it grows from left to right, with its equation / R² if asked), and ``highlight`` a last
    one (the chosen points get a ring, the others dim).

    Action targets: ``title``, ``axes``, ``legend``, ``series<N>``, ``series:<name>``,
    ``point:<series>@<N>`` (1-based) and ``point:<series>@<label>``, ``trend`` and
    ``trend:<series>`` (``trend: each``).
    """

    outro = 0.5
    target_patterns = ("title", "axes", "legend", "series<N>", "series:<name>", "point:<series>@<N>", "point:<series>@<label>", "trend", "trend:<series>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title``, ``axes``, ``legend`` (those present), per series ``series<N>``,
        ``series:<name>`` and its points, then ``trend`` (and ``trend:<name>`` per series)."""
        names = (["title"] if params.title else []) + ["axes"] + (["legend"] if params.show_legend() else [])
        series = params.series_list()
        for i, s in enumerate(series, start=1):
            names += [f"series{i}", f"series:{s.name}"]
            for j, point in enumerate(s.points, start=1):
                names += [f"point:{s.name}@{n}" for n in Scatter.point_names(s, j, point)]
        if params.trend != "none":
            names.append("trend")
        if params.trend == "each":
            names += [f"trend:{s.name}" for s in series]
        return names

    @staticmethod
    def point_names(series: ScatterSeries, index: int, point: ScatterPoint) -> list[str]:
        """What follows ``point:<series>@`` for a point (1-based ``index``): its number, and its
        label unless the label is another point's number."""
        names = [str(index)]
        if point.label and not (point.label.isdigit() and 1 <= int(point.label) <= len(series.points)):
            names.append(point.label)
        return names

    class Params(SceneParams):
        series: dict[str, list[ScatterPoint]] | list[ScatterSeries] = Field(min_length=1)
        """{name: [points]} or a list of {name, points, color, marker}; a point is [x, y], [x, y, label] or {x, y, label, group}."""
        title: str = ""
        """Chart title (in the header band at the top)."""
        x_label: str = ""
        """X axis label."""
        y_label: str = ""
        """Y axis label."""
        x_min: float | None = None
        """Left end of the x axis; default: from the data (rounded out to a tick)."""
        x_max: float | None = None
        """Right end of the x axis; default: from the data."""
        y_min: float | None = None
        """Lower end of the y axis; default: from the data."""
        y_max: float | None = None
        """Upper end of the y axis; default: from the data."""
        x_log: bool = False
        """Logarithmic x axis (positive values only; ticks at powers of ten)."""
        y_log: bool = False
        """Logarithmic y axis."""
        x_format: str | None = None
        """Python format for x tick labels, e.g. '{:.1f}'; default: automatic (12k, 3.4M for large numbers)."""
        y_format: str | None = None
        """Python format for y tick labels; default: automatic."""
        x_unit: str = ""
        """Appended to x tick labels."""
        y_unit: str = ""
        """Appended to y tick labels."""
        trend: Literal["none", "each", "all"] = "none"
        """Least-squares trend line: none, one per series (each), or one through every point (all); drawn in a step of its own."""
        trend_label: Literal["none", "equation", "r2", "both"] = "none"
        """Text at the trend line: its equation (y = ax + b), R², or both."""
        trend_color: ThemeColor | None = None
        """Trend line color; default: the series color (each), text (all)."""
        reveal: Literal["series", "groups", "all"] = "series"
        """series: one series per beat; groups: the points of each group per beat (points without a group come first); all: everything in beat 1."""
        show_labels: Literal["all", "highlight", "none"] = "all"
        """Which point labels are written: every labelled point, only highlighted ones (in the highlight step), or none."""
        highlight: one_or_many(str) = Field(default_factory=list)
        """Points emphasised in a last step: '<series>@<N>' (1-based), '<series>@<label>' or a label; the others dim."""
        highlight_color: ThemeColor = "highlight"
        """Ring color of highlighted points."""
        legend: bool | None = None
        """Legend of the series (placed where it covers no points); default: with more than one series."""
        point_radius: float | None = Field(default=None, gt=0, le=0.4)
        """Marker radius in Manim units; default: from the number of points (0.11 to 0.05)."""
        label_size: ThemeSize = "caption"
        """Size of tick labels, axis labels, point labels, the legend and the trend text (never below the readable minimum)."""
        caption: str = ""
        """Note under the chart (e.g. the data source)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption color."""
        title_size: ThemeSize = "heading"
        """Title size (1.3x in a portrait frame)."""
        title_color: ThemeColor = "text"
        """Title color."""

        @field_validator("x_format", "y_format")
        @classmethod
        def _format(cls, v: str | None) -> str | None:
            return None if v is None else check_format(v)

        @model_validator(mode="after")
        def _consistent(self) -> SceneParams:
            series = self.series_list()
            names = [s.name for s in series]
            for i, name in enumerate(names):
                if name in names[:i]:
                    raise ValueError(f"series name {name!r} is used twice")
            for s in series:
                labels = [p.label for p in s.points if p.label]
                for k, label in enumerate(labels):
                    if label in labels[:k]:
                        raise ValueError(f"series {s.name!r}: point label {label!r} is used twice")
            for axis in ("x", "y"):
                lo, hi = getattr(self, f"{axis}_min"), getattr(self, f"{axis}_max")
                if lo is not None and hi is not None and hi <= lo:
                    raise ValueError(f"{axis}_max must be greater than {axis}_min")
                for s in series:
                    for j, p in enumerate(s.points, start=1):
                        v = getattr(p, axis)
                        if getattr(self, f"{axis}_log") and v <= 0:
                            raise ValueError(f"{axis}_log needs positive values; series {s.name!r} point {j} has {axis} = {v:g}")
                        if (lo is not None and v < lo) or (hi is not None and v > hi):
                            raise ValueError(f"series {s.name!r} point {j} ({axis} = {v:g}) lies outside {axis}_min..{axis}_max; widen them or drop the point")
                if getattr(self, f"{axis}_log") and lo is not None and lo <= 0:
                    raise ValueError(f"{axis}_log needs a positive {axis}_min")
            if self.trend != "none":
                if self.x_log or self.y_log:
                    raise ValueError("trend lines need linear axes (x_log and y_log false)")
                groups = series if self.trend == "each" else [ScatterSeries(name="all", points=[p for s in series for p in s.points])]
                for s in groups:
                    if len({p.x for p in s.points}) < 2:
                        raise ValueError(f"trend: {'series ' + repr(s.name) if self.trend == 'each' else 'the points'} need at least two different x values")
            elif self.trend_label != "none":
                raise ValueError("trend_label needs a trend (each or all)")
            if self.reveal == "groups" and all(p.group is None for s in series for p in s.points):
                raise ValueError("reveal: groups needs points with a group")
            for ref in self.highlight:
                self.point_ref(ref)
            return self

        def series_list(self) -> list[ScatterSeries]:
            """The series as a list of :class:`ScatterSeries` (a mapping becomes one per key)."""
            if isinstance(self.series, dict):
                return [ScatterSeries(name=k, points=v) for k, v in self.series.items()]
            return list(self.series)

        def show_legend(self) -> bool:
            """Whether a legend is drawn."""
            return self.legend if self.legend is not None else len(self.series) > 1

        def point_ref(self, ref: str) -> tuple[int, int]:
            """``(series index, point index)`` (0-based) of a highlight reference:
            ``<series>@<N>``, ``<series>@<label>`` or a label used once."""
            series = self.series_list()
            name, at, key = ref.rpartition("@")
            if at:
                for i, s in enumerate(series):
                    if s.name == name:
                        for j, p in enumerate(s.points):
                            if key in Scatter.point_names(s, j + 1, p):
                                return i, j
                        raise ValueError(f"highlight {ref!r}: series {name!r} has no point {key!r} (1..{len(s.points)} or a label)")
                raise ValueError(f"highlight {ref!r}: no series {name!r} (series: {', '.join(s.name for s in series)})")
            found = [(i, j) for i, s in enumerate(series) for j, p in enumerate(s.points) if p.label == ref]
            if len(found) == 1:
                return found[0]
            if found:
                raise ValueError(f"highlight {ref!r}: several series have a point labelled so; write '<series>@{ref}'")
            raise ValueError(f"highlight {ref!r} is not '<series>@<N>', '<series>@<label>' or a point label")

    #: Opacity of the other points when some are highlighted (as ``timeline``).
    dimmed_opacity = 0.35

    def construct(self) -> None:
        p = self.params
        series = p.series_list()
        self._series = series
        colors = [self.theme.color(s.color) if s.color else self.theme.palette_color(i) for i, s in enumerate(series)]
        shapes = [s.marker if s.marker != "auto" else CHART_MARKERS[i % len(CHART_MARKERS)] for i, s in enumerate(series)]
        body = self.safe_area
        frame: list[Mobject] = []
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color)
            frame.append(title)
            body = body.below(title, gap=0.45)
        if p.caption:
            cap = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            frame.append(cap)
            body = body.above(cap, gap=0.3)
        size = chart_label_size(p.label_size)

        points = [pt for s in series for pt in s.points]
        portrait = self.is_portrait
        x_axis = value_axis([q.x for q in points], lo=p.x_min, hi=p.x_max, max_ticks=4 if portrait else 7, log=p.x_log, fmt=p.x_format, unit=p.x_unit, title=p.x_label)
        y_axis = value_axis([q.y for q in points], lo=p.y_min, hi=p.y_max, max_ticks=8 if portrait else 6, log=p.y_log, fmt=p.y_format, unit=p.y_unit, title=p.y_label)

        def layout(top: float = 0.0) -> ChartAxes:
            return chart_axes(body, x_axis, y_axis, size=size, grid="both", lines="xy", top=top)

        axes = layout()
        fits = self._fits(series)
        legend = None
        if p.show_legend():
            entries = [(s.name, c, shape) for s, c, shape in zip(series, colors, shapes)]
            legend, spot = auto_legend(entries, axes.plot, self._data_points(axes, series, fits), body.width, size=size)
            if spot is None:  # every corner has points: above the plot
                axes = layout(top=legend.height + 0.3)
                legend.move_to([body.center[0], body.y1 - legend.height / 2, 0])
            frame.append(legend)
        self._axes = axes

        radius = p.point_radius or next((r for n, r in _RADII if len(points) <= n), 0.05)
        markers = [
            [
                chart_marker(shape, radius, c, fill_opacity=0.9).set_stroke(self.theme.background, width=1.2).set_z_index(2).move_to(axes.point(q.x, q.y))
                for q in s.points
            ]
            for s, c, shape in zip(series, colors, shapes)
        ]
        trends = self._trends(axes, fits, colors, size)
        taken = [m for row in markers for m in row]
        boxes: list[Mobject] = [legend] if legend is not None else []
        labels: list[list[Mobject | None]] = []
        highlighted = {p.point_ref(ref) for ref in p.highlight}
        for i, s in enumerate(series):
            row: list[Mobject | None] = []
            for j, q in enumerate(s.points):
                wanted = q.label and (p.show_labels == "all" or (p.show_labels == "highlight" and (i, j) in highlighted))
                if not wanted:
                    row.append(None)
                    continue
                label = self._halo(self.text(q.label, size=size, color="text"))
                self._place_label(label, markers[i][j], radius, taken, boxes, [t[0] for t in trends], axes.plot)
                boxes.append(label)
                row.append(label)
            labels.append(row)
        points_at = self._marker_points(axes)
        for line, label, _ in trends:
            if label is not None:
                self._place_trend_label(label, line, points_at, boxes, [t[0] for t in trends], axes.plot)
                boxes.append(label)
        self._markers, self._labels = markers, labels
        self._steps(title, frame, axes, legend, markers, labels, trends, radius, highlighted)

    # ----- geometry --------------------------------------------------------------------------

    def _fits(self, series: list[ScatterSeries]) -> list[tuple[LinearFit, float, float, int | None]]:
        """``(fit, x from, x to, series index or None)`` per trend line."""
        p = self.params
        if p.trend == "none":
            return []
        if p.trend == "all":
            pts = [q for s in series for q in s.points]
            return [(linear_fit([q.x for q in pts], [q.y for q in pts]), min(q.x for q in pts), max(q.x for q in pts), None)]
        return [(linear_fit([q.x for q in s.points], [q.y for q in s.points]), min(q.x for q in s.points), max(q.x for q in s.points), i) for i, s in enumerate(series)]

    def _trend_ends(self, axes: ChartAxes, fit: LinearFit, x0: float, x1: float) -> tuple[np.ndarray, np.ndarray]:
        """The trend line's end points over ``x0..x1``, cut where it leaves the y domain."""
        lo, hi = sorted((axes.y.lo, axes.y.hi))
        a, b = x0, x1
        if fit.slope != 0:
            xs = sorted(((lo - fit.intercept) / fit.slope, (hi - fit.intercept) / fit.slope))
            if max(a, xs[0]) < min(b, xs[1]):
                a, b = max(a, xs[0]), min(b, xs[1])
        return axes.point(a, min(max(fit(a), lo), hi)), axes.point(b, min(max(fit(b), lo), hi))

    def _data_points(self, axes: ChartAxes, series: list[ScatterSeries], fits: list) -> np.ndarray:
        """Frame points a legend must not cover: the markers and samples along trend lines."""
        pts = [axes.point(q.x, q.y) for s in series for q in s.points]
        for fit, x0, x1, _ in fits:
            pts.extend(sample_path(list(self._trend_ends(axes, fit, x0, x1))))
        return np.array(pts)

    def _trends(self, axes: ChartAxes, fits: list, colors: list[str], size: float) -> list[tuple[Line, Mobject | None, int | None]]:
        """``(line, label or None, series index or None)`` per trend line (labels not placed yet)."""
        p = self.params
        out = []
        for fit, x0, x1, index in fits:
            color = self.theme.color(p.trend_color) if p.trend_color else (colors[index] if index is not None else self.theme.color("text"))
            a, b = self._trend_ends(axes, fit, x0, x1)
            line = Line(a, b, color=color, stroke_width=3.5).set_z_index(1)   # under the markers and labels
            label = None
            if p.trend_label != "none":
                parts = ([fit.equation()] if p.trend_label in ("equation", "both") else []) + ([f"R² = {fit.r2:.2f}"] if p.trend_label in ("r2", "both") else [])
                label = self.text("   ".join(parts), size=size, color=color)
                if label.width > axes.plot.width * 0.9:
                    label = VGroup(*[self.text(t, size=size, color=color) for t in parts]).arrange(DOWN, buff=0.12, aligned_edge=LEFT)
                label = self._halo(label)
            out.append((line, label, index))
        return out

    def _halo(self, label: Mobject) -> Mobject:
        """A label drawn above lines and markers with an outline of the background colour, so
        a line passing close stays behind it."""
        return label.set_stroke(self.theme.background, width=5, background=True).set_z_index(3)

    def _marker_points(self, axes: ChartAxes) -> list[np.ndarray]:
        return [axes.point(q.x, q.y) for s in self._series for q in s.points]

    @staticmethod
    def _overlaps(a: Mobject, b: Mobject, air: float = 0.04) -> bool:
        return not (
            a.get_right()[0] + air <= b.get_left()[0] or b.get_right()[0] + air <= a.get_left()[0]
            or a.get_top()[1] + air <= b.get_bottom()[1] or b.get_top()[1] + air <= a.get_bottom()[1]
        )

    @staticmethod
    def _covers(label: Mobject, point: np.ndarray, r: float) -> bool:
        return (label.get_left()[0] - r < point[0] < label.get_right()[0] + r) and (label.get_bottom()[1] - r < point[1] < label.get_top()[1] + r)

    def _place_trend_label(self, label: Mobject, line: Line, points: list[np.ndarray], boxes: list[Mobject], lines: list[Line], plot: Region) -> None:
        """Near the trend line's right end (beside the end, then above or below it further
        along), where it crosses no trend line and covers the fewest points, labels and the
        legend, inside the plot."""
        start, end = line.get_start(), line.get_end()
        w, h, gap = label.width, label.height, 0.25
        rising = end[1] >= start[1]
        centres = [
            end + np.array([w / 2 + gap, -h / 2 - gap if rising else h / 2 + gap, 0.0]),   # past the end, away from the line
            end + np.array([-w / 2, h / 2 + gap, 0.0]),
            end + np.array([-w / 2, -h / 2 - gap, 0.0]),
        ]
        along = (end - start) / (np.linalg.norm(end - start) or 1.0)
        normal = np.array([-along[1], along[0], 0.0])
        reach = abs(normal[0]) * w / 2 + abs(normal[1]) * h / 2 + gap   # clear of the line, whatever its slope
        for share in (0.85, 0.7, 0.55, 0.4, 0.25, 0.1):
            anchor = start + (end - start) * share
            centres += [anchor + side * reach * normal for side in (1, -1)]
        best: tuple[float, np.ndarray] | None = None
        for centre in centres:
            centre = centre.copy()
            centre[0] = min(max(centre[0], plot.x0 + w / 2), plot.x1 - w / 2)
            centre[1] = min(max(centre[1], plot.y0 + h / 2), plot.y1 - h / 2)
            label.move_to(centre)
            score = 5 * sum(self._crosses(label, ln.get_start(), ln.get_end()) for ln in lines)
            score += sum(self._covers(label, q, 0.08) for q in points) + 3 * sum(self._overlaps(label, b) for b in boxes)
            if best is None or score < best[0]:
                best = (score, centre)
            if score == 0:
                return
        label.move_to(best[1])  # type: ignore[index]

    @staticmethod
    def _crosses(label: Mobject, a: np.ndarray, b: np.ndarray) -> bool:
        """Whether the segment ``a``-``b`` passes through the label's box (sampled)."""
        for t in np.linspace(0, 1, 40):
            q = a + (b - a) * t
            if label.get_left()[0] < q[0] < label.get_right()[0] and label.get_bottom()[1] < q[1] < label.get_top()[1]:
                return True
        return False

    def _place_label(self, label: Mobject, marker: Mobject, r: float, markers: list[Mobject], boxes: list[Mobject], lines: list[Line], plot: Region) -> None:
        """Next to its marker (right, left, above, below, then the diagonals), where it covers
        no other marker, label or trend line and stays inside the plot; else where it collides
        least."""
        at = marker.get_center()
        w, h = label.width, label.height
        gap = r + 0.08
        options = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)]
        best: tuple[float, np.ndarray] | None = None
        for dx, dy in options:
            centre = at + np.array([dx * (gap + w / 2), dy * (gap * 0.8 + h / 2), 0.0])
            label.move_to(centre)
            outside = not plot.contains(label, tolerance=0.02)
            score = 4 * outside + 2 * sum(self._overlaps(label, b) for b in boxes) + sum(m is not marker and self._overlaps(label, m, 0.02) for m in markers)
            score += 2 * sum(self._crosses(label, line.get_start(), line.get_end()) for line in lines)
            if best is None or score < best[0]:
                best = (score, centre)
            if score == 0:
                return
        label.move_to(best[1])  # type: ignore[index]

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, title, frame, axes, legend, markers, labels, trends, radius, highlighted) -> None:  # noqa: ANN001
        p = self.params
        series = self._series
        pieces = [m for m in frame if m is not legend]

        def intro() -> list[Animation]:
            anims = [FadeIn(m) for m in pieces if not self.on_screen_parts(m)]
            if not self.on_screen_parts(axes.lines):
                anims += [Create(axes.lines), FadeIn(VGroup(*[m for m in axes.group if m is not axes.lines]))]
            if legend is not None and not self.on_screen_parts(legend):
                anims.append(FadeIn(legend))
            return anims

        chart = self.target("axes", axes.group, entrance=intro)
        if title is not None:
            self.target("title", title, entrance=intro)
        if legend is not None:
            self.target("legend", legend, entrance=lambda: [FadeIn(legend)])

        def own(i: int, j: int) -> list[Animation]:
            anims: list[Animation] = [GrowFromCenter(markers[i][j])]
            if labels[i][j] is not None and p.show_labels == "all":
                anims.append(FadeIn(labels[i][j], shift=UP * 0.08))
            return [Succession(*anims)] if len(anims) > 1 else anims

        point_targets: dict[tuple[int, int], Any] = {}
        for i, s in enumerate(series):
            for j, q in enumerate(s.points):
                part = VGroup(markers[i][j], labels[i][j]) if labels[i][j] is not None and p.show_labels == "all" else markers[i][j]
                names = [f"point:{s.name}@{n}" for n in self.point_names(s, j + 1, q)]
                point_targets[i, j] = self.target(names, part, entrance=lambda i=i, j=j: self.entrance(chart) + own(i, j))
        self._points = point_targets

        def pop(keys: list[tuple[int, int]]) -> list[Animation]:
            """The chart (if not shown), then the hidden points, left to right."""
            hidden = sorted((k for k in keys if not self.is_shown(point_targets[k])), key=lambda k: (series[k[0]].points[k[1]].x, k))
            anims = [AnimationGroup(*own(*k)) for k in hidden]
            lag = min(0.25, 2.0 / max(len(anims), 1))
            return self.entrance(chart) + ([LaggedStart(*anims, lag_ratio=lag)] if anims else [])

        for i, s in enumerate(series):
            keys = [(i, j) for j in range(len(s.points))]
            self.target([f"series{i + 1}", f"series:{s.name}"], VGroup(*[point_targets[k].mobject for k in keys]), entrance=lambda keys=keys: pop(keys))

        trend_target = None
        if trends:
            def grow(items: list) -> list[Animation]:  # noqa: ANN001
                out: list[Animation] = []
                for line, label, _ in items:
                    if not self.on_screen_parts(line):
                        out.append(Create(line, rate_func=linear))
                    if label is not None and not self.on_screen_parts(label):
                        out.append(FadeIn(label))
                return self.entrance(chart) + ([Succession(*out)] if len(out) > 1 else out)

            parts = [m for line, label, _ in trends for m in (line, label) if m is not None]
            trend_target = self.target("trend", VGroup(*parts), entrance=lambda: grow(trends))
            if p.trend == "each":
                for item in trends:
                    line, label, index = item
                    group = VGroup(line, label) if label is not None else line
                    self.target(f"trend:{series[index].name}", group, entrance=lambda item=item: grow([item]))

        if p.reveal == "all":
            groups = [[(i, j) for i, s in enumerate(series) for j in range(len(s.points))]]
        elif p.reveal == "series":
            groups = [[(i, j) for j in range(len(s.points))] for i, s in enumerate(series)]
        else:
            order: list[Any] = []
            for s in series:
                for q in s.points:
                    if q.group is not None and q.group not in order:
                        order.append(q.group)
            first = [(i, j) for i, s in enumerate(series) for j, q in enumerate(s.points) if q.group is None]
            groups = [[(i, j) for i, s in enumerate(series) for j, q in enumerate(s.points) if q.group == g] for g in order]
            groups[0] = first + groups[0]
        steps: list[Any] = [(lambda keys=keys: pop(keys)) for keys in groups]
        if trend_target is not None:
            steps.append(lambda: self.entrance(trend_target))
        if highlighted:
            steps.append(lambda: self._focus(sorted(highlighted), radius))
        self.reveal(steps, fraction=0.8, cap=2.0)
        self.finish()

    def _focus(self, chosen: list[tuple[int, int]], radius: float) -> list[Animation]:
        """The highlight step: rings around the chosen points (their labels appear with
        ``show_labels: highlight``), every other point dims."""
        p = self.params
        color = self.theme.color(p.highlight_color)
        anims: list[Animation] = [
            dim_to(t, part, self.dimmed_opacity) for key, t in self._points.items() if key not in chosen for part in self.on_screen_parts(t)
        ]
        for i, j in chosen:
            marker = self._markers[i][j]
            if not self.on_screen_parts(self._points[i, j]):  # transformed away by an action
                continue
            ring = Circle(radius=radius * 1.9, color=color, stroke_width=3).set_z_index(2).move_to(marker.get_center())
            anims.append(Create(ring))
            label = self._labels[i][j]
            if label is not None and p.show_labels == "highlight":
                anims.append(FadeIn(label, shift=UP * 0.08))
        return anims
