"""Step 111: moving in depth and the front view (DESIGN.md §69.44): depth paths, the draw-order
switch time and place, the front view's part layout and turning to it (without rendering); a
walk in depth and a front-facing character on a tiny rendered stage."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES, figure, run, target, use
from test_cartoon_character import COLORS
from test_cartoon_moving import StageFake
from test_cartoon_stage import render_with_layout
from vidgen.cartoon.acting import (
    FRONT_STEP_SHORTEN,
    TURN_SQUASH,
    WALK_KNEE_DEGREES,
    camera_look,
    depth_switch_times,
    look_pose,
    turn_squash,
    walk_cycle,
    walk_progress,
    walk_seconds,
    walk_share_seconds,
    walk_time_at,
)
from vidgen.cartoon.cast import front_view_warnings
from vidgen.cli import check_project
from vidgen.cartoon.character import FRONT_DRAW_ORDER, Character, look_parts
from vidgen.cartoon.generator import generate_parts
from vidgen.cartoon.holding import HandlingStep, holding_problems
from vidgen.cartoon.motion import Phases
from vidgen.cartoon.shading import ShadowCaster
from vidgen.cartoon.stage import (
    DEPTH_WALK_HEIGHTS,
    depth_along,
    depth_crossings,
    depth_scale,
    depth_slot,
    depth_walk_distance,
    facing_sign,
    walk_destination,
)
from vidgen.cartoon.transition import PoseChange, Walk, walking_state
from vidgen.config import CharacterLook, LintRules, parse_config
from vidgen.lint import StillContext
from vidgen.introspect import LayoutRecorder
from vidgen.lint.rules import RULES
from vidgen.project import Project

LOOK = CharacterLook(body="bean", nose="triangle", hair="long", accessories=["glasses"])


def both_views(name: str = "pip") -> Character:
    """A generated character with its side and front views, not idling."""
    return Character(look_parts(LOOK, COLORS), front=look_parts(LOOK, COLORS, front=True), name=name)


# ----- depth paths and the draw order (no manim) -------------------------------------------------------


def test_depth_path() -> None:
    assert depth_walk_distance(3.0, 0.2, 0.2, 3.0) == 3.0   # across only: as before
    assert depth_walk_distance(0.0, 0.0, 0.5, 3.0) == pytest.approx(0.5 * DEPTH_WALK_HEIGHTS * 3.0)
    assert depth_walk_distance(3.0, 0.5, 0.0, 2.0) == pytest.approx(np.hypot(3.0, 0.5 * DEPTH_WALK_HEIGHTS * 2.0))
    assert [depth_along(0.2, 0.8, s) for s in (0.0, 0.5, 1.0, 1.5)] == pytest.approx([0.2, 0.5, 0.8, 0.8])
    assert walk_destination({"to": "left"}) == ("left", None)
    assert walk_destination({"to": {"mark": 0.3, "depth": 0.6}}) == (0.3, 0.6)
    assert walk_destination({"depth": 0.4}) == (None, 0.4)
    assert walk_destination({"to": {"depth": 0.1}}) == (None, 0.1)
    assert (facing_sign("right"), facing_sign("left"), facing_sign("front"), facing_sign("front", front=0.0)) == (1.0, -1.0, 1.0, 0.0)


def test_draw_order_switch_times() -> None:
    others = {"tree": 0.5, "kit": 0.3, "rock": 0.95, "box": 0.0}
    assert depth_crossings(0.0, 0.8, others) == [(pytest.approx(0.375), "kit"), (pytest.approx(0.625), "tree")]   # not box (start), not rock
    assert [n for _, n in depth_crossings(0.8, 0.0, others)] == ["tree", "kit"]   # coming forward: nearest last
    assert depth_crossings(0.4, 0.4, others) == []
    for share in (0.0, 0.05, 0.3, 0.5, 0.9, 1.0):
        assert walk_progress(walk_time_at(share)) == pytest.approx(share)
    times = depth_switch_times(0.0, 0.8, others, 4.0)
    assert [n for _, n in times] == ["kit", "tree"]
    for seconds, name in times:   # at the switch, the walker's depth is the other's
        assert depth_along(0.0, 0.8, walk_progress(seconds / 4.0)) == pytest.approx(others[name])
    phases = Phases(0.1, 0.2)   # a wind-up and a settle (cartoon_motion): the feet move in between
    ((seconds, _),) = depth_switch_times(0.0, 1.0, {"tree": 0.5}, 10.0, phases)
    assert seconds == pytest.approx(walk_share_seconds(0.5, 10.0, phases)) and seconds == pytest.approx(1.0 + 0.5 * 7.0)


def test_depth_slot() -> None:
    stage = [(0.7, False), (0.5, False), (0.5, True), (0.2, True), (0.0, False)]   # back to front: tree, box, kit, pip, rock
    assert depth_slot(0.0, stage, 0) == 5   # at the front: after everything deeper, after the prop at its depth
    assert depth_slot(0.6, stage, 4) == 1   # between the tree and the box
    assert depth_slot(0.5, stage, 1) == 2   # in front of the box (a prop at its depth), by kit
    assert depth_slot(0.5, stage, 3) == 3   # kit is a character at its depth: it keeps its place
    assert depth_slot(0.9, stage, 5) == 0
    assert depth_slot(0.3, [(0.1, True), (0.6, False)], 0) == 2   # others out of order: after the deeper one


def test_stage_moves_the_walker_with_what_it_holds() -> None:
    from vidgen.scenes.stage import Stage

    def thing(name: str, depth: float, held_by: str | None = None) -> Any:
        return SimpleNamespace(name=name, stage_depth=depth, held_by=held_by)

    pip = figure()
    pip.stage_depth = 0.6
    tree, cup, kit, rug = thing("tree", 0.5), thing("cup", 0.0, held_by="pip"), thing("kit", 0.2), thing("rug", 0.0)
    scene = SimpleNamespace(mobjects=[tree, kit, pip, cup, rug], cast={"pip": pip, "kit": kit}, props={"tree": tree, "cup": cup, "rug": rug},
                            _shadows_first=lambda: None)
    assert Stage._keep_depth_order(scene, pip)
    assert scene.mobjects == [pip, cup, tree, kit, rug]   # behind the tree, its cup right after it
    assert not Stage._keep_depth_order(scene, pip)   # in its place: nothing moves
    pip.stage_depth = 0.0
    assert Stage._keep_depth_order(scene, pip) and scene.mobjects == [tree, kit, rug, pip, cup]   # in front of the rug at its depth
    shadows = SimpleNamespace(casters=[SimpleNamespace(mobject=pip), SimpleNamespace(mobject=kit)])
    scene = SimpleNamespace(mobjects=[pip, tree, shadows, kit], _moving_shadows=shadows)
    Stage._shadows_first(scene)
    assert scene.mobjects == [shadows, pip, tree, kit]   # the walker's shadow is drawn under it, not over the tree


# ----- the front view (no render) ---------------------------------------------------------------------


def _middle_x(parts: list[Any], name: str, shape: str | None = None) -> float:
    part = next(p for p in parts if p.name == name)
    drawing = part.shapes[shape or next(iter(part.shapes))]
    return float(drawing.get_center()[0])


def test_front_view_part_layout() -> None:
    side, front = generate_parts(LOOK, COLORS), generate_parts(LOOK, COLORS, front=True)
    assert [p.name for p in front] == [p.name for p in side]
    assert all(list(f.shapes) == list(s.shapes) for f, s in zip(front, side))   # the same shapes: poses, visemes work
    for part in ("eyes", "brows", "mouth", "head", "body", "accessory"):   # symmetric about the middle
        assert _middle_x(front, part) == pytest.approx(0.0, abs=2e-3), part
    for viseme in ("A", "O", "M"):
        assert _middle_x(front, "mouth", viseme) == pytest.approx(0.0, abs=1e-3)
    assert _middle_x(side, "eyes") > 0.01 and _middle_x(side, "mouth") > 0.01   # from the side the face sits forward
    arms = [_middle_x(front, arm) for arm in ("arm_left", "arm_right")]
    assert arms[0] == pytest.approx(-arms[1]) and arms[0] > 0   # an arm at each side
    temples = len(next(p for p in front if p.name == "accessory").shapes["default"].submobjects)
    assert temples == len(next(p for p in side if p.name == "accessory").shapes["default"].submobjects) + 1   # a temple each side
    assert FRONT_DRAW_ORDER["arm_right"] > FRONT_DRAW_ORDER["body"]


def test_facing_front_shows_the_front_view() -> None:
    c = both_views()
    side_order = c.draw_order
    assert c.has_front_view and c.facing == "right" and side_order.index("arm_right") < side_order.index("body")
    shown = {id(m) for m in c.get_family()[2:] if len(m.points)}   # not the character and its anchor
    c.face("front")
    assert c.facing == "front" and c.side_facing == "right" and c.order_changes == 1
    assert c.draw_order.index("arm_right") > c.draw_order.index("body")   # both arms in front of the body
    assert c.submobjects[1:] == [c.parts[n] for n in c.draw_order]
    front_shown = {id(m) for m in c.get_family()[2:] if len(m.points)}
    assert not shown & front_shown   # nothing of the side view is drawn
    eyes = c.parts["eyes"].get_center()[0] - c.feet()[0]
    assert eyes == pytest.approx(0.0, abs=1e-3)   # the face in the middle, not mirrored
    assert c.has_trails   # long hair trails in the wind from the front too
    c.set_expression("angry").swap("mouth", "O")
    assert c.shown_shape("mouth") == "O" and c.shown_shape("brows") == "angry"
    c.turn()
    assert c.facing == "right" and c.order_changes == 2 and c.draw_order == side_order
    c.face("left").face("front").turn()
    assert c.facing == "left"   # back to the side it faced before
    plain = figure()   # an SVG character has no front view: it keeps its side
    assert not Character(generate_parts(LOOK, COLORS)).has_front_view
    side = Character(generate_parts(LOOK, COLORS), facing="front")
    assert side.facing == "right" and side.order_changes == 0
    assert plain.has_front_view   # a generated character from the cast has one


def test_turning_to_the_front_swaps_halfway_and_narrows() -> None:
    assert turn_squash(0.0) == turn_squash(1.0) == 1.0 and turn_squash(0.5) == pytest.approx(1.0 - TURN_SQUASH)
    c = both_views()
    width = c.width
    turn = PoseChange(c, facing="front", run_time=0.4)
    turn.begin()
    turn.interpolate(0.45)
    assert c.facing == "right" and c.width < width
    turn.interpolate(0.55)
    assert c.facing == "front" and c.width < width
    turn.interpolate(1.0)
    turn.finish()
    assert c.facing == "front" and c._squash == (1.0, 1.0)
    assert PoseChange(c, facing="left")._turns_front   # from the front to a side
    assert not PoseChange(both_views(), facing="left")._turns_front   # side to side: a mirror, no narrowing


def test_look_and_camera_from_the_front() -> None:
    assert camera_look("front").eyes_shift == (0.0, 0.0)
    assert look_pose(0.01, 2.0, "front").facing == "front" and look_pose(0.01, 2.0, "front").eyes_shift[0] == 0.0
    assert look_pose(2.0, 0.0, "front").facing == "right"   # to the side: it turns


def test_front_walking_steps_towards_the_camera() -> None:
    c = both_views().face("front")
    base = c.state()
    cycle = walk_cycle(0.0)   # the left leg passing the other: its knee bent most
    walking = walking_state(base, cycle, "front")
    assert walking.facing == "front"
    assert walking.parts["leg_left"].angle == base.parts["leg_left"].angle   # no swing sideways
    assert walking.parts["leg_left"].scale[1] == pytest.approx(1.0 - FRONT_STEP_SHORTEN * cycle.knee_bends[0] / WALK_KNEE_DEGREES)
    assert walking.parts["leg_right"].scale == base.parts["leg_right"].scale
    assert walking.parts["body"].shift[1] == pytest.approx(cycle.body_lift)


# ----- walking in depth (no render) -----------------------------------------------------------------------


def feet_y(depth: float) -> float:
    return -2.0 + 1.0 * depth


def test_a_walk_in_depth_grows_shrinks_and_keeps_its_facing() -> None:
    from manim import Square

    c = figure().shift([-2.0, -2.0, 0.0])
    c.motion = "none"
    c.stage_depth, c.ground_y = 0.0, -2.0
    cup = Square(side_length=0.2).move_to(c.hand_point("left"))
    cup.set_stroke(width=4.0)
    height, stroke = c.character_height, c.parts["body"].family_members_with_points()[0].get_stroke_width()
    walk = Walk(c, -2.0, depth=0.6, feet_y=feet_y, carried=[cup])
    assert walk.run_time == pytest.approx(walk_seconds(depth_walk_distance(0.0, 0.0, 0.6, height)))
    assert walk.heights == pytest.approx(0.6 * DEPTH_WALK_HEIGHTS)
    walk.begin()
    seen = []
    for k in range(31):
        walk.interpolate(k / 30)
        seen.append((c.stage_depth, float(c.feet()[1]), c.character_height))
    walk.finish()
    depths = [d for d, _, _ in seen]
    assert depths == sorted(depths) and depths[-1] == pytest.approx(0.6)
    assert all(y == pytest.approx(feet_y(d)) for d, y, _ in seen)   # on the ground line at its depth all the way
    assert all(h == pytest.approx(height * depth_scale(d)) for d, _, h in seen)
    assert c.facing == "right" and c.feet()[0] == pytest.approx(-2.0)   # straight back: facing kept
    assert c.ground_y == pytest.approx(-1.4)
    factor = depth_scale(0.6)
    assert c.parts["body"].family_members_with_points()[0].get_stroke_width() == pytest.approx(stroke * factor)
    assert cup.width == pytest.approx(0.2 * factor) and cup.get_stroke_width() == pytest.approx(4.0 * factor)
    with pytest.raises(TypeError, match="feet_y"):
        Walk(c, 0.0, depth=0.2)


def test_shadow_follows_the_ground_and_size() -> None:
    walker = SimpleNamespace(feet=lambda: np.array([1.0, -1.4, 0.0]), standing_height=1.5, ground_y=-1.4)
    caster = ShadowCaster(walker, -2.0, 0.9, 3.0, grows=True)
    shadow = caster.ellipse(1.0)
    assert shadow.y == pytest.approx(-1.4) and shadow.width == pytest.approx(0.45)   # half as tall: half as wide
    still = ShadowCaster(SimpleNamespace(feet=lambda: np.array([1.0, -2.0, 0.0])), -2.0, 0.9, 3.0)
    assert still.ellipse(1.0).y == -2.0 and still.ellipse(1.0).width == pytest.approx(0.9)


class DepthStageFake(StageFake):
    """StageFake with a ground line per depth and a record of the walks in depth."""

    def __init__(self, **mobs: Any) -> None:
        super().__init__(**mobs)
        self.walks: list[Any] = []

    def feet_y_at(self, depth: float) -> float:
        return feet_y(depth)

    def walk_in_depth(self, character: Any, walk: Any) -> None:
        self.walks.append((character.name, walk.to_depth))


def test_walk_to_with_depth() -> None:
    pip = figure().shift([-4.0, -2.0, 0.0])
    pip.motion = "none"
    pip.stage_depth = 0.0
    scene = DepthStageFake(pip=pip)
    deep = use("walk_to", to={"mark": "centre", "depth": 0.5})
    expected = walk_seconds(depth_walk_distance(4.0, 0.0, 0.5, pip.character_height))
    assert deep.run_time_for(scene, [target("pip", pip)]) == pytest.approx(expected)
    run(deep.apply(scene, [target("pip", pip)]))
    assert pip.feet() == pytest.approx([0.0, feet_y(0.5), 0.0]) and pip.stage_depth == 0.5 and scene.walks == [("pip", 0.5)]
    run(use("walk_to", depth=0.0, speed=4.0).apply(scene, [target("pip", pip)]))
    assert pip.stage_depth == 0.0 and pip.feet()[0] == pytest.approx(0.0) and pip.facing == "right"   # straight forward
    assert use("walk_to", depth=0.0).apply(scene, [target("pip", pip)]) == []   # there already
    run(use("run_to", to="left", depth=0.2).apply(scene, [target("pip", pip)]))
    assert pip.stage_depth == 0.2 and pip.facing == "left"


def test_walk_to_problems(make_project) -> None:
    beats = [{"text": "Pip walks about.", "actions": [
        {"walk_to": "pip", "to": {"mark": "left", "depth": 0.3}}, {"run_to": "pip", "depth": 0.1},
        {"walk_to": "pip", "depth": 0.6}, {"walk_to": "pip"}, {"walk_to": "pip", "to": {"mark": "left", "depth": 0.3}, "depth": 0.2},
        {"walk_to": "pip", "to": {"mark": "nowhere"}}, {"walk_to": "pip", "to": {}},
    ]}]
    params = {"characters": ["pip"], "room": {"depth": 0.4}}
    project = Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=[{"id": "den", "type": "stage", "params": params, "beats": beats}])))
    where = "scenes[0].beats[0].actions"
    problems = sorted(check_project(project))
    assert problems[:3] == [
        f"{where}[2].depth: depth 0.6 is behind the room's wall (at depth 0.4); walk to at most 0.4",
        f"{where}[3].to: say where it walks: to (a mark or an x, or {{mark, depth}}) and / or depth",
        f"{where}[4].depth: give the depth once: in to ({{mark, depth}}) or as depth, not both",
    ]
    assert problems[3].startswith(f"{where}[5].to: unknown mark 'nowhere'")
    assert problems[4] == f"{where}[6].to: give the place a mark and / or a depth: {{mark: right, depth: 0.4}}"
    assert len(problems) == 5


# ----- validate and lint -------------------------------------------------------------------------------------


def test_sitting_at_another_depth_needs_a_walk_there_first() -> None:
    def problems(*steps: tuple[str, str, dict[str, Any]]) -> list[tuple[str, str]]:
        made = [HandlingStep(f"beats[0].actions[{k}]", a, (who,), o) for k, (a, who, o) in enumerate(steps)]
        return holding_problems(made, characters={"pip": (0.0, 3.0), "kit": (2.0, 3.0)}, props={"sofa": 0.5, "cup": 0.3},
                                place_x=lambda p: (p - 0.5) * 16 if isinstance(p, float) else 0.0, to_fraction=lambda x: x / 16 + 0.5,
                                depths={"pip": 0.0, "kit": 0.4, "sofa": 0.4, "cup": 0.0})

    (far,) = problems(("sit_on", "pip", {"to": "sofa"}))
    assert far[1] == "pip stands at depth 0 and 'sofa' at depth 0.4; walk_to first (- walk_to: pip, to: {mark: 0.47, depth: 0.4})"
    assert problems(("walk_to", "pip", {"depth": 0.4}), ("sit_on", "pip", {"to": "sofa"})) == []
    assert problems(("walk_to", "pip", {"to": {"mark": 0.53, "depth": 0.42}}), ("sit_on", "pip", {"to": "sofa"})) == []
    (give,) = problems(("pick_up", "pip", {"to": "cup"}), ("give", "pip", {"to": "kit"}))
    assert "pip stands at depth 0 and kit at depth 0.4" in give[1]
    (pick,) = problems(("walk_to", "kit", {"to": {"mark": 0.7}}), ("pick_up", "kit", {"to": "cup"}))
    assert "kit stands at depth 0.4 and 'cup' at depth 0" in pick[1]


def test_lint_overlap_rules_use_depth() -> None:
    def obj(name: str, box: list[float], depth: float = 0.0, walked: str | None = None) -> dict[str, Any]:
        found = {"id": name, "kind": "character", "name": name, "path": f"Stage/{name}", "bbox": box, "opacity": 1.0}
        return {**found, **({"depth": depth} if depth else {}), **({"walked_in": walked} if walked else {})}

    def check(rule: str, objects: list[dict[str, Any]]) -> list[Any]:
        ctx = StillContext(layout={"width": 854, "height": 480}, frame={"beat": "b2", "objects": objects}, objects=objects)
        return list(RULES[rule].check(ctx, getattr(LintRules(), rule)))

    kit = obj("kit", [500, 100, 600, 400])
    assert len(check("character_overlap", [obj("pip", [520, 120, 610, 380]), kit])) == 1
    assert check("character_overlap", [obj("pip", [520, 120, 610, 380], depth=0.4), kit]) == []   # one behind the other
    assert len(check("character_overlap", [obj("pip", [520, 120, 610, 380], depth=0.1), kit])) == 1
    assert check("walk_overlap", [obj("pip", [520, 150, 600, 350], depth=0.5, walked="b2"), kit]) == []


def test_validate_warns_about_front_views_of_svg_characters() -> None:
    cast = [{"name": "pip", "look": {"body": "bean"}}, {"name": "sprout", "look": {"svg": "assets/sprout.svg"}}]
    scenes = [{"id": "s", "type": "stage", "params": {"characters": [{"name": "sprout", "facing": "front"}, {"name": "pip", "facing": "front"}]},
               "beats": [{"text": "Hi.", "actions": [{"turn": "*", "to": "front"}, {"turn": "pip"}]}]}]
    config = parse_config(minimal_config(characters=cast, scenes=scenes))
    assert front_view_warnings(config) == [
        "scenes[0].params.characters[0]: character 'sprout' is drawn from an SVG file and has no front view; it faces its side",
        "scenes[0].beats[0].actions[0]: character 'sprout' is drawn from an SVG file and has no front view; the turn leaves it as it is",
    ]


# ----- render ------------------------------------------------------------------------------------------------------


@pytest.mark.render
def test_walking_behind_a_tree_and_a_front_view_on_a_stage(make_project, tmp_path: Path) -> None:
    """pip walks behind the tree to the back of the stage (drawn behind it, smaller, its shadow
    under it there); kit faces the viewer, then turns to its side."""
    params = {"idle": False, "props": [{"prop": "tree", "at": 0.45, "depth": 0.5}],
              "characters": [{"name": "pip", "at": 0.3}, {"name": "kit", "at": "right", "facing": "front"}]}
    scenes = [{"id": "yard", "type": "stage", "params": params, "beats": [
        {"text": "Pip walks round to the back of the yard, behind the tree.", "actions": [{"walk_to": "pip", "to": {"mark": 0.5, "depth": 0.9}, "speed": 8}]},
        {"text": "Kit turns to look at the tree.", "actions": [{"turn": "kit", "to": "left"}]},
    ]}]
    project = Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "yard", tmp_path / "media", recorder)
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    stills = [{o["name"]: o for o in frame["objects"] if o["name"]} for frame in recorder.frames]
    middle, end, turned = stills   # half-way through the walk, then the two beats' ends
    assert 0.5 < middle["pip"]["depth"] < 0.9 and middle["pip"]["order"] < middle["tree"]["order"]   # past the tree's depth: behind it
    assert end["pip"]["depth"] == 0.9 and end["kit"]["facing"] == "front" and "depth" not in end["kit"]
    assert turned["kit"]["facing"] == "left"
    assert end["pip"]["order"] < end["tree"]["order"] < end["kit"]["order"]   # behind the tree now
    assert pip.stage_depth == 0.9 and pip.feet()[1] == pytest.approx(scene.feet_y_at(0.9)) and scene.grounds["pip"] == pytest.approx(scene.feet_y_at(0.9))
    assert pip.standing_height == pytest.approx(scene.params.size * min(scene.frame_width, scene.frame_height) * depth_scale(0.9))
    caster = next(c for group in scene.shadows for c in group.casters if c.mobject is pip)
    assert caster.ellipse(1.0).y == pytest.approx(scene.feet_y_at(0.9))   # its shadow on the ground there
    assert kit.facing == "left" and kit.side_facing == "left" and kit.draw_order.index("arm_right") < kit.draw_order.index("body")


@pytest.mark.render
def test_props_at_the_depth_a_walker_leaves_stay_drawn(make_project, tmp_path: Path, monkeypatch) -> None:
    """pip walks from the wall's depth to the front past the armchair: every frame still draws the
    fridge and the door at the wall (they were redrawn while pip stood at their depth, and vanished
    once pip's crossing of the armchair rebuilt Manim's list without them)."""
    from manim.renderer.cairo_renderer import CairoRenderer

    params = {"idle": False, "room": {"doors": [0.1]}, "props": [{"prop": "fridge", "at": 0.9, "against": "wall"}, {"prop": "armchair", "at": 0.3, "depth": 0.2},
                                                                 {"prop": "picture", "at": 0.3}, {"prop": "rug", "at": 0.3, "depth": 0.1}],
              "characters": [{"name": "pip", "at": 0.6, "depth": 0.4}]}
    scenes = [{"id": "den", "type": "stage", "params": params, "beats": [
        {"text": "Pip walks from the wall to the front of the room.", "actions": [{"walk_to": "pip", "to": {"mark": 0.6, "depth": 0.0}, "speed": 4}]}]}]
    project = Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))
    missing: list[tuple[float, str]] = []
    in_front: list[bool] = []   # pip drawn after the armchair, frame by frame
    render = CairoRenderer.render

    def checking(self: Any, scene: Any, time: float, moving: Any = None) -> None:
        pip, armchair = scene.cast["pip"], scene.props["armchair"]
        if moving and pip in scene.mobjects and armchair in scene.mobjects:
            in_front.append(scene.mobjects.index(pip) > scene.mobjects.index(armchair))
            drawn = {id(m) for mob in [*moving, *scene.static_mobjects] for m in mob.get_family()}
            missing.extend((float(self.time), p.name) for p in scene.props.values() if p in scene.mobjects and not all(id(m) in drawn for m in p.family_members_with_points()))
        render(self, scene, time, moving)

    monkeypatch.setattr(CairoRenderer, "render", checking)
    scene, objects = render_with_layout(project, "den", tmp_path / "media")
    assert scene.cast["pip"].stage_depth == 0.0 and not in_front[0] and in_front[-1]   # it crossed the armchair's depth
    assert missing == []
    props = {o["name"]: o for o in objects if o["kind"] == "prop"}   # the keys prop_overlap reads
    assert (props["fridge"]["prop"], props["fridge"]["depth"], props["armchair"]["depth"]) == ("fridge", 0.4, 0.2)
    assert props["door"]["prop"] == "door" and "raised" not in props["door"] and "flat" not in props["door"]
    assert props["picture"]["raised"] and props["rug"]["flat"] and "raised" not in props["rug"]


@pytest.mark.render
def test_a_character_behind_a_house_does_not_show_through_it_as_the_scene_fades_out(make_project, tmp_path: Path, monkeypatch) -> None:
    """pip walks to behind the house, where the house hides it: the frames of the scene's fade-out
    (its outro) are the same as without pip. (Each thing used to fade on its own, so the fading
    house let pip's outline show through it.)"""
    from manim.scene.scene_file_writer import SceneFileWriter

    frames: list[np.ndarray] = []
    write = SceneFileWriter.write_frame

    def keeping(self: Any, frame: Any, num_frames: int = 1) -> None:
        frames.extend([np.asarray(frame).astype(int)] * num_frames)
        write(self, frame, num_frames)

    monkeypatch.setattr(SceneFileWriter, "write_frame", keeping)
    outros = []
    for folder, cast in (("with_pip", [{"name": "pip", "at": 0.2}, {"name": "kit", "at": 0.9}]), ("without", [{"name": "kit", "at": 0.9}])):
        params = {"idle": False, "props": [{"prop": "house", "at": 0.5, "depth": 0.4, "scale": 1.4}], "characters": cast}
        walk = [{"walk_to": "pip", "to": {"mark": 0.5, "depth": 0.9}, "speed": 8}] if folder == "with_pip" else []
        scenes = [{"id": "lane", "type": "stage", "params": params, "beats": [{"text": "Pip walks round to the back of the house.", "actions": walk}]}]
        project = Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes), folder=folder))
        frames.clear()
        scene, _ = render_with_layout(project, "lane", tmp_path / folder)
        outros.append(frames[-round(scene.outro * 5) - 1:])   # from the last frame before it
    assert scene.cast["kit"] and len(outros[0]) == len(outros[1]) >= 3
    assert int(np.abs(outros[0][0] - outros[1][0]).max()) <= 2   # the house hides pip
    assert max(int(np.abs(a - b).max()) for a, b in zip(*outros)) <= 2
