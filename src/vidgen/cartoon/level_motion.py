"""Walks and jumps on a platform level, drawn (DESIGN.md §86.7): the plans of the rules
(:mod:`vidgen.world.moves`, tile units) played with the cartoon motion of :class:`Walk` and
:class:`Jump` (the walk cycle, a crouch before a jump, squash and stretch, follow-through).

The animations only draw the plans; :class:`~vidgen.cartoon.level_stage.LevelFrame` maps tile
units to Manim units. A character's ``ground_y`` follows the floor under it on every frame, so its
shadow lies on the tile below it (none over a gap).
"""

from __future__ import annotations

from collections.abc import Sequence

from manim import Mobject

from vidgen.cartoon.acting import WALK_SPEED, WALKING, Gait
from vidgen.cartoon.character import Character
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
    squash_scale,
)
from vidgen.cartoon.transition import Jump, Walk, accented_state
from vidgen.world import Level, surface_under
from vidgen.world.moves import CLIMB, JumpPlan, Route

#: Below the frame, where a shadow goes over a gap (out of sight).
_NO_FLOOR_TILES = 100.0


def _floor_y(frame: LevelFrame, level: Level, x: float, y: float) -> float:
    """The scene y of the floor under feet at (``x``, ``y``) tile units (far below over a gap)."""
    floor = surface_under(level, x, y)
    return frame.point(x, floor if floor is not None else -_NO_FLOOR_TILES)[1]


class RouteWalk(Walk):
    """``character`` walks ``route`` (a :class:`~vidgen.world.moves.Route` of ``level``, placed by
    ``frame``): along the tiles facing the way each leg goes, its feet easing up or down at a step;
    up and down a ladder facing the front, its legs and arms stepping (a character without a front
    view keeps its side). It ends facing the way it last walked. Like :class:`Walk` it speeds up,
    slows down and stops with its ``cartoon_motion``'s wind-up and settle; the distance is the
    route's :attr:`~vidgen.world.moves.Route.effort` (a ladder climbs slower), so footsteps and
    run time follow it. ``entering``: it starts at the route's start off stage (``enter``);
    ``park_x``: moved there when it is over (``exit``)."""

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
        **kwargs,
    ) -> None:
        self.route, self.frame, self.level = route, frame, level
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


class ArcJump(Jump):
    """``character`` jumps the arc of ``plan`` (a :class:`~vidgen.world.moves.JumpPlan` of
    ``level``; its run-up is a separate :class:`RouteWalk`): it turns to face the landing, crouches
    (longer than a jump in place, :data:`~vidgen.cartoon.motion.LEVEL_JUMP_CROUCH_SECONDS`),
    stretches as it rises and falls, flies across at a steady speed on a parabola, squashes as it
    lands and wobbles a little (:data:`~vidgen.cartoon.motion.LANDING_WOBBLE_DEGREES`), all
    scaled by its ``cartoon_motion`` (``none``: the plain arc). Its run time is the plan's flight
    plus the crouch and the landing. ``lift``: how far it falls from the top of the arc (character
    heights; motion effects show impact stars after a big drop)."""

    def __init__(self, character: Character, plan: JumpPlan, frame: LevelFrame, level: Level, *, motion: str | None = None, **kwargs) -> None:
        self.plan, self.frame, self.level = plan, frame, level
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
        if self.strength > 0:
            rise = follow_through(self._up, t * self.run_time) * end_fade(t)
            wobble = -LANDING_WOBBLE_DEGREES * self.strength * settle_wobble(settle) if settle > 0 else 0.0
            figure.set_squash(*squash_scale(jump_stretch(t, self._phases, self.strength)))
            figure.set_state(accented_state(self._base, wobble, follow_angles(0.0, rise, self.strength)))
        x, y = self.plan.point(move)
        scene_x, scene_y = self.frame.point(x, y)
        figure.shift([scene_x - float(figure.feet()[0]), scene_y - float(figure.feet()[1]), 0.0])
        figure.ground_y = _floor_y(self.frame, self.level, x, y)
        figure.sync_mouth()

    @property
    def end(self) -> tuple[float, float]:
        """Where it lands (tile units)."""
        return self.plan.landing


__all__ = ["ArcJump", "RouteWalk"]
