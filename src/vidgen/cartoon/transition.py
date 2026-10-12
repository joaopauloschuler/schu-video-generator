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

All four apply the animation principles of :mod:`vidgen.cartoon.motion` (§69.13) with the
strength of the character's ``cartoon_motion`` setting (or their own ``motion=``): anticipation
and overshoot on pose changes and gestures; a wind-up, a settle and follow-through on walks;
a crouch, squash and stretch and follow-through on jumps. ``none`` plays the plain motion.

:class:`KeyedMotion` moves a character, a prop or a character's part through the channel values
of the ``keyframes`` and ``move_along`` actions (:mod:`vidgen.cartoon.keyframes`, §69.14).
:class:`ArmMove` and :class:`PropMove` play the prop actions (a hand reaching, carrying,
throwing; a prop going into a hand, onto the ground or flying, §69.27); :class:`BodyMove` sits a
character down, stands it up, leans it and crouches it (§69.28).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

import numpy as np
from manim import Animation, Mobject, linear, smooth

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
from vidgen.cartoon.holding import spin_degrees, throw_point
from vidgen.cartoon.limbs import TIMING_GROUP
from vidgen.cartoon.motion import (
    Phases,
    end_fade,
    follow_angles,
    follow_through,
    jump_motion_seconds,
    jump_phases,
    jump_stretch,
    motion_ease,
    motion_strength,
    squash_scale,
    walk_accent,
    walk_motion_seconds,
    walk_phases,
)


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
    ``lag_ratio`` of a part's duration after the previous one (0: all together), the last ends at
    1. A part of :data:`~vidgen.cartoon.limbs.TIMING_GROUP` shares its group's window (a forearm
    moves with its upper arm, the legs together), so limbs in two segments keep the timing of
    limbs in one piece."""
    groups = list(dict.fromkeys(TIMING_GROUP.get(part, part) for part in parts))
    if not groups:
        return {}
    total = 1.0 + (len(groups) - 1) * lag_ratio
    windows = {group: (k * lag_ratio / total, (k * lag_ratio + 1.0) / total) for k, group in enumerate(groups)}
    return {part: windows[TIMING_GROUP.get(part, part)] for part in parts}


class PoseChange(Animation):
    """Animate ``character`` to pose ``pose`` and / or expression ``expression`` (names of
    :meth:`Character.names`), or to ``state``; ``facing`` turns it too (the mirror switches
    halfway). Every changing part eases with ``part_rate_func`` in its own window; parts start
    ``lag_ratio`` apart, body first, then legs, arms, head and face (:data:`PART_NAMES` order).
    With the character's ``cartoon_motion`` (or ``motion``) each part first moves a little the
    other way and passes its end and settles (:func:`~vidgen.cartoon.motion.motion_ease`).
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
        motion: str | None = None,
        **kwargs,
    ) -> None:
        if state is not None and (pose is not None or expression is not None):
            raise TypeError("PoseChange: give state, or pose / expression, not both")
        target = state if state is not None else character.posed_state(pose=pose, expression=expression)
        if facing is not None:
            target = CharacterState(facing, dict(target.parts))
        self.target = target
        self.part_rate_func = part_rate_func
        self.strength = motion_strength(motion or character.motion)
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
            eased = motion_ease(local, self.strength, self.part_rate_func)
            parts[part] = blend_poses(self._start.parts[part], self.target.parts[part], eased)
        facing = self.target.facing if progress >= 0.5 else self._start.facing
        self.mobject.set_state(CharacterState(facing, parts))
        self.mobject.sync_mouth()  # Manim pauses the character's updaters: keep lip sync in step


#: A walk keeps the lower sole on the ground (legs drawn one each) when the pose it starts in has
#: it within this many character units of the ground.
GROUND_TOLERANCE = 0.02


def walking_state(base: CharacterState, cycle: WalkCycle, facing: str) -> CharacterState:
    """``base`` with the walk's ``cycle`` added: legs in one piece turned and narrowed and the
    body raised; legs drawn one each swung the opposite ways, the knee of the leg swinging forward
    bent; the arms swinging (the far arm the other way), the elbows bent; parts the character
    lacks are skipped (a folded forearm is in ``base``, :meth:`Character.state`)."""
    parts = dict(base.parts)

    def turn(part: str, degrees: float) -> None:
        if part in parts:
            parts[part] = replace(parts[part], angle=parts[part].angle + degrees)

    if "legs" in parts:
        sx, sy = parts["legs"].scale
        parts["legs"] = replace(parts["legs"], angle=parts["legs"].angle + cycle.legs_angle, scale=(sx * cycle.legs_width, sy))
        if "body" in parts:
            parts["body"] = replace(parts["body"], shift=(parts["body"].shift[0], parts["body"].shift[1] + cycle.body_lift))
    for leg, sign, knee in (("leg_left", 1.0, cycle.knee_bends[0]), ("leg_right", -1.0, cycle.knee_bends[1])):
        turn(leg, sign * cycle.thigh_angle)
        turn(f"{leg}_lower", -knee)
    for arm, sign, elbow in (("arm_left", 1.0, cycle.elbow_bends[0]), ("arm_right", -1.0, cycle.elbow_bends[1])):
        turn(arm, sign * cycle.arm_angle)
        turn(f"{arm}_lower", elbow)
    return CharacterState(facing, parts)


def accented_state(base: CharacterState, lean: float = 0.0, turns: dict[str, float] | None = None) -> CharacterState:
    """``base`` with the body leaning back ``lean`` degrees and each part of ``turns`` turned by
    its degrees (follow-through, :func:`~vidgen.cartoon.motion.follow_angles`); parts the
    character lacks are skipped."""
    parts = dict(base.parts)
    for part, degrees in {"body": lean, **(turns or {})}.items():
        if part in parts and degrees:
            parts[part] = replace(parts[part], angle=parts[part].angle + degrees)
    return CharacterState(base.facing, parts)


class Walk(Animation):
    """Walk ``character`` along the ground (its feet keep their height) to ``x`` (Manim units),
    facing the way it goes: it speeds up, walks at ``speed`` units per second, slows down and
    stops (:func:`~vidgen.cartoon.acting.walk_progress`), its legs, arms and body moving in step
    with the distance walked (:func:`~vidgen.cartoon.acting.walk_cycle`). ``start_x``: it first
    stands there (an entrance from off stage); ``park_x``: when the walk is over it is moved there
    (off stage, after an exit). With the character's ``cartoon_motion`` (or ``motion``) it first
    crouches and leans back, its arms, head and accessory trail as it sets off and carry on when
    it stops, and it leans on past the stop and settles (§69.13). The run time defaults to
    :func:`~vidgen.cartoon.acting.walk_seconds` plus that wind-up and settle
    (:func:`~vidgen.cartoon.motion.walk_motion_seconds`); a given one changes the speed.

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
        motion: str | None = None,
        **kwargs,
    ) -> None:
        self.to_x, self.start_x, self.park_x = float(x), start_x, park_x
        self.strength = motion_strength(motion or character.motion)
        from_x = float(character.feet()[0]) if start_x is None else float(start_x)
        walk_time = walk_seconds(self.to_x - from_x, speed)
        self._phases = walk_phases(walk_time, self.strength)
        #: How far it walks, in its heights (from where it stands now, or ``start_x``).
        self.heights = abs(self.to_x - from_x) / character.character_height if character.character_height > 0 else 0.0
        kwargs.setdefault("run_time", max(walk_motion_seconds(walk_time, self.strength), 1e-3))
        kwargs.setdefault("rate_func", linear)
        super().__init__(character, **kwargs)

    @property
    def phases(self) -> Phases:
        """The shares of its time spent winding up and settling (``cartoon_motion``)."""
        return self._phases

    def begin(self) -> None:
        figure = self.mobject
        figure.end_blink()
        if self.start_x is not None:
            figure.shift([self.start_x - float(figure.feet()[0]), 0.0, 0.0])
        figure.passage = "enter" if self.start_x is not None else "exit" if self.park_x is not None else None
        self._from = figure.feet()
        self._base = figure.state()
        # legs drawn one each: the body rises and falls so the lower sole stays where it stands
        # (lowest at the footfall, legs apart); not when the pose does not stand (sitting)
        sole = figure.sole_height(self._base)
        self._ground = sole if sole is not None and abs(sole) <= GROUND_TOLERANCE else None
        distance = self.to_x - float(self._from[0])
        self._facing = self._base.facing if abs(distance) < 1e-9 else ("right" if distance > 0 else "left")
        self._step = STEP_LENGTH * figure.character_height
        self._heights = abs(distance) / figure.character_height if figure.character_height > 0 else 0.0
        super().begin()

    def _ahead(self, seconds: float) -> float:
        """How far it has walked (character heights) ``seconds`` into the walk."""
        return walk_progress(self._phases.split(seconds / self.run_time)[1]) * self._heights

    def interpolate_mobject(self, alpha: float) -> None:
        t = self.rate_func(alpha)
        figure = self.mobject
        move = self._phases.split(t)[1]
        walked = walk_progress(move) * (self.to_x - float(self._from[0]))
        cycle = walk_cycle(abs(walked) / self._step if self._step > 0 else 0.0, walk_amplitude(move))
        state = walking_state(self._base, cycle, self._facing)
        if self.strength > 0:
            accent = walk_accent(t, self._phases, self.strength)
            trail = follow_through(self._ahead, t * self.run_time) * end_fade(t)
            state = accented_state(state, accent.lean, follow_angles(trail, 0.0, self.strength))
            figure.set_squash(*squash_scale(accent.stretch))
        figure.set_state(state if self._ground is None else figure.grounded(state, self._ground))
        figure.shift([self._from[0] + walked - figure.feet()[0], self._from[1] - figure.feet()[1], 0.0])
        figure.sync_mouth()  # Manim pauses the character's updaters: keep lip sync in step

    def clean_up_from_scene(self, scene) -> None:
        super().clean_up_from_scene(scene)
        self.mobject.passage = None
        if self.park_x is not None:
            self.mobject.shift([self.park_x - float(self.mobject.feet()[0]), 0.0, 0.0])


class Gesture(Animation):
    """``character`` makes gesture ``kind`` (``point``, ``wave``, ``shrug``, ``nod``,
    ``shake_head``; :func:`~vidgen.cartoon.acting.gesture_moves`) and comes back to its pose.
    ``point`` and ``wave`` use the near arm (``arm_left``; ``arm_right`` when it has no left arm);
    parts it lacks are skipped. With the character's ``cartoon_motion`` (or ``motion``) the arms
    wind up and overshoot as they move in and out (§69.13). The run time defaults to the
    gesture's (:data:`~vidgen.cartoon.acting.GESTURE_SECONDS`)."""

    def __init__(self, character: Character, kind: str, *, motion: str | None = None, **kwargs) -> None:
        self.kind = kind
        self.strength = motion_strength(motion or character.motion)
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
        for part, move in gesture_moves(self.kind, self.rate_func(alpha), self._arm, self.strength).items():
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
    (:func:`~vidgen.cartoon.acting.jump_lift`). With the character's ``cartoon_motion`` (or
    ``motion``) it crouches first, stretches as it rises and falls, squashes on landing and
    settles, its arms lifting as it falls (§69.13). Run time
    :data:`~vidgen.cartoon.acting.JUMP_SECONDS` plus the crouch and landing
    (:func:`~vidgen.cartoon.motion.jump_motion_seconds`) unless given."""

    def __init__(self, character: Character, height: float = JUMP_HEIGHT, *, motion: str | None = None, **kwargs) -> None:
        self.lift = float(height)
        self.strength = motion_strength(motion or character.motion)
        self._phases = jump_phases(JUMP_SECONDS, self.strength)
        kwargs.setdefault("run_time", jump_motion_seconds(JUMP_SECONDS, self.strength))
        kwargs.setdefault("rate_func", linear)
        super().__init__(character, **kwargs)

    @property
    def phases(self) -> Phases:
        """The shares of its time spent crouching before take-off and landing (``cartoon_motion``)."""
        return self._phases

    def begin(self) -> None:
        self.mobject.end_blink()
        self._from = self.mobject.feet()
        self._base = self.mobject.state()
        super().begin()

    def _up(self, seconds: float) -> float:
        """How high it is (character heights) ``seconds`` into the jump."""
        return jump_lift(self._phases.split(seconds / self.run_time)[1], self.lift)

    def interpolate_mobject(self, alpha: float) -> None:
        figure = self.mobject
        t = self.rate_func(alpha)
        if self.strength > 0:
            rise = follow_through(self._up, t * self.run_time) * end_fade(t)
            figure.set_squash(*squash_scale(jump_stretch(t, self._phases, self.strength)))
            figure.set_state(accented_state(self._base, 0.0, follow_angles(0.0, rise, self.strength)))
        up = jump_lift(self._phases.split(t)[1], self.lift) * figure.character_height
        figure.shift([0.0, self._from[1] + up - figure.feet()[1], 0.0])
        figure.sync_mouth()


class ArmMove(Animation):
    """Move some of ``character``'s parts through ``keys``: ``(share, part -> PartPose)`` in
    time order (shares 0..1 of the animation); each part eases (``smooth``) from where it was at
    the key before (at the start: as it is when the animation begins) to the key's pose, and holds
    after its last key. Parts no key names keep their pose. For the prop actions' reaches,
    carries and throws (DESIGN.md §69.27); like :class:`PoseChange` it ends a running blink and
    keeps lip sync in step."""

    def __init__(self, character: Character, keys: Sequence[tuple[float, Mapping[str, PartPose]]], **kwargs) -> None:
        self.keys = [(float(share), dict(parts)) for share, parts in keys]
        kwargs.setdefault("rate_func", linear)
        super().__init__(character, **kwargs)

    def begin(self) -> None:
        self.mobject.end_blink()
        self._base = self.mobject.state()
        # per part: (share, pose) from its pose now through each key that names it
        self._tracks: dict[str, list[tuple[float, PartPose]]] = {}
        for share, parts in self.keys:
            for part, pose in parts.items():
                if part in self._base.parts:
                    self._tracks.setdefault(part, [(0.0, self._base.parts[part])]).append((share, pose))
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        t = self.rate_func(alpha)
        parts = dict(self.mobject.state().parts)
        for part, track in self._tracks.items():
            pose = track[-1][1]
            for (begin, start), (end, target) in zip(track, track[1:]):
                if t <= end:
                    local = 1.0 if end <= begin else min(max((t - begin) / (end - begin), 0.0), 1.0)
                    pose = blend_poses(start, target, smooth(local))
                    break
            parts[part] = pose
        self.mobject.set_state(CharacterState(self.mobject.facing, parts))
        self.mobject.sync_mouth()


class BodyMove(ArmMove):
    """An :class:`ArmMove` of the whole figure: the parts eased through ``keys`` (body, legs,
    arms), the feet's x eased (``smooth``) to ``x`` (Manim units; ``None``: it stays), facing
    ``facing`` from the start, and single legs kept on the ground: each frame their soles are
    planted (:meth:`Character.planted`) on the way from where they were when it began to ``soles``
    (``left`` / ``right`` -> (x, y), character units as drawn facing right; ``None``: the legs move
    as the keys say). For sitting down, standing up, leaning and crouching (DESIGN.md §69.28)."""

    def __init__(
        self,
        character: Character,
        keys: Sequence[tuple[float, Mapping[str, PartPose]]],
        *,
        x: float | None = None,
        facing: str | None = None,
        soles: Mapping[str, Sequence[float]] | None = None,
        **kwargs,
    ) -> None:
        self.to_x, self.facing = x, facing
        self.soles = None if soles is None else {foot: (float(p[0]), float(p[1])) for foot, p in soles.items()}
        super().__init__(character, keys, **kwargs)

    def begin(self) -> None:
        figure = self.mobject
        if self.facing is not None:
            figure.face(self.facing)
        self._from_x = float(figure.feet()[0])
        self._from_soles = figure.sole_points() if self.soles is not None else {}
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        super().interpolate_mobject(alpha)
        figure = self.mobject
        t = smooth(self.rate_func(alpha))
        if self.soles:
            soles = {
                foot: (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)
                for foot, end in self.soles.items() if (start := self._from_soles.get(foot)) is not None
            }
            figure.set_state(figure.planted(figure.state(), soles))
        if self.to_x is not None:
            figure.shift([self._from_x + (self.to_x - self._from_x) * t - float(figure.feet()[0]), 0.0, 0.0])


class PropMove(Animation):
    """Move ``prop`` (its middle) between a hand and a place: until ``leave`` (a share of the
    animation) it stays at ``follow()`` (a hand's point, read every frame) or, without
    ``follow``, where it is; from ``leave`` to ``arrive`` it goes from there to ``to`` (a point,
    or a function giving one every frame), growing or shrinking to ``height`` units tall; then it
    stays there. ``rise`` > 0: it flies an arc peaking that many units above the higher end
    (:func:`~vidgen.cartoon.holding.throw_point`) and spins ``turns`` whole turns; ``lands``: the
    move ends on the ground (``lands_at`` is then ``arrive``, for the landing sound). Each frame
    is drawn from the prop's points when the animation began, so it ends exactly upright."""

    def __init__(
        self,
        prop: Mobject,
        *,
        to: Sequence[float] | Callable[[], Sequence[float]],
        follow: Callable[[], Sequence[float]] | None = None,
        leave: float = 0.0,
        arrive: float = 1.0,
        height: float | None = None,
        rise: float = 0.0,
        turns: int = 0,
        lands: bool = False,
        **kwargs,
    ) -> None:
        self.to, self.follow = to, follow
        self.leave, self.arrive = float(leave), max(float(arrive), float(leave))
        self.target_height, self.rise, self.turns = height, float(rise), int(turns)
        self.lands_at: float | None = self.arrive if lands else None
        kwargs.setdefault("rate_func", linear)
        super().__init__(prop, **kwargs)

    def begin(self) -> None:
        prop = self.mobject
        self._members = [(m, m.points.copy()) for m in prop.get_family() if len(m.points)]
        self._middle = np.array(prop.get_center(), dtype=float)
        self._height = max(float(prop.height), 1e-9)
        self._from: np.ndarray | None = None
        super().begin()

    def _point(self, where: Sequence[float] | Callable[[], Sequence[float]] | None) -> np.ndarray:
        if where is None:
            return self._middle
        value = where() if callable(where) else where
        return np.array([float(value[0]), float(value[1]), 0.0])

    def interpolate_mobject(self, alpha: float) -> None:
        t = self.rate_func(alpha)
        if t < self.leave or self.leave >= 1.0:
            self._draw(self._point(self.follow), self._height, 0.0)
            return
        if self._from is None:   # where the hand let go (or where it stood)
            self._from = self._point(self.follow)
        span = self.arrive - self.leave
        u = 1.0 if span <= 0 else min((t - self.leave) / span, 1.0)
        end = self._point(self.to)
        height = self._height if self.target_height is None else self._height + (self.target_height - self._height) * smooth(u)
        if self.rise > 0:
            x, y = throw_point(u, self._from, end, self.rise)
            middle, angle = np.array([x, y, 0.0]), spin_degrees(u, self.turns, float(end[0] - self._from[0]))
        else:
            middle, angle = self._from + (end - self._from) * smooth(u), 0.0
        self._draw(middle, height, angle)

    def _draw(self, middle: np.ndarray, height: float, angle: float) -> None:
        """The prop from its points at the start: ``height`` tall, turned ``angle`` degrees about
        its middle, the middle at ``middle``."""
        factor = height / self._height
        cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        turn = np.array([[cos, -sin, 0.0], [sin, cos, 0.0], [0.0, 0.0, 1.0]]) * factor
        for member, points in self._members:
            member.points = (points - self._middle) @ turn.T + middle

    def finish(self) -> None:
        super().finish()
        self.mobject.keyed_feet = None   # a keyed move's kept feet are stale now (feet_of)


def feet_of(mobject: Mobject) -> np.ndarray:
    """Where ``mobject`` stands: a character's :meth:`~Character.feet`, else the point a
    :class:`KeyedMotion` left it at, else its ``feet()`` (a prop), else the middle of its bottom
    edge."""
    if isinstance(mobject, Character):
        return mobject.feet()
    kept = getattr(mobject, "keyed_feet", None)
    if kept is not None:
        return np.array(kept, dtype=float)
    feet = getattr(mobject, "feet", None)
    return np.array(feet() if callable(feet) else mobject.get_bottom(), dtype=float)


class KeyedMotion(Animation):
    """Move ``mobject`` through the channel values ``values_at(share)`` gives at each ``share``
    (0..1) of the animation (:func:`~vidgen.cartoon.keyframes.keyed_values`, or a point along a
    :class:`~vidgen.cartoon.keyframes.MotionPath`); a channel it does not give holds.

    Without ``part``: ``x`` and ``y`` are where its feet go on screen (:func:`feet_of`), ``rotate``
    its turn in degrees counterclockwise about the feet and ``scale`` its size, both against how
    it was built (kept on it as ``keyed_rotate`` / ``keyed_scale``, so a later motion starts from
    them). With ``part`` (``mobject`` is then the :class:`Character`): the part's pose, ``x`` /
    ``y`` its shift in character units, ``rotate`` its angle, ``scale`` its size (a flipped part
    stays flipped). A character ends a running blink and keeps lip sync in step, as in
    :class:`PoseChange`."""

    def __init__(self, mobject: Mobject, values_at: Callable[[float], Mapping[str, float]], *, part: str | None = None, **kwargs) -> None:
        if part is not None and not isinstance(mobject, Character):
            raise TypeError("KeyedMotion: a part moves with its Character as the mobject")
        self.values_at = values_at
        self.part = part
        kwargs.setdefault("rate_func", linear)
        super().__init__(mobject, **kwargs)

    def begin(self) -> None:
        if isinstance(self.mobject, Character):
            self.mobject.end_blink()
        if self.part is not None:
            sx, sy = self.mobject.pose_of(self.part).scale
            self._signs = (math.copysign(1.0, sx), math.copysign(1.0, sy))
        else:
            self._feet = feet_of(self.mobject)
            self._rotate = float(getattr(self.mobject, "keyed_rotate", 0.0))
            self._scale = float(getattr(self.mobject, "keyed_scale", 1.0))
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        values = self.values_at(self.rate_func(alpha))
        if self.part is not None:
            self._pose_part(values)
        else:
            self._place(values)
        if isinstance(self.mobject, Character):
            self.mobject.sync_mouth()

    def _pose_part(self, values: Mapping[str, float]) -> None:
        pose = self.mobject.pose_of(self.part)
        scale = values.get("scale")
        self.mobject.set_part(
            self.part,
            angle=values.get("rotate", pose.angle),
            scale=pose.scale if scale is None else (scale * self._signs[0], scale * self._signs[1]),
            shift=(values.get("x", pose.shift[0]), values.get("y", pose.shift[1])),
        )

    def _place(self, values: Mapping[str, float]) -> None:
        """Undo the last frame's turn and size about the feet, move the feet, apply the new ones:
        a character's anchor moves along, so its poses and later moves keep them."""
        mob, old = self.mobject, self._feet
        feet = np.array([values.get("x", old[0]), values.get("y", old[1]), 0.0])
        rotate, scale = values.get("rotate", self._rotate), values.get("scale", self._scale)
        if self._rotate:
            mob.rotate(-math.radians(self._rotate), about_point=old)
        if self._scale != scale:
            mob.scale(scale / self._scale, about_point=old)
        mob.shift(feet - old)
        if rotate:
            mob.rotate(math.radians(rotate), about_point=feet)
        self._feet, self._rotate, self._scale = feet, rotate, scale
        mob.keyed_rotate, mob.keyed_scale = rotate, scale
        if not isinstance(mob, Character):
            mob.keyed_feet = tuple(feet)


__all__ = ["ArmMove", "BodyMove", "PropMove", "Gesture", "Jump", "KeyedMotion", "PoseChange", "Walk", "feet_of", "accented_state", "blend_poses", "part_windows", "walking_state"]
