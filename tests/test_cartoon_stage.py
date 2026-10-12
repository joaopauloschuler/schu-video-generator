"""Step 73: the ``stage`` scene type (background, ground line, marks, depth, characters)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from vidgen import extensions, registry
from vidgen.cartoon.stage import (
    FAR_RISE,
    FAR_SCALE,
    MARKS,
    StageItem,
    depth_scale,
    draw_order,
    facing_towards_centre,
    feet_point,
    mark_x,
    stage_layout,
)
from vidgen.cli import check_project
from vidgen.imagegen import scene_images
from vidgen.lint.layout_rules import describe
from vidgen.project import Project

CAST = [{"name": "pip", "look": {"body": "bean"}}, {"name": "kit", "look": {"body": "tall"}, "poses": {"bow": {"body": {"angle": -15}}}}]


def stage_params(**params: Any) -> Any:
    extensions.load_builtins()
    return registry.get("stage").cls.validate_params(params)


def stage_project(make_project, params: dict[str, Any], **config: Any) -> Project:
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": [{"text": "Two friends meet."}]}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes, **config)))


# ----- geometry (no manim) ----------------------------------------------------------------------


def test_marks_and_x_positions() -> None:
    assert [mark_x(name) for name in ("far_left", "left", "centre", "right", "far_right")] == list(MARKS.values())
    assert mark_x(0.3) == 0.3 and mark_x(1) == 1.0
    assert mark_x("door", {"door": 0.85}) == 0.85 and mark_x("left", {"left": 0.2}) == 0.2   # own marks win
    with pytest.raises(ValueError, match="unknown mark 'centr'; did you mean 'centre'"):
        mark_x("centr")
    with pytest.raises(ValueError, match="outside the frame"):
        mark_x(1.2)


def test_depth_scales_and_raises() -> None:
    assert depth_scale(0) == 1.0 and depth_scale(1) == FAR_SCALE and depth_scale(0.5) == pytest.approx((1 + FAR_SCALE) / 2)
    assert feet_point(0.5, 0.0, 0.2, 16.0, 8.0) == pytest.approx((0.0, -2.4))   # 0.2 of 8 above the bottom edge (-4)
    assert feet_point(0.25, 1.0, 0.2, 16.0, 8.0) == pytest.approx((-4.0, -2.4 + FAR_RISE * 8))


def test_draw_order_is_back_to_front_and_stable() -> None:
    assert draw_order([0.0, 0.6, 0.6, 0.2]) == [1, 2, 3, 0]
    assert draw_order([]) == []


def test_stage_layout() -> None:
    items = [StageItem("pip", "character", "left"), StageItem("kit", "character", "right", depth=1.0, scale=0.8)]
    wide = stage_layout(items, ground=0.2, size=0.5, frame_width=14.2, frame_height=8.0)
    assert [p.name for p in wide] == ["kit", "pip"] and [p.index for p in wide] == [1, 0]
    kit, pip = wide
    assert pip.height == pytest.approx(4.0) and kit.height == pytest.approx(4.0 * 0.8 * FAR_SCALE)
    assert pip.feet == pytest.approx(feet_point(0.25, 0.0, 0.2, 14.2, 8.0)) and kit.x_fraction == 0.75
    tall = stage_layout(items, ground=0.2, size=0.5, frame_width=8.0, frame_height=14.2)
    assert tall[1].height == pip.height   # a fraction of the shorter side: the same size in 9:16
    assert facing_towards_centre(0.25) == "right" and facing_towards_centre(0.5) == "right" and facing_towards_centre(0.9) == "left"


# ----- params and validate ------------------------------------------------------------------------


def test_params_shorthand_and_targets() -> None:
    params = stage_params(characters=["pip", {"name": "kit", "at": 0.8, "depth": 0.5, "facing": "left", "pose": "bow"}])
    assert params.characters[0].name == "pip" and params.characters[0].at == "centre"
    assert [i.name for i in params.items()] == ["pip", "kit"] and params.items()[1].at == 0.8
    assert registry.get("stage").cls.target_names(params) == ["pip", "kit"]
    assert not params.has_picture() and stage_params(image="assets/park.png").has_picture()


@pytest.mark.parametrize(
    "params,message",
    [
        ({"characters": ["pip", "pip"]}, "on the stage twice"),
        ({"characters": [{"name": "pip", "at": "middle"}]}, "characters\\[0\\].at: unknown mark 'middle'"),
        ({"characters": [{"name": "pip", "at": "door"}]}, "unknown mark 'door'"),
        ({"characters": [{"name": "pip", "at": 1.5}]}, "outside the frame"),
        ({"characters": [{"name": "pip", "depth": 2}]}, "less than or equal to 1"),
        ({"image": "assets/a.png", "generate": "a park"}, "not both"),
        ({"image": "assets/a.png", "background": "primary"}, "stages without a picture"),
        ({"background": ["primary"]}, "at least two colours"),
        ({"marks": {"bad name": 0.5}}, "pattern"),
        ({"marks": {"door": 1.5}}, "less than or equal to 1"),
        ({"ground": 0.9}, "less than or equal to 0.6"),
    ],
)
def test_bad_params(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        stage_params(**params)


def test_own_marks_and_ground_colour_off() -> None:
    params = stage_params(marks={"door": 0.9}, characters=[{"name": "pip", "at": "door"}], ground_color=False)
    assert params.items()[0].at == "door" and params.ground_color is False


def test_validate_checks_characters_poses_and_files(make_project) -> None:
    good = stage_project(make_project, {"characters": [{"name": "kit", "pose": "bow", "expression": "happy"}, "pip"]})
    assert check_project(good) == []
    bad = stage_project(
        make_project,
        {"image": "assets/park.png", "characters": [{"name": "kit", "pose": "pointng"}, {"name": "pip", "expression": "glad"}]},
    )
    problems = "\n".join(check_project(bad))
    assert "scenes[0].params.image: file not found: assets/park.png" in problems
    assert "characters[0].pose: character 'kit': unknown pose 'pointng'; did you mean 'pointing'?" in problems
    assert "bow" in problems   # kit's own pose is listed
    assert "characters[1].expression: character 'pip': unknown expression 'glad'" in problems
    unknown = stage_project(make_project, {"characters": ["pip", "rex"]}, )
    assert check_project(unknown) == ["scenes[0].params.characters[1].name: unknown character 'rex' characters: pip, kit"]


def test_imagegen_finds_a_stage_background(make_project) -> None:
    project = stage_project(make_project, {"generate": "a sunny park, an empty lawn in the middle", "characters": ["pip"]})
    (found,) = scene_images(project)
    assert found.scene_id == "park" and found.field == "generate" and found.request.prompt.startswith("a sunny park")


def test_lint_names_characters() -> None:
    obj = {"kind": "character", "class": "Character", "name": "pip", "path": "pip"}
    assert describe(obj) == "character 'pip'"


# ----- render ------------------------------------------------------------------------------------


def render_with_layout(project: Project, scene_id: str, media: Path) -> tuple[Any, list[dict[str, Any]]]:
    """Render one scene at 160x90 with a layout recorder; returns the scene and its first still's objects."""
    from manim import tempconfig

    from vidgen.capture import FrameCapture
    from vidgen.introspect import LayoutRecorder
    from vidgen.render.worker import frame_size

    fw, fh = frame_size(160, 90)
    settings = {"pixel_width": 160, "pixel_height": 90, "frame_width": fw, "frame_height": fh, "frame_rate": 5,
                "media_dir": str(media), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}
    recorder = LayoutRecorder()
    with tempconfig(settings):
        spec = project.scene(scene_id)
        theme = extensions.activate(project)
        scene = registry.get(spec.type).cls(spec, project, theme, capture=FrameCapture(1, [recorder]))
        scene.render()
    return scene, recorder.frames[0]["objects"]


@pytest.mark.render
def test_stage_renders_with_a_picture(make_project, tmp_path: Path) -> None:
    from PIL import Image

    params = {
        "image": "assets/park.png",
        "idle": False,
        "ground": 0.25,
        "characters": [{"name": "pip", "at": "left", "pose": "waving", "expression": "happy"}, {"name": "kit", "at": "right", "depth": 0.8}],
    }
    project = stage_project(make_project, params)
    (project.root / "assets").mkdir()
    Image.new("RGB", (64, 48), (90, 160, 90)).save(project.root / "assets" / "park.png")
    scene, objects = render_with_layout(project, "park", tmp_path / "media")
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    assert list(scene.cast) == ["kit", "pip"]   # back to front
    assert not pip.is_idle and pip.facing == "right" and kit.facing == "left"
    assert pip.pose_of("arm_left").angle != 0
    fw, fh = scene.frame_width, scene.frame_height
    assert pip.feet()[:2] == pytest.approx(feet_point(0.25, 0.0, 0.25, fw, fh), abs=1e-6)
    assert np.isclose(pip.feet()[1], -fh / 2 + 0.25 * fh) and kit.height < pip.height
    named = {obj["name"]: obj for obj in objects if obj["name"]}
    assert [named[n]["kind"] for n in ("background", "kit", "pip")] == ["image", "character", "character"]
    assert "ground" not in named   # no ground band on a picture
    assert named["background"]["order"] < named["kit"]["order"] < named["pip"]["order"]   # kit is drawn behind pip
    x0, y0, x1, y1 = named["background"]["bbox"]   # a 4:3 picture covers the 16:9 frame, cropped at the top and bottom
    assert (x0, x1) == (0.0, 160.0) and y0 == -y1 + 90 < 0
