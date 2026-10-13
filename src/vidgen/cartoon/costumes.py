"""Costume pieces of the generator (DESIGN.md §69.58): the accessories ``crown``, ``wizard_hat``,
``party_hat`` (worn on top of the head, in the ``accessory`` part, like a hat) and ``cape`` (its
own ``cape`` part hanging from the shoulders behind the body, with a clasp on the body).

Each is a generic piece built from polygons, circles and ellipses in the look's colours: the
piece in ``colors.accessory``, its trimmings (gems, a band, stars, stripes, a pompom) in
``colors.clothes``. A wizard hat, a party hat and the cape trail in the wind; the cape also
swings on the follow-through spring and flutters with each step
(:func:`~vidgen.cartoon.motion.follow_angles`, :func:`~vidgen.cartoon.transition.walking_state`).
Character units before the figure is scaled to height 1, as in :mod:`vidgen.cartoon.generator`,
which calls these; facing right.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from manim import Circle, Ellipse, Line, VGroup, VMobject

from vidgen.cartoon.animals import fur_shade
from vidgen.cartoon.character import CharacterPart
from vidgen.cartoon.keyframes import path_curve
from vidgen.cartoon.primitives import Point, clip_to_box, outlined, point_at, polygon, tapered_band, trailing
from vidgen.config import CharacterLook

if TYPE_CHECKING:
    from vidgen.cartoon.generator import Frame

#: Where a hat-like piece sits: its base this many head radii above the head's centre (the hat's brim's).
BASE_RISE = 0.72
#: The cape's hem: this share of the legs' length above the ground (about the knees).
CAPE_HEM = 0.45


def _star(x: float, y: float, radius: float) -> VMobject:
    """A five-pointed star about (``x``, ``y``), a point up."""
    return polygon([point_at(x, y, radius * (1.0 if k % 2 == 0 else 0.45), 90.0 + 36.0 * k) for k in range(10)])


def _turned(points: Sequence[Point], about: Point, degrees: float) -> list[Point]:
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [(about[0] + (x - about[0]) * cos - (y - about[1]) * sin, about[1] + (x - about[0]) * sin + (y - about[1]) * cos) for x, y in points]


def crown(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A crown: a band with points (balls on their tips) and three gems (from the side four
    points, set back a little)."""
    r = f.p.head_radius
    cx = f.head_x if f.front else f.head_x - 0.05 * r
    base, valley, tip = f.head_y + BASE_RISE * r, f.head_y + (BASE_RISE + 0.36) * r, f.head_y + (BASE_RISE + 0.72) * r
    half = 0.76 * r
    count = 5 if f.front else 4
    tips = [cx - half + 2 * half * k / (count - 1) for k in range(count)]
    outline: list[Point] = [(cx - half, base), (cx + half, base)]
    for k in range(count - 1, -1, -1):
        outline.append((tips[k], tip))
        if k:
            outline.append(((tips[k] + tips[k - 1]) / 2, valley))
    accessory, ink = c["accessory"], c["outline"]
    pieces = [outlined(polygon(outline), accessory, ink, w)]
    pieces += [outlined(Circle(radius=0.07 * r).move_to([x, tip, 0]), accessory, ink, w * 0.6) for x in tips]
    gems = (-0.45, 0.0, 0.45) if f.front else (-0.35, 0.25)
    pieces += [outlined(Circle(radius=0.08 * r).move_to([cx + g * r, base + 0.16 * r, 0]), c["clothes"], ink, w * 0.5) for g in gems]
    return pieces


def wizard_hat(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A wizard's hat: a wide brim, a tall cone whose tip bends back (from the front: to one
    side), a band and two stars; it trails in the wind."""
    r, cx = f.p.head_radius, f.head_x
    brim_y = f.head_y + BASE_RISE * r
    bend = 1.0 if f.front else -1.0
    line = [(cx, brim_y + 0.05 * r), (cx + bend * 0.02 * r, brim_y + 0.7 * r), (cx + bend * 0.18 * r, brim_y + 1.25 * r), (cx + bend * 0.52 * r, brim_y + 1.62 * r)]
    cone = polygon(tapered_band(path_curve(line, samples=4), 1.36 * r, 0.09 * r))
    band = polygon([(cx - 0.67 * r, brim_y + 0.06 * r), (cx + 0.67 * r, brim_y + 0.06 * r), (cx + 0.6 * r, brim_y + 0.3 * r), (cx - 0.6 * r, brim_y + 0.3 * r)])
    brim = Ellipse(width=2.5 * r, height=0.3 * r).move_to([cx, brim_y, 0])
    accessory, trim, ink = c["accessory"], c["clothes"], c["outline"]
    stars = [_star(cx - 0.12 * r * bend, brim_y + 0.62 * r, 0.15 * r), _star(cx + 0.12 * r * bend, brim_y + 1.0 * r, 0.1 * r)]
    pieces = [outlined(cone, accessory, ink, w), outlined(band, trim, ink, w), *(outlined(s, trim, ink, w * 0.5) for s in stars),
              outlined(brim, accessory, ink, w)]
    return [trailing(piece, (cx, brim_y), "wizard_hat") for piece in pieces]


def party_hat(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A party hat: a narrow cone at a slant (forward; from the front to one side) with two
    stripes and a pompom; it trails in the wind."""
    r = f.p.head_radius
    cx, base = (f.head_x + 0.1 * r if f.front else f.head_x + 0.05 * r), f.head_y + (BASE_RISE + 0.12) * r
    height, half = 1.3 * r, 0.42 * r
    cone = [(cx - half, base), (cx + half, base), (cx, base + height)]
    tilt = -12.0
    stripes = [clip_to_box(cone, bottom=base + a * height, top=base + b * height) for a, b in ((0.18, 0.32), (0.5, 0.62))]
    accessory, trim, ink = c["accessory"], c["clothes"], c["outline"]
    pieces = [outlined(polygon(_turned(cone, (cx, base), tilt)), accessory, ink, w)]
    pieces += [outlined(polygon(_turned(s, (cx, base), tilt)), trim, ink, w * 0.5) for s in stripes if s]
    tip = _turned([(cx, base + height)], (cx, base), tilt)[0]
    pieces.append(outlined(Circle(radius=0.15 * r).move_to([tip[0], tip[1], 0]), trim, ink, w * 0.75))
    return [trailing(piece, (cx, base), "party_hat") for piece in pieces]


def cape_part(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> CharacterPart | None:
    """The ``cape`` part (``None`` without the ``cape`` accessory): from the shoulders down to
    about the knees behind the body, its hem waving; from the side its back flares out behind,
    from the front its inside (a darker tone) shows beside the body. It pivots at the neck and
    trails in the wind."""
    if "cape" not in look.accessories:
        return None
    p = f.p
    top, hem = f.body_top - 0.01, CAPE_HEM * p.leg_length
    bw = p.body_width
    if f.front:
        pivot = (0.0, f.body_top - 0.02)
        left, right = -0.6 * bw, 0.6 * bw
        wave = [(left + (right - left) * k / 10, hem - 0.012 * math.sin(math.pi * k / 2.5)) for k in range(11)]
        outline = [(-0.36 * bw, top), *wave, (0.36 * bw, top)]
        color = fur_shade(c["accessory"])
    else:
        pivot = (-0.15 * bw, f.body_top - 0.02)
        back, front = -0.72 * bw, 0.02 * bw
        wave = [(front + (back - front) * k / 8, hem - 0.014 * math.sin(math.pi * k / 2.0)) for k in range(9)]
        outline = [(0.12 * bw, top), (front + 0.02, f.body_bottom), *wave, (-0.56 * bw, f.body_bottom + 0.35 * p.body_height), (-0.4 * bw, top - 0.04)]
        color = c["accessory"]
    cape = trailing(outlined(polygon(outline), color, c["outline"], w), pivot, "cape")
    return CharacterPart("cape", {"default": VGroup(cape)}, pivot)


def cape_clasp(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """The cape's ties over the shoulders and its round clasp at the throat, for the ``body`` part."""
    p, y = f.p, f.body_top - 0.045
    accessory, ink = c["accessory"], c["outline"]
    if f.front:
        ties = [Line([side * 0.34 * p.body_width, f.body_top - 0.01, 0], [side * 0.03, y, 0]) for side in (-1.0, 1.0)]
        clasp_x = 0.0
    else:
        clasp_x = 0.22 * p.body_width
        ties = [Line([-0.32 * p.body_width, f.body_top - 0.02, 0], [clasp_x, y, 0])]
    return [*(tie.set_stroke(accessory, width=w * 2.0) for tie in ties), outlined(Circle(radius=0.022).move_to([clasp_x, y, 0]), c["clothes"], ink, w * 0.6)]


#: Drawing of each costume piece worn on top of the head, by accessory name.
HEADWEAR_DRAWINGS = {"crown": crown, "wizard_hat": wizard_hat, "party_hat": party_hat}


__all__ = ["BASE_RISE", "CAPE_HEM", "HEADWEAR_DRAWINGS", "cape_clasp", "cape_part", "crown", "party_hat", "wizard_hat"]
