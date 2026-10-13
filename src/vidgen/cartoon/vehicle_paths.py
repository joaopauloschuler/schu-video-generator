"""Where the water and air vehicles go (DESIGN.md §69.53), worked out without manim: the water's
waves and a boat bobbing on them, a hot-air balloon's flight and a toy rocket's launch, and the
rocket's smoke.

Every function is pure: values depend only on the arguments (a seed for anything random), never on
frames drawn before, so a storyboard still or a seek shows the same. Lengths on screen are Manim
units (x right, y up); lengths of the water are in a character's heights (``unit``: one
character height in Manim units at the front of the stage); angles are degrees counterclockwise.

A flight is a :class:`Course` from the vehicle's feet at the start to its feet at the end; its
point at a share (0..1) of its time is :meth:`Course.at`: where the feet are and how far the
vehicle is turned about them.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from vidgen.cartoon.acting import walk_progress
from vidgen.cartoon.idle import idle_seed
from vidgen.cartoon.motion import smoothstep
from vidgen.cartoon.motion_effects import SMOKE_BURN_SHARE, SMOKE_SECONDS, Puff
from vidgen.cartoon.vehicles import ROCKET_ASCENT_SHARE, VEHICLES

# ----- water -------------------------------------------------------------------------------------

#: The water's colour (fixed: no theme token is a water blue in every theme) and its crests'.
WATER_COLOR = "#4C9BD6"
CREST_COLOR = "#BFE3F7"
#: How far the water's surface is above the ground line, in a character's heights: a boat's keel
#: sits on the ground line, this deep under the water.
WATERLINE = 0.12
#: The front strip of water (drawn in front of the boats, over their keels) ends this far under the
#: surface, in a character's heights.
FRONT_DROP = 0.05
#: The waves: the distance between two crests and their height (character heights), how fast they
#: drift (character heights per second, with the wind's way when it blows, else to the right).
WAVE_LENGTH = 0.9
WAVE_HEIGHT = 0.035
WAVE_SPEED = 0.25
#: A boat bobs this high (character heights) once every ``BOB_SECONDS`` and rocks ``BOB_DEGREES``.
BOB_HEIGHT = 0.025
BOB_SECONDS = 2.4
BOB_DEGREES = 2.5


def wave_offset(x: float, seconds: float, sign: float = 1.0) -> float:
    """How far (character heights) the water's surface is above its level at ``x`` (character
    heights from the stage's middle) at ``seconds``: two sines drifting the way ``sign`` says (+1
    right, -1 left), no more than :data:`WAVE_HEIGHT`."""
    k = 2.0 * math.pi / WAVE_LENGTH
    drift = sign * WAVE_SPEED * seconds
    return WAVE_HEIGHT * (0.6 * math.sin(k * (x - drift)) + 0.4 * math.sin(1.7 * k * (x - 0.8 * drift) + 1.1))


def front_outline(left: float, right: float, surface: float, bottom: float, seconds: float, unit: float, *,
                  sign: float = 1.0, steps: int = 48) -> list[tuple[float, float]]:
    """The front strip of water from x ``left`` to ``right`` (Manim units): its wavy top
    :data:`FRONT_DROP` under the ``surface`` y (by :func:`wave_offset` at ``seconds``), down to
    ``bottom``; corners counterclockwise from the bottom left. ``unit``: a character's height."""
    top = surface - FRONT_DROP * unit
    edge = [
        (left + (right - left) * k / steps, top + unit * wave_offset((left + (right - left) * k / steps) / unit, seconds, sign))
        for k in range(steps + 1)
    ] if unit > 0 else [(left, top), (right, top)]
    return [(left, bottom), (right, bottom), *reversed(edge)]


def boat_bob(seconds: float, phase: float = 0.0) -> tuple[float, float]:
    """A boat on the water at ``seconds``: how far its keel is above its rest (character heights)
    and how far it rocks (degrees), shifted by ``phase`` (radians) so two boats do not bob in step."""
    rise = BOB_HEIGHT * math.sin(2.0 * math.pi * seconds / BOB_SECONDS + phase)
    rock = BOB_DEGREES * math.sin(2.0 * math.pi * seconds / (1.3 * BOB_SECONDS) + phase + 1.0)
    return rise, rock


def bob_phase(name: str) -> float:
    """A phase (radians) from a boat's name."""
    return 2.0 * math.pi * (idle_seed(name) / float(1 << 32))


# ----- the hot-air balloon ---------------------------------------------------------------------

#: How high a balloon rises above where it set off (frame heights; the scene keeps its top in the
#: frame), the share of a flight it spends rising (and as much landing).
BALLOON_ALTITUDE = 0.3
BALLOON_RISE_SHARE = 0.3
#: How far the wind blows it aside on the way, at wind level 1 (character heights, downwind; the
#: bulge is largest half-way and it still lands where it was sent).
BALLOON_DRIFT = 1.2
#: Its gentle float up and down while it cruises: a share of the altitude, and how many times.
BALLOON_FLOAT = 0.05
BALLOON_FLOATS = 2.0


def balloon_point(share: float, start: tuple[float, float], end: tuple[float, float], *, altitude: float,
                  drift: float = 0.0, land: bool = True, seed: int = 1) -> tuple[float, float, float]:
    """A balloon's feet (x, y) and turn (degrees, 0: it hangs upright) at ``share`` (0..1) of its
    flight from ``start`` to ``end`` (its feet on screen): it rises ``altitude`` units over
    :data:`BALLOON_RISE_SHARE` of the time while it starts across, cruises with a gentle seeded
    float, and comes down over as long to land at ``end`` (``land: false``: it keeps rising to
    ``end``, above the frame). ``drift`` (signed units) bows the way aside, most half-way."""
    s = min(max(float(share), 0.0), 1.0)
    (x0, y0), (x1, y1) = start, end
    r = BALLOON_RISE_SHARE
    phase = 2.0 * math.pi * (idle_seed(str(seed)) / float(1 << 32))
    if land:
        lift = smoothstep(s / r) - smoothstep((s - 1.0 + r) / r)
        along = smoothstep((s - 0.5 * r) / (1.0 - r))
        y = y0 + (y1 - y0) * along + altitude * lift
    else:   # up to its altitude, then on up faster and faster to the end
        lift = smoothstep(s / r)
        along = s
        y = y0 + altitude * lift + (y1 - y0 - altitude) * (max(s - r, 0.0) / (1.0 - r)) ** 2
    y += altitude * BALLOON_FLOAT * math.sin(2.0 * math.pi * BALLOON_FLOATS * s + phase) * lift * math.sin(math.pi * s)
    x = x0 + (x1 - x0) * along + drift * math.sin(math.pi * s)
    return x, y, 0.0


def balloon_seconds(distance: float, altitude: float, speed: float) -> float:
    """How long a balloon takes to fly ``distance`` units across and up and down ``altitude`` at
    ``speed`` units per second."""
    return (abs(distance) + 2.0 * abs(altitude)) / speed if speed > 0 else 0.0


# ----- the toy rocket --------------------------------------------------------------------------

#: How high a toy rocket's arc goes above where it set off (frame heights; the scene keeps it in
#: the frame) and the share of the way across it covers going up (over
#: :data:`~vidgen.cartoon.vehicles.ROCKET_ASCENT_SHARE` of the time); then its parachute opens
#: and it floats down.
ROCKET_APEX = 0.45
ROCKET_ASCENT_ACROSS = 0.5
#: Under its parachute it turns upright over this share of the way down and sways at most this
#: much (degrees), less and less until it lands.
CHUTE_TURN = 0.25
CHUTE_SWAY = 9.0
#: It leaves the ground upright and leans into its arc over this share of the way up.
LIFT_OFF_SHARE = 0.3
#: Seconds a launch takes before its length (its path at the rocket's speed is added): landing
#: (most of it floating down) or flying away out of the frame.
ROCKET_LAND_SECONDS = 1.8
ROCKET_AWAY_SECONDS = 0.6


def _tangent_degrees(dx: float, dy: float) -> float:
    """The turn (degrees, counterclockwise from upright) of a rocket whose nose points along
    (``dx``, ``dy``)."""
    return -math.degrees(math.atan2(dx, dy)) if abs(dx) + abs(dy) > 1e-12 else 0.0


def _rocket_up(v: float, start: tuple[float, float], across: float, apex: float) -> tuple[float, float]:
    """The way up (``v`` 0..1): ``across`` units sideways, an arc to ``apex`` above the start,
    flat at the top."""
    return start[0] + across * v, start[1] + apex * (2.0 * v - v * v)


def rocket_point(share: float, start: tuple[float, float], end: tuple[float, float], *, apex: float,
                 land: bool = True, seed: int = 1) -> tuple[float, float, float]:
    """A toy rocket's feet (its tail: x, y) and turn (degrees, 0: nose up) at ``share`` (0..1) of
    its flight from ``start`` to ``end``. Landing: it shoots up an arc ``apex`` units high over
    :data:`ROCKET_ASCENT_SHARE` of the time (slowing to the top, its nose along the way), then
    floats down under its parachute to ``end``, turning upright and swaying less and less, and
    touches down slowly. ``land: false``: it speeds up along a curve to ``end`` (above the frame),
    its nose along the way. Pure; ``seed`` sets the sway."""
    s = min(max(float(share), 0.0), 1.0)
    (x0, y0), (x1, y1) = start, end
    if not land:   # x = x0 + dx v², y = y0 + dy v: straight up at first, bending towards end
        v = s ** 1.6
        return x0 + (x1 - x0) * v * v, y0 + (y1 - y0) * v, _tangent_degrees(2.0 * (x1 - x0) * v, y1 - y0)
    across = ROCKET_ASCENT_ACROSS * (x1 - x0)
    if s <= ROCKET_ASCENT_SHARE:
        u = s / ROCKET_ASCENT_SHARE
        v = 1.0 - (1.0 - u) ** 2   # slowing to the top
        x, y = _rocket_up(v, start, across, apex)
        return x, y, _tangent_degrees(across, apex * (2.0 - 2.0 * v)) * smoothstep(u / LIFT_OFF_SHARE)
    w = (s - ROCKET_ASCENT_SHARE) / (1.0 - ROCKET_ASCENT_SHARE)
    top_x, top_y = _rocket_up(1.0, start, across, apex)
    down = smoothstep(w)
    x = top_x + (x1 - top_x) * down
    y = top_y + (y1 - top_y) * down
    level = _tangent_degrees(across, 0.0)
    phase = 2.0 * math.pi * (idle_seed(str(seed)) / float(1 << 32))
    sway = CHUTE_SWAY * math.sin(2.0 * math.pi * 1.5 * w + phase) * (1.0 - w)
    turned = smoothstep(w / CHUTE_TURN)
    return x, y, level * (1.0 - turned) + sway * turned


def chute_open(share: float, land: bool) -> bool:
    """Whether a toy rocket's parachute is open at ``share`` of a flight (from the top of a landing
    flight on; never when it flies away)."""
    return land and share > ROCKET_ASCENT_SHARE


def rocket_seconds(distance: float, apex: float, speed: float, land: bool = True) -> float:
    """How long a toy rocket's flight takes: :data:`ROCKET_LAND_SECONDS` (or
    :data:`ROCKET_AWAY_SECONDS`) plus its way (``distance`` across, up and down ``apex``) at
    ``speed`` units per second."""
    length = abs(distance) + (2.0 if land else 1.0) * abs(apex)
    return (ROCKET_LAND_SECONDS if land else ROCKET_AWAY_SECONDS) + (length / speed if speed > 0 else 0.0)


# ----- a flight ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Course:
    """A vehicle's way: its ``kind``, its feet at the ``start`` and the ``end`` (Manim units), how
    high it goes (``rise``: a balloon's altitude, a rocket's apex, units), a balloon's ``drift``
    aside (signed units), whether it ``land`` s (else it flies away above the frame), and a
    ``seed``. A ground or water vehicle goes straight along, speeding up and slowing down like a
    walk (:func:`~vidgen.cartoon.acting.walk_progress`)."""

    kind: str
    start: tuple[float, float]
    end: tuple[float, float]
    rise: float = 0.0
    drift: float = 0.0
    land: bool = True
    seed: int = 1

    def at(self, share: float) -> tuple[float, float, float]:
        """The feet (x, y) and the turn (degrees) at ``share`` (0..1) of its time."""
        if self.kind == "hot_air_balloon":
            return balloon_point(share, self.start, self.end, altitude=self.rise, drift=self.drift, land=self.land, seed=self.seed)
        if self.kind == "toy_rocket":
            return rocket_point(share, self.start, self.end, apex=self.rise, land=self.land, seed=self.seed)
        g = walk_progress(share)
        return self.start[0] + (self.end[0] - self.start[0]) * g, self.start[1] + (self.end[1] - self.start[1]) * g, 0.0

    @property
    def flies(self) -> bool:
        """Whether it leaves the ground (or the water) on the way."""
        return VEHICLES[self.kind].medium == "air"

    def powered(self) -> float:
        """The share of its time a toy rocket's motor burns (smoke comes out): up to the top of a
        landing flight, most of a flight away; 0 for the others."""
        if self.kind != "toy_rocket":
            return 0.0
        return ROCKET_ASCENT_SHARE if self.land else SMOKE_BURN_SHARE


# ----- smoke -----------------------------------------------------------------------------------

#: How many puffs a launch's smoke trail has, and its burst on the ground at the start (each lasts
#: :data:`~vidgen.cartoon.motion_effects.SMOKE_SECONDS`).
SMOKE_TRAIL = 12
SMOKE_BURST = 6


def smoke_puffs(age: float, course: Course, seconds: float, size: float, seed: int = 1) -> list[Puff]:
    """A toy rocket's smoke ``age`` seconds after it set off on ``course`` (taking ``seconds``),
    the rocket ``size`` units tall: a burst of :data:`SMOKE_BURST` puffs rolling out both ways on
    the ground where it set off, then a trail of :data:`SMOKE_TRAIL` puffs left where its tail was
    while the motor burns (:meth:`Course.powered`); each grows and fades over
    :data:`SMOKE_SECONDS`. Puffs in Manim units (``x``, ``y``, ``radius``) with their opacity."""
    rng = random.Random(seed)
    puffs: list[Puff] = []
    x0, y0 = course.start
    for k in range(SMOKE_BURST):
        side = -1.0 if k % 2 else 1.0
        spread, radius, delay = rng.uniform(0.4, 1.0), rng.uniform(0.18, 0.28), rng.uniform(0.0, 0.12)
        u = (age - delay) / SMOKE_SECONDS
        if 0.0 < u < 1.0:
            out = 1.0 - (1.0 - u) ** 2
            r = size * radius * (0.5 + 0.8 * out)
            puffs.append(Puff(x0 + side * size * spread * out, y0 + 0.7 * r, r, 0.9 * (1.0 - smoothstep((u - 0.3) / 0.7))))
    burning = course.powered() * seconds
    for k in range(SMOKE_TRAIL):
        born = burning * (k + 0.5) / SMOKE_TRAIL
        u = (age - born) / SMOKE_SECONDS
        radius, jitter = rng.uniform(0.1, 0.17), (rng.uniform(-0.15, 0.15), rng.uniform(-0.1, 0.1))
        if burning <= 0.0 or not 0.0 < u < 1.0:
            continue
        x, y, _ = course.at(born / seconds if seconds > 0 else 0.0)
        r = size * radius * (0.6 + 0.9 * (1.0 - (1.0 - u) ** 2))
        puffs.append(Puff(x + size * jitter[0], y + size * jitter[1] + 0.2 * size * u, r, 0.8 * (1.0 - smoothstep((u - 0.2) / 0.8))))
    return puffs


def smoke_seconds(course: Course, seconds: float) -> float:
    """How long a launch's smoke lasts after the rocket set off (its last puff fades)."""
    return course.powered() * seconds + SMOKE_SECONDS + 0.12


__all__ = [
    "BALLOON_ALTITUDE",
    "BALLOON_DRIFT",
    "CREST_COLOR",
    "Course",
    "ROCKET_APEX",
    "SMOKE_BURST",
    "SMOKE_TRAIL",
    "WATERLINE",
    "WATER_COLOR",
    "balloon_point",
    "balloon_seconds",
    "boat_bob",
    "bob_phase",
    "chute_open",
    "front_outline",
    "rocket_point",
    "rocket_seconds",
    "smoke_puffs",
    "smoke_seconds",
    "wave_offset",
]
