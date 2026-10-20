"""Step 167: characters moving on an iso place — routes on the grid around what is in the way and
up and down steps, meet / follow / wander, ways in and out over the place's edge or out of a spot
(the rules, no manim), the replay that ``vidgen validate`` runs, the stage's checks of the moves,
the facing and draw order of a walker, and a tiny render of a walk behind a house."""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout
from vidgen import actions, extensions, registry
from vidgen.cartoon.iso_objects import ObjectLook
from vidgen.cartoon.iso_scenery import IsoColors
from vidgen.cartoon.iso_stage import IsoScenery, body_box, iso_view, standing_box
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.world.iso import STEP_HEIGHT, ObjectPlacing, parse_iso_map, place_objects
from vidgen.world.iso_moves import (
    EDGE_STEP,
    STEP_EASE,
    IsoRoute,
    IsoStep,
    can_step,
    edge_ways,
    entry_route,
    exit_route,
    find_route,
    follow_route,
    goal_cell,
    iso_move_problems,
    meet_routes,
    route_through,
    wander_route,
)

FW, FH = 8 * 16 / 9, 8.0


def turns(route: IsoRoute) -> int:
    steps = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(route.cells, route.cells[1:])]
    return sum(1 for s, t in zip(steps, steps[1:]) if s != t)


def adjacent(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1


# ----- routes (no manim) ---------------------------------------------------------------------------


def test_world_rules_do_not_import_manim() -> None:
    code = "import sys, vidgen.world.iso_moves; print('manim' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout.strip() == "False"


def test_a_route_goes_through_the_door_of_a_wall() -> None:
    place = parse_iso_map("a..#..\n...+..\n...#.b")
    route = find_route(place, (0, 0), (5, 2))
    assert route.cells[0] == (0, 0) and route.end_cell == (5, 2)
    assert (3, 1) in route.cells and not {(3, 0), (3, 2)} & set(route.cells)
    assert all(adjacent(a, b) for a, b in zip(route.cells, route.cells[1:]))
    assert find_route(place, (0, 0), (5, 2)) == route   # the same route every time


def test_diagonals_never_cut_a_corner() -> None:
    assert find_route(parse_iso_map("a.\n.b"), (0, 0), (1, 1)).length == pytest.approx(math.sqrt(2))
    walled = parse_iso_map("a#\n.b")
    assert not can_step(walled, (0, 0), (1, 1))
    assert find_route(walled, (0, 0), (1, 1)).cells == ((0, 0), (0, 1), (1, 1))


def test_routes_prefer_few_turns() -> None:
    place = parse_iso_map("\n".join(["........"] * 6))
    route = find_route(place, (0, 0), (7, 3))
    assert route.length == pytest.approx(3 * math.sqrt(2) + 4) and turns(route) == 1


def test_up_and_down_steps_one_at_a_time() -> None:
    place = parse_iso_map("a.123b")
    route = find_route(place, (0, 0), (5, 0))
    assert [place.cell(*c).steps for c in route.cells] == [0, 0, 1, 2, 3, 3]
    with pytest.raises(VidgenError, match=r"cannot walk from row 1, column 1 to row 1, column 4: the way stops at row 1, column 2: "
                                          r"a climb of 3 steps \(one walks up or down one step at a time"):
        find_route(parse_iso_map("a.3b"), (0, 0), (3, 0))


def test_feet_rise_before_the_higher_cell_and_drop_after_it() -> None:
    place = parse_iso_map(".1.")
    up, down = find_route(place, (0, 0), (1, 0)), find_route(place, (1, 0), (2, 0))
    assert up.at(0.5 - STEP_EASE - 0.01)[0][2] == 0.0 and up.at(0.5)[0][2] == pytest.approx(STEP_HEIGHT)
    assert down.at(0.5)[0][2] == pytest.approx(STEP_HEIGHT) and down.at(0.5 + STEP_EASE + 0.01)[0][2] == 0.0
    assert up.at(0.25)[1] == 0 and up.at(up.length)[0] == (1.5, 0.5, STEP_HEIGHT)


def test_water_needs_a_bridge_and_feet_stand_on_its_deck() -> None:
    text = "a.~~~.b"
    with pytest.raises(VidgenError, match=r"the way stops at row 1, column 2: water \(a bridge crosses it\) at row 1, column 3"):
        find_route(parse_iso_map(text), (0, 0), (6, 0))
    place = place_objects(parse_iso_map(text), [ObjectPlacing("bridge", (3, 1), facing="right", size=(3, 1))])
    route = find_route(place, (0, 0), (6, 0))
    assert (3, 0) in route.cells and place.stand_z(3, 0) == pytest.approx(0.22)
    assert max(p[2] for p in route.points) == pytest.approx(0.22)


def test_objects_are_in_the_way() -> None:
    place = place_objects(parse_iso_map("a....\n.....\n.....\n....b"), [ObjectPlacing("house", (2, 1))])
    route = find_route(place, (0, 0), (4, 3))
    assert not set(route.cells) & set(place.object("house").cells())
    with pytest.raises(VidgenError, match="the way stops at row 1, column 1: the well at row 1, column 2"):
        find_route(place_objects(parse_iso_map("a.b"), [ObjectPlacing("well", (2, 1))]), (0, 0), (2, 0))


def test_a_goal_where_someone_stands_becomes_the_free_cell_next_to_it() -> None:
    place = parse_iso_map("\n".join(["......"] * 3))
    route = find_route(place, (0, 1), (5, 1), crowd={(5, 1)})
    assert route.end_cell == (4, 2)   # beside it on the picture's level line, not in front of it
    assert find_route(place, (0, 1), (2, 1), crowd={(2, 1), (1, 2), (3, 0)}).end_cell == (4, 0)   # a tile and a half to its side
    assert (3, 1) not in find_route(place, (0, 1), (5, 1), crowd={(3, 1)}).cells   # round someone on the way


def test_goals_name_unknown_spots_and_cells_nobody_stands_on() -> None:
    place = parse_iso_map("a.~\n.#.", names={"a": "gate"})
    assert goal_cell(place, "gate") == ((0, 0), "'gate'") and goal_cell(place, {"column": 2, "row": 1}) == ((1, 0), "row 1, column 2")
    with pytest.raises(VidgenError, match=r"no spot 'well' \(spots: gate\)"):
        goal_cell(place, "well")
    with pytest.raises(VidgenError, match="row 1, column 3 is water: nobody can stand there"):
        goal_cell(place, (3, 1))
    with pytest.raises(VidgenError, match="row 2, column 2 is a wall"):
        goal_cell(place, (2, 2))
    with pytest.raises(VidgenError, match="row 4, column 1 is outside the place"):
        goal_cell(place, (1, 4))


def test_two_that_meet_end_side_by_side_on_the_picture() -> None:
    place = parse_iso_map("\n".join(["........"] * 6))
    first, second = meet_routes(place, (0, 0), (7, 5))
    a, b = first.end_cell, second.end_cell
    assert (b[0] - a[0], b[1] - a[1]) == (1, -1)   # on the picture's level line: side by side
    assert a[0] - a[1] < b[0] - b[1]   # the one from the picture's left stays on the left
    assert abs(first.length - second.length) < 1.5
    close, other = meet_routes(place, (3, 3), (4, 2))   # side by side already: nobody walks
    assert len(close.points) == 1 and len(other.points) == 1


def test_a_follower_walks_behind_the_leader() -> None:
    place = parse_iso_map("\n".join(["........"] * 3))
    leader = route_through(place, [(2, 1), (3, 1), (4, 1), (5, 1), (6, 1)])
    route = follow_route(place, (0, 1), (2, 1), leader, gap=1)
    assert route.cells == ((0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1))
    assert follow_route(place, (0, 1), (6, 1), gap=2).end_cell == (4, 1)   # the leader stands: stop two short of it


def test_wander_is_the_same_for_a_seed_and_stays_near() -> None:
    place = parse_iso_map("\n".join(["..........."] * 9))
    one = wander_route(place, (5, 4), radius=2, stops=4, seed=7)
    assert one == wander_route(place, (5, 4), radius=2, stops=4, seed=7) != wander_route(place, (5, 4), radius=2, stops=4, seed=8)
    assert all(max(abs(c[0] - 5), abs(c[1] - 4)) <= 2 for c in one.cells)
    with pytest.raises(VidgenError, match="nowhere to wander"):
        wander_route(parse_iso_map("~~~\n~a~\n~~~"), (1, 1))


def test_ways_in_and_out_over_the_edge() -> None:
    place = parse_iso_map("\n".join(["......"] * 4))
    assert {out for _, out in edge_ways(place, "left")} == {(0, 1), (-1, 0)}
    come = entry_route(place, (4, 1), side="right")
    assert come.cells[0] is None and come.end_cell == (4, 1)
    first = come.cells[1]
    assert math.dist(come.points[0][:2], come.points[1][:2]) == pytest.approx(EDGE_STEP)
    assert first in ((5, 1), (4, 0))   # its nearest edge on the right of the picture (east or north)
    go = exit_route(place, (1, 2), side="left")
    assert go.cells[-1] is None and go.cells[-2] in ((0, 2), (1, 3))
    door = entry_route(place, (4, 1), door=(0, 0))
    assert door.cells[0] == (0, 0) and None not in door.cells


def test_a_room_is_left_through_a_door_at_its_edge() -> None:
    room = parse_iso_map("#####\n#...#\n#...+\n#####", place="indoor")
    go = exit_route(room, (1, 1))
    assert go.cells[-2] == (4, 2) and go.points[-1][0] > 5.0
    with pytest.raises(VidgenError, match=r"no way out at its left side of its edge"):
        exit_route(room, (1, 1), side="left")


VILLAGE = """
a.......
...h....
........
........
w.......
"""


def test_the_replay_names_the_beat_and_what_is_wrong() -> None:
    place = place_objects(parse_iso_map(VILLAGE, names={"a": "gate", "w": "well", "h": "home"}), [ObjectPlacing("house", "home")])
    starts = {"pip": "gate", "kit": "well"}
    steps = [
        IsoStep("beats[0].actions[0]", "b1", "walk_to", ("pip",), {"to": "nowhere"}),   # its own check reports it: skipped
        IsoStep("beats[0].actions[1]", "b1", "walk_to", ("kit",), {"to": {"column": 5, "row": 3}}),
        IsoStep("beats[1].actions[0]", "b2", "walk_to", ("kit",), {"to": "gate"}),   # kit is no longer followed
    ]
    assert iso_move_problems(place, starts, steps) == [
        ("beats[0].actions[1].to", "beat 'b1': row 3, column 5 is the house: nobody can stand there; walk to a cell of floor, path, "
                                   "a block or a door, or to a spot"),
    ]
    gone = [IsoStep("beats[0].actions[0]", "b1", "exit", ("kit",), {"to": "left"}),
            IsoStep("beats[1].actions[0]", "b2", "walk_to", ("kit",), {"to": "gate"})]
    assert iso_move_problems(place, starts, gone) == [
        ("beats[1].actions[0].to", "beat 'b2': 'kit' is not on the place then (it has not entered yet, or it has exited): walk_to needs it there"),
    ]


def test_the_replay_follows_entrances_and_meetings() -> None:
    place = parse_iso_map(VILLAGE, names={"a": "gate", "w": "well", "h": "home"})
    starts = {"pip": "gate", "kit": "well"}
    steps = [IsoStep("beats[0].actions[0]", "b1", "walk_to", ("kit",), {"to": "home"}),
             IsoStep("beats[1].actions[0]", "b2", "enter", ("kit",), {"to": "home"}),
             IsoStep("beats[2].actions[0]", "b3", "meet", ("kit",), {"with": "pip"})]
    assert iso_move_problems(place, starts, steps, entering=["kit"])[0][0] == "beats[0].actions[0].to"
    assert iso_move_problems(place, starts, steps[1:], entering=["kit"]) == []


# ----- drawing: facing and the draw order of a walker ----------------------------------------------


def test_facing_follows_the_way_on_the_picture() -> None:
    from vidgen.cartoon.iso_motion import leg_facing

    place = parse_iso_map("\n".join(["....."] * 5))
    route = route_through(place, [(1, 1), (2, 1), (2, 2), (3, 3), (2, 2), (3, 1)])
    assert [leg_facing(route, k, "left", has_front=True) for k in range(5)] == ["right", "left", "front", "left", "right"]
    assert leg_facing(route, 2, "left", has_front=False) == "left"   # no front view: it keeps its side
    assert leg_facing(route, 3, "right", has_front=True) == "right"   # straight away: no back view


def test_a_walker_behind_a_house_is_covered_by_it_and_on_a_bridge_drawn_over_it() -> None:
    place = place_objects(parse_iso_map(VILLAGE + "~~~~~~~~\n........", names={"a": "gate", "w": "well", "h": "home"}),
                          [ObjectPlacing("house", "home"), ObjectPlacing("bridge", (2, 6), size=(1, 1))])
    looks = {o.name: ObjectLook("#C08040", "#E06060") for o in place.objects}
    scenery = IsoScenery(place, IsoColors(), looks, iso_view(place, FW, FH), 10.0)
    names = [scenery.pieces[k].name for k in scenery.over(body_box((4.5, 0.5, 0.0), 2.0))]
    assert names[:1] == ["house"]
    assert scenery.over(body_box((4.5, 4.5, 0.0), 2.0)) == ()
    assert body_box((4.95, 1.5, 0.0), 2.0).x1 == 5.0   # kept in the cell its feet are in
    on_deck = standing_box(place, (1.5, 5.5, place.stand_z(1, 5)), 2.0)
    assert on_deck.z0 >= 0.35 and "bridge" not in [scenery.pieces[k].name for k in scenery.over(on_deck)]


# ----- the stage: checks of the moves --------------------------------------------------------------


ISO = {"map": VILLAGE, "spots": {"a": "gate", "w": "well", "h": "home"}, "objects": [{"object": "house", "at": "home"}]}


def iso_project(make_project, beats: list[dict[str, Any]], *, kit: str = "well") -> Project:
    params = {"idle": False, "background": "#BFE3F5", "iso": ISO,
              "characters": [{"name": "pip", "at": "gate"}, {"name": "kit", "at": kit}]}
    scenes = [{"id": "town", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


def problems(project: Project, scene: str = "town") -> list[tuple[str, str]]:
    spec = project.scene(scene)
    with extensions.project_session(project) as theme:
        cls = registry.get(spec.type).cls
        return actions.scene_actions(spec.type, cls, spec, cls.validate_params(spec.params, theme), theme)[1]


@pytest.mark.parametrize(
    "action,message",
    [
        ({"walk_to": "pip", "to": 0.5}, "on an iso place a move goes to a spot of the map (gate, home, well) or a cell {column, row}, not '0.5'"),
        ({"walk_to": "pip", "to": "left"}, "not 'left'"),
        ({"walk_to": "pip", "to": "well", "depth": 0.3}, "an iso place has no depth"),
        ({"walk_to": "pip", "after": "kit", "to": "well"}, "give to (a place) or after (a character to follow), not both"),
        ({"walk_to": "pip", "after": "pip"}, "'pip' cannot walk after itself"),
        ({"walk_to": "pip", "after": "bob"}, "'bob' is not a character of this scene"),
        ({"meet": "pip", "with": "pip"}, "cannot meet itself"),
        ({"wander": "pip", "around": "pond"}, "not 'pond'"),
        ({"enter": "pip", "door": "pond"}, "not 'pond'"),
        ({"exit": "pip", "door": "gate", "to": "left"}, "give to (a side of the place's edge) or door (a spot), not both"),
        ({"walk_to": "pip", "to": {"column": 5, "row": 3}}, "row 3, column 5 is the house: nobody can stand there"),
        ({"run_to": "kit", "to": {"column": 9, "row": 1}}, "row 1, column 9 is outside the place"),
    ],
)
def test_bad_moves_on_an_iso_place(make_project, action: dict[str, Any], message: str) -> None:
    found = problems(iso_project(make_project, [{"text": "Pip and Kit move.", "actions": [action]}]))
    assert any(message in text for _, text in found), found


def test_iso_moves_need_an_iso_place(make_project) -> None:
    scenes = [{"id": "town", "type": "stage", "params": {"characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}]},
               "beats": [{"text": "Pip moves.", "actions": [{"wander": "pip"}, {"meet": "pip", "with": "kit", "at": 0.5},
                                                            {"walk_to": "kit", "after": "pip"}]}]}]
    texts = [text for _, text in problems(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))))]
    assert any("wander is for an iso place" in t for t in texts) and any("meet is for an iso place" in t for t in texts)
    assert any("after (walking behind a leader) is for an iso place" in t for t in texts)


def test_good_moves_validate_with_word_anchors(make_project) -> None:
    project = iso_project(make_project, [
        {"text": "Pip walks round the house to the well.", "actions": [{"walk_to": "pip", "to": "well", "at": "@house"}]},
        {"text": "Kit runs after Pip, and they meet.", "actions": [{"run_to": "kit", "to": {"column": 8, "row": 1}},
                                                                  {"meet": "kit", "with": "pip", "at": "@meet"}]},
        {"text": "Pip wanders about.", "actions": [{"wander": "pip", "radius": 2, "stops": 2}]},
        {"text": "Kit goes home.", "actions": [{"exit": "kit", "to": "right"}]},
    ])
    assert problems(project) == []


# ----- render --------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_walk_behind_the_house_renders(make_project, tmp_path: Path) -> None:
    from vidgen.introspect import LayoutRecorder

    project = iso_project(make_project, [
        {"text": "Pip walks behind the house.", "actions": [{"walk_to": "pip", "to": {"column": 5, "row": 1}}]},
        {"text": "Kit comes in and walks to the gate.", "actions": [{"enter": "kit", "to": "gate", "side": "left"}]},
        {"text": "They meet in front of the house.", "actions": [{"meet": "pip", "with": "kit"}]},
    ], kit="gate")
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "town", tmp_path / "media", recorder)
    view = scene.iso_view
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    named = [{o["name"]: o for o in frame["objects"] if o["name"]} for frame in recorder.frames]
    # beat 1 ends with pip behind the house: its front picture (the house) right after it
    assert named[0]["pip"]["order"] < named[0]["iso_front_pip"]["order"]
    assert scene.iso_cells["kit"] is not None and scene.iso_cells["pip"] is not None
    a, b = scene.iso_cells["pip"], scene.iso_cells["kit"]
    assert adjacent(a, b) and pip.feet()[:2] == pytest.approx(view.point(a[0] + 0.5, a[1] + 0.5, 0.0), abs=1e-6)
    assert kit.feet()[:2] == pytest.approx(view.point(b[0] + 0.5, b[1] + 0.5, 0.0), abs=1e-6)
    assert scene.grounds["kit"] == pytest.approx(kit.feet()[1])
    assert (pip.facing == "right") == (pip.feet()[0] < kit.feet()[0])   # they face each other
    assert scene._iso_fronts["pip"][0] == scene.iso_scenery.front(scene._iso_body(pip))
