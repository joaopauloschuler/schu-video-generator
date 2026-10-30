"""A city at night on an isometric place (DESIGN.md §102.2, §102.3), the maths without manim: a
tower's parts in its own frame (its info screen, its algae-farm bands, its antenna), how a
screen's lines of text crawl, and where the hover pods of a traffic lane are at a time.

A tower (the ``tower`` object, drawn by :mod:`vidgen.cartoon.iso_objects`) is a tall box: rows
of windows on its two faces that show (lit by a seeded share when it is on), neon trims in its
detail colour, optionally a big info ``screen`` on its front and glowing ``garden`` bands of
algae farms up its faces, and an antenna with a red light on its roof. The stage draws the moving
parts over the place's pictures (:mod:`vidgen.cartoon.iso_overlays`): the screens' crawling lines
and the pods gliding along the lanes.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass

from vidgen.world.iso_view import Box3, Point3, in_front, iso_point

#: A tower's storeys and window columns (tile units): a window row every ``TOWER_FLOOR`` from
#: ``TOWER_FIRST`` up, a column every ``TOWER_COLUMN``; a window is ``TOWER_WINDOW`` (across, up).
TOWER_FLOOR = 0.5
TOWER_FIRST = 0.55
TOWER_COLUMN = 0.34
TOWER_WINDOW = (0.2, 0.28)
#: The share of a lit tower's windows that show light (seeded per window) and their colours.
TOWER_LIT_SHARE = 0.58
TOWER_WINDOW_COLORS: tuple[str, ...] = ("#FFD98A", "#9FE8FF", "#FFF1D6", "#FFB86B")
#: An unlit window's glass (shaded by the face it is on).
TOWER_DARK_GLASS = "#1A2036"
#: How far in from its footprint a tower's walls stand (tile units).
TOWER_INSET = 0.08
#: The info screen on the front: from .. to across the face (shares), and up the tower (shares
#: of its height, at least ``TOWER_SCREEN_MIN`` tiles tall).
TOWER_SCREEN_ACROSS = (0.12, 0.88)
TOWER_SCREEN_UP = (0.52, 0.8)
TOWER_SCREEN_MIN = 1.2
#: The algae farms: a band of ``TOWER_GARDEN_HEIGHT`` tiles every ``TOWER_GARDEN_EVERY`` tiles
#: up the faces, from ``TOWER_GARDEN_FIRST``; their colour.
TOWER_GARDEN_EVERY = 2.5
TOWER_GARDEN_FIRST = 1.4
TOWER_GARDEN_HEIGHT = 0.42
TOWER_GARDEN_COLOR = "#3DFFB0"
#: The antenna on the roof (tile units high) and its light's colour.
TOWER_ANTENNA = 1.1
TOWER_ANTENNA_LIGHT = "#FF3B3B"
#: A screen's lines of text: how many are shown, how fast they crawl up (screen heights a
#: second), and the colour drawn over the screen's glow.
SCREEN_LINES = 6
SCREEN_CRAWL = 0.12
SCREEN_TEXT = "#F2FDFF"


def _unit(*keys: object) -> float:
    """A seeded number 0 .. 1 from ``keys`` (the same keys give the same number)."""
    return (zlib.crc32(":".join(str(k) for k in keys).encode()) % 10007) / 10007


def window_lit(name: str, face: str, row: int, column: int) -> bool:
    """Whether a lit tower's window shows light (:data:`TOWER_LIT_SHARE` of them, seeded)."""
    return _unit(name, face, row, column) < TOWER_LIT_SHARE


def window_color(name: str, face: str, row: int, column: int) -> str:
    """The colour of a lit window (one of :data:`TOWER_WINDOW_COLORS`, seeded)."""
    return TOWER_WINDOW_COLORS[int(_unit(name, face, row, column, "color") * len(TOWER_WINDOW_COLORS)) % len(TOWER_WINDOW_COLORS)]


def screen_box(height: float) -> tuple[float, float, float, float]:
    """``(across from, across to, up from, up to)`` of a tower's info screen: shares across its
    front, heights (tile units) up the tower of ``height``."""
    z0, z1 = TOWER_SCREEN_UP[0] * height, TOWER_SCREEN_UP[1] * height
    if z1 - z0 < TOWER_SCREEN_MIN:
        z0 = max(z1 - TOWER_SCREEN_MIN, TOWER_FIRST)
    return TOWER_SCREEN_ACROSS[0], TOWER_SCREEN_ACROSS[1], z0, z1


def garden_bands(height: float) -> list[tuple[float, float]]:
    """The algae-farm bands of a tower ``height`` tall: ``(from, to)`` heights (tile units)."""
    bands: list[tuple[float, float]] = []
    z = TOWER_GARDEN_FIRST
    while z + TOWER_GARDEN_HEIGHT < height - 0.5:
        bands.append((z, z + TOWER_GARDEN_HEIGHT))
        z += TOWER_GARDEN_EVERY
    return bands


def screen_color(detail: str) -> str:
    """The glow of a tower's info screen whose neon is ``detail`` (a hex): a deep shade of it,
    so its white lines of text read."""
    from vidgen.cartoon.iso_drawing import mix

    return mix(detail, "#101830", 0.45)


def screen_seed(name: str) -> int:
    """The seed of the lines on the screen of the tower called ``name``."""
    return zlib.crc32(name.encode())


def screen_lines(now: float, seed: int = 0, count: int = SCREEN_LINES) -> list[tuple[float, float]]:
    """The lines of text on a screen at scene time ``now``: ``(up, length)`` shares of the
    screen's height (from its bottom) and width, crawling up at :data:`SCREEN_CRAWL`; a line
    leaving the top comes back at the bottom with another (seeded) length."""
    found: list[tuple[float, float]] = []
    for k in range(count):
        travelled = now * SCREEN_CRAWL * count + k + 0.5   # in line spacings, from the bottom
        cycle = math.floor(travelled / count)
        up = (travelled % count) / count
        found.append((up, 0.3 + 0.62 * _unit(seed, k, cycle)))
    return found


@dataclass(frozen=True)
class PodSpot:
    """One pod of a lane at a time: ``share`` of the way along the lane (0 .. 1) and how much it
    shows (``shown``, 0 .. 1: it fades in and out at the lane's ends)."""

    share: float
    shown: float


#: A pod fades in and out over this share of its lane; its length (tile widths on the picture)
#: at ``size: 1``.
POD_FADE = 0.08
POD_LENGTH = 0.8


def lane_pods(now: float, seconds: float, count: int, at: float | None = None) -> list[PodSpot]:
    """Where the pods of a lane are at scene time ``now``. Each takes ``seconds`` along it.
    ``at`` ``None``: ``count`` pods loop along it all the time, evenly spaced (already on their
    way at the start); a time: each crosses once, the first from ``at``, the next ones
    ``seconds / count`` apart, easing in and out (a pod that sets off and arrives). Each fades in
    and out over :data:`POD_FADE` of its way (of its time, crossing once). Pods not on the lane
    now are left out."""
    found: list[PodSpot] = []
    for k in range(count):
        if at is None:
            share = (now / seconds + k / count) % 1.0
            found.append(PodSpot(share, max(0.0, min(1.0, share / POD_FADE, (1.0 - share) / POD_FADE))))
            continue
        t = (now - at - k * seconds / count) / seconds
        if t < 0.0 or t > 1.0:
            continue
        share = t * t * (3.0 - 2.0 * t)
        found.append(PodSpot(share, max(0.0, min(1.0, t / POD_FADE, (1.0 - t) / POD_FADE))))
    return found


#: The box a pod flies in, for what hides it (half its size each way, tile units).
POD_BOX = (0.35, 0.35, 0.2)


def _hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The convex hull of ``points`` (counter-clockwise, monotone chain)."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def box_outline(box: Box3) -> list[tuple[float, float]]:
    """The outline of ``box`` on the picture (tile widths, ``v`` down): the convex hull of its
    corners."""
    return _hull([iso_point(*corner) for corner in box.corners()])


def _inside(hull: list[tuple[float, float]], point: tuple[float, float]) -> bool:
    """Whether ``point`` lies inside the convex ``hull`` (either winding)."""
    if len(hull) < 3:
        return False
    signs = set()
    for k, a in enumerate(hull):
        b = hull[(k + 1) % len(hull)]
        c = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
        if abs(c) > 1e-12:
            signs.add(c > 0)
    return len(signs) <= 1


def pod_hidden(point: Point3, occluders: list[tuple[Box3, list[tuple[float, float]]]]) -> bool:
    """Whether a pod at world ``point`` is hidden by one of ``occluders`` (each a box and its
    outline on the picture, :func:`box_outline`): a box drawn in front of the pod's box whose
    outline covers the pod's middle."""
    x, y, z = point
    hx, hy, hz = POD_BOX
    mine = Box3(x - hx, y - hy, z - hz, x + hx, y + hy, z + hz)
    where = iso_point(x, y, z)
    return any(in_front(box, mine) is True and _inside(outline, where) for box, outline in occluders)


__all__ = [
    "POD_BOX",
    "POD_FADE",
    "POD_LENGTH",
    "SCREEN_CRAWL",
    "SCREEN_LINES",
    "SCREEN_TEXT",
    "TOWER_ANTENNA",
    "TOWER_ANTENNA_LIGHT",
    "TOWER_COLUMN",
    "TOWER_DARK_GLASS",
    "TOWER_FIRST",
    "TOWER_FLOOR",
    "TOWER_GARDEN_COLOR",
    "TOWER_INSET",
    "TOWER_LIT_SHARE",
    "TOWER_WINDOW",
    "TOWER_WINDOW_COLORS",
    "PodSpot",
    "box_outline",
    "garden_bands",
    "lane_pods",
    "pod_hidden",
    "screen_box",
    "screen_color",
    "screen_lines",
    "screen_seed",
    "window_color",
    "window_lit",
]
