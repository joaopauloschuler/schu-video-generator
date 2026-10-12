"""Props for a ``stage`` (DESIGN.md §69.8): things that stand on the ground line or hang in the sky.

A built-in prop (:data:`PROP_KINDS`) is drawn from primitives only (rectangles, rounded
rectangles, circles, ellipses, polygons, lines and unions of them), filled with two colours
(``main`` and ``detail``, theme tokens by default, :data:`PROP_COLORS`) plus lighter and darker
shades of them and the characters' outline ink. Shapes are drawn in *prop units*: the origin at
the middle of the prop's foot, ``y`` up, the top at 1, then scaled to the prop's height. An SVG
prop (:func:`svg_prop`) is sanitised and loaded by :func:`vidgen.vector_mobject.load_vector`.

Either way the result is a :class:`Prop`: one group whose :meth:`Prop.feet` is the middle of its
bottom edge, so a stage places it like a character (``stage_layout``).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from manim import (
    BLACK,
    UP,
    WHITE,
    Circle,
    Ellipse,
    Line,
    ManimColor,
    Polygon,
    Rectangle,
    RoundedRectangle,
    Union,
    VGroup,
    VMobject,
    interpolate_color,
)

from vidgen.cartoon.character import OUTLINE_WIDTH, REFERENCE_HEIGHT, one_pixel_stroke, scale_strokes
from vidgen.config import CHARACTER_INK
from vidgen.errors import VidgenError
from vidgen.helpers import resolve_color
from vidgen.theme import Theme

#: The built-in props.
PROP_KINDS: tuple[str, ...] = (
    "table", "chair", "tree", "bush", "house", "door", "lamp", "sign", "box",
    "ball", "cloud", "sun", "moon", "rock", "plant", "laptop", "cup",
)
#: Each prop's height relative to a character's (the stage's ``size``) before its own ``scale``.
PROP_HEIGHTS: dict[str, float] = {
    "table": 0.42, "chair": 0.5, "tree": 1.7, "bush": 0.35, "house": 1.6, "door": 1.0, "lamp": 1.5,
    "sign": 0.75, "box": 0.3, "ball": 0.18, "cloud": 0.35, "sun": 0.4, "moon": 0.35, "rock": 0.22,
    "plant": 0.4, "laptop": 0.14, "cup": 0.09,
}
#: Height of an SVG prop relative to a character's, before its own ``scale``.
SVG_PROP_HEIGHT = 0.5
#: How high above the ground line (a fraction of the frame height) a prop hangs when it gives no
#: ``lift``: the sky props; every other prop stands on the ground (0).
PROP_LIFTS: dict[str, float] = {"cloud": 0.5, "sun": 0.5, "moon": 0.5}
#: Default (main, detail) colour of each prop: theme tokens, or a hex where no token fits every
#: theme (a white cloud).
PROP_COLORS: dict[str, tuple[str, str]] = {
    "table": ("secondary", "secondary"), "chair": ("accent", "accent"), "tree": ("tertiary", "secondary"),
    "bush": ("tertiary", "tertiary"), "house": ("secondary", "accent"), "door": ("accent", "highlight"),
    "lamp": ("dim", "highlight"), "sign": ("highlight", "secondary"), "box": ("secondary", "highlight"),
    "ball": ("accent", "highlight"), "cloud": ("#F4F6FA", "#F4F6FA"), "sun": ("highlight", "secondary"),
    "moon": ("highlight", "dim"), "rock": ("dim", "dim"), "plant": ("tertiary", "accent"),
    "laptop": ("dim", "primary"), "cup": ("primary", "secondary"),
}
#: The glass of a house's window (light in every theme, like a character's eye whites).
GLASS = "#D6EEF8"
#: How much a shade darkens (towards black) or lightens (towards white) a colour.
SHADE = 0.25
LIGHT = 0.4


@dataclass(frozen=True)
class _Paint:
    """The colours one prop is drawn with (hex strings)."""

    main: str
    detail: str
    ink: str = CHARACTER_INK

    @staticmethod
    def _mix(color: str, towards: ManimColor, amount: float) -> str:
        return interpolate_color(ManimColor(color), towards, amount).to_hex()

    def dark(self, color: str) -> str:
        return self._mix(color, BLACK, SHADE)

    def light(self, color: str) -> str:
        return self._mix(color, WHITE, LIGHT)


class Prop(VGroup):
    """A prop on a stage: its drawn shapes, ``name`` (the layout dump and action targets use it),
    ``kind`` (a :data:`PROP_KINDS` name or ``svg``) and ``facing``. ``height_factor``: its
    height in the heights of a character next to it (the stage sets it; ``None``: not known).
    ``held_by`` / ``hand``: the character holding it and which hand (DESIGN.md §69.27)."""

    def __init__(self, *drawn: VMobject, name: str, kind: str, facing: str = "right") -> None:
        super().__init__(*drawn)
        self.name = name
        self.kind = kind
        self.facing = facing
        self.height_factor: float | None = None
        self.held_by: str | None = None
        self.hand: str | None = None

    def feet(self) -> np.ndarray:
        """The middle of the prop's bottom edge (where it stands)."""
        return self.get_bottom()


# ----- primitives (prop units) ----------------------------------------------------------------


def _ink(mob: VMobject, fill: str, paint: _Paint, *, outline: bool = True) -> VMobject:
    mob.set_fill(fill, opacity=1)
    return mob.set_stroke(paint.ink, width=OUTLINE_WIDTH if outline else 0)


def _rect(x0: float, y0: float, x1: float, y1: float, fill: str, paint: _Paint, *, radius: float = 0.0, outline: bool = True) -> VMobject:
    width, height = x1 - x0, y1 - y0
    mob = RoundedRectangle(width=width, height=height, corner_radius=radius) if radius > 0 else Rectangle(width=width, height=height)
    return _ink(mob.move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0.0]), fill, paint, outline=outline)


def _circle(cx: float, cy: float, r: float, fill: str, paint: _Paint, *, outline: bool = True) -> VMobject:
    return _ink(Circle(radius=r).move_to([cx, cy, 0.0]), fill, paint, outline=outline)


def _ellipse(cx: float, cy: float, w: float, h: float, fill: str, paint: _Paint, *, angle: float = 0.0, outline: bool = True) -> VMobject:
    mob = Ellipse(width=w, height=h).rotate(math.radians(angle)).move_to([cx, cy, 0.0])
    return _ink(mob, fill, paint, outline=outline)


def _poly(points: list[tuple[float, float]], fill: str, paint: _Paint, *, round_by: float = 0.0, outline: bool = True) -> VMobject:
    mob = Polygon(*(np.array([x, y, 0.0]) for x, y in points))
    if round_by > 0:
        mob.round_corners(round_by)
    return _ink(mob, fill, paint, outline=outline)


def _line(x0: float, y0: float, x1: float, y1: float, color: str, width: float = OUTLINE_WIDTH) -> VMobject:
    return Line([x0, y0, 0.0], [x1, y1, 0.0], stroke_width=width, color=color)


def _blob(circles: list[tuple[float, float, float]], fill: str, paint: _Paint, *, flat_bottom: float | None = None) -> VMobject:
    """One outlined shape: the union of circles (cx, cy, r), cut flat at ``flat_bottom`` by a
    rectangle under the circles' middles."""
    shapes: list[VMobject] = [Circle(radius=r).move_to([cx, cy, 0.0]) for cx, cy, r in circles]
    if flat_bottom is not None:
        xs = [cx for cx, _, _ in circles]
        top = min(cy for _, cy, _ in circles)
        shapes.append(Rectangle(width=max(xs) - min(xs), height=top - flat_bottom).move_to([(max(xs) + min(xs)) / 2, (top + flat_bottom) / 2, 0.0]))
    return _ink(Union(*shapes), fill, paint)


# ----- the props (prop units: feet at the origin, top at 1) -------------------------------------


def _table(p: _Paint) -> list[VMobject]:
    legs = p.dark(p.main)
    return [
        _rect(-0.68, 0.0, -0.56, 0.86, legs, p), _rect(0.56, 0.0, 0.68, 0.86, legs, p),
        _rect(-0.74, 0.76, 0.74, 0.88, legs, p),
        _rect(-0.82, 0.86, 0.82, 1.0, p.main, p, radius=0.04),
    ]


def _chair(p: _Paint) -> list[VMobject]:
    dark = p.dark(p.main)
    return [
        _rect(-0.34, 0.0, -0.26, 0.46, dark, p), _rect(0.26, 0.0, 0.34, 0.46, dark, p),
        _rect(-0.40, 0.44, -0.22, 1.0, p.main, p, radius=0.04),
        _rect(-0.40, 0.44, 0.40, 0.54, p.main, p, radius=0.03),
        _rect(-0.36, 0.68, -0.26, 0.86, p.light(p.main), p, outline=False),
    ]


def _tree(p: _Paint) -> list[VMobject]:
    crown = _blob([(0.0, 0.7, 0.3), (-0.24, 0.54, 0.22), (0.24, 0.54, 0.22)], p.main, p)
    return [
        _poly([(-0.1, 0.0), (0.1, 0.0), (0.07, 0.5), (-0.07, 0.5)], p.dark(p.detail), p),
        crown,
        _circle(-0.1, 0.78, 0.07, p.light(p.main), p, outline=False),
        _circle(0.16, 0.6, 0.05, p.light(p.main), p, outline=False),
    ]


def _bush(p: _Paint) -> list[VMobject]:
    return [
        _blob([(-0.48, 0.4, 0.4), (0.0, 0.55, 0.45), (0.48, 0.4, 0.4)], p.main, p, flat_bottom=0.0),
        _circle(-0.15, 0.72, 0.08, p.light(p.main), p, outline=False),
        _circle(0.38, 0.52, 0.06, p.light(p.main), p, outline=False),
    ]


def _house(p: _Paint) -> list[VMobject]:
    return [
        _rect(0.26, 0.66, 0.38, 0.94, p.dark(p.detail), p),
        _rect(-0.5, 0.0, 0.5, 0.62, p.main, p),
        _poly([(-0.62, 0.58), (0.62, 0.58), (0.0, 1.0)], p.detail, p, round_by=0.03),
        _rect(0.08, 0.0, 0.32, 0.38, p.dark(p.detail), p, radius=0.03),
        _circle(0.27, 0.19, 0.018, p.light(p.main), p, outline=False),
        _rect(-0.38, 0.24, -0.12, 0.46, GLASS, p),
        _line(-0.25, 0.24, -0.25, 0.46, p.ink), _line(-0.38, 0.35, -0.12, 0.35, p.ink),
    ]


def _door(p: _Paint) -> list[VMobject]:
    dark = p.dark(p.main)
    return [
        _rect(-0.3, 0.0, 0.3, 1.0, p.dark(dark), p),
        _rect(-0.24, 0.0, 0.24, 0.94, p.main, p, radius=0.02),
        _rect(-0.17, 0.54, 0.17, 0.86, dark, p, outline=False),
        _rect(-0.17, 0.08, 0.17, 0.44, dark, p, outline=False),
        _circle(0.15, 0.49, 0.035, p.detail, p),
    ]


def _lamp(p: _Paint) -> list[VMobject]:
    return [
        _poly([(-0.12, 0.0), (0.12, 0.0), (0.08, 0.07), (-0.08, 0.07)], p.dark(p.main), p),
        _rect(-0.03, 0.06, 0.03, 0.8, p.main, p),
        _poly([(-0.07, 0.8), (0.07, 0.8), (0.1, 0.92), (-0.1, 0.92)], p.detail, p),
        _poly([(-0.15, 0.92), (0.15, 0.92), (0.0, 1.0)], p.dark(p.main), p, round_by=0.01),
    ]


def _sign(p: _Paint) -> list[VMobject]:
    wood = p.dark(p.detail)
    return [
        _rect(-0.035, 0.0, 0.035, 0.6, wood, p),
        _poly([(-0.4, 0.56), (0.3, 0.56), (0.44, 0.78), (0.3, 1.0), (-0.4, 1.0)], p.main, p, round_by=0.03),
        _line(-0.3, 0.84, 0.2, 0.84, p.dark(p.main), 2 * OUTLINE_WIDTH),
        _line(-0.3, 0.72, 0.08, 0.72, p.dark(p.main), 2 * OUTLINE_WIDTH),
    ]


def _box(p: _Paint) -> list[VMobject]:
    return [
        _poly([(0.36, 0.0), (0.56, 0.2), (0.56, 1.0), (0.36, 0.8)], p.dark(p.main), p),
        _poly([(-0.56, 0.8), (0.36, 0.8), (0.56, 1.0), (-0.36, 1.0)], p.light(p.main), p),
        _rect(-0.56, 0.0, 0.36, 0.8, p.main, p),
        _rect(-0.16, 0.0, -0.04, 0.8, p.detail, p, outline=False),
        _poly([(-0.16, 0.8), (-0.04, 0.8), (0.16, 1.0), (0.04, 1.0)], p.detail, p, outline=False),
    ]


def _ball(p: _Paint) -> list[VMobject]:
    r, band = 0.5, 0.11
    arc = [math.asin(band / r) * (2 * k / 8 - 1) for k in range(9)]
    right = [(r * math.cos(a), 0.5 + r * math.sin(a)) for a in arc]
    left = [(-x, y) for x, y in reversed(right)]
    stripe = _poly([*right, *left], p.detail, p, outline=False)
    return [
        _circle(0.0, 0.5, r, p.main, p, outline=False),
        stripe,
        _ellipse(-0.2, 0.75, 0.2, 0.12, p.light(p.main), p, angle=30, outline=False),
        Circle(radius=r).move_to([0.0, 0.5, 0.0]).set_fill(opacity=0).set_stroke(p.ink, width=OUTLINE_WIDTH),
    ]


def _cloud(p: _Paint) -> list[VMobject]:
    return [_blob([(-0.52, 0.4, 0.4), (0.05, 0.55, 0.45), (0.58, 0.36, 0.34)], p.main, p, flat_bottom=0.0)]


def _sun(p: _Paint) -> list[VMobject]:
    rays: list[VMobject] = []
    for k in range(12):
        a = 2 * math.pi * k / 12
        width = math.radians(9)
        pts = [(0.37 * math.cos(a - width), 0.5 + 0.37 * math.sin(a - width)), (0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)),
               (0.37 * math.cos(a + width), 0.5 + 0.37 * math.sin(a + width))]
        rays.append(_poly(pts, p.detail, p))
    return [*rays, _circle(0.0, 0.5, 0.31, p.main, p), _circle(-0.1, 0.6, 0.07, p.light(p.main), p, outline=False)]


def _moon(p: _Paint) -> list[VMobject]:
    outer = [(0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)) for a in np.linspace(math.radians(55), math.radians(305), 25)]
    # the inner edge: a circle through both tips, centred to the right
    tip_x, tip_y = outer[0][0], outer[0][1] - 0.5
    center_x = 0.36
    inner_r = math.hypot(tip_x - center_x, tip_y)
    start, end = math.atan2(-tip_y, tip_x - center_x), math.atan2(tip_y, tip_x - center_x)
    inner = [(center_x + inner_r * math.cos(a), 0.5 + inner_r * math.sin(a)) for a in np.linspace(start, end - 2 * math.pi, 25)]
    return [
        _poly([*outer, *inner[1:-1]], p.main, p),
        _circle(-0.3, 0.62, 0.06, p.dark(p.main), p, outline=False),
        _circle(-0.22, 0.3, 0.045, p.dark(p.main), p, outline=False),
    ]


def _rock(p: _Paint) -> list[VMobject]:
    return [
        _poly([(-0.6, 0.0), (-0.52, 0.5), (-0.18, 0.92), (0.28, 1.0), (0.56, 0.6), (0.64, 0.0)], p.main, p, round_by=0.12),
        _poly([(-0.36, 0.5), (-0.14, 0.8), (0.14, 0.84), (-0.06, 0.56)], p.light(p.main), p, round_by=0.04, outline=False),
    ]


def _plant(p: _Paint) -> list[VMobject]:
    return [
        _ellipse(-0.17, 0.66, 0.17, 0.5, p.dark(p.main), p, angle=35),
        _ellipse(0.17, 0.66, 0.17, 0.5, p.dark(p.main), p, angle=-35),
        _ellipse(0.0, 0.74, 0.18, 0.52, p.main, p),
        _poly([(-0.24, 0.0), (0.24, 0.0), (0.29, 0.4), (-0.29, 0.4)], p.detail, p),
        _rect(-0.34, 0.38, 0.34, 0.48, p.dark(p.detail), p, radius=0.02),
    ]


def _laptop(p: _Paint) -> list[VMobject]:
    return [
        _rect(-0.6, 0.08, 0.6, 1.0, p.main, p, radius=0.05),
        _rect(-0.5, 0.18, 0.5, 0.9, p.detail, p, outline=False),
        _poly([(-0.3, 0.8), (-0.1, 0.8), (-0.3, 0.6)], p.light(p.detail), p, outline=False),
        _rect(-0.72, 0.0, 0.72, 0.1, p.dark(p.main), p, radius=0.03),
    ]


def _cup(p: _Paint) -> list[VMobject]:
    handle = Circle(radius=0.17).move_to([0.36, 0.42, 0.0]).set_fill(opacity=0).set_stroke(p.ink, width=OUTLINE_WIDTH * 2.6)
    handle_fill = Circle(radius=0.17).move_to([0.36, 0.42, 0.0]).set_fill(opacity=0).set_stroke(p.main, width=OUTLINE_WIDTH * 1.2)
    return [
        handle, handle_fill,
        _poly([(-0.32, 0.0), (0.32, 0.0), (0.38, 0.7), (-0.38, 0.7)], p.main, p, round_by=0.04),
        _ellipse(0.0, 0.7, 0.76, 0.12, p.dark(p.detail), p),
        _line(-0.1, 0.8, -0.04, 1.0, p.light(p.main), 1.5 * OUTLINE_WIDTH),
        _line(0.08, 0.8, 0.14, 0.97, p.light(p.main), 1.5 * OUTLINE_WIDTH),
    ]


_DRAWERS: dict[str, Callable[[_Paint], list[VMobject]]] = {
    "table": _table, "chair": _chair, "tree": _tree, "bush": _bush, "house": _house, "door": _door,
    "lamp": _lamp, "sign": _sign, "box": _box, "ball": _ball, "cloud": _cloud, "sun": _sun,
    "moon": _moon, "rock": _rock, "plant": _plant, "laptop": _laptop, "cup": _cup,
}


# ----- building ---------------------------------------------------------------------------------


def prop_colors(kind: str, theme: Theme, main: str | None = None, detail: str | None = None) -> tuple[str, str]:
    """The (main, detail) hex colours of a ``kind`` prop: ``main`` / ``detail`` (a theme token or
    #hex) where given, else :data:`PROP_COLORS`."""
    default_main, default_detail = PROP_COLORS[kind]
    return resolve_color(main or default_main, theme), resolve_color(detail or default_detail, theme)


def _finish(prop: Prop, height: float, character_height: float, facing: str) -> Prop:
    """Scale ``prop`` (drawn with strokes for a :data:`REFERENCE_HEIGHT` character) to ``height``, strokes to a character ``character_height`` tall, feet at the origin,
    mirrored when facing left."""
    if facing not in ("right", "left"):
        raise VidgenError(f"prop '{prop.name}': facing must be right or left, got {facing!r}")
    prop.scale(height / prop.height)
    scale_strokes(prop, character_height / REFERENCE_HEIGHT, one_pixel_stroke())
    if facing == "left":
        prop.flip(UP)
    prop.shift(-prop.feet())
    return prop


def draw_prop(
    kind: str,
    *,
    height: float,
    theme: Theme,
    name: str | None = None,
    main: str | None = None,
    detail: str | None = None,
    facing: str = "right",
    character_height: float | None = None,
) -> Prop:
    """A built-in prop ``kind`` ``height`` Manim units tall, its feet at the origin, coloured
    ``main`` / ``detail`` (theme tokens or #hex; default :data:`PROP_COLORS`). Outlines are as
    wide as a character's ``character_height`` tall (default: ``height``), at least one pixel."""
    if kind not in _DRAWERS:
        raise VidgenError(f"unknown prop '{kind}' (props: {', '.join(PROP_KINDS)})")
    if height <= 0:
        raise VidgenError(f"prop '{name or kind}': height must be positive, got {height}")
    paint = _Paint(*prop_colors(kind, theme, main, detail))
    prop = Prop(*_DRAWERS[kind](paint), name=name or kind, kind=kind, facing=facing)
    return _finish(prop, height, character_height or height, facing)


def svg_prop(
    path: Path,
    *,
    height: float,
    name: str,
    theme: Theme | None = None,
    recolor: str = "none",
    facing: str = "right",
    where: str | None = None,
) -> Prop:
    """A prop drawn from the SVG file ``path`` (sanitised and loaded by
    :func:`~vidgen.vector_mobject.load_vector`): its ``viewBox`` ``height`` units tall, the middle
    of the box's bottom edge at the origin. ``recolor="theme"`` maps its colours to the theme's."""
    from vidgen.vector_mobject import load_vector

    picture = load_vector(path, height=height, recolor=recolor, theme=theme, where=where or path.name)
    prop = Prop(picture, name=name, kind="svg", facing=facing)
    if facing == "left":
        prop.flip(UP)
    return prop.shift(-prop.feet())


__all__ = [
    "PROP_COLORS",
    "PROP_HEIGHTS",
    "PROP_KINDS",
    "PROP_LIFTS",
    "SVG_PROP_HEIGHT",
    "Prop",
    "draw_prop",
    "prop_colors",
    "svg_prop",
]
