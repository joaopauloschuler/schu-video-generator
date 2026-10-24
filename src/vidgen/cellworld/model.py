"""The cell world (DESIGN.md §95): a cross-section of a cell as plain data — the cell (animal,
plant or bacterium) with its envelope, the structures, filaments and complexes placed in it with
real sizes in µm, the compartments and membranes they make. Built from a :class:`CellSpec` by
:func:`~.build.build_cell_world`, which applies the location rules and refuses what is
impossible with a :class:`VidgenError` that says what to write instead. No manim: ``vidgen
validate`` runs it, renderers draw it."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Literal

from vidgen.errors import VidgenError

from .catalog import COMPARTMENTS, KINDS, Kind
from .geometry import Ellipse, Point, Shape

#: Names an object may not take: the scene's own targets and the cytosol / extracellular space.
RESERVED_IDS = frozenset({"cell", "title", "tissue", "scale_bar", "cytosol", "extracellular", "world"})


@dataclass(frozen=True)
class ObjectSpec:
    """One ``objects`` entry as the model reads it (the scene's params give these): ``kind``,
    ``id``, ``at`` (µm from the cell's centre, x right, y up), ``size`` (its length, µm),
    ``width``, ``angle`` (degrees), ``inside`` (YAML ``in``), ``on`` (a structure whose membrane,
    or a filament, it sits on), ``count``; kind options (``sheets``, ``span``, ``side`` of the
    rough ER, ``cisternae`` of the Golgi, ``tubules`` of the smooth ER, ``pores`` and
    ``ribosomes`` of the nucleus and the rough ER, ``coat`` of a vesicle, ``cargo`` of a motor,
    ``grana`` of a chloroplast); ``style`` (``section`` or ``surface``, for the drawing);
    a molecule's ``state`` and, for one in a membrane, the ``membrane`` of its ``on`` object it
    is in and the compartment its oriented part ``faces``; ``where`` names it in error
    messages (``objects[2]``)."""

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
    coat: str | None = None
    cargo: bool | None = None
    grana: int | None = None
    style: str | None = None
    state: str | None = None
    faces: str | None = None
    membrane: str | None = None


@dataclass(frozen=True)
class CellSpec:
    """The cell: its ``kind`` (animal, plant, bacterium), ``size`` (long axis, µm; ``None``: the
    kind's typical size) and ``aspect`` (long over short), the ``contents`` it starts with
    (``typical`` or ``none``), the ``objects`` added (an object with the id of a typical one
    replaces it) and the ``seed`` of automatic placement; a bacterium's ``gram`` stain
    (``negative``: inner and outer membrane with the periplasm between; ``positive``: a thick
    wall) and ``capsule``; a plant cell's ``wall`` thickness (µm) and ``plasmodesmata``; the
    ``style`` structures are drawn in unless an object says otherwise (``section`` or
    ``surface``)."""

    kind: str = "animal"
    size: float | None = None
    aspect: float | None = None
    contents: Literal["typical", "none"] = "typical"
    objects: tuple[ObjectSpec, ...] = ()
    seed: int = 1
    gram: Literal["negative", "positive"] = "negative"
    capsule: bool = False
    wall: float | None = None
    plasmodesmata: bool = True
    style: Literal["section", "surface"] = "section"


@dataclass(frozen=True)
class Part:
    """A membrane-bounded piece of a placed thing (a nucleus has one with two membranes; a
    rough ER one for its joined sheets): ``membranes`` from the outside in, each ``(name,
    shape)``, and ``interior``: the compartment inside each membrane (``interior[k]`` lies
    inside membrane ``k`` and outside membrane ``k + 1``)."""

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
    compartment instance such as ``cytosol`` or ``nucleus.nucleoplasm``), the structure or
    filament it sits on (``surface``) with the outward ``normal`` there, ``facing``: a Golgi
    stack's cis direction or a motor's walking direction (radians), ``joined``: the structures
    whose membranes it is continuous with (the rough ER with the nucleus), and ``options``:
    drawing details (a vesicle's coat, a Golgi's buds, a motor's filament)."""

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
    joined: tuple[str, ...] = ()
    options: tuple[tuple[str, Any], ...] = ()

    @property
    def info(self) -> Kind:
        return KINDS[self.kind]

    def option(self, name: str, default: Any = None) -> Any:
        """A drawing option (``coat``, ``buds``, ``style``…)."""
        return dict(self.options).get(name, default)

    def contains(self, p: Point, pad: float = 0.0) -> bool:
        return any(s.contains(p, pad) for s in self.footprint)

    def compartment_at(self, p: Point) -> str | None:
        """The compartment of this thing that ``p`` lies in (``None``: outside it, or it has no
        membrane). Inner parts (thylakoids, intraluminal vesicles) are asked first."""
        for part in reversed(self.parts):
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
    """A neighbouring cell of the tissue (or colony) round the cell: its outline, its nucleus
    (none for a bacterium) and, for a plant cell, the outer face of its wall."""

    cell: Shape
    nucleus: Shape | None
    wall: Shape | None = None


@dataclass(frozen=True)
class CellWorld:
    """A built cell world (µm, the cell's centre at the origin). ``cell`` is its plasma membrane
    (a bacterium's inner membrane); ``envelope`` the layers outside it, inner first, each
    ``(compartment, its outer face)`` (a plant's wall; a bacterium's periplasm or wall, and its
    capsule); ``membranes`` the cell's own membranes (``(name, shape)``); ``channels`` the
    plasmodesmata through a plant cell's wall (cytosol inside)."""

    kind: str
    cell: Shape
    placed: tuple[Placed, ...]
    entries: tuple[Entry, ...]
    neighbours: tuple[Neighbour, ...]
    seed: int
    envelope: tuple[tuple[str, Shape], ...] = ()
    membranes: tuple[tuple[str, Shape], ...] = ()
    channels: tuple[Shape, ...] = ()
    gram: str | None = None
    _by_key: dict[str, Placed] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._by_key.update({p.key: p for p in self.placed})

    @property
    def size(self) -> float:
        """The cell's long axis (µm)."""
        x0, y0, x1, y1 = self.cell.bounds()
        return max(x1 - x0, y1 - y0)

    @property
    def outside(self) -> Shape:
        """The outer face of the cell's envelope (the plasma membrane when it has none)."""
        return self.envelope[-1][1] if self.envelope else self.cell

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

    def filaments(self) -> list[Placed]:
        return [p for p in self.placed if KINDS[p.kind].category == "filament"]

    def compartment_at(self, p: Point) -> tuple[str, str]:
        """``(compartment kind, instance)`` at point ``p``: ``("nucleoplasm",
        "nucleus.nucleoplasm")``, ``("cytosol", "cytosol")``, ``("cell_wall", "cell_wall")``,
        ``("extracellular", "extracellular")``."""
        if not self.cell.contains(p):
            if any(c.contains(p) for c in self.channels):
                return ("cytosol", "cytosol")
            for name, shape in self.envelope:
                if shape.contains(p):
                    return (name, name)
            return ("extracellular", "extracellular")
        for thing in self.structures():
            found = thing.compartment_at(p)
            if found is not None:
                return (found, f"{thing.key}.{found}")
        return ("cytosol", "cytosol")

    def region_at(self, p: Point) -> Placed | None:
        """The structure without a membrane (a nucleolus, a centrosome, a nucleoid) whose region
        holds ``p``."""
        for thing in self.structures():
            if not thing.parts and thing.contains(p):
                return thing
        return None

    def tissue_bounds(self) -> tuple[float, float, float, float]:
        """Bounds of the cell and its neighbours (µm)."""
        shapes = [self.outside] + [n.wall or n.cell for n in self.neighbours]
        boxes = [s.bounds() for s in shapes]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def noun(label: str) -> str:
    """A label inside a sentence: ``rough ER``, ``mitochondrion``, ``Golgi apparatus``, ``ER lumen``."""
    if label.startswith("Golgi") or len(label) > 1 and label[1].isupper() or label.startswith(("cis", "trans")):
        return label
    return label[0].lower() + label[1:]


def did_you_mean(name: str, known: list[str] | tuple[str, ...]) -> str:
    """``; did you mean 'x'?`` for the closest of ``known`` (empty when none is close)."""
    close = difflib.get_close_matches(name, list(dict.fromkeys(known)), n=2, cutoff=0.5)
    return f"; did you mean {' or '.join(repr(c) for c in close)}?" if close else ""


def where_text(spec: ObjectSpec, entry_id: str) -> str:
    kind = noun(KINDS[spec.kind].label) if spec.kind in KINDS else spec.kind
    return f"{spec.where} ({kind} '{entry_id}')" if spec.where else f"{kind} '{entry_id}'"


def fail(spec: ObjectSpec, entry_id: str, message: str) -> VidgenError:
    """The error of object ``entry_id``: where it was written, then ``message``."""
    return VidgenError(f"{where_text(spec, entry_id)}: {message}")


def at_text(p: Point) -> str:
    return f"[{p[0]:g}, {p[1]:g}] µm"


def instance_words(instance: str) -> str:
    """``nucleoplasm of 'nucleus'`` for ``nucleus.nucleoplasm``; ``cytosol`` for ``cytosol``."""
    if "." not in instance:
        return noun(COMPARTMENTS[instance].label) if instance in COMPARTMENTS else instance
    key, compartment = instance.rsplit(".", 1)
    return f"{noun(COMPARTMENTS[compartment].label)} of '{key}'"


def round_cell(size: float, aspect: float) -> Ellipse:
    """An animal cell's outline."""
    return Ellipse(0.0, 0.0, size / 2, size / 2 / aspect)
