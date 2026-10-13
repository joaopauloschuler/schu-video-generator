"""What generated characters wear on the body (DESIGN.md §69.1, §69.47): the outfit
(``plain``, ``dress``, ``overalls``, ``coat``, ``shorts``, ``apron``), its pattern (stripes or
dots in a tone of the cloth), shoes, and the accessories worn on the body (scarf, bag, backpack,
necklace). Character units before the figure is scaled to height 1, as in
:mod:`vidgen.cartoon.generator`, which calls these.

Clothes follow the parts they are on: sleeves are the arm segments, trouser legs the leg
segments (a shorts' thighs, bare shins), shoes the shins. A dress's skirt and a coat's tails
hang from the ``body`` part, not from the legs, so the legs walk under them; the body of such an
outfit has a second shape, ``seated`` (:data:`~vidgen.config.SEATED_BODY_SHAPE`), in which the
cloth lies over the lap, shown while the character sits.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from manim import BLACK, WHITE, Circle, Line, ManimColor, RoundedRectangle, VGroup, VMobject, interpolate_color

from vidgen.cartoon.primitives import (
    Point,
    arc_points,
    clip_to_box,
    dot_centres,
    filled,
    outline_polygon,
    outlined,
    polygon,
    span_at,
    trailing,
)
from vidgen.config import SEATED_BODY_SHAPE, SKIRTED_OUTFITS, CharacterLook
from vidgen.lint.color import hex_rgb, relative_luminance

if TYPE_CHECKING:
    from vidgen.cartoon.generator import Frame

#: Width of a sleeve or a leg; its ends are round (half this radius), so a bent elbow or knee
#: stays a smooth joint.
LIMB_WIDTH = 0.08
#: Stripes: each band's height and the distance from one band to the next; dots: radius,
#: distance between centres, and the least gap to the cloth's edge.
STRIPE_HEIGHT, STRIPE_PERIOD = 0.03, 0.065
DOT_RADIUS, DOT_SPACING, DOT_MARGIN = 0.017, 0.06, 0.008
#: How far a pattern's tone goes from the cloth's colour: towards black on a light cloth, towards
#: white on a dark one (relative luminance above / below :data:`LIGHT_CLOTH`).
PATTERN_SHADE, PATTERN_LIGHT, LIGHT_CLOTH = 0.28, 0.4, 0.35
#: How far a skirt (and less, coat tails) flares out at the hem beyond the body's width.
SKIRT_FLARE = {"dress": 0.07, "coat": 0.02}
#: The cloth over a seated character's lap: from the hips, between these directions (degrees from
#: forward, + up), out to the knee plus :data:`LAP_OVERHANG`.
LAP_UP_DEGREES, LAP_DOWN_DEGREES, LAP_OVERHANG = 15.0, -50.0, 0.045


def pattern_tone(color: str) -> str:
    """The colour stripes and dots are drawn in on cloth of ``color``: darker on a light cloth,
    lighter on a dark one."""
    hexed = ManimColor(color).to_hex()
    light = relative_luminance(hex_rgb(hexed)) > LIGHT_CLOTH
    return interpolate_color(ManimColor(hexed), BLACK if light else WHITE, PATTERN_SHADE if light else PATTERN_LIGHT).to_hex()


def _pattern(points: Sequence[Point], kind: str, color: str) -> list[VMobject]:
    """``kind`` (``stripes`` / ``dots``) inside the polygon ``points`` in the tone of ``color``."""
    tone = pattern_tone(color)
    if kind == "stripes":
        top = max(p[1] for p in points)
        bottom = min(p[1] for p in points)
        bands = []
        y = top - STRIPE_PERIOD / 2
        while y - STRIPE_HEIGHT > bottom:
            band = clip_to_box(points, bottom=y - STRIPE_HEIGHT, top=y)
            if band:
                bands.append(filled(polygon(band), tone))
            y -= STRIPE_PERIOD
        return bands
    if kind == "dots":
        return [filled(Circle(radius=DOT_RADIUS).move_to([x, y, 0]), tone) for x, y in dot_centres(points, DOT_SPACING, DOT_RADIUS, DOT_MARGIN)]
    return []


def _cloth(shape: VMobject, look: CharacterLook, color: str, c: Mapping[str, str], w: float) -> list[VMobject]:
    """``shape`` as cloth of ``color``: filled and outlined, with the look's pattern on it (the
    outline drawn again over the pattern)."""
    if look.pattern == "none":
        return [outlined(shape, color, c["outline"], w)]
    points = outline_polygon(shape)
    edge = shape.copy().set_fill(opacity=0).set_stroke(c["outline"], width=w)
    return [outlined(shape, color, c["outline"], w), *_pattern(points, look.pattern, color), edge]


def limb_colors(look: CharacterLook, c: Mapping[str, str]) -> tuple[str, str, str, str]:
    """The colours of the upper arm, forearm (sleeves, or bare), thigh and shin (trouser legs, or
    bare) of the ``look``'s outfit."""
    clothes, trim, skin = c["clothes"], c.get("trim", c["clothes"]), c["skin"]
    return {
        "plain": (clothes, clothes, clothes, clothes),
        "apron": (clothes, clothes, clothes, clothes),
        "dress": (clothes, skin, skin, skin),
        "overalls": (trim, trim, clothes, clothes),
        "coat": (clothes, clothes, trim, trim),
        "shorts": (clothes, skin, trim, skin),
    }[look.outfit]


def shoe(look: CharacterLook, x: float, front: bool, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A shoe or boot (``look.shoes``) on the foot whose sole's middle is at (``x``, 0): the toe
    forward (from the front: centred); the sole on the ground."""
    if look.shoes == "none":
        return []
    half = LIMB_WIDTH / 2 + 0.006
    shaft = 0.11 if look.shoes == "boots" else 0.0
    if front:
        dome = [(x + 0.055 * math.cos(t), 0.045 * math.sin(t)) for t in (math.pi * k / 12 for k in range(13))]
        pieces = [polygon(dome)]
        if shaft:
            pieces.insert(0, polygon([(x + half, 0.0), (x + half, shaft), (x - half, shaft), (x - half, 0.0)]))
    else:
        toe = arc_points(x + 0.04, 0.0, [0.032] * 7, 0, 90)
        top = [(x + 0.005, 0.05), (x - 0.045, 0.046)] if not shaft else [(x + half, 0.05), (x + half, shaft), (x - half, shaft)]
        pieces = [polygon([(x - 0.047, 0.0), (x + 0.072, 0.0), *toe[1:], *top])]
    return [outlined(piece, c["accessory"], c["outline"], w) for piece in pieces]


def _skirt(look: CharacterLook, f: Frame, body: Sequence[Point], *, seated: bool) -> VMobject | None:
    """A dress's skirt or a coat's tails from just above the body's bottom: hanging to the knee,
    or (``seated``) over the lap: from the hips forward past the knee (side view; from the front,
    shorter and wider)."""
    if look.outfit not in SKIRTED_OUTFITS:
        return None
    waist = f.body_bottom + 0.06
    span = span_at(body, waist) or (-f.p.body_width / 2, f.p.body_width / 2)
    left, right = span
    hip, foot = f.p.leg_length - LIMB_WIDTH / 2, LIMB_WIDTH / 2
    knee = (hip + foot) / 2
    flare = SKIRT_FLARE[look.outfit]
    if seated and not f.front:
        reach = hip - knee + LAP_OVERHANG
        lap = arc_points(0.0, hip, [reach] * 9, LAP_DOWN_DEGREES, LAP_UP_DEGREES)
        return polygon([(left, waist), (left * 0.95, hip - 0.035), *lap, (right, waist)])
    hem = (hip - 0.02) if seated else (knee - 0.005)
    if seated:
        flare *= 2.0
    curve = [(left - flare + (right - left + 2 * flare) * k / 8, hem - 0.012 * math.sin(math.pi * k / 8)) for k in range(9)]
    return polygon([(left, waist), *curve, (right, waist)])


def _apron(f: Frame, body: Sequence[Point]) -> list[Point]:
    """An apron's outline: from the chest down the front of the body (side view: its front half;
    front view: the middle) to a straight hem below the body."""
    p = f.p
    top, bottom, hem = f.body_top - 0.12, f.body_bottom + 0.01, f.body_bottom - 0.05
    wide = 0.3 * p.body_width
    lefts, rights = [], []
    for k in range(9):
        y = top + (bottom - top) * k / 8
        span = span_at(body, y) or (-p.body_width / 2, p.body_width / 2)
        if f.front:
            lefts.append((max(-wide, 0.85 * span[0]), y))
            rights.append((min(wide, 0.85 * span[1]), y))
        else:
            lefts.append((0.0, y))
            rights.append((span[1] + 0.005, y))
    return [*rights, (rights[-1][0], hem), (lefts[-1][0], hem), *reversed(lefts)]


def _outfit_details(look: CharacterLook, f: Frame, body: Sequence[Point], c: Mapping[str, str], w: float) -> list[VMobject]:
    """What the outfit adds over the top: the overalls' trousers and bib, the shorts' waistband,
    the apron, the coat's closure, buttons and collar."""
    p = f.p
    trim, clothes, outline = c.get("trim", c["clothes"]), c["clothes"], c["outline"]

    def button(x: float, y: float) -> VMobject:
        return outlined(Circle(radius=0.012).move_to([x, y, 0]), c["accessory"], outline, w * 0.75)

    if look.outfit == "overalls":
        waist = f.body_bottom + 0.4 * p.body_height
        bib_top = f.body_top - 0.1
        bib_left, bib_right = (-0.28 * p.body_width, 0.28 * p.body_width) if f.front else (-0.1 * p.body_width, math.inf)
        pieces = [outlined(polygon(clip_to_box(body, top=waist)), clothes, outline, w)]
        bib = clip_to_box(body, left=bib_left, right=bib_right, bottom=waist - 0.01, top=bib_top)
        pieces.append(outlined(polygon(bib), clothes, outline, w))
        corners = [min(x for x, _ in bib), max(x for x, _ in bib)] if f.front else [max(min(x for x, _ in bib), 0.0)]
        shoulders = [-0.32 * p.body_width, 0.32 * p.body_width] if f.front else [-0.2 * p.body_width]
        for corner, shoulder in zip(corners, shoulders):
            inset = 0.02 if corner < 0 or not f.front else -0.02
            pieces.append(Line([corner + inset, bib_top - 0.01, 0], [shoulder, f.body_top - 0.005, 0]).set_stroke(clothes, width=w * 2.2))
            pieces.append(button(corner + inset, bib_top - 0.025))
        return pieces
    if look.outfit == "shorts":
        return [outlined(polygon(clip_to_box(body, top=f.body_bottom + 0.05)), trim, outline, w)]
    if look.outfit == "apron":
        apron = _apron(f, body)
        pieces = [outlined(polygon(apron), trim, outline, w)]
        top_y = apron[0][1]
        neck = [(-0.06, f.body_top), (0.06, f.body_top)] if f.front else [(-0.03, f.body_top)]
        corners = [apron[-1][0] + 0.015, apron[0][0] - 0.015] if f.front else [apron[-1][0] + 0.015]
        for corner, (nx, ny) in zip(corners, neck):
            pieces.append(Line([corner, top_y, 0], [nx, ny, 0]).set_stroke(trim, width=w * 1.6))
        if f.front:
            pocket = RoundedRectangle(width=0.12, height=0.07, corner_radius=0.015).move_to([0, f.body_bottom + 0.06, 0])
            pieces.append(outlined(pocket, trim, outline, w * 0.75))
        return pieces
    if look.outfit == "coat":
        x = 0.0 if f.front else 0.3 * p.body_width
        pieces: list[VMobject] = [Line([x, f.body_top - 0.04, 0], [x, f.body_bottom + 0.03, 0]).set_stroke(outline, width=w * 0.75)]
        pieces += [button(x + (0.03 if f.front else 0.025), f.body_top - 0.1 - k * 0.09 * p.body_height / 0.44) for k in range(3)]
        sides = (-1.0, 1.0) if f.front else (1.0,)
        for side in sides:
            base = x if f.front else x - 0.02
            lapel = [(base, f.body_top - 0.12), (base + side * 0.09, f.body_top - 0.005), (base + side * 0.02, f.body_top + 0.005)]
            pieces.append(outlined(polygon(lapel), clothes, outline, w * 0.75))
        return pieces
    return []


def _necklace(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """Beads round the neck and a pendant (which trails in the wind) at the front."""
    x0, y0 = (0.0, f.body_top) if f.front else (0.04, f.body_top)
    width = 0.09 if f.front else 0.06
    beads = [(x0 + width * math.cos(t), y0 + 0.085 * math.sin(t)) for t in (math.radians(200 + 140 * k / 8) for k in range(9))]
    pieces = [outlined(Circle(radius=0.012).move_to([x, y, 0]), c["accessory"], c["outline"], w * 0.6) for x, y in beads]
    low = min(beads, key=lambda b: b[1]) if f.front else max(beads, key=lambda b: b[0] - b[1])
    pendant = Circle(radius=0.022).move_to([low[0], low[1] - 0.026, 0])
    pieces.append(trailing(outlined(pendant, c["accessory"], c["outline"], w * 0.75), (low[0], low[1] - 0.004), "pendant"))
    return pieces


def _backpack(f: Frame, body: Sequence[Point], c: Mapping[str, str], w: float, *, straps: bool) -> list[VMobject]:
    """A backpack: (side view, ``straps`` false) the pack behind the back; (``straps`` true) the
    straps over the shoulders."""
    p = f.p
    middle = f.body_bottom + 0.55 * p.body_height
    back = (span_at(body, middle) or (-p.body_width / 2, 0.0))[0]
    if not straps:
        if f.front:
            return []
        pack = RoundedRectangle(width=0.13, height=0.55 * p.body_height, corner_radius=0.04).move_to([back - 0.035, middle, 0])
        flap = Line([back - 0.095, middle + 0.12 * p.body_height, 0], [back + 0.02, middle + 0.12 * p.body_height, 0]).set_stroke(c["outline"], width=w)
        return [outlined(pack, c["accessory"], c["outline"], w), flap]
    if f.front:
        return [
            Line([side * 0.3 * p.body_width, f.body_top - 0.01, 0], [side * 0.3 * p.body_width, f.body_top - 0.5 * p.body_height, 0])
            .set_stroke(c["accessory"], width=w * 2.2)
            for side in (-1.0, 1.0)
        ]
    return [Line([-0.12 * p.body_width, f.body_top - 0.01, 0], [0.12 * p.body_width, f.body_top - 0.3 * p.body_height, 0]).set_stroke(c["accessory"], width=w * 2.2)]


def _bag_and_scarf(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A bag on a strap and a scarf with a trailing end (DESIGN.md §69.1, §69.32)."""
    p = f.p
    pieces: list[VMobject] = []
    if "bag" in look.accessories:
        bag_x, bag_y = -p.body_width * 0.42, f.body_bottom + p.body_height * 0.3
        strap = Line([p.body_width * 0.28, f.body_top - 0.04, 0], [bag_x, bag_y + 0.05, 0]).set_stroke(c["accessory"], width=w * 1.8)
        bag = outlined(RoundedRectangle(width=0.16, height=0.12, corner_radius=0.03).move_to([bag_x, bag_y, 0]), c["accessory"], c["outline"], w)
        flap = Line([bag_x - 0.08, bag_y + 0.025, 0], [bag_x + 0.08, bag_y + 0.025, 0]).set_stroke(c["outline"], width=w)
        pieces += [strap, bag, flap]
    if "scarf" in look.accessories:
        band_w = min(p.body_width, 0.36) * 0.85
        band = RoundedRectangle(width=band_w, height=0.08, corner_radius=0.035).move_to([0, f.body_top - 0.03, 0])
        tail = RoundedRectangle(width=0.07, height=0.17, corner_radius=0.03).move_to([-band_w * 0.25, f.body_top - 0.12, 0]).rotate(-0.2)
        tail = trailing(tail, (-band_w * 0.25, f.body_top - 0.05), "scarf")
        pieces += [outlined(tail, c["accessory"], c["outline"], w), outlined(band, c["accessory"], c["outline"], w)]
    return pieces


def body_shapes(look: CharacterLook, f: Frame, shape: VMobject, c: Mapping[str, str], w: float) -> dict[str, VGroup]:
    """The ``body`` part's shapes: ``default``, and ``seated`` for an outfit with a skirt or
    tails (:data:`~vidgen.config.SKIRTED_OUTFITS`). ``shape`` is the bare body's outline; on it
    go the outfit's top (the shirt under overalls is ``trim``), its pattern and details, the
    necklace, the backpack, the bag and the scarf. A plain outfit without a pattern, backpack or
    necklace is drawn as before Step 113."""
    top = c.get("trim", c["clothes"]) if look.outfit == "overalls" else c["clothes"]
    plain = look.outfit == "plain" and look.pattern == "none" and not {"backpack", "necklace"} & set(look.accessories)
    if plain:
        return {"default": VGroup(outlined(shape, top, c["outline"], w), *_bag_and_scarf(look, f, c, w))}
    body = outline_polygon(shape)
    worn = [*_outfit_details(look, f, body, c, w)]
    if "necklace" in look.accessories:
        worn += _necklace(f, c, w)
    if "backpack" in look.accessories:
        worn += _backpack(f, body, c, w, straps=True)
    worn += _bag_and_scarf(look, f, c, w)
    behind = _backpack(f, body, c, w, straps=False) if "backpack" in look.accessories else []
    names = ["default", SEATED_BODY_SHAPE] if look.outfit in SKIRTED_OUTFITS else ["default"]
    shapes = {}
    for name in names:
        skirt = _skirt(look, f, body, seated=name == SEATED_BODY_SHAPE)
        cloth = [] if skirt is None else _cloth(skirt, look, c["clothes"], c, w)
        made = [*behind, *cloth, *_cloth(shape.copy(), look, top, c, w), *worn]
        shapes[name] = VGroup(*(m.copy() for m in made)) if name != names[0] else VGroup(*made)
    return shapes


__all__ = ["LIMB_WIDTH", "body_shapes", "limb_colors", "pattern_tone", "shoe"]
