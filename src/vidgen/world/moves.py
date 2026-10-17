"""Moving in a platform level (DESIGN.md §86.7): walking along the tiles (stepping up and down,
stopping at edges), climbing ladders and jumping between platforms, planned from where a body
stands and where it is asked to go.

This is the rules layer: pure functions in tile units, no manim and no physics engine (fixed
paths and parabolic arcs). The stage renders the plans; a game could feed them a player's inputs
instead of a script. A body is a box :data:`BODY_WIDTH` of its height wide standing on its feet;
ground and platforms are solid, a cloud is one-way (a body stands on its top, walks through it and
jumps up through it from below), a ladder is climbed and its top is a place to stand.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Iterator
from dataclasses import dataclass

from vidgen.errors import VidgenError
from vidgen.world.level import CLOUD, GROUND, LADDER, PLATFORM, STANDABLE, Level
from vidgen.world.world import World

#: The tiles a body cannot pass through, from the side or from below.
SOLID: frozenset[str] = frozenset({GROUND, PLATFORM})
#: The highest step (tiles) a walk goes up or down; a higher one stops it (a wall, an edge).
STEP_TILES = 1
#: How far across (tiles) a step up or down takes, centred on the edge between the two columns.
STEP_WIDTH = 0.5
#: A tile climbed on a ladder takes as long as this many tiles walked.
CLIMB_SLOWNESS = 2.0
#: A body's width as a share of its height (a character two tiles tall is 0.8 tiles wide).
BODY_WIDTH = 0.4
#: The longest jump: tiles across, tiles up, tiles down (a character is two tiles tall).
MAX_JUMP_ACROSS = 5.0
MAX_JUMP_UP = 3.0
MAX_JUMP_DOWN = 8.0
#: The lowest arc tried peaks this many tiles over the higher end; higher arcs are tried in steps
#: of :data:`JUMP_APEX_STEP` up to :data:`MAX_JUMP_UP` + :data:`JUMP_HEADROOM` over the take-off.
JUMP_CLEARANCE = 0.75
JUMP_APEX_STEP = 0.25
JUMP_HEADROOM = 1.0
#: The arc's timing: a gravity (tiles per second squared, about half a real one, so arcs are
#: slower than in a game), the fastest it flies across (tiles per second) and the shortest flight.
JUMP_GRAVITY = 8.0
JUMP_AIR_SPEED = 4.0
MIN_FLIGHT_SECONDS = 0.7
#: Kinds of :class:`Leg`.
WALK, STEP, CLIMB = "walk", "step", "climb"
_EPS = 1e-6
#: How finely an arc is checked against the tiles (tiles between samples).
_ARC_SAMPLE = 0.05

Point = tuple[float, float]
_State = tuple[int, int]   # (column, the height its feet stand at)


def smoothstep(x: float) -> float:
    """3x² − 2x³ on 0..1 (clamped)."""
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


@dataclass(frozen=True)
class Leg:
    """One straight part of a :class:`Route`, from ``start`` to ``end`` (feet, tile units): a
    ``walk`` across (the feet keep their height), a ``step`` up or down one tile across the edge of
    two columns, or a ``climb`` up or down a ladder."""

    kind: str
    start: Point
    end: Point

    @property
    def effort(self) -> float:
        """How long it takes, in tiles walked: across for a walk or a step, the height times
        :data:`CLIMB_SLOWNESS` for a climb."""
        if self.kind == CLIMB:
            return abs(self.end[1] - self.start[1]) * CLIMB_SLOWNESS
        return abs(self.end[0] - self.start[0])

    @property
    def direction(self) -> int:
        """+1 going right, -1 left, 0 straight up or down (a climb)."""
        dx = self.end[0] - self.start[0]
        return 0 if abs(dx) <= _EPS else (1 if dx > 0 else -1)

    def point(self, share: float) -> Point:
        """Where the feet are ``share`` (0..1) of the way along (a step eases up or down)."""
        share = min(max(share, 0.0), 1.0)
        rise = share if self.kind == CLIMB else smoothstep(share)
        return (self.start[0] + (self.end[0] - self.start[0]) * share, self.start[1] + (self.end[1] - self.start[1]) * rise)


@dataclass(frozen=True)
class Route:
    """A walk on foot from ``start`` along ``legs`` (none: it stays where it is)."""

    start: Point
    legs: tuple[Leg, ...] = ()

    @property
    def end(self) -> Point:
        return self.legs[-1].end if self.legs else self.start

    @property
    def effort(self) -> float:
        """How long it takes, in tiles walked (:attr:`Leg.effort`)."""
        return sum(leg.effort for leg in self.legs)

    def at(self, effort: float) -> tuple[Point, Leg | None]:
        """Where the feet are ``effort`` tiles walked into the route and the leg they are on
        (``None``: no legs)."""
        if not self.legs:
            return self.start, None
        for leg in self.legs:
            if effort <= leg.effort + _EPS or leg is self.legs[-1]:
                return leg.point(effort / leg.effort if leg.effort > 0 else 1.0), leg
            effort -= leg.effort
        raise AssertionError("unreachable")


@dataclass(frozen=True)
class JumpPlan:
    """A jump: the ``run_up`` walked to the take-off point (its end), then an arc to ``landing``
    whose feet peak at ``apex`` (tile units), in the air for ``flight_seconds``."""

    run_up: Route
    landing: Point
    apex: float
    flight_seconds: float

    @property
    def take_off(self) -> Point:
        return self.run_up.end

    def point(self, share: float) -> Point:
        """Where the feet are ``share`` (0..1) of the way through the flight."""
        return arc_point(self.take_off, self.landing, self.apex, share)


def arc_bump(y0: float, y1: float, apex: float) -> float:
    """``b`` of the arc ``y(u) = y0 + (y1 - y0) u + 4 b u (1 - u)`` from ``y0`` to ``y1`` whose
    highest point is ``apex`` (at least the higher end)."""
    d = y1 - y0
    k = apex - y0 - d / 2
    return (k + math.sqrt(max(k * k - d * d / 4, 0.0))) / 2


def arc_point(start: Point, end: Point, apex: float, share: float) -> Point:
    """The feet ``share`` (0..1) of the way along the arc from ``start`` to ``end`` peaking at
    ``apex``: x moves evenly (a steady speed across), y on a parabola."""
    u = min(max(share, 0.0), 1.0)
    b = arc_bump(start[1], end[1], apex)
    return (start[0] + (end[0] - start[0]) * u, start[1] + (end[1] - start[1]) * u + 4 * b * u * (1 - u))


def flight_seconds(start: Point, end: Point, apex: float) -> float:
    """How long a jump from ``start`` to ``end`` peaking at ``apex`` is in the air: rising and
    falling under :data:`JUMP_GRAVITY`, at most :data:`JUMP_AIR_SPEED` across, at least
    :data:`MIN_FLIGHT_SECONDS`."""
    up = math.sqrt(2 * max(apex - start[1], 0.0) / JUMP_GRAVITY)
    down = math.sqrt(2 * max(apex - end[1], 0.0) / JUMP_GRAVITY)
    return max(up + down, abs(end[0] - start[0]) / JUMP_AIR_SPEED, MIN_FLIGHT_SECONDS)


def is_floor(level: Level, column: int, row: int) -> bool:
    """Whether a body can stand on the top of this cell: a ground, platform or cloud tile, or the
    top of a ladder (a ladder cell with neither a ladder nor a tile to stand on above it)."""
    kind = level.tile(column, row)
    if kind in STANDABLE:
        return True
    above = level.tile(column, row + 1)
    return kind == LADDER and above != LADDER and above not in STANDABLE


def surface_under(level: Level, x: float, y: float) -> float | None:
    """The height of the first floor (:func:`is_floor`) at or below feet at (``x``, ``y``):
    where a shadow lies; ``None`` over a gap or outside the map."""
    if not 0.0 <= x <= level.columns:
        return None
    column = level.column_at(x)
    for row in range(min(math.floor(y + _EPS), level.rows) - 1, -1, -1):
        if is_floor(level, column, row):
            return float(row + 1)
    return None


def map_cell(level: Level, column: int, row: int) -> str:
    """A cell as the author reads the map: ``map row R, column C`` from the top left, from 1."""
    return f"map row {level.rows - row}, column {column + 1}"


class _Ground:
    """Where a body ``height`` tiles tall stands and goes in ``level`` (per column, memoised)."""

    def __init__(self, level: Level, height: float) -> None:
        self.level = level
        self.height = height
        self.half_width = BODY_WIDTH * height / 2
        self.cells_tall = max(1, math.ceil(height - _EPS))
        self._heights: dict[int, tuple[int, ...]] = {}

    def clear(self, column: int, y: int) -> bool:
        """Whether nothing solid fills the cells a body standing at ``y`` in ``column`` takes."""
        return all(self.level.tile(column, row) not in SOLID for row in range(y, y + self.cells_tall))

    def heights(self, column: int) -> tuple[int, ...]:
        """The heights a body can stand at in ``column`` (a floor with room above), bottom up."""
        if column not in self._heights:
            self._heights[column] = tuple(
                row + 1 for row in range(self.level.rows) if is_floor(self.level, column, row) and self.clear(column, row + 1)
            )
        return self._heights[column]

    def climbs(self, column: int, y: int) -> list[int]:
        """The heights a ladder takes a body standing at ``y`` in ``column`` to: up a ladder at its
        feet to the ladder's top (or onto the tile over it), down a ladder under its feet (or under
        the tile it stands on, a hatch) to the floor at its foot."""
        level, found = self.level, []
        if level.tile(column, y) == LADDER:
            top = y
            while level.tile(column, top) == LADDER:
                top += 1
            found.append(top + 1 if level.tile(column, top) in STANDABLE else top)
        below = y - 1
        if level.tile(column, below) in STANDABLE and level.tile(column, below - 1) == LADDER:
            below -= 1
        if level.tile(column, below) == LADDER:
            while level.tile(column, below - 1) == LADDER:
                below -= 1
            found.append(below)
        return [h for h in found if h != y and h in self.heights(column)]

    def moves(self, state: _State, *, climbing: bool = True) -> Iterator[tuple[_State, str, float]]:
        """``(next state, kind, cost)`` of each move from ``state``: a walk or a step to the next
        column either way (cost 1, a step a little more, so a flat way wins), a climb (its height
        times :data:`CLIMB_SLOWNESS`)."""
        column, y = state
        for side in (-1, 1):
            other = column + side
            if not 0 <= other < self.level.columns:
                continue
            for y2 in self.heights(other):
                if abs(y2 - y) <= STEP_TILES and self.clear(column, max(y, y2)) and self.clear(other, max(y, y2)):
                    yield (other, y2), (WALK if y2 == y else STEP), (1.0 if y2 == y else 1.05)
        if climbing:
            for y2 in self.climbs(column, y):
                yield (column, y2), CLIMB, abs(y2 - y) * CLIMB_SLOWNESS

    def box_hit(self, x: float, y: float) -> tuple[int, int] | None:
        """The first solid cell (column, row) a body with its feet at (``x``, ``y``) overlaps."""
        for column in range(math.floor(x - self.half_width + _EPS), math.floor(x + self.half_width - _EPS) + 1):
            for row in range(math.floor(y + _EPS), math.floor(y + self.height - _EPS) + 1):
                if self.level.tile(column, row) in SOLID:
                    return column, row
        return None


def _standing(ground: _Ground, point: Point, who: str) -> _State:
    """The state of a body standing at ``point``; :class:`VidgenError` when it stands on no tile."""
    x, y = point
    height = round(y)
    for column in dict.fromkeys((ground.level.column_at(x - _EPS), ground.level.column_at(x + _EPS))):
        if abs(y - height) <= 1e-3 and height in ground.heights(column):
            return column, height
    raise VidgenError(f"{who} is not standing on a tile (x {x:.2f}, height {y:.2f} tiles), so it cannot walk or jump from there; "
                      "give it a spot (at:) or walk it back onto the tiles")


def _reach(ground: _Ground, start: _State, *, climbing: bool = True) -> dict[_State, tuple[float, _State | None, str]]:
    """Every state reachable on foot from ``start``: its cost, the state before it and the kind of
    move that got there (Dijkstra; ties go to the lower column, then the lower height)."""
    best: dict[_State, tuple[float, _State | None, str]] = {start: (0.0, None, "")}
    heap = [(0.0, start[0], start[1])]
    while heap:
        cost, column, y = heapq.heappop(heap)
        if cost > best[(column, y)][0] + _EPS:
            continue
        for state, kind, step in ground.moves((column, y), climbing=climbing):
            if state not in best or cost + step < best[state][0] - _EPS:
                best[state] = (cost + step, (column, y), kind)
                heapq.heappush(heap, (cost + step, state[0], state[1]))
    return best


def reversed_route(route: Route) -> Route:
    """``route`` walked the other way (from its end to its start)."""
    return Route(route.end, tuple(Leg(leg.kind, leg.end, leg.start) for leg in reversed(route.legs)))


def _route(start: Point, best: dict[_State, tuple[float, _State | None, str]], goal: _State, end_x: float) -> Route:
    """The route from ``start`` through the states leading to ``goal``, ending at ``end_x``."""
    chain: list[tuple[_State, str]] = []
    state: _State | None = goal
    while state is not None:
        chain.append((state, best[state][2]))
        state = best[state][1]
    chain.reverse()
    legs: list[Leg] = []
    x, y = start

    def go(kind: str, to: Point) -> None:
        nonlocal x, y
        if abs(to[0] - x) > _EPS or abs(to[1] - y) > _EPS:
            legs.append(Leg(kind, (x, y), to))
            x, y = to

    for (here, _), (there, kind) in zip(chain, chain[1:]):
        if kind == CLIMB:
            go(WALK, (here[0] + 0.5, y))
            go(CLIMB, (here[0] + 0.5, float(there[1])))
        elif kind == STEP:
            side = there[0] - here[0]
            edge = float(max(here[0], there[0]))
            before = edge - side * STEP_WIDTH / 2
            if (before - x) * side > 0:
                go(WALK, (before, y))
            go(STEP, (edge + side * STEP_WIDTH / 2, float(there[1])))
    last = legs[-1] if legs else None
    if last is not None and last.kind == STEP and (end_x - x) * last.direction < 0:   # it stops right after the step
        legs[-1] = Leg(STEP, last.start, (end_x, last.end[1]))
        x = end_x
    go(WALK, (end_x, y))
    return Route(start, tuple(legs))


def _surface_row(level: Level, y: int) -> int:
    """The map row (from the top, from 1) of the tile feet at height ``y`` stand on."""
    return level.rows - (y - 1)


def _why_not(ground: _Ground, best: dict[_State, tuple[float, _State | None, str]], start: _State, column: int, goal_y: int | None) -> str:
    """Why no walk from ``start`` gets to ``column`` (at ``goal_y``): where the way stops."""
    level = ground.level
    there = sorted(y for c, y in best if c == column)
    if there:
        rows = " or ".join(str(_surface_row(level, y)) for y in there)
        wanted = f", not on row {_surface_row(level, goal_y)}" if goal_y is not None else ""
        return f"on foot it gets to map column {column + 1} only standing on map row {rows}{wanted}"
    side = 1 if column > start[0] else -1
    edge = max(best, key=lambda s: (side * s[0], -best[s][0], s[1]))
    here, y = edge
    other = here + side
    heights = ground.heights(other)
    where = f"the way stops at map column {here + 1}"
    if not any(is_floor(level, other, row) for row in range(level.rows)):
        return f"{where}: a gap at column {other + 1}"
    if any(abs(row + 1 - y) <= STEP_TILES and is_floor(level, other, row) and level.tile(other, row + 1) not in SOLID
           for row in range(level.rows)):   # a floor in reach, but too little room over it
        return f"{where}: no room to pass under the tiles at column {other + 1}"
    lower = [h for h in heights if h < y - STEP_TILES]
    higher = [h for h in heights if h > y + STEP_TILES]
    parts = ([f"a drop of {y - max(lower)} tiles"] if lower else []) + ([f"a wall {min(higher) - y} tiles high"] if higher else [])
    return f"{where}: {' and '.join(parts)} at column {other + 1} (a walk steps up or down at most {STEP_TILES} tile)"


def walk_route(level: Level, start: Point, height: float, goal_x: float, goal_y: float | None = None, *,
               who: str = "it", where: str = "there", hint: str = "jump there instead") -> Route:
    """The route on foot of a body ``height`` tiles tall standing at ``start`` to ``goal_x``
    (tile units; ``goal_y``: standing at that height, else at any height in that column): along
    the tiles, stepping up or down at most :data:`STEP_TILES`, up and down ladders, never across a
    gap. The cheapest way wins (:attr:`Route.effort`). :class:`VidgenError` naming where the way
    stops (``who`` and ``where`` name the body and the goal, ``hint`` ends it) when none gets there."""
    ground = _Ground(level, height)
    state = _standing(ground, start, who)
    best = _reach(ground, state)
    column = level.column_at(goal_x)
    wanted = None if goal_y is None else round(goal_y)
    found = [s for s in best if s[0] == column and (wanted is None or s[1] == wanted)]
    if not found:
        raise VidgenError(f"{who} cannot walk to {where}: {_why_not(ground, best, state, column, wanted)}; {hint}")
    goal = min(found, key=lambda s: (best[s][0], abs(s[1] - state[1]), s[1]))
    return _route(start, best, goal, goal_x)


def _jump_cost(across: float) -> float:
    """How much a jump this many tiles across is avoided: the shortest wins, but a hop of at least
    one tile beats one straight up."""
    return across if across >= 1.0 else 2.0 - across


def _arc_blocker(ground: _Ground, start: Point, end: Point, apex: float) -> str | None:
    """Why a body cannot fly the arc from ``start`` to ``end`` peaking at ``apex``: the solid tile
    it hits, or a cloud it would land on first (falling onto a cloud's top stops it there)."""
    level = ground.level
    span = abs(end[0] - start[0]) + 2 * (apex - min(start[1], end[1]))
    count = max(16, math.ceil(span / _ARC_SAMPLE))
    before = start[1]
    for i in range(1, count + 1):
        x, y = arc_point(start, end, apex, i / count)
        hit = ground.box_hit(x, y)
        if hit is not None:
            return f"the arc hits the tile at {map_cell(level, *hit)}"
        if y < before - _EPS and 0.0 <= x <= level.columns:
            column = level.column_at(x)
            for top in range(math.floor(y + _EPS) + 1, math.floor(before + _EPS) + 1):
                if y < top - _EPS and level.tile(column, top - 1) == CLOUD:
                    return f"it would land on the cloud at {map_cell(level, column, top - 1)} first"
        before = y
    return None


def _apexes(y0: float, y1: float) -> Iterator[float]:
    """The arcs' highest points tried, lowest first."""
    apex = max(y0, y1) + JUMP_CLEARANCE
    while apex <= y0 + MAX_JUMP_UP + JUMP_HEADROOM + _EPS:
        yield apex
        apex += JUMP_APEX_STEP


def plan_jump(level: Level, start: Point, height: float, goal_x: float, goal_y: float | None = None, *,
              who: str = "it", where: str = "there") -> JumpPlan:
    """A jump of a body ``height`` tiles tall standing at ``start`` to ``goal_x`` (tile units;
    ``goal_y``: landing at that height, else on the highest floor in that column a jump reaches).

    It may first walk (on foot, no ladders) to a better take-off point: the one giving the
    shortest jump (at least a tile across when it can), then the shortest walk. The arc is the
    lowest of :func:`_apexes` whose path is clear of solid tiles and lands on no cloud on the way;
    at most :data:`MAX_JUMP_ACROSS` across, :data:`MAX_JUMP_UP` up and :data:`MAX_JUMP_DOWN` down.
    :class:`VidgenError` naming why, from the nearest take-off, when no jump gets there."""
    ground = _Ground(level, height)
    state = _standing(ground, start, who)
    best = _reach(ground, state, climbing=False)
    column = level.column_at(goal_x)
    floors = ground.heights(column)
    if goal_y is not None:
        if round(goal_y) not in floors:
            raise VidgenError(f"{who} cannot jump to {where}: there is no room to stand there (tiles over it)")
        landings = [round(goal_y)]
    elif floors:
        landings = sorted(floors, reverse=True)
    else:
        raise VidgenError(f"{who} cannot jump to {where}: there is nothing to land on in map column {column + 1} (a gap)")
    failures: list[tuple[float, int, str]] = []
    for y1 in landings:
        end = (goal_x, float(y1))
        options: list[tuple[tuple[float, float, float], _State, float, float]] = []
        for (take_column, y0), (walked, _, _) in best.items():
            centre = take_column + 0.5
            xs = [centre, centre + 0.3 * (1 if goal_x > centre else -1)] + ([start[0]] if (take_column, y0) == state else [])
            for x0 in dict.fromkeys(xs):
                if ground.box_hit(x0, y0) is not None:
                    continue
                across, rise = abs(goal_x - x0), y1 - y0
                where_from = f"from map column {take_column + 1}"
                if across > MAX_JUMP_ACROSS + _EPS:
                    failures.append((across, 2, f"{where_from} it is {across:.1f} tiles across, at most {MAX_JUMP_ACROSS:g}; "
                                                "walk closer first or put a platform in between"))
                    continue
                if rise > MAX_JUMP_UP + _EPS or -rise > MAX_JUMP_DOWN + _EPS:
                    way = f"{rise} tiles up, at most {MAX_JUMP_UP:g}" if rise > 0 else f"{-rise} tiles down, at most {MAX_JUMP_DOWN:g}"
                    failures.append((across, 1, f"{where_from} it is {way}; add a step or a ladder on the way"))
                    continue
                blocker = None
                for apex in _apexes(y0, y1):
                    blocker = _arc_blocker(ground, (x0, float(y0)), end, apex)
                    if blocker is None:
                        cost = (_jump_cost(across), walked + 0.01 * abs(x0 - start[0]), apex)
                        options.append((cost, (take_column, y0), x0, apex))
                        break
                if blocker is not None:
                    failures.append((across, 0, f"{where_from} {blocker} (also on higher arcs); take off elsewhere or move the tile"))
        if options:
            _, take_state, x0, apex = min(options, key=lambda o: (o[0], o[1]))
            run_up = _route(start, best, take_state, x0)
            return JumpPlan(run_up, end, apex, flight_seconds(run_up.end, end, apex))
    reason = min(failures)[2] if failures else "there is no room to take off"
    raise VidgenError(f"{who} cannot jump to {where}: {reason}")


def walk_body(world: World, name: str, goal_x: float, goal_y: float | None = None, *, where: str = "there") -> tuple[World, Route]:
    """The rule for ``walk to``: the world once the body ``name`` has walked to the goal
    (:func:`walk_route`) and its route."""
    body = world.body(name)
    route = walk_route(world.level, (body.x, body.y), body.height, goal_x, goal_y, who=f"'{name}'", where=where)
    return world.moved(name, *route.end), route


def jump_body(world: World, name: str, goal_x: float, goal_y: float | None = None, *, where: str = "there") -> tuple[World, JumpPlan]:
    """The rule for ``jump to``: the world once the body ``name`` has jumped to the goal
    (:func:`plan_jump`) and its plan."""
    body = world.body(name)
    plan = plan_jump(world.level, (body.x, body.y), body.height, goal_x, goal_y, who=f"'{name}'", where=where)
    return world.moved(name, *plan.landing), plan


__all__ = [
    "BODY_WIDTH",
    "CLIMB",
    "CLIMB_SLOWNESS",
    "JUMP_GRAVITY",
    "MAX_JUMP_ACROSS",
    "MAX_JUMP_DOWN",
    "MAX_JUMP_UP",
    "SOLID",
    "STEP",
    "STEP_TILES",
    "WALK",
    "JumpPlan",
    "Leg",
    "Route",
    "arc_point",
    "flight_seconds",
    "is_floor",
    "jump_body",
    "map_cell",
    "plan_jump",
    "reversed_route",
    "surface_under",
    "walk_body",
    "walk_route",
]
