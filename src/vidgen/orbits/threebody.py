"""The circular restricted three-body problem (Phase X, Step 232, DESIGN §98.6): two primaries
on circles about their barycentre and a massless body moving in their field, written in the frame
that turns with them. No manim.

Units in the rotating frame are the usual normalised ones: the primaries' separation is 1, their
angular speed Ω is 1 (one turn takes 2π), the total mass is 1; the mass ratio μ = m₂ / (m₁ + m₂)
puts the larger primary at (−μ, 0) and the smaller at (1 − μ, 0), the barycentre at the origin.

- The **Lagrange points**: the collinear L1 (between the primaries), L2 (beyond the smaller), L3
  (beyond the larger) are the real positive roots γ of Szebehely's quintics (*Theory of Orbits*,
  1967, §4.4; γ the distance from the nearer primary, from the larger for L3), found by
  ``numpy.roots`` and polished by Newton's method on the quintic; L4 / L5 are the apexes of the
  equilateral triangles on the primaries, (½ − μ, ±√3/2).
- **Routh's criterion** (1875): L4 and L5 are linearly stable for μ < μ_R = (1 − √(23/27)) / 2
  = 0.038 520 9 (Gascheau's 27 μ(1 − μ) < 1).
- The **Jacobi constant** C = x² + y² + 2(1 − μ)/r₁ + 2μ/r₂ − (ẋ² + ẏ²), conserved by the motion;
  its zero-velocity curves (where 2Ω(x, y) = C) bound the regions the body can reach.
- The equations of motion in the rotating frame (ẍ − 2ẏ = ∂Ω/∂x, ÿ + 2ẋ = ∂Ω/∂y) integrated with
  Phase W's adaptive RK45 (the Coriolis term depends on the velocity, so leapfrog is not
  symplectic here; the ``orbit`` scene integrates the same problem as n-body in the inertial frame
  instead, where it is).

Sources for the checks (tests): Koon, Lo, Marsden & Ross, *Dynamical Systems, the Three-Body
Problem and Space Mission Design* (2011), the Earth–Moon γ₁ = 0.150 934, γ₂ = 0.167 833 and the
Sun–Earth+Moon γ₁ = 0.010 011, γ₂ = 0.010 078 (L1 / L2 about 1.5 million km from the Earth)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.plotcore import IntegrationError, did_you_mean, rk45

from .bodies import BODIES, GM_EARTH, ORBITS, Body
from .values import AU

#: Routh's critical mass ratio: L4 / L5 are stable for μ below it.
ROUTH_MU = (1 - math.sqrt(23 / 27)) / 2
#: The names of the five points.
LAGRANGE_NAMES = ("L1", "L2", "L3", "L4", "L5")
#: RK45 tolerance of :func:`integrate`.
RTOL = 1e-11


def routh_stable(mu: float) -> bool:
    """Whether L4 and L5 are (linearly) stable for the mass ratio ``mu`` (Routh: μ < 0.038 52)."""
    return 0 < mu < ROUTH_MU


def _check_mu(mu: float) -> None:
    if not 0 < mu <= 0.5:
        raise VidgenError(f"the mass ratio μ = m₂/(m₁ + m₂) lies between 0 and 0.5 (got {mu:g})")


def collinear_gamma(mu: float, point: str) -> float:
    """γ of a collinear point: L1 and L2 its distance from the smaller primary, L3 from the
    larger (the real positive root of Szebehely's quintic, Newton-polished)."""
    _check_mu(mu)
    coeffs = {
        "L1": [1.0, -(3 - mu), 3 - 2 * mu, -mu, 2 * mu, -mu],
        "L2": [1.0, 3 - mu, 3 - 2 * mu, -mu, -2 * mu, -mu],
        "L3": [1.0, 2 + mu, 1 + 2 * mu, -(1 - mu), -2 * (1 - mu), -(1 - mu)],
    }
    if point not in coeffs:
        raise VidgenError(f"'{point}' is not a collinear point (L1, L2, L3)")
    c = np.array(coeffs[point])
    roots = [r.real for r in np.roots(c) if abs(r.imag) < 1e-7 * max(1.0, abs(r)) and r.real > 0]
    if not roots:   # pragma: no cover - each quintic has one positive real root (Descartes)
        raise VidgenError(f"no positive root for {point} at μ = {mu:g}")
    g = min(roots, key=lambda r: abs(np.polyval(c, r)))
    d = np.polyder(c)
    for _ in range(20):
        step = np.polyval(c, g) / np.polyval(d, g)
        g -= step
        if abs(step) < 1e-16 * max(1.0, g):
            break
    return float(g)


def lagrange_points(mu: float) -> dict[str, np.ndarray]:
    """L1–L5 in the rotating frame (normalised units; the larger primary at (−μ, 0), the
    smaller at (1 − μ, 0))."""
    _check_mu(mu)
    g1, g2, g3 = (collinear_gamma(mu, k) for k in ("L1", "L2", "L3"))
    h = math.sqrt(3) / 2
    return {
        "L1": np.array([1 - mu - g1, 0.0]),
        "L2": np.array([1 - mu + g2, 0.0]),
        "L3": np.array([-mu - g3, 0.0]),
        "L4": np.array([0.5 - mu, h]),
        "L5": np.array([0.5 - mu, -h]),
    }


def potential(mu: float, x: Any, y: Any) -> Any:
    """The effective potential Ω(x, y) = (x² + y²)/2 + (1 − μ)/r₁ + μ/r₂ (normalised)."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    r1 = np.hypot(x + mu, y)
    r2 = np.hypot(x - 1 + mu, y)
    return (x * x + y * y) / 2 + (1 - mu) / r1 + mu / r2


def jacobi(mu: float, x: Any, y: Any, vx: Any, vy: Any) -> Any:
    """The Jacobi constant C = 2Ω − v² of a body at (x, y) moving at (vx, vy) in the rotating
    frame (normalised)."""
    return 2 * potential(mu, x, y) - (np.asarray(vx, dtype=float) ** 2 + np.asarray(vy, dtype=float) ** 2)


def jacobi_inertial(mu: float, rho: Any, v: Any, r1: Any, r2: Any) -> Any:
    """The Jacobi constant from inertial quantities (normalised: lengths in separations, speeds
    in Ω × separation): ``rho`` the position from the barycentre, ``v`` the inertial velocity
    relative to it, ``r1`` / ``r2`` the distances to the primaries. C = ρ² + 2(1 − μ)/r₁ + 2μ/r₂ −
    |v − Ω × ρ|² (the velocity seen in the rotating frame)."""
    rho, v = np.atleast_2d(np.asarray(rho, dtype=float)), np.atleast_2d(np.asarray(v, dtype=float))
    v_rot = v[:, :2] - np.column_stack([-rho[:, 1], rho[:, 0]])
    out = (rho[:, :2] ** 2).sum(axis=1) + 2 * (1 - mu) / np.asarray(r1) + 2 * mu / np.asarray(r2) - (v_rot**2).sum(axis=1)
    return out if np.ndim(r1) else float(out[0])


def lagrange_jacobi(mu: float) -> dict[str, float]:
    """The Jacobi constant of a body at rest at each point (C₁ > C₂ > C₃ > C₄ = C₅ = 3 − μ(1 − μ))."""
    return {k: float(jacobi(mu, p[0], p[1], 0.0, 0.0)) for k, p in lagrange_points(mu).items()}


def zero_velocity_segments(mu: float, c: float, x_range: tuple[float, float], y_range: tuple[float, float], cells: int = 240) -> np.ndarray:
    """The zero-velocity curves 2Ω(x, y) = C in a box (normalised units), by marching squares
    on a grid of ``cells`` × ``cells`` (finer along the longer side): line segments ``(k, 2, 2)``.
    The body with Jacobi constant C can only be where 2Ω ≥ C."""
    (x0, x1), (y0, y1) = x_range, y_range
    nx = cells if x1 - x0 >= y1 - y0 else max(8, round(cells * (x1 - x0) / (y1 - y0)))
    ny = cells if y1 - y0 > x1 - x0 else max(8, round(cells * (y1 - y0) / (x1 - x0)))
    xs, ys = np.linspace(x0, x1, nx + 1), np.linspace(y0, y1, ny + 1)
    gx, gy = np.meshgrid(xs, ys)
    with np.errstate(divide="ignore", invalid="ignore"):
        f = 2 * potential(mu, gx, gy) - c
    f = np.where(np.isfinite(f), f, 1e9)
    # the corners of every cell, counterclockwise from the bottom left: values and positions
    vals = np.stack([f[:-1, :-1], f[:-1, 1:], f[1:, 1:], f[1:, :-1]], axis=-1)
    cx = np.stack([gx[:-1, :-1], gx[:-1, 1:], gx[1:, 1:], gx[1:, :-1]], axis=-1)
    cy = np.stack([gy[:-1, :-1], gy[:-1, 1:], gy[1:, 1:], gy[1:, :-1]], axis=-1)
    nxt = [1, 2, 3, 0]
    va, vb = vals, vals[..., nxt]
    crosses = (va > 0) != (vb > 0)   # edge k joins corner k and k + 1
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(crosses, va / (va - vb), 0.0)
    px = cx + s * (cx[..., nxt] - cx)
    py = cy + s * (cy[..., nxt] - cy)
    count = crosses.sum(axis=-1)
    segs = []
    two = count == 2
    if np.any(two):
        idx = np.argsort(~crosses[two], axis=-1, kind="stable")[:, :2]   # the two crossed edges, in order
        ex, ey = px[two], py[two]
        rows = np.arange(len(idx))
        segs.append(np.stack([np.column_stack([ex[rows, idx[:, 0]], ey[rows, idx[:, 0]]]), np.column_stack([ex[rows, idx[:, 1]], ey[rows, idx[:, 1]]])], axis=1))
    four = count == 4
    if np.any(four):   # saddle cells: pair the crossings by the sign at the centre
        ex, ey, v = px[four], py[four], vals[four]
        same = (v.mean(axis=-1) > 0) == (v[:, 0] > 0)
        pairs = np.where(same[:, None, None], np.array([[0, 1], [2, 3]]), np.array([[0, 3], [1, 2]]))
        for j in range(2):
            a, b = pairs[:, j, 0], pairs[:, j, 1]
            rows = np.arange(len(v))
            segs.append(np.stack([np.column_stack([ex[rows, a], ey[rows, a]]), np.column_stack([ex[rows, b], ey[rows, b]])], axis=1))
    return np.concatenate(segs) if segs else np.zeros((0, 2, 2))


def equations(mu: float) -> Any:
    """The right-hand side of the rotating-frame equations for the state (x, y, ẋ, ẏ)."""
    def rhs(_: float, s: np.ndarray) -> np.ndarray:
        x, y, vx, vy = s
        r1 = math.hypot(x + mu, y) ** 3
        r2 = math.hypot(x - 1 + mu, y) ** 3
        ax = x - (1 - mu) * (x + mu) / r1 - mu * (x - 1 + mu) / r2 + 2 * vy
        ay = y - (1 - mu) * y / r1 - mu * y / r2 - 2 * vx
        return np.array([vx, vy, ax, ay])
    return rhs


def integrate(mu: float, state: Any, t_end: float, samples: int = 2000) -> tuple[np.ndarray, np.ndarray]:
    """The motion from ``state`` (x, y, ẋ, ẏ in the rotating frame, normalised) for ``t_end``
    (normalised time: 2π a turn of the primaries): output times and states, by RK45."""
    _check_mu(mu)
    times = np.linspace(0.0, t_end, samples + 1)
    try:
        return rk45(equations(mu), 0.0, np.asarray(state, dtype=float), t_end, times=times, rtol=RTOL, atol=RTOL)
    except IntegrationError as error:
        raise VidgenError(f"three-body: {error} (a close pass by a primary?)") from None


def coorbital_angles(rel: np.ndarray, secondary: np.ndarray) -> np.ndarray:
    """The angle (degrees, in (−180, 180]) of a body ahead of the smaller primary as seen from
    the larger: positive ahead (L4 at +60°), negative behind (L5 at −60°). ``rel`` and
    ``secondary`` are positions relative to the larger primary (rows)."""
    a = np.arctan2(rel[..., 1], rel[..., 0]) - np.arctan2(secondary[..., 1], secondary[..., 0])
    out = np.degrees((a + math.pi) % (2 * math.pi) - math.pi)
    return np.where(out == -180.0, 180.0, out)


def coorbital_kind(angles: Any) -> str:
    """How a co-orbital body moves, from its angles ahead of the smaller primary (degrees, see
    :func:`coorbital_angles`): ``tadpole L4`` / ``tadpole L5`` (it stays on one side, around that
    point), ``horseshoe`` (it goes round past L3 and turns back before reaching the smaller
    primary, from either side) or ``passing`` (it passes the smaller primary: no longer
    co-orbital)."""
    a = np.asarray(angles, dtype=float)
    if np.all(a > 0):
        return "tadpole L4"
    if np.all(a < 0):
        return "tadpole L5"
    # it changes side: through L3 (a jump of nearly 360° in the wrapped angle) or past the secondary
    jumps = np.abs(np.diff(a))
    near = np.abs(a[:-1]) < 90
    through_secondary = np.any((jumps < 180) & near & (np.sign(a[:-1]) != np.sign(a[1:])))
    return "passing" if through_secondary else "horseshoe"


@dataclass(frozen=True)
class Restricted:
    """A circular restricted problem in SI: the ``primary`` and ``secondary`` bodies (GM), their
    ``separation`` (m), the mass ratio ``mu``, the angular speed ``omega`` (rad/s) and
    ``period`` (s), and the ``source`` of the values."""

    key: str
    primary: Body
    secondary: Body
    separation: float
    source: str = ""

    @property
    def mu(self) -> float:
        return self.secondary.gm / (self.primary.gm + self.secondary.gm)

    @property
    def omega(self) -> float:
        return math.sqrt((self.primary.gm + self.secondary.gm) / self.separation**3)

    @property
    def period(self) -> float:
        return 2 * math.pi / self.omega

    def points(self) -> dict[str, np.ndarray]:
        """L1–L5 in metres in the rotating frame (origin at the barycentre, the secondary on +x)."""
        return {k: p * self.separation for k, p in lagrange_points(self.mu).items()}

    def distances(self) -> dict[str, float]:
        """Each collinear point's distance (m) from the nearer primary (L3: from the larger)."""
        return {k: collinear_gamma(self.mu, k) * self.separation for k in ("L1", "L2", "L3")}

    def with_mu(self, mu: float) -> "Restricted":
        """The same pair with the secondary's GM set for mass ratio ``mu`` (the primary kept)."""
        _check_mu(mu)
        gm = mu / (1 - mu) * self.primary.gm
        return Restricted(self.key, self.primary, Body(self.secondary.name, gm, self.secondary.radius, self.secondary.color, "mass set by μ"),
                          self.separation, self.source)


_EMB = Body("Earth", GM_EARTH + BODIES["moon"].gm, BODIES["earth"].radius, BODIES["earth"].color, "Earth + Moon (the Earth–Moon barycentre)")
#: The preset pairs: the Earth–Moon (mean distance), the Sun with the Earth–Moon barycentre
#: (1 AU, the usual pair for the Sun–Earth L1 / L2) and the Sun–Jupiter (Table 1's a).
RESTRICTED: dict[str, Restricted] = {
    "earth_moon": Restricted("earth_moon", BODIES["earth"], BODIES["moon"], ORBITS["moon"].a, "GM: IAU 2015 B3, DE440; mean distance 384 400 km"),
    "sun_earth": Restricted("sun_earth", BODIES["sun"], _EMB, AU, "GM: IAU 2015 B3, DE440 (Earth + Moon); separation 1 AU"),
    "sun_jupiter": Restricted("sun_jupiter", BODIES["sun"], BODIES["jupiter"], ORBITS["jupiter"].a, "GM: IAU 2015 B3, DE440; a from JPL Table 1"),
}
#: Other spellings of the pairs.
RESTRICTED_ALIASES = {"earth-moon": "earth_moon", "sun-earth": "sun_earth", "sun-jupiter": "sun_jupiter", "sun_earth_moon": "sun_earth"}


def restricted_preset(name: str) -> Restricted:
    """A preset pair (``earth_moon``, ``sun_earth``, ``sun_jupiter``)."""
    key = RESTRICTED_ALIASES.get(name.strip().lower(), name.strip().lower())
    if key not in RESTRICTED:
        raise VidgenError(f"unknown three-body system '{name}'" + did_you_mean(key, list(RESTRICTED)) + f"; presets: {', '.join(RESTRICTED)}")
    return RESTRICTED[key]


__all__ = ["LAGRANGE_NAMES", "RESTRICTED", "RESTRICTED_ALIASES", "ROUTH_MU", "RTOL", "Restricted", "collinear_gamma", "coorbital_angles", "coorbital_kind",
           "equations", "integrate", "jacobi", "jacobi_inertial", "lagrange_jacobi", "lagrange_points", "potential", "restricted_preset", "routh_stable", "zero_velocity_segments"]
