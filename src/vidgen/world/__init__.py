"""Platform worlds (DESIGN.md §86): the world model (levels, bodies) and its rules
(:mod:`vidgen.world.moves`: walking, climbing and jumping). Plain data and pure functions:
nothing here imports manim, so a game could reuse them."""

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
from vidgen.world.moves import (
    JumpPlan,
    Leg,
    Route,
    jump_body,
    plan_jump,
    surface_under,
    walk_body,
    walk_route,
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
    "JumpPlan",
    "Leg",
    "Level",
    "Placing",
    "Route",
    "Run",
    "Spot",
    "World",
    "jump_body",
    "parse_level",
    "place_bodies",
    "plan_jump",
    "surface_under",
    "walk_body",
    "walk_route",
]
