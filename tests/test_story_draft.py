"""Step 272: ``vidgen story draft`` (a story cartoon drafted from prose, no AI). The reader (scenes,
characters, attribution, person), the keyword tables (places, light, weather, music, objects) and
the draft are tested without rendering; three short sample stories of our own become projects
that ``vidgen validate`` accepts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen import cli
from vidgen.story_draft import DraftOptions, draft_story, report_markdown, story_yaml
from vidgen.story_places import PLACES, choose_place, light_cues, music_of, objects_named, weather_of
from vidgen.story_text import beat_groups, find_characters, person_of, read_story, segments, split_scenes

THIRD = """# The Kite in the Tree

Nora and her grandfather lived in a small cottage by the village green. One windy morning, Nora found her red kite stuck in the old tree.

"Grandpa, my kite is stuck!" Nora shouted.

Grandpa Bram looked up and laughed. "That tree has eaten three kites this year," he said.

"Can you reach it?"

"Not with these old knees. But I know who can."

Nora ran to the lane and knocked on the blue door. Her friend Theo came out, still holding a piece of toast.

"What's wrong?" Theo asked.

"My kite is in the tree again," she said quietly.

* * *

That evening the wind dropped. Theo climbed the ladder while Nora held it steady.

"Got it!" he called.
"""

FIRST = """My name is Lena, and I work the night shift at a small café near the old market.

At 3 AM the café was empty. I was wiping the counter when the door opened and a tall man in a wet coat walked in.

“Are you still open?” he asked.

“For coffee, always,” I said.

He sat by the window and stared at the rain. His name, he told me later, was Marco.

“Do you ever get lonely here?” Marco asked.

I thought about it. “Not when people like you come in.”
"""

BREAKS = """# Signal

## The Lab

Doctor Ada Vale checked the console for the tenth time. The signal from the old dish had stopped at midnight.

“It just went quiet,” said Kai, her assistant.

“Signals don't just go quiet,” she replied. “Check the servers.”

Kai hurried to the racks. The lights blinked green, then red.

## The Roof

Outside, rain hammered the city streets. Ada climbed up to the roof, where the old dish pointed at the clouds.

“There you are,” she whispered.

***

The next morning the rain had gone. Kai found Ada asleep in the lab.

“Did you fix it?” he asked.
"""


def dialogue(story_text: str) -> list[tuple[str | None, str, float]]:
    story = read_story(story_text)
    return [(line.speaker, line.text, line.confidence) for scene in story.scenes for line in scene.lines if line.dialogue]


# ----- reading ----------------------------------------------------------------------------------------


def test_scenes_split_at_headings_breaks_and_time_cues() -> None:
    title, scenes = split_scenes(BREAKS)
    assert title == "Signal"
    assert [(s.heading, s.reason) for s in scenes] == [("The Lab", "heading"), ("The Roof", "heading"), (None, "scene break")]
    _, scenes = split_scenes("Ann woke up.\n\nShe ate.\n\nThe next morning it snowed.\n\nLater that day she left.\n")
    assert [s.reason for s in scenes] == ["start", "time cue: 'The next morning'"]   # a cue needs two paragraphs before it
    assert len(split_scenes("One.\nTwo.\n# \nThree.\n")[1]) == 2                      # a lone # is a break
    assert segments("“Go,” said Mara, “now.” She ran.") == [(True, "Go,"), (False, "said Mara,"), (True, "now."), (False, "She ran.")]
    assert segments('"Unclosed to the end') == [(True, "Unclosed to the end")]
    long = " ".join(f"Sentence number {k} has some words in it." for k in range(6))
    assert [len(group.split()) for group in beat_groups(long)] == [24, 24]   # three 8-word sentences a beat
    assert beat_groups("Dr. Vale arrived. She sat.") == ["Dr. Vale arrived. She sat."]


def test_characters_titles_kinds_and_places() -> None:
    found = find_characters(THIRD)
    assert sorted(found) == ["bram", "nora", "theo"]
    assert found["bram"].name == "Grandpa Bram" and found["bram"].kind == "masculine" and found["bram"].kind_source == "title Grandpa"
    assert found["nora"].kind == "feminine" and found["theo"].kind == "masculine"
    found = find_characters("Doctor Ada Vale smiled. Ada said hello. They flew to London. In London it rained. Mum laughed. Mum said no.")
    assert found["ada"].name == "Doctor Ada Vale" and found["ada"].kind == "feminine"
    assert "london" not in found and found["mum"].kind == "feminine"
    found = find_characters("Quill opened the box. She smiled at it. Quill said nothing, and she left. The robot Quill hummed.")
    assert found["quill"].kind == "feminine" and found["quill"].kind_source.startswith("pronouns") and found["quill"].effect == "robot"


def test_dialogue_attribution_with_confidence() -> None:
    lines = dialogue(THIRD)
    assert lines[0][:2] == ("nora", "Grandpa, my kite is stuck!") and lines[0][2] > 0.9      # "Nora shouted"
    assert lines[1][:2] == ("bram", "That tree has eaten three kites this year.")             # "he said" after Bram
    assert [s for s, _, _ in lines[2:4]] == ["nora", "bram"] and all(c == 0.5 for _, _, c in lines[2:4])   # alternation
    assert lines[4][0] == "theo" and lines[5][0] == "nora" and lines[6][0] == "theo"
    story = read_story(THIRD)
    quietly = next(line for scene in story.scenes for line in scene.lines if line.text.startswith("My kite"))
    assert quietly.emotion == "whisper" and quietly.method.startswith("tag 'she said")
    narration = [line.text for scene in story.scenes for line in scene.lines if not line.dialogue]
    assert "Grandpa Bram looked up and laughed." in narration and not any("said" in t for t in narration)   # tags left out
    lines = dialogue(BREAKS)
    assert lines[0][0] == "kai" and lines[1] == ("ada", "Signals don't just go quiet. Check the servers.", 0.75)   # merged
    assert lines[2][0] == "ada" and lines[3][0] == "kai"
    lines = dialogue('"Who is there?"\n\nNobody answered.\n')
    assert lines == [(None, "Who is there?", 0.1)]


def test_first_person_and_moves() -> None:
    first, note, name = person_of(FIRST)
    assert first and name == "Lena" and "first-person words" in note
    assert not person_of(THIRD)[0]
    story = read_story(FIRST)
    assert story.first_person and story.characters["lena"].protagonist
    lines = dialogue(FIRST)
    assert [s for s, _, _ in lines] == ["marco", "lena", "marco", "lena"]   # "he asked" before Marco is named: the man named later
    assert lines[0][2] == 0.5 and lines[1][2] == 0.9
    story = read_story(THIRD)
    moves = [(m.who, m.kind) for scene in story.scenes for line in scene.lines for m in line.moves]
    assert ("nora", "run") in moves and ("theo", "enter") in moves and ("theo", "walk") in moves
    story = read_story("Pip left the key on the table. Then Pip walked away.\n")
    assert [(m.who, m.kind) for line in story.scenes[0].lines for m in line.moves] == [("pip", "exit")]


# ----- keyword tables -------------------------------------------------------------------------------------


def test_places_light_weather_music_objects() -> None:
    assert choose_place("The lab hummed; the console glowed.", None).place == "lab"
    assert choose_place("Nothing here.", "harbour").place == "harbour" and choose_place("Nothing.", None).place == "village"
    assert choose_place("Rain on the city streets and the roof.", None).place == "city"
    assert [p for _, p, _ in light_cues("At 3 AM it was quiet. By 8 a.m. the sun was up.")] == ["night", "morning"]
    assert [p for _, p, _ in light_cues("It was three in the morning.")] == ["night"]
    assert [p for _, p, _ in light_cues("That evening, under the stars")] == ["sunset", "night"]
    assert weather_of("The rain had stopped. Fog rolled in.") == {"fog": ["fog"]}
    assert set(weather_of("A storm: rain and wind.")) == {"rain", "wind"}
    assert music_of("A quiet, sad goodbye.")[0] == "calm" and music_of("No mood here.")[0] == "cartoon"
    found = objects_named("The old dish and the telescope; a lamp.", PLACES["city"])
    assert [(w, k) for w, k, _ in found] == [("dish", "satellite_dish"), ("telescope", "telescope"), ("lamp", "lamp")]
    assert [c for _, _, c in found] == list(PLACES["city"].free)
    assert objects_named("a telescope", PLACES["city"], found) == []          # the place has it now
    harbour = PLACES["harbour"].iso(False, objects_named("the lamp", PLACES["harbour"]))   # its street lamp is named 'lamp'
    names = [o["name"] for o in harbour["objects"] if "name" in o]   # unnamed ones are numbered by the stage
    assert len(names) == len(set(names)) and "lamp_2" in names
    for place in PLACES.values():   # spots of the stands and goals exist on the map
        assert set(place.stands) | set(place.goals) <= set(place.spots.values()), place.name
        assert len(place.free) == 3 and len(place.stands) == 4


# ----- the draft ------------------------------------------------------------------------------------------


@pytest.mark.slow
def test_draft_scenes_staging_and_report() -> None:
    draft = draft_story(read_story(BREAKS), DraftOptions())
    config = draft.config
    assert [s["id"] for s in config["scenes"]] == ["title", "the_lab", "the_roof", "lab", "end"]
    lab, roof, morning = config["scenes"][1:4]
    assert lab["set"] == "lab" and lab["params"]["light"] == "night" and lab["params"]["fill_light"] == 0.45
    assert roof["set"] == "city_night" and roof["params"]["light"] == "night"                  # still night: no new cue
    assert roof["params"]["particles"][0]["kind"] == "rain" and "fog" not in roof["params"]
    assert morning["params"]["light"] == "indoor" and "particles" not in morning["params"]     # the rain had gone
    assert {"run_to": "kai", "to": "bench", "at": 0.05} in lab["beats"][3]["actions"]
    whisper = roof["beats"][-1]
    assert whisper["voice"] == "ada_voice" and whisper["emotion"] == "whisper" and whisper["shot"] == "closeup ada"
    objects = {o["object"] for o in config["sets"]["city_night"]["iso"]["objects"]}
    assert "satellite_dish" in objects                                                      # "the old dish"
    assert all(o.get("on") for o in config["sets"]["city_night"]["iso"]["objects"] if o.get("name") in ("lamp_1", "lamp_2"))
    assert config["music"]["source"] == "lab" and config["voice"]["voice"] == "bf_emma"
    voices = [v["voice"] for v in config["voices"].values()]
    assert len(set(voices)) == len(voices) and "bf_emma" not in voices
    report = report_markdown(draft, "signal.md", "video.yaml")
    assert "## Dialogue attribution" in report and "| the_lab | 2 | kai | 95% |" in report and "- [ ] " in report
    text = story_yaml(draft, "signal.md")
    assert yaml.safe_load(text) == config and text.startswith("# Draft written by `vidgen story draft`")


def test_draft_first_person_flat_and_vertical() -> None:
    draft = draft_story(read_story(FIRST), DraftOptions(style="flat", fmt="9:16"))
    config = draft.config
    assert config["format"]["height"] > config["format"]["width"] and "sets" not in config
    scene = config["scenes"][1]
    assert scene["set"] == "shop" and scene["params"]["light"] == "night"
    assert [c["at"] for c in scene["params"]["characters"]] == ["stand_left", "stand_right"]
    assert config["voices"]["lena_voice"]["voice"] == config["voice"]["voice"]                # the narrator is Lena
    assert any("speaker guessed" in t for beat in draft.beat_comments[1] for t in beat)       # the 50 % line
    draft = draft_story(read_story(THIRD), DraftOptions(narrator="am_michael"))
    first = draft.config["scenes"][1]
    assert first["id"] == "village_morning" and first["params"]["wind"] == "windy"
    assert draft.config["scenes"][2]["params"].get("wind") is None                           # the wind dropped
    entering = [a for b in first["beats"] for a in b.get("actions", []) if "enter" in a]
    assert entering == [{"enter": "theo", "to": "middle", "side": "right", "at": 0.6}]


BRITISH = """# The Lamp

That night the wind rattled the cottage windows. Wren sat by the fire with Grandpa.

‘Grandpa! The lamp on the hill is out!’

Grandpa put down his net. ‘Then someone must light it, and I don’t think it’ll be the wind.’

‘I’ll come with you,’ said Wren.

At the top an old man was waiting with a box of matches. ‘You’re late,’ said the old man.

‘We came as fast as we could,’ Grandpa replied. A girl called Rosa waved from the gate.
"""


def test_british_quotes_described_speakers_and_calls_by_name() -> None:
    """Step 275: single curly quotes hold the speech of a story without double quotes (not the
    apostrophes inside); ``said the old man`` makes a character; a line calling a character by
    name is the other one's; ``a girl called Rosa`` names her, it is no speech."""
    lines = dialogue(BRITISH)
    assert [s for s, _, _ in lines] == ["wren", "grandpa", "wren", "old_man", "grandpa"]
    assert lines[1][1] == "Then someone must light it, and I don’t think it’ll be the wind."
    assert lines[0][2] == 0.55   # "Grandpa! ...": not Grandpa's, not the narrator's
    story = read_story(BRITISH)
    old = story.characters["old_man"]
    assert old.name == "Old man" and old.kind == "masculine" and old.described == "old man" and "girl" not in story.characters
    assert segments("It’s Kai’s turn, she said.") == [(False, "It’s Kai’s turn, she said.")]   # no quotes by default
    mixed = dialogue('"He said ‘no’ to me," said Ada.\n')
    assert mixed == [("ada", "He said ‘no’ to me.", 0.95)]   # with double quotes a ‘ is a quote inside one


def test_title_card_and_life_follow_the_story() -> None:
    """Step 275: a night story's title card is dark with neon letters, a cosy one's warm; outdoor
    places get a little ambient life (fireflies at night), rooms none."""
    from vidgen.story_draft import CARD_LOOKS, card_mood

    draft = draft_story(read_story(BRITISH), DraftOptions())
    card = draft.config["scenes"][0]["params"]
    assert card["color"] == CARD_LOOKS["night"]["color"] and card["style"] == "frame"
    village = draft.config["scenes"][1]
    assert village["params"]["ambient"]["fireflies"] > 0 and "walkers" not in village["params"]["ambient"]
    assert card_mood(["day"], "cartoon", "A cosy kitchen, warm tea and a blanket.") == "cosy"
    assert card_mood(["day", "day"], "cartoon", "A sunny day.") is None and card_mood(["day"], "lullaby", "") == "bedtime"
    lab = draft_story(read_story(BREAKS), DraftOptions()).config["scenes"][1]
    assert "ambient" not in lab["params"]   # a room


def run_cli(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    code = cli.main([*args, "--json"])
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.slow
@pytest.mark.parametrize("name, text, style", [("kite", THIRD, "iso"), ("night", FIRST, "iso"), ("signal", BREAKS, "iso"), ("flat", BREAKS, "flat")])
def test_cli_projects_validate(tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, text: str, style: str) -> None:
    source = tmp_path / f"{name}.md"
    source.write_text(text, encoding="utf-8")
    code, doc = run_cli(["story", "draft", str(source), "-o", str(tmp_path / name), "--style", style], capsys)
    assert code == 0 and doc["command"] == "story" and doc["ok"] and doc["problems"] == [], doc.get("problems")
    assert Path(doc["report"]).name == "story_draft.md" and doc["report_text"].startswith("# Story draft")
    assert doc["dialogue"] and all(0 <= d["confidence"] <= 1 for d in doc["dialogue"])
    assert cli.main(["validate", str(tmp_path / name), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]


def test_cli_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "s.md"
    source.write_text(THIRD, encoding="utf-8")
    code, doc = run_cli(["story", "draft", str(source), "--narrator", "bf_emmma", "-o", str(tmp_path / "p")], capsys)
    assert code == 1 and "did you mean 'bf_emma'" in doc["error"]["message"]
    code, doc = run_cli(["story", "draft", str(tmp_path / "missing.md")], capsys)
    assert code == 1 and "no such file" in doc["error"]["message"]
    assert run_cli(["story", "draft", str(source), "-o", str(tmp_path / "p")], capsys)[0] == 0
    code, doc = run_cli(["story", "draft", str(source), "-o", str(tmp_path / "p")], capsys)
    assert code == 1 and "--force" in doc["error"]["message"]
