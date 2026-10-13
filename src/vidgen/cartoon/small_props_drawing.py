"""Everyday small props in motion, drawn with manim (DESIGN.md §69.56); the maths is in
:mod:`vidgen.cartoon.small_props`.

The ``pour`` action plays :class:`Pouring` on a held watering can (it tilts about its grip, at the
hand) together with :class:`WaterFlow` on a :class:`WaterDrops` (drops leaving the spout and
falling to the ground), which the scene removes when the pour ends.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from manim import Animation, Circle, VGroup, VMobject, linear

from vidgen.cartoon.character import one_pixel_stroke
from vidgen.cartoon.small_props import POUR_TILT, Drop, pour_drops, pour_flow, pour_tilt

#: Water drops: their colour and edge, and how many a :class:`WaterDrops` can show at once.
WATER = "#8FD3F4"
WATER_EDGE = "#3E86B5"
MAX_DROPS = 40


class WaterDrops(VGroup):
    """Up to :data:`MAX_DROPS` water drops, placed by :meth:`place`."""

    def __init__(self, *, name: str) -> None:
        super().__init__()
        self.name = name
        self._unit = Circle(radius=1.0).points.copy()
        for _ in range(MAX_DROPS):
            drop = VMobject()
            drop.points = self._unit.copy()
            drop.set_fill(WATER, opacity=0.0)
            drop.set_stroke(WATER_EDGE, width=one_pixel_stroke(), opacity=0.0)
            self.add(drop)

    def place(self, drops: Sequence[Drop]) -> WaterDrops:
        """Show ``drops`` (Manim units); the discs left over are hidden."""
        for k, disc in enumerate(self.submobjects):
            if k < len(drops):
                d = drops[k]
                disc.points = self._unit * d.radius + np.array([d.x, d.y, 0.0])
                disc.set_fill(opacity=0.95)
                disc.set_stroke(opacity=0.9)
            else:
                disc.set_fill(opacity=0.0)
                disc.set_stroke(opacity=0.0)
        return self


class Pouring(Animation):
    """Tilt a held watering can ``prop`` about its grip, kept at ``follow()`` (the hand, read
    every frame): :func:`~vidgen.cartoon.small_props.pour_tilt` of :data:`POUR_TILT`, the spout
    going down (clockwise when the spout points right). Drawn from its points when it began, so
    it ends exactly as it was."""

    def __init__(self, prop: VMobject, *, follow: Callable[[], Sequence[float]], spout: Callable[[], np.ndarray], **kwargs) -> None:
        self.follow, self.spout = follow, spout
        kwargs.setdefault("rate_func", linear)
        super().__init__(prop, **kwargs)

    def begin(self) -> None:
        prop = self.mobject
        self._members = [(m, m.points.copy()) for m in prop.get_family() if len(m.points)]
        self._grip = np.array(prop.grip_point(), dtype=float)
        self._sign = 1.0 if float(self.spout()[0]) >= float(self._grip[0]) else -1.0
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        degrees = -self._sign * POUR_TILT * pour_tilt(self.rate_func(alpha))
        cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
        turn = np.array([[cos, -sin, 0.0], [sin, cos, 0.0], [0.0, 0.0, 1.0]])
        hand = self.follow()
        to = np.array([float(hand[0]), float(hand[1]), 0.0])
        for member, points in self._members:
            member.points = (points - self._grip) @ turn.T + to


class WaterFlow(Animation):
    """The water of a pour on ``drops``: drops leave ``spout()`` (screen, read every frame) while
    the water runs (:func:`~vidgen.cartoon.small_props.pour_flow`) and fall to ``ground`` (a y),
    forward the way ``direction()`` says (+1 right, −1 left); ``height`` scales them (the
    holder's height). Removed from the scene when it ends."""

    def __init__(self, drops: WaterDrops, *, spout: Callable[[], np.ndarray], direction: Callable[[], float], ground: float,
                 height: float, seed: int = 1, **kwargs) -> None:
        self.spout, self.direction, self.ground, self.height, self.seed = spout, direction, float(ground), float(height), seed
        kwargs.setdefault("rate_func", linear)
        kwargs.setdefault("remover", True)
        super().__init__(drops, **kwargs)

    def begin(self) -> None:
        self._flow = pour_flow(float(self.run_time))
        self._direction = self.direction()
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        spout = self.spout()
        elapsed = self.rate_func(alpha) * float(self.run_time)
        drops = pour_drops(elapsed, self._flow, (float(spout[0]), float(spout[1])), self.ground, self.height, self._direction, self.seed)
        self.mobject.place(drops[-MAX_DROPS:])


__all__ = ["MAX_DROPS", "Pouring", "WaterDrops", "WaterFlow"]
