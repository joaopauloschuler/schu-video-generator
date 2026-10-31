"""Home iso objects (DESIGN.md §104, Phase AC): a fireplace, a kitchen counter, a stove, a sink, a
tall bookshelf, an armchair, a floor lamp, a TV and a piano. No manim.

Drawn like :mod:`vidgen.cartoon.iso_objects`' objects (its frame, shading and helpers), which
looks each kind of this module up in :data:`DRAWINGS` and its moving parts in :func:`motion`.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from vidgen.cartoon.iso_drawing import Disc, Line, Poly, Shape, Upright, mix, shade
from vidgen.cartoon.iso_objects import (
    BOOK_COLORS,
    CASING,
    DARK_SCREEN,
    DISPLAY_GREEN,
    LED_OFF,
    LIT_CORE,
    LIT_GLASS,
    SHINE,
    WOOD,
    Motion,
    ObjectLook,
    _arc,
    _bubble,
    _face_circle,
    _fade,
    _Frame,
    _glow_rect,
    _indicator,
    _legs,
    _rising,
    _round,
    _screen,
    light_pool,
)
from vidgen.world.iso import ObjectState
from vidgen.world.iso_view import ISO_RISE, Point3

#: A fire's colours: its outer flames, their middles, the embers, the soot of a firebox and the
#: warm light it throws on the floor.
FIRE_ORANGE = "#FF8A3D"
FIRE_YELLOW = "#FFD75E"
EMBER = "#FF5A2A"
SOOT = "#2A1E1A"
FIRE_LIGHT = "#FFB45E"
#: A stove's hob and a pot's steam; a TV picture's hill and sun; chrome.
HOB = "#3A3F4B"
STEAM = "#FFFFFF"
HILL = "#5BC46A"
SUN = "#FFE27A"
CHROME = "#C9CED6"
#: The radius (tile units) of the pool of light under a lit floor lamp.
LIGHT_POOL_RADIUS_FLOOR = 0.95
#: Seconds of a puff of a pot's steam and of a cloud crossing a TV's screen.
POT_STEAM_SECONDS = 2.0
TV_CLOUD_SECONDS = 7.0


def _flicker(now: float, k: int) -> float:
    """A flame's or a screen's flicker (0..1) at ``now``, different for each ``k``."""
    return 0.5 + 0.5 * math.sin(2 * math.pi * now * (2.3 + 0.4 * k) + k) * math.sin(2 * math.pi * now * (1.3 + 0.3 * k) + 2 * k)


def _flame(base: Point3, half: float, height: float, sway: float) -> tuple[Point3, ...]:
    """A flame standing at ``base``: a round bottom ``half`` wide (tile widths), its tip
    ``height`` up the picture and ``sway`` across."""
    bottom = _arc(0.0, half, half, half, math.pi, 2 * math.pi, 8)
    return tuple(_screen(base, du, dv) for du, dv in [*bottom, (half * 0.75 + sway * 0.3, half + (height - half) * 0.45), (sway, height),
                                                      (-half * 0.75 + sway * 0.3, half + (height - half) * 0.45)])


# ----- a fireplace ---------------------------------------------------------------------------------------

#: A fireplace's opening on its front: its middle across, half its width, the face it is on and
#: its bottom and the top of its sides (an arch over them).
FIRE_OPENING = (0.42, 0.8, 0.12, 0.8)
FIRE_ARCH = 0.14
#: Its flames: (across from the middle, half width and height on the picture in tile widths).
FLAMES = ((-0.2, 0.085, 0.27), (0.0, 0.11, 0.36), (0.19, 0.08, 0.24))


def _fire(f: _Frame, now: float) -> list[Motion]:
    """A fireplace's fire at ``now``: its light on the floor, three flames with yellow middles and
    two sparks rising in the opening; the same parts at any time."""
    half, b, z0, z1 = FIRE_OPENING
    cx = f.width / 2
    glow = _flicker(now, 5)
    parts = [Motion(tuple(f.p(cx + 0.75 * math.cos(t), f.depth + 0.25 + 0.45 * math.sin(t), 0.012) for t in [2 * math.pi * k / 20 for k in range(20)]),
                    FIRE_LIGHT, 0.2 + 0.16 * glow, False, True, pool=True)]   # faint by day like a pool of light
    for k, (du, width, height) in enumerate(FLAMES):
        lick = _flicker(now, k)
        base = f.p(cx + du, b + 0.004, z0 + 0.1)
        tall = height * (0.8 + 0.35 * lick)
        sway = 0.03 * math.sin(2 * math.pi * now * (1.1 + 0.2 * k) + k)
        parts.append(Motion(_flame(base, width, tall, sway), FIRE_ORANGE, 0.95, False, True))
        parts.append(Motion(_flame(_screen(base, 0.0, 0.005), width * 0.55, tall * 0.6, sway * 0.6), FIRE_YELLOW, 1.0, False, True))
    for k in range(2):
        rise = _rising(now, k, 2, 1.4)
        point = _screen(f.p(cx + (0.12 if k else -0.1), b + 0.005, z0 + 0.35), 0.04 * math.sin(2 * math.pi * rise * 2 + k), (z1 - z0 - 0.3) * ISO_RISE * rise)
        parts.append(_bubble(point, 0.014, FIRE_YELLOW, _fade(rise)))
    return parts


def _fireplace(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A brick fireplace against the wall (``color`` its bricks, ``detail`` its stone): a hearth,
    an arched firebox with logs, a mantel shelf with candles and the chimney breast; lit when on
    (flames, embers and warm light on the floor; the stage makes them flicker)."""
    w, d = f.width, f.depth
    brick, stone = look.main, look.detail
    half, b, z0, z1 = FIRE_OPENING
    cx = w / 2
    on = state.on
    shapes: list[Shape] = []
    if on:   # the warm light on the floor in front of it
        shapes.append(Disc(f.p(cx, d + 0.25, 0.01), 0.85, FIRE_LIGHT, False, 0.45, holds_snow=False, pool=True))
    shapes += f.box(0.1, 0.08, 0.0, w - 0.1, b, 1.25, brick)
    mortar = shade(brick, 0.3)
    for k, z in enumerate((0.3, 0.55, 0.8, 1.05)):
        shapes.append(Line((f.p(0.12, b + 0.001, z), f.p(w - 0.12, b + 0.001, z)), mortar, 0.7))
        for j in range(5):
            a = 0.3 + j * 0.36 + (0.18 if k % 2 else 0.0)
            if a < w - 0.15:
                shapes.append(Line((f.p(a, b + 0.001, z - 0.25), f.p(a, b + 0.001, z)), mortar, 0.6))
    arch = [(cx + (half + 0.08) * math.cos(t), b + 0.002, z1 + (FIRE_ARCH + 0.08) * math.sin(t)) for t in [math.pi * k / 12 for k in range(13)]]
    shapes.append(f.poly([(cx + half + 0.08, b + 0.002, 0.04), *arch, (cx - half - 0.08, b + 0.002, 0.04)], f.front(stone)))
    opening = [(cx + half * math.cos(t), b + 0.003, z1 + FIRE_ARCH * math.sin(t)) for t in [math.pi * k / 12 for k in range(13)]]
    inside = mix(FIRE_ORANGE, SOOT, 0.55) if on else SOOT
    shapes.append(f.poly([(cx + half, b + 0.003, z0), *opening, (cx - half, b + 0.003, z0)], inside, True, on))
    if on:
        shapes.append(f.poly([(cx + half * 0.7, b + 0.0035, z0), *[(cx + half * 0.7 * math.cos(t), b + 0.0035, z0 + 0.35 * math.sin(t))
                                                                    for t in [math.pi * k / 10 for k in range(11)]], (cx - half * 0.7, b + 0.0035, z0)],
                             mix(FIRE_ORANGE, FIRE_YELLOW, 0.4), False, True))
    if on and not look.moving:   # the stage draws the flames over the picture while it burns
        shapes += [Poly(m.points, m.fill, m.ink, m.glow) for m in _fire(f, 0.3)[1:7]]
    log = "#6B4A2E"
    for p, q in (((cx - 0.3, z0 + 0.06), (cx + 0.28, z0 + 0.06)), ((cx - 0.22, z0 + 0.17), (cx + 0.3, z0 + 0.1))):
        ends = f.p(p[0], b + 0.006, p[1]), f.p(q[0], b + 0.006, q[1])
        shapes.append(Poly((_screen(ends[0], 0.0, -0.035), _screen(ends[1], 0.0, -0.035), _screen(ends[1], 0.0, 0.035), _screen(ends[0], 0.0, 0.035)), log))
        shapes.append(_round(ends[1], 0.035, "#C69466"))
    if on:   # embers along the logs
        for du in (-0.18, -0.02, 0.15):
            shapes.append(_round(_screen(f.p(cx + du, b + 0.007, z0 + 0.1), 0.0, 0.0), 0.022, EMBER, False, True))
    shapes += f.box(0.28, 0.08, 1.25, w - 0.28, 0.5, 2.4, brick)
    for z in (1.6, 1.9, 2.2):
        shapes.append(Line((f.p(0.3, 0.501, z), f.p(w - 0.3, 0.501, z)), mortar, 0.7))
    shapes += f.box(0.02, 0.5, 1.25, w - 0.02, 0.94, 1.37, stone)
    for a in (0.3, w - 0.3):   # candles on the mantel
        x, y, z = f.p(a, 0.72, 1.37)
        shapes += [Upright(x, y, z, z + 0.04, 0.06, "#C9A86A"), Upright(x, y, z + 0.04, z + 0.24, 0.03, "#F7F1E3")]
        shapes.append(_round((x, y, z + 0.28), 0.018, FIRE_YELLOW if on else "#5A4A3A", False, on))
    return shapes + f.box(0.1, b, 0.0, w - 0.1, d - 0.02, 0.08, stone)


# ----- a kitchen: counter, stove, sink -----------------------------------------------------------------------


def _counter_front(f: _Frame, a0: float, a1: float, b: float, top: float, body: str, bays: int) -> list[Shape]:
    """The front of a kitchen cabinet from ``a0`` to ``a1`` (its face at ``b``, its top at
    ``top``): a dark plinth, then ``bays`` bays, each a drawer over two doors, with handles."""
    face = f.front(mix(body, SHINE, 0.06))
    handle = "#8A93A3"
    shapes: list[Shape] = [f.poly([(a0, b + 0.001, 0.0), (a1, b + 0.001, 0.0), (a1, b + 0.001, 0.08), (a0, b + 0.001, 0.08)], shade(body, 0.45), False)]
    step = (a1 - a0) / bays
    for k in range(bays):
        u0, u1 = a0 + k * step + 0.035, a0 + (k + 1) * step - 0.035
        mid = (u0 + u1) / 2
        drawer = top - 0.24
        shapes.append(f.poly([(u0, b + 0.002, drawer), (u1, b + 0.002, drawer), (u1, b + 0.002, top - 0.05), (u0, b + 0.002, top - 0.05)], face))
        shapes.append(Line((f.p(mid - 0.1, b + 0.003, top - 0.13), f.p(mid + 0.1, b + 0.003, top - 0.13)), handle, 2.0))
        for v0, v1, knob in ((u0, mid - 0.015, mid - 0.07), (mid + 0.015, u1, mid + 0.07)):
            shapes.append(f.poly([(v0, b + 0.002, 0.12), (v1, b + 0.002, 0.12), (v1, b + 0.002, drawer - 0.04), (v0, b + 0.002, drawer - 0.04)], face))
            shapes.append(Line((f.p(knob, b + 0.003, drawer - 0.22), f.p(knob, b + 0.003, drawer - 0.1)), handle, 2.0))
    return shapes


def _kitchen_counter(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A run of kitchen cabinets (``color``) under a worktop (``detail``), drawers over doors, a
    jar and a crock of spoons at its back corner; small things go on its top."""
    w, d = f.width, f.depth
    body = look.main
    a0, a1, b0, b1 = 0.04, w - 0.04, 0.14, d - 0.08
    shapes = f.box(a0, b0, 0.0, a1, b1, 0.88, body)
    shapes += _counter_front(f, a0 + 0.02, a1 - 0.02, b1, 0.88, body, max(1, round(w)))
    shapes += f.box(a0 - 0.02, b0 - 0.02, 0.88, a1 + 0.02, b1 + 0.04, 0.96, look.detail)
    top = f.base + 0.96
    x, y = f.p(0.28, 0.32, 0.0)[:2]
    shapes += [Upright(x, y, top, top + 0.22, 0.08, "#E9E2D3"), Upright(x, y, top + 0.22, top + 0.25, 0.085, WOOD)]
    x, y = f.p(0.5, 0.36, 0.0)[:2]
    for du, color in ((-0.03, "#8A93A3"), (0.02, WOOD), (0.05, "#E2574C")):   # spoons and a spatula in a crock
        shapes.append(Line(((x, y, top + 0.1), _screen((x, y, top + 0.3), du, 0.0)), color, 1.6))
    return shapes + [Upright(x, y, top, top + 0.16, 0.065, "#4C8DD6")]


def _pot_spot(f: _Frame) -> Point3:
    """Where a stove's pot stands: its bottom's middle on the hob."""
    return f.p(0.38, 0.6, 0.9)


def _stove(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A kitchen stove (``color``) with knobs on its back panel, an oven door with a window, a dark
    hob with two rings and a pot (``detail``) on the third; on: the oven glows, the ring under the
    pot glows red and a light shows on the panel (the stage steams the pot)."""
    w, d = f.width, f.depth
    body = look.main
    on = state.on
    a0, a1, b0, b1 = 0.1, w - 0.1, 0.14, d - 0.08
    shapes = f.box(a0, b0, 0.0, a1, b1, 0.86, body)
    shapes += f.box(a0, b0, 0.86, a1, b1, 0.9, HOB)
    shapes.append(f.poly([(a0 + 0.02, b1 + 0.001, 0.0), (a1 - 0.02, b1 + 0.001, 0.0), (a1 - 0.02, b1 + 0.001, 0.08), (a0 + 0.02, b1 + 0.001, 0.08)],
                         shade(body, 0.45), False))
    shapes.append(f.poly([(a0 + 0.05, b1 + 0.002, 0.12), (a1 - 0.05, b1 + 0.002, 0.12), (a1 - 0.05, b1 + 0.002, 0.72), (a0 + 0.05, b1 + 0.002, 0.72)],
                         f.front(mix(body, SHINE, 0.05))))
    window = mix(FIRE_ORANGE, CASING, 0.3) if on else CASING
    shapes.append(f.poly([(a0 + 0.13, b1 + 0.003, 0.22), (a1 - 0.13, b1 + 0.003, 0.22), (a1 - 0.13, b1 + 0.003, 0.56), (a0 + 0.13, b1 + 0.003, 0.56)],
                         window, True, on))
    shapes.append(Line((f.p(a0 + 0.16, b1 + 0.004, 0.34), f.p(a1 - 0.16, b1 + 0.004, 0.34)), shade(window, 0.3), 0.8))
    shapes.append(Line((f.p(a0 + 0.12, b1 + 0.004, 0.65), f.p(a1 - 0.12, b1 + 0.004, 0.65)), CHROME, 2.6))
    for x, y, r in ((0.72, 0.42, 0.1), (0.74, 0.74, 0.12)):   # two rings, the pot on the third
        ring = f.p(x, y, 0.901)
        shapes.append(Poly(tuple((ring[0] + r * math.cos(t), ring[1] + r * math.sin(t), ring[2]) for t in [2 * math.pi * k / 20 for k in range(20)]),
                           "#20242C", True))
        shapes.append(Poly(tuple((ring[0] + r * 0.5 * math.cos(t), ring[1] + r * 0.5 * math.sin(t), ring[2] + 0.001) for t in [2 * math.pi * k / 16 for k in range(16)]),
                           "#4A5160", False))
    shapes += f.box(a0, b0, 0.9, a1, b0 + 0.12, 1.14, body)
    for a in (0.25, 0.4, 0.58, 0.73):
        shapes.append(f.poly(_face_circle(f, a * w, b0 + 0.121, 1.02, 0.04, 12), CASING))
    shapes.append(_indicator(f, a1 - 0.08, a1 - 0.03, b0 + 0.121, 1.0, 1.05, "#FF9A3D", on))
    x, y, z = _pot_spot(f)
    if on:
        shapes.append(Poly(tuple((x + 0.22 * math.cos(t), y + 0.22 * math.sin(t), z + 0.002) for t in [2 * math.pi * k / 24 for k in range(24)]), EMBER, False, True))
    pot = look.detail
    shapes += [Upright(x, y, z, z + 0.27, 0.18, pot), Disc((x, y, z + 0.27), 0.17, mix(pot, SHINE, 0.25)),
               Upright(x, y, z + 0.27, z + 0.31, 0.035, CASING)]
    for side in (-1.0, 1.0):
        shapes.append(Line((_screen((x, y, z + 0.22), side * 0.12, 0.0), _screen((x, y, z + 0.22), side * 0.19, 0.01)), CASING, 2.6))
    return shapes


def _wisp(centre: Point3, length: float, half: float, bend: float) -> tuple[Point3, ...]:
    """A soft wisp of steam round ``centre``: a narrow S-curved leaf ``length`` tall and ``half``
    wide (tile widths), ``bend`` its sway."""
    steps = 9
    left = [(-half * math.sin(math.pi * s) + bend * math.sin(2 * math.pi * s), length * (s - 0.5)) for s in [k / steps for k in range(steps + 1)]]
    right = [(half * math.sin(math.pi * s) + bend * math.sin(2 * math.pi * s), length * (s - 0.5)) for s in [1 - k / steps for k in range(1, steps)]]
    return tuple(_screen(centre, du, dv) for du, dv in left + right)


def _steam(f: _Frame, now: float) -> list[Motion]:
    """Steam rising from a stove's pot at ``now``: three soft, see-through wisps curling up and
    widening as they fade."""
    x, y, z = _pot_spot(f)
    parts = []
    for k in range(3):
        rise = _rising(now, k, 3, POT_STEAM_SECONDS)
        sway = 0.05 * math.sin(2 * math.pi * (rise + k * 0.37)) + (k - 1) * 0.04
        centre = _screen((x, y, z + 0.32), sway, 0.14 + 0.42 * rise)
        parts.append(Motion(_wisp(centre, 0.2 + 0.12 * rise, 0.035 + 0.035 * rise, 0.04 * (1 if k % 2 else -1)), STEAM, 0.42 * _fade(rise), False, True))
    return parts


def _sink(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A kitchen sink: a cabinet (``color``) with two doors under a worktop (``detail``) with a
    basin and a drain, a chrome tap with a hot and a cold handle."""
    w, d = f.width, f.depth
    body = look.main
    a0, a1, b0, b1 = 0.08, w - 0.08, 0.16, d - 0.08
    shapes = f.box(a0, b0, 0.0, a1, b1, 0.86, body)
    face = f.front(mix(body, SHINE, 0.06))
    shapes.append(f.poly([(a0 + 0.02, b1 + 0.001, 0.0), (a1 - 0.02, b1 + 0.001, 0.0), (a1 - 0.02, b1 + 0.001, 0.08), (a0 + 0.02, b1 + 0.001, 0.08)],
                         shade(body, 0.45), False))
    mid = w / 2
    for u0, u1, knob in ((a0 + 0.05, mid - 0.015, mid - 0.08), (mid + 0.015, a1 - 0.05, mid + 0.08)):
        shapes.append(f.poly([(u0, b1 + 0.002, 0.12), (u1, b1 + 0.002, 0.12), (u1, b1 + 0.002, 0.8), (u0, b1 + 0.002, 0.8)], face))
        shapes.append(Line((f.p(knob, b1 + 0.003, 0.56), f.p(knob, b1 + 0.003, 0.7)), "#8A93A3", 2.0))
    shapes += f.box(a0 - 0.03, b0 - 0.03, 0.86, a1 + 0.03, b1 + 0.04, 0.94, look.detail)
    basin = [(0.22, 0.34), (w - 0.22, 0.34), (w - 0.22, d - 0.16), (0.22, d - 0.16)]
    shapes.append(f.poly([(a, b, 0.941) for a, b in basin], shade(look.detail, 0.22)))
    shapes.append(f.poly([(a + (0.04 if a < mid else -0.04), b + (0.06 if b < 0.5 else -0.02), 0.942) for a, b in basin], shade(look.detail, 0.38), False))
    shapes.append(Disc(f.p(mid, (0.34 + d - 0.16) / 2 + 0.03, 0.943), 0.035, CASING, False, holds_snow=False))
    x, y, z = f.p(mid, b0 + 0.06, 0.94)
    shapes += [Upright(x, y, z, z + 0.04, 0.06, CHROME), Upright(x, y, z + 0.04, z + 0.36, 0.028, CHROME)]
    for a, cap in ((mid - 0.17, "#E2574C"), (mid + 0.17, "#4C8DD6")):
        hx, hy, hz = f.p(a, b0 + 0.06, 0.94)
        shapes += [Upright(hx, hy, hz, hz + 0.08, 0.025, CHROME), Disc((hx, hy, hz + 0.08), 0.035, cap, True, holds_snow=False)]
    spout = [f.p(mid, b0 + 0.06, 0.36 + 0.94), f.p(mid, b0 + 0.18, 0.4 + 0.94), f.p(mid, b0 + 0.27, 0.34 + 0.94), f.p(mid, b0 + 0.28, 0.28 + 0.94)]
    return shapes + [Line(tuple(spout), CHROME, 3.2)]


# ----- a living room: bookshelf, armchair, floor lamp, TV, piano ---------------------------------------------


def _bookshelf_tall(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A tall, narrow bookcase (``color`` its wood) with its back to the wall: five shelves of
    books (some in the ``detail`` colour), one leaning, a lying stack, a little plant and a crown."""
    w = f.width
    wood = look.main
    a0, a1, b0, b1, top = 0.08, w - 0.08, 0.14, 0.6, 2.45
    shapes = f.box(a0, b0, 0.0, a1, b1, top, wood)
    shapes.append(f.poly([(a0 + 0.07, b1, 0.1), (a1 - 0.07, b1, 0.1), (a1 - 0.07, b1, top - 0.08), (a0 + 0.07, b1, top - 0.08)], shade(wood, 0.5), False))
    rows = (0.1, 0.56, 1.02, 1.48, 1.94)
    for k, z in enumerate(rows):
        seed = (f.x0 * 7 + f.y0 * 13 + k * 5) % 11
        a = a0 + 0.1
        end = a1 - (0.3 if k == 2 else 0.2 if k == 4 else 0.1)
        n = 0
        while a < end - 0.1:
            width = 0.07 + ((seed + n * 3) % 4) * 0.012
            height = 0.3 + ((seed + n * 5) % 4) * 0.035
            color = look.detail if (seed + n) % 4 == 0 else BOOK_COLORS[(seed + n * 2) % len(BOOK_COLORS)]
            shapes.append(f.poly([(a, b1, z), (a + width, b1, z), (a + width, b1, z + height), (a, b1, z + height)], f.front(color)))
            a += width + 0.012
            n += 1
        if k in (0, 3):   # the last book leans on the others
            shapes.append(f.poly([(a + 0.01, b1, z), (a + 0.08, b1, z), (a + 0.2, b1, z + 0.3), (a + 0.13, b1, z + 0.33)], f.front(BOOK_COLORS[(seed + 1) % 5])))
        if k == 2:   # a little plant in a pot
            x, y, zz = f.p(a1 - 0.18, (b0 + b1) / 2 + 0.08, z)
            shapes += [Upright(x, y, zz, zz + 0.14, 0.07, "#C8734A")]
            shapes.append(_round(_screen((x, y, zz + 0.14), 0.0, 0.09), 0.08, "#5BA35B"))
            shapes.append(_round(_screen((x, y, zz + 0.14), 0.05, 0.05), 0.05, "#4C9A55"))
        if k == 4:   # a stack of books lying down
            for j in range(3):
                zz = z + j * 0.05
                shapes.append(f.poly([(a1 - 0.27 + 0.01 * j, b1, zz), (a1 - 0.1 - 0.01 * j, b1, zz), (a1 - 0.1 - 0.01 * j, b1, zz + 0.045),
                                      (a1 - 0.27 + 0.01 * j, b1, zz + 0.045)], f.front(BOOK_COLORS[(j + 2) % 5])))
        shapes.append(f.poly([(a0 + 0.07, b1, z - 0.06), (a1 - 0.07, b1, z - 0.06), (a1 - 0.07, b1, z), (a0 + 0.07, b1, z)], f.front(wood)))
    return shapes + f.box(a0 - 0.03, b0 - 0.02, top, a1 + 0.03, b1 + 0.04, top + 0.1, mix(wood, SHINE, 0.08))


def _armchair(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A padded armchair (``color``) on short wooden legs: a high back, two arms, a seat cushion
    and a cushion (``detail``) against its back; one sits on it like on a chair."""
    w, d = f.width, f.depth
    cloth = look.main
    a0, a1, b0, b1, arm = 0.1, w - 0.1, 0.14, d - 0.1, 0.2
    back_legs, front_legs = _legs(f, a0 + 0.05, b0 + 0.05, a1 - 0.05, b1 - 0.05, 0.14, shade(WOOD, 0.2), 0.06)
    shapes = back_legs + f.box(a0, b0, 0.12, a1, b0 + 0.26, 1.12, cloth)
    shapes += f.box(a0 + 0.02, b0 + 0.02, 1.12, a1 - 0.02, b0 + 0.24, 1.2, mix(cloth, SHINE, 0.06))
    shapes += f.box(a0, b0 + 0.26, 0.12, a0 + arm, b1, 0.74, shade(cloth, 0.04))
    shapes += f.box(a0 + arm, b0 + 0.26, 0.12, a1 - arm, b1, 0.48, cloth)
    shapes += f.box(a0 + arm, b0 + 0.26, 0.48, a1 - arm, b1 + 0.01, 0.58, mix(cloth, SHINE, 0.12))
    shapes += f.box(a0 + arm + 0.08, b0 + 0.26, 0.58, a1 - arm - 0.08, b0 + 0.38, 0.92, look.detail)
    shapes += f.box(a1 - arm, b0 + 0.26, 0.12, a1, b1, 0.74, shade(cloth, 0.04))
    return shapes + front_legs


def _cone(x: float, y: float, z0: float, z1: float, r0: float, r1: float, fill: str, *, glow: bool = False) -> Poly:
    """A cone's side (a lamp's shade) from radius ``r0`` at ``z0`` to ``r1`` at ``z1``: its front
    half at the bottom, its back half at the top."""
    front = [(x + r0 * math.cos(t), y + r0 * math.sin(t), z0) for t in [-math.pi / 4 + math.pi * k / 16 for k in range(17)]]
    back = [(x + r1 * math.cos(t), y + r1 * math.sin(t), z1) for t in [3 * math.pi / 4 + math.pi * k / 16 for k in range(17)]]
    return Poly(tuple(front + back), fill, True, glow)


def _floor_lamp(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A standing lamp: a round foot and a thin pole (``detail``) under a cone shade (``color``)
    with a trim; on, the shade glows warm, its top shows the bright bulb and light pools on the
    floor (it lights the characters near it like a lamp)."""
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    z = f.base
    on = state.on
    metal = look.detail
    shapes = light_pool((x, y, z + 0.01), LIGHT_POOL_RADIUS_FLOOR) if on else []
    shapes += [Upright(x, y, z, z + 0.05, 0.19, metal), Upright(x, y, z + 0.05, z + 1.62, 0.022, shade(metal, 0.05))]
    cloth = mix(look.main, LIT_GLASS, 0.45) if on else look.main
    shapes.append(_cone(x, y, z + 1.55, z + 2.0, 0.32, 0.2, cloth, glow=on))
    trim = [(x + 0.32 * math.cos(t), y + 0.32 * math.sin(t), z + 1.585) for t in [-math.pi / 4 + math.pi * k / 16 for k in range(17)]]
    shapes.append(Line(tuple(trim), shade(look.main, 0.3) if not on else LIT_GLASS, 1.6))
    inside = LIT_CORE if on else shade(look.main, 0.4)
    shapes.append(Poly(tuple((x + 0.2 * math.cos(t), y + 0.2 * math.sin(t), z + 2.0) for t in [2 * math.pi * k / 20 for k in range(20)]), inside, True, on))
    if on:
        shapes.append(Disc((x, y, z + 2.001), 0.08, "#FFFFFF", False, glow=True, holds_snow=False))
    return shapes


def _tv_screen(f: _Frame) -> tuple[float, float, float, float, float]:
    """A TV's screen on its front: a from, a to, the face, its bottom and top."""
    return 0.1, f.width - 0.1, 0.501, 0.68, 1.42


def _tv(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A flat TV (``color`` its frame) on a low wooden cabinet: dark when off; on, its screen
    glows with a picture (a sky in the ``detail`` colour, a hill, a sun; the stage flickers it and
    sails a cloud across) and its light shows green."""
    w, d = f.width, f.depth
    cx = w / 2
    shapes = f.box(0.06, 0.3, 0.0, w - 0.06, d - 0.08, 0.46, WOOD)
    face = d - 0.08 + 0.001
    shapes.append(f.poly([(0.12, face, 0.08), (cx - 0.02, face, 0.08), (cx - 0.02, face, 0.38), (0.12, face, 0.38)], shade(WOOD, 0.45), False))
    shapes += f.box(0.16, 0.42, 0.08, 0.4, d - 0.1, 0.14, CASING)   # a game console in the open shelf
    shapes.append(f.poly([(cx + 0.02, face, 0.08), (w - 0.12, face, 0.08), (w - 0.12, face, 0.38), (cx + 0.02, face, 0.38)], f.front(mix(WOOD, SHINE, 0.08))))
    shapes.append(Disc(f.p(cx + 0.1, face + 0.001, 0.23), 0.025, "#F2C14E", False, holds_snow=False))
    shapes += f.box(cx - 0.16, 0.38, 0.46, cx + 0.16, 0.56, 0.49, CASING)
    shapes += f.box(cx - 0.04, 0.42, 0.49, cx + 0.04, 0.48, 0.64, CASING)
    shapes += f.box(0.05, 0.43, 0.62, w - 0.05, 0.5, 1.48, look.main)
    a0, a1, b, z0, z1 = _tv_screen(f)
    if state.on:
        sky = look.detail
        shapes.append(_glow_rect(f, a0, a1, b, z0, z1, sky))
        shapes.append(_glow_rect(f, a0, a1, b + 0.0005, z1 - 0.2, z1, mix(sky, SHINE, 0.35)))
        hill = [(a0, b + 0.001, z0)] + [(a0 + (a1 - a0) * s, b + 0.001, z0 + 0.12 + 0.2 * math.sin(math.pi * s * 1.1)) for s in [k / 10 for k in range(11)]] + [(a1, b + 0.001, z0)]
        shapes.append(f.poly(hill, HILL, False, True))
        sun = (a0 + (a1 - a0) * (0.22 if not f.swap else 0.78), z1 - 0.2)
        shapes.append(f.poly(_face_circle(f, sun[0], b + 0.001, sun[1], 0.08, 16), SUN, False, True))
    else:
        shapes.append(f.poly([(a0, b, z0), (a1, b, z0), (a1, b, z1), (a0, b, z1)], DARK_SCREEN, False))
        shapes.append(f.poly([(a1 - 0.3, b + 0.001, z1 - 0.04), (a1 - 0.18, b + 0.001, z1 - 0.04), (a1 - 0.46, b + 0.001, z0 + 0.04), (a1 - 0.58, b + 0.001, z0 + 0.04)],
                             mix(DARK_SCREEN, SHINE, 0.12), False))
    return shapes + [_indicator(f, w - 0.2, w - 0.13, 0.5011, 0.64, 0.665, DISPLAY_GREEN, state.on)]


def _tv_motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A working TV's screen at ``now``: a cloud sailing across its sky and a flicker over it."""
    a0, a1, b, z0, z1 = _tv_screen(f)
    share = (now % TV_CLOUD_SECONDS) / TV_CLOUD_SECONDS
    a = a0 + 0.12 + (a1 - a0 - 0.24) * share
    seen = min(1.0, share * 8.0, (1.0 - share) * 8.0)
    cloud = mix(SHINE, look.detail, 0.08)
    parts = [Motion(tuple(f.p(*q) for q in _face_circle(f, a + da, b + 0.002, z1 - 0.18 + dz, r, 14)), cloud, seen, False, True)
             for da, dz, r in ((-0.06, 0.0, 0.05), (0.0, 0.03, 0.065), (0.07, 0.0, 0.05))]
    flicker = _flicker(now * 1.7, 2)
    parts.append(Motion(tuple(f.p(aa, b + 0.003, zz) for aa, zz in ((a0, z0), (a1, z0), (a1, z1), (a0, z1))), "#FFFFFF" if flicker > 0.5 else "#16304A",
                        0.04 + 0.12 * abs(flicker - 0.5), False, True))
    return parts


def _piano(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """An upright piano (``color``) against the wall: its tall case, a keyboard of white and black
    keys between two cheeks, sheet music on its stand, two legs and three pedals (``detail``)."""
    w = f.width
    body = look.main
    a0, a1, b0, back = 0.08, w - 0.08, 0.12, 0.52
    shapes = f.box(a0, b0, 0.0, a1, back, 1.6, body)
    shapes += f.box(a0 - 0.02, b0 - 0.02, 1.6, a1 + 0.02, back + 0.03, 1.66, mix(body, SHINE, 0.08))
    shapes.append(f.poly([(a0 + 0.1, back + 0.001, 0.86), (a1 - 0.1, back + 0.001, 0.86), (a1 - 0.1, back + 0.001, 1.5), (a0 + 0.1, back + 0.001, 1.5)],
                         f.front(mix(body, SHINE, 0.1)), True))
    shapes.append(f.poly([(a0 + 0.2, back + 0.002, 0.95), (a0 + 0.26, back + 0.002, 0.95), (a0 + 0.42, back + 0.002, 1.45), (a0 + 0.36, back + 0.002, 1.45)],
                         mix(body, SHINE, 0.25), False))
    cx = w / 2
    for k, (u0, u1) in enumerate(((cx - 0.34, cx - 0.01), (cx + 0.01, cx + 0.34))):   # sheet music
        page = [(u0, back + 0.04, 1.02), (u1, back + 0.04, 1.02), (u1, back + 0.01, 1.36), (u0, back + 0.01, 1.36)]
        shapes.append(f.poly(page, "#F7F4EC"))
        for j in range(4):
            s = 0.2 + j * 0.2
            zz, bb = 1.02 + 0.34 * s, back + 0.04 - 0.03 * s + 0.001
            shapes.append(Line((f.p(u0 + 0.04, bb, zz), f.p(u1 - 0.04, bb, zz)), "#6B6F7A", 0.6))
    shapes += f.box(cx - 0.4, back, 0.98, cx + 0.4, back + 0.06, 1.02, body)
    shapes.append(f.poly([(a0 + 0.06, back + 0.001, 0.08), (a1 - 0.06, back + 0.001, 0.08), (a1 - 0.06, back + 0.001, 0.62), (a0 + 0.06, back + 0.001, 0.62)],
                         f.front(mix(body, SHINE, 0.06)), True))
    for j in (-1, 0, 1):
        shapes += f.box(cx + j * 0.1 - 0.03, back, 0.05, cx + j * 0.1 + 0.03, back + 0.1, 0.08, look.detail)
    for a in (a0 + 0.1, a1 - 0.18):
        shapes += f.box(a, 0.74, 0.0, a + 0.08, 0.82, 0.72, body)
    shapes += f.box(a0, back, 0.72, a0 + 0.12, 0.86, 0.92, body)
    shapes += f.box(a0 + 0.12, back, 0.72, a1 - 0.12, 0.84, 0.8, body)
    k0, k1 = a0 + 0.14, a1 - 0.14
    shapes.append(f.poly([(k0, back + 0.02, 0.801), (k1, back + 0.02, 0.801), (k1, 0.83, 0.801), (k0, 0.83, 0.801)], "#F7F4EC"))
    keys = 28
    for k in range(1, keys):
        a = k0 + (k1 - k0) * k / keys
        shapes.append(Line((f.p(a, back + 0.03, 0.802), f.p(a, 0.83, 0.802)), "#B9BFC9", 0.5))
    for k in range(keys - 1):
        if k % 7 in (2, 6):
            continue
        a = k0 + (k1 - k0) * (k + 1) / keys
        shapes += f.box(a - 0.018, back + 0.02, 0.801, a + 0.018, 0.7, 0.83, "#1E1E26")
    return shapes + f.box(a1 - 0.12, back, 0.72, a1, 0.86, 0.92, body)


#: The drawings of this module's kinds (each by its frame, look and state), and those with
#: moving parts the stage draws while they work (:func:`motion`).
DRAWINGS: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {
    "fireplace": _fireplace, "kitchen_counter": _kitchen_counter, "stove": _stove, "sink": _sink, "bookshelf_tall": _bookshelf_tall,
    "armchair": _armchair, "floor_lamp": _floor_lamp, "tv": _tv, "piano": _piano,
}
MOVING = frozenset({"fireplace", "stove", "tv"})


def motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """The moving parts of a working fireplace (flickering flames, sparks, its light on the
    floor), stove (steam from its pot) or TV (a cloud across its screen, a flicker) at ``now``."""
    kind = f.item.kind
    if kind == "fireplace":
        return _fire(f, now)
    if kind == "stove":
        return _steam(f, now)
    if kind == "tv":
        return _tv_motion(f, look, now)
    return []


__all__ = ["DRAWINGS", "MOVING", "motion"]
