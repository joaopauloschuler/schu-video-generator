"""Nature iso objects (DESIGN.md §104, Phase AC Step 264): a campfire, a tent, a log, a stump, a
ring of mushrooms, a pond, a scarecrow and a beehive. No manim.

Drawn like :mod:`vidgen.cartoon.iso_objects`' objects (its frame, shading and helpers), which
looks each kind of this module up in :data:`DRAWINGS` and its moving parts in :func:`motion`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from vidgen.cartoon.iso_drawing import Blobs, Disc, Line, Poly, Shape, Upright, mix, shade
from vidgen.cartoon.iso_home import EMBER, FIRE_ORANGE, FIRE_YELLOW, SOOT, _flame, _flicker
from vidgen.cartoon.iso_objects import (
    CASING,
    SHINE,
    WOOD,
    Motion,
    ObjectLook,
    _arc,
    _bubble,
    _fade,
    _flat_circle,
    _Frame,
    _legs,
    _profile,
    _ribbon,
    _rising,
    _round,
    _screen,
    light_pool,
)
from vidgen.world.iso import ObjectState
from vidgen.world.iso_view import Point3, iso_point

#: Cut wood (a log's end, a stump's top), its rings; ash; straw; a sack's cloth; a bee's body.
CUT_WOOD = "#E9C99A"
ASH = "#5A5450"
STRAW = "#E8C35A"
SACK = "#E9D9B0"
BEE = "#FFC83D"
LEAF = "#4FA34A"
#: A campfire's flames: (across from the middle, half width and height on the picture in tile
#: widths), its sparks and how long one takes to rise and fade (seconds).
CAMP_FLAMES = ((-0.09, 0.085, 0.42), (0.0, 0.115, 0.6), (0.1, 0.08, 0.38))
SPARKS = 5
SPARK_SECONDS = 1.6
#: A mushroom ring's faint glow on the grass at night (a pool of light: strong at night only).
RING_GLOW = "#8DFFC8"
#: A pond's ripples: where they start (in its frame, shares of its width and depth) and how long
#: one takes to spread and fade (seconds).
RIPPLES = ((0.3, 0.68), (0.66, 0.36), (0.56, 0.72))
RIPPLE_SECONDS = 2.6
#: A beehive's bees and how long the quickest takes to circle it once (seconds).
BEES = 5
BEE_SECONDS = 2.4


def _hull(points: Sequence[Point3], fill: str, ink: bool = True) -> Poly:
    """The outline of ``points`` as seen (the convex hull of their pictures), as a polygon of
    those world points: a lying log's body round its two ends."""
    seen = sorted(range(len(points)), key=lambda k: iso_point(*points[k]))

    def turn(o: int, a: int, b: int) -> float:
        (ou, ov), (au, av), (bu, bv) = iso_point(*points[o]), iso_point(*points[a]), iso_point(*points[b])
        return (au - ou) * (bv - ov) - (av - ov) * (bu - ou)

    lower: list[int] = []
    upper: list[int] = []
    for k in seen:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], k) <= 0:
            lower.pop()
        lower.append(k)
    for k in reversed(seen):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], k) <= 0:
            upper.pop()
        upper.append(k)
    return Poly(tuple(points[k] for k in lower[:-1] + upper[:-1]), fill, ink)


def _middle(f: _Frame) -> Point3:
    return f.p(f.width / 2, f.depth / 2, 0.0)


# ----- a campsite: campfire, tent, log, stump --------------------------------------------------------------


def _campfire(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A ring of stones (``color``) round a bed of ash with logs (``detail``) leaning together,
    their tips charred; lit, embers glow among them, flames rise (the stage makes them flicker
    and sparks rise) and warm light pools round it (it lights who sits near)."""
    x, y, z = _middle(f)
    on = state.on
    shapes = light_pool((x, y, z + 0.01), 1.5) if on else []
    shapes.append(Disc((x, y, z + 0.012), 0.36, ASH, False, holds_snow=False))
    stones = sorted(((x + 0.42 * math.cos(t), y + 0.42 * math.sin(t), z + 0.05) for t in [2 * math.pi * k / 12 + 0.2 for k in range(12)]),
                    key=lambda p: p[0] + p[1])
    back = [p for p in stones if p[0] + p[1] < x + y]
    for k, p in enumerate(back):
        shapes.append(Blobs((p,), (0.068 + 0.012 * (k % 2),), shade(look.main, 0.05 * (k % 3))))
    if on:
        shapes += [Disc((x, y, z + 0.02), 0.22, EMBER, False, glow=True, holds_snow=False),
                   Disc((x, y, z + 0.022), 0.1, FIRE_YELLOW, False, glow=True, holds_snow=False)]
    logs = sorted((2 * math.pi * k / 4 + 0.5 for k in range(4)), key=lambda t: math.cos(t) + math.sin(t))
    for t in logs:
        foot = (x + 0.32 * math.cos(t), y + 0.32 * math.sin(t), z + 0.04)
        top = (x + 0.03 * math.cos(t), y + 0.03 * math.sin(t), z + 0.6)
        bend = (foot[0] + (top[0] - foot[0]) * 0.62, foot[1] + (top[1] - foot[1]) * 0.62, foot[2] + (top[2] - foot[2]) * 0.62)
        shapes.append(_ribbon(foot, bend, 0.04, look.detail))
        shapes.append(_ribbon(bend, top, 0.035, SOOT))
        shapes.append(_round(foot, 0.04, CUT_WOOD))
    for k, p in enumerate(stones[len(back):]):
        shapes.append(Blobs((p,), (0.072 + 0.012 * (k % 2),), shade(look.main, 0.05 * (k % 3))))
    if on and not look.moving:   # the stage draws the flames over the picture while it burns
        shapes += [Poly(m.points, m.fill, m.ink, m.glow) for m in _camp_fire(f, 0.3)[:2 * len(CAMP_FLAMES)]]
    return shapes


def _camp_fire(f: _Frame, now: float) -> list[Motion]:
    """A campfire's fire at ``now``: three flames with yellow middles, then sparks rising and
    drifting from it; the same parts at any time."""
    x, y, z = _middle(f)
    base = (x, y, z + 0.1)
    parts: list[Motion] = []
    for k, (du, half, height) in enumerate(CAMP_FLAMES):
        lick = _flicker(now, k)
        tall = height * (0.8 + 0.35 * lick)
        sway = 0.035 * math.sin(2 * math.pi * now * (1.1 + 0.2 * k) + k)
        foot = _screen(base, du, 0.0)
        parts.append(Motion(_flame(foot, half, tall, sway), FIRE_ORANGE, 0.95, False, True))
        parts.append(Motion(_flame(_screen(foot, 0.0, 0.005), half * 0.55, tall * 0.6, sway * 0.6), FIRE_YELLOW, 1.0, False, True))
    for k in range(SPARKS):
        rise = _rising(now, k, SPARKS, SPARK_SECONDS)
        drift = 0.07 * math.sin(2 * math.pi * (rise * 1.5 + k * 0.3)) + (k - 2) * 0.035 * rise
        parts.append(_bubble(_screen(base, drift, 0.3 + 0.9 * rise), 0.017, FIRE_YELLOW if k % 2 else EMBER, _fade(rise)))
    return parts


def _tent(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A ridge tent (``color``) on a ground sheet: two sloping sides, its front with the door
    open (flaps tied back, ``detail`` its trim and the bedroll inside), poles at the ridge's
    ends and guy ropes pegged at its sides."""
    w, d = f.width, f.depth
    a0, a1, b0, b1, h = 0.14, w - 0.14, 0.2, d - 0.22, 1.78
    mid = w / 2
    cloth, trim = look.main, look.detail

    def at(z: float, a: float) -> float:   # the side's ``a`` at height ``z`` (``a``: its foot)
        return a + (mid - a) * z / h

    shapes: list[Shape] = [f.poly([(a0 - 0.06, b0 - 0.04, 0.004), (a1 + 0.06, b0 - 0.04, 0.004), (a1 + 0.06, b1 + 0.14, 0.004),
                                   (a0 - 0.06, b1 + 0.14, 0.004)], shade(trim, 0.35), False)]
    shapes.append(Line((f.p(mid, b0 - 0.02, h - 0.05), f.p(mid, b0 - 0.02, h + 0.2)), WOOD, 2.2))
    for a, peg in ((a0, 0.03), (a1, w - 0.03)):   # guy ropes from each side to a peg
        shapes.append(Line((f.p(at(0.95, a), (b0 + b1) / 2, 0.95), f.p(peg, (b0 + b1) / 2, 0.0)), "#E9E2D3", 0.8))
        shapes.append(Line((f.p(peg, (b0 + b1) / 2, 0.0), f.p(peg, (b0 + b1) / 2, 0.12)), WOOD, 1.6))
    shapes.append(f.poly([(a0, b0, 0.0), (mid, b0, h), (mid, b1, h), (a0, b1, 0.0)], shade(cloth, 0.32)))
    shapes.append(f.poly([(a1, b1, 0.0), (a1, b0, 0.0), (mid, b0, h), (mid, b1, h)], f.side(cloth)))
    band = 0.2
    shapes.append(f.poly([(a1, b1, 0.0), (a1, b0, 0.0), (at(band, a1), b0, band), (at(band, a1), b1, band)], f.side(trim), (True, False, True, False)))
    shapes.append(Line((f.p(mid, b0, h), f.p(mid, b1, h)), shade(cloth, 0.4), 1.4))   # the ridge
    shapes.append(f.poly([(a0, b1, 0.0), (a1, b1, 0.0), (mid, b1, h)], f.front(cloth)))
    shapes.append(f.poly([(a0, b1 + 0.001, 0.0), (a1, b1 + 0.001, 0.0), (at(band, a1), b1 + 0.001, band), (at(band, a0), b1 + 0.001, band)],
                         f.front(trim), False))
    door, top = 0.34, 1.32
    face = b1 + 0.003
    shapes.append(f.poly([(mid - door, face, 0.0), (mid + door, face, 0.0), (mid, face, top)], "#2E2A38"))
    shapes.append(f.poly([(mid - door * 0.7, face + 0.001, 0.0), (mid + door * 0.8, face + 0.001, 0.0), (mid + door * 0.5, face + 0.001, 0.2),
                          (mid - door * 0.45, face + 0.001, 0.22)], f.front(mix(trim, "#4C8DD6", 0.5)), False))   # a bedroll inside
    flap = mix(f.front(cloth), SHINE, 0.12)
    for side in (-1, 1):   # the flaps, tied back
        shapes.append(f.poly([(mid, face + 0.002, top), (mid + side * door, face + 0.002, 0.0), (mid + side * (door + 0.16), face + 0.002, 0.0),
                              (mid + side * 0.2, face + 0.002, 0.82)], flap))
        shapes.append(Line((f.p(mid + side * (door + 0.02), face + 0.003, 0.48), f.p(mid + side * (door + 0.13), face + 0.003, 0.45)), trim, 1.6))
    return shapes + [Line((f.p(mid, b1 + 0.02, h - 0.05), f.p(mid, b1 + 0.02, h + 0.22)), WOOD, 2.2)]


def _log(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A fallen log (``color`` its bark) lying across its cells: grooved bark, its cut end with
    rings, a broken branch and moss (``detail``) on top; small things can sit on it."""
    w = f.width
    a0, a1, bc, r = 0.14, w - 0.12, f.depth / 2 + 0.04, 0.25
    bark = look.main

    def ring(a: float, radius: float, steps: int = 22) -> list[Point3]:
        return [f.p(a, bc + radius * math.cos(t), r + radius * math.sin(t)) for t in [2 * math.pi * k / steps for k in range(steps)]]

    shapes: list[Shape] = [_hull(ring(a0, r) + ring(a1, r), bark)]
    for t in (-0.5, 0.3, 1.0, 1.75, 2.4):   # grooves along the bark, on the side seen
        lo, hi = (a0 + 0.1, a1 - 0.08) if t != 1.0 else (a0 + 0.3, a1 - 0.35)
        shapes.append(Line((f.p(lo, bc + r * math.cos(t), r + r * math.sin(t)), f.p(hi, bc + r * math.cos(t), r + r * math.sin(t))), shade(bark, 0.3), 0.8))
    shapes.append(Poly(tuple(ring(a1, r)), CUT_WOOD))
    for share in (0.68, 0.36):
        shapes.append(Line(tuple(ring(a1 + 0.001, r * share, 18) + ring(a1 + 0.001, r * share, 18)[:1]), shade(CUT_WOOD, 0.25), 0.7))
    shapes.append(Line((f.p(a1 + 0.002, bc, r), f.p(a1 + 0.002, bc + r * 0.6, r + r * 0.55)), shade(CUT_WOOD, 0.35), 0.7))   # a crack
    stub, tip = f.p(a0 + 0.55, bc - 0.05, 2 * r - 0.02), f.p(a0 + 0.7, bc - 0.12, 2 * r + 0.3)
    shapes += [_ribbon(stub, tip, 0.035, shade(bark, 0.08)), _round(tip, 0.035, CUT_WOOD)]
    moss = [f.p(a, bc + 0.02, 2 * r + 0.01) for a in (a0 + 0.95, a0 + 1.12, a0 + 1.3)]
    shapes.append(Blobs(tuple(moss), (0.07, 0.085, 0.06), look.detail))
    shapes.append(Blobs((moss[1],), (0.03,), mix(look.detail, SHINE, 0.35), False))
    return shapes


def _stump(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A tree stump (``color`` its bark) on spreading roots: a cut top (``detail``) with rings
    and a crack, grooved bark and a green sprout; small things can sit on it."""
    x, y, z = _middle(f)
    r, h = 0.3, 0.56
    bark = look.main

    def root(t: float) -> Poly:
        return Poly(((x + r * math.cos(t - 0.42), y + r * math.sin(t - 0.42), z), (x + (r + 0.1) * math.cos(t - 0.12), y + (r + 0.1) * math.sin(t - 0.12), z),
                     (x + (r + 0.14) * math.cos(t), y + (r + 0.14) * math.sin(t), z + 0.03),
                     (x + (r + 0.1) * math.cos(t + 0.12), y + (r + 0.1) * math.sin(t + 0.12), z),
                     (x + r * math.cos(t + 0.42), y + r * math.sin(t + 0.42), z), (x + (r - 0.01) * math.cos(t), y + (r - 0.01) * math.sin(t), z + 0.17)),
                    shade(bark, 0.08))

    roots = sorted((0.3, 1.5, 2.8, 4.0, 5.2), key=lambda t: math.cos(t) + math.sin(t))
    shapes: list[Shape] = [root(t) for t in roots if math.cos(t) + math.sin(t) < 0]
    shapes.append(Upright(x, y, z, z + h, r, bark))
    for t in (math.pi / 4 - 0.9, math.pi / 4 - 0.35, math.pi / 4 + 0.25, math.pi / 4 + 0.8):   # grooves on the side seen
        shapes.append(Line(((x + r * math.cos(t), y + r * math.sin(t), z + 0.06), (x + r * math.cos(t), y + r * math.sin(t), z + h - 0.06)),
                           shade(bark, 0.3), 0.8))
    shapes += [root(t) for t in roots if math.cos(t) + math.sin(t) >= 0]
    top = (x, y, z + h + 0.001)
    shapes.append(Disc(top, r * 0.86, look.detail, False))
    for share in (0.6, 0.32):
        circle = _flat_circle((x, y, z + h + 0.002), r * share, 20)
        shapes.append(Line((*circle, circle[0]), shade(look.detail, 0.25), 0.7))
    shapes.append(Line(((x, y, z + h + 0.003), (x + r * 0.75, y - r * 0.2, z + h + 0.003)), shade(look.detail, 0.35), 0.7))   # a crack
    sprout = (x + r * math.cos(-0.2), y + r * math.sin(-0.2), z + 0.12)
    shapes.append(Line((sprout, _screen(sprout, 0.04, 0.16)), "#3E8E3E", 1.2))
    return shapes + [_round(_screen(sprout, 0.0, 0.14), 0.04, LEAF), _round(_screen(sprout, 0.08, 0.17), 0.035, LEAF)]


# ----- a meadow: mushroom ring, pond, scarecrow, beehive -----------------------------------------------------


def _mushroom_ring(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A fairy ring of mushrooms (caps in ``color`` and a warmer shade, ``detail`` spots) on the
    grass; their spots and a soft green glow on the grass show at night."""
    x, y, z = _middle(f)
    shapes: list[Shape] = [Disc((x, y, z + 0.01), 0.98, RING_GLOW, False, 0.22, holds_snow=False, pool=True)]
    radius = min(f.width, f.depth) / 2 - 0.3
    spots = sorted(((x + radius * math.cos(t), y + radius * math.sin(t), z, k) for k, t in enumerate(2 * math.pi * k / 11 + 0.15 for k in range(11))),
                   key=lambda p: p[0] + p[1])
    for px, py, pz, k in spots:
        size = 0.75 + 0.4 * ((k * 0.37) % 1.0)
        stem = 0.14 * size
        shapes.append(Upright(px, py, pz, pz + stem, 0.035 * size, "#F4EBDD"))
        cap = (px, py, pz + stem)
        rx, ry = 0.1 * size, 0.08 * size
        fill = look.main if k % 3 else mix(look.main, "#F2A33A", 0.45)
        shapes.append(_profile(cap, [*_arc(0.0, 0.0, rx, ry, 0.0, math.pi, 10), *_arc(0.0, 0.0, rx, ry * 0.3, math.pi, 2 * math.pi, 6)[1:-1]], fill))
        for du, dv, s in ((-0.04, 0.035, 0.018), (0.035, 0.05, 0.015), (0.01, 0.015, 0.012)):
            shapes.append(_round(_screen(cap, du * size, dv * size), s * size, look.detail, False, True))
    return shapes


def _pond_edge(f: _Frame, grow: float, z: float) -> list[Point3]:
    """A pond's rounded, uneven edge in its frame, ``grow`` (tile units) out from its water's."""
    w, d = f.width, f.depth
    rx, ry = w / 2 - 0.2 + grow, d / 2 - 0.2 + grow
    points = []
    for k in range(32):
        t = 2 * math.pi * k / 32
        wobble = 1.0 + 0.07 * math.sin(3 * t + 0.5) + 0.04 * math.sin(5 * t + 1.3)
        points.append(f.p(w / 2 + rx * wobble * math.cos(t), d / 2 + ry * wobble * math.sin(t), z))
    return points


def _pond(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A small pond: water (``detail``) in an edge of pebbles and sand (``color``), deeper in the
    middle, lily pads with a pink flower, reeds and cattails at the back and stones at the front;
    on, ripples spread on it (the stage moves them; still, two faint rings lie on it)."""
    w, d = f.width, f.depth
    water = look.detail
    shapes: list[Shape] = [Poly(tuple(_pond_edge(f, 0.14, 0.02)), look.main, True, holds_snow=False),
                           Poly(tuple(_pond_edge(f, 0.0, 0.03)), water, False, holds_snow=False),
                           Poly(tuple(_pond_edge(f, -0.32, 0.031)), shade(water, 0.14), False, holds_snow=False)]
    pale = mix(water, SHINE, 0.55)
    if not (state.on and look.moving):   # the stage spreads the ripples while it is on
        for (sa, sb), share in zip(RIPPLES, (0.45, 0.7)):
            circle = _flat_circle(f.p(sa * w, sb * d, 0.032), 0.12 + 0.12 * share, 20)
            shapes.append(Line((*circle, circle[0]), pale, 0.8))
    shapes.append(Line((f.p(0.62 * w, 0.22 * d, 0.033), f.p(0.8 * w, 0.3 * d, 0.033)), pale, 1.4))   # a glint
    for k, (sa, sb, r, notch) in enumerate(((0.36, 0.42, 0.17, 0.6), (0.7, 0.6, 0.13, 2.4), (0.44, 0.78, 0.15, 4.2))):
        centre = f.p(sa * w, sb * d, 0.034)
        rim = [(centre[0] + r * math.cos(t), centre[1] + r * math.sin(t), centre[2]) for t in [notch + 0.4 + (2 * math.pi - 0.8) * j / 16 for j in range(17)]]
        shapes.append(Poly((centre, *rim), LEAF if k != 1 else mix(LEAF, "#C8D86A", 0.3)))
        shapes.append(Line((centre, (centre[0] + r * 0.8 * math.cos(notch + math.pi), centre[1] + r * 0.8 * math.sin(notch + math.pi), centre[2])),
                           shade(LEAF, 0.25), 0.6))
        if k == 0:   # a water lily on it
            bloom = (centre[0] - 0.03, centre[1] + 0.03, centre[2] + 0.04)
            shapes.append(Blobs(tuple(_screen(bloom, 0.045 * math.cos(t), 0.03 * math.sin(t)) for t in [2 * math.pi * j / 5 + 0.3 for j in range(5)]),
                                (0.04,) * 5, "#F7A8C8"))
            shapes.append(_round(bloom, 0.025, "#FFD75E", False))
    for k, (sa, sb) in enumerate(((0.78, 0.12), (0.86, 0.2), (0.7, 0.08), (0.92, 0.3), (0.82, 0.26))):   # reeds at the back
        foot = f.p(sa * w, sb * d, 0.0)
        tall = 0.55 + 0.12 * (k % 3)
        tip = _screen(foot, 0.04 * (k % 2 * 2 - 1), tall * 0.62)
        shapes.append(Line((foot, tip), "#3E8E3E" if k % 2 else "#5BA35B", 1.6))
        if k < 2:   # a cattail
            head = _screen(foot, 0.04 * (k % 2 * 2 - 1) * 0.8, tall * 0.5)
            shapes.append(_profile(head, [(-0.022, -0.06), (0.022, -0.06), (0.022, 0.06), (-0.022, 0.06)], "#7A5236"))
    for sa, sb, r in ((0.22, 0.9, 0.08), (0.34, 0.95, 0.06), (0.9, 0.78, 0.07)):   # stones at the front
        shapes.append(Blobs((f.p(sa * w, sb * d, 0.07),), (r,), mix(look.main, "#8E8A84", 0.5)))
    return shapes


def _ripples(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A pond's ripples at ``now``: each a ring spreading from its spot and fading."""
    pale = mix(look.detail, SHINE, 0.6)
    parts: list[Motion] = []
    for k, (sa, sb) in enumerate(RIPPLES):
        spread = (now / RIPPLE_SECONDS + k / len(RIPPLES)) % 1.0
        centre = f.p(sa * f.width, sb * f.depth, 0.032)
        outer = 0.04 + 0.3 * spread
        ring = list(_flat_circle(centre, outer, 24)) + list(reversed(_flat_circle(centre, outer * 0.86, 24)))
        parts.append(Motion(tuple(ring), pale, 0.85 * (1.0 - spread) * min(1.0, spread * 8.0), False))
    return parts


def _scarecrow(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A scarecrow on a post: a patched shirt (``color``) with straw at the cuffs and hem, a sack
    head with a stitched smile under a straw hat (``detail``), and a crow on one arm."""
    x, y, z = _middle(f)
    side = -1.0 if f.swap else 1.0
    shirt = look.main
    shoulders = (x, y, z + 1.5)
    shapes: list[Shape] = [Upright(x, y, z, z + 1.95, 0.045, WOOD)]
    shapes.append(_profile(shoulders, [(-0.46, -0.02), (0.46, -0.02), (0.46, 0.03), (-0.46, 0.03)], WOOD))
    for s in (-1.0, 1.0):   # straw from the cuffs, the sleeves over it
        cuff = _screen(shoulders, s * 0.38, 0.0)
        for dv in (-0.06, 0.0, 0.05):
            shapes.append(Line((cuff, _screen(cuff, s * 0.1, dv * 1.4)), STRAW, 1.4))
        shapes.append(_profile(shoulders, [(s * 0.14, 0.08), (s * 0.4, 0.06), (s * 0.4, -0.08), (s * 0.14, -0.13)], shade(shirt, 0.1)))
    for du in (-0.12, -0.05, 0.03, 0.1):   # straw from the hem
        shapes.append(Line((_screen(shoulders, du, -0.46), _screen(shoulders, du * 1.35, -0.6)), STRAW, 1.4))
    shapes.append(_profile(shoulders, [(-0.17, 0.08), (0.17, 0.08), (0.2, -0.48), (-0.2, -0.48)], shirt))
    for du in (-0.07, 0.07):   # its checks
        shapes.append(Line((_screen(shoulders, du, 0.06), _screen(shoulders, du * 1.15, -0.46)), shade(shirt, 0.25), 0.8))
    for dv in (-0.14, -0.32):
        shapes.append(Line((_screen(shoulders, -0.18, dv), _screen(shoulders, 0.18, dv)), shade(shirt, 0.25), 0.8))
    shapes.append(Line((_screen(shoulders, -0.2, -0.4), _screen(shoulders, 0.2, -0.4)), "#B98A4E", 1.8))   # a rope belt
    shapes.append(_profile(_screen(shoulders, side * 0.08, -0.26), [(-0.045, -0.04), (0.045, -0.04), (0.045, 0.04), (-0.045, 0.04)],
                           mix(look.detail, "#E2574C", 0.5)))   # a patch
    head = _screen(shoulders, 0.0, 0.25)
    shapes.append(_round(head, 0.155, SACK))
    shapes += [_round(_screen(head, du, 0.03), 0.022, CASING, False) for du in (-0.055, 0.055)]
    shapes.append(Poly(tuple(_screen(head, du, dv) for du, dv in ((-0.012, -0.005), (0.012, -0.005), (0.0, -0.035))), "#F2A33A", False))
    smile = [_screen(head, 0.07 * math.cos(t), -0.05 + 0.035 * math.sin(t)) for t in [math.pi * (1.15 + 0.7 * k / 6) for k in range(7)]]
    shapes.append(Line(tuple(smile), CASING, 0.9))
    shapes += [Line((_screen(p, 0.0, -0.012), _screen(p, 0.0, 0.012)), CASING, 0.7) for p in smile[1:-1:2]]   # its stitches
    hat = look.detail
    shapes.append(_profile(head, [*_arc(0.0, 0.1, 0.27, 0.06, 0.0, 2 * math.pi, 20)], hat))   # the brim
    shapes.append(_profile(head, [(-0.12, 0.1), (0.12, 0.1), (0.09, 0.3), (-0.09, 0.3)], shade(hat, 0.06)))
    shapes.append(_profile(head, [(-0.115, 0.12), (0.115, 0.12), (0.11, 0.16), (-0.11, 0.16)], mix(hat, "#E2574C", 0.55), False))
    crow = _screen(shoulders, side * 0.32, 0.1)
    return shapes + [_round(crow, 0.065, CASING), _round(_screen(crow, side * 0.06, 0.06), 0.04, CASING),
                     Poly(tuple(_screen(crow, side * du, dv) for du, dv in ((0.09, 0.07), (0.14, 0.055), (0.09, 0.045))), "#F2A33A", False),
                     _round(_screen(crow, side * 0.075, 0.07), 0.01, SHINE, False)]


def _beehive(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A straw skep (``color``) of stacked coils on a wooden stand (``detail``), a dark entrance
    with honey at its sill; on, bees circle it (the stage flies them)."""
    x, y, z = _middle(f)
    back, front = _legs(f, 0.2, 0.2, 0.8, 0.8, 0.36, shade(look.detail, 0.15))
    shapes: list[Shape] = back + front + f.box(0.14, 0.14, 0.36, 0.86, 0.86, 0.44, look.detail)
    base = (x, y, z + 0.44)
    straw = look.main
    for k, half in enumerate((0.32, 0.315, 0.295, 0.26, 0.205, 0.13)):
        dv = 0.07 + 0.115 * k
        shapes.append(_profile(base, [*_arc(half - 0.06, dv, 0.06, 0.07, -math.pi / 2, math.pi / 2, 5),
                                      *_arc(-half + 0.06, dv, 0.06, 0.07, math.pi / 2, 3 * math.pi / 2, 5)],
                               straw if k % 2 == 0 else shade(straw, 0.08)))
    shapes.append(_round(_screen(base, 0.0, 0.73), 0.05, shade(straw, 0.1)))
    shapes.append(_profile(base, _arc(0.0, 0.01, 0.075, 0.08, 0.0, math.pi, 8), "#3A2A1A"))   # the entrance
    shapes.append(_profile(base, [(-0.09, 0.0), (0.09, 0.0), (0.06, -0.025), (0.0, -0.06), (-0.04, -0.025)], "#F2A33A", False))   # honey
    if state.on and not look.moving:   # the stage flies the bees while it is on
        shapes += [Poly(m.points, m.fill, m.ink, m.glow) for m in _bees(f, 0.6) if m.opacity > 0.5]
    return shapes


def _bees(f: _Frame, now: float) -> list[Motion]:
    """A hive's bees at ``now``: each circling it at its own height and pace (a body with a
    stripe and a wing), hidden while behind the skep."""
    x, y, z = _middle(f)
    parts: list[Motion] = []
    for k in range(BEES):
        turn = 2 * math.pi * ((now / (BEE_SECONDS + 0.5 * k) + k / BEES) * (1 if k % 2 else -1))
        reach = 0.46 + 0.08 * (k % 3)
        point = (x + reach * math.cos(turn), y + reach * math.sin(turn),
                 z + 0.7 + 0.32 * ((k * 0.41) % 1.0) + 0.05 * math.sin(2 * math.pi * now * 1.7 + k))
        behind = math.cos(turn) + math.sin(turn) < 0 and abs(math.cos(turn) - math.sin(turn)) * reach / 2 < 0.3
        seen = 0.0 if behind else 1.0
        parts += [Motion(_round(_screen(point, -0.012, 0.04), 0.026, SHINE).points, SHINE, 0.85 * seen, False),
                  Motion(_round(point, 0.036, BEE).points, BEE, seen, True),
                  Motion(_round(_screen(point, 0.01, 0.0), 0.014, CASING).points, CASING, seen, False)]
    return parts


#: The drawings of this module's kinds (each by its frame, look and state), and those with
#: moving parts the stage draws while they work (:func:`motion`).
DRAWINGS: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {
    "campfire": _campfire, "tent": _tent, "log": _log, "stump": _stump, "mushroom_ring": _mushroom_ring, "pond": _pond,
    "scarecrow": _scarecrow, "beehive": _beehive,
}
MOVING = frozenset({"campfire", "pond", "beehive"})


def motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """The moving parts of a lit campfire (flames and rising sparks), a pond with ripples on
    (spreading rings) or a hive with bees out (circling it) at ``now``."""
    kind = f.item.kind
    if kind == "campfire":
        return _camp_fire(f, now)
    if kind == "pond":
        return _ripples(f, look, now)
    if kind == "beehive":
        return _bees(f, now)
    return []


__all__ = ["DRAWINGS", "MOVING", "motion"]
