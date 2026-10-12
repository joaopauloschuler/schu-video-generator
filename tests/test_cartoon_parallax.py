"""Step 74: parallax layers and the camera on a stage (``layers``, ``width``, ``camera_at``; the
``pan`` and ``follow`` actions; ``zoom`` going back to the view before it)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout, stage_params
from vidgen import actions, extensions, registry
from vidgen.camera import view_center_within
from vidgen.cartoon.stage import DEFAULT_FACTORS, MAX_ZOOM, StageItem, layer_half_extent, layer_transform, stage_layout
from vidgen.cli import check_project
from vidgen.lint import StillContext
from vidgen.project import Project

FW, FH = 8 * 16 / 9, 8.0


def on_screen(point: tuple[float, float], factor: float, center: tuple[float, float], zoom: float) -> np.ndarray:
    """Where a layer point drawn for the home view shows, relative to the frame's centre in home units."""
    scale, shift = layer_transform(factor, center, zoom)
    world = np.array(point) * scale + np.array(shift)
    return (world - np.array(center)) * zoom


# ----- geometry (no manim) ----------------------------------------------------------------------


@pytest.mark.parametrize("factor", [0.0, 0.3, 0.6, 1.0, 1.4, 2.5])
@pytest.mark.parametrize("center,zoom", [((0.0, 0.0), 1.0), ((3.0, 0.0), 1.0), ((-5.0, 1.2), 2.0), ((2.0, -1.0), 3.5)])
def test_layer_offsets_follow_the_factor(factor: float, center: tuple[float, float], zoom: float) -> None:
    point = (1.5, -2.0)
    expected = zoom**factor * (np.array(point) - factor * np.array(center))
    assert on_screen(point, factor, center, zoom) == pytest.approx(expected)


def test_layer_offsets_for_a_pan() -> None:
    # the camera pans 4 units right at zoom 1: the stage (and characters) move 4 left on screen,
    # a background layer 0.3 x 4, a foreground layer 1.4 x 4; a factor-0 layer stays put
    for factor in (0.0, DEFAULT_FACTORS["background"], DEFAULT_FACTORS["middle"], 1.0, DEFAULT_FACTORS["foreground"]):
        moved = on_screen((2.0, 1.0), factor, (4.0, 0.0), 1.0) - on_screen((2.0, 1.0), factor, (0.0, 0.0), 1.0)
        assert moved == pytest.approx((-4.0 * factor, 0.0))
    assert layer_transform(1.0, (4.0, -1.0), 2.0) == (1.0, (0.0, 0.0))     # the stage itself: unchanged
    assert layer_transform(0.5, (0.0, 0.0), 1.0) == (1.0, (0.0, 0.0))     # camera at home: unchanged


def test_layer_offsets_for_a_zoom() -> None:
    # zooming 2x on the middle of the frame magnifies the stage 2x, a far layer less, a near one more
    for factor in (0.3, 1.0, 1.4):
        a, b = on_screen((1.0, 0.0), factor, (0.0, 0.0), 2.0), on_screen((-1.0, 0.0), factor, (0.0, 0.0), 2.0)
        assert (a - b)[0] / 2.0 == pytest.approx(2.0**factor)
    assert on_screen((3.0, 2.0), 0.0, (5.0, -1.0), 4.0) == pytest.approx((3.0, 2.0))   # factor 0: fixed on screen


@pytest.mark.parametrize("factor", [0.0, 0.3, 1.0, 1.4])
@pytest.mark.parametrize("stage_width", [FW, 2.5 * FW])
def test_layer_extent_covers_every_view(factor: float, stage_width: float) -> None:
    half_w, half_h = layer_half_extent(factor, stage_width=stage_width, frame_width=FW, frame_height=FH)
    bounds = (-stage_width / 2, stage_width / 2, -FH / 2, FH / 2)
    rng = np.random.default_rng(7)
    for _ in range(300):
        zoom = 1.0 + (MAX_ZOOM - 1.0) * rng.random() ** 2
        width, height = FW / zoom, FH / zoom
        wanted = (bounds[0] + (bounds[1] - bounds[0]) * rng.random(), bounds[2] + (bounds[3] - bounds[2]) * rng.random())
        center = view_center_within(bounds, wanted, width, height)
        scale, shift = layer_transform(factor, center, zoom)
        # the view's corners, mapped back into the layer's home coordinates, lie inside the extent
        for sx in (-1, 1):
            for sy in (-1, 1):
                world = np.array(center) + np.array([sx * width / 2, sy * height / 2])
                home = (world - np.array(shift)) / scale
                assert abs(home[0]) <= half_w + 1e-6 and abs(home[1]) <= half_h + 1e-6
    if factor in (0.0, 1.0) and stage_width == FW:
        assert (half_w, half_h) == pytest.approx((FW / 2, FH / 2), abs=1e-3)   # exactly the frame


def test_view_stays_inside_the_bounds() -> None:
    bounds = (-10.0, 10.0, -4.0, 4.0)
    assert view_center_within(bounds, (9.0, 0.0), 8.0, 4.0) == (6.0, 0.0)
    assert view_center_within(bounds, (-3.0, -3.5), 8.0, 4.0) == (-3.0, -2.0)
    assert view_center_within(bounds, (5.0, 3.0), 24.0, 8.0) == (0.0, 0.0)   # larger than the bounds: their middle


def test_marks_on_a_wide_stage() -> None:
    items = [StageItem("pip", "character", "left"), StageItem("kit", "character", 1.0)]
    pip, kit = stage_layout(items, ground=0.2, size=0.5, frame_width=FW, frame_height=FH, stage_width=2 * FW)
    assert pip.feet[0] == pytest.approx(-0.25 * 2 * FW) and kit.feet[0] == pytest.approx(FW)
    assert pip.height == pytest.approx(4.0)   # sizes still follow the frame's shorter side


def test_hills_run_across_the_layer() -> None:
    from vidgen.scenes.stage import hill_outline

    corners = np.array(hill_outline(10.0, -2.0, -5.0, 3.0, 1.0))
    assert corners[0, :2] == pytest.approx((-10.0, -5.0)) and corners[-1, :2] == pytest.approx((10.0, -5.0))
    ridge = corners[1:-1]
    assert ridge[0, 0] == pytest.approx(-10.0) and ridge[-1, 0] == pytest.approx(10.0)
    assert ridge[:, 1].min() == pytest.approx(-2.0) and ridge[:, 1].max() == pytest.approx(-1.0, abs=0.02)
    assert np.all(np.diff(ridge[:, 0]) > 0)


# ----- params, actions and validate ---------------------------------------------------------------


def test_layer_params() -> None:
    params = stage_params(
        width=2,
        camera_at="left",
        layers=[
            {"shapes": [{"shape": "hills"}]},
            {"place": "middle", "image": "assets/trees.png", "factor": 0.5},
            {"shapes": [{"shape": "rect", "x": 0.2}]},
            {"name": "bushes", "place": "foreground", "shapes": [{"shape": "ellipse", "color": "accent"}]},
        ],
    )
    assert params.layer_names() == ["background_layer", "middle_layer", "background_layer_2", "bushes"]
    assert [layer.resolved_factor() for layer in params.layers] == [DEFAULT_FACTORS["background"], 0.5, DEFAULT_FACTORS["background"], DEFAULT_FACTORS["foreground"]]


@pytest.mark.parametrize(
    "params,message",
    [
        ({"layers": [{"place": "middle"}]}, "either image .* or shapes"),
        ({"layers": [{"image": "a.png", "shapes": [{"shape": "rect"}]}]}, "either image .* or shapes"),
        ({"layers": [{"name": "far", "shapes": [{"shape": "rect"}]}, {"name": "far", "image": "a.png"}]}, "'far' is used twice"),
        ({"layers": [{"shapes": [{"shape": "star"}]}]}, "rect"),
        ({"layers": [{"place": "sky", "image": "a.png"}]}, "background"),
        ({"layers": [{"image": "a.png", "factor": -1}]}, "greater than or equal to 0"),
        ({"camera_at": "centr"}, "camera_at: unknown mark 'centr'"),
        ({"width": 0.5}, "greater than or equal to 1"),
    ],
)
def test_bad_layer_params(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        stage_params(**params)


def camera_project(make_project, beats: list[dict[str, Any]], params: dict[str, Any] | None = None, scene_type: str = "stage") -> Project:
    if scene_type == "stage":
        params = {"width": 2, "idle": False, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}], **(params or {})}
    else:
        params = params or {"text": "Hello"}
    scenes = [{"id": "park", "type": scene_type, "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


def test_validate_checks_pan_and_follow(make_project) -> None:
    good = camera_project(
        make_project,
        [{"text": "One.", "actions": [{"action": "pan", "to": "far_right"}, {"action": "pan", "to": 0.3, "at": 0.5}]},
         {"text": "Two.", "actions": [{"pan": "kit"}, {"follow": "pip", "at": 0.5}]}],
        {"marks": {"door": 0.95}},
    )
    assert check_project(good) == []
    bad = camera_project(
        make_project,
        [{"text": "One.", "actions": [{"action": "pan"}, {"action": "pan", "target": "kit", "to": "left"}, {"action": "pan", "to": "dor"}]},
         {"text": "Two.", "actions": [{"action": "follow", "target": ["pip", "kit"]}, {"action": "pan", "to": 1.5}, {"follow": "rex"}]}],
    )
    problems = "\n".join(check_project(bad))
    assert "beats[0].actions[0].to: give a target (a character) or to (a mark or an x from 0 to 1)" in problems
    assert "beats[0].actions[1].to: give a target (a character) or to (a mark or an x from 0 to 1), not both" in problems
    assert "beats[0].actions[2].to: unknown mark 'dor'" in problems
    assert "beats[1].actions[0].target: follow takes one target" in problems
    assert "beats[1].actions[1].to" in problems and "less than or equal to 1" in problems
    assert "beats[1].actions[2].target: unknown target 'rex'" in problems
    elsewhere = camera_project(make_project, [{"text": "One.", "actions": [{"action": "pan", "to": "left"}, {"action": "pan", "to": 0.2}]}], scene_type="text_card")
    assert check_project(elsewhere) == [
        "scenes[0].beats[0].actions[0].to: 'left' is not a place this scene type knows; give an x from 0 (left edge) to 1 (right edge)"
    ]


class FakeScene:
    """Just enough of a scene for the camera actions: a camera frame, bounds and following."""

    spec = type("Spec", (), {"id": "s"})()

    def __init__(self, camera: Any, stage_width: float) -> None:
        self.camera = camera
        self.frame_width, self.frame_height = FW, FH
        self.params = stage_params(width=stage_width / FW, marks={"door": 0.95})
        self.following: Any = None

    def camera_bounds(self) -> tuple[float, float, float, float]:
        return (-self.params.width * FW / 2, self.params.width * FW / 2, -FH / 2, FH / 2)

    def camera_place(self, params: Any, place: Any) -> float:
        return registry.get("stage").cls.camera_place(params, place)

    def follow_with_camera(self, x_of: Any) -> None:
        self.following = x_of

    @property
    def camera_following(self) -> Any:
        return self.following

    def on_screen_parts(self, target: Any) -> list[Any]:
        return [target.mobject]


def test_pan_follow_and_zoom_geometry() -> None:
    """The camera actions' end views without rendering."""
    from manim import MovingCamera, Square, tempconfig

    extensions.load_builtins()
    cls = {name: registry.find_action(name).cls for name in ("pan", "follow", "zoom")}

    def use(name: str, target: Any = None, **options: Any) -> Any:
        config = actions.ActionConfig.model_validate({"action": name, **({"target": "t"} if target is not None else {}), **options})
        return cls[name](cls[name].Options(**options), config)

    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": FW, "frame_height": FH}):
        scene = FakeScene(MovingCamera(), 3 * FW)
        frame = scene.camera.frame
        (move,) = use("pan", to="door").apply(scene, [])
        assert move.target_mobject.get_center()[0] == pytest.approx(FW)   # 0.95 of 3 frames: held 1 frame from the edge
        frame.move_to(move.target_mobject.get_center())
        pan_back = use("pan", to="left")
        (move,) = pan_back.apply(scene, [])
        assert move.target_mobject.get_center()[0] == pytest.approx(-0.25 * 3 * FW)
        frame.move_to(move.target_mobject.get_center())
        (back,) = pan_back.revert(scene, [])
        assert back.target_mobject.get_center()[0] == pytest.approx(FW)   # until: back to the view before

        dot = Square(0.5).move_to([-12.0, -1.0, 0.0])
        follow = use("follow", target="t")
        (move,) = follow.apply(scene, [actions.Target(("t",), dot)])
        assert move.target_mobject.get_center()[0] == pytest.approx(-12.0) and scene.following is None
        move.clean_up_from_scene(scene)   # after the move, the camera follows
        assert scene.following() == pytest.approx(-12.0)
        assert follow.revert(scene, []) == [] and scene.following is None

        frame.move_to([-0.25 * 3 * FW, 0.0, 0.0])
        zoom = use("zoom", target="t", scale=2)
        (move,) = zoom.apply(scene, [actions.Target(("t",), Square(1).move_to([-FW * 1.4, 3.5, 0.0]))])
        assert move.target_mobject.get_center()[:2] == pytest.approx((-FW * 1.5 + FW / 4, 2.0))   # inside the stage, not the frame
        frame.become(move.target_mobject)
        (back,) = zoom.revert(scene, [])
        assert back.target_mobject.width == pytest.approx(FW) and back.target_mobject.get_center()[0] == pytest.approx(-0.25 * 3 * FW)


def test_lint_skips_frame_edges_when_the_camera_moved() -> None:
    def ctx(center: list[float], zoom: float = 1.0) -> StillContext:
        frame = {"camera": {"center": center, "zoom": zoom}, "objects": []}
        return StillContext(layout={"width": 160, "height": 90}, frame=frame)

    assert not ctx([0.0, 0.0]).camera_moved
    assert ctx([3.0, 0.0]).camera_moved and ctx([0.0, 0.0], 2.0).camera_moved


# ----- render ------------------------------------------------------------------------------------


@pytest.mark.render
def test_stage_layers_move_with_the_camera(make_project, tmp_path: Path) -> None:
    beats = [
        {"text": "Pip waits on the left.", "actions": [{"action": "pan", "to": "far_right", "at": 0.2}]},
        {"text": "Then the camera follows him.", "actions": [{"follow": "pip", "at": 0.1}]},
    ]
    layers = [
        {"name": "hills", "shapes": [{"shape": "hills", "y": 0.2, "height": 0.2, "width": 0.6}]},
        {"name": "post", "place": "middle", "factor": 0.5, "shapes": [{"shape": "rect", "x": 0.5, "y": 0.2, "width": 0.05, "height": 0.5}]},
        {"name": "bush", "place": "foreground", "shapes": [{"shape": "ellipse", "x": 0.5, "width": 0.4, "height": 0.15, "color": "accent"}]},
    ]
    project = camera_project(make_project, beats, {"layers": layers, "background": ["primary", "surface"]})
    scene, objects = render_with_layout(project, "park", tmp_path / "media")
    named = {obj["name"]: obj for obj in objects if obj["name"]}
    order = [named[n]["order"] for n in ("background", "hills", "post", "ground", "kit", "bush")]
    assert order == sorted(order)   # sky, layers behind, ground band, characters, foreground layer
    fw = scene.frame_width
    frame = scene.camera.frame
    pip = scene.cast["pip"]
    # following pip at the end: the view's centre is pip's x, held inside the stage
    expected = view_center_within(scene.camera_bounds(), (pip.feet()[0], 0.0), frame.width, frame.height)
    assert frame.get_center()[:2] == pytest.approx(expected) and frame.get_center()[0] == pytest.approx(-fw / 2)
    # the middle layer's post was drawn at the stage's centre: it is shown moved by 0.5 x the camera's move
    post, bush = scene.layers["post"], scene.layers["bush"]
    assert post.get_center()[0] - frame.get_center()[0] == pytest.approx(-0.5 * frame.get_center()[0], abs=1e-6)
    assert bush.get_center()[0] - frame.get_center()[0] == pytest.approx(-DEFAULT_FACTORS["foreground"] * frame.get_center()[0], abs=1e-6)
    assert scene.camera_following is not None
