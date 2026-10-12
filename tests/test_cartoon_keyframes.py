"""Step 81: keyframes and motion paths (``keyframes``, ``move_along``): eases, interpolation, key
times and path lengths (no manim), the animation on a character, a prop and a part, the actions,
validate, and one tiny render."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES, acting_project, figure, run, target, use
from test_cartoon_moving import StageFake
from test_cartoon_stage import render_with_layout
from vidgen.cartoon.keyframes import (
    EASES,
    Key,
    KeyFrame,
    MotionPath,
    ease_progress,
    key_seconds,
    key_time_problems,
    keyed_values,
    path_curve,
    path_length,
)
from vidgen.cartoon.transition import KeyedMotion
from vidgen.cli import check_project
from vidgen.project import Project

# ----- eases, keys, paths (no manim) ------------------------------------------------------------------


def test_eases_are_manims_rate_functions() -> None:
    from manim.utils import rate_functions

    for name, ease in EASES.items():
        assert ease(0.0) == pytest.approx(0.0, abs=1e-9) and ease(1.0) == pytest.approx(1.0), name
        if name in ("lively", "calm"):
            continue
        manim_ease = getattr(rate_functions, name)
        assert all(ease(t) == pytest.approx(manim_ease(t), abs=1e-9) for t in np.linspace(0, 1, 21)), name
    assert min(EASES["lively"](t) for t in np.linspace(0, 0.3, 31)) < 0   # winds up the other way first
    assert max(EASES["lively"](t) for t in np.linspace(0.7, 1, 31)) > 1   # passes the end, settles
    assert ease_progress("linear", 1.5) == 1.0 and ease_progress("linear", -1) == 0.0


def test_interpolation_values() -> None:
    keys = [Key(1.0, {"x": 2.0}, "linear"), Key(2.0, {"x": 4.0, "rotate": 90.0}, "linear"), Key(3.0, {"scale": 2.0}, "ease_in_quad")]
    start = {"x": 0.0, "rotate": 0.0, "scale": 1.0}
    assert keyed_values(start, keys, 0.0) == start
    assert keyed_values(start, keys, 0.5) == pytest.approx({"x": 1.0, "rotate": 22.5, "scale": 1.0 + (0.5 / 3) ** 2})
    assert keyed_values(start, keys, 1.5) == pytest.approx({"x": 3.0, "rotate": 67.5, "scale": 1.0 + 0.25})
    assert keyed_values(start, keys, 2.0)["x"] == 4.0 and keyed_values(start, keys, 9.0) == {"x": 4.0, "rotate": 90.0, "scale": 2.0}   # held
    jump = [Key(0.0, {"y": 1.0}), Key(2.0, {"y": 3.0}, "smooth")]
    assert keyed_values({"y": 0.0}, jump, 0.0) == {"y": 1.0}   # a key at 0 s: at once
    assert keyed_values({"y": 0.0}, jump, 1.0) == pytest.approx({"y": 2.0})   # smooth is symmetric
    assert keyed_values({"y": 0.0}, jump, 0.5)["y"] < 1.5   # eases in


def test_key_times_order_and_ranges() -> None:
    assert key_seconds(1.5, 4.0) == 1.5 and key_seconds("25%", 4.0) == 1.0
    assert key_time_problems([0, 0.5, 2]) == [] and key_time_problems(["0%", "50%", "100%"]) == []
    assert key_time_problems([]) == [(None, "give at least one key")]
    assert key_time_problems([0.5, "50%"])[0][1].startswith("give every key's t in seconds")
    assert [k for k, _ in key_time_problems([1.0, 0.5, 0.5, 2.0])] == [1, 2]
    assert "past the end of the beat" in key_time_problems(["50%", "120%"])[0][1]
    assert KeyFrame(t="40%", x="door").values() == {"x": "door"}
    for bad in ({"t": 1}, {"t": -1, "x": 0.5}, {"t": "40", "x": 0.5}, {"t": 1, "scale": 0}, {"t": 1, "x": 0.5, "ease": "wobbly"}, {"t": 1, "z": 2}):
        with pytest.raises(ValidationError):
            KeyFrame(**bad)


def test_path_lengths() -> None:
    assert path_length([(0, 0), (3, 4)]) == pytest.approx(5.0)
    assert path_length([(0, 0), (1, 0), (1, 1)], smooth=False) == pytest.approx(2.0)
    assert path_length([(0, 0), (1, 0), (2, 0), (4, 0)]) == pytest.approx(4.0)   # points in a line: a line
    corner = [(0, 0), (1, 0), (1, 1)]
    smooth = path_curve(corner)
    assert all(p in smooth for p in [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])   # through every point
    assert math.dist((0, 0), (1, 1)) < path_length(corner) < 2.0 + 0.2   # round the corner, near the polyline
    half = MotionPath(((0.0, 0.0), (1.0, 0.0), (1.0, 3.0)), smooth=False)
    assert half.length == 4.0 and half.at(0.5) == pytest.approx((1.0, 1.0)) and half.at(2.0) == (1.0, 3.0)   # even speed
    assert MotionPath(((2.0, 1.0),)).at(0.7) == (2.0, 1.0)


# ----- the animation and the actions (no render) ---------------------------------------------------------


class KeyFake(StageFake):
    """StageFake with a frame height, ground lines and a beat 4 s long."""

    frame_height = 9.0

    def __init__(self, **mobs: Any) -> None:
        super().__init__(**mobs)
        self.grounds = {name: -2.0 for name in mobs}

    def beat_duration(self, beat: Any) -> float:
        return 4.0


def play_to(anim: KeyedMotion, share: float) -> None:
    anim.begin()
    anim.interpolate(share)


def test_keyed_motion_moves_turns_and_sizes_about_the_feet() -> None:
    from manim import Square

    pip = figure().shift([-4.0, -2.0, 0.0])
    height = pip.character_height
    anim = KeyedMotion(pip, lambda s: {"x": -4.0 + 4.0 * s, "rotate": 90.0 * s, "scale": 1.0 + s})
    play_to(anim, 0.5)
    assert pip.feet() == pytest.approx([-2.0, -2.0, 0.0]) and pip.keyed_rotate == 45.0
    anim.interpolate(1.0)
    anim.finish()
    assert pip.feet() == pytest.approx([0.0, -2.0, 0.0]) and pip.character_height == pytest.approx(2 * height)
    head = pip.parts["head"].get_center()
    assert head[0] < -1.0 and abs(head[1] + 2.0) < 1.0   # turned 90° counterclockwise: the head is to the left
    back = KeyedMotion(pip, lambda s: {"rotate": 90.0 * (1 - s), "scale": 2.0 - s})
    run([back])
    assert pip.character_height == pytest.approx(height) and pip.parts["head"].get_center()[1] > -1.0

    box = Square(1.0).move_to([3.0, 0.5, 0.0])
    run([KeyedMotion(box, lambda s: {"y": 0.0 + 2.0 * s, "rotate": 45.0 * s})])
    assert box.keyed_feet == pytest.approx((3.0, 2.0, 0.0)) and box.get_center() == pytest.approx([3.0 - 0.5 * math.sin(math.pi / 4), 2.0 + 0.5 * math.cos(math.pi / 4), 0.0])   # turned about its feet


def test_keyed_motion_poses_a_part() -> None:
    kit = figure("kit")
    kit.set_expression("sad")   # a mouth flipped upside down
    body = kit.pose_of("body")
    run([KeyedMotion(kit, lambda s: {"rotate": 80.0 * s, "y": 0.05 * s}, part="arm_left")])
    assert kit.pose_of("arm_left").angle == 80.0 and kit.pose_of("arm_left").shift == pytest.approx((0.0, 0.05))
    assert kit.pose_of("body") == body   # the other parts stay
    flipped = kit.pose_of("mouth").scale
    run([KeyedMotion(kit, lambda s: {"scale": 1.0 + s}, part="mouth")])
    assert np.sign(kit.pose_of("mouth").scale) == pytest.approx(np.sign(flipped)) and abs(kit.pose_of("mouth").scale[0]) == 2.0
    with pytest.raises(TypeError):
        KeyedMotion(kit.parts["head"], lambda s: {}, part="head")


def test_keyframes_action_on_a_character_a_part_and_back() -> None:
    pip = figure().shift([-4.0, -2.0, 0.0])
    scene = KeyFake(pip=pip)
    keys = use("keyframes", keys=[{"t": "25%", "x": 0.5, "y": 0.5, "ease": "linear"}, {"t": 2, "rotate": 30}])
    assert keys.run_time_for(scene, [target("pip", pip)]) == 2.0   # the last key
    (anim,) = keys.apply(scene, [target("pip", pip)])
    play_to(anim, 0.25)   # 0.5 s: half way to the first key (1 s), linear
    assert pip.feet() == pytest.approx([-2.0, -2.0 + 0.25 * 9.0, 0.0])
    anim.interpolate(1.0)
    anim.finish()
    assert pip.feet() == pytest.approx([0.0, 2.5, 0.0]) and pip.keyed_rotate == 30.0   # 0.5 of 9 above the ground line
    run(keys.revert(scene, [target("pip", pip)]))
    assert pip.feet() == pytest.approx([-4.0, -2.0, 0.0]) and pip.keyed_rotate == 0.0

    arm = use("keyframes", "pip.arm_left", keys=[{"t": 0.5, "rotate": 120}, {"t": 1.0, "rotate": 60, "x": 0.02}])
    (anim,) = arm.apply(scene, [target("pip.arm_left", pip.parts["arm_left"])])
    assert anim.mobject is pip and anim.part == "arm_left"
    run([anim])
    assert pip.pose_of("arm_left").angle == 60.0 and pip.pose_of("arm_left").shift[0] == 0.02 and pip.feet() == pytest.approx([-4.0, -2.0, 0.0])


def test_move_along_action() -> None:
    pip = figure().shift([-4.0, -2.0, 0.0])
    scene = KeyFake(pip=pip)
    hop = use("move_along", path=[[0.25, 0.4], [0.5, 0.0]], curve="straight", ease="linear", speed=2.0)
    # from x -4 to -4 (0.25 of -8..8) up 3.6, then to x 0 down 3.6
    length = 3.6 + math.hypot(4.0, 3.6)
    assert hop.run_time_for(scene, [target("pip", pip)]) == pytest.approx(length / 2.0)
    (anim,) = hop.apply(scene, [target("pip", pip)])
    play_to(anim, 3.6 / length)
    assert pip.feet() == pytest.approx([-4.0, 1.6, 0.0])   # at the top of the first leg
    anim.interpolate(1.0)
    anim.finish()
    assert pip.feet() == pytest.approx([0.0, -2.0, 0.0])
    assert use("move_along", path=[[0.5, 0]]).run_time_for(scene, []) is None   # no speed: run_time
    run(hop.revert(scene, [target("pip", pip)]))
    assert pip.feet() == pytest.approx([-4.0, -2.0, 0.0])
    head = use("move_along", "pip.head", path=[[0.03, 0.0], [0.0, 0.0]], speed=1.0)
    assert head.run_time_for(scene, [target("pip.head", pip.parts["head"])]) == pytest.approx(0.06 * pip.character_height, rel=0.02)


# ----- validate -----------------------------------------------------------------------------------------


def test_validate_keyframes_and_paths(make_project) -> None:
    good = acting_project(make_project, [
        {"text": "Pip floats up and waves.", "actions": [
            {"keyframes": "pip", "keys": [{"t": 0, "y": 0.1}, {"t": 1.5, "x": "centre", "rotate": 10, "ease": "ease_out_back"}]},
            {"keyframes": "kit.arm_left", "keys": [{"t": "20%", "rotate": 140}, {"t": "60%", "rotate": 100}], "ease": "lively"},
            {"move_along": "tree", "path": [[0.6, 0.0], ["right", 0.1]], "until": "b2"}]},
        {"id": "b2", "text": "And back.", "actions": [{"move_along": "kit.head", "path": [[0.02, 0.01]], "speed": 2}, {"emote": "k*", "to": "happy"}]},
    ])
    assert check_project(good) == []
    bad = acting_project(make_project, [{"text": "Hello.", "actions": [
        {"keyframes": "pip", "keys": [{"t": 1, "x": 0.5}, {"t": 0.5, "x": 0.2}]},
        {"keyframes": "pip", "keys": [{"t": 1, "x": 0.5}, {"t": "50%", "x": 0.2}]},
        {"keyframes": "kit.arm_left", "keys": [{"t": 1, "x": "door"}]},
        {"keyframes": "pip", "keys": [{"t": 1, "x": "nowhere", "y": 1.5}]},
        {"move_along": "kit.tail", "path": [[0.1, 0.1]]},
        {"move_along": "kit.head", "path": [[1.5, 0.0]]},
        {"emote": "kit.mouth", "to": "happy"},
        {"keyframes": "pip", "keys": [{"t": "50%", "x": 0.5}, {"t": "150%", "x": 0.2}]},
    ]}])
    problems = check_project(bad)
    where = "scenes[0].beats[0].actions"
    expected = [
        f"{where}[0].keys[1].t: t 0.5 is not after the key before (1.0)",
        f"{where}[1].keys: give every key's t in seconds",
        f"{where}[2].keys[0]: kit.arm_left: a part's x is its shift right",
        f"{where}[3].keys[0]: pip: x: unknown mark 'nowhere'",
        f"{where}[3].keys[0]: pip: y is the feet's height",
        f"{where}[4].target: unknown target 'kit.tail'",
        f"{where}[5].path[0]: kit.head: a part's x shift is at most 1.0",
        f"{where}[6].target: 'kit.mouth' is a character's part; emote acts on whole characters",
        f"{where}[7].keys[1].t: t 150% is past the end of the beat",
    ]
    for start in expected:
        assert any(p.startswith(start) for p in problems), (start, problems)
    other = Project.load(make_project(minimal_config(scenes=[{"id": "t", "type": "title", "params": {"title": "Hi"}, "beats": [
        {"text": "Hello.", "actions": [{"keyframes": "title", "keys": [{"t": 1, "rotate": 10}]}]}]}])))
    assert any("keyframes moves the characters, props and character parts of a stage" in p for p in check_project(other))


def test_stage_names_the_parts_as_targets(make_project, monkeypatch) -> None:
    from vidgen import extensions, registry, runtime

    project = acting_project(make_project, [{"text": "Hi."}])
    extensions.load_builtins()
    cls = registry.get("stage").cls
    params = cls.validate_params(project.config.scenes[0].params)
    with runtime.use_context(project):
        names = cls.target_names(params)
        monkeypatch.setattr(runtime, "_project", None)
        assert cls.target_names(params) == ["pip", "kit", "tree"]   # no active project: no parts
    assert names[:3] == ["pip", "kit", "tree"] and "pip.arm_left" in names and "kit.mouth" in names and "pip.accessory" not in names


# ----- render ---------------------------------------------------------------------------------------------


@pytest.mark.render
def test_keyframes_on_a_stage(make_project, tmp_path: Path) -> None:
    """pip floats up and back down along a path; kit raises its arm by keys; the tree tilts."""
    params = {"idle": False, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}], "props": ["tree"]}
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": [
        {"text": "Pip floats over to the middle while Kit raises an arm.", "actions": [
            {"move_along": "pip", "path": [[0.35, 0.2], [0.5, 0.0]], "run_time": 1.0},
            {"keyframes": "kit.arm_left", "keys": [{"t": 0.4, "rotate": 150}, {"t": 0.8, "rotate": 120}]},
            {"keyframes": "tree", "keys": [{"t": 0.6, "rotate": 8, "ease": "ease_out_back"}]}]},
    ]}]
    project = Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))
    scene, _ = render_with_layout(project, "park", tmp_path / "media")
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    assert pip.feet()[0] == pytest.approx(0.0, abs=1e-6) and pip.feet()[1] == pytest.approx(scene.grounds["pip"])
    assert kit.pose_of("arm_left").angle == pytest.approx(120.0) and scene.props["tree"].keyed_rotate == 8.0
    assert sum("KeyedMotion" in p.animations for p in scene.play_log) >= 1
