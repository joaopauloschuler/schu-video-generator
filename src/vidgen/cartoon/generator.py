"""The parametric character generator (DESIGN.md §69.1, §69.47): ``look:`` parameters -> character parts.

Every figure is built from primitives (circles, ellipses, rounded rectangles, polygons and lines)
in character units (origin between the feet, ``y`` up), then scaled so its top is at 1. The
proportions come from :func:`resolve_proportions` (numbers only): the look's values, its
``proportions`` (adult or kid), varied a little by ``seed``. Facing right, the face sits a little
to the right and the nose points right. The front view (``front=True``, DESIGN.md §69.44) draws
the same parts and shapes with the face in the middle of the head, the pupils looking ahead, a
symmetric nose, hair and body, and temples on both sides of glasses. What is worn on the body
(the outfit, its pattern, shoes, scarf, bag, backpack, necklace) is drawn by
:mod:`vidgen.cartoon.clothes`; an animal's head, paws, wings or flippers, its feet, the tail,
a turtle's shell and the species' proportions (``species``) by :mod:`vidgen.cartoon.animals`; a
robot's head, antenna, joints, hands, feet or wheels and chest panel by
:mod:`vidgen.cartoon.robots`; the costume pieces (crown, wizard hat, party hat, cape) by
:mod:`vidgen.cartoon.costumes`.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace

import numpy as np
from manim import PI, Arc, Circle, Ellipse, Line, RoundedRectangle, VGroup, VMobject

from vidgen.cartoon import animals, costumes, robots
from vidgen.cartoon.character import OUTLINE_WIDTH, TRAIL_ATTRIBUTE, CharacterPart
from vidgen.cartoon.clothes import LIMB_WIDTH, body_shapes, limb_colors, shoe
from vidgen.cartoon.primitives import (
    TRAIL_WEIGHTS,
    arc_points,
    filled,
    outer_hair,
    outlined,
    point_at,
    polygon,
    trailing,
)
from vidgen.config import SPECIES_WITHOUT_TAIL, CharacterLook

#: Colour keys :func:`generate_parts` needs (the fields of ``characters[].colors``).
COLOR_KEYS: tuple[str, ...] = ("skin", "clothes", "outline", "features", "hair", "accessory", "trim")
#: The whites of the ``oval`` and ``round`` eyes.
EYE_WHITE = "#FFFFFF"
#: (width, height) of each body shape, in character units before the figure is scaled to height 1.
BODY_SIZES: dict[str, tuple[float, float]] = {
    "round": (0.40, 0.44), "tall": (0.30, 0.52), "square": (0.42, 0.40), "bean": (0.36, 0.48),
    "pear": (0.42, 0.46), "triangle": (0.44, 0.46),
}
#: How far ``seed`` may move each proportion (a factor in [1 - x, 1 + x]).
SEED_VARIATION = 0.08
#: ``proportions`` other than ``adult``: factors on the adult proportions. A small kid has a big
#: head and eyes on a short body and legs; a tall kid is lankier, with a smaller head than a
#: small kid's (DESIGN.md §69.47).
PROPORTION_FACTORS: dict[str, dict[str, float]] = {
    "kid": {"head_radius": 1.3, "eye_gap": 1.3, "eye_size": 1.12, "body_width": 0.85, "body_height": 0.72, "leg_length": 0.72, "arm_length": 0.78},
    "tall_kid": {"head_radius": 1.12, "eye_gap": 1.12, "eye_size": 1.05, "body_width": 0.8, "body_height": 0.85, "leg_length": 0.95, "arm_length": 0.9},
}
#: Where the shoulders (the arms' pivots) are, as a share of half the body's width: a pear's
#: are narrower than its hips.
SHOULDER_SHARES: dict[str, float] = {"pear": 0.62}


@dataclass(frozen=True)
class Proportions:
    """The sizes the generator draws with, in character units before scaling to height 1 (eye
    size and mouth width are factors)."""

    head_radius: float
    body_width: float
    body_height: float
    leg_length: float
    arm_length: float
    eye_gap: float
    eye_size: float
    mouth_width: float


def resolve_proportions(look: CharacterLook) -> Proportions:
    """The proportions of ``look``: its body shape and head size, its ``proportions``
    (:data:`PROPORTION_FACTORS`), then each varied by up to :data:`SEED_VARIATION` with
    ``random.Random(look.seed)`` (no variation without a seed)."""
    width, height = BODY_SIZES[look.body]
    head_radius = 0.2 * look.head_size
    base = Proportions(
        head_radius=head_radius, body_width=width, body_height=height, leg_length=0.24, arm_length=0.26,
        eye_gap=0.35 * head_radius, eye_size=1.0, mouth_width=1.0,
    )
    if look.proportions != "adult":
        base = replace(base, **{name: getattr(base, name) * factor for name, factor in PROPORTION_FACTORS[look.proportions].items()})
    species = animals.proportion_factors(look)
    if species:
        base = replace(base, **{name: getattr(base, name) * factor for name, factor in species.items()})
    if look.seed is None:
        return base
    rng = random.Random(look.seed)  # random() (unlike uniform()) is promised the same sequence in every Python version
    return replace(base, **{f.name: getattr(base, f.name) * (1 + SEED_VARIATION * (2 * rng.random() - 1)) for f in fields(base)})


# ----- the figure ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """Where the generator puts things (character units, before scaling to height 1)."""

    p: Proportions
    body_bottom: float
    body_top: float
    head_x: float
    head_y: float
    face_x: float
    eye_y: float
    front: bool = False

    @classmethod
    def of(cls, p: Proportions, front: bool = False) -> Frame:
        """Where things go for proportions ``p``; ``front``: the front view (the face centred)."""
        body_bottom = p.leg_length - 0.06
        body_top = body_bottom + p.body_height
        head_y = body_top + p.head_radius - 0.02
        face_x = 0.0 if front else 0.125 * p.head_radius
        return cls(p, body_bottom, body_top, 0.0, head_y, face_x, head_y + 0.15 * p.head_radius, front)


def _outline_points(center_y: float, half_w: float, half_h: float, width_at: Callable[[float], float], count: int = 40) -> list[list[float]]:
    """A closed outline about (0, ``center_y``): at angle t the point (cos t, sin t) scaled by
    ``half_w`` × ``width_at(sin t)`` and ``half_h``."""
    points = []
    for k in range(count):
        t = 2 * PI * k / count
        x, y = math.cos(t), math.sin(t)
        points.append([x * half_w * width_at(y), center_y + y * half_h])
    return points


def _body_shape(look: CharacterLook, f: Frame) -> VMobject:
    p = f.p
    center = [0.0, (f.body_bottom + f.body_top) / 2, 0.0]
    if look.body == "round":
        return Ellipse(width=p.body_width, height=p.body_height).move_to(center)
    if look.body == "tall":
        return RoundedRectangle(width=p.body_width, height=p.body_height, corner_radius=p.body_width * 0.4).move_to(center)
    if look.body == "square":
        return RoundedRectangle(width=p.body_width, height=p.body_height, corner_radius=0.05).move_to(center)
    half_w, half_h = p.body_width / 2, p.body_height / 2
    if look.body == "pear":   # narrow at the shoulders, widest low down
        return polygon(_outline_points(center[1], half_w, half_h, lambda y: 0.78 - 0.22 * y))
    if look.body == "triangle":   # broad square shoulders, narrowing to the hips
        points = []
        for k in range(40):
            t = 2 * PI * k / 40
            c, s = math.cos(t), math.sin(t)
            squarish_x, squarish_y = math.copysign(abs(c) ** 0.6, c), math.copysign(abs(s) ** 0.7, s)
            points.append([squarish_x * half_w * (0.76 + 0.24 * squarish_y), center[1] + squarish_y * half_h])
        return polygon(points)
    # bean: an oval pinched in at the back (not from the front), a little wider at the bottom
    pinch = 0.0 if f.front else 0.22
    points = []
    for k in range(40):
        t = 2 * PI * k / 40
        x, y = math.cos(t), math.sin(t)
        width = 1.0 + 0.12 * (-y) - (pinch * math.exp(-((t - PI) ** 2) / 0.25))
        points.append([x * half_w * width, center[1] + y * half_h])
    return polygon(points)


def _segment(x: float, top: float, bottom: float, color: str, c: Mapping[str, str], w: float) -> VMobject:
    """A limb segment hanging from (x, ``top``) to (x, ``bottom``), the round ends centred there."""
    length = top - bottom + LIMB_WIDTH
    shape = RoundedRectangle(width=LIMB_WIDTH, height=length, corner_radius=LIMB_WIDTH / 2).move_to([x, (top + bottom) / 2, 0])
    return outlined(shape, color, c["outline"], w)


def _legs(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> list[CharacterPart]:
    """Each leg in two segments: the thigh turns about the hip (under the body), the shin about
    the knee half-way down; the foot's sole is at the ground (with the look's shoes on it)."""
    p = f.p
    x = 0.07 * p.body_width / 0.4
    hip, foot = p.leg_length - LIMB_WIDTH / 2, LIMB_WIDTH / 2
    knee = (hip + foot) / 2
    _, _, thigh_color, shin_color = limb_colors(look, c)
    parts = []
    robot = robots.is_robot(look)
    if robot:
        _, _, thigh_color, shin_color = robots.limb_colors(look, c, limb_colors(look, c))
    for name, side in (("leg_left", 1.0), ("leg_right", -1.0)):
        parts.append(CharacterPart(name, {"default": VGroup(_segment(side * x, hip, knee, thigh_color, c, w))}, (side * x, hip)))
        if robot:   # a knee bolt, and a block foot or a wheel (§69.58)
            if look.robot_look().moves_on == "wheels":
                shin = VGroup(_segment(side * x, knee, robots.WHEEL_RADIUS, shin_color, c, w), *robots.wheel(side * x, f.front, c, w))
            else:
                shin = VGroup(_segment(side * x, knee, foot, shin_color, c, w), *shoe(look, side * x, f.front, c, w), *robots.foot(look, side * x, f.front, c, w))
            shin.add(robots.joint(side * x, knee, c, w))
        elif look.species in animals.WINGED and shin_color == c["skin"]:   # bare: a bird's thin shin and toes
            shin = VGroup(*animals.bird_shin(look, side * x, knee, f.front, c, w), *shoe(look, side * x, f.front, c, w))
        else:
            shin = VGroup(_segment(side * x, knee, foot, shin_color, c, w), *shoe(look, side * x, f.front, c, w))
        if look.species in ("frog", "penguin"):
            shin.add(*animals.flat_foot(look, side * x, f.front, c, w))
        parts.append(CharacterPart(f"{name}_lower", {"default": shin}, (side * x, knee), end=(side * x, 0.0)))
    return parts


def _arm(name: str, side: float, look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> list[CharacterPart]:
    """An arm in two segments: the upper sleeve turns about the shoulder, the forearm (sleeve or
    bare arm, and hand) about the elbow half-way down; its end is the hand's middle."""
    p = f.p
    x, shoulder_y = side * p.body_width / 2 * SHOULDER_SHARES.get(look.body, 1.0), f.body_top - 0.08
    top, wrist = shoulder_y + 0.02 - LIMB_WIDTH / 2, shoulder_y + 0.02 - p.arm_length
    elbow = (top + wrist) / 2
    upper_color, lower_color, _, _ = limb_colors(look, c)
    if look.species in animals.WINGED:   # a wing, whatever the sleeves (§69.48)
        upper, lower = animals.wing(x, top, elbow, wrist, c, w)
    elif look.species == "penguin":   # a flipper, whatever the sleeves (§69.57)
        upper, lower = animals.flipper(x, top, elbow, wrist, c, w)
    elif robots.is_robot(look):   # bolted joints and a gripper (§69.58)
        upper_color, lower_color, _, _ = robots.limb_colors(look, c, limb_colors(look, c))
        upper = VGroup(_segment(x, top, elbow, upper_color, c, w), robots.joint(x, shoulder_y, c, w))
        lower = VGroup(_segment(x, elbow, wrist, lower_color, c, w), robots.hand(x, wrist, c, w), robots.joint(x, elbow, c, w))
    else:
        upper = VGroup(_segment(x, top, elbow, upper_color, c, w))
        hand = animals.paw(x, wrist, c, w) if animals.is_animal(look) else outlined(Circle(radius=0.045).move_to([x, wrist, 0]), c["skin"], c["outline"], w)
        lower = VGroup(_segment(x, elbow, wrist, lower_color, c, w), hand)
    return [
        CharacterPart(name, {"default": upper}, (x, shoulder_y)),
        CharacterPart(f"{name}_lower", {"default": lower}, (x, elbow), end=(x, wrist)),
    ]


def _hair_cap(look: CharacterLook, f: Frame) -> VMobject:
    """The hair over the top of the head: an arc (zigzag for ``spiky``) and a fringe above the eyes."""
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    radii = [1.35 * r if k % 2 else 1.0 * r for k in range(19)] if look.hair == "spiky" else [1.06 * r] * 25
    outer = arc_points(cx, cy, radii, -10, 190)
    fringe = [(-0.92, -0.15), (-0.7, 0.45), (-0.3, 0.62), (0.05, 0.55), (0.45, 0.7), (0.85, 0.4), (0.98, -0.05)]
    if f.front:   # symmetric: parted in the middle
        fringe = [(-0.97, -0.1), (-0.75, 0.42), (-0.35, 0.62), (0.0, 0.5), (0.35, 0.62), (0.75, 0.42), (0.97, -0.1)]
    return polygon([*outer, *((cx + a * r, cy + b * r) for a, b in fringe)])


def _braid(x: float, top: float, r: float) -> VGroup:
    """A braid hanging from (``x``, ``top``): four plaited lobes and a tie at the end."""
    lobes = [Ellipse(width=0.42 * r, height=0.38 * r).move_to([x, top - (0.17 + 0.3 * k) * r, 0]) for k in range(4)]
    tie = Ellipse(width=0.24 * r, height=0.2 * r).move_to([x, top - 1.33 * r, 0])
    return VGroup(*lobes, tie)


def _hair_back(look: CharacterLook, f: Frame) -> list[VMobject]:
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    if look.hair == "long":
        top = arc_points(cx, cy, [1.1 * r] * 25, 0, 180)
        ends = [(-1.12, -1.28), (0.0, -1.38), (1.12, -1.28)] if f.front else [(-1.15, -1.3), (-0.5, -1.4), (1.05, -1.25)]
        hair = polygon([*top, *((cx + a * r, cy + b * r) for a, b in ends)])
        return [trailing(hair, (cx, cy + 0.4 * r), "long")]
    if look.hair == "bun":
        bun_x = cx if f.front else cx - 0.15 * r
        return [trailing(Circle(radius=0.38 * r).move_to([bun_x, cy + 1.18 * r, 0]), (bun_x, cy + 0.85 * r), "bun")]
    if look.hair == "curly":
        return [Circle(radius=0.32 * r).move_to([x, y, 0]) for x, y in arc_points(cx, cy, [0.95 * r] * 12, -20, 200)]
    if look.hair == "ponytail":   # tied high at the back (from the front: swinging out on one side)
        tie_x, tie_y = (cx - 0.75 * r, cy + 0.6 * r) if f.front else (cx - 0.88 * r, cy + 0.42 * r)
        tip_x = tie_x - (0.55 if f.front else 0.42) * r
        tail = polygon([
            (tie_x + 0.12 * r, tie_y + 0.1 * r), (tie_x - 0.28 * r, tie_y + 0.05 * r), (tip_x - 0.1 * r, tie_y - 0.55 * r),
            (tip_x, tie_y - 1.15 * r), (tip_x + 0.22 * r, tie_y - 0.75 * r), (tie_x + 0.12 * r, tie_y - 0.2 * r),
        ])
        tie = Circle(radius=0.12 * r).move_to([tie_x, tie_y, 0])
        return [outer_hair(trailing(tail, (tie_x, tie_y), "ponytail")), outer_hair(tie)]
    if look.hair == "braids":   # one on each side; from the side the far one is hidden behind the head
        xs = (cx - 0.98 * r, cx + 0.98 * r) if f.front else (cx - 0.72 * r,)
        return [outer_hair(trailing(_braid(x, cy - 0.05 * r, r), (x, cy - 0.05 * r), "braids")) for x in xs]
    if look.hair == "afro":   # a big round mass of curls about the head
        mass_x = cx if f.front else cx - 0.12 * r
        radii = [1.0 if k % 2 else 1.07 for k in range(41)]
        outline = [(mass_x + 1.5 * r * radius * math.cos(2 * PI * k / 40), cy + 0.42 * r + 1.27 * r * radius * math.sin(2 * PI * k / 40))
                   for k, radius in enumerate(radii[:40])]
        return [outer_hair(polygon(outline))]
    return []


def _ears(look: CharacterLook, f: Frame) -> list[VMobject]:
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    if look.ears == "round":
        return [Circle(radius=0.28 * r).move_to([cx + side * 0.98 * r, cy, 0]) for side in (-1, 1)]
    if look.ears == "pointy":
        return [
            trailing(polygon([point_at(cx, cy, 0.9 * r, tip - 15), point_at(cx, cy, 1.55 * r, tip), point_at(cx, cy, 0.9 * r, tip + 15)]), point_at(cx, cy, 0.9 * r, tip), "pointy")
            for tip in (65, 115)
        ]
    if look.ears == "floppy":
        return [
            trailing(Ellipse(width=0.4 * r, height=0.95 * r).move_to([cx + side * 1.0 * r, cy - 0.2 * r, 0]).rotate(side * 0.25), (cx + side * 1.0 * r, cy + 0.2 * r), "floppy")
            for side in (-1, 1)
        ]
    return []


def _nose(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    r, y = f.p.head_radius, f.head_y - 0.1 * f.p.head_radius
    x = f.face_x + (0.0 if f.front else 0.05 * r)
    if look.nose == "dot":
        return [filled(Ellipse(width=0.12 * r, height=0.09 * r).move_to([x, y, 0]), c["features"])]
    if look.nose == "round":
        return [outlined(Circle(radius=0.1 * r).move_to([x, y, 0]), c["skin"], c["outline"], w)]
    if look.nose == "triangle":
        corners = [(x, y + 0.11 * r), (x + 0.1 * r, y - 0.09 * r), (x - 0.1 * r, y - 0.09 * r)] if f.front else \
            [(x - 0.04 * r, y + 0.11 * r), (x + 0.24 * r, y - 0.09 * r), (x - 0.04 * r, y - 0.09 * r)]
        return [outlined(polygon(corners), c["skin"], c["outline"], w)]
    return []


def _facial_hair(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A beard round the jaw (with a patch of skin where the mouth moves) and a moustache under the
    nose (``beard`` has both), in the hair colour."""
    if look.facial_hair == "none":
        return []
    r, cx, cy, fx = f.p.head_radius, f.head_x, f.head_y, f.face_x
    pieces: list[VMobject] = []
    if look.facial_hair == "beard":
        start, end = (200.0, 340.0) if f.front else (215.0, 345.0)
        outer = []
        for k in range(17):
            degrees = start + (end - start) * k / 16
            below = max(0.0, -math.sin(math.radians(degrees)))
            x, y = point_at(cx, cy, 1.03 * r + 0.32 * r * below**3, degrees)
            outer.append((x + (fx - cx) * below**3, y))
        inner = arc_points(fx, cy - 0.12 * r, [0.6 * r] * 9, end, start)
        pieces.append(outer_hair(outlined(polygon([*outer, *inner]), c["hair"], c["outline"], w)))
        pieces.append(filled(Ellipse(width=0.72 * r, height=0.5 * r).move_to([fx, cy - 0.45 * r, 0]), c["skin"]))
    lean = 0.0 if f.front else 0.04 * r
    for side in (-1.0, 1.0):
        lobe = Ellipse(width=(0.34 if f.front or side > 0 else 0.28) * r, height=0.14 * r)
        lobe.rotate(side * 0.25).move_to([fx + lean + side * 0.15 * r, cy - 0.3 * r, 0])
        pieces.append(outlined(lobe, c["hair"], c["outline"], w * 0.75))
    return pieces


def _head(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> VGroup:
    """Back hair, ears, the head, the hair cap, facial hair and the nose (all move with the head);
    an animal's ears, head and face (muzzle, snout or beak, nose, whiskers) instead (§69.48)."""
    if robots.is_robot(look):   # its own neck, head and face plate or screen; no hair (§69.58)
        return VGroup(*robots.head(look, f, c, w))
    group = VGroup(*(outlined(m, c["hair"], c["outline"], w) for m in _hair_back(look, f)))
    if animals.is_animal(look):
        group.add(*animals.ears(look, f, c, w))
        group.add(outlined(animals.head_shape(look, f), c["skin"], c["outline"], w))
    else:
        group.add(*(outlined(m, c["skin"], c["outline"], w) for m in _ears(look, f)))
        group.add(outlined(Circle(radius=f.p.head_radius).move_to([f.head_x, f.head_y, 0]), c["skin"], c["outline"], w))
    if look.hair != "none":
        group.add(outlined(_hair_cap(look, f), c["hair"], c["outline"], w))
    group.add(*_facial_hair(look, f, c, w))
    group.add(*_nose(look, f, c, w))
    if animals.is_animal(look):
        group.add(*animals.face(look, f, c, w))
    return group


def _eye_size(look: CharacterLook, f: Frame) -> tuple[float, float]:
    """(width, height) of one open eye."""
    r = f.p.head_radius * f.p.eye_size
    return {"dot": (0.25 * r, 0.375 * r), "oval": (0.3 * r, 0.45 * r), "round": (0.4 * r, 0.4 * r), "sleepy": (0.3 * r, 0.2 * r)}[look.eyes]


def _eye_xs(f: Frame) -> tuple[float, float]:
    return f.face_x - f.p.eye_gap, f.face_x + f.p.eye_gap


def _open_eye(look: CharacterLook, x: float, f: Frame, c: Mapping[str, str], w: float) -> VGroup:
    width, height = _eye_size(look, f)
    y, look_x = f.eye_y, 0.0 if f.front else 0.15 * width  # pupils look a little to the right (from the front: ahead)
    if look.eyes == "dot":
        return VGroup(filled(Ellipse(width=width, height=height).move_to([x, y, 0]), c["features"]))
    if look.eyes == "sleepy":
        lower = arc_points(x, y, [width / 2] * 13, 180, 360)
        half = polygon([(px, y + (py - y) * 2 * height / width) for px, py in lower])
        lid = Line([x - width * 0.65, y + 0.01, 0], [x + width * 0.65, y + 0.01, 0]).set_stroke(c["features"], width=w)
        return VGroup(filled(half, c["features"]), lid)
    white = Ellipse(width=width, height=height) if look.eyes == "oval" else Circle(radius=width / 2)
    pupil = Ellipse(width=width * 0.45, height=height * 0.45).move_to([x + look_x, y - 0.05 * height, 0])
    return VGroup(outlined(white.move_to([x, y, 0]), EYE_WHITE, c["outline"], w * 0.75), filled(pupil, c["features"]))


def _face(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> list[CharacterPart]:
    """Eyes (``open`` / ``closed``), brows (``default`` / ``angry`` / ``sad``) and mouth (``smile`` /
    ``open`` and the viseme shapes ``A E O U M F L W``)."""
    r, fx = f.p.head_radius, f.face_x
    width, height = _eye_size(look, f)
    xs = _eye_xs(f)
    if robots.has_screen(look):   # glowing on the screen (§69.58)
        open_eyes = VGroup(*(robots.screen_eye(look.eyes, x, f.eye_y, width, height) for x in xs))
    else:
        open_eyes = VGroup(*(_open_eye(look, x, f, c, w) for x in xs))
    closed_y = f.eye_y - (0 if look.eyes == "sleepy" else 0.025 * r)
    closed_eyes = VGroup(*(Line([x - width * 0.6, closed_y, 0], [x + width * 0.6, closed_y, 0]).set_stroke(c["features"], width=w) for x in xs))
    brow_y = f.eye_y + height / 2 + animals.BROW_GAPS.get(look.species, 0.16) * r

    def brows(back_left: float, back_right: float, front_left: float, front_right: float) -> VGroup:
        """Two brow lines; the arguments are each end's height (× r) above ``brow_y``."""
        ends = ((back_left, back_right), (front_left, front_right))
        return VGroup(*(
            Line([x - 0.175 * r, brow_y + left * r, 0], [x + 0.175 * r, brow_y + right * r, 0]).set_stroke(c["features"], width=w)
            for x, (left, right) in zip(xs, ends)
        ))

    # the mouth: on the face, or (an animal, §69.48) on its muzzle, under its snout, smaller
    mx, my, size = animals.mouth_place(look, f)
    mr = r * size   # the head radius the mouth is drawn for
    mouth_r = 0.3 * mr * f.p.mouth_width
    mouth_y = my - 0.45 * mr
    smile = Arc(radius=mouth_r, start_angle=PI * 1.2, angle=PI * 0.6, arc_center=[mx, my - 0.2 * mr, 0]).set_stroke(c["features"], width=w)

    def opening(width: float, height: float) -> VMobject:
        """A filled mouth opening, ``width`` × the mouth radius by ``height`` × the head radius."""
        return filled(Ellipse(width=width * mouth_r, height=height * mr).move_to([mx, mouth_y, 0]), c["features"])

    closed = Line([mx - 0.75 * mouth_r, mouth_y + 0.03 * mr, 0], [mx + 0.75 * mouth_r, mouth_y + 0.03 * mr, 0]).set_stroke(c["features"], width=w)
    # viseme shapes (DESIGN.md §69.4): A open, E wide, O round, U small round, M closed lips,
    # F a thin line (lip under the teeth), L open, W puckered
    speech = {
        "A": opening(1.6, 0.42), "E": opening(1.8, 0.18), "O": opening(0.95, 0.36), "U": opening(0.6, 0.24),
        "M": closed, "F": opening(1.3, 0.08), "L": opening(1.2, 0.28), "W": opening(0.45, 0.18),
    }
    mouth = CharacterPart("mouth", {"smile": smile, "open": opening(1.5, 0.35), **speech}, (mx, my - 0.4 * mr))
    if look.species in animals.BEAKED:   # it talks with its beak
        shapes, hinge = animals.beak_mouth(look.species, f, c, w)
        mouth = CharacterPart("mouth", shapes, hinge)
    return [
        CharacterPart("eyes", {"open": open_eyes, "closed": closed_eyes}, (fx, f.eye_y)),
        # angry: the inner ends (toward the face's middle) low; sad: the inner ends high
        CharacterPart("brows", {
            "default": brows(-0.025, 0.025, -0.025, 0.025),
            "angry": brows(0.05, -0.07, -0.07, 0.05),
            "sad": brows(-0.05, 0.07, 0.07, -0.05),
        }, (fx, brow_y)),
        mouth,
    ]


def _cap(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A cap: a dome over the top of the head with a button, its peak forward (from the front: a
    band across the forehead)."""
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    dome = polygon(arc_points(cx, cy + 0.08 * r, [1.06 * r] * 17, 28, 152))
    button = Circle(radius=0.08 * r).move_to([cx, cy + 1.16 * r, 0])
    if f.front:
        peak = Ellipse(width=1.9 * r, height=0.24 * r).move_to([cx, cy + 0.6 * r, 0])
        pieces = [dome, peak, button]
    else:
        peak = polygon([(cx + 0.55 * r, cy + 0.7 * r), (cx + 1.42 * r, cy + 0.6 * r), (cx + 1.5 * r, cy + 0.5 * r), (cx + 1.4 * r, cy + 0.43 * r), (cx + 0.6 * r, cy + 0.5 * r)])
        pieces = [peak, dome, button]
    return [trailing(outlined(piece, c["accessory"], c["outline"], w), (cx, cy + 0.6 * r), "cap") for piece in pieces]


def _bow(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A bow on top of the head (towards the back; from the front: on one side)."""
    r = f.p.head_radius
    x, y = (f.head_x + 0.55 * r, f.head_y + 0.82 * r) if f.front else (f.head_x - 0.42 * r, f.head_y + 0.9 * r)
    loops = [polygon([(x, y), (x + side * 0.42 * r, y + 0.22 * r), (x + side * 0.46 * r, y - 0.18 * r)]) for side in (-1.0, 1.0)]
    knot = Circle(radius=0.1 * r).move_to([x, y, 0])
    return [outlined(piece, c["accessory"], c["outline"], w) for piece in (*loops, knot)]


def _worn_on_head(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> VGroup:
    """Glasses, hat, cap and bow (the ``accessory`` part)."""
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    group = VGroup()
    if "glasses" in look.accessories:
        lens_r = max(0.27 * r, max(_eye_size(look, f)) / 2 + 0.07 * r)
        back_x, front_x = _eye_xs(f)
        lenses = [Circle(radius=lens_r).move_to([x, f.eye_y, 0]).set_fill(EYE_WHITE, opacity=0.15).set_stroke(c["outline"], width=w) for x in (back_x, front_x)]
        bridge = Line([back_x + lens_r, f.eye_y, 0], [front_x - lens_r, f.eye_y, 0]).set_stroke(c["outline"], width=w)
        temple = Line([back_x - lens_r, f.eye_y, 0], [cx - 0.97 * r, f.eye_y + 0.05 * r, 0]).set_stroke(c["outline"], width=w)
        temples = [temple]
        if f.front:   # one on each side
            temples.append(Line([front_x + lens_r, f.eye_y, 0], [cx + 0.97 * r, f.eye_y + 0.05 * r, 0]).set_stroke(c["outline"], width=w))
        group.add(*temples, *lenses, bridge)
    if "hat" in look.accessories:
        brim_y = cy + 0.72 * r
        crown = RoundedRectangle(width=1.4 * r, height=0.9 * r, corner_radius=0.15 * r).move_to([cx, brim_y + 0.45 * r, 0])
        band = polygon([(cx - 0.7 * r, brim_y + 0.06 * r), (cx + 0.7 * r, brim_y + 0.06 * r), (cx + 0.7 * r, brim_y + 0.22 * r), (cx - 0.7 * r, brim_y + 0.22 * r)])
        brim = RoundedRectangle(width=2.5 * r, height=0.16 * r, corner_radius=0.07 * r).move_to([cx, brim_y, 0])
        hat = (outlined(crown, c["accessory"], c["outline"], w), outlined(band, c["clothes"], c["outline"], w), outlined(brim, c["accessory"], c["outline"], w))
        group.add(*(trailing(piece, (cx, brim_y), "hat") for piece in hat))
    if "cap" in look.accessories:
        group.add(*_cap(f, c, w))
    if "bow" in look.accessories:
        group.add(*_bow(f, c, w))
    for piece, drawing in costumes.HEADWEAR_DRAWINGS.items():   # a crown, a wizard hat, a party hat (§69.58)
        if piece in look.accessories:
            group.add(*drawing(f, c, w))
    return group


def generate_parts(
    look: CharacterLook, colors: Mapping[str, str], *, outline_width: float = OUTLINE_WIDTH, front: bool = False,
) -> list[CharacterPart]:
    """The parts of the figure ``look`` describes, in character units with its top at 1.
    ``colors`` maps every key of :data:`COLOR_KEYS` to a Manim colour (``trim`` may be left out
    for an outfit that does not use it); ``outline_width`` is the stroke width of outlines and
    feature lines (the :class:`Character` scales it with its height); ``front``: its front view,
    the same parts and shapes seen from the front (DESIGN.md §69.44). The same look always gives
    the same shapes."""
    f = animals.species_frame(look, Frame.of(resolve_proportions(look), front))
    w = outline_width
    body = body_shapes(look, f, _body_shape(look, f), colors, w)
    if look.species == "turtle":   # its shell on its back, behind the body and clothes
        for shape in body.values():
            shape.add_to_back(animals.shell(f, colors, w))
    over_body = [*(robots.chest_panel(f, colors, w) if robots.is_robot(look) else []),
                 *(costumes.cape_clasp(f, colors, w) if "cape" in look.accessories else [])]
    if over_body:   # a robot's chest panel, a cape's ties and clasp (§69.58)
        for k, shape in enumerate(body.values()):
            shape.add(*(m if k == 0 else m.copy() for m in over_body))
    parts = [
        *_legs(look, f, colors, w),
        CharacterPart("body", body, (0.0, f.body_bottom + 0.02)),
        *_arm("arm_left", 1.0, look, f, colors, w),
        *_arm("arm_right", -1.0, look, f, colors, w),
        CharacterPart("head", {"default": _head(look, f, colors, w)}, (0.0, f.body_top - 0.02)),
        *_face(look, f, robots.face_colors(look, colors), w),
    ]
    worn = _worn_on_head(look, f, colors, w)
    if worn.submobjects:
        parts.append(CharacterPart("accessory", {"default": worn}, (f.head_x, f.head_y)))
    if animals.is_animal(look) and look.species not in SPECIES_WITHOUT_TAIL:
        parts.append(animals.tail_part(look, f, colors, w))
    for extra in (robots.antenna_part(look, f, colors, w) if robots.is_robot(look) else None, costumes.cape_part(look, f, colors, w)):
        if extra is not None:
            parts.append(extra)
    return _scaled_to_unit_height(parts)


def _scaled_to_unit_height(parts: list[CharacterPart]) -> list[CharacterPart]:
    """``parts`` scaled about the feet so the top of the figure (every shape) is at 1 (the
    trailing pieces' pivots too)."""
    top = max(shape.get_top()[1] for part in parts for shape in part.shapes.values())
    factor = 1.0 / top
    if math.isclose(factor, 1.0):
        return parts
    for part in parts:
        for shape in part.shapes.values():
            shape.scale(factor, about_point=np.zeros(3))
            for member in shape.get_family():
                trail = getattr(member, TRAIL_ATTRIBUTE, None)
                if trail is not None:
                    setattr(member, TRAIL_ATTRIBUTE, (trail[0] * factor, trail[1] * factor, trail[2]))
    def scaled(point: tuple[float, float] | None) -> tuple[float, float] | None:
        return None if point is None else (point[0] * factor, point[1] * factor)

    return [replace(part, pivot=scaled(part.pivot), end=scaled(part.end)) for part in parts]


__all__ = [
    "BODY_SIZES",
    "COLOR_KEYS",
    "EYE_WHITE",
    "LIMB_WIDTH",
    "PROPORTION_FACTORS",
    "SHOULDER_SHARES",
    "TRAIL_WEIGHTS",
    "Frame",
    "Proportions",
    "generate_parts",
    "resolve_proportions",
]
