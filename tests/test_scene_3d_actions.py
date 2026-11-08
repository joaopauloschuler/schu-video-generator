"""Object actions and character stand-ins of the ``3d`` scene type (Step 300, DESIGN.md §114.11–
114.12): the planned motion of the objects, the world, arrows and camera following it, the
description's tracks, the actions as `vidgen validate` checks them, the framing lint; a tiny
render through Playwright's Chromium (skipped when it is missing)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from vidgen.cli import check_project
from vidgen.config import FormatConfig, ThemeConfig, ThreeDHiddenRule, ThreeDOffFrameRule
from vidgen.lint.rules import StillContext
from vidgen.lint.three_d_rule import three_d_hidden, three_d_off_frame
from vidgen.project import Project
from vidgen.theme import Theme
from vidgen.three_d import browser
from vidgen.three_d.camera import CameraMove, camera_tracks
from vidgen.three_d.description import nose_color, plan_world, scene_description
from vidgen.three_d.framing import framing_3d, track_value
from vidgen.three_d.motion import ObjectChange, held_keys
from vidgen.three_d.spec import Scene3DParams

THEME = Theme.for_format(ThemeConfig(), FormatConfig())
FPS = 10


def params(**raw: Any) -> Scene3DParams:
    return Scene3DParams.model_validate(raw)


def world_of(p: Scene3DParams, *changes: ObjectChange, frames: int = 60):
    return plan_world(p, FPS, frames, list(changes))


PLAZA = {
    "floor": True,
    "objects": [
        {"id": "ana", "shape": "standin", "name": "Ana", "position": [-3, 0.8, 0], "rotation": [0, 90, 0]},
        {"id": "crate", "position": [0, 0.5, 0]},
        {"id": "cart", "shape": "group", "position": [0, 0, 3]},
        {"id": "wheel", "parent": "cart", "shape": "cylinder", "size": [0.5, 0.2, 0.5], "position": [1, 0.25, 0]},
        {"id": "ball", "shape": "sphere", "size": 0.6, "position": [3, 0.3, 0], "visible": False},
        {"id": "tag", "shape": "label", "text": "Plaza", "position": [0, 2, 0], "screen_size": True},
        {"id": "pointer", "shape": "arrow", "position": [0, 3, 3], "to": "cart"},
    ],
}


# ----- params -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"objects": [{"id": "a", "name": "A"}]}, "only a stand-in has a name"),
        ({"objects": [{"id": "a", "voice": "ana"}]}, "only a stand-in speaks"),
        ({"objects": [{"id": "a", "screen_size": True}]}, "only a label keeps its size"),
        ({"objects": [{"id": "a", "shape": "standin", "size": 1}]}, "[width, height, depth]"),
        ({"objects": [{"id": "a", "shape": "standin", "size": [1, 0.5, 1]}]}, "taller"),
        ({"objects": [{"id": "a", "shape": "standn"}]}, "did you mean 'standin'?"),
        ({"objects": [{"id": "p", "shape": "arrow", "to": "head"}, {"id": "head", "parent": "p"}]}, "its own part"),
    ],
)
def test_bad_stand_ins_are_named(raw: dict[str, Any], message: str) -> None:
    from vidgen.errors import VidgenError
    from vidgen.scenes.scene_3d import Scene3D

    with pytest.raises(VidgenError) as exc:
        Scene3D.parse_params(raw, "s", THEME)
    assert message in str(exc.value)


# ----- planned motion ---------------------------------------------------------------------------


def test_move_eases_from_where_it_is_and_the_next_move_stops_it() -> None:
    p = params(objects=[{"id": "a"}])
    w = world_of(p, ObjectChange("move", "a", 0.0, 1.0, "linear", point=(4, 0, 0)),
                 ObjectChange("move", "a", 0.5, 1.5, "linear", by=(0, 2, 0)))
    m = w.motion
    assert np.allclose(m.value("a", "position", 5), [2, 0, 0])   # halfway when the second starts
    assert np.allclose(m.value("a", "position", 10), [2, 1, 0])  # the first stopped there
    assert np.allclose(m.value("a", "position", 15), [2, 2, 0]) and np.allclose(m.value("a", "position", 50), [2, 2, 0])


def test_children_move_with_their_group_and_scale_with_it() -> None:
    p = params(**PLAZA)
    w = world_of(p, ObjectChange("move", "cart", 0.0, 1.0, "linear", by=(0, 0, -2)), ObjectChange("scale", "cart", 1.0, 2.0, "linear", factor=(2, 2, 2)))
    assert np.allclose(w.position("wheel", 0.0), [1, 0.25, 3]) and np.allclose(w.position("wheel", 1.0), [1, 0.25, 1])
    assert np.allclose(w.position("wheel", 2.0), [2, 0.5, 1])   # twice as far from the group's origin
    assert w.focus("wheel", 2.0)[1] == pytest.approx(2 * w.focus("wheel", 0.0)[1])


def test_rotate_spin_and_face() -> None:
    p = params(objects=[{"id": "a", "rotation": [0, 170, 0]}, {"id": "b", "position": [0, 0, -5]}])
    w = world_of(p, ObjectChange("rotate", "a", 0.0, 1.0, by=(90, 0, 0)), ObjectChange("spin", "a", 1.0, 2.0, turns=-0.5, axis="z"),
                 ObjectChange("face", "a", 2.0, 2.5, toward="b"))
    m = w.motion
    assert np.allclose(m.value("a", "rotation", 10), [90, 170, 0]) and np.allclose(m.value("a", "rotation", 20), [90, 170, -180])
    assert np.allclose(m.value("a", "rotation", 25), [90, 180, -180])   # b is at -z: yaw 180, the shorter way from 170


def test_show_hide_fade_and_grow() -> None:
    p = params(objects=[{"id": "a", "visible": False}])
    w = world_of(p, ObjectChange("show", "a", 0.0, 1.0, "linear"), ObjectChange("hide", "a", 2.0, 3.0, "linear", style="grow"))
    m = w.motion
    assert m.opacity("a", 0) == 0 and m.opacity("a", 5) == pytest.approx(0.5) and m.opacity("a", 15) == 1
    assert np.allclose(m.scale("a", 25), 0.5) and m.opacity("a", 25) == 1 and m.opacity("a", 30) == 0
    assert w.opacity("a", 3.5) == 0


def test_highlights_ramp_and_the_brightest_wins() -> None:
    p = params(objects=[{"id": "a"}])
    w = world_of(p, ObjectChange("highlight", "a", 0.0, 2.0, color="#ff0000", strength=0.5),
                 ObjectChange("highlight", "a", 1.0, 3.0, color="#0000ff", strength=1.0))
    m = w.motion
    assert np.allclose(m.value("a", "glow", 0), 0) and np.allclose(m.value("a", "glow", 5), [0.5, 0, 0])
    assert np.allclose(m.value("a", "glow", 15), [0.5, 0, 1]) and np.allclose(m.value("a", "glow", 40), 0)


def test_walk_turns_then_walks_and_stops_in_front_of_an_object() -> None:
    p = params(**PLAZA)
    w = world_of(p, ObjectChange("walk", "ana", 0.0, None, "linear", toward="crate", speed=1.0))
    m = w.motion
    end = m.value("ana", "position", 59)
    gap = w.follow("crate", 0.0)[1] + 0.25 + 0.15
    assert end[1] == pytest.approx(0.8) and end[0] == pytest.approx(-gap) and end[2] == pytest.approx(0)
    assert m.value("ana", "rotation", 0)[1] == 90   # already facing +x: no turn
    lifted = [m.value("ana", "position", n)[1] for n in range(60)]
    assert max(lifted) > 0.8 + 0.01   # it bobs on its way
    turned = world_of(p, ObjectChange("walk", "ana", 0.0, 2.0, point=(-3, -3)))
    assert turned.motion.value("ana", "rotation", 59)[1] == pytest.approx(180) and np.allclose(turned.motion.value("ana", "position", 30), [-3, 0.8, -3])


def test_path_goes_through_its_points_and_turns_along_it() -> None:
    p = params(objects=[{"id": "a"}])
    w = world_of(p, ObjectChange("path", "a", 0.0, 2.0, "linear", points=((2, 0, 0), (2, 0, 2)), turn=True))
    m = w.motion
    assert np.allclose(m.value("a", "position", 20), [2, 0, 2])
    assert m.value("a", "rotation", 1)[1] == pytest.approx(90, abs=8) and m.value("a", "rotation", 20)[1] == pytest.approx(0, abs=8)
    straight = world_of(p, ObjectChange("path", "a", 0.0, 2.0, "linear", points=((2, 0, 0), (2, 0, 2)), smooth=False))
    assert np.allclose(straight.motion.value("a", "position", 10), [2, 0, 0])


def test_a_change_reads_where_another_object_is_when_it_starts() -> None:
    p = params(objects=[{"id": "a", "shape": "standin", "position": [0, 0.8, 0]}, {"id": "b", "position": [5, 0.5, 0]}])
    w = world_of(p, ObjectChange("move", "b", 0.0, 1.0, point=(0, 0.5, 5)), ObjectChange("face", "a", 2.0, 2.5, toward="b"))
    assert w.motion.value("a", "rotation", 30)[1] == pytest.approx(0)   # faces +z, where b went


# ----- the description --------------------------------------------------------------------------


def describe(p: Scene3DParams, changes: list[ObjectChange] = (), moves: list[CameraMove] = (), frames: int = 40) -> dict[str, Any]:
    return scene_description(p, THEME, width=160, height=90, fps=FPS, frames=frames, beats=[], camera_moves=list(moves), object_changes=list(changes))


def test_tracks_hold_a_key_per_frame_while_an_object_changes() -> None:
    d = describe(params(**PLAZA), [ObjectChange("move", "cart", 1.0, 2.0, by=(0, 0, -2)), ObjectChange("show", "ball", 0.0, 0.5),
                                   ObjectChange("highlight", "crate", 0.0, 1.0)])
    tracks = {(t["target"], t["property"]): t for t in d["timeline"]["tracks"]}
    cart = tracks[("cart", "position")]["keys"]
    assert [k["t"] for k in cart] == [round(n / FPS, 6) for n in range(10, 21)]
    assert tracks[("ball", "opacity")]["keys"][0]["value"] == [0.0] and tracks[("ball", "opacity")]["keys"][-1]["value"] == [1.0]
    assert ("crate", "emissive") in tracks
    pointer = {prop for (target, prop) in tracks if target == "pointer"}
    assert pointer == {"position", "rotation", "length"}   # the arrow follows the cart
    length = tracks[("pointer", "length")]["keys"]
    assert length[-1]["value"][0] > length[0]["value"][0]   # the cart moved away from under it
    objects = {o["id"]: o for o in d["objects"]}
    assert objects["ball"]["opacity"] == 0.0 and "opacity" not in objects["crate"]
    assert objects["ana"]["name"] == "Ana" and objects["ana"]["nose"].startswith("#") and objects["ana"]["name_size"] == pytest.approx(0.224)
    assert objects["tag"]["screen_depth"] > 0
    still = describe(params(objects=[{"id": "a", "spin": [0, 90, 0]}]))
    assert len(still["timeline"]["tracks"]) == 1 and len(still["timeline"]["tracks"][0]["keys"]) == 2   # a spin alone: 2 keys, as before


def test_held_keys_and_track_values() -> None:
    keys = held_keys([[0], [0], [1], [2], [2], [2]], 10)
    assert [k["t"] for k in keys] == [0.1, 0.2, 0.3] and held_keys([[1], [1]], 10) == []
    track = {"keys": [{"t": 0.0, "value": [0.0]}, {"t": 1.0, "value": [4.0]}], "easing": "linear"}
    assert track_value(track, 0.25) == [1.0] and track_value(track, 9) == [4.0]


def test_nose_contrasts_with_its_body() -> None:
    assert nose_color("#ffffff") == "#808080" and nose_color("#000000") == "#8c8c8c"


# ----- the camera follows moving objects --------------------------------------------------------


def test_camera_fly_to_keeps_its_distance_to_a_moving_object() -> None:
    p = params(objects=[{"id": "a"}], camera={"position": [0, 0, 10], "look_at": [0, 0, 0]})
    w = world_of(p, ObjectChange("move", "a", 1.0, 2.0, "linear", by=(3, 0, 0)), frames=40)
    position, look = camera_tracks(p, w, [CameraMove("fly_to", 0.0, 0.5, target="a", distance=4)], FPS, 40)
    values = {k["t"]: k["value"] for k in position["keys"]}
    assert np.allclose(values[0.5], [0, 0, 4]) and np.allclose(values[2.0], [3, 0, 4])
    assert np.allclose(look["keys"][-1]["value"], [3, 0, 0]) and position["keys"][-1]["t"] == 2.0   # holds once it stops


def test_camera_look_at_an_object_follows_it_from_the_start() -> None:
    p = params(objects=[{"id": "a"}], camera={"position": [0, 2, 10], "look_at": "a"})
    w = world_of(p, ObjectChange("move", "a", 0.0, 1.0, "linear", by=(0, 0, -2)), frames=20)
    position, look = camera_tracks(p, w, [], FPS, 20)
    assert np.allclose(look["keys"][-1]["value"], [0, 0, -2]) and all(np.allclose(k["value"], [0, 2, 10]) for k in position["keys"])
    assert camera_tracks(p, world_of(p, frames=20), [], FPS, 20) == []   # nothing moves: no tracks


# ----- the actions in a project -------------------------------------------------------------------


def project(make_project, actions: list[dict[str, Any]], scene_type: str = "3d") -> Project:
    p = PLAZA if scene_type == "3d" else {"text": "Hi"}
    root = make_project({"title": "3D", "scenes": [{
        "id": "s", "type": scene_type, "params": p,
        "beats": [{"text": "Ana stands on the plaza."}, {"text": "Then she walks to the crate.", "actions": actions}],
    }]})
    return Project.load(root)


def test_object_actions_validate(make_project) -> None:
    ok = project(make_project, [
        {"object_walk": "ana", "at": "@walks", "to": "crate"}, {"object_face": "ana", "to": [1, 2]}, {"object_move": "crate", "by": [0, 1, 0]},
        {"object_path": "cart", "points": [[1, 0, 1], [2, 0, 0]], "turn": True}, {"object_rotate": "crate", "to": [0, 45, 0]},
        {"object_spin": "wheel", "turns": 2, "axis": "x"}, {"object_scale": "crate", "to": [1, 2, 1]}, {"object_show": "ball", "style": "grow"},
        {"object_hide": "tag"}, {"object_highlight": "cart", "color": "accent", "run_time": 3},
    ])
    assert check_project(ok) == []
    problems = "\n".join(check_project(project(make_project, [
        {"object_walk": "crate", "to": [1, 1]},
        {"object_walk": "ana", "to": "crat"},
        {"object_face": "ana", "to": "ana"},
        {"object_move": "crate", "to": [1, 1, 1], "by": [0, 1, 0]},
        {"object_rotate": "pointer", "by": [0, 90, 0]},
        {"object_highlight": "tag"},
        {"object_spin": "crate", "turns": 0},
        {"action": "object_move", "to": [1, 1, 1]},
        {"object_scale": "crate", "to": 0},
        {"object_show": "bal"},
    ])))
    for text in ["only a stand-in walks", "no object 'crat'; did you mean 'crate'", "cannot face itself", "give to or by, one of them",
                 "it cannot be turned", "a label does not glow", "turns: 0 does not turn it", "object_move needs the id of an object",
                 "a scale must be positive", "no object 'bal'; did you mean 'ball'"]:
        assert text in problems, text
    elsewhere = "\n".join(check_project(project(make_project, [{"object_show": "x"}], scene_type="text_card")))
    assert "changes an object of a 3D scene (type: 3d)" in elsewhere


# ----- lint ----------------------------------------------------------------------------------------


def test_framing_finds_objects_off_the_frame_and_hidden() -> None:
    p = params(objects=[{"id": "front", "position": [0, 0, 2]}, {"id": "back", "size": 0.6}, {"id": "aside", "position": [9, 0, 0]}],
               camera={"position": [0, 0, 6], "look_at": [0, 0, 0]})
    d = describe(p)
    seen = {o["id"]: o for o in framing_3d(d, world_of(p, frames=40), 0.0)}
    assert seen["back"]["hidden"] == 1.0 and seen["back"]["by"] == "front" and seen["front"]["hidden"] == 0
    assert seen["aside"]["off"] == 1.0 and seen["front"]["off"] == 0
    behind = describe(p, moves=[CameraMove("move", 0.0, 0.5, point=(0, 0, -6), look_at=(0, 0, -12))])
    assert {o["id"]: o for o in framing_3d(behind, world_of(p, frames=40), 1.0)}["front"]["box"] is None


def test_lint_rules_judge_only_what_the_beat_is_about() -> None:
    objects = [{"id": "ana", "shape": "standin", "box": [10, 10, 30, 30], "off": 0.8, "hidden": 0.0, "by": None},
               {"id": "ben", "shape": "standin", "box": [40, 10, 60, 30], "off": 0.0, "hidden": 0.9, "by": "crate"},
               {"id": "crate", "shape": "box", "box": [40, 10, 60, 30], "off": 0.9, "hidden": 0.9, "by": "ana"}]
    ctx = StillContext({"width": 160, "height": 90}, {"camera": {"zoom": 1.0}, "three_d": {"objects": objects, "spoken": ["ana", "ben"]}})
    off = list(three_d_off_frame(ctx, ThreeDOffFrameRule()))
    hidden = list(three_d_hidden(ctx, ThreeDHiddenRule()))
    assert [i.message.split("'")[1] for i in off] == ["ana"] and "80% outside the frame" in off[0].message
    assert [i.message.split("'")[1] for i in hidden] == ["ben"] and "behind 'crate'" in hidden[0].message
    zoomed = StillContext({"width": 160, "height": 90}, {"camera": {"zoom": 2.0}, "three_d": {"objects": objects, "spoken": ["ana"]}})
    assert list(three_d_off_frame(zoomed, ThreeDOffFrameRule())) == []


# ----- render (Chromium) --------------------------------------------------------------------------


@pytest.mark.render
def test_page_draws_stand_ins_hidden_objects_glow_and_arrow_length() -> None:
    pytest.importorskip("playwright.sync_api")
    if browser.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    p = params(background="#000000", camera={"position": [0, 0.8, 5], "look_at": [0, 0.8, 0]}, objects=[
        {"id": "ana", "shape": "standin", "name": "Ana", "color": "#4060e0", "position": [-1, 0.8, 0]},
        {"id": "box", "color": "#202020", "position": [1, 0.8, 0], "size": 0.8},
        {"id": "ghost", "shape": "sphere", "color": "#ffffff", "position": [0, 2.2, 0], "size": 0.5, "visible": False},
        {"id": "pin", "shape": "arrow", "color": "#e04040", "position": [0, -0.6, 0], "to": [0, 0.2, 0], "size": [0.1, 1, 0.1]},
    ])
    changes = [ObjectChange("highlight", "box", 0.0, 2.0, "linear", color="#00ff00", strength=1.0), ObjectChange("show", "ghost", 0.5, 1.0, "linear"),
               ObjectChange("move", "pin", 0.0, 1.0, "linear", by=(0, -0.6, 0))]
    d = scene_description(p, THEME, width=160, height=90, fps=FPS, frames=12, beats=[], object_changes=changes)
    with browser.PageRenderer(d) as page:
        first, later = page.frame(0).astype(int), page.frame(10).astype(int)
    assert first[45, 50, 2] > 100   # the stand-in's blue body
    assert later[45, 105][1] > first[45, 105][1] + 80   # the box glows green at its peak
    assert first[10, 80].max() < 40 and later[10, 80].min() > 150   # the hidden sphere came in
    pin_first = (first[:, 78:83, 0] > 120).sum()
    pin_later = (later[:, 78:83, 0] > 120).sum()
    assert pin_later > pin_first + 5   # the arrow's tail moved down: it got longer


@pytest.mark.render
@pytest.mark.slow
def test_lint_finds_a_speaking_stand_in_behind_a_box(make_project) -> None:
    pytest.importorskip("playwright.sync_api")
    if browser.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")
    from vidgen.lint import lint_project

    root = make_project({
        "title": "3D", "format": {"width": 160, "height": 90, "fps": 5}, "preview": {"width": 160, "height": 90, "fps": 5},
        "narration": {"words_per_second": 4.0, "pad": 0.2}, "voices": {"ana": {}},
        "scenes": [{
            "id": "hide", "type": "3d",
            "params": {"camera": {"position": [0, 1, 6], "look_at": [0, 1, 0]},
                       "objects": [{"id": "wall", "size": [3, 3, 0.4], "position": [0, 1.5, 2]},
                                   {"id": "ana", "shape": "standin", "position": [0, 0.8, -1]},
                                   {"id": "ball", "shape": "sphere", "position": [9, 1, 0]}]},
            "beats": [{"id": "b1", "voice": "ana", "text": "I am talking behind the wall."},
                      {"id": "b2", "text": "And the ball rolls away.", "actions": [{"object_move": "ball", "by": [5, 0, 0]}]}],
        }],
    })
    result = lint_project(Project.load(root), rules=["three_d_off_frame", "three_d_hidden"])
    messages = [f.message for f in result.findings]
    assert any("'ana'" in m and "hidden behind 'wall'" in m for m in messages), messages
    assert any("'ball'" in m and "outside the frame" in m for m in messages), messages
