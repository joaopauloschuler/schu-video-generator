"""The cartoon host pointing and reacting (DESIGN.md §71.1, §71.2): the pointing and moving
geometry, the host actions' checks, the scene types' reveal steps, the automatic-directing planner,
and one tiny render with a point, a reaction, a move and an exit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_cartoon_stage import render_with_layout
from test_lint import check
from vidgen import extensions, registry
from vidgen.cartoon.directing import project_directions
from vidgen.cartoon.host import HAND_REACH_OUT, facing_for, hand_goal, host_move_plan, pointed_spot
from vidgen.cartoon.host_directing import HostBeat, RevealStep, has_error_text, plan_host_directions, starts_present, value_trend
from vidgen.cli import check_project
from vidgen.config import ActionConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.project import Project

CHARACTERS = [{"name": "dot"}, {"name": "kit"}]


def bullets(scene_id: str = "steps", beats: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    beats = beats or [{"text": "First beat here."}, {"text": "Second beat here."}, {"text": "Third beat here."}]
    return {"id": scene_id, "type": "bullets", "params": {"items": ["One thing", "Another thing", "A third thing"]}, "beats": beats, **extra}


def config(scenes: list[dict[str, Any]] | None = None, **top: Any) -> dict[str, Any]:
    return {"title": "Host", "characters": CHARACTERS, "host": "dot", "scenes": scenes or [bullets()], **top}


def act(data: dict[str, Any]) -> ActionConfig:
    return ActionConfig.model_validate(data)


# ----- geometry ----------------------------------------------------------------------------------------


def test_the_host_points_at_the_edge_of_the_box_nearest_it() -> None:
    box = (-5.0, 1.0, -1.0, 2.0)
    assert pointed_spot((4.0, 0.0), box) == (-1.0, 1.0)     # right of and below it: the bottom right corner
    assert pointed_spot((4.0, 1.5), box) == (-1.0, 1.5)     # level with it: its right edge
    assert pointed_spot((-3.0, 4.0), box) == (-3.0, 2.0)    # above it: its top edge


def test_the_pointing_hand_stays_in_the_hosts_room() -> None:
    room = (3.0, -3.5, 6.5, 3.5)
    goal = hand_goal((4.5, 0.0), (-1.0, 1.0), room)
    assert goal[0] == pytest.approx(3.0 - HAND_REACH_OUT)           # stopped at the room's inner edge
    slope = (1.0 - 0.0) / (-1.0 - 4.5)
    assert goal[1] == pytest.approx(slope * (goal[0] - 4.5))        # on the line to the target
    assert hand_goal((4.5, 0.0), (4.0, 0.5), room) == (4.0, 0.5)    # within reach of the room: there
    assert hand_goal((1.0, 0.0), (-1.0, 0.0), room) == (1.0, 0.0)    # a shoulder outside the room stays
    below = hand_goal((5.0, -2.0), (0.0, 3.0), (-6.5, -3.5, 6.5, -1.0))   # a band below the content: up to its top
    assert below[1] == pytest.approx(-1.0 + HAND_REACH_OUT)


def test_a_move_mirrors_the_host_and_slides_the_content() -> None:
    area = (-6.5, -3.5, 6.5, 3.5)
    plan = host_move_plan(area, 5.0, (3.5, -3.5, 6.5, 3.5), "right", False, "other_side")
    assert plan is not None and plan.side == "left" and plan.feet_x == pytest.approx(-5.0)
    assert plan.reserve == pytest.approx((-6.5, -3.5, -3.5, 3.5)) and plan.content_shift == pytest.approx(3.0)
    back = host_move_plan(area, -5.0, plan.reserve, "left", False, "right")
    assert back is not None and back.content_shift == pytest.approx(-3.0) and back.reserve == pytest.approx((3.5, -3.5, 6.5, 3.5))
    assert host_move_plan(area, 5.0, (3.5, -3.5, 6.5, 3.5), "right", False, "right") is None   # there already
    band = host_move_plan(area, 5.0, (-6.5, -3.5, 6.5, -1.0), "right", True, "other_side")       # below the content: only the host walks
    assert band is not None and band.content_shift == 0.0 and band.reserve == (-6.5, -3.5, 6.5, -1.0) and band.feet_x == pytest.approx(-5.0)
    assert (facing_for("left", "auto"), facing_for("right", "auto"), facing_for("left", "front")) == ("right", "left", "front")


# ----- checks ----------------------------------------------------------------------------------------


def test_host_action_problems() -> None:
    beats = [
        {"text": "One.", "actions": [{"host_move": "other_side"}, {"host_exit": "left"}]},
        {"text": "Two.", "actions": [{"host_react": "hapy"}]},
    ]
    with pytest.raises(VidgenError) as exc:
        parse_config(config([bullets(beats=beats), bullets("bare", host=False, beats=[{"text": "Hi.", "actions": [{"host_point": "item1"}]}])]))
    lines = str(exc.value)
    assert "scenes[0].beats[0].actions[1]: host_exit: one host move per beat" in lines
    assert "scenes[0].beats[1].actions[0].target: character 'dot': unknown expression 'hapy'; did you mean 'happy'" in lines
    assert "scenes[1].beats[0].actions[0]: host_point: scene 'bare' has no host" in lines


def test_validate_checks_host_action_targets_and_scene_types(make_project) -> None:
    stage = {"id": "park", "type": "stage", "params": {"characters": ["kit"]}, "beats": [{"text": "Hi.", "actions": [{"host_look": "kit"}]}]}
    beats = [{"text": "One.", "actions": [{"host_point": "item9"}, {"host_move": "up"}]}, {"text": "Two.", "actions": [{"host_react": "happy", "effect": "glow"}]}]
    root = make_project(config([bullets(beats=beats), stage], host={"character": "dot"}))
    lines = check_project(Project.load(root))
    assert any(line.startswith("scenes[0].beats[0].actions[0].target: unknown target 'item9'") for line in lines), lines
    assert any(line.startswith("scenes[0].beats[0].actions[1].target: host_move takes one of other_side, left, right") for line in lines)
    assert any(line.startswith("scenes[0].beats[1].actions[0].effect:") for line in lines)
    assert any(line.startswith("scenes[1].beats[0].actions[0].action: host_look: this scene type draws no host") for line in lines), lines


# ----- reveal steps ------------------------------------------------------------------------------------


def test_value_trend_and_error_text() -> None:
    assert value_trend([1, 2, 5]) == "rise" and value_trend([5, 2, 1]) == "fall" and value_trend([10, 10.2]) is None
    assert value_trend([3]) is None and value_trend([0, 0]) is None
    assert has_error_text(["raise ValueError('no')"]) and has_error_text(["Traceback (most recent call last):"])
    assert has_error_text(["test_sum FAILED"]) and not has_error_text(["total = a + b", "return total"])


def steps_of(kind: str, params: dict[str, Any]) -> tuple[list[RevealStep], list[str]]:
    cls = registry.get(kind).cls
    parsed = cls.parse_params(params)
    return cls.reveal_steps(parsed), cls.target_names(parsed)


@pytest.mark.parametrize(
    ("kind", "params", "expected"),
    [
        ("bullets", {"items": ["a", "b"]}, [("item1", None), ("item2", None)]),
        ("bullets", {"items": ["a", "b"], "reveal": "all"}, [("item1", None)]),
        ("bar_chart", {"labels": ["x", "y", "z"], "values": [1, 3, 2]}, [("bar3", "rise")]),
        ("bar_chart", {"labels": ["x", "y", "z"], "values": [1, 3, 2], "reveal": "per_beat", "highlight": "y"},
         [("bar1", None), ("bar2", "rise"), ("bar3", "fall"), ("bar2", None)]),
        ("line_chart", {"x": [1, 2, 3], "series": {"up": [1, 2, 4], "down": [4, 3, 1]}}, [("series1", "rise"), ("series2", "fall")]),
        ("code", {"code": "x = 1\ny = 2\nraise ValueError(y)\n", "highlight": [1, "1-2", 3]},
         [("line1", None), ("lines:1-2", None), ("line3", "error")]),
        ("code", {"code": "x = 1\n"}, [("listing", None)]),
    ],
)
def test_reveal_steps_name_the_scenes_targets(kind: str, params: dict[str, Any], expected: list[tuple[str, str | None]]) -> None:
    steps, names = steps_of(kind, params)
    assert [(s.focus, s.result) for s in steps] == expected
    assert all(s.focus in names for s in steps)


# ----- the planner -------------------------------------------------------------------------------------

ON = frozenset({"looks", "gestures", "reactions", "effects"})


def planned(beats: list[HostBeat], **kw: Any) -> dict[str, list[str]]:
    return {d.beat: [" ".join([a.action, *a.targets(), *(f"{k}={v}" for k, v in a.options.items())]) for a in d.actions]
            for d in plan_host_directions(beats, **kw)}


def test_the_host_points_at_each_new_item_once_and_reacts_to_results() -> None:
    beats = [
        HostBeat("b1", (), ON, (RevealStep("bar1"),)),
        HostBeat("b2", (), ON, (RevealStep("bar2", "rise"), RevealStep("bar3", "fall"))),   # two reveals: one point, the first result
        HostBeat("b3", (), ON, (RevealStep("bar2"),)),                                       # pointed at already: a look
        HostBeat("b4", (), ON, ()),
    ]
    assert planned(beats) == {
        "b1": ["host_point bar1"],
        "b2": ["host_point bar2", "host_react happy effect=sparkle"],
        "b3": ["host_look bar2"],
    }
    assert all(a.auto for d in plan_host_directions(beats) for a in d.actions)
    react = plan_host_directions(beats)[1].actions[1]
    assert react.at == pytest.approx(0.4)
    no_effects = [HostBeat("b", (), frozenset({"reactions"}), (RevealStep("line3", "error"),))]
    assert planned(no_effects) == {"b": ["host_react surprised"]}


def test_written_host_actions_and_highlights_win() -> None:
    highlight = act({"highlight": "item2", "at": 0.5})
    beats = [
        HostBeat("b1", (act({"host_point": "item3"}),), ON, (RevealStep("item1"),)),          # a written point: no automatic point or look
        HostBeat("b2", (highlight,), ON, (RevealStep("item1"),)),                              # item1 still new: pointed at
        HostBeat("b3", (highlight,), ON, ()),                                                  # nothing new: looks at the highlight
        HostBeat("b4", (act({"host_react": "sad"}),), ON, (RevealStep("item4", "fall"),)),     # a written reaction: no automatic one
    ]
    assert planned(beats) == {"b2": ["host_point item1"], "b3": ["host_look item2"], "b4": ["host_point item4"]}
    directed = plan_host_directions(beats)
    assert directed[0].actions[0].at == 0.0 and directed[1].actions[0].at == pytest.approx(0.5)   # the look with the highlight
    only_looks = [HostBeat("b", (), frozenset({"looks"}), (RevealStep("item1", "rise"),))]
    assert planned(only_looks) == {"b": ["host_look item1"]}
    assert planned([HostBeat("b", (), frozenset(), (RevealStep("item1", "rise"),))]) == {}


def test_moves_get_nothing_and_an_absent_host_nothing() -> None:
    enter, leave = act({"action": "host_enter"}), act({"host_exit": "left"})
    beats = [
        HostBeat("b1", (), ON, (RevealStep("item1"),)),                        # not on screen yet
        HostBeat("b2", (enter,), ON, (RevealStep("item2"),)),                  # walking in
        HostBeat("b3", (), ON, (RevealStep("item3"),)),
        HostBeat("b4", (act({"host_move": "other_side"}),), ON, (RevealStep("item4"),)),
        HostBeat("b5", (leave,), ON, (RevealStep("item5"),)),
        HostBeat("b6", (), ON, (RevealStep("item6"),)),                        # gone
    ]
    assert not starts_present([enter, leave]) and starts_present([leave, enter]) and starts_present([])
    assert planned(beats, present=False) == {"b3": ["host_point item3"]}


def test_project_directions_for_a_host(make_project) -> None:
    root = make_project(config(auto_direct=True))
    project = Project.load(root)
    with extensions.project_session(project) as _:
        found = project_directions(project)
    assert [(d.beat, [a.describe() for a in d.actions]) for d in found["steps"]] == [
        ("steps_b1", ["host_point item1 (auto)"]), ("steps_b2", ["host_point item2 (auto)"]), ("steps_b3", ["host_point item3 (auto)"]),
    ]
    root = make_project(config(host={"character": "dot", "auto_direct": False}, auto_direct=True), folder="off")
    with extensions.project_session(Project.load(root)) as _:
        assert project_directions(Project.load(root)) == {}
    root = make_project(config(host={"character": "dot", "auto_direct": True}), folder="host_only")
    with extensions.project_session(Project.load(root)) as _:
        assert "steps" in project_directions(Project.load(root))


def test_host_overlap_skips_the_hosts_pointer_and_symbol() -> None:
    from test_lint import shape

    host = {**shape("h", [1500, 400, 1800, 1000], kind="host", order=50), "name": "dot", "class": "HostFigure"}
    pointer = {**shape("p", [900, 500, 1600, 520], kind="pointer", order=60), "name": "dot"}
    own = {**shape("e", [1600, 350, 1700, 450], kind="effect", order=61), "effect": "sparkle", "effect_of": "dot"}
    other = {**shape("o", [1600, 350, 1700, 450], kind="effect", order=62), "effect": "sweat", "effect_of": "kit"}
    issues = check("host_overlap", [host, pointer, own, other])
    assert [i.message.split(" (")[0] for i in issues] == ["host 'dot' overlaps effect 'sweat' of character 'kit'"]


def test_the_host_explainer_example_validates_and_is_directed() -> None:
    project = Project.load(Path(__file__).resolve().parents[1] / "examples" / "host-explainer")
    assert check_project(project) == []
    with extensions.project_session(project) as _:
        found = project_directions(project)
    labels = {d.beat: [a.describe() for a in d.actions] for beats in found.values() for d in beats}
    assert labels["helpers_b2"] == ["host_point item2 (auto)"]
    assert labels["grow_b1"] == ["host_point bar1 (auto)"]
    assert labels["grow_b3"] == ["host_point bar3 (auto)", "host_react happy (auto)"]   # the dough rising
    assert set(found) == {"helpers", "grow"}   # moves, and scene types without reveal steps, get none


# ----- one tiny render ---------------------------------------------------------------------------------


@pytest.mark.render
def test_the_host_points_reacts_moves_and_leaves(make_project, tmp_path: Path) -> None:
    from vidgen.introspect import LayoutRecorder

    beats = [
        {"text": "Here is the first thing on our list today.", "actions": [{"host_point": "item1", "line": True}, {"host_react": "happy", "effect": "sparkle"}]},
        {"text": "Now the host walks over to the other side of the content while we talk about it.", "actions": [{"host_move": "other_side"}]},
        {"text": "And now the host leaves the screen for a while.", "actions": [{"host_exit": "left"}]},
    ]
    root = make_project(config([bullets(beats=beats)]))
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(Project.load(root), "steps", tmp_path / "media", recorder)
    ends = {frame["beat"]: frame for frame in recorder.frames}
    first, moved, gone = (ends[f"steps_b{n}"]["objects"] for n in (1, 2, 3))

    def one(objects: list[dict[str, Any]], kind: str, name: str | None = None) -> dict[str, Any]:
        found = [o for o in objects if o["kind"] == kind and (name is None or o.get("text") == name or o.get("name") == name)]
        assert len(found) == 1, found
        return found[0]

    host = one(first, "host")
    assert host["pointing_at"] == "item1" and host["side"] == "right" and host["face"] is not None
    pointer = one(first, "pointer", "dot")
    item = one(first, "text", "One thing")
    assert pointer["bbox"][0] > item["bbox"][2] and pointer["bbox"][2] <= host["bbox"][2] + 1   # from the hand to just short of the item
    assert [o for o in first if o["kind"] == "effect"]                                         # the sparkle with the reaction
    assert check("host_overlap", first) == []
    host = one(moved, "host")
    assert host["side"] == "left" and "pointing_at" not in host and not [o for o in moved if o["kind"] == "pointer"]
    assert ends["steps_b2"]["camera"]["center"][0] < 0                                          # the camera moved, so the content slid right
    assert one(moved, "text", "One thing")["bbox"][0] > item["bbox"][0] + 10
    assert host["bbox"][2] < one(moved, "text", "One thing")["bbox"][0]
    assert check("host_overlap", moved) == []
    host = [o for o in gone if o["kind"] == "host"]
    assert not host or host[0]["bbox"][2] <= 0                                                  # out by the left edge
    assert not scene.host.present and not scene.host.at_home
