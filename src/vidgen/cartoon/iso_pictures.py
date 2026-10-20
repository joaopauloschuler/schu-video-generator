"""An iso place's pictures on the stage (DESIGN.md §89.10): each picture of an
:class:`~vidgen.cartoon.iso_stage.IsoScenery` (its base, a character's front picture, a layer of
an object that changes) is an :class:`IsoTiles` group showing the tiles the camera sees, at the
level of detail its zoom needs.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from manim import Group, ImageMobject, Mobject
from PIL import Image

from vidgen.cartoon.iso_stage import IsoScenery, IsoView, Picture, canvas_center, detail_for
from vidgen.cartoon.shading import LIT, mark_lit


class IsoTiles(Group):
    """One picture of an iso place (``picture`` of ``scenery``), named ``name``: its members are
    the tiles in the camera's view (:meth:`show_view`) at the level of detail of the camera's
    zoom; ``density``: level 0's pixels per frame pixel. A tile is made once (kept for the
    scene), lit like the group (:func:`~vidgen.cartoon.shading.mark_lit`), and marked
    ``scenery`` (the camera crops it on purpose: lint ``off_frame``)."""

    def __init__(self, scenery: IsoScenery, picture: Picture, view: IsoView, *, name: str, density: float, frame_width: float) -> None:
        super().__init__()
        self.scenery, self.picture, self.iso_view = scenery, picture, view
        self.name = name
        self.density = density
        self.frame_width = frame_width
        self.shown_key: tuple[int, tuple[tuple[int, int], ...]] | None = None
        self._tiles: dict[tuple[int, tuple[int, int]], ImageMobject | None] = {}
        #: the tiles' opacity (a place change fades a layer in or out, DESIGN.md §89.10)
        self.tile_opacity = 1.0

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
        for tile, canvas in tiles:
            if (level, tile) not in self._tiles:
                self._tiles[(level, tile)] = self._make(level, tile, canvas)
            made = self._tiles[(level, tile)]
            if made is not None:
                members.append(made)
        self.submobjects = members
        return True

    def _make(self, level: int, tile: tuple[int, int], canvas: Any) -> ImageMobject | None:
        image = self.scenery.tile_image(self.picture, level, tile, canvas)
        if image is None:
            return None
        made = ImageMobject(np.array(image))
        made.scale_to_fit_width(canvas.width / canvas.scale * self.iso_view.unit)
        made.move_to([*canvas_center(canvas, self.iso_view), 0.0])
        made.name = self.name
        made.scenery = True
        made.iso_tile = True   # drawn by :func:`draw_tile`
        if self.tile_opacity < 1.0:
            made.set_opacity(self.tile_opacity)
        if getattr(self, LIT, False):
            mark_lit(made)
        return made

    def set_tile_opacity(self, opacity: float) -> None:
        """Show every tile (also those made later) at ``opacity`` (0..1)."""
        self.tile_opacity = opacity
        for made in self._tiles.values():
            if made is not None:
                made.set_opacity(opacity)


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


__all__ = ["IsoTiles", "draw_tile", "install_tile_drawing"]
