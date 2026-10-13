"""Props that move by themselves, drawn and moved with manim (DESIGN.md §69.54); the maths is in
:mod:`vidgen.cartoon.living`.

A prop drawn ``living`` (:func:`living_overlays`, added by ``draw_prop(..., living=True)``) gets
the parts that change, tagged with :data:`LIVING_PART`: a running clock's second hand (its hour and
minute hands are tagged in its drawing), a television's picture over its screen, a lamp's lit
lantern. A :class:`LivingProp` sets them for a scene time on every frame; a lamp's or a
television's :class:`PropGlow` is a mobject of its own, drawn right behind the prop (so the prop's
box, shadow and layout stay as drawn) and never graded by the stage's light.
"""

from __future__ import annotations

import numpy as np
from manim import Circle, Mobject, VGroup, VMobject

from vidgen.cartoon.character import OUTLINE_WIDTH
from vidgen.cartoon.living import (
    DRAWN_CLOCK_SECONDS,
    GLOWS,
    LIVING_PART,
    Box,
    GlowSpec,
    clock_seconds,
    glow_box,
    glow_rings,
    hand_angles,
    hand_tip,
    on_between,
    shows_second_hand,
    switch_between,
    switched_on,
    tv_picture,
    union_box,
)
from vidgen.cartoon.props import Prop, _circle, _ellipse, _line, _Paint, _poly, _rect
from vidgen.cartoon.room import darker
from vidgen.cartoon.shading import LIT

#: Where a clock's hands turn (prop units) and how long each is.
CLOCK_CENTRE = (0.0, 0.5)
HAND_LENGTHS: dict[str, float] = {"hour": 0.2, "minute": 0.3, "second": 0.34}
#: A running clock's second hand, and a lit lamp's lantern and its bright core (fixed colours:
#: no theme token is red or warm white in every theme).
SECOND_HAND = "#C8473E"
LIT_LANTERN = "#FFE08A"
LIT_CORE = "#FFF8E1"


def tag(mob: VMobject, part: str) -> VMobject:
    """Mark ``mob`` as the living part ``part`` of a prop's drawing; returns it."""
    setattr(mob, LIVING_PART, part)
    return mob


def living_overlays(kind: str, paint: _Paint) -> list[VMobject]:
    """The parts a ``kind`` prop draws on top of itself when it lives, in prop units: a clock's
    second hand, a television's picture (sky, ground and two shapes over its screen, outlined like
    it), a lamp's lit lantern. None for other props."""
    if kind == "clock":
        x, y = CLOCK_CENTRE
        return [tag(_line(x, y, x, y + HAND_LENGTHS["second"], SECOND_HAND, OUTLINE_WIDTH), "second")]
    if kind == "tv":
        return [tag(mob, "picture") for mob in (
            _rect(-0.55, 0.46, 0.55, 0.94, paint.detail, paint),
            _rect(-0.55, 0.46, 0.55, 0.62, paint.detail, paint, outline=False),
            _circle(-0.25, 0.75, 0.1, paint.detail, paint, outline=False),
            _poly([(0.08, 0.62), (0.3, 0.84), (0.52, 0.62)], paint.detail, paint, outline=False),
        )]
    if kind == "lamp":
        return [
            tag(_poly([(-0.07, 0.8), (0.07, 0.8), (0.1, 0.92), (-0.1, 0.92)], LIT_LANTERN, paint), "lantern"),
            tag(_ellipse(0.0, 0.86, 0.09, 0.07, LIT_CORE, paint, outline=False), "lantern"),
        ]
    return []


def living_parts(prop: Prop, part: str) -> list[VMobject]:
    """The members of ``prop``'s drawing tagged ``part``, in drawing order."""
    return [m for m in prop.get_family() if getattr(m, LIVING_PART, None) == part]


class _Shown:
    """Shows or hides members, keeping the fill and stroke opacities they were drawn with."""

    def __init__(self, members: list[VMobject]) -> None:
        self.members = members
        self._drawn = [(float(m.get_fill_opacity()), float(m.get_stroke_opacity())) for m in members]

    def show(self, shown: bool) -> None:
        for member, (fill, stroke) in zip(self.members, self._drawn):
            member.set_fill(opacity=fill if shown else 0.0)
            member.set_stroke(opacity=stroke if shown else 0.0)


class PropGlow(VGroup):
    """A soft glow: :func:`~vidgen.cartoon.living.glow_rings` discs of one colour, placed by
    :meth:`place`."""

    def __init__(self, spec: GlowSpec, *, name: str) -> None:
        super().__init__()
        self.spec = spec
        self.name = name
        self._unit = Circle(radius=1.0).points.copy()
        self._rings = glow_rings(1.0, spec.opacity)
        for _ in self._rings:
            disc = VMobject()
            disc.points = self._unit.copy()
            disc.set_fill(spec.color, opacity=0.0)
            disc.set_stroke(width=0.0, opacity=0.0)
            self.add(disc)

    def place(self, x: float, y: float, radius: float, strength: float) -> PropGlow:
        """Centre it on (``x``, ``y``) with ``radius`` (Manim units), at ``strength`` (0: off, 1:
        its full opacity)."""
        for disc, (share, opacity) in zip(self.submobjects, self._rings):
            disc.points = self._unit * (radius * share) + np.array([x, y, 0.0])
            disc.set_fill(opacity=opacity * strength)
        return self


class LivingProp:
    """A prop that moves by itself (drawn ``living``): a clock running from ``start`` (seconds
    after midnight) at ``speed``, or a television or a lamp, ``on`` from the start, switched by
    :meth:`switch`. ``seed`` varies a television's pictures; ``movable``: an action may move the
    prop, so its glow follows it on every frame."""

    def __init__(self, prop: Prop, *, start: float | None = None, speed: float = 1.0, on: bool = False, seed: int = 0,
                 movable: bool = False) -> None:
        self.prop = prop
        self.kind = prop.kind
        self.start = DRAWN_CLOCK_SECONDS if start is None else float(start)
        self.speed = float(speed)
        self.on = bool(on)
        self.seed = seed
        self.movable = movable
        #: Each switch: (scene time, on).
        self.switches: list[tuple[float, bool]] = []
        self.hands = {name: living_parts(prop, name) for name in HAND_LENGTHS} if self.kind == "clock" else {}
        if self.hands:
            _Shown(self.hands["second"]).show(shows_second_hand(self.speed))
        self.overlays = living_parts(prop, "picture") + living_parts(prop, "lantern")
        self._shown = _Shown(self.overlays)
        spec = GLOWS.get(self.kind)
        #: Its glow (``None``: a clock), drawn right behind it.
        self.glow = PropGlow(spec, name=f"{prop.name}_glow") if spec is not None else None
        for member in [m for mob in (self.movers() if self.kind != "clock" else []) for m in mob.get_family()]:
            setattr(member, LIT, False)   # a lit screen or lamp shines at night too (§69.31's grade skips it); hands stay graded
        self.update(0.0)

    def switch(self, on: bool, time: float) -> None:
        """Switch it on (or off) at scene ``time``."""
        self.switches.append((float(time), bool(on)))

    def is_on(self, now: float) -> bool:
        """Whether it is on at scene time ``now`` (a clock always runs)."""
        return self.kind == "clock" or switched_on(self.on, self.switches, now)

    def changing(self, start: float, end: float) -> bool:
        """Whether it changes between scene times ``start`` and ``end``: a clock always, a
        television while it is on, a lamp when switched (or moved while on)."""
        if self.kind == "clock":
            return True
        if switch_between(self.switches, start, end):
            return True
        on = on_between(self.on, self.switches, start, end)
        return on and (self.kind == "tv" or self.movable)

    def movers(self) -> list[Mobject]:
        """The mobjects it changes on every frame: the hands, or the picture / lantern and the glow."""
        if self.kind == "clock":
            return [m for members in self.hands.values() for m in members]
        return [*self.overlays, *([self.glow] if self.glow is not None else [])]

    def region(self) -> Box:
        """The box of what it may change (Manim units): the prop and its glow."""
        low, high = self.prop.get_corner(np.array([-1.0, -1.0, 0.0])), self.prop.get_corner(np.array([1.0, 1.0, 0.0]))
        box = (float(low[0]), float(low[1]), float(high[0]), float(high[1]))
        if self.glow is None:
            return box
        x, y, radius = self._glow_place()
        return union_box(box, glow_box(x, y, radius))

    def _glow_place(self) -> tuple[float, float, float]:
        assert self.glow is not None
        spec = self.glow.spec
        centre = self.prop.prop_point(spec.x, spec.y)
        return float(centre[0]), float(centre[1]), spec.radius * self.prop.unit

    def update(self, now: float) -> None:
        """Show it as it is at scene time ``now``."""
        if self.kind == "clock":
            self._turn_hands(clock_seconds(self.start, self.speed, now))
            return
        on = self.is_on(now)
        self._shown.show(on)
        strength = 1.0 if on else 0.0
        if on and self.kind == "tv":
            picture = tv_picture(now, self.seed)
            for member, color in zip(self.overlays, picture.colors):
                member.set_fill(darker(color, 1.0 - picture.brightness), opacity=1.0)
            strength = picture.brightness
        if self.glow is not None:
            self.glow.place(*self._glow_place(), strength)

    def _turn_hands(self, seconds: float) -> None:
        angles = hand_angles(seconds)
        centre = self.prop.prop_point(*CLOCK_CENTRE)
        unit = self.prop.unit
        for name, members in self.hands.items():
            degrees = getattr(angles, name)
            for hand in members:
                x, y = hand_tip(float(centre[0]), float(centre[1]), HAND_LENGTHS[name] * unit, degrees)
                hand.set_points_as_corners(np.array([centre, [x, y, 0.0]]))


__all__ = ["CLOCK_CENTRE", "HAND_LENGTHS", "LivingProp", "PropGlow", "living_overlays", "living_parts", "tag"]
