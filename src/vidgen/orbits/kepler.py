"""Kepler's equation and the anomalies of a conic orbit (Phase X, DESIGN §98), numpy only.

The mean anomaly ``M`` grows uniformly with time, ``M = n (t − T)`` (``T`` the time of
periapsis passage, ``n`` the mean motion of :func:`mean_motion`), and the true anomaly ``ν`` is
the angle from periapsis seen from the focus. Between them lies Kepler's equation:

- ellipse (0 ≤ e < 1): ``M = E − e sin E`` (``E`` the eccentric anomaly), solved by Newton's
  method from Danby's start ``E₀ = M + 0.85 e·sign(sin M)``;
- parabola (e = 1): Barker's equation ``M = D + D³/3`` with ``D = tan(ν/2)`` and
  ``n = 2 √(μ/p³)``, solved in closed form (Cardano);
- hyperbola (e > 1): ``M = e sinh H − H``, solved by Newton's method.

Every function takes floats or numpy arrays (element-wise) and returns the same kind."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from vidgen.errors import VidgenError

#: An eccentricity within this of 1 is a parabola (Barker's equation).
PARABOLIC_TOLERANCE = 1e-9
#: Newton iterations allowed before a solver gives up (it converges in a few).
MAX_ITERATIONS = 60

Number = Any   # float or numpy array


def _out(x: np.ndarray, like: Number) -> Number:
    return float(x) if np.ndim(like) == 0 else x


def kind_of(e: float) -> str:
    """``ellipse`` (e < 1, a circle included), ``parabola`` (e = 1 within
    :data:`PARABOLIC_TOLERANCE`) or ``hyperbola`` (e > 1)."""
    if e < 0:
        raise VidgenError(f"an eccentricity cannot be negative (got {e:g})")
    if abs(e - 1.0) <= PARABOLIC_TOLERANCE:
        return "parabola"
    return "ellipse" if e < 1 else "hyperbola"


def wrap_angle(angle: Number) -> Number:
    """``angle`` brought into [−π, π)."""
    a = np.asarray(angle, dtype=float)
    return _out((a + math.pi) % (2 * math.pi) - math.pi, angle)


def eccentric_anomaly(mean: Number, e: float) -> Number:
    """``E`` with ``E − e sin E = M`` (ellipse, 0 ≤ e < 1), in the same turn as ``M`` (no
    wrapping: ``M`` = 2π + 0.1 gives ``E`` ≈ 2π + …)."""
    m = np.asarray(mean, dtype=float)
    turns = np.round(m / (2 * math.pi))
    r = m - 2 * math.pi * turns   # in [−π, π]
    x = r + 0.85 * e * np.sign(np.sin(r))
    # E − e sin E written as (E − sin E) + (1 − e) sin E: no cancellation near e = 1, E = 0
    x = _newton(lambda x: _x_minus_sin(x) + (1.0 - e) * np.sin(x) - r, lambda x: 1.0 - e * np.cos(x), x, f"Kepler's equation (e = {e:g})")
    return _out(x + 2 * math.pi * turns, mean)


def hyperbolic_anomaly(mean: Number, e: float) -> Number:
    """``H`` with ``e sinh H − H = M`` (hyperbola, e > 1)."""
    m = np.asarray(mean, dtype=float)
    x = np.sign(m) * np.log(2 * np.abs(m) / e + 1.8)
    # e sinh H − H written as (sinh H − H) + (e − 1) sinh H (no cancellation near e = 1, H = 0)
    x = _newton(lambda x: _sinh_minus_x(x) + (e - 1.0) * np.sinh(x) - m, lambda x: e * np.cosh(x) - 1.0, x, f"the hyperbolic Kepler equation (e = {e:g})")
    return _out(x, mean)


def _newton(f: Any, fprime: Any, x: np.ndarray, what: str) -> np.ndarray:
    """Newton's method from ``x`` until every step is below 10⁻¹² of its value, then one more
    step (quadratic convergence: the result is at rounding level)."""
    for _ in range(MAX_ITERATIONS):
        step = f(x) / fprime(x)
        x = x - step
        if np.all(np.abs(step) <= 1e-12 * np.abs(x) + 1e-300):
            return x - f(x) / fprime(x)
    raise VidgenError(f"{what} did not converge")


def _series(x: np.ndarray, sign: float) -> np.ndarray:
    """x³/3! ± x⁵/5! + x⁷/7! ± … to x¹⁹ (``sign`` −1 alternates): sinh x − x or x − sin x for
    |x| < 0.5, where subtracting the functions would cancel."""
    term = x**3 / 6.0
    total = term.copy()
    for k in range(2, 10):
        term = term * sign * x * x / ((2 * k) * (2 * k + 1))
        total = total + term
    return total


def _sinh_minus_x(x: np.ndarray) -> np.ndarray:
    return np.where(np.abs(x) < 0.5, _series(x, 1.0), np.sinh(x) - x)


def _x_minus_sin(x: np.ndarray) -> np.ndarray:
    return np.where(np.abs(x) < 0.5, _series(x, -1.0), x - np.sin(x))


def parabolic_anomaly(mean: Number) -> Number:
    """``D = tan(ν/2)`` with Barker's ``D + D³/3 = M``, in closed form:
    ``D = ∛(B + s) − ∛(s − B)``, ``B = 3M/2``, ``s = √(B² + 1)`` (the difference written
    without cancellation)."""
    b = 1.5 * np.asarray(mean, dtype=float)
    s = np.sqrt(b * b + 1.0)
    big = np.where(b >= 0, b + s, 1.0 / (s - b))   # B + s, also for B ≪ 0
    root = np.cbrt(big)
    return _out(root - 1.0 / root, mean)   # ∛(s − B) = 1/∛(s + B)


def true_from_mean(mean: Number, e: float) -> Number:
    """The true anomaly ν of mean anomaly ``M`` (see the module for each kind's ``M``)."""
    kind = kind_of(e)
    if kind == "parabola":
        return _out(2.0 * np.arctan(np.asarray(parabolic_anomaly(mean))), mean)
    if kind == "hyperbola":
        h = np.asarray(hyperbolic_anomaly(mean, e))
        return _out(2.0 * np.arctan(math.sqrt((e + 1) / (e - 1)) * np.tanh(h / 2)), mean)
    big_e = np.asarray(eccentric_anomaly(mean, e))
    turns = np.round(big_e / (2 * math.pi))
    r = big_e - 2 * math.pi * turns
    nu = 2.0 * np.arctan2(math.sqrt(1 + e) * np.sin(r / 2), math.sqrt(1 - e) * np.cos(r / 2))
    return _out(nu + 2 * math.pi * turns, mean)


def mean_from_true(nu: Number, e: float) -> Number:
    """The mean anomaly of true anomaly ``ν`` (an open orbit's ν must lie between its
    asymptotes, ``|ν| < acos(−1/e)``)."""
    kind = kind_of(e)
    v = np.asarray(nu, dtype=float)
    if kind == "parabola":
        d = np.tan(v / 2)
        return _out(d + d**3 / 3, nu)
    if kind == "hyperbola":
        limit = math.acos(-1.0 / e)
        if np.any(np.abs(v) >= limit):
            raise VidgenError(f"a true anomaly of {float(np.max(np.abs(v))) * 180 / math.pi:.4g}° lies beyond the asymptotes of this hyperbola "
                              f"(|ν| < {limit * 180 / math.pi:.4g}° for e = {e:g})")
        h = 2.0 * np.arctanh(math.sqrt((e - 1) / (e + 1)) * np.tan(v / 2))
        return _out(_sinh_minus_x(h) + (e - 1.0) * np.sinh(h), nu)
    turns = np.round(v / (2 * math.pi))
    r = v - 2 * math.pi * turns
    big_e = 2.0 * np.arctan2(math.sqrt(1 - e) * np.sin(r / 2), math.sqrt(1 + e) * np.cos(r / 2))
    return _out(_x_minus_sin(big_e) + (1.0 - e) * np.sin(big_e) + 2 * math.pi * turns, nu)


def mean_motion(mu: float, p: float, e: float) -> float:
    """``n`` (rad/s) of the conic with semi-latus rectum ``p`` around ``μ``: √(μ/|a|³) for an
    ellipse or a hyperbola, 2√(μ/p³) for a parabola (Barker's convention above)."""
    if kind_of(e) == "parabola":
        return 2.0 * math.sqrt(mu / p**3)
    a = abs(p / (1.0 - e * e))
    return math.sqrt(mu / a**3)


__all__ = [
    "MAX_ITERATIONS",
    "PARABOLIC_TOLERANCE",
    "eccentric_anomaly",
    "hyperbolic_anomaly",
    "kind_of",
    "mean_from_true",
    "mean_motion",
    "parabolic_anomaly",
    "true_from_mean",
    "wrap_angle",
]
