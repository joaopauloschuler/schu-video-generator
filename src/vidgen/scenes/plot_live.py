"""Live and animated ``plot`` scenes (Phase W, DESIGN §97.8): series that grow over their beat
(or a ``grow`` action) with a head marker and a live readout, axes that widen smoothly while
the data reach their edge, panels growing together on a shared time, trails for phase-space
plots, and ``zoom`` to a region of the data and back. A mixin of :class:`Plot` (``plot.py``),
written against ``vidgen.api``; the numbers come from ``plotcore.live``.

Everything that changes while it plays (the axes of a rescaling or zoomed panel, a growing
series, its head, the readout) is drawn into a *flat* group whose members are re-shaped in
place every frame (``plot_draw.morph_into``), so manim keeps drawing them during a play or a
wait."""

import math
from typing import Any

import numpy as np

from vidgen.api import *

#: Opacity of the older part of a trail.
TRAIL_OPACITY = 0.28
#: Share of a step's slot a growing step uses (the rest is a pause before the next).
GROW_SHARE = 0.92


class LivePlot:
    """The live part of the ``plot`` scene. :meth:`_live_prepare` is called by ``construct``
    once the figure is laid out and drawn; the attributes it reads are set there (see
    ``Plot.construct``)."""

    #: The seconds of the step slot being played (``play_steps``), for a growth over it.
    _slot: float | None = None

    def play_steps(self, d: float, steps: Any, fraction: float = 0.7, cap: float = 1.2) -> None:
        """As ``NarratedScene.play_steps``, remembering each step's slot (a live series grows
        over its slot)."""
        frame = 1 / config.frame_rate
        groups = max(1, min(len(steps), max(1, int(d / frame + 1e-9)))) if steps else 1
        self._slot = d / groups
        super().play_steps(d, steps, fraction=fraction, cap=cap)   # type: ignore[misc]

    # ----- preparation ---------------------------------------------------------------------------

    def _live_prepare(self) -> None:
        """Decide which panels change while playing, flatten what they draw, plan each
        rescaling axis and draw every panel's first look (the readout boxes ``_readout_box``
        are placed by ``construct``)."""
        series = self._series
        self._shown: dict[int, float] = {i: -math.inf for i, s in enumerate(series) if s.live}   # progress drawn, by series
        self._cache: dict[Any, Any] = {}
        self._zoomed: dict[int, tuple[tuple[float, float], tuple[float, float]]] = {}   # figure position -> its (x, y) zoom domains
        self._hidden_notes: list[Any] = []
        self._growing: list[tuple[Any, Any, list[int]]] = []   # (clock, updater, series) of growths running in waits
        region = any(use.options.x is not None or use.options.y is not None for use in self.action_uses("zoom"))
        self._schedule = {k: self._plan_rescale(k) for k in range(len(self._data_lays))}
        self._schedule = {k: v for k, v in self._schedule.items() if v}
        dynamic = set(range(len(self._lays))) if region else {self._figure.index(("data", k)) for k in self._schedule}
        self._dynamic = dynamic
        self._view = list(self._lays)
        self._domains = [{"x": self._dom(lay.x), "y": self._dom(lay.y)} for lay in self._lays]
        self._axes_flat: dict[int, VGroup] = {}
        for pos in sorted(dynamic):
            kind, j = self._figure[pos]
            if kind == "data":
                self._axes_flat[pos] = plot_draw.flat(self._drawn[pos].group)
            else:
                self._fit_parts[j]["residual"] = plot_draw.flat(self._fit_parts[j]["residual"])
        panel_dynamic = {self._figure[pos][1] for pos in dynamic if self._figure[pos][0] == "data"}
        for i, s in enumerate(series):
            if s.live or s.panel in panel_dynamic:
                line, dots, bars = self._parts[i]
                self._parts[i] = (plot_draw.flat(line), plot_draw.flat(dots), plot_draw.flat(bars))
                if self._errors[i] is not None:
                    self._errors[i] = plot_draw.flat(self._errors[i])
        for j, f in enumerate(self._fits):
            if f.panel in panel_dynamic:
                fp = self._fit_parts[j]
                fp["curve"], fp["band"] = plot_draw.flat(fp["curve"]), plot_draw.flat(fp["band"])
        self._heads = {i: VGroup() for i, s in enumerate(series) if s.live and s.spec.head and s.hist is None}
        self._readouts = {k: VGroup() for k in self._readout_box}
        for i, s in enumerate(series):
            if s.live:
                for part in (*self._parts[i], self._errors[i]):
                    if part is not None:
                        plot_draw.morph_into(part, None)   # nothing drawn before it grows
        for k in self._schedule:
            pos = self._figure.index(("data", k))
            doms = self._domains[pos]
            doms.update({axis: plotcore.domain_at(first, stops, -math.inf) for axis, (first, stops) in self._schedule[k].items()})
            self._set_view(pos)

    def _dom(self, axis: Any) -> tuple[float, float]:
        return axis.transform(axis.lo), axis.transform(axis.hi)

    def _plan_rescale(self, k: int) -> dict[str, Any]:
        """``{axis: (first domain, stops)}`` for the axes of data panel ``k`` that widen while
        its live series grow: every series of the panel live on one progress (one model, or
        one live series), the plot asks for it, the axis is free, not shared, without breaks,
        and its data do not only grow (a time axis is shown whole)."""
        p = self.params
        mine = [s for s in self._series if s.panel == k]
        if not p.rescale or p.aspect == "equal" or not mine or not all(s.live for s in mine):
            return {}
        if len({s.spec.model for s in mine}) > 1 or (mine[0].spec.model is None and len(mine) > 1):
            return {}
        lay = self._data_lays[k]
        shared = {"x": self._share_x, "y": self._share_y}
        out = {}
        times = mine[0].times
        if any(s.hist is not None for s in mine):   # a filling histogram: its bins stay, its counts grow
            spec = self._inputs[self._figure.index(("data", k))].y
            if len(mine) > 1 or shared["y"] or lay.y.scale == "log" or (spec.lo is not None and spec.hi is not None):
                return {}
            i = self._series.index(mine[0])
            bins = self._bins(i)
            counts = np.zeros(len(mine[0].hist.counts))
            tops = [0.0]
            for n, b in enumerate(bins, start=1):
                if b >= 0:
                    counts[b] += 1
                tops.append(float(np.max(counts / (n * mine[0].hist.widths) if mine[0].hist.density else counts)))
            values = np.ravel(np.column_stack([np.zeros(len(tops)), tops]))
            first, stops = plotcore.rescale_schedule(np.repeat(times, 2), values, self._dom(lay.y), fixed_lo=True, fixed_hi=spec.hi is not None)
            return {"y": (first, stops)} if stops or first != self._dom(lay.y) else {}
        for axis in ("x", "y"):
            spec = getattr(self._inputs[self._figure.index(("data", k))], axis)
            built = getattr(lay, axis)
            if shared[axis] or spec.breaks or (spec.lo is not None and spec.hi is not None):
                continue
            values = np.array([[getattr(s, f"{axis}s")[n] for s in mine] for n in range(len(times))], dtype=float)
            if all(plotcore.time_like(times, values[:, c]) for c in range(values.shape[1])):
                continue
            with np.errstate(all="ignore"):
                along = np.array([built.transform(v) if math.isfinite(v) and (built.scale != "log" or v > 0) else math.nan for v in values.ravel()])
            along = along.reshape(values.shape)
            row_lo, row_hi = np.nanmin(np.where(np.isfinite(along), along, np.nan), axis=1), np.nanmax(np.where(np.isfinite(along), along, np.nan), axis=1)
            merged_t = np.repeat(times, 2)
            merged_v = np.ravel(np.column_stack([row_lo, row_hi]))
            first, stops = plotcore.rescale_schedule(merged_t, merged_v, self._dom(built), fixed_lo=spec.lo is not None, fixed_hi=spec.hi is not None)
            if stops or first != self._dom(built):
                out[axis] = (first, stops)
        return out

    # ----- drawing ------------------------------------------------------------------------------

    def _set_view(self, pos: int) -> None:
        """Lay out figure position ``pos`` for its current domains and redraw what it shows."""
        static = self._lays[pos]
        spec = self._inputs[pos]
        doms = self._domains[pos]
        x = plotcore.axis_for(static.x, spec.x, *doms["x"])
        y = plotcore.axis_for(static.y, spec.y, *doms["y"])
        lay = static if (x is static.x and y is static.y) else plotcore.relabel(static, x, y, self._measure)
        self._view[pos] = lay
        kind, j = self._figure[pos]
        if kind == "residual":
            f = self._fits[j]
            i = self._series.index(f.series)
            drawing = plot_draw.draw_panel(lay, size=self._label_size, grid=self.params.grid, theme=self.theme, cache=self._cache)
            plot_draw.morph_into(self._fit_parts[j]["residual"], self._draw_residuals(f, lay, drawing, self._colors[i], self._radius, self._shapes[i]))
            return
        if pos in self._axes_flat:
            drawing = plot_draw.draw_panel(lay, size=self._label_size, grid=self.params.grid, theme=self.theme, cache=self._cache)
            plot_draw.morph_into(self._axes_flat[pos], drawing.group)
        for i, s in enumerate(self._series):
            if s.panel == j:
                self._draw_series(i)
        for n, f in enumerate(self._fits):
            if f.panel == j and pos in self._dynamic:
                fp = self._fit_parts[n]
                drawn = self._draw_fit(f, lay, self._fit_colors[n], fp["box"])
                plot_draw.morph_into(fp["curve"], drawn["curve"])
                plot_draw.morph_into(fp["band"], drawn["band"])
        self._draw_readout(j)

    def _data_view(self, k: int) -> Any:
        return self._view[self._figure.index(("data", k))]

    def _draw_series(self, i: int) -> None:
        """Redraw series ``i`` (its grown part when live) in its panel's current view."""
        s = self._series[i]
        lay = self._data_view(s.panel)
        line, dots, bars = self._parts[i]
        color = self._colors[i]
        style = s.spec.drawn_as
        if s.hist is not None:
            heights, errors = self._hist_heights(i)
            if style in ("bars", "step"):
                plot_draw.morph_into(bars, plot_draw.bars(lay, list(s.hist.edges), heights, color, opacity=0.0 if style == "step" else 0.5, theme=self.theme))
            else:
                shown = [h if not s.live or h > 0 else math.nan for h in heights]   # an empty bin of a filling histogram: no marker yet
                plot_draw.morph_into(dots, plot_draw.series_markers(lay.frame_points(s.xs, shown), lay.plot, color, marker=self._shapes[i], radius=self._radius,
                                                                   theme=self.theme).set_z_index(2))
            if self._errors[i] is not None:
                bars_err = plot_draw.error_bars(lay, s.xs, heights, y_lo=errors, y_hi=errors, color=mix_colors(color, self.theme.background, 0.85),
                                                width=2.5, cap=max(self._radius * 1.2, 0.08))
                plot_draw.morph_into(self._errors[i], bars_err.set_z_index(1))
            return
        if s.live:
            u = self._shown.get(i, -math.inf)
            xs, ys = plotcore.grown(s.times, s.xs, s.ys, u)
            reached = int(np.searchsorted(s.times, u, side="right"))
        else:
            xs, ys, reached = list(s.xs), list(s.ys), len(s.xs)
        if style in ("line", "both"):
            new = VGroup()
            trail = s.spec.trail if s.live else None
            if trail and len(xs) >= 2 and u - trail > s.times[0]:
                old_x, old_y = plotcore.grown(s.times, s.xs, s.ys, u - trail)
                faded = plot_draw.series_line(lay.frame_line(old_x, old_y), lay.plot, color, width=s.spec.width, dashed=s.spec.dashed)
                faded.set_stroke(opacity=TRAIL_OPACITY)
                rx, ry = plotcore.segment(s.times, s.xs, s.ys, u - trail, u)
                new.add(faded, plot_draw.series_line(lay.frame_line(rx, ry), lay.plot, color, width=s.spec.width, dashed=s.spec.dashed))
            elif len(xs) >= 2:
                new.add(plot_draw.series_line(lay.frame_line(xs, ys), lay.plot, color, width=s.spec.width, dashed=s.spec.dashed))
            plot_draw.morph_into(line, new.set_z_index(0.5))   # above gridlines redrawn meanwhile
        if style in ("points", "both"):
            pts = lay.frame_points(list(s.xs[:reached]), list(s.ys[:reached]))
            plot_draw.morph_into(dots, plot_draw.series_markers(pts, lay.plot, color, marker=self._shapes[i], radius=self._radius, theme=self.theme).set_z_index(2))
        self._draw_errors(i, reached)
        if i in self._heads:
            mark = VGroup()
            if xs and math.isfinite(xs[-1]) and math.isfinite(ys[-1]):
                fx, fy = lay.frame_x(xs[-1]), lay.frame_y(ys[-1])
                if lay.plot.contains(fx, fy, 1e-6):
                    mark = plot_draw.head_marker((fx, fy), color, radius=max(self._radius * 1.3, 0.075), theme=self.theme)
            plot_draw.morph_into(self._heads[i], mark)

    def _hist_heights(self, i: int, count: int | None = None) -> tuple[list[float], list[float]]:
        """A histogram's heights and √N errors with its first ``count`` values (default: as
        many as it has received; a static one: all)."""
        s = self._series[i]
        if not s.live:
            errors = s.y_err[0] if s.y_err is not None else np.zeros(len(s.ys))
            return list(s.ys), [float(e) for e in errors]
        if count is None:
            count = int(max(0.0, min(self._shown.get(i, 0.0), float(s.times[-1]))))
        bins = self._bins(i)[:count]
        counts = np.bincount(bins[bins >= 0], minlength=len(s.hist.counts)).astype(float)
        heights = counts / (max(counts.sum(), 1.0) * s.hist.widths) if s.hist.density else counts
        per_count = np.divide(heights, counts, out=np.zeros_like(counts), where=counts > 0)   # 1 for counts, 1/(N·width) for a density
        errors = np.sqrt(counts) * per_count
        return [float(h) for h in heights], [float(e) for e in errors]

    def _bins(self, i: int) -> np.ndarray:
        """The bin of each of a histogram's values in arrival order (−1: outside)."""
        cache = self.__dict__.setdefault("_bin_cache", {})
        if i not in cache:
            h = self._series[i].hist
            k = np.searchsorted(h.edges, h.values, side="right") - 1
            k = np.where(h.values == h.edges[-1], len(h.counts) - 1, k)   # the last bin includes its right edge
            cache[i] = np.where((k >= 0) & (k < len(h.counts)), k, -1)
        return cache[i]

    def _draw_errors(self, i: int, count: int) -> None:
        s = self._series[i]
        group = self._errors[i]
        if group is None:
            return
        lay = self._data_view(s.panel)
        y_err, x_err = s.y_err, s.x_err
        new = plot_draw.error_bars(lay, s.xs[:count], s.ys[:count], y_lo=y_err[0][:count] if y_err else None, y_hi=y_err[1][:count] if y_err else None,
                                   x_lo=x_err[0][:count] if x_err else None, x_hi=x_err[1][:count] if x_err else None,
                                   color=mix_colors(self._colors[i], self.theme.background, 0.85), width=2.5, cap=max(self._radius * 1.2, 0.08))
        plot_draw.morph_into(group, new.set_z_index(1))

    # ----- readouts -----------------------------------------------------------------------------

    def _readout_lines(self, k: int, until: float | None) -> list[str]:
        """The readout of panel ``k`` at progress ``until`` (``None``: at the end): the model's
        time once, then each live series with a readout."""
        lines: list[str] = []
        timed: set[str] = set()
        for i, s in enumerate(self._series):
            if s.panel != k or not s.live or not s.spec.readout:
                continue
            u = min(max(s.times[-1] if until is None else until, s.times[0]), s.times[-1])
            if s.hist is not None:   # a filling histogram: how many values it holds
                label = s.spec.readout if isinstance(s.spec.readout, str) else "events"
                lines.append(plotcore.readout_text(label, float(int(u)), integer=True))
                continue
            if s.discrete:   # the last step reached
                n = max(int(np.searchsorted(s.times, u, side="right")) - 1, 0)
                u, value = float(s.times[n]), float(s.ys[n])
            else:
                value = plotcore.value_at(s.times, s.ys, u)
            whole = getattr(s, "whole", None)   # whole numbers (a walker's position) are written whole
            if whole is None:
                whole = s.whole = s.discrete and all(float(v).is_integer() for v in s.ys if math.isfinite(v))
            if s.time_col is not None and s.spec.model not in timed:
                timed.add(s.spec.model)
                lines.append(plotcore.readout_text(s.time_col.name, u, s.time_col.unit, integer=s.discrete))
            label = s.spec.readout if isinstance(s.spec.readout, str) else (s.y_col.name if s.y_col is not None else str(s.spec.name))
            unit = s.y_col.unit if s.y_col is not None and s.y_col.unit else self._inputs[self._figure.index(("data", k))].y.unit
            lines.append(plotcore.readout_text(label, value, unit, integer=whole))
        return lines

    def readout_sizes(self) -> dict[int, tuple[float, float]]:
        """``{data panel: (width, height)}`` of each panel's readout box: its widest lines
        over the whole growth (placed with the legends, fit boxes and notes)."""
        out = {}
        for k in {s.panel for s in self._series}:
            if not self._readout_lines(k, None):
                continue
            longest = [max(lines_at, key=len) for lines_at in zip(*[self._readout_lines(k, u) for u in self._readout_probe(k)])]
            dims = [self._measure(t) for t in longest]
            pad = plot_draw.PLATE_PAD
            out[k] = (max(d[0] for d in dims) + 0.1 + 2 * pad, sum(d[1] for d in dims) + 0.12 * (len(dims) - 1) * self._label_size / 24 + 2 * pad)
        return out

    def _readout_probe(self, k: int) -> list[float]:
        """Progress values whose readouts give the widest text (every sample, at most 400)."""
        times = next(s.times for s in self._series if s.panel == k and s.live and s.spec.readout)
        step = max(1, len(times) // 400)
        return [float(t) for t in times[::step]] + [float(times[-1])]

    def _draw_readout(self, k: int) -> None:
        if k not in self._readouts:
            return
        started = [i for i, s in enumerate(self._series) if s.panel == k and s.live and s.spec.readout and self._shown.get(i, -math.inf) >= s.times[0]]
        if not started:
            plot_draw.morph_into(self._readouts[k], None)
            return
        u = max(self._shown[i] for i in started)
        box = self._readout_box[k]
        lines = VGroup(*[self._readout_label(t) for t in self._readout_lines(k, u)])
        if len(lines) > 1:
            lines.arrange(DOWN, buff=0.12 * self._label_size / 24, aligned_edge=LEFT)
        if lines.width > box.width - 2 * plot_draw.PLATE_PAD:   # a box shrunk beside the figure
            lines.scale((box.width - 2 * plot_draw.PLATE_PAD) / lines.width)
        lines.move_to([box.x0 + plot_draw.PLATE_PAD + lines.width / 2, box.y1 - plot_draw.PLATE_PAD - lines.height / 2, 0])
        plate = RoundedRectangle(width=box.width, height=box.height, corner_radius=0.08)
        plate.set_fill(self.theme.background, opacity=0.88).set_stroke(self.theme.color("dim"), width=1, opacity=0.5)
        plate.move_to([box.center[0], box.center[1], 0])
        # text above its plate by z-index (members added while playing are drawn in no set order)
        plot_draw.morph_into(self._readouts[k], VGroup(plate.set_z_index(3), lines.set_z_index(3.5)))

    def _readout_label(self, text: str) -> Mobject:
        key = ("readout", text)
        if key not in self._cache:
            self._cache[key] = plot_draw.label_text(text, size=self._label_size, theme=self.theme)
        return self._cache[key].copy()

    # ----- growth -------------------------------------------------------------------------------

    def _live_parts(self, i: int) -> list[Mobject]:
        """What series ``i`` draws (its target's mobjects)."""
        line, dots, bars = self._parts[i]
        out = [line, dots, bars]
        if self._errors[i] is not None:
            out.append(self._errors[i])
        if i in self._heads:
            out.append(self._heads[i])
        if self._series[i].panel in self._readouts and self._series[i].spec.readout:
            out.append(self._readouts[self._series[i].panel])
        return out

    def _clock(self) -> Mobject:
        """The empty mobject that drives growths and zooms (their animations' mobject, or the
        holder of a growth's updater), in the scene beneath everything: while it moves, manim
        redraws the whole frame, so parts re-shaped in place are drawn. (A group holding the
        parts would be dissolved by manim when one of them is added on its own.)"""
        clock = getattr(self, "_clock_mob", None)
        if clock is None:
            clock = self._clock_mob = Mobject().set_z_index(-1000)
        if clock not in self.get_mobject_family_members():
            self.add(clock)
        return clock

    def _show(self, ks: list[int]) -> None:
        """Put the (still empty) parts of series ``ks`` in the scene before they grow."""
        for i in ks:
            for m in self._live_parts(i):
                if not self.on_screen_parts(m):
                    self.add(m)

    def _advance(self, until: dict[int, float]) -> None:
        """Set the progress of live series and redraw them (and rescale their panels)."""
        for i, u in until.items():
            self._shown[i] = u
        done: set[int] = set()
        for k in sorted({self._series[i].panel for i in until}):
            pos = self._figure.index(("data", k))
            if k not in self._schedule or pos in self._zoomed:
                continue
            live = [i for i, s in enumerate(self._series) if s.panel == k and s.live]
            progress = max(self._shown[i] for i in live)
            doms = {axis: plotcore.domain_at(first, stops, progress) for axis, (first, stops) in self._schedule[k].items()}
            if any(doms[a] != self._domains[pos][a] for a in doms):
                self._domains[pos].update(doms)
                self._set_view(pos)
                done |= {i for i, s in enumerate(self._series) if s.panel == k}
        for i in until:
            if i not in done:
                self._draw_series(i)
        for k in {self._series[i].panel for i in until}:
            self._draw_readout(k)

    def _span(self, ks: list[int], to: float | None) -> dict[int, tuple[float, float]]:
        """``{series: (from, to)}`` of a growth of ``ks`` to progress ``to`` (default: the end)."""
        out = {}
        for i in ks:
            s = self._series[i]
            start = max(self._shown[i], float(s.times[0]))
            end = float(s.times[-1]) if to is None else min(max(float(to), float(s.times[0])), float(s.times[-1]))
            if end > start or self._shown[i] < s.times[0]:
                out[i] = (start, max(end, start))
        return out

    def _stop_growth(self, ks: list[int]) -> None:
        """Stop growths running in waits that involve ``ks`` (an action takes over)."""
        for item in list(self._growing):
            clock, update, which = item
            if set(which) & set(ks):
                clock.remove_updater(update)
                self._growing.remove(item)

    def grow_animation(self, ks: list[int], to: float | None = None) -> list[Animation]:
        """Animations growing live series ``ks`` from where they are to ``to`` (their end):
        the axes first when they are not on screen yet. Played at the caller's run time."""
        self._stop_growth(ks)
        spans = self._span(ks, to)
        if not spans:
            return []
        intro = self._intro(list(spans))
        self._show(list(spans))

        def frame(_: Mobject, alpha: float) -> None:
            self._advance({i: a + (b - a) * alpha for i, (a, b) in spans.items()})

        growth = UpdateFromAlphaFunc(self._clock(), frame, rate_func=linear)
        if intro:
            return [Succession(AnimationGroup(*intro, run_time=0.14), growth.set_run_time(0.86))]
        return [growth]

    def _intro(self, ks: list[int], targets: list[Any] | None = None) -> list[Animation]:
        """What must come on screen before series ``ks`` grow (axes, legend entries), with the
        entrances of ``targets`` (inside the entrance being built, if any)."""
        top = self._batch is None
        if top:
            self._batch = set()
        try:
            out = [a for t in [self._chart_target, *(targets or [])] for a in self.entrance(t)]
            for i in ks:
                out += self._legend_entry(f"series{i}")
            return out
        finally:
            if top:
                self._batch = None

    def live_step(self, ks: list[int], targets: list[Any] | None = None) -> list[Animation]:
        """A step growing live series ``ks`` over the step's slot while the narration goes on:
        the axes (and the entrances of ``targets``) come in first, then the series grow in the
        waits that follow."""
        spans = self._span(ks, None)
        intro = self._intro(list(spans), targets)
        slot = self._slot or 3.0
        start = float(self.renderer.time)
        if intro:
            self.play(*intro, run_time=min(0.8, 0.25 * slot))
        if not spans:
            return []
        self._stop_growth(list(spans))
        spent = float(self.renderer.time) - start   # whole frames: may be more than asked
        duration = max(min(slot * GROW_SHARE, slot - 1 / config.frame_rate) - spent, 1 / config.frame_rate)
        elapsed = [0.0]

        def update(m: Mobject, dt: float) -> None:
            elapsed[0] += dt
            f = min(1.0, elapsed[0] / duration)
            self._advance({i: a + (b - a) * f for i, (a, b) in spans.items()})
            if f >= 1.0:
                m.remove_updater(update)
                self._growing[:] = [g for g in self._growing if g[1] is not update]

        self._show(list(spans))
        self._advance({i: a for i, (a, _) in spans.items()})
        clock = self._clock()
        clock.add_updater(update)
        self._growing.append((clock, update, list(spans)))
        if self.capture is not None and self._current_beat is not None:
            fps = config.frame_rate
            self.capture.add_mid_still(self._current_beat, round(float(self.renderer.time) * fps), round(duration * fps), "grow")
        return []

    def settle(self) -> None:
        """End growths still running (the scene is over): their series drawn to the end."""
        for clock, update, which in list(self._growing):
            clock.remove_updater(update)
            self._advance({i: float(self._series[i].times[-1]) for i in which})
        self._growing = []

    def complete(self, ks: list[int]) -> list[Animation]:
        """Animations finishing the growth of live series ``ks`` (none when they are done): a
        fit or an annotation on live data waits for the data."""
        live = [i for i in ks if self._series[i].live and self._shown[i] < self._series[i].times[-1]]
        return self.grow_animation(live) if live else []

    def entrance_time(self, target: Any) -> float | None:
        """A live series revealed by an action grows over the rest of its beat."""
        if any(n.startswith("series") for n in target.names) and any(self._series[i].live for i in self._target_series(target.name)):
            return self.beat_time_left(next_action=True)
        return super().entrance_time(target)   # type: ignore[misc]

    def _target_series(self, name: str) -> list[int]:
        """The series a target name of a ``grow`` or ``zoom`` means: a series, a panel's or
        (``axes``) every panel's."""
        if name == "axes":
            return list(range(len(self._series)))
        if name.startswith("panel") and name[5:].isdigit():
            return [i for i, s in enumerate(self._series) if s.panel == int(name[5:]) - 1]
        if name.startswith("series:"):
            return [i for i, s in enumerate(self._series) if str(s.spec.name) == name[7:]]
        if name.startswith("series") and name[6:].isdigit():
            return [int(name[6:]) - 1]
        return []

    def grow_to(self, targets: list[Any], to: float | None) -> list[Animation]:
        """The ``grow`` action: the live series the targets name grow to ``to`` (their end)."""
        ks = sorted({i for t in targets for i in self._target_series(t.name) if self._series[i].live})
        return self.grow_animation(ks, to)

    # ----- zoom ---------------------------------------------------------------------------------

    def _zoom_positions(self, targets: list[Any], x: Any, y: Any) -> dict[int, dict[str, tuple[float, float]]]:
        """``{figure position: {axis: domain}}`` a region zoom changes: the targets' panels (on
        x every panel sharing it, residual panels included)."""
        panels = {self._series[i].panel for t in targets for i in self._target_series(t.name)}
        x_panels = set(range(len(self._data_lays))) if self._share_x else panels   # residual panels follow their plot's x
        out: dict[int, dict[str, tuple[float, float]]] = {}
        for pos, (kind, j) in enumerate(self._figure):
            k = j if kind == "data" else self._fits[j].panel
            doms: dict[str, tuple[float, float]] = {}
            if x is not None and k in x_panels:
                doms["x"] = self._zoom_domain(self._lays[pos].x, x, "x")
            if y is not None and kind == "data" and k in panels:
                doms["y"] = self._zoom_domain(self._lays[pos].y, y, "y")
            if doms:
                out[pos] = doms
        return out

    def _zoom_domain(self, axis: Any, rng: Any, name: str) -> tuple[float, float]:
        lo, hi = float(rng[0]), float(rng[1])
        if len(axis.segments) > 1:
            raise VidgenError(f"scene '{self.spec.id}': zoom on a broken {name} axis is not supported; drop the breaks or zoom on the other axis")
        if axis.scale == "log" and lo <= 0:
            raise VidgenError(f"scene '{self.spec.id}': zoom {name}: [{lo:g}, {hi:g}] on a log axis needs positive values")
        return axis.transform(lo), axis.transform(hi)

    def zoom_region(self, targets: list[Any], x: Any, y: Any) -> list[Animation]:
        """The ``zoom`` action with ``x`` / ``y``: the panels' axes ease to the region, the data
        redrawn in it; annotations of those panels step aside until the zoom ends."""
        wanted = self._zoom_positions(targets, x, y)
        if not wanted:
            return []
        start = {pos: dict(self._domains[pos]) for pos in wanted}
        goal = {pos: {**self._domains[pos], **doms} for pos, doms in wanted.items()}
        for pos in wanted:
            self._zoomed[pos] = (goal[pos]["x"], goal[pos]["y"])
        panels = {self._figure[pos][1] for pos in wanted if self._figure[pos][0] == "data"}
        notes = [n for n in self._notes if self._note_panel(n) in panels and self.on_screen_parts(n["group"])]
        self._hidden_notes += notes
        return self._domain_animation(start, goal) + [FadeOut(n["group"]) for n in notes]

    def zoom_back(self) -> list[Animation]:
        """Undo :meth:`zoom_region`: back to the domains the panels would show now."""
        if not self._zoomed:
            return []
        start = {pos: dict(self._domains[pos]) for pos in self._zoomed}
        goal = {}
        for pos in self._zoomed:
            kind, j = self._figure[pos]
            home = {"x": self._dom(self._lays[pos].x), "y": self._dom(self._lays[pos].y)}
            if kind == "data" and j in self._schedule:
                live = [i for i, s in enumerate(self._series) if s.panel == j and s.live]
                progress = max(self._shown[i] for i in live)
                home.update({a: plotcore.domain_at(first, stops, progress) for a, (first, stops) in self._schedule[j].items()})
            goal[pos] = home
        notes, self._hidden_notes = self._hidden_notes, []
        return self._domain_animation(start, goal, back=True) + [FadeIn(n["group"]) for n in notes]

    def _domain_animation(self, start: dict[int, dict[str, Any]], goal: dict[int, dict[str, Any]], back: bool = False) -> list[Animation]:
        """The panels' domains easing from ``start`` to ``goal``; ``back``: the zoom is over
        at the end (a growth rescales them again)."""
        def frame(_: Mobject, alpha: float) -> None:
            for pos in start:
                for axis in ("x", "y"):
                    self._domains[pos][axis] = plotcore.blend(start[pos][axis], goal[pos][axis], alpha)
                self._set_view(pos)
                if back and alpha >= 1.0:
                    self._zoomed.pop(pos, None)

        return [UpdateFromAlphaFunc(self._clock(), frame, rate_func=linear)]

    def _note_panel(self, note: dict[str, Any]) -> int:
        a = note["spec"]
        if a.panel is not None:
            return a.panel - 1
        if a.series is not None:
            return next(s.panel for s in self._series if str(s.spec.name) == a.series)
        return 0


__all__ = ["GROW_SHARE", "LivePlot", "TRAIL_OPACITY"]
