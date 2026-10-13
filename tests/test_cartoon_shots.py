"""Step 95: shots within a stage scene (``shot:`` beat key). The framing maths, the runner's cut
back after a shot's beat, lint ``off_stage`` in a shot and automatic close-up shots are tested
without rendering; one tiny render checks the camera and the layout dump."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES
from test_cartoon_directing import DUO, FEET, FH, FW, HEIGHT, LONG, MOVERS, directed, frame, line
from test_cartoon_lint import check, fig
from test_cartoon_stage import render_with_layout
from vidgen import actions, extensions, registry
from vidgen.cartoon.directing import CastMember, DirectedBeat, auto_label, directions_yaml
from vidgen.cartoon.shots import (
    LOOK_ROOM,
    MAX_SHOT_SCALE,
    SHOT_SPANS,
    SUBJECT_AT,
    TWO_SHOT_PADDING,
    Shot,
    ShotFigure,
    frame_shot,
    shot_figures,
)
from vidgen.config import ActionConfig, BeatConfig, SceneConfig, ShotConfig
from vidgen.project import Project

BOUNDS = (-FW / 2, FW / 2, -FH / 2, FH / 2)
PIP = ShotFigure("pip", -3.5, FEET, HEIGHT, "right")
KIT = ShotFigure("kit", 3.5, FEET, HEIGHT, "left")


def framed(kind: str, *subjects: ShotFigure, near: ShotFigure | None = None, bounds: tuple[float, ...] = BOUNDS) -> Any:
    return frame_shot(kind, subjects, frame_width=FW, frame_height=FH, bounds=bounds, near=near)


def view_box(view: Any) -> tuple[float, float, float, float]:
    width, height = view.size(FW, FH)
    return (view.center_x - width / 2, view.center_y - height / 2, view.center_x + width / 2, view.center_y + height / 2)


# ----- framing maths (no manim) --------------------------------------------------------------------------


def test_a_closeup_frames_head_and_shoulders_with_room_in_front_of_the_face() -> None:
    view = framed("closeup", PIP)
    below, above = SHOT_SPANS["closeup"]
    assert view.scale == pytest.approx(FH / ((below + above) * HEIGHT))
    left, bottom, right, top = view_box(view)
    assert top == pytest.approx(FEET + HEIGHT + above * HEIGHT) and bottom == pytest.approx(FEET + HEIGHT - below * HEIGHT)
    assert view.center_x == pytest.approx(PIP.x + LOOK_ROOM * (right - left))   # pip faces right: room on its right
    assert framed("closeup", KIT).center_x == pytest.approx(KIT.x - LOOK_ROOM * (right - left))


def test_a_medium_shot_is_wider_than_a_closeup_and_a_wide_shot_is_not_zoomed() -> None:
    assert 1 < framed("medium", PIP).scale < framed("closeup", PIP).scale
    assert framed("wide", PIP, KIT).scale == 1 and framed("wide", PIP, KIT).center_x == pytest.approx(0.0)
    assert framed("wide").center_x == 0.0   # no one on stage: the stage's middle


def test_a_two_shot_holds_both_figures_whole_with_padding() -> None:
    view = framed("two_shot", PIP, KIT)
    left, bottom, right, top = view_box(view)
    pad = TWO_SHOT_PADDING * (right - left)
    assert view.scale > 1
    assert left + pad == pytest.approx(PIP.box()[0]) and right - pad == pytest.approx(KIT.box()[2])   # the width decides here
    assert bottom <= FEET and top >= FEET + HEIGHT
    close = framed("two_shot", PIP, ShotFigure("kit", -2.5, FEET, HEIGHT, "left"))
    assert close.scale > view.scale   # nearer together: tighter


def test_over_the_shoulder_puts_the_near_character_on_the_edge() -> None:
    view = framed("over_shoulder", KIT, near=PIP)   # kit seen past pip, pip on the left
    left, _, right, _ = view_box(view)
    width = right - left
    assert left == pytest.approx(PIP.x)   # pip's middle on the edge: half of it out of frame
    assert (KIT.x - left) / width == pytest.approx(SUBJECT_AT)
    flipped = framed("over_shoulder", PIP, near=KIT)
    assert view_box(flipped)[2] == pytest.approx(KIT.x)   # pip seen past kit, kit on the right
    beside = framed("over_shoulder", KIT, near=ShotFigure("pip", 3.0, FEET, HEIGHT, "right"))
    assert beside.scale == pytest.approx(framed("closeup", KIT).scale)   # never tighter than a close-up
    assert framed("over_shoulder", KIT).scale == pytest.approx(framed("medium", KIT).scale)   # no near character: a medium


def test_shots_stay_on_the_stage_and_within_the_zoom_limit() -> None:
    edge = ShotFigure("pip", -FW / 2 + 0.3, FEET, HEIGHT, "left")
    left = view_box(framed("closeup", edge))[0]
    assert left == pytest.approx(-FW / 2)   # clamped to the stage's left edge
    tiny = ShotFigure("pip", 0.0, FEET, 0.2, "right")
    assert framed("closeup", tiny).scale == MAX_SHOT_SCALE
    with pytest.raises(ValueError, match="unknown shot"):
        framed("dutch_angle", PIP)


def test_the_characters_a_shot_frames_when_fewer_are_named() -> None:
    rex = ShotFigure("rex", 6.0, FEET, HEIGHT, "left")
    present = {"pip": PIP, "kit": KIT, "rex": rex}
    assert shot_figures("wide", [], present) == Shot("wide", ("pip", "kit", "rex"))
    assert shot_figures("two_shot", [], present, speakers=["kit"]) == Shot("two_shot", ("kit", "rex"))   # the speaker and its nearest
    assert shot_figures("two_shot", ["pip"], present) == Shot("two_shot", ("pip", "kit"))
    assert shot_figures("over_shoulder", ["kit"], present, looked_at={"kit": "pip"}) == Shot("over_shoulder", ("kit",), "pip")
    assert shot_figures("over_shoulder", ["kit"], present) == Shot("over_shoulder", ("kit",), "rex")   # the nearest
    assert shot_figures("over_shoulder", ["kit", "pip"], present).near == "pip"
    assert shot_figures("closeup", ["moss"], present).kind == "wide"   # not on stage: nothing to frame
    assert Shot("over_shoulder", ("kit",), "pip").layout() == {"kind": "over_shoulder", "subjects": ["kit"], "near": "pip"}


# ----- the beat key (no manim) ----------------------------------------------------------------------------


def test_the_shot_key_in_words_or_as_a_mapping() -> None:
    assert ShotConfig.model_validate("over_shoulder kit pip") == ShotConfig(kind="over_shoulder", of=["kit", "pip"])
    assert ShotConfig.model_validate({"kind": "closeup", "of": "kit", "move": True}).of == ["kit"]
    assert BeatConfig(id="b1", text="Hi.", shot="wide").shot.action().shorthand() == {"action": "shot", "kind": "wide"}
    assert ShotConfig.model_validate("closeup kit").action().shorthand() == {"shot": ["kit"], "kind": "closeup"}
    for bad, message in [("closeup", "names 1 character"), ("wide kit", "names no character"), ("two_shot kit kit", "twice"),
                         ({"kind": "medium", "of": "kit", "run_time": 2}, "move: true"), ("zoomed kit", "kind")]:
        with pytest.raises(ValidationError, match=message):
            ShotConfig.model_validate(bad)


def scene_with(beats: list[dict[str, Any]]) -> SceneConfig:
    return SceneConfig.model_validate({"id": "park", "type": "stage", "beats": beats})


def listed(beats: list[dict[str, Any]]) -> list[tuple[str, str, dict[str, Any]]]:
    return [(beat, where, act.shorthand()) for beat, where, act in actions.beat_action_list(scene_with(beats), ["shot", "look_at"])]


def test_a_shot_holds_for_its_beat_and_the_next_one_cuts_back() -> None:
    found = listed([
        {"text": "One.", "shot": "closeup pip", "actions": [{"look_at": "pip", "to": "kit"}]},
        {"text": "Two."},
        {"text": "Three.", "shot": {"kind": "medium", "of": "kit", "move": True}},
        {"text": "Four.", "shot": "wide"},
        {"text": "Five."},
    ])
    assert found == [
        ("park_b1", "beats[0].shot", {"shot": ["pip"], "kind": "closeup"}),
        ("park_b1", "beats[0].actions[0]", {"look_at": "pip", "to": "kit"}),
        ("park_b2", "beats[1].shot", {"action": "shot"}),   # back to the view before the shots
        ("park_b3", "beats[2].shot", {"shot": ["kit"], "kind": "medium", "move": True}),
        ("park_b4", "beats[3].shot", {"action": "shot", "kind": "wide"}),   # its own shot: no cut back first
        ("park_b5", "beats[4].shot", {"action": "shot"}),
    ]
    eased = listed([{"text": "One.", "shot": {"kind": "closeup", "of": "kit", "move": True, "run_time": 0.6}}, {"text": "Two."}])
    assert eased[-1][2] == {"action": "shot", "move": True, "run_time": 0.6}   # eases back as it eased in
    later = listed([{"text": "One.", "shot": "closeup kit"}, {"text": "Two.", "actions": [{"shot": "pip", "kind": "closeup", "at": 0.5}]}])
    assert [a for _, _, a in later][1] == {"action": "shot"}   # a shot later in the beat: back first


def stage_project(make_project, beats: list[dict[str, Any]], **params: Any) -> Project:
    params = {"idle": False, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}], "props": ["tree"], **params}
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))


def problems_of(project: Project) -> list[tuple[str, str]]:
    spec = project.config.scenes[0]
    with extensions.project_session(project) as theme:
        cls = registry.get(spec.type).cls
        params = cls.validate_params(spec.params, theme)
        return actions.scene_actions(spec.type, cls, spec, params, theme)[1]


def test_validate_checks_a_shots_characters_and_scene_type(make_project) -> None:
    assert problems_of(stage_project(make_project, [{"text": "Hi.", "shot": "over_shoulder kit pip"}, {"text": "Bye."}])) == []
    found = problems_of(stage_project(make_project, [{"text": "Hi.", "shot": "closeup tree"}, {"text": "Hi.", "shot": "closeup moss"}]))
    assert [loc for loc, _ in found] == ["beats[0].shot.target", "beats[1].shot.target"]
    assert "not a character" in found[0][1] and "moss" in found[1][1]
    card = Project.load(make_project(minimal_config(scenes=[{"id": "t", "type": "text_card", "params": {"text": "Hi"},
                                                              "beats": [{"text": "Hi.", "shot": "wide"}]}])))
    assert [(loc, "stage" in msg) for loc, msg in problems_of(card)] == [("beats[0].shot.kind", True)]


# ----- lint off_stage in a shot (no manim) ----------------------------------------------------------------


def off_stage(objects: list[dict[str, Any]], shot: dict[str, Any] | None, zoom: float = 3.0) -> list[str]:
    extra = {"shot": shot} if shot else {}
    return [o["name"] for issue in check("off_stage", objects, camera={"zoom": zoom, "center": [0, 0]}, **extra) for o in issue.objects]


def test_off_stage_lets_the_near_character_of_an_over_the_shoulder_shot_be_cut() -> None:
    near = fig("pip", [-150, 100, 150, 480], face=[-150, 100, 150, 250])    # half out on the left
    seen = fig("kit", [500, 100, 700, 480], face=[500, 100, 700, 250])
    shot = {"kind": "over_shoulder", "subjects": ["kit"], "near": "pip"}
    assert off_stage([near, seen], shot) == []
    cut = fig("kit", [700, 100, 900, 480], face=[700, 100, 900, 250])   # the subject's face cut by the right edge
    assert off_stage([near, cut], shot) == ["kit"]
    assert off_stage([near, cut], None) == []                 # a zoom without a shot: not checked (Step 84)
    assert off_stage([near, cut], None, zoom=1.0) == ["pip", "kit"]


def test_off_stage_in_a_closeup_checks_the_face_and_a_two_shot_the_whole_figures() -> None:
    legs_cut = fig("kit", [300, 50, 600, 700], face=[320, 50, 580, 300])   # its body below the frame: fine in a close-up
    other = fig("pip", [-100, 50, 150, 700], face=[-100, 50, 150, 300])    # not framed: may be cut
    assert off_stage([legs_cut, other], {"kind": "closeup", "subjects": ["kit"]}) == []
    assert off_stage([legs_cut, other], {"kind": "two_shot", "subjects": ["kit", "pip"]}) == ["kit", "pip"]
    gone = fig("kit", [900, 50, 1100, 700], face=[900, 50, 1100, 300])   # walked out of its close-up
    assert off_stage([gone], {"kind": "closeup", "subjects": ["kit"]}) == ["kit"]
    assert off_stage([legs_cut, other], {"kind": "wide", "subjects": ["kit", "pip"]}, zoom=1.0) == ["kit", "pip"]   # wide: as without a shot


# ----- automatic close-ups (no manim) ---------------------------------------------------------------------


def test_a_quick_closeup_is_a_shot_and_vidgen_direct_prints_it_as_the_key() -> None:
    beats = [line("b1", LONG, ("pip",), kinds=frozenset({"closeups"})), line("b2", "No.", ("kit",), kinds=frozenset({"closeups"}))]
    assert directed(beats) == {"b2": [{"shot": "kit", "kind": "closeup"}]}
    # in a close-up of pip, kit (whom it talks to) is out of the view and rex, behind pip, the nearest one:
    # lint would report pip facing away, so no shot
    trio, cast = frame(pip=(0.0, "right"), kit=(5.0, "left"), rex=(-2.0, "right")), [*MOVERS, CastMember("rex")]
    first = line("b1", LONG, ("kit",), [{"look_at": "pip", "to": "kit"}], kinds=frozenset({"closeups"}))
    short = line("b2", "No.", ("pip",), kinds=frozenset({"closeups"}))
    assert directed([first, short], trio, cast) == {}
    clear = frame(pip=(0.0, "right"), kit=(5.0, "left"), rex=(-5.5, "right"))
    assert directed([first, short], clear, cast) == {"b2": [{"shot": "pip", "kind": "closeup"}]}
    added = (ActionConfig.automatic({"shot": "kit", "kind": "closeup"}), ActionConfig.automatic({"react": "pip", "expression": "sad", "at": 0.95}))
    text = directions_yaml({"park": [DirectedBeat("b2", added)], "yard": [DirectedBeat("b5", added[:1])]})
    loaded = yaml.safe_load(text)
    assert loaded["scenes"][0]["beats"] == [{"id": "b2", "shot": "closeup kit", "actions": [{"react": "pip", "expression": "sad", "at": 0.95}]}]
    assert loaded["scenes"][1]["beats"] == [{"id": "b5", "shot": "closeup kit"}]
    assert BeatConfig(text="No.", **loaded["scenes"][0]["beats"][0]).shot == ShotConfig(kind="closeup", of=["kit"])   # pastes as a valid beat
    assert auto_label(added[0]) == "shot closeup kit"


def test_a_written_shot_stops_automatic_closeups_and_is_where_checks_look() -> None:
    beats = [line("b1", LONG, ("pip",), kinds=frozenset({"closeups"})),
             line("b2", "No.", ("kit",), [{"action": "shot", "kind": "wide"}], kinds=frozenset({"closeups"}))]
    assert directed(beats) == {}
    # pip shrugs in a close-up of kit: pip is outside the shot, so its arm cannot add an off_stage finding
    text = "That is a perfectly *ordinary* cardboard box, of course."
    edge = frame(pip=(-FW / 2 + 0.9, "left"), kit=(3.5, "left"))
    plain = directed([line("b1", text, ("pip",))], edge)["b1"][0]["to"]
    in_shot = directed([line("b1", text, ("pip",), [{"shot": "kit", "kind": "closeup"}])], edge)["b1"][0]["to"]
    assert plain in ("nod", "shake_head") and in_shot not in ("nod", "shake_head")


# ----- a tiny render ----------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_shot_cuts_the_camera_and_the_next_beat_cuts_back(make_project, tmp_path: Path) -> None:
    from vidgen.introspect import LayoutRecorder

    beats = [{"text": "Look at that.", "voice": "kit_voice", "shot": "over_shoulder kit"},
             {"text": "Yes.", "voice": "pip_voice", "shot": {"kind": "closeup", "of": "pip", "move": True}},
             {"text": "Fine."}]
    project = stage_project(make_project, beats, particles=["snow"], layers=[{"place": "background", "shapes": [{"shape": "hills"}]}])
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "park", tmp_path / "media", recorder)
    ends = {f["beat"]: f for f in recorder.frames if f["k"] == f["n"]}
    first, second, third = (ends[f"park_b{k}"] for k in (1, 2, 3))
    assert first["shot"] == {"kind": "over_shoulder", "subjects": ["kit"], "near": "pip"} and first["camera"]["zoom"] > 1.2   # left and right marks: far apart, so not tight
    assert second["shot"]["kind"] == "closeup" and second["camera"]["zoom"] > first["camera"]["zoom"]
    assert "shot" not in third and third["camera"]["zoom"] == pytest.approx(1.0) and third["camera"]["center"] == pytest.approx([0.0, 0.0])
    pip = next(o for o in first["objects"] if o.get("name") == "pip")
    assert pip["bbox"][0] < 0 < pip["bbox"][2]   # the near character stands cut by the left edge
    assert any(o["kind"] == "particles" for o in first["objects"])
    assert scene.camera_shot is None and scene.shot_home is None
