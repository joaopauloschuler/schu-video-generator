"""Step 70: named poses and expressions, the characters' own ones, and eased part-by-part changes."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from conftest import minimal_config, write_files
from vidgen import cli
from vidgen.cartoon.cast import GENERATED_SHAPES, character_part_shapes, pose_lines
from vidgen.cartoon.character import Character, CharacterState, PartPose, build_character
from vidgen.cartoon.poses import EXPRESSION_PARTS, EXPRESSIONS, POSE_PARTS, POSES, chosen_shape, find_entry
from vidgen.cartoon.transition import PoseChange, blend_poses, part_windows
from vidgen.cli import project_problems, validate_warnings
from vidgen.config import CharacterEntry, PartPoseEntry, parse_config
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.theme import Theme

EXAMPLE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "svg_character"
LOOKS = {
    "default": {},
    "dressed": {"body": "bean", "hair": "long", "eyes": "round", "nose": "triangle", "accessories": ["hat", "glasses", "scarf"]},
    "svg": {"svg": "assets/sprout.svg"},
}


def built(look: str, **entry) -> Character:
    return build_character(CharacterEntry(name="pip", look=LOOKS[look], **entry), theme=Theme(), root=EXAMPLE_ROOT)


def expected_pose(c: Character, part: str, setting: PartPoseEntry | None) -> PartPose:
    if setting is None:
        return PartPose()
    return PartPose(setting.angle, setting.scale_xy(), tuple(setting.shift), chosen_shape(setting, c.shape_names(part)))


# ----- the tables ---------------------------------------------------------------------------


def test_the_tables_name_the_step_70_entries() -> None:
    assert list(POSES) == ["stand", "pointing", "waving", "thinking", "shrug", "arms_crossed", "sitting"]
    assert list(EXPRESSIONS) == [
        "neutral", "happy", "sad", "angry", "surprised", "worried", "thinking",
        "laughing", "blushing", "tongue_out", "crying", "dizzy", "frightened",   # Step 125
    ]
    assert all(set(parts) <= set(POSE_PARTS) for parts in POSES.values())
    assert all(set(parts) <= set(EXPRESSION_PARTS) for parts in EXPRESSIONS.values())


@pytest.mark.parametrize("look", list(LOOKS))
def test_every_pose_and_expression_builds(look: str) -> None:
    c = built(look)
    for kind, table in (("pose", POSES), ("expression", EXPRESSIONS)):
        for name, parts in table.items():
            c.reset()
            if kind == "pose":
                c.set_pose(name)
            else:
                c.set_expression(name)
            group = POSE_PARTS if kind == "pose" else EXPRESSION_PARTS
            for part in group:
                if c.has_part(part):
                    assert c.pose_of(part) == expected_pose(c, part, parts.get(part)), (name, part)
            assert np.isfinite(c.get_all_points()).all()


def test_shape_choices_fall_back_per_character() -> None:
    generated, sprout = built("default"), built("svg")
    assert generated.set_expression("surprised").pose_of("mouth").shape == "open"
    assert sprout.set_expression("surprised").pose_of("mouth").shape == "O"
    assert generated.set_expression("angry").pose_of("brows").shape == "angry"
    angry = sprout.set_expression("angry").pose_of("brows")
    assert angry.shape is None and angry.shift == (0.0, -0.012)   # no brows_angry: only the shift


def test_pose_and_expression_combine_and_reset_their_own_parts() -> None:
    c = built("default").set_pose("pointing").set_expression("happy")
    assert c.pose_of("arm_left").angle == 82 and c.pose_of("arm_left_lower").angle == 12 and c.pose_of("mouth").scale == (1.15, 1.25)
    c.set_pose("stand")
    assert c.pose_of("arm_left") == PartPose() and c.pose_of("mouth").scale == (1.15, 1.25)
    state = c.posed_state(pose="shrug", expression="sad")
    assert state.parts["arm_right"].angle == -15 and state.parts["arm_right_lower"].angle == -60 and state.parts["brows"].shape == "sad"
    assert c.pose_of("arm_right") == PartPose()   # posed_state does not draw


def test_a_pose_moves_the_arm_and_its_hand_along_an_arc() -> None:
    c = built("default")
    hand_before = c.parts["arm_left"].get_bottom()
    c.set_pose("pointing")
    assert c.parts["arm_left"].get_right()[0] > hand_before[0] + 0.3   # the arm points forward
    assert c.parts["head"].get_center()[0] == pytest.approx(built("default").parts["head"].get_center()[0], abs=0.05)


def test_unknown_names_list_the_known_ones() -> None:
    with pytest.raises(VidgenError, match=r"character 'pip': unknown pose 'pointng'; did you mean 'pointing'\? poses: stand, pointing"):
        built("default").set_pose("pointng")
    with pytest.raises(VidgenError, match="unknown expression 'glad'.* expressions: neutral, happy"):
        find_entry("expression", "glad")


def test_generated_shape_table_matches_the_generator() -> None:
    for look, entry_look in (("default", {}), ("dressed", LOOKS["dressed"])):
        c = built(look)
        expected = {part: c.shape_names(part) for part in c.parts}
        assert character_part_shapes(CharacterEntry(name="pip", look=entry_look), EXAMPLE_ROOT) == expected
    assert GENERATED_SHAPES["brows"] == ["default", "angry", "sad"]


# ----- the characters' own poses -----------------------------------------------------------


OWN = {
    "poses": {"bow": {"body": {"angle": -20}, "head": {"angle": -10}}, "waving": {"arm_right": {"angle": -150}}},
    "expressions": {"smug": {"mouth": {"shape": ["grin", "smile"], "scale": [1.2, 0.6]}, "brows": {"angle": 10}}},
}


def test_own_poses_add_to_and_replace_the_built_in_ones() -> None:
    c = built("default", **OWN)
    assert c.names("pose")[-1] == "bow" and c.names("pose").count("waving") == 1
    c.set_pose("waving")
    assert c.pose_of("arm_right").angle == -150 and c.pose_of("arm_left") == PartPose()
    c.set_expression("smug")
    assert c.pose_of("mouth") == PartPose(0.0, (1.2, 0.6), (0.0, 0.0), "smile")
    assert pose_lines(CharacterEntry(name="pip", **OWN)) == [
        "  poses: stand, pointing, waving*, thinking, shrug, arms_crossed, sitting, bow*",
        "  expressions: neutral, happy, sad, angry, surprised, worried, thinking, laughing, blushing, tongue_out, crying, dizzy, frightened, smug*",
    ]


def test_own_pose_config_errors() -> None:
    def parse(poses: dict) -> None:
        parse_config(minimal_config(characters=[{"name": "pip", "poses": poses}]))

    with pytest.raises(VidgenError, match=r"poses.oops.mouth.\[key\]: Input should be 'body', 'legs'"):
        parse({"oops": {"mouth": {"angle": 3}}})   # a face part belongs to an expression
    with pytest.raises(VidgenError, match="scale factor of 0"):
        parse({"flat": {"head": {"scale": [1, 0]}}})
    with pytest.raises(VidgenError, match="spin"):
        parse({"twirl": {"head": {"spin": 3}}})


def svg_project(make_project, **entry) -> Project:
    characters = [{"name": "sprout", "look": {"svg": "assets/sprout.svg"}, **entry}, {"name": "pip", **entry}]
    root = make_project(minimal_config(characters=characters))
    (root / "assets").mkdir()
    shutil.copy(EXAMPLE_ROOT / "assets" / "sprout.svg", root / "assets" / "sprout.svg")
    return Project.load(root)


def test_validate_checks_own_pose_shapes_and_parts(make_project) -> None:
    project = svg_project(
        make_project,
        poses={"tip": {"accessory": {"angle": 10}}},
        expressions={"grin": {"mouth": {"shape": "wide"}}, "talk": {"mouth": {"shape": ["A", "open"]}}},
    )
    problems = {p.location: p.message for p in project_problems(project)}
    assert problems == {
        "characters[0].expressions.grin.mouth.shape": "character 'sprout': part 'mouth' has no shape 'wide' (shapes: smile, A, E, O, M)",
        "characters[1].expressions.grin.mouth.shape": "character 'pip': part 'mouth' has no shape 'wide' (shapes: smile, open, A, E, O, U, M, F, L, W, laugh, tongue, wavy)",
    }
    warnings = validate_warnings(project)
    assert "characters[0].poses.tip.accessory: character 'sprout' has no accessory; this setting does nothing" in warnings
    assert "characters[1].poses.tip.accessory: character 'pip' has no accessory; this setting does nothing" in warnings


def test_character_command_lists_poses(make_project, capsys) -> None:
    project = svg_project(make_project, poses={"bow": {"body": {"angle": -20}}})
    assert cli.main(["character", "sprout", str(project.root)]) == 0
    out = capsys.readouterr().out
    assert "poses: stand, pointing, waving, thinking, shrug, arms_crossed, sitting, bow*" in out
    assert "expressions: neutral, happy" in out


# ----- transitions --------------------------------------------------------------------------


def test_blend_and_windows() -> None:
    start, end = PartPose(), PartPose(90.0, (1.0, 0.5), (0.1, 0.0), "open")
    half = blend_poses(start, end, 0.5)
    assert half == PartPose(45.0, (1.0, 0.75), (0.05, 0.0), "open")
    assert blend_poses(start, end, 0.49).shape is None
    assert part_windows([], 0.2) == {}
    windows = part_windows(["body", "head", "mouth"], 0.5)
    assert windows["body"][0] == 0 and windows["mouth"][1] == pytest.approx(1.0)
    assert windows["head"][0] == pytest.approx(0.25) and part_windows(["a", "b"], 0)["b"] == (0.0, 1.0)


def test_pose_change_eases_each_part_along_its_arc() -> None:
    c = built("default", cartoon_motion="none")   # the plain easing (Step 80 adds overshoot)
    pivot = c.pivot("arm_left")
    hand = c.parts["arm_left_lower"].submobjects[0].submobjects[1]   # Step 92: the hand is on the forearm
    upper, lower = (np.linalg.norm(c.pivot("arm_left_lower") - pivot), np.linalg.norm(hand.get_center() - c.pivot("arm_left_lower")))
    change = PoseChange(c, pose="pointing", expression="surprised", run_time=1)
    change.begin()
    assert c.pose_of("arm_left") == PartPose()
    change.interpolate(0.5)
    angle = c.pose_of("arm_left").angle
    assert 0 < angle < 82 and 0 < c.pose_of("arm_left_lower").angle < 12   # the forearm in the arm's window
    # the elbow on its arc about the shoulder, the hand on its arc about the elbow (not the chords)
    assert np.linalg.norm(c.pivot("arm_left_lower") - pivot) == pytest.approx(upper)
    assert np.linalg.norm(hand.get_center() - c.pivot("arm_left_lower")) == pytest.approx(lower)
    assert c.pose_of("head").angle != 0 and c.pose_of("mouth").shape is None   # the head moves before the mouth swaps
    change.interpolate(0.9)
    assert c.pose_of("mouth").shape == "open"
    change.finish()
    assert c.state() == c.posed_state(pose="pointing", expression="surprised")


def test_pose_change_to_a_state_and_facing() -> None:
    c = built("svg")
    target = CharacterState("right", {"arm_right": PartPose(angle=-90.0)})
    change = PoseChange(c, state=target, facing="left")
    change.begin()
    change.interpolate(0.4)
    assert c.facing == "right" and -90 < c.pose_of("arm_right").angle < 0
    change.finish()
    assert c.facing == "left" and c.pose_of("arm_right").angle == -90 and c.pose_of("arm_left") == PartPose()
    with pytest.raises(TypeError, match="not both"):
        PoseChange(c, state=target, pose="stand")


# ----- render -------------------------------------------------------------------------------


EXTENSION = """
from vidgen.api import *


@scene("pose_demo")
class PoseDemo(NarratedScene):
    class Params(SceneParams):
        who: CharacterName

    def construct(self):
        area = self.region("center")
        hero = character(self.params.who, height=area.height * 0.9).move_to(area.center)
        self.add(hero)
        with self.narrate(0) as d:
            self.play(PoseChange(hero, pose="waving", expression="happy"), run_time=min(0.6, d))
            self.shown = hero.state()
        self.finish()
"""


@pytest.mark.render
def test_pose_change_renders(make_project, tmp_path: Path) -> None:
    from test_builtin_scenes import render_scene

    scenes = [{"id": "toon", "type": "pose_demo", "params": {"who": "pip"}, "beats": [{"text": "Hello there."}]}]
    root = make_project(minimal_config(characters=[{"name": "pip"}], scenes=scenes))
    write_files(root, {"extensions/pose_demo.py": EXTENSION})
    scene, duration, _ = render_scene(Project.load(root), "toon", tmp_path / "media", 160, 90)
    assert duration > 0 and scene.shown.parts["arm_left"].angle == POSES["waving"]["arm_left"].angle
