"""Step 93: interacting with props (``pick_up``, ``hold``, ``put_down``, ``give``, ``throw``): the
holding state machine, where held, put-down and thrown props go (no manim), the actions on a fake
stage, the checks of ``vidgen validate``, the planner leaving holding hands alone, the landing
sound, and one tiny render with the layout dump's keys."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from test_cartoon_acting import CAST, VOICES, figure, run, target, use
from test_cartoon_directing import directed, line
from test_cartoon_moving import StageFake
from test_cartoon_stage import render_with_layout
from conftest import minimal_config
from vidgen.cartoon.foley import PlayedAction, foley_cues
from vidgen.cartoon.holding import (
    HOLD_MAX_HEIGHT,
    PICK_UP_REACH,
    THROW_FLIGHT_MAX,
    HandlingStep,
    HoldingError,
    Holdings,
    held_height,
    hold_point,
    holding_problems,
    put_down_x,
    spin_degrees,
    throw_point,
    throw_release_share,
    throw_seconds,
)
from vidgen.cartoon.props import draw_prop
from vidgen.cartoon.transition import ArmMove, PropMove
from vidgen.cli import check_project
from vidgen.project import Project
from vidgen.theme import Theme


# ----- the state machine (no manim) ---------------------------------------------------------------


def test_take_release_and_give() -> None:
    h = Holdings()
    assert h.take("kit", "cup") == "left" and h.take("kit", "ball") == "right"   # the near hand first
    assert h.hands("kit") == {"left": "cup", "right": "ball"} and h.holder("cup") == ("kit", "left")
    with pytest.raises(HoldingError, match="already holds 'cup' and 'ball'"):
        h.take("kit", "box")
    with pytest.raises(HoldingError, match="held by kit; kit can give it"):
        h.take("pip", "cup")
    with pytest.raises(HoldingError, match="two props"):
        h.release("kit")
    assert h.release("kit", "ball") == ("ball", "right") and h.holder("ball") is None
    assert h.give("kit", "pip", hand="right") == ("cup", "left", "right") and h.hands("pip") == {"right": "cup"}
    with pytest.raises(HoldingError, match="holds no prop"):
        h.release("kit")
    with pytest.raises(HoldingError, match="does not hold 'cup' \\(pip holds it\\)"):
        h.release("kit", "cup")
    with pytest.raises(HoldingError, match="right hand already holds 'cup'"):
        h.take("pip", "ball", "right")
    with pytest.raises(HoldingError, match="itself"):
        h.give("pip", "pip")
    with pytest.raises(HoldingError, match="already holds 'cup'"):
        h.take("pip", "cup")


def test_where_props_go() -> None:
    assert hold_point((1.0, 2.0), 3.0, "right") == pytest.approx((1.36, 1.61))
    assert hold_point((1.0, 2.0), 3.0, "left") == pytest.approx((0.64, 1.61))   # in front, either way
    assert held_height(0.09, 3.0) == pytest.approx(0.27) and held_height(1.7, 3.0) == pytest.approx(HOLD_MAX_HEIGHT * 3.0)   # a tree shrinks
    assert put_down_x(0.0, 2.0, "left") < 0 < put_down_x(0.0, 2.0, "right")
    start, end = (0.0, 1.0), (6.0, -1.0)
    assert throw_point(0.0, start, end, 1.5) == pytest.approx(start) and throw_point(1.0, start, end, 1.5) == pytest.approx(end)
    ys = [throw_point(k / 200, start, end, 1.5)[1] for k in range(201)]
    assert max(ys) == pytest.approx(2.5, abs=1e-3)   # peaks 1.5 above the higher end
    assert spin_degrees(1.0, 2, 3.0) == -720.0 and spin_degrees(1.0, 1, -3.0) == 360.0 and spin_degrees(0.5, 1, 1.0) == -180.0
    assert throw_seconds(100.0) == pytest.approx(0.5 + THROW_FLIGHT_MAX) and 0 < throw_release_share(3.0) < throw_release_share(0.0) < 1


def test_replaying_a_scene_finds_what_cannot_happen() -> None:
    chars = {"pip": (-4.0, 3.6), "kit": (4.0, 3.6)}
    props = {"cup": 0.0, "ball": -3.0}

    def problems(*steps: tuple[str, str, dict[str, Any]], entering: tuple[str, ...] = ()) -> list[tuple[str, str]]:
        made = [HandlingStep(f"beats[0].actions[{k}]", action, (who,), options) for k, (action, who, options) in enumerate(steps)]
        place = {"centre": 0.0, "left": -4.0, "right": 4.0}
        return holding_problems(made, characters=chars, props=props, place_x=lambda p: place.get(p) if isinstance(p, str) else (p - 0.5) * 16,
                                to_fraction=lambda x: x / 16 + 0.5, entering=entering)

    (far,) = problems(("pick_up", "pip", {"to": "cup"}))
    assert far[0] == "beats[0].actions[0].to" and "1.1 of its heights from 'cup'" in far[1]
    assert far[1].endswith("walk_to first (- walk_to: pip, to: 0.41)")   # beside the cup, on pip's side
    assert problems(("walk_to", "pip", {"to": 0.41}), ("pick_up", "pip", {"to": "cup"})) == []
    assert problems(("pick_up", "pip", {"to": "ball"}), ("walk_to", "pip", {"to": "right"}), ("give", "pip", {"to": "kit"})) == []   # walked over with it
    (apart,) = problems(("pick_up", "pip", {"to": "ball"}), ("give", "pip", {"to": "kit"}))
    assert "pip is 2.2 of its heights from kit" in apart[1] and "next to each other" in apart[1]
    (away,) = problems(("pick_up", "pip", {"to": "ball"}), ("give", "pip", {"to": "kit"}), entering=("kit",))
    assert "kit is not on stage then" in away[1]
    (nothing,) = problems(("throw", "pip", {"to": "right"}))
    assert nothing == ("beats[0].actions[0].target", "pip holds no prop then; pick_up one first")
    (spot,) = problems(("pick_up", "pip", {"to": "ball"}), ("put_down", "pip", {"to": "right"}))
    assert "where it puts the prop down" in spot[1]
    assert problems(("pick_up", "pip", {"to": "ball"}), ("throw", "pip", {"to": "centre"}), ("walk_to", "pip", {"to": 0.45}), ("pick_up", "pip", {"to": "ball"})) == []   # it lies where it landed
    (moved,) = problems(("pick_up", "pip", {"to": "ball"}), ("keyframes", "ball", {}))
    assert moved[1] == "'ball' is held by pip then; put_down or throw it first"
    (taken,) = problems(("pick_up", "pip", {"to": "ball"}), ("hold", "kit", {"to": "ball"}))
    assert "'ball' is held by pip" in taken[1]
    assert PICK_UP_REACH * 3.6 >= 1.0   # ball is 1 unit from pip: in reach


# ----- the actions on a fake stage (no render) -------------------------------------------------------


def stage() -> tuple[StageFake, Any, Any, Any]:
    pip = figure("pip").shift([-4.0, -2.0, 0.0])
    kit = figure("kit").face("left").shift([-2.5, -2.0, 0.0])
    cup = draw_prop("cup", height=0.3, theme=Theme(), name="cup").shift([-3.2, -2.0, 0.0])
    cup.height_factor = 0.3 / pip.character_height
    scene = StageFake(pip=pip, kit=kit, cup=cup)
    scene.mobjects = [cup, pip, kit]
    return scene, pip, kit, cup


def test_pick_up_follow_and_put_down() -> None:
    scene, pip, kit, cup = stage()
    rest = pip.state()
    pick = use("pick_up", to="cup")
    anims = pick.apply(scene, [target("pip", pip)])
    assert [type(a) for a in anims] == [ArmMove, PropMove] and scene.mobjects == [pip, cup, kit]   # drawn right after its holder
    run(anims)
    assert np.allclose(cup.get_center(), pip.hand_point("left"), atol=1e-6)
    expected = hold_point(pip.shoulder_point("left"), pip.character_height, "right")
    assert pip.hand_point("left")[:2] == pytest.approx(expected, abs=1e-6)   # the elbow bent to hold it there
    assert cup.held_by == "pip" and cup.hand == "left" and pip.holding == {"left": "cup"}
    assert cup.height == pytest.approx(0.3, rel=1e-3)   # small enough: its own size
    pip.shift([2.0, 0.5, 0.0])
    cup.update()
    assert np.allclose(cup.get_center(), pip.hand_point("left"), atol=1e-6)   # follows the hand
    assert cup not in pip.get_family()   # never added to the character (DESIGN.md §69.22)

    down = use("put_down")
    run(down.apply(scene, [target("pip", pip)]))
    assert pip.holding == {} and cup.held_by is None and not cup.updaters
    assert pip.pose_of("arm_left") == rest.parts["arm_left"]   # the arm as before
    assert cup.feet()[0] == pytest.approx(put_down_x(-2.0, pip.character_height, "right"), abs=1e-6)
    assert cup.feet()[1] == pytest.approx(pip.feet()[1], abs=1e-6) and cup.height == pytest.approx(0.3, rel=1e-3)


def test_give_and_throw() -> None:
    scene, pip, kit, cup = stage()
    run(use("hold", to="cup").apply(scene, [target("pip", pip)]))
    assert pip.holding == {"left": "cup"}
    give = use("give", to="kit")
    anims = give.apply(scene, [target("pip", pip)])
    assert sum(isinstance(a, ArmMove) for a in anims) == 2 and pip.facing == "right" and kit.facing == "left"   # face each other
    run(anims)
    assert pip.holding == {} and kit.holding == {"left": "cup"} and cup.held_by == "kit"
    assert np.allclose(cup.get_center(), kit.hand_point("left"), atol=1e-6)
    assert scene.mobjects.index(cup) == scene.mobjects.index(kit) + 1

    throw = use("throw", to="right", spin=2, target="kit")
    x = 4.0   # the right mark of -8..8
    assert throw.run_time_for(scene, [target("kit", kit)]) == pytest.approx(throw_seconds(x - kit.feet()[0]))
    anims = throw.apply(scene, [target("kit", kit)])
    assert kit.facing == "right"   # turns towards where it throws
    flight = next(a for a in anims if isinstance(a, PropMove))
    assert flight.lands_at == 1.0 and flight.turns == 2 and flight.rise == pytest.approx(0.5 * kit.character_height)
    flight.begin()
    flight.interpolate(0.75)
    assert cup.get_center()[1] > kit.hand_point("left")[1]   # up in the air
    flight.finish()
    for a in anims:
        if a is not flight:
            a.begin()
            a.finish()
    assert cup.feet()[0] == pytest.approx(x, abs=1e-6) and cup.feet()[1] == pytest.approx(kit.feet()[1], abs=1e-6)
    assert cup.height == pytest.approx(0.3 * kit.character_height / pip.character_height, rel=1e-3)   # upright, its size next to kit
    assert kit.holding == {} and cup.held_by is None


def test_a_big_prop_is_smaller_in_the_hand() -> None:
    scene, pip, kit, _ = stage()
    box = draw_prop("box", height=3.0, theme=Theme(), name="box").shift([-3.5, -2.0, 0.0])
    box.height_factor = 1.0
    scene.mobs["box"] = box
    run(use("pick_up", to="box").apply(scene, [target("pip", pip)]))
    assert box.height == pytest.approx(HOLD_MAX_HEIGHT * pip.character_height, rel=1e-3)
    run(use("put_down").apply(scene, [target("pip", pip)]))
    assert box.height == pytest.approx(pip.character_height, rel=1e-3)


# ----- validate ---------------------------------------------------------------------------------------


def prop_project(make_project, beats: list[dict[str, Any]]) -> Project:
    params = {"idle": False, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}],
              "props": [{"prop": "ball", "at": 0.5}, {"prop": "tree", "at": "far_right"}]}
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))


def test_validate_prop_actions(make_project) -> None:
    good = prop_project(make_project, [
        {"text": "Pip walks to the ball and picks it up.", "actions": [{"walk_to": "pip", "to": 0.42}, {"pick_up": "pip", "to": "ball", "at": 0.5}]},
        {"text": "Pip carries it over and gives it to Kit.", "actions": [{"walk_to": "pip", "to": 0.65}, {"give": "pip", "to": "kit", "at": 0.6}]},
        {"text": "Kit throws it far away.", "actions": [{"throw": "kit", "to": "far_left", "spin": 2}]},
    ])
    assert check_project(good) == []
    bad = prop_project(make_project, [{"text": "Hello.", "actions": [
        {"pick_up": "pip", "to": "kite"}, {"pick_up": "pip", "to": "ball"}, {"give": "pip", "to": "rex"}, {"put_down": "kit", "to": "nowhere"},
        {"throw": "tree", "to": "left"},
    ]}])
    problems = check_project(bad)
    where = "scenes[0].beats[0].actions"
    for start in (f"{where}[0].to: 'kite' is not a prop of the scene (props: ball, tree)", f"{where}[2].to: 'rex' is not a character on the stage",
                  f"{where}[3].to: unknown mark 'nowhere'", f"{where}[4].target: 'tree' is not a character"):
        assert any(p.startswith(start) for p in problems), (start, problems)
    order = prop_project(make_project, [
        {"text": "Pip picks up the ball from afar.", "actions": [{"pick_up": "pip", "to": "ball"}]},
        {"text": "Kit gets it from far away.", "actions": [{"walk_to": "pip", "to": 0.42}, {"pick_up": "pip", "to": "ball"}, {"give": "pip", "to": "kit", "at": 0.5}]},
    ])
    (far, apart) = check_project(order)
    assert far.startswith("scenes[0].beats[0].actions[0].to: pip is") and "walk_to first (- walk_to: pip, to: 0.40)" in far
    assert apart.startswith("scenes[0].beats[1].actions[2].to: pip is") and "next to each other" in apart


# ----- the planner leaves holding hands alone, the landing sound -----------------------------------------


def test_no_arm_gesture_with_a_holding_hand() -> None:
    text = "This kite is truly REMARKABLE today, my friend."
    free = directed([line("b1", text, ("pip",))])["b1"][0]["to"]
    assert free in ("point", "wave", "shrug")
    held = directed([line("b0", "Pip takes the cup.", (), [{"hold": "pip", "to": "cup"}]), line("b1", text, ("pip",))])
    assert held["b1"][0]["to"] in ("nod", "shake_head")   # the near hand holds the cup
    right = directed([line("b0", "Pip takes the cup.", (), [{"hold": "pip", "to": "cup", "hand": "right"}]), line("b1", text, ("pip",))])
    assert right["b1"][0]["to"] in ("point", "wave", "nod", "shake_head")   # the near arm is free; no shrug
    after = directed([line("b0", "Pip takes the cup.", (), [{"hold": "pip", "to": "cup"}, {"put_down": "pip", "at": 0.5}]), line("b1", text, ("pip",))])
    assert after["b1"][0]["to"] == free


def test_a_thrown_prop_lands_with_a_thud() -> None:
    (cue,) = foley_cues(PlayedAction("throw", 2.0, 1.5, lands=1.0))
    assert (cue.time, cue.sound) == (3.5, "thud")
    assert foley_cues(PlayedAction("throw", 2.0, 1.5)) == []   # the thrower's arm makes no sound


# ----- render ----------------------------------------------------------------------------------------------


@pytest.mark.render
def test_props_change_hands_on_a_stage(make_project, tmp_path: Path) -> None:
    """pip picks up the ball and walks over with it (the dump says who holds it); kit throws it."""
    project = prop_project(make_project, [
        {"text": "Pip picks up the ball and carries it over.", "voice": "pip_voice",
         "actions": [{"walk_to": "pip", "to": 0.42, "speed": 8}, {"pick_up": "pip", "to": "ball", "at": 0.2}, {"walk_to": "pip", "to": 0.62, "speed": 8, "at": 0.5}]},
        {"text": "Kit takes it and throws it to the left.", "voice": "kit_voice",
         "actions": [{"give": "pip", "to": "kit"}, {"throw": "kit", "to": "far_left", "at": 0.4}]},
    ])
    from vidgen.introspect import LayoutRecorder

    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "park", tmp_path / "media", recorder)
    ends = [f for f in recorder.frames if "mid" not in f]   # the beat-end stills (mid-action ones too: Step 83)
    objects = ends[0]["objects"]
    named = {o["name"]: o for o in objects if o["name"]}
    assert named["ball"]["held_by"] == "pip" and named["ball"]["hand"] == "left" and named["pip"]["holding"] == {"left": "ball"}
    ball_box, pip_box = named["ball"]["bbox"], named["pip"]["bbox"]
    assert pip_box[0] <= (ball_box[0] + ball_box[2]) / 2 <= pip_box[2]   # at pip's hand
    assert any(f.get("mid", "").startswith("throw") and f["objects"] for f in recorder.frames)   # a mid-throw still
    assert [o["name"] for o in objects].index("ball") == [o["name"] for o in objects].index("pip") + 1
    last = {o["name"]: o for o in ends[-1]["objects"] if o["name"]}
    assert "held_by" not in last["ball"] and "holding" not in last["kit"]
    left, right = scene.camera_bounds()[:2]
    assert scene.props["ball"].feet()[0] == pytest.approx(left + 0.1 * (right - left), abs=1e-6)
    assert [e.sound for e in scene.sfx_log].count("thud") == 1
    thud = next(e for e in scene.sfx_log if e.sound == "thud")
    flight = next(p for p in scene.play_log if "PropMove" in p.animations and "ArmMove" in p.animations and p.start > scene.beat_log[1].start)
    assert thud.time == pytest.approx(flight.end, abs=0.25)
