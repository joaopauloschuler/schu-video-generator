"""The layout of a figure of one or more plot panels in a frame region, in frame units, without
drawing: where each plot area, tick label and axis title goes. Text is measured by a callback
(the drawing layer passes one that measures real text; tests pass :func:`approx_measure`), so
the same inputs always give the same layout.

Style (the chart scenes' style, §33): y tick labels right-aligned left of the plot, the y title
above them, left-aligned (horizontal text, readable on phones), x tick labels under the plot and
the x title under them, centred. Labels that would touch are thinned to every k-th one. Panels
stacked in ``rows`` share their x axis (only the lowest shows its labels); panels side by side in
``columns`` share their y axis (only the first shows its labels); shared plots line up."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import numpy as np

from vidgen.errors import VidgenError

from .axis import Axis, AxisSpec, build_axis, equal_aspect

#: ``measure(text) -> (width, height)`` of a label in frame units.
Measure = Callable[[str], tuple[float, float]]


@dataclass(frozen=True)
class Rect:
    """An axis-aligned box in frame units (``x0 < x1``, ``y0 < y1``)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2

    def contains(self, x: float, y: float, tolerance: float = 1e-9) -> bool:
        """True when the point lies in the box (``tolerance`` of slack)."""
        return self.x0 - tolerance <= x <= self.x1 + tolerance and self.y0 - tolerance <= y <= self.y1 + tolerance


def approx_measure(height: float = 0.3, char_width: float = 0.55) -> Measure:
    """A text measure without fonts: ``char_width`` x ``height`` per character (for tests and
    first estimates)."""

    def measure(text: str) -> tuple[float, float]:
        return len(text) * char_width * height, height

    return measure


@dataclass(frozen=True)
class Label:
    """A label of the layout: its ``text``, centre ``x``/``y`` and measured ``width``/``height``."""

    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class PanelInput:
    """A panel to lay out: the data values its axes must show and the axis specs."""

    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    x: AxisSpec
    y: AxisSpec


@dataclass(frozen=True)
class PanelLayout:
    """A laid-out panel: its ``plot`` area, built axes, the tick labels shown (``x_labels``,
    ``y_labels``: only those kept after thinning; empty on a shared side), the ``x_title`` /
    ``y_title`` (or ``None``), and which ticks have a label (``x_kept``, ``y_kept``: indices
    into the axis' ticks)."""

    plot: Rect
    x: Axis
    y: Axis
    x_labels: tuple[Label, ...]
    y_labels: tuple[Label, ...]
    x_title: Label | None
    y_title: Label | None
    x_kept: tuple[int, ...]
    y_kept: tuple[int, ...]

    def frame_x(self, value: float) -> float:
        """Frame x of a data x value."""
        return self.plot.x0 + self.x.fraction(value) * self.plot.width

    def frame_y(self, value: float) -> float:
        """Frame y of a data y value."""
        return self.plot.y0 + self.y.fraction(value) * self.plot.height

    def frame_points(self, xs: Sequence[float], ys: Sequence[float]) -> np.ndarray:
        """``(n, 3)`` frame points of data points (``nan`` stays ``nan``)."""
        out = np.zeros((len(xs), 3))
        for k, (x, y) in enumerate(zip(xs, ys)):
            ok = math.isfinite(x) and math.isfinite(y)
            out[k] = (self.frame_x(x), self.frame_y(y), 0.0) if ok else (math.nan, math.nan, 0.0)
        return out

    def frame_line(self, xs: Sequence[float], ys: Sequence[float]) -> np.ndarray:
        """Frame points of a line through data points, with a ``nan`` row (a gap) wherever two
        neighbours lie on different sides of an axis break: a line never crosses a break."""
        pts = self.frame_points(xs, ys)
        if len(self.x.segments) == 1 and len(self.y.segments) == 1:
            return pts
        rows: list[np.ndarray] = []
        for k in range(len(pts)):
            if k and math.isfinite(xs[k - 1]) and math.isfinite(xs[k]) and math.isfinite(ys[k - 1]) and math.isfinite(ys[k]):
                if self.x.piece(xs[k - 1]) != self.x.piece(xs[k]) or self.y.piece(ys[k - 1]) != self.y.piece(ys[k]):
                    rows.append(np.array([math.nan, math.nan, 0.0]))
            rows.append(pts[k])
        return np.array(rows)


def label_stride(positions: Sequence[float], extents: Sequence[float], gap: float, *, keep_last: bool = False) -> list[int]:
    """Indices of labels to keep: every k-th (smallest k) so neighbours keep ``gap`` between
    them (``extents`` = their sizes along the axis); the last one too when it has room.
    ``keep_last``: when it has no room, the last label replaces the one kept before it (the
    end of an axis says its range)."""
    n = len(positions)
    if n <= 1:
        return list(range(n))

    def clear(i: int, j: int) -> bool:
        return abs(positions[j] - positions[i]) >= (extents[i] + extents[j]) / 2 + gap

    for k in range(1, n):
        kept = list(range(0, n, k))
        if all(clear(a, b) for a, b in zip(kept, kept[1:])):
            if kept[-1] != n - 1:
                if clear(kept[-1], n - 1):
                    kept.append(n - 1)
                elif keep_last and len(kept) >= 2 and clear(kept[-2], n - 1):
                    kept[-1] = n - 1
            return kept
    return [0]


@dataclass(frozen=True)
class _Room:
    """Text extents of one panel's axes."""

    y_tick_w: float
    y_tick_h: float
    x_tick_h: float
    y_title: tuple[float, float] | None
    x_title: tuple[float, float] | None
    last_x_w: float


def _room(x: Axis, y: Axis, measure: Measure, show_x: bool, show_y: bool, width: float) -> _Room:
    ys = [measure(t) for t in y.labels] if show_y else []
    xs = [measure(t) for t in x.labels] if show_x else []

    def title(text: str, limit: float) -> tuple[float, float] | None:
        if not text:
            return None
        w, h = measure(text)
        lines = max(1, math.ceil(w / limit)) if limit > 0 else 1
        return min(w, limit), h * lines * 1.15 if lines > 1 else h

    last_w = xs[-1][0] if xs and abs(x.fraction(x.ticks[-1]) - 1.0) < 1e-6 else 0.0
    return _Room(
        max((w for w, _ in ys), default=0.0),
        max((h for _, h in ys), default=0.0),
        max((h for _, h in xs), default=0.0),
        title(y.title, width * 0.7) if show_y else None,
        title(x.title, width * 0.9) if show_x else None,
        last_w,
    )


def layout_figure(
    area: Rect,
    panels: Sequence[PanelInput],
    measure: Measure,
    *,
    arrange: str = "rows",
    share: bool = True,
    gap: float = 0.35,
    top: float = 0.0,
    aspect: str = "auto",
    weights: Sequence[float] | None = None,
) -> list[PanelLayout]:
    """Lay out ``panels`` in ``area`` (``top`` units kept free above, for a legend).

    ``arrange``: ``rows`` (stacked, top to bottom) or ``columns`` (side by side); with
    ``share`` the stacked panels share one x axis built from every panel's x values and the
    first panel's x spec (``columns``: one y axis). ``gap``: space between panels. ``aspect:
    equal`` (one panel, linear axes): one data unit is as long on x as on y; the axis with room
    to spare is widened about its middle (an axis with both ends fixed is not widened: the plot
    shrinks instead). ``weights``: relative panel sizes along the stacking direction."""
    if not panels:
        raise VidgenError("a figure needs at least one panel")
    if arrange not in ("rows", "columns"):
        raise VidgenError(f"arrange '{arrange}' is not rows or columns")
    if aspect == "equal" and len(panels) > 1:
        raise VidgenError("aspect: equal works on a figure with one panel")
    n = len(panels)
    weights = list(weights) if weights is not None else [1.0] * n
    if len(weights) != n or any(w <= 0 for w in weights):
        raise VidgenError("weights need one positive number per panel")
    axes = _axes(panels, arrange, share)
    layouts = _place(area, axes, measure, arrange, share, gap, top, weights)
    if aspect == "equal":
        for _ in range(4):
            lay = layouts[0]
            p = panels[0]
            free_x = p.x.lo is None or p.x.hi is None
            free_y = p.y.lo is None or p.y.hi is None
            (x_lo, x_hi), (y_lo, y_hi) = equal_aspect(lay.x, lay.y, lay.plot.width, lay.plot.height)
            widen_x = (x_hi - x_lo) > (lay.x.hi - lay.x.lo) * (1 + 1e-9)
            widen_y = (y_hi - y_lo) > (lay.y.hi - lay.y.lo) * (1 + 1e-9)
            if (widen_x and not free_x) or (widen_y and not free_y):
                inner = Rect(area.x0, area.y0, area.x1, area.y1 - top)
                return [_labels(_shrunk_plot(lay), lay.x, lay.y, measure, True, True, inner, _room(lay.x, lay.y, measure, True, True, area.width))]
            x_axis = build_axis(p.x_values, p.x, lo=x_lo, hi=x_hi) if widen_x else lay.x
            y_axis = build_axis(p.y_values, p.y, lo=y_lo, hi=y_hi) if widen_y else lay.y
            if not widen_x and not widen_y:
                break
            layouts = _place(area, [(x_axis, y_axis)], measure, arrange, share, gap, top, weights)
    return layouts


def _shrunk_plot(lay: PanelLayout) -> Rect:
    """The plot narrowed (centred) or lowered (top kept) to an equal aspect, for an axis that
    would have to widen but has both ends fixed."""
    per_x = lay.plot.width / (lay.x.hi - lay.x.lo)
    per_y = lay.plot.height / (lay.y.hi - lay.y.lo)
    plot = lay.plot
    if per_x > per_y:
        w = per_y * (lay.x.hi - lay.x.lo)
        x0 = plot.x0 + (plot.width - w) / 2
        return Rect(x0, plot.y0, x0 + w, plot.y1)
    h = per_x * (lay.y.hi - lay.y.lo)
    return Rect(plot.x0, plot.y1 - h, plot.x1, plot.y1)


def _axes(panels: Sequence[PanelInput], arrange: str, share: bool) -> list[tuple[Axis, Axis]]:
    """The axes of every panel; a shared axis is built once from every panel's values."""
    if share and arrange == "rows":
        shared = build_axis([v for p in panels for v in p.x_values], panels[0].x)
        return [(shared, build_axis(p.y_values, p.y)) for p in panels]
    if share and arrange == "columns":
        shared = build_axis([v for p in panels for v in p.y_values], panels[0].y)
        return [(build_axis(p.x_values, p.x), shared) for p in panels]
    return [(build_axis(p.x_values, p.x), build_axis(p.y_values, p.y)) for p in panels]


def _place(area: Rect, axes: list[tuple[Axis, Axis]], measure: Measure, arrange: str, share: bool, gap: float, top: float, weights: Sequence[float]) -> list[PanelLayout]:
    n = len(axes)
    _, cap = measure("0")
    label_gap = 0.45 * cap + 0.05
    show = []
    for k in range(n):
        show_x = not (share and arrange == "rows" and k < n - 1)
        show_y = not (share and arrange == "columns" and k > 0)
        show.append((show_x, show_y))
    rooms = [_room(x, y, measure, sx, sy, area.width / (n if arrange == "columns" else 1)) for (x, y), (sx, sy) in zip(axes, show)]

    def head(r: _Room) -> float:   # above the plot: the y title, half a tick label
        return (r.y_title[1] + label_gap if r.y_title else 0.0) + max(r.y_tick_h, cap) / 2

    def foot(r: _Room) -> float:   # below the plot: the x labels and title, or half a y label
        if r.x_tick_h or r.x_title:
            return r.x_tick_h + label_gap + (r.x_title[1] + label_gap * 0.8 if r.x_title else 0.0)
        return max(r.y_tick_h, cap) / 2

    plots: list[Rect] = []
    inner = Rect(area.x0, area.y0, area.x1, area.y1 - top)
    if arrange == "rows":
        left = inner.x0 + max(r.y_tick_w for r in rooms) + label_gap
        right = inner.x1 - max(max(r.last_x_w / 2 for r in rooms), 0.05)
        fixed = sum(head(r) + foot(r) for r in rooms) + gap * (n - 1)
        free = max(inner.height - fixed, 0.5 * n)
        y = inner.y1
        for r, w in zip(rooms, weights):
            h = free * w / sum(weights)
            top_y = y - head(r)
            plots.append(Rect(left, top_y - h, max(right, left + 0.5), top_y))
            y = top_y - h - foot(r) - gap
    else:
        fixed_w = [(r.y_tick_w + label_gap if r.y_tick_w else 0.0) for r in rooms]
        right_room = [max(r.last_x_w / 2, 0.05) for r in rooms]
        free = max(inner.width - sum(fixed_w) - sum(right_room) - gap * (n - 1), 0.5 * n)
        top_y = inner.y1 - max(head(r) for r in rooms)
        bottom = inner.y0 + max(foot(r) for r in rooms)
        x = inner.x0
        for r, fw, rr, w in zip(rooms, fixed_w, right_room, weights):
            width = free * w / sum(weights)
            plots.append(Rect(x + fw, min(bottom, top_y - 0.5), x + fw + width, top_y))
            x += fw + width + rr + gap
    out = []
    for plot, (x, y), (sx, sy), r in zip(plots, axes, show, rooms):
        cell = Rect(inner.x0 if arrange == "rows" else plot.x0 - (r.y_tick_w + label_gap if r.y_tick_w else 0.0), inner.y0, inner.x1 if arrange == "rows" else plot.x1, inner.y1)
        out.append(_labels(plot, x, y, measure, sx, sy, cell, r))
    return out


def _labels(plot: Rect, x: Axis, y: Axis, measure: Measure, show_x: bool, show_y: bool, cell: Rect, room: _Room) -> PanelLayout:
    """Tick labels and titles of a panel around ``plot`` (thinned so none touch)."""
    _, cap = measure("0")
    label_gap = 0.45 * cap + 0.05
    lay = PanelLayout(plot, x, y, (), (), None, None, (), ())
    x_labels: list[Label] = []
    y_labels: list[Label] = []
    x_kept: list[int] = []
    y_kept: list[int] = []
    if show_x and x.labels:
        sizes = [measure(t) for t in x.labels]
        pos = [lay.frame_x(t) for t in x.ticks]
        order = sorted(range(len(pos)), key=lambda i: pos[i])
        keep = label_stride([pos[i] for i in order], [sizes[i][0] for i in order], 0.35 * cap + 0.15, keep_last=True)
        x_kept = sorted(order[i] for i in keep)
        row_h = max(h for _, h in sizes)
        for i in x_kept:
            x_labels.append(Label(x.labels[i], pos[i], plot.y0 - label_gap - row_h / 2, *sizes[i]))
    if show_y and y.labels:
        sizes = [measure(t) for t in y.labels]
        pos = [lay.frame_y(t) for t in y.ticks]
        order = sorted(range(len(pos)), key=lambda i: pos[i])
        keep = label_stride([pos[i] for i in order], [sizes[i][1] for i in order], 0.9 * cap, keep_last=True)
        y_kept = sorted(order[i] for i in keep)
        for i in y_kept:
            w, h = sizes[i]
            y_labels.append(Label(y.labels[i], plot.x0 - label_gap - w / 2, pos[i], w, h))
    y_title = None
    if show_y and room.y_title is not None:
        w, h = room.y_title
        left = min(plot.x0 - label_gap - room.y_tick_w, plot.x0)
        top = plot.y1 + max(room.y_tick_h, cap) / 2 + label_gap
        y_title = Label(y.title, left + w / 2, top + h / 2, w, h)
    x_title = None
    if show_x and room.x_title is not None:
        w, h = room.x_title
        cx = min(max(plot.center[0], cell.x0 + w / 2), cell.x1 - w / 2)
        row_h = room.x_tick_h
        x_title = Label(x.title, cx, plot.y0 - label_gap - row_h - label_gap * 0.8 - h / 2, w, h)
    return replace(lay, x_labels=tuple(x_labels), y_labels=tuple(y_labels), x_title=x_title, y_title=y_title, x_kept=tuple(x_kept), y_kept=tuple(y_kept))


def clip_polyline(points: np.ndarray, box: Rect) -> list[np.ndarray]:
    """The parts of a polyline (``(n, 2|3)`` frame points; ``nan`` rows break it) inside
    ``box``: a list of runs of at least two points, each segment clipped (Liang-Barsky)."""
    pts = np.asarray(points, dtype=float)
    runs: list[list[np.ndarray]] = []
    current: list[np.ndarray] = []

    def close() -> None:
        nonlocal current
        if len(current) >= 2:
            runs.append(current)
        current = []

    for a, b in zip(pts, pts[1:]):
        if np.isnan(a[:2]).any() or np.isnan(b[:2]).any():
            close()
            continue
        seg = _clip_segment(a, b, box)
        if seg is None:
            close()
            continue
        p, q = seg
        if current and np.allclose(current[-1][:2], p[:2], atol=1e-9):
            current.append(q)
        else:
            close()
            current = [p, q]
        if not np.allclose(q[:2], b[:2], atol=1e-9):   # left the box
            close()
    close()
    return [np.array(run) for run in runs]


def _clip_segment(a: np.ndarray, b: np.ndarray, box: Rect) -> tuple[np.ndarray, np.ndarray] | None:
    d = b - a
    t0, t1 = 0.0, 1.0
    for p, q in ((-d[0], a[0] - box.x0), (d[0], box.x1 - a[0]), (-d[1], a[1] - box.y0), (d[1], box.y1 - a[1])):
        if abs(p) < 1e-15:
            if q < -1e-12:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1 + 1e-12:
            return None
    return a + d * t0, a + d * t1


__all__ = [
    "Label",
    "Measure",
    "PanelInput",
    "PanelLayout",
    "Rect",
    "approx_measure",
    "clip_polyline",
    "label_stride",
    "layout_figure",
]
