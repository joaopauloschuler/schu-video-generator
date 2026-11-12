"""Sitting on, lying on and using the objects of an iso place (DESIGN.md §105.2): the seats and
their facings, the parts drawn over a sitter, the checks of ``sit_on`` / ``lie_on`` / ``use`` /
``stand_up`` and one small render."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST
from test_iso_moves import problems
from vidgen import extensions, registry
from vidgen.cartoon.iso_drawing import shape_points
from vidgen.cartoon.iso_objects import ObjectLook, object_shapes
from vidgen.cartoon.iso_scenery import IsoColors
from vidgen.cartoon.iso_stage import IsoScenery, body_box, iso_view
from vidgen.cartoon.seating import PostureError, Postures
from vidgen.project import Project
from vidgen.world.iso import ObjectPlacing, parse_iso_map, place_objects
from vidgen.world.iso_seats import (
    ISO_BEDS,
    ISO_SEATS,
    ISO_USES,
    bed_facing,
    in_regions,
    next_to,
    object_frame_point,
    seat_facing,
    seat_hips,
    seat_order,
    use_point,
)

ROOM = """
#########
#.......#
#.......#
#..p....#
#.......#
#.......#
"""
LOOK = ObjectLook("#D9774B", "#F2D6A2")


def room(*placings: ObjectPlacing):
    return place_objects(parse_iso_map(ROOM, names={"p": "door"}, place="indoor"), placings)


def test_seat_rules_do_not_import_manim() -> None:
    code = "import sys, vidgen.world.iso_seats; print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_seats_face_out_of_their_object_and_mirror_with_it() -> None:
    place = room(ObjectPlacing("armchair", (3, 3)), ObjectPlacing("armchair", (6, 3), name="other", facing="right"),
                 ObjectPlacing("cafe_table", (3, 5)), ObjectPlacing("school_desk", (7, 5)), ObjectPlacing("bench", (5, 2)))
    left, right = place.object("armchair"), place.object("other")
    assert seat_facing(left, ISO_SEATS["armchair"][0]) == "left" and seat_facing(right, ISO_SEATS["armchair"][0]) == "right"
    assert seat_hips(left, 0.0, ISO_SEATS["armchair"][0]) == pytest.approx((2.5, 2.6, 0.58))
    assert seat_hips(right, 0.0, ISO_SEATS["armchair"][0]) == pytest.approx((5.6, 2.5, 0.58))   # the frame mirrored: x and y swap
    table = place.object("cafe_table")
    assert [seat_facing(table, seat) for seat in ISO_SEATS["cafe_table"]] == ["right", "left"]   # its two chairs face each other
    assert seat_facing(place.object("school_desk"), ISO_SEATS["school_desk"][0]) == "right"   # towards its desk, the room's back
    bench = place.object("bench")
    assert seat_order(bench, 0.0, (6.5, 2.5, 0.0)) == [1, 0] and seat_order(bench, 0.0, (3.0, 1.5, 0.0)) == [0, 1]
    bed = room(ObjectPlacing("bed", (2, 2)), ObjectPlacing("bed", (5, 2), name="bed_2", facing="right"))
    assert bed_facing(bed.object("bed")) == "left" and bed_facing(bed.object("bed_2")) == "right"
    assert object_frame_point(bed.object("bed_2"), 0.0, 0.5, 1.0, 0.0) == pytest.approx((6.0, 1.5, 0.0))
    assert set(ISO_BEDS) == {"bed"} and {"laptop", "campfire", "fireplace", "bookshelf_tall"} <= set(ISO_USES)


def test_the_parts_in_front_of_a_sitter_are_its_near_arm_and_the_blanket() -> None:
    place = room(ObjectPlacing("armchair", (3, 3)), ObjectPlacing("bed", (6, 2)))
    chair = place.object("armchair")
    shapes = object_shapes(chair, LOOK, 0.0)
    arm = [s for s in shapes if in_regions(chair, 0.0, ISO_SEATS["armchair"][0].front, shape_points(s))]
    assert 0 < len(arm) < len(shapes) // 2 and all(min(p[0] for p in shape_points(s)) >= chair.column + 0.65 for s in arm)
    bed = place.object("bed")
    blanket = [s for s in object_shapes(bed, LOOK, 0.0) if in_regions(bed, 0.0, ISO_BEDS["bed"].front, shape_points(s))]
    assert blanket and all(min(p[1] for p in shape_points(s)) >= bed.row + 0.75 for s in blanket)   # the foot end, not the pillow
    view = iso_view(place, 14.2, 8.0)
    scenery = IsoScenery(place, IsoColors(), {o.name: LOOK for o in place.objects}, view, 20.0)
    own = len(scenery.pieces)
    k = scenery.part("armchair", "seat0", lambda s: in_regions(chair, 0.0, ISO_SEATS["armchair"][0].front, shape_points(s)))
    assert k == own and scenery.part("armchair", "seat0", lambda s: True) == k   # made once
    assert scenery.part("armchair", "none", lambda s: False) is None
    assert all(j != k for j, _ in scenery.base()[1]) and k not in scenery.over(body_box((2.5, 2.6, 0.0), 2.0))
    front = scenery.front(body_box((2.5, 2.6, 0.0), 2.0), exclude=("armchair",), first=k)
    assert front is not None and front[1][0][0] == k


def test_postures_lying_and_full_seats() -> None:
    p = Postures()
    p.lie("pip", "bed")
    with pytest.raises(PostureError, match="'bed' is taken: pip lies on it then"):
        p.sit("kit", "bed", 1)
    with pytest.raises(PostureError, match="pip lies on 'bed' then; stand_up first"):
        p.pinned("pip", "walk_to")
    assert p.stand("pip") == ("lying", "bed")
    p.sit("kit", "bed", 1)
    with pytest.raises(PostureError, match="kit sits on it then"):
        p.lie("pip", "bed")


def test_hands_go_to_the_side_of_an_object_used_from_its_side_and_free_cells_next_to_it() -> None:
    place = room(ObjectPlacing("laptop", (4, 3)))
    laptop = place.object("laptop")
    front = use_point(laptop, 0.0, ISO_USES["laptop"], (3.5, 3.5, 0.0))
    side = use_point(laptop, 0.0, ISO_USES["laptop"], (4.5, 2.5, 0.0))
    assert front[1] > 2.6 and side[0] > front[0] and front[2] == pytest.approx(0.8)
    assert next_to(place, laptop, (6, 4)) in {(4, 3), (4, 2)}


# ----- the stage ----------------------------------------------------------------------------------------


LOUNGE = {"place": "indoor", "map": ROOM, "spots": {"p": "door"},
          "objects": [{"object": "armchair", "at": {"column": 3, "row": 3}, "facing": "right"}, {"object": "lamp", "at": {"column": 6, "row": 3}},
                      {"object": "bed", "at": {"column": 7, "row": 2}}, {"object": "laptop", "at": {"column": 4, "row": 3}},
                      {"object": "bench", "at": {"column": 6, "row": 6}}]}


def lounge_project(make_project, beats: list[dict[str, Any]], **params: Any) -> Project:
    params = {"idle": False, "background": "#BFE3F5", "iso": LOUNGE, "characters": [{"name": "pip", "at": "door"}], **params}
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


@pytest.mark.parametrize(
    "actions,message",
    [
        ([{"sit_on": "pip", "to": "armchiar"}], "'armchiar' is not an object of the place; did you mean armchair?"),
        ([{"sit_on": "pip", "to": "lamp"}], "'lamp' is a lamp: nothing to sit on (nothing to sit on, lie on or use)"),
        ([{"lie_on": "pip", "to": "armchair"}], "'armchair' is a armchair: nothing to lie on (one can sit_on it)"),
        ([{"use": "pip", "to": "bench"}], "objects to use: laptop"),
        ([{"sit_on": "pip", "to": "bench"}], "'pip' is 2 cells from 'bench'; it must be next to it to sit on it: walk_to first"),
        ([{"sit_on": "pip", "to": "armchair"}, {"walk_to": "pip", "to": {"column": 5, "row": 2}, "at": 0.5}], "pip sits on 'armchair' then; stand_up first"),
        ([{"sit_on": "pip", "to": "armchair"}, {"sit_on": "kit", "to": "armchair", "at": 0.5}], "'armchair' is taken: pip sits on it then"),
        ([{"stand_up": "pip"}], "pip neither sits nor leans then"),
        ([{"walk_to": "pip", "to": {"column": 6, "row": 2}}, {"lie_on": "pip", "to": "bed", "at": 0.5}, {"use": "pip", "to": "laptop", "at": 0.8}],
         "pip lies on 'bed' then; stand_up first"),
    ],
)
def test_bad_seats(make_project, actions: list[dict[str, Any]], message: str) -> None:
    characters = [{"name": "pip", "at": "door"}, {"name": "kit", "at": "door"}]
    found = problems(lounge_project(make_project, [{"text": "Pip sits.", "actions": actions}], characters=characters), "home")
    assert any(message in text for _, text in found), found


def test_lying_and_using_need_an_iso_place(make_project) -> None:
    scenes = [{"id": "home", "type": "stage", "params": {"characters": [{"name": "pip", "at": "left"}], "props": [{"prop": "bed", "at": "right"}]},
               "beats": [{"text": "Pip naps.", "actions": [{"lie_on": "pip", "to": "bed"}, {"use": "pip", "to": "bed"}]}]}]
    texts = [text for _, text in problems(Project.load(make_project(minimal_config(characters=CAST, scenes=scenes))), "home")]
    assert any("lie_on is for a bed of an iso place" in t for t in texts) and any("use is for the objects of an iso place" in t for t in texts), texts


def test_a_pupils_legs_go_under_the_school_desk() -> None:
    """Step 275: at a school desk the sitter's legs are tucked away (they showed over the desk's
    front); other seats keep them."""
    from vidgen.cartoon.character import CharacterState, PartPose
    from vidgen.scenes.stage_seats import IsoSeating

    assert ISO_SEATS["school_desk"][0].tucked and not any(seat.tucked for kind, seats in ISO_SEATS.items() if kind != "school_desk" for seat in seats)
    state = CharacterState("right", {"body": PartPose(10.0), "legs": PartPose(5.0), "arm_left": PartPose()})
    tucked = IsoSeating.iso_tucked(state)
    assert tucked.parts["legs"].scale == (0.05, 0.05) and tucked.parts["legs"].angle == 5.0
    assert tucked.parts["body"] == state.parts["body"] and tucked.facing == "right" and state.parts["legs"].scale == (1.0, 1.0)


def test_a_good_evening_validates(make_project) -> None:
    beats = [{"text": "Pip sits and types.", "actions": [{"sit_on": "pip", "to": "armchair"}, {"use": "pip", "to": "laptop", "at": 0.5}]},
             {"text": "Then it gets up.", "actions": [{"stand_up": "pip"}, {"walk_to": "pip", "to": {"column": 6, "row": 2}, "at": 0.5}]},
             {"text": "Bed time.", "actions": [{"lie_on": "pip", "to": "bed"}]}]
    assert problems(lounge_project(make_project, beats), "home") == []
    beats[0]["actions"][1]["to"] = "bench"
    assert any("objects to use: laptop" in text for _, text in problems(lounge_project(make_project, beats), "home"))


@pytest.mark.slow
@pytest.mark.render
def test_sitting_lying_and_using_render(make_project, tmp_path: Path, monkeypatch) -> None:
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    beats = [{"text": "Pip sits down.", "actions": [{"sit_on": "pip", "to": "armchair"}]},
             {"text": "It types a long message.", "actions": [{"use": "pip", "to": "laptop", "run_time": 1.5}]},
             {"text": "And up.", "actions": [{"stand_up": "pip"}]},
             {"text": "To bed.", "actions": [{"walk_to": "pip", "to": {"column": 6, "row": 2}}]},
             {"text": "Pip gets into bed and pulls up the blanket.", "actions": [{"lie_on": "pip", "to": "bed"}]}]
    scene, frames = frames_of(lounge_project(make_project, beats), tmp_path / "seats", monkeypatch)
    pip = scene.cast["pip"]
    assert pip.iso_seat == ("bed", "bed") and pip.sitting_on == "bed" and pip.iso_scale == pytest.approx(0.72)
    assert scene._iso_seat_parts[("armchair", "seat0")] is not None and scene._iso_seat_parts[("bed", "bed")] is not None
    picture = scene._iso_fronts["pip"][0]
    assert picture is not None and picture[1][0][0] == scene._iso_seat_parts[("bed", "bed")]   # the blanket over it
    assert scene.postures.of("pip") == ("lying", "bed") and len(frames) > 5
