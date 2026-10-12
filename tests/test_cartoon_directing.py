"""Steps 89 and 90: automatic directing (``auto_direct``: looks and reactions; gestures and
close-ups, checked against the cartoon lint rules on predicted stills). The planner is a pure
function from a scene's beats to added actions; the stage merges them before its action runner;
``vidgen direct`` and the storyboard show them."""

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
from vidgen.cartoon.acting import GESTURE_EASE, GESTURE_SECONDS, GESTURES
from vidgen.cartoon.directing import (
    CLOSEUP_CUT_SECONDS,
    CLOSEUP_SCALE,
    CLOSEUP_SECONDS,
    REACTION_AT,
    BeatInput,
    CastMember,
    StageFrame,
    StagePlace,
    _SceneState,
    _still,
    _Beat,
    auto_label,
    directions_yaml,
    gesture_choices,
    line_cue,
    plan_directions,
    project_directions,
    stage_frame,
    still_findings,
    stressed_word,
    with_auto_actions,
)
from vidgen.config import ActionConfig, AutoDirect, SceneConfig, directing_kinds
from vidgen.project import Project
from vidgen.sheets import SheetScene, SheetStill, _blocks, _metrics
from vidgen.speech import estimate_word_times

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


# ----- gestures and close-ups (Step 90, no manim) ---------------------------------------------------------

FW, FH = 128 / 9, 8.0   # a 16:9 frame in Manim units
HEIGHT = 3.6            # a stage character at size 0.45
FEET = -2.4             # on the ground line at 0.2


def frame(**places: tuple[float, str]) -> StageFrame:
    """A stage as wide as the frame with characters at (x, facing), the camera at its middle."""
    return StageFrame(FW, FH, FW, 0.0, {n: StagePlace(x, FEET, HEIGHT, facing) for n, (x, facing) in places.items()})


DUO = frame(pip=(-3.5, "right"), kit=(3.5, "left"))
MOVERS = [CastMember("pip", gestures=GESTURES), CastMember("kit", gestures=GESTURES)]


def line(id: str, text: str, speakers: tuple[str, ...] = (), actions: list[dict[str, Any]] | None = None,
         kinds: frozenset[str] = frozenset({"gestures", "closeups"})) -> BeatInput:
    """A beat with its words timed by the estimate (3 words a second)."""
    seconds = len(text.split()) / 3
    words = tuple(estimate_word_times(text.split(), 0.0, seconds))
    return BeatInput(id, text, speakers, tuple(ActionConfig.model_validate(a) for a in actions or []), kinds, seconds, words)


def directed(beats: list[BeatInput], stage: StageFrame | None = DUO, cast: list[CastMember] = MOVERS) -> dict[str, list[dict[str, Any]]]:
    return {d.beat: [a.shorthand() for a in d.actions] for d in plan_directions("park", cast, beats, stage)}


def test_the_stressed_word_of_a_line() -> None:
    assert stressed_word("I *really* mean it, TRULY".split()) == (1, "emphasis")
    assert stressed_word("I said it was ENORMOUS, honestly".split()) == (4, "capitals")
    assert stressed_word(["A", "wonderful", "remarkable", "thing"], [0.1, 0.5, 0.4, 0.2]) == (1, "longest")   # by spoken length
    assert stressed_word("A wonderful remarkable thing".split()) == (2, "longest")                            # else by letters
    assert stressed_word("I am a box.".split()) is None   # no long, capital or emphasised word ("I" is one letter)


def test_gesture_choices_follow_the_word_and_the_line() -> None:
    assert gesture_choices("never!", "That will never fly!", "s")[0] == "shake_head"
    assert gesture_choices("Yes,", "Yes, exactly.", "s")[0] == "nod"
    assert gesture_choices("hello", "Well hello there.", "s")[0] == "wave"
    assert gesture_choices("*there*", "It is over there.", "s")[0] == "point"
    assert gesture_choices("wonderful", "Is it wonderful?", "s")[0] == "shrug"
    rest = gesture_choices("wonderful", "It is wonderful.", "s", last="nod")
    assert sorted(rest) == ["nod", "point", "shrug"] and rest[-1] == "nod" and rest == gesture_choices("wonderful", "It is wonderful.", "s", last="nod")


def test_a_gesture_is_held_on_the_stressed_word_once_per_line() -> None:
    first = line("b1", "This kite is truly REMARKABLE today, my friend.", ("pip",))
    added = directed([first])
    (gesture,) = added["b1"]
    word = first.words[4]   # REMARKABLE
    start = gesture["at"] * first.seconds
    assert gesture["gesture"] == "pip" and gesture["to"] in GESTURES
    assert start <= word.start - GESTURE_EASE * GESTURE_SECONDS[gesture["to"]] + 1e-9 < start + 0.011 * first.seconds
    assert start + GESTURE_SECONDS[gesture["to"]] <= first.seconds   # over before the line ends

    # the longest word only when the speaker did not gesture in its previous line; capitals always
    beats = [first, line("b2", "A wonderful machine for every single person.", ("pip",)), line("b3", "Another remarkable machine for everyone here.", ("pip",)),
             line("b4", "And ANOTHER one for you, and you, and you.", ("pip",))]
    assert sorted(directed(beats)) == ["b1", "b3", "b4"]
    assert directed([line("b1", "A wonderful machine for every single person.", ("pip",))], cast=[CastMember("pip"), CastMember("kit")]) == {}   # no parts
    assert directed([line("b1", "REALLY now.", ("pip",))]) == {}   # no time for a gesture in the line
    touched = line("b1", "This kite is truly REMARKABLE today, my friend.", ("pip",), [{"emote": "pip", "to": "happy"}])
    assert directed([touched]) == {}   # written actions win


def test_an_arm_gesture_never_leaves_the_view() -> None:
    edge = frame(pip=(-FW / 2 + 0.9, "left"), kit=(3.5, "left"))   # facing out, an arm's length from the edge
    text = "That is a perfectly *ordinary* cardboard box, of course."
    assert directed([line("b1", text, ("pip",))], edge)["b1"][0]["to"] in ("nod", "shake_head")   # point and shrug would stick out
    assert directed([line("b1", text, ("pip",))], stage=DUO)["b1"][0]["to"] in GESTURES
    assert directed([line("b1", text, ("pip",))], stage=None)["b1"][0]["to"] in ("nod", "shake_head")   # no geometry: the head only


def test_predicted_stills_use_the_lint_rules() -> None:
    state = _SceneState(cast={m.name: m for m in MOVERS}, present={"pip", "kit"}, frame=DUO, x={"pip": -3.5, "kit": 3.5},
                        facing={"pip": "left", "kit": "left"}, camera_x=0.0)
    beat = _Beat(line("b1", "Hi.", ("pip",)), ("pip",), frozenset(), "park")
    assert still_findings(_still(state, beat)) == {("facing_away", ("pip", "kit"))}
    state.facing["pip"] = "right"
    state.x["pip"] = -FW / 2 + 0.2
    assert still_findings(_still(state, beat)) == {("off_stage", ("pip",))}


LONG = "Well, I have been thinking about kites for a very long time."


def test_a_closeup_for_a_short_line_after_a_long_one() -> None:
    beats = [line("b1", LONG, ("pip",), kinds=frozenset({"closeups"})), line("b2", "No, not today, my friend.", ("kit",), kinds=frozenset({"closeups"})),
             line("b3", "Why not?", ("pip",), kinds=frozenset({"closeups"}))]
    assert directed(beats) == {"b2": [{"zoom": "kit", "scale": CLOSEUP_SCALE, "run_time": CLOSEUP_SECONDS}]}
    quick = [beats[0], line("b2", "No.", ("kit",), kinds=frozenset({"closeups"}))]   # 0.33 s: cut in and back
    assert directed(quick) == {"b2": [{"zoom": "kit", "scale": CLOSEUP_SCALE, "run_time": CLOSEUP_CUT_SECONDS}]}
    again = [beats[0], beats[1], line("b3", LONG, ("pip",), kinds=frozenset({"closeups"})), line("b4", "Fine.", ("kit",), kinds=frozenset({"closeups"}))]
    assert sorted(directed(again)) == ["b2", "b4"]
    assert directed([beats[0], line("b2", "Hm.", ("kit",), kinds=frozenset({"closeups"}))], stage=None) == {}   # no geometry


@pytest.mark.parametrize("act", [
    {"walk_to": "pip", "to": "centre"}, {"action": "pan", "to": "left"}, {"zoom": "pip"}, {"say": "kit", "bubble": "No!"},
])
def test_no_closeup_during_a_move_or_with_a_bubble(act: dict[str, Any]) -> None:
    beats = [line("b1", LONG, ("pip",), kinds=frozenset({"closeups"})), line("b2", "No, not today, my friend.", ("kit",), [act], kinds=frozenset({"closeups"}))]
    assert directed(beats) == {}


def test_no_closeup_while_the_camera_follows_or_right_after_a_zoom() -> None:
    follow = line("b1", LONG, ("pip",), [{"follow": "pip"}], kinds=frozenset({"closeups"}))
    assert directed([follow, line("b2", "Not today.", ("kit",), kinds=frozenset({"closeups"}))]) == {}
    zoomed = line("b1", LONG, ("pip",), [{"zoom": "pip"}], kinds=frozenset({"closeups"}))
    assert directed([zoomed, line("b2", "Not today.", ("kit",), kinds=frozenset({"closeups"}))]) == {}


def test_a_closeup_that_would_turn_the_speaker_away_is_not_added() -> None:
    """Zoomed in on pip, kit (whom it talks to) is out of the view and rex, behind pip, is the
    nearest one: lint would report pip facing away."""
    trio = frame(pip=(0.0, "right"), kit=(5.0, "left"), rex=(-2.0, "right"))
    cast = [*MOVERS, CastMember("rex")]
    first = line("b1", LONG, ("kit",), [{"look_at": "pip", "to": "kit"}], kinds=frozenset({"closeups"}))
    short = line("b2", "No, not today, my friend.", ("pip",), kinds=frozenset({"closeups"}))
    assert directed([first, short], trio, cast) == {}
    clear = frame(pip=(0.0, "right"), kit=(2.5, "left"), rex=(-5.5, "right"))   # kit in the close-up's view
    assert directed([first, short], clear, cast) == {"b2": [{"zoom": "pip", "scale": CLOSEUP_SCALE, "run_time": CLOSEUP_SECONDS}]}


def test_a_look_that_would_add_a_lint_finding_is_not_added() -> None:
    """kit talks to pip, who has walked off the view's right edge (the camera stays left);
    turning kit right, away from rex beside it in view, would make lint report it facing away."""
    wide = StageFrame(FW, FH, 2 * FW, -FW / 2, {"kit": StagePlace(-FW / 2, FEET, HEIGHT, "left"), "rex": StagePlace(-FW / 2 - 2.5, FEET, HEIGHT, "right"),
                                                "pip": StagePlace(FW / 2, FEET, HEIGHT, "left")})
    cast = [CastMember("pip"), CastMember("kit"), CastMember("rex")]
    beats = [line("b1", "Hello.", ("pip",), kinds=frozenset()), line("b2", "Hello to you.", ("kit",), kinds=frozenset({"looks"}))]
    looks = directed(beats, wide, cast)["b2"]
    assert {"look_at": "kit", "to": "pip"} not in looks and {"look_at": "rex", "to": "kit"} in looks
    assert {"look_at": "kit", "to": "pip"} in directed(beats, None, cast)["b2"]   # without the geometry: as in Step 89


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
    # every beat of the example acts on both characters (explicit actions win), except one look in hill_told
    # and a gesture of moss on its longest word in yard_expert (its say only voices it)
    assert {sid: [(d.beat, [auto_label(a) for a in d.actions]) for d in beats] for sid, beats in directed.items()} == {
        "yard": [("yard_expert", ["gesture moss shake_head"])],
        "hill": [("hill_told", ["look_at moss dot"])],
    }


def test_stage_frame_places_the_characters_as_the_stage_does(make_project) -> None:
    project = directed_project(make_project, DIALOGUE, params={"marks": {"door": 0.6}, "props": [{"prop": "tree", "at": "door"}],
                                                               "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "door", "depth": 1, "facing": "left"}]})
    spec = project.scene("park")
    with extensions.project_session(project) as theme:
        made = stage_frame(project, registry.get("stage").cls.validate_params(spec.params, theme))
    fw = made.frame_width
    assert made.frame_height == 8.0 and made.stage_width == fw and made.camera_x == 0.0
    assert made.places["pip"] == StagePlace(-0.25 * fw, -2.4, 3.6, "right")
    kit = made.places["kit"]
    assert kit.x == pytest.approx(0.1 * fw) and kit.height == pytest.approx(3.6 * 0.55) and kit.feet_y > -2.4 and kit.facing == "left"
    assert made.props == {"tree": pytest.approx(0.1 * fw)} and made.place_x("door") == pytest.approx(0.1 * fw)


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


@pytest.mark.render
def test_gestures_and_a_closeup_render_and_lint_clean(make_project, capsys) -> None:
    """A long line with a stressed word, then a short answer: pip gestures, kit gets a close-up,
    and the cartoon lint rules find nothing in the rendered stills."""
    tiny = {"width": 160, "height": 90, "fps": 5}
    project = directed_project(make_project, [
        {"text": "This kite is truly REMARKABLE, it flies all day and all night long.", "voice": "pip_voice"},
        {"text": "Not today.", "voice": "kit_voice"},
    ], params={"characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}]}, auto_direct={"reactions": False},
        format=tiny, preview=tiny)
    with extensions.project_session(project):
        added = {d.beat: [auto_label(a) for a in d.actions] for d in project_directions(project)["park"]}
    assert any(a.startswith("gesture pip ") for a in added["park_b1"]) and "zoom kit 2" in added["park_b2"]
    rules = ["off_stage", "facing_away", "bubble_overlap", "character_overlap", "rushed_animation"]
    assert cli.main(["lint", str(project.root), "--json", "--fail-on", "warning", *[x for r in rules for x in ("--rule", r)]]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["findings"] == []


# ----- *word* emphasis: taken out of the spoken and shown text, kept for the planner ---------------------


def test_emphasis_marks_leave_the_text_but_not_the_marked_text() -> None:
    from vidgen.config import BeatConfig, strip_emphasis

    beat = BeatConfig(id="b", text="I *never* said *that one*, ok?")
    assert beat.text == "I never said that one, ok?" and beat.marked_text == "I *never* said *that one*, ok?"
    plain = BeatConfig(id="b", text="Hello there.")
    assert plain.text == plain.marked_text == "Hello there."
    for kept in ("a * b * c", "2*3*4", "**bold** stays", "a lone * star"):
        assert strip_emphasis(kept) == kept
    copied = beat.model_copy(update={"actions": []})   # with_auto_actions copies beats
    assert copied.marked_text == beat.marked_text


def test_emphasis_marks_are_not_spoken_and_unmarked_hashes_are_unchanged(make_project) -> None:
    """The TTS gets the text without asterisks; a beat without marks keeps its cache key (pinned)."""
    from vidgen import tts
    from vidgen.config import VoiceConfig
    from vidgen.render.fingerprint import scene_fingerprint

    scenes = [{"id": "intro", "type": "text_card", "params": {"text": "Hi"},
               "beats": [{"id": "plain", "text": "Hello there."}, {"id": "marked", "text": "Hello *there*."}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes)))
    spoken = project.spoken_texts()
    assert spoken == {"plain": "Hello there.", "marked": "Hello there."}
    kokoro = tts.get_provider(VoiceConfig(provider="kokoro"))
    assert kokoro.cache_key(spoken["plain"]) == kokoro.cache_key(spoken["marked"]) == "05cb88daec48cc27a4841b20f737de3c7cb847c4"
    assert tts.get_provider(VoiceConfig()).cache_key(spoken["plain"]) == "e07179cc8214a9008a163a96e3ab594f0d3da455"
    unmarked = Project.load(make_project(minimal_config(scenes=[{**scenes[0], "beats": [{"id": "plain", "text": "Hello there."}]}]), folder="p2"))
    assert scene_fingerprint(project, "intro") != scene_fingerprint(unmarked, "intro")


def test_emphasis_reaches_the_gesture_planner(make_project) -> None:
    """The planner still sees *word* (on the words of the stripped text), so the marked word
    picks the gesture: ``*you*`` points (unmarked, the line's negation would shake the head)."""
    project = directed_project(make_project, [
        {"text": "Look at this kite, it is the finest kite in town.", "voice": "pip_voice"},
        {"text": "Boxes never fly, and *you* know that.", "voice": "kit_voice"},
    ], params={"characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}]}, auto_direct={"gestures": True, "looks": False, "reactions": False, "closeups": False})
    assert project.beat("park_b2").text == "Boxes never fly, and you know that."
    with extensions.project_session(project):
        added = {d.beat: [a.shorthand() for a in d.actions] for d in project_directions(project)["park"]}
    assert [a for a in added["park_b2"] if a.get("gesture") == "kit"][0]["to"] == "point"
