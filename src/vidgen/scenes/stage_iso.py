"""A ``stage`` on an iso place (DESIGN.md §89): its pictures, the characters' moves and draw
order (§89.9) and its staging (§89.10): the camera on the place (shots, ``follow``, ``pan``),
small things standing on it and handed about, and changes to the place (a door opens, a lamp
lights, flowers bloom, a bridge appears). Written against ``vidgen.api`` only; :class:`IsoStaging`
is a part of :class:`~vidgen.scenes.stage.Stage`.
"""

import math
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from collections.abc import Callable
from typing import Any

import numpy as np

from vidgen.api import *

#: How much finer than the frame the place's pictures are drawn at the establishing view (as a
#: platform level's tiles); the camera zoomed in shows finer levels of detail (§89.10).
ISO_OVERSAMPLE = 1.25
#: Seconds a place change fades: a lamp switched on or off (a door opening takes its action's
#: time, an object appearing or going the ``reveal`` / ``hide`` action's).
ISO_SWITCH_SECONDS = 0.25
#: How far beside its feet a character puts a small thing down without ``to`` (tile units, along
#: the picture's level line; kept in its own cell).
ISO_PUT_ASIDE = 0.36
#: Seconds an object fades in when the scene's own entrance brings it (``reveal``).
ISO_REVEAL_SECONDS = 0.8
#: A lit lamp's light falls fully on a character whose feet are within the first distance of
#: the lamp's middle (tile units) and fades out by the second (its pool on the ground has a
#: radius of 1.1; the lantern stands high, so it lights a body a little beyond), DESIGN.md §89.13.
ISO_LAMP_REACH = (1.0, 2.2)
#: A lab object's blinking lights (DESIGN.md §100.11): the second colour (an amber besides the
#: object's own) and a light's radius (tile widths).
LAB_AMBER = "#FFB547"
LAB_LIGHT_SIZE = 0.035


@dataclass
class _IsoChange:
    """A change of an object of the place under way or to come: from scene time ``start`` over
    ``seconds`` its ``new`` picture (``None``: it goes) fades in over its ``old`` one (``None``: it
    was not there), which then leaves; the object's ``state`` counts from ``start``."""

    name: str
    state: ObjectState
    start: float
    seconds: float
    old: Mobject | None
    new: Mobject | None
    applied: bool = False


@dataclass
class _IsoFollow:
    """Another picture showing a changed object (a layer of an object behind it, a body's front
    picture) following the change instead of swapping at its start (DESIGN.md §90.15): the
    ``new`` picture, right under the ``old`` one, fades in and then the old one fades out
    (:meth:`IsoStaging._iso_follow_step`); when the change ends ``old`` leaves ``parent`` (a
    holder; ``None``: the scene). Either may be ``None`` (nothing was or will be there)."""

    change: _IsoChange
    old: Any
    new: Any
    parent: Mobject | None = None


def iso_particle_problem(iso: Any, kind: str, settings: Any) -> str | None:
    """Why particles of ``kind`` cannot fall on the iso place ``iso`` (DESIGN.md §89.11): rain,
    snow, leaves and streaks stay out of an indoor place. ``None``: they can (puddles and
    settling snow too, §90)."""
    if iso.place == "indoor" and kind in OUTDOOR_PARTICLES:
        return f"{kind} stays outdoors; an indoor place has none inside (sparkles, dust, confetti, smoke and bubbles work)"
    return None


#: What acts is in view on a frame when at least this share of it shows, or when what shows of
#: it fills at least :data:`WATCH_FILLS` of the view (a house in a close-up; lint ``offscreen_action``).
WATCH_IN_VIEW = 0.5
WATCH_FILLS = 0.25


@dataclass
class _Watched:
    """Something a beat does on an iso place, watched for lint ``offscreen_action`` (DESIGN.md
    §89.11): the ``action`` of ``who`` (a character, a small thing or an object of the place) in
    ``beat`` from scene time ``start`` to ``end``; ``box()`` gives what acts on screen now
    (``left, bottom, right, top``; ``None``: not there); ``frames`` counts the frames it played
    on, ``shown`` those with at least :data:`WATCH_IN_VIEW` of it in view."""

    beat: str
    action: str
    who: str
    start: float
    end: float
    box: Callable[[], tuple[float, float, float, float] | None]
    frames: int = 0
    shown: int = 0

    @property
    def seen(self) -> float:
        """The share of its frames on which it was in view (1 before any frame)."""
        return self.shown / self.frames if self.frames else 1.0


def _in_view(box: tuple[float, float, float, float] | None, frame: Mobject) -> bool:
    """Whether the camera's view ``frame`` shows ``box`` (``left, bottom, right, top``; ``None``:
    not there): :data:`WATCH_IN_VIEW` of it, or enough to fill :data:`WATCH_FILLS` of the view."""
    if box is None:
        return False
    left, bottom, right, top = box
    cx, cy = (float(v) for v in frame.get_center()[:2])
    hw, hh = float(frame.width) / 2, float(frame.height) / 2
    w, h = min(right, cx + hw) - max(left, cx - hw), min(top, cy + hh) - max(bottom, cy - hh)
    seen = max(w, 0.0) * max(h, 0.0)
    return seen >= WATCH_IN_VIEW * max((right - left) * (top - bottom), 1e-12) or seen >= WATCH_FILLS * 4 * hw * hh


class IsoObject(Group):
    """An object of the place that the scene changes or names (DESIGN.md §89.10): a group holding
    its layer picture (two while one fades into the other), drawn right after the place's base
    picture. Named after the object: an action's target."""


#: A speaker on an iso place gets a name tag over its head while its face on screen is smaller
#: than this share of the view's shorter side (lint ``small_speaker``'s ``min_face``), DESIGN.md §89.11.
NAME_TAG_FACE = 0.075
#: The name tag's gap over the head, its pointer's height and half width, and the width of its
#: outline, at the establishing view (Manim units; scaled with the camera's view).
NAME_TAG_GAP = 0.06
NAME_TAG_POINTER = 0.1
NAME_TAG_POINTER_HALF = 0.08
NAME_TAG_STROKE = 2.5


class NameTag(VGroup):
    """A speaker's name on a small plate in its colour with a pointer down to its head (DESIGN.md
    §89.11), kept the same size on screen and inside the view; shown while ``speaker`` speaks
    ``track`` (its lip sync) and its face is small on screen (:data:`NAME_TAG_FACE`), never while
    it has a speech bubble (``bubbled``). Not graded by the light."""

    def __init__(self, text: str, fill: str, theme: Any, speaker: Character, track: Any) -> None:
        label = callout_label(text, color=fill, size="caption", theme=theme)
        ink = label.text.family_members_with_points()[0].get_fill_color()
        plate = label.plate
        bottom = plate.get_bottom()
        pointer = Polygon(bottom + np.array([NAME_TAG_POINTER_HALF, 0.02, 0.0]), bottom + np.array([-NAME_TAG_POINTER_HALF, 0.02, 0.0]),
                          bottom + np.array([0.0, -NAME_TAG_POINTER, 0.0]))
        shape = Union(plate, pointer)
        shape.set_fill(plate.get_fill_color(), opacity=1).set_stroke(ink, width=NAME_TAG_STROKE)
        super().__init__(shape, label.text)
        self.shape, self.speaker, self.track = shape, speaker, track
        self.name_tag_of = speaker.name
        self.size_now = 1.0
        self.bubbled = False
        self.shown = 1.0

    def place(self, frame: Mobject, frame_width: float) -> None:
        """Size it for the camera's view ``frame``, put it over the speaker's head inside the
        view, and show it when it should show."""
        size = float(frame.width) / frame_width
        if abs(size - self.size_now) > 1e-9:
            self.scale(size / self.size_now)
            self.size_now = size
            self.shape.set_stroke(width=NAME_TAG_STROKE * size)
        figure = self.speaker
        head = figure.parts["head"] if figure.has_part("head") else figure
        tops = [figure.parts[part].get_top()[1] for part in ("head", "accessory") if figure.has_part(part)]
        top = float(max(tops)) if tops else float(figure.get_top()[1])
        cx, cy = (float(v) for v in frame.get_center()[:2])
        half_w, half_h = float(frame.width) / 2, float(frame.height) / 2
        x = float(head.get_center()[0])
        in_view = abs(x - cx) <= half_w and abs(top - cy) <= half_h
        x = min(max(x, cx - half_w + self.width / 2 + 0.1 * size), cx + half_w - self.width / 2 - 0.1 * size)
        y = min(top + NAME_TAG_GAP * size, cy + half_h - self.height - 0.05 * size)
        self.shift(np.array([x - float(self.get_center()[0]), y - float(self.get_bottom()[1]), 0.0]))
        small = float(head.height) < NAME_TAG_FACE * min(float(frame.width), float(frame.height))
        speaking = figure.lip_sync_track is self.track
        figure.name_tagged = speaking and small and in_view
        shown = 1.0 if figure.name_tagged and not self.bubbled else 0.0
        if shown != self.shown:
            self.set_opacity(shown)
            self.shown = shown


def _moving_block(scene: Any, mover: Mobject) -> list[Mobject]:
    """``mover`` with what moves with it in ``scene``'s draw order: a walker and the props right
    after it (or right before it: an open umbrella, balloons) that it holds; a vehicle, its riders
    and the props they hold (DESIGN.md §69.52)."""
    at = next((k for k, m in enumerate(scene.mobjects) if m is mover), None)
    if at is None:
        return []
    if isinstance(mover, Character):
        start, end = at, at + 1
        while start > 0 and getattr(scene.mobjects[start - 1], "held_by", None) == mover.name:
            start -= 1
        while end < len(scene.mobjects) and getattr(scene.mobjects[end], "held_by", None) == mover.name:
            end += 1
        return scene.mobjects[start:end]
    riders = {name for name, figure in scene.cast.items() if getattr(figure, "riding", None) == getattr(mover, "name", None)}
    return [m for m in scene.mobjects if m is mover or (isinstance(m, Character) and m.name in riders) or getattr(m, "held_by", None) in riders]


class IsoStaging:
    """The iso place's part of a ``stage`` (DESIGN.md §89.7, §89.9, §89.10)."""

    @property
    def on_iso(self) -> bool:
        """Whether the stage is an iso place: walks go from cell to cell on its map (§89.9)."""
        return self.params.iso is not None

    # ----- moves (DESIGN.md §89.9) -------------------------------------------------------------------

    def iso_place_now(self) -> IsoPlace:
        """The place as the moves planned now find it: without the objects that are not there
        (they appear later or have gone, §89.10)."""
        place = self.params.iso.parsed()
        planned = getattr(self, "_iso_planned_states", {})
        return place.without([name for name, state in planned.items() if not state.shown])

    def iso_walks(self, action: str, character: Character, options: dict[str, Any], *, pace: Any, gait: Gait = WALKING) -> list[IsoWalk]:
        """The walks of a move ``action`` of ``character`` on the iso place (DESIGN.md §89.9):
        ``walk_to`` / ``run_to`` (``options`` ``to``, or ``after`` and ``gap``), ``enter`` (``to``,
        ``door``, ``side``), ``exit`` (``to``: a side, ``door``), ``wander`` (``around``, ``radius``,
        ``stops``, ``seed``) or ``meet`` (``with``: the other walks too), planned by the rules
        (:func:`~vidgen.world.iso_moves.plan_move`) from where everyone stands once the moves
        planned so far are over; ``pace(character)``: its speed. A walk that goes nowhere is left
        out. Entering over the place's edge or out of a door it fades in, leaving it fades out
        and is moved off stage. :class:`VidgenError` naming the scene, the beat and the problem."""
        p = self.params
        assert p.iso is not None
        beat = self.current_beat
        now = float(self.renderer.time)
        step = IsoStep("", beat.id if beat is not None else "", action, (character.name,), options)
        planned = {name: route for name, (time, route) in self._iso_planned.items() if abs(time - now) < 1e-9}
        try:
            routes = plan_move(self.iso_place_now(), self.iso_cells, step, character.name, homes={c.name: str(c.at) for c in p.characters},
                               leader_routes=planned)
        except VidgenError as exc:
            raise self._level_error(exc) from None
        left, right = self.camera_bounds()[:2]
        walks: list[IsoWalk] = []
        for name, route in routes.items():
            self._iso_planned[name] = (now, route)
            figure = self.cast[name]
            passing = action in ("enter", "exit")
            if len(route.points) < 2 and not passing:
                continue
            extra: dict[str, Any] = {} if len(route.points) > 1 else {"run_time": 2 * DOOR_FADE_SECONDS}
            if passing:   # what it holds fades in and out with it (a key carried out of the room)
                extra["carried"] = [prop for prop in getattr(self, "props", {}).values() if getattr(prop, "held_by", None) == name]
            if action == "exit":
                side = nearer_side(self.iso_view.point(*route.end)[0], left, right)
                extra["park_x"] = offstage_x(side, left, right, figure.width / 2)
            walk = IsoWalk(figure, route, self.iso_view, speed=pace(figure), gait=gait, entering=action == "enter", **extra)
            walk.surfaces = route_surfaces(self.iso_place_now(), route)   # its footsteps (§89.11)
            if passing:
                fade = DOOR_FADE_SECONDS
                if route.cells[0 if action == "enter" else -1] is None:   # over the edge: it fades while it walks the step beyond
                    a, b = route.leg(0 if action == "enter" else len(route.points) - 2)
                    fade = max(walk.run_time * math.dist(a[:2], b[:2]) / route.length, DOOR_FADE_SECONDS)
                if action == "enter":
                    walk.fade_in = fade
                else:
                    walk.fade_out = fade
            walks.append(walk)
        return walks

    def iso_moved(self, walks: list[IsoWalk], *, leaving: bool = False) -> None:
        """Record where the walkers of ``walks`` (from :meth:`iso_walks`) stand once they are over
        (``leaving``: off the place): their cells for the next moves' plans, the cell top under
        their feet as their ground; the draw order is kept from now on (:meth:`_iso_keep_order`)."""
        for walk in walks:
            name = walk.mobject.name
            self.iso_cells[name] = None if leaving else walk.route.end_cell
            self.grounds[name] = self.iso_view.point(*walk.route.end)[1]
        self._watch_draw_order()

    # ----- the pictures (DESIGN.md §89.7, §89.10) ---------------------------------------------------

    def _iso_action_targets(self) -> list[str]:
        """The target patterns of every action of the scene."""
        uses = self._actions.uses if getattr(self, "_actions", None) is not None else []
        return [pattern for use in uses for pattern in use.action.config.targets()]

    def _iso_scenery(self, placements: list[StagePlacement]) -> list[Mobject]:
        """An iso place drawn into pictures (DESIGN.md §89.7, §89.9, §89.10): returns the place's
        base picture and the objects the scene changes or names (each an :class:`IsoObject`,
        drawn right after the base), for the backdrop; each character's and small thing's front
        picture (the pieces that hide part of it where it stands) goes in :attr:`_iso_after`
        under its name, drawn right after it. The pictures show the tiles in the camera's view
        (:meth:`_iso_show_view` on every frame)."""
        p = self.params
        assert p.iso is not None
        place = p.iso.parsed()
        #: where the place lies in the frame, and its pictures
        self.iso_view = iso_view(place, self.frame_width, self.frame_height)
        # everyone at its spot, those entering later too: the wide view shows where they come (§89.13);
        # in a tall frame also where the scene's walks go (it shows only the part where they are, §90.14)
        bodies = [self._iso_start_box(pl.name) for pl in placements]
        if self.frame_height > self.frame_width:
            bodies += self._iso_arrivals(place)
        width, center = self.iso_wide(bodies)
        if "camera_at" in p.model_fields_set:   # across the picture to the mark (a spot), as on any stage
            x = (mark_x(p.camera_at, p.stage_marks()) - 0.5) * self.stage_width
            center = view_center_within(self.camera_bounds(), (x, center[1]), width, width * self.frame_height / self.frame_width)
        self.camera.frame.scale(width / self.camera.frame.width).move_to([*center, 0.0])   # the wide view (§89.13)
        colors = IsoColors(**{key: resolve_color(value, self.theme) for key, value in p.iso.colors.items()})
        looks = {item.name: ObjectLook(*(resolve_color(own or default, self.theme)
                                         for own, default in zip((item.color, item.detail), OBJECT_COLORS[item.kind])))
                 for item in place.objects}
        density = 1.0 if self.is_draft else ISO_OVERSAMPLE
        states = p.iso.states()
        patterns = self._iso_action_targets()
        names = p.iso.changeable_names()
        layered = [name for name in names if name in states or any(fnmatchcase(name, pattern) for pattern in patterns)]
        pixels = config.pixel_height / self.frame_height
        self.iso_scenery = IsoScenery(place, colors, looks, self.iso_view, pixels * density, outline=self.drawing.outline_factor,
                                      states=states, layered=layered)
        self._iso_density = density * pixels / (config.pixel_width / self.frame_width)
        #: each object's state once the changes planned so far are over, its picture group, and the changes
        self._iso_planned_states: dict[str, ObjectState] = {name: self.iso_scenery.states[self.iso_scenery.index[name]] for name in layered}
        self.iso_objects: dict[str, IsoObject] = {}
        self._iso_changes: list[_IsoChange] = []
        #: the other pictures following a change under way (§90.15)
        self._iso_follows: list[_IsoFollow] = []
        self._iso_change_updater = self._iso_change_step
        #: each body's (character's, small thing's) front picture now: (its picture, the group;
        #: ``None``: nothing hides it), and the front pictures made so far by (body, picture)
        self._iso_fronts: dict[str, tuple[Any, Mobject | None]] = {}
        self._iso_front_pictures: dict[tuple[str, Any], Mobject] = {}
        for pl in placements:
            picture = self.iso_scenery.front(self._iso_start_box(pl.name))
            front = self._iso_front(pl.name, picture)
            self._iso_fronts[pl.name] = (picture, front)
            if front is not None:
                self._iso_after[pl.name] = [front]
        base = self._iso_tiles(self.iso_scenery.base(), "iso_place")
        shown: list[Mobject] = [base]
        for name in [self.iso_scenery.pieces[k].name for k in self.iso_scenery.layered]:
            holder = IsoObject()
            holder.name = name
            picture = self.iso_scenery.layer(name)
            if picture is not None:
                holder.add(self._iso_tiles(picture, f"iso_{name}"))
            self.iso_objects[name] = holder
            if picture is not None:
                shown.append(holder)
        self.add_camera_listener(self._iso_show_view)
        return shown + self._iso_story_overlays(place, looks)

    def _iso_story_overlays(self, place: Any, looks: dict[str, Any]) -> list[Mobject]:
        """The steel shutters over a room's windows when the place starts with them down or a
        ``shutters`` action moves them (DESIGN.md §100.7), and the blinking lights of its lab
        objects (§100.11), drawn over the place's pictures; each is one of :attr:`story_things`."""
        p = self.params
        #: things over the place that move by themselves (shutters, lights)
        self.story_things: list[Any] = []
        #: the room's shutters (``None``: none)
        self.iso_shutters: IsoShutters | None = None
        faces = window_faces(place)
        if faces and (p.iso.shutters or self.action_uses("shutters")):
            windows = [[self.iso_view.point(*corner) for corner in face] for face in faces]
            self.iso_shutters = IsoShutters(windows, closed=p.iso.shutters, stroke=1.5)
            self.story_things.append(self.iso_shutters)
        lights: list[tuple[float, float]] = []
        colors: list[str] = []
        for item in place.objects:
            if item.kind in LIT_OBJECTS:
                for k, point in enumerate(object_lights(item, place.floor_z(item.column, item.row))):
                    lights.append(self.iso_view.point(*point))
                    if item.kind == "tower":
                        colors.append(TOWER_ANTENNA_LIGHT)
                    else:
                        colors.append((looks[item.name].detail, LAB_AMBER, looks[item.name].detail)[k % 3] if item.kind == "server_rack" else LAB_AMBER)
        if lights and not self.is_draft:
            self.story_things.append(IsoBlinkers(lights, colors, LAB_LIGHT_SIZE * self.iso_view.unit, seed=motion_seed(self.spec.id, "lab_lights")))
        if not self.is_draft:
            self.story_things += self._iso_city(place, looks)
        return list(self.story_things)

    def _iso_city(self, place: Any, looks: dict[str, Any]) -> list[Mobject]:
        """A city's moving parts over the place (DESIGN.md §102.2, §102.3): the crawling lines of
        its towers' info screens (those no other object hides) and the hover pods of its
        ``traffic`` lanes."""
        p = self.params
        things: list[Mobject] = []
        screens, colors, seeds = [], [], []
        boxes = [(item, object_box(item, place.floor_z(item.column, item.row))) for item in place.objects]
        for item, box in boxes:
            corners = tower_screen(item, place.floor_z(item.column, item.row))
            if corners is None:
                continue
            picture = [iso_point(*corner) for corner in corners]
            left, right = min(u for u, _ in picture), max(u for u, _ in picture)
            top, bottom = min(v for _, v in picture), max(v for _, v in picture)

            def covers(other: Any, other_box: Any) -> bool:
                l, t, r, b = other_box.picture_bounds()
                return in_front(other_box, box) is True and l < right and r > left and t < bottom and b > top

            if any(other is not item and covers(other, other_box) for other, other_box in boxes):
                continue   # another building stands in front of it: its picture shows the screen as it is
            screens.append([self.iso_view.point(*corner) for corner in corners])
            colors.append(screen_color(looks[item.name].detail))
            seeds.append(screen_seed(item.name))
        if screens:
            things.append(IsoScreens(screens, colors, seeds=seeds))
        lanes = []
        for lane in p.iso.traffic:
            start, end = p.iso.lane_ends(lane)
            lanes.append(PodLane(self.iso_view.point(*start), self.iso_view.point(*end), lane.seconds, lane.count,
                                 resolve_color(lane.color, self.theme), POD_LENGTH * lane.size * self.iso_view.unit, lane.at, (start, end)))
        if lanes:   # a pod behind a building is hidden by it
            things.append(IsoTraffic(lanes, [(box, box_outline(box)) for _, box in boxes]))
        return things

    def _iso_arrivals(self, place: Any) -> list[Box3]:
        """In a tall frame, what the wide view keeps in view besides the characters: a character
        standing at each spot the scene's walks go to, or on a cell next to it (two sent to one
        spot stop side by side)."""
        boxes: list[Box3] = []
        for spot in self._iso_destinations(place):
            x, y, z = iso_stand(place, spot)
            boxes += [standing_box(place, (min(max(x + dx, 0.5), place.columns - 0.5), min(max(y + dy, 0.5), place.rows - 0.5), z), ISO_CHARACTER_HEIGHT)
                      for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        return boxes

    def _iso_destinations(self, place: Any) -> list[str]:
        """The spots of the place the scene's ``walk_to``, ``run_to`` and ``enter`` actions take
        characters to."""
        spots = {spot.name for spot in place.spots}
        out: list[str] = []
        for kind in ("walk_to", "run_to", "enter"):
            for use in self.action_uses(kind):
                to = getattr(use.options, "to", None)
                if isinstance(to, str) and to in spots and to not in out:
                    out.append(to)
        return out

    def iso_wide(self, bodies: list[Box3]) -> tuple[float, tuple[float, float]]:
        """The wide view of the place (:func:`~vidgen.cartoon.iso_stage.wide_view`, DESIGN.md
        §89.13) keeping ``bodies`` in view: ``(view width, centre)``; the scene's start and
        ``shot: wide``."""
        place = self.params.iso.parsed()
        count = len(self.params.iso.objects)
        placed = [item.name for item in place.objects[len(place.objects) - count:]] if count else []
        return wide_view(place, self.iso_view, self.frame_width, self.frame_height, bodies, placed, fit=self.params.iso.wide)

    def iso_wide_shot(self, names: list[str]) -> ShotView:
        """``shot: wide`` on the place: the wide view keeping the characters ``names`` (those on
        the place now) in view; in a tall frame also the spots the scene's walks go to."""
        bodies = [self._iso_body(self.cast[name]) for name in names if hasattr(self.cast[name], "iso_feet")]
        if self.frame_height > self.frame_width:   # a tall frame: also where the scene's walks go, as the start's view (§90.14)
            bodies += self._iso_arrivals(self.params.iso.parsed())
        width, (x, y) = self.iso_wide(bodies)
        return ShotView(x, y, self.frame_width / width)

    def _iso_tiles(self, picture: Any, name: str) -> IsoTiles:
        """An :class:`IsoTiles` group of ``picture`` showing what the camera sees now, graded by
        the light (with the snow lying on the place now, §90.3); every one made is kept in
        :attr:`_iso_groups`."""
        tiles = IsoTiles(self.iso_scenery, picture, self.iso_view, name=name, density=self._iso_density, frame_width=self.frame_width)
        mark_lit(tiles)
        snow = getattr(self, "iso_snow", None)
        if snow is not None:
            tiles.snow_opacity = snow.cover or 0.0
        tiles.show_view(self.camera.frame)
        self.__dict__.setdefault("_iso_groups", []).append(tiles)
        return tiles

    def get_moving_and_static_mobjects(self, animations: Any) -> tuple[list[Mobject], list[Mobject]]:
        """Manim's split into what it redraws and its static image; on an iso place the pictures
        first show the tiles of the camera's view now (Manim lists the members before it asks
        for the moving ones, which runs the camera listeners: after a cut the static image
        would show the tiles of the view before)."""
        if self.on_iso and hasattr(self, "iso_scenery"):
            self._iso_show_view()
        return super().get_moving_and_static_mobjects(animations)

    def _iso_show_view(self) -> None:
        """Camera listener: every picture of the place on the scene shows the tiles in view."""
        frame = self.camera.frame
        for mob in self.mobjects:
            if isinstance(mob, IsoTiles):
                mob.show_view(frame)
            elif isinstance(mob, IsoObject):
                for tiles in mob.submobjects:
                    tiles.show_view(frame)

    def _iso_front(self, name: str, picture: Any) -> Mobject | None:
        """``name``'s front picture of ``picture`` (made once; ``None`` for no picture), graded by the light."""
        if picture is None:
            return None
        if (name, picture) not in self._iso_front_pictures:
            self._iso_front_pictures[(name, picture)] = self._iso_tiles(picture, f"iso_front_{name}")
        return self._iso_front_pictures[(name, picture)]

    # ----- the draw order of the bodies (DESIGN.md §89.9) ---------------------------------------------

    def _iso_height(self, name: str) -> float:
        """How tall the character or small thing ``name`` is (tile units)."""
        member = next((c for c in self.params.characters if c.name == name), None)
        if member is not None:
            return ISO_CHARACTER_HEIGHT * member.scale
        return ISO_CHARACTER_HEIGHT * self._iso_item_param(name).height_factor()

    def _iso_item_param(self, name: str) -> Any:
        return dict(zip(self.params.prop_names(), self.params.stage_props()))[name]

    def _iso_start_box(self, name: str) -> Box3:
        """The box the character or small thing ``name`` stands in at the start."""
        place = self.params.iso.parsed()
        member = next((c for c in self.params.characters if c.name == name), None)
        feet = iso_stand(place, str(member.at)) if member is not None else iso_item_point(place, str(self._iso_item_param(name).at))
        return self._iso_box(name, feet)

    def _iso_box(self, name: str, feet: tuple[float, float, float]) -> Box3:
        place = self.params.iso.parsed()
        height = self._iso_height(name)
        if name in getattr(self, "cast", {}) or any(c.name == name for c in self.params.characters):
            return standing_box(place, feet, height)
        return item_box(place, feet, height)

    def _iso_body(self, mob: Mobject) -> Box3:
        """The box a character or small thing stands in on the place now (tile units)."""
        return self._iso_box(mob.name, mob.iso_feet)

    def _iso_bodies(self) -> dict[str, Mobject]:
        """The characters and the small things standing on the place (not held), by name."""
        props = {name: prop for name, prop in getattr(self, "props", {}).items() if getattr(prop, "held_by", None) is None}
        return {**self.cast, **props}

    def _iso_keep_order(self) -> bool:
        """On an iso place, each frame while things move or the place changes (DESIGN.md §89.9):
        each character's and small thing's front picture shows the pieces in front of it where
        it is now (swapped when they change), and they are drawn in the order of their boxes
        (:func:`draw_order`) with their front pictures; whether anything changed. A new front
        picture joins what Manim redraws on each frame of the animation playing."""
        changed = False
        added: list[Mobject] = []
        bodies = self._iso_bodies()
        for name in list(self._iso_fronts):
            swapped = self._iso_swap_front(name, bodies)
            if swapped is not None:
                added += [swapped[1]] if swapped[1] is not None else []
                changed = True
        names = list(bodies)
        order = [names[k] for k in draw_order([self._iso_body(bodies[n]) for n in names])]
        shown = sorted((n for n in names if bodies[n] in self.mobjects), key=lambda n: self.mobjects.index(bodies[n]))
        wanted = [n for n in order if n in shown]
        if wanted != shown:
            blocks = {n: [*_moving_block(self, bodies[n]), *([self._iso_fronts[n][1]] if self._iso_fronts[n][1] in self.mobjects else [])]
                      for n in shown}
            taken = {id(m) for block in blocks.values() for m in block}
            at = min(self.mobjects.index(blocks[n][0]) for n in shown)
            rest = [m for m in self.mobjects if id(m) not in taken]
            before = sum(1 for m in self.mobjects[:at] if id(m) not in taken)
            self.mobjects[:] = rest[:before] + [m for n in wanted for m in blocks[n]] + rest[before:]
            self._shadows_first()
            changed = True
        if added and getattr(self, "animations", None):
            self.moving_mobjects = [*self.moving_mobjects, *(m for front in added for m in front.get_family())]
        return changed

    def _iso_swap_front(self, name: str, bodies: dict[str, Mobject], keep: bool = False) -> tuple[Mobject | None, Mobject | None] | None:
        """Give the body ``name`` the front picture of the pieces in front of it where it is now:
        ``(old, new)`` front groups when it changed (``None``: it did not). ``keep``: the old one
        stays in the scene right over the new one (a change of the place fades from one to the
        other, §90.15)."""
        picture, front = self._iso_fronts[name]
        figure = bodies.get(name)
        new_picture = None if figure is None else self.iso_scenery.front(self._iso_body(figure))
        if new_picture == picture:
            return None
        new = self._iso_front(name, new_picture)
        if new is not None and new in self.mobjects:   # still fading out after an earlier change
            self.mobjects.remove(new)
        if front is not None and front in self.mobjects:
            at = self.mobjects.index(front)
            if not keep:
                self.mobjects.remove(front)
        else:
            block = _moving_block(self, figure) if figure is not None else []
            at = self.mobjects.index(block[-1]) + 1 if block else len(self.mobjects)
        if new is not None:
            self.mobjects.insert(at, new)
        self._iso_fronts[name] = (new_picture, new)
        return front, new

    def _iso_follow_change(self, change: _IsoChange) -> None:
        """When ``change`` starts, the other pictures showing its object follow it as it fades
        (§90.15): the layers of the objects it stands in front of and the bodies' front pictures,
        each new one right under the old one. Swapped at once, they showed an object appearing
        at full at the start of its fade (and one going, gone at once where it was in front)."""
        layers = self._iso_refresh_layers(change.name)
        follows = [_IsoFollow(change, old, new, holder) for old, new, holder in layers if holder is not None]
        added: list[Mobject] = [new for _, new, _ in layers]   # made now, mid-play: Manim must redraw them
        bodies = self._iso_bodies()
        for name in list(self._iso_fronts):
            swapped = self._iso_swap_front(name, bodies, keep=True)
            if swapped is not None:
                follows.append(_IsoFollow(change, *swapped))
                added += [swapped[1]] if swapped[1] is not None else []
        for follow in follows:
            if not self._iso_follow_on(follow):
                self._iso_follow_step(follow, 0.0)
                self._iso_follows.append(follow)
        if added and getattr(self, "animations", None):
            self.moving_mobjects = [*self.moving_mobjects, *(m for front in added for m in front.get_family())]
            self.moving_mobjects = self._moving_in_order()

    def _iso_follow_on(self, follow: _IsoFollow) -> bool:
        """When ``follow`` starts from the picture an earlier one under way fades to (two changes
        at once), the earlier one fades to ``follow``'s new picture instead (in its place, as
        far through): whether it did."""
        earlier = next((f for f in self._iso_follows if f.parent is follow.parent and follow.old is not None and f.new is follow.old), None)
        if earlier is None:
            return False
        siblings = follow.parent.submobjects if follow.parent is not None else self.mobjects
        if follow.new is not None:
            follow.new.set_tile_opacity(follow.old.tile_opacity)
        if follow.old in siblings:
            siblings.remove(follow.old)
        self._iso_undraw(follow.old)
        follow.old.set_tile_opacity(1.0)
        earlier.new = follow.new
        return True

    def _iso_undraw(self, mob: Mobject) -> None:
        """``mob`` taken out of the scene mid-play is no longer drawn: Manim draws the list of
        moving mobjects it made when the animation began (one left in it was drawn on, at full
        once its fade was undone: a hidden object showed again until the next animation)."""
        if getattr(self, "animations", None) and self.moving_mobjects:
            gone = {id(m) for m in mob.get_family()}
            self.moving_mobjects = [m for m in self.moving_mobjects if id(m) not in gone]

    @staticmethod
    def _iso_follow_step(follow: _IsoFollow, share: float) -> None:
        """Show ``follow`` ``share`` of the way through its change: a picture alone fades in or
        out with it; with both, the new one fades in under the old one in the first half and the
        old one fades out over it in the second (what both show stays as it is: never half seen
        through, never drawn twice when the change is over)."""
        if follow.old is None:
            if follow.new is not None:
                follow.new.set_tile_opacity(share)
        elif follow.new is None:
            follow.old.set_tile_opacity(1.0 - share)
        else:
            follow.new.set_tile_opacity(min(1.0, 2.0 * share))
            follow.old.set_tile_opacity(1.0 - max(0.0, 2.0 * share - 1.0))

    def _iso_follow_end(self, follow: _IsoFollow) -> None:
        """``follow``'s change is over: the new picture as it is, the old one gone (shown fully
        again: a body's front pictures are kept for later)."""
        if follow.new is not None:
            follow.new.set_tile_opacity(1.0)
        if follow.old is None:
            return
        siblings = follow.parent.submobjects if follow.parent is not None else self.mobjects
        if follow.old in siblings:
            siblings.remove(follow.old)
        self._iso_undraw(follow.old)
        follow.old.set_tile_opacity(1.0)

    def _iso_redrawn(self, animations: tuple[Animation, ...]) -> set[int]:
        """While a character walks on an iso place: the ids of the characters, small things,
        their front pictures and the moving shadows (their order and the front pictures change,
        §89.9); while a change of the place fades during the animation, the objects' pictures
        (everything drawn after them is redrawn with them, §89.10)."""
        if self.params.iso is None:
            return set()
        found: set[int] = set()
        if any(isinstance(anim, IsoWalk) for anim in animations):
            things: list[Mobject] = [*self._iso_bodies().values(), *(front for _, front in self._iso_fronts.values() if front is not None)]
            if getattr(self, "_moving_shadows", None) is not None:
                things.append(self._moving_shadows)
            found |= {id(m) for thing in things for m in thing.get_family()}
        now = float(self.renderer.time)
        duration = getattr(self, "duration", None)
        end = now + (math.inf if duration is None else float(duration))
        if any(change.start <= end and change.start + change.seconds >= now for change in self._iso_changes):
            found |= {id(m) for holder in self.iso_objects.values() for m in holder.get_family()}
        lamps = getattr(self, "_iso_lamps", {})
        if any(start <= end and start + seconds >= now for _, events in lamps.values() for start, seconds, _ in events[1:]):
            found |= {id(m) for body in [*self.cast.values(), *self.props.values()] for m in body.get_family()}   # lamplight (§89.13)
        return found

    # ----- small things (DESIGN.md §89.10) ----------------------------------------------------------

    def iso_put_point(self, character: Character, to: Any) -> tuple[float, float, float]:
        """Where ``character`` puts a small thing down (tile units): at the spot ``to`` (on a
        table there), else on the ground beside its feet in its own cell, on the side it faces
        across the picture."""
        place = self.iso_place_now()
        if isinstance(to, str) and to in place.spot_names():
            return iso_item_point(place, to)
        x, y, z = character.iso_feet
        column, row = math.floor(x), math.floor(y)
        side = -1.0 if character.facing == "left" else 1.0
        reach = ISO_PUT_ASIDE
        x = min(max(x + side * reach, column + 0.08), column + 0.92)
        y = min(max(y - side * reach, row + 0.08), row + 0.92)
        return (x, y, place.stand_z(column, row))

    def iso_put_down(self, prop: Prop, ground: float) -> None:
        """``prop`` (put down) stands on the place again: on the ground ``ground`` (its shadow's
        y), in the draw order with the others."""
        self.grounds[prop.name] = ground
        self._watch_draw_order()

    # ----- changes of the place (DESIGN.md §89.10) ---------------------------------------------------

    def iso_change(self, name: str, start: float, seconds: float, **fields: bool) -> bool:
        """Change the object (or map door) ``name`` from scene time ``start`` over ``seconds``:
        ``shown``, ``open``, ``on`` (:class:`~vidgen.world.iso.ObjectState`), after the changes
        planned so far; its new picture fades in over the old one. Whether anything changes."""
        planned = self._iso_planned_states[name]
        state = replace(planned, **fields)
        if state == planned:
            return False
        self._iso_planned_states[name] = state
        holder = self.iso_objects[name]
        old = holder.submobjects[-1] if holder.submobjects else None
        scenery = self.iso_scenery
        k = scenery.index[name]
        now_state, scenery.states[k] = scenery.states[k], state
        picture = scenery.layer(name)
        scenery.states[k] = now_state
        new = self._iso_tiles(picture, f"iso_{name}") if picture is not None else None
        if new is not None:
            new.set_tile_opacity(0.0)
            holder.add(new)
            if holder not in self.mobjects:
                self._iso_insert(holder)
        self._iso_changes.append(_IsoChange(name, state, float(start), max(float(seconds), 1e-3), old, new))
        if "shown" in fields:
            change = "reveal" if fields["shown"] else "hide"
        elif "open" in fields:
            change = "open" if fields["open"] else "close"
        else:
            change = "switch_on" if fields.get("on") else "switch_off"
        self.iso_watch(change, name, float(start), float(seconds), self._iso_object_box(name))
        if name in getattr(self, "_iso_lamps", {}):   # its light on the characters near it fades with it (§89.13)
            self._iso_lamps[name][1].append((float(start), max(float(seconds), 1e-3), 1.0 if state.on and state.shown else 0.0))
        if self._foley_on():   # a door's creak, a bloom, an appearance (§89.11)
            kind = self.iso_scenery.pieces[k].kind or "door"
            for cue in place_change_cues(kind, fields.get("open"), fields.get("shown"), float(start), float(seconds)):
                self.sfx(cue.sound, max(cue.time, 0.0), gain=cue.gain, align=cue.align, **cue.params)
        if not any(f is self._iso_change_updater for f in self.updaters):
            self.add_updater(self._iso_change_updater)
        return True

    def _iso_insert(self, holder: IsoObject) -> None:
        """Put ``holder`` in the draw order: right after the base picture and the objects drawn
        before it (in the set still to come in when the scene's entrance has not played yet)."""
        order = [self.iso_scenery.pieces[k].name for k in self.iso_scenery.layered]
        before = [self.iso_objects[n] for n in order[:order.index(holder.name)]]
        drawn = self.mobjects if any(isinstance(m, IsoTiles) and m.name == "iso_place" for m in self.mobjects) else self._backdrop
        if any(m is holder for m in drawn):
            return
        at = next(k for k, m in enumerate(drawn) if isinstance(m, IsoTiles) and m.name == "iso_place") + 1
        for k, mob in enumerate(drawn):
            if any(mob is other for other in before):
                at = max(at, k + 1)
        drawn.insert(at, holder)

    def _iso_change_step(self, dt: float) -> None:
        """Scene updater while the place changes: each change's new picture fades in over the
        old one from its start; then the old one leaves (and a gone object's group), the object's
        state counts, the other pictures showing it follow (the front pictures, the layers of
        the objects behind it); it removes itself once every change is over."""
        now = float(self.renderer.time)
        for change in self._iso_changes:
            if now < change.start:
                continue
            if not change.applied:
                change.applied = True
                self.iso_scenery.set_state(change.name, change.state)
                self._iso_follow_change(change)
                self._watch_draw_order()
            share = smooth(min(max((now - change.start) / change.seconds, 0.0), 1.0))
            if change.new is not None:
                change.new.set_tile_opacity(share)
            elif change.old is not None:
                change.old.set_tile_opacity(1.0 - share)
            for follow in [f for f in self._iso_follows if f.change is change]:
                if share >= 1.0:
                    self._iso_follow_end(follow)
                    self._iso_follows.remove(follow)
                else:
                    self._iso_follow_step(follow, share)
            if share >= 1.0:
                holder = self.iso_objects[change.name]
                if change.old is not None and change.old in holder.submobjects:
                    holder.remove(change.old)
                    self._iso_undraw(change.old)
                if not holder.submobjects and holder in self.mobjects:
                    self.mobjects.remove(holder)
        self._iso_changes = [c for c in self._iso_changes if not (c.applied and now >= c.start + c.seconds)]
        if not self._iso_changes:
            self.remove_updater(self._iso_change_updater)

    def iso_lamplight(self) -> None:
        """Let the place's lamps light the characters and small things near them (DESIGN.md
        §89.13): each is graded by the stage's light with a lamp's light on it
        (:class:`LampLit`), as much as :meth:`_iso_lamp_share` says when it is drawn."""
        place = self.params.iso.parsed()
        scenery = self.iso_scenery
        #: each lamp's middle (tile units) and its light from the start: (scene time, seconds, level)
        self._iso_lamps: dict[str, tuple[tuple[float, float], list[tuple[float, float, float]]]] = {}
        for item in place.objects:
            if item.kind == "lamp":
                state = scenery.states[scenery.index[item.name]]
                self._iso_lamps[item.name] = ((item.column + 0.5, item.row + 0.5), [(0.0, 0.0, 1.0 if state.on and state.shown else 0.0)])
        if not self._iso_lamps:
            return
        self._iso_lamp_shares: dict[str, float] = {}
        self._iso_lamp_time = -1.0
        for name, mob in [*self.cast.items(), *getattr(self, "props", {}).items()]:
            mark_lamp_lit(mob, LampLit(lambda name=name: self._iso_lamp_share(name)))

    def _iso_lamp_level(self, name: str, now: float) -> float:
        """How lit the lamp ``name`` is at scene time ``now`` (0..1), fading with its switches."""
        events = self._iso_lamps[name][1]
        level = events[0][2]
        for start, seconds, target in sorted(events[1:]):
            if now <= start:
                break
            level += (target - level) * smooth(min((now - start) / seconds, 1.0))
        return level

    def _iso_lamp_share(self, name: str) -> float:
        """How much lamplight falls on the character or small thing ``name`` now (a held thing:
        as on its holder), 0..1: the most of any lamp's, by the distance of its feet from the
        lamp (:data:`ISO_LAMP_REACH`) times how lit the lamp is."""
        now = float(self.renderer.time)
        if now != self._iso_lamp_time:
            self._iso_lamp_time, self._iso_lamp_shares = now, {}
        if name in self._iso_lamp_shares:
            return self._iso_lamp_shares[name]
        mob = self.cast[name] if name in self.cast else self.props.get(name)
        holder = getattr(mob, "held_by", None)
        if holder is not None and holder in self.cast:
            mob = self.cast[holder]
        feet = getattr(mob, "iso_feet", None)
        share = 0.0
        if feet is not None:
            near, far = ISO_LAMP_REACH
            for lamp, ((x, y), _) in self._iso_lamps.items():
                reach = min(max((far - math.hypot(feet[0] - x, feet[1] - y)) / (far - near), 0.0), 1.0)
                if reach > 0:
                    share = max(share, smooth(reach) * self._iso_lamp_level(lamp, now))
        self._iso_lamp_shares[name] = share
        return share

    def _iso_refresh_layers(self, changed: str) -> list[tuple[Mobject | None, Mobject, IsoObject | None]]:
        """The layers of the other objects that show ``changed`` (it stands in front of them)
        drawn again as it is now, each added right under the old one in its holder (they fade
        from one to the other with the change, §90.15): ``(old, new, holder)`` of each. An object
        fading in by a change of its own is drawn again in its place at the opacity it has now
        (it goes on fading in; swapped for a whole picture, it showed at full): ``(None, new,
        None)``."""
        out = []
        for name, holder in self.iso_objects.items():
            if name == changed or not holder.submobjects or self._iso_planned_states[name] != self.iso_scenery.states[self.iso_scenery.index[name]]:
                continue
            current = holder.submobjects[-1]
            following = [f for f in self._iso_follows if f.parent is holder]
            if following:   # still fading after an earlier change: the picture it fades to
                current = following[-1].new
            picture = self.iso_scenery.layer(name)
            if picture is None or current.picture == picture:
                continue
            new = self._iso_tiles(picture, f"iso_{name}")
            own = next((c for c in self._iso_changes if c.name == name and c.applied and c.new is current), None)
            if own is not None:
                new.set_tile_opacity(current.tile_opacity)
                holder.submobjects[holder.submobjects.index(current)] = new
                self._iso_undraw(current)
                own.new = new
                out.append((None, new, None))
                continue
            holder.submobjects.insert(holder.submobjects.index(current), new)
            out.append((current, new, holder))
        return out

    def iso_reveal(self, name: str) -> list[Animation]:
        """The ``reveal`` of an object that is not there: it fades in from now (none to play: the
        change runs by the scene's clock)."""
        self.iso_change(name, float(self.renderer.time), ISO_REVEAL_SECONDS, shown=True)
        return []

    def iso_hide(self, patterns: list[str], time: float, seconds: float) -> list[str]:
        """The objects matching ``patterns`` fade out from scene ``time`` over ``seconds`` (the
        ``hide`` action); the names that go."""
        names = [name for name in self.iso_objects if any(fnmatchcase(name, pat) for pat in patterns)]
        return [name for name in names if self.iso_change(name, time, seconds, shown=False)]

    def iso_switch(self, patterns: list[str], on: bool, time: float) -> list[str]:
        """Switch the lamps and houses matching ``patterns`` on (or off) at scene ``time`` (the
        ``switch_on`` / ``switch_off`` actions): the lamp lights, the house's windows glow. The
        names switched."""
        names = [name for name in self.iso_objects if any(fnmatchcase(name, pat) for pat in patterns)]
        return [name for name in names if self.iso_change(name, time, ISO_SWITCH_SECONDS, on=on)]

    # ----- what the camera shows of the beat's actions (DESIGN.md §89.11) -------------------------------

    def iso_watch(self, action: str, who: str, start: float, seconds: float, box: Callable[[], tuple[float, float, float, float] | None]) -> None:
        """Watch the ``action`` of ``who`` from scene time ``start`` for ``seconds``: on how many
        of its frames the camera shows it (``box()``; lint ``offscreen_action``)."""
        beat = self.current_beat
        if beat is None:
            return
        watched = self.__dict__.setdefault("_iso_watched", [])
        watched.append(_Watched(beat.id, action, who, float(start), float(start) + max(float(seconds), 0.0), box))
        if "_iso_look_updater" not in self.__dict__:   # kept: Manim removes an updater by identity
            self._iso_look_updater = lambda dt: self._iso_look()
        if not any(f is self._iso_look_updater for f in self.updaters):
            self.add_updater(self._iso_look_updater)   # from the next frame (a shot of the beat cuts as it plays)

    def _iso_look(self) -> None:
        """What the camera shows now of each watched action of the beat under way; the scene
        updater doing it on every frame leaves once each is wholly seen or its beat is over (a
        scene updater makes Manim draw every frame of a wait)."""
        now = float(self.renderer.time)
        beat = self.current_beat
        step = 1.0 / config.frame_rate
        pending = False
        for item in self.__dict__.get("_iso_watched", []):
            if beat is None or item.beat != beat.id or (item.frames and now > item.end + step / 2):
                continue
            if now >= item.start - step / 2:
                item.frames += 1
                item.shown += _in_view(item.box(), self.camera.frame)
            pending = pending or now < item.end
        if not pending and "_iso_look_updater" in self.__dict__:
            self.remove_updater(self._iso_look_updater)

    def _iso_body_box(self, mob: Mobject) -> Callable[[], tuple[float, float, float, float] | None]:
        def box() -> tuple[float, float, float, float] | None:
            if mob not in self.mobjects and not any(mob in m.get_family() for m in self.mobjects):
                return None
            return float(mob.get_left()[0]), float(mob.get_bottom()[1]), float(mob.get_right()[0]), float(mob.get_top()[1])
        return box

    def _iso_object_box(self, name: str) -> Callable[[], tuple[float, float, float, float] | None]:
        piece = self.iso_scenery.pieces[self.iso_scenery.index[name]]
        left, top, right, bottom = piece.box.picture_bounds()
        view = self.iso_view
        found = ((left - view.u0) * view.unit, -(bottom - view.v0) * view.unit, (right - view.u0) * view.unit, -(top - view.v0) * view.unit)
        return lambda: found

    def iso_watch_action(self, action: str, animations: Any, start: float, seconds: float) -> None:
        """Watch a built-in action as it plays from scene time ``start`` for ``seconds`` (from
        :meth:`action_foley`): each character walking, and the character picking up, giving or
        putting down a small thing."""
        for anim in animations:
            if isinstance(anim, IsoWalk):
                self.iso_watch(action, anim.mobject.name, start, seconds, self._iso_body_box(anim.mobject))
        if action in ISO_ITEM_ACTIONS:
            movers = {m.name: m for m in (getattr(anim, "mobject", None) for anim in animations) if isinstance(m, Character)}
            for name, figure in movers.items():
                self.iso_watch(action, name, start, seconds, self._iso_body_box(figure))

    def layout_keys(self, beat_id: str | None) -> dict[str, Any]:
        """What the layout dump adds to a still of ``beat_id`` on an iso place (DESIGN.md §89.11):
        ``line_words`` (the beat's words: a short line a name tag may carry) and ``iso_actions``
        (the beat's watched actions, each with the share of its frames on which the camera
        showed it)."""
        if not self.on_iso or beat_id is None:
            return {}
        beat = self.beat(beat_id)
        acts = [{"action": w.action, "who": w.who, "seen": round(w.seen, 4)} for w in self.__dict__.get("_iso_watched", []) if w.beat == beat_id and w.frames]
        return {"line_words": len(beat.text.split()), **({"iso_actions": acts} if acts else {})}

    # ----- who speaks (DESIGN.md §89.11) -----------------------------------------------------------

    def speak(self, character: Any) -> None:
        """As any scene's (lip sync for the beat); on an iso place with ``name_tags`` a name tag
        over its head shows while it speaks and is small on screen (:class:`NameTag`)."""
        super().speak(character)
        if self.on_iso and self.params.iso.name_tags and isinstance(character, Character):
            self._iso_name_tag(character)

    def _iso_name_tag(self, character: Character) -> None:
        tags = self.__dict__.setdefault("_iso_tags", {})
        old = tags.pop(character.name, None)
        if old is not None and old in self.mobjects:
            self.remove(old)
        config = self.project.config
        entry = next((c for c in config.characters if c.name == character.name), None)
        voice = entry.voice if entry is not None and entry.voice in config.voices else None
        label = config.voices[voice].label if voice is not None else None
        text = label or (character.name.replace("_", " ")[:1].upper() + character.name.replace("_", " ")[1:])
        fill = speaker_color(config, voice, self.theme) if voice is not None else "#FFFFFF"
        tag = NameTag(text, fill, self.theme, character, character.lip_sync_track)
        top = max((m.z_index for m in self.get_mobject_family_members()), default=0)
        tag.set_z_index(top + 2)
        tag.place(self.camera.frame, self.frame_width)
        tag.add_updater(lambda m: m.place(self.camera.frame, self.frame_width))
        tags[character.name] = tag
        self.add(tag)

    def iso_untag(self, name: str) -> None:
        """``name`` speaks with a speech bubble now: no name tag (the bubble's tail shows who speaks)."""
        tag = self.__dict__.get("_iso_tags", {}).get(name)
        if tag is not None:
            tag.bubbled = True
            tag.place(self.camera.frame, self.frame_width)

    def _iso_drop_tags(self) -> None:
        """Take the name tags of the lines that have ended off the scene."""
        tags = self.__dict__.get("_iso_tags", {})
        for name, tag in list(tags.items()):
            if tag.speaker.lip_sync_track is not tag.track:
                tag.speaker.name_tagged = False
                if tag in self.mobjects:
                    self.remove(tag)
                del tags[name]

    # ----- weather (DESIGN.md §89.11) ----------------------------------------------------------------

    def iso_rain_ground(self) -> IsoRainGround:
        """Where rain ends on the place now: anywhere on its ground as the camera sees it (the
        front and back edge of the place's picture at each x, within the view), but on the
        characters and small things standing there (no splash on a face)."""
        if getattr(self, "_iso_outline", None) is None:
            self._iso_outline = place_outline(self.params.iso.parsed(), self.iso_view)
        xs, fronts, backs = self._iso_outline
        frame = self.camera.frame
        cy, half = float(frame.get_center()[1]), float(frame.height) / 2
        bodies = tuple((float(m.get_left()[0]), float(m.get_bottom()[1]), float(m.get_right()[0]), float(m.get_top()[1]))
                       for m in self._iso_bodies().values() if m in self.mobjects)
        return IsoRainGround(cy - half, cy - half, cy + half, self.frame_height, (), xs, fronts, backs, bodies, lift=self._iso_shelter_lift())

    def _iso_shelter_lift(self) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
        """How much higher (Manim units) a drop landing on the ground seen at (``x``, ``y``) lands:
        on the top of what keeps the rain off there now (:func:`~vidgen.cartoon.iso_weather.lift_floors`
        over the place's top surface, DESIGN.md §90.2)."""
        surface, view = self.iso_scenery.top_surface(), self.iso_view

        def lift(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            return lift_floors(x / view.unit + view.u0, view.v0 - y / view.unit, surface) * view.unit

        return lift

    def iso_lay_puddles(self, field: Any, settings: Any) -> None:
        """Puddles growing on the place's ground cells while the rain ``field`` falls (``settings``:
        its seed), with ripples while it rains (:class:`IsoPuddles`, DESIGN.md §90.2), laid over
        the place's pictures under the shadows and the characters."""
        scenery = self.iso_scenery
        boxes = [piece.box for k, piece in enumerate(scenery.pieces) if scenery.shown(k)]
        spots = iso_puddles(self.iso_place_now(), scenery.top_surface(), boxes, settings.seed)
        if not spots:
            return
        puddles = IsoPuddles(spots, self.iso_view, start=field.start, ended=lambda: field.ended, clock=lambda: float(self.renderer.time))
        mark_lit(puddles)
        self.puddles.append(puddles)
        self._lay_on_ground(puddles)

    def iso_settle_snow(self, field: Any, settings: Any) -> None:
        """Snow from the settling ``field`` lies on the place (``settings``: its density and
        ``settled``): every picture shows its snow tiles, more and more opaque as it snows
        (:class:`IsoSnow`, DESIGN.md §90.3); one layer for all the scene's settling fields."""
        snow = getattr(self, "iso_snow", None)
        if snow is None:
            left, top, right, bottom = self.iso_scenery.bounds
            view = self.iso_view
            region = ((left - view.u0) * view.unit, -(bottom - view.v0) * view.unit, (right - view.u0) * view.unit, -(top - view.v0) * view.unit)
            snow = IsoSnow(lambda: list(self.__dict__.get("_iso_groups", [])), region)
            self.iso_snow = snow
            self.snow_layers.append(snow)
        snow.add_fall(field.start, lambda: field.ended, settings.density, settings.settled)
        self._watch_living()

    # ----- the camera (DESIGN.md §89.10) -------------------------------------------------------------

    def _iso_span(self, mob: Mobject) -> tuple[float, float, float]:
        """``(x, feet y, head-top y)`` of a character (or the middle and bottom and top of another
        mobject) on screen."""
        if isinstance(mob, Character):
            tops = [mob.parts[part].get_top()[1] for part in ("head", "accessory") if mob.has_part(part)]
            return float(mob.feet()[0]), float(mob.feet()[1]), float(max(tops) if tops else mob.get_top()[1])
        return float(mob.get_center()[0]), float(mob.get_bottom()[1]), float(mob.get_top()[1])

    def follow_start(self, mob: Mobject) -> tuple[float, np.ndarray, Callable[[], float]] | None:
        """On an iso place, the view a ``follow`` of ``mob`` moves to first: zoomed in until a
        character is :data:`~vidgen.cartoon.iso_stage.ISO_FOLLOW_SIZE` of the frame's shorter
        side (unless the camera is closer already), centred on it, and the y it keeps centred
        on meanwhile (``(width, centre, y_of)``); ``None`` elsewhere (the follow keeps the
        camera's zoom)."""
        if not self.on_iso:
            return None
        frame = self.camera.frame
        x, feet, head = self._iso_span(mob)
        width = follow_width(head - feet, self.frame_width, self.frame_height, float(frame.width))
        height = width * self.frame_height / self.frame_width
        center = view_center_within(self.camera_bounds(), (x, (feet + head) / 2), width, height)

        def y_of() -> float:   # the body's middle as it stands (not bobbing with each step)
            if isinstance(mob, Character):
                return float(mob.feet()[1]) + mob.standing_height / 2
            return float(mob.get_center()[1])

        return width, np.array([*center, 0.0]), y_of

    def pan_width(self) -> float:
        """The view's width a ``pan`` to a spot or a character of the place moves to: the
        camera's now, but at least :data:`ISO_PAN_ZOOM` times closer than the whole place, so a
        pan from the wide view moves in to its target (the wide view has little room to move
        in, DESIGN.md §89.13)."""
        return min(float(self.camera.frame.width), self.frame_width / ISO_PAN_ZOOM)

    def pan_point(self, targets: list[Mobject], to: Any) -> tuple[float, float] | None:
        """On an iso place, where a ``pan`` centres the view: the middle of ``targets`` (their
        bodies), or the spot ``to`` (the object standing there, else a character's middle
        standing there); ``None`` elsewhere (a pan moves sideways only)."""
        if not self.on_iso:
            return None
        if targets:
            spans = [self._iso_span(mob) for mob in targets]
            return float(np.mean([x for x, _, _ in spans])), float(np.mean([(f + h) / 2 for _, f, h in spans]))
        place = self.params.iso.parsed()
        if not isinstance(to, str) or to not in place.spot_names():
            return None
        spot = place.spot(to)
        item = place.object_at(spot.column, spot.row)
        if item is not None and not item.walkable:   # the object standing there: its middle
            left, top, right, bottom = object_box(item, place.floor_z(item.column, item.row)).picture_bounds()
            view = self.iso_view
            return (left + right) / 2 * view.unit - view.u0 * view.unit, -((top + bottom) / 2 - view.v0) * view.unit
        x, y = self.iso_view.point(*iso_stand(place, to))
        return x, y + self.iso_view.height(ISO_CHARACTER_HEIGHT) / 2


__all__ = ["ISO_LAMP_REACH", "NAME_TAG_FACE", "NameTag", "iso_particle_problem", "ISO_PUT_ASIDE", "ISO_REVEAL_SECONDS", "ISO_SWITCH_SECONDS", "IsoObject", "IsoStaging", "_moving_block"]
