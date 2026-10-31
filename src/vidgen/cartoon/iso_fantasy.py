"""Fantasy iso objects (DESIGN.md §104, Phase AC Step 266): a treasure chest, a cauldron, a giant
crystal, a throne, a torch sconce on a wall, a signpost, a stone archway and a statue. No manim.

Drawn like :mod:`vidgen.cartoon.iso_objects`' objects (its frame, shading and helpers), which
looks each kind of this module up in :data:`DRAWINGS` and its moving parts in :func:`motion`.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from vidgen.cartoon.iso_drawing import Blobs, Disc, Line, Poly, Shape, Upright, mix, shade
from vidgen.cartoon.iso_home import EMBER, FIRE_LIGHT, FIRE_ORANGE, FIRE_YELLOW, SOOT, _flame, _flicker
from vidgen.cartoon.iso_nature import _hull
from vidgen.cartoon.iso_objects import (
    CASING,
    SHINE,
    Motion,
    ObjectLook,
    _arc,
    _bubble,
    _face_circle,
    _fade,
    _flat_circle,
    _Frame,
    _profile,
    _ribbon,
    _rising,
    _round,
    _screen,
    light_pool,
)
from vidgen.cartoon.iso_shop import _rect
from vidgen.world.iso import ObjectState
from vidgen.world.iso_view import ISO_RISE, Point3

#: Gold and its deep shade, gems, a chest's dark inside; stone.
GOLD = "#FFD24A"
GOLD_DEEP = "#E0A526"
GEMS = ("#E2574C", "#4CB8FF", "#5BD18B", "#C77DFF")
CHEST_INSIDE = "#3A2416"
STONE = "#B9B4AA"
#: A treasure chest's body (a from, a to, b at its back and front, its height), how high its
#: rounded lid rises and how far it swings back when open (degrees).
CHEST = (0.16, 0.84, 0.3, 0.76, 0.46)
LID_RISE = 0.16
LID_OPEN = 104.0
#: Its sparkles while open and how long one takes to twinkle (seconds).
SPARKLES = 4
SPARKLE_SECONDS = 1.4
#: A cauldron: its rim's height and radius, its belly on the picture (half width, half height,
#: tile widths); its bubbles and vapour, and how long one takes (seconds).
CAULDRON_RIM = (0.8, 0.32)
BELLY = (0.29, 0.21)
CAULDRON_BUBBLES = 4
BUBBLE_SECONDS = 1.3
VAPOUR = 3
VAPOUR_SECONDS = 2.4
CAULDRON_FLAMES = ((-0.1, 0.05, 0.17), (0.02, 0.065, 0.22), (0.12, 0.05, 0.16))
#: A giant crystal's shards: (a, b in its cell, half width and height on the picture in tile
#: widths, lean across), and how long its glow takes to pulse (seconds).
SHARDS = ((0.3, 0.34, 0.09, 0.82, -0.13), (0.72, 0.32, 0.085, 0.7, 0.15), (0.5, 0.5, 0.16, 1.6, 0.03),
          (0.28, 0.7, 0.08, 0.58, -0.17), (0.7, 0.72, 0.1, 0.86, 0.12))
PULSE_SECONDS = 2.6
#: A torch sconce on a wall's face: its plate (z from .. to), where its torch's cup is (out from
#: the wall, height) and the slab it stands in for the draw order (z from .. to, out from the wall).
SCONCE_PLATE = (1.42, 2.0)
SCONCE_CUP = (0.3, 2.12)
SCONCE_SPAN = (1.35, 2.7, 0.38)
TORCH_FLAMES = ((0.0, 0.085, 0.38), (0.0, 0.045, 0.22))


def _middle(f: _Frame) -> Point3:
    return f.p(f.width / 2, f.depth / 2, 0.0)


def _star(centre: Point3, radius: float) -> tuple[Point3, ...]:
    """A four-pointed twinkle round ``centre`` facing the viewer (``radius`` in tile widths)."""
    return tuple(_screen(centre, (radius if k % 2 == 0 else radius * 0.28) * math.cos(math.pi * k / 4),
                         (radius if k % 2 == 0 else radius * 0.28) * math.sin(math.pi * k / 4)) for k in range(8))


# ----- a treasure chest -------------------------------------------------------------------------------------


def _lid_curve(open_: bool) -> list[tuple[float, float]]:
    """A chest lid's rounded top as (b, z) points from its front edge over to its hinge at the
    back; open, swung back round the hinge by :data:`LID_OPEN`."""
    _, _, b0, b1, h = CHEST
    bc, hb = (b0 + b1) / 2, (b1 - b0) / 2
    points = [(bc + hb * math.cos(t), h + LID_RISE * math.sin(t)) for t in [math.pi * k / 12 for k in range(13)]]
    if not open_:
        return points
    turn = math.radians(LID_OPEN)
    return [(b0 + (b - b0) * math.cos(turn) - (z - h) * math.sin(turn), h + (b - b0) * math.sin(turn) + (z - h) * math.cos(turn)) for b, z in points]


def _treasure_chest(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A wooden chest (``color``) with metal bands, corners and a lock (``detail``) under a
    rounded lid; open, its lid swings back and a heap of gold coins and gems glows in it, warm
    light pools round it (sparkles twinkle over it, the stage moves them)."""
    a0, a1, b0, b1, h = CHEST
    wood, metal = look.main, look.detail
    is_open = state.open
    curve = _lid_curve(is_open)
    shapes: list[Shape] = light_pool(f.p((a0 + a1) / 2, (b0 + b1) / 2 + 0.1, 0.01), 1.05) if is_open else []
    if is_open:   # the lid, swung back behind the body: its rounded back, its end, its inside lit gold
        shapes.append(_hull([f.p(a, b, z) for a in (a0, a1) for b, z in curve], shade(wood, 0.12)))
        shapes.append(f.poly([(a1, b, z) for b, z in curve], f.side(wood)))
        hinge, edge = curve[-1], curve[0]
        shapes.append(f.poly([(a0, *hinge), (a1, *hinge), (a1, *edge), (a0, *edge)], mix(shade(wood, 0.3), GOLD, 0.35), True, True))
        for a in (a0 + 0.12, a1 - 0.12):
            shapes.append(Line(tuple(f.p(a, b, z) for b, z in curve), shade(metal, 0.15), 2.4))
    shapes += f.box(a0, b0, 0.0, a1, b1, h, wood)
    t = 0.05   # its walls' thickness
    if is_open:
        shapes.append(f.poly([(a0 + t, b0 + t, h + 0.001), (a1 - t, b0 + t, h + 0.001), (a1 - t, b1 - t, h + 0.001), (a0 + t, b1 - t, h + 0.001)],
                             CHEST_INSIDE, False))
        cx, cb = (a0 + a1) / 2, (b0 + b1) / 2
        for k, (a, b, r) in enumerate(((cx - 0.16, cb - 0.06, 0.1), (cx + 0.14, cb - 0.07, 0.1), (cx, cb - 0.02, 0.13), (cx - 0.2, cb + 0.1, 0.08),
                                       (cx + 0.19, cb + 0.09, 0.08), (cx + 0.02, cb + 0.12, 0.09))):
            shapes.append(_round(f.p(a, b, h + 0.02), r, GOLD if k % 2 == 0 else GOLD_DEEP, True, True))
        for k, (a, b, dv) in enumerate(((cx - 0.08, cb - 0.04, 0.07), (cx + 0.12, cb + 0.02, 0.05), (cx - 0.17, cb + 0.06, 0.03), (cx + 0.04, cb + 0.1, 0.08))):
            gem = _screen(f.p(a, b, h + 0.02), 0.0, dv)
            shapes.append(_round(gem, 0.035, GEMS[k], True, True, 6))
            shapes.append(_round(_screen(gem, -0.01, 0.012), 0.01, SHINE, False, True, 6))
        for a, b in ((cx - 0.05, cb + 0.0), (cx + 0.08, cb - 0.05)):   # coins' glints
            shapes.append(_round(_screen(f.p(a, b, h + 0.02), 0.0, 0.08), 0.018, SHINE, False, True, 8))
        shapes += f.box(a1 - t, b0, 0.0, a1, b1, h, wood) + f.box(a0, b1 - t, 0.0, a1, b1, h, wood)   # the walls in front of the heap
    for a in (a0 + 0.1, a1 - 0.16):   # bands down its front and side, its lock
        shapes.append(_rect(f, a, a + 0.06, b1 + 0.001, 0.0, h, f.front(metal), False))
    shapes.append(f.poly([(a1 + 0.001, b, z) for b, z in ((b1, 0.0), (b0, 0.0), (b0, 0.06), (b1, 0.06))], f.side(metal), False))
    shapes.append(f.poly([(a1 + 0.001, b, z) for b, z in ((b1, h - 0.06), (b0, h - 0.06), (b0, h), (b1, h))], f.side(metal), False))
    if not is_open:
        shapes.append(_hull([f.p(a, b, z) for a in (a0, a1) for b, z in curve], wood))
        shapes.append(f.poly([(a1, b, z) for b, z in curve], f.side(wood)))
        for a in (a0 + 0.13, a1 - 0.13):
            shapes.append(Line(tuple(f.p(a, b, z + 0.004) for b, z in curve), metal, 2.6))
        shapes.append(Line(tuple(f.p(a1 + 0.002, b, z) for b, z in curve[1:-1]), shade(metal, 0.2), 1.8))
    lock = (a0 + a1) / 2
    shapes.append(_rect(f, lock - 0.065, lock + 0.065, b1 + 0.002, h - 0.16, h + (0.05 if not is_open else -0.02), metal))
    shapes.append(_rect(f, lock - 0.012, lock + 0.012, b1 + 0.003, h - 0.12, h - 0.06, CASING, False))
    if is_open and not look.moving:   # the stage twinkles the sparkles while it is open
        shapes += [Poly(m.points, m.fill, m.ink, m.glow) for m in _chest_sparkles(f, 0.5)[1:] if m.opacity > 0.4]
    return shapes


def _chest_sparkles(f: _Frame, now: float) -> list[Motion]:
    """An open chest's glow at ``now``: a soft golden halo over the heap, then sparkles each
    twinkling in and out as it drifts up."""
    a0, a1, b0, b1, h = CHEST
    heap = _screen(f.p((a0 + a1) / 2, (b0 + b1) / 2, h), 0.0, 0.1)
    beat = 0.5 - 0.5 * math.cos(2 * math.pi * now / SPARKLE_SECONDS)
    parts = [Motion(_round(heap, 0.34 + 0.04 * beat, GOLD).points, GOLD, 0.16 + 0.12 * beat, False, True)]
    for k in range(SPARKLES):
        rise = _rising(now, k, SPARKLES, SPARKLE_SECONDS * 1.6)
        twinkle = math.sin(math.pi * rise)
        spot = _screen(heap, (-0.2, 0.18, -0.05, 0.1)[k], 0.04 + 0.36 * rise)
        parts.append(Motion(_star(spot, 0.03 + 0.03 * twinkle), "#FFF6D0", twinkle, False, True))
    return parts


# ----- a cauldron ------------------------------------------------------------------------------------------


def _cauldron(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """An iron pot (``detail``) on three legs over a little fire of logs, full of potion
    (``color``) with a ladle in it; on, the fire burns and the potion glows (the stage makes it
    bubble and steam and the flames flicker), and warm light pools round it."""
    x, y, z = _middle(f)
    on = state.on
    iron, potion = look.detail, look.main
    rim_z, rim_r = CAULDRON_RIM
    rx, ry = BELLY
    shapes: list[Shape] = light_pool((x, y, z + 0.01), 1.3) if on else []
    shapes.append(Disc((x, y, z + 0.012), 0.24, "#5A5450", False, holds_snow=False))
    if on:
        shapes.append(Disc((x, y, z + 0.02), 0.17, EMBER, False, glow=True, holds_snow=False))
    legs = sorted((2 * math.pi * k / 3 + 0.4 for k in range(3)), key=lambda t: math.cos(t) + math.sin(t))
    foot = lambda t: (x + 0.34 * math.cos(t), y + 0.34 * math.sin(t), z)   # noqa: E731
    top = lambda t: (x + 0.22 * math.cos(t), y + 0.22 * math.sin(t), z + 0.3)   # noqa: E731
    shapes += [Line((top(t), foot(t)), shade(iron, 0.1), 2.4) for t in legs if math.cos(t) + math.sin(t) < 0]
    for t in (0.6, 2.2):   # logs under it, crossed
        shapes.append(_ribbon((x + 0.24 * math.cos(t), y + 0.24 * math.sin(t), z + 0.04), (x - 0.24 * math.cos(t), y - 0.24 * math.sin(t), z + 0.04),
                              0.035, "#7A5236" if not on else shade("#7A5236", 0.1)))
        shapes.append(_round((x - 0.24 * math.cos(t), y - 0.24 * math.sin(t), z + 0.04), 0.035, "#E9C99A"))
    if on and not look.moving:   # the stage makes the flames flicker while it is on
        shapes += [Poly(m.points, m.fill, m.ink, m.glow) for m in _cauldron_fire(f, 0.4)]
    belly = (x, y, z)
    lift = rim_z * ISO_RISE - ry + 0.04   # the belly's middle up the picture: its top just under the rim
    shapes.append(_profile(belly, [(du, dv + lift) for du, dv in _arc(0.0, 0.0, rx, ry, 0.0, 2 * math.pi, 28)], iron))
    shapes.append(_profile(belly, [(du, dv + lift) for du, dv in _arc(0.07, -0.02, rx * 0.72, ry * 0.7, -0.4, 1.3, 10)], shade(iron, 0.25), False))
    shapes.append(_profile(belly, [(du, dv + lift) for du, dv in _arc(-0.1, 0.05, rx * 0.55, ry * 0.55, 1.9, 2.8, 6)], mix(iron, SHINE, 0.3), False))
    shapes += [Line((top(t), foot(t)), iron, 2.4) for t in legs if math.cos(t) + math.sin(t) >= 0]
    rim = (x, y, z + rim_z)
    shapes.append(Poly(_flat_circle(rim, rim_r, 28), mix(iron, SHINE, 0.12)))
    liquid = mix(potion, SHINE, 0.15) if on else shade(potion, 0.3)
    shapes.append(Poly(_flat_circle((x, y, z + rim_z + 0.004), rim_r - 0.06, 28), liquid, False, on, holds_snow=False))
    if on:   # foam at the rim
        shapes += [_round((x + 0.2 * math.cos(t), y + 0.2 * math.sin(t), z + rim_z + 0.006), 0.026, mix(potion, SHINE, 0.5), False, True, 10)
                   for t in (0.3, 1.4, 2.6, 3.7, 4.9)]
    handle = (x + 0.06, y - 0.08, z + rim_z + 0.005)
    shapes.append(Line((handle, _screen(handle, 0.2, 0.36)), "#9C6B47", 2.4))
    return shapes


def _cauldron_fire(f: _Frame, now: float) -> list[Poly]:
    """The flames under a cauldron at ``now`` (outer, then their yellow middles)."""
    x, y, z = _middle(f)
    base = (x + 0.04, y + 0.04, z + 0.05)
    parts: list[Poly] = []
    for k, (du, half, height) in enumerate(CAULDRON_FLAMES):
        lick = _flicker(now, k + 2)
        tall = height * (0.8 + 0.35 * lick)
        sway = 0.025 * math.sin(2 * math.pi * now * (1.2 + 0.25 * k) + k)
        foot = _screen(base, du, 0.0)
        parts.append(Poly(_flame(foot, half, tall, sway), FIRE_ORANGE, False, True))
        parts.append(Poly(_flame(_screen(foot, 0.0, 0.004), half * 0.55, tall * 0.6, sway * 0.6), FIRE_YELLOW, False, True))
    return parts


def _cauldron_motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A working cauldron at ``now``: its flames, bubbles swelling and bursting on the potion,
    then wisps of vapour rising from it."""
    x, y, z = _middle(f)
    rim_z = CAULDRON_RIM[0]
    parts = [Motion(p.points, p.fill, 0.95, False, True) for p in _cauldron_fire(f, now)]
    froth = mix(look.main, SHINE, 0.45)
    for k, (r, t) in enumerate(((0.08, 0.5), (0.16, 2.1), (0.05, 3.6), (0.15, 4.6))[:CAULDRON_BUBBLES]):
        swell = _rising(now, k, CAULDRON_BUBBLES, BUBBLE_SECONDS)
        point = _screen((x + r * math.cos(t), y + r * math.sin(t), z + rim_z + 0.008), 0.0, 0.02 * swell)
        parts.append(_bubble(point, 0.015 + 0.04 * swell, froth, 0.95 if swell < 0.85 else 0.0))
    for k in range(VAPOUR):
        rise = _rising(now, k, VAPOUR, VAPOUR_SECONDS)
        drift = 0.06 * math.sin(2 * math.pi * (rise + k * 0.4)) + (k - 1) * 0.05 * rise
        point = _screen((x, y, z + rim_z), drift, 0.12 + 0.55 * rise)
        parts.append(_bubble(point, 0.05 + 0.07 * rise, mix(look.main, SHINE, 0.6), 0.55 * _fade(rise)))
    return parts


# ----- a giant crystal -------------------------------------------------------------------------------------


def _shard(foot: Point3, half: float, height: float, lean: float, main: str, lit: bool) -> list[Shape]:
    """One pointed crystal shard standing at ``foot``: its lit left face, its right face in shade
    and a glint down it; ``lit``: it glows (not dimmed at night)."""
    light, dark = (mix(main, SHINE, 0.45), mix(main, SHINE, 0.12)) if lit else (mix(main, SHINE, 0.28), shade(main, 0.18))
    left = [(-half, 0.0), (0.0, -half * 0.45), (lean, height), (-half + lean * 0.85, height * 0.8)]
    right = [(0.0, -half * 0.45), (half, 0.0), (half + lean * 0.85, height * 0.8), (lean, height)]
    return [_profile(foot, left, light, True, lit), _profile(foot, right, dark, True, lit),
            Line((_screen(foot, -half * 0.45, 0.06), _screen(foot, lean * 0.85 - half * 0.25, height * 0.72)), mix(main, SHINE, 0.75), 1.1)]


def _giant_crystal(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A cluster of tall crystal shards (``color``) growing from rocks (``detail``); on, they
    glow and their light tints the ground round them (the stage makes the glow pulse and sparkles
    twinkle at their tips)."""
    x, y, z = _middle(f)
    on, main = state.on, look.main
    shapes: list[Shape] = []
    if on:
        tint = mix(main, SHINE, 0.25)
        shapes += [Disc((x, y, z + 0.01 + 0.0005 * k), radius, tint, False, opacity, holds_snow=False, pool=True)
                   for k, (radius, opacity) in enumerate(((1.35, 0.24), (0.85, 0.28)))]
    rock = look.detail
    shapes.append(Blobs((f.p(0.3, 0.3, 0.1), f.p(0.62, 0.28, 0.08)), (0.16, 0.13), shade(rock, 0.1)))
    across = -1.0 if f.swap else 1.0   # the shards lean away from the middle facing either way
    for a, b, half, height, lean in sorted(SHARDS, key=lambda s: s[0] + s[1]):
        shapes += _shard(f.p(a, b, 0.12), half, height, lean * across, main, on)
    shapes.append(Blobs((f.p(0.24, 0.66, 0.08), f.p(0.5, 0.8, 0.09), f.p(0.8, 0.62, 0.08)), (0.15, 0.17, 0.13), rock))
    shapes.append(Blobs((f.p(0.46, 0.78, 0.15),), (0.06,), mix(rock, SHINE, 0.2), False))
    return shapes


def _crystal_glow(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A glowing crystal at ``now``: its light on the ground swelling, its shards brightening
    from within as it pulses (each shard's faces lit over), then sparkles twinkling at their tips
    in turn."""
    beat = 0.5 - 0.5 * math.cos(2 * math.pi * now / PULSE_SECONDS)
    x, y, z = _middle(f)
    parts = [Motion(_flat_circle((x, y, z + 0.015), 0.7 + 0.25 * beat, 28), mix(look.main, SHINE, 0.35), 0.12 + 0.16 * beat, False, True, pool=True)]
    across = -1.0 if f.swap else 1.0
    for a, b, half, height, lean in sorted(SHARDS, key=lambda s: s[0] + s[1]):
        foot, tilt = f.p(a, b, 0.12), lean * across
        low = height * 0.28   # over the rocks at its foot
        heart = [(-half * 0.55 + tilt * 0.25, low), (half * 0.55 + tilt * 0.25, low),(half * 0.4 + tilt * 0.7, height * 0.72), (tilt, height * 0.95), (-half * 0.4 + tilt * 0.6, height * 0.7)]
        parts.append(Motion(_profile(foot, heart, SHINE).points, mix(look.main, SHINE, 0.7), 0.1 + 0.4 * beat, False, True))
    for k, (a, b, half, height, lean) in enumerate(SHARDS):
        twinkle = max(0.0, math.sin(2 * math.pi * (now / (PULSE_SECONDS * 1.3) + k / len(SHARDS))))
        tip = _screen(f.p(a, b, 0.12), lean * (-1.0 if f.swap else 1.0), height)
        parts.append(Motion(_star(tip, 0.02 + 0.05 * twinkle), "#FFFFFF", twinkle, False, True))
    return parts


# ----- a throne -------------------------------------------------------------------------------------------


def _throne(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A throne on a stone step: a tall gilded back (``detail``) with a velvet panel (``color``),
    a crest with a jewel and finials, padded arms and a velvet seat (small things can sit on it)."""
    velvet, gold = look.main, look.detail
    shapes = f.box(0.04, 0.06, 0.0, 0.96, 0.98, 0.1, STONE)
    shapes += f.box(0.18, 0.18, 0.1, 0.82, 0.34, 1.98, gold)   # its back
    face = 0.341
    panel = [(0.28, face, 0.62), (0.72, face, 0.62), (0.72, face, 1.62)] + [(0.5 + 0.22 * math.cos(t), face, 1.62 + 0.2 * math.sin(t))
                                                                            for t in [math.pi * k / 10 for k in range(1, 10)]] + [(0.28, face, 1.62)]
    shapes.append(f.poly(panel, f.front(velvet)))
    shapes.append(f.poly([(0.18, face, 1.98), (0.82, face, 1.98), (0.66, face, 2.14), (0.5, face, 2.3), (0.34, face, 2.14)], f.front(gold)))
    shapes.append(_round(f.p(0.5, face + 0.002, 2.1), 0.05, GEMS[0]))
    shapes.append(_round(_screen(f.p(0.5, face + 0.003, 2.1), -0.015, 0.015), 0.014, SHINE, False))
    for a in (0.21, 0.79):   # finials on its back's corners
        shapes.append(_round(f.p(a, 0.26, 2.04), 0.055, mix(gold, SHINE, 0.15)))
    shapes += f.box(0.16, 0.34, 0.1, 0.84, 0.88, 0.5, shade(gold, 0.1))   # the seat's base
    shapes.append(_rect(f, 0.26, 0.74, 0.881, 0.18, 0.42, f.front(shade(gold, 0.25)), True))
    shapes.append(_round(f.p(0.5, 0.882, 0.3), 0.04, GEMS[1]))
    def arm(a0: float, a1: float) -> list[Shape]:   # an arm, padded on top
        return f.box(a0, 0.34, 0.5, a1, 0.88, 0.9, gold) + [f.poly([(a0 + 0.02, 0.36, 0.901), (a1 - 0.02, 0.36, 0.901), (a1 - 0.02, 0.86, 0.901),
                                                                   (a0 + 0.02, 0.86, 0.901)], velvet, False)]

    shapes += arm(0.14, 0.27)
    shapes += f.box(0.26, 0.34, 0.5, 0.74, 0.86, 0.62, velvet)   # the cushion
    shapes.append(Line((f.p(0.27, 0.86, 0.6), f.p(0.73, 0.86, 0.6)), mix(gold, SHINE, 0.2), 1.6))   # its piping
    shapes += arm(0.73, 0.86)
    for a in (0.205, 0.795):   # the arms' scrolled ends
        shapes.append(_round(f.p(a, 0.881, 0.84), 0.045, mix(gold, SHINE, 0.2)))
    return shapes


# ----- a torch sconce on a wall ---------------------------------------------------------------------------------


def _sconce_cup(f: _Frame) -> Point3:
    return f.p(f.width / 2, f.depth + 0.02 + SCONCE_CUP[0], SCONCE_CUP[1])


def _torch_sconce(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """An iron plate and bracket (``color``) on the face of the wall it hangs on holding a
    wooden torch (``detail``); lit, a flame burns on it (the stage makes it flicker and lights
    the wall) and warm light pools on the floor below (it lights who stands near)."""
    on = state.on
    cx, face = f.width / 2, f.depth + 0.02
    z0, z1 = SCONCE_PLATE
    iron = look.main
    shapes: list[Shape] = light_pool(f.p(cx, f.depth + 0.8, 0.01), 1.25) if on else []
    shapes.append(f.poly([(cx - 0.15, face, z1), (cx + 0.15, face, z1), (cx + 0.15, face, z0 + 0.16), (cx, face, z0), (cx - 0.15, face, z0 + 0.16)],
                         f.front(iron)))
    shapes += [Disc(f.p(cx + du, face + 0.002, z), 0.02, mix(iron, SHINE, 0.3), False, holds_snow=False) for du, z in ((-0.09, z1 - 0.08), (0.09, z1 - 0.08))]
    cup = _sconce_cup(f)
    grip = f.p(cx, face + SCONCE_CUP[0] * 0.45, z0 + 0.08)
    shapes.append(Line((f.p(cx, face, z0 + 0.16), grip), iron, 2.8))   # the bracket
    shapes.append(Line((f.p(cx, face, z1 - 0.1), _screen(cup, 0.0, -0.1)), iron, 2.2))
    shapes.append(_ribbon(f.p(cx, face + SCONCE_CUP[0] * 0.3, z0 + 0.02), _screen(cup, 0.0, -0.02), 0.042, look.detail))
    shapes.append(_profile(cup, [(-0.07, -0.09), (0.07, -0.09), (0.095, 0.025), (-0.095, 0.025)], iron))
    shapes.append(_profile(cup, [(-0.095, 0.0), (0.095, 0.0), (0.095, 0.032), (-0.095, 0.032)], mix(iron, SHINE, 0.2)))
    if on:
        shapes.append(_round(_screen(cup, 0.0, 0.035), 0.065, EMBER, False, True))
        if not look.moving:   # the stage makes the flame flicker while it burns
            shapes += [Poly(m.points, m.fill, m.ink, m.glow) for m in _torch_fire(f, 0.4)[1:3]]
    else:
        shapes.append(_round(_screen(cup, 0.0, 0.04), 0.065, SOOT, True, False, 12))
    return shapes


def _torch_fire(f: _Frame, now: float) -> list[Motion]:
    """A lit torch at ``now``: warm light flickering on the wall behind it, its flame (outer,
    then a yellow middle) and two sparks rising from it."""
    cup = _screen(_sconce_cup(f), 0.0, 0.025)
    cx, face = f.width / 2, f.depth + 0.021
    glow = _flicker(now, 3)
    parts = [Motion(tuple(f.p(*q) for q in _face_circle(f, cx, face, SCONCE_CUP[1] + 0.1, 0.36 + 0.04 * glow)), FIRE_LIGHT, 0.14 + 0.12 * glow, False, True,
                    pool=True)]   # faint by day like a pool of light
    lick = _flicker(now, 1)
    sway = 0.03 * math.sin(2 * math.pi * now * 1.4)
    for k, (du, half, height) in enumerate(TORCH_FLAMES):
        tall = height * (0.82 + 0.3 * lick)
        parts.append(Motion(_flame(_screen(cup, du, 0.004 * k), half, tall, sway * (1 - 0.4 * k)), (FIRE_ORANGE, FIRE_YELLOW)[k], 1.0, False, True))
    for k in range(2):
        rise = _rising(now, k, 2, 1.2)
        parts.append(_bubble(_screen(cup, 0.05 * math.sin(2 * math.pi * (rise + k * 0.5)), 0.32 + 0.4 * rise), 0.013, FIRE_YELLOW, _fade(rise)))
    return parts


# ----- a signpost, an archway, a statue ----------------------------------------------------------------------


def _signpost(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A wooden post (``detail``) with three arrow boards (``color``) pointing different ways,
    lettered and nailed on, a cap on top and stones at its foot."""
    x, y, z = _middle(f)
    am, bm = f.width / 2, f.depth / 2
    post = look.detail
    shapes: list[Shape] = [Blobs((f.p(am - 0.22, bm - 0.12, 0.04),), (0.07,), STONE), Upright(x, y, z, z + 2.12, 0.055, post)]
    shapes.append(_profile((x, y, z + 2.12), [(-0.07, -0.01), (0.07, -0.01), (0.0, 0.08)], shade(post, 0.15)))
    length, tall = 0.62, 0.17
    boards = (("+a", 1.8, look.main), ("-b", 1.54, mix(look.main, SHINE, 0.12)), ("-a", 1.28, shade(look.main, 0.08)))
    for way, z0, wood in boards:
        sign = 1.0 if way[0] == "+" else -1.0
        tail, tip = -0.09 * sign, length * sign
        outline = [(tail, z0), (tip - 0.11 * sign, z0), (tip, z0 + tall / 2), (tip - 0.11 * sign, z0 + tall), (tail, z0 + tall)]
        if way[1] == "a":
            at = lambda u, zz: (am + u, bm + 0.06, zz)   # noqa: E731
            fill = f.front(wood)
        else:
            at = lambda u, zz: (am + 0.06, bm + u, zz)   # noqa: E731
            fill = f.side(wood)
        shapes.append(f.poly([at(u, zz) for u, zz in outline], fill))
        for k, (u0, u1) in enumerate(((0.06, 0.3), (0.34, 0.44))):   # its lettering
            shapes.append(Line((f.p(*at(u0 * sign, z0 + tall * 0.5)), f.p(*at(u1 * sign, z0 + tall * 0.5))), shade(wood, 0.5), 1.4 if k == 0 else 1.0))
        shapes.append(Disc(f.p(*at(0.0, z0 + tall / 2)), 0.014, CASING, False, holds_snow=False))
    shapes.append(Blobs((f.p(am + 0.2, bm + 0.2, 0.04), f.p(am - 0.05, bm + 0.26, 0.03)), (0.07, 0.05), mix(STONE, CASING, 0.15)))
    for du in (-0.08, 0.0, 0.07):   # grass at its foot
        shapes.append(Line(((x, y + 0.08, z), _screen((x, y + 0.08, z), du, 0.12)), "#4FA34A", 1.4))
    return shapes


def _archway(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A stone archway (``color``) across its cells: two pillars with bases and a round arch of
    blocks with a keystone, ivy (``detail``) climbing it."""
    w = f.width
    stone = look.main
    p0, p1 = 0.08, 0.42   # a pillar's sides (the other mirrored)
    b0, b1 = 0.32, 0.68
    spring = 2.2   # where the arch springs from the pillars
    inner, outer = w / 2 - p1, w / 2 - p0
    steps = 14

    def arc(radius: float, b: float, start: float, end: float) -> list[tuple[float, float, float]]:
        return [(w / 2 + radius * math.cos(start + (end - start) * k / steps), b, spring + radius * math.sin(start + (end - start) * k / steps))
                for k in range(steps + 1)]

    shapes = f.box(p0 - 0.05, b0 - 0.05, 0.0, p1 + 0.05, b1 + 0.05, 0.2, shade(stone, 0.06))   # the far pillar's base
    shapes.append(f.poly([(p1, b1, 0.2), (p1, b0, 0.2), (p1, b0, spring), (p1, b1, spring)], f.side(stone)))   # its inside face, seen through
    left_under = arc(inner, b0, math.pi, math.pi / 2)
    for (a, _, zz), (a2, _, zz2) in zip(left_under, left_under[1:]):   # the arch's underside, its far half
        shapes.append(f.poly([(a, b0, zz), (a2, b0, zz2), (a2, b1, zz2), (a, b1, zz)], shade(f.side(stone), 0.1), False))
    top = arc(outer, b0, 0.0, math.pi)
    for (a, _, zz), (a2, _, zz2) in zip(top, top[1:]):   # its curved top
        lean = math.atan2(zz2 - zz, a2 - a)
        shapes.append(f.poly([(a, b0, zz), (a2, b0, zz2), (a2, b1, zz2), (a, b1, zz)], shade(stone, 0.05 if lean < 0.0 else 0.0), (False, True, False, True)))
    shapes += f.box(w - p1 - 0.05, b0 - 0.05, 0.0, w - p0 + 0.05, b1 + 0.05, 0.2, shade(stone, 0.06))   # the near pillar's base
    shapes.append(f.poly([(w - p0, b1, 0.2), (w - p0, b0, 0.2), (w - p0, b0, spring), (w - p0, b1, spring)], f.side(stone)))
    front = ([(p0, b1, 0.2), (p1, b1, 0.2), (p1, b1, spring)] + arc(inner, b1, math.pi, 0.0)
             + [(w - p1, b1, 0.2), (w - p0, b1, 0.2)] + arc(outer, b1, 0.0, math.pi))
    shapes.append(f.poly(front, f.front(stone)))
    joint = shade(f.front(stone), 0.22)
    for k in range(1, 9):   # the voussoirs' joints
        t = math.pi * k / 9
        shapes.append(Line((f.p(w / 2 + inner * math.cos(t), b1 + 0.001, spring + inner * math.sin(t)),
                            f.p(w / 2 + outer * math.cos(t), b1 + 0.001, spring + outer * math.sin(t))), joint, 0.9))
    key = [(w / 2 + r * math.cos(t), b1 + 0.002, spring + r * math.sin(t)) for r, t in ((inner - 0.02, math.pi * 0.555), (inner - 0.02, math.pi * 0.445),
                                                                                         (outer + 0.05, math.pi * 0.43), (outer + 0.05, math.pi * 0.57))]
    shapes.append(f.poly(key, mix(f.front(stone), SHINE, 0.12)))   # the keystone
    for a0, a1 in ((p0, p1), (w - p1, w - p0)):   # the pillars' courses
        for zz in (0.75, 1.3, 1.85):
            shapes.append(Line((f.p(a0, b1 + 0.001, zz), f.p(a1, b1 + 0.001, zz)), joint, 0.9))
        shapes.append(Line((f.p((a0 + a1) / 2, b1 + 0.001, 0.75), f.p((a0 + a1) / 2, b1 + 0.001, 1.3)), joint, 0.9))
    for zz in (0.75, 1.3, 1.85):
        shapes.append(Line((f.p(w - p0 + 0.001, b1, zz), f.p(w - p0 + 0.001, b0, zz)), shade(f.side(stone), 0.2), 0.9))
    ivy = look.detail
    leaves = [f.p(p0 + 0.02, b1 + 0.04, zz) for zz in (0.35, 0.7, 1.05, 1.45, 1.85)]
    leaves += [f.p(w / 2 + (outer + 0.02) * math.cos(t), b1 + 0.04, spring + (outer + 0.02) * math.sin(t)) for t in (math.pi * 0.95, math.pi * 0.82, math.pi * 0.7)]
    shapes.append(Line(tuple(leaves), shade(ivy, 0.35), 1.2))
    shapes.append(Blobs(tuple(leaves), (0.08, 0.1, 0.085, 0.1, 0.09, 0.1, 0.085, 0.07), ivy))
    shapes.append(Blobs(tuple(leaves[1::2]), (0.04,) * len(leaves[1::2]), mix(ivy, SHINE, 0.3), False))
    return shapes


def _statue(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A bronze statue (``color``) of a cloaked hero raising a sword, on a stone plinth
    (``detail``) with a plaque."""
    side = -1.0 if f.swap else 1.0
    plinth, bronze = look.detail, look.main
    shapes = f.box(0.12, 0.12, 0.0, 0.88, 0.88, 0.14, shade(plinth, 0.08))
    shapes += f.box(0.2, 0.2, 0.14, 0.8, 0.8, 0.66, plinth)
    shapes += f.box(0.15, 0.15, 0.66, 0.85, 0.85, 0.76, mix(plinth, SHINE, 0.1))
    shapes.append(_rect(f, 0.34, 0.66, 0.801, 0.28, 0.5, shade(plinth, 0.35)))
    for zz in (0.43, 0.36):   # its words
        shapes.append(Line((f.p(0.39, 0.802, zz), f.p(0.61, 0.802, zz)), mix(plinth, SHINE, 0.4), 1.0))
    base = f.p(0.5, 0.5, 0.76)
    dark, light = shade(bronze, 0.2), mix(bronze, SHINE, 0.18)
    shapes.append(_profile(base, [(-side * 0.05, 0.86), (side * 0.18, 0.84), (side * 0.24, 0.05), (-side * 0.2, 0.03)], dark))   # the cloak
    shapes.append(_profile(base, [(-0.1, 0.0), (-0.015, 0.0), (-0.03, 0.42), (-0.11, 0.42)], bronze))   # legs
    shapes.append(_profile(base, [(0.015, 0.0), (0.1, 0.0), (0.11, 0.42), (0.03, 0.42)], dark))
    shapes.append(_profile(base, [(-0.15, 0.34), (0.15, 0.34), (0.13, 0.82), (-0.13, 0.82)], bronze))   # the tunic
    shapes.append(_profile(base, [(side * 0.0, 0.36), (side * 0.15, 0.34), (side * 0.13, 0.82), (side * 0.03, 0.82)], dark, False))
    shapes.append(Line((_screen(base, -0.15, 0.5), _screen(base, 0.15, 0.5)), shade(bronze, 0.35), 1.6))   # a belt
    shoulder, hand = _screen(base, side * 0.12, 0.78), _screen(base, side * 0.24, 1.1)
    shapes.append(_ribbon(_screen(base, -side * 0.12, 0.78), _screen(base, -side * 0.19, 0.45), 0.035, bronze))   # the lowered arm
    shapes.append(_ribbon(hand, _screen(hand, side * 0.06, 0.4), 0.022, light))   # the sword's blade
    shapes.append(_ribbon(_screen(hand, -side * 0.05, 0.02), _screen(hand, side * 0.06, 0.03), 0.014, dark))   # its guard
    shapes.append(_ribbon(shoulder, hand, 0.036, bronze))   # the raised arm
    head = _screen(base, 0.0, 0.93)
    shapes.append(_round(head, 0.085, bronze))
    shapes.append(_profile(head, _arc(0.0, 0.0, 0.085, 0.085, 0.3, math.pi - 0.3, 8) + [(0.0, 0.03)], dark, False))   # hair
    shapes.append(_round(_screen(head, -side * 0.03, 0.02), 0.022, light, False))
    return shapes


#: The drawings of this module's kinds (each by its frame, look and state), and those with
#: moving parts the stage draws while they work (:func:`motion`).
DRAWINGS: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {
    "treasure_chest": _treasure_chest, "cauldron": _cauldron, "giant_crystal": _giant_crystal, "throne": _throne,
    "torch_sconce": _torch_sconce, "signpost": _signpost, "archway": _archway, "statue": _statue,
}
MOVING = frozenset({"treasure_chest", "cauldron", "giant_crystal", "torch_sconce"})


def motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """The moving parts at ``now`` of an open treasure chest (its halo and sparkles), a working
    cauldron (flames, bubbles, vapour), a glowing giant crystal (its pulse and twinkles) and a lit
    torch sconce (its flame and its light on the wall)."""
    kind = f.item.kind
    if kind == "treasure_chest":
        return _chest_sparkles(f, now)
    if kind == "cauldron":
        return _cauldron_motion(f, look, now)
    if kind == "giant_crystal":
        return _crystal_glow(f, look, now)
    if kind == "torch_sconce":
        return _torch_fire(f, now)
    return []


__all__ = ["DRAWINGS", "MOVING", "SCONCE_SPAN", "motion"]
