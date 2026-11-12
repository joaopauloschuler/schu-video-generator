"""Shapes, groups and camera moves of the ``3d`` scene type (Step 299, DESIGN.md §114.7–114.9):
params and their messages, the world transforms, the camera paths and tracks, the camera
actions as `vidgen validate` checks them, the validate warning for a missing Chromium; a few
tiny renders through Playwright's Chromium (skipped when it is missing)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vidgen.cli import check_project, validate_warnings
from vidgen.config import FormatConfig, ThemeConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.theme import Theme
from vidgen.three_d import browser
from vidgen.three_d.camera import CameraMove, Pose, camera_problems, camera_tracks, ease, move_path, start_pose
from vidgen.three_d.description import scene_description
from vidgen.three_d.spec import Scene3DParams
from vidgen.three_d.world import World, euler_xyz, rotation_matrix

THEME = Theme.for_format(ThemeConfig(), FormatConfig())


def params(**raw: Any) -> Scene3DParams:
    return Scene3DParams.model_validate(raw)


def errors_of(**raw: Any) -> str:
    from vidgen.scenes.scene_3d import Scene3D

    with pytest.raises(VidgenError) as exc:
        Scene3D.parse_params(raw, "s", THEME)
    return str(exc.value)


TOWN = {
    "floor": True,
    "objects": [
        {"id": "tower", "shape": "group", "position": [1, 0, 0]},
        {"id": "base", "parent": "tower", "shape": "cylinder", "size": [1, 2, 1], "position": [0, 1, 0]},
        {"id": "roof", "parent": "tower", "shape": "cone", "size": 1, "position": [0, 2.5, 0]},
        {"id": "tag", "parent": "tower", "shape": "label", "text": "Tower", "position": [0, 3.4, 0]},
        {"id": "ball", "shape": "sphere", "size": 0.8, "position": [-2, 0.4, 0]},
        {"id": "ring", "shape": "torus", "size": [1.2, 0.2, 1.2]},
        {"id": "pointer", "shape": "arrow", "position": [-2, 3, 0], "to": "ball"},
    ],
}


# ----- params -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"objects": [{"id": "a", "shape": "label"}]}, "a label needs a text"),
        ({"objects": [{"id": "a", "text": "hi"}]}, "only a label has a text"),
        ({"objects": [{"id": "a", "shape": "label", "text": "hi", "size": [1, 1, 1]}]}, "one number"),
        ({"objects": [{"id": "a", "to": [1, 1, 1]}]}, "only an arrow points"),
        ({"objects": [{"id": "a", "shape": "arrow", "to": [1, 1, 1], "rotation": [0, 0, 9]}]}, "leave rotation out"),
        ({"objects": [{"id": "a", "shape": "group", "size": 2}]}, "a group draws nothing"),
        ({"objects": [{"id": "a", "shape": "torus", "size": [1, 1, 1]}]}, "thickness (1) must be less"),
        ({"objects": [{"id": "a", "size": -1}]}, "must be positive"),
        ({"objects": [{"id": "a", "parent": "a"}]}, "its own parent"),
        ({"objects": [{"id": "roof", "parent": "tower"}, {"id": "tower", "shape": "group"}]}, "write 'tower' before 'roof'"),
        ({"objects": [{"id": "roof", "parent": "towr"}, ]}, "no object 'towr' before this one"),
        ({"objects": [{"id": "tower", "shape": "group"}, {"id": "roof", "parent": "towr"}]}, "did you mean 'tower'?"),
        ({"floor": True, "objects": [{"id": "floor"}]}, "the floor's id"),
        ({"objects": [{"id": "ball"}, {"id": "p", "shape": "arrow", "to": "bal"}]}, "did you mean 'ball'?"),
        ({"camera": {"look_at": "bal"}, "objects": [{"id": "ball"}]}, "camera.look_at: no object 'bal'; did you mean 'ball'?"),
    ],
)
def test_bad_objects_are_named(raw: dict[str, Any], message: str) -> None:
    assert message in errors_of(**raw)


def test_sizes_default_per_shape_and_one_number_means_all_three() -> None:
    p = params(floor={"size": 8, "y": -1}, objects=[
        {"id": "a", "shape": "sphere", "size": 2}, {"id": "b", "shape": "plane", "size": 3}, {"id": "c", "shape": "label", "text": "x"},
        {"id": "d", "shape": "arrow"}, {"id": "e", "shape": "torus"}, {"id": "f", "shape": "plane", "size": [2, 5, 1]}])
    assert [o.resolved_size() for o in p.objects] == [(2, 2, 2), (3, 0, 3), (0, 0.3, 0), (0.08, 1, 0.08), (1, 0.25, 1), (2, 0, 1)]
    assert p.object_ids()[0] == "floor" and params(floor=True).floor.size == 12


# ----- the world --------------------------------------------------------------------------------


def test_rotation_round_trips_through_euler_angles() -> None:
    for angles in [(10, 20, 30), (-90, 45, 0), (170, -30, 60)]:
        assert np.allclose(rotation_matrix(euler_xyz(rotation_matrix(angles))), rotation_matrix(angles))


def test_children_move_and_turn_with_their_group() -> None:
    world = World(params(objects=[{"id": "g", "shape": "group", "position": [1, 0, 0], "spin": [0, 90, 0]},
                                  {"id": "c", "parent": "g", "position": [1, 0, 0]}]))
    assert np.allclose(world.position("c", 0.0), [2, 0, 0])
    assert np.allclose(world.position("c", 1.0), [1, 0, -1])   # a quarter turn about +y: x -> -z
    centre, radius = world.focus("g", 0.0)
    assert np.allclose(centre, [2, 0, 0]) and radius == pytest.approx(math.sqrt(3) / 2)


def test_an_arrow_to_an_object_stops_at_its_edge() -> None:
    world = World(params(objects=[{"id": "ball", "shape": "sphere", "position": [0, 0, 0]},
                                  {"id": "p", "shape": "arrow", "position": [0, 3, 0], "to": "ball"}]))
    arrow = world.objects["p"]
    assert arrow.size[1] == pytest.approx(2.5) and np.allclose(arrow.position, [0, 1.75, 0])
    assert np.allclose(rotation_matrix(arrow.rotation) @ [0, 1, 0], [0, -1, 0])   # +y turned to point down
    with pytest.raises(ValueError, match="tip is at its tail"):
        World(params(objects=[{"id": "p", "shape": "arrow", "position": [1, 1, 1], "to": [1, 1, 1]}]))


def test_description_lists_parents_first_with_labels_and_the_floor() -> None:
    d = scene_description(params(**TOWN), THEME, width=160, height=90, fps=10, frames=4, beats=[])
    ids = [o["id"] for o in d["objects"]]
    assert ids == ["floor", "tower", "base", "roof", "tag", "ball", "ring", "pointer"]
    by_id = {o["id"]: o for o in d["objects"]}
    assert "size" not in by_id["tower"] and by_id["base"]["parent"] == "tower"
    assert by_id["floor"]["shape"] == "plane" and by_id["floor"]["size"] == [12.0, 0.0, 12.0]
    assert by_id["tag"]["text"] == "Tower" and by_id["tag"]["color"].startswith("#") and by_id["tag"]["plate_opacity"] == 0.88
    assert by_id["pointer"]["size"][1] == pytest.approx(2.2)


# ----- camera moves -----------------------------------------------------------------------------


def pose(position: list[float], look_at: list[float]) -> Pose:
    return Pose(np.array(position, dtype=float), np.array(look_at, dtype=float))


def test_orbit_keeps_its_distance_and_moves_to_the_cameras_right() -> None:
    world = World(params(**TOWN))
    path = move_path(CameraMove("orbit", degrees=90, up=1), pose([0, 1, 5], [0, 0, 0]), world, 40)
    end = path(1.0)
    assert np.allclose(end.position, [5, 2, 0]) and np.allclose(end.look_at, [0, 0, 0])
    around = move_path(CameraMove("orbit", target="ball", degrees=180), pose([-2, 1, 5], [0, 0, 0]), world, 40)(1.0)
    assert np.allclose(around.position, [-2, 1, -5]) and np.allclose(around.look_at, [-2, 0.4, 0])
    with pytest.raises(ValueError, match="right above"):
        move_path(CameraMove("orbit", degrees=90), pose([0, 5, 0], [0, 0, 0]), world, 40)


def test_dolly_fly_to_look_at_and_move() -> None:
    world = World(params(**TOWN))
    start = pose([0, 0, 10], [0, 0, 0])
    assert np.allclose(move_path(CameraMove("dolly", by=4), start, world, 40)(1.0).position, [0, 0, 6])
    with pytest.raises(ValueError, match="past the point"):
        move_path(CameraMove("dolly", by=10), start, world, 40)
    fly = move_path(CameraMove("fly_to", target="ball"), start, world, 40)(1.0)
    radius = 0.4
    assert np.allclose(fly.look_at, [-2, 0.4, 0])
    distance = np.linalg.norm(fly.position - fly.look_at)
    assert 2 * math.degrees(math.asin(radius / distance)) == pytest.approx(0.6 * 40)   # fills 60 % of the fov
    assert np.allclose((fly.position - fly.look_at) / distance, [0, 0, 1])   # seen from where it looked from
    assert np.allclose(move_path(CameraMove("fly_to", target="ball", distance=3), start, world, 40)(1.0).position, [-2, 0.4, 3])
    turned = move_path(CameraMove("look_at", target="ball"), start, world, 40)
    assert np.allclose(turned(0.5).look_at, [-1, 0.2, 0]) and np.allclose(turned(1.0).position, [0, 0, 10])
    moved = move_path(CameraMove("move", point=(4, 4, 4), look_at="ball"), start, world, 40)(1.0)
    assert np.allclose(moved.position, [4, 4, 4]) and np.allclose(moved.look_at, [-2, 0.4, 0])


def test_easing_matches_the_page() -> None:
    assert ease("linear", 0.25) == 0.25 and ease("smooth", 0.5) == 0.5 and ease("smooth", 0.25) == pytest.approx(0.15625)
    assert ease("smooth", -1) == 0 and ease("smooth", 2) == 1


def test_camera_tracks_hold_a_key_per_frame_while_the_camera_moves() -> None:
    p = params(**TOWN, camera={"position": [0, 1, 5], "look_at": [0, 0, 0]})
    world = World(p)
    moves = [CameraMove("dolly", 1.0, 2.0, by=2, easing="linear"), CameraMove("orbit", 0.0, 0.5, degrees=90)]
    position, look = camera_tracks(p, world, moves, fps=10, frames=40)
    times = [k["t"] for k in position["keys"]]
    assert times == [round(n / 10, 6) for n in [*range(0, 6), *range(10, 21)]]   # the orbit, then the dolly
    assert position["target"] == look["target"] == "camera" and position["easing"] == "linear"
    assert np.allclose(position["keys"][5]["value"], [5, 1, 0])   # the orbit's end...
    assert np.allclose(position["keys"][6]["value"], [5, 1, 0])   # ...is where the dolly starts
    end = np.array(position["keys"][-1]["value"])
    assert np.linalg.norm(end - [0, 0, 0]) == pytest.approx(math.sqrt(26) - 2)
    assert camera_tracks(p, world, [], 10, 40) == []


def test_a_move_still_running_stops_when_the_next_starts() -> None:
    p = params(camera={"position": [0, 0, 10], "look_at": [0, 0, 0]})
    (position, _) = camera_tracks(p, World(p), [CameraMove("dolly", 0.0, 1.0, by=4, easing="linear"),
                                                 CameraMove("dolly", 0.5, 1.0, by=1, easing="linear")], fps=10, frames=20)
    values = {k["t"]: k["value"][2] for k in position["keys"]}
    assert values[0.5] == pytest.approx(8.0) and values[1.0] == pytest.approx(7.0)


def test_camera_problems_name_the_move_that_cannot_be_made() -> None:
    p = params(camera={"position": [0, 0, 5], "look_at": [0, 0, 0]})
    moves = [CameraMove("dolly", 1.0, by=3), CameraMove("dolly", 2.0, by=3)]
    (k, message), = camera_problems(p, moves)
    assert k == 1 and "past the point it looks at" in message
    with pytest.raises(ValueError, match="stands on"):
        start_pose(params(camera={"position": [0, 0, 0], "look_at": "a"}, objects=[{"id": "a"}]), World(params(objects=[{"id": "a"}])))


# ----- the camera actions in a project -------------------------------------------------------------


def project(make_project, actions: list[dict[str, Any]], scene_type: str = "3d", **params3d: Any) -> Project:
    p = {**TOWN, **params3d} if scene_type == "3d" else {"text": "Hi"}
    root = make_project({"title": "3D", "scenes": [{
        "id": "s", "type": scene_type, "params": p,
        "beats": [{"text": "The camera circles the tower."}, {"text": "Then it flies to the ball.", "actions": actions}],
    }]})
    return Project.load(root)


def test_camera_actions_validate(make_project) -> None:
    ok = project(make_project, [{"camera_orbit": "tower", "at": "@flies", "degrees": 120}, {"camera_fly_to": "ball", "at": 0.5},
                                {"action": "camera_dolly", "by": 1}, {"camera_look_at": "ring"}, {"action": "camera_move", "to": [5, 5, 5], "look_at": "tower"}])
    assert check_project(ok) == []
    problems = "\n".join(check_project(project(make_project, [
        {"camera_fly_to": "bal"},                       # an unknown object
        {"action": "camera_fly_to"},                    # no object
        {"camera_orbit": "tower", "around": [0, 0, 0]},
        {"action": "camera_look_at"},
        {"action": "camera_move", "to": [1, 1, 1], "look_at": "rng"},
        {"camera_dolly": "ball", "by": 1},
        {"action": "camera_orbit", "degrees": 0},
    ])))
    for text in ["no object 'bal'; did you mean 'ball'", "camera_fly_to needs the id of an object", "not both",
                 "or point: [x, y, z], one of them", "no object 'rng'; did you mean 'ring'?", "camera_dolly takes no target",
                 "degrees: 0 does not move"]:
        assert text in problems, text
    elsewhere = "\n".join(check_project(project(make_project, [{"action": "camera_dolly", "by": 1}], scene_type="text_card")))
    assert "moves the camera of a 3D scene (type: 3d)" in elsewhere


def test_a_camera_move_that_cannot_be_made_is_a_validate_problem(make_project) -> None:
    problems = check_project(project(make_project, [{"action": "camera_dolly", "by": 50}]))
    assert len(problems) == 1 and "beats[1].actions[0]" in problems[0] and "past the point it looks at" in problems[0]
    problems = check_project(project(make_project, [], objects=[{"id": "p", "shape": "arrow", "to": [0, 0, 0]}]))
    assert len(problems) == 1 and "tip is at its tail" in problems[0]


def test_validate_warns_about_a_missing_chromium_only_with_a_3d_scene(make_project, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(browser, "missing_dependency", lambda: browser.BROWSER_HINT)
    three_d = project(make_project, [])
    assert any("3d scenes (s) cannot render here" in w and "playwright install chromium" in w for w in validate_warnings(three_d))
    flat = Project.load(make_project({"title": "T", "scenes": [{"id": "t", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "Hi."}]}]}, folder="flat"))
    assert not any("3d scenes" in w for w in validate_warnings(flat))


def test_missing_dependency_is_a_cheap_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import importlib.util

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    if importlib.util.find_spec("playwright") is not None:
        assert browser.missing_dependency() == browser.BROWSER_HINT   # no chromium folder in tmp_path
        (tmp_path / "chromium_headless_shell-1").mkdir()
        listed = json.loads((Path(importlib.util.find_spec("playwright").origin).parent / "driver/package/browsers.json").read_text(encoding="utf-8"))
        revision = next(b["revision"] for b in listed["browsers"] if b["name"] == "chromium-headless-shell")
        (tmp_path / f"chromium_headless_shell-{revision}").mkdir()
        assert browser.missing_dependency() is None
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "playwright" else real(name, *a))
    assert browser.missing_dependency() == browser.INSTALL_HINT


# ----- renders (Chromium) -----------------------------------------------------------------------


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    if browser.missing_dependency() is not None:
        pytest.skip("Chromium for Playwright is not available")


@pytest.mark.slow
@pytest.mark.render
def test_page_draws_every_shape() -> None:
    _chromium_or_skip()
    shapes: list[dict[str, Any]] = [
        {"shape": "box"}, {"shape": "sphere"}, {"shape": "cylinder"}, {"shape": "cone"}, {"shape": "torus", "size": [1.6, 0.4, 1.6], "rotation": [60, 0, 0]},
        {"shape": "plane", "size": 2, "rotation": [60, 0, 0]}, {"shape": "arrow", "size": [0.3, 1.6, 0.3]}, {"shape": "label", "text": "Hi", "size": 0.6},
    ]
    first = None
    for extra in shapes:
        d = scene_description(params(background="#000000", camera={"position": [0, 0, 4]}, objects=[{"id": "x", "color": "#e04040", **extra}]),
                              THEME, width=64, height=64, fps=10, frames=1, beats=[])
        if first is None:
            first = browser.PageRenderer(d).__enter__()
        else:
            first._call("d => window.vidgen3d.load(d)", d)
        pixels = first.frame(0).astype(int)
        hit = pixels[24:40, 24:40]
        assert hit.max() > 60, extra["shape"]   # something drawn in the middle
        assert pixels[0, 0].tolist() == [0, 0, 0], extra["shape"]
    assert first is not None
    first.close()


@pytest.mark.render
@pytest.mark.slow
def test_render_moves_the_camera_on_a_word(make_project) -> None:
    _chromium_or_skip()
    from vidgen.render.pipeline import render_project

    root = make_project({
        "title": "3D", "format": {"width": 160, "height": 90, "fps": 5}, "preview": {"width": 160, "height": 90, "fps": 5},
        "narration": {"words_per_second": 4.0, "pad": 0.2},
        "scenes": [{
            "id": "cam", "type": "3d",
            "params": {"background": "#000000", "camera": {"position": [0, 1, 5], "look_at": [0, 0, 0]},
                       "objects": [{"id": "crate", "color": "#e04040", "size": 1.2}, {"id": "ball", "shape": "sphere", "color": "#40e040", "position": [3, 0, 0]}]},
            "beats": [{"id": "b1", "text": "A red box sits alone in the dark."},
                      {"id": "b2", "text": "Now we fly over to the green ball.", "actions": [{"camera_fly_to": "ball", "at": "@fly", "run_time": 0.8}]}],
        }],
    })
    render_project(Project.load(root), preview=True)
    record = json.loads((root / "build" / "preview" / "three_d" / "cam.json").read_text(encoding="utf-8"))["description"]
    b2 = record["timeline"]["beats"][1]
    position = next(t for t in record["timeline"]["tracks"] if t["target"] == "camera" and t["property"] == "position")
    first, last = position["keys"][0], position["keys"][-1]
    assert b2["start"] < first["t"] < b2["end"]   # on the word, inside beat 2
    assert last["t"] - first["t"] == pytest.approx(0.8)
    assert last["value"][0] > 2.5   # ended in front of the ball

    import av

    with av.open(str(root / "build" / "preview" / "three_d" / "cam.mkv")) as container:
        frames = [f.to_ndarray(format="rgb24") for f in container.decode(video=0)]
    start, end = frames[0][45, 80], frames[-1][45, 80]
    assert start[0] > start[1] and end[1] > end[0]   # the box in the middle first, the ball at the end
