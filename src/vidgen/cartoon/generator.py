"""The parametric character generator (DESIGN.md §69.1): ``look:`` parameters -> character parts.

Every figure is built from primitives (circles, ellipses, rounded rectangles, polygons and lines)
in character units (origin between the feet, ``y`` up), then scaled so its top is at 1. The
proportions come from :func:`resolve_proportions` (numbers only): the look's values, varied a little
by ``seed``. Facing right, the face sits a little to the right and the nose points right. The
front view (``front=True``, DESIGN.md §69.44) draws the same parts and shapes with the face in the
middle of the head, the pupils looking ahead, a symmetric nose, hair and body, and temples on both
sides of glasses.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace

import numpy as np
from manim import PI, Arc, Circle, Ellipse, Line, Polygon, RoundedRectangle, VGroup, VMobject

from vidgen.cartoon.character import OUTLINE_WIDTH, TRAIL_ATTRIBUTE, CharacterPart
from vidgen.config import CharacterLook

#: Colour keys :func:`generate_parts` needs (the fields of ``characters[].colors``).
COLOR_KEYS: tuple[str, ...] = ("skin", "clothes", "outline", "features", "hair", "accessory")
#: The whites of the ``oval`` and ``round`` eyes.
EYE_WHITE = "#FFFFFF"
#: (width, height) of each body shape, in character units before the figure is scaled to height 1.
BODY_SIZES: dict[str, tuple[float, float]] = {
    "round": (0.40, 0.44), "tall": (0.30, 0.52), "square": (0.42, 0.40), "bean": (0.36, 0.48),
}
#: How far ``seed`` may move each proportion (a factor in [1 - x, 1 + x]).
SEED_VARIATION = 0.08
#: How far each trailing piece turns in the wind, as a share of
#: :data:`~vidgen.cartoon.wind.TRAIL_DEGREES` (DESIGN.md §69.32): the scarf's end, long hair, a
#: bun, pointy and floppy ears, the hat. Round ears and the other hair styles do not trail.
TRAIL_WEIGHTS: dict[str, float] = {"scarf": 1.2, "long": 0.7, "bun": 0.4, "pointy": 0.35, "floppy": 1.0, "hat": 0.35}


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
    """The proportions of ``look``: its body shape and head size, each varied by up to
    :data:`SEED_VARIATION` with ``random.Random(look.seed)`` (no variation without a seed)."""
    width, height = BODY_SIZES[look.body]
    head_radius = 0.2 * look.head_size
    base = Proportions(
        head_radius=head_radius, body_width=width, body_height=height, leg_length=0.24, arm_length=0.26,
        eye_gap=0.35 * head_radius, eye_size=1.0, mouth_width=1.0,
    )
    if look.seed is None:
        return base
    rng = random.Random(look.seed)  # random() (unlike uniform()) is promised the same sequence in every Python version
    return replace(base, **{f.name: getattr(base, f.name) * (1 + SEED_VARIATION * (2 * rng.random() - 1)) for f in fields(base)})


# ----- primitives ---------------------------------------------------------------------------


def _outlined(mob: VMobject, fill: str, outline: str, width: float) -> VMobject:
    return mob.set_fill(fill, opacity=1).set_stroke(outline, width=width)


def _filled(mob: VMobject, fill: str) -> VMobject:
    return mob.set_fill(fill, opacity=1).set_stroke(width=0)


def _at(cx: float, cy: float, radius: float, degrees: float) -> tuple[float, float]:
    """The point ``radius`` from (cx, cy) at ``degrees`` counterclockwise from the right."""
    angle = math.radians(degrees)
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def _arc_points(cx: float, cy: float, radii: Sequence[float], start_deg: float, end_deg: float) -> list[tuple[float, float]]:
    """Points from ``start_deg`` to ``end_deg`` around (cx, cy), one per radius (alternating
    radii give a zigzag)."""
    last = len(radii) - 1
    return [_at(cx, cy, radius, start_deg + (end_deg - start_deg) * k / last) for k, radius in enumerate(radii)]


def _polygon(points: Sequence[Sequence[float]]) -> Polygon:
    return Polygon(*(np.array([p[0], p[1], 0.0]) for p in points))


def _trailing(mob: VMobject, pivot: tuple[float, float], piece: str) -> VMobject:
    """Mark ``mob`` as a piece that trails in the wind, turning about ``pivot`` (the
    :class:`~vidgen.cartoon.character.Character` reads the mark; DESIGN.md §69.32)."""
    for member in mob.get_family():
        setattr(member, TRAIL_ATTRIBUTE, (float(pivot[0]), float(pivot[1]), TRAIL_WEIGHTS[piece]))
    return mob


# ----- the figure ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Frame:
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
    def of(cls, p: Proportions, front: bool = False) -> _Frame:
        """Where things go for proportions ``p``; ``front``: the front view (the face centred)."""
        body_bottom = p.leg_length - 0.06
        body_top = body_bottom + p.body_height
        head_y = body_top + p.head_radius - 0.02
        face_x = 0.0 if front else 0.125 * p.head_radius
        return cls(p, body_bottom, body_top, 0.0, head_y, face_x, head_y + 0.15 * p.head_radius, front)


def _body_shape(look: CharacterLook, f: _Frame) -> VMobject:
    p = f.p
    center = [0.0, (f.body_bottom + f.body_top) / 2, 0.0]
    if look.body == "round":
        return Ellipse(width=p.body_width, height=p.body_height).move_to(center)
    if look.body == "tall":
        return RoundedRectangle(width=p.body_width, height=p.body_height, corner_radius=p.body_width * 0.4).move_to(center)
    if look.body == "square":
        return RoundedRectangle(width=p.body_width, height=p.body_height, corner_radius=0.05).move_to(center)
    # bean: an oval pinched in at the back (not from the front), a little wider at the bottom
    half_w, half_h = p.body_width / 2, p.body_height / 2
    pinch = 0.0 if f.front else 0.22
    points = []
    for k in range(40):
        t = 2 * PI * k / 40
        x, y = math.cos(t), math.sin(t)
        width = 1.0 + 0.12 * (-y) - (pinch * math.exp(-((t - PI) ** 2) / 0.25))
        points.append([x * half_w * width, center[1] + y * half_h])
    return _polygon(points)


def _body(look: CharacterLook, f: _Frame, c: Mapping[str, str], w: float) -> VGroup:
    """The body and the accessories worn on it (scarf, bag)."""
    p = f.p
    group = VGroup(_outlined(_body_shape(look, f), c["clothes"], c["outline"], w))
    if "bag" in look.accessories:
        bag_x, bag_y = -p.body_width * 0.42, f.body_bottom + p.body_height * 0.3
        strap = Line([p.body_width * 0.28, f.body_top - 0.04, 0], [bag_x, bag_y + 0.05, 0]).set_stroke(c["accessory"], width=w * 1.8)
        bag = _outlined(RoundedRectangle(width=0.16, height=0.12, corner_radius=0.03).move_to([bag_x, bag_y, 0]), c["accessory"], c["outline"], w)
        flap = Line([bag_x - 0.08, bag_y + 0.025, 0], [bag_x + 0.08, bag_y + 0.025, 0]).set_stroke(c["outline"], width=w)
        group.add(strap, bag, flap)
    if "scarf" in look.accessories:
        band_w = min(p.body_width, 0.36) * 0.85
        band = RoundedRectangle(width=band_w, height=0.08, corner_radius=0.035).move_to([0, f.body_top - 0.03, 0])
        tail = RoundedRectangle(width=0.07, height=0.17, corner_radius=0.03).move_to([-band_w * 0.25, f.body_top - 0.12, 0]).rotate(-0.2)
        tail = _trailing(tail, (-band_w * 0.25, f.body_top - 0.05), "scarf")
        group.add(_outlined(tail, c["accessory"], c["outline"], w), _outlined(band, c["accessory"], c["outline"], w))
    return group


#: Width of a sleeve or a leg; its ends are round (half this radius), so a bent elbow or knee
#: stays a smooth joint.
LIMB_WIDTH = 0.08


def _segment(x: float, top: float, bottom: float, color: str, c: Mapping[str, str], w: float) -> VMobject:
    """A limb segment hanging from (x, ``top``) to (x, ``bottom``), the round ends centred there."""
    length = top - bottom + LIMB_WIDTH
    shape = RoundedRectangle(width=LIMB_WIDTH, height=length, corner_radius=LIMB_WIDTH / 2).move_to([x, (top + bottom) / 2, 0])
    return _outlined(shape, color, c["outline"], w)


def _legs(f: _Frame, c: Mapping[str, str], w: float) -> list[CharacterPart]:
    """Each leg in two segments: the thigh turns about the hip (under the body), the shin about
    the knee half-way down; the foot's sole is at the ground."""
    p = f.p
    x = 0.07 * p.body_width / 0.4
    hip, foot = p.leg_length - LIMB_WIDTH / 2, LIMB_WIDTH / 2
    knee = (hip + foot) / 2
    parts = []
    for name, side in (("leg_left", 1.0), ("leg_right", -1.0)):
        parts.append(CharacterPart(name, {"default": VGroup(_segment(side * x, hip, knee, c["clothes"], c, w))}, (side * x, hip)))
        shin = VGroup(_segment(side * x, knee, foot, c["clothes"], c, w))
        parts.append(CharacterPart(f"{name}_lower", {"default": shin}, (side * x, knee), end=(side * x, 0.0)))
    return parts


def _arm(name: str, side: float, f: _Frame, c: Mapping[str, str], w: float) -> list[CharacterPart]:
    """An arm in two segments: the upper sleeve turns about the shoulder, the forearm (sleeve and
    hand) about the elbow half-way down; its end is the hand's middle."""
    p = f.p
    x, shoulder_y = side * p.body_width / 2, f.body_top - 0.08
    top, wrist = shoulder_y + 0.02 - LIMB_WIDTH / 2, shoulder_y + 0.02 - p.arm_length
    elbow = (top + wrist) / 2
    upper = VGroup(_segment(x, top, elbow, c["clothes"], c, w))
    hand = _outlined(Circle(radius=0.045).move_to([x, wrist, 0]), c["skin"], c["outline"], w)
    lower = VGroup(_segment(x, elbow, wrist, c["clothes"], c, w), hand)
    return [
        CharacterPart(name, {"default": upper}, (x, shoulder_y)),
        CharacterPart(f"{name}_lower", {"default": lower}, (x, elbow), end=(x, wrist)),
    ]


def _hair_cap(look: CharacterLook, f: _Frame) -> Polygon:
    """The hair over the top of the head: an arc (zigzag for ``spiky``) and a fringe above the eyes."""
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    radii = [1.35 * r if k % 2 else 1.0 * r for k in range(19)] if look.hair == "spiky" else [1.06 * r] * 25
    outer = _arc_points(cx, cy, radii, -10, 190)
    fringe = [(-0.92, -0.15), (-0.7, 0.45), (-0.3, 0.62), (0.05, 0.55), (0.45, 0.7), (0.85, 0.4), (0.98, -0.05)]
    if f.front:   # symmetric: parted in the middle
        fringe = [(-0.97, -0.1), (-0.75, 0.42), (-0.35, 0.62), (0.0, 0.5), (0.35, 0.62), (0.75, 0.42), (0.97, -0.1)]
    return _polygon([*outer, *((cx + a * r, cy + b * r) for a, b in fringe)])


def _hair_back(look: CharacterLook, f: _Frame) -> list[VMobject]:
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    if look.hair == "long":
        top = _arc_points(cx, cy, [1.1 * r] * 25, 0, 180)
        ends = [(-1.12, -1.28), (0.0, -1.38), (1.12, -1.28)] if f.front else [(-1.15, -1.3), (-0.5, -1.4), (1.05, -1.25)]
        hair = _polygon([*top, *((cx + a * r, cy + b * r) for a, b in ends)])
        return [_trailing(hair, (cx, cy + 0.4 * r), "long")]
    if look.hair == "bun":
        bun_x = cx if f.front else cx - 0.15 * r
        return [_trailing(Circle(radius=0.38 * r).move_to([bun_x, cy + 1.18 * r, 0]), (bun_x, cy + 0.85 * r), "bun")]
    if look.hair == "curly":
        return [Circle(radius=0.32 * r).move_to([x, y, 0]) for x, y in _arc_points(cx, cy, [0.95 * r] * 12, -20, 200)]
    return []


def _ears(look: CharacterLook, f: _Frame) -> list[VMobject]:
    r, cx, cy = f.p.head_radius, f.head_x, f.head_y
    if look.ears == "round":
        return [Circle(radius=0.28 * r).move_to([cx + side * 0.98 * r, cy, 0]) for side in (-1, 1)]
    if look.ears == "pointy":
        return [
            _trailing(_polygon([_at(cx, cy, 0.9 * r, tip - 15), _at(cx, cy, 1.55 * r, tip), _at(cx, cy, 0.9 * r, tip + 15)]), _at(cx, cy, 0.9 * r, tip), "pointy")
            for tip in (65, 115)
        ]
    if look.ears == "floppy":
        return [
            _trailing(Ellipse(width=0.4 * r, height=0.95 * r).move_to([cx + side * 1.0 * r, cy - 0.2 * r, 0]).rotate(side * 0.25), (cx + side * 1.0 * r, cy + 0.2 * r), "floppy")
            for side in (-1, 1)
        ]
    return []


def _nose(look: CharacterLook, f: _Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    r, y = f.p.head_radius, f.head_y - 0.1 * f.p.head_radius
    x = f.face_x + (0.0 if f.front else 0.05 * r)
    if look.nose == "dot":
        return [_filled(Ellipse(width=0.12 * r, height=0.09 * r).move_to([x, y, 0]), c["features"])]
    if look.nose == "round":
        return [_outlined(Circle(radius=0.1 * r).move_to([x, y, 0]), c["skin"], c["outline"], w)]
    if look.nose == "triangle":
        corners = [(x, y + 0.11 * r), (x + 0.1 * r, y - 0.09 * r), (x - 0.1 * r, y - 0.09 * r)] if f.front else \
            [(x - 0.04 * r, y + 0.11 * r), (x + 0.24 * r, y - 0.09 * r), (x - 0.04 * r, y - 0.09 * r)]
        return [_outlined(_polygon(corners), c["skin"], c["outline"], w)]
    return []


def _head(look: CharacterLook, f: _Frame, c: Mapping[str, str], w: float) -> VGroup:
    """Back hair, ears, the head, the hair cap and the nose (all move with the head)."""
    group = VGroup(*(_outlined(m, c["hair"], c["outline"], w) for m in _hair_back(look, f)))
    group.add(*(_outlined(m, c["skin"], c["outline"], w) for m in _ears(look, f)))
    group.add(_outlined(Circle(radius=f.p.head_radius).move_to([f.head_x, f.head_y, 0]), c["skin"], c["outline"], w))
    if look.hair != "none":
        group.add(_outlined(_hair_cap(look, f), c["hair"], c["outline"], w))
    group.add(*_nose(look, f, c, w))
    return group


def _eye_size(look: CharacterLook, f: _Frame) -> tuple[float, float]:
    """(width, height) of one open eye."""
    r = f.p.head_radius * f.p.eye_size
    return {"dot": (0.25 * r, 0.375 * r), "oval": (0.3 * r, 0.45 * r), "round": (0.4 * r, 0.4 * r), "sleepy": (0.3 * r, 0.2 * r)}[look.eyes]


def _eye_xs(f: _Frame) -> tuple[float, float]:
    return f.face_x - f.p.eye_gap, f.face_x + f.p.eye_gap


def _open_eye(look: CharacterLook, x: float, f: _Frame, c: Mapping[str, str], w: float) -> VGroup:
    width, height = _eye_size(look, f)
    y, look_x = f.eye_y, 0.0 if f.front else 0.15 * width  # pupils look a little to the right (from the front: ahead)
    if look.eyes == "dot":
        return VGroup(_filled(Ellipse(width=width, height=height).move_to([x, y, 0]), c["features"]))
    if look.eyes == "sleepy":
        lower = _arc_points(x, y, [width / 2] * 13, 180, 360)
        half = _polygon([(px, y + (py - y) * 2 * height / width) for px, py in lower])
        lid = Line([x - width * 0.65, y + 0.01, 0], [x + width * 0.65, y + 0.01, 0]).set_stroke(c["features"], width=w)
        return VGroup(_filled(half, c["features"]), lid)
    white = Ellipse(width=width, height=height) if look.eyes == "oval" else Circle(radius=width / 2)
    pupil = Ellipse(width=width * 0.45, height=height * 0.45).move_to([x + look_x, y - 0.05 * height, 0])
    return VGroup(_outlined(white.move_to([x, y, 0]), EYE_WHITE, c["outline"], w * 0.75), _filled(pupil, c["features"]))


def _face(look: CharacterLook, f: _Frame, c: Mapping[str, str], w: float) -> list[CharacterPart]:
    """Eyes (``open`` / ``closed``), brows (``default`` / ``angry`` / ``sad``) and mouth (``smile`` /
    ``open`` and the viseme shapes ``A E O U M F L W``)."""
    r, fx = f.p.head_radius, f.face_x
    width, height = _eye_size(look, f)
    xs = _eye_xs(f)
    open_eyes = VGroup(*(_open_eye(look, x, f, c, w) for x in xs))
    closed_y = f.eye_y - (0 if look.eyes == "sleepy" else 0.025 * r)
    closed_eyes = VGroup(*(Line([x - width * 0.6, closed_y, 0], [x + width * 0.6, closed_y, 0]).set_stroke(c["features"], width=w) for x in xs))
    brow_y = f.eye_y + height / 2 + 0.16 * r

    def brows(back_left: float, back_right: float, front_left: float, front_right: float) -> VGroup:
        """Two brow lines; the arguments are each end's height (× r) above ``brow_y``."""
        ends = ((back_left, back_right), (front_left, front_right))
        return VGroup(*(
            Line([x - 0.175 * r, brow_y + left * r, 0], [x + 0.175 * r, brow_y + right * r, 0]).set_stroke(c["features"], width=w)
            for x, (left, right) in zip(xs, ends)
        ))

    mouth_r = 0.3 * r * f.p.mouth_width
    mouth_y = f.head_y - 0.45 * r
    smile = Arc(radius=mouth_r, start_angle=PI * 1.2, angle=PI * 0.6, arc_center=[fx, f.head_y - 0.2 * r, 0]).set_stroke(c["features"], width=w)

    def opening(width: float, height: float) -> VMobject:
        """A filled mouth opening, ``width`` × the mouth radius by ``height`` × the head radius."""
        return _filled(Ellipse(width=width * mouth_r, height=height * r).move_to([fx, mouth_y, 0]), c["features"])

    closed = Line([fx - 0.75 * mouth_r, mouth_y + 0.03 * r, 0], [fx + 0.75 * mouth_r, mouth_y + 0.03 * r, 0]).set_stroke(c["features"], width=w)
    # viseme shapes (DESIGN.md §69.4): A open, E wide, O round, U small round, M closed lips,
    # F a thin line (lip under the teeth), L open, W puckered
    speech = {
        "A": opening(1.6, 0.42), "E": opening(1.8, 0.18), "O": opening(0.95, 0.36), "U": opening(0.6, 0.24),
        "M": closed, "F": opening(1.3, 0.08), "L": opening(1.2, 0.28), "W": opening(0.45, 0.18),
    }
    return [
        CharacterPart("eyes", {"open": open_eyes, "closed": closed_eyes}, (fx, f.eye_y)),
        # angry: the inner ends (toward the face's middle) low; sad: the inner ends high
        CharacterPart("brows", {
            "default": brows(-0.025, 0.025, -0.025, 0.025),
            "angry": brows(0.05, -0.07, -0.07, 0.05),
            "sad": brows(-0.05, 0.07, 0.07, -0.05),
        }, (fx, brow_y)),
        CharacterPart("mouth", {"smile": smile, "open": opening(1.5, 0.35), **speech}, (fx, f.head_y - 0.4 * r)),
    ]


def _worn_on_head(look: CharacterLook, f: _Frame, c: Mapping[str, str], w: float) -> VGroup:
    """Glasses and hat (the ``accessory`` part)."""
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
        band = _polygon([(cx - 0.7 * r, brim_y + 0.06 * r), (cx + 0.7 * r, brim_y + 0.06 * r), (cx + 0.7 * r, brim_y + 0.22 * r), (cx - 0.7 * r, brim_y + 0.22 * r)])
        brim = RoundedRectangle(width=2.5 * r, height=0.16 * r, corner_radius=0.07 * r).move_to([cx, brim_y, 0])
        hat = (_outlined(crown, c["accessory"], c["outline"], w), _outlined(band, c["clothes"], c["outline"], w), _outlined(brim, c["accessory"], c["outline"], w))
        group.add(*(_trailing(piece, (cx, brim_y), "hat") for piece in hat))
    return group


def generate_parts(
    look: CharacterLook, colors: Mapping[str, str], *, outline_width: float = OUTLINE_WIDTH, front: bool = False,
) -> list[CharacterPart]:
    """The parts of the figure ``look`` describes, in character units with its top at 1.
    ``colors`` maps every key of :data:`COLOR_KEYS` to a Manim colour; ``outline_width`` is the
    stroke width of outlines and feature lines (the :class:`Character` scales it with its height);
    ``front``: its front view, the same parts and shapes seen from the front (DESIGN.md §69.44).
    The same look always gives the same shapes."""
    f = _Frame.of(resolve_proportions(look), front)
    w = outline_width
    parts = [
        *_legs(f, colors, w),
        CharacterPart("body", {"default": _body(look, f, colors, w)}, (0.0, f.body_bottom + 0.02)),
        *_arm("arm_left", 1.0, f, colors, w),
        *_arm("arm_right", -1.0, f, colors, w),
        CharacterPart("head", {"default": _head(look, f, colors, w)}, (0.0, f.body_top - 0.02)),
        *_face(look, f, colors, w),
    ]
    worn = _worn_on_head(look, f, colors, w)
    if worn.submobjects:
        parts.append(CharacterPart("accessory", {"default": worn}, (f.head_x, f.head_y)))
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


__all__ = ["BODY_SIZES", "COLOR_KEYS", "EYE_WHITE", "LIMB_WIDTH", "TRAIL_WEIGHTS", "Proportions", "generate_parts", "resolve_proportions"]
