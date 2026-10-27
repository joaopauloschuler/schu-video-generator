"""Tick values: round linear steps (1, 2, 2.5, 5 x 10^k), decades on a log axis (with 2-9
minor ticks) and symmetric decades on a symlog axis. Pure arithmetic, deterministic."""

from __future__ import annotations

import math

from vidgen.errors import VidgenError

from .numbers import clean, exponent_of

#: Step multipliers of a linear axis.
NICE_STEPS = (1.0, 2.0, 2.5, 5.0)
#: Relative spans below this are treated as one value (doubles hold ~15-16 digits).
_TINY = 1e-12


def widen(lo: float, hi: float) -> tuple[float, float]:
    """``lo..hi`` ordered, and widened around a single value (``5..5`` -> ``4.5..5.5``,
    ``0..0`` -> ``-1..1``)."""
    lo, hi = min(lo, hi), max(lo, hi)
    if hi - lo <= _TINY * max(abs(lo), abs(hi)) or hi == lo:
        pad = abs(lo) * 0.1 or 1.0
        lo, hi = lo - pad, hi + pad
    return lo, hi


def linear_step(lo: float, hi: float, max_ticks: int = 6) -> float:
    """The smallest round step (1, 2, 2.5 or 5 x 10^k) whose ticks from a multiple at or
    below ``lo`` to one at or above ``hi`` number at most ``max_ticks`` (at least 2)."""
    lo, hi = widen(lo, hi)
    max_ticks = max(2, max_ticks)
    raw = (hi - lo) / (max_ticks - 1)
    magnitude = 10.0 ** exponent_of(raw)
    for k in range(3):
        for mult in NICE_STEPS:
            step = mult * magnitude * 10.0**k
            first = math.floor(lo / step + 1e-9)
            last = math.ceil(hi / step - 1e-9)
            if last - first + 1 <= max_ticks:
                return step
    return 10.0 * magnitude * 100.0


def linear_ticks(lo: float, hi: float, max_ticks: int = 6, *, inside: bool = False) -> list[float]:
    """Round ticks covering ``lo..hi``: the first at or below ``lo``, the last at or above
    ``hi``, at most ``max_ticks``. ``inside``: only the round values within ``lo..hi`` (for a
    domain fixed by the author or by an equal aspect), at most ``max_ticks`` of them."""
    lo, hi = widen(lo, hi)
    step = linear_step(lo, hi, max_ticks)
    if inside:
        # the densest round step that still leaves at most max_ticks inside
        for candidate in _steps_from(step / 10.0):
            first, last = math.ceil(lo / candidate - 1e-9), math.floor(hi / candidate + 1e-9)
            if 0 < last - first + 1 <= max_ticks:
                return [clean(k * candidate) for k in range(first, last + 1)]
        return [clean(lo), clean(hi)]
    first = math.floor(lo / step + 1e-9)
    last = math.ceil(hi / step - 1e-9)
    return [clean(k * step) for k in range(first, last + 1)]


def _steps_from(start: float) -> list[float]:
    """Round steps from about ``start`` upwards over four decades."""
    base = 10.0 ** exponent_of(start)
    return [m * base * 10.0**k for k in range(5) for m in NICE_STEPS]


def log_ticks(lo: float, hi: float, max_ticks: int = 6, *, inside: bool = False) -> tuple[list[float], list[float]]:
    """``(major, minor)`` ticks of a base-10 log axis over ``lo..hi`` (both > 0).

    Major: powers of ten, every k-th decade when there are more than ``max_ticks``; when the
    range spans at most two decades and 1-2-5 steps fit in ``max_ticks``, those (1, 2, 5, 10,
    20...). Minor (only with every decade labelled): 2..9 x 10^k, for faint gridlines. Without
    ``inside`` the ticks reach a round value at or beyond each end."""
    if lo <= 0 or hi <= 0:
        raise VidgenError(f"a log axis needs positive values, got {lo:g}..{hi:g}")
    lo, hi = min(lo, hi), max(lo, hi)
    if hi / lo < 1 + 1e-9:
        lo, hi = lo / 2, hi * 2
    first, last = exponent_of(lo), exponent_of(hi)
    if 10.0**last < hi * (1 - 1e-9):
        last += 1
    last = max(last, first + 1)
    decades = last - first
    if decades <= 2:
        candidates = [clean(m * 10.0**e) for e in range(first, last + 1) for m in (1, 2, 5)]
        if inside:
            major = [t for t in candidates if lo * (1 - 1e-9) <= t <= hi * (1 + 1e-9)]
        else:
            below = [t for t in candidates if t <= lo * (1 + 1e-9)] or candidates[:1]
            above = [t for t in candidates if t >= hi * (1 - 1e-9)] or candidates[-1:]
            major = [t for t in candidates if below[-1] <= t <= above[0]]
        if 2 <= len(major) <= max(2, max_ticks):
            minor = [clean(m * 10.0**e) for e in range(first, last + 1) for m in (3, 4, 6, 7, 8, 9)]
            return major, [t for t in minor if major[0] < t < major[-1]]
    step = max(1, math.ceil(decades / max(1, max_ticks - 1)))
    start = math.floor(first / step) * step
    major = [clean(10.0**e) for e in range(start, last + step, step)]
    if inside:
        major = [t for t in major if lo * (1 - 1e-9) <= t <= hi * (1 + 1e-9)] or [clean(lo), clean(hi)]
    else:
        major = [t for t in major if t <= lo * (1 + 1e-9)][-1:] + [t for t in major if lo * (1 + 1e-9) < t < hi * (1 - 1e-9)] + [t for t in major if t >= hi * (1 - 1e-9)][:1]
    minor: list[float] = []
    if step == 1:
        minor = [clean(m * 10.0**e) for e in range(first - 1, last + 1) for m in range(2, 10)]
        minor = [t for t in minor if major[0] < t < major[-1]]
    return major, minor


def symlog_transform(value: float, linthresh: float) -> float:
    """The symmetric log of ``value``: linear within ``±linthresh`` (mapped to ``±1``), then one
    unit per decade: ``sign(v) (1 + log10(|v| / linthresh))``."""
    if abs(value) <= linthresh:
        return value / linthresh
    return math.copysign(1.0 + math.log10(abs(value) / linthresh), value)


def symlog_inverse(position: float, linthresh: float) -> float:
    """The value at a symlog ``position`` (inverse of :func:`symlog_transform`)."""
    if abs(position) <= 1.0:
        return position * linthresh
    return math.copysign(linthresh * 10.0 ** (abs(position) - 1.0), position)


def default_linthresh(values: list[float]) -> float:
    """A linear threshold for a symlog axis: the power of ten at or below the smallest non-zero
    magnitude, but at most 1/1000 of the largest (so the log part shows some decades)."""
    mags = [abs(v) for v in values if v != 0 and math.isfinite(v)]
    if not mags:
        return 1.0
    low = 10.0 ** exponent_of(min(mags))
    cap = 10.0 ** (exponent_of(max(mags)) - 3)
    return clean(max(low, cap))


def symlog_ticks(lo: float, hi: float, linthresh: float, max_ticks: int = 7, *, inside: bool = False) -> list[float]:
    """Ticks of a symlog axis: 0 (when in range) and ``±linthresh x 10^k``, every k-th decade
    when there are more than ``max_ticks``; without ``inside`` they reach a tick at or beyond
    each end."""
    if linthresh <= 0:
        raise VidgenError(f"a symlog axis needs a positive linthresh, got {linthresh:g}")
    lo, hi = widen(lo, hi)
    top = max(abs(lo), abs(hi), linthresh)
    decades = max(0, math.ceil(math.log10(top / linthresh) - 1e-9))
    for step in range(1, decades + 2):
        values = [0.0] + [s * linthresh * 10.0**k for k in range(0, decades + 1, step) for s in (1.0, -1.0)]
        if decades % step:
            values += [s * linthresh * 10.0**decades for s in (1.0, -1.0)]
        values = sorted({clean(v) for v in values})
        if inside:
            chosen = [v for v in values if lo - 1e-12 * top <= v <= hi + 1e-12 * top]
        else:
            below = [v for v in values if v <= lo + 1e-12 * top] or values[:1]
            above = [v for v in values if v >= hi - 1e-12 * top] or values[-1:]
            chosen = [v for v in values if below[-1] <= v <= above[0]]
        if len(chosen) <= max(3, max_ticks):
            return chosen
    return chosen


__all__ = [
    "NICE_STEPS",
    "default_linthresh",
    "linear_step",
    "linear_ticks",
    "log_ticks",
    "symlog_inverse",
    "symlog_ticks",
    "symlog_transform",
    "widen",
]
