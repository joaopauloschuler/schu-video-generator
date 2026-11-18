"""Flight data for ``web`` scenes (Step 385, DESIGN.md §123.7): ``flight_data:`` declares flights in
words (:mod:`vidgen.flight.spec`: a start, legs), the ground they must stay over, the world and the
scene's anchor; :mod:`vidgen.flight` computes, for every frame of the scene on vidgen's clock, each
flight's float64 position, velocity, attitude quaternion and the numbers a picture reads (speed,
Mach number, heights over sea level and over the ground, load factor, bank, pitch, heading, angle
of attack, a heating indicator) — handed to the page as ``ctx.flight`` (``data/web/flight.js``),
carried by the orbit bridge's payload (Step 367: the same plumbing, cache pattern and keys).

Frame: the scene's local frame (:mod:`vidgen.flight.frames`: metres, x east, y up, z south, the
origin on the world's sphere under ``at``), the axes ``vidgen/space-air`` and its siblings draw in.
:func:`vidgen.web.flights.scene_flight_data` keeps it in ``build/flights/flight-data-<key>.json``.
Imports only ``vidgen.api`` (a built-in scene module).
"""

import base64
from typing import Any, Callable

import numpy as np

from vidgen.api import *

from .space_params import scene_time, uses_bars

quaternions = orbits.rotation.quaternions
#: Version of the data's layout and of how it is made.
FLIGHT_DATA_VERSION = 1
DEFAULT_PATH_SAMPLES = 256
LOCAL_FRAME = "local"
FLAT_FRAME = "flat"
FRAME_TEXT = {
    LOCAL_FRAME: "the scene's local frame: metres, x east, y up, z south, the origin on the world's sphere under the anchor (the world's centre at (0, -R, 0))",
    FLAT_FRAME: "a flat world: metres, x east, y up (the height), z south",
}
UNITS = {"length": "m", "speed": "m/s", "time": "s", "angle": "rad", "density": "kg/m^3"}
#: The per-frame series of a flight and their widths.
SERIES = {"position": 3, "velocity": 3, "quaternion": 4, "speed": 1, "mach": 1, "height": 1, "above_ground": 1, "load": 1,
          "bank": 1, "pitch": 1, "heading": 1, "aoa": 1, "heating": 1, "climb": 1}


class SeaOptions(SceneParams):
    """The sea as the ground: its mean level, height 0."""

    waves: float = Field(default=0.0, ge=0)
    """Metres the crests stand over the mean level (added to the margin a path keeps)."""


class LevelOptions(SceneParams):
    """A level ground: the world's sphere, or a flat world's plane."""

    elevation: float = 0.0
    """Metres over the world's sphere (sea level)."""


class FlightGround(SceneParams):
    """What a flight must stay over: ``{land: alpine}`` (vidgen/space-land's ground: a preset or its
    options, the heights fetched once from a page), ``sea`` (or ``{sea: {waves: 2}}``), ``sphere``
    (a level ground on the world's sphere, ``{sphere: {elevation: 300}}``) or ``flat`` (a flat world: no
    sphere, ``{flat: {elevation: 0}}``)."""

    land: str | dict[str, Any] | None = None
    """vidgen/space-land's ground: a preset name (alpine, mars, canyon, dunes, snow, volcanic, airless) or its options {preset, world, at, seed, mountains, ...} and air."""
    sea: bool | SeaOptions | None = None
    """The sea's mean level: true or {waves: metres}."""
    sphere: bool | LevelOptions | None = None
    """A level ground on the world's sphere: true or {elevation: metres}."""
    flat: bool | LevelOptions | None = None
    """A flat world (no sphere: no latitudes, no re-entry): true or {elevation: metres}."""

    @model_validator(mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        return {value: True} if isinstance(value, str) and value in ("sea", "sphere", "flat") else value

    @model_validator(mode="after")
    def _one(self) -> "FlightGround":
        given = [k for k in ("land", "sea", "sphere", "flat") if getattr(self, k) not in (None, False)]
        if len(given) != 1:
            raise ValueError("ground: give one of land, sea, sphere or flat" + (f" (got {' and '.join(given)})" if given else ""))
        if self.land is not None:
            web_land_settings(self.land_options)
        return self

    @property
    def kind(self) -> str:
        return next(k for k in ("land", "sea", "sphere", "flat") if getattr(self, k) not in (None, False))

    @property
    def land_options(self) -> dict[str, Any]:
        return {"preset": self.land} if isinstance(self.land, str) else dict(self.land or {})


class FlightData(SceneParams):
    """``flight_data:`` of a ``web`` scene: flights over a ground, for the page as ``ctx.flight``."""

    flights: list[flight.Flight] = Field(min_length=1)
    """The flights: [{name: Plane, start: {x: -20000, z: 0, above_ground: 800, heading: 90, speed: 120}, legs: [{straight: 20}, {turn: {to: 180, bank: 30}}]}]."""
    ground: FlightGround = Field(default_factory=lambda: FlightGround(sphere=True))
    """What the flights stay over: {land: alpine}, sea, sphere (default) or flat."""
    world: str | None = None
    """The world (its radius, gravity, turning and air): earth, mars, thin, thick, moon...; default the land's air, else earth."""
    at: list[float] | None = None
    """The scene's anchor [latitude, longitude] (degrees): where its origin is on the world; default the land's place, else [0, 0]."""
    start: float | str = 0.0
    """The time of the scene the flights' time 0 is (seconds or 'bar 9'); a start from orbit takes over at its own at."""
    speedup: float | None = Field(default=None, gt=0)
    """Flight seconds per second of the scene (default 1: true timing; with a start from orbit, the orbit data's)."""
    margin: float = Field(default=20.0, ge=0)
    """Metres every path keeps over the ground (besides a leg's own clearance; a landing excepted)."""
    path_samples: int = Field(default=DEFAULT_PATH_SAMPLES, ge=2, le=4096)
    """Points of each flight's path polyline (ctx.flight.path)."""

    @model_validator(mode="after")
    def _consistent(self) -> "FlightData":
        names = [f.name for f in self.flights]
        twice = sorted({n for n in names if names.count(n) > 1})
        if twice:
            raise ValueError(f"flight_data: two flights are called {twice[0]} (each needs its own name)")
        for where, value in self.times():
            scene_time(value, where)
        if self.ground.kind == "flat":
            if self.at is not None:
                raise ValueError("flight_data: a flat world has no anchor on a globe; leave out at")
            if any(f.start.orbit is not None or any(leg.reentry is not None for leg in f.legs) for f in self.flights):
                raise ValueError("flight_data: a start from orbit and a re-entry need the world's sphere, not a flat world")
        try:
            self.world_of()
        except VidgenError as error:
            raise ValueError(str(error)) from None
        return self

    def times(self) -> list[tuple[str, Any]]:
        """Every time of the scene written in the data (``where``, value)."""
        out: list[tuple[str, Any]] = [("flight_data.start", self.start)]
        for f in self.flights:
            if f.start.at is not None:
                out.append((f"flight {f.name}: start.at", f.start.at))
            out += [(f"flight {f.name}: leg {i + 1}.until", leg.until) for i, leg in enumerate(f.legs) if leg.until is not None]
        return out

    @property
    def uses_bars(self) -> bool:
        return any(uses_bars(scene_time(v, w)) for w, v in self.times())

    @property
    def orbit_bodies(self) -> list[str]:
        """The orbit data's bodies the flights start from."""
        return [f.start.orbit for f in self.flights if f.start.orbit is not None]

    def land(self) -> dict[str, Any] | None:
        return web_land_settings(self.ground.land_options) if self.ground.kind == "land" else None

    def world_of(self) -> Any:
        land = self.land()
        name = self.world or (land["world"] if land else "earth")
        found = flight.world(name, "flight_data.world")
        if land and self.world is not None and land["world"] != found.name:
            raise VidgenError(f"flight_data.world: {self.world} is not the land's world ({land['world']}, its air's): leave out world or give ground.land.air")
        return found

    def anchor(self) -> list[float]:
        land = self.land()
        if land is not None:
            if self.at is not None and [float(v) for v in self.at] != land["at"]:
                raise VidgenError(f"flight_data.at {self.at} is not the land's place {land['at']}: the scene's frame is the land's (give at to ground.land)")
            return land["at"]
        if self.at is None:
            return [0.0, 0.0]
        if len(self.at) != 2:
            raise VidgenError(f"flight_data.at must be [latitude, longitude], got {self.at}")
        return [float(self.at[0]), float(self.at[1])]


def _b64(array: Any) -> str:
    return base64.b64encode(np.ascontiguousarray(array, dtype="<f8").tobytes()).decode("ascii")


def _f64(text: str, width: int) -> np.ndarray:
    a = np.frombuffer(base64.b64decode(text), dtype="<f8")
    return a.reshape(-1, width) if width > 1 else a


def scene_seconds(value: Any, music: dict[str, Any] | None) -> float:
    """A time of the scene (seconds or 'bar 9 beat 3') in seconds; bars from the score of ``music`` (ctx.music's)."""
    t = scene_time(value, "a time")
    if not uses_bars(t):
        return float(t)
    score = (music or {}).get("score")
    if not score:
        raise VidgenError("flight_data: a time in bars needs the score on the page: add music_data: true (and a score file as the video's music)")
    return (t["bar"] - 1) * score["bar"] + (t["beat"] - 1) * score["beat"] - music["t0"]


def _ground(settings: FlightData, world: Any) -> Any:
    g = settings.ground
    kind = g.kind
    if kind == "land":
        land = settings.land()
        definition = web_land_definition(land["options"], land["air"])
        if abs(float(definition["radius"]) - world.radius) > 1.0:
            raise VidgenError(f"flight_data: the land's sphere ({definition['radius']:.0f} m) is not the world's ({world.radius:.0f} m): give world: or ground.land.air the same world")
        return flight.LandGround("land", f"vidgen/space-land's ground ({land['options'].get('preset') or land['options'].get('world')})", definition=definition)
    level = g.sphere if kind == "sphere" else g.flat if kind == "flat" else None
    if kind == "sea":
        waves = g.sea.waves if isinstance(g.sea, SeaOptions) else 0.0
        return flight.SeaGround("sea", "the sea's mean level" + (f", crests {waves:g} m over it" if waves else ""), margin_extra=waves)
    elevation = level.elevation if isinstance(level, LevelOptions) else 0.0
    cls = flight.FlatGround if kind == "flat" else flight.SphereGround
    return cls(kind, f"level ground {elevation:g} m over {'the flat world' if kind == 'flat' else 'the sphere'}", elevation=elevation)


def _orbit_state(name: str, at: float, fps: int, orbits: dict[str, Any] | None, frame: Any, world: Any) -> tuple[np.ndarray, np.ndarray]:
    """The local position and velocity over the ground of the orbit data's body ``name`` at scene time ``at``."""
    if orbits is None or "bodies" not in orbits:
        raise VidgenError(f"flight_data: a start from orbit ({name}) needs the scene's orbit_data")
    if orbits["frame"] != "ecliptic_j2000":
        raise VidgenError("flight_data: a start from orbit needs orbit data in the ecliptic frame (not a flyby's)")
    bodies = {b["name"]: b for b in orbits["bodies"]}
    if name not in bodies:
        raise VidgenError(f"flight_data: start.orbit: no body '{name}' in the orbit data{did_you_mean(name, list(bodies))} (bodies: {', '.join(bodies)})")
    central = orbits["bodies"][0]
    if central.get("key") != world.rotation:
        raise VidgenError(f"flight_data: the orbit data goes round {central['name']}, the flights fly over {world.name}: give the orbit data central: {world.name}")
    k = min(max(round(at * fps), 0), int(orbits["frames"]) - 1)
    r, v = _f64(bodies[name]["position"], 3)[k], _f64(bodies[name]["velocity"], 3)[k]
    jd = float(orbits["jd0"]) + float(_f64(orbits["time"], 1)[k]) / 86400.0
    p, u = frame.from_ecliptic(world, r, v, jd)
    return np.asarray(p, dtype=float), np.asarray(u, dtype=float)


def make_flight_data(settings: FlightData, fps: int, frames: int, scene_frames: int, music: dict[str, Any] | None = None,
                     orbits: dict[str, Any] | None = None) -> dict[str, Any]:
    """The data for ``frames`` frames at ``fps`` of a scene whose own frames are ``scene_frames`` (the rest
    hold the last moment): see the module docstring and DESIGN.md §123.7. ``music``: the scene's
    ``ctx.music`` (bars); ``orbits``: its orbit data (a start from orbit)."""
    if scene_frames < 1 or frames < 1:
        raise VidgenError("flight_data: the scene has no frames")
    world = settings.world_of()
    flat = settings.ground.kind == "flat"
    frame = None if flat else flight.LocalFrame(*settings.anchor(), world.radius)
    ground = _ground(settings, world)
    speedup = settings.speedup or (float(orbits["speedup"]) if settings.orbit_bodies and orbits else 1.0)
    begin = scene_seconds(settings.start, music)
    scene_t = np.minimum(np.arange(frames, dtype=float), float(scene_frames)) / fps
    out_flights = []
    warnings: list[str] = []
    for spec in settings.flights:
        origin = scene_seconds(spec.start.at, music) if spec.start.at is not None else begin
        to_flight: Callable[[Any], float] = lambda value, origin=origin: (scene_seconds(value, music) - origin) * speedup
        context = flight.FlightContext(world, frame, ground, settings.margin, to_flight)
        state = _orbit_state(spec.start.orbit, origin, fps, orbits, frame, world) if spec.start.orbit is not None else None
        run = flight.FlightRun(spec, context, state)
        times = (scene_t - origin) * speedup
        s = run.sample(times)
        series = {"position": s["position"], "velocity": s["velocity"], "quaternion": quaternions(s["matrix"])}
        for key in SERIES:
            if key not in series:
                series[key] = s[key]
        warnings += run.warnings
        out_flights.append({
            "name": spec.name, "start": origin, "end": run.end, "warnings": run.warnings,
            "legs": [{"number": r.number, "kind": r.kind, "start": r.start, "end": r.end, "scene_start": origin + r.start / speedup,
                      "scene_end": origin + r.end / speedup, **_plain(r.notes)} for r in run.legs],
            "time": _b64(times), "path": _b64(run.path(settings.path_samples)), "path_points": settings.path_samples,
            **{k: _b64(v) for k, v in series.items()},
        })
    air = world.air
    return {
        "version": FLIGHT_DATA_VERSION, "frame": FLAT_FRAME if flat else LOCAL_FRAME, "frame_text": FRAME_TEXT[FLAT_FRAME if flat else LOCAL_FRAME],
        "units": UNITS, "fps": fps, "frames": frames, "scene_frames": scene_frames, "start": begin, "speedup": speedup,
        "world": {"name": world.name, "radius": world.radius, "gm": world.gm, "g0": world.g0, "rotation": world.rotation,
                  "spin_rate": world.spin_rate, "invented": world.invented, "sound_speed": world.sound_speed,
                  "air": None if air is None else {"scale_height": air.scale_height, "density": air.density, "gamma": air.gamma, "source": air.source}},
        "anchor": None if frame is None else {"lat": frame.lat, "lon": frame.lon, "axes": frame.axes.T.tolist()},
        "ground": {"kind": ground.kind, "text": ground.text, "margin": settings.margin + ground.margin_extra},
        "approximations": _approximations(settings, world), "warnings": warnings, "flights": out_flights,
    }


def _plain(notes: dict[str, Any]) -> dict[str, Any]:
    return {k: (float(v) if isinstance(v, (int, float, np.floating)) else [float(x) for x in v] if isinstance(v, (list, tuple)) else v) for k, v in notes.items()}


def _approximations(settings: FlightData, world: Any) -> list[str]:
    out = ["kinematic flight: the path is planned, not flown by a simulation of aerodynamics; the air at rest with the ground (no wind)",
           "coordinated turns (bank from speed and radius), the attitude from the path's acceleration; the angle of attack a look"]
    if world.air is not None:
        out.append(f"an isothermal exponential air (scale height {world.air.scale_height:.0f} m, the page's): speed of sound {world.sound_speed:.0f} m/s at every height")
    if world.invented:
        out.append(f"the invented world '{world.name}': its gravity from the Earth's mean density")
    if any(leg.reentry is not None for f in settings.flights for leg in f.legs):
        out.append("re-entry: the orbit's motion blended into an equilibrium glide, S-turns and the end a look (DESIGN.md §123.7)")
    if settings.ground.kind == "land":
        out.append("the ground's heights are vidgen/space-land's heightAt; far ground is drawn smoother than that")
    return out


__all__ = ["FLIGHT_DATA_VERSION", "FlightData", "FlightGround", "make_flight_data", "scene_seconds"]
