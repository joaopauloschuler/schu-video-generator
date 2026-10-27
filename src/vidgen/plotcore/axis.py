"""One axis of a scientific plot: its scale (linear, log, symlog), domain, direction, breaks,
ticks and labels, and the mapping of data values to a fraction of the axis' length."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from vidgen.errors import VidgenError

from .numbers import axis_title, check_tick_format, clean, tick_labels
from .ticks import default_linthresh, linear_ticks, log_ticks, symlog_inverse, symlog_ticks, symlog_transform, widen

#: Axis scales.
SCALES = ("linear", "log", "symlog")
#: The gap a break leaves in the axis, as a share of its length.
BREAK_GAP = 0.04


@dataclass(frozen=True)
class AxisSpec:
    """What the author asks of an axis. ``lo`` / ``hi`` fix an end (else the data's range,
    rounded out to a tick); ``reversed`` runs it from high to low; ``linthresh`` is the linear
    range of a symlog axis (default from the data); ``breaks`` are value ranges cut out of a
    linear axis (``[(a, b)]``: nothing between a and b is drawn); ``format`` is a tick format
    (:func:`~vidgen.plotcore.numbers.tick_labels`); ``include_zero`` keeps 0 in the domain;
    ``exact``: the domain is the data's range exactly (with ``margin``, a share of the span on
    each side), ticks only inside it."""

    scale: str = "linear"
    lo: float | None = None
    hi: float | None = None
    reversed: bool = False
    linthresh: float | None = None
    breaks: tuple[tuple[float, float], ...] = ()
    format: str = "auto"
    unit: str = ""
    label: str = ""
    max_ticks: int = 6
    include_zero: bool = False
    exact: bool = False
    margin: float = 0.0

    def problems(self, values: Sequence[float], name: str = "axis") -> list[str]:
        """What is wrong with this spec for ``values`` (data that must be shown), each a
        sentence starting with ``name``; empty when the axis can be built."""
        out: list[str] = []
        if self.scale not in SCALES:
            out.append(f"{name}: scale '{self.scale}' is not one of {', '.join(SCALES)}")
            return out
        try:
            check_tick_format(self.format)
        except ValueError as exc:
            out.append(f"{name}: {exc}")
        if self.format == "si":
            from .numbers import prefixed_unit_problem

            problem = prefixed_unit_problem(self.unit)
            if problem:
                out.append(f"{name}: {problem}")
        if self.lo is not None and self.hi is not None and self.hi <= self.lo:
            out.append(f"{name}: max ({self.hi:g}) must be greater than min ({self.lo:g}); use reversed: true to run it the other way")
        finite = [v for v in values if math.isfinite(v)]
        if self.scale == "log":
            bad = [v for v in finite if v <= 0]
            if bad:
                out.append(f"{name}: a log scale needs positive values, but the data has {bad[0]:g}; use scale: symlog for zero or negative values")
            for end, v in (("min", self.lo), ("max", self.hi)):
                if v is not None and v <= 0:
                    out.append(f"{name}: a log scale needs a positive {end}, got {v:g}")
        if self.linthresh is not None and self.scale != "symlog":
            out.append(f"{name}: linthresh is for scale: symlog")
        if self.linthresh is not None and self.linthresh <= 0:
            out.append(f"{name}: linthresh must be positive, got {self.linthresh:g}")
        if self.breaks:
            if self.scale != "linear":
                out.append(f"{name}: breaks need a linear scale")
            for a, b in self.breaks:
                if b <= a:
                    out.append(f"{name}: a break [{a:g}, {b:g}] must go from low to high")
                inside = [v for v in finite if a < v < b]
                if inside:
                    out.append(f"{name}: the value {inside[0]:g} lies inside the break [{a:g}, {b:g}]; narrow the break or drop the point")
            spans = sorted(self.breaks)
            for (a0, b0), (a1, _) in zip(spans, spans[1:]):
                if a1 < b0:
                    out.append(f"{name}: breaks [{a0:g}, {b0:g}] and [{a1:g}, ...] overlap")
            if finite and spans and not (min(finite) < spans[0][0] and max(finite) > spans[-1][1]):
                out.append(f"{name}: a break must have data on both sides (data {min(finite):g}..{max(finite):g})")
        for end, v in (("min", self.lo), ("max", self.hi)):
            outside = [x for x in finite if (end == "min" and v is not None and x < v - 1e-12 * abs(v)) or (end == "max" and v is not None and x > v + 1e-12 * abs(v))]
            if outside:
                out.append(f"{name}: the value {outside[0]:g} lies outside {end} {v:g}; widen the axis or drop the point")
        return out


@dataclass(frozen=True)
class Axis:
    """A built axis. ``lo..hi`` is the domain (``lo < hi``; ``reversed`` draws hi first),
    ``ticks`` / ``labels`` the labelled ticks, ``minor`` unlabelled ones (log decades),
    ``title`` the axis title with its unit (``time (ms)``), ``segments`` the domain pieces
    left by breaks (one piece without breaks)."""

    scale: str
    lo: float
    hi: float
    ticks: tuple[float, ...]
    labels: tuple[str, ...]
    minor: tuple[float, ...] = ()
    title: str = ""
    reversed: bool = False
    linthresh: float = 1.0
    segments: tuple[tuple[float, float], ...] = field(default=())

    def __post_init__(self) -> None:
        if len(self.ticks) != len(self.labels):
            raise VidgenError(f"an axis needs one label per tick, got {len(self.ticks)} ticks and {len(self.labels)} labels")
        if not self.lo < self.hi:
            raise VidgenError(f"an axis needs lo < hi, got {self.lo:g}..{self.hi:g}")
        if self.scale == "log" and self.lo <= 0:
            raise VidgenError(f"a log axis needs a positive domain, got {self.lo:g}..{self.hi:g}")
        if not self.segments:
            object.__setattr__(self, "segments", ((self.lo, self.hi),))

    def transform(self, value: float) -> float:
        """``value`` in scale space (log10 for log, the symlog transform for symlog)."""
        if self.scale == "log":
            return math.log10(max(value, 1e-300))
        if self.scale == "symlog":
            return symlog_transform(value, self.linthresh)
        return value

    def inverse(self, position: float) -> float:
        """The value at a scale-space ``position``."""
        if self.scale == "log":
            return 10.0**position
        if self.scale == "symlog":
            return symlog_inverse(position, self.linthresh)
        return position

    def fraction(self, value: float) -> float:
        """Where ``value`` lies along the drawn axis: 0 at its start (left / bottom), 1 at its
        end; beyond the domain it continues (< 0, > 1). Breaks take :data:`BREAK_GAP` each."""
        pieces = self.segments
        if len(pieces) == 1:
            a, b = self.transform(self.lo), self.transform(self.hi)
            f = (self.transform(value) - a) / ((b - a) or 1.0)
        else:
            usable = 1.0 - BREAK_GAP * (len(pieces) - 1)
            total = sum(b - a for a, b in pieces)
            start = 0.0
            f = None
            for i, (a, b) in enumerate(pieces):
                share = usable * (b - a) / total
                last = i == len(pieces) - 1
                if value <= b or last:
                    if value < a and i > 0:   # inside a break: at the break's middle
                        f = start - BREAK_GAP / 2
                    else:
                        f = start + share * (value - a) / ((b - a) or 1.0)
                    break
                start += share + BREAK_GAP
        return 1.0 - f if self.reversed else f

    def contains(self, value: float) -> bool:
        """True when ``value`` lies in the domain and in no break."""
        span = self.hi - self.lo
        return any(a - 1e-9 * span <= value <= b + 1e-9 * span for a, b in self.segments)

    def break_fractions(self) -> list[float]:
        """The middle of each break along the drawn axis (where the break marks go)."""
        out = []
        for (_, b0), (a1, _) in zip(self.segments, self.segments[1:]):
            out.append((self.fraction(b0) + self.fraction(a1)) / 2)
        return out


def build_axis(values: Sequence[float], spec: AxisSpec, *, lo: float | None = None, hi: float | None = None) -> Axis:
    """The axis showing ``values`` as ``spec`` asks. ``lo`` / ``hi`` override the domain
    exactly (an equal aspect widened it); ticks then lie inside. Raises ``VidgenError`` with
    the first of :meth:`AxisSpec.problems`."""
    problems = spec.problems(values)
    if problems:
        raise VidgenError(problems[0])
    data = [float(v) for v in values if math.isfinite(v)]
    data += [v for v in (spec.lo, spec.hi) if v is not None]
    if not data:
        data = [1.0, 10.0] if spec.scale == "log" else [0.0, 1.0]
    d_lo = spec.lo if spec.lo is not None else min(data)
    d_hi = spec.hi if spec.hi is not None else max(data)
    if spec.include_zero and spec.scale != "log":
        d_lo = min(d_lo, 0.0) if spec.lo is None else d_lo
        d_hi = max(d_hi, 0.0) if spec.hi is None else d_hi
    linthresh = spec.linthresh or default_linthresh(data)
    fixed = lo is not None or hi is not None
    if lo is not None:
        d_lo = lo
    if hi is not None:
        d_hi = hi
    if spec.scale == "log":
        if d_hi / d_lo < 1 + 1e-9:
            d_lo, d_hi = d_lo / 2, d_hi * 2
    else:
        d_lo, d_hi = widen(d_lo, d_hi)
    if spec.exact and not fixed and spec.margin > 0:
        if spec.scale == "log":
            r = (math.log10(d_hi) - math.log10(d_lo)) * spec.margin
            d_lo, d_hi = (d_lo if spec.lo is not None else d_lo / 10**r), (d_hi if spec.hi is not None else d_hi * 10**r)
        else:
            m = (d_hi - d_lo) * spec.margin
            d_lo, d_hi = (d_lo if spec.lo is not None else d_lo - m), (d_hi if spec.hi is not None else d_hi + m)
    inside = spec.exact or fixed
    minor: list[float] = []
    segments: tuple[tuple[float, float], ...] = ()
    if spec.breaks:
        pieces = _pieces(d_lo, d_hi, sorted(spec.breaks))
        total = sum(b - a for a, b in pieces)
        ticks: list[float] = []
        for k, (a, b) in enumerate(pieces):
            n = max(2, round(spec.max_ticks * (b - a) / total) + 1)
            ends_free = (k == 0 and spec.lo is None and not inside, k == len(pieces) - 1 and spec.hi is None and not inside)
            piece = linear_ticks(a, b, n, inside=True)
            if ends_free[0]:
                outer = linear_ticks(a, b, n)
                piece = [t for t in outer if t < a][-1:] + piece
            if ends_free[1]:
                outer = linear_ticks(a, b, n)
                piece = piece + [t for t in outer if t > b][:1]
            ticks += piece
        lo_, hi_ = min([d_lo] + ticks), max([d_hi] + ticks)
        pieces = [(lo_ if i == 0 else a, hi_ if i == len(pieces) - 1 else b) for i, (a, b) in enumerate(pieces)]
        segments = tuple(pieces)
        d_lo, d_hi = lo_, hi_
    elif spec.scale == "log":
        ticks, minor = log_ticks(d_lo, d_hi, spec.max_ticks, inside=inside)
        if not inside:
            d_lo, d_hi = min(d_lo, ticks[0]), max(d_hi, ticks[-1])
            if spec.lo is not None:
                d_lo, ticks = spec.lo, [t for t in ticks if t >= spec.lo * (1 - 1e-9)]
            if spec.hi is not None:
                d_hi, ticks = spec.hi, [t for t in ticks if t <= spec.hi * (1 + 1e-9)]
    elif spec.scale == "symlog":
        ticks = symlog_ticks(d_lo, d_hi, linthresh, spec.max_ticks, inside=inside)
        if not inside:
            d_lo, d_hi = min(d_lo, ticks[0]), max(d_hi, ticks[-1])
            if spec.lo is not None:
                d_lo, ticks = spec.lo, [t for t in ticks if t >= spec.lo - 1e-12 * abs(spec.lo)]
            if spec.hi is not None:
                d_hi, ticks = spec.hi, [t for t in ticks if t <= spec.hi + 1e-12 * abs(spec.hi)]
    else:
        ticks = linear_ticks(d_lo, d_hi, spec.max_ticks, inside=inside)
        if not inside:
            d_lo, d_hi = min(d_lo, ticks[0]), max(d_hi, ticks[-1])
            if spec.lo is not None:
                d_lo = spec.lo
                ticks = [t for t in ticks if t >= spec.lo - 1e-9 * abs(d_hi - d_lo)] or ticks
            if spec.hi is not None:
                d_hi = spec.hi
                ticks = [t for t in ticks if t <= spec.hi + 1e-9 * abs(d_hi - d_lo)] or ticks
    ticks = [clean(t) for t in ticks]
    minor = [t for t in minor if d_lo < t < d_hi and t not in ticks]
    labels = tick_labels(ticks, spec.format, spec.unit, scale=spec.scale)
    title = axis_title(spec.label, labels.title_unit, labels.exponent)
    return Axis(spec.scale, d_lo, d_hi, tuple(ticks), tuple(labels.labels), tuple(minor), title, spec.reversed, linthresh, segments)


def _pieces(lo: float, hi: float, breaks: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The domain ``lo..hi`` cut by the ``breaks`` into the pieces that are drawn."""
    pieces, start = [], lo
    for a, b in breaks:
        pieces.append((start, a))
        start = b
    pieces.append((start, hi))
    return [(clean(a), clean(b)) for a, b in pieces]


def equal_aspect(x: Axis, y: Axis, width: float, height: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """Domains for an x and a y axis (both linear) that make one data unit as long on both in a
    plot ``width`` x ``height``: the axis with room to spare widens about its middle. Returns
    ``((x_lo, x_hi), (y_lo, y_hi))``."""
    if x.scale != "linear" or y.scale != "linear":
        raise VidgenError("an equal aspect needs linear x and y axes")
    xs, ys = x.hi - x.lo, y.hi - y.lo
    per_x, per_y = width / xs, height / ys
    if per_x > per_y:   # x has room to spare: widen x
        span = width / per_y
        mid = (x.lo + x.hi) / 2
        return (mid - span / 2, mid + span / 2), (y.lo, y.hi)
    span = height / per_x
    mid = (y.lo + y.hi) / 2
    return (x.lo, x.hi), (mid - span / 2, mid + span / 2)


__all__ = ["BREAK_GAP", "SCALES", "Axis", "AxisSpec", "build_axis", "equal_aspect"]
