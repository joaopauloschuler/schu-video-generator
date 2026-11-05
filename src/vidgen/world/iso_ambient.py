"""Ambient life on an iso place (DESIGN.md §105.7): the rules of where the background creatures
go and what they do, without manim. Walkers wander between spots and along paths, birds peck,
hop and fly off, a cat strolls and sits down to groom, ducks glide on the water, butterflies
flutter from flower to flower, fireflies hover and blink, a fly buzzes about a room.

Each creature has an :class:`AmbientPlan`: its moves one after the other (:class:`AmbientMove`),
made as far as they are asked for (:meth:`AmbientPlan.at`) from a seeded random generator, so the
same seed gives the same life on every render. They keep to the cells of an
:class:`AmbientCells` (:func:`ambient_cells`): never the cells where the main characters stand or
go, their seats, the roads cars drive on or a train's track.
"""

from __future__ import annotations

import bisect
import heapq
import math
import random
import zlib
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass

from vidgen.world.iso import BLOCK, FLOOR, PATH, VOID, WALLS, WATER, OBJECT_KINDS, IsoPlace
from vidgen.world.iso_moves import NEIGHBOURS, can_step

Cell = tuple[int, int]
Point3 = tuple[float, float, float]

#: The kinds of creatures, the ones that live indoors too, and the config's key for each.
AMBIENT_KINDS: tuple[str, ...] = ("walker", "bird", "cat", "duck", "butterfly", "firefly", "fly")
INDOOR_KINDS: frozenset[str] = frozenset({"cat", "fly"})
AMBIENT_KEYS: dict[str, str] = {"walkers": "walker", "birds": "bird", "cat": "cat", "ducks": "duck", "butterflies": "butterfly",
                                "fireflies": "firefly", "flies": "fly"}
#: How many of each a ``true`` gives, and the most a scene may have.
AMBIENT_DEFAULTS: dict[str, int] = {"walkers": 3, "birds": 4, "cat": 1, "ducks": 2, "butterflies": 3, "fireflies": 10, "flies": 1}
AMBIENT_MAX: dict[str, int] = {"walkers": 8, "birds": 8, "cat": 1, "ducks": 4, "butterflies": 6, "fireflies": 16, "flies": 3}
#: How fast each goes (tiles per second): a main character walks about 1.4.
AMBIENT_SPEEDS: dict[str, float] = {"walker": 0.95, "cat": 0.75, "duck": 0.3, "bird": 3.2, "butterfly": 0.8, "fly": 1.6}
#: Objects no higher than this (tile units) are flown over low (flowers, a bush, a fence).
LOW_OBJECT = 1.2
#: Where butterflies settle and fireflies gather.
BLOOM_KINDS: frozenset[str] = frozenset({"flowers", "bush", "plant"})
GREEN_KINDS: frozenset[str] = frozenset({"flowers", "bush", "plant", "tree", "pine"})
#: How often a plan is sampled to find where a creature goes on screen over a while (seconds).
PLAN_STEP = 0.2


@dataclass(frozen=True)
class AmbientCells:
    """Where the creatures of a place may be: ``walk`` (walkers, the cat, birds on the ground),
    ``paths`` (the walk cells that are paths: walkers keep to them), ``rest`` (where they may
    stop: away from the main characters), ``water`` (ducks), ``air``
    (cells with nothing higher than :data:`LOW_OBJECT` on them: butterflies, fireflies and flies
    fly there), ``blooms`` (flowers, bushes, plants: butterflies settle on them), ``green``
    (blooms and trees: fireflies gather near them), ``spots`` (the place's spots among the walk
    cells: walkers stroll between them) and the place's size."""

    walk: frozenset[Cell]
    paths: frozenset[Cell]
    water: frozenset[Cell]
    air: frozenset[Cell]
    blooms: tuple[Cell, ...]
    green: tuple[Cell, ...]
    spots: tuple[Cell, ...]
    columns: int
    rows: int
    #: the walk cells where one may stop (not near the main characters)
    rest: frozenset[Cell] = frozenset()


def around(cells: Iterable[Cell], radius: int = 1) -> set[Cell]:
    """``cells`` and every cell within ``radius`` of one (8 neighbours), and the three cells two
    in front of each on the picture (who stands there would hide its legs)."""
    found: set[Cell] = set()
    for c, r in cells:
        found |= {(c + dc, r + dr) for dc in range(-radius, radius + 1) for dr in range(-radius, radius + 1)}
        found |= {(c + 2, r + 2), (c + 1, r + 2), (c + 2, r + 1)}
    return found


def ambient_cells(place: IsoPlace, *, avoid: Collection[Cell] = (), roads: Collection[Cell] = (), clear: Collection[Cell] = ()) -> AmbientCells:
    """The cells of ``place`` its creatures may use: never those in ``avoid`` (where the main
    characters stand and go, next to the seats they use) nor, on foot, ``roads`` (where a car
    drives, a train's track); they pass through ``clear`` but never stop there (round the main
    characters: one standing right behind a character would show over its shoulders)."""
    avoid, roads, clear = set(avoid), set(roads), set(clear)
    walk, paths, water, air = set(), set(), set(), set()
    blooms, green = [], []
    for r in range(place.rows):
        for c in range(place.columns):
            ground = place.ground(c, r)
            if ground == VOID or ground in WALLS:
                continue
            item = place.object_at(c, r)
            if item is not None and item.kind in BLOOM_KINDS:
                blooms.append((c, r))
            if item is not None and item.kind in GREEN_KINDS:
                green.append((c, r))
            if (c, r) in avoid:
                continue
            if item is None or item.height <= LOW_OBJECT:
                air.add((c, r))
            if ground == WATER and item is None:
                water.add((c, r))
            elif ground in (FLOOR, PATH, BLOCK) and (c, r) not in roads and place.is_standable(c, r) and (item is None or item.walkable):
                walk.add((c, r))
                if ground == PATH:
                    paths.add((c, r))
    spots = tuple(sorted({(spot.column, spot.row) for spot in place.spots} & walk - clear))
    return AmbientCells(frozenset(walk), frozenset(paths), frozenset(water), frozenset(air), tuple(blooms), tuple(green), spots,
                        place.columns, place.rows, frozenset(walk - clear))


def ambient_seed(seed: int, name: str) -> int:
    """The seed of one creature (``name``) of a scene's ambient life of ``seed``."""
    return zlib.crc32(f"{seed}/{name}".encode("utf-8"))


@dataclass(frozen=True)
class AmbientPose:
    """Where a creature is at a moment and what it does: its ``point`` (tile units: its feet, or
    its middle in the air), ``facing`` (1: to the right on the picture, -1: to the left),
    ``action`` (``stand``, ``walk``, ``sit``, ``groom``, ``peck``, ``hop``, ``fly``, ``swim``,
    ``dip``, ``rest``, ``flutter``, ``hover``), ``phase`` (seconds into it; a walk: the distance
    walked), ``shown`` (0..1: fading in and out at the place's edge) and ``glow`` (a firefly's
    light, 0..1)."""

    point: Point3
    facing: int
    action: str
    phase: float
    shown: float = 1.0
    glow: float = 1.0


@dataclass(frozen=True)
class AmbientMove:
    """One move of a creature: from scene time ``start`` for ``seconds``, ``action`` along
    ``points`` (one point: it stays there), ``facing`` while it stays, ``arc``: how high a hop or a
    flight rises over the line between its ends (tile units), ``fade``: ``in`` or ``out`` over the
    move (flying in or out of the place), ``gone`` while away."""

    start: float
    seconds: float
    action: str
    points: tuple[Point3, ...]
    facing: int = 1
    arc: float = 0.0
    fade: str = ""

    @property
    def end(self) -> float:
        return self.start + self.seconds

    @property
    def length(self) -> float:
        return sum(math.dist(a[:2], b[:2]) for a, b in zip(self.points, self.points[1:]))


def picture_facing(a: Sequence[float], b: Sequence[float], before: int) -> int:
    """Which way one moving from ``a`` to ``b`` faces on the picture (``before`` when straight up
    or down it)."""
    du = (b[0] - a[0]) - (b[1] - a[1])
    return before if abs(du) < 1e-9 else (1 if du > 0 else -1)


def _along(points: Sequence[Point3], distance: float) -> tuple[Point3, int]:
    """The point ``distance`` along ``points`` and the leg it is on."""
    for k, (a, b) in enumerate(zip(points, points[1:])):
        leg = math.dist(a[:2], b[:2])
        if distance <= leg or k == len(points) - 2:
            s = min(max(distance / leg, 0.0), 1.0) if leg > 0 else 1.0
            return (a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, a[2] + (b[2] - a[2]) * s), k
        distance -= leg
    return points[-1], 0


def _ease(s: float) -> float:
    s = min(max(s, 0.0), 1.0)
    return s * s * (3.0 - 2.0 * s)


def cell_route(ok: Collection[Cell], start: Cell, goal: Cell, *, place: IsoPlace | None = None,
               cost: Callable[[Cell], float] | None = None) -> list[Cell] | None:
    """The cheapest way from ``start`` to ``goal`` over the cells ``ok`` (8 neighbours, a
    diagonal only past two cells of ``ok``; with ``place``, steps of one only, as one walks:
    :func:`~vidgen.world.iso_moves.can_step`); ``cost(cell)``: entering a cell (default 1).
    ``None``: no way."""
    best: dict[Cell, float] = {start: 0.0}
    came: dict[Cell, Cell] = {}
    queue: list[tuple[float, int, Cell]] = [(0.0, 0, start)]
    order = 0
    while queue:
        spent, _, cell = heapq.heappop(queue)
        if cell == goal:
            path = [cell]
            while cell in came:
                cell = came[cell]
                path.append(cell)
            return path[::-1]
        if spent > best.get(cell, math.inf):
            continue
        for dc, dr in NEIGHBOURS:
            there = (cell[0] + dc, cell[1] + dr)
            if there not in ok:
                continue
            if dc and dr and ((cell[0] + dc, cell[1]) not in ok or (cell[0], cell[1] + dr) not in ok):
                continue
            if place is not None and not can_step(place, cell, there):
                continue
            step = (math.sqrt(2.0) if dc and dr else 1.0) * (cost(there) if cost is not None else 1.0)
            if spent + step < best.get(there, math.inf) - 1e-12:
                best[there] = spent + step
                came[there] = cell
                order += 1
                heapq.heappush(queue, (spent + step, order, there))
    return None


class AmbientPlan:
    """What one creature of the place (``kind``, :data:`AMBIENT_KINDS`, named ``name``) does over a
    scene: its moves, made one after the other from ``seed`` as far as they are asked for, in
    the cells ``cells`` of ``place``. :meth:`at` gives its pose at a scene time."""

    def __init__(self, kind: str, name: str, place: IsoPlace, cells: AmbientCells, seed: int, *, index: int = 0, of: int = 1) -> None:
        self.kind, self.name, self.place, self.cells = kind, name, place, cells
        self.rng = random.Random(seed)
        #: which of how many of its kind it is (they start spread out across the place)
        self.index, self.of = index, of
        self.moves: list[AmbientMove] = []
        self._starts: list[float] = []
        #: the cells it may pass through, and those it may stop on
        self.passable = frozenset(cells.water if kind == "duck" else cells.walk)
        self.ground = sorted(cells.water if kind == "duck" else (cells.rest or cells.walk))
        self.stops = frozenset(self.ground)
        self.offset = (self.rng.uniform(-0.18, 0.18), self.rng.uniform(-0.18, 0.18)) if kind in ("walker", "cat") else (0.0, 0.0)
        self.facing = self.rng.choice((-1, 1))
        #: a firefly's place and its drift and blink (it never moves on)
        self.anchor: Point3 | None = None
        self.waves = [self.rng.uniform(0.0, 2 * math.pi) for _ in range(6)]
        self.rates = [self.rng.uniform(0.35, 0.8) for _ in range(3)]
        self.blink = self.rng.uniform(2.2, 4.0)
        self._since_flight = 0.0
        self._flight_due = self.rng.uniform(5.0, 12.0)
        self._first()

    # ----- where it starts --------------------------------------------------------------------------

    def possible(self) -> bool:
        """Whether there is room for it on the place (a cell to stand on, water for a duck)."""
        if self.kind == "firefly":
            return self.anchor is not None
        if self.kind in ("butterfly", "fly"):
            return bool(self.cells.air)
        return bool(self.ground)

    def _point(self, cell: Cell, z: float | None = None) -> Point3:
        ox, oy = self.offset
        c, r = cell
        return (c + 0.5 + ox, r + 0.5 + oy, self.place.stand_z(c, r) if z is None else z)

    def _first(self) -> None:
        if self.kind == "firefly":
            spots = [cell for cell in self.cells.air if any((cell[0] + dc, cell[1] + dr) in set(self.cells.green)
                                                            for dc in (-1, 0, 1) for dr in (-1, 0, 1))]
            spots = sorted(spots) or sorted(self.cells.air)
            if spots:
                c, r = self.rng.choice(spots)
                self.anchor = (c + self.rng.uniform(0.3, 0.7), r + self.rng.uniform(0.3, 0.7), self.place.floor_z(c, r) + self.rng.uniform(0.35, 1.0))
            return
        if not self.possible():
            return
        if self.kind in ("butterfly", "fly"):
            cell = self.rng.choice(sorted(self._flower_cells() or self.cells.air))
            self._add(AmbientMove(0.0, self.rng.uniform(0.5, 2.0), "rest", (self._air_point(cell, rest=True),), self.facing))
            return
        pool = sorted(self._waypoints(), key=lambda cell: (cell[0] - cell[1], cell[1]))   # across the picture
        share = (self.index + self.rng.uniform(0.2, 0.8)) / max(self.of, 1)   # several spread out across it
        cell = pool[min(int(share * len(pool)), len(pool) - 1)]
        start = self._point(cell)
        action = {"walker": "stand", "cat": "sit", "duck": "swim", "bird": "peck"}[self.kind]
        if self.kind == "bird":
            start = (start[0] + self.rng.uniform(-0.3, 0.3), start[1] + self.rng.uniform(-0.3, 0.3), start[2])
        self._add(AmbientMove(0.0, self.rng.uniform(0.3, 2.5), action, (start,), self.facing))

    def _waypoints(self) -> list[Cell]:
        """Where it heads: a walker to the place's spots and along its paths, the others anywhere."""
        if self.kind == "walker":
            pool = sorted((set(self.cells.paths) & set(self.ground)) | set(self.cells.spots))
            if len(pool) >= 3:
                return pool
        return self.ground

    def _flower_cells(self) -> list[Cell]:
        return sorted(set(self.cells.blooms) | {cell for cell in self.cells.air if any(
            (cell[0] + dc, cell[1] + dr) in set(self.cells.blooms) for dc, dr in NEIGHBOURS)}) if self.cells.blooms else []

    def _air_point(self, cell: Cell, *, rest: bool = False) -> Point3:
        c, r = cell
        item = self.place.object_at(c, r)
        base = self.place.floor_z(c, r)
        if rest:
            top = item.height if item is not None and not item.walkable else 0.05
            return (c + 0.5, r + 0.5, base + top + 0.04)
        high = (1.0, 2.2) if self.kind == "fly" else (0.6, 1.3)
        return (c + self.rng.uniform(0.25, 0.75), r + self.rng.uniform(0.25, 0.75), base + max(self.rng.uniform(*high), (item.height + 0.3) if item else 0.0))

    # ----- the moves ---------------------------------------------------------------------------------

    def _add(self, move: AmbientMove) -> None:
        self.moves.append(move)
        self._starts.append(move.start)

    def _extend(self, until: float) -> None:
        guard = 0
        while self.moves and self.moves[-1].end <= until and guard < 10000:
            self._next(self.moves[-1])
            guard += 1

    def _next(self, last: AmbientMove) -> None:
        """Make the move after ``last``."""
        here = last.points[-1]
        t = last.end
        facing = picture_facing(last.points[-2], last.points[-1], last.facing) if len(last.points) > 1 else last.facing
        rng = self.rng
        if self.kind in ("walker", "cat", "duck"):
            if last.action in ("walk", "glide"):   # after a walk it stays a while
                if self.kind == "cat":
                    action, seconds = rng.choice((("sit", rng.uniform(3.0, 6.0)), ("groom", rng.uniform(2.5, 4.5)), ("stand", 0.8)))
                elif self.kind == "duck":
                    action, seconds = rng.choice((("swim", rng.uniform(2.0, 5.0)), ("dip", 1.6)))
                else:
                    action, seconds = "stand", rng.uniform(1.2, 4.0)
                    if rng.random() < 0.4:
                        facing = -facing   # it looks round
                self._add(AmbientMove(t, seconds, action, (here,), facing))
                return
            move = self._stroll(here, t, facing)
            if move is None:
                move = AmbientMove(t, 3.0, "stand" if self.kind == "walker" else ("swim" if self.kind == "duck" else "sit"), (here,), facing)
            self._add(move)
            return
        if self.kind == "bird":
            self._bird(last, here, t, facing)
            return
        self._flutter(last, here, t, facing)

    def _cell_of(self, point: Point3) -> Cell:
        return (math.floor(point[0]), math.floor(point[1]))

    def _stroll(self, here: Point3, t: float, facing: int) -> AmbientMove | None:
        """A walk (a duck's glide) from ``here`` to another waypoint at least three cells away."""
        start = self._cell_of(here)
        ok = set(self.passable)
        far = 6 if self.kind == "walker" else 5 if self.kind == "cat" else 4
        pool = [cell for cell in self._waypoints() if 3 <= max(abs(cell[0] - start[0]), abs(cell[1] - start[1])) <= (99 if self.kind == "walker" else far)]
        if not pool:
            pool = [cell for cell in self._waypoints() if cell != start]
        for _ in range(6):
            if not pool:
                return None
            goal = self.rng.choice(pool)
            paths = self.cells.paths
            cost = (lambda cell: 1.0 if cell in paths else 1.8) if self.kind == "walker" else None
            cells = cell_route(ok | {start}, start, goal, place=None if self.kind == "duck" else self.place, cost=cost)
            if cells is not None and len(cells) > 1:
                points = (here, *(self._point(cell) for cell in cells[1:]))
                length = sum(math.dist(a[:2], b[:2]) for a, b in zip(points, points[1:]))
                return AmbientMove(t, length / AMBIENT_SPEEDS[self.kind], "glide" if self.kind == "duck" else "walk", points, facing)
            pool.remove(goal)
        return None

    def _bird(self, last: AmbientMove, here: Point3, t: float, facing: int) -> None:
        rng = self.rng
        self._since_flight += last.seconds
        if last.fade == "out":   # flown out of the place: away a while, then back over another edge
            self._add(AmbientMove(t, rng.uniform(3.0, 7.0), "gone", (here,), facing, fade="gone"))
            return
        if last.fade == "gone":
            land = rng.choice(self.ground)
            goal = self._point(land)
            goal = (goal[0] + rng.uniform(-0.3, 0.3), goal[1] + rng.uniform(-0.3, 0.3), goal[2])
            start = self._outside(goal, rng.choice((-1, 1)))
            self._fly(start, goal, t, fade="in")
            return
        if self._since_flight >= self._flight_due:
            self._since_flight = 0.0
            self._flight_due = rng.uniform(6.0, 14.0)
            if rng.random() < 0.3:
                self._fly(here, self._outside(here, facing), t, fade="out")
                return
            start = self._cell_of(here)
            pool = [cell for cell in self.ground if max(abs(cell[0] - start[0]), abs(cell[1] - start[1])) >= 4] or self.ground
            goal = self._point(rng.choice(pool))
            if self._fly(here, (goal[0] + rng.uniform(-0.3, 0.3), goal[1] + rng.uniform(-0.3, 0.3), goal[2]), t):
                return
        roll = rng.random()
        if roll < 0.45:
            self._add(AmbientMove(t, rng.uniform(0.5, 1.4), "peck", (here,), facing))
        elif roll < 0.8:
            for _ in range(4):
                angle = rng.uniform(0.0, 2 * math.pi)
                there = (here[0] + 0.45 * math.cos(angle), here[1] + 0.45 * math.sin(angle), here[2])
                cell = self._cell_of(there)
                if cell in self.stops:
                    there = (there[0], there[1], self.place.stand_z(*cell))
                    self._add(AmbientMove(t, 0.3, "hop", (here, there), facing, arc=0.12))
                    return
            self._add(AmbientMove(t, 0.6, "peck", (here,), facing))
        else:
            self._add(AmbientMove(t, rng.uniform(0.4, 1.2), "stand", (here,), -facing if rng.random() < 0.5 else facing))

    def _outside(self, point: Point3, facing: int) -> Point3:
        """A point high up a few tiles beyond the place's edge on the picture's ``facing`` side
        (right: beyond its right-hand edges)."""
        x, y = point[0], point[1]
        if facing > 0:   # to the right on the picture: x up, y down
            far = max(self.cells.columns - x, y) + 3.0
            return (x + far * 0.7, y - far * 0.7, 6.0)
        far = max(x, self.cells.rows - y) + 3.0
        return (x - far * 0.7, y + far * 0.7, 6.0)

    def _fly(self, a: Point3, b: Point3, t: float, *, fade: str = "") -> bool:
        """A flight from ``a`` to ``b`` over what stands between (an arc high enough); whether it flies."""
        length = math.dist(a[:2], b[:2])
        if length < 0.5:
            return False
        tallest = 0.0
        steps = max(int(length * 3), 2)
        for k in range(steps + 1):
            s = k / steps
            c, r = math.floor(a[0] + (b[0] - a[0]) * s), math.floor(a[1] + (b[1] - a[1]) * s)
            item = self.place.object_at(c, r)
            if item is not None:
                tallest = max(tallest, self.place.floor_z(c, r) + item.height)
        if tallest > 7.5:
            return False   # a tower in the way
        arc = max(2.2, tallest + 1.0 - min(a[2], b[2]), 0.0)
        seconds = length / AMBIENT_SPEEDS["bird"] + 0.5
        self._add(AmbientMove(t, seconds, "fly", (a, b), picture_facing(a, b, 1), arc=arc if not fade else 0.6, fade=fade))
        return True

    def _flutter(self, last: AmbientMove, here: Point3, t: float, facing: int) -> None:
        """A butterfly or a fly: from where it rests or hovers to another flower or place in the air."""
        rng = self.rng
        landed = self.kind == "butterfly" and self._cell_of(here) in set(self.cells.blooms)
        if last.action == "flutter" and (landed or (self.kind == "fly" and rng.random() < 0.4)):
            self._add(AmbientMove(t, rng.uniform(1.5, 3.5) if self.kind == "butterfly" else rng.uniform(0.6, 1.5), "rest", (here,), facing))
            return
        start = self._cell_of(here)
        flowers = self._flower_cells() if self.kind == "butterfly" else []
        pool = [cell for cell in (flowers or sorted(self.cells.air)) if 1 <= max(abs(cell[0] - start[0]), abs(cell[1] - start[1])) <= 5]
        for _ in range(6):
            if not pool:
                break
            cell = rng.choice(pool)
            rest = self.kind == "butterfly" and cell in set(self.cells.blooms)
            goal = self._air_point(cell, rest=rest)
            if self._clear_line(here, goal):
                speed = AMBIENT_SPEEDS[self.kind]
                self._add(AmbientMove(t, math.dist(here[:2], goal[:2]) / speed + 0.4, "flutter", (here, goal), picture_facing(here, goal, facing),
                                      arc=0.4 if rest else 0.15))
                return
            pool.remove(cell)
        self._add(AmbientMove(t, 1.0, "rest", (here,), facing))

    def _clear_line(self, a: Point3, b: Point3) -> bool:
        """Whether the cells between ``a`` and ``b`` are all of the air (nothing tall in the way)."""
        steps = max(int(math.dist(a[:2], b[:2]) * 3), 1)
        return all((math.floor(a[0] + (b[0] - a[0]) * k / steps), math.floor(a[1] + (b[1] - a[1]) * k / steps)) in self.cells.air
                   or k in (0, steps) for k in range(steps + 1))

    # ----- where it is -----------------------------------------------------------------------------------

    def move_at(self, now: float) -> AmbientMove | None:
        """The move under way at scene time ``now`` (``None``: it has none: no room for it)."""
        if not self.moves:
            return None
        self._extend(now)
        k = max(bisect.bisect_right(self._starts, now) - 1, 0)
        return self.moves[k]

    def at(self, now: float) -> AmbientPose | None:
        """Its pose at scene time ``now`` (``None``: there is no room for it on the place)."""
        if self.kind == "firefly":
            return self._hover(now)
        move = self.move_at(now)
        if move is None:
            return None
        into = max(now - move.start, 0.0)
        share = min(into / move.seconds, 1.0) if move.seconds > 0 else 1.0
        shown = 0.0 if move.fade == "gone" else 1.0
        if move.fade == "in":
            shown = min(share / 0.35, 1.0)
        elif move.fade == "out":
            shown = min((1.0 - share) / 0.35, 1.0)
        if len(move.points) == 1:
            return AmbientPose(move.points[0], move.facing, move.action, into, shown)
        if move.action in ("walk", "glide"):
            distance = share * move.length
            point, leg = _along(move.points, distance)
            a, b = move.points[leg], move.points[leg + 1]
            return AmbientPose(point, picture_facing(a, b, move.facing), move.action, distance, shown)
        a, b = move.points[0], move.points[-1]
        s = _ease(share) if move.action in ("fly", "flutter") and not move.fade else share
        point = (a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, a[2] + (b[2] - a[2]) * s + move.arc * 4 * s * (1 - s))
        if move.action == "flutter":   # a butterfly's wavering way
            w = self.waves
            wobble = 0.22 if self.kind == "butterfly" else 0.12
            fast = 2.6 if self.kind == "butterfly" else 7.0
            calm = math.sin(math.pi * share)
            point = (point[0] + wobble * calm * math.sin(fast * now + w[0]), point[1] + wobble * calm * math.sin(fast * 1.3 * now + w[1]),
                     point[2] + 0.5 * wobble * calm * math.sin(fast * 1.7 * now + w[2]))
        return AmbientPose(point, picture_facing(a, b, move.facing), move.action, into, shown)

    def _hover(self, now: float) -> AmbientPose | None:
        """A firefly drifting about its place and blinking."""
        if self.anchor is None:
            return None
        x, y, z = self.anchor
        w, k = self.waves, self.rates
        dx = 0.32 * math.sin(k[0] * now + w[0]) + 0.1 * math.sin(2.3 * k[0] * now + w[3])
        dy = 0.32 * math.sin(k[1] * now + w[1]) + 0.1 * math.sin(2.1 * k[1] * now + w[4])
        dz = 0.22 * math.sin(k[2] * now + w[2]) + 0.06 * math.sin(3.1 * now + w[5])
        vx = math.cos(k[0] * now + w[0]) * k[0] - math.cos(k[1] * now + w[1]) * k[1]
        cycle = (now / self.blink + w[5] / (2 * math.pi)) % 1.0
        glow = 0.12 + 0.88 * max(0.0, math.sin(math.pi * min(cycle / 0.5, 1.0))) ** 2 if cycle < 0.5 else 0.12
        return AmbientPose((x + dx, y + dy, z + dz), 1 if vx >= 0 else -1, "hover", now, 1.0, glow)

    def samples(self, start: float, end: float, step: float = PLAN_STEP) -> list[AmbientPose]:
        """Its poses from scene time ``start`` to ``end`` every ``step`` seconds (at most 400)."""
        if end <= start:
            found = self.at(start)
            return [found] if found is not None else []
        count = min(max(int((end - start) / step), 1), 400)
        poses = [self.at(start + (end - start) * k / count) for k in range(count + 1)]
        return [pose for pose in poses if pose is not None]


def ambient_counts(given: dict[str, int | bool], indoor: bool) -> dict[str, int]:
    """How many of each kind (:data:`AMBIENT_KINDS`) a scene's ``ambient`` setting asks for:
    ``true`` is :data:`AMBIENT_DEFAULTS`, a number that many; indoors only :data:`INDOOR_KINDS`."""
    counts: dict[str, int] = {}
    for key, kind in AMBIENT_KEYS.items():
        value = given.get(key)
        if value is None or value is False:
            continue
        count = AMBIENT_DEFAULTS[key] if value is True else int(value)
        if count > 0 and (not indoor or kind in INDOOR_KINDS):
            counts[kind] = count
    return counts


def plan_ambient(place: IsoPlace, cells: AmbientCells, counts: dict[str, int], seed: int) -> list[AmbientPlan]:
    """The plans of a scene's ambient life: ``counts`` creatures of each kind on ``place`` (only
    those with room there), named ``ambient_<kind>_<n>``, each seeded from ``seed``."""
    plans: list[AmbientPlan] = []
    for kind in AMBIENT_KINDS:
        for n in range(counts.get(kind, 0)):
            name = f"ambient_{kind}_{n + 1}"
            plan = AmbientPlan(kind, name, place, cells, ambient_seed(seed, name), index=n, of=counts[kind])
            if plan.possible():
                plans.append(plan)
    return plans


__all__ = ["AMBIENT_DEFAULTS", "AMBIENT_KEYS", "AMBIENT_KINDS", "AMBIENT_MAX", "AMBIENT_SPEEDS", "BLOOM_KINDS", "GREEN_KINDS", "INDOOR_KINDS",
           "LOW_OBJECT", "AmbientCells", "AmbientMove", "AmbientPlan", "AmbientPose", "ambient_cells", "ambient_counts", "ambient_seed", "around",
           "cell_route", "picture_facing", "plan_ambient"]
