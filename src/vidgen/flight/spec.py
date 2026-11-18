"""A flight in words (Step 385, DESIGN.md §123.7): where it starts and the legs it flies, in the
spirit of the ``orbit`` scene's vocabulary. Units: metres, metres per second, seconds, degrees
(headings from north towards east; a bank or a turn ``by`` positive to the right). Times are
flight seconds (``for``) or times of the scene (``until``, ``at``: seconds or 'bar 9 beat 3',
resolved by the caller). Every model refuses unknown keys (with a did-you-mean in ``vidgen
validate``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Time = float | str


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)


class Place(_Model):
    """A place: local metres (x east, z south of the scene's anchor) or latitude and longitude (degrees)."""

    x: float | None = None
    """Metres east of the scene's anchor (with z)."""
    z: float | None = None
    """Metres south of the scene's anchor (with x)."""
    lat: float | None = Field(default=None, ge=-90, le=90)
    """Latitude, degrees (with lon), instead of x and z."""
    lon: float | None = Field(default=None, ge=-360, le=360)
    """East longitude, degrees (with lat)."""

    @model_validator(mode="before")
    @classmethod
    def _pair(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise ValueError(f"a place is [x, z] (metres east and south of the anchor) or {{lat, lon}}, got {list(value)}")
            return {"x": value[0], "z": value[1]}
        return value

    @model_validator(mode="after")
    def _one_way(self) -> "Place":
        _check_place(self)
        return self


def _check_place(place: Any) -> None:
    local, globe = place.x is not None or place.z is not None, place.lat is not None or place.lon is not None
    if local == globe:
        raise ValueError("give a place as x and z (metres east and south of the anchor) or as lat and lon (degrees), one of the two")
    if local and (place.x is None or place.z is None):
        raise ValueError("a place in metres needs both x and z")
    if globe and (place.lat is None or place.lon is None):
        raise ValueError("a place on the globe needs both lat and lon")


class Start(_Model):
    """Where and how a flight starts: a place, a height, a heading and a speed; or ``orbit``: a body
    of the scene's ``orbit_data`` at a time (its position and velocity)."""

    x: float | None = None
    """Metres east of the scene's anchor (with z)."""
    z: float | None = None
    """Metres south of the scene's anchor (with x)."""
    lat: float | None = Field(default=None, ge=-90, le=90)
    """Latitude, degrees (with lon), instead of x and z."""
    lon: float | None = Field(default=None, ge=-360, le=360)
    """East longitude, degrees (with lat)."""
    height: float | None = None
    """Metres over the world's sphere (sea level)."""
    above_ground: float | None = Field(default=None, ge=0)
    """Metres over the ground there, instead of height."""
    heading: float = 0.0
    """Degrees from north towards east."""
    speed: float | None = Field(default=None, ge=0)
    """Air speed, m/s (the air is at rest with the ground)."""
    climb: float = 0.0
    """Vertical rate at the start, m/s (positive up)."""
    orbit: str | None = None
    """A body of the scene's orbit_data: the flight starts where it is, as fast as it moves (a re-entry)."""
    at: Time | None = None
    """With orbit: the time of the scene the flight takes over (seconds or 'bar 9 beat 3'; default the flight's start)."""

    @model_validator(mode="after")
    def _start(self) -> "Start":
        if self.orbit is not None:
            given = [k for k in ("x", "z", "lat", "lon", "height", "above_ground", "speed") if getattr(self, k) is not None]
            if given:
                raise ValueError(f"start: with orbit the place, height and speed are the orbit's; leave out {', '.join(given)}")
            return self
        if self.at is not None:
            raise ValueError("start.at goes with orbit (the time the flight takes over from the orbit data)")
        if self.x is None and self.z is None and self.lat is None and self.lon is None:
            self.x, self.z = 0.0, 0.0
        _check_place(self)
        if (self.height is None) == (self.above_ground is None):
            raise ValueError("start: give height (metres over sea level) or above_ground (metres over the ground there), one of the two")
        if self.speed is None:
            raise ValueError("start: give the speed (m/s)")
        return self


class Turn(_Model):
    """A coordinated turn: to a heading or by an angle, with a bank angle or a turn radius."""

    to: float | None = None
    """The heading to turn to, degrees from north."""
    by: float | None = None
    """The angle to turn by, degrees (positive to the right; 720: twice round)."""
    side: Literal["left", "right", "shorter"] = "shorter"
    """With to: which way round."""
    bank: float | None = Field(default=None, gt=0, lt=85)
    """The bank angle, degrees (default 30)."""
    radius: float | None = Field(default=None, gt=0)
    """The turn's radius, metres, instead of bank (bank = atan(v² / (g r)))."""
    roll_rate: float | None = Field(default=None, gt=0)
    """The greatest roll rate going into and out of the turn, degrees a second (default the flight's)."""

    @model_validator(mode="after")
    def _what(self) -> "Turn":
        if (self.to is None) == (self.by is None):
            raise ValueError("turn: give to (a heading) or by (an angle), one of the two")
        if self.bank is not None and self.radius is not None:
            raise ValueError("turn: give bank or radius, not both")
        return self


class Circle(_Model):
    """Circling a place (a peak, a ship): in on a smooth curve, round ``turns`` times, out level."""

    around: Place
    """The place circled: [x, z] or {lat, lon}."""
    radius: float = Field(gt=0)
    """The circle's radius over the ground, metres."""
    turns: float = Field(default=1.0, gt=0)
    """How many times round."""
    side: Literal["left", "right"] = "left"
    """left: anticlockwise seen from above; right: clockwise."""


class Waypoints(_Model):
    """A smooth curve through places (its curvature bounded: the bank it needs is checked)."""

    points: list[Place] = Field(min_length=1)
    """The places, in order: [[x, z], ...] or [{lat, lon}, ...]."""
    bank_limit: float | None = Field(default=None, gt=0, lt=85)
    """The most bank the curve may need, degrees (default the flight's)."""

    @model_validator(mode="before")
    @classmethod
    def _list(cls, value: Any) -> Any:
        return {"points": value} if isinstance(value, list) else value


class Climb(_Model):
    """A climb (or with ``descend:`` a descent) to a height, by an amount, or at a rate."""

    to: float | None = None
    """The height to climb to, metres over sea level."""
    by: float | None = None
    """Metres to climb by."""
    rate: float | None = Field(default=None, gt=0)
    """Vertical speed, m/s (default 10; alone: climb at it until another leg changes it)."""
    accel: float | None = Field(default=None, gt=0)
    """The greatest vertical acceleration going into and out of it, in g (default the flight's)."""

    @model_validator(mode="after")
    def _what(self) -> "Climb":
        if self.to is not None and self.by is not None:
            raise ValueError("give to or by, not both")
        if self.to is None and self.by is None and self.rate is None:
            raise ValueError("give to (a height), by (metres) or rate (m/s)")
        return self


class Follow(_Model):
    """Terrain following: as low as ``clearance`` over the ground, looking ahead, with the vertical
    acceleration held (a push-over never under ``push`` g of lift, a climb rate at most ``rate``)."""

    clearance: float = Field(gt=0)
    """Metres over the ground."""
    rate: float | None = Field(default=None, gt=0)
    """The greatest vertical speed, m/s (default 30 % of the speed)."""
    push: float = Field(default=0.5, ge=0, lt=1)
    """The least load factor in a push-over, in g (0.5: the vertical acceleration is at most -0.5 g)."""
    smoothing: float = Field(default=4.0, gt=0)
    """Half-width of the smoothing, seconds (wider: gentler pull-ups, more height over valleys)."""


class Speed(_Model):
    """A change of air speed."""

    to: float | None = Field(default=None, gt=0)
    """The new speed, m/s."""
    mach: float | None = Field(default=None, gt=0)
    """The new speed as a Mach number (the air's speed of sound), instead of to."""
    rate: float | None = Field(default=None, gt=0)
    """Mean acceleration, m/s² (default the flight's)."""

    @model_validator(mode="before")
    @classmethod
    def _number(cls, value: Any) -> Any:
        return {"to": value} if isinstance(value, (int, float)) and not isinstance(value, bool) else value

    @model_validator(mode="after")
    def _what(self) -> "Speed":
        if (self.to is None) == (self.mach is None):
            raise ValueError("speed: give to (m/s) or mach, one of the two")
        return self


class Landing(_Model):
    """An approach and flare to height 0 on level ground or the sea, then a roll-out (or a stop on the water)."""

    glide: float = Field(default=3.0, gt=0, lt=20)
    """The glide slope, degrees."""
    flare: float = Field(default=15.0, gt=0)
    """The height the flare starts at, metres (the sink rate falls to zero by the ground)."""
    touchdown: float | None = Field(default=None, gt=0)
    """The speed at touchdown, m/s (default 80 % of the speed when the approach starts)."""
    brake: float = Field(default=2.5, gt=0)
    """Mean deceleration on the ground, m/s² (to a stop)."""


class Reentry(_Model):
    """From orbit down to flight: a shaped descent (a look, stated) — the orbit's own motion blended
    into an equilibrium glide in the air's exponential atmosphere, then into the level flight state ``to``."""

    to: dict[str, float]
    """The flight state at the end: {height: metres over sea level, speed: m/s}."""
    lift_to_drag: float = Field(default=1.2, gt=0.1, le=10)
    """Lift over drag in the glide."""
    loading: float = Field(default=450.0, gt=1)
    """Mass over lift coefficient times wing area, kg/m² (sets the glide's height for a speed)."""
    blend: float = Field(default=600.0, gt=0)
    """Seconds from the orbit's own motion to the glide (the descent into the air)."""
    end: float | None = Field(default=None, gt=0)
    """Seconds of the last part, from the glide to the level state (default from the height to lose)."""
    bank: float = Field(default=60.0, ge=0, lt=85)
    """The bank of the S-turns, degrees (a look)."""
    reversals: int = Field(default=3, ge=0, le=20)
    """Bank reversals in the glide."""
    reversal: float = Field(default=20.0, gt=0)
    """Seconds a reversal takes."""
    aoa: float = Field(default=40.0, ge=0, lt=80)
    """The nose over the air's direction during the entry, degrees (a look; it falls to the cruise's in the last part)."""

    @model_validator(mode="after")
    def _to(self) -> "Reentry":
        unknown = [k for k in self.to if k not in ("height", "speed")]
        if unknown or "height" not in self.to or "speed" not in self.to:
            raise ValueError("reentry.to is {height: metres over sea level, speed: m/s}")
        if self.to["speed"] <= 0 or self.to["height"] < 0:
            raise ValueError("reentry.to: the speed must be over 0 and the height 0 or more")
        return self


class Leg(_Model):
    """One leg: at most one horizontal manoeuvre (turn, circle, waypoints), one vertical one (climb,
    descend, level, follow), a speed change, or a landing or a re-entry; it lasts ``for`` seconds,
    ``until`` a time of the scene, or as long as its manoeuvres need. What a leg does not name is
    held: wings level, the vertical rate, the speed."""

    straight: float | None = Field(default=None, gt=0)
    """Fly straight on for this many seconds (the same as for: with nothing else)."""
    turn: Turn | None = None
    """A coordinated turn: {to: 180, bank: 30} or {by: -90, radius: 3000}."""
    circle: Circle | None = None
    """Circle a place: {around: [x, z], radius: 4000, turns: 1}."""
    waypoints: Waypoints | None = None
    """A smooth curve through places: [[x, z], ...] or {points: [...], bank_limit: 45}."""
    climb: Climb | None = None
    """{to: 3000, rate: 10}, {by: 500}, {rate: 5}."""
    descend: Climb | None = None
    """{to: 800}, {by: 500, rate: 8}, {rate: 3}."""
    level: bool = False
    """true: level off (the vertical rate to zero)."""
    follow: Follow | None = None
    """Terrain following: {clearance: 300}."""
    speed: Speed | None = None
    """{to: 200} (or 200), {mach: 0.8}, with rate (m/s², mean)."""
    land: Landing | None = None
    """An approach, flare and roll-out: {glide: 3, flare: 15, touchdown: 70}."""
    reentry: Reentry | None = None
    """Only as the first leg: from orbit down to {to: {height, speed}}."""
    for_: float | None = Field(default=None, alias="for", gt=0)
    """How long the leg lasts, seconds of the flight."""
    until: Time | None = None
    """When the leg ends: a time of the scene (seconds or 'bar 9 beat 3')."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True, populate_by_name=True)

    @model_validator(mode="after")
    def _consistent(self) -> "Leg":
        horizontal = [k for k in ("turn", "circle", "waypoints") if getattr(self, k) is not None]
        vertical = [k for k in ("climb", "descend", "follow") if getattr(self, k) is not None] + (["level"] if self.level else [])
        if len(horizontal) > 1:
            raise ValueError(f"a leg has one horizontal manoeuvre; got {' and '.join(horizontal)}: give them as legs one after another")
        if len(vertical) > 1:
            raise ValueError(f"a leg has one vertical manoeuvre; got {' and '.join(vertical)}")
        given = [k for k in ("straight", "for_", "until") if getattr(self, k) is not None]
        if len(given) > 1:
            raise ValueError("give one of straight, for and until")
        special = [k for k in ("land", "reentry") if getattr(self, k) is not None]
        if special and (horizontal or vertical or self.speed is not None or len(special) > 1):
            raise ValueError(f"{special[0]} is a leg of its own (no other manoeuvre with it)")
        if self.straight is not None and horizontal:
            raise ValueError("straight is a leg without a turn")
        if not (horizontal or vertical or special or self.speed is not None or given):
            raise ValueError("a leg needs a manoeuvre (turn, circle, waypoints, climb, descend, level, follow, speed, land, reentry) or a length (straight, for, until)")
        return self


class Flight(_Model):
    """One flight: a name for the page, where it starts, its legs and how it flies."""

    name: str
    """The name the page reads it by (ctx.flight.position(name, t))."""
    start: Start
    """Where and how it starts: {x, z | lat, lon, height | above_ground, heading, speed}, or {orbit: Ship, at: 12}."""
    legs: list[Leg] = Field(default_factory=list)
    """The legs, in order."""
    roll_rate: float = Field(default=20.0, gt=0)
    """The greatest roll rate into and out of turns, degrees a second."""
    accel: float = Field(default=2.0, gt=0)
    """Mean acceleration of a speed change, m/s²."""
    vertical_accel: float = Field(default=0.25, gt=0)
    """The greatest vertical acceleration going into and out of a climb or descent, in g."""
    bank_limit: float = Field(default=60.0, gt=0, lt=85)
    """The most bank a curve through waypoints or round a circle may need, degrees (more is an error)."""
    max_load: float = Field(default=3.0, gt=0)
    """A warning when the load factor (lift over weight) goes over it."""
    aoa: float = Field(default=3.0, ge=0, lt=30)
    """The nose over the air's direction per g of lift, degrees (a look)."""
    lift: bool = False
    """true: where the path would come too near the ground, raise it there (terrain following), instead of an error."""


__all__ = ["Circle", "Climb", "Flight", "Follow", "Landing", "Leg", "Place", "Reentry", "Speed", "Start", "Time", "Turn", "Waypoints"]
