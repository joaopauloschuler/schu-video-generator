"""Iso shapes (:mod:`vidgen.cartoon.iso_drawing`) as Manim vector mobjects (DESIGN.md §90.6):
an iso diagram's blocks stay sharp at any zoom and can be recoloured, moved and faded one by
one, which a Pillow picture of the place (the iso stage's drawing) cannot."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from manim import VGroup, VMobject

from vidgen.cartoon.iso_drawing import RIGHT_SHADE, Blobs, Disc, Line, Poly, Shape, Upright, shade
from vidgen.cartoon.level_drawing import mix
from vidgen.world.iso_view import iso_point

#: Maps a picture point (tile widths, ``v`` down) to a scene point.
ToScene = Callable[[float, float], np.ndarray]
#: Points along an ellipse's half (a cylinder's front, its top's rim).
ELLIPSE_SAMPLES = 32


def picture_to_scene(scale: float, origin: Sequence[float]) -> ToScene:
    """``scale`` Manim units per tile width, picture point (0, 0) at scene point ``origin``."""
    ox, oy = float(origin[0]), float(origin[1])
    return lambda u, v: np.array([ox + u * scale, oy - v * scale, 0.0])


def _polygon(points: Sequence[np.ndarray], fill: str, ink: str | None, stroke: float) -> VMobject:
    shape = VMobject()
    shape.set_points_as_corners([*points, points[0]])
    shape.set_fill(fill, opacity=1.0)
    shape.set_stroke(ink or fill, width=stroke if ink else 0.0)
    return shape


def _ellipse(cu: float, cv: float, a: float, b: float, start: float, end: float, to_scene: ToScene) -> list[np.ndarray]:
    """Points of the picture ellipse around (``cu``, ``cv``) from angle ``start`` to ``end``
    (degrees, counter-clockwise on the screen: 0 right, 90 up)."""
    return [to_scene(cu + a * math.cos(math.radians(t)), cv - b * math.sin(math.radians(t)))
            for t in np.linspace(start, end, ELLIPSE_SAMPLES + 1)]


def shape_mobject(shape: Shape, to_scene: ToScene, *, ink: str | None, stroke: float = 2.0) -> VMobject:
    """One iso shape as a mobject: a polygon filled in its colour (outlined in ``ink`` unless the
    shape has no outline), an upright cylinder (body with its right side in shade, and its
    top), or a line (``width`` outline widths of ``stroke``)."""
    if isinstance(shape, Poly):
        return _polygon([to_scene(*iso_point(*p)) for p in shape.points], shape.fill, ink if shape.ink is not False else None, stroke)
    if isinstance(shape, Upright):
        return _upright(shape, to_scene, ink, stroke)
    if isinstance(shape, Line):
        line = VMobject()
        line.set_points_as_corners([to_scene(*iso_point(*p)) for p in shape.points])
        line.set_fill(opacity=0.0).set_stroke(shape.color, width=stroke * shape.width)
        return line
    if isinstance(shape, Disc):
        a, b = shape.radius * math.sqrt(2) / 2, shape.radius * math.sqrt(2) / 4
        disc = _polygon(_ellipse(*iso_point(*shape.centre), a, b, 0, 360, to_scene)[:-1], shape.fill, ink if shape.ink else None, stroke)
        disc.set_fill(opacity=shape.opacity)
        return disc
    assert isinstance(shape, Blobs)
    group = VGroup()
    for centre, radius in zip(shape.centres, shape.radii):
        group.add(_polygon(_ellipse(*iso_point(*centre), radius, radius, 0, 360, to_scene)[:-1], shape.fill, ink if shape.ink else None, stroke))
    return group


def _upright(shape: Upright, to_scene: ToScene, ink: str | None, stroke: float) -> VGroup:
    """A cylinder: its body (the front half of the bottom ellipse up to the top's middle), the
    body's right part in shade, its top ellipse a little lighter."""
    a, b = shape.radius * math.sqrt(2) / 2, shape.radius * math.sqrt(2) / 4
    bu, bv = iso_point(shape.x, shape.y, shape.z0)
    tu, tv = iso_point(shape.x, shape.y, shape.z1)
    side = [to_scene(tu - a, tv), *_ellipse(bu, bv, a, b, 180, 360, to_scene), to_scene(tu + a, tv)]
    body = _polygon(side, shape.fill, None, stroke)
    start = math.degrees(math.acos(0.3))   # the shade starts 0.3 of the way right of the middle
    dark = _polygon([to_scene(tu + 0.3 * a, tv), *_ellipse(bu, bv, a, b, 360 - start, 360, to_scene), to_scene(tu + a, tv)],
                    shade(shape.fill, RIGHT_SHADE * 0.6), None, stroke)
    parts = [body, dark]
    if ink:
        outline = VMobject()
        outline.set_points_as_corners(side)
        outline.set_fill(opacity=0.0).set_stroke(ink, width=stroke)
        parts.append(outline)
    parts.append(_polygon(_ellipse(tu, tv, a, b, 0, 360, to_scene)[:-1], mix(shape.fill, "#FFFFFF", 0.12), ink, stroke))
    return VGroup(*parts)


def shapes_mobject(shapes: Sequence[Shape], to_scene: ToScene, *, ink: str | None, stroke: float = 2.0) -> VGroup:
    """``shapes`` in paint order as one group (one submobject per shape)."""
    return VGroup(*[shape_mobject(s, to_scene, ink=ink, stroke=stroke) for s in shapes])


__all__ = ["ToScene", "picture_to_scene", "shape_mobject", "shapes_mobject"]
