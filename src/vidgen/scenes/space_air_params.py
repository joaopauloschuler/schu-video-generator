"""The words of a ``space`` scene in the air and beside giant ships (DESIGN.md §123.14): the world of a
surface scene (``world:``: the planet, the place, the sun, the air, the sea, the ground, the clouds),
its flights (``flights:``, the ``flight_data`` vocabulary of Step 385), what a craft may be besides a
craft of the kit (a plane, a giant hull, a craft of the kit's own parts), the effects on a craft,
flashes on cuts, and the camera moves of ``vidgen/space-camera-air``.

Every key is checked here, at ``vidgen validate``, with did-you-mean; the names come from the shipped
modules through :func:`vidgen.web.space_names.air_names` (one registry for validation, the guide and
the parts sheet). Values a module checks itself (a deck's colour, a wing's sweep) are checked when the
page loads, by the module, with the option named. Imports only ``vidgen.api`` and its siblings.
"""

import math
import re
from typing import Any

from pydantic import ConfigDict

from vidgen.api import *

from .space_params import Open, camel, length, module_options, one_of, scene_time, snake, uses_bars

#: Metres a ship move's stand-off (or a hull camera's distance) may not go under: the view's near plane is
#: 4 m beside a hull (set by the page, DESIGN.md §123.12), and nearer than this the plates read as a model.
MIN_STANDOFF = 10.0
#: The near plane of a SpaceView with a giant hull in it (Step 390: the default 0.01 m slices a hull the
#: camera is inside the bounding sphere of, and draws the world behind it over the hull).
HULL_NEAR = 4.0


def own_and(model: Any, known: list[str]) -> list[str]:
    """``known`` (a module's option list, camelCase) with the model's own keys (camelCase too), so that a
    mistyped key of either is named with the closest word of both."""
    return list(dict.fromkeys([*(camel(k) for k in type(model).model_fields), *known]))


def air() -> dict[str, Any]:
    """The Phase AO modules' names and options (:func:`vidgen.web.space_names.air_names`)."""
    return air_names()


def kebab(name: str) -> str:
    """``climbThrough`` -> ``climb-through``; ``climb_through`` -> ``climb-through``."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", lambda m: "-" + m.group(1).lower(), name).replace("_", "-").lower()


def camel_move(name: str) -> str:
    """``climb-through`` -> ``climbThrough`` (the module's spelling)."""
    head, *rest = name.split("-")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def air_move_names() -> list[str]:
    """The air moves as the YAML writes them (kebab-case, as the parts sheet names them)."""
    return [kebab(m) for m in air()["air_moves"]]


def ship_move_names() -> list[str]:
    """The moves beside a giant hull as the YAML writes them."""
    return [kebab(m) for m in air()["ship_moves"]]


def move_option_list(move: str) -> list[str] | None:
    """The options the air or ship move ``move`` (kebab-case) takes, or None for a move of vidgen/space-camera."""
    a = air()
    return {**a["air_moves"], **a["ship_moves"]}.get(camel_move(move))


#: Options of the new moves that hold a time (seconds or 'bar N').
TIME_OPTIONS = {"fly-past": ("at",), "hull-reveal": ("at",), "stern-burn": ("light",)}
#: Options of the new moves that are lengths (metres, or text with a unit).
MOVE_LENGTHS = {
    "skim": ("clearance", "margin"), "climb-through": ("below", "above", "margin", "settle"), "descend-through": ("below", "above", "margin", "settle"),
    "chase": ("height", "side", "lead", "margin"), "fly-past": ("closest", "rise", "eye", "margin"),
    "orbit-peak": ("radius", "height", "top", "aim", "clearance", "margin"), "rise": ("from", "to", "margin"),
    "descend": ("from", "to", "margin"), "ascend": ("from", "to", "margin"),
    "hull-pass": ("standoff", "lane", "reach", "ahead"), "hull-reveal": ("standoff", "lane"), "into-bay": ("from", "along"),
    "stern-burn": ("distance", "push"), "scale-zoom": ("close",),
}
#: What each new move needs in the scene: a flight, ground or water, cloud decks, land, a hull.
NEEDS = {"skim": "surface", "chase": "flight", "wing": "flight", "fly-past": "flight", "climb-through": "decks", "descend-through": "decks",
         "orbit-peak": "peak", "hull-pass": "hull", "hull-reveal": "hull", "into-bay": "hull", "stern-burn": "hull", "scale-zoom": "hull"}
#: Names of places on every hull (DESIGN.md §123.10), and the numbered kinds (hangar-1, dock-2, bell-3).
HULL_POINTS = ("bow", "stern", "top", "bottom", "port", "starboard", "bridge")
HULL_NUMBERED = re.compile(r"^(hangar|dock|bell)-[1-9][0-9]*$")


def hull_point(value: str, where: str) -> str:
    """A place on a hull: a fixed point (bow, port, bridge...) or a numbered one (hangar-2); the page checks the number."""
    if value in HULL_POINTS or HULL_NUMBERED.match(value):
        return value
    raise ValueError(f"{where}: no place '{value}' on a hull{did_you_mean(value, [*HULL_POINTS, 'hangar-1', 'dock-1', 'bell-1'])} "
                     f"(places: {', '.join(HULL_POINTS)}, hangar-N, dock-N, bell-N; the page names the hull's own when N is too large)")


# ----- the sun of a surface scene ---------------------------------------------------------------------


def sun_of_date(date: str, utc: str, at: list[float]) -> list[float]:
    """[elevation, azimuth] (degrees; azimuth from north through east) of the Sun seen from ``at`` ([latitude,
    longitude]) on ``date`` at ``utc`` (HH:MM): the Earth's position from JPL's approximate elements
    (:mod:`vidgen.orbits.ephemeris`), the mean obliquity, Greenwich mean sidereal time; no refraction."""
    match = re.match(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$", str(utc))
    if match is None:
        raise ValueError(f"world.sun.utc: {utc!r} is not a time of day (HH:MM, universal time)")
    hours = int(match.group(1)) + int(match.group(2)) / 60 + int(match.group(3) or 0) / 3600
    if not 0 <= hours < 24:
        raise ValueError(f"world.sun.utc: {utc!r} is not a time of day")
    try:
        jd = orbits.ephemeris.julian_date(str(date)) + hours / 24
    except VidgenError as error:
        raise ValueError(f"world.sun.date: {error}") from None
    r = orbits.ephemeris.heliocentric("earth", jd)
    x, y, z = (-float(v) for v in r)                       # towards the Sun, ecliptic J2000
    eps = math.radians(23.439281)
    ye, ze = y * math.cos(eps) - z * math.sin(eps), y * math.sin(eps) + z * math.cos(eps)
    ra, dec = math.atan2(ye, x), math.atan2(ze, math.hypot(x, ye))
    gmst = math.radians((280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360)
    h = gmst + math.radians(at[1]) - ra
    lat = math.radians(at[0])
    east, north = -math.cos(dec) * math.sin(h), math.cos(lat) * math.sin(dec) - math.sin(lat) * math.cos(dec) * math.cos(h)
    up = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(h)
    return [round(math.degrees(math.asin(max(-1.0, min(1.0, up)))), 6), round(math.degrees(math.atan2(east, north)) % 360, 6)]


class SunPlace(SceneParams):
    """``world.sun``: where the sun stands at the place: ``[elevation, azimuth]`` (degrees; azimuth from
    north through east), ``{elevation, azimuth}``, or ``{date, utc}`` (the Earth's Sun on that day)."""

    header_synonyms = False
    elevation: float | None = Field(default=None, ge=-90, le=90)
    """Degrees over the horizon (negative: under it, twilight). ``height`` is the same."""
    azimuth: float | None = None
    """Degrees from north through east (90 east, 180 south, 270 west)."""
    date: str | None = None
    """The day (YYYY-MM-DD): the Earth's Sun at the place on that day, at ``utc``."""
    utc: str | None = None
    """With date: the time of day in universal time (HH:MM)."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            if len(value) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
                raise ValueError(f"world.sun: [elevation, azimuth] in degrees, got {list(value)!r}")
            return {"elevation": value[0], "azimuth": value[1]}
        if isinstance(value, dict) and "height" in value:
            value = {**value, "elevation": value["height"]}
            value.pop("height")
        return value

    @model_validator(mode="after")
    def _check(self) -> "SunPlace":
        dated = self.date is not None or self.utc is not None
        if dated and (self.date is None or self.utc is None):
            raise ValueError("world.sun: give both date and utc (the Earth's Sun on that day at that universal time)")
        if dated and (self.elevation is not None or self.azimuth is not None):
            raise ValueError("world.sun: give [elevation, azimuth] or {date, utc}, not both")
        if not dated and (self.elevation is None or self.azimuth is None):
            raise ValueError("world.sun: give elevation and azimuth (degrees), e.g. [12, 250], or {date: '2026-06-21', utc: '19:30'}")
        return self

    def pair(self, at: list[float]) -> list[float]:
        """[elevation, azimuth] in degrees."""
        if self.date is not None:
            return sun_of_date(self.date, str(self.utc), at)
        return [float(self.elevation), float(self.azimuth)]   # type: ignore[arg-type]


# ----- sea, ground, clouds -------------------------------------------------------------------------


class SeaSpec(Open):
    """``world.sea``: the sea of vidgen/space-sea. Also its other options (``filter``, ``shoal``, ``waves``) and a state's numbers (``wind``, ``height``, ``swell``...)."""

    state: str | dict[str, Any] = "breeze"
    """calm, breeze, swell, rough or storm (or a state of your own: {wind, height, length, swell...})."""
    water: str | dict[str, Any] = "ocean"
    """ocean, green, tropical, grey or methane (or {color, shallow, index, foam, glow})."""
    seed: int | None = Field(default=None, ge=0)
    """Other waves for every seed (default the scene's seed)."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        return {"state": value} if isinstance(value, str) else {} if value is True else value

    @model_validator(mode="after")
    def _check(self) -> "SeaSpec":
        a = air()
        if isinstance(self.state, str):
            self.state = one_of(self.state, a["sea_states"], "sea state")
        else:
            module_options(self.state, a["state_options"], "world.sea.state")
        if isinstance(self.water, str):
            self.water = one_of(self.water, a["waters"], "water")
        module_options(self.extras(), own_and(self, [*a["sea_options"], *a["state_options"]]), "world.sea", leave=("depth", "shade", "anchor"))
        return self

    def module(self, seed: int) -> dict[str, Any]:
        a = air()
        rest = module_options(self.extras(), [*a["sea_options"], *a["state_options"]], "world.sea", leave=("state", "seed", "water", "depth", "shade", "anchor"))
        return {"state": self.state, "water": self.water, "seed": self.seed if self.seed is not None else seed, **rest}

    def crest(self) -> float:
        """Metres the crests may stand over the mean level: the state's wave height (or a wind sea's, about
        0.0246 x wind^2), the margin a flight over this sea keeps besides its own."""
        state = self.state if isinstance(self.state, dict) else _state_numbers(str(self.state))
        swell = float(state["swell"].get("height") or 0) if isinstance(state.get("swell"), dict) else 0.0
        wind = float(state["height"]) if state.get("height") else 0.0246 * float(state.get("wind") or 0) ** 2
        return round(max(wind, swell), 2)


def _state_numbers(name: str) -> dict[str, Any]:
    import json

    raw = web_space_entries("vidgen/space-sea", "STATES")[name]
    text = re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', raw)
    return json.loads(text)


class LandSpec(Open):
    """``world.land``: the ground of vidgen/space-land. Also its recipe's parts (``mountains``, ``craters``, ``dunes``, ``canyons``, ``volcanoes``, ``materials``...)."""

    preset: str | None = None
    """alpine, mars, canyon, dunes, snow, volcanic or airless (a world and a place of its own; world.planet / world.at change them)."""
    seed: int | None = Field(default=None, ge=0)
    """Other mountains for every seed."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        return {"preset": value} if isinstance(value, str) else {} if value is True else value

    @model_validator(mode="after")
    def _check(self) -> "LandSpec":
        a = air()
        if self.preset is not None:
            self.preset = one_of(self.preset, a["land_presets"], "land preset")
        module_options(self.extras(), own_and(self, [*a["land_options"], *a["land_parts"]]), "world.land", leave=("world", "at", "macro", "shade", "water"))
        return self

    def module(self) -> dict[str, Any]:
        a = air()
        rest = module_options(self.extras(), [*a["land_options"], *a["land_parts"]], "world.land")
        return {**({"preset": self.preset} if self.preset else {}), **({"seed": self.seed} if self.seed is not None else {}), **rest}

    @property
    def volcanic(self) -> bool:
        """Whether the ground has volcanoes (a lava glow to drive)."""
        return self.preset == "volcanic" or bool((self.extras().get("volcanoes") or {}).get("height"))


class LightningSpec(Open):
    """``world.clouds.lightning``: flashes in the towers or the deck: ``rate`` (a seeded rate a minute), stated ``times`` (seconds or 'bar 9 beat 3'), ``track`` (the hits of a track of the score), and the module's ``power``, ``color``, ``radius``, ``seed``."""

    times: list[Any] = Field(default_factory=list)
    """Times of strikes: seconds of the scene, or places in the song ('bar 9 beat 3', with music_data)."""
    track: str | None = None
    """A track of the score: a strike on each of its hits (with music_data)."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        return {"rate": 10} if value is True else value

    @model_validator(mode="after")
    def _check(self) -> "LightningSpec":
        for i, v in enumerate(self.times):
            scene_time(v, f"world.clouds.lightning.times[{i}]")
        module_options(self.extras(), own_and(self, air()["lightning_options"]), "world.clouds.lightning", leave=("from", "to"))
        return self

    @property
    def uses_bars(self) -> bool:
        return any(uses_bars(scene_time(v, "times")) for v in self.times)


class CloudSpec(Open):
    """``world.clouds``: cloud decks of vidgen/space-clouds. Also its other options (``wind``, ``direction``, ``floor``)."""

    sky: str | None = None
    """fair, overcast, layers, towers or storm (ready-made decks, towers and lightning)."""
    decks: list[dict[str, Any]] | None = None
    """Decks of your own: [{type: cumulus | stratus | cirrus, base, top, cover, name, ...}] (instead of a sky's)."""
    towers: int | dict[str, Any] | None = None
    """Cloud towers: a count, or {count, seed, spread, radius, base, top, anvil, at}."""
    lightning: LightningSpec | bool | None = None
    """Lightning: true (seeded), or {times: [3.5, 'bar 9'], track: kick, rate, power, ...}."""
    seed: int | None = Field(default=None, ge=0)
    """Other clouds for every seed (default the scene's seed)."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        return {"sky": value} if isinstance(value, str) else {"sky": "fair"} if value is True else value

    @model_validator(mode="after")
    def _check(self) -> "CloudSpec":
        a = air()
        if self.sky is not None:
            self.sky = one_of(self.sky, list(a["skies"]), "cloud sky")
        if self.sky is None and not self.decks:
            raise ValueError(f"world.clouds: give sky (one of {', '.join(a['skies'])}) or decks: [{{type: cumulus, base: 1000, top: 2100}}]")
        for i, d in enumerate(self.decks or []):
            module_options(d, a["deck_options"], f"world.clouds.decks[{i}]")
            if "type" in d:
                d["type"] = one_of(str(d["type"]), a["deck_types"], "deck type")
        if isinstance(self.towers, dict):
            module_options(self.towers, a["tower_options"], "world.clouds.towers")
        module_options(self.extras(), own_and(self, a["cloud_options"]), "world.clouds", leave=("behind", "anchor"))
        return self

    def deck_names(self) -> list[str]:
        """The decks' names in order (a deck's name, else its type), as vidgen/space-clouds names them."""
        if self.decks:
            return [str(d.get("name") or d.get("type") or "cumulus") for d in self.decks]
        return list(air()["skies"][self.sky or "fair"])

    @property
    def has_towers(self) -> bool:
        if self.towers is not None:
            return bool(self.towers if isinstance(self.towers, int) else self.towers.get("count", 4))
        return bool(self.sky and air()["sky_towers"].get(self.sky))


class WorldSpec(SceneParams):
    """``world:`` of a surface scene: one world from orbit to the ground (vidgen/space-descent): the planet,
    the place under the scene's origin, the sun, the air, and the sea, the ground and the clouds under it."""

    header_synonyms = False
    planet: str | None = None
    """A world of vidgen/space-bodies (earth, mars, ochre, boreas, ember, moon...); default the ground's own, else earth."""
    at: list[float] | None = None
    """[latitude, longitude] in degrees of the place under the scene's origin; default the ground's own, else [0, 0]."""
    sun: SunPlace = Field(default_factory=lambda: SunPlace(elevation=35, azimuth=200))
    """[elevation, azimuth] in degrees (default [35, 200]), or {date, utc} (the Earth's Sun on that day)."""
    air: str | dict[str, Any] | None = None
    """earth, mars, thin or thick (vidgen/space-air), or {world, air, radius, ...}; default the planet's."""
    sea: SeaSpec | bool | None = None
    """The sea: a state (calm, breeze, swell, rough, storm) or {state, water, seed, ...}."""
    land: LandSpec | bool | None = None
    """The ground: a preset (alpine, mars, canyon, dunes, snow, volcanic, airless) or {preset, seed, mountains, ...}."""
    clouds: CloudSpec | bool | None = None
    """Cloud decks: a sky (fair, overcast, layers, towers, storm) or {sky | decks, towers, lightning, seed}."""
    globe: dict[str, Any] | None = None
    """More options for the globe seen from high up (vidgen/space-bodies: size, clouds, ...)."""
    handover: str | dict[str, Any] | None = None
    """Where the globe hands over to the near picture: low, high, or {near: [from, to], height: [from, to]} (metres)."""
    match: float = Field(default=1.0, gt=0, le=10)
    """The globe's brightness beside the near picture's."""
    exposure: str = "film"
    """film (default), camera or auto (vidgen/space-air)."""
    ev: float = 0.0
    """Stops over a sunlit ground's exposure (camera, auto)."""
    quality: str = "standard"
    """fast, standard or fine (the air's, sea's, ground's and clouds' own)."""
    shadows: bool | dict[str, Any] | None = None
    """Shadows in the air (default on): light shafts through gaps in the decks, the dim air under a closed deck, mountains'
    shadows in the haze, and the decks' shadows on the ground and the sea; false: none; or {reach, share, steps}."""

    @model_validator(mode="after")
    def _check(self) -> "WorldSpec":
        a, n = air(), space_names()
        if isinstance(self.shadows, dict):
            module_options(self.shadows, a["air_shadows"], "world.shadows")
        if self.planet is not None:
            self.planet = one_of(self.planet, n["worlds"], "world")
        if self.at is not None and (len(self.at) != 2 or abs(self.at[0]) > 90):
            raise ValueError(f"world.at must be [latitude, longitude] in degrees, got {self.at}")
        if isinstance(self.air, str):
            self.air = one_of(self.air, a["air_presets"], "air")
        elif isinstance(self.air, dict):
            module_options(self.air, a["air_options"], "world.air")
        if isinstance(self.handover, str):
            self.handover = one_of(self.handover, a["handovers"], "handover")
        elif isinstance(self.handover, dict):
            module_options(self.handover, ["near", "height"], "world.handover")
        self.exposure = one_of(self.exposure, a["exposures"], "exposure")
        self.quality = one_of(self.quality, a["air_qualities"], "quality")
        if self.globe is not None and "air" in self.globe:
            raise ValueError("world.globe.air: the globe has no air of its own (the air is world.air)")
        for key in ("sea", "land", "clouds"):
            if getattr(self, key) is True:
                setattr(self, key, {"sea": SeaSpec, "land": LandSpec, "clouds": CloudSpec}[key].model_validate(True))
        if self.air is not None and self.land_spec is not None and self.land_spec.preset == "airless":
            raise ValueError("world: the airless ground has no air; a surface scene needs one (vidgen/space-descent): choose another ground")
        return self

    @property
    def sea_spec(self) -> SeaSpec | None:
        return self.sea if isinstance(self.sea, SeaSpec) else None

    @property
    def land_spec(self) -> LandSpec | None:
        return self.land if isinstance(self.land, LandSpec) else None

    @property
    def cloud_spec(self) -> CloudSpec | None:
        return self.clouds if isinstance(self.clouds, CloudSpec) else None

    def place(self) -> list[float]:
        """[latitude, longitude] of the place: given, the ground preset's, else [0, 0]."""
        if self.at is not None:
            return [float(self.at[0]), float(self.at[1])]
        land = self.land_spec
        if land is not None and land.preset:
            return [float(v) for v in _land_preset(land.preset)["at"]]
        return [0.0, 0.0]

    def flight_ground(self) -> dict[str, Any]:
        """The ``ground`` of the scene's flights: the land when there is one (with the world's planet and
        place when they are stated), else the sea (its crests as the margin), else the world's sphere."""
        land = self.land_spec
        if land is not None:
            options = land.module()
            options.pop("quality", None)
            if self.planet is not None:
                options["world"] = self.planet
            if self.at is not None:
                options["at"] = [float(self.at[0]), float(self.at[1])]
            if isinstance(self.air, str):
                options["air"] = self.air
            if "preset" not in options and ("world" not in options or "at" not in options):
                options.setdefault("world", self.planet or "earth")
                options.setdefault("at", self.place())
            return {"land": options}
        if self.sea_spec is not None:
            return {"sea": {"waves": self.sea_spec.crest()}}
        return {"sphere": True}

    def flight_world(self) -> str | None:
        """The world the flights fly over when there is no land to say it: the air's preset, else the planet."""
        if self.land_spec is not None:
            return None
        if isinstance(self.air, str):
            return self.air
        return self.planet


def _land_preset(name: str) -> dict[str, Any]:
    import json

    raw = web_space_entries("vidgen/space-land", "PRESETS")[name]
    out = {}
    for key in ("world", "at", "air"):
        match = re.search(rf"\b{key}:\s*(\"[^\"]*\"|\[[^\]]*\]|null)", raw)
        if match:
            out[key] = json.loads(match.group(1))
    return out


# ----- flights -------------------------------------------------------------------------------------------


class FlightsSpec(SceneParams):
    """``flights:`` of a surface scene: the flights of ``flight_data:`` (Step 385) — a list of {name, start,
    legs} — or {flights: [...], start, speedup, margin, path_samples}. The ground is the scene's own (its
    land, else its sea, else the world's sphere) and the frame is the world's place."""

    header_synonyms = False
    flights: list[flight.Flight] = Field(min_length=1)
    """The flights: [{name: Plane, start: {x: -6000, z: 2000, above_ground: 600, heading: 70, speed: 140}, legs: [{follow: {clearance: 300}, for: 12}, ...]}]."""
    start: float | str = 0.0
    """The time of the scene the flights' time 0 is (seconds or 'bar 9')."""
    speedup: float | None = Field(default=None, gt=0)
    """Flight seconds per second of the scene (default 1: true timing)."""
    margin: float = Field(default=20.0, ge=0)
    """Metres every path keeps over the ground besides a leg's own clearance."""
    path_samples: int = Field(default=256, ge=2, le=4096)
    """Points of each flight's path polyline."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        return {"flights": value} if isinstance(value, list) else value

    @model_validator(mode="after")
    def _check(self) -> "FlightsSpec":
        for f in self.flights:
            if f.start.orbit is not None:
                raise ValueError(f"flights {f.name}: a start from orbit needs the orbit data; a surface scene has none: "
                                 "write the scene out with `vidgen space-page` and give the web scene orbit_data (DESIGN.md §123.7)")
        return self

    @property
    def names(self) -> list[str]:
        return [f.name for f in self.flights]

    def data(self, world: WorldSpec) -> Any:
        """The scene's ``flight_data`` (:class:`~vidgen.scenes.flight_data.FlightData`): these flights over the world's ground."""
        from .flight_data import FlightData

        raw: dict[str, Any] = {"flights": [f.model_dump(mode="json", by_alias=True, exclude_unset=True) for f in self.flights],
                               "ground": world.flight_ground(), "start": self.start, "margin": self.margin, "path_samples": self.path_samples}
        if self.speedup is not None:
            raw["speedup"] = self.speedup
        name = world.flight_world()
        if name is not None:
            raw["world"] = name
        if world.land_spec is None:
            raw["at"] = world.place()
        return FlightData.model_validate(raw)


# ----- what a craft may be, and its effects ---------------------------------------------------------------


class Ramp(SceneParams):
    """A value that moves: ``{over: [start, end], from: 0, to: 1}`` (seconds or bars), eased; or a number."""

    header_synonyms = False
    over: list[Any]
    """[start, end] of the change (seconds or 'bar 9')."""
    from_: float = Field(default=0.0, alias="from")
    """The value before the start."""
    to: float = 1.0
    """The value after the end."""

    @model_validator(mode="after")
    def _check(self) -> "Ramp":
        if len(self.over) != 2:
            raise ValueError("a ramp's over must be [start, end]")
        for i, v in enumerate(self.over):
            scene_time(v, f"over[{i}]")
        return self


class EffectsSpec(SceneParams):
    """``effects:`` of a craft (vidgen/space-effects): ``reentry``, ``contrails``, ``exhaust``, ``vapour`` (each
    true or its options), ``quality``, ``seed``. In a surface scene they follow the craft's flight; in an
    orbital scene only ``exhaust`` (the bells' flame in vacuum)."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)
    header_synonyms = False
    reentry: bool | dict[str, Any] | None = None
    """The re-entry glow, shock layer, wake, sparks and far train: true or {full, level, shock, skin, wake, sparks, trail, head, thickness, length, persist}."""
    contrails: bool | dict[str, Any] | None = None
    """Vapour trails (above about 8 km; always: true for anywhere): true or {from, band, always, life, size, level, color}."""
    exhaust: bool | dict[str, Any] | None = None
    """The bells' flame in air: true or {level, air}."""
    vapour: bool | dict[str, Any] | None = None
    """A vapour cone near Mach 0.97 and mist over the wings in hard turns: true or {cone, wings, tips, level}."""
    quality: str = "standard"
    """fast, standard or fine."""
    seed: int | None = Field(default=None, ge=0)
    """Other sparks and flicker for every seed."""

    @model_validator(mode="after")
    def _check(self) -> "EffectsSpec":
        groups = air()["effects"]
        for key, keys in groups.items():
            value = getattr(self, key)
            if isinstance(value, dict):
                module_options(value, keys, f"effects.{key}", leave=("nozzles",))
        self.quality = one_of(self.quality, ["fast", "standard", "fine"], "effects quality")
        if not self.groups():
            raise ValueError("effects: give at least one of reentry, contrails, exhaust or vapour (true or its options)")
        return self

    def groups(self) -> dict[str, Any]:
        """The groups asked for, as the module takes them (camelCase keys)."""
        out: dict[str, Any] = {}
        for key in air()["effects"]:
            value = getattr(self, key)
            if value:
                out[key] = True if value is True else {camel(k): v for k, v in value.items()}
        return out


class ScaleRefSpec(SceneParams):
    """``scale_ref:`` of a hull: a small craft of the kit riding beside it, for size (``hull.scaleRef``):
    ``{kind: ship, at: hangar-1, gap: 120, seed, detail, into: {hangar, over}, escort: true}``."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)
    header_synonyms = False
    kind: str = "ship"
    """A craft of the kit: probe, satellite, station, ship, lander or tug."""
    at: str = "port"
    """Where it rides: a place on the hull (bow, stern, top, bottom, port, starboard, bridge, hangar-N, dock-N)."""
    gap: Any = None
    """Metres (or a length) off that place."""
    seed: int | None = Field(default=None, ge=0)
    """Another craft for every seed."""
    detail: str = "near"
    """near or far."""
    into: dict[str, Any] | None = None
    """Fly it into a bay: {hangar: hangar-2, over: [0, 10]} (needs dress: the bay's approach is the detail's)."""
    escort: bool = False
    """With a hull-reveal move: where the move puts it (it comes into the frame last, after the stern)."""

    @model_validator(mode="after")
    def _check(self) -> "ScaleRefSpec":
        self.kind = one_of(self.kind, list(space_names()["craft"]), "craft kind")
        self.at = hull_point(self.at, "scale_ref.at")
        self.detail = one_of(self.detail, space_names()["details"], "detail")
        if self.gap is not None:
            length(self.gap, "scale_ref.gap")
        if self.into is not None:
            module_options(self.into, ["hangar", "over"], "scale_ref.into")
            hull_point(str(self.into.get("hangar", "hangar-1")), "scale_ref.into.hangar")
            over = self.into.get("over")
            if not (isinstance(over, list) and len(over) == 2):
                raise ValueError("scale_ref.into.over must be [start, end] (seconds or 'bar N')")
            for i, v in enumerate(over):
                scene_time(v, f"scale_ref.into.over[{i}]")
        return self

    def options(self) -> dict[str, Any]:
        out: dict[str, Any] = {"at": self.at, "detail": self.detail}
        if self.gap is not None:
            out["gap"] = length(self.gap, "scale_ref.gap")
        if self.seed is not None:
            out["seed"] = self.seed
        return out


def check_dress(value: Any) -> Any:
    """``dress:`` of a hull (vidgen/space-hull-detail): true, false, or its options."""
    a = air()
    if isinstance(value, dict):
        module_options(value, a["dress_options"], "dress")
        for group, keys in a["dress_groups"].items():
            if isinstance(value.get(group), dict):
                module_options(value[group], keys, f"dress.{group}")
        if "plumes" in value:
            value["plumes"] = one_of(str(value["plumes"]), a["plume_modes"], "plume mode")
    return value


#: The parts of the craft kit a ``parts:`` tree may name (vidgen/space-craft's CraftKit methods), read at need.
def kit_parts() -> list[str]:
    return air()["kit_parts"]


def check_parts(node: Any, where: str = "parts") -> None:
    """A ``parts:`` tree: ``{part: hull, ...its options, attach: [{at: fore | {angle, along, out}, mount, roll, gap, part: dish, ...}]}``,
    or ``{around: {count, angle, span, along, out, mount, roll, gap}, part: solarWing, ...}`` among the attached."""
    if not isinstance(node, dict):
        raise ValueError(f"{where}: a part is {{part: NAME, ...its options}}, got {node!r}")
    if "part" not in node:
        raise ValueError(f"{where}: give part: one of {', '.join(kit_parts())}")
    name = str(node["part"])
    if name not in kit_parts():
        name = one_of(camel(name.replace("-", "_")), kit_parts(), "part")
        node["part"] = name
    for key in ("at", "mount", "roll", "gap", "around"):
        if key in node and where == "parts":
            raise ValueError(f"parts: the first part is the craft's root: it takes no {key}")
    if "around" in node:
        module_options(node["around"], ["count", "angle", "span", "along", "out", "mount", "roll", "gap"], f"{where}.around")
        if "at" in node:
            raise ValueError(f"{where}: give at (one place) or around (a ring of copies), not both")
    attached = node.get("attach") or []
    if not isinstance(attached, list):
        raise ValueError(f"{where}.attach must be a list of parts")
    for i, child in enumerate(attached):
        check_parts(child, f"{where}.attach[{i}]")
        if "at" not in child and "around" not in child:
            raise ValueError(f"{where}.attach[{i}]: give at (fore, aft, port, starboard, zenith, nadir, tip, ... or {{angle, along, out}}) or around")


def part_options(node: dict[str, Any]) -> dict[str, Any]:
    """A part's own options (camelCase): everything but the tree's words."""
    return {camel(k): v for k, v in node.items() if k not in ("part", "attach", "at", "mount", "roll", "gap", "around")}


class FlashSpec(SceneParams):
    """A flash on a cut (``flash:``; vidgen/space-camera's flashCut through three-finish): the light rises over
    ``rise`` seconds before ``at`` to ``amount`` and falls over ``fall`` after it. Give the same ``at`` (a bar
    line) to the scene before the cut and the scene after it: the light is one curve across the cut."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)
    header_synonyms = False
    at: Any
    """The cut: seconds of the scene or 'bar 9' (may be the scene's end or its start)."""
    amount: float = Field(default=3.0, gt=0, le=100)
    """How bright at the cut (three-finish's flash: a share of white added)."""
    rise: float = Field(default=0.25, gt=0, le=10)
    """Seconds it rises over before the cut."""
    fall: float = Field(default=0.6, gt=0, le=10)
    """Seconds it falls over after the cut."""

    @model_validator(mode="before")
    @classmethod
    def _short(cls, value: Any) -> Any:
        return {"at": value} if isinstance(value, (int, float, str)) and not isinstance(value, bool) else value

    @model_validator(mode="after")
    def _check(self) -> "FlashSpec":
        scene_time(self.at, "flash.at")
        return self


__all__ = ["HULL_NEAR", "HULL_POINTS", "MIN_STANDOFF", "MOVE_LENGTHS", "NEEDS", "TIME_OPTIONS", "CloudSpec", "EffectsSpec", "FlashSpec", "FlightsSpec",
           "LandSpec", "LightningSpec", "Ramp", "ScaleRefSpec", "SeaSpec", "SunPlace", "WorldSpec", "air", "air_move_names", "camel_move",
           "check_dress", "check_parts", "hull_point", "kebab", "kit_parts", "move_option_list", "part_options", "ship_move_names", "sun_of_date"]
