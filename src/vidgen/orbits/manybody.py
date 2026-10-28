"""Many bodies (Phase X, Step 232, DESIGN §98.6): the figure-eight three-body orbit, binary
stars about their barycentre, mean-motion resonances and conjunctions, whether a path bends
towards a body (the Moon's path around the Sun), and the tidal schematic's numbers. No manim.

- **The figure-eight** (Chenciner & Montgomery, *Annals of Mathematics* 152, 2000; the orbit found
  numerically by C. Moore, *Phys. Rev. Lett.* 70, 1993): three equal masses chasing one another on
  one figure-eight curve. Initial values with G = m = 1 (the values widely quoted from C. Simó's
  computation, as in Chenciner–Montgomery): x₁ = −x₂ = (0.97000436, −0.24308753), x₃ = 0,
  v₃ = (−0.93240737, −0.86473146), v₁ = v₂ = −v₃/2; period T = 6.32591398. Checked here by
  integration: the bodies return to their start after T (tests).
- **Resonances**: period ratios near small whole numbers (``nearest_ratio``), the Laplace angle
  φ = λ₁ − 3λ₂ + 2λ₃ of a 1:2:4 chain (Io–Europa–Ganymede: φ librates about 180°, so the three
  are never lined up on one side), conjunctions found as zeros of the angle between two bodies.
- **Curvature**: a path is concave towards a body when its acceleration's component normal to
  the velocity points to that body's side of the tangent: sign(v × a) = sign(v × (s − r)).
- **Tides**: the tidal (differential) acceleration GM[(d − r)/|d − r|³ − d/|d|³] at points of a
  planet's surface, the equilibrium tide's height (M_m / M_p) R⁴ / d³ under the satellite (a
  static fluid planet, no Love numbers, no oceans' dynamics)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable

import numpy as np

from vidgen.errors import VidgenError

#: The figure-eight's initial values and period (G = m = 1; Chenciner–Montgomery 2000).
FIGURE_EIGHT_X1 = (0.97000436, -0.24308753)
FIGURE_EIGHT_V3 = (-0.93240737, -0.86473146)
FIGURE_EIGHT_PERIOD = 6.32591398


@dataclass(frozen=True)
class Choreography:
    """Three bodies' starting positions (m, rows) and velocities (m/s) in their barycentre, each
    body's ``gm`` and the ``period`` (s)."""

    positions: np.ndarray
    velocities: np.ndarray
    gm: float
    period: float


def figure_eight(gm: float, length: float) -> Choreography:
    """The figure-eight for three bodies of gravitational parameter ``gm`` (m³/s²) each, scaled so
    the published unit length is ``length`` (m): velocities × √(gm/length), period × √(length³/gm)."""
    if gm <= 0 or length <= 0:
        raise VidgenError("figure-eight: give a positive mass and length")
    x1 = np.array([*FIGURE_EIGHT_X1, 0.0])
    v3 = np.array([*FIGURE_EIGHT_V3, 0.0])
    pos = np.array([x1, -x1, np.zeros(3)]) * length
    vel = np.array([-v3 / 2, -v3 / 2, v3]) * math.sqrt(gm / length)
    return Choreography(pos, vel, gm, FIGURE_EIGHT_PERIOD * math.sqrt(length**3 / gm))


def barycentre(gms: Any, positions: Any) -> np.ndarray:
    """The barycentre of bodies of gravitational parameters ``gms`` at ``positions`` (bodies
    first: ``(n, 3)`` or ``(n, T, 3)``)."""
    w = np.asarray(gms, dtype=float)
    p = np.asarray(positions, dtype=float)
    total = float(w.sum())
    if total <= 0:
        raise VidgenError("a barycentre needs at least one body with mass")
    return np.tensordot(w, p, axes=(0, 0)) / total


def binary_shares(gm1: float, gm2: float) -> tuple[float, float]:
    """How far each of two bodies sits from their barycentre, as a share of their separation:
    (m₂/(m₁ + m₂), m₁/(m₁ + m₂)) — the heavier one closer."""
    total = gm1 + gm2
    if gm1 < 0 or gm2 < 0 or total <= 0:
        raise VidgenError("a binary needs two masses, at least one positive")
    return gm2 / total, gm1 / total


def nearest_ratio(x: float, max_denominator: int = 9) -> Fraction:
    """The fraction with a small denominator nearest to ``x`` (a period ratio: 2.007 → 2)."""
    if not x > 0:
        raise VidgenError(f"a period ratio must be positive (got {x:g})")
    return Fraction(x).limit_denominator(max_denominator)


def laplace_angle(l1: Any, l2: Any, l3: Any) -> Any:
    """The Laplace angle φ = λ₁ − 3λ₂ + 2λ₃ (radians in, degrees in [0, 360) out) of three bodies'
    longitudes (inner first)."""
    return np.degrees(np.mod(np.asarray(l1) - 3 * np.asarray(l2) + 2 * np.asarray(l3), 2 * math.pi))


def conjunctions(separation: Callable[[np.ndarray], np.ndarray], span: float, step: float) -> np.ndarray:
    """The times in [0, ``span``] at which the angle between two bodies (``separation(t)``:
    λ₁ − λ₂ in radians, any winding) passes through 0 (they line up on one side), sampled every
    ``step`` and refined by bisection."""
    if span <= 0 or step <= 0:
        raise VidgenError("conjunctions need a positive span and step")
    ts = np.linspace(0.0, span, max(int(math.ceil(span / step)), 2) + 1)

    def wrapped(t: Any) -> Any:
        return np.mod(np.asarray(separation(np.atleast_1d(t)), dtype=float) + math.pi, 2 * math.pi) - math.pi

    d = wrapped(ts)
    out = []
    for k in np.flatnonzero((np.sign(d[:-1]) != np.sign(d[1:])) & (np.abs(d[:-1]) < math.pi / 2) & (np.abs(d[1:]) < math.pi / 2)):
        a, b = float(ts[k]), float(ts[k + 1])
        fa = float(d[k])
        for _ in range(60):
            m = (a + b) / 2
            fm = float(wrapped(m)[0])
            if (fm > 0) == (fa > 0):
                a, fa = m, fm
            else:
                b = m
        out.append((a + b) / 2)
    if abs(float(d[0])) < 1e-12:
        out.insert(0, 0.0)
    return np.array(out)


def bends_toward(velocity: Any, acceleration: Any, toward: Any) -> np.ndarray:
    """At each sample, whether the path (velocity, acceleration) curves towards the direction
    ``toward`` (rows of 2- or 3-vectors, the xy plane): sign(v × a) = sign(v × toward)."""
    v, a, s = (np.atleast_2d(np.asarray(x, dtype=float)) for x in (velocity, acceleration, toward))
    bend = v[:, 0] * a[:, 1] - v[:, 1] * a[:, 0]
    side = v[:, 0] * s[:, 1] - v[:, 1] * s[:, 0]
    return np.sign(bend) == np.sign(side)


def tidal_acceleration(gm: float, satellite: Any, points: Any) -> np.ndarray:
    """The tidal acceleration (m/s²) a body of ``gm`` at ``satellite`` (m, from the planet's
    centre) causes at ``points`` (m, from the centre): its pull there minus its pull at the
    centre."""
    d = np.asarray(satellite, dtype=float)
    p = np.atleast_2d(np.asarray(points, dtype=float))
    rel = d[None, :] - p
    return gm * (rel / np.linalg.norm(rel, axis=1)[:, None] ** 3 - d / np.linalg.norm(d) ** 3)


def equilibrium_tide(gm_satellite: float, gm_planet: float, radius: float, distance: float) -> float:
    """The equilibrium tide's height (m) under the satellite: (M_s / M_p) R⁴ / d³ (a fluid planet
    with no Love numbers; the far side's bulge is as high, the ring between them is half as deep)."""
    if min(gm_satellite, gm_planet, radius, distance) <= 0:
        raise VidgenError("the tide needs positive masses, radius and distance")
    return gm_satellite / gm_planet * radius**4 / distance**3


__all__ = ["FIGURE_EIGHT_PERIOD", "FIGURE_EIGHT_V3", "FIGURE_EIGHT_X1", "Choreography", "barycentre", "bends_toward", "binary_shares", "conjunctions",
           "equilibrium_tide", "figure_eight", "laplace_angle", "nearest_ratio", "tidal_acceleration"]
