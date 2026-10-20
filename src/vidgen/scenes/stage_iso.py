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


def iso_particle_problem(iso: Any, kind: str, settings: Any) -> str | None:
    """Why particles of ``kind`` with ``settings`` (``puddles``, ``settle``) cannot fall on the
    iso place ``iso`` (DESIGN.md §89.11): rain, snow, leaves and streaks stay out of an indoor
    place; puddles and settling snow are a flat stage's. ``None``: they can."""
    if iso.place == "indoor" and kind in OUTDOOR_PARTICLES:
        return f"{kind} stays outdoors; an indoor place has none inside (sparkles, dust, confetti, smoke and bubbles work)"
    if getattr(settings, "puddles", False):
        return "puddles are not drawn on an iso place yet; remove puddles (the rain still lands on the place with splashes)"
    if getattr(settings, "settle", False):
        return "settling snow is not drawn on an iso place yet; remove settle (the snow still falls over the place)"
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
        return shown

    def _iso_tiles(self, picture: Any, name: str) -> IsoTiles:
        """An :class:`IsoTiles` group of ``picture`` showing what the camera sees now, graded by the light."""
        tiles = IsoTiles(self.iso_scenery, picture, self.iso_view, name=name, density=self._iso_density, frame_width=self.frame_width)
        mark_lit(tiles)
        tiles.show_view(self.camera.frame)
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
            picture, front = self._iso_fronts[name]
            figure = bodies.get(name)
            new_picture = None if figure is None else self.iso_scenery.front(self._iso_body(figure))
            if new_picture == picture:
                continue
            new = self._iso_front(name, new_picture)
            if front is not None and front in self.mobjects:
                at = self.mobjects.index(front)
                self.mobjects.remove(front)
            else:
                block = _moving_block(self, figure) if figure is not None else []
                at = self.mobjects.index(block[-1]) + 1 if block else len(self.mobjects)
            if new is not None:
                self.mobjects.insert(at, new)
                added.append(new)
            self._iso_fronts[name] = (new_picture, new)
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
                self._iso_refresh_layers(change.name)
                self._watch_draw_order()
            share = smooth(min(max((now - change.start) / change.seconds, 0.0), 1.0))
            if change.new is not None:
                change.new.set_tile_opacity(share)
            elif change.old is not None:
                change.old.set_tile_opacity(1.0 - share)
            if share >= 1.0:
                holder = self.iso_objects[change.name]
                if change.old is not None and change.old in holder.submobjects:
                    holder.remove(change.old)
                if not holder.submobjects and holder in self.mobjects:
                    self.mobjects.remove(holder)
        self._iso_changes = [c for c in self._iso_changes if not (c.applied and now >= c.start + c.seconds)]
        if not self._iso_changes:
            self.remove_updater(self._iso_change_updater)

    def _iso_refresh_layers(self, changed: str) -> None:
        """The layers of the other objects that show ``changed`` (it stands in front of them)
        drawn again as it is now: swapped at once."""
        for name, holder in self.iso_objects.items():
            if name == changed or not holder.submobjects or self._iso_planned_states[name] != self.iso_scenery.states[self.iso_scenery.index[name]]:
                continue
            current = holder.submobjects[-1]
            picture = self.iso_scenery.layer(name)
            if picture is None or current.picture == picture:
                continue
            holder.submobjects[-1] = self._iso_tiles(picture, f"iso_{name}")

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
        return IsoRainGround(cy - half, cy - half, cy + half, self.frame_height, (), xs, fronts, backs, bodies)

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


__all__ = ["NAME_TAG_FACE", "NameTag", "iso_particle_problem", "ISO_PUT_ASIDE", "ISO_REVEAL_SECONDS", "ISO_SWITCH_SECONDS", "IsoObject", "IsoStaging", "_moving_block"]
