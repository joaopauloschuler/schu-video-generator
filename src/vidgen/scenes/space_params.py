"""The words of a ``space`` scene (DESIGN.md §122.12): sky, sun, bodies, orbits and scale, light,
craft, phenomena, camera moves, finishing, music, title and end card, and the hook to code.

Every key is checked here, at ``vidgen validate``, in Python: the vocabulary's own keys by these
models, and the options a section passes on to a module (``milky_way`` of the sky, ``glare`` of a
star, ``closest`` of a fly-by...) against that module's own option list, read from the shipped
JavaScript (``space_names``). Names of worlds, craft kinds, moves, phases, lenses, views, looks and
star kinds come from there too, with did-you-mean. Option keys may be written snake_case
(``milky_way``) or as the module writes them (``milkyWay``); values are checked by the module when the
page loads (a render-time error naming the option). Lengths are metres, or text with a unit
(``"58232 km"``, ``"1.2 AU"``). Positions are the orbit data's axes: x and y in the plane, z up.

Imports only ``vidgen.api`` (a built-in scene module).
"""

import math
import re
from typing import Any, Literal

from pydantic import ConfigDict

from vidgen.api import *

from .orbit_data import OrbitData

#: A place in the song: "bar 9", "bar 9 beat 3" (bars and beats from 1).
BAR = re.compile(r"^\s*bar\s+(\d+(?:\.\d+)?)(?:\s+beat\s+(\d+(?:\.\d+)?))?\s*$", re.IGNORECASE)
#: The reactions to the music and what each reads.
REACTIONS = {"pulse": "hits", "glint": "notes", "glow": "signal"}
#: The radius of a free-standing world nobody gave a size, and of a body the presets do not know (m).
DEFAULT_RADIUS = 6.0e6


def names() -> dict[str, Any]:
    """The space modules' names and options (:func:`vidgen.web.space_names.space_names`)."""
    return space_names()


def camel(key: str) -> str:
    """``milky_way`` -> ``milkyWay`` (a key already in camelCase stays)."""
    head, *rest = key.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def snake(key: str) -> str:
    """``milkyWay`` -> ``milky_way``."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", lambda m: "_" + m.group(1).lower(), key)


def module_options(given: dict[str, Any], known: list[str], where: str, leave: tuple[str, ...] = ()) -> dict[str, Any]:
    """``given`` with its keys as the module writes them (camelCase), each checked against ``known``
    (the module's option list) less ``leave`` (the keys this vocabulary sets itself); an unknown key
    is a ValueError with the closest one and the list (snake_case, as the YAML writes them)."""
    allowed = [k for k in known if k not in leave]
    out: dict[str, Any] = {}
    for key, value in given.items():
        name = camel(key)
        if name not in allowed:
            shown = [snake(k) for k in allowed]
            raise ValueError(f"{where}: unknown option '{key}'{did_you_mean(snake(name), shown)} (options: {', '.join(shown)})")
        problem = web_json_problem(value, f"{where}.{key}")
        if problem is not None:
            raise ValueError(problem)
        out[name] = value
    return out


def one_of(value: str, choices: list[str] | tuple[str, ...], what: str) -> str:
    """``value`` as the module spells it (``three_quarter`` -> ``three-quarter``), or a ValueError naming the choices."""
    for form in (value, value.replace("_", "-"), value.lower(), value.lower().replace("_", "-")):
        if form in choices:
            return form
    raise ValueError(f"unknown {what} '{value}'{did_you_mean(value.lower().replace('_', '-'), list(choices))} ({what}s: {', '.join(choices)})")


def length(value: Any, where: str) -> float:
    """A length in metres: a number (metres) or text with a unit ('58232 km', '1.2 AU'); a number YAML
    read as text ('2.6e9': YAML 1.1 wants '2.6e+9') is metres too."""
    if isinstance(value, bool):
        raise ValueError(f"{where}: {value!r} is not a length (metres, or text with a unit: '6371 km')")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError(f"{where}: {value} is not a finite length")
        return float(value)
    try:
        number = float(value) if isinstance(value, str) else None
    except ValueError:
        number = None
    if number is not None:
        return length(number, where)
    try:
        return orbits.value_si(value, "length", where)
    except VidgenError as error:
        raise ValueError(str(error)) from None


#: The options of camera moves that are lengths (metres, or text with a unit), at any depth.
LENGTH_KEYS = ("distance", "closest", "altitude")


def move_lengths(value: Any, where: str) -> Any:
    """``value`` (a move's options) with its lengths (:data:`LENGTH_KEYS`) written as text turned into metres."""
    if isinstance(value, dict):
        return {k: (length(v, f"{where}.{k}") if k in LENGTH_KEYS and isinstance(v, str) else move_lengths(v, f"{where}.{k}")) for k, v in value.items()}
    if isinstance(value, list):
        return [move_lengths(v, where) for v in value]
    return value


def point(value: Any, where: str) -> list[float]:
    """[x, y, z] lengths -> metres."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{where} must be [x, y, z] (lengths: metres, or text with a unit), got {value!r}")
    return [length(v, f"{where}[{i}]") for i, v in enumerate(value)]


def direction(value: Any, where: str) -> list[float]:
    """[x, y, z] numbers, not all 0."""
    if not (isinstance(value, (list, tuple)) and len(value) == 3 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        raise ValueError(f"{where} must be [x, y, z] (numbers: a direction in the orbit data's axes, z up), got {value!r}")
    if not any(value):
        raise ValueError(f"{where}: [0, 0, 0] is no direction")
    return [float(v) for v in value]


def scene_time(value: Any, where: str) -> float | dict[str, float]:
    """Seconds of the scene (a number) or a place in the song ('bar 9', 'bar 9 beat 3') as {bar, beat}."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < 0:
            raise ValueError(f"{where}: {value} is before the scene's start (times are seconds from its start)")
        return float(value)
    match = BAR.match(str(value)) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"{where}: {value!r} is not a time: seconds of the scene (2.5) or a place in the song ('bar 9', 'bar 9 beat 3')")
    bar, beat = float(match.group(1)), float(match.group(2) or 1)
    if bar < 1 or beat < 1:
        raise ValueError(f"{where}: bars and beats count from 1 ('bar 1' is the song's start)")
    return {"bar": bar, "beat": beat}


def uses_bars(value: Any) -> bool:
    return isinstance(value, dict) and "bar" in value


class Open(SceneParams):
    """A section that also takes the options of the module it drives (checked against that module's list)."""

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)
    header_synonyms = False

    def extras(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


# ----- sky, sun, scale, light ----------------------------------------------------------------------


class SkySpec(Open):
    """``sky:``: the sky of vidgen/space-sky. Also any of its options (``milky_way``, ``density``, ``brightness``, ``glare``, ``dust``, ``limit``...)."""

    seed: int | None = Field(default=None, ge=0)
    """Another sky for every seed (default: the scene's seed)."""
    look: str = "natural"
    """natural, rich or sparse (option sets of the sky; your own options override them)."""
    stars: Literal["seed", "real"] = "seed"
    """seed: an algorithmic sky (the default); real: the bright stars where they really are (the shipped list of well-known stars) and the real Milky Way's plane."""
    nebulae: int | list[dict[str, Any]] = 0
    """Seeded nebulae (a number, up to 12) or a list of {kind: emission | reflection | dark, at, size, ...}."""
    galaxies: int | list[dict[str, Any]] = 0
    """Painted galaxies in the background (a number, up to 12) or a list of {kind: spiral | elliptical | irregular, at, size, tilt, ...}."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"stars": "real"} if value == "real" else {"look": value}
        return value

    @model_validator(mode="after")
    def _check(self) -> "SkySpec":
        n = names()
        self.look = one_of(self.look, n["sky_looks"], "sky look")
        for key, kinds in (("nebulae", n["nebula_kinds"]), ("galaxies", n["galaxy_kinds"])):
            value = getattr(self, key)
            if isinstance(value, int) and not 0 <= value <= 12:
                raise ValueError(f"sky.{key}: {value}: from 0 to 12")
            for i, item in enumerate(value if isinstance(value, list) else []):
                if "kind" in item:
                    item["kind"] = one_of(str(item["kind"]), kinds, f"{key[:-1] if key == 'nebulae' else 'galaxy'} kind")
        module_options(self.extras(), n["sky_options"], "sky", leave=("seed", "look", "stars", "nebulae", "galaxies"))
        return self

    def options(self, seed: int) -> dict[str, Any]:
        n = names()
        return {"seed": self.seed if self.seed is not None else seed, "look": self.look, "stars": self.stars,
                **({"nebulae": self.nebulae} if self.nebulae else {}), **({"galaxies": self.galaxies} if self.galaxies else {}),
                **module_options(self.extras(), n["sky_options"], "sky")}


class SunSpec(Open):
    """``sun:``: the star of vidgen/space-light. Also any of its options (``glare``, ``spikes``, ``flare``, ``corona``, ``spots``...)."""

    kind: str = "sun"
    """red-dwarf, orange, sun, white or blue-giant (a star by temperature)."""
    temperature: float | None = Field(default=None, gt=1000, lt=60000)
    """The star's temperature in K, instead of its kind's."""
    seed: int | None = Field(default=None, ge=0)
    """Another surface for every seed."""
    direction: list[float] | None = None
    """Towards the sun, [x, y, z] in the orbit data's axes (z up), for a sun far away in the sky. Default: with orbits on a date around a planet, where the Sun really is that day; with the Sun in the orbit data, the Sun itself; else [1, 0.25, 0.35]."""
    at: list[Any] | None = None
    """A star you can fly to: where it stands ([x, y, z] lengths; a scene without orbits)."""
    radius: Any = None
    """Its radius with at (a length; default the Sun's, 695,700 km)."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        return {"kind": value} if isinstance(value, str) else value

    @model_validator(mode="after")
    def _check(self) -> "SunSpec":
        n = names()
        self.kind = one_of(self.kind, n["stars"], "star kind")
        if self.direction is not None:
            self.direction = direction(self.direction, "sun.direction")
        if self.direction is not None and self.at is not None:
            raise ValueError("sun: give direction (a sun far away in the sky) or at (a star in the scene), not both")
        if self.at is not None:
            point(self.at, "sun.at")
        if self.radius is not None:
            if self.at is None:
                raise ValueError("sun.radius goes with sun.at (a star standing in the scene)")
            length(self.radius, "sun.radius")
        module_options(self.extras(), n["star_options"], "sun", leave=("temperature", "seed", "direction", "name"))
        return self


class ScaleSpec(SceneParams):
    """``scale:`` of a scene with orbits (vidgen/space-scale): true (default), enlarged bodies, or log distances."""

    header_synonyms = False
    mode: Literal["true", "enlarged", "log"] = "true"
    """true: sizes and distances as they are; enlarged: bodies drawn larger by a stated factor (the note says so); log: distances compressed as the orbit scene's radial: log."""
    enlarge: float | dict[str, float] = 1.0
    """The factor of enlarged (a number, or {default: 50, Sun: 5} per body)."""
    note: bool = True
    """Say it on screen: the orbit scene's words ("sizes not to scale · bodies enlarged 50×; distances to scale", "distances compressed (log)") in a corner; false leaves it to the narration."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        if value is True:
            return {"mode": "true"}
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return {"mode": "enlarged", "enlarge": value}
        if isinstance(value, str):
            return {"mode": value}
        return value

    @model_validator(mode="after")
    def _check(self) -> "ScaleSpec":
        factors = [self.enlarge] if isinstance(self.enlarge, (int, float)) else list(self.enlarge.values())
        if any(not f > 0 for f in factors):
            raise ValueError("scale.enlarge: factors must be positive")
        enlarged = any(f != 1 for f in factors)
        if self.mode == "true" and enlarged:
            raise ValueError("scale: mode true draws every size as it is; to enlarge bodies write scale: {mode: enlarged, enlarge: 50} (its note says so)")
        if self.mode == "enlarged" and not enlarged:
            raise ValueError("scale: mode enlarged needs enlarge: a factor other than 1 (e.g. 50), stated in the scene's note")
        return self


class LightSpec(Open):
    """``light:``: the light of vidgen/space-light (one hard sun, planet-shine, eclipses, exposure). Also its other options (``ring_shine``, ``reference``, ``auto``...)."""

    exposure: str = "film"
    """film (a film's convention: day sides and stars in one frame; default), camera (honest, ev stops) or auto (honest, metered)."""
    ev: float = 0
    """Stops over a sunlit ground's exposure, with camera or auto."""
    falloff: float = Field(default=0, ge=0, le=2)
    """0: the sun as bright everywhere (stated artistic default); 2: the inverse-square law from reference."""
    eclipses: bool = False
    """Soft eclipse shadows of bodies on bodies."""
    shadows: bool = False
    """Shadow maps for the craft (their own parts and each other)."""
    shine: float = Field(default=1, ge=0)
    """Planet-shine on the night sides (0: black)."""
    ambient: float = Field(default=0, ge=0)
    """An ambient light (none by default)."""

    @model_validator(mode="after")
    def _check(self) -> "LightSpec":
        n = names()
        self.exposure = one_of(self.exposure, n["exposures"], "exposure")
        module_options(self.extras(), n["light_options"], "light",
                       leave=("scene", "camera", "renderer", "sun", "bodies", "sky", "at", "exposure", "ev", "falloff", "eclipses", "shadows", "shine", "ambient"))
        return self


# ----- bodies, craft, phenomena -----------------------------------------------------------------------


class BodySpec(Open):
    """A world of ``bodies:`` (vidgen/space-bodies). Also any option of its surface type (``clouds``, ``land``, ``bands``, ``storms``, ``craters``, ``palette``, ``oblateness``, ``quality``...)."""

    name: str
    """Its name: the body of the orbit data it shows (with orbits), and what the camera and the music name."""
    world: str | None = None
    """A ready-made world (earth, saturn, moon, tempest, ochre...); default the name's, when it is one."""
    type: str | None = None
    """Or a world of your own of this surface type: rocky, icy, desert, ocean, lava, gas, ice-giant."""
    seed: int | None = Field(default=None, ge=0)
    """Another surface for every seed."""
    rings: bool | dict[str, Any] | None = None
    """Rings: true, false, or {inner, outer (radii), style: broad | narrow, gaps, color, opacity, dust, seed}; a ready-made world keeps its own unless changed."""
    air: bool | str | dict[str, Any] | None = None
    """Air: false, a kind (earth, mars, venus, titan, giant, ice, thin, smoke) or {like, density, height...}; true scale heights unless height says otherwise."""
    spin: bool | str | float | None = None
    """true: the body's own turning from the orbit data (the default there), locked: no turning, or seconds of film for a turn (a stated artistic rate)."""
    tilt: float | None = None
    """Degrees the pole leans (a scene without orbits; with orbits the data's pole)."""
    at: list[Any] | None = None
    """Where it stands, [x, y, z] lengths (a scene without orbits; default [0, 0, 0])."""
    radius: Any = None
    """Its radius (a length; a scene without orbits; default the real body's for a ready-made lookalike, else 6,000 km)."""

    @model_validator(mode="after")
    def _check(self) -> "BodySpec":
        n = names()
        if self.world is not None and self.type is not None:
            raise ValueError(f"bodies {self.name}: give world (a ready-made one) or type (your own), not both")
        if self.world is not None:
            self.world = one_of(self.world, n["worlds"], "world")
        elif self.type is not None:
            self.type = one_of(self.type, n["world_types"], "surface type")
        elif self.name.lower() in n["worlds"]:
            self.world = self.name.lower()
        else:
            raise ValueError(f"bodies {self.name}: give world (one of {', '.join(n['worlds'])}) or type ({', '.join(n['world_types'])})"
                             + did_you_mean(self.name.lower(), n["worlds"]))
        if isinstance(self.air, str):
            self.air = one_of(self.air, n["airs"], "air")
        if isinstance(self.rings, dict):
            module_options(self.rings, n["ring_options"], f"bodies {self.name}.rings")
        if isinstance(self.spin, str) and self.spin not in ("true", "locked"):
            raise ValueError(f"bodies {self.name}.spin: true, locked or seconds for one turn, got {self.spin!r}")
        if self.at is not None:
            point(self.at, f"bodies {self.name}.at")
        if self.radius is not None and length(self.radius, f"bodies {self.name}.radius") <= 0:
            raise ValueError(f"bodies {self.name}.radius must be above 0")
        self.planet_options()
        return self

    @property
    def surface(self) -> str:
        """Its surface type (a ready-made world's own)."""
        if self.type is not None:
            return self.type
        return _preset_types()[self.world or ""]

    def planet_options(self) -> dict[str, Any]:
        """The options for ``planet()`` beyond the ready-made world (checked against its type's)."""
        out = module_options(self.extras(), names()["world_options"][self.surface], f"bodies {self.name}",
                             leave=("type", "seed", "rings", "air", "spin", "tilt", "name"))
        if self.type is not None:
            out = {"type": self.type, **out}
        for key in ("seed", "rings", "air", "tilt"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        if self.spin is not None:
            out["spin"] = "true" if self.spin is True else "locked" if self.spin is False else self.spin
        return out

    def radius_m(self) -> float:
        """Its radius (m) standing free: given, the real body's for a lookalike, else :data:`DEFAULT_RADIUS`."""
        if self.radius is not None:
            return length(self.radius, f"bodies {self.name}.radius")
        return real_radius(self.world or "") or DEFAULT_RADIUS


def real_radius(key: str) -> float | None:
    """The radius (m) of the real body a ready-made world is a lookalike of (the orbit presets'), or None."""
    body = orbits.BODIES.get(key)
    return float(body.radius) if body is not None and body.radius > 0 else ({"titan": 2_574_730.0}.get(key))


def _preset_types() -> dict[str, str]:
    """Each ready-made world's surface type (from the module's PRESETS)."""
    out = {}
    for key, text in web_space_entries("vidgen/space-bodies", "PRESETS").items():
        match = re.search(r'type:\s*"([^"]+)"', text)
        out[key] = match.group(1) if match else "rocky"
    return out


class CraftSpec(Open):
    """A craft of ``craft:`` (vidgen/space-craft). Also the kit's and its kind's options (``accent``, ``foil``, ``wear``, ``lit``, ``panels``, ``engines``, ``ring``...)."""

    name: str
    """Its name (what the camera follows and the music names)."""
    kind: str | list[str] = "probe"
    """probe, satellite, station, ship, lander or tug (invented designs); a list of kinds for a fleet."""
    seed: int | None = Field(default=None, ge=0)
    """Another design of the kind for every seed."""
    detail: str = "near"
    """near (everything) or far (a third of the triangles: for the distance and fleets)."""
    fly: str | None = None
    """The body of the orbit data it flies (its position, velocity and burns); default its own name when the data has it."""
    attitude: str | list[dict[str, Any]] | None = None
    """prograde, retrograde, radial, nadir, sun, target, thrust or inertial, or a list of {at, attitude, turn} (default prograde when it flies or moves)."""
    burn: bool | dict[str, Any] = True
    """How the data's burns are shown: true, false, or {seconds: 2, turn: 3, attitude: thrust} (thrust for seconds centred on each impulsive burn)."""
    target: str | None = None
    """A body or craft the dishes point at (and attitude target)."""
    throttle: float | None = Field(default=None, ge=0, le=1)
    """The engines, 0..1 (default: the burns of the orbit data; music: can drive it)."""
    rcs: float | None = Field(default=None, ge=0, le=1)
    """The thrusters, 0..1 (default: puffs at the turns)."""
    lights: float | None = Field(default=None, ge=0)
    """The lights' strength (1)."""
    marker: float = Field(default=0, ge=0)
    """A point of at least this many pixels when the craft is too small to see (a stated departure from true size)."""
    at: list[Any] | None = None
    """Where it stands, [x, y, z] lengths (a scene without orbits)."""
    velocity: list[float] | None = None
    """Its velocity (m/s, [x, y, z]) standing free: it moves on a straight line from at."""
    fleet: int | None = Field(default=None, ge=2, le=40)
    """Not one craft but this many (seeds seed, seed + 1, ...) in a loose formation."""
    spacing: Any = None
    """The fleet's spacing (a length; default 2.5 times the first craft's radius)."""
    plane: str | None = None
    """Instead of kind: a space plane of vidgen/space-plane (glider, freighter, needle, lifter, scout, skiff); its parts' options (wing, fins, body, scheme, scorch...) as extra keys."""
    hull: str | list[str] | None = None
    """Instead of kind: a giant ship of vidgen/space-hull (spine, carrier, cluster, lance, wheel, ark, twin; a list with fleet), with length, age, palette and the family's numbers as extra keys."""
    parts: dict[str, Any] | None = None
    """Instead of kind: a craft of the kit's own parts (vidgen/space-craft): {part: hull, shape: prism, ..., attach: [{at: fore, part: dish, diameter: 3}, {around: {count: 2, along: 0.5}, part: solarWing}]}."""
    effects: dict[str, Any] | None = None
    """Effects of vidgen/space-effects on it: {reentry, contrails, exhaust, vapour} (a surface scene: they follow its flight; an orbital one: exhaust only)."""
    gear: float | dict[str, Any] | None = None
    """A plane's landing gear, 0 (up) to 1 (down), or {over: [start, end], from: 0, to: 1}."""
    bay: float | dict[str, Any] | None = None
    """A plane's payload bay doors, 0 to 1, or {over, from, to}."""
    cabin: float | dict[str, Any] | None = None
    """A plane's cabin lights, 0 to 1, or {over, from, to}."""
    controls: dict[str, Any] | None = None
    """A plane's control surfaces held at angles (elevon, roll, rudder, flap, brake, bodyFlap, canard; degrees); default they follow its flight."""
    dress: bool | dict[str, Any] = True
    """A hull's fine detail (vidgen/space-hull-detail): true (default), false (bare), or {windows, lights, nav, hangars, engines, clutter, marks, plumes, ...}."""
    scale_ref: dict[str, Any] | None = None
    """A hull's small craft for size: {kind: ship, at: hangar-1, gap: 120, into: {hangar: hangar-2, over: [0, 10]}, escort: true}."""

    @property
    def maker(self) -> str:
        """What makes it: kit (a ready-made craft or a fleet), plane, hull or parts."""
        return "plane" if self.plane is not None else "hull" if self.hull is not None else "parts" if self.parts is not None else "kit"

    @property
    def hull_kinds(self) -> list[str]:
        return [] if self.hull is None else [self.hull] if isinstance(self.hull, str) else list(self.hull)

    @model_validator(mode="after")
    def _check(self) -> "CraftSpec":
        if self.maker != "kit":
            return self._check_other()
        for key in ("gear", "bay", "cabin", "controls", "scale_ref"):
            if getattr(self, key) is not None:
                raise ValueError(f"craft {self.name}: {key} is a {'hull' if key == 'scale_ref' else 'plane'}'s (give {'hull' if key == 'scale_ref' else 'plane'}: ...)")
        n = names()
        kinds = [self.kind] if isinstance(self.kind, str) else list(self.kind)
        if not kinds:
            raise ValueError(f"craft {self.name}: kind must name a craft kind")
        kinds = [one_of(k, list(n["craft"]), "craft kind") for k in kinds]
        self.kind = kinds[0] if isinstance(self.kind, str) else kinds
        if isinstance(self.kind, list) and self.fleet is None:
            raise ValueError(f"craft {self.name}: a list of kinds makes a fleet: give fleet: N (how many)")
        self.detail = one_of(self.detail, n["details"], "detail")
        if isinstance(self.attitude, str):
            self.attitude = one_of(self.attitude, n["attitudes"], "attitude")
        if self.at is not None:
            point(self.at, f"craft {self.name}.at")
        if self.velocity is not None and not (len(self.velocity) == 3):
            raise ValueError(f"craft {self.name}.velocity must be [x, y, z] m/s")
        if isinstance(self.burn, dict):
            module_options(self.burn, ["seconds", "turn", "attitude"], f"craft {self.name}.burn")
        if self.spacing is not None:
            length(self.spacing, f"craft {self.name}.spacing")
        if self.effects is not None:
            self.effects_spec()
        self.craft_options()
        return self

    def _check_other(self) -> "CraftSpec":
        """A plane, a hull or a craft of the kit's parts."""
        from .space_air_params import Ramp, ScaleRefSpec, air, check_dress, check_parts

        a, n = air(), names()
        given = [k for k in ("plane", "hull", "parts") if getattr(self, k) is not None]
        if len(given) > 1:
            raise ValueError(f"craft {self.name}: give one of plane, hull or parts, not {' and '.join(given)}")
        if "kind" in self.model_fields_set:
            raise ValueError(f"craft {self.name}: give kind (a craft of the kit) or {given[0]}, not both")
        if self.plane is not None:
            self.plane = one_of(self.plane, a["planes"], "plane")
        if self.hull is not None:
            kinds = [one_of(k, list(a["hulls"]), "hull family") for k in self.hull_kinds]
            if not kinds:
                raise ValueError(f"craft {self.name}: hull must name a family")
            if isinstance(self.hull, list) and self.fleet is None:
                raise ValueError(f"craft {self.name}: a list of hull families makes a fleet: give fleet: N (how many)")
            self.hull = kinds[0] if isinstance(self.hull, str) else kinds
        if self.parts is not None:
            check_parts(self.parts)
        if self.fleet is not None and self.maker != "hull":
            raise ValueError(f"craft {self.name}: fleet is for craft of the kit (kind) and hulls (hull); a fleet of {self.maker} is not reached from YAML")
        if self.maker != "plane":
            for key in ("gear", "bay", "cabin", "controls"):
                if getattr(self, key) is not None:
                    raise ValueError(f"craft {self.name}: {key} is a plane's (give plane: glider, ...)")
        for key in ("gear", "bay", "cabin"):
            value = getattr(self, key)
            if isinstance(value, dict):
                Ramp.model_validate(value)
            elif value is not None and not 0 <= value <= 1:
                raise ValueError(f"craft {self.name}.{key}: from 0 to 1, got {value}")
        if self.controls is not None:
            module_options(self.controls, ["elevon", "roll", "rudder", "flap", "brake", "bodyFlap", "canard"], f"craft {self.name}.controls")
        if self.maker == "hull":
            if self.dress is not True:
                check_dress(self.dress)
            if self.scale_ref is not None:
                ScaleRefSpec.model_validate(self.scale_ref)
                if self.scale_ref.get("into") is not None and self.dress is False:
                    raise ValueError(f"craft {self.name}: scale_ref.into flies the craft into a bay along the detail's approach: it needs dress (leave out dress: false)")
        else:
            if "dress" in self.model_fields_set:
                raise ValueError(f"craft {self.name}: dress is a hull's (give hull: carrier, ...)")
            if self.scale_ref is not None:
                raise ValueError(f"craft {self.name}: scale_ref is a hull's (give hull: carrier, ...)")
        if one_of(self.detail, n["details"], "detail") != self.detail:   # (an unset detail stays unset: a fleet of hulls keeps its own)
            self.detail = one_of(self.detail, n["details"], "detail")
        if isinstance(self.attitude, str):
            self.attitude = one_of(self.attitude, n["attitudes"], "attitude")
        if self.at is not None:
            point(self.at, f"craft {self.name}.at")
        if self.velocity is not None and not (len(self.velocity) == 3):
            raise ValueError(f"craft {self.name}.velocity must be [x, y, z] m/s")
        if isinstance(self.burn, dict):
            module_options(self.burn, ["seconds", "turn", "attitude"], f"craft {self.name}.burn")
        if self.spacing is not None:
            length(self.spacing, f"craft {self.name}.spacing")
        if self.effects is not None:
            self.effects_spec()
        self.craft_options()
        return self

    def effects_spec(self) -> Any:
        """Its effects (:class:`~vidgen.scenes.space_air_params.EffectsSpec`)."""
        from .space_air_params import EffectsSpec

        return EffectsSpec.model_validate(self.effects)

    def craft_options(self) -> dict[str, Any]:
        if self.maker != "kit":
            return self._other_options()
        n = names()
        own = sorted({o for k in ([self.kind] if isinstance(self.kind, str) else self.kind) for o in n["craft"][k]})
        out = module_options(self.extras(), [*n["craft_options"], *own], f"craft {self.name}",
                             leave=("seed", "detail", "name", "camera", "height", "sun", "target", "lights", "marker"))
        out["detail"] = self.detail
        if self.seed is not None:
            out["seed"] = self.seed
        if self.marker:
            out["marker"] = self.marker
        if self.lights is not None:
            out["lights"] = self.lights
        return out

    def _other_options(self) -> dict[str, Any]:
        """The options of plane(), hull() or the kit (parts), checked against the module's own lists."""
        from .space_air_params import air

        a = air()
        leave = ("seed", "detail", "name", "camera", "height", "sun", "target", "lights", "marker", "gear", "bay")
        if self.maker == "plane":
            out = module_options(self.extras(), a["plane_options"], f"craft {self.name}", leave=leave)
        elif self.maker == "hull":
            params = sorted({p for k in self.hull_kinds for p in a["hulls"][k]})
            out = module_options(self.extras(), [*a["hull_options"], *params], f"craft {self.name}", leave=leave)
            if "length" in out:
                metres = length(out["length"], f"craft {self.name}.length")
                if not 200 <= metres <= 20000:
                    raise ValueError(f"craft {self.name}.length: a hull is 200 m to 20 km long, got {metres:g} m")
                out["length"] = metres
            if "palette" in out:
                out["palette"] = one_of(str(out["palette"]), a["palettes"], "palette")
        else:
            out = module_options(self.extras(), [k for k in a["kit_options"] if k not in ("seed", "detail")], f"craft {self.name}")
        if not (self.maker == "hull" and self.fleet and "detail" not in self.model_fields_set):   # a fleet of hulls: hullFleet's own far
            out["detail"] = self.detail
        if self.seed is not None:
            out["seed"] = self.seed
        if self.marker:
            out["marker"] = self.marker
        if self.lights is not None:
            out["lights"] = self.lights
        return out

    def hull_length(self) -> float:
        """The hull's length in metres when it is stated, else the shortest of its family's usual lengths (a lower bound)."""
        from .space_air_params import air

        given = self.extras().get("length")
        if given is not None:
            return length(given, f"craft {self.name}.length")
        return min(air()["hull_lengths"][k][0] for k in self.hull_kinds)


PHENOMENA =("black-hole", "wormhole", "warp", "asteroids", "asteroid", "comet", "aurora")


class PhenomenonSpec(Open):
    """A thing of ``phenomena:`` (vidgen/space-phenomena). Also the options of its kind (``disc``, ``inner``, ``outer``, ``tilt``, ``quality``, ``count``, ``latitude``...)."""

    kind: str
    """black-hole, wormhole, warp, asteroids, asteroid, comet or aurora."""
    name: str | None = None
    """Its name (what the camera and the music name; default its kind)."""
    at: list[Any] | None = None
    """Where it stands, [x, y, z] lengths (default [0, 0, 0]); not for a warp, a field of asteroids or an aurora."""
    size: Any = None
    """Its unit as a length: a black hole's horizon radius, a wormhole's throat, a rock's or a comet's scale; metres per unit of an asteroid belt (default: a sixteenth of the radius of the body it goes round)."""
    world: str | None = None
    """aurora: the world it shines on."""
    around: str | None = None
    """asteroids with layout belt: the world it goes round."""
    body: str | None = None
    """comet: the body of the orbit data it is (it grows near the sun)."""
    over: list[Any] | None = None
    """warp: [start, end] of the jump (seconds or 'bar 9'); default the whole scene."""
    other: dict[str, Any] | None = None
    """wormhole: the sky on the other side (sky options: {seed: 11, look: rich})."""
    cut: dict[str, Any] | None = None
    """warp: the jump as a cut between two scenes (vidgen/space-camera's warpCut): {at: 'bar 9', seconds: 3, split: 0.5}; the scene before the cut shows the jump up to split, the scene after it the rest."""

    @model_validator(mode="after")
    def _check(self) -> "PhenomenonSpec":
        self.kind = one_of(self.kind, list(PHENOMENA), "phenomenon")
        if self.name is None:
            self.name = self.kind
        where = f"phenomena {self.name}"
        fixed = {"warp": (), "asteroids": ("around",), "aurora": ("world",), "comet": ("body", "at", "size"), "wormhole": ("at", "size", "other"),
                 "black-hole": ("at", "size"), "asteroid": ("at", "size")}[self.kind]
        for key in ("at", "size", "world", "around", "body", "over", "other"):
            if getattr(self, key) is not None and key not in fixed and not (key == "over" and self.kind == "warp") \
                    and not (self.kind == "asteroids" and key in ("at", "size")):
                raise ValueError(f"{where}: a {self.kind} takes no {key}")
        if self.kind == "aurora" and self.world is None:
            raise ValueError(f"{where}: an aurora needs world: the world it shines on")
        if self.at is not None:
            point(self.at, f"{where}.at")
        if self.size is not None and length(self.size, f"{where}.size") <= 0:
            raise ValueError(f"{where}.size must be above 0")
        if self.over is not None:
            if len(self.over) != 2:
                raise ValueError(f"{where}.over must be [start, end]")
            [scene_time(v, f"{where}.over[{i}]") for i, v in enumerate(self.over)]
        if self.other is not None:
            SkySpec.model_validate(self.other)
        if self.cut is not None:
            if self.kind != "warp":
                raise ValueError(f"{where}: cut is a warp's (the jump as a cut between two scenes)")
            if self.over is not None:
                raise ValueError(f"{where}: give over (the jump inside the scene) or cut (the jump across a cut), not both")
            module_options(self.cut, ["at", "seconds", "split"], f"{where}.cut")
            if "at" not in self.cut:
                raise ValueError(f"{where}.cut: give at: the time of the cut (seconds or 'bar 9')")
            scene_time(self.cut["at"], f"{where}.cut.at")
            if not 0 < float(self.cut.get("seconds", 3)) <= 60 or not 0 <= float(self.cut.get("split", 0.5)) <= 1:
                raise ValueError(f"{where}.cut: seconds from 0 to 60, split from 0 to 1")
        self.module()
        return self

    def module(self) -> dict[str, Any]:
        leave = ("sky", "other", "fps", "seconds", "space", "body", "orbits", "light", "sun")
        return module_options(self.extras(), names()["phenomena"][self.kind], f"phenomena {self.name}", leave=leave)


# ----- camera, finish, music, cards ------------------------------------------------------------------


MOVE_WORDS = {"flyby": "fly-by", "fly_by": "fly-by", "flyBy": "fly-by"}
#: Keys of a move that name things of the scene (the generator makes them subjects).
SUBJECT_KEYS = ("subject", "behind", "of", "target", "around", "level", "from", "to")


class MoveSpec(Open):
    """A move of ``camera:`` (vidgen/space-camera, and in the air and beside giant ships vidgen/space-camera-air). Also the move's own options (``phase``, ``distance``, ``closest``, ``side``, ``view``, ``push``, ``rate``, ``place``, ``roll``, ``stops``, ``flight``, ``ship``, ``deck``, ``clearance``, ``standoff``...)."""

    move: str
    """arc, fly-by, pass, arrive, reveal, follow, zoom or look; in the air skim, climb-through, descend-through, chase, wing, fly-past, orbit-peak, rise, descend, ascend; beside a giant ship hull-pass, hull-reveal, into-bay, stern-burn, scale-zoom."""
    subject: str | None = None
    """What it looks at, flies by or follows: a body, craft or phenomenon by name."""
    over: list[Any] | None = None
    """[start, end] of the move: seconds of the scene, or places in the song ('bar 9', 'bar 13 beat 3') with music_data; default the whole scene for one move."""
    lens: str | float | list[Any] | None = None
    """A lens by name (ultra-wide 16 mm, wide 24, wide-normal 35, normal 50, portrait 85, long 135, tele 300, long-tele 600) or in mm; rise, descend and ascend take a pair [from, to]."""
    cut: bool = False
    """A cut into this move: it need not start where the move before left the camera."""
    match: str | None = None
    """A match cut on a disc (vidgen/space-camera's matchDisc): the thing the move before shows at this move's start; this move's subject is placed and sized as that disc was (give it cut: true)."""
    continues: bool = False
    """A skim after a descend (or an ascend): it starts where that move leaves the camera (its place, heading, speed and height), with no cut."""

    @model_validator(mode="after")
    def _check(self) -> "MoveSpec":
        n = names()
        from .space_air_params import air_move_names, kebab, ship_move_names

        word = MOVE_WORDS.get(self.move, self.move)
        new = [*air_move_names(), *ship_move_names()]
        self.move = one_of(kebab(word) if kebab(word) in new else word, [*n["moves"], *new], "camera move")
        lenses = self.lens if isinstance(self.lens, list) else [self.lens]
        if isinstance(self.lens, list) and (len(self.lens) != 2 or self.move not in ("rise", "descend", "ascend")):
            raise ValueError(f"camera {self.move}: a lens pair [from, to] is for rise, descend and ascend; give one lens")
        for i, value in enumerate(lenses):
            if isinstance(value, str):
                lenses[i] = one_of(value, list(n["lenses"]), "lens")
            elif value is not None and not (isinstance(value, (int, float)) and 4 <= value <= 5000):
                raise ValueError(f"camera {self.move}: lens {value} mm: from 4 to 5000")
        if isinstance(self.lens, (str, list)):   # only a name is rewritten (an unset lens stays unset: the page's PARAMS)
            self.lens = lenses if isinstance(self.lens, list) else lenses[0]
        if self.over is not None:
            if len(self.over) != 2:
                raise ValueError(f"camera {self.move}.over must be [start, end]")
            a, b = (scene_time(v, f"camera {self.move}.over[{i}]") for i, v in enumerate(self.over))
            if not uses_bars(a) and not uses_bars(b) and not b > a:  # type: ignore[operator]
                raise ValueError(f"camera {self.move}.over: the end must come after the start, got {self.over}")
        extra = self.options()
        if self.air:
            from .space_air_params import MOVE_LENGTHS, TIME_OPTIONS

            for key in TIME_OPTIONS.get(self.move, ()):
                if key in extra:
                    scene_time(extra[key], f"camera {self.move}.{key}")
            for key in MOVE_LENGTHS.get(self.move, ()):
                if isinstance(extra.get(key), str):
                    length(extra[key], f"camera {self.move}.{key}")
        else:
            move_lengths(extra, f"camera {self.move}")
            if "at" in extra:
                scene_time(extra["at"], f"camera {self.move}.at")
        if self.continues and self.move != "skim":
            raise ValueError(f"camera {self.move}: continues is a skim's (after a descend or an ascend: it starts where that move ends)")
        if self.match is not None and not self.cut:
            raise ValueError(f"camera {self.move}: a match cut is a cut: give it cut: true with match: {self.match}")
        if self.match is not None and (self.air or "distance" not in names_of_move(self.move)):
            raise ValueError(f"camera {self.move}: match places the subject by its distance; give it to a move that takes distance (arc, follow, look...)")
        return self

    @property
    def air(self) -> bool:
        """A move of vidgen/space-camera-air (in the air or beside a giant ship)."""
        from .space_air_params import move_option_list

        return move_option_list(self.move) is not None

    @property
    def ship(self) -> bool:
        """A move beside a giant ship."""
        from .space_air_params import ship_move_names

        return self.move in ship_move_names()

    @staticmethod
    def _phase(value: Any) -> Any:
        return one_of(value, names()["phases"], "phase") if isinstance(value, str) else value

    def options(self) -> dict[str, Any]:
        """The move's own options (camelCase; ``progress`` and ``time`` are the scene's to set)."""
        if self.air:
            from .space_air_params import move_option_list

            return module_options(self.extras(), move_option_list(self.move) or [], f"camera {self.move}", leave=("over", "lens", "time", "progress", "seconds"))
        out = module_options(self.extras(), names()["moves"][self.move], f"camera {self.move}", leave=("subject", "over", "lens", "time", "progress"))
        if "phase" in out:
            out["phase"] = [self._phase(p) for p in out["phase"]] if isinstance(out["phase"], list) else self._phase(out["phase"])
        if isinstance(out.get("view"), str):
            out["view"] = one_of(out["view"], names()["views"], "view")
        return out

    def named(self) -> list[tuple[str, str]]:
        """``(key, name)`` of every thing of the scene this move names (subject, behind, of, target, zoom stops...)."""
        if self.air:
            found = [(k, v) for k, v in (("subject", self.subject), ("world", self.options().get("world")), ("behind", self.options().get("behind"))) if isinstance(v, str)]
            return found
        found = [(k, v) for k, v in [("subject", self.subject), *((k, self.options().get(k)) for k in SUBJECT_KEYS[1:])] if isinstance(v, str)]
        for i, stop in enumerate(self.options().get("stops") or []):
            if isinstance(stop, dict) and isinstance(stop.get("subject"), str):
                found.append((f"stops[{i}].subject", stop["subject"]))
        if self.match is not None:
            found.append(("match", self.match))
        return found


def names_of_move(move: str) -> list[str]:
    """The options of a move of vidgen/space-camera."""
    return names()["moves"].get(move, [])


class FinishSpec(SceneParams):
    """``finish:``: vidgen/three-finish with space-safe defaults (no FXAA: it breaks stars and thin rings)."""

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)
    header_synonyms = False
    bloom: bool | float | dict[str, Any] = Field(default_factory=lambda: {"strength": 0.3, "radius": 0.5, "threshold": 1.0})
    """Glow round the brightest light: a strength (0.3), true, false, or {strength, radius, threshold, scale}."""
    grain: float = Field(default=0.02, ge=0, le=0.5)
    """Film grain."""
    vignette: bool | float | dict[str, Any] = 0.3
    """Darker corners: an amount, false, or {amount, inner, outer}."""
    grade: dict[str, Any] = Field(default_factory=dict)
    """Colour grade: {temperature, tint, saturation, contrast, lift, gamma, gain, filter}."""
    motion_blur: bool | int | dict[str, Any] = False
    """Samples across a 180 degree shutter (3 to 5), true (5) or {samples, shutter}: costs a frame that many times."""
    depth_of_field: bool | dict[str, Any] = False
    """true, or {f_stop, max_blur, quality}: focused on the camera move's subject (shot.focus), every frame."""
    antialias: Literal["none", "fxaa"] = "none"
    """none (space-safe default: FXAA makes small crosses of stars and dots of thin rings) or fxaa."""
    noise: bool | float | dict[str, Any] | None = None
    """A camera sensor's noise in place of the grain (off unless given): an amount (0.012 at mid grey), true, or {amount, color, size, floor}."""
    range_: bool | float | dict[str, Any] | None = Field(default=None, alias="range")
    """A camera's limited dynamic range (off unless given): stops above mid grey where it clips (2.5), true, or {stops, shoulder, black}."""
    sharpen: bool | float | dict[str, Any] | None = None
    """In-camera sharpening with faint halos (off unless given): an amount (0.5), true, or {amount, radius, limit}."""
    distort: bool | float | dict[str, Any] | None = None
    """The lens's barrel distortion (off unless given), from the camera's lens at each moment (strong at ultra-wide, none from 50 mm): true, a share of it (1), or {amount, mm}."""
    edges: bool | float | dict[str, Any] | None = None
    """Softness and a colour fringe growing towards the frame's edges (off unless given): true (1.2 and 0.8 pixels at the corner), the softness, or {soft, fringe, power}."""
    halation: bool | float | dict[str, Any] | None = None
    """A warm glow bleeding round the brightest edges (off unless given): an amount (0.15), true, or {amount, radius, threshold, color}."""

    @model_validator(mode="after")
    def _check(self) -> "FinishSpec":
        self.options()
        return self

    def options(self) -> dict[str, Any]:
        """Three-finish's options (camelCase), every key checked against its own lists."""
        known = names()["finish_options"]
        out: dict[str, Any] = {"antialias": self.antialias, "grain": self.grain}
        sensor = [(k, v) for k, v in (("noise", self.noise), ("range", self.range_), ("sharpen", self.sharpen),
                                      ("distort", self.distort), ("edges", self.edges), ("halation", self.halation)) if v is not None]
        for key, value in (("bloom", self.bloom), ("vignette", self.vignette), ("grade", self.grade), ("motionBlur", self.motion_blur), *sensor):
            if isinstance(value, dict):
                value = module_options(value, known[key], f"finish.{snake(key)}")
            if isinstance(value, int) and not isinstance(value, bool) and key == "motionBlur":
                value = {"samples": value}
            if key != "grade" or value:
                out[key] = value
        if self.depth_of_field:
            out["dof"] = module_options(self.depth_of_field, known["dof"], "finish.depth_of_field", leave=("focus",)) if isinstance(self.depth_of_field, dict) else {}
        out.update(module_options(dict(self.model_extra or {}), list(known), "finish", leave=("update", "bloom", "vignette", "grade", "motionBlur", "dof", "antialias", "grain", "noise", "range", "sharpen",
                                                                                         "distort", "edges", "halation")))
        return out


class ReactionSpec(SceneParams):
    """A reaction of ``music:``: ``{track: kick, pulse: Sun}``, ``{track: level, glow: Ship}``, ``{track: hook, glint: Station}``."""

    header_synonyms = False
    track: str
    """A track of the score, or level (the measured level of the video's music)."""
    pulse: str | None = None
    """A brightness pulse on each hit of the track, of this thing (a star's glare, the sky, a black hole, a warp; a craft's lights). Never the camera."""
    glow: str | None = None
    """A level that follows how strongly the track sounds, of this thing (a craft: its throttle)."""
    glint: str | None = None
    """A glint on each note, of this thing (a craft: its lights)."""
    as_: Literal["lights", "throttle", "rcs", "boost", "pulse"] | None = Field(default=None, alias="as")
    """For a craft: what the reaction drives instead (lights, throttle or rcs; with effects boost: the afterburner, pulse: the glow's flicker)."""
    amount: float = Field(default=0.6, ge=0, le=8)
    """How strong: the share the brightness grows by at a full hit (0.6), or a craft's value at full."""
    decay: float = Field(default=0.18, gt=0, le=10)
    """Seconds a pulse or a glint takes to fall to a third."""

    @model_validator(mode="after")
    def _check(self) -> "ReactionSpec":
        given = [k for k in REACTIONS if getattr(self, k) is not None]
        if len(given) != 1:
            raise ValueError(f"music: a reaction to {self.track} gives one of pulse, glow or glint (the thing it changes), got {', '.join(given) or 'none'}")
        return self

    @property
    def action(self) -> str:
        return next(k for k in REACTIONS if getattr(self, k) is not None)

    @property
    def target(self) -> str:
        return str(getattr(self, self.action))


class CardSpec(Open):
    """``title:`` or ``end_card:`` through vidgen/title-cards (Escapement's look). Also its options (``side``, ``start``, ``hold``, ``fade_in``, ``fade_out``, ``size``, ``color``, ``accent``, ``link``...)."""

    title: TranslatableStr
    """The card's title."""
    subtitle: TranslatableStr = ""
    """The line under it."""
    lines: list[TranslatableStr] = Field(default_factory=list)
    """An end card's further lines."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        return {"title": value} if isinstance(value, str) else value

    def card_options(self, kind: str) -> dict[str, Any]:
        known = names()["title_options" if kind == "title" else "end_options"]
        out = module_options(self.extras(), known, kind, leave=("title", "subtitle", "lines"))
        out = {"title": str(self.title), **({"subtitle": str(self.subtitle)} if self.subtitle else {}), **out}
        if self.lines:
            if kind == "title":
                raise ValueError("title: lines are an end card's (end_card: {title, lines})")
            out["lines"] = [str(x) for x in self.lines]
        return out


__all__ = ["BAR", "DEFAULT_RADIUS", "LENGTH_KEYS", "PHENOMENA", "REACTIONS", "SUBJECT_KEYS", "BodySpec", "CardSpec", "CraftSpec",
           "FinishSpec", "LightSpec", "MoveSpec", "Open", "OrbitData", "PhenomenonSpec", "ReactionSpec", "ScaleSpec", "SkySpec", "SunSpec",
           "camel", "direction", "length", "module_options", "move_lengths", "names", "one_of", "point", "real_radius", "scene_time", "snake", "uses_bars"]
