"""The drawing layer of the chart core (Phase W, DESIGN §97): manim objects for a laid-out
:class:`~vidgen.plotcore.PanelLayout` — axis lines with break marks, tick marks, gridlines
(dashed at labelled ticks, faint solid at a log axis' minor ticks), tick labels, axis titles —
and for data (lines clipped to the plot, point markers, error bars, shaded bands, histogram
bars) and annotations (reference lines, shaded ranges, text on plates, leaders and arrows). The layout itself is decided
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


def _segment(a: Sequence[float], b: Sequence[float], plot: Rect) -> np.ndarray | None:
    """The part of the segment a-b inside ``plot`` (``(2, 3)`` frame points) or ``None``."""
    runs = clip_polyline(np.array([[a[0], a[1], 0.0], [b[0], b[1], 0.0]]), plot)
    return runs[0] if runs else None


def error_bars(
    lay: PanelLayout,
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    y_lo: Sequence[float] | None = None,
    y_hi: Sequence[float] | None = None,
    x_lo: Sequence[float] | None = None,
    x_hi: Sequence[float] | None = None,
    color: str = "#888888",
    width: float = 2.5,
    cap: float = 0.07,
) -> VGroup:
    """Error bars at data points: from ``y - y_lo`` to ``y + y_hi`` (and ``x - x_lo`` to ``x +
    x_hi``), lengths in data units (asymmetric when the two differ), clipped to the plot, with
    caps ``cap`` units wide where a bar ends inside it. On a log axis a bar reaching 0 or below
    runs to the plot's edge."""
    plot = lay.plot
    group = VGroup()

    def stroke(seg: np.ndarray) -> Line:
        return Line(seg[0], seg[1], color=color, stroke_width=width)

    for k, (x, y) in enumerate(zip(xs, ys)):
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        fx, fy = lay.frame_x(x), lay.frame_y(y)
        if y_lo is not None and y_hi is not None and (y_lo[k] > 0 or y_hi[k] > 0):
            low, high = y - y_lo[k], y + y_hi[k]
            a = (fx, lay.frame_y(low) if (lay.y.scale != "log" or low > 0) else plot.y0 - 1.0)
            b = (fx, lay.frame_y(high))
            seg = _segment(a, b, plot)
            if seg is not None:
                group.add(stroke(seg))
                for end in (a, b):
                    if plot.contains(end[0], end[1], 1e-6):
                        group.add(Line(np.array([fx - cap / 2, end[1], 0.0]), np.array([fx + cap / 2, end[1], 0.0]), color=color, stroke_width=width))
        if x_lo is not None and x_hi is not None and (x_lo[k] > 0 or x_hi[k] > 0):
            low, high = x - x_lo[k], x + x_hi[k]
            a = (lay.frame_x(low) if (lay.x.scale != "log" or low > 0) else plot.x0 - 1.0, fy)
            b = (lay.frame_x(high), fy)
            seg = _segment(a, b, plot)
            if seg is not None:
                group.add(stroke(seg))
                for end in (a, b):
                    if plot.contains(end[0], end[1], 1e-6):
                        group.add(Line(np.array([end[0], fy - cap / 2, 0.0]), np.array([end[0], fy + cap / 2, 0.0]), color=color, stroke_width=width))
    return group


def band(lay: PanelLayout, xs: Sequence[float], lower: Sequence[float], upper: Sequence[float], color: str, *, opacity: float = 0.2) -> VGroup:
    """A shaded band between ``lower`` and ``upper`` (data values at ``xs``, increasing),
    clipped to the plot (heights held at its top and bottom), one polygon per piece of the x
    axis between breaks and per run of finite values."""
    from manim import Polygon

    plot = lay.plot
    group = VGroup()
    runs: list[list[tuple[float, float, float]]] = []
    current: list[tuple[float, float, float]] = []
    last_piece = None
    for x, lo, hi in zip(xs, lower, upper):
        ok = np.isfinite(x) and np.isfinite(lo) and np.isfinite(hi) and lay.x.contains(x)
        piece = lay.x.piece(x) if ok else None
        if not ok or (last_piece is not None and piece != last_piece):
            if len(current) >= 2:
                runs.append(current)
            current = []
        if ok:
            fx = min(max(lay.frame_x(x), plot.x0), plot.x1)
            f_lo = plot.y0 - 1.0 if (lay.y.scale == "log" and lo <= 0) else lay.frame_y(lo)
            f_hi = lay.frame_y(hi)
            clamp = (lambda v: min(max(v, plot.y0), plot.y1))
            current.append((fx, clamp(min(f_lo, f_hi)), clamp(max(f_lo, f_hi))))
            last_piece = piece
    if len(current) >= 2:
        runs.append(current)
    for run in runs:
        top = [np.array([x, hi, 0.0]) for x, _, hi in run]
        bottom = [np.array([x, lo, 0.0]) for x, lo, _ in reversed(run)]
        group.add(Polygon(*top, *bottom).set_fill(color, opacity=opacity).set_stroke(width=0))
    return group


def bars(lay: PanelLayout, edges: Sequence[float], heights: Sequence[float], color: str, *, opacity: float = 0.55, outline: bool = True, theme: Theme | None = None) -> VGroup:
    """Histogram bars from the axis' base (0, or the bottom of a log axis) to ``heights``
    between ``edges``, clipped to the plot; filled at ``opacity`` (0: an outline only, the
    ``step`` style) with an outline in ``color``. One ``Polygon`` per bar, left to right."""
    from manim import Polygon

    theme = theme or current_theme()
    plot = lay.plot
    group = VGroup()
    base = plot.y0 if lay.y.scale == "log" or not lay.y.contains(0.0) else lay.frame_y(0.0)
    for a, b, h in zip(edges, edges[1:], heights):
        x0 = min(max(lay.frame_x(a), plot.x0), plot.x1)
        x1 = min(max(lay.frame_x(b), plot.x0), plot.x1)
        if x1 - x0 <= 1e-9:
            continue
        top = plot.y0 if (lay.y.scale == "log" and h <= 0) else min(max(lay.frame_y(h), plot.y0), plot.y1)
        rect = Polygon(np.array([x0, base, 0.0]), np.array([x1, base, 0.0]), np.array([x1, top, 0.0]), np.array([x0, top, 0.0]))
        rect.set_fill(color, opacity=opacity)
        rect.set_stroke(color if outline else theme.background, width=2.0 if opacity == 0 else 1.2, opacity=1.0)
        group.add(rect)
    return group


def label_text(text: str, *, size: str | float = "caption", color: Any = "text", theme: Theme | None = None) -> Text:
    """One line of chart text in the theme font at ``size`` (never below the readable size)."""
    theme = theme or current_theme()
    return styled(Text, theme, text, chart_label_size(size, theme), color, NORMAL)


def text_lines(lines: Sequence[str], *, size: str | float = "caption", color: Any = "text", theme: Theme | None = None) -> VGroup:
    """Lines of plain text, left-aligned under one another (a fit's parameters, a note)."""
    from manim import DOWN, LEFT

    theme = theme or current_theme()
    s = chart_label_size(size, theme)
    group = VGroup(*[styled(Text, theme, line, s, color, NORMAL) for line in lines])
    return group.arrange(DOWN, buff=0.12 * s / 24, aligned_edge=LEFT) if len(group) > 1 else group


#: Inner padding of a text plate (frame units).
PLATE_PAD = 0.12


def plate(content: VMobject, *, color: Any = "dim", theme: Theme | None = None) -> VGroup:
    """``content`` on a faint rounded plate in the background colour (so text reads over
    gridlines and data), drawn above the plot's lines; ``VGroup(plate, content)``."""
    from manim import RoundedRectangle

    theme = theme or current_theme()
    box = RoundedRectangle(width=content.width + 2 * PLATE_PAD, height=content.height + 2 * PLATE_PAD, corner_radius=0.08)
    box.set_fill(theme.background, opacity=0.88).set_stroke(resolve_color(color, theme), width=1, opacity=0.5)
    box.move_to(content.get_center())
    return VGroup(box, content).set_z_index(3)


def reference_line(lay: PanelLayout, *, x: float | None = None, y: float | None = None, color: str = "#888888", width: float = 2.5, dashed: bool = True) -> VGroup:
    """A line across the plot at data ``x`` (vertical) or ``y`` (horizontal), dashed by
    default; empty when the value lies outside the axis."""
    plot = lay.plot
    group = VGroup()
    if y is not None and lay.y.contains(y):
        fy = lay.frame_y(y)
        a, b = np.array([plot.x0, fy, 0.0]), np.array([plot.x1, fy, 0.0])
    elif x is not None and lay.x.contains(x):
        fx = lay.frame_x(x)
        a, b = np.array([fx, plot.y0, 0.0]), np.array([fx, plot.y1, 0.0])
    else:
        return group
    line = DashedLine(a, b, color=color, stroke_width=width, dash_length=0.14, dashed_ratio=0.55) if dashed else Line(a, b, color=color, stroke_width=width)
    return group.add(line)


def span(lay: PanelLayout, lo: float, hi: float, color: str, *, vertical: bool = True, opacity: float = 0.14) -> VGroup:
    """A shaded range across the plot: x from ``lo`` to ``hi`` (``vertical``) or y, clipped."""
    from manim import Polygon

    plot = lay.plot
    if vertical:
        a, b = sorted((lay.frame_x(lo), lay.frame_x(hi)))
        a, b = max(a, plot.x0), min(b, plot.x1)
        corners = ((a, plot.y0), (b, plot.y0), (b, plot.y1), (a, plot.y1))
    else:
        a, b = sorted((lay.frame_y(lo), lay.frame_y(hi)))
        a, b = max(a, plot.y0), min(b, plot.y1)
        corners = ((plot.x0, a), (plot.x1, a), (plot.x1, b), (plot.x0, b))
    if b - a <= 1e-9:
        return VGroup()
    return VGroup(Polygon(*[np.array([cx, cy, 0.0]) for cx, cy in corners]).set_fill(color, opacity=opacity).set_stroke(width=0))


def leader(start: Sequence[float], end: Sequence[float], color: str, *, arrow: bool = False, width: float = 2.5, buff: float = 0.08) -> VMobject:
    """A thin line from a label (``start``) to the point it names (``end``), stopping ``buff``
    short of it; with ``arrow`` a small arrowhead at the point."""
    from manim import Arrow

    a, b = np.array([*start[:2], 0.0]), np.array([*end[:2], 0.0])
    length = float(np.linalg.norm(b - a))
    if length <= buff * 2:
        return VGroup()
    b2 = a + (b - a) * (length - buff) / length
    if arrow:
        return Arrow(a, b2, buff=0, color=color, stroke_width=width + 0.5, max_tip_length_to_length_ratio=0.5, tip_length=0.16)
    return Line(a, b2, color=color, stroke_width=width)


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


__all__ = [
    "AXIS_STROKE",
    "GRID_OPACITY",
    "MINOR_OPACITY",
    "PLATE_PAD",
    "TICK_LENGTH",
    "PanelDrawing",
    "band",
    "bars",
    "draw_panel",
    "error_bars",
    "label_text",
    "leader",
    "plate",
    "reference_line",
    "series_line",
    "series_markers",
    "span",
    "text_lines",
    "text_measure",
]
