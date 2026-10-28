"""The ``orbit`` scene's many-body params and their resolution (Phase X, Step 232, DESIGN §98.6):
``system`` (a circular restricted three-body pair — ``earth_moon``, ``sun_earth``,
``sun_jupiter`` or your own with a mass ratio — or the ``figure_eight`` of three equal masses),
bodies placed at a Lagrange point (``near: L4`` with a ``shift``), ``resonance`` (period ratios,
the Laplace angle, conjunctions), ``tides`` (the schematic) and what the scene computes from them:
the rotating frame, the Jacobi constants, co-orbital motion, the barycentre. The physics is in
:mod:`vidgen.orbits.threebody` and :mod:`vidgen.orbits.manybody`."""

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vidgen.api import *

from .orbit_parts import LagrangeName, OrbitBody, OrbitCentral, Value

#: The many-body presets that are not restricted pairs.
CHOREOGRAPHIES = ("figure_eight",)
#: The figure-eight's bodies.
EIGHT_NAMES = ("A", "B", "C")


class OrbitSystem(SceneParams):
    """A many-body system: ``{preset}`` or a restricted pair ``{primary, secondary, mu, separation}``
    or the figure-eight ``{preset: figure_eight, mass, scale}``."""

    preset: str | None = None
    """earth_moon, sun_earth (the Sun with the Earth–Moon barycentre), sun_jupiter (restricted three-body pairs) or figure_eight (three equal masses)."""
    primary: str | None = None
    """The larger body of a pair of your own (a preset body: sun, earth, jupiter...)."""
    secondary: str | None = None
    """The smaller body of the pair (a preset body); it goes round the primary on a circle."""
    mu: float | None = Field(default=None, gt=0, le=0.5)
    """The mass ratio μ = m₂/(m₁ + m₂) instead of the bodies' own (the secondary's mass is set from it): L4 and L5 are stable below 0.0385 (Routh)."""
    separation: Value | None = None
    """The distance between the primaries ('5.2 AU'); default: the secondary preset's mean distance."""
    mass: Value | None = None
    """figure_eight: each body's mass ('1 Msun')."""
    scale: Value | None = None
    """figure_eight: the length the published unit stands for ('1 AU'): the eight is about 2.2 of it wide."""

    @model_validator(mode="before")
    @classmethod
    def _from_name(cls, data: Any) -> Any:
        return {"preset": data} if isinstance(data, str) else data


class OrbitResonance(SceneParams):
    """A mean-motion resonance: ``{bodies: [Io, Europa, Ganymede], conjunctions: true}``."""

    bodies: list[str] = Field(min_length=2, max_length=3)
    """Two or three bodies around the same body, inner first: their period ratios (and the Laplace angle of a 1:2:4 chain) in the panel."""
    conjunctions: bool = True
    """Mark each conjunction of neighbours (a line from the centre through both) as it happens: they recur at nearly the same places."""
    keep: int = Field(default=6, ge=1, le=24)
    """How many past conjunctions of each pair stay drawn (faint)."""

    @model_validator(mode="before")
    @classmethod
    def _from_list(cls, data: Any) -> Any:
        return {"bodies": data} if isinstance(data, list) else data


class OrbitTides(SceneParams):
    """The tidal schematic: ``{satellite: moon, locking: true}`` (the central body is the planet)."""

    satellite: str = "moon"
    """The body raising the tides (a preset orbiting the central body: moon, io...)."""
    locking: bool = True
    """Show the satellite's near side marked: it spins once per orbit (tidal locking), so the same face looks at the planet."""
    points: int = Field(default=12, ge=4, le=36)
    """How many points around the planet carry arrows."""

    @model_validator(mode="before")
    @classmethod
    def _from_flag(cls, data: Any) -> Any:
        if data is True:
            return {}
        return data


@dataclass(frozen=True)
class RestrictedInfo:
    """A resolved restricted pair: the :class:`orbits.Restricted`, the primary's and secondary's
    names in the system, its preset key (``None``: of the author's own)."""

    pair: Any
    primary: str
    secondary: str
    preset: str | None


@dataclass(frozen=True)
class ResonanceInfo:
    """A resolved resonance: the bodies (inner first), their parent's name (``None``: the central
    body), periods (s), the conjunctions of each neighbouring pair: (time s, direction angle rad)."""

    bodies: tuple[str, ...]
    parent: str | None
    periods: tuple[float, ...]
    conjunctions: tuple[tuple[tuple[float, float], ...], ...]
    keep: int
    show: bool


@dataclass(frozen=True)
class ManySpec:
    """The many-body params of an ``orbit`` scene, as written (passed to ``resolve_model``)."""

    system: OrbitSystem | None = None
    central_given: bool = False
    dynamics_given: bool = False
    resonance: OrbitResonance | None = None
    origin: str | None = None
    view: str = "inertial"
    center: str | None = None
    tides: OrbitTides | None = None
    lagrange: Any = False
    zero_velocity: Any = False
    method_given: bool = False

    def wanted(self, bodies: list[OrbitBody]) -> bool:
        """Whether anything here (or a body's ``near`` / ``curvature``) is used."""
        return (self.system is not None or self.resonance is not None or self.tides is not None or self.center is not None or self.view != "inertial"
                or self.origin not in (None, "central") or self.lagrange is not False or self.zero_velocity is not False
                or any(b.near or b.curvature or b.shift is not None or b.drift is not None for b in bodies))


@dataclass
class ManyInfo:
    """What the many-body params add to an ``orbit`` model."""

    origin: str = "central"
    restricted: RestrictedInfo | None = None
    eight: Any = None
    resonance: ResonanceInfo | None = None
    turn0: float = 0.0
    center: str | None = None
    near: dict[str, str] = field(default_factory=dict)
    curvature: dict[str, tuple[float, int]] = field(default_factory=dict)
    tides: OrbitTides | None = None
    lagrange: tuple[str, ...] = ()
    zero_velocity: str | None = None
    jacobi: dict[str, np.ndarray] = field(default_factory=dict)
    coorbital: dict[str, tuple[str, float, float]] = field(default_factory=dict)
    trail_samples: dict[str, int] = field(default_factory=dict)
    closure: float | None = None


def prepare_many(spec: ManySpec, central: Any, bodies: list[OrbitBody], dynamics: str, *, cannon: Any, transfer: Any, flyby: Any,
                 follow: str | None) -> tuple[Any, list[OrbitBody], str, ManyInfo]:
    """The central body, bodies and dynamics a scene's many-body params make (the system's own
    bodies added, ``near`` bodies placed), checked against the rest of the scene."""
    if spec.tides is not None:
        others = [k for k, v in (("system", spec.system), ("resonance", spec.resonance), ("cannonball", cannon), ("transfer", transfer), ("flyby", flyby),
                                 ("center", spec.center)) if v is not None] + (["bodies"] if bodies else [])
        if others:
            raise VidgenError(f"tides: the tidal schematic is a scene of its own; leave out {', '.join(others)}")
        if spec.view != "inertial" or spec.lagrange is not False or spec.zero_velocity is not False:
            raise VidgenError("tides: the tidal schematic has no rotating view, Lagrange points or zero-velocity curves")
        sat = orbits.orbit_preset(spec.tides.satellite, "tides.satellite")
        if not spec.central_given:
            central = sat.around
        centre = (OrbitCentral(preset=central) if isinstance(central, str) else central).body()
        if orbits.preset_key(centre) != sat.around:
            raise VidgenError(f"tides: {sat.body.name} goes around {orbits.BODIES[sat.around].name}, not {centre.name} (central: {sat.around})")
        if sat.body.gm <= 0 or centre.radius <= 0:
            raise VidgenError("tides: the satellite needs a mass and the planet a radius")
        bodies = [OrbitBody(preset=sat.key, trail=False)]
        return central, bodies, dynamics, ManyInfo(tides=spec.tides)
    if spec.system is not None:
        if cannon is not None or transfer is not None or flyby is not None:
            raise VidgenError("system: a three-body system or the figure-eight is a scene of its own (no cannonball, transfer or flyby)")
        if spec.dynamics_given and dynamics != "nbody":
            raise VidgenError("system: its bodies pull on one another; leave out dynamics (it is nbody)")
        dynamics = "nbody"
    central, bodies, restricted, eight = expand_system(central, bodies, spec.system, spec.central_given)
    bodies, near = place_near(bodies, restricted)
    origin = spec.origin or ("barycentre" if spec.system is not None else "central")
    if spec.view == "rotating" and restricted is None:
        raise VidgenError("view: rotating turns with a three-body pair; give system: earth_moon, sun_earth, sun_jupiter or {primary, secondary}")
    if restricted is not None and origin != "barycentre":
        raise VidgenError("origin: a three-body system is seen from its barycentre (leave origin out)")
    if follow is not None and origin == "barycentre":
        raise VidgenError("follow: the view is centred on the barycentre; leave out follow (or origin)")
    if (spec.lagrange is not False or spec.zero_velocity is not False) and restricted is None:
        what = "lagrange" if spec.lagrange is not False else "zero_velocity"
        raise VidgenError(f"{what}: Lagrange points and zero-velocity curves belong to a three-body pair; give system: earth_moon, sun_earth, sun_jupiter "
                          "or {primary, secondary}")
    if spec.system is not None and any(b.burns for b in bodies):
        raise VidgenError("burns are flown on Kepler arcs (patched conics); a three-body system is integrated (n-body): leave out burns")
    points: tuple[str, ...] = ()
    if spec.lagrange is True:
        points = orbits.LAGRANGE_NAMES
    elif isinstance(spec.lagrange, list):
        points = tuple(dict.fromkeys(spec.lagrange))
    info = ManyInfo(origin=origin, restricted=restricted, eight=eight, turn0=1.0 if spec.view == "rotating" else 0.0, center=spec.center, near=near,
                    lagrange=points)
    return central, bodies, dynamics, info


def finish_many(model: Any, spec: ManySpec) -> None:
    """What needs the resolved model: the resonance's conjunctions, the Jacobi constants and
    co-orbital motion of bodies near Lagrange points, which way curving paths bend, the
    figure-eight's return, the bodies to centre on and to draw zero-velocity curves for."""
    info = model.many
    system = model.system
    names = [system.central.name, *system.names]
    if spec.center is not None and spec.center not in names:
        raise VidgenError(f"center: no body '{spec.center}' (bodies: {', '.join(names)})" + did_you_mean(spec.center, names))
    if spec.resonance is not None:
        info.resonance = resonance_info(spec.resonance, system, model.span)
    for o, b in zip(system.orbiters, model.specs):
        if b.curvature:
            info.curvature[o.name] = curvature(model, o.name)
    r = info.restricted
    if r is not None:
        for name in info.near:
            info.jacobi[name] = jacobi_series(model, name)
            rel = model.run.positions[model.run.names.index(name)]
            sec = model.run.positions[model.run.names.index(r.secondary)]
            ang = orbits.coorbital_angles(rel, sec)
            info.coorbital[name] = (orbits.coorbital_kind(ang), float(ang.min()), float(ang.max()))
        for name, length in model.trails.items():   # a trail many turns long, seen turning with the pair
            info.trail_samples[name] = int(min(2400, max(64, 64 * length / r.pair.period)))
        zv = spec.zero_velocity
        if zv is not False:
            target = zv if isinstance(zv, str) else next(iter(info.near), None)
            if target is None:
                raise VidgenError("zero_velocity: its curve is drawn for a body's Jacobi constant; add a body near a Lagrange point (near: L4)")
            if target not in info.near:
                raise VidgenError(f"zero_velocity: '{target}' is not a body placed near a Lagrange point ({', '.join(info.near) or 'none'})")
            info.zero_velocity = target
    if info.eight is not None and model.run is not None:
        t = min(info.eight.period, model.span)
        if t >= info.eight.period * (1 - 1e-9):
            rel = [model.view(n, t) - model.view(n, 0.0) for n in names]
            info.closure = float(max(np.linalg.norm(x) for x in rel)) / float(np.max(np.abs(info.eight.positions)))
    if info.origin == "barycentre":
        info.trail_samples.setdefault(system.central.name, 64)
        if info.eight is not None:   # the figure-eight's A moves too: its trail as long as the others'
            model.trails[system.central.name] = model.trails[system.names[0]]


def jacobi_series(model: Any, name: str) -> np.ndarray:
    """The Jacobi constant (normalised) of a body in a restricted pair at each output of the
    n-body run, from its inertial position and velocity about the barycentre."""
    run = model.run
    pair = model.many.restricted.pair
    d, omega, mu = pair.separation, pair.omega, pair.mu
    t = run.times
    k = run.names.index(name)
    p, v = run.positions[k], run.velocities[k]
    gms = [model.system.central.gm] + [o.body.gm for o in model.system.orbiters]
    b = orbits.barycentre(gms, run.positions)
    vb = orbits.barycentre(gms, run.velocities)
    sec = run.positions[run.names.index(model.many.restricted.secondary)]
    rho = (p - b) / d
    vel = (v - vb) / (omega * d)
    r1 = np.linalg.norm(p, axis=1) / d
    r2 = np.linalg.norm(p - sec, axis=1) / d
    return np.asarray(orbits.jacobi_inertial(mu, rho, vel, r1, r2)).reshape(len(t))


def curvature(model: Any, name: str) -> tuple[float, int]:
    """Which way a body's path bends around the central body over the span: the share of samples
    at which it is concave towards it, and the number of samples. Accelerations from every body
    with mass (Newton), not from the drawn path."""
    ts = np.linspace(0.0, model.span, 721)
    central = model.system.central.name
    r = model.position(name, ts)
    v = model.velocity(name, ts)
    a = np.zeros_like(r)   # the body's acceleration minus the central body's (positions are relative to it)
    for n in dict.fromkeys([*model.massive(), name]):
        gm = model.system.central.gm if n == central else model.system.orbiter(n).body.gm
        p = model.position(n, ts)
        if n != name:
            d = p - r
            a += gm * d / np.linalg.norm(d, axis=1)[:, None] ** 3
        if n != central and gm > 0:
            a -= gm * p / np.linalg.norm(p, axis=1)[:, None] ** 3
    toward = -r   # the central body, from the body
    ok = orbits.bends_toward(v, a, toward)
    return float(np.mean(ok)), len(ts)


def expand_system(central: Any, bodies: list[OrbitBody], system: OrbitSystem | None, central_given: bool) -> tuple[Any, list[OrbitBody], RestrictedInfo | None, Any]:
    """The central body and the bodies with a ``system``'s own bodies first (the secondary of a
    restricted pair; the figure-eight's B and C around A), and what the system is."""
    if system is None:
        return central, bodies, None, None
    preset = system.preset.strip().lower() if system.preset else None
    if central_given:
        raise VidgenError("system: it sets the central body (the primary, or the figure-eight's A); leave central out")
    if preset in CHOREOGRAPHIES:
        extra = [k for k in ("primary", "secondary", "mu", "separation") if getattr(system, k) is not None]
        if extra:
            raise VidgenError(f"system: figure_eight takes mass and scale, not {', '.join(extra)}")
        if bodies:
            raise VidgenError("system: figure_eight is three bodies of its own (A, B, C); leave bodies out")
        gm = orbits.value_si(system.mass, "mass", "system.mass") * orbits.G if system.mass is not None else orbits.GM_SUN
        length = orbits.value_si(system.scale, "length", "system.scale") if system.scale is not None else orbits.AU
        if gm <= 0 or length <= 0:
            raise VidgenError("system: figure_eight needs a positive mass and scale")
        eight = orbits.figure_eight(gm, length)
        mass_text = f"{gm:.6e} m^3/s^2"
        a = OrbitCentral(name=EIGHT_NAMES[0], gm=mass_text, color="highlight")
        out = []
        for k, name in enumerate(EIGHT_NAMES[1:], start=1):
            # B's velocity relative to A is radial (B and C start with A's velocity): the Kepler
            # orbit the model keeps for a body is a stand-in from the barycentric velocity; the
            # run starts from the true states (eight_initial)
            r = eight.positions[k] - eight.positions[0]
            v = eight.velocities[k]
            out.append(OrbitBody(name=name, gm=mass_text, r=[f"{float(x)!r} m" for x in r[:2]], v=[f"{float(x)!r} m/s" for x in v[:2]],
                                 color=("primary", "accent")[k - 1], trail=0.35))
        return a, out, None, eight
    if system.mass is not None or system.scale is not None:
        raise VidgenError("system: mass and scale belong to figure_eight")
    if preset is not None:
        if system.primary is not None or system.secondary is not None:
            raise VidgenError(f"system: the preset '{system.preset}' names its bodies; leave out primary and secondary (or give them without a preset)")
        pair = orbits.restricted_preset(preset)
        key: str | None = pair.key
    else:
        if system.primary is None or system.secondary is None:
            raise VidgenError("system: give a preset (earth_moon, sun_earth, sun_jupiter, figure_eight) or primary and secondary")
        primary = orbits.body_preset(system.primary, "system.primary")
        secondary = orbits.body_preset(system.secondary, "system.secondary")
        if secondary.gm > primary.gm:
            raise VidgenError(f"system: the primary is the larger body ({secondary.name} is heavier than {primary.name}); swap them")
        sep = _separation(system.secondary)
        pair = orbits.Restricted("custom", primary, secondary, sep)
        key = None
    if system.separation is not None:
        sep = orbits.value_si(system.separation, "length", "system.separation")
        if sep <= 0:
            raise VidgenError("system.separation must be a positive distance")
        pair = orbits.Restricted(pair.key, pair.primary, pair.secondary, sep, pair.source)
    if system.mu is not None:
        pair = pair.with_mu(system.mu)
    if pair.primary.radius + pair.secondary.radius >= pair.separation:
        raise VidgenError(f"system: {pair.primary.name} and {pair.secondary.name} would touch at {pair.separation / 1000:,.0f} km apart")
    names = {b.display_name() for b in bodies}
    if pair.secondary.name in names or pair.primary.name in names:
        raise VidgenError(f"system: {pair.primary.name} and {pair.secondary.name} are the system's own bodies; do not list them in bodies")
    centre = OrbitCentral(name=pair.primary.name, gm=f"{pair.primary.gm!r} m^3/s^2", radius=f"{pair.primary.radius!r} m", color=pair.primary.color or None)
    sec = OrbitBody(name=pair.secondary.name, gm=f"{pair.secondary.gm!r} m^3/s^2", radius=f"{pair.secondary.radius!r} m", a=f"{pair.separation!r} m", e=0.0,
                    color=pair.secondary.color or None, trail=False)
    return centre, [sec, *bodies], RestrictedInfo(pair, pair.primary.name, pair.secondary.name, key), None


def eight_initial(eight: Any) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """The figure-eight's starting states of B and C relative to A (for the n-body run)."""
    return {name: (eight.positions[k] - eight.positions[0], eight.velocities[k] - eight.velocities[0]) for k, name in enumerate(EIGHT_NAMES) if k}


def _separation(secondary: str) -> float:
    try:
        return orbits.orbit_preset(secondary, "system.secondary").a
    except VidgenError:
        raise VidgenError(f"system: give separation for '{secondary}' (no preset orbit to take it from)") from None


def place_near(bodies: list[OrbitBody], info: RestrictedInfo | None) -> tuple[list[OrbitBody], dict[str, str]]:
    """Bodies written ``near: L4`` (with ``shift`` and ``drift`` in the rotating frame) turned into
    a position and velocity relative to the primary: at rest in the rotating frame, i.e. moving
    with Ω × r inertially."""
    out, near = [], {}
    for k, spec in enumerate(bodies, start=1):
        if spec.near is None:
            if spec.shift is not None or spec.drift is not None:
                raise VidgenError(f"bodies[{k}] '{spec.display_name()}': shift and drift move a body from its Lagrange point; give near: L4 (or L1…L5)")
            out.append(spec)
            continue
        where = f"bodies[{k}] '{spec.display_name()}'"
        if info is None:
            raise VidgenError(f"{where}: near: {spec.near} needs a three-body system (system: sun_jupiter, earth_moon, sun_earth or your own pair)")
        others = [n for n in ("a", "e", "periapsis", "apoapsis", "altitude", "i", "raan", "argp", "nu", "mean_anomaly", "r", "v", "preset", "alongside", "around")
                  if getattr(spec, n) is not None]
        if others:
            raise VidgenError(f"{where}: near: {spec.near} gives its start; leave out {', '.join(others)}")
        if spec.burns:
            raise VidgenError(f"{where}: burns are flown on Kepler arcs; a body near a Lagrange point moves in the three-body field")
        pair = info.pair
        d = pair.separation
        point = orbits.lagrange_points(pair.mu)[spec.near] * d
        shift = _pair(spec.shift, "length", d, f"{where}.shift")
        drift = _pair(spec.drift, "speed", pair.omega * d, f"{where}.drift")
        rho = np.array([point[0] + shift[0], point[1] + shift[1], 0.0])   # from the barycentre, the secondary on +x
        v = np.array([-pair.omega * rho[1] + drift[0], pair.omega * rho[0] + drift[1], 0.0])
        r = rho + np.array([pair.mu * d, 0.0, 0.0])   # from the primary
        if np.linalg.norm(r[:2]) <= pair.primary.radius:
            raise VidgenError(f"{where}: it starts inside {pair.primary.name}")
        moved = spec.model_copy(update={"r": [f"{float(x)!r} m" for x in r[:2]], "v": [f"{float(x)!r} m/s" for x in v[:2]], "near": None, "shift": None, "drift": None,
                                        "color": spec.color or "accent"})   # apart from the primaries' colours
        near[spec.display_name()] = spec.near
        out.append(moved)
    return out, near


def _pair(values: list[Any] | None, kind: str, unit: float, where: str) -> tuple[float, float]:
    """Two components: numbers are shares of ``unit`` (the separation, or Ω × separation),
    text a value with its unit."""
    if values is None:
        return 0.0, 0.0
    if len(values) != 2:
        raise VidgenError(f"{where}: give two components [x, y] (numbers: shares of the separation; or '0.01 AU')")
    out = []
    for n, c in enumerate(values):
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            out.append(float(c) * unit)
        else:
            out.append(orbits.value_si(c, kind, f"{where}[{n}]"))
    return out[0], out[1]


def resonance_info(spec: OrbitResonance, system: Any, span: float) -> ResonanceInfo:
    """Periods and conjunctions of a resonance's bodies (checked: known, around one body, closed
    orbits, inner first)."""
    names = system.names
    for n in spec.bodies:
        if n not in names:
            raise VidgenError(f"resonance: no body '{n}' (bodies: {', '.join(names)})" + did_you_mean(n, names))
    if len(set(spec.bodies)) != len(spec.bodies):
        raise VidgenError("resonance: name each body once")
    orbiters = [system.orbiter(n) for n in spec.bodies]
    parents = {o.parent for o in orbiters}
    if len(parents) != 1:
        raise VidgenError("resonance: the bodies must go around the same body")
    periods = []
    for o in orbiters:
        if o.elements.period is None:
            raise VidgenError(f"resonance: '{o.name}' is on an open orbit (no period)")
        periods.append(o.elements.period)
    if any(b <= a for a, b in zip(periods, periods[1:])):
        raise VidgenError(f"resonance: list the bodies from the inside out (periods {', '.join(f'{p / 86400:.4g} d' for p in periods)})")
    pairs = []
    for (a, ta), (b, tb) in zip(zip(orbiters, periods), list(zip(orbiters, periods))[1:]):
        synodic = 1 / (1 / ta - 1 / tb)

        def sep(t: np.ndarray, a: Any = a, b: Any = b) -> np.ndarray:
            pa, pb = a.positions(t), b.positions(t)
            return np.arctan2(pa[:, 1], pa[:, 0]) - np.arctan2(pb[:, 1], pb[:, 0])

        times = orbits.conjunctions(sep, span, synodic / 24)
        pairs.append(tuple((float(t), float(math.atan2(*a.positions(float(t))[[1, 0]]))) for t in times))
    return ResonanceInfo(tuple(spec.bodies), next(iter(parents)), tuple(periods), tuple(pairs), spec.keep, spec.conjunctions)


__all__ = ["CHOREOGRAPHIES", "EIGHT_NAMES", "LagrangeName", "ManyInfo", "ManySpec", "OrbitResonance", "OrbitSystem", "OrbitTides", "ResonanceInfo",
           "RestrictedInfo", "curvature", "expand_system", "finish_many", "jacobi_series", "place_near", "prepare_many", "resonance_info"]
