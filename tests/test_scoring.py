"""Step 289: music cues for dramas (DESIGN.md §112.2): named themes that scenes and sections play,
cross-fading at the changes, motifs on beats, stings on words, ducking presets with a swell into
the pauses, theme variations rendered from their score, and the dense-dialogue music check.
Narration is mocked: each beat's "MP3" is a WAV tone (PyAV reads it by its content)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import config, mix, schema, scoring
from vidgen.audio_only import plan_audio, render_audio
from vidgen.errors import VidgenError
from vidgen.music import config_problems
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.sfx import RATE, write_wav
from vidgen.sound_design import word_offset

#: A small project piece: a pad on the chords, a kick, a lead ducking under the kick.
PIECE = {
    "version": 1, "key": "A minor", "tempo": 120, "bars": 4, "progression": "i VI III VII",
    "tracks": {
        "pad": {"instrument": "pad", "play": "chords"},
        "kick": {"instrument": "kick", "steps": "x... x... x... x..."},
        "lead": {"instrument": "piano", "steps": "1 . 3 . 5 . 3 .", "duck": {"to": "kick", "depth": 0.3, "release": 0.25}},
    },
}


def _write(root: Path, data: dict[str, Any], piece: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    if piece:
        (root / "assets" / "music").mkdir(parents=True, exist_ok=True)
        (root / "assets" / "music" / "motif.yaml").write_text(yaml.safe_dump(PIECE, sort_keys=False), encoding="utf-8")
    return root


def _voice_all(project: Project, seconds: float = 1.2) -> None:
    t = np.arange(round(seconds * RATE)) / RATE
    for k, (_, beat) in enumerate(project.beats()):
        write_wav(project.audio_dir / f"{beat.id}.mp3", (0.2 * np.sin(2 * np.pi * (200 + 40 * k) * t)).astype(np.float32))


DRAMA: dict[str, Any] = {
    "title": "Drama",
    "narration": {"pad": 0.3, "words_per_second": 2},
    "voices": {"b": {"voice_id": "other", "pan": "right"}},
    "score": {"themes": {"tension": "calm", "warm": {"source": "motif", "volume": -2}}, "crossfade": 2.0},
    "sections": [
        {"id": "night", "title": "Night", "music": "tension",
         "beats": [{"text": "the door opened", "sting": {"kind": "reveal", "at": "@opened"}}, {"text": "who is there", "voice": "b", "pause": 3.0}]},
        {"pause": 2.0},
        {"id": "day", "title": "Day", "music": "warm",
         "beats": [{"text": "morning came at last", "motif": {"theme": "warm", "at": "end", "length": 3}}, {"text": "it is you", "voice": "b"}]},
    ],
}


# ----- config ---------------------------------------------------------------------------------------------


def test_settings_parse() -> None:
    cue = config.MusicCue.model_validate({"source": "calm", "duck": "drama"})
    assert (cue.duck.depth, cue.duck.release, cue.duck.swell, cue.duck.preset) == (18.0, 2.5, 3.0, "drama")
    cue = config.MusicCue.model_validate({"source": "calm", "duck": {"preset": "deep", "swell": 2}})
    assert (cue.duck.depth, cue.duck.swell) == (24.0, 2.0)
    assert config.MusicCue.model_validate({"source": "calm"}).duck == config.DuckConfig()   # unchanged default
    scene = config.SceneConfig.model_validate({"id": "s", "type": "title", "duration": 1, "music": "tension"})
    assert isinstance(scene.music, config.SceneMusic) and scene.music.theme == "tension" and scene.music.volume == 0
    beat = config.BeatConfig.model_validate({"id": "b", "text": "the door opened", "motif": "love", "sting": {"kind": "reveal", "at": "@door"}})
    assert beat.motif is not None and beat.motif.theme == "love" and beat.motif.at == "start" and beat.sting is not None and beat.sting.placed_at == "@door"
    score = config.ScoreConfig.model_validate({"themes": {"main": "calm", "love": {"source": "motif", "transpose": -2, "tracks": ["pad"]}}})
    assert score.themes["main"].source == "calm" and score.themes["love"].tracks == ["pad"] and score.duck.preset == "drama"


@pytest.mark.parametrize("data, message", [
    ({"score": {"duck": "dramma"}}, "did you mean 'drama'"),
    ({"scenes": [{"id": "s", "type": "title", "beats": [{"text": "hi there", "sting": {"kind": "reveal", "at": "@door"}}]}]}, 'sting at .*does not say "door"'),
    ({"scenes": [{"id": "s", "type": "title", "beats": [{"text": "hi there", "motif": {"theme": "x", "at": "@door"}}]}]}, 'motif at .*does not say "door"'),
])
def test_setting_errors(data: dict[str, Any], message: str) -> None:
    base = {"title": "t", "scenes": [{"id": "s", "type": "title", "beats": [{"text": "hi"}]}]}
    with pytest.raises(VidgenError, match=message):
        config.parse_config({**base, **data})


@pytest.mark.slow
def test_schema_takes_a_theme_name() -> None:
    music = schema.config_schema([], [])["properties"]["sections"]["items"]["anyOf"][0]["properties"]["music"]
    assert {"type": "string", "minLength": 1} in music["anyOf"]


def test_theme_problems(tmp_path: Path) -> None:
    data = {"title": "t", "score": {"themes": {"main": "assets/music/theme.mp3", "lost": "nowhere"}}, "scenes": [
        {"id": "a", "type": "title", "music": "tensoin", "beats": [{"text": "hi"}]},
        {"id": "b", "type": "title", "music": {"theme": "main", "variation": {"transpose": 2}}, "beats": [{"text": "hi", "motif": {"theme": "motif", "variation": {"tracks": ["pda"]}}}]},
        {"id": "c", "type": "title", "music": {"theme": "calm", "variation": {"section": "lift"}}, "beats": [{"text": "hi"}]},
    ]}
    root = _write(tmp_path / "p", data, piece=True)
    (root / "assets" / "music" / "theme.mp3").write_bytes(b"")
    problems = dict(config_problems(Project.load(root).config, root))
    assert "nowhere" in problems["score.themes.lost.source"]
    assert "unknown theme 'tensoin'" in problems["scenes[0].music"]
    assert "only a score" in problems["scenes[1].music"]
    assert "no track 'pda'; did you mean 'pad'" in problems["scenes[1].beats[0].motif"]
    assert "no section 'lift'" in problems["scenes[2].music"]                                           # calm's template has one section


# ----- the walk, fades, ducking -------------------------------------------------------------------------------


def test_fade_curves() -> None:
    u = np.linspace(0, 1, 11)
    up, down = scoring.fade_shape(u, "equal_power"), scoring.fade_shape(1 - u, "equal_power")
    assert np.allclose(up**2 + down**2, 1.0)                                                             # even power
    assert np.allclose(scoring.fade_shape(u, "linear") + scoring.fade_shape(1 - u, "linear"), 1.0)
    smooth = scoring.fade_shape(u, "smooth")
    assert smooth[0] == 0 and smooth[-1] == pytest.approx(1) and smooth[5] == pytest.approx(0.5) and smooth[1] < u[1]


def test_themes_change_with_the_scenes() -> None:
    cfg = config.parse_config({"title": "t", "score": {"themes": {"a": "calm", "b": "enigma"}, "crossfade": 2.0, "fade_in": 1.0, "fade_out": 3.0}, "scenes": [
        {"id": "s1", "type": "title", "music": "a", "duration": 10},
        {"id": "s2", "type": "title", "duration": 10},                                                     # a plays on
        {"id": "s3", "type": "title", "music": "a", "duration": 10},                                       # the same: no break
        {"id": "s4", "type": "title", "music": {"theme": "a", "variation": {"transpose": 2}}, "duration": 10},
        {"id": "s5", "type": "title", "music": False, "duration": 10},
        {"id": "s6", "type": "title", "music": "b", "duration": 10},
    ]})
    pieces = scoring.theme_pieces(cfg, [(10.0 * k, 10.0) for k in range(6)], 60.0)
    got = [(p.play.name, p.play.transpose, p.start, p.end, p.fade_in, p.fade_out) for p in pieces]
    assert got == [("a", None, 0.0, 31.0, 1.0, 2.0), ("a", 2, 29.0, 41.0, 2.0, 2.0), ("b", None, 49.0, 60.0, 2.0, 3.0)]
    assert not scoring.uses_score(config.parse_config({"title": "t", "scenes": [{"id": "s", "type": "title", "duration": 1}]}))


def test_swell_follows_the_release() -> None:
    frames = 2000
    spans = [(1.0, 5.0), (12.0, 15.0)]
    plain = config.DuckConfig()
    assert np.array_equal(mix.duck_gain_db(spans, frames, plain), mix.duck_curve(spans, frames, plain))   # no swell: as before
    drama = config.DuckConfig.model_validate("drama")
    gain = mix.duck_gain_db(spans, frames, drama)
    assert gain[300] == pytest.approx(-18.0)                                                            # under the speech
    assert gain[900] == pytest.approx(3.0)                                                              # up in the long pause
    rise = gain[500:760]
    assert np.all(np.diff(rise) >= -1e-9) and gain[600] < 0 < gain[760]                                 # the release is smooth and slow


def test_variation_of_a_score(tmp_path: Path) -> None:
    root = _write(tmp_path / "p", {"title": "t", "scenes": [{"id": "s", "type": "title", "duration": 1}]}, piece=True)
    path = root / "assets" / "music" / "motif.yaml"
    plain = scoring.variant_score(path, scoring.ThemePlay("m", "motif"))
    varied = scoring.variant_score(path, scoring.ThemePlay("m", "motif", transpose=3, tempo=90, tracks=("pad", "lead")))
    assert [t.name for t in varied.tracks] == ["pad", "lead"] and varied.tempo == 90 and varied.beat > plain.beat
    lead = next(t for t in varied.tracks if t.name == "lead")
    assert all(p.transpose == 3 and p.duck is None for p in lead.parts.values())                          # the kick is gone: no duck
    kick = scoring.variant_score(path, scoring.ThemePlay("m", "motif", transpose=3)).tracks[1]
    assert kick.name == "kick" and all(p.transpose == 0 for p in kick.parts.values())                     # drums keep their pitch
    with pytest.raises(VidgenError, match="did you mean 'pad'"):
        scoring.variant_score(path, scoring.ThemePlay("m", "motif", tracks=("pda",)))


# ----- in the mix ---------------------------------------------------------------------------------------------


@pytest.mark.slow
def test_render_with_themes_motif_and_sting(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "p", DRAMA, piece=True))
    _voice_all(project)
    plan = plan_audio(project)
    night, _, day = plan.scenes
    sting = next(e for e in night.events if e.duck)
    first = night.beats[0]
    assert sting.time == pytest.approx(first.start + word_offset(project, project.config.scenes[0].beats[0], "@opened"))
    assert sting.time > first.start + 0.1                                                               # on its word, not before the line
    result = render_audio(project)
    timings = json.loads(result.timings_file.read_text(encoding="utf-8"))
    music = timings["mix"]["music"]
    assert [(m["theme"], m.get("motif", False)) for m in music] == [("tension", False), ("warm", False), ("warm", True)]
    tension, warm, motif = music
    assert tension["end"] == pytest.approx(day.start + 1.0) and warm["start"] == pytest.approx(day.start - 1.0)
    assert tension["from"] == "night" and warm["volume"] == -2 and motif["start"] > day.beats[0].start
    assert tension["swell"] == 3.0 and tension["duck"] == 18.0
    check = timings["mix"]["music_check"]
    assert check["under_dialogue_lu"] > check["in_pauses_lu"]                                           # the music is lower under the lines
    total = round(plan.duration * RATE)
    placements = mix.plan_score(project, timings, total)
    bed = placements[0]
    times = np.arange(len(bed.gain)) / 100
    dips = scoring.dip_curve(times, [], scoring.sting_windows(project, timings), project.config.score.sting_dip, "smooth")
    k_under, k_pause = round((night.beats[1].start + 0.6) * 100), round((night.beats[1].end + 2.4) * 100)
    assert dips[k_pause] == 0
    assert 20 * np.log10(bed.gain[k_pause] / bed.gain[k_under]) + dips[k_under] == pytest.approx(21.0, abs=0.3)   # 18 dB duck + 3 dB swell
    at = round((sting.time + 0.3) * 100)
    assert bed.gain[at] < 10 ** (-17.5 / 20) * 10 ** (-3.9 / 20)                                        # dipped under the sting
    warm_bed = placements[1]
    t = round((motif["start"] + 1.5) * 100)
    plain = 10 ** (-2 / 20) * np.interp(t, np.arange(len(warm_bed.gain)), warm_bed.gain)
    assert 20 * np.log10(plain / 10 ** (-2 / 20)) < -5.5                                                # the scene's theme dips 6 dB under the motif


@pytest.mark.slow
def test_dense_dialogue_check() -> None:
    total = 20 * RATE
    rng = np.random.default_rng(1)
    noise = rng.standard_normal((total, 2)) * 0.05

    def voice(a: int, b: int) -> np.ndarray:
        return noise[a:b].copy()

    speech = [(0.5, 3.0), (3.2, 6.0), (6.2, 9.0), (13.0, 14.0)]
    loud = scoring.dense_dialogue_check(total, voice, lambda a, b: noise[a:b] * 0.3, speech, 15.0)
    quiet = scoring.dense_dialogue_check(total, voice, lambda a, b: noise[a:b] * 0.05, speech, 15.0)
    assert len(loud["dense"]) == 1 and loud["dense"][0]["start"] < 2.0 < 7.5 < loud["dense"][0]["end"]
    assert loud["worst_dense_lu"] == pytest.approx(10.5, abs=0.3) and not loud["ok"]                    # 20 log10(1/0.3)
    assert quiet["worst_dense_lu"] == pytest.approx(26.0, abs=0.3) and quiet["ok"]
    assert loud["in_pauses_lu"] == pytest.approx(10.5, abs=0.3)


@pytest.mark.render
def test_a_video_scene_plays_a_sting_on_a_word(tmp_path: Path) -> None:
    from manim import tempconfig

    from vidgen import extensions, registry

    data = {"title": "t", "narration": {"pad": 0.3, "words_per_second": 2}, "scenes": [
        {"id": "s", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "one two three four", "sting": {"kind": "reveal", "at": "@three"}}]}]}
    project = Project.load(_write(tmp_path / "p", data))
    extensions.load_builtins()
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_rate": 5, "media_dir": str(tmp_path / "media"),
                     "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}):
        with extensions.project_session(project):
            scene = registry.get("text_card").cls(project.scene("s"), project)
            scene.render()
    sting = next(e for e in scene.timings()["sfx"] if e.get("duck"))
    assert sting["time"] == pytest.approx(word_offset(project, project.config.scenes[0].beats[0], "@three"), abs=0.01) and sting["time"] > 0.5


# ----- compatibility --------------------------------------------------------------------------------------


@pytest.mark.slow
def test_unset_options_change_nothing(tmp_path: Path) -> None:
    pin = {"title": "Pin", "narration": {"pad": 0.3, "words_per_second": 2}, "music": {"source": "calm"},
           "sections": [{"id": "one", "title": "One", "beats": ["one two three four", {"text": "a b c d", "sting": "reveal"}]}]}
    plain = Project.load(_write(tmp_path / "a", pin))
    _voice_all(plain)
    same = {**pin, "score": {"themes": {"x": "calm"}, "crossfade": 6, "duck": "deep"}, "music": {"source": "calm", "duck": {"swell": 0}}}
    other = Project.load(_write(tmp_path / "b", same))
    _voice_all(other)
    a, b = render_audio(plain), render_audio(other)
    assert a.output.read_bytes() == b.output.read_bytes() and "music_check" not in b.timings["mix"]


@pytest.mark.slow
def test_fingerprint_ignores_the_score(tmp_path: Path) -> None:
    base = {"title": "t", "scenes": [{"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "the rain"}]}]}
    plain = scene_fingerprint(Project.load(_write(tmp_path / "a", base)), "s")
    scored = {**base, "score": {"themes": {"m": "calm"}}, "scenes": [{**base["scenes"][0], "music": "m", "beats": [{"text": "the rain", "motif": "m"}]}]}
    assert scene_fingerprint(Project.load(_write(tmp_path / "b", scored)), "s") == plain
