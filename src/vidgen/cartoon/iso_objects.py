"""The ready-made objects of an isometric place drawn as shapes (DESIGN.md §89.5): a house, trees,
a bush, a rock, flowers, a fence, a bench, a lamp, a well, a sign, a bridge, and indoors a table,
a chair, a bed, a shelf, a sofa, a plant and a rug. No manim.

Each is drawn in its own frame: ``a`` across its front (0 .. its width), ``b`` from its back (0)
to its front (its depth), ``z`` up from the ground it stands on. Facing left its front is the
face to the viewer's lower left; facing right the whole drawing is mirrored (``x`` and ``y``
swap), so its front is the face to the lower right.
"""

from __future__ import annotations

import importlib
import math
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

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
    "coffee_machine": ("#EEF0F3", "#E2574C"), "lab_stool": ("#4C8DD6", "#B9BFC9"), "wall_clock": ("#3A3F4B", "#E2574C"),
    "grow_rack": ("#B9BFC9", "#E86BFF"), "terrarium": ("#4FB65E", "#FF9BE0"), "specimen_tank": ("#3FE0C8", "#24464F"),
    "chemistry_bench": ("#5BE37A", "#FF5FA2"), "distillation_rig": ("#FF8A3D", "#5FD8FF"), "lab_fridge": ("#F4F6FA", "#7FD8FF"),
    "fume_hood": ("#C9CED6", "#9DF5C4"),
    "telescope": ("#F4F6FA", "#3B6FB6"), "satellite_dish": ("#E6EAF0", "#E2574C"), "charging_station": ("#E6EAF0", "#48E07A"),
    "crate_stack": ("#7A8699", "#B9BFC9"), "airlock": ("#8A93A3", "#F2A33A"), "printer_3d": ("#E6EAF0", "#FF8A3D"),
    "hazard_sign": ("#F6C945", "#2B2F3A"), "fire_extinguisher": ("#E2574C", "#2B2F3A"),
    "fireplace": ("#B5655A", "#E9E2D3"), "kitchen_counter": ("#86B6A2", "#EEE6D8"), "stove": ("#EEF0F3", "#E2574C"),
    "sink": ("#7FA7C9", "#E6EAF0"), "bookshelf_tall": ("#9C6B47", "#3B6FB6"), "armchair": ("#D9774B", "#F2D6A2"),
    "floor_lamp": ("#F2D6A2", "#3A3F4B"), "tv": ("#2B2F3A", "#6EC6FF"), "piano": ("#2E2A33", "#F2C14E"),
    "bathtub": ("#F4F6FA", "#7FC8E8"), "wardrobe": ("#B07A4F", "#7FA7C9"), "crib": ("#F4F6FA", "#F2A7C3"),
    "cafe_table": ("#3A3F4B", "#F4F1EA"), "counter": ("#B07A4F", "#EEE6D8"), "cash_register": ("#E6EAF0", "#E2574C"),
    "display_case": ("#F2E6D8", "#F2A7C3"), "market_stall": ("#E2574C", "#F4F6FA"), "vending_machine": ("#E2574C", "#6EC6FF"),
    "street_lamp": ("#34404F", "#F7E7B0"), "traffic_light": ("#5A6272", "#F2C14E"), "bus_stop": ("#4C6A85", "#E2574C"),
    "mailbox": ("#D7322B", "#F2C14E"), "fountain": ("#D8D2C4", "#6FB8E0"), "phone_booth": ("#D7322B", "#F2C14E"),
    "car": ("#4C8DD6", "#CFE8F7"), "bicycle": ("#2EA38A", "#D9B07A"), "newsstand": ("#3E8E6A", "#F2C14E"),
    "campfire": ("#9A958C", "#7A5236"), "tent": ("#E8833A", "#F4E3B5"), "log": ("#7A5236", "#5BA35B"), "stump": ("#7A5236", "#E9C99A"),
    "mushroom_ring": ("#E2574C", "#F4F6FA"), "pond": ("#D2C29A", "#5FA8D3"), "scarecrow": ("#4C8DD6", "#E8C35A"), "beehive": ("#E2B54A", "#9C6B47"),
    "vegetable_patch": ("#A0703F", "#E2574C"), "wheelbarrow": ("#4FA36B", "#9C6B47"), "hay_bale": ("#E8C35A", "#B0563A"),
    "school_desk": ("#D9A066", "#4C6A85"), "desk_with_pc": ("#D8C3A0", "#4C9BE0"), "water_cooler": ("#EEF1F5", "#7EC8F0"),
    "printer": ("#E6EAF0", "#4CB8FF"), "globe": ("#4C8DD6", "#9C6B47"), "trophy_shelf": ("#7A5236", "#F2C14E"),
    "treasure_chest": ("#9C5B2E", "#E8B83A"), "cauldron": ("#7BE36A", "#3A3F4B"), "giant_crystal": ("#A98BFF", "#6B6478"),
    "throne": ("#B0303A", "#E8B83A"), "torch_sconce": ("#4A4F5B", "#9C6B47"), "signpost": ("#D9A066", "#7A5236"),
    "archway": ("#C9C2B4", "#5BA35B"), "statue": ("#7CB8A4", "#B9B4AA"),
}
GLASS = "#D6EEF8"
FRAME = "#F4F6FA"
WOOD = "#9C6B47"
WATER_DEEP = "#4D8FC0"
LAMP_GLOW = "#FFF1B8"
#: A lamp's lantern and a house's windows when lit, and the dark of an open doorway (DESIGN.md §89.10).
LIT_GLASS = "#FFD75E"
LIT_CORE = "#FFF6D0"
#: The pool of light under a lit lamp (:func:`light_pool`, DESIGN.md §104): rings of a saturated
#: warm amber (its middle lighter), each a tint of the ground: (share of the radius, opacity). A
#: pale yellow, half seen through over the night's blue-graded ground, read olive; this stays warm.
#: Drawn only in the picture of the pools, shown as strong as the light is dark (faint by day).
LIGHT_POOL = "#FF8F3A"
POOL_CORE = "#FFC062"
POOL_RINGS = ((1.0, 0.34), (0.68, 0.34), (0.4, 0.38))
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


def light_pool(centre: Point3, radius: float, strength: float = 1.0) -> list[Shape]:
    """A lit lamp's soft pool of warm light on the ground round ``centre`` (``radius`` in tile
    units; ``strength`` scales it): :data:`POOL_RINGS` of discs marked ``pool`` (not dimmed at
    night; the stage shows them as strong as its light is dark, faint by day)."""
    return [Disc((centre[0], centre[1], centre[2] + 0.0005 * k), radius * share, POOL_CORE if k == len(POOL_RINGS) - 1 else LIGHT_POOL, False,
                 opacity * strength, holds_snow=False, pool=True) for k, (share, opacity) in enumerate(POOL_RINGS)]


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
    pool = light_pool((x, y, z + 0.01), LIGHT_POOL_RADIUS) if state.on else []
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
        start, end = _reading(f, start, a0, a1), _reading(f, end, a0, a1)   # read from the left facing either way
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
            start, end = (_reading(f, a, a0, a1) for a in (a0 + 0.06, a0 + 0.06 + (a1 - a0 - 0.12) * (0.85, 0.5, 0.7, 0.35, 0.6)[k]))
            shapes.append(_glow_rect(f, min(start, end), max(start, end), 0.462, zz, zz + 0.045, SCREEN_LINE))
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


#: Coffee's brown, a coffee machine's mug: its spot (a, b in the frame) and the height of its rim.
COFFEE = "#6B3F22"
MUG_SPOT = (0.5, 0.63)
MUG_RIM = 1.09


def _coffee_machine(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A drip coffee machine on a cabinet: a light body in the main colour (a column and a head
    over the drip tray with a band and a light in the detail colour, lit when on), a window on
    its side showing the coffee, a spout over a big white mug of coffee (pouring when on; the
    stage puffs steam from the mug, :func:`object_motion`)."""
    shapes = _cabinet(f)
    w, body = f.width, look.main
    a0, a1, b0, back, b1 = 0.2, w - 0.2, 0.22, 0.46, 0.76
    shapes += f.box(a0, b0, 0.8, a1, back, 1.6, body)
    shapes.append(f.poly([(a0 + 0.06, back + 0.001, 0.86), (a1 - 0.06, back + 0.001, 0.86), (a1 - 0.06, back + 0.001, 1.3), (a0 + 0.06, back + 0.001, 1.3)],
                         "#4A5160", False))
    shapes += f.box(a0 + 0.03, back, 0.8, a1 - 0.03, b1, 0.87, "#8A93A3")   # the drip tray and its grille
    for k in range(1, 4):
        shapes.append(Line((f.p(a0 + 0.08, back + (b1 - back) * k / 4, 0.871), f.p(a1 - 0.08, back + (b1 - back) * k / 4, 0.871)), shade("#8A93A3", 0.3), 0.7))
    ma, mb = MUG_SPOT[0] * w, MUG_SPOT[1]
    mug = f.p(ma, mb, 0.0)
    shapes += [Upright(mug[0], mug[1], f.base + 0.87, f.base + MUG_RIM, 0.1, "#F4F6FA"), Disc((mug[0], mug[1], f.base + MUG_RIM + 0.001), 0.082, COFFEE, False)]
    handle = [_screen((mug[0], mug[1], f.base + 0.98), 0.06 + 0.045 * math.sin(math.pi * k / 8), 0.06 * math.cos(math.pi * k / 8)) for k in range(9)]
    shapes.append(Line(tuple(handle), "#F4F6FA", 2.6))
    if state.on:   # a thin stream of coffee from the spout
        shapes.append(Line(((mug[0], mug[1], f.base + 1.24), (mug[0], mug[1], f.base + MUG_RIM + 0.01)), COFFEE, 1.6))
    shapes += f.box(a0, back, 1.3, a1, b1, 1.6, body)   # the head over the mug, its spout under it
    shapes.append(f.poly([(a0, b1 + 0.001, 1.47), (a1, b1 + 0.001, 1.47), (a1, b1 + 0.001, 1.55), (a0, b1 + 0.001, 1.55)], f.front(look.detail), False))
    shapes += f.box(ma - 0.05, mb - 0.05, 1.24, ma + 0.05, mb + 0.05, 1.3, CASING)
    shapes.append(_indicator(f, a0 + 0.08, a0 + 0.18, b1 + 0.002, 1.36, 1.42, mix(look.detail, SHINE, 0.2), state.on))
    shapes.append(Disc(f.p(a1 - 0.14, b1 + 0.002, 1.39), 0.03, CASING, True, holds_snow=False))
    window = [(a1 + 0.001, b0 + 0.05, 0.95), (a1 + 0.001, back - 0.05, 0.95), (a1 + 0.001, back - 0.05, 1.5), (a1 + 0.001, b0 + 0.05, 1.5)]
    shapes.append(f.poly(window, GLASS))
    level = [(a1 + 0.002, b0 + 0.06, 0.96), (a1 + 0.002, back - 0.06, 0.96), (a1 + 0.002, back - 0.06, 1.22), (a1 + 0.002, b0 + 0.06, 1.22)]
    shapes.append(f.poly(level, COFFEE, False))
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
    """The box of an object hanging on a wall: a slab on the wall's face, round its height (a
    clock's thin, a torch sconce's as deep as its torch reaches out, §104)."""
    f = _Frame(item, base)
    if item.kind == "torch_sconce":
        low, high, reach = _more(item.kind).SCONCE_SPAN
    else:
        radius = CLOCK_RADIUS * min(f.width, 1.6)
        low, high, reach = CLOCK_HEIGHT - radius - 0.05, CLOCK_HEIGHT + radius + 0.05, 0.06
    (x0, y0, z0), (x1, y1, z1) = f.p(0.0, f.depth, low), f.p(f.width, f.depth + reach, high)
    return Box3(min(x0, x1), min(y0, y1), z0, max(x0, x1), max(y0, y1), z1)


# ----- plants, glassware and liquids (DESIGN.md §103, Step 259) ------------------------------------------

#: Extra liquid colours of the glassware after its main (``color``) and detail ones, a dark metal,
#: a pot's terracotta, soil, a lit glass's highlight and the pale of mist and vapour.
LIQUIDS = ("#4CB8FF", "#FFC23D", "#B07CFF")
METAL = "#5A6272"
POT = "#C8734A"
SOIL = "#6B4A2E"
SHINE = "#FFFFFF"
MIST = "#E6F6FF"
#: Seconds a bubble takes to rise through a specimen tank, a drip to fall in a distillation rig,
#: a puff of mist or vapour to fade, and a fume hood's fan to turn once.
BUBBLE_SECONDS = 2.4
DRIP_SECONDS = 1.1
MIST_SECONDS = 2.6
FAN_SECONDS = 0.6


def _liquid(color: str, on: bool) -> str:
    """A liquid's fill: brighter while its object works (then it glows, not dimmed by the light)."""
    return mix(color, SHINE, 0.18) if on else color


def _profile(base: Point3, points: list[tuple[float, float]], fill: str, ink: bool = True, glow: bool = False) -> Poly:
    """A cut-out facing the viewer (a flask, a tube): ``points`` across (``du``) and up (``dv``)
    the picture from ``base`` (tile widths)."""
    return Poly(tuple(_screen(base, du, dv) for du, dv in points), fill, ink, glow)


def _arc(du: float, dv: float, rx: float, ry: float, start: float, end: float, steps: int = 12) -> list[tuple[float, float]]:
    """Points of an elliptic arc round (``du``, ``dv``) from angle ``start`` to ``end`` (radians)."""
    return [(du + rx * math.cos(start + (end - start) * k / steps), dv + ry * math.sin(start + (end - start) * k / steps)) for k in range(steps + 1)]


def _cylinder(x: float, y: float, z0: float, z1: float, radius: float, fill: str, *, ink: bool = True, glow: bool = False,
              lid: str | None = None) -> list[Shape]:
    """An upright cylinder as flat shapes (glass, a liquid): its body and, with ``lid``, its top
    in that colour."""
    front = [(x + radius * math.cos(t), y + radius * math.sin(t), z0) for t in [-math.pi / 4 + math.pi * k / 16 for k in range(17)]]
    back = [(x + radius * math.cos(t), y + radius * math.sin(t), z1) for t in [3 * math.pi / 4 + math.pi * k / 16 for k in range(17)]]
    shapes: list[Shape] = [Poly(tuple(front + back), fill, ink, glow)]
    if lid is not None:
        shapes.append(Poly(_flat_circle((x, y, z1), radius, 24), lid, ink, glow))
    return shapes


def _flask(base: Point3, size: float, liquid: str, level: float, on: bool) -> list[Shape]:
    """A conical flask standing at ``base``, ``size`` its height on the picture (tile widths),
    filled to ``level`` of its body with ``liquid`` (glowing while ``on``)."""
    b, n, shoulder = 0.42 * size, 0.1 * size, 0.62 * size
    glass = _profile(base, [(-b, 0.0), (b, 0.0), (n, shoulder), (n, size), (-n, size), (-n, shoulder)], GLASS)
    top = shoulder * level
    width = b - (b - n) * level
    fluid = _profile(base, [(-b + 0.015, 0.012), (b - 0.015, 0.012), (width - 0.012, top), (-width + 0.012, top)], _liquid(liquid, on), False, on)
    return [glass, fluid, _profile(base, [(-b * 0.55, 0.06 * size), (-b * 0.42, 0.06 * size), (-n * 0.4, shoulder * 0.95), (-n * 0.7, shoulder * 0.95)],
                                    mix(GLASS, SHINE, 0.7), False),
            _profile(base, [(-n * 1.3, size), (n * 1.3, size), (n * 1.3, size + 0.02), (-n * 1.3, size + 0.02)], GLASS)]


def _round_flask(base: Point3, radius: float, neck: float, liquid: str, level: float, on: bool) -> list[Shape]:
    """A round-bottomed flask: a ball of ``radius`` (tile widths) whose bottom is at ``base``, a
    neck ``neck`` long, filled to ``level`` (share of the ball from its bottom) with ``liquid``."""
    n = radius * 0.3
    shapes: list[Shape] = [_profile(base, [(-n, radius), (n, radius), (n, 2 * radius + neck), (-n, 2 * radius + neck)], GLASS),
                           _profile(base, _arc(0.0, radius, radius, radius, 0.0, 2 * math.pi, 24)[:-1], GLASS)]
    cut = math.asin(min(max(1.0 - 2.0 * level, -0.99), 0.99))   # the surface's angle below the middle
    shapes.append(_profile(base, _arc(0.0, radius, radius * 0.9, radius * 0.9, -math.pi - cut, cut, 16), _liquid(liquid, on), False, on))
    shapes.append(_profile(base, _arc(-radius * 0.35, radius * 1.35, radius * 0.22, radius * 0.16, 0.0, 2 * math.pi, 10)[:-1], mix(GLASS, SHINE, 0.7), False))
    return shapes


def _tube(base: Point3, height: float, liquid: str, on: bool) -> list[Shape]:
    """A test tube standing at ``base`` (its round bottom), ``height`` tall on the picture, half full."""
    r = 0.028
    glass = _profile(base, [*_arc(0.0, r, r, r, math.pi, 2 * math.pi, 6), (r, height), (-r, height)], GLASS)
    fluid = _profile(base, [*_arc(0.0, r, r * 0.7, r * 0.7, math.pi, 2 * math.pi, 6), (r * 0.7, height * 0.55), (-r * 0.7, height * 0.55)],
                     _liquid(liquid, on), False, on)
    return [glass, fluid]


def _grow_rack(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """An open rack of three shelves with potted plants, its back to the wall, a grow light under
    each shelf above them: purple-pink (the detail colour) and washing the plants' tier in its
    light when on, dark when off."""
    w = f.width
    a0, a1, b0, b1 = 0.08, w - 0.08, 0.14, f.depth - 0.22
    frame, light = look.main, look.detail
    tiers = (0.1, 0.85, 1.6, 2.3)
    shapes = f.box(a0, b0 - 0.04, 0.0, a1, b0, tiers[-1] + 0.06, shade(frame, 0.45))
    for k in range(3):
        z, z_next = tiers[k], tiers[k + 1]
        wash = mix(light, "#2B2F3A", 0.45) if state.on else shade(frame, 0.55)
        shapes.append(f.poly([(a0 + 0.02, b0 + 0.001, z + 0.06), (a1 - 0.02, b0 + 0.001, z + 0.06), (a1 - 0.02, b0 + 0.001, z_next),
                              (a0 + 0.02, b0 + 0.001, z_next)], wash, False, state.on))
        shapes += f.box(a0, b0, z, a1, b1, z + 0.06, frame)
        if state.on:   # the shelf lit by the grow light over it
            shapes.append(f.poly([(a0 + 0.03, b0 + 0.02, z + 0.061), (a1 - 0.03, b0 + 0.02, z + 0.061), (a1 - 0.03, b1 - 0.02, z + 0.061),
                                  (a0 + 0.03, b1 - 0.02, z + 0.061)], mix(light, SHINE, 0.3), False, True))
        for j, share in enumerate((0.2, 0.5, 0.8)):
            a = a0 + (a1 - a0) * share
            b = (b0 + b1) / 2 + (0.05 if j % 2 else -0.03)
            pot = f.p(a, b, z + 0.06)
            shapes += [Upright(pot[0], pot[1], pot[2], pot[2] + 0.2, 0.08, POT), Disc((pot[0], pot[1], pot[2] + 0.2), 0.065, SOIL, False, holds_snow=False)]
            leaves = mix(mix(look.main, "#3FA34D", 0.85), light, 0.22) if state.on else "#4C9A55"
            top = _screen((pot[0], pot[1], pot[2] + 0.2), 0.0, 0.0)
            spread = 0.07 + 0.02 * ((k + j) % 2)
            shapes.append(Blobs(tuple(_screen(top, du, dv) for du, dv in ((0.0, 0.17), (-spread, 0.1), (spread, 0.1), (0.0, 0.07))), (0.08, 0.06, 0.06, 0.06),
                                leaves))
            if (k + j) % 3 == 0:   # a few ripe ones
                shapes.append(Blobs((_screen(top, 0.03, 0.12),), (0.025,), "#E2574C", False))
        shapes += f.box(a0 + 0.06, b1 - 0.14, z_next - 0.05, a1 - 0.06, b1 - 0.04, z_next, CASING)
        shapes.append(_indicator(f, a0 + 0.08, a1 - 0.08, b1 - 0.039, z_next - 0.045, z_next - 0.005, mix(light, SHINE, 0.45), state.on))
    shapes += f.box(a0, b0, tiers[-1], a1, b1, tiers[-1] + 0.06, frame)
    for a in (a0, a1 - 0.05):
        shapes += f.box(a, b1 - 0.05, 0.0, a + 0.05, b1, tiers[-1] + 0.06, shade(frame, 0.1))
    return shapes


def _terrarium(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A glass dome on a round stand with a little garden inside: moss, a leafy plant in the main
    colour and tiny flowers in the detail colour that glow faintly (at night too)."""
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    z = f.base
    floor = z + 0.78
    radius = 0.3
    across, low = radius * math.sqrt(2) / 2, radius * math.sqrt(2) / 4
    centre = (x, y, floor)
    shapes: list[Shape] = [Upright(x, y, z, z + 0.12, 0.26, METAL), Upright(x, y, z + 0.12, floor - 0.06, 0.07, METAL),
                           Upright(x, y, floor - 0.08, floor, radius + 0.03, shade(METAL, 0.1))]
    dome = [*_arc(0.0, 0.0, across, 0.55, 0.0, math.pi, 16), *_arc(0.0, 0.0, across, low, math.pi, 2 * math.pi, 12)[1:-1]]
    shapes.append(_profile(centre, dome, mix(GLASS, look.detail, 0.12)))
    shapes.append(Disc((x, y, floor + 0.005), radius * 0.92, SOIL, False, holds_snow=False))
    shapes.append(Disc((x, y, floor + 0.01), radius * 0.85, look.detail, False, 0.28, glow=True, holds_snow=False))
    shapes.append(Blobs(tuple(_screen(centre, du, 0.02) for du in (-0.12, 0.0, 0.12)), (0.06, 0.07, 0.06), "#5E9E4E", False))
    leaves = mix(look.main, "#2F6B3A", 0.1)
    shapes.append(Line((_screen(centre, 0.0, 0.0), _screen(centre, 0.0, 0.2)), shade(leaves, 0.3), 1.6))
    shapes.append(Blobs(tuple(_screen(centre, du, dv) for du, dv in ((0.0, 0.3), (-0.09, 0.22), (0.09, 0.22), (-0.04, 0.14), (0.06, 0.15))),
                        (0.08, 0.065, 0.065, 0.06, 0.06), leaves))
    for du, dv in ((-0.13, 0.08), (0.14, 0.1), (0.05, 0.36), (-0.07, 0.04)):
        shapes.append(Poly(_round(_screen(centre, du, dv), 0.026, look.detail).points, look.detail, False, True))
        shapes.append(Poly(_round(_screen(centre, du, dv), 0.01, SHINE).points, SHINE, False, True))
    shapes.append(Line(tuple(_screen(centre, du, dv) for du, dv in _arc(0.0, 0.0, across * 0.78, 0.45, math.pi * 0.62, math.pi * 0.85, 6)),
                       mix(GLASS, SHINE, 0.8), 2.2))
    return shapes


def _tank_parts(f: _Frame) -> tuple[float, float, float, float, float]:
    """A specimen tank's middle (x, y), its liquid's bottom and top and the glass's radius."""
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    return x, y, f.base + 0.36, f.base + 2.0, 0.3


def _specimen_tank(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A tall glass cylinder of liquid (the main colour, glowing when on; the stage bubbles it)
    on a metal base with a status light, a cap and a pipe; a dark shape floats in it when the
    placing gives a ``detail`` colour."""
    x, y, bottom, top, radius = _tank_parts(f)
    z = f.base
    liquid = _liquid(look.main, state.on)
    shapes: list[Shape] = [Upright(x, y, z, z + 0.32, radius + 0.06, METAL)]
    shapes.append(_round((x + (radius + 0.06) * 0.7, y + (radius + 0.06) * 0.7, z + 0.17), 0.035, DISPLAY_GREEN if state.on else LED_OFF, True, state.on))
    shapes += _cylinder(x, y, z + 0.32, z + 2.12, radius, GLASS)
    shapes += _cylinder(x, y, bottom, top, radius * 0.9, liquid, ink=False, glow=state.on, lid=mix(liquid, SHINE, 0.25))
    if f.item.detail is not None:   # a floating silhouette
        body = mix(look.detail, look.main, 0.2)
        middle = (x, y, (bottom + top) / 2 + 0.1)
        shapes += [_ribbon(_screen(middle, -0.03, -0.05), _screen(middle, -0.1, -0.32), 0.025, body),
                   _ribbon(_screen(middle, 0.03, -0.05), _screen(middle, 0.08, -0.33), 0.025, body),
                   _ribbon(_screen(middle, -0.04, 0.12), _screen(middle, -0.13, -0.02), 0.022, body),
                   _ribbon(_screen(middle, 0.04, 0.12), _screen(middle, 0.13, 0.0), 0.022, body)]
        shapes.append(Blobs((_screen(middle, 0.0, 0.07), _screen(middle, 0.0, -0.03), _screen(middle, 0.0, 0.24)), (0.065, 0.06, 0.075), body))
    shapes.append(Poly((_screen((x, y, z + 0.42), -radius * 0.55, 0.0), _screen((x, y, z + 0.42), -radius * 0.38, 0.0),
                        _screen((x, y, z + 2.02), -radius * 0.38, 0.0), _screen((x, y, z + 2.02), -radius * 0.55, 0.0)), mix(GLASS, SHINE, 0.65), False))
    shapes += [Upright(x, y, z + 2.1, z + 2.3, radius + 0.04, METAL), Upright(x, y, z + 2.3, z + 2.45, 0.07, shade(METAL, 0.15))]
    return shapes


def _bench_vessels(f: _Frame) -> list[tuple[str, Point3, float, int]]:
    """A chemistry bench's glassware on its top, back to front: (what, where it stands, its size
    on the picture, its liquid's colour: an index into the bench's palette)."""
    w = f.width
    top = 0.86
    found = [("rack", f.p(0.24 * w, 0.34, top), 0.22 * w, 0), ("flask", f.p(0.52 * w, 0.4, top), 0.5, 0),
             ("round", f.p(0.8 * w, 0.36, top), 0.15, 1), ("beaker", f.p(0.3 * w, 0.74, top), 0.26, 2), ("flask", f.p(0.66 * w, 0.76, top), 0.32, 3)]
    return sorted(found, key=lambda v: v[1][0] + v[1][1])


def _bench_palette(look: ObjectLook) -> tuple[str, ...]:
    return (look.main, look.detail, *LIQUIDS)


def _chemistry_bench(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A lab bench with a dark top: a test-tube rack, flasks and a beaker of liquids in the main,
    detail and a few more colours, glowing when on (the stage bubbles and steams them)."""
    w = f.width
    shapes = _cabinet(f)
    shapes += f.box(0.04, 0.14, 0.8, w - 0.04, f.depth - 0.03, 0.86, "#3A3F4B")
    palette = _bench_palette(look)
    on = state.on
    for what, base, size, color in _bench_vessels(f):
        if what == "rack":
            a_from, a_to = 0.24 * w - size, 0.24 * w + size
            shapes += f.box(a_from, 0.27, 0.86, a_to, 0.41, 0.9, WOOD)
            count = 4
            for k in range(count):
                a = a_from + (a_to - a_from) * (k + 0.5) / count
                shapes += _tube(f.p(a, 0.34, 0.9), 0.36, palette[(k + 1) % len(palette)], on)
            shapes += f.box(a_from, 0.29, 1.08, a_to, 0.39, 1.12, WOOD)
            for a in (a_from, a_to - 0.04):
                shapes += f.box(a, 0.31, 0.9, a + 0.04, 0.37, 1.12, shade(WOOD, 0.1))
        elif what == "flask":
            shapes += _flask(base, size, palette[color], 0.55, on)
        elif what == "round":
            shapes.append(Disc((base[0], base[1], base[2] + 0.005), 0.13, "#8A93A3", True, holds_snow=False))
            shapes += _round_flask(base, size, 0.18, palette[color], 0.55, on)
        else:   # a beaker with a scale
            r = size * 0.42
            shapes.append(_profile(base, [(-r, 0.0), (r, 0.0), (r, size), (r + 0.02, size + 0.02), (-r, size + 0.01)], GLASS))
            shapes.append(_profile(base, [(-r + 0.012, 0.012), (r - 0.012, 0.012), (r - 0.012, size * 0.6), (-r + 0.012, size * 0.6)],
                                   _liquid(palette[color], on), False, on))
            for k in range(3):
                shapes.append(Line((_screen(base, r * 0.3, size * (0.3 + 0.2 * k)), _screen(base, r * 0.75, size * (0.3 + 0.2 * k))), SHINE, 0.8))
    return shapes


def _rig_parts(f: _Frame) -> tuple[Point3, Point3, Point3, Point3]:
    """A distillation rig's boiling flask's bottom, the condenser's start and end, and the
    receiving flask's base (world points)."""
    boil = f.p(0.18, 0.6, 1.02)
    start = _screen(boil, 0.0, 0.5)
    catch = f.p(0.84, 0.46, 0.86)
    return boil, start, _screen(catch, 0.04, 0.52), catch


def _distillation_rig(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A distillation rig on a bench cabinet: a burner under a round flask of the main colour's
    liquid on a ring stand, a slanting condenser with a coil (the detail colour) down to a conical
    flask catching the distillate (detail). When on the liquids glow, the burner's flame burns and
    the stage drips the distillate and boils the flask."""
    shapes = _cabinet(f)
    boil, start, end, catch = _rig_parts(f)
    on = state.on
    post = f.p(0.14, 0.3, 0.0)
    shapes += [Disc((post[0], post[1], f.base + 0.81), 0.1, METAL, True, holds_snow=False), Upright(post[0], post[1], f.base + 0.8, f.base + 1.85, 0.025, METAL)]
    shapes.append(Line((f.p(0.14, 0.3, 1.62), _screen(start, 0.0, -0.1)), METAL, 1.8))
    burner = f.p(0.18, 0.6, 0.8)
    shapes += [Upright(burner[0], burner[1], burner[2], burner[2] + 0.06, 0.1, METAL), Upright(burner[0], burner[1], burner[2] + 0.06, burner[2] + 0.12, 0.035, "#8A93A3")]
    if on and not look.moving:   # a still flame (the stage flickers it)
        shapes.append(_profile(_screen(burner, 0.0, 0.07), [(-0.035, 0.0), (0.035, 0.0), (0.0, 0.11)], "#FF9A3D", False, True))
    ring = f.p(0.18, 0.6, 1.04)
    shapes.append(Line(_flat_circle(ring, 0.12, 16) + (_flat_circle(ring, 0.12, 16)[0],), METAL, 1.2))
    shapes += _round_flask(_screen(boil, 0.0, -0.04), 0.15, 0.24, look.main, 0.6, on)
    shapes += _flask(catch, 0.42, look.detail, 0.35, on)
    shapes.append(_ribbon(start, end, 0.05, GLASS))
    coil = []
    for k in range(25):
        s = k / 24
        p = (start[0] + (end[0] - start[0]) * s, start[1] + (end[1] - start[1]) * s, start[2] + (end[2] - start[2]) * s)
        coil.append(_screen(p, 0.0, 0.028 * math.sin(s * math.pi * 14)))
    shapes.append(Line(tuple(coil), mix(look.detail, SHINE, 0.2) if on else shade(look.detail, 0.15), 1.3))
    for s in (0.12, 0.88):   # the jacket's hose nozzles
        p = (start[0] + (end[0] - start[0]) * s, start[1] + (end[1] - start[1]) * s, start[2] + (end[2] - start[2]) * s)
        shapes.append(_ribbon(p, _screen(p, 0.0, 0.07), 0.015, METAL))
    return shapes


def _fridge_bottles(f: _Frame, a0: float, a1: float, b: float, z0: float, z1: float, look: ObjectLook, lit: bool) -> list[Shape]:
    """A fridge's inside on the face at ``b``: dark (lit pale in the detail colour when ``lit``),
    shelves and rows of coloured sample bottles."""
    inside = mix(look.detail, SHINE, 0.65) if lit else "#2E3A48"
    shapes: list[Shape] = [f.poly([(a0, b, z0), (a1, b, z0), (a1, b, z1), (a0, b, z1)], inside, False, lit)]
    colors = (*LIQUIDS, "#E2574C", "#48E07A")
    rows = 3
    for row in range(rows):
        z = z0 + (z1 - z0) * row / rows + 0.02
        shapes.append(f.poly([(a0, b + 0.001, z), (a1, b + 0.001, z), (a1, b + 0.001, z + 0.025), (a0, b + 0.001, z + 0.025)], "#B9BFC9", False))
        count = 4
        for k in range(count):
            a = a0 + (a1 - a0) * (k + 0.5) / count
            color = colors[(row * 2 + k) % len(colors)]
            height = 0.22 + 0.06 * ((row + k) % 2)
            shapes.append(f.poly([(a - 0.04, b + 0.002, z + 0.025), (a + 0.04, b + 0.002, z + 0.025), (a + 0.04, b + 0.002, z + height),
                                  (a - 0.04, b + 0.002, z + height)], mix(color, SHINE, 0.15) if lit else shade(color, 0.25), True, lit))
            shapes.append(f.poly([(a - 0.025, b + 0.002, z + height), (a + 0.025, b + 0.002, z + height), (a + 0.025, b + 0.002, z + height + 0.05),
                                  (a - 0.025, b + 0.002, z + height + 0.05)], "#F4F6FA", True))
    return shapes


def _fridge_box(f: _Frame) -> tuple[float, float, float, float, float]:
    """A lab fridge's body: a from, a to, b at its back and front, its height."""
    return 0.1, f.width - 0.1, 0.14, f.depth - 0.1, 2.25


def _lab_fridge(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A tall lab fridge: its body in the main colour, a glass door showing shelves of coloured
    sample bottles (lit pale in the detail colour while on or open), a handle, a display and
    vents; open, its door swung out towards the viewer (the stage pours cold mist from it)."""
    a0, a1, b0, b1, h = _fridge_box(f)
    body = look.main
    lit = state.on or state.open
    shapes = f.box(a0, b0, 0.0, a1, b1, h, body)
    shapes.append(f.poly([(a0 + 0.05, b1, 0.05), (a1 - 0.05, b1, 0.05), (a1 - 0.05, b1, 0.18), (a0 + 0.05, b1, 0.18)], shade(body, 0.35), False))
    for k in range(4):
        z = 0.08 + k * 0.025
        shapes.append(Line((f.p(a0 + 0.1, b1 + 0.001, z), f.p(a1 - 0.1, b1 + 0.001, z)), shade(body, 0.5), 0.7))
    door0, door1 = 0.22, h - 0.08
    shapes.append(_indicator(f, a0 + 0.08, a0 + 0.3, b1 + 0.001, door1 - 0.12, door1 - 0.04, look.detail, lit))
    if not state.open:
        shapes.append(f.poly([(a0 + 0.04, b1, door0), (a1 - 0.04, b1, door0), (a1 - 0.04, b1, door1 - 0.16), (a0 + 0.04, b1, door1 - 0.16)], f.front(body)))
        shapes += _fridge_bottles(f, a0 + 0.1, a1 - 0.16, b1 + 0.002, door0 + 0.1, door1 - 0.26, look, lit)
        shapes.append(f.poly([(a0 + 0.14, b1 + 0.004, door0 + 0.14), (a0 + 0.24, b1 + 0.004, door0 + 0.14), (a0 + 0.42, b1 + 0.004, door1 - 0.3),
                              (a0 + 0.32, b1 + 0.004, door1 - 0.3)], mix(GLASS, SHINE, 0.5), False))
        return shapes + f.box(a1 - 0.12, b1, door0 + 0.5, a1 - 0.08, b1 + 0.06, door1 - 0.5, "#8A93A3")
    shapes += _fridge_bottles(f, a0 + 0.04, a1 - 0.04, b1 + 0.002, door0, door1 - 0.16, look, lit)
    swing = (a1 - a0) * 0.85
    out = (a0 - swing * 0.2, b1 + swing * 0.97)
    leaf = [(a0, b1, door0), (out[0], out[1], door0), (out[0], out[1], door1 - 0.16), (a0, b1, door1 - 0.16)]
    shapes.append(f.poly(leaf, mix(body, SHINE, 0.1)))
    inner = [(a0 + (out[0] - a0) * s, b1 + (out[1] - b1) * s, z) for s, z in ((0.15, door0 + 0.12), (0.85, door0 + 0.12), (0.85, door1 - 0.28), (0.15, door1 - 0.28))]
    shapes.append(f.poly(inner, mix(GLASS, "#2E3A48", 0.35), False))
    return shapes


def _hood_parts(f: _Frame) -> tuple[float, float, float, float]:
    """A fume hood's chamber: a from, a to, b at its front, and its fan's middle height."""
    return 0.08, f.width - 0.08, f.depth - 0.12, 2.27


def _fan_blades(f: _Frame, a: float, b: float, z: float, radius: float, turn: float, fill: str) -> list[Motion]:
    """A fan's three blades on the face at ``b`` round (``a``, ``z``), turned ``turn`` radians."""
    blades = []
    for k in range(3):
        t = turn + 2 * math.pi * k / 3
        points = [(a + r * math.cos(t + d), b, z + r * math.sin(t + d)) for r, d in ((0.02, -0.5), (radius, -0.35), (radius, 0.25), (0.02, 0.5))]
        blades.append(Motion(tuple(f.p(*q) for q in points), fill, ink=False))
    return blades


def _fume_hood(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A fume hood: a cabinet in the main colour under a chamber with a glass sash in front (lit
    pale in the detail colour while on, with glassware inside), a fan housing on top with a round
    grille (the stage spins its fan and wafts vapour in the chamber while on) and a duct."""
    a0, a1, front, fan_z = _hood_parts(f)
    w = f.width
    body = look.main
    on = state.on
    b0 = 0.14
    shapes = f.box(a0, b0, 0.0, a1, front, 0.85, body)
    shapes.append(Line((f.p(w / 2, front, 0.08), f.p(w / 2, front, 0.75)), shade(body, 0.35), 0.8))
    shapes += f.box(a0, b0, 0.85, a1, front, 2.1, body)
    inside = mix(look.detail, SHINE, 0.55) if on else "#3A4250"
    shapes.append(f.poly([(a0 + 0.07, front + 0.001, 0.9), (a1 - 0.07, front + 0.001, 0.9), (a1 - 0.07, front + 0.001, 1.95), (a0 + 0.07, front + 0.001, 1.95)],
                         inside, False, on))
    shapes.append(_indicator(f, a1 - 0.2, a1 - 0.1, front + 0.001, 1.99, 2.05, DISPLAY_GREEN, on))
    at = f.p(0.35 * w, front, 0.92)
    shapes += _flask(_screen(at, 0.0, 0.0), 0.36, look.detail, 0.5, on)
    shapes += _tube(_screen(f.p(0.62 * w, front, 0.92), 0.0, 0.0), 0.3, LIQUIDS[0], on)
    shapes += _tube(_screen(f.p(0.7 * w, front, 0.92), 0.0, 0.0), 0.26, LIQUIDS[1], on)
    sash = 1.5
    shapes.append(f.poly([(a0 + 0.05, front + 0.004, sash), (a1 - 0.05, front + 0.004, sash), (a1 - 0.05, front + 0.004, sash + 0.06),
                          (a0 + 0.05, front + 0.004, sash + 0.06)], shade(body, 0.2)))
    for k in range(2):   # the glass's shine
        u = 0.18 + 0.2 * k
        shapes.append(f.poly([(a0 + u, front + 0.005, 0.95), (a0 + u + 0.06, front + 0.005, 0.95), (a0 + u + 0.22, front + 0.005, 1.45),
                              (a0 + u + 0.16, front + 0.005, 1.45)], mix(GLASS, SHINE, 0.55), False))
    shapes += f.box(a0 + 0.1, b0 + 0.08, 2.1, a1 - 0.1, front - 0.06, 2.42, shade(body, 0.08))
    grille = front - 0.06
    radius = 0.13
    ring = tuple(f.p(w / 2 + radius * math.cos(t), grille + 0.001, fan_z + radius * math.sin(t)) for t in [2 * math.pi * k / 20 for k in range(20)])
    shapes.append(Poly(ring, CASING))
    shapes += [Poly(m.points, m.fill, m.ink) for m in _fan_blades(f, w / 2, grille + 0.002, fan_z, radius * 0.85, 0.4, "#8A93A3")]
    duct = f.p(w / 2, (b0 + front) / 2 - 0.05, 0.0)
    return shapes + [Upright(duct[0], duct[1], f.base + 2.42, f.base + 2.5, 0.09, "#8A93A3")]


# ----- space, workshop and safety objects (DESIGN.md §103, Step 260) -------------------------------------

#: Hazard stripes' yellow and black.
HAZARD_YELLOW = "#F6C945"
HAZARD_BLACK = "#2B2F3A"
#: Seconds of a satellite dish's sweep (there and back), a charging station's fill, a 3D print
#: (growing, then a short hold) and an airlock beacon's flash.
DISH_SWEEP_SECONDS = 12.0
CHARGE_SECONDS = 4.0
PRINT_SECONDS = 8.0
BEACON_SECONDS = 1.2
#: A satellite dish's sweep (its turn in its own frame, degrees: it keeps facing the viewer) and
#: its tilt over the level.
DISH_TURNS = (0.0, 90.0)
DISH_TILT = 58.0


def _face_circle(f: _Frame, a: float, b: float, z: float, radius: float, steps: int = 24) -> list[tuple[float, float, float]]:
    """The points (in the frame) of a circle on the face at ``b`` round (``a``, ``z``): a hatch, a dial."""
    return [(a + radius * math.cos(2 * math.pi * k / steps), b, z + radius * math.sin(2 * math.pi * k / steps)) for k in range(steps)]


def _reading(f: _Frame, a: float, a0: float, a1: float) -> float:
    """``a`` between ``a0`` and ``a1`` on a face to the viewer as read left to right: mirrored
    when the object faces right, so lines of text start at the left (DESIGN.md §103)."""
    return a0 + a1 - a if f.swap else a


def _stripes(f: _Frame, a0: float, a1: float, b: float, z0: float, z1: float, *, side: float | None = None) -> list[Shape]:
    """A band of diagonal hazard stripes on the front face (at ``b``, from ``a0`` to ``a1``) or,
    with ``side``, the right side face at ``a`` = ``side`` (``a0`` .. ``a1`` its ``b`` range)."""
    def at(u: float, z: float) -> tuple[float, float, float]:
        return (side, u, z) if side is not None else (u, b, z)

    shade_of = f.side if side is not None else f.front
    shapes: list[Shape] = [f.poly([at(a0, z0), at(a1, z0), at(a1, z1), at(a0, z1)], shade_of(HAZARD_YELLOW))]
    slant, step = (z1 - z0) * 0.9, 0.16
    u = a0 - slant
    while u < a1:
        corners = [(u, z0), (u + step / 2, z0), (u + step / 2 + slant, z1), (u + slant, z1)]
        clipped = [(min(max(c, a0), a1), z) for c, z in corners]
        if max(c for c, _ in clipped) - min(c for c, _ in clipped) > 1e-3:
            shapes.append(f.poly([at(c, z) for c, z in clipped], shade_of(HAZARD_BLACK), False))
        u += step
    return shapes


def _telescope(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A telescope on a tripod: three legs to a mount, its tube in the main colour pointing up
    and away with a band in the detail colour, a dew shield, a finder scope and an eyepiece."""
    cx, cy = f.width / 2, f.depth / 2
    turn, tilt, centre = math.radians(-45.0), math.radians(36.0), 1.22
    da, db = math.cos(turn) * math.cos(tilt), math.sin(turn) * math.cos(tilt)

    def along(s: float, lift: float = 0.0) -> Point3:
        return f.p(cx + s * da, cy + s * db, centre + s * math.sin(tilt) + lift)

    mount = f.p(cx, cy, 1.1)
    legs = [_ribbon(mount, f.p(a, b, 0.0), 0.022, METAL) for a, b in ((cx - 0.34, cy - 0.3), (cx + 0.36, cy - 0.12), (cx - 0.1, cy + 0.38))]
    shapes: list[Shape] = [*legs[:2], *f.box(cx - 0.07, cy - 0.07, 1.04, cx + 0.07, cy + 0.07, 1.16, CASING)]
    shapes.append(_ribbon(along(-0.52), along(0.62), 0.075, look.main))
    shapes.append(_ribbon(along(0.62), along(0.9), 0.092, shade(look.main, 0.08)))   # the dew shield
    shapes.append(_round(along(0.9), 0.05, mix(GLASS, "#3B6FB6", 0.35)))
    shapes.append(_ribbon(along(0.06), along(0.2), 0.082, look.detail))
    shapes.append(_ribbon(along(-0.2, 0.13), along(0.22, 0.13), 0.025, shade(look.main, 0.15)))   # the finder scope
    eye = along(-0.5)
    shapes += [_ribbon(eye, _screen(eye, -0.02, 0.1), 0.026, CASING), _round(_screen(eye, -0.02, 0.1), 0.03, shade(CASING, 0.2))]
    return shapes + [legs[2]]


def _dish_parts(f: _Frame, look: ObjectLook, turn_degrees: float, on: bool) -> list[Poly]:
    """A satellite dish turned ``turn_degrees`` in its frame and tilted up: its rim, its bowl, the
    struts and the feed at its focus (lit in the detail colour when ``on``)."""
    cx, cy, cz = f.width / 2, f.depth / 2, 1.5
    t, e = math.radians(turn_degrees), math.radians(DISH_TILT)
    d = (math.cos(t) * math.cos(e), math.sin(t) * math.cos(e), math.sin(e))
    u = (-math.sin(t), math.cos(t), 0.0)
    v = (-math.cos(t) * math.sin(e), -math.sin(t) * math.sin(e), math.cos(e))

    def at(radius: float, angle: float, forward: float) -> Point3:
        c, s = math.cos(angle), math.sin(angle)
        return f.p(*(cx_ + radius * (c * uu + s * vv) + forward * dd for cx_, uu, vv, dd in zip((cx, cy, cz), u, v, d)))

    steps = [2 * math.pi * k / 24 for k in range(24)]
    shell = Poly(tuple(at(0.44, s, -0.1) for s in steps), shade(look.main, 0.35))   # its back, giving it depth
    rim = Poly(tuple(at(0.46, s, 0.0) for s in steps), look.main)
    bowl = Poly(tuple(at(0.36, s, -0.05) for s in steps), shade(look.main, 0.12), False)
    hub = Poly(tuple(at(0.08, s, -0.07) for s in steps[::2]), shade(look.main, 0.3), False)
    focus = at(0.0, 0.0, 0.42)
    struts = [_ribbon(at(0.42, s, 0.0), focus, 0.012, METAL) for s in (math.pi / 2, math.pi * 7 / 6, math.pi * 11 / 6)]
    feed = _round(focus, 0.04, look.detail if on else LED_OFF, True, on)
    return [shell, rim, bowl, hub, *struts, feed]


def _satellite_dish(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A satellite dish on a plinth: a post, a yoke and a tilted dish in the main colour with a
    feed on struts (its light lit in the detail colour when on; the stage turns the dish slowly
    from side to side, :func:`object_motion`)."""
    cx, cy = f.width / 2, f.depth / 2
    shapes = f.box(0.22, 0.22, 0.0, f.width - 0.22, f.depth - 0.22, 0.3, shade(look.main, 0.2))
    shapes.append(_indicator(f, cx - 0.1, cx + 0.1, f.depth - 0.219, 0.12, 0.18, DISPLAY_GREEN, state.on))
    x, y = f.p(cx, cy, 0.0)[:2]
    shapes += [Upright(x, y, f.base + 0.3, f.base + 1.4, 0.06, METAL), Upright(x, y, f.base + 1.36, f.base + 1.48, 0.12, CASING)]
    if look.moving and state.on:
        return shapes
    return shapes + list(_dish_parts(f, look, sum(DISH_TURNS) / 2, state.on))


def _battery(f: _Frame) -> tuple[float, float, float, float, float]:
    """A charging station's battery gauge on its front: a from, a to, b, its bottom and top."""
    cx = f.width / 2
    return cx - 0.13, cx + 0.13, 0.681, 1.0, 1.42


def _charge_bars(f: _Frame, look: ObjectLook, lit: int, blink: float = 1.0) -> list[Motion]:
    """A charging station's four bars, the lowest ``lit`` of them lit (the next at ``blink``)."""
    a0, a1, b, z0, z1 = _battery(f)
    step = (z1 - z0 - 0.04) / 4
    bars = []
    for k in range(4):
        zz = z0 + 0.03 + k * step
        points = tuple(f.p(a, b + 0.002, z) for a, z in ((a0 + 0.035, zz), (a1 - 0.035, zz), (a1 - 0.035, zz + step - 0.025), (a0 + 0.035, zz + step - 0.025)))
        opacity = 1.0 if k < lit else blink if k == lit else 0.0
        bars.append(Motion(points, look.detail, opacity, False, True))
    return bars


def _charging_station(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A charging post: a slim body in the main colour on a base, a battery gauge of four bars
    on its front (lit in the detail colour when on; the stage fills them over and over), a
    lightning mark, and a cable hanging in a loop to a plug in a holster on its side."""
    w, d = f.width, f.depth
    a0, a1, b0, b1 = 0.3, w - 0.3, 0.32, 0.68
    shapes = f.box(0.22, 0.24, 0.0, w - 0.22, d - 0.2, 0.1, shade(look.main, 0.3))
    shapes += f.box(a0, b0, 0.1, a1, b1, 1.72, look.main)
    shapes += f.box(a0 - 0.03, b0 - 0.03, 1.72, a1 + 0.03, b1 + 0.03, 1.8, CASING)
    g0, g1, b, z0, z1 = _battery(f)
    shapes.append(f.poly([(a0 + 0.05, b1 + 0.001, 0.9), (a1 - 0.05, b1 + 0.001, 0.9), (a1 - 0.05, b1 + 0.001, 1.6), (a0 + 0.05, b1 + 0.001, 1.6)], CASING))
    shapes.append(f.poly([(g0, b, z0), (g1, b, z0), (g1, b, z1), (g0, b, z1)], "#11151C", False))
    shapes.append(f.poly([(g0 + 0.07, b, z1), (g1 - 0.07, b, z1), (g1 - 0.07, b, z1 + 0.05), (g0 + 0.07, b, z1 + 0.05)], "#11151C", False))
    if not (look.moving and state.on):
        shapes += [Poly(m.points, m.fill if state.on else LED_OFF, False, state.on) for m in _charge_bars(f, look, 4)]
    cx = w / 2
    bolt = [(cx + 0.02, 1.56), (cx - 0.05, 1.48), (cx, 1.48), (cx - 0.03, 1.43), (cx + 0.05, 1.51), (cx, 1.51)]
    shapes.append(f.poly([(a, b, z) for a, z in bolt], LIT_GLASS if state.on else "#6A7080", False, state.on))
    shapes += f.box(a1, 0.42, 0.95, a1 + 0.07, 0.58, 1.2, CASING)   # the holster and the plug in it
    shapes += f.box(a1 + 0.01, 0.46, 1.2, a1 + 0.06, 0.54, 1.28, "#8A93A3")
    cable = [(a1 + 0.035 + 0.06 * math.sin(math.pi * s), 0.5 + 0.12 * s, 0.95 - 0.5 * s - 0.45 * math.sin(math.pi * s)) for s in [k / 12 for k in range(13)]]
    return shapes + [Line(tuple(f.p(*q) for q in cable), CASING, 2.2)]


def _crate(f: _Frame, look: ObjectLook, a0: float, b0: float, z0: float, a1: float, b1: float, z1: float) -> list[Shape]:
    """A crate in the main colour: hazard stripes round its top on its two faces to the viewer,
    darker corner posts and a stencilled mark."""
    shapes = f.box(a0, b0, z0, a1, b1, z1, look.main)
    band0, band1 = z1 - 0.2, z1 - 0.07
    shapes += _stripes(f, a0 + 0.06, a1 - 0.06, b1 + 0.001, band0, band1)
    shapes += _stripes(f, b0 + 0.06, b1 - 0.06, 0.0, band0, band1, side=a1 + 0.001)
    edge = shade(look.main, 0.3)
    for a in (a0, a1 - 0.05):
        shapes.append(f.poly([(a, b1 + 0.002, z0), (a + 0.05, b1 + 0.002, z0), (a + 0.05, b1 + 0.002, z1), (a, b1 + 0.002, z1)], f.front(edge), False))
    shapes.append(f.poly([(a1 + 0.002, b0, z0), (a1 + 0.002, b0 + 0.05, z0), (a1 + 0.002, b0 + 0.05, z1), (a1 + 0.002, b0, z1)], f.side(edge), False))
    mid = (a0 + a1) / 2
    shapes.append(f.poly([(mid - 0.12, b1 + 0.002, z0 + 0.12), (mid + 0.12, b1 + 0.002, z0 + 0.12), (mid + 0.12, b1 + 0.002, band0 - 0.08),
                          (mid - 0.12, b1 + 0.002, band0 - 0.08)], f.front(look.detail), False))
    shapes.append(Line((f.p(a0 + 0.04, (b0 + b1) / 2, z1 + 0.001), f.p(a1 - 0.04, (b0 + b1) / 2, z1 + 0.001)), edge, 0.8))
    return shapes


def _crate_stack(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A big crate with a smaller one on top, each with hazard stripes (crates of supplies)."""
    w, d = f.width, f.depth
    return _crate(f, look, 0.08, 0.1, 0.0, w - 0.08, d - 0.1, 0.78) + _crate(f, look, 0.18, 0.16, 0.78, w - 0.3, d - 0.3, 1.32)


def _beacon(f: _Frame) -> Point3:
    """An airlock's warning beacon over its hatch (world point)."""
    return f.p(f.width / 2, 0.82, 2.27)


def _airlock(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A round airlock hatch in a thick bulkhead in the main colour, hazard stripes along its foot
    and a warning beacon over it (lit in the detail colour when on; the stage flashes it). Closed:
    a door with bolts and a wheel; open: the door slid into the wall, a dark tunnel behind (its
    floor lights lit when on)."""
    w = f.width
    b0, b1, h = 0.3, 0.75, 2.5
    cx, cz, r = w / 2, 1.12, min(0.78, w * 0.39)
    shapes = f.box(0.05, b0, 0.0, w - 0.05, b1, h, look.main)
    shapes += _stripes(f, 0.12, w - 0.12, b1 + 0.001, 0.04, 0.2)
    shapes.append(f.poly(_face_circle(f, cx, b1 + 0.002, cz, r + 0.1), f.front(shade(look.main, 0.3))))
    face = b1 + 0.003
    if state.open:
        shapes.append(f.poly(_face_circle(f, cx, face, cz, r), DOORWAY))
        shapes.append(f.poly(_face_circle(f, cx, face + 0.001, cz, r * 0.62), mix(DOORWAY, look.main, 0.18), False))
        shapes.append(_indicator(f, cx - r * 0.4, cx + r * 0.4, face + 0.002, cz - r * 0.55, cz - r * 0.48, look.detail, state.on))
        edge = [(cx + r * math.cos(t), face + 0.002, cz + r * math.sin(t)) for t in [-math.pi / 2 + math.pi * k / 12 for k in range(13)]]
        shapes.append(f.poly(edge + [(cx + r * 0.86 * math.cos(t), face + 0.002, cz + r * math.sin(t)) for t in
                                     [math.pi / 2 - math.pi * k / 12 for k in range(13)]], f.front(mix(look.main, SHINE, 0.15))))
    else:
        door = f.front(mix(look.main, SHINE, 0.15))
        shapes.append(f.poly(_face_circle(f, cx, face, cz, r), door))
        shapes.append(Line(tuple(f.p(*q) for q in [*_face_circle(f, cx, face + 0.001, cz, r * 0.8, 28), _face_circle(f, cx, face + 0.001, cz, r * 0.8, 28)[0]]),
                           shade(door, 0.3), 1.0))
        for k in range(8):
            t = 2 * math.pi * k / 8 + math.pi / 8
            shapes.append(Disc(f.p(cx + r * 0.9 * math.cos(t), face + 0.002, cz + r * 0.9 * math.sin(t)), 0.025, shade(door, 0.35), False, holds_snow=False))
        wheel = _face_circle(f, cx, face + 0.002, cz, r * 0.3, 20)
        shapes.append(Line(tuple(f.p(*q) for q in [*wheel, wheel[0]]), CASING, 2.4))
        for k in range(3):
            t = math.pi / 6 + 2 * math.pi * k / 3
            shapes.append(Line((f.p(cx, face + 0.002, cz), f.p(cx + r * 0.3 * math.cos(t), face + 0.002, cz + r * 0.3 * math.sin(t))), CASING, 1.8))
        shapes.append(_round(f.p(cx, face + 0.003, cz), 0.04, CASING))
    shapes += f.box(cx - 0.12, b1, 2.15, cx + 0.12, b1 + 0.1, 2.22, CASING)
    beacon = _beacon(f)
    shapes.append(_round(beacon, 0.07, mix(look.detail, SHINE, 0.25) if state.on else shade(look.detail, 0.5), True, state.on))
    return shapes


def _printer_box(f: _Frame) -> tuple[float, float, float, float, float, float]:
    """A 3D printer's frame: a from, a to, b at its back and front, its bed's height and its top."""
    return 0.2, f.width - 0.2, 0.28, f.depth - 0.14, 0.99, 1.68


def _print_parts(f: _Frame, look: ObjectLook, share: float, now: float, on: bool) -> list[Poly]:
    """A 3D printer's print ``share`` grown (a vase in the detail colour, its newest layer bright
    while ``on``), the gantry at its top and the print head over it."""
    a0, a1, b0, b1, bed, top = _printer_box(f)
    ca, cb = (a0 + a1) / 2, (b0 + b1) / 2
    base = f.p(ca, cb, bed)
    full = 0.42
    height = max(full * share, 0.004)
    steps = 6
    left = [(-(0.07 + 0.045 * math.sin(math.pi * (height * k / steps) / full)), height * k / steps * ISO_RISE) for k in range(steps + 1)]
    outline = left + [(-du, dv) for du, dv in reversed(left)]
    vase = _profile(base, outline, look.detail)
    rim = left[-1]
    layer = _profile(base, [(rim[0], rim[1] - 0.025), (-rim[0], rim[1] - 0.025), (-rim[0], rim[1]), (rim[0], rim[1])],
                     mix(look.detail, SHINE, 0.55) if on else shade(look.detail, 0.15), False, on)
    z = bed + height + 0.04
    sweep = 0.12 * math.sin(2 * math.pi * now * 0.9) if on else 0.0
    head_a = ca + sweep
    gantry = f.box(a0, cb - 0.03, z + 0.05, a1, cb + 0.03, z + 0.09, CASING)
    head = f.box(head_a - 0.07, cb - 0.07, z + 0.02, head_a + 0.07, cb + 0.07, z + 0.15, "#8A93A3")
    nozzle = _round(f.p(head_a, cb + 0.07, z + 0.01), 0.022, "#FF9A3D" if on else CASING, False, on)
    return [vase, layer, *(s for s in gantry + head if isinstance(s, Poly)), nozzle]


def _printer_3d(f: _Frame, look: ObjectLook, state: ObjectState) -> list[Shape]:
    """A 3D printer on a bench cabinet: an open frame in the main colour round a bed, a print (a
    vase in the detail colour), the gantry and head over it, a spool of filament on top and a
    display (green when on; the stage grows the print layer by layer while it works)."""
    a0, a1, b0, b1, bed, top = _printer_box(f)
    shapes = _cabinet(f)
    shapes += f.box(a0, b0, 0.8, a1, b1, 0.95, look.main)
    shapes.append(_indicator(f, a0 + 0.06, a0 + 0.26, b1 + 0.001, 0.84, 0.91, DISPLAY_GREEN, state.on))
    post = 0.05
    for a, b in ((a0, b0), (a1 - post, b0)):
        shapes += f.box(a, b, 0.95, a + post, b + post, top, CASING)
    shapes += f.box(a0, b0, top - 0.05, a1, b0 + post, top, look.main)
    shapes += f.box(a0 + 0.04, b0 + 0.04, 0.95, a1 - 0.04, b1 - 0.04, bed, METAL)
    if not (look.moving and state.on):
        shapes += list(_print_parts(f, look, 0.55 if state.on else 1.0, 0.0, state.on))
    for a, b in ((a0, b1 - post), (a1 - post, b1 - post)):
        shapes += f.box(a, b, 0.95, a + post, b + post, top, CASING)
    shapes += f.box(a0, b0, top - 0.05, a0 + post, b1, top, look.main) + f.box(a1 - post, b0, top - 0.05, a1, b1, top, look.main)
    shapes += f.box(a0, b1 - post, top - 0.05, a1, b1, top, look.main)
    spool = f.p((a0 + a1) / 2, (b0 + b1) / 2, top)
    shapes += [Upright(spool[0], spool[1], spool[2], spool[2] + 0.1, 0.16, look.detail), Disc((spool[0], spool[1], spool[2] + 0.101), 0.05, CASING, False)]
    return shapes


def _hazard_sign(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A warning sign on a stand facing the front: a yellow (main colour) triangle with a black
    (detail) border and a biohazard or radiation symbol, or (``authorised``) a white board with a
    red band and lines of text."""
    kind = f.item.features[0] if f.item.features else "biohazard"
    cx, b = f.width / 2, f.depth / 2
    ink = look.detail
    if kind == "authorised":
        a0, a1, z0, z1 = cx - 0.38, cx + 0.38, 0.95, 1.62
        shapes: list[Shape] = []
        for a in (a0 + 0.08, a1 - 0.12):
            shapes += f.box(a, b - 0.06, 0.0, a + 0.04, b - 0.02, z0 + 0.1, METAL)
        board = "#F4F6FA" if f.item.color is None else look.main
        shapes.append(f.poly([(a0, b, z0), (a1, b, z0), (a1, b, z1), (a0, b, z1)], f.front(board)))
        shapes.append(f.poly([(a0 + 0.04, b + 0.001, z1 - 0.2), (a1 - 0.04, b + 0.001, z1 - 0.2), (a1 - 0.04, b + 0.001, z1 - 0.04),
                              (a0 + 0.04, b + 0.001, z1 - 0.04)], f.front("#E2574C"), False))
        lines = ((z1 - 0.12, 0.62, SHINE, 2.2), (z0 + 0.36, 0.7, ink, 1.6), (z0 + 0.24, 0.5, ink, 1.6), (z0 + 0.12, 0.6, ink, 1.6))
        for z, share, color, width in lines:
            start = a0 + 0.1
            end = start + (a1 - a0 - 0.2) * share
            shapes.append(Line((f.p(_reading(f, start, a0, a1), b + 0.002, z), f.p(_reading(f, end, a0, a1), b + 0.002, z)), color, width))
        return shapes
    x, y = f.p(cx, b, 0.0)[:2]
    shapes = [Disc(f.p(cx, b, 0.01), 0.18, METAL, True, holds_snow=False), Upright(x, y, f.base, f.base + 1.12, 0.035, METAL)]
    zc, half, height = 1.32, 0.42, 0.72
    z0 = zc - height / 3
    outer = [(cx - half, b + 0.02, z0), (cx + half, b + 0.02, z0), (cx, b + 0.02, z0 + height)]
    shapes.append(f.poly(outer, f.front(ink)))
    inner = [(cx - half * 0.78, b + 0.021, z0 + 0.06), (cx + half * 0.78, b + 0.021, z0 + 0.06), (cx, b + 0.021, z0 + height * 0.8)]
    shapes.append(f.poly(inner, f.front(look.main), False))
    sb = b + 0.022
    if kind == "radiation":
        for k in range(3):
            t = math.radians(30.0 + 120.0 * k)
            wedge = [(cx + r * math.cos(t + d), sb, zc + r * math.sin(t + d)) for r, d in ((0.045, -0.5), (0.15, -0.5), (0.15, -0.17), (0.15, 0.17), (0.15, 0.5),
                                                                                          (0.045, 0.5))]
            shapes.append(f.poly(wedge, f.front(ink), False))
        shapes.append(f.poly(_face_circle(f, cx, sb, zc, 0.03, 12), f.front(ink), False))
        return shapes
    for k in range(3):   # a biohazard: three rings cut by the yellow, round a ring in the middle
        t = math.radians(90.0 + 120.0 * k)
        shapes.append(f.poly(_face_circle(f, cx + 0.065 * math.cos(t), sb, zc + 0.065 * math.sin(t), 0.075, 16), f.front(ink), False))
    for k in range(3):
        t = math.radians(90.0 + 120.0 * k)
        shapes.append(f.poly(_face_circle(f, cx + 0.085 * math.cos(t), sb + 0.001, zc + 0.085 * math.sin(t), 0.05, 16), f.front(look.main), False))
    shapes.append(Line(tuple(f.p(*q) for q in [*_face_circle(f, cx, sb + 0.002, zc, 0.06, 16), _face_circle(f, cx, sb + 0.002, zc, 0.06, 16)[0]]),
                       f.front(ink), 1.4))
    shapes.append(f.poly(_face_circle(f, cx, sb + 0.003, zc, 0.022, 10), f.front(look.main), False))
    return shapes


def _fire_extinguisher(f: _Frame, look: ObjectLook) -> list[Shape]:
    """A fire extinguisher on a little floor stand: a cylinder in the main colour with a white
    label, a valve and lever, and a hose in the detail colour down to its nozzle."""
    x, y = f.p(f.width / 2, f.depth / 2, 0.0)[:2]
    z = f.base
    body = look.main
    shapes: list[Shape] = [Upright(x, y, z, z + 0.05, 0.2, CASING), Upright(x, y, z + 0.05, z + 0.68, 0.13, body),
                           Upright(x, y, z + 0.68, z + 0.74, 0.085, shade(body, 0.08)), Upright(x, y, z + 0.74, z + 0.82, 0.035, METAL)]
    middle = (x, y, z + 0.05)
    shapes.append(_profile(middle, [(-0.075, 0.1), (0.075, 0.1), (0.075, 0.25), (-0.075, 0.25)], "#F4F6FA", False))
    shapes.append(Line((_screen(middle, -0.045, 0.2), _screen(middle, 0.045, 0.2)), "#E2574C", 1.4))
    shapes.append(Line((_screen(middle, -0.045, 0.15), _screen(middle, 0.03, 0.15)), CASING, 1.0))
    shapes.append(_profile(middle, [(-0.07, 0.27), (-0.05, 0.27), (-0.05, 0.37), (-0.07, 0.37)], mix(body, SHINE, 0.45), False))
    valve = (x, y, z + 0.8)
    shapes.append(_ribbon(_screen(valve, -0.02, 0.0), _screen(valve, -0.13, 0.05), 0.014, CASING))   # the lever
    hose = [_screen(valve, 0.03, -0.01), _screen(valve, 0.09, -0.04), _screen(valve, 0.12, -0.16), _screen(valve, 0.115, -0.42), _screen(valve, 0.1, -0.55)]
    shapes.append(Line(tuple(hose), look.detail, 2.4))
    return shapes + [_ribbon(hose[-1], _screen(hose[-1], -0.01, -0.07), 0.018, look.detail)]


#: The objects with moving parts the stage draws over their pictures while they work (DESIGN.md §103).
MOVING_KINDS = ("quantum_core", "robot_arm", "centrifuge", "coffee_machine", "specimen_tank", "chemistry_bench", "distillation_rig", "lab_fridge",
                "fume_hood", "satellite_dish", "charging_station", "airlock", "printer_3d", "fireplace", "stove", "tv", "traffic_light", "fountain",
                "campfire", "pond", "beehive", "desk_with_pc", "water_cooler", "printer", "globe", "treasure_chest", "cauldron", "giant_crystal",
                "torch_sconce")
_LAB_MOVING = frozenset({"specimen_tank", "chemistry_bench", "distillation_rig", "lab_fridge", "fume_hood"})
_WORKSHOP_MOVING = frozenset({"satellite_dish", "charging_station", "airlock", "printer_3d"})
#: The objects that work while open too (a lab fridge's cold mist, a treasure chest's sparkles).
OPEN_WORKING = frozenset({"lab_fridge", "treasure_chest"})


def object_working(kind: str, state: ObjectState) -> bool:
    """Whether an object of ``kind`` in ``state`` works (its moving parts move): there and on;
    a lab fridge or a treasure chest also while open."""
    return state.shown and (state.on or (kind in OPEN_WORKING and state.open))


def _bubble(point: Point3, radius: float, fill: str, opacity: float) -> Motion:
    return Motion(_round(point, radius, fill).points, fill, opacity, False, True)


def _rising(now: float, k: int, count: int, seconds: float) -> float:
    """How far (0..1) the ``k``-th of ``count`` bubbles or puffs is along its way at ``now``."""
    return (now / seconds + k / count + 0.13 * k) % 1.0


def _fade(rise: float) -> float:
    """A puff's or a bubble's opacity along its way: in quickly, out slowly."""
    return min(1.0, rise * 6.0) * (1.0 - rise) ** 0.6


def _lab_motion(f: _Frame, look: ObjectLook, now: float, state: ObjectState) -> list[Motion]:
    """The moving parts of the Step 259 objects (:func:`object_motion`)."""
    kind = f.item.kind
    parts: list[Motion] = []
    if kind == "specimen_tank":
        x, y, bottom, top, radius = _tank_parts(f)
        pale = mix(look.main, SHINE, 0.7)
        for k in range(7):
            rise = _rising(now, k, 7, BUBBLE_SECONDS)
            sway = (0.5 * ((k * 0.37) % 1.0) - 0.25) * radius + 0.02 * math.sin(2 * math.pi * (rise * 2 + k * 0.3))
            point = _screen((x, y, bottom + 0.1 + (top - bottom - 0.15) * rise), sway, 0.0)
            parts.append(_bubble(point, 0.018 + 0.012 * (k % 3), pale, 0.9 * _fade(rise)))
        return parts
    if kind == "chemistry_bench":
        palette = _bench_palette(look)
        for what, base, size, color in _bench_vessels(f):
            if what not in ("flask", "round"):
                continue
            pale = mix(palette[color], SHINE, 0.6)
            inside = size * 0.3 if what == "flask" else size
            for k in range(3):
                rise = _rising(now, k, 3, 1.3)
                point = _screen(base, (k - 1) * size * 0.12, 0.03 + inside * 0.9 * rise + (size if what == "round" else 0.0) * 0.1)
                parts.append(_bubble(point, 0.012 + 0.006 * k, pale, _fade(rise)))
            top = size + 0.03 if what == "flask" else 2 * size + 0.2
            rise = _rising(now, 0, 1, STEAM_SECONDS * 1.2)
            sway = 0.03 * math.sin(2 * math.pi * rise * 1.5)
            parts.append(_bubble(_screen(base, sway, top + 0.5 * rise), 0.03 + 0.06 * rise, mix(palette[color], SHINE, 0.75), 0.55 * _fade(rise)))
        return parts
    if kind == "distillation_rig":
        boil, _, end, catch = _rig_parts(f)
        burner = f.p(0.18, 0.6, 0.8)
        flicker = 0.5 + 0.5 * math.sin(2 * math.pi * now * 3.1) * math.sin(2 * math.pi * now * 1.7)
        flame = _screen(burner, 0.0, 0.07)
        parts += [Motion(tuple(_screen(flame, du, dv) for du, dv in ((-0.04, 0.0), (0.04, 0.0), (0.012 * flicker, 0.09 + 0.04 * flicker))), "#FF9A3D", 0.95, False, True),
                  Motion(tuple(_screen(flame, du, dv) for du, dv in ((-0.02, 0.0), (0.02, 0.0), (0.0, 0.045 + 0.02 * flicker))), "#7FD0FF", 0.95, False, True)]
        pale = mix(look.main, SHINE, 0.6)
        for k in range(3):
            rise = _rising(now, k, 3, 1.0)
            parts.append(_bubble(_screen(boil, (k - 1) * 0.05, 0.0 + 0.16 * rise), 0.012 + 0.005 * k, pale, _fade(rise)))
        drop = mix(look.detail, SHINE, 0.3)
        fall = _screen(catch, 0.0, 0.44)
        for k in range(2):
            share = (now / DRIP_SECONDS + k / 2) % 1.0
            grow, falling = min(share / 0.6, 1.0), max(share - 0.6, 0.0) / 0.4
            point = (end[0] + (fall[0] - end[0]) * falling, end[1] + (fall[1] - end[1]) * falling, end[2] + (fall[2] - end[2]) * falling)
            parts.append(_bubble(_screen(point, 0.0, -0.02), 0.012 + 0.01 * grow, drop, 1.0 if share < 0.98 else 0.0))
        return parts
    if kind == "lab_fridge":
        a0, a1, b0, b1, h = _fridge_box(f)
        for k in range(5):
            rise = _rising(now, k, 5, MIST_SECONDS)
            if state.open:   # it pours from the opening and down to the floor, out towards the viewer
                point = f.p(a0 + (a1 - a0) * (0.2 + 0.15 * k), b1 + 0.05 + 0.5 * rise, max(0.1, 0.9 + 0.25 * (k % 3) - 1.0 * rise))
            else:   # it seeps from under the door
                point = f.p(a0 + (a1 - a0) * (0.15 + 0.18 * k), b1 + 0.05 + 0.35 * rise, 0.12 + 0.05 * rise)
            parts.append(_bubble(point, 0.06 + 0.1 * rise, MIST, (0.55 if state.open else 0.4) * _fade(rise)))
        return parts
    if kind == "fume_hood":
        a0, a1, front, fan_z = _hood_parts(f)
        w = f.width
        grille = front - 0.06
        parts.append(Motion(tuple(f.p(w / 2 + 0.115 * math.cos(t), grille + 0.002, fan_z + 0.115 * math.sin(t)) for t in [2 * math.pi * k / 20 for k in range(20)]),
                            CASING, ink=False))
        parts += _fan_blades(f, w / 2, grille + 0.003, fan_z, 0.11, -2 * math.pi * now / FAN_SECONDS, "#C9CED6")
        mouth = _screen(f.p(0.35 * w, front, 0.92), 0.0, 0.38)
        vapour = mix(look.detail, SHINE, 0.4)
        for k in range(3):
            rise = _rising(now, k, 3, MIST_SECONDS)
            sway = 0.03 * math.sin(2 * math.pi * (rise + k * 0.4))
            parts.append(_bubble(_screen(mouth, sway + 0.06 * rise, 0.3 * rise), 0.03 + 0.05 * rise, vapour, 0.5 * _fade(rise)))
        return parts
    return parts


def _workshop_motion(f: _Frame, look: ObjectLook, now: float) -> list[Motion]:
    """The moving parts of the Step 260 objects (:func:`object_motion`)."""
    kind = f.item.kind
    if kind == "satellite_dish":
        swing = 0.5 - 0.5 * math.cos(2 * math.pi * now / DISH_SWEEP_SECONDS)
        turn = DISH_TURNS[0] + (DISH_TURNS[1] - DISH_TURNS[0]) * swing
        return [Motion(p.points, p.fill, 1.0, bool(p.ink), p.glow) for p in _dish_parts(f, look, turn, True)]
    if kind == "charging_station":
        share = (now % CHARGE_SECONDS) / CHARGE_SECONDS
        lit = min(int(share * 5), 4)
        return _charge_bars(f, look, lit, 0.5 + 0.5 * math.sin(2 * math.pi * now * 1.5) ** 2)
    if kind == "airlock":
        beat = 0.5 - 0.5 * math.cos(2 * math.pi * now / BEACON_SECONDS)
        beacon = _beacon(f)
        return [Motion(_round(beacon, 0.2 + 0.06 * beat, SHINE).points, look.detail, 0.15 + 0.4 * beat, False, True),
                Motion(_round(beacon, 0.06, SHINE).points, mix(look.detail, SHINE, 0.6), 0.3 + 0.7 * beat, False, True)]
    if kind == "printer_3d":
        cycle = (now % PRINT_SECONDS) / PRINT_SECONDS
        share = min(cycle / 0.85, 1.0)
        layers = 24   # it grows layer by layer, not smoothly
        return [Motion(p.points, p.fill, 1.0, bool(p.ink), p.glow) for p in _print_parts(f, look, math.floor(share * layers) / layers, now, True)]
    return []


def object_motion(item: IsoObject, look: ObjectLook, base: float, now: float, state: ObjectState | None = None) -> list[Motion]:
    """The moving parts of a working ``item`` (one of :data:`MOVING_KINDS`) at scene time
    ``now``, drawn over its picture: a quantum core's pulsing halo, its bright core and sparks
    round its ring; a robot arm's arm swinging between its two poses; a centrifuge's spinning
    rotor (over a dark window); a coffee machine's steam rising from the mug; bubbles rising in
    a specimen tank and a chemistry bench's flasks (with steam); a distillation rig's flame,
    boiling and drips; a lab fridge's cold mist (``state``: from the opening while open); a fume
    hood's fan and vapour; a satellite dish turning, a charging station's bars filling, an
    airlock's flashing beacon and a 3D print growing layer by layer under its moving head; a
    fireplace's flames, a stove's steam, a TV's picture, a traffic light's lamps, a fountain's
    water, a campfire's flames and sparks, a pond's ripples, a hive's bees, a line typed on a
    computer, a water cooler's bubbles, a printed sheet, a globe's turning land, an open chest's
    sparkles, a cauldron's bubbles, a crystal's pulse and a torch's flame (§104). The same
    number of parts at any time (those not seen have opacity 0)."""
    f = _Frame(item, base)
    if item.kind in MORE_MODULES:
        return _more(item.kind).motion(f, look, now)
    if item.kind in _WORKSHOP_MOVING:
        return _workshop_motion(f, look, now)
    if item.kind in _LAB_MOVING:
        return _lab_motion(f, look, now, state or ObjectState(on=True))
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
        parts = []
        for k in range(STEAM_PUFFS):
            rise = (now / STEAM_SECONDS + k / STEAM_PUFFS) % 1.0
            sway = 0.035 * math.sin(2 * math.pi * (rise + k * 0.37))
            top = f.p(MUG_SPOT[0] * f.width, MUG_SPOT[1] + 0.35 * rise, MUG_RIM)   # it drifts out from under the head
            centre = _screen(top, sway, 0.05 + 0.45 * rise)
            opacity = 0.9 * min(1.0, rise * 5.0) * (1.0 - rise) ** 0.7
            parts.append(Motion(_round(centre, 0.04 + 0.07 * rise, "#FFFFFF").points, "#FFFFFF", opacity * 0.8, False, True))   # pale at night too
        return parts
    return []


_DRAWINGS: dict[str, Callable[[_Frame, ObjectLook], list[Shape]]] = {
    "tree": _tree, "pine": _pine, "bush": _bush, "rock": _rock, "bench": _bench, "well": _well, "sign": _sign, "bridge": _bridge, "table": _table, "chair": _chair, "bed": _bed,
    "shelf": _shelf, "sofa": _sofa, "plant": _plant, "rug": _rug,
    "console": _console, "server_rack": _server_rack, "projector_pad": _projector_pad, "whiteboard": _whiteboard,
    "flower_arch": _flower_arch, "chess_table": _chess_table,
    "microscope": _microscope, "lab_stool": _lab_stool, "wall_clock": _wall_clock, "terrarium": _terrarium,
    "telescope": _telescope, "crate_stack": _crate_stack, "hazard_sign": _hazard_sign, "fire_extinguisher": _fire_extinguisher,
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
                                  "plant": 0.32, "flowers": 0.36, "chair": 0.42, "lab_stool": 0.26, "quantum_core": 0.42, "robot_arm": 0.36,
                                  "terrarium": 0.3, "specimen_tank": 0.42, "telescope": 0.4, "hazard_sign": 0.22, "fire_extinguisher": 0.24,
                                  "floor_lamp": 0.26, "street_lamp": 0.26, "traffic_light": 0.22, "mailbox": 0.3, "bicycle": 0.36,
                                  "stump": 0.4, "scarecrow": 0.3, "beehive": 0.4, "wheelbarrow": 0.4, "water_cooler": 0.32, "globe": 0.36,
                                  "cauldron": 0.42, "giant_crystal": 0.48, "signpost": 0.24}
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
    "grow_rack": _grow_rack, "specimen_tank": _specimen_tank, "chemistry_bench": _chemistry_bench, "distillation_rig": _distillation_rig,
    "lab_fridge": _lab_fridge, "fume_hood": _fume_hood, "satellite_dish": _satellite_dish, "charging_station": _charging_station,
    "airlock": _airlock, "printer_3d": _printer_3d,
}
#: The kinds drawn by another module of :mod:`vidgen.cartoon` (DESIGN.md §104): its name. Each
#: such module has ``DRAWINGS`` (by frame, look and state) and ``motion(frame, look, now)``; it
#: is imported when first needed (it builds on this module's helpers).
MORE_MODULES: dict[str, str] = {
    **{kind: "iso_home" for kind in ("fireplace", "kitchen_counter", "stove", "sink", "bookshelf_tall", "armchair", "floor_lamp", "tv", "piano")},
    **{kind: "iso_shop" for kind in ("bathtub", "wardrobe", "crib", "cafe_table", "counter", "cash_register", "display_case", "market_stall",
                                     "vending_machine")},
    **{kind: "iso_town" for kind in ("street_lamp", "traffic_light", "bus_stop", "mailbox", "fountain", "phone_booth", "car", "bicycle", "newsstand")},
    **{kind: "iso_nature" for kind in ("campfire", "tent", "log", "stump", "mushroom_ring", "pond", "scarecrow", "beehive")},
    **{kind: "iso_school" for kind in ("vegetable_patch", "wheelbarrow", "hay_bale", "school_desk", "desk_with_pc", "water_cooler", "printer",
                                       "globe", "trophy_shelf")},
    **{kind: "iso_fantasy" for kind in ("treasure_chest", "cauldron", "giant_crystal", "throne", "torch_sconce", "signpost", "archway", "statue")},
}
#: The objects whose light falls on the characters near them while on, like a lamp's (§89.13).
LAMPLIGHT_KINDS = frozenset({"lamp", "floor_lamp", "fireplace", "street_lamp", "phone_booth", "campfire", "cauldron", "torch_sconce"})


def _more(kind: str) -> ModuleType:
    """The module that draws ``kind`` (one of :data:`MORE_MODULES`)."""
    return importlib.import_module(f"vidgen.cartoon.{MORE_MODULES[kind]}")


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
    if item.kind in MORE_MODULES:
        return shadow + _more(item.kind).DRAWINGS[item.kind](frame, look, state)
    return shadow + _DRAWINGS[item.kind](frame, look)


def object_box(item: IsoObject, base: float) -> Box3:
    """The box ``item`` stands in, for the draw order: its footprint, up to its height (an object
    hanging on a wall: a thin slab on the wall's face)."""
    if item.kind in WALL_KINDS:
        return _wall_box(item, base)
    return Box3(item.column, item.row, base, item.column + item.width, item.row + item.depth, base + item.height)


__all__ = ["BED_KINDS", "DOORWAY", "LAMPLIGHT_KINDS", "LIGHT_POOL", "LIT_GLASS", "LIT_OBJECTS", "MORE_MODULES", "MOVING_KINDS", "OBJECT_COLORS",
           "OPEN_WORKING", "Motion", "ObjectLook",
           "clock_hands", "light_pool", "object_box", "object_lights", "object_motion", "object_shapes", "object_working", "tower_screen"]
