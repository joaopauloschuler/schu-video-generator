"""Score files and their rendering (Step 184, DESIGN.md §93): theory, step patterns, checks with
clear messages, deterministic seamless loops and one-shots, ``vidgen music render``."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import cli, loudness, music
from vidgen.errors import VidgenError
from vidgen.sfx import RATE, read_wav
from vidgen.studio import INSTRUMENTS, load_music_score, parse_music_score, render_music_score, score_outline
from vidgen.studio.patterns import ACCENT_GAIN, SOFT_GAIN, accent_steps, parse_accent, parse_steps
from vidgen.studio.theory import close_voicing, degree_interval, led_voicing, note_name, note_number, parse_chord, parse_key

DEMO = Path(__file__).parent / "data" / "studio" / "tidewater.yaml"


def _score(**changes: Any) -> dict[str, Any]:
    """A small valid score (8 bars at 120 BPM: 16 s), changed by ``changes``."""
    data: dict[str, Any] = {
        "key": "A minor",
        "tempo": 120,
        "progression": "i VI III VII",
        "sections": [{"name": "a", "bars": 4}, {"name": "b", "bars": 4}],
        "tracks": {
            "pad": {"instrument": "pad", "play": "chords"},
            "kick": {"instrument": "kick", "steps": "x... x... x... x...", "rest": ["a"]},
            "bass": {"instrument": "synth_bass", "steps": ".1.1 .1.1 .1.1 .1.1"},
        },
    }
    data.update(changes)
    return data


def _problems(data: Any) -> str:
    with pytest.raises(VidgenError) as info:
        parse_music_score(data, "t.yaml")
    return str(info.value)


# ----- theory ----------------------------------------------------------------------------------------


def test_notes_and_keys() -> None:
    assert note_number("C4") == 60 and note_number("A4") == 69 and note_number("Bb3") == 58 and note_number("C#5") == 73
    assert note_name(69) == "A4" and note_name(70, flats=True) == "Bb4"
    with pytest.raises(VidgenError, match="capital letter"):
        note_number("a4")
    for text, name in (("A minor", "A minor"), ("Am", "A minor"), ("F#", "F# major"), ("Bb major", "Bb major"), ("D dorian", "D dorian")):
        assert parse_key(text).name == name
    assert parse_key("E minor").scale == (4, 6, 7, 9, 11, 0, 2)
    with pytest.raises(VidgenError, match="did you mean 'A minor'"):
        parse_key("A minr")
    assert parse_key("D minor").flats and parse_key("F major").flats and not parse_key("E minor").flats


def test_roman_numerals_and_chord_names() -> None:
    a_minor = parse_key("A minor")
    chords = {s: parse_chord(s, a_minor) for s in ("i", "VI", "III", "VII", "iv7", "V7", "bVII", "ii°", "Vsus4", "VI/3")}
    assert chords["i"].name == "Am" and chords["i"].pitch_classes == (9, 0, 4)
    assert chords["VI"].name == "F" and chords["VII"].name == "G" and chords["III"].name == "C"
    assert chords["iv7"].name == "Dm7" and chords["iv7"].intervals == (0, 3, 7, 10)
    assert chords["V7"].pitch_classes == (4, 8, 11, 2)  # E7: the raised leading tone
    assert chords["ii°"].intervals == (0, 3, 6) and chords["Vsus4"].intervals == (0, 5, 7)
    assert chords["VI/3"].bass == 9  # F/A
    names = {s: parse_chord(s, a_minor) for s in ("Dm(add9)", "G7sus4", "C/E", "Bdim", "Bm7b5", "C6/9", "Fmaj7", "Gmaj9", "Cmaj7(#11)", "A5")}
    assert names["Dm(add9)"].intervals == (0, 2, 3, 7)
    assert names["G7sus4"].intervals == (0, 5, 7, 10)
    assert names["C/E"].bass == 4 and names["C/E"].root == 0
    assert names["Bdim"].intervals == (0, 3, 6) and names["Bm7b5"].intervals == (0, 3, 6, 10)
    assert names["C6/9"].intervals == (0, 2, 4, 7, 9) and names["Fmaj7"].intervals == (0, 4, 7, 11)
    assert names["Gmaj9"].intervals == (0, 2, 4, 7, 11) and names["Cmaj7(#11)"].intervals == (0, 4, 6, 7, 11)
    assert names["A5"].intervals == (0, 7)
    with pytest.raises(VidgenError, match="lower case"):
        parse_chord("VIm", a_minor)
    with pytest.raises(VidgenError, match="cannot read 'x'"):
        parse_chord("Amx", a_minor)
    with pytest.raises(VidgenError, match="not a chord"):
        parse_chord("H7", a_minor)


def test_degrees_follow_the_chord_then_the_key() -> None:
    key = parse_key("A minor")
    am, f, g7sus = parse_chord("Am", key), parse_chord("F", key), parse_chord("G7sus4", key)
    assert [degree_interval(am, key, d) for d in (1, 3, 5, 8)] == [0, 3, 7, 12]
    assert degree_interval(am, key, 7) == 10 and degree_interval(f, key, 7) == 11  # the key's G and E
    assert degree_interval(g7sus, key, 3) == 5 and degree_interval(g7sus, key, 7) == 10  # a sus chord's 3 is its 4th
    assert degree_interval(am, key, 9) == 14 and degree_interval(am, key, 2) == 2


def test_voicings() -> None:
    key = parse_key("C major")
    c, f, g = (parse_chord(s, key) for s in ("C", "F", "G"))
    assert close_voicing(c, 3) == (48, 52, 55)
    first = led_voicing(c, 3, None)
    assert first == (48, 52, 55)
    near = led_voicing(f, 3, first)
    assert abs(sum(near) / 3 - sum(first) / 3) < 4 and {n % 12 for n in near} == {5, 9, 0}
    assert {n % 12 for n in led_voicing(g, 3, near)} == {7, 11, 2}


# ----- step patterns ---------------------------------------------------------------------------------


def test_step_patterns() -> None:
    drums = parse_steps("x... X... o... x?x!", "p")
    assert len(drums) == 1 and len(drums[0]) == 14
    assert [s.gain for s in drums[0] if s.sounds] == [1.0, ACCENT_GAIN, SOFT_GAIN, SOFT_GAIN, ACCENT_GAIN]
    tune = parse_steps(["E5 - - . G5 - . .", "C#6 - 1 3' 5, * . ."], "p")
    assert [len(b) for b in tune] == [8, 8]
    assert tune[0][0].kind == "note" and tune[0][0].value == 76 and tune[0][1].kind == "hold"
    assert tune[1][0].value == 85 and tune[1][3].octaves == 1 and tune[1][4].octaves == -1 and tune[1][5].kind == "chord"
    assert [len(b) for b in parse_steps("x | - | - | -", "p")] == [1, 1, 1, 1]
    for bad, message in (("- x", "starts with '-'"), ("x.-.", "rest cannot be held"), ("x a", "capital letter"), ("x||x", "empty bar"), (".!", "only a hit")):
        with pytest.raises(VidgenError, match=message):
            parse_steps(bad, "p")
    assert parse_accent("3+3+2", "a") == (3, 3, 2)
    assert accent_steps((3, 3, 2), 16) == {0, 3, 6, 8, 11, 14} and accent_steps((3, 3, 2), 12) is None


# ----- checks ----------------------------------------------------------------------------------------


def test_demo_score_reads() -> None:
    score = load_music_score(DEMO)
    outline = score_outline(score)
    assert outline["title"] == "Tidewater" and outline["bars"] == 24 and outline["loop"]
    assert [(s["name"], s["bars"]) for s in outline["sections"]] == [("intro", 4), ("build", 8), ("lift", 8), ("outro", 4)]
    assert outline["sections"][1]["chords"] == ["Em", "C", "G", "D"] and outline["sections"][2]["chords"] == ["C", "D", "Em", "Em"]
    tracks = {t["name"]: t for t in outline["tracks"]}
    assert tracks["kick"]["sections"] == ["build", "lift", "outro"] and tracks["melody"]["sections"] == ["lift"]
    assert score.beat == 26664 and score.bar == 4 * 26664 and score.samples == 24 * score.bar


def test_every_problem_is_reported_with_a_suggestion() -> None:
    data = _score(tempp=3, key="A minr", progression="i VIm Q7")
    data["tracks"] = {
        "kick": {"instrument": "kik", "steps": "x..."},
        "bass": {"instrument": "synth_bass", "steps": "1..1 a...", "rest": ["bb"]},
        "arp": {"instrument": "pluck", "steps": "1358 5315 1358 531", "accent": "3+3+2"},
        "hat": {"instrument": "hat", "steps": "x.3.", "octave": 4},
        "pad": {"instrument": "pad", "play": "chords", "sections": {"b": "rest"}},
        "lead": {"instrument": "bell", "play": "chords"},
    }
    text = _problems(data)
    for part in (
        "tempp: unknown key; did you mean 'tempo'?",
        "did you mean 'A minor'?",
        "'VIm': a Roman numeral shows minor by lower case",
        "'Q7' is not a chord",
        "unknown instrument 'kik'; did you mean 'kick'?",
        "no section 'bb'; did you mean 'b'?",
        "notes start with a capital letter",
        "do not fill bar 1 of the steps (15 steps)",
        "hat has no pitch",
        "list the section in rest: (rest: [b])",
        "bell cannot hold chords",
    ):
        assert part in text, part
    assert text.count("'Q7' is not a chord") == 1  # reported once, not per section


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"tempo": 400}, "tempo: 400 is out of range"),
        ({"time": "4-4"}, "time: write the time signature"),
        ({"bars": 8}, "give either bars or sections"),
        ({"sections": [{"name": "a", "bars": 4}, {"name": "a", "bars": 4}]}, "section 'a' is already used"),
        ({"progression": None}, "progression: missing: tracks pad, bass play notes"),
        ({"chord_bars": 0.3}, "not a whole number of beats"),
        ({"tracks": {}}, "at least one track"),
        ({"tracks": {"k": {"instrument": "kick"}}}, "no steps for section 'a'"),
        ({"tracks": {"k": {"instrument": "kick", "steps": "x", "settings": {"decy": 0.1}}}}, "did you mean 'decay'"),
        ({"tracks": {"k": {"instrument": "kick", "steps": "x", "settings": {"decay": 9}}}}, "decay: 9 is out of range"),
        ({"tracks": {"k": {"instrument": "kick", "steps": "x", "rest": ["a"], "only": ["b"]}}}, "not both"),
        ({"loop": "yes"}, "loop: expected true"),
        ({"version": 2}, "score files of version 1"),
    ],
)
def test_score_problems(change: dict[str, Any], message: str) -> None:
    data = _score(**change)
    if data.get("progression") is None:
        data.pop("progression")
    assert message in _problems(data)


def test_drums_need_no_progression_and_bars_make_one_section() -> None:
    score = parse_music_score({"key": "C", "tempo": 100, "bars": 2, "tracks": {"k": {"instrument": "kick", "steps": "x.x."}}})
    assert [s.name for s in score.sections] == ["main"] and score.bars == 2


def test_explicit_voicing_and_section_key() -> None:
    data = _score(progression=[{"chord": "Dm(add9)", "notes": ["D3", "A3", "E4", "F4"], "bass": "D2"}, "Bb"])
    data["sections"][1]["key"] = "C minor"
    data["sections"][1]["progression"] = "i iv"
    score = parse_music_score(data)
    first = score.sections[0].chords[0]
    assert first.notes == (50, 57, 64, 65) and first.bass_note == 38 and first.chord.name == "Dm(add9)"
    assert [c.chord.name for c in score.sections[1].chords] == ["Cm", "Fm", "Cm", "Fm"] and score.sections[1].key.name == "C minor"


# ----- rendering ---------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def small_loop() -> tuple[Any, np.ndarray]:
    score = parse_music_score(_score())
    return score, render_music_score(score)


def test_loop_is_exact_level_deterministic_and_seamless(small_loop: tuple[Any, np.ndarray]) -> None:
    score, audio = small_loop
    assert audio.dtype == np.float32 and audio.shape == (score.samples, 2) and not audio.flags.writeable
    assert score.samples == 8 * 4 * 24000
    assert loudness.integrated_loudness(audio) == pytest.approx(music.MUSIC_LEVEL, abs=0.05)
    assert np.array_equal(audio, render_music_score(parse_music_score(_score())))
    x = audio.astype(np.float64)
    steps = np.abs(np.diff(x, axis=0))
    assert (np.abs(x[0] - x[-1]) <= np.quantile(steps, 0.999, axis=0)).all()
    assert 20 * math.log10(float(np.abs(x).max())) < -9


def test_sections_rest_and_seed_changes_the_pad(small_loop: tuple[Any, np.ndarray]) -> None:
    score, audio = small_loop
    half = score.samples // 2
    low = lambda x: float(np.sqrt(np.mean(np.fft.irfft(np.fft.rfft(x.mean(axis=1)) * (np.fft.rfftfreq(len(x), 1 / RATE) < 70), len(x)) ** 2)))
    assert low(audio[half:].astype(np.float64)) > 1.5 * low(audio[:half].astype(np.float64))  # the kick plays only in b
    other = render_music_score(parse_music_score(_score(seed=2)))
    assert not np.array_equal(audio, other)


def test_one_shot_keeps_its_tail_and_ends_silent() -> None:
    data = _score(loop=False)
    data["tracks"]["bell"] = {"instrument": "bell", "steps": "x . . . | . . . . | . . . . | . . . 8"}
    score = parse_music_score(data)
    audio = render_music_score(score)
    assert score.samples < len(audio) <= score.samples + 8 * RATE + RATE
    assert np.abs(audio[-10:]).max() < 1e-4 and np.abs(audio[:5]).max() < 0.01
    assert loudness.integrated_loudness(audio) == pytest.approx(music.MUSIC_LEVEL, abs=0.05)


@pytest.mark.slow
def test_demo_renders_with_its_lift() -> None:
    score = load_music_score(DEMO)
    audio = render_music_score(score).astype(np.float64)
    assert len(audio) == score.samples and loudness.integrated_loudness(audio) == pytest.approx(-28.0, abs=0.05)
    levels = {s.name: loudness.integrated_loudness(audio[score.section_start(s) : score.section_start(s) + s.bars * score.bar]) for s in score.sections}
    assert levels["intro"] < levels["build"] < levels["lift"]
    steps = np.abs(np.diff(audio, axis=0))
    assert (np.abs(audio[0] - audio[-1]) <= np.quantile(steps, 0.999, axis=0)).all()


def test_every_instrument_plays() -> None:
    tracks = {}
    for name, inst in INSTRUMENTS.items():
        tracks[name] = {"instrument": name, "play": "chords"} if inst.kind == "pad" else {"instrument": name, "steps": "x.x." if inst.kind == "drum" else "1 3 5 *"}
    score = parse_music_score({"key": "D minor", "tempo": 110, "bars": 1, "progression": "i", "tracks": tracks})
    audio = render_music_score(score)
    assert np.isfinite(audio).all() and np.abs(audio).max() > 0


def test_studio_imports_no_video_code() -> None:
    import subprocess
    import sys

    code = "import sys, vidgen.studio; print(' '.join(sorted(sys.modules)))"
    loaded = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout.split()
    assert "manim" not in loaded
    assert not [m for m in loaded if m.startswith(("vidgen.scene", "vidgen.render", "vidgen.scenes", "vidgen.cartoon", "vidgen.project"))]


# ----- the command ---------------------------------------------------------------------------------------


def test_music_render_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "theme.yaml"
    path.write_text(yaml.safe_dump(_score(title="Theme")), encoding="utf-8")
    out = tmp_path / "theme.wav"
    assert cli.main(["music", "render", str(path), "--out", str(out), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] and doc["action"] == "render" and doc["title"] == "Theme" and doc["bars"] == 8
    assert doc["loudness"] == pytest.approx(-28.0, abs=0.1) and doc["wav_seconds"] == pytest.approx(16.0)
    assert [s["name"] for s in doc["sections"]] == ["a", "b"] and doc["sections"][1]["start"] == pytest.approx(8.0)
    assert read_wav(out).shape == (16 * RATE, 2)
    assert cli.main(["music", "render", str(path), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Theme: A minor, 120 BPM, 4/4, 8 bars = 16.00 s (a seamless loop)" in text and "loudness: -28.0 LUFS" in text
    path.write_text("key: A minor\ntempo: 120\nbars: 2\ntracks: {k: {instrument: kik, steps: x}}\n", encoding="utf-8")
    assert cli.main(["music", "render", str(path), "--out", str(out)]) == 1
    assert "did you mean 'kick'" in capsys.readouterr().err
