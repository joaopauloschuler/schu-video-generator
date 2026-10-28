"""The ``orbit`` scene's bodies as written in YAML and their resolution into a
:class:`orbits.System` (Phase X, DESIGN §98): a body from a preset (the planets on their J2000
orbits, the Moon, an ISS-like orbit, a geostationary one, Halley's comet), from orbital elements
(``a`` and ``e``, ``periapsis`` and ``apoapsis``, ``periapsis`` and ``e``, ``altitude``) or from a
position and velocity, with values written with their units (``"1 AU"``, ``"7.8 km/s"``)."""

import math
from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np

from vidgen.api import *

#: A value with its unit as text ("1.5 AU", "7.8 km/s", "92 min"), or a number (an angle: degrees).
Value = str | float
#: Shape keys of an orbit (at most one way of giving its size and shape).
SHAPE_KEYS = ("a", "periapsis", "apoapsis", "altitude")
#: The parts of an ellipse's geometry overlay (``geometry: [foci, axes]``).
GEOMETRY_PARTS = ("foci", "axes", "apsides")
GeometryPart = Literal["foci", "axes", "apsides"]
#: Fewest and most equal-time sectors per orbit.
SECTOR_COUNTS = (2, 36)
#: Most shots of one cannon.
MAX_SHOTS = 8
#: The Lagrange points a body can start near.
LagrangeName = Literal["L1", "L2", "L3", "L4", "L5"]


class OrbitSectors(SceneParams):
    """Equal-time sectors (Kepler's second law): ``{count, show}``."""

    count: int = Field(default=8, ge=SECTOR_COUNTS[0], le=SECTOR_COUNTS[1])
    """How many equal times one orbit is cut into (each Δt = period / count)."""
    show: Literal["alternate", "all"] = "alternate"
    """alternate: every other sector shaded (gaps between them, the textbook picture); all: every one, in two alternating tints."""


class OrbitVelocity(SceneParams):
    """Velocity vectors and the speed: ``{live, along, readout}``."""

    live: bool = True
    """An arrow on the moving body, turning and stretching with its velocity."""
    along: int = Field(default=0, ge=0, le=24)
    """Also this many fixed arrows along the orbit at equal times (crowded where it is slow, long where it is fast)."""
    readout: bool = True
    """The speed now (vis-viva, v² = μ(2/r − 1/a)) and its range, fastest at periapsis, in the readout."""


class OrbitCannon(SceneParams):
    """Newton's cannonball: ``{altitude, speeds, at}``."""

    speeds: list[float | str] = Field(min_length=1, max_length=MAX_SHOTS)
    """Launch speeds, slowest first: numbers are multiples of the circular speed at the cannon (0.8, 1, 1.2), or speeds with units ('7.9 km/s'), or circular / escape (exactly)."""
    altitude: Value | None = None
    """Height of the cannon above the surface ('600 km'); default a tenth of the radius."""
    at: float = 90.0
    """Where the cannon stands, in degrees from +x (90: the top of the planet)."""
    clockwise: bool = True
    """Fire to the right of the top (clockwise); false: counterclockwise."""
    show_paths: bool = False
    """Draw each shot's whole path faintly from the start (the trajectories to come)."""


class OrbitBurn(SceneParams):
    """An impulsive burn: ``{at, prograde, retrograde, radial, anti_radial, normal, anti_normal, label}``."""

    at: Value = 0.0
    """When: a time from the start ('45 min'; 0 the start), or periapsis / apoapsis (the next one after the burn before)."""
    prograde: Value | None = None
    """Δv along the velocity ('2.4 km/s'): faster, the far side of the orbit rises."""
    retrograde: Value | None = None
    """Δv against the velocity: slower, the far side sinks."""
    radial: Value | None = None
    """Δv in the orbit's plane, perpendicular to the velocity, outwards: turns the orbit (the apsides move)."""
    anti_radial: Value | None = None
    """Δv in the plane, perpendicular to the velocity, inwards."""
    normal: Value | None = None
    """Δv out of the plane, along the angular momentum: tilts the orbit (a plane change; seen from above the picture shows only its projection)."""
    anti_normal: Value | None = None
    """Δv out of the plane the other way."""
    label: TranslatableStr = ""
    """Text next to its Δv arrow (default: Δv₁ 2.43 km/s prograde)."""

    def plan(self, where: str) -> Any:
        """The :class:`orbits.BurnPlan` (SI), checked."""
        comps = {k: orbits.value_si(getattr(self, k), "speed", f"{where}.{k}") for k in orbits.BURN_DIRECTIONS if getattr(self, k) is not None}
        if not comps:
            raise VidgenError(f"{where}: give its Δv in a direction: prograde, retrograde, radial, anti_radial, normal or anti_normal ('0.5 km/s')")
        for k, v in comps.items():
            if v < 0:
                raise VidgenError(f"{where}.{k}: a Δv is a positive speed; use the opposite direction ({_opposite(k)}) instead of a minus sign")
        at = self.at
        if isinstance(at, str) and at.strip().lower() in ("periapsis", "apoapsis"):
            when: float | str = at.strip().lower()
        elif at == 0 or at == "0":
            when = 0.0
        else:
            when = orbits.value_si(at, "time", f"{where}.at")
            if when < 0:
                raise VidgenError(f"{where}.at: '{at}' is before the start")
        return orbits.BurnPlan(when, comps, str(self.label))


def _opposite(direction: str) -> str:
    return direction[5:] if direction.startswith("anti_") else ("retrograde" if direction == "prograde" else "prograde" if direction == "retrograde" else f"anti_{direction}")


class OrbitTransfer(SceneParams):
    """A transfer between circular coplanar orbits flown by one body: ``{kind, ship, to, depart, apoapsis, revolutions}``."""

    kind: Literal["hohmann", "bielliptic", "phasing"] = "hohmann"
    """hohmann (two burns, half an ellipse), bielliptic (three burns, out to apoapsis and back in), phasing (catch up a body on the same orbit)."""
    ship: str
    """The body that flies it (listed in bodies, on a circular orbit; alongside: Earth starts it with a planet)."""
    to: Value
    """Where to: a body's name (its orbit circular and in the same plane: the phase angle and launch windows then count) or a radius ('42164 km')."""
    depart: Value = "window"
    """When the first burn fires: window (the first launch window from the start, when the target leads by the right angle), or a time ('30 d')."""
    apoapsis: Value | None = None
    """bielliptic: the far point between the two burns ('300000 km'), beyond both orbits."""
    revolutions: int = Field(default=1, ge=1, le=20)
    """phasing: turns on the phasing orbit before the second burn (more turns: a gentler orbit)."""


class OrbitFlyby(SceneParams):
    """A gravity assist past the central body, in its frame: ``{v_inf, periapsis or altitude, side, angle, planet_speed, atmosphere, name}``."""

    v_inf: Value
    """The probe's speed relative to the planet far away (hyperbolic excess speed, '5.6 km/s'): the same in and out."""
    periapsis: Value | None = None
    """Closest distance to the planet's centre ('400000 km'); or altitude."""
    altitude: Value | None = None
    """Closest height above the surface ('200000 km')."""
    side: Literal["behind", "in_front"] = "behind"
    """behind: the probe passes behind the planet (on the side it comes from) and gains speed around the Sun; in_front: it loses speed."""
    angle: Value = 150.0
    """Direction of v∞ coming in, in degrees from the planet's motion (180: straight against it; 150: mostly from ahead)."""
    planet_speed: Value | None = None
    """The planet's speed around the Sun ('13.06 km/s'); default: a preset planet's circular speed at its mean distance."""
    atmosphere: Value | None = None
    """Height of the top of the atmosphere ('100 km'): a periapsis in it is refused."""
    name: str = "Probe"
    """The probe's name (target body:<name>)."""
    reach: float | None = Field(default=None, gt=1.5, le=500.0)
    """How far out the pass starts and ends, in periapsis distances; default: far enough to show where the asymptotes cross (at least 6)."""
    vectors: bool = True
    """Draw the Sun-frame vector diagram: the planet's velocity plus v∞ before and after."""


class OrbitCentral(SceneParams):
    """The central body: ``{preset: earth}`` or one of your own, ``{name, gm or mass, radius}``."""

    preset: str | None = None
    """A preset body: sun, mercury, venus, earth, moon, mars, jupiter, saturn, uranus, neptune (GM and radius from IAU / JPL)."""
    name: str | None = None
    """Its name (default: the preset's); bodies' around and the scene's follow use it."""
    label: TranslatableStr = ""
    """Text shown next to it (default: its name)."""
    show_label: bool = True
    """Show its label."""
    gm: Value | None = None
    """Gravitational parameter GM with its unit ('3.986e14 m^3/s^2'); or give mass."""
    mass: Value | None = None
    """Mass with its unit ('5.97e24 kg'); GM = G × mass (CODATA 2022 G)."""
    radius: Value | None = None
    """Radius with its unit ('6371 km'): drawn to scale when it is large enough to see; a periapsis inside it is refused."""
    color: ThemeColor | None = None
    """Colour (default: the preset's, else highlight)."""

    def body(self) -> Any:
        """The :class:`orbits.Body` this describes (raises ``VidgenError``)."""
        base = orbits.body_preset(self.preset) if self.preset else None
        if base is None and not self.name:
            raise VidgenError("central: give a preset (sun, earth, mars...) or a name with gm or mass")
        gm = _gm(self.gm, self.mass, "central")
        if gm is None:
            if base is None:
                raise VidgenError(f"central '{self.name}': give gm ('3.986e14 m^3/s^2') or mass ('5.97e24 kg')")
            gm = base.gm
        if gm <= 0:
            raise VidgenError("central: the central body needs a positive mass")
        radius = orbits.value_si(self.radius, "length", "central.radius") if self.radius is not None else (base.radius if base else 0.0)
        if radius < 0:
            raise VidgenError("central.radius: a radius cannot be negative")
        return orbits.Body(self.name or (base.name if base else ""), gm, radius, base.color if base else "highlight", base.source if base else "")


class OrbitBody(SceneParams):
    """A body on its orbit: a preset (``{preset: mars}``), orbital elements (``{name, a, e, i,
    raan, argp, nu}``, or periapsis / apoapsis / altitude for the size) or a state (``{name, r,
    v}``), around the central body or another body (``around``)."""

    name: str | None = None
    """Its name (default: the preset's); targets body:<name> and orbit:<name>, around and follow use it."""
    preset: str | None = None
    """A preset orbit: mercury … neptune (JPL J2000 elements), moon, iss (420 km, 51.6°), geo (geostationary), halley; elements you give override the preset's."""
    around: str | None = None
    """The body it orbits (another body's name; default: the central body, or the preset's primary)."""
    a: Value | None = None
    """Semi-major axis with its unit ('1.52 AU'); for a hyperbola |a|."""
    e: float | None = None
    """Eccentricity: 0 a circle, below 1 an ellipse, 1 a parabola (escape), above 1 a hyperbola (default 0)."""
    periapsis: Value | None = None
    """Closest distance to the centre of what it orbits ('6778 km'); with apoapsis, or e."""
    apoapsis: Value | None = None
    """Farthest distance (an ellipse); with periapsis, or e."""
    altitude: Value | None = None
    """Height of the periapsis above the surface ('420 km'); a circle unless e is given."""
    i: Value | None = None
    """Inclination (degrees, or '0.9 rad'); the picture shows the orbit seen from above its reference plane."""
    raan: Value | None = None
    """Longitude of the ascending node Ω (degrees)."""
    argp: Value | None = None
    """Argument of periapsis ω (degrees): where the periapsis lies, measured from the node (from +x when i = 0)."""
    nu: Value | None = None
    """True anomaly at the start (degrees from periapsis; default 0: it starts at periapsis)."""
    mean_anomaly: Value | None = None
    """Mean anomaly at the start (degrees), instead of nu."""
    r: list[Value] | None = None
    """Start position relative to what it orbits, instead of elements: ['1 AU', 0] or [x, y, z] with units."""
    v: list[Value] | None = None
    """Start velocity with r: [0, '29.8 km/s']."""
    gm: Value | None = None
    """Its own gravitational parameter (matters for n-body and adds to its parent's in μ = G(M + m)); default 0 (a probe) or the preset's."""
    mass: Value | None = None
    """Its mass instead of gm ('7.35e22 kg')."""
    radius: Value | None = None
    """Its radius ('1737 km'); drawn to scale when large enough."""
    label: TranslatableStr = ""
    """Text shown next to it (default: its name)."""
    show_label: bool = True
    """Show its label."""
    color: ThemeColor | None = None
    """Colour (default: the palette by position)."""
    trail: bool | float | str = True
    """A fading trail behind it: true (a quarter of its orbit), a share of its orbit (0.5), a time ('30 d') or false."""
    orbit: bool = True
    """Draw its orbit (the conic of its Kepler orbit, dashed for an open one)."""
    geometry: bool | list[GeometryPart] = False
    """The ellipse's geometry (an orbit with e < 1): true for all of it, or some of foci (the empty focus F′ and the centre C), axes (a and b with their lengths), apsides (periapsis and apoapsis with their names and distances: perihelion / aphelion, perigee / apogee...)."""
    sectors: bool | int | OrbitSectors = False
    """Kepler's second law: shaded sectors swept in equal times (true: 8 per orbit; a number; or {count, show}), each one's area computed and listed."""
    velocity: bool | OrbitVelocity = False
    """Velocity vectors (length ∝ speed, one scale for the scene, with a key) and the speed from vis-viva: true, or {live, along, readout}."""
    alongside: str | None = None
    """Start where another body listed before is, moving with it ('Earth': a spacecraft leaving with the planet), instead of elements."""
    burns: list[OrbitBurn] = Field(default_factory=list)
    """Impulsive burns, in time order: [{at: '45 min', prograde: '0.5 km/s'}, {at: apoapsis, prograde: '0.4 km/s'}]; each Δv drawn as an arrow at its point, the orbits before and after."""
    near: LagrangeName | None = None
    """With a three-body system: start at this Lagrange point (L1…L5), at rest in the rotating frame (a Trojan near L4)."""
    shift: list[float | str] | None = None
    """With near: move the start by [x, y] in the rotating frame (x away from the primary along the line to the secondary): numbers are shares of the separation (0.004), or lengths ('0.02 AU')."""
    drift: list[float | str] | None = None
    """With near: a starting velocity [x, y] in the rotating frame: numbers are shares of the secondary's orbital speed, or speeds ('0.1 km/s')."""
    curvature: bool = False
    """Check which way its path bends around the central body (the Moon's path around the Sun is always concave towards it): the result in the panel."""

    @field_validator("geometry")
    @classmethod
    def _geometry(cls, v: Any) -> Any:
        if isinstance(v, list) and not v:
            raise ValueError("geometry: name at least one part (foci, axes, apsides) or write true")
        return v

    @field_validator("sectors")
    @classmethod
    def _sectors(cls, v: Any) -> Any:
        if isinstance(v, int) and not isinstance(v, bool) and not SECTOR_COUNTS[0] <= v <= SECTOR_COUNTS[1]:
            raise ValueError(f"sectors: give {SECTOR_COUNTS[0]} to {SECTOR_COUNTS[1]} equal times per orbit (got {v})")
        return v

    def geometry_parts(self) -> list[str]:
        """The geometry parts it shows (none, some or all of :data:`GEOMETRY_PARTS`)."""
        if self.geometry is True:
            return list(GEOMETRY_PARTS)
        return [p for p in GEOMETRY_PARTS if isinstance(self.geometry, list) and p in self.geometry]

    def sector_spec(self) -> "OrbitSectors | None":
        if self.sectors is False:
            return None
        if self.sectors is True:
            return OrbitSectors()
        if isinstance(self.sectors, int):
            return OrbitSectors(count=self.sectors)
        return self.sectors

    def velocity_spec(self) -> "OrbitVelocity | None":
        if self.velocity is False:
            return None
        return OrbitVelocity() if self.velocity is True else self.velocity

    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.preset:
            return orbits.orbit_preset(self.preset).body.name
        return ""


def _gm(gm: str | None, mass: str | None, where: str) -> float | None:
    if gm is not None and mass is not None:
        raise VidgenError(f"{where}: give gm or mass, not both")
    if gm is not None:
        value = orbits.value_si(gm, "gm", f"{where}.gm")
    elif mass is not None:
        value = orbits.value_si(mass, "mass", f"{where}.mass") * orbits.G
    else:
        return None
    if value < 0:
        raise VidgenError(f"{where}: a mass cannot be negative")
    return value


def _length(value: str | None, where: str) -> float | None:
    if value is None:
        return None
    out = orbits.value_si(value, "length", where)
    if out <= 0:
        raise VidgenError(f"{where}: a distance must be positive (got '{value}')")
    return out


def _angle(value: Any, where: str, default: float = 0.0) -> float:
    return default if value is None else orbits.value_si(value, "angle", where)


def build_system(central: Any, bodies: list[OrbitBody], jd: float | None = None) -> Any:
    """The :class:`orbits.System` of the central body (a preset name or :class:`OrbitCentral`)
    and the bodies, checked: names unique, ``around`` a body listed before, a preset's primary
    present, elements consistent, periapses outside the bodies they orbit. With a Julian date
    ``jd`` (Step 233) the Table 1 planets take their elements on that date."""
    from .orbit_sky import dated_preset   # the date's module builds on this one
    centre = (OrbitCentral(preset=central) if isinstance(central, str) else central).body()
    central_key = orbits.preset_key(centre)
    out: list[Any] = []
    seen: dict[str, Any] = {}
    presets: dict[str, str] = {}   # preset key -> the name of the body using it
    for k, spec in enumerate(bodies, start=1):
        where = f"bodies[{k}]"
        preset = orbits.orbit_preset(spec.preset, where) if spec.preset else None
        preset = dated_preset(preset, jd, spec, where)
        name = spec.display_name()
        if not name:
            raise VidgenError(f"{where}: give a name (or a preset)")
        where = f"bodies[{k}] '{name}'"
        if name in seen or name == centre.name:
            raise VidgenError(f"{where}: the name is used twice; give each body its own name")
        mate = _alongside(spec, where, seen, centre)
        parent = mate.parent if mate is not None else _parent(spec, preset, where, centre, central_key, seen, presets)
        parent_body = centre if parent is None else seen[parent].body
        gm = _gm(spec.gm, spec.mass, where)
        radius = _length(spec.radius, f"{where}.radius")
        body = orbits.Body(name, gm if gm is not None else (preset.body.gm if preset else 0.0),
                           radius if radius is not None else (preset.body.radius if preset else 0.0), preset.body.color if preset else "")
        if mate is not None:   # where the other body is, moving with it (a circle stays the same circle under its own μ)
            el = mate.elements
            mu = parent_body.gm + body.gm
            elements = orbits.Elements(mu, el.p, 0.0, el.i, el.raan, el.argp, el.nu) if el.e == 0 else orbits.Elements.from_state(mu, *el.state())
        else:
            elements = _elements(spec, preset, where, parent_body.gm + body.gm, parent_body)
        q = elements.periapsis
        if parent_body.radius > 0 and q <= parent_body.radius:
            raise VidgenError(f"{where}: its periapsis ({_distance(q)} from the centre of {parent_body.name}) lies inside {parent_body.name} "
                              f"(radius {_distance(parent_body.radius)}): it would crash; raise the periapsis or lower e")
        trajectory = None
        if spec.burns:
            plans = [b.plan(f"{where}.burns[{n}]") for n, b in enumerate(spec.burns, start=1)]
            trajectory = _fly(elements, plans, parent_body, where)
        orbiter = orbits.Orbiter(name, body, elements, parent, trajectory)
        out.append(orbiter)
        seen[name] = orbiter
        if preset is not None:
            presets.setdefault(preset.key, name)
    return orbits.System(centre, tuple(out))


def _distance(metres: float) -> str:
    if metres >= 0.05 * orbits.AU:
        return f"{metres / orbits.AU:.4g} AU"
    return f"{metres / 1000:,.0f} km"


def _alongside(spec: "OrbitBody", where: str, seen: dict[str, Any], centre: Any) -> Any:
    """The body ``spec`` starts alongside (``None``: it has its own orbit), checked."""
    if spec.alongside is None:
        return None
    if spec.alongside not in seen:
        known = list(seen)
        raise VidgenError(f"{where}: alongside '{spec.alongside}' is not a body listed before it" + (f" (known: {', '.join(known)})" if known else "")
                          + did_you_mean(spec.alongside, known))
    others = [k for k in (*SHAPE_KEYS, "e", "i", "raan", "argp", "nu", "mean_anomaly", "r", "v", "preset") if getattr(spec, k) is not None]
    if others:
        raise VidgenError(f"{where}: alongside '{spec.alongside}' gives its start; leave out {', '.join(others)}")
    mate = seen[spec.alongside]
    if spec.around is not None and spec.around != (mate.parent or centre.name):
        raise VidgenError(f"{where}: alongside '{spec.alongside}' it goes around {mate.parent or centre.name}, not '{spec.around}'")
    return mate


def _fly(elements: Any, plans: list[Any], parent: Any, where: str) -> Any:
    try:
        return orbits.fly(elements, plans, radius=parent.radius, body=parent.name)
    except VidgenError as error:
        raise VidgenError(f"{where}: {error}") from None


def _parent(spec: OrbitBody, preset: Any, where: str, centre: Any, central_key: str | None, seen: dict[str, Any], presets: dict[str, str]) -> str | None:
    """The name of the body ``spec`` orbits (``None``: the central body)."""
    if spec.around is not None:
        if spec.around == centre.name:
            return None
        if spec.around not in seen:
            known = [centre.name, *seen]
            raise VidgenError(f"{where}: around '{spec.around}' is not the central body or a body listed before it (known: {', '.join(known)})"
                              + did_you_mean(spec.around, known))
        return spec.around
    if preset is None:
        return None
    if preset.around == central_key:
        return None
    if preset.around in presets:
        return presets[preset.around]
    primary = orbits.BODIES[preset.around].name
    raise VidgenError(f"{where}: preset '{preset.key}' orbits {primary}, but the central body is {centre.name}; "
                      f"use central: {preset.around}, list {primary} first (preset: {preset.around}), or give around:")


def _elements(spec: OrbitBody, preset: Any, where: str, mu: float, parent: Any) -> Any:
    """The body's Kepler orbit around its parent (gravitational parameter ``mu``)."""
    shape = [k for k in SHAPE_KEYS if getattr(spec, k) is not None]
    if spec.r is not None or spec.v is not None:
        if spec.r is None or spec.v is None:
            raise VidgenError(f"{where}: give both r (position) and v (velocity)")
        others = shape + [k for k in ("e", "i", "raan", "argp", "nu", "mean_anomaly") if getattr(spec, k) is not None]
        if others:
            raise VidgenError(f"{where}: give elements ({', '.join(others)}) or a state (r, v), not both")
        for key, kind in (("r", "length"), ("v", "speed")):
            if len(getattr(spec, key)) not in (2, 3):
                raise VidgenError(f"{where}.{key}: give 2 or 3 components ([x, y] or [x, y, z])")
        r = [orbits.value_si(c, "length", f"{where}.r[{n}]") if c != 0 else 0.0 for n, c in enumerate(spec.r)]
        v = [orbits.value_si(c, "speed", f"{where}.v[{n}]") if c != 0 else 0.0 for n, c in enumerate(spec.v)]
        try:
            return orbits.Elements.from_state(mu, r, v)
        except VidgenError as error:
            raise VidgenError(f"{where}: {error}") from None
    if spec.e is not None and spec.e < 0:
        raise VidgenError(f"{where}: e = {spec.e:g}: an eccentricity cannot be negative (0 is a circle)")
    if spec.nu is not None and spec.mean_anomaly is not None:
        raise VidgenError(f"{where}: give nu or mean_anomaly, not both")
    angles = {
        "i": _angle(spec.i, f"{where}.i", preset.i if preset else 0.0),
        "raan": _angle(spec.raan, f"{where}.raan", preset.raan if preset else 0.0),
        "argp": _angle(spec.argp, f"{where}.argp", preset.argp if preset else 0.0),
    }
    if not 0 <= angles["i"] <= math.pi + 1e-12:
        raise VidgenError(f"{where}.i: an inclination lies between 0° and 180° (above 90° the body goes round backwards)")
    e = spec.e if spec.e is not None else (preset.e if preset and not shape else 0.0)
    if len(shape) > 1 and set(shape) != {"periapsis", "apoapsis"}:
        raise VidgenError(f"{where}: give the orbit's size one way: a, periapsis (with apoapsis or e), apoapsis with e, or altitude (got {', '.join(shape)})")
    if "apoapsis" in shape and "periapsis" in shape and spec.e is not None:
        raise VidgenError(f"{where}: periapsis and apoapsis fix e already; leave e out")
    kind = orbits.kind_of(e)
    try:
        if not shape:
            if preset is None:
                raise VidgenError(f"{where}: give its orbit: a and e, periapsis and apoapsis, periapsis and e, altitude, a preset, or r and v")
            el = orbits.Elements.from_a(mu, preset.a, e, **angles) if kind != "parabola" else orbits.Elements.from_periapsis(mu, preset.a * (1 - preset.e), e, **angles)
        elif shape == ["a"]:
            el = orbits.Elements.from_a(mu, _length(spec.a, f"{where}.a"), e, **angles)
        elif set(shape) == {"periapsis", "apoapsis"}:
            el = orbits.Elements.from_apsides(mu, _length(spec.periapsis, f"{where}.periapsis"), _length(spec.apoapsis, f"{where}.apoapsis"), **angles)
        elif shape == ["periapsis"]:
            el = orbits.Elements.from_periapsis(mu, _length(spec.periapsis, f"{where}.periapsis"), e, **angles)
        elif shape == ["apoapsis"]:
            if spec.e is None or kind != "ellipse":
                raise VidgenError(f"{where}: an apoapsis needs a periapsis or an eccentricity below 1")
            apo = _length(spec.apoapsis, f"{where}.apoapsis")
            el = orbits.Elements.from_periapsis(mu, apo * (1 - e) / (1 + e), e, **angles)
        else:   # altitude
            if parent.radius <= 0:
                raise VidgenError(f"{where}: altitude needs the radius of {parent.name} (give its radius, or use periapsis)")
            height = orbits.value_si(spec.altitude, "length", f"{where}.altitude")
            if height <= 0:
                raise VidgenError(f"{where}: altitude '{spec.altitude}' puts it on or under the surface of {parent.name}")
            el = orbits.Elements.from_periapsis(mu, parent.radius + height, e, **angles)
    except VidgenError as error:
        message = str(error)
        raise VidgenError(message if message.startswith(where) else f"{where}: {message}") from None
    if spec.nu is not None:
        nu = _angle(spec.nu, f"{where}.nu")
    elif spec.mean_anomaly is not None:
        nu = float(orbits.true_from_mean(_angle(spec.mean_anomaly, f"{where}.mean_anomaly"), el.e))
    elif preset is not None and not shape and spec.e is None:
        nu = float(orbits.true_from_mean(preset.mean_anomaly, el.e))
    else:
        nu = 0.0
    if el.closed:
        nu = (nu + math.pi) % (2 * math.pi) - math.pi
    try:
        return orbits.Elements(el.mu, el.p, el.e, el.i, el.raan, el.argp, nu)
    except VidgenError as error:
        raise VidgenError(f"{where}: {error}") from None


class OrbitModel:
    """A resolved ``orbit`` scene: the ``system``, the simulated ``span`` (s), the n-body
    ``run`` (``None``: Kepler orbits), the body the view ``follow``s (``None``: the central
    body stays at the centre), each body's trail length (s), and Newton's cannon: its ``shots``
    (:class:`orbits.Shot`, fired from ``cannon_at``, a 3-vector in m) and ``cannon_radius``."""

    def __init__(self, system: Any, span: float, run: Any, follow: str | None, trails: dict[str, float], shots: list[Any] | None = None,
                 cannon_at: Any = None, transfer: "TransferInfo | None" = None, assist: "AssistInfo | None" = None,
                 extra_bodies: list["OrbitBody"] | None = None, specs: list["OrbitBody"] | None = None, many: Any = None, sky: Any = None) -> None:
        self.system, self.span, self.run, self.follow, self.trails = system, span, run, follow, trails
        self.shots = list(shots or [])
        self.cannon_at = cannon_at
        self.transfer = transfer
        self.assist = assist
        self.extra_bodies = list(extra_bodies or [])
        self.specs = list(specs) if specs is not None else None
        #: Step 232: the many-body additions (:class:`~vidgen.scenes.orbit_systems.ManyInfo`;
        #: ``None`` without them) and how far the view turns with a restricted pair (0 the
        #: inertial view, 1 the rotating frame; the scene sets it as it draws).
        self.many = many
        self.turn = many.turn0 if many is not None else 0.0
        #: Step 233: the date, event, log view, inset or sizes picture
        #: (:class:`~vidgen.scenes.orbit_sky.SkyInfo`; ``None`` without them).
        self.sky = sky

    def burns(self) -> list[tuple[str, Any]]:
        """Every burn of the scene in order of the bodies, then time: (body name, :class:`orbits.Burn`)
        — ``burn:1``, ``burn:2``... in that order."""
        return [(o.name, b) for o in self.system.orbiters if o.trajectory is not None for b in o.trajectory.burns]

    def shot_view(self, k: int, t: Any, launch: float) -> Any:
        """Shot ``k``'s position(s) in the view's frame at time(s) ``t`` when fired at ``launch``
        (at the cannon before it)."""
        p = self.shots[k].positions(np.asarray(t, dtype=float) - launch)
        return p - self.position(self.follow, t) if self.follow is not None else p

    def position(self, name: str, t: Any) -> Any:
        """Position (m) relative to the central body at time(s) ``t``; the central body's own
        name gives 0."""
        if name == self.system.central.name:
            return np.zeros(3) if np.ndim(t) == 0 else np.zeros((len(t), 3))
        return self.run.position(name, t) if self.run is not None else self.system.position(name, t)

    def view(self, name: str, t: Any) -> Any:
        """Position (m) in the view's frame: relative to the followed body, else the central one
        (Step 232: or the barycentre, turned by :attr:`turn` of the restricted pair's angle)."""
        p = self.position(name, t)
        if self.follow is not None:
            return p - self.position(self.follow, t)
        if self.many is None or self.many.origin != "barycentre":
            return p
        return self.turned(p - self.barycentre(t), t)

    def velocity(self, name: str, t: Any) -> Any:
        """Velocity (m/s) relative to the central body at time(s) ``t``."""
        if name == self.system.central.name:
            return np.zeros(3) if np.ndim(t) == 0 else np.zeros((len(t), 3))
        if self.run is not None:
            return self.run.velocity(name, t)
        v = np.zeros(3) if np.ndim(t) == 0 else np.zeros((len(t), 3))
        for o in self.system.chain(name):
            v = v + o.states(t)[1]
        return v

    def massive(self) -> list[str]:
        """The names of the bodies with mass (the central body first)."""
        return [self.system.central.name] + [o.name for o in self.system.orbiters if o.body.gm > 0]

    def barycentre(self, t: Any) -> Any:
        """The barycentre of the bodies with mass (m, relative to the central body) at time(s) ``t``."""
        names = self.massive()
        gms = [self.system.central.gm] + [self.system.orbiter(n).body.gm for n in names[1:]]
        return orbits.barycentre(gms, np.array([self.position(n, t) for n in names]))

    def theta(self, t: Any) -> Any:
        """The restricted pair's angle (rad, unwrapped): the secondary's direction from the
        primary, continuous in time (Ω t plus its start, corrected to the run's own positions)."""
        info = self.many.restricted
        omega = info.pair.omega
        p = self.position(info.secondary, t)
        actual = np.arctan2(p[..., 1], p[..., 0])
        nominal = omega * np.asarray(t, dtype=float)
        return nominal + np.mod(actual - nominal + math.pi, 2 * math.pi) - math.pi

    def turned(self, p: Any, t: Any, turn: float | None = None) -> Any:
        """Points (m, from the barycentre) at time(s) ``t`` seen in the view turned by ``turn`` (default
        :attr:`turn`) of the restricted pair's angle: 0 inertial, 1 the frame turning with it."""
        turn = self.turn if turn is None else turn
        if not turn or self.many is None or self.many.restricted is None:
            return p
        a = -turn * self.theta(t)
        c, s = np.cos(a), np.sin(a)
        p = np.asarray(p, dtype=float)
        out = p.copy()
        out[..., 0] = c * p[..., 0] - s * p[..., 1]
        out[..., 1] = s * p[..., 0] + c * p[..., 1]
        return out

    def from_rotating(self, points: Any, t: float) -> np.ndarray:
        """Points fixed in the rotating frame (m, from the barycentre, the secondary on +x) where
        the view shows them at time ``t`` (they turn with the pair in the inertial view)."""
        pts = np.atleast_2d(np.asarray(points, dtype=float))
        a = (1.0 - self.turn) * float(self.theta(float(t)))
        c, s = math.cos(a), math.sin(a)
        out = np.zeros((len(pts), 3))
        out[:, 0] = c * pts[:, 0] - s * pts[:, 1]
        out[:, 1] = s * pts[:, 0] + c * pts[:, 1]
        return out

    def energy_error(self, t: float) -> float:
        """The n-body run's relative energy error (E − E₀)/|E₀| at the output nearest ``t``."""
        run = self.run
        k = int(np.clip(np.searchsorted(run.times, t), 0, len(run.times) - 1))
        e0 = float(run.energy[0])
        return float(run.energy[k] - e0) / abs(e0) if e0 else 0.0

    def angular_error(self, t: float) -> float:
        """The n-body run's relative angular-momentum error at the output nearest ``t`` (Step 232)."""
        run = self.run
        return run.angular_error(int(np.clip(np.searchsorted(run.times, t), 0, len(run.times) - 1)))


def resolve_model(central: Any, bodies: list[OrbitBody], *, span: str | None, orbit_count: float | None, dynamics: str, method: str,
                  step: str | None, follow: str | None, cannon: OrbitCannon | None = None, transfer: OrbitTransfer | None = None,
                  flyby: OrbitFlyby | None = None, many: Any = None, sky: Any = None) -> OrbitModel:
    """Everything an ``orbit`` scene computes before drawing, checked (``VidgenError`` with the
    reason): the system, the span (``span``, or ``orbit_count`` periods of the first body —
    default one; with only a cannon, the longest closed shot's period; with a transfer, until a
    little after it arrives; with a flyby, the whole pass), the n-body run, the followed body,
    the trails, the cannon's shots, the transfer's burns, the flyby's probe and the overlays'
    needs. Step 232: ``many`` (:class:`~vidgen.scenes.orbit_systems.ManySpec`) adds a
    three-body system, bodies near Lagrange points, a resonance, the barycentre or rotating
    view, the tidal schematic. Step 233: ``sky`` (:class:`~vidgen.scenes.orbit_sky.SkySpec`) a
    date, an event, the log view, an inset, or the sizes picture."""
    info_sky = None
    if sky is not None and sky.wanted():
        from . import orbit_sky as osky
        if sky.sizes is not None:
            busy = [k for k, on in (("date", sky.date is not None), ("event", sky.event), ("radial: log", sky.radial != "linear"),
                                    ("inset", sky.inset not in (None, False)), ("cannonball", cannon), ("transfer", transfer), ("flyby", flyby),
                                    ("system / resonance / tides", many is not None and many.wanted(bodies))) if on]
            if busy:
                raise VidgenError(f"sizes: the sizes picture is a scene of its own; leave out {', '.join(busy)}")
            info_sky = osky.sizes_model(central, bodies, sky.sizes)
            centre = (OrbitCentral(preset=central) if isinstance(central, str) else central).body()
            return OrbitModel(orbits.System(centre, ()), orbits.DAY, None, None, {}, specs=[], sky=info_sky)
        osky.check_sky(sky, bodies=bodies, follow=follow, cannon=cannon, transfer=transfer, flyby=flyby, many=many, dynamics=dynamics)
        info_sky = osky.SkyInfo(jd0=osky.date_jd(sky.date) if sky.date is not None else None, log=sky.radial == "log")
    info_many = None
    if many is not None and many.wanted(bodies):
        from .orbit_systems import prepare_many   # the many-body module builds on this one
        central, bodies, dynamics, info_many = prepare_many(many, central, bodies, dynamics, cannon=cannon, transfer=transfer, flyby=flyby, follow=follow)
        if info_many.restricted is not None and not many.method_given:   # adaptive: a body may pass close to the secondary
            method = "rk45"
    assist = None
    extra: list[OrbitBody] = []
    if flyby is not None:
        if cannon is not None or transfer is not None:
            raise VidgenError("flyby: a gravity assist is a scene of its own (no cannonball or transfer with it)")
        centre = (OrbitCentral(preset=central) if isinstance(central, str) else central).body()
        probe, assist = _flyby_probe(centre, flyby, [b.display_name() for b in bodies])
        extra.append(probe)
    all_bodies = [*bodies, *extra]
    system = build_system(central, all_bodies, jd=info_sky.jd0 if info_sky is not None else None)
    if info_sky is not None:
        if sky.event is not None:
            info_sky.event, info_sky.event_t = osky.resolve_event(sky.event, info_sky.jd0, system)
        if sky.inset not in (None, False):
            info_sky.inset, info_sky.inner = osky.inset_radius(sky.inset, system)
        if info_sky.log:
            info_sky.r0 = osky.log_r0(system)
    if not all_bodies and cannon is None:
        raise VidgenError("bodies: give at least 1 item (a body), or a cannonball")
    if cannon is not None and dynamics == "nbody":
        raise VidgenError("cannonball: the shots fly on Kepler orbits around the central body; use dynamics: kepler")
    if dynamics == "nbody" and (transfer is not None or flyby is not None or any(b.burns for b in bodies)):
        raise VidgenError("burns, transfers and flybys are flown on Kepler arcs (patched conics); use dynamics: kepler")
    shots, cannon_at = _shots(system.central, cannon) if cannon is not None else ([], None)
    info = None
    if transfer is not None:
        system, info = _transfer(system, all_bodies, transfer)
    _check_overlays(all_bodies, system, dynamics)
    if span is not None and orbit_count is not None:
        raise VidgenError("give span (a time) or orbits (periods of the first body), not both")
    if span is not None:
        seconds = orbits.value_si(span, "time", "span")
        if seconds <= 0:
            raise VidgenError(f"span: '{span}' must be a positive time")
    elif info is not None and orbit_count is None:
        seconds = info.arrival + 0.2 * (info.arrival - info.depart)
    elif assist is not None and orbit_count is None:
        seconds = 2 * assist.t_periapsis
    elif info_sky is not None and info_sky.event is not None and orbit_count is None:   # until a little after the event
        seconds = max(1.15 * info_sky.event_t, 30 * orbits.DAY)
    elif info_many is not None and info_many.eight is not None:   # the figure-eight: its own period
        seconds = (orbit_count if orbit_count is not None else 1.0) * info_many.eight.period
    elif not all_bodies:
        if orbit_count is not None:
            raise VidgenError("orbits counts periods of the first body; with only a cannonball give span: '3 h' (a time), or leave it out")
        seconds = _cannon_span(shots, system.central.gm, float(np.linalg.norm(cannon_at)))
    else:
        first, period = system.first_period()
        if period is None:
            o = system.orbiters[0]
            raise VidgenError(f"orbits: bodies[1] '{first}' is on an open orbit (e = {o.elements.e:g}, a {o.elements.kind}): it has no period; "
                              "give span: '200 d' (a time) instead")
        seconds = (orbit_count if orbit_count is not None else 1.0) * period
    if info_sky is not None and info_sky.jd0 is not None:
        orbits.check_valid(info_sky.jd0, info_sky.jd0 + seconds / orbits.DAY, where="span")
    late = [(name, b) for name, b in OrbitModel(system, seconds, None, None, {}).burns() if b.time > seconds]
    if late:
        name, b = late[0]
        what = f"the transfer's burn at {_time(b.time)}" if info is not None else f"{name}'s burn at {_time(b.time)}"
        raise VidgenError(f"{what} comes after the scene's span ({_time(seconds)}); make the span longer or leave it out")
    names = [system.central.name, *system.names]
    if follow is not None and follow not in names:
        raise VidgenError(f"follow: no body '{follow}' (bodies: {', '.join(names)})" + did_you_mean(follow, names))
    run = None
    if dynamics == "nbody":
        step_s = None
        if step is not None:
            step_s = orbits.value_si(step, "time", "step")
            if step_s <= 0:
                raise VidgenError(f"step: '{step}' must be a positive time")
        samples, initial = 2000, None
        if info_many is not None and info_many.restricted is not None:   # enough outputs per turn of the pair for smooth trails
            samples = int(min(40_000, max(2000, 96 * seconds / info_many.restricted.pair.period)))
        if info_many is not None and info_many.eight is not None:   # the true starting states; a step of 1/4000 of its period
            from .orbit_systems import eight_initial
            initial = eight_initial(info_many.eight)
            step_s = step_s if step_s is not None else info_many.eight.period / 4000
        run = orbits.simulate(system, seconds, method=orbits.method_name(method), step=step_s, samples=samples, initial=initial)
    elif step is not None:
        raise VidgenError("step is the n-body integration step; it needs dynamics: nbody")
    trails = {}
    for spec, o in zip(all_bodies, system.orbiters):
        whole = o.elements.period
        if info_many is not None and info_many.eight is not None:
            whole = info_many.eight.period
        elif info_many is not None and info_many.restricted is not None and o.name in info_many.near:
            whole = info_many.restricted.pair.period
        trails[o.name] = _trail_seconds(spec.trail, whole, seconds, f"{o.name}.trail")
    follow_name = None if follow == system.central.name else follow
    model = OrbitModel(system, seconds, run, follow_name, trails, shots, cannon_at, info, assist, extra, specs=all_bodies, many=info_many, sky=info_sky)
    if info_many is not None:
        from .orbit_systems import finish_many
        finish_many(model, many)
    return model


def _time(seconds: float) -> str:
    unit, scale = orbits.time_unit(seconds)
    return f"{seconds / scale:.4g} {unit}"


@dataclass(frozen=True)
class TransferInfo:
    """A resolved transfer: its ``kind``, the ``ship`` flying it, the ``target`` body (``None``
    for a radius), the radii, the result (:class:`orbits.Hohmann`, :class:`orbits.BiElliptic`
    or :class:`orbits.Phasing`), the times of departure and arrival, the lead angle the target
    needs at departure (``phase_needed``, rad; ``None`` without a target) and the one it has
    (``phase_at_depart``), whether ``depart`` was the launch window, the ship's and target's
    mean motions (rad/s), the distance between ship and target at arrival (``miss``, m)."""

    kind: str
    ship: str
    target: str | None
    r1: float
    r2: float
    result: Any
    depart: float
    arrival: float
    phase_needed: float | None
    phase_at_depart: float | None
    window: bool
    n_ship: float
    n_target: float
    miss: float | None

    @property
    def total(self) -> float:
        return float(self.result.total)


@dataclass(frozen=True)
class AssistInfo:
    """A resolved flyby: the probe's name, the planet's, the :class:`orbits.GravityAssist`,
    when the probe passes periapsis (s after the start), the planet's speed around the Sun."""

    probe: str
    planet: str
    assist: Any
    t_periapsis: float
    planet_speed: float


def lead_angle(system: Any, ship: str, target: str, t: float) -> float:
    """The angle (rad, in (−π, π]) the target leads the ship by at ``t``, in the ship's direction of motion."""
    o = system.orbiter(ship)
    r_s, v_s = o.states(t)
    r_t = system.orbiter(target).positions(t)
    sense = 1.0 if np.cross(r_s, v_s)[2] >= 0 else -1.0
    ang = sense * (math.atan2(r_t[1], r_t[0]) - math.atan2(r_s[1], r_s[0]))
    out = (ang + math.pi) % (2 * math.pi) - math.pi
    return math.pi if out == -math.pi else out


def _transfer(system: Any, bodies: list[OrbitBody], spec: OrbitTransfer) -> tuple[Any, TransferInfo]:
    """The ship's burns for the transfer (a new system with its trajectory) and what the panel
    shows of it. Raises for a ship or target off a circular orbit, orbits in different planes,
    a ship with burns of its own, a phasing orbit into the planet, an impossible transfer."""
    names = system.names
    if spec.ship not in names:
        raise VidgenError(f"transfer.ship: no body '{spec.ship}' (bodies: {', '.join(names)})" + did_you_mean(spec.ship, names))
    ship = system.orbiter(spec.ship)
    k = names.index(spec.ship)
    if bodies[k].burns:
        raise VidgenError(f"transfer: '{spec.ship}' has burns of its own; the transfer makes its burns (leave out its burns:)")
    parent = system.parent_body(ship)
    el = ship.elements
    if el.e > orbits.CIRCULAR_E:
        raise VidgenError(f"transfer: '{spec.ship}' is on an orbit with e = {el.e:.4g}; a {spec.kind} transfer starts from a circular orbit "
                          f"(give it e: 0, or plan the burns yourself)")
    target, r2 = None, None
    to = spec.to
    if isinstance(to, str) and to in names:
        if to == spec.ship:
            raise VidgenError("transfer.to: the ship cannot fly to itself")
        target = to
        tgt = system.orbiter(to)
        if tgt.parent != ship.parent:
            raise VidgenError(f"transfer.to: '{to}' goes around {tgt.parent or system.central.name}, '{spec.ship}' around "
                              f"{ship.parent or system.central.name}: a transfer here is between orbits around one body")
        tel = tgt.elements
        if tel.e > orbits.CIRCULAR_E:
            raise VidgenError(f"transfer.to: {to}'s orbit has e = {tel.e:.4g}; the transfer is computed between circular orbits — give {to} e: 0 "
                              "(the circular approximation; say so in the caption)")
        h1 = el.rotation[:, 2]
        h2 = tel.rotation[:, 2]
        tilt = math.acos(max(-1.0, min(1.0, float(h1 @ h2))))
        if tilt > orbits.COPLANAR:
            raise VidgenError(f"transfer.to: {to}'s orbit is inclined {math.degrees(tilt):.3g}° to {spec.ship}'s; a {spec.kind} transfer here is between "
                              f"coplanar orbits — give both the same plane (i: 0: the coplanar approximation) or add a plane-change burn "
                              f"(Δv = 2 v sin(Δi/2))")
        r2 = tel.p
        n_target = tel.mean_motion
    elif isinstance(to, str) and not any(c.isdigit() for c in to):
        raise VidgenError(f"transfer.to: no body '{to}' (bodies: {', '.join(names)}); give a body or a radius ('42164 km')" + did_you_mean(to, names))
    else:
        r2 = orbits.value_si(to, "length", "transfer.to")
        if r2 <= 0:
            raise VidgenError(f"transfer.to: '{to}' must be a positive radius")
        if parent.radius > 0 and r2 <= parent.radius:
            raise VidgenError(f"transfer.to: a {r2 / 1000:,.0f} km orbit lies inside {parent.name} (radius {parent.radius / 1000:,.0f} km)")
        n_target = math.sqrt(el.mu / r2**3)
    r1 = el.p
    mu = el.mu
    n_ship = el.mean_motion
    kind = spec.kind
    if kind == "phasing":
        if target is None:
            raise VidgenError("transfer: phasing catches up a body on the same orbit; give to: a body's name")
        if not math.isclose(r1, r2, rel_tol=1e-6):
            raise VidgenError(f"transfer: phasing is on one orbit, but {target} is at {_distance(r2)} and {spec.ship} at {_distance(r1)}; use kind: hohmann")
    elif math.isclose(r1, r2, rel_tol=1e-9):
        raise VidgenError(f"transfer.to: {spec.ship} is already on that orbit ({_distance(r1)}); to catch up a body there use kind: phasing")
    if spec.apoapsis is not None and kind != "bielliptic":
        raise VidgenError("transfer.apoapsis is the far point of a bielliptic transfer; give kind: bielliptic")
    window = spec.depart == "window"
    if kind == "hohmann":
        result = orbits.hohmann(mu, r1, r2, mu_target=(system.orbiter(target).elements.mu if target else mu), mu_from=mu)
        swept, legs = math.pi, None
    elif kind == "bielliptic":
        if spec.apoapsis is None:
            raise VidgenError("transfer: a bielliptic transfer needs apoapsis: its far point ('300000 km'), beyond both orbits")
        rb = orbits.value_si(spec.apoapsis, "length", "transfer.apoapsis")
        result = orbits.bielliptic(mu, r1, r2, rb)
        swept = 2 * math.pi
        legs = (math.pi * math.sqrt(result.a1**3 / mu), math.pi * math.sqrt(result.a2**3 / mu))
    else:
        result = None
        swept, legs = 0.0, None
    if window and target is not None and kind != "phasing":
        needed = (swept - n_target * result.time + math.pi) % (2 * math.pi) - math.pi
        depart = orbits.window_wait(lead_angle(system, spec.ship, target, 0.0), needed, n_ship, n_target)
    elif window:
        depart, needed = 0.0, None
    else:
        depart = orbits.value_si(spec.depart, "time", "transfer.depart")
        if depart < 0:
            raise VidgenError(f"transfer.depart: '{spec.depart}' is before the start")
        needed = (swept - n_target * result.time + math.pi) % (2 * math.pi) - math.pi if (target is not None and result is not None) else None
    lead = lead_angle(system, spec.ship, target, depart) if target is not None else None
    if kind == "phasing":
        result = orbits.phasing(mu, r1, lead, spec.revolutions, radius=parent.radius, body=parent.name)
        d = "retrograde" if result.lower else "prograde"
        plans = [orbits.BurnPlan(depart, {d: result.dv}), orbits.BurnPlan(depart + result.time, {_opposite(d): result.dv})]
        needed = None
    elif kind == "hohmann":
        d = "prograde" if result.raising else "retrograde"
        plans = [orbits.BurnPlan(depart, {d: result.dv1}), orbits.BurnPlan(depart + result.time, {d: result.dv2})]
    else:
        raising = r2 > r1
        plans = [orbits.BurnPlan(depart, {"prograde": result.dv1}), orbits.BurnPlan(depart + legs[0], {"prograde" if raising else "retrograde": result.dv2}),
                 orbits.BurnPlan(depart + legs[0] + legs[1], {"retrograde": result.dv3})]
    trajectory = _fly(el, plans, parent, f"transfer ({spec.ship})")
    orbiters = tuple(replace(o, trajectory=trajectory) if o.name == spec.ship else o for o in system.orbiters)
    new = orbits.System(system.central, orbiters)
    arrival = trajectory.burns[-1].time
    miss = float(np.linalg.norm(new.orbiter(spec.ship).positions(arrival) - new.orbiter(target).positions(arrival))) if target else None
    return new, TransferInfo(kind, spec.ship, target, r1, r2, result, depart, arrival, needed, lead, window, n_ship, n_target, miss)


def _flyby_probe(centre: Any, spec: OrbitFlyby, names: list[str]) -> tuple[OrbitBody, AssistInfo]:
    """The flyby's probe as a body (its state where the pass starts, ``reach`` periapsis
    distances out) and the gravity assist (raises for a periapsis inside the planet or its
    atmosphere, a side the direction of arrival cannot give)."""
    if spec.name in names or spec.name == centre.name:
        raise VidgenError(f"flyby.name: '{spec.name}' is already a body's name; give the probe another")
    v_inf = orbits.value_si(spec.v_inf, "speed", "flyby.v_inf")
    if v_inf <= 0:
        raise VidgenError("flyby.v_inf must be a positive speed")
    if (spec.periapsis is None) == (spec.altitude is None):
        raise VidgenError("flyby: give its closest approach one way: periapsis (from the centre) or altitude (above the surface)")
    if spec.altitude is not None:
        if centre.radius <= 0:
            raise VidgenError(f"flyby.altitude needs the radius of {centre.name} (give central: {{radius: ...}}) or use periapsis")
        rp = centre.radius + orbits.value_si(spec.altitude, "length", "flyby.altitude")
    else:
        rp = orbits.value_si(spec.periapsis, "length", "flyby.periapsis")
    if rp <= 0:
        raise VidgenError("flyby: the periapsis distance must be positive")
    atmosphere = orbits.value_si(spec.atmosphere, "length", "flyby.atmosphere") if spec.atmosphere is not None else 0.0
    if spec.planet_speed is not None:
        speed = orbits.value_si(spec.planet_speed, "speed", "flyby.planet_speed")
    else:
        key = orbits.preset_key(centre)
        if key is None or key not in orbits.ORBITS or orbits.ORBITS[key].around != "sun":
            raise VidgenError(f"flyby.planet_speed: give the speed of {centre.name} around the Sun ('13.06 km/s'); it is known for the planet presets only")
        p = orbits.ORBITS[key]
        speed = math.sqrt((orbits.GM_SUN + centre.gm) / p.a)
    if speed <= 0:
        raise VidgenError("flyby.planet_speed must be positive")
    angle = orbits.value_si(spec.angle, "angle", "flyby.angle")
    v_in = v_inf * np.array([math.cos(angle), math.sin(angle)])
    ga = orbits.gravity_assist(centre.gm, [speed, 0.0], v_in, rp, side=spec.side, radius=centre.radius, atmosphere=atmosphere, body=centre.name)
    el = ga.flyby.elements
    crossing = float(np.linalg.norm(ga.flyby.centre))   # where the asymptotes cross, |a| e from the planet
    r_start = spec.reach * rp if spec.reach is not None else max(6 * rp, 1.6 * crossing)
    nu0 = -math.acos(max(-1.0, min(1.0, (el.p / r_start - 1.0) / el.e)))
    r, v = el.state_at_anomaly(nu0)
    t_peri = el.time_of_flight(nu0, 0.0)
    probe = OrbitBody(name=spec.name, r=[f"{float(x)!r} m" for x in r[:2]], v=[f"{float(x)!r} m/s" for x in v[:2]], color="highlight")
    return probe, AssistInfo(spec.name, centre.name, ga, t_peri, speed)


def _check_overlays(bodies: list[OrbitBody], system: Any, dynamics: str) -> None:
    """The overlays a body asks for fit its orbit: an ellipse's geometry and equal-time sectors
    need a closed orbit; sectors and velocity vectors follow the Kepler orbit (not n-body)."""
    for k, (spec, o) in enumerate(zip(bodies, system.orbiters), start=1):
        where = f"bodies[{k}] '{o.name}'"
        el = o.elements
        if spec.geometry_parts() and not el.closed:
            raise VidgenError(f"{where}: geometry: its orbit is a {el.kind} (e = {el.e:g}); foci, axes and an apoapsis belong to an ellipse (e < 1)")
        if spec.sector_spec() is not None:
            if not el.closed:
                raise VidgenError(f"{where}: sectors: its orbit is a {el.kind} (e = {el.e:g}) with no period to cut into equal times")
            if dynamics == "nbody":
                raise VidgenError(f"{where}: sectors are swept on the Kepler orbit; with dynamics: nbody the path is not one (use dynamics: kepler)")
        if spec.velocity_spec() is not None and dynamics == "nbody":
            raise VidgenError(f"{where}: velocity vectors come from the Kepler orbit (vis-viva); with dynamics: nbody use dynamics: kepler")


def _shots(centre: Any, cannon: OrbitCannon) -> tuple[list[Any], Any]:
    """Newton's cannonball: the shots and the cannon's position (m)."""
    if centre.radius <= 0:
        raise VidgenError(f"cannonball: the central body {centre.name} needs a radius (give central: {{radius: '6371 km', ...}})")
    height = orbits.value_si(cannon.altitude, "length", "cannonball.altitude") if cannon.altitude is not None else centre.radius / 10
    if height <= 0:
        raise VidgenError(f"cannonball.altitude: '{cannon.altitude}' puts the cannon on or under the surface of {centre.name}")
    r0 = centre.radius + height
    speeds = []
    for n, s in enumerate(cannon.speeds, start=1):
        where = f"cannonball.speeds[{n}]"
        if isinstance(s, str):
            named = orbits.named_speed(s, centre.gm, r0)
            value = named if named is not None else orbits.value_si(s, "speed", where)
        else:
            value = float(s) * orbits.circular_speed(centre.gm, r0)
        if not value > 0:
            raise VidgenError(f"{where}: a launch speed must be positive (got {s})")
        speeds.append(value)
    angle = math.radians(cannon.at)
    shots = orbits.cannon_shots(centre.gm, centre.radius, r0, speeds, angle, cannon.clockwise)
    return shots, np.array([math.cos(angle), math.sin(angle), 0.0]) * r0


def _cannon_span(shots: list[Any], mu: float, r0: float) -> float:
    """A cannonball scene's default span: long enough for every closed shot to come round
    (at most four circular periods), at least one circular period."""
    circular = 2 * math.pi * math.sqrt(r0**3 / mu)
    closed = [s.elements.period for s in shots if s.kind in ("circular", "elliptical")]
    return min(max([circular, *closed]), 4 * circular)


def _trail_seconds(trail: Any, period: float | None, span: float, where: str) -> float:
    """A trail's length (s): true a quarter of the orbit, a share of it, a time, false none (an
    open orbit's share is of the span)."""
    if trail is False:
        return 0.0
    whole = period if period is not None else span
    if trail is True:
        return 0.25 * whole
    if isinstance(trail, (int, float)):
        if trail <= 0:
            raise VidgenError(f"{where}: give a positive share of the orbit (0.5), a time ('30 d') or false")
        return float(trail) * whole
    seconds = orbits.value_si(trail, "time", where)
    if seconds <= 0:
        raise VidgenError(f"{where}: '{trail}' must be a positive time")
    return seconds


__all__ = ["GEOMETRY_PARTS", "MAX_SHOTS", "SECTOR_COUNTS", "SHAPE_KEYS", "AssistInfo", "OrbitBody", "OrbitBurn", "OrbitCannon", "OrbitCentral",
           "OrbitFlyby", "OrbitModel", "OrbitSectors", "OrbitTransfer", "OrbitVelocity", "TransferInfo", "Value", "build_system", "lead_angle", "resolve_model"]
