"""Drawing in the isometric view with Pillow (DESIGN.md §89.6), in schu-video-generator's flat cartoon look:
filled shapes with the characters' ink outline. No manim.

Shapes are given in the world (tile units, :mod:`vidgen.world.iso_view`) and drawn onto an
:class:`IsoCanvas`, a picture of part of the view at some pixels per tile width, supersampled
for smooth edges. :func:`box_shapes` gives a block's three visible faces with the outline only
where an edge shows (not where it joins a neighbour of the same height), so a terrace of blocks
or a run of wall reads as one solid thing.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw

from vidgen.cartoon.level_drawing import mix
from vidgen.config import CHARACTER_INK
from vidgen.world.iso_view import Point3, iso_point

#: Outline width (tile widths on the picture) in the plain drawing style.
ISO_OUTLINE = 0.022
#: The drawing's supersampling factor (drawn this many times larger, then reduced).
ISO_SUPERSAMPLE = 3
#: How much darker a block's faces are than its top: the face to the viewer's lower left (lit)
#: and to the lower right (in shade).
LEFT_SHADE = 0.12
RIGHT_SHADE = 0.26

#: The sides of a cell, as the map reads: n (up, further back), e (right), s (down, nearer), w (left).
SIDES = ("n", "e", "s", "w")


def shade(color: str, amount: float) -> str:
    """``color`` darker by ``amount`` (0..1), towards a cool dark rather than grey."""
    return mix(color, "#1B2333", amount)


@dataclass(frozen=True)
class Poly:
    """A flat polygon in the world; ``ink`` outlines every edge (``True``), none (``False``) or
    the edges marked (edge ``i`` runs from point ``i`` to the next); ``glow``: a light (a lit
    window or lantern) that the stage's light does not dim (DESIGN.md §89.11). Settling snow
    (DESIGN.md §90.3) lies on it when it faces up (:func:`upward`) and ``holds_snow`` (water does
    not); ``snow_cap``: on an upright one (a pine's tier), snow covers that share of it from its
    top down."""

    points: tuple[Point3, ...]
    fill: str
    ink: bool | tuple[bool, ...] = True
    glow: bool = False
    holds_snow: bool = True
    snow_cap: float = 0.0


@dataclass(frozen=True)
class Blobs:
    """Round shapes on the picture (a tree's crown, a bush) drawn and outlined as one form: each
    a circle around a world point, ``radii`` in tile widths."""

    centres: tuple[Point3, ...]
    radii: tuple[float, ...]
    fill: str
    ink: bool = True


@dataclass(frozen=True)
class Disc:
    """A flat circle lying in the world at height ``centre[2]`` (a well's water, a lamp's base):
    ``radius`` in tile units; with ``opacity`` under 1 it tints what is under it (a shadow, a
    pool of light); ``glow`` and ``holds_snow`` as a :class:`Poly`'s."""

    centre: Point3
    radius: float
    fill: str
    ink: bool = True
    opacity: float = 1.0
    glow: bool = False
    holds_snow: bool = True


@dataclass(frozen=True)
class Upright:
    """An upright cylinder (a trunk, a post, a well): its axis at (``x``, ``y``) from ``z0`` to
    ``z1``, ``radius`` in tile units; its right side a little in shade."""

    x: float
    y: float
    z0: float
    z1: float
    radius: float
    fill: str
    ink: bool = True


@dataclass(frozen=True)
class Line:
    """A line through world points (a plank's seam, a window's bars), ``width`` in outline widths."""

    points: tuple[Point3, ...]
    color: str
    width: float = 1.0


Shape = Poly | Blobs | Disc | Upright | Line


def box_shapes(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float, top: str, *,
               left: str | None = None, right: str | None = None, joined: Iterable[str] = (),
               bottoms: tuple[float, float] | None = None, faces: str = "tlr", glow: bool = False) -> list[Shape]:
    """A box's visible faces: its top, its face to the viewer's lower left (``y = y1``, the map's
    ``s`` side) and to the lower right (``x = x1``, ``e``), coloured ``top`` and shades of it
    unless given. ``joined`` sides (``n``, ``e``, ``s``, ``w``) continue into a neighbour of the
    same height: no outline there, and no face on ``s`` or ``e``. ``bottoms`` (``s``, ``e``)
    start those faces higher than ``z0`` (on a neighbour's top). ``faces`` picks among top
    (``t``), left (``l``) and right (``r``); ``glow``: its faces are a light (a lit lantern)."""
    joined = set(joined)
    left = left or shade(top, LEFT_SHADE)
    right = right or shade(top, RIGHT_SHADE)
    bottom_s, bottom_e = bottoms if bottoms is not None else (z0, z0)
    shapes: list[Shape] = []
    if "l" in faces and "s" not in joined and z1 > bottom_s:
        # bottom edge, front corner (unless the right side joins), top edge, back-left corner (unless the left joins)
        shapes.append(Poly(((x0, y1, bottom_s), (x1, y1, bottom_s), (x1, y1, z1), (x0, y1, z1)), left,
                           (True, "e" not in joined, True, "w" not in joined), glow))
    if "r" in faces and "e" not in joined and z1 > bottom_e:
        shapes.append(Poly(((x1, y1, bottom_e), (x1, y0, bottom_e), (x1, y0, z1), (x1, y1, z1)), right,
                           (True, "n" not in joined, True, "s" not in joined), glow))
    if "t" in faces:
        shapes.append(Poly(((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)), top,
                           tuple(side not in joined for side in ("n", "e", "s", "w")), glow))
    return shapes


@dataclass(frozen=True)
class IsoCanvas:
    """A picture of part of the view: ``scale`` pixels per tile width, its top-left corner at
    picture point (``left``, ``top``), ``width`` x ``height`` pixels."""

    scale: float
    left: float
    top: float
    width: int
    height: int

    def pixel(self, point: Point3, supersample: int = 1) -> tuple[float, float]:
        """A world point in the canvas's pixels (times ``supersample``)."""
        u, v = iso_point(*point)
        return ((u - self.left) * self.scale * supersample, (v - self.top) * self.scale * supersample)


def canvas_for(bounds: tuple[float, float, float, float], scale: float, margin: float = 0.05) -> IsoCanvas:
    """A canvas covering picture ``bounds`` (left, top, right, bottom, tile widths) and ``margin``
    tile widths around them at ``scale`` pixels per tile width."""
    left, top, right, bottom = bounds
    left, top = left - margin, top - margin
    width = math.ceil((right + margin - left) * scale)
    height = math.ceil((bottom + margin - top) * scale)
    return IsoCanvas(scale, left, top, max(width, 1), max(height, 1))


def shape_bounds(shape: Shape) -> tuple[float, float, float, float]:
    """The picture bounds (tile widths: left, top, right, bottom) of ``shape``'s fill, without
    its outline."""
    if isinstance(shape, (Poly, Line)):
        found = [iso_point(*p) for p in shape.points]
        return min(u for u, _ in found), min(v for _, v in found), max(u for u, _ in found), max(v for _, v in found)
    if isinstance(shape, Blobs):
        found = [(*iso_point(*c), r) for c, r in zip(shape.centres, shape.radii)]
        return min(u - r for u, _, r in found), min(v - r for _, v, r in found), max(u + r for u, _, r in found), max(v + r for _, v, r in found)
    a, b = shape.radius * math.sqrt(2) / 2, shape.radius * math.sqrt(2) / 4
    if isinstance(shape, Disc):
        u, v = iso_point(*shape.centre)
        return u - a, v - b, u + a, v + b
    (u0, v0), (_, v1) = iso_point(shape.x, shape.y, shape.z0), iso_point(shape.x, shape.y, shape.z1)
    return u0 - a, min(v0, v1) - b, u0 + a, max(v0, v1) + b


def _on_canvas(shape: Shape, canvas: IsoCanvas, pad: float) -> bool:
    """Whether ``shape`` (with ``pad`` tile widths around it for its outline) reaches onto ``canvas``."""
    left, top, right, bottom = shape_bounds(shape)
    return (right + pad >= canvas.left and left - pad <= canvas.left + canvas.width / canvas.scale
            and bottom + pad >= canvas.top and top - pad <= canvas.top + canvas.height / canvas.scale)


def _ink_runs(points: list[tuple[float, float]], ink: bool | tuple[bool, ...]) -> list[list[tuple[float, float]]]:
    """The outlined runs of a closed polygon's edges, each a list of points."""
    count = len(points)
    marks = [ink] * count if isinstance(ink, bool) else list(ink)
    if all(marks):
        return [[*points, points[0]]]
    runs: list[list[tuple[float, float]]] = []
    start = next((k for k in range(count) if not marks[k]), 0)   # begin after a gap, so runs do not wrap
    run: list[tuple[float, float]] = []
    for step in range(1, count + 1):
        k = (start + step) % count
        if marks[k]:
            if not run:
                run = [points[k]]
            run.append(points[(k + 1) % count])
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    return runs


#: What a shape that is not a light paints in a picture of the lights (:func:`draw_shapes` with
#: ``glow``): nothing, so a light behind it stays hidden.
CLEAR = (0, 0, 0, 0)
#: Settling snow on an iso place (DESIGN.md §90.3): its colour (as on a plain stage), the least
#: share of a polygon's normal that points up for snow to lie on it (a roof's slope, not a wall),
#: how much darker it is on a slope facing away from the viewer, and the arc (degrees each side of
#: the top) of the cap on a round thing's every puff.
SNOW_WHITE = "#F4F7FC"
SNOW_SLOPE = 0.45
SNOW_AWAY_SHADE = 0.1
SNOW_CAP_DEGREES = 62.0
#: A line at least this many outline widths wide hides the snow behind it (a well's crank);
#: thinner ones (seams, tufts, bars) are covered by it.
SNOW_LINE_WIDTH = 1.5


def surface_normal(points: Sequence[Point3]) -> tuple[float, float, float] | None:
    """The unit normal of a flat polygon through ``points`` (``z`` up when it faces up or down;
    ``None`` when the points are on a line)."""
    p0 = points[0]
    for k in range(1, len(points) - 1):
        a = [points[k][i] - p0[i] for i in range(3)]
        for j in range(k + 1, len(points)):
            b = [points[j][i] - p0[i] for i in range(3)]
            n = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
            length = math.sqrt(sum(c * c for c in n))
            if length > 1e-9:
                sign = -1.0 if n[2] < 0 else 1.0
                return (sign * n[0] / length, sign * n[1] / length, sign * n[2] / length)
    return None


def upward(shape: Poly) -> tuple[float, float, float] | None:
    """The upward unit normal of ``shape`` when it faces up enough to hold snow and keep rain off
    (:data:`SNOW_SLOPE`: a top, a roof's slope), else ``None`` (a wall, a face, a cut-out)."""
    normal = surface_normal(shape.points)
    return normal if normal is not None and normal[2] >= SNOW_SLOPE else None


def _above(points: Sequence[Point3], z: float) -> list[Point3]:
    """The part of the polygon ``points`` at or above height ``z`` (clipped, Sutherland–Hodgman)."""
    found: list[Point3] = []
    for k, a in enumerate(points):
        b = points[(k + 1) % len(points)]
        if a[2] >= z:
            found.append(a)
        if (a[2] >= z) != (b[2] >= z):
            share = (z - a[2]) / (b[2] - a[2])
            found.append((a[0] + share * (b[0] - a[0]), a[1] + share * (b[1] - a[1]), z))
    return found


def draw_shapes(shapes: Sequence[Shape], canvas: IsoCanvas, *, outline: float = 1.0, ink: str = CHARACTER_INK,
                image: Image.Image | None = None, supersample: int = ISO_SUPERSAMPLE, glow: bool = False, snow: bool = False) -> Image.Image:
    """An RGBA picture of ``shapes`` (painted in order) on ``canvas``, transparent elsewhere;
    ``outline`` multiplies :data:`ISO_OUTLINE`. Drawn ``supersample`` times larger and reduced
    with a box filter. With ``image`` (the canvas's size) the shapes go over it. ``glow``: a
    picture of the lights only (DESIGN.md §89.11): the shapes marked ``glow`` as drawn, every
    other shape (but a tint) clearing what it covers, so a light is seen only where the whole
    picture shows it. ``snow``: a picture of the snow lying on the shapes (DESIGN.md §90.3,
    :func:`_snow`), each shape clearing the snow behind it."""
    ss = supersample
    big = Image.new("RGBA", (canvas.width * ss, canvas.height * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    width = max(ISO_OUTLINE * outline * canvas.scale * ss, 1.0)

    def line(points: list[tuple[float, float]], color: Any, line_width: float) -> None:
        draw.line(points, fill=color, width=max(round(line_width), 1), joint="curve")
        r = line_width / 2
        for x, y in (points[0], points[-1]):
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    pad = ISO_OUTLINE * outline * 3 + 2 / canvas.scale   # the outline and a line's width reach past the fill
    for shape in shapes:
        if not _on_canvas(shape, canvas, pad):
            continue   # nothing of it on this canvas (a tile of a large picture, DESIGN.md §89.10)
        if snow:
            _snow(draw, shape, canvas, ss, width, line, ink)
            continue
        clearing = glow and not getattr(shape, "glow", False)
        if clearing and isinstance(shape, Disc) and shape.opacity < 1.0:
            continue   # a shadow hides no light
        if clearing:
            _clear(draw, shape, canvas, ss, width, line)
            continue
        if isinstance(shape, Poly):
            points = [canvas.pixel(p, ss) for p in shape.points]
            draw.polygon(points, fill=shape.fill, outline=shape.fill)   # its own colour on the edge: no seam with a neighbour
            for run in _ink_runs(points, shape.ink) if shape.ink is not False else []:
                line(run, ink, width)
        elif isinstance(shape, Blobs):
            circles = [(canvas.pixel(c, ss), r * canvas.scale * ss) for c, r in zip(shape.centres, shape.radii)]
            if shape.ink:
                for (x, y), r in circles:
                    draw.ellipse((x - r - width / 2, y - r - width / 2, x + r + width / 2, y + r + width / 2), fill=ink)
            for (x, y), r in circles:
                inner = r - width / 2 if shape.ink else r
                draw.ellipse((x - inner, y - inner, x + inner, y + inner), fill=shape.fill)
        elif isinstance(shape, Disc) and shape.opacity < 1.0:
            x, y = canvas.pixel(shape.centre, ss)
            a, b = shape.radius * math.sqrt(2) / 2 * canvas.scale * ss, shape.radius * math.sqrt(2) / 4 * canvas.scale * ss
            left, top = math.floor(x - a), math.floor(y - b)
            patch = Image.new("RGBA", (math.ceil(2 * a) + 2, math.ceil(2 * b) + 2), (0, 0, 0, 0))
            rgb = tuple(int(shape.fill[k:k + 2], 16) for k in (1, 3, 5))
            ImageDraw.Draw(patch).ellipse((x - a - left, y - b - top, x + a - left, y + b - top), fill=(*rgb, round(255 * shape.opacity)))
            if left >= 0 and top >= 0 and left + patch.width <= big.width and top + patch.height <= big.height:
                big.alpha_composite(patch, dest=(left, top))
            else:   # partly off the canvas: crop the patch to it
                x0, y0 = max(-left, 0), max(-top, 0)
                x1, y1 = min(patch.width, big.width - left), min(patch.height, big.height - top)
                if x1 > x0 and y1 > y0:
                    big.alpha_composite(patch.crop((x0, y0, x1, y1)), dest=(max(left, 0), max(top, 0)))
        elif isinstance(shape, Disc):
            x, y = canvas.pixel(shape.centre, ss)
            a, b = shape.radius * math.sqrt(2) / 2 * canvas.scale * ss, shape.radius * math.sqrt(2) / 4 * canvas.scale * ss
            draw.ellipse((x - a, y - b, x + a, y + b), fill=shape.fill, outline=ink if shape.ink else None,
                         width=round(width) if shape.ink else 0)
        elif isinstance(shape, Upright):
            (xb, yb), (xt, yt) = canvas.pixel((shape.x, shape.y, shape.z0), ss), canvas.pixel((shape.x, shape.y, shape.z1), ss)
            a, b = shape.radius * math.sqrt(2) / 2 * canvas.scale * ss, shape.radius * math.sqrt(2) / 4 * canvas.scale * ss
            dark = shade(shape.fill, RIGHT_SHADE * 0.6)
            draw.ellipse((xb - a, yb - b, xb + a, yb + b), fill=shape.fill, outline=ink if shape.ink else None,
                         width=round(width) if shape.ink else 0)
            draw.rectangle((xb - a, yt, xb + a, yb), fill=shape.fill)
            draw.rectangle((xb + a * 0.3, yt, xb + a, yb), fill=dark)
            if shape.ink:
                line([(xb - a, yt), (xb - a, yb)], ink, width)
                line([(xb + a, yt), (xb + a, yb)], ink, width)
            draw.ellipse((xt - a, yt - b, xt + a, yt + b), fill=mix(shape.fill, "#FFFFFF", 0.12),
                         outline=ink if shape.ink else None, width=round(width) if shape.ink else 0)
        else:
            points = [canvas.pixel(p, ss) for p in shape.points]
            line(points, shape.color, width * shape.width)
    small = big.resize((canvas.width, canvas.height), Image.Resampling.BOX)
    if image is None:
        return small
    return Image.alpha_composite(image, small)


def _clear(draw: ImageDraw.ImageDraw, shape: Shape, canvas: IsoCanvas, ss: int, width: float, line: Any) -> None:
    """Paint ``shape``'s whole drawing (its fill and outline) as :data:`CLEAR` (a picture of the lights)."""
    if isinstance(shape, Poly):
        points = [canvas.pixel(p, ss) for p in shape.points]
        draw.polygon(points, fill=CLEAR, outline=CLEAR)
        if shape.ink is not False:
            for run in _ink_runs(points, shape.ink):
                line(run, CLEAR, width)
    elif isinstance(shape, Blobs):
        for c, r in zip(shape.centres, shape.radii):
            (x, y), r = canvas.pixel(c, ss), r * canvas.scale * ss + width / 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=CLEAR)
    elif isinstance(shape, Disc):
        x, y = canvas.pixel(shape.centre, ss)
        a, b = shape.radius * math.sqrt(2) / 2 * canvas.scale * ss + width / 2, shape.radius * math.sqrt(2) / 4 * canvas.scale * ss + width / 2
        draw.ellipse((x - a, y - b, x + a, y + b), fill=CLEAR)
    elif isinstance(shape, Upright):
        (xb, yb), (xt, yt) = canvas.pixel((shape.x, shape.y, shape.z0), ss), canvas.pixel((shape.x, shape.y, shape.z1), ss)
        a, b = shape.radius * math.sqrt(2) / 2 * canvas.scale * ss + width / 2, shape.radius * math.sqrt(2) / 4 * canvas.scale * ss + width / 2
        draw.ellipse((xb - a, yb - b, xb + a, yb + b), fill=CLEAR)
        draw.rectangle((xb - a, yt, xb + a, yb), fill=CLEAR)
        draw.ellipse((xt - a, yt - b, xt + a, yt + b), fill=CLEAR)
    else:
        line([canvas.pixel(p, ss) for p in shape.points], CLEAR, width * shape.width)


def _snow(draw: ImageDraw.ImageDraw, shape: Shape, canvas: IsoCanvas, ss: int, width: float, line: Any, ink: str) -> None:
    """Paint the snow lying on ``shape`` (a picture of the snow, :func:`draw_shapes`): white over
    a polygon facing up (:func:`upward`) that holds snow, its outline kept, and over the top of
    a ``snow_cap`` upright one; a cap over each puff of a round thing (the top of its circle); the
    top of an upright cylinder and of a flat disc; everything else clears the snow behind it (a
    shadow or a pool of light, and thin lines, leave it)."""
    if isinstance(shape, Poly):
        normal = upward(shape) if shape.holds_snow and not shape.glow else None
        if normal is not None:
            away = normal[0] < -0.05 or normal[1] < -0.05   # a slope facing the back of the place
            fill = shade(SNOW_WHITE, SNOW_AWAY_SHADE) if away else SNOW_WHITE
            points = [canvas.pixel(p, ss) for p in shape.points]
            draw.polygon(points, fill=fill, outline=fill)
            for run in _ink_runs(points, shape.ink) if shape.ink is not False else []:
                line(run, ink, width)
            return
        _clear(draw, shape, canvas, ss, width, line)
        if shape.snow_cap > 0 and shape.holds_snow:
            top = max(p[2] for p in shape.points)
            low = min(p[2] for p in shape.points)
            cap = _above(shape.points, top - shape.snow_cap * (top - low))
            if len(cap) >= 3:
                points = [canvas.pixel(p, ss) for p in cap]
                draw.polygon(points, fill=SNOW_WHITE, outline=SNOW_WHITE)
        return
    if isinstance(shape, Blobs):
        _clear(draw, shape, canvas, ss, width, line)
        inner = width / 2 if shape.ink else 0.0
        for c, r in zip(shape.centres, shape.radii):   # each puff hides the caps behind it, then gets its own
            (x, y), radius = canvas.pixel(c, ss), r * canvas.scale * ss - inner
            if radius <= 0:
                continue
            box = (x - radius, y - radius, x + radius, y + radius)
            draw.ellipse(box, fill=CLEAR)
            draw.chord(box, 270 - SNOW_CAP_DEGREES, 270 + SNOW_CAP_DEGREES, fill=SNOW_WHITE)
        return
    if isinstance(shape, Disc):
        if shape.opacity < 1.0:
            return
        if not shape.holds_snow:
            _clear(draw, shape, canvas, ss, width, line)
            return
        x, y = canvas.pixel(shape.centre, ss)
        a, b = shape.radius * math.sqrt(2) / 2 * canvas.scale * ss, shape.radius * math.sqrt(2) / 4 * canvas.scale * ss
        draw.ellipse((x - a, y - b, x + a, y + b), fill=SNOW_WHITE, outline=ink if shape.ink else None, width=round(width) if shape.ink else 0)
        return
    if isinstance(shape, Upright):
        _clear(draw, shape, canvas, ss, width, line)
        xt, yt = canvas.pixel((shape.x, shape.y, shape.z1), ss)
        a, b = shape.radius * math.sqrt(2) / 2 * canvas.scale * ss, shape.radius * math.sqrt(2) / 4 * canvas.scale * ss
        draw.ellipse((xt - a, yt - b, xt + a, yt + b), fill=SNOW_WHITE, outline=ink if shape.ink else None, width=round(width) if shape.ink else 0)
        return
    if shape.width >= SNOW_LINE_WIDTH:
        _clear(draw, shape, canvas, ss, width, line)


__all__ = [
    "CLEAR",
    "SNOW_SLOPE",
    "SNOW_WHITE",
    "ISO_OUTLINE",
    "ISO_SUPERSAMPLE",
    "LEFT_SHADE",
    "RIGHT_SHADE",
    "SIDES",
    "Blobs",
    "Disc",
    "IsoCanvas",
    "Line",
    "Poly",
    "Shape",
    "Upright",
    "box_shapes",
    "canvas_for",
    "draw_shapes",
    "shade",
    "shape_bounds",
    "surface_normal",
    "upward",
]
