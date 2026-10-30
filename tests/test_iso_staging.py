"""Step 168: staging on an iso place — objects that change (doors open, lamps light, flowers
bloom, a bridge appears), the pictures drawn in tiles at levels of detail for the camera, small
things standing on the place and handed about (checked in cells), the camera's follow / pan / shots
on the place, a follower stepping aside, and a tiny render of it all."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen import actions, extensions, registry
from vidgen.cartoon.iso_drawing import Disc, Poly, shape_bounds
from vidgen.cartoon.iso_objects import DOORWAY, LIGHT_POOL, LIT_GLASS, ObjectLook, object_shapes
from vidgen.cartoon.iso_scenery import IsoColors
from vidgen.cartoon.iso_stage import (
    ISO_FOLLOW_SIZE,
    ISO_WIDE_MAX,
    MAX_DETAIL,
    TILE_OVERLAP,
    TILE_PIXELS,
    IsoScenery,
    body_box,
    detail_for,
    follow_width,
    item_box,
    iso_item_point,
    iso_view,
)
from vidgen.cartoon.stage import MAX_ZOOM
from vidgen.project import Project
from vidgen.world.iso import OBJECT_KINDS, ObjectPlacing, ObjectState, default_state, parse_iso_map, place_objects
from vidgen.world.iso_moves import IsoStep, follow_route, iso_move_problems, route_through

FW, FH = 8 * 16 / 9, 8.0
POND = """
a..~..b
...~...
.t.~.w.
...~...
"""
SPOTS = {"a": "start", "b": "far", "t": "table", "w": "well"}
ROOM = """
###+####
#......#
#.k....#
#......#
"""


def pond(**bridge: Any) -> Any:
    place = parse_iso_map(POND, names=SPOTS)
    return place_objects(place, [ObjectPlacing("table", "table"), ObjectPlacing("well", "well"), ObjectPlacing("bridge", (4, 1), **bridge)])


def looks(place: Any) -> dict[str, ObjectLook]:
    return {item.name: ObjectLook("#C08040", "#E06060") for item in place.objects}


# ----- the world: states, doors, objects not there (no manim) ------------------------------------


def test_objects_have_states_and_the_room_doors_names() -> None:
    assert default_state("house") == ObjectState() and default_state("flowers") == ObjectState(open=True)
    room = parse_iso_map(ROOM + "########", place="indoor")
    assert room.doors() == [("door_1", 3, 0)]   # in the standing back wall
    assert parse_iso_map(ROOM.replace("###+", "####") + "#+######", place="indoor").doors() == []   # a front door is cut away: a doorway
    assert parse_iso_map(".+.\n...").doors() == []   # outdoors a gap in a garden wall
    assert OBJECT_KINDS["table"].top == pytest.approx(0.98) and OBJECT_KINDS["tree"].top is None


def test_a_place_without_an_object_walks_where_it_stood() -> None:
    place = pond()
    gone = place.without(["bridge"])
    assert place.object_at(3, 1).name == "bridge" and gone.object_at(3, 1) is None
    assert not gone.is_standable(3, 1) and place.is_standable(3, 1)   # water, without the bridge
    assert place.without([]) is place and [o.name for o in gone.objects] == ["table", "well"]


# ----- drawing by state (no manim) ----------------------------------------------------------------


def _fills(shapes: list[Any]) -> set[str]:
    return {getattr(shape, "fill", "") for shape in shapes}


def test_objects_are_drawn_open_and_lit() -> None:
    place = place_objects(parse_iso_map("h...\n....\n....\n...."), [ObjectPlacing("house", "h"), ObjectPlacing("lamp", (4, 1)),
                                                                    ObjectPlacing("flowers", (4, 4))])
    house, lamp, flowers = place.objects
    look = ObjectLook("#C08040", "#E06060")
    shut = object_shapes(house, look, 0.0)
    assert object_shapes(house, look, 0.0, ObjectState()) == shut and DOORWAY not in _fills(shut) and LIT_GLASS not in _fills(shut)
    assert DOORWAY in _fills(object_shapes(house, look, 0.0, ObjectState(open=True)))
    assert LIT_GLASS in _fills(object_shapes(house, look, 0.0, ObjectState(on=True)))
    pool = [s for s in object_shapes(lamp, look, 0.0, ObjectState(on=True)) if isinstance(s, Disc) and s.fill == LIGHT_POOL]
    assert len(pool) == 1 and pool[0].opacity < 1 and not any(s.fill == LIGHT_POOL for s in object_shapes(lamp, look, 0.0) if isinstance(s, Disc))
    buds, bloom = object_shapes(flowers, look, 0.0, ObjectState(open=False)), object_shapes(flowers, look, 0.0)
    assert len(buds) < len(bloom) and object_shapes(flowers, look, 0.0, ObjectState(open=True)) == bloom   # buds have no hearts


def test_a_room_door_opens_into_the_room() -> None:
    from vidgen.cartoon.iso_scenery import place_pieces

    room = parse_iso_map(ROOM + "########", place="indoor")
    door = next(p for p in place_pieces(room, IsoColors(), {}) if p.name == "door_1")
    assert door.kind == "door" and door.shapes_in(ObjectState()) is door.shapes
    shapes = door.shapes_in(ObjectState(open=True))
    assert DOORWAY in _fills(list(shapes)) and DOORWAY not in _fills(list(door.shapes))
    leaf = [s for s in shapes if isinstance(s, Poly) and s.fill not in (DOORWAY,)][-1]
    assert max(p[1] for p in leaf.points) > door.box.y1   # swung out of the wall into the room


def test_shape_bounds_cover_the_drawing() -> None:
    disc = Disc((1.0, 1.0, 0.0), 0.5, "#FFFFFF")
    left, top, right, bottom = shape_bounds(disc)
    assert right - left == pytest.approx(0.5 * 2**0.5) and bottom - top == pytest.approx(0.5 * 2**0.5 / 2)


# ----- the scenery: layers, tiles, levels of detail (no manim) ------------------------------------


def test_the_scenery_leaves_changing_objects_out_of_its_base() -> None:
    place = pond()
    view = iso_view(place, FW, FH)
    scenery = IsoScenery(place, IsoColors(), looks(place), view, 20.0, states={"bridge": ObjectState(shown=False)}, layered=["bridge", "well"])
    bridge, well = scenery.index["bridge"], scenery.index["well"]
    names = [scenery.pieces[k].name for k, _ in scenery.base()[1]]
    assert "bridge" not in names and "well" not in names and "table" in names and scenery.base()[0]
    assert scenery.layer("bridge") is None   # not there yet
    scenery.set_state("bridge", ObjectState())
    assert [k for k, _ in scenery.layer("bridge")[1]][0] == bridge
    assert scenery.layer("well")[1][0] == (well, ObjectState())
    behind_well = body_box((5.5, 1.5, 0.0), 2.0)
    assert scenery.front(behind_well) is not None and scenery.front(behind_well)[1][0][0] == well
    scenery.set_state("well", ObjectState(shown=False))
    assert scenery.front(behind_well) is None   # gone: nothing hides it


def test_tiles_cover_the_view_at_the_level_of_detail_of_the_zoom() -> None:
    assert [detail_for(z, 1.25) for z in (1.0, 1.4, 2.6, 5.0, MAX_ZOOM, 40.0)] == [0, 1, 1, 2, 3, MAX_DETAIL]
    assert detail_for(1.0, 1.0) == 0 and 1.25 * 2**MAX_DETAIL >= MAX_ZOOM
    place = pond()
    scenery = IsoScenery(place, IsoColors(), looks(place), iso_view(place, FW, FH), 60.0)
    whole = scenery.tiles(scenery.base(), 2)
    c = scenery.level_canvas(2)
    assert c.scale == pytest.approx(4 * scenery.canvas.scale)
    assert sum(t.width - (TILE_OVERLAP if t.left + t.width / t.scale < c.left + c.width / c.scale - 1e-9 else 0) for (i, j), t in whole if j == 0) == c.width
    corner = scenery.tiles(scenery.base(), 2, (c.left, c.top, c.left + 1.0, c.top + 1.0))
    assert [tile for tile, _ in corner] == [(0, 0)] and corner[0][1].width == TILE_PIXELS + TILE_OVERLAP
    picture = (False, ((scenery.index["well"], ObjectState()),))
    clipped = scenery.tiles(picture, 2)
    assert clipped and all(t.width <= TILE_PIXELS + TILE_OVERLAP for _, t in clipped) and len(clipped) < len(whole)


def test_a_tile_lies_on_the_whole_picture_pixel_for_pixel() -> None:
    place = pond()
    scenery = IsoScenery(place, IsoColors(), looks(place), iso_view(place, FW, FH), 40.0)
    canvas, whole = scenery.picture(scenery.base(), 1)
    tiles = scenery.tiles(scenery.base(), 1)
    (i, j), part = tiles[min(1, len(tiles) - 1)]
    image = scenery.tile_image(scenery.base(), 1, (i, j), part)
    assert image is not None and scenery.tile_image(scenery.base(), 1, (i, j), part) is image   # drawn once
    x0, y0 = round((part.left - canvas.left) * part.scale), round((part.top - canvas.top) * part.scale)
    a = np.asarray(image).astype(int)[4:-4, 4:-4]
    b = np.asarray(whole).astype(int)[y0:y0 + part.height, x0:x0 + part.width][4:-4, 4:-4]
    # the same drawing; a tile is drawn on its own, and Pillow rounds a polygon's corners off the
    # picture (negative pixels) a little differently: an edge may move by a third of a pixel
    assert (np.abs(a - b).max(axis=2) > 3).mean() < 0.005


# ----- small things and the camera (no manim) ------------------------------------------------------


def test_small_things_stand_on_tables_and_on_a_wells_rim() -> None:
    place = pond()
    table = iso_item_point(place, "table")
    assert table == pytest.approx((1.5, 2.5, OBJECT_KINDS["table"].top))
    rim = iso_item_point(place, "well")
    assert rim[0] > 5.5 and rim[2] == pytest.approx(OBJECT_KINDS["well"].top)   # at the front of the rim, not in the water
    assert iso_item_point(place, "start") == pytest.approx((0.5, 0.5, 0.0))
    box = item_box(place, table, 0.4)
    assert box.z0 >= OBJECT_KINDS["table"].height - 1e-9   # over the table: drawn after it
    assert item_box(place, (0.5, 0.5, 0.0), 0.4).z0 == 0.0


def test_follow_zooms_in_to_a_plain_stages_size() -> None:
    height = 0.6
    width = follow_width(height, FW, FH, FW)
    assert height * FW / width == pytest.approx(ISO_FOLLOW_SIZE * FH)
    assert follow_width(height, FW, FH, FW / 6) == pytest.approx(FW / 6)   # closer already: it stays
    assert follow_width(0.001, FW, FH, FW) == pytest.approx(FW / MAX_ZOOM)
    assert follow_width(10.0, FW, FH, FW) == pytest.approx(FW)


def test_a_follower_right_behind_its_leader_steps_aside() -> None:
    place = parse_iso_map("\n".join(["......"] * 6))
    lead = route_through(place, [(1, 1), (2, 2), (3, 3)])   # straight down the picture
    route = follow_route(place, (0, 0), (1, 1), lead, gap=1)
    end = route.end_cell
    assert end != (2, 2) and max(abs(end[0] - 3), abs(end[1] - 3)) == 1 and (end[0] - 3) != (end[1] - 3)
    two = follow_route(place, (0, 0), (1, 1), lead, gap=2)
    assert two.end_cell == (1, 1)   # two cells behind: left as it is


# ----- the replay: small things in reach, objects that come and go (no manim) ----------------------


def _step(action: str, names: tuple[str, ...], **options: Any) -> IsoStep:
    return IsoStep(f"beats[0].actions[{len(options)}]", "b1", action, names, options)


def test_the_replay_checks_reach_in_cells() -> None:
    place = pond()
    starts = {"pip": "start", "kit": "far"}
    items = {"gift": "table"}
    far = iso_move_problems(place, starts, [_step("pick_up", ("pip",), to="gift")], items=items)
    assert len(far) == 1 and "'pip' stands 2 cells from 'gift'" in far[0][1] and "walk_to: pip, to: table" in far[0][1]
    near = [_step("walk_to", ("pip",), to="table"), _step("pick_up", ("pip",), to="gift")]
    assert iso_move_problems(place, starts, near, items=items) == []
    give = near + [_step("give", ("pip",), to="kit")]
    found = iso_move_problems(place, starts, give, items=items)
    assert len(found) == 1 and "from 'kit'" in found[0][1] and "meet: pip, with: kit" in found[0][1]
    put = near + [_step("put_down", ("pip",), to="well")]
    assert "where it puts 'gift' down" in iso_move_problems(place, starts, put, items=items)[0][1]
    put_near = near + [_step("put_down", ("pip",)), _step("walk_to", ("pip",), to="start"), _step("pick_up", ("pip",), to="gift")]
    assert "'pip' stands" in iso_move_problems(place, starts, put_near, items=items)[0][1]   # it put the gift down by the table


def test_the_replay_walks_round_objects_that_are_not_there() -> None:
    place = pond()
    walk = [_step("walk_to", ("pip",), to="far")]
    blocked = iso_move_problems(place, {"pip": "start"}, walk, hidden=["bridge"])
    assert len(blocked) == 1 and "cannot walk" in blocked[0][1]
    shown = [IsoStep("beats[0].actions[0]", "b1", "reveal", ("bridge",), {}), *walk]
    assert iso_move_problems(place, {"pip": "start"}, shown, hidden=["bridge"]) == []
    gone = [IsoStep("beats[0].actions[0]", "b1", "hide", ("bridge",), {}), *walk]
    assert len(iso_move_problems(place, {"pip": "start"}, gone)) == 1


# ----- the stage: params and checks ---------------------------------------------------------------


ISO = {"map": POND, "spots": SPOTS, "objects": [{"object": "table", "at": "table"}, {"object": "well", "at": "well"},
                                                  {"object": "bridge", "at": {"column": 4, "row": 1}, "shown": False},
                                                  {"object": "lamp", "at": {"column": 7, "row": 4}, "on": True}]}


def test_iso_props_and_object_states() -> None:
    params = stage_params(iso=ISO, characters=[{"name": "pip", "at": "start"}], props=[{"prop": "gift", "at": "table"}, {"prop": "flower", "at": "well"}])
    assert params.iso.states() == {"bridge": ObjectState(shown=False), "lamp": ObjectState(on=True)}
    names = registry.get("stage").cls.target_names(params)
    assert {"gift", "flower", "table", "bridge", "lamp"} <= set(names)
    placements = params.layout(frame_width=FW, frame_height=FH, stage_width=FW)
    gift = next(p for p in placements if p.name == "gift")
    view = iso_view(params.iso.parsed(), FW, FH)
    assert gift.feet == pytest.approx(view.point(1.5, 2.5, OBJECT_KINDS["table"].top))


@pytest.mark.parametrize(
    "change,message",
    [
        ({"props": ["sofa"]}, "a sofa is a ready-made object"),
        ({"props": [{"prop": "gift", "at": "left"}]}, "props\\[0\\].at: on an iso place a small thing stands at a spot"),
        ({"props": [{"prop": "gift", "at": "table", "depth": 0.3}]}, "remove depth"),
        ({"props": [{"prop": "gift", "name": "well", "at": "table"}]}, "'well' is also the name of an object"),
        ({"objects": [{"object": "well", "at": "well", "on": True}]}, "on is for a lamp, a house or a tower"),
        ({"objects": [{"object": "bench", "at": "well", "open": True}]}, "open is for a house"),
    ],
)
def test_iso_staging_refuses_what_makes_no_sense(change: dict[str, Any], message: str) -> None:
    iso = {**ISO, **({"objects": change["objects"]} if "objects" in change else {})}
    props = change.get("props", [])
    with pytest.raises(ValidationError, match=message):
        stage_params(iso=iso, characters=[{"name": "pip", "at": "start"}], props=props)


def iso_project(make_project, beats: list[dict[str, Any]], **params: Any) -> Project:
    stage = {"idle": False, "background": "#BFE3F5", "iso": ISO, "props": [{"prop": "gift", "at": "table"}],
             "characters": [{"name": "pip", "at": "start"}, {"name": "kit", "at": "table"}], **params}
    scenes = [{"id": "pond", "type": "stage", "params": stage, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


def problems(project: Project, scene: str = "pond") -> list[tuple[str, str]]:
    spec = project.scene(scene)
    with extensions.project_session(project) as theme:
        cls = registry.get(spec.type).cls
        return actions.scene_actions(spec.type, cls, spec, cls.validate_params(spec.params, theme), theme)[1]


@pytest.mark.parametrize(
    "action,message",
    [
        ({"open": "well"}, "'well' \\(a well\\) cannot open"),
        ({"switch_on": "table"}, "'table' \\(a table\\) cannot be switched on"),
        ({"hide": "pip"}, "'pip' is not an object of the place"),
        ({"throw": "pip", "to": "far"}, "throw is not for an iso place"),
        ({"blow_away": "gift"}, "blow_away is not for an iso place"),
        ({"pick_up": "pip", "to": "gift"}, "'pip' stands 2 cells from 'gift'"),
        ({"walk_to": "pip", "to": "far"}, "cannot walk from"),
    ],
)
def test_the_stage_checks_staging_actions(make_project, action: dict[str, Any], message: str) -> None:
    found = problems(iso_project(make_project, [{"text": "Something happens.", "actions": [action]}]))
    assert any(re.search(message, text) for _, text in found), found


def test_hide_is_for_iso_places(make_project) -> None:
    scenes = [{"id": "flat", "type": "stage", "params": {"characters": ["pip"], "props": ["rock"]},
               "beats": [{"text": "Go.", "actions": [{"hide": "rock"}]}]}]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))
    assert any("hide is for the objects of an iso place" in text for _, text in problems(project, "flat"))


def test_a_revealed_bridge_is_walked_over(make_project) -> None:
    beats = [{"text": "The bridge appears and pip crosses.", "actions": [{"reveal": "bridge"}, {"walk_to": "pip", "to": "far", "at": 0.3}]}]
    assert problems(iso_project(make_project, beats)) == []


# ----- a tiny render -------------------------------------------------------------------------------


@pytest.mark.render
def test_staging_renders(make_project, tmp_path: Path) -> None:
    from vidgen.introspect import LayoutRecorder

    beats = [
        {"text": "Pip walks to the table and picks up the gift.", "actions": [{"walk_to": "pip", "to": "table"},
                                                                          {"pick_up": "pip", "to": "gift", "at": 0.6}]},
        {"text": "Pip gives it to Kit.", "shot": "two_shot pip kit", "actions": [{"give": "pip", "to": "kit"}]},
        {"text": "The lamp goes out and the bridge appears.", "actions": [{"switch_off": "lamp"}, {"reveal": "bridge"}]},
        {"text": "Kit puts the gift down and the camera follows Pip.", "actions": [{"put_down": "kit"}, {"follow": "pip"},
                                                                                 {"walk_to": "pip", "to": "far", "at": 0.2}]},
    ]
    project = iso_project(make_project, beats)
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "pond", tmp_path / "media", recorder)
    last = {frame["beat"]: frame for frame in recorder.frames}   # each beat's last still
    named = {beat: {o["name"]: o for o in frame["objects"] if o["name"]} for beat, frame in last.items()}
    wide = last["pond_b1"]["camera"]["zoom"]   # the establishing view: the wide view (§89.13)
    assert 1.0 <= wide <= ISO_WIDE_MAX
    assert last["pond_b2"]["camera"]["zoom"] > 2 and last["pond_b2"]["shot"]["kind"] == "two_shot"
    assert last["pond_b3"]["camera"]["zoom"] == pytest.approx(wide)   # back after the shot's beat
    assert last["pond_b4"]["camera"]["zoom"] > 1.5   # the follow zoomed in
    assert scene.holdings.holder("gift") is None and scene.props["gift"].iso_feet[2] == pytest.approx(0.0)
    assert scene.iso_scenery.states[scene.iso_scenery.index["lamp"]] == ObjectState(on=False)
    assert scene.iso_scenery.states[scene.iso_scenery.index["bridge"]].shown and "iso_bridge" in named["pond_b4"]
    assert "iso_bridge" not in named["pond_b1"] and "iso_lamp" in named["pond_b1"]
    assert scene.iso_cells["pip"] == (6, 0) and "iso_place" in named["pond_b1"]


def test_a_tile_is_drawn_as_manim_draws_a_picture_but_only_where_it_shows() -> None:
    from manim import ImageMobject, tempconfig
    from manim.camera.camera import Camera

    from vidgen.cartoon.iso_pictures import draw_tile

    pixels = np.zeros((64, 64, 4), dtype=np.uint8)
    ramp = np.linspace(0, 255, 64).astype(np.uint8)
    pixels[..., 0], pixels[..., 1], pixels[..., 2] = ramp[None, :], ramp[:, None], 120
    pixels[..., 3] = 255
    pixels[:, :8, 3] = 0   # a transparent band
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": FW, "frame_height": FH}):
        image = ImageMobject(pixels).scale_to_fit_width(3.0).move_to([6.0, 1.0, 0.0])   # partly out of the frame
        mine, theirs = Camera(), Camera()
        theirs.display_image_mobject(image, theirs.pixel_array)
        draw_tile(mine, image, mine.pixel_array)
    shown, drawn = theirs.pixel_array[..., 3] > 128, mine.pixel_array[..., 3] > 128
    assert shown.sum() > 200 and abs(int(shown.sum()) - int(drawn.sum())) < 0.05 * shown.sum()   # the same place
    both = shown & drawn
    assert np.abs(mine.pixel_array.astype(int) - theirs.pixel_array.astype(int))[both].mean() < 8   # resampled alike


def test_the_flower_prop_is_held_by_its_stem() -> None:
    from vidgen.cartoon.props import PROP_GRIPS, SMALL_PROPS, draw_prop
    from vidgen.theme import Theme

    flower = draw_prop("flower", height=1.0, theme=Theme())
    assert "flower" in SMALL_PROPS and PROP_GRIPS[("flower", None)] == (0.0, 0.3)
    assert flower.height == pytest.approx(1.0) and flower.grip_point()[1] < flower.get_center()[1] + 0.2
