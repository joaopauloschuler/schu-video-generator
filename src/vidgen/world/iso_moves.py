"""Walking on an isometric place (DESIGN.md §89.9): routes on the grid of cells, around what is
in the way and up and down steps. Plain data and pure functions, no manim, like
:mod:`vidgen.world.moves` for platform levels.

A route goes from cell to cell, to the 8 cells around (a diagonal only where both cells beside
it are free and all four are level, so it never cuts a corner or climbs diagonally), up or down
at most one step (:data:`~vidgen.world.iso.STEP_HEIGHT`) at a time, never through water, walls,
objects (but a bridge or a rug) or outside the place. The search is a cheapest-path search with
a small cost per turn (fewer, longer straight parts read better) and ties broken by a fixed
order, so the same map gives the same route every time. Cells where other characters stand cost
more (a route goes round them when it can) but are not refused; a goal where one stands becomes
the free cell nearest to it.

The feet move along the middles of the cells; going up a step they rise just before the edge of
the higher cell, going down they drop just after it (:attr:`IsoRoute.at`), so a character is
never inside a block. An entrance starts beyond the place's edge (:data:`EDGE_STEP`), an exit
ends there.
"""

from __future__ import annotations

import heapq
import math
import random
import zlib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from vidgen.errors import VidgenError
from vidgen.world.iso import BLOCK, DOOR, PATH, VOID, WALLS, WATER, IsoPlace

Cell = tuple[int, int]
Point3 = tuple[float, float, float]

#: The steps to the cells around one, as (column, row) changes: the four sides first (n, e, s,
#: w as the map reads), then the diagonals; their order breaks ties between equal routes.
NEIGHBOURS: tuple[Cell, ...] = ((0, -1), (1, 0), (0, 1), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1))
#: The extra cost of a turn (cells): among routes of the same length the one with fewer turns.
TURN_COST = 0.05
#: The extra cost of passing a cell where another character stands (cells).
CROWD_COST = 4.0
#: How far beyond the place's edge (tile units, from the edge cell's middle) an entrance starts
#: and an exit ends.
EDGE_STEP = 1.0
#: The share of a leg in which the feet go up or down a step (before the higher cell going up,
#: after it going down).
STEP_EASE = 0.3
#: How far a wander's stops are from where it starts (cells), and how many stops it makes.
WANDER_RADIUS = 3
WANDER_STOPS = 3
#: The sides of the place's edge an entrance or exit uses: the map's west and south edges are
#: on the picture's left, its north and east edges on its right; the front sides (south, east)
#: are tried first, they are in view.
EDGE_SIDES: dict[str, tuple[Cell, ...]] = {"left": ((0, 1), (-1, 0)), "right": ((1, 0), (0, -1))}
_EDGE_ORDER: tuple[Cell, ...] = ((0, 1), (1, 0), (-1, 0), (0, -1))
_SIDE_WORDS: dict[Cell, str] = {(0, 1): "front-left", (1, 0): "front-right", (-1, 0): "back-left", (0, -1): "back-right"}


def _smoothstep(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


@dataclass(frozen=True)
class IsoRoute:
    """A walk on an iso place: the feet's ``points`` (tile units; one per cell walked through, at
    its middle and standing height, and an entrance's start or an exit's end beyond the edge) and
    the ``cells`` they stand in (``None`` beyond the edge). A single point: it stays where it is."""

    points: tuple[Point3, ...]
    cells: tuple[Cell | None, ...] = field(default=())

    @property
    def start(self) -> Point3:
        return self.points[0]

    @property
    def end(self) -> Point3:
        return self.points[-1]

    @property
    def end_cell(self) -> Cell | None:
        return self.cells[-1] if self.cells else None

    @property
    def length(self) -> float:
        """How far the feet go across (tile units; steps up and down do not add to it)."""
        return sum(math.dist(a[:2], b[:2]) for a, b in zip(self.points, self.points[1:]))

    def at(self, distance: float) -> tuple[Point3, int]:
        """Where the feet are ``distance`` tiles along and the leg they are on (its index; -1:
        no legs). Up a step the feet rise in the last :data:`STEP_EASE` before the middle of the
        leg (the higher cell's edge), down a step they drop in the same share after it."""
        if len(self.points) < 2:
            return self.points[0], -1
        for k, (a, b) in enumerate(zip(self.points, self.points[1:])):
            leg = math.dist(a[:2], b[:2])
            if distance <= leg + 1e-9 or k == len(self.points) - 2:
                share = min(max(distance / leg, 0.0), 1.0) if leg > 0 else 1.0
                if b[2] > a[2]:
                    rise = _smoothstep((share - (0.5 - STEP_EASE)) / STEP_EASE)
                elif b[2] < a[2]:
                    rise = _smoothstep((share - 0.5) / STEP_EASE)
                else:
                    rise = 0.0
                return (a[0] + (b[0] - a[0]) * share, a[1] + (b[1] - a[1]) * share, a[2] + (b[2] - a[2]) * rise), k
            distance -= leg
        raise AssertionError("unreachable")

    def leg(self, index: int) -> tuple[Point3, Point3]:
        return self.points[index], self.points[index + 1]

    def then(self, other: IsoRoute) -> IsoRoute:
        """This route and then ``other`` (which starts where this one ends)."""
        return IsoRoute((*self.points, *other.points[1:]), (*self.cells, *other.cells[1:]))

    def part(self, first: int, last: int) -> IsoRoute:
        """The route from its point ``first`` to its point ``last`` (inclusive; ``last`` before
        ``first`` walks it backwards)."""
        step = 1 if last >= first else -1
        indices = range(first, last + step, step)
        return IsoRoute(tuple(self.points[k] for k in indices), tuple(self.cells[k] for k in indices))


def cell_point(place: IsoPlace, cell: Cell) -> Point3:
    """The feet of someone standing in ``cell``: its middle, on its top (a bridge's deck)."""
    column, row = cell
    return (column + 0.5, row + 0.5, place.stand_z(column, row))


def cell_of(point: Sequence[float]) -> Cell:
    """The cell a point (tile units) lies in."""
    return (math.floor(point[0]), math.floor(point[1]))


def route_through(place: IsoPlace, cells: Sequence[Cell]) -> IsoRoute:
    """The route through ``cells`` (each next to the one before)."""
    return IsoRoute(tuple(cell_point(place, cell) for cell in cells), tuple(cells))


def can_step(place: IsoPlace, here: Cell, there: Cell) -> bool:
    """Whether one can walk from ``here`` to the cell ``there`` next to it: ``there`` is
    standable, at most one step higher or lower; diagonally only past two free cells, all four
    cells level (no cutting a corner, no climbing diagonally)."""
    if not place.is_standable(*there):
        return False
    steps_here, steps_there = place.cell(*here).steps, place.cell(*there).steps
    if abs(steps_here - steps_there) > 1:
        return False
    dc, dr = there[0] - here[0], there[1] - here[1]
    if dc and dr:
        beside = ((here[0] + dc, here[1]), (here[0], here[1] + dr))
        return all(place.is_standable(*cell) and place.cell(*cell).steps == steps_here for cell in beside) and steps_here == steps_there
    return True


def where(cell: Cell) -> str:
    """A cell as the author reads the map: ``row r, column c`` from 1."""
    return f"row {cell[1] + 1}, column {cell[0] + 1}"


#: What :func:`_reach` finds for each cell: the cost of the cheapest way there and its cells.
Reached = dict[Cell, tuple[float, tuple[Cell, ...]]]


def _reach(place: IsoPlace, start: Cell, crowd: Collection[Cell] = ()) -> Reached:
    """The cheapest way to every cell reachable from ``start``: a cheapest-path search over
    (cell, heading) with :data:`TURN_COST` per turn and :data:`CROWD_COST` per crowded cell;
    deterministic (ties by the order things were found, :data:`NEIGHBOURS`)."""
    crowded = set(crowd) - {start}
    State = tuple[Cell, int]
    best: dict[State, tuple[float, State | None]] = {(start, -1): (0.0, None)}
    queue: list[tuple[float, int, Cell, int]] = [(0.0, 0, start, -1)]
    order = 0
    done: set[State] = set()
    first: dict[Cell, State] = {}   # each cell's cheapest state: the first one taken off the queue
    while queue:
        cost, _, cell, heading = heapq.heappop(queue)
        if (cell, heading) in done:
            continue
        done.add((cell, heading))
        first.setdefault(cell, (cell, heading))
        for k, (dc, dr) in enumerate(NEIGHBOURS):
            there = (cell[0] + dc, cell[1] + dr)
            if not can_step(place, cell, there):
                continue
            step = math.sqrt(2.0) if dc and dr else 1.0
            step += TURN_COST if heading not in (-1, k) else 0.0
            step += CROWD_COST if there in crowded else 0.0
            known = best.get((there, k))
            if known is None or cost + step < known[0] - 1e-12:
                best[(there, k)] = (cost + step, (cell, heading))
                order += 1
                heapq.heappush(queue, (cost + step, order, there, k))
    found: Reached = {}
    for cell, state in first.items():
        cells: list[Cell] = []
        at: State | None = state
        while at is not None:
            cells.append(at[0])
            at = best[at][1]
        found[cell] = (best[state][0], tuple(reversed(cells)))
    return found


def _blocker(place: IsoPlace, here: Cell, there: Cell) -> str:
    """Why one cannot walk from ``here`` to ``there``, in words."""
    item = place.object_at(*there)
    ground = place.ground(*there)
    if ground == VOID:
        return "the edge of the place"
    if item is not None and not item.walkable:
        return f"the {item.kind} '{item.name}'" if item.name != item.kind else f"the {item.kind}"
    if ground == WATER:
        return "water (a bridge crosses it)"
    if ground in WALLS:
        return "a wall (a door, +, lets one through)"
    rise = place.cell(*there).steps - place.cell(*here).steps
    if abs(rise) > 1:
        return (f"a {'climb' if rise > 0 else 'drop'} of {abs(rise)} steps (one walks up or down one step at a time: "
                "put steps of one between, e.g. 1 2 3 on the map)")
    return "a corner (it walks diagonally only past two free, level cells)"


def _why_not(place: IsoPlace, reached: Reached, goal: Cell) -> str:
    """Where the way to ``goal`` stops and what is in the way there."""
    def key(cell: Cell) -> tuple[float, float, int, int]:
        return (math.dist(cell, goal), reached[cell][0], cell[1], cell[0])

    nearest = min(reached, key=key)
    towards = sorted(((nearest[0] + dc, nearest[1] + dr) for dc, dr in NEIGHBOURS),
                     key=lambda cell: (math.dist(cell, goal), cell[1], cell[0]))
    there = next((cell for cell in towards if cell not in reached), towards[0])
    return f"the way stops at {where(nearest)}: {_blocker(place, nearest, there)} at {where(there)}"


def find_route(place: IsoPlace, start: Cell, goal: Cell, *, crowd: Collection[Cell] = (), who: str = "it",
               to: str | None = None) -> IsoRoute:
    """The route on foot from ``start`` to ``goal`` (cells), round the cells in ``crowd`` (where
    others stand) when it can; a goal in ``crowd`` becomes a free cell beside it on the picture
    (:data:`BESIDE`, the nearest to walk to), else the nearest free cell.
    :class:`VidgenError` naming ``who``, the goal (``to``) and where the way is blocked."""
    reached = _reach(place, start, crowd)
    if goal in crowd and goal != start:
        taken = goal
        free = [cell for cell in reached if cell not in crowd or cell == start]

        def nearness(cell: Cell) -> tuple[int, float, int, int]:
            offset = (cell[0] - taken[0], cell[1] - taken[1])
            rank = BESIDE.index(offset) if offset in BESIDE else len(BESIDE) + max(abs(offset[0]), abs(offset[1]))
            return (rank, reached[cell][0], cell[1], cell[0])

        goal = min(free, key=nearness)
    if goal not in reached:
        raise VidgenError(f"{who} cannot walk from {where(start)} to {to or where(goal)}: {_why_not(place, reached, goal)}")
    return route_through(place, reached[goal][1])


def goal_cell(place: IsoPlace, to: str | Mapping[str, int] | tuple[int, int]) -> tuple[Cell, str]:
    """Where a walk ``to`` a spot (its stand cell) or a cell (``{column, row}`` or ``(column,
    row)`` from 1, as the author reads the map) ends, and how to name it. :class:`VidgenError`
    for an unknown spot (listing the spots) or a cell outside the place or not to stand on."""
    if isinstance(to, str):
        return place.stand_cell(to), f"'{to}'"
    column, row = (to["column"], to["row"]) if isinstance(to, Mapping) else to
    cell = (column - 1, row - 1)
    if not 0 <= cell[0] < place.columns or not 0 <= cell[1] < place.rows or place.ground(*cell) == VOID:
        raise VidgenError(f"{where(cell)} is outside the place (its map is {place.columns} columns by {place.rows} rows)")
    if not place.is_standable(*cell):
        raise VidgenError(f"{where(cell)} is {_blocker(place, cell, cell).split(' (')[0]}: nobody can stand there; "
                          "walk to a cell of floor, path, a block or a door, or to a spot")
    return cell, where(cell)


#: The cells next to one where a second character stands *beside* it on the picture, best
#: first: along the picture's level line (one tile width apart: two characters do not overlap),
#: then the four sides (half a tile width apart, a little higher or lower). Diagonally up or
#: down the picture one would stand right in front of the other.
SIDE_BY_SIDE: tuple[Cell, ...] = ((1, -1), (-1, 1), (1, 0), (0, 1), (-1, 0), (0, -1))
#: Where to stand next to someone (offsets from its cell), best first: on its level line, then
#: a tile and a half to its side, then its four sides.
BESIDE: tuple[Cell, ...] = ((1, -1), (-1, 1), (2, -1), (1, -2), (-2, 1), (-1, 2), (1, 0), (0, 1), (-1, 0), (0, -1))


def meet_routes(place: IsoPlace, a: Cell, b: Cell, *, crowd: Collection[Cell] = (), who: str = "they") -> tuple[IsoRoute, IsoRoute]:
    """Two characters standing in ``a`` and ``b`` walking to each other: to two cells side by
    side on the picture (:data:`SIDE_BY_SIDE`: on its level line when there is such a pair), the
    pair the longer of the two walks reaches soonest (then the shorter both walks, then the one
    furthest back and left: deterministic), the
    one coming from the picture's left on the left. A route of a single point: that one stays."""
    others = set(crowd) - {a, b}
    from_a, from_b = _reach(place, a, others), _reach(place, b, others)
    if b not in from_a:
        raise VidgenError(f"{who} cannot meet: {_why_not(place, from_a, b)}")
    left_first = a[0] - a[1] <= b[0] - b[1]   # a stands left of b on the picture (u = (x - y) / 2)
    best: tuple[tuple[bool, float, float, int, int, int], Cell, Cell] | None = None
    for here in from_a:
        for k, (dc, dr) in enumerate(SIDE_BY_SIDE):
            there = (here[0] + dc, here[1] + dr)
            if there in others or here in others or not can_step(place, here, there):
                continue
            left, right = sorted((here, there), key=lambda cell: cell[0] - cell[1])
            goal_a, goal_b = (left, right) if left_first else (right, left)
            if goal_a not in from_a or goal_b not in from_b:
                continue
            cost_a, cost_b = from_a[goal_a][0], from_b[goal_b][0]
            key = (k >= 2, round(max(cost_a, cost_b), 6), round(cost_a + cost_b, 6), k, goal_a[1], goal_a[0])
            if best is None or key < best[0]:
                best = (key, goal_a, goal_b)
    if best is None:
        raise VidgenError(f"{who} cannot meet: no two free cells side by side between {where(a)} and {where(b)}")
    return route_through(place, from_a[best[1]][1]), route_through(place, from_b[best[2]][1])


def follow_route(place: IsoPlace, start: Cell, leader: Cell, leader_route: IsoRoute | None = None, *, gap: int = 1,
                 crowd: Collection[Cell] = (), who: str = "it", whom: str = "the leader") -> IsoRoute:
    """A walk after a leader: to where it stands (``leader``) and on along its route when it walks
    now (``leader_route``), stopping ``gap`` cells behind where the leader stops; one cell right
    behind it on the picture (where the leader would hide it) takes a step aside, to a cell next
    to the leader half a tile to the side (DESIGN.md §89.10)."""
    cells = [cell for cell in (leader_route.cells if leader_route is not None else (leader,)) if cell is not None]
    approach = find_route(place, start, cells[0], crowd=set(crowd) - {cells[0]}, who=who, to=whom)
    path = list(approach.cells) + cells[1:]
    if start in path[1:]:   # it stands on the leader's way: it walks on from there
        last = len(path) - 1 - path[::-1].index(start)
        path = path[last:]
    path = path[:max(len(path) - gap, 1)]
    end, last = path[-1], cells[-1]
    if end != last and abs(end[0] - last[0]) == 1 and end[0] - last[0] == end[1] - last[1]:
        # right behind (or in front of) the leader on the picture, it would be hidden (or hide
        # it): a step aside, to a cell beside the leader half a tile to the side
        aside = [cell for cell in ((end[0], last[1]), (last[0], end[1]))
                 if place.is_standable(*cell) and can_step(place, end, cell) and cell not in set(crowd) - {start}]   # type: ignore[arg-type]
        if aside:
            path.append(aside[0])
    return route_through(place, path)   # type: ignore[arg-type]


def wander_route(place: IsoPlace, start: Cell, *, around: Cell | None = None, radius: int = WANDER_RADIUS, stops: int = WANDER_STOPS,
                 seed: int = 0, crowd: Collection[Cell] = (), who: str = "it") -> IsoRoute:
    """A stroll: ``stops`` cells picked at random (``seed``: the same seed, the same stroll) among
    the free cells it can reach within ``radius`` cells of ``around`` (default: ``start``),
    each a different one at least two cells from the one before, walked in turn."""
    centre = around if around is not None else start
    reached = _reach(place, start, crowd)
    choices = sorted(cell for cell in reached
                     if cell not in crowd and max(abs(cell[0] - centre[0]), abs(cell[1] - centre[1])) <= radius)
    if not any(cell != start for cell in choices):
        raise VidgenError(f"{who} has nowhere to wander within {radius} cells of {where(centre)} (walls, water, objects or others "
                          "all around); give a larger radius or another place (around)")
    rng = random.Random(seed)
    route = route_through(place, [start])
    here = start
    for _ in range(stops):
        far = [cell for cell in choices if max(abs(cell[0] - here[0]), abs(cell[1] - here[1])) >= 2]
        pool = far or [cell for cell in choices if cell != here]
        there = rng.choice(pool)
        route = route.then(find_route(place, here, there, crowd=crowd, who=who))
        here = there
    return route


def wander_seed(name: str, beat: str | None) -> int:
    """A wander's seed when it gives none: the same for a character in a beat on every render."""
    return zlib.crc32(f"{name}/{beat or ''}".encode("utf-8"))


def edge_ways(place: IsoPlace, side: str | None = None) -> list[tuple[Cell, Cell]]:
    """The ways in and out of the place: each standable cell at its edge (outside the place next
    to it) with the direction out, the front edges first; only the ``side`` (``left``, ``right``)
    of the picture given. Water, walls and windows are no way out (a door in an edge wall is)."""
    allowed = EDGE_SIDES[side] if side is not None else _EDGE_ORDER
    found = []
    for out in [d for d in _EDGE_ORDER if d in allowed]:
        for r in range(place.rows):
            for c in range(place.columns):
                if place.is_standable(c, r) and place.ground(c + out[0], r + out[1]) == VOID:
                    found.append(((c, r), out))
    return found


def _edge_point(place: IsoPlace, cell: Cell, out: Cell) -> Point3:
    x, y, z = cell_point(place, cell)
    return (x + out[0] * EDGE_STEP, y + out[1] * EDGE_STEP, z)


def _edge_route(place: IsoPlace, inside: Cell, *, side: str | None, crowd: Collection[Cell], who: str, verb: str) -> IsoRoute:
    """The cheapest route from ``inside`` out over the place's edge (on ``side``), ending beyond it."""
    ways = edge_ways(place, side)
    if not ways:
        sides = f"its {side} side" if side is not None else "any side"
        raise VidgenError(f"{who} cannot {verb}: the place has no way out at {sides} of its edge (a cell to stand on at the edge "
                          "of the map; indoors a door, +, in an edge wall); give door: a spot, or another side")
    reached = _reach(place, inside, crowd)
    open_ways = [(cell, out) for cell, out in ways if cell in reached]
    if not open_ways:
        raise VidgenError(f"{who} cannot {verb}: from {where(inside)} no way leads to the {side + ' ' if side else ''}edge of the place "
                          f"({_why_not(place, reached, ways[0][0])})")
    rank = {way: k for k, way in enumerate(ways)}
    cell, out = min(open_ways, key=lambda way: (reached[way[0]][0], rank[way]))
    route = route_through(place, reached[cell][1])
    return IsoRoute((*route.points, _edge_point(place, cell, out)), (*route.cells, None))


def entry_route(place: IsoPlace, goal: Cell, *, side: str | None = None, door: Cell | None = None, crowd: Collection[Cell] = (),
                who: str = "it", to: str | None = None) -> IsoRoute:
    """A walk into the place to ``goal``: from beyond its nearest edge (on ``side`` of the
    picture), or from the cell ``door`` (a spot it comes out of)."""
    if door is not None:
        return find_route(place, door, goal, crowd=crowd, who=who, to=to)
    out = _edge_route(place, goal, side=side, crowd=crowd, who=who, verb=f"enter to {to or where(goal)}")
    return out.part(len(out.points) - 1, 0)


def exit_route(place: IsoPlace, start: Cell, *, side: str | None = None, door: Cell | None = None, crowd: Collection[Cell] = (),
               who: str = "it", to: str | None = None) -> IsoRoute:
    """A walk out of the place from ``start``: over its nearest edge (on ``side`` of the
    picture) to beyond it, or to the cell ``door`` (a spot it goes into)."""
    if door is not None:
        return find_route(place, start, door, crowd=crowd, who=who, to=to)
    return _edge_route(place, start, side=side, crowd=crowd, who=who, verb="exit")


# ----- replaying a scene's moves (vidgen validate) -----------------------------------------------


#: The moves :func:`iso_move_problems` replays.
ISO_MOVES = frozenset({"walk_to", "run_to", "enter", "exit", "wander", "meet"})
#: What else :func:`iso_move_problems` replays (DESIGN.md §89.10): small things handed about
#: (who stands next to what), and objects coming and going (a bridge to walk over).
ISO_ITEM_ACTIONS = frozenset({"pick_up", "give", "put_down"})
ISO_PLACE_CHANGES = frozenset({"reveal", "hide"})
#: How far (in cells across, 8 neighbours) a character reaches to pick up, give or put down.
ISO_REACH = 1


@dataclass(frozen=True)
class IsoStep:
    """One move of a scene, in play order: where it is written (``location``), its beat, the
    action, the characters it moves (the objects a ``reveal`` or ``hide`` changes) and its
    options."""

    location: str
    beat: str
    action: str
    names: tuple[str, ...]
    options: Mapping[str, object]


def _spot_cell(place: IsoPlace, name: object) -> Cell:
    return place.stand_cell(str(name))


def plan_move(place: IsoPlace, cells: Mapping[str, Cell | None], step: IsoStep, name: str, *, homes: Mapping[str, str],
              leader_routes: Mapping[str, IsoRoute] | None = None) -> dict[str, IsoRoute | None]:
    """The routes of one move of ``name`` (and of whoever moves with it: ``meet``'s other) with
    everyone in ``cells`` (``None``: off the place), as the stage plays it: name -> route
    (``None``: it leaves the place). ``homes``: each character's own spot (where ``enter`` walks
    it without ``to``); ``leader_routes``: the routes planned just now in the same batch (a walk
    ``after`` a leader walks after its route). :class:`VidgenError` naming the problem."""
    o = step.options
    here = cells.get(name)
    crowd = {cell for other, cell in cells.items() if other != name and cell is not None}
    who = f"'{name}'"
    if step.action == "enter":
        to = o.get("to") or homes[name]
        goal, label = goal_cell(place, str(to))
        door = _spot_cell(place, o["door"]) if o.get("door") else None
        return {name: entry_route(place, goal, side=o.get("side"), door=door, crowd=crowd, who=who, to=label)}   # type: ignore[arg-type]
    if here is None:
        raise VidgenError(f"{who} is not on the place then (it has not entered yet, or it has exited): {step.action} needs it there")
    if step.action == "exit":
        door = _spot_cell(place, o["door"]) if o.get("door") else None
        route = exit_route(place, here, side=o.get("to"), door=door, crowd=crowd, who=who,   # type: ignore[arg-type]
                           to=f"'{o['door']}'" if o.get("door") else None)
        return {name: route}
    if step.action == "wander":
        around = _spot_cell(place, o["around"]) if o.get("around") else None
        seed = o.get("seed")
        return {name: wander_route(place, here, around=around, radius=int(o.get("radius") or WANDER_RADIUS),   # type: ignore[arg-type]
                                   stops=int(o.get("stops") or WANDER_STOPS),   # type: ignore[arg-type]
                                   seed=int(seed) if seed is not None else wander_seed(name, step.beat), crowd=crowd, who=who)}   # type: ignore[arg-type]
    if step.action == "meet":
        other = str(o["with"])
        there = cells.get(other)
        if there is None:
            raise VidgenError(f"'{other}' is not on the place then: {who} cannot meet it")
        first, second = meet_routes(place, here, there, crowd=crowd - {there}, who=f"{who} and '{other}'")
        return {name: first, other: second}
    leader = o.get("after")
    if leader is not None:
        there = cells.get(str(leader))
        if there is None:
            raise VidgenError(f"'{leader}' is not on the place then: {who} cannot walk after it")
        planned = (leader_routes or {}).get(str(leader))
        start = cell_of(planned.start) if planned is not None else there
        return {name: follow_route(place, here, start, planned, gap=int(o.get("gap") or 1), crowd=crowd, who=who,   # type: ignore[call-overload]
                                   whom=f"'{leader}'")}
    goal, label = goal_cell(place, o["to"])   # type: ignore[arg-type]
    return {name: find_route(place, here, goal, crowd=crowd, who=who, to=label)}


def _cells_apart(cell: Cell, cells: Collection[Cell]) -> int:
    """How many cells across (8 neighbours) ``cell`` is from the nearest of ``cells``."""
    return min(max(abs(cell[0] - c), abs(cell[1] - r)) for c, r in cells)


def _cell_words(cell: Cell) -> str:
    return f"row {cell[1] + 1}, column {cell[0] + 1}"


def _footprint(place: IsoPlace, cell: Cell) -> list[Cell]:
    """The cells a small thing at ``cell`` can be reached from next to: the whole object it
    stands on (a table 2 cells long), else its cell."""
    item = place.object_at(*cell)
    return item.cells() if item is not None else [cell]


def iso_move_problems(place: IsoPlace, starts: Mapping[str, str], steps: Sequence[IsoStep], *, entering: Collection[str] = (),
                      items: Mapping[str, str] | None = None, hidden: Collection[str] = ()) -> list[tuple[str, str]]:
    """The moves of a scene replayed in order on its place (``starts``: each character's spot;
    ``entering``: off the place until their ``enter``): a spot it does not have, a cell nobody can
    stand on, no way there, a move of a character not on the place, as ``(location.option,
    message naming the beat)``. A character with a problem is no longer followed, nor one whose
    move names a spot the place does not have (the action's own check says so).

    Also (DESIGN.md §89.10): ``items`` (small thing -> its spot) picked up, given and put down
    by characters standing next to them (:data:`ISO_REACH`), and the objects ``hidden`` at the
    start or by a ``hide`` (not there until a ``reveal``): routes go round where they would stand
    and do not cross a bridge that is not there."""
    cells: dict[str, Cell | None] = {name: None if name in entering else place.stand_cell(spot) for name, spot in starts.items()}
    spots = set(place.spot_names())
    things: dict[str, Cell | None] = {name: (place.spot(spot).column, place.spot(spot).row) for name, spot in (items or {}).items() if spot in spots}
    held: dict[str, list[str]] = {}
    gone = set(hidden)
    lost: set[str] = set()
    problems: list[tuple[str, str]] = []
    planned: dict[tuple[str, str], dict[str, IsoRoute]] = {}

    def too_far(step: IsoStep, who: str, here: Cell, what: str, there: Collection[Cell], hint: str) -> bool:
        apart = _cells_apart(here, there)
        if apart <= ISO_REACH:
            return False
        problems.append((f"{step.location}.to", f"beat '{step.beat}': '{who}' stands {apart} cells from {what}; it must stand next to "
                         f"it: {hint}"))
        return True

    for step in steps:
        if step.action in ISO_PLACE_CHANGES:
            gone = (gone | set(step.names)) if step.action == "hide" else (gone - set(step.names))
            continue
        now = place.without(gone)
        if step.action in ISO_ITEM_ACTIONS:
            for who in step.names:
                here = cells.get(who)
                if here is None or who in lost:
                    continue
                o = step.options
                if step.action == "pick_up":
                    thing = str(o.get("to"))
                    there = things.get(thing)
                    if there is None:
                        continue   # held by someone (the holding replay says so) or not a small thing of the place
                    start = (items or {}).get(thing)
                    at_start = start is not None and there == (place.spot(start).column, place.spot(start).row)
                    goal = start if at_start else f"{{column: {there[0] + 1}, row: {there[1] + 1}}}"
                    hint = f"walk_to first (- walk_to: {who}, to: {goal})"
                    if not too_far(step, who, here, f"'{thing}' (at {_cell_words(there)})", _footprint(now, there), hint):
                        things[thing] = None
                        held.setdefault(who, []).append(thing)
                elif step.action == "give":
                    other = str(o.get("to"))
                    there = cells.get(other)
                    if there is None or not held.get(who):
                        continue
                    if not too_far(step, who, here, f"'{other}'", [there], f"walk_to first (- walk_to: {who}, to: {other}) or meet "
                                   f"(- meet: {who}, with: {other})"):
                        thing = str(o["prop"]) if o.get("prop") in held[who] else held[who][-1]
                        held[who].remove(thing)
                        held.setdefault(other, []).append(thing)
                else:
                    if not held.get(who):
                        continue
                    thing = str(o["prop"]) if o.get("prop") in held[who] else held[who][-1]
                    to = o.get("to")
                    there = (place.spot(str(to)).column, place.spot(str(to)).row) if isinstance(to, str) and to in spots else here
                    if not too_far(step, who, here, f"'{to}' (where it puts '{thing}' down)", _footprint(now, there),
                                   f"walk_to first (- walk_to: {who}, to: {to})"):
                        held[who].remove(thing)
                        things[thing] = there
            continue
        batch = planned.setdefault((step.beat, str(step.options.get("at", ""))), {})
        for name in step.names:
            moved = {name, str(step.options.get("with"))} if step.action == "meet" else {name}
            named = [step.options.get(key) for key in (("door",) if step.action == "exit" else ("to", "door", "around"))]
            if any(isinstance(spot, str) and spot not in spots for spot in named):
                lost |= moved
            if moved & lost:
                continue
            try:
                routes = plan_move(now, cells, step, name, homes=starts, leader_routes=batch)
            except VidgenError as exc:
                option = {"enter": "to", "exit": "to", "wander": "around", "meet": "with"}.get(step.action, "after" if step.options.get("after") else "to")
                problems.append((f"{step.location}.{option}", f"beat '{step.beat}': {exc}"))
                lost |= moved
                continue
            for mover, route in routes.items():
                batch[mover] = route
                cells[mover] = None if step.action == "exit" or route.end_cell is None else route.end_cell
    return problems


#: What a cell is underfoot, for the footsteps (DESIGN.md §89.11): outdoors ``grass`` (floor) and
#: ``path``, indoors ``boards`` (floor) and ``tiles`` (a path); ``stone`` a raised block (steps,
#: a terrace) or a doorway in a garden wall; a ``bridge`` and a ``rug`` (walkable objects).
SURFACES: tuple[str, ...] = ("grass", "path", "boards", "tiles", "stone", "bridge", "rug")


def surface_at(place: IsoPlace, column: int, row: int) -> str:
    """What the cell is underfoot (:data:`SURFACES`)."""
    item = place.object_at(column, row)
    if item is not None and item.walkable:
        return "rug" if item.kind == "rug" else "bridge"
    ground = place.ground(column, row)
    if ground == BLOCK:
        return "stone"
    if ground == PATH:
        return "tiles" if place.indoor else "path"
    if ground == DOOR:
        return "boards" if place.indoor else "stone"
    return "boards" if place.indoor else "grass"   # the floor


def route_surfaces(place: IsoPlace, route: IsoRoute) -> tuple[tuple[float, str], ...]:
    """What the feet walk on along ``route``: ``(share of its length, surface)`` from where each
    surface starts (the middle of the leg where the feet go from one cell into the next; beyond
    the place's edge, the surface of the first or last cell on it)."""
    known = [c for c in route.cells if c is not None]
    if not known:
        return ()
    length = route.length
    found: list[tuple[float, str]] = []
    covered = 0.0
    for k, cell in enumerate(route.cells):
        surface = surface_at(place, *(cell if cell is not None else (known[0] if k == 0 or not found else known[-1])))
        start = 0.0 if k == 0 else covered - math.dist(route.points[k - 1][:2], route.points[k][:2]) / 2
        if not found or found[-1][1] != surface:
            found.append((min(max(start / length, 0.0), 1.0) if length > 0 else 0.0, surface))
        if k + 1 < len(route.points):
            covered += math.dist(route.points[k][:2], route.points[k + 1][:2])
    return tuple(found)


__all__ = [
    "SURFACES",
    "route_surfaces",
    "surface_at",
    "CROWD_COST",
    "EDGE_SIDES",
    "EDGE_STEP",
    "ISO_ITEM_ACTIONS",
    "ISO_MOVES",
    "ISO_PLACE_CHANGES",
    "ISO_REACH",
    "BESIDE",
    "NEIGHBOURS",
    "SIDE_BY_SIDE",
    "STEP_EASE",
    "TURN_COST",
    "WANDER_RADIUS",
    "WANDER_STOPS",
    "IsoRoute",
    "IsoStep",
    "can_step",
    "cell_of",
    "cell_point",
    "edge_ways",
    "entry_route",
    "exit_route",
    "find_route",
    "follow_route",
    "goal_cell",
    "iso_move_problems",
    "meet_routes",
    "plan_move",
    "route_through",
    "wander_route",
    "wander_seed",
    "where",
]
