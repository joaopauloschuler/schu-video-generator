"""Step 80: animation principles built in (anticipation, squash and stretch, overshoot and settle,
follow-through) and the ``cartoon_motion`` setting: the curves at fixed times (no manim), each
effect off with ``none``, the animations that apply them, and the nearest setting winning."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_acting import figure, target, use
from test_cartoon_moving import StageFake
from test_cartoon_stage import render_with_layout, stage_params
from vidgen.cartoon.acting import GESTURE_EASE, GESTURES, JUMP_SECONDS, POINT_DEGREES, gesture_moves, gesture_weight, walk_seconds
from vidgen.cartoon.character import Character, build_character, character
from vidgen.cartoon.motion import (
    ANTICIPATION,
    ANTICIPATION_SHARE,
    DEFAULT_MOTION,
    FOLLOW_ARM_LIMIT,
    FOLLOW_INWARD_LIMIT,
    FOLLOW_LAG_SECONDS,
    JUMP_CROUCH_SECONDS,
    JUMP_LAND_SECONDS,
    JUMP_SQUASH,
    JUMP_STRETCH,
    MOTION_LEVELS,
    OVERSHOOT,
    SETTLE_SHARE,
    STOP_LEAN_DEGREES,
    WALK_CROUCH,
    WALK_LEAN_DEGREES,
    WALK_SETTLE_SECONDS,
    WALK_WIND_UP_SECONDS,
    Phases,
    end_fade,
    follow_angles,
    follow_lag,
    follow_through,
    jump_motion_seconds,
    jump_phases,
    jump_stretch,
    landing_bounce,
    motion_ease,
    motion_strength,
    resolve_motion,
    settle_wobble,
    smoothstep,
    squash_scale,
    walk_accent,
    walk_motion_seconds,
    walk_phases,
)
from vidgen.cartoon.transition import Gesture, Jump, PoseChange, Walk
from vidgen.config import CharacterEntry
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.runtime import use_context
from vidgen.theme import Theme

GRID = [k / 40 for k in range(41)]


# ----- the curves at fixed times (no manim) ---------------------------------------------------------


def test_settings_and_strengths() -> None:
    assert MOTION_LEVELS == {"lively": 1.0, "calm": 0.4, "none": 0.0} and DEFAULT_MOTION == "lively"
    assert resolve_motion("none", "calm", "lively") == "none"   # the nearest (first) wins
    assert resolve_motion(None, "calm", "lively") == "calm" and resolve_motion(None, None) == "lively"
    assert motion_strength("calm") == 0.4
    with pytest.raises(ValueError, match="lively, calm, none"):
        motion_strength("wild")


def test_phases_split_the_time() -> None:
    phases = Phases.of(1.0, 2.0, 1.0)
    assert (phases.before, phases.after) == (0.25, 0.25)
    assert phases.split(0.125) == (0.5, 0.0, 0.0) and phases.split(0.5) == (1.0, 0.5, 0.0)
    assert phases.split(0.875) == (1.0, 1.0, 0.5) and phases.split(1.0) == (1.0, 1.0, 1.0)
    assert Phases().split(0.3) == (1.0, 0.3, 0.0) and Phases.of(0, 0, 0) == Phases()


def test_anticipation_and_overshoot_ease() -> None:
    a, s = ANTICIPATION_SHARE, SETTLE_SHARE
    assert motion_ease(0.0, 1.0) == 0.0 and motion_ease(1.0, 1.0) == 1.0
    assert motion_ease(a / 2, 1.0) == pytest.approx(-ANTICIPATION)   # back first: the wind-up's deepest point
    assert motion_ease(a, 1.0) == pytest.approx(0.0) and motion_ease(1 - s, 1.0) == pytest.approx(1.0)
    assert motion_ease(1 - s + s / 4, 1.0) == pytest.approx(1 + OVERSHOOT, abs=0.005)   # past the end
    assert min(motion_ease(u, 1.0) for u in GRID if u > 1 - s / 2) < 1.0   # and back a little: settling
    assert motion_ease(0.5, 1.0) == pytest.approx(smoothstep((0.5 - a) / (1 - a - s)))
    calm = [motion_ease(u, 0.4) for u in GRID]   # calm: the same shape, smaller
    assert min(calm) == pytest.approx(-0.4 * ANTICIPATION, abs=0.01) and max(calm) == pytest.approx(1 + 0.4 * OVERSHOOT, abs=0.01)
    assert settle_wobble(0.0) == settle_wobble(1.0) == 0.0 and max(settle_wobble(u / 1000) for u in range(1001)) == pytest.approx(1.0)
    assert -0.35 < min(settle_wobble(u / 100) for u in range(101)) < -0.25   # back about a third


def test_walk_wind_up_and_settle() -> None:
    walk = walk_seconds(4.25)
    assert walk_motion_seconds(walk, 1.0) == pytest.approx(walk + WALK_WIND_UP_SECONDS + WALK_SETTLE_SECONDS)
    assert walk_motion_seconds(0.0, 1.0) == 0.0
    phases = walk_phases(walk, 1.0)
    assert phases.before == pytest.approx(WALK_WIND_UP_SECONDS / walk_motion_seconds(walk, 1.0))
    back = walk_accent(phases.before / 2, phases, 1.0)
    assert back.lean == pytest.approx(WALK_LEAN_DEGREES) and back.stretch == pytest.approx(-WALK_CROUCH)   # crouch, lean back
    assert walk_accent(0.5, phases, 1.0).lean == 0.0   # walking: no accent
    on = walk_accent(1 - phases.after * 0.75, phases, 1.0)
    assert on.lean == pytest.approx(-STOP_LEAN_DEGREES, abs=0.5)   # leans on past the stop
    assert walk_accent(1.0, phases, 1.0).lean == pytest.approx(0.0, abs=1e-12)


def test_jump_squash_and_stretch() -> None:
    assert jump_motion_seconds(JUMP_SECONDS, 1.0) == pytest.approx(JUMP_SECONDS + JUMP_CROUCH_SECONDS + JUMP_LAND_SECONDS)
    phases = jump_phases(JUMP_SECONDS, 1.0)
    take_off = phases.before
    assert jump_stretch(0.0, phases, 1.0) == 0.0
    assert jump_stretch(take_off - 1e-9, phases, 1.0) == pytest.approx(-JUMP_SQUASH)   # crouched
    assert jump_stretch(take_off, phases, 1.0) == pytest.approx(JUMP_STRETCH)   # stretched leaving the ground
    top = take_off + (1 - phases.before - phases.after) / 2
    assert jump_stretch(top, phases, 1.0) == pytest.approx(0.0)   # round at the top
    landing = 1 - phases.after + 1e-9
    assert jump_stretch(landing, phases, 1.0) == pytest.approx(-JUMP_SQUASH)   # squashed on landing
    assert max(jump_stretch(1 - phases.after * (1 - v), phases, 1.0) for v in (0.3, 0.4, 0.5)) > 0   # a little rebound
    assert jump_stretch(1.0, phases, 1.0) == pytest.approx(0.0)
    assert landing_bounce(0.0) == 1.0 and landing_bounce(0.2) == pytest.approx(0.0, abs=1e-12) and landing_bounce(1.0) == 0.0
    sx, sy = squash_scale(-0.2)
    assert sy == pytest.approx(0.8) and sx * sy == pytest.approx(1.0)   # flatter and wider, same area
    assert squash_scale(0.0) == (1.0, 1.0)


def test_follow_through_lags_then_carries_on() -> None:
    step = lambda s: 1.0 if s >= 0.05 else 0.0   # noqa: E731
    tau = FOLLOW_LAG_SECONDS
    assert follow_lag(step, 0.05 + tau) == pytest.approx(1 - math.exp(-1), abs=0.01)   # a first-order lag
    assert follow_lag(step, 0.05 + 6 * tau) == pytest.approx(1.0, abs=0.01) and follow_lag(step, 0.0) == 0.0
    assert follow_lag(lambda s: 3.0, 0.4) == pytest.approx(3.0)
    assert follow_lag(step, 0.3, 0.0) == 1.0

    def speeding_up_then_steady(s: float) -> float:   # accelerates at 1 height/s² for 1 s, then 1 height/s
        s = max(s, 0.0)
        return s * s / 2 if s < 1 else 0.5 + (s - 1)

    assert follow_through(speeding_up_then_steady, 0.5) == pytest.approx(-tau * (1 - math.exp(-0.5 / tau)), abs=0.01)   # trails
    assert follow_through(speeding_up_then_steady, 3.0) == pytest.approx(0.0, abs=1e-3)   # steady: nothing
    stopping = lambda s: min(max(s, 0.0), 1.0)   # noqa: E731  walks 1 height/s, stops at 1 s
    assert follow_through(stopping, 1.05) > 0.5   # carries on after the stop
    angles = follow_angles(-1.0, 0.0, 1.0)
    assert angles["arm_left"] == angles["arm_right"] < 0 and angles["head"] > 0 and angles["accessory"] > 0   # trailing
    assert follow_angles(-100.0, 0.0, 1.0)["arm_left"] == -FOLLOW_ARM_LIMIT
    up = follow_angles(0.0, 1.0, 1.0)   # falling: arms raised outwards
    assert up["arm_left"] > 0 > up["arm_right"] and up["arm_left"] == -up["arm_right"] and up["head"] == 0
    assert follow_angles(0.0, -100.0, 1.0)["arm_left"] == -FOLLOW_INWARD_LIMIT
    assert end_fade(0.5) == 1.0 and end_fade(1.0) == 0.0


def test_none_turns_each_effect_off() -> None:
    assert all(motion_ease(u, 0.0) == smoothstep(u) for u in GRID)   # no anticipation, no overshoot
    assert all(motion_ease(u, 0.0, math.sqrt) == math.sqrt(u) for u in GRID)   # any base easing is kept
    plain = [min(1.0, t / GESTURE_EASE, (1.0 - t) / GESTURE_EASE) for t in GRID]
    assert all(gesture_weight(t, 0.0) == pytest.approx(smoothstep(r)) for t, r in zip(GRID, plain))
    assert all(gesture_moves(k, t, strength=0.0) == gesture_moves(k, t) for k in GESTURES for t in GRID)
    assert walk_motion_seconds(2.0, 0.0) == 2.0 and jump_motion_seconds(JUMP_SECONDS, 0.0) == JUMP_SECONDS
    assert walk_phases(2.0, 0.0) == Phases() == jump_phases(JUMP_SECONDS, 0.0)
    assert all(walk_accent(t, Phases(), 0.0) == walk_accent(t, walk_phases(2.0, 0.0), 0.0) for t in GRID)
    assert all(walk_accent(t, walk_phases(2.0, 0.0), 0.0).lean == walk_accent(t, walk_phases(2.0, 0.0), 0.0).stretch == 0 for t in GRID)
    assert all(jump_stretch(t, jump_phases(JUMP_SECONDS, 0.0), 0.0) == 0 for t in GRID)   # no squash or stretch
    assert set(follow_angles(-1.0, 1.0, 0.0).values()) == {0.0}   # no follow-through
    # and each is on with lively
    assert min(motion_ease(u, 1.0) for u in GRID) < 0 < max(motion_ease(u, 1.0) for u in GRID) - 1
    assert min(gesture_weight(t, 1.0) for t in GRID) < 0
    assert any(jump_stretch(t, jump_phases(JUMP_SECONDS, 1.0), 1.0) != 0 for t in GRID)
    assert any(walk_accent(t, walk_phases(2.0, 1.0), 1.0).lean != 0 for t in GRID)


# ----- the animations (no render) -------------------------------------------------------------------


def frames(anim: Any, count: int = 60) -> list[Any]:
    """Run ``anim`` frame by frame; returns (feet, squash, state) at each frame."""
    anim.begin()
    seen = []
    for k in range(count + 1):
        anim.interpolate(k / count)
        c = anim.mobject
        seen.append((c.feet().copy(), c._squash, c.state()))
    anim.finish()
    return seen


def test_walk_winds_up_trails_and_settles() -> None:
    c = figure().shift([-3.0, -2.0, 0.0])
    assert c.motion == "lively"
    before = c.state()
    walk = Walk(c, 2.0)
    assert walk.run_time == pytest.approx(walk_seconds(5.0) + WALK_WIND_UP_SECONDS + WALK_SETTLE_SECONDS)
    seen = frames(walk)
    xs = [f[0][0] for f in seen]
    wind = [s for f, s, _ in seen[: int(60 * walk._phases.before)]]
    assert xs[: len(wind)] == pytest.approx([-3.0] * len(wind)) and min(y for _, y in wind) < 1   # crouches on the spot
    assert max(abs(st.parts["body"].angle) for _, _, st in seen[:len(wind)]) > 0   # leans back
    settling = seen[-int(60 * walk._phases.after):]
    assert all(f[0] == pytest.approx(2.0) for f, _, _ in settling)   # feet still while settling
    assert min(st.parts["body"].angle for _, _, st in settling) < -1   # leans on past the stop
    assert xs[-1] == pytest.approx(2.0) and c._squash == (1.0, 1.0) and c.state().parts == before.parts


def test_walk_arms_trail_when_setting_off() -> None:
    c = figure()
    c.stop_idle()
    walk = Walk(c, 8.0)
    walk.begin()
    start = walk._phases.before
    walk.interpolate(start + 0.03)   # just set off: speeding up
    arms = c.pose_of("arm_left").angle + c.pose_of("arm_right").angle   # the walk cycle swings them opposite ways
    assert arms < 0 and c.pose_of("head").angle > 0   # both arms trail, the head tips back
    walk.finish()


def test_jump_crouches_stretches_and_lands() -> None:
    c = figure().shift([0.0, -2.0, 0.0])
    before = c.state()
    jump = Jump(c, 0.5)
    assert jump.run_time == pytest.approx(jump_motion_seconds(JUMP_SECONDS, 1.0))
    seen = frames(jump)
    crouch = [s for f, s, _ in seen if f[1] == pytest.approx(-2.0)][:5]
    assert min(y for _, y in crouch) < 1 < max(x for x, _ in crouch)   # squashed on the ground first
    flying = [(f, s) for f, s, _ in seen if f[1] > -2.0 + 1e-6]
    assert max(s[1] for _, s in flying) > 1   # stretched in the air
    top = max(flying, key=lambda fs: fs[0][1])
    assert top[0][1] == pytest.approx(-2.0 + 0.5 * c.character_height, abs=0.02)   # as high as asked
    falling = [st for f, _, st in seen if f[1] > -2.0 + 1e-6][-6:-2]
    assert any(st.parts["arm_left"].angle > 0 for st in falling)   # arms lift as it falls
    assert c.feet()[1] == pytest.approx(-2.0) and c._squash == (1.0, 1.0) and c.state() == before


def test_gesture_and_pose_change_wind_up_and_overshoot() -> None:
    c = figure()
    point = Gesture(c, "point")
    point.begin()
    point.interpolate(GESTURE_EASE * ANTICIPATION_SHARE / 2)
    assert c.pose_of("arm_left").angle < 0   # back first
    point.interpolate(GESTURE_EASE * (1 - SETTLE_SHARE * 3 / 4))
    assert c.pose_of("arm_left").angle > POINT_DEGREES   # past the point, then settles
    point.finish()
    assert c.pose_of("arm_left").angle == 0
    change = PoseChange(c, pose="pointing", run_time=1)
    change.begin()
    angles = []
    for k in range(61):
        change.interpolate(k / 60)
        angles.append(c.pose_of("arm_left").angle)
    change.finish()
    assert min(angles) < 0 and max(angles) > POINT_DEGREES and angles[-1] == pytest.approx(POINT_DEGREES)


def test_none_plays_the_plain_motion() -> None:
    c = figure().shift([-3.0, -2.0, 0.0])
    walk = Walk(c, 2.0, motion="none")
    assert walk.run_time == pytest.approx(walk_seconds(5.0))
    assert all(s == (1.0, 1.0) for _, s, _ in frames(walk))
    jump = Jump(c, 0.5, motion="none")
    assert jump.run_time == JUMP_SECONDS
    seen = frames(jump)
    assert all(s == (1.0, 1.0) for _, s, _ in seen) and all(st == seen[0][2] for _, _, st in seen)   # no squash, no follow-through
    c.motion = "none"
    change = PoseChange(c, pose="pointing", run_time=1)
    change.begin()
    angles = []
    for k in range(61):
        change.interpolate(k / 60)
        angles.append(c.pose_of("arm_left").angle)
    change.finish()
    assert angles == sorted(angles) and angles[-1] == pytest.approx(POINT_DEGREES)   # no wind-up, no overshoot


def test_actions_time_the_wind_up_and_landing() -> None:
    pip = figure().shift([-4.0, -2.0, 0.0])
    scene = StageFake(pip=pip)
    walk = use("walk_to", to="door")
    assert walk.run_time_for(scene, [target("pip", pip)]) == pytest.approx(walk_motion_seconds(walk_seconds(10.4), 1.0))
    jump = use("jump")
    assert jump.run_time_for(scene, [target("pip", pip)]) == pytest.approx(jump_motion_seconds(JUMP_SECONDS, 1.0))
    pip.motion = "calm"
    assert jump.run_time_for(scene, [target("pip", pip)]) == pytest.approx(jump_motion_seconds(JUMP_SECONDS, 0.4))
    pip.motion = "none"
    assert walk.run_time_for(scene, [target("pip", pip)]) == pytest.approx(walk_seconds(10.4))


# ----- the setting: video, scene, character (nearest wins) ------------------------------------------


def test_nearest_setting_wins(make_project) -> None:
    cast = [{"name": "pip"}, {"name": "kit", "cartoon_motion": "none"}]
    scenes = [{"id": "park", "type": "stage", "params": {"characters": ["pip", "kit"]}, "beats": [{"text": "Hi."}]}]
    project = Project.load(make_project(minimal_config(characters=cast, scenes=scenes, cartoon_motion="calm")))
    with use_context(project, Theme()):
        assert character("pip").motion == "calm"   # the video's
        assert character("pip", motion="lively").motion == "lively"   # the scene's wins over the video's
        assert character("kit", motion="lively").motion == "none"   # the character's own wins
    assert build_character(CharacterEntry(name="pip"), theme=Theme()).motion == "lively"   # nothing set
    assert stage_params(cartoon_motion="calm").cartoon_motion == "calm" and stage_params().cartoon_motion is None
    with pytest.raises(Exception, match="cartoon_motion"):
        stage_params(cartoon_motion="wild")
    with pytest.raises(Exception, match="cartoon_motion"):
        CharacterEntry(name="pip", cartoon_motion="wild")
    with pytest.raises(VidgenError, match="cartoon_motion"):
        Character([], name="x", motion="wild")


@pytest.mark.render
def test_stage_setting_reaches_its_characters(make_project, tmp_path: Path) -> None:
    cast = [{"name": "pip", "look": {"body": "bean"}}, {"name": "kit", "cartoon_motion": "lively"}]
    params = {"idle": False, "cartoon_motion": "none", "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}]}
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": [
        {"text": "Pip and kit jump for joy.", "actions": [{"jump": "pip"}, {"jump": "kit"}]}]}]
    project = Project.load(make_project(minimal_config(characters=cast, scenes=scenes, cartoon_motion="calm")))
    scene, _ = render_with_layout(project, "park", tmp_path / "media")
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    assert (pip.motion, kit.motion) == ("none", "lively")
    assert pip._squash == kit._squash == (1.0, 1.0)
