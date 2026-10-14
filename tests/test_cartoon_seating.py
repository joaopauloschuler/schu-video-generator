"""Step 94: sitting and leaning (``sit_on``, ``lean_on``, ``stand_up``) and the crouch of
``pick_up`` / ``put_down``: the seats and lean edges of props, the postures state machine and the
seated feet (no manim), the seated, crouched and leaning states of a generated and an SVG
character, the actions on a fake stage, the checks of ``vidgen validate``, the planner leaving a
seated character's facing alone, and one tiny render with the layout dump's keys."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES, figure, run, target, use
from test_cartoon_directing import DUO, FH, FW, directed, line
from test_cartoon_moving import StageFake
from test_cartoon_poses import built
from test_cartoon_stage import render_with_layout
from vidgen.cartoon.directing import StageFrame
from vidgen.cartoon.props import PROP_HEIGHTS, draw_prop, read_svg_seat_and_lean
from vidgen.cartoon.seating import (
    CROUCH_MAX,
    PROP_LEANS,
    PROP_SEATS,
    PostureError,
    Postures,
    crouch_drop,
    crouch_stoop,
    mirrored_lean,
    mirrored_seat,
    seated_sole,
    svg_seat_and_lean,
)
from vidgen.cartoon.transition import ArmMove, BodyMove
from vidgen.cli import check_project
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.theme import Theme

GROUND = 1e-6


def flat(soles: dict[str, tuple[float, float]]) -> list[float]:
    return [v for foot in sorted(soles) for v in soles[foot]]


# ----- seats, lean edges, the state machine and the feet (no manim) --------------------------------------


def test_postures_say_what_to_do_instead() -> None:
    p = Postures()
    p.sit("kit", "chair")
    with pytest.raises(PostureError, match="'chair' is taken: kit sits on it then"):
        p.sit("pip", "chair")
    with pytest.raises(PostureError, match=r"kit sits on 'chair' then; stand_up first \(- stand_up: kit\)"):
        p.lean("kit", "tree")
    with pytest.raises(PostureError, match="stand_up first"):
        p.pinned("kit", "walk_to")
    p.pinned("kit", "gesture")   # arms and head move while seated
    p.lean("pip", "tree")
    p.lean("rex", "tree")   # several lean on one prop
    assert p.on("tree") == ["pip", "rex"] and p.stand("kit") == ("sitting", "chair") and p.of("kit") is None
    with pytest.raises(PostureError, match="kit neither sits nor leans then"):
        p.stand("kit")


def test_seated_feet_and_the_crouch() -> None:
    assert seated_sole((0.0, 0.3), 0.1, 0.2) == pytest.approx((0.0, 0.0), abs=1e-6)   # thigh straight down
    x, y = seated_sole((0.0, 0.25), 0.1, 0.2)
    assert y == 0.0 and x == pytest.approx(math.sqrt(0.01 - 0.0025))   # knee forward, shin straight down
    assert seated_sole((0.0, 0.5), 0.1, 0.2) == pytest.approx((0.1, 0.3))   # a high seat: thigh level, foot hanging
    assert seated_sole((0.0, 0.05), 0.1, 0.2) == (0.0, 0.0)   # a low seat: folded
    assert crouch_drop(0.1, 0.0, 0.25, 0.2) == 0.0   # in reach standing
    assert crouch_drop(0.3, 0.0, 0.25, 0.4) == pytest.approx(0.3 - 0.95 * 0.25)
    assert crouch_drop(5.0, 0.0, 0.25, 0.2) == pytest.approx(CROUCH_MAX * 0.2)   # at most this deep
    assert crouch_stoop(0.0, 0.2) == 0.0 < crouch_stoop(0.05, 0.2) < crouch_stoop(1.0, 0.2) == pytest.approx(15.0)


def test_props_have_seats_and_lean_edges() -> None:
    assert set(PROP_SEATS) == {"chair", "rock", "box", "sofa", "armchair", "bed", "desk", "bench", "log"} and {"tree", "door", "sign"} <= set(PROP_LEANS)
    for kind, (x, y) in PROP_SEATS.items():
        prop = draw_prop(kind, height=2.0, theme=Theme()).shift([1.0, -1.0, 0.0])
        seat = prop.seat_point()
        assert prop.get_left()[0] < seat[0] < prop.get_right()[0] and seat[1] == pytest.approx(-1.0 + 2.0 * y), kind
        assert prop.lean_edges() is None
    chair = draw_prop("chair", height=2.0, theme=Theme(), facing="left")
    assert chair.seat_point()[0] == pytest.approx(-2.0 * PROP_SEATS["chair"][0])   # mirrored with the prop
    for kind, (left, right) in PROP_LEANS.items():
        prop = draw_prop(kind, height=2.0, theme=Theme())
        assert prop.lean_edges() == pytest.approx((2.0 * left, 2.0 * right)) and prop.seat_point() is None, kind
    assert draw_prop("ball", height=1.0, theme=Theme()).seat_point() is None
    assert mirrored_seat((0.1, 0.5), "left") == (-0.1, 0.5) and mirrored_lean((-0.4, 0.36), "left") == (-0.36, 0.4)


def test_svg_props_give_seats_in_view_box_coordinates(tmp_path: Path) -> None:
    root = ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg" data-seat="60 50" data-lean="90 10"/>')
    seat, lean = svg_seat_and_lean(root, (0.0, 0.0, 100.0, 100.0), "bench.svg")
    assert seat == pytest.approx((0.1, 0.5)) and lean == pytest.approx((-0.4, 0.4))   # from the box's bottom middle
    assert svg_seat_and_lean(ET.fromstring("<svg/>"), (0, 0, 10, 10), "x") == (None, None)
    with pytest.raises(ValueError, match="data-seat must be 2 numbers"):
        svg_seat_and_lean(ET.fromstring('<svg data-seat="high"/>'), (0, 0, 10, 10), "bench.svg")
    bench = tmp_path / "bench.svg"
    bench.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100" data-seat="100 40">'
                     '<rect x="0" y="40" width="200" height="60" fill="#885522"/></svg>', encoding="utf-8")
    assert read_svg_seat_and_lean(bench, where="bench.svg") == (pytest.approx((0.0, 0.6)), None)   # kept by the sanitiser
    with pytest.raises(VidgenError, match="cannot read"):
        read_svg_seat_and_lean(tmp_path / "none.svg", where="none.svg")


# ----- the character's states (no render) -------------------------------------------------------------------


@pytest.mark.parametrize("look", ["generated", "svg"])
def test_seated_crouched_and_leaning_states(look: str) -> None:
    c = figure("pip") if look == "generated" else built("svg")
    rest = c.state()
    seated = c.seated(rest, 0.12)
    hips = c._hips_y(c._world({**c._poses, **seated.parts}), seated.parts)
    assert hips == pytest.approx(0.12)   # the hips on the seat line (Step 102; was the body's bottom)
    assert 0.12 - 0.03 < c.part_box("body", seated)[1] < 0.12   # its bottom a little lower, in front of the seat
    if look == "generated":
        soles = c.sole_points(seated)
        assert all(y == pytest.approx(0.0, abs=GROUND) for _, y in soles.values())   # feet on the ground ahead
        assert all(soles[f][0] > c.sole_points()[f][0] for f in soles)
        high = c.sole_points(c.seated(rest, 0.4))
        assert all(y > 0.05 for _, y in high.values())   # a high seat: the feet hang
        low = c.lowered(rest, 0.05, stoop=10.0)
        assert flat(c.sole_points(low)) == pytest.approx(flat(c.sole_points()))   # crouched, the feet stay
        assert c.part_box("body", low)[3] < c.part_box("body")[3] and low.parts["body"].angle == -10.0
        assert c.limb_rest("leg_left")[0][1] == pytest.approx(c.hip_height())
        leant = c.leaning(rest)
        assert all(y == pytest.approx(0.0, abs=GROUND) for _, y in c.sole_points(leant).values())
        assert c.part_box("body", leant)[0] < c.part_box("body")[0]   # the back goes back
    else:
        assert c.sole_points() == {} and c.hip_height() is not None
        legs = seated.parts["legs"]
        assert 0 < legs.angle < 80   # one-piece legs turned forward to the ground
        low = c.lowered(rest, 0.05)
        assert low.parts["legs"].scale[1] < 1.0   # shortened so they still reach the ground
    assert np.isfinite(c.set_state(seated).get_all_points()).all()


# ----- the actions on a fake stage (no render) ---------------------------------------------------------------


def stage(*kinds: str) -> tuple[StageFake, Any, dict[str, Any]]:
    pip = figure("pip").shift([-4.0, -2.0, 0.0])
    h = pip.character_height
    props = {}
    for kind, x in zip(kinds, (-3.4, -1.0, 1.5)):
        prop = draw_prop(kind, height=PROP_HEIGHTS[kind] * h, theme=Theme(), name=kind).shift([x, -2.0, 0.0])
        prop.height_factor = PROP_HEIGHTS[kind]
        props[kind] = prop
    scene = StageFake(pip=pip, **props)
    scene.mobjects = [*props.values(), pip]
    return scene, pip, props


def test_sit_on_a_chair_and_stand_up() -> None:
    scene, pip, props = stage("chair")
    chair = props["chair"]
    before = pip.state()
    pip.face("left")
    (anim,) = use("sit_on", to="chair").apply(scene, [target("pip", pip)])
    assert isinstance(anim, BodyMove)
    run([anim])
    seat = chair.seat_point()
    assert pip.facing == "right"   # the way the chair faces, its back behind
    sink = 0.03 * pip.character_height   # the hips on the seat line, the body's bottom a little lower (Step 102)
    assert pip.feet()[0] == pytest.approx(seat[0]) and seat[1] - sink < pip.parts["body"].get_bottom()[1] < seat[1]
    assert pip.sitting_on == "chair" and scene.postures.of("pip") == ("sitting", "chair")
    feet = [pip.foot_point(f) for f in ("left", "right")]
    assert all(f[0] > seat[0] for f in feet)   # the feet in front
    run(use("look_at", to=0.05).apply(scene, [target("pip", pip)]))
    assert pip.facing == "right"   # a look behind does not turn it round
    run(use("pose", to="sitting").apply(scene, [target("pip", pip)]))
    assert seat[1] - sink < pip.parts["body"].get_bottom()[1] < seat[1]   # a pose keeps the body and legs
    standing_x = float(np.mean([f[0] for f in feet]))
    run(use("stand_up").apply(scene, [target("pip", pip)]))
    assert pip.sitting_on is None and scene.postures.of("pip") is None
    assert pip.feet()[0] == pytest.approx(standing_x, abs=1e-6)   # stands up over its feet
    for part in ("body", "leg_left", "leg_left_lower", "leg_right", "leg_right_lower"):
        assert pip.pose_of(part) == before.parts[part], part
    assert use("stand_up").apply(scene, [target("pip", pip)]) == []   # nothing to stand up from


def test_lean_on_a_tree() -> None:
    scene, pip, props = stage("tree")
    tree = props["tree"]
    pip.shift([tree.feet()[0] + 1.0 - pip.feet()[0], 0.0, 0.0])   # right of the tree, facing right
    pip.face("left")
    run(use("lean_on", to="tree").apply(scene, [target("pip", pip)]))
    assert pip.facing == "right" and pip.leaning_on == "tree"   # its back to the tree
    assert pip.parts["body"].get_left()[0] == pytest.approx(tree.lean_edges()[1], abs=1e-6)   # the back on the trunk
    assert pip.pose_of("body").angle > 0   # leaning back
    assert all(abs(pip.foot_point(f)[1] - pip.feet()[1]) < 1e-6 for f in ("left", "right"))


def test_pick_up_and_put_down_crouch_for_a_low_prop() -> None:
    scene, pip, props = stage("box")
    box = props["box"]
    pip.shift([box.feet()[0] - 0.9 - pip.feet()[0], 0.0, 0.0])
    soles = pip.sole_points()
    anims = use("pick_up", to="box").apply(scene, [target("pip", pip)])
    move = anims[0]
    assert isinstance(move, BodyMove)
    for a in anims:
        a.begin()
    for a in anims:
        a.interpolate(0.45)
    assert pip.pose_of("body").shift[1] < 0 and pip.pose_of("leg_left_lower").angle != 0   # knees bent, body lower
    assert np.linalg.norm(pip.hand_point("left")[:2] - box.get_top()[:2]) < 0.05 * pip.character_height   # the hand at the box
    assert flat(pip.sole_points()) == pytest.approx(flat(soles))   # the feet stay
    for a in anims:
        a.interpolate(1.0)
        a.finish()
    assert pip.pose_of("body").shift == (0.0, 0.0) and pip.holding == {"left": "box"}   # up again
    down = use("put_down").apply(scene, [target("pip", pip)])
    assert isinstance(down[0], BodyMove)
    run(down)
    assert pip.pose_of("body").shift == (0.0, 0.0)
    cup = draw_prop("cup", height=0.3, theme=Theme(), name="cup").move_to(pip.hand_point("right"))   # within reach: no crouch
    cup.height_factor = 0.1
    scene.mobs["cup"] = cup
    assert type(use("pick_up", to="cup", hand="right").apply(scene, [target("pip", pip)])[0]) is ArmMove


def test_a_seated_character_does_not_crouch() -> None:
    scene, pip, props = stage("chair", "ball")
    run(use("sit_on", to="chair").apply(scene, [target("pip", pip)]))
    seated = pip.state()
    anims = use("pick_up", to="ball").apply(scene, [target("pip", pip)])
    assert type(anims[0]) is ArmMove
    run(anims)
    assert {p: pip.pose_of(p) for p in ("body", "leg_left")} == {p: seated.parts[p] for p in ("body", "leg_left")}


# ----- validate ---------------------------------------------------------------------------------------------


def seat_project(make_project, beats: list[dict[str, Any]]) -> Project:
    params = {"idle": False, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}],
              "props": [{"prop": "chair", "at": 0.3}, {"prop": "tree", "at": 0.7}, {"prop": "ball", "at": 0.5}]}
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))


def test_validate_sitting_and_leaning(make_project) -> None:
    good = seat_project(make_project, [
        {"text": "Pip sits down and kit leans on the tree.", "actions": [{"sit_on": "pip", "to": "chair"}, {"lean_on": "kit", "to": "tree"}]},
        {"text": "Both get up and walk.", "actions": [{"stand_up": ["pip", "kit"]}, {"walk_to": "pip", "to": 0.5, "at": 0.5}]},
    ])
    assert check_project(good) == []
    bad = seat_project(make_project, [{"text": "Hello.", "actions": [
        {"sit_on": "pip", "to": "tree"}, {"lean_on": "pip", "to": "ball"}, {"sit_on": "pip", "to": "stool"},
    ]}])
    problems = check_project(bad)
    where = "scenes[0].beats[0].actions"
    for start in (f"{where}[0].to: 'tree' has no seat (seats: chair, rock, box, sofa, armchair, bed, desk, bench, log, or an SVG prop with data-seat)",
                  f"{where}[1].to: 'ball' has no lean", f"{where}[2].to: 'stool' is not a prop of the scene"):
        assert any(p.startswith(start) for p in problems), (start, problems)
    order = seat_project(make_project, [
        {"text": "Kit sits on the chair from afar.", "actions": [{"sit_on": "kit", "to": "chair"}]},
        {"text": "Pip sits, then walks off.", "actions": [{"sit_on": "pip", "to": "chair"}, {"walk_to": "pip", "to": 0.5, "at": 0.5}]},
        {"text": "Kit stands.", "actions": [{"stand_up": "kit"}, {"pick_up": "pip", "to": "chair", "at": 0.5}]},
    ])
    far, walk, stand, chair = check_project(order)
    assert far.startswith(f"scenes[0].beats[0].actions[0].to: kit is") and "walk_to first" in far
    assert walk == "scenes[0].beats[1].actions[1].target: pip sits on 'chair' then; stand_up first (- stand_up: pip)"
    assert stand.startswith("scenes[0].beats[2].actions[0].target: kit neither sits nor leans then")
    assert chair.startswith("scenes[0].beats[2].actions[1].to: pip sits on 'chair' then")


# ----- the planner does not turn a seated character -----------------------------------------------------------


def test_a_seated_listener_does_not_turn_to_look_behind() -> None:
    props = StageFrame(FW, FH, FW, 0.0, DUO.places, {"chair": -3.6, "rock": -3.2}, seat_facings={"chair": "left"})
    looks = frozenset({"looks"})
    speak = line("b1", "I think so.", ("kit",), kinds=looks)
    assert directed([speak], stage=props)["b1"] == [{"look_at": "pip", "to": "kit"}, {"look_at": "kit", "to": "pip"}]
    sat = directed([line("b0", "Pip sits.", (), [{"sit_on": "pip", "to": "chair"}], kinds=looks), speak], stage=props)
    assert sat["b1"] == [{"look_at": "kit", "to": "pip"}]   # pip faces left on the chair: kit is behind it
    rock = directed([line("b0", "Pip sits.", (), [{"sit_on": "pip", "to": "rock"}], kinds=looks), speak], stage=props)
    assert {"look_at": "pip", "to": "kit"} in rock["b1"]   # on a rock it keeps facing right: kit is ahead


# ----- render -------------------------------------------------------------------------------------------------


@pytest.mark.render
def test_sitting_on_a_stage(make_project, tmp_path: Path) -> None:
    """pip sits on the chair (the dump says so), kit leans on the tree; then both stand up."""
    project = seat_project(make_project, [
        {"text": "Pip sits down and kit leans on the tree.", "actions": [{"sit_on": "pip", "to": "chair"}, {"lean_on": "kit", "to": "tree"}]},
        {"text": "Both get up again.", "actions": [{"stand_up": ["pip", "kit"]}]},
    ])
    from vidgen.introspect import LayoutRecorder

    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "park", tmp_path / "media", recorder)
    ends = [f for f in recorder.frames if "mid" not in f]
    first = {o["name"]: o for o in ends[0]["objects"] if o["name"]}
    assert first["pip"]["sitting_on"] == "chair" and first["kit"]["leaning_on"] == "tree"
    last = {o["name"]: o for o in ends[-1]["objects"] if o["name"]}
    assert "sitting_on" not in last["pip"] and "leaning_on" not in last["kit"]
    assert first["pip"]["bbox"][1] > last["pip"]["bbox"][1]   # seated, pip's head is lower (y down in pixels)
    assert first["pip"]["bbox"][3] == pytest.approx(last["pip"]["bbox"][3], abs=1.0)   # its feet on the ground (Step 102)
    assert any(f.get("mid", "").startswith("sit_on") for f in recorder.frames)
    assert scene.cast["pip"].sitting_on is None
