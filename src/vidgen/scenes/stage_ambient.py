"""Ambient life on an iso place (DESIGN.md §105.7): the part of a ``stage`` that sets background
walkers, birds, a cat, ducks, butterflies, fireflies and flies about the place (``ambient``).
Written against ``vidgen.api`` only; :class:`IsoAmbience` is a part of
:class:`~vidgen.scenes.stage.Stage`.

The creatures are bodies of the place (:class:`IsoCritter`, sorted with the characters by their
boxes, each with a front picture of what stands in front of it: fog bands and swaying trees layer
them as they do the characters) and things that move by themselves (their plans say where they
are at each scene time). They keep off where the main characters stand and go, the objects the
scene uses, the vehicles' roads and tracks; they never speak, are no action targets and hide
in close shots (they never steal the focus). None in a draft.
"""

import math
from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *

from .stage_iso import ISO_OVERSAMPLE

#: The camera's zoom (over the scene's wide view) from which the creatures fade out, and where
#: they are gone: a close shot or a follow shows the main characters alone.
AMBIENT_FADE_ZOOM = (1.45, 1.9)
#: How dark the light is when butterflies have gone and when fireflies are out (``darkness``).
BUTTERFLY_DARK = (0.2, 0.5)
FIREFLY_DARK = (0.3, 0.7)


def _rise(value: float, low: float, high: float) -> float:
    """0 at ``low`` or under, 1 at ``high`` or over, smoothly between."""
    return smooth(min(max((value - low) / (high - low), 0.0), 1.0))


class IsoAmbience:
    """The ambient life part of a ``stage`` on an iso place (DESIGN.md §105.7)."""

    def _iso_make_ambient(self, place: Any) -> None:
        """An :class:`IsoCritter` for each creature of the scene's ``ambient`` (:attr:`iso_critters`)
        that has room on the place, each one of :attr:`story_things` with its front picture (they
        come on screen with the set: :meth:`iso_ambient_shown`)."""
        #: the creatures of the place's ambient life by name
        self.iso_critters: dict[str, IsoCritter] = {}
        #: for each creature's cell and height band, the pieces of the place drawn over it
        self._iso_critter_overs: dict[tuple[Any, ...], tuple[int, ...]] = {}
        setting = getattr(self.params, "ambient", None)
        if setting is None or self.is_draft:
            return
        counts = self._ambient_counts(setting)
        if not counts:
            return
        people, things = self._ambient_avoided(place)
        cells = ambient_cells(place, avoid=around(people | things), roads=self._ambient_roads(place), clear=around(people, 2))
        seed = setting.seed if setting.seed is not None else motion_seed(self.spec.id, "ambient")
        #: the camera's view width at the scene's start (the wide view): closer, the creatures hide
        self._ambient_wide = float(self.camera.frame.width)
        scale = self.iso_view.unit * config.pixel_height / self.frame_height * ISO_OVERSAMPLE
        for plan in plan_ambient(place, cells, counts, seed):
            look = critter_look(plan.kind, ambient_seed(seed, plan.name), muted=setting.muted)
            critter = IsoCritter(plan, look, self.iso_view, scale=scale, density=self._iso_density, frame_width=self.frame_width,
                                 seen=lambda now, kind=plan.kind: self._ambient_seen(kind, now), outline=self.drawing.outline_factor)
            mark_lit(critter)
            self.iso_critters[plan.name] = critter
            self.story_things.append(critter)
            picture = self._iso_critter_front(critter)
            front = self._iso_front(plan.name, picture)
            self._iso_fronts[plan.name] = (picture, front)   # (they move by themselves: _start_story watches them)

    def _ambient_counts(self, setting: Any) -> dict[str, int]:
        """How many of each kind the scene has: as ``setting`` asks, indoors only a cat and flies,
        butterflies only when it may be light, fireflies only when it may be dark."""
        indoor = self.params.iso.place == "indoor"
        counts = ambient_counts(setting.counts(indoor=indoor), indoor)
        changes = bool(self.action_uses("time_of_day") or self.action_uses("light"))
        dark = darkness(self.base_light)
        if not changes and dark >= BUTTERFLY_DARK[1]:
            counts.pop("butterfly", None)
        if not changes and dark <= FIREFLY_DARK[0]:
            counts.pop("firefly", None)
        return counts

    def _ambient_avoided(self, place: Any) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
        """The cells the creatures keep off (the cells round them too): where the main characters
        stand and the spots and cells the scene's moves take them to, where the small things stand
        (the first set); the objects the scene's actions name (the seats they sit on, what they
        use) and the vehicles it drives (the second)."""
        spots = {spot.name: (spot.column, spot.row) for spot in place.spots}
        cells: set[tuple[int, int]] = set()
        for member in self.params.characters:
            cells.add(place.stand_cell(str(member.at)))
        for prop in self.params.stage_props():
            if isinstance(prop.at, str) and prop.at in spots:
                cells.add(spots[prop.at])
        for kind in sorted(ISO_MOVES):
            for use in self.action_uses(kind):
                for key in ("to", "around", "door"):
                    to = getattr(use.options, key, None)
                    if isinstance(to, str) and to in spots:
                        cells.add(place.stand_cell(to))
                    elif to is not None and hasattr(to, "column"):
                        cells.add((to.column - 1, to.row - 1))
        things: set[tuple[int, int]] = set()
        patterns = self._iso_action_targets()
        for item in place.objects:
            if any(fnmatchcase(item.name, pattern) for pattern in patterns) or item.kind in ISO_SEATS or item.kind in ISO_BEDS:
                things |= set(item.cells())
        for name in getattr(self, "iso_vehicles", {}):
            things |= set(place.object(name).cells())
        return cells, things | self._ambient_lanes(place)

    def _ambient_lanes(self, place: Any) -> set[tuple[int, int]]:
        """The water a sailing boat crosses (its routes, replayed as planned from where it
        stands): ducks keep off it (DESIGN.md §105.8). A car's paths and a train's track are
        :meth:`_ambient_roads`."""
        lanes: set[tuple[int, int]] = set()
        boats = {name: (place.object(name), None) for name, v in getattr(self, "iso_vehicles", {}).items() if v.kind == "boat"}
        for use in self.action_uses("sail_to"):
            for name in [n for n in boats if any(fnmatchcase(n, p) for p in use.config.targets())]:
                item, heading = boats[name]
                options = {"to": getattr(use.options, "to", None), "via": list(getattr(use.options, "via", None) or [])}
                try:
                    route = plan_vehicle(moved_place(place, {name: item}), name, "sail_to", options, heading=heading)
                except VidgenError:
                    continue   # validate says why
                for a, b in zip(route.points, route.points[1:]):
                    steps = max(int(math.dist(a, b) * 2), 1)
                    lanes |= {(math.floor(a[0] + (b[0] - a[0]) * k / steps), math.floor(a[1] + (b[1] - a[1]) * k / steps)) for k in range(steps + 1)}
                boats[name] = (moved_item(item, route.end_cells, route.end_heading), route.end_heading)
        return lanes

    def _ambient_roads(self, place: Any) -> set[tuple[int, int]]:
        """Where nobody walks: the paths when a car drives on them, a train car's track."""
        roads = {cell for cells in getattr(self, "_iso_tracks", {}).values() for cell in cells}
        if any(vehicle.kind == "car" for vehicle in getattr(self, "iso_vehicles", {}).values()):
            roads |= {(c, r) for r in range(place.rows) for c in range(place.columns) if place.ground(c, r) == "path"}
        return roads

    def _ambient_seen(self, kind: str, now: float) -> float:
        """How much of a creature of ``kind`` shows at scene time ``now``: none in a close view
        (:data:`AMBIENT_FADE_ZOOM`), butterflies fading out at dusk, fireflies coming out at night."""
        zoom = self._ambient_wide / max(float(self.camera.frame.width), 1e-9)
        seen = 1.0 - _rise(zoom, *AMBIENT_FADE_ZOOM)
        if kind == "butterfly":
            seen *= 1.0 - _rise(self._iso_night(), *BUTTERFLY_DARK)
        elif kind == "firefly":
            seen *= _rise(self._iso_night(), *FIREFLY_DARK)
        return seen

    def _iso_critter_front(self, critter: Any) -> Any:
        """The front picture of ``critter`` where it is now: the pieces drawn over a body in its
        cell at its height (found once per cell and height, :meth:`_iso_body_over`)."""
        return self.iso_scenery.front(critter.box(), over=self._iso_body_over(critter))

    def _iso_body_over(self, body: Any) -> tuple[int, ...]:
        """Which pieces of the place are drawn over ``body`` (a creature's: found once per cell
        and height)."""
        if getattr(body, "iso_ambient", False):
            box = body.box()
            c, r = body.cell()
            key = (c, r, round(box.z0 * 2), round(box.z1 * 2))
            if key not in self._iso_critter_overs:
                self._iso_critter_overs[key] = self.iso_scenery.over(Box3(c, r, box.z0, c + 1, r + 1, box.z1))
            return self._iso_critter_overs[key]
        return self.iso_scenery.over(self._iso_body(body))

    def _iso_splice_front(self, critter: Any, old: Mobject | None, new: Mobject | None) -> bool:
        """``critter`` has a new front picture (``new`` for ``old``, swapped in the scene's list
        already): while an animation plays, what Manim draws on each frame drops the old one and
        draws the new one right after the creature, without sorting it all again (creatures
        change cells often). Whether it did (else the whole list is sorted again)."""
        if not getattr(self, "animations", None):
            return True   # the next animation starts from the scene's list
        moving = self.moving_mobjects
        own = {id(m) for m in critter.get_family()}
        at = max((k for k, m in enumerate(moving) if id(m) in own), default=None)
        if at is None:
            return False
        if new is not None:
            new.show_view(self.camera.frame)   # a front picture made earlier: the tiles of the view now
        gone = {id(m) for m in old.get_family()} if old is not None else set()
        head = [m for m in moving[:at + 1] if id(m) not in gone]
        tail = [m for m in moving[at + 1:] if id(m) not in gone]
        self.moving_mobjects = [*head, *(new.get_family() if new is not None else []), *tail]
        return True

    def iso_ambient_shown(self) -> list[Mobject]:
        """The creatures and their front pictures, to come on screen with the set."""
        return [m for name, critter in getattr(self, "iso_critters", {}).items()
                for m in (critter, *([self._iso_fronts[name][1]] if self._iso_fronts[name][1] is not None else []))]


__all__ = ["AMBIENT_FADE_ZOOM", "BUTTERFLY_DARK", "FIREFLY_DARK", "IsoAmbience"]
