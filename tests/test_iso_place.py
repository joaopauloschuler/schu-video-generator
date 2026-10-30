"""Step 166: isometric places — the world model (an ASCII map with heights, spots, ready-made
objects) and its checks, the projection and draw order, the drawing (ground, blocks, walls cut
away indoors, objects) and the place on a ``stage`` with a character standing in it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen.cartoon.iso_drawing import Disc, IsoCanvas, Poly, _ink_runs, box_shapes, draw_shapes
from vidgen.cartoon.iso_objects import OBJECT_COLORS, ObjectLook, object_shapes
from vidgen.cartoon.iso_scenery import IsoColors, ground_shapes, place_pieces
from vidgen.cartoon.iso_stage import ISO_MARGIN, IsoScenery, body_box, iso_layout, iso_stand, iso_view, map_fraction, pieces_in_front, place_bounds
from vidgen.cartoon.stage import StageItem
from vidgen.errors import VidgenError
from vidgen.includes import ISO_DROPPED_KEYS, apply_set, builtin_sets
from vidgen.project import Project
from vidgen.world.iso import (
    BLOCK,
    CUT_WALL_HEIGHT,
    DOOR,
    FLOOR,
    GARDEN_WALL_HEIGHT,
    ISO_CHARACTER_HEIGHT,
    OBJECT_KINDS,
    PATH,
    STEP_HEIGHT,
    VOID,
    WALL,
    WALL_HEIGHT,
    WATER,
    WINDOW,
    IsoCell,
    ObjectPlacing,
    parse_iso_map,
    place_objects,
)
from vidgen.world.iso_view import ISO_RISE, Box3, draw_order, in_front, iso_point

FW, FH = 8 * 16 / 9, 8.0
VILLAGE = """
-.......@..
.a..:::....
..h.:..w.~~
....:.123..
&...:.12b..
-.===......
"""
ROOM = """
####%###
#......#
#..t...+
#....k.#
#......#
###+####
"""
LOOKS = {kind: ObjectLook("#C08040", "#E06060") for kind in OBJECT_KINDS}


def village() -> Any:
    place = parse_iso_map(VILLAGE, names={"a": "start", "h": "home", "w": "well", "b": "top"})
    return place_objects(place, [ObjectPlacing("house", "home"), ObjectPlacing("well", "well")])


def looks(place: Any) -> dict[str, ObjectLook]:
    return {item.name: LOOKS[item.kind] for item in place.objects}


# ----- the world model (no manim) ----------------------------------------------------------------


def test_parse_reads_ground_heights_and_spots() -> None:
    place = parse_iso_map(VILLAGE, names={"a": "start"})
    assert (place.columns, place.rows, place.indoor) == (11, 6, False)
    assert place.ground(0, 0) == VOID and place.ground(-1, 2) == VOID and place.ground(11, 0) == VOID   # outside: void
    assert place.ground(1, 0) == FLOOR and place.ground(4, 1) == PATH and place.ground(9, 2) == WATER
    assert place.cell(6, 3) == IsoCell(BLOCK, 1) and place.floor_z(8, 3) == pytest.approx(3 * STEP_HEIGHT)
    # a letter takes the ground of its neighbours: 'b' among blocks 2, 3 and floor
    top = place.spot("b")
    assert (top.column, top.row) == (8, 4) and place.cell(8, 4) == IsoCell(FLOOR, 0)
    assert place.spot("start").letter == "a" and place.spot_names() == ["start", "h", "w", "b"]
    on_path = parse_iso_map(":::\n:a:\n:::")
    assert on_path.cell(1, 1).ground == PATH   # a spot on a path is path
    raised = parse_iso_map("222\n2a2\n...")
    assert raised.cell(1, 1) == IsoCell(BLOCK, 2)   # on a terrace: raised
    with pytest.raises(VidgenError, match="no spot 'home' \\(spots: start, h, w, b\\)"):
        place.spot("home")


def test_map_symbols_are_objects_named_in_map_order() -> None:
    place = parse_iso_map(VILLAGE)
    names = [item.name for item in place.objects]
    assert names == ["tree_1", "bush_1", "fence_1", "fence_2", "fence_3"]
    fences = [item for item in place.objects if item.kind == "fence"]
    assert fences[0].links == ("e",) and fences[1].links == ("e", "w") and fences[2].links == ("w",)
    assert parse_iso_map(".=.\n...").objects[0].links == ("e", "w")   # alone: left to right
    assert not place.is_standable(8, 0) and place.is_standable(7, 0)   # a tree stands in the way


def test_heights_map_raises_cells() -> None:
    place = parse_iso_map("....\n.a..\n....", heights="....\n.33.\n..1.")
    assert place.cell(1, 1) == IsoCell(FLOOR, 3) and place.cell(2, 2) == IsoCell(FLOOR, 1) and place.floor_z(0, 0) == 0.0
    walls = parse_iso_map("###\n...", heights="222")
    assert walls.cell(1, 0) == IsoCell(WALL, 2)


@pytest.mark.parametrize(
    "text,kwargs,message",
    [
        ("", {}, "the map is empty"),
        ("~~~\n~~~", {}, "nowhere to stand"),
        ("..?.\n....", {}, "map row 1, column 3: unknown symbol '\\?'"),
        ("a..a", {}, "map row 1, column 4: spot 'a' is already at row 1, column 1"),
        ("a...", {"names": {"b": "home"}}, "spots: letter 'b' is not on the map"),
        ("a..b", {"names": {"a": "home", "b": "home"}}, "'home' names both 'a' and 'b'"),
        ("." * 49, {}, "49 columns wide; at most 48"),
        ("\n".join(["."] * 49), {}, "49 rows; at most 48"),
        ("....", {"heights": "..x."}, "heights row 1, column 3: 'x' is not a height"),
        ("....", {"heights": ".....\n"}, "larger than the map"),
        ("..~.", {"heights": "..2."}, "heights row 1, column 3: water lies at height 0"),
        ("- ..", {"heights": "2..."}, "heights row 1, column 1: the map has nothing there"),
        ("....", {"place": "cave"}, "'cave' is not a kind of place"),
    ],
)
def test_bad_maps_name_the_row_and_column(text: str, kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        parse_iso_map(text, **kwargs)


def test_objects_stand_on_their_footprint() -> None:
    place = village()
    house = place.object("house")
    assert (house.column, house.row, house.width, house.depth) == (2, 2, 3, 3) and place.object_at(4, 4) is house
    assert not place.is_standable(3, 3) and place.object("well").cells() == [(7, 2)]
    bench = place_objects(parse_iso_map("....\n.a..\n...."), [ObjectPlacing("bench", "a", facing="right")]).object("bench")
    assert (bench.width, bench.depth) == (1, 2)   # facing right turns its footprint
    two = place_objects(parse_iso_map("......\n......"), [ObjectPlacing("rock", (1, 1)), ObjectPlacing("rock", (3, 1), name="big"),
                                                          ObjectPlacing("rock", (5, 2)), ObjectPlacing("rug", (1, 2), size=(2, 1))])
    assert [o.name for o in two.objects] == ["rock", "big", "rock_3", "rug"] and two.is_standable(0, 1)   # a rug is walked on
    bridge = place_objects(parse_iso_map(".~~.\n...."), [ObjectPlacing("bridge", (2, 1), size=(2, 1))])
    assert bridge.is_standable(1, 0) and bridge.is_standable(2, 0) and not parse_iso_map(".~~.").is_standable(1, 0)


@pytest.mark.parametrize(
    "placing,message",
    [
        (ObjectPlacing("castle", (1, 1)), "unknown object 'castle'"),
        (ObjectPlacing("well", "nowhere"), "no spot 'nowhere'"),
        (ObjectPlacing("house", (3, 1)), "reaches outside the place at map row 1, column 5"),
        (ObjectPlacing("bench", (1, 1)), "'bench' would stand on a wall at map row 1, column 2"),
        (ObjectPlacing("well", (3, 2)), "'well' would stand on water"),
        (ObjectPlacing("well", (1, 3)), "'well' and 'tree_1' would both stand at map row 3, column 1"),
        (ObjectPlacing("bench", (1, 2)), "would stand on two heights"),
        (ObjectPlacing("sign", (1, 2), facing="up"), "facing is left or right"),
    ],
)
def test_bad_objects_name_the_object_and_cell(placing: ObjectPlacing, message: str) -> None:
    place = parse_iso_map(".#..\n.1~.\n@...")
    with pytest.raises(VidgenError, match=message):
        place_objects(place, [placing])


def test_characters_stand_next_to_an_object_at_their_spot() -> None:
    place = village()
    assert place.stand_cell("start") == (1, 1)
    assert place.stand_cell("well") == (8, 3)   # in front of the well (lower right), as near as can be
    assert iso_stand(place, "top") == (8.5, 4.5, 0.0)
    assert iso_stand(parse_iso_map("...\n.3a"), "a") == (2.5, 1.5, 0.0)


def test_indoor_walls_stand_at_the_back_and_are_cut_in_front() -> None:
    room = parse_iso_map(ROOM, place="indoor")
    assert room.ground(4, 0) == WINDOW and room.ground(7, 2) == DOOR
    assert room.wall_height(2, 0) == WALL_HEIGHT and room.wall_height(0, 3) == WALL_HEIGHT   # the back walls stand
    assert room.wall_height(4, 5) == CUT_WALL_HEIGHT and room.wall_height(7, 3) == CUT_WALL_HEIGHT   # the front ones are cut
    assert room.wall_height(3, 5) == 0.0 and room.is_cut(3, 5) and room.is_standable(3, 5)   # a cut doorway: a way through
    assert room.wall_height(0, 5) == WALL_HEIGHT and room.wall_height(7, 0) == WALL_HEIGHT   # the back walls' front ends
    outdoor = parse_iso_map("###+#\n.....")
    assert outdoor.wall_height(0, 0) == GARDEN_WALL_HEIGHT and outdoor.wall_height(3, 0) == 0.0 and not outdoor.is_cut(0, 0)


def test_world_and_drawing_modules_do_not_import_manim() -> None:
    code = ("import sys, vidgen.world.iso, vidgen.world.iso_view, vidgen.cartoon.iso_drawing, vidgen.cartoon.iso_objects, "
            "vidgen.cartoon.iso_scenery, vidgen.cartoon.iso_stage; print('manim' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout
    assert out.strip() == "False"


# ----- the view: projection and draw order (no manim) --------------------------------------------


def test_projection() -> None:
    assert iso_point(0, 0) == (0.0, 0.0)
    assert iso_point(1, 0) == pytest.approx((0.5, 0.25)) and iso_point(0, 1) == pytest.approx((-0.5, 0.25))   # a diamond 1 wide, 1/2 high
    assert iso_point(1, 1, 1) == pytest.approx((0.0, 0.5 - ISO_RISE)) and ISO_RISE == pytest.approx(0.6124, abs=1e-4)
    assert Box3(0, 0, 0, 1, 1, 0).picture_bounds() == pytest.approx((-0.5, 0.0, 0.5, 0.5))


def test_boxes_in_front() -> None:
    cell = Box3(2, 2, 0, 3, 3, 1)
    assert in_front(Box3(3, 2, 0, 4, 3, 1), cell) is True and in_front(cell, Box3(3, 2, 0, 4, 3, 1)) is False   # nearer in x
    assert in_front(Box3(2, 3, 0, 3, 4, 1), cell) is True and in_front(Box3(2, 1, 0, 3, 2, 1), cell) is False   # in y
    assert in_front(Box3(2, 2, 1, 3, 3, 2), cell) is True   # on top of it
    assert in_front(Box3(20, 0, 0, 21, 1, 1), cell) is None   # far apart on the picture: no order needed


def test_draw_order_is_back_to_front_and_deterministic() -> None:
    wall = Box3(0, 0, 0, 4, 0.5, 3)
    hero = Box3(1.25, 1.25, 0, 1.75, 1.75, 2)
    block = Box3(1, 2, 0, 2, 3, 1)
    on_block = Box3(1.25, 2.25, 1, 1.75, 2.75, 3)
    boxes = [on_block, block, hero, wall]
    assert draw_order(boxes) == [3, 2, 1, 0]
    assert draw_order(boxes) == draw_order(list(boxes))
    assert draw_order([Box3(0, 0, 0, 1, 1, 1), Box3(0.5, 0.5, 0, 1.5, 1.5, 1)]) == [0, 1]   # overlapping: by their middles


def test_pieces_in_front_of_characters() -> None:
    place = village()
    pieces = place_pieces(place, IsoColors(), looks(place))
    behind_house = body_box((1.5, 1.5, 0.0), ISO_CHARACTER_HEIGHT)
    by_the_steps = body_box((5.5, 4.5, 0.0), ISO_CHARACTER_HEIGHT)
    ordered, fronts = pieces_in_front(pieces, [("pip", behind_house), ("kit", by_the_steps)])
    assert sorted(p.name for p in ordered) == sorted(p.name for p in pieces)
    # pip stands behind the house; what stands in front of the house (the fence, the steps) is drawn over it too
    assert fronts["pip"][0].name == "house" and {"fence_1", "fence_2", "fence_3", "block_7_4"} <= {p.name for p in fronts["pip"]}
    assert "tree_1" not in {p.name for p in fronts["pip"]}
    # the steps in front of kit; those to its right are beside it on the picture, not in front
    assert [p.name for p in fronts["kit"]] == ["block_7_5", "block_8_5"]
    names = [p.name for p in ordered]
    assert names.index("house") < names.index("fence_1") and names.index("block_7_4") < names.index("block_7_5")


# ----- drawing (no manim) ------------------------------------------------------------------------


def test_box_faces_and_their_outline() -> None:
    faces = box_shapes(0, 0, 0, 1, 1, 1, "#808080")
    assert len(faces) == 3 and all(isinstance(f, Poly) for f in faces)
    joined = box_shapes(0, 0, 0, 1, 1, 1, "#808080", joined={"s", "w"})
    assert len(joined) == 2   # no face towards a joined neighbour
    top = joined[-1]
    assert top.ink == (True, True, False, False)   # no outline along the joins
    assert _ink_runs([(0, 0), (1, 0), (1, 1), (0, 1)], (True, False, True, True)) == [[(1, 1), (0, 1), (0, 0), (1, 0)]]
    assert _ink_runs([(0, 0), (1, 0), (1, 1)], True) == [[(0, 0), (1, 0), (1, 1), (0, 0)]]


def test_draw_shapes_paints_where_the_world_point_lands() -> None:
    canvas = IsoCanvas(40.0, -1.0, -1.0, 80, 80)
    image = draw_shapes(box_shapes(0, 0, 0, 1, 1, 0.5, "#FF0000"), canvas)
    pixels = np.asarray(image)
    assert pixels.shape == (80, 80, 4) and pixels[0, 0, 3] == 0   # transparent around
    x, y = canvas.pixel((0.5, 0.5, 0.5))
    assert tuple(pixels[round(y), round(x)][:3]) == (255, 0, 0) and pixels[round(y), round(x), 3] == 255   # the top's middle
    floor = draw_shapes([Poly(((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)), "#FF0000", False)], canvas)
    tinted = draw_shapes([Disc((0.5, 0.5, 0.0), 0.3, "#000000", False, 0.5)], canvas, image=floor)
    x, y = canvas.pixel((0.5, 0.5, 0.0))
    assert np.asarray(tinted)[round(y), round(x)][:3] == pytest.approx((128, 0, 0), abs=3)   # a shadow tints what is under it


def test_ground_and_pieces() -> None:
    place = village()
    pieces = place_pieces(place, IsoColors(), looks(place))
    names = [p.name for p in pieces]
    assert "block_7_4" in names and "house" in names and "well" in names and "tree_1" in names
    assert not any(name.startswith("wall_") for name in names)
    ground = ground_shapes(place, IsoColors(water="#0000FF"))
    assert any(isinstance(s, Poly) and s.fill == "#0000FF" for s in ground)
    room = parse_iso_map(ROOM, place="indoor")
    walls = {p.name: p for p in place_pieces(room, IsoColors(), {})}
    assert "wall_4_6" not in walls and walls["wall_1_1"].box.z1 == WALL_HEIGHT and walls["wall_5_6"].box.z1 == CUT_WALL_HEIGHT
    corner = walls["wall_1_1"].box   # the back corner reaches both of its walls' ends
    assert (corner.x0, corner.y0, corner.x1, corner.y1) == (0, 0, 1, 1)
    run = walls["wall_3_1"].box   # a run of wall: the whole cell along it, thinner across it
    assert (run.x0, run.x1) == (2, 3) and 0 < run.y1 - run.y0 < 1


def test_every_object_draws() -> None:
    place = parse_iso_map("\n".join(["." * 8] * 8))
    room = parse_iso_map("###\n#..\n#..", place="indoor")
    for kind in OBJECT_KINDS:   # a wall clock hangs on a wall
        found = place_objects(room if kind == "wall_clock" else place, [ObjectPlacing(kind, (2, 1) if kind == "wall_clock" else (1, 1))]).object(kind)
        shapes = object_shapes(found, LOOKS[kind], 0.0)
        assert shapes, kind
    assert set(OBJECT_COLORS) == set(OBJECT_KINDS)


# ----- the place on a stage (no manim) ------------------------------------------------------------


def test_view_fits_the_place_in_the_frame() -> None:
    place = village()
    view = iso_view(place, FW, FH)
    left, top, right, bottom = place_bounds(place)
    width, height = (right - left) * view.unit, (bottom - top) * view.unit
    assert width <= FW * (1 - 2 * ISO_MARGIN) + 1e-9 and height <= FH * (1 - 2 * ISO_MARGIN) + 1e-9
    assert max(width / FW, height / FH) == pytest.approx(1 - 2 * ISO_MARGIN)
    assert view.height(1.0) == pytest.approx(ISO_RISE * view.unit)
    assert map_fraction(place, 0, place.rows - 1) < 0.1 and map_fraction(place, place.columns - 1, 0) > 0.9


def test_layout_stands_characters_on_their_cells_back_to_front() -> None:
    place = village()
    items = [StageItem("kit", "character", "top"), StageItem("pip", "character", "start", scale=0.8)]
    pip, kit = iso_layout(place, items, frame_width=FW, frame_height=FH)   # pip is further back
    view = iso_view(place, FW, FH)
    assert (pip.name, kit.name) == ("pip", "kit") and pip.index == 1
    assert pip.feet == pytest.approx(view.point(1.5, 1.5, 0.0)) and kit.feet == pytest.approx(view.point(8.5, 4.5, 0.0))
    assert pip.height == pytest.approx(view.height(ISO_CHARACTER_HEIGHT * 0.8)) and pip.depth == 0.0
    with pytest.raises(VidgenError, match="'pip' stands at 'left', which is not a spot of the place"):
        iso_layout(place, [StageItem("pip", "character", "left")], frame_width=FW, frame_height=FH)


def test_scenery_draws_front_pictures_of_the_pieces_over_a_character() -> None:
    place = village()
    view = iso_view(place, FW, FH)
    scenery = IsoScenery(place, IsoColors(), looks(place), view, 20.0)
    canvas, base = scenery.picture(scenery.base())
    assert base.size == (scenery.canvas.width, scenery.canvas.height) and canvas == scenery.canvas
    assert scenery.front(body_box((9.5, 1.5, 0.0), 2.0)) is None   # nothing hides kit
    key = scenery.over(body_box((1.5, 1.5, 0.0), 2.0))
    assert scenery.pieces[key[0]].name == "house"   # the house in front of pip
    picture = scenery.front(body_box((1.5, 1.5, 0.0), 2.0))
    assert picture == (False, tuple((k, scenery.states[k]) for k in key))
    part, front = scenery.picture(picture)
    assert front.size == (part.width, part.height) and part.width < scenery.canvas.width and part.scale == scenery.canvas.scale
    # the front picture is a part of the canvas, in whole pixels: it lies on the base where it is drawn
    x0, y0 = round((part.left - scenery.canvas.left) * part.scale), round((part.top - scenery.canvas.top) * part.scale)
    assert (part.left - scenery.canvas.left) * part.scale == pytest.approx(x0, abs=1e-6)
    under = np.asarray(base)[y0:y0 + part.height, x0:x0 + part.width]
    shown = np.asarray(front)[..., 3] == 255
    assert 0 < shown.mean() and np.all(np.asarray(front)[shown] == under[shown], axis=1).mean() > 0.98   # no seam where they meet


# ----- stage params and config ---------------------------------------------------------------------


ISO = {"map": VILLAGE, "spots": {"a": "start", "h": "home", "w": "well", "b": "top"}, "objects": [{"object": "house", "at": "home"}]}


def test_stage_takes_an_iso_place() -> None:
    params = stage_params(iso={**ISO, "objects": [{"object": "house", "at": "home"}, {"object": "lamp", "at": {"column": 10, "row": 1},
                                                                                     "color": "accent", "facing": "right"}]},
                          characters=[{"name": "pip", "at": "start"}, {"name": "kit", "at": "well"}])
    place = params.iso.parsed()
    assert place.object("lamp").color == "accent" and place.object("lamp").column == 9
    assert params.iso.parsed() is place   # parsed once
    marks = params.stage_marks()
    assert marks["start"] == pytest.approx(map_fraction(place, 1, 1)) and "centre" not in params.marks
    placements = params.layout(frame_width=FW, frame_height=FH, stage_width=FW)
    assert [p.name for p in placements] == ["pip", "kit"]


@pytest.mark.parametrize(
    "extra,message",
    [
        ({"level": {"map": "a..\n###"}}, "an iso place cannot have level"),
        ({"room": True}, "an iso place cannot have room \\(an indoor place is iso: \\{place: indoor\\}\\)"),
        ({"water": True}, "cannot have water"),
        ({"props": ["tree"]}, "props\\[0\\]: on an iso place the props are small things to hold .* a tree is a ready-made object"),
        ({"layers": [{"place": "background", "shapes": [{"shape": "hills"}]}]}, "cannot have layers"),
        ({"width": 2}, "cannot have width"),
        ({"size": 0.3}, "the characters' size follows the place .*remove size"),
        ({"character_size": "large"}, "remove character_size"),
        ({"characters": [{"name": "pip", "at": "start", "depth": 0.3}]}, "characters\\[0\\]: an iso place has no depth"),
        ({"characters": [{"name": "pip", "at": "left"}]}, "characters\\[0\\].at: on an iso place a character stands at a spot"),
        ({"iso": {**ISO, "map": "..?."}}, "map row 1, column 3: unknown symbol"),
        ({"iso": {**ISO, "objects": [{"object": "house", "at": "well"}]}}, "'house' .*reaches outside the place|'house' would stand on water"),
    ],
)
def test_iso_refuses_what_makes_no_sense(extra: dict[str, Any], message: str) -> None:
    params = {"iso": ISO, "characters": [{"name": "pip", "at": "start"}], **extra}
    with pytest.raises(ValidationError, match=message):
        stage_params(**params)


def test_a_set_and_the_videos_character_size_leave_an_iso_place_alone(make_project) -> None:
    park = builtin_sets()["park"]
    merged = apply_set(park, {"iso": ISO}).params
    assert not ISO_DROPPED_KEYS & set(merged) and merged["background"] == park["background"]
    scenes = [{"id": "town", "type": "stage", "params": {"iso": ISO, "characters": [{"name": "pip", "at": "start"}]},
               "beats": [{"text": "Pip is home."}]},
              {"id": "yard", "type": "stage", "params": {"characters": ["pip"]}, "beats": [{"text": "And out."}]}]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes, character_size="large")))
    assert "character_size" not in project.scene("town").params and project.scene("yard").params["character_size"] == "large"


# ----- render -------------------------------------------------------------------------------------


@pytest.mark.render
def test_iso_place_renders_on_a_stage(make_project, tmp_path: Path) -> None:
    params = {"idle": False, "background": "#BFE3F5", "iso": ISO,
              "characters": [{"name": "pip", "at": "start"}, {"name": "kit", "at": "top"}]}
    scenes = [{"id": "town", "type": "stage", "params": params, "beats": [{"text": "Pip and Kit."}]}]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))
    scene, objects = render_with_layout(project, "town", tmp_path / "media")
    place = scene.params.iso.parsed()
    view = iso_view(place, scene.frame_width, scene.frame_height)
    assert scene.cast["pip"].feet()[:2] == pytest.approx(view.point(1.5, 1.5, 0.0), abs=1e-6)
    assert scene.cast["kit"].feet()[:2] == pytest.approx(view.point(8.5, 4.5, 0.0), abs=1e-6)
    named = {obj["name"]: obj for obj in objects if obj["name"]}
    assert "ground" not in named and named["background"]["order"] < named["iso_place"]["order"] < named["pip"]["order"]
    assert named["pip"]["order"] < named["iso_front_pip"]["order"] < named["kit"]["order"]   # the house hides pip
    assert "iso_front_kit" not in named
    assert scene.grounds["pip"] == pytest.approx(view.point(1.5, 1.5, 0.0)[1])
