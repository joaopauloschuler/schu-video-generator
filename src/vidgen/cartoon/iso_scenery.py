"""An isometric place as shapes (DESIGN.md §89.6): its flat ground (drawn once, behind everything)
and its *pieces*, the raised blocks, walls and objects that can hide a character, each in the box
it stands in for the draw order. No manim.

Outdoors the ground is grass with paths and water, the place a slab of earth with its edges
showing; indoors a wooden floor (``:`` a tiled one) and walls in the room's colour, the back
walls standing with their skirting, windows and doors, the front walls cut away with their cut
showing on top.
"""

from __future__ import annotations

import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field

from vidgen.cartoon.iso_drawing import Disc, Line, Poly, Shape, box_shapes, mix, shade
from vidgen.cartoon.iso_objects import FRAME, GLASS, WOOD, ObjectLook, object_box, object_shapes
from vidgen.config import CHARACTER_INK
from vidgen.world.iso import (
    BLOCK,
    DOOR,
    DOOR_HEIGHT,
    FLOOR,
    PATH,
    VOID,
    WALLS,
    WATER,
    WINDOW,
    IsoPlace,
)
from vidgen.world.iso_view import Box3

#: How deep the place's slab shows under its edges, and how far water lies below the ground
#: (tile units).
SLAB_DEPTH = 0.45
WATER_DEPTH = 0.14
#: How far a wall stands in from a side of its cell that does not join another wall (tile units).
WALL_INSET = 0.24
#: A standing wall's skirting board and a window's sill and top (tile units over the wall's base).
SKIRTING = 0.16
WINDOW_SILL = 1.0
WINDOW_TOP = 2.15


@dataclass(frozen=True)
class IsoColors:
    """The ground's and the walls' colours (``#rrggbb``); objects take their own (``ObjectLook``)."""

    grass: str = "#A5D67E"
    earth: str = "#B98A5E"
    path: str = "#E8D5A6"
    water: str = "#7CC7EA"
    stone: str = "#CBC5B8"
    floor: str = "#D9AE7E"
    tiles: str = "#EDE7DB"
    wall: str = "#EDE1CC"
    cut: str = "#8A664A"


@dataclass(frozen=True)
class IsoPiece:
    """Something that can hide what stands behind it: its ``name`` (a cell's ``block_3_4`` /
    ``wall_3_4``, an object's own), the box it stands in and its shapes back to front."""

    name: str
    box: Box3
    shapes: tuple[Shape, ...] = field(compare=False)


def _seed(column: int, row: int, salt: str = "") -> int:
    return zlib.crc32(f"{column}:{row}:{salt}".encode())


def _top(column: int, row: int, z: float) -> tuple[tuple[float, float, float], ...]:
    """A cell's top diamond at height ``z``, corners from the back clockwise (n, e, s, w)."""
    return ((column, row, z), (column + 1, row, z), (column + 1, row + 1, z), (column, row + 1, z))


def _surface(place: IsoPlace, colors: IsoColors, column: int, row: int) -> str:
    """The colour of a cell's top: grass, path or stone outdoors; floor or tiles indoors."""
    ground = place.ground(column, row)
    if place.indoor:
        return colors.tiles if ground == PATH else colors.floor
    if ground == PATH:
        return colors.path
    return colors.stone if ground == BLOCK else colors.grass


def _sides(place: IsoPlace, colors: IsoColors, column: int, row: int) -> str:
    """The colour of the sides under a cell's top: earth under grass and paths, stone under a
    stone block; indoors the floor's wood, darker."""
    if place.indoor:
        return shade(colors.floor, 0.18)
    return colors.stone if place.ground(column, row) == BLOCK else colors.earth


def _details(place: IsoPlace, colors: IsoColors, column: int, row: int, z: float) -> list[Shape]:
    """What lies on a cell's top: tufts of grass, stones in a path, the seams of floorboards,
    placed by the cell (the same in every render)."""
    ground = place.ground(column, row)
    seed = _seed(column, row)
    found: list[Shape] = []
    if place.indoor:
        if ground == PATH:
            return []
        for k in (1, 2):   # boards run along x, three to a cell, their ends staggered
            found.append(Line(((column + 0.02, row + k / 3, z), (column + 0.98, row + k / 3, z)), shade(colors.floor, 0.14), 0.55))
        cut = column + 0.25 + (seed % 50) / 100
        found.append(Line(((cut, row + 0.36, z), (cut, row + 0.64, z)), shade(colors.floor, 0.14), 0.55))
        return found
    if ground == PATH:
        for k in range(2):
            s = seed >> (8 * k)
            x, y = column + 0.2 + (s % 60) / 100, row + 0.2 + ((s >> 6) % 60) / 100
            found.append(Disc((x, y, z), 0.09 + (s >> 12) % 4 * 0.015, mix(colors.path, "#FFFFFF", 0.35), False))
        return found
    if ground == FLOOR and seed % 3 != 0:
        x, y = column + 0.2 + (seed % 60) / 100, row + 0.2 + ((seed >> 6) % 60) / 100
        tuft = shade(colors.grass, 0.22)
        found += [Line(((x - 0.05, y + 0.05, z + 0.12), (x, y, z), (x + 0.05, y - 0.05, z + 0.12)), tuft, 0.6),
                  Line(((x, y, z), (x, y, z + 0.16)), tuft, 0.6)]
    return found


def ground_shapes(place: IsoPlace, colors: IsoColors) -> list[Shape]:
    """The flat ground (height 0, back to front): each cell's top with what lies on it, water
    sunk below its banks, the slab's sides along the place's open front edges and the outline
    along its back edges. Raised cells are pieces (:func:`place_pieces`)."""
    shapes: list[Shape] = []
    ink = CHARACTER_INK
    cells = sorted(((c, r) for r in range(place.rows) for c in range(place.columns)), key=lambda cr: (cr[0] + cr[1], cr[0]))
    for c, r in cells:
        cell = place.cell(c, r)
        if cell.ground == VOID or cell.steps > 0:
            continue
        open_n, open_w = place.ground(c, r - 1) == VOID, place.ground(c - 1, r) == VOID
        open_s, open_e = place.ground(c, r + 1) == VOID, place.ground(c + 1, r) == VOID
        if cell.ground == WATER:
            shapes.append(Poly(_top(c, r, -WATER_DEPTH), colors.water, False))
            bank = _sides(place, colors, c, r)
            if place.ground(c, r - 1) not in (WATER, VOID):
                shapes.append(Poly(((c, r, 0.0), (c + 1, r, 0.0), (c + 1, r, -WATER_DEPTH), (c, r, -WATER_DEPTH)), shade(bank, 0.1), False))
                shapes.append(Line(((c, r, 0.0), (c + 1, r, 0.0)), ink, 0.9))
            if place.ground(c - 1, r) not in (WATER, VOID):
                shapes.append(Poly(((c, r, 0.0), (c, r + 1, 0.0), (c, r + 1, -WATER_DEPTH), (c, r, -WATER_DEPTH)), shade(bank, 0.25), False))
                shapes.append(Line(((c, r, 0.0), (c, r + 1, 0.0)), ink, 0.9))
            seed = _seed(c, r, "wave")
            if seed % 2:
                x, y = c + 0.25 + (seed >> 3) % 40 / 100, r + 0.3 + (seed >> 9) % 40 / 100
                shapes.append(Line(((x, y, -WATER_DEPTH), (x + 0.22, y - 0.22, -WATER_DEPTH)), mix(colors.water, "#FFFFFF", 0.55), 0.9))
        else:
            color = _surface(place, colors, c, r)
            if not place.indoor and (c + r) % 2:
                color = shade(color, 0.035)
            elif place.indoor and cell.ground == PATH and (c + r) % 2:
                color = shade(color, 0.12)
            shapes.append(Poly(_top(c, r, 0.0), color, (open_n, open_e, open_s, open_w)))
            if place.ground(c, r) not in WALLS:
                shapes += _details(place, colors, c, r, 0.0)
        sides = _sides(place, colors, c, r)
        # the slab's faces join their neighbours' along the edge: an outline only at its ends
        if open_s:
            shapes.append(Poly(((c, r + 1, 0.0), (c + 1, r + 1, 0.0), (c + 1, r + 1, -SLAB_DEPTH), (c, r + 1, -SLAB_DEPTH)), shade(sides, 0.1),
                               (True, open_e or not _open_south(place, c + 1, r), True, not _open_south(place, c - 1, r))))
        if open_e:
            shapes.append(Poly(((c + 1, r + 1, 0.0), (c + 1, r, 0.0), (c + 1, r, -SLAB_DEPTH), (c + 1, r + 1, -SLAB_DEPTH)), shade(sides, 0.24),
                               (True, not _open_east(place, c, r - 1), True, open_s or not _open_east(place, c, r + 1))))
    return shapes


def _open_south(place: IsoPlace, column: int, row: int) -> bool:
    """Whether the cell is in the place with nothing in front of it to the lower left."""
    return place.ground(column, row) != VOID and place.ground(column, row + 1) == VOID


def _open_east(place: IsoPlace, column: int, row: int) -> bool:
    """Whether the cell is in the place with nothing in front of it to the lower right."""
    return place.ground(column, row) != VOID and place.ground(column + 1, row) == VOID


def _neighbour_bottom(place: IsoPlace, column: int, row: int) -> float:
    """Where a face down from a raised cell towards (``column``, ``row``) ends: that cell's top,
    the water's surface, or the slab's bottom outside the place."""
    ground = place.ground(column, row)
    if ground == VOID:
        return -SLAB_DEPTH
    if ground == WATER:
        return -WATER_DEPTH
    return place.floor_z(column, row)


def _block(place: IsoPlace, colors: IsoColors, column: int, row: int) -> IsoPiece:
    """A raised cell: its top and the faces down to its lower neighbours, joined to neighbours
    of the same height (one terrace, no seams); grass hangs a little over its edges."""
    z = place.floor_z(column, row)
    steps = place.cell(column, row).steps
    near = {"n": (column, row - 1), "e": (column + 1, row), "s": (column, row + 1), "w": (column - 1, row)}
    joined = [side for side, (c, r) in near.items()
              if place.ground(c, r) not in WALLS and place.ground(c, r) not in (VOID, WATER) and place.cell(c, r).steps == steps]
    top = _surface(place, colors, column, row)
    sides = _sides(place, colors, column, row)
    bottoms = (_neighbour_bottom(place, *near["s"]), _neighbour_bottom(place, *near["e"]))
    shapes: list[Shape] = box_shapes(column, row, 0.0, column + 1, row + 1, z, top, left=shade(sides, 0.1), right=shade(sides, 0.24),
                                     joined=joined, bottoms=bottoms)
    grassy = not place.indoor and place.ground(column, row) in (FLOOR,)
    if grassy:   # a lip of grass over the faces
        lip = 0.13
        if "s" not in joined and z > bottoms[0]:
            shapes.append(Poly(((column, row + 1, z), (column + 1, row + 1, z), (column + 1, row + 1, z - lip), (column, row + 1, z - lip)),
                               shade(colors.grass, 0.12), (False, False, False, False)))
        if "e" not in joined and z > bottoms[1]:
            shapes.append(Poly(((column + 1, row + 1, z), (column + 1, row, z), (column + 1, row, z - lip), (column + 1, row + 1, z - lip)),
                               shade(colors.grass, 0.24), (False, False, False, False)))
    elif place.ground(column, row) == BLOCK and not place.indoor:
        for side, (dc, dr) in (("s", (0, 1)), ("e", (1, 0))):   # stone courses on the faces
            if side in joined:
                continue
            bottom = bottoms[0 if side == "s" else 1]
            level = z - 0.25
            while level > bottom + 0.1:
                if side == "s":
                    shapes.append(Line(((column + 0.04, row + 1, level), (column + 0.96, row + 1, level)), shade(sides, 0.3), 0.5))
                else:
                    shapes.append(Line(((column + 1, row + 0.96, level), (column + 1, row + 0.04, level)), shade(sides, 0.4), 0.5))
                level -= 0.25
    shapes += _details(place, colors, column, row, z)
    low = min(0.0, *bottoms)
    return IsoPiece(f"block_{column + 1}_{row + 1}", Box3(column, row, low, column + 1, row + 1, z), tuple(shapes))


def _wall(place: IsoPlace, colors: IsoColors, column: int, row: int) -> IsoPiece | None:
    """A wall's cell: a core standing in from the cell's sides (flush with the place's edge) and
    an arm to each wall it joins, so runs, corners and crossings read as one wall; indoors a
    standing back wall with its skirting, window or door on the faces that look into the room,
    or a cut-away wall showing its cut on top; outdoors a stone wall with a cap."""
    height = place.wall_height(column, row)
    if height <= 0.0:
        return None   # a doorway in a cut-away wall, a gate in a garden wall: a way through
    base = place.floor_z(column, row)
    top_z = base + height
    near = {"n": (column, row - 1), "e": (column + 1, row), "s": (column, row + 1), "w": (column - 1, row)}
    joined = {side for side, (c, r) in near.items() if place.ground(c, r) in WALLS and place.floor_z(c, r) == base
              and abs(place.wall_height(c, r) - height) < 1e-9}
    inset = {side: 0.0 if place.ground(*near[side]) == VOID else WALL_INSET for side in near}
    cx0, cy0, cx1, cy1 = column + inset["w"], row + inset["n"], column + 1 - inset["e"], row + 1 - inset["s"]
    boxes = [(("n", "s"), (cx0, row, cx1, cy0)) if "n" in joined and inset["n"] else None,
             (("w", "e"), (column, cy0, cx0, cy1)) if "w" in joined and inset["w"] else None,
             (tuple(joined), (cx0, cy0, cx1, cy1)),
             (("w", "e"), (cx1, cy0, column + 1, cy1)) if "e" in joined and inset["e"] else None,
             (("n", "s"), (cx0, cy1, cx1, row + 1)) if "s" in joined and inset["s"] else None]
    if place.indoor:
        face = colors.wall
        cap = colors.cut if place.is_cut(column, row) else shade(colors.wall, 0.3)
    else:
        face, cap = colors.stone, mix(colors.stone, "#FFFFFF", 0.25)
    shapes: list[Shape] = []
    lows = [base]
    for found in boxes:
        if found is None:
            continue
        sides, (x0, y0, x1, y1) = found
        # a face on the cell's edge goes down to what is in front (the slab outside the place)
        bottoms = (min(base, _neighbour_bottom(place, *near["s"])) if y1 == row + 1 else base,
                   min(base, _neighbour_bottom(place, *near["e"])) if x1 == column + 1 else base)
        lows += bottoms
        shapes += box_shapes(x0, y0, base, x1, y1, top_z, cap, left=shade(face, 0.06), right=shade(face, 0.2), joined=sides, bottoms=bottoms)
    # the faces to the lower left and lower right, from end to end of the cell's wall
    fx0, fx1 = (column if "w" in joined else cx0), (column + 1 if "e" in joined else cx1)
    fy0, fy1 = (row if "n" in joined else cy0), (row + 1 if "s" in joined else cy1)
    inside = {side: place.ground(*near[side]) not in WALLS and place.ground(*near[side]) != VOID for side in ("s", "e")}
    if place.indoor and not place.is_cut(column, row):
        skirting = shade(colors.floor, 0.3)
        if inside["s"]:
            shapes.append(Poly(((fx0, cy1, base), (fx1, cy1, base), (fx1, cy1, base + SKIRTING), (fx0, cy1, base + SKIRTING)), skirting,
                               (False, "e" not in joined, True, "w" not in joined)))
        if inside["e"]:
            shapes.append(Poly(((cx1, fy1, base), (cx1, fy0, base), (cx1, fy0, base + SKIRTING), (cx1, fy1, base + SKIRTING)), shade(skirting, 0.12),
                               (False, "n" not in joined, True, "s" not in joined)))
        ground = place.ground(column, row)
        for side in ("s", "e"):
            if inside[side] and ground == WINDOW:
                shapes += _wall_window(side, column, row, cx1, cy1, base)
            elif inside[side] and ground == DOOR:
                shapes += _wall_door(side, column, row, cx1, cy1, base)
    elif not place.indoor:
        for side in ("s", "e"):   # stone courses on the faces that show
            if side in joined:
                continue
            level = top_z - 0.3
            while level > base + 0.1:
                if side == "s":
                    shapes.append(Line(((fx0 + 0.04, cy1, level), (fx1 - 0.04, cy1, level)), shade(face, 0.3), 0.5))
                else:
                    shapes.append(Line(((cx1, fy1 - 0.04, level), (cx1, fy0 + 0.04, level)), shade(face, 0.38), 0.5))
                level -= 0.3
    return IsoPiece(f"wall_{column + 1}_{row + 1}", Box3(fx0, fy0, min(lows), fx1, fy1, top_z), tuple(shapes))


def _on_face(side: str, column: int, row: int, x1: float, y1: float, base: float, u0: float, u1: float, z0: float, z1: float) -> tuple:
    """A rectangle on a wall's face: across the face from ``u0`` to ``u1`` (0..1 of the cell,
    left to right as seen), from ``z0`` to ``z1`` over the base."""
    if side == "s":
        return ((column + u0, y1, base + z0), (column + u1, y1, base + z0), (column + u1, y1, base + z1), (column + u0, y1, base + z1))
    return ((x1, row + 1 - u0, base + z0), (x1, row + 1 - u1, base + z0), (x1, row + 1 - u1, base + z1), (x1, row + 1 - u0, base + z1))


def _wall_window(side: str, column: int, row: int, x1: float, y1: float, base: float) -> list[Shape]:
    outer = _on_face(side, column, row, x1, y1, base, 0.14, 0.86, WINDOW_SILL, WINDOW_TOP)
    inner = _on_face(side, column, row, x1, y1, base, 0.2, 0.8, WINDOW_SILL + 0.06, WINDOW_TOP - 0.06)
    mid = (WINDOW_SILL + WINDOW_TOP) / 2
    bar_v = _on_face(side, column, row, x1, y1, base, 0.5, 0.5, WINDOW_SILL + 0.06, WINDOW_TOP - 0.06)
    bar_h = _on_face(side, column, row, x1, y1, base, 0.2, 0.8, mid, mid)
    sill = _on_face(side, column, row, x1, y1, base, 0.1, 0.9, WINDOW_SILL - 0.07, WINDOW_SILL)
    return [Poly(outer, FRAME), Poly(inner, GLASS, False), Line((bar_v[0], bar_v[3]), FRAME, 1.3), Line((bar_h[0], bar_h[1]), FRAME, 1.3),
            Poly(sill, shade(FRAME, 0.15))]


def _wall_door(side: str, column: int, row: int, x1: float, y1: float, base: float) -> list[Shape]:
    door = _on_face(side, column, row, x1, y1, base, 0.15, 0.85, 0.0, DOOR_HEIGHT - 0.25)
    knob = _on_face(side, column, row, x1, y1, base, 0.72, 0.72, 1.05, 1.05)[0]
    panel = _on_face(side, column, row, x1, y1, base, 0.27, 0.73, 1.35, DOOR_HEIGHT - 0.45)
    return [Poly(door, WOOD), Poly(panel, shade(WOOD, 0.18), False), Disc(knob, 0.05, "#F2C14E", False)]


def place_pieces(place: IsoPlace, colors: IsoColors, looks: Mapping[str, ObjectLook]) -> list[IsoPiece]:
    """The place's pieces: each raised cell, each wall that stands (not a doorway) and each
    object (``looks``: its colours by name; a walkable rug or bridge too, it lies on top)."""
    pieces: list[IsoPiece] = []
    for r in range(place.rows):
        for c in range(place.columns):
            ground = place.ground(c, r)
            if ground in WALLS:
                wall = _wall(place, colors, c, r)
                if wall is not None:
                    pieces.append(wall)
            elif ground != VOID and ground != WATER and place.cell(c, r).steps > 0:
                pieces.append(_block(place, colors, c, r))
    for item in place.objects:
        base = place.floor_z(item.column, item.row)
        pieces.append(IsoPiece(item.name, object_box(item, base), tuple(object_shapes(item, looks[item.name], base))))
    return pieces


__all__ = ["SLAB_DEPTH", "WATER_DEPTH", "IsoColors", "IsoPiece", "ground_shapes", "place_pieces"]
