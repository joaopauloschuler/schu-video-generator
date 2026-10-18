"""Walks and jumps on a platform level, drawn (DESIGN.md §86.7): the plans of the rules
(:mod:`vidgen.world.moves`, tile units) played with the cartoon motion of :class:`Walk` and
:class:`Jump` (the walk cycle, a crouch before a jump, squash and stretch, follow-through).

The animations only draw the plans; :class:`~vidgen.cartoon.level_stage.LevelFrame` maps tile
units to Manim units. A character's ``ground_y`` follows the floor under it on every frame, so its
shadow lies on the tile below it (none over a gap). The coins and stars a move picks up pop on the
frame its feet get there (``pickups``), and a :class:`Reaction` (a new expression, an effect
symbol) starts at its moment during or after the move (DESIGN.md §86.8).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from manim import Mobject

from vidgen.cartoon.acting import WALK_SPEED, WALKING, Gait, walk_progress
from vidgen.cartoon.character import Character, CharacterState
from vidgen.cartoon.level_stage import LevelFrame
from vidgen.cartoon.motion import (
    LANDING_WOBBLE_DEGREES,
    LEVEL_JUMP_CROUCH_SECONDS,
    LEVEL_JUMP_LAND_SECONDS,
    end_fade,
    follow_angles,
    follow_through,
    jump_motion_seconds,
    jump_phases,
    jump_stretch,
    motion_strength,
    settle_wobble,
    smoothstep,
    squash_scale,
)
from vidgen.cartoon.poses import kind_parts
from vidgen.cartoon.transition import Jump, Walk, accented_state, blend_poses
from vidgen.world import Level, surface_under
from vidgen.world.moves import CLIMB, JumpPlan, Route

#: Below the frame, where a shadow goes over a gap (out of sight).
_NO_FLOOR_TILES = 100.0
#: A reaction's expression comes on over this many seconds; its effect symbol stays this long.
REACTION_BLEND_SECONDS = 0.3
REACTION_EFFECT_SECONDS = 1.4
#: Where a move's progress (its walk or flight 0..1, then its settle 1..2) is when it lands or
#: stops, and when its settle is over.
LANDED = 1.0
SETTLED = 2.0


def _floor_y(frame: LevelFrame, level: Level, x: float, y: float) -> float:
    """The scene y of the floor under feet at (``x``, ``y``) tile units (far below over a gap)."""
    floor = surface_under(level, x, y)
    return frame.point(x, floor if floor is not None else -_NO_FLOOR_TILES)[1]


class Reaction:
    """A reaction inside a level move: once the move's progress passes ``at`` (a share of its walk
    or flight 0..1, :data:`LANDED` when it lands or stops, :data:`SETTLED` once its settle is over)
    its face eases to ``expression`` over :data:`REACTION_BLEND_SECONDS` (and keeps it) and the
    ``effect`` symbol pops in for :data:`REACTION_EFFECT_SECONDS` (``symbol``: its
    :class:`~vidgen.cartoon.effect_symbols.EffectSymbol` following the head, kept hidden until
    then; the stage adds it when the move is applied)."""

    def __init__(self, at: float, expression: str | None = None, effect: str | None = None) -> None:
        self.at, self.expression, self.effect = at, expression, effect
        self.symbol: Any = None
        self.started: float | None = None
        self._face: dict[str, Any] = {}

    def begin(self, character: Character) -> None:
        """Work out the face to ease to from ``character``'s state now."""
        if self.expression is not None:
            target = character.posed_state(expression=self.expression).parts
            self._face = {part: target[part] for part in kind_parts("expression") if part in target}

    def state(self, base: CharacterState, progress: float, seconds: float) -> CharacterState:
        """``base`` with the face eased towards the reaction's ``seconds`` into the move."""
        if self.started is None and progress >= self.at - 1e-9:
            self.start(seconds)
        if self.started is None or not self._face:
            return base
        share = smoothstep((seconds - self.started) / REACTION_BLEND_SECONDS)
        face = {part: blend_poses(base.parts[part], pose, share) for part, pose in self._face.items() if part in base.parts}
        return CharacterState(base.facing, {**base.parts, **face})

    def start(self, seconds: float) -> None:
        self.started = seconds
        if self.symbol is not None:
            self.symbol.age, self.symbol.leaving = 0.0, REACTION_EFFECT_SECONDS

    def finish(self, character: Character, seconds: float) -> None:
        """Make sure it has played once the move is over: started, the face fully on."""
        if self.started is None:
            self.start(seconds)
        if self._face:
            state = character.state()
            character.set_state(CharacterState(state.facing, {**state.parts, **{p: v for p, v in self._face.items() if p in state.parts}}))
            character.sync_mouth()


class _Cues:
    """The coins and stars a level move picks up (``pickups``: (progress, collectible) in
    order) and its :class:`Reaction`, played as its progress passes them."""

    pickups: Sequence[tuple[float, Any]]
    reaction: Reaction | None

    def _cue(self, progress: float, seconds: float) -> None:
        if not hasattr(self, "_plain_base"):   # the first frame (Animation.begin interpolates at 0)
            self._plain_base = self._base
            if self.reaction is not None:
                self.reaction.begin(self.mobject)
        for share, item in self.pickups:
            if progress >= share - 1e-9:
                item.collect()
        if self.reaction is not None:
            self._base = self.reaction.state(self._plain_base, progress, seconds)

    def _finish_cues(self, character: Character, seconds: float) -> None:
        for _, item in self.pickups:
            item.collect()
        if self.reaction is not None:
            self.reaction.finish(character, seconds)


class RouteWalk(_Cues, Walk):
    """``character`` walks ``route`` (a :class:`~vidgen.world.moves.Route` of ``level``, placed by
    ``frame``): along the tiles facing the way each leg goes, its feet easing up or down at a step;
    up and down a ladder facing the front, its legs and arms stepping (a character without a front
    view keeps its side). It ends facing the way it last walked. Like :class:`Walk` it speeds up,
    slows down and stops with its ``cartoon_motion``'s wind-up and settle; the distance is the
    route's :attr:`~vidgen.world.moves.Route.effort` (a ladder climbs slower), so footsteps and
    run time follow it. ``entering``: it starts at the route's start off stage (``enter``);
    ``park_x``: moved there when it is over (``exit``). ``pickups``: (share of the route's effort,
    collectible) popped as its feet get there; ``reaction``: a :class:`Reaction` (its ``at`` a
    share of the route, :data:`LANDED` as its feet stop)."""

    def __init__(
        self,
        character: Character,
        route: Route,
        frame: LevelFrame,
        level: Level,
        *,
        speed: float = WALK_SPEED,
        gait: Gait = WALKING,
        motion: str | None = None,
        entering: bool = False,
        park_x: float | None = None,
        carried: Sequence[Mobject] = (),
        pickups: Sequence[tuple[float, Any]] = (),
        reaction: Reaction | None = None,
        **kwargs,
    ) -> None:
        self.route, self.frame, self.level = route, frame, level
        self.pickups, self.reaction = list(pickups), reaction
        start_x = frame.point(*route.start)[0] if entering else None
        super().__init__(character, frame.point(*route.end)[0], start_x=start_x, park_x=park_x, speed=speed, gait=gait, motion=motion,
                         carried=carried, **kwargs)

    def _distance(self, character: Character, dx: float, from_depth: float) -> float:
        return self.route.effort * self.frame.tile

    def begin(self) -> None:
        figure = self.mobject
        x, y = self.frame.point(*self.route.start)
        figure.shift([x - float(figure.feet()[0]), y - float(figure.feet()[1]), 0.0])
        side = figure.facing if figure.facing != "front" else "right"
        #: the way it faces on each leg (by its id), and once its feet stop
        self._facings: dict[int, str] = {}
        for leg in self.route.legs:
            if leg.kind == CLIMB:
                self._facings[id(leg)] = "front"
            else:
                side = "right" if leg.direction > 0 else "left" if leg.direction < 0 else side
                self._facings[id(leg)] = side
        self._last_side = side
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        _, move, settle = self._phases.split(self.rate_func(alpha))
        self._cue(walk_progress(move) + settle, self.rate_func(alpha) * self.run_time)
        super().interpolate_mobject(alpha)

    def finish(self) -> None:
        super().finish()
        self._finish_cues(self.mobject, self.run_time)

    def _place(self, share: float, done: bool) -> tuple[float, float, str]:
        (x, y), leg = self.route.at(share * self.route.effort)
        facing = self._last_side if done or leg is None else self._facings[id(leg)]
        self.mobject.ground_y = _floor_y(self.frame, self.level, x, y)
        scene_x, scene_y = self.frame.point(x, y)
        return scene_x, scene_y, facing

    @property
    def end(self) -> tuple[float, float]:
        """Where it ends up (tile units)."""
        return self.route.end


class ArcJump(_Cues, Jump):
    """``character`` jumps the arc of ``plan`` (a :class:`~vidgen.world.moves.JumpPlan` of
    ``level``; its run-up is a separate :class:`RouteWalk`): it turns to face the landing, crouches
    (longer than a jump in place, :data:`~vidgen.cartoon.motion.LEVEL_JUMP_CROUCH_SECONDS`),
    stretches as it rises and falls, flies across at a steady speed on a parabola, squashes as it
    lands and wobbles a little (:data:`~vidgen.cartoon.motion.LANDING_WOBBLE_DEGREES`), all
    scaled by its ``cartoon_motion`` (``none``: the plain arc). Its run time is the plan's flight
    plus the crouch and the landing. ``lift``: how far it falls from the top of the arc (character
    heights; motion effects show impact stars after a big drop). ``pickups``: (share of the
    flight, collectible) popped mid-air as it gets there; ``reaction``: a :class:`Reaction` (its
    ``at`` a share of the flight, :data:`LANDED` as it lands, :data:`SETTLED` once it stands still)."""

    def __init__(self, character: Character, plan: JumpPlan, frame: LevelFrame, level: Level, *, motion: str | None = None,
                 pickups: Sequence[tuple[float, Any]] = (), reaction: Reaction | None = None, **kwargs) -> None:
        self.plan, self.frame, self.level = plan, frame, level
        self.pickups, self.reaction = list(pickups), reaction
        strength = motion_strength(motion or character.motion)
        kwargs.setdefault("run_time", jump_motion_seconds(plan.flight_seconds, strength, LEVEL_JUMP_CROUCH_SECONDS, LEVEL_JUMP_LAND_SECONDS))
        self._tiles_tall = max(character.character_height / frame.tile, 1e-9)
        super().__init__(character, (plan.apex - plan.landing[1]) / self._tiles_tall, motion=motion, **kwargs)
        self._phases = jump_phases(plan.flight_seconds, self.strength, LEVEL_JUMP_CROUCH_SECONDS, LEVEL_JUMP_LAND_SECONDS)

    def begin(self) -> None:
        figure = self.mobject
        dx = self.plan.landing[0] - self.plan.take_off[0]
        if abs(dx) > 1e-6:
            figure.face("right" if dx > 0 else "left")
        x, y = self.frame.point(*self.plan.take_off)
        figure.shift([x - float(figure.feet()[0]), y - float(figure.feet()[1]), 0.0])
        super().begin()

    def _up(self, seconds: float) -> float:
        """How high over the take-off it is (character heights) ``seconds`` into the jump."""
        move = self._phases.split(seconds / self.run_time)[1]
        return (self.plan.point(move)[1] - self.plan.take_off[1]) / self._tiles_tall

    def interpolate_mobject(self, alpha: float) -> None:
        figure = self.mobject
        t = self.rate_func(alpha)
        _, move, settle = self._phases.split(t)
        self._cue(move + settle, t * self.run_time)
        if self.strength > 0:
            rise = follow_through(self._up, t * self.run_time) * end_fade(t)
            wobble = -LANDING_WOBBLE_DEGREES * self.strength * settle_wobble(settle) if settle > 0 else 0.0
            figure.set_squash(*squash_scale(jump_stretch(t, self._phases, self.strength)))
            figure.set_state(accented_state(self._base, wobble, follow_angles(0.0, rise, self.strength)))
        elif self.reaction is not None:
            figure.set_state(self._base)
        x, y = self.plan.point(move)
        scene_x, scene_y = self.frame.point(x, y)
        figure.shift([scene_x - float(figure.feet()[0]), scene_y - float(figure.feet()[1]), 0.0])
        figure.ground_y = _floor_y(self.frame, self.level, x, y)
        figure.sync_mouth()

    def finish(self) -> None:
        super().finish()
        self._finish_cues(self.mobject, self.run_time)

    @property
    def end(self) -> tuple[float, float]:
        """Where it lands (tile units)."""
        return self.plan.landing


__all__ = ["LANDED", "REACTION_BLEND_SECONDS", "REACTION_EFFECT_SECONDS", "SETTLED", "ArcJump", "Reaction", "RouteWalk"]
