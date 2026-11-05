"""Vehicles on an iso place (DESIGN.md §105): ``drive_to`` (a car along path cells, a train car
along its track), ``sail_to`` (a boat across water) and ``lift_off`` (a rocket from its pad, up
and out of the view). Written against ``vidgen.api`` only, like project actions; the stage plans
and draws them (``iso_drive``, :class:`IsoDrive`). Timed like any move: the beat's ``at`` or a
word (``at: "@word"``), as long as the way needs at the vehicle's speed (``run_time`` sets it)."""

import difflib
from fnmatch import fnmatchcase
from typing import Any, ClassVar

from vidgen.api import *

from .moving import MapTile


def _place_problems(params: Any, places: list[Any], key: str) -> list[tuple[str, str]]:
    """Each of ``places`` is a spot of the iso place or a cell of its map."""
    if getattr(params, "iso", None) is None:
        return []
    place = params.iso.parsed()
    spots = place.spot_names()
    problems = []
    for to in places:
        if isinstance(to, str) and to not in spots:
            close = difflib.get_close_matches(to, spots, n=1, cutoff=0.6)
            hint = f"did you mean {close[0]}? " if close else ""
            problems.append((key, f"the place has no spot '{to}' ({hint}spots: {', '.join(spots) or 'none: put a letter on the map'}); or give a cell {{column, row}}"))
        elif isinstance(to, MapTile) and (to.column > place.columns or to.row > place.rows):
            problems.append((key, f"row {to.row}, column {to.column} is outside the map ({place.rows} rows, {place.columns} columns)"))
    return problems


class _VehicleMove(Action):
    """A vehicle's move on an iso place: its targets are vehicles of :attr:`kinds`."""

    #: The vehicles it moves.
    kinds: ClassVar[tuple[str, ...]] = ()
    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        action = self.config.action
        if getattr(params, "iso", None) is None:
            return [("action", f"{action} moves a vehicle of an iso place (params.iso); on a plain stage a car rides with ride_to")]
        objects = params.iso.object_kinds()
        vehicles = sorted(name for name, kind in objects.items() if kind in self.kinds)
        known = ", ".join(vehicles) or f"none: add one to iso.objects ({' or '.join(self.kinds)})"
        problems: list[tuple[str, str]] = []
        for pattern in self.config.targets():
            matched = [n for n in objects if fnmatchcase(n, pattern)]
            for name in matched:
                if objects[name] not in self.kinds:
                    problems.append(("target", f"'{name}' is a {objects[name]}: {action} moves {' or '.join('a ' + k for k in self.kinds)} "
                                               f"(the place's: {known})"))
            if not matched:
                close = difflib.get_close_matches(pattern, vehicles, n=1, cutoff=0.6)
                hint = f"; did you mean {close[0]}?" if close else ""
                problems.append(("target", f"'{pattern}' is not a vehicle of the place{hint} ({action} moves: {known})"))
        return problems + self._place_options(params)

    def _place_options(self, params: Any) -> list[tuple[str, str]]:
        return []

    def _vehicles(self, scene: NarratedScene, targets: list[Target]) -> list[Any]:
        """The target vehicles the stage drives, each once."""
        found: list[Any] = []
        for target in targets:
            mob = target.mobject
            if getattr(mob, "iso_vehicle", False) and mob.kind in self.kinds and all(mob is not v for v in found):
                found.append(mob)
        return found

    def _drive(self, scene: NarratedScene, vehicle: Any) -> IsoDrive | None:
        raise NotImplementedError

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """As long as the longest of its vehicles' moves needs (``None``: none moves, or the rules
        refuse one now: :meth:`apply` plans it again when it plays, and raises)."""
        times = []
        for vehicle in self._vehicles(scene, targets):
            try:
                drive = self._drive(scene, vehicle)
            except VidgenError:
                continue
            if drive is not None:
                times.append(float(drive.run_time))
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """An :class:`IsoDrive` of each vehicle, recorded on the stage."""
        anims: list[Animation] = []
        for vehicle in self._vehicles(scene, targets):
            drive = self._drive(scene, vehicle)
            if drive is None:
                continue
            scene.iso_drove(drive, self.config.action)  # type: ignore[attr-defined]
            anims.append(drive)
        return anims


class _Route(_VehicleMove):
    """A move along a route to ``to`` (through ``via``) at ``speed``."""

    class Options(ActionOptions):
        to: str | MapTile
        """Where it goes: a spot of the map (its letter's cell) or a cell {column, row} from 1 at the map's top left."""
        via: list[str | MapTile] = []
        """Spots or cells it passes on the way, in order."""
        speed: float | None = Field(None, gt=0.0, le=12.0)
        """Speed in tiles per second (a character walks about 1.4); default: the vehicle's (a car 2.6, a train car 2.2, a boat 1.1)."""

    def _place_options(self, params: Any) -> list[tuple[str, str]]:
        return _place_problems(params, [self.options.to], "to") + _place_problems(params, list(self.options.via), "via")

    def _drive(self, scene: NarratedScene, vehicle: Any) -> IsoDrive | None:
        return scene.iso_drive(vehicle.name, self.config.action, self.options, speed=self.options.speed)  # type: ignore[attr-defined]


@action("drive_to")
class DriveTo(_Route):
    """The target car of an iso place drives along the path cells (:) to ``to`` (a spot or a cell
    {column, row}), through ``via`` on the way: it speeds up, turns at corners, its wheels turning,
    and stops with its front at the goal (it never turns round on the spot). A train car rolls
    along its track (the straight line of its cells, drawn as far as level free ground goes) and
    stops with its middle at ``to``. Characters and objects in the way stop it (vidgen validate
    says where); ``switch_on`` lights a car's headlights. An engine sounds, brakes as it stops."""

    kinds = ("car", "train_car")


@action("sail_to")
class SailTo(_Route):
    """The target boat of an iso place sails across the water (~) to ``to`` (a spot or a cell
    {column, row}), through ``via`` on the way, turning at corners, bobbing, and stops with its bow
    at the goal. Land, bridges, docks and other boats are in the way. A small motor sounds."""

    kinds = ("boat",)


@action("lift_off")
class LiftOff(_VehicleMove):
    """The target rocket of an iso place lifts off its pad: its engine fires (smoke billows over
    the pad), it rises slowly, then faster and faster, its flame roaring, up and out of the view,
    gone for the rest of the scene (its pad and tower stay). ``run_time`` sets how long it takes
    (default 4 s); a ``switch_on`` before fires the engine on the pad first."""

    class Options(ActionOptions):
        pass

    run_time = LIFT_OFF_SECONDS
    kinds = ("rocket",)

    def _drive(self, scene: NarratedScene, vehicle: Any) -> IsoDrive | None:
        seconds = self.config.run_time if self.config.run_time is not None else LIFT_OFF_SECONDS
        return scene.iso_drive(vehicle.name, "lift_off", self.options, seconds=seconds)  # type: ignore[attr-defined]

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return None


__all__ = ["DriveTo", "LiftOff", "SailTo"]
