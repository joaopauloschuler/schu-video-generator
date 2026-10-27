"""Integrators for systems of ordinary differential equations ``dy/dt = f(t, y)`` (Phase W,
DESIGN §97.7), numpy only and deterministic: the classical Runge–Kutta method with a fixed step
(:func:`rk4`), the adaptive Dormand–Prince 5(4) pair (:func:`rk45`, the method of scipy's
``RK45``) and the symplectic velocity Verlet / leapfrog scheme for ``x'' = a(t, x)``
(:func:`verlet`), which keeps the energy of a conservative system bounded over long times
where RK4 drifts. Each returns the solution at the output times; a solution that blows up
(not finite, or beyond :data:`BLOW_UP` times its starting size) or an adaptive step that
collapses (a stiff or singular system) raises :class:`IntegrationError` saying where."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np

from vidgen.errors import VidgenError

#: ``f(t, y) -> dy/dt`` for a state vector ``y``.
Rhs = Callable[[float, np.ndarray], np.ndarray]
#: A solution counts as blown up beyond this many times max(1, its largest starting value).
BLOW_UP = 1e12
#: The most steps a fixed-step integration may take.
MAX_STEPS = 2_000_000
#: The most steps the adaptive method may take (more means a stiff system).
MAX_ADAPTIVE_STEPS = 100_000
#: Hairer's stiffness test for Dormand–Prince: h·|λ| above this on :data:`STIFF_STEPS`
#: accepted steps (six calm steps in a row reset the count) means the step is held by
#: stability, not accuracy.
STIFF_LIMIT, STIFF_STEPS = 2.5, 30
#: A stiff system is refused only when it would still need more than this many steps.
STIFF_BUDGET = 20_000


class IntegrationError(VidgenError):
    """An integration failed: ``kind`` is ``blow_up``, ``stiff`` or ``steps``; ``time`` where;
    ``variable`` the index of the state variable that blew up (or ``None``)."""

    def __init__(self, message: str, kind: str, time: float, variable: int | None = None) -> None:
        super().__init__(message)
        self.kind, self.time, self.variable = kind, time, variable


def _check(y: np.ndarray, t: float, limit: float) -> None:
    bad = ~np.isfinite(y) | (np.abs(y) > limit)
    if np.any(bad):
        k = int(np.flatnonzero(bad)[0])
        raise IntegrationError(f"the solution blows up near t = {t:.4g}", "blow_up", t, k)


def _limit(y0: np.ndarray) -> float:
    return BLOW_UP * max(1.0, float(np.max(np.abs(y0))) if len(y0) else 1.0)


def output_times(t0: float, t1: float, step: float, samples: int | None) -> np.ndarray:
    """The times a fixed-step integration reports: every step from ``t0`` to ``t1`` (the last
    step shortened to end on ``t1``), thinned to about ``samples`` evenly spaced steps."""
    n = max(1, math.ceil((t1 - t0) / step - 1e-9))
    if n > MAX_STEPS:
        raise IntegrationError(f"a step of {step:g} needs {n:,} steps from t = {t0:g} to {t1:g} (at most {MAX_STEPS:,}); use a larger step or method: rk45",
                               "steps", t0)
    every = max(1, math.ceil(n / samples)) if samples else 1
    idx = list(range(0, n + 1, every))
    if idx[-1] != n:
        idx.append(n)
    return np.array([min(t0 + k * step, t1) for k in idx])


def rk4(f: Rhs, t0: float, y0: Sequence[float], t1: float, step: float, *, samples: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Classical fourth-order Runge–Kutta with a fixed ``step`` from ``t0`` to ``t1``:
    ``(times, states)`` with ``states[k]`` the state at ``times[k]`` (thinned to about
    ``samples`` outputs). Global error O(step⁴)."""
    y = np.asarray(y0, dtype=float).copy()
    limit = _limit(y)
    outs = output_times(t0, t1, step, samples)
    states = [y.copy()]
    t = t0
    for target in outs[1:]:
        while t < target - 1e-12 * max(1.0, abs(target)):
            h = min(step, target - t)
            k1 = f(t, y)
            k2 = f(t + h / 2, y + h / 2 * k1)
            k3 = f(t + h / 2, y + h / 2 * k2)
            k4 = f(t + h, y + h * k3)
            y = y + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
            t += h
            _check(y, t, limit)
        t = float(target)
        states.append(y.copy())
    return outs, np.array(states)


# Dormand–Prince 5(4) coefficients (the tableau of scipy's RK45)
_C = np.array([0, 1 / 5, 3 / 10, 4 / 5, 8 / 9, 1])
_A = [
    [],
    [1 / 5],
    [3 / 40, 9 / 40],
    [44 / 45, -56 / 15, 32 / 9],
    [19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729],
    [9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656],
]
_B = np.array([35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84])
_E = np.array([71 / 57600, 0, -71 / 16695, 71 / 1920, -17253 / 339200, 22 / 525, -1 / 40])


def rk45(
    f: Rhs,
    t0: float,
    y0: Sequence[float],
    t1: float,
    *,
    times: Sequence[float],
    rtol: float = 1e-6,
    atol: float = 1e-9,
    first_step: float | None = None,
    max_step: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Adaptive Dormand–Prince 5(4) from ``t0`` to ``t1``, reporting the state at ``times``
    (increasing, inside ``[t0, t1]``; steps end on each of them, so outputs are exact to the
    tolerance). Error per step below ``atol + rtol·|y|`` (RMS norm, as scipy). A step that must
    shrink below 10⁻¹² of the span raises an ``IntegrationError`` of kind ``stiff``."""
    y = np.asarray(y0, dtype=float).copy()
    limit = _limit(y)
    span = t1 - t0
    outs = np.asarray(times, dtype=float)
    h_nat = first_step or span / 100   # the step the error control asks for (before ending on an output time)
    h_max = max_step or span
    t = t0
    states = []
    steps = stiff_steps = calm_steps = 0
    k_first = f(t, y)
    for target in outs:
        while t < target - 1e-12 * max(1.0, abs(target)):
            h = min(h_nat, h_max, target - t)
            clamped = h < h_nat
            if h < 1e-12 * span:
                raise IntegrationError(f"the adaptive step had to shrink below {h:.3g} near t = {t:.4g}: the system looks stiff or singular there",
                                       "stiff", t)
            ks = [k_first]
            stage = y
            for i in range(1, 6):
                stage = y + h * sum(a * k for a, k in zip(_A[i], ks))
                ks.append(f(t + _C[i] * h, stage))
            y_new = y + h * sum(b * k for b, k in zip(_B, ks))
            k7 = f(t + h, y_new)
            err = h * sum(e * k for e, k in zip(_E, [*ks, k7]))
            scale = atol + rtol * np.maximum(np.abs(y), np.abs(y_new))
            norm = float(np.sqrt(np.mean((err / scale) ** 2))) if len(y) else 0.0
            steps += 1
            if steps > MAX_ADAPTIVE_STEPS:
                raise IntegrationError(f"more than {MAX_ADAPTIVE_STEPS:,} adaptive steps by t = {t:.4g} (of {t0:g} to {t1:g}): the system looks stiff "
                                       "(very different time scales); loosen the tolerance, shorten t or use method: rk4 with a small step", "stiff", t)
            if not math.isfinite(norm):
                h_nat = h / 4
                continue
            if norm <= 1.0:
                # Hairer's test: h·|λ| ≈ h·|k7 − k6| / |y_new − stage6| near the edge of the
                # method's stability region (3.3) for many steps in a row means a stiff system
                dy = float(np.linalg.norm(y_new - stage))
                if dy > 0 and h * float(np.linalg.norm(k7 - ks[5])) / dy > STIFF_LIMIT:
                    stiff_steps, calm_steps = stiff_steps + 1, 0
                    if stiff_steps >= STIFF_STEPS and (t1 - t) / h > STIFF_BUDGET:   # a short stiff stretch is just slow
                        raise IntegrationError(f"the system is stiff near t = {t:.4g} (a fast decay forces tiny steps): the adaptive method would need "
                                               "a very small step for its whole time; shorten t, rescale the fast rate, or use method: rk4 with a small step", "stiff", t)
                else:
                    calm_steps += 1
                    if calm_steps >= 6:   # Hairer: six calm steps in a row reset the count
                        stiff_steps = 0
                t, y, k_first = t + h, y_new, k7
                _check(y, t, limit)
                grown = h * (min(5.0, max(0.2, 0.9 * norm ** -0.2)) if norm > 0 else 5.0)
                h_nat = max(h_nat, grown) if clamped else grown
            else:
                h_nat = h * max(0.2, 0.9 * norm ** -0.2)
        t = float(target) if abs(t - target) <= 1e-12 * max(1.0, abs(target)) else t
        states.append(y.copy())
    return outs, np.array(states)


def verlet(
    accel: Callable[[float, np.ndarray], np.ndarray],
    t0: float,
    x0: Sequence[float],
    v0: Sequence[float],
    t1: float,
    step: float,
    *,
    samples: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Velocity Verlet (leapfrog in kick-drift-kick form) for ``x'' = accel(t, x)`` with a fixed
    ``step``: ``(times, positions, velocities)``. Symplectic and time-reversible: for a
    conservative force the energy error stays bounded (it oscillates, O(step²)) instead of
    drifting."""
    x = np.asarray(x0, dtype=float).copy()
    v = np.asarray(v0, dtype=float).copy()
    limit = _limit(np.concatenate([x, v]))
    outs = output_times(t0, t1, step, samples)
    xs, vs = [x.copy()], [v.copy()]
    t = t0
    a = accel(t, x)
    for target in outs[1:]:
        while t < target - 1e-12 * max(1.0, abs(target)):
            h = min(step, target - t)
            v_half = v + h / 2 * a
            x = x + h * v_half
            t += h
            a = accel(t, x)
            v = v_half + h / 2 * a
            _check(np.concatenate([x, v]), t, limit)
        t = float(target)
        xs.append(x.copy())
        vs.append(v.copy())
    return outs, np.array(xs), np.array(vs)


__all__ = ["BLOW_UP", "MAX_ADAPTIVE_STEPS", "MAX_STEPS", "STIFF_BUDGET", "STIFF_LIMIT", "STIFF_STEPS", "IntegrationError", "Rhs", "output_times", "rk4", "rk45", "verlet"]
