"""Step 92: arms and legs in two segments, the two-bone solver (reach / plant), folded one-piece
limbs, and the poses, gestures and walk that bend them."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from conftest import minimal_config
from vidgen.cartoon.acting import WALK_KNEE_DEGREES, walk_cycle
from vidgen.cartoon.cast import character_pose_warnings
from vidgen.cartoon.character import Character, CharacterState, PartPose, build_character
from vidgen.cartoon.limbs import FOLD_MIN_LENGTH, LIMBS, fold, solve_two_bone, wrap_degrees
from vidgen.cartoon.poses import POSES
from vidgen.cartoon.svg_look import split_character_svg, svg_character_parts
from vidgen.cartoon.transition import Walk, part_windows, walking_state
from vidgen.config import CharacterEntry, parse_config
from vidgen.errors import VidgenError
from vidgen.theme import Theme

EXAMPLE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "svg_character"


def generated(**look) -> Character:
    return build_character(CharacterEntry(name="pip", look=look), theme=Theme(), height=2.0).stop_idle()


def sprout() -> Character:
    return build_character(CharacterEntry(name="sprout", look={"svg": "assets/sprout.svg"}), theme=Theme(), root=EXAMPLE_ROOT).stop_idle()


def end_of(root: tuple[float, float], solution, upper: float, lower: float) -> np.ndarray:
    a = math.radians(solution.direction)
    b = math.radians(solution.direction + solution.bend)
    return np.array(root) + upper * np.array([math.cos(a), math.sin(a)]) + lower * np.array([math.cos(b), math.sin(b)])


# ----- the solver (no manim) ---------------------------------------------------------------------


@pytest.mark.parametrize("target", [(1.2, 0.3), (-0.5, 0.9), (0.2, -1.4), (0.3, 0.1)])
def test_two_bone_reaches_points_in_range(target: tuple[float, float]) -> None:
    for bend in (1.0, -1.0):
        solution = solve_two_bone((0.0, 0.0), target, 1.0, 0.8, bend)
        assert solution.reached and np.allclose(end_of((0.0, 0.0), solution, 1.0, 0.8), target)
        assert math.copysign(1.0, solution.bend) == bend


def test_two_bone_out_of_reach_points_straight_or_folds() -> None:
    far = solve_two_bone((1.0, 1.0), (5.0, 1.0), 1.0, 1.0)
    assert not far.reached and far.direction == pytest.approx(0.0) and far.bend == pytest.approx(0.0)   # straight at it
    near = solve_two_bone((0.0, 0.0), (0.0, 0.1), 1.0, 0.5)   # nearer than 1 - 0.5
    assert not near.reached and np.allclose(end_of((0.0, 0.0), near, 1.0, 0.5), (0.0, 0.5))   # folded, towards it
    assert solve_two_bone((0.0, 0.0), (0.0, 0.0), 1.0, 1.0).bend == pytest.approx(180.0)
    with pytest.raises(ValueError):
        solve_two_bone((0.0, 0.0), (1.0, 0.0), 0.0, 1.0)


def test_elbow_and_knee_sides() -> None:
    # an arm hanging from the shoulder reaching forward: the natural elbow (+1) sits below the line to the hand
    elbow = solve_two_bone((0.0, 0.0), (1.2, 0.0), 1.0, 1.0, 1.0)
    assert math.sin(math.radians(elbow.direction)) < 0
    # a leg whose foot is pulled up below the hip: the natural knee (-1) comes forward (+x)
    knee = solve_two_bone((0.0, 0.0), (0.0, -1.2), 1.0, 1.0, -1.0)
    assert math.cos(math.radians(knee.direction)) > 0


def test_fold_and_wrap() -> None:
    assert fold(0.0) == (0.0, 1.0)
    turn, length = fold(60.0)
    assert turn == 30.0 and length == pytest.approx(math.cos(math.radians(30)))
    assert fold(170.0)[1] == FOLD_MIN_LENGTH   # never squashed flat
    assert [wrap_degrees(a) for a in (190.0, -190.0, 180.0, -180.0, 30.0)] == pytest.approx([-170.0, 170.0, 180.0, 180.0, 30.0])


def test_lower_segments_share_their_limbs_time_window() -> None:
    windows = part_windows(["body", "leg_left", "leg_left_lower", "leg_right", "arm_left", "arm_left_lower", "head"], 0.5)
    assert windows["arm_left_lower"] == windows["arm_left"] and windows["leg_right"] == windows["leg_left"] == windows["leg_left_lower"]
    one_piece = part_windows(["body", "legs", "arm_left", "head"], 0.5)   # timing as with one-piece limbs
    assert all(windows[part] == one_piece[part] for part in ("body", "arm_left", "head")) and windows["leg_left"] == one_piece["legs"]


# ----- reach and plant on characters -------------------------------------------------------------


def test_reach_puts_the_hand_on_the_point_with_a_natural_elbow() -> None:
    for facing in ("right", "left"):
        c = generated().face(facing).shift([1.0, -2.0, 0.0])
        sign = 1.0 if facing == "right" else -1.0
        shoulder = c.pivot("arm_left")
        target = shoulder + np.array([sign * 0.35, 0.2, 0.0])
        c.reach("left", target)
        assert np.allclose(c.hand_point("left"), target, atol=1e-6)
        elbow = c.pivot("arm_left_lower")
        assert elbow[1] < shoulder[1] + 0.2 * (elbow[0] - shoulder[0]) / (sign * 0.35)   # below the shoulder-hand line
        behind = c.pivot("arm_right") + np.array([-sign * 0.2, -0.25, 0.0])
        c.reach("right", behind, bend=-1.0)
        assert np.allclose(c.hand_point("right"), behind, atol=1e-6)


def test_reach_out_of_range_points_at_it() -> None:
    c = generated()
    shoulder = c.pivot("arm_left")
    far = shoulder + np.array([3.0, 3.0, 0.0])
    c.reach("left", far)
    hand = c.hand_point("left") - shoulder
    assert hand[0] == pytest.approx(hand[1], rel=1e-3) and np.linalg.norm(hand) < 1.0   # straight towards it, not there


def test_plant_puts_the_sole_on_the_point_knee_forward() -> None:
    c = generated()
    assert c.foot_point("left")[1] == pytest.approx(0.0) and c.sole_height() == pytest.approx(0.0)
    hip = c.pivot("leg_left")
    step = np.array([c.foot_point("left")[0] + 0.1, 0.15, 0.0])   # up on a step
    c.plant("left", step)
    assert np.allclose(c.foot_point("left"), step, atol=1e-6)
    assert c.pivot("leg_left_lower")[0] > (hip[0] + step[0]) / 2   # the knee forward
    with pytest.raises(VidgenError, match="right foot"):
        sprout().plant("right", step)   # sprout's legs are one part
    with pytest.raises(VidgenError, match="hand must be left or right"):
        c.reach("middle", step)


def test_a_one_piece_arm_folds_and_reaches() -> None:
    c = sprout()
    assert not c.has_part("arm_left_lower") and c.pose_of("arm_left_lower") == PartPose()
    assert "arm_left_lower" in c.state().parts and "leg_left_lower" not in c.state().parts
    rest = c.hand_point("left").copy()
    c.set_part("arm_left_lower", angle=60.0)
    shoulder = c.pivot("arm_left")
    folded = c.hand_point("left") - shoulder
    expected = np.linalg.norm(rest - shoulder) * math.cos(math.radians(30))
    assert np.linalg.norm(folded) == pytest.approx(expected, rel=1e-6)   # shortened to the chord
    c.reset()
    target = shoulder + 0.8 * (rest - shoulder) @ np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])   # 90° round, nearer
    c.reach("left", target)
    assert np.allclose(c.hand_point("left"), target, atol=1e-6)
    with pytest.raises(VidgenError, match="no shape"):
        c.set_part("arm_left_lower", shape="rest")


# ----- poses, gestures and the walk ------------------------------------------------------------------


@pytest.mark.parametrize("pose", list(POSES))
def test_poses_bend_two_segment_limbs_and_fold_one_piece_ones(pose: str) -> None:
    entry = POSES[pose]
    two = generated().set_pose(pose)
    for part in LIMBS.values():
        expected = entry[part].angle if part in entry else 0.0
        assert two.pose_of(part).angle == expected
    one = sprout().set_pose(pose)   # one-piece arms: the forearm's bend is kept and shown folded
    for arm in ("arm_left", "arm_right"):
        lower = f"{arm}_lower"
        assert one.pose_of(lower).angle == (entry[lower].angle if lower in entry else 0.0)
        if lower in entry:   # the hand points as a one-piece arm did before Step 92 (up to 3° in arms_crossed: 10°)
            folded = entry[arm].angle + entry[lower].angle / 2
            old = {"pointing": 88, "waving": 150, "thinking": 160, "shrug": 45, "arms_crossed": -65}[pose]
            assert abs(abs(folded) - abs(old)) <= 10


def test_sitting_uses_the_legs_the_character_has() -> None:
    one = sprout().set_pose("sitting")
    assert one.pose_of("legs").angle == 80
    two = generated().set_pose("sitting")
    assert two.pose_of("leg_left").angle == 80 and two.pose_of("leg_left_lower").angle < 0   # the knees bent
    assert abs(two.sole_height()) < 0.02   # the feet near the ground


def test_walk_cycle_bends_the_knee_of_the_swinging_leg() -> None:
    passing = walk_cycle(0.0)   # the left leg swings forward past the right one
    assert passing.knee_bends == (pytest.approx(WALK_KNEE_DEGREES), 0.0) and passing.thigh_angle == 0.0
    footfall = walk_cycle(0.5)   # legs apart, both knees straight
    assert footfall.knee_bends == pytest.approx((0.0, 0.0)) and footfall.thigh_angle > 0
    assert walk_cycle(1.0).knee_bends == (0.0, pytest.approx(WALK_KNEE_DEGREES))   # the other leg next
    assert walk_cycle(0.5).elbow_bends[0] > walk_cycle(1.5).elbow_bends[0] > 0   # the elbow bends more swinging forward
    assert walk_cycle(0.3, amplitude=0.0).knee_bends == (0.0, 0.0)
    c = generated()
    state = walking_state(c.state(), passing, "right")
    assert state.parts["leg_left_lower"].angle == pytest.approx(-WALK_KNEE_DEGREES)   # the foot goes back
    assert "legs" not in state.parts and state.parts["body"].shift == (0.0, 0.0)   # no fixed bob: the walk grounds it


def test_the_walk_keeps_a_sole_on_the_ground_and_ends_in_the_pose() -> None:
    c = generated()
    c.motion = "none"
    before = c.state()
    walk = Walk(c, 3.0)
    walk.begin()
    soles, lifts = [], []
    for k in range(41):
        walk.interpolate(k / 40)
        soles.append(min(c.foot_point("left")[1], c.foot_point("right")[1]))
        lifts.append(c.pose_of("body").shift[1])
    walk.finish()
    assert soles == pytest.approx([0.0] * 41, abs=1e-9)
    assert min(lifts) < -0.001   # the body dips as the legs spread
    assert c.state() == CharacterState("right", before.parts)


# ----- imported SVGs with two-segment limbs ----------------------------------------------------------

SEGMENTED = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 200">
  <rect id="body" x="30" y="60" width="40" height="70"/>
  <g id="leg_left" data-pivot="60 125"><rect x="56" y="125" width="8" height="35"/></g>
  <g id="leg_left_lower" data-pivot="60 160"><rect x="56" y="160" width="8" height="40"/></g>
  <g id="leg_right"><rect x="36" y="125" width="8" height="75"/></g>
  <g id="arm_left" data-pivot="70 65"><rect x="66" y="65" width="8" height="30"/></g>
  <g id="arm_left_lower"><rect x="66" y="95" width="8" height="30"/></g>
  <circle id="head" cx="50" cy="35" r="25"/>
</svg>"""


def test_svg_lower_segments_by_id(tmp_path: Path) -> None:
    split = split_character_svg(SEGMENTED, where="seg.svg")
    assert list(split.part_shapes()) == ["body", "leg_left", "leg_left_lower", "leg_right", "arm_left", "arm_left_lower", "head"]
    assert split.pivots["leg_left_lower"] == (60, 160)
    path = tmp_path / "seg.svg"
    path.write_bytes(SEGMENTED)
    parts = {p.name: p for p in svg_character_parts(path, where="seg.svg")}
    assert parts["arm_left_lower"].parent == "arm_left" and parts["leg_left_lower"].parent == "leg_left"
    assert parts["arm_left_lower"].pivot[1] == pytest.approx(parts["arm_left"].pivot[1] - 30 / 200, abs=0.01)   # guessed: top centre
    c = Character(parts.values(), name="seg", required=("body",))
    # the left leg in two segments, the right in one (folded): both can be planted
    for foot in ("left", "right"):
        point = c.foot_point(foot) + np.array([0.15, 0.3, 0.0])
        c.plant(foot, point)
        assert np.allclose(c.foot_point(foot), point, atol=1e-6)
    with pytest.raises(VidgenError, match="'legs' and leg_left"):
        split_character_svg(SEGMENTED.replace(b'<rect id="body"', b'<rect id="legs" x="0" y="0" width="1" height="1"/><rect id="body"'), where="seg.svg")


def test_validate_does_not_warn_about_a_folded_forearm(tmp_path: Path) -> None:
    config = parse_config({
        **minimal_config(),
        "characters": [
            {"name": "sprout", "look": {"svg": "assets/sprout.svg"}, "poses": {"reach": {"arm_left": {"angle": 40}, "arm_left_lower": {"angle": 50}, "leg_left": {"angle": 10}}}},
            {"name": "pip", "poses": {"old": {"legs": {"angle": 10}}}},
        ],
    })
    warnings = character_pose_warnings(config, EXAMPLE_ROOT)
    assert warnings == [
        "characters[0].poses.reach.leg_left: character 'sprout' has no leg_left; this setting does nothing",
        "characters[1].poses.old.legs: character 'pip' has no legs; this setting does nothing",
    ]
