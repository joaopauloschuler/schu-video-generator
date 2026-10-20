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

from vidgen.cartoon.iso_drawing import Blobs, Disc, Line, Poly, Shape, Upright, box_shapes, mix, shade
from vidgen.world.iso import IsoObject, ObjectState, default_state
from vidgen.world.iso_view import ISO_RISE, Box3, Point3

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
DOORWAY = "#2E2A38"
BOOK_COLORS: tuple[str, ...] = ("#E2574C", "#F6C945", "#5BA35B", "#4C8DD6", "#B48EAD")


@dataclass(frozen=True)
class ObjectLook:
    """An object's resolved colours (``#rrggbb``)."""

    main: str
    detail: str


class _Frame:
    """An object's own frame: ``a`` across its front, ``b`` from its back to its front, ``z`` up
    from its base; facing right mirrors it (``x`` and ``y`` swap)."""

    def __init__(self, item: IsoObject, base: float) -> None:
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
                Disc(f.p(a0 + (a1 - a0) * 0.8, b, height * 0.52), 0.045, "#F2C14E", False)]
    swing = (a1 - a0) * 0.9
    out = (a0 - swing * 0.17, b + swing * 0.98)
    return [f.poly([(a0, b, 0.0), (a1, b, 0.0), (a1, b, height), (a0, b, height)], DOORWAY),
            f.poly([(a0, b, 0.0), (out[0], out[1], 0.0), (out[0], out[1], height), (a0, b, height)], mix(WOOD, "#FFFFFF", 0.12)),
            Disc(f.p(out[0] + 0.02, out[1] - 0.12, height * 0.52), 0.045, "#F2C14E", False)]


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
                           shade(leaves, 0.06 * (2 - k))))
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
    shapes.append(Poly(((x - half, y + half, z + 2.05), (x + half, y - half, z + 2.05), (x, y, z + 2.85)), roof))
    shapes.append(Poly(((x - half, y + half, z + 2.05), (x + half, y - half, z + 2.05), (x + half, y - half + 0.12, z + 1.95),
                        (x - half, y + half + 0.12, z + 1.95)), shade(roof, 0.3)))
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


_DRAWINGS: dict[str, Callable[[_Frame, ObjectLook], list[Shape]]] = {
    "tree": _tree, "pine": _pine, "bush": _bush, "rock": _rock, "bench": _bench, "well": _well, "sign": _sign, "bridge": _bridge, "table": _table, "chair": _chair, "bed": _bed,
    "shelf": _shelf, "sofa": _sofa, "plant": _plant, "rug": _rug,
}


#: The radius (tile units) of the soft shadow under the objects that cast a round one.
SHADOW_RADII: dict[str, float] = {"tree": 0.45, "pine": 0.42, "bush": 0.48, "rock": 0.42, "lamp": 0.24, "well": 0.52, "sign": 0.22,
                                  "plant": 0.32, "flowers": 0.36, "chair": 0.42}
#: The shadows' colour and opacity (a tint of what lies under them).
SHADOW_COLOR = "#1F2430"
SHADOW_OPACITY = 0.16


#: The objects drawn as one clump per cell of their footprint (a flower bed, a hedge), with a
#: shadow under each.
BED_KINDS = ("flowers", "bush")
#: The objects drawn by their state too (DESIGN.md §89.10).
_STATEFUL: dict[str, Callable[[_Frame, ObjectLook, ObjectState], list[Shape]]] = {"house": _house, "flowers": _flowers, "lamp": _lamp}


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
    """The box ``item`` stands in, for the draw order: its footprint, up to its height."""
    return Box3(item.column, item.row, base, item.column + item.width, item.row + item.depth, base + item.height)


__all__ = ["BED_KINDS", "DOORWAY", "LIGHT_POOL", "LIT_GLASS", "OBJECT_COLORS", "ObjectLook", "object_box", "object_shapes"]
