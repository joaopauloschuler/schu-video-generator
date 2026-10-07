"""Step 43: named voices (``voices:``, per-scene / per-beat ``voice:``), their audio hashes,
TTS context, dry run and filter, validation, and speaker names in the SRT and captions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from manim import ManimColor

from conftest import minimal_config
from test_captions import built, load, narrated
from test_tts import FakeAPI, api, run  # noqa: F401  (fixture)
from vidgen import tts
from vidgen.cli import main, project_problems, validate_warnings
from vidgen.config import parse_config
from vidgen.cues import caption_cues
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.runtime import current_theme
from vidgen.subtitles import cues_from_timings
from vidgen.tts.run import context_texts, plan_tts
from vidgen.voices import resolve_voice, speaker_label, speaker_tags

ANA = {"voice_id": "ana_id", "settings": {"stability": 0.3}, "color": "secondary"}
BEN = {"voice_id": "ben_id", "label": "Dr. Ben"}


def dialogue(**extra: Any) -> dict[str, Any]:
    """intro (base voice) -> talk (scene voice ana, one beat by ben, one back to default) -> end (ana)."""
    scenes = [
        {"id": "intro", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Welcome to the show."}]},
        {
            "id": "talk",
            "type": "text_card",
            "params": {"text": "Talk"},
            "voice": "ana",
            "beats": [
                {"text": "Did you see the results?"},
                {"text": "Yes, they were great.", "voice": "ben"},
                {"text": "Tell me more.", "voice": "ana"},
                {"text": "Back to the narrator.", "voice": "default"},
            ],
        },
        {"id": "end", "type": "text_card", "params": {"text": "End"}, "voice": "ana", "beats": [{"text": "Thanks, Ben."}]},
    ]
    return minimal_config(scenes=scenes, voices={"ana": dict(ANA), "ben": dict(BEN)}, **extra)


def edit(root: Path, fn) -> None:
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    fn(data)
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# ----- config -----------------------------------------------------------------------------------


def test_named_voices_inherit_the_base_voice() -> None:
    config = parse_config(dialogue(voice={"model_id": "m1", "settings": {"style": 0.2}, "label": "Narrator", "color": "dim"}))
    ana = resolve_voice(config, "ana")
    assert (ana.voice_id, ana.model_id) == ("ana_id", "m1")
    assert ana.settings.model_dump() == {"stability": 0.3, "similarity_boost": 0.75, "style": 0.2, "use_speaker_boost": True}
    assert ana.label is None and ana.color == "secondary"   # the speaker's name / colour are its own
    assert resolve_voice(config, None) is config.voice and resolve_voice(config, "default") is config.voice
    assert speaker_label(config, "ana") == "Ana" and speaker_label(config, "ben") == "Dr. Ben"
    assert speaker_label(config, None) == "Narrator"
    with pytest.raises(VidgenError, match="unknown voice 'eve'"):
        resolve_voice(config, "eve")


def test_effective_voice_per_beat(make_project) -> None:
    project = Project.load(make_project(dialogue()))
    assert project.voice_names() == {
        "intro_b1": None, "talk_b1": "ana", "talk_b2": "ben", "talk_b3": "ana", "talk_b4": None, "end_b1": "ana",
    }
    assert project.beat_voice("talk_b2").voice_id == "ben_id"
    assert project.beat_voice("talk_b4") is project.config.voice


def test_unknown_names_and_the_reserved_default() -> None:
    data = dialogue()
    data["scenes"][1]["beats"][1]["voice"] = "bem"
    data["scenes"][2]["voice"] = "zed"
    with pytest.raises(VidgenError) as info:
        parse_config(data)
    locations = {p.location: p.message for p in info.value.problems}
    assert "did you mean 'ben'?" in locations["scenes[1].beats[1].voice"]
    assert "voices: default, ana, ben" in locations["scenes[2].voice"]
    with pytest.raises(VidgenError, match="'default' is the base voice"):
        parse_config(minimal_config(voices={"default": {"voice_id": "x"}}))
    with pytest.raises(VidgenError, match="unknown key 'voiceid'"):
        parse_config(minimal_config(voices={"ana": {"voiceid": "x"}}))


def test_validate_checks_colours_and_warns_about_unused_voices(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    data = dialogue()
    data["voices"]["eve"] = {"voice_id": "eve_id", "color": "no_such_colour"}
    project = Project.load(make_project(data))
    problems = {p.location: p.message for p in project_problems(project)}
    assert "unknown theme color 'no_such_colour'" in problems["voices.eve.color"]
    assert "voices: 'eve' is not used by any scene or beat" in validate_warnings(project)
    del data["voices"]["eve"]
    root = make_project(data, folder="ok")
    assert main(["validate", str(root)]) == 0
    assert "voices:    default (2 beats), ana (3 beats), ben (1 beats)" in capsys.readouterr().out


# ----- audio hashes, context, dry run ----------------------------------------------------------


def test_beats_without_a_voice_keep_their_hash(make_project) -> None:
    """Adding voices: changes nothing for beats of the base voice (kphi3's committed audio)."""
    root = make_project(dialogue())
    project = Project.load(root)
    providers = tts.beat_providers(project)
    base = tts.get_provider(project.config.voice)
    assert providers["intro_b1"].cache_key("x") == base.cache_key("x") == providers["talk_b4"].cache_key("x")
    assert providers["talk_b1"].cache_key("x") != base.cache_key("x") != providers["talk_b2"].cache_key("x")
    assert providers["talk_b1"] is providers["end_b1"]   # one provider per voice


def test_editing_one_speaker_revoices_only_their_beats(make_project, api: FakeAPI) -> None:
    root = make_project(dialogue())
    assert run(root) == 0
    assert len(api.requests) == 6
    urls = {api.body(i)["text"]: api.requests[i].full_url for i in range(6)}
    assert "/ben_id?" in urls["Yes, they were great."] and "/ana_id?" in urls["Tell me more."]
    assert "/nPczCjzI2devNBz1zQrb?" in urls["Back to the narrator."]
    assert api.body(0)["voice_settings"]["stability"] == 0.55 and api.body(1)["voice_settings"]["stability"] == 0.3
    edit(root, lambda d: d["voices"]["ben"].update(voice_id="ben2"))
    run(root)
    assert api.texts()[6:] == ["Yes, they were great."]
    # a speaker's name and colour are not part of the audio
    edit(root, lambda d: d["voices"]["ana"].update(label="Ana B.", color="accent"))
    run(root)
    # moving a beat to another voice re-voices that beat
    edit(root, lambda d: d["scenes"][2]["beats"][0].update(voice="ben"))
    run(root)
    assert api.texts()[7:] == ["Thanks, Ben."] and "/ben2?" in api.requests[-1].full_url


def test_context_only_from_neighbours_of_the_same_voice(make_project, api: FakeAPI) -> None:
    root = make_project(dialogue())
    project = Project.load(root)
    context = context_texts(project, project.spoken_texts())
    assert context["intro_b1"] == (None, None)                 # next beat: another speaker
    assert context["talk_b1"] == (None, None)                  # ben answers
    assert context["talk_b3"] == (None, None)                  # narrator next
    assert context["talk_b4"] == (None, None)                  # ana next
    run(root)
    assert all("previous_text" not in api.body(i) and "next_text" not in api.body(i) for i in range(6))
    edit(root, lambda d: d["scenes"][1]["beats"][3].pop("voice"))   # talk_b4 now ana: ana, ana, ana
    context = context_texts(Project.load(root), Project.load(root).spoken_texts())
    assert context["talk_b4"] == ("Tell me more.", "Thanks, Ben.")
    assert context["talk_b3"] == (None, "Back to the narrator.")


def test_dry_run_shows_voices_and_characters_per_voice(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(dialogue())
    assert run(root, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "would generate talk_b2.mp3 (21 chars, voice ben)" in out
    assert "would generate intro_b1.mp3 (20 chars, voice default)" in out
    assert "  voice default (nPczCjzI2devNBz1zQrb): 2 beat(s), 41 characters" in out
    assert "  voice ana (ana_id): 3 beat(s), 49 characters" in out
    assert "  voice ben (ben_id): 1 beat(s), 21 characters" in out
    assert run(root, "--dry-run", "--voice", "ben", "--voice", "default") == 0
    out = capsys.readouterr().out
    assert "dry run: 3 beat(s) to generate, 62 characters" in out and "voice ana" not in out
    assert run(root, "--dry-run", "--voice", "bem") == 1
    assert "unknown voice 'bem'; did you mean 'ben'?" in capsys.readouterr().err
    # without voices: the output is as before
    plain = make_project(minimal_config(), folder="plain")
    run(plain, "--dry-run")
    assert "would generate intro_b1.mp3 (12 chars)\n" in capsys.readouterr().out


def test_voice_filter_with_beats(make_project) -> None:
    project = Project.load(make_project(dialogue()))
    plan = plan_tts(project, voices=["ana"], beat_ids=["talk_b1", "talk_b2", "end_b1"])
    assert [b.id for b in plan.todo] == ["talk_b1", "end_b1"]
    assert plan.characters_by_voice() == {"ana": (2, 36)}


def test_variant_changing_one_speaker_gets_its_own_folder(make_project, api: FakeAPI) -> None:
    data = dialogue(variants={"other_ben": {"voices": {"ben": {"voice_id": "ben_fr"}}}, "relabel": {"voices": {"ben": {"label": "B"}}}})
    root = make_project(data)
    run(root)
    variant = Project.load(root, variant="other_ben")
    assert variant.has_own_audio and variant.audio_dir == root / "audio" / "other_ben"
    assert variant.beat_voice("talk_b1").voice_id == "ana_id"   # deep-merged: ana untouched
    assert not Project.load(root, variant="relabel").has_own_audio
    plan = plan_tts(variant)
    assert [b.id for b in plan.todo] == list(variant.voice_names()) and set(plan.reuse) == set(variant.voice_names()) - {"talk_b2"}
    assert run(root, "--variant", "other_ben") == 0
    assert api.texts()[6:] == ["Yes, they were great."] and "/ben_fr?" in api.requests[-1].full_url


@pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / "examples" / "kphi3" / "audio").is_dir(), reason="no kphi3 audio")
def test_kphi3_audio_stays_valid() -> None:
    project = Project.load(Path(__file__).resolve().parents[1] / "examples" / "kphi3")
    assert not project.config.voices
    assert {s.state for s in tts.audio_status(project)} == {"ok"}


# ----- speakers in subtitles and captions ------------------------------------------------------


def test_speaker_tags_where_the_speaker_changes() -> None:
    config = parse_config(dialogue())
    # the narrator has no label: no tag; ana and ben are tagged at each change
    assert speaker_tags(config) == {"talk_b1": "Ana", "talk_b2": "Dr. Ben", "talk_b3": "Ana", "end_b1": "Ana"}
    config = parse_config(dialogue(voice={"label": "Host"}))
    assert speaker_tags(config)["intro_b1"] == "Host" and speaker_tags(config)["talk_b4"] == "Host"


def test_caption_cue_prefix_is_glued_to_the_first_word() -> None:
    text = "Yes they were really great and everyone in the lab was happy with them"
    cues = caption_cues(text, 0.0, 4.0, max_width=20, max_lines=1, prefix="Dr. Ben:")
    assert cues[0].lines[0].startswith("Dr. Ben: Yes") and cues[0].prefix == "Dr. Ben:"
    assert all(c.prefix == "" for c in cues[1:])
    assert sum(len(c.words) for c in cues) == len(text.split())   # the tag is no spoken word
    assert " ".join(" ".join(c.lines) for c in cues) == f"Dr. Ben: {text}"


def test_srt_names_speakers_when_asked(make_project) -> None:
    timings = {"scenes": [{"beats": [
        {"id": "talk_b1", "start": 0.0, "end": 1.5, "text": "Did you see the results?"},
        {"id": "talk_b2", "start": 2.0, "end": 3.5, "text": "Yes, they were great."},
    ]}]}
    project = Project.load(make_project(dialogue(subtitles={"speakers": "name"})))
    texts = [c.text for c in cues_from_timings(timings, speakers=project.speaker_tags())]
    assert texts == ["Ana: Did you see the results?", "Dr. Ben: Yes, they were great."]
    off = Project.load(make_project(dialogue(), folder="off"))
    assert off.speaker_tags() == {} and off.config.subtitles.speakers == "off"
    assert [c.text for c in cues_from_timings(timings, speakers=off.speaker_tags())][0] == "Did you see the results?"


@pytest.mark.render
@pytest.mark.slow
def test_render_writes_speaker_names_into_the_srt(make_project) -> None:
    from vidgen.render.pipeline import render_project

    scenes = [
        {"id": "q", "type": "text_card", "params": {"text": "Q"}, "voice": "ana", "beats": [{"text": "Did it work?"}]},
        {"id": "a", "type": "text_card", "params": {"text": "A"}, "beats": [{"text": "It did.", "voice": "ben"}, {"text": "Good."}]},
    ]
    data = minimal_config(scenes=scenes, voices={"ana": {"voice_id": "a"}, "ben": {"voice_id": "b"}}, subtitles={"speakers": "name"},
                          preview={"width": 96, "height": 54, "fps": 5}, overlays=[{"type": "captions", "speakers": "both"}])
    result = render_project(Project.load(make_project(data)), preview=True, no_audio=True)
    srt = result.srt.read_text(encoding="utf-8")
    assert "\nAna: Did it work?\n" in srt and "\nBen: It did.\n" in srt and "\nGood.\n" in srt   # the narrator has no label


def _colours(line) -> list[str]:
    """Fill colours of a caption line's glyphs, spaces left out (Manim 0.21 keeps a glyph per space)."""
    glyphs = line.submobjects
    if len(glyphs) == len(line.original_text):
        glyphs = [g for g, ch in zip(glyphs, line.original_text) if ch != " "]
    return [ManimColor(g.get_fill_color()).to_hex().upper() for g in glyphs]


def _hexes(line) -> set[str]:
    return set(_colours(line))


def test_captions_name_and_colour_speakers(make_project) -> None:
    scenes = [narrated("a", "Hello there.", voice="ana"), {**narrated("b", "Fine thanks.", "And you?"), "voice": "ben"}]
    voices = {"ana": {"voice_id": "a", "color": "secondary"}, "ben": {"voice_id": "b", "label": "Ben"}}
    project = load(make_project, scenes, [{"type": "captions", "speakers": "both"}], voices=voices)
    (cap,) = built(project, "b")
    theme = current_theme()
    ben = ManimColor(theme.palette_color(1)).to_hex().upper()   # no colour given: palette by position
    first, second = cap.built.submobjects[1:]  # type: ignore[attr-defined]
    assert first.submobjects[1].original_text == "Ben: Fine thanks."
    assert _hexes(first.submobjects[1]) == {ben} and _hexes(second.submobjects[1]) == {ben}
    assert second.submobjects[1].original_text == "And you?"   # same speaker: no tag again
    # name only: the tag in the speaker's colour, the words in the text colour
    project = load(make_project, scenes, [{"type": "captions"}], voices=voices, subtitles={"speakers": "name"})
    (cap,) = built(project, "a")
    line = cap.built.submobjects[1].submobjects[1]  # type: ignore[attr-defined]
    assert line.original_text == "Ana: Hello there."
    secondary = ManimColor(current_theme().color("secondary")).to_hex().upper()
    assert ManimColor(line.submobjects[0].get_fill_color()).to_hex().upper() == secondary
    assert len(_hexes(line)) == 2
    assert len(cap._cues[0].glyphs) == 2   # type: ignore[attr-defined]   # karaoke word map skips the tag


def test_captions_karaoke_with_a_tag_highlights_spoken_words(make_project) -> None:
    project = load(make_project, [narrated("a", "Hello there my friend.", voice="ana")], [{"type": "captions", "style": "karaoke", "speakers": "name"}],
                   voices={"ana": {"voice_id": "a"}})
    (cap,) = built(project, "a", size=(180, 320))
    k, word = 0, 0
    posed = cap.pose(cap.built, (k, word))  # type: ignore[attr-defined]
    highlight = ManimColor(current_theme().color("highlight")).to_hex().upper()
    first_line = posed.submobjects[1]
    assert first_line.original_text.startswith("Ana: Hello")
    # the tag ("Ana:", 4 glyphs) is not highlighted, the first spoken word is
    colours = _colours(first_line)
    assert highlight not in colours[:4] and colours[4:9] == [highlight] * 5 and highlight not in colours[9:]


def test_fingerprint_follows_beat_voices_only_with_overlays(make_project) -> None:
    root = make_project(dialogue())
    before = scene_fingerprint(Project.load(root), "intro")
    edit(root, lambda d: d["voices"]["ana"].update(label="Ana B."))
    assert scene_fingerprint(Project.load(root), "intro") == before   # no overlays: labels change no pixels
    edit(root, lambda d: d.update(overlays=[{"type": "captions"}]))
    before = scene_fingerprint(Project.load(root), "intro")
    edit(root, lambda d: d["scenes"][1].update(voice="ben"))
    assert scene_fingerprint(Project.load(root), "intro") != before   # captions tag speakers by the order
