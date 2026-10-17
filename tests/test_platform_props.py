"""Step 152: story props on a platform level — coins and stars on the map picked up on the way
(mid-jump too), closed and locked doors and friendly blockers in the way of walks and jumps,
opening a door with its key, stepping aside (the rules, no manim), the stage's checks naming the
beat, reactions during and after a move, and a tiny render of the whole story."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from test_platform_moves import action_problems
from vidgen.cartoon.level_stage import LevelProps, LevelStep, level_move_problems, level_world
from vidgen.cartoon.stage import StageItem
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.world import (
    BLOCKER,
    COIN,
    DOOR,
    KEY,
    STAR,
    Item,
    Placing,
    close_door,
    hold_key,
    jump_body,
    jump_pickups,
    obstacles_in,
    open_door,
    parse_level,
    place_bodies,
    plan_jump,
    route_pickups,
    step_aside,
    walk_body,
    walk_route,
)

TALL = 2.0

#: columns  0         1         2
#:          012345678901234567890123
MAP = """
........................
..........*.............
.a..k.$$d.......t.....h.
#########...############
"""
SPOTS = {"a": "start", "k": "key_spot", "d": "gate_spot", "t": "path", "h": "home"}


def story_world(*, locked: bool = True) -> Any:
    level = parse_level(MAP, SPOTS)
    world = place_bodies(level, [Placing("pip", "character", spot="start"), Placing("tobble", "character", spot="path"),
                                 Placing("gate", "prop", spot="gate_spot"), Placing("gold_key", "prop", spot="key_spot", scale=0.2)])
    gate, key, tobble = world.body("gate"), world.body("gold_key"), world.body("tobble")
    return world.with_items(Item("gate", DOOR, gate.x, gate.y, gate.height, key="gold_key" if locked else None),
                            Item("gold_key", KEY, key.x, key.y, key.height), Item("tobble", BLOCKER, tobble.x, tobble.y, tobble.height))


# ----- the map's coins and stars (no manim) -------------------------------------------------------


def test_coins_and_stars_are_map_symbols_named_in_map_order() -> None:
    level = parse_level(MAP, SPOTS)
    assert [(i.name, i.kind, i.x, i.y) for i in level.items] == [
        ("star_1", STAR, 10.5, 2.5), ("coin_1", COIN, 6.5, 1.5), ("coin_2", COIN, 7.5, 1.5)]
    assert level.tile(6, 1) == "air"   # a coin floats in an air cell
    assert place_bodies(level, []).items == level.items
    with pytest.raises(VidgenError, match=r"unknown symbol '%' \(symbols: .*\$ a coin, \* a star, a letter: a spot\)"):
        parse_level("a%\n##")


def test_walks_pick_up_what_they_touch() -> None:
    world = story_world()
    route = walk_route(world.level, (1.5, 1.0), TALL, 7.5)
    found = route_pickups(route, TALL, world.items)
    assert [item.name for item, _ in found] == ["coin_1", "coin_2"]
    shares = [share for _, share in found]
    assert 0 < shares[0] < shares[1] < 1   # in the order it touches them, as shares of the walk
    assert route_pickups(walk_route(world.level, (1.5, 1.0), TALL, 4.5), TALL, world.items) == []   # stops short of them
    moved, _ = walk_body(world, "pip", 7.5)
    assert {i.name: i.holder for i in moved.items if i.kind == COIN} == {"coin_1": "pip", "coin_2": "pip"}
    assert route_pickups(walk_route(moved.level, (1.5, 1.0), TALL, 7.5), TALL, moved.items) == []   # picked up once


def test_a_jump_picks_up_a_star_mid_air() -> None:
    level = parse_level(MAP, SPOTS)
    plan = plan_jump(level, (7.5, 1.0), TALL, 13.5, 1.0)
    on_foot, flying = jump_pickups(plan, TALL, level.items)
    assert [(i.name, share) for i, share in on_foot] == [("coin_2", 0.0)]   # it stands on that coin as it sets off
    assert [i.name for i, _ in flying] == ["star_1"] and 0.1 < flying[0][1] < 0.5   # rising over the gap, in the air


# ----- doors, keys, blockers (no manim) -----------------------------------------------------------


def test_a_locked_door_blocks_walks_and_jumps_until_its_key_opens_it() -> None:
    world = story_world()
    with pytest.raises(VidgenError, match="'pip' cannot walk to spot 'home': the locked door 'gate' is in the way at map column 9; "
                                          r"open it first with its key 'gold_key' \(- open: gate, by: <who holds gold_key>\)"):
        walk_body(world, "pip", 22.5, 1.0, where="spot 'home'")
    with pytest.raises(VidgenError, match="'pip' cannot jump to there: the locked door 'gate' is in the way at map column 9"):
        jump_body(world, "pip", 13.5, 1.0)
    with pytest.raises(VidgenError, match=r"the door 'gate' is locked: say who opens it with its key 'gold_key' \(- open: gate, by: <who holds gold_key>\)"):
        open_door(world, "gate")
    with pytest.raises(VidgenError, match=r"'pip' cannot open the door 'gate': it is locked and 'pip' does not hold its key 'gold_key'; "
                                          r"pick it up first \(- pick_up: pip, to: gold_key\)"):
        open_door(world, "gate", "pip")
    held = hold_key(world, "gold_key", "pip")
    with pytest.raises(VidgenError, match=r"'pip' is too far from the door 'gate' to open it \(7.0 tiles; at most 1.6\)"):
        open_door(held, "gate", "pip")
    there, _ = walk_body(held, "pip", 7.5)
    opened = open_door(there, "gate", "pip")
    assert opened.item("gate").open and not opened.item("gate").blocks
    landed, plan = jump_body(opened, "pip", 13.5, 1.0)
    assert plan.landing == (13.5, 1.0) and landed.item("star_1").holder == "pip"   # through the open door, the star on the way
    assert close_door(opened, "gate").item("gate").blocks
    assert open_door(story_world(locked=False), "gate").item("gate").open   # an unlocked door opens without a key


def test_a_blocker_is_in_the_way_until_it_steps_aside() -> None:
    world = story_world(locked=False)
    world = open_door(world, "gate")
    world = jump_body(world, "pip", 13.5, 1.0)[0]
    with pytest.raises(VidgenError, match=r"'tobble' is in the way at map column 17; ask it to move first \(- step_aside: tobble\)"):
        walk_body(world, "pip", 22.5, 1.0)
    assert [o.item.name for o in obstacles_in(world)] == ["tobble"] and obstacles_in(world, besides="tobble") == ()
    walk_body(world, "tobble", 20.5)   # a blocker is not in its own way
    moved = step_aside(world, "tobble")
    assert walk_body(moved, "pip", 22.5, 1.0)[1].end == (22.5, 1.0)
    with pytest.raises(VidgenError, match="'pip' is not a blocker of the level"):
        step_aside(world, "pip")


def test_an_obstacle_shuts_its_column_only_up_to_the_tile_above_it() -> None:
    level = parse_level("..........\n.a..====..\n..........\n..........\n##########")
    world = place_bodies(level, [Placing("pip", "character", spot="a")])
    upper = place_bodies(level, [Placing("pip", "character", x=4.5)])   # on the plank
    blocker = Item("tobble", BLOCKER, 5.5, 1.0, 1.0)
    on_plank = upper.with_items(blocker)
    assert walk_body(on_plank, "pip", 7.5)[1].end == (7.5, 4.0)   # the way over its head is open
    with pytest.raises(VidgenError, match="'tobble' is in the way at map column 6"):
        walk_body(world.with_items(blocker), "pip", 8.5)


# ----- the replay (no manim) -----------------------------------------------------------------------


ITEMS = [StageItem("gate", "prop", "gate_spot"), StageItem("gold_key", "prop", "key_spot"), StageItem("pip", "character", "start"),
         StageItem("kit", "character", "path")]
PROPS = LevelProps({"gate": False}, {"gate": "gold_key"}, ("kit",))


def replay(steps: list[LevelStep]) -> list[tuple[str, str]]:
    return level_move_problems(parse_level(MAP, SPOTS), ITEMS, steps, props=PROPS)


def test_the_world_has_the_stage_story_props() -> None:
    world = level_world(parse_level(MAP, SPOTS), ITEMS, props=PROPS)
    assert {i.name: (i.kind, i.key) for i in world.items if i.kind not in (COIN, STAR)} == {
        "gate": (DOOR, "gold_key"), "gold_key": (KEY, None), "kit": (BLOCKER, None)}


def test_the_replay_follows_keys_doors_and_blockers() -> None:
    steps = [
        LevelStep("beats[0].actions[0]", "s_b1", "walk_to", ("pip",), "key_spot"),
        LevelStep("beats[0].actions[1]", "s_b1", "open", ("gate",), options={"by": "pip"}),   # no key yet
        LevelStep("beats[1].actions[0]", "s_b2", "pick_up", ("pip",), options={"to": "gold_key"}),
        LevelStep("beats[1].actions[1]", "s_b2", "walk_to", ("pip",), {"column": 8, "row": 4}, {"react": {"when": "pickup"}}),
        LevelStep("beats[2].actions[0]", "s_b3", "open", ("gate",), options={"by": "pip"}),
        LevelStep("beats[2].actions[1]", "s_b3", "jump", ("pip",), {"column": 14, "row": 4}),
        LevelStep("beats[3].actions[0]", "s_b4", "walk_to", ("pip",), "home"),   # kit in the way
    ]
    assert replay(steps) == [
        ("beats[0].actions[1].by", "beat 's_b1': 'pip' cannot open the door 'gate': it is locked and 'pip' does not hold its key 'gold_key'; "
                                   "pick it up first (- pick_up: pip, to: gold_key)"),
        ("beats[3].actions[0].to", "beat 's_b4': 'pip' cannot walk to spot 'home': 'kit' is in the way at map column 17; "
                                   "ask it to move first (- step_aside: kit)"),
    ]
    fixed = [*steps[:1], *steps[2:6], LevelStep("x", "s_b4", "step_aside", ("kit",)), steps[6]]
    assert replay(fixed) == []
    gave = [steps[0], steps[2], LevelStep("g", "s_b2", "give", ("pip",), options={"to": "kit"}), steps[3],
            LevelStep("o", "s_b3", "open", ("gate",), options={"by": "pip"})]
    assert replay(gave)[0][1].endswith("does not hold its key 'gold_key' ('kit' holds it)")


def test_a_reaction_on_a_pickup_needs_something_to_pick_up() -> None:
    steps = [LevelStep("beats[0].actions[0]", "s_b1", "walk_to", ("pip",), "key_spot", {"react": {"when": "pickup", "expression": "happy"}})]
    assert replay(steps) == [("beats[0].actions[0].react", "beat 's_b1': 'pip' picks up nothing on the way there, so a reaction when: pickup "
                                                           "never plays; react when: arrive (or land) instead")]


# ----- the stage's checks --------------------------------------------------------------------------


LEVEL = {"map": MAP, "spots": SPOTS, "locks": {"gate": "gold_key"}, "blockers": ["kit"]}
STORY_PROPS = [{"prop": "door", "name": "gate", "at": "gate_spot"}, {"prop": "key", "name": "gold_key", "at": "key_spot"}]


def story_project(make_project, beats: list[dict[str, Any]], **level: Any) -> Project:
    params = {"level": {**LEVEL, **level}, "idle": False, "props": STORY_PROPS,
              "characters": [{"name": "pip", "at": "start"}, {"name": "kit", "at": "path", "facing": "left"}]}
    scenes = [{"id": "hills", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


def test_validate_refuses_a_locked_door_and_a_blocker_naming_the_beat(make_project) -> None:
    project = story_project(make_project, [
        {"text": "Pip runs to the gate.", "actions": [{"run_to": "pip", "to": "home"}]},
        {"text": "Pip tries the door.", "actions": [{"open": "gate"}]},
    ])
    assert action_problems(project) == [
        ("beats[0].actions[0].to", "beat 'hills_b1': 'pip' cannot walk to spot 'home': the locked door 'gate' is in the way at map column 9; "
                                   "open it first with its key 'gold_key' (- open: gate, by: <who holds gold_key>)"),
        ("beats[1].actions[0].target", "beat 'hills_b2': the door 'gate' is locked: say who opens it with its key 'gold_key' "
                                       "(- open: gate, by: <who holds gold_key>)"),
    ]


def test_validate_accepts_the_whole_story(make_project) -> None:
    project = story_project(make_project, STORY)
    assert action_problems(project) == []


@pytest.mark.parametrize(
    "level,props,message",
    [
        ({"locks": {"gold_key": "gate"}}, None, "level.locks: 'gold_key' is not a door prop of the stage"),
        ({"locks": {"gate": "nothing"}}, None, "the key 'nothing' of 'gate' is not a prop of the stage"),
        ({"blockers": ["gate"]}, None, r"level.blockers\[0\]: 'gate' is not a character on the stage"),
        ({}, [*STORY_PROPS, {"prop": "box", "name": "coin_1", "at": "home"}], "'coin_1' is the name of a coin on the map"),
    ],
)
def test_bad_story_props(level: dict[str, Any], props: Any, message: str) -> None:
    import re

    with pytest.raises(Exception, match=re.compile(message)):
        stage_params(level={**LEVEL, **level}, props=props or STORY_PROPS,
                     characters=[{"name": "pip", "at": "start"}, {"name": "kit", "at": "path"}])


@pytest.mark.parametrize(
    "action,message",
    [
        ({"step_aside": "pip"}, "'pip' is not one of the level's blockers"),
        ({"walk_to": "pip", "to": "key_spot", "react": {"when": "land", "expression": "happy"}}, "when: land is for a jump"),
        ({"walk_to": "pip", "to": "key_spot", "react": {"when": "arrive"}}, "an expression and / or an effect"),
        ({"walk_to": "pip", "to": "key_spot", "react": {"expression": "nope"}}, "nope"),
        ({"jump": "pip", "react": {"effect": "sparkle"}}, "react goes with a jump to a place"),
        ({"open": "gate", "by": "nobody"}, "'nobody' is not a character on the stage"),
    ],
)
def test_bad_story_actions(make_project, action: dict[str, Any], message: str) -> None:
    project = story_project(make_project, [{"text": "Pip moves.", "actions": [action]}])
    assert any(message in text for _, text in action_problems(project)), action_problems(project)


def test_tiles_and_reactions_need_a_level(make_project) -> None:
    scenes = [{"id": "hills", "type": "stage", "params": {"characters": [{"name": "pip", "at": "left"}]},
               "beats": [{"text": "Pip walks.", "actions": [{"walk_to": "pip", "to": {"column": 3, "row": 2}},
                                                             {"walk_to": "pip", "to": "right", "react": {"expression": "happy"}}]}]}]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))
    texts = [text for _, text in action_problems(project)]
    assert any("a tile {column, row} is a place on a platform level" in t for t in texts)
    assert any("react is for moves on a platform level" in t for t in texts)


def test_directing_knows_the_x_of_a_tile(make_project) -> None:
    from vidgen import extensions, registry
    from vidgen.cartoon.directing import stage_frame

    project = story_project(make_project, [{"text": "Pip walks."}])
    with extensions.project_session(project) as theme:
        params = registry.get("stage").cls.validate_params(project.scene("hills").params, theme)
        frame = stage_frame(project, params)
    assert frame.place_x({"column": 8, "row": 4}) == pytest.approx(frame.place_x((7.5) / 24))


# ----- render --------------------------------------------------------------------------------------


STORY = [
    {"text": "Pip walks to the shiny key.", "actions": [{"walk_to": "pip", "to": "key_spot"}]},
    {"text": "Pip picks it up and smiles.", "actions": [{"pick_up": "pip", "to": "gold_key"},
                                                      {"walk_to": "pip", "to": {"column": 8, "row": 4}, "at": 0.3,
                                                       "react": {"when": "pickup", "expression": "happy", "effect": "sparkle"}}]},
    {"text": "The key opens the gate!", "actions": [{"open": "gate", "by": "pip"}]},
    {"text": "Pip jumps over the gap and catches a star.", "actions": [{"jump": "pip", "to": {"column": 14, "row": 4},
                                                                         "react": {"when": "land", "expression": "laughing"}}]},
    {"text": "Please, Kit, may I pass? Kit steps aside.", "actions": [{"step_aside": "kit", "at": 0.5}]},
    {"text": "And Pip walks home.", "actions": [{"walk_to": "pip", "to": "home"}]},
]


@pytest.mark.render
def test_the_story_renders(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.scenes.stage import Stage

    symbols: list[Any] = []
    moved = Stage.level_moved

    def level_moved(self: Any, character: Any, animation: Any) -> None:
        moved(self, character, animation)
        parts = getattr(animation, "animations", [animation])
        symbols.extend(p.reaction.symbol for p in parts if getattr(p, "reaction", None) is not None and p.reaction.symbol is not None)

    monkeypatch.setattr(Stage, "level_moved", level_moved)
    project = story_project(make_project, STORY)
    scene, _ = render_with_layout(project, "hills", tmp_path / "media")
    frame = scene.params.level_frame(scene.frame_width, scene.frame_height)
    pip = scene.cast["pip"]
    assert pip.feet()[:2] == pytest.approx(frame.point(22.5, 1.0), abs=1e-6)
    assert all(item.gone for item in scene.level_pickups.values())   # two coins on the walk, the star mid-jump
    assert {i.name: i.holder for i in scene.level_state.items if i.kind in (COIN, STAR)} == {"star_1": "pip", "coin_1": "pip", "coin_2": "pip"}
    assert scene.props["gate"].shape == "open" and scene.level_state.item("gate").open
    assert scene.props["gold_key"].held_by == "pip"
    assert scene.level_state.item("kit").aside and scene.cast["kit"].stage_depth == pytest.approx(0.3)
    laughing = pip.posed_state(expression="laughing").parts
    assert pip.state().parts["mouth"] == laughing["mouth"]   # the landing reaction stayed on
    assert [(m.kind, m.effect_of) for m in symbols] == [("sparkle", "pip")] and symbols[0].age > 0   # popped on the first coin
