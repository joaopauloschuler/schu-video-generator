"""Placing a cell world's structures (DESIGN.md §95.3, §95.9): the cell and its envelope (a
plant's wall with plasmodesmata, a bacterium's periplasm or wall and capsule), each structure
with its fine structure (the nuclear envelope opened by pores, ER sheets joined to it and a
smooth-ER network joined to them, Golgi cisternae with rims and buds, cristae, thylakoids,
intraluminal vesicles), the generated things (pores, bound ribosomes, vesicles at the Golgi and
at ER exit sites) and the tissue around. Used by :func:`~.build.build_cell_world`. No manim."""

from __future__ import annotations

import math
import random

from .catalog import (
    BILAYER, CAPSULE, CELL_SIZES, CELL_WALL, CHLOROPLAST_GAP, COATS, COMPARTMENTS, ER_LUMEN, ER_RIBOSOMES_PER_UM, ER_TUBULE, GOLGI_LUMEN, GOLGI_PERIOD,
    KINDS, MITO_GAP, PERINUCLEAR_GAP, PERIPLASM, PLASMODESMA, PORES_PER_UM, THICK_WALL, Kind,
)
from .geometry import ArcBand, Capsule, Ellipse, Point, RoundedBox, Shape, inside, overlap
from .model import CellSpec, CellWorld, Entry, Neighbour, ObjectSpec, Part, Placed, at_text, fail, instance_words, noun
from .morphology import (
    endosome_tubules, envelope, er_necks, er_network, golgi_buds, golgi_cisterna, inner_mitochondrial, intraluminal_vesicles, rng_for,
    segment, starch_grains, thylakoids, tubule,
)
from .regions import Region
from .units import format_length

#: Room kept between a structure and the plasma membrane, and between two structures (µm).
EDGE_ROOM, STRUCTURE_ROOM = 0.25, 0.2
#: Tries per thing when scattering.
SCATTER_TRIES = 600
#: Most things one world holds (ribosomes along the ER included).
MAX_PLACED = 4000
#: A plant cell's peripheral cytoplasm round its central vacuole (µm), and the share of its
#: length left free beside the vacuole for the nucleus.
PLANT_BAND, PLANT_POCKET = 2.9, 0.36


def cell_shape(kind: str, size: float, aspect: float) -> Shape:
    """The plasma membrane of a cell of ``kind`` (an ellipse, a rounded box, a rod)."""
    short = size / aspect
    if kind == "plant":
        return RoundedBox(0.0, 0.0, size, short, min(1.5, 0.08 * short))
    if kind == "bacterium":
        return Capsule(0.0, 0.0, size, short)
    return Ellipse(0.0, 0.0, size / 2, short / 2)


def grown(shape: Shape, d: float) -> Shape:
    """``shape`` grown outwards by ``d`` µm (its next layer out)."""
    return shape.inset(-d)


class Builder:
    """Places the entries one after another (see :func:`~.build.build_cell_world`)."""

    def __init__(self, spec: CellSpec) -> None:
        self.spec = spec
        default_size, default_aspect, _ = CELL_SIZES[spec.kind]
        self.size = spec.size if spec.size is not None else default_size
        self.aspect = spec.aspect if spec.aspect is not None else default_aspect
        self.cell = cell_shape(spec.kind, self.size, self.aspect)
        self.edge_room = min(EDGE_ROOM, self.size / self.aspect * 0.05)
        self.room = min(STRUCTURE_ROOM, self.edge_room)
        self.placed: list[Placed] = []
        self.entries: list[Entry] = []
        self.envelope, self.membranes, self.channels = self._envelope()

    # ----- the cell -------------------------------------------------------------------------

    def _envelope(self) -> tuple[tuple[tuple[str, Shape], ...], tuple[tuple[str, Shape], ...], tuple[Shape, ...]]:
        spec, cell = self.spec, self.cell
        if spec.kind == "plant":
            wall = grown(cell, spec.wall if spec.wall is not None else CELL_WALL)
            channels = self._plasmodesmata(wall) if spec.plasmodesmata else ()
            return (("cell_wall", wall),), (("plasma_membrane", cell),), channels
        if spec.kind == "bacterium":
            if spec.gram == "negative":
                outer = grown(cell, PERIPLASM)
                layers: list[tuple[str, Shape]] = [("periplasm", outer)]
                membranes = (("bacterial_inner_membrane", cell), ("bacterial_outer_membrane", outer))
            else:
                layers = [("cell_wall", grown(cell, THICK_WALL))]
                membranes = (("plasma_membrane", cell),)
            if spec.capsule:
                layers.append(("capsule", grown(layers[-1][1], CAPSULE)))
            return tuple(layers), membranes, ()
        return (), (("plasma_membrane", cell),), ()

    def _plasmodesmata(self, wall: Shape) -> tuple[Shape, ...]:
        """Plasmodesmata in pit fields (clusters of a few) through the wall and the next cell's
        wall: the cytosol of the two cells joined through each (on the straight sides)."""
        rng = self.rng("plasmodesmata")
        assert isinstance(self.cell, RoundedBox)
        thickness = wall.bounds()[2] - self.cell.bounds()[2]
        hx, hy, r = self.cell._corner()
        out = []
        sides = [((hx + r, 0.0), (1.0, 0.0), hy), ((0.0, hy + r), (0.0, 1.0), hx), ((-hx - r, 0.0), (-1.0, 0.0), hy), ((0.0, -hy - r), (0.0, -1.0), hx)]
        for (sx, sy), (nx, ny), half in sides:
            along = rng.uniform(-0.6, 0.6) * half
            for k in range(3):
                u = along + (k - 1) * 0.3
                p = (sx - ny * u, sy + nx * u)
                mid = (p[0] + nx * thickness, p[1] + ny * thickness)
                out.append(Capsule(mid[0], mid[1], 2 * thickness, PLASMODESMA + BILAYER, math.atan2(ny, nx)))
        return tuple(out)

    def rng(self, *key: object) -> random.Random:
        return random.Random(":".join(str(k) for k in (self.spec.seed, *key)))

    def world(self) -> CellWorld:
        return CellWorld(self.spec.kind, self.cell, tuple(self.placed), tuple(self.entries), (), self.spec.seed,
                         self.envelope, self.membranes, self.channels, self.spec.gram if self.spec.kind == "bacterium" else None)

    def structures(self) -> list[Placed]:
        return [p for p in self.placed if KINDS[p.kind].category == "structure"]

    def nuclei(self) -> list[Placed]:
        return [p for p in self.placed if p.kind == "nucleus"]

    def size_of(self, kind: Kind, spec: ObjectSpec) -> float:
        return spec.size or kind.size_in(self.spec.kind)

    def fits(self, shapes: tuple[Shape, ...], ignore: tuple[str, ...] = (), room: float | None = None) -> str | None:
        """Why ``shapes`` cannot go in the cytosol here (``None``: they can)."""
        room = self.room if room is None else room
        for shape in shapes:
            if not inside(shape, self.cell, self.edge_room if room >= self.room else room):
                return "it reaches the plasma membrane or out of the cell"
        # small things (vesicles) may come closer to others than large ones
        x0, y0, x1, y1 = shapes[0].bounds()
        room = min(room, max(0.02, 0.4 * min(x1 - x0, y1 - y0))) if len(shapes) == 1 else room
        for other in self.structures():
            if other.key in ignore or other.entry in ignore:
                continue
            if any(overlap(s, o, room) for s in shapes for o in other.footprint):
                return f"it overlaps '{other.key}'"
        return None

    def add(self, entry_id: str, spec: ObjectSpec, things: list[Placed], owner: str | None = None) -> None:
        self.placed.extend(things)
        self.entries.append(Entry(entry_id, spec.kind, tuple(t.key for t in things), spec.where, owner))
        if len(self.placed) > MAX_PLACED:
            raise fail(spec, entry_id, f"too many things in one cell (more than {MAX_PLACED}); use a smaller count")

    def random_point(self, rng: random.Random) -> Point:
        x0, y0, x1, y1 = self.cell.bounds()
        return (rng.uniform(x0, x1), rng.uniform(y0, y1))

    # ----- shapes of each kind --------------------------------------------------------------

    def outline_of(self, kind: Kind, key: str, spec: ObjectSpec, center: Point, size: float, width: float, angle: float) -> tuple[Shape, ...]:
        """A structure's footprint alone (cheap: tried at each place while scattering)."""
        shape = self.shape_of(kind, center, size, width, angle)
        if kind.name == "early_endosome":
            assert isinstance(shape, Ellipse)
            return (shape, *endosome_tubules(shape, key))
        if kind.name == "vesicle" and spec.coat not in (None, "none"):
            return (grown(shape, COATS[spec.coat]),)  # type: ignore[index]
        return (shape,)

    @staticmethod
    def shape_of(kind: Kind, center: Point, size: float, width: float, angle: float) -> Shape:
        if kind.shape == "capsule":
            return Capsule(center[0], center[1], size, width, angle)
        if kind.shape == "box":
            return RoundedBox(center[0], center[1], size, width, min(1.6, width * 0.15), angle)
        return Ellipse(center[0], center[1], size / 2, width / 2, angle)

    def body(self, kind: Kind, key: str, spec: ObjectSpec, center: Point, size: float, width: float, angle: float
             ) -> tuple[tuple[Shape, ...], tuple[Part, ...], tuple[tuple[str, object], ...]]:
        """A structure's footprint, its membrane-bounded parts and its drawing options."""
        shape = self.shape_of(kind, center, size, width, angle)
        name = kind.name
        if name == "nucleus":
            outer = shape
            inner = shape.inset(PERINUCLEAR_GAP + BILAYER)
            pores = pore_points(outer, inner) if spec.pores is not False else []   # type: ignore[arg-type]
            region = envelope(outer, inner, pores).plus(inner)                       # type: ignore[arg-type]
            return (shape,), (Part((("outer_nuclear_membrane", region), ("inner_nuclear_membrane", inner)), kind.interior),), (("pores", tuple(pores)),)
        if name == "mitochondrion":
            assert isinstance(shape, Capsule)
            inner = shape.inset(MITO_GAP + BILAYER)
            region = inner_mitochondrial(inner, key)
            return (shape,), (Part((("outer_mitochondrial_membrane", shape), ("inner_mitochondrial_membrane", region)), kind.interior),), ()
        if name == "chloroplast":
            assert isinstance(shape, Ellipse)
            inner = shape.inset(CHLOROPLAST_GAP + BILAYER)
            discs, lamellae = thylakoids(inner, spec.grana or max(2, round(size / 1.1)), key)
            region = Region.of(*discs, *lamellae, origin=shape.center())
            parts = (Part((("outer_envelope_membrane", shape), ("inner_envelope_membrane", inner)), kind.interior),
                     Part((("thylakoid_membrane", region),), ("thylakoid_lumen",)))
            return (shape,), parts, (("discs", tuple(discs)), ("lamellae", tuple(lamellae)), ("starch", tuple(starch_grains(inner, key))))
        if name == "late_endosome":
            assert isinstance(shape, Ellipse)
            ilvs = intraluminal_vesicles(shape.inset(BILAYER), key)
            parts = (Part((("endosomal_membrane", shape),), ("endosome_lumen",)),
                     *(Part((("intraluminal_vesicle_membrane", e),), ("intraluminal_vesicle",)) for e in ilvs))
            return (shape,), parts, ()
        if name == "early_endosome":
            assert isinstance(shape, Ellipse)
            tubules = endosome_tubules(shape, key)
            region = Region.of(shape, *tubules)
            return (shape, *tubules), (Part((("endosomal_membrane", region),), ("endosome_lumen",)),), ()
        if name == "vesicle":
            coat = spec.coat if spec.coat not in (None, "none") else None
            parts = (Part((("vesicle_membrane", shape),), ("vesicle_lumen",)),)
            if coat is None:
                return (shape,), parts, ()
            return (grown(shape, COATS[coat]),), parts, (("coat", coat),)
        if not kind.membranes:
            return (shape,), (), ()
        membranes = [(kind.membranes[0], shape)]
        for membrane in kind.membranes[1:]:
            membranes.append((membrane, membranes[-1][1].inset(BILAYER * 2)))
        return (shape,), (Part(tuple(membranes), kind.interior),), ()

    # ----- placing ----------------------------------------------------------------------------

    def place_round(self, entry_id: str, spec: ObjectSpec, kind: Kind, defaults: list[tuple[Point, float | None] | None]) -> list[Placed]:
        """Structures with a body shape: at ``at``, at the default places, or scattered in the
        cytosol (a nucleolus: in a nucleus)."""
        size = self.size_of(kind, spec)
        width = spec.width or (kind.width if kind.width is not None else size)
        if kind.width is not None and spec.size and not spec.width:
            width = min(width, size)
        if width > size:
            size, width = width, size
        things: list[Placed] = []
        rng = self.rng(entry_id)
        chosen = spec.style or self.spec.style
        style = (("style", chosen),) if chosen != "section" else ()
        for n in range(spec.count):
            key = entry_id if spec.count == 1 else f"{entry_id}#{n + 1}"
            default = defaults[n] if n < len(defaults) else None
            tries = 1 if spec.at is not None else SCATTER_TRIES
            reason = "no room"
            for attempt in range(tries):
                fixed: Point | None = spec.at
                angle_default = None
                if fixed is None and attempt == 0 and default is not None:
                    fixed, angle_default = default          # the typical layout's place first, then scattered
                if fixed is None and kind.name == "chloroplast" and isinstance(self.cell, RoundedBox):
                    fixed, angle_default = self.along_wall(rng, kind, width)   # in the thin cytoplasm along the wall
                if spec.angle is not None:
                    angle = math.radians(spec.angle)
                elif angle_default is not None:
                    angle = angle_default
                elif kind.name == "nucleus":
                    angle = math.radians(10.0)
                elif kind.name in ("vacuole", "nucleoid"):
                    angle = 0.0
                else:
                    angle = 0.0 if fixed is not None else rng.uniform(0, math.pi)
                center = fixed if fixed is not None else self.random_point(rng)
                host, why = self.host_of(kind, spec, center, self.outline_of(kind, key, spec, center, size, width, angle), fixed is not None)
                if why is None:
                    footprint, parts, options = self.body(kind, key, spec, center, size, width, angle)
                    things.append(Placed(key, entry_id, kind.name, center, size, width, angle, footprint, parts, host,
                                         options=options + style))
                    self.placed.append(things[-1])
                    break
                reason = why
            else:
                del self.placed[len(self.placed) - len(things):]
                if spec.at is not None:
                    fix = "move it (at)" if reason.startswith("that point") else "move it (at) or make it smaller (size)"
                    raise fail(spec, entry_id, f"at {at_text(spec.at)}, {format_length(size)} long: {reason}; {fix}")
                raise fail(spec, entry_id, f"could not fit {spec.count} of them ({format_length(size)} each) into the "
                                           f"{self.host_words(kind)}; use a smaller count or size, or a larger cell")
        del self.placed[len(self.placed) - len(things):]
        return things

    def along_wall(self, rng: random.Random, kind: Kind, width: float) -> tuple[Point, float]:
        """A place just inside a plant cell's plasma membrane, long axis along it."""
        cell = self.cell
        assert isinstance(cell, RoundedBox)
        t = rng.random()
        p, (nx, ny) = cell.point(t), cell.normal(t)
        inward = self.edge_room + width / 2 + 0.08
        return (p[0] - nx * inward, p[1] - ny * inward), math.atan2(ny, nx) + math.pi / 2

    def host_words(self, kind: Kind) -> str:
        return "nucleoplasm" if kind.name == "nucleolus" else "cytosol"

    def host_of(self, kind: Kind, spec: ObjectSpec, center: Point, footprint: tuple[Shape, ...], fixed: bool) -> tuple[str, str | None]:
        """Where a structure at ``center`` would be, and why it cannot be there (``None``: it can)."""
        shape = footprint[0]
        if kind.name == "nucleolus":
            for nucleus in self.nuclei():
                inner = nucleus.parts[0].membranes[-1][1]
                if inside(shape, inner, 0.15):
                    return (f"{nucleus.key}.nucleoplasm", None if not self.overlaps_region(shape) else "it overlaps another nucleolus")
            compartment = self.world().compartment_at(center)[0]
            if fixed and compartment != "nucleoplasm":
                return ("", f"that point is in the {noun(COMPARTMENTS[compartment].label)}; {kind.why}")
            return ("", "it does not lie wholly inside a nucleus's inner membrane")
        compartment, instance = self.world().compartment_at(center)
        if fixed and compartment not in kind.places:
            return ("", f"that point is in the {instance_words(instance)}; {kind.why}")
        why = self.fits(footprint)
        return ("cytosol", why)

    def overlaps_region(self, shape: Shape) -> bool:
        return any(overlap(shape, other.footprint[0], 0.1) for other in self.placed if other.kind == "nucleolus")

    def nucleus_for(self, spec: ObjectSpec, entry_id: str, what: str) -> Placed:
        nuclei = self.nuclei()
        if not nuclei:
            raise fail(spec, entry_id, f"{what}; add a nucleus to objects (or use contents: typical)")
        return nuclei[0]

    def place_sheets(self, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
        """The rough ER: curved sheets round the nucleus, on ``side`` (degrees, default away from
        the Golgi), over ``span`` degrees, the first joined to the outer nuclear membrane and each
        to the next (one lumen with the perinuclear space), with COPII buds at exit sites."""
        if spec.at is not None:
            raise fail(spec, entry_id, "the rough ER wraps around the nucleus: give side (the direction, degrees) and span instead of at")
        nucleus = self.nucleus_for(spec, entry_id, "the rough ER grows from the nuclear envelope")
        sheets = spec.sheets or 4
        span = math.radians(spec.span if spec.span is not None else 200.0)
        side = math.radians(spec.side) if spec.side is not None else self.golgi_side() + math.pi
        base = max(nucleus.size, nucleus.width) / 2 + 0.35
        cx, cy = nucleus.center
        bands = [ArcBand(cx, cy, base + 0.4 * k, ER_LUMEN + BILAYER, side - span / 2, side + span / 2) for k in range(sheets)]
        why = self.fits(tuple(bands))
        if why is not None:
            raise fail(spec, entry_id, f"{sheets} sheets over {math.degrees(span):g}° round the nucleus: {why}; "
                                       "use fewer sheets, a smaller span or another side")
        outer = nucleus.footprint[0]
        necks = er_necks(bands, outer if isinstance(outer, Ellipse) else None, entry_id)
        last = bands[-1]
        buds = []
        for end, sign in ((last.end, -1.0), (last.start, 1.0)):
            angle = end + sign * 0.35 / last.radius
            r = last.radius + last.thickness / 2 + 0.035 * 0.5
            buds.append(((cx + r * math.cos(angle), cy + r * math.sin(angle)), 0.035, "copii", sheets - 1))
        bud_shapes = [Ellipse(c[0], c[1], r, r) for c, r, _, _ in buds]
        region = Region.of(*bands, *necks, *bud_shapes, origin=nucleus.center)
        middle = bands[len(bands) // 2].center()
        return [Placed(entry_id, entry_id, kind.name, middle, 2 * (base + 0.4 * sheets), 0.4 * sheets, side, (*bands, *necks, *bud_shapes),
                       (Part((("er_membrane", region),), ("er_lumen",)),), "cytosol", joined=(nucleus.key,),
                       options=(("sheets", tuple(bands)), ("necks", tuple(necks)), ("buds", tuple(buds))))]

    def golgi_side(self) -> float:
        """The direction (radians) from the nucleus to the Golgi and centrosome."""
        golgi = next((p for p in self.placed if p.kind == "golgi"), None)
        nucleus = self.nuclei()[0] if self.nuclei() else None
        if golgi is not None and nucleus is not None:
            return math.atan2(golgi.center[1] - nucleus.center[1], golgi.center[0] - nucleus.center[0])
        return math.radians(-25.0)

    def beside_nucleus(self, distance: float, turn: float = 0.0) -> Point | None:
        """A point ``distance`` µm out from the nucleus's envelope towards the Golgi side (turned
        by ``turn`` radians)."""
        nuclei = self.nuclei()
        if not nuclei:
            return None
        nucleus = nuclei[0]
        side = self.golgi_side() + turn
        ellipse = nucleus.footprint[0]
        assert isinstance(ellipse, Ellipse)
        local = side - ellipse.angle
        r = 1 / math.sqrt((math.cos(local) / ellipse.a) ** 2 + (math.sin(local) / ellipse.b) ** 2)
        return (nucleus.center[0] + (r + distance) * math.cos(side), nucleus.center[1] + (r + distance) * math.sin(side))

    def place_golgi(self, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
        """A Golgi stack: ``cisternae`` curved cisternae (cis, medial, trans) with dilated rims and
        budding vesicles, the cis (convex) face towards the nucleus; beside the nucleus, else
        scattered."""
        size = self.size_of(kind, spec)
        count = spec.cisternae or 5
        rng = self.rng(entry_id, "golgi")
        nuclei = self.nuclei()
        first = spec.at if spec.at is not None else self.beside_nucleus(1.6)
        if first is None and spec.at is None and self.spec.kind == "animal" and not any(p.kind == "golgi" for p in self.placed):
            first = (0.35 * self.cell.bounds()[2], 0.3 * self.cell.bounds()[1])
        if spec.at is not None:
            compartment, instance = self.world().compartment_at(spec.at)
            if compartment not in kind.places:
                raise fail(spec, entry_id, f"at {at_text(spec.at)}: that point is in the {instance_words(instance)}; {kind.why}")
        tries = 1 if spec.at is not None else SCATTER_TRIES
        why: str | None = "no room"
        for attempt in range(tries):
            center = first if attempt == 0 and first is not None else self.random_point(rng)
            if spec.angle is not None:
                facing = math.radians(spec.angle)
            elif nuclei:
                facing = math.atan2(nuclei[0].center[1] - center[1], nuclei[0].center[0] - center[0])
            else:
                facing = rng.uniform(0, 2 * math.pi)
            bands, cisternae, buds = self.golgi_shapes(entry_id, center, size, count, facing)
            footprint = (*bands, *(s for c in cisternae for s in c if not isinstance(s, ArcBand)), *(Ellipse(c[0], c[1], r, r) for c, r, _, _ in buds))
            if attempt > 0 and self.world().compartment_at(center)[0] != "cytosol":
                continue
            why = self.fits(footprint)
            if why is None:
                break
        else:
            where = f"at {at_text(spec.at)}, " if spec.at is not None else ""
            raise fail(spec, entry_id, f"{where}{format_length(size)} long: {why}; move it (at) or make it smaller (size)")
        names = ["cis_golgi_lumen"] + ["medial_golgi_lumen"] * (count - 2) + ["trans_golgi_lumen"]
        parts = []
        for k, shapes in enumerate(cisternae):
            mine = [Ellipse(c[0], c[1], r, r) for c, r, _, i in buds if i == k]
            parts.append(Part((("golgi_membrane", Region.of(*shapes, *mine, origin=center)),), (names[k],)))
        thickness = GOLGI_LUMEN + BILAYER
        return [Placed(entry_id, entry_id, kind.name, center, size, GOLGI_PERIOD * (count - 1) + thickness, facing, footprint, tuple(parts),
                       "cytosol", facing=facing, options=(("cisternae", tuple(tuple(c) for c in cisternae)), ("bands", tuple(bands)),
                                                          ("buds", tuple(buds))))]

    def golgi_shapes(self, key: str, center: Point, size: float, count: int, facing: float
                     ) -> tuple[list[ArcBand], list[list[object]], list[tuple[Point, float, str, int]]]:
        curve = 2.6 * size
        thickness = GOLGI_LUMEN + BILAYER
        depth = GOLGI_PERIOD * (count - 1)
        # the cisternae curve round a point behind the trans face, so the cis face is convex
        ox = center[0] - (curve - depth / 2) * math.cos(facing)
        oy = center[1] - (curve - depth / 2) * math.sin(facing)
        bands = []
        for k in range(count):                       # cis (k = 0) to trans
            radius = curve - k * GOLGI_PERIOD
            length = size * (1.0 - 0.06 * abs(k - (count - 1) / 2))
            half = length / 2 / radius
            bands.append(ArcBand(ox, oy, radius, thickness, facing - half, facing + half))
        cisternae = [golgi_cisterna(band, k, count, key) for k, band in enumerate(bands)]
        return bands, cisternae, golgi_buds(bands, key)

    def place_tubules(self, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
        """Smooth ER: a network of tubules between three-way junctions in a region ``size``
        across, joined to the end of a rough-ER sheet when one is near."""
        size = self.size_of(kind, spec)
        count = spec.tubules or 18
        rng = self.rng(entry_id, "tubules")
        centers: list[Point | None] = [spec.at] if spec.at is not None else [self.beside_nucleus(2.6, math.radians(-45.0))] + [None] * 60
        last = "no room"
        structures = self.structures()

        def ok(p: Point) -> bool:
            return self.cell.contains(p, -(self.edge_room + 0.1)) and not any(s.contains(p, 0.25) for t in structures for s in t.footprint)

        for attempt, center in enumerate(centers):
            if center is None:
                center = self.random_point(rng)
            nodes, edges = er_network(center, size, count, f"{entry_id}:{attempt}", ok)
            if len(edges) < 2:
                last = "no room for its tubules"
                continue
            pieces = [c for k, (i, j) in enumerate(edges) for c in tubule(nodes[i], nodes[j], f"{entry_id}:{k}")]
            joints = [Ellipse(x, y, ER_TUBULE * 0.65, ER_TUBULE * 0.65) for x, y in nodes]
            why = self.fits(tuple(pieces))
            if why is not None:
                last = why
                if spec.at is not None:
                    break
                continue
            joined: tuple[str, ...] = ()
            link = self.er_link(nodes)
            if link:
                pieces += link[1]
                joined = (link[0],)
            region = Region.of(*pieces, *joints, origin=center)
            return [Placed(entry_id, entry_id, kind.name, center, size, size, 0.0, tuple(pieces), (Part((("er_membrane", region),), ("er_lumen",)),),
                           "cytosol", joined=joined, options=(("nodes", tuple(nodes)), ("edges", tuple(edges))))]
        raise fail(spec, entry_id, f"no room for the smooth ER ({format_length(size)} across): {last}; give it another at or a smaller size")

    def er_link(self, nodes: list[Point]) -> tuple[str, list[Capsule]] | None:
        """A tubule from the nearest rough-ER sheet end to the network (the smooth ER grows out of
        the rough ER), when one is near and the way is free."""
        rough = [p for p in self.placed if p.kind == "rough_er"]
        best = None
        for er in rough:
            for band in er.option("sheets", ()):
                for end in band.ends():
                    for k, node in enumerate(nodes):
                        d = math.dist(end, node)
                        if d < 3.2 and (best is None or d < best[0]):
                            best = (d, er.key, end, node, k)
        if best is None:
            return None
        _, key, end, node, k = best
        pieces = tubule(end, node, f"link:{k}")
        for piece in pieces:
            if self.fits((piece,), ignore=(key,), room=0.05) is not None and not any(s.contains(piece.center(), 0.3) for s in self.thing_shapes(key)):
                return None
        return key, pieces

    def thing_shapes(self, key: str) -> tuple[Shape, ...]:
        return next(p.footprint for p in self.placed if p.key == key)

    # ----- bound and generated things ------------------------------------------------------------

    def place_bound(self, entry_id: str, spec: ObjectSpec, kind: Kind, host: Placed, points: list[tuple[Point, Point]]) -> list[Placed]:
        """Complexes on a membrane: one per ``(point, outward normal)``."""
        size = spec.size or kind.size_in(self.spec.kind)
        width = spec.width or (kind.width or size)
        things = []
        for n, ((x, y), (nx, ny)) in enumerate(points):
            lift = 0.0 if kind.name == "nuclear_pore" else size / 2 + BILAYER / 2
            center = (x + nx * lift, y + ny * lift)
            key = f"{entry_id}#{n + 1}" if len(points) > 1 else entry_id
            things.append(Placed(key, entry_id, kind.name, center, size, width, math.atan2(ny, nx),
                                 (Ellipse(center[0], center[1], size / 2, width / 2, math.atan2(ny, nx)),), (), "cytosol",
                                 surface=host.key, normal=(nx, ny)))
        return things

    def surface_points(self, host: Placed, spacing: float, rng: random.Random | None = None, count: int | None = None,
                       avoid: list[Point] = (), clearance: float = 0.09) -> list[tuple[Point, Point]]:  # type: ignore[assignment]
        """Points on the cytosolic face of ``host``'s membrane (an ER's sheet faces, a nucleus's
        outer membrane), ``clearance`` µm from the points in ``avoid``. With ``count``, that many
        chosen at random."""
        candidates: list[tuple[Point, Point]] = []
        shapes = host.option("sheets") or host.footprint[:1]
        for shape in shapes:
            if isinstance(shape, ArcBand):
                candidates += shape.faces(spacing)
            elif isinstance(shape, (Ellipse, Capsule)):
                candidates += shape.surface(spacing, 0.5)
        candidates = [c for c in candidates if all(math.hypot(c[0][0] - a[0], c[0][1] - a[1]) > clearance for a in avoid)]
        world = self.world()
        candidates = [c for c in candidates if world.compartment_at((c[0][0] + c[1][0] * 0.03, c[0][1] + c[1][1] * 0.03))[0] == "cytosol"]
        if count is not None and rng is not None:
            rng.shuffle(candidates)
            candidates = sorted(candidates[:count], key=lambda c: (c[0][0], c[0][1]))
        return candidates

    def scatter_complexes(self, entry_id: str, spec: ObjectSpec, kind: Kind, regions: list[tuple[str, Placed | None]]) -> list[Placed]:
        """Complexes scattered in compartment instances (``(compartment, owner)``; the cytosol has
        no owner)."""
        size = spec.size or kind.size_in(self.spec.kind)
        width = spec.width or (kind.width or size)
        rng = self.rng(entry_id)
        world = self.world()
        boxes = []
        for compartment, owner in regions:
            boxes.append(self.cell.bounds() if owner is None else owner.footprint[0].bounds())
        things: list[Placed] = []
        grid: dict[tuple[int, int], list[Point]] = {}
        cell_size = max(2 * size, 1e-3)
        blockers = [t for t in world.structures() if t.parts == ()]
        for n in range(spec.count):
            for _ in range(SCATTER_TRIES):
                k = rng.randrange(len(regions))
                x0, y0, x1, y1 = boxes[k]
                p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
                gx, gy = int(p[0] // cell_size), int(p[1] // cell_size)
                if any(math.hypot(p[0] - q[0], p[1] - q[1]) < 2 * size for i in (-1, 0, 1) for j in (-1, 0, 1) for q in grid.get((gx + i, gy + j), ())):
                    continue
                compartment, instance = world.compartment_at(p)
                wanted, owner = regions[k]
                if compartment != wanted or (owner is not None and not instance.startswith(owner.key + ".")):
                    continue
                if not self.cell.contains(p, -0.05 * min(1.0, self.edge_room / EDGE_ROOM)) or \
                        any(t.contains(p, size) for t in (blockers if compartment != "cytosol" else world.structures())):
                    continue
                grid.setdefault((gx, gy), []).append(p)
                key = entry_id if spec.count == 1 else f"{entry_id}#{n + 1}"
                angle = rng.uniform(0, math.pi)
                things.append(Placed(key, entry_id, kind.name, p, size, width, angle, (Ellipse(p[0], p[1], size / 2, width / 2, angle),), (), instance))
                break
            else:
                raise fail(spec, entry_id, f"could not fit {spec.count} of them into the {noun(COMPARTMENTS[regions[0][0]].label)}; "
                                           "use a smaller count")
        return things

    def generated_vesicles(self, owner: Placed, spec: ObjectSpec) -> list[Placed]:
        """Free vesicles round a Golgi stack (COPI near the cis face and the rims, clathrin-coated
        and secretory ones off the trans face) or near the rough ER's exit sites (COPII)."""
        rng = rng_for("vesicles", self.spec.seed, owner.key)
        wanted: list[tuple[Point, str, float]] = []
        if owner.kind == "golgi":
            facing = owner.facing or 0.0
            ux, uy = math.cos(facing), math.sin(facing)          # towards the cis side
            px, py = -uy, ux
            cx, cy = owner.center
            half = owner.size / 2
            for along, ahead, coat, size in ((-0.25, 0.32, "copi", 0.06), (0.3, 0.38, "copi", 0.06), (0.98, 0.0, "copi", 0.06),
                                             (-1.0, -0.12, "copi", 0.06), (-0.2, -0.45, "clathrin", 0.08), (0.25, -0.5, "clathrin", 0.08),
                                             (0.0, -0.75, "none", 0.1), (0.45, -0.85, "none", 0.1)):
                wanted.append(((cx + px * along * half * 1.25 + ux * ahead, cy + py * along * half * 1.25 + uy * ahead), coat, size))
        else:
            for center, _r, _coat, _sheet in owner.option("buds", ()):
                er = owner.option("sheets")[-1]
                d = math.atan2(center[1] - er.cy, center[0] - er.cx)
                for k in range(2):
                    r = math.dist(center, (er.cx, er.cy)) + 0.15 + 0.12 * k
                    a = d + rng.uniform(-0.05, 0.05)
                    wanted.append(((er.cx + r * math.cos(a), er.cy + r * math.sin(a)), "copii", 0.065))
        things = []
        kind = KINDS["vesicle"]
        for n, (p, coat, size) in enumerate(wanted):
            p = (p[0] + rng.uniform(-0.03, 0.03), p[1] + rng.uniform(-0.03, 0.03))
            key = f"{owner.key}.vesicles#{n + 1}"
            vspec = ObjectSpec("vesicle", coat=coat, size=size)
            footprint, parts, options = self.body(kind, key, vspec, p, size, size, 0.0)
            if self.world().compartment_at(p)[0] != "cytosol" or self.fits(footprint, room=0.02) is not None:
                continue
            thing = Placed(key, f"{owner.key}.vesicles", "vesicle", p, size, size, 0.0, footprint, parts, "cytosol", options=options)
            things.append(thing)
            self.placed.append(thing)
        del self.placed[len(self.placed) - len(things):]
        return things


def pore_points(outer: Ellipse, inner: Ellipse) -> list[tuple[Point, Point]]:
    """Where a nucleus's pores are: about one per µm along the middle of its envelope."""
    middle = Ellipse(outer.cx, outer.cy, (outer.a + inner.a) / 2, (outer.b + inner.b) / 2, outer.angle)
    return middle.surface(1.0 / PORES_PER_UM, 0.25)


def ribosome_density(kind: str) -> float:
    """Bound ribosomes per µm of a face: the rough ER's, half that on the nucleus."""
    return ER_RIBOSOMES_PER_UM / (2.0 if kind == "nucleus" else 1.0)


def neighbours(builder: Builder) -> tuple[Neighbour, ...]:
    """Cells round the cell: animal cells on a stretched hexagonal lattice, each with its
    nucleus; plant cells in rows like bricks, wall against wall; bacteria scattered round in a
    colony."""
    cell = builder.cell
    x0, y0, x1, y1 = cell.bounds()
    a, b = (x1 - x0) / 2, (y1 - y0) / 2
    out = []
    if builder.spec.kind == "plant":
        wall = builder.envelope[0][1].bounds()
        t = wall[2] - x1
        step_x, step_y = 2 * a + 2 * t, 2 * b + 2 * t
        for j in range(-2, 3):
            for i in range(-3, 4):
                ox = i * step_x + (step_x / 2 if j % 2 else 0.0)
                if (i, j) == (0, 0) or abs(ox) > 3.6 * step_x / 2 + step_x or math.hypot(ox / step_x, j * step_y / step_y) > 2.6:
                    continue
                rng = builder.rng("tissue", i, j)
                body = RoundedBox(ox, j * step_y, 2 * a, 2 * b, cell.radius if isinstance(cell, RoundedBox) else 1.0)   # wall against wall
                nucleus = Ellipse(ox + rng.uniform(-0.35, -0.2) * a, j * step_y + rng.uniform(-0.2, 0.2) * b, 0.17 * a, 0.14 * a, rng.uniform(0, math.pi))
                out.append(Neighbour(body, nucleus, RoundedBox(ox, j * step_y, 2 * a + 2 * t, 2 * b + 2 * t, body.radius + t)))
        return tuple(out)
    if builder.spec.kind == "bacterium":
        rng = builder.rng("colony")
        for k in range(26):
            for _ in range(60):
                r = rng.uniform(1.2, 3.4) * a
                ang = rng.uniform(0, 2 * math.pi)
                c = (r * math.cos(ang), r * math.sin(ang) * 0.8)
                rod = Capsule(c[0], c[1], 2 * a * rng.uniform(0.75, 1.15), 2 * b * rng.uniform(0.9, 1.05), rng.uniform(0, math.pi))
                if overlap(rod, builder.envelope[-1][1], 0.25 * b) or any(overlap(rod, n.cell, 0.2 * b) for n in out):
                    continue
                out.append(Neighbour(grown(rod, PERIPLASM if builder.spec.gram == "negative" else THICK_WALL), None))
                break
        return tuple(out)
    for i in range(-3, 4):
        for j in range(-2, 3):
            if (i, j) == (0, 0):
                continue
            ux, uy = 2.12 * i + 1.06 * j, 1.836 * j
            if math.hypot(ux, uy) > 4.5:
                continue
            rng = builder.rng("tissue", i, j)
            scale = rng.uniform(0.86, 1.0)
            cx = ux * a + rng.uniform(-0.04, 0.04) * a
            cy = uy * b + rng.uniform(-0.04, 0.04) * b
            body = Ellipse(cx, cy, a * scale, b * scale * rng.uniform(0.92, 1.05), rng.uniform(-0.25, 0.25))
            nucleus = Ellipse(cx + rng.uniform(-0.2, 0.2) * a, cy + rng.uniform(-0.2, 0.2) * b, 0.33 * a * scale, 0.29 * a * scale,
                              rng.uniform(0, math.pi))
            out.append(Neighbour(body, nucleus))
    return tuple(out)


def plant_vacuole(builder: Builder) -> RoundedBox:
    """The typical plant cell's central vacuole: most of the cell, the peripheral cytoplasm a
    band round it, a pocket on the left for the nucleus."""
    x0, y0, x1, y1 = builder.cell.bounds()
    band = min(PLANT_BAND, (y1 - y0) * 0.16)
    left = x0 + (x1 - x0) * PLANT_POCKET
    right = x1 - band
    return RoundedBox((left + right) / 2, (y0 + y1) / 2, right - left, (y1 - y0) - 2 * band, min(2.0, (y1 - y0 - 2 * band) * 0.15))


def plant_defaults(builder: Builder, kind: Kind, count: int) -> list[tuple[Point, float | None] | None]:
    """Default places in the typical plant cell: the nucleus in the pocket beside the vacuole,
    chloroplasts along the wall (their long axis along it)."""
    x0, y0, x1, y1 = builder.cell.bounds()
    if kind.name == "vacuole":
        box = plant_vacuole(builder)
        return [(box.center(), 0.0)]
    if kind.name == "nucleus":
        left = x0 + (x1 - x0) * PLANT_POCKET
        return [(((x0 + left) / 2 + 0.2, (y0 + y1) / 2 + 0.6), math.radians(80.0))]
    if kind.name == "chloroplast":
        cell = builder.cell
        assert isinstance(cell, RoundedBox)
        rng = builder.rng("chloroplasts")
        out: list[tuple[Point, float | None] | None] = []
        inward = builder.edge_room + (kind.width or 2.0) / 2 + 0.08
        for k in range(count):
            t = (k + 0.5) / count + rng.uniform(-0.02, 0.02) + 0.03
            p = cell.point(t)
            nx, ny = cell.normal(t)
            out.append(((p[0] - nx * inward, p[1] - ny * inward), math.atan2(ny, nx) + math.pi / 2))
        return out
    return []


def bacterium_defaults(builder: Builder, kind: Kind) -> list[tuple[Point, float | None] | None]:
    if kind.name == "nucleoid":
        return [((0.0, 0.0), 0.0)]
    return []


def nucleoid_size(builder: Builder) -> tuple[float, float]:
    x0, y0, x1, y1 = builder.cell.bounds()
    return (x1 - x0) * 0.55, (y1 - y0) * 0.5


def vacuole_size(builder: Builder) -> tuple[float, float]:
    box = plant_vacuole(builder)
    return box.width, box.height


__all__ = ["Builder", "EDGE_ROOM", "MAX_PLACED", "SCATTER_TRIES", "STRUCTURE_ROOM", "cell_shape", "grown", "neighbours", "pore_points",
           "ribosome_density", "plant_defaults", "bacterium_defaults", "nucleoid_size", "vacuole_size", "segment"]
