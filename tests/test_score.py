"""Composed music (Step 146): the Score, its MIDI export, the numpy mixing of rendered parts, a
composed score as a music source; one real render, skipped without symusic 0.5.9 and a SoundFont."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import loudness, mix, music, synth
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.score import Note, Part, Score, Section, midi_pan, midi_volume, write_midi
from vidgen.sfx import RATE, write_wav
from vidgen.soundfont import default_path

HAS_SYMUSIC = synth.symusic_version() == synth.SYMUSIC_VERSION
needs_symusic = pytest.mark.skipif(not HAS_SYMUSIC, reason=f"symusic {synth.SYMUSIC_VERSION} (the music extra) is not installed")


def _score(**extra: Any) -> Score:
    melody = Part("melody", [Note(0, 1, 72), Note(1, 1, 76, 100), Note(2, 2, 79)], program=73, pan=0.3)
    drums = Part("drums", [Note(b, 0.5, 36 if b % 2 == 0 else 38) for b in range(4)], program=40, drums=True, reverb=0.0)
    return Score(**{"tempo": 120, "parts": [melody, drums], **extra})


# ----- score maths ---------------------------------------------------------------------------------


def test_length_rounds_up_to_whole_bars() -> None:
    score = _score()
    assert score.bar_beats == 4 and score.length_beats == 4 and score.length_seconds == pytest.approx(2.0)
    longer = _score(parts=[Part("p", [Note(3.5, 1.0, 60)])])
    assert longer.length_beats == 8  # ends at 4.5 beats: two bars
    waltz = _score(time_signature=(3, 4), parts=[Part("p", [Note(0, 3, 60)])])
    assert waltz.bar_beats == 3 and waltz.length_beats == 3
    assert _score(time_signature=(6, 8)).bar_beats == 3  # beats are quarter notes
    assert _score(length=10).length_beats == 10
    assert Score(tempo=90, parts=[]).length_beats == 4  # at least one bar


def test_tempo_changes_at_sections() -> None:
    score = _score(tempo=60, sections=[Section("b", 8, tempo=120), Section("a", 0), Section("c", 4)])
    assert [s.name for s in score.sections] == ["a", "c", "b"]
    assert score.tempo_changes() == [(0.0, 60.0), (8.0, 120.0)]
    assert score.seconds_at(0) == 0 and score.seconds_at(4) == pytest.approx(4.0)
    assert score.seconds_at(8) == pytest.approx(8.0) and score.seconds_at(12) == pytest.approx(10.0)
    assert _score(tempo=60, sections=[Section("a", 0, tempo=100)]).tempo_changes() == [(0.0, 100.0)]


@pytest.mark.parametrize(
    ("key", "signature", "tonic"),
    [("C major", (0, False), 0), ("A minor", (0, True), 9), ("F# minor", (3, True), 6), ("Bb major", (-2, False), 10), ("Cb major", (-7, False), 11), ("C# major", (7, False), 1)],
)
def test_key_signatures(key: str, signature: tuple[int, bool], tonic: int) -> None:
    score = _score(key=key)
    assert score.key_signature() == signature and score.tonic == tonic


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: Note(-1, 1, 60), "note start -1"),
        (lambda: Note(0, 0, 60), "note length 0"),
        (lambda: Note(0, 1, 128), "note pitch 128"),
        (lambda: Note(0, 1, 60, 0), "note velocity 0"),
        (lambda: Part("p", [], program=128), "program 128"),
        (lambda: Part("p", [], pan=2), "pan 2"),
        (lambda: Part("p", [], reverb=1.5), "reverb 1.5"),
        (lambda: _score(tempo=10), "tempo 10"),
        (lambda: _score(time_signature=(4, 3)), "time signature 4/3"),
        (lambda: _score(key="H major"), "key 'H major' must be"),
        (lambda: _score(key="D# major"), "no standard key signature"),
        (lambda: Score(tempo=100, parts=[Part("a", []), Part("a", [])]), "part names must differ"),
    ],
)
def test_score_errors(make: Any, message: str) -> None:
    with pytest.raises(VidgenError, match="^score: ") as info:
        make()
    assert message in str(info.value)


def test_fingerprint_follows_the_content() -> None:
    assert _score().fingerprint() == _score().fingerprint()
    assert _score().fingerprint() != _score(tempo=121).fingerprint()
    assert _score().fingerprint() != _score(key="G major").fingerprint()


def test_midi_controller_values() -> None:
    assert midi_volume(0) == 127 and midi_volume(6) == 127 and midi_volume(-12) == 64 and midi_volume(-60) == 4
    assert (midi_pan(-1), midi_pan(0), midi_pan(1)) == (0, 64, 127)


@needs_symusic
def test_midi_export(tmp_path: Path) -> None:
    import symusic

    score = _score(key="E minor", time_signature=(3, 4), sections=[Section("intro", 0), Section("theme", 3, tempo=90)])
    path = write_midi(score, tmp_path / "out" / "piece.mid")
    back = symusic.Score(str(path))
    assert back.tpq == 480
    assert [(t.time, round(t.qpm)) for t in back.tempos] == [(0, 120), (1440, 90)]
    assert [(t.numerator, t.denominator) for t in back.time_signatures] == [(3, 4)]
    assert [(k.key, k.tonality) for k in back.key_signatures] == [(1, 1)]
    assert [(m.time, m.text) for m in back.markers] == [(0, "intro"), (1440, "theme")]
    melody, drums = back.tracks
    assert (melody.name, melody.program, melody.is_drum) == ("melody", 73, False)
    assert [(n.time, n.duration, n.pitch, n.velocity) for n in melody.notes] == [(0, 480, 72, 90), (480, 480, 76, 100), (960, 960, 79, 90)]
    assert (drums.program, drums.is_drum, len(drums.notes)) == (40, True, 4)
    assert {(c.number, c.value) for c in melody.controls} == {(7, 127), (10, 83), (91, 25)}


def test_missing_extra_is_a_clear_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(synth, "symusic_version", lambda: None)
    with pytest.raises(VidgenError, match=r'needs the optional extra: pip install "schu-video-generator\[music\]"'):
        write_midi(_score(), tmp_path / "x.mid")


# ----- mixing (numpy, no symusic) --------------------------------------------------------------------


def _tone(seconds: float, freq: float, level: float = 0.5) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    return np.repeat((level * np.sin(2 * np.pi * freq * t))[:, None], 2, axis=1)


def test_pan_is_constant_power() -> None:
    assert synth.pan_gains(0) == pytest.approx((1.0, 1.0))
    assert synth.pan_gains(1) == pytest.approx((0.0, math.sqrt(2)), abs=1e-12)
    for pan in (-1, -0.4, 0.3, 1):
        left, right = synth.pan_gains(pan)
        assert left**2 + right**2 == pytest.approx(2.0)


def test_reverb_impulse() -> None:
    impulse = synth.reverb_impulse()
    assert impulse.shape == (round(synth.REVERB_SECONDS * RATE), 2) and not impulse.flags.writeable
    delay = round(synth.REVERB_PREDELAY * RATE)
    assert not impulse[:delay].any()
    assert np.sum(impulse**2, axis=0) == pytest.approx([1.0, 1.0])
    assert abs(np.corrcoef(impulse[:, 0], impulse[:, 1])[0, 1]) < 0.1  # decorrelated: wide
    late = slice(round(1.5 * RATE), None)
    assert np.sum(impulse[late] ** 2) < 1e-3  # 1.5 s in, about 56 dB down


def test_convolve_matches_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(1)
    x = rng.standard_normal((5000, 2))
    x[1024:2048] = 0  # a silent block is skipped
    impulse = rng.standard_normal((300, 2))
    monkeypatch.setattr(synth, "_CONVOLUTION_BLOCK", 1024)  # several blocks
    got = synth.convolve(x, impulse)
    for c in range(2):
        assert np.allclose(got[:, c], np.convolve(x[:, c], impulse[:, c])[:5000])


def test_mix_parts_level_pan_tail_and_peak() -> None:
    score = Score(
        tempo=120,
        parts=[Part("left", [Note(0, 4, 60)], pan=-1, reverb=0), Part("loud", [Note(0, 4, 64)], volume=0, reverb=0.3), Part("rest", [])],
    )
    left = _tone(1.5, 220.0, 0.2)  # shorter than the score: padded
    loud = _tone(2.5, 330.0, 3.0)  # floats above 1, as symusic returns them
    out = synth.mix_parts(score, [left, loud, None])
    assert out.shape == (round((2.0 + synth.TAIL_SECONDS) * RATE), 2)
    assert loudness.integrated_loudness(out) == pytest.approx(music.MUSIC_LEVEL, abs=0.2)
    assert 20 * math.log10(loudness.peak_envelope(out).max()) <= synth.TRUE_PEAK_CEILING + 0.01
    assert not out[-1].any()  # the end is faded to silence
    tail = out[round(2.6 * RATE) : round(3.0 * RATE)]
    assert np.abs(tail).max() > 0  # the reverb rings on after the last note


def test_mix_parts_pans_and_sets_volume() -> None:
    def channels(pan: float, volume: float) -> np.ndarray:
        score = Score(tempo=120, parts=[Part("a", [Note(0, 4, 60)], pan=pan, volume=volume, reverb=0), Part("ref", [Note(0, 4, 60)], reverb=0)])
        out = synth.mix_parts(score, [_tone(2, 440.0, 0.3), _tone(2, 110.0, 0.3)])
        spectrum = np.abs(np.fft.rfft(out[: 2 * RATE], axis=0))
        k440, k110 = 880, 220  # bins of 440 Hz and 110 Hz over 2 s
        return spectrum[k440] / spectrum[k110]

    left = channels(-1.0, 0.0)
    assert left[1] < 1e-6 and left[0] == pytest.approx(math.sqrt(2), rel=1e-3)
    quiet = channels(0.0, -6.0)
    assert quiet[0] == pytest.approx(10 ** (-6 / 20), rel=1e-3)


def test_balance_sets_the_parts_to_one_loudness_before_their_volume() -> None:
    def ratio(balance: bool) -> float:
        parts = [Part("a", [Note(0, 4, 60)], volume=-6, reverb=0), Part("ref", [Note(0, 4, 60)], reverb=0)]
        out = synth.mix_parts(Score(tempo=120, parts=parts, balance=balance), [_tone(2, 300.0, 0.01), _tone(2, 400.0, 0.5)])
        spectrum = np.abs(np.fft.rfft(out[: 2 * RATE, 0]))
        return float(spectrum[600] / spectrum[800])  # 300 Hz / 400 Hz (near-equal K-weighting)

    assert ratio(False) == pytest.approx(0.02 * 10 ** (-6 / 20), rel=1e-3)  # the raw levels, then the volume
    assert 20 * math.log10(ratio(True)) == pytest.approx(-6.0, abs=0.3)  # same loudness, then -6 dB


def test_silent_mix_is_an_error() -> None:
    score = Score(tempo=120, parts=[Part("a", [Note(0, 1, 60)])])
    with pytest.raises(VidgenError, match="the rendered music is silent"):
        synth.mix_parts(score, [np.zeros((RATE, 2))])


def test_render_key_follows_score_soundfont_and_symusic(monkeypatch: pytest.MonkeyPatch) -> None:
    key = synth.render_key(_score(), "a" * 64)
    assert key == synth.render_key(_score(), "a" * 64)
    assert key != synth.render_key(_score(tempo=100), "a" * 64)
    assert key != synth.render_key(_score(), "b" * 64)
    monkeypatch.setattr(synth, "symusic_version", lambda: "0.5.10")
    assert key != synth.render_key(_score(), "a" * 64)


# ----- the score as a music source ---------------------------------------------------------------


def _fake_soundfont(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF\x04\x00\x00\x00sfbk")
    return path


def test_composed_music_plays_as_a_music_cue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen import composer

    calls: list[tuple[Score, Path, Path | None]] = []

    def fake_render(score: Score, soundfont: Path, cache_dir: Path | None = None) -> np.ndarray:
        calls.append((score, soundfont, cache_dir))
        audio = _tone(score.length_seconds + synth.TAIL_SECONDS, 262.0, 0.1)
        return (audio * 10 ** ((music.MUSIC_LEVEL - loudness.integrated_loudness(audio)) / 20)).astype(np.float32)

    monkeypatch.setattr(synth, "symusic_version", lambda: synth.SYMUSIC_VERSION)
    monkeypatch.setattr(synth, "render_score", fake_render)
    root = tmp_path / "p"
    _fake_soundfont(root / "sf" / "bank.sf2")
    scenes = [{"id": f"s{i}", "type": "title", "params": {"title": "x"}, "duration": 6.0} for i in range(2)]
    compose = {"mood": "upbeat", "bars": 4, "tempo": 120}  # 8 s + 3 s tail
    video = {"title": "t", "soundfont": "sf/bank.sf2", "music": {"compose": compose, "fade_in": 0.5, "volume": -3}, "scenes": scenes}
    root.mkdir(exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(video), encoding="utf-8")
    project = Project.load(root)
    cue = project.config.music_cues[0]
    assert music.source_kind(cue) == "composed" and music.config_problems(project.config, root) == []
    timings = {"scenes": [{"id": f"s{i}", "start": 6.0 * i, "duration": 6.0, "beats": []} for i in range(2)]}
    wavs = []
    for i in range(2):
        wavs.append(root / "padded" / f"s{i}.wav")
        write_wav(wavs[-1], np.zeros((6 * RATE, 2)))
    report = mix.mix_audio(project, timings, wavs, None, tmp_path / "mix.wav")
    assert calls == [(composer.compose("upbeat", bars=4, tempo=120), (root / "sf" / "bank.sf2").resolve(), project.build_dir / "music")]
    assert report.music == [{"source": "compose: upbeat", "kind": "composed", "from": "s0", "to": "s1", "start": 0.0, "end": 12.0, "volume": -3.0, "duck": 12.0}]
    assert report.mixed and report.normalized
    # looped: the 8 s piece repeats with its 3 s tail added onto its start (no cross-fade)
    source = mix.plan_music(project, timings, 12 * RATE)[0].source
    rendered = fake_render(calls[0][0], Path("x"))
    piece = 8 * RATE
    assert source.loop and source.length == piece and np.array_equal(source.head, rendered[:piece])
    assert np.allclose(source.read(piece, piece + 10), rendered[:10] + rendered[piece : piece + 10])
    assert np.array_equal(source.read(piece + 3 * RATE, piece + 3 * RATE + 10), rendered[3 * RATE : 3 * RATE + 10])


# ----- one real render ------------------------------------------------------------------------------


def _test_soundfont() -> Path | None:
    candidate = Path(os.environ.get("VIDGEN_TEST_SOUNDFONT") or default_path())
    return candidate if candidate.is_file() else None


@pytest.mark.skipif(not HAS_SYMUSIC or _test_soundfont() is None, reason="needs symusic 0.5.9 and a SoundFont (VIDGEN_TEST_SOUNDFONT or the downloaded default)")
def test_real_render_is_cached_and_at_the_music_level(tmp_path: Path) -> None:
    soundfont = _test_soundfont()
    assert soundfont is not None
    score = Score(
        tempo=120,
        parts=[
            Part("piano", [Note(b, 1, p, 100) for b, p in enumerate((60, 64, 67, 72))], program=0, pan=-0.3),
            Part("drums", [Note(b, 0.5, 36 if b % 2 == 0 else 38, 110) for b in range(4)], drums=True, reverb=0.1),
        ],
    )
    first = synth.render_score(score, soundfont, tmp_path / "cache")
    assert first.shape == (round((2.0 + synth.TAIL_SECONDS) * RATE), 2) and first.dtype == np.float32
    assert loudness.integrated_loudness(first) == pytest.approx(music.MUSIC_LEVEL, abs=0.3)
    assert 20 * math.log10(float(loudness.peak_envelope(first.astype(np.float64)).max())) <= synth.TRUE_PEAK_CEILING + 0.05
    cached = list((tmp_path / "cache").glob("score-*.wav"))
    assert len(cached) == 1 and not list((tmp_path / "cache").glob(".score-*"))
    again = synth.render_score(score, soundfont, tmp_path / "cache")
    assert np.array_equal(first, again)
    assert np.array_equal(synth.render_score(score, soundfont), first)  # deterministic without the cache too
