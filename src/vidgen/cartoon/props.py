"""Props for a ``stage`` (DESIGN.md §69.8): things that stand on the ground line or hang in the sky.

A built-in prop (:data:`PROP_KINDS`) is drawn from primitives only (rectangles, rounded
rectangles, circles, ellipses, polygons, lines and unions of them), filled with two colours
(``main`` and ``detail``, theme tokens by default, :data:`PROP_COLORS`) plus lighter and darker
shades of them and the characters' outline ink. Shapes are drawn in *prop units*: the origin at
the middle of the prop's foot, ``y`` up, the top at 1, then scaled to the prop's height. An SVG
prop (:func:`svg_prop`) is sanitised and loaded by :func:`vidgen.vector_mobject.load_vector`.

Either way the result is a :class:`Prop`: one group whose :meth:`Prop.feet` is the middle of its
bottom edge, so a stage places it like a character (``stage_layout``). A door and an umbrella are
drawn in two shapes, closed and open (:data:`PROP_SHAPES`, :meth:`Prop.show_shape`); a basket and an open
umbrella are held by a grip (:data:`PROP_GRIPS`, :meth:`Prop.grip_point`), DESIGN.md §69.37.
The :data:`FURNITURE` furnishes a room (§69.43); a picture and a clock hang on its wall
(:data:`PROP_HANGS`). The :data:`SMALL_PROPS` are everyday things to hold (§69.56): a book, a
letter and a gift open too.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from typing import Any
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

from vidgen.cartoon.character import (
    OUTLINE_WIDTH,
    REFERENCE_HEIGHT,
    anchor_mobject,
    anchor_placement,
    apply_matrix,
    one_pixel_stroke,
    scale_strokes,
    shape_drawing,
)
from vidgen.cartoon.living import LIVING_KINDS, LIVING_PART
from vidgen.cartoon.nature import FRUIT_COLOR, FRUIT_RADIUS, FRUIT_SHINE, FRUIT_SPOTS, FRUIT_STALK
from vidgen.cartoon.seating import (
    PROP_LEANS,
    PROP_SEATS,
    SEAT_PLACES,
    mirrored_lean,
    mirrored_places,
    mirrored_seat,
    svg_seat_and_lean,
)
from vidgen.cartoon.vehicles import VEHICLE_KINDS, VEHICLES, crank_degrees
from vidgen.config import CHARACTER_INK
from vidgen.errors import VidgenError
from vidgen.helpers import resolve_color
from vidgen.svgclean import CleanSvg
from vidgen.theme import Theme

#: The furniture among the built-in props (DESIGN.md §69.43): drawn as seen from the front of a
#: room, their backs to its wall (a bed and a desk side on, along it).
FURNITURE: tuple[str, ...] = (
    "sofa", "armchair", "bed", "bookshelf", "counter", "fridge", "picture", "rug", "houseplant", "clock", "tv", "desk",
    "fireplace",
)
#: The everyday small props (DESIGN.md §69.56): things to hold, give, open and put on a table.
SMALL_PROPS: tuple[str, ...] = ("cake", "muffin", "book", "phone", "letter", "gift", "balloons", "vase", "watering_can")
#: The built-in props.
PROP_KINDS: tuple[str, ...] = (
    "table", "chair", "tree", "bush", "house", "door", "lamp", "sign", "box",
    "ball", "cloud", "sun", "moon", "rock", "plant", "laptop", "cup", "basket", "umbrella", "napkin", "kettle",
    *SMALL_PROPS, *FURNITURE, *VEHICLE_KINDS,
)
#: Each prop's height relative to a character's (the stage's ``size``) before its own ``scale``.
PROP_HEIGHTS: dict[str, float] = {
    "table": 0.42, "chair": 0.26, "tree": 1.7, "bush": 0.35, "house": 1.6, "door": 1.0, "lamp": 1.5,
    "sign": 0.75, "box": 0.155, "ball": 0.18, "cloud": 0.35, "sun": 0.4, "moon": 0.35, "rock": 0.155,
    "plant": 0.4, "laptop": 0.14, "cup": 0.09, "basket": 0.2, "umbrella": 0.6, "napkin": 0.05,
    "sofa": 0.36, "armchair": 0.38, "bed": 0.34, "bookshelf": 0.9, "counter": 0.5, "fridge": 0.95,
    "picture": 0.3, "rug": 0.06, "houseplant": 0.75, "clock": 0.2, "tv": 0.55, "desk": 0.42, "fireplace": 0.75, "kettle": 0.15,
    "cake": 0.22, "muffin": 0.08, "book": 0.13, "phone": 0.13, "letter": 0.08, "gift": 0.2, "balloons": 1.1, "vase": 0.32,
    "watering_can": 0.22,
    **{kind: spec.height for kind, spec in VEHICLES.items()},
}
#: Props that hang on a wall: how far their bottom edge is above the floor, in the heights of a
#: character standing where they are (on top of any ``lift``).
PROP_HANGS: dict[str, float] = {"picture": 0.5, "clock": 0.85}
#: Props lying flat on the floor, which cast no shadow (a rug).
FLAT_PROPS: frozenset[str] = frozenset({"rug"})
#: Props drawn in more than one shape: kind -> its shape names, the first drawn unless the stage
#: asks for another (``open: true``); the ``open`` / ``close`` actions switch them.
PROP_SHAPES: dict[str, tuple[str, ...]] = {
    "door": ("closed", "open"), "umbrella": ("closed", "open"), "toy_rocket": ("folded", "chute"),
    "book": ("closed", "open"), "letter": ("closed", "open"), "gift": ("closed", "open"),
}
#: Where a balloons' strings meet (prop units): a hand holds them there, just above the weight.
BALLOON_KNOT = (0.0, 0.07)
#: A watering can's grip (the top of its handle) and the middle of its spout's rose (prop units, as
#: drawn facing right): the ``pour`` action tilts it about the grip, the water leaves the rose.
WATERING_GRIP = (-0.05, 0.75)
WATERING_SPOUT = (0.7, 0.64)
#: Where a hand holds a prop, in prop units as drawn facing right, per (kind, shape) (``None``: a
#: prop with one shape); a prop or shape not listed is held by its middle. A basket hangs from
#: its handle; an open umbrella is held by its shaft above the hook; balloons by their strings, a
#: watering can by its handle.
PROP_GRIPS: dict[tuple[str, str | None], tuple[float, float]] = {
    ("basket", None): (0.0, 0.94), ("umbrella", "open"): (0.0, 0.16),
    ("balloons", None): BALLOON_KNOT, ("watering_can", None): WATERING_GRIP,
}
#: Height of an SVG prop relative to a character's, before its own ``scale``.
SVG_PROP_HEIGHT = 0.5
#: How high above the ground line (a fraction of the frame height) a prop hangs when it gives no
#: ``lift``: the sky props; every other prop stands on the ground (0).
PROP_LIFTS: dict[str, float] = {"cloud": 0.5, "sun": 0.5, "moon": 0.5}
#: Default (main, detail) colour of each prop: theme tokens, or a hex where no token fits every
#: theme (a white cloud, a napkin's light cloth).
PROP_COLORS: dict[str, tuple[str, str]] = {
    "table": ("secondary", "secondary"), "chair": ("accent", "accent"), "tree": ("tertiary", "secondary"),
    "bush": ("tertiary", "tertiary"), "house": ("secondary", "accent"), "door": ("accent", "highlight"),
    "lamp": ("dim", "highlight"), "sign": ("highlight", "secondary"), "box": ("secondary", "highlight"),
    "ball": ("accent", "highlight"), "cloud": ("#F4F6FA", "#F4F6FA"), "sun": ("highlight", "secondary"),
    "moon": ("highlight", "dim"), "rock": ("dim", "dim"), "plant": ("tertiary", "accent"),
    "laptop": ("dim", "primary"), "cup": ("primary", "secondary"), "basket": ("secondary", "accent"),
    "umbrella": ("primary", "dim"), "napkin": ("#F4F6FA", "accent"),
    "sofa": ("primary", "highlight"), "armchair": ("accent", "highlight"), "bed": ("secondary", "primary"),
    "bookshelf": ("secondary", "accent"), "counter": ("tertiary", "dim"), "fridge": ("#F4F6FA", "dim"),
    "picture": ("secondary", "primary"), "rug": ("accent", "highlight"), "houseplant": ("tertiary", "secondary"),
    "clock": ("#F4F6FA", "secondary"), "tv": ("secondary", "primary"), "desk": ("secondary", "accent"),
    "fireplace": ("dim", "secondary"), "kettle": ("accent", "dim"),
    "cake": ("accent", "highlight"), "muffin": ("secondary", "accent"), "book": ("primary", "highlight"),
    "phone": ("#2B2F3A", "primary"), "letter": ("#FBF8EF", "accent"), "gift": ("primary", "highlight"),
    "balloons": ("accent", "highlight"), "vase": ("primary", "accent"), "watering_can": ("tertiary", "highlight"),
    "bicycle": ("primary", "accent"), "car": ("accent", "highlight"), "bus": ("highlight", "primary"),
    "boat": ("highlight", "accent"), "hot_air_balloon": ("accent", "secondary"), "toy_rocket": ("primary", "accent"),
}
#: The glass of a house's window (light in every theme, like a character's eye whites).
GLASS = "#D6EEF8"
#: Light cloth (a bed's sheet and pillow) and a television's dark case: fixed, as no theme token
#: is light (or dark) in every theme.
CLOTH = "#F4F6FA"
TV_CASE = "#2B2F3A"
#: A fireplace's sooty hollow and its logs (fixed: dark and wooden in every theme).
HEARTH_HOLLOW = "#2A1F1C"
LOG_WOOD = "#7A4E2D"
#: Small props (DESIGN.md §69.56), fixed where no theme token fits every theme: a candle's flame
#: and its bright core, a page and the lines written on it, green stems and leaves, a flower's heart.
CANDLE_FLAME = "#FFB547"
LIGHT_FLAME = "#FFF1B8"
PAPER = "#FBF8EF"
PAGE_TEXT = "#8A8F99"
STEM = "#4E8A3E"
FLOWER_HEART = "#F6C945"
#: Balloon strings: a mid grey that shows on light and dark backgrounds.
BALLOON_STRING = "#9AA0AA"
#: The attribute giving a tree's fruit member the index of its spot (:data:`FRUIT_SPOTS`).
FRUIT_INDEX = "fruit_index"
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
    ``held_by`` / ``hand``: the character holding it and which hand (DESIGN.md §69.27).
    ``seat`` / ``lean``: the middle of its seat line (x, y) and the edges a character leans its
    back on (left x, right x), in prop units as it faces (``None``: it has none; DESIGN.md §69.28).
    ``seat_places``: the x of each place on a seat for more than one sitter (a sofa, a bed), prop
    units as it faces (empty: one place, the seat's middle; §69.43).

    ``shapes`` (DESIGN.md §69.37): a prop drawn in several shapes (a door or an umbrella closed and open)
    gets them instead of ``drawn``, shape name -> its members, the first shown. Every shape stays
    in the family for the prop's life; the hidden ones have no points (like a character's part
    shapes, §69.22), and :meth:`show_shape` draws another from its points in prop units through an
    invisible anchor that moves, scales and mirrors with the prop. ``grips``: shape (``None`` for
    a prop with one shape) -> where a hand holds it, prop units as drawn facing right.
    ``anchored``: give it an anchor even without shapes or grips (a prop that moves by itself
    places its moving parts by it, DESIGN.md §69.54)."""

    def __init__(
        self, *drawn: VMobject, name: str, kind: str, facing: str = "right",
        seat: tuple[float, float] | None = None, lean: tuple[float, float] | None = None,
        shapes: Mapping[str, Sequence[VMobject]] | None = None,
        grips: Mapping[str | None, tuple[float, float]] | None = None,
        seat_places: Sequence[float] = (),
        wheels: Sequence[tuple[VMobject, tuple[float, float]]] = (),
        crank: tuple[VMobject, tuple[float, float]] | None = None,
        anchored: bool = False,
    ) -> None:
        super().__init__(*drawn)
        self.name = name
        self.kind = kind
        self.facing = facing
        self.height_factor: float | None = None
        self.held_by: str | None = None
        self.hand: str | None = None
        #: Whether it stands above the floor: lifted (a basket on a counter) or hung on a wall (the
        #: stage sets it; lint's ``prop_overlap`` leaves such props out).
        self.raised = False
        self.seat = seat
        self.lean = lean
        self.seat_places = tuple(seat_places)
        self.grips = dict(grips or {})
        #: The shape it shows (``None``: a prop with one shape).
        self.shape: str | None = None
        self._members: dict[str, list[VMobject]] = {}
        self._drawings: dict[str, tuple[np.ndarray, ...]] = {}
        self._anchor: VMobject | None = None
        #: A vehicle's turning parts (DESIGN.md §69.52): each wheel's group and axle, the cranks'
        #: (prop units as drawn facing right), and how far they have turned (degrees as drawn).
        self.wheels = list(wheels)
        self.crank = crank
        self.wheel_angle = 0.0
        self.crank_angle = 0.0
        #: The y of the ground line under it while it rides in depth (``None``: its stage's).
        self.ground_y: float | None = None
        #: How far a vehicle is turned about its feet now (degrees counterclockwise on screen: a
        #: boat rocking, a toy rocket's nose along its way, DESIGN.md §69.53).
        self.tilt = 0.0
        #: Where a boat rests on the water (its feet before bobbing; ``None``: not afloat), and a
        #: flying vehicle's last flight: its course and seconds (the rocket's smoke reads it).
        self.afloat: tuple[float, float] | None = None
        self.flight: tuple[Any, float] | None = None
        if shapes or self.grips or self.wheels or kind in VEHICLES or anchored:
            self._anchor = anchor_mobject()   # drawn in prop units: the placement starts as the identity
            self.add(self._anchor)
        for shape, members in (shapes or {}).items():
            group = VGroup(*members)
            self.add(group)
            self._members[shape] = group.family_members_with_points()
            self._drawings[shape] = shape_drawing(group)
            if self.shape is None:
                self.shape = shape
            else:
                for member in self._members[shape]:
                    member.points = np.zeros((0, 3))

    @property
    def shapes(self) -> tuple[str, ...]:
        """The shapes it can show (empty: it has one)."""
        return tuple(self._members)

    def show_shape(self, shape: str) -> Prop:
        """Show ``shape`` instead of the shape shown now, where the prop is now (its size,
        facing and place kept); only points change, the family stays as it is."""
        if shape not in self._members:
            known = ", ".join(self._members) or "it has one shape"
            raise VidgenError(f"prop '{self.name}' has no shape '{shape}' ({known})")
        if shape == self.shape or self.shape is None or self._anchor is None:
            return self
        placement = anchor_placement(self._anchor)
        for member in self._members[self.shape]:
            member.points = np.zeros((0, 3))
        for member, points in zip(self._members[shape], self._drawings[shape]):
            member.points = apply_matrix(placement, points)
        self.shape = shape
        return self

    def shape_width(self, shape: str) -> float:
        """How wide it is when it shows ``shape``, at its size now (Manim units)."""
        if shape not in self._drawings or self._anchor is None:
            raise VidgenError(f"prop '{self.name}' has no shape '{shape}'")
        placed = [apply_matrix(anchor_placement(self._anchor), points) for points in self._drawings[shape] if len(points)]
        xs = np.concatenate([p[:, 0] for p in placed])
        return float(xs.max() - xs.min())

    @property
    def grip(self) -> tuple[float, float] | None:
        """Where a hand holds the shape it shows (prop units), ``None``: by its middle."""
        return self.grips.get(self.shape)

    def grip_point(self) -> np.ndarray:
        """Where a hand holds it on screen now: its :attr:`grip`, else its middle."""
        grip = self.grip
        if grip is None or self._anchor is None:
            return np.array(self.get_center(), dtype=float)
        placed = apply_matrix(anchor_placement(self._anchor), np.array([[grip[0], grip[1], 0.0]]))[0]
        return np.array([placed[0], placed[1], 0.0])

    def feet(self) -> np.ndarray:
        """Where the prop stands: the middle of its bottom edge; for one with shapes or a grip the
        point of its bottom edge below where it was drawn from (an umbrella's tip or hook, the
        same for each shape)."""
        bottom = self.get_bottom()
        if self._anchor is not None:
            bottom[0] = self._anchor.points[0][0]
        return bottom

    def seat_point(self, place: int | None = None) -> np.ndarray | None:
        """The middle of its seat line on screen now, or of its ``place`` (an index of
        :attr:`seat_places`) on the seat line (``None``: it has no seat)."""
        if self.seat is None:
            return None
        x = self.seat[0] if place is None else self.seat_places[place]
        return self.feet() + np.array([x, self.seat[1], 0.0]) * self.height

    def lean_edges(self) -> tuple[float, float] | None:
        """The x on screen of the edges a character leans on, left and right (``None``: none)."""
        if self.lean is None:
            return None
        x = float(self.feet()[0])
        return x + self.lean[0] * self.height, x + self.lean[1] * self.height

    # ----- vehicles (DESIGN.md §69.52) ---------------------------------------------------------

    @property
    def is_vehicle(self) -> bool:
        """Whether it is a vehicle (riders get in, it rides with them)."""
        return self.kind in VEHICLES

    def prop_point(self, x: float, y: float) -> np.ndarray:
        """Where the point (``x``, ``y``) in prop units as drawn facing right is on screen now (its
        place, size and facing; a prop drawn with an anchor: shapes, a grip or wheels)."""
        return self.prop_points(np.array([[float(x), float(y), 0.0]]))[0]

    def prop_points(self, points: np.ndarray) -> np.ndarray:
        """:meth:`prop_point` for many points at once: ``points`` (n x 3, prop units as drawn
        facing right) where they are on screen now (n x 3, z 0)."""
        if self._anchor is None:
            raise VidgenError(f"prop '{self.name}' has no anchor to place points by")
        placed = apply_matrix(anchor_placement(self._anchor), np.asarray(points, dtype=float))
        placed[:, 2] = 0.0
        return placed

    def drawn_points(self, points: np.ndarray) -> np.ndarray:
        """The inverse of :meth:`prop_points`: ``points`` on screen now (n x 3) in prop units as
        drawn facing right (n x 3, z 0)."""
        if self._anchor is None:
            raise VidgenError(f"prop '{self.name}' has no anchor to place points by")
        drawn = apply_matrix(np.linalg.inv(anchor_placement(self._anchor)), np.asarray(points, dtype=float))
        drawn[:, 2] = 0.0
        return drawn

    @property
    def anchor(self) -> VMobject | None:
        """Its invisible anchor (``None``: it has none), which maps prop units to the screen."""
        return self._anchor

    @property
    def unit(self) -> float:
        """How long one prop unit is on screen now (its height as built, times any scaling)."""
        if self._anchor is None:
            return float(self.height)
        return float(np.linalg.norm(self.prop_point(0.0, 1.0) - self.prop_point(0.0, 0.0)))

    @property
    def standing_height(self) -> float:
        """How tall it is built, times any scaling since (:attr:`unit`): its shadow grows and
        shrinks with it as it rides in depth."""
        return self.unit

    def pose_at(self, x: float, y: float, degrees: float = 0.0) -> Prop:
        """Put the middle of its foot as drawn (prop units (0, 0)) at (``x``, ``y``) on screen,
        turned ``degrees`` (counterclockwise) about it: the :attr:`tilt` it had is undone first, so
        each call sets the pose afresh (a boat bobbing, a balloon or a toy rocket flying)."""
        pivot = self.prop_point(0.0, 0.0)
        if self.tilt:
            self.rotate(-np.radians(self.tilt), about_point=pivot)
        self.shift(np.array([float(x), float(y), 0.0]) - pivot)
        if degrees:
            self.rotate(np.radians(degrees), about_point=np.array([float(x), float(y), 0.0]))
        self.tilt = float(degrees)
        return self

    def turn_wheels(self, degrees: float) -> Prop:
        """Turn its wheels ``degrees`` (counterclockwise as drawn facing right) about their axles,
        and its cranks by :func:`~vidgen.cartoon.vehicles.crank_degrees` of that."""
        mirror = 1.0 if self.facing == "right" else -1.0
        for group, (x, y) in self.wheels:
            group.rotate(np.radians(degrees * mirror), about_point=self.prop_point(x, y))
        self.wheel_angle += degrees
        if self.crank is not None:
            turn = crank_degrees(degrees)
            group, (x, y) = self.crank
            group.rotate(np.radians(turn * mirror), about_point=self.prop_point(x, y))
            self.crank_angle += turn
        return self


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


def _door(p: _Paint) -> dict[str, list[VMobject]]:
    """Closed, and open: the doorway dark, the leaf swung towards the viewer on its hinge side (the
    left as drawn), seen nearly edge on and a little taller at its near edge."""
    dark = p.dark(p.main)
    frame = _rect(-0.3, 0.0, 0.3, 1.0, p.dark(dark), p)
    closed = [
        frame,
        _rect(-0.24, 0.0, 0.24, 0.94, p.main, p, radius=0.02),
        _rect(-0.17, 0.54, 0.17, 0.86, dark, p, outline=False),
        _rect(-0.17, 0.08, 0.17, 0.44, dark, p, outline=False),
        _circle(0.15, 0.49, 0.035, p.detail, p),
    ]
    beyond = interpolate_color(ManimColor(p.ink), ManimColor(p.main), 0.25).to_hex()
    opened = [
        _rect(-0.3, 0.0, 0.3, 1.0, p.dark(dark), p),
        _rect(-0.24, 0.0, 0.24, 0.94, beyond, p),
        _poly([(-0.24, 0.0), (-0.24, 0.94), (-0.44, 1.0), (-0.44, 0.0)], p.main, p),
        _poly([(-0.27, 0.54), (-0.27, 0.86), (-0.39, 0.9), (-0.39, 0.54)], dark, p, outline=False),
        _poly([(-0.27, 0.08), (-0.27, 0.44), (-0.39, 0.44), (-0.39, 0.06)], dark, p, outline=False),
        _circle(-0.41, 0.49, 0.03, p.detail, p),
    ]
    return {"closed": closed, "open": opened}


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


def _handle(points: list[tuple[float, float]], color: str, paint: _Paint, width: float = 2.6) -> list[VMobject]:
    """A thick bar along ``points`` (a cup's or a basket's handle, an umbrella's shaft): an ink
    stroke ``width`` outlines wide with a ``color`` stroke inside it."""
    path = [np.array([x, y, 0.0]) for x, y in points]
    outer = VMobject().set_points_smoothly(path).set_fill(opacity=0).set_stroke(paint.ink, width=OUTLINE_WIDTH * width)
    inner = VMobject().set_points_smoothly(path).set_fill(opacity=0).set_stroke(color, width=OUTLINE_WIDTH * (width - 1.4))
    return [outer, inner]


def _arc(cx: float, cy: float, r: float, start: float, end: float, steps: int = 12) -> list[tuple[float, float]]:
    """Points on a circle about (cx, cy) from angle ``start`` to ``end`` (degrees)."""
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in np.linspace(start, end, steps)]


def _basket(p: _Paint) -> list[VMobject]:
    weave = p.dark(p.main)
    body = _poly([(-0.5, 0.0), (0.5, 0.0), (0.6, 0.5), (-0.6, 0.5)], p.main, p, round_by=0.04)
    bands = [_line(-0.55 + 0.1 * (y / 0.5), y, 0.55 - 0.1 * (y / 0.5), y, weave, 1.5 * OUTLINE_WIDTH) for y in (0.17, 0.33)]
    slats = [_line(x, 0.03, x * 1.2, 0.47, weave, 1.2 * OUTLINE_WIDTH) for x in (-0.3, 0.0, 0.3)]
    cloth = _poly([(-0.46, 0.5), (-0.3, 0.66), (-0.12, 0.55), (0.06, 0.64), (0.2, 0.5)], p.detail, p, round_by=0.03)
    return [
        *_handle(_arc(0.0, 0.52, 0.42, 180, 0, 15), p.main, p),
        body, *bands, *slats, cloth,
        _rect(-0.64, 0.46, 0.64, 0.56, weave, p, radius=0.03),
    ]


def _umbrella(p: _Paint) -> dict[str, list[VMobject]]:
    wood, dark = p.dark(p.detail), p.dark(p.main)
    closed = [
        _line(0.0, 0.0, 0.0, 0.08, p.ink, 2 * OUTLINE_WIDTH),
        _poly([(0.0, 0.05), (0.1, 0.3), (0.09, 0.62), (0.03, 0.74), (-0.03, 0.74), (-0.09, 0.62), (-0.1, 0.3)], p.main, p, round_by=0.03),
        _line(0.0, 0.12, 0.05, 0.66, dark, 1.5 * OUTLINE_WIDTH),
        _rect(-0.1, 0.42, 0.1, 0.47, p.detail, p, radius=0.01),
        *_handle([(0.0, 0.72), (0.0, 0.9), *_arc(0.1, 0.9, 0.1, 180, 0, 9)[1:], (0.2, 0.84)], wood, p),
    ]
    rim, top = 0.74, 0.96
    dome = [(0.5 * math.cos(a), rim + (top - rim) * math.sin(a)) for a in np.linspace(0.0, math.pi, 25)]
    ribs = (-0.5, -0.25, 0.0, 0.25, 0.5)
    scallops = [
        (x0 + (x1 - x0) * k / 6, rim + 0.05 * math.sin(math.pi * k / 6))
        for x0, x1 in zip(ribs, ribs[1:]) for k in range(1, 7)
    ][:-1]
    panels = [
        _poly([(0.0, top), (x0, rim), *[(x0 + (x1 - x0) * k / 6, rim + 0.05 * math.sin(math.pi * k / 6)) for k in range(1, 6)], (x1, rim)],
              p.light(p.main), p, outline=False)
        for x0, x1 in ((-0.25, 0.0), (0.25, 0.5))
    ]
    opened = [
        *_handle([(0.2, 0.1), *_arc(0.1, 0.1, 0.1, 0, -180, 9), (0.0, 0.2), (0.0, rim)], wood, p),
        _poly([*dome, *scallops], p.main, p),
        *panels,
        *[_line(0.0, top, x, rim, dark, 1.2 * OUTLINE_WIDTH) for x in ribs[1:-1]],
        _line(0.0, top - 0.01, 0.0, 1.0, p.ink, 2 * OUTLINE_WIDTH),
    ]
    return {"closed": closed, "open": opened}


def _napkin(p: _Paint) -> list[VMobject]:
    def at(u: float, v: float) -> tuple[float, float]:   # (0..1 across, 0..1 back) -> the cloth lying flat, seen from the front
        return (-1.1 + 2.0 * u + 0.4 * v, v)

    def band(u0: float, u1: float, v0: float, v1: float) -> VMobject:
        return _poly([at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v1)], p.detail, p, outline=False)

    return [
        _poly([at(0, 0), at(1, 0), at(1, 1), at(0, 1)], p.main, p),
        band(0.0, 1.0, 0.4, 0.6), band(0.2, 0.32, 0.0, 1.0), band(0.68, 0.8, 0.0, 1.0),
        _poly([at(0.82, 0.0), at(1.0, 0.0), at(1.0, 0.5)], p.light(p.detail), p, round_by=0.02),
    ]


def _kettle(p: _Paint) -> list[VMobject]:
    """A round-bellied kettle, its spout up to the right (the steam leaves its tip, DESIGN.md §69.55)."""
    dark = p.dark(p.main)
    return [
        _poly([(0.3, 0.14), (0.42, 0.4), (0.69, 0.66), (0.63, 0.72), (0.34, 0.5), (0.24, 0.3)], p.main, p, round_by=0.02),
        *_handle([(-0.3, 0.6), *_arc(0.0, 0.62, 0.3, 175, 5, 13)[1:-1], (0.3, 0.6)], p.detail, p),
        _poly([(-0.42, 0.04), (0.42, 0.04), (0.37, 0.58), (-0.37, 0.58)], p.main, p, round_by=0.08),
        _rect(-0.45, 0.0, 0.45, 0.08, dark, p, radius=0.03),
        _poly([(-0.3, 0.57), *_arc(0.0, 0.57, 0.3, 180, 0, 11)[1:-1], (0.3, 0.57)], p.light(p.main), p),
        _circle(0.0, 0.69, 0.05, p.detail, p),
        _ellipse(-0.2, 0.36, 0.1, 0.22, p.light(p.main), p, angle=-10, outline=False),
    ]


# ----- everyday small props (DESIGN.md §69.56) ----------------------------------------------------


def _icing(left: float, right: float, top: float, drip: float, p: _Paint) -> VMobject:
    """A band of white icing on a cake's tier: flat at ``top``, its lower edge dripping down to
    ``drip`` every other step."""
    steps = 10
    edge = [(right - (right - left) * k / steps, top - 0.05 - (drip if k % 2 else 0.0)) for k in range(steps + 1)]
    return _poly([(left, top), (right, top), *edge], CLOTH, p, round_by=0.015)


def _cake(p: _Paint) -> list[VMobject]:
    """A two-tier cake on a plate, icing dripping down each tier, three candles alight."""
    candles = (-0.2, 0.0, 0.2)
    return [
        _rect(-0.2, 0.0, 0.2, 0.05, p.dark(p.detail), p, radius=0.01),
        _ellipse(0.0, 0.06, 1.5, 0.1, CLOTH, p),
        _rect(-0.6, 0.08, 0.6, 0.44, p.main, p, radius=0.04),
        *[_circle(x, 0.2, 0.035, p.detail, p, outline=False) for x in (-0.4, -0.2, 0.0, 0.2, 0.4)],
        _icing(-0.62, 0.62, 0.45, 0.06, p),
        _rect(-0.4, 0.45, 0.4, 0.7, p.main, p, radius=0.04),
        _icing(-0.42, 0.42, 0.72, 0.05, p),
        *[_rect(x - 0.03, 0.72, x + 0.03, 0.87, p.detail, p) for x in candles],
        *[_ellipse(x, 0.93, 0.07, 0.13, CANDLE_FLAME, p, outline=False) for x in candles],
        *[_ellipse(x, 0.915, 0.03, 0.06, LIGHT_FLAME, p, outline=False) for x in candles],
    ]


def _muffin(p: _Paint) -> list[VMobject]:
    """A muffin: a domed top over a ridged paper case, a few berries."""
    ridges = [_line(x, 0.03, x * 1.25, 0.47, p.dark(p.detail), 1.2 * OUTLINE_WIDTH) for x in (-0.24, -0.08, 0.08, 0.24)]
    return [
        _poly([(-0.36, 0.0), (0.36, 0.0), (0.46, 0.5), (-0.46, 0.5)], p.detail, p, round_by=0.03),
        *ridges,
        _blob([(0.0, 0.64, 0.36), (-0.3, 0.56, 0.22), (0.3, 0.56, 0.22)], p.main, p, flat_bottom=0.46),
        _ellipse(-0.14, 0.8, 0.18, 0.08, p.light(p.main), p, angle=15, outline=False),
        *[_circle(x, y, 0.045, p.dark(p.dark(p.main)), p, outline=False) for x, y in ((-0.25, 0.6), (0.06, 0.7), (0.26, 0.58), (0.12, 0.88))],
    ]


def _book(p: _Paint) -> dict[str, list[VMobject]]:
    """Closed: upright, its cover towards the viewer (the spine on the left); open: both pages
    spread towards the viewer, lines of text on them."""
    dark = p.dark(p.main)
    closed = [
        _rect(-0.36, 0.0, 0.36, 1.0, p.main, p, radius=0.03),
        _rect(-0.36, 0.0, -0.25, 1.0, dark, p, radius=0.02),
        _rect(-0.14, 0.6, 0.26, 0.8, p.detail, p, radius=0.02),
        _line(-0.1, 0.5, 0.22, 0.5, p.light(p.main), 1.5 * OUTLINE_WIDTH),
        _line(-0.1, 0.42, 0.12, 0.42, p.light(p.main), 1.5 * OUTLINE_WIDTH),
    ]
    text = [_line(side * 0.1, y, side * (0.62 - 0.1 * (k % 2)), y + 0.04, PAGE_TEXT, 1.2 * OUTLINE_WIDTH)
            for side in (-1, 1) for k, y in enumerate((0.78, 0.66, 0.54, 0.42, 0.3))]
    opened = [
        _poly([(-0.8, 0.04), (0.0, 0.0), (0.8, 0.04), (0.8, 0.96), (0.0, 0.92), (-0.8, 0.96)], p.main, p),
        _poly([(-0.75, 0.09), (0.0, 0.04), (0.0, 0.94), (-0.75, 1.0)], PAPER, p),
        _poly([(0.75, 0.09), (0.0, 0.04), (0.0, 0.94), (0.75, 1.0)], PAPER, p),
        *text,
        _poly([(0.5, 0.97), (0.56, 0.975), (0.56, 0.84), (0.53, 0.87), (0.5, 0.84)], p.detail, p, outline=False),
    ]
    return {"closed": closed, "open": opened}


def _phone(p: _Paint) -> list[VMobject]:
    """A mobile phone, its screen towards the viewer."""
    return [
        _rect(-0.27, 0.0, 0.27, 1.0, p.main, p, radius=0.07),
        _rect(-0.22, 0.1, 0.22, 0.88, p.detail, p, radius=0.02),
        _poly([(-0.2, 0.86), (-0.04, 0.86), (-0.2, 0.62)], p.light(p.detail), p, outline=False),
        _rect(-0.07, 0.925, 0.07, 0.945, p.light(p.main), p, outline=False),
        _circle(0.0, 0.05, 0.025, p.light(p.main), p, outline=False),
    ]


def _letter(p: _Paint) -> dict[str, list[VMobject]]:
    """Closed: a sealed envelope (flap down, a seal and a stamp); open: the sheet unfolded, its
    two folds showing, lines of writing and a signature."""
    fold = p.dark(p.main)
    closed = [
        _rect(-0.75, 0.0, 0.75, 1.0, p.main, p, radius=0.02),
        _poly([(-0.75, 0.0), (0.0, 0.48), (0.75, 0.0)], p.main, p),
        _poly([(-0.75, 1.0), (0.0, 0.42), (0.75, 1.0)], p.light(fold), p),
        _circle(0.0, 0.44, 0.09, p.detail, p),
        _rect(0.46, 0.68, 0.66, 0.92, p.detail, p),
        _rect(0.5, 0.72, 0.62, 0.88, p.light(p.detail), p, outline=False),
    ]
    writing = [_line(-0.3, y, 0.3 - 0.12 * (k % 3 == 2), y, PAGE_TEXT, 1.2 * OUTLINE_WIDTH) for k, y in enumerate((0.86, 0.78, 0.7, 0.58, 0.5, 0.42, 0.3))]
    signature = VMobject().set_points_smoothly([np.array([x, 0.14 + 0.04 * math.sin(9 * x), 0.0]) for x in np.linspace(0.02, 0.3, 9)])
    opened = [
        _rect(-0.4, 0.0, 0.4, 1.0, p.main, p),
        _line(-0.4, 0.34, 0.4, 0.34, fold, OUTLINE_WIDTH), _line(-0.4, 0.67, 0.4, 0.67, fold, OUTLINE_WIDTH),
        *writing,
        signature.set_fill(opacity=0).set_stroke(p.detail, width=1.5 * OUTLINE_WIDTH),
    ]
    return {"closed": closed, "open": opened}


def _star(cx: float, cy: float, r: float, fill: str, p: _Paint) -> VMobject:
    """A four-pointed sparkle about (``cx``, ``cy``), ``r`` from its middle to a tip."""
    points = [(cx + (r if k % 2 == 0 else 0.3 * r) * math.cos(math.pi * k / 4 + math.pi / 2),
               cy + (r if k % 2 == 0 else 0.3 * r) * math.sin(math.pi * k / 4 + math.pi / 2)) for k in range(8)]
    return _poly(points, fill, p, outline=False)


def _gift(p: _Paint) -> dict[str, list[VMobject]]:
    """Closed: a wrapped box with a ribbon and a bow on its lid; open: the lid leaning on its
    side, sparkles rising out of the box."""
    dark = p.dark(p.main)

    def body() -> list[VMobject]:   # each shape has its own members (§69.37)
        return [
            _rect(-0.5, 0.0, 0.5, 0.62, p.main, p),
            _rect(-0.07, 0.0, 0.07, 0.62, p.detail, p, outline=False),
            _rect(-0.5, 0.27, 0.5, 0.37, p.detail, p, outline=False),
        ]

    closed = [
        *body(),
        _rect(-0.55, 0.6, 0.55, 0.78, p.main, p, radius=0.02),
        _rect(-0.07, 0.6, 0.07, 0.78, p.detail, p, outline=False),
        _poly([(-0.03, 0.8), (-0.16, 0.66), (-0.1, 0.64), (0.0, 0.78)], p.dark(p.detail), p),
        _poly([(0.03, 0.8), (0.16, 0.66), (0.1, 0.64), (0.0, 0.78)], p.dark(p.detail), p),
        _ellipse(-0.15, 0.88, 0.28, 0.18, p.detail, p, angle=25),
        _ellipse(0.15, 0.88, 0.28, 0.18, p.detail, p, angle=-25),
        _circle(0.0, 0.82, 0.055, p.light(p.detail), p),
    ]
    lid = VGroup(_rect(-0.55, -0.09, 0.55, 0.09, p.main, p, radius=0.02), _rect(-0.07, -0.09, 0.07, 0.09, p.detail, p, outline=False))
    lid.rotate(math.radians(50)).move_to([0.78, 0.48, 0.0])   # leaning on the box: as tall as the closed gift
    opened = [
        _poly([(-0.5, 0.62), (0.5, 0.62), (0.44, 0.68), (-0.44, 0.68)], dark, p),
        *lid.submobjects,
        *body(),
        _star(-0.18, 0.84, 0.1, p.light(p.detail), p),
        _star(0.1, 0.91, 0.07, p.light(p.detail), p),
        _star(0.26, 0.78, 0.06, p.light(p.detail), p),
    ]
    return {"closed": closed, "open": opened}


def _balloons(p: _Paint) -> list[VMobject]:
    """Three balloons on strings tied to a small weight (the third in a lighter shade)."""
    balloons = ((-0.17, 0.81, p.main), (0.17, 0.84, p.detail), (0.0, 0.71, p.light(p.main)))
    strings: list[VMobject] = []
    drawn: list[VMobject] = []
    kx, ky = BALLOON_KNOT
    for k, (x, y, color) in enumerate(balloons):
        bottom = y - 0.18
        path = [np.array([x + (kx - x) * u + 0.025 * math.sin(math.pi * 2 * u + k), bottom + (ky - bottom) * u, 0.0]) for u in np.linspace(0.0, 1.0, 7)]
        strings.append(VMobject().set_points_smoothly(path).set_fill(opacity=0).set_stroke(BALLOON_STRING, width=OUTLINE_WIDTH))
        drawn += [
            _ellipse(x, y, 0.3, 0.36, color, p),
            _poly([(x - 0.03, bottom - 0.035), (x + 0.03, bottom - 0.035), (x, bottom + 0.01)], color, p),
            _ellipse(x - 0.07, y + 0.08, 0.06, 0.1, WHITE.to_hex(), p, angle=25, outline=False),
        ]
    return [*strings, _rect(-0.06, 0.0, 0.06, 0.06, p.dark(p.detail), p, radius=0.015), *drawn]


def _vase(p: _Paint) -> list[VMobject]:
    """A round vase with three flowers on green stems and two leaves."""
    flowers = ((-0.2, 0.8), (0.03, 0.89), (0.22, 0.76))
    stems = [_line(x * 0.25, 0.46, x, y - 0.04, STEM, 1.5 * OUTLINE_WIDTH) for x, y in flowers]
    leaves = [_ellipse(-0.13, 0.58, 0.07, 0.16, STEM, p, angle=40), _ellipse(0.14, 0.6, 0.07, 0.16, STEM, p, angle=-40)]
    blooms: list[VMobject] = []
    for x, y in flowers:
        blooms += [_circle(x + 0.06 * math.cos(a), y + 0.06 * math.sin(a), 0.05, p.detail, p) for a in np.linspace(math.pi / 2, math.pi / 2 + 2 * math.pi, 5, endpoint=False)]
        blooms.append(_circle(x, y, 0.035, FLOWER_HEART, p))
    return [
        *stems, *leaves, *blooms,
        _poly([(-0.16, 0.0), (0.16, 0.0), (0.25, 0.18), (0.12, 0.4), (0.14, 0.46), (-0.14, 0.46), (-0.12, 0.4), (-0.25, 0.18)], p.main, p, round_by=0.04),
        _rect(-0.16, 0.44, 0.16, 0.49, p.dark(p.main), p, radius=0.01),
        _ellipse(-0.12, 0.2, 0.05, 0.14, p.light(p.main), p, angle=-10, outline=False),
    ]


def _watering_can(p: _Paint) -> list[VMobject]:
    """A watering can: a round-shouldered body, a long spout up to the right with a rose, a
    handle arching over the top."""
    dark = p.dark(p.main)
    return [
        *_handle(_arc(-0.05, 0.5, 0.25, 180, 0, 13), p.main, p),
        _poly([(0.24, 0.1), (0.3, 0.26), (0.66, 0.6), (0.7, 0.54)], p.main, p),
        _ellipse(*WATERING_SPOUT, 0.08, 0.18, dark, p, angle=-35),
        _rect(-0.38, 0.0, 0.32, 0.5, p.main, p, radius=0.08),
        _rect(-0.38, 0.18, 0.32, 0.27, p.detail, p, outline=False),
        _ellipse(-0.03, 0.5, 0.5, 0.08, dark, p),
        _ellipse(-0.24, 0.36, 0.08, 0.16, p.light(p.main), p, outline=False),
    ]


# ----- furniture (DESIGN.md §69.43): seats at 0.14 of a character's height, below every generated
# character's hips, so a sitter's hips rest on the seat line (§69.36) ---------------------------------


def _upholstered(p: _Paint, half: float, arm: float, seat: float, cushions: int) -> list[VMobject]:
    """A sofa or an armchair from the front: a back with ``cushions`` cushions, a base, as many
    seat cushions whose tops are the seat line at ``seat``, and two arms; ``half`` the half width,
    ``arm`` an arm's width (prop units)."""
    dark, light = p.dark(p.main), p.light(p.main)
    inner = half - arm
    edges = np.linspace(-inner, inner, cushions + 1)
    gap = 0.02
    back = [_rect(-inner - 0.04, seat - 0.08, inner + 0.04, 1.0, p.main, p, radius=0.12)]
    back += [_rect(a + gap, seat + 0.04, b - gap, 0.9, light, p, radius=0.08) for a, b in zip(edges, edges[1:])]
    base = _rect(-half, 0.07, half, seat - 0.08, dark, p)
    seats = [_rect(a + gap, seat - 0.12, b - gap, seat, p.main, p, radius=0.04) for a, b in zip(edges, edges[1:])]
    arms = [_rect(x0, 0.07, x1, seat + 0.24, p.main, p, radius=0.09) for x0, x1 in ((-half, -inner), (inner, half))]
    feet = [_rect(x - 0.05, 0.0, x + 0.05, 0.08, p.dark(dark), p) for x in (-half + 0.12, half - 0.12)]
    return [*feet, *back, base, *seats, *arms]


def _sofa(p: _Paint) -> list[VMobject]:
    pillow = _poly([(-1.12, 0.4), (-0.84, 0.36), (-0.8, 0.62), (-1.08, 0.66)], p.detail, p, round_by=0.05)
    drawn = _upholstered(p, 1.45, 0.3, 0.39, 2)
    return [*drawn[:-2], pillow, *drawn[-2:]]


def _armchair(p: _Paint) -> list[VMobject]:
    drawn = _upholstered(p, 0.62, 0.22, 0.37, 1)
    button = _circle(0.0, 0.66, 0.05, p.detail, p)
    return [*drawn[:4], button, *drawn[4:]]


def _bed(p: _Paint) -> list[VMobject]:
    """Side on, along the wall: the headboard on the left as drawn facing right."""
    blanket = _poly([(-0.85, 0.2), (1.52, 0.2), (1.52, 0.41), (-0.85, 0.43)], p.detail, p, round_by=0.03)
    fold = _rect(-0.85, 0.2, -0.62, 0.45, p.light(p.detail), p, radius=0.02)
    return [
        _rect(-1.55, 0.1, 1.55, 0.26, p.dark(p.main), p),
        _rect(-1.5, 0.24, 1.5, 0.41, CLOTH, p, radius=0.05),
        _rect(-1.44, 0.38, -0.96, 0.58, CLOTH, p, radius=0.09),
        blanket, fold,
        _rect(-1.7, 0.0, -1.44, 1.0, p.main, p, radius=0.1),
        _rect(-1.64, 0.5, -1.5, 0.88, p.light(p.main), p, radius=0.05, outline=False),
        _rect(1.46, 0.0, 1.7, 0.62, p.main, p, radius=0.08),
    ]


def _books(p: _Paint, left: float, right: float, floor: float, top: float, seed: int) -> list[VMobject]:
    """A row of upright books from ``left`` to ``right`` on a shelf at ``floor``, at most ``top`` high
    (widths, heights and colours in a fixed order shifted by ``seed``; a gap left at the end)."""
    widths = (0.07, 0.05, 0.09, 0.06, 0.08, 0.05, 0.07)
    heights = (0.92, 0.78, 1.0, 0.85, 0.7, 0.95, 0.82)
    colors = (p.detail, p.light(p.detail), p.dark(p.detail), p.light(p.main), p.dark(p.main))
    books: list[VMobject] = []
    x, k = left, seed
    while x + widths[k % len(widths)] <= right - 0.08:
        w, h = widths[k % len(widths)], heights[(k * 3) % len(heights)] * (top - floor)
        books.append(_rect(x, floor, x + w, floor + h, colors[k % len(colors)], p))
        x, k = x + w, k + 1
    return books


def _bookshelf(p: _Paint) -> list[VMobject]:
    shelves = (0.05, 0.36, 0.67)
    drawn = [_rect(-0.34, 0.0, 0.34, 1.0, p.main, p), _rect(-0.29, 0.05, 0.29, 0.95, p.dark(p.main), p)]
    for k, y in enumerate(shelves):
        drawn += _books(p, -0.29, 0.29, y + 0.03, y + 0.27, 2 * k)
        drawn.append(_rect(-0.29, y, 0.29, y + 0.03, p.main, p))
    return drawn


def _counter(p: _Paint) -> list[VMobject]:
    """A kitchen counter: cupboards under drawers and a worktop."""
    light = p.light(p.main)
    doors = ((-0.95, -0.34), (-0.3, 0.3), (0.34, 0.95))
    drawn = [_rect(-0.95, 0.0, 0.95, 0.06, p.dark(p.main), p), _rect(-1.0, 0.05, 1.0, 0.88, p.main, p)]
    for x0, x1 in doors:
        drawn += [_rect(x0, 0.1, x1, 0.62, light, p, radius=0.02), _rect(x0, 0.66, x1, 0.82, light, p, radius=0.02)]
        drawn += [_circle((x0 + x1) / 2, 0.74, 0.025, p.detail, p), _circle(x1 - 0.07, 0.5, 0.025, p.detail, p)]
    return [*drawn, _rect(-1.1, 0.87, 1.1, 1.0, p.detail, p, radius=0.02)]


def _fridge(p: _Paint) -> list[VMobject]:
    return [
        _rect(-0.26, 0.0, -0.2, 0.03, p.dark(p.detail), p), _rect(0.2, 0.0, 0.26, 0.03, p.dark(p.detail), p),
        _rect(-0.3, 0.02, 0.3, 1.0, p.main, p, radius=0.05),
        _line(-0.3, 0.68, 0.3, 0.68, p.ink),
        _rect(0.2, 0.74, 0.24, 0.92, p.detail, p, radius=0.015), _rect(0.2, 0.38, 0.24, 0.62, p.detail, p, radius=0.015),
        _poly([(-0.18, 0.46), (-0.04, 0.48), (-0.06, 0.6), (-0.2, 0.58)], p.light(p.detail), p),
        _circle(-0.11, 0.59, 0.02, p.detail, p),
    ]


def _picture(p: _Paint) -> list[VMobject]:
    """A framed picture of a hill under a sun."""
    canvas = p.light(p.detail)
    hill = [(-0.53 + 1.06 * k / 16, 0.12 + 0.34 * math.sin(math.pi * k / 16) ** 1.5) for k in range(17)]
    return [
        _rect(-0.65, 0.0, 0.65, 1.0, p.main, p),
        _rect(-0.53, 0.12, 0.53, 0.88, canvas, p),
        _circle(0.25, 0.64, 0.1, p.light(p.main), p, outline=False),
        _poly(hill, p.detail, p, outline=False),
    ]


def _rug(p: _Paint) -> list[VMobject]:
    """An oval rug lying on the floor, seen nearly edge on."""
    return [
        _ellipse(0.0, 0.5, 20.0, 1.0, p.detail, p),
        _ellipse(0.0, 0.5, 16.6, 0.74, p.main, p, outline=False),
        _ellipse(0.0, 0.5, 10.0, 0.42, p.light(p.main), p, outline=False),
    ]


def _houseplant(p: _Paint) -> list[VMobject]:
    """A tall plant with broad leaves in a round pot."""
    dark = p.dark(p.main)
    leaves = [
        _ellipse(-0.26, 0.58, 0.2, 0.44, dark, p, angle=48), _ellipse(0.27, 0.6, 0.2, 0.44, dark, p, angle=-50),
        _ellipse(-0.13, 0.76, 0.19, 0.44, p.main, p, angle=20), _ellipse(0.15, 0.74, 0.19, 0.44, p.main, p, angle=-24),
        _ellipse(0.0, 0.8, 0.18, 0.4, p.main, p),
    ]
    veins = [_line(0.0, 0.62, 0.0, 0.96, dark), _line(-0.06, 0.6, -0.2, 0.92, dark), _line(0.06, 0.6, 0.22, 0.9, dark)]
    return [
        *leaves[:2], *leaves[2:], *veins,
        _poly([(-0.2, 0.0), (0.2, 0.0), (0.27, 0.3), (-0.27, 0.3)], p.detail, p, round_by=0.03),
        _rect(-0.3, 0.28, 0.3, 0.35, p.dark(p.detail), p, radius=0.02),
    ]


def _clock(p: _Paint) -> list[VMobject]:
    """A round wall clock at ten past ten."""
    ticks = [
        _line(0.0 + 0.33 * math.cos(a), 0.5 + 0.33 * math.sin(a), 0.0 + 0.4 * math.cos(a), 0.5 + 0.4 * math.sin(a), p.ink, 1.5 * OUTLINE_WIDTH)
        for a in (math.pi * k / 2 for k in range(4))
    ]
    hour, minute = math.radians(150), math.radians(30)
    hands = [
        _line(0.0, 0.5, 0.2 * math.cos(hour), 0.5 + 0.2 * math.sin(hour), p.ink, 2.5 * OUTLINE_WIDTH),
        _line(0.0, 0.5, 0.3 * math.cos(minute), 0.5 + 0.3 * math.sin(minute), p.ink, 2.0 * OUTLINE_WIDTH),
    ]
    for hand, part in zip(hands, ("hour", "minute")):   # a running clock turns them (DESIGN.md §69.54)
        setattr(hand, LIVING_PART, part)
    return [
        _circle(0.0, 0.5, 0.5, p.detail, p),
        _circle(0.0, 0.5, 0.41, p.main, p),
        *ticks,
        *hands,
        _circle(0.0, 0.5, 0.04, p.ink, p, outline=False),
    ]


def _tv(p: _Paint) -> list[VMobject]:
    """A television on a low cabinet."""
    return [
        _rect(-0.7, 0.0, -0.62, 0.05, p.dark(p.main), p), _rect(0.62, 0.0, 0.7, 0.05, p.dark(p.main), p),
        _rect(-0.75, 0.04, 0.75, 0.34, p.main, p, radius=0.02),
        _line(0.0, 0.07, 0.0, 0.31, p.ink),
        _circle(-0.08, 0.19, 0.022, p.light(p.main), p), _circle(0.08, 0.19, 0.022, p.light(p.main), p),
        _rect(-0.07, 0.33, 0.07, 0.41, TV_CASE, p),
        _rect(-0.62, 0.4, 0.62, 1.0, TV_CASE, p, radius=0.04),
        _rect(-0.55, 0.46, 0.55, 0.94, p.detail, p),
        _poly([(-0.5, 0.9), (-0.3, 0.9), (-0.5, 0.7)], p.light(p.detail), p, outline=False),
    ]


def _desk(p: _Paint) -> list[VMobject]:
    """Side on: a desk with a chair pulled up to it, the chair's back on the left as drawn facing
    right (a sitter faces the desk)."""
    wood, chair = p.dark(p.main), p.dark(p.detail)
    return [
        _rect(-0.15, 0.0, -0.05, 0.9, wood, p),
        _rect(0.5, 0.0, 0.95, 0.9, p.main, p),
        _line(0.5, 0.6, 0.95, 0.6, p.ink), _line(0.5, 0.3, 0.95, 0.3, p.ink),
        _circle(0.6, 0.75, 0.025, p.light(p.main), p), _circle(0.6, 0.45, 0.025, p.light(p.main), p),
        _rect(-0.2, 0.88, 0.95, 1.0, p.main, p, radius=0.02),
        _rect(-0.92, 0.0, -0.86, 0.31, chair, p), _rect(-0.42, 0.0, -0.36, 0.31, chair, p),
        _rect(-0.95, 0.29, -0.84, 0.82, p.detail, p, radius=0.03),
        _rect(-0.95, 0.27, -0.33, 0.333, p.detail, p, radius=0.02),
    ]


#: How many of a fireplace's last members are its front logs: a burning fire's flames go before
#: them (they burn behind the logs, DESIGN.md §69.55).
FIREPLACE_FRONT = 2


def _fireplace(p: _Paint) -> list[VMobject]:
    """A brick fireplace against the wall: a hearth, a surround with brick lines, an arched sooty
    hollow, a mantelpiece and two logs in front."""
    dark = p.dark(p.main)
    arch = [(-0.42, 0.07), (0.42, 0.07), *((0.42 * math.cos(a), 0.4 + 0.26 * math.sin(a)) for a in np.linspace(0.0, math.pi, 13))]
    bricks = [_line(-0.75, y, 0.75, y, dark, 1.2 * OUTLINE_WIDTH) for y in (0.27, 0.47, 0.67)]
    bricks += [_line(x, y0, x, y0 + 0.2, dark, 1.2 * OUTLINE_WIDTH) for x, y0 in ((-0.6, 0.07), (0.58, 0.07), (-0.55, 0.47), (0.5, 0.47), (0.0, 0.67), (-0.4, 0.67), (0.4, 0.67))]
    return [
        _rect(-0.75, 0.05, 0.75, 0.88, p.main, p),
        *bricks,
        _poly(arch, HEARTH_HOLLOW, p),
        _rect(-0.85, 0.0, 0.85, 0.07, dark, p, radius=0.02),
        _rect(-0.9, 0.86, 0.9, 1.0, p.detail, p, radius=0.02),
        _rect(-0.3, 0.07, 0.3, 0.15, LOG_WOOD, p, radius=0.04),
        _poly([(-0.26, 0.09), (0.24, 0.19), (0.22, 0.25), (-0.28, 0.15)], p.light(LOG_WOOD), p, round_by=0.02),
    ]


_DRAWERS: dict[str, Callable[[_Paint], list[VMobject] | dict[str, list[VMobject]]]] = {
    "table": _table, "chair": _chair, "tree": _tree, "bush": _bush, "house": _house, "door": _door,
    "lamp": _lamp, "sign": _sign, "box": _box, "ball": _ball, "cloud": _cloud, "sun": _sun,
    "moon": _moon, "rock": _rock, "plant": _plant, "laptop": _laptop, "cup": _cup,
    "basket": _basket, "umbrella": _umbrella, "napkin": _napkin, "kettle": _kettle,
    "cake": _cake, "muffin": _muffin, "book": _book, "phone": _phone, "letter": _letter, "gift": _gift,
    "balloons": _balloons, "vase": _vase, "watering_can": _watering_can,
    "sofa": _sofa, "armchair": _armchair, "bed": _bed, "bookshelf": _bookshelf, "counter": _counter,
    "fridge": _fridge, "picture": _picture, "rug": _rug, "houseplant": _houseplant, "clock": _clock,
    "tv": _tv, "desk": _desk, "fireplace": _fireplace,
}


def _fruits(p: _Paint) -> list[VMobject]:
    """A tree's fruits (DESIGN.md §69.55): at each of :data:`FRUIT_SPOTS` a round fruit with a
    shine and a stalk, every member tagged with its spot's index (:data:`FRUIT_INDEX`)."""
    members: list[VMobject] = []
    for k, (x, y) in enumerate(FRUIT_SPOTS):
        r = FRUIT_RADIUS
        fruit = [
            _line(x, y + 0.8 * r, x + 0.25 * r, y + 1.6 * r, FRUIT_STALK, 1.2 * OUTLINE_WIDTH),
            _circle(x, y, r, FRUIT_COLOR, p),
            _circle(x - 0.35 * r, y + 0.35 * r, 0.28 * r, FRUIT_SHINE, p, outline=False),
        ]
        for member in fruit:
            setattr(member, FRUIT_INDEX, k)
        members += fruit
    return members


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
    shape: str | None = None,
    living: bool = False,
    fruit: bool = False,
) -> Prop:
    """A built-in prop ``kind`` ``height`` Manim units tall, its feet at the origin, coloured
    ``main`` / ``detail`` (theme tokens or #hex; default :data:`PROP_COLORS`). Outlines are as
    wide as a character's ``character_height`` tall (default: ``height``), at least one pixel.
    ``shape``: which of its :data:`PROP_SHAPES` it shows (default: the first). ``living``: a
    clock, television, lamp, fireplace or kettle that moves by itself gets its moving parts and an
    anchor (:func:`~vidgen.cartoon.living_drawing.living_overlays`, DESIGN.md §69.54, §69.55).
    ``fruit``: a tree carries a few fruits (:func:`_fruits`)."""
    if kind not in _DRAWERS and kind not in VEHICLES:
        raise VidgenError(f"unknown prop '{kind}' (props: {', '.join(PROP_KINDS)})")
    if height <= 0:
        raise VidgenError(f"prop '{name or kind}': height must be positive, got {height}")
    paint = _Paint(*prop_colors(kind, theme, main, detail))
    if kind in VEHICLES:
        from vidgen.cartoon.vehicle_drawing import draw_vehicle

        vehicle = draw_vehicle(kind, paint)
        prop = Prop(*vehicle.members, name=name or kind, kind=kind, facing=facing, wheels=vehicle.wheels, crank=vehicle.crank,
                    shapes=vehicle.shapes or None)
        if shape is not None:
            prop.show_shape(shape)
        return _finish(prop, height, character_height or height, facing)
    drawn = _DRAWERS[kind](paint)
    shapes = drawn if isinstance(drawn, dict) else None
    living = living and kind in LIVING_KINDS
    if living and isinstance(drawn, list):
        from vidgen.cartoon.living_drawing import living_overlays

        front = FIREPLACE_FRONT if kind == "fireplace" else 0   # flames burn behind the front logs
        drawn = [*drawn[: len(drawn) - front], *living_overlays(kind, paint), *drawn[len(drawn) - front :]]
    if fruit and kind == "tree" and isinstance(drawn, list):
        drawn = [*drawn, *_fruits(paint)]
    prop = Prop(
        *([] if shapes is not None else drawn), name=name or kind, kind=kind, facing=facing,
        seat=mirrored_seat(PROP_SEATS.get(kind), facing), lean=mirrored_lean(PROP_LEANS.get(kind), facing),
        shapes=shapes, grips={s: g for (k, s), g in PROP_GRIPS.items() if k == kind},
        seat_places=mirrored_places(SEAT_PLACES.get(kind, ()), facing), anchored=living,
    )
    if shape is not None:
        prop.show_shape(shape)
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
    of the box's bottom edge at the origin. ``recolor="theme"`` maps its colours to the theme's.
    Its ``<svg>`` element's ``data-seat`` / ``data-lean`` give its seat and lean edges
    (:func:`~vidgen.cartoon.seating.svg_seat_and_lean`; a bad value is a :class:`VidgenError`)."""
    from vidgen.vector_mobject import load_vector

    picture = load_vector(path, height=height, recolor=recolor, theme=theme, where=where or path.name)
    seat, lean = _seat_and_lean(picture.report, where or path.name)
    prop = Prop(picture, name=name, kind="svg", facing=facing, seat=mirrored_seat(seat, facing), lean=mirrored_lean(lean, facing))
    if facing == "left":
        prop.flip(UP)
    return prop.shift(-prop.feet())


def _seat_and_lean(report: CleanSvg, where: str) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    try:
        return svg_seat_and_lean(ET.fromstring(report.data), report.view_box, where)
    except ValueError as exc:
        raise VidgenError(str(exc)) from None


def read_svg_seat_and_lean(path: Path, *, where: str) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    """The seat and lean edges (prop units, facing right) the SVG prop file ``path`` gives on its
    ``<svg>`` element (``data-seat``, ``data-lean``); :class:`VidgenError` for a file that cannot
    be read or sanitised, or a bad value."""
    from vidgen.svgclean import sanitize_svg

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise VidgenError(f"cannot read {where}: {exc}") from None
    return _seat_and_lean(sanitize_svg(data, where=where), where)


__all__ = [
    "FLAT_PROPS",
    "FRUIT_INDEX",
    "FURNITURE",
    "PROP_COLORS",
    "PROP_HANGS",
    "PROP_HEIGHTS",
    "PROP_KINDS",
    "PROP_LIFTS",
    "PROP_GRIPS",
    "PROP_SHAPES",
    "SMALL_PROPS",
    "SVG_PROP_HEIGHT",
    "WATERING_SPOUT",
    "Prop",
    "draw_prop",
    "prop_colors",
    "svg_prop",
    "read_svg_seat_and_lean",
]
