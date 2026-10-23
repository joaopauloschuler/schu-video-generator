"""The cell world (DESIGN.md §95): a cross-section of a cell as plain data — the cell, the
structures and complexes placed in it with real sizes in µm, the compartments and membranes
they make — built from a :class:`CellSpec` by :func:`build_cell_world`, which applies the
location rules (``rules.py``) and refuses what is impossible with a :class:`VidgenError` that
says what to write instead. No manim: ``vidgen validate`` runs it, renderers draw it."""

from __future__ import annotations

import difflib
import math
import random
from dataclasses import dataclass, field
from typing import Literal

from vidgen.errors import VidgenError

from .catalog import (
    CELL_KINDS, CELL_SIZE_RANGE, COMPARTMENTS, ER_LUMEN, ER_RIBOSOMES_PER_UM, ER_TUBULE, GOLGI_LUMEN, GOLGI_PERIOD, KINDS,
    MITO_GAP, PERINUCLEAR_GAP, PORES_PER_UM, BILAYER, TYPICAL_ANIMAL, Kind, main_interior,
)
from .geometry import ArcBand, Capsule, Ellipse, Point, Shape, inside, overlap
from .units import format_length

#: Names an object may not take: the scene's own targets and the cytosol / extracellular space.
RESERVED_IDS = frozenset({"cell", "title", "tissue", "scale_bar", "cytosol", "extracellular", "world"})
#: Room kept between a structure and the plasma membrane, and between two structures (µm).
EDGE_ROOM, STRUCTURE_ROOM = 0.25, 0.2
#: Tries per thing when scattering.
SCATTER_TRIES = 600
#: Most things one world holds (ribosomes along the ER included).
MAX_PLACED = 4000


@dataclass(frozen=True)
class ObjectSpec:
    """One ``objects`` entry as the model reads it (the scene's params give these): ``kind``,
    ``id``, ``at`` (µm from the cell's centre, x right, y up), ``size`` (its length, µm),
    ``width``, ``angle`` (degrees), ``inside`` (YAML ``in``), ``on`` (a structure whose membrane
    it sits on), ``count``; kind options (``sheets``, ``span``, ``side`` of the rough ER,
    ``cisternae`` of the Golgi, ``tubules`` of the smooth ER, ``pores`` and ``ribosomes`` of
    the nucleus and the rough ER); ``where`` names it in error messages (``objects[2]``)."""

    kind: str
    id: str | None = None
    at: Point | None = None
    size: float | None = None
    width: float | None = None
    angle: float | None = None
    inside: str | None = None
    on: str | None = None
    count: int = 1
    sheets: int | None = None
    span: float | None = None
    side: float | None = None
    cisternae: int | None = None
    tubules: int | None = None
    pores: bool | None = None
    ribosomes: bool | None = None
    where: str = ""


@dataclass(frozen=True)
class CellSpec:
    """The cell: its ``kind``, ``size`` (long axis, µm) and ``aspect`` (long over short), the
    ``contents`` it starts with (``typical`` or ``none``), the ``objects`` added (an object with
    the id of a typical one replaces it) and the ``seed`` of automatic placement."""

    kind: str = "animal"
    size: float = 20.0
    aspect: float = 1.25
    contents: Literal["typical", "none"] = "typical"
    objects: tuple[ObjectSpec, ...] = ()
    seed: int = 1


@dataclass(frozen=True)
class Part:
    """A membrane-bounded piece of a placed thing (a nucleus has one with two membranes; a
    rough ER one per sheet): ``membranes`` from the outside in, each ``(name, shape)``, and
    ``interior``: the compartment inside each membrane (``interior[k]`` lies inside membrane
    ``k`` and outside membrane ``k + 1``)."""

    membranes: tuple[tuple[str, Shape], ...]
    interior: tuple[str, ...]

    @property
    def outer(self) -> Shape:
        return self.membranes[0][1]


@dataclass(frozen=True)
class Placed:
    """One thing in the world: its ``key`` (the entry id, or ``<entry>#<n>`` for the n-th of
    several), ``entry``, ``kind``, ``center``, ``size`` (length) and ``width`` (µm), ``angle``
    (radians), ``footprint`` (the shapes it covers), ``parts``, where it is (``host``: a
    compartment instance such as ``cytosol`` or ``nucleus.nucleoplasm``), the structure whose
    membrane it sits on (``surface``) with the membrane's outward ``normal`` there, and
    ``facing``: a Golgi stack's cis direction (radians)."""

    key: str
    entry: str
    kind: str
    center: Point
    size: float
    width: float
    angle: float
    footprint: tuple[Shape, ...]
    parts: tuple[Part, ...]
    host: str
    surface: str | None = None
    normal: Point | None = None
    facing: float | None = None

    @property
    def info(self) -> Kind:
        return KINDS[self.kind]

    def contains(self, p: Point, pad: float = 0.0) -> bool:
        return any(s.contains(p, pad) for s in self.footprint)

    def compartment_at(self, p: Point) -> str | None:
        """The compartment of this thing that ``p`` lies in (``None``: outside it, or it has no
        membrane)."""
        for part in self.parts:
            for k in range(len(part.membranes) - 1, -1, -1):
                if part.membranes[k][1].contains(p):
                    return part.interior[k]
        return None


@dataclass(frozen=True)
class Entry:
    """An entry of the world: its id, kind, the keys of its placed things, the config place it
    came from, and the structure it belongs to for generated ones (``rough_er.ribosomes``)."""

    id: str
    kind: str
    keys: tuple[str, ...]
    where: str
    owner: str | None = None


@dataclass(frozen=True)
class Neighbour:
    """A neighbouring cell of the tissue around the cell: its outline and its nucleus."""

    cell: Ellipse
    nucleus: Ellipse


@dataclass(frozen=True)
class CellWorld:
    """A built cell world (µm, the cell's centre at the origin)."""

    kind: str
    cell: Ellipse
    placed: tuple[Placed, ...]
    entries: tuple[Entry, ...]
    neighbours: tuple[Neighbour, ...]
    seed: int
    _by_key: dict[str, Placed] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._by_key.update({p.key: p for p in self.placed})

    @property
    def size(self) -> float:
        """The cell's long axis (µm)."""
        return 2 * max(self.cell.a, self.cell.b)

    def thing(self, key: str) -> Placed:
        return self._by_key[key]

    def entry(self, entry_id: str) -> Entry:
        """The entry ``entry_id`` (``KeyError`` when there is none)."""
        for e in self.entries:
            if e.id == entry_id:
                return e
        raise KeyError(entry_id)

    def members(self, entry_id: str) -> list[Placed]:
        return [self._by_key[k] for k in self.entry(entry_id).keys]

    def structures(self) -> list[Placed]:
        return [p for p in self.placed if KINDS[p.kind].category == "structure"]

    def compartment_at(self, p: Point) -> tuple[str, str]:
        """``(compartment kind, instance)`` at point ``p``: ``("nucleoplasm",
        "nucleus.nucleoplasm")``, ``("cytosol", "cytosol")``, ``("extracellular",
        "extracellular")``."""
        if not self.cell.contains(p):
            return ("extracellular", "extracellular")
        for thing in self.structures():
            found = thing.compartment_at(p)
            if found is not None:
                return (found, f"{thing.key}.{found}")
        return ("cytosol", "cytosol")

    def region_at(self, p: Point) -> Placed | None:
        """The structure without a membrane (a nucleolus, a centrosome) whose region holds ``p``."""
        for thing in self.structures():
            if not thing.parts and thing.contains(p):
                return thing
        return None

    def tissue_bounds(self) -> tuple[float, float, float, float]:
        """Bounds of the cell and its neighbours (µm)."""
        shapes = [self.cell] + [n.cell for n in self.neighbours]
        boxes = [s.bounds() for s in shapes]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def noun(label: str) -> str:
    """A label inside a sentence: ``rough ER``, ``mitochondrion``, ``Golgi apparatus``, ``ER lumen``."""
    if label.startswith("Golgi") or len(label) > 1 and label[1].isupper():
        return label
    return label[0].lower() + label[1:]


def did_you_mean(name: str, known: list[str] | tuple[str, ...]) -> str:
    """``; did you mean 'x'?`` for the closest of ``known`` (empty when none is close)."""
    close = difflib.get_close_matches(name, list(dict.fromkeys(known)), n=2, cutoff=0.5)
    return f"; did you mean {' or '.join(repr(c) for c in close)}?" if close else ""


def _where(spec: ObjectSpec, entry_id: str) -> str:
    kind = noun(KINDS[spec.kind].label) if spec.kind in KINDS else spec.kind
    return f"{spec.where} ({kind} '{entry_id}')" if spec.where else f"{kind} '{entry_id}'"


def _fail(spec: ObjectSpec, entry_id: str, message: str) -> VidgenError:
    return VidgenError(f"{_where(spec, entry_id)}: {message}")


def _at_text(p: Point) -> str:
    return f"[{p[0]:g}, {p[1]:g}] µm"


class _Builder:
    """Places the entries one after another (see :func:`build_cell_world`)."""

    def __init__(self, spec: CellSpec) -> None:
        self.spec = spec
        half = spec.size / 2
        self.cell = Ellipse(0.0, 0.0, half, half / spec.aspect)
        self.placed: list[Placed] = []
        self.entries: list[Entry] = []

    # ----- helpers --------------------------------------------------------------------------

    def rng(self, *key: object) -> random.Random:
        return random.Random(":".join(str(k) for k in (self.spec.seed, *key)))

    def world(self) -> CellWorld:
        return CellWorld(self.spec.kind, self.cell, tuple(self.placed), tuple(self.entries), (), self.spec.seed)

    def structures(self) -> list[Placed]:
        return [p for p in self.placed if KINDS[p.kind].category == "structure"]

    def nuclei(self) -> list[Placed]:
        return [p for p in self.placed if p.kind == "nucleus"]

    def fits(self, shapes: tuple[Shape, ...], ignore: tuple[str, ...] = ()) -> str | None:
        """Why ``shapes`` cannot go in the cytosol here (``None``: they can)."""
        for shape in shapes:
            if not inside(shape, self.cell, EDGE_ROOM):
                return "it reaches the plasma membrane or out of the cell"
        for other in self.structures():
            if other.key in ignore or other.entry in ignore:
                continue
            if any(overlap(s, o, STRUCTURE_ROOM) for s in shapes for o in other.footprint):
                return f"it overlaps '{other.key}'"
        return None

    def add(self, entry_id: str, spec: ObjectSpec, things: list[Placed], owner: str | None = None) -> None:
        self.placed.extend(things)
        self.entries.append(Entry(entry_id, spec.kind, tuple(t.key for t in things), spec.where, owner))
        if len(self.placed) > MAX_PLACED:
            raise _fail(spec, entry_id, f"too many things in one cell (more than {MAX_PLACED}); use a smaller count")

    # ----- shapes of each kind --------------------------------------------------------------

    @staticmethod
    def round_parts(kind: Kind, shape: Shape) -> tuple[Part, ...]:
        """One part per membrane-bounded kind: its membranes inset one after another."""
        if not kind.membranes:
            return ()
        gaps = {"nucleus": PERINUCLEAR_GAP + BILAYER, "mitochondrion": MITO_GAP + BILAYER}
        membranes = [(kind.membranes[0], shape)]
        for name in kind.membranes[1:]:
            membranes.append((name, membranes[-1][1].inset(gaps.get(kind.name, BILAYER * 2))))
        return (Part(tuple(membranes), kind.interior),)

    def body_shape(self, kind: Kind, center: Point, size: float, width: float, angle: float) -> Shape:
        if kind.shape == "capsule":
            return Capsule(center[0], center[1], size, width, angle)
        return Ellipse(center[0], center[1], size / 2, width / 2, angle)

    # ----- placing ----------------------------------------------------------------------------

    def place_round(self, entry_id: str, spec: ObjectSpec, kind: Kind, defaults: list[Point | None]) -> list[Placed]:
        """Structures with a body shape (ellipse, capsule, region): at ``at``, at the default
        place, or scattered in the cytosol (or in their host compartment)."""
        size = spec.size or kind.size
        width = spec.width or (kind.width if kind.width is not None else size)
        if kind.width is not None and spec.size and not spec.width:
            width = min(width, size)
        if width > size:
            size, width = width, size
        things: list[Placed] = []
        rng = self.rng(entry_id)
        for n in range(spec.count):
            key = entry_id if spec.count == 1 else f"{entry_id}#{n + 1}"
            default = defaults[n] if n < len(defaults) else None
            fixed = spec.at
            tries = 1 if fixed is not None else SCATTER_TRIES
            reason = "no room"
            for attempt in range(tries):
                if fixed is None and attempt == 0 and default is not None:
                    fixed = default          # the typical layout's place first, then scattered
                elif spec.at is None:
                    fixed = None
                if spec.angle is not None:
                    angle = math.radians(spec.angle)
                elif kind.name == "nucleus":
                    angle = math.radians(10.0)
                else:
                    angle = 0.0 if fixed is not None else rng.uniform(0, math.pi)
                center = fixed if fixed is not None else self.random_point(rng, kind, size)
                shape = self.body_shape(kind, center, size, width, angle)
                host, why = self.host_of(kind, spec, entry_id, center, shape, fixed is not None)
                if why is None:
                    things.append(Placed(key, entry_id, kind.name, center, size, width, angle, (shape,), self.round_parts(kind, shape), host))
                    self.placed.append(things[-1])
                    break
                reason = why
            else:
                del self.placed[len(self.placed) - len(things):]
                if spec.at is not None:
                    fix = "move it (at)" if reason.startswith("that point") else "move it (at) or make it smaller (size)"
                    raise _fail(spec, entry_id, f"at {_at_text(spec.at)}, {format_length(size)} long: {reason}; {fix}")
                raise _fail(spec, entry_id, f"could not fit {spec.count} of them ({format_length(size)} each) into the "
                                            f"{self.host_words(kind, spec)}; use a smaller count or size, or a larger cell")
        del self.placed[len(self.placed) - len(things):]
        return things

    def random_point(self, rng: random.Random, kind: Kind, size: float) -> Point:
        x0, y0, x1, y1 = self.cell.bounds()
        return (rng.uniform(x0, x1), rng.uniform(y0, y1))

    def host_words(self, kind: Kind, spec: ObjectSpec) -> str:
        return "nucleoplasm" if kind.name == "nucleolus" else "cytosol"

    def host_of(self, kind: Kind, spec: ObjectSpec, entry_id: str, center: Point, shape: Shape, fixed: bool) -> tuple[str, str | None]:
        """Where a structure at ``center`` would be, and why it cannot be there (``None``: it can)."""
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
            return ("", f"that point is in the {_instance_words(instance)}; {kind.why}")
        why = self.fits((shape,))
        return ("cytosol", why)

    def overlaps_region(self, shape: Shape) -> bool:
        return any(overlap(shape, other.footprint[0], 0.1) for other in self.placed if other.kind == "nucleolus")

    def nucleus_for(self, spec: ObjectSpec, entry_id: str, what: str) -> Placed:
        nuclei = self.nuclei()
        if not nuclei:
            raise _fail(spec, entry_id, f"{what}; add a nucleus to objects (or use contents: typical)")
        return nuclei[0]

    def place_sheets(self, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
        """The rough ER: curved sheets round the nucleus, on ``side`` (degrees, default away from
        the Golgi), over ``span`` degrees."""
        if spec.at is not None:
            raise _fail(spec, entry_id, "the rough ER wraps around the nucleus: give side (the direction, degrees) and span instead of at")
        nucleus = self.nucleus_for(spec, entry_id, "the rough ER grows from the nuclear envelope")
        sheets = spec.sheets or 4
        span = math.radians(spec.span if spec.span is not None else 200.0)
        side = math.radians(spec.side) if spec.side is not None else self.golgi_side() + math.pi
        base = max(nucleus.size, nucleus.width) / 2 + 0.35
        cx, cy = nucleus.center
        parts = []
        for k in range(sheets):
            band = ArcBand(cx, cy, base + 0.4 * k, ER_LUMEN + BILAYER, side - span / 2, side + span / 2)
            parts.append(band)
        why = self.fits(tuple(parts))
        if why is not None:
            raise _fail(spec, entry_id, f"{sheets} sheets over {math.degrees(span):g}° round the nucleus: {why}; "
                                        "use fewer sheets, a smaller span or another side")
        middle = parts[len(parts) // 2].center()
        thing = Placed(entry_id, entry_id, kind.name, middle, 2 * (base + 0.4 * sheets), 0.4 * sheets, side, tuple(parts),
                       tuple(Part((("er_membrane", band),), ("er_lumen",)) for band in parts), "cytosol")
        return [thing]

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
        """A Golgi stack: ``cisternae`` curved cisternae, cis (convex) face towards the nucleus."""
        size = spec.size or kind.size
        count = spec.cisternae or 5
        center = spec.at if spec.at is not None else self.beside_nucleus(1.6) or (0.35 * self.cell.a, -0.3 * self.cell.b)
        nuclei = self.nuclei()
        if spec.angle is not None:
            facing = math.radians(spec.angle)
        elif nuclei:
            facing = math.atan2(nuclei[0].center[1] - center[1], nuclei[0].center[0] - center[0])
        else:
            facing = math.pi
        curve = 1.6 * size
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
        if spec.at is not None:
            compartment, instance = self.world().compartment_at(center)
            if compartment not in kind.places:
                raise _fail(spec, entry_id, f"at {_at_text(center)}: that point is in the {_instance_words(instance)}; {kind.why}")
        why = self.fits(tuple(bands))
        if why is not None:
            raise _fail(spec, entry_id, f"at {_at_text(center)}, {format_length(size)} long: {why}; move it (at) or make it smaller (size)")
        return [Placed(entry_id, entry_id, kind.name, center, size, depth + thickness, facing, tuple(bands),
                       tuple(Part((("golgi_membrane", band),), ("golgi_lumen",)) for band in bands), "cytosol", facing=facing)]

    def place_tubules(self, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
        """Smooth ER: a cluster of curved tubules in a region ``size`` across."""
        size = spec.size or kind.size
        count = spec.tubules or 6
        rng = self.rng(entry_id, "tubules")
        centers = [spec.at] if spec.at is not None else [self.beside_nucleus(2.6, math.radians(-45.0))] + [None] * 40
        last = "no room"
        for attempt, center in enumerate(centers):
            if center is None:
                x0, y0, x1, y1 = self.cell.bounds()
                center = (rng.uniform(x0, x1), rng.uniform(y0, y1))
            bands = []
            for k in range(count):
                radius = rng.uniform(0.5, 1.3) * size / 3
                start = rng.uniform(0, 2 * math.pi)
                length = rng.uniform(0.35, 0.6) * size
                ox = center[0] + rng.uniform(-0.3, 0.3) * size - radius * math.cos(start + length / radius / 2)
                oy = center[1] + rng.uniform(-0.3, 0.3) * size - radius * math.sin(start + length / radius / 2)
                bands.append(ArcBand(ox, oy, radius, ER_TUBULE - BILAYER, start, start + length / radius))
            why = self.fits(tuple(bands))
            if why is None:
                return [Placed(entry_id, entry_id, kind.name, center, size, size, 0.0, tuple(bands),
                               tuple(Part((("er_membrane", band),), ("er_lumen",)) for band in bands), "cytosol")]
            last = why
            if spec.at is not None:
                break
        raise _fail(spec, entry_id, f"no room for the smooth ER ({format_length(size)} across): {last}; give it another at or a smaller size")

    def place_bound(self, entry_id: str, spec: ObjectSpec, kind: Kind, host: Placed, points: list[tuple[Point, Point]],
                    owner: str | None = None) -> list[Placed]:
        """Complexes on a membrane: one per ``(point, outward normal)``."""
        size = spec.size or kind.size
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
                       avoid: list[Point] = (), clearance: float = 0.09) -> list[tuple[Point, Point]]:
        """Points on the cytosolic face of ``host``'s membrane (an ER's sheet faces, a nucleus's
        outer membrane), ``clearance`` µm from the points in ``avoid``. With ``count``, that many
        chosen at random."""
        candidates: list[tuple[Point, Point]] = []
        for shape in host.footprint:
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
        size = spec.size or kind.size
        width = spec.width or (kind.width or size)
        rng = self.rng(entry_id)
        world = self.world()
        boxes = []
        for compartment, owner in regions:
            boxes.append(self.cell.bounds() if owner is None else owner.footprint[0].bounds())
        things: list[Placed] = []
        points: list[Point] = []
        for n in range(spec.count):
            for _ in range(SCATTER_TRIES):
                k = rng.randrange(len(regions))
                x0, y0, x1, y1 = boxes[k]
                p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
                compartment, instance = world.compartment_at(p)
                wanted, owner = regions[k]
                if compartment != wanted or (owner is not None and not instance.startswith(owner.key + ".")):
                    continue
                if not self.cell.contains(p, -0.05) or any(t.contains(p, size) for t in world.structures() if t.parts == () or compartment == "cytosol"):
                    continue
                if any(math.hypot(p[0] - q[0], p[1] - q[1]) < 2 * size for q in points):
                    continue
                points.append(p)
                key = entry_id if spec.count == 1 else f"{entry_id}#{n + 1}"
                angle = rng.uniform(0, math.pi)
                things.append(Placed(key, entry_id, kind.name, p, size, width, angle, (Ellipse(p[0], p[1], size / 2, width / 2, angle),), (), instance))
                break
            else:
                raise _fail(spec, entry_id, f"could not fit {spec.count} of them into the {noun(COMPARTMENTS[regions[0][0]].label)}; "
                                            "use a smaller count")
        return things


def _instance_words(instance: str) -> str:
    """``nucleoplasm of 'nucleus'`` for ``nucleus.nucleoplasm``; ``cytosol`` for ``cytosol``."""
    if "." not in instance:
        return noun(COMPARTMENTS[instance].label) if instance in COMPARTMENTS else instance
    key, compartment = instance.rsplit(".", 1)
    return f"{noun(COMPARTMENTS[compartment].label)} of '{key}'"


#: The order kinds are placed in when nothing else decides: what others are placed by first.
_PLACE_ORDER = {"nucleus": 0, "golgi": 1, "centrosome": 2, "nucleolus": 3, "rough_er": 4, "smooth_er": 5}


def _entries(spec: CellSpec) -> list[tuple[str, ObjectSpec]]:
    """The entries with their ids: the typical contents (unless ``contents: none``), each
    replaced by an object of the same id, then the other objects in order."""
    if spec.kind not in CELL_KINDS:
        raise VidgenError(f"cell kind '{spec.kind}': only {', '.join(CELL_KINDS)} cells are drawn so far")
    given: list[tuple[str, ObjectSpec]] = []
    counts: dict[str, int] = {}
    for obj in spec.objects:
        if obj.kind not in KINDS:
            raise VidgenError(f"{obj.where or 'objects'}: unknown kind '{obj.kind}'{did_you_mean(obj.kind, list(KINDS))} "
                              f"(kinds: {', '.join(KINDS)})")
        if obj.id is not None:
            entry_id = obj.id
        else:
            counts[obj.kind] = counts.get(obj.kind, 0) + 1
            entry_id = obj.kind if counts[obj.kind] == 1 else f"{obj.kind}_{counts[obj.kind]}"
        if entry_id in RESERVED_IDS:
            raise VidgenError(f"{obj.where or 'objects'}: id '{entry_id}' is reserved ({', '.join(sorted(RESERVED_IDS))}); choose another")
        if "." in entry_id or "#" in entry_id:
            raise VidgenError(f"{obj.where or 'objects'}: id '{entry_id}': use letters, digits, '_' and '-' (no '.' or '#')")
        if any(entry_id == other for other, _ in given):
            raise VidgenError(f"{obj.where or 'objects'}: two objects have the id '{entry_id}'; give one another id")
        given.append((entry_id, obj))
    ids = {entry_id for entry_id, _ in given}
    typical = []
    if spec.contents == "typical":
        typical = [(entry_id, ObjectSpec(kind, count=count, where="contents: typical"))
                   for entry_id, kind, count in TYPICAL_ANIMAL if entry_id not in ids]
    return typical + given


def _check_static(entry_id: str, spec: ObjectSpec) -> None:
    kind = KINDS[spec.kind]
    if spec.count < 1:
        raise _fail(spec, entry_id, "count must be at least 1")
    if spec.at is not None and spec.count > 1:
        raise _fail(spec, entry_id, f"at places one thing; for {spec.count} of them leave out at (they are scattered) or write one object per place")
    if spec.inside is not None and spec.on is not None:
        raise _fail(spec, entry_id, "give in (a compartment it floats in) or on (a structure whose membrane it sits on), not both")
    if spec.on is not None and not kind.surfaces:
        raise _fail(spec, entry_id, f"a {noun(kind.label)} does not sit on a membrane; {kind.why}")
    if spec.inside is not None and kind.category == "structure":
        raise _fail(spec, entry_id, "in is for complexes (ribosomes, proteasomes); place a structure with at, or leave at out to scatter it")
    if spec.count > 1 and kind.shape in ("sheets", "stack", "tubules"):
        raise _fail(spec, entry_id, f"one {kind.label} per object; write another object for a second one")
    options = {"sheets": ("rough_er",), "span": ("rough_er",), "side": ("rough_er",), "cisternae": ("golgi",), "tubules": ("smooth_er",),
               "pores": ("nucleus",), "ribosomes": ("nucleus", "rough_er")}
    for name, kinds in options.items():
        if getattr(spec, name) is not None and spec.kind not in kinds:
            raise _fail(spec, entry_id, f"{name} is for {' and '.join(kinds)}, not a {noun(kind.label)}")
    if spec.size is not None and kind.category == "structure" and spec.size < 0.02:
        raise _fail(spec, entry_id, f"size {format_length(spec.size)} is too small for a {noun(kind.label)}")


def _resolve_in(builder: _Builder, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[tuple[str, Placed | None]]:
    """The compartment instances ``in:`` names, after the location rule."""
    text = spec.inside or "cytosol"
    names: list[str] = ["cytosol", "extracellular", *COMPARTMENTS]
    entries = {e.id: e for e in builder.entries}
    names += [e for e in entries] + [f"{e}.{c}" for e in entries for c in KINDS[entries[e].kind].interior]
    if text in ("cytosol", "extracellular"):
        compartment, owners = text, [None]
    elif text in COMPARTMENTS:
        compartment = text
        owners = [p for p in builder.structures() if compartment in KINDS[p.kind].interior]
        if not owners:
            raise _fail(spec, entry_id, f"in: {text}: nothing in this cell has a {noun(COMPARTMENTS[text].label)}")
    else:
        entry_part, _, sub = text.partition(".")
        if entry_part not in entries:
            raise _fail(spec, entry_id, f"in: '{text}' is neither a compartment nor an object{did_you_mean(text, names)}")
        host_kind = KINDS[entries[entry_part].kind]
        compartment = sub or main_interior(host_kind) or ""
        if not compartment:
            hint = " (it is part of the nucleoplasm)" if host_kind.name == "nucleolus" else ""
            raise _fail(spec, entry_id, f"in: '{text}': a {noun(host_kind.label)} has no inside of its own{hint}")
        if compartment not in host_kind.interior:
            raise _fail(spec, entry_id, f"in: '{text}': a {noun(host_kind.label)} has {', '.join(host_kind.interior) or 'no compartments'}"
                                        f"{did_you_mean(compartment, list(host_kind.interior))}")
        owners = [builder.world().thing(k) for k in entries[entry_part].keys]
    if compartment not in kind.places:
        raise _fail(spec, entry_id, f"a {noun(kind.label)} cannot be in the {noun(COMPARTMENTS[compartment].label)}: {kind.why}")
    return [(compartment, owner) for owner in owners]


def build_cell_world(spec: CellSpec) -> CellWorld:
    """Build the world of ``spec``: the cell, every entry placed (written ``at``, default
    places for the typical layout, else scattered by ``seed``), the generated complexes (nuclear
    pores, ribosomes on the rough ER and the outer nuclear membrane) and the tissue around.
    Raises :class:`VidgenError` naming the object and what to change when an entry breaks a
    location rule, overlaps another, does not fit, or names something unknown."""
    lo, hi = CELL_SIZE_RANGE
    if not lo <= spec.size <= hi:
        raise VidgenError(f"cell size {format_length(spec.size)}: an animal cell is drawn from {lo:g} to {hi:g} µm long")
    if not 1.0 <= spec.aspect <= 2.5:
        raise VidgenError(f"cell aspect {spec.aspect:g}: the long axis over the short one, from 1 (round) to 2.5")
    entries = _entries(spec)
    for entry_id, obj in entries:
        _check_static(entry_id, obj)
    builder = _Builder(spec)
    structures = [(i, e) for i, e in enumerate(entries) if KINDS[e[1].kind].category == "structure"]
    complexes = [(i, e) for i, e in enumerate(entries) if KINDS[e[1].kind].category == "complex"]
    structures.sort(key=lambda item: (_PLACE_ORDER.get(item[1][1].kind, 9), item[1][1].at is None, item[0]))
    for _, (entry_id, obj) in structures:
        kind = KINDS[obj.kind]
        if kind.shape == "sheets":
            things = builder.place_sheets(entry_id, obj, kind)
        elif kind.shape == "stack":
            things = builder.place_golgi(entry_id, obj, kind)
        elif kind.shape == "tubules":
            things = builder.place_tubules(entry_id, obj, kind)
        else:
            things = builder.place_round(entry_id, obj, kind, _defaults(builder, kind, obj))
        builder.add(entry_id, obj, things)
    _generated(builder, entries)
    for _, (entry_id, obj) in complexes:
        kind = KINDS[obj.kind]
        if obj.on is not None:
            things = _on_surface(builder, entry_id, obj, kind)
        elif obj.at is not None:
            things = _at_point(builder, entry_id, obj, kind)
        else:
            things = builder.scatter_complexes(entry_id, obj, kind, _resolve_in(builder, entry_id, obj, kind))
        builder.add(entry_id, obj, things)
    world = builder.world()
    return CellWorld(world.kind, world.cell, world.placed, world.entries, _neighbours(builder), spec.seed)


def _defaults(builder: _Builder, kind: Kind, spec: ObjectSpec) -> list[Point | None]:
    """Default places of the typical layout (``None``: scattered)."""
    if spec.at is not None:
        return []
    if kind.name == "nucleus":
        return [(-0.12 * builder.cell.a, 0.08 * builder.cell.b)]
    if kind.name == "nucleolus" and builder.nuclei():
        nucleus = builder.nuclei()[0]
        return [(nucleus.center[0] + 0.22 * nucleus.size / 2, nucleus.center[1] + 0.18 * nucleus.width / 2)]
    if kind.name == "centrosome":
        return [builder.beside_nucleus(0.8, math.radians(32.0))]
    return []


def _generated(builder: _Builder, entries: list[tuple[str, ObjectSpec]]) -> None:
    """Nuclear pores on each nucleus, ribosomes on the outer nuclear membrane and the rough ER."""
    for entry_id, obj in entries:
        if obj.kind == "nucleus" and obj.pores is not False:
            for nucleus in builder.world().members(entry_id):
                outer, inner = nucleus.parts[0].membranes[0][1], nucleus.parts[0].membranes[1][1]
                assert isinstance(outer, Ellipse) and isinstance(inner, Ellipse)
                middle = Ellipse(outer.cx, outer.cy, (outer.a + inner.a) / 2, (outer.b + inner.b) / 2, outer.angle)
                pore_spec = ObjectSpec("nuclear_pore", where=obj.where)
                points = middle.surface(1.0 / PORES_PER_UM, 0.25)
                builder.add(f"{nucleus.key}.pores", pore_spec, builder.place_bound(f"{nucleus.key}.pores", pore_spec, KINDS["nuclear_pore"],
                                                                                   nucleus, points), owner=entry_id)
        if obj.kind in ("nucleus", "rough_er") and obj.ribosomes is not False:
            for host in builder.world().members(entry_id):
                density = ER_RIBOSOMES_PER_UM / (2.0 if obj.kind == "nucleus" else 1.0)
                pores = [p.center for p in builder.placed if p.surface == host.key and p.kind == "nuclear_pore"]
                points = builder.surface_points(host, 1.0 / density, avoid=pores)
                ribo_spec = ObjectSpec("ribosome", where=obj.where)
                builder.add(f"{host.key}.ribosomes", ribo_spec, builder.place_bound(f"{host.key}.ribosomes", ribo_spec, KINDS["ribosome"], host, points),
                            owner=entry_id)


def _on_surface(builder: _Builder, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    entries = {e.id: e for e in builder.entries if e.owner is None}
    if spec.on not in entries:
        raise _fail(spec, entry_id, f"on: '{spec.on}' is not an object of this cell{did_you_mean(spec.on or '', list(entries))}")
    host_kind = KINDS[entries[spec.on].kind]
    if host_kind.name not in kind.surfaces:
        allowed = " or ".join(noun(KINDS[k].label) for k in sorted(kind.surfaces))
        raise _fail(spec, entry_id, f"a {noun(kind.label)} cannot sit on a {noun(host_kind.label)} (only on a {allowed}): {kind.why}")
    hosts = builder.world().members(spec.on)
    rng = builder.rng(entry_id, "on")
    points: list[tuple[Point, Point]] = []
    taken = [p.center for p in builder.placed if p.surface in {h.key for h in hosts}]
    for host in hosts:
        points += builder.surface_points(host, 0.05, avoid=taken, clearance=0.04)
    rng.shuffle(points)
    if len(points) < spec.count:
        raise _fail(spec, entry_id, f"only {len(points)} free places on '{spec.on}' for {spec.count}; use a smaller count")
    chosen = sorted(points[: spec.count])
    host = hosts[0]
    return builder.place_bound(entry_id, spec, kind, host, chosen)


def _at_point(builder: _Builder, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    assert spec.at is not None
    world = builder.world()
    compartment, instance = world.compartment_at(spec.at)
    if spec.inside is not None:
        wanted = _resolve_in(builder, entry_id, spec, kind)
        if not any(compartment == c and (owner is None or instance.startswith(owner.key + ".")) for c, owner in wanted):
            raise _fail(spec, entry_id, f"at {_at_text(spec.at)} is in the {_instance_words(instance)}, not in {spec.inside}; "
                                        "move it or change in")
    if compartment not in kind.places:
        raise _fail(spec, entry_id, f"at {_at_text(spec.at)}: that point is in the {_instance_words(instance)}; {kind.why}")
    size = spec.size or kind.size
    width = spec.width or (kind.width or size)
    angle = math.radians(spec.angle or 0.0)
    p = spec.at
    return [Placed(entry_id, entry_id, kind.name, p, size, width, angle, (Ellipse(p[0], p[1], size / 2, width / 2, angle),), (), instance)]


def _neighbours(builder: _Builder) -> tuple[Neighbour, ...]:
    """Cells of the tissue round the cell: two rings on a hexagonal lattice (stretched to the
    cell's shape), a little jittered, each with its nucleus."""
    a, b = builder.cell.a, builder.cell.b
    out = []
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
            cell = Ellipse(cx, cy, a * scale, b * scale * rng.uniform(0.92, 1.05), rng.uniform(-0.25, 0.25))
            nucleus = Ellipse(cx + rng.uniform(-0.2, 0.2) * a, cy + rng.uniform(-0.2, 0.2) * b, 0.33 * a * scale, 0.29 * a * scale,
                              rng.uniform(0, math.pi))
            out.append(Neighbour(cell, nucleus))
    return tuple(out)
