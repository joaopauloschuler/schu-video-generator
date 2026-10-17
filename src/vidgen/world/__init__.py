"""Platform worlds (DESIGN.md §86): the world model (levels, bodies, story props) and its rules
(:mod:`vidgen.world.moves`: walking, climbing and jumping, picking up coins and stars, closed doors
and blockers in the way; :mod:`vidgen.world.story_props`: doors, keys, blockers). Plain data and
pure functions: nothing here imports manim, so a game could reuse them."""

from vidgen.world.items import BLOCKER, COIN, COLLECTIBLES, DOOR, ITEM_SYMBOLS, KEY, STAR, Item
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
    Obstacle,
    Route,
    jump_body,
    jump_pickups,
    obstacles_in,
    plan_jump,
    route_pickups,
    surface_under,
    walk_body,
    walk_route,
)
from vidgen.world.story_props import close_door, hold_key, open_door, step_aside
from vidgen.world.world import CHARACTER_TILES, Body, Placing, World, place_bodies

__all__ = [
    "AIR",
    "BLOCKER",
    "CHARACTER_TILES",
    "CLOUD",
    "COIN",
    "COLLECTIBLES",
    "DOOR",
    "GROUND",
    "ITEM_SYMBOLS",
    "KEY",
    "LADDER",
    "PLATFORM",
    "STANDABLE",
    "STAR",
    "TILE_SYMBOLS",
    "Body",
    "Item",
    "JumpPlan",
    "Leg",
    "Level",
    "Obstacle",
    "Placing",
    "Route",
    "Run",
    "Spot",
    "World",
    "close_door",
    "hold_key",
    "jump_body",
    "jump_pickups",
    "obstacles_in",
    "open_door",
    "parse_level",
    "place_bodies",
    "plan_jump",
    "route_pickups",
    "step_aside",
    "surface_under",
    "walk_body",
    "walk_route",
]
