"""Step 283: audio-only renders, audio-only projects (``sections:``), timing without pictures,
explicit pauses and ``vidgen story draft --audio`` (DESIGN.md §111). Narration is mocked: each
beat's "MP3" is a WAV tone (PyAV reads it by its content)."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import cli, extensions, loudness, mix, sfx
from vidgen.audio_only import plan_audio, render_audio
from vidgen.config import parse_config
from vidgen.errors import Problem, VidgenError
from vidgen.project import Project
from vidgen.sections import expand_sections
from vidgen.sfx import RATE, STING_SOUNDS, SoundLibrary, write_wav
from vidgen.videoplan import VideoPlan

STORY: dict[str, Any] = {
    "title": "T",
    "narration": {"pad": 0.3, "words_per_second": 2},
    "voices": {"b": {"voice_id": "other"}},
    "pacing": {"speaker": 0.7, "scene": 1.1, "chapter": 2.2, "lead_in": 0.5, "tail": 1.5, "sting_before": 0.6, "sting_after": 0.4},
    "sections": [
        {"id": "one", "title": "One", "sfx": [{"sound": "chime", "at": 0.1}], "beats": [
            "one two three four",
            {"text": "five six seven eight"},
            {"text": "a b c d", "voice": "b"},
            {"pause": 1.0},
        ]},
        {"pause": 2.0},
        {"id": "two", "beats": [
            {"text": "e f g h", "sting": "reveal"},
            {"text": "i j k l", "voice": "b", "sting": "comic"},
            {"text": "m n o p", "actions": [{"sfx": "pop", "at": 0.5}]},
        ]},
        {"id": "three", "title": "Three", "beats": ["q r s t"]},
    ],
}


def _write(root: Path, data: dict[str, Any]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return root


def _voice_all(project: Project, seconds: float = 1.2) -> None:
    """A mock narration: a quiet tone of ``seconds`` for every beat (a different pitch each)."""
    t = np.arange(round(seconds * RATE)) / RATE
    for k, (_, beat) in enumerate(project.beats()):
        write_wav(project.audio_dir / f"{beat.id}.mp3", (0.2 * np.sin(2 * np.pi * (200 + 40 * k) * t)).astype(np.float32))


def _read_24(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as src:
        assert (src.getnchannels(), src.getsampwidth(), src.getframerate()) == (2, 3, RATE)
        raw = np.frombuffer(src.readframes(src.getnframes()), dtype=np.uint8).reshape(-1, 3)
    ints = raw[:, 0].astype(np.int32) | raw[:, 1].astype(np.int32) << 8 | raw[:, 2].astype(np.int8).astype(np.int32) << 16
    return (ints / 8388608).reshape(-1, 2)


# ----- sections and pauses ------------------------------------------------------------------------


def test_sections_become_scenes(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "p", STORY))
    scenes = project.config.scenes
    assert [(s.id, s.type, s.silent) for s in scenes] == [("one", "text_card", False), ("s2", "text_card", True), ("two", "text_card", False), ("three", "text_card", False)]
    assert scenes[0].chapter == "One" and scenes[0].params == {"text": "One"} and scenes[2].params == {"text": "T"} and scenes[2].chapter is None
    assert [b.id for b in scenes[0].beats] == ["one_b1", "one_b2", "one_b3"] and scenes[0].beats[2].pause == 1.0   # the pause item
    assert scenes[1].duration == 2.0 and scenes[0].sfx[0].sound == "chime"
    assert expand_sections({"title": "x", "scenes": []}) == {"title": "x", "scenes": []}   # no sections: as it is


@pytest.mark.parametrize("sections, message", [
    ([{"title": "a", "beets": ["x"]}], "unknown key 'beets'; did you mean 'beats'?"),
    ([{"pause": 1, "beats": ["x"]}], "a pause section has no beats"),
    ([{"title": "a"}], "a section needs beats"),
    ([], "a list of sections"),
    ([{"beats": [{"pause": 1}, "x"]}], "a pause item adds silence after the beat before it"),
])
def test_section_problems(tmp_path: Path, sections: list[Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        Project.load(_write(tmp_path / "p", {"title": "t", "sections": sections}))


def test_scenes_and_sections_not_both() -> None:
    with pytest.raises(VidgenError, match="not both"):
        expand_sections({"title": "t", "scenes": [], "sections": []})


def test_section_problems_name_the_sections(tmp_path: Path) -> None:
    """Problems of a project written with sections point at the sections, not the scenes they
    become (Step 286)."""
    data = {"title": "t", "sections": [{"title": "A", "beats": [{"text": "x", "voise": "b"}]}, {"pause": -1}]}
    with pytest.raises(VidgenError) as caught:
        Project.load(_write(tmp_path / "p", data))
    locations = [p.location for p in caught.value.problems]
    assert "sections[0].beats[0].voise" in locations and "sections[1].pause" in locations
    assert "scenes[" not in str(caught.value) and "sections[0].beats[0].voise" in str(caught.value)
    with pytest.raises(VidgenError, match=r"sections\[1\]\.pause"):
        parse_config(data)
    project = Project.load(_write(tmp_path / "q", STORY))   # later checks (vidgen validate) too
    problems = project.attributed([Problem("scenes[2].beats[0].text", "bad in scenes[2]"), Problem("scenes[0].chapter", "x")])
    assert project.from_sections and [str(p) for p in problems] == ["sections[2].beats[0].text: bad in sections[2]", "sections[0].title: x"]


def test_no_youtube_chapter_warnings_for_audio_only_projects(tmp_path: Path) -> None:
    """Two chapters: too few for YouTube, which matters for a video, not for an audio-only project."""
    from vidgen.chapter_export import chapter_warnings

    assert any("YouTube shows chapters only" in w for w in chapter_warnings(Project.load(_write(tmp_path / "v", STORY))))
    assert chapter_warnings(Project.load(_write(tmp_path / "a", {**STORY, "audio_only": True}))) == []


def test_a_beats_pause_times_the_video_too(tmp_path: Path) -> None:
    data = {"title": "t", "narration": {"words_per_second": 2, "pad": 0.3}, "scenes": [
        {"id": "a", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "one two"}, {"pause": 1.5}, {"text": "three four"}, {"text": "five six"}]},
    ]}
    project = Project.load(_write(tmp_path / "p", data))
    beats = VideoPlan(project, 30).scene("a").beats
    assert [b.start for b in beats] == pytest.approx([0.0, 2.5, 3.8])   # 1 s + the pause, then 1 s + the pad
    plain = Project.load(_write(tmp_path / "q", {**data, "scenes": [{**data["scenes"][0], "beats": [{"text": "one two"}, {"text": "three four"}]}]}))
    assert [b.start for b in VideoPlan(plain, 30).scene("a").beats] == pytest.approx([0.0, 1.3])   # no pause: unchanged


# ----- timing ------------------------------------------------------------------------------------------


def test_speech_timing_gaps(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "p", STORY))
    plan = plan_audio(project)
    assert plan.timing == "speech"
    starts = {b.id: round(b.start, 6) for b in plan.beats}
    comic = len(SoundLibrary(None).audio(STING_SOUNDS["comic"], {})) / RATE
    assert starts["one_b1"] == 0.5 and starts["one_b2"] == 2.8 and starts["one_b3"] == 5.5   # lead-in, line gap, speaker gap
    scenes = {s.spec.id: s for s in plan.scenes}
    assert scenes["one"].duration == pytest.approx(8.5)          # the last line's pause replaces the scene gap
    assert scenes["s2"].start == pytest.approx(8.5) and scenes["s2"].duration == 2.0
    assert starts["two_b1"] == pytest.approx(10.5) and starts["two_b2"] == pytest.approx(13.2)
    assert starts["two_b3"] == pytest.approx(15.2 + max(0.7, comic + 0.4))   # the comic sting plays after the line
    assert starts["three_b1"] == pytest.approx(starts["two_b3"] + 2.0 + 2.2)  # a chapter starts there
    assert plan.duration == pytest.approx(starts["three_b1"] + 2.0 + 1.5)     # the tail
    events = [(e.sound, round(e.time, 6), e.duck) for e in plan.events]
    assert ("chime", 0.1, False) in events and ("sting_reveal", 9.9, True) in events   # 0.6 s before the line
    assert ("sting_comic", 15.2, True) in events and ("pop", round(starts["two_b3"] + 1.0, 6), False) in events
    assert plan_audio(project).beats == plan.beats   # deterministic


def test_speech_timing_joins_interrupted_lines(tmp_path: Path) -> None:
    data = {"title": "t", "narration": {"words_per_second": 2}, "voices": {"b": {"voice_id": "x"}}, "pacing": {"lead_in": 0},
            "sections": [{"beats": ["one two three four", {"text": "no wait", "voice": "b", "interrupt": True, "overlap": 0.5}]}]}
    plan = plan_audio(Project.load(_write(tmp_path / "p", data)))
    first, second = plan.beats
    assert second.start == pytest.approx(1.5) and first.shape.cut == pytest.approx(1.5)


def test_video_timing_follows_the_video_plan(tmp_path: Path) -> None:
    data = {**STORY, "variants": {"video": {"pacing": {"timing": "video"}}}}
    project = Project.load(_write(tmp_path / "p", data), variant="video")
    with extensions.project_session(project):
        plan = plan_audio(project)
        video = VideoPlan(project, project.config.format.fps)
        expected = [round(s.start + b.start, 6) for s in video.scenes for b in s.beats]
        assert plan.timing == "video" and [round(b.start, 6) for b in plan.beats] == expected
        assert plan.duration == pytest.approx(video.duration)
    silent = Project.load(_write(tmp_path / "q", {**STORY, "pacing": {**STORY["pacing"], "silent": 0.5}}))
    assert {s.spec.id: s.duration for s in plan_audio(silent).scenes}["s2"] == 0.5


# ----- rendering ---------------------------------------------------------------------------------------


VIDEO: dict[str, Any] = {
    "title": "Video",
    "output": "talk",
    "music": {"source": "calm"},
    "audio": {"normalize": True, "target_lufs": -18},
    "scenes": [
        {"id": "intro", "type": "title", "params": {"title": "Hello"}, "beats": [{"text": "Hello and welcome."}, {"text": "Let us start.", "sting": "reveal"}]},
        {"id": "card", "type": "text_card", "params": {"text": "x"}, "duration": 2.0},
        {"id": "end", "type": "text_card", "params": {"text": "y"}, "beats": [{"text": "That is all."}], "sfx": ["whoosh"]},
    ],
}


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, Any]:
    root = _write(tmp_path_factory.mktemp("audio") / "talk", VIDEO)
    project = Project.load(root)
    _voice_all(project)
    return project, render_audio(project)


def test_render_writes_only_the_sound(rendered: tuple[Project, Any]) -> None:
    project, result = rendered
    assert result.output == project.root / "output" / "talk.wav" and not (project.root / "output" / "talk.mp4").exists()
    samples = _read_24(result.output)
    assert len(samples) == round(result.duration * RATE)
    assert result.timings["mix"]["normalized"] and loudness.integrated_loudness(samples) == pytest.approx(-18, abs=0.5)
    assert result.timings["mix"]["true_peak_dbtp"] <= -1.5
    timings = json.loads(result.timings_file.read_text(encoding="utf-8"))
    assert timings["audio_only"] == {"timing": "speech", "left_out": []} and timings["mix"]["music"][0]["source"] == "calm"
    sounds = [e["sound"] for s in timings["scenes"] for e in s.get("sfx", [])]
    assert sounds == ["sting_reveal", "whoosh"]
    first = timings["scenes"][0]["beats"][0]
    voice = _read_24(project.render_dir(False) / "audio" / "mix.wav")
    lo = round(first["start"] * RATE)
    assert np.abs(voice[lo : lo + RATE // 2]).max() > np.abs(voice[: lo - RATE // 10]).max()   # the line, louder than the lead-in's music


def test_render_is_deterministic(rendered: tuple[Project, Any]) -> None:
    project, result = rendered
    before = result.output.read_bytes()
    assert render_audio(project).output.read_bytes() == before


def test_cli_audio_only_flag_and_conflicts(rendered: tuple[Project, Any], capsys: pytest.CaptureFixture[str]) -> None:
    project, _ = rendered
    assert cli.main(["render", str(project.root), "--audio-only", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["audio_only"] and doc["timing"] == "speech" and doc["outputs"]["audio"].endswith("talk.wav")
    assert [s["id"] for s in doc["scenes"]] == ["intro", "card", "end"] and doc["mix"]["normalized"]
    assert cli.main(["render", str(project.root), "--audio-only", "--scene", "intro", "--json"]) == 1
    assert "not with an audio-only render" in json.loads(capsys.readouterr().out)["error"]["message"]


def test_mix_without_music_is_written_when_asked(tmp_path: Path) -> None:
    root = _write(tmp_path / "p", {"title": "t", "scenes": [{"id": "s", "type": "text_card", "params": {"text": "x"}, "duration": 1.0}]})
    project = Project.load(root)
    wav = tmp_path / "v.wav"
    write_wav(wav, np.full((RATE, 2), 0.1, dtype=np.float32))
    timings = {"scenes": [{"id": "s", "start": 0.0, "duration": 1.0, "beats": []}]}
    assert not mix.mix_audio(project, timings, [wav], None, tmp_path / "a.wav").mixed and not (tmp_path / "a.wav").exists()
    report = mix.mix_audio(project, timings, [wav], None, tmp_path / "b.wav", always_write=True)
    assert report.mixed and not report.normalized and len(_read_24(tmp_path / "b.wav")) == RATE


# ----- a video's mix is unchanged ----------------------------------------------------------------------

#: The mix of a small video (narration, a pop, the calm bed, normalised) as Step 282 made it: RMS
#: of each half second. An audio-only option must never change it.
PINNED_RMS = [0.131923, 0.170006, 0.164122, 0.104846, 0.048088, 0.069333, 0.042903, 0.10044, 0.012277, 0.002249]


def test_video_mix_is_pinned(tmp_path: Path) -> None:
    root = tmp_path / "p"
    scenes = [
        {"id": "s0", "type": "title", "params": {"title": "x"}, "beats": [{"text": "Words here."}]},
        {"id": "s1", "type": "title", "params": {"title": "y"}, "duration": 2.0},
    ]
    _write(root, {"title": "t", "music": {"source": "calm", "fade_in": 0.5}, "audio": {"normalize": True}, "scenes": scenes})
    tone = (0.1 * np.sin(2 * np.pi * 220 * np.arange(round(1.5 * RATE)) / RATE)).astype(np.float32)
    write_wav(root / "audio" / "s0_b1.mp3", tone)
    voice0 = np.zeros((3 * RATE, 2), dtype=np.float32)
    voice0[round(0.2 * RATE) : round(0.2 * RATE) + len(tone)] = tone[:, None]
    wavs = [root / "padded" / "s0.wav", root / "padded" / "s1.wav"]
    write_wav(wavs[0], voice0)
    write_wav(wavs[1], np.zeros((2 * RATE, 2), dtype=np.float32))
    timings = {"scenes": [
        {"id": "s0", "start": 0.0, "duration": 3.0, "beats": [{"id": "s0_b1", "start": 0.2, "end": 1.7}]},
        {"id": "s1", "start": 3.0, "duration": 2.0, "beats": []},
    ]}
    track = root / "padded" / "sfx.wav"
    sfx.write_track(track, [sfx.SfxEvent(3.5, "pop")], 5 * RATE, SoundLibrary(root))
    out = tmp_path / "mix.wav"
    report = mix.mix_audio(Project.load(root), timings, wavs, track, out)
    assert (report.gain_db, report.integrated_lufs, report.true_peak_dbtp) == pytest.approx((7.55, -16.01, -1.9), abs=0.006)
    blocks = _read_24(out).reshape(-1, RATE // 2, 2)
    assert [float(np.sqrt(np.mean(b**2))) for b in blocks] == pytest.approx(PINNED_RMS, abs=2e-6)
    # Step 288's options neutral (no scene names a bed; sound-design settings of audio:) leave the mix as it was
    _write(root, {"title": "t", "music": {"source": "calm", "fade_in": 0.5}, "scenes": [{**scenes[0], "ambience": False}, scenes[1]],
                  "audio": {"normalize": True, "sfx_room": False, "ambience_crossfade": 6.0, "scene_sounds": True}})
    again = tmp_path / "mix2.wav"
    mix.mix_audio(Project.load(root), timings, wavs, track, again)
    assert again.read_bytes() == out.read_bytes()


# ----- story draft --audio -----------------------------------------------------------------------------


STORY_TEXT = """# The Lantern Shop

## Evening

It was evening when Ada opened the door of the lantern shop. A small bell rang above her head.

"We are closing," said Mr. Pell, without looking up.

"I only need one lantern," Ada said. "The path home is dark."

## The Choice

Mr. Pell put down his brush and smiled. "Then take the blue one. It never goes out."
"""


def test_story_draft_audio(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "lantern.md"
    source.write_text(STORY_TEXT, encoding="utf-8")
    assert cli.main(["story", "draft", str(source), "--audio", "-o", str(tmp_path / "lantern"), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] and doc["audio_only"] and "## Sections (audio only)" in doc["report_text"]
    config = yaml.safe_load((tmp_path / "lantern" / "video.yaml").read_text(encoding="utf-8"))
    assert config["audio_only"] is True and "scenes" not in config and "characters" not in config
    assert [s.get("title") for s in config["sections"]] == ["Evening", "The Choice"]
    beats = [b for s in config["sections"] for b in s["beats"]]
    assert all(set(b) <= {"text", "voice", "emotion"} for b in beats) and any(b.get("voice") == "pell_voice" for b in beats)
    project = Project.load(tmp_path / "lantern")
    assert project.config.audio_only and [s.chapter for s in project.config.scenes] == ["Evening", "The Choice"]
