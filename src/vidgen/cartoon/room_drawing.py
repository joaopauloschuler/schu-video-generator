"""Drawing a stage's room (DESIGN.md §69.42): :func:`draw_room` turns the shapes of
:mod:`vidgen.cartoon.room` into mobjects in three layers, back to front: the room (wall,
wallpaper, floor, skirting, ceiling), the views out of its windows (:class:`WindowViews`: the sky
and its stars, never graded by the stage's light) and the window frames, sills and curtains.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from manim import DOWN, Circle, Difference, Line, Mobject, Polygon, Rectangle, VGroup, VMobject

from vidgen.cartoon.character import OUTLINE_WIDTH, REFERENCE_HEIGHT, one_pixel_stroke
from vidgen.cartoon.lighting import night_stars
from vidgen.cartoon.room import (
    CEILING_SHADE,
    PATTERN_SHADE,
    SKIRTING_SHADE,
    Box,
    RoomGeometry,
    WindowParts,
    WindowSky,
    darker,
    floor_lines,
    lighter,
    shade,
    wallpaper_dots,
    wallpaper_stripes,
)
from vidgen.cartoon.shading import StarField
from vidgen.config import CHARACTER_INK

#: Line width of the floor's seams (a share of a character's outline).
SEAM_WIDTH = 0.6


@dataclass(frozen=True)
class RoomColors:
    """A room's colours (``#hex``): ``wall``, ``floor``, ``skirting`` and ``ceiling`` (``None``:
    no ceiling band)."""

    wall: str
    floor: str
    skirting: str
    ceiling: str | None


def room_colors(wall: str, floor: str, *, skirting: str | None = None, ceiling: str | bool = False) -> RoomColors:
    """The colours of a room from the given ones: the skirting defaults to the floor colour made
    darker, a ceiling given as ``True`` to the wall colour made lighter."""
    band = lighter(wall, CEILING_SHADE) if ceiling is True else (ceiling or None)
    return RoomColors(wall, floor, skirting or darker(floor, SKIRTING_SHADE), band)


@dataclass(frozen=True)
class WindowLook:
    """A window to draw: its ``parts``, its ``frame`` colour and its ``curtains`` colour
    (``None``: none; ``#hex``)."""

    parts: WindowParts
    frame: str
    curtains: str | None = None


def _box(box: Box, color: str, *, outline: float = 0.0) -> Rectangle:
    rect = Rectangle(width=max(box.width, 1e-6), height=max(box.height, 1e-6))
    rect.move_to([*box.center, 0.0])
    rect.set_fill(color, opacity=1.0)
    rect.set_stroke(CHARACTER_INK, width=outline, opacity=1.0 if outline else 0.0)
    return rect


def _stroke(unit: float, share: float = 1.0) -> float:
    """An outline as wide as a character's ``unit`` tall draws its own (``share`` of it), at least
    one pixel."""
    return max(OUTLINE_WIDTH * share * unit / REFERENCE_HEIGHT, one_pixel_stroke())


class WindowViews(VGroup):
    """The sky seen through each window: a gradient over its glass and its stars
    (:class:`~vidgen.cartoon.shading.StarField`); :meth:`show` sets the sky for the light now."""

    def __init__(self, glasses: Sequence[Box], sky: WindowSky, short_side: float, frame_area: float, *, preview: bool = False) -> None:
        super().__init__()
        self.name = "window_views"
        self.skies: list[Rectangle] = []
        self.stars: list[StarField] = []
        for k, glass in enumerate(glasses):
            pane = Rectangle(width=glass.width, height=glass.height, stroke_width=0).move_to([*glass.center, 0.0])
            stars = StarField(
                night_stars(glass.width * glass.height / frame_area, seed=k + 1, preview=preview),
                (glass.left, glass.bottom, glass.right, glass.top), short_side,
            )
            self.skies.append(pane)
            self.stars.append(stars)
            self.add(pane, stars)
        self.show(sky)

    def show(self, sky: WindowSky) -> WindowViews:
        """Colour every window's sky ``sky`` (top to bottom) with its stars at ``sky.stars``."""
        for pane in self.skies:
            pane.set_fill([sky.top, sky.bottom], opacity=1.0)
            pane.set_sheen_direction(DOWN)
        for stars in self.stars:
            stars.set_level(sky.stars)
        return self


@dataclass
class RoomDrawing:
    """A drawn room, back to front: ``back`` (wall, wallpaper, floor, skirting, ceiling),
    ``views`` (the windows' skies) and ``front`` (window frames, bars, sills, rods, curtains)."""

    back: VGroup
    views: WindowViews
    front: VGroup

    def mobjects(self) -> list[Mobject]:
        return [self.back, self.views, self.front]


def draw_room(
    geometry: RoomGeometry,
    colors: RoomColors,
    *,
    wallpaper: str,
    flooring: str,
    windows: Sequence[WindowLook],
    sky: WindowSky,
    short_side: float,
    frame_area: float,
    preview: bool = False,
) -> RoomDrawing:
    """The room of ``geometry`` in ``colors`` with its ``wallpaper`` and ``flooring`` patterns
    and ``windows`` showing ``sky``. ``short_side`` and ``frame_area``: the frame's shorter side
    and area (Manim units), for the stars (fewer at ``preview`` quality)."""
    unit = geometry.unit
    back = VGroup()
    back.add(_box(geometry.wall, colors.wall))
    pattern = shade(colors.wall, PATTERN_SHADE)
    if wallpaper == "stripes":
        back.add(*[_box(box, pattern) for box in wallpaper_stripes(geometry.wall, unit)])
    elif wallpaper == "dots":
        back.add(*[Circle(radius=r).move_to([x, y, 0.0]).set_fill(pattern, opacity=1.0).set_stroke(width=0, opacity=0.0)
                   for x, y, r in wallpaper_dots(geometry.wall, unit)])
    back.add(_box(geometry.floor, colors.floor))
    seam = shade(colors.floor, 0.25)
    for (x0, y0), (x1, y1) in floor_lines(flooring, geometry.floor, unit):
        back.add(Line([x0, y0, 0.0], [x1, y1, 0.0], stroke_width=_stroke(unit, SEAM_WIDTH), color=seam))
    back.add(_box(geometry.skirting, colors.skirting, outline=_stroke(unit, 0.6)))
    if geometry.ceiling is not None and colors.ceiling is not None:
        back.add(_box(geometry.ceiling, colors.ceiling, outline=_stroke(unit, 0.6)))
    back.name = "room"
    views = WindowViews([w.parts.glass for w in windows], sky, short_side, frame_area, preview=preview)
    front = VGroup()
    outline = _stroke(unit)
    for look in windows:
        window = look.parts
        hole = Rectangle(width=window.glass.width, height=window.glass.height).move_to([*window.glass.center, 0.0])
        front.add(_cut(_box(window.frame, look.frame), hole, look.frame, outline))
        front.add(*[_box(bar, look.frame, outline=outline * 0.6) for bar in window.bars])
        front.add(_box(window.sill, look.frame, outline=outline))
        if window.rod is not None and look.curtains is not None:
            front.add(_box(window.rod, darker(look.frame, 0.45), outline=outline * 0.6))
            for curtain in window.curtains:
                drape = Polygon(*[np.array([x, y, 0.0]) for x, y in curtain]).round_corners(0.08 * unit)
                front.add(drape.set_fill(look.curtains, opacity=1.0).set_stroke(CHARACTER_INK, width=outline, opacity=1.0))
    front.name = "room_front"
    return RoomDrawing(back, views, front)


def _cut(frame: VMobject, hole: VMobject, color: str, outline: float) -> VMobject:
    """``frame`` with ``hole`` cut out of it (the glass shows the sky behind), filled ``color``."""
    ring = Difference(frame, hole)
    ring.set_fill(color, opacity=1.0).set_stroke(CHARACTER_INK, width=outline, opacity=1.0)
    return ring


__all__ = ["RoomColors", "RoomDrawing", "WindowLook", "WindowViews", "draw_room", "room_colors"]
