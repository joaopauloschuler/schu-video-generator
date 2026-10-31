"""Sitting on, lying on and using the objects of an isometric place (DESIGN.md §105.2): where
each object's seats are, which way one sits on them, which of its parts stand in front of who sits
there, how one uses an object, and the checks ``vidgen validate`` replays. Plain data and pure
functions, no manim, like :mod:`vidgen.world.iso_moves` for walks.

Seats, beds and uses are given in an object's own frame (as its drawing is): ``a`` across its front
and ``b`` from its back to its front, as shares of its footprint (so a longer bench keeps its
places spread), ``z`` up from its base (tile units). An object facing ``right`` mirrors the frame
(``a`` along the map's rows, ``b`` along its columns). A seat *faces* the way one sitting there
looks: ``front`` (out of the object's front, towards the viewer's lower left or right), ``back``
(a school desk's chair faces its desk), ``+a`` or ``-a`` (a café table's two chairs face each
other). Its *front* regions are rectangles of the frame (``a0, b0, a1, b1``, shares): a shape of
the object lying wholly inside one (an armchair's near arm, a bus shelter's near pane, a
blanket) is drawn over the sitter.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vidgen.cartoon.seating import PostureError, Postures
from vidgen.world.iso import IsoObject, IsoPlace

Cell = tuple[int, int]
Point3 = tuple[float, float, float]
#: ``(a0, b0, a1, b1)`` shares of the frame, or with a fifth number: up to that height (tile units
#: over the object's base) only (a bus shelter's front posts, not its roof).
Region = tuple[float, ...]


@dataclass(frozen=True)
class IsoSeat:
    """One place to sit on an object: where the hips rest (``a``, ``b`` shares of the footprint,
    ``z`` tile units over the object's base), the way the sitter faces and the parts of the
    object drawn over the sitter (``front`` regions)."""

    a: float
    b: float
    z: float
    faces: str = "front"
    front: tuple[Region, ...] = ()


@dataclass(frozen=True)
class IsoBed:
    """Where one lies on a bed: across it at ``a``, the head towards its back (the top of the
    head at ``head``, a share of its depth), on its mattress ``z`` over its base; the ``front``
    regions (its blanket, its foot board) are drawn over who lies there."""

    a: float
    head: float
    z: float
    front: tuple[Region, ...] = ()


@dataclass(frozen=True)
class IsoUse:
    """How one uses an object: ``style`` (``type`` at keys, ``warm`` the hands at a fire,
    ``read`` a shelf's books, ``reach`` to press, pour or turn) and the object's own place for
    the hands (``a``, ``b`` shares, ``z`` tile units over its base; :func:`use_point`)."""

    style: str
    a: float
    b: float
    z: float


_NEAR_ARM: Region = (0.68, 0.0, 1.0, 1.0)
#: The seats of each object one can sit on (the kinds of :data:`~vidgen.world.iso.OBJECT_KINDS`),
#: as drawn (DESIGN.md §104).
ISO_SEATS: dict[str, tuple[IsoSeat, ...]] = {
    "chair": (IsoSeat(0.5, 0.52, 0.63),),
    "bench": (IsoSeat(0.3, 0.58, 0.55), IsoSeat(0.7, 0.58, 0.55)),
    "sofa": (IsoSeat(0.3, 0.62, 0.55, front=((0.84, 0.0, 1.0, 1.0),)), IsoSeat(0.7, 0.62, 0.55, front=((0.84, 0.0, 1.0, 1.0),))),
    "armchair": (IsoSeat(0.5, 0.6, 0.58, front=(_NEAR_ARM,)),),
    "throne": (IsoSeat(0.5, 0.6, 0.62, front=((0.72, 0.0, 1.0, 1.0),)),),
    "lab_stool": (IsoSeat(0.5, 0.5, 0.72),),
    "log": (IsoSeat(0.3, 0.54, 0.5), IsoSeat(0.7, 0.54, 0.5)),
    "stump": (IsoSeat(0.5, 0.5, 0.57),),
    "hay_bale": (IsoSeat(0.3, 0.55, 0.72), IsoSeat(0.7, 0.55, 0.72)),
    "rock": (IsoSeat(0.5, 0.55, 0.5),),
    "bus_stop": tuple(IsoSeat(a, 0.45, 0.55, front=((0.9, 0.0, 1.0, 1.0, 2.2), (0.0, 0.7, 1.0, 1.2, 2.2))) for a in (0.33, 0.67)),
    "school_desk": (IsoSeat(0.5, 0.71, 0.48, faces="back", front=((0.0, 0.84, 1.0, 1.0),)),),
    "cafe_table": (IsoSeat(0.15, 0.5, 0.56, faces="+a", front=((0.27, 0.0, 1.0, 1.0),)), IsoSeat(0.85, 0.5, 0.56, faces="-a", front=((0.91, 0.0, 1.0, 1.0),))),
    "bed": (IsoSeat(0.75, 0.6, 0.58, faces="+a"),),
}
#: The objects one lies on (``lie_on``).
ISO_BEDS: dict[str, IsoBed] = {"bed": IsoBed(0.5, 0.1, 0.58, front=((0.0, 0.39, 1.0, 1.1),))}
#: How one uses each object that can be used (``use``).
ISO_USES: dict[str, IsoUse] = {
    **{kind: IsoUse("type", 0.5, b, z) for kind, b, z in (("laptop", 0.75, 0.8), ("console", 0.9, 0.87), ("terminal_kiosk", 0.5, 1.1),
                                                      ("cash_register", 0.84, 1.25), ("piano", 0.75, 0.9))},
    "desk_with_pc": IsoUse("type", 0.42, 0.66, 0.82),
    **{kind: IsoUse("warm", 0.5, b, z) for kind, b, z in (("campfire", 0.5, 0.55), ("fireplace", 1.0, 0.6))},
    **{kind: IsoUse("read", 0.5, b, 1.3) for kind, b in (("bookshelf_tall", 0.6), ("shelf", 0.6), ("trophy_shelf", 0.6), ("newsstand", 0.8))},
    **{kind: IsoUse("reach", 0.5, b, z) for kind, b, z in (
        ("stove", 0.85, 0.95), ("sink", 0.8, 1.0), ("coffee_machine", 0.9, 1.05), ("vending_machine", 0.9, 1.1), ("water_cooler", 0.8, 1.0),
        ("microscope", 0.6, 1.05), ("chemistry_bench", 0.8, 0.95), ("cauldron", 0.5, 1.25), ("globe", 0.5, 1.1), ("printer", 0.7, 1.1),
        ("mailbox", 0.6, 1.2), ("telescope", 0.5, 1.4), ("kitchen_counter", 0.85, 1.0), ("counter", 0.85, 1.15))},
}
#: The actions of this module, replayed by :func:`~vidgen.world.iso_moves.iso_move_problems`.
ISO_SEAT_ACTIONS = frozenset({"sit_on", "lie_on", "stand_up", "use"})
#: How long sitting down on an object, lying down and using it take by default (seconds).
LIE_SECONDS = 1.2
USE_SECONDS = 3.0
#: How far (cells across, 8 neighbours) from an object's footprint a character sits, lies or uses
#: it without walking first.
SEAT_REACH = 1
#: How much smaller a character lying in bed is drawn (a cartoon bed is short for a whole
#: character; the legs lie under the blanket), and how far (degrees) its body turns to lie along
#: the bed on the picture (the map's axes rise 1 in 2 on it).
LIE_SCALE = 0.72
LIE_DEGREES = math.degrees(math.atan(2.0))


def _swap(item: IsoObject) -> bool:
    return item.facing == "right"


def frame_size(item: IsoObject) -> tuple[int, int]:
    """The object's footprint in its own frame: (across, back to front)."""
    return (item.depth, item.width) if _swap(item) else (item.width, item.depth)


def object_frame_point(item: IsoObject, base: float, a: float, b: float, z: float) -> Point3:
    """A point of the object's frame (``a``, ``b`` shares of its footprint, ``z`` tile units over
    its ``base``) in the world (tile units)."""
    w, d = frame_size(item)
    if _swap(item):
        return (item.column + b * d, item.row + a * w, base + z)
    return (item.column + a * w, item.row + b * d, base + z)


def in_frame(item: IsoObject, x: float, y: float) -> tuple[float, float]:
    """A world point's place in the object's frame: (``a``, ``b``) as shares of its footprint."""
    w, d = frame_size(item)
    if _swap(item):
        return ((y - item.row) / w, (x - item.column) / d)
    return ((x - item.column) / w, (y - item.row) / d)


def in_regions(item: IsoObject, base: float, regions: Sequence[Region], points: Sequence[Point3]) -> bool:
    """Whether every one of ``points`` (world) lies in one of the object's ``regions`` (the
    object standing on ``base``)."""
    if not points or not regions:
        return False
    framed = [(*in_frame(item, x, y), z - base) for x, y, z in points]
    for a0, b0, a1, b1, *top in regions:
        if all(a0 - 1e-6 <= a <= a1 + 1e-6 and b0 - 1e-6 <= b <= b1 + 1e-6 and (not top or z <= top[0] + 1e-6) for a, b, z in framed):
            return True
    return False


_WAYS = {"front": (0.0, 1.0), "back": (0.0, -1.0), "+a": (1.0, 0.0), "-a": (-1.0, 0.0)}


def seat_facing(item: IsoObject, seat: IsoSeat) -> str:
    """The way (``left`` / ``right`` on the picture) one sitting on ``seat`` of ``item`` faces."""
    da, db = _WAYS[seat.faces]
    dx, dy = (db, da) if _swap(item) else (da, db)
    return "right" if dx - dy > 0 else "left"


def bed_facing(item: IsoObject) -> str:
    """The way one lying in the bed ``item`` faces (its face up, its head on the pillow): the
    picture's left for a bed facing left (its head at the upper right), else right."""
    return "left" if not _swap(item) else "right"


def seat_hips(item: IsoObject, base: float, seat: IsoSeat) -> Point3:
    """Where the hips of one sitting on ``seat`` rest (world, tile units)."""
    return object_frame_point(item, base, seat.a, seat.b, seat.z)


def use_point(item: IsoObject, base: float, use: IsoUse, feet: Sequence[float]) -> Point3:
    """Where the hands of one using ``item`` with its feet at ``feet`` (world) go: half way
    between the object's own place for them (``use``: a laptop's keys, a fire) and the point of
    its footprint (a little inside it) nearest the user, at the use's height: one standing
    beside the object reaches to its side, not through it."""
    x, y, z = object_frame_point(item, base, use.a, use.b, use.z)
    margin = 0.1
    nx = min(max(float(feet[0]), item.column + margin), item.column + item.width - margin)
    ny = min(max(float(feet[1]), item.row + margin), item.row + item.depth - margin)
    return ((x + nx) / 2, (y + ny) / 2, z)


def footprint_apart(cell: Cell, item: IsoObject) -> int:
    """How many cells across (8 neighbours) ``cell`` is from the nearest cell of ``item``."""
    return min(max(abs(cell[0] - c), abs(cell[1] - r)) for c, r in item.cells())


def seat_order(item: IsoObject, base: float, feet: Sequence[float]) -> list[int]:
    """The seats of ``item`` nearest first to ``feet`` (world): where one coming from there sits."""
    seats = ISO_SEATS.get(item.kind, ())
    return sorted(range(len(seats)), key=lambda k: (math.dist(seat_hips(item, base, seats[k])[:2], tuple(feet)[:2]), k))


def object_uses_hint(kind: str) -> str:
    """What one can do with an object of ``kind`` (sit, lie, use), for an error's hint."""
    found = [verb for verb, table in (("sit_on", ISO_SEATS), ("lie_on", ISO_BEDS), ("use", ISO_USES)) if kind in table]
    return f"(one can {' or '.join(found)} it)" if found else "(nothing to sit on, lie on or use)"


def kinds_words(table: Mapping[str, object]) -> str:
    return ", ".join(sorted(table))


def next_to(place: IsoPlace, item: IsoObject, near: Cell, crowd: Collection[Cell] = ()) -> Cell | None:
    """A free cell next to ``item`` to walk to before sitting on, lying on or using it: the one
    nearest ``near`` (``None``: none)."""
    best: tuple[tuple[float, int, int], Cell] | None = None
    for c in range(item.column - 1, item.column + item.width + 1):
        for r in range(item.row - 1, item.row + item.depth + 1):
            if (c, r) in item.cells() or (c, r) in crowd or not place.is_standable(c, r):
                continue
            key = (math.dist((c, r), near), -(c + r), c)
            if best is None or key < best[0]:
                best = (key, (c, r))
    return None if best is None else best[1]


_VERBS = {"sit_on": "sit on it", "lie_on": "lie on it", "use": "use it"}


def seat_step_problem(place: IsoPlace, postures: Postures, who: str, cell: Cell, step: Any) -> str | None:
    """Replay one ``sit_on``, ``lie_on``, ``stand_up`` or ``use`` of ``who`` standing in ``cell``
    (a :class:`~vidgen.world.iso_moves.IsoStep`) on ``postures``: why it cannot happen then
    (``None``: it can). One sits, lies or uses an object from a cell next to it (a character
    sitting uses what is next to its seat: a laptop on the desk in front of its chair); two
    cannot sit on one seat, nor anyone on a bed somebody lies on. An object that is not there or
    has nothing to sit on is the action's own check."""
    if step.action == "stand_up":
        try:
            postures.stand(who)
        except PostureError as exc:
            return str(exc)
        return None
    name = str(step.options.get("to"))
    item = next((o for o in place.objects if o.name == name), None)
    table: Mapping[str, object] = {"sit_on": ISO_SEATS, "lie_on": ISO_BEDS, "use": ISO_USES}[step.action]
    if item is None or item.kind not in table:
        return None
    now = postures.of(who)
    if step.action == "use" and now is not None and now[0] == "lying":
        return f"{who} lies on '{now[1]}' then; stand_up first (- stand_up: {who})"
    seat = next((o for o in place.objects if now is not None and o.name == now[1]), None)
    froms = seat.cells() if step.action == "use" and seat is not None else [cell]
    apart = min(footprint_apart(c, item) for c in froms)
    if apart > SEAT_REACH:
        near = next_to(place, item, cell)
        hint = f"walk_to first (- walk_to: {who}, to: {{column: {near[0] + 1}, row: {near[1] + 1}}})" if near else "no free cell is next to it"
        return f"'{who}' is {apart} cells from '{name}'; it must be next to it to {_VERBS[step.action]}: {hint}"
    try:
        if step.action == "sit_on":
            postures.sit(who, name, len(ISO_SEATS[item.kind]))
        elif step.action == "lie_on":
            postures.lie(who, name)
    except PostureError as exc:
        return str(exc)
    return None


__all__ = [
    "ISO_BEDS",
    "IsoBed",
    "ISO_SEAT_ACTIONS",
    "LIE_DEGREES",
    "LIE_SCALE",
    "LIE_SECONDS",
    "ISO_SEATS",
    "SEAT_REACH",
    "IsoSeat",
    "ISO_USES",
    "USE_SECONDS",
    "IsoUse",
    "bed_facing",
    "footprint_apart",
    "object_frame_point",
    "frame_size",
    "in_frame",
    "in_regions",
    "kinds_words",
    "next_to",
    "seat_facing",
    "seat_order",
    "seat_hips",
    "seat_step_problem",
    "use_point",
    "object_uses_hint",
]
