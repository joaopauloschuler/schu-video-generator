"""The drawing helpers of the ``plot`` scene type (Phase W, DESIGN §97.4-97.6): what each panel's
axes must show, legend entries, the data points text must keep clear of, fitted curves, their
parameter boxes and residual panels, the side column (or row) for what finds no free spot, and
annotations. A mixin of :class:`Plot` (``plot.py``), written against ``vidgen.api``."""

import math
from dataclasses import replace
from typing import Any

import numpy as np

from vidgen.api import *

from .plot_parts import ERROR_MEANINGS, PlotAnnotation, ResolvedFit, ResolvedPanel, ResolvedSeries, series_point

#: A free axis end is rounded out to a tick only when that adds at most this share of the
#: data's span (else the plot ends just past the data and fills its area).
TIGHT = 0.08


class PlotFigure:
    """Drawing helpers of :class:`Plot` (they read ``self.theme``, ``self.params``, ``self.spec``)."""

    # ----- figure inputs ------------------------------------------------------------------------

    @staticmethod
    def _usable(values: list[float], spec: Any) -> list[float]:
        """Extra values an axis should show (error bar ends, a fit's curve) that it can show:
        finite, positive on a log axis, inside fixed ends, not in a break."""
        out = []
        for v in values:
            if not math.isfinite(v) or (spec.scale == "log" and v <= 0):
                continue
            if (spec.lo is not None and v < spec.lo) or (spec.hi is not None and v > spec.hi):
                continue
            if any(a < v < b for a, b in spec.breaks):
                continue
            out.append(v)
        return out

    def _panel_input(self, panel: ResolvedPanel, fits: list[ResolvedFit]) -> Any:
        xs = [v for s in panel.series for v in s.x_values()]
        ys = [v for s in panel.series for v in s.y_values()]
        xs += self._usable([v for s in panel.series for v in s.extents("x")], panel.x)
        ys += self._usable([v for s in panel.series for v in s.extents("y")], panel.y)
        for f in fits:
            grid = f.curve_x(f.lo, f.hi, panel.x.scale, 120)
            ys += self._usable([float(v) for v in f.result(grid)], panel.y)
        return plotcore.PanelInput(tuple(xs), tuple(ys), panel.x, panel.y)

    @staticmethod
    def _residuals(f: ResolvedFit) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``(x, residual, error)`` of a fit's points (normalized: (y − f)/σ, without errors;
        σ of Poisson counts is the fit's √(scale·f), as in its χ²)."""
        s = f.series
        xs, ys = np.asarray(s.xs, dtype=float), np.asarray(s.ys, dtype=float)
        sigma = s.hist.errors if s.hist is not None else s.sigma()
        res = ys - f.result(xs)
        err = np.asarray(sigma, dtype=float) if sigma is not None else np.zeros_like(xs)
        if f.spec.residuals == "normalized" and f.poisson is not None:   # Pearson residuals: the fit's own variance
            with np.errstate(all="ignore"):
                err = np.sqrt(f.poisson * np.maximum(f.result(xs), 0.0))
        if f.spec.residuals == "normalized":   # pulls: every error is 1 by definition, so no bars
            with np.errstate(all="ignore"):
                res = np.where(err > 0, res / np.where(err > 0, err, 1.0), np.nan)
            err = np.zeros_like(res)
        ok = np.isfinite(xs) & np.isfinite(res)
        if f.spec.range is not None:
            ok &= (xs >= f.spec.range[0]) & (xs <= f.spec.range[1])
        return xs[ok], res[ok], err[ok]

    def _residual_input(self, f: ResolvedFit, panel: ResolvedPanel, parent: Any) -> Any:
        xs, res, err = self._residuals(f)
        normalized = f.spec.residuals == "normalized"
        spec = plotcore.AxisSpec(label="(y − fit)/σ" if normalized else "residual", unit="" if normalized else panel.y.unit,
                                 include_zero=True, max_ticks=3, tight=TIGHT, format=panel.y.format if panel.y.scale == "linear" else "auto")
        ys = [0.0, *res, *(res - err), *(res + err)]
        if normalized:   # symmetric, ticked at ±2σ (the band most points should fall in; 0 has its own line)
            reach = max([abs(v) for v in ys if math.isfinite(v)] + [2.0])
            edge = max(2.5, math.ceil(reach * 1.05 * 2) / 2)
            spec = replace(spec, lo=-edge, hi=edge, ticks=(-2.0, 2.0) if edge <= 6 else None)
        return plotcore.PanelInput(parent.x_values, tuple(float(v) for v in ys if math.isfinite(v)), panel.x, spec)

    # ----- legend -------------------------------------------------------------------------------

    def _legend_entries(self, panel: ResolvedPanel, fits: list[ResolvedFit], k: int, colors: list[str], index: dict[int, int], shapes: list[str],
                        fit_colors: list[str]) -> list[tuple[str, str, str, str]]:
        """``(key, name, colour, swatch)`` per series of the panel, then per fit."""
        out = []
        for s in panel.series:
            i = index[id(s)]
            name = str(s.spec.name)
            if s.spec.meaning is not None:
                name += f" ({ERROR_MEANINGS[s.spec.meaning]})"
            style = s.spec.drawn_as
            swatch = "box" if style == "bars" else shapes[i] if style == "points" else "dashed" if s.spec.dashed else "line"
            out.append((f"series{i}", name, colors[i], swatch))
        for j, f in enumerate(fits):
            if f.panel == k:
                out.append((f"fit{j}", str(f.spec.name) or f.result.model.formula, fit_colors[j], "dashed" if f.spec.dashed else "line"))
                if f.spec.band != "none":
                    out.append((f"band{j}", f"{f.spec.level * 100:g} % {f.spec.band} band", fit_colors[j], "band"))
        return out

    @staticmethod
    def _legend_parts(legends: list[Mobject]) -> tuple[list[Mobject | None], list[Mobject]]:
        """The frame of each legend (``None`` for one above the figure) and every entry, in
        order."""
        boxes, items = [], []
        for lg in legends:
            if len(lg) == 2 and isinstance(lg[0], RoundedRectangle):
                boxes.append(lg[0])
                rows = lg[1]
            else:
                boxes.append(None)
                rows = lg
            items += [item for row in rows for item in row]
        return boxes, items

    @staticmethod
    def _sample(lay: Any, s: ResolvedSeries) -> list[np.ndarray]:
        """Frame points a legend or a label must keep clear of: the series' points, samples
        along its line, the inside of its bars, its error bars' ends."""
        if s.hist is not None and s.spec.drawn_as in ("bars", "step"):
            out = []
            for a, b, h in zip(s.hist.edges, s.hist.edges[1:], s.ys):
                x0, x1 = lay.frame_x(a), lay.frame_x(b)
                top = lay.frame_y(h) if (lay.y.scale != "log" or h > 0) else lay.plot.y0
                for fx in np.linspace(x0, x1, max(2, int((x1 - x0) / 0.12) + 1)):
                    for fy in np.arange(lay.plot.y0, min(top, lay.plot.y1) + 1e-9, 0.15):
                        out.append(np.array([fx, fy, 0.0]))
                    out.append(np.array([fx, min(top, lay.plot.y1), 0.0]))
            return out
        pts = lay.frame_points(s.xs, s.ys)
        out = [q for q in pts if not np.isnan(q[:2]).any()]
        if s.spec.drawn_as in ("line", "both"):
            for run in plotcore.clip_polyline(lay.frame_line(s.xs, s.ys), lay.plot):
                out.extend(sample_path(list(run)))
        for axis, err in (("y", s.y_err), ("x", s.x_err)):
            if err is None:
                continue
            for x, y, lo, hi in zip(s.xs, s.ys, *err):
                if not (math.isfinite(x) and math.isfinite(y)):
                    continue
                for v in np.linspace(-lo, hi, 5):
                    q = (x, y + v) if axis == "y" else (x + v, y)
                    if (axis == "y" and lay.y.scale == "log" and q[1] <= 0) or (axis == "x" and lay.x.scale == "log" and q[0] <= 0):
                        continue
                    out.append(np.array([lay.frame_x(q[0]), lay.frame_y(q[1]), 0.0]))
        return out

    def _obstacles(self, k: int, lay: Any, series: list[ResolvedSeries], fits: list[ResolvedFit]) -> np.ndarray:
        """Every frame point of the data in panel ``k`` (what text must not cover)."""
        panel_series = [s for s in series if s.panel == k]
        pts = [q for s in panel_series for q in self._sample(lay, s)]
        for f in fits:
            if f.panel == k:
                lo, hi = self._curve_range(f, lay)
                xs = f.curve_x(lo, hi, lay.x.scale, 160)
                for run in plotcore.clip_polyline(lay.frame_line(list(xs), list(f.result(xs))), lay.plot):
                    pts.extend(sample_path(list(run)))
        return np.array(pts).reshape(-1, 3)[:, :2] if pts else np.zeros((0, 2))

    @staticmethod
    def _rect(m: Mobject) -> Any:
        return plotcore.Rect(m.get_left()[0], m.get_bottom()[1], m.get_right()[0], m.get_top()[1])

    # ----- fits ---------------------------------------------------------------------------------

    @staticmethod
    def _curve_range(f: ResolvedFit, lay: Any) -> tuple[float, float]:
        if f.spec.extend:
            return lay.x.lo, lay.x.hi
        return max(f.lo, lay.x.lo), min(f.hi, lay.x.hi)

    def _curve_points(self, f: ResolvedFit, lay: Any) -> tuple[list[float], list[float]]:
        """Data points along the fitted curve, a gap at every x break (a Poisson fit: steps)."""
        lo, hi = self._curve_range(f, lay)
        if f.discrete:
            xs, ys = [], []
            for c in f.series.hist.centers:
                h = float(f.result(np.array([c]))[0])
                xs += [c - 0.5, c + 0.5]
                ys += [h, h]
            return xs, ys
        xs_all: list[float] = []
        ys_all: list[float] = []
        for a, b in lay.x.segments:
            a, b = max(a, lo), min(b, hi)
            if b <= a:
                continue
            xs = f.curve_x(a, b, lay.x.scale)
            if xs_all:
                xs_all.append(xs[0])
                ys_all.append(math.nan)
            xs_all += [float(v) for v in xs]
            ys_all += [float(v) for v in f.result(xs)]
        return xs_all, ys_all

    def _fit_box(self, f: ResolvedFit, size: float) -> VGroup:
        """A fit's parameters (± standard errors), R² and χ²/ν on a plate (empty for ``show:
        none``); placed later."""
        lines = f.lines()
        if not lines:
            return VGroup()
        return plot_draw.plate(plot_draw.text_lines(lines, size=size, theme=self.theme), theme=self.theme)

    def _side(self, legend: bool, fits: set[int], entries: list[list[Any]], boxes: list[VGroup], body: Region, size: float, portrait: bool,
              notes: list[VGroup]) -> VGroup:
        """What stands beside the figure: one legend of every entry (when a panel's legend
        found no free corner), the fit boxes and notes that found no free spot; a column (16:9)
        or above the figure (9:16; side by side when they fit), shrunk to fit."""
        items: list[Mobject] = []
        if legend:
            items.append(chart_legend([e[1:] for es in entries for e in es], body.width if portrait else body.width * 0.4, size=size, stack=not portrait))
        items += [boxes[j].copy() for j in sorted(fits)] + [n.copy() for n in notes]
        if not items:
            return VGroup()
        group = VGroup(*items)
        if portrait and sum(m.width for m in items) + 0.4 * (len(items) - 1) <= body.width:
            group.arrange(RIGHT, buff=0.4, aligned_edge=UP)   # side by side when they fit: the plot keeps its height
        else:
            group.arrange(DOWN, buff=0.3, aligned_edge=ORIGIN if portrait else LEFT)
        limit_w = body.width if portrait else body.width * 0.42
        limit_h = body.height * (0.45 if portrait else 1.0)
        factor = min(1.0, limit_w / group.width, limit_h / group.height)
        if factor < 1.0:
            group.scale(factor)
        return group

    def _draw_fit(self, f: ResolvedFit, lay: Any, color: str, box: VGroup) -> dict[str, Any]:
        xs, ys = self._curve_points(f, lay)
        curve = plot_draw.series_line(lay.frame_line(xs, ys), lay.plot, color, width=f.spec.width, dashed=f.spec.dashed).set_z_index(1)
        band = VGroup()
        if f.spec.band != "none":
            lo, hi = self._curve_range(f, lay)
            bx = f.curve_x(lo, hi, lay.x.scale)
            lower, upper = f.result.band(bx, level=f.spec.level, kind=f.spec.band)
            band = plot_draw.band(lay, list(bx), list(lower), list(upper), color, opacity=0.2)
        return {"curve": curve, "band": band, "box": box, "residual": None}

    def _draw_residuals(self, f: ResolvedFit, lay: Any, panel: Any, color: str, radius: float, shape: str) -> VGroup:
        xs, res, err = self._residuals(f)
        zero = plot_draw.reference_line(lay, y=0.0, color=self.theme.color("dim"), width=2.0)
        dots = plot_draw.series_markers(lay.frame_points(list(xs), list(res)), lay.plot, color, marker=shape if f.series.spec.drawn_as != "line" else "circle",
                                        radius=min(radius, 0.07), theme=self.theme).set_z_index(2)
        bars = plot_draw.error_bars(lay, list(xs), list(res), y_lo=list(err), y_hi=list(err), color=mix_colors(color, self.theme.background, 0.85),
                                    width=2.0, cap=0.07) if np.any(err > 0) else VGroup()
        return VGroup(panel.group, zero, bars, dots)

    # ----- annotations --------------------------------------------------------------------------

    def _draw_annotation(self, a: PlotAnnotation, lay: Any, series: list[ResolvedSeries], size: float, obstacles: np.ndarray, taken: list[Any],
                         radius: float) -> dict[str, Any]:
        color = self.theme.color(a.color or "highlight")
        text = str(a.text)
        label: Mobject = VGroup()
        if text:
            label = plot_draw.plate(plot_draw.label_text(text, size=size, theme=self.theme), theme=self.theme)
        dims = (label.width, label.height)
        mark: Mobject = VGroup()
        lead: Mobject = VGroup()
        box = None
        plot = lay.plot
        if a.type in ("label", "arrow"):
            if a.series is not None:
                s = next(r for r in series if str(r.spec.name) == a.series)
                x, y = series_point(s, a.x, a.index)
            else:
                x, y = float(a.x), float(a.y)
            if not (lay.x.contains(x) and lay.y.contains(y)):
                raise VidgenError(f"scene '{self.spec.id}': an annotation's point ({x:g}, {y:g}) lies outside the plot's axes")
            ax, ay = lay.frame_x(x), lay.frame_y(y)
            ring = Circle(radius=max(radius * 1.7, 0.12)).set_stroke(color, width=3).move_to([ax, ay, 0])
            mark = ring if a.type == "label" else VGroup()
            steps = (1.0, 2.2, 3.6) if a.type == "label" else (2.6, 3.8, 5.0)
            placed = plotcore.place_near((ax, ay), dims, plot, obstacles, taken, gap=max(radius * 1.7, 0.12) + 0.08, steps=steps)
            box = placed.box
            label.move_to([box.center[0], box.center[1], 0])
            edge = (min(max(ax, box.x0), box.x1), min(max(ay, box.y0), box.y1))
            if a.type == "arrow":
                lead = plot_draw.leader(edge, (ax, ay), color, arrow=True, buff=max(radius, 0.06) + 0.04)
            elif placed.leader:
                lead = plot_draw.leader(edge, (ax, ay), color, buff=max(radius * 1.7, 0.12))
        elif a.type in ("hline", "vline"):
            value = float(a.y if a.type == "hline" else a.x)
            axis = lay.y if a.type == "hline" else lay.x
            if not axis.contains(value):
                raise VidgenError(f"scene '{self.spec.id}': the {a.type} at {value:g} lies outside the axis ({axis.lo:g} to {axis.hi:g})")
            mark = plot_draw.reference_line(lay, x=None if a.type == "hline" else value, y=value if a.type == "hline" else None, color=color)
            if text:
                where = plotcore.place_on_hline(lay.frame_y(value), dims, plot, obstacles, taken) if a.type == "hline" else \
                    plotcore.place_on_vline(lay.frame_x(value), dims, plot, obstacles, taken)
                box = where.box
        else:   # xrange, yrange
            lo, hi = a.x if a.type == "xrange" else a.y
            vertical = a.type == "xrange"
            mark = plot_draw.span(lay, lo, hi, color, vertical=vertical)
            if text:
                f0, f1 = sorted((lay.frame_x(lo), lay.frame_x(hi))) if vertical else sorted((lay.frame_y(lo), lay.frame_y(hi)))
                box = plotcore.place_in_span(f0, f1, dims, plot, obstacles, taken, vertical=vertical).box
        if text and box is not None:
            label.move_to([box.center[0], box.center[1], 0])
            taken.append(box)
        return {"mark": mark, "label": label, "lead": lead, "box": box, "spec": a}


__all__ = ["TIGHT", "PlotFigure"]
