"""Town iso objects (DESIGN.md §104, Phase AC Step 263): a street lamp, a traffic light, a bus
stop, a mailbox, a fountain, a phone booth, a parked car, a bicycle and a newsstand. No manim.

Drawn like :mod:`vidgen.cartoon.iso_objects`' objects (its frame, shading and helpers), which
looks each kind of this module up in :data:`DRAWINGS` and its moving parts in :func:`motion`.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from vidgen.cartoon.iso_drawing import Disc, Line, Poly, Shape, Upright, box_shapes, mix, shade
from vidgen.cartoon.iso_objects import (
    BOOK_COLORS,
    CASING,
    GLASS,
    LIT_CORE,
    LIT_GLASS,
    SHINE,
    WOOD,
    Motion,
    ObjectLook,
    _face_circle,
    _Frame,
    _profile,
    _round,
    _screen,
    light_pool,
)
from vidgen.cartoon.iso_shop import CHROME, _rect
from vidgen.world.iso import ObjectState
from vidgen.world.iso_view import Point3

#: A traffic light's lamps when lit (red, amber, green) and how long each shows in its cycle, in
#: the order they come: red, green, amber (seconds).
SIGNAL_COLORS = ("#FF4A3D", "#FFB020", "#3DDC6B")
SIGNAL_CYCLE = ((0, 3.6), (2, 3.6), (1, 1.2))
#: The heights of its three lamps' middles (red at the top) and their radius.
SIGNAL_LAMPS = (2.84, 2.55, 2.26)
SIGNAL_RADIUS = 0.115
#: Seconds of a drop's fall from a fountain's bowl and of a ripple spreading.
FALL_SECONDS = 0.9
RIPPLE_SECONDS = 1.4
#: Where a fountain's falls leave its upper bowl: angles round it (radians, all on its side to
#: the viewer, so no fall shows over the column behind it).
FALL_ANGLES = (-0.35, 0.45, 1.15, 1.95)
#: A car's tyres, its bumpers and trims, its tail lights; a booth's sign; magazines' paper.
TYRE = "#2B2F3A"
TRIM = "#5A6070"
TAIL = "#E2574C"
PAPER = "#F4F1EA"
#: Dark seen through an opening.
INSIDE = "#2E2A38"


def _side_rect(f: _Frame, a: float, b0: float, b1: float, z0: float, z1: float, fill: str, ink: bool = True, glow: bool = False) -> Poly:
    """A rectangle on the right side face at ``a`` (``b0`` .. ``b1`` along it, ``z0`` .. ``z1`` up)."""
    return f.poly([(a, b1, z0), (a, b0, z0), (a, b0, z1), (a, b1, z1)], fill, ink, glow)


# ----- the street: lamp, traffic light, bus stop, mailbox ----------------------------------------------------


def _street_lamp(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A tall cast-iron street lamp (``color``): a fluted foot, a slim post with collars, a crook
    curling over towards the front and a lantern hanging from it (``detail`` its glass when off);
    on, the lantern glows and warm light pools on the ground under it (it lights who stands near)."""
    x, y = f.p(0.5, 0.34, 0.0)[:2]
    hx, hy = f.p(0.5, 0.72, 0.0)[:2]   # under the lantern
    z = f.base
    iron = look.main
    on = state.on
    shapes = light_pool((hx, hy, z + 0.01), 1.3) if on else []
    shapes += [Upright(x, y, z, z + 0.12, 0.2, shade(iron, 0.12)), Upright(x, y, z + 0.12, z + 0.6, 0.12, iron),
               Upright(x, y, z + 0.6, z + 0.68, 0.15, mix(iron, SHINE, 0.12)), Upright(x, y, z + 0.68, z + 3.72, 0.055, iron),
               Upright(x, y, z + 2.3, z + 2.36, 0.085, mix(iron, SHINE, 0.12))]
    crook = [f.p(0.5, 0.53 - 0.19 * math.cos(t), 3.7 + 0.2 * math.sin(t)) for t in [math.pi * k / 12 for k in range(13)]]
    shapes.append(Line((f.p(0.5, 0.34, 3.6), *crook, f.p(0.5, 0.72, 3.62)), iron, 3.4))
    curl = [f.p(0.5, 0.45 + 0.07 * math.cos(t), 3.62 + 0.07 * math.sin(t)) for t in [math.pi * (0.2 + 1.6 * k / 10) for k in range(11)]]
    shapes.append(Line(tuple(curl), iron, 2.0))
    top, z0, z1, half = z + 3.58, z + 3.08, z + 3.46, 0.13
    glass = (LIT_CORE, LIT_GLASS, shade(LIT_GLASS, 0.08)) if on else (mix(look.detail, SHINE, 0.3), look.detail, shade(look.detail, 0.15))
    shapes += box_shapes(hx - 0.07, hy - 0.07, z0 - 0.08, hx + 0.07, hy + 0.07, z0, shade(iron, 0.1))
    shapes += box_shapes(hx - half, hy - half, z0, hx + half, hy + half, z1, glass[0], left=glass[1], right=glass[2], glow=on)
    for px, py in ((hx - half, hy + half), (hx + half, hy + half), (hx + half, hy - half)):   # the lantern's frame
        shapes.append(Line(((px, py, z0), (px, py, z1)), iron, 1.4))
    rim = 0.18
    shapes.append(Poly(((hx - rim, hy - rim, z1), (hx + rim, hy - rim, z1), (hx + rim, hy + rim, z1), (hx - rim, hy + rim, z1)), iron))
    shapes.append(Poly(((hx - rim, hy + rim, z1), (hx + rim, hy + rim, z1), (hx, hy, top)), shade(iron, 0.05)))
    shapes.append(Poly(((hx + rim, hy + rim, z1), (hx + rim, hy - rim, z1), (hx, hy, top)), shade(iron, 0.22)))
    return shapes + [Upright(hx, hy, top - 0.02, top + 0.04, 0.03, iron)]


def _signal_lamps(f: _Frame, lit: int | None) -> list[Shape]:
    """A traffic light's three lamps on its head's front: the ``lit`` one (0 red, 1 amber, 2
    green) a light, the others dark glass."""
    b = 0.6
    shapes: list[Shape] = []
    for k, (zc, color) in enumerate(zip(SIGNAL_LAMPS, SIGNAL_COLORS)):
        if k == lit:
            shapes.append(f.poly(_face_circle(f, 0.5, b, zc, SIGNAL_RADIUS, 18), color, True, True))
            shapes.append(f.poly(_face_circle(f, 0.48, b + 0.001, zc + 0.02, SIGNAL_RADIUS * 0.45, 12), mix(color, SHINE, 0.6), False, True))
        else:
            shapes.append(f.poly(_face_circle(f, 0.5, b, zc, SIGNAL_RADIUS, 18), mix(shade(color, 0.62), CASING, 0.3)))
    return shapes


def _traffic_light(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A traffic light: a post (``color``) with a push-button box, a signal head with a backing
    board (``detail``) and three lamps under hoods; on, it shows red (the stage cycles red, green,
    amber); off, all three are dark."""
    x, y = f.p(0.5, 0.46, 0.0)[:2]
    z = f.base
    pole = look.main
    shapes: list[Shape] = [Upright(x, y, z, z + 0.14, 0.15, shade(pole, 0.15)), Upright(x, y, z + 0.14, z + 2.05, 0.055, pole)]
    shapes += f.box(0.42, 0.52, 0.95, 0.58, 0.58, 1.22, look.detail)   # the walk button
    shapes.append(f.poly(_face_circle(f, 0.5, 0.581, 1.05, 0.035, 10), CASING, False))
    shapes.append(_rect(f, 0.27, 0.73, 0.37, 2.02, 3.1, look.detail))   # the backing board
    shapes.append(Line((f.p(0.29, 0.371, 2.04), f.p(0.71, 0.371, 2.04), f.p(0.71, 0.371, 3.08), f.p(0.29, 0.371, 3.08), f.p(0.29, 0.371, 2.04)),
                       CASING, 1.4))
    shapes += f.box(0.33, 0.38, 2.06, 0.67, 0.6, 3.06, CASING)
    for zc in SIGNAL_LAMPS:   # a hood over each lamp (the lamp drawn over its shadow on the picture)
        shapes.append(f.poly([(0.37, 0.6, zc + 0.135), (0.63, 0.6, zc + 0.135), (0.63, 0.66, zc + 0.12), (0.37, 0.66, zc + 0.12)], shade(CASING, 0.1)))
    shapes += _signal_lamps(f, 0 if state.on and not look.moving else None)
    return shapes + [Upright(x, y, z + 3.06, z + 3.12, 0.04, pole)]


def _signal_motion(f: _Frame, now: float) -> list[Motion]:
    """A working traffic light at ``now``: its lit lamp (red, green, amber in turn), the lamp's
    shine and a soft halo round it."""
    share = now % sum(seconds for _, seconds in SIGNAL_CYCLE)
    lit = SIGNAL_CYCLE[-1][0]
    for k, seconds in SIGNAL_CYCLE:
        if share < seconds:
            lit = k
            break
        share -= seconds
    zc, color = SIGNAL_LAMPS[lit], SIGNAL_COLORS[lit]
    b = 0.6
    return [Motion(tuple(f.p(*q) for q in _face_circle(f, 0.5, b + 0.002, zc, SIGNAL_RADIUS * 1.9, 20)), color, 0.3, False, True),
            Motion(tuple(f.p(*q) for q in _face_circle(f, 0.5, b + 0.003, zc, SIGNAL_RADIUS, 18)), color, 1.0, True, True),
            Motion(tuple(f.p(*q) for q in _face_circle(f, 0.48, b + 0.004, zc + 0.02, SIGNAL_RADIUS * 0.45, 12)), mix(color, SHINE, 0.6), 1.0, False, True)]


def _bus_stop(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A bus shelter (``color`` its frame): a glass back and ends on posts, a bench inside, an
    advert (``detail``) on its end, a flat roof and a round bus sign on a post with a timetable."""
    w = f.width
    frame = look.main
    a0, a1, b0, b1, h = 0.12, w - 0.12, 0.2, 0.74, 2.2
    pane = mix(GLASS, SHINE, 0.25)
    shapes: list[Shape] = [_side_rect(f, a0 + 0.04, b0, b1, 0.18, h - 0.06, pane)]   # the far end (seen through the shelter)
    for a in (a0, a1 - 0.08):
        shapes += f.box(a, b0 - 0.06, 0.0, a + 0.08, b0 + 0.02, h, frame)
    shapes.append(_rect(f, a0 + 0.08, a1 - 0.08, b0, 0.18, h - 0.06, pane))
    shapes.append(Line((f.p(a0 + 0.08, b0 + 0.001, 1.15), f.p(a1 - 0.08, b0 + 0.001, 1.15)), frame, 2.0))
    for a in (a0 + 0.35, a0 + 1.0):
        shapes.append(Line((f.p(a, b0 + 0.002, 1.35), f.p(a + 0.3, b0 + 0.002, 1.95)), SHINE, 1.2))
    seat = mix(WOOD, SHINE, 0.1)   # the bench along the back
    for a in (a0 + 0.3, a1 - 0.36):
        shapes += f.box(a, b0 + 0.06, 0.0, a + 0.06, b0 + 0.4, 0.48, shade(frame, 0.1))
    shapes += f.box(a0 + 0.2, b0 + 0.04, 0.48, a1 - 0.2, b0 + 0.42, 0.55, seat)
    shapes.append(Line((f.p(a0 + 0.22, b0 + 0.23, 0.551), f.p(a1 - 0.22, b0 + 0.23, 0.551)), shade(seat, 0.3), 0.8))
    end = a1 - 0.04   # the near end: glass with an advert
    shapes.append(_side_rect(f, end, b0, b1, 0.18, h - 0.06, pane))
    shapes.append(_side_rect(f, end + 0.002, b0 + 0.08, b1 - 0.08, 0.45, 1.75, look.detail))
    shapes.append(_side_rect(f, end + 0.003, b0 + 0.14, b1 - 0.14, 1.32, 1.62, mix(look.detail, SHINE, 0.6), False))
    for z in (0.62, 0.74):
        shapes.append(Line((f.p(end + 0.004, b1 - 0.14, z), f.p(end + 0.004, b0 + 0.2, z)), SHINE, 1.2))
    for a in (a0, a1 - 0.08):
        shapes += f.box(a, b1 - 0.02, 0.0, a + 0.08, b1 + 0.06, h, frame)
    shapes += f.box(0.04, 0.06, h, w - 0.04, 0.9, h + 0.1, mix(frame, SHINE, 0.12))
    shapes.append(_rect(f, 0.04, w - 0.04, 0.901, h, h + 0.1, look.detail, False))
    px, py = f.p(0.1, 0.96, 0.0)[:2]   # the sign's post, before the roof's front
    z = f.base
    shapes += [Upright(px, py, z, z + 2.62, 0.04, shade(frame, 0.2))]
    board = f.p(0.1, 0.96, 0.0)
    shapes.append(_profile((board[0], board[1], z + 1.25), [(-0.1, 0.0), (0.1, 0.0), (0.1, 0.3), (-0.1, 0.3)], PAPER))
    for k in range(4):
        shapes.append(Line((_screen((board[0], board[1], z + 1.25), -0.07, 0.24 - 0.055 * k), _screen((board[0], board[1], z + 1.25), 0.05 - 0.02 * (k % 2), 0.24 - 0.055 * k)),
                           TRIM, 0.7))
    sign = (board[0], board[1], z + 2.6)
    shapes.append(_round(sign, 0.17, look.detail))
    shapes.append(_round(sign, 0.12, PAPER, False))
    shapes.append(_profile(sign, [(-0.075, -0.035), (0.075, -0.035), (0.075, 0.05), (-0.075, 0.05)], frame, False))   # a little bus
    shapes.append(_profile(sign, [(-0.06, 0.012), (0.06, 0.012), (0.06, 0.038), (-0.06, 0.038)], GLASS, False))
    return shapes + [_round(_screen(sign, du, -0.04), 0.018, CASING, False) for du in (-0.045, 0.045)]


def _mailbox(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A round pillar mailbox (``color``): a dark foot, a body with a letter slot under a lip, a
    plaque (``detail``) and a white collection plate, a domed cap with a knob."""
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    z = f.base
    body = look.main
    shapes: list[Shape] = [Upright(x, y, z, z + 0.1, 0.26, shade(body, 0.4)), Upright(x, y, z + 0.1, z + 1.12, 0.22, body),
                           Upright(x, y, z + 1.12, z + 1.2, 0.26, mix(body, SHINE, 0.1))]
    cap = (x, y, z + 1.2)
    shapes.append(_profile(cap, [(0.184 * math.cos(t), 0.13 * math.sin(t)) for t in [math.pi * k / 14 for k in range(15)]], mix(body, SHINE, 0.06)))
    shapes.append(_round(_screen(cap, 0.0, 0.15), 0.03, mix(body, SHINE, 0.06)))
    face = (x, y, z + 0.1)
    shapes.append(_profile(face, [(-0.1, 0.62), (0.1, 0.62), (0.11, 0.66), (-0.11, 0.66)], shade(body, 0.2)))   # the lip over the slot
    shapes.append(_profile(face, [(-0.09, 0.57), (0.09, 0.57), (0.09, 0.61), (-0.09, 0.61)], "#1E1E26", False))
    shapes.append(_profile(face, [(-0.06, 0.42), (0.06, 0.42), (0.06, 0.5), (-0.06, 0.5)], look.detail))
    shapes.append(_profile(face, [(-0.07, 0.22), (0.07, 0.22), (0.07, 0.36), (-0.07, 0.36)], PAPER))
    return shapes + [Line((_screen(face, -0.045, dv), _screen(face, 0.045, dv)), TRIM, 0.7) for dv in (0.26, 0.29, 0.32)]


# ----- a square: fountain, phone booth, newsstand ------------------------------------------------------------

#: A fountain's parts (tile units over its base): its basin's radius, wall height and water's
#: radius; its upper bowl's height and radius; the height its jet leaves the top at.
BASIN = (0.95, 0.42, 0.8)
BOWL = (1.3, 0.42)
SPOUT = 1.98


def _fountain_middle(f: _Frame) -> Point3:
    return f.p(f.width / 2, f.depth / 2, 0.0)


def _fountain(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A round stone fountain (``color``) filling its square: a basin of water (``detail``), a
    pedestal with an upper bowl and a little top bowl; on, water falls from the bowl into the
    basin and a jet rises from the top (the stage makes them flow and rings spread on the water)."""
    x, y, z = _fountain_middle(f)
    stone = look.main
    water = look.detail
    radius, wall, pool = BASIN
    shapes: list[Shape] = [Upright(x, y, z, z + wall, radius, stone), Disc((x, y, z + wall), radius - 0.08, shade(stone, 0.28), False),
                           Disc((x, y, z + wall + 0.001), pool, water, False, holds_snow=False),
                           Disc((x + 0.18, y - 0.25, z + wall + 0.002), 0.22, mix(water, SHINE, 0.35), False, holds_snow=False)]
    high, bowl = BOWL
    shapes += [Upright(x, y, z + wall - 0.02, z + wall + 0.12, 0.2, shade(stone, 0.06)), Upright(x, y, z + wall, z + high - 0.12, 0.12, stone),
               Upright(x, y, z + high - 0.16, z + high, bowl, stone), Disc((x, y, z + high + 0.001), bowl - 0.07, mix(water, SHINE, 0.15), False, holds_snow=False),
               Upright(x, y, z + high, z + 1.72, 0.07, stone), Upright(x, y, z + 1.72, z + 1.82, 0.17, stone),
               Disc((x, y, z + 1.821), 0.12, mix(water, SHINE, 0.15), False, holds_snow=False), Upright(x, y, z + 1.82, z + SPOUT, 0.035, shade(stone, 0.1))]
    if state.on and not look.moving:   # the stage draws the flowing water while it runs
        shapes += [Poly(m.points, m.fill, m.ink, m.glow) for m in _fountain_water(f, look, 0.4) if m.opacity >= 0.3]
    return shapes


def _parabola(start: Point3, end: Point3, lift: float, share: float) -> Point3:
    """A point ``share`` of the way along a falling arc from ``start`` to ``end``, ``lift`` (tile
    units) over the straight line at its middle."""
    return (start[0] + (end[0] - start[0]) * share, start[1] + (end[1] - start[1]) * share,
            start[2] + (end[2] - start[2]) * share * share + lift * 4 * share * (1 - share))


def _fountain_water(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A running fountain's water at ``now``: the jet from its top, falls from the upper bowl
    (each a stream with drops running down it) and rings spreading where they land."""
    x, y, z = _fountain_middle(f)
    pale = mix(look.detail, SHINE, 0.55)
    foam = mix(look.detail, SHINE, 0.85)
    radius, wall, pool = BASIN
    high, bowl = BOWL
    jet = 0.32 + 0.04 * math.sin(2 * math.pi * now * 1.3)
    top = (x, y, z + SPOUT)
    parts = [Motion((_screen(top, -0.02, 0.0), _screen(top, 0.02, 0.0), _screen(top, 0.008, jet * 0.86), _screen(top, 0.0, jet),
                     _screen(top, -0.008, jet * 0.86)), foam, 0.9, False)]
    for k, t in enumerate(FALL_ANGLES):
        start = (x + (bowl - 0.02) * math.cos(t), y + (bowl - 0.02) * math.sin(t), z + high)
        land = (x + 0.66 * math.cos(t), y + 0.66 * math.sin(t), z + wall + 0.003)
        arc = [_parabola(start, land, 0.08, s / 8) for s in range(9)]
        parts.append(Motion(tuple([_screen(p, -0.012 - 0.01 * s / 8, 0.0) for s, p in enumerate(arc)]
                                  + [_screen(p, 0.012 + 0.01 * s / 8, 0.0) for s, p in reversed(list(enumerate(arc)))]), pale, 0.55, False))
        for j in range(2):
            share = (now / FALL_SECONDS + j / 2 + k * 0.29) % 1.0
            parts.append(Motion(_round(_parabola(start, land, 0.08, share), 0.022, foam).points, foam, 0.95, False))
        spread = (now / RIPPLE_SECONDS + k * 0.37) % 1.0
        r0 = 0.05 + 0.16 * spread
        ring = [(land[0] + r * math.cos(a), land[1] + r * math.sin(a), land[2]) for r, angles in ((r0, range(13)), (r0 * 0.7, range(12, -1, -1)))
                for a in [-math.pi / 4 + math.pi * i / 12 for i in angles]]
        parts.append(Motion(tuple(ring), foam, 0.8 * (1.0 - spread), False))   # its near half: a crescent
    return parts


def _phone_booth(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A red telephone box (``color``): glazed in small panes on its front and side, a door
    handle (``detail``), a sign band under a crowned roof and the phone inside; on, its panes and
    sign glow and light falls on the pavement in front (it lights who stands near)."""
    a0, a1, b0, b1, h = 0.16, 0.84, 0.16, 0.84, 2.25
    body = look.main
    on = state.on
    shapes = light_pool(f.p(0.5, b1 + 0.2, 0.01), 0.8, 0.8) if on else []
    shapes += f.box(a0 - 0.03, b0 - 0.03, 0.0, a1 + 0.03, b1 + 0.03, 0.1, shade(body, 0.2))
    shapes += f.box(a0, b0, 0.1, a1, b1, h, body)
    pane = mix(LIT_GLASS, LIT_CORE, 0.45) if on else mix(GLASS, SHINE, 0.2)
    cols, rows, z0, z1 = 3, 6, 0.72, 1.92
    for face in ("front", "side"):
        lo, hi = (a0 + 0.1, a1 - 0.1)
        for i in range(cols):
            for j in range(rows):
                u0, u1 = lo + (hi - lo) * i / cols + 0.02, lo + (hi - lo) * (i + 1) / cols - 0.02
                v0, v1 = z0 + (z1 - z0) * j / rows + 0.02, z0 + (z1 - z0) * (j + 1) / rows - 0.02
                if face == "front":
                    shapes.append(_rect(f, u0, u1, b1 + 0.001, v0, v1, pane, False, on))
                else:
                    shapes.append(_side_rect(f, a1 + 0.001, b1 - u1 + b0, b1 - u0 + b0, v0, v1, pane, False, on))
        if face == "front":
            shapes.append(_rect(f, a0 + 0.1, a1 - 0.1, b1 + 0.001, 0.22, 0.6, shade(body, 0.12)))
            shapes.append(_rect(f, 0.36, 0.64, b1 + 0.002, 1.24, 1.5, CASING, True))   # the phone, through the glass
            shapes.append(Line((f.p(0.4, b1 + 0.003, 1.44), f.p(0.6, b1 + 0.003, 1.44)), shade(CASING, 0.4), 2.2))
            shapes.append(_rect(f, a1 - 0.12, a1 - 0.08, b1 + 0.002, 1.12, 1.36, look.detail))
        else:
            shapes.append(_side_rect(f, a1 + 0.001, b0 + 0.1, b1 - 0.1, 0.22, 0.6, f.side(shade(body, 0.12))))
    sign = LIT_CORE if on else PAPER
    shapes.append(_rect(f, a0 + 0.06, a1 - 0.06, b1 + 0.001, 2.0, 2.16, sign, True, on))
    shapes.append(_side_rect(f, a1 + 0.001, b0 + 0.06, b1 - 0.06, 2.0, 2.16, sign if on else f.side(sign), True, on))
    for k in range(5):   # its lettering
        u = a0 + 0.13 + k * 0.09
        shapes.append(Line((f.p(u, b1 + 0.002, 2.05), f.p(u + 0.05, b1 + 0.002, 2.05)), CASING, 1.4))
    shapes += f.box(a0 - 0.04, b0 - 0.04, h, a1 + 0.04, b1 + 0.04, h + 0.08, mix(body, SHINE, 0.06))
    shapes += f.box(a0 + 0.02, b0 + 0.02, h + 0.08, a1 - 0.02, b1 - 0.02, h + 0.2, body)
    crown = [(0.5 + 0.2 * math.cos(t), b1 - 0.019, h + 0.2 + 0.1 * math.sin(t)) for t in [math.pi * k / 10 for k in range(11)]]
    shapes.append(f.poly([(0.7, b1 - 0.019, h + 0.2), *crown, (0.3, b1 - 0.019, h + 0.2)], f.front(body)))
    return shapes + [f.poly(_face_circle(f, 0.5, b1 - 0.018, h + 0.24, 0.04, 10), look.detail)]


def _magazines(f: _Frame, a0: float, a1: float, z0: float, z1: float, rows: int, b: float | None = None, side: float | None = None,
               seed: int = 0) -> list[Shape]:
    """Rows of magazine covers on the front face at ``b`` (``a0`` .. ``a1`` across) or the right
    side face at ``a`` = ``side`` (``a0`` .. ``a1`` its ``b`` range): each a colour with a white
    masthead, a ledge under each row."""
    shapes: list[Shape] = []
    step = (z1 - z0) / rows
    count = max(1, round((a1 - a0) / 0.19))
    width = (a1 - a0) / count
    for r in range(rows):
        zz = z0 + r * step
        for k in range(count):
            u0, u1 = a0 + k * width + 0.015, a0 + (k + 1) * width - 0.015
            color = BOOK_COLORS[(k * 2 + r + seed) % len(BOOK_COLORS)]
            top = zz + step - 0.03
            if side is None:
                assert b is not None
                shapes.append(_rect(f, u0, u1, b, zz + 0.02, top, f.front(color)))
                shapes.append(_rect(f, u0 + 0.02, u1 - 0.02, b + 0.001, top - 0.07, top - 0.03, PAPER, False))
            else:
                shapes.append(_side_rect(f, side, u0, u1, zz + 0.02, top, f.side(color)))
                shapes.append(_side_rect(f, side + 0.001, u0 + 0.02, u1 - 0.02, top - 0.07, top - 0.03, PAPER, False))
        if side is None:
            assert b is not None
            shapes.append(Line((f.p(a0, b + 0.002, zz + 0.02), f.p(a1, b + 0.002, zz + 0.02)), TRIM, 1.6))
    return shapes


def _newsstand(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A street kiosk (``color``): racks of magazines on its front and side, an open hatch with
    papers on the counter under it, a striped awning (``detail`` and white) and a sign band."""
    w = f.width
    body = look.main
    a0, a1, b0, b1, h = 0.08, w - 0.08, 0.14, 0.7, 2.0
    shapes = f.box(a0, b0, 0.0, a1, b1, h, body)
    shapes += _magazines(f, a0 + 0.1, a1 - 0.1, 0.1, 0.92, 3, b=b1 + 0.001)
    shapes += _magazines(f, b0 + 0.08, b1 - 0.08, 0.1, 1.7, 5, side=a1 + 0.001, seed=2)
    shapes.append(_rect(f, a0 + 0.15, a1 - 0.15, b1 + 0.001, 1.08, 1.84, INSIDE))
    shapes += _magazines(f, a0 + 0.25, a1 - 0.25, 1.4, 1.78, 1, b=b1 + 0.002, seed=1)   # hung up inside the hatch
    shapes += f.box(a0 - 0.02, b1, 0.96, a1 + 0.02, b1 + 0.22, 1.04, mix(body, SHINE, 0.15))
    for k, (u0, u1) in enumerate(((0.3, 0.75), (1.15, 1.6))):   # stacks of newspapers on the counter
        shapes += f.box(u0, b1 + 0.03, 1.04, u1, b1 + 0.19, 1.13 + 0.03 * k, PAPER)
        for zz in (1.07, 1.1):
            shapes.append(Line((f.p(u0 + 0.02, b1 + 0.191, zz), f.p(u1 - 0.02, b1 + 0.191, zz)), "#B9BFC9", 0.6))
        shapes.append(f.poly([(u0 + 0.05, b1 + 0.05, 1.131 + 0.03 * k), (u1 - 0.1, b1 + 0.05, 1.131 + 0.03 * k), (u1 - 0.1, b1 + 0.12, 1.131 + 0.03 * k),
                              (u0 + 0.05, b1 + 0.12, 1.131 + 0.03 * k)], "#8A93A3", False))
    shapes += f.box(a0, b0, h, a1, b1, h + 0.32, look.detail)
    for k in range(4):   # the sign's letters as blocks
        u = w / 2 - 0.42 + k * 0.22
        shapes.append(_rect(f, u, u + 0.14, b1 + 0.001, h + 0.08, h + 0.24, mix(CASING, body, 0.3), False))
    shapes += f.box(a0 - 0.05, b0 - 0.05, h + 0.32, a1 + 0.05, b1 + 0.05, h + 0.4, shade(body, 0.15))
    stripes, out, high, low = 8, b1 + 0.38, h - 0.02, h - 0.24
    for k in range(stripes):   # the awning, sloping out over the counter
        u0, u1 = a0 + (a1 - a0) * k / stripes, a0 + (a1 - a0) * (k + 1) / stripes
        color = look.detail if k % 2 == 0 else "#F4F6FA"
        shapes.append(f.poly([(u0, b1, high), (u1, b1, high), (u1, out, low), (u0, out, low)], color, (False, True, False, True)))
    shapes.append(f.poly([(a1, b1, high), (a1, out, low), (a1, out, low - 0.04), (a1, b1, high - 0.04)], f.side(look.detail)))
    for k in range(stripes):
        u0, u1 = a0 + (a1 - a0) * k / stripes, a0 + (a1 - a0) * (k + 1) / stripes
        arc = [((u0 + u1) / 2 + (u1 - u0) / 2 * math.cos(t), out, low - 0.04 - 0.09 * math.sin(t)) for t in [math.pi * j / 8 for j in range(9)]]
        shapes.append(f.poly([(u1, out, low), *arc, (u0, out, low)], f.front(look.detail if k % 2 == 0 else "#F4F6FA")))
    return shapes


# ----- vehicles: car, bicycle ------------------------------------------------------------------------------


def _car(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A small parked car (``color``) side-on, its nose to the viewer's right: a body with
    wheels, doors and a handle, a cabin with windows (``detail``), bumpers, a grille and
    headlights; on, the headlights shine (light on the ground ahead) and the tail lights glow."""
    w, d = f.width, f.depth
    body = look.main
    on = state.on
    a0, a1, b0, b1 = 0.1, w - 0.1, 0.2, 0.84
    shapes = light_pool(f.p(a1 + 0.45, (b0 + b1) / 2, 0.01), 0.55, 0.9) if on else []
    shapes += f.box(a0, b0, 0.2, a1, b1, 0.68, body)
    c0, c1, low, high = b0 + 0.06, b1 - 0.06, 0.68, 1.28
    rear, roof0, roof1, nose = 0.42, 0.66, 1.26, 1.54
    shapes.append(f.poly([(rear, c0, low), (rear, c1, low), (roof0, c1, high), (roof0, c0, high)], shade(body, 0.2)))
    shapes.append(f.poly([(roof0, c0, high), (roof1, c0, high), (roof1, c1, high), (roof0, c1, high)], mix(body, SHINE, 0.1)))
    shapes.append(f.poly([(rear, c1, low), (nose, c1, low), (roof1, c1, high), (roof0, c1, high)], f.front(body)))

    def along(edge: float, rise: float, z: float) -> float:
        return edge + rise * (z - low) / (high - low)

    glass = look.detail
    w0, w1, pillar = low + 0.07, high - 0.07, 1.0
    for u_rear, u_front in ((lambda z: along(rear, roof0 - rear, z) + 0.07, lambda z: pillar - 0.03),
                            (lambda z: pillar + 0.03, lambda z: along(nose, roof1 - nose, z) - 0.07)):
        shapes.append(f.poly([(u_rear(w0), c1 + 0.001, w0), (u_front(w0), c1 + 0.001, w0), (u_front(w1), c1 + 0.001, w1), (u_rear(w1), c1 + 0.001, w1)],
                             f.front(glass)))
    shapes.append(Line((f.p(0.62, c1 + 0.002, 0.8), f.p(0.74, c1 + 0.002, 1.12)), SHINE, 1.2))
    shapes.append(f.poly([(nose, c1, low), (nose, c0, low), (roof1, c0, high), (roof1, c1, high)], f.side(body)))
    shapes.append(f.poly([(nose - 0.035, c1 - 0.05, low + 0.05), (nose - 0.035, c0 + 0.05, low + 0.05), (roof1 + 0.025, c0 + 0.05, high - 0.04),
                          (roof1 + 0.025, c1 - 0.05, high - 0.04)], f.side(mix(glass, SHINE, 0.15)), False))
    face = b1 + 0.001
    shapes.append(Line((f.p(0.98, face, 0.24), f.p(0.98, face, 0.66)), shade(body, 0.3), 0.9))
    shapes.append(Line((f.p(1.12, face + 0.001, 0.58), f.p(1.22, face + 0.001, 0.58)), TRIM, 2.2))
    shapes.append(Line((f.p(0.7, face + 0.001, 0.58), f.p(0.8, face + 0.001, 0.58)), TRIM, 2.2))
    shapes += f.box(1.42, b1, 0.7, 1.5, b1 + 0.07, 0.8, shade(body, 0.1))   # a mirror
    shapes.append(_rect(f, a0, a1, face, 0.2, 0.28, TRIM, False))
    shapes.append(_side_rect(f, a1 + 0.001, b0, b1, 0.2, 0.3, f.side(TRIM), False))
    tail = "#FF4A3D" if on else TAIL
    shapes.append(_rect(f, a0 + 0.01, a0 + 0.08, face + 0.001, 0.46, 0.6, tail, False, on))
    for u0, u1 in ((b0 + 0.05, b0 + 0.17), (b1 - 0.17, b1 - 0.05)):
        lamp = LIT_CORE if on else "#E6EAF0"
        shapes.append(_side_rect(f, a1 + 0.002, u0, u1, 0.46, 0.58, lamp, True, on))
    shapes.append(_side_rect(f, a1 + 0.002, b0 + 0.24, b1 - 0.24, 0.36, 0.5, CASING))
    shapes.append(_side_rect(f, a1 + 0.003, b0 + 0.27, b1 - 0.27, 0.22, 0.29, PAPER, False))   # the number plate
    for a in (0.44, w - 0.46):   # the near wheels in their arches
        shapes.append(f.poly([(a + 0.25 * math.cos(t), face + 0.001, 0.22 + 0.25 * math.sin(t)) for t in [math.pi * k / 12 for k in range(13)]],
                             shade(body, 0.5), False))
        shapes.append(f.poly(_face_circle(f, a, face + 0.002, 0.21, 0.21, 20), TYRE))
        shapes.append(f.poly(_face_circle(f, a, face + 0.003, 0.21, 0.1, 14), CHROME))
        shapes.append(f.poly(_face_circle(f, a, face + 0.004, 0.21, 0.035, 8), TRIM, False))
    return shapes


def _bicycle(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A bicycle on its stand, side-on (``color`` its frame): spoked wheels, a saddle, handlebars
    and a wicker basket (``detail``) over the front wheel."""
    b = 0.5
    frame = look.main

    def p(a: float, z: float, bb: float = b) -> Point3:
        return f.p(a, bb, z)

    shapes: list[Shape] = []
    hub_r, hub_f, r = (0.22, 0.22), (0.8, 0.22), 0.21
    for a, zc in (hub_r, hub_f):
        shapes.append(Line(tuple(p(a + r * math.cos(t), zc + r * math.sin(t)) for t in [2 * math.pi * k / 28 for k in range(29)]), TYRE, 2.8))
        shapes.append(Line(tuple(p(a + (r - 0.03) * math.cos(t), zc + (r - 0.03) * math.sin(t)) for t in [2 * math.pi * k / 28 for k in range(29)]),
                           CHROME, 0.9))
        for k in range(6):
            t = math.pi * k / 6
            shapes.append(Line((p(a + (r - 0.03) * math.cos(t), zc + (r - 0.03) * math.sin(t)), p(a - (r - 0.03) * math.cos(t), zc - (r - 0.03) * math.sin(t))),
                               "#B9BFC9", 0.5))
        shapes.append(_round(p(a, zc), 0.02, CHROME))
    crank, seat, head_top, head_low = (0.48, 0.22), (0.4, 0.58), (0.72, 0.62), (0.74, 0.52)
    shapes.append(Line((p(0.44, 0.2, b + 0.02), p(0.38, 0.0, b + 0.1)), TRIM, 1.4))   # the stand
    shapes.append(Line(tuple(p(crank[0] + 0.06 * math.cos(t), crank[1] + 0.06 * math.sin(t)) for t in [2 * math.pi * k / 14 for k in range(15)]), TRIM, 1.2))
    for pair in ((hub_r, crank), (hub_r, seat), (crank, seat), (seat, head_top), (crank, head_low), (head_top, head_low)):
        shapes.append(Line((p(*pair[0]), p(*pair[1])), frame, 2.2))
    shapes.append(Line((p(*head_low), p(*hub_f)), shade(frame, 0.15), 2.0))
    shapes.append(Line((p(*crank), p(0.52, 0.14, b + 0.05)), TRIM, 1.6))
    shapes.append(Line((p(0.49, 0.14, b + 0.05), p(0.56, 0.14, b + 0.05)), CASING, 2.0))   # a pedal
    shapes.append(Line((p(*seat), p(0.385, 0.7)), CHROME, 1.6))
    shapes.append(f.poly([(0.31, b, 0.71), (0.46, b, 0.73), (0.45, b, 0.69), (0.33, b, 0.68)], CASING))   # the saddle
    shapes.append(Line((p(*head_top), p(0.7, 0.76)), CHROME, 1.6))
    shapes.append(Line((p(0.7, 0.76, b - 0.17), p(0.7, 0.76, b + 0.17)), CASING, 2.2))   # the handlebars
    shapes += f.box(0.78, b - 0.09, 0.56, 0.94, b + 0.09, 0.7, look.detail)
    shapes.append(Line((f.p(0.78, b + 0.091, 0.63), f.p(0.94, b + 0.091, 0.63)), shade(look.detail, 0.3), 0.6))
    return shapes


#: The drawings of this module's kinds (each by its frame, look and state), and those with
#: moving parts the stage draws while they work (:func:`motion`).
DRAWINGS: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {
    "street_lamp": _street_lamp, "traffic_light": _traffic_light, "bus_stop": _bus_stop, "mailbox": _mailbox, "fountain": _fountain,
    "phone_booth": _phone_booth, "car": _car, "bicycle": _bicycle, "newsstand": _newsstand,
}
MOVING = frozenset({"traffic_light", "fountain"})


def motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """The moving parts of a working traffic light (its lamps in turn) or fountain (its jet,
    falls and spreading rings) at ``now``."""
    kind = f.item.kind
    if kind == "traffic_light":
        return _signal_motion(f, now)
    if kind == "fountain":
        return _fountain_water(f, look, now)
    return []


__all__ = ["DRAWINGS", "MOVING", "motion"]
