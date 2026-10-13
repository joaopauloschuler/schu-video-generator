"""Original animal characters of the generator (DESIGN.md §69.48, §69.57): ``look.species``
``cat``, ``dog``, ``bird``, ``bear``, ``rabbit``, ``mouse`` and (Step 123) ``fox``, ``owl``,
``frog``, ``turtle``, ``penguin``.

A species changes the head (its shape, ears, a crest or tufts, a muzzle, snout or beak, a nose and
whiskers, a frog's eye bulges, an owl's face discs, a penguin's face patch), the hands (round paws,
a bird's or owl's wings, a penguin's flippers), the shins and feet (a bird's or owl's thin shins
with toes, a frog's or penguin's flat feet), some proportions (:data:`SPECIES_PROPORTIONS`), where
the mouth sits (on the muzzle, under the snout; birds, owls and penguins talk with their beaks),
adds a ``tail`` part behind the body (not a frog) and a turtle's shell on its back. Everything else
(bodies, outfits, hair, accessories, poses, lip sync) is the human generator's. Each design is a
plain generic animal built from circles, ellipses and polygons in the look's own colours (fur,
feathers or skin: ``colors.skin``; a turtle's shell: ``colors.hair``; a muzzle, inner ear or
rabbit's tail a tint of it; noses, beaks and a mouse's tail a fixed natural colour), with no
feature taken from any known character. Character units before the figure is scaled to height 1,
as in :mod:`vidgen.cartoon.generator`, which calls these; facing right, the face looks right.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
from manim import BLACK, WHITE, Arc, Circle, Ellipse, Line, ManimColor, RoundedRectangle, VGroup, VMobject, interpolate_color

from vidgen.cartoon.character import CharacterPart
from vidgen.cartoon.keyframes import path_curve
from vidgen.cartoon.primitives import Point, filled, outer_hair, outlined, point_at, polygon, tapered_band, trailing
from vidgen.config import CharacterLook
from vidgen.lint.color import hex_rgb, relative_luminance

if TYPE_CHECKING:
    from vidgen.cartoon.generator import Frame

#: Fixed natural colours: a beak and a bird's legs; a pink nose, inner ear and mouse's tail.
BEAK_COLOR = "#E2A33C"
PINK = "#E39AA2"
#: The head's (width, height) as a share of the round human head's.
HEAD_SHAPES: dict[str, tuple[float, float]] = {
    "cat": (1.08, 0.95), "dog": (1.0, 0.98), "bird": (1.0, 1.0), "bear": (1.06, 1.0), "rabbit": (0.95, 1.04), "mouse": (0.98, 0.96),
    "fox": (1.0, 0.92), "owl": (1.06, 1.0), "frog": (1.32, 0.8), "turtle": (0.95, 0.86), "penguin": (0.98, 0.98),
}
#: Factors on the proportions (:class:`~vidgen.cartoon.generator.Proportions` fields) of the
#: species that differ from a person's build: a frog's long legs and wide mouth, an owl's big eyes
#: set apart, a penguin's short legs and flippers, a turtle's short legs and small head.
SPECIES_PROPORTIONS: dict[str, dict[str, float]] = {
    "frog": {"leg_length": 1.3, "mouth_width": 2.2},
    "owl": {"eye_size": 1.4, "eye_gap": 1.2},
    "penguin": {"leg_length": 0.6, "arm_length": 0.85, "body_width": 1.08},
    "turtle": {"leg_length": 0.85, "head_radius": 0.92},
}
#: Species that talk with a beak (:func:`beak_mouth`), and those whose arms are wings.
BEAKED: frozenset[str] = frozenset({"bird", "owl", "penguin"})
WINGED: frozenset[str] = frozenset({"bird", "owl"})
#: Each beak: from the side (hinge x and y from the head's centre, half height, length) and from
#: the front (the seam's y, half height, half width), in head radii.
BEAKS: dict[str, tuple[tuple[float, float, float, float], tuple[float, float, float]]] = {
    "bird": ((0.8, -0.14, 0.21, 0.78), (-0.16, 0.2, 0.26)),
    "owl": ((0.5, -0.3, 0.13, 0.42), (-0.3, 0.17, 0.13)),
    "penguin": ((0.8, -0.12, 0.15, 0.72), (-0.14, 0.15, 0.2)),
}
#: Where a frog's eyes sit: this many head radii above the head's centre, in skin-coloured bulges.
FROG_EYE_RISE = 0.6
#: The gap between the top of an eye and its brow (head radii) where it is not a person's 0.16:
#: a frog's brows sit on its eye bulges.
BROW_GAPS: dict[str, float] = {"frog": 0.06}
#: A mouse's snout from the side: how much farther than the head it reaches, its direction
#: (radians from forward, + up) and how wide it starts (a spread of angles, radians squared).
MOUSE_SNOUT = (0.55, -0.22, 0.12)
#: Where the mouth goes, side view: (x, y) of its reference point in head radii from the head's
#: centre (the human mouth's is the head's centre: its smile hangs 0.2 below it) and its size.
MOUTH_PLACES: dict[str, tuple[float, float, float]] = {
    "cat": (0.33, -0.16, 0.55), "rabbit": (0.3, -0.16, 0.5), "bear": (0.33, -0.18, 0.6),
    "dog": (0.72, -0.21, 0.6), "mouse": (0.72, -0.3, 0.45),
    "fox": (0.85, -0.2, 0.5), "frog": (0.32, 0.15, 0.9), "turtle": (0.42, -0.2, 0.6),
}
#: The same from the front (x is 0).
FRONT_MOUTH_PLACES: dict[str, tuple[float, float]] = {
    "cat": (-0.16, 0.55), "rabbit": (-0.16, 0.5), "bear": (-0.18, 0.6), "dog": (-0.21, 0.6), "mouse": (-0.24, 0.45),
    "fox": (-0.26, 0.5), "frog": (0.15, 0.9), "turtle": (-0.22, 0.6),
}
#: How far a bird's beak opens for each mouth shape (degrees, side view): ``open`` for a
#: surprised face, the visemes of DESIGN.md §69.4; ``M`` is closed.
BEAK_OPENINGS: dict[str, float] = {"open": 40.0, "A": 34.0, "E": 16.0, "O": 26.0, "U": 14.0, "F": 6.0, "L": 22.0, "W": 12.0}
#: Tails from the side: the centre line (from the root, character units) and its width at the
#: root and at the tip; ``None``: a round tail (bear, rabbit) or a bird's fan.
TAIL_LINES: dict[str, tuple[tuple[Point, ...], float, float]] = {
    "cat": (((0.0, 0.0), (-0.09, -0.02), (-0.18, 0.0), (-0.25, 0.07), (-0.28, 0.16), (-0.26, 0.25), (-0.21, 0.3)), 0.05, 0.032),
    "dog": (((0.0, 0.0), (-0.07, 0.02), (-0.13, 0.07), (-0.16, 0.14), (-0.16, 0.2)), 0.06, 0.03),
    "mouse": (((0.0, 0.0), (-0.1, -0.04), (-0.2, -0.06), (-0.29, -0.03), (-0.34, 0.04), (-0.35, 0.11)), 0.03, 0.012),
    "turtle": (((0.0, 0.0), (-0.05, -0.02), (-0.1, -0.025)), 0.045, 0.012),   # short, from under the shell
}
#: A bird's tail feathers: directions (degrees, side view), length and widths.
TAIL_FEATHERS = ((200.0, 215.0, 230.0), 0.24, 0.07, 0.04)
#: A fox's bushy tail from the side: its centre line, its widest (character units) and the share
#: of its length that is a light tip.
FOX_TAIL = (((0.0, 0.0), (-0.08, -0.02), (-0.17, 0.0), (-0.24, 0.06), (-0.28, 0.15), (-0.27, 0.24)), 0.13, 0.3)


def is_animal(look: CharacterLook) -> bool:
    """Whether ``look`` is an animal (``species`` other than ``human`` and ``robot``)."""
    return look.species not in ("human", "robot")


def _mix(color: str, other: str, share: float) -> str:
    return interpolate_color(ManimColor(color), ManimColor(other), share).to_hex()


def fur_tint(color: str) -> str:
    """A muzzle's or a belly's colour on fur of ``color``: lighter, or (on light fur) a little darker."""
    hexed = ManimColor(color).to_hex()
    light = relative_luminance(hex_rgb(hexed)) > 0.55
    return _mix(hexed, BLACK if light else WHITE, 0.14 if light else 0.5)


def fur_shade(color: str) -> str:
    """A darker tone of ``color`` (a dog's ears, a bird's crest and wing tips)."""
    return _mix(color, BLACK, 0.28)


def patch_tint(color: str) -> str:
    """A penguin's face patch or a fox's tail tip on fur of ``color``: nearly white, or (on very
    light fur) a clearly darker tone."""
    hexed = ManimColor(color).to_hex()
    light = relative_luminance(hex_rgb(hexed)) > 0.7
    return _mix(hexed, BLACK if light else WHITE, 0.3 if light else 0.85)


def proportion_factors(look: CharacterLook) -> dict[str, float]:
    """The factors :data:`SPECIES_PROPORTIONS` gives ``look``'s species (none: no change)."""
    return SPECIES_PROPORTIONS.get(look.species, {})


def species_frame(look: CharacterLook, f: Frame) -> Frame:
    """``f``, or for a frog the same with its flat head lowered onto its shoulders and the eyes
    high in its bulges (:data:`FROG_EYE_RISE`)."""
    if look.species != "frog":
        return f
    r = f.p.head_radius
    head_y = f.head_y - (1.0 - HEAD_SHAPES["frog"][1]) * r
    return replace(f, head_y=head_y, eye_y=head_y + FROG_EYE_RISE * r)


def head_shape(look: CharacterLook, f: Frame) -> VMobject:
    """The animal's head: an ellipse about the human head's circle; a mouse's, from the side,
    drawn out in front into a pointed snout (:data:`MOUSE_SNOUT`)."""
    sx, sy = HEAD_SHAPES[look.species]
    r = f.p.head_radius
    if look.species != "mouse" or f.front:
        return Ellipse(width=2 * r * sx, height=2 * r * sy).move_to([f.head_x, f.head_y, 0])
    reach, direction, spread = MOUSE_SNOUT
    points = []
    for k in range(48):
        t = 2 * math.pi * k / 48
        offset = math.atan2(math.sin(t - direction), math.cos(t - direction))
        stretch = 1.0 + reach * math.exp(-(offset**2) / spread)
        points.append((f.head_x + r * sx * stretch * math.cos(t), f.head_y + r * sy * stretch * math.sin(t)))
    return polygon(points)


def snout_tip(look: CharacterLook, f: Frame) -> Point:
    """The tip of a mouse's snout, from the side (where :func:`head_shape` reaches farthest)."""
    sx, sy = HEAD_SHAPES[look.species]
    reach, direction, _ = MOUSE_SNOUT
    r = f.p.head_radius
    return f.head_x + r * sx * (1 + reach) * math.cos(direction), f.head_y + r * sy * (1 + reach) * math.sin(direction)


def mouth_place(look: CharacterLook, f: Frame) -> tuple[float, float, float]:
    """``(x, y, size)``: where the mouth's reference point is (the human mouth's: the face's
    middle at the head's centre height) and the mouth's size (1 for a human)."""
    if not is_animal(look) or look.species in BEAKED:
        return f.face_x, f.head_y, 1.0
    r = f.p.head_radius
    if f.front:
        dy, size = FRONT_MOUTH_PLACES[look.species]
        return f.head_x, f.head_y + dy * r, size
    dx, dy, size = MOUTH_PLACES[look.species]
    return f.head_x + dx * r, f.head_y + dy * r, size


# ----- ears and crest (drawn behind the head) -------------------------------------------------------


def _ear_angles(front: bool, side: tuple[float, ...], from_front: tuple[float, ...]) -> tuple[float, ...]:
    """Where on the head's rim (degrees) the ears or crest go, from the side or the front."""
    return from_front if front else side


def ears(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """The ears (a bird: its crest), styled, marked as beyond the head (effect symbols go above
    them); a rabbit's long ears and a dog's hanging ears trail in the wind."""
    r, cx, cy, skin, ink = f.p.head_radius, f.head_x, f.head_y, c["skin"], c["outline"]
    inner = _mix(skin, PINK, 0.55)
    pieces: list[VMobject] = []
    species = look.species
    if species == "cat":
        for tip in _ear_angles(f.front, (58.0, 112.0), (52.0, 128.0)):
            outer = polygon([point_at(cx, cy, 0.8 * r, tip - 18), point_at(cx, cy, 1.42 * r, tip), point_at(cx, cy, 0.8 * r, tip + 18)])
            lining = polygon([point_at(cx, cy, 0.9 * r, tip - 10), point_at(cx, cy, 1.3 * r, tip), point_at(cx, cy, 0.9 * r, tip + 10)])
            pieces += [outlined(outer, skin, ink, w), outlined(lining, inner, ink, w * 0.5)]
    elif species == "rabbit":
        for base, lean in zip(_ear_angles(f.front, (82.0, 104.0), (66.0, 114.0)), (-14.0, 14.0) if f.front else (12.0, 24.0)):
            bx, by = point_at(cx, cy, 0.8 * r, base)
            tilt = math.radians(lean)
            middle = [bx - math.sin(tilt) * 0.72 * r, by + math.cos(tilt) * 0.72 * r, 0]
            ear = Ellipse(width=0.46 * r, height=1.55 * r).rotate(tilt).move_to(middle)
            lining = Ellipse(width=0.22 * r, height=1.15 * r).rotate(tilt).move_to(middle)
            pieces.append(trailing(VGroup(outlined(ear, skin, ink, w), outlined(lining, inner, ink, w * 0.5)), (bx, by), "long_ears"))
    elif species == "mouse":   # big oval ears set back on the sides of the head
        for angle in _ear_angles(f.front, (150.0, 118.0), (18.0, 162.0)):
            x, y = point_at(cx, cy, 0.88 * r, angle)
            tilt = math.radians(angle - 90)
            pieces += [outlined(Ellipse(width=0.84 * r, height=1.02 * r).rotate(tilt).move_to([x, y, 0]), skin, ink, w),
                       outlined(Ellipse(width=0.5 * r, height=0.66 * r).rotate(tilt).move_to([x, y, 0]), inner, ink, w * 0.5)]
    elif species == "bear":
        for angle in _ear_angles(f.front, (72.0, 116.0), (48.0, 132.0)):
            x, y = point_at(cx, cy, 0.9 * r, angle)
            pieces += [outlined(Circle(radius=0.3 * r).move_to([x, y, 0]), skin, ink, w),
                       outlined(Circle(radius=0.15 * r).move_to([x, y, 0]), fur_tint(skin), ink, w * 0.5)]
    elif species == "dog" and f.front:   # long ears hanging beside the head (from the side: :func:`face`)
        for side in (-1.0, 1.0):
            pieces.append(_dog_ear(cx + side * 0.78 * r, cy + 0.5 * r, side, 0.18, r, c, w))
    elif species == "bird":   # a crest of three feathers
        shade = fur_shade(skin)
        for angle in _ear_angles(f.front, (98.0, 114.0, 130.0), (72.0, 90.0, 108.0)):
            base = point_at(cx, cy, 0.86 * r, angle)
            tip = point_at(base[0], base[1], 0.5 * r, angle + (0.0 if f.front else 12.0))
            pieces.append(trailing(outlined(polygon(tapered_band([base, tip], 0.16 * r, 0.08 * r)), shade, ink, w), base, "pointy"))
    elif species == "fox":   # tall pointed ears with a light lining
        for tip in _ear_angles(f.front, (64.0, 102.0), (58.0, 122.0)):
            outer = polygon([point_at(cx, cy, 0.78 * r, tip - 17), point_at(cx, cy, 1.62 * r, tip), point_at(cx, cy, 0.78 * r, tip + 17)])
            lining = polygon([point_at(cx, cy, 0.9 * r, tip - 9), point_at(cx, cy, 1.42 * r, tip), point_at(cx, cy, 0.9 * r, tip + 9)])
            pieces += [outlined(outer, skin, ink, w), outlined(lining, fur_tint(skin), ink, w * 0.5)]
    elif species == "frog":   # the eye bulges rising above the top of the head (the eyes sit in them)
        pieces += [outlined(Circle(radius=0.34 * r * f.p.eye_size).move_to([x, f.eye_y, 0]), skin, ink, w)
                   for x in (f.face_x - f.p.eye_gap, f.face_x + f.p.eye_gap)]
    elif species == "owl":   # two tufts of two slim feathers each on top
        shade = fur_shade(skin)
        for angle, lean in zip(_ear_angles(f.front, (60.0, 106.0), (48.0, 132.0)), (-1.0, 1.0)):
            base = point_at(cx, cy, 0.86 * r, angle)
            for outward, length in ((4.0, 0.5), (22.0, 0.4)):   # leaning out, away from the middle
                tip = point_at(base[0], base[1], length * r, angle + lean * outward)
                pieces.append(trailing(outlined(polygon(tapered_band([base, tip], 0.17 * r, 0.04 * r)), shade, ink, w), base, "pointy"))
    return [outer_hair(piece) for piece in pieces]


def _dog_ear(x: float, top: float, side: float, tilt: float, r: float, c: Mapping[str, str], w: float) -> VMobject:
    """A dog's long ear hanging from (``x``, ``top``), its lower end out to ``side``, in a
    darker tone of the fur; it trails in the wind."""
    ear = Ellipse(width=0.46 * r, height=1.12 * r).rotate(side * tilt).move_to([x + side * 0.1 * r, top - 0.55 * r, 0])
    return trailing(outlined(ear, fur_shade(c["skin"]), c["outline"], w), (x, top), "floppy")


# ----- the face (drawn over the head) ----------------------------------------------------------------


def _whiskers(x: float, y: float, r: float, sides: Sequence[float], c: Mapping[str, str], w: float, length: float) -> list[VMobject]:
    lines = []
    for side in sides:
        for rise in (0.08, -0.08):
            start = [x + side * 0.12 * r, y, 0]
            end = [x + side * (0.12 + length) * r, y + rise * r + 0.03 * r, 0]
            lines.append(Line(start, end).set_stroke(c["features"], width=w * 0.6))
    return lines


def face(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """What the species draws on the face: a muzzle, a snout or a beak, a nose, whiskers."""
    r, cx, cy, skin, ink = f.p.head_radius, f.head_x, f.head_y, c["skin"], c["outline"]
    tint = fur_tint(skin)
    species = look.species
    mx = cx if f.front else cx + {"cat": 0.33, "rabbit": 0.3, "bear": 0.33}.get(species, 0.0) * r
    pieces: list[VMobject] = []
    if species in ("cat", "rabbit"):
        puff = (0.36, 0.28) if species == "cat" else (0.3, 0.24)
        for side in (-1.0, 1.0):
            pieces.append(outlined(Ellipse(width=puff[0] * r, height=puff[1] * r).move_to([mx + side * 0.13 * r, cy - 0.36 * r, 0]), tint, ink, w * 0.6))
        if species == "cat":   # a small nose, its point down
            nose = polygon([(mx - 0.09 * r, cy - 0.17 * r), (mx + 0.09 * r, cy - 0.17 * r), (mx, cy - 0.28 * r)])
        else:
            nose = Ellipse(width=0.15 * r, height=0.1 * r).move_to([mx, cy - 0.22 * r, 0])
        pieces.append(outlined(nose, PINK, ink, w * 0.6))
        pieces += _whiskers(mx, cy - 0.33 * r, r, (-1.0, 1.0) if f.front else (1.0,), c, w, 0.55 if species == "cat" else 0.4)
    elif species == "bear":
        pieces.append(outlined(Ellipse(width=0.78 * r, height=0.58 * r).move_to([mx, cy - 0.34 * r, 0]), tint, ink, w * 0.75))
        pieces.append(filled(Ellipse(width=0.26 * r, height=0.17 * r).move_to([mx + (0 if f.front else 0.06 * r), cy - 0.2 * r, 0]), c["features"]))
    elif species == "dog":
        if not f.front:   # the near ear, over the side of the head
            pieces.append(outer_hair(_dog_ear(cx - 0.42 * r, cy + 0.52 * r, -1.0, 0.2, r, c, w)))
        if f.front:
            snout, nose_at = Ellipse(width=0.8 * r, height=0.6 * r).move_to([cx, cy - 0.35 * r, 0]), (cx, cy - 0.17 * r)
        else:
            snout, nose_at = Ellipse(width=0.95 * r, height=0.62 * r).move_to([cx + 0.62 * r, cy - 0.3 * r, 0]), (cx + 1.0 * r, cy - 0.12 * r)
        pieces.append(outer_hair(outlined(snout, tint, ink, w)))
        pieces.append(outer_hair(outlined(Ellipse(width=0.3 * r, height=0.2 * r).move_to([*nose_at, 0]), c["features"], ink, w * 0.5)))
    elif species == "mouse":
        if f.front:
            pieces.append(outlined(Ellipse(width=0.55 * r, height=0.45 * r).move_to([cx, cy - 0.28 * r, 0]), tint, ink, w * 0.75))
            pieces.append(outlined(Circle(radius=0.09 * r).move_to([cx, cy - 0.17 * r, 0]), PINK, ink, w * 0.6))
            pieces += _whiskers(cx, cy - 0.27 * r, r, (-1.0, 1.0), c, w, 0.5)
        else:   # a round nose on the tip of the snout (the head's own shape)
            tip = snout_tip(look, f)
            pieces.append(outer_hair(outlined(Circle(radius=0.12 * r).move_to([tip[0], tip[1], 0]), PINK, ink, w * 0.6)))
            pieces += _whiskers(tip[0] - 0.4 * r, tip[1] - 0.02 * r, r, (1.0,), c, w, 0.5)
    elif species == "fox":
        pieces += _fox_face(f, c, w)
    elif species == "frog":
        pieces += _frog_face(f, c, w)
    elif species == "turtle":
        chin = Ellipse(width=1.0 * r, height=0.45 * r).move_to([cx, cy - 0.44 * r, 0]) if f.front else \
            Ellipse(width=0.85 * r, height=0.42 * r).move_to([cx + 0.38 * r, cy - 0.42 * r, 0])
        pieces.append(outlined(chin, tint, ink, w * 0.6))
        nostrils = [(cx - 0.1 * r, cy - 0.08 * r), (cx + 0.1 * r, cy - 0.08 * r)] if f.front else [(cx + 0.8 * r, cy + 0.0 * r)]
        pieces += [filled(Circle(radius=0.035 * r).move_to([x, y, 0]), c["features"]) for x, y in nostrils]
    if species == "owl":   # light discs round the eyes
        pieces += [outlined(Circle(radius=0.3 * r * f.p.eye_size).move_to([x, f.eye_y, 0]), tint, ink, w * 0.5)
                   for x in (f.face_x - f.p.eye_gap, f.face_x + f.p.eye_gap)]
    elif species == "penguin":   # a light patch over the eyes and cheeks
        patch = patch_tint(skin)
        if f.front:
            pieces += [filled(Circle(radius=0.36 * r).move_to([x, f.eye_y, 0]), patch) for x in (f.face_x - f.p.eye_gap, f.face_x + f.p.eye_gap)]
            pieces.append(filled(Ellipse(width=1.3 * r, height=0.75 * r).move_to([cx, cy - 0.32 * r, 0]), patch))
        else:
            pieces.append(filled(Ellipse(width=1.0 * r, height=1.15 * r).move_to([cx + 0.42 * r, cy - 0.12 * r, 0]), patch))
    if species in BEAKED:
        pieces += [outer_hair(piece) for piece in _closed_beak(species, f, c, w)]
    return pieces


def _fox_face(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A fox's light cheek ruffs and a long pointed snout with a dark nose at its tip (from the
    front: a light muzzle under a small dark nose)."""
    r, cx, cy, skin, ink = f.p.head_radius, f.head_x, f.head_y, c["skin"], c["outline"]
    tint = fur_tint(skin)

    def at(points: Sequence[Point]) -> VMobject:
        return polygon([(cx + x * r, cy + y * r) for x, y in points])

    if f.front:
        pieces: list[VMobject] = [
            outlined(at([(s * 0.15, -0.22), (s * 0.78, -0.24), (s * 1.1, -0.56), (s * 0.72, -0.6), (s * 0.55, -0.84), (s * 0.12, -0.74)]), tint, ink, w * 0.6)
            for s in (-1.0, 1.0)
        ]
        pieces.append(outlined(Ellipse(width=0.62 * r, height=0.5 * r).move_to([cx, cy - 0.42 * r, 0]), tint, ink, w * 0.6))
        pieces.append(outlined(Ellipse(width=0.22 * r, height=0.14 * r).move_to([cx, cy - 0.22 * r, 0]), c["features"], ink, w * 0.5))
        return pieces
    # the snout grows out of the head: filled over the head's outline, its ridge and underside drawn
    ridge = [(0.92, 0.36), (1.1, 0.1), (1.32, -0.12), (1.54, -0.26)]
    underside = [(1.52, -0.37), (1.2, -0.5), (0.85, -0.66), (0.53, -0.78)]
    snout = at([*ridge, *underside, (0.3, -0.4), (0.5, 0.1)])
    jaw = at([(0.5, -0.46), (1.0, -0.4), (1.5, -0.35), *underside, (0.4, -0.62)])
    nose = Ellipse(width=0.18 * r, height=0.14 * r).move_to([cx + 1.52 * r, cy - 0.31 * r, 0])
    edges = [VMobject().set_points_as_corners([[cx + x * r, cy + y * r, 0] for x, y in edge]).set_stroke(ink, width=w) for edge in (ridge, underside)]
    return [outer_hair(filled(snout, skin)), outer_hair(filled(jaw, tint)), *(outer_hair(edge) for edge in edges),
            outer_hair(outlined(nose, c["features"], ink, w * 0.5))]


def _frog_face(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A frog's nostrils (its eye bulges are drawn behind the head, :func:`ears`)."""
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    nostrils = [(cx - 0.14 * r, cy + 0.12 * r), (cx + 0.14 * r, cy + 0.12 * r)] if f.front else [(cx + 1.15 * r, cy + 0.12 * r)]
    return [filled(Circle(radius=0.035 * r).move_to([x, ny, 0]), c["features"]) for x, ny in nostrils]


# ----- a bird's beak --------------------------------------------------------------------------------


def _beak_frame(species: str, f: Frame) -> tuple[float, float, float, float]:
    """(hinge x, hinge y, half height, length) of the species' beak (:data:`BEAKS`; side view;
    from the front the middle of the seam, its y, the rhombus's half height and 0)."""
    r = f.p.head_radius
    (dx, dy, half, length), (front_dy, front_half, _) = BEAKS[species]
    if f.front:
        return f.head_x, f.head_y + front_dy * r, front_half * r, 0.0
    return f.head_x + dx * r, f.head_y + dy * r, half * r, length * r


def _beak_halves(species: str, f: Frame) -> tuple[list[Point], list[Point]]:
    """The upper and lower half of the closed beak, mirror images about the hinge's line."""
    x, y, h, length = _beak_frame(species, f)
    if f.front:
        width = BEAKS[species][1][2] * f.p.head_radius
        return [(x - width, y), (x + width, y), (x, y + h)], [(x - width, y), (x, y - h), (x + width, y)]
    return [(x, y + h), (x, y), (x + length, y)], [(x, y), (x, y - h), (x + length, y)]


def _closed_beak(species: str, f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    upper, lower = _beak_halves(species, f)
    return [outlined(polygon(lower), BEAK_COLOR, c["outline"], w), outlined(polygon(upper), BEAK_COLOR, c["outline"], w)]


def _turned(points: Sequence[Point], center: Point, degrees: float) -> list[Point]:
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [(center[0] + (x - center[0]) * cos - (y - center[1]) * sin, center[1] + (x - center[0]) * sin + (y - center[1]) * cos) for x, y in points]


def beak_mouth(species: str, f: Frame, c: Mapping[str, str], w: float) -> tuple[dict[str, VMobject], Point]:
    """The ``mouth`` shapes and pivot (the hinge) of a species that talks with its beak
    (:data:`BEAKED`): ``smile`` the line at the beak's corner; ``open`` and the visemes the beak
    open by :data:`BEAK_OPENINGS` (side view: both halves turned apart about the hinge over the
    dark inside; from the front a dark opening on the beak), ``M`` closed; the Step 125 shapes
    ``laugh``, ``tongue`` and ``wavy`` (:func:`_beak_expression_shapes`). Each shape is
    symmetric about the hinge's line, so an expression's flipped mouth (a frown) still shows an
    open beak the right way up."""
    x, y, h, length = _beak_frame(species, f)
    r, ink, inside = f.p.head_radius, c["outline"], c["features"]
    hinge = (x, y)
    # from the front, the openings scale with the beak (the bird's is the reference)
    across, up = BEAKS[species][1][2] / BEAKS["bird"][1][2], BEAKS[species][1][1] / BEAKS["bird"][1][1]
    if f.front:
        width = BEAKS[species][1][2] * r
        smile: VMobject = Arc(radius=0.12 * r * up, start_angle=math.radians(240), angle=math.radians(60), arc_center=[x, y + 0.08 * r * up, 0])
        closed: VMobject = Line([x - width, y, 0], [x + width, y, 0])
    else:
        smile = Arc(radius=0.13 * r, start_angle=math.radians(200), angle=math.radians(70), arc_center=[x, y + 0.13 * r, 0])
        closed = Line([x, y, 0], [x + 0.55 * length, y, 0])
    shapes: dict[str, VMobject] = {"smile": smile.set_stroke(inside, width=w)}
    upper, lower = _beak_halves(species, f)
    for name, degrees in BEAK_OPENINGS.items():
        if f.front:
            share = degrees / BEAK_OPENINGS["open"]
            wide = 0.42 if name == "E" else 0.22 if name in ("U", "W", "O") else 0.32
            shapes[name] = filled(Ellipse(width=wide * r * across, height=max(0.3 * share, 0.03) * r * up).move_to([x, y, 0]), inside)
            continue
        half = degrees / 2
        fan = [hinge, *(point_at(x, y, length, a) for a in np.linspace(-half, half, 7))]
        shapes[name] = VGroup(
            filled(polygon(fan), inside),
            outlined(polygon(_turned(upper, hinge, half)), BEAK_COLOR, ink, w),
            outlined(polygon(_turned(lower, hinge, -half)), BEAK_COLOR, ink, w),
        )
    shapes["M"] = closed.set_stroke(ink, width=w)
    shapes.update(_beak_expression_shapes(species, f, c, w))
    order = ["smile", "open", "A", "E", "O", "U", "M", "F", "L", "W", "laugh", "tongue", "wavy"]
    return {name: shapes[name] for name in order}, hinge


#: How far a beak opens laughing and with its tongue out (degrees, side view; DESIGN.md §69.59).
BEAK_LAUGH_OPENING = 46.0
BEAK_TONGUE_OPENING = 18.0


def _beak_expression_shapes(species: str, f: Frame, c: Mapping[str, str], w: float) -> dict[str, VMobject]:
    """A beak's Step 125 mouth shapes: ``laugh`` open wide with a pink tongue inside, ``tongue``
    a little open with the tongue poking out past its tip, ``wavy`` the closed seam wobbling."""
    x, y, h, length = _beak_frame(species, f)
    r, ink, inside = f.p.head_radius, c["outline"], c["features"]
    hinge = (x, y)
    across, up = BEAKS[species][1][2] / BEAKS["bird"][1][2], BEAKS[species][1][1] / BEAKS["bird"][1][1]
    if f.front:
        laugh = VGroup(filled(Ellipse(width=0.36 * r * across, height=0.38 * r * up).move_to([x, y, 0]), inside),
                       filled(Ellipse(width=0.22 * r * across, height=0.1 * r * up).move_to([x, y - 0.12 * r * up, 0]), PINK))
        tongue = VGroup(filled(Ellipse(width=0.24 * r * across, height=0.08 * r * up).move_to([x, y, 0]), inside),
                        outlined(Ellipse(width=0.16 * r * across, height=0.2 * r * up).move_to([x, y - 0.1 * r * up, 0]), PINK, ink, w * 0.6))
        half = BEAKS[species][1][2] * r
        seam = [(x - half + 2 * half * k / 16, y + 0.025 * r * math.sin(math.pi * k / 2)) for k in range(17)]
    else:
        upper, lower = _beak_halves(species, f)

        def opened(degrees: float, extra: list[VMobject]) -> VGroup:
            fan = [hinge, *(point_at(x, y, length, a) for a in np.linspace(-degrees / 2, degrees / 2, 7))]
            return VGroup(filled(polygon(fan), inside), *extra,
                          outlined(polygon(_turned(upper, hinge, degrees / 2)), BEAK_COLOR, ink, w),
                          outlined(polygon(_turned(lower, hinge, -degrees / 2)), BEAK_COLOR, ink, w))

        laugh = opened(BEAK_LAUGH_OPENING, [filled(Ellipse(width=0.5 * length, height=0.12 * r).move_to([x + 0.45 * length, y - 0.04 * r, 0]), PINK)])
        poking = Ellipse(width=0.42 * length, height=0.13 * r).move_to([x + 0.95 * length, y - 0.02 * r, 0])
        tongue = opened(BEAK_TONGUE_OPENING, [outlined(poking, PINK, ink, w * 0.6)])
        seam = [(x + 0.6 * length * k / 16, y + 0.03 * r * math.sin(math.pi * k / 2)) for k in range(17)]
    wavy = VMobject().set_points_smoothly([[px, py, 0.0] for px, py in seam]).set_fill(opacity=0).set_stroke(ink, width=w)
    return {"laugh": laugh, "tongue": tongue, "wavy": wavy}


# ----- hands, wings and a bird's feet ---------------------------------------------------------------


def paw(x: float, y: float, c: Mapping[str, str], w: float) -> VGroup:
    """A round paw at (``x``, ``y``) with two toe lines underneath."""
    pad = outlined(Circle(radius=0.05).move_to([x, y, 0]), c["skin"], c["outline"], w)
    toes = [Line([x + dx, y - 0.048, 0], [x + dx, y - 0.026, 0]).set_stroke(c["outline"], width=w * 0.6) for dx in (-0.016, 0.016)]
    return VGroup(pad, *toes)


def wing(x: float, top: float, elbow: float, wrist: float, c: Mapping[str, str], w: float) -> tuple[VGroup, VGroup]:
    """A bird's arm as a wing (upper, lower): a feathered upper segment from the shoulder (``x``,
    ``top``) to the elbow, then a tapering wing to three feather tips round the wrist (its end)."""
    width = 0.11
    upper = RoundedRectangle(width=width, height=top - elbow + width, corner_radius=width / 2).move_to([x, (top + elbow) / 2, 0])
    band = polygon(tapered_band([(x, elbow), (x, wrist + 0.02)], width, 0.07))
    tips = [polygon(tapered_band([(x, wrist + 0.02), point_at(x, wrist + 0.02, 0.085, angle)], 0.04, 0.022)) for angle in (-118.0, -90.0, -62.0)]
    shade = fur_shade(c["skin"])
    lower = VGroup(*(outlined(tip, shade, c["outline"], w) for tip in tips), outlined(band, c["skin"], c["outline"], w))
    return VGroup(outlined(upper, c["skin"], c["outline"], w)), lower


def flipper(x: float, top: float, elbow: float, wrist: float, c: Mapping[str, str], w: float) -> tuple[VGroup, VGroup]:
    """A penguin's arm as a flipper (upper, lower), whatever the sleeves: a smooth upper segment
    from the shoulder (``x``, ``top``) to the elbow, then a flat paddle narrowing to a round tip
    at the wrist (its end)."""
    width = 0.1
    upper = RoundedRectangle(width=width, height=top - elbow + width, corner_radius=width / 2).move_to([x, (top + elbow) / 2, 0])
    paddle = polygon(tapered_band([(x, elbow), (x, wrist - 0.01)], width, 0.05))
    return VGroup(outlined(upper, c["skin"], c["outline"], w)), VGroup(outlined(paddle, c["skin"], c["outline"], w))


def flat_foot(look: CharacterLook, x: float, front: bool, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A frog's or a penguin's flat foot on the ground under the shin at ``x`` (none with
    shoes): a penguin's in :data:`BEAK_COLOR`, a frog's in its skin with round toe pads."""
    if look.shoes != "none":
        return []
    color = BEAK_COLOR if look.species == "penguin" else c["skin"]
    if front:
        foot: VMobject = Ellipse(width=0.12, height=0.045).move_to([x, 0.0225, 0])
        tips = [(x + dx, 0.014) for dx in (-0.05, 0.0, 0.05)]
    else:
        foot = Ellipse(width=0.14, height=0.04).move_to([x + 0.035, 0.02, 0])
        tips = [(x + 0.1, 0.014), (x + 0.075, 0.03)]
    pieces = [outlined(foot, color, c["outline"], w * 0.75)]
    if look.species == "frog":
        pieces += [outlined(Circle(radius=0.014).move_to([tx, ty, 0]), color, c["outline"], w * 0.6) for tx, ty in tips]
    return pieces


def bird_shin(look: CharacterLook, x: float, knee: float, front: bool, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A bird's thin shin from the knee to the ground and, without shoes, its toes (three
    forward and one back from the side; spread from the front), the soles at 0."""
    thin = 0.035
    shin = RoundedRectangle(width=thin, height=knee + thin / 2, corner_radius=thin / 2).move_to([x, (knee + thin / 2) / 2, 0])
    pieces: list[VMobject] = [outlined(shin, BEAK_COLOR, c["outline"], w)]
    if look.shoes != "none":
        return pieces
    toes = [(-0.035, 0.0, 0.05), (0.0, 0.0, 0.05), (0.035, 0.0, 0.05)] if front else [(0.045, 0.0, 0.075), (0.035, 15.0, 0.065), (-0.025, 0.0, 0.045)]
    for dx, angle, length in toes:
        toe = Ellipse(width=length, height=0.02).rotate(math.radians(angle)).move_to([x + dx, 0.01 + abs(math.sin(math.radians(angle))) * length / 2, 0])
        pieces.append(outlined(toe, BEAK_COLOR, c["outline"], w * 0.75))
    return pieces


# ----- the tail --------------------------------------------------------------------------------------


def _bumpy_puff(x: float, y: float, radius: float) -> VMobject:
    return polygon([point_at(x, y, radius * (1.0 if k % 2 else 1.12), 360.0 * k / 24) for k in range(24)])


def shell(f: Frame, c: Mapping[str, str], w: float) -> VGroup:
    """A turtle's shell (``colors.hair``) for the back of the ``body`` part, drawn behind the
    body: from the side a dome bulging out behind the back with a light rim and the lines of its
    plates; from the front its rim showing round the body's sides and shoulders."""
    p, ink = f.p, c["outline"]
    color = c["hair"]
    middle = f.body_bottom + 0.52 * p.body_height
    if f.front:
        outer = Ellipse(width=1.3 * p.body_width, height=1.08 * p.body_height).move_to([0.0, middle, 0])
        inner = Ellipse(width=1.12 * p.body_width, height=0.98 * p.body_height).move_to([0.0, middle, 0])
        return VGroup(outlined(outer, fur_tint(color), ink, w), outlined(inner, color, ink, w * 0.6))
    centre = (-0.2 * p.body_width, middle + 0.02)
    rim = Ellipse(width=1.22 * p.body_width, height=1.06 * p.body_height).move_to([*centre, 0])
    dome = Ellipse(width=1.12 * p.body_width, height=0.98 * p.body_height).move_to([centre[0] + 0.01, centre[1], 0])
    plates = Ellipse(width=0.7 * p.body_width, height=0.6 * p.body_height).move_to([*centre, 0])
    seams: list[Line] = []
    for angle in (135.0, 180.0, 225.0):
        inner_point = (centre[0] + 0.35 * p.body_width * math.cos(math.radians(angle)), centre[1] + 0.3 * p.body_height * math.sin(math.radians(angle)))
        outer_point = (centre[0] + 0.56 * p.body_width * math.cos(math.radians(angle)), centre[1] + 0.49 * p.body_height * math.sin(math.radians(angle)))
        seams.append(Line([*inner_point, 0], [*outer_point, 0]))
    shade = fur_shade(color)
    return VGroup(
        outlined(rim, fur_tint(color), ink, w), outlined(dome, color, ink, w * 0.6),
        plates.set_fill(opacity=0).set_stroke(shade, width=w * 0.6), *(seam.set_stroke(shade, width=w * 0.6) for seam in seams),
    )


def _fox_tail(root: Point, side: float, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A fox's bushy tail (:data:`FOX_TAIL`): a band widest in its middle, its tip light."""
    line, widest, tip_share = FOX_TAIL
    centre = path_curve([(root[0] - side * dx, root[1] + dy) for dx, dy in line], samples=4)
    tip_from = int(len(centre) * (1.0 - tip_share))

    def bushy(share: float) -> float:
        return widest * (0.35 + 0.65 * math.sin(math.pi * min(0.15 + 0.85 * share, 1.0)))

    tail = polygon(tapered_band(centre, widest, 0.04, profile=bushy))
    tip = polygon(tapered_band(centre[tip_from:], bushy((tip_from) / (len(centre) - 1)), 0.04))
    return [trailing(outlined(tail, c["skin"], c["outline"], w), root, "tail"), trailing(outlined(tip, patch_tint(c["skin"]), c["outline"], w), root, "tail")]


def tail_part(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> CharacterPart:
    """The ``tail`` part: from its root low on the back of the body (from the front: behind the
    body, its end showing beside it), pivoting there; long tails and a bird's feathers trail in
    the wind (:data:`~vidgen.cartoon.primitives.TRAIL_WEIGHTS`). A frog has none (the generator
    does not call this for one)."""
    p, skin, ink = f.p, c["skin"], c["outline"]
    side = 1.0 if f.front else -1.0   # the way the tail goes: back, or (from the front) to one side
    species = look.species
    if species == "turtle":   # out from under the back of the shell
        root = ((0.12 if f.front else -0.62) * p.body_width, f.body_bottom + 0.12 * p.body_height)
    else:
        root = ((0.12 if f.front else -0.4) * p.body_width, f.body_bottom + 0.22 * p.body_height)
    pieces: list[VMobject]
    if species in TAIL_LINES:
        line, start, end = TAIL_LINES[species]
        centre = path_curve([(root[0] - side * dx, root[1] + dy) for dx, dy in line], samples=4)
        color = _mix(skin, PINK, 0.6) if species == "mouse" else skin
        pieces = [trailing(outlined(polygon(tapered_band(centre, start, end)), color, ink, w), root, "tail")]
    elif species == "fox":
        pieces = _fox_tail(root, side, c, w)
    elif species in BEAKED:   # a fan of feathers (an owl's short, a penguin's one stubby wedge)
        angles, length, start, end = TAIL_FEATHERS
        shown = (245.0, 270.0, 295.0) if f.front else angles
        if species == "owl":
            length *= 0.65
        elif species == "penguin":
            shown, length, start, end = (270.0,) if f.front else (212.0,), 0.11, 0.09, 0.03
        pieces = [trailing(outlined(polygon(tapered_band([root, point_at(*root, length, a)], start, end)), fur_shade(skin), ink, w), root, "feathers")
                  for a in shown]
    else:   # a round tail on the back (from the front: hidden behind the body)
        x = root[0] - (0.0 if f.front else 0.1 * p.body_width + 0.03)
        if species == "rabbit":
            pieces = [outlined(_bumpy_puff(x, root[1] + 0.01, 0.065), fur_tint(skin), ink, w)]
        else:   # bear
            pieces = [outlined(Circle(radius=0.05).move_to([x + 0.01, root[1], 0]), skin, ink, w)]
    return CharacterPart("tail", {"default": VGroup(*pieces)}, root)


__all__ = [
    "BEAKED",
    "BEAKS",
    "BEAK_COLOR",
    "BEAK_LAUGH_OPENING",
    "BEAK_OPENINGS",
    "BEAK_TONGUE_OPENING",
    "FOX_TAIL",
    "FROG_EYE_RISE",
    "HEAD_SHAPES",
    "MOUTH_PLACES",
    "PINK",
    "SPECIES_PROPORTIONS",
    "TAIL_LINES",
    "WINGED",
    "beak_mouth",
    "bird_shin",
    "ears",
    "face",
    "flat_foot",
    "flipper",
    "fur_shade",
    "fur_tint",
    "head_shape",
    "is_animal",
    "mouth_place",
    "patch_tint",
    "paw",
    "proportion_factors",
    "shell",
    "species_frame",
    "tail_part",
    "wing",
]
