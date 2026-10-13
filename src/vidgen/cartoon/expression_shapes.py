"""The drawings of the Step 125 expressions (DESIGN.md §69.59), called by
:mod:`vidgen.cartoon.generator` for every generated look (people, animals, robots; side and front):

- eye shapes ``laughing`` (closed in arcs; flipped, the squeezed eyes of ``crying``), ``wide`` (a
  big white with a small pupil; on a screen a glowing ring), ``swirl`` and ``swirl_turned`` (a
  spiral, the idle motion alternates the two);
- mouth shapes ``laugh`` (open wide, flat on top, a tongue inside), ``tongue`` (sticking out) and
  ``wavy`` (a wobbly line); a beak's are in :func:`vidgen.cartoon.animals.beak_mouth`;
- the ``cheeks`` part: ``none`` (nothing drawn, the rest shape), ``blush`` (pink ovals; on a
  screen glowing strokes), ``tears`` and ``tears_running`` (streams from the eyes with drops lower
  down; the idle motion alternates the two);
- the ``bristles`` part, behind the head: ``none`` and ``up``: hair standing on end (a person
  with hair), fur tufts (a furry animal), feathers (a bird, an owl, a penguin), or fright lines
  over the head (no hair: a bald person, a frog, a turtle, a robot).

Character units before the figure is scaled to height 1; facing right, the face looks right.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

import numpy as np
from manim import PI, Arc, Circle, Ellipse, Line, VGroup, VMobject

from vidgen.cartoon import animals, robots
from vidgen.cartoon.character import CharacterPart
from vidgen.cartoon.primitives import Point, filled, outlined, point_at, polygon, tapered_band
from vidgen.config import CharacterLook

if TYPE_CHECKING:
    from vidgen.cartoon.generator import Frame

#: Shapes Step 125 added to parts every generated character has (after their earlier shapes).
EYE_SHAPES: tuple[str, ...] = ("laughing", "wide", "swirl", "swirl_turned")
MOUTH_SHAPES: tuple[str, ...] = ("laugh", "tongue", "wavy")
#: The shapes of the two parts Step 125 added (the first, ``none``, draws nothing).
CHEEK_SHAPES: tuple[str, ...] = ("none", "blush", "tears", "tears_running")
BRISTLE_SHAPES: tuple[str, ...] = ("none", "up")
#: Fixed colours: a blush, tears, a tongue (the pink of noses and inner ears).
BLUSH_COLOR = "#F0828F"
BLUSH_OPACITY = 0.7
TEAR_COLOR = "#7CC6F0"
TEAR_EDGE = "#3F8FC4"
TONGUE_COLOR = animals.PINK
#: Species with fur that stands up (a bird's, an owl's and a penguin's feathers do too).
FURRY: frozenset[str] = frozenset({"cat", "dog", "bear", "rabbit", "mouse", "fox"})


def nothing(x: float, y: float) -> VMobject:
    """A shape that draws nothing at (``x``, ``y``): one point, no fill area, no stroke (so a
    dimmed or faded character does not show it either)."""
    shape = VMobject(fill_opacity=0, stroke_width=0)
    shape.set_points(np.array([[x, y, 0.0]] * 4))
    return shape


def _curve(points: Sequence[Point]) -> VMobject:
    return VMobject().set_points_smoothly([[x, y, 0.0] for x, y in points]).set_fill(opacity=0)


# ----- eyes -----------------------------------------------------------------------------------------


def eye_shapes(look: CharacterLook, xs: Sequence[float], y: float, width: float, height: float, r: float,
               c: Mapping[str, str], w: float, white: str) -> dict[str, VMobject]:
    """The eyes' :data:`EYE_SHAPES` at ``xs`` (both eyes), ``y``, each eye ``width`` x ``height``
    open, for a head of radius ``r``; ``white`` the eyes' white (a screen's eyes glow instead)."""
    screen = robots.has_screen(look)
    size = max(width, height, 0.3 * r)   # dot and sleepy eyes are small: the new shapes read at an oval's size

    def laughing(x: float) -> VMobject:
        radius = 0.5 * size
        return Arc(radius=radius, start_angle=PI * 0.15, angle=PI * 0.7, arc_center=[x, y - 0.55 * radius, 0]).set_stroke(c["features"], width=w * 1.2)

    def wide(x: float) -> VGroup:
        ring = Ellipse(width=1.05 * size, height=1.15 * size).move_to([x, y, 0])
        pupil = Circle(radius=0.11 * size).move_to([x, y, 0])
        if screen:
            return VGroup(ring.set_fill(opacity=0).set_stroke(c["features"], width=w), filled(pupil, c["features"]))
        return VGroup(outlined(ring, white, c["outline"], w * 0.75), filled(pupil, c["features"]))

    def swirl(x: float, turned: bool) -> VMobject:
        turns, radius = 2.25, 0.55 * size
        start = PI if turned else 0.0
        points = [(x + radius * (k / 40) * math.cos(start + 2 * PI * turns * k / 40), y + radius * (k / 40) * math.sin(start + 2 * PI * turns * k / 40)) for k in range(41)]
        return _curve(points).set_stroke(c["features"], width=w)

    return {
        "laughing": VGroup(*(laughing(x) for x in xs)),
        "wide": VGroup(*(wide(x) for x in xs)),
        "swirl": VGroup(*(swirl(x, False) for x in xs)),
        "swirl_turned": VGroup(*(swirl(x, True) for x in xs)),
    }


# ----- the mouth -----------------------------------------------------------------------------------


def mouth_shapes(mx: float, mouth_y: float, mouth_r: float, mr: float, front: bool, c: Mapping[str, str], w: float) -> dict[str, VMobject]:
    """The mouth's :data:`MOUTH_SHAPES` about (``mx``, ``mouth_y``), the generator's open-mouth
    centre, for a mouth radius ``mouth_r`` and a head radius ``mr`` (an animal's: its muzzle's)."""
    ink = c["features"]
    top = mouth_y + 0.1 * mr
    half, depth = 0.85 * mouth_r, 0.42 * mr
    bowl = [(mx + half * math.cos(a), top - depth * math.sin(a)) for a in np.linspace(0, PI, 17)]
    laugh = VGroup(
        filled(polygon([(mx - half, top), *reversed(bowl[1:-1]), (mx + half, top)]), ink),
        filled(Ellipse(width=0.95 * mouth_r, height=0.16 * mr).move_to([mx, top - depth + 0.09 * mr, 0]), TONGUE_COLOR),
    )
    forward = 0.0 if front else 0.2 * mouth_r   # from the side the tongue comes out in front
    lip_y = mouth_y + 0.05 * mr
    tongue_body = Ellipse(width=0.95 * mouth_r, height=0.46 * mr).move_to([mx + forward, lip_y - 0.17 * mr, 0])
    tongue = VGroup(
        outlined(tongue_body, TONGUE_COLOR, ink, w * 0.75),
        Line([mx + forward, lip_y - 0.03 * mr, 0], [mx + forward, lip_y - 0.24 * mr, 0]).set_stroke(ink, width=w * 0.5),
        Line([mx - 0.85 * mouth_r, lip_y, 0], [mx + 0.85 * mouth_r, lip_y, 0]).set_stroke(ink, width=w),
    )
    wave = [(mx - 0.8 * mouth_r + 1.6 * mouth_r * k / 24, lip_y + 0.05 * mr * math.sin(2 * PI * 2 * k / 24)) for k in range(25)]
    return {"laugh": laugh, "tongue": tongue, "wavy": _curve(wave).set_stroke(ink, width=w)}


# ----- the cheeks ----------------------------------------------------------------------------------


def cheeks_part(look: CharacterLook, f: Frame, xs: Sequence[float], eye_bottom: float, c: Mapping[str, str], w: float) -> CharacterPart:
    """The ``cheeks`` part (:data:`CHEEK_SHAPES`) under the eyes at ``xs`` (their lowest point
    ``eye_bottom``), hanging from the head; ``c`` the face's colours."""
    r = f.p.head_radius
    cheek_y = min(f.eye_y - 0.3 * r, f.head_y - 0.1 * r)
    screen = robots.has_screen(look)

    def blush(x: float) -> VMobject:
        if screen:   # three short glowing strokes
            return VGroup(*(Line([x + dx - 0.04 * r, cheek_y - 0.05 * r, 0], [x + dx + 0.04 * r, cheek_y + 0.05 * r, 0]).set_stroke(BLUSH_COLOR, width=w)
                            for dx in (-0.1 * r, 0.0, 0.1 * r)))
        return Ellipse(width=0.42 * r, height=0.22 * r).move_to([x, cheek_y, 0]).set_fill(BLUSH_COLOR, opacity=BLUSH_OPACITY).set_stroke(width=0)

    bottom = f.head_y - 0.72 * r

    def tears(x: float, running: bool) -> VGroup:
        start = eye_bottom - 0.02 * r
        stream = polygon(tapered_band([(x, start), (x, (start + bottom) / 2), (x, bottom)], 0.09 * r, 0.14 * r))
        drops = [bottom - (0.2 if running else 0.08) * r]
        if running:
            drops.append((start + bottom) / 2 - 0.04 * r)
        pieces = [stream, *(Circle(radius=0.065 * r).move_to([x, d, 0]) for d in drops)]
        return VGroup(*(piece.set_fill(TEAR_COLOR, opacity=0.9).set_stroke(TEAR_EDGE, width=w * 0.5) for piece in pieces))

    shapes = {
        "none": nothing(f.face_x, cheek_y),
        "blush": VGroup(*(blush(x) for x in xs)),
        "tears": VGroup(*(tears(x, False) for x in xs)),
        "tears_running": VGroup(*(tears(x, True) for x in xs)),
    }
    return CharacterPart("cheeks", shapes, (f.face_x, cheek_y))


# ----- hair standing up ----------------------------------------------------------------------------


def _fright_lines(cx: float, cy: float, top: float, r: float, ink: str, w: float) -> VGroup:
    """Four short strokes standing out over a head whose top is ``top`` above (cx, cy)."""
    lines = []
    for degrees in (52.0, 76.0, 104.0, 128.0):
        inner, outer = point_at(cx, cy, top + 0.12 * r, degrees), point_at(cx, cy, top + 0.42 * r, degrees)
        lines.append(Line([*inner, 0], [*outer, 0]).set_stroke(ink, width=w))
    return VGroup(*lines)


def _spikes(cx: float, cy: float, rx: float, ry: float, inner: float, outer: float, count: int, start: float, end: float) -> VMobject:
    """A zigzag crown of ``count`` spikes from ``start`` to ``end`` degrees round (cx, cy) on an
    ellipse of radii ``rx``, ``ry``: the valleys at ``inner``, the tips at ``outer`` (shares of it)."""
    points = []
    steps = 2 * count
    for k in range(steps + 1):
        a = math.radians(start + (end - start) * k / steps)
        share = outer if k % 2 else inner
        points.append((cx + rx * share * math.cos(a), cy + ry * share * math.sin(a)))
    points.append((cx, cy))
    return polygon(points)


def bristles_part(look: CharacterLook, f: Frame, head_top: float, c: Mapping[str, str], w: float) -> CharacterPart:
    """The ``bristles`` part (:data:`BRISTLE_SHAPES`) behind the head, pivoting at its centre;
    ``head_top`` is how far the head part's drawing (hair, ears, eye bulges) reaches above it."""
    r, cx, cy, ink = f.p.head_radius, f.head_x, f.head_y, c["outline"]
    species = look.species
    up: VMobject
    if species in FURRY:
        sx, sy = animals.HEAD_SHAPES[species]
        up = outlined(_spikes(cx, cy, sx * r, sy * r, 0.8, 1.32, 7, 25.0, 155.0), c["skin"], ink, w)
    elif species in animals.BEAKED:
        shade = animals.fur_shade(c["skin"])
        feathers = []
        for degrees in (66.0, 80.0, 94.0, 108.0, 122.0):
            base = point_at(cx, cy, 0.85 * r, degrees)
            feathers.append(outlined(polygon(tapered_band([base, point_at(cx, cy, 1.5 * r, degrees)], 0.15 * r, 0.05 * r)), shade, ink, w))
        up = VGroup(*feathers)
    elif species == "human" and look.hair != "none":
        reach = max(head_top + 0.3 * r, 1.35 * r) / r
        up = outlined(_spikes(cx, cy, r, r, 0.8, reach, 7, 20.0, 160.0), c["hair"], ink, w)
    else:   # nothing to stand up: fright lines
        up = _fright_lines(cx, cy, head_top, r, ink, w)
    return CharacterPart("bristles", {"none": nothing(cx, cy), "up": VGroup(up)}, (cx, cy))


__all__ = [
    "BLUSH_COLOR",
    "BLUSH_OPACITY",
    "BRISTLE_SHAPES",
    "CHEEK_SHAPES",
    "EYE_SHAPES",
    "FURRY",
    "MOUTH_SHAPES",
    "TEAR_COLOR",
    "TEAR_EDGE",
    "TONGUE_COLOR",
    "bristles_part",
    "cheeks_part",
    "eye_shapes",
    "mouth_shapes",
    "nothing",
]
