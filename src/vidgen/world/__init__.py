"""Platform worlds (DESIGN.md §86): the world model (levels, bodies) and, from Step 151, its
rules. Plain data and pure functions: nothing here imports manim, so a game could reuse them."""

from vidgen.world.level import (
    AIR,
    CLOUD,
    GROUND,
    LADDER,
    PLATFORM,
    STANDABLE,
    TILE_SYMBOLS,
    Level,
    Run,
    Spot,
    parse_level,
)
from vidgen.world.world import CHARACTER_TILES, Body, Placing, World, place_bodies

__all__ = [
    "AIR",
    "CHARACTER_TILES",
    "CLOUD",
    "GROUND",
    "LADDER",
    "PLATFORM",
    "STANDABLE",
    "TILE_SYMBOLS",
    "Body",
    "Level",
    "Placing",
    "Run",
    "Spot",
    "World",
    "parse_level",
    "place_bodies",
]
