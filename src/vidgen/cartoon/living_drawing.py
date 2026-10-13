"""Props that move by themselves, drawn and moved with manim (DESIGN.md §69.54, §69.55); the
maths is in :mod:`vidgen.cartoon.living`.

A prop drawn ``living`` (:func:`living_overlays`, added by ``draw_prop(..., living=True)``) gets
the parts that change, tagged with :data:`LIVING_PART`: a running clock's second hand (its hour and
minute hands are tagged in its drawing), a television's picture over its screen, a lamp's lit
lantern, a fireplace's flames (behind its front logs), a phone's lit screen and ring lines (the
whole phone shakes while it rings). A :class:`LivingProp` sets them for a scene
time on every frame; a lamp's, a television's or a fireplace's :class:`PropGlow` is a mobject of
its own, drawn right behind the prop (so the prop's box, shadow and layout stay as drawn) and
never graded by the stage's light; a kettle's :class:`PropSteam` is one too, drawn right in front
of it (the steam rises above the kettle's box).
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
from manim import Circle, Mobject, VGroup, VMobject

from vidgen.cartoon.character import OUTLINE_WIDTH, one_pixel_stroke
from vidgen.cartoon.living import (
    DRAWN_CLOCK_SECONDS,
    GLOWS,
    LIVING_PART,
    RING_TILT,
    STEAM_LEAN_MAX,
    STEAM_PUFFS,
    Box,
    GlowSpec,
    clock_seconds,
    fire_flicker,
    flame_lean,
    flame_shapes,
    glow_box,
    glow_rings,
    hand_angles,
    hand_tip,
    on_between,
    on_since,
    ring_burst,
    ring_shake,
    shows_second_hand,
    steam_box,
    steam_puffs,
    switch_between,
    switched_on,
    tv_picture,
    union_box,
)
from vidgen.cartoon.props import Prop, _circle, _ellipse, _line, _Paint, _poly, _rect
from vidgen.cartoon.room import darker
from vidgen.cartoon.shading import LIT, mark_lit

#: Where a clock's hands turn (prop units) and how long each is.
CLOCK_CENTRE = (0.0, 0.5)
HAND_LENGTHS: dict[str, float] = {"hour": 0.2, "minute": 0.3, "second": 0.34}
#: A running clock's second hand, and a lit lamp's lantern and its bright core (fixed colours:
#: no theme token is red or warm white in every theme).
SECOND_HAND = "#C8473E"
LIT_LANTERN = "#FFE08A"
LIT_CORE = "#FFF8E1"
#: A fire's outer and inner tongues and the edge of the outer ones; a kettle's steam.
FLAME_OUTER = "#F2762E"
FLAME_INNER = "#FFD25A"
FLAME_EDGE = "#C9472A"
STEAM = "#F4F6FA"
#: The steam puffs' faint edge: its colour, width (pixels) and opacity (a share of the puff's).
STEAM_EDGE = "#AEB9C6"
STEAM_EDGE_PIXELS = 1.5
STEAM_EDGE_SHARE = 0.7
#: A ringing phone (DESIGN.md §69.56): its lit screen, the middle it shakes about, the ring lines
#: beside it (prop units) and their colour (amber: it shows on light and dark backgrounds).
LIT_SCREEN = "#E3F4FF"
PHONE_CENTRE = (0.0, 0.6)
RING_RADII = (0.4, 0.54)
RING_LINE = "#E8A33D"


def closed_curve(corners: np.ndarray) -> np.ndarray:
    """A smooth closed curve through ``corners`` (n x 2) as Manim's cubic Bézier points (4 per
    corner, n x 4 x 3 flattened, z 0): Catmull-Rom tangents, so each piece leaves a corner towards
    the next one's neighbour (a flame redrawn on every frame, faster than ``set_points_smoothly``)."""
    before, after, after2 = np.roll(corners, 1, axis=0), np.roll(corners, -1, axis=0), np.roll(corners, -2, axis=0)
    pieces = np.stack([corners, corners + (after - before) / 6.0, after - (after2 - corners) / 6.0, after], axis=1)
    out = np.zeros((len(corners) * 4, 3))
    out[:, :2] = pieces.reshape(-1, 2)
    return out


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
    if kind == "phone":
        rings: list[VMobject] = []
        for side in (-1.0, 1.0):
            for radius in RING_RADII:
                x, y = PHONE_CENTRE
                points = [np.array([x + side * radius * math.cos(a), y + radius * math.sin(a), 0.0]) for a in np.linspace(-0.5, 0.5, 7)]
                arc = VMobject().set_points_smoothly(points).set_fill(opacity=0).set_stroke(RING_LINE, width=2.5 * OUTLINE_WIDTH)
                rings.append(tag(arc, "ring"))
        return [
            tag(_rect(-0.22, 0.1, 0.22, 0.88, LIT_SCREEN, paint, radius=0.02), "screen"),
            tag(_ellipse(0.0, 0.36, 0.28, 0.2, paint.detail, paint, outline=False), "screen"),
            tag(_circle(0.0, 0.6, 0.09, paint.detail, paint, outline=False), "screen"),
            *rings,
        ]
    if kind == "fireplace":
        flames: list[VMobject] = []
        for shape in flame_shapes(0.0, 0):
            flame = VMobject()
            flame.points = closed_curve(np.array(shape.points, dtype=float))
            flame.set_fill(FLAME_INNER if shape.inner else FLAME_OUTER, opacity=1.0)
            flame.set_stroke(FLAME_EDGE, width=0.0 if shape.inner else OUTLINE_WIDTH, opacity=0.0 if shape.inner else 1.0)
            flames.append(tag(flame, "flame"))
        return flames
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


class PropSteam(VGroup):
    """A kettle's steam: :data:`~vidgen.cartoon.living.STEAM_PUFFS` soft discs placed by
    :meth:`place`."""

    def __init__(self, *, name: str) -> None:
        super().__init__()
        self.name = name
        self._unit = Circle(radius=1.0).points.copy()
        for _ in range(STEAM_PUFFS):
            puff = VMobject()
            puff.points = self._unit.copy()
            puff.set_fill(STEAM, opacity=0.0)
            puff.set_stroke(STEAM_EDGE, width=STEAM_EDGE_PIXELS * one_pixel_stroke(), opacity=0.0)
            self.add(puff)

    def place(self, puffs: list[tuple[float, float, float, float]]) -> PropSteam:
        """Draw the puffs (x, y, radius in Manim units, opacity; a faint edge, so steam shows on a
        pale sky too); the discs left over are hidden."""
        for k, disc in enumerate(self.submobjects):
            if k < len(puffs):
                x, y, radius, opacity = puffs[k]
                disc.points = self._unit * radius + np.array([x, y, 0.0])
                disc.set_fill(opacity=opacity)
                disc.set_stroke(opacity=STEAM_EDGE_SHARE * opacity)
            else:
                disc.set_fill(opacity=0.0)
                disc.set_stroke(opacity=0.0)
        return self


class LivingProp:
    """A prop that moves by itself (drawn ``living``): a clock running from ``start`` (seconds
    after midnight) at ``speed``, or a television, a lamp, a fireplace, a kettle or a phone (on:
    ringing), ``on`` from the start, switched by :meth:`switch`. ``seed`` varies a television's pictures, a fire's flicker
    and a kettle's puffs; ``movable``: an action may move the prop, so its glow follows it on every
    frame; ``wind``: the felt wind force at a scene time (a fire's flames and a kettle's steam lean
    with it; ``None``: calm)."""

    def __init__(self, prop: Prop, *, start: float | None = None, speed: float = 1.0, on: bool = False, seed: int = 0,
                 movable: bool = False, wind: Callable[[float], float] | None = None) -> None:
        self.prop = prop
        self.kind = prop.kind
        self.start = DRAWN_CLOCK_SECONDS if start is None else float(start)
        self.speed = float(speed)
        self.on = bool(on)
        self.seed = seed
        self.movable = movable
        self.wind = wind
        #: Each switch: (scene time, on).
        self.switches: list[tuple[float, bool]] = []
        self.hands = {name: living_parts(prop, name) for name in HAND_LENGTHS} if self.kind == "clock" else {}
        if self.hands:
            _Shown(self.hands["second"]).show(shows_second_hand(self.speed))
        self.flames = living_parts(prop, "flame")
        self.overlays = living_parts(prop, "picture") + living_parts(prop, "lantern") + self.flames + living_parts(prop, "screen")
        self._shown = _Shown(self.overlays)
        #: A phone's ring lines, shown in each burst of rings, and its whole drawing in prop
        #: units (each member with points but the anchor), redrawn turned as it shakes (§69.56).
        self.rings = living_parts(prop, "ring")
        self._rings = _Shown(self.rings)
        anchor = prop.anchor
        self._body = [(m, prop.drawn_points(m.points)) for m in prop.family_members_with_points() if m is not anchor] if self.kind == "phone" else []
        spec = GLOWS.get(self.kind)
        #: Its glow (``None``: a clock, a kettle or a phone), drawn right behind it.
        self.glow = PropGlow(spec, name=f"{prop.name}_glow") if spec is not None else None
        #: A kettle's steam (``None``: another prop), drawn right in front of it.
        self.steam = PropSteam(name=f"{prop.name}_steam") if self.kind == "kettle" else None
        for member in [m for mob in (self.movers() if self.kind not in ("clock", "kettle", "phone") else self.overlays) for m in mob.get_family()]:
            setattr(member, LIT, False)   # a lit screen, lamp or fire shines at night too (§69.31's grade skips it); hands stay graded
        if self.steam is not None:
            mark_lit(self.steam)   # steam is graded like the set
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
        return on and (self.kind in ("tv", "fireplace", "kettle", "phone") or self.movable)

    def movers(self) -> list[Mobject]:
        """The mobjects it changes on every frame: the hands, or the picture / lantern / flames
        and the glow, or the steam, or a ringing phone's whole drawing."""
        if self.kind == "clock":
            return [m for members in self.hands.values() for m in members]
        if self.kind == "phone":
            return [m for m, _ in self._body]
        return [*self.overlays, *(m for m in (self.glow, self.steam) if m is not None)]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        """The box of what it may change (Manim units): the prop, its glow and its steam (the same
        at any scene times ``start`` to ``end``)."""
        low, high = self.prop.get_corner(np.array([-1.0, -1.0, 0.0])), self.prop.get_corner(np.array([1.0, 1.0, 0.0]))
        box = (float(low[0]), float(low[1]), float(high[0]), float(high[1]))
        if self._body:   # a shaking phone's corners swing out a little
            grow = math.sin(math.radians(RING_TILT)) * float(self.prop.height)
            box = (box[0] - grow, box[1] - grow, box[2] + grow, box[3] + grow)
        if self.glow is not None:
            x, y, radius = self._glow_place()
            box = union_box(box, glow_box(x, y, radius))
        if self.steam is not None:   # with wind it may lean either way
            boxes = [steam_box(0.0)] if self.wind is None else [steam_box(STEAM_LEAN_MAX), steam_box(-STEAM_LEAN_MAX)]
            corners = self.prop.prop_points(np.array([[x, y, 0.0] for b in boxes for x in (b[0], b[2]) for y in (b[1], b[3])]))
            box = union_box(box, (float(corners[:, 0].min()), float(corners[:, 1].min()), float(corners[:, 0].max()), float(corners[:, 1].max())))
        return box

    def _lean(self, now: float) -> float:
        """The felt wind force at scene time ``now`` (0 without wind)."""
        return float(self.wind(now)) if self.wind is not None else 0.0

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
        if self.kind == "phone":
            since = on_since(self.on, self.switches, now)
            self._shown.show(since is not None)
            self._rings.show(ring_burst(now, since))
            self._shake(ring_shake(now, since))
            return
        on = self.is_on(now)
        self._shown.show(on)
        strength = 1.0 if on else 0.0
        if on and self.kind == "tv":
            picture = tv_picture(now, self.seed)
            for member, color in zip(self.overlays, picture.colors):
                member.set_fill(darker(color, 1.0 - picture.brightness), opacity=1.0)
            strength = picture.brightness
        if on and self.kind == "fireplace":
            self._burn(now)
            strength = fire_flicker(now, self.seed)
        if self.steam is not None:
            self._steam(now if on else None)
        if self.glow is not None:
            self.glow.place(*self._glow_place(), strength)

    def _burn(self, now: float) -> None:
        """The flames as they are at scene time ``now``, leaning with the wind."""
        shapes = flame_shapes(now, self.seed, flame_lean(self._lean(now)))
        curves = [closed_curve(np.array(shape.points, dtype=float)) for shape in shapes]
        placed = self.prop.prop_points(np.vstack(curves))
        at = 0
        for flame, curve in zip(self.flames, curves):
            flame.points = placed[at : at + len(curve)]
            at += len(curve)

    def _steam(self, now: float | None) -> None:
        """The steam's puffs at scene time ``now`` (``None``: none, the kettle is off)."""
        assert self.steam is not None
        if now is None:
            self.steam.place([])
            return
        puffs = steam_puffs(now, self.seed, self._lean(now))
        middles = self.prop.prop_points(np.array([[p.x, p.y, 0.0] for p in puffs])) if puffs else np.zeros((0, 3))
        unit = self.prop.unit
        self.steam.place([(float(m[0]), float(m[1]), p.radius * unit, p.opacity) for m, p in zip(middles, puffs)])

    def _shake(self, degrees: float) -> None:
        """A phone's drawing turned ``degrees`` (counterclockwise as drawn facing right) about
        :data:`PHONE_CENTRE`, where it is now."""
        cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
        x, y = PHONE_CENTRE
        drawn = np.vstack([points for _, points in self._body])
        turned = drawn.copy()
        turned[:, 0] = x + (drawn[:, 0] - x) * cos - (drawn[:, 1] - y) * sin
        turned[:, 1] = y + (drawn[:, 0] - x) * sin + (drawn[:, 1] - y) * cos
        placed = self.prop.prop_points(turned)
        at = 0
        for member, points in self._body:
            member.points = placed[at : at + len(points)]
            at += len(points)

    def _turn_hands(self, seconds: float) -> None:
        angles = hand_angles(seconds)
        centre = self.prop.prop_point(*CLOCK_CENTRE)
        unit = self.prop.unit
        for name, members in self.hands.items():
            degrees = getattr(angles, name)
            for hand in members:
                x, y = hand_tip(float(centre[0]), float(centre[1]), HAND_LENGTHS[name] * unit, degrees)
                hand.set_points_as_corners(np.array([centre, [x, y, 0.0]]))


__all__ = ["CLOCK_CENTRE", "HAND_LENGTHS", "LivingProp", "PropGlow", "PropSteam", "living_overlays", "living_parts", "tag"]
