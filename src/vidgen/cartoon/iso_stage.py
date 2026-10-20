"""An isometric place on a ``stage`` (DESIGN.md §89): from the world's tile units to Manim units,
where the characters stand, and the place drawn into a few pictures split around them. No manim.

The whole place fits the frame (its establishing view): :func:`iso_view` scales the picture of
the map, its raised blocks, walls and objects, and room for a character on every cell, into the
frame with a margin. A character stands upright in the middle of its cell, :data:`~vidgen.world.iso.ISO_CHARACTER_HEIGHT`
tiles tall: no perspective, so it is the same size wherever it stands (no ``depth``).

The scenery is drawn into pictures (:class:`IsoScenery`): the flat ground and every piece
(blocks, walls, objects) in draw order into one, drawn behind the characters, and for each
character a *front picture* with just the pieces that hide part of it, drawn right after it. As
a character walks the pieces in front of it change, and the stage swaps its front picture
(DESIGN.md §89.9).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from PIL import Image

from vidgen.cartoon.iso_drawing import ISO_SUPERSAMPLE, IsoCanvas, Shape, canvas_for, draw_shapes
from vidgen.cartoon.iso_objects import ObjectLook, object_box
from vidgen.cartoon.iso_scenery import SLAB_DEPTH, IsoColors, IsoPiece, ground_shapes, place_pieces
from vidgen.cartoon.stage import StageItem, StagePlacement
from vidgen.errors import VidgenError
from vidgen.world.iso import ISO_CHARACTER_HEIGHT, VOID, IsoPlace
from vidgen.world.iso_view import ISO_RISE, Box3, draw_order, in_front, iso_point

#: Room left around the place in the frame, a share of the frame's width and height each side.
ISO_MARGIN = 0.05
#: Half the width of the box a character stands in, for the draw order (tile units).
ISO_BODY_HALF = 0.25
#: The most pixels a drawing may have while supersampled (memory): fewer supersamples above it.
ISO_MAX_DRAW_PIXELS = 40_000_000


@dataclass(frozen=True)
class IsoView:
    """Where the place lies in the frame: ``unit`` Manim units per tile width of the picture, and
    the picture point (``u0``, ``v0``) at the frame's centre."""

    unit: float
    u0: float
    v0: float

    def point(self, x: float, y: float, z: float = 0.0) -> tuple[float, float]:
        """A world point (tile units) in Manim units (``y`` up)."""
        u, v = iso_point(x, y, z)
        return ((u - self.u0) * self.unit, -(v - self.v0) * self.unit)

    def height(self, tiles: float) -> float:
        """An upright height (tile units) in Manim units."""
        return tiles * ISO_RISE * self.unit


def place_bounds(place: IsoPlace) -> tuple[float, float, float, float]:
    """The picture bounds (tile widths: left, top, right, bottom) of the place: each cell with the
    slab under it up to its wall's top or a character standing on it, and its objects."""
    boxes = [object_box(item, place.floor_z(item.column, item.row)) for item in place.objects]
    for r in range(place.rows):
        for c in range(place.columns):
            if place.ground(c, r) != VOID:
                z = place.floor_z(c, r)
                boxes.append(Box3(c, r, -SLAB_DEPTH, c + 1, r + 1, z + max(place.wall_height(c, r), ISO_CHARACTER_HEIGHT * 1.08)))
    found = [box.picture_bounds() for box in boxes]
    return min(b[0] for b in found), min(b[1] for b in found), max(b[2] for b in found), max(b[3] for b in found)


def iso_view(place: IsoPlace, frame_width: float, frame_height: float) -> IsoView:
    """The establishing view: the place (:func:`place_bounds`) as large as fits the frame with
    :data:`ISO_MARGIN` around it, centred."""
    left, top, right, bottom = place_bounds(place)
    unit = min(frame_width * (1 - 2 * ISO_MARGIN) / (right - left), frame_height * (1 - 2 * ISO_MARGIN) / (bottom - top))
    return IsoView(unit, (left + right) / 2, (top + bottom) / 2)


def map_fraction(place: IsoPlace, column: int, row: int) -> float:
    """Where a cell's middle is across the picture of the map, 0 (its left corner) to 1 (its
    right corner): a spot as a stage mark (frame-independent)."""
    u = iso_point(column + 0.5, row + 0.5)[0]
    left, right = -place.rows / 2, place.columns / 2
    return (u - left) / (right - left)


def iso_stand(place: IsoPlace, at: str) -> tuple[float, float, float]:
    """Where a character asked to stand at the spot ``at`` has its feet (tile units): the middle
    of its cell (:meth:`~vidgen.world.iso.IsoPlace.stand_cell`), on its top (a bridge's deck)."""
    column, row = place.stand_cell(at)
    return (column + 0.5, row + 0.5, place.stand_z(column, row))


def body_box(feet: tuple[float, float, float], height: float) -> Box3:
    """The box a character with its feet at ``feet`` and ``height`` tall stands in (tile units),
    kept inside the cell its feet are in: walking from cell to cell it is in one or the other,
    never inside a neighbour's block or object (the draw order would be in doubt)."""
    x, y, z = feet
    column, row = math.floor(x), math.floor(y)
    return Box3(max(x - ISO_BODY_HALF, column), max(y - ISO_BODY_HALF, row), z,
                min(x + ISO_BODY_HALF, column + 1), min(y + ISO_BODY_HALF, row + 1), z + height)


def standing_box(place: IsoPlace, feet: tuple[float, float, float], height: float) -> Box3:
    """:func:`body_box` of a character standing on ``place``: on a walkable object (a bridge, a
    rug) it counts as standing on top of all of it, so it is drawn over it (its low rails too)."""
    box = body_box(feet, height)
    item = place.object_at(math.floor(feet[0]), math.floor(feet[1]))
    if item is None or not item.walkable:
        return box
    top = object_box(item, place.floor_z(item.column, item.row)).z1
    return Box3(box.x0, box.y0, max(box.z0, top), box.x1, box.y1, max(box.z1, top + height))


def iso_layout(place: IsoPlace, items: Sequence[StageItem], *, frame_width: float, frame_height: float) -> list[StagePlacement]:
    """Where each character stands on the place, back to front (like
    :func:`~vidgen.cartoon.stage.stage_layout`, all at depth 0): its feet in Manim units on its
    spot's cell, its height :data:`ISO_CHARACTER_HEIGHT` tiles times its ``scale``.
    :class:`VidgenError` for an ``at`` that is not a spot."""
    view = iso_view(place, frame_width, frame_height)
    found = []
    for index, item in enumerate(items):
        if not isinstance(item.at, str) or item.at not in place.spot_names():
            raise VidgenError(f"'{item.name}' stands at '{item.at}', which is not a spot of the place "
                              f"(spots: {', '.join(place.spot_names()) or 'none'}); put a letter on the map for it")
        feet = iso_stand(place, item.at)
        x, y = view.point(*feet)
        found.append((feet[0] + feet[1], index, StagePlacement(
            name=item.name, kind=item.kind, index=index, x_fraction=x / frame_width + 0.5, depth=0.0, feet=(x, y),
            height=view.height(ISO_CHARACTER_HEIGHT * item.scale),
        )))
    return [placement for _, _, placement in sorted(found, key=lambda f: (f[0], f[1]))]


def _over(ordered: Sequence[IsoPiece], box: Box3) -> list[int]:
    """The indices into ``ordered`` (pieces in draw order) of those drawn over a body in ``box``:
    in front of it, or in front of one of these."""
    found: list[int] = []
    for k, piece in enumerate(ordered):
        if in_front(piece.box, box) is True or any(in_front(piece.box, ordered[near].box) is True for near in found):
            found.append(k)
    return found


def pieces_in_front(pieces: Sequence[IsoPiece], bodies: Sequence[tuple[str, Box3]]) -> tuple[list[IsoPiece], dict[str, list[IsoPiece]]]:
    """The pieces in draw order, and for each character of ``bodies`` (name, box) the pieces drawn
    over it (in draw order): those in front of it (:func:`~vidgen.world.iso_view.in_front`) and
    those in front of these, so a piece over the character is never drawn over a nearer one."""
    order = draw_order([p.box for p in pieces])
    ordered = [pieces[k] for k in order]
    return ordered, {name: [ordered[k] for k in _over(ordered, box)] for name, box in bodies}


#: Room (tile widths) around a front picture's pieces: drawings reach past their boxes.
FRONT_MARGIN = 0.5


class IsoScenery:
    """An iso place drawn on one ``canvas`` (DESIGN.md §89.7, §89.9): ``base``, the ground and every
    piece in draw order (behind the characters, drawn first), and on demand a *front picture* of
    the pieces drawn over a character standing in a box (:meth:`over`, :meth:`front`): drawn right
    after it, so what stands in front of it hides it. A front picture covers just its pieces (a
    part of the canvas, whole pixels of it) and is kept for when the same pieces hide someone
    again. A piece in a front picture is in the base too, so where its edge meets the base no
    seam shows."""

    def __init__(self, place: IsoPlace, colors: IsoColors, looks: Mapping[str, ObjectLook], view: IsoView, pixels_per_unit: float,
                 *, outline: float = 1.0) -> None:
        pieces = place_pieces(place, colors, looks)
        self.canvas = iso_canvas(place, view, pixels_per_unit)
        self.outline = outline
        self.supersample = ISO_SUPERSAMPLE
        while self.supersample > 1 and self.canvas.width * self.canvas.height * self.supersample**2 > ISO_MAX_DRAW_PIXELS:
            self.supersample -= 1
        #: the pieces in draw order
        self.pieces = [pieces[k] for k in draw_order([p.box for p in pieces])]
        shapes: list[Shape] = [*ground_shapes(place, colors), *(shape for piece in self.pieces for shape in piece.shapes)]
        self.base = draw_shapes(shapes, self.canvas, outline=outline, supersample=self.supersample)
        self._fronts: dict[tuple[int, ...], tuple[IsoCanvas, Image.Image]] = {}

    def over(self, box: Box3) -> tuple[int, ...]:
        """Which pieces (indices into :attr:`pieces`) are drawn over a character standing in ``box``."""
        return tuple(_over(self.pieces, box))

    def front(self, key: tuple[int, ...]) -> tuple[IsoCanvas, Image.Image]:
        """The front picture of the pieces ``key`` (from :meth:`over`, not empty): the part of the
        canvas it covers and the picture."""
        if key not in self._fronts:
            bounds = [self.pieces[k].box.picture_bounds() for k in key]
            c = self.canvas
            x0 = max(math.floor((min(b[0] for b in bounds) - FRONT_MARGIN - c.left) * c.scale), 0)
            y0 = max(math.floor((min(b[1] for b in bounds) - FRONT_MARGIN - c.top) * c.scale), 0)
            x1 = min(math.ceil((max(b[2] for b in bounds) + FRONT_MARGIN - c.left) * c.scale), c.width)
            y1 = min(math.ceil((max(b[3] for b in bounds) + FRONT_MARGIN - c.top) * c.scale), c.height)
            part = IsoCanvas(c.scale, c.left + x0 / c.scale, c.top + y0 / c.scale, max(x1 - x0, 1), max(y1 - y0, 1))
            shapes = [shape for k in key for shape in self.pieces[k].shapes]
            self._fronts[key] = (part, draw_shapes(shapes, part, outline=self.outline, supersample=self.supersample))
        return self._fronts[key]


def iso_canvas(place: IsoPlace, view: IsoView, pixels_per_unit: float) -> IsoCanvas:
    """The canvas the place is drawn on: its bounds at ``pixels_per_unit`` (pixels per Manim unit)."""
    return canvas_for(place_bounds(place), view.unit * pixels_per_unit, margin=0.1)


def canvas_center(canvas: IsoCanvas, view: IsoView) -> tuple[float, float]:
    """The middle of ``canvas`` in Manim units (where its picture goes)."""
    u = canvas.left + canvas.width / canvas.scale / 2
    v = canvas.top + canvas.height / canvas.scale / 2
    return ((u - view.u0) * view.unit, -(v - view.v0) * view.unit)


__all__ = [
    "ISO_BODY_HALF",
    "ISO_MARGIN",
    "FRONT_MARGIN",
    "IsoScenery",
    "IsoView",
    "body_box",
    "canvas_center",
    "iso_canvas",
    "iso_layout",
    "iso_stand",
    "iso_view",
    "map_fraction",
    "place_bounds",
    "standing_box",
    "pieces_in_front",
]
