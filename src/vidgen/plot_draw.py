"""The drawing layer of the chart core (Phase W, DESIGN §97): manim objects for a laid-out
:class:`~vidgen.plotcore.PanelLayout` — axis lines with break marks, tick marks, gridlines
(dashed at labelled ticks, faint solid at a log axis' minor ticks), tick labels, axis titles —
and for data series (lines clipped to the plot, point markers). The layout itself is decided
by :mod:`vidgen.plotcore` without manim; this module only draws it. Exported by ``vidgen.api``
as the module ``plot_draw``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import numpy as np
from manim import NORMAL, DashedLine, Line, Text, VGroup, VMobject

from vidgen.charts import chart_label_size, chart_marker
from vidgen.helpers import resolve_color, styled
from vidgen.layout import fit_text
from vidgen.plotcore import BREAK_GAP, Measure, PanelLayout, Rect, clip_polyline
from vidgen.runtime import current_theme
from vidgen.theme import Theme

#: Length of a tick mark outside the plot (frame units); minor ticks are 60 % of it.
TICK_LENGTH = 0.08
#: Stroke widths: axis lines, tick marks, gridlines.
AXIS_STROKE, TICK_STROKE, GRID_STROKE = 2.0, 1.5, 1.0
#: Grid opacities: major (dashed, as the chart scenes) and minor (solid, a log axis' 2-9).
GRID_OPACITY, MINOR_OPACITY = 0.4, 0.16
Grid = Literal["major", "both", "x", "y", "none"]


def text_measure(size: str | float = "caption", theme: Theme | None = None, color: Any = "dim") -> Measure:
    """A :data:`~vidgen.plotcore.Measure` of chart labels at ``size`` (a theme token or points,
    never below the readable size), measured on the theme's font and cached per text."""
    theme = theme or current_theme()
    s = chart_label_size(size, theme)
    cache: dict[str, tuple[float, float]] = {}

    def measure(text: str) -> tuple[float, float]:
        if text not in cache:
            t = styled(Text, theme, text, s, color, NORMAL)
            cache[text] = (float(t.width), float(t.height))
        return cache[text]

    return measure


class PanelDrawing:
    """The manim parts of one panel: ``lines`` (axis lines), ``ticks`` (tick marks), ``grid``
    (major gridlines), ``minor`` (minor gridlines), ``breaks`` (break marks), ``x_labels`` /
    ``y_labels`` (``Text``), ``x_title`` / ``y_title`` (or ``None``) and ``group`` (all of them,
    gridlines first)."""

    def __init__(self) -> None:
        self.lines, self.ticks, self.grid, self.minor, self.breaks = VGroup(), VGroup(), VGroup(), VGroup(), VGroup()
        self.x_labels: list[Text] = []
        self.y_labels: list[Text] = []
        self.x_title: Any = None
        self.y_title: Any = None
        self.group = VGroup()


def draw_panel(
    lay: PanelLayout,
    *,
    size: str | float = "caption",
    color: Any = "text",
    axis_color: Any = "dim",
    grid: Grid = "major",
    theme: Theme | None = None,
) -> PanelDrawing:
    """Draw a laid-out panel: the left and bottom axis lines (cut at breaks, with ``//`` marks),
    outward tick marks at every major tick (shorter at minor ones), gridlines (``major``: both
    axes at labelled ticks, ``both``: also minor ones, ``x`` / ``y`` / ``none``), tick labels in
    ``color`` and axis titles. Nothing is added to a scene."""
    theme = theme or current_theme()
    s = chart_label_size(size, theme)
    dim = resolve_color(axis_color, theme)
    plot = lay.plot
    out = PanelDrawing()

    def dashed(a: Sequence[float], b: Sequence[float]) -> DashedLine:
        return DashedLine(np.array([*a, 0.0]), np.array([*b, 0.0]), color=dim, stroke_width=GRID_STROKE, stroke_opacity=GRID_OPACITY, dash_length=0.08)

    def faint(a: Sequence[float], b: Sequence[float]) -> Line:
        return Line(np.array([*a, 0.0]), np.array([*b, 0.0]), color=dim, stroke_width=GRID_STROKE * 0.8, stroke_opacity=MINOR_OPACITY)

    x_major = [lay.frame_x(t) for t in lay.x.ticks if lay.x.contains(t)]
    y_major = [lay.frame_y(t) for t in lay.y.ticks if lay.y.contains(t)]
    x_labelled = [lay.frame_x(lay.x.ticks[k]) for k in lay.x_kept] if lay.x_kept else x_major
    y_labelled = [lay.frame_y(lay.y.ticks[k]) for k in lay.y_kept] if lay.y_kept else y_major
    x_minor = [lay.frame_x(t) for t in lay.x.minor]
    y_minor = [lay.frame_y(t) for t in lay.y.minor]
    if grid in ("major", "both", "x"):
        out.grid.add(*[dashed((x, plot.y0), (x, plot.y1)) for x in x_labelled if abs(x - plot.x0) > 1e-6])
    if grid in ("major", "both", "y"):
        out.grid.add(*[dashed((plot.x0, y), (plot.x1, y)) for y in y_labelled if abs(y - plot.y0) > 1e-6])
    if grid == "both":
        out.minor.add(*[faint((x, plot.y0), (x, plot.y1)) for x in x_minor])
        out.minor.add(*[faint((plot.x0, y), (plot.x1, y)) for y in y_minor])

    for line in _axis_line(lay, "x") + _axis_line(lay, "y"):
        out.lines.add(Line(np.array([*line[0], 0.0]), np.array([*line[1], 0.0]), color=dim, stroke_width=AXIS_STROKE))
    for x in x_major:
        out.ticks.add(Line(np.array([x, plot.y0, 0.0]), np.array([x, plot.y0 - TICK_LENGTH, 0.0]), color=dim, stroke_width=TICK_STROKE))
    for y in y_major:
        out.ticks.add(Line(np.array([plot.x0, y, 0.0]), np.array([plot.x0 - TICK_LENGTH, y, 0.0]), color=dim, stroke_width=TICK_STROKE))
    for x in x_minor:
        out.ticks.add(Line(np.array([x, plot.y0, 0.0]), np.array([x, plot.y0 - TICK_LENGTH * 0.6, 0.0]), color=dim, stroke_width=TICK_STROKE * 0.8))
    for y in y_minor:
        out.ticks.add(Line(np.array([plot.x0, y, 0.0]), np.array([plot.x0 - TICK_LENGTH * 0.6, y, 0.0]), color=dim, stroke_width=TICK_STROKE * 0.8))
    out.breaks.add(*_break_marks(lay, dim))

    for lab in lay.x_labels:
        out.x_labels.append(styled(Text, theme, lab.text, s, color, NORMAL).move_to(np.array([lab.x, lab.y, 0.0])))
    for lab in lay.y_labels:
        t = styled(Text, theme, lab.text, s, color, NORMAL)
        out.y_labels.append(t.move_to(np.array([lab.x + lab.width / 2 - t.width / 2, lab.y, 0.0])))
    if lay.y_title is not None:
        t = fit_text(lay.y_title.text, lay.y_title.width + 0.05, size=s, color=color, align="left", theme=theme)
        out.y_title = t.move_to(np.array([lay.y_title.x - lay.y_title.width / 2 + t.width / 2, lay.y_title.y, 0.0]))
    if lay.x_title is not None:
        t = fit_text(lay.x_title.text, lay.x_title.width + 0.05, size=s, color=color, theme=theme)
        out.x_title = t.move_to(np.array([lay.x_title.x, lay.x_title.y, 0.0]))
    out.group.add(out.minor, out.grid, out.lines, out.ticks, out.breaks, *out.x_labels, *out.y_labels)
    out.group.add(*[t for t in (out.x_title, out.y_title) if t is not None])
    return out


def _axis_line(lay: PanelLayout, which: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """The pieces of the bottom (``x``) or left (``y``) axis line, cut at each break's gap."""
    axis = lay.x if which == "x" else lay.y
    plot = lay.plot
    cuts = sorted(axis.break_fractions())
    spans, start = [], 0.0
    for f in cuts:
        spans.append((start, f - BREAK_GAP * 0.3))
        start = f + BREAK_GAP * 0.3
    spans.append((start, 1.0))
    if which == "x":
        return [((plot.x0 + a * plot.width, plot.y0), (plot.x0 + b * plot.width, plot.y0)) for a, b in spans]
    return [((plot.x0, plot.y0 + a * plot.height), (plot.x0, plot.y0 + b * plot.height)) for a, b in spans]


def _break_marks(lay: PanelLayout, color: str) -> list[Line]:
    """Two short slanted strokes on each side of every break (``//``)."""
    out = []
    plot = lay.plot
    half = 0.09
    for which, axis in (("x", lay.x), ("y", lay.y)):
        for f in axis.break_fractions():
            for side in (-1, 1):
                if which == "x":
                    cx, cy = plot.x0 + (f + side * BREAK_GAP * 0.3) * plot.width, plot.y0
                    a, b = (cx - half * 0.5, cy - half), (cx + half * 0.5, cy + half)
                else:
                    cx, cy = plot.x0, plot.y0 + (f + side * BREAK_GAP * 0.3) * plot.height
                    a, b = (cx - half, cy - half * 0.5), (cx + half, cy + half * 0.5)
                out.append(Line(np.array([*a, 0.0]), np.array([*b, 0.0]), color=color, stroke_width=AXIS_STROKE))
    return out


def series_line(points: np.ndarray, plot: Rect, color: str, *, width: float = 4.0, dashed: bool = False) -> VGroup:
    """A data line through frame ``points`` (``nan`` rows leave a gap), clipped to ``plot``:
    one ``VMobject`` per visible run (a ``DashedVMobject`` when ``dashed``)."""
    from manim import DashedVMobject

    group = VGroup()
    for run in clip_polyline(points, plot):
        line = VMobject(stroke_color=color, stroke_width=width).set_points_as_corners(run)
        if dashed:
            length = float(np.sum(np.linalg.norm(np.diff(run[:, :2], axis=0), axis=1)))
            line = DashedVMobject(line, num_dashes=max(2, int(length / 0.18)), dashed_ratio=0.55)
        group.add(line)
    return group


def series_markers(points: np.ndarray, plot: Rect, color: str, *, marker: str = "circle", radius: float = 0.08, theme: Theme | None = None) -> VGroup:
    """Point markers (:func:`~vidgen.charts.chart_marker`) at the frame ``points`` inside
    ``plot``, with a thin outline in the background colour so overlapping markers stay apart."""
    theme = theme or current_theme()
    group = VGroup()
    for p in np.asarray(points, dtype=float):
        if np.isnan(p[:2]).any() or not plot.contains(p[0], p[1], 1e-6):
            continue
        m = chart_marker(marker, radius, color, fill_opacity=0.9, theme=theme)
        group.add(m.set_stroke(theme.background, width=1.2).move_to(np.array([p[0], p[1], 0.0])))
    return group


__all__ = ["AXIS_STROKE", "GRID_OPACITY", "MINOR_OPACITY", "TICK_LENGTH", "PanelDrawing", "draw_panel", "series_line", "series_markers", "text_measure"]
