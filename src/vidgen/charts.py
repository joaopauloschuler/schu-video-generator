"""Chart building blocks shared by the chart scenes (exported by ``vidgen.api``).

Numbers: :func:`axis_ticks` (round linear ticks, or decades for a log axis), :func:`short_number`
(``12k``, ``3.4M``) and :func:`tick_texts`. Axes: a :class:`ChartAxis` (domain, ticks, labels,
linear or log) from :func:`value_axis`, and :func:`chart_axes`, which lays out two axes in a
region (tick labels, axis titles, gridlines, axis lines) and maps data to points. Also a
legend (:func:`chart_legend`, auto-placed with :func:`legend_spot`), point markers
(:func:`chart_marker`), a least-squares line (:func:`linear_fit`), and the frame of a chart: its
title in the ``header`` region (:func:`chart_title`) and a caption (:func:`chart_caption`).
Colour: a :class:`ColorScale` from theme colours (:func:`color_scale`, sequential or diverging,
interpolated in OKLab), its legend (:func:`color_bar`), :func:`mix_colors` and
:func:`text_color_on` (text that stays readable on any fill).

Text sizes are theme size tokens (or points) and never go below :func:`chart_label_size`'s
readable floor, so labels grow with the theme's type scale (``large`` in 9:16) instead of
staying fixed. Every label is plain ``Text`` (no LaTeX).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

import numpy as np
from manim import BOLD, DOWN, LEFT, NORMAL, ORIGIN, PI, RIGHT, UP, Circle, DashedLine, Line, Paragraph, Rectangle, RoundedRectangle, Square, Text, Triangle, VGroup, VMobject

from vidgen.errors import VidgenError
from vidgen.helpers import resolve_color, styled
from vidgen.layout import auto_format, fit_text, format_value, nice_ticks
from vidgen.lint.color import TEXT_RATIO, _gamma, _linear, blend, contrast_ratio, hex_rgb, rgb_hex
from vidgen.regions import Region, orientation, place, readable_size, region
from vidgen.runtime import current_theme
from vidgen.theme import Theme

#: Marker shapes of :func:`chart_marker`.
CHART_MARKERS: tuple[str, ...] = ("circle", "square", "triangle", "diamond")
#: Space between a legend inside the plot and its frame (Manim units).
LEGEND_BUFF = 0.15
#: In a vertical frame a chart title grows by this factor (as ``bullets`` headings).
PORTRAIT_TITLE_GROWTH = 1.3
_SUFFIXES = ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k"))


# ----- numbers ---------------------------------------------------------------------------------


def axis_ticks(lo: float, hi: float, max_ticks: int = 6, *, log: bool = False) -> list[float]:
    """Round tick values covering ``lo..hi``: :func:`~vidgen.layout.nice_ticks` (steps of 1, 2,
    2.5 or 5 x 10^k), or with ``log`` powers of ten (every 2nd, 3rd... decade when there are
    more than ``max_ticks``; 1-2-5 steps when the range spans at most two decades).
    ``log`` needs ``lo > 0``."""
    if not log:
        return nice_ticks(lo, hi, max_ticks)
    if lo <= 0 or hi <= 0:
        raise VidgenError(f"a log axis needs positive values, got {lo:g}..{hi:g}")
    lo, hi = min(lo, hi), max(lo, hi)
    first, last = math.floor(math.log10(lo) + 1e-9), math.ceil(math.log10(hi) - 1e-9)
    last = max(last, first + 1)
    decades = last - first
    if decades <= 2:
        ticks = [m * 10.0**e for e in range(first, last + 1) for m in (1, 2, 5)]
        inside = [t for t in ticks if lo - 1e-12 <= t <= hi + 1e-12]
        below = [t for t in ticks if t < lo] or [ticks[0]]
        above = [t for t in ticks if t > hi] or [ticks[-1]]
        ticks = ([below[-1]] if not inside or inside[0] > lo * (1 + 1e-9) else []) + inside
        ticks += [above[0]] if ticks[-1] < hi * (1 - 1e-9) else []
        if len(ticks) <= max(2, max_ticks):
            return [_clean(t) for t in ticks]
    step = max(1, math.ceil(decades / max(1, max_ticks - 1)))
    first = math.floor(first / step) * step
    ticks = [10.0**e for e in range(first, last + step, step)]
    return [_clean(t) for t in ticks]


def _clean(value: float) -> float:
    """``value`` rounded to 12 significant digits (powers of ten without float noise)."""
    return float(f"{value:.12g}")


def short_number(value: float, decimals: int | None = None) -> str:
    """A compact number: ``1500`` -> ``1.5k``, ``2_000_000`` -> ``2M``, ``0.05`` -> ``0.05``
    (suffixes k, M, B, T). ``decimals`` fixes the decimals shown after scaling; by default as
    many as needed, up to 1 (suffixed) or 3."""
    v = float(value)
    for div, suffix in _SUFFIXES:
        if abs(v) >= div * (1 - 5e-13):
            text = f"{v / div:.{1 if decimals is None else decimals}f}"
            return (_strip(text) if decimals is None else text) + suffix
    if decimals is not None:
        return f"{v:.{decimals}f}"
    return _strip(f"{v:.3f}") if v != int(v) else str(int(v))


def _strip(text: str) -> str:
    return text.rstrip("0").rstrip(".") if "." in text else text


def tick_texts(ticks: Sequence[float], fmt: str | None = None, unit: str = "", *, log: bool = False) -> list[str]:
    """Labels for ``ticks``: ``fmt`` (a ``str.format`` pattern) if given; else on a log axis
    :func:`short_number`; else with one shared number of decimals
    (:func:`~vidgen.layout.auto_format`), switching to ``k``/``M``/``B`` suffixes from 10 000
    on. ``unit`` is appended to each."""
    if fmt:
        return [format_value(t, fmt, unit) for t in ticks]
    if log:
        return [short_number(t) + unit for t in ticks]
    top = max((abs(t) for t in ticks), default=0.0)
    for div, suffix in _SUFFIXES:
        if top >= 10_000 and top >= div:
            scaled = [t / div for t in ticks]
            pattern = auto_format(scaled).replace(",", "")
            return [(pattern.format(s) + suffix if s else "0") + unit for s in scaled]
    pattern = auto_format(ticks)
    return [format_value(t, pattern, unit) for t in ticks]


class LinearFit(NamedTuple):
    """A least-squares line ``y = slope * x + intercept`` and its coefficient of determination."""

    slope: float
    intercept: float
    r2: float

    def __call__(self, x: float) -> float:
        return self.slope * x + self.intercept

    def equation(self, digits: int = 3) -> str:
        """``"y = 0.52x + 1.3"`` with ``digits`` significant digits (typographic minus)."""
        def num(v: float) -> str:
            return f"{v:.{digits}g}".replace("-", "−")
        sign = "−" if self.intercept < 0 else "+"
        return f"y = {num(self.slope)}x {sign} {num(abs(self.intercept))}"


def linear_fit(xs: Sequence[float], ys: Sequence[float]) -> LinearFit:
    """Ordinary least squares through the points (``r2`` is 1.0 when every y is equal and the
    line passes through them). Needs at least two different x values."""
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if len(x) != len(y) or len(x) < 2 or np.ptp(x) == 0:
        raise VidgenError("a trend line needs at least two points with different x values")
    slope, intercept = np.polyfit(x, y, 1)
    residual = float(np.sum((y - (slope * x + intercept)) ** 2))
    total = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - residual / total if total > 0 else 1.0
    return LinearFit(float(slope), float(intercept), r2)


# ----- axes ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChartAxis:
    """One axis: its domain ``lo..hi``, the ``ticks`` with their ``labels``, linear or ``log``,
    and an optional ``title`` (e.g. ``"epoch"``)."""

    lo: float
    hi: float
    ticks: tuple[float, ...]
    labels: tuple[str, ...]
    log: bool = False
    title: str = ""

    def __post_init__(self) -> None:
        if len(self.ticks) != len(self.labels):
            raise VidgenError(f"an axis needs one label per tick, got {len(self.ticks)} ticks and {len(self.labels)} labels")
        if self.log and (self.lo <= 0 or self.hi <= 0):
            raise VidgenError(f"a log axis needs a positive domain, got {self.lo:g}..{self.hi:g}")

    def fraction(self, value: float) -> float:
        """Where ``value`` lies along the axis: 0 at ``lo``, 1 at ``hi`` (outside: beyond)."""
        if self.log:
            a, b = math.log10(self.lo), math.log10(self.hi)
            return (math.log10(max(value, 1e-300)) - a) / ((b - a) or 1.0)
        return (value - self.lo) / ((self.hi - self.lo) or 1.0)

    def contains(self, value: float) -> bool:
        """True when ``value`` lies in the domain."""
        return min(self.lo, self.hi) - 1e-9 <= value <= max(self.lo, self.hi) + 1e-9


def value_axis(
    values: Sequence[float],
    *,
    lo: float | None = None,
    hi: float | None = None,
    max_ticks: int = 6,
    log: bool = False,
    fmt: str | None = None,
    unit: str = "",
    title: str = "",
    include_zero: bool = False,
) -> ChartAxis:
    """A numeric axis covering ``values``: round ticks from :func:`axis_ticks`, the domain
    extended to the outer ticks unless ``lo``/``hi`` fix an end (ticks outside are dropped),
    labels from :func:`tick_texts`. ``include_zero`` keeps 0 in the domain (bars, counts)."""
    data = [float(v) for v in values]
    if lo is not None:
        data.append(lo)
    if hi is not None:
        data.append(hi)
    if not data:
        raise VidgenError("an axis needs at least one value")
    if log and min(data) <= 0:
        raise VidgenError("a log axis needs positive values (and a positive minimum)")
    d_lo = lo if lo is not None else min(data)
    d_hi = hi if hi is not None else max(data)
    if include_zero and not log:
        d_lo, d_hi = (min(d_lo, 0.0) if lo is None else d_lo), (max(d_hi, 0.0) if hi is None else d_hi)
    ticks = axis_ticks(d_lo, d_hi, max_ticks, log=log)
    if lo is not None:
        ticks = [t for t in ticks if t >= lo - 1e-9] or ticks
    if hi is not None:
        ticks = [t for t in ticks if t <= hi + 1e-9] or ticks
    a = lo if lo is not None else min(ticks[0], d_lo)
    b = hi if hi is not None else max(ticks[-1], d_hi)
    if b == a:
        b = a + 1.0
    return ChartAxis(a, b, tuple(ticks), tuple(tick_texts(ticks, fmt, unit, log=log)), log, title)


def chart_label_size(size: str | float = "caption", theme: Theme | None = None) -> float:
    """The font size of chart labels for a theme size token or points: never below
    :func:`~vidgen.regions.readable_size` (``vidgen lint``'s ``min_font``)."""
    theme = theme or current_theme()
    return max(float(theme.size(size)), readable_size(theme.font))


class ChartAxes:
    """Two axes laid out in a region by :func:`chart_axes`.

    Attributes: ``plot`` (the :class:`~vidgen.regions.Region` the data maps to), ``x``/``y``
    (the :class:`ChartAxis` objects), ``group`` (everything drawn, a ``VGroup``), and its parts
    ``lines`` (axis lines), ``grid`` (gridlines), ``x_labels``/``y_labels`` (the tick labels
    shown, ``Text``), ``x_title``/``y_title`` (or ``None``), ``label_size`` (points).
    """

    def __init__(self, plot: Region, x: ChartAxis, y: ChartAxis, label_size: float) -> None:
        self.plot, self.x, self.y, self.label_size = plot, x, y, label_size
        self.lines, self.grid = VGroup(), VGroup()
        self.x_labels: list[Text] = []
        self.y_labels: list[Text] = []
        self.x_title: Paragraph | None = None
        self.y_title: Paragraph | None = None
        self.group = VGroup()

    def x_pos(self, value: float) -> float:
        """Frame x of a data x value."""
        return self.plot.x0 + self.x.fraction(value) * self.plot.width

    def y_pos(self, value: float) -> float:
        """Frame y of a data y value."""
        return self.plot.y0 + self.y.fraction(value) * self.plot.height

    def point(self, x: float, y: float) -> np.ndarray:
        """The frame point ``[x, y, 0]`` of a data point."""
        return np.array([self.x_pos(x), self.y_pos(y), 0.0])

    def inside(self, x: float, y: float) -> bool:
        """True when the data point lies in both domains."""
        return self.x.contains(x) and self.y.contains(y)


def _stride(positions: Sequence[float], extents: Sequence[float], gap: float) -> list[int]:
    """Indices of labels to keep: every k-th (smallest k) so neighbours keep ``gap`` between
    them (``extents`` = their sizes along the axis); the last one too when it has room."""
    n = len(positions)
    if n <= 1:
        return list(range(n))

    def clear(i: int, j: int) -> bool:
        return abs(positions[j] - positions[i]) >= (extents[i] + extents[j]) / 2 + gap

    for k in range(1, n):
        kept = list(range(0, n, k))
        if all(clear(a, b) for a, b in zip(kept, kept[1:])):
            if kept[-1] != n - 1 and clear(kept[-1], n - 1):
                kept.append(n - 1)
            return kept
    return [0]


def chart_axes(
    area: Region,
    x: ChartAxis,
    y: ChartAxis,
    *,
    size: str | float = "caption",
    color: Any = "dim",
    axis_color: Any = "dim",
    grid: Literal["x", "y", "both", "none"] = "y",
    lines: Literal["x", "xy"] = "x",
    right: float = 0.0,
    top: float = 0.0,
    theme: Theme | None = None,
) -> ChartAxes:
    """Lay out two axes in ``area``: y tick labels on the left (the y title above them, left
    aligned), x tick labels below the plot (the x title under them, centred), dashed gridlines
    at the labelled ticks (``grid``), and the x axis line (``lines="xy"``: also the y axis
    line). ``right``/``top`` keep room free beside / above the plot (end labels, a legend).
    Labels that would collide are thinned to every k-th one. Text sizes use
    :func:`chart_label_size`; nothing is added to a scene."""
    theme = theme or current_theme()
    s = chart_label_size(size, theme)
    dim = resolve_color(axis_color, theme)

    def label(text: str) -> Text:
        return styled(Text, theme, text, s, color, NORMAL)

    y_texts = [label(t) for t in y.labels]
    x_texts = [label(t) for t in x.labels]
    y_title = fit_text(y.title, area.width * 0.7, size=s, color=color, align="left", theme=theme) if y.title else None
    x_title = fit_text(x.title, area.width * 0.9, size=s, color=color, theme=theme) if x.title else None
    tick_w = max((t.width for t in y_texts), default=0.0)
    x_h = max((t.height for t in x_texts), default=0.0)
    y_h = max((t.height for t in y_texts), default=0.0)
    cap = styled(Text, theme, "0", s, color, NORMAL).height
    gap = 0.45 * cap + 0.05

    plot_top = area.y1 - top - y_h / 2
    if y_title is not None:
        plot_top = area.y1 - top - y_title.height - gap - y_h / 2
    plot_bottom = area.y0 + x_h + gap + (x_title.height + gap * 0.8 if x_title is not None else 0.0)
    plot_left = area.x0 + tick_w + gap
    plot_right = area.x1 - right
    # an x label centred on the right end must not leave the area
    if x_texts and abs(x.fraction(x.ticks[-1]) - 1.0) < 1e-6:
        plot_right = min(plot_right, area.x1 - x_texts[-1].width / 2)
    plot = Region(plot_left, min(plot_bottom, plot_top - 0.5), max(plot_right, plot_left + 0.5), plot_top)
    axes = ChartAxes(plot, x, y, s)

    xs = [axes.x_pos(t) for t in x.ticks]
    ys = [axes.y_pos(t) for t in y.ticks]
    keep_x = _stride(xs, [t.width for t in x_texts], 0.35 * cap + 0.15)
    keep_y = _stride(ys, [t.height for t in y_texts], 0.9 * cap)
    for i in keep_y:
        t = y_texts[i]
        t.move_to([plot.x0 - gap - t.width / 2, ys[i], 0])
        axes.y_labels.append(t)
    for i in keep_x:
        t = x_texts[i]
        t.move_to([xs[i], plot.y0 - gap - x_h / 2, 0])
        axes.x_labels.append(t)
    if y_title is not None:
        y_title.move_to([area.x0 + y_title.width / 2, area.y1 - top - y_title.height / 2, 0])
        axes.y_title = y_title
    if x_title is not None:
        x_title.move_to([plot.center[0], plot.y0 - gap - x_h - gap * 0.8 - x_title.height / 2, 0])
        x_title.set_x(min(max(x_title.get_x(), area.x0 + x_title.width / 2), area.x1 - x_title.width / 2))
        axes.x_title = x_title

    def dashed(a: np.ndarray, b: np.ndarray) -> DashedLine:
        return DashedLine(a, b, color=dim, stroke_width=1, stroke_opacity=0.4, dash_length=0.08)

    if grid in ("y", "both"):
        for i in keep_y:
            if abs(ys[i] - plot.y0) > 1e-6:
                axes.grid.add(dashed(np.array([plot.x0, ys[i], 0]), np.array([plot.x1, ys[i], 0])))
    if grid in ("x", "both"):
        for i in keep_x:
            if abs(xs[i] - plot.x0) > 1e-6 or lines == "x":
                axes.grid.add(dashed(np.array([xs[i], plot.y0, 0]), np.array([xs[i], plot.y1, 0])))
    axes.lines.add(Line([plot.x0, plot.y0, 0], [plot.x1, plot.y0, 0], color=dim, stroke_width=2))
    if lines == "xy":
        axes.lines.add(Line([plot.x0, plot.y0, 0], [plot.x0, plot.y1, 0], color=dim, stroke_width=2))
    axes.group.add(axes.grid, axes.lines, *axes.y_labels, *axes.x_labels)
    axes.group.add(*[t for t in (axes.y_title, axes.x_title) if t is not None])
    return axes


# ----- legend and markers ----------------------------------------------------------------------


def chart_marker(kind: str, radius: float, color: Any, *, fill_opacity: float = 1.0, theme: Theme | None = None) -> VMobject:
    """A filled point marker of about ``radius`` (Manim units): ``circle``, ``square``,
    ``triangle`` or ``diamond`` (shapes of similar visual weight, for series that must stay
    apart without colour)."""
    c = resolve_color(color, theme)
    if kind == "circle":
        mob: VMobject = Circle(radius=radius)
    elif kind == "square":
        mob = Square(side_length=radius * 1.7)
    elif kind == "triangle":
        mob = Triangle().scale_to_fit_height(radius * 1.95)
    elif kind == "diamond":
        mob = Square(side_length=radius * 1.6).rotate(PI / 4)
    else:
        raise VidgenError(f"unknown marker {kind!r}; use one of: {', '.join(CHART_MARKERS)}")
    return mob.set_fill(c, opacity=fill_opacity).set_stroke(c, width=0)


def chart_legend(
    entries: Sequence[tuple[str, Any, str]],
    max_width: float,
    *,
    size: str | float = "caption",
    color: Any = "text",
    stack: bool = False,
    theme: Theme | None = None,
) -> VGroup:
    """A legend: per ``(name, color, swatch)`` entry a swatch and the name, wrapped into rows
    that fit ``max_width`` (``stack``: one entry per row; shrunk if one entry alone is wider).
    ``swatch`` is ``line``, ``box`` or a marker shape (:data:`CHART_MARKERS`). Rows are
    ``VGroup`` s of items, items ``VGroup(swatch, name)``."""
    theme = theme or current_theme()
    s = chart_label_size(size, theme)
    h = styled(Text, theme, "H", s, color, NORMAL).height
    items = []
    for name, c, swatch in entries:
        if swatch == "line":
            mark: VMobject = Line([0, 0, 0], [h * 2.2, 0, 0], color=resolve_color(c, theme), stroke_width=4)
        elif swatch == "box":
            mark = Square(side_length=h * 1.1).set_fill(resolve_color(c, theme), opacity=0.9).set_stroke(width=0)
        else:
            mark = chart_marker(swatch, h * 0.5, c, theme=theme)
        items.append(VGroup(mark, styled(Text, theme, name, s, color, NORMAL)).arrange(RIGHT, buff=h * 0.5))
    gap = h * 1.6
    rows, row, width = VGroup(), VGroup(), 0.0
    for item in items:
        if len(row) and (stack or width + gap + item.width > max_width):
            rows.add(row.arrange(RIGHT, buff=gap))
            row, width = VGroup(), 0.0
        width += item.width + (gap if len(row) else 0.0)
        row.add(item)
    if len(row):
        rows.add(row.arrange(RIGHT, buff=gap))
    rows.arrange(DOWN, buff=h * 0.7, aligned_edge=LEFT)
    if rows.width > max_width:
        rows.scale(max_width / rows.width)
    return rows


def legend_spot(
    size: tuple[float, float],
    plot: Region,
    points: Sequence[Sequence[float]] | np.ndarray,
    *,
    pad: float = 0.15,
    corners: Sequence[str] = ("top_right", "top_left", "bottom_right", "bottom_left"),
) -> np.ndarray | None:
    """Where a legend of ``size`` (width, height) can stand inside ``plot`` without covering
    data: the centre of the first of ``corners`` whose box (``pad`` inside the plot, ``pad``
    of air around it) contains none of ``points`` (frame points of the data: markers, samples
    along lines); ``None`` when every corner is taken (put the legend above the plot)."""
    w, h = size
    if w + 2 * pad > plot.width or h + 2 * pad > plot.height:
        return None
    pts = np.asarray(points, dtype=float)
    pts = pts.reshape(len(pts), -1)[:, :2] if pts.size else np.zeros((0, 2))
    inner = plot.inset(pad)
    for corner in corners:
        cx, cy = inner.point(corner)[:2]
        cx -= np.sign(cx - inner.center[0]) * w / 2
        cy -= np.sign(cy - inner.center[1]) * h / 2
        x0, x1, y0, y1 = cx - w / 2 - pad, cx + w / 2 + pad, cy - h / 2 - pad, cy + h / 2 + pad
        if not len(pts) or not np.any((pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1)):
            return np.array([cx, cy, 0.0])
    return None


def auto_legend(
    entries: Sequence[tuple[str, Any, str]],
    plot: Region,
    points: Sequence[Sequence[float]] | np.ndarray,
    max_width: float,
    *,
    size: str | float = "caption",
    color: Any = "text",
    theme: Theme | None = None,
) -> tuple[VGroup, np.ndarray | None]:
    """A :func:`chart_legend` placed where it covers no data: in a free corner of ``plot`` as
    one row, else stacked (one entry per row), framed by a faint rounded box on the background
    colour (so its swatches do not read as data) and drawn over the gridlines (``z_index``
    1); returns ``(legend, centre)``, already moved there. When no corner is free: ``(legend wrapped to max_width, None)``, unframed and not
    moved, for the caller to put above the plot (making room for it)."""
    theme = theme or current_theme()
    wide = chart_legend(entries, max_width, size=size, color=color, theme=theme)
    for legend in (wide, chart_legend(entries, max_width, size=size, color=color, stack=True, theme=theme)):
        buff = LEGEND_BUFF
        spot = legend_spot((legend.width + 2 * buff, legend.height + 2 * buff), plot, points)
        if spot is not None:
            box = RoundedRectangle(width=legend.width + 2 * buff, height=legend.height + 2 * buff, corner_radius=0.08)
            box.set_fill(theme.background, opacity=0.85).set_stroke(resolve_color("dim", theme), width=1, opacity=0.5)
            return VGroup(box, legend.move_to(box)).move_to(spot).set_z_index(1), spot   # over the gridlines
    return wide, None


def sample_path(points: Sequence[np.ndarray], step: float = 0.1) -> np.ndarray:
    """Points every ``step`` units along a polyline (for :func:`legend_spot` to avoid lines)."""
    out = []
    for a, b in zip(points, points[1:]):
        a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        n = max(1, int(np.linalg.norm(b - a) / step))
        out.extend(a + (b - a) * k / n for k in range(n))
    if len(points):
        out.append(np.asarray(points[-1], dtype=float))
    return np.array(out).reshape(-1, 3) if out else np.zeros((0, 3))


# ----- colour scales ---------------------------------------------------------------------------


def _oklab(color: str) -> np.ndarray:
    """An sRGB hex colour in OKLab (Ottosson 2020): perceptually even lightness and hue."""
    r, g, b = (_linear(c) for c in hex_rgb(color))
    lms = np.cbrt(np.array([
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    ]))
    return np.array([
        0.2104542553 * lms[0] + 0.7936177850 * lms[1] - 0.0040720468 * lms[2],
        1.9779984951 * lms[0] - 2.4285922050 * lms[1] + 0.4505937099 * lms[2],
        0.0259040371 * lms[0] + 0.7827717662 * lms[1] - 0.8086757660 * lms[2],
    ])


def _from_oklab(lab: np.ndarray) -> str:
    l_, m_, s_ = (
        lab[0] + 0.3963377774 * lab[1] + 0.2158037573 * lab[2],
        lab[0] - 0.1055613458 * lab[1] - 0.0638541728 * lab[2],
        lab[0] - 0.0894841775 * lab[1] - 1.2914855480 * lab[2],
    )
    l3, m3, s3 = l_**3, m_**3, s_**3
    rgb = (
        4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
        -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
        -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3,
    )
    return rgb_hex(tuple(_gamma(c) for c in rgb))  # type: ignore[arg-type]


def mix_colors(a: Any, b: Any, t: float, *, theme: Theme | None = None) -> str:
    """``a`` drawn at opacity ``t`` over ``b`` (theme tokens or hex), as the viewer sees it
    (``#RRGGBB``): e.g. what a cell faded to 30 % looks like on the background."""
    theme = theme or current_theme()
    return rgb_hex(blend(hex_rgb(resolve_color(a, theme)), hex_rgb(resolve_color(b, theme)), t))


def text_color_on(fill: Any, *, min_ratio: float = TEXT_RATIO, theme: Theme | None = None) -> str:
    """The colour to write on a ``fill`` (theme token or hex) so the text stays readable: the
    theme's ``text`` or its background, whichever contrasts more; if neither reaches
    ``min_ratio`` (WCAG 4.5:1, what ``vidgen lint`` checks), white or black."""
    theme = theme or current_theme()
    behind = hex_rgb(resolve_color(fill, theme))

    def ratio(c: str) -> float:
        return contrast_ratio(hex_rgb(c), behind)

    best = max((theme.color("text"), theme.background), key=ratio)
    return best if ratio(best) >= min_ratio else max(("#FFFFFF", "#000000"), key=ratio)


def plate_contrast(color: Any, plate: Any, opacity: float = 1.0, *, theme: Theme | None = None) -> float:
    """The WCAG contrast ratio text in ``color`` keeps on a ``plate`` (theme tokens or hex)
    drawn at ``opacity`` over *anything*: the lower of the plate over black and over white
    (a caption plate over a picture)."""
    theme = theme or current_theme()
    text = hex_rgb(resolve_color(color, theme))
    fill = hex_rgb(resolve_color(plate, theme))
    return min(contrast_ratio(text, blend(fill, under, opacity)) for under in ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))


@dataclass(frozen=True)
class ColorScale:
    """Values ``lo..hi`` mapped to colours: ``scale(v)`` gives the ``#RRGGBB`` of a value,
    interpolated in OKLab between ``stops`` (``(fraction, colour)`` pairs from 0 to 1), so equal
    steps in value look like equal steps in colour. ``kind`` is ``sequential`` or
    ``diverging`` (then ``center`` is the neutral middle). Values outside are clamped."""

    lo: float
    hi: float
    stops: tuple[tuple[float, str], ...]
    kind: str = "sequential"
    center: float | None = None

    def fraction(self, value: float) -> float:
        """Where ``value`` lies on the scale (0..1, clamped)."""
        if self.kind == "diverging" and self.center is not None:
            c = self.center
            if value >= c:
                return 0.5 + 0.5 * min((value - c) / ((self.hi - c) or 1.0), 1.0)
            return 0.5 - 0.5 * min((c - value) / ((c - self.lo) or 1.0), 1.0)
        return min(max((value - self.lo) / ((self.hi - self.lo) or 1.0), 0.0), 1.0)

    def at(self, fraction: float) -> str:
        """The colour at a position ``0..1`` of the scale."""
        f = min(max(fraction, 0.0), 1.0)
        for (f0, c0), (f1, c1) in zip(self.stops, self.stops[1:]):
            if f <= f1 or f1 >= 1.0:
                t = (f - f0) / ((f1 - f0) or 1.0)
                return _from_oklab(_oklab(c0) * (1 - t) + _oklab(c1) * t)
        return self.stops[-1][1]

    def __call__(self, value: float) -> str:
        return self.at(self.fraction(value))


def color_scale(
    values: Sequence[float],
    *,
    kind: Literal["sequential", "diverging"] = "sequential",
    color: Any = "primary",
    low_color: Any = "primary",
    high_color: Any = "accent",
    center: float = 0.0,
    lo: float | None = None,
    hi: float | None = None,
    theme: Theme | None = None,
) -> ColorScale:
    """A :class:`ColorScale` for ``values`` made from theme colours. ``sequential``: from a
    faint tint of ``color`` on the background (low) to ``color`` itself (high), so larger values
    stand out more on any background (lighter on dark themes, darker on light ones).
    ``diverging``: ``low_color`` below ``center``, a near-background neutral at it,
    ``high_color`` above; the domain is symmetric around ``center`` (equal distances look
    equally strong) unless ``lo``/``hi`` fix an end."""
    theme = theme or current_theme()
    data = [float(v) for v in values]
    if not data and (lo is None or hi is None):
        raise VidgenError("a colour scale needs values or both ends (lo, hi)")
    a = lo if lo is not None else min(data)
    b = hi if hi is not None else max(data)
    bg = theme.background
    if kind == "diverging":
        reach = max(abs(center - a), abs(b - center)) or 1.0
        a = lo if lo is not None else center - reach
        b = hi if hi is not None else center + reach
        if not a < center < b:
            raise VidgenError(f"a diverging scale needs its center {center:g} inside {a:g}..{b:g}")
        neutral = mix_colors("text", bg, 0.1, theme=theme)
        stops = ((0.0, resolve_color(low_color, theme)), (0.5, neutral), (1.0, resolve_color(high_color, theme)))
        return ColorScale(a, b, stops, "diverging", center)
    if b <= a:
        b = a + 1.0
    full = resolve_color(color, theme)
    return ColorScale(a, b, ((0.0, mix_colors(full, bg, 0.14, theme=theme)), (1.0, full)))


def color_bar(
    scale: ColorScale,
    length: float,
    *,
    vertical: bool = True,
    thickness: float = 0.26,
    size: str | float = "caption",
    color: Any = "dim",
    title: str = "",
    max_ticks: int = 5,
    fmt: str | None = None,
    unit: str = "",
    theme: Theme | None = None,
) -> VGroup:
    """A colour-scale legend: a gradient bar ``length`` units long (low at the bottom / left)
    with round ticks and their labels (right of a vertical bar, below a horizontal one) and an
    optional ``title`` above. Returns ``VGroup(bar, ticks, labels, title?)``, centred at the
    origin; labels never go below the readable size."""
    theme = theme or current_theme()
    s = chart_label_size(size, theme)
    steps = 48
    bar = VGroup()
    piece = length / steps
    for k in range(steps):
        rect = Rectangle(width=thickness, height=piece * 1.02) if vertical else Rectangle(width=piece * 1.02, height=thickness)
        rect.set_fill(scale.at((k + 0.5) / steps), opacity=1).set_stroke(width=0)
        offset = -length / 2 + piece * (k + 0.5)
        bar.add(rect.move_to([0, offset, 0] if vertical else [offset, 0, 0]))
    frame = Rectangle(width=thickness, height=length) if vertical else Rectangle(width=length, height=thickness)
    bar.add(frame.set_fill(opacity=0).set_stroke(resolve_color(color, theme), width=1, opacity=0.6))
    values = [t for t in axis_ticks(scale.lo, scale.hi, max_ticks) if scale.lo - 1e-9 <= t <= scale.hi + 1e-9]
    texts = tick_texts(values, fmt, unit)
    ticks, labels = VGroup(), VGroup()
    dim = resolve_color(color, theme)
    for v, label in zip(values, texts):
        pos = -length / 2 + scale.fraction(v) * length
        text = styled(Text, theme, label, s, "text", NORMAL)
        if vertical:
            ticks.add(Line([thickness / 2, pos, 0], [thickness / 2 + 0.1, pos, 0], color=dim, stroke_width=2))
            labels.add(text.move_to([thickness / 2 + 0.18 + text.width / 2, pos, 0]))
        else:
            ticks.add(Line([pos, -thickness / 2, 0], [pos, -thickness / 2 - 0.1, 0], color=dim, stroke_width=2))
            labels.add(text.move_to([pos, -thickness / 2 - 0.18 - text.height / 2, 0]))
    if vertical and len(labels) > 1:   # thin labels that would touch
        keep = _stride([m.get_y() for m in labels], [m.height for m in labels], 0.5 * labels[0].height)
    else:
        keep = _stride([m.get_x() for m in labels], [m.width for m in labels], 0.3) if len(labels) > 1 else list(range(len(labels)))
    ticks = VGroup(*[ticks[i] for i in keep])
    labels = VGroup(*[labels[i] for i in keep])
    group = VGroup(bar, ticks, labels)
    if title:
        head = fit_text(title, max(length, 1.5) if not vertical else max(2.2, labels.width + thickness + 0.3), size=s, color=color, theme=theme)
        head.next_to(VGroup(bar, labels) if not vertical else bar, UP, buff=0.2)
        if vertical:
            head.align_to(bar, LEFT)
        group.add(head)
    return group.move_to(ORIGIN)


# ----- title and caption -----------------------------------------------------------------------


def chart_title(
    text: str,
    *,
    size: str | float = "heading",
    color: Any = "text",
    growth: float | None = None,
    area: Region | None = None,
    theme: Theme | None = None,
) -> Paragraph:
    """A chart title fitted into and centred in the ``header`` region of ``area`` (default:
    the safe area), bold, in the theme's ``heading`` font role, ``growth`` x larger in a
    portrait frame (default :data:`PORTRAIT_TITLE_GROWTH`), like ``bullets`` headings. Place
    the chart below it: ``body = area.below(title, gap=0.45)``."""
    theme = theme or current_theme()
    header = region("header", area)
    grow = (PORTRAIT_TITLE_GROWTH if growth is None else growth) if orientation() == "portrait" else 1.0
    title = fit_text(text, header.width, header.height, size=float(theme.size(size)) * grow, color=color, weight=BOLD, role="heading", theme=theme, balance=True)
    return place(title, header, fit="none", align="center")


def chart_caption(text: str, area: Region, *, size: str | float = "caption", color: Any = "dim", theme: Theme | None = None) -> Paragraph:
    """A caption (e.g. the data source) wrapped to ``area``'s width (at most 15 % of its
    height) and placed at its bottom. Continue with ``area.above(caption, gap=0.3)``."""
    theme = theme or current_theme()
    caption = fit_text(text, area.width, area.height * 0.15, size=size, color=color, theme=theme)
    return place(caption, area, fit="none", align="bottom")


__all__ = [
    "CHART_MARKERS",
    "ChartAxes",
    "ChartAxis",
    "ColorScale",
    "LinearFit",
    "axis_ticks",
    "auto_legend",
    "chart_axes",
    "chart_caption",
    "chart_label_size",
    "chart_legend",
    "chart_marker",
    "chart_title",
    "color_bar",
    "color_scale",
    "legend_spot",
    "linear_fit",
    "mix_colors",
    "sample_path",
    "short_number",
    "text_color_on",
    "tick_texts",
    "value_axis",
]
