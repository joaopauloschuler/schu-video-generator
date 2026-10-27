"""The logic of live plots (Phase W, DESIGN §97.7), without manim: how much of a series is
drawn at a moment of its growth, where its head is, how an axis rescales smoothly while the
data grow past it, the domain of a zoom in between, and the text of a live readout. Deterministic
pure functions of the progress, so a frame never depends on the frames before it."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np

from .axis import Axis, AxisSpec, build_axis
from .numbers import plain_number, sci_number

#: Share of the progress shown by the first domain of a rescaling axis.
START_SHARE = 0.12
#: Room added past the data when an axis grows (share of the data's span).
HEADROOM = 0.3
#: An end closer than this share of the final span to the final end jumps to it.
SNAP = 0.15
#: Length of one rescaling, as a share of the progress range.
EASE = 0.07


def grown(times: Sequence[float], xs: Sequence[float], ys: Sequence[float], until: float) -> tuple[list[float], list[float]]:
    """The part of a series drawn when its growth has reached ``until`` (in its progress
    column ``times``, non-decreasing): every point up to it and, between two points, the head
    interpolated (a gap stays a gap)."""
    t = np.asarray(times, dtype=float)
    if not len(t) or until < t[0]:
        return [], []
    k = int(np.searchsorted(t, until, side="right"))   # points 0..k-1 are reached
    out_x = [float(v) for v in xs[:k]]
    out_y = [float(v) for v in ys[:k]]
    if k < len(t) and t[k] > t[k - 1]:
        f = (until - t[k - 1]) / (t[k] - t[k - 1])
        x0, x1, y0, y1 = float(xs[k - 1]), float(xs[k]), float(ys[k - 1]), float(ys[k])
        if f > 1e-9 and all(math.isfinite(v) for v in (x0, x1, y0, y1)):
            out_x.append(x0 + (x1 - x0) * f)
            out_y.append(y0 + (y1 - y0) * f)
    return out_x, out_y


def segment(times: Sequence[float], xs: Sequence[float], ys: Sequence[float], start: float, end: float) -> tuple[list[float], list[float]]:
    """The stretch of a series between progress ``start`` and ``end`` (both ends interpolated
    between points): a trail's recent part."""
    if end <= start:
        return [], []
    gx, gy = grown(times, xs, ys, end)
    t = np.asarray(times, dtype=float)
    if not gx or start <= t[0]:
        return gx, gy
    k = int(np.searchsorted(t, start, side="right"))   # points 0..k-1 lie at or before start
    first_x, first_y = grown(times, xs, ys, start)
    return [first_x[-1], *gx[k:]], [first_y[-1], *gy[k:]]


def head(times: Sequence[float], xs: Sequence[float], ys: Sequence[float], until: float) -> tuple[float, float] | None:
    """Where the growing series' head is at ``until`` (its last drawn point; ``None`` before
    it starts or on a gap)."""
    gx, gy = grown(times, xs, ys, until)
    if not gx or not (math.isfinite(gx[-1]) and math.isfinite(gy[-1])):
        return None
    return gx[-1], gy[-1]


def value_at(times: Sequence[float], values: Sequence[float], until: float) -> float:
    """A column's value at ``until`` (linear between samples; held past the ends)."""
    t = np.asarray(times, dtype=float)
    v = np.asarray(values, dtype=float)
    if until <= t[0]:
        return float(v[0])
    if until >= t[-1]:
        return float(v[-1])
    k = int(np.searchsorted(t, until, side="right"))
    if t[k] == t[k - 1]:
        return float(v[k])
    f = (until - t[k - 1]) / (t[k] - t[k - 1])
    return float(v[k - 1] + (v[k] - v[k - 1]) * f)


def time_like(times: Sequence[float], values: Sequence[float]) -> bool:
    """True when ``values`` never decrease along the growth (a time axis): such an axis is
    shown whole from the start instead of rescaling."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    return bool(len(v) < 2 or np.all(np.diff(v) >= 0))


@dataclass(frozen=True)
class Stop:
    """A rescaling: from ``start`` to ``end`` (progress) the axis eases to ``lo..hi``
    (transform space)."""

    start: float
    end: float
    lo: float
    hi: float


def rescale_schedule(
    times: Sequence[float],
    values: Sequence[float],
    final: tuple[float, float],
    *,
    fixed_lo: bool = False,
    fixed_hi: bool = False,
    start_share: float = START_SHARE,
    headroom: float = HEADROOM,
    snap: float = SNAP,
    ease: float = EASE,
) -> tuple[tuple[float, float], list[Stop]]:
    """How an axis grows with data that arrive over ``times``: ``(first domain, stops)``.

    ``values`` are the data along the axis in transform space (log10 for a log axis), in growth
    order; ``final`` the axis' domain once all data are shown (the static plot's). The first
    domain covers the data of the first ``start_share`` of the progress with ``headroom``;
    whenever the data would leave the domain shown, it grows to cover them with ``headroom`` of
    their span (never past ``final``; an end within ``snap`` of the final end jumps to it). Each
    growth eases in over ``ease`` of the progress range and ends when the data get there, so
    the data never leave the plot; stops closer than that merge. Fixed ends stay at ``final``.
    The last stop ends on ``final`` at the end of the progress."""
    t = np.asarray(times, dtype=float)
    v = np.asarray(values, dtype=float)
    f_lo, f_hi = float(final[0]), float(final[1])
    f_span = f_hi - f_lo
    if not len(t):
        return (f_lo, f_hi), []
    t0, t1 = float(t[0]), float(t[-1])
    t_span = max(t1 - t0, 1e-12)
    ease_t = ease * t_span
    finite = np.isfinite(v)
    lo_run = np.minimum.accumulate(np.where(finite, v, np.inf))
    hi_run = np.maximum.accumulate(np.where(finite, v, -np.inf))

    def cover(lo: float, hi: float) -> tuple[float, float]:
        span = hi - lo
        if not math.isfinite(span) or span <= 0:
            span = 0.1 * f_span
            if not math.isfinite(lo):
                lo = hi = (f_lo + f_hi) / 2
        a, b = lo - headroom * span, hi + headroom * span
        a, b = max(a, f_lo), min(b, f_hi)
        if a - f_lo < snap * f_span or fixed_lo:
            a = f_lo
        if f_hi - b < snap * f_span or fixed_hi:
            b = f_hi
        return a, b

    k0 = int(np.searchsorted(t, t0 + start_share * t_span, side="right")) - 1
    k0 = max(0, min(k0, len(t) - 1))
    first = cover(float(lo_run[k0]), float(hi_run[k0]))
    stops: list[Stop] = []
    cur = first
    for k in range(k0 + 1, len(t)):
        if lo_run[k] < cur[0] - 1e-12 * f_span or hi_run[k] > cur[1] + 1e-12 * f_span:
            # the domain must cover the data from the moment they arrive: ease in before
            new = cover(min(cur[0], float(lo_run[k])), max(cur[1], float(hi_run[k])))
            end = float(t[k - 1]) if k > 0 else float(t[k])
            if stops and end - stops[-1].end < ease_t:   # too close: the earlier stop grows instead
                prev = stops.pop()
                stops.append(Stop(prev.start, prev.end, new[0], new[1]))
            else:
                stops.append(Stop(max(end - ease_t, stops[-1].end if stops else t0 - ease_t), end, new[0], new[1]))
            cur = new
    if cur != (f_lo, f_hi):
        end = t1
        if stops and end - stops[-1].end < ease_t:
            prev = stops.pop()
            stops.append(Stop(prev.start, prev.end, f_lo, f_hi))
        else:
            stops.append(Stop(max(end - ease_t, stops[-1].end if stops else t0), end, f_lo, f_hi))
    return first, stops


def axis_for(static: Axis, spec: AxisSpec, lo: float, hi: float) -> Axis:
    """The axis ``spec`` describes over the domain ``lo..hi`` given in ``static``'s transform
    space (a rescaling or zoomed axis): ticks inside it, the static axis' ``linthresh``. The
    static axis itself when the domain is its own."""
    if abs(lo - static.transform(static.lo)) < 1e-12 and abs(hi - static.transform(static.hi)) < 1e-12:
        return static
    a, b = static.inverse(lo), static.inverse(hi)
    use = replace(spec, linthresh=static.linthresh if spec.scale == "symlog" else None, lo=None, hi=None, breaks=())
    return build_axis([], use, lo=a, hi=b)


def smoothstep(f: float) -> float:
    """``3f² − 2f³`` on [0, 1] (0 below, 1 above)."""
    f = min(max(f, 0.0), 1.0)
    return f * f * (3 - 2 * f)


def domain_at(first: tuple[float, float], stops: Sequence[Stop], progress: float) -> tuple[float, float]:
    """The domain (transform space) of a rescaling axis at ``progress``."""
    lo, hi = first
    for s in stops:
        if progress >= s.end:
            lo, hi = s.lo, s.hi
            continue
        if progress > s.start and s.end > s.start:
            f = smoothstep((progress - s.start) / (s.end - s.start))
            return lo + (s.lo - lo) * f, hi + (s.hi - hi) * f
        break
    return lo, hi


def blend(a: tuple[float, float], b: tuple[float, float], f: float) -> tuple[float, float]:
    """The domain a share ``f`` (eased) of the way from ``a`` to ``b`` (a zoom)."""
    g = smoothstep(f)
    return a[0] + (b[0] - a[0]) * g, a[1] + (b[1] - a[1]) * g


def readout_number(value: float, digits: int = 3, *, integer: bool = False) -> str:
    """A live value with ``digits`` significant digits: plain between 10⁻³ and 10⁵, else in
    scientific notation; the minus sign U+2212. ``integer``: a whole number is written whole
    (a step count, a walker's position)."""
    if not math.isfinite(value):
        return "—"
    if value == 0:
        return "0"
    if integer and value == round(value) and abs(value) < 1e9:
        return plain_number(value, 0)
    if 1e-3 <= abs(value) < 1e5:
        decimals = max(0, digits - 1 - math.floor(math.log10(abs(value))))
        return plain_number(value, decimals)
    return sci_number(value, digits)


def readout_text(label: str, value: float, unit: str = "", digits: int = 3, *, integer: bool = False) -> str:
    """``label = value unit`` (a live readout line)."""
    return f"{label} = {readout_number(value, digits, integer=integer)}" + (f" {unit}" if unit else "")


__all__ = [
    "EASE",
    "HEADROOM",
    "SNAP",
    "START_SHARE",
    "Stop",
    "axis_for",
    "blend",
    "domain_at",
    "grown",
    "head",
    "readout_number",
    "readout_text",
    "rescale_schedule",
    "segment",
    "smoothstep",
    "time_like",
    "value_at",
]
