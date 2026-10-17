"""The coins and stars of a platform level, drawn (DESIGN.md §86.8): each a small mobject of its
own floating in the middle of its map cell, bobbing gently, that pops (grows, rises and fades)
when a walk or a jump of the rules (:func:`~vidgen.world.moves.route_pickups`) reaches it.

A :class:`Collectible` draws itself from an updater that counts its own seconds, like an effect
symbol: :meth:`Collectible.collect` (called by the move that picks it up, on the frame its feet
get there) starts the pop.
"""

from __future__ import annotations

import math

import numpy as np
from manim import Circle, Ellipse, Polygon, VGroup, VMobject

from vidgen.cartoon.character import OUTLINE_WIDTH, REFERENCE_HEIGHT, one_pixel_stroke
from vidgen.config import CHARACTER_INK
from vidgen.world import CHARACTER_TILES, COIN, STAR

#: Default fills of a coin and a star (``level.colors`` coin / star change them).
COIN_COLOR = "#F2C230"
STAR_COLOR = "#FFD84A"
#: A coin's radius and a star's outer and inner radii (tiles); the coin's inner ring.
COIN_RADIUS = 0.26
COIN_RING = 0.17
STAR_RADIUS = 0.32
STAR_INNER = 0.14
#: The idle bob: how far up and down (tiles) and how long one bob takes (s); a coin also turns
#: (narrows to ``COIN_TURN`` of its width and back) once a ``COIN_TURN_SECONDS``.
BOB_TILES = 0.06
BOB_SECONDS = 1.6
COIN_TURN = 0.7
COIN_TURN_SECONDS = 2.4
#: The pop when picked up: how long it takes (s), how much bigger it grows and how far it rises
#: (tiles) while it fades away.
POP_SECONDS = 0.35
POP_GROWTH = 0.6
POP_RISE = 0.8


def _shine(x: float, y: float, w: float, h: float) -> VMobject:
    mob = Ellipse(width=w, height=h).move_to([x, y, 0.0])
    mob.set_fill("#FFFFFF", opacity=0.85)
    mob.set_stroke(width=0.0, opacity=0.0)
    return mob


def _shapes(kind: str, fill: str, ring: str, stroke: float) -> list[VMobject]:
    """The shapes of a ``kind`` item about the origin, in tile units."""
    if kind == COIN:
        disc = Circle(radius=COIN_RADIUS).set_fill(fill, opacity=1.0).set_stroke(CHARACTER_INK, width=stroke)
        inner = Circle(radius=COIN_RING).set_fill(fill, opacity=0.0).set_stroke(ring, width=stroke * 0.8)
        return [disc, inner, _shine(-0.09, 0.1, 0.1, 0.06)]
    points = []
    for k in range(10):
        angle = math.pi / 2 + k * math.pi / 5
        r = STAR_RADIUS if k % 2 == 0 else STAR_INNER
        points.append([r * math.cos(angle), r * math.sin(angle) - 0.03, 0.0])
    star = Polygon(*points).round_corners(0.03).set_fill(fill, opacity=1.0).set_stroke(CHARACTER_INK, width=stroke)
    return [star, _shine(-0.07, 0.07, 0.08, 0.05)]


class Collectible(VGroup):
    """A ``kind`` item (a coin or a star) named ``name`` floating with its middle at ``center``
    (scene units) in a level whose tiles are ``tile`` units: filled with ``color`` (hex), outlined
    in the characters' ink. ``bobbing``: it bobs (and a coin turns) while it waits; ``phase``
    (0..1) puts items out of step. ``collected``: seconds since it was picked up (``None``: it
    has not been)."""

    def __init__(self, kind: str, name: str, center: tuple[float, float], tile: float, color: str, *,
                 bobbing: bool = True, phase: float = 0.0) -> None:
        super().__init__()
        self.kind, self.name = kind, name
        self.center = np.array([center[0], center[1], 0.0])
        self.tile = tile
        self.bobbing, self.phase = bobbing, phase
        self.age = 0.0
        self.collected: float | None = None
        stroke = max(OUTLINE_WIDTH * CHARACTER_TILES * tile / REFERENCE_HEIGHT * 0.7, one_pixel_stroke())
        ring = _darker(color)
        shapes = _shapes(kind if kind == COIN else STAR, color, ring, stroke)
        self.add(*shapes)
        self._home = [np.array(m.points, dtype=float) for m in shapes]
        self._fills = [m.get_fill_opacity() for m in shapes]
        self._strokes = [m.get_stroke_opacity() for m in shapes]
        self.add_updater(Collectible._step)
        self._draw()

    def collect(self) -> None:
        """Start the pop (once): it grows, rises and fades over :data:`POP_SECONDS`."""
        if self.collected is None:
            self.collected = 0.0

    @property
    def gone(self) -> bool:
        """Whether its pop is over (nothing is drawn)."""
        return self.collected is not None and self.collected >= POP_SECONDS

    def _step(self, dt: float) -> None:
        self.age += dt
        if self.collected is not None:
            self.collected += dt
        self._draw()

    def _draw(self) -> None:
        sx = sy = 1.0
        dy = 0.0
        fade = 1.0
        if self.bobbing and self.collected is None:
            dy = BOB_TILES * math.sin(2 * math.pi * (self.age / BOB_SECONDS + self.phase))
            if self.kind == COIN:
                sx = 1.0 - (1.0 - COIN_TURN) * 0.5 * (1.0 - math.cos(2 * math.pi * (self.age / COIN_TURN_SECONDS + self.phase)))
        if self.collected is not None:
            share = min(self.collected / POP_SECONDS, 1.0)
            grow = 1.0 + POP_GROWTH * share
            sx, sy = grow, grow
            dy = POP_RISE * (1.0 - (1.0 - share) ** 2)
            fade = 1.0 - share
        offset = self.center + np.array([0.0, dy * self.tile, 0.0])
        scale = np.array([sx * self.tile, sy * self.tile, 1.0])
        for member, home, fill, stroke in zip(self.submobjects, self._home, self._fills, self._strokes):
            member.points = home * scale + offset if fade > 0 else np.zeros((0, 3))
            if fade > 0:
                member.set_fill(opacity=fill * fade)
                member.set_stroke(opacity=stroke * fade)


def _darker(color: str) -> str:
    """``color`` (#rrggbb) a quarter darker: the coin's inner ring."""
    value = color.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return "#{:02X}{:02X}{:02X}".format(*(round(c * 0.75) for c in (r, g, b)))


__all__ = ["COIN_COLOR", "POP_SECONDS", "STAR_COLOR", "Collectible"]
