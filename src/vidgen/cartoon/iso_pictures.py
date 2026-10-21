"""An iso place's pictures on the stage (DESIGN.md §89.10): each picture of an
:class:`~vidgen.cartoon.iso_stage.IsoScenery` (its base, a character's front picture, a layer of
an object that changes) is an :class:`IsoTiles` group showing the tiles the camera sees, at the
level of detail its zoom needs. Weather on the place (DESIGN.md §90): :class:`IsoPuddles` (puddles
growing in the rain, with ripples) and :class:`IsoSnow` (settling snow, shown by the pictures'
snow tiles).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from manim import Group, ImageMobject, Mobject, VGroup, VMobject
from PIL import Image

from vidgen.cartoon.iso_stage import IsoScenery, IsoView, Picture, canvas_center, detail_for
from vidgen.cartoon.iso_weather import RIPPLE_OPACITY, RIPPLE_WIDTH, RIPPLES, IsoPuddle, ripples
from vidgen.cartoon.rain import puddle_growth
from vidgen.cartoon.shading import LIT, mark_lit
from vidgen.cartoon.snow import BLANKET_OPACITY, blanket_cover, settle_amount, settled_seconds


class GlowTile(ImageMobject):
    """A tile of the lights of a picture (DESIGN.md §89.11): never graded by the stage's light,
    even when the group holding it is marked lit (:func:`~vidgen.cartoon.shading.mark_lit`), so
    a lit lamp or window glows at night."""

    @property
    def light_graded(self) -> bool:
        return False

    @light_graded.setter
    def light_graded(self, value: bool) -> None:
        pass


class IsoTiles(Group):
    """One picture of an iso place (``picture`` of ``scenery``), named ``name``: its members are
    the tiles in the camera's view (:meth:`show_view`) at the level of detail of the camera's
    zoom; ``density``: level 0's pixels per frame pixel. A tile is made once (kept for the
    scene), lit like the group (:func:`~vidgen.cartoon.shading.mark_lit`), and marked
    ``scenery`` (the camera crops it on purpose: lint ``off_frame``). While snow settles on the
    place (:meth:`set_snow_opacity`, DESIGN.md §90.3) each tile shows the snow lying on it at
    that opacity, laid over its pixels in place (the same mobject: a picture of the snow on its
    own, half seen through, showed the tiles' overlaps as lines). A picture with lights in it (a
    lit lamp or window) has their tiles too, after the others, never graded (:class:`GlowTile`,
    DESIGN.md §89.11)."""

    def __init__(self, scenery: IsoScenery, picture: Picture, view: IsoView, *, name: str, density: float, frame_width: float) -> None:
        super().__init__()
        self.scenery, self.picture, self.iso_view = scenery, picture, view
        self.name = name
        self.density = density
        self.frame_width = frame_width
        self.shown_key: tuple[int, tuple[tuple[int, int], ...]] | None = None
        self._tiles: dict[tuple[int, tuple[int, int], bool], ImageMobject | None] = {}
        #: the tiles' opacity (a place change fades a layer in or out, DESIGN.md §89.10)
        self.tile_opacity = 1.0
        #: how much of the settling snow shows (0..1, DESIGN.md §90.3)
        self.snow_opacity = 0.0
        #: each picture tile's own pixels and its snow's, while snow settles; the snow shown on it
        self._snow_sources: dict[int, tuple[np.ndarray, np.ndarray | None]] = {}
        self._snow_shown: dict[int, float] = {}

    def show_view(self, frame: Mobject) -> bool:
        """Keep as members the tiles that the camera ``frame`` shows (with a margin of half a
        view, so a moving camera rarely waits for a tile); whether they changed."""
        view = self.iso_view
        zoom = self.frame_width / max(float(frame.width), 1e-9)
        level = detail_for(zoom, self.density)
        cx, cy = float(frame.get_center()[0]), float(frame.get_center()[1])
        half_w, half_h = float(frame.width) * 0.75, float(frame.height) * 0.75
        left, right = view.u0 + (cx - half_w) / view.unit, view.u0 + (cx + half_w) / view.unit
        top, bottom = view.v0 - (cy + half_h) / view.unit, view.v0 - (cy - half_h) / view.unit
        tiles = self.scenery.tiles(self.picture, level, (left, top, right, bottom))
        key = (level, tuple(tile for tile, _ in tiles))
        if key == self.shown_key:
            return False
        self.shown_key = key
        members = []
        for glow in (False, True) if self.scenery.glows(self.picture) else (False,):
            for tile, canvas in tiles:
                if (level, tile, glow) not in self._tiles:
                    self._tiles[(level, tile, glow)] = self._make(level, tile, canvas, glow)
                made = self._tiles[(level, tile, glow)]
                if made is not None:
                    if not glow:
                        self._show_snow(made)
                    members.append(made)
        self.submobjects = members
        return True

    def _make(self, level: int, tile: tuple[int, int], canvas: Any, glow: bool = False) -> ImageMobject | None:
        image = self.scenery.tile_image(self.picture, level, tile, canvas, glow=glow)
        if image is None:
            return None
        made = (GlowTile if glow else ImageMobject)(np.array(image))
        made.scale_to_fit_width(canvas.width / canvas.scale * self.iso_view.unit)
        made.move_to([*canvas_center(canvas, self.iso_view), 0.0])
        made.name = self.name
        made.iso_pieces = tuple(self._piece_box(k) for k, _ in self.picture[1])   # what it shows, and where (lint, §89.11)
        made.scenery = True
        made.iso_tile = True   # drawn by :func:`draw_tile`
        made.iso_canvas = (level, tile, canvas)
        if self.tile_opacity < 1.0:
            made.set_opacity(self.tile_opacity)
        if getattr(self, LIT, False) and not glow:
            mark_lit(made)
        return made

    def _piece_box(self, k: int) -> tuple[str, tuple[float, float, float, float]]:
        """A piece's name and the box (Manim units: left, bottom, right, top) its box's picture covers."""
        piece, view = self.scenery.pieces[k], self.iso_view
        left, top, right, bottom = piece.box.picture_bounds()
        return piece.name, ((left - view.u0) * view.unit, -(bottom - view.v0) * view.unit, (right - view.u0) * view.unit, -(top - view.v0) * view.unit)

    def set_tile_opacity(self, opacity: float) -> None:
        """Show every tile (also those made later) at ``opacity`` (0..1)."""
        self.tile_opacity = opacity
        for made in self._tiles.values():
            if made is not None:
                made.set_opacity(opacity)

    def set_snow_opacity(self, opacity: float) -> None:
        """Show the snow lying on the picture at ``opacity`` (0..1): on the tiles shown now at
        once, on others when they are shown."""
        self.snow_opacity = opacity
        for made in self.picture_tiles():
            self._show_snow(made)

    def picture_tiles(self) -> list[ImageMobject]:
        """The members showing the picture (not its lights): what changes as snow settles."""
        return [m for m in self.submobjects if not isinstance(m, GlowTile)]

    def _show_snow(self, made: ImageMobject) -> None:
        """Lay the snow over the tile ``made``'s own pixels at :attr:`snow_opacity`, in place."""
        shown = self._snow_shown.get(id(made), 0.0)
        if shown == self.snow_opacity:
            return
        if id(made) not in self._snow_sources:
            level, tile, canvas = made.iso_canvas
            snow = self.scenery.tile_image(self.picture, level, tile, canvas, snow=True)
            self._snow_sources[id(made)] = (made.pixel_array.copy() if self.tile_opacity >= 1.0 else _own_pixels(made),
                                            None if snow is None else np.array(snow))
        own, snow = self._snow_sources[id(made)]
        self._snow_shown[id(made)] = self.snow_opacity
        if snow is None:
            return
        cover = snow.copy()
        cover[:, :, 3] = np.round(cover[:, :, 3] * self.snow_opacity).astype(np.uint8)
        made.pixel_array = np.array(Image.alpha_composite(Image.fromarray(own, "RGBA"), Image.fromarray(cover, "RGBA")))
        made.orig_alpha_pixel_array = made.pixel_array[:, :, 3].copy()
        if self.tile_opacity < 1.0:
            made.set_opacity(self.tile_opacity)


def _own_pixels(made: ImageMobject) -> np.ndarray:
    """A tile's pixels at full opacity (its alpha as made)."""
    pixels = made.pixel_array.copy()
    pixels[:, :, 3] = made.orig_alpha_pixel_array
    return pixels


#: A puddle on an iso place: a light blue of the sky it mirrors, a little seen through (seen from
#: above, the plain stage's darker puddles read as holes in the grass); its ripples lighter still.
ISO_PUDDLE_COLOR = "#A9C8E8"
ISO_PUDDLE_OPACITY = 0.8
RIPPLE_COLOR = "#EEF4FB"
#: Corners of a puddle's or a ripple's ellipse.
_ELLIPSE_CORNERS = 28


def _ellipse(cx: float, cy: float, a: float, b: float, reverse: bool = False) -> np.ndarray:
    angles = np.linspace(0.0, 2 * math.pi, _ELLIPSE_CORNERS + 1)
    if reverse:
        angles = angles[::-1]
    return np.stack([cx + a * np.cos(angles), cy + b * np.sin(angles), np.zeros_like(angles)], axis=1)


class IsoPuddles(VGroup):
    """Puddles on an iso place (DESIGN.md §90.2): each :class:`~vidgen.cartoon.iso_weather.IsoPuddle`
    a flat ellipse as the ``view`` sees a circle on the ground, growing with the seconds of rain
    (:func:`~vidgen.cartoon.rain.puddle_growth`) from scene time ``start`` until ``ended()`` (``None``
    while it rains) and staying when it stops, with ripples spreading on it while it rains
    (:func:`~vidgen.cartoon.iso_weather.ripples`). ``clock()``: the scene's time. Drawn over the
    place's pictures, under the shadows and the characters (the cells are chosen so that no piece
    stands in front of a puddle)."""

    def __init__(self, puddles: Sequence[IsoPuddle], view: IsoView, *, start: float, ended: Callable[[], float | None],
                 clock: Callable[[], float]) -> None:
        super().__init__()
        self.puddles, self.view = list(puddles), view
        self.start, self.ended, self.clock = start, ended, clock
        self.name = "iso_puddles"
        self.pools: list[VMobject] = []
        self.rings: list[VMobject] = []
        for _ in self.puddles:
            pool = VMobject()
            pool.set_fill(ISO_PUDDLE_COLOR, opacity=ISO_PUDDLE_OPACITY)
            pool.set_stroke(width=0.0, opacity=0.0)
            self.pools.append(pool)
        for _ in range(len(self.puddles) * RIPPLES):
            ring = VMobject()
            ring.set_fill(RIPPLE_COLOR, opacity=RIPPLE_OPACITY)
            ring.set_stroke(width=0.0, opacity=0.0)
            self.rings.append(ring)
        self.add(*self.pools, *self.rings)
        self._draw()
        self.add_updater(lambda mob, dt: self._draw())

    def _axes(self, radius: float) -> tuple[float, float]:
        """The half axes (Manim units) of a circle of ``radius`` (tile units) on the ground."""
        a = radius * math.sqrt(2) / 2 * self.view.unit
        return a, a / 2

    def _draw(self) -> None:
        """Size the puddles and place the ripples for now; stops updating once the rain has
        stopped (they grow no more)."""
        now, ended = self.clock(), self.ended()
        rained = (now if ended is None else min(now, ended)) - self.start
        growth = puddle_growth(rained)
        for k, puddle in enumerate(self.puddles):
            x, y = self.view.point(puddle.x, puddle.y, puddle.z)
            a, b = self._axes(puddle.radius * growth)
            if growth > 0:
                self.pools[k].set_points_as_corners(_ellipse(x, y, a, b))
            else:
                self.pools[k].points = np.zeros((0, 3))
            rings = ripples(puddle, max(rained, 0.0), growth) if ended is None and growth > 0 else []
            for j in range(RIPPLES):
                ring = self.rings[k * RIPPLES + j]
                if j >= len(rings) or rings[j].opacity <= 0:
                    ring.points = np.zeros((0, 3))
                    continue
                r = rings[j]
                rx, ry = self.view.point(puddle.x + r.dx, puddle.y + r.dy, puddle.z)
                outer, inner = self._axes(r.radius), self._axes(r.radius * (1.0 - RIPPLE_WIDTH))
                ring.set_points_as_corners(np.concatenate([_ellipse(rx, ry, *outer), _ellipse(rx, ry, *inner, reverse=True)]))
                ring.set_fill(opacity=r.opacity)
        if ended is not None and now >= ended:
            self.clear_updaters()


class IsoSnow:
    """Snow settling on an iso place (DESIGN.md §90.3): the snow lying on the place's pictures
    (:meth:`IsoTiles.set_snow_opacity`) grows with the seconds of snowfall of each of its
    ``falls`` (``(start, ended, density, settled)``: scene time it began, ``ended()`` its end or
    ``None``, its density, seconds of snowfall already lying) in steps
    (:func:`~vidgen.cartoon.snow.settled_seconds`), shown at the plain stage blanket's opacity
    (:func:`~vidgen.cartoon.snow.blanket_cover`). ``groups()``: the pictures now (front
    pictures are made as characters walk); ``region``: where it draws (Manim units: left, bottom,
    right, top). A living thing of the stage (its ``update``, ``changing``, ``done``, ``movers``,
    ``region``)."""

    def __init__(self, groups: Callable[[], list[IsoTiles]], region: tuple[float, float, float, float]) -> None:
        self.groups = groups
        self._region = region
        self.falls: list[tuple[float, Callable[[], float | None], float, float]] = []
        #: the opacity shown now (``None``: not drawn yet)
        self.cover: float | None = None

    def add_fall(self, start: float, ended: Callable[[], float | None], density: float, settled: float) -> None:
        """A snow field that settles, from scene time ``start``; its snow tiles show from now on."""
        self.falls.append((start, ended, density, settled))
        self.cover = None
        self.update(start)

    def amount_at(self, now: float) -> float:
        """How much snow lies at scene time ``now`` (0..1), in steps."""
        return min(sum(settle_amount(settled_seconds(now, start, ended(), settled), density) for start, ended, density, settled in self.falls), 1.0)

    def cover_at(self, now: float) -> float:
        return BLANKET_OPACITY * blanket_cover(self.amount_at(now))

    def update(self, now: float) -> None:
        """Show the snow for scene time ``now`` (only when its step changed)."""
        cover = self.cover_at(now)
        if cover == self.cover:
            return
        self.cover = cover
        for group in self.groups():
            group.set_snow_opacity(cover)

    def changing(self, start: float, end: float) -> bool:
        return self.cover_at(start) != self.cover_at(end)

    def done(self, now: float) -> bool:
        return self.cover_at(now) == self.cover_at(math.inf)

    def movers(self) -> list[Mobject]:
        """What changes as it grows: the pictures' tiles shown."""
        return [tile for group in self.groups() for tile in group.picture_tiles()]

    def region(self, start: float, end: float) -> tuple[float, float, float, float]:
        return self._region


def draw_tile(camera: Any, mob: ImageMobject, pixel_array: np.ndarray) -> None:
    """Draw the tile ``mob`` (upright, not turned) onto the camera's ``pixel_array``: only the
    part in the frame, resized (smoothly, also when it shrinks) onto just that part. Manim's own
    way warps the whole picture and blends it over a picture of the whole frame, for each picture
    on each frame: a few times slower with the dozen tiles a view shows (DESIGN.md §89.10)."""
    corners = camera.points_to_subpixel_coords(mob, mob.points)   # top left, top right, bottom left, bottom right
    (left, top), (right, bottom) = corners[0], corners[3]
    if right - left < 0.5 or bottom - top < 0.5:
        return
    height, width = pixel_array.shape[:2]
    x0, y0 = max(math.floor(left), 0), max(math.floor(top), 0)
    x1, y1 = min(math.ceil(right), width), min(math.ceil(bottom), height)
    if x1 <= x0 or y1 <= y0:
        return
    source = mob.pixel_array
    sx, sy = source.shape[1] / (right - left), source.shape[0] / (bottom - top)
    high_x, high_y = source.shape[1], source.shape[0]
    box = (min(max((x0 - left) * sx, 0.0), high_x), min(max((y0 - top) * sy, 0.0), high_y),
           min(max((x1 - left) * sx, 0.0), high_x), min(max((y1 - top) * sy, 0.0), high_y))
    part = Image.fromarray(source, "RGBA").resize((x1 - x0, y1 - y0), Image.Resampling.BILINEAR, box=box)
    under = Image.fromarray(np.ascontiguousarray(pixel_array[y0:y1, x0:x1]), "RGBA")
    pixel_array[y0:y1, x0:x1] = np.asarray(Image.alpha_composite(under, part))


def install_tile_drawing(camera: Any) -> None:
    """Let ``camera`` (Manim's Cairo camera) draw iso tiles with :func:`draw_tile`; other
    pictures as before. Install it before anything else wraps the camera's picture drawing (the
    stage's light grades a tile's pixels around it)."""
    if getattr(camera, "draws_iso_tiles", False):
        return
    original = camera.display_image_mobject

    def display(image_mobject: Any, pixel_array: np.ndarray) -> None:
        if getattr(image_mobject, "iso_tile", False):
            draw_tile(camera, image_mobject, pixel_array)
        else:
            original(image_mobject, pixel_array)

    camera.display_image_mobject = display
    camera.draws_iso_tiles = True


__all__ = ["ISO_PUDDLE_COLOR", "ISO_PUDDLE_OPACITY", "RIPPLE_COLOR", "GlowTile", "IsoPuddles", "IsoSnow", "IsoTiles", "draw_tile", "install_tile_drawing"]
