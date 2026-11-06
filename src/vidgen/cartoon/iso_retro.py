"""A retro-future kit of iso objects (DESIGN.md §107): the 1950s-60s "world of tomorrow" — a
googie building with a boomerang roof and a starburst sign, a round tower with a saucer deck, a
starburst sign, a ray-gun street lamp, an atomic sculpture, a monorail's beam on pylons, a
mainframe of tape reels and blinking bulbs, a sunburst wall clock, a TV console, a kidney desk
with a terminal, a clipped hedge and a planter; and a car's ``rocket`` kind (tail fins, a bubble
canopy). No manim.

Drawn like :mod:`vidgen.cartoon.iso_objects`' objects (its frame, shading and helpers), which
looks each kind of this module up in :data:`DRAWINGS` and its moving parts in :func:`motion`.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Callable

from vidgen.cartoon.iso_drawing import Line, Poly, Shape, Upright, mix, shade
from vidgen.cartoon.iso_objects import (
    CASING,
    CLOCK_HEIGHT,
    GLASS,
    LIT_CORE,
    LIT_GLASS,
    SHINE,
    Motion,
    ObjectLook,
    _arc,
    _face_circle,
    _flat_circle,
    _Frame,
    _profile,
    _round,
    _screen,
    clock_hands,
    light_pool,
)
from vidgen.cartoon.iso_seasons import _band, _middle, _star
from vidgen.cartoon.iso_city import window_color, window_lit
from vidgen.cartoon.iso_shop import _rect
from vidgen.cartoon.iso_town import TAIL, TYRE, _side_rect
from vidgen.world.iso import ObjectState
from vidgen.world.iso_view import Point3

#: The kit's palette: chrome, cream, a dark glass, turquoise, coral, mustard and mint.
CHROME = "#D5DEE6"
CREAM = "#FFF4DE"
DARK_GLASS = "#2E4057"
TURQUOISE = "#3FC1B5"
CORAL = "#FF7F6B"
MUSTARD = "#F2B33D"
MINT = "#A8E6CF"
#: A lit neon's colour over its tube (its core), and a terminal's green.
NEON_CORE = "#FFFFFF"
TERMINAL = "#7CFFB2"
#: Seconds of a turn of a tape reel, of a bulb's blink, of an electron's orbit and of a wave
#: crossing a screen.
REEL_SECONDS = 2.6
BLINK_SECONDS = 1.3
ORBIT_SECONDS = 2.2
WAVE_SECONDS = 1.6
#: A sunburst clock's middle (tile units over its wall's base) and its rays' reach.
SUNBURST_HEIGHT = CLOCK_HEIGHT + 0.1
SUNBURST_RADIUS = 0.5
#: A bulb panel's rows and columns, and its bulbs' colours.
BULB_ROWS, BULB_COLUMNS = 3, 5
BULBS = ("#FF5A5A", "#FFC23D", "#7CFF8A", "#5FD8FF")


def _unit(*keys: object) -> float:
    """A seeded number 0..1 for ``keys`` (the same in every render)."""
    return zlib.crc32(":".join(str(k) for k in keys).encode()) % 10007 / 10007


def _arc_band(x: float, y: float, z0: float, z1: float, r: float, t0: float, t1: float, fill: str, *, ink: bool = False,
              glow: bool = False, steps: int = 6) -> Poly:
    """A piece of an upright cylinder's face (radius ``r`` round (``x``, ``y``)) from angle ``t0``
    to ``t1`` (radians; the side to the viewer is -pi/4 .. 3pi/4) and height ``z0`` to ``z1``: a
    window, a fin, a band."""
    low = [(x + r * math.cos(t0 + (t1 - t0) * k / steps), y + r * math.sin(t0 + (t1 - t0) * k / steps), z0) for k in range(steps + 1)]
    high = [(x + r * math.cos(t1 - (t1 - t0) * k / steps), y + r * math.sin(t1 - (t1 - t0) * k / steps), z1) for k in range(steps + 1)]
    return Poly(tuple(low + high), fill, ink, glow)


def _lit_face(on: bool, color: str, shaded: float) -> str:
    """A glass's fill: lit warm while ``on``, else ``color`` in its face's shade."""
    return LIT_GLASS if on else shade(color, shaded)


def _starburst(centre: Point3, radius: float, fill: str, *, glow: bool = False, points: int = 12) -> list[Shape]:
    """A starburst facing the viewer: long and short rays round a small disc, a dot at each long
    ray's tip."""
    rays = []
    for k in range(points * 2):
        t = math.pi * k / points
        r = radius if k % 2 == 0 else radius * 0.38
        rays.append(_screen(centre, r * math.sin(t), r * math.cos(t)))
    shapes: list[Shape] = [Poly(tuple(rays), fill, True, glow), _round(centre, radius * 0.3, mix(fill, SHINE, 0.45), True, glow, 14)]
    for k in range(0, points * 2, 4):
        t = math.pi * k / points
        shapes.append(_round(_screen(centre, radius * 1.08 * math.sin(t), radius * 1.08 * math.cos(t)), radius * 0.07, mix(fill, SHINE, 0.3), False, glow, 8))
    return shapes


# ----- buildings: a googie building, a retro tower --------------------------------------------------------------


def _roof_z(a: float, b: float, w: float, d: float) -> float:
    """The googie building's roof over (``a``, ``b``) of its frame: rising from its back left to
    a high, swept front right corner."""
    s = b / d
    return 2.25 + 0.35 * a / w + 0.95 * math.copysign(abs(s) ** 1.3, s)


def _googie_building(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A googie diner or shop (``color`` its walls, ``detail`` its roof and trims): a glass shop
    front with a door, a side wall of tall slot windows, glass up to a roof that sweeps up to the
    front right like a boomerang on a V of pylons, and a mast over its back carrying a sign board
    and a starburst; on, its glass and sign glow and warm light pools in front."""
    w, d = f.width, f.depth
    on = state.on
    a0, a1, b0, b1 = 0.2, w - 0.25, 0.3, d - 0.2
    wall = 2.1
    trim = look.detail
    shapes: list[Shape] = light_pool(f.p(w * 0.45, d + 0.55, 0.01), 1.5, 0.8) if on else []
    # the mast behind the roof: its post, then (after the roof) the sign and the star
    mast_a, mast_b = a0 + 0.55, b0 + 0.35
    shapes += f.box(mast_a - 0.08, mast_b - 0.08, wall, mast_a + 0.08, mast_b + 0.08, 4.25, trim)
    shapes += f.box(a0, b0, 0.0, a1, b1, wall, look.main)
    shapes.append(_rect(f, a0, a1, b1 + 0.002, 0.0, 0.22, shade(trim, 0.15), False))   # a coloured plinth
    shapes.append(_side_rect(f, a1 + 0.002, b0, b1, 0.0, 0.22, shade(trim, 0.3), False))
    glass = f.front(DARK_GLASS)
    shapes.append(_rect(f, a0 + 0.12, a1 - 0.12, b1 + 0.003, 0.32, 1.85, LIT_GLASS if on else glass, True, on))
    if on:
        shapes.append(_rect(f, a0 + 0.5, a1 - 0.5, b1 + 0.004, 0.6, 1.5, LIT_CORE, False, True))
    for k in range(1, 5):   # mullions
        a = a0 + 0.12 + (a1 - a0 - 0.24) * k / 5
        shapes.append(Line((f.p(a, b1 + 0.005, 0.32), f.p(a, b1 + 0.005, 1.85)), CHROME, 1.3))
    door = a1 - 0.95
    shapes.append(_rect(f, door, door + 0.5, b1 + 0.006, 0.22, 1.55, mix(trim, SHINE, 0.2)))
    shapes.append(_rect(f, door + 0.08, door + 0.42, b1 + 0.007, 0.5, 1.45, LIT_CORE if on else mix(DARK_GLASS, SHINE, 0.2), False, on))
    for k in range(3):   # tall slot windows on the side wall
        b = b0 + 0.35 + (b1 - b0 - 0.7) * k / 2
        shapes.append(_side_rect(f, a1 + 0.004, b - 0.13, b + 0.13, 0.45, 1.85, LIT_GLASS if on else f.side(DARK_GLASS), True, on))
    # clerestory glass between the walls and the swept roof
    front = [(a, _roof_z(a, b1, w, d)) for a in (a0, (a0 + a1) / 2, a1)]
    shapes.append(f.poly([(a0, b1, wall), (a1, b1, wall), *[(a, b1, z - 0.06) for a, z in reversed(front)]], _lit_face(on, MINT, 0.3), True, on))
    side = [(b, _roof_z(a1, b, w, d)) for b in (b1, (b0 + b1) / 2, b0)]
    shapes.append(f.poly([(a1, b1, wall), (a1, b0, wall), *[(a1, b, z - 0.06) for b, z in reversed(side)]], _lit_face(on, MINT, 0.42), True, on))
    shapes.append(_rect(f, a0, a1, b1 + 0.004, wall - 0.05, wall + 0.05, CHROME, False))
    # the roof: its fascia, then its top, overhanging
    o = 0.32
    corners = [(a0 - o, b0 - o), (a1 + o * 1.6, b0 - o), (a1 + o * 1.6, b1 + o * 1.5), (a0 - o, b1 + o * 1.2)]
    top = [(a, b, _roof_z(a, b, w, d)) for a, b in corners]
    thick = 0.16
    shapes.append(f.poly([top[3], top[2], (top[2][0], top[2][1], top[2][2] - thick), (top[3][0], top[3][1], top[3][2] - thick)], CREAM))
    shapes.append(f.poly([top[2], top[1], (top[1][0], top[1][1], top[1][2] - thick), (top[2][0], top[2][1], top[2][2] - thick)], shade(CREAM, 0.15)))
    shapes.append(f.poly(top, mix(trim, SHINE, 0.12)))
    shapes.append(f.poly([top[3], top[2], (top[2][0] - 0.1, top[2][1] - 0.1, top[2][2]), (top[3][0] + 0.1, top[3][1] - 0.1, top[3][2])],
                         mix(trim, SHINE, 0.35), False))
    # the V of pylons holding the swept corner
    tip = (a1 + o * 1.3, b1 + o * 1.2)
    for foot in ((a1 + 0.3, b1 + 0.3), (a1 + 0.3, b1 - 0.75)):
        shapes.append(Poly((f.p(foot[0] - 0.05, foot[1], 0.0), f.p(foot[0] + 0.05, foot[1], 0.0), f.p(tip[0] + 0.04, tip[1], _roof_z(*tip, w, d) - thick),
                            f.p(tip[0] - 0.06, tip[1], _roof_z(*tip, w, d) - thick)), shade(trim, 0.2)))
    # the sign board and the starburst on the mast
    board = f.p(mast_a, mast_b, 3.35)
    outline = [(-0.62, -0.22), (0.5, -0.32), (0.72, 0.02), (0.55, 0.3), (-0.5, 0.26)]
    shapes.append(_profile(board, [(du * 1.06, dv * 1.12) for du, dv in outline], mix(CORAL, SHINE, 0.1) if on else CORAL, True, on))
    shapes.append(_profile(board, outline, CREAM))
    neon = TURQUOISE
    for k, (u0, u1) in enumerate(((-0.42, 0.38), (-0.32, 0.22))):
        dv = 0.08 - 0.16 * k
        shapes.append(_profile(board, [(u0, dv - 0.035), (u1, dv - 0.035), (u1, dv + 0.035), (u0, dv + 0.035)],
                               mix(neon, NEON_CORE, 0.35) if on else shade(neon, 0.15), False, on))
    shapes += _starburst(f.p(mast_a, mast_b, 4.45), 0.38, mix(MUSTARD, SHINE, 0.25) if on else MUSTARD, glow=on)
    return shapes


#: A retro tower: its shaft's and deck's radii (tile units), its floors' spacing and windows.
SHAFT = 0.72
DECK = 1.42
FLOOR_STEP = 0.55
WINDOW_SLICES = 8


def _retro_tower(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A round streamlined tower (``color``) on a podium: ribbon windows round each floor (a
    seeded share lit while on, warm or cool), fins up its face and a flying-saucer deck near the
    top (``detail`` its rim, with a ring of portholes), a cupola, a spire and a glowing atom ball."""
    item = f.item
    h = item.height
    x, y, _ = _middle(f)
    z = f.base
    on = state.on
    trim = look.detail
    deck = max(1.4, h - 2.55)
    shapes: list[Shape] = []
    shapes += _band(x, y, z, z + 0.45, 0.98, 0.98, mix(trim, CREAM, 0.55))
    shapes.append(Poly(_flat_circle((x, y, z + 0.45), 0.98, 28), mix(trim, CREAM, 0.7)))
    shapes += _band(x, y, z + 0.45, z + deck, SHAFT, SHAFT, look.main)
    span = (math.pi - 0.16) / WINDOW_SLICES
    row, level = 0, 0.8
    while level + 0.27 <= deck - 0.2:
        for k in range(WINDOW_SLICES):
            t0 = -math.pi / 4 + 0.08 + k * span
            lit = on and window_lit(item.name, "round", row, k)
            dark = shade(DARK_GLASS, 0.2 if t0 < math.pi / 6 else 0.05)
            shapes.append(_arc_band(x, y, z + level, z + level + 0.27, SHAFT + 0.004, t0 + 0.02, t0 + span - 0.02,
                                    window_color(item.name, "round", row, k) if lit else dark, glow=lit, steps=3))
        row, level = row + 1, level + FLOOR_STEP
    for t in (-math.pi / 8, math.pi / 4, 5 * math.pi / 8):   # fins
        shapes.append(_arc_band(x, y, z + 0.45, z + deck - 0.05, SHAFT + 0.03, t - 0.05, t + 0.05, mix(trim, SHINE, 0.15), ink=True, steps=2))
    d = z + deck
    shapes += _band(x, y, d, d + 0.28, SHAFT, DECK, shade(look.main, 0.12))
    shapes += _band(x, y, d + 0.28, d + 0.5, DECK, DECK, trim)
    for k in range(10):   # portholes round the rim
        t = -math.pi / 4 + 0.15 + k * (math.pi - 0.3) / 9
        lit = on and k % 3 != 1
        shapes.append(_arc_band(x, y, d + 0.33, d + 0.45, DECK + 0.004, t - 0.06, t + 0.06, LIT_GLASS if lit else shade(DARK_GLASS, 0.1),
                                glow=lit, steps=2))
    shapes.append(Poly(_flat_circle((x, y, d + 0.5), DECK, 32), mix(look.main, SHINE, 0.25)))
    shapes += _band(x, y, d + 0.5, d + 0.82, DECK * 0.8, 0.5, mix(look.main, SHINE, 0.12))
    shapes.append(Poly(_flat_circle((x, y, d + 0.82), 0.5, 20), mix(look.main, SHINE, 0.3)))
    shapes += _band(x, y, d + 0.82, d + 1.35, 0.32, 0.26, trim)
    shapes.append(Poly(_flat_circle((x, y, d + 1.35), 0.26, 16), mix(trim, SHINE, 0.2)))
    shapes.append(Upright(x, y, d + 1.35, z + h - 0.2, 0.04, CHROME))
    shapes.append(_round((x, y, z + h - 0.12), 0.11, mix(trim, SHINE, 0.4) if on else trim, True, on, 14))
    return shapes


# ----- the street: a starburst sign, a ray lamp, an atomic sculpture, a monorail --------------------------------


def _starburst_sign(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A roadside sign on a chrome pole: a boomerang board (``color``) with two neon lines of
    lettering in ``detail``, and a starburst on top; on, the lettering, the bulbs round the board
    and the star glow and a little light pools under it."""
    x, y, z = _middle(f)
    on = state.on
    shapes: list[Shape] = light_pool((x, y, z + 0.01), 0.8, 0.6) if on else []
    shapes.append(Upright(x, y, z, z + 2.85, 0.05, CHROME))
    board = (x, y, z + 2.05)
    outline = [(-0.55, -0.28), (0.42, -0.2), (0.6, 0.08), (0.36, 0.3), (-0.46, 0.18)]
    shapes.append(_profile(board, [(du * 1.1, dv * 1.18) for du, dv in outline], mix(look.detail, SHINE, 0.15) if on else look.detail, True, on))
    shapes.append(_profile(board, outline, look.main))
    for k, (u0, u1) in enumerate(((-0.36, 0.34), (-0.26, 0.2))):
        dv = 0.06 - 0.15 * k
        shapes.append(_profile(board, [(u0, dv - 0.03), (u1, dv - 0.03), (u1, dv + 0.03), (u0, dv + 0.03)],
                               mix(look.detail, NEON_CORE, 0.4) if on else shade(look.detail, 0.2), False, on))
    for k in range(7):
        s = k / 6
        du, dv = -0.5 + s * 1.0, -0.28 + 0.08 * s
        shapes.append(_round(_screen(board, du, dv - 0.02), 0.025, LIT_CORE if on else CREAM, False, on, 8))
    shapes += _starburst((x, y, z + 2.95), 0.32, mix(MUSTARD, SHINE, 0.25) if on else MUSTARD, glow=on)
    return shapes


def _ray_lamp(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A ray-gun street lamp: three fins round its foot, a tapering pole (``color``) with chrome
    rings, a globe (``detail`` its glass off) in a tilted ring like a planet's and a spike on
    top; on, the globe glows and a warm pool lies under it (it lights who stands near)."""
    x, y, z = _middle(f)
    on = state.on
    foot = (x, y, z)
    shapes: list[Shape] = light_pool((x, y, z + 0.01), 1.15, 0.95) if on else []
    for side in (-1.0, 1.0):   # the two fins seen
        shapes.append(_profile(foot, [(side * 0.04, 0.0), (side * 0.26, 0.0), (side * 0.05, 0.6)], shade(look.main, 0.1)))
    shapes.append(_profile(foot, [(-0.07, 0.0), (0.07, 0.0), (0.035, 2.55), (-0.035, 2.55)], look.main))
    shapes.append(_profile(foot, [(0.0, 0.0), (0.07, 0.0), (0.035, 2.55), (0.0, 2.55)], shade(look.main, 0.18), False))
    for dv in (0.75, 1.6):
        shapes.append(_profile(foot, [(-0.075, dv), (0.075, dv), (0.072, dv + 0.06), (-0.072, dv + 0.06)], CHROME))
    shapes.append(_profile(foot, [(-0.12, 0.0), (0.12, 0.0), (0.0, 0.07)], CHROME))
    head = _screen(foot, 0.0, 2.85)
    ring = [(0.48 * math.cos(t), 0.14 * math.sin(t) + 0.05 * math.cos(t)) for t in [math.pi * k / 14 for k in range(15)]]
    shapes.append(Line(tuple(_screen(head, du, dv) for du, dv in ring), CHROME, 2.4))   # the ring's far half
    glass = mix(look.detail, SHINE, 0.4) if on else look.detail
    shapes.append(_round(head, 0.27, glass, True, on, 20))
    shapes.append(_round(_screen(head, -0.08, 0.08), 0.08, LIT_CORE if on else mix(look.detail, SHINE, 0.55), False, on, 10))
    near = [(0.48 * math.cos(t), 0.14 * math.sin(t) + 0.05 * math.cos(t)) for t in [math.pi + math.pi * k / 14 for k in range(15)]]
    shapes.append(Line(tuple(_screen(head, du, dv) for du, dv in near), CHROME, 2.4))
    shapes.append(_profile(head, [(-0.035, 0.25), (0.035, 0.25), (0.0, 0.5)], CHROME))
    return shapes


#: An atomic sculpture's nucleus (tile units over its base), its orbits' half axes (tile widths
#: on the picture) and turns (radians).
NUCLEUS = 1.75
ORBIT = (0.52, 0.17)
ORBIT_TURNS = (0.0, math.pi / 3, 2 * math.pi / 3)


def _orbit_point(centre: Point3, turn: float, t: float) -> Point3:
    du, dv = ORBIT[0] * math.cos(t), ORBIT[1] * math.sin(t)
    return _screen(centre, du * math.cos(turn) - dv * math.sin(turn), du * math.sin(turn) + dv * math.cos(turn))


def _atomic_sculpture(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A plaza's atom on a terrazzo plinth (``color``): a slim post, a nucleus (``detail``) and
    three crossed chrome orbits with an electron on each; on, the nucleus glows and the stage
    moves the electrons round their orbits (in the picture while still)."""
    x, y, z = _middle(f)
    on = state.on
    shapes: list[Shape] = f.box(0.22, 0.22, 0.0, f.width - 0.22, f.depth - 0.22, 0.55, look.main)
    shapes += _terrazzo(f, 0.22, f.width - 0.22, f.depth - 0.22, 0.05, 0.5, look.main)
    shapes.append(Upright(x, y, z + 0.55, z + NUCLEUS - 0.1, 0.045, CHROME))
    centre = (x, y, z + NUCLEUS)
    for turn in ORBIT_TURNS:   # the orbits' far halves behind the nucleus
        shapes.append(Line(tuple(_orbit_point(centre, turn, math.pi * k / 16) for k in range(17)), CHROME, 2.0))
    shapes.append(_round(centre, 0.15, mix(look.detail, SHINE, 0.35) if on else look.detail, True, on, 18))
    shapes.append(_round(_screen(centre, -0.05, 0.05), 0.045, mix(look.detail, SHINE, 0.7), False, on, 8))
    for turn in ORBIT_TURNS:
        shapes.append(Line(tuple(_orbit_point(centre, turn, math.pi + math.pi * k / 16) for k in range(17)), CHROME, 2.0))
    if not (on and look.moving):
        for k, turn in enumerate(ORBIT_TURNS):
            shapes.append(_round(_orbit_point(centre, turn, 1.1 + 2.1 * k), 0.05, mix(look.detail, SHINE, 0.5), True, False, 10))
    return shapes


def _electrons(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A working atomic sculpture's electrons at ``now``: one round each orbit, glowing."""
    x, y, z = _middle(f)
    centre = (x, y, z + NUCLEUS)
    parts = []
    for k, turn in enumerate(ORBIT_TURNS):
        t = 2 * math.pi * (now / ORBIT_SECONDS + k / 3) * (1 if k % 2 == 0 else -1)
        point = _orbit_point(centre, turn, t)
        parts.append(Motion(_round(point, 0.09, look.detail, steps=10).points, mix(look.detail, SHINE, 0.3), 0.35, False, True))
        parts.append(Motion(_round(point, 0.05, SHINE, steps=10).points, mix(look.detail, SHINE, 0.75), 1.0, True, True))
    return parts


def _monorail(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A monorail's beam (``color``, a stripe of ``detail`` along it) on T pylons, across the
    whole footprint (``size`` makes it longer): a traffic lane with ``shape: monorail`` at its
    height glides a train along it."""
    w, d = f.width, f.depth
    m = d / 2
    shapes: list[Shape] = []
    count = max(2, round(w / 2) + 1)
    for k in range(count):
        a = 0.5 + (w - 1.0) * k / (count - 1)
        shapes += f.box(a - 0.11, m - 0.11, 0.0, a + 0.11, m + 0.11, 2.2, mix(look.main, CREAM, 0.2))
        shapes += f.box(a - 0.2, m - 0.3, 2.12, a + 0.2, m + 0.3, 2.32, shade(look.main, 0.05))
    shapes += f.box(0.0, m - 0.22, 2.32, w, m + 0.22, 2.72, look.main)
    shapes.append(f.poly([(0.0, m + 0.221, 2.45), (w, m + 0.221, 2.45), (w, m + 0.221, 2.55), (0.0, m + 0.221, 2.55)], look.detail, False))
    return shapes


# ----- indoors: a tube computer, a sunburst clock, a TV console, a retro desk -------------------------------


def _reel_centres(f: _Frame) -> list[tuple[float, float]]:
    return [(0.48, 1.55), (1.08, 1.55)]


def _tube_computer(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A mainframe of the atomic age (``color`` its cabinet, ``detail`` its trims): two tape
    reels behind a window, a panel of bulbs, dials and a chart slot, vacuum tubes in glass on top;
    on, the bulbs and the tubes' filaments glow (the stage turns the reels and blinks the bulbs)."""
    w = f.width
    on = state.on
    a0, a1, b0, b1 = 0.08, w - 0.08, 0.22, 0.9
    shapes: list[Shape] = f.box(a0, b0, 0.0, a1, b1, 2.12, look.main)
    face = b1 + 0.002
    shapes.append(_rect(f, a0, a1, face, 0.0, 0.12, shade(look.main, 0.4), False))
    shapes.append(_rect(f, a0, a1, face, 2.0, 2.06, look.detail, False))
    shapes.append(_rect(f, 0.2, 1.36, face, 1.18, 1.92, CASING))
    for a, zz in _reel_centres(f):
        shapes.append(f.poly(_face_circle(f, a, face + 0.001, zz, 0.27, 24), shade(TYRE, 0.1)))
        shapes.append(f.poly(_face_circle(f, a, face + 0.002, zz, 0.21, 24), "#6B4A2E", False))
        shapes.append(f.poly(_face_circle(f, a, face + 0.003, zz, 0.08, 14), CHROME))
        if not (on and look.moving):
            for k in range(3):
                t = 2 * math.pi * k / 3 + 0.4
                shapes.append(Line((f.p(a + 0.08 * math.cos(t), face + 0.004, zz + 0.08 * math.sin(t)),
                                    f.p(a + 0.25 * math.cos(t), face + 0.004, zz + 0.25 * math.sin(t))), CHROME, 1.4))
    shapes += _bulbs(f, on, None if look.moving else 0.0)
    shapes.append(_rect(f, 1.45, a1 - 0.08, face, 1.2, 1.9, mix(look.main, SHINE, 0.25)))
    for k in range(3):   # dials
        zz = 1.75 - 0.22 * k
        shapes.append(f.poly(_face_circle(f, 1.62, face + 0.003, zz, 0.07, 14), CREAM))
        shapes.append(Line((f.p(1.62, face + 0.004, zz), f.p(1.66, face + 0.004, zz + 0.05)), CASING, 1.0))
    shapes.append(_rect(f, 1.45, a1 - 0.08, face, 0.35, 0.95, shade(look.main, 0.08)))   # the chart slot
    shapes.append(_rect(f, 1.5, a1 - 0.13, face + 0.001, 0.55, 0.85, SHINE, False))
    shapes.append(Line(tuple(f.p(1.5 + 0.03 * k, face + 0.002, 0.7 + 0.08 * math.sin(k * 1.3)) for k in range(int((a1 - 1.63) / 0.03))), CORAL, 1.0))
    for k in range(5):   # the vacuum tubes on top
        a = a0 + 0.25 + (a1 - a0 - 0.5) * k / 4
        base = f.p(a, (b0 + b1) / 2, 2.12)
        shapes.append(_profile(base, [(-0.06, 0.0), (0.06, 0.0), (0.06, 0.04), (-0.06, 0.04)], CASING))
        shapes.append(_profile(base, [*_arc(0.0, 0.2, 0.05, 0.05, 0.0, math.pi, 8), (-0.05, 0.04), (0.05, 0.04)], mix(GLASS, SHINE, 0.2)))
        shapes.append(_profile(base, [(-0.015, 0.06), (0.015, 0.06), (0.015, 0.18), (-0.015, 0.18)], "#FF9A3D" if on else shade(CHROME, 0.3), False, on))
    return shapes


def _bulbs(f: _Frame, on: bool, now: float | None) -> list[Shape]:
    """The tube computer's panel of bulbs (``now``: lit as they blink then; ``None``: none lit)."""
    face = f.depth - 0.1 + 0.003
    shapes: list[Shape] = [_rect(f, 0.2, 1.36, face, 0.35, 1.0, shade(CASING, -0.2))]
    for r in range(BULB_ROWS):
        for c in range(BULB_COLUMNS):
            a, zz = 0.32 + c * 0.23, 0.48 + r * 0.2
            color = BULBS[(r + c) % len(BULBS)]
            lit = on and now is not None and _bulb_lit(r, c, now)
            shapes.append(f.poly(_face_circle(f, a, face + 0.001, zz, 0.055, 10), mix(color, SHINE, 0.3) if lit else shade(color, 0.45), True, lit))
    return shapes


def _bulb_lit(row: int, column: int, now: float) -> bool:
    phase = _unit("bulb", row, column)
    return (now / BLINK_SECONDS * (0.7 + 0.6 * phase) + phase) % 1.0 < 0.55


def _tube_motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """A working tube computer at ``now``: its reels' spokes turning (the two reels opposite
    ways), its bulbs blinking."""
    face = f.depth - 0.1 + 0.006
    parts = []
    for k, (a, zz) in enumerate(_reel_centres(f)):
        turn = 2 * math.pi * now / REEL_SECONDS * (1 if k == 0 else -0.8)
        for s in range(3):
            t = turn + 2 * math.pi * s / 3
            c, sn, n = math.cos(t), math.sin(t), (-math.sin(t), math.cos(t))
            spoke = [(a + 0.08 * c + 0.02 * n[0], zz + 0.08 * sn + 0.02 * n[1]), (a + 0.25 * c + 0.02 * n[0], zz + 0.25 * sn + 0.02 * n[1]),
                     (a + 0.25 * c - 0.02 * n[0], zz + 0.25 * sn - 0.02 * n[1]), (a + 0.08 * c - 0.02 * n[0], zz + 0.08 * sn - 0.02 * n[1])]
            parts.append(Motion(tuple(f.p(u, face, v) for u, v in spoke), CHROME, 1.0, False))
    for r in range(BULB_ROWS):
        for c in range(BULB_COLUMNS):
            color = BULBS[(r + c) % len(BULBS)]
            points = tuple(f.p(*q) for q in _face_circle(f, 0.32 + c * 0.23, face, 0.48 + r * 0.2, 0.05, 10))
            parts.append(Motion(points, mix(color, SHINE, 0.35), 1.0 if _bulb_lit(r, c, now) else 0.0, False, True))
    return parts


def _sunburst_clock(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A sunburst clock on the face of the wall it hangs on: rays of ``detail`` (gold) round a
    cream face (``color`` its rim) with its hands at its ``time``."""
    face_b = f.depth + 0.02
    cx = f.width / 2
    across = -1.0 if f.swap else 1.0

    def at(angle: float, r: float, lift: float = 0.0) -> Point3:
        t = math.radians(angle)
        return f.p(cx + across * r * math.sin(t), face_b + lift, SUNBURST_HEIGHT + r * math.cos(t))

    def dot(angle: float, reach: float, radius: float) -> Poly:
        t = math.radians(angle)
        u, v = across * reach * math.sin(t), reach * math.cos(t)
        return f.poly([(cx + u + across * radius * math.cos(2 * math.pi * s / 8), face_b + 0.001, SUNBURST_HEIGHT + v + radius * math.sin(2 * math.pi * s / 8))
                       for s in range(8)], mix(look.detail, SHINE, 0.2))

    shapes: list[Shape] = []
    for k in range(24):
        angle = k * 15.0
        reach = SUNBURST_RADIUS if k % 2 == 0 else SUNBURST_RADIUS * 0.72
        shapes.append(Poly((at(angle - 4.0, 0.2), at(angle, reach), at(angle + 4.0, 0.2)), look.detail if k % 2 == 0 else mix(look.detail, SHINE, 0.25)))
        if k % 4 == 0:
            shapes.append(dot(angle, reach + 0.035, 0.035))
    steps = [k * 360.0 / 24 for k in range(24)]
    shapes.append(Poly(tuple(at(t, 0.22, 0.002) for t in steps), look.main))
    shapes.append(Poly(tuple(at(t, 0.18, 0.003) for t in steps), CREAM, False))
    for k in range(4):
        shapes.append(Line((at(k * 90.0, 0.13, 0.004), at(k * 90.0, 0.165, 0.004)), CASING, 1.4))
    hour, minute = clock_hands(f.item.time)
    shapes.append(Line((at(0.0, 0.0, 0.005), at(hour, 0.1, 0.005)), CASING, 2.4))
    shapes.append(Line((at(0.0, 0.0, 0.006), at(minute, 0.15, 0.006)), CASING, 1.6))
    return shapes


def _tv_screen(f: _Frame) -> tuple[float, float, float, float, float]:
    return 0.2, 0.66, f.depth - 0.15 + 0.004, 0.55, 1.02


def _wave(f: _Frame, a0: float, a1: float, b: float, z: float, amp: float, phase: float, fill: str, glow: bool) -> Poly:
    """A wave across a face at ``b`` (from ``a0`` to ``a1`` round height ``z``) as a thin band."""
    steps = 18
    top = [(a0 + (a1 - a0) * k / steps, b, z + amp * math.sin(phase + 2.6 * math.pi * k / steps) + 0.014) for k in range(steps + 1)]
    low = [(a, bb, zz - 0.028) for a, bb, zz in reversed(top)]
    return f.poly(top + low, fill, False, glow)


def _tv_console(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A TV console on splayed legs (``color`` its cabinet): a round-cornered screen, two knobs, a
    speaker grille and rabbit-ear aerials; on, its screen glows in ``detail`` with an
    oscilloscope's wave or (``kind: face``) a robot face whose mouth is a wave (the stage moves
    them)."""
    w, d = f.width, f.depth
    on = state.on
    a0, a1, b0, b1 = 0.1, w - 0.1, 0.25, d - 0.15
    shapes: list[Shape] = []
    for a, b in ((a0 + 0.08, b0 + 0.08), (a1 - 0.08, b0 + 0.08), (a0 + 0.08, b1 - 0.06), (a1 - 0.08, b1 - 0.06)):
        out = (a - 0.06 if a < w / 2 else a + 0.06, b + 0.05 if b > d / 2 else b - 0.03)
        shapes.append(Line((f.p(a, b, 0.38), f.p(out[0], out[1], 0.0)), shade(look.main, 0.45), 2.4))
    shapes += f.box(a0, b0, 0.36, a1, b1, 1.12, look.main)
    s0, s1, face, z0, z1 = _tv_screen(f)
    r = 0.07

    def rounded(u0: float, u1: float, v0: float, v1: float, rr: float) -> list[tuple[float, float, float]]:
        pts = []
        for cu, cv, start in ((u1 - rr, v1 - rr, 0.0), (u0 + rr, v1 - rr, 90.0), (u0 + rr, v0 + rr, 180.0), (u1 - rr, v0 + rr, 270.0)):
            pts += [(cu + rr * math.cos(math.radians(start + 15 * k)), face, cv + rr * math.sin(math.radians(start + 15 * k))) for k in range(7)]
        return pts

    shapes.append(f.poly(rounded(s0 - 0.04, s1 + 0.04, z0 - 0.04, z1 + 0.04, r + 0.03), CHROME))
    screen = mix(look.detail, "#0B2A2A", 0.55) if on else "#3C4A48"
    shapes.append(f.poly(rounded(s0, s1, z0, z1, r), screen, True, on))
    shapes.append(f.poly(rounded(s0 + 0.03, s1 - 0.25, z1 - 0.12, z1 - 0.03, 0.03), mix(screen, SHINE, 0.25), False, on))
    if on and not look.moving:
        shapes += _tv_picture(f, look, 0.0)
    for zz in (0.95, 0.75):
        shapes.append(f.poly(_face_circle(f, 0.8, face, zz, 0.045, 12), CREAM))
    for k in range(4):
        zz = 0.45 + k * 0.05
        shapes.append(Line((f.p(0.73, face, zz), f.p(0.87, face, zz)), shade(look.main, 0.35), 0.8))
    top = f.p(w / 2, (b0 + b1) / 2, 1.12)
    shapes.append(_round(top, 0.05, CASING, True, False, 10))
    for side in (-1.0, 1.0):
        shapes.append(Line((top, _screen(top, side * 0.22, 0.32)), CHROME, 1.2))
        shapes.append(_round(_screen(top, side * 0.22, 0.32), 0.018, CHROME, False, False, 8))
    return shapes


def _tv_picture(f: _Frame, look: ObjectLook, now: float) -> list[Poly]:
    """What a lit TV console's screen shows at ``now``: a wave, or a face over a wave."""
    s0, s1, face, z0, z1 = _tv_screen(f)
    bright = mix(look.detail, SHINE, 0.45)
    phase = 2 * math.pi * now / WAVE_SECONDS
    lift = 0.002
    if "face" not in f.item.features:
        grid = [f.poly([(s0 + 0.06, face + lift, (z0 + z1) / 2 - 0.004), (s1 - 0.06, face + lift, (z0 + z1) / 2 - 0.004),
                        (s1 - 0.06, face + lift, (z0 + z1) / 2 + 0.004), (s0 + 0.06, face + lift, (z0 + z1) / 2 + 0.004)],
                       mix(look.detail, "#0B2A2A", 0.2), False, True)]
        return grid + [_wave(f, s0 + 0.05, s1 - 0.05, face + lift * 2, (z0 + z1) / 2, 0.12, phase, bright, True)]
    eyes = [f.poly(_face_circle(f, a, face + lift, z1 - 0.15, 0.055, 12), bright, False, True) for a in (s0 + 0.14, s1 - 0.14)]
    talk = 0.04 + 0.03 * math.sin(phase * 1.7)
    return eyes + [_wave(f, s0 + 0.08, s1 - 0.08, face + lift * 2, z0 + 0.13, talk, phase * 2, bright, True)]


def _tv_motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    return [Motion(p.points, p.fill, 1.0, False, True) for p in _tv_picture(f, look, now)]


def _retro_desk(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A kidney-shaped desk (``color`` its top) on hairpin legs, a drawer pedestal (``detail``)
    under its right end, a terminal with a round-cornered screen and a dial telephone on it; on,
    the terminal's screen glows green with lines of text (its top takes small things)."""
    w, d = f.width, f.depth
    on = state.on
    top_z = 0.8
    steps = 16
    front = [(0.12 + (w - 0.24) * k / steps, d - 0.12 - 0.16 * math.sin(math.pi * k / steps)) for k in range(steps + 1)]
    back = [(w - 0.12, 0.18), (0.12, 0.18)]
    shapes: list[Shape] = []
    for a, b in ((0.25, 0.3), (0.25, d - 0.25)):
        shapes.append(Line((f.p(a, b, top_z - 0.05), f.p(a - 0.05, b + 0.03, 0.0)), CASING, 1.8))
        shapes.append(Line((f.p(a + 0.08, b, top_z - 0.05), f.p(a + 0.03, b + 0.03, 0.0)), CASING, 1.8))
    shapes += f.box(w - 0.75, 0.25, 0.0, w - 0.15, d - 0.25, top_z - 0.06, look.detail)
    for zz in (0.25, 0.5):
        shapes.append(_rect(f, w - 0.7, w - 0.2, d - 0.25 + 0.002, zz, zz + 0.012, shade(look.detail, 0.4), False))
        shapes.append(_rect(f, w - 0.5, w - 0.4, d - 0.25 + 0.003, zz + 0.08, zz + 0.11, CHROME, False))
    edge = [(a, b, top_z) for a, b in front] + [(a, b, top_z - 0.07) for a, b in reversed(front)]
    shapes.append(f.poly(edge, shade(look.main, 0.15)))
    shapes.append(f.poly([(a, b, top_z) for a, b in front] + [(a, b, top_z) for a, b in back], look.main))
    # the terminal
    t0, t1, tb0, tb1 = 0.3, 0.85, 0.25, 0.62
    shapes += f.box(t0, tb0, top_z, t1, tb1, top_z + 0.48, CREAM)
    screen = mix(TERMINAL, "#0B2A1A", 0.6) if on else "#33403A"
    shapes.append(_rect(f, t0 + 0.07, t1 - 0.07, tb1 + 0.002, top_z + 0.12, top_z + 0.42, screen, True, on))
    if on:
        for k in range(3):
            zz = top_z + 0.36 - k * 0.08
            shapes.append(_rect(f, t0 + 0.11, t0 + 0.11 + (0.25 + 0.08 * (k % 2)), tb1 + 0.003, zz - 0.015, zz + 0.015, TERMINAL, False, True))
    shapes += f.box(t0 + 0.02, tb1, top_z, t1 - 0.02, tb1 + 0.18, top_z + 0.06, shade(CREAM, 0.1))   # its keys
    # a dial telephone
    phone = f.p(w - 0.5, d * 0.45, top_z)
    shapes.append(_profile(phone, [(-0.13, 0.0), (0.13, 0.0), (0.1, 0.12), (-0.1, 0.12)], CORAL))
    shapes.append(_profile(phone, [*_arc(0.0, 0.14, 0.15, 0.06, 0.0, math.pi, 8)], shade(CORAL, 0.15)))
    shapes.append(_round(_screen(phone, 0.0, 0.07), 0.04, CREAM, True, False, 10))
    return shapes


# ----- the garden: a hedge, a planter, terrazzo ---------------------------------------------------------------


def _terrazzo(f: _Frame, a0: float, a1: float, b: float, z0: float, z1: float, color: str) -> list[Shape]:
    """Terrazzo chips on a front face at ``b`` (``a0`` .. ``a1``, ``z0`` .. ``z1``), seeded by place."""
    chips = (CORAL, TURQUOISE, MUSTARD, shade(color, 0.35))
    shapes: list[Shape] = []
    count = max(3, int((a1 - a0) * (z1 - z0) * 26))
    for k in range(count):
        u, v = _unit(f.item.name, "chip", k), _unit(f.item.name, "chip", k, "v")
        a, zz = a0 + 0.04 + (a1 - a0 - 0.08) * u, z0 + 0.03 + (z1 - z0 - 0.06) * v
        shapes.append(f.poly(_face_circle(f, a, b + 0.002, zz, 0.018, 6), chips[k % len(chips)], False))
    return shapes


def _hedge(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A clipped box hedge (``color``) across its whole footprint, its top rounded off and its
    faces dotted with leaves (``size`` makes a long one)."""
    w, d = f.width, f.depth
    leaves = look.main
    shapes: list[Shape] = f.box(0.06, 0.1, 0.0, w - 0.06, d - 0.06, 0.78, shade(leaves, 0.04))
    shapes += f.box(0.12, 0.16, 0.78, w - 0.12, d - 0.12, 0.9, mix(leaves, SHINE, 0.12))
    for k in range(int(w * 7)):
        u, v = _unit(f.item.name, "leaf", k), _unit(f.item.name, "leaf", k, "v")
        a, zz = 0.12 + (w - 0.24) * u, 0.1 + 0.6 * v
        shapes.append(f.poly(_face_circle(f, a, d - 0.06 + 0.002, zz, 0.04, 6), mix(leaves, SHINE, 0.22), False))
    for k in range(int(d * 4)):
        u, v = _unit(f.item.name, "side", k), _unit(f.item.name, "side", k, "v")
        b, zz = 0.16 + (d - 0.3) * u, 0.1 + 0.6 * v
        shapes.append(f.poly([(w - 0.06 + 0.002, b + 0.04 * math.cos(2 * math.pi * s / 6), zz + 0.04 * math.sin(2 * math.pi * s / 6)) for s in range(6)],
                             shade(leaves, 0.2), False))
    return shapes


def _planter(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A raised terrazzo planter (``color``, a rim of ``detail``) across its footprint, with
    spiky leaves and tulips in each cell (``size`` makes a long one)."""
    w, d = f.width, f.depth
    a0, a1, b0, b1 = 0.08, w - 0.08, 0.14, d - 0.08
    shapes: list[Shape] = f.box(a0, b0, 0.0, a1, b1, 0.5, look.main)
    shapes += _terrazzo(f, a0, a1, b1, 0.06, 0.44, look.main)
    shapes += f.box(a0 - 0.03, b0 - 0.03, 0.5, a1 + 0.03, b1 + 0.03, 0.58, look.detail)
    shapes.append(f.poly([(a0 + 0.05, b0 + 0.05, 0.585), (a1 - 0.05, b0 + 0.05, 0.585), (a1 - 0.05, b1 - 0.05, 0.585), (a0 + 0.05, b1 - 0.05, 0.585)],
                         "#6B4A2E", False))
    tulips = (CORAL, MUSTARD, "#F7A8B8")
    for cell in range(max(1, w) * max(1, d)):
        ca, cb = (cell % max(1, w)) + 0.5, (cell // max(1, w)) + 0.5
        foot = f.p(ca, min(max(cb, b0 + 0.2), b1 - 0.2), 0.58)
        for k, (du, top) in enumerate(((-0.17, 0.42), (-0.08, 0.6), (0.0, 0.52), (0.09, 0.62), (0.18, 0.4))):
            shapes.append(_profile(foot, [(du - 0.035, 0.0), (du + 0.035, 0.0), (du * 1.5, top)], shade("#4FA36B", 0.08 * (k % 2))))
        for k, du in enumerate((-0.12, 0.05, 0.15)):
            head = _screen(foot, du, 0.5 + 0.07 * (k % 2))
            shapes.append(Line((_screen(foot, du * 0.8, 0.0), head), "#3E8E55", 1.2))
            shapes.append(_profile(head, [(-0.05, 0.0), (0.05, 0.0), (0.06, 0.07), (0.02, 0.05), (0.0, 0.09), (-0.02, 0.05), (-0.06, 0.07)],
                                   tulips[(cell + k) % len(tulips)]))
    return shapes


# ----- a rocket car --------------------------------------------------------------------------------------------


def rocket_car_shapes(f: _Frame, look: ObjectLook, state: ObjectState, *, reverse: bool = False, spin: float | None = None) -> list[Shape]:
    """A car's ``rocket`` kind (``color`` its body, ``detail`` its canopy): a long, low body with
    a pointed nose, a chrome stripe, a bubble canopy, tail fins and a jet ring at its tail; on,
    its headlight and the jet glow and its light pools ahead (also driven, :func:`car_shapes`)."""
    w = f.width
    body = look.main
    on = state.on

    def X(a: float) -> float:
        return w - a if reverse else a

    a0, a1, b0, b1 = 0.08, w - 0.08, 0.22, 0.82
    reach, size = (1.0, 0.75) if reverse else (0.45, 0.55)
    shapes: list[Shape] = light_pool(f.p(X(a1 + reach), (b0 + b1) / 2, 0.01), size, 0.9) if on else []
    face = b1 + 0.001
    # the far fin, the body, the near fin
    fin = [(X(0.12), 0.95), (X(0.5), 0.55), (X(0.12), 0.55)]
    shapes.append(f.poly([(a, b0 + 0.08, z) for a, z in fin], shade(look.detail if look.detail != body else CORAL, 0.2)))
    nose_a = X(a1)
    shapes += f.box(min(X(a0), X(a1 - 0.35)), b0, 0.2, max(X(a0), X(a1 - 0.35)), b1, 0.58, body)
    tip = [(X(a1 - 0.35), b1, 0.2), (nose_a, (b0 + b1) / 2 + 0.15, 0.32), (X(a1 - 0.35), b1, 0.58)]
    shapes.append(f.poly(tip, f.front(body)))
    if not reverse:
        shapes.append(f.poly([(X(a1 - 0.35), b1, 0.58), (nose_a, (b0 + b1) / 2 + 0.15, 0.32), (X(a1 - 0.35), b0, 0.58)], mix(body, SHINE, 0.1)))
    else:
        shapes.append(f.poly([(X(a1 - 0.35), b1, 0.58), (nose_a, (b0 + b1) / 2 + 0.15, 0.32), (X(a1 - 0.35), b0, 0.58)], f.side(body)))
    shapes.append(_rect(f, min(X(a0), X(a1 - 0.35)), max(X(a0), X(a1 - 0.35)), face, 0.38, 0.44, CHROME, False))
    # the bubble canopy
    dome = f.p(X(w * 0.45), (b0 + b1) / 2, 0.58)
    shapes.append(_profile(dome, _arc(0.0, 0.0, 0.42, 0.34, 0.0, math.pi, 14), mix(look.detail, SHINE, 0.25)))
    shapes.append(_profile(dome, _arc(-0.1, 0.1, 0.12, 0.12, 0.4, 2.2, 6), SHINE, False))
    shapes.append(f.poly([(a, face + 0.003, z) for a, z in fin], look.detail if look.detail != body else CORAL))
    tail_a = X(a0)
    ring = f.p(tail_a, (b0 + b1) / 2, 0.39)
    shapes.append(_round(ring, 0.13, CHROME, True, False, 14))
    shapes.append(_round(ring, 0.07, "#FF8A3D" if on else TYRE, False, on, 12))
    if not reverse:
        shapes.append(_side_rect(f, a1 - 0.33, b0 + 0.12, b1 - 0.12, 0.4, 0.5, LIT_CORE if on else CREAM, True, on))
    else:
        shapes.append(_rect(f, X(a0) - 0.02, X(a0) + 0.06, face + 0.002, 0.46, 0.56, "#FF4A3D" if on else TAIL, False, on))
    for a in (X(0.45), X(w - 0.55)):
        shapes.append(f.poly([(a + 0.24 * math.cos(t), face + 0.001, 0.21 + 0.24 * math.sin(t)) for t in [math.pi * k / 12 for k in range(13)]],
                             shade(body, 0.5), False))
        shapes.append(f.poly(_face_circle(f, a, face + 0.002, 0.2, 0.2, 20), TYRE))
        shapes.append(f.poly(_face_circle(f, a, face + 0.003, 0.2, 0.11, 14), CREAM))
        if spin is not None:
            for k in range(2):
                t = spin + math.pi / 2 * k
                shapes.append(Line((f.p(a + 0.09 * math.cos(t), face + 0.0035, 0.2 + 0.09 * math.sin(t)),
                                    f.p(a - 0.09 * math.cos(t), face + 0.0035, 0.2 - 0.09 * math.sin(t))), CHROME, 1.3))
        shapes.append(f.poly(_face_circle(f, a, face + 0.004, 0.2, 0.04, 8), CHROME, False))
    return shapes


#: Objects dressing a room's walls (DESIGN.md §108): (lowest, highest, reach into the room), tile
#: units over the wall's base, of a poster and a wall shelf.
WALL_SPANS: dict[str, tuple[float, float, float]] = {"poster": (1.2, 2.45, 0.05), "wall_shelf": (1.35, 2.45, 0.34)}
#: A poster's picture's sky colour by kind, and a shelf's book colours.
POSTER_SKIES: dict[str, str] = {"rocket": "#24365E", "atom": CREAM, "planet": "#2F8F9D"}
BOOKS = (CORAL, MUSTARD, TURQUOISE, CREAM, "#7C6FD6", MINT)
PLANT_GREEN = "#4FA36B"


def _poster(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A framed travel poster of tomorrow on the wall it hangs on (``color`` the frame, ``detail``
    the picture's accent): a rocket over a planet, an atom, or a ringed planet with a saucer."""
    kind = f.item.features[0] if f.item.features else "rocket"
    face_b = f.depth + 0.02
    cx, across = f.width / 2, (-1.0 if f.swap else 1.0)
    low, high, _ = WALL_SPANS["poster"]

    def at(u: float, z: float, lift: float = 0.0) -> Point3:
        return f.p(cx + across * u, face_b + lift, z)

    def rect(u0: float, u1: float, z0: float, z1: float, fill: str, lift: float, ink: bool = True) -> Poly:
        return Poly((at(u0, z0, lift), at(u1, z0, lift), at(u1, z1, lift), at(u0, z1, lift)), fill, ink)

    def disc(u: float, z: float, r: float, fill: str, lift: float, ink: bool = False, squash: float = 1.0) -> Poly:
        return Poly(tuple(at(u + r * math.cos(2 * math.pi * k / 16), z + squash * r * math.sin(2 * math.pi * k / 16), lift) for k in range(16)), fill, ink)

    half = 0.34
    shapes: list[Shape] = [rect(-half, half, low, high, look.main, 0.0), rect(-half + 0.05, half - 0.05, low + 0.05, high - 0.05, POSTER_SKIES[kind], 0.002, False)]
    mid = (low + high) / 2
    if kind == "rocket":
        shapes.append(disc(0.12, low + 0.28, 0.2, look.detail, 0.003))
        body = [(-0.05, mid - 0.2), (0.05, mid - 0.2), (0.06, mid + 0.18), (0.0, mid + 0.36), (-0.06, mid + 0.18)]
        shapes.append(Poly(tuple(at(u - 0.08, z, 0.004) for u, z in body), CREAM, False))
        for side in (-1.0, 1.0):
            shapes.append(Poly((at(-0.08 + side * 0.05, mid - 0.2, 0.005), at(-0.08 + side * 0.13, mid - 0.3, 0.005),
                                at(-0.08 + side * 0.05, mid - 0.06, 0.005)), CORAL, False))
        shapes.append(disc(-0.08, mid + 0.08, 0.03, TURQUOISE, 0.006))
        shapes += [disc(u, z, 0.012, CREAM, 0.003) for u, z in ((-0.2, high - 0.15), (0.18, high - 0.22), (0.22, mid + 0.05), (-0.22, mid - 0.15))]
    elif kind == "atom":
        for k in range(3):
            t = math.pi * k / 3
            ring = [(0.2 * math.cos(s) * math.cos(t) - 0.08 * math.sin(s) * math.sin(t), 0.2 * math.cos(s) * math.sin(t) + 0.08 * math.sin(s) * math.cos(t))
                    for s in [2 * math.pi * j / 20 for j in range(21)]]
            shapes.append(Line(tuple(at(u, mid + 0.08 + z, 0.003) for u, z in ring), look.detail, 1.6))
        shapes.append(disc(0.0, mid + 0.08, 0.04, CORAL, 0.004))
        shapes.append(rect(-0.2, 0.2, low + 0.12, low + 0.17, TURQUOISE, 0.003, False))
    else:
        shapes.append(disc(-0.04, mid, 0.16, MUSTARD, 0.003))
        ring = [(-0.04 + 0.27 * math.cos(s), mid + 0.06 * math.sin(s) - 0.03 * math.cos(s)) for s in [2 * math.pi * j / 20 for j in range(21)]]
        shapes.append(Line(tuple(at(u, z, 0.004) for u, z in ring), CREAM, 1.8))
        shapes.append(disc(0.16, high - 0.22, 0.07, look.detail, 0.004, squash=0.35))
        shapes.append(disc(0.16, high - 0.2, 0.035, "#BFEFFF", 0.005))
    return shapes


def _wall_shelf(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """Two planks on brackets on the wall it hangs on (``color`` wood, ``detail`` an accent) with
    rows of books, a small potted plant and a vase."""
    face_b = f.depth
    a0, a1 = 0.1, f.width - 0.1
    reach = WALL_SPANS["wall_shelf"][2] - 0.04
    shapes: list[Shape] = []
    for tier, z in enumerate((1.4, 2.0)):
        shapes += f.box(a0, face_b, z, a1, face_b + reach, z + 0.05, look.main)
        a = a0 + 0.04
        k = tier * 3 + f.item.column + f.item.row
        while a < a1 - 0.12:
            width = 0.06 + 0.03 * _unit(f.item.name, tier, a)
            height = 0.22 + 0.12 * _unit(f.item.name, a, tier)
            if tier == 1 and a > a0 + 0.45:   # a plant on the upper plank
                cx = a + 0.1
                shapes += f.box(cx - 0.07, face_b + 0.08, z + 0.05, cx + 0.07, face_b + 0.22, z + 0.17, CORAL)
                leaves = [(cx + 0.11 * math.cos(2 * math.pi * j / 10), face_b + 0.15, z + 0.27 + 0.1 * math.sin(2 * math.pi * j / 10)) for j in range(10)]
                shapes.append(f.poly(leaves, PLANT_GREEN))
                break
            color = look.detail if k % 4 == 0 else BOOKS[k % len(BOOKS)]
            shapes += f.box(a, face_b + 0.05, z + 0.05, a + width, face_b + reach - 0.03, z + 0.05 + height, color)
            a += width + 0.01
            k += 1
    return shapes


DRAWINGS: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {
    "googie_building": _googie_building, "retro_tower": _retro_tower, "starburst_sign": _starburst_sign, "ray_lamp": _ray_lamp,
    "atomic_sculpture": _atomic_sculpture, "monorail": _monorail, "tube_computer": _tube_computer, "sunburst_clock": _sunburst_clock,
    "tv_console": _tv_console, "retro_desk": _retro_desk, "hedge": _hedge, "planter": _planter, "poster": _poster, "wall_shelf": _wall_shelf,
}


def motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """The moving parts of a working object of this module at ``now``: an atomic sculpture's
    electrons, a tube computer's reels and bulbs, a TV console's picture."""
    kind = f.item.kind
    if kind == "atomic_sculpture":
        return _electrons(f, look, now)
    if kind == "tube_computer":
        return _tube_motion(f, look, now)
    if kind == "tv_console":
        return _tv_motion(f, look, now)
    return []


__all__ = ["CHROME", "CORAL", "CREAM", "MINT", "MUSTARD", "SUNBURST_HEIGHT", "SUNBURST_RADIUS", "TURQUOISE", "WALL_SPANS", "DRAWINGS", "motion",
           "rocket_car_shapes"]
