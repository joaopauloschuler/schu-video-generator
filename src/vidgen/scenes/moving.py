"""Moving beat actions (DESIGN.md §69.12): ``walk_to``, ``run_to`` (§69.41), ``enter``, ``exit``,
``gesture`` and ``jump`` on the characters of a scene. Written against ``vidgen.api`` only, like
project actions.

The motion is worked out without manim in :mod:`vidgen.cartoon.acting` (walk times, the walk
cycle, where an entrance starts and an exit ends, gestures, jumps) and played with the
:class:`Walk`, :class:`Gesture` and :class:`Jump` animations. A walk lasts its distance over its
speed (:meth:`Action.run_time_for`) plus the wind-up and settle of the character's
``cartoon_motion`` (§69.13), shortened like any action when its beat has less time.
"""

import logging
from typing import Annotated, Any, Literal

from vidgen.api import *

from .acting import _Acting, _characters

log = logging.getLogger("vidgen.actions")

#: Where a walk goes: a mark of the stage, or an x from 0 (left edge) to 1 (right edge).
Place = str | Annotated[float, Field(ge=0.0, le=1.0)]
#: How far back a walk goes on the stage (0 front .. 1 back).
Depth = Annotated[float, Field(ge=0.0, le=1.0)]


class WalkPlace(ActionOptions):
    """Where a walk goes on the stage: a mark or an x, and a depth (DESIGN.md §69.44)."""

    mark: Place | None = None
    """A mark (left, centre, right, ... or the stage's own) or an x from 0 (left edge) to 1 (right edge); default: where it is."""
    depth: Depth | None = None
    """How far back: 0 = the front (the ground line, full size) .. 1 = the back of the stage; default: its depth now."""


def _place_x(scene: NarratedScene, place: str | float) -> float:
    """``place`` (a mark or an x 0..1 of the stage) in Manim units."""
    left, right = scene.camera_bounds()[:2]
    return left + scene.camera_place(scene.params, place) * (right - left)


def _view(scene: NarratedScene) -> tuple[float, float]:
    """The left and right x of what the camera shows now."""
    frame = scene.camera.frame
    middle = float(frame.get_center()[0])
    return middle - frame.width / 2, middle + frame.width / 2


def _feet_x(character: Character) -> float:
    return float(character.feet()[0])


def _walk_time(character: Character, distance: float, speed: float) -> float:
    """How long ``character`` takes to walk ``distance`` units at ``speed``, with its
    ``cartoon_motion``'s wind-up and settle."""
    return walk_motion_seconds(walk_seconds(distance, speed), character.motion_strength)


def _ended_walk(scene: NarratedScene, character: Character) -> None:
    """Record the beat its walk ends in (the layout dump's ``walked_in``, lint ``walk_overlap``)."""
    beat = scene.current_beat
    character.walked_in = beat.id if beat is not None else None


class _Moving(_Acting):
    """A moving action: its targets must be characters; ``to`` (when it is a place) must be a
    mark of the scene or an x."""

    def _place_problems(self, scene_cls: type[NarratedScene], params: Any, place: str | float | None) -> list[tuple[str, str]]:
        problems = self._target_characters(scene_cls, params)[1]
        if place is None:
            return problems
        try:
            scene_cls.camera_place(params, place)
        except ValueError as exc:
            problems.append(("to", str(exc)))
        return problems


def _walk_problems(params: Any, to: Any, depth: float | None) -> list[tuple[str, str]]:
    """A walk names where it goes (``to`` or ``depth``), its depth once, and, in a room, not
    behind the wall (DESIGN.md §69.44)."""
    inner = to.depth if isinstance(to, WalkPlace) else None
    if to is None and depth is None:
        return [("to", "say where it walks: to (a mark or an x, or {mark, depth}) and / or depth")]
    if isinstance(to, WalkPlace) and to.mark is None and to.depth is None:
        return [("to", "give the place a mark and / or a depth: {mark: right, depth: 0.4}")]
    if inner is not None and depth is not None:
        return [("depth", "give the depth once: in to ({mark, depth}) or as depth, not both")]
    wall = params.wall_depth() if hasattr(params, "wall_depth") else None
    going = inner if inner is not None else depth
    if wall is not None and going is not None and going > wall + SAME_DEPTH:
        return [("depth", f"depth {going} is behind the room's wall (at depth {wall}); walk to at most {wall}")]
    return []


@action("walk_to")
class WalkTo(_Moving):
    """The target character walks along the ground to ``to`` (a mark of the stage, or an x from 0
    = left to 1 = right), facing the way it goes, at ``speed`` (Manim units per second; the frame's
    shorter side is 8). ``depth`` (or ``to: {mark, depth}``) walks it towards (smaller) or away
    from (larger) the camera too: it grows or shrinks, its shadow with it, and passes in front of
    or behind the others on the way; walking only in depth it keeps its facing (``facing: front``:
    it steps towards the camera). It takes as long as the distance needs (``run_time`` sets it
    instead); a beat shorter than that speeds it up. It stays there."""

    class Options(ActionOptions):
        to: WalkPlace | Place | None = None
        """Where it walks: a mark (left, centre, right, ... or the stage's own), an x from 0 (left edge) to 1 (right edge) of the stage, or {mark, depth}; default: where it is (with depth)."""
        depth: Depth | None = None
        """How far back it walks to: 0 = the front (the ground line, full size) .. 1 = the back of the stage, smaller; default: its depth now."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second (the frame's shorter side is 8 units; a stage character is about 3.6 tall)."""

    run_time = 2.0

    def _destination(self) -> tuple[Any, float | None]:
        """Where it goes (a mark or an x; ``None``: its x now) and to what depth (``None``: its own)."""
        to = self.options.to
        if isinstance(to, WalkPlace):
            return to.mark, to.depth if to.depth is not None else self.options.depth
        return to, self.options.depth

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        place = self._destination()[0]
        return self._place_problems(scene_cls, params, place) + _walk_problems(params, self.options.to, self.options.depth)

    def _goal(self, scene: NarratedScene, character: Character) -> tuple[float, float | None]:
        """The x it walks to and its depth there (``None``: no walk in depth on this scene)."""
        place, depth = self._destination()
        x = _feet_x(character) if place is None else _place_x(scene, place)
        if depth is not None and not hasattr(scene, "feet_y_at"):
            log.warning("scene '%s': %s depth needs a stage; it walks across only", scene.spec.id, self.label)
            depth = None
        return x, depth

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        times = []
        for c in _characters(scene, targets, self.label):
            x, depth = self._goal(scene, c)
            far = abs(x - _feet_x(c)) if depth is None else depth_walk_distance(x - _feet_x(c), c.stage_depth, depth, c.character_height)
            times.append(_walk_time(c, far, self.options.speed))
        return max(times, default=None)

    #: Its action name (in log messages) and how it moves its feet (a run: :data:`RUNNING`).
    label = "walk_to"
    gait = WALKING

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`Walk` to the place (and depth) for each character not there yet."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, self.label):
            x, depth = self._goal(scene, character)
            deeper = depth is not None and abs(depth - character.stage_depth) > SAME_DEPTH
            if abs(x - _feet_x(character)) <= 1e-6 and not deeper:
                continue
            if not deeper:
                anims.append(Walk(character, x, speed=self.options.speed, gait=self.gait))
            else:
                carried = [p for p in getattr(scene, "props", {}).values() if getattr(p, "held_by", None) == character.name]
                walk = Walk(character, x, speed=self.options.speed, gait=self.gait, depth=depth, feet_y=scene.feet_y_at, carried=carried)
                anims.append(walk)
                scene.walk_in_depth(character, walk)
            _ended_walk(scene, character)
        return anims


@action("run_to")
class RunTo(WalkTo):
    """The target character runs along the ground to ``to`` (a mark of the stage, or an x from 0
    = left to 1 = right): a walk at running ``speed`` with longer strides, bigger swings and the
    body leaning forward. With motion effects (``cartoon_motion`` not none) dust puffs up where
    it sets off and stops and speed lines trail it."""

    class Options(ActionOptions):
        to: WalkPlace | Place | None = None
        """Where it runs: a mark (left, centre, right, ... or the stage's own), an x from 0 (left edge) to 1 (right edge) of the stage, or {mark, depth}; default: where it is (with depth)."""
        depth: Depth | None = None
        """How far back it runs to: 0 = the front (the ground line, full size) .. 1 = the back of the stage, smaller; default: its depth now."""
        speed: float = Field(RUN_SPEED, gt=0.0, le=20.0)
        """Running speed in units per second (the frame's shorter side is 8 units; a stage character is about 3.6 tall)."""

    run_time = 1.2
    label = "run_to"
    gait = RUNNING


def _door_problems(params: Any, door: str | None, other: str, given: Any) -> list[tuple[str, str]]:
    """``door`` names a door of the stage's room, and the edge option ``other`` is not ``given``
    too (DESIGN.md §69.42)."""
    if door is None:
        return []
    doors = params.door_names() if hasattr(params, "door_names") else []
    problems: list[tuple[str, str]] = []
    if door not in doors:
        known = ", ".join(doors) or "none (add room: {doors: [...]} to the stage)"
        problems.append(("door", f"no door '{door}' on this stage (its room's doors: {known})"))
    if given is not None:
        problems.append(("door", f"give {other} (an edge) or door, not both"))
    return problems


def _door_x(scene: NarratedScene, name: str) -> float:
    """The x of the room's door ``name`` (opened if it is closed: a character goes through it)."""
    door = scene.door(name)
    if door.shape != "open":
        door.show_shape("open")
    return float(door.feet()[0])


@action("enter")
class Enter(_Moving):
    """The target character walks in from beyond the ``side`` edge of what the camera shows (left
    or right; default: the edge nearer where it goes), or through the room's ``door`` (it opens,
    the character appears in it and walks on), to ``to`` (a mark or an x; default its own mark on
    the stage). On a ``stage`` a character with an enter action waits off stage until then."""

    class Options(ActionOptions):
        side: Literal["left", "right"] | None = None
        """The edge it comes in from: left or right; default: the one nearer where it goes."""
        door: str | None = None
        """Instead of side: a door of the stage's room (its name) it comes in through."""
        to: Place | None = None
        """Where it walks to: a mark or an x from 0 to 1 of the stage; default: its own mark (its at on the stage)."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second."""

    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._place_problems(scene_cls, params, self.options.to) + _door_problems(params, self.options.door, "side", self.options.side)

    def _path(self, scene: NarratedScene, character: Character, *, opening: bool = False) -> tuple[str, float, float]:
        if self.options.to is not None:
            to_x = _place_x(scene, self.options.to)
        else:
            to_x = getattr(scene, "homes", {}).get(character.name, _feet_x(character))
        if self.options.door is not None:
            door = scene.door(self.options.door)
            return "door", _door_x(scene, self.options.door) if opening else float(door.feet()[0]), to_x
        return enter_path(self.options.side, to_x, _view(scene), character.width / 2)

    def _seconds(self, character: Character, start: float, end: float) -> float:
        walk = _walk_time(character, end - start, self.options.speed)
        return max(walk, 2 * DOOR_FADE_SECONDS) if self.options.door is not None else walk

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        times = []
        for character in _characters(scene, targets, "enter"):
            _, start, end = self._path(scene, character)
            times.append(self._seconds(character, start, end))
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Put each character just beyond the view's edge, or in the open door, and walk it in
        (fading in at the door)."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "enter"):
            _, start, end = self._path(scene, character, opening=True)
            door = {} if self.options.door is None else {"fade_in": DOOR_FADE_SECONDS, "run_time": self._seconds(character, start, end)}
            anims.append(Walk(character, end, start_x=start, speed=self.options.speed, **door))
            _ended_walk(scene, character)
        return anims


@action("exit")
class Exit(_Moving):
    """The target character walks out of what the camera shows, beyond its ``to`` edge (left or
    right; default: the nearer one), or out through the room's ``door`` (it opens; the character
    fades away in it), and then waits off the stage (an ``enter`` brings it back). A camera
    following it stops following (and stays)."""

    class Options(ActionOptions):
        to: Literal["left", "right"] | None = None
        """The edge it leaves by: left or right; default: the nearer one."""
        door: str | None = None
        """Instead of to: a door of the stage's room (its name) it leaves through."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second."""

    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1] + _door_problems(params, self.options.door, "to", self.options.to)

    def _end(self, scene: NarratedScene, character: Character, *, opening: bool = False) -> tuple[str, float]:
        if self.options.door is not None:
            door = scene.door(self.options.door)
            return nearer_side(_feet_x(character), *scene.camera_bounds()[:2]), _door_x(scene, self.options.door) if opening else float(door.feet()[0])
        return exit_path(self.options.to, _feet_x(character), _view(scene), character.width / 2)

    def _seconds(self, character: Character, end: float) -> float:
        walk = _walk_time(character, end - _feet_x(character), self.options.speed)
        return max(walk, 2 * DOOR_FADE_SECONDS) if self.options.door is not None else walk

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        times = [self._seconds(c, self._end(scene, c)[1]) for c in _characters(scene, targets, "exit")]
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Walk each character out of the view or into the door (fading away there); then put it
        beyond the stage's edge."""
        left, right = scene.camera_bounds()[:2]
        anims: list[Animation] = []
        for character in _characters(scene, targets, "exit"):
            if getattr(scene.camera_following, "followed", None) is character:
                scene.follow_with_camera(None)
            half = character.width / 2
            side, end = self._end(scene, character, opening=True)
            door = {} if self.options.door is None else {"fade_out": DOOR_FADE_SECONDS, "run_time": self._seconds(character, end)}
            anims.append(Walk(character, end, park_x=offstage_x(side, left, right, half), speed=self.options.speed, **door))
        return anims


@action("gesture")
class GestureAction(_Moving):
    """The target character makes a gesture ``to``: point (the near arm forward), wave, shrug,
    nod or shake_head, and comes back to its pose. ``big: true``: a sweeping gesture; with motion
    effects (``cartoon_motion`` not none) a small whoosh arc trails the hand of a point, wave or
    shrug."""

    class Options(ActionOptions):
        to: Literal[GESTURES]  # type: ignore[valid-type]
        """The gesture: point, wave, shrug, nod or shake_head."""
        big: bool = False
        """true: a big, sweeping gesture: with motion effects a whoosh arc trails the hand (point, wave, shrug)."""

    run_time = 1.2

    def character_needs(self) -> str | None:
        return f"gesture: {self.options.to}"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1]

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return GESTURE_SECONDS[self.options.to]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`Gesture` on each character."""
        return [Gesture(c, self.options.to) for c in _characters(scene, targets, "gesture")]


@action("jump")
class JumpAction(_Moving):
    """The target character jumps up (``height`` in character heights) and lands where it stood."""

    class Options(ActionOptions):
        height: float = Field(JUMP_HEIGHT, gt=0.0, le=2.0)
        """How high it jumps, in its own heights (0.4: a hop; 1: its own height)."""

    run_time = JUMP_SECONDS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1]

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        times = [jump_motion_seconds(JUMP_SECONDS, c.motion_strength) for c in _characters(scene, targets, "jump")]
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`Jump` on each character."""
        return [Jump(c, self.options.height) for c in _characters(scene, targets, "jump")]
