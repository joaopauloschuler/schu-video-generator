"""Shorts suggestions (DESIGN.md §105.6): windows timed from the plan, scores, hooks, the teaser,
the variants written to shorts.yaml (included by the config) and the CLI. No rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen import cli
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.shorts_suggest import (
    TEASER_SECONDS, Window, _with_include, candidate_windows, ending_beats, hook_line, pick_windows,
    score_window, shorten, suggest_shorts, timed_beats, write_suggestions,
)
from vidgen.videoplan import VideoPlan

HEADER = "# my notes on this video\n# second line\n"


def _beat(text: str, voice: str | None = None, **more: Any) -> dict[str, Any]:
    return {"text": text, **({"voice": voice} if voice else {}), **more}


def _config() -> dict[str, Any]:
    """A neutral sample: a calm opening (narration), a scene with an argument and questions, a
    tense scene, and an ending; 2 words per second."""
    calm = [_beat(f"The village slept under a grey sky and the baker counted his loaves number {n} again and again.") for n in range(1, 5)]
    argue = [
        _beat("Mira found the door of the mill open.", actions=[{"walk_to": "mira", "to": 0.6}]),
        _beat("Who left this open?", "mira_voice"),
        _beat("Not me! I locked it at night!", "teo_voice"),
        _beat("Then where is the flour?", "mira_voice"),
        _beat("Someone took it. We have to find them before the storm.", "teo_voice"),
        _beat("They ran out into the wind together.", actions=[{"run_to": "teo", "to": 0.9}]),
    ]
    storm = [
        _beat("Thunder broke over the hills and the rain came down hard on the road."),
        _beat("Help! Over here!", "mira_voice"),
        _beat("A cart lay stuck in the mud, full of flour sacks, and a boy sat crying beside it."),
        _beat("Are you hurt?", "teo_voice"),
        _beat("I only wanted bread for my sister.", "boy_voice"),
    ]
    ending = [
        _beat("In the morning the three of them pulled the cart back to the mill and baked bread for the whole village."),
        _beat("And from then on the boy worked at the mill every day, and the door was never locked again."),
    ]
    stage = lambda chars: {"characters": [{"name": c, "at": 0.3 + 0.3 * k} for k, c in enumerate(chars)]}   # noqa: E731
    return {
        "title": "The Open Door",
        "voice": {"provider": "kokoro", "voice": "bf_emma"},
        "narration": {"words_per_second": 2.0, "pad": 0.4},
        "voices": {"mira_voice": {"voice": "af_heart"}, "teo_voice": {"voice": "bm_fable"}, "boy_voice": {"voice": "am_adam"}},
        "characters": [{"name": "mira", "voice": "mira_voice"}, {"name": "teo", "voice": "teo_voice"}, {"name": "boy", "voice": "boy_voice"}],
        "overlays": [{"type": "watermark", "text": "demo"}, {"type": "captions"}],
        "scenes": [
            {"id": "title", "type": "card", "params": {"text": "The Open Door"}, "duration": 2},
            {"id": "village", "type": "stage", "params": stage(["mira"]), "beats": calm},
            {"id": "mill", "type": "stage", "params": stage(["mira", "teo"]), "beats": argue},
            {"id": "storm", "type": "stage", "params": stage(["mira", "teo", "boy"]), "beats": storm},
            {"id": "morning", "type": "stage", "params": stage(["mira", "teo", "boy"]), "beats": ending},
            {"id": "end", "type": "end_card", "params": {"title": "The End"}, "duration": 2},
        ],
    }


def _project(tmp_path: Path, config: dict[str, Any] | None = None, header: str = HEADER) -> Path:
    folder = tmp_path / "proj"
    folder.mkdir(exist_ok=True)
    (folder / "video.yaml").write_text(header + yaml.safe_dump(config or _config(), sort_keys=False), encoding="utf-8")
    return folder


# ----- timing, windows, scores -------------------------------------------------------------


def test_beats_are_timed_from_the_plan(tmp_path: Path) -> None:
    project = Project.load(_project(tmp_path))
    beats, outros = timed_beats(project)
    assert [b.id for b in beats][:2] == ["village_b1", "village_b2"] and len(beats) == 17
    assert all(b.end <= c.start + 1e-6 for b, c in zip(beats, beats[1:]))
    plan = VideoPlan(project, project.config.format.fps)
    assert beats[0].start == pytest.approx(plan.scene_start("village"))
    second = beats[1]
    assert second.seconds == pytest.approx(len(second.text.split()) / 2.0 + 0.4, abs=0.05)   # word-count estimate + pad
    assert beats[5].speaker == "mira_voice" and beats[4].speaker is None
    assert {b.run for b in beats} == {1}   # one run of narrated scenes (the cards are outside it)
    assert outros["stage"] >= 0
    assert ending_beats(beats) >= {"morning_b2"}


def test_windows_lie_between_min_and_max(tmp_path: Path) -> None:
    beats, outros = timed_beats(Project.load(_project(tmp_path)))
    windows = candidate_windows(beats, outros, 20, 30)
    assert windows and all(20 - 1e-6 <= w.seconds <= 30 + 1e-6 for w in windows)
    assert all([b.id for b in w.beats] == [b.id for b in beats if w.start - 1e-6 <= b.start < w.end - 1e-6] for w in windows)
    assert candidate_windows(beats, outros, 500, 600) == []


def test_dialogue_and_questions_score_above_narration(tmp_path: Path) -> None:
    beats, outros = timed_beats(Project.load(_project(tmp_path)))
    ending = ending_beats(beats)
    by_id = {b.id: k for k, b in enumerate(beats)}
    calm = Window(beats[by_id["village_b1"]:by_id["village_b4"] + 1], 30.0)
    argue = Window(beats[by_id["mill_b1"]:by_id["storm_b2"] + 1], 30.0)
    for w in (calm, argue):
        score_window(w, beats, ending)
    assert argue.score > calm.score + 5
    assert argue.parts["question"] > 0 and argue.parts["exclaim"] > 0 and argue.parts["dialogue"] > calm.parts["dialogue"]
    late = Window(beats[by_id["storm_b4"]:], 30.0)
    score_window(late, beats, ending)
    assert late.spoils and late.parts["spoiler"] < 0
    score_window(late, beats, ending, spoilers=True)
    assert late.spoils and late.parts["spoiler"] == 0


def test_a_clean_start_scores_better(tmp_path: Path) -> None:
    beats, _ = timed_beats(Project.load(_project(tmp_path)))
    by_id = {b.id: k for k, b in enumerate(beats)}
    scene_start = Window(beats[by_id["mill_b1"]:by_id["mill_b4"] + 1], 30.0)
    reply = Window(beats[by_id["mill_b3"]:by_id["mill_b6"] + 1], 30.0)   # opens on Teo's answer
    leaning = Window(beats[by_id["mill_b6"]:by_id["storm_b3"] + 1], 30.0)   # "They ran out..."
    for w in (scene_start, reply, leaning):
        score_window(w, beats, set())
    assert scene_start.parts["start"] == 1.0 and reply.parts["start"] < 0 and leaning.parts["start"] < 0


def test_picked_windows_barely_overlap(tmp_path: Path) -> None:
    beats, outros = timed_beats(Project.load(_project(tmp_path)))
    windows = candidate_windows(beats, outros, 15, 25)
    ending = ending_beats(beats)
    for w in windows:
        score_window(w, beats, ending)
    picked = pick_windows(windows, 3)
    assert picked[0].score == max(w.score for w in windows)
    for k, a in enumerate(picked):
        for b in picked[k + 1:]:
            assert a.overlap(b) <= 0.25 * min(a.end - a.start, b.end - b.start) + 1e-6


# ----- hooks -------------------------------------------------------------------------------


@pytest.mark.parametrize(("sentence", "hook"), [
    ("Will the lamp work tonight?", "Will the lamp work tonight?"),
    ("But why do you still climb all the way up there?", None),
    ("I know, but where did the flour go?", "Where did the flour go?"),
    ("So, we must hurry now!", "We must hurry now!"),
    ("So, we have to find them before the storm!", None),
    ("Help!", None),
])
def test_shorten(sentence: str, hook: str | None) -> None:
    assert shorten(sentence) == hook


def test_hooks_prefer_spoken_questions_then_templates(tmp_path: Path) -> None:
    beats, _ = timed_beats(Project.load(_project(tmp_path)))
    by_id = {b.id: k for k, b in enumerate(beats)}
    window = Window(beats[by_id["mill_b1"]:by_id["mill_b5"] + 1], 30.0)
    assert hook_line(window) == ("Who left this open?", "question")
    calm = Window(beats[by_id["village_b1"]:by_id["village_b4"] + 1], 30.0)
    assert hook_line(calm) == ("Wait for the ending.", "template")
    stormy = Window([beats[by_id["storm_b1"]]], 10.0)
    assert hook_line(stormy) == ("Caught in the storm.", "template")


# ----- suggestions written -----------------------------------------------------------------


def test_suggest_write_and_validate(tmp_path: Path) -> None:
    folder = _project(tmp_path)
    project = Project.load(folder)
    found = suggest_shorts(project, count=2, min_seconds=20, max_seconds=35, teaser=True)
    assert [s.name for s in found.shorts] == ["short1", "short2"] and found.teaser is not None and found.timed_by == "words"
    best = found.shorts[0]
    assert "mill_b2" in [b.id for b in best.window.beats] and not best.window.spoils
    result = write_suggestions(project, found)
    assert result.config_changed and result.file == folder / "shorts.yaml"
    text = (folder / "video.yaml").read_text(encoding="utf-8")
    assert text.startswith(HEADER + "include: [shorts.yaml]\n")   # comments kept, the include added after them
    assert (folder / "video.yaml.bak").read_text(encoding="utf-8").startswith(HEADER + "title:")
    variants = yaml.safe_load((folder / "shorts.yaml").read_text(encoding="utf-8"))["variants"]
    assert set(variants) == {"short1", "short2", "teaser"}
    short = variants["short1"]
    assert short["format"] == {"width": 1080, "height": 1920} and short["shorts"] is True
    assert short["overlays"] == [{"type": "watermark", "text": "demo"}, {"type": "captions", "style": "karaoke", "speakers": "color"}]
    assert short["cut"]["end_card"] == "Full story on the channel" and len(short["cut"]["hook"].split()) <= 6
    first = short["cut"]["scenes"][0]
    first_beat = best.window.beats[0].id
    zoom = short["cut"]["beats"][first_beat]["actions"][0]
    assert zoom["at"] == 0 and zoom["cut"] is True and "zoom" in zoom
    if isinstance(first, dict):
        assert first["beats"]["from"] == first_beat
    loaded = Project.load(folder)
    assert set(loaded.config.variants) == {"short1", "short2", "teaser"}
    problems, variants_loaded = cli.validate_all(loaded, keep_going=True)
    assert problems == [] and all(v is not None for v in variants_loaded.values())
    for name, suggestion in (("short1", best), ("short2", found.shorts[1])):
        planned = VideoPlan(variants_loaded[name], 30).duration   # type: ignore[arg-type]
        assert planned <= 35 + 0.5 and planned == pytest.approx(suggestion.window.seconds, abs=1.5)
    teaser = variants["teaser"]["cut"]
    assert teaser["end_card"]["type"] == "card"
    ids = [s if isinstance(s, str) else s["scene"] for s in teaser["scenes"]]
    assert len(ids) == len(set(ids)) and "morning" not in ids   # one entry per scene; no ending
    assert sum(b.seconds for b in found.teaser.window.beats) <= TEASER_SECONDS + 1e-6
    again = write_suggestions(Project.load(folder), found)
    assert not again.config_changed and again.backups == (folder / "shorts.yaml.bak",)


def test_own_variant_names_are_kept(tmp_path: Path) -> None:
    config = _config()
    config["variants"] = {"short1": {"format": {"width": 1080, "height": 1920}}}
    found = suggest_shorts(Project.load(_project(tmp_path, config)), count=2, min_seconds=20, max_seconds=35)
    assert [s.name for s in found.shorts] == ["short2", "short3"]


@pytest.mark.parametrize(("text", "expected"), [
    ("title: x\n", "include: [shorts.yaml]\ntitle: x\n"),
    ("# c\ninclude: cast.yaml   # cast\ntitle: x\n", '# c\ninclude: ["cast.yaml", "shorts.yaml"]\ntitle: x\n'),
    ("include: [a.yaml, b.yaml]\ntitle: x\n", 'include: ["a.yaml", "b.yaml", "shorts.yaml"]\ntitle: x\n'),
    ("include:\n    - a.yaml\ntitle: x\n", "include:\n    - shorts.yaml\n    - a.yaml\ntitle: x\n"),
    ("include: [shorts.yaml]\ntitle: x\n", None),
])
def test_include_line(text: str, expected: str | None) -> None:
    assert _with_include(text, yaml.safe_load(text), "shorts.yaml") == expected


def test_errors(tmp_path: Path) -> None:
    project = Project.load(_project(tmp_path))
    with pytest.raises(VidgenError, match="--min"):
        suggest_shorts(project, min_seconds=50, max_seconds=40)
    found = suggest_shorts(project, min_seconds=500, max_seconds=600)
    assert found.shorts == [] and found.candidates == 0
    with pytest.raises(VidgenError, match="give a .yaml file name"):
        write_suggestions(project, suggest_shorts(project, min_seconds=20, max_seconds=35), "../x.yaml")


def test_cli_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _project(tmp_path)
    assert cli.main(["shorts", "suggest", str(folder), "--min", "20", "--max", "35", "--count", "2", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "shorts" and doc["ok"] and len(doc["shorts"]) == 2 and doc["written"] is None
    first = doc["shorts"][0]
    assert first["name"] == "short1" and first["seconds"] <= 35 and first["hook"] and first["variant"]["cut"]["end_card"]
    assert not (folder / "shorts.yaml").exists()
    assert cli.main(["shorts", "suggest", str(folder), "--min", "20", "--max", "35", "--write", "--teaser", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["written"]["config_changed"] and doc["teaser"]["name"] == "teaser" and doc["problems"] == []
    assert cli.main(["validate", str(folder), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]


STORY = """# The Kite

## The hill

Ana carried her new kite up the hill. The wind was strong and the grass bent flat.

"Will it fly?" asked Ben.

"Of course it will!" Ana said. She ran down the slope and let the string go.

The kite rose, higher and higher, until it was a red dot in the clouds.

## The tree

Then the string snapped. The kite drifted over the field and caught in the tallest tree.

"No! It's stuck!" Ana cried.

Ben looked up at the branches. "I can climb it," he said. "Hold the ladder."

He climbed slowly. The branches shook in the wind, and Ana held her breath.

"Got it!" Ben shouted at last.

## Home

They walked home in the evening with the torn kite between them. Tomorrow they would fix it together.
"""


def test_a_drafted_story_gets_shorts_that_validate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "kite.md"
    source.write_text(STORY, encoding="utf-8")
    assert cli.main(["story", "draft", str(source), "-o", str(tmp_path / "kite"), "--json"]) == 0
    capsys.readouterr()
    assert cli.main(["shorts", "suggest", str(tmp_path / "kite"), "--min", "15", "--max", "30", "--count", "2", "--write", "--teaser"]) == 0
    out = capsys.readouterr().out
    assert "rank" in out and "short1" in out and "wrote" in out
    variants = yaml.safe_load((tmp_path / "kite" / "shorts.yaml").read_text(encoding="utf-8"))["variants"]
    for variant in variants.values():
        for change in variant["cut"].get("beats", {}).values():
            zoom = change["actions"][0]
            assert zoom["cut"] is True and set(zoom) >= {"zoom", "at"}
    assert cli.main(["validate", str(tmp_path / "kite")]) == 0
