"""Step 135: voices with feeling, part 1 (``emotion:`` for Kokoro, DESIGN.md §72).

The emotion table and its parsing are pure; the prosody edits run on numpy arrays (and one tiny
ffmpeg call for the pitch); synthesis uses the fake Kokoro pipeline of ``test_tts_kokoro``."""

from __future__ import annotations

import hashlib
import json
import math
import typing
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from test_tts_kokoro import KOKORO, Factory, FakePipeline, fake, kokoro_config, tone  # noqa: F401 (fake: a fixture)
from vidgen import config, emotions, kokoro_voices, tts
from vidgen.cli import main, validate_warnings
from vidgen.config import EmotionConfig, VoiceConfig
from vidgen.emotions import EMOTIONS, Prosody, manner_emotion, prosody
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.screenplay import parse_screenplay, screenplay_project
from vidgen.sfx import decode_audio
from vidgen.speech import audio_duration, read_alignment
from vidgen.tts import kokoro as kk
from vidgen.tts import prosody as pr
from vidgen.tts.run import plan_tts, run_tts

RATE = kk.SAMPLE_RATE


# ----- the table and its parsing (pure) -----------------------------------------------------------


def test_table_is_the_config_literal_and_in_range() -> None:
    assert typing.get_args(config.EmotionName) == emotions.EMOTION_NAMES
    assert EMOTIONS["neutral"].is_neutral and all(not p.is_neutral for name, p in EMOTIONS.items() if name != "neutral")
    for p in EMOTIONS.values():
        assert emotions.SPEED_RANGE[0] <= p.speed <= emotions.SPEED_RANGE[1]
        assert emotions.PITCH_RANGE[0] <= p.pitch <= emotions.PITCH_RANGE[1]
        assert emotions.GAIN_RANGE[0] <= p.gain <= emotions.GAIN_RANGE[1]
        assert emotions.PAUSES_RANGE[0] <= p.pauses <= emotions.PAUSES_RANGE[1]
    # the directions the table promises
    assert EMOTIONS["excited"].speed > 1 and EMOTIONS["excited"].pitch > 0 and EMOTIONS["excited"].pauses < 1
    assert EMOTIONS["sad"].speed < 1 and EMOTIONS["sad"].pitch < 0 and EMOTIONS["sad"].pauses > 1
    assert EMOTIONS["whisper"].gain < EMOTIONS["sad"].gain < 0 < EMOTIONS["angry"].gain < EMOTIONS["shout"].gain


def test_prosody_of_a_name_or_a_mapping() -> None:
    assert prosody(None) is None and prosody("neutral") is None
    assert prosody("sad") == EMOTIONS["sad"]
    changed = prosody(EmotionConfig(like="sad", pitch=-2))
    assert changed == Prosody("sad", 0.86, -2.0, -3.0, 1.5)
    assert prosody(EmotionConfig(pauses=1.5)) == Prosody("neutral", pauses=1.5)
    assert prosody(EmotionConfig(like="excited", speed=1, pitch=0, gain=0, pauses=1)) is None   # changes nothing
    for bad in ({"pitch": 4}, {"speed": 0.3}, {"gain": 7}, {"pauses": 0.1}, {"like": "joyful"}, {"tone": 1}):
        with pytest.raises(ValueError):
            EmotionConfig(**bad)
    with pytest.raises(ValueError):
        config.BeatConfig(id="b", text="Hi.", emotion="joyful")


def test_manner_words_name_emotions() -> None:
    assert manner_emotion("cross, arms crossed") == ("angry", ["arms crossed"])
    assert manner_emotion("Whispering") == ("whisper", [])
    assert manner_emotion("waving") == (None, ["waving"])
    assert manner_emotion("excited and sad") == ("excited", [])   # the first one


def test_weighted_voice_blends() -> None:
    assert kokoro_voices.blend_weights("af_heart") is None and kokoro_voices.blend_weights("af_bella,af_heart") is None
    assert kokoro_voices.blend_weights("af_heart+af_bella:0.6") == [("af_heart", 0.4), ("af_bella", 0.6)]
    assert kokoro_voices.blend_weights("af_heart:2 + af_bella:1") == [("af_heart", pytest.approx(2 / 3)), ("af_bella", pytest.approx(1 / 3))]
    assert kokoro_voices.blend_weights("a+b+c:0.5") == [("a", 0.25), ("b", 0.25), ("c", 0.5)]
    for bad in ("af_heart+", "af_heart+af_bella:0", "af_heart:0.7+af_bella:0.5+am_adam", "af_heart+af_bella,af_sky"):
        with pytest.raises(ValueError, match="voice blend"):
            kokoro_voices.blend_weights(bad)
    assert kokoro_voices.voice_parts("af_heart+af_bella:0.6") == ["af_heart", "af_bella"]
    assert kokoro_voices.lang_of_voice("bf_emma+af_bella:0.3") == "b"
    assert kokoro_voices.voice_warnings("af_heart+af_belle:0.3", "a", None, False, "voice")[0].startswith("voice.voice: 'af_belle' is not among")


def test_bad_blends_are_config_errors(make_project) -> None:
    with pytest.raises(ValueError, match="voice blend"):
        VoiceConfig(provider="kokoro", voice="af_heart+af_bella:1.5")
    assert VoiceConfig(provider="openrouter", model="a/b", voice="x+y").voice == "x+y"   # only Kokoro reads +
    with pytest.raises(VidgenError, match=r"voices.ana.voice: voice blend 'af_heart\+'"):
        Project.load(make_project(kokoro_config(voices={"ana": {"voice": "af_heart+"}})))


# ----- which emotion a beat has -------------------------------------------------------------------


def emotion_config(**voice: Any) -> dict[str, Any]:
    data = kokoro_config(voice, voices={"ana": {"voice": "af_bella"}, "ben": {"voice": "am_michael", "emotion": "calm"}})
    data["scenes"][0]["beats"][1]["emotion"] = "excited"
    data["scenes"][1]["voice"] = "ben"
    return data


def test_beat_emotion_beat_then_its_voice_not_inherited(make_project) -> None:
    project = Project.load(make_project(emotion_config(emotion="sad")))
    assert project.beat_emotion("intro_b1") == EMOTIONS["sad"]          # the base voice's
    assert project.beat_emotion("intro_b2") == EMOTIONS["excited"]      # the beat's own wins
    assert project.beat_emotion("custom") == EMOTIONS["calm"]           # ben's own
    assert project.voice("ana").emotion is None                          # not inherited from the base voice
    data = emotion_config()
    data["scenes"][1]["beats"][0]["emotion"] = "neutral"
    assert Project.load(make_project(data, folder="p2")).beat_emotion("custom") is None   # back to plain


def test_variant_with_other_emotions_gets_its_own_audio(make_project) -> None:
    data = emotion_config()
    data["variants"] = {"same": {"title": "Other"}}
    root = make_project(data)
    assert not Project.load(root, variant="same").has_own_audio
    data["variants"] = {"moody": {"voices": {"ben": {"emotion": "sad"}}}}
    root = make_project(data, folder="p2")
    assert Project.load(root, variant="moody").has_own_audio


# ----- the audio hash -----------------------------------------------------------------------------


def test_hash_changes_only_with_an_emotion() -> None:
    plain = kk.KokoroProvider(VoiceConfig(**KOKORO))
    assert plain.cache_key("Hello there.") == "05cb88daec48cc27a4841b20f737de3c7cb847c4"   # pinned (Step 65)
    assert kk.KokoroProvider(VoiceConfig(**KOKORO), emotion=EMOTIONS["neutral"]).cache_key("Hello there.") == plain.cache_key("Hello there.")
    excited = kk.KokoroProvider(VoiceConfig(**KOKORO), emotion=EMOTIONS["excited"])
    spec = {**plain.spec(), "emotion": {"name": "excited", "speed": 1.12, "pitch": 2.0, "gain": 3.0, "pauses": 0.7}}
    assert excited.cache_key("Hi") == hashlib.sha1(f"{json.dumps(spec, sort_keys=True)}|Hi".encode()).hexdigest()
    tweaked = kk.KokoroProvider(VoiceConfig(**KOKORO), emotion=prosody(EmotionConfig(like="excited", pitch=1)))
    sad = kk.KokoroProvider(VoiceConfig(**KOKORO), emotion=EMOTIONS["sad"])
    assert len({plain.cache_key("Hi"), excited.cache_key("Hi"), tweaked.cache_key("Hi"), sad.cache_key("Hi")}) == 4
    # the other providers' pinned keys without an emotion (with one: tests/test_emotions_providers.py)
    assert tts.get_provider(VoiceConfig()).cache_key("Hello there.") == "e07179cc8214a9008a163a96e3ab594f0d3da455"
    routed = VoiceConfig(provider="openrouter", model="mistralai/voxtral-mini-tts-2603", voice="en_paul_neutral")
    assert tts.get_provider(routed).cache_key("Hello there.") == "ed12a9d42adbd729f424fb9c6b73f406f5b27aaa"


def test_beat_providers_per_voice_and_emotion(make_project) -> None:
    project = Project.load(make_project(emotion_config()))
    providers = tts.beat_providers(project)
    assert providers["intro_b1"] is not providers["intro_b2"]
    assert (providers["intro_b1"].emotion, providers["intro_b2"].emotion, providers["custom"].emotion) == (None, EMOTIONS["excited"], EMOTIONS["calm"])
    plain = make_project(kokoro_config(), folder="plain")
    assert tts.beat_providers(Project.load(plain))["intro_b1"].cache_key("Hello there.") == "05cb88daec48cc27a4841b20f737de3c7cb847c4"


def test_kokoro_emotions_need_no_warning(make_project) -> None:
    project = Project.load(make_project(emotion_config(), folder="k"))
    assert not tts.emotion_warnings(project) and not [w for w in validate_warnings(project) if w.startswith("emotion")]


# ----- the prosody edits --------------------------------------------------------------------------


TIMED = [("Hello", 0.1, 0.5), (",", 0.5, 0.7), ("big", 0.7, 0.9), ("world", 0.9, 1.3), (".", 1.3, 1.5)]


def test_inner_pauses_are_punctuation_followed_by_words() -> None:
    assert pr.inner_pauses(TIMED) == [(0.5, 0.7, ",")]   # the full stop at the end is the beat's padding
    assert pr.inner_pauses([("Hi", 0.0, 0.2), ("!", 0.2, 0.21), ("Yo", 0.3, 0.5)]) == []   # too short to edit
    assert pr.inner_pauses([("Wait", 0, 0.3), ("...", 0.3, 0.6), ("what", 0.6, 0.9), ("?", 0.9, 1.0)]) == [(0.3, 0.6, "...")]
    assert (pr.natural_pause(","), pr.natural_pause("..."), pr.natural_pause("!")) == (pr.CLAUSE_PAUSE, pr.SENTENCE_PAUSE, pr.SENTENCE_PAUSE)


@pytest.mark.parametrize(("pause", "factor", "delta"), [
    ((0.5, 0.7, ","), 1.5, 0.1),     # 0.5 x the pause (0.2 s)
    ((0.55, 0.65, "."), 1.5, 0.2),   # Kokoro's 0.1 s full stop counts as a natural 0.4 s pause
    ((0.5, 0.7, ","), 0.5, -0.1),    # half of the pause cut
    ((0.55, 0.65, "."), 0.5, -0.05),
])
def test_scale_pauses_and_shift_times(pause: tuple[float, float, str], factor: float, delta: float) -> None:
    samples = np.arange(int(1.6 * RATE), dtype=np.float32)
    edited, edits = pr.scale_pauses(samples, [pause], factor, RATE)
    assert edits == [(pytest.approx(0.6), pytest.approx(delta))]
    assert len(edited) == pytest.approx(len(samples) + delta * RATE, abs=2)
    np.testing.assert_array_equal(edited[: int(0.5 * RATE)], samples[: int(0.5 * RATE)])   # before the pause: untouched
    np.testing.assert_array_equal(edited[-100:], samples[-100:])                              # the end moved, unchanged
    assert pr.shift_time(0.4, edits) == 0.4 and pr.shift_time(0.9, edits) == pytest.approx(0.9 + delta)
    if factor > 1:
        assert not edited[int(0.6 * RATE) + 10 : int((0.6 + delta) * RATE) - 10].any()     # silence inserted at the middle
    else:
        assert pr.shift_time(0.6, edits) == pytest.approx(0.6 + delta / 2)                   # inside the cut: its start
    assert pr.scale_pauses(samples, [pause], 1.0, RATE) == (samples, [])


def test_gain_is_louder_and_never_clips() -> None:
    wave = tone(0.5) * 3.0                     # peak 0.9
    louder = pr.apply_gain(wave, 5.0)
    assert np.abs(louder).max() < pr.LIMIT_CEILING
    assert np.sqrt(np.mean(louder**2)) > 1.2 * np.sqrt(np.mean(wave**2))
    quiet = pr.apply_gain(wave, -6.0)
    assert np.abs(quiet).max() == pytest.approx(0.9 * 10 ** (-6 / 20), rel=1e-3)
    assert pr.apply_gain(wave, 0.0) is wave


def frequency(samples: np.ndarray, rate: int) -> float:
    """Hz of a pure tone from its zero crossings."""
    signs = np.signbit(samples)
    return float(np.count_nonzero(signs[1:] != signs[:-1])) / 2 / (len(samples) / rate)


def test_pitch_shift_keeps_the_length(tmp_path: Path) -> None:
    assert pr.pitch_filter(0.0, RATE) is None
    assert pr.pitch_filter(3.0, RATE) == "asetrate=28541,aresample=24000,atempo=0.840896"
    wave = (0.3 * np.sin(2 * math.pi * 220 * np.arange(RATE) / RATE)).astype(np.float32)
    path = tmp_path / "up.mp3"
    path.write_bytes(kk.pcm_to_mp3(kk.pcm16(wave), filters=pr.pitch_filter(3.0, RATE)))
    shifted = decode_audio(path, rate=RATE, mono=True)[:, 0]
    assert len(shifted) / RATE == pytest.approx(1.0, abs=0.06)
    middle = shifted[int(0.2 * RATE) : int(0.8 * RATE)]
    assert frequency(middle, RATE) == pytest.approx(220 * 2 ** (3 / 12), rel=0.03)


# ----- synthesis with the fake pipeline -----------------------------------------------------------


class PhonemePipeline(FakePipeline):
    """The fake pipeline whose tokens also carry phonemes (as misaki's English tokens do)."""

    def __call__(self, text: str, voice: str, speed: float, split_pattern: Any) -> Any:
        for result in super().__call__(text, voice, speed, split_pattern):
            for token in result.tokens or ():
                token.phonemes = token.text.lower()
            yield result


def test_synthesis_applies_the_emotion_and_moves_the_timings(tmp_path: Path) -> None:
    made: list[PhonemePipeline] = []

    def factory(lang: str, device: str, model: Any) -> PhonemePipeline:
        made.append(PhonemePipeline(lang, device, model))
        return made[-1]

    engine = kk.KokoroEngine("cpu", factory)
    text = "Hello, big world."
    plain = kk.KokoroProvider(VoiceConfig(**KOKORO), engine=engine)
    audio, timing = plain.synthesize_timed(text)
    slow = kk.KokoroProvider(VoiceConfig(**KOKORO, speed=1.2), emotion=prosody(EmotionConfig(like="sad", pitch=0)), engine=engine)
    sad_audio, sad_timing = slow.synthesize_timed(text)
    assert [c["speed"] for c in made[0].calls] == [1.0, pytest.approx(1.2 * 0.86)]
    assert timing is not None and sad_timing is not None
    step = 0.3 / (1.2 * 0.86)
    added = 0.5 * pr.CLAUSE_PAUSE            # the fake's short "," lengthened by half a natural pause
    big = text.index("big")
    assert sad_timing["character_start_times_seconds"][big] == pytest.approx(0.1 + step + added, abs=1e-3)
    assert sad_timing["character_start_times_seconds"][0] == pytest.approx(0.1, abs=1e-3)   # before the pause: as spoken
    phonemes = {ps: (start, end) for ps, start, end in slow.last_phonemes}
    assert phonemes["hello"][0] == pytest.approx(0.1) and phonemes["big"][0] == pytest.approx(0.1 + step + added)   # visemes follow
    for name, data in (("plain", audio), ("sad", sad_audio)):
        (tmp_path / f"{name}.mp3").write_bytes(data)
    plain_samples = decode_audio(tmp_path / "plain.mp3", rate=RATE, mono=True)[:, 0]
    sad_samples = decode_audio(tmp_path / "sad.mp3", rate=RATE, mono=True)[:, 0]
    expected = 0.1 + 3 * step + 0.1 + added   # the fake's tone at this speed, plus the longer pause
    assert len(sad_samples) / RATE == pytest.approx(expected, abs=0.06)
    assert np.sqrt(np.mean(sad_samples**2)) < 0.8 * np.sqrt(np.mean(plain_samples**2))   # -3 dB


class BlendingPipeline(FakePipeline):
    """The fake pipeline with Kokoro's ``load_single_voice`` (a voice's style pack)."""

    packs = {"af_heart": np.full(4, 1.0, dtype=np.float32), "af_bella": np.full(4, 3.0, dtype=np.float32)}

    def load_single_voice(self, voice: str) -> np.ndarray:
        self.loaded = [*getattr(self, "loaded", []), voice]
        return self.packs[voice]


def test_weighted_blend_mixes_the_style_packs() -> None:
    made: list[BlendingPipeline] = []

    def factory(lang: str, device: str, model: Any) -> BlendingPipeline:
        made.append(BlendingPipeline(lang, device, model))
        return made[-1]

    engine = kk.KokoroEngine("cpu", factory)
    provider = kk.KokoroProvider(VoiceConfig(**KOKORO, voice="af_heart+af_bella:0.25"), engine=engine)
    provider.synthesize_timed("One two.")
    provider.synthesize_timed("Three.")
    voices = [c["voice"] for c in made[0].calls]
    np.testing.assert_allclose(voices[0], np.full(4, 0.75 * 1.0 + 0.25 * 3.0))
    assert voices[1] is voices[0] and made[0].loaded == ["af_heart", "af_bella"]   # mixed once
    assert kk.KokoroProvider(VoiceConfig(**KOKORO, voice="af_bella,af_heart"), engine=engine).voice_for(made[0]) == "af_bella,af_heart"


def test_tts_run_with_emotions(make_project, fake: Factory, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(emotion_config())
    assert main(["tts", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would generate intro_b2.mp3 (12 chars, voice default, excited)" in out and "would generate custom.mp3 (19 chars, voice ben, calm)" in out
    assert main(["tts", str(root)]) == 0
    capsys.readouterr()
    project = Project.load(root)
    providers = tts.beat_providers(project)
    audio = root / "audio"
    assert (audio / "intro_b2.hash").read_text(encoding="utf-8") == providers["intro_b2"].cache_key("Second beat.")
    assert read_alignment(audio, "intro_b2", "Second beat.") is not None
    assert {s.state for s in tts.audio_status(project)} == {"ok"}
    data = emotion_config()
    data["scenes"][0]["beats"][1]["emotion"] = {"like": "excited", "pitch": 1}
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert [b.id for b in plan_tts(Project.load(root)).todo] == ["intro_b2"]   # only the changed beat


def test_lip_sync_follows_the_edited_audio(make_project, fake: Factory) -> None:
    from vidgen.cartoon.visemes import read_visemes

    data = kokoro_config(characters=[{"name": "ana"}])
    data["scenes"][0]["beats"][0] = {"text": "Hello, big world.", "emotion": {"like": "sleepy", "pitch": 0}}
    root = make_project(data)
    run_tts(Project.load(root), out=lambda s: None)
    track = read_visemes(root / "audio", "intro_b1", "Hello, big world.")
    timing = read_alignment(root / "audio", "intro_b1", "Hello, big world.")
    assert track is not None and timing is not None
    assert track.duration == pytest.approx(audio_duration(root / "audio" / "intro_b1.mp3"), abs=0.05)   # the edited MP3's length


# ----- screenplays --------------------------------------------------------------------------------


def test_screenplay_manners_set_the_emotion() -> None:
    play = "# Scene: a\nPIP (cross): Rain!\nJUNO (whispers): It is a shower.\nNARRATOR (sleepy): Later.\nPIP (waving): Bye."
    draft = screenplay_project(parse_screenplay(play))
    beats = draft.config["scenes"][0]["beats"]
    assert [b.get("emotion") for b in beats] == ["angry", "whisper", "sleepy", None]
    assert beats[0]["actions"][0] == {"react": "pip", "expression": "angry"}
    assert draft.todo_count == 0   # an emotion word is understood, also for the narrator
