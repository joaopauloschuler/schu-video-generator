"""Actions timed to a spoken word (DESIGN.md §87.2): ``at: "@gradient"`` on beat actions (scene,
callout, stage and sound actions), ``lower_third``'s ``at``, the estimate before any audio, the
beat's audio once it exists, errors naming the beat, translations, and one tiny render."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from conftest import minimal_config
from vidgen.cli import main, project_problems
from vidgen.config import BeatConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.speech import estimate_word_times, write_alignment
from vidgen.word_anchors import (
    MAX_FRACTION,
    WordAnchor,
    find_words,
    parse_word_anchor,
    pin_translated_anchors,
)

TEXT = "Follow the gradient down; the Gradient knows the way."
BULLETS = {"heading": "Steps", "items": ["Loss", "Gradient", "Step"]}


def beat(actions: list[dict[str, Any]], text: str = TEXT, **extra: Any) -> BeatConfig:
    return BeatConfig.model_validate({"id": "b1", "text": text, "actions": actions, **extra})


def bullets_scene(actions: list[dict[str, Any]], text: str = TEXT) -> dict[str, Any]:
    return {"id": "s", "type": "bullets", "params": BULLETS, "beats": [{"text": text, "actions": actions}]}


def tone(path: Path, seconds: float, rate: int = 16000) -> Path:
    """A WAV tone (PyAV reads it whatever the file is called)."""
    t = np.arange(int(seconds * rate)) / rate
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16).tobytes())
    return path


def align(audio: Path, beat_id: str, text: str, seconds: float, step: float) -> None:
    """An MP3 of ``seconds`` with a stored alignment: one character every ``step`` seconds."""
    mp3 = tone(audio / f"{beat_id}.mp3", seconds)
    chars = list(text)
    alignment = {
        "characters": chars,
        "character_start_times_seconds": [k * step for k in range(len(chars))],
        "character_end_times_seconds": [(k + 1) * step for k in range(len(chars))],
    }
    write_alignment(audio, beat_id, text, mp3.read_bytes(), alignment)


# ----- syntax -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "anchor"),
    [
        ("@gradient", WordAnchor(("gradient",))),
        ("  @Gradient#2 ", WordAnchor(("Gradient",), 2)),
        ("@gradient+0.3s", WordAnchor(("gradient",), 1, 0.3)),
        ("@gradient#2 - .25 s", WordAnchor(("gradient",), 2, -0.25)),
        ("@learning rate", WordAnchor(("learning", "rate"))),
        ("@K-Phi-3", WordAnchor(("K-Phi-3",))),          # a hyphen without "s" is part of the word
        ('@"loss,"', WordAnchor(("loss",))),             # punctuation around the word is dropped
    ],
)
def test_word_anchor_syntax(text: str, anchor: WordAnchor) -> None:
    assert parse_word_anchor(text) == anchor


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("@", "which word?"),
        ("@ ,", "which word?"),
        ("@loss#0", "#N counts from 1"),
        ("b2@loss", "an action's word is in its own beat; write '@loss'"),
        ("@loss@grad", "a word anchor is @WORD"),
    ],
)
def test_word_anchor_syntax_errors(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_word_anchor(text)


def test_an_overlay_may_name_the_beat() -> None:
    assert parse_word_anchor("intro_b2@Ada#2-0.2s", beat_allowed=True) == WordAnchor(("Ada",), 2, -0.2, "intro_b2")


def test_find_words_ignores_case_accents_and_punctuation() -> None:
    words = "Você sees the gradient, then the GRADIENT; learning rate: done".split()
    assert find_words(parse_word_anchor("@gradient"), words, "b") == 3
    assert find_words(parse_word_anchor("@gradient#2"), words, "b") == 6
    assert find_words(parse_word_anchor("@voce"), words, "b") == 0
    assert find_words(parse_word_anchor("@learning rate"), words, "b") == 7
    with pytest.raises(ValueError, match=r"""beat 'b' does not say "gradiant" \(words like it: gradient\)"""):
        find_words(parse_word_anchor("@gradiant"), words, "b")
    with pytest.raises(ValueError, match=r"""beat 'b' says "gradient" 2 times, so there is no #3"""):
        find_words(parse_word_anchor("@gradient#3"), words, "b")
    with pytest.raises(ValueError, match=r"does not say \"zebra\" \(its words: Você, sees, the, gradient"):
        find_words(parse_word_anchor("@zebra"), words, "b")


# ----- the config: the estimate ------------------------------------------------------------------


def test_beat_resolves_anchors_with_the_estimate() -> None:
    b = beat([{"reveal": "item2", "at": "@gradient"}, {"dim": "item1", "at": "@gradient#2+0.5s"}, {"highlight": "item3", "at": 0.25}])
    seconds = b.estimated_duration(2.6)
    times = estimate_word_times(TEXT.split(), 0.0, seconds)
    first, second, plain = b.actions
    assert first.at == pytest.approx(times[2].start / seconds) and first.anchor == "@gradient"
    assert second.at == pytest.approx((times[5].start + 0.5) / seconds) and second.anchor == "@gradient#2+0.5s"
    assert plain.at == 0.25 and plain.anchor is None
    assert 0 < first.at < second.at < 1


def test_anchor_is_written_back_as_written() -> None:
    b = beat([{"callout": "item2", "label": "slope", "at": "@gradient#2"}])
    act = b.actions[0]
    assert act.shorthand() == {"callout": "item2", "label": "slope", "at": "@gradient#2"}
    assert act.model_dump()["at"] == "@gradient#2"
    again = beat([act.model_dump(exclude_none=True)])
    assert again.actions[0].at == act.at and again.actions[0].anchor == "@gradient#2"
    copied = act.model_copy()
    assert copied.anchor == "@gradient#2" and copied.at == act.at


def test_resolved_shorthand_keeps_the_fraction() -> None:
    b = beat([{"label": "slope", "callout": "item2", "at": "@knows"}])   # keys sorted by a tool
    act = b.actions[0]
    fixed = act.resolved({"callout"})
    assert fixed.action == "callout" and fixed.at == act.at > 0.5 and fixed.anchor == "@knows"


def test_offset_past_the_ends_is_clamped() -> None:
    b = beat([{"reveal": "item1", "at": "@Follow-3s"}, {"reveal": "item2", "at": "@way+9s"}])
    assert [a.at for a in b.actions] == [0.0, MAX_FRACTION]


@pytest.mark.parametrize(
    ("at", "message"),
    [
        ("@gradiant", "beat 's_b1' does not say \"gradiant\" (words like it: gradient)"),
        ("@gradient#3", "beat 's_b1' says \"gradient\" 2 times, so there is no #3"),
        (1.0, "at 1: a fraction of the beat's narration, 0 <= at < 1"),
        ("half", "Input should be a valid number"),
    ],
)
def test_config_errors_name_the_beat(at: Any, message: str) -> None:
    with pytest.raises(VidgenError) as info:
        parse_config(minimal_config(scenes=[bullets_scene([{"reveal": "item2", "at": at}])]))
    assert message in str(info.value)
    assert "scenes[0].beats[0]" in str(info.value.problems[0].location)


def test_video_language_and_speech_rate_refine_the_estimate() -> None:
    scenes = [bullets_scene([{"reveal": "item2", "at": "@gradient+1s"}])]
    slow = parse_config(minimal_config(scenes=scenes, narration={"words_per_second": 1.0}))
    fast = parse_config(minimal_config(scenes=scenes, narration={"words_per_second": 4.0}))
    words = len(TEXT.split())
    times = estimate_word_times(TEXT.split(), 0.0, 1.0)
    # the word's own share is the same; the second's offset is a smaller share of a longer beat
    assert slow.scenes[0].beats[0].actions[0].at == pytest.approx(times[2].start + 1.0 / words)
    assert fast.scenes[0].beats[0].actions[0].at == pytest.approx(times[2].start + 4.0 / words)


def test_scene_sfx_list_points_to_the_sfx_action() -> None:
    scene = {**bullets_scene([]), "sfx": [{"sound": "pop", "at": "@gradient"}]}
    with pytest.raises(VidgenError, match=r"a scene's sfx list is timed in seconds; for a sound on a spoken word use the beat's sfx action"):
        parse_config(minimal_config(scenes=[scene]))


def test_every_kind_of_action_validates_with_a_word(make_project) -> None:
    """Scene actions, a callout, a sound, and stage actions (moves, acting) all take a word."""
    stage = {
        "id": "st", "type": "stage", "params": {"characters": [{"name": "kit", "at": "left"}]},
        "beats": [{"text": "Kit walks over, waves and smiles at the end.", "voice": None, "actions": [
            {"walk_to": "kit", "to": "right", "at": "@walks"},
            {"gesture": "kit", "to": "wave", "at": "@waves"},
            {"emote": "kit", "to": "happy", "at": "@smiles"},
            {"sfx": "pop", "at": "@end-0.1s"},
        ]}],
    }
    data = minimal_config(
        scenes=[bullets_scene([{"reveal": "item2", "at": "@gradient"}, {"callout": "item2", "label": "slope", "at": "@knows"}]), stage],
        characters=[{"name": "kit", "look": {"species": "cat"}}],
    )
    project = Project.load(make_project(data))
    assert project_problems(project) == []
    acts = project.config.scenes[1].beats[0].actions
    assert [a.anchor for a in acts] == ["@walks", "@waves", "@smiles", "@end-0.1s"]
    assert all(isinstance(a.at, float) for a in acts) and [a.at for a in acts] == sorted(a.at for a in acts)


# ----- the project: the beat's audio ------------------------------------------------------------------


def test_audio_alignment_times_the_word(make_project) -> None:
    root = make_project(minimal_config(scenes=[bullets_scene([{"reveal": "item2", "at": "@gradient"}, {"dim": "item1", "at": "@way-0.1s"}])]))
    align(root / "audio", "s_b1", TEXT, 6.0, 0.1)
    project = Project.load(root)
    first, second = project.config.scenes[0].beats[0].actions
    assert first.at == pytest.approx(TEXT.index("gradient") * 0.1 / 6.0)
    assert second.at == pytest.approx((TEXT.index("way") * 0.1 - 0.1) / 6.0)
    # without the audio the estimate is used
    (root / "audio" / "s_b1.mp3").unlink()
    estimate = Project.load(root).config.scenes[0].beats[0].actions[0].at
    assert estimate != pytest.approx(first.at, abs=1e-3)


def test_word_said_differently_is_still_found(make_project) -> None:
    """Pronunciation changes what the TTS says; the anchor names the written word."""
    text = "Train the KPhi model now."
    data = minimal_config(scenes=[bullets_scene([{"reveal": "item2", "at": "@model"}], text=text)], pronunciation={"KPhi": "kay fye"})
    root = make_project(data)
    spoken = "Train the kay fye model now."
    align(root / "audio", "s_b1", spoken, 4.0, 0.1)
    project = Project.load(root)
    assert project.config.scenes[0].beats[0].actions[0].at == pytest.approx(spoken.index("model") * 0.1 / 4.0)


def test_translated_beat_keeps_the_source_moment(make_project) -> None:
    data = minimal_config(scenes=[bullets_scene([{"reveal": "item2", "at": "@gradient"}])])
    data["variants"] = {"pt": {"language": "pt-BR", "translations": "pt.yaml"}}
    root = make_project(data)
    assert main(["translate-template", str(root), "--variant", "pt", "--output", str(root / "pt.yaml")]) == 0
    doc = yaml.safe_load((root / "pt.yaml").read_text(encoding="utf-8"))
    (key,) = [k for k in doc["entries"] if k.endswith("s_b1.text")]
    doc["entries"][key]["text"] = "Siga o gradiente para baixo; ele conhece o caminho."
    (root / "pt.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    source = Project.load(root).config.scenes[0].beats[0].actions[0].at
    translated = Project.load(root, variant="pt").config.scenes[0].beats[0]
    assert translated.text.startswith("Siga") and translated.actions[0].at == pytest.approx(source, abs=1e-4)


def test_pin_translated_anchors_only_where_the_text_changed() -> None:
    raw = minimal_config(scenes=[bullets_scene([{"reveal": "item2", "at": "@gradient"}]), {**bullets_scene([{"reveal": "item1", "at": "@way"}]), "id": "t"}])
    config = parse_config(raw)
    translated = yaml.safe_load(yaml.safe_dump(raw))
    translated["scenes"][0]["beats"][0]["text"] = "Outro texto."
    pin_translated_anchors(translated, raw, config)
    assert translated["scenes"][0]["beats"][0]["actions"][0]["at"] == round(config.scenes[0].beats[0].actions[0].at, 4)
    assert translated["scenes"][1]["beats"][0]["actions"][0]["at"] == "@way"


# ----- lower_third --------------------------------------------------------------------------------------


def test_lower_third_starts_at_a_word(make_project) -> None:
    scenes = [
        {"id": "s", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Hello there."}, {"text": "Meet Ada Lovelace, our guest."}]},
    ]
    good = minimal_config(scenes=scenes, overlays=[{"type": "lower_third", "name": "Ada Lovelace", "at": "@Ada"}])
    root = make_project(good)
    align(root / "audio", "s_b1", "Hello there.", 1.0, 0.05)
    align(root / "audio", "s_b2", "Meet Ada Lovelace, our guest.", 3.0, 0.1)
    project = Project.load(root)
    assert project_problems(project) == []
    from manim import tempconfig

    from vidgen import extensions
    from vidgen.overlays import scene_overlays
    from vidgen.videoplan import VideoPlan

    with tempconfig({"frame_rate": 5}):
        plan = VideoPlan(project, 5)
        (lower,) = scene_overlays(project, project.scene("s"), extensions.activate(project), plan)
    slot = plan.scene("s")
    assert lower.window()[0] == pytest.approx(slot.start + slot.beats[1].start + len("Meet ") * 0.1, abs=1e-6)
    bad = minimal_config(scenes=scenes, overlays=[{"type": "lower_third", "name": "Ada", "at": "s_b1@Ada"}])
    problems = [str(p) for p in project_problems(Project.load(make_project(bad, folder="bad")))]
    assert any("beat 's_b1' does not say \"Ada\"" in p for p in problems), problems


# ----- one tiny render --------------------------------------------------------------------------------


@pytest.mark.render
def test_action_plays_on_its_word(make_project, tmp_path: Path) -> None:
    from manim import tempconfig

    from vidgen import extensions, registry
    from vidgen.render.worker import frame_size

    root = make_project(minimal_config(scenes=[bullets_scene([{"highlight": "item1", "at": "@knows"}])], narration={"pad": 0.2}))
    align(root / "audio", "s_b1", TEXT, 5.0, 0.08)
    project = Project.load(root)
    w, h = 160, 90
    fw, fh = frame_size(w, h)
    settings = {"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": 5,
                "media_dir": str(tmp_path / "media"), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR", "output_file": "s"}
    with tempconfig(settings):
        spec = project.scene("s")
        theme = extensions.activate(project)
        scene = registry.get(spec.type).cls(spec, project, theme)
        scene.finish = lambda: None
        scene.render()
    (record,) = [p for p in scene.play_log if p.animations == ("Repaint",)]
    start = next(t.start for t in scene.beat_log if t.beat_id == "s_b1")
    assert record.start == pytest.approx(start + TEXT.index("knows") * 0.08, abs=0.5 / 5)
