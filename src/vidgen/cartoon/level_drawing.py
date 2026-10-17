"""The tiles of a platform level drawn once into pictures (DESIGN.md §86), in vidgen's flat
cartoon look: filled shapes with the characters' outline ink. No manim.

:func:`level_shapes` lists the shapes in world (tile) units, back to front; :func:`draw_columns`
paints the columns ``first .. last`` of them into a Pillow image, supersampled for smooth edges.
A scene draws the level in chunks of :data:`CHUNK_COLUMNS` columns, so a camera move only
redraws the chunks in view.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageColor, ImageDraw

from vidgen.config import CHARACTER_INK
from vidgen.world import CLOUD, GROUND, LADDER, PLATFORM, Level

#: Outline width of the tiles (tile units) in the plain drawing style.
OUTLINE = 0.04
#: Grass on top of the ground: its depth and the radius of the scallops along its bottom edge.
GRASS_DEPTH = 0.2
GRASS_SCALLOP = 0.1
#: A floating platform's slab: its thickness and corner radius (tile units).
PLATFORM_THICKNESS = 0.38
PLATFORM_RADIUS = 0.12
#: Room drawn above the highest tile (tile units): a cloud's bumps reach a little over its top.
TOP_ROOM = 0.25
#: Columns per drawn chunk, and the supersampling factor of the drawing.
CHUNK_COLUMNS = 8
SUPERSAMPLE = 2


@dataclass(frozen=True)
class LevelColors:
    """The tiles' fill colours (``#rrggbb``); the outline is the characters' ink."""

    ground: str = "#B5835A"
    grass: str = "#7CC456"
    platform: str = "#C98B4F"
    cloud: str = "#FFFFFF"
    ladder: str = "#C98B4F"
    ink: str = CHARACTER_INK


@dataclass(frozen=True)
class Shape:
    """One filled shape in tile units (``y`` up): ``rect`` or ``ellipse`` in the box (x0, y0,
    x1, y1), or ``rounded`` (a rectangle with corners of ``radius``)."""

    kind: str
    box: tuple[float, float, float, float]
    fill: str
    radius: float = 0.0

    def shrunk(self, by: float, fill: str) -> Shape:
        """The shape ``by`` smaller on every side, filled with ``fill``."""
        x0, y0, x1, y1 = self.box
        return Shape(self.kind, (x0 + by, y0 + by, x1 - by, y1 - by), fill, max(self.radius - by, 0.0))


def mix(color: str, towards: str, amount: float) -> str:
    """``color`` moved ``amount`` (0..1) of the way to ``towards`` (both ``#rrggbb``)."""
    a, b = ImageColor.getrgb(color)[:3], ImageColor.getrgb(towards)[:3]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def _outlined(shapes: Sequence[Shape], ink: str, width: float) -> list[Shape]:
    """``shapes`` as one outlined form: all of them in ink, then all of them ``width`` smaller in
    their fills (the ink shows only along the form's edge)."""
    return [*(Shape(s.kind, s.box, ink, s.radius) for s in shapes), *(s.shrunk(width, s.fill) for s in shapes)]


def _ground(level: Level, colors: LevelColors, width: float) -> list[Shape]:
    """The ground as one mass: ink cells, fills inset on their open sides (and ink in the inner
    corners), grass with a scalloped edge on top, and a few pebbles."""
    def solid(column: int, row: int) -> bool:
        return level.tile(column, row) == GROUND

    cells = [(c, r) for r in range(level.rows) for c in range(level.columns) if solid(c, r)]
    ink, fills, corners, grass, pebbles = [], [], [], [], []
    pebble = mix(colors.ground, "#000000", 0.18)
    for c, r in cells:
        left, right, up = not solid(c - 1, r), not solid(c + 1, r), not solid(c, r + 1)
        down = not solid(c, r - 1) and r > 0   # the map's bottom edge runs on below the frame
        ink.append(Shape("rect", (c, r, c + 1, r + 1), colors.ink))
        x0, x1 = c + (width if left else 0.0), c + 1 - (width if right else 0.0)
        fills.append(Shape("rect", (x0, r + (width if down else 0.0), x1, r + 1 - (width if up else 0.0)), colors.ground))
        for dx, dy in ((-1, 1), (1, 1), (-1, -1), (1, -1)):   # an inner corner: both sides solid, the diagonal open
            if solid(c + dx, r) and solid(c, r + dy) and not solid(c + dx, r + dy):
                cx, cy = (c if dx < 0 else c + 1 - width), (r + 1 - width if dy > 0 else r)
                corners.append(Shape("rect", (cx, cy, cx + width, cy + width), colors.ink))
        if up:
            top = r + 1 - width
            grass.append(Shape("rect", (x0, top - GRASS_DEPTH, x1, top), colors.grass))
            for share in (0.25, 0.75):
                cx = c + share
                grass.append(Shape("ellipse", (cx - GRASS_SCALLOP, top - GRASS_DEPTH - GRASS_SCALLOP * 0.8,
                                               cx + GRASS_SCALLOP, top - GRASS_DEPTH + GRASS_SCALLOP * 0.8), colors.grass))
        seed = zlib.crc32(f"{c}:{r}".encode())
        if seed % 3 == 0:   # a pebble in one cell of three, placed by the cell (the same every render)
            px = c + 0.25 + (seed >> 4) % 50 / 100
            py = r + 0.2 + (seed >> 10) % 25 / 100
            size = 0.06 + (seed >> 16) % 5 / 100
            pebbles.append(Shape("ellipse", (px - size, py - size * 0.7, px + size, py + size * 0.7), pebble))
    return [*ink, *fills, *corners, *grass, *pebbles]


def _platforms(level: Level, colors: LevelColors, width: float) -> list[Shape]:
    """Each run of platform tiles as one wooden slab under the tiles' top, with plank seams."""
    shapes: list[Shape] = []
    light = mix(colors.platform, "#FFFFFF", 0.3)
    for run in level.runs(PLATFORM):
        top, bottom = run.row + 1, run.row + 1 - PLATFORM_THICKNESS
        slab = Shape("rounded", (run.first, bottom, run.last + 1, top), colors.platform, PLATFORM_RADIUS)
        shapes += _outlined([slab], colors.ink, width)
        shapes.append(Shape("rect", (run.first + 2 * width, top - 2.2 * width, run.last + 1 - 2 * width, top - width), light))
        for column in range(run.first + 1, run.last + 1):
            shapes.append(Shape("rect", (column - width * 0.35, bottom + width, column + width * 0.35, top - width), colors.ink))
    return shapes


def _clouds(level: Level, colors: LevelColors, width: float) -> list[Shape]:
    """Each run of cloud tiles as one puffy cloud whose bumps' tops are the tiles' top."""
    shapes: list[Shape] = []
    for run in level.runs(CLOUD):
        top = run.row + 1
        puffs = [Shape("rounded", (run.first, top - 0.8, run.last + 1, top - 0.3), colors.cloud, 0.25)]
        for column in range(run.first, run.last + 1):
            puffs.append(Shape("ellipse", (column + 0.02, top - 0.75, column + 0.98, top + 0.02), colors.cloud))
        shapes += _outlined(puffs, colors.ink, width)
        shade = mix(colors.cloud, "#9DB8D9", 0.45)
        shapes.append(Shape("rounded", (run.first + 0.18, top - 0.8 + 2 * width, run.last + 0.82, top - 0.62), shade, 0.08))
    return shapes


def _ladders(level: Level, colors: LevelColors, width: float) -> list[Shape]:
    """Each ladder tile: two rails and two rungs."""
    parts: list[Shape] = []
    for run in level.runs(LADDER):
        for column in range(run.first, run.last + 1):
            r = run.row
            parts += [Shape("rect", (column + 0.16, r, column + 0.3, r + 1), colors.ladder),
                      Shape("rect", (column + 0.7, r, column + 0.84, r + 1), colors.ladder)]
            parts += [Shape("rect", (column + 0.16, r + y, column + 0.84, r + y + 0.12), colors.ladder) for y in (0.2, 0.68)]
    return _outlined(parts, colors.ink, width)


def level_shapes(level: Level, colors: LevelColors = LevelColors(), outline: float = 1.0) -> list[Shape]:
    """Every shape of the level's tiles, back to front: ladders, ground, platforms, clouds.
    ``outline`` multiplies :data:`OUTLINE` (the drawing style's outline factor)."""
    width = OUTLINE * outline
    return [*_ladders(level, colors, width), *_ground(level, colors, width), *_platforms(level, colors, width), *_clouds(level, colors, width)]


def drawn_rows(level: Level) -> float:
    """How many tile rows the drawing covers from the bottom: the used rows and :data:`TOP_ROOM`."""
    return level.used_rows() + TOP_ROOM


def draw_columns(shapes: Sequence[Shape], first: int, last: int, rows: float, tile_pixels: int) -> Image.Image:
    """An RGBA picture of ``shapes`` from column ``first`` to ``last`` (inclusive), ``rows``
    rows high from the bottom, ``tile_pixels`` pixels per tile; transparent where there is no
    tile. Drawn :data:`SUPERSAMPLE` times larger and reduced with a box filter, so chunks drawn
    side by side join without a seam."""
    scale = tile_pixels * SUPERSAMPLE
    width, height = (last - first + 1) * tile_pixels, math.ceil(rows * tile_pixels)
    big = Image.new("RGBA", (width * SUPERSAMPLE, height * SUPERSAMPLE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    top = height * SUPERSAMPLE
    for shape in shapes:
        x0, y0, x1, y1 = shape.box
        if x1 < first or x0 > last + 1 or x1 <= x0 or y1 <= y0:
            continue
        box = [(x0 - first) * scale, top - y1 * scale, (x1 - first) * scale - 1, top - y0 * scale - 1]
        if box[2] < box[0] or box[3] < box[1]:
            continue
        if shape.kind == "ellipse":
            draw.ellipse(box, fill=shape.fill)
        elif shape.kind == "rounded":
            radius = min(shape.radius * scale, (box[2] - box[0]) / 2, (box[3] - box[1]) / 2)
            draw.rounded_rectangle(box, radius=max(radius, 0.0), fill=shape.fill)
        else:
            draw.rectangle(box, fill=shape.fill)
    return big.resize((width, height), Image.Resampling.BOX)


__all__ = [
    "CHUNK_COLUMNS",
    "LevelColors",
    "OUTLINE",
    "Shape",
    "draw_columns",
    "drawn_rows",
    "level_shapes",
    "mix",
]
