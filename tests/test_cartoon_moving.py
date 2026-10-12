"""Step 79: acting actions, part 2 (``walk_to``, ``enter``, ``exit``, ``gesture``, ``jump``): walk
times and the walk cycle, where entrances start and exits end (all without manim), the animations,
the actions, a speech bubble and the camera following a walking character, and the
``walk_overlap`` lint rule."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES, FakeScene, acting_project, figure, run, target, use
from test_cartoon_stage import render_with_layout
from vidgen import actions, extensions
from vidgen.cartoon.acting import (
    GESTURE_EASE,
    GESTURES,
    NOD_DEGREES,
    OFFSTAGE_GAP,
    POINT_DEGREES,
    SHRUG_DEGREES,
    STEP_LENGTH,
    WALK_EASE,
    WALK_SPEED,
    WAVE_DEGREES,
    enter_path,
    exit_path,
    gesture_moves,
    gesture_weight,
    jump_lift,
    nearer_side,
    offstage_x,
    walk_amplitude,
    walk_cycle,
    walk_progress,
    walk_seconds,
)
from vidgen.cartoon.transition import Gesture, Jump, Walk
from vidgen.cli import check_project, validate_warnings
from vidgen.lint import StillContext
from vidgen.lint.rules import RULES
from vidgen.config import LintRules
from vidgen.project import Project

FPS = 30


# ----- walking, entering, leaving (no manim) --------------------------------------------------------


def test_walk_duration_from_distance_and_speed() -> None:
    assert walk_seconds(4.25, 2.5) == pytest.approx(4.25 / 2.5 / (1 - WALK_EASE)) == pytest.approx(2.0)
    assert walk_seconds(-4.25, 2.5) == walk_seconds(4.25, 2.5)   # either way
    assert walk_seconds(0.0) == 0.0 and walk_seconds(10.0) == pytest.approx(2 * walk_seconds(5.0))
    assert walk_seconds(6.0, 2 * WALK_SPEED) == pytest.approx(walk_seconds(6.0) / 2)
    with pytest.raises(ValueError):
        walk_seconds(1.0, 0.0)
    # the middle of the walk goes at the given speed: distance per second there = speed
    distance, speed = 6.0, 3.0
    seconds = walk_seconds(distance, speed)
    dt = 0.01
    middle = (walk_progress(0.5 + dt / 2) - walk_progress(0.5 - dt / 2)) * distance / (dt * seconds)
    assert middle == pytest.approx(speed)
    assert [walk_progress(t) for t in (0.0, 0.5, 1.0)] == pytest.approx([0.0, 0.5, 1.0])
    samples = [walk_progress(k / 100) for k in range(101)]
    assert samples == sorted(samples) and walk_progress(WALK_EASE) == pytest.approx(0.5 * WALK_EASE / (1 - WALK_EASE))
    assert walk_amplitude(0.0) == walk_amplitude(1.0) == 0.0 and walk_amplitude(0.5) == 1.0


def test_walk_cycle() -> None:
    still = walk_cycle(0.0)   # legs passing: narrowest, body highest, nothing swung
    assert (still.legs_angle, still.arm_angle) == (0.0, 0.0) and still.legs_width < 1 and still.body_lift > 0
    footfall = walk_cycle(0.5)
    assert footfall.legs_angle == pytest.approx(10.0) and footfall.legs_width == pytest.approx(1.0) and footfall.body_lift == pytest.approx(0.0)
    assert walk_cycle(1.5).legs_angle == pytest.approx(-10.0)   # the next footfall swings the other way
    assert walk_cycle(0.5, amplitude=0.0) == walk_cycle(1.3, amplitude=0.0) == walk_cycle(0.0, amplitude=0.0)
    assert walk_cycle(0.0, amplitude=0.0).legs_width == 1.0


def test_enter_and_exit_end_positions() -> None:
    view = (-7.0, 7.0)
    assert nearer_side(-1.0, *view) == "left" and nearer_side(2.0, *view) == "right" and nearer_side(0.0, *view) == "left"
    assert offstage_x("left", *view, 1.0) == pytest.approx(-8.0 - OFFSTAGE_GAP)
    assert offstage_x("right", *view, 0.5) == pytest.approx(7.5 + OFFSTAGE_GAP)
    with pytest.raises(ValueError):
        offstage_x("up", *view, 1.0)
    # enter: from beyond the nearer edge (or the side given) to where it goes
    assert enter_path(None, 3.0, view, 1.0) == ("right", pytest.approx(8.0 + OFFSTAGE_GAP), 3.0)
    assert enter_path("left", 3.0, view, 1.0) == ("left", pytest.approx(-8.0 - OFFSTAGE_GAP), 3.0)
    # exit: until just beyond the nearer edge (or the side given), wholly outside the view
    assert exit_path(None, -2.0, view, 1.0) == ("left", pytest.approx(-8.0 - OFFSTAGE_GAP))
    assert exit_path("right", -2.0, (0.0, 14.0), 0.8) == ("right", pytest.approx(14.8 + OFFSTAGE_GAP))


def test_gestures_and_jumps() -> None:
    assert gesture_weight(0.0) == gesture_weight(1.0) == 0.0 and gesture_weight(0.5) == 1.0
    assert gesture_weight(GESTURE_EASE / 2) == pytest.approx(0.5)
    for kind in GESTURES:   # every gesture starts and ends in the pose
        for t in (0.0, 1.0):
            assert all(m.weight == 0 and m.turn == pytest.approx(0, abs=1e-9) and m.shift == pytest.approx((0, 0), abs=1e-9)
                       for m in gesture_moves(kind, t).values()), (kind, t)
    assert gesture_moves("point", 0.5) == {"arm_left": gesture_moves("point", 0.5)["arm_left"]}
    assert gesture_moves("point", 0.5)["arm_left"].angle == POINT_DEGREES
    assert gesture_moves("point", 0.5, "arm_right")["arm_right"].angle == -POINT_DEGREES   # the other side: mirrored
    wave = [gesture_moves("wave", t)["arm_left"] for t in (0.3, 0.5, 0.6)]
    assert all(m.angle == WAVE_DEGREES for m in wave) and len({round(m.turn, 3) for m in wave}) == 3   # to and fro
    shrug = gesture_moves("shrug", 0.5)
    assert (shrug["arm_left"].angle, shrug["arm_right"].angle) == (SHRUG_DEGREES, -SHRUG_DEGREES) and shrug["arm_left"].shift[1] > 0
    assert gesture_moves("nod", 0.25)["head"].turn == pytest.approx(-NOD_DEGREES) and gesture_moves("nod", 0.5)["head"].turn == pytest.approx(0)
    shake = gesture_moves("shake_head", 0.375)
    assert shake["head"].shift[0] < 0 and shake["eyes"].shift == shake["head"].shift and gesture_moves("shake_head", 0.625)["head"].shift[0] > 0
    with pytest.raises(ValueError, match="unknown gesture 'bow'"):
        gesture_moves("bow", 0.5)
    assert jump_lift(0.0) == jump_lift(1.0) == 0.0 and jump_lift(0.5, 2.0) == 2.0 and jump_lift(0.25, 1.0) == pytest.approx(0.75)


# ----- the animations (no render) -------------------------------------------------------------------


def play(anim: Any, frames: int = FPS) -> list[Any]:
    """Run ``anim`` frame by frame; returns the feet at each frame."""
    anim.begin()
    seen = []
    for k in range(frames + 1):
        anim.interpolate(k / frames)
        seen.append(anim.mobject.feet().copy())
    anim.finish()
    return seen


def test_walk_moves_the_feet_and_ends_in_the_pose() -> None:
    c = figure().face("left").shift([-3.0, -2.0, 0.0])
    c.set_pose("pointing")
    before = c.state()
    walk = Walk(c, 2.0)
    assert walk.run_time == pytest.approx(walk_seconds(5.0))
    feet = play(walk)
    xs = [f[0] for f in feet]
    assert xs == sorted(xs) and xs[0] == pytest.approx(-3.0) and xs[-1] == pytest.approx(2.0)
    assert all(f[1] == pytest.approx(-2.0) for f in feet)   # on the ground all the way
    assert c.facing == "right" and c.state().parts == before.parts   # faces the way it went, then the pose again
    mid = Walk(c, -4.0)
    mid.begin()
    mid.interpolate(0.5)
    assert c.facing == "left" and c.state().parts != before.parts   # mid-walk: legs and arms move
    assert c.character_height == pytest.approx(3.0) and STEP_LENGTH * c.character_height > 0
    mid.finish()


def test_walk_from_and_to_off_stage() -> None:
    c = figure()
    walk = Walk(c, 1.0, start_x=-9.0, park_x=None)
    feet = play(walk, 10)
    assert feet[0][0] == pytest.approx(-9.0) and c.feet()[0] == pytest.approx(1.0)
    leave = Walk(c, 9.0, park_x=20.0)
    play(leave, 10)
    assert c.feet()[0] == pytest.approx(9.0)
    leave.clean_up_from_scene(type("S", (), {"remove": lambda self, *m: None, "mobjects": []})())
    assert c.feet()[0] == pytest.approx(20.0)


def test_gesture_and_jump_come_back() -> None:
    c = figure()
    before = c.state()
    wave = Gesture(c, "wave")
    wave.begin()
    wave.interpolate(0.5)
    assert c.pose_of("arm_left").angle == pytest.approx(WAVE_DEGREES + gesture_moves("wave", 0.5)["arm_left"].turn)
    wave.finish()
    assert c.state() == before
    feet = c.feet().copy()
    jump = Jump(c, 0.5)
    jump.begin()
    jump.interpolate(0.5)
    assert c.feet()[1] - feet[1] == pytest.approx(0.5 * c.character_height)
    jump.finish()
    assert c.feet() == pytest.approx(feet)


# ----- the actions (no render) -------------------------------------------------------------------------


class StageFake(FakeScene):
    """FakeScene with a camera, a home mark per character and a camera that may follow."""

    def __init__(self, **mobs: Any) -> None:
        from manim import MovingCamera

        extensions.load_builtins()
        super().__init__(**mobs)
        self.camera = MovingCamera()
        self.camera.frame.scale(16.0 / self.camera.frame.width).move_to([0.0, 0.0, 0.0])
        self.homes = {"pip": -4.0}
        self.following: Any = None

    def follow_with_camera(self, x_of: Any) -> None:
        self.following = x_of

    @property
    def camera_following(self) -> Any:
        return self.following


def test_walk_to_enter_and_exit_actions() -> None:
    pip = figure().shift([-4.0, -2.0, 0.0])
    scene = StageFake(pip=pip)
    walk = use("walk_to", to="door")   # the stage's own mark at 0.9 of -8..8: x 6.4
    assert walk.run_time_for(scene, [target("pip", pip)]) == pytest.approx(walk_seconds(10.4))
    (anim,) = walk.apply(scene, [target("pip", pip)])
    run([anim])
    assert pip.feet()[0] == pytest.approx(6.4) and pip.walked_in == "b"
    assert use("walk_to", to=0.9).apply(scene, [target("pip", pip)]) == []   # there already
    assert use("walk_to", to="left", speed=5.0).run_time_for(scene, [target("pip", pip)]) == pytest.approx(walk_seconds(10.4, 5.0))

    out = use("exit", to="right")
    scene.following = type("X", (), {"followed": pip, "__call__": lambda self: 0.0})()
    (anim,) = out.apply(scene, [target("pip", pip)])
    assert scene.following is None   # the camera lets it go
    run([anim])
    assert pip.feet()[0] == pytest.approx(8.0 + pip.width / 2 + OFFSTAGE_GAP)   # just beyond the view
    anim.clean_up_from_scene(type("S", (), {"remove": lambda self, *m: None, "mobjects": []})())
    assert pip.feet()[0] == pytest.approx(offstage_x("right", -8.0, 8.0, pip.width / 2))   # then beyond the stage

    come = use("enter", side="left")
    start = offstage_x("left", -8.0, 8.0, pip.width / 2)
    assert come.run_time_for(scene, [target("pip", pip)]) == pytest.approx(walk_seconds(-4.0 - start))
    run(come.apply(scene, [target("pip", pip)]))
    assert pip.feet()[0] == pytest.approx(-4.0) and pip.facing == "right"   # back on its home mark
    run(use("enter", to="right").apply(scene, [target("pip", pip)]))   # nearer edge of x 4: the right one
    assert pip.feet()[0] == pytest.approx(4.0) and pip.facing == "left"


def test_gesture_and_jump_actions() -> None:
    from manim import Square

    pip = figure()
    scene = StageFake(pip=pip, lamp=Square())
    wave = use("gesture", to="wave")
    assert wave.character_needs() == "gesture: wave" and wave.run_time_for(scene, []) == 1.6
    (anim,) = wave.apply(scene, [target("pip", pip)])
    assert isinstance(anim, Gesture) and use("gesture", to="nod").apply(scene, [target("lamp", scene.mobs["lamp"])]) == []
    (hop,) = use("jump", height=1.0).apply(scene, [target("pip", pip)])
    assert isinstance(hop, Jump) and hop.lift == 1.0


def test_runner_uses_the_walk_time_and_plays_follow_with_the_walk() -> None:
    """The phase of a walk lasts its distance over its speed (``run_time:`` wins), and a
    ``follow`` due with it plays in the same phase (it only reads where the character is)."""
    pip = figure().shift([-4.0, -2.0, 0.0])
    scene = StageFake(pip=pip)
    scene.find_targets = lambda p: [target(p, pip)]
    scene.is_shown = lambda t: True
    runner = actions.ActionRunner.__new__(actions.ActionRunner)
    runner.scene = scene

    def due(name: str, run_time: float | None = None, **options: Any) -> Any:
        act = use(name, **options)
        act.config = act.config.model_copy(update={"run_time": run_time})
        kind = type("Kind", (), {"cls": type(act), "name": name})()
        return actions._Due(0, actions.ActionUse("b", "here", act.config, kind, act), False)

    phases = runner._phases([due("follow"), due("walk_to", to="door")])
    assert len(phases) == 1 and phases[0][1] == pytest.approx(walk_seconds(10.4))
    timed = actions.ActionRunner._natural(runner, due("walk_to", to="door", run_time=1.0))
    assert timed == 1.0
    assert len(runner._phases([due("dim"), due("walk_to", to="door")])) == 2   # dim changes pip: one after the other


# ----- the bubble and the camera follow a walking character -------------------------------------------


def test_bubble_follows_its_speaker() -> None:
    from manim import Square

    from vidgen.scenes.acting import follow_speaker

    pip = figure()
    bubble = Square(1.0).move_to([0.5, 4.0, 0.0])
    follow_speaker(bubble, pip)
    pip.shift([3.0, 0.5, 0.0])
    bubble.update()
    assert bubble.get_center()[:2] == pytest.approx((3.5, 4.5))


def test_follow_catches_up_with_a_walking_target() -> None:
    from manim import MovingCamera, tempconfig

    from test_cartoon_parallax import FW, FH, FakeScene as CameraScene

    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": FW, "frame_height": FH}):
        scene = CameraScene(MovingCamera(), 3 * FW)
        pip = figure().shift([-10.0, -2.0, 0.0])
        follow = use("follow")
        (move,) = follow.apply(scene, [target("pip", pip)])
        move.begin()
        pip.shift([4.0, 0.0, 0.0])   # walks on while the camera pans
        move.interpolate(1.0)
        assert scene.camera.frame.get_center()[0] == pytest.approx(-6.0)   # where pip is now, not where it was
        move.clean_up_from_scene(scene)
        assert scene.following() == pytest.approx(-6.0) and scene.following.followed is pip


# ----- validate --------------------------------------------------------------------------------------


def test_validate_moving_actions(make_project) -> None:
    good = acting_project(make_project, [
        {"text": "Pip walks over.", "actions": [{"walk_to": "pip", "to": "centre"}, {"enter": "kit", "side": "right"}, {"follow": "pip"}]},
        {"text": "Kit waves and leaves.", "actions": [{"gesture": "kit", "to": "wave"}, {"jump": "pip", "height": 0.6},
                                                      {"exit": "kit", "to": "right", "at": 0.5}, {"walk_to": "pip", "to": 0.3, "speed": 4}]},
    ])
    assert check_project(good) == []
    bad = acting_project(make_project, [{"text": "Hello.", "actions": [
        {"walk_to": "pip", "to": "nowhere"}, {"gesture": "pip", "to": "bow"}, {"enter": "tree"}, {"exit": "kit", "to": "up"},
        {"jump": "pip", "height": 0}, {"walk_to": "kit"}, {"enter": "pip", "to": 2},
    ]}])
    problems = check_project(bad)
    where = "scenes[0].beats[0].actions"
    expected = [
        f"{where}[0].to: unknown mark 'nowhere'",
        f"{where}[1].to",
        f"{where}[2].target: 'tree' is not a character; enter acts on characters",
        f"{where}[3].to",
        f"{where}[4].height",
        f"{where}[5].to",
        f"{where}[6].to",
    ]
    for start in expected:
        assert any(p.startswith(start) for p in problems), (start, problems)


def test_validate_warns_about_gestures_without_the_parts(make_project) -> None:
    root = make_project(minimal_config(
        characters=[{"name": "blob", "look": {"svg": "assets/blob.svg"}}],
        scenes=[{"id": "park", "type": "stage", "params": {"characters": ["blob"]}, "beats": [
            {"text": "Hello.", "actions": [{"gesture": "blob", "to": "wave"}, {"gesture": "blob", "to": "nod"}, {"walk_to": "blob", "to": "left"}]}]}],
    ))
    (root / "assets").mkdir()
    (root / "assets" / "blob.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect id="body" width="10" height="10" fill="#3a6"/></svg>', encoding="utf-8"
    )
    project = Project.load(root)
    assert check_project(project) == []
    assert [w for w in validate_warnings(project) if w.startswith("scenes[")] == [
        "scenes[0].beats[0].actions[0]: character 'blob' cannot gesture: wave (needs arm_left or arm_right); the action does nothing for it",
        "scenes[0].beats[0].actions[1]: character 'blob' cannot gesture: nod (needs head); the action does nothing for it",
    ]


# ----- lint ---------------------------------------------------------------------------------------------


def test_walk_overlap_rule() -> None:
    def figure_obj(name: str, box: list[float], walked: str | None = None) -> dict[str, Any]:
        obj = {"id": name, "kind": "character", "name": name, "path": f"Stage/{name}", "bbox": box, "opacity": 1.0}
        return {**obj, "walked_in": walked} if walked else obj

    def check(objects: list[dict[str, Any]], beat: str = "b2") -> list[Any]:
        ctx = StillContext(layout={"width": 854, "height": 480}, frame={"beat": beat, "objects": objects}, objects=objects)
        return list(RULES["walk_overlap"].check(ctx, LintRules().walk_overlap))

    kit = figure_obj("kit", [500, 100, 600, 400])
    (issue,) = check([figure_obj("pip", [540, 100, 640, 400], "b2"), kit])
    assert issue.message.startswith("character 'pip' ends its walk on character 'kit' (60% of the narrower one's width)")
    assert issue.value == 0.6 and issue.bbox == (540, 100, 600, 400)
    assert check([figure_obj("pip", [540, 100, 640, 400], "b1"), kit]) == []   # its walk ended in an earlier beat
    assert check([figure_obj("pip", [590, 100, 690, 400], "b2"), kit]) == []   # 10%: side by side
    assert check([figure_obj("pip", [540, 100, 640, 400]), kit]) == []   # never walked
    assert len(check([figure_obj("pip", [540, 100, 640, 400], "b2"), figure_obj("kit", [500, 100, 600, 400], "b2")])) == 1   # once a pair


# ----- render ------------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_walk_on_a_stage(make_project, tmp_path: Path) -> None:
    """kit waits off stage until it enters; the camera follows pip walking right with its bubble."""
    params = {"idle": False, "width": 1.5, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}]}
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": [
        {"text": "Pip says hello and then walks all the way over to the right.", "voice": "pip_voice",
         "actions": [{"say": "pip", "bubble": "Hi!"}, {"follow": "pip", "at": 0.3}, {"walk_to": "pip", "to": "right", "speed": 6, "at": 0.3}]},
        {"text": "Kit comes in from the left and waves at everyone there.", "voice": "kit_voice",
         "actions": [{"enter": "kit", "side": "left", "to": "centre", "speed": 8}, {"gesture": "kit", "to": "wave", "at": 0.6}]},
    ]}]
    project = Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))
    scene, objects = render_with_layout(project, "park", tmp_path / "media")
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    named = {o["name"]: o for o in objects if o["name"]}
    assert named["pip"]["walked_in"] == "park_b1" and "walked_in" not in named.get("kit", {})
    assert "kit" not in named or named["kit"]["bbox"][2] <= 0   # beat 1's still: kit still off stage, outside the view
    left, right = scene.camera_bounds()[:2]
    assert pip.feet()[0] == pytest.approx(left + 0.75 * (right - left)) and kit.feet()[0] == pytest.approx(0.0, abs=1e-6)
    assert kit.walked_in == "park_b2" and kit.facing == "right"
    frame = scene.camera.frame
    assert frame.get_center()[0] == pytest.approx(min(pip.feet()[0], right - frame.width / 2))   # followed pip
    together = [p for p in scene.play_log if "Walk" in p.animations and "_MoveThenFollow" in p.animations]
    assert together, [p.animations for p in scene.play_log]
    assert any("Gesture" in p.animations for p in scene.play_log)
