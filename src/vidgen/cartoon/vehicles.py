"""Vehicles (DESIGN.md §69.52, §69.53): a bicycle, a car and a bus on the ground, a boat on the
water, a hot-air balloon and a toy rocket in the air. No manim.

A vehicle is a built-in prop (:mod:`vidgen.cartoon.props` draws it) with seats, wheels that turn
and, on a bicycle, pedals. Its geometry is in *prop units*, as for every prop: the origin at the
middle of its foot, ``y`` up, the top at 1, as drawn facing right (the front on the right). Where
it goes is its :attr:`VehicleSpec.medium`; the water and air paths are in
:mod:`vidgen.cartoon.vehicle_paths`.

- a *seat* is where a rider sits: the x of its hips and the y of the seat line, and the *floor*
  under it, where the rider's feet rest (a car's and a bus's floor is above the ground and behind
  the vehicle's side, so the lower body is hidden by it; a bicycle's rider pedals, its feet on the
  pedals);
- wheels turn by the distance the vehicle goes (:func:`wheel_degrees`), a bicycle's cranks by
  that over :data:`GEAR` (:func:`crank_degrees`), and its pedals are where they turn
  (:func:`pedal_points`).

Who rides what is a :class:`~vidgen.cartoon.seating.Postures` (``ride``, ``get_out``); a ride's
time is a walk's (:func:`~vidgen.cartoon.acting.walk_seconds`: it speeds up and slows down) at
the vehicle's speed (:data:`RIDE_SPEEDS`), and a ride in depth goes as far as a walk in depth
(:func:`~vidgen.cartoon.stage.depth_walk_distance`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: The built-in vehicles on the ground, on the water and in the air, and all of them.
GROUND_VEHICLES: tuple[str, ...] = ("bicycle", "car", "bus")
WATER_VEHICLES: tuple[str, ...] = ("boat",)
AIR_VEHICLES: tuple[str, ...] = ("hot_air_balloon", "toy_rocket")
VEHICLE_KINDS: tuple[str, ...] = (*GROUND_VEHICLES, *WATER_VEHICLES, *AIR_VEHICLES)
#: The actions that put riders in a vehicle, move it, and take them out.
RIDING_ACTIONS: frozenset[str] = frozenset({"get_in", "ride_to", "get_out"})
#: How far beyond a vehicle's end (in the rider's heights) a character can get in without
#: walking first.
GET_IN_REACH = 0.5
#: Seconds of ``get_in`` and ``get_out``.
GET_IN_SECONDS = 1.0
GET_OUT_SECONDS = 0.9
#: A bicycle's cranks turn once for every ``GEAR`` turns of its wheels.
GEAR = 2.0
#: How far a bicycle's rider leans forward (degrees) to reach the handlebar.
CYCLING_LEAN = 14.0
#: The share of a toy rocket's landing flight it spends shooting up; its parachute opens then
#: (:mod:`vidgen.cartoon.vehicle_paths`; its foley pops then).
ROCKET_ASCENT_SHARE = 0.3


@dataclass(frozen=True)
class VehicleSpec:
    """One vehicle's geometry, in prop units as drawn facing right: its ``height`` next to a
    character (the stage's ``size``); its ``seats`` (each place's hips ``x``, front first), the
    ``seat`` line's y and the ``floor`` under the riders' feet; its ``wheels`` ((x, y, radius)
    each); ``half_length`` (from its middle to either end); a bicycle's ``crank`` ((x, y,
    radius): where its pedals turn) and ``grip`` (the handlebar, where the rider's hands go);
    ``hides_legs``: riders sit behind its side (a car, a bus: drawn before it), else on it (a
    bicycle: drawn after it); ``speed``: units per second (the frame's shorter side is 8);
    ``bell``: it rings a bell when it sets off (else its engine starts); ``medium``: where it goes
    (``ground``, ``water`` or ``air``, DESIGN.md §69.53); ``stands``: its riders stand on the floor
    (a balloon's basket) instead of sitting on the seat line."""

    height: float
    seats: tuple[float, ...]
    seat: float
    floor: float
    wheels: tuple[tuple[float, float, float], ...]
    half_length: float
    hides_legs: bool
    speed: float
    crank: tuple[float, float, float] | None = None
    grip: tuple[float, float] | None = None
    bell: bool = False
    medium: str = "ground"
    stands: bool = False


def _units(height: float, value: float) -> float:
    """``value`` in a character's heights as prop units of a vehicle ``height`` tall."""
    return value / height


def _spec(height: float, *, seats: tuple[float, ...], seat: float, floor: float, wheels: tuple[tuple[float, float, float], ...] = (),
          half_length: float, hides_legs: bool, speed: float, crank: tuple[float, float, float] | None = None,
          grip: tuple[float, float] | None = None, bell: bool = False, medium: str = "ground", stands: bool = False) -> VehicleSpec:
    """A :class:`VehicleSpec` from measures in a character's heights (the drawings use them too)."""
    def u(value: float) -> float:
        return _units(height, value)

    return VehicleSpec(
        height, tuple(u(x) for x in seats), u(seat), u(floor), tuple((u(x), u(y), u(r)) for x, y, r in wheels), u(half_length),
        hides_legs, speed, None if crank is None else (u(crank[0]), u(crank[1]), u(crank[2])),
        None if grip is None else (u(grip[0]), u(grip[1])), bell, medium, stands,
    )


#: The vehicles. Measures in a character's heights: a seat line at 0.2 (a car), 0.44 (a bus, on
#: its high floor) or 0.255 (a bicycle's saddle), so a seated rider's head shows in a window or
#: above the handlebar; riders' feet on the floor behind the side (car 0.08, bus 0.3).
VEHICLES: dict[str, VehicleSpec] = {
    "bicycle": _spec(
        0.38, seats=(-0.08,), seat=0.255, floor=0.0, wheels=((-0.19, 0.12, 0.12), (0.19, 0.12, 0.12)), half_length=0.31,
        hides_legs=False, speed=4.0, crank=(0.0, 0.11, 0.042), grip=(0.093, 0.36), bell=True,
    ),
    "car": _spec(
        1.12, seats=(0.1, -0.4), seat=0.2, floor=0.08, wheels=((-0.58, 0.16, 0.16), (0.58, 0.16, 0.16)), half_length=0.95,
        hides_legs=True, speed=5.0,
    ),
    "bus": _spec(
        1.45, seats=(1.28, 0.38, -0.38, -1.12), seat=0.44, floor=0.3, wheels=((-1.0, 0.22, 0.22), (1.15, 0.22, 0.22)),
        half_length=1.6, hides_legs=True, speed=4.0,
    ),
    "boat": _spec(
        0.58, seats=(0.2, -0.3), seat=0.2, floor=0.05, half_length=0.9, hides_legs=True, speed=2.5, medium="water",
    ),
    "hot_air_balloon": _spec(
        2.1, seats=(0.15, -0.15), seat=0.04, floor=0.04, half_length=0.5, hides_legs=True, speed=1.2, medium="air", stands=True,
    ),
    "toy_rocket": _spec(0.55, seats=(), seat=0.0, floor=0.0, half_length=0.12, hides_legs=False, speed=6.0, medium="air"),
}


def is_vehicle(kind: str | None) -> bool:
    """Whether a built-in prop ``kind`` is a vehicle."""
    return kind in VEHICLES


def medium(kind: str) -> str:
    """Where a ``kind`` vehicle goes: ``ground``, ``water`` or ``air``."""
    return VEHICLES[kind].medium


def seat_count(kind: str) -> int:
    """How many ride a ``kind`` vehicle (one per seat)."""
    return len(VEHICLES[kind].seats)


def seat_origin(kind: str, place: int) -> tuple[float, float]:
    """Where a rider's feet (its origin) go in a ``kind`` vehicle's seat ``place`` (0: the front
    one), prop units as drawn facing right: below its hips, on the floor."""
    spec = VEHICLES[kind]
    return spec.seats[place], spec.floor


def seated_height(kind: str, prop_height: float, character_height: float) -> float:
    """How high a ``kind`` vehicle's seat line is above its floor, in the heights of a rider
    ``character_height`` tall, for the vehicle ``prop_height`` tall (any unit, the same for
    both): the seat :meth:`~vidgen.cartoon.character.Character.seated` puts the hips on."""
    spec = VEHICLES[kind]
    return (spec.seat - spec.floor) * prop_height / character_height


def get_in_gap(rider_x: float, vehicle_x: float, vehicle_height: float, kind: str) -> float:
    """How far (units) a rider's feet at ``rider_x`` are beyond the nearer end of a ``kind``
    vehicle ``vehicle_height`` units tall standing at ``vehicle_x`` (0 beside it)."""
    half = VEHICLES[kind].half_length * vehicle_height
    return max(abs(rider_x - vehicle_x) - half, 0.0)


def place_order(rider_x: float, vehicle_x: float, vehicle_height: float, kind: str, facing: str) -> list[int]:
    """A ``kind`` vehicle's seats, the one nearest to a rider at ``rider_x`` first (the vehicle
    ``vehicle_height`` units tall at ``vehicle_x``, facing ``facing``)."""
    sign = 1.0 if facing == "right" else -1.0
    seats = VEHICLES[kind].seats
    return sorted(range(len(seats)), key=lambda k: (abs(vehicle_x + sign * seats[k] * vehicle_height - rider_x), k))


def wheel_degrees(forward: float, radius: float) -> float:
    """How far (degrees, counterclockwise as drawn facing right) a wheel of ``radius`` turns as its
    vehicle rolls ``forward`` (the same unit; negative: backwards): clockwise going forward."""
    return -math.degrees(forward / radius) if radius > 0 else 0.0


def crank_degrees(wheel_turn: float) -> float:
    """How far a bicycle's cranks turn while its wheels turn ``wheel_turn`` degrees (:data:`GEAR`)."""
    return wheel_turn / GEAR


def pedal_points(kind: str, crank_angle: float) -> dict[str, tuple[float, float]]:
    """Where a ``kind`` vehicle's pedals are with its cranks turned ``crank_angle`` degrees
    (counterclockwise as drawn facing right; 0: the near pedal straight ahead), prop units as
    drawn facing right: ``left`` (the near foot's) and ``right`` (the far one's, opposite). Empty
    for a vehicle without pedals."""
    crank = VEHICLES[kind].crank
    if crank is None:
        return {}
    x, y, r = crank
    a = math.radians(crank_angle)
    return {"left": (x + r * math.cos(a), y + r * math.sin(a)), "right": (x - r * math.cos(a), y - r * math.sin(a))}


def ride_facing(facing: str, dx: float) -> str:
    """Which way a vehicle facing ``facing`` faces while it goes ``dx`` across (it turns round to
    go the other way; only in depth it keeps its facing)."""
    if abs(dx) <= 1e-9:
        return facing
    return "right" if dx > 0 else "left"


__all__ = [
    "AIR_VEHICLES",
    "CYCLING_LEAN",
    "GEAR",
    "GET_IN_REACH",
    "GET_IN_SECONDS",
    "GET_OUT_SECONDS",
    "GROUND_VEHICLES",
    "RIDING_ACTIONS",
    "ROCKET_ASCENT_SHARE",
    "VEHICLES",
    "VEHICLE_KINDS",
    "WATER_VEHICLES",
    "VehicleSpec",
    "crank_degrees",
    "get_in_gap",
    "is_vehicle",
    "medium",
    "pedal_points",
    "place_order",
    "ride_facing",
    "seat_count",
    "seat_origin",
    "seated_height",
    "wheel_degrees",
]
