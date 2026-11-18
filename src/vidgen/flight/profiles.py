"""Smooth functions of time a flight is made of (Step 385, DESIGN.md §123.7).

Every change of a flight's speed, vertical rate, bank or turn rate goes through :func:`step`, the
septic smoothstep S(u) = 35u⁴ − 84u⁵ + 70u⁶ − 20u⁷, whose first three derivatives are zero at
both ends: a quantity that moves between two steady values this way joins them with its first
three derivatives continuous, so position is smooth to its third derivative (and attitude, which
follows the acceleration, has no kink) where manoeuvres meet. Its peak slope is 35/16 times the
mean (:data:`PEAK`). A :class:`Channel` is a list of pieces in time, each a function of time;
derivatives are central differences of the functions (they are smooth where pieces meet).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

#: The septic smoothstep's greatest slope over its mean: S'(1/2) = 35/16.
PEAK = 35.0 / 16.0
#: The time step of the central differences (s).
DELTA = 0.01

Fn = Callable[[np.ndarray], np.ndarray]


def step(u: np.ndarray | float) -> np.ndarray:
    """S(u) on [0, 1] (0 before, 1 after)."""
    u = np.clip(np.asarray(u, dtype=float), 0.0, 1.0)
    return u**4 * (35 - 84 * u + 70 * u * u - 20 * u**3)


def step_integral(u: np.ndarray | float) -> np.ndarray:
    """∫₀ᵘ S (u clipped to [0, 1]; ½ at 1, then growing by 1 a unit of u)."""
    v = np.asarray(u, dtype=float)
    w = np.clip(v, 0.0, 1.0)
    return w**5 * (7 - 14 * w + 10 * w * w - 2.5 * w**3) + np.maximum(v - 1.0, 0.0)


def bump(s: np.ndarray) -> np.ndarray:
    """(1 − s²)⁴ on [−1, 1], 0 outside: a smoothing kernel whose first three derivatives vanish at its ends."""
    s = np.asarray(s, dtype=float)
    return np.where(np.abs(s) < 1, (1 - s * s) ** 4, 0.0)


#: ∫ bump over [−1, 1] and its variance (for a half-width w: w² / 11).
BUMP_AREA = 256.0 / 315.0
BUMP_VARIANCE = 1.0 / 11.0


def ramp(t0: float, duration: float, a: float, b: float) -> Fn:
    """A value going from ``a`` to ``b`` over [t0, t0 + duration] by S."""
    if duration <= 0:
        return lambda t: np.full(np.shape(t), float(b))
    return lambda t: a + (b - a) * step((np.asarray(t, dtype=float) - t0) / duration)


def rate_ramp(t0: float, duration: float, value: float, rate_from: float, rate_to: float) -> Fn:
    """The integral of a rate going from ``rate_from`` to ``rate_to`` over [t0, t0 + duration] by S,
    starting at ``value``: value + rate_from·(t − t0) + (rate_to − rate_from)·duration·∫S."""
    if duration <= 0:
        return lambda t: value + rate_to * (np.asarray(t, dtype=float) - t0)

    def fn(t: np.ndarray) -> np.ndarray:
        dt = np.asarray(t, dtype=float) - t0
        return value + rate_from * dt + (rate_to - rate_from) * duration * step_integral(dt / duration)
    return fn


def blend(t0: float, duration: float, first: Fn, second: Fn) -> Fn:
    """``first`` turning into ``second`` over [t0, t0 + duration]: (1 − S)·first + S·second."""
    def fn(t: np.ndarray) -> np.ndarray:
        w = step((np.asarray(t, dtype=float) - t0) / duration)
        return (1 - w) * first(t) + w * second(t)
    return fn


@dataclass
class Channel:
    """A quantity over time: pieces ``(start, fn)`` in order (each holds from its start to the next's);
    before the first piece the first one's function is used."""

    pieces: list[tuple[float, Fn]] = field(default_factory=list)

    def add(self, start: float, fn: Fn) -> None:
        """A new piece from ``start`` on (pieces after it are dropped)."""
        self.pieces = [p for p in self.pieces if p[0] < start - 1e-12] + [(float(start), fn)]

    def __call__(self, t: np.ndarray | float) -> np.ndarray:
        t = np.asarray(t, dtype=float)
        flat = t.reshape(-1)
        out = np.empty_like(flat)
        starts = np.array([p[0] for p in self.pieces])
        which = np.clip(np.searchsorted(starts, flat, side="right") - 1, 0, len(self.pieces) - 1)
        for k, (_, fn) in enumerate(self.pieces):
            sel = which == k
            if sel.any():
                out[sel] = fn(flat[sel])
        return out.reshape(t.shape)

    def derivative(self, t: np.ndarray | float, order: int = 1, delta: float = DELTA) -> np.ndarray:
        """The ``order``-th derivative (1 to 3) by central differences of step ``delta``."""
        t = np.asarray(t, dtype=float)
        if order == 1:
            return (self(t - 2 * delta) - 8 * self(t - delta) + 8 * self(t + delta) - self(t + 2 * delta)) / (12 * delta)
        if order == 2:
            return (-self(t - 2 * delta) + 16 * self(t - delta) - 30 * self(t) + 16 * self(t + delta) - self(t + 2 * delta)) / (12 * delta * delta)
        if order == 3:
            return (-self(t - 2 * delta) + 2 * self(t - delta) - 2 * self(t + delta) + self(t + 2 * delta)) / (2 * delta**3)
        raise ValueError("order 1 to 3")


def constant(value: float) -> Fn:
    return lambda t: np.full(np.shape(t), float(value))


def linear(t0: float, value: float, rate: float) -> Fn:
    return lambda t: value + rate * (np.asarray(t, dtype=float) - t0)


__all__ = ["BUMP_AREA", "BUMP_VARIANCE", "Channel", "DELTA", "PEAK", "blend", "bump", "constant", "linear", "ramp", "rate_ramp", "step", "step_integral"]
