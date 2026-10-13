"""Step 91: ``vidgen screenplay`` (a stage project from a screenplay). The parser, the set line,
the stage-direction grammar, voices and looks are tested without rendering; the sample in
``examples/screenplay`` is turned into a project that validates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen import cli
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.screenplay import (
    LOOKS,
    Direction,
    Line,
    StageState,
    assign_voices,
    character_id,
    direction_actions,
    manner_actions,
    parse_screenplay,
    parse_set,
    screenplay_project,
)

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "screenplay" / "humming_box.md"

PLAY = """---
title: Lantern Night
theme: {preset: soft_pastel}
---
# Ignored title

# Scene: porch
set: background: night; props: lamp (light) at 0.4, bench; marks: steps 0.85

<!-- a comment
     over two lines -->
The porch was dark, except for one small lamp.

WREN (excited, waving): Ash, look! The lamp
is blinking at us.
[Ash walks to the light and looks at it. The wind howls.]
OLD ASH (whispering): It is a moth, Wren. [shrugs] Just a moth.

# Scene: porch
[Wren exits left.]
OLD ASH: Goodnight, lamp.
[Ash jumps.]
"""


def stage(**x: float) -> StageState:
    names = {"wren": "wren", "ash": "ash"}
    return StageState(dict(x), dict(x), {"light": 0.4, "bench": 0.85}, {"light": "lamp", "bench": "chair"}, {"steps": 0.85}, names)


# ----- parsing ------------------------------------------------------------------------------------


def test_parse_screenplay_reads_scenes_lines_and_directions() -> None:
    play = parse_screenplay(PLAY)
    assert play.front == {"title": "Lantern Night", "theme": {"preset": "soft_pastel"}} and play.title == "Ignored title"
    first, second = play.scenes
    assert (first.name, second.name) == ("porch", "porch")
    assert first.set_text.startswith("background: night")
    narrator, wren, direction, ash = first.items
    assert isinstance(narrator, Line) and narrator.speaker is None and narrator.text.startswith("The porch was dark")
    assert isinstance(wren, Line) and (wren.speaker, wren.manner) == ("WREN", "excited, waving")
    assert wren.text == "Ash, look! The lamp is blinking at us."               # a line goes on until a blank line
    assert isinstance(direction, Direction) and direction.text.startswith("Ash walks to the light")
    assert isinstance(ash, Line) and ash.speaker == "OLD ASH" and ash.text == "It is a moth, Wren. Just a moth."
    assert [(d.text, d.at, d.speaker) for d in ash.directions] == [("shrugs", 0.62, "OLD ASH")]   # after 5 of 8 words
    assert [type(i).__name__ for i in second.items] == ["Direction", "Line", "Direction"]


@pytest.mark.parametrize(("text", "message"), [
    ("---\ntitle: x\n# Scene: a\nA: hi", "no closing ---"),
    ("---\nscenes: []\n---\n# Scene: a\nA: hi", "scenes come from"),
    ("# Scene: a\nA: hi\nset: background: day", "set: belongs right under"),
    ("# Scene: a\n[Ash walks\n\nA: hi", "does not end with ]"),
    ("# Title", "no scenes"),
])
def test_parse_screenplay_errors_name_the_problem(text: str, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        parse_screenplay(text)


def test_manner_words_become_expressions_and_poses() -> None:
    assert manner_actions("doubtful, arms crossed") == ({"expression": "thinking", "pose": "arms_crossed"}, [])
    assert manner_actions("Sad") == ({"expression": "sad"}, [])
    assert manner_actions("whispering, happy") == ({"expression": "happy"}, ["whispering"])


# ----- the set ------------------------------------------------------------------------------------


def test_parse_set_line() -> None:
    design = parse_set("background: night; props: lamp (light) at 0.4, bench, tree, house at far_left; marks: steps 0.85; "
                       "characters: wren at steps", {"wren": "wren"})
    params = design.params
    assert params["background"] == ["#1B2140", "#3D4677"] and params["ground_color"] == "#2E4A3A"
    assert params["props"] == [
        {"prop": "lamp", "name": "light", "at": 0.4},
        {"prop": "tree", "at": 0.85, "depth": 0.5},                               # first free slot; a tree goes back
        {"prop": "house", "at": "far_left", "depth": 0.6},
    ]
    assert design.props == {"light": "lamp", "tree": "tree", "house": "house"}
    assert params["marks"] == {"steps": 0.85} and design.placed == {"wren": "steps"}
    assert design.todos == ["set: prop 'bench' is not a built-in prop (" + design.todos[0].split("(", 1)[1]]
    colours = parse_set("background: primary to accent", {}).params
    assert colours == {"background": ["primary", "accent"], "ground_color": "tertiary"}
    assert parse_set("background: assets/park.png", {}).params == {"image": "assets/park.png"}
    unknown = parse_set("weather: rain; characters: zed at left", {})
    assert len(unknown.todos) == 2 and unknown.params["background"] == ["#9CCBEA", "#E4F3FB"]   # a day sky by default


# ----- stage directions ----------------------------------------------------------------------------


def test_direction_grammar() -> None:
    state = stage(wren=0.25, ash=0.75)
    groups, unmatched = direction_actions("Wren walks to the light and points at it. The wind howls.", state)
    walk, point = groups
    assert walk[0]["walk_to"] == "wren" and walk[0]["to"] == 0.3 and walk[0]["_seconds"] > 0   # stops before the lamp, on her side
    assert [a.get("look_at") or a.get("gesture") for a in point] == ["wren", "wren"] and point[0]["to"] == "light"
    assert unmatched == ["The wind howls"] and state.x["wren"] == 0.3

    def first(text: str, default: str | None = None) -> list[dict[str, Any]]:
        found, missed = direction_actions(text, state, default)
        assert not missed, missed
        return [{k: v for k, v in a.items() if not k.startswith("_")} for group in found for a in group]

    assert first("Ash enters from the right") == [{"enter": "ash", "side": "right"}]
    assert first("Ash leaves to the left quietly") == [{"exit": "ash", "side": "left"}]
    assert first("Wren and Ash jump for joy") == [{"jump": ["wren", "ash"]}]
    assert first("They look at each other") == [{"look_at": "wren", "to": "ash"}, {"look_at": "ash", "to": "wren"}]
    assert first("Wren looks at the camera") == [{"look_at": "wren", "to": "camera"}]
    assert first("She runs to the steps") == [{"walk_to": "wren", "to": "steps", "speed": 5.0}]
    assert first("Ash waves at Wren") == [{"look_at": "ash", "to": "wren"}, {"gesture": "ash", "to": "wave"}]
    assert first("Ash shakes his head. Then he nods") == [{"gesture": "ash", "to": "shake_head"}, {"gesture": "ash", "to": "nod"}]
    assert first("shrugs", default="wren") == [{"gesture": "wren", "to": "shrug"}]   # inside a line: the speaker
    assert direction_actions("Wren walks to Wren", state)[1] == ["Wren walks to Wren"]
    assert direction_actions("He sighs", state)[1] == ["He sighs"]


def test_two_walks_to_one_prop_end_apart() -> None:
    """Step 106: "Pip runs to the tree. Juno runs to the tree." ended both on one spot."""
    state = stage(wren=0.25, ash=0.6)
    state.props["tree"], state.kinds["tree"] = 0.84, "tree"
    groups, _ = direction_actions("Wren runs to the tree. Ash runs to the tree.", state)
    ends = [a["to"] for group in groups for a in group]
    assert ends == [0.74, 0.94] and state.x == {"wren": 0.74, "ash": 0.94}   # the other side of it
    edge = stage(wren=0.25, ash=0.4)
    edge.props["tree"], edge.kinds["tree"] = 0.9, "tree"
    both, _ = direction_actions("Wren and Ash walk to the tree.", edge)
    assert [a["to"] for a in both[0]] == [0.8, 0.66]   # no room behind it: a character's gap further out


def test_names_and_looks() -> None:
    assert character_id("OLD ASH") == "old_ash" and character_id("O'NEIL") == "o_neil"
    silhouettes = {(lk["look"]["body"], lk["look"].get("hair"), tuple(lk["look"].get("accessories", []))) for lk in LOOKS}
    assert len(silhouettes) == len(LOOKS)
    assert len({lk["colors"]["clothes"] for lk in LOOKS}) >= 5 and len({lk["colors"]["skin"] for lk in LOOKS}) == len(LOOKS)


# ----- voices -------------------------------------------------------------------------------------


def test_kokoro_voices_differ_in_gender_and_accent() -> None:
    settings, notes = assign_voices({"provider": "kokoro", "voice": "bf_emma"}, None, 5)
    voices = [s["voice"] for s in settings]
    assert not notes and len(set(voices)) == 5 and "bf_emma" not in voices
    assert {v[:2] for v in voices[:4]} == {"af", "am", "bf", "bm"} and voices[3][:2] == "bf"   # the narrator's kind last
    american, _ = assign_voices({"provider": "kokoro"}, "en-US", 2)
    assert [v["voice"][:2] for v in american] == ["am", "bf"]                                 # narrator af_heart's kind last
    spanish, _ = assign_voices({"provider": "kokoro"}, "es", 2)
    assert [v["voice"][0] for v in spanish] == ["e", "e"]
    assert all("santa" not in v["voice"] for v in assign_voices({"provider": "kokoro", "voice": "am_adam"}, None, 30)[0])


def test_kokoro_voices_follow_the_voice_kind() -> None:
    kinds = ["feminine", "masculine", "neutral", "feminine", "masculine"]
    settings, notes = assign_voices({"provider": "kokoro", "voice": "bf_emma"}, None, kinds)
    voices = [s["voice"] for s in settings]
    assert not notes and [v[:2] for v in voices] == ["af", "bm", "am", "bf", "bm"] and len(set(voices)) == 5   # accents alternate
    assert assign_voices({"provider": "kokoro", "voice": "bf_emma"}, None, [None, None])[0] == assign_voices({"provider": "kokoro", "voice": "bf_emma"}, None, 2)[0]


def test_pronoun_in_brackets_states_the_voice_kind() -> None:
    play = parse_screenplay("# Scene: a\nFEN (she, doubtful): Hi.\nBRAM (he/him): Yo.\nGUS (They): Hm.\nFEN: Again.")
    fen, bram, gus, again = play.scenes[0].items
    assert (fen.voice_kind, fen.manner) == ("feminine", "doubtful") and (bram.voice_kind, bram.manner) == ("masculine", "")
    assert gus.voice_kind == "neutral" and again.voice_kind is None
    assert manner_actions(fen.manner) == ({"expression": "thinking"}, [])
    with pytest.raises(VidgenError, match="line 2: a pronoun in brackets"):
        parse_screenplay("# Scene: a\nNARRATOR (she): Once.")
    with pytest.raises(VidgenError, match="line 3: fen is masculine here but feminine at line 2"):
        screenplay_project(parse_screenplay("# Scene: a\nFEN (she): Hi.\nFEN (he): Yo."))


def _cast(text: str) -> tuple[dict[str, Any], dict[str, str]]:
    config = screenplay_project(parse_screenplay(text)).config
    return {c["name"]: c for c in config["characters"]}, {name: v["voice"] for name, v in config["voices"].items()}


def test_generated_looks_and_voices_suit_each_other() -> None:
    by_name, voices = _cast("# Scene: a\nFEN: Hi.\nBRAM: Yo.\nGUS: Hm.")
    assert by_name["fen"]["look"]["hair"] == "bun" and voices["fen_voice"][1] == "f"            # a feminine look, a feminine voice
    assert by_name["bram"]["look"]["hair"] == "short" and voices["bram_voice"][1] == "m"
    assert voices["fen_voice"][0] != voices["bram_voice"][0]                                     # other accent
    assert all("voice_kind" not in c for c in by_name.values())
    stated, voices = _cast("# Scene: a\nFEN (he): Hi.\nBRAM (she): Yo.")
    assert LOOKS[1]["look"] == stated["fen"]["look"] and voices["fen_voice"][1] == "m"            # the look follows the stated kind
    assert LOOKS[0]["look"] == stated["bram"]["look"] and voices["bram_voice"][1] == "f"
    many, voices = _cast("# Scene: a\n" + "".join(f"P{k} (she): Hi.\n" for k in range(3)))
    # Step 113 added two feminine looks (ponytail, braids): a third "she" gets the ponytail, not the bun again
    assert [many[f"p{k}"]["look"].get("hair") for k in range(3)] == ["bun", "long", "ponytail"] and "seed" not in many["p2"]["look"]
    assert all(v[1] == "f" for v in voices.values()) and len(set(voices.values())) == 3
    more, _ = _cast("# Scene: a\n" + "".join(f"P{k} (she): Hi.\n" for k in range(5)))
    assert [more[f"p{k}"]["look"].get("hair") for k in range(5)] == ["bun", "long", "ponytail", "braids", "bun"] and more["p4"]["look"]["seed"] == 4


def test_declared_characters_keep_their_entries() -> None:
    text = ("---\ncharacters:\n  - {name: ash, look: {body: bean}, voice_kind: masculine}\n  - {name: wren, look: {body: tall}, voice: own}\n"
            "voices: {own: {voice: af_heart}}\n---\n# Scene: a\nASH: Hi.\nWREN (he): Yo.")
    by_name, voices = _cast(text)
    assert by_name["ash"] == {"name": "ash", "look": {"body": "bean"}, "voice": "ash_voice"} and voices["ash_voice"][1] == "m"
    assert by_name["wren"] == {"name": "wren", "look": {"body": "tall"}, "voice": "own"} and voices["own"] == "af_heart"   # its voice is kept
    with pytest.raises(VidgenError, match="voice_kind 'deep' is not one of"):
        _cast(text.replace("masculine", "deep"))


def test_other_providers_voices() -> None:
    routed, notes = assign_voices({"provider": "openrouter", "model": "canopylabs/orpheus-3b-0.1-ft", "voice": "tara"}, None, 2)
    assert routed == [{"voice": "leah"}, {"voice": "jess"}] and not notes
    eleven, notes = assign_voices({"provider": "elevenlabs"}, None, 2)
    assert eleven == [{}, {}] and "voice_id" in notes[0]
    draft = screenplay_project(parse_screenplay("---\nvoice: {provider: elevenlabs}\n---\n# Scene: a\nFEN: Hi.\nBRAM: Yo."))
    assert "(fen: feminine, bram: masculine)" in draft.notes[0]   # TODO: ElevenLabs has no voice list here


# ----- the project --------------------------------------------------------------------------------


def test_screenplay_project_builds_stage_scenes() -> None:
    draft = screenplay_project(parse_screenplay(PLAY.replace("---\n#", "characters:\n  - {name: old_ash, look: {body: bean}}\n---\n#")))
    config = draft.config
    assert config["title"] == "Lantern Night" and config["auto_direct"] is True and config["theme"] == {"preset": "soft_pastel"}
    by_name = {c["name"]: c for c in config["characters"]}
    assert by_name["old_ash"]["look"] == {"body": "bean"} and draft.generated == ["wren"]           # declared: kept
    assert by_name["wren"]["voice"] == "wren_voice" and config["voices"]["old_ash_voice"]["label"] == "Old Ash"
    porch, porch_2 = config["scenes"]
    assert (porch["id"], porch_2["id"]) == ("porch", "porch_2")
    assert porch["params"]["characters"] == [{"name": "wren", "at": "left"}, {"name": "old_ash", "at": "right"}]
    narrator, wren, ash = porch["beats"]
    assert "voice" not in narrator and wren["voice"] == "wren_voice"
    assert wren["actions"] == [{"react": "wren", "expression": "happy", "pose": "waving"}]
    walk, look, shrug = ash["actions"]                                                            # (whispering): no react
    assert walk["walk_to"] == "old_ash" and "at" not in walk and look["at"] > 0                     # the look waits for the walk
    assert shrug == {"gesture": "old_ash", "to": "shrug", "at": shrug["at"]} and 0.4 < shrug["at"] < 0.7
    todos = draft.beat_todos[0][2]
    assert any("The wind howls" in t for t in todos) and any("whispering" in t for t in todos)
    assert porch_2["beats"][0]["actions"][0] == {"exit": "wren", "side": "left"}
    assert porch_2["beats"][0]["actions"][1]["jump"] == "old_ash" and porch_2["beats"][0]["actions"][1]["at"] >= 0.6   # after the last line
    assert draft.todo_count == 3                                                                   # bench, wind, whispering


def test_a_scene_without_lines_is_an_error() -> None:
    with pytest.raises(VidgenError, match="has no lines"):
        screenplay_project(parse_screenplay("# Scene: a\nA: hi\n# Scene: b\n[A jumps]"))


# ----- round trip on the sample ------------------------------------------------------------------------


def test_sample_screenplay_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "box"
    assert cli.main(["screenplay", str(SAMPLE), "--out", str(out), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "screenplay" and doc["ok"] and doc["problems"] == [] and doc["todo_count"] == 0
    assert [c["name"] for c in doc["characters"]] == ["fen", "bram", "gus"] and all(c["generated"] for c in doc["characters"])
    assert [s["id"] for s in doc["scenes"]] == ["yard", "reveal"]
    text = (out / "video.yaml").read_text(encoding="utf-8")
    assert text.startswith("# Written by `vidgen screenplay`") and "# generated: fen, bram, gus" in text
    data = yaml.safe_load(text)
    voices = [v["voice"] for v in data["voices"].values()]
    assert len(set(voices)) == 3 and data["voice"]["voice"] not in voices
    project = Project.load(out)
    assert project.beat("yard_b3").text == "Boxes do not hum, Fen. Boxes do not do anything."   # *anything*: spoken plain
    assert cli.main(["direct", str(out), "--json"]) == 0
    direct = json.loads(capsys.readouterr().out)
    yard = {b["beat"]: b["actions"] for s in direct["scenes"] if s["scene"] == "yard" for b in s["beats"]}
    assert {"gesture": "bram", "to": "shake_head"} in [{k: v for k, v in a.items() if k != "at"} for a in yard["yard_b3"]]
    assert cli.main(["screenplay", str(SAMPLE), "--out", str(out)]) == 1                           # not empty: --force
    assert "--force" in capsys.readouterr().err
