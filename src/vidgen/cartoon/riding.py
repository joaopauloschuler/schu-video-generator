"""Riders in vehicles, drawn and moved with manim (DESIGN.md §69.52); the geometry is in
:mod:`vidgen.cartoon.vehicles`.

A rider is never added to its vehicle (a character's family never changes, §69.22, and a
vehicle's box stays its own in the layout dump): :func:`place_rider` puts it on its seat where
the vehicle is now, at its size (a vehicle riding in depth grows or shrinks, its riders with it),
and an updater on the rider calls it on every frame while it rides; :class:`Ride` calls it too
on every frame it moves the vehicle (Manim pauses the updaters of a character another animation
plays on). A car's or a bus's riders are drawn right before it (its side hides their lower body,
its windows show the rest), a bicycle's rider right after it, pedalling: its feet planted on the
pedals as the cranks turn (:meth:`Character.planted`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import numpy as np
from manim import Animation, linear

from vidgen.cartoon.acting import walk_progress, walk_seconds
from vidgen.cartoon.character import Character, CharacterState, scale_strokes
from vidgen.cartoon.motion import Phases
from vidgen.cartoon.props import Prop
from vidgen.cartoon.stage import depth_along, depth_scale, depth_walk_distance
from vidgen.cartoon.vehicles import CYCLING_LEAN, VEHICLES, pedal_points, ride_facing, seat_origin, seated_height, wheel_degrees


@dataclass
class RiderSeat:
    """A character riding a vehicle: the ``vehicle``, its seat ``place`` and its height as a
    share of one of the vehicle's prop units (``ratio``: kept while the vehicle grows or
    shrinks)."""

    rider: Character
    vehicle: Prop
    place: int
    ratio: float


def character_unit(vehicle: Prop) -> float:
    """The height of a character standing where ``vehicle`` is (Manim units): the vehicle's prop
    unit over its height next to a character."""
    factor = vehicle.height_factor if vehicle.height_factor is not None else VEHICLES[vehicle.kind].height
    return vehicle.unit / factor


def seat_point(vehicle: Prop, place: int) -> np.ndarray:
    """Where a rider's feet go on screen in ``vehicle``'s seat ``place`` (on its floor)."""
    return vehicle.prop_point(*seat_origin(vehicle.kind, place))


def place_rider(seat: RiderSeat) -> None:
    """Put ``seat.rider`` on its seat where the vehicle is now, at the size it keeps next to it,
    facing the vehicle's way, at its depth (its ``stage_depth`` and ``ground_y``)."""
    rider, vehicle = seat.rider, seat.vehicle
    height = seat.ratio * vehicle.unit
    factor = height / rider.character_height if rider.character_height > 0 else 1.0
    if abs(factor - 1.0) > 1e-9:
        rider.scale(factor, about_point=rider.feet())
        scale_strokes(rider, factor, 0.0)
    if rider.facing != vehicle.facing and rider.facing != "front":
        rider.face(vehicle.facing)
    rider.shift(seat_point(vehicle, seat.place) - rider.feet())
    rider.stage_depth = float(getattr(vehicle, "stage_depth", 0.0))
    if vehicle.ground_y is not None:
        rider.ground_y = vehicle.ground_y


def pedal_soles(seat: RiderSeat) -> dict[str, tuple[float, float]]:
    """Where a bicycle's rider's soles go (character units as drawn facing right, from its feet):
    on the pedals as the cranks are turned now; empty for a vehicle without pedals."""
    vehicle = seat.vehicle
    pedals = pedal_points(vehicle.kind, vehicle.crank_angle)
    if not pedals:
        return {}
    ox, oy = seat_origin(vehicle.kind, seat.place)
    scale = vehicle.unit / max(seat.rider.character_height, 1e-9)
    return {foot: ((x - ox) * scale, (y - oy) * scale) for foot, (x, y) in pedals.items()}


def riding_state(rider: Character, vehicle: Prop, place: int, base: CharacterState) -> CharacterState:
    """``base`` (the rider standing) as it rides ``vehicle`` in seat ``place``: its hips on the
    seat line; on a bicycle leaning forward (:data:`CYCLING_LEAN`), its feet on the pedals and its
    hands on the handlebar. The rider must face the vehicle's way and stand at its size already."""
    spec = VEHICLES[vehicle.kind]
    seated = rider.seated(base, seated_height(vehicle.kind, vehicle.unit, rider.character_height))
    if spec.crank is None:
        return seated
    body = seated.parts["body"]
    seated = CharacterState(seated.facing, {**seated.parts, "body": replace(body, angle=body.angle - CYCLING_LEAN)})
    probe = RiderSeat(rider, vehicle, place, rider.character_height / vehicle.unit)
    seated = rider.planted(seated, pedal_soles(probe))
    if spec.grip is None:
        return seated
    # the handlebar seen from where the rider stands now, as it will be from its seat
    grip = vehicle.prop_point(*spec.grip) - seat_point(vehicle, place) + rider.feet()
    parts = dict(seated.parts)
    for hand in ("left", "right"):
        if rider.has_part(f"arm_{hand}"):
            parts.update(rider.reached_parts(hand, grip, state=CharacterState(seated.facing, parts)))
    return CharacterState(seated.facing, parts)


def pedal(seat: RiderSeat) -> None:
    """Plant ``seat.rider``'s feet on its bicycle's pedals as they are now (nothing for a vehicle
    without pedals)."""
    soles = pedal_soles(seat)
    if soles:
        rider = seat.rider
        rider.set_state(rider.planted(rider.state(), soles))


class Ride(Animation):
    """``vehicle`` (a vehicle :class:`~vidgen.cartoon.props.Prop`) rides along the ground to ``x``
    (Manim units) at ``speed`` units per second, with the riders of ``seats``: it turns to face
    the way it goes (at once, its riders with it), speeds up, goes, slows down and stops
    (:func:`~vidgen.cartoon.acting.walk_progress`), its wheels turning by the way it goes and a
    bicycle's rider pedalling. ``depth``: it also rides towards or away from the camera
    (DESIGN.md §69.44), its feet to ``feet_y(depth)``, growing or shrinking by the depth scale with
    its riders. ``strength``: its riders' ``cartoon_motion`` strength, for the motion effects
    (``None``: the scene's)."""

    def __init__(
        self,
        vehicle: Prop,
        x: float,
        *,
        seats: Sequence[RiderSeat] = (),
        speed: float | None = None,
        depth: float | None = None,
        feet_y: Callable[[float], float] | None = None,
        strength: float | None = None,
        **kwargs,
    ) -> None:
        if depth is not None and feet_y is None:
            raise TypeError("Ride: a ride in depth needs feet_y (the ground line's y at a depth)")
        self.to_x = float(x)
        self.to_depth = None if depth is None else float(depth)
        self.feet_y = feet_y
        self.seats = list(seats)
        self.strength = strength
        self.kind = vehicle.kind
        self.from_depth = float(getattr(vehicle, "stage_depth", 0.0))
        unit = character_unit(vehicle)
        self.path = self._distance(self.to_x - float(vehicle.feet()[0]), unit)
        #: How far it rides, in the heights of a character beside it.
        self.heights = self.path / unit if unit > 0 else 0.0
        self.phases = Phases()
        kwargs.setdefault("run_time", max(walk_seconds(self.path, speed or VEHICLES[vehicle.kind].speed), 1e-3))
        kwargs.setdefault("rate_func", linear)
        super().__init__(vehicle, **kwargs)

    def _distance(self, dx: float, unit: float) -> float:
        if self.to_depth is None:
            return abs(dx)
        return depth_walk_distance(dx, self.from_depth, self.to_depth, unit)

    def begin(self) -> None:
        vehicle = self.mobject
        self._from = vehicle.feet()
        self.from_depth = self._shown_depth = float(getattr(vehicle, "stage_depth", 0.0))
        self.path = self._distance(self.to_x - float(self._from[0]), character_unit(vehicle))
        facing = ride_facing(vehicle.facing, self.to_x - float(self._from[0]))
        if facing != vehicle.facing:
            vehicle.flip(np.array([0.0, 1.0, 0.0]), about_point=self._from)
            vehicle.facing = facing
            for seat in self.seats:
                seat.rider.face(facing)
                place_rider(seat)
        self._travelled = 0.0
        super().begin()

    def _to_depth_now(self, share: float) -> float:
        """Grow or shrink the vehicle about its feet to its depth at ``share`` of the way; the y of
        its feet there."""
        vehicle = self.mobject
        depth = depth_along(self.from_depth, self.to_depth, share)
        factor = depth_scale(depth) / depth_scale(self._shown_depth)
        if abs(factor - 1.0) > 1e-12:
            vehicle.scale(factor, about_point=vehicle.feet())
            scale_strokes(vehicle, factor, 0.0)
        self._shown_depth = vehicle.stage_depth = depth
        vehicle.ground_y = float(self.feet_y(depth))
        return vehicle.ground_y

    def interpolate_mobject(self, alpha: float) -> None:
        vehicle = self.mobject
        share = walk_progress(self.rate_func(alpha))
        feet_y = float(self._from[1]) if self.to_depth is None else self._to_depth_now(share)
        x = float(self._from[0]) + share * (self.to_x - float(self._from[0]))
        vehicle.shift(np.array([x, feet_y, 0.0]) - vehicle.feet())
        travelled = share * self.path
        wheel = VEHICLES[self.kind].wheels[0][2] * vehicle.unit
        vehicle.turn_wheels(wheel_degrees(travelled - self._travelled, wheel))
        self._travelled = travelled
        for seat in self.seats:
            place_rider(seat)
            pedal(seat)
            seat.rider.sync_mouth()  # Manim pauses an animated character's updaters: keep lip sync in step


__all__ = ["Ride", "RiderSeat", "character_unit", "pedal", "pedal_soles", "place_rider", "riding_state", "seat_point"]
