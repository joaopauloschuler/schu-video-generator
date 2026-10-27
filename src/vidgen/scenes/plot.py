"""``plot``: scientific plots on the chart core (Phase W, DESIGN §97): line, point and histogram
series from inline numbers or a CSV in the project (units read from the headers) on linear /
log / symlog / reversed / broken axes with units, scientific notation and SI prefixes; error
bars, fitted curves with their parameters ± errors, confidence and prediction bands, residual
panels, distributions over histograms, and annotations tied to the data (labels, arrows,
reference lines, shaded ranges, notes) placed clear of the data and of each other; one panel
or several sharing an axis, an equal aspect for trajectories; data from models (ODEs,
recurrences, random processes, registered functions) growing live. The params and their
resolution are in ``plot_parts.py`` and ``plot_models.py``, the drawing helpers in
``plot_figure.py``, the live part in ``plot_live.py``; the actions ``fit``, ``annotate`` and
``grow`` in ``plot_actions.py``."""

import math
from dataclasses import replace
from fnmatch import fnmatchcase
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .plot_figure import TIGHT, PlotFigure
from .plot_live import LivePlot
from .plot_models import PlotModel
from .plot_parts import (
    DATA_SUFFIXES,
    PlotAnnotation,
    PlotAxis,
    PlotFit,
    PlotSeries,
    Resolved,
    ResolvedFit,
    ResolvedPanel,
    ResolvedSeries,
    error_arrays,
)

#: Point marker radius (Manim units) by the number of points drawn (as ``scatter``).
_RADII = ((20, 0.1), (60, 0.08), (150, 0.06), (600, 0.045))
#: Size of a residual panel relative to the panel it belongs to.
RESIDUAL_WEIGHT = 0.4
#: Actions whose targets a plot's own steps leave to them.
_TIMED = ("reveal", "fit", "annotate", "grow")


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


@scene("plot")
class Plot(LivePlot, PlotFigure, NarratedScene):
    """Scientific plot: line, point and histogram series from inline numbers or a CSV, on
    linear, log, symlog, reversed or broken axes with units, with error bars, fitted curves
    (parameters ± errors, R², bands, residual panels) and annotations, in one panel or several
    sharing an axis. ``reveal: series`` (default): the axes with the first series, then one
    series per beat (lines grow left to right, points pop in, bars rise), then each fit, then
    each annotation; ``all``: everything in the first beat. The actions ``fit`` and
    ``annotate`` (and ``reveal``) time a fit, an annotation, a series or its error bars to a word.

    Action targets: ``title``, ``axes`` (every panel's axes), ``panel<N>`` (with several
    panels), ``legend``, ``series<N>``, ``series:<name>``, ``errors:<name>`` (a series' error
    bars), ``fit<N>``, ``fit:<name>`` (the curve, band, parameter box and residual panel),
    ``annotation<N>``, ``annotation:<id>``.
    """

    outro = 0.5
    plot_actions = True
    mid_still_actions = frozenset({"grow", "zoom"})
    target_patterns = ("title", "axes", "panel<N>", "legend", "series<N>", "series:<name>", "errors:<name>", "fit<N>", "fit:<name>",
                       "annotation<N>", "annotation:<id>")

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
        """Legend of the series and fits (in a free corner, else above); default: with more than one series or a fit in a panel, or error bars with a meaning."""
        fits: list[PlotFit] = Field(default_factory=list)
        """Fitted curves: [{series, model, ...}], drawn with their parameters ± standard errors."""
        annotations: list[PlotAnnotation] = Field(default_factory=list)
        """Annotations tied to the data: [{type: label | arrow | hline | vline | xrange | yrange | note, text, ...}]."""
        reveal: Literal["series", "all"] = "series"
        """series: one series per beat, then the fits and annotations; all: everything in beat 1."""
        models: dict[str, PlotModel] = Field(default_factory=dict)
        """Models generating data, by name: {osc: {kind: ode, equations: {x: v, v: "-k*x"}, initial: {x: 1, v: 0}, params: {k: 4}, t: [0, 10]}}; series name their columns (x: t, y: x) and grow live."""
        rescale: bool = True
        """While live series grow, axes without fixed ends start around the first data and widen smoothly as the data reach their edge (a time axis is shown whole); false: the whole range from the start."""
        point_radius: float | None = Field(default=None, gt=0, le=0.4)
        """Marker radius in Manim units; default: from the number of points."""
        label_size: ThemeSize | None = None
        """Size of tick labels, axis titles, the legend, fit boxes and annotations (never below the readable minimum); default: body in a landscape frame, caption in a portrait one."""
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
            all_series = self.all_series()
            for name in self.models:
                if not name.isidentifier():
                    raise ValueError(f"models: '{name}' is not a name (letters, digits and _)")
            for s in all_series:
                if s.model is None and s.data is None and self.data is None and len(self.models) == 1 and s.columns():
                    s.model = next(iter(self.models))   # the plot's only model
                if s.model is not None and s.model not in self.models:
                    known = list(self.models)
                    raise ValueError(f"series '{s.name}': no model '{s.model}'" + (f"; models: {', '.join(known)}" if known else " (add it under models:)")
                                     + did_you_mean(s.model, known))
                problem = s.live_problem()
                if problem:
                    raise ValueError(problem)
            names = [str(s.name) for s in all_series]
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
            for s in all_series:
                if s.columns() and s.data is None and self.data is None and s.model is None:
                    hint = "; with several models, say which: model: <name>" if self.models else ""
                    raise ValueError(f"series '{s.name}': it names columns ({', '.join(s.columns())}) but no data file is given (data: assets/file.csv) "
                                     f"and no model{hint}")
            fit_names = []
            for k, f in enumerate(self.fits, start=1):
                if f.series not in names:
                    raise ValueError(f"fits[{k}]: no series '{f.series}'; series: {', '.join(names)}" + did_you_mean(f.series, names))
                target = all_series[names.index(f.series)]
                if f.kind in ("normal", "poisson") and not target.histogram:
                    raise ValueError(f"fits[{k}]: a {f.kind} distribution is fitted to a histogram (a series with values:); for a peak in x, y data use model: gaussian")
                if f.residuals and self.panels is not None and len(self.panels) > 1 and self.arrange == "columns":
                    raise ValueError(f"fits[{k}]: a residual panel goes under its plot; use arrange: rows")
                if f.residuals and self.aspect == "equal":
                    raise ValueError(f"fits[{k}]: residuals need aspect: auto")
                fit_names.append(f.label())
            for i, name in enumerate(fit_names):
                if name in fit_names[:i]:
                    raise ValueError(f"two fits are called '{name}'; give one a name")
            ids = [a.id for a in self.annotations if a.id]
            for i, a in enumerate(self.annotations, start=1):
                if a.series is not None and a.series not in names:
                    raise ValueError(f"annotations[{i}]: no series '{a.series}'; series: {', '.join(names)}" + did_you_mean(a.series, names))
                if a.panel is not None and a.panel > self.panel_count():
                    raise ValueError(f"annotations[{i}]: panel {a.panel}, but the plot has {self.panel_count()} panel{'s' if self.panel_count() > 1 else ''}")
                if a.id and ids.count(a.id) > 1:
                    raise ValueError(f"annotations: the id '{a.id}' is used twice")
            if not self.files():
                try:
                    self.resolve(None)
                except VidgenError as error:
                    raise ValueError(str(error)) from None
            return self

        def all_series(self) -> list[PlotSeries]:
            """Every series of every panel, in order."""
            return list(self.series) if self.series is not None else [s for p in self.panels or [] for s in p.series]

        def panel_list(self) -> list[PlotPanel]:
            """The panels (one for ``series``)."""
            return [PlotPanel(series=self.series)] if self.series is not None else list(self.panels or [])

        def panel_count(self) -> int:
            return 1 if self.series is not None else len(self.panels or [])

        def files(self) -> list[str]:
            """The data files this plot reads."""
            used = {s.data or self.data for s in self.all_series() if s.columns() and s.model is None}
            return sorted(f for f in used if f)

        def source(self, s: PlotSeries) -> str:
            """The key of the table a series reads: ``model:<name>`` or the data file."""
            return f"model:{s.model}" if s.model is not None else (s.data or self.data or "")

        def simulations(self) -> dict[str, Any]:
            """Each used model's :class:`plotcore.Simulation` (run once, cached)."""
            used = {s.model for s in self.all_series() if s.model is not None}
            return {name: m.run(name) for name, m in self.models.items() if name in used}

        def conservation(self) -> list[tuple[str, str, float]]:
            """``(model, quantity, relative drift)`` for every quantity a used model declares
            conserved (for lint: a drift above a few 10⁻³ means the method or step is wrong)."""
            return [(name, q, d) for name, sim in self.simulations().items() for q, d in sim.drift.items()]

        def resolve(self, project: Any = None) -> Resolved:
            """The panels with their numbers (read from the data files of ``project``, default
            the current one), axis specs and fits; raises ``VidgenError`` for unknown columns,
            unit mismatches, data an axis cannot show and fits that fail."""
            tables: dict[str, Any] = {}
            for name in self.files():
                proj = project if project is not None else current_project()
                path = proj.asset(name)
                tables[name] = plotcore.read_table(path.read_text(encoding="utf-8"), name)
            for name, sim in self.simulations().items():
                tables[f"model:{name}"] = sim.table()
            out = []
            for k, panel in enumerate(self.panel_list()):
                series = [self._numbers(s, tables) for s in panel.series]
                for s in series:
                    s.panel = k
                x_axis = (panel.x or self.x) if not (self.share and self.arrange == "rows") else self.x
                y_axis = (panel.y or self.y) if not (self.share and self.arrange == "columns") else self.y
                out.append(ResolvedPanel(series, x_axis, y_axis, panel.weight))
            share_x = self.share and self.arrange == "rows" and len(out) > 1
            share_y = self.share and self.arrange == "columns" and len(out) > 1
            specs_x = self._specs(out, "x", share_x)
            specs_y = self._specs(out, "y", share_y)
            for k, panel in enumerate(out):
                panel.x, panel.y = specs_x[k], specs_y[k]
                if any(s.hist is not None for s in panel.series) and panel.y.scale == "linear":
                    panel.y = replace(panel.y, include_zero=True)
            self._check_axes(out, share_x, share_y)
            resolved = Resolved(out, [])
            for k, f in enumerate(self.fits, start=1):
                resolved.fits.append(self._fit(k, f, resolved))
            return resolved

        def _numbers(self, s: PlotSeries, tables: dict[str, Any]) -> ResolvedSeries:
            table = tables.get(self.source(s))
            where = f"series '{s.name}'"
            if s.histogram:
                col = table.column(s.values, f"{where} values") if isinstance(s.values, str) else None
                raw = list(col.values) if col is not None else [float(v) for v in s.values]
                lo, hi = s.bin_range if s.bin_range is not None else (None, None)
                try:
                    hist = plotcore.histogram(raw, s.bins, width=s.bin_width, lo=lo, hi=hi, density=s.density, nice=s.nice_bins)
                except VidgenError as error:
                    raise VidgenError(f"{where}: {error}") from None
                rs = ResolvedSeries(s, [float(c) for c in hist.centers], [float(h) for h in hist.heights], col, None, hist=hist)
                rs.y_err = error_arrays(s.y_err, len(rs.xs), table, f"{where} y_err", rs.ys, hist)
                if s.is_live:   # it fills as its values arrive: the progress counts them
                    rs.times = np.arange(len(hist.values) + 1, dtype=float)
                    rs.discrete = True
                return rs
            if s.points is not None:
                xs, ys = [p[0] for p in s.points], [p[1] for p in s.points]
                cols: list[Any] = [None, None]
            else:
                cols, values = [], []
                for axis in ("x", "y"):
                    v = getattr(s, axis)
                    if isinstance(v, str):
                        col = table.column(v, f"{where} {axis}")
                        cols.append(col)
                        values.append(list(col.values))
                    else:
                        cols.append(None)
                        values.append([float(n) for n in v])
                xs, ys = values
            if len(xs) != len(ys):
                raise VidgenError(f"{where}: x has {len(xs)} values but y has {len(ys)}")
            if any(math.isnan(v) for v in xs):
                raise VidgenError(f"{where}: x has a missing value (only y may have gaps)")
            rs = ResolvedSeries(s, xs, ys, cols[0], cols[1])
            rs.y_err = error_arrays(s.y_err, len(xs), table, f"{where} y_err", ys)
            rs.x_err = error_arrays(s.x_err, len(xs), table, f"{where} x_err", xs)
            if s.is_live:
                if s.model is not None:
                    rs.time_col = table.columns[0]
                    rs.times = np.asarray(rs.time_col.values, dtype=float)
                else:
                    rs.times = np.arange(len(xs), dtype=float)
                # steps (a recurrence, a walk, data points): readouts show the last step reached
                rs.discrete = s.model is None or self.models[s.model].kind in ("recurrence", "random_walk")
                if len(xs) < 2:
                    raise VidgenError(f"{where}: a live series needs at least two points")
            return rs

        def _specs(self, panels: list[ResolvedPanel], axis: str, shared: bool) -> list[Any]:
            """Each panel's ``AxisSpec`` on ``axis``: label and unit from the params, else from
            the first series' column (a histogram's y: count or density); units of every column
            on the axis must agree."""
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
                first = group[0].series[0]
                if axis == "y" and not label and first.hist is not None:
                    label = "density" if first.spec.density else "count"
                specs += [param.spec(label, unit)] * len(group)
            return specs

        def _check_axes(self, panels: list[ResolvedPanel], share_x: bool, share_y: bool) -> None:
            for k, panel in enumerate(panels):
                for axis, shared in (("x", share_x), ("y", share_y)):
                    group = panels if shared else [panel]
                    values = [v for p in group for s in p.series for v in (s.x_values() if axis == "x" else s.y_values())]
                    name = f"panels[{k + 1}].{axis}" if len(panels) > 1 and not shared else axis
                    problems = getattr(panel, axis).problems(values, name)
                    if problems:
                        raise VidgenError(problems[0])

        def _fit(self, k: int, f: PlotFit, resolved: Resolved) -> ResolvedFit:
            s = next(r for r in resolved.series if str(r.spec.name) == f.series)
            where = f"fits[{k}] ({f.label()})"
            try:
                if s.hist is not None and f.kind in plotcore.DISTRIBUTIONS:
                    result = plotcore.fit_distribution(s.hist, f.kind)
                    lo, hi = float(s.hist.edges[0]), float(s.hist.edges[-1])
                else:
                    xs, ys = np.asarray(s.xs, dtype=float), np.asarray(s.ys, dtype=float)
                    sigma = s.sigma() if f.weighted else None
                    if s.hist is not None and f.weighted:
                        sigma = np.asarray(s.hist.errors, dtype=float)
                        floor = float(sigma[sigma > 0].min()) if np.any(sigma > 0) else 1.0
                        sigma = np.where(sigma > 0, sigma, floor)   # an empty bin: one count's error
                    x_sigma = (s.x_err[0] + s.x_err[1]) / 2 if f.weighted and s.x_err is not None else None
                    keep = np.isfinite(xs) & np.isfinite(ys)
                    if f.range is not None:
                        keep &= (xs >= f.range[0]) & (xs <= f.range[1])
                    if sigma is not None and np.any(sigma[keep] <= 0):
                        raise VidgenError("a point to fit has a y error of 0; give every point an error, or weighted: false")
                    result = plotcore.fit_curve(xs[keep], ys[keep], f.make_model(), y_err=None if sigma is None else sigma[keep],
                                                x_err=None if x_sigma is None or not np.any(x_sigma[keep] > 0) else x_sigma[keep])
                    lo, hi = float(xs[keep].min()), float(xs[keep].max())
                    if s.hist is not None:
                        lo, hi = max(float(s.hist.edges[0]), lo - s.hist.widths[0] / 2), min(float(s.hist.edges[-1]), hi + s.hist.widths[0] / 2)
            except VidgenError as error:
                raise VidgenError(f"{where}: {error}") from None
            fit = ResolvedFit(f, s, result, f.kind == "poisson", lo, hi)
            panel = resolved.panels[s.panel]
            fit.x_unit, fit.y_unit = panel.x.unit, panel.y.unit
            return fit

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
        names += [f"errors:{s.name}" for s in params.all_series() if s.y_err is not None or s.x_err is not None]
        for i, f in enumerate(params.fits, start=1):
            names += [f"fit{i}", f"fit:{f.label()}"]
        for i, a in enumerate(params.annotations, start=1):
            names += [f"annotation{i}"] + ([f"annotation:{a.id}"] if a.id else [])
        return names

    @staticmethod
    def _legend_panels(params: Any) -> list[bool]:
        """Per panel, whether it shows a legend: ``legend`` if given, else with several series,
        a fit, or error bars with a stated meaning, or (in a figure of several panels) when its
        one series is not already named by the panel's own axis title."""
        panels = params.panel_list()
        if params.legend is not None:
            return [params.legend] * len(panels)
        own = "y" if params.arrange == "rows" else "x"
        fitted = {f.series for f in params.fits}
        out = []
        for panel in panels:
            if len(panel.series) > 1 or any(str(s.name) in fitted or s.meaning is not None for s in panel.series):
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
        resolved = p.resolve(self.project)
        panels, fits = resolved.panels, resolved.fits
        portrait = self.is_portrait
        size_token = p.label_size if p.label_size is not None else ("caption" if portrait else "body")
        size = chart_label_size(size_token)
        for panel in panels:
            panel.x = replace(panel.x, max_ticks=4 if portrait else 7, tight=TIGHT)
            panel.y = replace(panel.y, max_ticks=7 if portrait else 6, tight=TIGHT)
            if p.aspect == "equal":
                panel.x = replace(panel.x, exact=True, margin=0.06, tight=None)
                panel.y = replace(panel.y, exact=True, margin=0.06, tight=None)
        body = self.safe_area
        frame: list[Mobject] = []
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            frame.append(title)
            body = body.below(title, gap=0.35)
        if p.caption:
            cap = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            frame.append(cap)
            body = body.above(cap, gap=0.25)
        measure = plot_draw.text_measure(size, self.theme)
        series = resolved.series
        colors = [self.theme.color(s.spec.color) if s.spec.color else self.theme.palette_color(i) for i, s in enumerate(series)]
        index = {id(s): i for i, s in enumerate(series)}
        marked = [s for s in series if s.spec.drawn_as in ("points", "both")]
        shapes = [s.spec.marker if s.spec.marker != "auto" else CHART_MARKERS[marked.index(s) % len(CHART_MARKERS)] if s in marked else "circle" for s in series]
        count = sum(len(s.xs) for s in marked)
        radius = p.point_radius or next((r for n, r in _RADII if count <= n), 0.035)
        fit_colors = [self.theme.color(f.spec.color) if f.spec.color else (self.theme.color("accent") if len(fits) == 1 else colors[index[id(f.series)]]) for f in fits]

        # the figure: every data panel, each followed by the residual panels of its fits
        figure: list[tuple[str, int]] = []   # ("data", panel index) or ("residual", fit index)
        inputs = []
        weights = []
        for k, panel in enumerate(panels):
            figure.append(("data", k))
            parent = self._panel_input(panel, [f for f in fits if f.panel == k])
            inputs.append(parent)
            weights.append(panel.weight)
            for j, f in enumerate(fits):
                if f.panel == k and f.spec.residuals:
                    figure.append(("residual", j))
                    inputs.append(self._residual_input(f, panel, parent))
                    weights.append(panel.weight * RESIDUAL_WEIGHT)
        arrange = p.arrange if len(panels) > 1 else "rows"
        wanted = self._legend_panels(p)
        entries = [self._legend_entries(panel, fits, k, colors, index, shapes, fit_colors) if wanted[k] else [] for k, panel in enumerate(panels)]
        fit_boxes = [self._fit_box(f, size) for f in fits]
        note_plates = {i: plot_draw.plate(plot_draw.label_text(str(a.text), size=size, theme=self.theme), theme=self.theme)
                       for i, a in enumerate(p.annotations) if a.type == "note"}
        note_panel = {i: (p.annotations[i].panel or 1) - 1 for i in note_plates}
        # live readouts: boxes of their widest text, placed like notes (plot_live.py draws them)
        self._series, self._inputs, self._figure, self._measure, self._label_size = series, inputs, figure, measure, size
        readout_plates = {k: Rectangle(width=w, height=h).set_stroke(width=0).set_fill(opacity=0) for k, (w, h) in self.readout_sizes().items()}

        def layout(right: float, top: float) -> list[Any]:
            area = plotcore.Rect(body.x0, body.y0, body.x1 - right, body.y1)
            try:
                return plotcore.layout_figure(area, inputs, measure, arrange=arrange, share=p.share or len(panels) == 1, top=top, aspect=p.aspect,
                                              weights=weights, gap=0.5 if arrange == "columns" else 0.35)
            except VidgenError as error:
                raise VidgenError(f"scene '{self.spec.id}': {error}") from None

        # legends and fit boxes go in a free spot of their plot; what finds none moves beside
        # the figure (16:9: a column on the right) or above it (9:16), and the figure shrinks
        outside_legend, outside_fits, outside_notes, outside_readouts = False, set(), set(), set()
        for _ in range(len(fits) + len(note_plates) + len(readout_plates) + 3):
            side = self._side(outside_legend, outside_fits, entries, fit_boxes, body, size, portrait,
                              [note_plates[i] for i in sorted(outside_notes)] + [readout_plates[k] for k in sorted(outside_readouts)])
            right, top = (0.0, side.height + 0.3) if portrait and len(side) else ((side.width + 0.45, 0.0) if len(side) else (0.0, 0.0))
            lays = layout(right, top)
            data_lays = [lays[i] for i, (kind, _) in enumerate(figure) if kind == "data"]
            obstacles = {k: self._obstacles(k, data_lays[k], series, fits) for k in range(len(panels))}
            taken: dict[int, list[Any]] = {k: [] for k in range(len(panels))}
            legends: list[Mobject] = []
            moved = False
            if any(entries) and not outside_legend:
                for k, ents in enumerate(entries):
                    if not ents:
                        continue
                    lay = data_lays[k]
                    plot = Region(lay.plot.x0, lay.plot.y0, lay.plot.x1, lay.plot.y1)
                    legend, spot = auto_legend([e[1:] for e in ents], plot, obstacles[k], body.width, size=size)
                    if spot is None:
                        outside_legend = moved = True
                        break
                    legends.append(legend)
                    taken[k].append(self._rect(legend))
            if moved:
                continue
            for j, (f, box) in enumerate(zip(fits, fit_boxes)):
                if j in outside_fits or not len(box):
                    continue
                placed = plotcore.place_in_plot((box.width, box.height), data_lays[f.panel].plot, obstacles[f.panel], taken[f.panel])
                if placed.cost > 0:
                    outside_fits.add(j)
                    moved = True
                    break
                box.move_to([placed.box.center[0], placed.box.center[1], 0])
                taken[f.panel].append(placed.box)
            if moved:
                continue
            for i, note in note_plates.items():
                if i in outside_notes:
                    continue
                at = p.annotations[i].at
                k = note_panel[i]
                placed = plotcore.place_in_plot((note.width, note.height), data_lays[k].plot, obstacles[k], taken[k],
                                                spots=plotcore.annotate.SPOTS if at == "auto" else (at,))
                if placed.cost > 0 and at == "auto":
                    outside_notes.add(i)
                    moved = True
                    break
                note.move_to([placed.box.center[0], placed.box.center[1], 0])
                taken[k].append(placed.box)
            if moved:
                continue
            for k, box in readout_plates.items():
                if k in outside_readouts:
                    continue
                placed = plotcore.place_in_plot((box.width, box.height), data_lays[k].plot, obstacles[k], taken[k])
                if placed.cost > 0:
                    outside_readouts.add(k)
                    moved = True
                    break
                box.move_to([placed.box.center[0], placed.box.center[1], 0])
                taken[k].append(placed.box)
            if not moved:
                break
        if len(side):
            if portrait:
                side.move_to([body.center[0], body.y1 - side.height / 2, 0])
            else:
                top_y = min(data_lays[0].plot.y1, body.y1)
                side.move_to([body.x1 - side.width / 2, top_y - side.height / 2, 0])
                if side.get_bottom()[1] < body.y0:
                    side.shift(UP * (body.y0 - side.get_bottom()[1]))
            if outside_legend:
                legends.append(side[0])
            first = 1 if outside_legend else 0
            for n, j in enumerate(sorted(outside_fits)):
                fit_boxes[j] = side[first + n]
            for n, i in enumerate(sorted(outside_notes)):
                note_plates[i] = side[first + len(outside_fits) + n]
            for n, k in enumerate(sorted(outside_readouts)):
                readout_plates[k] = side[first + len(outside_fits) + len(outside_notes) + n]
        self._readout_box = {k: self._rect(m) for k, m in readout_plates.items()}
        frame += legends
        legend_items: dict[str, Mobject] = {}
        boxes: list[Mobject | None] = []
        if legends:
            keys = [key for ents in entries for key, *_ in ents]
            boxes, items = self._legend_parts(legends)
            legend_items = dict(zip(keys, items))
        drawn = [plot_draw.draw_panel(lay, size=size, grid=p.grid, theme=self.theme) for lay in lays]

        # series
        parts: list[tuple[VGroup, VGroup, VGroup]] = []   # per series: (line runs, markers, bars)
        error_groups: list[VGroup | None] = []
        for s in series:
            i = index[id(s)]
            lay = data_lays[s.panel]
            style = s.spec.drawn_as
            line, dots, bars = VGroup(), VGroup(), VGroup()
            if s.hist is not None and style in ("bars", "step"):
                bars = plot_draw.bars(lay, list(s.hist.edges), s.ys, colors[i], opacity=0.0 if style == "step" else 0.5, theme=self.theme)
            else:
                pts = lay.frame_points(s.xs, s.ys)
                if style in ("line", "both"):
                    line = plot_draw.series_line(lay.frame_line(s.xs, s.ys), lay.plot, colors[i], width=s.spec.width, dashed=s.spec.dashed)
                if style in ("points", "both"):
                    dots = plot_draw.series_markers(pts, lay.plot, colors[i], marker=shapes[i], radius=radius, theme=self.theme)
            parts.append((line, dots.set_z_index(2), bars))
            if s.y_err is not None or s.x_err is not None:
                err_color = mix_colors(colors[i], self.theme.background, 0.85)
                group = plot_draw.error_bars(lay, s.xs, s.ys, y_lo=s.y_err[0] if s.y_err else None, y_hi=s.y_err[1] if s.y_err else None,
                                             x_lo=s.x_err[0] if s.x_err else None, x_hi=s.x_err[1] if s.x_err else None,
                                             color=err_color, width=2.5, cap=max(radius * 1.2, 0.08))
                error_groups.append(group.set_z_index(1))
            else:
                error_groups.append(None)

        # fits
        fit_parts = [self._draw_fit(f, data_lays[f.panel], fit_colors[j], fit_boxes[j]) for j, f in enumerate(fits)]
        for j, f in enumerate(fits):
            if f.spec.residuals:
                pos = figure.index(("residual", j))
                fit_parts[j]["residual"] = self._draw_residuals(f, lays[pos], drawn[pos], colors[index[id(f.series)]], radius, shapes[index[id(f.series)]])

        # annotations
        notes = []
        for i, a in enumerate(p.annotations):
            if a.type == "note":   # placed with the legends and fit boxes
                notes.append({"mark": VGroup(), "label": note_plates[i], "lead": VGroup(), "box": self._rect(note_plates[i]), "spec": a})
                continue
            k =(a.panel - 1) if a.panel is not None else (next(s.panel for s in series if str(s.spec.name) == a.series) if a.series else 0)
            notes.append(self._draw_annotation(a, data_lays[k], series, size, obstacles[k], taken[k], radius))
        for n in notes:
            n["group"] = VGroup(n["mark"], n["lead"], n["label"])

        self.layouts, self.legends, self.fit_results = lays, legends, fits   # the plotcore layouts, legends drawn, fits (with results)
        self.annotation_boxes = [n["box"] for n in notes]
        # the live part (plot_live.py) reads these
        self._series, self._data_lays, self._lays, self._figure, self._drawn, self._inputs = series, data_lays, lays, figure, drawn, inputs
        self._parts, self._errors, self._colors, self._shapes, self._radius, self._label_size = parts, error_groups, colors, shapes, radius, size
        self._fits, self._fit_parts, self._fit_colors, self._notes, self._measure = fits, fit_parts, fit_colors, notes, measure
        self._share_x = arrange == "rows" and p.share and len(panels) > 1
        self._share_y = arrange == "columns" and p.share and len(panels) > 1
        self._live_prepare()
        self.conservation = p.conservation()   # (model, quantity, drift) for lint
        data_pos = [i for i, (kind, _) in enumerate(figure) if kind == "data"]
        axes_mobs = [self._axes_flat.get(i, drawn[i]) for i in data_pos]
        self._steps(title, frame, legends, boxes, legend_items, axes_mobs, self._parts, self._errors, series, fit_parts, fits, notes)

    # ----- steps -----------------------------------------------------------------------------

    def _held(self) -> set[str]:
        """Target names that a timed action (reveal, fit, annotate) brings on screen."""
        patterns = {t for kind in _TIMED for use in self.action_uses(kind) for t in use.config.targets()}
        for use in self.action_uses("grow"):   # a grow of a panel (or of every panel) holds their series
            for t in use.config.targets():
                if t == "axes" or (t.startswith("panel") and t[5:].isdigit()):
                    panels = self.params.panel_list()
                    chosen = panels if t == "axes" else panels[int(t[5:]) - 1 : int(t[5:])]
                    patterns |= {f"series:{s.name}" for panel in chosen for s in panel.series}
        return patterns

    def _steps(self, title: Mobject | None, frame: list[Mobject], legends: list[Mobject], boxes: list[Any], legend_items: dict[str, Mobject],
               drawn: list[Any], parts: list[tuple[VGroup, VGroup, VGroup]], errors: list[VGroup | None], series: list[ResolvedSeries],
               fit_parts: list[dict[str, Any]], fits: list[ResolvedFit], notes: list[dict[str, Any]]) -> None:
        p = self.params
        pieces = [m for m in frame if not any(m is lg for lg in legends)]
        groups = [d if isinstance(d, VGroup) else d.group for d in drawn]   # a flat group: a panel redrawn while playing
        axes_group = VGroup(*groups)
        patterns = self._held()

        def held(names: list[str]) -> bool:
            return any(fnmatchcase(n, pat) for n in names for pat in patterns)

        def show_panel(d: Any) -> list[Animation]:
            group = d if isinstance(d, VGroup) else d.group
            if self.on_screen_parts(group):
                return []
            if isinstance(d, VGroup):
                return [FadeIn(d)]
            rest = VGroup(*[m for m in d.group if m is not d.lines])
            return [Create(d.lines), FadeIn(rest)]

        def intro() -> list[Animation]:
            anims = [FadeIn(m) for m in pieces if not self.on_screen_parts(m)]
            for d in drawn:
                anims += show_panel(d)
            return anims

        chart = self.target("axes", axes_group, entrance=intro)
        self._chart_target = chart
        if title is not None:
            self.target("title", title, entrance=intro)
        if len(drawn) > 1:
            for k, d in enumerate(drawn, start=1):
                self.target(f"panel{k}", groups[k - 1], entrance=lambda d=d: show_panel(d))
        if legends:
            parts_of_legends = [b for b in boxes if b is not None] + list(legend_items.values())
            self.target("legend", VGroup(*legends), entrance=lambda: [FadeIn(m) for m in parts_of_legends if not self.on_screen_parts(m)])

        def legend_entry(key: str) -> list[Animation]:
            """The legend's frame (when it is not on screen yet) and the entry ``key``."""
            item = legend_items.get(key)
            if item is None:
                return []
            anims = []
            for lg, box in zip(legends, boxes):
                if box is not None and any(m is item for m in lg.get_family()) and self._fresh(box):
                    anims.append(FadeIn(box))
            if self._fresh(item):
                anims.append(FadeIn(item))
            return anims

        self._legend_entry = legend_entry

        def grow(k: int) -> list[Animation]:
            """Lines draw from their first point; markers pop in (in data order); bars rise."""
            line, dots, bars = parts[k]
            anims: list[Animation] = [Create(run, rate_func=linear) for run in line]
            if len(dots):
                anims.append(LaggedStart(*[GrowFromCenter(m) for m in dots], lag_ratio=min(0.25, 2.0 / len(dots))))
            if len(bars):
                anims.append(LaggedStart(*[GrowFromEdge(b, DOWN) for b in bars], lag_ratio=min(0.2, 2.0 / len(bars))))
            return [AnimationGroup(*anims, lag_ratio=0.35)] if len(anims) > 1 else anims

        error_targets: dict[int, Any] = {}
        for k, (s, group) in enumerate(zip(series, errors)):
            if group is not None and s.live:   # a live series' error bars grow with it
                error_targets[k] = self.target(f"errors:{s.spec.name}", group, entrance=lambda k=k: self.entrance(series_targets[k]))
            elif group is not None:
                error_targets[k] = self.target(f"errors:{s.spec.name}", group, entrance=lambda k=k, g=group: self.entrance(chart) + self.entrance(series_targets[k])
                                               + [LaggedStart(*[Create(m) for m in g], lag_ratio=min(0.1, 1.0 / max(len(g), 1)))])
        series_targets: list[Any] = []

        def series_entrance(k: int) -> list[Animation]:
            if series[k].live:
                return self.grow_animation([k])
            anims = self.entrance(chart) + legend_entry(f"series{k}") + grow(k)
            names = [f"errors:{series[k].spec.name}"]
            if k in error_targets and not held(names) and not self.is_shown(error_targets[k]):
                g = errors[k]
                anims.append(LaggedStart(*[Create(m) for m in g], lag_ratio=min(0.1, 1.0 / max(len(g), 1))))
            return anims

        for k, s in enumerate(series):
            mob = VGroup(*self._live_parts(k)) if s.live else VGroup(*parts[k])
            series_targets.append(self.target([f"series{k + 1}", f"series:{s.spec.name}"], mob, entrance=lambda k=k: series_entrance(k)))

        def after_growth(pre: list[Animation], own: list[Animation]) -> list[Animation]:
            """``own`` once the data it needs have grown (``pre``)."""
            if not pre:
                return [AnimationGroup(*own, lag_ratio=0.3)] if own else []
            return [Succession(*pre, AnimationGroup(*own, lag_ratio=0.3))] if own else pre

        fit_targets = []
        for j, (f, fp) in enumerate(zip(fits, fit_parts)):
            residual = fp["residual"]

            def fit_entrance(j: int = j, fp: dict[str, Any] = fp, residual: Any = residual) -> list[Animation]:
                k = series.index(fits[j].series)
                residual = fp["residual"]
                anims = self.complete([k]) if series[k].live else self.entrance(series_targets[k])
                own: list[Animation] = []
                if len(fp["band"]):
                    own.append(FadeIn(fp["band"]))
                own += [Create(run, rate_func=smooth) for run in fp["curve"] if run.has_points()]
                own += legend_entry(f"fit{j}") + legend_entry(f"band{j}")
                if len(fp["box"]):
                    own.append(FadeIn(fp["box"], shift=UP * 0.1))
                if residual is not None:
                    panel = residual[0]
                    rest = VGroup(*residual[1:])
                    own.append(AnimationGroup(FadeIn(panel), FadeIn(rest)))
                if series[k].live:
                    return after_growth(anims, own)
                return anims + [AnimationGroup(*own, lag_ratio=0.3)]

            mob = VGroup(fp["band"], fp["curve"], fp["box"], *([residual] if residual is not None else []))
            fit_targets.append(self.target([f"fit{j + 1}", f"fit:{f.spec.label()}"], mob, entrance=fit_entrance))

        note_targets = []
        for i, n in enumerate(notes):
            a: PlotAnnotation = n["spec"]

            def note_entrance(n: dict[str, Any] = n) -> list[Animation]:
                own: list[Animation] = []
                if len(n["mark"]):
                    own.append(FadeIn(n["mark"]) if n["spec"].type in ("xrange", "yrange") else Create(n["mark"]))
                if len(n["lead"]):
                    own.append(Create(n["lead"]))
                if len(n["label"]):
                    own.append(FadeIn(n["label"]))
                k = self._note_panel(n)
                waiting = [i for i, s in enumerate(series) if s.panel == k and s.live and (k in self._schedule or (n["spec"].series is not None and str(s.spec.name) == n["spec"].series))]
                pre = self.complete(waiting)   # an annotation on growing data (or a rescaling panel) waits for the data
                if pre:
                    return after_growth(pre, own)
                return self.entrance(chart) + ([AnimationGroup(*own, lag_ratio=0.4)] if own else [])

            names = [f"annotation{i + 1}"] + ([f"annotation:{a.id}"] if a.id else [])
            note_targets.append(self.target(names, n["group"], entrance=note_entrance))

        def reveal(targets: list[Any]) -> list[Animation]:
            """The targets' entrances (the axes, a legend's frame: once)."""
            self._batch = set()
            try:
                return [a for t in [chart, *targets] for a in self.entrance(t)]
            finally:
                self._batch = None

        steps: list[Any] = []
        free = [k for k, t in enumerate(series_targets) if not held(list(t.names))]
        free_fits = [t for t in fit_targets if not held(list(t.names))]
        free_notes = [t for t in note_targets if not held(list(t.names))]
        # live series grow over their step's slot; consecutive ones on one model grow together
        runs: list[list[int]] = []
        for k in free:
            same = runs and series[runs[-1][-1]].live and series[k].live and series[k].spec.model is not None \
                and series[runs[-1][-1]].spec.model == series[k].spec.model
            if same:
                runs[-1].append(k)
            else:
                runs.append([k])
        if p.reveal == "all":
            static = [series_targets[k] for k in free if not series[k].live]
            growing = [k for k in free if series[k].live]
            waits = [t for t, f in zip(fit_targets, fits) if f.series.live] + [t for t, n in zip(note_targets, notes)
                                                                               if any(s.live and s.panel == self._note_panel(n) for s in series)]
            first = static + [t for t in free_fits + free_notes if t not in waits]
            if growing:
                steps = [lambda: self.live_step(growing, first)]
                later = [t for t in free_fits + free_notes if t in waits]
                if later:
                    steps.append(lambda: reveal(later))
            else:
                steps = [lambda: reveal(first)]
        else:
            steps = [(lambda ks=ks: self.live_step(ks)) if series[ks[0]].live else (lambda t=series_targets[ks[0]]: reveal([t])) for ks in runs]
            steps += [(lambda t=t: reveal([t])) for t in free_fits + free_notes]
        if not steps:
            steps = [lambda: self.entrance(chart)]
        self.reveal(steps, fraction=0.8, cap=2.5)
        self.settle()
        self.finish()

    #: Targets and parts entering in the entrance being built (``None`` between entrances): an
    #: entrance that brings the axes or a legend's frame with it does so once per step.
    _batch: set[int] | None = None

    def _fresh(self, m: Any) -> bool:
        """True (once per entrance being built) when ``m`` is not on screen yet."""
        if self.on_screen_parts(m) or (self._batch is not None and id(m) in self._batch):
            return False
        if self._batch is not None:
            self._batch.add(id(m))
        return True

    def entrance(self, target: Any) -> list[Animation]:
        """The scene's entrance of a target, without what the entrance being built already
        brings (nested entrances: a fit brings its series, a series the axes)."""
        top = self._batch is None
        if top:
            self._batch = set()
        try:
            found = self.find_targets(target) if isinstance(target, str) else [target]
            return [a for t in found if self._fresh(t.mobject) for a in super().entrance(t)]
        finally:
            if top:
                self._batch = None
