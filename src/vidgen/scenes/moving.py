"""Moving beat actions (DESIGN.md §69.12): ``walk_to``, ``enter``, ``exit``, ``gesture`` and
``jump`` on the characters of a scene. Written against ``vidgen.api`` only, like project actions.

The motion is worked out without manim in :mod:`vidgen.cartoon.acting` (walk times, the walk
cycle, where an entrance starts and an exit ends, gestures, jumps) and played with the
:class:`Walk`, :class:`Gesture` and :class:`Jump` animations. A walk lasts its distance over its
speed (:meth:`Action.run_time_for`), shortened like any action when its beat has less time.
"""

from typing import Annotated, Any, Literal

from vidgen.api import *

from .acting import _Acting, _characters

#: Where a walk goes: a mark of the stage, or an x from 0 (left edge) to 1 (right edge).
Place = str | Annotated[float, Field(ge=0.0, le=1.0)]


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


@action("walk_to")
class WalkTo(_Moving):
    """The target character walks along the ground to ``to`` (a mark of the stage, or an x from 0
    = left to 1 = right), facing the way it goes, at ``speed`` (Manim units per second; the frame's
    shorter side is 8). It takes as long as the distance needs (``run_time`` sets it instead); a
    beat shorter than that speeds it up. It stays there."""

    class Options(ActionOptions):
        to: Place
        """Where it walks: a mark (left, centre, right, ... or the stage's own) or an x from 0 (left edge) to 1 (right edge) of the stage."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second (the frame's shorter side is 8 units; a stage character is about 3.6 tall)."""

    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._place_problems(scene_cls, params, self.options.to)

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        x = _place_x(scene, self.options.to)
        times = [walk_seconds(x - _feet_x(c), self.options.speed) for c in _characters(scene, targets, "walk_to")]
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`Walk` to the place for each character not there yet."""
        x = _place_x(scene, self.options.to)
        anims: list[Animation] = []
        for character in _characters(scene, targets, "walk_to"):
            if abs(x - _feet_x(character)) > 1e-6:
                anims.append(Walk(character, x, speed=self.options.speed))
                _ended_walk(scene, character)
        return anims


@action("enter")
class Enter(_Moving):
    """The target character walks in from beyond the ``side`` edge of what the camera shows (left
    or right; default: the edge nearer where it goes) to ``to`` (a mark or an x; default its own
    mark on the stage). On a ``stage`` a character with an enter action waits off stage until
    then."""

    class Options(ActionOptions):
        side: Literal["left", "right"] | None = None
        """The edge it comes in from: left or right; default: the one nearer where it goes."""
        to: Place | None = None
        """Where it walks to: a mark or an x from 0 to 1 of the stage; default: its own mark (its at on the stage)."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second."""

    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._place_problems(scene_cls, params, self.options.to)

    def _path(self, scene: NarratedScene, character: Character) -> tuple[str, float, float]:
        if self.options.to is not None:
            to_x = _place_x(scene, self.options.to)
        else:
            to_x = getattr(scene, "homes", {}).get(character.name, _feet_x(character))
        return enter_path(self.options.side, to_x, _view(scene), character.width / 2)

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        paths = [self._path(scene, c) for c in _characters(scene, targets, "enter")]
        return max((walk_seconds(end - start, self.options.speed) for _, start, end in paths), default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Put each character just beyond the view's edge and walk it in."""
        anims: list[Animation] = []
        for character in _characters(scene, targets, "enter"):
            _, start, end = self._path(scene, character)
            anims.append(Walk(character, end, start_x=start, speed=self.options.speed))
            _ended_walk(scene, character)
        return anims


@action("exit")
class Exit(_Moving):
    """The target character walks out of what the camera shows, beyond its ``to`` edge (left or
    right; default: the nearer one), and then waits off the stage (an ``enter`` brings it back).
    A camera following it stops following (and stays)."""

    class Options(ActionOptions):
        to: Literal["left", "right"] | None = None
        """The edge it leaves by: left or right; default: the nearer one."""
        speed: float = Field(WALK_SPEED, gt=0.0, le=20.0)
        """Walking speed in units per second."""

    run_time = 2.0

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1]

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        times = []
        for character in _characters(scene, targets, "exit"):
            _, end = exit_path(self.options.to, _feet_x(character), _view(scene), character.width / 2)
            times.append(walk_seconds(end - _feet_x(character), self.options.speed))
        return max(times, default=None)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Walk each character out of the view; then put it beyond the stage's edge."""
        left, right = scene.camera_bounds()[:2]
        anims: list[Animation] = []
        for character in _characters(scene, targets, "exit"):
            if getattr(scene.camera_following, "followed", None) is character:
                scene.follow_with_camera(None)
            half = character.width / 2
            side, end = exit_path(self.options.to, _feet_x(character), _view(scene), half)
            anims.append(Walk(character, end, park_x=offstage_x(side, left, right, half), speed=self.options.speed))
        return anims


@action("gesture")
class GestureAction(_Moving):
    """The target character makes a gesture ``to``: point (the near arm forward), wave, shrug,
    nod or shake_head, and comes back to its pose."""

    class Options(ActionOptions):
        to: Literal[GESTURES]  # type: ignore[valid-type]
        """The gesture: point, wave, shrug, nod or shake_head."""

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

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`Jump` on each character."""
        return [Jump(c, self.options.height) for c in _characters(scene, targets, "jump")]
