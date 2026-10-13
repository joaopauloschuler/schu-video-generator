"""Step 110: furniture for rooms (DESIGN.md §69.43): the furniture props, seats at the seat line
(more than one place on a sofa or a bed), props against a room's wall and hanging on it, the
screenplay's ``set:`` room and furniture, the gallery still, and one tiny render of a furnished
room."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_acting import VOICES
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen.cartoon.holding import HandlingStep, holding_problems
from vidgen.cartoon.props import FLAT_PROPS, FURNITURE, PROP_HANGS, PROP_HEIGHTS, draw_prop
from vidgen.cartoon.room import WALL_DEPTH
from vidgen.cartoon.seating import PROP_LEANS, PROP_SEATS, SEAT_BACKS, SEAT_PLACES, PostureError, Postures
from vidgen.cartoon.stage import StageItem, depth_scale, feet_point, stage_layout
from vidgen.cli import check_project
from vidgen.project import Project
from vidgen.screenplay import parse_set
from vidgen.theme import Theme

FW, FH = 16.0, 9.0
#: Every seat line's height in a character's heights (below every generated character's hips).
SEAT_LINE = 0.14


# ----- the props (no render) ----------------------------------------------------------------------


def test_furniture_seats_are_at_the_seat_line() -> None:
    assert {"sofa", "armchair", "bed", "desk"} <= set(PROP_SEATS) and set(SEAT_PLACES) <= set(PROP_SEATS)
    for kind, (_, y) in PROP_SEATS.items():   # the older seats too (Step 102)
        assert PROP_HEIGHTS[kind] * y == pytest.approx(SEAT_LINE, abs=0.002), kind
    assert {"bookshelf", "counter", "fridge"} <= set(PROP_LEANS) and "desk" in SEAT_BACKS
    for kind in FURNITURE:   # seats and lean edges lie within the drawing
        prop = draw_prop(kind, height=2.0, theme=Theme()).shift([1.0, -1.0, 0.0])
        left, right = prop.get_left()[0], prop.get_right()[0]
        points = [prop.seat_point(k) for k in range(len(prop.seat_places))] + ([prop.seat_point()] if prop.seat else [])
        assert all(left < p[0] < right and prop.get_bottom()[1] < p[1] < prop.get_top()[1] for p in points), kind
        if prop.lean_edges() is not None:
            assert prop.lean_edges() == pytest.approx((left, right), abs=0.01 * prop.height), kind


def test_a_sofa_seats_two_side_by_side_and_mirrors() -> None:
    sofa = draw_prop("sofa", height=1.0, theme=Theme())
    assert sofa.seat_places == SEAT_PLACES["sofa"] and sofa.seat_point(0)[0] < sofa.seat_point()[0] < sofa.seat_point(1)[0]
    gap = sofa.seat_point(1)[0] - sofa.seat_point(0)[0]
    assert gap / PROP_HEIGHTS["sofa"] > 0.4   # two characters' widths apart (in a character's heights)
    bed = draw_prop("bed", height=1.0, theme=Theme(), facing="left")
    assert bed.seat_places == tuple(-x for x in SEAT_PLACES["bed"]) and bed.seat_point(0)[0] == pytest.approx(-SEAT_PLACES["bed"][0])
    assert draw_prop("armchair", height=1.0, theme=Theme()).seat_places == ()


def test_postures_fill_a_seat_place_by_place() -> None:
    postures = Postures()
    assert postures.sit("pip", "sofa", 2, prefer=[1, 0]) == 1
    assert postures.sit("kit", "sofa", 2, prefer=[1, 0]) == 0   # the nearest is taken: the other one
    with pytest.raises(PostureError, match="'sofa' is full: pip and kit sit on it then"):
        postures.sit("moss", "sofa", 2)
    postures.stand("pip")
    assert postures.sit("moss", "sofa", 2) == 1 and postures.places == {"kit": 0, "moss": 1}
    with pytest.raises(PostureError, match="'chair' is taken: dot sits on it then"):
        postures.sit("dot", "chair")
        postures.sit("pip", "chair")


def test_validate_counts_the_places_of_a_seat() -> None:
    steps = [HandlingStep(f"a[{k}]", "sit_on", (who,), {"to": "sofa"}) for k, who in enumerate(("pip", "kit", "moss"))]
    characters = {"pip": (0.0, 2.0), "kit": (0.5, 2.0), "moss": (-0.5, 2.0)}
    problems = holding_problems(steps, characters=characters, props={"sofa": 0.0}, place_x=lambda p: None, to_fraction=lambda x: x,
                                seat_places={"sofa": 2})
    assert problems == [("a[2].target", "'sofa' is full: pip and kit sit on it then")]


# ----- on the stage (no render) -------------------------------------------------------------------


def test_hanging_props_hang_above_their_floor() -> None:
    items = [StageItem("clock", "prop", 0.5, 0.4, 0.2, hang=0.85), StageItem("pip", "character", 0.5, 0.4)]
    clock, pip = stage_layout(items, ground=0.2, size=0.45, frame_width=FW, frame_height=FH)
    assert pip.feet == pytest.approx(feet_point(0.5, 0.4, 0.2, FW, FH))
    assert clock.feet[1] - pip.feet[1] == pytest.approx(0.85 * pip.height)   # 0.85 of a character there
    assert clock.height == pytest.approx(0.2 * 0.45 * FH * depth_scale(0.4))


def test_props_against_the_wall_take_its_depth() -> None:
    params = stage_params(
        room=True, characters=[{"name": "pip", "depth": 0.3}],
        props=[{"prop": "sofa", "against": "wall"}, {"prop": "bed", "against": "wall", "depth": 0.2}, "picture",
               {"prop": "clock", "depth": 0.1}, {"prop": "bush", "at": 0.1, "depth": 0.6}, "rug"],
    )
    depths = {item.name: item.depth for item in params.items()}
    assert params.wall_depth() == 0.6   # the bush pushes the wall back; the props against it do not count
    assert depths == {"sofa": 0.6, "bed": 0.2, "picture": 0.6, "clock": 0.1, "bush": 0.6, "rug": 0.0, "pip": 0.3}
    hangs = {item.name: item.hang for item in params.items()}
    assert hangs["picture"] == PROP_HANGS["picture"] and hangs["clock"] == PROP_HANGS["clock"] and hangs["sofa"] == 0.0
    assert stage_params(room=True, props=[{"prop": "sofa", "against": "wall"}]).items()[0].depth == WALL_DEPTH
    outdoor = stage_params(props=["picture"])
    assert outdoor.items()[0].depth == 0.0 and outdoor.items()[0].hang == PROP_HANGS["picture"]   # no wall: where it is written


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"props": [{"prop": "sofa", "against": "wall"}]}, r"props\[0\]: against: wall needs a room"),
        ({"room": True, "props": [{"prop": "sofa", "against": "floor"}]}, "against"),
        ({"room": {"depth": 0.3}, "props": [{"prop": "fridge", "against": "wall", "depth": 0.5}]}, "'fridge' stands at depth 0.5, behind the room's wall"),
    ],
)
def test_bad_furniture_params(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        stage_params(**params)


def furnished_project(make_project, beats: list[dict[str, Any]]) -> Project:
    """A room: a sofa and a counter against the wall, a picture on it, a rug; pip and kit at the
    wall's depth (to sit on the sofa and lean on the counter)."""
    params = {
        "idle": False, "light": "indoor",
        "room": {"wallpaper": "stripes", "windows": [0.15], "doors": [0.9]},
        "props": [{"prop": "sofa", "at": 0.35, "against": "wall"}, {"prop": "counter", "at": 0.7, "against": "wall"},
                  {"prop": "picture", "at": 0.35}, {"prop": "rug", "at": 0.4, "depth": 0.1}],
        "characters": [{"name": "pip", "at": 0.3, "depth": 0.4}, {"name": "kit", "at": 0.45, "depth": 0.4}],
    }
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))


SIT_TOGETHER = [{"text": "They sit down together.", "actions": [{"sit_on": "pip", "to": "sofa"}, {"sit_on": "kit", "to": "sofa"}]}]


def test_validate_two_on_a_sofa_and_one_at_the_counter(make_project) -> None:
    assert check_project(furnished_project(make_project, SIT_TOGETHER)) == []
    lean = [{"text": "Kit leans on the counter.", "actions": [{"walk_to": "kit", "to": 0.55}, {"lean_on": "kit", "to": "counter", "at": 0.6}]}]
    assert check_project(furnished_project(make_project, lean)) == []
    rug = [{"text": "Pip sits on the rug.", "actions": [{"sit_on": "pip", "to": "rug"}]}]
    assert any("'rug' has no seat" in p for p in check_project(furnished_project(make_project, rug)))


# ----- the screenplay's set: lines ----------------------------------------------------------------


def test_screenplay_sets_name_a_room_and_its_furniture() -> None:
    design = parse_set("room: stripes, tiles, window at 0.2, open door (hall) at far_right; "
                       "props: couch against the wall at 0.4, kitchen counter (bar) at 0.7 against the back wall, rug at 0.45, "
                       "picture frame on the wall", {})
    assert design.todos == []
    assert design.params["room"] == {"wallpaper": "stripes", "flooring": "tiles", "windows": [0.2],
                                     "doors": [{"at": "far_right", "name": "hall", "open": True}]}
    assert "background" not in design.params and "ground_color" not in design.params   # the room draws its own
    assert design.params["props"] == [
        {"prop": "sofa", "at": 0.4, "against": "wall"}, {"prop": "counter", "name": "bar", "at": 0.7, "against": "wall"},
        {"prop": "rug", "at": 0.45}, {"prop": "picture", "at": 0.85, "against": "wall"},
    ]
    assert parse_set("room", {}).params == {"room": True}
    outdoor = parse_set("props: sofa against the wall; room: curtains", {})
    assert outdoor.params["props"] == [{"prop": "sofa", "at": 0.85, "against": "wall"}]   # the room makes it indoors
    assert outdoor.todos == ["set: room 'curtains' is not stripes, striped, dots, dotted, plain, boards, tiles, tiled, ceiling, a window or a door"]
    yard = parse_set("background: day; props: sofa against the wall", {})
    assert yard.params["props"] == [{"prop": "sofa", "at": 0.85}] and yard.todos == ["set: sofa against the wall needs a room (room: ...)"]
    both = parse_set("background: night; room", {})
    assert "background" not in both.params and both.todos == ["set: a room draws its own wall and floor; background left out"]


# ----- render ---------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_furnished_room(make_project, tmp_path: Path) -> None:
    """Pip and kit sit on the sofa side by side; the picture hangs on the wall; the picture and the
    rug cast no shadow."""
    from vidgen.introspect import LayoutRecorder

    recorder = LayoutRecorder()
    scene, _ = render_with_layout(furnished_project(make_project, SIT_TOGETHER), "home", tmp_path / "media", recorder)
    sofa, picture, pip, kit = scene.props["sofa"], scene.props["picture"], scene.cast["pip"], scene.cast["kit"]
    assert pip.sitting_on == kit.sitting_on == "sofa"
    assert pip.feet()[0] == pytest.approx(sofa.seat_point(0)[0], abs=1e-6) and kit.feet()[0] == pytest.approx(sofa.seat_point(1)[0], abs=1e-6)
    assert picture.feet()[1] > sofa.get_top()[1] and picture.feet()[1] > scene.grounds["sofa"]   # on the wall above the sofa
    assert scene.grounds["sofa"] == pytest.approx(scene.grounds["counter"]) == pytest.approx(scene.grounds["pip"])   # all at the wall
    shadows = {id(c.mobject) for group in scene.shadows for c in group.casters}
    assert id(sofa) in shadows and id(picture) not in shadows and id(scene.props["rug"]) not in shadows and "rug" in FLAT_PROPS
    first = {o["name"]: o for o in [f for f in recorder.frames if "mid" not in f][0]["objects"] if o["name"]}
    assert first["pip"]["sitting_on"] == "sofa" and first["kit"]["sitting_on"] == "sofa"


@pytest.mark.render
def test_furniture_gallery_still(tmp_path: Path) -> None:
    from PIL import Image

    from vidgen.cartoon.still import write_props_png

    path = write_props_png(Theme(), tmp_path / "furniture.png", width=192, height=108, kinds=FURNITURE, columns=4)
    with Image.open(path) as image:
        assert image.size == (192, 108) and image.mode == "P"
