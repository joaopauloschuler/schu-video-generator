"""The ``orbit`` scene's bodies as written in YAML and their resolution into a
:class:`orbits.System` (Phase X, DESIGN §98): a body from a preset (the planets on their J2000
orbits, the Moon, an ISS-like orbit, a geostationary one, Halley's comet), from orbital elements
(``a`` and ``e``, ``periapsis`` and ``apoapsis``, ``periapsis`` and ``e``, ``altitude``) or from a
position and velocity, with values written with their units (``"1 AU"``, ``"7.8 km/s"``)."""

import math
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


def build_system(central: Any, bodies: list[OrbitBody]) -> Any:
    """The :class:`orbits.System` of the central body (a preset name or :class:`OrbitCentral`)
    and the bodies, checked: names unique, ``around`` a body listed before, a preset's primary
    present, elements consistent, periapses outside the bodies they orbit."""
    centre = (OrbitCentral(preset=central) if isinstance(central, str) else central).body()
    central_key = orbits.preset_key(centre)
    out: list[Any] = []
    seen: dict[str, Any] = {}
    presets: dict[str, str] = {}   # preset key -> the name of the body using it
    for k, spec in enumerate(bodies, start=1):
        where = f"bodies[{k}]"
        preset = orbits.orbit_preset(spec.preset, where) if spec.preset else None
        name = spec.display_name()
        if not name:
            raise VidgenError(f"{where}: give a name (or a preset)")
        where = f"bodies[{k}] '{name}'"
        if name in seen or name == centre.name:
            raise VidgenError(f"{where}: the name is used twice; give each body its own name")
        parent = _parent(spec, preset, where, centre, central_key, seen, presets)
        parent_body = centre if parent is None else seen[parent].body
        gm = _gm(spec.gm, spec.mass, where)
        radius = _length(spec.radius, f"{where}.radius")
        body = orbits.Body(name, gm if gm is not None else (preset.body.gm if preset else 0.0),
                           radius if radius is not None else (preset.body.radius if preset else 0.0), preset.body.color if preset else "")
        elements = _elements(spec, preset, where, parent_body.gm + body.gm, parent_body)
        q = elements.periapsis
        if parent_body.radius > 0 and q <= parent_body.radius:
            raise VidgenError(f"{where}: its periapsis ({_distance(q)} from the centre of {parent_body.name}) lies inside {parent_body.name} "
                              f"(radius {_distance(parent_body.radius)}): it would crash; raise the periapsis or lower e")
        orbiter = orbits.Orbiter(name, body, elements, parent)
        out.append(orbiter)
        seen[name] = orbiter
        if preset is not None:
            presets.setdefault(preset.key, name)
    return orbits.System(centre, tuple(out))


def _distance(metres: float) -> str:
    if metres >= 0.05 * orbits.AU:
        return f"{metres / orbits.AU:.4g} AU"
    return f"{metres / 1000:,.0f} km"


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
                 cannon_at: Any = None) -> None:
        self.system, self.span, self.run, self.follow, self.trails = system, span, run, follow, trails
        self.shots = list(shots or [])
        self.cannon_at = cannon_at

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
        """Position (m) in the view's frame: relative to the followed body, else the central one."""
        p = self.position(name, t)
        return p - self.position(self.follow, t) if self.follow is not None else p

    def energy_error(self, t: float) -> float:
        """The n-body run's relative energy error (E − E₀)/|E₀| at the output nearest ``t``."""
        run = self.run
        k = int(np.clip(np.searchsorted(run.times, t), 0, len(run.times) - 1))
        e0 = float(run.energy[0])
        return float(run.energy[k] - e0) / abs(e0) if e0 else 0.0


def resolve_model(central: Any, bodies: list[OrbitBody], *, span: str | None, orbit_count: float | None, dynamics: str, method: str,
                  step: str | None, follow: str | None, cannon: OrbitCannon | None = None) -> OrbitModel:
    """Everything an ``orbit`` scene computes before drawing, checked (``VidgenError`` with the
    reason): the system, the span (``span``, or ``orbit_count`` periods of the first body —
    default one; with only a cannon, the longest closed shot's period), the n-body run, the
    followed body, the trails, the cannon's shots and the overlays' needs."""
    system = build_system(central, bodies)
    if not bodies and cannon is None:
        raise VidgenError("bodies: give at least 1 item (a body), or a cannonball")
    if cannon is not None and dynamics == "nbody":
        raise VidgenError("cannonball: the shots fly on Kepler orbits around the central body; use dynamics: kepler")
    shots, cannon_at = _shots(system.central, cannon) if cannon is not None else ([], None)
    _check_overlays(bodies, system, dynamics)
    if span is not None and orbit_count is not None:
        raise VidgenError("give span (a time) or orbits (periods of the first body), not both")
    if span is not None:
        seconds = orbits.value_si(span, "time", "span")
        if seconds <= 0:
            raise VidgenError(f"span: '{span}' must be a positive time")
    elif not bodies:
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
        run = orbits.simulate(system, seconds, method=orbits.method_name(method), step=step_s)
    elif step is not None:
        raise VidgenError("step is the n-body integration step; it needs dynamics: nbody")
    trails = {}
    for spec, o in zip(bodies, system.orbiters):
        trails[o.name] = _trail_seconds(spec.trail, o.elements.period, seconds, f"{o.name}.trail")
    return OrbitModel(system, seconds, run, None if follow == system.central.name else follow, trails, shots, cannon_at)


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


__all__ = ["GEOMETRY_PARTS", "MAX_SHOTS", "SECTOR_COUNTS", "SHAPE_KEYS", "OrbitBody", "OrbitCannon", "OrbitCentral", "OrbitModel", "OrbitSectors",
           "OrbitVelocity", "Value", "build_system", "resolve_model"]
