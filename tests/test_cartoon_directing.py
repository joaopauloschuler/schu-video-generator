"""Step 89: automatic directing, part 1 (``auto_direct``: looks and reactions). The planner is a
pure function from a scene's beats to added actions; the stage merges them before its action
runner; ``vidgen direct`` and the storyboard show them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES
from test_cartoon_stage import render_with_layout
from vidgen import actions, cli, extensions, registry
from vidgen.cartoon.directing import (
    REACTION_AT,
    BeatInput,
    CastMember,
    auto_label,
    directions_yaml,
    line_cue,
    plan_directions,
    project_directions,
    with_auto_actions,
)
from vidgen.config import ActionConfig, AutoDirect, SceneConfig, directing_kinds
from vidgen.project import Project
from vidgen.sheets import SheetScene, SheetStill, _blocks, _metrics

ALL = frozenset({"looks", "reactions"})
TRIO = [CastMember("pip"), CastMember("kit"), CastMember("rex")]


def beat(id: str, text: str, speakers: tuple[str, ...] = (), actions: list[dict[str, Any]] | None = None, kinds: frozenset[str] = ALL) -> BeatInput:
    return BeatInput(id, text, speakers, tuple(ActionConfig.model_validate(a) for a in actions or []), kinds)


def plan(beats: list[BeatInput], cast: list[CastMember] = TRIO) -> dict[str, list[dict[str, Any]]]:
    """The added actions by beat, in the YAML form."""
    return {d.beat: [a.shorthand() for a in d.actions] for d in plan_directions("park", cast, beats)}


# ----- the setting (no manim) ----------------------------------------------------------------------------


def test_the_nearest_auto_direct_setting_wins() -> None:
    assert directing_kinds(None, None, False) == frozenset()   # the video's default: off
    assert directing_kinds(None, None, True) == {"looks", "reactions", "gestures", "closeups"}
    assert directing_kinds(None, AutoDirect(reactions=False), True) == {"looks", "gestures", "closeups"}   # the scene's
    assert directing_kinds(False, True, True) == frozenset()   # the beat's
    assert directing_kinds(AutoDirect(looks=False, gestures=False, closeups=False), None, None) == {"reactions"}


def test_line_cues() -> None:
    assert line_cue("Ready? One, two...") == "question"
    assert line_cue("Isn't it great?") == "question"          # a question before a negation
    assert line_cue("Boxes do not fly.") == "negation"
    assert line_cue("That won’t work!") == "negation"      # curly apostrophe
    assert line_cue("It flew away!") == "exclaim"
    assert line_cue("It is a box kite.") is None


# ----- looks (no manim) ----------------------------------------------------------------------------------


def test_listeners_look_at_the_speaker_and_the_speaker_at_whom_it_answers() -> None:
    added = plan([
        beat("b1", "Once upon a time."),                     # the narrator: nothing
        beat("b2", "Hello there.", ("pip",)),
        beat("b3", "Hi, pip.", ("kit",)),
        beat("b4", "How are you.", ("kit",)),               # the same speaker again: nothing new
    ])
    assert added == {
        # pip talks first: to the next one who speaks (kit)
        "b2": [{"look_at": "pip", "to": "kit"}, {"look_at": "kit", "to": "pip"}, {"look_at": "rex", "to": "pip"}],
        "b3": [{"look_at": "rex", "to": "kit"}],             # kit already looks at pip, pip at kit
    }


def test_written_actions_win_and_reset_a_look() -> None:
    added = plan([
        beat("b1", "Hello there.", ("pip",), [{"look_at": "kit", "to": "camera"}, {"say": "pip"}, {"zoom": "rex"}]),
        beat("b2", "Hello again.", ("pip",), [{"walk_to": "rex", "to": "left"}]),
        beat("b3", "And again.", ("pip",)),
    ])
    assert added == {
        "b1": [{"look_at": "rex", "to": "pip"}],   # kit's own look wins; say and zoom leave pip and rex to auto
        "b2": [{"look_at": "kit", "to": "pip"}],   # kit looked at the camera; rex walks
        "b3": [{"look_at": "rex", "to": "pip"}],   # after its walk
    }   # pip talks to nobody in particular: two listeners and no one answers


def test_characters_off_stage_neither_look_nor_are_looked_at() -> None:
    added = plan([
        beat("b1", "Where is everyone.", ("pip",)),
        beat("b2", "Here I am.", ("rex",), [{"enter": "rex", "side": "left"}]),
        beat("b3", "Bye.", ("kit",), [{"exit": "kit", "to": "right"}]),
        beat("b4", "Hm.", ("pip",)),
    ])
    assert added == {
        "b1": [{"look_at": "pip", "to": "kit"}, {"look_at": "kit", "to": "pip"}],   # rex enters later
        "b2": [{"look_at": "pip", "to": "rex"}, {"look_at": "kit", "to": "rex"}],   # rex itself walks in
        "b4": [{"look_at": "rex", "to": "pip"}],   # kit has left; pip still looks at rex
    }


def test_what_the_parts_and_the_kinds_allow() -> None:
    cast = [CastMember("pip"), CastMember("kit", can_look=False, can_emote=False)]
    assert plan([beat("b1", "Hello!", ("pip",))], cast) == {"b1": [{"look_at": "pip", "to": "kit"}]}
    only = frozenset({"reactions"})
    (reactions,) = plan([beat("b1", "Hello!", ("pip",), kinds=only)]).values()
    assert [(a["react"], a["at"]) for a in reactions] == [("kit", REACTION_AT), ("rex", REACTION_AT)]
    assert all(a["expression"] in ("surprised", "happy") for a in reactions)
    assert plan([beat("b1", "Hello!", ("pip",), kinds=frozenset())]) == {}


# ----- reactions (no manim) ------------------------------------------------------------------------------


def test_reactions_follow_the_line_and_never_repeat() -> None:
    lines = ["Look at it!", "What is it?", "It is not a kite.", "No!", "Never!", "Really?", "Why?", "Oh."]
    beats = [beat(f"b{k}", text, ("pip",), kinds=frozenset({"reactions"})) for k, text in enumerate(lines)]
    added = plan(beats)
    assert added == plan(beats)   # seeded: the same every time
    kit = [next(a["expression"] for a in added[f"b{k}"] if a["react"] == "kit") for k in range(7)]
    assert kit[0] in ("surprised", "happy") and kit[1] in ("thinking", "surprised") and kit[2] in ("worried", "sad")
    assert all(a != b for a, b in zip(kit, kit[1:]))
    assert "b7" not in added   # a plain statement: no reaction
    assert all(a["at"] == REACTION_AT and a["react"] != "pip" for acts in added.values() for a in acts)   # the speaker does not react


def test_merged_after_the_written_actions_and_marked_auto() -> None:
    spec = SceneConfig(id="park", type="stage", beats=[{"id": "b1", "text": "Hi!", "actions": [{"emote": "pip", "to": "happy"}]}, {"id": "b2", "text": "Yo."}])
    directed = plan_directions("park", TRIO, [beat("b1", "Hi!", ("pip",), [{"emote": "pip", "to": "happy"}])])
    merged = with_auto_actions(spec, directed)
    assert len(spec.beats[0].actions) == 1   # the config is not changed
    acts = merged.beats[0].actions
    assert [a.auto for a in acts] == [False, True, True, True, True]
    assert acts[1].describe() == "look_at kit (auto)" and auto_label(acts[3]) in ("react kit surprised", "react kit happy")
    assert merged.beats[1] is spec.beats[1]


# ----- a stage project ----------------------------------------------------------------------------------


def directed_project(make_project, beats: list[dict[str, Any]], params: dict[str, Any] | None = None, **config: Any) -> Project:
    params = {"idle": False, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}, "rex"], **(params or {})}
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": beats}]
    return Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes, **config)))


DIALOGUE = [
    {"text": "On a sunny day."},
    {"text": "Is that a kite?", "voice": "pip_voice"},
    {"text": "It is not.", "voice": "kit_voice", "auto_direct": False},
    {"text": "Wow!", "actions": [{"say": "kit"}]},
]


def test_stage_scene_directions_from_the_project(make_project) -> None:
    project = directed_project(make_project, DIALOGUE, params={"auto_direct": {"reactions": False}}, auto_direct=True)
    with extensions.project_session(project):
        directed = project_directions(project)
    assert [(d.beat, [a.shorthand() for a in d.actions]) for d in directed["park"]] == [
        ("park_b2", [{"look_at": "pip", "to": "kit"}, {"look_at": "kit", "to": "pip"}, {"look_at": "rex", "to": "pip"}]),
        ("park_b4", [{"look_at": "rex", "to": "kit"}]),   # say picks the speaker; beat 3 is off
    ]
    off = directed_project(make_project, DIALOGUE)
    with extensions.project_session(off):
        assert project_directions(off) == {}   # off by default


def test_the_directed_actions_are_valid_and_planned_with_the_written_ones(make_project) -> None:
    project = directed_project(make_project, DIALOGUE, auto_direct=True)
    spec = project.scene("park")
    with extensions.project_session(project) as theme:
        cls = registry.get("stage").cls
        params = cls.validate_params(spec.params, theme)
        merged = with_auto_actions(spec, cls.auto_actions(project, spec, params))
        uses, problems = actions.scene_actions("stage", cls, merged, params, theme)
    assert problems == []
    assert [(u.beat, u.config.describe()) for u in uses if u.beat == "park_b4"] == [
        ("park_b4", "say kit"), ("park_b4", "look_at rex (auto)"), ("park_b4", "react pip (auto)"), ("park_b4", "react rex (auto)"),
    ]


def test_cartoon_example_with_auto_direct_validates(tmp_path: Path) -> None:
    root = tmp_path / "cartoon"
    root.mkdir()
    data = yaml.safe_load((Path(__file__).resolve().parents[1] / "examples" / "cartoon" / "video.yaml").read_text(encoding="utf-8"))
    (root / "video.yaml").write_text(yaml.safe_dump({**data, "auto_direct": True}, sort_keys=False), encoding="utf-8")
    project = Project.load(root)
    with extensions.project_session(project) as theme:
        directed = project_directions(project)
        for spec in project.config.scenes:
            cls = registry.get(spec.type).cls
            params = cls.validate_params(spec.params, theme)
            _, problems = actions.scene_actions(spec.type, cls, with_auto_actions(spec, directed.get(spec.id, [])), params, theme)
            assert problems == [], spec.id
    # every beat of the example acts on both characters, except one look in hill_told (explicit actions win)
    assert {sid: [(d.beat, [auto_label(a) for a in d.actions]) for d in beats] for sid, beats in directed.items()} == {
        "hill": [("hill_told", ["look_at moss dot"])],
    }


# ----- vidgen direct and the storyboard ------------------------------------------------------------------


def test_vidgen_direct_prints_yaml_to_paste(make_project, capsys) -> None:
    project = directed_project(make_project, DIALOGUE, auto_direct=True)
    assert cli.main(["direct", str(project.root), "--print"]) == 0
    printed = capsys.readouterr().out
    pasted = yaml.safe_load(printed)["scenes"]
    with extensions.project_session(project):
        directed = project_directions(project)
    assert pasted == [{"id": "park", "beats": [{"id": d.beat, "actions": [a.shorthand() for a in d.actions]} for d in directed["park"]]}]
    assert any(line.startswith("          - {react: pip, expression: ") and line.endswith(", at: 0.95}") for line in printed.splitlines())
    assert printed == directions_yaml(directed)

    assert cli.main(["direct", str(project.root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "direct" and [s["scene"] for s in doc["scenes"]] == ["park"]
    assert [{"id": b["beat"], "actions": b["actions"]} for b in doc["scenes"][0]["beats"]] == pasted[0]["beats"]

    assert cli.main(["direct", str(project.root)]) == 0
    assert "  park_b4: look_at rex kit  ·  react pip " in capsys.readouterr().out
    assert cli.main(["direct", str(project.root), "--scene", "nope"]) == 1


def test_pasting_the_printed_actions_leaves_nothing_to_add(make_project, capsys) -> None:
    """Explicit actions win: once pasted, automatic directing adds nothing more to those beats."""
    project = directed_project(make_project, DIALOGUE, auto_direct=True)
    cli.main(["direct", str(project.root), "--print"])
    pasted = {b["id"]: b["actions"] for b in yaml.safe_load(capsys.readouterr().out)["scenes"][0]["beats"]}
    beats = [dict(b, id=f"park_b{k}") for k, b in enumerate(DIALOGUE, start=1)]
    for b in beats:
        b["actions"] = [*b.get("actions", []), *pasted.get(b["id"], [])]
    again = directed_project(make_project, beats, auto_direct=True)
    with extensions.project_session(again):
        assert project_directions(again) == {}


def test_storyboard_sheet_lists_a_beats_automatic_actions(tmp_path: Path) -> None:
    from PIL import Image

    path = tmp_path / "b1-1.png"
    Image.new("RGB", (16, 9)).save(path)
    added = (ActionConfig.automatic({"look_at": "kit", "to": "pip"}), ActionConfig.automatic({"react": "kit", "expression": "happy", "at": 0.95}))
    still = SheetStill("park", "b1", 1, 1, 2.0, None, path, "Hello!", auto=added)
    scene = SheetScene("park", "stage", 1, 1, None, 2.5, 1, (still,))
    (block,) = _blocks(scene, _metrics(1280, (160, 90), True, None, 1))
    assert block.text[0] == "“Hello!”" and block.text[1] == "auto: look_at kit pip · react kit happy"


# ----- render --------------------------------------------------------------------------------------------


@pytest.mark.render
def test_a_directed_dialogue_renders(make_project, tmp_path: Path) -> None:
    project = directed_project(make_project, [
        {"text": "Is that a kite?", "voice": "pip_voice"},
        {"text": "No.", "voice": "kit_voice"},
    ], params={"characters": [{"name": "pip", "at": "left", "facing": "left"}, {"name": "kit", "at": "right"}]}, auto_direct=True)
    scene, objects = render_with_layout(project, "park", tmp_path / "media")
    pip, kit = scene.cast["pip"], scene.cast["kit"]
    assert [b.actions[-1].auto for b in scene.spec.beats] == [True, True]
    assert pip.facing == "right" and pip.looked_at == "kit" and kit.looked_at == "pip"   # pip turned to kit
    first = {o["name"]: o for o in objects if o.get("kind") == "character"}
    assert first["kit"]["looked_at"] == "pip" and first["pip"]["looked_at"] == "kit"
    played = {(record.beat, name) for record in scene.play_log for name in record.animations}
    assert ("park_b1", "PoseChange") in played and ("park_b2", "PoseChange") in played


@pytest.mark.render
def test_storyboard_marks_the_automatic_actions(make_project, capsys) -> None:
    tiny = {"width": 160, "height": 90, "fps": 5}
    project = directed_project(make_project, [
        {"text": "Is that a kite?", "voice": "pip_voice"},
        {"text": "It is a box.", "voice": "kit_voice", "actions": [{"emote": "kit", "to": "happy"}]},
    ], params={"characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}]}, auto_direct=True, format=tiny, preview=tiny)
    assert cli.main(["storyboard", str(project.root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    frames = {f["beat"]: f["auto"] for f in doc["sheets"][0]["frames"]}
    assert frames["park_b1"][:2] == [{"look_at": "pip", "to": "kit"}, {"look_at": "kit", "to": "pip"}]
    assert frames["park_b1"][2]["react"] == "kit" and frames["park_b2"] == []   # kit acts itself; pip already looks at kit
