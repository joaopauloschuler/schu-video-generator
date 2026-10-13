"""Riding beat actions (DESIGN.md §69.52): ``get_in`` (or on), ``ride_to`` and ``get_out`` on the
characters and vehicles (a ``bicycle``, a ``car``, a ``bus``) of a ``stage``. Written against
``vidgen.api`` only, like project actions.

Who rides what is the scene's :class:`Postures` (a rider is ``riding`` its vehicle, in a seat);
the riders follow their vehicle with an updater (:func:`place_rider`; a rider is never added to
its vehicle) and :class:`Ride` moves the vehicle and its riders together. The geometry and the
checks are pure (:mod:`vidgen.cartoon.vehicles`, :func:`holding_problems`).
"""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *

from .acting import _Acting, _characters, is_part_target, posture_parts
from .moving import Depth, Place, WalkPlace, _ended_walk, _place_x, _walk_problems
from .sitting import _posed, _stage_prop, postures


def _riders(scene: NarratedScene) -> dict[str, tuple[RiderSeat, Any]]:
    """Rider name -> its :class:`RiderSeat` and its follow updater (made on first use)."""
    found = getattr(scene, "_riders", None)
    if found is None:
        found = scene._riders = {}
    return found


def _vehicle(scene: NarratedScene, name: str) -> Prop:
    found = [t.mobject for t in scene.find_targets(name) if isinstance(t.mobject, Prop) and t.mobject.is_vehicle]
    if not found:
        raise VidgenError(f"scene '{scene.spec.id}': '{name}' is not a vehicle of the scene")
    return found[0]


def _vehicle_names(params: Any) -> list[str]:
    """The stage's vehicles (props of a :data:`VEHICLE_KINDS` kind), by name."""
    return [name for name, prop in zip(params.prop_names(), params.stage_props()) if prop.prop in VEHICLE_KINDS]


def vehicle_problem(params: Any, name: str) -> str | None:
    """Why ``name`` is not a vehicle of the stage with ``params`` (``None``: it is one)."""
    vehicles = _vehicle_names(params)
    if name in vehicles:
        return None
    known = f"vehicles: {', '.join(vehicles)}" if vehicles else f"the scene has no vehicle; add one to its props ({', '.join(VEHICLE_KINDS)})"
    if _stage_prop(params, name) is not None:
        return f"'{name}' is not a vehicle ({known})"
    return f"'{name}' is not a vehicle of the scene ({known})"


def _draw_with(scene: NarratedScene, rider: Character, vehicle: Prop, *, behind: bool) -> None:
    """Draw ``rider`` (and the props it holds) right before ``vehicle`` (``behind``: its side hides
    the lower body) or right after it (on it, or standing in front of it)."""
    mobjects = getattr(scene, "mobjects", [])
    if rider not in mobjects or vehicle not in mobjects:
        return
    block = [m for m in mobjects if m is rider or getattr(m, "held_by", None) == rider.name]
    for m in block:
        mobjects.remove(m)
    at = mobjects.index(vehicle) + (0 if behind else 1)
    if not behind:   # after its other riders drawn on it
        while at < len(mobjects) and getattr(mobjects[at], "riding", None) == vehicle.name:
            at += 1
    mobjects[at:at] = block
    keep = getattr(scene, "_shadows_first", None)
    if callable(keep):
        keep()


@action("get_in")
class GetIn(_Acting):
    """The target characters get in (or on) the vehicle ``to`` (a car, a bus or a bicycle of the
    stage): each takes the free seat nearest to it and sits down (a car's or a bus's side then
    hides its legs and its head shows in a window; on a bicycle it sits on the saddle, its feet on
    the pedals and its hands on the handlebar). It rides along with every ride_to of the vehicle
    until a get_out; it cannot walk, jump or turn before. Each must stand next to the vehicle at its
    depth (vidgen validate says where to walk_to first); a full vehicle (a bicycle 1, a car 2, a
    bus 4) takes no more."""

    class Options(ActionOptions):
        to: str
        """The vehicle it gets in (a car, a bus or a bicycle of the stage, by its name)."""

    run_time = GET_IN_SECONDS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = self._target_characters(scene_cls, params)[1]
        if "<prop>" not in scene_cls.target_patterns:
            return problems + [("target", "get_in is for the characters and vehicles of a stage")]
        problem = vehicle_problem(params, self.options.to)
        return problems + ([("to", problem)] if problem is not None else [])

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Each character climbs onto a free seat: its feet to the seat's floor, its body down onto
        the seat (on a bicycle: leaning to the handlebar, feet on the pedals)."""
        vehicle = _vehicle(scene, self.options.to)
        anims: list[Animation] = []
        for character in _characters(scene, targets, "get_in"):
            here = float(character.feet()[0])
            order = place_order(here, float(vehicle.feet()[0]), vehicle.unit, vehicle.kind, vehicle.facing)
            place = postures(scene).ride(character.name, vehicle.name, seat_count(vehicle.kind), order)
            before = character.state()
            character.face(vehicle.facing)
            seat = RiderSeat(character, vehicle, place, character.character_height / vehicle.unit)
            riding = riding_state(character, vehicle, place, character.state())
            target = seat_point(vehicle, place)
            moved = {**posture_parts(riding), **{p: riding.parts[p] for p in riding.parts if p.startswith("arm_")}}
            anims.append(BodyMove(character, [(1.0, moved)], x=float(target[0]), y=float(target[1])))
            _posed(scene)[character.name] = {**posture_parts(before), **{p: before.parts[p] for p in moved if p.startswith("arm_")}}

            def follow(mob: Mobject, seat: RiderSeat = seat) -> None:
                place_rider(seat)

            character.add_updater(follow)
            character.riding = vehicle.name
            _riders(scene)[character.name] = (seat, follow)
            _draw_with(scene, character, vehicle, behind=VEHICLES[vehicle.kind].hides_legs)
        return anims


@action("get_out")
class GetOut(_Acting):
    """The target characters get out of (or off) the vehicle they ride (after a get_in), where it
    is now: each stands up beside its seat, in front of the vehicle, its body, legs and arms back to
    how they were before it got in."""

    class Options(ActionOptions):
        pass

    run_time = GET_OUT_SECONDS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Each rider stands up on the ground beside its seat (drawn in front of the vehicle)."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "get_out"):
            found = _riders(scene).pop(character.name, None)
            if found is None:
                continue
            seat, follow = found
            postures(scene).get_out(character.name)
            character.remove_updater(follow)
            before = _posed(scene).pop(character.name, {})
            ground = float(seat.vehicle.feet()[1])
            anims.append(BodyMove(character, [(1.0, before)], y=ground))
            character.riding = None
            character.stage_depth = float(getattr(seat.vehicle, "stage_depth", character.stage_depth))
            _draw_with(scene, character, seat.vehicle, behind=False)
        return anims


@action("ride_to")
class RideTo(Action):
    """The target vehicle (a car, a bus or a bicycle of the stage; or a character riding one: its
    vehicle) rides along the ground to ``to`` (a mark of the stage, or an x from 0 = left to 1 =
    right) with everyone in it: it turns to face the way it goes, speeds up, goes at ``speed``,
    slows down and stops, its wheels turning (a bicycle's rider pedals). ``depth`` (or ``to:
    {mark, depth}``) rides it towards (smaller) or away from (larger) the camera too, its riders
    growing or shrinking with it. A bicycle rings its bell as it sets off, a car or a bus starts its
    engine; it brakes at the stop (foley); a fast ride raises dust and leaves speed lines (motion
    effects). It takes as long as the distance needs (``run_time`` sets it instead)."""

    class Options(ActionOptions):
        to: WalkPlace | Place | None = None
        """Where it rides: a mark (left, centre, right, ... or the stage's own), an x from 0 (left edge) to 1 (right edge) of the stage, or {mark, depth}; default: where it is (with depth)."""
        depth: Depth | None = None
        """How far back it rides to: 0 = the front (the ground line, full size) .. 1 = the back of the stage, smaller; default: its depth now."""
        speed: float | None = Field(None, gt=0.0, le=30.0)
        """Speed in units per second (the frame's shorter side is 8 units); default: the vehicle's (a bicycle and a bus 4, a car 5)."""

    run_time = 2.0

    def _destination(self) -> tuple[Any, float | None]:
        to = self.options.to
        if isinstance(to, WalkPlace):
            return to.mark, to.depth if to.depth is not None else self.options.depth
        return to, self.options.depth

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if "<prop>" not in scene_cls.target_patterns:
            return [("target", "ride_to is for the vehicles of a stage")]
        problems: list[tuple[str, str]] = []
        vehicles = _vehicle_names(params)
        characters = {c.name for c in getattr(params, "characters", [])}
        for pattern in self.config.targets():
            for name in [n for n in scene_cls.target_names(params) if fnmatchcase(n, pattern) and not is_part_target(n)]:
                if name not in vehicles and name not in characters:
                    problems.append(("target", vehicle_problem(params, name) or ""))
        place = self._destination()[0]
        if place is not None:
            try:
                scene_cls.camera_place(params, place)
            except ValueError as exc:
                problems.append(("to", str(exc)))
        return problems + _walk_problems(params, self.options.to, self.options.depth)

    def _vehicles(self, scene: NarratedScene, targets: list[Target]) -> list[Prop]:
        """The target vehicles, and the vehicles the target characters ride, each once."""
        found: list[Prop] = []
        for target in targets:
            mob = target.mobject
            if isinstance(mob, Character) and mob.riding is not None:
                mob = _vehicle(scene, mob.riding)
            if isinstance(mob, Prop) and mob.is_vehicle and all(mob is not v for v in found):
                found.append(mob)
        return found

    def _goal(self, scene: NarratedScene, vehicle: Prop) -> tuple[float, float | None]:
        place, depth = self._destination()
        x = float(vehicle.feet()[0]) if place is None else _place_x(scene, place)
        return x, depth if hasattr(scene, "feet_y_at") else None

    def _seats(self, scene: NarratedScene, vehicle: Prop) -> list[RiderSeat]:
        return [seat for seat, _ in _riders(scene).values() if seat.vehicle is vehicle]

    def _ride(self, scene: NarratedScene, vehicle: Prop) -> Ride:
        x, depth = self._goal(scene, vehicle)
        deeper = depth is not None and abs(depth - float(getattr(vehicle, "stage_depth", 0.0))) > SAME_DEPTH
        seats = self._seats(scene, vehicle)
        strength = min((s.rider.motion_strength for s in seats), default=None)   # no rider: the scene's (motion effects)
        return Ride(vehicle, x, seats=seats, speed=self.options.speed, depth=depth if deeper else None,
                    feet_y=getattr(scene, "feet_y_at", None) if deeper else None, strength=strength)

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        times = [self._ride(scene, v).run_time for v in self._vehicles(scene, targets)]
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`Ride` of each vehicle with its riders."""
        anims: list[Animation] = []
        for vehicle in self._vehicles(scene, targets):
            ride = self._ride(scene, vehicle)
            if ride.path <= 1e-6:
                continue
            anims.append(ride)
            if ride.to_depth is not None and hasattr(scene, "ride_in_depth"):
                scene.ride_in_depth(vehicle, ride)
            for seat in ride.seats:
                _ended_walk(scene, seat.rider)
        return anims
