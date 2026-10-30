"""Home and shop iso objects (DESIGN.md §104, Phase AC Step 262): a bathtub, a wardrobe, a crib,
a café table with two chairs, a shop counter, a cash register, a display case of cakes or
jewels, a market stall and a vending machine. No manim.

Drawn like :mod:`vidgen.cartoon.iso_objects`' objects (its frame, shading and helpers), which
looks each kind of this module up in :data:`DRAWINGS`; none of them has moving parts.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from vidgen.cartoon.iso_drawing import Disc, Line, Poly, Shape, Upright, mix, shade
from vidgen.cartoon.iso_objects import (
    BOOK_COLORS,
    CASING,
    DISPLAY_GREEN,
    GLASS,
    SHINE,
    WOOD,
    Motion,
    ObjectLook,
    _Frame,
    _glow_rect,
    _indicator,
    _round,
    _screen,
    light_pool,
)
from vidgen.world.iso import DISPLAY_CASES, ObjectState
from vidgen.world.iso_view import Point3

#: A clawfoot bath's feet, a rubber duck and its beak; brass knobs; chrome.
BRASS = "#E0B85A"
DUCK = "#FFD23F"
BEAK = "#FF8A3D"
CHROME = "#C9CED6"
#: A shop counter's wood (also under a cash register), a café chair's rattan, a crate's wood.
COUNTER_WOOD = "#B07A4F"
RATTAN = "#D9B07A"
CRATE = "#D8A867"
#: Cakes (sponge, chocolate, cream), a cherry, gold and gems.
CAKES = ("#F7E3B8", "#7A4A32", "#FFF3E3")
CHERRY = "#D7263D"
GOLD = "#F2C14E"
GEMS = ("#E2574C", "#4C8DD6", "#48C774", "#B48EAD")
#: Fruit in a market stall's crates: apples, oranges, limes.
FRUIT = ("#E2574C", "#FF9A3D", "#8BC34A")
#: A vending machine's drinks.
DRINKS = ("#E2574C", "#4C8DD6", "#F6C945", "#5BA35B", "#F4F6FA", "#FF8A3D")


def _rect(f: _Frame, a0: float, a1: float, b: float, z0: float, z1: float, fill: str, ink: bool = True, glow: bool = False) -> Poly:
    """A rectangle on the front face at ``b`` (``a0`` .. ``a1`` across, ``z0`` .. ``z1`` up)."""
    return f.poly([(a0, b, z0), (a1, b, z0), (a1, b, z1), (a0, b, z1)], fill, ink, glow)


def _plinth(f: _Frame, a0: float, a1: float, b: float, color: str, height: float = 0.08) -> Poly:
    """The dark kick plinth along the bottom of a front at ``b``."""
    return _rect(f, a0, a1, b + 0.001, 0.0, height, shade(color, 0.45), False)


# ----- a bathroom and a bedroom: bathtub, wardrobe, crib ---------------------------------------------------


def _bathtub(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A clawfoot bathtub (``color`` its enamel) on four brass feet: a rolled rim, water
    (``detail``) with foam and a rubber duck, a chrome tap at its far end."""
    w, d = f.width, f.depth
    enamel, water = look.main, look.detail
    a0, a1, b0, b1, z0, z1 = 0.12, w - 0.12, 0.16, d - 0.12, 0.16, 0.8
    shapes: list[Shape] = [_round(f.p(a, b0 + 0.1, 0.08), 0.07, BRASS) for a in (a0 + 0.15, a1 - 0.15)]
    shapes += f.box(a0, b0, z0, a1, b1, z1, enamel)
    shapes.append(Line((f.p(a0 + 0.05, b1 + 0.001, z0 + 0.1), f.p(a1 - 0.05, b1 + 0.001, z0 + 0.1)), shade(enamel, 0.18), 0.8))
    shapes += [_round(f.p(a, b1 - 0.06, 0.08), 0.075, BRASS) for a in (a0 + 0.15, a1 - 0.15)]
    shapes += f.box(a0 - 0.03, b0 - 0.03, z1, a1 + 0.03, b1 + 0.03, z1 + 0.07, mix(enamel, SHINE, 0.3))
    top = z1 + 0.07
    i0, i1, j0, j1 = a0 + 0.07, a1 - 0.07, b0 + 0.07, b1 - 0.07
    shapes.append(f.poly([(i0, j0, top + 0.001), (i1, j0, top + 0.001), (i1, j1, top + 0.001), (i0, j1, top + 0.001)], shade(enamel, 0.22)))
    sunk = 0.12   # the water lies lower: the far inner walls show
    shapes.append(f.poly([(i0 + sunk, j0 + sunk, top + 0.002), (i1, j0 + sunk, top + 0.002), (i1, j1, top + 0.002), (i0 + sunk, j1, top + 0.002)],
                         water, False))
    shapes.append(Line((f.p(i0 + 0.4, j0 + 0.3, top + 0.003), f.p(i0 + 0.7, j0 + 0.3, top + 0.003)), mix(water, SHINE, 0.55), 1.4))
    shapes.append(Line((f.p(i1 - 0.55, j1 - 0.15, top + 0.003), f.p(i1 - 0.3, j1 - 0.15, top + 0.003)), mix(water, SHINE, 0.55), 1.4))
    for k, (a, b, r) in enumerate(((0.32, 0.4, 0.07), (0.45, 0.5, 0.09), (0.36, 0.62, 0.06), (0.6, 0.45, 0.06), (0.55, 0.62, 0.075))):
        shapes.append(_round(f.p(i0 + a, j0 + b * (j1 - j0) + 0.05, top + 0.02), r, "#FFFFFF" if k % 2 else "#F4F8FB"))
    duck = f.p(i1 - 0.42, (j0 + j1) / 2 + 0.06, top + 0.04)
    shapes += [_round(duck, 0.075, DUCK), _round(_screen(duck, -0.05, 0.07), 0.05, DUCK),
               Poly((_screen(duck, -0.1, 0.065), _screen(duck, -0.14, 0.055), _screen(duck, -0.1, 0.045)), BEAK, False),
               _round(_screen(duck, -0.06, 0.085), 0.008, "#2B2F3A", False)]
    x, y, z = f.p(a0 + 0.12, (b0 + b1) / 2, z1 + 0.07)
    shapes += [Upright(x, y, z, z + 0.24, 0.03, CHROME)]
    shapes.append(Line((_screen((x, y, z + 0.24), 0.0, 0.0), f.p(a0 + 0.3, (b0 + b1) / 2, z1 + 0.35), f.p(a0 + 0.33, (b0 + b1) / 2, z1 + 0.25)), CHROME, 3.0))
    for side in (-0.13, 0.13):
        hx, hy, hz = f.p(a0 + 0.12, (b0 + b1) / 2 + side, z1 + 0.07)
        shapes += [Upright(hx, hy, hz, hz + 0.08, 0.02, CHROME), _round((hx, hy, hz + 0.1), 0.03, "#E2574C" if side < 0 else "#4C8DD6")]
    return shapes


#: A wardrobe's body: a from, a to, b at its back and front, its height; its doors' bottom and top.
WARDROBE = (0.08, 0.6, 2.3, 0.14, 2.2)
#: How far an open wardrobe door has swung out (degrees from shut).
WARDROBE_SWING = 105.0


def _leaf(hinge: float, b: float, along: tuple[float, float], length: float, s: float, z: float) -> tuple[float, float, float]:
    """A point of a door swung out on its hinge at (``hinge``, ``b``): ``s`` of its ``length`` along
    the direction ``along`` (across, out), at height ``z``."""
    return (hinge + along[0] * length * s, b + along[1] * length * s, z)


def _wardrobe(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A tall double wardrobe (``color`` its wood) with panelled doors, brass knobs and a cornice;
    open, its doors swung out (a mirror inside the left one) show clothes on hangers (some in the
    ``detail`` colour), folded clothes on a shelf and shoes."""
    w = f.width
    wood = look.main
    pad, b1, h, door0, door1 = WARDROBE
    a0, a1, b0 = pad, w - pad, 0.12
    mid = w / 2
    shapes = f.box(a0, b0, 0.0, a1, b1, h, wood)
    shapes.append(_plinth(f, a0 + 0.02, a1 - 0.02, b1, wood, 0.1))
    panel = f.front(mix(wood, SHINE, 0.06))
    inset = f.front(shade(wood, 0.06))
    if not state.open:
        for u0, u1, knob in ((a0 + 0.04, mid - 0.012, mid - 0.08), (mid + 0.012, a1 - 0.04, mid + 0.08)):
            shapes.append(_rect(f, u0, u1, b1 + 0.002, door0, door1, panel))
            for z0, z1 in ((door0 + 0.12, door0 + 0.8), (door0 + 0.95, door1 - 0.12)):
                shapes.append(_rect(f, u0 + 0.09, u1 - 0.09, b1 + 0.003, z0, z1, inset))
            shapes.append(_round(f.p(knob, b1 + 0.004, 1.1), 0.03, BRASS))
    else:
        inside = shade(wood, 0.6)
        shapes.append(_rect(f, a0 + 0.04, a1 - 0.04, b1 + 0.001, door0, door1, inside, False))
        shelf = door1 - 0.3
        shapes.append(_rect(f, a0 + 0.04, a1 - 0.04, b1 + 0.002, shelf - 0.04, shelf, f.front(wood), False))
        for k, color in enumerate((look.detail, BOOK_COLORS[1], BOOK_COLORS[3], BOOK_COLORS[2])):   # folded clothes
            u = a0 + 0.2 + 0.42 * (k // 2)
            z = shelf + 0.07 * (k % 2)
            shapes.append(_rect(f, u + 0.02 * (k % 2), u + 0.32 - 0.02 * (k % 2), b1 + 0.003, z, z + 0.07, f.front(color)))
        rail = shelf - 0.16
        shapes.append(Line((f.p(a0 + 0.08, b1 + 0.003, rail), f.p(a1 - 0.08, b1 + 0.003, rail)), CHROME, 2.0))
        colors = (look.detail, BOOK_COLORS[0], "#F4F6FA", BOOK_COLORS[3], look.detail, BOOK_COLORS[4], BOOK_COLORS[2])
        count = max(3, round((a1 - a0 - 0.2) / 0.22))
        for k in range(count):
            c = a0 + 0.17 + (a1 - a0 - 0.34) * k / max(count - 1, 1)
            long = k % 3 == 1
            low = rail - (1.05 if long else 0.72)
            flare = 0.03 if long else 0.0
            hook = rail - 0.08
            shapes.append(Line((f.p(c, b1 + 0.004, rail + 0.02), f.p(c, b1 + 0.004, hook + 0.02)), CHROME, 1.2))
            shapes.append(f.poly([(c - 0.06, b1 + 0.004, hook), (c + 0.06, b1 + 0.004, hook), (c + 0.1 + flare, b1 + 0.004, hook - 0.06),
                                  (c + 0.09 + flare, b1 + 0.004, low), (c - 0.09 - flare, b1 + 0.004, low), (c - 0.1 - flare, b1 + 0.004, hook - 0.06)],
                                 f.front(colors[k % len(colors)])))
        for k in range(2):   # shoes
            u = a0 + 0.25 + k * 0.32
            shapes.append(f.poly([(u, b1 + 0.004, door0), (u + 0.2, b1 + 0.004, door0), (u + 0.2, b1 + 0.004, door0 + 0.05),
                                  (u + 0.08, b1 + 0.004, door0 + 0.11), (u, b1 + 0.004, door0 + 0.11)], "#4A3A30"))
        length = mid - a0 - 0.05
        t = math.radians(WARDROBE_SWING)
        left, right = (math.cos(t), math.sin(t)), (-math.cos(t), math.sin(t))
        hinge = a0 + 0.04
        shapes.append(f.poly([_leaf(hinge, b1, left, length, s, z) for s, z in ((0.0, door0), (1.0, door0), (1.0, door1), (0.0, door1))],
                             shade(wood, 0.2)))
        shapes.append(f.poly([_leaf(hinge, b1, left, length, s, z) for s, z in ((0.18, door0 + 0.2), (0.82, door0 + 0.2), (0.82, door1 - 0.15),
                                                                                (0.18, door1 - 0.15))], mix(GLASS, "#8FB3C9", 0.35)))
        shapes.append(f.poly([_leaf(hinge, b1, left, length, s, z) for s, z in ((0.3, door0 + 0.5), (0.42, door0 + 0.5), (0.68, door1 - 0.6),
                                                                                (0.56, door1 - 0.6))], mix(GLASS, SHINE, 0.6), False))
        hinge = a1 - 0.04
        shapes.append(f.poly([_leaf(hinge, b1, right, length, s, z) for s, z in ((0.0, door0), (1.0, door0), (1.0, door1), (0.0, door1))],
                             f.side(mix(wood, SHINE, 0.06))))
        for z0, z1 in ((door0 + 0.12, door0 + 0.8), (door0 + 0.95, door1 - 0.12)):
            shapes.append(f.poly([_leaf(hinge, b1, right, length, s, z) for s, z in ((0.12, z0), (0.88, z0), (0.88, z1), (0.12, z1))],
                                 f.side(shade(wood, 0.06))))
        shapes.append(_round(f.p(*_leaf(hinge, b1, right, length, 0.9, 1.1)), 0.03, BRASS))
    return shapes + f.box(a0 - 0.04, b0 - 0.02, h, a1 + 0.04, b1 + 0.05, h + 0.12, mix(wood, SHINE, 0.1))


def _crib(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A baby's crib (``color`` its painted wood): corner posts with round knobs, barred sides, a
    mattress with a pillow, a blanket (``detail``) and a teddy bear, and a mobile of a star, a
    moon and a ball hanging over it."""
    w, d = f.width, f.depth
    wood = look.main
    a0, a1, b0, b1 = 0.14, w - 0.14, 0.16, d - 0.12
    post, base, rail = 0.06, 0.3, 0.88
    bar = shade(wood, 0.3)

    def bar_line(a: float, b: float) -> Line:   # a thin bar: a line, so the bars do not ink over the bed
        return Line((f.p(a, b, base), f.p(a, b, rail - 0.05)), bar, 1.1)

    shapes: list[Shape] = []
    shapes += f.box(a0, b0, 0.0, a0 + post, b0 + post, rail + 0.06, wood)
    shapes += f.box(a1 - post, b0, 0.0, a1, b0 + post, rail + 0.06, wood)
    shapes += f.box(a0 + post, b0, base, a1 - post, b0 + 0.04, rail - 0.05, mix(wood, SHINE, 0.04))
    shapes += f.box(a0 + post, b0, rail - 0.05, a1 - post, b0 + 0.04, rail, wood)
    for k in range(1, 5):   # the far side's bars
        b = b0 + (b1 - b0) * k / 5
        shapes.append(bar_line(a0 + 0.03, b))
    shapes += f.box(a0 + post, b0 + 0.04, base - 0.06, a1 - post, b1 - 0.02, base, wood)
    shapes += f.box(a0 + 0.06, b0 + 0.05, base, a1 - 0.06, b1 - 0.04, base + 0.12, "#F7F4EC")
    shapes += f.box(a0 + 0.14, b0 + 0.08, base + 0.12, a1 - 0.14, b0 + 0.26, base + 0.2, "#FFFFFF")
    bear = f.p(a1 - 0.24, b0 + 0.36, base + 0.2)
    ears = [_round(_screen(bear, du, 0.21), 0.035, "#B07A4F") for du in (-0.055, 0.055)]
    shapes += [*ears, _round(bear, 0.085, "#B07A4F"), _round(_screen(bear, 0.0, 0.15), 0.07, "#C68B5C"),
               _round(_screen(bear, 0.0, 0.13), 0.025, "#E9D3B5", False)]
    shapes += f.box(a0 + 0.06, b0 + 0.45, base + 0.12, a1 - 0.06, b1 - 0.03, base + 0.18, look.detail)
    shapes.append(Line((f.p(a0 + 0.06, b0 + 0.52, base + 0.181), f.p(a1 - 0.06, b0 + 0.52, base + 0.181)), mix(look.detail, SHINE, 0.45), 1.4))
    for k in range(1, 6):   # the near side's bars
        a = a0 + (a1 - a0) * k / 6
        shapes.append(bar_line(a, b1 - 0.025))
    for k in range(1, 5):   # the right side's
        b = b0 + (b1 - b0) * k / 5
        shapes.append(bar_line(a1 - 0.025, b))
    shapes += f.box(a0 + post, b1 - 0.05, base - 0.06, a1 - post, b1, base, wood)
    shapes += f.box(a0 + post, b1 - 0.05, rail - 0.05, a1 - post, b1, rail, wood)
    shapes += f.box(a1 - 0.05, b0 + post, rail - 0.05, a1, b1 - post, rail, wood)
    shapes += f.box(a0, b1 - post, 0.0, a0 + post, b1, rail + 0.06, wood)
    shapes += f.box(a1 - post, b1 - post, 0.0, a1, b1, rail + 0.06, wood)
    for a, b in ((a0, b0), (a1 - post, b0), (a0, b1 - post), (a1 - post, b1 - post)):
        shapes.append(_round(f.p(a + post / 2, b + post / 2, rail + 0.1), 0.045, mix(wood, SHINE, 0.1)))
    # the mobile: a pole up from the far corner, an arm over the middle, three toys on strings
    x, y, z = f.p(a0 + post / 2, b0 + post / 2, rail + 0.1)
    top = z + 0.62
    hub = f.p(w / 2, d / 2, rail + 0.72)
    shapes += [Upright(x, y, z, top, 0.018, wood), Line(((x, y, top), hub), wood, 2.2)]
    for k, color in enumerate(("#F6C945", "#7FC8E8", "#F2A7C3")):
        t = 2 * math.pi * k / 3 + 0.5
        end = (hub[0] + 0.2 * math.cos(t), hub[1] + 0.2 * math.sin(t), hub[2] - 0.02)
        toy = (end[0], end[1], end[2] - 0.22 - 0.05 * k)
        shapes += [Line((hub, end), CHROME, 1.0), Line((end, toy), CHROME, 0.8)]
        if k == 0:   # a star
            shapes.append(Poly(tuple(_screen(toy, (0.075 if j % 2 == 0 else 0.032) * math.sin(math.pi * j / 5),
                                             (0.075 if j % 2 == 0 else 0.032) * math.cos(math.pi * j / 5) - 0.06) for j in range(10)), color))
        elif k == 1:   # a moon
            shapes.append(Poly(tuple([_screen(toy, 0.065 * math.cos(t), 0.065 * math.sin(t) - 0.065) for t in [math.pi * (0.5 + j / 10) for j in range(11)]]
                                     + [_screen(toy, 0.03 * math.cos(t), 0.055 * math.sin(t) - 0.065) for t in [math.pi * (1.5 - j / 10) for j in range(11)]]),
                               color))
        else:
            shapes.append(_round(_screen(toy, 0.0, -0.05), 0.05, color))
    return shapes


# ----- a café and a shop: café table, counter, cash register, display case --------------------------------


def _bistro_chair(f: _Frame, a: float, b: float, back: float, metal: str) -> list[Shape]:
    """A café chair (``metal`` frame, rattan seat and back) at (``a``, ``b``), its back on the side
    of ``back`` (-1: towards smaller ``a``, 1: larger), drawn back to front."""
    seat, r = 0.56, 0.17
    edge = a + back * (r - 0.02)
    curve = [(edge, b + 0.17 * math.cos(t), seat + 0.52 + 0.14 * math.sin(t)) for t in [math.pi * k / 10 for k in range(11)]]
    outer = f.poly([(edge, b - 0.17, seat), (edge, b + 0.17, seat), *curve], f.side(metal))
    inner = f.poly([(edge, b + 0.11, seat + 0.12)] + [(edge, b + 0.11 * math.cos(t), seat + 0.5 + 0.1 * math.sin(t)) for t in [math.pi * k / 10 for k in range(11)]]
                   + [(edge, b - 0.11, seat + 0.12)], f.side(RATTAN))
    legs: list[Shape] = []
    for da, db in ((-0.11, -0.11), (0.11, -0.11), (-0.11, 0.11), (0.11, 0.11)):
        x, y, z = f.p(a + da, b + db, 0.0)
        legs.append(Upright(x, y, z, z + seat, 0.018, metal))
    x, y, z = f.p(a, b, seat)
    cushion = [Upright(x, y, z - 0.05, z, r, metal), Disc((x, y, z), r, RATTAN)]
    if back < 0:
        return [outer, inner, *legs, *cushion]
    return [*legs, *cushion, outer, inner]


def _cafe_table(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A round café table (``detail`` its marble top, ``color`` its iron foot) between two bistro
    chairs, with two cups of coffee on saucers and a flower in a little vase."""
    w, d = f.width, f.depth
    metal = look.main
    cx, cy = w / 2, d / 2
    shapes = _bistro_chair(f, 0.3, cy, -1.0, metal)
    x, y, z = f.p(cx, cy, 0.0)
    top = z + 0.94
    shapes += [Disc((x, y, z + 0.01), 0.2, shade(metal, 0.1)), Upright(x, y, z, top - 0.04, 0.035, metal),
               Upright(x, y, top - 0.04, top, 0.4, shade(look.detail, 0.12)), Disc((x, y, top), 0.4, look.detail)]
    for da in (-0.2, 0.2):
        cup = f.p(cx + da, cy + 0.06, 0.941)
        shapes += [Disc(cup, 0.075, "#FFFFFF"), Upright(cup[0], cup[1], cup[2], cup[2] + 0.07, 0.042, "#FFFFFF"),
                   Disc((cup[0], cup[1], cup[2] + 0.07), 0.034, "#6B4A2E", False)]
    vase = f.p(cx, cy - 0.12, 0.941)
    shapes += [Upright(vase[0], vase[1], vase[2], vase[2] + 0.12, 0.028, mix(GLASS, "#7FC8E8", 0.3)),
               Line((vase, (vase[0], vase[1], vase[2] + 0.22)), "#4C9A55", 1.4), _round((vase[0], vase[1], vase[2] + 0.24), 0.045, "#E2574C")]
    return shapes + _bistro_chair(f, w - 0.3, cy, 1.0, metal)


def _counter_body(f: _Frame, a0: float, a1: float, body: str, worktop: str) -> list[Shape]:
    """A shop counter's body from ``a0`` to ``a1`` (``body``) with planks on its front, a trim and
    a ``worktop`` over it (its top at 1.12)."""
    b0, b1 = 0.14, f.depth - 0.12
    shapes = f.box(a0, b0, 0.0, a1, b1, 1.04, body)
    shapes.append(_plinth(f, a0 + 0.01, a1 - 0.01, b1, body))
    count = max(2, round((a1 - a0) / 0.17))
    for k in range(1, count):
        a = a0 + (a1 - a0) * k / count
        shapes.append(Line((f.p(a, b1 + 0.002, 0.09), f.p(a, b1 + 0.002, 0.88)), shade(body, 0.28), 0.7))
    shapes.append(_rect(f, a0 + 0.01, a1 - 0.01, b1 + 0.003, 0.88, 0.98, f.front(mix(body, SHINE, 0.12))))
    return shapes + f.box(a0 - 0.03, b0 - 0.02, 1.04, a1 + 0.03, b1 + 0.06, 1.12, worktop)


def _counter(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A shop counter (``color`` its wood, ``detail`` its worktop) with a service bell; small
    things go on its top."""
    w = f.width
    shapes = _counter_body(f, 0.06, w - 0.06, look.main, look.detail)
    x, y, z = f.p(w - 0.35, 0.45, 1.12)
    return shapes + [Disc((x, y, z + 0.005), 0.08, "#3A3F4B"), _round((x, y, z + 0.045), 0.065, CHROME),
                     Upright(x, y, z + 0.08, z + 0.12, 0.012, "#3A3F4B")]


def _cash_register(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A cash register (``color``) on a piece of shop counter: a cash drawer, a sloping keyboard
    (its big key in the ``detail`` colour), a display showing a price and a receipt curling out."""
    w = f.width
    body = look.main
    shapes = _counter_body(f, 0.06, w - 0.06, COUNTER_WOOD, "#EEE6D8")
    a0, a1 = 0.2, w - 0.2
    shapes += f.box(a0, 0.24, 1.12, a1, 0.84, 1.3, body)
    shapes.append(Line((f.p(a0 + 0.03, 0.841, 1.27), f.p(a1 - 0.03, 0.841, 1.27)), shade(body, 0.3), 0.8))
    shapes.append(Line((f.p(0.5 * w - 0.08, 0.842, 1.21), f.p(0.5 * w + 0.08, 0.842, 1.21)), shade(body, 0.45), 2.2))
    shapes += f.box(a0, 0.24, 1.3, a1, 0.5, 1.52, body)
    slope = [(a0, 0.5, 1.52), (a1, 0.5, 1.52), (a1, 0.82, 1.34), (a0, 0.82, 1.34)]
    shapes.append(f.poly([(a1, 0.5, 1.3), (a1, 0.82, 1.3), (a1, 0.82, 1.34), (a1, 0.5, 1.52)], f.side(body)))
    shapes.append(f.poly([(a0, 0.82, 1.3), (a1, 0.82, 1.3), (a1, 0.82, 1.34), (a0, 0.82, 1.34)], f.front(body)))
    shapes.append(f.poly(slope, mix(body, SHINE, 0.1)))

    def on_slope(u: float, s: float) -> tuple[float, float, float]:
        return (a0 + (a1 - a0) * u, 0.5 + 0.32 * s, 1.52 - 0.18 * s + 0.002)

    for row in range(3):
        for col in range(4):
            u0, s0 = 0.1 + col * 0.2, 0.15 + row * 0.27
            big = col == 3 and row == 2
            color = look.detail if big else ("#F4F6FA" if col < 3 else "#B9BFC9")
            shapes.append(f.poly([on_slope(u0, s0), on_slope(u0 + 0.14, s0), on_slope(u0 + 0.14, s0 + 0.18), on_slope(u0, s0 + 0.18)], color))
    shapes += f.box(a0 + 0.12, 0.3, 1.52, a1 - 0.12, 0.42, 1.72, shade(body, 0.12))
    shapes.append(_rect(f, a0 + 0.16, a1 - 0.16, 0.421, 1.56, 1.68, "#24342A", False))
    for k, digit in enumerate((0.0, 0.28, 0.6, 0.86)):   # a price in green digits
        u = a0 + 0.2 + (a1 - a0 - 0.48) * digit
        shapes.append(_rect(f, u, u + 0.05, 0.422, 1.585, 1.655, DISPLAY_GREEN, False))
    shapes.append(_round(f.p(a0 + 0.2 + (a1 - a0 - 0.48) * 0.47, 0.422, 1.59), 0.006, DISPLAY_GREEN, False))
    paper = [(a1 - 0.2, 0.26, 1.52), (a1 - 0.08, 0.26, 1.52), (a1 - 0.08, 0.26, 1.7), (a1 - 0.11, 0.3, 1.78), (a1 - 0.2, 0.3, 1.74)]
    return shapes + [f.poly(paper, "#FFFFFF")]


def _cake(base: Point3, radius: float, height: float, sponge: str, icing: str) -> list[Shape]:
    """A round cake on a plate: its sponge, its icing on top and a cherry."""
    x, y, z = base
    return [Disc((x, y, z + 0.004), radius + 0.025, "#FFFFFF"), Upright(x, y, z, z + height, radius, sponge),
            Upright(x, y, z + height - 0.03, z + height, radius + 0.004, icing), Disc((x, y, z + height), radius, mix(icing, SHINE, 0.15)),
            _round((x, y, z + height + 0.03), 0.028, CHERRY)]


def _cupcake(base: Point3, icing: str) -> list[Shape]:
    """A cupcake: its paper case and a swirl of icing."""
    x, y, z = base
    return [Upright(x, y, z, z + 0.07, 0.045, "#F4D9A0"), _round((x, y, z + 0.1), 0.05, icing), _round((x, y, z + 0.15), 0.03, mix(icing, SHINE, 0.3))]


def _sparkle(point: Point3, size: float) -> Poly:
    """A small four-pointed white sparkle (on a gem)."""
    return Poly(tuple(_screen(point, (size if k % 2 == 0 else size * 0.25) * math.cos(math.pi * k / 4),
                              (size if k % 2 == 0 else size * 0.25) * math.sin(math.pi * k / 4)) for k in range(8)), "#FFFFFF", False)


def _jewel_stand(f: _Frame, a: float, b: float, z: float, gem: str, kind: int) -> list[Shape]:
    """A jewel on a small velvet block or stand: a ring (``kind`` 0), a pendant necklace (1) or a
    pair of earrings (2), with a gem of colour ``gem`` and a sparkle."""
    x, y, zz = f.p(a, b, z)
    if kind == 0:
        ring = (x, y, zz + 0.1)
        return [*f.box(a - 0.06, b - 0.06, z, a + 0.06, b + 0.06, z + 0.06, "#3A2A44"),
                Line(tuple(_screen(ring, 0.04 * math.cos(math.pi * k / 8), 0.035 * math.sin(math.pi * k / 8)) for k in range(17)), GOLD, 2.2),
                _round(_screen(ring, 0.0, 0.045), 0.025, gem), _sparkle(_screen(ring, 0.03, 0.08), 0.03)]
    top = (x, y, zz + 0.3)
    shapes: list[Shape] = [Upright(x, y, zz, zz + 0.3, 0.012, "#3A2A44"), Disc((x, y, zz + 0.004), 0.05, "#3A2A44")]
    if kind == 1:
        chain = [_screen(top, 0.09 * math.cos(t), 0.12 * math.sin(t)) for t in [math.pi * (1.0 + k / 12) for k in range(13)]]
        return shapes + [Line(tuple(chain), GOLD, 1.6), _round(_screen(top, 0.0, -0.15), 0.035, gem), _sparkle(_screen(top, 0.03, -0.12), 0.035)]
    return shapes + [Line((_screen(top, -0.05, 0.0), _screen(top, 0.05, 0.0)), "#3A2A44", 2.2),
                     _round(_screen(top, -0.05, -0.05), 0.022, gem), _round(_screen(top, 0.05, -0.05), 0.022, gem)]


def _display_case(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A shop's glass display case on a cabinet (``color``): ``kind: cakes`` (default) shows cakes
    and cupcakes iced in the ``detail`` colour and others; ``jewels`` rings, necklaces and
    earrings on velvet (a dark shade of ``detail``)."""
    w, d = f.width, f.depth
    body = look.main
    kind = f.item.features[0] if f.item.features else DISPLAY_CASES[0]
    a0, a1, b0, b1, low, high = 0.06, w - 0.06, 0.14, d - 0.1, 0.55, 1.4
    shapes = f.box(a0, b0, 0.0, a1, b1, low, body)
    shapes.append(_plinth(f, a0 + 0.01, a1 - 0.01, b1, body))
    shapes.append(_rect(f, a0 + 0.08, a1 - 0.08, b1 + 0.002, 0.14, low - 0.08, f.front(mix(body, SHINE, 0.1))))
    floor = "#F7F4EC" if kind == "cakes" else shade(look.detail, 0.6)
    pane = mix(GLASS, "#FFFFFF", 0.35)
    shapes.append(f.poly([(a0, b0, low + 0.001), (a1, b0, low + 0.001), (a1, b1, low + 0.001), (a0, b1, low + 0.001)], floor))
    shapes.append(f.poly([(a0, b0, low), (a1, b0, low), (a1, b0, high), (a0, b0, high)], pane, False))
    shapes.append(f.poly([(a0, b0, low), (a0, b1, low), (a0, b1, high), (a0, b0, high)], shade(pane, 0.06), False))
    shelf = 0.97
    span = a1 - a0
    if kind == "cakes":
        icings = (look.detail, "#FFFFFF", "#7A4A32", look.detail)
        for k in range(4):   # cupcakes on the glass shelf, at the back
            shapes += _cupcake(f.p(a0 + span * (0.14 + 0.24 * k), b0 + 0.18, shelf), icings[k])
    else:
        for k in range(3):
            shapes += _jewel_stand(f, a0 + span * (0.2 + 0.3 * k), b0 + 0.18, shelf, GEMS[(k + 1) % len(GEMS)], 1 + k % 2)
    shapes.append(f.poly([(a0 + 0.02, b0 + 0.02, shelf), (a1 - 0.02, b0 + 0.02, shelf), (a1 - 0.02, b0 + 0.42, shelf), (a0 + 0.02, b0 + 0.42, shelf)],
                         mix(GLASS, SHINE, 0.2)))
    if kind == "cakes":
        for k, (sponge, icing) in enumerate(((CAKES[0], look.detail), (CAKES[1], "#5A3424"), (CAKES[2], "#FFFFFF"))):
            shapes += _cake(f.p(a0 + span * (0.2 + 0.3 * k), b1 - 0.3, low), 0.15, 0.17 + 0.03 * (k % 2), sponge, icing)
    else:
        for k in range(4):
            shapes += _jewel_stand(f, a0 + span * (0.14 + 0.24 * k), b1 - 0.28, low, GEMS[k % len(GEMS)], 0)
    edge = CHROME
    for a, b in ((a0, b1), (a1, b1), (a1, b0)):
        shapes.append(Line((f.p(a, b, low), f.p(a, b, high)), edge, 2.0))
    shapes.append(Line(tuple(f.p(a, b, high) for a, b in ((a0, b1), (a1, b1), (a1, b0), (a0, b0), (a0, b1))), edge, 2.0))
    for u in (0.08, 0.72):   # glints on the front glass
        shapes.append(Line((f.p(a0 + span * u, b1, low + 0.12), f.p(a0 + span * u + 0.2, b1, high - 0.1)), mix(GLASS, SHINE, 0.7), 1.6))
    return shapes


# ----- a market and a street: market stall, vending machine -------------------------------------------------


def _market_stall(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A market stall: a wooden table with crates of apples, oranges and limes, a chalk price board,
    four posts and a striped awning (``color`` and ``detail``) with a scalloped edge."""
    w, d = f.width, f.depth
    a0, a1, b0, b1 = 0.1, w - 0.1, 0.12, d - 0.1
    post = 0.07
    high, low, out = 2.62, 2.2, b1 + 0.18

    def awning_z(b: float) -> float:
        return high + (low - high) * (b - b0) / (out - b0)

    shapes = f.box(a0, b0, 0.0, a0 + post, b0 + post, high, WOOD) + f.box(a1 - post, b0, 0.0, a1, b0 + post, high, WOOD)
    t0, t1 = b0 + 0.22, b1 - 0.04
    shapes += f.box(a0 + 0.05, t0, 0.0, a1 - 0.05, t1, 0.76, mix(WOOD, SHINE, 0.12))
    for k in range(1, 6):
        a = a0 + 0.05 + (a1 - a0 - 0.1) * k / 6
        shapes.append(Line((f.p(a, t1 + 0.002, 0.04), f.p(a, t1 + 0.002, 0.72)), shade(WOOD, 0.2), 0.7))
    count = 3
    span = (a1 - a0 - 0.2) / count
    for k in range(count):
        c0, c1 = a0 + 0.1 + k * span + 0.03, a0 + 0.1 + (k + 1) * span - 0.03
        tilt = 0.06   # the crates lean towards the buyers: their backs sit higher
        shapes += f.box(c0, t0 + 0.04, 0.76, c1, t1 - 0.04, 0.96 + tilt, CRATE)
        shapes.append(Line((f.p(c0 + 0.02, t1 - 0.039, 0.86), f.p(c1 - 0.02, t1 - 0.039, 0.86)), shade(CRATE, 0.35), 0.8))
        fruit = FRUIT[k % len(FRUIT)]
        for row in range(3):
            n = 4
            for j in range(n):
                a = c0 + 0.07 + (c1 - c0 - 0.14) * (j + 0.5 * (row % 2)) / (n - 0.5)
                b = t0 + 0.12 + (t1 - t0 - 0.24) * row / 2
                shapes.append(_round(f.p(a, b, 0.96 + tilt - 0.02 * row + 0.04), 0.058, mix(fruit, SHINE, 0.06 * row)))
    board = (a0 + 0.3, a0 + 0.78)
    shapes.append(_rect(f, board[0], board[1], t1 + 0.004, 0.32, 0.6, "#2F4A3A"))
    shapes.append(Line((f.p(board[0] + 0.06, t1 + 0.005, 0.5), f.p(board[0] + 0.2, t1 + 0.005, 0.52), f.p(board[0] + 0.32, t1 + 0.005, 0.48)), "#F4F6FA", 1.2))
    shapes.append(Line((f.p(board[0] + 0.08, t1 + 0.005, 0.4), f.p(board[1] - 0.1, t1 + 0.005, 0.4)), "#F4F6FA", 1.2))
    shapes += f.box(a0, b1 - post, 0.0, a0 + post, b1, awning_z(b1), WOOD) + f.box(a1 - post, b1 - post, 0.0, a1, b1, awning_z(b1), WOOD)
    e0, e1 = a0 - 0.08, a1 + 0.08
    stripes = max(4, round((e1 - e0) / 0.24))
    for k in range(stripes):
        u0, u1 = e0 + (e1 - e0) * k / stripes, e0 + (e1 - e0) * (k + 1) / stripes
        color = look.main if k % 2 == 0 else look.detail
        shapes.append(f.poly([(u0, b0 - 0.04, high), (u1, b0 - 0.04, high), (u1, out, low), (u0, out, low)], color, (False, True, False, True)))
    shapes.append(f.poly([(e1, b0 - 0.04, high), (e1, out, low), (e1, out, low - 0.04), (e1, b0 - 0.04, high - 0.04)], f.side(look.main)))
    for k in range(stripes):   # the scalloped edge hanging in front
        u0, u1 = e0 + (e1 - e0) * k / stripes, e0 + (e1 - e0) * (k + 1) / stripes
        color = look.main if k % 2 == 0 else look.detail
        arc = [((u0 + u1) / 2 + (u1 - u0) / 2 * math.cos(t), out, low - 0.04 - 0.12 * math.sin(t)) for t in [math.pi * j / 8 for j in range(9)]]
        shapes.append(f.poly([(u1, out, low), *arc, (u0, out, low)], f.front(color)))
    return shapes


def _vending_machine(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A drinks vending machine (``color``): a window of drinks on shelves, a sign band
    (``detail``), buttons, a coin slot and a pick-up flap; on, its window, sign and buttons glow
    and it lights the floor in front of it."""
    w, d = f.width, f.depth
    a0, a1, b0, b1, h = 0.1, w - 0.1, 0.22, d - 0.1, 2.15
    on = state.on
    body = look.main
    shapes = light_pool(f.p(w / 2, d + 0.1, 0.01), 0.7, 0.8) if on else []
    shapes += f.box(a0, b0, 0.0, a1, b1, h, body)
    face = b1 + 0.002
    shapes.append(_plinth(f, a0 + 0.01, a1 - 0.01, b1, body, 0.1))
    sign = (h - 0.34, h - 0.08)
    if on:
        shapes.append(_glow_rect(f, a0 + 0.05, a1 - 0.05, face, sign[0], sign[1], mix(look.detail, SHINE, 0.2)))
    else:
        shapes.append(_rect(f, a0 + 0.05, a1 - 0.05, face, sign[0], sign[1], f.front(look.detail)))
    swoosh = [(a0 + 0.14 + (a1 - a0 - 0.28) * s, face + 0.001, sign[0] + 0.13 + 0.07 * math.sin(math.pi * 2 * s)) for s in [k / 10 for k in range(11)]]
    shapes.append(Line(tuple(f.p(*q) for q in swoosh), "#FFFFFF", 2.4))
    g0, g1, z0, z1 = a0 + 0.06, a0 + (a1 - a0) * 0.68, 0.62, sign[0] - 0.08
    back = mix(look.detail, SHINE, 0.7) if on else "#2E3A48"
    shapes.append(_rect(f, g0, g1, face, z0, z1, back, True, on))
    rows, per = 4, 4
    for row in range(rows):
        z = z0 + 0.04 + (z1 - z0 - 0.06) * row / rows
        shapes.append(_rect(f, g0 + 0.01, g1 - 0.01, face + 0.001, z - 0.025, z, "#8A93A3" if not on else "#C9CED6", False, on))
        for k in range(per):
            a = g0 + 0.05 + (g1 - g0 - 0.1) * (k + 0.5) / per
            color = DRINKS[(row * 2 + k) % len(DRINKS)]
            fill = mix(color, SHINE, 0.12) if on else shade(color, 0.3)
            shapes.append(_rect(f, a - 0.04, a + 0.04, face + 0.002, z, z + 0.18, fill, True, on))
            shapes.append(_rect(f, a - 0.04, a + 0.04, face + 0.003, z + 0.13, z + 0.16, mix(fill, SHINE, 0.5), False, on))
    shapes.append(Line((f.p(g0 + 0.06, face + 0.004, z0 + 0.1), f.p(g0 + 0.24, face + 0.004, z1 - 0.1)), mix(GLASS, SHINE, 0.7), 1.6))
    p0, p1 = g1 + 0.06, a1 - 0.06
    shapes.append(_indicator(f, p0, p1, face, z1 - 0.14, z1 - 0.02, DISPLAY_GREEN, on))
    for k in range(5):
        z = z1 - 0.26 - k * 0.12
        shapes.append(_indicator(f, p0 + 0.03, p1 - 0.03, face, z, z + 0.07, mix(look.detail, SHINE, 0.3), on) if on
                      else _rect(f, p0 + 0.03, p1 - 0.03, face, z, z + 0.07, "#E6EAF0"))
    shapes.append(_rect(f, (p0 + p1) / 2 - 0.015, (p0 + p1) / 2 + 0.015, face, z1 - 0.98, z1 - 0.86, "#2B2F3A", False))
    shapes.append(_rect(f, g0 + 0.06, g1 - 0.06, face, 0.2, 0.44, "#2B2F3A"))
    shapes.append(Line((f.p(g0 + 0.14, face + 0.001, 0.4), f.p(g1 - 0.14, face + 0.001, 0.4)), CASING, 1.6))
    return shapes


#: The drawings of this module's kinds (each by its frame, look and state).
DRAWINGS: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {
    "bathtub": _bathtub, "wardrobe": _wardrobe, "crib": _crib, "cafe_table": _cafe_table, "counter": _counter,
    "cash_register": _cash_register, "display_case": _display_case, "market_stall": _market_stall, "vending_machine": _vending_machine,
}


def motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """No moving parts here (the module interface of :data:`~vidgen.cartoon.iso_objects.MORE_MODULES`)."""
    return []


__all__ = ["DRAWINGS", "motion"]
