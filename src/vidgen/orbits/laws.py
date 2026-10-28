"""Kepler's laws and orbital speed as numbers for the ``orbit`` scene's overlays (Phase X, Step
230, DESIGN §98.4): the ellipse's geometry (foci, centre, a, b, apsides and their names), the
areas swept in equal times (Kepler II, the area integrated from the geometry, not from Kepler's
equation), Newton's cannonball (shots from one point at increasing speeds, classified by their
energy, with the time a falling shot reaches the ground) and the planets' periods against their
semi-major axes (Kepler III), registered as the plot model ``kepler_planets``. No manim."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.plotcore import register_model

from .bodies import GM_SUN, ORBITS
from .elements import Elements, circular_speed, escape_speed, specific_energy
from .values import AU, YEAR

#: Names of the closest and farthest points of an orbit around these bodies (by lower-case
#: name); any other body: periapsis / apoapsis.
APSIS_NAMES: dict[str, tuple[str, str]] = {
    "sun": ("perihelion", "aphelion"),
    "earth": ("perigee", "apogee"),
    "moon": ("perilune", "apolune"),
    "jupiter": ("perijove", "apojove"),
}
#: The kinds of a cannon shot, slowest first.
SHOT_KINDS = ("suborbital", "circular", "elliptical", "parabolic", "hyperbolic")
#: A shot whose specific energy is within this share of μ/r of zero is parabolic (escape).
PARABOLIC_ENERGY_TOLERANCE = 1e-9
#: Gauss–Legendre nodes for a swept area (per piece; the arc is cut into pieces of at most 1/8 turn).
_NODES, _WEIGHTS = np.polynomial.legendre.leggauss(48)


def apsis_names(body_name: str) -> tuple[str, str]:
    """The names of the closest and farthest points of an orbit around ``body_name``:
    perihelion / aphelion (the Sun), perigee / apogee (the Earth), perilune / apolune, perijove /
    apojove, else periapsis / apoapsis."""
    return APSIS_NAMES.get(body_name.strip().lower(), ("periapsis", "apoapsis"))


@dataclass(frozen=True)
class EllipseGeometry:
    """An elliptic orbit's geometry in the reference frame, relative to the occupied focus F
    (the body orbited): semi-axes ``a``, ``b``, focal distance ``c`` = ae, ``e``, periapsis and
    apoapsis distances ``q``, ``Q``; points (3-vectors, m): ``centre``, ``empty_focus``,
    ``periapsis_point``, ``apoapsis_point``, ``minor_point`` (an end of the minor axis); unit
    vectors ``p_hat`` (towards the periapsis) and ``q_hat`` (90° ahead in the orbit's plane)."""

    a: float
    b: float
    c: float
    e: float
    q: float
    big_q: float
    centre: np.ndarray
    empty_focus: np.ndarray
    periapsis_point: np.ndarray
    apoapsis_point: np.ndarray
    minor_point: np.ndarray
    p_hat: np.ndarray
    q_hat: np.ndarray


def ellipse_geometry(el: Elements) -> EllipseGeometry:
    """The geometry of an elliptic orbit (raises ``VidgenError`` for an open one)."""
    if not el.closed:
        raise VidgenError(f"a {el.kind} (e = {el.e:g}) has no centre, second focus or apoapsis: the ellipse's geometry is for e < 1")
    rot = el.rotation
    p_hat, q_hat = rot[:, 0].copy(), rot[:, 1].copy()
    a, b, e = el.a, el.b, el.e
    c = a * e
    centre = -c * p_hat
    return EllipseGeometry(a, b, c, e, el.periapsis, el.apoapsis, centre, -2 * c * p_hat, el.periapsis * p_hat, -el.apoapsis * p_hat,
                           centre + b * q_hat, p_hat, q_hat)


def area_between(el: Elements, nu_from: float, nu_to: float) -> float:
    """The area (m²) swept by the line from the focus to the body as it moves forwards from
    true anomaly ``nu_from`` to ``nu_to``: ½ ∫ r(ν)² dν with r = p / (1 + e cos ν), integrated
    numerically (Gauss–Legendre) from the orbit's shape alone."""
    span = (nu_to - nu_from) % (2 * math.pi) if el.closed else nu_to - nu_from
    if el.closed and span == 0 and nu_to != nu_from:
        span = 2 * math.pi
    if span < 0:
        raise VidgenError("on an open orbit the body passes each point once: the end lies before the start")
    pieces = max(1, math.ceil(span / (math.pi / 4)))
    edges = np.linspace(nu_from, nu_from + span, pieces + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        nu = (hi - lo) / 2 * _NODES + (hi + lo) / 2
        r = el.p / (1.0 + el.e * np.cos(nu))
        total += (hi - lo) / 2 * float(_WEIGHTS @ (r * r))
    return total / 2


def sector_times(el: Elements, count: int, start: float = 0.0) -> np.ndarray:
    """The ``count + 1`` times (s) that cut one period from ``start`` into equal intervals."""
    if not el.closed:
        raise VidgenError("equal-time sectors need a closed orbit (one with a period)")
    if count < 1:
        raise VidgenError("give at least one sector")
    return start + np.linspace(0.0, el.period, count + 1)


def sector_areas(el: Elements, count: int, start: float = 0.0) -> np.ndarray:
    """The areas (m²) swept in each of ``count`` equal times from ``start``: the true anomalies
    at the times come from Kepler's equation, each area from the geometry
    (:func:`area_between`); Kepler's second law makes them equal (each πab / count)."""
    times = sector_times(el, count, start)
    nus = np.asarray(el.true_anomaly_at(times), dtype=float)
    if count == 1:   # a whole turn: back at the same anomaly
        return np.array([area_between(el, float(nus[0]), float(nus[0]) + 2 * math.pi)])
    return np.array([area_between(el, float(n1), float(n2)) for n1, n2 in zip(nus[:-1], nus[1:])])


@dataclass(frozen=True)
class Shot:
    """One shot of Newton's cannon: launched at ``speed`` (m/s; ``multiple`` of the circular
    speed there), its orbit ``elements`` around the planet from the launch point at t = 0, its
    ``kind`` (one of :data:`SHOT_KINDS`), specific ``energy`` (J/kg) and, for a shot that falls
    back, the seconds until it reaches the ground (``impact``; ``None`` otherwise)."""

    speed: float
    multiple: float
    elements: Elements
    kind: str
    energy: float
    impact: float | None

    def positions(self, t: Any) -> np.ndarray:
        """Positions (m, relative to the planet's centre) ``t`` seconds after launch (held at
        the start before it and at the impact point after it)."""
        tt = np.clip(np.asarray(t, dtype=float), 0.0, self.impact if self.impact is not None else np.inf)
        return self.elements.positions(tt)


def classify(mu: float, r: float, v: float, elements: Elements, radius: float) -> str:
    """What a body at distance ``r`` moving at ``v`` (horizontally) does, by its specific
    energy ε = v²/2 − μ/r: ε < 0 bound — ``circular`` (e = 0), ``suborbital`` when its
    periapsis lies inside the planet (``radius``), else ``elliptical``; ε = 0 ``parabolic``
    (exactly the escape speed √(2μ/r)); ε > 0 ``hyperbolic``."""
    eps = specific_energy(mu, r, v)
    if abs(eps) <= PARABOLIC_ENERGY_TOLERANCE * mu / r:
        return "parabolic"
    if eps > 0:
        return "hyperbolic"
    if elements.periapsis < radius:
        return "suborbital"
    return "circular" if elements.e == 0 else "elliptical"


def cannon_shots(mu: float, radius: float, r0: float, speeds: list[float], angle: float = math.pi / 2, clockwise: bool = True) -> list[Shot]:
    """Newton's cannonball: shots fired horizontally from distance ``r0`` (m) at polar angle
    ``angle`` (rad) at each of ``speeds`` (m/s), clockwise or not, around a planet of
    gravitational parameter ``mu`` and ``radius``."""
    if radius <= 0:
        raise VidgenError("cannonball: the central body needs a radius (the shots start above its surface)")
    if r0 <= radius:
        raise VidgenError("cannonball: the cannon must stand above the surface (a positive altitude)")
    pos = np.array([math.cos(angle), math.sin(angle), 0.0]) * r0
    ahead = np.array([math.sin(angle), -math.cos(angle), 0.0]) if clockwise else np.array([-math.sin(angle), math.cos(angle), 0.0])
    v_circ = circular_speed(mu, r0)
    shots = []
    for v in speeds:
        if not v > 0:
            raise VidgenError(f"cannonball: a launch speed must be positive (got {v:g} m/s)")
        el = Elements.from_state(mu, pos, ahead * v)
        kind = classify(mu, r0, v, el, radius)
        if kind == "parabolic" and el.e != 1.0:
            el = Elements(mu, el.p, 1.0, el.i, el.raan, el.argp, el.nu)
        impact = None
        if kind == "suborbital":
            cos_c = (el.p / radius - 1.0) / el.e
            nu_c = math.acos(max(-1.0, min(1.0, cos_c)))
            impact = el.time_of_flight(el.nu, -nu_c)
        shots.append(Shot(v, v / v_circ, el, kind, specific_energy(mu, r0, v), impact))
    return shots


def named_speed(name: str, mu: float, r0: float) -> float | None:
    """``circular`` or ``escape``: that speed at ``r0`` exactly; anything else ``None``."""
    key = name.strip().lower()
    if key == "circular":
        return circular_speed(mu, r0)
    if key == "escape":
        return escape_speed(mu, r0)
    return None


def kepler_planets() -> dict[str, np.ndarray]:
    """Kepler's third law for the eight planets (JPL Table 1, J2000): semi-major axis ``a``
    (AU), period ``T`` (Julian years; T = 2π √(a³ / G(M☉ + m))), ``T_law`` (2π √(a³ / GM☉),
    the law without the planet's mass), ``a3`` (AU³) and ``T2`` (yr²), by increasing a."""
    planets = sorted((p for p in ORBITS.values() if p.around == "sun" and p.body.gm > 0), key=lambda p: p.a)
    a = np.array([p.a for p in planets])
    period = np.array([2 * math.pi * math.sqrt(p.a**3 / (GM_SUN + p.body.gm)) for p in planets]) / YEAR
    law = 2 * math.pi * np.sqrt(a**3 / GM_SUN) / YEAR
    a_au = a / AU
    return {"a": a_au, "T": period, "T_law": law, "a3": a_au**3, "T2": period**2}


def kepler_planet_names() -> list[str]:
    """The planets' names in the order of :func:`kepler_planets` (for labels on the plot)."""
    planets = sorted((p for p in ORBITS.values() if p.around == "sun" and p.body.gm > 0), key=lambda p: p.a)
    return [p.body.name for p in planets]


@register_model("kepler_planets")
def _kepler_planets_model(params: dict[str, float], seed: int) -> dict[str, Any]:
    """The plot model ``kepler_planets`` (``kind: function``): the columns of :func:`kepler_planets`."""
    if params:
        raise VidgenError(f"kepler_planets takes no params (got {', '.join(params)})")
    return kepler_planets()


__all__ = [
    "APSIS_NAMES",
    "PARABOLIC_ENERGY_TOLERANCE",
    "SHOT_KINDS",
    "EllipseGeometry",
    "Shot",
    "apsis_names",
    "area_between",
    "cannon_shots",
    "classify",
    "ellipse_geometry",
    "kepler_planet_names",
    "kepler_planets",
    "named_speed",
    "sector_areas",
    "sector_times",
]
