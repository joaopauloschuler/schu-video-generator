"""NSGC pedigree symbols for the ``pedigree`` scene (DESIGN.md §96.8; Bennett et al. 2008): male
square, female circle, sex unknown a diamond; affected filled; a carrier a dot in the centre (or,
with ``carrier_style: half``, the textbook heterozygote's half-shaded symbol); deceased a diagonal
line through the symbol; adoption square brackets; a miscarriage a small triangle; a proposed
child dashed with a question mark; the proband's arrow with P, the consultand's without.
Original flat drawings."""

from typing import Any

import numpy as np

from vidgen.api import *


def outline(sex: str, s: float) -> VMobject:
    """The symbol's outline, ``s`` wide, centred on the origin."""
    if sex == "male":
        return Square(side_length=s)
    if sex == "female":
        return Circle(radius=s / 2)
    d = s * 0.62
    return Polygon(np.array([0, d, 0]), np.array([d, 0, 0]), np.array([0, -d, 0]), np.array([-d, 0, 0]))


def left_half(sex: str, s: float) -> VMobject:
    """The left half of the symbol (the half-shaded heterozygote)."""
    if sex == "male":
        return Rectangle(width=s / 2, height=s).move_to(np.array([-s / 4, 0, 0]))
    if sex == "female":
        return Sector(radius=s / 2, angle=PI, start_angle=PI / 2)
    d = s * 0.62
    return Polygon(np.array([0, d, 0]), np.array([0, -d, 0]), np.array([-d, 0, 0]))


def triangle(s: float) -> VMobject:
    """A pregnancy loss (spontaneous abortion): a small triangle, apex up."""
    h = s * 0.55
    return Polygon(np.array([0, h / 2, 0]), np.array([h * 0.6, -h / 2, 0]), np.array([-h * 0.6, -h / 2, 0]))


def symbol(scene: Any, person: Any, s: float, ink: Any, bg: Any, fill: Any, carrier_style: str, stroke: float) -> VGroup:
    """One person's symbol with its marks (affected fill, carrier, deceased, adoption, proposed),
    centred on the origin. The first submobject is the outline (what a highlight box surrounds)."""
    if person.loss == "miscarriage":
        shape = triangle(s)
    else:
        shape = outline(person.sex, s)
    shape.set_stroke(ink, width=stroke).set_fill(fill if person.affected else bg, opacity=1.0)
    parts: list[Mobject] = [shape]
    if person.proposed:
        dashed = DashedVMobject(shape.copy().set_fill(opacity=0), num_dashes=14).set_stroke(ink, width=stroke)
        shape.set_stroke(opacity=0).set_fill(bg, opacity=1.0)
        q = scene.markup("<b>?</b>", size=s * 48 * 0.55, color=ink)
        parts += [dashed, q]
    if person.carrier:
        parts.append(carrier_mark(person.sex, s, fill, carrier_style))
    if person.deceased or person.loss == "stillbirth":
        r = s * 0.7
        parts.append(Line(np.array([-r, -r, 0]), np.array([r, r, 0])).set_stroke(ink, width=stroke))
    if person.adopted is not None:
        h, w, t = s * 0.72, s * 0.78, s * 0.14
        for side in (-1, 1):
            x = side * w
            parts.append(VMobject().set_points_as_corners([np.array([x - side * t, h, 0]), np.array([x, h, 0]), np.array([x, -h, 0]),
                                                           np.array([x - side * t, -h, 0])]).set_stroke(ink, width=stroke * 0.8))
    return VGroup(*parts)


def carrier_mark(sex: str, s: float, fill: Any, style: str) -> VMobject:
    """A carrier: a dot in the centre (NSGC), or the left half shaded (textbook heterozygote)."""
    if style == "half":
        return left_half(sex, s).set_stroke(width=0).set_fill(fill, opacity=1.0)
    return Dot(radius=s * 0.13, color=fill)


def arrow(scene: Any, s: float, ink: Any, letter: str, stroke: float, letter_size: float = 20.0) -> VGroup:
    """The proband's (with P) or the consultand's arrow, from the lower left to the symbol."""
    tip = np.array([-s * 0.5, -s * 0.5, 0])
    tail = tip + np.array([-s * 0.8, -s * 0.38, 0])
    a = Arrow(tail, tip, buff=0, stroke_width=stroke, max_tip_length_to_length_ratio=0.45, tip_length=s * 0.22).set_color(ink)
    parts: list[Mobject] = [a]
    if letter:
        p = scene.markup(f"<b>{letter}</b>", size=letter_size, color=ink)
        p.next_to(tail, LEFT, buff=s * 0.04)
        parts.append(p)
    return VGroup(*parts)


def mating_line(a: np.ndarray, b: np.ndarray, ink: Any, stroke: float, double: bool, separated: bool, s: float) -> VGroup:
    """The line between partners: double for consanguinity, two short slashes across it for a
    separation or divorce."""
    parts: list[Mobject] = []
    if double:
        off = np.array([0, s * 0.07, 0])
        parts += [Line(a + off, b + off), Line(a - off, b - off)]
    else:
        parts.append(Line(a, b))
    if separated:
        mid = (a + b) / 2
        for dx in (-s * 0.08, s * 0.08):
            c = mid + np.array([dx, 0, 0])
            parts.append(Line(c + np.array([-s * 0.08, -s * 0.16, 0]), c + np.array([s * 0.08, s * 0.16, 0])))
    return VGroup(*parts).set_stroke(ink, width=stroke)


def tick(size: float, color: Any, ok: bool) -> VGroup:
    """A check mark (fits) or a cross (excluded), drawn (no font glyph needed)."""
    if ok:
        pts = [np.array([-0.5, 0.0, 0]), np.array([-0.15, -0.38, 0]), np.array([0.5, 0.42, 0])]
        return VGroup(VMobject().set_points_as_corners([p * size for p in pts]).set_stroke(color, width=4))
    return VGroup(Line(np.array([-0.4, -0.4, 0]) * size, np.array([0.4, 0.4, 0]) * size),
                  Line(np.array([-0.4, 0.4, 0]) * size, np.array([0.4, -0.4, 0]) * size)).set_stroke(color, width=4)
