"""Things drawn over an iso place's pictures that move by themselves (DESIGN.md §100.7, §100.11):
the steel shutters over a room's windows and the blinking lights of its lab objects. Each is a
*living thing* of the stage (``update_to``, ``changing``, ``done``, ``movers``, ``region``), drawn
right after the place's pictures (behind the characters).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from manim import Circle, VGroup, VMobject

from vidgen.cartoon.alarm import shutter_level, shutters_changing
from vidgen.cartoon.living import _unit

#: Shutters: the steel's colour, its slats' colour and how many slats a window has.
SHUTTER_STEEL = "#8E96A3"
SHUTTER_SLAT = "#5D6573"
SHUTTER_SLATS = 7

Box = tuple[float, float, float, float]
Point = tuple[float, float]


def _box(points: Sequence[Point]) -> Box:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


class IsoShutters(VGroup):
    """Steel shutters over ``windows`` (each four points on screen: bottom left, bottom right,
    top right, top left), down at the start when ``closed``; :meth:`move` closes or opens them
    at a scene time (:func:`~vidgen.cartoon.alarm.shutter_level`). ``stroke``: the slats' width."""

    def __init__(self, windows: Sequence[Sequence[Point]], *, closed: bool = False, stroke: float = 1.0) -> None:
        super().__init__()
        self.name = "shutters"
        self.windows = [tuple((float(x), float(y)) for x, y in w) for w in windows]
        self.closed = closed
        self.moves: list[tuple[float, bool]] = []
        self.plates: list[VMobject] = []
        self.slats: list[list[VMobject]] = []
        for _ in self.windows:
            plate = VMobject().set_fill(SHUTTER_STEEL, opacity=1.0).set_stroke(SHUTTER_SLAT, width=stroke, opacity=1.0)
            slats = [VMobject().set_fill(opacity=0.0).set_stroke(SHUTTER_SLAT, width=stroke, opacity=1.0) for _ in range(SHUTTER_SLATS)]
            self.plates.append(plate)
            self.slats.append(slats)
            self.add(plate, *slats)
        self.update_to(0.0)

    def move(self, close: bool, time: float) -> None:
        """Close (or open) the shutters from scene ``time``."""
        self.moves.append((float(time), bool(close)))

    def update_to(self, now: float) -> None:
        """Draw them as they are at scene time ``now``: each plate from its window's top down to
        its level, the slats on it."""
        level = shutter_level(self.closed, self.moves, now)
        for window, plate, slats in zip(self.windows, self.plates, self.slats):
            bl, br, tr, tl = (np.array([x, y, 0.0]) for x, y in window)
            if level <= 1e-4:
                plate.points = np.zeros((0, 3))
                for slat in slats:
                    slat.points = np.zeros((0, 3))
                continue
            low_l, low_r = tl + (bl - tl) * level, tr + (br - tr) * level
            plate.set_points_as_corners([tl, tr, low_r, low_l, tl])
            for k, slat in enumerate(slats):
                share = (k + 1) / (len(slats) + 1)
                if share < level:
                    left, right = tl + (low_l - tl) * (share / level), tr + (low_r - tr) * (share / level)
                    slat.set_points_as_corners([left, right])
                else:
                    slat.points = np.zeros((0, 3))

    def changing(self, start: float, end: float) -> bool:
        """Whether they move between scene times ``start`` and ``end``."""
        return shutters_changing(self.moves, start, end)

    def done(self, now: float) -> bool:
        """Whether every move is over at scene time ``now``."""
        return not shutters_changing(self.moves, now, math.inf)

    def movers(self) -> list[VMobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        """The box of every window (Manim units)."""
        boxes = [_box(w) for w in self.windows] or [(0.0, 0.0, 0.0, 0.0)]
        return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


#: Blinking lights: the radius of a light's halo (a share more than its own), the halo's opacity,
#: the seconds a light's blink takes (from .. to, seeded) and its share lit (from .. to).
LIGHT_HALO = 1.8
LIGHT_HALO_OPACITY = 0.22
BLINK_SECONDS = (0.35, 2.4)
BLINK_DUTY = (0.25, 0.8)


def blink_on(index: int, now: float, seed: int = 0) -> bool:
    """Whether light ``index`` is lit at scene time ``now``: each blinks at its own seeded
    period and share lit; one in four flickers fast, like a disk at work."""
    period = BLINK_SECONDS[0] + (BLINK_SECONDS[1] - BLINK_SECONDS[0]) * _unit(seed, "blink", index)
    if index % 4 == 3:
        period *= 0.25
    duty = BLINK_DUTY[0] + (BLINK_DUTY[1] - BLINK_DUTY[0]) * _unit(seed, "duty", index)
    phase = _unit(seed, "phase", index)
    return ((now / period + phase) % 1.0) < duty


class IsoBlinkers(VGroup):
    """Small lights at ``points`` (on screen) of ``radius``, in ``colors`` (one per light), each
    blinking by :func:`blink_on` with a soft halo; never graded by the stage's light."""

    def __init__(self, points: Sequence[Point], colors: Sequence[str], radius: float, *, seed: int = 0) -> None:
        super().__init__()
        self.name = "lab_lights"
        self.points_xy = [(float(x), float(y)) for x, y in points]
        self.radius = radius
        self.seed = seed
        unit = Circle(radius=1.0).points
        self.lights: list[tuple[VMobject, VMobject]] = []
        for (x, y), color in zip(self.points_xy, colors):
            halo = VMobject().set_fill(color, opacity=0.0).set_stroke(width=0.0, opacity=0.0)
            halo.points = unit * (radius * LIGHT_HALO) + np.array([x, y, 0.0])
            dot = VMobject().set_fill(color, opacity=0.0).set_stroke(width=0.0, opacity=0.0)
            dot.points = unit * radius + np.array([x, y, 0.0])
            self.lights.append((halo, dot))
            self.add(halo, dot)
        self.update_to(0.0)

    def update_to(self, now: float) -> None:
        """Light each one as it is at scene time ``now``."""
        for k, (halo, dot) in enumerate(self.lights):
            lit = blink_on(k, now, self.seed)
            dot.set_fill(opacity=1.0 if lit else 0.0)
            halo.set_fill(opacity=LIGHT_HALO_OPACITY if lit else 0.0)

    def changing(self, start: float, end: float) -> bool:
        return bool(self.lights)

    def done(self, now: float) -> bool:
        return not self.lights

    def movers(self) -> list[VMobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        pad = self.radius * LIGHT_HALO
        xs = [p[0] for p in self.points_xy] or [0.0]
        ys = [p[1] for p in self.points_xy] or [0.0]
        return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


__all__ = ["BLINK_DUTY", "BLINK_SECONDS", "SHUTTER_SLATS", "IsoBlinkers", "IsoShutters", "blink_on"]
