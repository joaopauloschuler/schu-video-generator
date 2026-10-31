"""Seasons, harbour and travel iso objects (DESIGN.md §104, Phase AC Step 267): a Christmas tree,
a snowman, a pumpkin, a pile of gifts, a bunch of balloons, a birthday cake, a sailing boat on
water, a dock, a lighthouse, a train car and a rocket on its launch pad. No manim.

Drawn like :mod:`vidgen.cartoon.iso_objects`' objects (its frame, shading and helpers), which
looks each kind of this module up in :data:`DRAWINGS` and its moving parts in :func:`motion`.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from vidgen.cartoon.iso_drawing import Disc, Line, Poly, Shape, Upright, mix, shade
from vidgen.cartoon.iso_home import EMBER, FIRE_ORANGE, FIRE_YELLOW, _flame, _flicker
from vidgen.cartoon.iso_nature import _hull
from vidgen.cartoon.iso_objects import (
    CASING,
    GLASS,
    LIT_CORE,
    LIT_GLASS,
    PINE_SNOW_CAP,
    SHINE,
    Motion,
    ObjectLook,
    _arc,
    _face_circle,
    _fade,
    _Frame,
    _profile,
    _ribbon,
    _rising,
    _round,
    _screen,
    _stripes,
    light_pool,
)
from vidgen.cartoon.iso_scenery import WATER_DEPTH
from vidgen.cartoon.iso_shop import _rect
from vidgen.cartoon.iso_town import TYRE, _side_rect
from vidgen.world.iso import ObjectState
from vidgen.world.iso_view import Point3

#: A Christmas tree's tiers (bottom, top, half width as a pine's), its baubles' and lights'
#: colours, and how long a light takes to twinkle (seconds).
TREE_TIERS = ((0.4, 1.6, 0.7), (1.1, 2.25, 0.56), (1.75, 2.85, 0.4))
BAUBLES = ("#E2574C", "#4C8DD6", "#F2A7C3", "#F2C14E")
TREE_LIGHTS = ("#FF5A5A", "#FFD75E", "#5FD8FF", "#7CFF8A")
TWINKLE_SECONDS = 1.7
#: Snow, and its shade.
SNOW = "#F4F8FC"
SNOW_SHADE = "#D6E0EC"
CARROT = "#F28A2E"
COAL = "#2B2F3A"
TWIG = "#7A5236"
#: A pumpkin's carved face when dark.
CARVED = "#5A2A10"
#: Wrapping paper of a pile of gifts besides its own colour.
PAPERS = ("#4C8DD6", "#5BA35B", "#F2A7C3")
#: A bunch of balloons: each (across, up the picture from the weight, radius; tile widths), the
#: colours after its own and how long a sway takes (seconds).
BALLOONS = ((0.04, 1.46, 0.16), (-0.21, 1.24, 0.15), (0.26, 1.2, 0.15), (-0.07, 1.03, 0.14), (0.16, 0.95, 0.13))
BALLOON_COLORS = ("#F6C945", "#4C8DD6", "#5BA35B", "#C77DFF")
SWAY_SECONDS = 3.4
#: A birthday cake's candles' colours.
CANDLES = ("#4C8DD6", "#F6C945", "#5BA35B", "#E2574C")
#: A boat: how long its bob takes (seconds), how far it rises (tile units), pitches and rolls.
BOB_SECONDS = 2.8
BOB = (0.03, 0.02, 0.025)
FOAM = "#E4F3FB"
SAIL_WOOD = "#7A5236"
DECK = "#C69466"
#: A lighthouse's lantern (its middle's height, its glass's radius), how long its beam takes
#: to sweep round (seconds) and how far it reaches (tile units).
LANTERN = (4.6, 0.19)
SWEEP_SECONDS = 6.0
BEAM_REACH = 3.2
BEAM = "#FFF1B8"
TOWER_WHITE = "#F4F6FA"
STONE = "#B9B4AA"
#: A rocket: its body's radius and its nozzle's bottom; its launch pad's concrete; its smoke.
ROCKET_RADIUS = 0.3
NOZZLE = 0.45
CONCRETE = "#A3A8B0"
SMOKE = "#E9ECF1"
SMOKE_PUFFS = 6
SMOKE_SECONDS = 2.2


def _middle(f: _Frame) -> Point3:
    return f.p(f.width / 2, f.depth / 2, 0.0)


def _band(x: float, y: float, z0: float, z1: float, r0: float, r1: float, fill: str, glow: bool = False) -> list[Shape]:
    """A band of a round tower (or a cone, ``r1`` 0) from radius ``r0`` at ``z0`` to ``r1`` at
    ``z1``: its front half, its right quarter in shade."""
    def arc(r: float, z: float, start: float, end: float) -> list[Point3]:
        return [(x + r * math.cos(t), y + r * math.sin(t), z) for t in [start + (end - start) * k / 16 for k in range(17)]]

    front = arc(r0, z0, -math.pi / 4, 3 * math.pi / 4) + arc(r1, z1, 3 * math.pi / 4, -math.pi / 4)
    right = arc(r0, z0, -math.pi / 4, math.pi / 6) + arc(r1, z1, math.pi / 6, -math.pi / 4)
    return [Poly(tuple(front), shade(fill, 0.06), True, glow), Poly(tuple(right), shade(fill, 0.2), False, glow)]


def _star(centre: Point3, radius: float, fill: str, glow: bool = False, ink: bool = True) -> Poly:
    """A five-pointed star facing the viewer round ``centre`` (``radius`` in tile widths)."""
    return Poly(tuple(_screen(centre, (radius if k % 2 == 0 else radius * 0.42) * math.sin(math.pi * k / 5),
                              (radius if k % 2 == 0 else radius * 0.42) * math.cos(math.pi * k / 5)) for k in range(10)), fill, ink, glow)


# ----- seasons: a Christmas tree, a snowman, a pumpkin ---------------------------------------------------------


def _tier_point(f: _Frame, tier: int, s: float, lift: float) -> Point3:
    """A point on a Christmas tree's ``tier``: ``s`` across it (0 left .. 1 right), ``lift`` up it."""
    bottom, top, half = TREE_TIERS[tier]
    z = bottom + lift * (top - bottom)
    return f.across(0.5, 0.5, z, (2 * s - 1) * half * (1 - lift) * 0.82)


def _tree_lights(f: _Frame) -> list[tuple[int, Point3, str]]:
    """A Christmas tree's lights: (its tier, where, its colour), along a garland round each tier."""
    found = []
    for tier in range(len(TREE_TIERS)):
        count = 5 - tier
        for k in range(count):
            s = (k + 0.5) / count
            found.append((tier, _tier_point(f, tier, s, 0.12 + 0.32 * s), TREE_LIGHTS[(k + tier) % len(TREE_LIGHTS)]))
    return found


def _christmas_tree(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A fir tree (``color``) in a red pot: three tiers hung with baubles and a garland of
    lights, a star (``detail``) on top; on, the lights and the star shine (the stage makes them
    twinkle) and a soft glow pools round it."""
    x, y, z = _middle(f)
    on = state.on
    leaves = mix(look.main, "#1F5A3A", 0.2)
    shapes: list[Shape] = light_pool((x, y, z + 0.01), 1.0, 0.6) if on else []
    shapes += [Upright(x, y, z, z + 0.3, 0.2, "#B0303A"), Upright(x, y, z + 0.26, z + 0.34, 0.23, mix("#B0303A", SHINE, 0.15)),
               Upright(x, y, z + 0.34, z + 0.55, 0.07, "#7A5236")]
    lights = _tree_lights(f)
    for tier, (bottom, top, half) in enumerate(TREE_TIERS):
        shapes.append(Poly((f.across(0.5, 0.5, bottom, -half), f.across(0.5, 0.5, bottom, half), f.across(0.5, 0.5, top, 0.0)),
                           shade(leaves, 0.06 * (2 - tier)), snow_cap=PINE_SNOW_CAP))
        shapes.append(Poly((f.across(0.5, 0.5, bottom + 0.05, -half * 0.75), f.across(0.5, 0.5, bottom + 0.05, -half * 0.35),
                            f.across(0.5, 0.5, top - 0.35, -0.04)), mix(leaves, SHINE, 0.18), False))
        mine = [point for t, point, _ in lights if t == tier]
        shapes.append(Line(tuple(mine), mix(look.detail, SHINE, 0.2), 1.2))   # the garland the lights hang on
        for k, (s, lift) in enumerate(((0.2, 0.5), (0.72, 0.08), (0.55, 0.55))[:3 - tier // 2]):
            ball = _tier_point(f, tier, s, lift)
            color = BAUBLES[(tier * 3 + k) % len(BAUBLES)]
            shapes += [_round(ball, 0.05, color), _round(_screen(ball, -0.015, 0.015), 0.015, SHINE, False)]
        for _, point, color in [light for light in lights if light[0] == tier]:
            shapes.append(_round(point, 0.03, mix(color, SHINE, 0.3) if on else shade(color, 0.35), not on, on, 10))
    tip = f.across(0.5, 0.5, TREE_TIERS[-1][1] + 0.08, 0.0)
    shapes.append(_star(tip, 0.13, mix(look.detail, SHINE, 0.3) if on else look.detail, on))
    return shapes


def _tree_twinkle(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A lit Christmas tree at ``now``: its lights twinkling in turn (a bright spark over each)
    and the glow round its star breathing."""
    parts = []
    for k, (_, point, color) in enumerate(_tree_lights(f)):
        twinkle = max(0.0, math.sin(2 * math.pi * (now / TWINKLE_SECONDS + k * 0.37))) ** 2
        parts.append(Motion(_round(point, 0.035 + 0.025 * twinkle, color, steps=10).points, mix(color, SHINE, 0.65), twinkle, False, True))
    beat = 0.5 - 0.5 * math.cos(2 * math.pi * now / (TWINKLE_SECONDS * 1.6))
    tip = f.across(0.5, 0.5, TREE_TIERS[-1][1] + 0.08, 0.0)
    parts.append(Motion(_star(tip, 0.22 + 0.04 * beat, look.detail).points, mix(look.detail, SHINE, 0.5), 0.15 + 0.25 * beat, False, True, pool=True))
    return parts


def _snowball(centre: Point3, radius: float) -> list[Shape]:
    return [_round(centre, radius, SNOW_SHADE), _round(_screen(centre, -radius * 0.14, radius * 0.12), radius * 0.8, SNOW, False)]


def _snowman(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A snowman of three snowballs on a drift: stick arms, coal buttons, eyes and smile, a
    carrot nose (pointing the way it faces), a scarf (``color``) and a top hat (``detail``)."""
    x, y, z = _middle(f)
    side = 1.0 if f.swap else -1.0
    foot = (x, y, z)
    shapes: list[Shape] = [Disc((x, y, z + 0.01), 0.42, SNOW, True, holds_snow=False)]
    low, mid, head = _screen(foot, 0.0, 0.28), _screen(foot, 0.0, 0.7), _screen(foot, 0.0, 0.98)
    shapes += _snowball(low, 0.29)
    for k in (-1.0, 1.0):   # the arms, a twig on each
        elbow = _screen(mid, k * 0.36, 0.12)
        shapes.append(Line((_screen(mid, k * 0.12, 0.04), elbow, _screen(mid, k * 0.5, 0.2)), TWIG, 2.2))
        shapes.append(Line((elbow, _screen(elbow, k * 0.04, 0.12)), TWIG, 1.6))
    shapes += _snowball(mid, 0.21)
    shapes += [_round(_screen(mid, side * 0.03, dv), 0.022, COAL, False) for dv in (0.1, 0.0, -0.1)]
    shapes += _snowball(head, 0.15)
    scarf = look.main
    shapes.append(_profile(head, _arc(0.0, -0.13, 0.15, 0.045, 0.0, 2 * math.pi, 18), scarf))
    shapes.append(_profile(head, [(-side * 0.08, -0.14), (-side * 0.02, -0.15), (-side * 0.05, -0.34), (-side * 0.12, -0.32)], shade(scarf, 0.12)))
    shapes.append(Line((_screen(head, -side * 0.035, -0.3), _screen(head, -side * 0.1, -0.29)), mix(scarf, SHINE, 0.4), 1.2))
    for du in (-0.05, 0.05):
        shapes.append(_round(_screen(head, du + side * 0.03, 0.04), 0.018, COAL, False))
    shapes += [_round(_screen(head, side * 0.03 + du, -0.055 + 0.02 * du * du * 40), 0.011, COAL, False) for du in (-0.05, -0.025, 0.0, 0.025, 0.05)]
    nose = _screen(head, side * 0.03, 0.0)
    shapes.append(Poly((_screen(nose, 0.0, 0.022), _screen(nose, 0.0, -0.022), _screen(nose, side * 0.14, -0.005)), CARROT))
    hat = look.detail
    brim = _screen(head, 0.0, 0.11)
    shapes.append(_profile(brim, _arc(0.0, 0.0, 0.17, 0.05, 0.0, 2 * math.pi, 18), hat))
    shapes.append(_profile(brim, [(-0.1, 0.0), (0.1, 0.0), (0.095, 0.17), (-0.095, 0.17)], hat))
    shapes.append(_profile(brim, [(-0.1, 0.015), (0.1, 0.015), (0.099, 0.05), (-0.099, 0.05)], scarf, False))
    return shapes


def _pumpkin_face(centre: Point3) -> list[list[tuple[float, float]]]:
    """A jack-o'-lantern's carved eyes, nose and grin round its middle (on the picture)."""
    eyes = [[(-0.12, 0.03), (-0.04, 0.03), (-0.08, 0.1)], [(0.04, 0.03), (0.12, 0.03), (0.08, 0.1)]]
    nose = [(-0.025, -0.02), (0.025, -0.02), (0.0, 0.025)]
    grin = [(-0.15, -0.05), (-0.09, -0.07), (-0.07, -0.05), (-0.03, -0.07), (0.03, -0.07), (0.07, -0.05), (0.09, -0.07), (0.15, -0.05),
            (0.1, -0.13), (0.04, -0.15), (0.02, -0.12), (-0.02, -0.12), (-0.04, -0.15), (-0.1, -0.13)]
    return [*eyes, nose, grin]


def _pumpkin(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A round, ribbed pumpkin (``color``) with a curly stem and leaf (``detail``) and a
    jack-o'-lantern face carved in it; on, the candle inside lights its face (the stage makes it
    flicker) and a warm glow pools round it."""
    x, y, z = _middle(f)
    on = state.on
    body = look.main
    centre = _screen((x, y, z), 0.0, 0.23)
    shapes: list[Shape] = light_pool((x, y, z + 0.01), 0.95, 0.75) if on else []
    for du, rx, fill in ((-0.15, 0.19, shade(body, 0.1)), (0.15, 0.19, shade(body, 0.16)), (0.0, 0.22, body)):
        shapes.append(_profile(centre, _arc(du, 0.0, rx, 0.21, 0.0, 2 * math.pi, 22), fill))
    shapes.append(_profile(centre, _arc(-0.08, 0.1, 0.06, 0.04, 0.0, 2 * math.pi, 10), mix(body, SHINE, 0.35), False))
    lit = mix(FIRE_YELLOW, SHINE, 0.2)
    for hole in _pumpkin_face(centre):
        shapes.append(_profile(centre, hole, lit if on else CARVED, True, on))
    stem = _screen(centre, 0.0, 0.18)
    shapes.append(_ribbon(stem, _screen(stem, 0.03, 0.1), 0.03, look.detail))
    shapes.append(Line((_screen(stem, 0.02, 0.06), _screen(stem, 0.09, 0.09), _screen(stem, 0.12, 0.05)), shade(look.detail, 0.2), 1.4))
    shapes.append(_profile(stem, [(-0.02, 0.02), (-0.1, 0.06), (-0.16, 0.02), (-0.1, -0.01)], mix(look.detail, SHINE, 0.1)))
    return shapes


def _pumpkin_flicker(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A lit jack-o'-lantern at ``now``: its carved face flickering with the candle inside."""
    x, y, z = _middle(f)
    centre = _screen((x, y, z), 0.0, 0.23)
    flicker = _flicker(now, 4)
    return [Motion(_profile(centre, hole, LIT_CORE).points, LIT_CORE, 0.15 + 0.6 * flicker, False, True) for hole in _pumpkin_face(centre)]


# ----- a party: a pile of gifts, balloons, a birthday cake -------------------------------------------------------


def _gift(f: _Frame, a0: float, b0: float, z0: float, a1: float, b1: float, z1: float, paper: str, ribbon: str, bow: bool) -> list[Shape]:
    """A wrapped box from (``a0``, ``b0``, ``z0``) to (``a1``, ``b1``, ``z1``): a ribbon round it
    both ways, a bow on top."""
    am, bm, half = (a0 + a1) / 2, (b0 + b1) / 2, 0.025
    shapes = f.box(a0, b0, z0, a1, b1, z1, paper)
    shapes.append(_rect(f, am - half, am + half, b1 + 0.001, z0, z1, f.front(ribbon), False))
    shapes.append(_side_rect(f, a1 + 0.001, bm - half, bm + half, z0, z1, f.side(ribbon), False))
    top = z1 + 0.001
    shapes.append(f.poly([(am - half, b0, top), (am + half, b0, top), (am + half, b1, top), (am - half, b1, top)], ribbon, False))
    shapes.append(f.poly([(a0, bm - half, top), (a1, bm - half, top), (a1, bm + half, top), (a0, bm + half, top)], ribbon, False))
    if bow:
        knot = f.p(am, bm, z1)
        shapes += [_profile(knot, [(0.0, 0.0), (-0.09, 0.07), (-0.1, -0.01)], mix(ribbon, SHINE, 0.1)),
                   _profile(knot, [(0.0, 0.0), (0.09, 0.07), (0.1, -0.01)], shade(ribbon, 0.1)), _round(knot, 0.025, ribbon)]
    return shapes


def _gift_pile(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A pile of four wrapped presents (the biggest in ``color``), tied with ribbons and bows
    (``detail``)."""
    ribbon = look.detail
    shapes = _gift(f, 0.58, 0.1, 0.0, 0.9, 0.44, 0.42, PAPERS[2], ribbon, True)
    shapes += _gift(f, 0.08, 0.28, 0.0, 0.54, 0.8, 0.5, look.main, ribbon, False)
    shapes += _gift(f, 0.16, 0.38, 0.5, 0.46, 0.7, 0.78, PAPERS[1], ribbon, True)
    return shapes + _gift(f, 0.58, 0.52, 0.0, 0.9, 0.88, 0.34, PAPERS[0], mix(ribbon, SHINE, 0.3), True)


def _balloons(f: _Frame, look: ObjectLook, now: float) -> list[Poly]:
    """A bunch of balloons at ``now`` (swaying on their strings): the strings, then each balloon
    (the highest first) with its knot and shine."""
    foot = f.p(0.5, 0.55, 0.14)
    colors = (look.main, *BALLOON_COLORS)
    placed = []
    for k, (du, dv, r) in enumerate(BALLOONS):
        swing = math.sin(2 * math.pi * now / SWAY_SECONDS + k * 0.9)
        placed.append((dv, _screen(foot, du + 0.05 * swing * dv / 1.4, dv + 0.012 * math.sin(2 * math.pi * now / 2.1 + k)), r, colors[k]))
    string = "#8A93A3"
    shapes = [Poly(_ribbon(_screen(foot, 0.0, 0.02), _screen(centre, 0.0, -r * 1.18 - 0.03), 0.005, string).points, string, False) for _, centre, r, _ in placed]
    for _, centre, r, color in sorted(placed, key=lambda p: -p[0]):
        shapes.append(_profile(centre, [(-0.025, -r * 1.18 - 0.035), (0.025, -r * 1.18 - 0.035), (0.0, -r * 1.18 + 0.01)], shade(color, 0.15)))
        shapes.append(_profile(centre, _arc(0.0, 0.0, r, r * 1.18, 0.0, 2 * math.pi, 22), color))
        shapes.append(_profile(centre, _arc(-r * 0.38, r * 0.42, r * 0.17, r * 0.28, 0.0, 2 * math.pi, 10), mix(color, SHINE, 0.6), False))
    return shapes


def _balloon_bunch(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A bunch of five balloons (the first in ``color``) on strings tied to a little weight
    (``detail``); on, they sway gently (the stage moves them)."""
    shapes = f.box(0.4, 0.45, 0.0, 0.6, 0.65, 0.14, look.detail)
    shapes.append(Line((f.p(0.4, 0.651, 0.1), f.p(0.6, 0.651, 0.1)), mix(look.detail, SHINE, 0.4), 1.2))
    if not (state.on and look.moving):   # the stage sways them while on
        shapes += _balloons(f, look, 0.0)
    return shapes


def _candle_tops(f: _Frame) -> list[tuple[Point3, str]]:
    """A birthday cake's candles: the tip of each (back to front) and its colour."""
    x, y, z = _middle(f)
    tops = [((x + 0.09 * math.cos(t), y + 0.09 * math.sin(t), z + 1.42), CANDLES[k]) for k, t in enumerate([2 * math.pi * k / 4 + 0.3 for k in range(4)])]
    return sorted(tops, key=lambda c: c[0][0] + c[0][1])


def _candle_flames(f: _Frame, now: float) -> list[Poly]:
    """The flames of a birthday cake's candles at ``now`` (outer, then yellow middle, each)."""
    parts = []
    for k, (tip, _) in enumerate(_candle_tops(f)):
        tall = 0.07 * (0.8 + 0.4 * _flicker(now, k + 1))
        sway = 0.012 * math.sin(2 * math.pi * now * (1.3 + 0.2 * k) + k)
        parts.append(Poly(_flame(_screen(tip, 0.0, 0.008), 0.02, tall, sway), FIRE_ORANGE, False, True))
        parts.append(Poly(_flame(_screen(tip, 0.0, 0.01), 0.011, tall * 0.6, sway * 0.6), FIRE_YELLOW, False, True))
    return parts


def _birthday_cake(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A two-tier birthday cake (``color`` its icing, ``detail`` its top tier and cream) on a
    plate on a little round table, four candles on top; on, they burn (the stage makes the flames
    flicker) and a warm glow pools round it."""
    x, y, z = _middle(f)
    on = state.on
    icing, cream = look.main, look.detail
    shapes: list[Shape] = light_pool((x, y, z + 0.01), 0.9, 0.6) if on else []
    shapes += [Upright(x, y, z, z + 0.06, 0.22, "#9C6B47"), Upright(x, y, z + 0.06, z + 0.78, 0.045, "#9C6B47"),
               Upright(x, y, z + 0.78, z + 0.84, 0.42, "#F4F1EA"), Upright(x, y, z + 0.84, z + 0.86, 0.33, "#E6EAF0")]
    shapes += [Upright(x, y, z + 0.86, z + 1.1, 0.26, icing), Disc((x, y, z + 1.1), 0.26, mix(icing, SHINE, 0.45))]
    drips = [(x + 0.26 * math.cos(t), y + 0.26 * math.sin(t), z + 1.1) for t in [-math.pi / 4 + math.pi * k / 10 for k in range(11)]]
    shapes.append(Line(tuple(drips), mix(icing, SHINE, 0.6), 3.0))
    shapes += [Upright(x, y, z + 1.1, z + 1.28, 0.17, cream), Disc((x, y, z + 1.28), 0.17, mix(cream, SHINE, 0.3))]
    for t in [-math.pi / 4 + math.pi * k / 5 for k in range(6)]:   # rosettes round the top tier's foot
        shapes.append(_round((x + 0.2 * math.cos(t), y + 0.2 * math.sin(t), z + 1.12), 0.025, mix(icing, SHINE, 0.2), False))
    for tip, color in _candle_tops(f):
        cx, cy, top = tip
        shapes += [Line(((cx, cy, z + 1.28), (cx, cy, top)), color, 3.4), Line(((cx, cy, top), (cx, cy, top + 0.03)), CASING, 0.8)]   # thin: no outline
    if on and not look.moving:   # the stage makes the flames flicker while they burn
        shapes += _candle_flames(f, 0.4)
    return shapes


# ----- a harbour: a boat, a dock, a lighthouse ---------------------------------------------------------------------


def _hull_half(a: float) -> float:
    """Half a boat's beam at ``a`` along it (its bow tapers to a point at 1.92)."""
    return 0.3 if a <= 1.2 else 0.3 * math.sqrt(max(0.0, 1.0 - ((a - 1.2) / 0.72) ** 2))


def _boat_parts(f: _Frame, look: ObjectLook, on: bool, lift: float, pitch: float, roll: float) -> list[Poly]:
    """A small sailing boat afloat (rising ``lift``, pitching and rolling by those shares): its
    hull (``color``) and deck, a white stripe, a mast with a mainsail and a jib (``detail``), a
    pennant, a lantern at the stern (lit when ``on``), then the foam where it meets the water."""
    wl = -WATER_DEPTH

    def p(a: float, b: float, z: float) -> Point3:
        return f.p(a, b + roll * (z - wl), z + lift + pitch * (a - 1.0))

    def gunwale(a: float) -> float:
        return wl + 0.42 + 0.1 * max(0.0, (a - 1.2) / 0.72) ** 2

    along = [0.12 + 1.8 * k / 18 for k in range(19)]
    near = [(a, 0.5 + _hull_half(a)) for a in along]
    far = [(a, 0.5 - _hull_half(a)) for a in reversed(along)]
    keel = [(a, 0.5 + s * 0.6 * _hull_half(a)) for s in (1.0, -1.0) for a in along[2:-1]]
    hull = look.main
    shapes = [_hull([p(a, b, gunwale(a)) for a, b in near + far] + [p(a, b, wl - 0.05) for a, b in keel], f.side(hull))]
    shapes.append(Poly(tuple([p(a, b, gunwale(a)) for a, b in near] + [p(a, 0.5 + 0.6 * _hull_half(a), wl - 0.05) for a, _ in reversed(near)]),
                       f.front(hull)))
    shapes.append(Poly(tuple([p(a, b - 0.002, gunwale(a) - 0.06) for a, b in near[:-2]] + [p(a, b - 0.002, gunwale(a) - 0.11) for a, b in reversed(near[:-2])]),
                       SHINE, False))
    shapes.append(Poly(tuple(p(a, b, gunwale(a)) for a, b in near + far), DECK))
    inner = [(a, 0.5 + 0.7 * (b - 0.5)) for a, b in [q for q in near if 0.3 < q[0] < 1.0] + [q for q in far if 0.3 < q[0] < 1.0]]   # the cockpit
    shapes.append(Poly(tuple(p(a, b, gunwale(a) + 0.001) for a, b in inner), shade(DECK, 0.3), False))
    sail = look.detail
    shapes.append(Poly(tuple(p(*q) for q in ((0.82, 0.5, wl + 2.42), (0.82, 0.5, wl + 0.76), (0.22, 0.5, wl + 0.76))), f.front(sail)))
    shapes.append(_ribbon(p(0.84, 0.5, wl + 0.74), p(0.18, 0.5, wl + 0.74), 0.016, SAIL_WOOD))
    shapes.append(_ribbon(p(0.86, 0.5, gunwale(0.86) - 0.05), p(0.86, 0.5, wl + 2.55), 0.024, SAIL_WOOD))
    shapes.append(Poly(tuple(p(*q) for q in ((0.92, 0.5, wl + 2.3), (1.86, 0.5, gunwale(1.86) + 0.06), (0.92, 0.5, wl + 0.7))),
                       f.front(mix(sail, SHINE, 0.3))))
    shapes.append(Poly(tuple(p(*q) for q in ((0.86, 0.5, wl + 2.55), (0.58, 0.5, wl + 2.5), (0.86, 0.5, wl + 2.44))), "#E2574C"))
    shapes.append(_ribbon(p(0.22, 0.5, gunwale(0.22)), p(0.22, 0.5, gunwale(0.22) + 0.34), 0.012, CASING))
    shapes.append(_round(p(0.22, 0.5, gunwale(0.22) + 0.39), 0.05, LIT_GLASS if on else "#8A93A3", True, on, 12))
    rim = [(a, b + 0.0) for a, b in near] + [(a, b) for a, b in far if a > 1.45]
    out = [(a + (0.08 if a > 1.8 else 0.0), b + (0.08 if b >= 0.5 else -0.08)) for a, b in rim]
    shapes.append(Poly(tuple([f.p(a, b, wl + 0.004) for a, b in rim] + [f.p(a, b, wl + 0.004) for a, b in reversed(out)]), FOAM, False))
    return shapes


def _bob(now: float) -> tuple[float, float, float]:
    """A boat's rise, pitch and roll at ``now``."""
    rise, pitch, roll = BOB
    t = 2 * math.pi * now / BOB_SECONDS
    return rise * math.sin(t), pitch * math.sin(t + 1.3), roll * math.sin(2 * math.pi * now / 3.7)


def _boat(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A small sailing boat afloat on water (it floats: its cells are water): a hull
    (``color``), a deck, a mast and two sails (``detail``), a lantern at its stern; on, the lantern
    is lit (light on the water) and the boat bobs (the stage rocks it)."""
    on = state.on
    shapes: list[Shape] = light_pool(f.p(0.25, 0.5, -WATER_DEPTH + 0.01), 0.8, 0.6) if on else []
    if not (on and look.moving):   # the stage rocks it while on
        shapes += _boat_parts(f, look, on, 0.0, 0.0, 0.0)
    return shapes


def _dock(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A wooden dock (``color`` its planks, ``detail`` its posts) reaching from the shore at its
    back out over the water at its front: posts at its sides (those out front go down into the
    water), plank seams, a coil of rope on it; one walks on it like on a bridge."""
    w, d = f.width, f.depth
    planks, posts = look.main, look.detail

    def post(a: float, b: float) -> list[Shape]:
        return f.box(a - 0.06, b - 0.06, -WATER_DEPTH if b > d / 2 else 0.0, a + 0.06, b + 0.06, 0.5, posts) + [
            Disc(f.p(a, b, 0.5), 0.045, mix(posts, SHINE, 0.2), False, holds_snow=False)]

    stations = [0.12 + (d - 0.24) * k / max(1, round(d)) for k in range(round(d) + 1)]
    shapes: list[Shape] = []
    for b in stations:
        shapes += post(0.1, b)
    shapes += f.box(0.04, -0.02, 0.06, w - 0.04, d + 0.02, 0.22, planks)
    for k in range(1, math.ceil(d * 4)):
        b = k / 4
        shapes.append(Line((f.p(0.06, b, 0.221), f.p(w - 0.06, b, 0.221)), shade(planks, 0.3), 0.7))
    shapes.append(Line((f.p(w - 0.04 + 0.001, -0.02, 0.14), f.p(w - 0.04 + 0.001, d + 0.02, 0.14)), shade(planks, 0.35), 0.6))
    for b in stations:
        shapes += post(w - 0.1, b)
    coil = f.p(w / 2 + 0.05, d - 0.45, 0.225)
    for r, color in ((0.14, "#D9B07A"), (0.09, "#C69A62")):
        shapes.append(Line(tuple((coil[0] + r * math.cos(t), coil[1] + r * math.sin(t), coil[2] + 0.02) for t in [2 * math.pi * k / 16 for k in range(17)]), color, 2.4))
    return shapes


def _lantern_middle(f: _Frame) -> Point3:
    x, y, z = _middle(f)
    return (x, y, z + LANTERN[0])


def _lighthouse(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A tall lighthouse on a stone base: a round tower in white and ``color`` bands with a door
    and little windows, a gallery with a railing, a glass lantern room and a dome (``detail``); on,
    its lantern shines (the stage sweeps its beam round; strongest at night)."""
    x, y, z = _middle(f)
    on = state.on
    stripe, dark = look.main, look.detail
    shapes = f.box(0.06, 0.06, 0.0, 0.94, 0.94, 0.3, STONE)
    bands = (0.3, 1.3, 2.3, 3.3, 4.25)
    radius = lambda zz: 0.38 - 0.12 * (zz - 0.3) / 3.95   # noqa: E731
    for k, (z0, z1) in enumerate(zip(bands, bands[1:])):
        shapes += _band(x, y, z + z0, z + z1, radius(z0), radius(z1), TOWER_WHITE if k % 2 == 0 else stripe)
    t = math.pi / 4   # the door and the windows face the viewer
    door = [(x + radius(0.3) * math.cos(t + dt), y + radius(0.3) * math.sin(t + dt), z + zz) for dt, zz in ((-0.35, 0.3), (0.35, 0.3), (0.35, 0.95), (0.0, 1.05), (-0.35, 0.95))]
    shapes.append(Poly(tuple(door), dark))
    for zz in (1.8, 2.8, 3.7):
        r = radius(zz) + 0.002
        shapes.append(Poly(tuple((x + r * math.cos(t + dt), y + r * math.sin(t + dt), z + zz + dz) for dt, dz in ((-0.18, 0.0), (0.18, 0.0), (0.18, 0.28), (-0.18, 0.28))),
                           LIT_GLASS if on else "#3A4A5C", True, on))
    shapes += [Disc((x, y, z + 4.25), 0.4, dark), Upright(x, y, z + 4.25, z + 4.29, 0.4, dark)]
    shapes += _band(x, y, z + 4.29, z + 4.9, LANTERN[1], LANTERN[1], LIT_GLASS if on else GLASS, on)
    if on:
        shapes.append(_round((x, y, z + LANTERN[0]), 0.09, LIT_CORE, False, True))
    for dt in (-0.6, 0.15, 0.9):   # the lantern's window bars
        shapes.append(Line(((x + LANTERN[1] * math.cos(t + dt), y + LANTERN[1] * math.sin(t + dt), z + 4.3),
                            (x + LANTERN[1] * math.cos(t + dt), y + LANTERN[1] * math.sin(t + dt), z + 4.9)), dark, 1.2))
    rail = [(x + 0.4 * math.cos(a), y + 0.4 * math.sin(a), z + 4.55) for a in [-math.pi / 4 + math.pi * k / 12 for k in range(13)]]
    shapes.append(Line(tuple(rail), dark, 1.6))
    for px, py, pz in rail[::3]:
        shapes.append(Line(((px, py, z + 4.29), (px, py, pz)), dark, 1.2))
    shapes += _band(x, y, z + 4.9, z + 5.35, 0.24, 0.02, dark)
    return shapes + [_round((x, y, z + 5.42), 0.05, mix(dark, SHINE, 0.3))]


def _beam(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A lit lighthouse at ``now``: its beam sweeping round (fainter while it points away), light
    thrown on things (strong at night, faint by day)."""
    x, y, z = _lantern_middle(f)
    turn = 2 * math.pi * now / SWEEP_SECONDS
    ux, uy = math.cos(turn), math.sin(turn)
    near = 0.5 + 0.5 * max(-1.0, min(1.0, (ux + uy) / math.sqrt(2)))   # 1 pointing at the viewer, 0 away
    spread = 0.55
    tip = (x + BEAM_REACH * ux, y + BEAM_REACH * uy, z)
    beam = ((x - 0.1 * uy, y + 0.1 * ux, z), (tip[0] - spread * uy, tip[1] + spread * ux, z + 0.12), (tip[0] + spread * uy, tip[1] - spread * ux, z - 0.12),
            (x + 0.1 * uy, y - 0.1 * ux, z))
    return [Motion(beam, BEAM, 0.18 + 0.32 * near, False, True, pool=True)]


# ----- travel: a train car, a rocket ---------------------------------------------------------------------------


def _train_car(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A passenger carriage (``color``) side-on on a stretch of track: a row of windows with a
    trim line (``detail``), doors at its ends, a rounded roof, two bogies with wheels."""
    w = f.width
    body = look.main
    a0, a1, b0, b1 = 0.14, w - 0.14, 0.22, 0.78
    shapes: list[Shape] = []
    for k in range(int((w - 0.26) / 0.4) + 1):   # sleepers, then the rails
        a = 0.1 + k * 0.4
        shapes += f.box(a, 0.12, 0.0, a + 0.16, 0.88, 0.05, "#7A5236")
    for b in (0.3, 0.7):
        shapes += f.box(0.0, b - 0.025, 0.05, w, b + 0.025, 0.1, "#8A93A3")
    for c0 in (0.4, w - 1.0):   # the bogies: a frame and two wheels each on the near side
        shapes += f.box(c0, 0.3, 0.12, c0 + 0.6, 0.7, 0.36, CASING)
        for a in (c0 + 0.15, c0 + 0.45):
            shapes.append(f.poly(_face_circle(f, a, 0.701, 0.2, 0.12, 16), TYRE))
            shapes.append(f.poly(_face_circle(f, a, 0.702, 0.2, 0.045, 8), "#B9BFC9", False))
    shapes += f.box(a0, b0, 0.36, a1, b1, 1.78, body)
    face = b1 + 0.001
    trim = look.detail
    shapes.append(_rect(f, a0, a1, face, 0.36, 0.48, shade(body, 0.3), False))
    shapes.append(_rect(f, a0, a1, face, 0.88, 0.94, f.front(trim), False))
    doors = (a0 + 0.12, a1 - 0.44)
    for d0 in doors:
        shapes.append(_rect(f, d0, d0 + 0.32, face, 0.5, 1.62, f.front(mix(body, SHINE, 0.08))))
        shapes.append(_rect(f, d0 + 0.07, d0 + 0.25, face + 0.001, 1.1, 1.5, f.front(mix(GLASS, CASING, 0.15))))
    count = 5
    span0, span1 = doors[0] + 0.44, doors[1] - 0.12
    step = (span1 - span0) / count
    for k in range(count):
        u0 = span0 + k * step + 0.04
        shapes.append(_rect(f, u0, u0 + step - 0.08, face, 1.04, 1.5, f.front(mix(GLASS, SHINE, 0.1))))
        shapes.append(Line((f.p(u0 + 0.05, face + 0.001, 1.12), f.p(u0 + 0.14, face + 0.001, 1.42)), SHINE, 1.0))
    shapes.append(_side_rect(f, a1 + 0.001, 0.36, 0.64, 1.0, 1.5, f.side(mix(GLASS, CASING, 0.15))))   # the end door's window
    roof = [(a0 - 0.03, b0 - 0.03, 1.78), (a1 + 0.03, b0 - 0.03, 1.78), (a1 + 0.03, b1 + 0.03, 1.78), (a0 - 0.03, b1 + 0.03, 1.78)]
    shapes.append(f.poly(roof, shade(body, 0.35)))
    shapes += f.box(a0 + 0.02, b0 + 0.08, 1.78, a1 - 0.02, b1 - 0.08, 1.92, mix(TOWER_WHITE, body, 0.25))
    for a in (a0 - 0.08, a1):   # couplers
        shapes += f.box(a, 0.45, 0.45, a + 0.08, 0.55, 0.55, CASING)
    return shapes


def _rocket_centre(f: _Frame) -> Point3:
    return _middle(f)


def _jet(top: Point3, half: float, length: float, sway: float) -> tuple[Point3, ...]:
    """A flame blasting down from ``top``: round at the top ``half`` wide, its tip ``length``
    down the picture and ``sway`` across."""
    cap = [_screen(top, half * math.cos(t), half * 0.4 * math.sin(t)) for t in [math.pi * k / 8 for k in range(9)]]
    return tuple(cap + [_screen(top, -half * 0.8, -length * 0.4), _screen(top, sway, -length), _screen(top, half * 0.8, -length * 0.4)])


def _rocket_fire(f: _Frame, now: float) -> list[Poly]:
    """A rocket's flame at ``now``: outer, then its yellow middle."""
    x, y, z = _rocket_centre(f)
    nozzle = (x, y, z + NOZZLE)
    lick = _flicker(now, 2)
    sway = 0.02 * math.sin(2 * math.pi * now * 1.7)
    return [Poly(_jet(nozzle, 0.2, 0.3 + 0.12 * lick, sway), FIRE_ORANGE, False, True),
            Poly(_jet(_screen(nozzle, 0.0, -0.01), 0.11, 0.2 + 0.08 * lick, sway * 0.6), FIRE_YELLOW, False, True)]


def _rocket(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A rocket (``color``, its nose, fins and band ``detail``) standing on a launch pad of
    concrete with hazard stripes beside an orange service tower; on, its engine fires (the stage
    makes the flame roar and smoke billow over the pad) and the fire lights the pad."""
    w, d = f.width, f.depth
    on = state.on
    x, y, z = _rocket_centre(f)
    body, trim = look.main, look.detail
    shapes: list[Shape] = light_pool((x, y, z + 0.17), 1.7) if on else []
    shapes += f.box(0.06, 0.06, 0.0, w - 0.06, d - 0.06, 0.16, CONCRETE)
    shapes += _stripes(f, 0.1, w - 0.1, d - 0.06 + 0.001, 0.03, 0.13)
    shapes += _stripes(f, 0.1, d - 0.1, 0.0, 0.03, 0.13, side=w - 0.06 + 0.001)
    shapes.append(Disc((x, y, z + 0.161), 0.36, "#3A3F4B", True, holds_snow=False))
    if on:
        shapes.append(Disc((x, y, z + 0.162), 0.26, EMBER, False, glow=True, holds_snow=False))
    tower = "#F2A33A"   # the service tower behind the rocket: a lattice, a platform, an arm to it
    a0, a1, b0, b1, top = w / 2 - 0.19, w / 2 + 0.19, 0.1, 0.48, 4.05
    for a, b in ((a0, b0), (a1, b0), (a0, b1)):
        shapes.append(Line((f.p(a, b, 0.16), f.p(a, b, top)), shade(tower, 0.15), 2.4))
    for k in range(6):   # its braces on the faces to the viewer
        z0, z1 = 0.16 + k * 0.64, 0.16 + (k + 1) * 0.64
        shapes.append(Line((f.p(a0, b1, z0), f.p(a1, b1, z1)), tower, 1.4))
        shapes.append(Line((f.p(a1, b0, z0), f.p(a1, b1, z1)), shade(tower, 0.15), 1.4))
    shapes.append(Line((f.p(a1, b1, 0.16), f.p(a1, b1, top)), tower, 2.6))
    shapes += f.box(a0 - 0.03, b0 - 0.03, top, a1 + 0.03, b1 + 0.03, top + 0.06, tower)
    shapes += f.box(w / 2 - 0.05, b1, 3.2, w / 2 + 0.05, d / 2 - ROCKET_RADIUS + 0.02, 3.28, tower)
    for t in (math.pi * 5 / 4, -math.pi / 4, math.pi * 3 / 4):   # fins behind and at the sides
        shapes.append(Poly(tuple((x + s * math.cos(t), y + s * math.sin(t), z + zz) for s, zz in ((0.26, 0.6), (0.58, 0.48), (0.58, 0.82), (0.26, 1.35))),
                           shade(trim, 0.12)))
    shapes += _band(x, y, z + NOZZLE, z + 0.62, 0.15, 0.22, "#4A4F5B")
    for k, (z0, z1, color) in enumerate(((0.6, 2.86, body), (2.86, 3.02, trim), (3.02, 3.5, body))):
        shapes += _band(x, y, z + z0, z + z1, ROCKET_RADIUS, ROCKET_RADIUS, color)
    shapes += _band(x, y, z + 3.5, z + 4.5, ROCKET_RADIUS, 0.0, trim)
    window = (x + ROCKET_RADIUS * 0.72, y + ROCKET_RADIUS * 0.72, z + 2.45)
    shapes += [_round(window, 0.1, "#B9BFC9"), _round(window, 0.07, "#5FD8FF" if not on else mix("#5FD8FF", SHINE, 0.3), True, on),
               _round(_screen(window, -0.02, 0.02), 0.02, SHINE, False)]
    t = math.pi / 4   # the fin to the viewer
    shapes.append(Poly(tuple((x + s * math.cos(t), y + s * math.sin(t), z + zz) for s, zz in ((0.26, 0.6), (0.6, 0.46), (0.6, 0.82), (0.26, 1.38))), trim))
    if on and not look.moving:   # the stage makes it roar and smoke
        shapes += _rocket_fire(f, 0.4)
    return shapes


def _rocket_motion(f: _Frame, now: float) -> list[Motion]:
    """A firing rocket at ``now``: its flame, then puffs of smoke billowing out over the pad to
    both sides and fading."""
    x, y, z = _rocket_centre(f)
    parts = [Motion(p.points, p.fill, 1.0, False, True) for p in _rocket_fire(f, now)]
    for k in range(SMOKE_PUFFS):
        rise = _rising(now, k, SMOKE_PUFFS, SMOKE_SECONDS)
        way = 1.0 if k % 2 else -1.0
        point = _screen((x, y, z + 0.2), way * (0.15 + 0.75 * rise), 0.04 + 0.22 * rise)
        parts.append(Motion(_round(point, 0.12 + 0.2 * rise, SMOKE).points, SMOKE, 0.7 * _fade(rise), False, True))   # lit by the fire at night
    return parts


#: The drawings of this module's kinds (each by its frame, look and state), and those with
#: moving parts the stage draws while they work (:func:`motion`).
DRAWINGS: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {
    "christmas_tree": _christmas_tree, "snowman": _snowman, "pumpkin": _pumpkin, "gift_pile": _gift_pile, "balloon_bunch": _balloon_bunch,
    "birthday_cake": _birthday_cake, "boat": _boat, "dock": _dock, "lighthouse": _lighthouse, "train_car": _train_car, "rocket": _rocket,
}
MOVING = frozenset({"christmas_tree", "pumpkin", "balloon_bunch", "birthday_cake", "boat", "lighthouse", "rocket"})


def motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """The moving parts at ``now`` of a lit Christmas tree (twinkling lights), a lit pumpkin (its
    flickering face), swaying balloons, a cake's candle flames, a bobbing boat, a lighthouse's
    sweeping beam and a firing rocket (its flame and smoke)."""
    kind = f.item.kind
    if kind == "christmas_tree":
        return _tree_twinkle(f, look, now)
    if kind == "pumpkin":
        return _pumpkin_flicker(f, look, now)
    if kind == "balloon_bunch":
        return [Motion(p.points, p.fill, 1.0, p.ink, False) for p in _balloons(f, look, now)]
    if kind == "birthday_cake":
        return [Motion(p.points, p.fill, 1.0, False, True) for p in _candle_flames(f, now)]
    if kind == "boat":
        return [Motion(p.points, p.fill, 1.0, p.ink, p.glow) for p in _boat_parts(f, look, True, *_bob(now))]
    if kind == "lighthouse":
        return _beam(f, look, now)
    if kind == "rocket":
        return _rocket_motion(f, now)
    return []


__all__ = ["DRAWINGS", "MOVING", "motion"]
