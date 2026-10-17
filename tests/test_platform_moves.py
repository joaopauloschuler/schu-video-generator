"""Step 151: walking and jumping on a platform level — the rules (routes along the tiles, ladders,
one-way clouds, planned jump arcs and their refusals, no manim), the stage's checks of a scene's
walks and jumps, automatic directing, and a tiny render of the moves timed in their beats."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen import actions, extensions, registry
from vidgen.cartoon.level_stage import LevelGoal, LevelStep, level_goal, level_move_problems
from vidgen.cartoon.stage import StageItem
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.world import Placing, World, jump_body, parse_level, place_bodies, plan_jump, surface_under, walk_body, walk_route
from vidgen.world.moves import CLIMB, MAX_JUMP_ACROSS, MIN_FLIGHT_SECONDS, STEP, WALK, arc_point, flight_seconds, reversed_route

TALL = 2.0   # a character of scale 1 is two tiles tall

#: columns  0         1         2
#:          012345678901234567890123
MAP = """
................~~~.....
........b...............
.....|====....=====..c..
.a...|...............###
#########...####...#####
"""


def kinds(route: Any) -> list[str]:
    return [leg.kind for leg in route.legs]


# ----- walking (no manim) -------------------------------------------------------------------------


def test_a_flat_walk_is_one_leg() -> None:
    level = parse_level("a.........\n##########")
    route = walk_route(level, (0.5, 1.0), TALL, 7.25)
    assert kinds(route) == [WALK] and route.end == (7.25, 1.0) and route.effort == pytest.approx(6.75)
    assert walk_route(level, (0.5, 1.0), TALL, 0.5).legs == ()   # already there
    assert reversed_route(route).start == (7.25, 1.0) and reversed_route(route).end == (0.5, 1.0)


def test_walks_step_up_and_down_one_tile_at_the_column_edges() -> None:
    level = parse_level("..........\n....###...\n.a.#####..\n##########")
    route = walk_route(level, (1.5, 1.0), TALL, 8.5)
    assert kinds(route) == [WALK, STEP, WALK, STEP, WALK, STEP, WALK, STEP, WALK]
    up = route.legs[1]
    assert up.start == (2.75, 1.0) and up.end == (3.25, 2.0)   # half a tile across the edge at x 3
    assert up.point(0.5) == pytest.approx((3.0, 1.5)) and up.point(0.25)[1] < 1.25   # eased, not a ramp
    assert [leg.end[1] for leg in route.legs if leg.kind == STEP] == [2.0, 3.0, 2.0, 1.0]
    (x, y), leg = route.at(route.effort)
    assert (x, y) == (8.5, 1.0) and leg is route.legs[-1]


def test_a_walk_stops_at_an_edge_and_suggests_a_jump() -> None:
    level = parse_level(MAP, {"c": "home"})
    home = level.spot("home")
    with pytest.raises(VidgenError, match="'pip' cannot walk to spot 'home': the way stops at map column 10: a gap at column 11; jump there instead"):
        walk_route(level, (8.5, 3.0), TALL, home.x, home.y, who="'pip'", where="spot 'home'")
    wall = parse_level("a.....\n...#..\n...#..\n######")
    with pytest.raises(VidgenError, match="the way stops at map column 3: a wall 2 tiles high at column 4"):
        walk_route(wall, (0.5, 1.0), TALL, 5.5)
    drop = parse_level("a.....\n###...\n###...\n######")
    with pytest.raises(VidgenError, match="a drop of 2 tiles at column 4 \\(a walk steps up or down at most 1 tile\\)"):
        walk_route(drop, (0.5, 3.0), TALL, 5.5)
    low = parse_level("......\n..####\n......\n######")   # one free row under the slab: no room for a character
    with pytest.raises(VidgenError, match="the way stops at map column 2: no room to pass under the tiles at column 3"):
        walk_route(low, (0.5, 1.0), TALL, 3.5, 1.0)
    with pytest.raises(VidgenError, match="on foot it gets to map column 4 only standing on map row 2, not on row 4"):
        walk_route(parse_level("......\n..####\n......\n######"), (5.5, 3.0), TALL, 3.5, 1.0)


def test_ladders_are_climbed_on_the_way() -> None:
    level = parse_level(MAP)
    a, b = level.spot("a"), level.spot("b")
    route = walk_route(level, (a.x, a.y), TALL, b.x, b.y)
    assert kinds(route) == [WALK, CLIMB, WALK]
    assert route.legs[1].start == (5.5, 1.0) and route.legs[1].end == (5.5, 3.0)   # up the ladder to its top
    assert route.effort == pytest.approx(4.0 + 2 * 2.0 + 3.0)   # a climbed tile counts double
    down = walk_route(level, (b.x, b.y), TALL, a.x, a.y)
    assert kinds(down) == [WALK, CLIMB, WALK] and down.legs[1].end == (5.5, 1.0)
    # a hatch: the ladder ends under a platform tile; it climbs through onto the platform
    hatch = parse_level("..====\n..|...\n..|...\n######")
    assert kinds(walk_route(hatch, (0.5, 1.0), TALL, 4.5, 4.0)) == [WALK, CLIMB, WALK]
    assert walk_route(hatch, (0.5, 1.0), TALL, 4.5, 4.0).legs[1].end == (2.5, 4.0)
    assert kinds(walk_route(hatch, (0.5, 1.0), TALL, 4.5)) == [WALK]   # room under the platform: it walks along the ground


def test_surface_under_and_standing_checks() -> None:
    level = parse_level(MAP)
    assert surface_under(level, 8.5, 3.0) == 3.0 and surface_under(level, 8.5, 2.5) == 1.0   # on the slab; the ground under it
    assert surface_under(level, 10.5, 2.0) is None and surface_under(level, 5.5, 3.0) == 3.0   # a gap; a ladder's top
    with pytest.raises(VidgenError, match="'pip' is not standing on a tile"):
        walk_route(level, (1.5, 1.6), TALL, 3.5, who="'pip'")


# ----- jumping (no manim) -------------------------------------------------------------------------


def test_a_jump_over_a_gap_takes_off_at_the_edge() -> None:
    level = parse_level(MAP)
    b = level.spot("b")
    plan = plan_jump(level, (b.x, b.y), TALL, 14.5)
    assert plan.run_up.legs and plan.take_off == pytest.approx((9.8, 3.0))   # it walks to the edge first
    assert plan.landing == (14.5, 3.0) and plan.apex == pytest.approx(3.75)
    assert plan.point(0.0) == pytest.approx(plan.take_off) and plan.point(1.0) == pytest.approx(plan.landing)
    assert max(plan.point(k / 100)[1] for k in range(101)) == pytest.approx(3.75, abs=1e-3)
    assert plan.flight_seconds == pytest.approx(flight_seconds(plan.take_off, plan.landing, plan.apex))
    assert plan.flight_seconds >= MIN_FLIGHT_SECONDS
    again = plan_jump(level, (b.x, b.y), TALL, 14.5)
    assert again == plan   # deterministic


def test_clouds_are_one_way() -> None:
    level = parse_level(MAP)
    up = plan_jump(level, (16.5, 3.0), TALL, 17.5)   # from the platform, up through the cloud onto its top
    assert up.landing == (17.5, 5.0) and up.run_up.legs == ()
    assert walk_route(parse_level("a~~~\n####"), (0.5, 1.0), TALL, 3.5).end == (3.5, 1.0)   # walked through
    # a solid platform overhead blocks the same jump
    slab = parse_level("....\n#==#\n#..#\n#..#\n####")   # in a shaft under a plank: only through it
    with pytest.raises(VidgenError, match="the arc hits the tile at map row 2, column [23] \\(also on higher arcs\\)"):
        plan_jump(slab, (1.5, 1.0), TALL, 2.5, 4.0)
    cloud = parse_level("....\n#~~#\n#..#\n#..#\n####")
    assert plan_jump(cloud, (1.5, 1.0), TALL, 2.5, 4.0).landing == (2.5, 4.0)
    # falling onto a cloud on the way stops it there
    lower = parse_level("a.......\n###.~~~~\n###.....\n###....#")
    with pytest.raises(VidgenError, match="would land on the cloud at map row 2, column [5-8] first"):
        plan_jump(lower, (2.5, 3.0), TALL, 7.5, 1.0)


@pytest.mark.parametrize(
    "text,start,goal,message",
    [
        ("a..........\n##.......##", (0.5, 1.0), (10.5, 1.0), f"from map column 2 it is 8.7 tiles across, at most {MAX_JUMP_ACROSS:g}; walk closer"),
        ("..........\n......####\n......####\n......####\n.a....####\n##########", (1.5, 1.0), (7.5, 5.0), "from map column 6 it is 4 tiles up, at most 3; add a step"),
        ("a....\n#....", (0.5, 1.0), (3.5, None), "there is nothing to land on in map column 4 \\(a gap\\)"),
    ],
)
def test_impossible_jumps_say_why(text: str, start: tuple[float, float], goal: tuple[float, float | None], message: str) -> None:
    with pytest.raises(VidgenError, match=f"'pip' cannot jump to there: {message}"):
        plan_jump(parse_level(text), start, TALL, goal[0], goal[1], who="'pip'")


def test_arc_points() -> None:
    assert arc_point((0.0, 1.0), (4.0, 1.0), 2.0, 0.5) == pytest.approx((2.0, 2.0))
    assert arc_point((0.0, 1.0), (2.0, 3.0), 3.0, 1.0) == pytest.approx((2.0, 3.0))


def test_world_rules_move_the_body() -> None:
    level = parse_level(MAP)
    world = place_bodies(level, [Placing("pip", "character", spot="a"), Placing("kit", "character", spot="b")])
    world, route = walk_body(world, "pip", 8.5, 3.0)
    assert isinstance(world, World) and (world.body("pip").x, world.body("pip").y) == (8.5, 3.0) and route.end == (8.5, 3.0)
    world, plan = jump_body(world, "pip", 14.5)
    assert (world.body("pip").x, world.body("pip").y) == (14.5, 3.0) and world.body("kit").x == 8.5


# ----- goals and the replay of a scene's moves (no manim) ------------------------------------------


def test_level_goals() -> None:
    level = parse_level(MAP, {"c": "home"})
    assert level_goal(level, "home") == LevelGoal(21.5, 2.0, "spot 'home'")
    assert level_goal(level, 0.5) == LevelGoal(12.0, None, "x 0.5")
    assert level_goal(level, "right").label == "'right'"
    assert level_goal(level, {"column": 7, "row": 3}) == LevelGoal(6.5, 3.0, "the tile at map row 3, column 7")
    assert level_goal(level, {"column": 6, "row": 3}).y == 3.0   # a ladder's top
    with pytest.raises(VidgenError, match="map row 2, column 1 is not a tile to stand on"):
        level_goal(level, {"column": 1, "row": 2})
    with pytest.raises(VidgenError, match="outside the map"):
        level_goal(level, {"column": 30, "row": 1})


def test_the_replay_follows_each_character() -> None:
    level = parse_level(MAP, {"c": "home"})
    items = [StageItem("pip", "character", "a"), StageItem("kit", "character", "b")]
    steps = [
        LevelStep("beats[0].actions[0]", "s_b1", "walk_to", ("pip",), "b"),      # up the ladder: fine
        LevelStep("beats[1].actions[0]", "s_b2", "walk_to", ("pip",), "home"),   # a gap on the way
        LevelStep("beats[1].actions[1]", "s_b2", "walk_to", ("pip",), "a"),      # not followed after a problem
        LevelStep("beats[2].actions[0]", "s_b3", "jump", ("kit",), 0.6),
        LevelStep("beats[2].actions[1]", "s_b3", "jump", ("kit",), "home"),
    ]
    problems = level_move_problems(level, items, steps)
    assert problems == [("beats[1].actions[0].to", "beat 's_b2': 'pip' cannot walk to spot 'home': the way stops at map column 10: "
                                                   "a gap at column 11; jump there instead (- jump: pip, to: home)")]
    exit_then = [LevelStep("b", "s_b1", "exit", ("kit",)), LevelStep("c", "s_b1", "walk_to", ("kit",), "home")]
    assert level_move_problems(level, items, exit_then) == []   # off stage: not followed


# ----- the stage's checks --------------------------------------------------------------------------


LEVEL = {"map": MAP, "spots": {"c": "home"}}


def level_project(make_project, beats: list[dict[str, Any]], **params: Any) -> Project:
    params = {"level": LEVEL, "idle": False, "characters": [{"name": "pip", "at": "a"}, {"name": "kit", "at": "b"}], **params}
    scenes = [{"id": "hills", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


def action_problems(project: Project) -> list[tuple[str, str]]:
    spec = project.scene("hills")
    with extensions.project_session(project) as theme:
        cls = registry.get("stage").cls
        return actions.scene_actions("stage", cls, spec, cls.validate_params(spec.params, theme), theme)[1]


def test_validate_names_the_beat_and_why(make_project) -> None:
    project = level_project(make_project, [
        {"text": "Pip climbs up to the plank.", "actions": [{"walk_to": "pip", "to": "b"}]},
        {"text": "Then Pip wants to go home.", "actions": [{"walk_to": "pip", "to": "home"}]},
        {"text": "Kit jumps too far.", "actions": [{"jump": "kit", "to": "home"}]},
    ])
    assert action_problems(project) == [
        ("beats[1].actions[0].to", "beat 'hills_b2': 'pip' cannot walk to spot 'home': the way stops at map column 10: a gap at column 11; "
                                   "jump there instead (- jump: pip, to: home)"),
        ("beats[2].actions[0].to", "beat 'hills_b3': 'kit' cannot jump to spot 'home': from map column 10 it is 11.7 tiles across, at most 5; "
                                   "walk closer first or put a platform in between"),
    ]
    fixed = level_project(make_project, [
        {"text": "Pip climbs up.", "actions": [{"walk_to": "pip", "to": "b"}]},
        {"text": "Pip hops over the gap.", "actions": [{"jump": "pip", "to": {"column": 15, "row": 3}}]},
        {"text": "And down to home.", "actions": [{"walk_to": "pip", "to": 0.78}, {"jump": "pip", "to": "home", "at": 0.5}]},
    ])
    assert action_problems(fixed) == []


@pytest.mark.parametrize(
    "action,params,message",
    [
        ({"walk_to": "pip", "to": "b", "depth": 0.3}, {}, "a level has no depth"),
        ({"jump": "pip", "to": "b", "height": 1}, {}, "give height .* or to .*, not both"),
        ({"jump": "pip", "to": "nowhere"}, {}, "unknown mark 'nowhere'"),
    ],
)
def test_bad_moves_on_a_level(make_project, action: dict[str, Any], params: dict[str, Any], message: str) -> None:
    project = level_project(make_project, [{"text": "Pip moves.", "actions": [action]}], **params)
    assert any(__import__("re").search(message, text) for _, text in action_problems(project)), action_problems(project)


def test_jump_to_needs_a_level(make_project) -> None:
    scenes = [{"id": "hills", "type": "stage", "params": {"characters": [{"name": "pip", "at": "left"}]},
               "beats": [{"text": "Pip jumps.", "actions": [{"jump": "pip", "to": "right"}]}]}]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))
    assert action_problems(project) == [("beats[0].actions[0].to", "jumping to a place needs a platform level (params.level); "
                                                                   "without one a character jumps up where it stands")]


def test_default_speeds_scale_with_the_level_size() -> None:
    from vidgen.scenes.stage import STAGE_SIZE

    p = stage_params(level={"map": "a" + "." * 19 + "\n" + "#" * 20})
    assert p.size / STAGE_SIZE == pytest.approx(0.25 / 0.45)


def test_directing_follows_a_jump(make_project) -> None:
    from vidgen.cartoon.directing import BeatInput, CastMember, _follow_written, _start_state, stage_frame
    from vidgen.config import ActionConfig

    project = level_project(make_project, [{"text": "Pip jumps."}])
    with extensions.project_session(project) as theme:
        params = registry.get("stage").cls.validate_params(project.scene("hills").params, theme)
        frame = stage_frame(project, params)
    cast = [CastMember("pip"), CastMember("kit")]
    state = _start_state(cast, [], frame)
    jumps = [ActionConfig.model_validate({"action": "jump", "target": "pip", "to": "home"}),
             ActionConfig.model_validate({"action": "jump", "target": "kit", "to": {"column": 15, "row": 3}})]
    _follow_written(state, BeatInput("hills_b1", "Pip jumps.", (), tuple(jumps)), ["pip", "kit"])
    assert state.x["pip"] == pytest.approx(frame.place_x("home")) and state.facing["pip"] == "right"
    assert state.x["kit"] is None   # a tile: not a mark the planner knows


def test_lint_reports_level_moves_squeezed_into_their_beat() -> None:
    from test_timing_lint import activity, beat, play, run

    plays = [play(0.0, 2.0, "b1", "RouteWalk", requested=4.0), play(3.0, 4.2, "b2", "Succession(RouteWalk, ArcJump)", requested=1.5),
             play(5.0, 5.5, "b3", "Walk", requested=2.0)]   # a walk on a plain stage: only min_run_time applies
    doc = activity([beat("b1", 0, 2.5), beat("b2", 2.8, 4.5), beat("b3", 5.0, 5.6)], plays=plays)
    issues = run("rushed_animation", doc, min_run_time=0.4)
    assert [(i.beat, i.value) for i in issues] == [("b1", 2.0)]
    assert issues[0].message.startswith("a walk or jump on the level plays 2.0 times as fast as its own pace (RouteWalk: 2.0 s instead of 4.0 s)")
    assert [i.beat for i in run("rushed_animation", doc, min_run_time=0.4, max_speedup=1.2)] == ["b1", "b2"]


# ----- render --------------------------------------------------------------------------------------


@pytest.mark.render
def test_walks_and_jumps_render_in_their_beats(make_project, tmp_path: Path) -> None:
    project = level_project(make_project, [
        {"text": "Pip climbs the ladder up to the plank.", "actions": [{"walk_to": "pip", "to": "b"}]},
        {"text": "Then Pip hops over the gap.", "actions": [{"jump": "pip", "to": {"column": 15, "row": 3}, "at": 0.2}]},
        {"text": "Kit comes in and up the ladder to the plank.", "actions": [{"enter": "kit", "side": "left"}]},
        {"text": "And Kit climbs down and leaves.", "actions": [{"exit": "kit", "to": "left", "at": 0.2}]},
    ])
    scene, _ = render_with_layout(project, "hills", tmp_path / "media")
    frame = scene.params.level_frame(scene.frame_width, scene.frame_height)
    pip = scene.cast["pip"]
    assert pip.feet()[:2] == pytest.approx(frame.point(14.5, 3.0), abs=1e-6)
    assert scene.grounds["pip"] == pytest.approx(frame.point(0, 3.0)[1]) and pip.ground_y == pytest.approx(scene.grounds["pip"])
    assert pip.facing == "right"
    kit = scene.cast["kit"]
    assert scene.grounds["kit"] == pytest.approx(frame.point(0, 3.0)[1])   # it entered up to its spot on the plank...
    assert kit.feet()[1] == pytest.approx(frame.point(0, 1.0)[1]) and kit.feet()[0] < scene.camera.frame.get_left()[0]   # ...and left down the ladder
    assert kit.facing == "left"
