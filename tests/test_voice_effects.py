"""Voice effects (DESIGN.md §100.2): the presets, the filter chains, the config, the hash and a
real ffmpeg run over a fake Kokoro voice."""

from __future__ import annotations

import io
import typing
import wave
from typing import Any

import numpy as np
import pytest
import yaml

from test_tts_kokoro import KOKORO, Factory, fake, kokoro_config  # noqa: F401 (fake: a fixture)
from vidgen import config, tts
from vidgen.cli import main
from vidgen.config import VoiceConfig, VoiceEffectConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.speech import audio_duration, read_alignment
from vidgen.tts import kokoro as kk
from vidgen.tts.effects import EffectProvider, level_match, with_effect
from vidgen.tts.run import describe_voice, plan_tts
from vidgen.voice_effects import (
    MATCH_LIMIT,
    VOICE_EFFECTS,
    OTHERWORLDLY_PITCH,
    TAILS,
    VoiceEffect,
    effect_filter,
    voice_effect,
)

PLAIN_KEY = "05cb88daec48cc27a4841b20f737de3c7cb847c4"   # Kokoro's pinned hash of "Hello there." (Step 65)


# ----- the presets (pure) -------------------------------------------------------------------------


def test_names_are_the_config_literal() -> None:
    assert typing.get_args(config.VoiceEffectName) == VOICE_EFFECTS


def test_settings_become_effects() -> None:
    assert voice_effect(None) is None and voice_effect([]) is None
    assert voice_effect("hall") == VoiceEffect(("hall",), 0.0, 0.5)
    assert voice_effect("deep") == VoiceEffect((), -4.0, 0.5)                       # a pitch preset is its pitch
    assert voice_effect(["hall", "deep", "robot"]) == VoiceEffect(("robot", "hall"), -4.0, 0.5)   # fixed order
    assert voice_effect(["hall", "deep"]) == voice_effect(["deep", "hall"])
    assert voice_effect("otherworldly") == VoiceEffect(("chorus", "hall"), OTHERWORLDLY_PITCH, 0.5)
    assert voice_effect(["otherworldly", "deep"]).pitch == -4.0
    assert voice_effect({"use": "robot", "pitch": -6, "amount": 0.8}) == VoiceEffect(("robot",), -6.0, 0.8)
    assert voice_effect(VoiceEffectConfig(pitch=2)) == VoiceEffect((), 2.0, 0.5)   # only a pitch
    assert voice_effect(VoiceEffectConfig(pitch=0)) is None
    with pytest.raises(ValueError, match="unknown voice effect 'reverb'"):
        voice_effect("reverb")
    assert voice_effect("hall").tail == TAILS["hall"] and voice_effect("robot").tail == 0.0


def test_filter_chains() -> None:
    hall = effect_filter(voice_effect("hall"))
    assert hall.startswith("aresample=48000,aformat=channel_layouts=mono,apad=pad_dur=0.553,aecho=1:0.8:37|59|")
    assert hall.endswith("alimiter=limit=0.89:level=false") and "asetrate" not in hall
    deep = effect_filter(voice_effect("deep"))
    assert "asetrate=38098,aresample=48000,atempo=1.259909" in deep and "apad" not in deep
    robot = effect_filter(voice_effect({"use": "robot", "pitch": -6}))
    assert robot.index("afftfilt") < robot.index("asetrate")                        # the pitch moves the robot's buzz
    other = effect_filter(voice_effect("otherworldly"))
    assert other.index("asetrate") < other.index("chorus") < other.index("aecho")
    strong, soft = (effect_filter(voice_effect({"use": "echo", "amount": a})) for a in (1.0, 0.2))
    assert "aecho=1:0.85:110|230:0.600|0.300" in strong and "aecho=1:0.85:110|230:0.120|0.060" in soft


# ----- the config and the voices ------------------------------------------------------------------


def test_config_takes_names_lists_and_mappings() -> None:
    assert VoiceConfig(provider="kokoro", effect="hall").effect == "hall"
    assert VoiceConfig(provider="kokoro", effect=["deep", "hall"]).effect == ["deep", "hall"]
    assert VoiceConfig(provider="kokoro", effect={"use": "robot", "pitch": -5}).effect == VoiceEffectConfig(use="robot", pitch=-5)
    for bad in ("reverb", {"use": "hall", "amount": 2}, {"pitch": 13}, {"use": "hall", "wet": 1}):
        with pytest.raises(ValueError):
            VoiceConfig(provider="kokoro", effect=bad)


def test_named_voices_do_not_inherit_the_effect(make_project) -> None:
    data = kokoro_config({"effect": "echo"}, voices={"guard": {"voice": "am_onyx", "effect": "otherworldly"}, "ana": {"voice": "af_bella"}})
    data["scenes"][1]["voice"] = "guard"
    project = Project.load(make_project(data))
    assert project.voice(None).effect == "echo" and project.voice("guard").effect == "otherworldly"
    assert project.voice("ana").effect is None                       # a speaker's own, like emotion
    providers = tts.beat_providers(project)
    assert isinstance(providers["intro_b1"], EffectProvider) and providers["intro_b1"].effect == voice_effect("echo")
    assert providers["custom"].effect == voice_effect("otherworldly")
    assert describe_voice(project.voice("guard")).endswith(", effect chorus+hall (pitch -3)")
    assert describe_voice(VoiceConfig(provider="kokoro", effect={"pitch": 2})).endswith(", effect pitch +2")


def test_hash_unchanged_without_an_effect_and_changed_with_one() -> None:
    plain = tts.get_provider(VoiceConfig(**KOKORO))
    assert not isinstance(plain, EffectProvider) and plain.cache_key("Hello there.") == PLAIN_KEY
    hall = tts.get_provider(VoiceConfig(**KOKORO, effect="hall"))
    keys = {hall.cache_key("Hello there."), tts.get_provider(VoiceConfig(**KOKORO, effect={"use": "hall", "amount": 0.8})).cache_key("Hello there.")}
    assert PLAIN_KEY not in keys and len(keys) == 2
    assert hall.matches("Hello there.", hall.cache_key("Hello there.") + "\n") and not hall.matches("Hello there.", PLAIN_KEY)
    assert tts.get_provider(VoiceConfig(**KOKORO, effect={"pitch": 0})).cache_key("Hello there.") == PLAIN_KEY   # changes nothing


class _Inner:
    name = "fake"
    timings_included = True
    last_phonemes = [("h", 0.0, 0.1)]

    def cache_key(self, text: str) -> str:
        return "k"

    def check_credentials(self) -> None:
        raise VidgenError("no key")


def test_the_wrapper_is_its_provider_otherwise() -> None:
    wrapped = EffectProvider(_Inner(), voice_effect("echo"))
    assert (wrapped.name, wrapped.timings_included, wrapped.last_phonemes) == ("fake", True, [("h", 0.0, 0.1)])
    with pytest.raises(VidgenError, match="no key"):
        wrapped.check_credentials()
    with pytest.raises(AttributeError):
        _ = wrapped.reported_cost


# ----- a real run (ffmpeg) over the fake Kokoro ---------------------------------------------------


def test_tts_run_with_an_effect(make_project, fake: Factory, capsys: pytest.CaptureFixture[str]) -> None:
    data = kokoro_config(voices={"guard": {"voice": "am_onyx", "effect": "hall", "label": "Guard"}})
    data["scenes"][1]["voice"] = "guard"
    root = make_project(data)
    assert main(["tts", str(root), "--dry-run"]) == 0
    assert "voice guard (kokoro am_onyx (lang a, American English), speed 1, cpu, effect hall)" in capsys.readouterr().out
    assert main(["tts", str(root)]) == 0
    capsys.readouterr()
    project = Project.load(root)
    audio = root / "audio"
    text = project.config.scenes[1].beats[0].text
    assert (audio / "custom.hash").read_text(encoding="utf-8") == tts.beat_providers(project)["custom"].cache_key(text)
    plain = project.config.scenes[0].beats[0].text   # the narrator's, no effect (the fake: 0.3 s a word)
    expected = audio_duration(audio / "intro_b1.mp3") + 0.3 * (len(text.split()) - len(plain.split())) + TAILS["hall"]
    assert audio_duration(audio / "custom.mp3") == pytest.approx(expected, abs=0.08)   # the tail rings out
    assert read_alignment(audio, "custom", text) is not None                      # the timings are kept
    assert {s.state for s in tts.audio_status(project)} == {"ok"}
    data["voices"]["guard"]["effect"] = "echo"
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert [b.id for b in plan_tts(Project.load(root)).todo] == ["custom"]       # only that voice's beats


def _speech_like(seconds: float = 3.0, rate: int = 24000) -> bytes:
    """A WAV of a voice-like signal: harmonics of a gliding 110-190 Hz pitch in syllable bursts."""
    t = np.arange(int(seconds * rate)) / rate
    f0 = 150 + 40 * np.sin(2 * np.pi * 0.7 * t)
    phase = 2 * np.pi * np.cumsum(f0) / rate
    voice = sum(np.sin(k * phase) / k for k in range(1, 12))
    syllables = np.clip(np.sin(2 * np.pi * 3.2 * t), 0, None) ** 0.6
    pcm = (0.25 * voice * syllables / np.max(np.abs(voice)) * 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return out.getvalue()


def test_every_effect_is_level_matched_to_the_dry_voice(tmp_path) -> None:
    from vidgen.loudness import integrated_loudness
    from vidgen.render.ffmpeg import decode_mono

    dry_file = tmp_path / "dry.wav"
    dry_file.write_bytes(_speech_like())
    dry = integrated_loudness(decode_mono(dry_file, 48000))
    for setting in ("robot", {"use": "robot", "pitch": -5}, "radio", "echo", "hall", "otherworldly", ["deep", "chorus"]):
        out = tmp_path / "wet.mp3"
        out.write_bytes(with_effect(dry_file.read_bytes(), voice_effect(setting)))
        wet = decode_mono(out, 48000)
        assert integrated_loudness(wet) == pytest.approx(dry, abs=1.0), setting
        assert np.max(np.abs(wet)) < 1.0
    assert level_match(np.zeros(48000), np.ones(48000)) == 0.0                      # silence: no correction
    loud = np.sin(np.arange(96000) / 7.0)
    assert level_match(loud * 0.001, loud) == -MATCH_LIMIT                         # never more than the limit


def test_variant_with_another_effect_gets_its_own_audio(make_project) -> None:
    data: dict[str, Any] = kokoro_config(voices={"guard": {"voice": "am_onyx"}})
    data["scenes"][1]["voice"] = "guard"
    data["variants"] = {"eerie": {"voices": {"guard": {"effect": "hall"}}}, "same": {"title": "Other"}}
    root = make_project(data)
    assert Project.load(root, variant="eerie").has_own_audio
    assert not Project.load(root, variant="same").has_own_audio
