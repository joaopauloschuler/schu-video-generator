"""A stage's water, drawn and moved with manim (DESIGN.md §69.53); the waves and the bobbing are
pure functions of :mod:`vidgen.cartoon.vehicle_paths`.

The water is a strip at the front of the stage, from the bottom of the frame up to its surface
(:data:`~vidgen.cartoon.vehicle_paths.WATERLINE` above the ground line): a flat band behind
everything on the stage, and a front strip with a wavy top drawn in front of the boats, over their
keels, so they sit in the water. On every frame :meth:`StageWater.update` moves the waves and
bobs each boat about where it rests (``afloat``), its riders with it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from manim import Rectangle, VGroup, VMobject

from vidgen.cartoon.props import Prop
from vidgen.cartoon.riding import RiderSeat, place_rider
from vidgen.cartoon.vehicle_paths import CREST_COLOR, WATERLINE, boat_bob, bob_phase, front_outline

#: How opaque the front strip is (the keels show a little through it), and its light crest line's
#: stroke width.
FRONT_OPACITY = 0.88
CREST_WIDTH = 2.0


class StageWater:
    """The water from x ``left`` to ``right`` (Manim units) on a stage whose ground line is at
    ``ground`` (y) and whose frame's bottom edge is ``bottom``, for characters ``unit`` units tall
    at the front, in ``color``; ``sign``: the way the waves drift (+1 right, -1 left).
    :attr:`back` and :attr:`front` are its two mobjects (the stage draws them behind and in front
    of everything else)."""

    def __init__(self, left: float, right: float, ground: float, bottom: float, unit: float, color: str, *, sign: float = 1.0) -> None:
        self.left, self.right, self.bottom, self.unit, self.sign = left, right, bottom, unit, sign
        self.surface = ground + WATERLINE * unit
        self.back = Rectangle(width=right - left, height=self.surface - bottom, stroke_width=0)
        self.back.set_fill(color, opacity=1.0).move_to([(left + right) / 2, (self.surface + bottom) / 2, 0.0])
        self.back.name = "water"
        self._strip = VMobject().set_fill(color, opacity=FRONT_OPACITY).set_stroke(width=0.0, opacity=0.0)
        self._crest = VMobject().set_fill(opacity=0.0).set_stroke(CREST_COLOR, width=CREST_WIDTH, opacity=0.9)
        self.front = VGroup(self._strip, self._crest)
        self.front.name = "water_front"
        self.boats: list[tuple[Prop, float]] = []
        self.update(0.0)

    def float_boat(self, boat: Prop) -> None:
        """``boat`` (standing where the stage put it) rests on the water from now on."""
        feet = boat.feet()
        boat.afloat = (float(feet[0]), float(feet[1]))
        self.boats.append((boat, bob_phase(boat.name)))

    def update(self, now: float, riders: Callable[[Prop], Sequence[RiderSeat]] = lambda boat: ()) -> None:
        """The waves and the boats at scene time ``now``; ``riders`` gives a boat's riders (they
        follow it)."""
        outline = front_outline(self.left, self.right, self.surface, self.bottom, now, self.unit, sign=self.sign)
        self._strip.set_points_as_corners(np.array([[x, y, 0.0] for x, y in [*outline, outline[0]]]))
        self._crest.set_points_as_corners(np.array([[x, y, 0.0] for x, y in reversed(outline[2:])]))
        for boat, phase in self.boats:
            if boat.afloat is None:
                continue
            rise, rock = boat_bob(now, phase)
            boat.pose_at(boat.afloat[0], boat.afloat[1] + rise * self.unit, rock)
            for seat in riders(boat):
                place_rider(seat)

    def contains(self, x: float) -> bool:
        """Whether ``x`` is over the water."""
        return self.left <= x <= self.right


__all__ = ["StageWater"]
