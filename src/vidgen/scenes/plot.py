"""``plot``: scientific line and scatter plots on the chart core (Phase W, DESIGN §97): data
inline or from a CSV in the project (units read from the headers), linear / log / symlog /
reversed / broken axes, scientific notation and SI prefixes, units in the axis titles,
gridlines, a legend, several panels sharing an axis, an equal aspect for trajectories."""

import math
from dataclasses import replace
from typing import Any, Literal

import numpy as np

from vidgen.api import *

#: Point marker radius (Manim units) by the number of points drawn (as ``scatter``).
_RADII = ((20, 0.1), (60, 0.08), (150, 0.06), (600, 0.045))
#: Data files a plot reads.
DATA_SUFFIXES = (".csv", ".tsv", ".txt")


class PlotAxis(SceneParams):
    """An axis: ``{label, unit, scale, min, max, reversed, format, linthresh, breaks}``."""

    label: TranslatableStr = ""
    """Axis title (the unit is added in parentheses); default: the name of the first series' data column."""
    unit: str = ""
    """Unit, shown as 'label (unit)'; default: the unit in the first series' column header, e.g. 'time (s)'."""
    scale: Literal["linear", "log", "symlog"] = "linear"
    """linear; log (base 10, positive values; ticks at powers of ten with 2-9 minor ticks); symlog (linear near 0, logarithmic beyond ±linthresh: data across zero spanning decades)."""
    min: float | None = None
    """Lower end of the axis; default: from the data, rounded out to a tick."""
    max: float | None = None
    """Upper end of the axis; default: from the data."""
    reversed: bool = False
    """Run the axis from high to low (e.g. magnitudes in astronomy, depth)."""
    format: str = "auto"
    """Tick labels: auto (plain numbers, or a power of ten moved into the title: 'distance (10⁶ km)'), plain, sci (2.5 × 10⁻³ on every tick), si (an SI prefix on the unit: 'time (ms)'; on a log axis each tick: '10 kHz'; needs a base unit such as s, m, Hz, eV), or a pattern such as '{:.1f}'."""
    linthresh: float | None = Field(default=None, gt=0)
    """symlog: the range ±linthresh drawn linearly; default: from the data."""
    breaks: list[tuple[float, float]] = Field(default_factory=list)
    """Value ranges cut out of a linear axis, [[from, to], ...], drawn with // marks; data on both sides, none inside."""

    @field_validator("format")
    @classmethod
    def _format(cls, v: str) -> str:
        return plotcore.check_tick_format(v)

    def spec(self, label: str, unit: str, max_ticks: int = 6) -> Any:
        """The core's ``AxisSpec`` with the label and unit decided by the data."""
        return plotcore.AxisSpec(scale=self.scale, lo=self.min, hi=self.max, reversed=self.reversed, linthresh=self.linthresh,
                                 breaks=tuple(tuple(b) for b in self.breaks), format=self.format, unit=unit, label=label, max_ticks=max_ticks)


class PlotSeries(SceneParams):
    """A series: ``{name, x, y}`` (column names of the data file, or lists of numbers) or
    ``{name, points: [[x, y], ...]}``; ``style``, ``color``, ``marker``, ``dashed``, ``width``."""

    name: TranslatableStr = Field(min_length=1)
    """Series name (legend, targets series:<name>)."""
    x: str | list[float] | None = None
    """X values: a column of the data file (by name, e.g. 'time') or a list of numbers."""
    y: str | list[float] | None = None
    """Y values: a column of the data file or a list of numbers (null for a gap)."""
    points: list[tuple[float, float]] | None = None
    """Inline points [[x, y], ...] instead of x and y."""
    data: str | None = None
    """A CSV for this series (default: the plot's data)."""
    style: Literal["line", "points", "both"] = "line"
    """line (joined in data order), points (markers), or both."""
    color: ThemeColor | None = None
    """Colour; default: the theme palette colour at the series' position."""
    marker: Literal["auto", "circle", "square", "triangle", "diamond"] = "auto"
    """Marker shape of points; auto: by series position."""
    dashed: bool = False
    """Dashed line (e.g. a model next to measurements)."""
    width: float = Field(default=4.0, gt=0, le=12)
    """Line width (pixels at 1080p)."""

    @field_validator("y", mode="before")
    @classmethod
    def _gaps(cls, v: Any) -> Any:
        return [math.nan if item is None else item for item in v] if isinstance(v, list) else v

    @model_validator(mode="after")
    def _source(self) -> "PlotSeries":
        if self.points is not None:
            if self.x is not None or self.y is not None:
                raise ValueError(f"series '{self.name}': give points or x and y, not both")
            if not self.points:
                raise ValueError(f"series '{self.name}': points is empty")
        elif self.x is None or self.y is None:
            raise ValueError(f"series '{self.name}': give x and y (column names or lists) or points")
        elif isinstance(self.x, list) and isinstance(self.y, list) and len(self.x) != len(self.y):
            raise ValueError(f"series '{self.name}': x has {len(self.x)} values but y has {len(self.y)}")
        if self.data is not None and not self.data.lower().endswith(DATA_SUFFIXES):
            raise ValueError(f"series '{self.name}': data '{self.data}' is not a .csv or .tsv file")
        return self

    def columns(self) -> list[str]:
        """The data columns this series names."""
        return [v for v in (self.x, self.y) if isinstance(v, str)]


class PlotPanel(SceneParams):
    """A panel of a figure: ``{series, x?, y?, weight?}``."""

    series: list[PlotSeries] = Field(min_length=1)
    """The panel's series."""
    x: PlotAxis | None = None
    """Its x axis (arrange: columns, or share: false); default: the plot's x."""
    y: PlotAxis | None = None
    """Its y axis (arrange: rows, or share: false); default: the plot's y."""
    weight: float = Field(default=1.0, gt=0)
    """Its size relative to the other panels."""


class ResolvedSeries:
    """A series with its numbers and the units its columns carry."""

    def __init__(self, spec: PlotSeries, xs: list[float], ys: list[float], x_col: Any, y_col: Any) -> None:
        self.spec, self.xs, self.ys = spec, xs, ys
        self.x_col, self.y_col = x_col, y_col   # plotcore.Column or None (inline numbers)


class ResolvedPanel:
    """A panel's series and the axis specs decided from params and data."""

    def __init__(self, series: list[ResolvedSeries], x: Any, y: Any, weight: float) -> None:
        self.series, self.x, self.y, self.weight = series, x, y, weight


@scene("plot")
class Plot(NarratedScene):
    """Scientific plot: line and point series from inline numbers or a CSV, on linear, log,
    symlog, reversed or broken axes with units, in one panel or several sharing an axis.
    ``reveal: series`` (default): the axes with the first series, then one series per beat
    (lines grow left to right, points pop in); ``all``: everything in the first beat.

    Action targets: ``title``, ``axes`` (every panel's axes), ``panel<N>`` (with several
    panels), ``legend``, ``series<N>``, ``series:<name>``.
    """

    outro = 0.5
    target_patterns = ("title", "axes", "panel<N>", "legend", "series<N>", "series:<name>")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Plot title (in the header band at the top)."""
        data: str | None = None
        """A CSV (or TSV) in the project, e.g. assets/decay.csv: the first row names the columns, with units as 'time (s)' or 'E [MeV]'."""
        series: list[PlotSeries] | None = None
        """The series of a one-panel plot."""
        panels: list[PlotPanel] | None = None
        """Several panels instead of series, stacked (arrange: rows, sharing x) or side by side (columns, sharing y)."""
        x: PlotAxis = Field(default_factory=PlotAxis)
        """The x axis (shared by stacked panels)."""
        y: PlotAxis = Field(default_factory=PlotAxis)
        """The y axis (shared by panels side by side; else the default of each panel)."""
        arrange: Literal["rows", "columns"] = "rows"
        """Panels stacked top to bottom (rows) or side by side (columns)."""
        share: bool = True
        """Panels share the axis along which they are arranged (rows: x, columns: y); false: each its own."""
        aspect: Literal["auto", "equal"] = "auto"
        """equal: one unit is as long on x as on y (orbits, trajectories, geometry); one panel, linear axes."""
        grid: Literal["major", "both", "x", "y", "none"] = "major"
        """Gridlines: at the labelled ticks of both axes (major), also at a log axis' minor ticks (both), one axis, or none."""
        legend: bool | None = None
        """Legend of the series (in a free corner, else above); default: with more than one series in a panel."""
        reveal: Literal["series", "all"] = "series"
        """series: one series per beat; all: everything in beat 1."""
        point_radius: float | None = Field(default=None, gt=0, le=0.4)
        """Marker radius in Manim units; default: from the number of points."""
        label_size: ThemeSize = "caption"
        """Size of tick labels, axis titles and the legend (never below the readable minimum)."""
        caption: TranslatableStr = ""
        """Note under the plot (e.g. the data source)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption color."""
        title_size: ThemeSize = "heading"
        """Title size (1.3x in a portrait frame)."""
        title_color: ThemeColor = "text"
        """Title color."""

        @field_validator("data")
        @classmethod
        def _data(cls, v: str | None) -> str | None:
            if v is not None and not v.lower().endswith(DATA_SUFFIXES):
                raise ValueError(f"data '{v}' is not a .csv or .tsv file")
            return v

        @model_validator(mode="after")
        def _consistent(self) -> "Plot.Params":
            if (self.series is None) == (self.panels is None):
                raise ValueError("give series (one panel) or panels, not both" if self.series is not None else "give series (one panel) or panels")
            names = [s.name for s in self.all_series()]
            for i, name in enumerate(names):
                if name in names[:i]:
                    raise ValueError(f"series name '{name}' is used twice")
            if self.panels is not None and self.share:
                fixed = "x" if self.arrange == "rows" else "y"
                for k, panel in enumerate(self.panels, start=1):
                    if getattr(panel, fixed) is not None:
                        raise ValueError(f"panels[{k}].{fixed}: the panels share the {fixed} axis (arrange: {self.arrange}); "
                                         f"set it once as the plot's {fixed}, or share: false")
            if self.aspect == "equal":
                if self.panels is not None and len(self.panels) > 1:
                    raise ValueError("aspect: equal works on one panel")
                if self.x.scale != "linear" or self.y.scale != "linear" or self.x.breaks or self.y.breaks:
                    raise ValueError("aspect: equal needs linear x and y axes without breaks")
            for s in self.all_series():
                if s.columns() and s.data is None and self.data is None:
                    raise ValueError(f"series '{s.name}': x / y name columns ({', '.join(s.columns())}) but no data file is given (data: assets/file.csv)")
            if not self.files():
                try:
                    self.resolve(None)
                except VidgenError as error:
                    raise ValueError(str(error)) from None
            return self

        def all_series(self) -> list[PlotSeries]:
            """Every series of every panel, in order."""
            return list(self.series) if self.series is not None else [s for p in self.panels or [] for s in p.series]

        def files(self) -> list[str]:
            """The data files this plot reads."""
            used = {s.data or self.data for s in self.all_series() if s.columns()}
            return sorted(f for f in used if f)

        def resolve(self, project: Any = None) -> list[ResolvedPanel]:
            """The panels with their numbers (read from the data files of ``project``, default
            the current one) and axis specs; raises ``VidgenError`` for unknown columns, unit
            mismatches and data an axis cannot show."""
            tables: dict[str, Any] = {}
            for name in self.files():
                proj = project if project is not None else current_project()
                path = proj.asset(name)
                tables[name] = plotcore.read_table(path.read_text(encoding="utf-8"), name)
            panels = [PlotPanel(series=self.series)] if self.series is not None else list(self.panels or [])
            out = []
            for panel in panels:
                series = [self._numbers(s, tables) for s in panel.series]
                x_axis = (panel.x or self.x) if not (self.share and self.arrange == "rows") else self.x
                y_axis = (panel.y or self.y) if not (self.share and self.arrange == "columns") else self.y
                out.append(ResolvedPanel(series, x_axis, y_axis, panel.weight))
            share_x = self.share and self.arrange == "rows" and len(out) > 1
            share_y = self.share and self.arrange == "columns" and len(out) > 1
            specs_x = self._specs(out, "x", share_x)
            specs_y = self._specs(out, "y", share_y)
            for k, panel in enumerate(out):
                panel.x, panel.y = specs_x[k], specs_y[k]
            self._check_axes(out, share_x, share_y)
            return out

        def _numbers(self, s: PlotSeries, tables: dict[str, Any]) -> ResolvedSeries:
            if s.points is not None:
                return ResolvedSeries(s, [p[0] for p in s.points], [p[1] for p in s.points], None, None)
            table = tables.get(s.data or self.data or "")
            cols = []
            values = []
            for axis in ("x", "y"):
                v = getattr(s, axis)
                if isinstance(v, str):
                    col = table.column(v, f"series '{s.name}' {axis}")
                    cols.append(col)
                    values.append(list(col.values))
                else:
                    cols.append(None)
                    values.append([float(n) for n in v])
            if len(values[0]) != len(values[1]):
                raise VidgenError(f"series '{s.name}': x has {len(values[0])} values but y has {len(values[1])}")
            if any(math.isnan(v) for v in values[0]):
                raise VidgenError(f"series '{s.name}': x has a missing value (only y may have gaps)")
            return ResolvedSeries(s, values[0], values[1], cols[0], cols[1])

        def _specs(self, panels: list[ResolvedPanel], axis: str, shared: bool) -> list[Any]:
            """Each panel's ``AxisSpec`` on ``axis``: label and unit from the params, else from
            the first series' column; units of every column on the axis must agree."""
            groups = [panels] if shared else [[p] for p in panels]
            specs = []
            for group in groups:
                param: PlotAxis = getattr(group[0], axis)
                cols = [getattr(s, f"{axis}_col") for p in group for s in p.series]
                cols = [c for c in cols if c is not None]
                units = {c.unit for c in cols if c.unit}
                if param.unit and units - {param.unit}:
                    other = next(c for c in cols if c.unit and c.unit != param.unit)
                    raise VidgenError(f"{axis}: the axis is in {param.unit} but the column '{other.name}' is in {other.unit}; "
                                      f"convert the data or set {axis}.unit: {other.unit}")
                if len(units) > 1:
                    a, b = sorted(units)[:2]
                    raise VidgenError(f"{axis}: the series' columns are in different units ({a} and {b}); plot them on separate panels or convert one")
                unit = param.unit or (units.pop() if units else "")
                label = str(param.label) or (cols[0].name if cols else "")
                spec = param.spec(label, unit)
                specs += [spec] * len(group)
            return specs

        def _check_axes(self, panels: list[ResolvedPanel], share_x: bool, share_y: bool) -> None:
            for k, panel in enumerate(panels):
                for axis, shared in (("x", share_x), ("y", share_y)):
                    group = panels if shared else [panel]
                    values = [v for p in group for s in p.series for v in getattr(s, f"{axis}s")]
                    name = f"panels[{k + 1}].{axis}" if len(panels) > 1 and not shared else axis
                    problems = getattr(panel, axis).problems(values, name)
                    if problems:
                        raise VidgenError(problems[0])

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super().validate_project(params, project)
        if params.files():
            try:
                params.resolve(project)
            except VidgenError as error:
                return problems + [f"data: {error}"]
        return problems

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        names = (["title"] if params.title else []) + ["axes"]
        if params.panels is not None and len(params.panels) > 1:
            names += [f"panel{k}" for k in range(1, len(params.panels) + 1)]
        if any(cls._legend_panels(params)):
            names.append("legend")
        for i, s in enumerate(params.all_series(), start=1):
            names += [f"series{i}", f"series:{s.name}"]
        return names

    @staticmethod
    def _legend_panels(params: Any) -> list[bool]:
        """Per panel, whether it shows a legend: ``legend`` if given, else with several series,
        or (in a figure of several panels) when its one series is not already named by the
        panel's own axis title."""
        panels = [PlotPanel(series=params.series)] if params.series is not None else list(params.panels)
        if params.legend is not None:
            return [params.legend] * len(panels)
        own = "y" if params.arrange == "rows" else "x"
        out = []
        for panel in panels:
            if len(panel.series) > 1:
                out.append(True)
                continue
            if len(panels) == 1:
                out.append(False)
                continue
            s = panel.series[0]
            axis = getattr(panel, own) or getattr(params, own)
            column = getattr(s, own)
            label = str(axis.label) or (plotcore.split_header(column)[0] if isinstance(column, str) else "")
            out.append(str(s.name).strip().lower() != label.strip().lower())
        return out

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        problems = type(self).validate_project(p, self.project)
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        panels = p.resolve(self.project)
        portrait = self.is_portrait
        for panel in panels:
            panel.x = replace(panel.x, max_ticks=4 if portrait else 7)
            panel.y = replace(panel.y, max_ticks=7 if portrait else 6)
            if p.aspect == "equal":
                panel.x = replace(panel.x, exact=True, margin=0.06)
                panel.y = replace(panel.y, exact=True, margin=0.06)
        body = self.safe_area
        frame: list[Mobject] = []
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            frame.append(title)
            body = body.below(title, gap=0.45)
        if p.caption:
            cap = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            frame.append(cap)
            body = body.above(cap, gap=0.3)
        size = chart_label_size(p.label_size)
        measure = plot_draw.text_measure(size, self.theme)
        series = [s for panel in panels for s in panel.series]
        colors = [self.theme.color(s.spec.color) if s.spec.color else self.theme.palette_color(i) for i, s in enumerate(series)]
        marked = [s for s in series if s.spec.style != "line"]   # auto markers go by position among the series with markers
        shapes = [s.spec.marker if s.spec.marker != "auto" else CHART_MARKERS[marked.index(s) % len(CHART_MARKERS)] if s in marked else "circle" for s in series]
        count = sum(len(s.xs) for s in series if s.spec.style != "line")
        radius = p.point_radius or next((r for n, r in _RADII if count <= n), 0.035)
        area = plotcore.Rect(body.x0, body.y0, body.x1, body.y1)
        inputs = [plotcore.PanelInput(tuple(v for s in panel.series for v in s.xs), tuple(v for s in panel.series for v in s.ys), panel.x, panel.y) for panel in panels]

        def layout(top: float = 0.0) -> list[Any]:
            try:
                return plotcore.layout_figure(area, inputs, measure, arrange=p.arrange, share=p.share, top=top, aspect=p.aspect,
                                              weights=[panel.weight for panel in panels], gap=0.5 if p.arrange == "columns" else 0.4)
            except VidgenError as error:
                raise VidgenError(f"scene '{self.spec.id}': {error}") from None

        lays = layout()
        index = {id(s): i for i, s in enumerate(series)}
        legend_entries = [[(str(s.spec.name), colors[index[id(s)]], self._swatch(s.spec, shapes[index[id(s)]])) for s in panel.series] for panel in panels]
        legend_entries = [ents if wanted else [] for ents, wanted in zip(legend_entries, self._legend_panels(p))]
        legends: list[Mobject] = []
        if any(legend_entries):
            legends, top = self._legends(lays, panels, legend_entries, body, size)
            if top:
                lays = layout(top=top)
                legends, _ = self._legends(lays, panels, legend_entries, body, size, above=True)
            frame += legends
        drawn = [plot_draw.draw_panel(lay, size=size, grid=p.grid, theme=self.theme) for lay in lays]
        parts: list[tuple[VGroup, VGroup]] = []   # per series: (line runs, markers)
        for panel, lay in zip(panels, lays):
            for s in panel.series:
                i = index[id(s)]
                pts = lay.frame_points(s.xs, s.ys)
                line = plot_draw.series_line(pts, lay.plot, colors[i], width=s.spec.width, dashed=s.spec.dashed) if s.spec.style != "points" else VGroup()
                dots = plot_draw.series_markers(pts, lay.plot, colors[i], marker=shapes[i], radius=radius, theme=self.theme) if s.spec.style != "line" else VGroup()
                parts.append((line, dots.set_z_index(2)))
        self.layouts, self.legends = lays, legends   # the panels' plotcore layouts and the legends drawn
        self._steps(title, frame, legends, drawn, parts, series)

    @staticmethod
    def _swatch(spec: PlotSeries, shape: str) -> str:
        return shape if spec.style == "points" else "line"

    def _legends(self, lays: list[Any], panels: list[ResolvedPanel], entries: list[list[Any]], body: Region, size: float,
                 above: bool = False) -> tuple[list[Mobject], float]:
        """One legend per panel with ``entries``, in a free corner of its plot; when a corner is
        missing, one legend of all those entries above the figure (``(legends, room it needs
        on top)``)."""
        if not above:
            out = []
            for panel, lay, ents in zip(panels, lays, entries):
                if not ents:
                    continue
                plot = Region(lay.plot.x0, lay.plot.y0, lay.plot.x1, lay.plot.y1)
                pts = [q for s in panel.series for q in self._sample(lay, s)]
                legend, spot = auto_legend(ents, plot, np.array(pts) if pts else np.zeros((0, 3)), body.width, size=size)
                if spot is None:
                    row = chart_legend([e for es in entries for e in es], body.width, size=size)
                    return [], row.height + 0.3
                out.append(legend)
            return out, 0.0
        row = chart_legend([e for es in entries for e in es], body.width, size=size)
        row.move_to([body.center[0], body.y1 - row.height / 2, 0])
        return [row], row.height + 0.3

    @staticmethod
    def _sample(lay: Any, s: ResolvedSeries) -> list[np.ndarray]:
        """Frame points a legend must keep clear of: the series' points and samples along its line."""
        pts = lay.frame_points(s.xs, s.ys)
        out = [q for q in pts if not np.isnan(q[:2]).any()]
        if s.spec.style != "points":
            for run in plotcore.clip_polyline(pts, lay.plot):
                out.extend(sample_path(list(run)))
        return out

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, title: Mobject | None, frame: list[Mobject], legends: list[Mobject], drawn: list[Any], parts: list[tuple[VGroup, VGroup]],
               series: list[ResolvedSeries]) -> None:
        p = self.params
        series_mobs = [VGroup(line, dots) for line, dots in parts]
        pieces = [m for m in frame if not any(m is lg for lg in legends)]
        axes_group = VGroup(*[d.group for d in drawn])

        def show_panel(d: Any) -> list[Animation]:
            if self.on_screen_parts(d.group):
                return []
            rest = VGroup(*[m for m in d.group if m is not d.lines])
            return [Create(d.lines), FadeIn(rest)]

        def intro() -> list[Animation]:
            anims = [FadeIn(m) for m in pieces if not self.on_screen_parts(m)]
            for d in drawn:
                anims += show_panel(d)
            anims += [FadeIn(lg) for lg in legends if not self.on_screen_parts(lg)]
            return anims

        chart = self.target("axes", axes_group, entrance=intro)
        if title is not None:
            self.target("title", title, entrance=intro)
        if len(drawn) > 1:
            for k, d in enumerate(drawn, start=1):
                self.target(f"panel{k}", d.group, entrance=lambda d=d: show_panel(d))
        if legends:
            self.target("legend", VGroup(*legends), entrance=lambda: [FadeIn(lg) for lg in legends if not self.on_screen_parts(lg)])

        def grow(k: int) -> list[Animation]:
            """Lines draw from their first point; markers pop in (in data order)."""
            line, dots = parts[k]
            anims: list[Animation] = [Create(run, rate_func=linear) for run in line]
            if len(dots):
                anims.append(LaggedStart(*[GrowFromCenter(m) for m in dots], lag_ratio=min(0.25, 2.0 / len(dots))))
            return [AnimationGroup(*anims, lag_ratio=0.35)] if len(anims) > 1 else anims

        targets = []
        for k, (s, mob) in enumerate(zip(series, series_mobs)):
            targets.append(self.target([f"series{k + 1}", f"series:{s.spec.name}"], mob, entrance=lambda k=k: self.entrance(chart) + grow(k)))

        def reveal(indices: list[int]) -> list[Animation]:
            anims = [a for k in indices if not self.is_shown(targets[k]) for a in grow(k)]
            if len(anims) > 1:
                anims = [LaggedStart(*anims, lag_ratio=0.2)]
            return self.entrance(chart) + anims

        if p.reveal == "all":
            steps: list[Any] = [lambda: reveal(list(range(len(series))))]
        else:
            steps = [(lambda k=k: reveal([k])) for k in range(len(series))]
        self.reveal(steps, fraction=0.8, cap=2.5)
        self.finish()
