"""Bodies (gravitational parameter GM and radius) and preset orbits (Phase X, DESIGN §98). No
manim.

Sources (SI; marked in each entry):

- **IAU 2015 Resolution B3** (nominal values, through :mod:`vidgen.quantities.constants`):
  (GM)☉, (GM)⊕, the Sun's radius 695 700 km, the Earth's equatorial radius 6 378.1 km.
- **JPL DE440** (Park et al. 2021, *AJ* 161:105) planetary GM values, km³ s⁻² (the planet with
  its moons for Mars to Neptune, as the ephemeris gives them): Mercury 22 031.868 551, Venus
  324 858.592, Moon 4 902.800 118, Mars 42 828.375 816, Jupiter 126 712 764.1, Saturn
  37 940 584.841 8, Uranus 5 794 556.4, Neptune 6 836 527.100 58.
- **IAU WGCCRE 2015** (Archinal et al. 2018) radii: equatorial for the planets (Mercury
  2 440.53, Venus 6 051.8, Mars 3 396.19, Jupiter 71 492, Saturn 60 268, Uranus 25 559,
  Neptune 24 764 km), the Moon's mean radius 1 737.4 km.
- **JPL "Keplerian Elements for Approximate Positions of the Major Planets"** (E. M. Standish,
  Table 1, valid 1800–2050): the planets' J2000 mean elements a, e, I, L, ϖ, Ω (ecliptic and
  equinox J2000); ω = ϖ − Ω, M = L − ϖ. The Earth's entry is the Earth–Moon barycentre. Their
  rates (positions on a date) are Step 233.
- The Moon: mean distance 384 400 km, e = 0.0549, i = 5.145° to the ecliptic (Ω and ω
  precess with periods of 18.6 and 8.85 years: set to 0 here). The ISS-like orbit: circular at
  420 km altitude, i = 51.64°. The geostationary orbit: circular, equatorial, period one
  sidereal day (86 164.0905 s). Halley's comet: osculating elements of its 1986 apparition,
  rounded (a = 17.834 AU, e = 0.96714, i = 162.26°, Ω = 58.42°, ω = 111.33°), for illustration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from vidgen.errors import VidgenError
from vidgen.plotcore import did_you_mean
from vidgen.quantities import constant

from .values import AU

_KM3 = 1e9   # km³/s² in m³/s²
GM_SUN = float(constant("GM_sun").number())
GM_EARTH = float(constant("GM_earth").number())
R_EARTH = float(constant("R_earth").number())
#: One sidereal day (s): the Earth's rotation period relative to the stars.
SIDEREAL_DAY = 86_164.0905


@dataclass(frozen=True)
class Body:
    """A body: its ``name`` (as shown), gravitational parameter ``gm`` (m³/s²; 0 for a probe
    whose gravity does not matter), ``radius`` (m; 0 unknown or a point), a theme colour token
    and the ``source`` of its values."""

    name: str
    gm: float
    radius: float = 0.0
    color: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        if self.gm < 0 or not math.isfinite(self.gm):
            raise VidgenError(f"{self.name}: a gravitational parameter (GM) cannot be negative (got {self.gm:g} m³/s²)")
        if self.radius < 0 or not math.isfinite(self.radius):
            raise VidgenError(f"{self.name}: a radius cannot be negative (got {self.radius:g} m)")


@dataclass(frozen=True)
class OrbitPreset:
    """A preset orbiting body: the body, the preset of the body it goes around, and its orbit's
    elements there (SI; angles in radians; ``mean_anomaly`` at the epoch)."""

    key: str
    body: Body
    around: str
    a: float
    e: float
    i: float = 0.0
    raan: float = 0.0
    argp: float = 0.0
    mean_anomaly: float = 0.0
    source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


_DE440 = "JPL DE440 (GM); IAU WGCCRE 2015 (radius)"
#: Bodies that can be the central body, by preset key.
BODIES: dict[str, Body] = {
    "sun": Body("Sun", GM_SUN, 695_700e3, "highlight", "IAU 2015 B3 (nominal)"),
    "mercury": Body("Mercury", 22_031.868551 * _KM3, 2_440.53e3, "dim", _DE440),
    "venus": Body("Venus", 324_858.592 * _KM3, 6_051.8e3, "secondary", _DE440),
    "earth": Body("Earth", GM_EARTH, R_EARTH, "primary", "IAU 2015 B3 (nominal)"),
    "moon": Body("Moon", 4_902.800118 * _KM3, 1_737.4e3, "dim", _DE440 + ", mean radius"),
    "mars": Body("Mars", 42_828.375816 * _KM3, 3_396.19e3, "accent", _DE440),
    "jupiter": Body("Jupiter", 126_712_764.1 * _KM3, 71_492e3, "secondary", _DE440),
    "saturn": Body("Saturn", 37_940_584.8418 * _KM3, 60_268e3, "highlight", _DE440),
    "uranus": Body("Uranus", 5_794_556.4 * _KM3, 25_559e3, "primary", _DE440),
    "neptune": Body("Neptune", 6_836_527.10058 * _KM3, 24_764e3, "primary", _DE440),
}

_JPL = "JPL approximate planetary elements, Table 1 (J2000; valid 1800–2050)"


def _planet(key: str, a_au: float, e: float, inc: float, mean_long: float, peri_long: float, node: float) -> OrbitPreset:
    """A planet from Table 1's J2000 values (degrees): ω = ϖ − Ω, M = L − ϖ. A negative
    inclination (the Earth–Moon barycentre's −0.000 015 31°) is the same plane with the nodes
    swapped: |I| with Ω + 180°."""
    node = node if inc >= 0 else node + 180
    return OrbitPreset(key, BODIES[key], "sun", a_au * AU, e, math.radians(abs(inc)), math.radians(node % 360),
                       math.radians((peri_long - node) % 360), math.radians((mean_long - peri_long) % 360), _JPL)


#: Preset orbiting bodies, by key.
ORBITS: dict[str, OrbitPreset] = {
    p.key: p
    for p in [
        _planet("mercury", 0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
        _planet("venus", 0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255),
        _planet("earth", 1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
        _planet("mars", 1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
        _planet("jupiter", 5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
        _planet("saturn", 9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
        _planet("uranus", 19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503),
        _planet("neptune", 30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574),
        OrbitPreset("moon", BODIES["moon"], "earth", 384_400e3, 0.0549, math.radians(5.145), source="mean distance and eccentricity; i to the ecliptic"),
        OrbitPreset("iss", Body("ISS", 0.0, 0.0, "", "an ISS-like orbit"), "earth", R_EARTH + 420e3, 0.0, math.radians(51.64),
                    source="ISS-like: circular, 420 km altitude, i = 51.64°"),
        OrbitPreset("geo", Body("GEO satellite", 0.0, 0.0, "", "geostationary"), "earth", (GM_EARTH * SIDEREAL_DAY**2 / (4 * math.pi**2)) ** (1 / 3), 0.0,
                    source="geostationary: period one sidereal day"),
        OrbitPreset("halley", Body("Halley", 0.0, 0.0, "", "1P/Halley"), "sun", 17.834 * AU, 0.96714, math.radians(162.26), math.radians(58.42),
                    math.radians(111.33), source="1P/Halley, 1986 osculating elements (rounded; for illustration)"),
    ]
}
#: Other spellings of preset keys.
ALIASES = {"sol": "sun", "luna": "moon", "geostationary": "geo", "comet_halley": "halley", "1p": "halley", "iss_like": "iss"}


def _key(name: str) -> str:
    k = name.strip().lower().replace(" ", "_").replace("-", "_")
    return ALIASES.get(k, k)


def body_preset(name: str, where: str = "central") -> Body:
    """The body of preset ``name`` (a planet, the Sun, the Moon); raises with did-you-mean."""
    key = _key(name)
    if key in BODIES:
        return BODIES[key]
    if key in ORBITS:
        raise VidgenError(f"{where}: '{name}' is a spacecraft or a comet without a known mass; it cannot be a central body "
                          f"(central bodies: {', '.join(BODIES)})")
    raise VidgenError(f"{where}: unknown body '{name}'" + did_you_mean(key, list(BODIES) + list(ALIASES)) + f"; presets: {', '.join(BODIES)}")


def orbit_preset(name: str, where: str = "bodies") -> OrbitPreset:
    """The preset orbit ``name`` (a planet around the Sun, the Moon, ``iss``, ``geo``,
    ``halley``); raises with did-you-mean."""
    key = _key(name)
    if key in ORBITS:
        return ORBITS[key]
    if key == "sun":
        raise VidgenError(f"{where}: the Sun has no preset orbit; make it the central body (central: sun)")
    raise VidgenError(f"{where}: unknown preset '{name}'" + did_you_mean(key, list(ORBITS) + list(ALIASES)) + f"; presets: {', '.join(ORBITS)}")


def preset_key(body: Body) -> str | None:
    """The preset key of a preset body (``None`` for a body of the author's own)."""
    return next((k for k, b in BODIES.items() if b == body), None)


__all__ = ["ALIASES", "BODIES", "GM_EARTH", "GM_SUN", "ORBITS", "R_EARTH", "SIDEREAL_DAY", "Body", "OrbitPreset", "body_preset", "orbit_preset", "preset_key"]
