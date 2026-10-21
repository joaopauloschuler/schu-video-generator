"""Walks on an isometric place, drawn (DESIGN.md §89.9): the routes of the rules
(:mod:`vidgen.world.iso_moves`, tile units) played with the cartoon motion of :class:`Walk`.

The side walk cycle slides along the route's diagonals (accepted for iso: no new walk views).
The character faces left or right by the way the leg goes on the picture; a leg straight towards
the camera shows its front view (a character without one keeps its side), a leg straight away
keeps the side it last showed (there is no back view). Its feet follow the route's heights, up
and down steps, and its ``ground_y`` follows them, so its shadow lies on the cell top under it.
``iso_feet`` holds where its feet are in the world, for the stage's draw order (§89.9).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from manim import Mobject

from vidgen.cartoon.acting import WALK_SPEED, WALKING, Gait
from vidgen.cartoon.character import Character
from vidgen.cartoon.iso_stage import IsoView
from vidgen.cartoon.transition import Walk
from vidgen.world.iso_moves import IsoRoute
from vidgen.world.iso_view import iso_point

#: A leg whose picture moves less than this across (tile widths per tile walked) goes straight
#: towards or away from the camera.
STRAIGHT_ON = 0.05


def leg_facing(route: IsoRoute, index: int, side: str, *, has_front: bool) -> str:
    """The way a walker faces on the route's leg ``index``: ``left`` / ``right`` by the picture's
    direction; ``front`` straight towards the camera (when it ``has_front`` view); straight away,
    ``side`` (the side it showed last)."""
    a, b = route.leg(index)
    (u0, v0), (u1, v1) = iso_point(*a), iso_point(*b)
    du, dv = u1 - u0, v1 - v0
    across = abs(du) / max(abs(du) + abs(dv), 1e-9)
    if across < STRAIGHT_ON:
        return "front" if dv > 0 and has_front else side
    return "right" if du > 0 else "left"


class IsoWalk(Walk):
    """``character`` walks ``route`` (a :class:`~vidgen.world.iso_moves.IsoRoute`, placed by
    ``view``), facing the way each leg goes (:func:`leg_facing`), its feet up and down the steps on
    the way. Like :class:`Walk` it speeds up, walks at ``speed`` (Manim units per second, measured
    upright: a tile walked counts as a tile of height), slows down and stops with its
    ``cartoon_motion``. ``entering``: it starts at the route's start (beyond the place's edge or
    in a doorway; ``enter``); ``park_x``: moved there when it is over (``exit``); ``fade_in`` /
    ``fade_out``: it appears or disappears meanwhile (seconds). It ends facing the way it last
    walked (or its front), or ``end_facing`` when set (two that meet face each other)."""

    #: The way it faces once its feet stop (``None``: the way it last walked).
    end_facing: str | None = None

    def __init__(
        self,
        character: Character,
        route: IsoRoute,
        view: IsoView,
        *,
        speed: float = WALK_SPEED,
        gait: Gait = WALKING,
        motion: str | None = None,
        entering: bool = False,
        park_x: float | None = None,
        carried: Sequence[Mobject] = (),
        **kwargs: Any,
    ) -> None:
        self.route, self.view = route, view
        start_x = view.point(*route.start)[0] if entering else None
        super().__init__(character, view.point(*route.end)[0], start_x=start_x, park_x=park_x, speed=speed, gait=gait, motion=motion,
                         carried=carried, **kwargs)

    def _distance(self, character: Character, dx: float, from_depth: float) -> float:
        return self.route.length * self.view.height(1.0)

    def begin(self) -> None:
        figure = self.mobject
        x, y = self.view.point(*self.route.start)
        figure.shift([x - float(figure.feet()[0]), y - float(figure.feet()[1]), 0.0])
        figure.iso_feet = self.route.start
        figure.ground_y = y
        side = figure.facing if figure.facing != "front" else getattr(figure, "_side", "right")
        #: the way it faces on each leg, and once its feet stop
        self._facings: list[str] = []
        for k in range(len(self.route.points) - 1):
            facing = leg_facing(self.route, k, side, has_front=figure.has_front_view)
            side = facing if facing != "front" else side
            self._facings.append(facing)
        self._last = self.end_facing or (self._facings[-1] if self._facings else figure.facing)
        super().begin()

    def _place(self, share: float, done: bool) -> tuple[float, float, str]:
        (x, y, z), leg = self.route.at(share * self.route.length)
        figure = self.mobject
        figure.iso_feet = (x, y, z)
        scene_x, scene_y = self.view.point(x, y, z)
        figure.ground_y = scene_y
        facing = self._last if done or leg < 0 else self._facings[leg]
        return scene_x, scene_y, facing

    @property
    def end(self) -> tuple[float, float, float]:
        """Where its feet end up (tile units)."""
        return self.route.end


__all__ = ["STRAIGHT_ON", "IsoWalk", "leg_facing"]
