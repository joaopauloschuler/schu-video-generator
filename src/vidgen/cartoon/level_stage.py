"""A platform level on a ``stage`` (DESIGN.md §86): from the world's tile units to Manim units.
No manim.

The level's bottom edge is the frame's bottom edge and the stage is exactly as wide as the
level. A tile is ``size`` (a character's height as a fraction of the frame's shorter side)
divided by :data:`~vidgen.world.CHARACTER_TILES`, so characters keep the size the scene gives
them and the level grows around them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from vidgen.cartoon.stage import StageItem, StagePlacement, mark_x
from vidgen.errors import VidgenError
from vidgen.world import (
    BLOCKER,
    CHARACTER_TILES,
    COLLECTIBLES,
    DOOR,
    KEY,
    Item,
    Level,
    Placing,
    World,
    close_door,
    hold_key,
    jump_body,
    open_door,
    place_bodies,
    step_aside,
    walk_body,
)
from vidgen.world.moves import is_floor

#: A character's height (fraction of the frame's shorter side) on a level when the scene gives
#: no ``size``: about eight rows of tiles fit in a 16:9 frame.
LEVEL_SIZE = 0.25


@dataclass(frozen=True)
class LevelFrame:
    """Where a level lies in the scene: ``tile`` (Manim units per tile), the stage's width (the
    level's), and the scene x and y of the level's left and bottom edges."""

    tile: float
    stage_width: float
    left: float
    bottom: float

    def point(self, x: float, y: float) -> tuple[float, float]:
        """A world point (tile units) in Manim units."""
        return (self.left + x * self.tile, self.bottom + y * self.tile)

    def x_fraction(self, x: float) -> float:
        """A world x as a fraction of the stage (0 left edge, 1 right edge)."""
        return x * self.tile / self.stage_width

    def world_x(self, fraction: float) -> float:
        """A fraction of the stage as a world x (tile units)."""
        return fraction * self.stage_width / self.tile

    def world_point(self, x: float, y: float) -> tuple[float, float]:
        """A scene point (Manim units) in tile units (the inverse of :meth:`point`)."""
        return ((x - self.left) / self.tile, (y - self.bottom) / self.tile)


def level_frame(level: Level, size: float, frame_width: float, frame_height: float) -> LevelFrame:
    """How ``level`` lies in a frame ``frame_width`` x ``frame_height`` (Manim units) for
    characters ``size`` tall (fraction of the shorter side)."""
    tile = size * min(frame_width, frame_height) / CHARACTER_TILES
    width = level.columns * tile
    return LevelFrame(tile, width, -width / 2, -frame_height / 2)


def level_fit_problems(level: Level, size: float, frame_width: float, frame_height: float) -> list[str]:
    """Why ``level`` does not fit the frame at ``size``: narrower than the frame (the camera would
    see past its ends), or tiles above the frame's top edge (the camera follows sideways only)."""
    frame = level_frame(level, size, frame_width, frame_height)
    problems = []
    columns = frame_width / frame.tile
    if level.columns < columns - 1e-9:
        problems.append(f"the map is {level.columns} columns wide, narrower than the frame ({columns:.1f} columns at size {size:g}); "
                        "add columns or make the characters larger (size)")
    rows = frame_height / frame.tile
    if level.used_rows() > rows + 1e-9:
        problems.append(f"the map's tiles reach {level.used_rows()} rows up, above the frame's top ({rows:.1f} rows at size {size:g}); "
                        "lower them or make the characters smaller (size)")
    return problems


@dataclass(frozen=True)
class LevelProps:
    """The stage's props and characters that are story props of its level (DESIGN.md §86.8): its
    door props (name -> whether it starts open), the level's ``locks`` (door -> the prop that is
    its key) and ``blockers`` (characters in the way until they step aside)."""

    doors: Mapping[str, bool] = field(default_factory=dict)
    locks: Mapping[str, str] = field(default_factory=dict)
    blockers: Sequence[str] = ()


def level_world(level: Level, items: Sequence[StageItem], marks: Mapping[str, float] | None = None,
                props: LevelProps | None = None) -> World:
    """The world with each stage item standing where its ``at`` says: a spot of the level by
    name, else a mark or an x (fraction of the stage) on the highest tile there; with ``props``,
    its doors, keys and blockers as the world's items too (after the map's coins and stars)."""
    spots = set(level.spot_names())
    placings = []
    for item in items:
        if isinstance(item.at, str) and item.at in spots:
            placings.append(Placing(item.name, item.kind, spot=item.at, scale=item.scale))
            continue
        try:
            fraction = mark_x(item.at, marks)
        except ValueError as exc:
            raise VidgenError(f"'{item.name}': {exc}") from None
        placings.append(Placing(item.name, item.kind, x=fraction * level.columns, scale=item.scale))
    world = place_bodies(level, placings)
    if props is None:
        return world
    found = []
    for body in world.bodies:
        if body.name in props.doors:
            found.append(Item(body.name, DOOR, body.x, body.y, body.height, key=props.locks.get(body.name), open=props.doors[body.name]))
        elif body.name in props.locks.values():
            found.append(Item(body.name, KEY, body.x, body.y, body.height))
        elif body.name in props.blockers:
            found.append(Item(body.name, BLOCKER, body.x, body.y, body.height))
    return world.with_items(*found)


def level_layout(
    level: Level,
    items: Sequence[StageItem],
    *,
    marks: Mapping[str, float] | None = None,
    size: float,
    frame_width: float,
    frame_height: float,
) -> list[StagePlacement]:
    """Where each item goes on a level, like :func:`~vidgen.cartoon.stage.stage_layout` (all at
    depth 0, in list order): its feet on the tile it stands on, raised by its ``lift`` (frame
    heights) and ``hang`` (its heights)."""
    frame = level_frame(level, size, frame_width, frame_height)
    world = level_world(level, items, marks)
    placements = []
    for index, (item, body) in enumerate(zip(items, world.bodies)):
        x, y = frame.point(body.x, body.y)
        unit = CHARACTER_TILES * frame.tile   # a character of scale 1
        placements.append(StagePlacement(
            name=item.name, kind=item.kind, index=index, x_fraction=frame.x_fraction(body.x), depth=0.0,
            feet=(x, y + item.lift * frame_height + item.hang * unit), height=body.height * frame.tile,
        ))
    return placements


@dataclass(frozen=True)
class LevelGoal:
    """Where a walk or a jump on a level goes: ``x`` and, when the place says, the height ``y``
    to stand at (tile units; ``None``: any floor in that column), and how messages name it."""

    x: float
    y: float | None
    label: str


def level_goal(level: Level, place: Any, marks: Mapping[str, float] | None = None) -> LevelGoal:
    """The goal of a walk or a jump to ``place``: a spot of the level (its x and height), a mark
    or an x 0..1 of the stage (any floor in that column), or ``{column, row}``, a tile of the map
    as the author reads it (from the top left, from 1: standing on its top). :class:`VidgenError`
    for an unknown mark or a cell with nothing to stand on."""
    if isinstance(place, Mapping):
        column, row = int(place["column"]) - 1, level.rows - int(place["row"])
        where = f"map row {place['row']}, column {place['column']}"
        if not (0 <= column < level.columns and 0 <= row < level.rows):
            raise VidgenError(f"{where} is outside the map ({level.rows} rows, {level.columns} columns)")
        if not is_floor(level, column, row):
            raise VidgenError(f"{where} is not a tile to stand on (a ground #, platform =, cloud ~ or the top of a ladder |)")
        return LevelGoal(column + 0.5, float(row + 1), f"the tile at {where}")
    if isinstance(place, str) and place in level.spot_names():
        spot = level.spot(place)
        return LevelGoal(spot.x, spot.y, f"spot '{place}'")
    try:
        fraction = mark_x(place, marks)
    except ValueError as exc:
        raise VidgenError(str(exc)) from None
    return LevelGoal(fraction * level.columns, None, f"'{place}'" if isinstance(place, str) else f"x {place:g}")


@dataclass(frozen=True)
class LevelStep:
    """One action of a scene as ``vidgen validate`` replays it on a level: its location
    (``beats[1].actions[0]``) and beat id, the action, the characters (or props: a door, a key)
    it acts on, its place (``to``; ``None``: none given) and its other ``options`` as written."""

    location: str
    beat: str
    action: str
    names: tuple[str, ...]
    place: Any = None
    options: Mapping[str, Any] = field(default_factory=dict)


#: Actions after which the replay no longer knows where a character stands on the level.
LEVEL_UNTRACKED = frozenset({"keyframes", "move_along", "get_in", "ride_to", "get_out"})
#: The moves the replay plans with the rules, and the actions on the level's story props it
#: follows (who holds a key, doors, blockers; DESIGN.md §86.8).
LEVEL_MOVES = frozenset({"walk_to", "run_to", "jump", "enter", "exit"})
LEVEL_PROP_ACTIONS = frozenset({"pick_up", "hold", "give", "put_down", "throw", "let_go", "blow_away", "open", "close", "step_aside"})


@dataclass
class _Replay:
    world: World
    marks: Mapping[str, float] | None
    away: set[str] = field(default_factory=set)
    problems: list[tuple[str, str]] = field(default_factory=list)


def level_move_problems(level: Level, items: Sequence[StageItem], steps: Sequence[LevelStep], marks: Mapping[str, float] | None = None,
                        *, entering: Sequence[str] = (), props: LevelProps | None = None) -> list[tuple[str, str]]:
    """The walks and jumps of a scene replayed in order on its level with the rules
    (:func:`~vidgen.world.moves.walk_body`, :func:`~vidgen.world.moves.jump_body`), with its
    story ``props`` (:func:`~vidgen.world.story_props.open_door`...): a walk that cannot get there
    on foot, a jump that cannot be made, a closed door or a blocker in the way, a locked door
    opened without its key, a reaction on a pickup with nothing to pick up, as ``(location.option,
    message naming the beat)``. ``entering``: characters off stage until their ``enter`` (it brings
    them to its ``to``, else their own place). A character is no longer followed after a problem,
    an ``exit`` or a :data:`LEVEL_UNTRACKED` action (until it enters again)."""
    start = level_world(level, items, marks, props)
    replay = _Replay(start, marks, set(entering))
    for step in steps:
        if step.action in LEVEL_PROP_ACTIONS:
            _replay_prop_step(replay, start, step)
            continue
        for name in step.names:
            _replay_step(replay, start, step, name)
    return replay.problems


def _keys_let_go(world: World, step: LevelStep, holder: str) -> list[str]:
    """The keys ``holder`` lets go of with ``step`` (its ``prop`` option, else whatever key it holds)."""
    chosen = step.options.get("prop")
    held = [i.name for i in world.items if i.kind == KEY and i.holder == holder]
    return [name for name in held if chosen is None or name == chosen]


def _replay_prop_step(replay: _Replay, start: World, step: LevelStep) -> None:
    """A step on the level's story props: who holds a key, a door opening or closing, a blocker
    stepping aside (and walking off, with ``to``)."""
    world, o = replay.world, step.options
    try:
        if step.action in ("pick_up", "hold"):
            for name in step.names:
                replay.world = hold_key(replay.world, str(o.get("to")), name)
        elif step.action == "give":
            for name in step.names:
                for key in _keys_let_go(world, step, name):
                    replay.world = hold_key(replay.world, key, str(o.get("to")))
        elif step.action in ("put_down", "throw", "let_go"):
            for name in step.names:
                for key in _keys_let_go(world, step, name):
                    replay.world = hold_key(replay.world, key, None)
        elif step.action == "blow_away":
            for name in step.names:
                replay.world = hold_key(replay.world, name, None)
        elif step.action == "open":
            by = o.get("by")
            for name in step.names:
                replay.world = open_door(replay.world, name, by, reach=by is not None and by not in replay.away)
        elif step.action == "close":
            for name in step.names:
                replay.world = close_door(replay.world, name)
        elif step.action == "step_aside":
            for name in step.names:
                replay.world = step_aside(replay.world, name)
                if step.place is None:
                    replay.away.add(name)   # it stepped back off the path: no longer followed
                else:
                    _replay_step(replay, start, replace(step, action="walk_to"), name)
    except VidgenError as exc:
        option = "by" if step.action == "open" and o.get("by") is not None else "target"
        replay.problems.append((f"{step.location}.{option}", f"beat '{step.beat}': {exc}"))


def _replay_step(replay: _Replay, start: World, step: LevelStep, name: str) -> None:
    if step.action == "enter":
        replay.away.discard(name)
        if step.place is None:
            home = start.body(name)
            replay.world = replay.world.moved(name, home.x, home.y)
            return
        goal = level_goal(start.level, step.place, replay.marks)
        y = goal.y if goal.y is not None else start.level.top_surface(start.level.column_at(goal.x))
        replay.world = replay.world.moved(name, goal.x, y if y is not None else 0.0)
        return
    if step.action == "exit" or step.action in LEVEL_UNTRACKED:
        replay.away.add(name)
        return
    if name in replay.away or step.place is None:
        return
    try:
        goal = level_goal(start.level, step.place, replay.marks)
        move = jump_body if step.action == "jump" else walk_body
        before = replay.world
        replay.world = move(replay.world, name, goal.x, goal.y, where=goal.label)[0]
    except VidgenError as exc:
        hint = f" (- jump: {name}, to: {_place_text(step.place)})" if step.action != "jump" and "jump there instead" in str(exc) else ""
        replay.problems.append((f"{step.location}.to", f"beat '{step.beat}': {exc}{hint}"))
        replay.away.add(name)
        return
    react = step.options.get("react")
    if isinstance(react, Mapping) and react.get("when") == "pickup" and not _picked(before, replay.world):
        replay.problems.append((f"{step.location}.react", f"beat '{step.beat}': '{name}' picks up nothing on the way there, "
                                                          "so a reaction when: pickup never plays; react when: arrive (or land) instead"))


def _picked(before: World, after: World) -> bool:
    """Whether a coin or a star was picked up between ``before`` and ``after``."""
    return any(item.holder is not None and before.item(item.name) is not None and before.item(item.name).holder is None
               for item in after.items if item.kind in COLLECTIBLES)


def _place_text(place: Any) -> str:
    if isinstance(place, Mapping):
        return "{column: %s, row: %s}" % (place["column"], place["row"])
    return str(place)


__all__ = [
    "LEVEL_MOVES",
    "LEVEL_PROP_ACTIONS",
    "LEVEL_SIZE",
    "LEVEL_UNTRACKED",
    "LevelFrame",
    "LevelGoal",
    "LevelProps",
    "LevelStep",
    "level_fit_problems",
    "level_frame",
    "level_goal",
    "level_layout",
    "level_move_problems",
    "level_world",
]
