"""N-body motion: every body with mass pulls on every other (Phase X, DESIGN §98), integrated
with Phase W's integrators (:mod:`vidgen.plotcore.integrate`): velocity Verlet / leapfrog
(symplectic: the energy error stays bounded over many orbits, the default) or adaptive
Dormand–Prince RK45 (accurate over a short run, but its energy drifts). The equations are solved
in scaled units (the largest starting distance, and the time in which the total mass would make a
body go 1 radian around at that distance), so positions and velocities have the same tolerance.
No manim."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.plotcore import IntegrationError, rk45, verlet

from .system import System

#: Integration methods and other spellings of them.
METHODS = ("leapfrog", "rk45")
METHOD_ALIASES = {"verlet": "leapfrog", "velocity_verlet": "leapfrog", "symplectic": "leapfrog", "adaptive": "rk45", "rk": "rk45"}
#: A leapfrog step is this share of the shortest dynamical time (2π √(q³/μ), q a periapsis).
STEPS_PER_ORBIT = 1000
#: RK45's relative tolerance.
RK45_RTOL = 1e-10


@dataclass(frozen=True)
class NBodyRun:
    """The bodies' motion: ``names`` (the central body first), output ``times`` (s), positions
    and velocities relative to the central body (``(bodies, N, 3)``, m and m/s), the system's
    ``energy`` at each output (see :func:`simulate`), the ``method`` and its ``step`` (s;
    ``None`` for RK45)."""

    names: tuple[str, ...]
    times: np.ndarray
    positions: np.ndarray
    velocities: np.ndarray
    energy: np.ndarray
    method: str
    step: float | None

    @property
    def drift(self) -> float:
        """The largest relative change of the energy: max |E − E₀| / max(|E₀|, max |E|)."""
        e = self.energy
        scale = max(abs(float(e[0])), float(np.max(np.abs(e))))
        return float(np.max(np.abs(e - e[0])) / scale) if scale > 0 else 0.0

    def position(self, name: str, t: Any) -> np.ndarray:
        """Position relative to the central body at time(s) ``t``, between the outputs by cubic
        Hermite interpolation of positions and velocities (third-order accurate)."""
        try:
            k = self.names.index(name)
        except ValueError:
            raise VidgenError(f"no body '{name}' in the n-body run (bodies: {', '.join(self.names)})") from None
        ts = np.atleast_1d(np.asarray(t, dtype=float))
        times = self.times
        j = np.clip(np.searchsorted(times, ts, side="right") - 1, 0, len(times) - 2)
        h = times[j + 1] - times[j]
        s = np.clip((ts - times[j]) / h, 0.0, 1.0)[:, None]
        hh = h[:, None]
        p0, p1 = self.positions[k, j], self.positions[k, j + 1]
        v0, v1 = self.velocities[k, j], self.velocities[k, j + 1]
        out = ((2 * s**3 - 3 * s**2 + 1) * p0 + (s**3 - 2 * s**2 + s) * hh * v0 + (-2 * s**3 + 3 * s**2) * p1 + (s**3 - s**2) * hh * v1)
        return out[0] if np.ndim(t) == 0 else out


def method_name(method: str) -> str:
    """``leapfrog`` or ``rk45`` from a method or one of its other spellings."""
    m = METHOD_ALIASES.get(method, method)
    if m not in METHODS:
        raise VidgenError(f"method '{method}' is not one of {', '.join(METHODS)} (or {', '.join(METHOD_ALIASES)})")
    return m


def default_step(system: System) -> float:
    """The leapfrog step (s): 1/:data:`STEPS_PER_ORBIT` of the shortest time scale of the
    system, 2π √(q³/μ) over the orbiters (q its periapsis distance, μ its parent's)."""
    scales = [2 * math.pi * math.sqrt(o.elements.periapsis**3 / o.elements.mu) for o in system.orbiters]
    return min(scales) / STEPS_PER_ORBIT


def simulate(system: System, span: float, *, method: str = "leapfrog", step: float | None = None, samples: int = 2000) -> NBodyRun:
    """Integrate the system from its Kepler states at t = 0 for ``span`` seconds, every body
    with ``gm`` > 0 pulling on all others (bodies of ``gm`` 0 are test particles). ``step``:
    the leapfrog step (default :func:`default_step`). The energy is the total
    Σ ½ GMᵢ vᵢ² − Σ GMᵢ GMⱼ / rᵢⱼ (the energy times G, in the barycentre's frame) when more than
    one body has mass; with the central body's mass alone, the test particles' specific energies
    ½ v² − GM/r added up."""
    method = method_name(method)
    if span <= 0:
        raise VidgenError(f"an n-body run needs a positive time span (got {span:g} s)")
    names = (system.central.name, *system.names)
    gm = np.array([system.central.gm] + [o.body.gm for o in system.orbiters], dtype=float)
    n = len(names)
    r0, v0 = np.zeros((n, 3)), np.zeros((n, 3))
    for k, name in enumerate(system.names, start=1):
        r0[k], v0[k] = system.state(name, 0.0)
    total = float(gm.sum())
    r0 -= (gm[:, None] * r0).sum(axis=0) / total   # barycentric
    v0 -= (gm[:, None] * v0).sum(axis=0) / total
    length = float(np.max(np.linalg.norm(r0[:, None] - r0[None, :], axis=-1)))
    unit_t = math.sqrt(length**3 / total)
    unit_v = length / unit_t
    w = gm / total   # scaled GM

    def accel(_: float, x: np.ndarray) -> np.ndarray:
        pos = x.reshape(n, 3)
        d = pos[None, :, :] - pos[:, None, :]   # d[i, j] = r_j − r_i
        r2 = np.einsum("ijk,ijk->ij", d, d)
        np.fill_diagonal(r2, np.inf)
        return (w[None, :, None] * d * r2[:, :, None] ** -1.5).sum(axis=1).ravel()

    x0, u0 = (r0 / length).ravel(), (v0 / unit_v).ravel()
    try:
        if method == "leapfrog":
            h = (step if step is not None else default_step(system)) / unit_t
            if h <= 0:
                raise VidgenError(f"step must be positive (got {step:g} s)")
            times, xs, us = verlet(accel, 0.0, x0, u0, span / unit_t, h, samples=samples)
        else:
            out = np.linspace(0.0, span / unit_t, samples + 1)
            y0 = np.concatenate([x0, u0])
            m = 3 * n
            times, ys = rk45(lambda t, y: np.concatenate([y[m:], accel(t, y[:m])]), 0.0, y0, span / unit_t, times=out, rtol=RK45_RTOL, atol=RK45_RTOL)
            xs, us = ys[:, :m], ys[:, m:]
            h = None
    except IntegrationError as error:
        when = error.time * unit_t
        raise VidgenError(f"n-body: {error} (at t = {when:.4g} s): a close encounter or a collision? try a smaller step or method: rk45") from None
    pos = xs.reshape(len(times), n, 3).transpose(1, 0, 2) * length
    vel = us.reshape(len(times), n, 3).transpose(1, 0, 2) * unit_v
    energy = _energy(gm, pos, vel)
    return NBodyRun(names, np.asarray(times) * unit_t, pos - pos[0], vel - vel[0], energy, method, None if h is None else h * unit_t)


def _energy(gm: np.ndarray, pos: np.ndarray, vel: np.ndarray) -> np.ndarray:
    """The conserved energy at each output (see :func:`simulate`)."""
    massive = np.flatnonzero(gm > 0)
    if len(massive) > 1:
        kinetic = 0.5 * np.einsum("i,itk,itk->t", gm, vel, vel)
        potential = np.zeros(pos.shape[1])
        for a, i in enumerate(massive):
            for j in massive[a + 1:]:
                potential -= gm[i] * gm[j] / np.linalg.norm(pos[i] - pos[j], axis=-1)
        return kinetic + potential
    c = massive[0]
    out = np.zeros(pos.shape[1])
    for k in range(len(gm)):
        if k != c:
            dv = vel[k] - vel[c]
            out += 0.5 * np.einsum("tk,tk->t", dv, dv) - gm[c] / np.linalg.norm(pos[k] - pos[c], axis=-1)
    return out


__all__ = ["METHODS", "METHOD_ALIASES", "RK45_RTOL", "STEPS_PER_ORBIT", "NBodyRun", "default_step", "method_name", "simulate"]
