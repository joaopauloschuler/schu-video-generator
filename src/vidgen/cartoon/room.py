"""Rooms: a stage's indoor set (DESIGN.md §69.42). No manim: the stage draws these shapes.

A *room* replaces a stage's sky and ground band with a back wall, a floor in front of it, a
skirting board where they meet and an optional ceiling band. The wall stands at a *depth* (the
§69.6 depth of the things on the floor): the floor's top edge is where a thing at that depth
stands, so everything on the floor stands in front of the wall. Windows hang on the wall and show
the sky outside, whose colours follow the stage's ``light`` (:func:`window_sky`); doors are
``door`` props standing at the wall (their marks are the doors' names).

Positions are Manim units (origin at the frame's centre, ``y`` up). Sizes on the wall are in
*wall units*: the height of a character of scale 1 standing at the wall's depth.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from vidgen.cartoon.lighting import fade_at, grade_rgbas, tint_grade
from vidgen.cartoon.storm import FLASH_COLOR, WINDOW_FLASH
from vidgen.cartoon.stage import FAR_RISE, StageItem, depth_scale
from vidgen.lint.color import blend, hex_rgb, relative_luminance, rgb_hex

#: The wallpapers and floors a room can have.
WALLPAPERS: tuple[str, ...] = ("plain", "stripes", "dots")
FLOORINGS: tuple[str, ...] = ("plain", "boards", "tiles")
#: Default colours of the wall and the floor (a warm cream and a wood; no theme token is light
#: and warm in every preset) and of a window's frame.
DEFAULT_WALL = "#E9DCC9"
DEFAULT_FLOOR = "#C9A27A"
WINDOW_FRAME = "#F4F6FA"
#: The wall's depth when the room gives none and nothing on the floor stands further back.
WALL_DEPTH = 0.4
#: The skirting board's height (wall units) and the ceiling band's (a share of the frame height).
SKIRTING_HEIGHT = 0.07
CEILING_HEIGHT = 0.07
#: How much lighter or darker a wallpaper's pattern, the skirting and a ceiling are than the
#: colour they are made from (a share of the way to black or white).
PATTERN_SHADE = 0.1
SKIRTING_SHADE = 0.3
CEILING_SHADE = 0.25
#: Wallpaper: stripe width and dot spacing / radius (wall units).
STRIPE_WIDTH = 0.11
DOT_SPACING = 0.28
DOT_RADIUS = 0.03
#: Floor: the depth of a row of boards or tiles at the wall (wall units), how many times deeper
#: the front row looks (perspective), a board's length and a tile's width at the wall (wall units),
#: and how much wider the floor looks at the frame's bottom edge than at the wall (tiles' lines).
ROW_DEPTH = 0.16
FRONT_ROWS = 2.2
BOARD_LENGTH = 0.9
TILE_WIDTH = 0.32
FLOOR_SPREAD = 1.6
#: A window's default width, height and the height of its sill above the floor (wall units),
#: its frame's width (a share of the window's smaller side) and a curtain's width (a share of
#: the window's width).
WINDOW_WIDTH = 0.6
WINDOW_HEIGHT = 0.62
WINDOW_SILL = 0.42
FRAME_SHARE = 0.08
CURTAIN_SHARE = 0.3
#: A door's height relative to a character's (the ``door`` prop is 1 character tall).
DOOR_SCALE = 1.3
#: Particles that fall or blow outdoors only (none in a room).
OUTDOOR_PARTICLES: tuple[str, ...] = ("rain", "snow", "leaves", "streaks")
#: Seconds a character takes to fade in when it enters through a door (and out when it leaves).
DOOR_FADE_SECONDS = 0.35

Point = tuple[float, float]
Segment = tuple[Point, Point]


@dataclass(frozen=True)
class Box:
    """An upright rectangle: ``left``, ``bottom``, ``right``, ``top`` (Manim units)."""

    left: float
    bottom: float
    right: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def center(self) -> Point:
        return ((self.left + self.right) / 2, (self.bottom + self.top) / 2)


@dataclass(frozen=True)
class RoomGeometry:
    """Where a room's pieces are: the ``wall`` (from the floor's top edge to the frame's top),
    the ``floor`` (from the frame's bottom edge to the wall), the ``skirting`` board on the wall
    just above the floor, the ``ceiling`` band (``None``: none), and ``unit``, the wall unit
    (Manim units)."""

    wall: Box
    floor: Box
    skirting: Box
    ceiling: Box | None
    unit: float

    @property
    def wall_line(self) -> float:
        """The y where the floor meets the wall."""
        return self.floor.top


def wall_depth(items: Sequence[StageItem], depth: float | None = None) -> float:
    """How far back a room's wall stands: ``depth`` when given, else :data:`WALL_DEPTH` or the
    depth of the deepest thing standing on the floor (``lift`` 0), whichever is further back."""
    if depth is not None:
        return float(depth)
    return max([WALL_DEPTH, *(item.depth for item in items if item.lift == 0)])


def room_geometry(
    *,
    ground: float,
    depth: float,
    size: float,
    frame_width: float,
    frame_height: float,
    stage_width: float | None = None,
    ceiling: bool = False,
) -> RoomGeometry:
    """The pieces of a room whose wall stands at ``depth`` on a stage with its ground line at
    ``ground`` (a fraction of the frame height above the bottom edge) and characters ``size``
    of the frame's shorter side tall, ``stage_width`` wide (Manim units, default the frame's)."""
    width = frame_width if stage_width is None else stage_width
    left, right = -width / 2, width / 2
    bottom, top = -frame_height / 2, frame_height / 2
    unit = size * min(frame_width, frame_height) * depth_scale(depth)
    line = (ground + FAR_RISE * depth - 0.5) * frame_height
    band = Box(left, top - CEILING_HEIGHT * frame_height, right, top) if ceiling else None
    return RoomGeometry(
        wall=Box(left, line, right, top),
        floor=Box(left, bottom, right, line),
        skirting=Box(left, line, right, line + SKIRTING_HEIGHT * unit),
        ceiling=band,
        unit=unit,
    )


# ----- colours ------------------------------------------------------------------------------------


def shade(color: str, amount: float) -> str:
    """``color`` (``#hex``) ``amount`` of the way to black when it is light, to white when it is
    dark: a pattern on it, or its edge, reads on it in any theme."""
    rgb = hex_rgb(color)
    towards = (0.0, 0.0, 0.0) if relative_luminance(rgb) > 0.18 else (1.0, 1.0, 1.0)
    return rgb_hex(blend(towards, rgb, amount))


def darker(color: str, amount: float) -> str:
    """``color`` (``#hex``) ``amount`` of the way to black (a skirting board under a floor colour)."""
    return rgb_hex(blend((0.0, 0.0, 0.0), hex_rgb(color), amount))


def lighter(color: str, amount: float) -> str:
    """``color`` (``#hex``) ``amount`` of the way to white (a ceiling over a wall colour)."""
    return rgb_hex(blend((1.0, 1.0, 1.0), hex_rgb(color), amount))


# ----- the wall's and the floor's patterns -------------------------------------------------------


def wallpaper_stripes(wall: Box, unit: float) -> list[Box]:
    """Vertical stripes :data:`STRIPE_WIDTH` wall units wide, one every two widths, across the
    wall from its left edge."""
    step = STRIPE_WIDTH * unit
    count = int(wall.width // (2 * step)) + 1
    return [
        Box(wall.left + (2 * k + 0.5) * step, wall.bottom, min(wall.left + (2 * k + 1.5) * step, wall.right), wall.top)
        for k in range(count)
        if wall.left + (2 * k + 0.5) * step < wall.right
    ]


def wallpaper_dots(wall: Box, unit: float) -> list[tuple[float, float, float]]:
    """Dots ``(x, y, radius)`` on a grid :data:`DOT_SPACING` wall units apart, every other row
    shifted by half a step, inside the wall."""
    step, radius = DOT_SPACING * unit, DOT_RADIUS * unit
    dots: list[tuple[float, float, float]] = []
    row = 0
    y = wall.bottom + step / 2
    while y < wall.top - radius:
        x = wall.left + (step / 2 if row % 2 else step)
        while x < wall.right - radius:
            dots.append((x, y, radius))
            x += step
        y += step
        row += 1
    return dots


def floor_rows(floor: Box, unit: float) -> list[float]:
    """The y of each line between two rows of boards or tiles, from the wall to the front: the
    first row :data:`ROW_DEPTH` wall units deep, each further one a little deeper, the front row
    about :data:`FRONT_ROWS` times the first (the floor seen in perspective)."""
    first = ROW_DEPTH * unit
    if floor.height <= first:
        return []
    count = max(2, round(2 * floor.height / (first * (1 + FRONT_ROWS))))
    ratio = FRONT_ROWS ** (1 / max(count - 1, 1))
    depths = [ratio**k for k in range(count)]
    scale = floor.height / sum(depths)
    ys, y = [], floor.top
    for d in depths[:-1]:
        y -= d * scale
        ys.append(y)
    return ys


def floor_lines(flooring: str, floor: Box, unit: float) -> list[Segment]:
    """The lines drawn on a floor: ``boards`` (the seams between rows of boards and the joints
    between boards, staggered row by row), ``tiles`` (the rows' seams and lines running towards
    the front, spreading :data:`FLOOR_SPREAD` times from the wall to the frame's bottom edge) or
    none (``plain``). ``ValueError`` for another flooring."""
    if flooring not in FLOORINGS:
        raise ValueError(f"unknown flooring '{flooring}' (floorings: {', '.join(FLOORINGS)})")
    if flooring == "plain":
        return []
    rows = floor_rows(floor, unit)
    lines: list[Segment] = [((floor.left, y), (floor.right, y)) for y in rows]
    if flooring == "boards":
        edges = [floor.top, *rows, floor.bottom]
        for k, (upper, lower) in enumerate(zip(edges, edges[1:])):
            length = BOARD_LENGTH * unit * (upper - lower) / (ROW_DEPTH * unit)
            x = floor.left + ((0.37 * k) % 1.0) * length
            while x < floor.right:
                if x > floor.left:
                    lines.append(((x, upper), (x, lower)))
                x += length
        return lines
    middle = (floor.left + floor.right) / 2
    step = TILE_WIDTH * unit
    count = int((floor.right - middle) // step)
    for k in range(-count, count + 1):
        back = middle + k * step
        lines.append(_clipped_spread(back, middle, floor))
    return lines


def _clipped_spread(back: float, middle: float, floor: Box) -> Segment:
    """A tile line from ``back`` on the wall line to the frame's bottom edge, :data:`FLOOR_SPREAD`
    times as far from ``middle`` there, ending at the floor's side edge if it reaches it first."""
    front = middle + (back - middle) * FLOOR_SPREAD
    edge = floor.right if front > middle else floor.left
    if (front - edge) * (edge - middle) > 0:   # past the side edge: stop there
        share = (edge - back) / (front - back)
        return ((back, floor.top), (edge, floor.top - share * floor.height))
    return ((back, floor.top), (front, floor.bottom))


# ----- windows ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowParts:
    """A window's pieces: its ``frame`` (outer edge), the ``glass`` inside it (where the sky shows),
    the ``bars`` across the glass (a cross), the ``sill`` under it, the curtain ``rod`` above it
    (``None`` without curtains) and the ``curtains`` (closed outlines; none without curtains)."""

    frame: Box
    glass: Box
    bars: tuple[Box, ...]
    sill: Box
    rod: Box | None
    curtains: tuple[tuple[Point, ...], ...]


def window_parts(x: float, wall_line: float, unit: float, *, width: float = WINDOW_WIDTH, height: float = WINDOW_HEIGHT,
                 sill: float = WINDOW_SILL, curtains: bool = True) -> WindowParts:
    """A window centred on ``x`` on a wall whose floor line is at ``wall_line``: ``width`` and
    ``height`` wall units, its bottom ``sill`` wall units above the floor (``unit``: the wall unit)."""
    w, h = width * unit, height * unit
    bottom = wall_line + sill * unit
    frame = Box(x - w / 2, bottom, x + w / 2, bottom + h)
    edge = FRAME_SHARE * min(w, h)
    glass = Box(frame.left + edge, frame.bottom + edge, frame.right - edge, frame.top - edge)
    bar = edge * 0.6
    cx, cy = glass.center
    bars = (Box(cx - bar / 2, glass.bottom, cx + bar / 2, glass.top), Box(glass.left, cy - bar / 2, glass.right, cy + bar / 2))
    ledge = edge * 0.8
    sill_box = Box(frame.left - ledge, frame.bottom - ledge, frame.right + ledge, frame.bottom + ledge * 0.3)
    if not curtains:
        return WindowParts(frame, glass, bars, sill_box, None, ())
    rod = Box(frame.left - 2 * ledge, frame.top + ledge, frame.right + 2 * ledge, frame.top + 1.6 * ledge)
    reach = CURTAIN_SHARE * w
    top, low = rod.bottom, frame.bottom - ledge
    tie = frame.bottom + 0.4 * h

    def curtain(outer: float, sign: float) -> tuple[Point, ...]:
        inner = outer + sign * reach
        waist = outer + sign * reach * 0.35
        hem = outer + sign * reach * 0.8
        return ((outer, top), (inner, top), (waist, tie), (hem, low), (outer, low))

    return WindowParts(frame, glass, bars, sill_box, rod, (curtain(frame.left - ledge, 1.0), curtain(frame.right + ledge, -1.0)))


# ----- the sky outside ------------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowSky:
    """The sky a window shows: ``top`` and ``bottom`` colours of its gradient (``#hex``) and how
    bright its stars are (0: none)."""

    top: str
    bottom: str
    stars: float = 0.0


#: The sky outside per light preset. ``indoor`` is lamplight inside, so it is evening outside.
WINDOW_SKIES: dict[str, WindowSky] = {
    "day": WindowSky("#7FB8E6", "#CFE8F7"),
    "morning": WindowSky("#9CC4E8", "#FBE3C8"),
    "sunset": WindowSky("#5B6FB0", "#F59A6B"),
    "night": WindowSky("#0E1838", "#24366A", 1.0),
    "indoor": WindowSky("#1B2550", "#4A4F86", 0.6),
}


def window_sky(light: str | tuple[str, float]) -> WindowSky:
    """The sky outside a window under ``light``: a preset's (:data:`WINDOW_SKIES`), or for a tint
    ``(#hex, strength)`` the day's sky multiplied towards the tint as the light grades the set
    (§69.31). ``ValueError`` for an unknown preset."""
    if isinstance(light, tuple):
        day = WINDOW_SKIES["day"]
        rows = np.array([[*hex_rgb(day.top), 1.0], [*hex_rgb(day.bottom), 1.0]])
        top, bottom = grade_rgbas(rows, tint_grade(*light))[:, :3]
        return WindowSky(rgb_hex(tuple(top)), rgb_hex(tuple(bottom)))  # type: ignore[arg-type]
    if light not in WINDOW_SKIES:
        raise ValueError(f"unknown light {light!r}; presets: {', '.join(WINDOW_SKIES)}")
    return WINDOW_SKIES[light]


def blend_skies(a: WindowSky, b: WindowSky, share: float) -> WindowSky:
    """``share`` 0..1 of the way from sky ``a`` to sky ``b`` (colours and stars linearly)."""
    s = min(max(float(share), 0.0), 1.0)
    return WindowSky(
        rgb_hex(blend(hex_rgb(b.top), hex_rgb(a.top), s)),
        rgb_hex(blend(hex_rgb(b.bottom), hex_rgb(a.bottom), s)),
        a.stars * (1.0 - s) + b.stars * s,
    )


def flash_sky(sky: WindowSky, level: float) -> WindowSky:
    """The sky outside lit by lightning at ``level`` (0..1, DESIGN.md §69.61): ``level`` ×
    :data:`~vidgen.cartoon.storm.WINDOW_FLASH` of the way to the flash's colour (nothing indoors
    dims it); ``sky`` at 0."""
    if level <= 0:
        return sky
    return blend_skies(sky, WindowSky(FLASH_COLOR, FLASH_COLOR), level * WINDOW_FLASH)


@dataclass(frozen=True)
class SkyChange:
    """The sky outside fading to ``value`` from scene time ``start`` over ``seconds`` (a ``light``
    action; :func:`~vidgen.cartoon.lighting.fade_at`)."""

    start: float
    seconds: float
    value: WindowSky

    @property
    def end(self) -> float:
        return self.start + max(self.seconds, 0.0)


def sky_at(base: WindowSky, changes: Sequence[SkyChange], now: float) -> WindowSky:
    """The sky outside at scene time ``now``: ``base``, then the changes faded in (smoothstep)."""
    return fade_at(base, changes, now, blend_skies)


__all__ = [
    "DEFAULT_FLOOR",
    "DEFAULT_WALL",
    "DOOR_FADE_SECONDS",
    "DOOR_SCALE",
    "FLOORINGS",
    "OUTDOOR_PARTICLES",
    "WALLPAPERS",
    "WALL_DEPTH",
    "WINDOW_FRAME",
    "WINDOW_HEIGHT",
    "WINDOW_SILL",
    "WINDOW_SKIES",
    "WINDOW_WIDTH",
    "Box",
    "RoomGeometry",
    "SkyChange",
    "WindowParts",
    "WindowSky",
    "blend_skies",
    "flash_sky",
    "darker",
    "floor_lines",
    "floor_rows",
    "lighter",
    "room_geometry",
    "shade",
    "sky_at",
    "wall_depth",
    "wallpaper_dots",
    "wallpaper_stripes",
    "window_parts",
    "window_sky",
]
