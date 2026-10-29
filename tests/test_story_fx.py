"""Story-cartoon features of Step 246 (DESIGN.md §100.6-§100.13): framing, alarms and shutters,
holograms that materialise and flicker, iridescence and afterimages, holding hands, a hologram
display, a view through a portal, lab and memory objects, a flashback's look, the new sounds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_living import frames_of
from test_cartoon_stage import CAST, stage_params
from vidgen import ambience, sfx
from vidgen.cartoon import alarm, apparition, holo_display, portal
from vidgen.cartoon.iso_objects import LIT_OBJECTS, OBJECT_COLORS, ObjectLook, object_lights, object_shapes
from vidgen.cartoon.iso_scenery import window_faces
from vidgen.cartoon.iso_stage import iso_view, wide_view
from vidgen.cartoon.lighting import LightGrade, blend_grades, grade_pixels, grade_rgbas, light_grade, tint_grade
from vidgen.cartoon.living_drawing import DISPLAY_PARTS, LivingProp, living_parts
from vidgen.cartoon.props import draw_prop
from vidgen.cartoon.shots import ShotFigure, frame_shot, shot_figures
from vidgen.cartoon.vignette import flashback_grade, vignette_pixels
from vidgen.cli import check_project
from vidgen.config import AfterimageConfig, CharacterEntry, IridescentConfig, ShotConfig
from vidgen.project import Project
from vidgen.theme import Theme
from vidgen.world.iso import OBJECT_KINDS, ObjectPlacing, parse_iso_map, place_objects

# ----- alarms and shutters (no manim) ---------------------------------------------------------------


def test_alarm_spans_from_starts_and_stops() -> None:
    spans = alarm.alarm_spans([(2.0, True, "#FF0000", 1.6), (8.0, False, "#FF0000", 1.6), (9.0, False, "#FF0000", 1.6)])
    assert spans == [alarm.AlarmSpan(2.0, 8.0, "#FF0000", 1.6)]
    running = alarm.alarm_spans([(1.0, True, "#FF0000", 1.6), (3.0, True, "#FFAA00", 1.0)])
    assert [(s.start, s.end, s.color) for s in running] == [(1.0, 3.0, "#FF0000"), (3.0, None, "#FFAA00")]
    assert running[1].over_at() == float("inf") and spans[0].over_at() == pytest.approx(8.0 + alarm.ALARM_FALL)


def test_alarm_darkens_and_pulses_red() -> None:
    base = light_grade("night")
    span = alarm.AlarmSpan(1.0, 10.0)
    assert alarm.alarm_grade(base, [span], 0.5) == base   # before it starts
    dark = alarm.alarm_grade(base, [span], 1.0 + 4 * span.period)            # a pulse's bottom
    bright = alarm.alarm_grade(base, [span], 1.0 + 4.5 * span.period)        # its top
    assert sum(dark.multiply) < sum(bright.multiply)
    r, g, b = bright.multiply
    assert r > 2.5 * g and r > 2.5 * b and r < 0.85   # red, and still a dim room
    assert alarm.alarm_grade(base, [span], 10.0 + alarm.ALARM_FALL + 0.01) == base   # faded out
    assert alarm.alarm_changing([span], 0.0, 1.5) and not alarm.alarm_changing([span], 11.0, 20.0)
    assert not alarm.alarm_settled([span], 10.0) and alarm.alarm_settled([span], 11.0)


def test_shutters_slam_down_and_roll_up() -> None:
    moves = [(1.0, True), (5.0, False)]
    assert alarm.shutter_level(False, moves, 0.5) == 0.0
    assert 0.0 < alarm.shutter_level(False, moves, 1.0 + alarm.SHUTTER_CLOSE_SECONDS / 2) < 0.5   # accelerating
    assert alarm.shutter_level(False, moves, 2.0) == 1.0
    assert alarm.shutter_level(False, moves, 5.0 + alarm.SHUTTER_OPEN_SECONDS) == 0.0
    assert alarm.shutter_level(True, [], 3.0) == 1.0
    assert alarm.shutters_changing(moves, 0.9, 1.1) and not alarm.shutters_changing(moves, 2.0, 4.9)


# ----- appearing, flickering, iridescence -------------------------------------------------------------


def test_materialise_is_a_wireframe_first() -> None:
    outline, fill = apparition.materialise_levels(apparition.WIREFRAME_SHARE * 0.9, 1.0)
    assert outline > 0.3 and fill == 0.0
    assert apparition.materialise_levels(0.0, 1.0) == (0.0, 0.0) and apparition.materialise_levels(1.0, 9.0) == (1.0, 1.0)
    assert 0.0 < apparition.materialise_levels(0.8, 1.0)[1] < 1.0


def test_flicker_dips_now_and_then() -> None:
    levels = [apparition.flicker_level(t, seed=3) for t in np.arange(0.0, 30.0, 0.02)]
    assert min(levels) < 0.75 and max(levels) <= 1.0
    assert np.mean(np.array(levels) > 0.9) > 0.8   # mostly steady
    assert apparition.flicker_level(4.2, 3) == apparition.flicker_level(4.2, 3)


def test_iridescence_turns_hues_but_keeps_ink_and_white() -> None:
    skin = (0.6, 0.75, 0.85)
    assert apparition.iridescent_rgb((0.05, 0.05, 0.07), 0.5, 3.0) == (0.05, 0.05, 0.07)
    assert apparition.iridescent_rgb((1.0, 1.0, 1.0), 0.5, 3.0) == (1.0, 1.0, 1.0)
    a, b = apparition.iridescent_rgb(skin, 0.2, 0.0), apparition.iridescent_rgb(skin, 0.2, 4.0)
    assert a != b and apparition.iridescent_rgb(skin, 0.9, 0.0) != a   # with time and up the figure
    assert IridescentConfig().seconds == 12.0 and CharacterEntry(name="v", iridescent=True).iridescent_look() == IridescentConfig()
    assert CharacterEntry(name="v", afterimages={"life": 1.0}).afterimage_look() == AfterimageConfig(life=1.0)
    assert CharacterEntry(name="v").iridescent_look() is None and CharacterEntry(name="v").afterimage_look() is None
    assert CharacterEntry(name="v", hologram={"flicker": False}).hologram_look().flicker is False


# ----- framing ------------------------------------------------------------------------------------------


def test_a_closeup_of_two_shows_both_faces() -> None:
    near, far = ShotFigure("ana", -1.0, -2.0, 2.0, "right"), ShotFigure("ben", 0.6, -1.2, 2.0, "left")
    view = frame_shot("closeup", [near, far], frame_width=16.0, frame_height=9.0, bounds=(-8.0, 8.0, -4.5, 4.5))
    width, height = 16.0 / view.scale, 9.0 / view.scale
    for figure in (near, far):
        assert abs(figure.x - view.center_x) < width / 2 - 0.2   # whole across
        assert view.center_y - height / 2 < figure.head_top - 0.62 * figure.height and figure.head_top < view.center_y + height / 2
    assert view.scale > 1.2 and view.center_x == pytest.approx((-1.0 + 0.6) / 2, abs=0.05)
    present = {"ana": near, "ben": far, "cy": ShotFigure("cy", 3.0, -2.0, 2.0)}
    assert shot_figures("closeup", ["ana", "ben"], present).subjects == ("ana", "ben")
    assert shot_figures("closeup", ["ana"], present).subjects == ("ana",)
    assert ShotConfig.model_validate({"kind": "closeup", "of": ["ana", "ben"], "clear": True}).action().shorthand()["clear"] is True


LAB = "##%###%#\n#......#\n#.c..r.#\n#......#\n##+#####"


def _lab(objects: list[ObjectPlacing] = ()) -> Any:
    return place_objects(parse_iso_map(LAB, names={"c": "desk", "r": "rack"}, place="indoor"), tuple(objects))


def test_a_rooms_wide_view_can_fill_the_frame() -> None:
    place = _lab()
    view = iso_view(place, 16.0, 9.0)
    auto, _ = wide_view(place, view, 16.0, 9.0)
    fill, _ = wide_view(place, view, 16.0, 9.0, fit="fill")
    zoomed, _ = wide_view(place, view, 16.0, 9.0, fit=1.6)
    assert fill < auto and zoomed == pytest.approx(16.0 / 1.6)


# ----- lab and memory objects, shutters' windows ------------------------------------------------------


def test_lab_and_memory_objects_draw_and_blink() -> None:
    for kind in ("console", "server_rack", "projector_pad", "whiteboard", "flower_arch", "chess_table"):
        assert kind in OBJECT_KINDS and kind in OBJECT_COLORS
    place = _lab([ObjectPlacing("console", "desk"), ObjectPlacing("server_rack", "rack")])
    console, rack = place.objects
    look = ObjectLook("#8A93A3", "#5FD8FF")
    assert any(getattr(s, "glow", False) for s in object_shapes(console, look, 0.0))   # its screens glow
    assert set(LIT_OBJECTS) == {"console", "server_rack", "tower"}
    assert len(object_lights(rack, 0.0)) == 18 and object_lights(console, 0.0)
    assert OBJECT_KINDS["projector_pad"].walkable and OBJECT_KINDS["console"].top is not None


def test_windows_that_show_into_a_room() -> None:
    faces = window_faces(_lab())
    assert len(faces) == 2 and all(len(face) == 4 for face in faces)
    assert all(face[2][2] > face[0][2] for face in faces)   # the top is above the sill
    assert window_faces(parse_iso_map("....\n.%..\n....")) == []   # outdoors: none


# ----- a hologram display and a view through a portal -------------------------------------------------


def test_display_patterns_stay_on_the_panel() -> None:
    assert holo_display.display_frame("fractal", None, 3.0) is None
    left, bottom, right, top = holo_display.PANEL
    for pattern in holo_display.DISPLAY_PATTERNS:
        frame = holo_display.display_frame(pattern, 0.0, 4.0, seed=2)
        assert frame is not None and frame.grow == 1.0
        points = [p for curve in frame.curves for p in curve] + [(b[0], b[1]) for b in (*frame.bars, *frame.lines)]
        assert points and all(left - 1e-9 <= x <= right + 1e-9 and bottom - 1e-9 <= y <= top + 1e-9 for x, y in points)
    growing = holo_display.display_frame("text", 1.0, 1.0 + holo_display.GROW_SECONDS / 2)
    assert growing is not None and 0.0 < growing.grow < 1.0 and len(growing.lines) == 1   # the first line being written


def test_a_living_display_shows_its_panel_when_on() -> None:
    prop = draw_prop("hologram_display", height=2.0, theme=Theme(), living=True)
    live = LivingProp(prop, pattern="data")
    panel = living_parts(prop, "holo_panel")[0]
    assert all(living_parts(prop, part) for part in DISPLAY_PARTS) and len(panel.points) == 0
    live.switch(True, 1.0)
    assert live.changing(0.5, 1.5) and live.changing(3.0, 4.0)
    live.update(3.0)
    assert len(panel.points) > 0 and live.glow is not None


def test_a_portal_view_is_inside_the_oval() -> None:
    rx, ry = portal.HALF_WIDTH, portal.HALF_HEIGHT
    cx, cy = portal.CENTRE
    for view in portal.PORTAL_VIEWS:
        shapes = portal.portal_view(view, rx, ry, 2.0, seed=1)
        assert 3 <= len(shapes) <= portal.VIEW_SHAPES
        for shape in shapes:
            assert all(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0 + 1e-6 for x, y in shape.points)
    prop = draw_prop("portal", height=3.0, theme=Theme(), living=True, view="coast")
    live = LivingProp(prop)
    assert live.view == "coast" and len(living_parts(prop, "portal_view")) == portal.VIEW_SHAPES
    live.switch(True, 0.0)
    live.update(portal.OPEN_SECONDS + 0.5)
    assert any(len(m.points) for m in living_parts(prop, "portal_view"))


# ----- light: a flashback's look -----------------------------------------------------------------------


def test_flashback_fades_and_warms_the_colours() -> None:
    base = light_grade("day")
    look = flashback_grade(base)
    assert look.changes_colors and look.saturation == pytest.approx(0.4)
    red = grade_rgbas(np.array([[1.0, 0.0, 0.0, 1.0]]), look)[0]
    assert red[1] > 0.1 and red[0] < 0.9   # faded towards grey, warm
    pixels = grade_pixels(np.array([[[255, 0, 0]]], dtype=np.uint8), look)
    assert pixels[0, 0, 1] > 20
    assert blend_grades(tint_grade("#FF0000", 0.5), light_grade("night"), 0.3).saturation == 1.0   # exactly: nothing desaturated
    assert LightGrade().changes_colors is False
    picture = vignette_pixels(64, 36)
    assert picture[0, 0, 3] > 150 and picture[18, 32, 3] == 0


# ----- sounds --------------------------------------------------------------------------------------------


def test_the_story_sounds_and_beds() -> None:
    for name in ("alarm", "crackle", "hum", "drone", "slam"):
        samples = sfx.synthesize(name)
        assert len(samples) == round(sfx.BUILTIN_SOUNDS[name].duration * sfx.RATE)
        assert sfx.loudness(samples) == pytest.approx(sfx.LOUDNESS_TARGET, abs=1.5) and sfx.peak_db(samples) <= sfx.PEAK_CEILING + 1e-6
    for bed, level in (("alarm", ambience.ALARM_LEVEL), ("hum", ambience.HUM_LEVEL)):
        loop = ambience.BEDS[bed].loop()
        assert loop.shape[1] == 2 and ambience.integrated_loudness(loop) == pytest.approx(level, abs=0.5)
    assert "hum" in ambience.SET_BEDS and "alarm" not in ambience.SET_BEDS
    assert ambience.set_ambience(["hum"], room=True, lights=[(0.0, "night")], rain=[], end=5.0) == [("hum", 0.0, 5.0)]


# ----- validation ----------------------------------------------------------------------------------------


def stage(make_project, params: dict[str, Any], beats: list[dict[str, Any]], characters: list[dict[str, Any]] | None = None) -> Project:
    scenes = [{"id": "home", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=characters or CAST, scenes=scenes)))


ISO_LAB = {"place": "indoor", "map": "##%###%#\n#......#\n#.c.p..#\n#..a.r.#\n#..b...#\n##+#####",
           "spots": {"c": "desk", "p": "pad", "a": "here", "b": "there", "r": "rift"},
           "objects": [{"object": "console", "at": "desk"}, {"object": "projector_pad", "at": "pad"}]}


def test_story_actions_validate(make_project) -> None:
    cast = [*CAST, {"name": "ai", "hologram": True, "look": {"body": "tall"}}]
    params = {"light": "night", "iso": {**ISO_LAB, "wide": "fill"},
              "props": [{"prop": "hologram_display", "name": "screen", "at": "desk", "pattern": "text"},
                        {"prop": "portal", "name": "tear", "at": "rift", "view": "stars"}],
              "characters": [{"name": "pip", "at": "here"}, {"name": "kit", "at": "there"}, {"name": "ai", "at": "pad"}]}
    good = [{"text": "The alarm sounds and the shutters slam down over the windows.",
             "actions": [{"alarm": "start"}, {"shutters": "close", "at": 0.3}, {"materialise": "ai", "at": 0.5}]},
            {"text": "They take each other's hand, and the alarm stops.", "shot": {"kind": "closeup", "of": ["pip", "kit"], "clear": True},
             "actions": [{"hold_hands": "pip", "with": "kit"}, {"alarm": "stop", "at": 0.6}, {"let_go_hands": "kit", "at": 0.9}]}]
    assert check_project(stage(make_project, params, good, cast)) == []
    bad = [{"text": "Wrong.", "actions": [{"alarm": "on"}, {"shutters": "down"}, {"hold_hands": "pip", "with": "pip"},
                                           {"pick_up": "kit", "to": "tear"}]}]
    problems = " ".join(check_project(stage(make_project, params, bad, cast)))
    for expected in ("alarm: start", "shutters: close", "its own hand", "cannot be held"):
        assert expected in problems, problems
    outdoors = {"map": "....\n.a..\n....", "spots": {"a": "here"}}
    no_room = check_project(stage(make_project, {"iso": outdoors, "characters": [{"name": "pip", "at": "here"}]},
                                  [{"text": "Shut it all.", "actions": [{"shutters": "close"}]}]))
    assert any("indoor iso place" in p for p in no_room)


def test_prop_keys_for_their_props() -> None:
    assert stage_params(props=[{"prop": "portal", "view": "meadow"}]).props[0].view == "meadow"
    assert stage_params(props=[{"prop": "hologram_display", "pattern": "data"}]).props[0].pattern == "data"
    for bad, message in (({"prop": "lamp", "view": "coast"}, "view is for a portal"), ({"prop": "tv", "pattern": "text"}, "pattern is for a hologram_display"),
                         ({"prop": "portal", "view": "moon"}, "coast")):
        with pytest.raises(ValidationError, match=message):
            stage_params(props=[bad])
    assert stage_params(flashback=True).flashback is True
    assert stage_params(flashback={"vignette": 0.3}).flashback.vignette == 0.3
    with pytest.raises(ValidationError):
        stage_params(iso={**ISO_LAB, "wide": 3.0})


def test_lint_lets_hands_held_stand_close() -> None:
    from vidgen.lint.cartoon_rules import _riding_together

    assert _riding_together({"name": "ana", "hand_in_hand": "ben"}, {"name": "ben", "hand_in_hand": "ana"})
    assert not _riding_together({"name": "ana"}, {"name": "ben"})


# ----- rendering -----------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_lab_under_an_alarm(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen import extensions, registry

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    cast = [*CAST, {"name": "ai", "hologram": True, "look": {"body": "tall"}},
            {"name": "vis", "iridescent": True, "afterimages": True, "look": {"body": "tall"}}]
    params = {"light": "night", "iso": {**ISO_LAB, "wide": "fill", "objects": [*ISO_LAB["objects"], {"object": "server_rack", "at": {"column": 6, "row": 2}}]},
              "props": [{"prop": "hologram_display", "name": "screen", "at": "desk", "on": True}, {"prop": "portal", "name": "tear", "at": "rift", "view": "coast"}],
              "characters": [{"name": "pip", "at": "here"}, {"name": "kit", "at": "there"}, {"name": "ai", "at": "pad"},
                             {"name": "vis", "at": "rift", "scale": 1.4}]}
    beats = [{"text": "The hologram takes shape on its pad.", "actions": [{"materialise": "ai", "at": 0.0}, {"hold_hands": "pip", "with": "kit"}]},
             {"text": "Then the alarm goes off and the rift tears open.",
              "actions": [{"alarm": "start", "at": 0.0}, {"shutters": "close", "at": 0.0}, {"switch_on": "tear", "at": 0.0},
                          {"enter": "vis", "door": "rift", "at": 0.3}]}]
    scene, frames = frames_of(stage(make_project, params, beats, cast), tmp_path / "lab", monkeypatch)
    assert scene.iso_shutters is not None and scene.light is not None and scene.light.alarms
    assert ("pip", "kit") in scene.hand_holds or ("kit", "pip") in scene.hand_holds
    first, last = frames[3].astype(float), frames[-1].astype(float)
    red = lambda f: float(f[..., 0].mean() - f[..., 1].mean())  # noqa: E731
    assert red(last) > red(first) + 2   # the room is red under the alarm
    sounds = {s.sound for s in scene.sfx_log}
    assert {"slam", "riser", "chime"} <= sounds   # the shutters, the hologram taking shape
    beds = {b["bed"] for b in scene.timings().get("ambience", [])}
    assert "alarm" in beds


@pytest.mark.render
def test_a_flashback_frame_is_framed_and_faded(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen import extensions, registry

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    params = {"background": ["#9CCBEA", "#E4F3FB"], "flashback": True, "characters": [{"name": "pip", "at": 0.5}]}
    _, frames = frames_of(stage(make_project, params, [{"text": "Long ago, on a summer day."}]), tmp_path / "memory", monkeypatch)
    frame = frames[-1].astype(float)
    corner, middle = frame[:8, :8].mean(), frame[40:50, 70:90].mean()
    assert corner < middle - 30   # the vignette darkens the corners
    sky = frame[10, 80]
    assert abs(sky[0] - sky[2]) < 60   # the blue sky faded towards a warm grey
