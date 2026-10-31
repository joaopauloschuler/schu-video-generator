"""Vehicles moving on an isometric place (DESIGN.md §105): a ``car`` driving along path cells, a
``boat`` sailing across water, a ``train_car`` rolling along its track and a ``rocket`` lifting
off. Plain data and pure functions, no manim, like :mod:`vidgen.world.iso_moves` for walks.

A car or a boat goes from cell to cell to the four cells beside one (never diagonally: it is
drawn side-on, along the map's rows or columns), with a cost per turn so it keeps straight where
it can and a larger one to turn round (where its way ends); ties are broken by a fixed order, so the same
map gives the same route. Its *middle* moves: from between its two cells, through the middle of
each edge it crosses, so on a straight stretch it covers two whole cells and at a corner it cuts
across the corner cell, turning half-way. It stops with its front in the goal cell. A train car
rolls along the straight line of its own cells, as far as level free ground goes both ways (its
*track*), and stops with its middle at the goal. A rocket rises straight up from its pad.

What is in the way is named in the error: the place's edge, an object, ground the vehicle does
not go on (grass for a car, land for a boat), a step, or a character standing there.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace

from vidgen.errors import VidgenError
from vidgen.world.iso import FLOOR, PATH, VOID, WALLS, WATER, IsoObject, IsoPlace

Cell = tuple[int, int]
Point3 = tuple[float, float, float]

#: The vehicles that move, and the action that moves each.
VEHICLE_ACTIONS: dict[str, str] = {"car": "drive_to", "train_car": "drive_to", "boat": "sail_to", "rocket": "lift_off"}
#: The actions that move vehicles (replayed by :func:`~vidgen.world.iso_moves.iso_move_problems`).
ISO_VEHICLE_ACTIONS = frozenset({"drive_to", "sail_to", "lift_off"})
#: Default speeds (tiles per second): a character walks about 1.4.
VEHICLE_SPEEDS: dict[str, float] = {"car": 2.6, "train_car": 2.2, "boat": 1.1}
#: Seconds a vehicle takes to speed up at the start and to slow down at the end, each (at most
#: half the move).
SET_OFF_SECONDS = 0.6
#: How long a rocket's lift-off takes by default (seconds), and how high it rises (tile units;
#: the stage gives the height that takes it out of the view).
LIFT_OFF_SECONDS = 4.0
LIFT_HEIGHT = 30.0
#: The four ways a vehicle heads, as (column, row) steps: the map's east, south, west, north
#: (on the picture: lower right, lower left, upper left, upper right).
HEADINGS: tuple[Cell, ...] = ((1, 0), (0, 1), (-1, 0), (0, -1))
#: The extra cost of a turn (cells): a route keeps straight where it can.
DRIVE_TURN_COST = 0.3
#: The extra cost of turning round (cells): only where the way ends or going on is much longer.
UTURN_COST = 4.0
#: How long each vehicle is along its way and how wide (tile units), and how tall: its box for
#: the draw order (a car's and a boat's two cells, a train car's three).
VEHICLE_SIZES: dict[str, tuple[float, float, float]] = {"car": (1.8, 0.7, 1.32), "boat": (1.9, 0.62, 2.6), "train_car": (2.9, 0.62, 1.95),
                                                        "rocket": (0.7, 0.7, 4.6)}
_GROUND_WORDS = {FLOOR: "grass", PATH: "a path", WATER: "water"}


def _words(cell: Cell) -> str:
    return f"row {cell[1] + 1}, column {cell[0] + 1}"


@dataclass(frozen=True)
class VehicleRoute:
    """A vehicle's move: its middle's ``points`` (tile units, at its base), the way it heads on
    each leg (``turns``: over the first half of the leg, over the second: they differ where it
    turns a corner), the cells it ends on (``end_cells``) and the way it heads then. A single
    point: it stays where it is."""

    points: tuple[Point3, ...]
    turns: tuple[tuple[Cell, Cell], ...]
    end_cells: tuple[Cell, ...]
    end_heading: Cell

    @property
    def length(self) -> float:
        """How far its middle goes (tile units)."""
        return sum(math.dist(a, b) for a, b in zip(self.points, self.points[1:]))

    def at(self, distance: float) -> tuple[Point3, Cell]:
        """Where its middle is ``distance`` along, and the way it heads there."""
        if len(self.points) < 2:
            return self.points[0], self.end_heading
        for k, (a, b) in enumerate(zip(self.points, self.points[1:])):
            leg = math.dist(a, b)
            if distance <= leg + 1e-9 or k == len(self.points) - 2:
                share = min(max(distance / leg, 0.0), 1.0) if leg > 0 else 1.0
                point = tuple(a[i] + (b[i] - a[i]) * share for i in range(3))
                return point, self.turns[k][0 if share < 0.5 else 1]   # type: ignore[return-value]
            distance -= leg
        raise AssertionError("unreachable")

    def turning(self, distance: float) -> tuple[Cell, Cell] | None:
        """The turn it is half-way through ``distance`` along (the ways it heads before and
        after), or ``None``: in the middle half of a corner's leg it heads along the diagonal
        between them (drawn turned, DESIGN.md §105.8); a U-turn has no in-between."""
        for (a, b), (before, after) in zip(zip(self.points, self.points[1:]), self.turns):
            leg = math.dist(a, b)
            if distance <= leg + 1e-9:
                square = before[0] * after[0] + before[1] * after[1] == 0 and before != (0, 0)
                return (before, after) if square and leg > 0 and 0.25 <= distance / leg <= 0.75 else None
            distance -= leg
        return None


def start_heading(item: IsoObject) -> Cell:
    """The way a vehicle standing as placed heads: its front faces left (the viewer's lower left),
    so it heads along the map's row to the east (its nose on the right); facing right, down its
    column to the south. A rocket heads up (``(0, 0)``)."""
    if item.kind == "rocket":
        return (0, 0)
    return (1, 0) if item.facing == "left" else (0, 1)


def middle_of(place: IsoPlace, item: IsoObject) -> Point3:
    """A vehicle's middle (tile units, on its base)."""
    return (item.column + item.width / 2, item.row + item.depth / 2, place.floor_z(item.column, item.row))


def moved_item(item: IsoObject, cells: Sequence[Cell], heading: Cell) -> IsoObject:
    """``item`` standing on ``cells`` (its new footprint), heading ``heading``."""
    columns, rows = [c for c, _ in cells], [r for _, r in cells]
    return replace(item, column=min(columns), row=min(rows), width=max(columns) - min(columns) + 1, depth=max(rows) - min(rows) + 1,
                   facing="left" if heading[1] == 0 else "right")


def moved_place(place: IsoPlace, items: Mapping[str, IsoObject]) -> IsoPlace:
    """``place`` with its objects of ``items`` (by name) standing as they say."""
    if not items:
        return place
    known = {item.name for item in place.objects}
    items = {name: item for name, item in items.items() if name in known}
    occupied = {cell: name for cell, name in place._occupied.items() if name not in items}
    for name, item in items.items():
        for cell in item.cells():
            occupied[cell] = name
    objects = tuple(items.get(item.name, item) for item in place.objects)
    return IsoPlace(place.cells, place.indoor, place.spots, objects, occupied)


def _blocked(place: IsoPlace, item: IsoObject, cell: Cell, level: int, crowd: Mapping[Cell, str]) -> str | None:
    """Why the vehicle ``item`` cannot go onto ``cell`` (``None``: it can)."""
    ground = place.ground(*cell)
    if ground == VOID:
        return "the edge of the place"
    other = place.object_at(*cell)
    if other is not None and other.name != item.name:
        return f"the {other.kind} '{other.name}'" if other.name != other.kind else f"the {other.kind}"
    if cell in crowd:
        return f"'{crowd[cell]}' standing there (walk it away first)"
    if item.kind == "boat":
        return None if ground == WATER else f"{_GROUND_WORDS.get(ground, 'a wall' if ground in WALLS else 'land')} (a boat sails on water, ~)"
    wanted = (PATH,) if item.kind == "car" else (FLOOR, PATH)
    if ground not in wanted:
        word = _GROUND_WORDS.get(ground, "a wall" if ground in WALLS else "a raised block")
        return f"{word} ({'a car drives along path cells, :' if item.kind == 'car' else 'a train car rolls on level ground'})"
    if place.cell(*cell).steps != level:
        return "a step (it drives on level ground only)"
    return None


def _goal(place: IsoPlace, to: object) -> tuple[Cell, str]:
    """The cell a move goes ``to`` (a spot: its own cell; a cell ``{column, row}`` from 1) and how
    to name it."""
    if isinstance(to, str):
        spot = place.spot(to)
        return (spot.column, spot.row), f"'{to}'"
    column, row = (to["column"], to["row"]) if isinstance(to, Mapping) else (getattr(to, "column"), getattr(to, "row"))
    cell = (int(column) - 1, int(row) - 1)
    if not (0 <= cell[0] < place.columns and 0 <= cell[1] < place.rows):
        raise VidgenError(f"{_words(cell)} is outside the place (its map is {place.columns} columns by {place.rows} rows)")
    return cell, _words(cell)


#: How far (cells, sideways and up or down the map together) from a spot off its way a car or a
#: boat stops: a spot on the grass by the road (a shop's door), on the shore by the water (a
#: cell ``{column, row}`` is taken as written).
GOAL_REACH = 2


def _near_goal(place: IsoPlace, item: IsoObject, goal: Cell, level: int) -> Cell:
    """``goal``, or when the vehicle cannot stand there (a spot beside the road or on the shore)
    the nearest cell it can, at most :data:`GOAL_REACH` cells away (the nearest, then the most in
    front, then the leftmost); none: ``goal`` (the search says why it cannot go there)."""
    if _blocked(place, item, goal, level, {}) is None:
        return goal
    near = [(goal[0] + dc, goal[1] + dr) for dc in range(-GOAL_REACH, GOAL_REACH + 1) for dr in range(-GOAL_REACH, GOAL_REACH + 1)
            if 0 < abs(dc) + abs(dr) <= GOAL_REACH]
    free = [cell for cell in near if _blocked(place, item, cell, level, {}) is None]
    return min(free, key=lambda c: (abs(c[0] - goal[0]) + abs(c[1] - goal[1]), -(c[0] + c[1]), c[0]), default=goal)


def _verb(item: IsoObject) -> str:
    return {"boat": "sail", "train_car": "roll"}.get(item.kind, "drive")


def _search(place: IsoPlace, item: IsoObject, start: Cell, heading: Cell, goal: Cell, label: str, crowd: Mapping[Cell, str],
            level: int) -> tuple[list[Cell], Cell]:
    """The cheapest way of ``item`` from ``start`` (its front cell), heading ``heading``, to
    ``goal``: the cells after ``start`` and the way it heads at the end. Four neighbours,
    :data:`DRIVE_TURN_COST` per turn, :data:`UTURN_COST` to turn round (where the way ends);
    deterministic."""
    who = f"'{item.name}'"
    why = _blocked(place, item, goal, level, crowd)
    if why is not None and goal != start:
        raise VidgenError(f"{who} cannot {_verb(item)} to {label}: {_words(goal)} is {why}")
    State = tuple[Cell, Cell]
    best: dict[State, tuple[float, State | None]] = {(start, heading): (0.0, None)}
    queue: list[tuple[float, int, Cell, Cell]] = [(0.0, 0, start, heading)]
    order, done = 0, set()
    reached: dict[Cell, State] = {}
    while queue:
        cost, _, cell, way = heapq.heappop(queue)
        if (cell, way) in done:
            continue
        done.add((cell, way))
        reached.setdefault(cell, (cell, way))
        if cell == goal:
            break
        for turn in HEADINGS:
            there = (cell[0] + turn[0], cell[1] + turn[1])
            if _blocked(place, item, there, level, crowd) is not None:
                continue
            back = turn == (-way[0], -way[1])   # turning round where the way ends (or nothing shorter goes)
            step = 1.0 + (UTURN_COST if back else DRIVE_TURN_COST if turn != way else 0.0)
            known = best.get((there, turn))
            if known is None or cost + step < known[0] - 1e-12:
                best[(there, turn)] = (cost + step, (cell, way))
                order += 1
                heapq.heappush(queue, (cost + step, order, there, turn))
    if goal not in reached:
        nearest = min(reached, key=lambda c: (math.dist(c, goal), c[1], c[0]))
        towards = sorted(((nearest[0] + dc, nearest[1] + dr) for dc, dr in HEADINGS), key=lambda c: (math.dist(c, goal), c[1], c[0]))
        there = next((c for c in towards if _blocked(place, item, c, level, crowd) is not None), towards[0])
        why = _blocked(place, item, there, level, crowd) or "no way on"
        raise VidgenError(f"{who} cannot {_verb(item)} from {_words(start)} to {label}: the way stops at {_words(nearest)}: {why} at {_words(there)}")
    cells: list[Cell] = []
    at: State | None = reached[goal]
    end_way = at[1]
    while at is not None:
        cells.append(at[0])
        at = best[at][1]
    return list(reversed(cells))[1:], end_way


def _road_route(place: IsoPlace, item: IsoObject, heading: Cell, goals: Sequence[object], crowd: Mapping[Cell, str]) -> VehicleRoute:
    """A car's or a boat's route through ``goals`` in turn (spots or cells)."""
    tail = (item.column, item.row)
    nose = (tail[0] + heading[0], tail[1] + heading[1]) if heading[0] >= 0 and heading[1] >= 0 else tail
    if heading[0] < 0 or heading[1] < 0:   # heading west or north: its front is its first cell
        tail = (nose[0] - heading[0], nose[1] - heading[1])
    level = place.cell(*nose).steps
    z = place.floor_z(*nose)
    path, way = [nose], heading
    for to in goals:
        goal, label = _goal(place, to)
        if isinstance(to, str):   # a spot by the road or on the shore: the nearest cell it can stop on
            goal = _near_goal(place, item, goal, level)
        more, way = _search(place, item, path[-1], way, goal, label, crowd, level)
        path += more
    if len(path) < 2:
        return VehicleRoute((middle_of(place, item),), (), item.cells(), heading)
    def mid(a: Cell, b: Cell) -> Point3:
        return ((a[0] + b[0]) / 2 + 0.5, (a[1] + b[1]) / 2 + 0.5, z)
    points = [mid(tail, nose)] + [mid(a, b) for a, b in zip(path, path[1:])]
    ways = [heading] + [(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])]
    turns = tuple((ways[k], ways[k + 1]) for k in range(len(ways) - 1))
    return VehicleRoute(tuple(points), turns, (path[-2], path[-1]), ways[-1])


def track_cells(place: IsoPlace, item: IsoObject) -> list[Cell]:
    """A train car's track: the straight line of its cells (along its row facing left, its column
    facing right), on as far as level, free floor or path goes both ways (other objects, water,
    walls and steps end it)."""
    axis = (1, 0) if item.facing == "left" else (0, 1)
    cells = item.cells()
    level = place.cell(*cells[0]).steps
    line = list(cells)
    for sign in (-1, 1):
        cell = cells[0] if sign < 0 else cells[-1]
        while True:
            cell = (cell[0] + sign * axis[0], cell[1] + sign * axis[1])
            if _blocked(place, item, cell, level, {}) is not None:
                break
            line.append(cell)
    return sorted(line)


def _track_route(place: IsoPlace, item: IsoObject, to: object, crowd: Mapping[Cell, str], track: Sequence[Cell] | None) -> VehicleRoute:
    """A train car rolling along its track (``track``: :func:`track_cells` of where it stood at
    the start) until its middle is at ``to``."""
    goal, label = _goal(place, to)
    line = list(track) if track is not None else track_cells(place, item)
    axis = (1, 0) if item.facing == "left" else (0, 1)
    cells = item.cells()
    middle = cells[len(cells) // 2]
    who = f"'{item.name}'"
    across = 1 if axis == (1, 0) else 0
    if goal[across] != middle[across]:
        lane = f"row {middle[1] + 1}" if axis == (1, 0) else f"column {middle[0] + 1}"
        raise VidgenError(f"{who} rolls along its track ({lane}): to {label} is not on it; give a spot or cell on {lane}")
    half = len(cells) // 2
    ends = [(goal[0] - half * axis[0], goal[1] - half * axis[1]), (goal[0] + half * axis[0], goal[1] + half * axis[1])]
    if any(end not in line for end in ends):
        first, last = line[0], line[-1]
        raise VidgenError(f"{who} cannot roll to {label}: its track runs from {_words(first)} to {_words(last)} and it is {len(cells)} cells long "
                          "(its middle stops at the goal); give a goal further inside the track")
    if goal == middle:
        return VehicleRoute((middle_of(place, item),), (), tuple(cells), start_heading(item))
    sign = 1 if goal[1 - across] > middle[1 - across] else -1
    way = (sign * axis[0], sign * axis[1])
    low, high = sorted((middle[1 - across], goal[1 - across]))
    passed = [(k, middle[1]) if across == 1 else (middle[0], k) for k in range(low - half, high + half + 1)]
    for cell in passed:
        if cell in crowd:
            raise VidgenError(f"{who} cannot roll to {label}: '{crowd[cell]}' stands on the track at {_words(cell)} (walk it away first)")
    z = place.floor_z(*middle)
    start, end = middle_of(place, item), (goal[0] + 0.5, goal[1] + 0.5, z)
    end_cells = tuple(sorted((goal[0] + k * axis[0], goal[1] + k * axis[1]) for k in range(-half, half + 1)))
    return VehicleRoute((start, end), ((way, way),), end_cells, way)


def lift_route(place: IsoPlace, item: IsoObject, height: float = LIFT_HEIGHT) -> VehicleRoute:
    """A rocket rising ``height`` straight up from its pad."""
    x, y, z = middle_of(place, item)
    return VehicleRoute(((x, y, z), (x, y, z + height)), (((0, 0), (0, 0)),), tuple(item.cells()), (0, 0))


def plan_vehicle(place: IsoPlace, name: str, action: str, options: Mapping[str, object], *, heading: Cell | None = None,
                 crowd: Mapping[Cell, str] | None = None, track: Sequence[Cell] | None = None, height: float = LIFT_HEIGHT) -> VehicleRoute:
    """The move ``action`` (``drive_to``, ``sail_to``, ``lift_off``) of the vehicle ``name`` with
    ``options`` (``to``: a spot or a cell; ``via``: spots or cells to pass on the way), from where
    it stands in ``place`` heading ``heading`` (default: as placed), round nobody: ``crowd`` (cell
    -> who stands there) blocks the way. :class:`VidgenError` naming what is in the way."""
    item = place.object(name)
    wanted = {"drive_to": ("car", "train_car"), "sail_to": ("boat",), "lift_off": ("rocket",)}[action]
    if item.kind not in wanted:
        raise VidgenError(f"'{name}' is {item.kind}: {action} moves {' or '.join('a ' + k for k in wanted)}")
    people = dict(crowd or {})
    if action == "lift_off":
        return lift_route(place, item, height)
    if item.kind == "train_car":
        return _track_route(place, item, options["to"], people, track)
    way = heading or start_heading(item)
    goals = [*(options.get("via") or ()), options["to"]]   # type: ignore[misc]
    return _road_route(place, item, way, goals, people)


def drive_share(share: float, seconds: float) -> float:
    """How far along (0..1) a vehicle is ``share`` of the way through a move of ``seconds``: it
    speeds up over :data:`SET_OFF_SECONDS` (at most a third of the move), goes on steadily and
    slows down as long at the end."""
    t = min(max(share, 0.0), 1.0) * seconds
    ramp = min(SET_OFF_SECONDS, seconds / 3)
    if ramp <= 0:
        return min(max(share, 0.0), 1.0)
    top = 1.0 / (seconds - ramp)   # its steady speed (shares of the way per second)
    if t < ramp:
        return top * t * t / (2 * ramp)
    if t > seconds - ramp:
        left = seconds - t
        return 1.0 - top * left * left / (2 * ramp)
    return top * (ramp / 2 + (t - ramp))


def drive_seconds(route: VehicleRoute, speed: float) -> float:
    """How long a move along ``route`` takes at ``speed`` (tiles per second) with its speeding
    up and slowing down."""
    return route.length / speed + SET_OFF_SECONDS


def lift_share(share: float) -> float:
    """How high (0..1) a rocket is ``share`` of the way through its lift-off: from rest, faster and
    faster."""
    s = min(max(share, 0.0), 1.0)
    return s * s * (0.35 + 0.65 * s)


def vehicle_problems(place: IsoPlace, step_action: str, names: Collection[str], options: Mapping[str, object], *,
                     vehicles: dict[str, tuple[IsoObject, Cell]], crowd: Mapping[Cell, str], tracks: dict[str, list[Cell]],
                     gone: set[str]) -> list[str]:
    """Replay one vehicle move (``vidgen validate``): plans the move of each of ``names`` on
    ``place`` with the vehicles where ``vehicles`` says (name -> its footprint and heading, updated
    as they move) and the characters of ``crowd``; the messages of those that cannot go. A rocket
    that lifted off joins ``gone``."""
    problems: list[str] = []
    for name in names:
        if name in gone:
            problems.append(f"'{name}' has lifted off already: it is gone for the rest of the scene")
            continue
        item, heading = vehicles.get(name, (None, None))   # type: ignore[assignment]
        if item is None:
            item = place.object(name)
            heading = start_heading(item)
            if item.kind == "train_car":
                tracks[name] = track_cells(place, item)
        now = moved_place(place, {n: i for n, (i, _) in vehicles.items()})
        try:
            route = plan_vehicle(now, name, step_action, options, heading=heading, crowd=crowd, track=tracks.get(name))
        except VidgenError as exc:
            problems.append(str(exc))
            continue
        if step_action != "lift_off":
            vehicles[name] = (moved_item(item, route.end_cells, route.end_heading), route.end_heading)
        else:
            gone.add(name)
    return problems


__all__ = [
    "DRIVE_TURN_COST",
    "HEADINGS",
    "ISO_VEHICLE_ACTIONS",
    "LIFT_HEIGHT",
    "LIFT_OFF_SECONDS",
    "SET_OFF_SECONDS",
    "VEHICLE_ACTIONS",
    "VEHICLE_SIZES",
    "VEHICLE_SPEEDS",
    "VehicleRoute",
    "drive_seconds",
    "drive_share",
    "lift_route",
    "lift_share",
    "middle_of",
    "moved_item",
    "moved_place",
    "plan_vehicle",
    "start_heading",
    "track_cells",
    "vehicle_problems",
]
