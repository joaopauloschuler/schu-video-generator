"""The composer (Step 147): moods, chords, determinism, the melody's rules, the loop, the
``compose:`` config, the bed fallback without the extra, ``list-music`` and ``vidgen music
preview``. No rendering, except one real render skipped without symusic 0.5.9 and a SoundFont."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from vidgen import composer, loudness, mix, music, synth
from vidgen.cli import main
from vidgen.composer import MOODS, compose, compose_piece, parse_chord, parse_key
from vidgen.config import VideoConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.score import Score
from vidgen.sfx import RATE
from vidgen.soundfont import default_path

SEEDS = (1, 2, 3, 7, 42)
HAS_SYMUSIC = synth.symusic_version() == synth.SYMUSIC_VERSION


def _melody_bars(piece: composer.Piece) -> list[tuple[tuple[float, float, int], ...]]:
    meter = piece.mood.meter
    bars: list[list[tuple[float, float, int]]] = [[] for _ in range(piece.bars)]
    melody = next(p for p in piece.score.parts if p.name == "melody")
    for note in melody.notes:
        bar = int(note.start // meter)
        bars[bar].append((round(note.start - bar * meter, 6), round(note.length, 6), note.pitch))
    return [tuple(b) for b in bars]


# ----- keys and chords -----------------------------------------------------------------------------


def test_chords_from_roman_numerals() -> None:
    a_minor, c_major = parse_key("A minor", True), parse_key("C", False)
    v7 = parse_chord("V7", a_minor)
    assert v7.name == "E7" and v7.pitch_classes == (4, 8, 11, 2)
    assert v7.scale(a_minor)[6] == 8  # the raised leading tone (G#) over V in minor
    assert parse_chord("bVII", parse_key("F", False)).name == "Eb"
    assert parse_chord("ii°", parse_key("D minor", True)).name == "Edim"
    assert parse_chord("I/3", parse_key("G", False)).name == "G/B"
    assert parse_chord("ii7", c_major).name == "Dm7" and parse_chord("IVmaj7", c_major).name == "Fmaj7"
    assert parse_chord("Vsus4", c_major).pitch_classes == (7, 0, 2)
    assert parse_chord("bVI", parse_key("Bb", False)).name == "Gb"
    with pytest.raises(VidgenError, match="not a Roman numeral"):
        parse_chord("X7", c_major)


def test_keys() -> None:
    assert parse_key("Eb", False).name == "Eb major" and parse_key("F#", True).name == "F# minor"
    for bad in ("H major", "D# major", "c minor"):
        with pytest.raises(VidgenError, match="must be a note with major or minor"):
            parse_key(bad, False)


def test_every_progression_and_cell_of_every_mood_parses() -> None:
    for mood in MOODS.values():
        key = parse_key(mood.key, mood.minor)
        for progression in (*mood.themes, *mood.contrasts):
            assert parse_chord(progression.question[-1].split()[-1], key).root == (key.tonic + 7) % 12, (mood.name, progression)
            assert parse_chord(progression.answer[-1].split()[-1], key).root == key.tonic, (mood.name, progression)
            for bar in (*progression.question, *progression.answer):
                for symbol in bar.split():
                    parse_chord(symbol, key)
        for cell in (*mood.cells, mood.half, mood.full, mood.turn):
            composer.parse_cell(cell, mood.meter)
        assert mood.bed in music.BUILTIN_BEDS and mood.drums in composer.DRUM_PATTERNS
        assert mood.chords in composer.CHORD_PATTERNS and mood.bass in composer.BASS_PATTERNS


# ----- moods and settings --------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(MOODS))
def test_mood_parameters_reach_the_score(name: str) -> None:
    mood = MOODS[name]
    piece = compose_piece(name)
    score = piece.score
    assert score.tempo == mood.tempo and score.key == mood.key and score.time_signature == (mood.meter, 4)
    assert piece.bars == mood.bars and score.length_beats == mood.bars * mood.meter and score.balance
    defaults = composer.resolve_voices(mood)
    assert [p.name for p in score.parts] == [v.role for v in defaults]
    for part, voice in zip(score.parts, defaults):
        assert (part.program, part.drums, part.volume, part.pan, part.reverb) == (
            voice.instrument.program, voice.instrument.drums, voice.volume, voice.pan, voice.reverb,
        )
        assert part.notes and all(n.end <= score.length_beats + 1e-9 for n in part.notes)
    assert "drums" in [p.name for p in score.parts] or "No drums." in composer.describe(mood)
    assert 25 <= piece.seconds <= 60
    assert [s.name for s in score.sections][:2] == ["A1 question", "A1 answer"]


def test_settings_change_the_piece() -> None:
    piece = compose_piece("calm", key="E", tempo=80, bars=8, instruments={"melody": "flute", "pad": "none", "drums": "soft_drums", "bass": {"volume": -2}})
    score = piece.score
    assert score.key == "E major" and score.tempo == 80 and score.length_beats == 32
    parts = {p.name: p for p in score.parts}
    assert set(parts) == {"melody", "chords", "bass", "drums"}
    assert parts["melody"].program == 73 and parts["drums"].program == 40 and parts["drums"].drums
    assert parts["bass"].volume == -2 and parts["bass"].program == 42
    assert piece.chords[0] == ("E",) and piece.chords[-1] == ("E", "B7")


def test_invalid_settings_say_what_to_write() -> None:
    def problems(**settings: Any) -> str:
        return "; ".join(composer.settings_problems(**{"mood": "calm", **settings}))

    assert "unknown mood 'calmm'; did you mean 'calm'?" in problems(mood="calmm")
    assert "unknown instrument 'flut'; did you mean 'flute'?" in problems(instruments={"melody": "flut"})
    assert "unknown role 'melodie'; did you mean 'melody'?" in problems(instruments={"melodie": "flute"})
    assert "drums does not fit; melody needs an instrument" in problems(instruments={"melody": "drums"})
    assert "piano does not fit; drums needs a drum kit" in problems(instruments={"drums": "piano"})
    assert "has no drums by default; name an instrument" in problems(instruments={"drums": {"volume": -3}})
    assert "mood 'calm' is written for a major key; write 'E major' (or just 'E')" in problems(key="E minor")
    assert "must be a multiple of 4" in problems(bars=10)
    assert "tempo 300 must be 40 to 200" in problems(tempo=300)
    assert problems() == ""
    with pytest.raises(VidgenError, match="compose: unknown mood"):
        compose("happy")


def test_instruments_have_ranges_and_words() -> None:
    for inst in composer.INSTRUMENTS.values():
        assert inst.words and 0 <= inst.program <= 127 and inst.low < inst.high
    # not offered: they play as a click with GeneralUser GS and symusic 0.5.9
    assert "pizzicato" not in composer.INSTRUMENTS and "xylophone" not in composer.INSTRUMENTS


# ----- determinism and the melody ------------------------------------------------------------------


def test_the_same_settings_give_the_same_music() -> None:
    for name in MOODS:
        first, again = compose(name, seed=5), compose(name, seed=5)
        assert first == again and first.fingerprint() == again.fingerprint()
        assert compose(name, seed=6).fingerprint() != first.fingerprint()
    # another instrument changes that part's sound, not the notes of the others
    plain, other = compose("upbeat"), compose("upbeat", instruments={"melody": "flute"})
    assert [p.notes for p in plain.parts[1:]] == [p.notes for p in other.parts[1:]]


@pytest.mark.parametrize("name", list(MOODS))
def test_melody_stays_in_range_with_chord_tones_on_strong_beats(name: str) -> None:
    mood = MOODS[name]
    strong = (0.0, 2.0) if mood.meter == 4 else (0.0,)
    for seed in SEEDS:
        piece = compose_piece(name, seed=seed)
        low, high = composer.fit_range(*mood.melody_range, piece.voices[0].instrument)
        for bar, notes in enumerate(_melody_bars(piece)):
            assert notes, (name, seed, bar)
            for k, (onset, _, pitch) in enumerate(notes):
                assert low <= pitch <= high, (name, seed, bar, pitch)
                if k == 0 or onset in strong:
                    chord = piece.chord_at(bar * mood.meter + onset)
                    assert pitch % 12 in chord.pitch_classes, (name, seed, bar, onset, pitch, chord.name)
            leaps = [abs(b[2] - a[2]) for a, b in zip(notes, notes[1:])]
            assert max(leaps, default=0) <= 12, (name, seed, bar, notes)


@pytest.mark.parametrize("name", list(MOODS))
def test_no_long_repetition(name: str) -> None:
    for seed in SEEDS:
        bars = _melody_bars(compose_piece(name, seed=seed))
        assert all(a != b for a, b in zip(bars, bars[1:])), (name, seed)  # no bar played twice in a row
        phrases = [tuple(bars[k : k + 4]) for k in range(0, len(bars), 4)]
        assert all(a != b for a, b in zip(phrases, phrases[1:])), (name, seed)
        assert len(set(bars)) >= 0.6 * len(bars), (name, seed, len(set(bars)))


@pytest.mark.parametrize("name", list(MOODS))
def test_the_piece_ends_turning_back_to_its_start(name: str) -> None:
    piece = compose_piece(name, seed=2)
    tonic = piece.key.tonic
    assert piece.chord_at(0).root == tonic
    last_bar = (piece.bars - 1) * piece.mood.meter
    assert piece.chord_at(last_bar).root == tonic and piece.chord_at(last_bar + piece.mood.meter - 0.5).symbol == "V7"
    melody = _melody_bars(piece)
    assert melody[-1][0][2] % 12 == tonic and melody[7][0][2] % 12 == tonic  # answers end on the tonic
    assert piece.chord_at(3 * piece.mood.meter).root == (tonic + 7) % 12  # the first question on V
    assert piece.phrases[:4] == ("A question", "A answer", "B question", "A answer")


def test_form_of_any_length() -> None:
    assert composer.form(1) == [("A", "answer")]
    assert [letter for letter, _ in composer.form(8)] == list("AABAAACA")
    assert all(role == "answer" for _, role in (composer.form(n)[-1] for n in range(1, 12)))
    piece = compose_piece("tense", bars=4)
    assert piece.chords[-1][-1] == "A7" and piece.score.length_beats == 16


# ----- config ----------------------------------------------------------------------------------------


def _config(music_setting: Any) -> VideoConfig:
    scenes = [{"id": i, "type": "title", "params": {"title": "x"}, "duration": 2} for i in "ab"]
    return VideoConfig.model_validate({"title": "t", "music": music_setting, "scenes": scenes})


def test_compose_in_video_yaml() -> None:
    short = _config({"compose": "playful"}).music_cues[0]
    assert short.compose is not None and short.compose.mood == "playful" and short.source is None and short.label == "compose: playful"
    full = _config({"compose": {"mood": "tense", "key": "E", "seed": 4, "instruments": {"melody": {"instrument": "oboe", "pan": 0.2}, "pad": "none"}}}).music_cues[0]
    assert full.compose is not None and full.compose.instrument_settings() == {
        "melody": {"instrument": "oboe", "volume": None, "pan": 0.2, "reverb": None}, "pad": "none",
    }
    listed = _config([{"source": "calm", "to": "a"}, {"compose": {"mood": "calm"}, "from": "b"}]).music_cues
    assert [music.source_kind(c) for c in listed] == ["bed", "composed"]
    assert _config("calm").music_cues[0].source == "calm"  # beds unchanged


@pytest.mark.parametrize(
    ("setting", "message"),
    [
        ({"compose": {"mood": "calmm"}}, "did you mean 'calm'?"),
        ({"compose": {"mood": "calm", "instruments": {"melody": "pizzicato"}}}, "unknown instrument 'pizzicato'"),
        ({"compose": "calm", "source": "calm"}, "give either source (a bed or a file) or compose (a mood), not both"),
        ({"volume": -3}, "give source (a bed or a file) or compose (a mood)"),
        ({"compose": {"mood": "calm", "bars": 6}}, "multiple of 4"),
        ({"compose": {"mood": "calm", "temp": 90}}, "temp"),
    ],
)
def test_compose_problems(setting: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message.replace("(", r"\(").replace(")", r"\)").replace("?", r"\?")):
        _config(setting)


# ----- the music source -------------------------------------------------------------------------


def _project(tmp_path: Path, music_setting: Any) -> Project:
    root = tmp_path / "p"
    root.mkdir()
    scenes = [{"id": "a", "type": "title", "params": {"title": "x"}, "duration": 4.0}]
    (root / "video.yaml").write_text(yaml.safe_dump({"title": "t", "music": music_setting, "scenes": scenes}), encoding="utf-8")
    return Project.load(root)


def test_without_the_extra_the_moods_bed_plays(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(synth, "symusic_version", lambda: None)
    beds = {"lullaby": np.full((RATE, 2), 0.1, dtype=np.float32)}
    monkeypatch.setattr(music, "bed_loop", beds.__getitem__)  # the real bed takes ~3 s to make
    project = _project(tmp_path, {"compose": {"mood": "sleepy"}})
    timings = {"scenes": [{"id": "a", "start": 0.0, "duration": 4.0, "beats": []}]}
    with caplog.at_level(logging.WARNING, logger="vidgen.music"):
        placement = mix.plan_music(project, timings, 4 * RATE)[0]
    assert "playing the built-in bed 'lullaby' instead" in caplog.text and "pip install" in caplog.text
    assert placement.source.seamless and placement.source.data is beds["lullaby"]
    assert placement.summary()["kind"] == "bed" and placement.summary()["source"] == "compose: sleepy (bed lullaby: no music extra)"
    assert {m: MOODS[m].bed for m in MOODS} == {
        "calm": "calm", "focused": "pulse", "curious": "bright", "upbeat": "bright",
        "playful": "cartoon", "sleepy": "lullaby", "tense": "pulse", "triumphant": "bright",
    }


def test_composed_start_wraps_and_plays_once_without_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_render(score: Score, soundfont: Path, cache_dir: Path | None = None) -> np.ndarray:
        n = round((score.length_seconds + synth.TAIL_SECONDS) * RATE)
        return np.repeat(np.linspace(0.0, 0.5, n, dtype=np.float32)[:, None], 2, axis=1)

    monkeypatch.setattr(synth, "symusic_version", lambda: synth.SYMUSIC_VERSION)
    monkeypatch.setattr(synth, "render_score", fake_render)
    monkeypatch.setattr("vidgen.soundfont.resolve", lambda setting, root, download=True: Path("bank.sf2"))
    project = _project(tmp_path, {"compose": {"mood": "upbeat", "bars": 4, "tempo": 120}, "start": 10.0, "loop": False})
    cue = project.config.music_cues[0]
    source = music.Source(cue, project.root)
    rendered = fake_render(composer.compose("upbeat", bars=4, tempo=120), Path("x"))
    assert not source.loop and source.ends_at == len(rendered) - 2 * RATE  # 10 s into an 8 s piece: 2 s in
    assert np.array_equal(source.read(0, 5), rendered[2 * RATE : 2 * RATE + 5])


# ----- list-music and music preview ---------------------------------------------------------------


def test_list_music_describes_moods_and_instruments(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(music, "music_entries", lambda root, previews: [])  # the beds (tested in test_music.py) take ~10 s
    assert main(["list-music", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert [m["name"] for m in doc["moods"]] == list(MOODS) and doc["symusic"]
    calm = doc["moods"][0]
    assert calm["family"] == "explainer" and calm["fallback_bed"] == "calm" and calm["instruments"]["melody"] == "piano"
    assert "D major" in calm["description"] and "Melody: piano, A4 to D6" in calm["description"]
    assert {i["name"] for i in doc["instruments"]} == set(composer.INSTRUMENTS)
    assert main(["list-music"]) == 0
    text = capsys.readouterr().out
    assert "composed music (music: {compose: {mood: NAME" in text and "triumphant  cartoon  Bb major, 112 BPM" in text
    assert "    flute (GM 73, C4-C7): flute: airy, light, gentle" in text


def test_music_preview_needs_a_mood(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["music", "preview"]) == 1
    assert "give --mood NAME (moods: calm, focused" in capsys.readouterr().err


@pytest.mark.skipif(not HAS_SYMUSIC, reason=f"writing a .mid needs symusic {synth.SYMUSIC_VERSION}")
def test_music_preview_writes_wav_and_mid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[Score] = []

    def fake_render(score: Score, soundfont: Path, cache_dir: Path | None = None) -> np.ndarray:
        calls.append(score)
        t = np.arange(round((score.length_seconds + synth.TAIL_SECONDS) * RATE)) / RATE
        return np.repeat((0.05 * np.sin(2 * np.pi * 220 * t))[:, None], 2, axis=1)

    monkeypatch.setattr(synth, "render_score", fake_render)
    monkeypatch.setattr("vidgen.soundfont.resolve", lambda setting, root, download=True: Path("bank.sf2"))
    project = _project(tmp_path, {"compose": {"mood": "tense", "seed": 9, "instruments": {"melody": "oboe"}}})
    out = tmp_path / "out"
    assert main(["music", "preview", str(project.root), "--bars", "8", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert calls == [compose("tense", seed=9, bars=8, instruments={"melody": "oboe"})]
    assert (out / "tense-seed9.wav").is_file() and (out / "tense-seed9.mid").stat().st_size > 100
    assert "mood: tense (cartoon), seed 9: D minor, 104 BPM, 4/4, 8 bars" in text and "melody oboe" in text
    assert "bars   1-4   A question" in text
    assert main(["music", "preview", str(project.root), "--mood", "calm", "--out", str(out)]) == 0  # another mood: its defaults
    assert calls[-1] == compose("calm") and (out / "calm-seed1.mid").is_file()


# ----- one real render ------------------------------------------------------------------------------


def _test_soundfont() -> Path | None:
    candidate = Path(os.environ.get("VIDGEN_TEST_SOUNDFONT") or default_path())
    return candidate if candidate.is_file() else None


@pytest.mark.skipif(not HAS_SYMUSIC or _test_soundfont() is None, reason="needs symusic 0.5.9 and a SoundFont (VIDGEN_TEST_SOUNDFONT or the downloaded default)")
def test_real_render_of_a_mood_balances_its_parts() -> None:
    soundfont = _test_soundfont()
    assert soundfont is not None
    audio = synth.render_score(compose("playful", bars=4), soundfont)
    assert loudness.integrated_loudness(audio) == pytest.approx(music.MUSIC_LEVEL, abs=0.3)
    peak_db = 20 * np.log10(float(loudness.peak_envelope(audio.astype(np.float64)).max()))
    assert peak_db < -6  # no part is a spiky click (e.g. a preset the renderer cannot play)
