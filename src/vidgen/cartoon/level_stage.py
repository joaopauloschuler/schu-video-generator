"""A platform level on a ``stage`` (DESIGN.md §86): from the world's tile units to Manim units.
No manim.

The level's bottom edge is the frame's bottom edge and the stage is exactly as wide as the
level. A tile is ``size`` (a character's height as a fraction of the frame's shorter side)
divided by :data:`~vidgen.world.CHARACTER_TILES`, so characters keep the size the scene gives
them and the level grows around them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vidgen.cartoon.stage import StageItem, StagePlacement, mark_x
from vidgen.errors import VidgenError
from vidgen.world import CHARACTER_TILES, Level, Placing, World, place_bodies

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


def level_world(level: Level, items: Sequence[StageItem], marks: Mapping[str, float] | None = None) -> World:
    """The world with each stage item standing where its ``at`` says: a spot of the level by
    name, else a mark or an x (fraction of the stage) on the highest tile there."""
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
    return place_bodies(level, placings)


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


__all__ = ["LEVEL_SIZE", "LevelFrame", "level_fit_problems", "level_frame", "level_layout", "level_world"]
