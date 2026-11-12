"""Step 290: delivering an audio drama (DESIGN.md §112.3) — the drama loudness preset and its
dialogue checks, one file per chapter with a playlist and per-file transcripts, spoken credits
from the cast, a cold open. Narration is mocked: each beat's "MP3" is a WAV of speech-like
bursts."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import audio_check, cli, delivery
from vidgen.audio_only import render_audio
from vidgen.config import CreditsConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.sfx import RATE, write_wav

DRAMA: dict[str, Any] = {
    "title": "The Ferry",
    "output": "ferry",
    "narration": {"pad": 0.3, "words_per_second": 2},
    "voice": {"provider": "kokoro", "voice": "bm_george"},
    "voices": {"ann": {"voice": "af_bella", "label": "Ann", "pan": "left"}, "ben": {"voice": "am_adam", "label": "Ben", "pan": "right"}},
    "sections": [
        {"id": "shore", "title": "The Shore", "beats": ["one two three four", {"text": "five six", "voice": "ann"}, {"text": "seven eight", "voice": "ben"}]},
        {"pause": 2.0},
        {"id": "river", "title": "The River", "beats": ["nine ten", {"text": "eleven twelve", "voice": "ann"}, {"text": "Home.", "voice": "ben"}]},
    ],
}


def _write(root: Path, data: dict[str, Any]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return root


def _speech(seconds: float, seed: int, level: float = 0.08) -> np.ndarray:
    """Speech-like mono: syllables of a harmonic tone, each 120-250 ms."""
    rng = np.random.default_rng(seed)
    n = round(seconds * RATE)
    t = np.arange(n) / RATE
    tone = sum(np.sin(2 * np.pi * 150 * h * t) / h for h in range(1, 6))
    envelope = np.zeros(n)
    pos = 0
    while pos < n:
        length = int(rng.uniform(0.12, 0.25) * RATE)
        envelope[pos : pos + length] = level * rng.uniform(0.7, 1.1) * np.hanning(min(length, n - pos))
        pos += length + int(0.05 * RATE)
    return (tone * envelope).astype(np.float32)


def _project(tmp_path: Path, name: str, levels: dict[str, float] | None = None, **extra: Any) -> Project:
    project = Project.load(_write(tmp_path / name, {**DRAMA, **extra}))
    for k, (_, beat) in enumerate(project.beats()):
        write_wav(project.audio_dir / f"{beat.id}.mp3", _speech(1.6, k, (levels or {}).get(beat.id, 0.08)))
    return project


# ----- config: credits and cold open ---------------------------------------------------------------


def test_credit_lines_from_the_cast() -> None:
    data = {**DRAMA, "scenes": [{"id": "a", "beats": [{"text": "x"}, {"text": "y", "voice": "ben"}, {"text": "z", "voice": "ann"}]}]}
    lines = delivery.credit_lines(data, CreditsConfig(speak=True, lines=["Music by the studio"]))
    assert lines == ["The Ferry.", "Starring Adam as Ben and Bella as Ann.", "Narrated by George.", "Music by the studio."]
    named = delivery.credit_lines(data, CreditsConfig(speak=True, title="Ferry, episode one", voiced_by={"ann": "Ana Lima", "narrator": "Jo"}))
    assert named == ["Ferry, episode one.", "Starring Adam as Ben and Ana Lima as Ann.", "Narrated by Jo."]
    eleven = {**data, "voice": {"voice_id": "abc"}, "voices": {"ann": {"voice_id": "x"}, "ben": {"voice_id": "y", "label": "Ben"}}}
    assert delivery.credit_lines(eleven, CreditsConfig(speak=True)) == ["The Ferry.", "Starring Ben and Ann."]   # no actor names known


def test_spoken_credits_scene(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "c", {**DRAMA, "score": {"themes": {"main": "calm"}}, "credits": {"speak": True, "voice": "ann"}}))
    last = project.config.scenes[-1]
    assert last.id == "credits" and last.chapter is None and [b.id for b in last.beats] == ["credits_b1", "credits_b2", "credits_b3"]
    assert last.beats[1].text == "Starring Bella as Ann and Adam as Ben." and all(b.voice == "ann" for b in last.beats)
    assert last.music is not None and last.music.theme == "main"
    own = Project.load(_write(tmp_path / "d", {**DRAMA, "credits": {"speak": True, "chapter": "Credits", "music": False}}))
    assert own.config.scenes[-1].chapter == "Credits" and own.config.scenes[-1].music is False
    with pytest.raises(VidgenError, match="a scene 'shore' exists already"):
        Project.load(_write(tmp_path / "e", {**DRAMA, "credits": {"speak": True, "id": "shore"}}))
    assert Project.load(_write(tmp_path / "f", {**DRAMA, "credits": {"speak": False}})).config.scenes[-1].id == "river"


def test_cold_open(tmp_path: Path) -> None:
    moved = Project.load(_write(tmp_path / "a", {**DRAMA, "cold_open": "river"})).config
    assert [s.id for s in moved.scenes] == ["river", "shore", "s2"] and moved.scenes[0].chapter is None
    assert [b.id for b in moved.scenes[0].beats] == ["river_b1", "river_b2", "river_b3"]   # the same beats: the same audio
    teaser = Project.load(_write(tmp_path / "b", {**DRAMA, "cold_open": ["river_b3", "shore_b2"]})).config
    first = teaser.scenes[0]
    assert first.id == "cold_open" and [b.id for b in first.beats] == ["cold_open_river_b3", "cold_open_shore_b2"]
    assert [b.voice for b in first.beats] == ["ben", "ann"] and teaser.scenes[1].id == "shore" and len(teaser.scenes) == 4
    with pytest.raises(VidgenError, match="did you mean 'river_b3'"):
        Project.load(_write(tmp_path / "c", {**DRAMA, "cold_open": ["river_b33"]}))
    data = {"title": "t", "scenes": [{"id": "s", "beats": [{"text": "x"}]}]}
    assert delivery.apply_delivery(data)[0] is data   # nothing asked: nothing changed
    assert [s.id for s in Project.load(_write(tmp_path / "d", {**DRAMA, "cold_open": []})).config.scenes] == ["shore", "s2", "river"]


def test_problems_name_the_sections_after_a_cold_open(tmp_path: Path) -> None:
    sections = [*DRAMA["sections"][:2], {**DRAMA["sections"][2], "beats": ["nine ten", {"text": "Home.", "voice": "ben", "pause": 99}]}]
    data = {**DRAMA, "sections": sections, "cold_open": ["shore_b2"], "credits": {"speak": True}}
    assert delivery.scene_sources({"scenes": sections, "cold_open": ["shore_b2"], "credits": {"speak": True}}) == ["cold_open", 0, 1, 2, "credits"]
    assert delivery.scene_sources({"scenes": sections, "cold_open": "river"}) == [2, 0, 1]
    assert delivery.scene_sources({"scenes": sections}) is None
    with pytest.raises(VidgenError) as raised:
        Project.load(_write(tmp_path / "a", data))
    assert "sections[2].beats[1].pause" in str(raised.value) and "sections[3]" not in str(raised.value)
    assert all("sections[2].beats[1]" in p.location for p in raised.value.problems)
    moved = {**data, "cold_open": "river"}
    with pytest.raises(VidgenError, match=r"sections\[2\]\.beats\[1\]\.pause"):
        Project.load(_write(tmp_path / "b", moved))


class _Voicer:
    """A TTS mock: each text's own bytes; what it was asked to say is kept."""

    name = "fake"

    def __init__(self) -> None:
        self.said: list[str] = []

    def cache_key(self, text: str) -> str:
        return f"fake|{text}"

    def matches(self, text: str, stored: str) -> bool:
        return stored == self.cache_key(text)

    def check_credentials(self) -> None:
        pass

    def synthesize(self, text: str, previous_text: str | None = None, next_text: str | None = None) -> bytes:
        self.said.append(text)
        return f"audio of {text}".encode()


def test_cold_open_lines_copy_their_audio(tmp_path: Path) -> None:
    from vidgen.tts.run import run_tts

    root = _write(tmp_path / "t", {**DRAMA, "cold_open": ["river_b3", "shore_b2"]})
    project = Project.load(root)
    assert delivery.cold_open_sources(project) == {"cold_open_river_b3": "river_b3", "cold_open_shore_b2": "shore_b2"}
    voicer, lines = _Voicer(), []
    run_tts(project, provider=voicer, out=lines.append)
    spoken = [beat.text for _, beat in project.beats() if not beat.id.startswith("cold_open_")]
    assert sorted(voicer.said) == sorted(spoken)   # every line voiced once
    assert (project.audio_dir / "cold_open_river_b3.mp3").read_bytes() == b"audio of Home."
    assert "copied cold_open_river_b3.mp3 from audio/river_b3.mp3" in " ".join(lines)
    order = [line.split("] ")[1].split(".mp3")[0].split()[-1] for line in lines if line.startswith("[")]
    assert order.index("cold_open_shore_b2") == order.index("shore_b2") + 1   # copied right after its source is voiced
    (project.audio_dir / "cold_open_shore_b2.mp3").unlink()
    again = _Voicer()
    run_tts(Project.load(root), provider=again, out=lines.append)
    assert again.said == [] and (project.audio_dir / "cold_open_shore_b2.mp3").read_bytes() == b"audio of five six"
    (project.audio_dir / "shore_b2.hash").write_text("stale", encoding="utf-8")   # a source that is not current is not copied
    third = _Voicer()
    run_tts(Project.load(root), provider=third, out=lines.append, beat_ids=["cold_open_shore_b2"], force=True)
    assert third.said == ["five six"]


# ----- the drama preset's checks ---------------------------------------------------------------------


def _momentary(levels: list[tuple[float, float, float]], end: float) -> np.ndarray:
    """Momentary loudness every 100 ms: ``levels`` (from, to, LUFS), silence (-120) elsewhere."""
    t = np.arange(1, round(end * 10) + 1) / 10
    m = np.full(len(t), -120.0)
    for a, b, v in levels:
        m[(t - 0.4 >= a - 1e-9) & (t <= b + 1e-9)] = v
    return np.stack([t, m], axis=1)


def _measured(**values: Any) -> audio_check.AudioMeasurement:
    base = dict(path=Path("x"), codec="mp3", sample_rate=48000, channels=2, bitrate=192000, duration=20.0, integrated_lufs=-16.2,
                loudness_range=6.0, true_peak=-1.8, sample_peak=-2.0, rms=-19.0, noise_floor=-math.inf, head=0.5, tail=2.0)
    return audio_check.AudioMeasurement(**{**base, **values})


def test_line_loudness_gates_and_averages() -> None:
    m = _momentary([(1.0, 3.0, -18.0), (3.0, 4.0, -40.0)], 6.0)
    assert audio_check.line_loudness(m, 1.0, 3.0) == pytest.approx(-18.0)
    assert audio_check.line_loudness(m, 1.0, 4.0) == pytest.approx(-18.0)   # the quiet second is gated out (10 LU under)
    assert audio_check.line_loudness(m, 4.5, 5.5) == -math.inf
    assert audio_check.parse_momentary("t: 0.1  TARGET:-23 LUFS    M:-120.7 S:-120.7  I: -70.0 LUFS\nt: 0.2 TARGET:-23 LUFS M: -35.6 S:x").tolist() == [
        [0.1, -120.7], [0.2, -35.6]]


def test_drama_preset_checks() -> None:
    preset = audio_check.PRESETS["drama"]
    lines = [audio_check.DialogueLine("a", "Ann", 1.0, 3.0), audio_check.DialogueLine("b", "Ben", 4.0, 6.0), audio_check.DialogueLine("c", "Ann", 7.0, 9.0)]
    even = _measured(momentary=_momentary([(1, 3, -17.0), (4, 6, -18.0), (7, 9, -17.5)], 20))
    music = {"under_dialogue_lu": 22.0, "worst_dense_lu": 19.0}
    result = audio_check.check(even, preset, audio_check.Dialogue(lines, music, 15.0))
    assert result.ok, result.line()
    names = [i.name for i in result.items]
    assert names == ["loudness", "true peak", "loudness range", "dialogue lines", "voices", "music under dialogue"]
    assert "noise floor" not in names and "head" not in names   # no ACX gate
    uneven = _measured(loudness_range=12.0, momentary=_momentary([(1, 3, -12.0), (4, 6, -24.0), (7, 9, -12.0)], 20))
    loud_music = {"under_dialogue_lu": 20.0, "worst_dense_lu": 9.0}
    failing = audio_check.check(uneven, preset, audio_check.Dialogue(lines, loud_music, 15.0))
    assert [i.name for i in failing.failures] == ["loudness range", "dialogue lines", "voices", "music under dialogue"]
    alone = audio_check.check(even, preset)   # a file without its project
    assert alone.ok and alone.items[-1].status == "note" and "vidgen audio check PROJECT" in alone.items[-1].value
    assert audio_check.preset_named("drama") is preset
    across = audio_check.files_check([(even, audio_check.Dialogue(lines)), (_measured(integrated_lufs=-17.5, momentary=even.momentary), audio_check.Dialogue(lines))])
    assert [i.name for i in across.failures] == ["loudness spread"] and [i.name for i in across.items] == ["loudness spread", "dialogue spread"]


@pytest.mark.slow
def test_drama_render_checks_dialogue_and_music(tmp_path: Path) -> None:
    project = _project(tmp_path, "drama", levels={"shore_b2": 0.02}, music={"source": "calm", "volume": -6},
                       audio_output={"loudness": "drama", "transcripts": False})
    result = render_audio(project)
    assert result.check is not None and result.timings["mix"]["levelled_db"] is not None   # the preset levels the voices
    items = {i.name: i for i in result.check.items}
    assert items["music under dialogue"].status == "pass" and "music_check" in result.timings["mix"]   # measured for any music
    assert items["voices"].status in ("pass", "fail") and "Ann" in items["voices"].value
    assert result.timings["audio_output"]["check"]["preset"] == "drama"


# ----- one file per chapter -------------------------------------------------------------------------


@pytest.mark.slow
def test_split_into_chapter_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _project(tmp_path, "split", levels={"river_b1": 0.03}, cold_open=["river_b3"],
                       audio_output={"loudness": "drama", "split": "chapters", "format": "mp3"})
    for _, beat in project.beats():   # the cold open's copy is voiced too
        path = project.audio_dir / f"{beat.id}.mp3"
        if not path.is_file():
            write_wav(path, _speech(1.6, 9))
    result = render_audio(project)
    out = project.output_dir
    assert [p.name for p in result.files] == ["ferry_01_the_shore.mp3", "ferry_02_the_river.mp3"] and result.output == out / "ferry.m3u"
    assert not (out / "ferry.mp3").exists()
    playlist = result.output.read_text(encoding="utf-8").splitlines()
    assert playlist[:3] == ["#EXTM3U", "#PLAYLIST:The Ferry", playlist[2]] and playlist[2].endswith(",The Ferry - The Shore")
    assert playlist[3] == "ferry_01_the_shore.mp3" and playlist[5] == "ferry_02_the_river.mp3"
    entries = result.timings["audio_output"]["files"]
    parts = result.timings["mix"]["parts"]
    assert entries[0]["start"] == 0.0 and entries[1]["end"] == pytest.approx(result.duration, abs=1e-3) and entries[0]["end"] == entries[1]["start"]
    river = next(s for s in result.timings["scenes"] if s["id"] == "river")
    assert river["beats"][0]["start"] - entries[1]["start"] == pytest.approx(0.5, abs=0.01)   # lead_in before its first line
    measured = [audio_check.measure_file(p) for p in result.files]
    for m, part in zip(measured, parts):
        assert m.integrated_lufs == pytest.approx(-16.0, abs=0.7) and part["integrated_lufs"] == pytest.approx(-16.0, abs=0.3)
    assert abs(parts[0]["gain_db"] - parts[1]["gain_db"]) > 0.5   # each file normalised on its own (the river's first line is quiet)
    first = (out / "ferry_01_the_shore_transcript.txt").read_text(encoding="utf-8")
    assert first.startswith("The Ferry\n\nBen: Home.\n\n[0:0") and "[0:0" in first and "nine ten" not in first   # the cold open, then chapter 1
    second = (out / "ferry_02_the_river.vtt").read_text(encoding="utf-8")
    assert second.startswith("WEBVTT\n\n00:00:00.49") and "one two" not in second   # 0.5 s before the first speech
    assert set(result.transcripts) == {"txt_01", "srt_01", "vtt_01", "txt_02", "srt_02", "vtt_02"}
    assert result.check is not None and [i.name for i in result.check.items][-2:] == ["loudness spread", "dialogue spread"]
    assert result.timings["audio_output"]["files_check"]["ok"]
    # vidgen audio check PROJECT: each file, then the files against each other
    code = cli.main(["audio", "check", str(project.root), "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert code == (0 if result.check.ok else 1) and doc["ok"] == result.check.ok
    assert [Path(f["file"]).name for f in doc["files"]] == ["ferry_01_the_shore.mp3", "ferry_02_the_river.mp3"] and "files_check" in doc
    assert [c["preset"] for c in doc["files"][1]["checks"]] == ["drama", "mono"]


def test_playlist_removes_files_it_no_longer_lists(tmp_path: Path) -> None:
    for name in ("a_01.mp3", "a_02.mp3", "a_03.mp3", "mine.mp3"):
        (tmp_path / name).write_bytes(b"x")
    playlist = tmp_path / "a.m3u"
    delivery.write_playlist(playlist, "T", [(tmp_path / "a_01.mp3", "T - One", 10.2), (tmp_path / "a_02.mp3", "T - Two", 5.0), (tmp_path / "a_03.mp3", "T - 3", 1.0)])
    delivery.write_playlist(playlist, "T", [(tmp_path / "a_01.mp3", "T - One", 10.2), (tmp_path / "a_02.mp3", "T - Two", 5.0)])
    assert playlist.read_text(encoding="utf-8") == "#EXTM3U\n#PLAYLIST:T\n#EXTINF:11,T - One\na_01.mp3\n#EXTINF:5,T - Two\na_02.mp3\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.m3u", "a_01.mp3", "a_02.mp3", "mine.mp3"]


@pytest.mark.slow
def test_split_without_chapters_is_one_file(tmp_path: Path) -> None:
    data = {**DRAMA, "sections": [{k: v for k, v in s.items() if k != "title"} for s in DRAMA["sections"]]}
    project = Project.load(_write(tmp_path / "one", {**data, "audio_output": {"split": "chapters", "transcripts": ["txt"]}}))
    for k, (_, beat) in enumerate(project.beats()):
        write_wav(project.audio_dir / f"{beat.id}.mp3", _speech(1.6, k))
    result = render_audio(project)
    assert [p.name for p in result.files] == ["ferry_01_the_ferry.wav"] and result.check is None
    m = audio_check.measure_file(result.files[0])
    assert m.duration == pytest.approx(result.duration, abs=0.01)
