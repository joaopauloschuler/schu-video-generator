"""Orbit data for ``web`` scenes (Step 367, DESIGN.md §122.3): ``orbit_data:`` declares bodies in
the ``orbit`` scene's words (``central``, ``bodies``, ``span`` / ``orbits`` or ``speedup``,
``date``, ``dynamics``, ``transfer``, ``flyby``, ``system``), the same model resolves them
(:func:`~vidgen.scenes.orbit_parts.resolve_model`), and the page is given, for every frame of the
scene on vidgen's clock, each body's position and velocity, its rotation (a quaternion and the
prime meridian's angle) for the bodies with rotation data (:mod:`vidgen.orbits.rotation`), its
path and orbit as polylines and a spacecraft's burns — as ``ctx.orbits`` (``data/web/orbits.js``).

Units SI (m, m/s, s, rad); frame: the mean ecliptic and equinox of J2000 (x the equinox, z the
ecliptic's north pole), origin the central body (a flyby: the planet's own frame, x along its
motion). :func:`vidgen.web.orbits.scene_orbit_data` keeps it in
``build/orbits/orbit-data-<key>.json``. Imports only ``vidgen.api`` (a built-in scene module).
"""

import base64
import datetime as dt
import math
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .orbit_parts import OrbitBody, OrbitCentral, OrbitFlyby, OrbitTransfer, Value, resolve_model
from .orbit_sky import SkySpec
from .orbit_systems import ManySpec, OrbitSystem

rot = orbits.rotation

#: Version of the data's layout and of how it is made (bumped when either changes).
ORBIT_DATA_VERSION = 2
#: Points of a body's path over the scene and of its orbit's conic.
DEFAULT_PATH_SAMPLES, CONIC_SAMPLES = 256, 360
#: The frames of the data and their text.
ECLIPTIC_FRAME = "ecliptic_j2000"
FLYBY_FRAME = "flyby"
FRAME_TEXT = {
    ECLIPTIC_FRAME: "mean ecliptic and equinox of J2000: x towards the equinox, z towards the ecliptic's north pole; origin the central body",
    FLYBY_FRAME: "the flyby planet's frame (patched conics): origin the planet, x along its motion around the Sun, the pass in the x-y plane",
}
UNITS = {"length": "m", "speed": "m/s", "time": "s", "angle": "rad", "gm": "m^3/s^2"}
Plane = Literal["equator", "ecliptic"]


class OrbitData(SceneParams):
    """``orbit_data:`` of a ``web`` scene: bodies on their orbits, in the ``orbit`` scene's words."""

    central: str | OrbitCentral = "sun"
    """The central body (the origin): a preset (sun, earth, mars, jupiter, moon...) or {name, gm or mass, radius}."""
    bodies: list[OrbitBody] = Field(default_factory=list)
    """The orbiting bodies, as in the orbit scene: [{preset: earth}, {preset: moon, around: Earth}, {name: Probe, a: '1.5 AU', e: 0.4}, {name: Ship, alongside: Earth}]; its drawing keys (trail, geometry, sectors...) are accepted and not used."""
    span: Value | None = None
    """Simulated time the scene shows, from its first frame to its end ('1 yr', '92 min'); or orbits, or speedup."""
    orbits: float | None = Field(default=None, gt=0)
    """Simulated time in periods of the first body (default 1 when neither span nor speedup is given)."""
    speedup: float | None = Field(default=None, gt=0)
    """Simulated seconds per second of the scene (86400: a day a second), instead of span."""
    date: str | dt.date | None = None
    """The date of the first frame ('2026-11-17', 1800-2050): the planet presets are placed by JPL's approximate elements on that day and the bodies turn as they do on it; default J2000.0 (2000-01-01 12:00 TT), the presets' own epoch."""
    dynamics: Literal["kepler", "nbody"] = "kepler"
    """kepler: each body on its two-body orbit around its parent; nbody: every body with mass pulls on every other."""
    method: str = "leapfrog"
    """n-body method: leapfrog or rk45."""
    step: Value | None = None
    """n-body leapfrog step ('1 h')."""
    transfer: OrbitTransfer | None = None
    """A transfer flown by one body (as in the orbit scene): {kind: hohmann, ship: Ship, to: Mars}; the ship's path and burns are in the data."""
    flyby: OrbitFlyby | None = None
    """A gravity assist past the central body (as in the orbit scene), in the planet's frame; the probe is a body of the data."""
    system: OrbitSystem | None = None
    """A restricted three-body pair or the figure-eight (as in the orbit scene)."""
    planes: dict[str, Plane] = Field(default_factory=dict)
    """What a body's i, raan and argp are measured from, by name: equator (the equator of the body it orbits) or ecliptic. Default: the preset's (iss, geo and the Galilean moons the equator; the planets, the Moon and Halley the ecliptic); a body of your own around a planet or moon the equator, around the Sun the ecliptic."""
    path_samples: int = Field(default=DEFAULT_PATH_SAMPLES, ge=2, le=4096)
    """Points of each body's path over the scene (the polyline ctx.orbits.path gives)."""

    @model_validator(mode="after")
    def _consistent(self) -> "OrbitData":
        given = [k for k in ("span", "orbits", "speedup") if getattr(self, k) is not None]
        if len(given) > 1:
            raise ValueError(f"give one of span, orbits or speedup (got {' and '.join(given)})")
        if self.method != "leapfrog" and self.dynamics != "nbody" and self.system is None:
            raise ValueError("method is the n-body integrator; it needs dynamics: nbody")
        try:
            model = self.model(None)
            self.body_planes(model)
        except VidgenError as error:
            raise ValueError(str(error)) from None
        return self

    def model(self, span_seconds: float | None) -> Any:
        """The resolved ``orbit`` model (:class:`~vidgen.scenes.orbit_parts.OrbitModel`); with
        ``span_seconds`` (the speed-up's span) that span, else the settings' own."""
        fields = self.model_fields_set
        many = ManySpec(self.system, "central" in fields, "dynamics" in fields, method_given="method" in fields) if self.system is not None else None
        span = f"{span_seconds!r} s" if span_seconds is not None else self.span
        orbit_count = None if span_seconds is not None else self.orbits
        return resolve_model(self.central, self.bodies, span=span, orbit_count=orbit_count, dynamics=self.dynamics, method=self.method,
                             step=self.step, follow=None, transfer=self.transfer, flyby=self.flyby, many=many,
                             sky=SkySpec(self.date) if self.date is not None else None)

    def body_planes(self, model: Any) -> dict[str, str]:
        """Each orbiter's plane (``equator`` or ``ecliptic``; ``as_written`` for an n-body run or a
        flyby, whose bodies stay in one frame), checked: names known, a transfer's ship and target
        in one plane, an equator only of a body with rotation data."""
        system = model.system
        names = system.names
        unknown = [n for n in self.planes if n not in names]
        if unknown:
            raise VidgenError(f"orbit_data.planes: no body '{unknown[0]}' (bodies: {', '.join(names)})" + did_you_mean(unknown[0], names))
        if model.run is not None or self.flyby is not None:
            asked = [n for n, p in self.planes.items() if p == "equator"]
            if asked:
                what = "an n-body run" if model.run is not None else "a flyby"
                raise VidgenError(f"orbit_data.planes: {asked[0]}: {what} keeps every body in the frame its elements are written in; "
                                  "leave out planes (or use dynamics: kepler)")
            return {n: "as_written" for n in names}
        out: dict[str, str] = {}
        keys = _preset_keys(model)
        for spec, o in zip(model.specs, system.orbiters):
            parent_key = keys[o.parent]
            if o.name in self.planes:
                plane = self.planes[o.name]
            elif spec.alongside is not None:
                plane = out[spec.alongside]
            elif spec.preset:
                plane = orbits.orbit_preset(spec.preset).plane
            else:
                plane = "equator" if parent_key not in (None, "sun") and parent_key in rot.ROTATIONS else "ecliptic"
            if plane == "equator" and parent_key not in rot.ROTATIONS:
                parent = system.parent_body(o).name
                raise VidgenError(f"orbit_data.planes: {o.name} goes around {parent}, which has no rotation data (no equator known); "
                                  "give planes: {" + o.name + ": ecliptic}")
            out[o.name] = plane
        info = model.transfer
        if info is not None and info.target is not None and out[info.ship] != out[info.target]:
            raise VidgenError(f"orbit_data.transfer: {info.ship} is measured from the {out[info.ship]} and {info.target} from the "
                              f"{out[info.target]}: a transfer is between orbits in one plane; give both the same planes:")
        return out


def frame_times(model_span: float, frames: int, scene_frames: int) -> np.ndarray:
    """Simulated time (s) of each frame: 0 at frame 0, ``model_span`` at the scene's end (frame
    ``scene_frames``: one constant speed-up), held there on the frames after it."""
    n = np.minimum(np.arange(frames, dtype=float), float(scene_frames))
    return model_span * n / scene_frames


def _b64(array: Any) -> str:
    """Little-endian float64 bytes, base64."""
    return base64.b64encode(np.ascontiguousarray(array, dtype="<f8").tobytes()).decode("ascii")


def _preset_keys(model: Any) -> dict[str | None, str | None]:
    """The preset key of each orbiter by name, and of the central body under ``None`` (``None`` for
    a body of the author's own)."""
    centre = model.system.central
    keys: dict[str | None, str | None] = {None: next((k for k, b in orbits.BODIES.items() if b.name == centre.name and b.gm == centre.gm), None)}
    for spec, o in zip(model.specs or [], model.system.orbiters):
        keys[o.name] = orbits.orbit_preset(spec.preset).key if spec.preset else None
    return keys


def make_orbit_data(settings: OrbitData, fps: int, frames: int, scene_frames: int) -> dict[str, Any]:
    """The data for ``frames`` frames at ``fps`` of a scene whose own frames are ``scene_frames``
    (the rest hold the last moment). See the module docstring and DESIGN.md §122.3."""
    if scene_frames < 1 or frames < 1:
        raise VidgenError("orbit_data: the scene has no frames")
    seconds = scene_frames / fps
    model = settings.model(settings.speedup * seconds if settings.speedup is not None else None)
    span = float(model.span)
    times = frame_times(span, frames, scene_frames)
    planes = settings.body_planes(model)
    system = model.system
    jd0 = float(model.sky.jd0) if model.sky is not None and model.sky.jd0 is not None else rot.J2000_JD
    jds = jd0 + times / rot.DAY_S
    path_t = np.linspace(0.0, span, settings.path_samples)
    keys = _preset_keys(model)
    turns = {o.name: rot.equator_frame(rot.ROTATIONS[keys[o.parent]], jd0) if planes[o.name] == "equator" else None for o in system.orbiters}

    def relative(name: str, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Position and velocity relative to the parent (data frame)."""
        o = system.orbiter(name)
        if model.run is not None:
            parent = o.parent
            r, v = model.run.position(name, t), model.run.velocity(name, t)
            if parent is not None:
                r, v = r - model.run.position(parent, t), v - model.run.velocity(parent, t)
            return r, v
        r, v = o.states(t)
        turn = turns[name]
        return (r, v) if turn is None else (r @ turn.T, v @ turn.T)

    states = {n: relative(n, times) for n in system.names}

    def absolute(name: str) -> tuple[np.ndarray, np.ndarray]:
        if model.run is not None:
            return model.run.position(name, times), model.run.velocity(name, times)
        r, v = np.zeros((frames, 3)), np.zeros((frames, 3))
        for o in system.chain(name):
            r, v = r + states[o.name][0], v + states[o.name][1]
        return r, v

    central = system.central
    central_key = keys[None]
    # a flyby's frame turns with the planet's motion on the date: its pole (and a moon's) turned into it
    axes = orbits.ephemeris.flyby_axes(central_key, jd0) if settings.flyby is not None and central_key in orbits.TABLE1 else None
    bodies = [_body_entry(central.name, central_key, None, central, None, "central", np.zeros((frames, 3)), np.zeros((frames, 3)), jds, None,
                          np.array([0.0, 0.0, 1.0]) if central_key == "sun" else None, axes)]
    for spec, o in zip(model.specs, system.orbiters):
        key = keys[o.name]
        r, v = absolute(o.name)
        rel = states[o.name][0]
        path = relative(o.name, path_t)[0]
        turn = turns[o.name]
        el0 = o.elements_at(0.0)
        conic = el0.conic(CONIC_SAMPLES)
        if turn is not None:
            conic = conic @ turn.T
        r0, v0 = (x[0] for x in relative(o.name, np.zeros(1)))
        normal = np.cross(r0, v0)
        entry = _body_entry(o.name, key, o.parent or central.name, o.body, spec, planes[o.name], r, v, jds, rel, normal / np.linalg.norm(normal), axes)
        entry.update(path=_b64(path), conic=_b64(conic), path_points=len(path), conic_points=len(conic), orbit=_orbit_entry(el0.mu, r0, v0),
                     burns=_burns(o, turn, times))
        bodies.append(entry)
    return {
        "version": ORBIT_DATA_VERSION, "frame": FLYBY_FRAME if settings.flyby is not None else ECLIPTIC_FRAME,
        "frame_text": FRAME_TEXT[FLYBY_FRAME if settings.flyby is not None else ECLIPTIC_FRAME], "units": UNITS,
        "fps": fps, "frames": frames, "scene_frames": scene_frames, "seconds": seconds, "span": span, "speedup": span / seconds,
        "jd0": jd0, "date": orbits.date_text(jd0, time=True), "dynamics": "nbody" if model.run is not None else "kepler",
        "approximations": _approximations(settings, model, planes, jd0), "time": _b64(times), "bodies": bodies,
    }


def _orbit_entry(mu: float, r: np.ndarray, v: np.ndarray) -> dict[str, Any]:
    """The orbit at the start in the data's frame: a (m; ``None`` for a parabola), e, i, raan,
    argp, nu (rad; i to the frame's x-y plane), the period (s; ``None`` open), the kind and μ."""
    el = orbits.Elements.from_state(mu, r, v)
    return {"a": None if math.isinf(el.a) else el.a, "e": el.e, "i": el.i, "raan": el.raan, "argp": el.argp, "nu": el.nu,
            "period": el.period, "kind": el.kind, "mu": mu}


def _burns(o: Any, turn: np.ndarray | None, times: np.ndarray) -> list[dict[str, Any]]:
    """A body's burns: number, simulated time, the first frame at or after it (``None`` after the
    last frame), Δv (data frame, m/s), its (prograde, radial, normal) parts, size, direction, label."""
    if o.trajectory is None:
        return []
    out = []
    for b in o.trajectory.burns:
        dv = b.dv if turn is None else turn @ b.dv
        k = int(np.searchsorted(times, b.time - 1e-9 * max(1.0, abs(b.time))))
        out.append({"number": b.number, "time": b.time, "frame": k if k < len(times) and times[k] >= b.time - 1e-6 * max(1.0, abs(b.time)) else None,
                    "dv": [float(x) for x in dv], "components": [float(x) for x in b.components], "magnitude": b.magnitude,
                    "direction": b.direction, "label": b.label})
    return out


def _rotation_entry(key: str | None, jds: np.ndarray, parent_rel: np.ndarray | None, orbit_normal: np.ndarray | None,
                    axes: np.ndarray | None = None) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """A body's rotation facts and its per-frame quaternion and prime-meridian angle (``None`` without rotation data);
    ``axes``: the data frame's axes in the ecliptic frame when it is another (a flyby's, :func:`vidgen.orbits.ephemeris.flyby_axes`).
    A tidally locked moon (``synchronous``) in orbit around a body of the data faces it: its prime meridian
    points at its parent (projected on its equator) on the model's orbit, instead of the IAU formula's
    meridian (the model does not put the moons where they are on the date)."""
    if key not in rot.ROTATIONS:
        return None, {}
    m = rot.ROTATIONS[key]
    turn = np.eye(3) if axes is None else axes
    poles = m.pole(jds) @ turn.T
    alpha, delta = m.pole_radec(jds[0])
    locked = m.synchronous and parent_rel is not None
    if locked:
        to_parent = -parent_rel / np.linalg.norm(parent_rel, axis=-1, keepdims=True)
        x = to_parent - np.sum(to_parent * poles, axis=-1, keepdims=True) * poles
        x /= np.linalg.norm(x, axis=-1, keepdims=True)
        frames = np.stack([x, np.cross(poles, x), poles], axis=-1)
        alpha_all, _ = m.pole_radec(jds)
        node = rot.ecliptic_from_icrf(np.stack([np.cos(np.radians(alpha_all) + math.pi / 2), np.sin(np.radians(alpha_all) + math.pi / 2),
                                                np.zeros_like(alpha_all)], axis=-1)) @ turn.T
        spin = np.mod(np.arctan2(np.sum(x * np.cross(poles, node), axis=-1), np.sum(x * node, axis=-1)), 2 * math.pi)
    else:
        frames = np.einsum("ij,njk->nik", turn, m.frame(jds))
        spin = np.radians(m.prime_meridian(jds))
    facts = {"period": m.period, "retrograde": m.retrograde, "synchronous": m.synchronous, "faces_parent": locked,
             "pole": [float(c) for c in poles[0]], "pole_radec": [alpha, delta], "spin_axis": [float(c) for c in (-poles[0] if m.retrograde else poles[0])],
             "obliquity": rot.obliquity(m, orbit_normal, float(jds[0])) if orbit_normal is not None else None,
             "obliquity_published": m.obliquity_published, "radii": list(m.radii), "mean_radius": m.mean_radius,
             "source": m.source, "note": m.note, "check": m.check}
    return facts, {"quaternion": _b64(rot.quaternions(frames)), "spin": _b64(spin)}


def _body_entry(name: str, key: str | None, parent: str | None, body: Any, spec: Any, plane: str, r: np.ndarray, v: np.ndarray, jds: np.ndarray,
                rel: np.ndarray | None, normal: np.ndarray | None, axes: np.ndarray | None = None) -> dict[str, Any]:
    """A body's facts and per-frame series (``rel``: its positions relative to its parent; ``normal``:
    its orbit's normal at the start, or the ecliptic's for the Sun at the centre, for the tilt; ``axes``:
    a flyby frame's axes, :func:`vidgen.orbits.ephemeris.flyby_axes`)."""
    rotation, series = _rotation_entry(key, jds, rel, normal, axes)
    color = (str(spec.color) if spec is not None and spec.color else body.color) or None
    label = str(spec.label) if spec is not None and spec.label else name
    return {"name": name, "key": key, "parent": parent, "label": label, "color": color, "gm": body.gm, "radius": body.radius, "plane": plane,
            "rotation": rotation, "position": _b64(r), "velocity": _b64(v), **series}


def _approximations(settings: OrbitData, model: Any, planes: dict[str, str], jd0: float) -> list[str]:
    """What the data simplifies, in words a caption can use."""
    out = []
    if model.run is not None:
        out.append(f"n-body motion ({model.run.method}), every body with mass pulling on every other")
    else:
        out.append("two-body Kepler orbits: each body around its parent, the others' pull ignored")
    keys = {orbits.orbit_preset(s.preset).key for s in model.specs if s.preset}
    planets = keys & set(orbits.TABLE1)
    if planets:
        if settings.date is not None:
            out.append(f"planets placed by JPL's approximate elements (Table 1) on {orbits.date_text(jd0)}, then moving on two-body orbits")
        else:
            out.append("planets at their J2000 mean elements (JPL Table 1): where they were on 2000-01-01 12:00 TT")
    if keys & set(orbits.GALILEAN_PERIODS):
        out.append("Galilean moons on circles in Jupiter's equator, phases set for the Laplace angle, not their positions on the date")
    if model.transfer is not None or any(o.trajectory is not None for o in model.system.orbiters):
        out.append("impulsive burns" + (" between circular coplanar orbits" if model.transfer is not None else ""))
    if settings.flyby is not None:
        out.append("patched conics: the planet's gravity alone near it, its velocity constant during the pass")
    if any(k in rot.ROTATIONS for k in keys | {_preset_keys(model)[None]}):
        out.append("rotation from the IAU WGCCRE models; tidally locked moons face their planet")
    return out


__all__ = ["DEFAULT_PATH_SAMPLES", "ECLIPTIC_FRAME", "FLYBY_FRAME", "ORBIT_DATA_VERSION", "OrbitData", "frame_times", "make_orbit_data"]
