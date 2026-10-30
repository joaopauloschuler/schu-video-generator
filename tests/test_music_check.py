"""``vidgen music check`` (Step 187, DESIGN.md §93.9): the measures and limits on small synthetic
sounds and small scores (each fault flagged, with advice naming the score's keys), the track-by-
track render, schu-video-generator's ducking for the narration demo, the pictures, the command, and two
templates of the built-in beds that must pass as fine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import cli
from vidgen.config import DuckConfig
from vidgen.mix import duck_curve
from vidgen.sfx import RATE, write_wav
from vidgen.studio import check_music_audio, check_music_score, music_check_text, parse_music_score, render_music_score
from vidgen.studio import check as chk
from vidgen.studio.render import render_music_stems
from vidgen.studio.templates import template_path


def _score(**changes: Any) -> dict[str, Any]:
    """A small score with a build and a lift (10 bars at 120 BPM: 20 s), changed by ``changes``."""
    data: dict[str, Any] = {
        "key": "A minor",
        "tempo": 120,
        "progression": "i VI III VII",
        "sections": [{"name": "intro", "bars": 2}, {"name": "build", "bars": 4}, {"name": "lift", "bars": 4}],
        "tracks": {
            "pad": {"instrument": "pad", "play": "chords", "sections": {"build": {"volume": {"from": -6, "to": 0}}, "lift": {"settings": {"tone": 3200}, "volume": 2}}},
            "kick": {"instrument": "kick", "steps": "x... x... x... x...", "rest": ["intro"]},
            "bass": {"instrument": "synth_bass", "steps": ".1.1 .1.1 .1.1 .1.1"},
            "riser": {"instrument": "riser", "only": ["build"], "steps": ". | . | x | -"},
            "hat": {"instrument": "hat", "only": ["lift"], "steps": "..x. ..x. ..x. ..x."},
        },
    }
    data.update(changes)
    return data


def _check(data: dict[str, Any]) -> chk.MusicCheck:
    return check_music_score(parse_music_score(data, "t.yaml"))


def _levels(report: chk.MusicCheck) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in report.findings:
        out.setdefault(f.topic, []).append(f.level)
    return out


def _fixes(report: chk.MusicCheck, topic: str) -> str:
    return " ".join(fix for f in report.findings if f.topic == topic for fix in f.fixes)


# ----- pieces that pass, pieces that fail ------------------------------------------------------------


def test_a_good_small_score_passes() -> None:
    report = _check(_score())
    assert report.verdict.startswith("fine under narration"), music_check_text(report)
    assert report.facts["lufs"] == pytest.approx(-28.0, abs=0.05)
    assert report.facts["tempo_heard"] == pytest.approx(120.0, rel=0.01)
    assert report.facts["seam_ratio"] < 1 and report.facts["in_key"] > 0.9
    assert {s["name"] for s in report.sections} == {"intro", "build", "lift"}
    assert [t["name"] for t in report.tracks] == ["pad", "kick", "bass", "riser", "hat"]
    assert sum(t["all_share"] for t in report.tracks) == pytest.approx(1.0, abs=0.01)
    text = music_check_text(report)
    assert "the lift lifts" in text and "the build builds" in text and "advice" not in text


def test_a_flat_lift_and_build_are_flagged_with_fixes() -> None:
    tracks = {
        "pad": {"instrument": "pad", "play": "chords", "sections": {"lift": {"volume": -3}}},
        "kick": {"instrument": "kick", "steps": "x... x... x... x..."},
        "bass": {"instrument": "synth_bass", "steps": ".1.1 .1.1 .1.1 .1.1"},
    }
    report = _check(_score(tracks=tracks))
    texts = [f.text for f in report.findings if f.topic == "sections" and f.level == "fix"]
    assert any("the build does not build" in t for t in texts) and any("the lift does not lift" in t for t in texts)
    fixes = _fixes(report, "sections")
    assert "`pad` is 3 dB quieter in the lift than in the build" in fixes and "`pad: sections: {lift: {volume: 2}}`" in fixes
    assert "riser" in fixes and "volume: {from: -6, to: 0}" in fixes


def test_a_loud_mid_range_part_competes_with_the_voice() -> None:
    tracks = {
        "pad": {"instrument": "pad", "play": "chords", "volume": -6},
        "piano": {"instrument": "piano", "steps": "* . * . * . * .", "octave": 4, "volume": 4, "only": ["lift"]},
    }
    report = _check(_score(tracks=tracks))
    assert _levels(report)["voice range"] == ["fix"]
    found = next(f for f in report.findings if f.topic == "voice range")
    assert "bars 7-10" in found.text
    fix = _fixes(report, "voice range")
    assert "`piano` (piano) holds" in fix and "`piano.volume: " in fix and "(now 4)" in fix and "`octave: 5`" in fix


def test_boomy_harsh_and_out_of_key_scores_are_flagged() -> None:
    boomy = _check(_score(tracks={
        "pad": {"instrument": "pad", "play": "chords", "volume": -10},
        "kick": {"instrument": "kick", "steps": "x..x ..x. x..x ..x.", "volume": 8},
        "boom": {"instrument": "boom", "steps": "x | . | . | .", "volume": 12},
    }))
    assert _levels(boomy)["bass"] == ["fix"] and "`kick.volume: " in _fixes(boomy, "bass")
    harsh = _check(_score(master={"lowpass": 16000}, tracks={
        "pad": {"instrument": "pad", "play": "chords"},
        "hat": {"instrument": "hat", "steps": "xxxx xxxx xxxx xxxx", "volume": 12, "settings": {"tone": 9000}},
    }))
    assert _levels(harsh)["highs"] == ["fix"]
    assert "master: {lowpass: 16000}" in _fixes(harsh, "highs") and "`hat`" in _fixes(harsh, "highs")
    off = _check(_score(key="C major", progression="F#m C#m D#m G#", tracks={"pad": {"instrument": "pad", "play": "chords"}}))
    assert _levels(off)["key"] == ["fix"] and "C major" in next(f.text for f in off.findings if f.topic == "key")


def test_a_quiet_intro_under_a_loud_lift_is_unsteady() -> None:
    tracks = {
        "pad": {"instrument": "pad", "play": "chords", "sections": {"intro": {"volume": -24}, "build": {"volume": -24}}},
        "saw": {"instrument": "supersaw", "play": "chords", "only": ["lift"], "volume": 2},
        "kick": {"instrument": "kick", "steps": "x... x... x... x...", "only": ["lift"], "volume": 4},
    }
    report = _check(_score(tracks=tracks))
    assert _levels(report)["steadiness"] == ["fix"]
    fixes = _fixes(report, "steadiness")
    assert "`pad` is 24 dB quieter in the intro and the build than in the lift" in fixes
    assert "`pad: sections: {intro: {volume: -7}, build: {volume: -7}}` (+17 dB)" in fixes and "`saw`, `kick`" in fixes


def test_audio_files_clipping_and_a_seam_click() -> None:
    t = np.arange(4 * RATE) / RATE
    clean = 0.3 * np.sin(2 * np.pi * 220 * t)  # whole periods: a seamless loop
    report = check_music_audio(np.stack([clean, clean], axis=1), "tone")
    assert _levels(report)["loop seam"] == ["ok"] and _levels(report)["clipping"] == ["ok"]
    assert report.facts["lufs"] == pytest.approx(-28.0, abs=0.05) and report.sections == [] and report.tracks == []
    bad = np.clip(1.8 * clean / 0.3, -1, 1)
    bad[-100:] = np.linspace(bad[-100], 0.9, 100)
    report = check_music_audio(np.stack([bad, bad], axis=1), "bad")
    assert _levels(report)["clipping"] == ["fix"] and _levels(report)["loop seam"] == ["fix"]
    assert report.verdict.startswith("needs work")
    assert "cross-fade" in _fixes(report, "loop seam")


def test_tempo_words_accept_the_same_beat_heard_another_way() -> None:
    level, words = chk._tempo_words(72.0, 108.0)
    assert level == "ok" and "2/3" in words and "3+3+2" in words
    assert chk._tempo_words(216.5, 108.0)[0] == "ok" and "double time" in chk._tempo_words(216.5, 108.0)[1]
    assert chk._tempo_words(100.0, 108.0)[0] == "note"
    assert chk._tempo_words(None, 108.0)[0] == "ok"


# ----- the pieces ------------------------------------------------------------------------------------


def test_track_by_track_render_matches_the_render() -> None:
    score = parse_music_score(_score(), "t.yaml")
    seen: dict[str, float] = {}
    mix, gain = render_music_stems(score, lambda name, sound: seen.__setitem__(name, float(np.abs(sound).max())))
    whole = render_music_score(score)
    assert list(seen) == ["pad", "kick", "bass", "riser", "hat"] and all(v > 0 for v in seen.values())
    assert mix.shape == whole.shape and float(np.abs(mix - whole).max()) < 1e-5 and gain > 0
    one_shot = parse_music_score(_score(loop=False), "t.yaml")
    mix, _ = render_music_stems(one_shot, lambda name, sound: None)
    assert float(np.abs(mix - render_music_score(one_shot)).max()) < 1e-5


def test_ducking_is_vidgens_default() -> None:
    duck = DuckConfig()
    assert chk.DUCK == (duck.depth, duck.attack, duck.release, duck.hold)
    spans = [(1.0, 2.5), (3.2, 4.0), (7.0, 8.0)]
    assert np.allclose(chk.duck_gain_db(spans, 1000), duck_curve(spans, 1000, duck))


def test_narration_demo() -> None:
    voice, name = chk.load_narration(None)
    assert name == "narration_sample.mp3" and len(voice) == pytest.approx(20 * RATE, abs=RATE // 10)
    spans = chk.speech_spans(voice)
    assert spans[0][0] == pytest.approx(2.0, abs=0.1) and spans[-1][1] < 17.0
    music = render_music_score(parse_music_score(_score(), "t.yaml"))
    mix, facts = chk.narration_demo(music, voice)
    assert mix.shape == (len(voice), 2)
    assert facts["voice_lufs"] == pytest.approx(chk.NARRATION_LUFS, abs=0.5)
    assert facts["music_under_voice_lufs"] < -38 and facts["voice_clear_db"] > chk.LIMITS["voice_clear_db"]
    assert 20 * np.log10(np.abs(mix).max()) <= chk.DEMO_TRUE_PEAK + 0.01


def test_pictures_and_comparison() -> None:
    a = _check(_score())
    t = np.arange(8 * RATE) / RATE
    b = check_music_audio(np.stack([0.2 * np.sin(2 * np.pi * 330 * t)] * 2, axis=1), "short", hop=chk.frame_hop(a.seconds))
    one = chk.spectrogram_image([a])
    two = chk.spectrogram_image([a, b])
    assert one.width == two.width and two.height == 2 * one.height + 4
    rows = chk.compare_rows(a, b)
    assert rows[0] == {"label": "length (s)", "a": "20.0", "b": "8.0"} and rows[-1]["label"] == "verdict"
    assert "short" in chk.compare_text(a, b)


# ----- the command -----------------------------------------------------------------------------------


def test_music_check_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    score = tmp_path / "theme.yaml"
    score.write_text(yaml.safe_dump(_score(title="Theme")), encoding="utf-8")
    other = tmp_path / "other.wav"
    t = np.arange(3 * RATE) / RATE
    write_wav(other, np.stack([0.2 * np.sin(2 * np.pi * 330 * t)] * 2, axis=1))
    out = tmp_path / "out"
    assert cli.main(["music", "check", str(score), "--out", str(out), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] and doc["action"] == "check" and doc["kind"] == "score" and doc["name"] == "Theme"
    assert doc["verdict"].startswith("fine") and doc["compare"] is None
    assert {f["topic"] for f in doc["findings"]} >= {"loudness", "voice range", "sections", "narration"}
    assert Path(doc["files"]["spectrogram"]).is_file() and Path(doc["files"]["demo"]).is_file()
    assert cli.main(["music", "check", str(score), "--out", str(out), "--compare", str(other)]) == 0
    text = capsys.readouterr().out
    assert "verdict: fine under narration" in text and "compared with" in text and "voice clear of music (dB)" in text
    assert (out / "theme-vs-other.png").is_file() and (out / "other-demo.mp3").is_file()
    assert cli.main(["music", "check", str(tmp_path / "missing.yaml")]) == 1
    assert "not found" in capsys.readouterr().err


# ----- templates -------------------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("bed", ["pulse", "horizon"])
def test_templates_pass_as_fine(bed: str) -> None:
    from vidgen.studio import load_music_score

    report = check_music_score(load_music_score(template_path(bed)))
    assert report.verdict == "fine under narration", music_check_text(report)
    if bed == "horizon":  # its build builds and its lift lifts (by brightness more than loudness)
        assert {s["name"] for s in report.sections} >= {"build", "lift"}
        assert sum(f.topic == "sections" and f.level == "ok" for f in report.findings) == 2
