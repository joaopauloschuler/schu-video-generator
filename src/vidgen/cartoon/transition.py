"""Animations of characters: eased part-by-part changes between two states (DESIGN.md §69.3),
walking, gestures and jumps (§69.12).

:class:`PoseChange` animates a :class:`~vidgen.cartoon.character.Character` from its state when the
animation starts to a target state (a pose, an expression, or any :class:`CharacterState`). Each
part that changes eases on its own: angles, scales and shifts are blended and the character is
redrawn from its rest shapes, so an arm swings along an arc about its pivot (``.animate`` would
move its points along straight lines), and parts start one after another from the body out.

:class:`Walk`, :class:`Gesture` and :class:`Jump` redraw the character on every frame from its
state when they begin plus the motion of :mod:`vidgen.cartoon.acting` at that moment, and end in
that state. Like :class:`PoseChange`, they end a running blink and keep lip sync in step.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from manim import Animation, linear, smooth

from vidgen.cartoon.acting import (
    GESTURE_SECONDS,
    JUMP_HEIGHT,
    JUMP_SECONDS,
    STEP_LENGTH,
    WALK_SPEED,
    WalkCycle,
    gesture_moves,
    jump_lift,
    walk_amplitude,
    walk_cycle,
    walk_progress,
    walk_seconds,
)
from vidgen.cartoon.character import PART_NAMES, Character, CharacterState, PartPose


def blend_poses(start: PartPose, end: PartPose, progress: float) -> PartPose:
    """The pose ``progress`` (0..1) of the way from ``start`` to ``end``: angle, scale and shift
    blended linearly; the shape switches to ``end``'s at the halfway point."""
    def mix(a: float, b: float) -> float:
        return a + (b - a) * progress

    return PartPose(
        angle=mix(start.angle, end.angle),
        scale=(mix(start.scale[0], end.scale[0]), mix(start.scale[1], end.scale[1])),
        shift=(mix(start.shift[0], end.shift[0]), mix(start.shift[1], end.shift[1])),
        shape=end.shape if progress >= 0.5 else start.shape,
    )


def part_windows(parts: Sequence[str], lag_ratio: float) -> dict[str, tuple[float, float]]:
    """When each of ``parts`` moves, as (start, end) fractions of the animation: each starts
    ``lag_ratio`` of a part's duration after the previous one (0: all together), the last ends at 1."""
    if not parts:
        return {}
    total = 1.0 + (len(parts) - 1) * lag_ratio
    return {part: (k * lag_ratio / total, (k * lag_ratio + 1.0) / total) for k, part in enumerate(parts)}


class PoseChange(Animation):
    """Animate ``character`` to pose ``pose`` and / or expression ``expression`` (names of
    :meth:`Character.names`), or to ``state``; ``facing`` turns it too (the mirror switches
    halfway). Every changing part eases with ``part_rate_func`` in its own window; parts start
    ``lag_ratio`` apart, body first, then legs, arms, head and face (:data:`PART_NAMES` order).
    The target is resolved when the animation is created; the start when it begins, which also
    ends a running blink (the idle clock stops while it plays, §69.5). A running lip sync keeps
    following its clock on every frame (§69.4).

    ``self.play(PoseChange(pip, pose="waving", expression="happy"), run_time=0.8)``
    """

    def __init__(
        self,
        character: Character,
        *,
        pose: str | None = None,
        expression: str | None = None,
        state: CharacterState | None = None,
        facing: str | None = None,
        lag_ratio: float = 0.15,
        part_rate_func: Callable[[float], float] = smooth,
        **kwargs,
    ) -> None:
        if state is not None and (pose is not None or expression is not None):
            raise TypeError("PoseChange: give state, or pose / expression, not both")
        target = state if state is not None else character.posed_state(pose=pose, expression=expression)
        if facing is not None:
            target = CharacterState(facing, dict(target.parts))
        self.target = target
        self.part_rate_func = part_rate_func
        self._start = character.state()
        self._windows: dict[str, tuple[float, float]] = {}
        kwargs.setdefault("rate_func", linear)
        super().__init__(character, lag_ratio=lag_ratio, **kwargs)

    def begin(self) -> None:
        self.mobject.end_blink()
        self._start = self.mobject.state()
        changing = [
            part for part in PART_NAMES
            if part in self._start.parts and self.target.parts.get(part, self._start.parts[part]) != self._start.parts[part]
        ]
        self._windows = part_windows(changing, self.lag_ratio)
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        progress = self.rate_func(alpha)
        parts = {}
        for part, (begin, end) in self._windows.items():
            local = min(max((progress - begin) / (end - begin), 0.0), 1.0)
            parts[part] = blend_poses(self._start.parts[part], self.target.parts[part], self.part_rate_func(local))
        facing = self.target.facing if progress >= 0.5 else self._start.facing
        self.mobject.set_state(CharacterState(facing, parts))
        self.mobject.sync_mouth()  # Manim pauses the character's updaters: keep lip sync in step


def walking_state(base: CharacterState, cycle: WalkCycle, facing: str) -> CharacterState:
    """``base`` with the walk's ``cycle`` added: the legs turned and narrowed, the body raised, the
    arms swinging (the far arm the other way); parts the character lacks are skipped."""
    parts = dict(base.parts)

    def change(part: str, **values: object) -> None:
        if part in parts:
            parts[part] = replace(parts[part], **values)

    if "legs" in parts:
        sx, sy = parts["legs"].scale
        change("legs", angle=parts["legs"].angle + cycle.legs_angle, scale=(sx * cycle.legs_width, sy))
    if "body" in parts:
        change("body", shift=(parts["body"].shift[0], parts["body"].shift[1] + cycle.body_lift))
    for arm, sign in (("arm_left", 1.0), ("arm_right", -1.0)):
        if arm in parts:
            change(arm, angle=parts[arm].angle + sign * cycle.arm_angle)
    return CharacterState(facing, parts)


class Walk(Animation):
    """Walk ``character`` along the ground (its feet keep their height) to ``x`` (Manim units),
    facing the way it goes: it speeds up, walks at ``speed`` units per second, slows down and
    stops (:func:`~vidgen.cartoon.acting.walk_progress`), its legs, arms and body moving in step
    with the distance walked (:func:`~vidgen.cartoon.acting.walk_cycle`). ``start_x``: it first
    stands there (an entrance from off stage); ``park_x``: when the walk is over it is moved there
    (off stage, after an exit). The run time defaults to
    :func:`~vidgen.cartoon.acting.walk_seconds`; a given one changes the speed.

    ``self.play(Walk(pip, 3.0))``
    """

    def __init__(
        self,
        character: Character,
        x: float,
        *,
        start_x: float | None = None,
        park_x: float | None = None,
        speed: float = WALK_SPEED,
        **kwargs,
    ) -> None:
        self.to_x, self.start_x, self.park_x = float(x), start_x, park_x
        from_x = float(character.feet()[0]) if start_x is None else float(start_x)
        kwargs.setdefault("run_time", max(walk_seconds(self.to_x - from_x, speed), 1e-3))
        kwargs.setdefault("rate_func", linear)
        super().__init__(character, **kwargs)

    def begin(self) -> None:
        figure = self.mobject
        figure.end_blink()
        if self.start_x is not None:
            figure.shift([self.start_x - float(figure.feet()[0]), 0.0, 0.0])
        self._from = figure.feet()
        self._base = figure.state()
        distance = self.to_x - float(self._from[0])
        self._facing = self._base.facing if abs(distance) < 1e-9 else ("right" if distance > 0 else "left")
        self._step = STEP_LENGTH * figure.character_height
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        t = self.rate_func(alpha)
        figure = self.mobject
        walked = walk_progress(t) * (self.to_x - float(self._from[0]))
        cycle = walk_cycle(abs(walked) / self._step if self._step > 0 else 0.0, walk_amplitude(t))
        figure.set_state(walking_state(self._base, cycle, self._facing))
        figure.shift([self._from[0] + walked - figure.feet()[0], self._from[1] - figure.feet()[1], 0.0])
        figure.sync_mouth()  # Manim pauses the character's updaters: keep lip sync in step

    def clean_up_from_scene(self, scene) -> None:
        super().clean_up_from_scene(scene)
        if self.park_x is not None:
            self.mobject.shift([self.park_x - float(self.mobject.feet()[0]), 0.0, 0.0])


class Gesture(Animation):
    """``character`` makes gesture ``kind`` (``point``, ``wave``, ``shrug``, ``nod``,
    ``shake_head``; :func:`~vidgen.cartoon.acting.gesture_moves`) and comes back to its pose.
    ``point`` and ``wave`` use the near arm (``arm_left``; ``arm_right`` when it has no left arm);
    parts it lacks are skipped. The run time defaults to the gesture's
    (:data:`~vidgen.cartoon.acting.GESTURE_SECONDS`)."""

    def __init__(self, character: Character, kind: str, **kwargs) -> None:
        self.kind = kind
        kwargs.setdefault("run_time", GESTURE_SECONDS[kind])
        kwargs.setdefault("rate_func", linear)
        super().__init__(character, **kwargs)

    def begin(self) -> None:
        self.mobject.end_blink()
        self._base = self.mobject.state()
        self._arm = "arm_left" if self.mobject.has_part("arm_left") else "arm_right"
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        parts = dict(self._base.parts)
        for part, move in gesture_moves(self.kind, self.rate_func(alpha), self._arm).items():
            if part not in parts:
                continue
            pose = parts[part]
            angle = pose.angle if move.angle is None else pose.angle + (move.angle - pose.angle) * move.weight
            shift = (pose.shift[0] + move.shift[0], pose.shift[1] + move.shift[1])
            parts[part] = replace(pose, angle=angle + move.turn, shift=shift)
        self.mobject.set_state(CharacterState(self._base.facing, parts))
        self.mobject.sync_mouth()


class Jump(Animation):
    """``character`` jumps ``height`` character heights up and lands where it stood
    (:func:`~vidgen.cartoon.acting.jump_lift`); run time :data:`~vidgen.cartoon.acting.JUMP_SECONDS`
    unless given."""

    def __init__(self, character: Character, height: float = JUMP_HEIGHT, **kwargs) -> None:
        self.lift = float(height)
        kwargs.setdefault("run_time", JUMP_SECONDS)
        kwargs.setdefault("rate_func", linear)
        super().__init__(character, **kwargs)

    def begin(self) -> None:
        self.mobject.end_blink()
        self._from = self.mobject.feet()
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        figure = self.mobject
        up = jump_lift(self.rate_func(alpha), self.lift) * figure.character_height
        figure.shift([0.0, self._from[1] + up - figure.feet()[1], 0.0])
        figure.sync_mouth()


__all__ = ["Gesture", "Jump", "PoseChange", "Walk", "blend_poses", "part_windows", "walking_state"]
