"""The ready-made objects of an isometric place drawn as shapes (DESIGN.md §89.5): a house, trees,
a bush, a rock, flowers, a fence, a bench, a lamp, a well, a sign, a bridge, and indoors a table,
a chair, a bed, a shelf, a sofa, a plant and a rug. No manim.

Each is drawn in its own frame: ``a`` across its front (0 .. its width), ``b`` from its back (0)
to its front (its depth), ``z`` up from the ground it stands on. Facing left its front is the
face to the viewer's lower left; facing right the whole drawing is mirrored (``x`` and ``y``
swap), so its front is the face to the lower right.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Callable
from dataclasses import dataclass

from vidgen.cartoon.iso_city import (
    SCREEN_TEXT,
    TOWER_ANTENNA,
    TOWER_COLUMN,
    TOWER_DARK_GLASS,
    TOWER_FIRST,
    TOWER_FLOOR,
    TOWER_GARDEN_COLOR,
    TOWER_INSET,
    TOWER_WINDOW,
    garden_bands,
    screen_box,
    screen_color,
    screen_lines,
    screen_seed,
    window_color,
    window_lit,
)
from vidgen.cartoon.iso_drawing import Blobs, Disc, Line, Poly, Shape, Upright, box_shapes, mix, shade
from vidgen.world.iso import WALL_KINDS, IsoObject, ObjectState, default_state
from vidgen.world.iso_view import ISO_RISE, Box3, Point3, iso_point

#: Default (main, detail) colours of each object: theme tokens like the stage's props
#: (:data:`~vidgen.cartoon.props.PROP_COLORS`), or a hex where no token fits every theme.
OBJECT_COLORS: dict[str, tuple[str, str]] = {
    "house": ("secondary", "accent"), "tree": ("tertiary", "#9C6B47"), "pine": ("tertiary", "#9C6B47"),
    "bush": ("tertiary", "accent"), "rock": ("#B9B4AA", "#B9B4AA"), "flowers": ("accent", "highlight"),
    "fence": ("#F4F6FA", "dim"), "bench": ("secondary", "dim"), "lamp": ("dim", "highlight"),
    "well": ("#C9C3B6", "accent"), "sign": ("highlight", "secondary"), "bridge": ("#C69466", "#9C6B47"),
    "table": ("secondary", "secondary"), "chair": ("accent", "accent"), "bed": ("primary", "#F4F6FA"),
    "shelf": ("secondary", "accent"), "sofa": ("primary", "highlight"), "plant": ("tertiary", "accent"),
    "rug": ("accent", "highlight"),
    "console": ("#8A93A3", "#5FD8FF"), "server_rack": ("#3A3F4B", "#48E07A"), "projector_pad": ("#5A6272", "#5FD8FF"),
    "whiteboard": ("#B9BFC9", "#3B6FB6"), "flower_arch": ("#F2A7C3", "#FFFFFF"), "chess_table": ("#9C6B47", "#2B2F3A"),
    "tower": ("#2A3050", "#FF2E8B"),
    "laptop": ("#B9BFC9", "#5FD8FF"), "terminal_kiosk": ("#8A93A3", "#5FD8FF"), "quantum_core": ("#4A5266", "#A98BFF"),
    "robot_arm": ("#F2A33A", "#3A3F4B"), "microscope": ("#F4F6FA", "#3A3F4B"), "centrifuge": ("#E6EAF0", "#5FD8FF"),
    "coffee_machine": ("#3A3F4B", "#E2574C"), "lab_stool": ("#4C8DD6", "#B9BFC9"), "wall_clock": ("#3A3F4B", "#E2574C"),
}
GLASS = "#D6EEF8"
FRAME = "#F4F6FA"
WOOD = "#9C6B47"
WATER_DEEP = "#4D8FC0"
LAMP_GLOW = "#FFF1B8"
#: A lamp's lantern and a house's windows when lit, the pool of light under a lit lamp (a tint
#: of the ground, ``LIGHT_POOL_OPACITY``), and the dark of an open doorway (DESIGN.md §89.10).
LIT_GLASS = "#FFD75E"
LIT_CORE = "#FFF6D0"
LIGHT_POOL = "#FFE58A"
LIGHT_POOL_OPACITY = 0.32
LIGHT_POOL_RADIUS = 1.1
#: Settling snow covers this share of each of a pine's tiers from its tip down (the tier above
#: hides most of it, so the white shows as shoulders over a green fringe), and of a well's roof
#: (a cut-out facing the viewer), DESIGN.md §90.3.
PINE_SNOW_CAP = 0.72
ROOF_SNOW_CAP = 0.6
DOORWAY = "#2E2A38"
BOOK_COLORS: tuple[str, ...] = ("#E2574C", "#F6C945", "#5BA35B", "#4C8DD6", "#B48EAD")


@dataclass(frozen=True)
class ObjectLook:
    """An object's resolved colours (``#rrggbb``); ``moving``: its moving parts are drawn over its
    picture by the stage while it works (:func:`object_motion`), so the picture of it working
    leaves them out (a robot arm's arm, DESIGN.md §103)."""

    main: str
    detail: str
    moving: bool = False


class _Frame:
    """An object's own frame: ``a`` across its front, ``b`` from its back to its front, ``z`` up
    from its base; facing right mirrors it (``x`` and ``y`` swap)."""

    def __init__(self, item: IsoObject, base: float) -> None:
        self.item = item
        self.swap = item.facing == "right"
        self.x0, self.y0, self.base = item.column, item.row, base
        self.width, self.depth = (item.depth, item.width) if self.swap else (item.width, item.depth)

    def p(self, a: float, b: float, z: float) -> Point3:
        if self.swap:
            return (self.x0 + b, self.y0 + a, self.base + z)
        return (self.x0 + a, self.y0 + b, self.base + z)

    def poly(self, points: list[tuple[float, float, float]], fill: str, ink: bool | tuple[bool, ...] = True, glow: bool = False) -> Poly:
        return Poly(tuple(self.p(*q) for q in points), fill, ink, glow)

    def box(self, a0: float, b0: float, z0: float, a1: float, b1: float, z1: float, color: str, *, top: str | None = None) -> list[Shape]:
        """A box in the frame, its faces shaded as they face in the world."""
        (x0, y0, zz0), (x1, y1, zz1) = self.p(a0, b0, z0), self.p(a1, b1, z1)
        return box_shapes(min(x0, x1), min(y0, y1), zz0, max(x0, x1), max(y0, y1), zz1, top or color)

    def front(self, color: str) -> str:
        """``color`` as shaded on the object's front face."""
        return shade(color, 0.26 if self.swap else 0.12)

    def side(self, color: str) -> str:
        """``color`` as shaded on the object's right side face."""
        return shade(color, 0.12 if self.swap else 0.26)

    def across(self, a: float, b: float, z: float, offset: float) -> Point3:
        """A point ``offset`` (tile units) from (``a``, ``b``, ``z``) straight across the picture
        (to the right for a positive offset): for shapes that face the viewer, like a cut-out."""
        x, y, zz = self.p(a, b, z)
        return (x + offset / 2, y - offset / 2, zz)


def _window(f: _Frame, u0: float, u1: float, z0: float, z1: float, *, front: float | None = None, side: float | None = None,
            lit: bool = False) -> list[Shape]:
    """A window with a frame and a cross of bars on the front face (at ``b`` = ``front``; ``u``
    across it as ``a``) or the right side face (at ``a`` = ``side``; ``u`` from the front back);
    ``lit``: warm light behind its glass."""
    def at(u: float, z: float) -> tuple[float, float, float]:
        if side is not None:
            return (side, f.depth - u, z)
        assert front is not None
        return (u, front, z)

    pad = 0.06
    shapes: list[Shape] = [f.poly([at(u0, z0), at(u1, z0), at(u1, z1), at(u0, z1)], FRAME),
                           f.poly([at(u0 + pad, z0 + pad), at(u1 - pad, z0 + pad), at(u1 - pad, z1 - pad), at(u0 + pad, z1 - pad)],
                                  LIT_GLASS if lit else GLASS, False, lit)]
    mid_u, mid_z = (u0 + u1) / 2, (z0 + z1) / 2
    if lit:
        core = 0.3
        shapes.append(f.poly([at(mid_u - (mid_u - u0) * core, mid_z - (mid_z - z0) * core), at(mid_u + (u1 - mid_u) * core, mid_z - (mid_z - z0) * core),
                              at(mid_u + (u1 - mid_u) * core, mid_z + (z1 - mid_z) * core), at(mid_u - (mid_u - u0) * core, mid_z + (z1 - mid_z) * core)],
                             LIT_CORE, False, True))
    shapes += [Line((f.p(*at(mid_u, z0 + pad)), f.p(*at(mid_u, z1 - pad))), FRAME, 1.4),
               Line((f.p(*at(u0 + pad, mid_z)), f.p(*at(u1 - pad, mid_z))), FRAME, 1.4)]
    return shapes


def _door_leaf(f: _Frame, a0: float, a1: float, b: float, height: float, is_open: bool) -> list[Shape]:
    """A door in the front face (at ``b``) from ``a0`` to ``a1``: closed, its leaf with a knob;
    open, a dark doorway and the leaf swung out towards the viewer on its hinge at ``a0``."""
    if not is_open:
        return [f.poly([(a0, b, 0.0), (a1, b, 0.0), (a1, b, height), (a0, b, height)], WOOD),
                Disc(f.p(a0 + (a1 - a0) * 0.8, b, height * 0.52), 0.045, "#F2C14E", False, holds_snow=False)]
    swing = (a1 - a0) * 0.9
    out = (a0 - swing * 0.17, b + swing * 0.98)
    return [f.poly([(a0, b, 0.0), (a1, b, 0.0), (a1, b, height), (a0, b, height)], DOORWAY),
            f.poly([(a0, b, 0.0), (out[0], out[1], 0.0), (out[0], out[1], height), (a0, b, height)], mix(WOOD, "#FFFFFF", 0.12)),
            Disc(f.p(out[0] + 0.02, out[1] - 0.12, height * 0.52), 0.045, "#F2C14E", False, holds_snow=False)]


def _house(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """Walls, a gable roof whose ridge runs across the front (the gable on the right side), a
    door and windows on the front, a window on the side, a chimney; the door open and the
    windows lit as ``state`` says."""
    inset, wall, ridge, eave = 0.12, 2.3, 4.35, 0.28
    a0, a1, b0, b1 = inset, f.width - inset, inset, f.depth - inset
    mid = (b0 + b1) / 2
    shapes = f.box(a0, b0, 0.0, a1, b1, wall, look.main)
    door_w = 0.62
    door_a = (a0 + a1) / 2 - door_w / 2 + 0.35
    shapes += _window(f, a0 + 0.35, a0 + 1.0, 1.0, 1.75, front=b1, lit=state.on)
    shapes += _window(f, f.depth / 2 - 0.32, f.depth / 2 + 0.32, 1.0, 1.7, side=a1, lit=state.on)
    roof = look.detail
    # the far slope first (only its edge shows past the near one), then the gable, the chimney, the near slope
    shapes.append(f.poly([(a0, mid, ridge), (a1, mid, ridge), (a1, b0 - eave, wall - 0.25), (a0, b0 - eave, wall - 0.25)], shade(roof, 0.3)))
    shapes.append(f.poly([(a1, b0, wall), (a1, b1, wall), (a1, mid, ridge)], f.side(look.main)))
    chimney_a = a0 + 0.45
    shapes += f.box(chimney_a, mid - 0.55, wall + 0.6, chimney_a + 0.38, mid - 0.17, ridge + 0.25, "#B5655A")
    shapes.append(f.poly([(a0, mid, ridge), (a1, mid, ridge), (a1, b1 + eave, wall - 0.25), (a0, b1 + eave, wall - 0.25)], f.front(roof)))
    shapes.append(f.poly([(a1, mid, ridge), (a1, b1 + eave, wall - 0.25), (a1, b1 + eave, wall - 0.4), (a1, mid, ridge - 0.15)],
                         shade(roof, 0.4)))
    return shapes + _door_leaf(f, door_a, door_a + door_w, b1, 1.55, state.open)


def _crown(f: _Frame, look: ObjectLook, z: float, size: float) -> list[Shape]:
    """A round, puffy crown of leaves around height ``z``: one outlined form, a lighter puff."""
    centre = f.p(0.5, 0.5, z)
    offsets = [(0.0, 0.0, 1.0), (-0.42, 0.1, 0.72), (0.42, 0.1, 0.72), (-0.22, -0.32, 0.72), (0.24, -0.3, 0.7), (0.0, 0.34, 0.62)]
    # each puff ``du`` across the picture and ``dv`` down it from the middle (tile widths; a world
    # unit up is ISO_RISE tile widths, so dv / ISO_RISE units down)
    centres = tuple((centre[0] + du / 2 * size, centre[1] - du / 2 * size, centre[2] - dv * size / ISO_RISE) for du, dv, _ in offsets)
    radii = tuple(r * 0.42 * size for _, _, r in offsets)
    leaves = mix(look.main, "#2F6B3A", 0.12)
    shine = mix(leaves, "#FFFFFF", 0.3)
    return [Blobs(centres, radii, leaves),
            Blobs((centres[3],), (radii[3] * 0.45,), shine, False),
            Blobs(((centres[1][0] + 0.05, centres[1][1] - 0.05, centres[1][2] + 0.1),), (radii[1] * 0.3,), shine, False)]


def _tree(f: _Frame, look: ObjectLook) -> list[Shape]:
    return [Upright(*f.p(0.5, 0.5, 0.0)[:2], f.base, f.base + 1.7, 0.15, look.detail), *_crown(f, look, 2.65, 1.2)]


def _pine(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A trunk and three tiers of needles, each a triangle facing the viewer."""
    leaves = mix(look.main, "#1F5A3A", 0.3)
    shapes: list[Shape] = [Upright(*f.p(0.5, 0.5, 0.0)[:2], f.base, f.base + 0.9, 0.11, look.detail)]
    for k, (bottom, top, half) in enumerate(((0.7, 2.4, 0.62), (1.6, 3.3, 0.5), (2.5, 4.2, 0.38))):
        shapes.append(Poly((f.across(0.5, 0.5, bottom, -half), f.across(0.5, 0.5, bottom, half), f.across(0.5, 0.5, top, 0.0)),
                           shade(leaves, 0.06 * (2 - k)), snow_cap=PINE_SNOW_CAP))
        shapes.append(Poly((f.across(0.5, 0.5, bottom + 0.05, -half * 0.75), f.across(0.5, 0.5, bottom + 0.05, -half * 0.35),
                            f.across(0.5, 0.5, top - 0.35, -0.04)), mix(leaves, "#FFFFFF", 0.18), False))
    return shapes


def _bush(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A round bush in each cell of its footprint (a larger one is a hedge of bushes)."""
    leaves = mix(look.main, "#2F6B3A", 0.05)
    puffs = [(-0.26, 0.42, 0.24), (0.24, 0.42, 0.24), (0.0, 0.62, 0.27), (-0.1, 0.3, 0.2), (0.14, 0.28, 0.2)]
    berries = [(-0.2, 0.62), (0.12, 0.75), (0.22, 0.45)]
    shapes: list[Shape] = []
    for a, b in _bed_cells(f):
        centre = f.p(a, b + 0.05, 0.0)
        centres = tuple((centre[0] + du / 2, centre[1] - du / 2, centre[2] + z) for du, z, _ in puffs)
        shapes.append(Blobs(centres, tuple(r for _, _, r in puffs), leaves))
        shapes.append(Blobs(tuple((centre[0] + du / 2, centre[1] - du / 2, centre[2] + z) for du, z in berries), (0.045,) * 3, look.detail))
    return shapes


def _bed_cells(f: _Frame) -> list[tuple[float, float]]:
    """The middles (``a``, ``b`` in the object's frame) of the cells of its footprint, back to
    front: a flower bed or a hedge draws a clump in each."""
    cells = [(a + 0.5, b + 0.5) for b in range(round(f.depth)) for a in range(round(f.width))]
    return sorted(cells, key=lambda cell: (sum(f.p(cell[0], cell[1], 0.0)[:2]), cell[0]))


def _rock(f: _Frame, look: ObjectLook) -> list[Shape]:
    centre = f.p(0.5, 0.55, 0.0)
    stones = (centre[0] - 0.08, centre[1] + 0.08, centre[2] + 0.22), (centre[0] + 0.12, centre[1] - 0.12, centre[2] + 0.3)
    return [Blobs(stones, (0.2, 0.27), look.main),
            Blobs(((stones[1][0] - 0.05, stones[1][1] + 0.05, stones[1][2] + 0.12),), (0.08,), mix(look.main, "#FFFFFF", 0.35), False)]


def _flowers(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A clump of leaves with flower heads in the main and detail colours (in bloom), or with
    green buds tinged with them (closed), in each cell of its footprint (a larger one is a bed,
    every other clump with its colours the other way round)."""
    leaves = [(-0.2, 0.15, 0.14), (0.18, 0.15, 0.14), (0.0, 0.22, 0.15)]
    shapes: list[Shape] = []
    for k, (a, b) in enumerate(_bed_cells(f)):
        centre = f.p(a, b, 0.0)
        main, detail = (look.main, look.detail) if k % 2 == 0 else (look.detail, look.main)
        shapes.append(Blobs(tuple((centre[0] + du / 2, centre[1] - du / 2, centre[2] + z) for du, z, _ in leaves),
                            tuple(r for _, _, r in leaves), "#5BA35B"))
        heads = [(-0.22, 0.42, main), (0.05, 0.55, detail), (0.25, 0.4, main), (-0.05, 0.32, detail), (0.12, 0.3, main)]
        for du, z, color in heads:
            point = (centre[0] + du / 2, centre[1] - du / 2, centre[2] + z)
            if not state.open:
                shapes.append(Blobs((point,), (0.042,), mix(color, "#5BA35B", 0.55)))
                continue
            shapes.append(Blobs((point,), (0.075,), color))
            shapes.append(Blobs((point,), (0.025,), "#F6C945" if color != "#F6C945" else "#FFFFFF", False))
    return shapes


def _fence(f: _Frame, look: ObjectLook, links: tuple[str, ...]) -> list[Shape]:
    """A post in the middle of the cell and two rails to each side it joins (world sides, no mirroring)."""
    x0, y0, z0 = f.x0, f.y0, f.base
    post, rail = 0.07, 0.035
    rails = {"n": (0.5 - rail, 0.0, 0.5 + rail, 0.5), "s": (0.5 - rail, 0.5, 0.5 + rail, 1.0),
             "w": (0.0, 0.5 - rail, 0.5, 0.5 + rail), "e": (0.5, 0.5 - rail, 1.0, 0.5 + rail)}

    def rail_shapes(side: str) -> list[Shape]:
        ax0, ay0, ax1, ay1 = rails[side]
        found: list[Shape] = []
        for z in (0.32, 0.68):
            found += box_shapes(x0 + ax0, y0 + ay0, z0 + z, x0 + ax1, y0 + ay1, z0 + z + 0.1, look.main)
        end = {"n": (0.5, 0.0), "s": (0.5, 1.0), "w": (0.0, 0.5), "e": (1.0, 0.5)}[side]
        found += box_shapes(x0 + end[0] - post * 0.8, y0 + end[1] - post * 0.8, z0, x0 + end[0] + post * 0.8, y0 + end[1] + post * 0.8,
                            z0 + 0.82, look.main) if side in ("s", "e") else []
        return found

    shapes: list[Shape] = []
    for side in ("n", "w"):
        shapes += rail_shapes(side) if side in links else []
    shapes += box_shapes(x0 + 0.5 - post, y0 + 0.5 - post, z0, x0 + 0.5 + post, y0 + 0.5 + post, z0 + 0.95, look.main)
    shapes.append(Poly(((x0 + 0.5 - post, y0 + 0.5 - post, z0 + 0.95), (x0 + 0.5 + post, y0 + 0.5 - post, z0 + 0.95),
                        (x0 + 0.5 + post, y0 + 0.5 + post, z0 + 0.95), (x0 + 0.5, y0 + 0.5, z0 + 1.05)), look.main))
    for side in ("e", "s"):
        shapes += rail_shapes(side) if side in links else []
    return shapes


def _legs(f: _Frame, a0: float, b0: float, a1: float, b1: float, height: float, color: str, size: float = 0.07) -> tuple[list[Shape], list[Shape]]:
    """Four legs at the corners of a box: the two at its back, then the two at its front."""
    back = f.box(a0, b0, 0.0, a0 + size, b0 + size, height, color) + f.box(a1 - size, b0, 0.0, a1, b0 + size, height, color)
    front = f.box(a0, b1 - size, 0.0, a0 + size, b1, height, color) + f.box(a1 - size, b1 - size, 0.0, a1, b1, height, color)
    return back, front


def _bench(f: _Frame, look: ObjectLook) -> list[Shape]:
    a0, a1 = 0.12, f.width - 0.12
    wood, iron = look.main, look.detail
    back, front = _legs(f, a0 + 0.1, 0.3, a1 - 0.1, 0.85, 0.45, iron)
    shapes = back + f.box(a0, 0.18, 0.62, a1, 0.3, 1.08, wood)
    shapes.append(Line((f.p(a0 + 0.05, 0.3, 0.85), f.p(a1 - 0.05, 0.3, 0.85)), shade(wood, 0.3), 0.8))
    shapes += f.box(a0, 0.3, 0.45, a1, 0.88, 0.55, wood)
    shapes.append(Line((f.p(a0 + 0.05, 0.6, 0.55), f.p(a1 - 0.05, 0.6, 0.55)), shade(wood, 0.25), 0.8))
    return shapes + front


def _lamp(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A post with a lantern, lit (a bright lantern, a pool of light on the ground) when on."""
    x, y = f.p(0.5, 0.5, 0.0)[:2]
    z = f.base
    post = look.main
    pool: list[Shape] = [Disc((x, y, z + 0.01), LIGHT_POOL_RADIUS, LIGHT_POOL, False, LIGHT_POOL_OPACITY, glow=True)] if state.on else []
    glass = (LIT_CORE, LIT_GLASS, shade(LIT_GLASS, 0.08)) if state.on else (LAMP_GLOW, look.detail, shade(look.detail, 0.15))
    return [*pool, Disc((x, y, z + 0.02), 0.2, shade(post, 0.1)), Upright(x, y, z, z + 2.75, 0.06, post),
            *box_shapes(x - 0.16, y - 0.16, z + 2.6, x + 0.16, y + 0.16, z + 3.1, glass[0], left=glass[1], right=glass[2], glow=state.on),
            Poly(((x - 0.22, y - 0.22, z + 3.1), (x + 0.22, y - 0.22, z + 3.1), (x + 0.22, y + 0.22, z + 3.1), (x - 0.22, y + 0.22, z + 3.1)), post),
            Poly(((x - 0.22, y + 0.22, z + 3.1), (x + 0.22, y + 0.22, z + 3.1), (x, y, z + 3.35)), shade(post, 0.1)),
            Poly(((x + 0.22, y + 0.22, z + 3.1), (x + 0.22, y - 0.22, z + 3.1), (x, y, z + 3.35)), shade(post, 0.25))]


def _well(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A round stone wall with water inside, two posts, a crank and a little roof."""
    x, y = f.p(0.5, 0.5, 0.0)[:2]
    z = f.base
    stone, roof = look.main, look.detail
    shapes: list[Shape] = [Upright(x, y, z, z + 0.85, 0.42, stone), Disc((x, y, z + 0.85), 0.31, WATER_DEEP, True),
                           Line(((x - 0.3, y + 0.3, z + 0.3), (x + 0.3, y - 0.3, z + 0.3)), shade(stone, 0.2), 0.7)]
    left, right = (x - 0.36, y + 0.36), (x + 0.36, y - 0.36)
    for px, py in (left, right):
        shapes.append(Upright(px, py, z + 0.7, z + 2.15, 0.055, WOOD))
    shapes.append(Line(((left[0], left[1], z + 1.75), (right[0], right[1], z + 1.75)), WOOD, 2.0))
    shapes.append(Line(((x, y, z + 1.75), (x, y, z + 1.25)), "#7A7F88", 0.7))
    shapes += box_shapes(x - 0.09, y - 0.09, z + 1.05, x + 0.09, y + 0.09, z + 1.28, "#8A8F99")
    half = 0.6
    shapes.append(Poly(((x - half, y + half, z + 2.05), (x + half, y - half, z + 2.05), (x, y, z + 2.85)), roof, snow_cap=ROOF_SNOW_CAP))
    shapes.append(Poly(((x - half, y + half, z + 2.05), (x + half, y - half, z + 2.05), (x + half, y - half + 0.12, z + 1.95),
                        (x - half, y + half + 0.12, z + 1.95)), shade(roof, 0.3), holds_snow=False))   # the roof's edge
    return shapes


def _sign(f: _Frame, look: ObjectLook) -> list[Shape]:
    x, y = f.p(0.5, 0.5, 0.0)[:2]
    z = f.base
    shapes: list[Shape] = [Upright(x, y, z, z + 1.0, 0.06, WOOD)]
    board = [f.across(0.5, 0.5, 0.95, -0.42), f.across(0.5, 0.5, 0.95, 0.42), f.across(0.5, 0.5, 1.6, 0.42), f.across(0.5, 0.5, 1.6, -0.42)]
    shapes.append(Poly(tuple(board), look.main))
    for k, z_line in enumerate((1.4, 1.25, 1.1)):
        shapes.append(Line((f.across(0.5, 0.5, z_line, -0.3), f.across(0.5, 0.5, z_line, 0.3 - 0.12 * k)), look.detail, 1.1))
    return shapes


def _bridge(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A plank deck running from the back to the front, with a rail on each side."""
    deck, rail = look.main, look.detail
    length = f.depth
    shapes: list[Shape] = []

    def side_rail(a: float) -> list[Shape]:
        found: list[Shape] = []
        for k in range(math.floor(length) + 1):
            b = min(max(k, 0.1), length - 0.1)
            found += f.box(a - 0.05, b - 0.05, 0.0, a + 0.05, b + 0.05, 0.85, rail)
        found += f.box(a - 0.04, 0.05, 0.75, a + 0.04, length - 0.05, 0.85, rail)
        return found

    shapes += side_rail(0.1)
    shapes += f.box(0.05, -0.05, 0.0, f.width - 0.05, length + 0.05, 0.22, deck)
    for k in range(1, math.ceil(length * 3)):
        b = k / 3
        shapes.append(Line((f.p(0.08, b, 0.22), f.p(f.width - 0.08, b, 0.22)), shade(deck, 0.25), 0.6))
    return shapes + side_rail(f.width - 0.1)


def _table(f: _Frame, look: ObjectLook) -> list[Shape]:
    a0, a1, b0, b1 = 0.12, f.width - 0.12, 0.12, f.depth - 0.12
    back, front = _legs(f, a0 + 0.08, b0 + 0.08, a1 - 0.08, b1 - 0.08, 0.85, shade(look.main, 0.15), 0.09)
    return back + front + f.box(a0, b0, 0.85, a1, b1, 0.98, look.main)


def _chair(f: _Frame, look: ObjectLook) -> list[Shape]:
    a0, a1, b0, b1 = 0.25, 0.75, 0.25, 0.75
    back, front = _legs(f, a0, b0, a1, b1, 0.55, shade(look.main, 0.15))
    return back + f.box(a0, b0 - 0.02, 0.55, a1, b0 + 0.08, 1.3, look.main) + front + f.box(a0, b0, 0.55, a1, b1, 0.63, look.main)


def _bed(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A wooden frame, a headboard at the back, a pillow and a blanket over the front."""
    a0, a1 = 0.08, f.width - 0.08
    b1 = f.depth - 0.08
    shapes = f.box(a0, 0.05, 0.0, a1, 0.2, 1.05, WOOD)
    shapes += f.box(a0, 0.2, 0.0, a1, b1, 0.4, WOOD)
    shapes += f.box(a0 + 0.04, 0.2, 0.4, a1 - 0.04, b1 - 0.04, 0.58, "#F4F6FA")
    shapes += f.box(a0 + 0.15, 0.28, 0.58, a1 - 0.15, 0.68, 0.72, look.detail)
    shapes += f.box(a0 + 0.02, 0.8, 0.4, a1 - 0.02, b1, 0.64, look.main)
    shapes.append(Line((f.p(a0 + 0.02, 0.95, 0.64), f.p(a1 - 0.02, 0.95, 0.64)), mix(look.main, "#FFFFFF", 0.4), 1.2))
    return shapes + f.box(a0, b1 - 0.1, 0.0, a1, b1 + 0.02, 0.75, WOOD)


def _shelf(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A tall bookcase with its back to the wall: rows of books on its front, a board under each."""
    a0, a1, b0, b1 = 0.06, f.width - 0.06, 0.12, 0.6
    wood = look.main
    shapes = f.box(a0, b0, 0.0, a1, b1, 2.4, wood)
    shapes.append(f.poly([(a0 + 0.08, b1, 0.1), (a1 - 0.08, b1, 0.1), (a1 - 0.08, b1, 2.3), (a0 + 0.08, b1, 2.3)], shade(wood, 0.5), False))
    for k, z in enumerate((0.1, 0.84, 1.58)):
        seed = zlib.crc32(f"{f.x0}:{f.y0}:{k}".encode())
        a = a0 + 0.12
        while a < a1 - 0.22:
            width = 0.08 + (seed % 5) * 0.015
            height = 0.42 + (seed >> 3) % 4 * 0.06
            color = BOOK_COLORS[(seed >> 7) % len(BOOK_COLORS)] if (seed >> 11) % 3 else look.detail
            shapes.append(f.poly([(a, b1, z), (a + width, b1, z), (a + width, b1, z + height), (a, b1, z + height)], f.front(color), True))
            a += width + 0.015
            seed = zlib.crc32(seed.to_bytes(4, "little"))
        shapes.append(f.poly([(a0 + 0.08, b1, z - 0.07), (a1 - 0.08, b1, z - 0.07), (a1 - 0.08, b1, z), (a0 + 0.08, b1, z)], f.front(wood)))
    return shapes


def _sofa(f: _Frame, look: ObjectLook) -> list[Shape]:
    a0, a1 = 0.08, f.width - 0.08
    cloth = look.main
    shapes = f.box(a0, 0.12, 0.0, a1, 0.42, 1.12, cloth)
    shapes += f.box(a0 + 0.22, 0.42, 0.0, a1 - 0.22, 0.92, 0.55, cloth)
    middle = (a0 + a1) / 2
    shapes.append(Line((f.p(middle, 0.42, 0.55), f.p(middle, 0.92, 0.55)), shade(cloth, 0.3), 0.8))
    shapes += f.box(a0 + 0.45, 0.32, 0.55, a0 + 0.85, 0.45, 0.9, look.detail)
    for a in (a0, a1 - 0.22):
        shapes += f.box(a, 0.12, 0.0, a + 0.22, 0.92, 0.78, shade(cloth, 0.06))
    return shapes


def _plant(f: _Frame, look: ObjectLook) -> list[Shape]:
    x, y = f.p(0.5, 0.5, 0.0)[:2]
    z = f.base
    leaves = mix(look.main, "#2F6B3A", 0.1)
    pot = look.detail
    centres = tuple((x + du / 2, y - du / 2, z + dz) for du, dz in ((0.0, 1.15), (-0.24, 0.95), (0.24, 0.95), (-0.12, 0.75), (0.14, 0.78)))
    return [Upright(x, y, z, z + 0.5, 0.22, pot), Disc((x, y, z + 0.5), 0.18, "#7A5536", False),
            Blobs(centres, (0.24, 0.18, 0.18, 0.16, 0.16), leaves)]


def _rug(f: _Frame, look: ObjectLook) -> list[Shape]:
    a0, a1, b0, b1 = 0.1, f.width - 0.1, 0.1, f.depth - 0.1
    z = 0.02
    border = 0.14
    return [f.poly([(a0, b0, z), (a1, b0, z), (a1, b1, z), (a0, b1, z)], look.main),
            f.poly([(a0 + border, b0 + border, z), (a1 - border, b0 + border, z), (a1 - border, b1 - border, z), (a0 + border, b1 - border, z)],
                   mix(look.main, look.detail, 0.55), False),
            Disc(f.p((a0 + a1) / 2, (b0 + b1) / 2, z), min(a1 - a0, b1 - b0) * 0.2, look.main, False)]


# ----- a lab and a memory's props (DESIGN.md §100.11) -------------------------------------------------

#: Dark casings (a monitor's frame, a rack's front), a screen's lines and a lab light's off look.
CASING = "#2B2F3A"
SCREEN_LINE = "#E8FBFF"
LED_OFF = "#3D4350"
#: The screens' faces as drawn on a console: (a from, a to) of each monitor, as shares of the width.
CONSOLE_SCREENS = ((0.06, 0.34), (0.37, 0.63), (0.66, 0.94))
#: A server rack's units: how many, and the lights on each (a across the front).
RACK_UNITS = 6
RACK_LIGHTS = (0.22, 0.32, 0.42)


def _glow_rect(f: _Frame, a0: float, a1: float, b: float, z0: float, z1: float, color: str) -> Poly:
    """A lit rectangle on a face at ``b`` (a screen): not dimmed by the stage's light."""
    return f.poly([(a0, b, z0), (a1, b, z0), (a1, b, z1), (a0, b, z1)], color, False, True)


def _console(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A lab desk: two cabinets under a long top, a keyboard, and a row of monitors along its
    back whose screens glow in the detail colour with lines of text (lit at night too)."""
    w = f.width
    steel = look.main
    shapes = f.box(0.08, 0.3, 0.0, 0.62, 0.92, 0.78, shade(steel, 0.1)) + f.box(w - 0.62, 0.3, 0.0, w - 0.08, 0.92, 0.78, shade(steel, 0.1))
    shapes += f.box(0.04, 0.22, 0.78, w - 0.04, 0.98, 0.86, steel)
    for share0, share1 in CONSOLE_SCREENS:
        a0, a1 = share0 * w, share1 * w
        shapes += f.box(a0, 0.28, 0.86, a1, 0.36, 1.78, CASING)
        shapes.append(_glow_rect(f, a0 + 0.05, a1 - 0.05, 0.36, 0.93, 1.71, look.detail))
        for k, z in enumerate((1.6, 1.48, 1.36, 1.24, 1.12)):
            reach = a0 + 0.1 + (a1 - a0 - 0.2) * (0.9 - 0.17 * ((k * 3 + round(share0 * 10)) % 4))
            shapes.append(_glow_rect(f, a0 + 0.1, reach, 0.361, z, z + 0.035, SCREEN_LINE))
    shapes += f.box(0.3 * w, 0.55, 0.86, 0.7 * w, 0.8, 0.9, CASING)
    return shapes


def _server_rack(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A tall dark cabinet of server units, each with a vent and a row of small lights (dark in
    the picture; the stage blinks them, :func:`object_lights`)."""
    a0, a1, b0, b1 = 0.1, f.width - 0.1, 0.12, f.depth - 0.12
    top = 2.6
    shapes = f.box(a0, b0, 0.0, a1, b1, top, look.main)
    shapes.append(f.poly([(a0 + 0.06, b1, 0.12), (a1 - 0.06, b1, 0.12), (a1 - 0.06, b1, top - 0.1), (a0 + 0.06, b1, top - 0.1)], shade(look.main, 0.35), False))
    unit = (top - 0.3) / RACK_UNITS
    for k in range(RACK_UNITS):
        z = 0.16 + k * unit
        shapes.append(f.poly([(a0 + 0.1, b1, z), (a1 - 0.1, b1, z), (a1 - 0.1, b1, z + unit - 0.06), (a0 + 0.1, b1, z + unit - 0.06)], shade(look.main, 0.15)))
        for g in range(3):
            shapes.append(Line((f.p(a1 - 0.45 + g * 0.1, b1, z + 0.08), f.p(a1 - 0.45 + g * 0.1, b1, z + unit - 0.14)), shade(look.main, 0.5), 0.6))
        for a in RACK_LIGHTS:
            shapes.append(Disc(f.p(a0 + a * (a1 - a0), b1, z + unit / 2 - 0.03), 0.035, LED_OFF, False, holds_snow=False))
    return shapes


def _projector_pad(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A round, low platform with a glowing ring and an emitter in its middle (a hologram stands
    on it)."""
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    z = f.base
    radius = min(f.width, f.depth) * 0.45
    return [Upright(x, y, z, z + 0.12, radius, look.main), Disc((x, y, z + 0.121), radius * 0.86, look.detail, False, glow=True, holds_snow=False),
            Disc((x, y, z + 0.122), radius * 0.74, shade(look.main, 0.25), False, holds_snow=False),
            Disc((x, y, z + 0.123), radius * 0.18, mix(look.detail, "#FFFFFF", 0.5), False, glow=True, holds_snow=False)]


def _whiteboard(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A whiteboard on two legs with a tray, scribbled with a diagram in the detail colour."""
    w = f.width
    b = f.depth / 2
    shapes: list[Shape] = []
    for a in (0.2, w - 0.2):
        shapes += f.box(a - 0.04, b - 0.04, 0.0, a + 0.04, b + 0.04, 2.1, shade(look.main, 0.3))
    shapes += f.box(0.12, b - 0.03, 0.75, w - 0.12, b + 0.03, 2.1, shade(look.main, 0.1))
    face = b + 0.031
    shapes.append(f.poly([(0.16, face, 0.79), (w - 0.16, face, 0.79), (w - 0.16, face, 2.06), (0.16, face, 2.06)], "#F7F8FA", False))
    shapes += f.box(0.2, b, 0.72, w - 0.2, b + 0.12, 0.76, shade(look.main, 0.2))
    ink = look.detail
    shapes.append(Line((f.p(0.35, face, 1.25), f.p(0.6, face, 1.7), f.p(0.85, face, 1.35), f.p(1.1, face, 1.85)), ink, 1.2))
    for k, z in enumerate((1.9, 1.7, 1.5, 1.3, 1.1)):
        shapes.append(Line((f.p(w * 0.58, face, z), f.p(w * (0.88 - 0.05 * (k % 3)), face, z)), shade(ink, 0.2), 0.9))
    shapes.append(Line((f.p(0.32, face, 0.95), f.p(w * 0.5, face, 0.95)), "#E2574C", 1.0))
    return shapes


def _flower_arch(f: _Frame, look: ObjectLook) -> list[Shape]:
    """An arch of flowers across its width (a wedding, a garden gate): two posts wound with
    leaves and a curved top, flowers in the main and detail colours along it."""
    w = f.width
    b = f.depth / 2
    shapes: list[Shape] = []
    leaves = "#5BA35B"
    top = 2.6
    for a in (0.15, w - 0.15):
        shapes.append(Upright(*f.p(a, b, 0.0)[:2], f.base, f.base + top, 0.07, "#F4F6FA"))
    curve = [(0.15 + (w - 0.3) * t, b, top + 0.55 * math.sin(math.pi * t)) for t in [k / 12 for k in range(13)]]
    shapes.append(Line(tuple(f.p(*q) for q in curve), "#F4F6FA", 3.0))
    spots = [(0.15, b, z) for z in (0.6, 1.1, 1.6, 2.1)] + [(w - 0.15, b, z) for z in (0.6, 1.1, 1.6, 2.1)] + curve[1:-1:2] + [curve[0], curve[-1]]
    centres = tuple(f.p(*q) for q in spots)
    shapes.append(Blobs(centres, (0.17,) * len(centres), leaves))
    for k, centre in enumerate(centres):
        shapes.append(Blobs(((centre[0] + 0.05, centre[1] - 0.05, centre[2] + 0.05),), (0.09,), look.main if k % 2 else look.detail, False))
    return shapes


def _chess_table(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A small table with a board of squares on top and a few round pieces on it."""
    a0, a1, b0, b1 = 0.15, f.width - 0.15, 0.15, f.depth - 0.15
    back, front = _legs(f, a0 + 0.06, b0 + 0.06, a1 - 0.06, b1 - 0.06, 0.8, shade(WOOD, 0.1), 0.08)
    shapes = back + front + f.box(a0, b0, 0.8, a1, b1, 0.86, look.main)
    n = 6
    for i in range(n):
        for j in range(n):
            if (i + j) % 2:
                continue
            u0, u1 = a0 + 0.05 + (a1 - a0 - 0.1) * i / n, a0 + 0.05 + (a1 - a0 - 0.1) * (i + 1) / n
            v0, v1 = b0 + 0.05 + (b1 - b0 - 0.1) * j / n, b0 + 0.05 + (b1 - b0 - 0.1) * (j + 1) / n
            shapes.append(f.poly([(u0, v0, 0.861), (u1, v0, 0.861), (u1, v1, 0.861), (u0, v1, 0.861)], look.detail, False))
    for k, (u, v) in enumerate(((0.3, 0.3), (0.55, 0.35), (0.7, 0.65), (0.4, 0.7))):
        centre = f.p(a0 + (a1 - a0) * u, b0 + (b1 - b0) * v, 0.87)
        shapes.append(Upright(centre[0], centre[1], centre[2], centre[2] + 0.1, 0.05, "#F4F6FA" if k % 2 else "#C8473E"))
    return shapes


# ----- a city's towers (DESIGN.md §102.2) --------------------------------------------------------------

#: The width (tile units) of a tower's neon trims, and the frame round its info screen.
TOWER_TRIM = 0.05
TOWER_SCREEN_FRAME = 0.05


def _face_rect(f: _Frame, face: str, u0: float, u1: float, z0: float, z1: float, color: str, *, glow: bool = False) -> Poly:
    """A rectangle on a tower's ``front`` face (``u`` across it as ``a``) or its ``side`` face
    (``u`` from its front corner back), from height ``z0`` to ``z1``: a window, a band, a screen."""
    if face == "front":
        b = f.depth - TOWER_INSET
        return f.poly([(u0, b, z0), (u1, b, z0), (u1, b, z1), (u0, b, z1)], color, False, glow)
    a = f.width - TOWER_INSET
    return f.poly([(a, f.depth - u0, z0), (a, f.depth - u1, z0), (a, f.depth - u1, z1), (a, f.depth - u0, z1)], color, False, glow)


def _tower(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A tall building of a city at night: its walls in the main colour, rows of windows on its
    two faces (a seeded share lit while it is on, each in a warm or cool light; the rest dark
    glass), neon trims up its front corners and round its roof in the detail colour, optionally
    a big info screen on its front (``screen``; the stage crawls lines of text on it) and glowing
    algae-farm bands up its faces (``garden``), and an antenna on its roof (its light blinks)."""
    item = f.item
    h = item.height
    i = TOWER_INSET
    shapes = f.box(i, i, 0.0, f.width - i, f.depth - i, h, look.main)
    neon = look.detail
    screen = screen_box(h) if "screen" in item.features else None
    bands = garden_bands(h) if "garden" in item.features else []
    for face, span in (("front", f.width), ("side", f.depth)):
        lo, hi = i, span - i
        cols = max(1, int((hi - lo - 0.12) / TOWER_COLUMN))
        start = lo + (hi - lo - cols * TOWER_COLUMN) / 2 + (TOWER_COLUMN - TOWER_WINDOW[0]) / 2
        dark = f.front(TOWER_DARK_GLASS) if face == "front" else f.side(TOWER_DARK_GLASS)
        hidden: tuple[float, float, float, float] | None = None
        if screen is not None and face == "front":
            hidden = (lo + screen[0] * (hi - lo), lo + screen[1] * (hi - lo), screen[2], screen[3])
        row, z = 0, TOWER_FIRST
        while z + TOWER_WINDOW[1] <= h - 0.35:
            z1 = z + TOWER_WINDOW[1]
            if not any(b0 - 0.05 < z1 and z < b1 + 0.05 for b0, b1 in bands):
                for col in range(cols):
                    u0 = start + col * TOWER_COLUMN
                    u1 = u0 + TOWER_WINDOW[0]
                    if hidden is not None and hidden[0] - 0.08 < u1 and u0 < hidden[1] + 0.08 and hidden[2] - 0.1 < z1 and z < hidden[3] + 0.1:
                        continue
                    lit = state.on and window_lit(item.name, face, row, col)
                    shapes.append(_face_rect(f, face, u0, u1, z, z1, window_color(item.name, face, row, col) if lit else dark, glow=lit))
            row, z = row + 1, z + TOWER_FLOOR
        for b0, b1 in bands:   # an algae farm: a glowing band with the darker frames of its tanks
            shapes.append(_face_rect(f, face, lo + 0.02, hi - 0.02, b0, b1, TOWER_GARDEN_COLOR, glow=True))
            for k in range(1, 6):
                u = lo + (hi - lo) * k / 6
                shapes.append(_face_rect(f, face, u - 0.018, u + 0.018, b0, b1, mix(TOWER_GARDEN_COLOR, "#06301F", 0.55), glow=True))
        # neon: up the face's outer edge and along its top
        outer = (lo, lo + TOWER_TRIM) if face == "front" else (hi - TOWER_TRIM, hi)
        shapes.append(_face_rect(f, face, *outer, 0.0, h, neon, glow=True))
        shapes.append(_face_rect(f, face, lo, hi, h - 0.16, h - 0.16 + TOWER_TRIM * 1.4, neon, glow=True))
    shapes.append(_face_rect(f, "front", f.width - i - TOWER_TRIM, f.width - i, 0.0, h, neon, glow=True))   # the front corner
    if screen is not None:
        lo, hi = i, f.width - i
        u0, u1 = lo + screen[0] * (hi - lo), lo + screen[1] * (hi - lo)
        z0, z1 = screen[2], screen[3]
        shapes.append(_face_rect(f, "front", u0 - TOWER_SCREEN_FRAME, u1 + TOWER_SCREEN_FRAME, z0 - TOWER_SCREEN_FRAME, z1 + TOWER_SCREEN_FRAME, CASING))
        shapes.append(_face_rect(f, "front", u0, u1, z0, z1, screen_color(neon), glow=True))
        for up, length in screen_lines(0.0, screen_seed(item.name)):   # the lines as they start (the stage crawls them)
            zz = z0 + (z1 - z0) * up
            shapes.append(_face_rect(f, "front", u0 + 0.06, u0 + 0.06 + (u1 - u0 - 0.12) * length, zz - 0.03, zz + 0.03, SCREEN_TEXT, glow=True))
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    shapes.append(Upright(x, y, f.base + h, f.base + h + TOWER_ANTENNA, 0.035, shade(look.main, 0.2)))
    return shapes


# ----- more lab and sci-fi objects (DESIGN.md §103) ------------------------------------------------------

#: A lab bench's or a small desk's colour, a dark screen's and a working display's green.
BENCH = "#C9CED6"
DARK_SCREEN = "#1E2430"
DISPLAY_GREEN = "#48E07A"
#: Seconds of a robot arm's swing (there and back), a quantum core's pulse, a centrifuge's turn
#: and a puff of a coffee machine's steam.
ARM_SWING_SECONDS = 3.2
CORE_PULSE_SECONDS = 2.0
SPIN_SECONDS = 0.9
STEAM_SECONDS = 1.8
STEAM_PUFFS = 3
#: The poses a robot arm swings between: its turn (degrees in its own frame), the upper arm's and
#: the forearm's angle over the level.
ARM_POSES = ((135.0, 80.0, -20.0), (-25.0, 55.0, -62.0))


@dataclass(frozen=True)
class Motion:
    """A moving part of a working object at one moment (DESIGN.md §103): a flat polygon in the
    world (tile units), its fill and opacity, outlined or not, and whether it is a light (not
    dimmed by the stage's light)."""

    points: tuple[Point3, ...]
    fill: str
    opacity: float = 1.0
    ink: bool = True
    glow: bool = False


def _screen(p: Point3, du: float, dv: float) -> Point3:
    """The world point ``du`` right of ``p`` on the picture and ``dv`` up it (tile widths)."""
    x, y, z = p
    return (x + du, y - du, z + dv / ISO_RISE)


def _round(centre: Point3, radius: float, fill: str, ink: bool = True, glow: bool = False, steps: int = 20) -> Poly:
    """A round shape facing the viewer (a sphere, a joint, a puff) around ``centre``, ``radius``
    in tile widths."""
    return Poly(tuple(_screen(centre, radius * math.cos(2 * math.pi * k / steps), radius * math.sin(2 * math.pi * k / steps)) for k in range(steps)),
                fill, ink, glow)


def _flat_circle(centre: Point3, radius: float, steps: int = 24, turn: float = 0.0) -> tuple[Point3, ...]:
    """The points of a level circle round ``centre`` (tile units)."""
    x, y, z = centre
    return tuple((x + radius * math.cos(turn + 2 * math.pi * k / steps), y + radius * math.sin(turn + 2 * math.pi * k / steps), z) for k in range(steps))


def _ribbon(p: Point3, q: Point3, half: float, fill: str, glow: bool = False) -> Poly:
    """A band from ``p`` to ``q`` facing the viewer, ``half`` its width (tile widths): an arm's
    segment, a tube."""
    (u0, v0), (u1, v1) = iso_point(*p), iso_point(*q)
    du, dup = u1 - u0, -(v1 - v0)
    length = math.hypot(du, dup) or 1.0
    su, sv = -dup / length * half, du / length * half
    return Poly((_screen(p, su, sv), _screen(q, su, sv), _screen(q, -su, -sv), _screen(p, -su, -sv)), fill, True, glow)


def _indicator(f: _Frame, a0: float, a1: float, b: float, z0: float, z1: float, color: str, on: bool) -> Poly:
    """A small light on a face at ``b``: lit in ``color`` when ``on`` (not dimmed by the stage's
    light), else dark."""
    return _glow_rect(f, a0, a1, b, z0, z1, color) if on else f.poly([(a0, b, z0), (a1, b, z0), (a1, b, z1), (a0, b, z1)], LED_OFF, False)


def _side_table(f: _Frame, color: str = BENCH, height: float = 0.78) -> list[Shape]:
    """A small table filling the cell, its top at ``height``: what a laptop or a microscope stands on."""
    a0, a1, b0, b1 = 0.1, f.width - 0.1, 0.16, f.depth - 0.08
    back, front = _legs(f, a0 + 0.05, b0 + 0.05, a1 - 0.05, b1 - 0.05, height - 0.06, shade(color, 0.25), 0.06)
    return back + front + f.box(a0, b0, height - 0.06, a1, b1, height, color)


def _cabinet(f: _Frame, height: float = 0.8) -> list[Shape]:
    """A lab bench's cabinet filling the cell with a door seam: what a benchtop machine stands on."""
    a0, a1, b0, b1 = 0.08, f.width - 0.08, 0.18, f.depth - 0.06
    shapes = f.box(a0, b0, 0.0, a1, b1, height, BENCH)
    shapes.append(Line((f.p((a0 + a1) / 2, b1, 0.08), f.p((a0 + a1) / 2, b1, height - 0.1)), shade(BENCH, 0.35), 0.8))
    shapes.append(Line((f.p(a0 + 0.04, b1, height - 0.06), f.p(a1 - 0.04, b1, height - 0.06)), shade(BENCH, 0.35), 0.8))
    return shapes


def _lid_point(hinge: tuple[float, float], top: tuple[float, float], a: float, s: float) -> tuple[float, float, float]:
    """A point of a laptop's open lid: ``a`` across, ``s`` of the way from its hinge (b, z) to its top."""
    return (a, hinge[0] + (top[0] - hinge[0]) * s, hinge[1] + (top[1] - hinge[1]) * s)


def _laptop(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A laptop on a small desk: open, its screen glows in the detail colour with lines of code
    when on (dark when off); closed, its lid lies on it."""
    shapes = _side_table(f)
    cx = f.width / 2
    a0, a1, b0, b1, z = cx - 0.24, cx + 0.24, 0.42, 0.78, 0.78
    shapes += f.box(a0, b0, z, a1, b1, z + 0.03, look.main)
    if not state.open:
        shapes += f.box(a0, b0, z + 0.03, a1, b1, z + 0.06, mix(look.main, "#FFFFFF", 0.15))
        return shapes + [Disc(f.p(cx, (b0 + b1) / 2, z + 0.061), 0.04, shade(look.main, 0.3), False, holds_snow=False)]
    shapes.append(f.poly([(a0 + 0.04, b0 + 0.04, z + 0.031), (a1 - 0.04, b0 + 0.04, z + 0.031), (a1 - 0.04, b0 + 0.22, z + 0.031),
                          (a0 + 0.04, b0 + 0.22, z + 0.031)], shade(look.main, 0.4), False))
    shapes.append(f.poly([(cx - 0.07, b0 + 0.26, z + 0.031), (cx + 0.07, b0 + 0.26, z + 0.031), (cx + 0.07, b1 - 0.03, z + 0.031),
                          (cx - 0.07, b1 - 0.03, z + 0.031)], shade(look.main, 0.15), False))
    hinge, top = (b0, z + 0.03), (b0 - 0.1, z + 0.44)
    shapes.append(f.poly([_lid_point(hinge, top, a0, 0.0), _lid_point(hinge, top, a1, 0.0), _lid_point(hinge, top, a1, 1.0),
                          _lid_point(hinge, top, a0, 1.0)], shade(look.main, 0.55)))
    screen = DARK_SCREEN if not state.on else look.detail
    shapes.append(f.poly([_lid_point(hinge, top, a0 + 0.03, 0.08), _lid_point(hinge, top, a1 - 0.03, 0.08), _lid_point(hinge, top, a1 - 0.03, 0.93),
                          _lid_point(hinge, top, a0 + 0.03, 0.93)], screen, False, state.on))
    if not state.on:
        return shapes + [f.poly([_lid_point(hinge, top, a1 - 0.2, 0.9), _lid_point(hinge, top, a1 - 0.1, 0.9), _lid_point(hinge, top, a1 - 0.3, 0.12),
                                 _lid_point(hinge, top, a1 - 0.4, 0.12)], mix(DARK_SCREEN, "#FFFFFF", 0.12), False)]
    colors = (SCREEN_LINE, mix(look.detail, "#FFFFFF", 0.55), LIT_GLASS)
    for k, s in enumerate((0.8, 0.68, 0.56, 0.44, 0.32, 0.2)):
        indent = (0.0, 0.05, 0.1, 0.05, 0.1, 0.0)[k]
        start = a0 + 0.07 + indent
        end = start + (a1 - a0 - 0.18 - indent) * (0.9, 0.55, 0.75, 0.4, 0.65, 0.3)[k]
        shapes.append(f.poly([_lid_point(hinge, top, start, s), _lid_point(hinge, top, end, s), _lid_point(hinge, top, end, s + 0.055),
                              _lid_point(hinge, top, start, s + 0.055)], colors[k % 3], False, True))
    return shapes


def _terminal_kiosk(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A standing terminal: a base plate, a column, a keyboard shelf and a big screen that glows
    in the detail colour with a header and lines of text when on."""
    w, d = f.width, f.depth
    cx = w / 2
    shapes = f.box(0.18, 0.22, 0.0, w - 0.18, d - 0.12, 0.08, shade(look.main, 0.2))
    shapes += f.box(cx - 0.09, 0.4, 0.08, cx + 0.09, 0.58, 1.12, look.main)
    shapes.append(_indicator(f, cx - 0.04, cx + 0.04, 0.581, 0.85, 0.89, DISPLAY_GREEN, state.on))
    shapes += f.box(0.1, 0.34, 1.1, w - 0.1, 0.46, 1.95, CASING)
    a0, a1, z0, z1 = 0.16, w - 0.16, 1.16, 1.89
    if state.on:
        shapes.append(_glow_rect(f, a0, a1, 0.461, z0, z1, look.detail))
        shapes.append(_glow_rect(f, a0, a1, 0.462, z1 - 0.09, z1, mix(look.detail, "#FFFFFF", 0.5)))
        for k, zz in enumerate((1.68, 1.57, 1.46, 1.35, 1.24)):
            shapes.append(_glow_rect(f, a0 + 0.06, a0 + 0.06 + (a1 - a0 - 0.12) * (0.85, 0.5, 0.7, 0.35, 0.6)[k], 0.462, zz, zz + 0.045, SCREEN_LINE))
    else:
        shapes.append(f.poly([(a0, 0.461, z0), (a1, 0.461, z0), (a1, 0.461, z1), (a0, 0.461, z1)], DARK_SCREEN, False))
        shapes.append(f.poly([(a1 - 0.25, 0.462, z1 - 0.05), (a1 - 0.12, 0.462, z1 - 0.05), (a1 - 0.4, 0.462, z0 + 0.05), (a1 - 0.53, 0.462, z0 + 0.05)],
                             mix(DARK_SCREEN, "#FFFFFF", 0.12), False))
    shapes += f.box(0.16, 0.56, 0.92, w - 0.16, d - 0.1, 0.98, look.main)
    shapes.append(f.poly([(0.22, 0.6, 0.981), (w - 0.22, 0.6, 0.981), (w - 0.22, d - 0.15, 0.981), (0.22, d - 0.15, 0.981)], CASING, False))
    for b in (0.68, 0.76):
        shapes.append(Line((f.p(0.24, b, 0.982), f.p(w - 0.24, b, 0.982)), "#4A5160", 0.6))
    return shapes


def _core_centre(f: _Frame) -> tuple[Point3, float]:
    """A quantum core's sphere: its middle and radius (tile widths)."""
    return f.p(f.width / 2, f.depth / 2, 1.08), 0.27 * min(f.width, f.depth, 1.4)


def _quantum_core(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A glowing sphere in a cage of four posts on a round plinth, a ring round its middle; the
    sphere dim when off (the stage pulses it when on, :func:`object_motion`)."""
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    z = f.base
    centre, radius = _core_centre(f)
    plinth = 0.42 * min(f.width, f.depth, 1.4)
    shapes: list[Shape] = [Upright(x, y, z, z + 0.22, plinth, look.main),
                           Disc((x, y, z + 0.221), plinth * 0.72, look.detail if state.on else shade(look.detail, 0.55), False, glow=state.on, holds_snow=False)]
    reach = plinth * 0.72
    posts = [(-reach, -reach), (reach, -reach), (-reach, reach), (reach, reach)]   # back first, the front post last
    ring = [(x + radius * 1.3 * math.cos(t), y + radius * 1.3 * math.sin(t), centre[2]) for t in [2 * math.pi * k / 32 for k in range(33)]]
    back = [p for p in ring if p[0] + p[1] <= x + y + 1e-9]
    front = [p for p in ring if p[0] + p[1] >= x + y - 1e-9]
    for dx, dy in posts[:3]:
        shapes.append(Upright(x + dx, y + dy, z + 0.22, z + 1.92, 0.035, shade(look.main, 0.1)))
    shapes.append(Line(tuple(sorted(back, key=lambda p: iso_point(*p)[0])), mix(look.detail, "#FFFFFF", 0.3), 1.6))
    if state.on:
        shapes.append(_round(centre, radius, look.detail, True, True))
        shapes.append(_round(_screen(centre, -radius * 0.25, radius * 0.25), radius * 0.45, mix(look.detail, "#FFFFFF", 0.55), False, True))
        shapes.append(_round(_screen(centre, -radius * 0.38, radius * 0.38), radius * 0.15, "#FFFFFF", False, True))
    else:
        shapes.append(_round(centre, radius, shade(look.detail, 0.55)))
        shapes.append(_round(_screen(centre, -radius * 0.35, radius * 0.35), radius * 0.2, mix(shade(look.detail, 0.55), "#FFFFFF", 0.35), False))
    shapes.append(Line(tuple(sorted(front, key=lambda p: iso_point(*p)[0])), mix(look.detail, "#FFFFFF", 0.3), 1.6))
    dx, dy = posts[3]
    shapes.append(Upright(x + dx, y + dy, z + 0.22, z + 1.92, 0.035, shade(look.main, 0.1)))
    shapes.append(Upright(x, y, z + 1.86, z + 1.96, plinth * 0.9, look.main))
    return shapes


def _arm_pose(share: float) -> tuple[float, float, float]:
    """A robot arm's pose ``share`` of the way from its first pose to its second (smoothly)."""
    s = 0.5 - 0.5 * math.cos(math.pi * min(max(share, 0.0), 1.0))
    return tuple(a + (b - a) * s for a, b in zip(*ARM_POSES))   # type: ignore[return-value]


def _arm(f: _Frame, look: ObjectLook, share: float) -> list[Poly]:
    """A robot arm's arm ``share`` of its swing: the upper arm, the forearm, the joints and a
    two-fingered gripper."""
    turn, upper, fore = (math.radians(v) for v in _arm_pose(share))
    cx, cy = f.width / 2, f.depth / 2
    da, db = math.cos(turn), math.sin(turn)

    def at(reach: float, z: float) -> Point3:
        return f.p(cx + reach * da, cy + reach * db, z)

    shoulder_r, shoulder_z = 0.0, 0.62
    elbow_r, elbow_z = shoulder_r + 0.58 * math.cos(upper), shoulder_z + 0.58 * math.sin(upper)
    wrist_r, wrist_z = elbow_r + 0.44 * math.cos(fore), elbow_z + 0.44 * math.sin(fore)
    tip_r, tip_z = wrist_r + 0.14 * math.cos(fore - 0.5), wrist_z + 0.14 * math.sin(fore - 0.5)
    joint = look.detail
    shoulder, elbow, wrist = at(shoulder_r, shoulder_z), at(elbow_r, elbow_z), at(wrist_r, wrist_z)
    finger = [_ribbon(wrist, _screen(at(tip_r, tip_z), side * 0.05, 0.0), 0.018, joint) for side in (-1.0, 1.0)]
    return [_ribbon(shoulder, elbow, 0.075, look.main), _round(shoulder, 0.09, joint), *finger, _ribbon(elbow, wrist, 0.055, f.front(look.main)),
            _round(elbow, 0.07, joint), _round(wrist, 0.05, joint)]


def _robot_arm(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """An industrial robot arm on a round base with a turret and a warning light (amber, lit when
    on); its arm at rest, or left to the stage while it swings (``look.moving``)."""
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    z = f.base
    shapes: list[Shape] = [Upright(x, y, z, z + 0.14, 0.34, look.detail), Upright(x, y, z + 0.14, z + 0.55, 0.17, look.main)]
    shapes.append(_round(_screen(f.p(f.width / 2, f.depth / 2, 0.1), -0.22, 0.0), 0.04, LIT_GLASS if state.on else LED_OFF, True, state.on))
    if look.moving and state.on:
        return shapes
    return shapes + list(_arm(f, look, 0.0))


def _microscope(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A microscope on a small table: a base, a pillar, a stage with a slide, the objective, the
    head and an eyepiece tilted towards the viewer."""
    cx = f.width / 2
    main, dark = look.main, look.detail
    shapes = _side_table(f)
    shapes += f.box(cx - 0.16, 0.42, 0.78, cx + 0.16, 0.76, 0.84, main)
    shapes += f.box(cx - 0.05, 0.42, 0.84, cx + 0.05, 0.5, 1.4, main)
    shapes.append(_round(f.p(cx + 0.07, 0.46, 1.1), 0.04, dark))
    shapes.append(Disc(f.p(cx, 0.62, 0.841), 0.04, LAMP_GLOW, False, holds_snow=False))
    shapes += f.box(cx - 0.13, 0.5, 1.0, cx + 0.13, 0.74, 1.04, dark)
    shapes.append(f.poly([(cx - 0.08, 0.58, 1.041), (cx + 0.08, 0.58, 1.041), (cx + 0.08, 0.66, 1.041), (cx - 0.08, 0.66, 1.041)], GLASS, False))
    shapes.append(Upright(*f.p(cx, 0.62, 0.0)[:2], f.base + 1.12, f.base + 1.32, 0.032, dark))
    shapes += f.box(cx - 0.07, 0.42, 1.3, cx + 0.07, 0.68, 1.42, main)
    eye0, eye1 = f.p(cx, 0.5, 1.42), f.p(cx, 0.6, 1.6)
    return shapes + [_ribbon(eye0, eye1, 0.032, dark), _round(eye1, 0.036, shade(dark, 0.2))]


def _centrifuge(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A benchtop centrifuge on a cabinet: a body with a round window in its lid showing the
    rotor and its tubes (in the detail colour), a display on its front (green when on; the stage
    spins the rotor, :func:`object_motion`)."""
    shapes = _cabinet(f)
    w = f.width
    b0, b1 = 0.3, f.depth - 0.16
    shapes += f.box(0.2, b0, 0.8, w - 0.2, b1, 1.12, look.main)
    shapes.append(_indicator(f, 0.3, 0.55 * w, b1 + 0.001, 0.88, 0.99, DISPLAY_GREEN, state.on))
    shapes.append(Disc(f.p(0.72 * w, b1 + 0.001, 0.94), 0.035, look.detail, True, holds_snow=False))
    centre = f.p(w / 2, (b0 + b1) / 2, 1.121)
    shapes.append(Disc(centre, 0.2, CASING, True, holds_snow=False))
    return shapes + [Poly(m.points, m.fill, m.ink, m.glow) for m in _rotor(centre, look, 0.3)]


def _rotor(centre: Point3, look: ObjectLook, turn: float) -> list[Motion]:
    """A centrifuge's rotor turned ``turn`` (radians): three arms with a tube at each end and a hub."""
    x, y, z = centre
    parts: list[Motion] = []
    for k in range(3):
        t = turn + 2 * math.pi * k / 3
        ca, sa = math.cos(t), math.sin(t)
        na, nb = -sa * 0.025, ca * 0.025
        tip = (x + 0.15 * ca, y + 0.15 * sa, z + 0.002)
        parts.append(Motion(((x + na, y + nb, z + 0.002), (tip[0] + na, tip[1] + nb, z + 0.002), (tip[0] - na, tip[1] - nb, z + 0.002),
                             (x - na, y - nb, z + 0.002)), "#8A93A3", ink=False))
        parts.append(Motion(_flat_circle((tip[0], tip[1], z + 0.003), 0.04, 12), look.detail))
    parts.append(Motion(_flat_circle((x, y, z + 0.004), 0.035, 12), "#D6DAE0"))
    return parts


def _coffee_machine(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A coffee machine on a cabinet: its body in the main colour, a bean hopper, a dark recess
    with a spout, a drip tray with a tiny mug, a light in the detail colour (lit when on; the
    stage puffs steam from the mug, :func:`object_motion`)."""
    shapes = _cabinet(f)
    w = f.width
    b0, b1 = 0.24, f.depth - 0.3
    shapes += f.box(0.22, b0, 0.8, w - 0.22, b1, 1.58, look.main)
    shapes += f.box(0.3, b0 + 0.04, 1.58, 0.55, b0 + 0.24, 1.72, "#7A5536")
    shapes.append(f.poly([(0.33, b1, 0.86), (w - 0.33, b1, 0.86), (w - 0.33, b1, 1.3), (0.33, b1, 1.3)], DARK_SCREEN, False))
    shapes += f.box(w / 2 - 0.04, b1, 1.2, w / 2 + 0.04, b1 + 0.06, 1.28, "#8A93A3")
    shapes.append(_indicator(f, 0.3, 0.42, b1 + 0.001, 1.4, 1.48, look.detail, state.on))
    for a in (0.5, 0.6):
        shapes.append(Disc(f.p(a * w, b1 + 0.001, 1.44), 0.03, "#D6DAE0", True, holds_snow=False))
    shapes += f.box(0.32, b1, 0.8, w - 0.32, b1 + 0.14, 0.84, "#8A93A3")
    mug = f.p(w / 2, b1 + 0.07, 0.0)
    shapes += [Upright(mug[0], mug[1], f.base + 0.84, f.base + 0.98, 0.055, "#F4F6FA"), Disc((mug[0], mug[1], f.base + 0.981), 0.045, "#5A3A22", False)]
    return shapes


def _lab_stool(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A round lab stool: a flat base, a post with a foot ring and a padded seat in the main colour."""
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    z = f.base
    frame = look.detail
    ring = _flat_circle((x, y, z + 0.28), 0.17, 24)
    return [Disc((x, y, z + 0.02), 0.22, frame, True, holds_snow=False), Upright(x, y, z + 0.02, z + 0.62, 0.035, shade(frame, 0.1)),
            Line((*ring, ring[0]), shade(frame, 0.15), 1.8), Upright(x, y, z + 0.6, z + 0.72, 0.23, look.main)]


#: A wall clock's face: its middle's height over the wall's base and its radius (tile units).
CLOCK_HEIGHT = 2.2
CLOCK_RADIUS = 0.32


def clock_hands(time: str | None) -> tuple[float, float]:
    """A clock's hour and minute hands' angles (degrees clockwise from twelve) for ``time``
    (``"HH:MM"``; ``None``: ten past ten)."""
    hours, minutes = (int(v) for v in (time or "10:10").split(":"))
    return ((hours % 12) * 30.0 + minutes * 0.5, minutes * 6.0)


def _wall_clock(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A round clock on the face of the wall it hangs on: a rim in the main colour, a white face
    with twelve marks, its hour and minute hands at its ``time`` and a pin in the detail colour."""
    face_b = f.depth + 0.02
    cx = f.width / 2
    radius = CLOCK_RADIUS * min(f.width, 1.6)
    across = -1.0 if f.swap else 1.0   # as seen from the room, clockwise

    def at(angle: float, r: float, lift: float = 0.0) -> Point3:
        t = math.radians(angle)
        return f.p(cx + across * r * math.sin(t), face_b + lift, CLOCK_HEIGHT + r * math.cos(t))

    steps = [k * 360.0 / 28 for k in range(28)]
    shapes: list[Shape] = [Poly(tuple(at(t, radius) for t in steps), look.main),
                           Poly(tuple(at(t, radius * 0.84, 0.002) for t in steps), "#F7F8FA", False)]
    for k in range(12):
        inner = 0.62 if k % 3 == 0 else 0.7
        shapes.append(Line((at(k * 30.0, radius * inner, 0.003), at(k * 30.0, radius * 0.76, 0.003)), CASING, 1.6 if k % 3 == 0 else 0.9))
    hour, minute = clock_hands(f.item.time)
    shapes.append(Line((at(0.0, 0.0, 0.004), at(hour, radius * 0.42, 0.004)), CASING, 3.0))
    shapes.append(Line((at(0.0, 0.0, 0.005), at(minute, radius * 0.66, 0.005)), CASING, 2.0))
    return shapes + [Poly(tuple(at(t, radius * 0.07, 0.006) for t in steps[::2]), look.detail, False)]


def _wall_box(item: IsoObject, base: float) -> Box3:
    """The box of an object hanging on a wall: a thin slab on the wall's face, round its height."""
    f = _Frame(item, base)
    radius = CLOCK_RADIUS * min(f.width, 1.6)
    (x0, y0, z0), (x1, y1, z1) = f.p(0.0, f.depth, CLOCK_HEIGHT - radius - 0.05), f.p(f.width, f.depth + 0.06, CLOCK_HEIGHT + radius + 0.05)
    return Box3(min(x0, x1), min(y0, y1), z0, max(x0, x1), max(y0, y1), z1)


#: The objects with moving parts the stage draws over their pictures while they work (DESIGN.md §103).
MOVING_KINDS = ("quantum_core", "robot_arm", "centrifuge", "coffee_machine")


def object_motion(item: IsoObject, look: ObjectLook, base: float, now: float) -> list[Motion]:
    """The moving parts of a working ``item`` (one of :data:`MOVING_KINDS`) at scene time
    ``now``, drawn over its picture: a quantum core's pulsing halo, its bright core and sparks
    round its ring; a robot arm's arm swinging between its two poses; a centrifuge's spinning
    rotor (over a dark window); a coffee machine's steam rising from the mug. The same number of
    parts at any time (those not seen have opacity 0)."""
    f = _Frame(item, base)
    if item.kind == "quantum_core":
        centre, radius = _core_centre(f)
        beat = 0.5 - 0.5 * math.cos(2 * math.pi * now / CORE_PULSE_SECONDS)
        parts = [Motion(_round(centre, radius * (1.25 + 0.3 * beat), look.detail).points, mix(look.detail, "#FFFFFF", 0.3), 0.22 + 0.22 * beat, False, True),
                 Motion(_round(centre, radius * (0.42 + 0.14 * beat), "#FFFFFF").points, mix(look.detail, "#FFFFFF", 0.75), 0.45 + 0.4 * beat, False, True)]
        x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
        for k in range(3):
            t = 2 * math.pi * (now / 1.6 + k / 3)
            point = (x + radius * 1.3 * math.cos(t), y + radius * 1.3 * math.sin(t), centre[2])
            seen = math.cos(t) + math.sin(t) > 0   # on the ring's near half
            parts.append(Motion(_round(point, 0.035, "#FFFFFF").points, "#FFFFFF", 1.0 if seen else 0.0, False, True))
        return parts
    if item.kind == "robot_arm":
        swing = (now % ARM_SWING_SECONDS) / ARM_SWING_SECONDS
        share = 2 * swing if swing < 0.5 else 2 - 2 * swing
        return [Motion(p.points, p.fill, 1.0, bool(p.ink), p.glow) for p in _arm(f, look, share)]
    if item.kind == "centrifuge":
        w, b0, b1 = f.width, 0.3, f.depth - 0.16
        centre = f.p(w / 2, (b0 + b1) / 2, 1.121)
        turn = 2 * math.pi * now / SPIN_SECONDS
        return [Motion(_flat_circle(centre, 0.2), CASING), Motion(_flat_circle((centre[0], centre[1], centre[2] + 0.001), 0.17), look.detail, 0.25, False),
                *_rotor(centre, look, turn)]
    if item.kind == "coffee_machine":
        top = f.p(f.width / 2, f.depth - 0.3 + 0.07, 1.0)
        parts = []
        for k in range(STEAM_PUFFS):
            rise = (now / STEAM_SECONDS + k / STEAM_PUFFS) % 1.0
            sway = 0.035 * math.sin(2 * math.pi * (rise + k * 0.37))
            centre = _screen(top, sway, 0.08 + 0.6 * rise)
            opacity = 0.9 * min(1.0, rise * 5.0) * (1.0 - rise) ** 0.7
            parts.append(Motion(_round(centre, 0.05 + 0.08 * rise, "#FFFFFF").points, "#FFFFFF", opacity * 0.8, False, True))   # pale at night too
        return parts
    return []


_DRAWINGS: dict[str, Callable[[_Frame, ObjectLook], list[Shape]]] = {
    "tree": _tree, "pine": _pine, "bush": _bush, "rock": _rock, "bench": _bench, "well": _well, "sign": _sign, "bridge": _bridge, "table": _table, "chair": _chair, "bed": _bed,
    "shelf": _shelf, "sofa": _sofa, "plant": _plant, "rug": _rug,
    "console": _console, "server_rack": _server_rack, "projector_pad": _projector_pad, "whiteboard": _whiteboard,
    "flower_arch": _flower_arch, "chess_table": _chess_table,
    "microscope": _microscope, "lab_stool": _lab_stool, "wall_clock": _wall_clock,
}


#: The kinds of objects with small lights the stage blinks (DESIGN.md §100.11, §102.2).
LIT_OBJECTS = ("server_rack", "console", "tower")


def object_lights(item: IsoObject, base: float) -> list[Point3]:
    """The small lights of ``item`` the stage blinks (world points, tile units): a server rack's
    lights on each unit; a console's lights on its cabinets; a tower's on its antenna's tip;
    none for other objects."""
    f = _Frame(item, base)
    if item.kind == "tower":
        return [f.p(f.width / 2, f.depth / 2, item.height + TOWER_ANTENNA)]
    if item.kind == "server_rack":
        a0, a1, b1 = 0.1, f.width - 0.1, f.depth - 0.12
        unit = (2.6 - 0.3) / RACK_UNITS
        return [f.p(a0 + a * (a1 - a0), b1 + 0.002, 0.16 + k * unit + unit / 2 - 0.03) for k in range(RACK_UNITS) for a in RACK_LIGHTS]
    if item.kind == "console":
        w = f.width
        return [f.p(a, 0.921, z) for a in (0.2, 0.3, w - 0.5, w - 0.4) for z in (0.6,)]
    return []


#: The radius (tile units) of the soft shadow under the objects that cast a round one.
SHADOW_RADII: dict[str, float] = {"tree": 0.45, "pine": 0.42, "bush": 0.48, "rock": 0.42, "lamp": 0.24, "well": 0.52, "sign": 0.22,
                                  "plant": 0.32, "flowers": 0.36, "chair": 0.42, "lab_stool": 0.26, "quantum_core": 0.42, "robot_arm": 0.36}
#: The shadows' colour and opacity (a tint of what lies under them).
SHADOW_COLOR = "#1F2430"
SHADOW_OPACITY = 0.16


#: The objects drawn as one clump per cell of their footprint (a flower bed, a hedge), with a
#: shadow under each.
BED_KINDS = ("flowers", "bush")
#: The objects drawn by their state too (DESIGN.md §89.10).
_STATEFUL: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {
    "house": _house, "flowers": _flowers, "lamp": _lamp, "tower": _tower, "laptop": _laptop, "terminal_kiosk": _terminal_kiosk,
    "quantum_core": _quantum_core, "robot_arm": _robot_arm, "centrifuge": _centrifuge, "coffee_machine": _coffee_machine,
}


def tower_screen(item: IsoObject, base: float) -> tuple[Point3, Point3, Point3, Point3] | None:
    """The corners of a tower's info screen (world points: bottom left, bottom right, top right,
    top left as seen), or ``None`` when it has none (DESIGN.md §102.2)."""
    if item.kind != "tower" or "screen" not in item.features:
        return None
    f = _Frame(item, base)
    lo, hi = TOWER_INSET, f.width - TOWER_INSET
    s0, s1, z0, z1 = screen_box(item.height)
    u0, u1 = lo + s0 * (hi - lo), lo + s1 * (hi - lo)
    b = f.depth - TOWER_INSET
    return f.p(u0, b, z0), f.p(u1, b, z0), f.p(u1, b, z1), f.p(u0, b, z1)


def object_shapes(item: IsoObject, look: ObjectLook, base: float, state: ObjectState | None = None) -> list[Shape]:
    """The shapes of ``item`` standing at height ``base`` (tile units), back to front, its soft
    shadow on the ground first; ``state``: open, lit (default: :func:`default_state`)."""
    frame = _Frame(item, base)
    state = state or default_state(item.kind)
    radius = SHADOW_RADII.get(item.kind)
    middles = _bed_cells(frame) if item.kind in BED_KINDS else [(frame.width / 2, frame.depth / 2)]
    shadow: list[Shape] = [] if radius is None else [Disc(frame.p(a, b, 0.0), radius, SHADOW_COLOR, False, SHADOW_OPACITY) for a, b in middles]
    if item.kind == "fence":
        return shadow + _fence(frame, look, item.links)
    if item.kind in _STATEFUL:
        return shadow + _STATEFUL[item.kind](frame, look, state)
    return shadow + _DRAWINGS[item.kind](frame, look)


def object_box(item: IsoObject, base: float) -> Box3:
    """The box ``item`` stands in, for the draw order: its footprint, up to its height (an object
    hanging on a wall: a thin slab on the wall's face)."""
    if item.kind in WALL_KINDS:
        return _wall_box(item, base)
    return Box3(item.column, item.row, base, item.column + item.width, item.row + item.depth, base + item.height)


__all__ = ["BED_KINDS", "DOORWAY", "LIGHT_POOL", "LIT_GLASS", "LIT_OBJECTS", "MOVING_KINDS", "OBJECT_COLORS", "Motion", "ObjectLook", "clock_hands",
           "object_box", "object_lights", "object_motion", "object_shapes", "tower_screen"]
