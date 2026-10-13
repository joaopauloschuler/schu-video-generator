"""Motion effects drawn and moved with manim (DESIGN.md §69.41); when they fire and their shapes
are in :mod:`vidgen.cartoon.motion_effects`.

A :class:`MotionEffect` is a mobject of its own, never a part of the character or prop it goes
with (a character's parts never change, §69.22): an updater counts its seconds from the frame its
cue was made on, waits for the cue's start, then on every frame redraws its shapes where the mover
is (speed lines behind it as it goes, a whoosh behind the hand) or where the mover was when it
started (dust and stars stay on the ground), and draws nothing once its cue is over (:attr:`done`).
"""

from __future__ import annotations

import math

import numpy as np
from manim import Mobject, VGroup, VMobject

from vidgen.cartoon.character import OUTLINE_WIDTH, REFERENCE_HEIGHT, Character, one_pixel_stroke
from vidgen.cartoon.effects import Point, _circle, _star, thick_path
from vidgen.cartoon.motion_effects import (
    DUST_PUFFS,
    IMPACT_STARS,
    SPEED_LINES,
    WHOOSH_TRAIL_SECONDS,
    MotionEffectCue,
    arc_band,
    dust_puffs,
    fade,
    impact_stars,
    speed_lines,
)
from vidgen.cartoon.transition import feet_of
from vidgen.cartoon.stage import facing_sign
from vidgen.config import CHARACTER_INK
from vidgen.particles import KINDS as PARTICLE_SPECS

#: The dust's colour (the ``dust`` particles'), and the opacity of its ink outline.
DUST_COLOR = PARTICLE_SPECS["dust"].colors[0]
DUST_OUTLINE_OPACITY = 0.5
#: Speed lines and whoosh arcs: ink at this opacity, this wide (mover heights).
LINE_OPACITY = 0.55
LINE_WIDTH = 0.016
WHOOSH_WIDTH = 0.03
#: A whoosh runs along two arcs about the shoulder, at these shares of the hand's distance.
WHOOSH_RADII: tuple[float, ...] = (1.12, 0.96)
#: Behind a prop, speed lines are as long and wide as behind a mover this tall at least (units):
#: lines scaled by a small ball would be specks.
PROP_LINE_UNIT = 2.0
#: Outline width as a share of a character's.
OUTLINE_SHARE = 0.6
#: A prop moving less than this from one frame to the next (units) keeps the direction its speed
#: lines had.
STILL_MOVE = 1e-3


def _shape(fill: str, opacity: float, stroke: float, stroke_opacity: float) -> VMobject:
    mob = VMobject()
    mob.set_fill(fill, opacity=opacity)
    mob.set_stroke(CHARACTER_INK, width=stroke, opacity=stroke_opacity)
    return mob


class MotionEffect(VGroup):
    """The ``cue`` (:class:`~vidgen.cartoon.motion_effects.MotionEffectCue`) drawn for ``mover``
    (a :class:`Character`, or a prop for speed lines): its cue starts ``delay`` seconds after the
    frame it is added on; ``seed`` picks its puffs, stars and lines; ``scale`` sizes them
    (:func:`~vidgen.cartoon.motion_effects.effect_scale`); ``star_color``: the stars' fill (hex).
    ``kind`` and ``effect_of`` (the mover's name) are the layout dump's; ``done``: its cue is over
    and it draws nothing."""

    def __init__(
        self,
        cue: MotionEffectCue,
        mover: Mobject,
        *,
        delay: float,
        seed: int,
        scale: float = 1.0,
        star_color: str = "#FFD166",
        effect_of: str | None = None,
    ) -> None:
        super().__init__()
        self.cue, self.kind, self.mover, self.effect_of = cue, cue.kind, mover, effect_of
        self.delay, self.seed, self.size_factor = float(delay), seed, scale
        self.clock = 0.0
        self.done = False
        self._anchor: np.ndarray | None = None
        self._direction: np.ndarray | None = None
        self._last: np.ndarray | None = None
        self._size = 1.0
        self._angles: list[tuple[float, float]] = []
        height = self._mover_height()
        stroke = max(OUTLINE_WIDTH * OUTLINE_SHARE * height / REFERENCE_HEIGHT, one_pixel_stroke())
        if self.kind == "dust":
            shapes = [_shape(DUST_COLOR, 1.0, stroke, DUST_OUTLINE_OPACITY) for _ in range(DUST_PUFFS)]
        elif self.kind == "impact":
            shapes = [_shape(star_color, 1.0, stroke, 1.0) for _ in range(IMPACT_STARS)]
        elif self.kind == "speed_lines":
            shapes = [_shape(CHARACTER_INK, LINE_OPACITY, 0.0, 0.0) for _ in range(SPEED_LINES)]
        else:
            shapes = [_shape(CHARACTER_INK, LINE_OPACITY, 0.0, 0.0) for _ in WHOOSH_RADII]
        self.add(*shapes)
        self.add_updater(MotionEffect._step)

    def _mover_height(self) -> float:
        if isinstance(self.mover, Character):
            return self.mover.character_height
        if getattr(self.mover, "is_vehicle", False):   # a long bus raises dust as tall as it, not as long
            return max(float(self.mover.height), 1e-6)
        return max(float(self.mover.height), float(self.mover.width), 1e-6)

    @staticmethod
    def _step(mob: Mobject, dt: float) -> None:
        mob.clock += dt
        mob.draw(mob.clock - mob.delay)

    def draw(self, age: float) -> MotionEffect:
        """Draw it ``age`` seconds into its cue (nothing before the start or after the end)."""
        if age < 0.0 or age >= self.cue.seconds or self.done:
            self.done = self.done or age >= self.cue.seconds
            self._hide(range(len(self.submobjects)))
            return self
        if self._anchor is None:
            self._start()
        drawn = {"dust": self._dust, "impact": self._impact, "speed_lines": self._lines, "whoosh": self._whoosh}[self.kind](age)
        self._hide(range(drawn, len(self.submobjects)))
        return self

    def _hide(self, members: range) -> None:
        for k in members:
            self.submobjects[k].points = np.zeros((0, 3))

    def _set(self, k: int, points: tuple[Point, ...] | list[Point], opacity: float | None = None) -> None:
        member = self.submobjects[k]
        member.set_points_as_corners(np.array([[x, y, 0.0] for x, y in (*points, points[0])]))
        if opacity is not None:
            member.set_fill(opacity=opacity * (LINE_OPACITY if self.kind in ("speed_lines", "whoosh") else 1.0))
            if self.kind == "dust":
                member.set_stroke(opacity=opacity * DUST_OUTLINE_OPACITY)

    def _start(self) -> None:
        """Where it starts: the mover's feet, its size and, for a character or a vehicle, the way it
        faces (another prop's way is found as it moves); a vehicle's dust rises at its back end
        (setting off) or its front end (stopping)."""
        self._anchor = np.array(feet_of(self.mover), dtype=float)
        self._size = self._mover_height()
        if isinstance(self.mover, Character) or getattr(self.mover, "is_vehicle", False):
            self._direction = np.array([facing_sign(self.mover.facing), 0.0])
        if getattr(self.mover, "is_vehicle", False) and self.kind == "dust":
            ahead = float(self._direction[0]) > 0
            front = self.cue.toward == "front"
            self._anchor[0] = float(self.mover.get_right()[0] if ahead == front else self.mover.get_left()[0])

    def _dust(self, age: float) -> int:
        h, side = self._size * self.size_factor, float(self._direction[0])
        puffs = dust_puffs(age, self.seed, self.cue.toward)
        for k, puff in enumerate(puffs):
            cx, cy = self._anchor[0] + side * puff.x * self._size, self._anchor[1] + puff.y * h
            self._set(k, [(cx + x * puff.radius * h, cy + y * puff.radius * h) for x, y in _circle(0.0, 0.0, 1.0, 20)], puff.opacity)
        return len(puffs)

    def _impact(self, age: float) -> int:
        h = self._size * self.size_factor
        stars = [s for s in impact_stars(age, self.seed) if s.size > 1e-3]
        for k, star in enumerate(stars):
            c, s = math.cos(math.radians(star.angle)), math.sin(math.radians(star.angle))
            cx, cy = self._anchor[0] + star.x * self._size, self._anchor[1] + star.y * self._size
            outline = _star(5, star.size * h, 0.45 * star.size * h)
            self._set(k, [(cx + x * c - y * s, cy + x * s + y * c) for x, y in outline])
        return len(stars)

    def _way(self) -> tuple[np.ndarray, np.ndarray] | None:
        """The way the mover goes now (unit vector) and the middle of its back edge."""
        mover = self.mover
        if isinstance(mover, Character):
            ahead = np.array([facing_sign(mover.facing), 0.0])
            back = mover.get_left()[0] if ahead[0] > 0 else mover.get_right()[0]
            return ahead, np.array([float(back), float(mover.feet()[1]) + 0.45 * self._size])
        middle = np.array(mover.get_center()[:2], dtype=float)
        if self._last is not None and np.linalg.norm(middle - self._last) > STILL_MOVE:
            self._direction = (middle - self._last) / np.linalg.norm(middle - self._last)
        self._last = middle
        if self._direction is None:
            return None
        if getattr(mover, "is_vehicle", False):   # from its back end, halfway up
            back = mover.get_left()[0] if self._direction[0] > 0 else mover.get_right()[0]
            return self._direction, np.array([float(back), float(feet_of(mover)[1]) + 0.45 * self._size])
        return self._direction, middle - self._direction * self._size / 2

    def _lines(self, age: float) -> int:
        found = self._way()
        if found is None:
            return 0
        ahead, back = found
        across = np.array([-ahead[1], ahead[0]])
        size = self._size if isinstance(self.mover, Character) else max(self._size, PROP_LINE_UNIT)
        width = LINE_WIDTH * size * self.size_factor
        lines = [line for line in speed_lines(age, self.cue.seconds, self.seed) if line.length * size > width]
        for k, line in enumerate(lines):
            base = back + across * line.across * 1.5 * self._size * self.size_factor
            tail = base - ahead * (line.behind + line.length) * size
            head = base - ahead * line.behind * size
            self._set(k, thick_path([tuple(tail), tuple(head)], width), line.opacity)
        return len(lines)

    def _whoosh(self, age: float) -> int:
        figure = self.mover
        if not isinstance(figure, Character):
            return 0
        arm = self.cue.arm or ("arm_left" if figure.has_part("arm_left") else "arm_right")
        hand = "left" if arm == "arm_left" else "right"
        if not figure.has_part(arm):
            return 0
        shoulder, point = figure.shoulder_point(hand)[:2], figure.hand_point(hand)[:2]
        radius = float(np.linalg.norm(point - shoulder))
        angle = math.degrees(math.atan2(point[1] - shoulder[1], point[0] - shoulder[0]))
        if self._angles:   # keep the angle continuous (no jump at ±180°)
            angle += 360.0 * round((self._angles[-1][1] - angle) / 360.0)
        self._angles.append((age, angle))
        then = _angle_at(self._angles, age - WHOOSH_TRAIL_SECONDS)
        if abs(angle - then) < 3.0 or radius <= 0:
            return 0
        weight = fade(age, self.cue.seconds)
        width = WHOOSH_WIDTH * self._size * self.size_factor
        for k, share in enumerate(WHOOSH_RADII):
            self._set(k, arc_band(float(shoulder[0]), float(shoulder[1]), radius * share, then, angle, width), weight)
        return len(WHOOSH_RADII)


def _angle_at(angles: list[tuple[float, float]], age: float) -> float:
    """The angle at ``age`` in ``angles`` ((age, angle), in time order), interpolated; the first
    one before them."""
    if age <= angles[0][0]:
        return angles[0][1]
    for (a0, v0), (a1, v1) in zip(angles, angles[1:]):
        if a0 <= age <= a1:
            return v0 if a1 <= a0 else v0 + (v1 - v0) * (age - a0) / (a1 - a0)
    return angles[-1][1]
