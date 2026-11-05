"""Farm, school and office iso objects (DESIGN.md §104, Phase AC Step 265): a vegetable patch, a
wheelbarrow, a hay bale, a pupil's desk, a desk with a computer, a water cooler, an office
printer, a floor globe and a shelf of trophies. No manim.

Drawn like :mod:`vidgen.cartoon.iso_objects`' objects (its frame, shading and helpers), which
looks each kind of this module up in :data:`DRAWINGS` and its moving parts in :func:`motion`.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from vidgen.cartoon.iso_drawing import Blobs, Disc, Line, Poly, Shape, Upright, mix, shade
from vidgen.cartoon.iso_home import _cone
from vidgen.cartoon.iso_objects import (
    CASING,
    DARK_SCREEN,
    DISPLAY_GREEN,
    SHINE,
    SOIL,
    Motion,
    ObjectLook,
    _cylinder,
    _face_circle,
    _fade,
    _Frame,
    _indicator,
    _profile,
    _reading,
    _rising,
    _round,
    _screen,
)
from vidgen.cartoon.iso_shop import _rect
from vidgen.world.iso import ObjectState
from vidgen.world.iso_view import Point3

#: Crops and leaves; a pencil's yellow; paper; the land on a globe; a stand's brass.
LEAF = "#4FA34A"
CABBAGE = "#8CC63F"
CARROT = "#F28C28"
STAKE = "#C9A86A"
PENCIL = "#F6C945"
PAPER = "#F7F4EC"
INK_GREY = "#8A93A3"
LAND = "#6CC070"
BRASS = "#D9A441"
#: Seconds of a line being typed on a computer's screen and of its cursor's blink.
TYPE_SECONDS = 3.2
BLINK_SECONDS = 0.8
#: A water cooler's bubbles and how long one takes to rise through its bottle (seconds).
COOLER_BUBBLES = 3
COOLER_BUBBLE_SECONDS = 1.9
#: Seconds of a printed sheet sliding out onto a printer's tray (it then settles on the stack),
#: and the tray: where it leaves the printer and where it ends (b, z in the printer's frame).
SHEET_SECONDS = 2.6
TRAY = ((0.822, 0.8), (1.08, 0.74))
SHEET_LENGTH = 0.26
#: Seconds of a globe's turn, its axis's tilt (degrees, its north leaning right), and its land:
#: outlines of (longitude, latitude) in degrees, longitude 0 facing the viewer at rest.
GLOBE_SECONDS = 9.0
GLOBE_TILT = 23.5
CONTINENTS: tuple[tuple[tuple[float, float], ...], ...] = (
    ((-100, 55), (-80, 64), (-60, 52), (-76, 32), (-82, 12), (-60, 6), (-38, -6), (-52, -26), (-68, -52), (-74, -30), (-80, -6),
     (-96, 16), (-112, 30), (-126, 52)),
    ((-10, 56), (20, 62), (36, 46), (30, 32), (46, 10), (40, -16), (26, -34), (16, -30), (10, -6), (-16, 10), (-16, 30), (-6, 42)),
    ((44, 60), (80, 72), (130, 66), (152, 56), (132, 36), (120, 20), (102, 8), (80, 10), (70, 25), (52, 30), (46, 46)),
    ((114, -20), (134, -12), (150, -20), (152, -36), (134, -36), (116, -32)),
)


# ----- a garden and a farm: vegetable patch, wheelbarrow, hay bale ---------------------------------------------


def _vegetable_patch(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A raised bed of planks (``color``) full of soil: staked tomato plants at the back (their
    fruit in ``detail``), a row of cabbages, then carrot tops at the front."""
    w, d = f.width, f.depth
    wood = look.main
    a0, a1, b0, b1, h = 0.08, w - 0.08, 0.1, d - 0.06, 0.3
    shapes = f.box(a0, b0, 0.0, a1, b1, h, wood)
    shapes.append(Line((f.p(a0, b1 + 0.001, h / 2), f.p(a1, b1 + 0.001, h / 2)), shade(wood, 0.3), 0.8))   # the planks' seams
    shapes.append(Line((f.p(a1 + 0.001, b1, h / 2), f.p(a1 + 0.001, b0, h / 2)), shade(wood, 0.35), 0.8))
    shapes.append(f.poly([(a0 + 0.06, b0 + 0.06, h + 0.001), (a1 - 0.06, b0 + 0.06, h + 0.001), (a1 - 0.06, b1 - 0.06, h + 0.001),
                          (a0 + 0.06, b1 - 0.06, h + 0.001)], SOIL, False))
    for a, b in ((a0, b0), (a1 - 0.08, b0), (a0, b1 - 0.08), (a1 - 0.08, b1 - 0.08)):   # corner posts
        shapes += f.box(a, b, 0.0, a + 0.08, b + 0.08, h + 0.07, shade(wood, 0.08))
    for b in (0.33, 0.57, 0.8):   # furrows
        shapes.append(Line((f.p(a0 + 0.1, b + 0.05, h + 0.002), f.p(a1 - 0.1, b + 0.05, h + 0.002)), shade(SOIL, 0.3), 0.8))
    n = max(2, round(w * 2))
    spots = [a0 + (a1 - a0) * (k + 0.5) / n for k in range(n)]
    for k, a in enumerate(spots):   # tomatoes on stakes
        foot = f.p(a, 0.3, h)
        top = (foot[0], foot[1], foot[2] + 0.75)
        shapes.append(Line((foot, top), STAKE, 1.4))
        leaves = tuple(_screen((foot[0], foot[1], foot[2] + z), du, 0.0) for du, z in ((-0.07, 0.22), (0.07, 0.36), (-0.05, 0.5), (0.05, 0.62)))
        shapes.append(Blobs(leaves, (0.09, 0.085, 0.08, 0.065), LEAF))
        for du, z in ((0.05, 0.24), (-0.06, 0.4), (0.04, 0.52))[: 2 + k % 2]:
            shapes.append(_round(_screen((foot[0], foot[1], foot[2] + z), du, 0.0), 0.036, look.detail))
    for k, a in enumerate(spots):   # cabbages
        heart = f.p(a + (0.06 if k % 2 else -0.04), 0.56, h + 0.07)
        shapes.append(Blobs((_screen(heart, -0.06, -0.01), _screen(heart, 0.06, -0.01)), (0.07, 0.07), shade(CABBAGE, 0.12)))
        shapes.append(Blobs((heart,), (0.1,), CABBAGE))
        shapes.append(Blobs((_screen(heart, -0.015, 0.025),), (0.05,), mix(CABBAGE, SHINE, 0.3), False))
    for k, a in enumerate(spots):   # carrots: their shoulders and leafy tops
        for j, da in enumerate((-0.12, 0.08)):
            root = f.p(a + da + 0.03 * (k % 2), 0.8, h + 0.002)
            for du in (-0.045, 0.0, 0.045):
                shapes.append(Line((_screen(root, 0.0, 0.04), _screen(root, du, 0.14 + 0.02 * ((j + k) % 2))), "#3E8E3E", 1.3))
            shapes.append(_profile(root, [(-0.04, -0.01), (0.04, -0.01), (0.032, 0.05), (-0.032, 0.05)], CARROT))
    return shapes


def _wheelbarrow(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A wheelbarrow (its tray in ``color``) with soil and a seedling in it: a wheel at its nose,
    two legs and two handles (``detail``) reaching back."""
    tray, wood = look.main, look.detail
    hub = f.p(0.14, 0.5, 0.17)
    shapes: list[Shape] = [Line((f.p(0.66, 0.32, 0.0), f.p(0.62, 0.32, 0.36)), shade(wood, 0.2), 2.2),   # the back leg and handle
                           Line((f.p(0.22, 0.32, 0.34), f.p(0.98, 0.26, 0.62)), shade(wood, 0.15), 2.4)]
    shapes.append(Line((hub, f.p(0.3, 0.38, 0.34)), shade(wood, 0.2), 1.8))
    wheel = _face_circle(f, 0.14, 0.5, 0.17, 0.17, 20)
    shapes += [f.poly(wheel, CASING), f.poly(_face_circle(f, 0.14, 0.501, 0.17, 0.1, 16), "#5A6272", False),
               f.poly(_face_circle(f, 0.14, 0.502, 0.17, 0.035, 10), "#C9CED6", False)]
    rim = [(0.2, 0.22, 0.66), (0.86, 0.22, 0.66), (0.86, 0.78, 0.66), (0.2, 0.78, 0.66)]
    floor = [(0.34, 0.34, 0.34), (0.76, 0.34, 0.34), (0.76, 0.66, 0.34), (0.34, 0.66, 0.34)]
    shapes.append(f.poly(rim, shade(tray, 0.4)))   # its inside as seen over the rim
    heap = f.p(0.54, 0.5, 0.6)
    shapes.append(Blobs((_screen(heap, -0.13, -0.01), heap, _screen(heap, 0.13, -0.02)), (0.1, 0.13, 0.09), SOIL))
    sprout = _screen(heap, 0.02, 0.1)
    shapes.append(Line((sprout, _screen(sprout, 0.0, 0.1)), "#3E8E3E", 1.2))
    shapes += [_round(_screen(sprout, -0.04, 0.11), 0.035, LEAF), _round(_screen(sprout, 0.04, 0.12), 0.035, LEAF)]
    shapes.append(f.poly([floor[3], floor[2], rim[2], rim[3]], f.front(tray)))   # its front and right side
    shapes.append(f.poly([floor[2], floor[1], rim[1], rim[2]], f.side(tray)))
    shapes.append(Line(tuple(f.p(*q) for q in (*rim, rim[0])), mix(tray, SHINE, 0.25), 1.2))
    shapes.append(Line((hub, f.p(0.3, 0.62, 0.34)), wood, 1.8))
    shapes.append(Line((f.p(0.66, 0.68, 0.0), f.p(0.62, 0.68, 0.36)), wood, 2.2))   # the front leg and handle
    shapes.append(Line((f.p(0.22, 0.68, 0.34), f.p(0.98, 0.74, 0.62)), wood, 2.4))
    return shapes + [Line((f.p(0.88, 0.735, 0.585), f.p(0.98, 0.74, 0.62)), shade(wood, 0.4), 3.0)]   # a grip


def _hay_bale(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A rectangular bale of straw (``color``) tied with two bands of twine (``detail``), straws
    poking from its edges and a few loose on the ground; small things can sit on it."""
    w, d = f.width, f.depth
    straw = look.main
    a0, a1, b0, b1, h = 0.1, w - 0.1, 0.16, d - 0.1, 0.72
    shapes: list[Shape] = []
    for k in range(5):   # loose straws on the ground in front
        a = a0 + (a1 - a0) * ((k * 0.37 + 0.1) % 1.0)
        shapes.append(Line((f.p(a, b1 + 0.06, 0.004), f.p(a + 0.12, b1 + 0.03 + 0.04 * (k % 2), 0.004)), shade(straw, 0.1), 1.0))
    shapes += f.box(a0, b0, 0.0, a1, b1, h, straw)
    dark, pale = shade(straw, 0.28), mix(straw, SHINE, 0.35)
    for k in range(int(9 * (a1 - a0))):   # its texture: short straws on the top, the front and the cut end
        s, t = (k * 0.618) % 1.0, (k * 0.381 + 0.2) % 1.0
        a, b = a0 + 0.06 + (a1 - a0 - 0.2) * s, b0 + 0.06 + (b1 - b0 - 0.16) * t
        shapes.append(Line((f.p(a, b, h + 0.002), f.p(a + 0.1, b + 0.02 * (k % 3 - 1), h + 0.002)), dark if k % 2 else pale, 0.8))
        z = 0.08 + (h - 0.18) * t
        shapes.append(Line((f.p(a, b1 + 0.002, z), f.p(a + 0.09, b1 + 0.002, z + 0.03 * (k % 3 - 1))), dark if k % 3 else pale, 0.8))
        if k < 7:
            bb, zz = b0 + 0.08 + (b1 - b0 - 0.16) * s, 0.08 + (h - 0.18) * t
            shapes.append(_round(f.p(a1 + 0.002, bb, zz), 0.012, dark, False))
    for share in (0.27, 0.73):   # the twine round its short way
        a = a0 + (a1 - a0) * share
        shapes.append(Line((f.p(a, b0, h + 0.003), f.p(a, b1, h + 0.003), f.p(a, b1 + 0.003, 0.0)), look.detail, 1.6))
    for k in range(6):   # straws poking out of its edges
        a = a0 + 0.1 + (a1 - a0 - 0.2) * k / 5
        shapes.append(Line((f.p(a, b1, h), f.p(a + 0.05, b1 + 0.05, h + 0.07 + 0.03 * (k % 2))), straw, 1.0))
    return shapes + [Line((f.p(a1, b1 - 0.2, h), f.p(a1 + 0.05, b1 - 0.24, h + 0.08)), straw, 1.0)]


# ----- a classroom and an office: school desk, desk with a PC, water cooler, printer, globe, trophies ----------


def _school_desk(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A pupil's desk (``color`` its wood) on a steel frame (``detail``) with its chair in front
    of it, so a pupil would face the room's back wall (its board): a lid sloping down to the
    chair, a pencil groove at its far edge, the book box under it, an open book, a pencil and an
    apple on it."""
    wood, steel = look.main, look.detail
    b0, b1, high, low = 0.06, 0.52, 0.8, 0.72   # the lid: from its far edge to its near edge

    def on_lid(a: float, b: float, lift: float = 0.004) -> Point3:
        return f.p(a, b, high + (low - high) * (b - b0) / (b1 - b0) + lift)

    shapes: list[Shape] = []
    for a in (0.14, 0.81):   # the desk's back legs, its book box, its front legs and footrest
        shapes += f.box(a, 0.1, 0.0, a + 0.05, 0.15, 0.66, steel)
    shapes += f.box(0.12, 0.1, 0.56, 0.88, 0.48, 0.68, shade(wood, 0.08))
    for a in (0.14, 0.81):
        shapes += f.box(a, 0.43, 0.0, a + 0.05, 0.48, 0.6, steel)
    shapes.append(Line((f.p(0.16, 0.46, 0.04), f.p(0.84, 0.46, 0.04)), steel, 1.6))
    shapes.append(f.poly([(0.92, b1, low - 0.04), (0.92, b0, high - 0.04), (0.92, b0, high), (0.92, b1, low)], f.side(wood)))
    shapes.append(f.poly([(0.08, b1, low - 0.04), (0.92, b1, low - 0.04), (0.92, b1, low), (0.08, b1, low)], f.front(wood)))
    shapes.append(f.poly([(0.08, b0, high), (0.92, b0, high), (0.92, b1, low), (0.08, b1, low)], mix(wood, SHINE, 0.08)))
    shapes.append(Line((on_lid(0.12, 0.14, 0.002), on_lid(0.88, 0.14, 0.002)), shade(wood, 0.35), 1.2))   # the pencil groove
    for a0, a1, color in ((0.3, 0.49, PAPER), (0.51, 0.7, mix(PAPER, "#DDE4EE", 0.5))):   # an open book
        shapes.append(Poly((on_lid(a0, 0.22), on_lid(a1, 0.22), on_lid(a1, 0.46), on_lid(a0, 0.46)), color))
        for b in (0.29, 0.35, 0.41):
            shapes.append(Line((on_lid(a0 + 0.03, b, 0.006), on_lid(a1 - 0.03, b, 0.006)), INK_GREY, 0.5))
    shapes.append(Line((on_lid(0.18, 0.12, 0.012), on_lid(0.52, 0.12, 0.012)), PENCIL, 2.0))
    shapes.append(Line((on_lid(0.52, 0.12, 0.012), on_lid(0.56, 0.12, 0.012)), "#3A2A1A", 1.2))
    apple = _screen(on_lid(0.8, 0.3), 0.0, 0.05)
    fruit = [_round(apple, 0.055, "#E2574C"), Line((_screen(apple, 0.0, 0.05), _screen(apple, 0.01, 0.08)), "#6B4A2E", 1.2),
             _round(_screen(apple, 0.035, 0.075), 0.018, LEAF, False), _round(_screen(apple, -0.02, 0.02), 0.012, SHINE, False)]
    shapes += fruit
    for a in (0.28, 0.72):   # the chair: its front legs, its seat, then its back legs holding the backrest
        shapes.append(Line((f.p(a, 0.58, 0.0), f.p(a, 0.58, 0.44)), steel, 1.8))
    shapes += f.box(0.26, 0.56, 0.42, 0.74, 0.86, 0.48, wood)
    for a in (0.28, 0.72):
        shapes.append(Line((f.p(a, 0.88, 0.0), f.p(a, 0.88, 0.86)), steel, 1.8))
    return shapes + f.box(0.25, 0.86, 0.58, 0.75, 0.91, 0.86, wood)


def _pc_screen(f: _Frame) -> tuple[float, float, float, float, float]:
    """A desk's monitor's screen: a from, a to, its face, its bottom and top."""
    cx = f.width * 0.42
    return cx - 0.45, cx + 0.45, 0.331, 1.0, 1.56


def _typed(f: _Frame, share: float, blink: bool) -> list[Poly]:
    """The line being typed in a computer's window, ``share`` of it written, and its cursor
    (shown while ``blink``): lights on the screen."""
    a0, a1, b, z0, z1 = _pc_screen(f)
    start = a0 + (a1 - a0) * 0.12
    end = start + (a1 - a0) * 0.46 * share
    z = z0 + 0.11
    left, right = sorted((_reading(f, start, a0, a1), _reading(f, end, a0, a1)))
    line = f.poly([(left, b + 0.002, z), (right, b + 0.002, z), (right, b + 0.002, z + 0.035), (left, b + 0.002, z + 0.035)], INK_GREY, False, True)
    at = _reading(f, end + 0.02, a0, a1)
    cursor = f.poly([(at - 0.012, b + 0.003, z - 0.01), (at + 0.012, b + 0.003, z - 0.01), (at + 0.012, b + 0.003, z + 0.05),
                     (at - 0.012, b + 0.003, z + 0.05)], CASING if blink else "#F4F6FA", False, True)
    return [line, cursor]


def _desk_with_pc(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """An office desk (``color``) with a drawer pedestal, a computer under it, a monitor, a
    keyboard, a mouse, papers and a mug on it; on, the screen glows: a desktop in ``detail`` with
    a window of text, a line being typed (the stage types it), icons and a taskbar."""
    w, d = f.width, f.depth
    desk = look.main
    on = state.on
    shapes = f.box(0.08, 0.16, 0.0, 0.16, d - 0.1, 0.72, shade(desk, 0.15))
    tower = "#3A3F4B"
    shapes += f.box(0.3, 0.3, 0.0, 0.56, d - 0.18, 0.6, tower)
    face = d - 0.18 + 0.001
    shapes.append(_rect(f, 0.34, 0.52, face, 0.44, 0.47, CASING, False))   # a drive slot
    shapes.append(_indicator(f, 0.4, 0.46, face, 0.36, 0.39, DISPLAY_GREEN, on))
    shapes += f.box(w - 0.62, 0.16, 0.0, w - 0.08, d - 0.1, 0.72, desk)
    front = d - 0.1 + 0.001
    for z0, z1 in ((0.04, 0.3), (0.34, 0.5), (0.54, 0.68)):   # its drawers
        shapes.append(_rect(f, w - 0.59, w - 0.11, front, z0, z1, f.front(mix(desk, SHINE, 0.06))))
        shapes.append(Line((f.p(w - 0.42, front + 0.001, z1 - 0.06), f.p(w - 0.28, front + 0.001, z1 - 0.06)), "#8A93A3", 1.8))
    shapes += f.box(0.04, 0.12, 0.72, w - 0.04, d - 0.06, 0.78, desk)
    shapes += f.box(0.1, 0.22, 0.78, 0.38, 0.58, 0.84, PAPER)   # papers
    shapes.append(Line((f.p(0.14, 0.4, 0.841), f.p(0.32, 0.4, 0.841)), INK_GREY, 0.6))
    a0, a1, b, z0, z1 = _pc_screen(f)
    cx = (a0 + a1) / 2
    shapes += f.box(cx - 0.18, 0.26, 0.78, cx + 0.18, 0.46, 0.8, CASING)
    shapes += f.box(cx - 0.04, 0.28, 0.8, cx + 0.04, 0.34, 1.0, CASING)
    shapes += f.box(a0 - 0.05, 0.26, z0 - 0.05, a1 + 0.05, b - 0.001, z1 + 0.05, CASING)
    if on:
        sky = look.detail
        shapes.append(_rect(f, a0, a1, b, z0, z1, sky, False, True))
        shapes.append(_rect(f, a0, a1, b + 0.0005, z0, z0 + 0.05, shade(sky, 0.4), False, True))   # the taskbar
        u0, u1 = sorted(_reading(f, a0 + (a1 - a0) * s, a0, a1) for s in (0.07, 0.72))
        shapes.append(_rect(f, u0, u1, b + 0.001, z0 + 0.08, z1 - 0.07, "#F4F6FA", False, True))   # a window
        shapes.append(_rect(f, u0, u1, b + 0.0015, z1 - 0.13, z1 - 0.07, mix(sky, CASING, 0.25), False, True))
        for k, z in enumerate((z1 - 0.21, z1 - 0.28, z1 - 0.35)):
            l0, l1 = sorted(_reading(f, a0 + (a1 - a0) * s, a0, a1) for s in (0.12, 0.12 + 0.52 * (0.95, 0.6, 0.8)[k]))
            shapes.append(_rect(f, l0, l1, b + 0.002, z, z + 0.035, INK_GREY, False, True))
        for k, color in enumerate((PENCIL, "#F4F6FA")):   # icons on the desktop
            i0, i1 = sorted(_reading(f, a0 + (a1 - a0) * s, a0, a1) for s in (0.8, 0.9))
            shapes.append(_rect(f, i0, i1, b + 0.001, z1 - 0.15 - 0.13 * k, z1 - 0.07 - 0.13 * k, color, False, True))
        if not look.moving:   # the stage types the line while it is on
            shapes += _typed(f, 0.6, True)
    else:
        shapes.append(_rect(f, a0, a1, b, z0, z1, DARK_SCREEN, False))
        shapes.append(_rect(f, a1 - 0.3, a1 - 0.18, b + 0.001, z0 + 0.04, z1 - 0.04, mix(DARK_SCREEN, SHINE, 0.1), False))
    shapes.append(_indicator(f, a1 - 0.03, a1 + 0.01, b, z0 - 0.04, z0 - 0.015, DISPLAY_GREEN, on))
    shapes += f.box(cx - 0.32, 0.5, 0.78, cx + 0.32, 0.7, 0.81, "#E6EAF0")   # the keyboard
    for bb in (0.55, 0.6, 0.65):
        shapes.append(Line((f.p(cx - 0.28, bb, 0.811), f.p(cx + 0.28, bb, 0.811)), "#9AA3B2", 0.6))
    mx, my, mz = f.p(cx + 0.47, 0.6, 0.78)
    shapes.append(Disc((mx, my, mz + 0.005), 0.1, "#3A6EA5", False, holds_snow=False))   # a mouse pad, a mouse
    shapes += [Upright(mx, my, mz + 0.006, mz + 0.04, 0.045, "#E6EAF0")]
    x, y, z = f.p(w - 0.26, 0.42, 0.78)
    mug = "#E2574C"
    return shapes + [_round(_screen((x, y, z + 0.08), 0.065, 0.0), 0.035, shade(mug, 0.2)), Upright(x, y, z, z + 0.15, 0.06, mug),
                     Disc((x, y, z + 0.15), 0.05, "#6B3F22", False, holds_snow=False)]


def _cooler_middle(f: _Frame) -> Point3:
    return f.p(0.5, 0.52, 0.0)


def _water_cooler(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A water cooler (``color``) with a big upturned bottle of water (``detail``) on it, a red
    and a blue tap over a drip tray, and a tube of paper cups at its side; on, its light shows
    and bubbles rise through the bottle (the stage moves them)."""
    body = look.main
    water = look.detail
    shapes = f.box(0.26, 0.28, 0.0, 0.74, 0.76, 1.05, body)
    face = 0.761
    shapes.append(_rect(f, 0.32, 0.68, face, 0.58, 0.92, shade(body, 0.28), False))   # the recess
    for z in (0.12, 0.2, 0.28):   # a vent
        shapes.append(Line((f.p(0.36, face, z), f.p(0.64, face, z)), shade(body, 0.3), 0.8))
    shapes += f.box(0.34, 0.6, 0.58, 0.66, 0.82, 0.62, "#8A93A3")   # the drip tray
    for a, tap in ((0.37, "#E2574C"), (0.57, "#4C8DD6")):
        shapes += f.box(a, 0.7, 0.8, a + 0.06, 0.8, 0.87, tap)
    shapes.append(_indicator(f, 0.46, 0.54, face, 0.97, 1.0, DISPLAY_GREEN, state.on))
    x, y, _ = _cooler_middle(f)
    z = f.base
    cx, cy, cz = f.p(0.84, 0.5, 0.5)   # the cups' tube
    shapes += [Upright(cx, cy, cz, cz + 0.42, 0.05, "#F4F6FA"), _round((cx, cy, cz - 0.03), 0.035, "#F4F6FA")]
    shapes.append(Upright(x, y, z + 1.05, z + 1.1, 0.1, shade(body, 0.12)))
    shapes.append(_cone(x, y, z + 1.1, z + 1.22, 0.08, 0.22, water))
    glass = mix(water, SHINE, 0.55)
    shapes += _cylinder(x, y, z + 1.2, z + 1.84, 0.22, glass, lid=mix(glass, SHINE, 0.3))
    shapes += _cylinder(x, y, z + 1.2, z + 1.7, 0.215, water, ink=False, lid=mix(water, SHINE, 0.3))
    for zz in (1.38, 1.56):   # its ridges
        arc = [(x + 0.218 * math.cos(t), y + 0.218 * math.sin(t), z + zz) for t in [-math.pi / 4 + math.pi * k / 12 for k in range(13)]]
        shapes.append(Line(tuple(arc), shade(water, 0.2), 0.8))
    shapes.append(Line((_screen((x, y, z + 1.3), -0.13, 0.0), _screen((x, y, z + 1.76), -0.13, 0.0)), SHINE, 1.4))
    if state.on and not look.moving:   # the stage bubbles it while it is on
        shapes += [Poly(m.points, m.fill, m.ink, m.glow) for m in _cooler_bubbles(f, look, 0.5) if m.opacity > 0.4]
    return shapes


def _cooler_bubbles(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A working water cooler's bubbles at ``now``, rising from the bottle's neck to the water's top."""
    x, y, _ = _cooler_middle(f)
    z = f.base
    pale = mix(look.detail, SHINE, 0.75)
    parts = []
    for k in range(COOLER_BUBBLES):
        rise = _rising(now, k, COOLER_BUBBLES, COOLER_BUBBLE_SECONDS)
        sway = 0.03 * math.sin(2 * math.pi * (rise * 1.3 + k * 0.4)) + 0.04 * (k - 1)
        point = _screen((x, y, z + 1.16 + 0.48 * rise), sway, 0.0)
        parts.append(Motion(_round(point, 0.022 + 0.022 * rise, pale).points, pale, 0.9 * _fade(rise), False))
    return parts


def _sheet(f: _Frame, share: float) -> tuple[list[tuple[float, float, float]], float]:
    """A printed sheet ``share`` of the way through its time: its corners on the tray (in the
    frame) and its opacity (it slides out, then settles on the stack and fades)."""
    (s0, t0), (s1, t1) = TRAY

    def on_tray(b: float) -> float:
        return t0 + (t1 - t0) * (b - s0) / (s1 - s0) + 0.014

    out = min(1.0, share / 0.7)
    tip = s0 + (s1 - 0.02 - s0) * out
    tail = max(s0, tip - SHEET_LENGTH)
    corners = [(0.33, tail, on_tray(tail)), (0.67, tail, on_tray(tail)), (0.67, tip, on_tray(tip)), (0.33, tip, on_tray(tip))]
    return corners, 1.0 if share < 0.7 else max(0.0, 1.0 - (share - 0.7) / 0.25)


def _printer(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """An office printer (``color``) on its paper drawers: a scanner lid, a control panel whose
    screen glows in ``detail`` when on, a slot over a tray with a stack of printed sheets; on, a
    sheet slides out onto the stack (the stage moves it)."""
    body = look.main
    shapes = f.box(0.14, 0.2, 0.0, 0.86, 0.82, 0.5, shade(body, 0.1))
    face = 0.821
    for z0, z1 in ((0.05, 0.23), (0.27, 0.45)):   # the paper drawers
        shapes.append(_rect(f, 0.18, 0.82, face, z0, z1, f.front(mix(body, SHINE, 0.05))))
        shapes.append(Line((f.p(0.4, face + 0.001, z1 - 0.05), f.p(0.6, face + 0.001, z1 - 0.05)), shade(body, 0.4), 1.6))
    shapes += f.box(0.12, 0.18, 0.5, 0.88, 0.82, 1.02, body)
    shapes.append(_rect(f, 0.26, 0.74, face, 0.8, 0.9, "#2E2A38"))   # the slot
    shapes.append(_rect(f, 0.14, 0.86, face, 0.6, 0.635, look.detail, False))   # a trim
    (s0, t0), (s1, t1) = TRAY
    shapes.append(f.poly([(0.28, s0, t0), (0.72, s0, t0), (0.72, s1, t1), (0.28, s1, t1)], shade(body, 0.4)))
    shapes.append(f.poly([(0.28, s1, t1), (0.72, s1, t1), (0.72, s1, t1 + 0.04), (0.28, s1, t1 + 0.04)], shade(body, 0.3)))
    shapes += f.box(0.12, 0.18, 1.02, 0.88, 0.82, 1.1, shade(body, 0.12))   # the scanner's lid
    shapes += f.box(0.5, 0.58, 1.1, 0.84, 0.8, 1.14, CASING)
    screen = look.detail if state.on else DARK_SCREEN
    shapes.append(f.poly([(0.54, 0.62, 1.141), (0.72, 0.62, 1.141), (0.72, 0.77, 1.141), (0.54, 0.77, 1.141)], screen, False, state.on))
    if state.on:
        shapes.append(f.poly([(0.57, 0.68, 1.142), (0.68, 0.68, 1.142), (0.68, 0.71, 1.142), (0.57, 0.71, 1.142)], SHINE, False, True))
    shapes.append(Disc(f.p(0.78, 0.66, 1.142), 0.025, DISPLAY_GREEN if state.on else "#3D4350", False, glow=state.on, holds_snow=False))
    shapes.append(Disc(f.p(0.78, 0.74, 1.142), 0.025, "#E2574C", False, holds_snow=False))
    if state.on and not look.moving:   # the stage slides the sheet out while it prints
        corners, _ = _sheet(f, 0.4)
        shapes.append(f.poly(corners, PAPER))
    return shapes


def _sheet_motion(f: _Frame, now: float) -> list[Motion]:
    """A printing printer's sheet at ``now``: the sheet and two printed lines on it."""
    share = (now % SHEET_SECONDS) / SHEET_SECONDS
    corners, seen = _sheet(f, share)
    parts = [Motion(tuple(f.p(*q) for q in corners), PAPER, seen, True)]
    tip = corners[2][1]
    for k, back in enumerate((0.06, 0.13)):
        b = tip - back
        shown = seen if b - 0.02 > corners[0][1] else 0.0
        z = corners[2][2] + (corners[0][2] - corners[2][2]) * (back / max(SHEET_LENGTH, 1e-6)) + 0.002
        parts.append(Motion(tuple(f.p(*q) for q in ((0.38, b, z), (0.62 - 0.08 * k, b, z), (0.62 - 0.08 * k, b + 0.025, z), (0.38, b + 0.025, z))),
                            INK_GREY, shown, False))
    return parts


def _globe_centre(f: _Frame) -> tuple[Point3, float]:
    """A globe's middle and radius (tile widths)."""
    return f.p(f.width / 2, f.depth / 2, 0.98), 0.3


def _land(f: _Frame, turn: float) -> list[Motion]:
    """A globe's land turned by ``turn`` (radians): each continent's outline on the side seen
    (points over the edge pressed onto it), hidden while all of it is round the back."""
    centre, radius = _globe_centre(f)
    tilt = math.radians(GLOBE_TILT)
    parts = []
    for outline in CONTINENTS:
        points, seen = [], 0
        for lon, lat in outline:
            lam, phi = math.radians(lon) + turn, math.radians(lat)
            sx, sy, depth = math.cos(phi) * math.sin(lam), math.sin(phi), math.cos(phi) * math.cos(lam)
            if depth < 0:
                norm = math.hypot(sx, sy) or 1.0
                sx, sy = sx / norm, sy / norm
            else:
                seen += 1
            du, dv = sx * math.cos(tilt) + sy * math.sin(tilt), -sx * math.sin(tilt) + sy * math.cos(tilt)
            points.append(_screen(centre, radius * 0.985 * du, radius * 0.985 * dv))
        parts.append(Motion(tuple(points), LAND, 1.0 if seen >= 2 else 0.0, True))
    return parts


def _globe_shine(f: _Frame, look: ObjectLook) -> list[Motion]:
    """The light on a globe: a soft shine at its upper left."""
    centre, radius = _globe_centre(f)
    shine = mix(look.main, SHINE, 0.55)
    return [Motion(_round(_screen(centre, -radius * 0.45, radius * 0.45), radius * 0.15, shine).points, shine, 1.0, False)]


def _shadow_side(centre: Point3, radius: float, fill: str) -> Poly:
    """A sphere's shaded side: a crescent along its lower right edge."""
    span = [math.radians(80 - 200 * k / 16) for k in range(17)]
    outer = [_screen(centre, radius * math.cos(t), radius * math.sin(t)) for t in span]
    inner = [_screen(centre, -radius * 0.16 + radius * 0.9 * math.cos(t), radius * 0.1 + radius * 0.9 * math.sin(t)) for t in reversed(span)]
    return Poly(tuple(outer + inner), fill, False)


def _globe(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A floor globe: seas in ``color`` with green land, on a tilted brass ring over a wooden
    tripod (``detail``); on, it spins (the stage turns its land)."""
    centre, radius = _globe_centre(f)
    x, y, z = f.p(f.width / 2, f.depth / 2, 0.0)
    wood = look.detail
    hub = (x, y, z + 0.3)
    feet = sorted((2 * math.pi * k / 3 + 0.35 for k in range(3)), key=lambda t: math.cos(t) + math.sin(t))
    shapes: list[Shape] = []
    for t in feet[:1]:   # the leg behind
        shapes.append(Line((hub, (x + 0.32 * math.cos(t), y + 0.32 * math.sin(t), z)), shade(wood, 0.2), 2.6))
    tilt = math.radians(GLOBE_TILT)
    axis = (math.sin(tilt), math.cos(tilt))
    bottom = _screen(centre, -axis[0] * radius * 1.14, -axis[1] * radius * 1.14)
    shapes.append(Upright(x, y, z + 0.26, bottom[2], 0.035, wood))
    shapes.append(_round(_screen(hub, 0.0, 0.01), 0.05, shade(wood, 0.1)))
    for t in feet[1:]:
        shapes.append(Line((hub, (x + 0.32 * math.cos(t), y + 0.32 * math.sin(t), z)), wood, 2.6))
    shapes.append(_round(centre, radius, look.main))
    shapes.append(_shadow_side(centre, radius, shade(look.main, 0.15)))
    if not (state.on and look.moving):   # the stage turns its land while it spins
        shapes += [Poly(m.points, m.fill, m.ink) for m in _land(f, 0.0) if m.opacity > 0]
        shapes += [Poly(m.points, m.fill, m.ink) for m in _globe_shine(f, look)]
    ring = [_screen(centre, radius * 1.12 * math.cos(t), radius * 1.12 * math.sin(t)) for t in [2 * math.pi * k / 40 for k in range(41)]]
    shapes.append(Line(tuple(ring), shade(BRASS, 0.25), 3.4))
    shapes.append(Line(tuple(ring), BRASS, 2.0))
    for s in (1.0, -1.0):   # the axis's pins
        shapes.append(_round(_screen(centre, s * axis[0] * radius * 1.12, s * axis[1] * radius * 1.12), 0.03, BRASS))
    return shapes


def _trophy(base: Point3, size: float, metal: str) -> list[Shape]:
    """A cup on a plinth (``size``: its scale), its handles and a shine."""
    s = size
    shapes: list[Shape] = [_profile(base, [(-0.07 * s, 0.0), (0.07 * s, 0.0), (0.06 * s, 0.06 * s), (-0.06 * s, 0.06 * s)], "#3A2A1A")]
    shapes.append(_profile(base, [(-0.045 * s, 0.06 * s), (0.045 * s, 0.06 * s), (0.015 * s, 0.1 * s), (0.015 * s, 0.15 * s),
                                  (-0.015 * s, 0.15 * s), (-0.015 * s, 0.1 * s)], shade(metal, 0.12)))
    for side in (-1.0, 1.0):
        handle = [_screen(base, side * (0.08 * s + 0.035 * s * math.sin(t)), 0.24 * s + 0.045 * s * math.cos(t)) for t in [math.pi * k / 8 for k in range(9)]]
        shapes.append(Line(tuple(handle), shade(metal, 0.15), 1.8))
    shapes.append(_profile(base, [(-0.09 * s, 0.3 * s), (0.09 * s, 0.3 * s), (0.075 * s, 0.2 * s), (0.03 * s, 0.15 * s), (-0.03 * s, 0.15 * s),
                                  (-0.075 * s, 0.2 * s)], metal))
    return shapes + [Line((_screen(base, -0.05 * s, 0.28 * s), _screen(base, -0.04 * s, 0.2 * s)), mix(metal, SHINE, 0.6), 1.2)]


def _trophy_shelf(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A wooden cabinet of open shelves (``color``) against the wall, full of prizes (``detail``
    the gold): a big cup and two statuettes on top, silver and bronze cups round a medal hung on
    its ribbon, a plaque and a star below."""
    w = f.width
    wood, gold = look.main, look.detail
    a0, a1, b0, b1, top = 0.08, w - 0.08, 0.14, 0.58, 2.0
    shapes = f.box(a0, b0, 0.0, a1, b1, top, wood)
    shapes.append(_rect(f, a0 + 0.07, a1 - 0.07, b1, 0.1, top - 0.08, shade(wood, 0.5), False))
    rows = (0.1, 0.72, 1.34)
    mid = (b0 + b1) / 2 + 0.1

    def spot(share: float, z: float) -> Point3:
        return f.p(a0 + (a1 - a0) * share, mid, z)

    # the bottom row: a plaque and a star
    plaque = spot(0.3, rows[0])
    shapes.append(_profile(plaque, [(-0.09, 0.0), (0.09, 0.0), (0.09, 0.2), (0.0, 0.26), (-0.09, 0.2)], mix(wood, "#3A2A1A", 0.35)))
    shapes.append(_profile(plaque, [(-0.05, 0.08), (0.05, 0.08), (0.05, 0.15), (-0.05, 0.15)], gold, False))
    star = spot(0.72, rows[0])
    shapes.append(_profile(star, [(-0.06, 0.0), (0.06, 0.0), (0.05, 0.05), (-0.05, 0.05)], "#3A2A1A"))
    shapes.append(_profile(star, [(-0.012, 0.05), (0.012, 0.05), (0.012, 0.15), (-0.012, 0.15)], shade(gold, 0.12)))
    points = [(0.09 * (1.0 if k % 2 == 0 else 0.42) * math.sin(math.pi * k / 5), 0.23 + 0.09 * (1.0 if k % 2 == 0 else 0.42) * math.cos(math.pi * k / 5))
              for k in range(10)]
    shapes.append(_profile(star, points, gold))
    # the middle row: a silver and a bronze cup round a medal hung from the shelf above
    shapes += _trophy(spot(0.18, rows[1]), 0.85, "#C9CED6")
    shapes += _trophy(spot(0.82, rows[1]), 0.85, "#C8814A")
    hook = spot(0.5, rows[2] - 0.08)
    shapes.append(_profile(hook, [(-0.06, 0.0), (-0.02, 0.0), (0.0, -0.17), (-0.03, -0.17)], "#E2574C"))
    shapes.append(_profile(hook, [(0.02, 0.0), (0.06, 0.0), (0.03, -0.17), (0.0, -0.17)], "#4C8DD6"))
    shapes.append(_round(_screen(hook, 0.0, -0.21), 0.055, gold))
    shapes.append(_round(_screen(hook, 0.0, -0.21), 0.03, mix(gold, SHINE, 0.35), False))
    # the top row: a big gold cup between two statuettes
    shapes += _trophy(spot(0.5, rows[2]), 1.1, gold)
    for share in (0.17, 0.83):
        foot = spot(share, rows[2])
        shapes.append(_profile(foot, [(-0.06, 0.0), (0.06, 0.0), (0.05, 0.05), (-0.05, 0.05)], "#3A2A1A"))
        shapes.append(_profile(foot, [(-0.035, 0.05), (0.035, 0.05), (0.03, 0.16), (0.05, 0.2), (0.04, 0.22), (0.0, 0.18), (-0.04, 0.22),
                                      (-0.05, 0.2), (-0.03, 0.16)], gold))   # a figure, arms up
        shapes.append(_round(_screen(foot, 0.0, 0.215), 0.025, gold))
    for z in rows:   # the shelves' front edges
        shapes.append(_rect(f, a0 + 0.07, a1 - 0.07, b1, z - 0.06, z, f.front(wood)))
    return shapes + f.box(a0 - 0.03, b0 - 0.02, top, a1 + 0.03, b1 + 0.04, top + 0.08, mix(wood, SHINE, 0.08))


#: The drawings of this module's kinds (each by its frame, look and state), and those with
#: moving parts the stage draws while they work (:func:`motion`).
DRAWINGS: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {
    "vegetable_patch": _vegetable_patch, "wheelbarrow": _wheelbarrow, "hay_bale": _hay_bale, "school_desk": _school_desk,
    "desk_with_pc": _desk_with_pc, "water_cooler": _water_cooler, "printer": _printer, "globe": _globe, "trophy_shelf": _trophy_shelf,
}
MOVING = frozenset({"desk_with_pc", "water_cooler", "printer", "globe"})


def motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """The moving parts of a working computer (a line being typed, a blinking cursor), water
    cooler (bubbles rising), printer (a sheet sliding out) or globe (its land turning) at ``now``."""
    kind = f.item.kind
    if kind == "desk_with_pc":
        share = (now % TYPE_SECONDS) / TYPE_SECONDS
        blink = (now % BLINK_SECONDS) < BLINK_SECONDS / 2
        return [Motion(p.points, p.fill, 1.0, False, True) for p in _typed(f, min(1.0, share * 1.25), blink)]
    if kind == "water_cooler":
        return _cooler_bubbles(f, look, now)
    if kind == "printer":
        return _sheet_motion(f, now)
    if kind == "globe":
        return _land(f, 2 * math.pi * now / GLOBE_SECONDS) + _globe_shine(f, look)
    return []


__all__ = ["DRAWINGS", "MOVING", "motion"]
