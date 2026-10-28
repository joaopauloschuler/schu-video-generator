"""Two-body (Kepler) orbits: classical orbital elements, their conversion to and from state
vectors (position and velocity), the orbit's derived quantities and its motion in time (Phase X,
DESIGN §98). SI units throughout (m, s, rad, μ = GM in m³ s⁻²).

An orbit is stored by its semi-latus rectum ``p`` rather than its semi-major axis ``a`` so that
one representation serves all three conics (a parabola has no finite ``a``). Angles: ``i``
inclination, ``raan`` the longitude of the ascending node Ω, ``argp`` the argument of periapsis
ω, ``nu`` the true anomaly ν at the epoch (t = 0). Degenerate cases follow the usual
conventions: an equatorial orbit has Ω = 0 (ω is then the longitude of periapsis), a circular
one ω = 0 (ν is then the argument of latitude, or the true longitude when it is also
equatorial)."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from vidgen.errors import VidgenError

from .kepler import kind_of, mean_from_true, mean_motion, true_from_mean

#: Below this eccentricity an orbit is circular (ω = 0), below this sin i equatorial (Ω = 0).
CIRCULAR_TOLERANCE = 1e-10
EQUATORIAL_TOLERANCE = 1e-10


def _rotation(i: float, raan: float, argp: float) -> np.ndarray:
    """The perifocal → reference-frame rotation R₃(−Ω) R₁(−i) R₃(−ω)."""
    co, so = math.cos(raan), math.sin(raan)
    cw, sw = math.cos(argp), math.sin(argp)
    ci, si = math.cos(i), math.sin(i)
    return np.array([
        [co * cw - so * sw * ci, -co * sw - so * cw * ci, so * si],
        [so * cw + co * sw * ci, -so * sw + co * cw * ci, -co * si],
        [sw * si, cw * si, ci],
    ])


@dataclass(frozen=True)
class Elements:
    """A Kepler orbit around a body of gravitational parameter ``mu`` (m³/s²): semi-latus
    rectum ``p`` (m), eccentricity ``e``, inclination ``i``, ascending node ``raan``, argument
    of periapsis ``argp`` and true anomaly ``nu`` at the epoch (rad)."""

    mu: float
    p: float
    e: float
    i: float = 0.0
    raan: float = 0.0
    argp: float = 0.0
    nu: float = 0.0

    def __post_init__(self) -> None:
        if not (self.mu > 0 and math.isfinite(self.mu)):
            raise VidgenError(f"an orbit needs a positive gravitational parameter μ = GM (got {self.mu:g} m³/s²)")
        if not (self.p > 0 and math.isfinite(self.p)):
            raise VidgenError(f"an orbit needs a positive size (semi-latus rectum p = {self.p:g} m)")
        if not (0 <= self.i <= math.pi + 1e-12):
            raise VidgenError(f"an inclination lies between 0° and 180° (got {math.degrees(self.i):.6g}°)")
        kind = kind_of(self.e)
        if kind == "parabola" and self.e != 1.0:
            object.__setattr__(self, "e", 1.0)
        if kind != "ellipse":
            limit = self.nu_limit
            if abs(self.nu) >= limit:
                raise VidgenError(f"a true anomaly of {math.degrees(self.nu):.4g}° lies beyond the asymptotes of this {kind} "
                                  f"(|ν| < {math.degrees(limit):.4g}° for e = {self.e:g})")

    # ----- construction ---------------------------------------------------------------------------

    @classmethod
    def from_a(cls, mu: float, a: float, e: float, **angles: float) -> "Elements":
        """From the semi-major axis ``a`` (an ellipse; for a hyperbola ``|a|``, either sign)."""
        kind = kind_of(e)
        if kind == "parabola":
            raise VidgenError("a parabola (e = 1) has no finite semi-major axis; give its periapsis distance")
        if kind == "ellipse" and a <= 0:
            raise VidgenError(f"an ellipse needs a positive semi-major axis (got {a:g} m)")
        if a == 0:
            raise VidgenError("a hyperbola needs a non-zero semi-major axis")
        return cls(mu, abs(a) * abs(1.0 - e * e), e, **angles)

    @classmethod
    def from_periapsis(cls, mu: float, q: float, e: float, **angles: float) -> "Elements":
        """From the periapsis distance ``q`` and the eccentricity (any conic)."""
        if q <= 0:
            raise VidgenError(f"a periapsis distance must be positive (got {q:g} m)")
        return cls(mu, q * (1.0 + e), e, **angles)

    @classmethod
    def from_apsides(cls, mu: float, q: float, apo: float, **angles: float) -> "Elements":
        """From the periapsis and apoapsis distances (an ellipse)."""
        if q <= 0 or apo <= 0:
            raise VidgenError("periapsis and apoapsis distances must be positive")
        if apo < q:
            raise VidgenError(f"the apoapsis ({apo:g} m) is closer than the periapsis ({q:g} m); swap them")
        e = (apo - q) / (apo + q)
        return cls(mu, 2 * q * apo / (q + apo), e, **angles)

    @classmethod
    def from_state(cls, mu: float, r: Any, v: Any) -> "Elements":
        """From a position ``r`` (m) and velocity ``v`` (m/s) relative to the central body
        (2 or 3 components each)."""
        r = _vec(r, "position")
        v = _vec(v, "velocity")
        rn = float(np.linalg.norm(r))
        if rn == 0:
            raise VidgenError("a body cannot sit at the centre of its central body (r = 0)")
        h = np.cross(r, v)
        hn = float(np.linalg.norm(h))
        if hn <= 1e-12 * rn * max(float(np.linalg.norm(v)), 1e-300):
            raise VidgenError("the velocity points straight towards or away from the central body: a radial (degenerate) "
                              "trajectory has no conic orbit; give the velocity a sideways part")
        e_vec = ((float(v @ v) - mu / rn) * r - float(r @ v) * v) / mu
        e = float(np.linalg.norm(e_vec))
        p = hn * hn / mu
        h_hat = h / hn
        i = math.acos(max(-1.0, min(1.0, h_hat[2])))
        node = np.array([-h[1], h[0], 0.0])
        nn = float(np.linalg.norm(node))
        if nn > EQUATORIAL_TOLERANCE * hn:
            ref = node / nn
            raan = math.atan2(ref[1], ref[0]) % (2 * math.pi)
        else:
            ref, raan = np.array([1.0, 0.0, 0.0]), 0.0

        def angle(a: np.ndarray, b: np.ndarray) -> float:   # from a to b about h
            return math.atan2(float(np.cross(a, b) @ h_hat), float(a @ b))

        if e > CIRCULAR_TOLERANCE:
            argp = angle(ref, e_vec / e) % (2 * math.pi)
            nu = angle(e_vec / e, r / rn)
        else:
            e, argp, nu = 0.0, 0.0, angle(ref, r / rn)
        if kind_of(e) == "parabola":
            e = 1.0
        return cls(mu, p, e, i, raan, argp, nu)

    # ----- shape and size ---------------------------------------------------------------------------

    @property
    def kind(self) -> str:
        """``ellipse``, ``parabola`` or ``hyperbola``."""
        return kind_of(self.e)

    @property
    def closed(self) -> bool:
        return self.e < 1.0

    @property
    def a(self) -> float:
        """Semi-major axis (m): positive for an ellipse, negative for a hyperbola, ∞ for a parabola."""
        if self.kind == "parabola":
            return math.inf
        return self.p / (1.0 - self.e * self.e)

    @property
    def b(self) -> float:
        """Semi-minor axis (m) of an ellipse (|b| = |a| √(e² − 1) for a hyperbola)."""
        if self.kind == "parabola":
            return math.inf
        return abs(self.a) * math.sqrt(abs(1.0 - self.e * self.e))

    @property
    def periapsis(self) -> float:
        """Periapsis distance q (m)."""
        return self.p / (1.0 + self.e)

    @property
    def apoapsis(self) -> float:
        """Apoapsis distance (m); ∞ for an open orbit."""
        return self.p / (1.0 - self.e) if self.closed else math.inf

    @property
    def period(self) -> float | None:
        """Orbital period (s), Kepler's third law T = 2π √(a³/μ); ``None`` for an open orbit."""
        return 2 * math.pi * math.sqrt(self.a**3 / self.mu) if self.closed else None

    @property
    def mean_motion(self) -> float:
        """Mean motion n (rad/s), the rate of the mean anomaly (see :mod:`.kepler`)."""
        return mean_motion(self.mu, self.p, self.e)

    @property
    def energy(self) -> float:
        """Specific orbital energy ε = v²/2 − μ/r = −μ/(2a) (J/kg); 0 for a parabola."""
        return 0.0 if self.kind == "parabola" else -self.mu / (2 * self.a)

    @property
    def angular_momentum(self) -> float:
        """Specific angular momentum h = √(μ p) (m²/s)."""
        return math.sqrt(self.mu * self.p)

    @property
    def nu_limit(self) -> float:
        """The asymptote's true anomaly of an open orbit (acos(−1/e); π for a parabola), π for
        an ellipse."""
        return math.acos(-1.0 / self.e) if self.e > 1 else math.pi

    @property
    def v_infinity(self) -> float:
        """Hyperbolic excess speed √(−μ/a) (m/s); 0 for a parabola, ``nan`` for an ellipse."""
        if self.kind == "ellipse":
            return math.nan
        return 0.0 if self.kind == "parabola" else math.sqrt(-self.mu / self.a)

    @property
    def mean_anomaly(self) -> float:
        """The mean anomaly at the epoch (rad)."""
        return float(mean_from_true(self.nu, self.e))

    def radius_at(self, nu: Any) -> Any:
        """Distance from the focus at true anomaly ``nu``: p / (1 + e cos ν)."""
        return self.p / (1.0 + self.e * np.cos(nu))

    def speed_at(self, nu: Any) -> Any:
        """Speed at true anomaly ``nu`` (vis-viva)."""
        return vis_viva(self.mu, self.radius_at(nu), self.a)

    # ----- motion ---------------------------------------------------------------------------------

    @property
    def rotation(self) -> np.ndarray:
        return _rotation(self.i, self.raan, self.argp)

    def time_since_periapsis(self) -> float:
        """Seconds since the last periapsis passage at the epoch (negative before it on an
        open orbit)."""
        m = self.mean_anomaly
        if self.closed:
            m %= 2 * math.pi
        return m / self.mean_motion

    def true_anomaly_at(self, t: Any) -> Any:
        """ν at time ``t`` (s after the epoch; float or array): Kepler's equation."""
        m = self.mean_anomaly + self.mean_motion * np.asarray(t, dtype=float)
        nu = np.asarray(true_from_mean(m, self.e))
        return float(nu) if np.ndim(t) == 0 else nu

    def at(self, t: float) -> "Elements":
        """The same orbit with the body where it is ``t`` seconds after the epoch."""
        nu = float(self.true_anomaly_at(t))
        if self.closed:
            nu = (nu + math.pi) % (2 * math.pi) - math.pi
        return replace(self, nu=nu)

    def state(self) -> tuple[np.ndarray, np.ndarray]:
        """Position (m) and velocity (m/s) at the epoch, 3-vectors."""
        return self.state_at_anomaly(self.nu)

    def state_at_anomaly(self, nu: Any) -> tuple[np.ndarray, np.ndarray]:
        """Positions and velocities at true anomaly ``nu`` (``(3,)`` each, or ``(N, 3)`` for
        an array)."""
        v_nu = np.asarray(nu, dtype=float)
        c, s = np.cos(v_nu), np.sin(v_nu)
        r = self.p / (1.0 + self.e * c)
        k = math.sqrt(self.mu / self.p)
        pos_pf = np.stack([r * c, r * s, np.zeros_like(r)], axis=-1)
        vel_pf = np.stack([-k * s, k * (self.e + c), np.zeros_like(r)], axis=-1)
        rot = self.rotation
        return pos_pf @ rot.T, vel_pf @ rot.T

    def positions(self, t: Any) -> np.ndarray:
        """Positions (m) at times ``t`` (s after the epoch): ``(3,)`` or ``(N, 3)``."""
        return self.state_at_anomaly(self.true_anomaly_at(t))[0]

    def states(self, t: Any) -> tuple[np.ndarray, np.ndarray]:
        """Positions and velocities at times ``t``."""
        return self.state_at_anomaly(self.true_anomaly_at(t))

    def time_of_flight(self, nu_from: float, nu_to: float) -> float:
        """Seconds to move from true anomaly ``nu_from`` to ``nu_to`` (forwards; on an ellipse
        at most one period)."""
        m1, m2 = float(mean_from_true(nu_from, self.e)), float(mean_from_true(nu_to, self.e))
        dm = m2 - m1
        if self.closed:
            dm %= 2 * math.pi
        elif dm < 0:
            raise VidgenError("on an open orbit the body passes each point once: the end lies before the start")
        return dm / self.mean_motion

    def conic(self, samples: int = 360, r_max: float | None = None) -> np.ndarray:
        """``(N, 3)`` points along the orbit: an ellipse closed (its first point repeated at
        the end), sampled evenly in its eccentric anomaly (dense where it bends); an open orbit
        between the true anomalies where it reaches ``r_max`` (default 4 periapsis distances),
        sampled evenly in its hyperbolic / parabolic anomaly."""
        if self.closed:
            big_e = np.linspace(-math.pi, math.pi, samples + 1)
            nu = 2.0 * np.arctan2(math.sqrt(1 + self.e) * np.sin(big_e / 2), math.sqrt(1 - self.e) * np.cos(big_e / 2))
            return self.state_at_anomaly(nu)[0]
        reach = r_max if r_max is not None else 4 * self.periapsis
        cos_nu = (self.p / max(reach, self.periapsis * (1 + 1e-9)) - 1.0) / self.e
        nu_max = min(math.acos(max(-1.0, min(1.0, cos_nu))), self.nu_limit * (1 - 1e-6))
        m_max = float(mean_from_true(nu_max, self.e))
        nu = np.asarray(true_from_mean(np.linspace(-m_max, m_max, samples + 1), self.e))
        return self.state_at_anomaly(nu)[0]


def _vec(value: Any, what: str) -> np.ndarray:
    v = np.asarray(value, dtype=float).ravel()
    if v.size == 2:
        v = np.append(v, 0.0)
    if v.size != 3 or not np.all(np.isfinite(v)):
        raise VidgenError(f"a {what} has 2 or 3 finite components (got {value!r})")
    return v


def vis_viva(mu: float, r: Any, a: float) -> Any:
    """Speed (m/s) at distance ``r`` on an orbit of semi-major axis ``a``: √(μ (2/r − 1/a))
    (``a`` = ∞ for a parabola, negative for a hyperbola)."""
    inv_a = 0.0 if math.isinf(a) else 1.0 / a
    return np.sqrt(mu * (2.0 / np.asarray(r, dtype=float) - inv_a)) if np.ndim(r) else math.sqrt(mu * (2.0 / r - inv_a))


def period(mu: float, a: float) -> float:
    """Kepler's third law: T = 2π √(a³/μ) (s)."""
    if a <= 0:
        raise VidgenError(f"only an ellipse (a > 0) has a period (got a = {a:g} m)")
    return 2 * math.pi * math.sqrt(a**3 / mu)


def semi_major_axis(mu: float, period_s: float) -> float:
    """The semi-major axis (m) of an orbit of period ``period_s`` (s): a = (μ T² / 4π²)^(1/3)."""
    if period_s <= 0:
        raise VidgenError(f"a period must be positive (got {period_s:g} s)")
    return (mu * period_s**2 / (4 * math.pi**2)) ** (1 / 3)


def circular_speed(mu: float, r: float) -> float:
    """Speed of a circular orbit of radius ``r``: √(μ/r)."""
    return math.sqrt(mu / r)


def escape_speed(mu: float, r: float) -> float:
    """Escape speed at distance ``r``: √(2μ/r)."""
    return math.sqrt(2 * mu / r)


def specific_energy(mu: float, r: float, v: float) -> float:
    """ε = v²/2 − μ/r (J/kg): negative bound, zero parabolic, positive open."""
    return v * v / 2 - mu / r


__all__ = [
    "CIRCULAR_TOLERANCE",
    "EQUATORIAL_TOLERANCE",
    "Elements",
    "circular_speed",
    "escape_speed",
    "period",
    "semi_major_axis",
    "specific_energy",
    "vis_viva",
]
