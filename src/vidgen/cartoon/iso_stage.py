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
from collections import OrderedDict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

from vidgen.cartoon.iso_drawing import ISO_SUPERSAMPLE, IsoCanvas, Shape, canvas_for, draw_shapes
from vidgen.cartoon.iso_objects import ObjectLook, object_box
from vidgen.cartoon.iso_scenery import SLAB_DEPTH, IsoColors, IsoPiece, ground_shapes, place_pieces
from vidgen.cartoon.stage import MAX_ZOOM, StageItem, StagePlacement
from vidgen.errors import VidgenError
from vidgen.world.iso import ISO_CHARACTER_HEIGHT, OBJECT_KINDS, VOID, IsoPlace, ObjectState, default_state
from vidgen.world.iso_view import ISO_RISE, Box3, draw_order, in_front, iso_point

#: Room left around the place in the frame, a share of the frame's width and height each side.
ISO_MARGIN = 0.05
#: Half the width of the box a character stands in, for the draw order (tile units).
ISO_BODY_HALF = 0.25


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


#: Where in its cell a small thing put on an object stands, when not in the middle: on a well's
#: rim at the front (its middle is the water).
TOP_SPOTS: dict[str, tuple[float, float]] = {"well": (0.79, 0.79)}


def iso_item_point(place: IsoPlace, at: str) -> tuple[float, float, float]:
    """Where a small thing put at the spot ``at`` stands (tile units, DESIGN.md §89.10): on the
    top of an object standing there that things go on (a table, a bench, a well's rim), in the
    middle of the spot's cell; else in the middle of the spot's cell on the ground (or of the
    nearest free cell when an object stands there)."""
    spot = place.spot(at)
    item = place.object_at(spot.column, spot.row)
    top = OBJECT_KINDS[item.kind].top if item is not None else None
    if item is not None and top is not None:
        dx, dy = TOP_SPOTS.get(item.kind, (0.5, 0.5))
        return (spot.column + dx, spot.row + dy, place.floor_z(item.column, item.row) + top)
    return iso_stand(place, at)


def item_box(place: IsoPlace, feet: tuple[float, float, float], height: float) -> Box3:
    """The box a small thing with its bottom at ``feet`` and ``height`` tall stands in (tile
    units): :func:`standing_box`, and on an object it is put on (a table) over that object's box,
    so it is drawn over it."""
    box = standing_box(place, feet, height)
    item = place.object_at(math.floor(feet[0]), math.floor(feet[1]))
    if item is None or item.walkable or OBJECT_KINDS[item.kind].top is None or feet[2] <= place.floor_z(item.column, item.row) + 1e-9:
        return box
    top = object_box(item, place.floor_z(item.column, item.row)).z1
    return Box3(box.x0, box.y0, max(box.z0, top), box.x1, box.y1, max(box.z1, top + height))


#: A ``follow`` on an iso place zooms in until a character is this share of the frame's shorter
#: side tall (as on a plain stage), unless the camera is closer already (DESIGN.md §89.10).
ISO_FOLLOW_SIZE = 0.45


def follow_width(character_height: float, frame_width: float, frame_height: float, view_width: float) -> float:
    """The view's width (Manim units) a ``follow`` of a character ``character_height`` tall on
    screen (at the establishing view) moves to: zoomed in to :data:`ISO_FOLLOW_SIZE`, at most
    to :data:`~vidgen.cartoon.stage.MAX_ZOOM`, never wider than ``view_width`` (the camera's
    now)."""
    zoom = ISO_FOLLOW_SIZE * min(frame_width, frame_height) / max(character_height, 1e-9)
    return min(view_width, frame_width / min(max(zoom, 1.0), MAX_ZOOM))


def iso_layout(place: IsoPlace, items: Sequence[StageItem], *, frame_width: float, frame_height: float) -> list[StagePlacement]:
    """Where each character and small thing stands on the place, back to front (like
    :func:`~vidgen.cartoon.stage.stage_layout`, all at depth 0): its feet in Manim units on its
    spot's cell (a small thing on the top of a table standing there, :func:`iso_item_point`), its
    height :data:`ISO_CHARACTER_HEIGHT` tiles times its ``scale`` (a prop's: its height next to a
    character). :class:`VidgenError` for an ``at`` that is not a spot."""
    view = iso_view(place, frame_width, frame_height)
    found = []
    for index, item in enumerate(items):
        if not isinstance(item.at, str) or item.at not in place.spot_names():
            raise VidgenError(f"'{item.name}' stands at '{item.at}', which is not a spot of the place "
                              f"(spots: {', '.join(place.spot_names()) or 'none'}); put a letter on the map for it")
        feet = iso_item_point(place, item.at) if item.kind == "prop" else iso_stand(place, item.at)
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
#: The pictures are drawn in square tiles this many pixels wide (each overlapping the next by
#: :data:`TILE_OVERLAP` pixels: a resampled picture's edge is half transparent and showed a seam),
#: at levels of detail: level ``k`` has 2**k times the pixels of level 0, up to
#: :data:`MAX_DETAIL` (DESIGN.md §89.10). A camera zoomed in shows the tiles of the level as sharp
#: as its view needs, and only those in view are drawn (once, kept in :data:`TILE_CACHE`).
TILE_PIXELS = 512
TILE_OVERLAP = 2
MAX_DETAIL = 3
#: A level of detail is used up to a zoom this much over its own (a little blur is not seen).
DETAIL_SLACK = 1.1
#: How many tiles a scenery keeps drawn (about 1 MB each).
TILE_CACHE = 320

#: A picture of the scenery: whether it has the ground, and the pieces in it (indices into
#: :attr:`IsoScenery.pieces`, in draw order) with the state each is drawn in.
Picture = tuple[bool, tuple[tuple[int, ObjectState], ...]]


def detail_for(zoom: float, density: float) -> int:
    """The level of detail for a camera ``zoom`` (1: the establishing view) when level 0 has
    ``density`` pixels per frame pixel: the least that is sharp enough, at most :data:`MAX_DETAIL`."""
    level = 0
    while level < MAX_DETAIL and density * 2**level * DETAIL_SLACK < zoom:
        level += 1
    return level


class IsoScenery:
    """An iso place drawn into pictures (DESIGN.md §89.7, §89.9, §89.10): the *base*, the ground
    and every piece in draw order (behind the characters, drawn first); for a character standing
    in a box a *front* picture of the pieces drawn over it (:meth:`front`: drawn right after it,
    so what stands in front of it hides it); and for each object the scene changes (``layered``:
    a door opens, a lamp lights, a bridge appears) a *layer* of it with the pieces over it
    (:meth:`layer`), drawn right after the base, which leaves it out. ``states``: how the objects
    are at the start (:class:`~vidgen.world.iso.ObjectState`); :meth:`set_state` changes one.

    A picture is drawn in tiles (:meth:`tiles`, :meth:`tile_image`) on the canvas of a level of
    detail (:func:`detail_for`); a front or a layer covers just its pieces (whole pixels of the
    canvas), so its pixels fall on the base's and no seam shows. A piece in a front picture or a
    layer is in the base too (but a layered one), so where its edge meets the base no seam shows."""

    def __init__(self, place: IsoPlace, colors: IsoColors, looks: Mapping[str, ObjectLook], view: IsoView, pixels_per_unit: float,
                 *, outline: float = 1.0, states: Mapping[str, ObjectState] | None = None, layered: Collection[str] = ()) -> None:
        pieces = place_pieces(place, colors, looks)
        self.view = view
        self.bounds = place_bounds(place)
        #: pixels per tile width at level 0
        self.scale = view.unit * pixels_per_unit
        self.outline = outline
        #: the pieces in draw order
        self.pieces = [pieces[k] for k in draw_order([p.box for p in pieces])]
        self.index = {piece.name: k for k, piece in enumerate(self.pieces)}
        self.ground = tuple(ground_shapes(place, colors))
        #: each piece's state now (a block or a wall: as drawn)
        self.states: dict[int, ObjectState] = {k: (states or {}).get(piece.name, default_state(piece.kind or "")) for k, piece in enumerate(self.pieces)}
        self.layered = tuple(k for k, piece in enumerate(self.pieces) if piece.name in layered)
        self._images: OrderedDict[tuple[Any, ...], Image.Image | None] = OrderedDict()
        self._glows: dict[Picture, bool] = {}

    @property
    def canvas(self) -> IsoCanvas:
        """The whole place's canvas at level 0."""
        return self.level_canvas(0)

    def level_canvas(self, level: int) -> IsoCanvas:
        """The whole place's canvas at a level of detail."""
        return canvas_for(self.bounds, self.scale * 2**level, margin=0.1)

    def shown(self, k: int) -> bool:
        return self.states[k].shown

    def set_state(self, name: str, state: ObjectState) -> None:
        """Change the object (or map door) ``name`` to ``state`` from now on."""
        self.states[self.index[name]] = state

    def over(self, box: Box3) -> tuple[int, ...]:
        """Which pieces (indices into :attr:`pieces`) are drawn over a character standing in ``box``."""
        return tuple(_over(self.pieces, box))

    def _entries(self, ks: Collection[int]) -> tuple[tuple[int, ObjectState], ...]:
        return tuple((k, self.states[k]) for k in sorted(ks) if self.shown(k))

    def base(self) -> Picture:
        """The base picture: the ground and every piece there now but the layered ones."""
        return (True, self._entries([k for k in range(len(self.pieces)) if k not in self.layered]))

    def front(self, box: Box3) -> Picture | None:
        """The front picture of a character standing in ``box`` (``None``: nothing hides it)."""
        found = self._entries(self.over(box))
        return (False, found) if found else None

    def layer(self, name: str) -> Picture | None:
        """The layer of the layered piece ``name``: it as it is now, with the pieces over it
        (``None``: it is not there now)."""
        k = self.index[name]
        if not self.shown(k):
            return None
        return (False, self._entries({k, *(j for j in _over(self.pieces, self.pieces[k].box) if j != k)}))

    def clip(self, picture: Picture) -> tuple[float, float, float, float] | None:
        """The picture bounds (tile widths) a front or a layer covers (``None``: the whole canvas)."""
        if picture[0]:
            return None
        bounds = [self.pieces[k].box.picture_bounds() for k, _ in picture[1]]
        return (min(b[0] for b in bounds) - FRONT_MARGIN, min(b[1] for b in bounds) - FRONT_MARGIN,
                max(b[2] for b in bounds) + FRONT_MARGIN, max(b[3] for b in bounds) + FRONT_MARGIN)

    def tiles(self, picture: Picture, level: int, view: tuple[float, float, float, float] | None = None) -> list[tuple[tuple[int, int], IsoCanvas]]:
        """The tiles of ``picture`` at ``level`` that ``view`` (picture bounds in tile widths:
        left, top, right, bottom; ``None``: all of it) shows: ``((column, row), the part of the
        level's canvas)``, left to right, top to bottom."""
        c = self.level_canvas(level)
        x0, y0, x1, y1 = 0, 0, c.width, c.height
        clip = self.clip(picture)
        for bounds in (clip, view):
            if bounds is not None:
                x0, y0 = max(x0, math.floor((bounds[0] - c.left) * c.scale)), max(y0, math.floor((bounds[1] - c.top) * c.scale))
                x1, y1 = min(x1, math.ceil((bounds[2] - c.left) * c.scale)), min(y1, math.ceil((bounds[3] - c.top) * c.scale))
        found = []
        if x1 <= x0 or y1 <= y0:
            return found
        for j in range(y0 // TILE_PIXELS, (y1 - 1) // TILE_PIXELS + 1):
            for i in range(x0 // TILE_PIXELS, (x1 - 1) // TILE_PIXELS + 1):
                tx0, ty0 = i * TILE_PIXELS, j * TILE_PIXELS
                tx1, ty1 = min(tx0 + TILE_PIXELS + TILE_OVERLAP, c.width), min(ty0 + TILE_PIXELS + TILE_OVERLAP, c.height)
                if clip is not None:   # a front or a layer: just its pieces' part of the tile
                    cx0, cy0 = math.floor((clip[0] - c.left) * c.scale), math.floor((clip[1] - c.top) * c.scale)
                    cx1, cy1 = math.ceil((clip[2] - c.left) * c.scale), math.ceil((clip[3] - c.top) * c.scale)
                    tx0, ty0, tx1, ty1 = max(tx0, cx0), max(ty0, cy0), min(tx1, cx1), min(ty1, cy1)
                if tx1 > tx0 and ty1 > ty0:
                    found.append(((i, j), IsoCanvas(c.scale, c.left + tx0 / c.scale, c.top + ty0 / c.scale, tx1 - tx0, ty1 - ty0)))
        return found

    def shapes(self, picture: Picture) -> list[Shape]:
        """What ``picture`` draws, back to front."""
        ground = list(self.ground) if picture[0] else []
        return ground + [shape for k, state in picture[1] for shape in self.pieces[k].shapes_in(state)]

    def glows(self, picture: Picture) -> bool:
        """Whether ``picture`` shows a light (a lit lamp or window, DESIGN.md §89.11)."""
        if picture not in self._glows:
            self._glows[picture] = any(getattr(shape, "glow", False) for k, state in picture[1] for shape in self.pieces[k].shapes_in(state))
        return self._glows[picture]

    def tile_image(self, picture: Picture, level: int, tile: tuple[int, int], canvas: IsoCanvas, *, glow: bool = False) -> Image.Image | None:
        """The tile ``tile`` of ``picture`` at ``level`` (its ``canvas`` from :meth:`tiles`),
        drawn once (``None``: nothing on it); ``glow``: of its lights only (DESIGN.md §89.11)."""
        key = (picture, level, tile, glow)
        if key in self._images:
            self._images.move_to_end(key)
            return self._images[key]
        image: Image.Image | None = draw_shapes(self.shapes(picture), canvas, outline=self.outline, supersample=ISO_SUPERSAMPLE, glow=glow)
        if image is not None and image.getbbox() is None:
            image = None
        self._images[key] = image
        while len(self._images) > TILE_CACHE:
            self._images.popitem(last=False)
        return image

    def picture(self, picture: Picture, level: int = 0, *, glow: bool = False) -> tuple[IsoCanvas, Image.Image]:
        """The whole of ``picture`` at ``level`` as one image, on its part of the canvas (for tests
        and stills; the stage draws tiles); ``glow``: of its lights only."""
        c = self.level_canvas(level)
        clip = self.clip(picture)
        if clip is None:
            part = c
        else:
            x0, y0 = max(math.floor((clip[0] - c.left) * c.scale), 0), max(math.floor((clip[1] - c.top) * c.scale), 0)
            x1, y1 = min(math.ceil((clip[2] - c.left) * c.scale), c.width), min(math.ceil((clip[3] - c.top) * c.scale), c.height)
            part = IsoCanvas(c.scale, c.left + x0 / c.scale, c.top + y0 / c.scale, max(x1 - x0, 1), max(y1 - y0, 1))
        return part, draw_shapes(self.shapes(picture), part, outline=self.outline, supersample=ISO_SUPERSAMPLE, glow=glow)


#: How many places across the picture :func:`place_outline` measures the place's edges at.
OUTLINE_SAMPLES = 256


def place_outline(place: IsoPlace, view: IsoView, samples: int = OUTLINE_SAMPLES) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """The place's ground as seen (Manim units): ``(xs, fronts, backs)``, at ``samples`` xs
    across it the lowest and the highest y of the tops of its cells there (a raised block's
    top, water's surface): where rain can land (DESIGN.md §89.11)."""
    cells = [(c, r, place.floor_z(c, r)) for r in range(place.rows) for c in range(place.columns) if place.ground(c, r) != VOID]
    if not cells:
        return (), (), ()
    corners = np.array([[view.point(c + dx, r + dy, z) for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 1))] for c, r, z in cells])
    back, right, front, left = (corners[:, k] for k in range(4))   # each (cells, 2): x, y
    xs = np.linspace(float(left[:, 0].min()), float(right[:, 0].max()), samples)
    x = xs[:, None]
    inside = (x >= left[None, :, 0]) & (x <= right[None, :, 0])
    on_left = x <= back[None, :, 0]   # the back and front corners share their x
    share_left = (x - left[None, :, 0]) / np.maximum(back[None, :, 0] - left[None, :, 0], 1e-9)
    share_right = (x - back[None, :, 0]) / np.maximum(right[None, :, 0] - back[None, :, 0], 1e-9)
    tops = np.where(on_left, left[None, :, 1] + share_left * (back[None, :, 1] - left[None, :, 1]),
                    back[None, :, 1] + share_right * (right[None, :, 1] - back[None, :, 1]))
    bottoms = np.where(on_left, left[None, :, 1] + share_left * (front[None, :, 1] - left[None, :, 1]),
                       front[None, :, 1] + share_right * (right[None, :, 1] - front[None, :, 1]))
    highs = np.where(inside, tops, -np.inf).max(axis=1)
    lows = np.where(inside, bottoms, np.inf).min(axis=1)
    found = np.isfinite(highs) & np.isfinite(lows)
    return tuple(xs[found].tolist()), tuple(lows[found].tolist()), tuple(highs[found].tolist())


def iso_canvas(place: IsoPlace, view: IsoView, pixels_per_unit: float) -> IsoCanvas:
    """The canvas the place is drawn on: its bounds at ``pixels_per_unit`` (pixels per Manim unit)."""
    return canvas_for(place_bounds(place), view.unit * pixels_per_unit, margin=0.1)


def canvas_center(canvas: IsoCanvas, view: IsoView) -> tuple[float, float]:
    """The middle of ``canvas`` in Manim units (where its picture goes)."""
    u = canvas.left + canvas.width / canvas.scale / 2
    v = canvas.top + canvas.height / canvas.scale / 2
    return ((u - view.u0) * view.unit, -(v - view.v0) * view.unit)


__all__ = [
    "DETAIL_SLACK",
    "ISO_BODY_HALF",
    "ISO_FOLLOW_SIZE",
    "MAX_DETAIL",
    "TILE_CACHE",
    "TILE_OVERLAP",
    "TILE_PIXELS",
    "Picture",
    "detail_for",
    "follow_width",
    "item_box",
    "iso_item_point",
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
    "OUTLINE_SAMPLES",
    "place_bounds",
    "place_outline",
    "standing_box",
    "pieces_in_front",
]
