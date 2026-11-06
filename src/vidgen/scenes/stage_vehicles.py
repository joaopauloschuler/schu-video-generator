"""Vehicles moving on an iso place (DESIGN.md §105): the part of a ``stage`` that drives a car,
sails a boat, rolls a train car along its track and lifts a rocket off. Written against
``vidgen.api`` only; :class:`IsoDriving` is a part of :class:`~vidgen.scenes.stage.Stage`.

A vehicle the scene's ``drive_to``, ``sail_to`` or ``lift_off`` moves is *driven*: left out of the
place's pictures (a train car's track is drawn along its whole run instead, a rocket's pad and
tower stay) and drawn as an :class:`IsoVehicle`, a body of the place like a character (its front
picture, the draw order by boxes). Its moves are planned by the rules
(:func:`~vidgen.world.iso_vehicles.plan_vehicle`) from where it and everyone stand once the moves
planned so far are over, as the walks are (§89.9).
"""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *

#: How long a rocket's smoke goes on billowing over its pad once it has lifted off (seconds).
SMOKE_AFTER = 2.5


class IsoDriving:
    """The vehicles' part of a ``stage`` on an iso place (DESIGN.md §105)."""

    def _iso_driven(self, place: Any) -> dict[str, str]:
        """The vehicles of the place the scene moves (``drive_to``, ``sail_to``, ``lift_off``):
        name -> kind. None in a scene without those actions."""
        found: dict[str, str] = {}
        for action in sorted(ISO_VEHICLE_ACTIONS):
            for use in self.action_uses(action):
                for pattern in use.config.targets():
                    for item in place.objects:
                        if VEHICLE_ACTIONS.get(item.kind) == action and fnmatchcase(item.name, pattern):
                            found[item.name] = item.kind
        return found

    def _iso_vehicle_views(self, place: Any) -> list[Box3]:
        """What a tall frame's wide view keeps in view of the vehicles the scene moves: each one
        where it stands, and the cells its moves go to and through."""
        driven = self._iso_driven(place)
        boxes = [object_box(place.object(name), place.floor_z(place.object(name).column, place.object(name).row)) for name in driven]
        spots = {spot.name: (spot.column, spot.row) for spot in place.spots}
        for action in ("drive_to", "sail_to"):
            for use in self.action_uses(action):
                if not any(fnmatchcase(name, pattern) for name in driven for pattern in use.config.targets()):
                    continue
                for to in [getattr(use.options, "to", None), *(getattr(use.options, "via", None) or [])]:
                    cell = spots.get(to) if isinstance(to, str) else (to.column - 1, to.row - 1) if to is not None else None
                    if cell is not None:
                        z = place.floor_z(*cell)
                        boxes.append(Box3(cell[0], cell[1], z, cell[0] + 1, cell[1] + 1, z + 1.3))
        return boxes

    def _iso_make_vehicles(self, place: Any, looks: dict[str, Any], density: float) -> None:
        """An :class:`IsoVehicle` for each driven vehicle (:attr:`iso_vehicles`) where it stands,
        on as the scene starts it, with its front picture; a train car's track drawn on the
        ground along the whole line it may roll on (:func:`track_cells`)."""
        #: the driven vehicles by name, and where each will stand once the moves planned so far are over
        self.iso_vehicles: dict[str, IsoVehicle] = {}
        self._iso_vehicle_plans: dict[str, tuple[Any, tuple[int, int]]] = {}
        self._iso_tracks: dict[str, list[tuple[int, int]]] = {}
        states = self.params.iso.states()
        pixels = config.pixel_height / self.frame_height
        track: list[Any] = []
        for name, kind in self._iso_driven(place).items():
            item = place.object(name)
            heading = start_heading(item)
            look = looks[name]
            vehicle = IsoVehicle(name, kind, ObjectLook(look.main, look.detail), self.iso_view, point=middle_of(place, item), heading=heading,
                                 scale=self.iso_view.unit * pixels * density, density=self._iso_density, frame_width=self.frame_width,
                                 outline=self.drawing.outline_factor, on=states.get(name, default_state(kind)).on, features=item.features)
            self.iso_vehicles[name] = vehicle
            self._iso_vehicle_plans[name] = (item, heading)
            if kind == "train_car":
                cells = track_cells(place, item)
                self._iso_tracks[name] = cells
                track += track_shapes(cells, place.floor_z(*cells[0]))
            picture = self._iso_vehicle_front(vehicle)
            front = self._iso_front(name, picture)
            self._iso_fronts[name] = (picture, front)
            if front is not None:
                self._iso_after[name] = [front]
        if track:   # on the ground, under everything standing on the place
            self.iso_scenery.ground = (*self.iso_scenery.ground, *track)

    def _iso_vehicle_front(self, vehicle: Any) -> Any:
        """The front picture of ``vehicle`` where it is now: the pieces in front of its box, but
        its own piece (a rocket's pad and tower stand round it, behind it)."""
        return self.iso_scenery.front(vehicle.box(), exclude=(vehicle.name,))

    def iso_vehicle_items(self) -> dict[str, Any]:
        """Each driven vehicle's object where it will stand once the moves planned so far are over."""
        return {name: item for name, (item, _) in getattr(self, "_iso_vehicle_plans", {}).items()}

    def _iso_rocket_smoke(self, place: Any, looks: dict[str, Any]) -> list[tuple[Any, Any]]:
        """For each driven rocket, the smoke billowing over its pad while its engine fires and a
        little after it has gone (an :class:`IsoGadgets`), with the piece of the place it is."""
        found = []
        for name, vehicle in getattr(self, "iso_vehicles", {}).items():
            if vehicle.kind != "rocket":
                continue
            item = place.object(name)
            base = place.floor_z(item.column, item.row)

            def strength(now: float, vehicle: Any = vehicle) -> float:
                if vehicle.launch is None:
                    return 1.0 if vehicle.on_at(now) else 0.0
                start, seconds = vehicle.launch
                if now < start:
                    return 1.0 if vehicle.on_at(now) else 0.0
                return min(max(1.0 - (now - start - seconds) / SMOKE_AFTER, 0.0), 1.0)

            def parts(now: float, item: Any = item, base: float = base, strength: Any = strength) -> list[Any]:
                return rocket_smoke(item, base, now, strength(now))

            def working(now: float, strength: Any = strength) -> bool:
                return strength(now) > 0.0

            def busy(start: float, end: float, working: Any = working, vehicle: Any = vehicle) -> bool:
                times = [start, end, *(t for t, _ in vehicle.switches if start <= t <= end)]
                if vehicle.launch is not None:
                    times += [t for t in (vehicle.launch[0], vehicle.launch[0] + vehicle.launch[1] + SMOKE_AFTER) if start <= t <= end]
                return any(working(t) for t in times) or (vehicle.launch is not None and vehicle.launch[0] <= end
                                                          and vehicle.launch[0] + vehicle.launch[1] + SMOKE_AFTER >= start)

            box = object_box(item, base)
            corners = [self.iso_view.point(x, y, z) for x in (box.x0 - 2, box.x1 + 2) for y in (box.y0 - 2, box.y1 + 2) for z in (box.z0, box.z0 + 2)]
            region = (min(x for x, _ in corners), min(y for _, y in corners), max(x for x, _ in corners), max(y for _, y in corners))
            gadget = IsoGadgets([Gadget(parts, working, busy)], lambda point: self.iso_view.point(*point), unit=self.iso_view.unit, region=region,
                                outline=self.drawing.outline_factor, pool_strength=lambda: getattr(self.camera, POOL_STRENGTH, POOL_DAY))
            found.append((gadget, item))
        return found

    # ----- moves ---------------------------------------------------------------------------------------

    def _iso_crowd(self) -> dict[tuple[int, int], str]:
        """Where the characters stand once the moves planned so far are over: cell -> name."""
        return {cell: name for name, cell in self.iso_cells.items() if cell is not None}

    def iso_drive(self, name: str, action: str, options: Any, *, speed: float | None = None, seconds: float | None = None) -> IsoDrive | None:
        """The move ``action`` (``drive_to``, ``sail_to``, ``lift_off``) of the driven vehicle
        ``name`` with ``options`` (``to``, ``via``), planned from where everyone stands once the
        moves planned so far are over (not recorded: :meth:`iso_drove` does): an :class:`IsoDrive`
        at ``speed`` (tiles per second; default the vehicle's), a lift-off over ``seconds``;
        ``None`` when it stays where it is. :class:`VidgenError` naming the scene, the beat and
        what is in the way."""
        vehicle = self.iso_vehicles[name]
        item, heading = self._iso_vehicle_plans[name]
        if vehicle.launch is not None:
            raise self._level_error(VidgenError(f"'{name}' has lifted off already: it is gone for the rest of the scene"))
        place = moved_place(self.iso_place_now(), {name: item})
        plan = {"to": getattr(options, "to", None), "via": list(getattr(options, "via", None) or [])}
        try:
            route = plan_vehicle(place, name, action, plan, heading=heading, crowd=self._iso_crowd(), track=self._iso_tracks.get(name),
                                 height=self._iso_lift_height(vehicle))
        except VidgenError as exc:
            raise self._level_error(exc) from None
        if len(route.points) < 2:
            return None
        clock = lambda: float(self.renderer.time)   # noqa: E731
        if action == "lift_off":
            return IsoDrive(vehicle, route, run_time=seconds or LIFT_OFF_SECONDS, gone=self._iso_gone_share(route), clock=clock)
        return IsoDrive(vehicle, route, run_time=drive_seconds(route, speed or VEHICLE_SPEEDS[vehicle.kind]), clock=clock)

    def _iso_lift_height(self, vehicle: Any) -> float:
        """How high a rocket rises (tile units): until it is well above the whole place's picture
        and a frame's height more (out of any view of the place)."""
        x, y, z = vehicle.point
        top = self.iso_scenery.bounds[1]
        return max((iso_point(x, y, z)[1] - top + self.frame_height / self.iso_view.unit) / ISO_RISE, 6.0)

    def _iso_gone_share(self, route: Any) -> float:
        """The share of a lift-off's way after which the rocket is out of the camera's view now
        (its flame's tip above the view's top edge)."""
        start, end = route.points[0], route.points[-1]
        frame = self.camera.frame
        top = float(frame.get_center()[1]) + float(frame.height) / 2
        bottom_now = self.iso_view.point(*start)[1] - self.iso_view.height(1.2)   # its flame's tip under the nozzle
        rise = self.iso_view.height(end[2] - start[2])
        return min(max((top - bottom_now) / max(rise, 1e-9), 0.0), 1.0)

    def iso_drove(self, drive: IsoDrive, action: str) -> None:
        """Record ``drive`` as it starts now: where the vehicle will stand once it is over (for the
        moves planned next), its time (for the stage's redrawing of moving things), where it goes
        on screen; a rocket switches its engine on as it lifts off."""
        vehicle = drive.mobject
        now = float(self.renderer.time)
        seconds = float(drive.run_time)
        item, _ = self._iso_vehicle_plans[vehicle.name]
        route = drive.route
        if action == "lift_off":
            vehicle.launch = (now, seconds)
            if not vehicle.on_at(now):
                vehicle.switch(now, True)
        else:
            self._iso_vehicle_plans[vehicle.name] = (moved_item(item, route.end_cells, route.end_heading), route.end_heading)
            vehicle.drives.append((now, seconds))
        vehicle.reaches(list(route.points))
        self._watch_draw_order()
        self._watch_living()

    def iso_switch_vehicles(self, patterns: list[str], on: bool, time: float) -> list[str]:
        """Switch the driven vehicles matching ``patterns`` on (or off) from scene ``time``: a
        car's headlights, a boat's lantern, a rocket's engine. The names switched."""
        names = []
        for name, vehicle in getattr(self, "iso_vehicles", {}).items():
            if any(fnmatchcase(name, pattern) for pattern in patterns) and vehicle.on_at(time) != on:
                vehicle.switch(time, on)
                names.append(name)
        if names:
            self._watch_living()
        return names


__all__ = ["SMOKE_AFTER", "IsoDriving"]
