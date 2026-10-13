"""Step 109: rooms (indoor sets) on a stage: the wall, floor, windows and doors (DESIGN.md §69.42)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen.cartoon.acting import passage_fade
from vidgen.cartoon.room import (
    FLOOR_SPREAD,
    ROW_DEPTH,
    WALL_DEPTH,
    WINDOW_SKIES,
    Box,
    SkyChange,
    floor_lines,
    floor_rows,
    room_geometry,
    shade,
    sky_at,
    wall_depth,
    wallpaper_dots,
    wallpaper_stripes,
    window_parts,
    window_sky,
)
from vidgen.cartoon.stage import FAR_RISE, StageItem, depth_scale
from vidgen.cli import check_project
from vidgen.includes import apply_set
from vidgen.lint.color import hex_rgb, relative_luminance
from vidgen.project import Project

FW, FH = 16.0, 9.0


def inside(inner: Box, outer: Box, slack: float = 1e-9) -> bool:
    return (outer.left - slack <= inner.left <= inner.right <= outer.right + slack
            and outer.bottom - slack <= inner.bottom <= inner.top <= outer.top + slack)


# ----- geometry (no manim) ------------------------------------------------------------------------


def test_the_wall_stands_at_its_depth_behind_the_floor() -> None:
    room = room_geometry(ground=0.2, depth=0.5, size=0.45, frame_width=FW, frame_height=FH, ceiling=True)
    line = (0.2 + FAR_RISE * 0.5 - 0.5) * FH
    assert room.wall_line == pytest.approx(line) and room.floor.bottom == -FH / 2 and room.wall.top == FH / 2
    assert room.unit == pytest.approx(0.45 * FH * depth_scale(0.5))   # a character's height at the wall
    assert room.skirting.bottom == room.wall_line < room.skirting.top
    assert room.ceiling is not None and room.ceiling.top == FH / 2 and room.ceiling.bottom > room.skirting.top
    wide = room_geometry(ground=0.2, depth=0.5, size=0.45, frame_width=FW, frame_height=FH, stage_width=2 * FW)
    assert (wide.wall.left, wide.wall.right) == (-FW, FW) and wide.ceiling is None


def test_wall_depth_defaults_behind_everything_on_the_floor() -> None:
    items = [StageItem("pip", "character", "left", 0.2), StageItem("sun", "prop", "right", 0.9, lift=0.5)]
    assert wall_depth(items) == WALL_DEPTH   # the hanging sun does not count
    assert wall_depth([*items, StageItem("tree", "prop", "centre", 0.7)]) == 0.7
    assert wall_depth(items, 0.1) == 0.1   # given: as given (the stage's params check it)


def test_floor_rows_get_deeper_towards_the_front() -> None:
    floor = Box(-8.0, -4.5, 8.0, -2.0)
    rows = floor_rows(floor, 3.0)
    edges = [floor.top, *rows, floor.bottom]
    depths = [a - b for a, b in zip(edges, edges[1:])]
    assert len(rows) >= 2 and all(b > a for a, b in zip(depths, depths[1:]))
    assert depths[0] == pytest.approx(ROW_DEPTH * 3.0, rel=0.6)
    assert floor_rows(Box(-8.0, -4.5, 8.0, -4.4), 3.0) == []   # too shallow for a row


@pytest.mark.parametrize("flooring", ["boards", "tiles"])
def test_floor_lines_stay_on_the_floor(flooring: str) -> None:
    floor = Box(-8.0, -4.5, 8.0, -2.0)
    lines = floor_lines(flooring, floor, 3.0)
    assert lines
    for (x0, y0), (x1, y1) in lines:
        for x, y in ((x0, y0), (x1, y1)):
            assert floor.left - 1e-9 <= x <= floor.right + 1e-9 and floor.bottom - 1e-9 <= y <= floor.top + 1e-9
    if flooring == "tiles":   # lines spread out from the middle towards the front
        fan = [(a, b) for a, b in lines if a[1] != b[1] and b[1] == floor.bottom and a[0] != 0]
        assert fan and all(b[0] == pytest.approx(a[0] * FLOOR_SPREAD) for a, b in fan)
    assert floor_lines("plain", floor, 3.0) == []
    with pytest.raises(ValueError, match="unknown flooring 'carpet'"):
        floor_lines("carpet", floor, 3.0)


def test_wallpaper_patterns_stay_on_the_wall() -> None:
    wall = Box(-8.0, -2.0, 8.0, 4.5)
    stripes = wallpaper_stripes(wall, 3.0)
    assert len(stripes) > 10 and all(inside(s, wall) for s in stripes)
    dots = wallpaper_dots(wall, 3.0)
    assert len(dots) > 20 and all(wall.left < x < wall.right and wall.bottom < y < wall.top for x, y, _ in dots)


def test_pattern_shades_read_on_light_and_dark_walls() -> None:
    light, dark = "#E9DCC9", "#252238"
    assert relative_luminance(hex_rgb(shade(light, 0.1))) < relative_luminance(hex_rgb(light))
    assert relative_luminance(hex_rgb(shade(dark, 0.1))) > relative_luminance(hex_rgb(dark))


def test_window_parts() -> None:
    window = window_parts(2.0, -2.0, 3.0, width=0.6, height=0.6, sill=0.4)
    assert window.frame.center[0] == pytest.approx(2.0) and window.frame.bottom == pytest.approx(-2.0 + 0.4 * 3.0)
    assert window.frame.width == pytest.approx(1.8) and inside(window.glass, window.frame)
    assert all(inside(bar, window.glass) for bar in window.bars) and window.sill.top <= window.glass.bottom
    assert window.rod is not None and window.rod.bottom > window.frame.top and len(window.curtains) == 2
    left, right = window.curtains
    assert min(x for x, _ in left) < window.frame.left and max(x for x, _ in right) > window.frame.right
    bare = window_parts(2.0, -2.0, 3.0, curtains=False)
    assert bare.rod is None and bare.curtains == ()


# ----- the sky outside ----------------------------------------------------------------------------


def test_window_sky_follows_the_light() -> None:
    day, sunset, night, indoor = (window_sky(name) for name in ("day", "sunset", "night", "indoor"))
    r, g, b = hex_rgb(day.top)
    assert b > r and day.stars == 0
    assert hex_rgb(sunset.bottom)[0] > hex_rgb(sunset.bottom)[2]   # warm low in the sky
    assert night.stars == 1.0 and 0 < indoor.stars < 1   # lamplight inside: evening outside
    lum = {name: relative_luminance(hex_rgb(window_sky(name).bottom)) for name in WINDOW_SKIES}
    assert lum["night"] < lum["indoor"] < lum["sunset"] < lum["day"]
    tinted = window_sky(("#FF0000", 1.0))   # a tint multiplies the day's sky
    assert hex_rgb(tinted.top)[1] == 0 and hex_rgb(tinted.top)[0] == pytest.approx(hex_rgb(day.top)[0], abs=1 / 255)
    with pytest.raises(ValueError, match="unknown light 'noon'"):
        window_sky("noon")


def test_the_sky_outside_fades_with_a_light_change() -> None:
    day, night = window_sky("day"), window_sky("night")
    change = [SkyChange(2.0, 2.0, night)]
    assert sky_at(day, change, 1.0) == day and sky_at(day, change, 5.0) == night
    half = sky_at(day, change, 3.0)
    assert half.stars == pytest.approx(0.5) and half.top not in (day.top, night.top)


def test_passage_fade_through_a_door() -> None:
    assert passage_fade(0.0, 2.0, fade_in=0.4) == 0.0 and passage_fade(0.4, 2.0, fade_in=0.4) == 1.0
    assert passage_fade(1.0, 2.0) == 1.0 and passage_fade(2.0, 2.0, fade_out=0.4) == 0.0
    assert passage_fade(0.25, 0.5, fade_in=1.0, fade_out=1.0) == 1.0   # each fade at most half the walk
    assert 0 < passage_fade(0.1, 2.0, fade_in=0.4) < 1


def test_a_door_opens_in_place() -> None:
    from vidgen.cartoon.props import draw_prop
    from vidgen.theme import Theme

    door = draw_prop("door", height=4.0, theme=Theme())
    feet = door.feet().copy()
    closed = door.shape_width("closed")
    family = door.get_family()
    assert door.shapes == ("closed", "open") and door.shape == "closed"
    door.show_shape("open")
    assert door.shape == "open" and door.get_family() == family   # live copies: only points change
    assert door.feet() == pytest.approx(feet) and door.height == pytest.approx(4.0)
    assert door.shape_width("open") > closed and door.get_left()[0] < feet[0] - closed / 2   # the leaf swings out on the hinge side
    mirrored = draw_prop("door", height=4.0, theme=Theme(), facing="left", shape="open")
    assert mirrored.get_right()[0] > mirrored.feet()[0] + closed / 2


def test_a_walk_fades_out_through_a_door_and_comes_back_whole() -> None:
    from test_cartoon_moving import figure

    from vidgen.cartoon.transition import Walk

    c = figure()
    own = [m.fill_rgbas[:, 3].copy() for m in c.get_family()]
    leave = Walk(c, 2.0, park_x=20.0, fade_out=0.35)
    leave.begin()
    leave.interpolate(0.5)
    assert c.shown == 1.0 and all((m.fill_rgbas[:, 3] == a).all() for m, a in zip(c.get_family(), own))
    leave.interpolate(1.0)
    assert c.shown == 0.0 and all(m.fill_rgbas[:, 3].max() == 0 for m in c.get_family())
    leave.clean_up_from_scene(type("S", (), {"remove": lambda self, *m: None, "mobjects": []})())
    assert c.feet()[0] == pytest.approx(20.0) and c.shown == 1.0   # parked off stage, whole again
    assert all((m.fill_rgbas[:, 3] == a).all() for m, a in zip(c.get_family(), own))
    plain = Walk(c, 18.0)
    plain.begin()
    plain.interpolate(0.0)
    assert plain.fade_in == plain.fade_out == 0.0 and c.shown == 1.0   # no door: nothing fades


# ----- the stage's params --------------------------------------------------------------------------


def test_room_params_doors_are_props_and_marks() -> None:
    params = stage_params(room={"windows": ["left", 0.7], "doors": [0.8, {"name": "back", "at": "far_left", "open": True}]},
                          characters=[{"name": "pip", "at": "door"}], props=["table"])
    assert stage_params(room=True).room.windows == []   # true: a room with the defaults
    assert [w.at for w in params.room.windows] == ["left", 0.7]
    assert params.prop_names() == ["table", "door", "back"] and params.door_names() == ["door", "back"]
    assert params.stage_marks() == {"door": 0.8, "back": 0.1}
    doors = {item.name: item for item in params.items()}
    assert doors["door"].depth == WALL_DEPTH == doors["back"].depth and doors["door"].scale == pytest.approx(1.3)
    assert [p.open for p in params.stage_props()[1:]] == [False, True]
    deep = stage_params(room={"doors": ["right"]}, props=[{"prop": "bush", "at": 0.2, "depth": 0.7}])
    assert deep.wall_depth() == 0.7 and deep.items()[-1].depth == 0.7   # the wall behind the bush
    assert stage_params(props=["table"]).stage_marks() == {} and stage_params().door_names() == []


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"room": True, "background": "primary"}, "a room draws its own wall and floor: remove background"),
        ({"room": True, "ground_color": "tertiary"}, "remove ground_color"),
        ({"room": True, "wind": "windy"}, "there is no wind in a room"),
        ({"room": True, "particles": ["rain"]}, "rain stays outdoors"),
        ({"room": {"depth": 0.2}, "characters": [{"name": "pip", "depth": 0.5}]}, "'pip' stands at depth 0.5, behind the room's wall"),
        ({"room": {"doors": ["right"]}, "marks": {"door": 0.4}}, "'door' is also a mark"),
        ({"room": {"doors": [{"name": "pip"}]}, "characters": ["pip"]}, "'pip' is also the name of a character or another prop"),
        ({"room": {"doors": ["nowhere"]}}, r"room\.doors\[0\]\.at: unknown mark 'nowhere'"),
        ({"room": {"windows": [1.5]}}, r"room\.windows\[0\]\.at: x position 1.5"),
        ({"room": {"flooring": "carpet"}}, "flooring"),
    ],
)
def test_bad_room_params(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        stage_params(**params)


def test_sets_hold_rooms() -> None:
    room = {"wallpaper": "stripes", "doors": ["right"]}
    merged = apply_set({"room": room, "light": "indoor"}, {"room": {"wallpaper": "dots"}}).params
    assert merged["room"] == {"wallpaper": "dots", "doors": ["right"]} and merged["light"] == "indoor"   # key by key
    outdoor = apply_set({"room": room}, {"background": "primary"}).params
    assert "room" not in outdoor and outdoor["background"] == "primary"   # a backdrop of its own drops the set's room
    indoor = apply_set({"background": ["#9CCBEA", "#E4F3FB"], "ground_color": "tertiary", "marks": {"tree": 0.8}}, {"room": True}).params
    assert indoor == {"marks": {"tree": 0.8}, "room": True}


def room_project(make_project, params: dict[str, Any], beats: list[dict[str, Any]]) -> Project:
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


def test_actions_know_doors_and_keep_the_weather_out(make_project) -> None:
    params = {"room": {"doors": [0.8]}, "characters": ["pip", {"name": "kit", "at": "right"}]}
    good = [{"text": "Kit comes in.", "actions": [{"enter": "kit", "door": "door"}, {"close": "door", "at": 0.9}]},
            {"text": "Pip goes out.", "actions": [{"exit": "pip", "door": "door"}, {"walk_to": "kit", "to": "door"}]}]
    assert check_project(room_project(make_project, params, good)) == []
    bad = [{"text": "Kit comes in.", "actions": [{"enter": "kit", "door": "hatch", "side": "left"}, {"wind": "windy"}, {"particles": "snow"}]}]
    problems = check_project(room_project(make_project, params, bad))
    assert any("no door 'hatch' on this stage (its room's doors: door)" in p for p in problems)
    assert any("give side (an edge) or door, not both" in p for p in problems)
    assert any("there is no wind in a room" in p for p in problems)
    assert any("snow stays outdoors" in p for p in problems)
    outdoor = check_project(room_project(make_project, {"characters": ["pip"]}, [{"text": "Hi.", "actions": [{"enter": "pip", "door": "door"}]}]))
    assert any("no door 'door' on this stage (its room's doors: none" in p for p in outdoor)


# ----- render ---------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_room_at_night_with_a_character_coming_in_through_the_door(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen import extensions, registry
    from vidgen.cartoon.character import character
    from vidgen.cartoon.shading import LIT

    params = {
        "light": "night", "idle": False,
        "room": {"wallpaper": "stripes", "flooring": "tiles", "ceiling": True, "windows": [0.3], "doors": [{"at": 0.8}]},
        "characters": ["pip", {"name": "kit", "at": "right"}],
    }
    beats = [{"id": "b1", "text": "Kit comes in through the door.", "actions": [{"enter": "kit", "door": "door"}]}]
    project = room_project(make_project, params, beats)
    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)   # no fade out: the stage stays to look at
    scene, objects = render_with_layout(project, "home", tmp_path / "media")
    door, kit = scene.props["door"], scene.cast["kit"]
    assert door.shape == "open" and kit.shown == 1.0   # opened by the entrance; kit fully seen at the end
    assert float(kit.feet()[0]) == pytest.approx(scene.homes["kit"])
    fresh = character("kit", height=kit.standing_height)   # its own opacities are back after the fade in
    assert [float(m.fill_rgbas[:, 3].max()) for m in kit.get_family()] == [float(m.fill_rgbas[:, 3].max()) for m in fresh.get_family()]
    views = scene.window_views
    assert views is not None and len(views.skies) == 1
    assert not getattr(views.skies[0], LIT, False) and getattr(door, LIT, False)   # the sky outside is not graded by the room's light
    assert views.skies[0].get_fill_colors()[0].to_hex().upper() == WINDOW_SKIES["night"].top.upper()
    assert all(s.fill_rgbas[:, 3].max() > 0 for s in views.stars[0].submobjects) or len(views.stars[0].submobjects) == 0
    names = {o.get("name"): o for o in objects}
    assert {"room", "window_views", "room_front", "door", "kit", "pip"} <= set(names)
    assert names["room"]["order"] < names["window_views"]["order"] < names["room_front"]["order"] < names["door"]["order"] < names["pip"]["order"]
    shadows = [c.mobject for group in scene.shadows for c in group.casters]
    assert door not in shadows and kit in shadows   # a door in the wall casts no shadow


@pytest.mark.render
def test_the_set_fades_in_as_one_picture(make_project, tmp_path: Path, monkeypatch) -> None:
    """While the room fades in, nothing shows through what stands in front of it (pip over the
    armchair, the armchair over the sofa): each frame is the finished picture blended with the
    background by one amount, not each thing faded on its own (§69.51)."""
    import numpy as np
    from manim.scene.scene_file_writer import SceneFileWriter

    params = {"idle": False, "room": {"wallpaper": "plain", "flooring": "plain"},
              "props": [{"prop": "sofa", "at": 0.5, "against": "wall"}, {"prop": "armchair", "at": 0.5, "depth": 0.2}],
              "characters": [{"name": "pip", "at": 0.5, "depth": 0.1}]}
    project = room_project(make_project, params, [{"id": "b1", "text": "Pip waits in front of the armchair for a while, quietly."}])
    frames: list[np.ndarray] = []
    write = SceneFileWriter.write_frame

    def recording(self: Any, frame: Any, num_frames: int = 1) -> None:
        frames.extend([np.asarray(frame)[:, :, :3].astype(float)] * num_frames)
        write(self, frame, num_frames)

    monkeypatch.setattr(SceneFileWriter, "write_frame", recording)
    render_with_layout(project, "home", tmp_path / "media")
    background, done = frames[0], frames[7]   # nothing yet; the set after its 1 s fade (5 fps)
    assert np.abs(frames[8] - done).max() == 0   # finished: nothing moves
    change = done - background
    power = (change**2).sum(axis=2)
    contrast = power > 40**2
    for mid in frames[1:5]:   # per pixel: how far from the background towards the finished picture
        blend = (((mid - background) * change).sum(axis=2) / np.maximum(power, 1.0))[contrast]
        amount = float(np.median(blend))
        assert 0.02 < amount < 0.98
        assert float(np.mean(np.abs(blend - amount) > 0.12)) < 0.01   # one amount everywhere (anti-aliased edges aside)
