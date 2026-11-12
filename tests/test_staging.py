"""Step 285: stereo staging and room acoustics of the voices, music width, the mono-compatibility
check (DESIGN.md §111.4). Narration is mocked: each beat's "MP3" is a WAV tone."""

from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any, get_args

import numpy as np
import pytest
import yaml

from vidgen import audio_check, cli, config, mix
from vidgen.audio_only import plan_audio, render_audio
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.sfx import RATE, decode_audio, write_wav
from vidgen.staging import POSITIONS, ROOM_PRESETS, ROOMS, VoiceStaging, beat_staging, params_stage_pan, reverb_ir, stage_voice, widen


def _write(root: Path, data: dict[str, Any]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return root


def _voice_all(project: Project, seconds: float = 1.2) -> None:
    t = np.arange(round(seconds * RATE)) / RATE
    for k, (_, beat) in enumerate(project.beats()):
        write_wav(project.audio_dir / f"{beat.id}.mp3", (0.2 * np.sin(2 * np.pi * (200 + 40 * k) * t)).astype(np.float32))


def _read_24(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as src:
        raw = np.frombuffer(src.readframes(src.getnframes()), dtype=np.uint8).reshape(-1, 3)
    ints = raw[:, 0].astype(np.int32) | raw[:, 1].astype(np.int32) << 8 | raw[:, 2].astype(np.int8).astype(np.int32) << 16
    return (ints / 8388608).reshape(-1, 2)


def _db(a: np.ndarray, b: np.ndarray) -> float:
    return 10 * math.log10(float(np.sum(a**2)) / float(np.sum(b**2)))


TONE = (0.1 * np.sin(2 * np.pi * 440 * np.arange(RATE) / RATE)).astype(np.float32)[:, None]

# ----- config -------------------------------------------------------------------------------------------


def test_names_match_the_config_literals() -> None:
    assert set(POSITIONS) == set(get_args(config.PanPosition))
    assert ROOMS == get_args(config.RoomName)


def test_settings_parse_and_errors(tmp_path: Path) -> None:
    beat = config.BeatConfig.model_validate({"id": "b", "text": "x", "pan": {"from": "right", "to": -0.3}})
    assert isinstance(beat.pan, config.PanMove) and beat.pan.from_ == "right" and beat.pan.to == -0.3
    assert config.SceneConfig.model_validate({"id": "s", "type": "title", "beats": [{"text": "x"}], "room": {"use": "hall", "narrator": True}}).room.narrator
    with pytest.raises(Exception, match="hall"):
        config.SceneConfig.model_validate({"id": "s", "type": "title", "beats": [{"text": "x"}], "room": "hal"})
    with pytest.raises(Exception):
        config.BeatConfig.model_validate({"id": "b", "text": "x", "pan": 1.5})
    with pytest.raises(VidgenError, match="did you mean 'room'"):
        Project.load(_write(tmp_path / "p", {"title": "t", "sections": [{"title": "a", "rooom": "hall", "beats": ["x"]}]}))
    scene = Project.load(_write(tmp_path / "q", {"title": "t", "sections": [{"title": "a", "room": "car", "beats": ["x"]}]})).config.scenes[0]
    assert scene.room == "car"


def _config(**audio: Any) -> config.VideoConfig:
    return config.parse_config({
        "title": "t",
        "voice": {"pan": "right"},
        "voices": {"ada": {"voice_id": "a", "pan": "left"}, "tom": {"voice_id": "b"}},
        "audio": audio,
        "characters": [{"name": "Ada", "voice": "ada"}],
        "scenes": [{"id": "s", "type": "title", "params": {"title": "x"}, "beats": [{"text": "x"}]}],
    })


def test_beat_staging_precedence_and_the_dry_narrator() -> None:
    cfg = _config(room="hall")
    scene = config.SceneConfig.model_validate({"id": "s", "type": "title", "beats": [
        {"text": "a"}, {"text": "b", "voice": "ada"}, {"text": "c", "voice": "ada", "pan": 0.2}, {"text": "d", "voice": "tom", "pan": {"from": "left", "to": "right"}},
    ]})
    narrator, ada, own, move = (beat_staging(cfg, scene, b) for b in scene.beats)
    assert narrator == VoiceStaging(pan=0.5, room="none")             # the narrator stays dry
    assert ada == VoiceStaging(pan=-0.5, room="hall")                  # the voice's pan, the video's room
    assert own.pan == 0.2 and move.pan == -0.5 and move.pan_to == 0.5
    assert beat_staging(cfg, scene, scene.beats[1], stage=0.7).pan == 0.7          # the character's place wins over the voice's pan
    assert beat_staging(cfg, scene, scene.beats[2], stage=0.7).pan == 0.2          # a beat's own pan wins
    wet = scene.model_copy(update={"room": config.RoomConfig(use="corridor", amount=0.5, narrator=True)})
    assert beat_staging(cfg, wet, scene.beats[0]) == VoiceStaging(pan=0.5, room="corridor", amount=0.5)
    dry = scene.model_copy(update={"room": "none"})
    assert beat_staging(cfg, dry, scene.beats[1]).room == "none"       # a scene's none cancels audio.room
    assert beat_staging(_config(), scene, scene.beats[0]).plain is False and VoiceStaging().plain


def test_pan_is_not_part_of_the_audio_hash() -> None:
    from vidgen.voices import audio_fields, resolve_voice

    assert "pan" not in audio_fields(resolve_voice(_config(), "ada"))
    assert resolve_voice(_config(), "tom").pan is None                 # not inherited from the base voice


def test_follow_stage_from_the_characters_places() -> None:
    cfg = _config(follow_stage=True)
    scene = config.SceneConfig.model_validate({"id": "s", "type": "stage", "params": {"characters": [{"name": "Ada", "at": "far_right"}]},
                                               "beats": [{"text": "a", "voice": "ada"}, {"text": "b"}]})
    assert params_stage_pan(cfg, scene, scene.beats[0]) == pytest.approx(0.8)
    assert params_stage_pan(cfg, scene, scene.beats[1]) is None        # nobody on the stage has that voice
    assert params_stage_pan(_config(), scene, scene.beats[0]) is None  # follow_stage off


# ----- signal -------------------------------------------------------------------------------------------


@pytest.mark.slow
def test_pan_law_and_moves() -> None:
    left = stage_voice(TONE, VoiceStaging(pan=-0.5))
    assert len(left) == RATE and _db(left[:, 0], left[:, 1]) == pytest.approx(7.66, abs=0.02)
    assert float(np.sum(left**2)) == pytest.approx(2 * float(np.sum(TONE**2)), rel=1e-4)   # equal power: as loud as centred
    move = stage_voice(TONE, VoiceStaging(pan=-0.8, pan_to=0.8))
    q = RATE // 4
    assert _db(move[:q, 0], move[:q, 1]) > 10 and _db(move[-q:, 1], move[-q:, 0]) > 10
    assert np.array_equal(stage_voice(TONE, VoiceStaging(pan=0.3, room="hall")), stage_voice(TONE, VoiceStaging(pan=0.3, room="hall")))


def test_rooms_ring_out_in_order_and_decorrelate() -> None:
    tails = {}
    for name in ("small_office", "corridor", "hall", "outdoors", "car"):
        y = stage_voice(TONE, VoiceStaging(room=name)).astype(np.float64)
        assert len(y) > RATE
        tail = y[RATE + RATE // 20 : RATE + RATE // 2]
        tails[name] = _db(tail, y[:RATE]) if len(tail) else -math.inf
    assert tails["hall"] > tails["corridor"] > tails["small_office"] > tails["car"]
    left, right = reverb_ir("hall", 0), reverb_ir("hall", 1)
    assert abs(float(np.dot(left, right)) / math.sqrt(float(np.dot(left, left) * np.dot(right, right)))) < 0.1
    assert 10 * math.log10(float(np.sum(left**2))) == pytest.approx(ROOM_PRESETS["hall"].wet_db, abs=0.01)


@pytest.mark.slow
def test_hall_decay_matches_its_rt60() -> None:
    ir = reverb_ir("hall", 0)
    spectrum = np.fft.rfft(ir, 2 * len(ir))
    freqs = np.fft.rfftfreq(2 * len(ir), 1 / RATE)
    band = np.fft.irfft(spectrum * ((freqs > 354) & (freqs < 707)), 2 * len(ir))[: len(ir)]
    edc = np.cumsum((band**2)[::-1])[::-1]
    edc = 10 * np.log10(edc / edc[0])
    idx = np.nonzero((edc <= -5) & (edc >= -35))[0]
    rt = -60 / np.polyfit(idx / RATE, edc[idx], 1)[0]
    assert rt == pytest.approx(ROOM_PRESETS["hall"].rt60, rel=0.1)


def test_phone_keeps_the_band_and_the_level() -> None:
    noise = np.random.default_rng(1).standard_normal(RATE).astype(np.float32)[:, None] * 0.1
    y = stage_voice(noise, VoiceStaging(room="phone"))
    assert len(y) == RATE and _db(y, np.repeat(noise, 2, axis=1)) == pytest.approx(0.0, abs=0.01)
    spectrum = np.abs(np.fft.rfft(y[:, 0])) ** 2
    freqs = np.fft.rfftfreq(RATE, 1 / RATE)
    inside = spectrum[(freqs > 500) & (freqs < 3000)].mean()
    assert 10 * math.log10(spectrum[freqs < 100].mean() / inside) < -25 and 10 * math.log10(spectrum[freqs > 8000].mean() / inside) < -25


def test_a_tail_past_the_limit_fades_out() -> None:
    y = stage_voice(TONE, VoiceStaging(room="hall"), limit=RATE + RATE // 2)
    assert len(y) == RATE + RATE // 2 and np.abs(y[-10:]).max() < 1e-4
    assert np.array_equal(y[:RATE], stage_voice(TONE, VoiceStaging(room="hall"))[:RATE])


def test_widen() -> None:
    x = np.stack([np.sin(np.arange(100.0)), np.cos(np.arange(100.0))], axis=1)
    assert widen(x, 1.0) is x
    mono = widen(x, 0.0)
    assert np.allclose(mono[:, 0], mono[:, 1]) and np.allclose(mono[:, 0], x.mean(axis=1))
    assert np.allclose(widen(x, 2.0).mean(axis=1), x.mean(axis=1))


# ----- the mono check -----------------------------------------------------------------------------------


@pytest.mark.parametrize("right, ok, fold", [(1.0, True, 0.0), (0.0, True, 3.01), (-1.0, False, None)], ids=["centre", "hard_left", "anti_phase"])
def test_mono_check(tmp_path: Path, right: float, ok: bool, fold: float | None) -> None:
    tone = TONE[:, 0]
    path = tmp_path / "x.wav"
    write_wav(path, np.stack([tone, right * tone], axis=1))
    measured = audio_check.measure_file(path)
    result = audio_check.mono_check(measured)
    assert result.ok is ok and [i.name for i in result.items] == ["correlation", "worst second", "mono fold"]
    if fold is not None:
        assert measured.mono_fold_db == pytest.approx(fold, abs=0.02)
    assert measured.to_json()["correlation"] == pytest.approx(right, abs=0.001)


@pytest.mark.slow
def test_mono_check_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "x.wav"
    write_wav(path, np.stack([TONE[:, 0], -TONE[:, 0]], axis=1))
    assert cli.main(["audio", "check", str(path), "--preset", "broadcast", "--lufs", "-20"]) == 1   # broadcast fails anyway
    assert "mono       FAIL" in capsys.readouterr().out
    mono = tmp_path / "m.wav"
    write_wav(mono, TONE[:, 0])
    assert cli.main(["audio", "check", str(mono), "--mono"]) == 0 and "mono  " not in capsys.readouterr().out
    capsys.readouterr()
    centred = tmp_path / "c.wav"
    write_wav(centred, np.repeat(TONE, 2, axis=1))
    assert cli.main(["audio", "check", str(centred), "--mono", "--preset", "custom", "--lufs", "-20.7"]) == 0
    assert cli.main(["audio", "check", str(path), "--preset", "custom", "--lufs", "-20.7"]) == 0          # the preset passes ...
    assert cli.main(["audio", "check", str(path), "--mono", "--preset", "custom", "--lufs", "-20.7"]) == 1  # ... the mono check does not


# ----- renders ------------------------------------------------------------------------------------------

PIN: dict[str, Any] = {
    "title": "Pin",
    "narration": {"pad": 0.3, "words_per_second": 2},
    "voices": {"b": {"voice_id": "other"}},
    "music": {"source": "calm"},
    "sections": [
        {"id": "one", "title": "One", "sfx": [{"sound": "chime", "at": 0.1}], "beats": ["one two three four", {"text": "a b c d", "voice": "b"}]},
        {"id": "two", "beats": [{"text": "e f g h", "sting": "reveal"}, {"text": "i j k l", "voice": "b"}]},
    ],
}
#: The audio-only render of :data:`PIN` as Step 284 made it (RMS of each half second): staging
#: must never change it while unset.
PINNED_RMS = [0.03958, 0.144599, 0.143564, 0.091011, 0.090911, 0.143437, 0.143369, 0.00732, 0.036565, 0.11344, 0.143063, 0.128317,
              0.00734, 0.143375, 0.143282, 0.090624, 0.003207, 0.001814]


@pytest.mark.slow
def test_audio_only_render_is_pinned_without_staging(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "p", PIN))
    _voice_all(project)
    out = _read_24(render_audio(project).output)
    blocks = out[: len(out) // (RATE // 2) * (RATE // 2)].reshape(-1, RATE // 2, 2)
    assert len(out) == 441600 and [float(np.sqrt(np.mean(b**2))) for b in blocks] == pytest.approx(PINNED_RMS, abs=2e-6)
    neutral = {**PIN, "voices": {"b": {"voice_id": "other", "pan": "centre"}}, "audio": {"room": "none", "music_width": 1.0}}
    same = Project.load(_write(tmp_path / "q", neutral))
    _voice_all(same)
    assert render_audio(same).output.read_bytes() == render_audio(project).output.read_bytes()
    # Step 288's options unset or neutral (no bed, cues dry, scene sounds on a project without stage or clip scenes)
    designed = {**PIN, "audio": {"sfx_room": False, "ambience_crossfade": 4.0, "scene_sounds": True}}
    designed["sections"] = [{**PIN["sections"][0], "ambience": False, "sfx": [{"sound": "chime", "at": 0.1, "repeat": 1, "room": False, "pan": "centre"}]},
                            PIN["sections"][1]]
    still = Project.load(_write(tmp_path / "r", designed))
    _voice_all(still)
    assert render_audio(still).output.read_bytes() == render_audio(project).output.read_bytes()
    # Step 290's options unset or neutral (no split, no spoken credits, no cold open)
    delivered = {**PIN, "audio_output": {"split": "none", "loudness": "none"}, "credits": {"speak": False, "voiced_by": {"b": "Bo"}}, "cold_open": None}
    plain = Project.load(_write(tmp_path / "s", delivered))
    _voice_all(plain)
    assert render_audio(plain).output.read_bytes() == render_audio(project).output.read_bytes()


@pytest.mark.slow
def test_staged_render_places_the_voices(tmp_path: Path) -> None:
    data = {**PIN, "voices": {"b": {"voice_id": "other", "pan": "left"}}, "audio": {"music_width": 0.0}}
    data["sections"] = [PIN["sections"][0], {**PIN["sections"][1], "room": {"use": "hall", "narrator": True}}]
    data["sections"][1]["beats"] = [{"text": "e f g h", "pan": {"from": "right", "to": "left"}}, {"text": "i j k l", "voice": "b"}]
    project = Project.load(_write(tmp_path / "p", data))
    rng = np.random.default_rng(5)
    for _, beat in project.beats():   # noise bursts: a room adds power to them (a steady tone would interfere with its own reverb)
        write_wav(project.audio_dir / f"{beat.id}.mp3", (0.05 * rng.standard_normal(round(1.2 * RATE))).astype(np.float32))
    result = render_audio(project)
    voice = decode_audio(project.render_dir(False) / "audio" / "voice.wav").astype(np.float64)
    beats = {b.id: b for b in plan_audio(project).beats}
    assert beats["two_b2"].staging == VoiceStaging(pan=-0.5, room="hall") and beats["one_b1"].staging.plain

    def part(beat: str, seconds: float = 1.2) -> np.ndarray:
        start = round(beats[beat].start * RATE)
        return voice[start : start + round(seconds * RATE)]

    assert _db(part("one_b1")[:, 0], part("one_b1")[:, 1]) == pytest.approx(0.0, abs=1e-6)   # the narrator: centred, dry
    assert _db(part("one_b2")[:, 0], part("one_b2")[:, 1]) == pytest.approx(7.66, abs=0.1)    # b on the left
    assert _db(part("two_b2")[:, 0], part("two_b2")[:, 1]) > 5                                # ... in the hall too
    moving = part("two_b1")
    assert _db(moving[: RATE // 5, 1], moving[: RATE // 5, 0]) > 4 and _db(moving[-RATE // 5 :, 0], moving[-RATE // 5 :, 1]) > 4
    tail = part("two_b2", 1.7)[round(1.3 * RATE) :]
    assert _db(tail, part("two_b2")) > -30                                                     # the hall rings on after the line
    assert result.timings["stereo"]["preset"] == "mono" and result.timings["stereo"]["ok"]


@pytest.mark.slow
def test_music_width_zero_is_mono(tmp_path: Path) -> None:
    root = _write(tmp_path / "p", {"title": "t", "music": {"source": "calm"}, "audio": {"music_width": 0.0},
                                   "scenes": [{"id": "s", "type": "text_card", "params": {"text": "x"}, "duration": 2.0}]})
    wav = tmp_path / "v.wav"
    write_wav(wav, np.zeros((2 * RATE, 2), dtype=np.float32))
    timings = {"scenes": [{"id": "s", "start": 0.0, "duration": 2.0, "beats": []}]}
    out = tmp_path / "m.wav"
    mix.mix_audio(Project.load(root), timings, [wav], None, out)
    x = _read_24(out)
    assert np.abs(x).max() > 1e-3 and np.array_equal(x[:, 0], x[:, 1])


def _scene_sounds(project: Project, scene_id: str, scene_type: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[np.ndarray]:
    """Render ``scene_id`` (160x90, 5 fps) and return the voice WAVs it adds, in order."""
    from manim import tempconfig

    from vidgen import extensions, registry

    extensions.load_builtins()
    cls = registry.get(scene_type).cls
    sounds: list[np.ndarray] = []
    add_sound = cls.add_sound

    def recording(self: Any, path: str, time_offset: float = 0, gain: Any = None, **kwargs: Any) -> None:
        if Path(path).name == "narration.wav":
            sounds.append(decode_audio(Path(path)).astype(np.float64))
        add_sound(self, path, time_offset, gain, **kwargs)

    monkeypatch.setattr(cls, "add_sound", recording)
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_rate": 5, "media_dir": str(tmp_path / "media"),
                     "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}):
        with extensions.project_session(project):
            cls(project.scene(scene_id), project).render()
    return sounds


def _noise_voices(project: Project, seconds: float = 1.0) -> None:
    rng = np.random.default_rng(3)
    for _, beat in project.beats():
        write_wav(project.audio_dir / f"{beat.id}.mp3", (0.05 * rng.standard_normal(round(seconds * RATE))).astype(np.float32))


@pytest.mark.slow
@pytest.mark.render
def test_a_video_scene_pans_and_rooms_its_voices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = {"title": "t", "voices": {"pip": {"voice_id": "p", "pan": "left"}}, "narration": {"pad": 0.4},
            "scenes": [{"id": "talk", "type": "text_card", "params": {"text": "Hi"}, "room": "hall",
                        "beats": [{"text": "one two"}, {"text": "three four", "voice": "pip"}]}]}
    project = Project.load(_write(tmp_path / "p", data))
    _noise_voices(project)
    narrator, pip = _scene_sounds(project, "talk", "text_card", tmp_path, monkeypatch)
    assert len(narrator) == RATE and np.array_equal(narrator[:, 0], narrator[:, 1])          # the narrator: dry, centred, as before
    assert RATE < len(pip) <= round(1.4 * RATE) + 1 and np.abs(pip[-20:]).max() < 1e-3       # the hall's tail, faded by the scene's end
    assert _db(pip[:RATE, 0], pip[:RATE, 1]) > 5


@pytest.mark.slow
@pytest.mark.render
def test_follow_stage_pans_to_the_speaker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = {"title": "t", "audio": {"follow_stage": True}, "narration": {"pad": 0.3},
            "voices": {"pip_voice": {"voice_id": "p1"}, "kit_voice": {"voice_id": "k1"}},
            "characters": [{"name": "pip", "voice": "pip_voice", "look": {"body": "bean"}}, {"name": "kit", "voice": "kit_voice", "look": {"body": "tall"}}],
            "scenes": [{"id": "yard", "type": "stage", "params": {"background": "#88AACC", "idle": False, "characters": [{"name": "pip", "at": "far_left"}, {"name": "kit", "at": "right"}]},
                        "beats": [{"text": "hello there", "voice": "pip_voice"}, {"text": "hi", "voice": "kit_voice"}]}]}
    project = Project.load(_write(tmp_path / "p", data))
    _noise_voices(project, 0.6)
    pip, kit = _scene_sounds(project, "yard", "stage", tmp_path, monkeypatch)
    assert _db(pip[:, 0], pip[:, 1]) > 10 and _db(kit[:, 1], kit[:, 0]) > 5


def test_fingerprint_changes_only_with_staging(tmp_path: Path) -> None:
    base = {"title": "t", "voices": {"a": {"voice_id": "x"}},
            "scenes": [{"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "hello", "voice": "a"}]}]}
    plain = scene_fingerprint(Project.load(_write(tmp_path / "a", base)), "s")
    centred = {**base, "voices": {"a": {"voice_id": "x", "pan": "centre"}}}
    assert scene_fingerprint(Project.load(_write(tmp_path / "b", centred)), "s") == plain
    panned = {**base, "voices": {"a": {"voice_id": "x", "pan": "left"}}}
    assert scene_fingerprint(Project.load(_write(tmp_path / "c", panned)), "s") != plain
    roomed = {**base, "audio": {"room": "hall"}}
    assert scene_fingerprint(Project.load(_write(tmp_path / "d", roomed)), "s") != plain
